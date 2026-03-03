"""
Tests for FormicOS v0.7.3 Circuit Breaker (model_registry.py).

Covers:
- CLOSED state allows probes
- CLOSED → OPEN after failure_threshold failures
- OPEN blocks probes (fail-fast)
- OPEN → HALF_OPEN after cooldown_seconds elapse
- HALF_OPEN allows single probe
- HALF_OPEN → CLOSED on success
- HALF_OPEN → OPEN on failure
- record_success resets failure count and state
- Injectable _time_func works correctly
"""

from __future__ import annotations


from src.model_registry import CircuitBreaker, CircuitState


class FakeClock:
    """Deterministic clock for circuit breaker testing."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


# ── State transitions ──────────────────────────────────────────────────


def test_closed_allows_probe():
    cb = CircuitBreaker()
    assert cb.state == CircuitState.CLOSED
    assert cb.should_probe() is True


def test_closed_to_open_after_threshold():
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=3, _time_func=clock)

    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    cb.record_failure()
    assert cb.state == CircuitState.OPEN


def test_open_blocks_probe():
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0, _time_func=clock)

    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.should_probe() is False


def test_open_to_half_open_after_cooldown():
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0, _time_func=clock)

    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    clock.advance(59)
    assert cb.should_probe() is False
    assert cb.state == CircuitState.OPEN

    clock.advance(2)  # now at 61s
    assert cb.should_probe() is True
    assert cb.state == CircuitState.HALF_OPEN


def test_half_open_allows_probe():
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=10.0, _time_func=clock)

    cb.record_failure()
    clock.advance(11)
    cb.should_probe()  # transitions to HALF_OPEN
    assert cb.state == CircuitState.HALF_OPEN
    assert cb.should_probe() is True


def test_half_open_to_closed_on_success():
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=10.0, _time_func=clock)

    cb.record_failure()
    clock.advance(11)
    cb.should_probe()
    assert cb.state == CircuitState.HALF_OPEN

    cb.record_success(latency_ms=42.0)
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0
    assert cb.last_latency_ms == 42.0


def test_half_open_to_open_on_failure():
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=10.0, _time_func=clock)

    cb.record_failure()
    clock.advance(11)
    cb.should_probe()
    assert cb.state == CircuitState.HALF_OPEN

    cb.record_failure()
    assert cb.state == CircuitState.OPEN


def test_record_success_resets_state():
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=3, _time_func=clock)

    cb.record_failure()
    cb.record_failure()
    assert cb.failure_count == 2
    assert cb.state == CircuitState.CLOSED

    cb.record_success(latency_ms=10.0)
    assert cb.failure_count == 0
    assert cb.state == CircuitState.CLOSED
    assert cb.last_healthy is True


def test_failure_tracks_timestamp():
    clock = FakeClock(start=100.0)
    cb = CircuitBreaker(failure_threshold=3, _time_func=clock)

    clock.advance(5.0)
    cb.record_failure()
    assert cb.last_failure_at == 105.0
    assert cb.last_healthy is False


def test_full_cycle():
    """CLOSED → OPEN → HALF_OPEN → CLOSED full cycle."""
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=30.0, _time_func=clock)

    # CLOSED → OPEN
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # Wait for cooldown → HALF_OPEN
    clock.advance(31)
    assert cb.should_probe() is True
    assert cb.state == CircuitState.HALF_OPEN

    # Success → CLOSED
    cb.record_success(latency_ms=15.0)
    assert cb.state == CircuitState.CLOSED
    assert cb.should_probe() is True
