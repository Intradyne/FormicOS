"""Wave 41 Team 2: Multi-file coordination tests.

Tests the multi-file task coordination capability (B2):
- ColonyContext.target_files field propagation
- ColonyConfig.target_files field
- File-aware context in colony execution
- Workspace file tools (list, read, write) via runner._handle_workspace_file_tool
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from formicos.core.types import ColonyConfig, ColonyContext


# ---------------------------------------------------------------------------
# ColonyContext target_files tests
# ---------------------------------------------------------------------------


class TestColonyContextTargetFiles:
    """Test that ColonyContext carries target_files for multi-file coordination."""

    def test_default_empty(self) -> None:
        ctx = ColonyContext(
            colony_id="col-1",
            workspace_id="ws-1",
            thread_id="th-1",
            goal="Test task",
            round_number=1,
            merge_edges=[],
        )
        assert ctx.target_files == []

    def test_with_target_files(self) -> None:
        files = ["src/main.py", "src/utils.py", "tests/test_main.py"]
        ctx = ColonyContext(
            colony_id="col-1",
            workspace_id="ws-1",
            thread_id="th-1",
            goal="Refactor main module",
            round_number=1,
            merge_edges=[],
            target_files=files,
        )
        assert ctx.target_files == files
        assert len(ctx.target_files) == 3

    def test_target_files_is_frozen(self) -> None:
        """ColonyContext is frozen — target_files cannot be mutated after creation."""
        ctx = ColonyContext(
            colony_id="col-1",
            workspace_id="ws-1",
            thread_id="th-1",
            goal="Task",
            round_number=1,
            merge_edges=[],
            target_files=["a.py"],
        )
        with pytest.raises(Exception):  # ValidationError for frozen model
            ctx.target_files = ["b.py"]  # type: ignore[misc]

    def test_workspace_dir_field(self) -> None:
        ctx = ColonyContext(
            colony_id="col-1",
            workspace_id="ws-1",
            thread_id="th-1",
            goal="Task",
            round_number=1,
            merge_edges=[],
            workspace_dir="/data/formicos",
        )
        assert ctx.workspace_dir == "/data/formicos"

    def test_workspace_dir_default_empty(self) -> None:
        ctx = ColonyContext(
            colony_id="col-1",
            workspace_id="ws-1",
            thread_id="th-1",
            goal="Task",
            round_number=1,
            merge_edges=[],
        )
        assert ctx.workspace_dir == ""


# ---------------------------------------------------------------------------
# ColonyConfig target_files tests
# ---------------------------------------------------------------------------


class TestColonyConfigTargetFiles:
    """Test that ColonyConfig carries target_files for spawning file-aware colonies."""

    def test_default_empty(self) -> None:
        config = ColonyConfig(
            task="Write tests",
            castes=[],
            max_rounds=5,
            budget_limit=1.0,
            strategy="stigmergic",
        )
        assert config.target_files == []

    def test_with_target_files(self) -> None:
        config = ColonyConfig(
            task="Refactor module",
            castes=[],
            max_rounds=10,
            budget_limit=2.0,
            strategy="stigmergic",
            target_files=["src/foo.py", "src/bar.py"],
        )
        assert config.target_files == ["src/foo.py", "src/bar.py"]


# ---------------------------------------------------------------------------
# Workspace file tool handler tests (via RoundRunner._handle_workspace_file_tool)
# ---------------------------------------------------------------------------


class TestWorkspaceFileTools:
    """Test workspace file tools for multi-file coordination.

    These tests exercise the tool handler methods directly since they are
    deterministic and don't require full colony execution.
    """

    def _make_runner(self, data_dir: str) -> Any:
        """Create a minimal RoundRunner with workspace tools enabled."""
        from formicos.engine.runner import RoundRunner, RunnerCallbacks

        def noop_emit(event: Any) -> None:
            pass

        return RoundRunner(RunnerCallbacks(
            emit=noop_emit,
            data_dir=data_dir,
        ))

    @pytest.mark.asyncio
    async def test_list_workspace_files(self, tmp_path: Path) -> None:
        ws_dir = tmp_path / "workspaces" / "ws-test" / "files"
        ws_dir.mkdir(parents=True)
        (ws_dir / "main.py").write_text("# main")
        (ws_dir / "utils.py").write_text("# utils")
        sub = ws_dir / "tests"
        sub.mkdir()
        (sub / "test_main.py").write_text("# test")

        runner = self._make_runner(str(tmp_path))
        result = await runner._handle_workspace_file_tool(
            "list_workspace_files",
            {"pattern": "**/*.py"},
            "ws-test",
        )
        assert "main.py" in result.content
        assert "utils.py" in result.content
        assert "test_main.py" in result.content

    @pytest.mark.asyncio
    async def test_list_workspace_files_pattern_filter(self, tmp_path: Path) -> None:
        ws_dir = tmp_path / "workspaces" / "ws-test" / "files"
        ws_dir.mkdir(parents=True)
        (ws_dir / "main.py").write_text("# main")
        (ws_dir / "readme.md").write_text("# readme")

        runner = self._make_runner(str(tmp_path))
        result = await runner._handle_workspace_file_tool(
            "list_workspace_files",
            {"pattern": "*.md"},
            "ws-test",
        )
        assert "readme.md" in result.content
        assert "main.py" not in result.content

    @pytest.mark.asyncio
    async def test_read_workspace_file(self, tmp_path: Path) -> None:
        ws_dir = tmp_path / "workspaces" / "ws-test" / "files"
        ws_dir.mkdir(parents=True)
        (ws_dir / "main.py").write_text("line1\nline2\nline3\n")

        runner = self._make_runner(str(tmp_path))
        result = await runner._handle_workspace_file_tool(
            "read_workspace_file",
            {"path": "main.py"},
            "ws-test",
        )
        assert "line1" in result.content
        assert "line2" in result.content
        assert "line3" in result.content

    @pytest.mark.asyncio
    async def test_read_workspace_file_with_offset(self, tmp_path: Path) -> None:
        ws_dir = tmp_path / "workspaces" / "ws-test" / "files"
        ws_dir.mkdir(parents=True)
        content = "\n".join(f"line{i}" for i in range(20))
        (ws_dir / "big.py").write_text(content)

        runner = self._make_runner(str(tmp_path))
        result = await runner._handle_workspace_file_tool(
            "read_workspace_file",
            {"path": "big.py", "offset": 5, "limit": 3},
            "ws-test",
        )
        assert "line5" in result.content
        assert "line7" in result.content
        assert "line8" not in result.content

    @pytest.mark.asyncio
    async def test_read_workspace_file_not_found(self, tmp_path: Path) -> None:
        ws_dir = tmp_path / "workspaces" / "ws-test" / "files"
        ws_dir.mkdir(parents=True)

        runner = self._make_runner(str(tmp_path))
        result = await runner._handle_workspace_file_tool(
            "read_workspace_file",
            {"path": "nonexistent.py"},
            "ws-test",
        )
        assert "not found" in result.content.lower()

    @pytest.mark.asyncio
    async def test_read_workspace_file_path_traversal_blocked(
        self, tmp_path: Path,
    ) -> None:
        ws_dir = tmp_path / "workspaces" / "ws-test" / "files"
        ws_dir.mkdir(parents=True)

        runner = self._make_runner(str(tmp_path))
        result = await runner._handle_workspace_file_tool(
            "read_workspace_file",
            {"path": "../../etc/passwd"},
            "ws-test",
        )
        assert "traversal" in result.content.lower()

    @pytest.mark.asyncio
    async def test_write_workspace_file(self, tmp_path: Path) -> None:
        ws_dir = tmp_path / "workspaces" / "ws-test" / "files"
        ws_dir.mkdir(parents=True)

        runner = self._make_runner(str(tmp_path))
        result = await runner._handle_workspace_file_tool(
            "write_workspace_file",
            {"path": "new_file.py", "content": "print('hello')"},
            "ws-test",
        )
        assert "Written" in result.content
        assert (ws_dir / "new_file.py").read_text() == "print('hello')"

    @pytest.mark.asyncio
    async def test_write_workspace_file_creates_dirs(self, tmp_path: Path) -> None:
        ws_dir = tmp_path / "workspaces" / "ws-test" / "files"
        ws_dir.mkdir(parents=True)

        runner = self._make_runner(str(tmp_path))
        result = await runner._handle_workspace_file_tool(
            "write_workspace_file",
            {"path": "sub/dir/file.py", "content": "# nested"},
            "ws-test",
        )
        assert "Written" in result.content
        assert (ws_dir / "sub" / "dir" / "file.py").read_text() == "# nested"

    @pytest.mark.asyncio
    async def test_write_workspace_file_path_traversal_blocked(
        self, tmp_path: Path,
    ) -> None:
        ws_dir = tmp_path / "workspaces" / "ws-test" / "files"
        ws_dir.mkdir(parents=True)

        runner = self._make_runner(str(tmp_path))
        result = await runner._handle_workspace_file_tool(
            "write_workspace_file",
            {"path": "../../evil.py", "content": "bad"},
            "ws-test",
        )
        assert "traversal" in result.content.lower()

    @pytest.mark.asyncio
    async def test_no_data_dir_errors(self) -> None:
        runner = self._make_runner("")
        result = await runner._handle_workspace_file_tool(
            "list_workspace_files",
            {},
            "ws-test",
        )
        assert "error" in result.content.lower()
