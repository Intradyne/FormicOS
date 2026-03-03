"""
FormicOS v0.7.4 -- Webhook Dispatcher

Standalone async httpx dispatcher for colony lifecycle events.
Exponential backoff with jitter, configurable max_retries, in-memory
delivery log capped at 500 entries.

Integration:
  - Created in server.py lifespan, stored on app.state.webhook_dispatcher
  - Orchestrator fires dispatch() at post-colony completion
  - GET /api/v1/webhooks/logs exposes delivery records
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger("formicos.webhook")

_DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_MAX_LOG_ENTRIES = 500


class WebhookDispatcher:
    """Async webhook delivery with retries and logging."""

    def __init__(
        self,
        max_retries: int = 5,
        timeout: httpx.Timeout | None = None,
        signing_secret: str | None = None,
    ) -> None:
        self._max_retries = max_retries
        self._timeout = timeout or _DEFAULT_TIMEOUT
        self._delivery_log: list[dict[str, Any]] = []
        self._client: httpx.AsyncClient | None = None
        self._signing_secret: str | None = signing_secret

    async def start(self) -> None:
        """Create the shared httpx client.  Call in lifespan startup."""
        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def stop(self) -> None:
        """Close the shared httpx client.  Call in lifespan shutdown."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def dispatch(
        self,
        url: str,
        payload: dict[str, Any],
        colony_id: str = "",
    ) -> bool:
        """Send webhook with exponential backoff.

        Returns True on successful delivery (2xx), False if all retries
        exhausted.
        """
        if self._client is None:
            logger.error("WebhookDispatcher not started — call start() first")
            return False

        delivery_id = str(uuid.uuid4())
        payload_bytes = json.dumps(payload, default=str).encode()

        # Build headers — always JSON, optionally HMAC-signed
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._signing_secret:
            sig = hmac.new(
                self._signing_secret.encode(),
                payload_bytes,
                hashlib.sha256,
            ).hexdigest()
            headers["X-FormicOS-Signature"] = f"sha256={sig}"

        record: dict[str, Any] = {
            "delivery_id": delivery_id,
            "colony_id": colony_id,
            "url": url,
            "payload_type": payload.get("type", "unknown"),
            "payload_size_bytes": len(payload_bytes),
            "payload": payload,
            "signature_sent": self._signing_secret is not None,
            "attempts": 0,
            "status": "pending",
            "status_code": None,
            "last_error": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        for attempt in range(self._max_retries):
            record["attempts"] = attempt + 1
            try:
                resp = await self._client.post(url, content=payload_bytes, headers=headers)
                record["status_code"] = resp.status_code
                if resp.status_code < 300:
                    record["status"] = "delivered"
                    self._append_log(record)
                    logger.info(
                        "Webhook delivered to %s (colony=%s, attempt=%d)",
                        url, colony_id, attempt + 1,
                    )
                    return True
            except Exception as exc:
                record["last_error"] = str(exc)
                record["status_code"] = "timeout"

            # Exponential backoff with jitter
            delay = min(2 ** attempt + (time.monotonic() % 1), 30)
            await asyncio.sleep(delay)

        record["status"] = "failed"
        self._append_log(record)
        logger.error(
            "Webhook exhausted %d retries for %s (colony=%s)",
            self._max_retries, url, colony_id,
        )
        return False

    def get_logs(
        self,
        colony_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return delivery records, optionally filtered by colony_id."""
        if colony_id:
            return [r for r in self._delivery_log if r.get("colony_id") == colony_id]
        return list(self._delivery_log)

    def _append_log(self, record: dict[str, Any]) -> None:
        """Append a delivery record, capping at _MAX_LOG_ENTRIES."""
        self._delivery_log.append(record)
        if len(self._delivery_log) > _MAX_LOG_ENTRIES:
            self._delivery_log = self._delivery_log[-_MAX_LOG_ENTRIES:]
