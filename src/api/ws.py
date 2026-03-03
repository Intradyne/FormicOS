"""
FormicOS v0.7.9 -- WebSocket Connection Managers

Extracted from server.py.  Two managers:

- ConnectionManager: Legacy broadcast-to-all WS manager
- ConnectionManagerV1: Per-colony subscription model for V1 events
"""

from __future__ import annotations

from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts events."""

    def __init__(self) -> None:
        self.active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws)

    async def broadcast(self, message: dict) -> None:
        for ws in list(self.active):
            try:
                await ws.send_json(message)
            except Exception:
                self.active.discard(ws)


class ConnectionManagerV1:
    """WS connection manager with per-colony subscription."""

    def __init__(self) -> None:
        self.connections: dict[WebSocket, set[str | None]] = {}

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.connections[ws] = set()

    def disconnect(self, ws: WebSocket) -> None:
        self.connections.pop(ws, None)

    def subscribe(self, ws: WebSocket, colony_id: str | None) -> None:
        if ws in self.connections:
            self.connections[ws].add(colony_id)

    def unsubscribe(self, ws: WebSocket, colony_id: str | None) -> None:
        if ws in self.connections:
            self.connections[ws].discard(colony_id)

    async def emit(self, event: dict[str, Any]) -> None:
        """Send event to clients subscribed to the event's colony_id."""
        target_colony = event.get("colony_id")
        for ws, subs in list(self.connections.items()):
            # Send if subscribed to this colony or subscribed to None (all)
            if target_colony in subs or None in subs:
                try:
                    await ws.send_json(event)
                except Exception:
                    self.connections.pop(ws, None)
