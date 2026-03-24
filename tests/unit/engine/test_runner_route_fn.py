"""Tests for route_fn injection and phase threading in RoundRunner (ADR-012)."""

from __future__ import annotations

import pytest

from formicos.core.events import AgentTurnStarted, TokensConsumed
from formicos.core.types import AgentConfig, CasteRecipe, ColonyContext, LLMResponse
from formicos.engine.runner import RoundResult, RunnerCallbacks, RoundRunner
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


def _agent(agent_id: str, caste: str = "coder") -> AgentConfig:
    return AgentConfig(
        id=agent_id, name=agent_id, caste=caste,
        model="default/model", recipe=_recipe(caste),
    )


def _colony_ctx(round_number: int = 1) -> ColonyContext:
    return ColonyContext(
        colony_id="col-1", workspace_id="ws-1", thread_id="th-1",
        goal="Build a widget", round_number=round_number,
        merge_edges=[],
    )


class MockLLMPort:
    def __init__(self, response_content: str = "Test output") -> None:
        self._content = response_content
        self.calls: list[str] = []  # track model used in each call

    async def complete(
        self, model: str, messages: object, tools: object = None,
        temperature: float = 0.0, max_tokens: int = 4096,
        tool_choice: object | None = None,
    ) -> LLMResponse:
        self.calls.append(model)
        return LLMResponse(
            content=self._content, tool_calls=[],
            input_tokens=10, output_tokens=5,
            model=model, stop_reason="end_turn",
        )


# ---------------------------------------------------------------------------
# route_fn injection
# ---------------------------------------------------------------------------


class TestRouteFnInjection:
    """route_fn selects effective_model for agent LLM calls."""

    @pytest.mark.anyio()
    async def test_route_fn_overrides_agent_model(self) -> None:
        events: list[object] = []
        llm = MockLLMPort()

        def route_fn(caste: str, phase: str, round_num: int, budget: float) -> str:
            return "routed/model"

        runner = RoundRunner(RunnerCallbacks(
            emit=lambda e: events.append(e),
            route_fn=route_fn,
        ))
        result = await runner.run_round(
            colony_context=_colony_ctx(),
            agents=[_agent("coder-0")],
            strategy=SequentialStrategy(),
            llm_port=llm,  # type: ignore[arg-type]
            vector_port=None,
            event_store_address="ws/th/col",
        )
        # LLM was called with routed model, not default
        assert llm.calls == ["routed/model"]

        # AgentTurnStarted event has routed model
        turn_started = [e for e in events if isinstance(e, AgentTurnStarted)]
        assert len(turn_started) == 1
        assert turn_started[0].model == "routed/model"

        # TokensConsumed event has routed model
        tokens = [e for e in events if isinstance(e, TokensConsumed)]
        assert len(tokens) == 1
        assert tokens[0].model == "routed/model"

    @pytest.mark.anyio()
    async def test_no_route_fn_uses_agent_model(self) -> None:
        events: list[object] = []
        llm = MockLLMPort()

        runner = RoundRunner(RunnerCallbacks(emit=lambda e: events.append(e)))
        await runner.run_round(
            colony_context=_colony_ctx(),
            agents=[_agent("coder-0")],
            strategy=SequentialStrategy(),
            llm_port=llm,  # type: ignore[arg-type]
            vector_port=None,
            event_store_address="ws/th/col",
        )
        assert llm.calls == ["default/model"]

    @pytest.mark.anyio()
    async def test_route_fn_receives_correct_args(self) -> None:
        captured: list[tuple[str, str, int, float]] = []

        def route_fn(caste: str, phase: str, round_num: int, budget: float) -> str:
            captured.append((caste, phase, round_num, budget))
            return "routed/model"

        runner = RoundRunner(RunnerCallbacks(
            emit=lambda e: None,
            route_fn=route_fn,
        ))
        await runner.run_round(
            colony_context=_colony_ctx(round_number=3),
            agents=[_agent("rev-0", caste="reviewer")],
            strategy=SequentialStrategy(),
            llm_port=MockLLMPort(),  # type: ignore[arg-type]
            vector_port=None,
            event_store_address="ws/th/col",
            budget_limit=10.0,
            total_colony_cost=2.5,
        )
        assert len(captured) == 1
        caste, phase, rn, budget = captured[0]
        assert caste == "reviewer"
        assert phase == "execute"
        assert rn == 3
        # budget_remaining = 10.0 - 2.5 - 0.0 = 7.5
        assert budget == pytest.approx(7.5)

    @pytest.mark.anyio()
    async def test_route_fn_per_caste_routing(self) -> None:
        """Different castes get different models from route_fn."""
        llm = MockLLMPort()

        def route_fn(caste: str, phase: str, round_num: int, budget: float) -> str:
            if caste == "coder":
                return "cloud/expensive"
            return "local/cheap"

        runner = RoundRunner(RunnerCallbacks(
            emit=lambda e: None,
            route_fn=route_fn,
        ))
        await runner.run_round(
            colony_context=_colony_ctx(),
            agents=[_agent("coder-0", "coder"), _agent("rev-0", "reviewer")],
            strategy=SequentialStrategy(),
            llm_port=llm,  # type: ignore[arg-type]
            vector_port=None,
            event_store_address="ws/th/col",
        )
        assert "cloud/expensive" in llm.calls
        assert "local/cheap" in llm.calls


# ---------------------------------------------------------------------------
# budget_limit and total_colony_cost
# ---------------------------------------------------------------------------


class TestBudgetTracking:
    """run_round passes budget_remaining to route_fn."""

    @pytest.mark.anyio()
    async def test_budget_limit_default(self) -> None:
        captured_budgets: list[float] = []

        def route_fn(caste: str, phase: str, rn: int, budget: float) -> str:
            captured_budgets.append(budget)
            return "test/model"

        runner = RoundRunner(RunnerCallbacks(emit=lambda e: None, route_fn=route_fn))
        await runner.run_round(
            colony_context=_colony_ctx(),
            agents=[_agent("c-0")],
            strategy=SequentialStrategy(),
            llm_port=MockLLMPort(),  # type: ignore[arg-type]
            vector_port=None,
            event_store_address="ws/th/col",
        )
        # Default budget_limit=5.0, total_colony_cost=0.0
        assert captured_budgets[0] == pytest.approx(5.0)

    @pytest.mark.anyio()
    async def test_budget_limit_with_colony_cost(self) -> None:
        captured_budgets: list[float] = []

        def route_fn(caste: str, phase: str, rn: int, budget: float) -> str:
            captured_budgets.append(budget)
            return "test/model"

        runner = RoundRunner(RunnerCallbacks(emit=lambda e: None, route_fn=route_fn))
        await runner.run_round(
            colony_context=_colony_ctx(),
            agents=[_agent("c-0")],
            strategy=SequentialStrategy(),
            llm_port=MockLLMPort(),  # type: ignore[arg-type]
            vector_port=None,
            event_store_address="ws/th/col",
            budget_limit=10.0,
            total_colony_cost=7.0,
        )
        assert captured_budgets[0] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# RoundResult.retrieved_skill_ids
# ---------------------------------------------------------------------------


class TestRetrievedSkillIds:
    """RoundResult includes retrieved_skill_ids field."""

    @pytest.mark.anyio()
    async def test_round_result_has_retrieved_skill_ids(self) -> None:
        runner = RoundRunner(RunnerCallbacks(emit=lambda e: None))
        result = await runner.run_round(
            colony_context=_colony_ctx(),
            agents=[_agent("c-0")],
            strategy=SequentialStrategy(),
            llm_port=MockLLMPort(),  # type: ignore[arg-type]
            vector_port=None,
            event_store_address="ws/th/col",
        )
        assert isinstance(result, RoundResult)
        assert result.retrieved_skill_ids == []

    def test_round_result_model_accepts_skill_ids(self) -> None:
        from formicos.engine.runner import ConvergenceResult, GovernanceDecision

        result = RoundResult(
            round_number=1,
            convergence=ConvergenceResult(
                score=0.5, goal_alignment=0.5, stability=0.0,
                progress=0.1, is_stalled=False, is_converged=False,
            ),
            governance=GovernanceDecision(action="continue", reason="in_progress"),
            cost=0.01, duration_ms=100,
            round_summary="summary",
            outputs={}, updated_weights={},
            retrieved_skill_ids=["skill-1", "skill-2"],
        )
        assert result.retrieved_skill_ids == ["skill-1", "skill-2"]


# ---------------------------------------------------------------------------
# routing_override (Wave 19 Track C)
# ---------------------------------------------------------------------------


class TestRoutingOverride:
    """routing_override bypasses caste×phase routing with tier-based model."""

    @pytest.mark.anyio()
    async def test_override_selects_tier_model(self) -> None:
        """routing_override=heavy uses claude-sonnet model, not route_fn."""
        llm = MockLLMPort()

        def route_fn(caste: str, phase: str, rn: int, budget: float) -> str:
            return "routed/model"

        runner = RoundRunner(RunnerCallbacks(emit=lambda e: None, route_fn=route_fn))
        await runner.run_round(
            colony_context=_colony_ctx(),
            agents=[_agent("coder-0")],
            strategy=SequentialStrategy(),
            llm_port=llm,  # type: ignore[arg-type]
            vector_port=None,
            event_store_address="ws/th/col",
            routing_override={"tier": "heavy", "reason": "complex task"},
        )
        assert llm.calls == ["anthropic/claude-sonnet-4-6"]

    @pytest.mark.anyio()
    async def test_override_max_tier(self) -> None:
        """routing_override=max uses claude-opus model."""
        llm = MockLLMPort()
        runner = RoundRunner(RunnerCallbacks(emit=lambda e: None))
        await runner.run_round(
            colony_context=_colony_ctx(),
            agents=[_agent("coder-0")],
            strategy=SequentialStrategy(),
            llm_port=llm,  # type: ignore[arg-type]
            vector_port=None,
            event_store_address="ws/th/col",
            routing_override={"tier": "max", "reason": "critical"},
        )
        assert llm.calls == ["anthropic/claude-opus-4-6"]

    @pytest.mark.anyio()
    async def test_override_standard_with_route_fn(self) -> None:
        """routing_override=standard with route_fn delegates to route_fn."""
        llm = MockLLMPort()

        def route_fn(caste: str, phase: str, rn: int, budget: float) -> str:
            return "fleet/default-model"

        runner = RoundRunner(RunnerCallbacks(emit=lambda e: None, route_fn=route_fn))
        await runner.run_round(
            colony_context=_colony_ctx(),
            agents=[_agent("coder-0")],
            strategy=SequentialStrategy(),
            llm_port=llm,  # type: ignore[arg-type]
            vector_port=None,
            event_store_address="ws/th/col",
            routing_override={"tier": "standard", "reason": "downgrade"},
        )
        assert llm.calls == ["fleet/default-model"]

    @pytest.mark.anyio()
    async def test_override_standard_no_route_fn_falls_back(self) -> None:
        """routing_override=standard without route_fn uses llama-cpp/default."""
        llm = MockLLMPort()
        runner = RoundRunner(RunnerCallbacks(emit=lambda e: None))
        await runner.run_round(
            colony_context=_colony_ctx(),
            agents=[_agent("coder-0")],
            strategy=SequentialStrategy(),
            llm_port=llm,  # type: ignore[arg-type]
            vector_port=None,
            event_store_address="ws/th/col",
            routing_override={"tier": "standard", "reason": "reset"},
        )
        assert llm.calls == ["llama-cpp/default"]

    @pytest.mark.anyio()
    async def test_no_override_uses_route_fn(self) -> None:
        """Without routing_override, route_fn is used normally."""
        llm = MockLLMPort()

        def route_fn(caste: str, phase: str, rn: int, budget: float) -> str:
            return "normal/model"

        runner = RoundRunner(RunnerCallbacks(emit=lambda e: None, route_fn=route_fn))
        await runner.run_round(
            colony_context=_colony_ctx(),
            agents=[_agent("coder-0")],
            strategy=SequentialStrategy(),
            llm_port=llm,  # type: ignore[arg-type]
            vector_port=None,
            event_store_address="ws/th/col",
        )
        assert llm.calls == ["normal/model"]


class TestTierToModel:
    """_tier_to_model maps tier strings to model addresses."""

    def test_heavy_tier(self) -> None:
        runner = RoundRunner(RunnerCallbacks(emit=lambda e: None))
        assert runner._tier_to_model("heavy") == "anthropic/claude-sonnet-4-6"

    def test_max_tier(self) -> None:
        runner = RoundRunner(RunnerCallbacks(emit=lambda e: None))
        assert runner._tier_to_model("max") == "anthropic/claude-opus-4-6"

    def test_standard_no_route_fn(self) -> None:
        runner = RoundRunner(RunnerCallbacks(emit=lambda e: None))
        assert runner._tier_to_model("standard") == "llama-cpp/default"

    def test_standard_with_route_fn(self) -> None:
        def route_fn(caste: str, phase: str, rn: int, budget: float) -> str:
            return "fleet/custom"

        runner = RoundRunner(RunnerCallbacks(emit=lambda e: None, route_fn=route_fn))
        assert runner._tier_to_model("standard") == "fleet/custom"

    def test_unknown_tier_falls_back_to_standard(self) -> None:
        runner = RoundRunner(RunnerCallbacks(emit=lambda e: None))
        assert runner._tier_to_model("unknown") == "llama-cpp/default"
