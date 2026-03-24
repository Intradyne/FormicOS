"""Unit tests for formicos.surface.runtime."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import shutil
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from formicos.core.events import (
    ColonyKilled,
    ColonySpawned,
    MergeCreated,
    QueenMessage,
    ThreadRenamed,
)
from formicos.core.types import CasteSlot, InputSource
from formicos.core.settings import (
    EmbeddingConfig,
    GovernanceConfig,
    ModelDefaults,
    ModelsConfig,
    RoutingConfig,
    SystemConfig,
    SystemSettings,
)
from formicos.core.types import LLMResponse
from formicos.surface.runtime import LLMRouter, Runtime

NOW = datetime.now(UTC)


def _make_settings() -> SystemSettings:
    return SystemSettings(
        system=SystemConfig(host="0.0.0.0", port=8080, data_dir="./data"),
        models=ModelsConfig(
            defaults=ModelDefaults(
                queen="anthropic/claude-3-haiku",
                coder="ollama/llama3.2:3b",
                reviewer="ollama/llama3.2:3b",
                researcher="ollama/llama3.2:3b",
                archivist="ollama/llama3.2:3b",
            ),
            registry=[],
        ),
        embedding=EmbeddingConfig(model="test-model", dimensions=384),
        governance=GovernanceConfig(
            max_rounds_per_colony=25,
            stall_detection_window=3,
            convergence_threshold=0.95,
            default_budget_per_colony=1.0,
        ),
        routing=RoutingConfig(
            default_strategy="stigmergic",
            tau_threshold=0.35,
            k_in_cap=5,
            pheromone_decay_rate=0.1,
            pheromone_reinforce_rate=0.3,
        ),
    )


def _make_runtime(
    *,
    settings: SystemSettings | None = None,
    castes: Any = None,
) -> Runtime:
    event_store = AsyncMock()
    event_store.append = AsyncMock(return_value=42)
    projections = MagicMock()
    ws_manager = MagicMock()
    ws_manager.fan_out_event = AsyncMock()
    llm_router = MagicMock(spec=LLMRouter)
    return Runtime(
        event_store=event_store,
        projections=projections,
        ws_manager=ws_manager,
        settings=settings or _make_settings(),
        castes=castes,
        llm_router=llm_router,
        embed_fn=None,
        vector_store=None,
    )


# ---------------------------------------------------------------------------
# LLMRouter tests
# ---------------------------------------------------------------------------


class TestLLMRouter:
    """Tests for LLMRouter provider resolution and delegation."""

    def test_resolve_raises_for_unknown_provider(self) -> None:
        router = LLMRouter(adapters={})
        with pytest.raises(ValueError, match="No adapter registered for provider 'unknown'"):
            router._resolve("unknown/model-name")

    def test_resolve_returns_adapter_for_known_provider(self) -> None:
        adapter = MagicMock()
        router = LLMRouter(adapters={"anthropic": adapter})
        assert router._resolve("anthropic/claude-3-haiku") is adapter

    @pytest.mark.anyio()
    async def test_complete_delegates_to_correct_adapter(self) -> None:
        expected = LLMResponse(
            content="hello",
            tool_calls=[],
            input_tokens=10,
            output_tokens=5,
            model="anthropic/claude-3-haiku",
            stop_reason="end_turn",
        )
        adapter = AsyncMock()
        adapter.complete = AsyncMock(return_value=expected)
        router = LLMRouter(adapters={"anthropic": adapter})

        result = await router.complete(
            model="anthropic/claude-3-haiku",
            messages=[{"role": "user", "content": "hi"}],
        )

        assert result is expected
        adapter.complete.assert_awaited_once_with(
            "anthropic/claude-3-haiku",
            [{"role": "user", "content": "hi"}],
            tools=None,
            temperature=0.0,
            max_tokens=4096,
            tool_choice=None,
        )


# ---------------------------------------------------------------------------
# Runtime tests
# ---------------------------------------------------------------------------


class TestEmitAndBroadcast:
    """Tests for the single mutation path."""

    @pytest.mark.anyio()
    async def test_appends_projects_and_fans_out(self) -> None:
        rt = _make_runtime()

        event = QueenMessage(
            seq=0, timestamp=NOW, address="ws1/th1",
            thread_id="th1", role="operator", content="hello",
        )
        seq = await rt.emit_and_broadcast(event)

        assert seq == 42
        rt.event_store.append.assert_awaited_once_with(event)
        rt.projections.apply.assert_called_once()
        applied_event = rt.projections.apply.call_args[0][0]
        assert applied_event.seq == 42
        rt.ws_manager.fan_out_event.assert_awaited_once()


class TestSpawnColony:
    """Tests for spawn_colony."""

    @pytest.mark.anyio()
    async def test_emits_colony_spawned_and_returns_id(self) -> None:
        rt = _make_runtime()

        colony_id = await rt.spawn_colony(
            workspace_id="ws1", thread_id="th1",
            task="build feature", castes=[CasteSlot(caste="coder"), CasteSlot(caste="reviewer")],
        )

        assert colony_id.startswith("colony-")
        rt.event_store.append.assert_awaited_once()
        emitted = rt.event_store.append.call_args[0][0]
        assert isinstance(emitted, ColonySpawned)
        assert emitted.task == "build feature"
        assert emitted.castes == [CasteSlot(caste="coder"), CasteSlot(caste="reviewer")]


class TestKillColony:
    """Tests for kill_colony."""

    @pytest.mark.anyio()
    async def test_emits_colony_killed_and_stops_manager(self) -> None:
        rt = _make_runtime()
        rt.colony_manager = MagicMock()
        rt.colony_manager.stop_colony = AsyncMock()
        rt.projections.get_colony.return_value = None

        await rt.kill_colony("colony-abc")

        rt.event_store.append.assert_awaited_once()
        emitted = rt.event_store.append.call_args[0][0]
        assert isinstance(emitted, ColonyKilled)
        assert emitted.colony_id == "colony-abc"
        rt.colony_manager.stop_colony.assert_awaited_once_with("colony-abc")

    @pytest.mark.anyio()
    async def test_kill_colony_without_colony_manager(self) -> None:
        rt = _make_runtime()
        rt.colony_manager = None
        rt.projections.get_colony.return_value = None

        await rt.kill_colony("colony-abc")

        rt.event_store.append.assert_awaited_once()


class TestSendQueenMessage:
    """Tests for send_queen_message."""

    @pytest.mark.anyio()
    async def test_emits_queen_message(self) -> None:
        rt = _make_runtime()

        await rt.send_queen_message("ws1", "th1", "hello queen")

        emitted = rt.event_store.append.call_args[0][0]
        assert isinstance(emitted, QueenMessage)
        assert emitted.role == "operator"
        assert emitted.content == "hello queen"
        assert emitted.address == "ws1/th1"


class TestCreateWorkspace:
    """Tests for eager workspace bootstrap."""

    @pytest.mark.anyio()
    async def test_creates_filesystem_workspace_directory(self) -> None:
        scratch = Path(".tmp_runtime_tests") / str(uuid4())
        settings = _make_settings()
        settings.system.data_dir = str(scratch)
        rt = _make_runtime(settings=settings)

        try:
            workspace_id = await rt.create_workspace("alpha")
            assert workspace_id == "alpha"
            assert (scratch / "workspaces" / "alpha" / "files").is_dir()
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    @pytest.mark.anyio()
    async def test_auto_renames_new_generated_thread_on_first_message(self) -> None:
        rt = _make_runtime()
        thread = MagicMock()
        thread.name = "thread-abc123"
        thread.queen_messages = []
        rt.projections.get_thread.return_value = thread

        await rt.send_queen_message("ws1", "thread-abc123", "can you make a snake game?")

        assert rt.event_store.append.await_count == 2
        first = rt.event_store.append.await_args_list[0].args[0]
        second = rt.event_store.append.await_args_list[1].args[0]
        assert isinstance(first, QueenMessage)
        assert isinstance(second, ThreadRenamed)
        assert second.thread_id == "thread-abc123"
        assert second.new_name == "Snake Game"

    @pytest.mark.anyio()
    async def test_does_not_rename_named_thread(self) -> None:
        rt = _make_runtime()
        thread = MagicMock()
        thread.name = "Main"
        thread.queen_messages = []
        rt.projections.get_thread.return_value = thread

        await rt.send_queen_message("ws1", "thread-abc123", "can you make a snake game?")

        assert rt.event_store.append.await_count == 1


class TestCreateMerge:
    """Tests for create_merge."""

    @pytest.mark.anyio()
    async def test_emits_merge_created_and_returns_edge_id(self) -> None:
        rt = _make_runtime()

        edge_id = await rt.create_merge("ws1", "colony-a", "colony-b")

        assert edge_id.startswith("merge-")
        emitted = rt.event_store.append.call_args[0][0]
        assert isinstance(emitted, MergeCreated)
        assert emitted.from_colony == "colony-a"
        assert emitted.to_colony == "colony-b"


class TestResolveModel:
    """Tests for model cascade resolution."""

    def test_returns_system_default_when_no_workspace_override(self) -> None:
        rt = _make_runtime()
        rt.projections.workspaces = {}

        model = rt.resolve_model("queen")
        assert model == "anthropic/claude-3-haiku"

    def test_returns_workspace_override_when_set(self) -> None:
        rt = _make_runtime()
        ws_proj = MagicMock()
        ws_proj.config = {"queen_model": "openai/gpt-4o"}
        rt.projections.workspaces = {"ws1": ws_proj}

        model = rt.resolve_model("queen", workspace_id="ws1")
        assert model == "openai/gpt-4o"

    def test_falls_back_to_coder_for_unknown_caste(self) -> None:
        rt = _make_runtime()
        rt.projections.workspaces = {}

        model = rt.resolve_model("unknown_caste")
        assert model == "ollama/llama3.2:3b"  # coder default


class TestBuildAgents:
    """Tests for build_agents."""

    def test_returns_empty_when_colony_not_found(self) -> None:
        rt = _make_runtime()
        rt.projections.get_colony.return_value = None

        assert rt.build_agents("colony-missing") == []

    def test_returns_empty_when_castes_not_set(self) -> None:
        rt = _make_runtime(castes=None)
        colony = MagicMock()
        colony.castes = [CasteSlot(caste="coder")]
        rt.projections.get_colony.return_value = colony

        assert rt.build_agents("colony-1") == []

    def test_builds_agent_configs_from_caste_recipes(self) -> None:
        from formicos.core.types import CasteRecipe

        recipe = CasteRecipe(
            name="Coder",
            system_prompt="You are a coder.",
            temperature=0.0,
            tools=["write_file"],
            max_tokens=4096,
        )
        castes_mock = MagicMock()
        castes_mock.castes = {"coder": recipe}
        rt = _make_runtime(castes=castes_mock)

        colony = MagicMock()
        colony.castes = [CasteSlot(caste="coder")]
        colony.model_assignments = {}
        colony.workspace_id = "ws1"
        rt.projections.get_colony.return_value = colony
        rt.projections.workspaces = {}

        agents = rt.build_agents("colony-1")

        assert len(agents) == 1
        assert agents[0].caste == "coder"
        assert agents[0].recipe is recipe


class TestParseToolInput:
    """Tests for cross-provider tool call normalization."""

    def test_anthropic_format(self) -> None:
        tc = {"name": "spawn_colony", "input": {"task": "build", "castes": ["coder"]}}
        result = Runtime.parse_tool_input(tc)
        assert result == {"task": "build", "castes": ["coder"]}

    def test_openai_format_string_arguments(self) -> None:
        tc = {"name": "spawn_colony", "arguments": '{"task": "build", "castes": ["coder"]}'}
        result = Runtime.parse_tool_input(tc)
        assert result == {"task": "build", "castes": ["coder"]}

    def test_openai_format_dict_arguments(self) -> None:
        tc = {"name": "spawn_colony", "arguments": {"task": "build"}}
        result = Runtime.parse_tool_input(tc)
        assert result == {"task": "build"}

    def test_empty_defaults(self) -> None:
        tc = {"name": "some_tool"}
        result = Runtime.parse_tool_input(tc)
        assert result == {}


# ---------------------------------------------------------------------------
# Input source resolution (ADR-033)
# ---------------------------------------------------------------------------


class TestInputSourceResolution:
    """Tests for spawn-time input source resolution."""

    @pytest.mark.anyio()
    async def test_spawn_with_input_sources(self) -> None:
        """Spawn passes resolved input_sources to the ColonySpawned event."""
        rt = _make_runtime()
        # Mock a completed source colony
        source_colony = MagicMock()
        source_colony.status = "completed"
        source_colony.round_records = [MagicMock()]
        source_colony.round_records[0].agent_outputs = {"arch-0": "summary output"}
        agent_mock = MagicMock()
        agent_mock.caste = "archivist"
        source_colony.agents = {"arch-0": agent_mock}
        rt.projections.get_colony.return_value = source_colony

        src = InputSource(type="colony", colony_id="colony-src")
        colony_id = await rt.spawn_colony(
            "ws1", "th1", "chained task",
            [CasteSlot(caste="coder")],
            input_sources=[src],
        )
        assert colony_id.startswith("colony-")

        # Check the emitted event has resolved input_sources
        emitted = rt.event_store.append.call_args[0][0]
        assert isinstance(emitted, ColonySpawned)
        assert len(emitted.input_sources) == 1
        assert emitted.input_sources[0].summary == "summary output"

    @pytest.mark.anyio()
    async def test_spawn_rejects_non_completed_source(self) -> None:
        """Spawn fails if source colony is not completed."""
        rt = _make_runtime()
        source_colony = MagicMock()
        source_colony.status = "running"
        rt.projections.get_colony.return_value = source_colony

        src = InputSource(type="colony", colony_id="colony-running")
        with pytest.raises(ValueError, match="Chain only from completed"):
            await rt.spawn_colony(
                "ws1", "th1", "task",
                [CasteSlot(caste="coder")],
                input_sources=[src],
            )

    @pytest.mark.anyio()
    async def test_spawn_rejects_missing_source(self) -> None:
        """Spawn fails if source colony does not exist."""
        rt = _make_runtime()
        rt.projections.get_colony.return_value = None

        src = InputSource(type="colony", colony_id="colony-gone")
        with pytest.raises(ValueError, match="not found"):
            await rt.spawn_colony(
                "ws1", "th1", "task",
                [CasteSlot(caste="coder")],
                input_sources=[src],
            )

    @pytest.mark.anyio()
    async def test_spawn_without_input_sources(self) -> None:
        """Spawn without input_sources works as before."""
        rt = _make_runtime()
        colony_id = await rt.spawn_colony(
            "ws1", "th1", "simple task",
            [CasteSlot(caste="coder")],
        )
        assert colony_id.startswith("colony-")
        emitted = rt.event_store.append.call_args[0][0]
        assert isinstance(emitted, ColonySpawned)
        assert emitted.input_sources == []
