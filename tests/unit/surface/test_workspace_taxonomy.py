"""Tests for Wave 68 Track 6: soft workspace taxonomy."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestSetWorkspaceTags:
    @pytest.mark.asyncio
    async def test_emits_config_event(self) -> None:
        """set_workspace_tags emits WorkspaceConfigChanged with correct fields."""
        from formicos.surface.queen_tools import QueenToolDispatcher

        runtime = MagicMock()
        ws = MagicMock()
        ws.config = {}
        runtime.projections.workspaces = {"ws-1": ws}
        runtime.emit_and_broadcast = AsyncMock()

        dispatcher = QueenToolDispatcher(runtime)
        result_text, meta = await dispatcher._set_workspace_tags(
            {"tags": ["python", "web-api"]},
            workspace_id="ws-1",
            thread_id="th-1",
        )

        runtime.emit_and_broadcast.assert_called_once()
        event = runtime.emit_and_broadcast.call_args[0][0]
        assert event.type == "WorkspaceConfigChanged"
        assert event.field == "taxonomy_tags"
        assert event.workspace_id == "ws-1"
        tags = json.loads(event.new_value)
        assert tags == ["python", "web-api"]
        assert "python" in result_text
        assert "web-api" in result_text

    @pytest.mark.asyncio
    async def test_tags_normalized_and_capped(self) -> None:
        """Tags are lowercased, stripped, deduped, capped at 20/50chars."""
        from formicos.surface.queen_tools import QueenToolDispatcher

        runtime = MagicMock()
        ws = MagicMock()
        ws.config = {}
        runtime.projections.workspaces = {"ws-1": ws}
        runtime.emit_and_broadcast = AsyncMock()

        dispatcher = QueenToolDispatcher(runtime)

        # Test normalization
        result_text, _ = await dispatcher._set_workspace_tags(
            {"tags": ["  Python  ", "PYTHON", "Auth", "a" * 100]},
            workspace_id="ws-1",
            thread_id="th-1",
        )

        event = runtime.emit_and_broadcast.call_args[0][0]
        tags = json.loads(event.new_value)
        # Dedup: "python" appears once (case-insensitive)
        assert tags.count("python") == 1
        assert "auth" in tags
        # Long tag capped at 50 chars
        long_tag = [t for t in tags if len(t) == 50]
        assert len(long_tag) == 1

    @pytest.mark.asyncio
    async def test_max_20_tags(self) -> None:
        """No more than 20 tags accepted."""
        from formicos.surface.queen_tools import QueenToolDispatcher

        runtime = MagicMock()
        ws = MagicMock()
        ws.config = {}
        runtime.projections.workspaces = {"ws-1": ws}
        runtime.emit_and_broadcast = AsyncMock()

        dispatcher = QueenToolDispatcher(runtime)
        await dispatcher._set_workspace_tags(
            {"tags": [f"tag-{i}" for i in range(30)]},
            workspace_id="ws-1",
            thread_id="th-1",
        )

        event = runtime.emit_and_broadcast.call_args[0][0]
        tags = json.loads(event.new_value)
        assert len(tags) == 20


class TestThreadContextIncludesTags:
    def test_tags_injected(self) -> None:
        """Thread context includes tags when workspace has them."""
        from formicos.surface.queen_runtime import QueenAgent

        runtime = MagicMock()
        ws = MagicMock()
        ws.config = {"taxonomy_tags": json.dumps(["python", "auth"])}
        thread = MagicMock()
        thread.name = "test-thread"
        thread.goal = "Build auth system"
        thread.status = "active"
        thread.expected_outputs = []
        thread.colony_count = 0
        thread.completed_colony_count = 0
        thread.failed_colony_count = 0
        thread.workflow_steps = []
        ws.threads = {"th-1": thread}
        runtime.projections.workspaces = {"ws-1": ws}
        runtime.settings.system.data_dir = ""

        agent = QueenAgent.__new__(QueenAgent)
        agent._runtime = runtime

        ctx = agent._build_thread_context("th-1", "ws-1")
        assert "Tags: python, auth" in ctx

    def test_no_tags_no_line(self) -> None:
        """No tags line when workspace has no taxonomy_tags."""
        from formicos.surface.queen_runtime import QueenAgent

        runtime = MagicMock()
        ws = MagicMock()
        ws.config = {}
        thread = MagicMock()
        thread.name = "test-thread"
        thread.goal = "Do something"
        thread.status = "active"
        thread.expected_outputs = []
        thread.colony_count = 0
        thread.completed_colony_count = 0
        thread.failed_colony_count = 0
        thread.workflow_steps = []
        ws.threads = {"th-1": thread}
        runtime.projections.workspaces = {"ws-1": ws}
        runtime.settings.system.data_dir = ""

        agent = QueenAgent.__new__(QueenAgent)
        agent._runtime = runtime

        ctx = agent._build_thread_context("th-1", "ws-1")
        assert "Tags:" not in ctx


class TestAutoSuggestNudge:
    def test_nudge_for_tagless_workspace(self) -> None:
        """Tagless workspace with < 3 threads gets nudge."""
        from formicos.surface.queen_runtime import QueenAgent

        runtime = MagicMock()
        ws = MagicMock()
        ws.config = {}
        thread = MagicMock()
        thread.name = "t1"
        thread.goal = "Test"
        thread.status = "active"
        thread.expected_outputs = []
        thread.colony_count = 0
        thread.completed_colony_count = 0
        thread.failed_colony_count = 0
        thread.workflow_steps = []
        ws.threads = {"th-1": thread}
        runtime.projections.workspaces = {"ws-1": ws}
        runtime.settings.system.data_dir = ""

        agent = QueenAgent.__new__(QueenAgent)
        agent._runtime = runtime

        ctx = agent._build_thread_context("th-1", "ws-1")
        assert "set_workspace_tags" in ctx

    def test_no_nudge_when_tags_exist(self) -> None:
        """No nudge when workspace has tags."""
        from formicos.surface.queen_runtime import QueenAgent

        runtime = MagicMock()
        ws = MagicMock()
        ws.config = {"taxonomy_tags": json.dumps(["python"])}
        thread = MagicMock()
        thread.name = "t1"
        thread.goal = "Test"
        thread.status = "active"
        thread.expected_outputs = []
        thread.colony_count = 0
        thread.completed_colony_count = 0
        thread.failed_colony_count = 0
        thread.workflow_steps = []
        ws.threads = {"th-1": thread}
        runtime.projections.workspaces = {"ws-1": ws}
        runtime.settings.system.data_dir = ""

        agent = QueenAgent.__new__(QueenAgent)
        agent._runtime = runtime

        ctx = agent._build_thread_context("th-1", "ws-1")
        assert "set_workspace_tags" not in ctx
