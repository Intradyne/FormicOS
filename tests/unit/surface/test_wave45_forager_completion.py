"""Wave 45 Team 1: Forager completion tests.

Covers:
- Proactive forage signals on insight rules (1A)
- Source credibility tier system (1B)
- Source credibility integration with admission provenance (1B)
- Dispatcher bridge for forage signals (1A)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from formicos.surface.forager import (
    CREDIBILITY_T1,
    CREDIBILITY_T2,
    CREDIBILITY_T3,
    CREDIBILITY_T4,
    CREDIBILITY_T5,
    ForageRequest,
    get_source_credibility,
    prepare_forager_entry,
)
from formicos.surface.proactive_intelligence import (
    KnowledgeInsight,
    generate_briefing,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeCooccurrence:
    weight: float = 1.0
    last_reinforced: str = ""
    reinforcement_count: int = 0


@dataclass
class _FakeProjections:
    memory_entries: dict[str, dict[str, Any]] = field(default_factory=dict)
    cooccurrence_weights: dict[tuple[str, str], _FakeCooccurrence] = field(
        default_factory=dict,
    )


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _recent_iso() -> str:
    return (datetime.now(tz=UTC) - timedelta(days=1)).isoformat()


# ---------------------------------------------------------------------------
# 1A: Proactive forage signals on insight rules
# ---------------------------------------------------------------------------


class TestForageSignalOnConfidenceDecline:
    """Rule 1 emits forage_signal when confidence declines."""

    def test_confidence_decline_carries_forage_signal(self) -> None:
        entries = {
            "e1": {
                "workspace_id": "ws-1",
                "conf_alpha": 3.0,
                "conf_beta": 5.0,
                "peak_alpha": 10.0,
                "last_confidence_update": _recent_iso(),
                "title": "Python asyncio patterns",
                "domains": ["python", "asyncio"],
                "status": "verified",
            },
        }
        projections = _FakeProjections(memory_entries=entries)
        briefing = generate_briefing("ws-1", projections)  # type: ignore[arg-type]

        confidence_insights = [
            i for i in briefing.insights if i.category == "confidence"
        ]
        assert len(confidence_insights) >= 1
        insight = confidence_insights[0]
        assert insight.forage_signal is not None
        assert insight.forage_signal["trigger"] == "proactive:confidence_decline"
        assert "python" in insight.forage_signal.get("domains", [])
        assert insight.forage_signal["max_results"] == 3

    def test_no_forage_signal_when_decline_small(self) -> None:
        entries = {
            "e1": {
                "workspace_id": "ws-1",
                "conf_alpha": 9.0,
                "conf_beta": 5.0,
                "peak_alpha": 10.0,
                "last_confidence_update": _recent_iso(),
                "title": "Stable entry",
                "domains": ["python"],
                "status": "verified",
            },
        }
        projections = _FakeProjections(memory_entries=entries)
        briefing = generate_briefing("ws-1", projections)  # type: ignore[arg-type]
        confidence_insights = [
            i for i in briefing.insights if i.category == "confidence"
        ]
        assert len(confidence_insights) == 0


class TestForageSignalOnCoverageGap:
    """Rule 4 emits forage_signal for coverage gaps."""

    def test_coverage_gap_carries_forage_signal(self) -> None:
        entries = {}
        for i in range(3):
            entries[f"e{i}"] = {
                "workspace_id": "ws-1",
                "prediction_error_count": 5,
                "domains": ["kubernetes"],
                "status": "verified",
                "conf_alpha": 5.0,
                "conf_beta": 5.0,
            }
        projections = _FakeProjections(memory_entries=entries)
        briefing = generate_briefing("ws-1", projections)  # type: ignore[arg-type]

        coverage_insights = [
            i for i in briefing.insights if i.category == "coverage"
        ]
        assert len(coverage_insights) >= 1
        insight = coverage_insights[0]
        assert insight.forage_signal is not None
        assert insight.forage_signal["trigger"] == "proactive:coverage_gap"
        assert "kubernetes" in insight.forage_signal["domains"]
        assert insight.forage_signal["max_results"] == 5
        # Must also preserve suggested_colony (additive)
        assert insight.suggested_colony is not None


class TestForageSignalOnStaleCluster:
    """Rule 5 emits forage_signal for stale clusters."""

    def test_stale_cluster_carries_forage_signal(self) -> None:
        entries = {
            "e1": {
                "workspace_id": "ws-1",
                "prediction_error_count": 5,
                "domains": ["docker"],
                "conf_alpha": 5.0,
                "conf_beta": 5.0,
                "status": "verified",
            },
            "e2": {
                "workspace_id": "ws-1",
                "prediction_error_count": 5,
                "domains": ["docker"],
                "conf_alpha": 5.0,
                "conf_beta": 5.0,
                "status": "verified",
            },
        }
        cooccurrence = {
            ("e1", "e2"): _FakeCooccurrence(weight=2.0),
        }
        projections = _FakeProjections(
            memory_entries=entries,
            cooccurrence_weights=cooccurrence,
        )
        briefing = generate_briefing("ws-1", projections)  # type: ignore[arg-type]

        stale_insights = [
            i for i in briefing.insights if i.category == "staleness"
        ]
        assert len(stale_insights) >= 1
        insight = stale_insights[0]
        assert insight.forage_signal is not None
        assert insight.forage_signal["trigger"] == "proactive:stale_cluster"
        assert "docker" in insight.forage_signal["domains"]
        # Must also preserve suggested_colony (additive)
        assert insight.suggested_colony is not None


# ---------------------------------------------------------------------------
# 1B: Source credibility tier system
# ---------------------------------------------------------------------------


class TestSourceCredibility:
    """get_source_credibility returns correct tiers."""

    def test_tier1_exact_match(self) -> None:
        assert get_source_credibility("docs.python.org") == CREDIBILITY_T1
        assert get_source_credibility("developer.mozilla.org") == CREDIBILITY_T1

    def test_tier1_suffix_match(self) -> None:
        # Subdomain of a T1 domain
        assert get_source_credibility("api.docs.python.org") == CREDIBILITY_T1

    def test_tier2_tld(self) -> None:
        assert get_source_credibility("arxiv.org") == CREDIBILITY_T2
        assert get_source_credibility("cs.stanford.edu") == CREDIBILITY_T2
        assert get_source_credibility("data.gov") == CREDIBILITY_T2

    def test_tier3_community(self) -> None:
        assert get_source_credibility("stackoverflow.com") == CREDIBILITY_T3
        assert get_source_credibility("github.com") == CREDIBILITY_T3

    def test_tier4_blogs(self) -> None:
        assert get_source_credibility("medium.com") == CREDIBILITY_T4

    def test_tier5_unknown(self) -> None:
        assert get_source_credibility("random-blog.example.com") == CREDIBILITY_T5
        assert get_source_credibility("") == CREDIBILITY_T5

    def test_case_insensitive(self) -> None:
        assert get_source_credibility("Docs.Python.Org") == CREDIBILITY_T1

    def test_gov_uk_tld(self) -> None:
        assert get_source_credibility("www.nhs.gov.uk") == CREDIBILITY_T2


class TestSourceCredibilityInEntry:
    """prepare_forager_entry embeds credibility in provenance."""

    def test_authoritative_domain_gets_high_credibility(self) -> None:
        entry = prepare_forager_entry(
            "Some content about Python async",
            source_url="https://docs.python.org/3/library/asyncio.html",
            title="asyncio docs",
            workspace_id="ws-1",
        )
        prov = entry["forager_provenance"]
        assert prov["source_credibility"] == CREDIBILITY_T1
        assert prov["source_domain"] == "docs.python.org"

    def test_unknown_domain_gets_low_credibility(self) -> None:
        entry = prepare_forager_entry(
            "Some blog post",
            source_url="https://random-blog.example.com/post",
            title="blog post",
            workspace_id="ws-1",
        )
        prov = entry["forager_provenance"]
        assert prov["source_credibility"] == CREDIBILITY_T5


# ---------------------------------------------------------------------------
# 1B: Admission provenance integration
# ---------------------------------------------------------------------------


class TestAdmissionCredibilityIntegration:
    """Source credibility adjusts admission provenance score."""

    def test_high_credibility_boosts_provenance(self) -> None:
        from formicos.surface.admission import evaluate_entry

        entry = prepare_forager_entry(
            "Authoritative content from docs",
            source_url="https://docs.python.org/3/tutorial.html",
            title="Python tutorial",
            workspace_id="ws-1",
        )
        result = evaluate_entry(entry)
        # T1 credibility (1.0) should boost provenance
        assert result.signal_scores["provenance"] > 0.5
        assert "low_source_credibility" not in result.flags

    def test_low_credibility_penalizes_provenance(self) -> None:
        from formicos.surface.admission import evaluate_entry

        entry = prepare_forager_entry(
            "Random blog content",
            source_url="https://unknown-blog.example.com/post",
            title="blog post",
            workspace_id="ws-1",
        )
        result = evaluate_entry(entry)
        # T5 credibility (0.30) should lower provenance and flag
        assert "low_source_credibility" in result.flags

    def test_non_forager_entries_unaffected(self) -> None:
        from formicos.surface.admission import evaluate_entry

        # Colony-produced entry has no forager_provenance
        entry = {
            "source_colony_id": "colony-1",
            "content": "Some knowledge",
            "title": "Test entry",
            "conf_alpha": 5.0,
            "conf_beta": 5.0,
        }
        result = evaluate_entry(entry)
        # Standard provenance scoring, no credibility blend
        assert "low_source_credibility" not in result.flags


# ---------------------------------------------------------------------------
# 1A: Dispatcher bridge
# ---------------------------------------------------------------------------


class TestMaintenanceForageDispatch:
    """MaintenanceDispatcher hands forage signals to ForagerService."""

    @pytest.mark.asyncio
    async def test_forage_signal_dispatched_when_policy_allows(self) -> None:
        from formicos.core.types import AutonomyLevel, MaintenancePolicy
        from formicos.surface.self_maintenance import MaintenanceDispatcher

        # Setup: mock runtime with forager_service
        runtime = MagicMock()
        runtime.forager_service = MagicMock()
        runtime.forager_service.handle_forage_signal = AsyncMock()
        runtime.projections = MagicMock()
        runtime.projections.workspaces = {}
        runtime.projections.colonies = {}

        dispatcher = MaintenanceDispatcher(runtime)

        # Override policy retrieval to return auto_notify with coverage
        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel.auto_notify,
            auto_actions=["coverage"],
            max_maintenance_colonies=5,
            daily_maintenance_budget=10.0,
        )
        dispatcher._get_policy = MagicMock(return_value=policy)  # type: ignore[method-assign]

        # Build briefing with coverage insight carrying forage_signal
        from formicos.surface.proactive_intelligence import ProactiveBriefing

        briefing = ProactiveBriefing(
            workspace_id="ws-1",
            generated_at=_now_iso(),
            insights=[
                KnowledgeInsight(
                    severity="attention",
                    category="coverage",
                    title="Coverage gap in 'kubernetes'",
                    detail="3 entries with high prediction errors.",
                    forage_signal={
                        "trigger": "proactive:coverage_gap",
                        "gap_description": "coverage gap",
                        "topic": "kubernetes",
                        "domains": ["kubernetes"],
                        "max_results": 5,
                    },
                ),
            ],
            total_entries=10,
            entries_by_status={"verified": 10},
            avg_confidence=0.6,
            prediction_error_rate=0.3,
            active_clusters=2,
        )

        await dispatcher.evaluate_and_dispatch("ws-1", briefing)

        # ForagerService.handle_forage_signal was called via asyncio.create_task
        # Give the event loop a tick to process the task
        import asyncio

        await asyncio.sleep(0)
        runtime.forager_service.handle_forage_signal.assert_called_once()
        signal = runtime.forager_service.handle_forage_signal.call_args[0][0]
        assert signal["workspace_id"] == "ws-1"
        assert signal["trigger"] == "proactive:coverage_gap"

    @pytest.mark.asyncio
    async def test_forage_signal_skipped_when_category_not_in_auto_actions(
        self,
    ) -> None:
        from formicos.core.types import AutonomyLevel, MaintenancePolicy
        from formicos.surface.self_maintenance import MaintenanceDispatcher

        runtime = MagicMock()
        runtime.forager_service = MagicMock()
        runtime.forager_service.handle_forage_signal = AsyncMock()
        runtime.projections = MagicMock()
        runtime.projections.workspaces = {}
        runtime.projections.colonies = {}

        dispatcher = MaintenanceDispatcher(runtime)
        # Policy only allows "staleness", not "coverage"
        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel.auto_notify,
            auto_actions=["staleness"],
            max_maintenance_colonies=5,
            daily_maintenance_budget=10.0,
        )
        dispatcher._get_policy = MagicMock(return_value=policy)  # type: ignore[method-assign]

        from formicos.surface.proactive_intelligence import ProactiveBriefing

        briefing = ProactiveBriefing(
            workspace_id="ws-1",
            generated_at=_now_iso(),
            insights=[
                KnowledgeInsight(
                    severity="attention",
                    category="coverage",
                    title="Coverage gap",
                    detail="Gap detected.",
                    forage_signal={
                        "trigger": "proactive:coverage_gap",
                        "gap_description": "gap",
                        "topic": "kubernetes",
                        "domains": ["kubernetes"],
                        "max_results": 5,
                    },
                ),
            ],
            total_entries=10,
            entries_by_status={},
            avg_confidence=0.6,
            prediction_error_rate=0.0,
            active_clusters=0,
        )

        await dispatcher.evaluate_and_dispatch("ws-1", briefing)
        import asyncio

        await asyncio.sleep(0)
        runtime.forager_service.handle_forage_signal.assert_not_called()

    @pytest.mark.asyncio
    async def test_forage_signal_skipped_when_suggest_mode(self) -> None:
        from formicos.core.types import AutonomyLevel, MaintenancePolicy
        from formicos.surface.self_maintenance import MaintenanceDispatcher

        runtime = MagicMock()
        runtime.forager_service = MagicMock()
        runtime.forager_service.handle_forage_signal = AsyncMock()
        runtime.projections = MagicMock()
        runtime.projections.workspaces = {}
        runtime.projections.colonies = {}

        dispatcher = MaintenanceDispatcher(runtime)
        policy = MaintenancePolicy(autonomy_level=AutonomyLevel.suggest)
        dispatcher._get_policy = MagicMock(return_value=policy)  # type: ignore[method-assign]

        from formicos.surface.proactive_intelligence import ProactiveBriefing

        briefing = ProactiveBriefing(
            workspace_id="ws-1",
            generated_at=_now_iso(),
            insights=[
                KnowledgeInsight(
                    severity="attention",
                    category="coverage",
                    title="Coverage gap",
                    detail="Gap detected.",
                    forage_signal={
                        "trigger": "proactive:coverage_gap",
                        "gap_description": "gap",
                        "topic": "k8s",
                        "domains": ["kubernetes"],
                        "max_results": 5,
                    },
                ),
            ],
            total_entries=10,
            entries_by_status={},
            avg_confidence=0.6,
            prediction_error_rate=0.0,
            active_clusters=0,
        )

        result = await dispatcher.evaluate_and_dispatch("ws-1", briefing)
        assert result == []
        runtime.forager_service.handle_forage_signal.assert_not_called()
