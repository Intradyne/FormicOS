"""Service colony routing — tracks active services and request/response matching.

Implements algorithms.md §7 — service colonies retain their tools, skills,
and knowledge after completion.  Other colonies (or external agents via
A2A/MCP) query them through a message-injection + response-matching protocol.

Message convention
------------------
Query:    ``[Service Query: <request_id>]\n<query_text>``
Response: ``[Service Response: <request_id>]\n<response_text>``

Stream C owns this file.
"""

from __future__ import annotations

import asyncio
import re
import time as _time_mod
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import structlog

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_QUERY_TAG = "[Service Query: {}]"
_RESPONSE_RE = re.compile(r"\[Service Response:\s*([^\]]+)\]")
_DEFAULT_TIMEOUT_S = 30.0
InjectFn = Callable[[str, str], Awaitable[None]]


# ---------------------------------------------------------------------------
# ServiceRouter
# ---------------------------------------------------------------------------


class ServiceRouter:
    """Registry of active service colonies with async request/response matching.

    Lifecycle
    ---------
    1. ``register()`` — called when a completed colony is activated as a service.
    2. ``unregister()`` — called when the operator deactivates or kills a service.
    3. ``query()`` — sends a query to a service colony and waits for a response.
    4. ``resolve_response()`` — called by the runner when a service colony's
       agent output contains a ``[Service Response: <id>]`` block.

    Thread-safety: all public methods are safe for concurrent ``asyncio`` use.
    The router is instantiated once per ``Runtime`` and shared across colonies.
    """

    def __init__(self, inject_fn: InjectFn | None = None) -> None:
        # service_type -> colony_id
        self._registry: dict[str, str] = {}
        # service_type -> async callable (Wave 29: deterministic handlers)
        self._handlers: dict[str, Callable[..., Any]] = {}
        # request_id -> asyncio.Event (set when response arrives)
        self._waiters: dict[str, asyncio.Event] = {}
        # request_id -> response text
        self._responses: dict[str, str] = {}
        self._inject_fn = inject_fn
        # Wave 29: event emission callback (injected from surface)
        self._emit_fn: Callable[..., Any] | None = None

    # -- Registration -------------------------------------------------------

    def register(self, service_type: str, colony_id: str) -> None:
        """Register a colony as an active service of the given type."""
        prev = self._registry.get(service_type)
        if prev and prev != colony_id:
            log.warning(
                "service_router.replacing",
                service_type=service_type,
                old_colony=prev,
                new_colony=colony_id,
            )
        self._registry[service_type] = colony_id
        log.info(
            "service_router.registered",
            service_type=service_type,
            colony_id=colony_id,
        )

    def unregister(self, service_type: str) -> None:
        """Remove a service type from the registry."""
        removed = self._registry.pop(service_type, None)
        if removed:
            log.info(
                "service_router.unregistered",
                service_type=service_type,
                colony_id=removed,
            )

    def lookup(self, service_type: str) -> str | None:
        """Return the colony_id for a service type, or None."""
        return self._registry.get(service_type)

    def set_inject_fn(self, inject_fn: InjectFn | None) -> None:
        """Update the default colony-message injection function."""
        self._inject_fn = inject_fn

    def register_handler(
        self,
        service_type: str,
        handler: Callable[[str, dict[str, Any]], Awaitable[str]],
    ) -> None:
        """Register a deterministic service handler (Wave 29).

        Handler signature: async (query_text: str, ctx: dict) -> str
        Takes precedence over colony-based registration for the same service_type.
        """
        self._handlers[service_type] = handler
        log.info("service_router.handler_registered", service_type=service_type)

    def set_emit_fn(self, emit_fn: Callable[..., Any] | None) -> None:
        """Set the event emission callback. Called from app.py at startup."""
        self._emit_fn = emit_fn

    @property
    def active_services(self) -> dict[str, str]:
        """Return a snapshot of {service_type: colony_id}."""
        return dict(self._registry)

    # -- Query / Response ---------------------------------------------------

    def format_query(self, request_id: str, query_text: str) -> str:
        """Format a query message for injection into a service colony."""
        return f"{_QUERY_TAG.format(request_id)}\n{query_text}"

    async def query(
        self,
        service_type: str,
        query_text: str,
        *,
        sender_colony_id: str | None = None,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        inject_fn: Any = None,  # noqa: ANN401
    ) -> str:
        """Send a query to a service and wait for its response.

        Checks deterministic handlers first (Wave 29), then falls back to
        colony-based dispatch.
        """
        # --- Wave 29: deterministic handler bypass ---
        if service_type in self._handlers:
            handler = self._handlers[service_type]
            request_id = self._make_request_id(service_type)
            t0 = _time_mod.perf_counter()

            await self._emit_service_query_sent(
                request_id=request_id,
                service_type=service_type,
                target_id=service_type,
                sender_colony_id=sender_colony_id,
                query_preview=query_text[:200],
            )

            result = await handler(query_text, {
                "sender_colony_id": sender_colony_id,
            })
            latency_ms = (_time_mod.perf_counter() - t0) * 1000

            await self._emit_service_query_resolved(
                request_id=request_id,
                service_type=service_type,
                source_id=service_type,
                response_preview=result[:200],
                latency_ms=latency_ms,
            )

            log.info(
                "service_router.deterministic_resolved",
                request_id=request_id,
                service_type=service_type,
                latency_ms=round(latency_ms, 2),
            )
            return result

        # --- Existing colony-based dispatch ---
        colony_id = self._registry.get(service_type)
        if colony_id is None:
            msg = f"No {service_type} colony is running"
            raise ValueError(msg)

        request_id = self._make_request_id(colony_id)
        event = asyncio.Event()
        self._waiters[request_id] = event

        # Format and inject the query message
        formatted = self.format_query(request_id, query_text)

        # Emit ServiceQuerySent (Wave 29: was never emitted before)
        await self._emit_service_query_sent(
            request_id=request_id,
            service_type=service_type,
            target_id=colony_id,
            sender_colony_id=sender_colony_id,
            query_preview=query_text[:200],
        )

        effective_inject_fn = inject_fn or self._inject_fn
        if effective_inject_fn is None:
            msg = "Service router has no colony injection function configured"
            raise RuntimeError(msg)
        await effective_inject_fn(colony_id, formatted)

        # Wait for the response
        t0 = _time_mod.perf_counter()
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout_s)
        except TimeoutError:
            self._cleanup_request(request_id)
            log.warning(
                "service_router.query_timeout",
                request_id=request_id,
                service_type=service_type,
                timeout_s=timeout_s,
            )
            msg = f"Service query timed out after {timeout_s}s"
            raise TimeoutError(msg) from None

        latency_ms = (_time_mod.perf_counter() - t0) * 1000
        response = self._responses.pop(request_id, "")
        self._cleanup_request(request_id)

        # Emit ServiceQueryResolved (Wave 29: was never emitted before)
        await self._emit_service_query_resolved(
            request_id=request_id,
            service_type=service_type,
            source_id=colony_id,
            response_preview=response[:200],
            latency_ms=latency_ms,
        )

        log.info(
            "service_router.query_resolved",
            request_id=request_id,
            service_type=service_type,
            latency_ms=round(latency_ms, 2),
            response_len=len(response),
        )

        return response

    def resolve_response(self, request_id: str, response_text: str) -> bool:
        """Resolve a pending query with the service colony's response.

        Called by the runner when agent output contains a
        ``[Service Response: <request_id>]`` block.

        Returns True if the request was pending, False otherwise.
        """
        event = self._waiters.get(request_id)
        if event is None:
            log.warning(
                "service_router.unmatched_response",
                request_id=request_id,
            )
            return False

        self._responses[request_id] = response_text
        event.set()
        return True

    # -- Response detection -------------------------------------------------

    @staticmethod
    def extract_response(agent_output: str) -> tuple[str, str] | None:
        """Parse a ``[Service Response: <id>]`` block from agent output.

        Returns ``(request_id, response_text)`` or ``None`` if no match.
        """
        match = _RESPONSE_RE.search(agent_output)
        if match is None:
            return None
        request_id = match.group(1).strip()
        # Everything after the tag line is the response body
        rest = agent_output[match.end() :].strip()
        return request_id, rest

    # -- Event emission helpers (Wave 29) ------------------------------------

    async def _emit_service_query_sent(
        self,
        *,
        request_id: str,
        service_type: str,
        target_id: str,
        sender_colony_id: str | None,
        query_preview: str,
    ) -> None:
        if self._emit_fn is None:
            return
        from formicos.core.events import ServiceQuerySent  # noqa: PLC0415

        await self._emit_fn(ServiceQuerySent(
            seq=0,
            timestamp=datetime.now(UTC),
            address=f"service/{service_type}",
            request_id=request_id,
            service_type=service_type,
            target_colony_id=target_id,
            sender_colony_id=sender_colony_id,
            query_preview=query_preview,
        ))

    async def _emit_service_query_resolved(
        self,
        *,
        request_id: str,
        service_type: str,
        source_id: str,
        response_preview: str,
        latency_ms: float,
    ) -> None:
        if self._emit_fn is None:
            return
        from formicos.core.events import ServiceQueryResolved  # noqa: PLC0415

        await self._emit_fn(ServiceQueryResolved(
            seq=0,
            timestamp=datetime.now(UTC),
            address=f"service/{service_type}",
            request_id=request_id,
            service_type=service_type,
            source_colony_id=source_id,
            response_preview=response_preview,
            latency_ms=latency_ms,
            artifact_count=0,
        ))

    # -- Internal -----------------------------------------------------------

    @staticmethod
    def _make_request_id(colony_id: str) -> str:
        ts = int(_time_mod.time() * 1000)
        return f"svc-{colony_id[-8:]}-{ts}"

    def _cleanup_request(self, request_id: str) -> None:
        self._waiters.pop(request_id, None)
        self._responses.pop(request_id, None)
