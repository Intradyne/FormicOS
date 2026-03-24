"""Federation transport via A2A DataPart protocol (Wave 33 C8, adapter layer).

Imports from core only (VectorClock). Surface-layer FederationManager
owns the business logic; this adapter handles serialization and HTTP.
"""

from __future__ import annotations

from typing import Any

from formicos.core.vector_clock import VectorClock


class FederationTransport:
    """Abstract transport for federation events.

    Concrete implementations handle the actual HTTP/A2A communication.
    """

    async def send_events(
        self, endpoint: str, events: list[dict[str, Any]],
    ) -> None:
        """Send CRDT events to a remote peer."""
        raise NotImplementedError

    async def receive_events(
        self, endpoint: str, since: VectorClock,
    ) -> list[dict[str, Any]]:
        """Receive CRDT events from a remote peer since given clock."""
        raise NotImplementedError

    async def send_feedback(
        self, endpoint: str, entry_id: str, success: bool,
    ) -> None:
        """Send validation feedback to a remote peer."""
        raise NotImplementedError


class A2ADataPartTransport(FederationTransport):
    """Concrete transport using A2A DataPart protocol over httpx."""

    def __init__(self, *, timeout: float = 30.0) -> None:
        self._timeout = timeout

    async def send_events(
        self, endpoint: str, events: list[dict[str, Any]],
    ) -> None:
        """POST serialized CRDT events to peer's A2A endpoint as DataPart artifacts."""
        import httpx  # noqa: PLC0415

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            await client.post(
                f"{endpoint}/federation/events",
                json={"events": events},
            )

    async def receive_events(
        self, endpoint: str, since: VectorClock,
    ) -> list[dict[str, Any]]:
        """GET CRDT events from peer since given vector clock."""
        import httpx  # noqa: PLC0415

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{endpoint}/federation/pull",
                json={"since": since.clock},
            )
            data = resp.json()
            return data.get("events", [])  # type: ignore[no-any-return]

    async def send_feedback(
        self, endpoint: str, entry_id: str, success: bool,
    ) -> None:
        """POST validation feedback to peer."""
        import httpx  # noqa: PLC0415

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            await client.post(
                f"{endpoint}/federation/feedback",
                json={"entry_id": entry_id, "success": success},
            )


__all__ = ["A2ADataPartTransport", "FederationTransport"]
