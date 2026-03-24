"""
FormicOS Alpha — Telemetry Event Bus

Ported from pre-alpha v0.12.10 (src/instrumentation/bus.py, 180 LOC).
Adapted for the alpha's hexagonal architecture (engine layer).

Lightweight bounded-queue async event bus for operational metrics.
Separates telemetry (token usage, routing decisions, tool calls, skill
retrieval) from domain events (ColonySpawned, RoundCompleted, etc.).

Key design decisions from the prototype's v0.12.20 "Close the Loops":
  - Bounded FIFO: 10K capacity, overflow drops oldest, never blocks
  - Pre-start buffering: events emitted before async loop starts are
    queued in a thread-safe deque, migrated on start()
  - Fan-out: registered sinks receive every event, failures isolated
  - Non-blocking emit: safe to call from any synchronous context

Layer: engine/ (imports only core types).
Sinks go in adapters/ (JSONL file sink, Context Tree sink).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, Field

log = logging.getLogger("formicos.engine.telemetry_bus")

# Payload value type — covers every hook's data fields.
PayloadValue = str | int | float | bool | list[str]


class TelemetryEvent(BaseModel):
    """Single telemetry event emitted by a hook."""
    event_type: str
    timestamp: float = Field(default_factory=time.time)
    colony_id: str = ""
    round_num: int = 0
    payload: dict[str, PayloadValue] = Field(default_factory=dict)


SinkCallable = Callable[[TelemetryEvent], Awaitable[None]]

_DEFAULT_MAXSIZE = 10_000


class _EventBuffer:
    """Loop-agnostic bounded FIFO used before async queue startup."""

    def __init__(self, maxsize: int) -> None:
        self._maxsize = maxsize
        self._items: deque[TelemetryEvent] = deque()

    def put_nowait(self, event: TelemetryEvent) -> None:
        if len(self._items) >= self._maxsize:
            raise asyncio.QueueFull
        self._items.append(event)

    def get_nowait(self) -> TelemetryEvent:
        if not self._items:
            raise asyncio.QueueEmpty
        return self._items.popleft()

    def qsize(self) -> int:
        return len(self._items)

    def empty(self) -> bool:
        return not self._items


class TelemetryBus:
    """Bounded async event bus with fan-out to registered sinks.

    Overflow strategy: drop oldest event and retry (never blocks).
    """

    def __init__(self, maxsize: int = _DEFAULT_MAXSIZE) -> None:
        self._maxsize = maxsize
        self._queue = _EventBuffer(maxsize=maxsize)
        self._async_queue: asyncio.Queue[TelemetryEvent] | None = None
        self._sinks: list[SinkCallable] = []
        self._task: asyncio.Task[None] | None = None
        self._running = False

    # ── Emit ────────────────────────────────────────────────────────

    def emit_nowait(self, event: TelemetryEvent) -> None:
        """Non-blocking put. Drops oldest event on overflow."""
        queue: _EventBuffer | asyncio.Queue[TelemetryEvent]
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
                log.warning("telemetry_event_dropped")

    async def emit(self, event: TelemetryEvent) -> None:
        """Async emit — delegates to emit_nowait."""
        self.emit_nowait(event)

    # ── Sinks ───────────────────────────────────────────────────────

    def add_sink(self, sink: SinkCallable) -> None:
        """Register an async consumer for all events."""
        self._sinks.append(sink)

    # ── Lifecycle ───────────────────────────────────────────────────

    async def run(self) -> None:
        """Consumer loop: dequeue events and dispatch to all sinks."""
        self._running = True
        while self._running:
            queue = self._async_queue
            if queue is None:
                await asyncio.sleep(0.05)
                continue
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            await self._dispatch(event)

    async def start(self) -> None:
        """Start the consumer loop as a background task.

        Migrates any pre-start buffered events to the async queue.
        """
        if self._task is not None:
            return
        new_q: asyncio.Queue[TelemetryEvent] = asyncio.Queue(maxsize=self._maxsize)
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
        if self._async_queue is not None:
            while not self._async_queue.empty():
                try:
                    event = self._async_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                await self._dispatch(event)
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

    async def _dispatch(self, event: TelemetryEvent) -> None:
        """Fan out event to every registered sink."""
        for sink in self._sinks:
            try:
                await sink(event)
            except Exception as exc:
                log.warning("telemetry_sink_error", event_type=event.event_type, error=str(exc))


# ── Singleton ──────────────────────────────────────────────────────────

_bus: TelemetryBus | None = None


def get_telemetry_bus() -> TelemetryBus:
    """Return the module-level singleton bus (lazy-created)."""
    global _bus
    if _bus is None:
        _bus = TelemetryBus()
    return _bus


def reset_telemetry_bus() -> None:
    """Replace the singleton with a fresh instance (testing only)."""
    global _bus
    _bus = None


# ── Typed Emit Helpers ─────────────────────────────────────────────────
#
# Call these from anywhere in the codebase. They construct a TelemetryEvent
# and emit it non-blocking via the singleton bus.

def emit_routing_decision(
    colony_id: str,
    round_num: int,
    agent_id: str,
    caste: str,
    routed_model: str,
    reason: str,
) -> None:
    """Log a compute routing decision."""
    get_telemetry_bus().emit_nowait(TelemetryEvent(
        event_type="routing_decision",
        colony_id=colony_id,
        round_num=round_num,
        payload={
            "agent_id": agent_id,
            "caste": caste,
            "routed_model": routed_model,
            "reason": reason,
        },
    ))


def emit_token_expenditure(
    colony_id: str,
    round_num: int,
    agent_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
) -> None:
    """Log token consumption for a single LLM call."""
    get_telemetry_bus().emit_nowait(TelemetryEvent(
        event_type="token_expenditure",
        colony_id=colony_id,
        round_num=round_num,
        payload={
            "agent_id": agent_id,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
        },
    ))


def emit_tool_call(
    colony_id: str,
    round_num: int,
    agent_id: str,
    tool_name: str,
    permitted: bool,
    denial_reason: str = "",
) -> None:
    """Log a tool call attempt (permitted or denied)."""
    get_telemetry_bus().emit_nowait(TelemetryEvent(
        event_type="tool_call",
        colony_id=colony_id,
        round_num=round_num,
        payload={
            "agent_id": agent_id,
            "tool_name": tool_name,
            "permitted": permitted,
            "denial_reason": denial_reason,
        },
    ))


def emit_skill_retrieval(
    colony_id: str,
    round_num: int,
    agent_id: str,
    query: str,
    hits: int,
    top_score: float,
) -> None:
    """Log a skill bank retrieval attempt."""
    get_telemetry_bus().emit_nowait(TelemetryEvent(
        event_type="skill_retrieval",
        colony_id=colony_id,
        round_num=round_num,
        payload={
            "agent_id": agent_id,
            "query": query,
            "hits": hits,
            "top_score": top_score,
        },
    ))
