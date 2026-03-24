"""Bounded async telemetry event bus (Wave 17, Track A).

Operational telemetry events (routing decisions, token expenditure) flow
through this bus to registered sinks.  Events are NOT persisted in the
domain event store — they are debug/observability signals only.

The bus lives in ``engine/`` and imports only core types.
Sinks live in ``adapters/``.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from collections.abc import Callable, Coroutine
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field

log = structlog.get_logger()

_FrozenConfig = ConfigDict(frozen=True)


class TelemetryEvent(BaseModel):
    """Single operational telemetry event."""

    model_config = _FrozenConfig

    event_type: str
    timestamp: float = Field(default_factory=time.time)
    colony_id: str = ""
    round_num: int = 0
    payload: dict[str, str | int | float | bool] = Field(default_factory=dict)


# Type alias for async sink callables
TelemetrySink = Callable[[TelemetryEvent], Coroutine[Any, Any, None]]

_QUEUE_CAPACITY = 10_000


class TelemetryBus:
    """Bounded async event bus for operational telemetry.

    - Pre-start: events queued in a thread-safe deque (never blocks).
    - Post-start: events placed into an asyncio.Queue and consumed by a
      background task that fans out to registered sinks.
    - Overflow: oldest events dropped silently (never blocks producers).
    - Sink failures: caught, logged, never propagated.
    """

    def __init__(self, capacity: int = _QUEUE_CAPACITY) -> None:
        self._capacity = capacity
        self._sinks: list[TelemetrySink] = []
        self._started = False
        # Pre-start buffer (thread-safe, bounded)
        self._buffer: deque[TelemetryEvent] = deque(maxlen=capacity)
        self._queue: asyncio.Queue[TelemetryEvent] | None = None
        self._task: asyncio.Task[None] | None = None

    def add_sink(self, sink: TelemetrySink) -> None:
        """Register an async sink callable."""
        self._sinks.append(sink)

    def emit_nowait(self, event: TelemetryEvent) -> None:
        """Enqueue a telemetry event without blocking.

        Safe to call from any context (sync or async).  If the bus has
        not started yet, events are buffered.  On overflow, oldest events
        are dropped.
        """
        if self._queue is not None:
            try:
                self._queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest to make room
                with contextlib.suppress(asyncio.QueueEmpty):
                    self._queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    self._queue.put_nowait(event)
        else:
            self._buffer.append(event)

    async def start(self) -> None:
        """Start the background consumer task.

        Drains the pre-start buffer into the async queue, then launches
        the fan-out loop.
        """
        if self._started:
            return
        self._queue = asyncio.Queue(maxsize=self._capacity)
        # Drain pre-start buffer
        while self._buffer:
            evt = self._buffer.popleft()
            try:
                self._queue.put_nowait(evt)
            except asyncio.QueueFull:
                break
        self._started = True
        self._task = asyncio.create_task(self._consumer(), name="telemetry-bus")
        log.info("telemetry_bus.started", sinks=len(self._sinks))

    async def stop(self) -> None:
        """Stop the background consumer and drain remaining events."""
        if not self._started or self._task is None:
            return
        self._started = False
        # Signal consumer to exit
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        # Best-effort drain
        if self._queue is not None:
            while not self._queue.empty():
                try:
                    evt = self._queue.get_nowait()
                    await self._fan_out(evt)
                except asyncio.QueueEmpty:
                    break
        log.info("telemetry_bus.stopped")

    async def _consumer(self) -> None:
        """Background loop: dequeue events and fan out to sinks."""
        assert self._queue is not None
        while self._started:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._fan_out(event)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def _fan_out(self, event: TelemetryEvent) -> None:
        """Deliver event to all registered sinks."""
        for sink in self._sinks:
            try:
                await sink(event)
            except Exception:  # noqa: BLE001
                log.debug(
                    "telemetry_bus.sink_error",
                    event_type=event.event_type,
                )


# Module-level singleton
_bus: TelemetryBus | None = None


def get_telemetry_bus() -> TelemetryBus:
    """Return the module-level telemetry bus singleton."""
    global _bus  # noqa: PLW0603
    if _bus is None:
        _bus = TelemetryBus()
    return _bus


def reset_telemetry_bus() -> None:
    """Reset the singleton (for tests)."""
    global _bus  # noqa: PLW0603
    _bus = None


__all__ = [
    "TelemetryBus",
    "TelemetryEvent",
    "TelemetrySink",
    "get_telemetry_bus",
    "reset_telemetry_bus",
]
