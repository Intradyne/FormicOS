"""Wave 43 Pillar 4C: Property-based replay tests for budget truth.

Verifies fundamental event-sourcing invariants for the Wave 43 budget
projection system:

1. Replay idempotence: replaying the same events twice produces identical budget state
2. Prefix consistency: replaying a prefix of events produces a budget state that
   is a prefix of the full replay state
3. Budget monotonicity: total_cost and total_tokens never decrease
4. Workspace = sum of colonies: workspace budget equals aggregate of colony budgets
5. Operator event survival: budget state survives alongside operator overlay events
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

import pytest

from formicos.core.events import (
    AgentTurnStarted,
    ColonyCompleted,
    ColonySpawned,
    RoundCompleted,
    TokensConsumed,
    WorkspaceConfigSnapshot,
    WorkspaceCreated,
)
from formicos.core.types import CasteSlot
from formicos.surface.projections import ProjectionStore

_NOW = datetime(2026, 3, 19, 12, 0, 0, tzinfo=UTC)
_WS_ID = "replay-ws"
_TH_ID = "thread-1"
_COL_IDS = ["colony-r1", "colony-r2", "colony-r3"]
_AGENT_IDS = ["agent-r1", "agent-r2", "agent-r3"]
_MODELS = ["gemini/gemini-2.5-flash", "anthropic/claude-sonnet-4.6", "llama-cpp/gpt-4"]
_CASTE = CasteSlot(caste="coder", count=1)


def _build_event_sequence() -> list[Any]:
    """Build a realistic multi-colony event sequence for replay testing."""
    events: list[Any] = []
    seq = 0

    def _seq() -> int:
        nonlocal seq
        seq += 1
        return seq

    # Workspace
    events.append(WorkspaceCreated(
        seq=_seq(), timestamp=_NOW, address=_WS_ID,
        name=_WS_ID,
        config=WorkspaceConfigSnapshot(budget=5.0, strategy="stigmergic"),
    ))

    # Spawn 3 colonies
    for i, (col_id, agent_id, model) in enumerate(
        zip(_COL_IDS, _AGENT_IDS, _MODELS),
    ):
        addr = f"{_WS_ID}/{_TH_ID}/{col_id}"
        events.append(ColonySpawned(
            seq=_seq(), timestamp=_NOW, address=addr,
            thread_id=_TH_ID, task=f"Task {i+1}",
            castes=[_CASTE], model_assignments={"coder": model},
            strategy="stigmergic", max_rounds=10, budget_limit=5.0,
            template_id="", input_sources=[], step_index=-1,
            target_files=[],
        ))
        events.append(AgentTurnStarted(
            seq=_seq(), timestamp=_NOW, address=addr,
            colony_id=col_id, agent_id=agent_id,
            caste="coder", model=model,
            round_number=1,
        ))

    # Each colony consumes tokens across 2 rounds
    costs = [
        (0.01, 500, 200), (0.02, 1000, 400), (0.005, 300, 100),
        (0.015, 800, 300), (0.008, 400, 150), (0.03, 1500, 500),
    ]
    round_num = 1
    for i, (col_id, agent_id, model) in enumerate(
        zip(_COL_IDS, _AGENT_IDS, _MODELS),
    ):
        addr = f"{_WS_ID}/{_TH_ID}/{col_id}"
        for r in range(2):
            cost, inp, out = costs[i * 2 + r]
            events.append(TokensConsumed(
                seq=_seq(), timestamp=_NOW, address=addr,
                agent_id=agent_id, model=model,
                input_tokens=inp, output_tokens=out, cost=cost,
            ))
            events.append(RoundCompleted(
                seq=_seq(), timestamp=_NOW, address=addr,
                colony_id=col_id, round_number=r + 1,
                convergence=0.5 * (r + 1), cost=cost,
                duration_ms=2000 + r * 500,
            ))

    return events


# ---------------------------------------------------------------------------
# Property 1: Replay idempotence
# ---------------------------------------------------------------------------


class TestReplayIdempotence:
    """Replaying the same events from empty state must produce identical budget state."""

    def test_budget_idempotent(self) -> None:
        events = _build_event_sequence()

        store1 = ProjectionStore()
        store1.replay(events)

        store2 = ProjectionStore()
        store2.replay(events)

        b1 = store1.workspace_budget(_WS_ID)
        b2 = store2.workspace_budget(_WS_ID)
        assert b1 is not None and b2 is not None
        assert b1.total_cost == b2.total_cost
        assert b1.total_input_tokens == b2.total_input_tokens
        assert b1.total_output_tokens == b2.total_output_tokens
        assert b1.model_usage == b2.model_usage

    def test_colony_budgets_idempotent(self) -> None:
        events = _build_event_sequence()

        store1 = ProjectionStore()
        store1.replay(events)

        store2 = ProjectionStore()
        store2.replay(events)

        for col_id in _COL_IDS:
            c1 = store1.colony_budget(col_id)
            c2 = store2.colony_budget(col_id)
            assert c1 is not None and c2 is not None
            assert c1.total_cost == c2.total_cost
            assert c1.total_input_tokens == c2.total_input_tokens


# ---------------------------------------------------------------------------
# Property 2: Prefix consistency
# ---------------------------------------------------------------------------


class TestPrefixConsistency:
    """Replaying a prefix of events must produce budget state that is
    consistent with (less than or equal to) the full replay."""

    @pytest.mark.parametrize("prefix_len", [5, 10, 15])
    def test_prefix_budget_leq_full(self, prefix_len: int) -> None:
        events = _build_event_sequence()
        prefix_events = events[:prefix_len]

        full_store = ProjectionStore()
        full_store.replay(events)

        prefix_store = ProjectionStore()
        prefix_store.replay(prefix_events)

        full_budget = full_store.workspace_budget(_WS_ID)
        prefix_budget = prefix_store.workspace_budget(_WS_ID)

        if full_budget is None or prefix_budget is None:
            # If workspace not yet created in prefix, that's fine
            return

        assert prefix_budget.total_cost <= full_budget.total_cost
        assert prefix_budget.total_input_tokens <= full_budget.total_input_tokens
        assert prefix_budget.total_output_tokens <= full_budget.total_output_tokens


# ---------------------------------------------------------------------------
# Property 3: Budget monotonicity
# ---------------------------------------------------------------------------


class TestBudgetMonotonicity:
    """Budget totals must never decrease as events are applied."""

    def test_cost_never_decreases(self) -> None:
        events = _build_event_sequence()
        store = ProjectionStore()
        prev_cost = 0.0

        for event in events:
            store.apply(event)
            ws_budget = store.workspace_budget(_WS_ID)
            if ws_budget is not None:
                assert ws_budget.total_cost >= prev_cost
                prev_cost = ws_budget.total_cost

    def test_tokens_never_decrease(self) -> None:
        events = _build_event_sequence()
        store = ProjectionStore()
        prev_tokens = 0

        for event in events:
            store.apply(event)
            ws_budget = store.workspace_budget(_WS_ID)
            if ws_budget is not None:
                assert ws_budget.total_tokens >= prev_tokens
                prev_tokens = ws_budget.total_tokens


# ---------------------------------------------------------------------------
# Property 4: Workspace = sum of colonies
# ---------------------------------------------------------------------------


class TestWorkspaceAggregation:
    """Workspace budget must equal the sum of all colony budgets within it."""

    def test_workspace_cost_equals_colony_sum(self) -> None:
        events = _build_event_sequence()
        store = ProjectionStore()
        store.replay(events)

        ws_budget = store.workspace_budget(_WS_ID)
        assert ws_budget is not None

        colony_cost_sum = sum(
            (store.colony_budget(cid) or type("_", (), {"total_cost": 0.0})).total_cost
            for cid in _COL_IDS
        )
        assert ws_budget.total_cost == pytest.approx(colony_cost_sum)

    def test_workspace_tokens_equals_colony_sum(self) -> None:
        events = _build_event_sequence()
        store = ProjectionStore()
        store.replay(events)

        ws_budget = store.workspace_budget(_WS_ID)
        assert ws_budget is not None

        colony_input_sum = sum(
            (store.colony_budget(cid) or type("_", (), {"total_input_tokens": 0})).total_input_tokens
            for cid in _COL_IDS
        )
        colony_output_sum = sum(
            (store.colony_budget(cid) or type("_", (), {"total_output_tokens": 0})).total_output_tokens
            for cid in _COL_IDS
        )
        assert ws_budget.total_input_tokens == colony_input_sum
        assert ws_budget.total_output_tokens == colony_output_sum


# ---------------------------------------------------------------------------
# Property 5: Budget survives alongside operator events
# ---------------------------------------------------------------------------


class TestBudgetOperatorEventSurvival:
    """Budget state must be preserved when operator overlay events are applied.

    This guards against regression where non-budget event handlers might
    accidentally reset or corrupt budget state.
    """

    def test_budget_survives_colony_completion(self) -> None:
        events = _build_event_sequence()
        store = ProjectionStore()
        store.replay(events)

        pre_budget = copy.deepcopy(store.workspace_budget(_WS_ID))
        assert pre_budget is not None

        # Complete a colony
        addr = f"{_WS_ID}/{_TH_ID}/{_COL_IDS[0]}"
        store.apply(ColonyCompleted(
            seq=999, timestamp=_NOW, address=addr,
            colony_id=_COL_IDS[0], summary="Done",
            skills_extracted=0,
        ))

        post_budget = store.workspace_budget(_WS_ID)
        assert post_budget is not None
        assert post_budget.total_cost == pre_budget.total_cost
        assert post_budget.total_input_tokens == pre_budget.total_input_tokens
