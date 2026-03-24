"""NemoClaw external specialist client — Pattern 1 tool-level bridge.

Bounded HTTP adapter for calling NemoClaw or OpenShell-backed specialist
services. Registered as deterministic ServiceRouter handlers so calls are
traceable through ServiceQuerySent / ServiceQueryResolved events.

Wave 38 1A: tool-level only. Not an LLMPort adapter.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import structlog

log = structlog.get_logger()

# Default timeout for external specialist calls (seconds).
_DEFAULT_TIMEOUT_S = 30.0

# Environment variable names for configuration.
_ENV_ENDPOINT = "NEMOCLAW_ENDPOINT"
_ENV_API_KEY = "NEMOCLAW_API_KEY"


class NemoClawClient:
    """HTTP client for a NemoClaw-compatible external specialist service.

    The client sends a task payload and returns the specialist's text response.
    All configuration is environment-driven for operator control.

    Supports three specialist types:
    - ``secure_coder``: security-aware code generation
    - ``security_review``: code security review and analysis
    - ``sandbox_analysis``: sandboxed code execution and analysis
    """

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        api_key: str | None = None,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
    ) -> None:
        self._endpoint = (
            endpoint or os.environ.get(_ENV_ENDPOINT, "")
        ).rstrip("/")
        self._api_key = api_key or os.environ.get(_ENV_API_KEY, "")
        self._timeout_s = timeout_s

    @property
    def is_configured(self) -> bool:
        """True if the endpoint is set (key may be optional for local deploys)."""
        return bool(self._endpoint)

    async def query(
        self,
        specialist_type: str,
        task_text: str,
        *,
        timeout_s: float | None = None,
    ) -> str:
        """Send a task to the external specialist and return the response text.

        Raises ``NemoClawError`` on transport or protocol failures.
        """
        if not self._endpoint:
            msg = (
                "NemoClaw endpoint not configured. "
                f"Set {_ENV_ENDPOINT} environment variable."
            )
            raise NemoClawError(msg)

        url = f"{self._endpoint}/v1/specialist/{specialist_type}"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload: dict[str, Any] = {"task": task_text}
        effective_timeout = timeout_s if timeout_s is not None else self._timeout_s

        try:
            async with httpx.AsyncClient(timeout=effective_timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            msg = f"NemoClaw specialist '{specialist_type}' timed out after {effective_timeout}s"
            raise NemoClawError(msg) from exc
        except httpx.HTTPError as exc:
            msg = f"NemoClaw transport error: {exc}"
            raise NemoClawError(msg) from exc

        if resp.status_code != 200:  # noqa: PLR2004
            msg = (
                f"NemoClaw specialist '{specialist_type}' returned "
                f"HTTP {resp.status_code}: {resp.text[:200]}"
            )
            raise NemoClawError(msg)

        # Parse response — expect {"result": "..."} or plain text.
        content_type = resp.headers.get("content-type", "")
        if "json" in content_type:
            try:
                data = resp.json()
                return str(data.get("result", data.get("output", str(data))))
            except Exception:  # noqa: BLE001
                return resp.text
        return resp.text


class NemoClawError(Exception):
    """Raised when a NemoClaw specialist call fails."""


# ---------------------------------------------------------------------------
# ServiceRouter handler factories
# ---------------------------------------------------------------------------

# Supported specialist types and their service names.
SPECIALIST_SERVICES: dict[str, str] = {
    "service:external:nemoclaw:secure_coder": "secure_coder",
    "service:external:nemoclaw:security_review": "security_review",
    "service:external:nemoclaw:sandbox_analysis": "sandbox_analysis",
}


def make_nemoclaw_handler(
    client: NemoClawClient,
    specialist_type: str,
) -> Any:  # noqa: ANN401
    """Create a deterministic ServiceRouter handler for a NemoClaw specialist.

    Returns an async callable matching the handler signature:
    ``async (query_text: str, ctx: dict) -> str``
    """

    async def handler(query_text: str, ctx: dict[str, Any]) -> str:
        try:
            result = await client.query(specialist_type, query_text)
            log.info(
                "nemoclaw.query_resolved",
                specialist=specialist_type,
                result_len=len(result),
                sender=ctx.get("sender_colony_id"),
            )
            return result
        except NemoClawError as exc:
            log.warning(
                "nemoclaw.query_failed",
                specialist=specialist_type,
                error=str(exc),
            )
            return f"Error: NemoClaw specialist '{specialist_type}' failed: {exc}"

    return handler
