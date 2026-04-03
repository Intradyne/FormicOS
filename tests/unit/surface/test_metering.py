"""Wave 75: Tests for surface/metering.py — billing aggregate, fee, chain hash."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from formicos.surface.metering import (
    aggregate_period,
    compute_chain_hash,
    compute_fee,
    current_period,
    format_billing_status,
    load_attestation_history,
    parse_period,
)


# ---------------------------------------------------------------------------
# Fee computation
# ---------------------------------------------------------------------------


class TestComputeFee:
    def test_zero_tokens(self) -> None:
        assert compute_fee(0) == 0.0

    def test_negative_tokens(self) -> None:
        assert compute_fee(-100) == 0.0

    def test_one_million(self) -> None:
        # 2.00 * sqrt(1) = 2.00
        assert compute_fee(1_000_000) == 2.00

    def test_four_million(self) -> None:
        # 2.00 * sqrt(4) = 4.00
        assert compute_fee(4_000_000) == 4.00

    def test_66_million(self) -> None:
        # 2.00 * sqrt(66) = 16.248...
        expected = round(2.00 * math.sqrt(66), 2)
        assert compute_fee(66_000_000) == expected

    def test_formula_matches_spec(self) -> None:
        """Fee formula: round(2.00 * sqrt(total_tokens / 1_000_000), 2)."""
        for tokens in [100_000, 500_000, 1_000_000, 10_000_000, 100_000_000]:
            expected = round(2.00 * math.sqrt(tokens / 1_000_000), 2)
            assert compute_fee(tokens) == expected


# ---------------------------------------------------------------------------
# Chain hash
# ---------------------------------------------------------------------------


class TestChainHash:
    def test_empty_events(self) -> None:
        """Empty event list produces a well-defined hash."""
        import hashlib
        expected = hashlib.sha256().hexdigest()
        assert compute_chain_hash([]) == expected

    def test_deterministic(self) -> None:
        events = [
            {"seq": 1, "input_tokens": 100, "output_tokens": 50},
            {"seq": 2, "input_tokens": 200, "output_tokens": 100},
        ]
        h1 = compute_chain_hash(events)
        h2 = compute_chain_hash(events)
        assert h1 == h2

    def test_order_independent_of_input_order(self) -> None:
        """Events are sorted by seq before hashing."""
        events_a = [
            {"seq": 2, "input_tokens": 200},
            {"seq": 1, "input_tokens": 100},
        ]
        events_b = [
            {"seq": 1, "input_tokens": 100},
            {"seq": 2, "input_tokens": 200},
        ]
        assert compute_chain_hash(events_a) == compute_chain_hash(events_b)

    def test_different_events_different_hash(self) -> None:
        h1 = compute_chain_hash([{"seq": 1, "input_tokens": 100}])
        h2 = compute_chain_hash([{"seq": 1, "input_tokens": 200}])
        assert h1 != h2


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _make_event(
    seq: int,
    input_tokens: int = 100,
    output_tokens: int = 50,
    reasoning_tokens: int = 10,
    cache_read_tokens: int = 20,
    cost: float = 0.01,
    model: str = "test-model",
    timestamp: str = "2026-03-15T12:00:00Z",
) -> Any:
    """Create a mock TokensConsumed event."""
    evt = type("MockEvent", (), {
        "seq": seq,
        "timestamp": timestamp,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cost": cost,
        "model": model,
        "agent_id": f"agent_{seq}",
    })()
    return evt


@pytest.mark.asyncio
class TestAggregatePeriod:
    async def test_includes_reasoning_tokens(self) -> None:
        """Total tokens = input + output + reasoning (not cache-read)."""
        store = AsyncMock()
        store.query = AsyncMock(return_value=[
            _make_event(1, input_tokens=100, output_tokens=50, reasoning_tokens=25, cache_read_tokens=10),
        ])
        start = datetime(2026, 3, 1, tzinfo=UTC)
        end = datetime(2026, 4, 1, tzinfo=UTC)
        agg = await aggregate_period(store, start, end)
        assert agg["total_tokens"] == 100 + 50 + 25  # NOT + 10
        assert agg["cache_read_tokens"] == 10
        assert agg["reasoning_tokens"] == 25

    async def test_cache_read_not_double_counted(self) -> None:
        """Cache-read tokens are informational only — not added to total."""
        store = AsyncMock()
        store.query = AsyncMock(return_value=[
            _make_event(1, input_tokens=1000, output_tokens=500, reasoning_tokens=0, cache_read_tokens=400),
        ])
        start = datetime(2026, 3, 1, tzinfo=UTC)
        end = datetime(2026, 4, 1, tzinfo=UTC)
        agg = await aggregate_period(store, start, end)
        assert agg["total_tokens"] == 1000 + 500 + 0
        assert agg["cache_read_tokens"] == 400

    async def test_by_model_breakdown(self) -> None:
        store = AsyncMock()
        store.query = AsyncMock(return_value=[
            _make_event(1, model="model-a", input_tokens=100, output_tokens=50),
            _make_event(2, model="model-b", input_tokens=200, output_tokens=100),
        ])
        start = datetime(2026, 3, 1, tzinfo=UTC)
        end = datetime(2026, 4, 1, tzinfo=UTC)
        agg = await aggregate_period(store, start, end)
        assert "model-a" in agg["by_model"]
        assert "model-b" in agg["by_model"]
        assert agg["by_model"]["model-a"]["input_tokens"] == 100
        assert agg["by_model"]["model-b"]["input_tokens"] == 200

    async def test_period_filtering(self) -> None:
        """Only events within the period are counted."""
        store = AsyncMock()
        store.query = AsyncMock(return_value=[
            _make_event(1, input_tokens=100, timestamp="2026-02-15T12:00:00Z"),  # Before
            _make_event(2, input_tokens=200, timestamp="2026-03-15T12:00:00Z"),  # In
            _make_event(3, input_tokens=300, timestamp="2026-04-15T12:00:00Z"),  # After
        ])
        start = datetime(2026, 3, 1, tzinfo=UTC)
        end = datetime(2026, 4, 1, tzinfo=UTC)
        agg = await aggregate_period(store, start, end)
        assert agg["event_count"] == 1
        assert agg["input_tokens"] == 200

    async def test_empty_store(self) -> None:
        store = AsyncMock()
        store.query = AsyncMock(return_value=[])
        start = datetime(2026, 3, 1, tzinfo=UTC)
        end = datetime(2026, 4, 1, tzinfo=UTC)
        agg = await aggregate_period(store, start, end)
        assert agg["total_tokens"] == 0
        assert agg["event_count"] == 0
        assert agg["computed_fee"] == 0.0

    async def test_chain_hash_deterministic(self) -> None:
        store = AsyncMock()
        events = [_make_event(i, input_tokens=i * 100) for i in range(1, 4)]
        store.query = AsyncMock(return_value=events)
        start = datetime(2026, 3, 1, tzinfo=UTC)
        end = datetime(2026, 4, 1, tzinfo=UTC)
        agg1 = await aggregate_period(store, start, end)
        store.query = AsyncMock(return_value=events)
        agg2 = await aggregate_period(store, start, end)
        assert agg1["chain_hash"] == agg2["chain_hash"]
        assert agg1["chain_hash"] != ""

    async def test_fee_matches_formula(self) -> None:
        store = AsyncMock()
        store.query = AsyncMock(return_value=[
            _make_event(1, input_tokens=500_000, output_tokens=300_000, reasoning_tokens=200_000),
        ])
        start = datetime(2026, 3, 1, tzinfo=UTC)
        end = datetime(2026, 4, 1, tzinfo=UTC)
        agg = await aggregate_period(store, start, end)
        assert agg["computed_fee"] == compute_fee(agg["total_tokens"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestParsePeriod:
    def test_normal(self) -> None:
        start, end = parse_period("2026-03")
        assert start == datetime(2026, 3, 1, tzinfo=UTC)
        assert end == datetime(2026, 4, 1, tzinfo=UTC)

    def test_december(self) -> None:
        start, end = parse_period("2026-12")
        assert start == datetime(2026, 12, 1, tzinfo=UTC)
        assert end == datetime(2027, 1, 1, tzinfo=UTC)


class TestCurrentPeriod:
    def test_returns_utc_datetimes(self) -> None:
        start, end = current_period()
        assert start.tzinfo is not None
        assert end.tzinfo is not None
        assert start < end


class TestFormatBillingStatus:
    def test_renders_readable(self) -> None:
        agg = {
            "period_start": "2026-03-01T00:00:00+00:00",
            "period_end": "2026-04-01T00:00:00+00:00",
            "input_tokens": 1000,
            "output_tokens": 500,
            "reasoning_tokens": 100,
            "cache_read_tokens": 200,
            "total_tokens": 1600,
            "total_cost": 0.05,
            "event_count": 5,
            "computed_fee": 0.08,
            "by_model": {},
        }
        output = format_billing_status(agg)
        assert "1,600" in output  # total tokens formatted
        assert "0.08" in output  # fee
        assert "Tier 1" in output  # free tier note


class TestLoadAttestationHistory:
    def test_empty_dir(self, tmp_path: Any) -> None:
        assert load_attestation_history(str(tmp_path)) == []

    def test_loads_files(self, tmp_path: Any) -> None:
        import json
        att_dir = tmp_path / ".formicos" / "billing" / "attestations"
        att_dir.mkdir(parents=True)
        att = {"version": 1, "total_tokens": 1000, "period_start": "2026-03"}
        (att_dir / "2026-03.json").write_text(json.dumps(att))
        result = load_attestation_history(str(tmp_path))
        assert len(result) == 1
        assert result[0]["total_tokens"] == 1000
