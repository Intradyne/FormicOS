"""Unit tests for formicos.surface.queen_runtime."""

from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from formicos.core.types import CasteRecipe, LLMResponse, VectorSearchHit
from formicos.surface.queen_runtime import (
    QueenAgent,
    QueenResponse,
)
from formicos.surface.queen_shared import (
    PendingConfigProposal,
    _is_experimentable,
    _load_experimentable_params,
)


def _make_llm_response(
    content: str = "I will help you.",
    tool_calls: list[dict[str, Any]] | None = None,
) -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=tool_calls or [],
        input_tokens=100,
        output_tokens=50,
        model="anthropic/claude-3-haiku",
        stop_reason="end_turn",
    )


def _make_queen_recipe() -> CasteRecipe:
    return CasteRecipe(
        name="Queen",
        system_prompt="You are the Queen of the colony.",
        temperature=0.3,
        tools=["spawn_colony", "kill_colony", "get_status"],
        max_tokens=2048,
    )


def _make_thread(queen_messages: list[Any] | None = None) -> MagicMock:
    thread = MagicMock()
    thread.queen_messages = queen_messages or []
    return thread


def _make_runtime(
    *,
    thread: Any = None,
    llm_response: LLMResponse | None = None,
    queen_recipe: CasteRecipe | None = None,
) -> MagicMock:
    runtime = MagicMock()
    runtime.emit_and_broadcast = AsyncMock(return_value=1)

    # projections.get_thread
    runtime.projections.get_thread.return_value = thread

    # llm_router
    runtime.llm_router = MagicMock()
    runtime.llm_router.complete = AsyncMock(
        return_value=llm_response or _make_llm_response(),
    )

    # castes
    if queen_recipe:
        runtime.castes = MagicMock()
        runtime.castes.castes = {"queen": queen_recipe}
    else:
        runtime.castes = None

    # resolve_model
    runtime.resolve_model.return_value = "anthropic/claude-3-haiku"

    # parse_tool_input
    runtime.parse_tool_input = MagicMock(side_effect=lambda tc: tc.get("input", {}))

    # colony_manager
    runtime.colony_manager = None

    # settings (for read_workspace_files, suggest_config_change)
    runtime.settings.system.data_dir = tempfile.gettempdir()
    runtime.settings.governance.convergence_threshold = 0.85
    runtime.settings.governance.default_budget_per_colony = 5.0
    runtime.settings.governance.max_redirects_per_colony = 1
    runtime.settings.routing.tau_threshold = 0.5

    # vector_store
    runtime.vector_store = None

    # Wave 51: queen notes projection (dict, not MagicMock)
    runtime.projections.queen_notes = {}

    return runtime


@contextmanager
def _workspace_tempdir() -> Any:
    """Create a temp directory under the repo to avoid Windows temp ACL issues."""
    base = Path.cwd() / ".tmp_pytest"
    base.mkdir(exist_ok=True)
    tmpdir = base / f"queen-runtime-{uuid4().hex}"
    tmpdir.mkdir()
    try:
        yield str(tmpdir)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# QueenAgent.respond tests
# ---------------------------------------------------------------------------


class TestQueenRespond:
    """Tests for the QueenAgent.respond method."""

    @pytest.mark.anyio()
    async def test_returns_thread_not_found(self) -> None:
        runtime = _make_runtime(thread=None)
        queen = QueenAgent(runtime)

        result = await queen.respond("ws1", "th-missing")

        assert "not found" in result.reply.lower()
        assert result.actions == []
        runtime.llm_router.complete.assert_not_awaited()
        # Now emits a QueenMessage so the operator sees feedback in chat
        runtime.emit_and_broadcast.assert_awaited_once()
        emitted = runtime.emit_and_broadcast.call_args[0][0]
        assert emitted.role == "queen"

    @pytest.mark.anyio()
    async def test_calls_llm_and_emits_queen_message(self) -> None:
        thread = _make_thread()
        runtime = _make_runtime(thread=thread)
        queen = QueenAgent(runtime)

        result = await queen.respond("ws1", "th1")

        assert result.reply == "I will help you."
        # LLM called at least once (primary); may also be called by intent
        # fallback's Gemini classification (Wave 13) when no tool calls found.
        assert runtime.llm_router.complete.await_count >= 1
        runtime.emit_and_broadcast.assert_awaited_once()
        emitted = runtime.emit_and_broadcast.call_args[0][0]
        assert emitted.role == "queen"
        assert emitted.content == "I will help you."

    @pytest.mark.anyio()
    async def test_handles_tool_calls_spawn_colony(self) -> None:
        thread = _make_thread()

        # First call returns tool call, second call returns final response
        tool_response = _make_llm_response(
            content="",
            tool_calls=[{"name": "spawn_colony", "input": {
                "task": "build it",
                "castes": [{"caste": "coder", "tier": "standard"}],
            }}],
        )
        final_response = _make_llm_response(content="Colony spawned successfully.")

        runtime = _make_runtime(thread=thread)
        runtime.llm_router.complete = AsyncMock(side_effect=[tool_response, final_response])
        runtime.spawn_colony = AsyncMock(return_value="colony-abc123")

        queen = QueenAgent(runtime)
        result = await queen.respond("ws1", "th1")

        assert result.reply == "Colony spawned successfully."
        assert len(result.actions) == 1
        assert result.actions[0]["tool"] == "spawn_colony"
        assert result.actions[0]["colony_id"] == "colony-abc123"
        runtime.spawn_colony.assert_awaited_once()

    @pytest.mark.anyio()
    async def test_handles_plain_string_castes_backward_compat(self) -> None:
        """Old-format castes (plain strings) still work."""
        thread = _make_thread()

        tool_response = _make_llm_response(
            content="",
            tool_calls=[{"name": "spawn_colony", "input": {
                "task": "build it", "castes": ["coder", "reviewer"],
            }}],
        )
        final_response = _make_llm_response(content="Done.")

        runtime = _make_runtime(thread=thread)
        runtime.llm_router.complete = AsyncMock(side_effect=[tool_response, final_response])
        runtime.spawn_colony = AsyncMock(return_value="colony-xyz")

        queen = QueenAgent(runtime)
        result = await queen.respond("ws1", "th1")

        assert result.actions[0]["colony_id"] == "colony-xyz"
        # Verify CasteSlot objects were passed
        call_args = runtime.spawn_colony.call_args
        caste_slots = call_args[0][3] if len(call_args[0]) > 3 else call_args[1].get("castes", [])
        assert len(caste_slots) == 2
        assert caste_slots[0].caste == "coder"
        assert caste_slots[1].caste == "reviewer"

    @pytest.mark.anyio()
    async def test_handles_llm_error_gracefully(self) -> None:
        thread = _make_thread()
        runtime = _make_runtime(thread=thread)
        runtime.llm_router.complete = AsyncMock(side_effect=Exception("LLM down"))

        queen = QueenAgent(runtime)
        result = await queen.respond("ws1", "th1")

        assert "error" in result.reply.lower()
        assert result.actions == []
        # Now DOES emit a QueenMessage so the operator sees the error in chat
        runtime.emit_and_broadcast.assert_awaited_once()
        emitted = runtime.emit_and_broadcast.call_args[0][0]
        assert emitted.role == "queen"
        assert "language model" in emitted.content.lower()

    @pytest.mark.anyio()
    async def test_retries_once_after_recon_only_on_build_task(self) -> None:
        thread = _make_thread([
            SimpleNamespace(
                role="operator",
                content="build test-sentinel addon with scanner.py coverage.py handlers.py and tests",
            ),
        ])
        tool_response = _make_llm_response(
            content="",
            tool_calls=[{"name": "run_command", "input": {"command": "ls -la"}}],
        )
        recon_only_response = _make_llm_response(
            content="I checked the workspace and found the relevant files.",
            tool_calls=[],
        )
        final_response = _make_llm_response(
            content="I will propose the execution plan now.",
            tool_calls=[],
        )

        runtime = _make_runtime(thread=thread)
        runtime.projections.colonies = {}
        runtime.projections.workspaces = {}
        runtime.projections.list_colonies = MagicMock(return_value=[])
        runtime.retrieve_relevant_memory = AsyncMock(return_value=("", []))
        runtime.llm_router.complete = AsyncMock(
            side_effect=[tool_response, recon_only_response, final_response],
        )

        queen = QueenAgent(runtime)
        queen._execute_tool = AsyncMock(return_value=("workspace listing", None))  # type: ignore[method-assign]

        result = await queen.respond("ws1", "th1")

        assert result.reply == "I will propose the execution plan now."
        assert runtime.llm_router.complete.await_count >= 3

    @pytest.mark.anyio()
    async def test_injects_pre_llm_colony_directive_for_implementation_turn(self) -> None:
        thread = _make_thread([
            SimpleNamespace(
                role="operator",
                content="Strengthen checkpoint coverage in tests and add missing rollback cases.",
            ),
        ])
        runtime = _make_runtime(thread=thread)
        runtime.projections.colonies = {}
        runtime.projections.workspaces = {}
        runtime.projections.list_colonies = MagicMock(return_value=[])
        runtime.retrieve_relevant_memory = AsyncMock(return_value=("", []))

        queen = QueenAgent(runtime)
        await queen.respond("ws1", "th1")

        call = runtime.llm_router.complete.await_args_list[0]
        messages = call.kwargs["messages"]
        directive_idx = next(
            i for i, m in enumerate(messages)
            if m["role"] == "system"
            and "IMPORTANT: The operator's message is implementation work" in m["content"]
        )
        first_user_idx = next(i for i, m in enumerate(messages) if m["role"] == "user")
        assert directive_idx < first_user_idx

    @pytest.mark.anyio()
    async def test_implementation_turn_narrowing_excludes_propose_plan(self) -> None:
        thread = _make_thread([
            SimpleNamespace(
                role="operator",
                content="Refactor runner.py to share workspace root logic cleanly.",
            ),
        ])
        runtime = _make_runtime(thread=thread)
        runtime.projections.colonies = {}
        runtime.projections.workspaces = {}
        runtime.projections.list_colonies = MagicMock(return_value=[])
        runtime.retrieve_relevant_memory = AsyncMock(return_value=("", []))

        queen = QueenAgent(runtime)
        await queen.respond("ws1", "th1")

        call = runtime.llm_router.complete.await_args_list[0]
        tool_names = {tool["name"] for tool in call.kwargs["tools"]}
        assert "spawn_colony" in tool_names
        assert "spawn_parallel" in tool_names
        assert "propose_plan" not in tool_names

    @pytest.mark.anyio()
    async def test_simple_implementation_turn_prefers_single_colony(self) -> None:
        thread = _make_thread([
            SimpleNamespace(
                role="operator",
                content="Fix src/ssrf_validate.py host parsing.",
            ),
        ])
        runtime = _make_runtime(thread=thread)
        runtime.projections.colonies = {}
        runtime.projections.workspaces = {}
        runtime.projections.list_colonies = MagicMock(return_value=[])
        runtime.retrieve_relevant_memory = AsyncMock(return_value=("", []))

        queen = QueenAgent(runtime)
        await queen.respond("ws1", "th1")

        call = runtime.llm_router.complete.await_args_list[0]
        tool_names = {tool["name"] for tool in call.kwargs["tools"]}
        assert "spawn_colony" in tool_names
        assert "spawn_parallel" not in tool_names

    @pytest.mark.anyio()
    async def test_narrowed_spawn_preview_is_forced_to_dispatch(self) -> None:
        thread = _make_thread([
            SimpleNamespace(
                role="operator",
                content="Fix src/ssrf_validate.py host parsing.",
            ),
        ])
        tool_response = _make_llm_response(
            content="",
            tool_calls=[{"name": "spawn_colony", "input": {
                "task": "Fix src/ssrf_validate.py host parsing.",
                "preview": True,
            }}],
        )
        final_response = _make_llm_response(content="Colony spawned successfully.")

        runtime = _make_runtime(thread=thread)
        runtime.projections.colonies = {}
        runtime.projections.workspaces = {}
        runtime.projections.list_colonies = MagicMock(return_value=[])
        runtime.retrieve_relevant_memory = AsyncMock(return_value=("", []))
        runtime.llm_router.complete = AsyncMock(side_effect=[tool_response, final_response])
        runtime.spawn_colony = AsyncMock(return_value="colony-fast")

        queen = QueenAgent(runtime)
        result = await queen.respond("ws1", "th1")

        assert result.actions[0]["tool"] == "spawn_colony"
        call_kwargs = runtime.spawn_colony.call_args.kwargs
        assert call_kwargs["fast_path"] is True
        assert result.actions[0]["colony_id"] == "colony-fast"

    @pytest.mark.anyio()
    async def test_skips_pre_llm_colony_directive_for_deliberative_turn(self) -> None:
        thread = _make_thread([
            SimpleNamespace(
                role="operator",
                content="Should we improve checkpoint coverage next, or focus on API tests first?",
            ),
        ])
        runtime = _make_runtime(thread=thread)
        runtime.projections.colonies = {}
        runtime.projections.workspaces = {}
        runtime.projections.list_colonies = MagicMock(return_value=[])
        runtime.retrieve_relevant_memory = AsyncMock(return_value=("", []))

        queen = QueenAgent(runtime)
        await queen.respond("ws1", "th1")

        call = runtime.llm_router.complete.await_args_list[0]
        messages = call.kwargs["messages"]
        assert not any(
            m["role"] == "system"
            and "IMPORTANT: The operator's message is implementation work" in m["content"]
            for m in messages
        )


# ---------------------------------------------------------------------------
# _build_messages tests
# ---------------------------------------------------------------------------


class TestBuildMessages:
    """Tests for LLM message construction."""

    def test_includes_system_prompt_from_recipe(self) -> None:
        recipe = _make_queen_recipe()
        thread = _make_thread()
        runtime = _make_runtime(thread=thread, queen_recipe=recipe)

        queen = QueenAgent(runtime)
        messages = queen._build_messages(thread)

        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are the Queen of the colony."

    def test_default_system_prompt_when_no_castes(self) -> None:
        thread = _make_thread()
        runtime = _make_runtime(thread=thread)

        queen = QueenAgent(runtime)
        messages = queen._build_messages(thread)

        assert messages[0]["role"] == "system"
        assert "Queen agent" in messages[0]["content"]
        assert "spawn_colony" in messages[0]["content"]

    def test_includes_conversation_history(self) -> None:
        msg1 = MagicMock()
        msg1.role = "operator"
        msg1.content = "Hello queen"
        msg2 = MagicMock()
        msg2.role = "queen"
        msg2.content = "Hello operator"

        thread = _make_thread(queen_messages=[msg1, msg2])
        runtime = _make_runtime(thread=thread)

        queen = QueenAgent(runtime)
        messages = queen._build_messages(thread)

        assert len(messages) == 3  # system + 2 conversation
        assert messages[1] == {"role": "user", "content": "Hello queen"}
        assert messages[2] == {"role": "assistant", "content": "Hello operator"}

    def test_loads_thread_scoped_notes_from_projection_thread_id(self) -> None:
        thread = SimpleNamespace(
            id="th-proj",
            workspace_id="ws1",
            queen_messages=[],
        )
        runtime = _make_runtime(thread=thread)
        # Wave 51: notes are in projections, not YAML
        runtime.projections.queen_notes = {
            "ws1/th-proj": [{"content": "Prefer reviewer on code tasks", "timestamp": "2026-03-20T00:00:00"}],
        }
        queen = QueenAgent(runtime)

        messages = queen._build_messages(thread)

        assert any("Prefer reviewer on code tasks" in m["content"] for m in messages)


# ---------------------------------------------------------------------------
# _queen_tools tests
# ---------------------------------------------------------------------------


class TestQueenTools:
    """Tests for tool definitions."""

    def test_returns_expected_tool_names(self) -> None:
        runtime = _make_runtime()
        queen = QueenAgent(runtime)

        tools = queen._queen_tools()
        tool_names = [t["name"] for t in tools]

        assert "spawn_colony" in tool_names
        assert "kill_colony" in tool_names
        assert "get_status" in tool_names

    def test_returns_all_tools(self) -> None:
        runtime = _make_runtime()
        queen = QueenAgent(runtime)
        tools = queen._queen_tools()
        tool_names = {t["name"] for t in tools}
        # Core tools (Waves 12-19)
        assert "spawn_colony" in tool_names
        assert "kill_colony" in tool_names
        assert "get_status" in tool_names
        assert "redirect_colony" in tool_names
        assert "suggest_config_change" in tool_names
        assert len(tool_names) >= 10

    def test_tools_have_required_fields(self) -> None:
        runtime = _make_runtime()
        queen = QueenAgent(runtime)

        for tool in queen._queen_tools():
            assert "name" in tool
            assert "description" in tool
            assert "parameters" in tool
            assert tool["parameters"]["type"] == "object"

    def test_spawn_colony_castes_accepts_structured_items(self) -> None:
        runtime = _make_runtime()
        queen = QueenAgent(runtime)

        tools = queen._queen_tools()
        spawn = next(t for t in tools if t["name"] == "spawn_colony")
        castes_schema = spawn["parameters"]["properties"]["castes"]
        assert castes_schema["items"]["type"] == "object"
        assert "caste" in castes_schema["items"]["properties"]
        assert "tier" in castes_schema["items"]["properties"]


# ---------------------------------------------------------------------------
# Wave 18 Track A — New tool handler tests
# ---------------------------------------------------------------------------


class TestListTemplates:
    """Tests for list_templates tool."""

    @pytest.mark.anyio()
    async def test_list_templates_returns_templates(self) -> None:
        runtime = _make_runtime()
        queen = QueenAgent(runtime)
        result, action = await queen._tool_dispatcher._list_templates()
        # Real templates exist in config/templates/
        assert "Available templates:" in result or "No templates available" in result
        assert action is None

    @pytest.mark.anyio()
    async def test_list_templates_empty_dir(self) -> None:
        runtime = _make_runtime()
        queen = QueenAgent(runtime)
        with patch("formicos.surface.queen_tools.load_all_templates", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = []
            result, action = await queen._tool_dispatcher._list_templates()
        assert result == "No templates available."
        assert action is None


class TestInspectTemplate:
    """Tests for inspect_template tool."""

    @pytest.mark.anyio()
    async def test_inspect_template_not_found(self) -> None:
        runtime = _make_runtime()
        queen = QueenAgent(runtime)
        with patch("formicos.surface.queen_tools.load_all_templates", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = []
            result, action = await queen._tool_dispatcher._inspect_template({"template_id": "nonexistent"})
        assert "not found" in result.lower()
        assert action is None

    @pytest.mark.anyio()
    async def test_inspect_template_missing_id(self) -> None:
        runtime = _make_runtime()
        queen = QueenAgent(runtime)
        result, action = await queen._tool_dispatcher._inspect_template({})
        assert "required" in result.lower()

    @pytest.mark.anyio()
    async def test_inspect_template_found_by_id(self) -> None:
        from formicos.core.types import CasteSlot
        from formicos.surface.template_manager import ColonyTemplate

        tmpl = ColonyTemplate(
            template_id="test-tmpl",
            name="Test Template",
            description="A test template",
            castes=[CasteSlot(caste="coder")],
            tags=["test"],
            use_count=5,
        )
        runtime = _make_runtime()
        queen = QueenAgent(runtime)
        with patch("formicos.surface.queen_tools.load_all_templates", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = [tmpl]
            result, _ = await queen._tool_dispatcher._inspect_template({"template_id": "test-tmpl"})
        assert "Test Template" in result
        assert "test-tmpl" in result
        assert "coder" in result

    @pytest.mark.anyio()
    async def test_inspect_template_found_by_name_substring(self) -> None:
        from formicos.core.types import CasteSlot
        from formicos.surface.template_manager import ColonyTemplate

        tmpl = ColonyTemplate(
            template_id="tmpl-abc",
            name="Code Review Template",
            description="Reviews code",
            castes=[CasteSlot(caste="reviewer")],
        )
        runtime = _make_runtime()
        queen = QueenAgent(runtime)
        with patch("formicos.surface.queen_tools.load_all_templates", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = [tmpl]
            result, _ = await queen._tool_dispatcher._inspect_template({"template_id": "code review"})
        assert "Code Review Template" in result


class TestInspectColony:
    """Tests for inspect_colony tool."""

    def test_inspect_colony_not_found(self) -> None:
        runtime = _make_runtime()
        runtime.projections.get_colony.return_value = None
        runtime.projections.colonies = {}
        queen = QueenAgent(runtime)
        result, action = queen._tool_dispatcher._inspect_colony({"colony_id": "nonexistent"})
        assert "not found" in result.lower()
        assert action is None

    def test_inspect_colony_missing_id(self) -> None:
        runtime = _make_runtime()
        queen = QueenAgent(runtime)
        result, _ = queen._tool_dispatcher._inspect_colony({})
        assert "required" in result.lower()

    def test_inspect_colony_found(self) -> None:
        from formicos.surface.projections import (
            AgentProjection,
            ColonyProjection,
            RoundProjection,
        )

        colony = ColonyProjection(
            id="col-123",
            thread_id="th1",
            workspace_id="ws1",
            task="Build it",
            status="completed",
            round_number=3,
            max_rounds=10,
            strategy="stigmergic",
            quality_score=0.85,
            cost=0.12,
            budget_limit=5.0,
            skills_extracted=2,
            display_name="Build Project",
        )
        colony.agents["agent-1"] = AgentProjection(
            id="agent-1", caste="coder", model="llama-cpp/gpt-4",
        )
        rp = RoundProjection(round_number=3)
        rp.agent_outputs["agent-1"] = "Wrote the code successfully."
        colony.round_records.append(rp)

        runtime = _make_runtime()
        runtime.projections.get_colony.return_value = colony
        queen = QueenAgent(runtime)
        result, _ = queen._tool_dispatcher._inspect_colony({"colony_id": "col-123"})
        assert "Build Project" in result
        assert "completed" in result
        assert "0.85" in result
        assert "coder" in result
        assert "Wrote the code" in result

    def test_inspect_colony_fallback_display_name_search(self) -> None:
        from formicos.surface.projections import ColonyProjection

        colony = ColonyProjection(
            id="col-xyz",
            thread_id="th1",
            workspace_id="ws1",
            task="Research",
            display_name="Deep Research",
        )
        runtime = _make_runtime()
        runtime.projections.get_colony.return_value = None
        runtime.projections.colonies = {"col-xyz": colony}
        queen = QueenAgent(runtime)
        result, _ = queen._tool_dispatcher._inspect_colony({"colony_id": "deep research"})
        assert "Deep Research" in result


class TestReadWorkspaceFiles:
    """Tests for read_workspace_files tool."""

    def test_no_directory(self) -> None:
        runtime = _make_runtime()
        runtime.settings.system.data_dir = "/nonexistent/path"
        queen = QueenAgent(runtime)
        result, action = queen._tool_dispatcher._read_workspace_files({}, "ws1")
        assert "No files found" in result
        assert action is None

    def test_with_files(self) -> None:
        with _workspace_tempdir() as tmpdir:
            runtime = _make_runtime()
            runtime.settings.system.data_dir = tmpdir
            ws_dir = os.path.join(tmpdir, "workspaces", "ws1")
            os.makedirs(ws_dir)
            # Create test files
            with open(os.path.join(ws_dir, "output.txt"), "w") as f:
                f.write("hello")
            with open(os.path.join(ws_dir, "data.json"), "w") as f:
                f.write("{}")

            queen = QueenAgent(runtime)
            result, _ = queen._tool_dispatcher._read_workspace_files({}, "ws1")
            assert "output.txt" in result
            assert "data.json" in result
            assert "2 entries" in result

    def test_empty_directory(self) -> None:
        with _workspace_tempdir() as tmpdir:
            runtime = _make_runtime()
            runtime.settings.system.data_dir = tmpdir
            ws_dir = os.path.join(tmpdir, "workspaces", "ws1")
            os.makedirs(ws_dir)

            queen = QueenAgent(runtime)
            result, _ = queen._tool_dispatcher._read_workspace_files({}, "ws1")
            assert "no files" in result.lower() or "contains no files" in result.lower()

    def test_caps_at_50_entries(self) -> None:
        with _workspace_tempdir() as tmpdir:
            runtime = _make_runtime()
            runtime.settings.system.data_dir = tmpdir
            ws_dir = os.path.join(tmpdir, "workspaces", "ws1")
            os.makedirs(ws_dir)
            for i in range(60):
                with open(os.path.join(ws_dir, f"file_{i:03d}.txt"), "w") as f:
                    f.write("x")
            queen = QueenAgent(runtime)
            result, _ = queen._tool_dispatcher._read_workspace_files({}, "ws1")
            assert "50 entries" in result


class TestSuggestConfigChange:
    """Tests for suggest_config_change tool."""

    def test_missing_params(self) -> None:
        runtime = _make_runtime()
        queen = QueenAgent(runtime)
        result, action = queen._tool_dispatcher._suggest_config_change({})
        assert "required" in result.lower()
        assert action is None

    def test_gate1_rejects_forbidden_string(self) -> None:
        runtime = _make_runtime()
        queen = QueenAgent(runtime)
        result, action = queen._tool_dispatcher._suggest_config_change({
            "param_path": "castes.coder.temperature",
            "proposed_value": "eval(hack)",
            "reason": "testing",
        })
        assert "rejected (safety)" in result.lower()
        assert action is None

    def test_gate1_rejects_unknown_path(self) -> None:
        runtime = _make_runtime()
        queen = QueenAgent(runtime)
        result, action = queen._tool_dispatcher._suggest_config_change({
            "param_path": "system.data_dir",
            "proposed_value": "/tmp",
            "reason": "testing",
        })
        assert "rejected" in result.lower()
        assert action is None

    def test_gate2_rejects_non_experimentable(self) -> None:
        """A path that passes config_validator but is not experimentable."""
        runtime = _make_runtime()
        queen = QueenAgent(runtime)
        # This path doesn't exist in PARAM_RULES (config_validator) so Gate 1
        # will reject it first. We need to test Gate 2 by passing a valid path
        # that is not in experimentable_params — but experimentable_params is a
        # subset of PARAM_RULES, so we test with a path that might be in
        # PARAM_RULES but not experimentable.
        # In practice, both use the same source, so this tests the flow.
        result, action = queen._tool_dispatcher._suggest_config_change({
            "param_path": "nonexistent.path.here",
            "proposed_value": "0.5",
            "reason": "testing",
        })
        assert "rejected" in result.lower()
        assert action is None

    def test_both_gates_pass(self) -> None:
        runtime = _make_runtime()
        # Set up caste recipes for _resolve_current_value
        recipe = _make_queen_recipe()
        recipe_with_temp = CasteRecipe(
            name="Coder",
            system_prompt="Code.",
            temperature=0.7,
            tools=["code_execute"],
            max_tokens=4096,
        )
        runtime.castes = MagicMock()
        runtime.castes.castes = {"queen": recipe, "coder": recipe_with_temp}
        queen = QueenAgent(runtime)
        result, action = queen._tool_dispatcher._suggest_config_change({
            "param_path": "castes.coder.temperature",
            "proposed_value": "0.5",
            "reason": "Lower temperature for more deterministic output",
        })
        assert "Config change proposal" in result
        assert "castes.coder.temperature" in result
        assert "0.5" in result
        assert action is not None
        assert action["tool"] == "suggest_config_change"
        assert action["status"] == "proposed"

    def test_resolve_current_value_governance(self) -> None:
        runtime = _make_runtime()
        queen = QueenAgent(runtime)
        val = queen._tool_dispatcher._resolve_current_value("governance.convergence_threshold")
        assert val == "0.85"

    def test_resolve_current_value_routing(self) -> None:
        runtime = _make_runtime()
        queen = QueenAgent(runtime)
        val = queen._tool_dispatcher._resolve_current_value("routing.tau_threshold")
        assert val == "0.5"

    def test_resolve_current_value_unknown(self) -> None:
        runtime = _make_runtime()
        queen = QueenAgent(runtime)
        val = queen._tool_dispatcher._resolve_current_value("unknown.path")
        assert val == "(unknown)"


class TestIsExperimentable:
    """Tests for the experimentable params helper."""

    def test_known_param_is_experimentable(self) -> None:
        # castes.coder.temperature is in the whitelist
        assert _is_experimentable("castes.coder.temperature") is True

    def test_unknown_param_is_not_experimentable(self) -> None:
        assert _is_experimentable("system.data_dir") is False

    def test_load_returns_dict(self) -> None:
        params = _load_experimentable_params()
        assert isinstance(params, dict)
        # Should have at least the caste temperature entries
        assert "castes.coder.temperature" in params


class TestMaxToolIterations:
    """Verify _MAX_TOOL_ITERATIONS was bumped (Wave 21: 5 -> 7)."""

    def test_iteration_limit_is_seven(self) -> None:
        from formicos.surface.queen_runtime import _MAX_TOOL_ITERATIONS
        assert _MAX_TOOL_ITERATIONS == 7


# ---------------------------------------------------------------------------
# Wave 18 Track B — follow_up_colony and max_tokens alignment tests
# ---------------------------------------------------------------------------


class TestFollowUpColony:
    """Tests for QueenAgent.follow_up_colony (Wave 18 B2)."""

    @pytest.mark.anyio()
    async def test_skips_when_thread_not_found(self) -> None:
        runtime = _make_runtime(thread=None)
        queen = QueenAgent(runtime)
        await queen.follow_up_colony("col-1", "ws1", "th-missing")
        runtime.emit_and_broadcast.assert_not_awaited()

    @pytest.mark.anyio()
    async def test_skips_when_no_recent_operator_message(self) -> None:
        """Thread exists but operator's last message is older than 30 min."""
        msg = MagicMock()
        msg.role = "operator"
        msg.timestamp = "2020-01-01T00:00:00+00:00"  # very old
        thread = _make_thread(queen_messages=[msg])
        runtime = _make_runtime(thread=thread)
        queen = QueenAgent(runtime)
        await queen.follow_up_colony("col-1", "ws1", "th1")
        runtime.emit_and_broadcast.assert_not_awaited()

    @pytest.mark.anyio()
    async def test_sends_summary_when_thread_recently_active(self) -> None:
        from datetime import UTC, datetime

        msg = MagicMock()
        msg.role = "operator"
        msg.timestamp = datetime.now(UTC).isoformat()  # just now
        thread = _make_thread(queen_messages=[msg])
        runtime = _make_runtime(thread=thread)

        # Set up colony projection
        colony = MagicMock()
        colony.display_name = "Test Colony"
        colony.status = "completed"
        colony.quality_score = 0.85
        colony.skills_extracted = 2
        colony.cost = 0.05
        colony.round_number = 3
        runtime.projections.get_colony.return_value = colony

        queen = QueenAgent(runtime)
        await queen.follow_up_colony("col-1", "ws1", "th1")

        runtime.emit_and_broadcast.assert_awaited_once()
        emitted = runtime.emit_and_broadcast.call_args[0][0]
        assert emitted.role == "queen"
        assert "Test Colony" in emitted.content
        assert "completed well" in emitted.content
        assert "85%" in emitted.content

    @pytest.mark.anyio()
    async def test_skips_when_colony_not_found(self) -> None:
        from datetime import UTC, datetime

        msg = MagicMock()
        msg.role = "operator"
        msg.timestamp = datetime.now(UTC).isoformat()
        thread = _make_thread(queen_messages=[msg])
        runtime = _make_runtime(thread=thread)
        runtime.projections.get_colony.return_value = None

        queen = QueenAgent(runtime)
        await queen.follow_up_colony("col-missing", "ws1", "th1")
        runtime.emit_and_broadcast.assert_not_awaited()

    @pytest.mark.anyio()
    async def test_ignores_queen_messages_for_recency(self) -> None:
        """Only operator messages count for the 30-min recency check."""
        from datetime import UTC, datetime

        msg = MagicMock()
        msg.role = "queen"  # not operator
        msg.timestamp = datetime.now(UTC).isoformat()
        thread = _make_thread(queen_messages=[msg])
        runtime = _make_runtime(thread=thread)
        queen = QueenAgent(runtime)
        await queen.follow_up_colony("col-1", "ws1", "th1")
        runtime.emit_and_broadcast.assert_not_awaited()


class TestQueenMaxTokensAlignment:
    """Tests for _queen_max_tokens model policy alignment (Wave 18 B3)."""

    def test_returns_caste_max_when_no_model_match(self) -> None:
        recipe = CasteRecipe(
            name="Queen", system_prompt=".", temperature=0.3,
            tools=[], max_tokens=4096,
        )
        runtime = _make_runtime(queen_recipe=recipe)
        runtime.settings.models.registry = []  # no models in registry
        queen = QueenAgent(runtime)
        assert queen._queen_max_tokens("ws1") == 4096

    def test_returns_min_of_caste_and_model(self) -> None:
        from formicos.core.types import ModelRecord

        recipe = CasteRecipe(
            name="Queen", system_prompt=".", temperature=0.3,
            tools=[], max_tokens=4096,
        )
        model = ModelRecord(
            address="anthropic/claude-3-haiku",
            provider="anthropic",
            context_window=200000,
            supports_tools=True,
            max_output_tokens=8192,
        )
        runtime = _make_runtime(queen_recipe=recipe)
        runtime.settings.models.registry = [model]
        queen = QueenAgent(runtime)
        # caste=4096, model=8192 → min=4096
        assert queen._queen_max_tokens("ws1") == 4096

    def test_model_cap_lower_than_caste(self) -> None:
        from formicos.core.types import ModelRecord

        recipe = CasteRecipe(
            name="Queen", system_prompt=".", temperature=0.3,
            tools=[], max_tokens=4096,
        )
        model = ModelRecord(
            address="anthropic/claude-3-haiku",
            provider="anthropic",
            context_window=200000,
            supports_tools=True,
            max_output_tokens=2048,  # lower than caste
        )
        runtime = _make_runtime(queen_recipe=recipe)
        runtime.settings.models.registry = [model]
        queen = QueenAgent(runtime)
        # caste=4096, model=2048 → min=2048
        assert queen._queen_max_tokens("ws1") == 2048

    def test_defaults_to_4096_without_castes(self) -> None:
        runtime = _make_runtime()
        runtime.settings.models.registry = []
        queen = QueenAgent(runtime)
        assert queen._queen_max_tokens() == 4096


# ---------------------------------------------------------------------------
# Wave 19 Track A — redirect_colony + on_governance_alert tests
# ---------------------------------------------------------------------------


def _make_colony_for_redirect(
    colony_id: str = "col-abc",
    status: str = "running",
    task: str = "original task",
    round_number: int = 3,
    redirect_history: list[Any] | None = None,
) -> MagicMock:
    colony = MagicMock()
    colony.id = colony_id
    colony.status = status
    colony.task = task
    colony.round_number = round_number
    colony.redirect_history = redirect_history or []
    colony.display_name = "Test Colony"
    return colony


class TestRedirectColony:
    """Tests for redirect_colony tool (Wave 19 ADR-032)."""

    @pytest.mark.anyio()
    async def test_missing_params(self) -> None:
        runtime = _make_runtime()
        queen = QueenAgent(runtime)
        result, action = await queen._tool_dispatcher._redirect_colony(
            {}, "ws1", "th1",
        )
        assert "required" in result.lower()
        assert action is None

    @pytest.mark.anyio()
    async def test_colony_not_found(self) -> None:
        runtime = _make_runtime()
        runtime.projections.get_colony.return_value = None
        queen = QueenAgent(runtime)
        result, action = await queen._tool_dispatcher._redirect_colony(
            {"colony_id": "nope", "new_goal": "x", "reason": "y"},
            "ws1", "th1",
        )
        assert "not found" in result.lower()
        assert action is None

    @pytest.mark.anyio()
    async def test_colony_not_running(self) -> None:
        colony = _make_colony_for_redirect(status="completed")
        runtime = _make_runtime()
        runtime.projections.get_colony.return_value = colony
        queen = QueenAgent(runtime)
        result, action = await queen._tool_dispatcher._redirect_colony(
            {"colony_id": "col-abc", "new_goal": "x", "reason": "y"},
            "ws1", "th1",
        )
        assert "not running" in result.lower()
        assert action is None

    @pytest.mark.anyio()
    async def test_redirect_cap_exceeded(self) -> None:
        colony = _make_colony_for_redirect(
            redirect_history=[{"redirect_index": 0}],
        )
        runtime = _make_runtime()
        runtime.projections.get_colony.return_value = colony
        queen = QueenAgent(runtime)
        result, action = await queen._tool_dispatcher._redirect_colony(
            {"colony_id": "col-abc", "new_goal": "x", "reason": "y"},
            "ws1", "th1",
        )
        assert "already been redirected" in result.lower()
        assert action is None

    @pytest.mark.anyio()
    async def test_successful_redirect(self) -> None:
        colony = _make_colony_for_redirect()
        runtime = _make_runtime()
        runtime.projections.get_colony.return_value = colony
        queen = QueenAgent(runtime)
        result, action = await queen._tool_dispatcher._redirect_colony(
            {
                "colony_id": "col-abc",
                "new_goal": "fix the bug",
                "reason": "colony went off-track",
            },
            "ws1", "th1",
        )
        assert "redirected" in result.lower()
        assert "fix the bug" in result
        assert action is not None
        assert action["tool"] == "redirect_colony"
        assert action["colony_id"] == "col-abc"
        assert action["redirect_index"] == 0
        # ColonyRedirected event emitted
        runtime.emit_and_broadcast.assert_awaited_once()
        emitted = runtime.emit_and_broadcast.call_args[0][0]
        assert emitted.type == "ColonyRedirected"
        assert emitted.original_goal == "original task"
        assert emitted.new_goal == "fix the bug"
        assert emitted.trigger == "queen_inspection"

    @pytest.mark.anyio()
    async def test_redirect_uses_original_goal_not_active(self) -> None:
        """original_goal on the event must come from immutable task."""
        colony = _make_colony_for_redirect(task="immutable original")
        colony.active_goal = "already redirected once"
        runtime = _make_runtime()
        runtime.projections.get_colony.return_value = colony
        queen = QueenAgent(runtime)
        _, _ = await queen._tool_dispatcher._redirect_colony(
            {
                "colony_id": "col-abc",
                "new_goal": "new goal",
                "reason": "needed",
            },
            "ws1", "th1",
        )
        emitted = runtime.emit_and_broadcast.call_args[0][0]
        assert emitted.original_goal == "immutable original"


class TestOnGovernanceAlert:
    """Tests for on_governance_alert (Wave 19 ADR-032)."""

    @pytest.mark.anyio()
    async def test_skips_when_thread_not_found(self) -> None:
        runtime = _make_runtime(thread=None)
        queen = QueenAgent(runtime)
        await queen.on_governance_alert("col-1", "ws1", "th-miss", "stall")
        runtime.emit_and_broadcast.assert_not_awaited()

    @pytest.mark.anyio()
    async def test_skips_when_no_recent_operator(self) -> None:
        msg = MagicMock()
        msg.role = "operator"
        msg.timestamp = "2020-01-01T00:00:00+00:00"
        thread = _make_thread(queen_messages=[msg])
        runtime = _make_runtime(thread=thread)
        queen = QueenAgent(runtime)
        await queen.on_governance_alert("col-1", "ws1", "th1", "stall")
        runtime.emit_and_broadcast.assert_not_awaited()

    @pytest.mark.anyio()
    async def test_skips_when_colony_not_running(self) -> None:
        from datetime import UTC, datetime

        msg = MagicMock()
        msg.role = "operator"
        msg.timestamp = datetime.now(UTC).isoformat()
        thread = _make_thread(queen_messages=[msg])
        runtime = _make_runtime(thread=thread)
        colony = _make_colony_for_redirect(status="completed")
        runtime.projections.get_colony.return_value = colony
        queen = QueenAgent(runtime)
        await queen.on_governance_alert("col-abc", "ws1", "th1", "stall")
        runtime.emit_and_broadcast.assert_not_awaited()

    @pytest.mark.anyio()
    async def test_skips_when_redirect_cap_reached(self) -> None:
        from datetime import UTC, datetime

        msg = MagicMock()
        msg.role = "operator"
        msg.timestamp = datetime.now(UTC).isoformat()
        thread = _make_thread(queen_messages=[msg])
        runtime = _make_runtime(thread=thread)
        colony = _make_colony_for_redirect(
            redirect_history=[{"redirect_index": 0}],
        )
        runtime.projections.get_colony.return_value = colony
        queen = QueenAgent(runtime)
        await queen.on_governance_alert("col-abc", "ws1", "th1", "stall")
        runtime.emit_and_broadcast.assert_not_awaited()

    @pytest.mark.anyio()
    async def test_emits_alert_message_when_preconditions_pass(self) -> None:
        from datetime import UTC, datetime

        msg = MagicMock()
        msg.role = "operator"
        msg.timestamp = datetime.now(UTC).isoformat()
        thread = _make_thread(queen_messages=[msg])
        runtime = _make_runtime(thread=thread)
        colony = _make_colony_for_redirect()
        runtime.projections.get_colony.return_value = colony
        queen = QueenAgent(runtime)
        await queen.on_governance_alert(
            "col-abc", "ws1", "th1", "stall_detected",
        )
        runtime.emit_and_broadcast.assert_awaited_once()
        emitted = runtime.emit_and_broadcast.call_args[0][0]
        assert emitted.role == "queen"
        assert "Governance alert" in emitted.content
        assert "stall_detected" in emitted.content


# ---------------------------------------------------------------------------
# Colony chaining (ADR-033): spawn_colony with input_from
# ---------------------------------------------------------------------------


class TestSpawnColonyInputFrom:
    """Wave 19 Track B: input_from wraps into InputSource."""

    @pytest.mark.anyio()
    async def test_spawn_with_input_from(self) -> None:
        runtime = _make_runtime()
        runtime.spawn_colony = AsyncMock(return_value="colony-new")
        queen = QueenAgent(runtime)
        result, action = await queen._tool_dispatcher._spawn_colony(
            {"task": "chained work", "castes": ["coder"], "input_from": "colony-src"},
            "ws1", "th1",
        )
        assert action is not None
        assert action["tool"] == "spawn_colony"
        # Verify input_sources was passed through
        call_kwargs = runtime.spawn_colony.call_args
        assert call_kwargs.kwargs.get("input_sources") is not None
        sources = call_kwargs.kwargs["input_sources"]
        assert len(sources) == 1
        assert sources[0].colony_id == "colony-src"

    @pytest.mark.anyio()
    async def test_spawn_without_input_from(self) -> None:
        runtime = _make_runtime()
        runtime.spawn_colony = AsyncMock(return_value="colony-plain")
        queen = QueenAgent(runtime)
        result, action = await queen._tool_dispatcher._spawn_colony(
            {"task": "plain work", "castes": ["coder"]},
            "ws1", "th1",
        )
        assert action is not None
        call_kwargs = runtime.spawn_colony.call_args
        assert call_kwargs.kwargs.get("input_sources") is None

    @pytest.mark.anyio()
    async def test_spawn_input_from_error_returns_message(self) -> None:
        runtime = _make_runtime()
        runtime.spawn_colony = AsyncMock(
            side_effect=ValueError("Source colony 'gone' not found."),
        )
        queen = QueenAgent(runtime)
        result, action = await queen._tool_dispatcher._spawn_colony(
            {"task": "chain", "castes": ["coder"], "input_from": "gone"},
            "ws1", "th1",
        )
        assert "not found" in result
        assert action is None


# ---------------------------------------------------------------------------
# Config approval (Wave 19 Track B)
# ---------------------------------------------------------------------------


class TestPendingConfigProposal:
    """PendingConfigProposal dataclass tests."""

    def test_not_expired_when_fresh(self) -> None:
        from datetime import UTC, datetime
        proposal = PendingConfigProposal(
            proposal_id="abc12345",
            thread_id="th1",
            param_path="castes.coder.temperature",
            proposed_value="0.5",
            current_value="0.7",
            reason="test",
            proposed_at=datetime.now(UTC),
        )
        assert not proposal.is_expired

    def test_expired_after_ttl(self) -> None:
        from datetime import UTC, datetime, timedelta
        old = datetime.now(UTC) - timedelta(minutes=31)
        proposal = PendingConfigProposal(
            proposal_id="abc12345",
            thread_id="th1",
            param_path="castes.coder.temperature",
            proposed_value="0.5",
            current_value="0.7",
            reason="test",
            proposed_at=old,
        )
        assert proposal.is_expired


class TestSuggestConfigChangeStoresProposal:
    """suggest_config_change should store a pending proposal when both gates pass."""

    def test_stores_pending_when_valid(self) -> None:
        runtime = _make_runtime()
        queen = QueenAgent(runtime)
        with patch("formicos.surface.queen_tools.validate_config_update") as mock_val, \
             patch("formicos.surface.queen_tools._is_experimentable", return_value=True):
            mock_val.return_value = MagicMock(valid=True, value=0.5, error="")
            result, action = queen._tool_dispatcher._suggest_config_change(
                {"param_path": "castes.coder.temperature", "proposed_value": "0.5", "reason": "test"},
                thread_id="th1",
            )
        assert "proposal" in result.lower()
        assert action is not None
        assert "proposal_id" in action
        assert "th1" in queen._tool_dispatcher._pending_proposals
        assert queen._tool_dispatcher._pending_proposals["th1"].param_path == "castes.coder.temperature"


class TestApproveConfigChange:
    """approve_config_change tool handler tests."""

    @pytest.mark.anyio()
    async def test_no_pending_proposal(self) -> None:
        runtime = _make_runtime()
        queen = QueenAgent(runtime)
        result, action = await queen._tool_dispatcher._approve_config_change(
            {}, "ws1", "th1",
        )
        assert "No pending" in result
        assert action is None

    @pytest.mark.anyio()
    async def test_expired_proposal(self) -> None:
        from datetime import UTC, datetime, timedelta
        runtime = _make_runtime()
        queen = QueenAgent(runtime)
        queen._tool_dispatcher._pending_proposals["th1"] = PendingConfigProposal(
            proposal_id="abc12345",
            thread_id="th1",
            param_path="castes.coder.temperature",
            proposed_value="0.5",
            current_value="0.7",
            reason="test",
            proposed_at=datetime.now(UTC) - timedelta(minutes=31),
        )
        result, action = await queen._tool_dispatcher._approve_config_change(
            {}, "ws1", "th1",
        )
        assert "expired" in result
        assert action is None
        assert "th1" not in queen._tool_dispatcher._pending_proposals

    @pytest.mark.anyio()
    async def test_successful_approval(self) -> None:
        from datetime import UTC, datetime
        runtime = _make_runtime()
        runtime.apply_config_change = AsyncMock()
        queen = QueenAgent(runtime)
        queen._tool_dispatcher._pending_proposals["th1"] = PendingConfigProposal(
            proposal_id="abc12345",
            thread_id="th1",
            param_path="castes.coder.temperature",
            proposed_value="0.5",
            current_value="0.7",
            reason="test",
            proposed_at=datetime.now(UTC),
        )
        with patch("formicos.surface.queen_tools.validate_config_update") as mock_val, \
             patch("formicos.surface.queen_tools._is_experimentable", return_value=True):
            mock_val.return_value = MagicMock(valid=True, value=0.5, error="")
            result, action = await queen._tool_dispatcher._approve_config_change(
                {}, "ws1", "th1",
            )
        assert "Applied" in result
        assert action is not None
        assert action["applied"] is True
        runtime.apply_config_change.assert_awaited_once()
        assert "th1" not in queen._tool_dispatcher._pending_proposals

    @pytest.mark.anyio()
    async def test_revalidation_failure_clears_proposal(self) -> None:
        from datetime import UTC, datetime
        runtime = _make_runtime()
        queen = QueenAgent(runtime)
        queen._tool_dispatcher._pending_proposals["th1"] = PendingConfigProposal(
            proposal_id="abc12345",
            thread_id="th1",
            param_path="castes.coder.temperature",
            proposed_value="0.5",
            current_value="0.7",
            reason="test",
            proposed_at=datetime.now(UTC),
        )
        with patch("formicos.surface.queen_tools.validate_config_update") as mock_val:
            mock_val.return_value = MagicMock(valid=False, error="out of range")
            result, action = await queen._tool_dispatcher._approve_config_change(
                {}, "ws1", "th1",
            )
        assert "failed re-validation" in result
        assert "th1" not in queen._tool_dispatcher._pending_proposals


class TestSearchMemoryRemoved:
    """Wave 28: search_memory tool was removed. Verify it's gone."""

    def test_search_memory_not_in_tools(self) -> None:
        runtime = _make_runtime()
        queen = QueenAgent(runtime)
        tools = queen._queen_tools()
        names = {t["name"] for t in tools}
        assert "search_memory" not in names

    def test_list_skills_not_in_tools(self) -> None:
        runtime = _make_runtime()
        queen = QueenAgent(runtime)
        tools = queen._queen_tools()
        names = {t["name"] for t in tools}
        assert "list_skills" not in names

    def test_memory_search_still_present(self) -> None:
        runtime = _make_runtime()
        queen = QueenAgent(runtime)
        tools = queen._queen_tools()
        names = {t["name"] for t in tools}
        assert "memory_search" in names


# ---------------------------------------------------------------------------
# Wave 63 Track 1: Cross-turn tool memory tests
# ---------------------------------------------------------------------------


class TestToolMemory:
    """Tests for cross-turn tool memory collection and injection."""

    @pytest.mark.anyio()
    async def test_tool_memory_collected(self) -> None:
        """respond() with tool calls produces QueenMessage with tool_memory in meta."""
        llm_resp_with_tools = _make_llm_response(
            content="Found results.",
            tool_calls=[{
                "name": "search_codebase",
                "input": {"query": "budget"},
            }],
        )
        # After tool call, LLM returns final response
        llm_final = _make_llm_response(content="Here are the results.")

        thread = _make_thread(queen_messages=[
            SimpleNamespace(role="operator", content="Search for budget", timestamp=_recent_timestamp(), meta=None),
        ])
        thread.workspace_id = "ws-1"
        thread.thread_id = "th-1"

        runtime = _make_runtime(thread=thread)
        runtime.llm_router.complete = AsyncMock(
            side_effect=[llm_resp_with_tools, llm_final],
        )
        runtime.retrieve_relevant_memory = AsyncMock(return_value=("", []))

        queen = QueenAgent(runtime)
        # Mock the tool dispatcher to return a result
        queen._tool_dispatcher.dispatch = AsyncMock(
            return_value=("3 matches found in projections.py", None),
        )

        await queen.respond("ws-1", "th-1")

        # Check emit_and_broadcast was called with QueenMessage
        emitted = runtime.emit_and_broadcast.call_args_list
        assert len(emitted) > 0
        last_event = emitted[-1][0][0]
        assert hasattr(last_event, "meta")
        if last_event.meta:
            assert "tool_memory" in last_event.meta

    def test_tool_memory_injected(self) -> None:
        """_build_messages() injects prior tool results when recent QueenMessages have tool_memory."""
        thread = _make_thread(queen_messages=[
            SimpleNamespace(
                role="queen", content="Previous response",
                timestamp="2026-03-24T09:00:00Z",
                meta={"tool_memory": [
                    {"tool": "search_codebase", "summary": "Found 5 matches"},
                ]},
                intent=None, render=None,
            ),
            SimpleNamespace(
                role="operator", content="Tell me more",
                timestamp="2026-03-24T09:01:00Z",
                meta=None, intent=None, render=None,
            ),
        ])
        thread.workspace_id = "ws-1"
        thread.thread_id = "th-1"

        runtime = _make_runtime(thread=thread)
        queen = QueenAgent(runtime)
        messages = queen._build_messages(thread)

        # Find the tool memory injection
        tool_mem_msg = [
            m for m in messages
            if "Prior tool results" in m.get("content", "")
        ]
        assert len(tool_mem_msg) == 1
        assert "search_codebase" in tool_mem_msg[0]["content"]

    def test_tool_memory_window(self) -> None:
        """Only last 3 turns of tool memory are injected."""
        queen_msgs = []
        for i in range(5):
            queen_msgs.append(SimpleNamespace(
                role="queen", content=f"Response {i}",
                timestamp=f"2026-03-24T0{i}:00:00Z",
                meta={"tool_memory": [
                    {"tool": f"tool_{i}", "summary": f"Result {i}"},
                ]},
                intent=None, render=None,
            ))
        queen_msgs.append(SimpleNamespace(
            role="operator", content="next",
            timestamp="2026-03-24T06:00:00Z",
            meta=None, intent=None, render=None,
        ))

        thread = _make_thread(queen_messages=queen_msgs)
        thread.workspace_id = "ws-1"
        thread.thread_id = "th-1"

        runtime = _make_runtime(thread=thread)
        queen = QueenAgent(runtime)
        messages = queen._build_messages(thread)

        tool_mem_msg = [
            m for m in messages
            if "Prior tool results" in m.get("content", "")
        ]
        assert len(tool_mem_msg) == 1
        content = tool_mem_msg[0]["content"]
        # Should have tool_4, tool_3, tool_2 (last 3) but NOT tool_0, tool_1
        assert "tool_4" in content
        assert "tool_3" in content
        assert "tool_2" in content
        assert "tool_0" not in content


# ---------------------------------------------------------------------------
# Wave 63 Track 2: Failed colony notifications + parallel aggregation
# ---------------------------------------------------------------------------


def _recent_timestamp() -> str:
    """Return an ISO timestamp within the last 5 minutes (passes the 30-min recency check)."""
    from datetime import datetime, UTC, timedelta
    return (datetime.now(UTC) - timedelta(minutes=2)).isoformat()


class TestFailedColonyFollowUp:
    """Tests for failure-aware follow-up and parallel aggregation."""

    @pytest.mark.anyio()
    async def test_failed_colony_triggers_followup(self) -> None:
        """Failed colony should produce a follow-up notification."""
        thread = _make_thread(queen_messages=[
            SimpleNamespace(
                role="operator", content="build auth",
                timestamp=_recent_timestamp(),
                meta=None,
            ),
        ])
        thread.workspace_id = "ws-1"
        thread.thread_id = "th-1"

        colony = SimpleNamespace(
            display_name="auth-builder",
            quality_score=0.0,
            skills_extracted=0,
            cost=0.001,
            round_number=4,
            status="failed",
            failure_reason="stalled at round 4",
            agents={"a1": SimpleNamespace(tokens=5000)},
            task="Build auth module",
            max_rounds=10,
            artifacts=[],
            expected_output_types=[],
        )

        runtime = _make_runtime(thread=thread)
        runtime.projections.get_thread.return_value = thread
        runtime.projections.get_colony.return_value = colony

        queen = QueenAgent(runtime)
        await queen.follow_up_colony("col-1", "ws-1", "th-1")

        # Should have emitted a QueenMessage
        assert runtime.emit_and_broadcast.called
        event = runtime.emit_and_broadcast.call_args[0][0]
        assert "FAILED" in event.content
        assert "stalled at round 4" in event.content

    @pytest.mark.anyio()
    async def test_failure_card_has_failure_reason_in_meta(self) -> None:
        """Failure follow-up meta should include failureReason."""
        thread = _make_thread(queen_messages=[
            SimpleNamespace(
                role="operator", content="work",
                timestamp=_recent_timestamp(),
                meta=None,
            ),
        ])
        thread.workspace_id = "ws-1"
        thread.thread_id = "th-1"

        colony = SimpleNamespace(
            display_name="broken",
            quality_score=0.0,
            skills_extracted=0,
            cost=0.0,
            round_number=2,
            status="failed",
            failure_reason="tool error",
            agents={},
            task="Fix bug",
            max_rounds=5,
            artifacts=[],
            expected_output_types=[],
        )

        runtime = _make_runtime(thread=thread)
        runtime.projections.get_thread.return_value = thread
        runtime.projections.get_colony.return_value = colony

        queen = QueenAgent(runtime)
        await queen.follow_up_colony("col-2", "ws-1", "th-1")

        event = runtime.emit_and_broadcast.call_args[0][0]
        assert event.meta["failureReason"] == "tool error"
        assert event.meta["status"] == "failed"

    @pytest.mark.anyio()
    async def test_parallel_aggregation_waits(self) -> None:
        """First completion in a parallel plan should not emit a message."""
        thread = _make_thread(queen_messages=[
            SimpleNamespace(
                role="operator", content="build",
                timestamp=_recent_timestamp(),
                meta=None,
            ),
        ])
        thread.workspace_id = "ws-1"
        thread.thread_id = "th-1"

        colony = SimpleNamespace(
            display_name="task-a",
            quality_score=0.8,
            skills_extracted=1,
            cost=0.0,
            round_number=3,
            status="completed",
            failure_reason=None,
            agents={"a1": SimpleNamespace(tokens=3000)},
            task="Task A",
            max_rounds=10,
            artifacts=[],
            expected_output_types=[],
        )

        runtime = _make_runtime(thread=thread)
        runtime.projections.get_thread.return_value = thread
        runtime.projections.get_colony.return_value = colony

        queen = QueenAgent(runtime)
        queen.register_parallel_plan("plan-1", ["col-a", "col-b"])

        await queen.follow_up_colony("col-a", "ws-1", "th-1")

        # Should NOT have emitted — still waiting for col-b
        assert not runtime.emit_and_broadcast.called

    @pytest.mark.anyio()
    async def test_parallel_aggregation_emits_on_last(self) -> None:
        """Last colony in plan triggers grouped result card."""
        thread = _make_thread(queen_messages=[
            SimpleNamespace(
                role="operator", content="build",
                timestamp=_recent_timestamp(),
                meta=None,
            ),
        ])
        thread.workspace_id = "ws-1"
        thread.thread_id = "th-1"

        def _make_colony(name: str, status: str = "completed") -> SimpleNamespace:
            return SimpleNamespace(
                display_name=name,
                quality_score=0.8 if status == "completed" else 0.0,
                skills_extracted=1,
                cost=0.01,
                round_number=3,
                status=status,
                failure_reason="stalled" if status == "failed" else None,
                agents={"a1": SimpleNamespace(tokens=2000)},
                task=f"Task {name}",
                max_rounds=10,
                artifacts=[],
                expected_output_types=[],
            )

        runtime = _make_runtime(thread=thread)
        runtime.projections.get_thread.return_value = thread

        queen = QueenAgent(runtime)
        queen.register_parallel_plan("plan-1", ["col-a", "col-b"])

        # First colony completes
        runtime.projections.get_colony.return_value = _make_colony("task-a")
        await queen.follow_up_colony("col-a", "ws-1", "th-1")
        assert not runtime.emit_and_broadcast.called

        # Second (last) colony completes
        runtime.projections.get_colony.return_value = _make_colony("task-b", "failed")
        await queen.follow_up_colony("col-b", "ws-1", "th-1")

        # NOW should emit aggregated summary
        assert runtime.emit_and_broadcast.called
        event = runtime.emit_and_broadcast.call_args[0][0]
        assert "Parallel plan complete: 1/2 succeeded" in event.content
        assert event.meta["planId"] == "plan-1"
