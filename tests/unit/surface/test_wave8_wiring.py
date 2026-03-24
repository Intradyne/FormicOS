"""Tests for Wave 8 integration wiring — tier budgets + background state push."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from formicos.engine.context import TierBudgets as EngineTierBudgets
from formicos.surface.colony_manager import ColonyManager


def _make_colony(
    colony_id: str = "col-1",
    workspace_id: str = "ws-1",
    thread_id: str = "th-1",
    status: str = "running",
    max_rounds: int = 3,
    budget_limit: float = 5.0,
) -> MagicMock:
    colony = MagicMock()
    colony.id = colony_id
    colony.workspace_id = workspace_id
    colony.thread_id = thread_id
    colony.status = status
    colony.round_number = 0
    colony.max_rounds = max_rounds
    colony.task = "test task"
    colony.strategy = "sequential"
    colony.castes = [{"caste": "coder", "tier": "standard", "count": 1}]
    colony.model_assignments = {}
    colony.budget_limit = budget_limit
    colony.quality_score = 0.0
    colony.skills_extracted = 0
    return colony


def _make_runtime(colony: Any = None) -> MagicMock:
    runtime = MagicMock()
    runtime.emit_and_broadcast = AsyncMock(return_value=1)
    runtime.embed_fn = None
    runtime.vector_store = None
    runtime.cost_fn = lambda m, i, o: 0.0
    runtime.ws_manager.send_state_to_workspace = AsyncMock()

    # Settings with context config
    runtime.settings.routing.tau_threshold = 0.35
    runtime.settings.routing.k_in_cap = 5
    runtime.settings.context.tier_budgets.goal = 500
    runtime.settings.context.tier_budgets.routed_outputs = 1500
    runtime.settings.context.tier_budgets.max_per_source = 500
    runtime.settings.context.tier_budgets.merge_summaries = 500
    runtime.settings.context.tier_budgets.prev_round_summary = 500
    runtime.settings.context.tier_budgets.skill_bank = 800
    runtime.settings.context.compaction_threshold = 500

    runtime.build_agents.return_value = []
    # Wave 28: knowledge catalog methods
    runtime.fetch_knowledge_for_colony = AsyncMock(return_value=[])
    runtime.make_catalog_search_fn = MagicMock(return_value=None)
    runtime.make_knowledge_detail_fn = MagicMock(return_value=None)
    runtime.make_artifact_inspect_fn = MagicMock(return_value=None)

    if colony is not None:
        runtime.projections.get_colony.return_value = colony
    else:
        runtime.projections.get_colony.return_value = None

    runtime.projections.colonies = {}
    return runtime


# ---------------------------------------------------------------------------
# Gap 1: Tier budgets wired through to RoundRunner
# ---------------------------------------------------------------------------


class TestTierBudgetWiring:
    """Verify tier budgets flow from settings → colony_manager → RoundRunner."""

    @pytest.mark.anyio()
    async def test_runner_receives_tier_budgets(self) -> None:
        """RoundRunner is constructed with tier_budgets from settings."""
        colony = _make_colony()
        runtime = _make_runtime(colony=colony)
        runtime.build_agents.return_value = [MagicMock()]
        runtime.llm_router = MagicMock()
        runtime.llm_router.route = MagicMock(return_value="test-model")
        runtime.resolve_model = MagicMock(return_value="test-model")
        manager = ColonyManager(runtime)

        runner_init_args: dict[str, Any] = {}

        original_init = MagicMock()

        captured_callbacks: list[Any] = []

        def capture_runner(
            callbacks: Any, **kwargs: Any,
        ) -> MagicMock:
            captured_callbacks.append(callbacks)
            mock_runner = MagicMock()
            # run_round must return an awaitable with expected structure
            result = MagicMock()
            result.updated_weights = {}
            result.round_summary = "done"
            result.cost = 0.0
            result.convergence.score = 0.9
            result.convergence.is_stalled = False
            result.governance.action = "complete"
            result.governance.reason = "converged"
            result.retrieved_skill_ids = []
            result.stall_count = 0
            result.productive_calls = 0
            result.total_calls = 0
            result.outputs = {}
            mock_runner.run_round = AsyncMock(return_value=result)
            return mock_runner

        with patch(
            "formicos.surface.colony_manager.RoundRunner",
            side_effect=capture_runner,
        ):
            await manager._run_colony_inner(colony.id)

        assert len(captured_callbacks) == 1
        cb = captured_callbacks[0]
        assert cb.tier_budgets is not None
        assert cb.route_fn is not None
        tb = cb.tier_budgets
        assert isinstance(tb, EngineTierBudgets)
        assert tb.goal == 500
        assert tb.compaction_threshold == 500


# ---------------------------------------------------------------------------
# Gap 2: Background colony pushes state snapshot on exit
# ---------------------------------------------------------------------------


class TestBackgroundStatePush:
    """Verify background colony completion triggers workspace state refresh."""

    @pytest.mark.anyio()
    async def test_state_pushed_after_no_agents(self) -> None:
        """Colony with no agents still pushes state on exit."""
        colony = _make_colony()
        runtime = _make_runtime(colony=colony)
        runtime.build_agents.return_value = []  # no agents
        manager = ColonyManager(runtime)

        await manager._run_colony(colony.id)

        runtime.ws_manager.send_state_to_workspace.assert_awaited_once_with("ws-1")

    @pytest.mark.anyio()
    async def test_state_pushed_after_completion(self) -> None:
        """Completed colony pushes state to workspace subscribers."""
        colony = _make_colony()
        runtime = _make_runtime(colony=colony)
        runtime.build_agents.return_value = [MagicMock()]
        runtime.llm_router.route = MagicMock(return_value="test-model")
        runtime.resolve_model = MagicMock(return_value="test-model")
        manager = ColonyManager(runtime)

        result = MagicMock()
        result.updated_weights = {}
        result.round_summary = "done"
        result.cost = 0.0
        result.convergence.score = 0.95
        result.convergence.is_stalled = False
        result.governance.action = "complete"
        result.governance.reason = "converged"
        result.retrieved_skill_ids = []
        result.stall_count = 0
        result.productive_calls = 0
        result.total_calls = 0
        result.outputs = {}

        mock_runner = MagicMock()
        mock_runner.run_round = AsyncMock(return_value=result)

        with patch(
            "formicos.surface.colony_manager.RoundRunner",
            return_value=mock_runner,
        ):
            await manager._run_colony(colony.id)

        # Mid-round push + final push = at least 2 calls, all for same workspace
        calls = runtime.ws_manager.send_state_to_workspace.await_args_list
        assert len(calls) >= 2
        assert all(c.args == ("ws-1",) for c in calls)

    @pytest.mark.anyio()
    async def test_state_pushed_after_error(self) -> None:
        """Even if the round loop raises, state is pushed."""
        colony = _make_colony()
        runtime = _make_runtime(colony=colony)
        runtime.build_agents.return_value = [MagicMock()]
        runtime.llm_router.route = MagicMock(return_value="test-model")
        runtime.resolve_model = MagicMock(return_value="test-model")
        manager = ColonyManager(runtime)

        mock_runner = MagicMock()
        mock_runner.run_round = AsyncMock(side_effect=RuntimeError("boom"))

        with patch(
            "formicos.surface.colony_manager.RoundRunner",
            return_value=mock_runner,
        ):
            await manager._run_colony(colony.id)

        runtime.ws_manager.send_state_to_workspace.assert_awaited_once_with("ws-1")
