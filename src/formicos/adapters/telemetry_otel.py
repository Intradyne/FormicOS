"""Additive OpenTelemetry adapter for FormicOS (Wave 43, Pillar 3C).

Instruments the most valuable runtime seams with spans and metrics.
Activates only when ``opentelemetry-api`` is importable — the local/debug
JSONL path (telemetry_jsonl.py) remains usable even if OTel is not configured.

This adapter is **beside** JSONL, not a replacement. No OTel dependency is
required to run FormicOS locally.

Instrumented seams:
  - Event replay timing
  - LLM call duration and token usage
  - Colony lifecycle timing (spawn → complete/fail)
  - Knowledge retrieval latency

Usage:
    from formicos.adapters.telemetry_otel import OTelAdapter

    otel = OTelAdapter.create()  # returns no-op if opentelemetry not installed
    otel.record_llm_call(model, input_tokens, output_tokens, cost, duration_ms)
"""

from __future__ import annotations

import time as _time_mod
from typing import Any

import structlog

log = structlog.get_logger()

# Try to import opentelemetry. If unavailable, all methods become no-ops.
_otel_metrics: Any = None
_otel_trace: Any = None
_has_otel = False

try:
    from opentelemetry import metrics as _otel_metrics  # type: ignore[import-untyped]
    from opentelemetry import trace as _otel_trace  # type: ignore[import-untyped]

    _has_otel = True
except ImportError:
    pass


class OTelAdapter:
    """Lightweight OpenTelemetry instrumentation adapter.

    All public methods are safe to call even when OTel is not installed —
    they degrade to no-ops with zero overhead beyond a boolean check.
    """

    def __init__(self, tracer: Any, meter: Any, enabled: bool = True) -> None:  # noqa: ANN401
        self._tracer = tracer
        self._meter = meter
        self._enabled = enabled and _has_otel

        # Pre-create instruments if OTel is available
        if self._enabled and meter is not None:
            self._llm_duration = meter.create_histogram(
                "formicos.llm.duration_ms",
                description="LLM call duration in milliseconds",
                unit="ms",
            )
            self._llm_input_tokens = meter.create_counter(
                "formicos.llm.input_tokens",
                description="Total LLM input tokens consumed",
            )
            self._llm_output_tokens = meter.create_counter(
                "formicos.llm.output_tokens",
                description="Total LLM output tokens consumed",
            )
            self._llm_cost = meter.create_counter(
                "formicos.llm.cost_usd",
                description="Estimated LLM cost in USD",
                unit="usd",
            )
            self._colony_duration = meter.create_histogram(
                "formicos.colony.duration_ms",
                description="Colony lifecycle duration in milliseconds",
                unit="ms",
            )
            self._replay_duration = meter.create_histogram(
                "formicos.replay.duration_ms",
                description="Event replay duration in milliseconds",
                unit="ms",
            )
            self._retrieval_duration = meter.create_histogram(
                "formicos.retrieval.duration_ms",
                description="Knowledge retrieval latency in milliseconds",
                unit="ms",
            )
        else:
            self._llm_duration = None
            self._llm_input_tokens = None
            self._llm_output_tokens = None
            self._llm_cost = None
            self._colony_duration = None
            self._replay_duration = None
            self._retrieval_duration = None

    @classmethod
    def create(cls, service_name: str = "formicos") -> OTelAdapter:
        """Create an OTel adapter. Returns a no-op adapter if OTel is not installed."""
        if not _has_otel:
            log.debug("otel_adapter.disabled", reason="opentelemetry not installed")
            return cls(tracer=None, meter=None, enabled=False)

        tracer = _otel_trace.get_tracer(service_name)  # type: ignore[union-attr]
        meter = _otel_metrics.get_meter(service_name)  # type: ignore[union-attr]
        log.info("otel_adapter.enabled", service_name=service_name)
        return cls(tracer=tracer, meter=meter, enabled=True)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def record_llm_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        duration_ms: int,
    ) -> None:
        """Record an LLM call's metrics."""
        if not self._enabled:
            return
        attrs = {"model": model}
        if self._llm_duration is not None:
            self._llm_duration.record(duration_ms, attributes=attrs)
        if self._llm_input_tokens is not None:
            self._llm_input_tokens.add(input_tokens, attributes=attrs)
        if self._llm_output_tokens is not None:
            self._llm_output_tokens.add(output_tokens, attributes=attrs)
        if self._llm_cost is not None:
            self._llm_cost.add(cost, attributes=attrs)

    def record_colony_lifecycle(
        self,
        colony_id: str,
        workspace_id: str,
        duration_ms: int,
        status: str,
    ) -> None:
        """Record a colony's total lifecycle duration."""
        if not self._enabled or self._colony_duration is None:
            return
        self._colony_duration.record(duration_ms, attributes={
            "colony_id": colony_id,
            "workspace_id": workspace_id,
            "status": status,
        })

    def record_replay(self, event_count: int, duration_ms: int) -> None:
        """Record event replay timing."""
        if not self._enabled or self._replay_duration is None:
            return
        self._replay_duration.record(duration_ms, attributes={
            "event_count": event_count,
        })

    def record_retrieval(
        self, workspace_id: str, result_count: int, duration_ms: int,
    ) -> None:
        """Record knowledge retrieval latency."""
        if not self._enabled or self._retrieval_duration is None:
            return
        self._retrieval_duration.record(duration_ms, attributes={
            "workspace_id": workspace_id,
            "result_count": result_count,
        })

    def start_span(self, name: str, **attrs: Any) -> Any:  # noqa: ANN401
        """Start a trace span. Returns a context manager (or no-op)."""
        if not self._enabled or self._tracer is None:
            return _NoOpSpan()
        return self._tracer.start_as_current_span(name, attributes=attrs)

    def timer(self) -> _Timer:
        """Return a simple monotonic timer for measuring durations."""
        return _Timer()


class _NoOpSpan:
    """No-op context manager when OTel is not available."""

    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def set_attribute(self, key: str, value: Any) -> None:  # noqa: ANN401
        pass


class _Timer:
    """Simple monotonic timer for measuring operation durations."""

    def __init__(self) -> None:
        self._start = _time_mod.monotonic()

    def elapsed_ms(self) -> int:
        return int((_time_mod.monotonic() - self._start) * 1000)


class OTelSink:
    """Telemetry bus sink that bridges TelemetryEvent to OTelAdapter calls.

    Register via ``telemetry_bus.add_sink(OTelSink(otel_adapter))`` to
    forward operational telemetry to OpenTelemetry beside the JSONL sink.
    """

    def __init__(self, adapter: OTelAdapter) -> None:
        self._adapter = adapter

    async def __call__(self, event: Any) -> None:  # noqa: ANN401
        """Route a TelemetryEvent to the appropriate OTel recording method."""
        if not self._adapter.enabled:
            return
        etype = getattr(event, "event_type", "")
        payload = getattr(event, "payload", {})

        if etype == "llm_call":
            self._adapter.record_llm_call(
                model=str(payload.get("model", "")),
                input_tokens=int(payload.get("input_tokens", 0)),
                output_tokens=int(payload.get("output_tokens", 0)),
                cost=float(payload.get("cost", 0.0)),
                duration_ms=int(payload.get("duration_ms", 0)),
            )
        elif etype == "colony_lifecycle":
            self._adapter.record_colony_lifecycle(
                colony_id=str(getattr(event, "colony_id", "")),
                workspace_id=str(payload.get("workspace_id", "")),
                duration_ms=int(payload.get("duration_ms", 0)),
                status=str(payload.get("status", "")),
            )
        elif etype == "retrieval":
            self._adapter.record_retrieval(
                workspace_id=str(payload.get("workspace_id", "")),
                result_count=int(payload.get("result_count", 0)),
                duration_ms=int(payload.get("duration_ms", 0)),
            )


__all__ = ["OTelAdapter", "OTelSink"]
