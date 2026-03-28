"""Unit tests for Wave 70.0 Team C: autonomy guardrails.

Covers blast radius estimation, autonomy scoring, check_autonomy_budget
Queen tool, dispatch gate integration, and the autonomy-status endpoint.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.surface.self_maintenance import (
    AutonomyScore,
    BlastRadiusEstimate,
    compute_autonomy_score,
    estimate_blast_radius,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_outcome(
    *,
    colony_id: str = "c1",
    workspace_id: str = "ws1",
    succeeded: bool = True,
    total_cost: float = 0.10,
    quality_score: float = 0.8,
    strategy: str = "sequential",
    caste_composition: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        colony_id=colony_id,
        workspace_id=workspace_id,
        thread_id="t1",
        succeeded=succeeded,
        total_rounds=3,
        total_cost=total_cost,
        duration_ms=5000,
        entries_extracted=1,
        entries_accessed=2,
        quality_score=quality_score,
        caste_composition=caste_composition or ["coder"],
        strategy=strategy,
        maintenance_source=None,
    )


def _make_projections(
    outcomes: list[Any] | None = None,
    *,
    acted_on: dict[str, int] | None = None,
    kills: int = 0,
) -> MagicMock:
    proj = MagicMock()
    colony_outcomes: dict[str, Any] = {}
    if outcomes:
        for o in outcomes:
            colony_outcomes[o.colony_id] = o
    proj.colony_outcomes = colony_outcomes

    # operator_behavior
    behavior = MagicMock()
    behavior.suggestion_categories_acted_on = acted_on or {}
    behavior.kill_records = [MagicMock() for _ in range(kills)]
    proj.operator_behavior = behavior

    # outcome_stats replicates the real implementation's shape
    def _outcome_stats(ws_id: str) -> list[dict[str, Any]]:
        ws_outcomes = [o for o in colony_outcomes.values() if o.workspace_id == ws_id]
        if not ws_outcomes:
            return []
        buckets: dict[tuple[str, str], list[Any]] = {}
        for o in ws_outcomes:
            key = (o.strategy, ",".join(sorted(o.caste_composition)))
            buckets.setdefault(key, []).append(o)
        stats = []
        for (strategy, caste_mix), group in buckets.items():
            successes = sum(1 for o in group if o.succeeded)
            stats.append({
                "strategy": strategy,
                "caste_mix": caste_mix,
                "total": len(group),
                "success_rate": successes / len(group),
                "avg_rounds": sum(o.total_rounds for o in group) / len(group),
                "avg_cost": sum(o.total_cost for o in group) / len(group),
            })
        return stats

    proj.outcome_stats = _outcome_stats
    return proj


def _make_runtime_with_workspace(
    *,
    policy: dict[str, Any] | None = None,
    outcomes: list[Any] | None = None,
    acted_on: dict[str, int] | None = None,
    kills: int = 0,
    daily_spend: float = 0.0,
) -> MagicMock:
    """Build a mock runtime with workspace, projections, and maintenance dispatcher."""
    runtime = MagicMock()
    runtime.parse_tool_input = MagicMock(side_effect=lambda tc: tc.get("input", {}))

    proj = _make_projections(outcomes, acted_on=acted_on, kills=kills)
    runtime.projections = proj

    ws_config: dict[str, Any] = {}
    if policy:
        ws_config["maintenance_policy"] = json.dumps(policy)

    ws = SimpleNamespace(
        config=ws_config,
        budget=SimpleNamespace(total_cost=1.50),
    )
    proj.workspaces = {"ws1": ws}

    # Maintenance dispatcher mock
    dispatcher = MagicMock()
    dispatcher._daily_spend = {"ws1": daily_spend}
    dispatcher._reset_daily_budget_if_needed = MagicMock()
    dispatcher._count_active_maintenance_colonies = MagicMock(return_value=1)
    runtime.maintenance_dispatcher = dispatcher

    return runtime


# ---------------------------------------------------------------------------
# Track 8: Blast Radius Estimator
# ---------------------------------------------------------------------------


class TestEstimateBlastRadius:
    def test_low_blast_radius(self) -> None:
        """Simple task, researcher caste, 2 rounds -> low."""
        result = estimate_blast_radius(
            task="Check test coverage",
            caste="researcher",
            max_rounds=2,
        )
        assert isinstance(result, BlastRadiusEstimate)
        assert result.score < 0.3
        assert result.level == "low"
        assert result.recommendation == "proceed"

    def test_high_blast_radius(self) -> None:
        """Long task with danger keywords, coder caste, high rounds, stigmergic -> high."""
        long_task = (
            "Delete all database tables and migrate the schema. "
            "Also refactor the auth module and deploy to production. " * 5
        )
        result = estimate_blast_radius(
            task=long_task,
            caste="coder",
            max_rounds=8,
            strategy="stigmergic",
        )
        assert result.score >= 0.6
        assert result.level == "high"
        assert result.recommendation == "escalate"

    def test_medium_blast_radius(self) -> None:
        """Moderate task, coder caste, 3 rounds -> medium."""
        result = estimate_blast_radius(
            task="Update the logging configuration",
            caste="coder",
            max_rounds=3,
        )
        assert 0.3 <= result.score < 0.6
        assert result.level == "medium"
        assert result.recommendation == "notify"

    def test_uses_outcome_history(self) -> None:
        """Low historical success rate increases score."""
        outcomes = [
            _make_outcome(colony_id=f"c{i}", succeeded=False)
            for i in range(4)
        ]
        proj = _make_projections(outcomes)

        result_with = estimate_blast_radius(
            task="Fix a bug",
            caste="coder",
            max_rounds=3,
            strategy="sequential",
            workspace_id="ws1",
            projections=proj,
        )
        result_without = estimate_blast_radius(
            task="Fix a bug",
            caste="coder",
            max_rounds=3,
            strategy="sequential",
        )
        assert result_with.score > result_without.score

    def test_score_clamped_to_1(self) -> None:
        """Score is never above 1.0 even with many risk factors."""
        long_task = "delete database schema deploy production auth security " * 20
        result = estimate_blast_radius(
            task=long_task,
            caste="coder",
            max_rounds=10,
            strategy="stigmergic",
        )
        assert result.score <= 1.0

    def test_factors_populated(self) -> None:
        """Factors list explains what contributed to the score."""
        result = estimate_blast_radius(
            task="delete the database",
            caste="coder",
            max_rounds=2,
        )
        assert any("delete" in f.lower() for f in result.factors)
        assert any("coder" in f.lower() for f in result.factors)


# ---------------------------------------------------------------------------
# Track 9: Graduated Autonomy Scoring
# ---------------------------------------------------------------------------


class TestComputeAutonomyScore:
    def test_no_outcomes(self) -> None:
        """Empty outcome history -> score 0, grade F."""
        proj = _make_projections([])
        result = compute_autonomy_score("ws1", proj)
        assert isinstance(result, AutonomyScore)
        assert result.score == 0
        assert result.grade == "F"
        assert "No outcome history" in result.recommendation

    def test_perfect_track_record(self) -> None:
        """All successes, many colonies, low cost, positive trust -> A."""
        outcomes = [
            _make_outcome(colony_id=f"c{i}", total_cost=0.02)
            for i in range(30)
        ]
        proj = _make_projections(
            outcomes,
            acted_on={"coverage": 10, "staleness": 5},
            kills=0,
        )
        result = compute_autonomy_score("ws1", proj)
        assert result.score >= 80
        assert result.grade == "A"

    def test_mixed_results(self) -> None:
        """50% success, moderate volume -> C or D."""
        outcomes = [
            _make_outcome(colony_id=f"c{i}", succeeded=(i % 2 == 0))
            for i in range(10)
        ]
        proj = _make_projections(outcomes, acted_on={"coverage": 3}, kills=3)
        result = compute_autonomy_score("ws1", proj)
        assert result.score < 80
        # With 50% success, moderate volume, 50/50 trust: should be C or D
        assert result.grade in ("C", "D")

    def test_components_present(self) -> None:
        """All four components are returned."""
        outcomes = [_make_outcome()]
        proj = _make_projections(outcomes)
        result = compute_autonomy_score("ws1", proj)
        assert "success_rate" in result.components
        assert "volume" in result.components
        assert "cost_efficiency" in result.components
        assert "operator_trust" in result.components

    def test_wrong_workspace_ignored(self) -> None:
        """Outcomes from other workspaces are ignored."""
        outcomes = [_make_outcome(workspace_id="ws_other")]
        proj = _make_projections(outcomes)
        result = compute_autonomy_score("ws1", proj)
        assert result.score == 0


# ---------------------------------------------------------------------------
# Track 7: check_autonomy_budget Queen tool
# ---------------------------------------------------------------------------


class TestCheckAutonomyBudget:
    def test_returns_budget_status(self) -> None:
        """Tool returns daily budget info and autonomy level."""
        from formicos.surface.queen_tools import QueenToolDispatcher

        runtime = _make_runtime_with_workspace(
            policy={
                "autonomy_level": "auto_notify",
                "daily_maintenance_budget": 5.0,
                "auto_actions": ["coverage", "staleness"],
            },
            outcomes=[_make_outcome()],
            daily_spend=1.50,
        )

        dispatcher = QueenToolDispatcher(runtime)
        result_text, _action = dispatcher._check_autonomy_budget(
            {}, "ws1", "t1",
        )

        assert "auto_notify" in result_text
        assert "$5.00" in result_text  # daily budget
        assert "$1.50" in result_text  # spent today
        assert "$3.50" in result_text  # remaining
        assert "Autonomy Score" in result_text

    def test_budget_exhausted_message(self) -> None:
        """When daily spend equals budget, show exhausted warning."""
        from formicos.surface.queen_tools import QueenToolDispatcher

        runtime = _make_runtime_with_workspace(
            policy={"daily_maintenance_budget": 2.0},
            daily_spend=2.0,
        )

        dispatcher = QueenToolDispatcher(runtime)
        result_text, _ = dispatcher._check_autonomy_budget({}, "ws1", "t1")

        assert "exhausted" in result_text.lower()

    def test_blast_radius_in_output_when_task_provided(self) -> None:
        """When task is provided, blast radius estimate is included."""
        from formicos.surface.queen_tools import QueenToolDispatcher

        runtime = _make_runtime_with_workspace(
            outcomes=[_make_outcome()],
        )

        dispatcher = QueenToolDispatcher(runtime)
        result_text, _ = dispatcher._check_autonomy_budget(
            {"task": "delete the database schema"},
            "ws1", "t1",
        )

        assert "Blast Radius Estimate" in result_text
        assert "Score:" in result_text

    def test_workspace_not_found(self) -> None:
        """Returns error when workspace doesn't exist."""
        from formicos.surface.queen_tools import QueenToolDispatcher

        runtime = _make_runtime_with_workspace()
        runtime.projections.workspaces = {}

        dispatcher = QueenToolDispatcher(runtime)
        result_text, _ = dispatcher._check_autonomy_budget({}, "ws1", "t1")

        assert "not found" in result_text.lower()


# ---------------------------------------------------------------------------
# Track 8: Blast radius blocks dispatch
# ---------------------------------------------------------------------------


class TestBlastRadiusDispatchGate:
    @pytest.mark.anyio()
    async def test_high_blast_radius_blocks_dispatch(self) -> None:
        """Autonomous dispatch is skipped when blast radius is 'escalate'."""
        from formicos.addons.proactive_intelligence.rules import (
            KnowledgeInsight,
            SuggestedColony,
        )
        from formicos.surface.self_maintenance import MaintenanceDispatcher

        runtime = MagicMock()
        # Build workspace with autonomous policy
        ws = SimpleNamespace(
            config={
                "maintenance_policy": json.dumps({
                    "autonomy_level": "autonomous",
                    "daily_maintenance_budget": 10.0,
                    "auto_actions": ["coverage"],
                }),
            },
        )
        runtime.projections.workspaces = {"ws1": ws}
        runtime.projections.colonies = MagicMock()
        runtime.projections.colonies.values = MagicMock(return_value=[])
        runtime.projections.colony_outcomes = {}
        runtime.projections.operator_behavior = MagicMock()
        runtime.projections.operator_behavior.suggestion_categories_acted_on = {}
        runtime.projections.operator_behavior.kill_records = []

        # outcome_stats returns empty
        runtime.projections.outcome_stats = MagicMock(return_value=[])

        dispatcher = MaintenanceDispatcher(runtime)
        runtime.spawn_colony = AsyncMock(return_value="new_colony")

        # Create a high-risk insight
        long_task = (
            "Delete all database tables and migrate the schema to new format. "
            "Refactor authentication module and deploy to production. " * 5
        )
        from formicos.addons.proactive_intelligence.rules import ProactiveBriefing

        briefing = ProactiveBriefing(
            workspace_id="ws1",
            generated_at="2026-03-26T00:00:00Z",
            total_entries=10,
            entries_by_status={"verified": 5, "candidate": 5},
            avg_confidence=0.7,
            prediction_error_rate=0.1,
            active_clusters=2,
            insights=[
                KnowledgeInsight(
                    severity="attention",
                    category="coverage",
                    title="High-risk task",
                    detail="Test",
                    affected_entries=[],
                    suggested_action="Check",
                    suggested_colony=SuggestedColony(
                        task=long_task,
                        caste="coder",
                        strategy="stigmergic",
                        max_rounds=8,
                        rationale="Test",
                        estimated_cost=0.50,
                    ),
                ),
            ],
        )

        dispatched = await dispatcher.evaluate_and_dispatch("ws1", briefing)
        # Colony should NOT be spawned due to high blast radius
        assert len(dispatched) == 0
        runtime.spawn_colony.assert_not_called()

    @pytest.mark.anyio()
    async def test_low_blast_radius_allows_dispatch(self) -> None:
        """Autonomous dispatch proceeds when blast radius is low."""
        from formicos.addons.proactive_intelligence.rules import (
            KnowledgeInsight,
            ProactiveBriefing,
            SuggestedColony,
        )
        from formicos.surface.self_maintenance import MaintenanceDispatcher

        runtime = MagicMock()
        ws = SimpleNamespace(
            config={
                "maintenance_policy": json.dumps({
                    "autonomy_level": "autonomous",
                    "daily_maintenance_budget": 10.0,
                }),
            },
        )
        runtime.projections.workspaces = {"ws1": ws}
        runtime.projections.colonies = MagicMock()
        runtime.projections.colonies.values = MagicMock(return_value=[])
        runtime.projections.colony_outcomes = {}
        runtime.projections.operator_behavior = MagicMock()
        runtime.projections.operator_behavior.suggestion_categories_acted_on = {}
        runtime.projections.operator_behavior.kill_records = []
        runtime.projections.outcome_stats = MagicMock(return_value=[])

        dispatcher = MaintenanceDispatcher(runtime)
        runtime.spawn_colony = AsyncMock(return_value="new_colony")

        briefing = ProactiveBriefing(
            workspace_id="ws1",
            generated_at="2026-03-26T00:00:00Z",
            total_entries=10,
            entries_by_status={"verified": 5, "candidate": 5},
            avg_confidence=0.7,
            prediction_error_rate=0.1,
            active_clusters=2,
            insights=[
                KnowledgeInsight(
                    severity="info",
                    category="staleness",
                    title="Check coverage",
                    detail="Test",
                    affected_entries=[],
                    suggested_action="Check",
                    suggested_colony=SuggestedColony(
                        task="Check test coverage",
                        caste="researcher",
                        strategy="sequential",
                        max_rounds=2,
                        rationale="Test",
                        estimated_cost=0.10,
                    ),
                ),
            ],
        )

        dispatched = await dispatcher.evaluate_and_dispatch("ws1", briefing)
        assert len(dispatched) == 1
        runtime.spawn_colony.assert_called_once()


# ---------------------------------------------------------------------------
# Track 8: Proposal metadata carries blast-radius truth
# ---------------------------------------------------------------------------


class TestProposalMetadata:
    def test_propose_plan_carries_blast_radius(self) -> None:
        """The action dict from _propose_plan includes blast_radius and autonomy_score."""
        from formicos.surface.queen_tools import QueenToolDispatcher

        runtime = _make_runtime_with_workspace(
            outcomes=[_make_outcome()],
        )
        runtime.settings.system.data_dir = ""
        runtime.settings.governance.max_rounds_per_colony = 20
        runtime.settings.models.defaults.coder = "local/qwen3"
        runtime.settings.models.registry = []

        dispatcher = QueenToolDispatcher(runtime)

        # Call _propose_plan directly (sync part only)
        result_text, action = dispatcher._propose_plan(
            {
                "summary": "Add unit tests for auth module",
                "options": [],
                "questions": [],
                "recommendation": "Sequential coder colony",
            },
            "ws1",
            "t1",
        )

        assert action is not None
        assert "blast_radius" in action
        br = action["blast_radius"]
        assert "score" in br
        assert "level" in br
        assert "factors" in br
        assert "recommendation" in br

        assert "autonomy_score" in action
        auto = action["autonomy_score"]
        assert "score" in auto
        assert "grade" in auto
        assert "components" in auto


# ---------------------------------------------------------------------------
# Track 9: Autonomy status endpoint
# ---------------------------------------------------------------------------


class TestAutonomyStatusEndpoint:
    def test_autonomy_status_response_shape(self) -> None:
        """Autonomy status computation returns expected shape."""
        # Test the scoring/budget logic that the endpoint would return,
        # without needing the full Starlette route wiring.
        from formicos.surface.self_maintenance import compute_autonomy_score

        runtime = _make_runtime_with_workspace(
            policy={
                "autonomy_level": "auto_notify",
                "daily_maintenance_budget": 5.0,
                "auto_actions": ["coverage"],
                "max_maintenance_colonies": 3,
            },
            outcomes=[_make_outcome()],
            daily_spend=1.20,
        )

        # Simulate what the endpoint does
        ws = runtime.projections.workspaces["ws1"]
        raw_policy = ws.config.get("maintenance_policy")

        from formicos.core.types import MaintenancePolicy

        policy = MaintenancePolicy(**json.loads(raw_policy))

        dispatcher = runtime.maintenance_dispatcher
        daily_spend = dispatcher._daily_spend.get("ws1", 0.0)
        remaining = max(0.0, policy.daily_maintenance_budget - daily_spend)

        auto_score = compute_autonomy_score("ws1", runtime.projections)

        data = {
            "level": str(policy.autonomy_level),
            "score": auto_score.score,
            "grade": auto_score.grade,
            "daily_budget": policy.daily_maintenance_budget,
            "daily_spend": round(daily_spend, 4),
            "remaining": round(remaining, 4),
            "components": auto_score.components,
            "recommendation": auto_score.recommendation,
            "auto_actions": policy.auto_actions,
            "recent_actions": [],
        }

        assert data["level"] == "auto_notify"
        assert data["daily_budget"] == 5.0
        assert data["daily_spend"] == 1.20
        assert data["remaining"] == 3.80
        assert "score" in data
        assert "grade" in data
        assert "components" in data
        assert "recommendation" in data
        assert "recent_actions" in data
        assert data["auto_actions"] == ["coverage"]
