"""Tests for round projection pipeline: PhaseEntered, AgentTurnCompleted,
RoundCompleted, and view_state round serialization."""

from __future__ import annotations

from datetime import UTC, datetime

from formicos.core.events import (
    AgentTurnCompleted,
    AgentTurnStarted,
    ColonySpawned,
    PhaseEntered,
    RoundCompleted,
    RoundStarted,
    ThreadCreated,
    WorkspaceConfigSnapshot,
    WorkspaceCreated,
)
from formicos.core.types import CasteSlot
from formicos.core.settings import load_config
from formicos.surface.projections import ProjectionStore
from formicos.surface.view_models import round_history
from formicos.surface.view_state import build_snapshot

NOW = datetime.now(UTC)
E = {"timestamp": NOW}


def _seed() -> ProjectionStore:
    """Workspace + thread + colony + round 1 started."""
    store = ProjectionStore()
    store.apply(WorkspaceCreated(
        seq=1, address="ws1", name="ws1",
        config=WorkspaceConfigSnapshot(budget=10.0, strategy="stigmergic"),
        **E,
    ))
    store.apply(ThreadCreated(
        seq=2, address="ws1/t1", workspace_id="ws1", name="t1", **E,
    ))
    store.apply(ColonySpawned(
        seq=3, address="ws1/t1/c1", thread_id="t1",
        task="fibonacci", castes=[CasteSlot(caste="coder")],
        model_assignments={"coder": "llama-cpp/gpt-4"},
        strategy="stigmergic", max_rounds=10, budget_limit=5.0,
        **E,
    ))
    store.apply(RoundStarted(
        seq=4, address="ws1/t1/c1", colony_id="c1", round_number=1, **E,
    ))
    return store


class TestPhaseEnteredHandler:
    def test_updates_round_phase(self) -> None:
        store = _seed()
        store.apply(PhaseEntered(
            seq=5, address="ws1/t1/c1",
            colony_id="c1", round_number=1, phase="execute",
            **E,
        ))
        colony = store.get_colony("c1")
        assert colony is not None
        rp = colony.round_records[0]
        assert rp.current_phase == "execute"

    def test_phase_updates_sequentially(self) -> None:
        store = _seed()
        for i, phase in enumerate(["goal", "intent", "route", "execute", "compress"]):
            store.apply(PhaseEntered(
                seq=5 + i, address="ws1/t1/c1",
                colony_id="c1", round_number=1, phase=phase,
                **E,
            ))
        colony = store.get_colony("c1")
        assert colony is not None
        assert colony.round_records[0].current_phase == "compress"

    def test_creates_round_if_missing(self) -> None:
        store = _seed()
        # PhaseEntered for round 2 before RoundStarted
        store.apply(PhaseEntered(
            seq=5, address="ws1/t1/c1",
            colony_id="c1", round_number=2, phase="goal",
            **E,
        ))
        colony = store.get_colony("c1")
        assert colony is not None
        assert len(colony.round_records) == 2
        assert colony.round_records[1].round_number == 2


class TestAgentTurnCompletedPopulatesRound:
    def test_records_output_and_tools(self) -> None:
        store = _seed()
        store.apply(AgentTurnStarted(
            seq=5, address="ws1/t1/c1",
            colony_id="c1", round_number=1,
            agent_id="coder-0", caste="coder", model="llama-cpp/gpt-4",
            **E,
        ))
        store.apply(AgentTurnCompleted(
            seq=6, address="ws1/t1/c1",
            agent_id="coder-0",
            output_summary="def fib(n): ...",
            input_tokens=100, output_tokens=50,
            tool_calls=["code_execute"],
            duration_ms=500,
            **E,
        ))
        colony = store.get_colony("c1")
        assert colony is not None
        rp = colony.round_records[0]
        assert rp.agent_outputs == {"coder-0": "def fib(n): ..."}
        assert rp.tool_calls == {"coder-0": ["code_execute"]}

    def test_multiple_agents_in_same_round(self) -> None:
        store = _seed()
        for aid, caste in [("coder-0", "coder"), ("reviewer-0", "reviewer")]:
            store.apply(AgentTurnStarted(
                seq=10, address="ws1/t1/c1",
                colony_id="c1", round_number=1,
                agent_id=aid, caste=caste, model="llama-cpp/gpt-4",
                **E,
            ))
            store.apply(AgentTurnCompleted(
                seq=11, address="ws1/t1/c1",
                agent_id=aid,
                output_summary=f"output from {aid}",
                input_tokens=50, output_tokens=25,
                tool_calls=[],
                duration_ms=300,
                **E,
            ))
        colony = store.get_colony("c1")
        assert colony is not None
        rp = colony.round_records[0]
        assert len(rp.agent_outputs) == 2
        assert "coder-0" in rp.agent_outputs
        assert "reviewer-0" in rp.agent_outputs

    def test_uses_event_address_to_disambiguate_duplicate_agent_ids(self) -> None:
        store = _seed()
        store.apply(ThreadCreated(
            seq=20, address="ws1/t2", workspace_id="ws1", name="t2", **E,
        ))
        store.apply(ColonySpawned(
            seq=21, address="ws1/t2/c2", thread_id="t2",
            task="second task", castes=[CasteSlot(caste="coder")],
            model_assignments={"coder": "llama-cpp/gpt-4"},
            strategy="stigmergic", max_rounds=10, budget_limit=5.0,
            **E,
        ))
        store.apply(RoundStarted(
            seq=22, address="ws1/t2/c2", colony_id="c2", round_number=1, **E,
        ))

        for seq, colony_id in [(23, "c1"), (25, "c2")]:
            store.apply(AgentTurnStarted(
                seq=seq, address=f"ws1/t{1 if colony_id == 'c1' else 2}/{colony_id}",
                colony_id=colony_id, round_number=1,
                agent_id="coder-0", caste="coder", model="llama-cpp/gpt-4",
                **E,
            ))
        store.apply(AgentTurnCompleted(
            seq=30, address="ws1/t2/c2",
            agent_id="coder-0",
            output_summary="only colony c2 should get this",
            input_tokens=10, output_tokens=5,
            tool_calls=[],
            duration_ms=100,
            **E,
        ))

        colony1 = store.get_colony("c1")
        colony2 = store.get_colony("c2")
        assert colony1 is not None
        assert colony2 is not None
        assert colony1.round_records[0].agent_outputs == {}
        assert colony2.round_records[0].agent_outputs == {
            "coder-0": "only colony c2 should get this"
        }


class TestRoundCompletedPreservesState:
    def test_preserves_agent_outputs_and_phase(self) -> None:
        store = _seed()
        store.apply(PhaseEntered(
            seq=5, address="ws1/t1/c1",
            colony_id="c1", round_number=1, phase="execute",
            **E,
        ))
        store.apply(AgentTurnStarted(
            seq=6, address="ws1/t1/c1",
            colony_id="c1", round_number=1,
            agent_id="coder-0", caste="coder", model="llama-cpp/gpt-4",
            **E,
        ))
        store.apply(AgentTurnCompleted(
            seq=7, address="ws1/t1/c1",
            agent_id="coder-0",
            output_summary="fib implementation",
            input_tokens=100, output_tokens=50,
            tool_calls=["code_execute"],
            duration_ms=500,
            **E,
        ))
        store.apply(RoundCompleted(
            seq=8, address="ws1/t1/c1",
            colony_id="c1", round_number=1,
            convergence=0.75, cost=0.12, duration_ms=1500,
            **E,
        ))
        colony = store.get_colony("c1")
        assert colony is not None
        assert len(colony.round_records) == 1
        rp = colony.round_records[0]
        # RoundCompleted merged into existing projection
        assert rp.convergence == 0.75
        assert rp.cost == 0.12
        assert rp.duration_ms == 1500
        # Earlier data preserved
        assert rp.current_phase == "execute"
        assert rp.agent_outputs == {"coder-0": "fib implementation"}
        assert rp.tool_calls == {"coder-0": ["code_execute"]}


class TestViewStateRounds:
    def test_snapshot_includes_round_detail(self) -> None:
        store = _seed()
        store.apply(PhaseEntered(
            seq=5, address="ws1/t1/c1",
            colony_id="c1", round_number=1, phase="execute",
            **E,
        ))
        store.apply(AgentTurnStarted(
            seq=6, address="ws1/t1/c1",
            colony_id="c1", round_number=1,
            agent_id="coder-0", caste="coder", model="llama-cpp/gpt-4",
            **E,
        ))
        store.apply(AgentTurnCompleted(
            seq=7, address="ws1/t1/c1",
            agent_id="coder-0",
            output_summary="fibonacci code",
            input_tokens=80, output_tokens=40,
            tool_calls=["code_execute", "test_run"],
            duration_ms=400,
            **E,
        ))
        store.apply(RoundCompleted(
            seq=8, address="ws1/t1/c1",
            colony_id="c1", round_number=1,
            convergence=0.65, cost=0.05, duration_ms=1200,
            **E,
        ))

        settings = load_config("config/formicos.yaml")
        snap = build_snapshot(store, settings)
        colony_node = snap["tree"][0]["children"][0]["children"][0]
        rounds = colony_node["rounds"]
        assert len(rounds) == 1
        r = rounds[0]
        assert r["roundNumber"] == 1
        assert r["phase"] == "execute"
        assert r["convergence"] == 0.65
        assert r["cost"] == 0.05
        assert r["durationMs"] == 1200
        assert len(r["agents"]) == 1
        agent_row = r["agents"][0]
        assert agent_row["id"] == "coder-0"
        assert agent_row["output"] == "fibonacci code"
        assert agent_row["toolCalls"] == ["code_execute", "test_run"]


class TestViewModelsRoundHistory:
    def test_round_history_includes_phase(self) -> None:
        store = _seed()
        store.apply(PhaseEntered(
            seq=5, address="ws1/t1/c1",
            colony_id="c1", round_number=1, phase="compress",
            **E,
        ))
        store.apply(RoundCompleted(
            seq=6, address="ws1/t1/c1",
            colony_id="c1", round_number=1,
            convergence=0.8, cost=0.1, duration_ms=1000,
            **E,
        ))
        history = round_history(store, "c1")
        assert len(history) == 1
        assert history[0]["phase"] == "compress"
        assert history[0]["convergence"] == 0.8
