"""Tests for the colony round runner."""

from __future__ import annotations

import pytest

from formicos.core.events import (
    AgentTurnCompleted,
    AgentTurnStarted,
    ColonyChatMessage,
    PhaseEntered,
)
from formicos.core.types import AgentConfig, CasteRecipe, ColonyContext, LLMResponse
from formicos.engine.runner import (
    ConvergenceResult,
    RoundRunner,
    RunnerCallbacks,
    ToolExecutionResult,
    _detect_completion_signal,
)
from formicos.engine.strategies.sequential import SequentialStrategy

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _recipe(name: str = "coder") -> CasteRecipe:
    return CasteRecipe(
        name=name,
        description=f"{name} caste",
        system_prompt=f"You are a {name}.",
        temperature=0.0,
        tools=[],
        max_tokens=1024,
    )


def _agent(agent_id: str, name: str = "coder") -> AgentConfig:
    return AgentConfig(
        id=agent_id, name=agent_id, caste=name,
        model="test-model", recipe=_recipe(name),
    )


def _colony_ctx(round_number: int = 1) -> ColonyContext:
    return ColonyContext(
        colony_id="col-1", workspace_id="ws-1", thread_id="th-1",
        goal="Build a widget", round_number=round_number,
        merge_edges=[],
    )


class MockLLMPort:
    def __init__(
        self, response_content: str = "Test output",
        tool_calls: list[dict[str, object]] | None = None,
        tool_call_rounds: int = 1,
    ) -> None:
        self._content = response_content
        self._tool_calls: list[dict[str, object]] = tool_calls or []
        self._tool_call_rounds = tool_call_rounds
        self._call_count = 0

    async def complete(
        self, model, messages, tools=None, temperature=0.0, max_tokens=4096,
        tool_choice=None,
    ) -> LLMResponse:
        self._call_count += 1
        # Return tool_calls only for the first N calls
        tc = self._tool_calls if self._call_count <= self._tool_call_rounds else []
        return LLMResponse(
            content=self._content, tool_calls=tc,
            input_tokens=100, output_tokens=50,
            model=model, stop_reason="end_turn",
        )

    async def stream(self, model, messages, tools=None, temperature=0.0, max_tokens=4096):
        from formicos.core.types import LLMChunk
        yield LLMChunk(content=self._content, is_final=True)


class MockEventStore:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def append(self, event: object) -> int:
        self.events.append(event)
        return len(self.events)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_round_emits_phase_sequence() -> None:
    store = MockEventStore()
    runner = RoundRunner(RunnerCallbacks(emit=store.append))
    agents = [_agent("a1")]
    strategy = SequentialStrategy()

    await runner.run_round(
        colony_context=_colony_ctx(),
        agents=agents,
        strategy=strategy,
        llm_port=MockLLMPort(),
        vector_port=None,
        event_store_address="ws-1/th-1/col-1",
    )

    types_seen = [type(e).__name__ for e in store.events]
    assert types_seen[0] == "RoundStarted"
    # 5 PhaseEntered events: goal, intent, route, execute, compress
    phase_events = [e for e in store.events if isinstance(e, PhaseEntered)]
    assert [e.phase for e in phase_events] == [
        "goal", "intent", "route", "execute", "compress",
    ]
    assert types_seen[-1] == "RoundCompleted"


@pytest.mark.asyncio
async def test_run_round_sequential() -> None:
    store = MockEventStore()
    runner = RoundRunner(RunnerCallbacks(emit=store.append))
    agents = [_agent("a1"), _agent("a2")]
    strategy = SequentialStrategy()

    await runner.run_round(
        colony_context=_colony_ctx(),
        agents=agents,
        strategy=strategy,
        llm_port=MockLLMPort(),
        vector_port=None,
        event_store_address="ws-1/th-1/col-1",
    )

    turn_starts = [e for e in store.events if isinstance(e, AgentTurnStarted)]
    assert [e.agent_id for e in turn_starts] == ["a1", "a2"]


@pytest.mark.asyncio
async def test_run_round_returns_result() -> None:
    store = MockEventStore()
    runner = RoundRunner(RunnerCallbacks(emit=store.append))
    agents = [_agent("a1")]
    strategy = SequentialStrategy()

    result = await runner.run_round(
        colony_context=_colony_ctx(),
        agents=agents,
        strategy=strategy,
        llm_port=MockLLMPort(response_content="hello world"),
        vector_port=None,
        event_store_address="ws-1/th-1/col-1",
    )

    assert result.round_number == 1
    assert result.convergence.score > 0
    assert "a1" in result.outputs
    assert result.outputs["a1"] == "hello world"
    assert isinstance(result.updated_weights, dict)


@pytest.mark.asyncio
async def test_governance_continue() -> None:
    store = MockEventStore()
    runner = RoundRunner(RunnerCallbacks(emit=store.append))
    agents = [_agent("a1")]
    strategy = SequentialStrategy()

    result = await runner.run_round(
        colony_context=_colony_ctx(round_number=1),
        agents=agents,
        strategy=strategy,
        llm_port=MockLLMPort(),
        vector_port=None,
        event_store_address="ws-1/th-1/col-1",
    )

    assert result.governance.action == "continue"


@pytest.mark.asyncio
async def test_governance_warn_on_carried_stall_streak() -> None:
    """Runner should warn once the carried stall streak reaches 2 rounds."""
    store = MockEventStore()
    def fake_embed(_texts: list[str]) -> list[list[float]]:
        return [
            [1.0, 0.0],      # goal
            [0.1, 0.995],    # current
            [0.1, 0.995],    # previous (identical -> stalled)
        ]

    runner = RoundRunner(RunnerCallbacks(emit=store.append, embed_fn=fake_embed))
    agents = [_agent("a1")]
    strategy = SequentialStrategy()

    ctx = _colony_ctx(round_number=3).model_copy(update={
        "prev_round_summary": "a1: Stable output repeated with no completion marker.",
    })
    result = await runner.run_round(
        colony_context=ctx,
        agents=agents,
        strategy=strategy,
        llm_port=MockLLMPort(
            response_content="Stable output repeated with no completion marker.",
        ),
        vector_port=None,
        event_store_address="ws-1/th-1/col-1",
        prior_stall_count=1,
    )

    assert result.convergence.is_stalled
    assert result.stall_count == 2
    assert result.governance.action == "warn"
    assert result.governance.reason == "stalled 2+ rounds"

    warning_chats = [
        e for e in store.events
        if isinstance(e, ColonyChatMessage)
        and e.event_kind == "governance"
        and "Governance warning" in e.content
    ]
    assert len(warning_chats) == 1


@pytest.mark.asyncio
async def test_governance_force_halt_on_carried_stall_streak() -> None:
    """Runner should force-halt once the carried stall streak reaches 4 rounds."""
    store = MockEventStore()
    def fake_embed(_texts: list[str]) -> list[list[float]]:
        return [
            [1.0, 0.0],      # goal
            [0.1, 0.995],    # current
            [0.1, 0.995],    # previous (identical -> stalled)
        ]

    runner = RoundRunner(RunnerCallbacks(emit=store.append, embed_fn=fake_embed))
    agents = [_agent("a1")]
    strategy = SequentialStrategy()

    ctx = _colony_ctx(round_number=5).model_copy(update={
        "prev_round_summary": "a1: Stable output repeated with no completion marker.",
    })
    result = await runner.run_round(
        colony_context=ctx,
        agents=agents,
        strategy=strategy,
        llm_port=MockLLMPort(
            response_content="Stable output repeated with no completion marker.",
        ),
        vector_port=None,
        event_store_address="ws-1/th-1/col-1",
        prior_stall_count=3,
    )

    assert result.convergence.is_stalled
    assert result.stall_count == 4
    assert result.governance.action == "force_halt"
    assert result.governance.reason == "stalled 4+ rounds"


@pytest.mark.asyncio
async def test_successful_code_execute_sets_recent_verified_signal() -> None:
    """A successful code_execute should carry a completion hint into later rounds."""
    store = MockEventStore()

    async def successful_code_execute(*_args) -> ToolExecutionResult:
        return ToolExecutionResult(
            content="tests passed",
            code_execute_succeeded=True,
        )

    runner = RoundRunner(RunnerCallbacks(
        emit=store.append,
        code_execute_handler=successful_code_execute,
    ))
    agents = [_agent("a1")]
    strategy = SequentialStrategy()

    result = await runner.run_round(
        colony_context=_colony_ctx(round_number=1),
        agents=agents,
        strategy=strategy,
        llm_port=MockLLMPort(
            response_content="Implementation complete.",
            tool_calls=[{"name": "code_execute", "input": {"code": "print('ok')"}}],
            tool_call_rounds=1,
        ),
        vector_port=None,
        event_store_address="ws-1/th-1/col-1",
    )

    assert result.recent_successful_code_execute


@pytest.mark.asyncio
async def test_verified_execution_reclassifies_stall_to_complete() -> None:
    """Stable repeated output after a successful execution should complete, not stall."""
    store = MockEventStore()

    def fake_embed(_texts: list[str]) -> list[list[float]]:
        return [
            [1.0, 0.0],      # goal
            [0.1, 0.995],    # current
            [0.1, 0.995],    # previous (identical -> stalled)
        ]

    runner = RoundRunner(RunnerCallbacks(emit=store.append, embed_fn=fake_embed))
    agents = [_agent("a1")]
    strategy = SequentialStrategy()

    ctx = _colony_ctx(round_number=3).model_copy(update={
        "prev_round_summary": "a1: Stable verified output repeated.",
    })
    result = await runner.run_round(
        colony_context=ctx,
        agents=agents,
        strategy=strategy,
        llm_port=MockLLMPort(
            response_content="Stable verified output repeated.",
        ),
        vector_port=None,
        event_store_address="ws-1/th-1/col-1",
        recent_successful_code_execute=True,
    )

    assert result.convergence.is_stalled
    assert result.stall_count == 0
    assert result.governance.action == "complete"
    assert result.governance.reason == "verified_execution_converged"

    governance_chats = [
        e for e in store.events
        if isinstance(e, ColonyChatMessage) and e.event_kind == "governance"
    ]
    assert not any("Convergence stall detected" in e.content for e in governance_chats)


@pytest.mark.asyncio
async def test_failed_code_execute_clears_verified_completion_signal() -> None:
    """A newer failed execution should cancel the carried completion hint."""
    store = MockEventStore()

    def fake_embed(_texts: list[str]) -> list[list[float]]:
        return [
            [1.0, 0.0],      # goal
            [0.1, 0.995],    # current
            [0.1, 0.995],    # previous (identical -> stalled)
        ]

    async def failed_code_execute(*_args) -> ToolExecutionResult:
        return ToolExecutionResult(
            content="Traceback: failing test",
            code_execute_failed=True,
        )

    runner = RoundRunner(RunnerCallbacks(
        emit=store.append,
        embed_fn=fake_embed,
        code_execute_handler=failed_code_execute,
    ))
    agents = [_agent("a1")]
    strategy = SequentialStrategy()

    ctx = _colony_ctx(round_number=3).model_copy(update={
        "prev_round_summary": "a1: Stable verified output repeated.",
    })
    result = await runner.run_round(
        colony_context=ctx,
        agents=agents,
        strategy=strategy,
        llm_port=MockLLMPort(
            response_content="Stable verified output repeated.",
            tool_calls=[{"name": "code_execute", "input": {"code": "print('fail')"}}],
            tool_call_rounds=1,
        ),
        vector_port=None,
        event_store_address="ws-1/th-1/col-1",
        prior_stall_count=1,
        recent_successful_code_execute=True,
    )

    assert result.convergence.is_stalled
    assert not result.recent_successful_code_execute
    assert result.stall_count == 2
    assert result.governance.action == "warn"
    assert result.governance.reason == "stalled 2+ rounds"


@pytest.mark.asyncio
async def test_tool_calls_extracted() -> None:
    """AgentTurnCompleted events should carry tool names from the LLM response."""
    store = MockEventStore()
    runner = RoundRunner(RunnerCallbacks(emit=store.append))
    agents = [_agent("a1")]
    strategy = SequentialStrategy()

    llm = MockLLMPort(
        response_content="done",
        tool_calls=[{"name": "read_file", "input": {}}, {"name": "write_file", "input": {}}],
    )
    await runner.run_round(
        colony_context=_colony_ctx(),
        agents=agents,
        strategy=strategy,
        llm_port=llm,
        vector_port=None,
        event_store_address="ws-1/th-1/col-1",
    )
    turn_completed = [e for e in store.events if isinstance(e, AgentTurnCompleted)]
    assert len(turn_completed) == 1
    assert turn_completed[0].tool_calls == ["read_file", "write_file"]


@pytest.mark.asyncio
async def test_pheromone_update() -> None:
    weights: dict[tuple[str, str], float] = {("a1", "a2"): 1.0}
    updated = RoundRunner._update_pheromones(
        weights=weights,
        active_edges=[("a1", "a2")],
        governance_action="continue",
        convergence_progress=0.1,
    )
    # Should have been evaporated then strengthened
    assert ("a1", "a2") in updated
    # Evaporate: 1.0 + (1.0 - 1.0) * 0.95 = 1.0, then strengthen: 1.0 * 1.15 = 1.15
    assert abs(updated[("a1", "a2")] - 1.15) < 0.01


@pytest.mark.asyncio
async def test_pheromone_new_edge_initialized() -> None:
    """New routed edges should be initialized at 1.0 then modified."""
    updated = RoundRunner._update_pheromones(
        weights=None,
        active_edges=[("a1", "a2")],
        governance_action="continue",
        convergence_progress=0.1,
    )
    assert ("a1", "a2") in updated
    # New edge at 1.0, strengthened: 1.0 * 1.15 = 1.15
    assert abs(updated[("a1", "a2")] - 1.15) < 0.01


@pytest.mark.asyncio
async def test_pheromone_weaken_on_warn() -> None:
    """Pheromones weaken when governance warns."""
    weights: dict[tuple[str, str], float] = {("a1", "a2"): 1.5}
    updated = RoundRunner._update_pheromones(
        weights=weights,
        active_edges=[("a1", "a2")],
        governance_action="warn",
        convergence_progress=0.0,
    )
    # Evaporate: 1.0 + (1.5 - 1.0) * 0.95 = 1.475, weaken: 1.475 * 0.75 = 1.10625
    assert ("a1", "a2") in updated
    assert abs(updated[("a1", "a2")] - 1.10625) < 0.01


# ---------------------------------------------------------------------------
# Completion signal detection
# ---------------------------------------------------------------------------


def test_detect_completion_signal_positive() -> None:
    assert _detect_completion_signal("The task complete. Here is the result.")
    assert _detect_completion_signal("Implementation is complete.")
    assert _detect_completion_signal("Nothing left to do.")
    assert _detect_completion_signal("No further changes needed.")
    assert _detect_completion_signal("FINAL ANSWER: 42")
    assert _detect_completion_signal("All done with the widget.")


def test_detect_completion_signal_negative() -> None:
    assert not _detect_completion_signal("Working on it, still iterating.")
    assert not _detect_completion_signal("Here is the next attempt at building the widget.")
    assert not _detect_completion_signal("I need to complete the refactor first.")


# ---------------------------------------------------------------------------
# Heuristic convergence — new signals
# ---------------------------------------------------------------------------


def test_heuristic_converges_on_completion_phrase() -> None:
    """Stable output with a completion phrase should converge at round 2+."""
    runner = RoundRunner(RunnerCallbacks(emit=lambda _: None))
    prev = "a1: The fibonacci function returns correct values. Task complete."
    curr = "a1: The fibonacci function returns correct values. Task complete."
    result = runner._compute_convergence_heuristic(prev, curr, round_number=2)
    assert result.is_converged, (
        f"Expected convergence, got score={result.score}, stability={result.stability}"
    )


def test_heuristic_converges_completion_phrase_with_overlap() -> None:
    """Completion phrase with moderate word overlap should converge."""
    runner = RoundRunner(RunnerCallbacks(emit=lambda _: None))
    prev = "a1: The widget is built and tested. Verified output is correct."
    curr = "a1: The widget is built and tested. Task complete."
    result = runner._compute_convergence_heuristic(prev, curr, round_number=3)
    assert result.stability > 0.50
    assert result.is_converged


def test_heuristic_converges_on_high_stability() -> None:
    """Very similar outputs at round 2+ should converge (settled)."""
    runner = RoundRunner(RunnerCallbacks(emit=lambda _: None))
    prev = "a1: The widget is built and tested. All tests pass. Output verified."
    curr = "a1: The widget is built and tested. All tests pass. Output verified."
    result = runner._compute_convergence_heuristic(prev, curr, round_number=2)
    assert result.stability > 0.80
    assert result.is_converged


def test_heuristic_does_not_converge_on_changing_outputs() -> None:
    """Obviously different outputs should NOT converge."""
    runner = RoundRunner(RunnerCallbacks(emit=lambda _: None))
    prev = "a1: Starting work on the fibonacci implementation. Setting up the module."
    curr = "a1: Refactored the approach. Now using memoization. Added error handling for negatives."
    result = runner._compute_convergence_heuristic(prev, curr, round_number=3)
    assert not result.is_converged, (
        f"Should not converge on changing output, stability={result.stability}"
    )


def test_heuristic_does_not_converge_at_round_one() -> None:
    """Round 1 should never converge regardless of signals."""
    runner = RoundRunner(RunnerCallbacks(emit=lambda _: None))
    prev = "a1: Task complete."
    curr = "a1: Task complete."
    result = runner._compute_convergence_heuristic(prev, curr, round_number=1)
    assert not result.is_converged


def test_heuristic_no_converge_low_stability_with_phrase() -> None:
    """Completion phrase alone is not enough — need stability > 0.50."""
    runner = RoundRunner(RunnerCallbacks(emit=lambda _: None))
    prev = "a1: alpha bravo charlie delta echo foxtrot"
    curr = "a1: xray yankee zulu. Task complete."
    result = runner._compute_convergence_heuristic(prev, curr, round_number=2)
    # Very low word overlap → low stability
    assert not result.is_converged, f"Should not converge with low stability={result.stability}"


# ---------------------------------------------------------------------------
# Wave 55: round_had_progress prevents false stall
# ---------------------------------------------------------------------------


def test_heuristic_no_stall_when_productive_progress() -> None:
    """Identical summaries should NOT stall when round_had_progress is True.

    Uses the embedding path (_compute_convergence_from_vecs) where identical
    vectors produce stability>0.95 and progress<0.01 — the stall condition.
    """
    runner = RoundRunner(RunnerCallbacks(emit=lambda _: None))
    # Craft vectors: goal=[1,0], curr=prev=[0.1,0.995] (identical, low alignment)
    vecs_stall = [[1.0, 0.0], [0.1, 0.995], [0.1, 0.995]]
    # Without progress — should stall at round 3+
    result_no_progress = runner._compute_convergence_from_vecs(
        vecs_stall, has_prev=True, round_number=3, round_had_progress=False,
    )
    assert result_no_progress.is_stalled, "Should stall without progress signal"
    # With progress — should NOT stall
    result_with_progress = runner._compute_convergence_from_vecs(
        vecs_stall, has_prev=True, round_number=3, round_had_progress=True,
    )
    assert not result_with_progress.is_stalled, (
        "Productive round should not be marked stalled"
    )
    assert result_with_progress.progress >= 0.02, (
        "Progress floor should be applied"
    )


def test_progress_floor_does_not_help_observation_spam() -> None:
    """round_had_progress=False leaves stall detection intact for pure observation."""
    runner = RoundRunner(RunnerCallbacks(emit=lambda _: None))
    # Identical vectors, low goal alignment — classic stall
    vecs = [[1.0, 0.0], [0.1, 0.995], [0.1, 0.995]]
    result = runner._compute_convergence_from_vecs(
        vecs, has_prev=True, round_number=4, round_had_progress=False,
    )
    assert result.is_stalled, "Observation-only round should still stall"


# ---------------------------------------------------------------------------
# Wave 55: broadened governance escape hatch
# ---------------------------------------------------------------------------


def test_governance_completes_on_productive_action() -> None:
    """Stalled colony with recent productive action should complete."""
    stalled = ConvergenceResult(
        score=0.5, goal_alignment=0.5, stability=0.98,
        progress=0.0, is_stalled=True, is_converged=False,
    )
    decision = RoundRunner._evaluate_governance(
        stalled, round_number=3, stall_count=1,
        recent_successful_code_execute=False,
        recent_productive_action=True,
    )
    assert decision.action == "complete"
    assert decision.reason == "verified_execution_converged"


def test_governance_still_halts_without_productive_action() -> None:
    """Stalled colony without productive action should still halt at 4+ rounds."""
    stalled = ConvergenceResult(
        score=0.5, goal_alignment=0.5, stability=0.98,
        progress=0.0, is_stalled=True, is_converged=False,
    )
    decision = RoundRunner._evaluate_governance(
        stalled, round_number=6, stall_count=4,
        recent_successful_code_execute=False,
        recent_productive_action=False,
    )
    assert decision.action == "force_halt"
    assert "stalled 4+" in decision.reason


def test_governance_warns_without_productive_action() -> None:
    """Stalled colony without productive action should warn at 2+ rounds."""
    stalled = ConvergenceResult(
        score=0.5, goal_alignment=0.5, stability=0.98,
        progress=0.0, is_stalled=True, is_converged=False,
    )
    decision = RoundRunner._evaluate_governance(
        stalled, round_number=4, stall_count=2,
        recent_successful_code_execute=False,
        recent_productive_action=False,
    )
    assert decision.action == "warn"


def test_governance_code_execute_still_works() -> None:
    """Original code_execute escape hatch still works."""
    stalled = ConvergenceResult(
        score=0.5, goal_alignment=0.5, stability=0.98,
        progress=0.0, is_stalled=True, is_converged=False,
    )
    decision = RoundRunner._evaluate_governance(
        stalled, round_number=3, stall_count=1,
        recent_successful_code_execute=True,
        recent_productive_action=False,
    )
    assert decision.action == "complete"


# ---------------------------------------------------------------------------
# Embedding path takes precedence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_path_takes_precedence() -> None:
    """When embed_fn is provided, the embedding path is used, not the heuristic."""
    call_log: list[str] = []

    def fake_embed(texts: list[str]) -> list[list[float]]:
        call_log.append("embed")
        # Return unit vectors: goal=[1,0], curr=[0.9,0.44], prev=[0.85,0.53]
        vecs = []
        for i, _ in enumerate(texts):
            if i == 0:
                vecs.append([1.0, 0.0])
            elif i == 1:
                vecs.append([0.9, 0.436])
            else:
                vecs.append([0.85, 0.527])
        return vecs

    runner = RoundRunner(RunnerCallbacks(emit=lambda _: None, embed_fn=fake_embed))
    result = await runner._compute_convergence(
        prev_summary="previous output",
        curr_summary="current output",
        goal="build a widget",
        round_number=3,
    )
    assert len(call_log) == 1, "embed_fn should have been called"
    # The embedding path computes real cosine similarity, not the heuristic
    assert result.goal_alignment != 0.5, "Should not be the heuristic fixed value"


# ---------------------------------------------------------------------------
# Governance returns 'complete' on heuristic convergence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_governance_complete_on_heuristic_convergence() -> None:
    """A settled single-agent colony should get governance action='complete'."""
    store = MockEventStore()
    runner = RoundRunner(RunnerCallbacks(emit=store.append))
    agents = [_agent("a1")]
    strategy = SequentialStrategy()

    # Simulate round 3 with stable output
    ctx = _colony_ctx(round_number=3)
    ctx = ctx.model_copy(update={
        "prev_round_summary": "a1: The widget is built and tested. All tests pass. Task complete.",
    })
    result = await runner.run_round(
        colony_context=ctx,
        agents=agents,
        strategy=strategy,
        llm_port=MockLLMPort(
            response_content="The widget is built and tested. All tests pass. Task complete.",
        ),
        vector_port=None,
        event_store_address="ws-1/th-1/col-1",
    )
    assert result.convergence.is_converged
    assert result.governance.action == "complete"
    assert result.governance.reason == "converged"


# ---------------------------------------------------------------------------
# KG write hook (Wave 13 A-T3)
# ---------------------------------------------------------------------------


class MockKGAdapter:
    """Minimal mock for the KG adapter used by the runner hook."""

    def __init__(self) -> None:
        self.ingested: list[tuple[list[dict[str, str]], str, str | None, int | None]] = []

    async def ingest_tuples(
        self,
        tuples: list[dict[str, str]],
        workspace_id: str,
        source_colony: str | None = None,
        source_round: int | None = None,
    ) -> int:
        self.ingested.append((tuples, workspace_id, source_colony, source_round))
        return len(tuples)


@pytest.mark.asyncio
async def test_kg_hook_ingests_archivist_tuples() -> None:
    """Runner should call kg_adapter.ingest_tuples for archivist agent outputs."""
    store = MockEventStore()
    kg = MockKGAdapter()
    runner = RoundRunner(RunnerCallbacks(emit=store.append, kg_adapter=kg))
    agents = [_agent("arch-1", name="archivist")]
    strategy = SequentialStrategy()

    tuples_json = '[{"subject": "Auth", "predicate": "DEPENDS_ON", "object": "JWT"}]'
    await runner.run_round(
        colony_context=_colony_ctx(),
        agents=agents,
        strategy=strategy,
        llm_port=MockLLMPort(response_content=tuples_json),
        vector_port=None,
        event_store_address="ws-1/th-1/col-1",
    )

    assert len(kg.ingested) == 1
    tuples, ws_id, colony_id, round_num = kg.ingested[0]
    assert len(tuples) == 1
    assert tuples[0]["subject"] == "Auth"
    assert ws_id == "ws-1"
    assert colony_id == "col-1"
    assert round_num == 1


@pytest.mark.asyncio
async def test_kg_hook_skips_non_archivist() -> None:
    """Runner should NOT call kg_adapter for non-archivist agents."""
    store = MockEventStore()
    kg = MockKGAdapter()
    runner = RoundRunner(RunnerCallbacks(emit=store.append, kg_adapter=kg))
    agents = [_agent("c1", name="coder")]
    strategy = SequentialStrategy()

    await runner.run_round(
        colony_context=_colony_ctx(),
        agents=agents,
        strategy=strategy,
        llm_port=MockLLMPort(response_content="Some code output"),
        vector_port=None,
        event_store_address="ws-1/th-1/col-1",
    )

    assert len(kg.ingested) == 0


@pytest.mark.asyncio
async def test_kg_hook_no_adapter_no_crash() -> None:
    """Runner without kg_adapter should run fine (backward-compatible)."""
    store = MockEventStore()
    runner = RoundRunner(RunnerCallbacks(emit=store.append))  # no kg_adapter
    agents = [_agent("arch-1", name="archivist")]
    strategy = SequentialStrategy()

    result = await runner.run_round(
        colony_context=_colony_ctx(),
        agents=agents,
        strategy=strategy,
        llm_port=MockLLMPort(response_content="test output"),
        vector_port=None,
        event_store_address="ws-1/th-1/col-1",
    )

    assert result.round_number == 1


# ---------------------------------------------------------------------------
# Wave 37 1A: _compute_knowledge_prior tests
# ---------------------------------------------------------------------------

from formicos.engine.runner import _compute_knowledge_prior  # noqa: E402


def test_knowledge_prior_none_without_items() -> None:
    """No knowledge items → None (neutral topology)."""
    agents = [_agent("a1"), _agent("a2")]
    assert _compute_knowledge_prior(agents, None) is None
    assert _compute_knowledge_prior(agents, []) is None


def test_knowledge_prior_none_low_confidence() -> None:
    """Items with very low observation mass → None."""
    agents = [_agent("a1"), _agent("a2")]
    items = [{"conf_alpha": 1.0, "conf_beta": 1.0, "domains": ["python"]}]
    result = _compute_knowledge_prior(agents, items)
    assert result is None


def test_knowledge_prior_returns_dict_with_items() -> None:
    """Sufficient knowledge items should produce a prior dict."""
    agents = [_agent("a1", "coder"), _agent("a2", "reviewer")]
    items = [
        {"conf_alpha": 20.0, "conf_beta": 5.0, "domains": ["coder"]},
        {"conf_alpha": 15.0, "conf_beta": 3.0, "domains": ["reviewer"]},
    ]
    result = _compute_knowledge_prior(agents, items)
    assert result is not None
    assert isinstance(result, dict)
    # Should contain edges for both directions
    assert ("a1", "a2") in result
    assert ("a2", "a1") in result


def test_knowledge_prior_clamped_to_band() -> None:
    """Prior values must be within [0.85, 1.15]."""
    agents = [_agent("a1"), _agent("a2")]
    items = [
        {"conf_alpha": 100.0, "conf_beta": 1.0, "domains": ["coder"]},
    ]
    result = _compute_knowledge_prior(agents, items)
    if result is not None:
        for v in result.values():
            assert 0.85 <= v <= 1.15, f"Prior {v} outside band"
