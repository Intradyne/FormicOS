"""Integration test — Self-maintenance dispatch (Wave 35, ADR-046).

Workspace with contradiction insight + auto_notify policy dispatches
maintenance colony automatically.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from formicos.core.types import AutonomyLevel, CasteSlot, MaintenancePolicy
from formicos.surface.proactive_intelligence import (
    KnowledgeInsight,
    ProactiveBriefing,
    SuggestedColony,
)
from formicos.surface.self_maintenance import MaintenanceDispatcher


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _make_briefing(
    workspace_id: str = "ws-1",
    insights: list[KnowledgeInsight] | None = None,
) -> ProactiveBriefing:
    return ProactiveBriefing(
        workspace_id=workspace_id,
        generated_at=_now_iso(),
        insights=insights or [],
        total_entries=10,
        entries_by_status={"verified": 5, "candidate": 5},
        avg_confidence=0.7,
        prediction_error_rate=0.1,
        active_clusters=2,
    )


def _contradiction_insight() -> KnowledgeInsight:
    return KnowledgeInsight(
        severity="action_required",
        category="contradiction",
        title="Conflicting auth patterns",
        detail="Entry mem-1 says use JWT. Entry mem-2 says use sessions.",
        affected_entries=["mem-1", "mem-2"],
        suggested_action="Research and resolve the contradiction",
        suggested_colony=SuggestedColony(
            task="Resolve contradiction between JWT and session auth entries",
            caste="researcher",
            strategy="sequential",
            max_rounds=3,
            rationale="Contradictory verified entries need resolution",
            estimated_cost=0.24,
        ),
    )


def _make_runtime(
    policy: MaintenancePolicy | None = None,
    workspace_id: str = "ws-1",
) -> MagicMock:
    """Create a mock runtime with configurable maintenance policy."""
    import json

    runtime = MagicMock()
    runtime.spawn_colony = AsyncMock(return_value="colony-maint-1")

    ws = MagicMock()
    ws.workspace_id = workspace_id
    if policy:
        ws.config = {"maintenance_policy": json.dumps(policy.model_dump())}
    else:
        ws.config = {}

    runtime.projections = MagicMock()
    runtime.projections.workspaces = {workspace_id: ws}
    runtime.projections.colonies = {}
    return runtime


class TestSelfMaintenanceIntegration:
    """Full integration: insight + policy → dispatch decision."""

    @pytest.mark.asyncio
    async def test_suggest_level_no_dispatch(self) -> None:
        """Suggest level: insights are shown but no colonies spawn."""
        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel.suggest,
            auto_actions=["contradiction"],
        )
        runtime = _make_runtime(policy)
        dispatcher = MaintenanceDispatcher(runtime)

        briefing = _make_briefing(insights=[_contradiction_insight()])
        dispatched = await dispatcher.evaluate_and_dispatch("ws-1", briefing)

        assert dispatched == [], "Suggest level should not auto-dispatch"
        runtime.spawn_colony.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_notify_dispatches_opted_in_category(self) -> None:
        """auto_notify with contradiction in auto_actions dispatches colony."""
        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel.auto_notify,
            auto_actions=["contradiction"],
            daily_maintenance_budget=5.0,
        )
        runtime = _make_runtime(policy)
        dispatcher = MaintenanceDispatcher(runtime)

        briefing = _make_briefing(insights=[_contradiction_insight()])
        dispatched = await dispatcher.evaluate_and_dispatch("ws-1", briefing)

        assert len(dispatched) == 1
        assert dispatched[0] == "colony-maint-1"
        runtime.spawn_colony.assert_called_once()
        call_kwargs = runtime.spawn_colony.call_args
        # Colony task should be prefixed with maintenance context
        assert "maintenance:contradiction" in call_kwargs.kwargs.get(
            "task", call_kwargs[1].get("task", ""),
        ) or "maintenance:contradiction" in str(call_kwargs)

    @pytest.mark.asyncio
    async def test_auto_notify_skips_non_opted_category(self) -> None:
        """auto_notify skips insights whose category is NOT in auto_actions."""
        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel.auto_notify,
            auto_actions=["coverage"],  # NOT contradiction
        )
        runtime = _make_runtime(policy)
        dispatcher = MaintenanceDispatcher(runtime)

        briefing = _make_briefing(insights=[_contradiction_insight()])
        dispatched = await dispatcher.evaluate_and_dispatch("ws-1", briefing)

        assert dispatched == []

    @pytest.mark.asyncio
    async def test_autonomous_dispatches_all_eligible(self) -> None:
        """Autonomous level dispatches all eligible insights regardless of auto_actions."""
        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel.autonomous,
            daily_maintenance_budget=5.0,
        )
        runtime = _make_runtime(policy)
        dispatcher = MaintenanceDispatcher(runtime)

        briefing = _make_briefing(insights=[_contradiction_insight()])
        dispatched = await dispatcher.evaluate_and_dispatch("ws-1", briefing)

        assert len(dispatched) == 1

    @pytest.mark.asyncio
    async def test_budget_cap_blocks_dispatch(self) -> None:
        """Daily budget cap prevents colony dispatch."""
        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel.autonomous,
            daily_maintenance_budget=0.01,  # Very low budget
        )
        runtime = _make_runtime(policy)
        dispatcher = MaintenanceDispatcher(runtime)

        # Cost is 0.24 which exceeds 0.01 budget
        briefing = _make_briefing(insights=[_contradiction_insight()])
        dispatched = await dispatcher.evaluate_and_dispatch("ws-1", briefing)

        assert dispatched == [], "Budget cap should block dispatch"

    @pytest.mark.asyncio
    async def test_max_colonies_cap(self) -> None:
        """max_maintenance_colonies cap prevents additional dispatch."""
        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel.autonomous,
            max_maintenance_colonies=0,
            daily_maintenance_budget=5.0,
        )
        runtime = _make_runtime(policy)
        dispatcher = MaintenanceDispatcher(runtime)

        briefing = _make_briefing(insights=[_contradiction_insight()])
        dispatched = await dispatcher.evaluate_and_dispatch("ws-1", briefing)

        assert dispatched == [], "Max colonies cap should block dispatch"

    @pytest.mark.asyncio
    async def test_no_suggested_colony_skips(self) -> None:
        """Insights without suggested_colony are skipped."""
        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel.autonomous,
            daily_maintenance_budget=5.0,
        )
        runtime = _make_runtime(policy)
        dispatcher = MaintenanceDispatcher(runtime)

        insight = KnowledgeInsight(
            severity="info",
            category="confidence",
            title="Confidence declining",
            detail="Entry confidence is declining over time.",
            suggested_colony=None,  # No suggested colony
        )
        briefing = _make_briefing(insights=[insight])
        dispatched = await dispatcher.evaluate_and_dispatch("ws-1", briefing)

        assert dispatched == []
