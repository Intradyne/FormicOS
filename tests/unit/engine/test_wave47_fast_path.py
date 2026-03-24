"""Wave 47: Tests for fast_path execution, structural context refresh, and preview.

Validates:
  - fast_path field is replay-safe (event → projection)
  - fast_path execution skips convergence/pheromone overhead
  - structural context is injected into agent round context
  - preview returns plan summary without dispatching
"""

from __future__ import annotations

from typing import Any

import pytest

from formicos.core.events import ColonySpawned
from formicos.core.types import (
    AgentConfig,
    CasteRecipe,
    CasteSlot,
    ColonyContext,
    LLMResponse,
)
from formicos.engine.context import assemble_context
from formicos.engine.runner import (
    ConvergenceResult,
    GovernanceDecision,
    RoundRunner,
    RunnerCallbacks,
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


def _colony_ctx(
    round_number: int = 1,
    structural_context: str = "",
) -> ColonyContext:
    return ColonyContext(
        colony_id="col-1", workspace_id="ws-1", thread_id="th-1",
        goal="Build a widget", round_number=round_number,
        merge_edges=[],
        structural_context=structural_context,
    )


class MockLLMPort:
    def __init__(self, response_content: str = "Test output") -> None:
        self._content = response_content

    async def complete(
        self, model: str, messages: Any, tools: Any = None,
        temperature: float = 0.0, max_tokens: int = 4096,
        tool_choice: object | None = None,
    ) -> LLMResponse:
        return LLMResponse(
            content=self._content, tool_calls=[],
            input_tokens=100, output_tokens=50,
            model=model, stop_reason="end_turn",
        )

    async def stream(
        self, model: str, messages: Any, tools: Any = None,
        temperature: float = 0.0, max_tokens: int = 4096,
    ) -> Any:
        from formicos.core.types import LLMChunk
        yield LLMChunk(content=self._content, is_final=True)


# ---------------------------------------------------------------------------
# Track A: fast_path replay truth
# ---------------------------------------------------------------------------


class TestFastPathReplayTruth:
    """fast_path must be persisted through event → projection → replay."""

    def test_colony_spawned_default_false(self) -> None:
        """Older events without fast_path default to False."""
        from datetime import UTC, datetime

        ev = ColonySpawned(
            seq=1, timestamp=datetime.now(UTC),
            address="ws/th/col",
            thread_id="th", task="test",
            castes=[CasteSlot(caste="coder")],
            model_assignments={},
            strategy="stigmergic",
            max_rounds=5,
            budget_limit=1.0,
        )
        assert ev.fast_path is False

    def test_colony_spawned_explicit_true(self) -> None:
        """fast_path=True is persisted on the event."""
        from datetime import UTC, datetime

        ev = ColonySpawned(
            seq=1, timestamp=datetime.now(UTC),
            address="ws/th/col",
            thread_id="th", task="test",
            castes=[CasteSlot(caste="coder")],
            model_assignments={},
            strategy="stigmergic",
            max_rounds=5,
            budget_limit=1.0,
            fast_path=True,
        )
        assert ev.fast_path is True

    def test_projection_persists_fast_path(self) -> None:
        """ColonyProjection should capture fast_path from ColonySpawned."""
        from datetime import UTC, datetime

        from formicos.surface.projections import ProjectionStore

        store = ProjectionStore()
        ev = ColonySpawned(
            seq=1, timestamp=datetime.now(UTC),
            address="ws-1/th-1/col-fast",
            thread_id="th-1", task="test fast path",
            castes=[CasteSlot(caste="coder")],
            model_assignments={},
            strategy="sequential",
            max_rounds=3,
            budget_limit=1.0,
            fast_path=True,
        )
        store.apply(ev)
        colony = store.get_colony("col-fast")
        assert colony is not None
        assert colony.fast_path is True

    def test_projection_default_false(self) -> None:
        """Colony spawned without fast_path defaults to False in projection."""
        from datetime import UTC, datetime

        from formicos.surface.projections import ProjectionStore

        store = ProjectionStore()
        ev = ColonySpawned(
            seq=1, timestamp=datetime.now(UTC),
            address="ws-1/th-1/col-norm",
            thread_id="th-1", task="normal task",
            castes=[CasteSlot(caste="coder")],
            model_assignments={},
            strategy="stigmergic",
            max_rounds=5,
            budget_limit=2.0,
        )
        store.apply(ev)
        colony = store.get_colony("col-norm")
        assert colony is not None
        assert colony.fast_path is False

    def test_event_serialization_roundtrip(self) -> None:
        """fast_path survives JSON serialization and deserialization."""
        from datetime import UTC, datetime

        from formicos.core.events import deserialize

        ev = ColonySpawned(
            seq=1, timestamp=datetime.now(UTC),
            address="ws/th/col",
            thread_id="th", task="test",
            castes=[CasteSlot(caste="coder")],
            model_assignments={},
            strategy="stigmergic",
            max_rounds=5,
            budget_limit=1.0,
            fast_path=True,
        )
        raw = ev.model_dump()
        restored = deserialize(raw)
        assert isinstance(restored, ColonySpawned)
        assert restored.fast_path is True


# ---------------------------------------------------------------------------
# Track A: fast_path execution behavior
# ---------------------------------------------------------------------------


class TestFastPathExecution:
    """fast_path should skip convergence and pheromone overhead."""

    @pytest.mark.asyncio
    async def test_fast_path_completes_after_first_round(self) -> None:
        """With fast_path, governance should signal complete after first round."""
        emitted: list[Any] = []

        async def emit(event: Any) -> None:
            emitted.append(event)

        runner = RoundRunner(RunnerCallbacks(
            emit=emit,
            embed_fn=None,
            async_embed_fn=None,
            cost_fn=lambda m, i, o: 0.001,
            tier_budgets=None,
            route_fn=None,
            kg_adapter=None,
            max_rounds=5,
        ))

        ctx = _colony_ctx(round_number=1)
        agents = [_agent("agent-1")]
        strategy = SequentialStrategy()

        result = await runner.run_round(
            colony_context=ctx,
            agents=agents,
            strategy=strategy,
            llm_port=MockLLMPort("Hello, world!"),  # type: ignore[arg-type]
            vector_port=None,
            event_store_address="ws-1/th-1/col-1",
            fast_path=True,
        )

        assert result.governance.action == "complete"
        assert result.governance.reason == "fast_path_complete"
        # Convergence should be synthetic 1.0
        assert result.convergence.score == 1.0
        assert result.convergence.is_converged is True
        # Pheromone weights should be unchanged (empty)
        assert result.updated_weights == {}

    @pytest.mark.asyncio
    async def test_normal_path_computes_convergence(self) -> None:
        """Without fast_path, convergence is computed normally."""
        emitted: list[Any] = []

        async def emit(event: Any) -> None:
            emitted.append(event)

        runner = RoundRunner(RunnerCallbacks(
            emit=emit,
            embed_fn=None,
            async_embed_fn=None,
            cost_fn=lambda m, i, o: 0.001,
            tier_budgets=None,
            route_fn=None,
            kg_adapter=None,
            max_rounds=5,
        ))

        ctx = _colony_ctx(round_number=1)
        agents = [_agent("agent-1")]
        strategy = SequentialStrategy()

        result = await runner.run_round(
            colony_context=ctx,
            agents=agents,
            strategy=strategy,
            llm_port=MockLLMPort("Test output"),  # type: ignore[arg-type]
            vector_port=None,
            event_store_address="ws-1/th-1/col-1",
            fast_path=False,
        )

        # Normal path should compute governance normally (not fast_path_complete)
        assert result.governance.reason != "fast_path_complete"


# ---------------------------------------------------------------------------
# Track B: structural context injection
# ---------------------------------------------------------------------------


class TestStructuralContextInjection:
    """Structural context must appear in the assembled Coder prompt."""

    @pytest.mark.asyncio
    async def test_structural_context_injected_when_present(self) -> None:
        """When structural_context is non-empty, it should appear in messages."""
        agent = _agent("agent-1")
        ctx = _colony_ctx(
            round_number=1,
            structural_context="src/main.py: def foo() -> None",
        )

        result = await assemble_context(
            agent=agent,
            colony_context=ctx,
            round_goal="Fix the widget",
            routed_outputs={},
            merged_summaries=[],
            vector_port=None,
        )

        # Find the structural context message
        structural_msgs = [
            m for m in result.messages
            if "[Workspace Structure]" in m["content"]
        ]
        assert len(structural_msgs) == 1
        assert "src/main.py" in structural_msgs[0]["content"]

    @pytest.mark.asyncio
    async def test_no_structural_context_when_empty(self) -> None:
        """When structural_context is empty, no structural message is added."""
        agent = _agent("agent-1")
        ctx = _colony_ctx(round_number=1, structural_context="")

        result = await assemble_context(
            agent=agent,
            colony_context=ctx,
            round_goal="Fix the widget",
            routed_outputs={},
            merged_summaries=[],
            vector_port=None,
        )

        structural_msgs = [
            m for m in result.messages
            if "Workspace Structure" in m["content"]
        ]
        assert len(structural_msgs) == 0


# ---------------------------------------------------------------------------
# Track C: preview behavior
# ---------------------------------------------------------------------------


class TestPreviewBehavior:
    """Preview must return plan summary without dispatching."""

    def test_spawn_colony_preview(self) -> None:
        """_preview_spawn_colony returns summary without colony_id."""
        from unittest.mock import MagicMock

        from formicos.surface.queen_tools import QueenToolDispatcher

        # We test the method directly with a minimal mock runtime
        dispatcher = QueenToolDispatcher.__new__(QueenToolDispatcher)
        dispatcher._runtime = MagicMock()
        dispatcher._runtime.projections.templates = {}
        msg, metadata = dispatcher._preview_spawn_colony(
            task="Build the widget",
            caste_slots=[CasteSlot(caste="coder")],
            strategy="stigmergic",
            max_rounds=10,
            budget_limit=2.0,
            fast_path=False,
            target_files=[],
        )
        assert "[PREVIEW" in msg
        assert "no colony dispatched" in msg.lower()
        assert "Build the widget" in msg
        assert metadata is not None
        assert metadata.get("preview") is True
        # No colony_id should be present
        assert "colony_id" not in (metadata or {})

    def test_spawn_colony_preview_with_fast_path(self) -> None:
        """Preview should surface fast_path mode honestly."""
        from unittest.mock import MagicMock

        from formicos.surface.queen_tools import QueenToolDispatcher

        dispatcher = QueenToolDispatcher.__new__(QueenToolDispatcher)
        dispatcher._runtime = MagicMock()
        dispatcher._runtime.projections.templates = {}
        msg, _ = dispatcher._preview_spawn_colony(
            task="Quick fix",
            caste_slots=[CasteSlot(caste="coder")],
            strategy="sequential",
            max_rounds=3,
            budget_limit=0.50,
            fast_path=True,
            target_files=["src/main.py"],
        )
        assert "fast_path" in msg
        assert "src/main.py" in msg
