"""Tests for Wave 60 Team A: temporal queries, semantic gate, cost truth."""

from __future__ import annotations

import pytest

from formicos.engine.context import build_budget_block
from formicos.surface.projections import BudgetSnapshot


# ---------------------------------------------------------------------------
# A3-S1: BudgetSnapshot.api_cost and .local_tokens
# ---------------------------------------------------------------------------


class TestBudgetSnapshotCostSplit:
    """BudgetSnapshot with mixed model_usage returns correct split."""

    def test_api_cost_cloud_only(self) -> None:
        snap = BudgetSnapshot()
        snap.record_token_spend("openai/gpt-4o", 1000, 500, 0.05)
        snap.record_token_spend("openai/gpt-4o-mini", 2000, 300, 0.01)
        assert snap.api_cost == pytest.approx(0.06)

    def test_api_cost_local_only(self) -> None:
        snap = BudgetSnapshot()
        snap.record_token_spend("llama-cpp/gpt-4", 5000, 2000, 0.0)
        snap.record_token_spend("llama-cpp/gpt-4", 3000, 1000, 0.0)
        assert snap.api_cost == 0.0

    def test_api_cost_mixed(self) -> None:
        snap = BudgetSnapshot()
        snap.record_token_spend("llama-cpp/gpt-4", 5000, 2000, 0.0)
        snap.record_token_spend("openai/gpt-4o", 1000, 500, 0.05)
        assert snap.api_cost == pytest.approx(0.05)

    def test_local_tokens_local_only(self) -> None:
        snap = BudgetSnapshot()
        snap.record_token_spend("llama-cpp/gpt-4", 5000, 2000, 0.0)
        snap.record_token_spend("llama-cpp/gpt-4", 3000, 1000, 0.0)
        assert snap.local_tokens == 11000

    def test_local_tokens_mixed(self) -> None:
        """Cloud model tokens are not counted as local."""
        snap = BudgetSnapshot()
        snap.record_token_spend("llama-cpp/gpt-4", 5000, 2000, 0.0)
        snap.record_token_spend("openai/gpt-4o", 1000, 500, 0.05)
        assert snap.local_tokens == 7000

    def test_local_tokens_cloud_only(self) -> None:
        snap = BudgetSnapshot()
        snap.record_token_spend("openai/gpt-4o", 1000, 500, 0.05)
        assert snap.local_tokens == 0

    def test_total_cost_unchanged(self) -> None:
        """total_cost still reflects all models."""
        snap = BudgetSnapshot()
        snap.record_token_spend("llama-cpp/gpt-4", 5000, 2000, 0.0)
        snap.record_token_spend("openai/gpt-4o", 1000, 500, 0.05)
        assert snap.total_cost == pytest.approx(0.05)
        assert snap.total_tokens == 8500


# ---------------------------------------------------------------------------
# A3-S2: BudgetEnforcer gates on api_cost
# ---------------------------------------------------------------------------


class TestBudgetEnforcerLocalOnly:
    """Pure-local workspace (api_cost == $0): enforcer NEVER fires.

    This is by-design — no money spent = no budget concern. Local models
    have $0 cost, so utilization is always 0% regardless of how many
    colonies run.
    """

    def _make_enforcer_and_workspace(self):  # noqa: ANN202
        from formicos.surface.projections import (
            ProjectionStore,
            WorkspaceProjection,
        )
        from formicos.surface.runtime import BudgetEnforcer

        store = ProjectionStore()
        ws = WorkspaceProjection(id="ws-1", name="test")
        ws.budget_limit = 5.0
        # Simulate 10 completed colonies — all local, total_cost stays $0
        for _ in range(10):
            ws.budget.record_token_spend("llama-cpp/gpt-4", 5000, 2000, 0.0)
        store.workspaces["ws-1"] = ws
        enforcer = BudgetEnforcer(store)
        return enforcer, ws

    def test_spawn_allowed_pure_local(self) -> None:
        enforcer, _ = self._make_enforcer_and_workspace()
        allowed, reason = enforcer.check_spawn_allowed("ws-1")
        assert allowed
        assert reason == "ok"

    def test_no_model_downgrade_pure_local(self) -> None:
        enforcer, _ = self._make_enforcer_and_workspace()
        assert not enforcer.check_model_downgrade("ws-1", 5.0)

    def test_no_hard_stop_pure_local(self) -> None:
        enforcer, _ = self._make_enforcer_and_workspace()
        should_stop, reason = enforcer.check_workspace_hard_stop("ws-1")
        assert not should_stop
        assert reason == ""

    def test_warn_fires_with_api_cost(self) -> None:
        """When api_cost approaches budget, warn fires."""
        from formicos.surface.projections import (
            ProjectionStore,
            WorkspaceProjection,
        )
        from formicos.surface.runtime import BudgetEnforcer

        store = ProjectionStore()
        ws = WorkspaceProjection(id="ws-1", name="test")
        ws.budget_limit = 5.0
        # Simulate API spend: $4.10 = 82% utilization (above 80% warn)
        ws.budget.record_token_spend("openai/gpt-4o", 10000, 5000, 4.10)
        store.workspaces["ws-1"] = ws
        enforcer = BudgetEnforcer(store)

        should_stop, _ = enforcer.check_workspace_hard_stop("ws-1")
        assert not should_stop
        # Warning should have been issued (check flag)
        assert ws.budget.warning_issued

    def test_hard_stop_fires_with_api_cost(self) -> None:
        """When api_cost >= budget, hard stop fires."""
        from formicos.surface.projections import (
            ProjectionStore,
            WorkspaceProjection,
        )
        from formicos.surface.runtime import BudgetEnforcer

        store = ProjectionStore()
        ws = WorkspaceProjection(id="ws-1", name="test")
        ws.budget_limit = 5.0
        ws.budget.record_token_spend("openai/gpt-4o", 50000, 20000, 5.10)
        store.workspaces["ws-1"] = ws
        enforcer = BudgetEnforcer(store)

        should_stop, reason = enforcer.check_workspace_hard_stop("ws-1")
        assert should_stop
        assert "API budget exhausted" in reason


# ---------------------------------------------------------------------------
# A3-S3: Budget block split display
# ---------------------------------------------------------------------------


class TestBudgetBlockSplitDisplay:
    """Budget block shows API Budget label and optional local tokens."""

    def test_api_budget_label(self) -> None:
        block = build_budget_block(
            budget_limit=5.0, total_cost=0.5,
            iteration=1, max_iterations=25,
            round_number=2, max_rounds=10,
        )
        assert "[API Budget: $4.50 remaining (90%)" in block

    def test_local_tokens_shown_when_nonzero(self) -> None:
        block = build_budget_block(
            budget_limit=5.0, total_cost=0.0,
            iteration=1, max_iterations=25,
            round_number=2, max_rounds=10,
            local_tokens=450_000,
        )
        assert "[API Budget: $5.00 remaining (100%)" in block
        assert "[Local: 450K tokens processed]" in block

    def test_local_tokens_hidden_when_zero(self) -> None:
        block = build_budget_block(
            budget_limit=5.0, total_cost=1.0,
            iteration=1, max_iterations=25,
            round_number=2, max_rounds=10,
            local_tokens=0,
        )
        assert "Local:" not in block

    def test_local_tokens_millions(self) -> None:
        block = build_budget_block(
            budget_limit=5.0, total_cost=0.0,
            iteration=1, max_iterations=25,
            round_number=2, max_rounds=10,
            local_tokens=2_500_000,
        )
        assert "[Local: 2.5M tokens processed]" in block

    def test_backward_compat_no_local_tokens_param(self) -> None:
        """Existing callers without local_tokens still work."""
        block = build_budget_block(
            budget_limit=5.0, total_cost=1.0,
            iteration=1, max_iterations=25,
            round_number=2, max_rounds=10,
        )
        assert "API Budget" in block
        assert "STATUS:" in block


# ---------------------------------------------------------------------------
# A2: Semantic preservation gate
# ---------------------------------------------------------------------------


class TestSemanticPreservationGate:
    """Cosine similarity helper used by semantic gate."""

    def test_cosine_identical(self) -> None:
        from formicos.surface.colony_manager import _cm_cosine_similarity

        assert _cm_cosine_similarity([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)

    def test_cosine_orthogonal(self) -> None:
        from formicos.surface.colony_manager import _cm_cosine_similarity

        assert _cm_cosine_similarity([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)

    def test_cosine_zero_vector(self) -> None:
        from formicos.surface.colony_manager import _cm_cosine_similarity

        assert _cm_cosine_similarity([0, 0, 0], [1, 0, 0]) == 0.0


# ---------------------------------------------------------------------------
# A1: Temporal query parameter
# ---------------------------------------------------------------------------


class TestTemporalQueryParam:
    """get_neighbors accepts valid_before kwarg."""

    @pytest.mark.asyncio
    async def test_get_neighbors_accepts_valid_before(self) -> None:
        """Smoke test: valid_before param is accepted without error."""
        from formicos.adapters.knowledge_graph import KnowledgeGraphAdapter

        kg = KnowledgeGraphAdapter(db_path=":memory:")

        # Add nodes and edge
        e1 = await kg.resolve_entity("entry-one", "Entry", "ws-1")
        e2 = await kg.resolve_entity("entry-two", "Entry", "ws-1")
        await kg.add_edge(e1, e2, "RELATED_TO", "ws-1")

        # Query with valid_before — should not raise
        neighbors = await kg.get_neighbors(
            e1, depth=1, valid_before="2099-01-01T00:00:00Z",
        )
        assert len(neighbors) >= 1

    @pytest.mark.asyncio
    async def test_valid_before_filters_recent_edges(self) -> None:
        """Edges created now are excluded by a past valid_before cutoff."""
        from formicos.adapters.knowledge_graph import KnowledgeGraphAdapter

        kg = KnowledgeGraphAdapter(db_path=":memory:")

        e1 = await kg.resolve_entity("entry-one", "Entry", "ws-1")
        e2 = await kg.resolve_entity("entry-two", "Entry", "ws-1")
        # Edge gets valid_at = now (2026)
        await kg.add_edge(e1, e2, "RELATED_TO", "ws-1")

        # Cutoff in 2000 excludes the edge created in 2026
        neighbors = await kg.get_neighbors(
            e1, depth=1, valid_before="2000-01-01T00:00:00Z",
        )
        assert len(neighbors) == 0
