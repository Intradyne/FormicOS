"""
FormicOS v0.12.10 -- Instrumentation Event Bus

Lightweight bounded-queue event bus following the FleetEventAggregator
pattern proven stable in v0.12.9.  Hooks across the system emit
``InstrumentationEvent`` objects; registered sinks (OTEL exporter,
Context Tree writer) consume them asynchronously.

STRICTURE-001: All I/O uses async/await.
STRICTURE-002: No blocking — overflow drops oldest, never blocks.
STRICTURE-003: Fully typed. No typing.Any.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, Field

logger = logging.getLogger("formicos.instrumentation.bus")

# Payload value type — covers every hook's data fields without typing.Any.
PayloadValue = str | int | float | bool | list[str]


class InstrumentationEvent(BaseModel):
    """Single telemetry event emitted by a hook."""

    event_type: str
    timestamp: float = Field(default_factory=time.time)
    colony_id: str = ""
    round_num: int = 0
    payload: dict[str, PayloadValue] = Field(default_factory=dict)


# Type alias for sink callables.
SinkCallable = Callable[[InstrumentationEvent], Awaitable[None]]

# Default bounded-queue capacity (matches spec: 10 000).
_DEFAULT_MAXSIZE = 10_000


class _EventBuffer:
    """Loop-agnostic bounded FIFO used before async queue startup."""

    def __init__(self, maxsize: int) -> None:
        self._maxsize = maxsize
        self._items: deque[InstrumentationEvent] = deque()

    def put_nowait(self, event: InstrumentationEvent) -> None:
        if len(self._items) >= self._maxsize:
            raise asyncio.QueueFull
        self._items.append(event)

    def get_nowait(self) -> InstrumentationEvent:
        if not self._items:
            raise asyncio.QueueEmpty
        return self._items.popleft()

    def qsize(self) -> int:
        return len(self._items)

    def empty(self) -> bool:
        return not self._items


class InstrumentationBus:
    """Bounded async event bus with fan-out to registered sinks.

    Follows the ``FleetEventAggregator`` overflow strategy:
    on ``QueueFull``, drop the oldest event and retry.
    """

    def __init__(self, maxsize: int = _DEFAULT_MAXSIZE) -> None:
        self._maxsize = maxsize
        self._queue = _EventBuffer(maxsize=maxsize)
        self._async_queue: asyncio.Queue[InstrumentationEvent] | None = None
        self._sinks: list[SinkCallable] = []
        self._task: asyncio.Task[None] | None = None
        self._running = False

    # ── Emit ────────────────────────────────────────────────────────

    def emit_nowait(self, event: InstrumentationEvent) -> None:
        """Non-blocking put.  Drops oldest event on overflow."""
        queue: _EventBuffer | asyncio.Queue[InstrumentationEvent]
        queue = self._async_queue if self._async_queue is not None else self._queue

        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Instrumentation event dropped (queue full after overflow)")

    async def emit(self, event: InstrumentationEvent) -> None:
        """Async emit — delegates to :meth:`emit_nowait`."""
        self.emit_nowait(event)

    # ── Sinks ───────────────────────────────────────────────────────

    def add_sink(self, sink: SinkCallable) -> None:
        """Register an async consumer for all events."""
        self._sinks.append(sink)

    # ── Lifecycle ───────────────────────────────────────────────────

    async def run(self) -> None:
        """Consumer loop: dequeue events and dispatch to all sinks.

        Intended to be wrapped in ``asyncio.create_task(bus.run())``.
        """
        self._running = True
        while self._running:
            queue = self._async_queue
            if queue is None:
                await asyncio.sleep(0.05)
                continue
            try:
                event = await asyncio.wait_for(
                    queue.get(), timeout=1.0,
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            await self._dispatch(event)

    async def start(self) -> None:
        """Start the consumer loop as a background task.

        Rebinds the internal queue to the current event loop when the
        singleton survives across loops (e.g. successive ``pytest-asyncio``
        function-scoped tests that each spin up a full server lifespan).
        Any events queued before ``start()`` are migrated to the new queue.
        """
        if self._task is not None:
            return
        new_q: asyncio.Queue[InstrumentationEvent] = asyncio.Queue(maxsize=self._maxsize)
        while not self._queue.empty():
            try:
                event = self._queue.get_nowait()
                new_q.put_nowait(event)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                break
        self._async_queue = new_q
        self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        """Drain remaining events, then cancel the consumer task."""
        self._running = False

        # Drain async queue first.
        if self._async_queue is not None:
            while not self._async_queue.empty():
                try:
                    event = self._async_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                await self._dispatch(event)

        # Drain pre-start buffer (supports stop() without start()).
        while not self._queue.empty():
            try:
                event = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            await self._dispatch(event)

        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._async_queue = None

    # ── Internal ────────────────────────────────────────────────────

    async def _dispatch(self, event: InstrumentationEvent) -> None:
        """Fan out *event* to every registered sink."""
        for sink in self._sinks:
            try:
                await sink(event)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Sink error dispatching %s: %s", event.event_type, exc,
                )


# ── Singleton ──────────────────────────────────────────────────────────

_bus: InstrumentationBus | None = None


def get_bus() -> InstrumentationBus:
    """Return the module-level singleton bus (lazy-created)."""
    global _bus  # noqa: PLW0603
    if _bus is None:
        _bus = InstrumentationBus()
    return _bus


def reset_bus() -> None:
    """Replace the singleton with a fresh instance (testing only)."""
    global _bus  # noqa: PLW0603
    _bus = None
