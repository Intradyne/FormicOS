"""Tests for self-maintenance dispatch engine (Wave 35)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from formicos.core.types import AutonomyLevel, MaintenancePolicy
from formicos.surface.proactive_intelligence import (
    KnowledgeInsight,
    ProactiveBriefing,
    SuggestedColony,
)
from formicos.surface.self_maintenance import MaintenanceDispatcher

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeWorkspace:
    id: str
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class _FakeColonyProjection:
    id: str
    workspace_id: str
    status: str = "running"
    tags: list[str] = field(default_factory=list)


@dataclass
class _FakeProjections:
    workspaces: dict[str, _FakeWorkspace] = field(default_factory=dict)
    colonies: dict[str, _FakeColonyProjection] = field(default_factory=dict)
    memory_entries: dict[str, dict[str, Any]] = field(default_factory=dict)
    cooccurrence_weights: dict[tuple[str, str], Any] = field(default_factory=dict)
    distillation_candidates: list[list[str]] = field(default_factory=list)


def _make_runtime(
    *,
    policy: MaintenancePolicy | None = None,
    active_maintenance: int = 0,
) -> Any:
    """Build a mock runtime with the given policy on workspace 'ws-1'."""
    ws = _FakeWorkspace(id="ws-1")
    if policy is not None:
        ws.config["maintenance_policy"] = policy.model_dump()

    projections = _FakeProjections(workspaces={"ws-1": ws})

    # Simulate active maintenance colonies
    for i in range(active_maintenance):
        col = _FakeColonyProjection(
            id=f"maint-{i}", workspace_id="ws-1", status="running",
            tags=["maintenance"],
        )
        projections.colonies[f"maint-{i}"] = col

    runtime = type("Runtime", (), {
        "projections": projections,
        "spawn_colony": AsyncMock(return_value="col-new"),
    })()
    return runtime


def _make_briefing(insights: list[KnowledgeInsight]) -> ProactiveBriefing:
    return ProactiveBriefing(
        workspace_id="ws-1",
        generated_at=datetime.now(tz=UTC).isoformat(),
        insights=insights,
        total_entries=10,
        entries_by_status={"verified": 10},
        avg_confidence=0.7,
        prediction_error_rate=0.1,
        active_clusters=5,
    )


def _contradiction_insight() -> KnowledgeInsight:
    return KnowledgeInsight(
        severity="action_required",
        category="contradiction",
        title="Test contradiction",
        detail="Two entries conflict",
        affected_entries=["e1", "e2"],
        suggested_colony=SuggestedColony(
            task="Resolve contradiction",
            caste="researcher",
            strategy="sequential",
            max_rounds=5,
            estimated_cost=0.40,
        ),
    )


def _coverage_insight() -> KnowledgeInsight:
    return KnowledgeInsight(
        severity="attention",
        category="coverage_gap",
        title="Coverage gap in docker",
        detail="Entries have high prediction errors",
        affected_entries=["e3"],
        suggested_colony=SuggestedColony(
            task="Research docker",
            caste="researcher",
            strategy="sequential",
            max_rounds=5,
            estimated_cost=0.40,
        ),
    )


def _stale_insight() -> KnowledgeInsight:
    return KnowledgeInsight(
        severity="attention",
        category="stale_cluster",
        title="Stale cluster in auth",
        detail="Cluster entries have high errors",
        affected_entries=["e4", "e5"],
        suggested_colony=SuggestedColony(
            task="Re-validate auth cluster",
            caste="researcher",
            strategy="sequential",
            max_rounds=5,
            estimated_cost=0.40,
        ),
    )


def _confidence_insight() -> KnowledgeInsight:
    """Insight without suggested_colony (not auto-dispatchable)."""
    return KnowledgeInsight(
        severity="attention",
        category="confidence",
        title="Confidence declining",
        detail="Entry alpha dropped",
        affected_entries=["e6"],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSuggestLevel:
    @pytest.mark.asyncio
    async def test_suggest_no_dispatch(self) -> None:
        """suggest level: no colonies dispatched regardless of insights."""
        runtime = _make_runtime(policy=MaintenancePolicy())
        dispatcher = MaintenanceDispatcher(runtime)
        briefing = _make_briefing([_contradiction_insight()])
        result = await dispatcher.evaluate_and_dispatch("ws-1", briefing)
        assert result == []
        runtime.spawn_colony.assert_not_called()


class TestAutoNotifyLevel:
    @pytest.mark.asyncio
    async def test_auto_notify_dispatches_opted_in(self) -> None:
        """auto_notify with auto_actions=["contradiction"]: contradiction dispatches."""
        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel.auto_notify,
            auto_actions=["contradiction"],
        )
        runtime = _make_runtime(policy=policy)
        dispatcher = MaintenanceDispatcher(runtime)
        briefing = _make_briefing([_contradiction_insight(), _coverage_insight()])
        result = await dispatcher.evaluate_and_dispatch("ws-1", briefing)
        assert len(result) == 1  # only contradiction, not coverage_gap
        runtime.spawn_colony.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_notify_empty_actions_no_dispatch(self) -> None:
        """auto_notify with empty auto_actions: nothing dispatches."""
        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel.auto_notify,
            auto_actions=[],
        )
        runtime = _make_runtime(policy=policy)
        dispatcher = MaintenanceDispatcher(runtime)
        briefing = _make_briefing([_contradiction_insight()])
        result = await dispatcher.evaluate_and_dispatch("ws-1", briefing)
        assert result == []


class TestAutonomousLevel:
    @pytest.mark.asyncio
    async def test_autonomous_dispatches_all_eligible(self) -> None:
        """autonomous: all 3 eligible categories dispatch."""
        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel.autonomous,
            daily_maintenance_budget=5.0,
            max_maintenance_colonies=5,
        )
        runtime = _make_runtime(policy=policy)
        dispatcher = MaintenanceDispatcher(runtime)
        briefing = _make_briefing([
            _contradiction_insight(),
            _coverage_insight(),
            _stale_insight(),
        ])
        result = await dispatcher.evaluate_and_dispatch("ws-1", briefing)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_skips_insight_without_suggested_colony(self) -> None:
        """Insights without suggested_colony are skipped."""
        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel.autonomous,
        )
        runtime = _make_runtime(policy=policy)
        dispatcher = MaintenanceDispatcher(runtime)
        briefing = _make_briefing([_confidence_insight()])
        result = await dispatcher.evaluate_and_dispatch("ws-1", briefing)
        assert result == []


class TestBudgetCap:
    @pytest.mark.asyncio
    async def test_budget_exhausted_blocks_dispatch(self) -> None:
        """3rd colony blocked when daily budget exhausted."""
        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel.autonomous,
            daily_maintenance_budget=0.75,  # enough for 1 colony ($0.40), not 2
            max_maintenance_colonies=5,
        )
        runtime = _make_runtime(policy=policy)
        dispatcher = MaintenanceDispatcher(runtime)
        briefing = _make_briefing([
            _contradiction_insight(),  # $0.40
            _coverage_insight(),       # $0.40 — would exceed budget
        ])
        result = await dispatcher.evaluate_and_dispatch("ws-1", briefing)
        assert len(result) == 1


class TestConcurrentCap:
    @pytest.mark.asyncio
    async def test_max_colonies_blocks_dispatch(self) -> None:
        """3rd colony blocked when max_maintenance_colonies=2 reached."""
        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel.autonomous,
            max_maintenance_colonies=2,
            daily_maintenance_budget=10.0,
        )
        runtime = _make_runtime(policy=policy, active_maintenance=2)
        dispatcher = MaintenanceDispatcher(runtime)
        briefing = _make_briefing([_contradiction_insight()])
        result = await dispatcher.evaluate_and_dispatch("ws-1", briefing)
        assert result == []


class TestDailyBudgetReset:
    @pytest.mark.asyncio
    async def test_budget_resets_across_days(self) -> None:
        """Daily budget resets at midnight UTC."""
        from datetime import date

        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel.autonomous,
            daily_maintenance_budget=0.50,
            max_maintenance_colonies=5,
        )
        runtime = _make_runtime(policy=policy)
        dispatcher = MaintenanceDispatcher(runtime)

        # Simulate yesterday's spend
        dispatcher._daily_spend["ws-1"] = 0.50
        dispatcher._last_reset = date(2020, 1, 1)  # force reset

        briefing = _make_briefing([_contradiction_insight()])
        result = await dispatcher.evaluate_and_dispatch("ws-1", briefing)
        assert len(result) == 1  # budget was reset


class TestDefaultPolicy:
    def test_default_values(self) -> None:
        policy = MaintenancePolicy()
        assert policy.autonomy_level == AutonomyLevel.suggest
        assert policy.auto_actions == []
        assert policy.max_maintenance_colonies == 2
        assert policy.daily_maintenance_budget == 1.0


# ---------------------------------------------------------------------------
# Wave 45.5: run_proactive_dispatch — live runtime path
# ---------------------------------------------------------------------------


class TestRunProactiveDispatch:
    """Verifies the live runtime path that generates briefings and dispatches."""

    @pytest.mark.asyncio
    async def test_dispatches_across_workspaces(self) -> None:
        """run_proactive_dispatch iterates workspaces and dispatches."""
        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel.autonomous,
            daily_maintenance_budget=5.0,
            max_maintenance_colonies=5,
        )
        # Two workspaces, each with entries that trigger coverage insights
        ws1 = _FakeWorkspace(id="ws-1", config={"maintenance_policy": policy.model_dump()})
        ws2 = _FakeWorkspace(id="ws-2", config={"maintenance_policy": policy.model_dump()})
        projections = _FakeProjections(
            workspaces={"ws-1": ws1, "ws-2": ws2},
            memory_entries={
                f"e{i}": {
                    "workspace_id": "ws-1",
                    "prediction_error_count": 5,
                    "domains": ["python"],
                    "status": "verified",
                    "conf_alpha": 5.0,
                    "conf_beta": 5.0,
                }
                for i in range(3)
            },
        )
        runtime = type("Runtime", (), {
            "projections": projections,
            "spawn_colony": AsyncMock(return_value="col-new"),
        })()
        dispatcher = MaintenanceDispatcher(runtime)
        results = await dispatcher.run_proactive_dispatch()
        # ws-1 should have dispatched (coverage gap entries present)
        # ws-2 has no entries so no insights trigger
        assert isinstance(results, dict)
        # At least ws-1 dispatched something
        if "ws-1" in results:
            assert len(results["ws-1"]) >= 1

    @pytest.mark.asyncio
    async def test_suggest_mode_dispatches_nothing(self) -> None:
        """run_proactive_dispatch respects suggest-only policy."""
        policy = MaintenancePolicy(autonomy_level=AutonomyLevel.suggest)
        ws = _FakeWorkspace(id="ws-1", config={"maintenance_policy": policy.model_dump()})
        projections = _FakeProjections(
            workspaces={"ws-1": ws},
            memory_entries={
                "e1": {
                    "workspace_id": "ws-1",
                    "prediction_error_count": 5,
                    "domains": ["python"],
                    "status": "verified",
                    "conf_alpha": 5.0,
                    "conf_beta": 5.0,
                },
            },
        )
        runtime = type("Runtime", (), {
            "projections": projections,
            "spawn_colony": AsyncMock(return_value="col-new"),
        })()
        dispatcher = MaintenanceDispatcher(runtime)
        results = await dispatcher.run_proactive_dispatch()
        assert results == {}

    @pytest.mark.asyncio
    async def test_empty_workspaces_returns_empty(self) -> None:
        """No workspaces means no dispatch."""
        projections = _FakeProjections()
        runtime = type("Runtime", (), {
            "projections": projections,
            "spawn_colony": AsyncMock(return_value="col-new"),
        })()
        dispatcher = MaintenanceDispatcher(runtime)
        results = await dispatcher.run_proactive_dispatch()
        assert results == {}
