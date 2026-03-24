"""Wave 43 Pillar 3: Budget truth, enforcement, and observability tests.

Tests cover:
- BudgetSnapshot accumulation
- Workspace-level budget truth from TokensConsumed events
- Colony-level budget truth from TokensConsumed events
- Model usage tracking per scope
- BudgetEnforcer spawn blocking
- BudgetEnforcer model downgrade
- BudgetEnforcer workspace hard stop and soft warning
- BudgetEnforcer budget summary
- OTel adapter no-op behavior when OTel is not installed
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from formicos.core.events import (
    AgentTurnStarted,
    ColonySpawned,
    ThreadCreated,
    TokensConsumed,
    WorkspaceCreated,
    WorkspaceConfigSnapshot,
)
from formicos.core.types import CasteSlot
from formicos.surface.projections import (
    BudgetSnapshot,
    ProjectionStore,
)
from formicos.surface.runtime import BudgetEnforcer

_NOW = datetime(2026, 3, 19, 12, 0, 0, tzinfo=UTC)
_WS_ID = "test-ws"
_TH_ID = "thread-1"
_COL_ID = "colony-abc"
_ADDR = f"{_WS_ID}/{_TH_ID}/{_COL_ID}"
_AGENT_ID = "agent-001"
_MODEL = "gemini/gemini-2.5-flash"
_CASTE = CasteSlot(caste="coder", count=1)


def _seq_gen():
    n = 0
    while True:
        n += 1
        yield n


def _make_store_with_colony(budget_limit: float = 50.0) -> ProjectionStore:
    """Create a ProjectionStore with one workspace, thread, colony, and agent."""
    store = ProjectionStore()
    seq = _seq_gen()
    store.apply(WorkspaceCreated(
        seq=next(seq), timestamp=_NOW, address=_WS_ID,
        name=_WS_ID,
        config=WorkspaceConfigSnapshot(budget=5.0, strategy="stigmergic"),
    ))
    # Set workspace budget limit
    ws = store.workspaces[_WS_ID]
    ws.budget_limit = budget_limit

    # Create thread so workspace_colonies() can find the colony
    store.apply(ThreadCreated(
        seq=next(seq), timestamp=_NOW, address=f"{_WS_ID}/{_TH_ID}",
        workspace_id=_WS_ID, name=_TH_ID,
        goal="test", expected_outputs=[],
    ))

    store.apply(ColonySpawned(
        seq=next(seq), timestamp=_NOW, address=_ADDR,
        thread_id=_TH_ID, task="test task",
        castes=[_CASTE], model_assignments={"coder": _MODEL},
        strategy="stigmergic",
        max_rounds=10, budget_limit=5.0,
        template_id="", input_sources=[], step_index=-1,
        target_files=[],
    ))
    store.apply(AgentTurnStarted(
        seq=next(seq), timestamp=_NOW, address=_ADDR,
        colony_id=_COL_ID, agent_id=_AGENT_ID,
        caste="coder", model=_MODEL,
        round_number=1,
    ))
    return store


# ---------------------------------------------------------------------------
# BudgetSnapshot unit tests
# ---------------------------------------------------------------------------


class TestBudgetSnapshot:
    def test_initial_state(self) -> None:
        bs = BudgetSnapshot()
        assert bs.total_cost == 0.0
        assert bs.total_tokens == 0
        assert bs.total_input_tokens == 0
        assert bs.total_output_tokens == 0
        assert bs.model_usage == {}

    def test_record_single_spend(self) -> None:
        bs = BudgetSnapshot()
        bs.record_token_spend("model-a", 100, 50, 0.005)
        assert bs.total_cost == pytest.approx(0.005)
        assert bs.total_input_tokens == 100
        assert bs.total_output_tokens == 50
        assert bs.total_tokens == 150
        assert "model-a" in bs.model_usage

    def test_record_multiple_models(self) -> None:
        bs = BudgetSnapshot()
        bs.record_token_spend("model-a", 100, 50, 0.005)
        bs.record_token_spend("model-b", 200, 100, 0.010)
        bs.record_token_spend("model-a", 50, 25, 0.002)
        assert bs.total_cost == pytest.approx(0.017)
        assert bs.total_input_tokens == 350
        assert bs.total_output_tokens == 175
        assert len(bs.model_usage) == 2
        assert bs.model_usage["model-a"]["cost"] == pytest.approx(0.007)
        assert bs.model_usage["model-b"]["input_tokens"] == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# Projection-level budget truth tests
# ---------------------------------------------------------------------------


class TestWorkspaceBudgetTruth:
    def test_tokens_consumed_updates_workspace_budget(self) -> None:
        store = _make_store_with_colony()
        store.apply(TokensConsumed(
            seq=100, timestamp=_NOW, address=_ADDR,
            agent_id=_AGENT_ID, model=_MODEL,
            input_tokens=500, output_tokens=200, cost=0.05,
        ))
        ws_budget = store.workspace_budget(_WS_ID)
        assert ws_budget is not None
        assert ws_budget.total_cost == pytest.approx(0.05)
        assert ws_budget.total_input_tokens == 500
        assert ws_budget.total_output_tokens == 200

    def test_multiple_events_accumulate(self) -> None:
        store = _make_store_with_colony()
        for i in range(5):
            store.apply(TokensConsumed(
                seq=100 + i, timestamp=_NOW, address=_ADDR,
                agent_id=_AGENT_ID, model=_MODEL,
                input_tokens=100, output_tokens=50, cost=0.01,
            ))
        ws_budget = store.workspace_budget(_WS_ID)
        assert ws_budget is not None
        assert ws_budget.total_cost == pytest.approx(0.05)
        assert ws_budget.total_tokens == 750

    def test_model_usage_tracked(self) -> None:
        store = _make_store_with_colony()
        store.apply(TokensConsumed(
            seq=100, timestamp=_NOW, address=_ADDR,
            agent_id=_AGENT_ID, model=_MODEL,
            input_tokens=100, output_tokens=50, cost=0.01,
        ))
        ws_budget = store.workspace_budget(_WS_ID)
        assert ws_budget is not None
        assert _MODEL in ws_budget.model_usage
        assert ws_budget.model_usage[_MODEL]["cost"] == pytest.approx(0.01)

    def test_unknown_workspace_returns_none(self) -> None:
        store = ProjectionStore()
        assert store.workspace_budget("nonexistent") is None

    def test_utilization_computed(self) -> None:
        store = _make_store_with_colony(budget_limit=10.0)
        store.apply(TokensConsumed(
            seq=100, timestamp=_NOW, address=_ADDR,
            agent_id=_AGENT_ID, model=_MODEL,
            input_tokens=100, output_tokens=50, cost=5.0,
        ))
        assert store.workspace_budget_utilization(_WS_ID) == pytest.approx(0.5)


class TestColonyBudgetTruth:
    def test_tokens_consumed_updates_colony_budget(self) -> None:
        store = _make_store_with_colony()
        store.apply(TokensConsumed(
            seq=100, timestamp=_NOW, address=_ADDR,
            agent_id=_AGENT_ID, model=_MODEL,
            input_tokens=300, output_tokens=100, cost=0.03,
        ))
        col_budget = store.colony_budget(_COL_ID)
        assert col_budget is not None
        assert col_budget.total_cost == pytest.approx(0.03)
        assert col_budget.total_input_tokens == 300
        assert col_budget.total_output_tokens == 100

    def test_unknown_colony_returns_none(self) -> None:
        store = ProjectionStore()
        assert store.colony_budget("nonexistent") is None

    def test_colony_and_workspace_both_updated(self) -> None:
        store = _make_store_with_colony()
        store.apply(TokensConsumed(
            seq=100, timestamp=_NOW, address=_ADDR,
            agent_id=_AGENT_ID, model=_MODEL,
            input_tokens=200, output_tokens=100, cost=0.02,
        ))
        ws_budget = store.workspace_budget(_WS_ID)
        col_budget = store.colony_budget(_COL_ID)
        assert ws_budget is not None
        assert col_budget is not None
        assert ws_budget.total_cost == col_budget.total_cost


# ---------------------------------------------------------------------------
# BudgetEnforcer tests
# ---------------------------------------------------------------------------


class TestBudgetEnforcerSpawnBlocking:
    def test_spawn_allowed_under_budget(self) -> None:
        store = _make_store_with_colony(budget_limit=50.0)
        enforcer = BudgetEnforcer(store)
        allowed, reason = enforcer.check_spawn_allowed(_WS_ID)
        assert allowed is True
        assert reason == "ok"

    def test_spawn_blocked_at_budget(self) -> None:
        store = _make_store_with_colony(budget_limit=10.0)
        # Burn the budget
        store.apply(TokensConsumed(
            seq=100, timestamp=_NOW, address=_ADDR,
            agent_id=_AGENT_ID, model=_MODEL,
            input_tokens=10000, output_tokens=5000, cost=10.0,
        ))
        enforcer = BudgetEnforcer(store)
        allowed, reason = enforcer.check_spawn_allowed(_WS_ID)
        assert allowed is False
        assert "exhausted" in reason

    def test_spawn_allowed_unknown_workspace(self) -> None:
        store = ProjectionStore()
        enforcer = BudgetEnforcer(store)
        allowed, reason = enforcer.check_spawn_allowed("unknown")
        assert allowed is True
        assert reason == "workspace_unknown"


class TestBudgetEnforcerModelDowngrade:
    def test_no_downgrade_under_threshold(self) -> None:
        store = _make_store_with_colony(budget_limit=100.0)
        enforcer = BudgetEnforcer(store)
        assert enforcer.check_model_downgrade(_WS_ID, 3.0) is False

    def test_downgrade_at_90_percent(self) -> None:
        store = _make_store_with_colony(budget_limit=10.0)
        store.apply(TokensConsumed(
            seq=100, timestamp=_NOW, address=_ADDR,
            agent_id=_AGENT_ID, model=_MODEL,
            input_tokens=10000, output_tokens=5000, cost=9.5,
        ))
        enforcer = BudgetEnforcer(store)
        assert enforcer.check_model_downgrade(_WS_ID, 3.0) is True

    def test_downgrade_low_colony_budget(self) -> None:
        store = _make_store_with_colony(budget_limit=100.0)
        enforcer = BudgetEnforcer(store)
        # Colony has only $0.30 remaining
        assert enforcer.check_model_downgrade(_WS_ID, 0.30) is True


class TestBudgetEnforcerHardStop:
    def test_no_stop_under_budget(self) -> None:
        store = _make_store_with_colony(budget_limit=50.0)
        enforcer = BudgetEnforcer(store)
        should_stop, _ = enforcer.check_workspace_hard_stop(_WS_ID)
        assert should_stop is False

    def test_hard_stop_at_100_percent(self) -> None:
        store = _make_store_with_colony(budget_limit=10.0)
        store.apply(TokensConsumed(
            seq=100, timestamp=_NOW, address=_ADDR,
            agent_id=_AGENT_ID, model=_MODEL,
            input_tokens=10000, output_tokens=5000, cost=10.0,
        ))
        enforcer = BudgetEnforcer(store)
        should_stop, reason = enforcer.check_workspace_hard_stop(_WS_ID)
        assert should_stop is True
        assert "exhausted" in reason

    def test_soft_warning_at_80_percent(self) -> None:
        store = _make_store_with_colony(budget_limit=10.0)
        store.apply(TokensConsumed(
            seq=100, timestamp=_NOW, address=_ADDR,
            agent_id=_AGENT_ID, model=_MODEL,
            input_tokens=10000, output_tokens=5000, cost=8.5,
        ))
        enforcer = BudgetEnforcer(store)
        should_stop, _ = enforcer.check_workspace_hard_stop(_WS_ID)
        assert should_stop is False
        # Warning should have been issued
        ws = store.workspaces[_WS_ID]
        assert ws.budget.warning_issued is True


class TestBudgetSummary:
    def test_summary_structure(self) -> None:
        store = _make_store_with_colony(budget_limit=50.0)
        store.apply(TokensConsumed(
            seq=100, timestamp=_NOW, address=_ADDR,
            agent_id=_AGENT_ID, model=_MODEL,
            input_tokens=500, output_tokens=200, cost=0.05,
        ))
        enforcer = BudgetEnforcer(store)
        summary = enforcer.budget_summary(_WS_ID)
        assert summary["workspace_id"] == _WS_ID
        assert summary["total_cost"] == pytest.approx(0.05)
        assert summary["budget_limit"] == 50.0
        assert summary["utilization"] == pytest.approx(0.001)
        assert len(summary["colonies"]) == 1
        assert summary["colonies"][0]["colony_id"] == _COL_ID

    def test_summary_unknown_workspace(self) -> None:
        store = ProjectionStore()
        enforcer = BudgetEnforcer(store)
        summary = enforcer.budget_summary("unknown")
        assert "error" in summary


# ---------------------------------------------------------------------------
# OTel adapter no-op tests
# ---------------------------------------------------------------------------


class TestOTelAdapterNoOp:
    def test_create_returns_disabled_when_no_otel(self) -> None:
        from formicos.adapters.telemetry_otel import OTelAdapter
        adapter = OTelAdapter(tracer=None, meter=None, enabled=False)
        assert adapter.enabled is False

    def test_record_methods_are_safe_when_disabled(self) -> None:
        from formicos.adapters.telemetry_otel import OTelAdapter
        adapter = OTelAdapter(tracer=None, meter=None, enabled=False)
        # These should all be no-ops, no exceptions
        adapter.record_llm_call("model", 100, 50, 0.01, 500)
        adapter.record_colony_lifecycle("col-1", "ws-1", 5000, "completed")
        adapter.record_replay(1000, 200)
        adapter.record_retrieval("ws-1", 10, 50)

    def test_start_span_returns_noop_context(self) -> None:
        from formicos.adapters.telemetry_otel import OTelAdapter
        adapter = OTelAdapter(tracer=None, meter=None, enabled=False)
        with adapter.start_span("test") as span:
            span.set_attribute("key", "value")
        # No exception = pass

    def test_timer_works(self) -> None:
        from formicos.adapters.telemetry_otel import OTelAdapter
        adapter = OTelAdapter(tracer=None, meter=None, enabled=False)
        timer = adapter.timer()
        elapsed = timer.elapsed_ms()
        assert elapsed >= 0
