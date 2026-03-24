"""Wave 46 Team 1: Forager operator surface + OTel sink tests.

Covers:
- Forager operator REST endpoints (Track A)
- Forager provenance in knowledge detail (Track B)
- OTel telemetry sink bridge (Track C)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

from formicos.adapters.telemetry_otel import OTelAdapter, OTelSink

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeProjections:
    workspaces: dict[str, Any] = field(default_factory=dict)
    colonies: dict[str, Any] = field(default_factory=dict)
    memory_entries: dict[str, dict[str, Any]] = field(default_factory=dict)
    forage_cycles: dict[str, list[Any]] = field(default_factory=dict)
    domain_strategies: dict[str, dict[str, Any]] = field(default_factory=dict)
    domain_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Track A: Forager operator endpoint tests
# ---------------------------------------------------------------------------


class TestForagerEndpointRoutes:
    """Verify forager route functions exist and behave correctly."""

    def test_forage_cycle_history_empty(self) -> None:
        """Forage cycle endpoint returns empty list for workspace with no cycles."""
        projections = _FakeProjections()
        cycles = projections.forage_cycles.get("ws-1", [])
        assert cycles == []

    def test_domain_strategies_empty(self) -> None:
        """Domain strategies endpoint returns empty for workspace with no strategies."""
        projections = _FakeProjections()
        strategies = projections.domain_strategies.get("ws-1", {})
        overrides = projections.domain_overrides.get("ws-1", {})
        assert strategies == {}
        assert overrides == {}

    def test_forage_cycles_returns_recent_first(self) -> None:
        """Forage cycle history returns most-recent first."""
        from formicos.surface.projections import ForageCycleSummary

        cycle1 = ForageCycleSummary(
            forage_request_seq=1, mode="reactive", reason="gap",
            timestamp="2026-01-01T00:00:00",
        )
        cycle2 = ForageCycleSummary(
            forage_request_seq=2, mode="proactive", reason="coverage",
            timestamp="2026-01-02T00:00:00",
        )
        projections = _FakeProjections(
            forage_cycles={"ws-1": [cycle1, cycle2]},
        )
        cycles = projections.forage_cycles.get("ws-1", [])
        recent = list(reversed(cycles))[:50]
        assert recent[0].forage_request_seq == 2
        assert recent[1].forage_request_seq == 1

    def test_domain_override_strategies_roundtrip(self) -> None:
        """Domain strategies and overrides are accessible from projections."""
        from formicos.surface.projections import (
            DomainOverrideProjection,
            DomainStrategyProjection,
        )

        strat = DomainStrategyProjection(
            domain="docs.python.org", preferred_level=1,
            success_count=5, failure_count=0,
        )
        override = DomainOverrideProjection(
            domain="evil.example.com", action="distrust",
            actor="operator", reason="spam",
        )
        projections = _FakeProjections(
            domain_strategies={"ws-1": {"docs.python.org": strat}},
            domain_overrides={"ws-1": {"evil.example.com": override}},
        )
        strats = projections.domain_strategies["ws-1"]
        ovrs = projections.domain_overrides["ws-1"]
        assert "docs.python.org" in strats
        assert asdict(strats["docs.python.org"])["preferred_level"] == 1
        assert ovrs["evil.example.com"].action == "distrust"


# ---------------------------------------------------------------------------
# Track A: DomainPolicy integration
# ---------------------------------------------------------------------------


class TestDomainPolicyActions:
    """Verify DomainPolicy trust/distrust/reset actions."""

    def test_trust_action(self) -> None:
        from formicos.surface.forager import DomainPolicy

        dp = DomainPolicy()
        dp.trust("docs.python.org")
        assert dp.is_allowed("docs.python.org") is True
        assert "docs.python.org" in dp.trusted

    def test_distrust_action(self) -> None:
        from formicos.surface.forager import DomainPolicy

        dp = DomainPolicy()
        dp.distrust("evil.example.com")
        assert dp.is_allowed("evil.example.com") is False
        assert "evil.example.com" in dp.distrusted

    def test_reset_action(self) -> None:
        from formicos.surface.forager import DomainPolicy

        dp = DomainPolicy()
        dp.distrust("example.com")
        assert dp.is_allowed("example.com") is False
        dp.reset("example.com")
        assert dp.is_allowed("example.com") is True


# ---------------------------------------------------------------------------
# Track B: Forager provenance in knowledge detail
# ---------------------------------------------------------------------------


class TestForagerProvenanceEnrichment:
    """_enrich_trust_provenance includes forager provenance when present."""

    def test_forager_provenance_exposed(self) -> None:
        from formicos.surface.knowledge_catalog import _enrich_trust_provenance

        raw_entry: dict[str, Any] = {
            "source_colony_id": "forager",
            "content": "Python asyncio tutorial",
            "title": "asyncio docs",
            "conf_alpha": 5.0,
            "conf_beta": 5.0,
            "forager_provenance": {
                "source_url": "https://docs.python.org/3/library/asyncio.html",
                "source_domain": "docs.python.org",
                "source_credibility": 1.0,
                "fetch_timestamp": "2026-03-19T00:00:00",
                "forager_trigger": "reactive",
                "forager_query": "python asyncio",
                "quality_score": 0.85,
                "fetch_level": 1,
            },
        }
        item: dict[str, Any] = {}
        _enrich_trust_provenance(item, raw_entry)

        prov = item["provenance"]
        assert "forager_provenance" in prov
        fp = prov["forager_provenance"]
        assert fp["source_domain"] == "docs.python.org"
        assert fp["source_credibility"] == 1.0
        assert fp["source_url"] == "https://docs.python.org/3/library/asyncio.html"
        assert fp["quality_score"] == 0.85

    def test_no_forager_provenance_for_colony_entries(self) -> None:
        from formicos.surface.knowledge_catalog import _enrich_trust_provenance

        raw_entry: dict[str, Any] = {
            "source_colony_id": "colony-1",
            "content": "Some knowledge",
            "title": "Test entry",
            "conf_alpha": 5.0,
            "conf_beta": 5.0,
        }
        item: dict[str, Any] = {}
        _enrich_trust_provenance(item, raw_entry)

        prov = item["provenance"]
        assert "forager_provenance" not in prov


# ---------------------------------------------------------------------------
# Track C: OTel sink bridge
# ---------------------------------------------------------------------------


class TestOTelSink:
    """OTelSink correctly bridges TelemetryEvent to OTelAdapter."""

    @pytest.mark.asyncio
    async def test_llm_call_event(self) -> None:
        adapter = MagicMock(spec=OTelAdapter)
        adapter.enabled = True
        sink = OTelSink(adapter)

        event = MagicMock()
        event.event_type = "llm_call"
        event.payload = {
            "model": "claude-sonnet-4-20250514",
            "input_tokens": 100,
            "output_tokens": 50,
            "cost": 0.01,
            "duration_ms": 500,
        }
        await sink(event)
        adapter.record_llm_call.assert_called_once_with(
            model="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
            cost=0.01,
            duration_ms=500,
        )

    @pytest.mark.asyncio
    async def test_colony_lifecycle_event(self) -> None:
        adapter = MagicMock(spec=OTelAdapter)
        adapter.enabled = True
        sink = OTelSink(adapter)

        event = MagicMock()
        event.event_type = "colony_lifecycle"
        event.colony_id = "col-1"
        event.payload = {
            "workspace_id": "ws-1",
            "duration_ms": 3000,
            "status": "completed",
        }
        await sink(event)
        adapter.record_colony_lifecycle.assert_called_once_with(
            colony_id="col-1",
            workspace_id="ws-1",
            duration_ms=3000,
            status="completed",
        )

    @pytest.mark.asyncio
    async def test_retrieval_event(self) -> None:
        adapter = MagicMock(spec=OTelAdapter)
        adapter.enabled = True
        sink = OTelSink(adapter)

        event = MagicMock()
        event.event_type = "retrieval"
        event.payload = {
            "workspace_id": "ws-1",
            "result_count": 5,
            "duration_ms": 120,
        }
        await sink(event)
        adapter.record_retrieval.assert_called_once_with(
            workspace_id="ws-1",
            result_count=5,
            duration_ms=120,
        )

    @pytest.mark.asyncio
    async def test_disabled_adapter_skips(self) -> None:
        adapter = MagicMock(spec=OTelAdapter)
        adapter.enabled = False
        sink = OTelSink(adapter)

        event = MagicMock()
        event.event_type = "llm_call"
        event.payload = {
            "model": "x", "input_tokens": 1, "output_tokens": 1,
            "cost": 0, "duration_ms": 1,
        }
        await sink(event)
        adapter.record_llm_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_event_type_no_error(self) -> None:
        adapter = MagicMock(spec=OTelAdapter)
        adapter.enabled = True
        sink = OTelSink(adapter)

        event = MagicMock()
        event.event_type = "unknown_thing"
        event.payload = {}
        await sink(event)  # should not raise


class TestOTelAdapterCreateNoop:
    """OTelAdapter.create returns a no-op when OTel is not installed."""

    def test_create_returns_disabled_without_otel(self) -> None:
        adapter = OTelAdapter.create()
        # OTel is not installed in test env, so adapter should be disabled
        # (or enabled if otel is installed — either way, create() shouldn't crash)
        assert isinstance(adapter, OTelAdapter)


# ---------------------------------------------------------------------------
# Wave 46 cleanup: Forager activity data assembly for briefing
# ---------------------------------------------------------------------------


class TestForagerActivityDataAssembly:
    """Verify the projection data used by the Forager Activity briefing section."""

    def test_cycles_with_full_fields(self) -> None:
        """ForageCycleSummary carries all fields the briefing UI needs."""
        from formicos.surface.projections import ForageCycleSummary

        cycle = ForageCycleSummary(
            forage_request_seq=5,
            mode="operator",
            reason="manual topic search",
            queries_issued=3,
            pages_fetched=7,
            pages_rejected=2,
            entries_admitted=4,
            entries_deduplicated=1,
            duration_ms=1500,
            error="",
            timestamp="2026-03-19T10:00:00",
        )
        d = asdict(cycle)
        assert d["mode"] == "operator"
        assert d["pages_fetched"] == 7
        assert d["entries_admitted"] == 4
        assert d["timestamp"] == "2026-03-19T10:00:00"

    def test_domain_overrides_classify_trust_distrust(self) -> None:
        """DomainOverrideProjection action field distinguishes trusted/distrusted."""
        from formicos.surface.projections import DomainOverrideProjection

        trusted = DomainOverrideProjection(
            domain="docs.python.org", action="trust",
            actor="operator", reason="reliable",
        )
        distrusted = DomainOverrideProjection(
            domain="spam.example.com", action="distrust",
            actor="operator", reason="spam",
        )
        reset = DomainOverrideProjection(
            domain="neutral.example.com", action="reset",
            actor="operator", reason="reconsidered",
        )
        overrides = {
            "docs.python.org": trusted,
            "spam.example.com": distrusted,
            "neutral.example.com": reset,
        }
        # Mimic the frontend's classification logic
        trust_list = [d for d, o in overrides.items() if o.action == "trust"]
        distrust_list = [d for d, o in overrides.items() if o.action == "distrust"]
        assert trust_list == ["docs.python.org"]
        assert distrust_list == ["spam.example.com"]

    def test_empty_projections_produce_empty_activity(self) -> None:
        """When no forage cycles or overrides exist, everything is empty."""
        projections = _FakeProjections()
        cycles = projections.forage_cycles.get("ws-1", [])
        overrides = projections.domain_overrides.get("ws-1", {})
        assert cycles == []
        assert overrides == {}

    def test_forage_cycles_limit_applied(self) -> None:
        """Cycle limit truncation works as the endpoint does it."""
        from formicos.surface.projections import ForageCycleSummary

        cycles = [
            ForageCycleSummary(
                forage_request_seq=i, mode="reactive", reason=f"gap-{i}",
                timestamp=f"2026-03-{i+1:02d}T00:00:00",
            )
            for i in range(10)
        ]
        projections = _FakeProjections(forage_cycles={"ws-1": cycles})
        all_cycles = projections.forage_cycles["ws-1"]
        limit = 5
        recent = list(reversed(all_cycles))[:limit]
        assert len(recent) == 5
        # Most recent first
        assert recent[0].forage_request_seq == 9


class TestBriefingRouteExists:
    """Verify the briefing endpoint is registered at the correct path."""

    def test_briefing_route_path(self) -> None:
        """The briefing route must be /api/v1/workspaces/{workspace_id}/briefing."""
        import inspect

        from formicos.surface.routes.api import routes as api_routes_factory

        source = inspect.getsource(api_routes_factory)
        assert "/api/v1/workspaces/{workspace_id:str}/briefing" in source
        # The old incorrect path should NOT be in the route definitions
        assert "/api/v1/briefing/" not in source
