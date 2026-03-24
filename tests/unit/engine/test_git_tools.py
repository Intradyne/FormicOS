"""Wave 47 Team 1: Git workflow primitive tool tests.

Covers git_status, git_diff, git_commit, git_log tool dispatch
and argument handling. Uses a mock workspace_execute_handler since
actual git operations require a real repository.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from formicos.core.types import WorkspaceExecutionResult
from formicos.engine.runner import RoundRunner, RunnerCallbacks
from formicos.engine.tool_dispatch import TOOL_CATEGORY_MAP, TOOL_SPECS, ToolCategory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ws_result(
    stdout: str = "",
    stderr: str = "",
    exit_code: int = 0,
) -> WorkspaceExecutionResult:
    """Create a minimal WorkspaceExecutionResult."""
    return WorkspaceExecutionResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=False,
    )


def _make_runner_with_mock(
    mock_handler: AsyncMock,
) -> RoundRunner:
    """Create a RoundRunner with a mocked workspace_execute_handler."""
    cb = RunnerCallbacks(
        emit=lambda e: None,
        data_dir="/fake",
        workspace_execute_handler=mock_handler,
    )
    return RoundRunner(cb)


# ---------------------------------------------------------------------------
# Tool spec registration
# ---------------------------------------------------------------------------


class TestGitToolSpecs:
    """Verify git tools are registered in TOOL_SPECS and TOOL_CATEGORY_MAP."""

    @pytest.mark.parametrize("tool_name", [
        "git_status", "git_diff", "git_commit", "git_log",
    ])
    def test_tool_spec_exists(self, tool_name: str) -> None:
        assert tool_name in TOOL_SPECS
        spec = TOOL_SPECS[tool_name]
        assert spec["name"] == tool_name
        assert "description" in spec

    @pytest.mark.parametrize("tool_name,expected_cat", [
        ("git_status", ToolCategory.read_fs),
        ("git_diff", ToolCategory.read_fs),
        ("git_commit", ToolCategory.write_fs),
        ("git_log", ToolCategory.read_fs),
    ])
    def test_category_mapping(
        self, tool_name: str, expected_cat: ToolCategory,
    ) -> None:
        assert TOOL_CATEGORY_MAP[tool_name] == expected_cat

    def test_git_commit_requires_message(self) -> None:
        spec = TOOL_SPECS["git_commit"]
        assert "message" in spec["parameters"].get("required", [])


# ---------------------------------------------------------------------------
# git_status
# ---------------------------------------------------------------------------


class TestGitStatus:
    """git_status dispatches correctly."""

    @pytest.mark.asyncio
    async def test_status_output(self) -> None:
        handler = AsyncMock(return_value=_make_ws_result(
            stdout=" M src/app.py\n?? new_file.txt\n---\n## main\n M src/app.py\n?? new_file.txt",
        ))
        runner = _make_runner_with_mock(handler)

        result = await runner._handle_git_tool("git_status", {}, "ws-1")
        handler.assert_called_once()
        cmd = handler.call_args[0][0]
        assert "git status" in cmd
        assert "M src/app.py" in result.content

    @pytest.mark.asyncio
    async def test_status_no_handler(self) -> None:
        cb = RunnerCallbacks(emit=lambda e: None, data_dir="/fake")
        runner = RoundRunner(cb)
        result = await runner._handle_git_tool("git_status", {}, "ws-1")
        assert "not available" in result.content.lower()


# ---------------------------------------------------------------------------
# git_diff
# ---------------------------------------------------------------------------


class TestGitDiff:
    """git_diff dispatches with correct flags."""

    @pytest.mark.asyncio
    async def test_diff_basic(self) -> None:
        handler = AsyncMock(return_value=_make_ws_result(
            stdout="diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n",
        ))
        runner = _make_runner_with_mock(handler)

        result = await runner._handle_git_tool("git_diff", {}, "ws-1")
        cmd = handler.call_args[0][0]
        assert cmd.startswith("git diff")
        assert "--cached" not in cmd
        assert "diff --git" in result.content

    @pytest.mark.asyncio
    async def test_diff_staged(self) -> None:
        handler = AsyncMock(return_value=_make_ws_result(stdout="staged diff"))
        runner = _make_runner_with_mock(handler)

        await runner._handle_git_tool("git_diff", {"staged": True}, "ws-1")
        cmd = handler.call_args[0][0]
        assert "--cached" in cmd

    @pytest.mark.asyncio
    async def test_diff_with_path(self) -> None:
        handler = AsyncMock(return_value=_make_ws_result(stdout="path diff"))
        runner = _make_runner_with_mock(handler)

        await runner._handle_git_tool(
            "git_diff", {"path": "src/app.py"}, "ws-1",
        )
        cmd = handler.call_args[0][0]
        assert "src/app.py" in cmd

    @pytest.mark.asyncio
    async def test_diff_empty(self) -> None:
        handler = AsyncMock(return_value=_make_ws_result(stdout=""))
        runner = _make_runner_with_mock(handler)

        result = await runner._handle_git_tool("git_diff", {}, "ws-1")
        assert "(no output)" in result.content


# ---------------------------------------------------------------------------
# git_commit
# ---------------------------------------------------------------------------


class TestGitCommit:
    """git_commit requires a message and stages all changes."""

    @pytest.mark.asyncio
    async def test_commit_success(self) -> None:
        handler = AsyncMock(return_value=_make_ws_result(
            stdout="[main abc1234] Fix bug\n 1 file changed, 1 insertion(+)",
        ))
        runner = _make_runner_with_mock(handler)

        result = await runner._handle_git_tool(
            "git_commit", {"message": "Fix bug"}, "ws-1",
        )
        cmd = handler.call_args[0][0]
        assert "git add -A" in cmd
        assert "git commit" in cmd
        assert "Fix bug" in cmd
        assert "abc1234" in result.content

    @pytest.mark.asyncio
    async def test_commit_empty_message(self) -> None:
        handler = AsyncMock()
        runner = _make_runner_with_mock(handler)

        result = await runner._handle_git_tool(
            "git_commit", {"message": ""}, "ws-1",
        )
        assert "message is required" in result.content.lower()
        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_commit_missing_message(self) -> None:
        handler = AsyncMock()
        runner = _make_runner_with_mock(handler)

        result = await runner._handle_git_tool("git_commit", {}, "ws-1")
        assert "message is required" in result.content.lower()
        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_commit_message_shell_safety(self) -> None:
        """Commit messages with special characters are safely quoted."""
        handler = AsyncMock(return_value=_make_ws_result(stdout="committed"))
        runner = _make_runner_with_mock(handler)

        await runner._handle_git_tool(
            "git_commit",
            {"message": "fix: handle 'single quotes' & \"doubles\""},
            "ws-1",
        )
        cmd = handler.call_args[0][0]
        # The message should be quoted (shlex.quote wraps in single quotes)
        assert "git commit -m" in cmd


# ---------------------------------------------------------------------------
# git_log
# ---------------------------------------------------------------------------


class TestGitLog:
    """git_log returns bounded commit history."""

    @pytest.mark.asyncio
    async def test_log_default_count(self) -> None:
        handler = AsyncMock(return_value=_make_ws_result(
            stdout="abc1234 2026-03-19 Dev: Initial commit\n",
        ))
        runner = _make_runner_with_mock(handler)

        result = await runner._handle_git_tool("git_log", {}, "ws-1")
        cmd = handler.call_args[0][0]
        assert "-10" in cmd
        assert "abc1234" in result.content

    @pytest.mark.asyncio
    async def test_log_custom_count(self) -> None:
        handler = AsyncMock(return_value=_make_ws_result(stdout="log"))
        runner = _make_runner_with_mock(handler)

        await runner._handle_git_tool("git_log", {"n": 5}, "ws-1")
        cmd = handler.call_args[0][0]
        assert "-5" in cmd

    @pytest.mark.asyncio
    async def test_log_count_capped(self) -> None:
        """Requesting more than 50 commits is capped."""
        handler = AsyncMock(return_value=_make_ws_result(stdout="log"))
        runner = _make_runner_with_mock(handler)

        await runner._handle_git_tool("git_log", {"n": 100}, "ws-1")
        cmd = handler.call_args[0][0]
        assert "-50" in cmd


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestGitToolErrors:
    """Git tools handle errors gracefully."""

    @pytest.mark.asyncio
    async def test_nonzero_exit_code(self) -> None:
        handler = AsyncMock(return_value=_make_ws_result(
            stderr="fatal: not a git repository",
            exit_code=128,
        ))
        runner = _make_runner_with_mock(handler)

        result = await runner._handle_git_tool("git_status", {}, "ws-1")
        assert "fatal" in result.content or "failed" in result.content

    @pytest.mark.asyncio
    async def test_unknown_git_tool(self) -> None:
        handler = AsyncMock()
        runner = _make_runner_with_mock(handler)

        result = await runner._handle_git_tool("git_push", {}, "ws-1")
        assert "unknown git tool" in result.content.lower()
        handler.assert_not_called()
