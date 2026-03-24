"""Wave 47 Team 1: patch_file surgical editing tool tests.

Covers the frozen failure contract:
- Zero matches → error with nearby context, line numbers, closest match
- Multiple matches → error listing all match locations with line numbers
- Sequential operations against in-memory buffer
- Atomic write (only if all operations succeed)
- Empty replace means deletion
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

from formicos.engine.runner import RoundRunner
from formicos.engine.runner_types import ToolExecutionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_runner(tmp_path: Path, workspace_id: str = "ws-1") -> RoundRunner:
    """Create a minimal RoundRunner wired to tmp_path as data_dir."""
    from formicos.engine.runner import RunnerCallbacks

    cb = RunnerCallbacks(
        emit=lambda e: None,
        data_dir=str(tmp_path),
    )
    return RoundRunner(cb)


def _setup_workspace_file(
    tmp_path: Path,
    workspace_id: str,
    rel_path: str,
    content: str,
) -> Path:
    """Create a file in the workspace directory structure."""
    ws_files = tmp_path / "workspaces" / workspace_id / "files"
    target = ws_files / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestPatchFileHappyPath:
    """Verify basic patch_file functionality."""

    @pytest.mark.asyncio
    async def test_single_replacement(self, tmp_path: Path) -> None:
        """Single search/replace operation succeeds."""
        _setup_workspace_file(tmp_path, "ws-1", "hello.py", "print('hello')\n")
        runner = _make_runner(tmp_path)

        result = await runner._handle_patch_file(
            {"path": "hello.py", "operations": [
                {"search": "hello", "replace": "world"},
            ]},
            "ws-1",
        )
        assert "Applied 1 operation" in result.content
        actual = (tmp_path / "workspaces/ws-1/files/hello.py").read_text()
        assert actual == "print('world')\n"

    @pytest.mark.asyncio
    async def test_multiple_sequential_operations(self, tmp_path: Path) -> None:
        """Operations apply sequentially against the updated buffer."""
        content = textwrap.dedent("""\
            import os
            import sys

            def main():
                print("hello")
        """)
        _setup_workspace_file(tmp_path, "ws-1", "app.py", content)
        runner = _make_runner(tmp_path)

        result = await runner._handle_patch_file(
            {"path": "app.py", "operations": [
                {"search": "import os\n", "replace": "import os\nimport json\n"},
                {"search": 'print("hello")', "replace": 'print("goodbye")'},
            ]},
            "ws-1",
        )
        assert "Applied 2 operations" in result.content
        actual = (tmp_path / "workspaces/ws-1/files/app.py").read_text()
        assert "import json" in actual
        assert 'print("goodbye")' in actual

    @pytest.mark.asyncio
    async def test_empty_replace_deletes(self, tmp_path: Path) -> None:
        """Empty replace string deletes the matched text."""
        _setup_workspace_file(
            tmp_path, "ws-1", "clean.py",
            "# TODO: remove this\nkeep_this()\n",
        )
        runner = _make_runner(tmp_path)

        result = await runner._handle_patch_file(
            {"path": "clean.py", "operations": [
                {"search": "# TODO: remove this\n", "replace": ""},
            ]},
            "ws-1",
        )
        assert "Applied 1 operation" in result.content
        actual = (tmp_path / "workspaces/ws-1/files/clean.py").read_text()
        assert actual == "keep_this()\n"

    @pytest.mark.asyncio
    async def test_multiline_search_replace(self, tmp_path: Path) -> None:
        """Multiline search and replace works correctly."""
        content = "def foo():\n    pass\n\ndef bar():\n    pass\n"
        _setup_workspace_file(tmp_path, "ws-1", "funcs.py", content)
        runner = _make_runner(tmp_path)

        result = await runner._handle_patch_file(
            {"path": "funcs.py", "operations": [
                {
                    "search": "def foo():\n    pass",
                    "replace": "def foo():\n    return 42",
                },
            ]},
            "ws-1",
        )
        assert "Applied 1 operation" in result.content
        actual = (tmp_path / "workspaces/ws-1/files/funcs.py").read_text()
        assert "return 42" in actual
        assert "def bar():\n    pass" in actual


# ---------------------------------------------------------------------------
# Failure contract: zero matches
# ---------------------------------------------------------------------------


class TestPatchFileZeroMatch:
    """Zero matches → error with nearby context and line numbers."""

    @pytest.mark.asyncio
    async def test_zero_match_error_message(self, tmp_path: Path) -> None:
        """Zero matches produces a helpful error."""
        _setup_workspace_file(
            tmp_path, "ws-1", "example.py",
            "def calculate(x):\n    return x * 2\n",
        )
        runner = _make_runner(tmp_path)

        result = await runner._handle_patch_file(
            {"path": "example.py", "operations": [
                {"search": "def compute(x):", "replace": "def compute(y):"},
            ]},
            "ws-1",
        )
        assert "no match found" in result.content
        assert "operation 1" in result.content
        assert "example.py" in result.content

    @pytest.mark.asyncio
    async def test_zero_match_shows_nearby_context(self, tmp_path: Path) -> None:
        """Zero-match error includes closest nearby line."""
        content = textwrap.dedent("""\
            class MyClass:
                def process_data(self, items):
                    for item in items:
                        self.handle(item)
        """)
        _setup_workspace_file(tmp_path, "ws-1", "cls.py", content)
        runner = _make_runner(tmp_path)

        result = await runner._handle_patch_file(
            {"path": "cls.py", "operations": [
                {"search": "def process_items(self, items):", "replace": "changed"},
            ]},
            "ws-1",
        )
        assert "no match found" in result.content
        # Should show nearby context with line numbers
        assert "Closest match" in result.content

    @pytest.mark.asyncio
    async def test_zero_match_no_file_modification(self, tmp_path: Path) -> None:
        """File is NOT modified when a match fails."""
        original = "unchanged content\n"
        _setup_workspace_file(tmp_path, "ws-1", "safe.txt", original)
        runner = _make_runner(tmp_path)

        await runner._handle_patch_file(
            {"path": "safe.txt", "operations": [
                {"search": "missing text", "replace": "new text"},
            ]},
            "ws-1",
        )
        actual = (tmp_path / "workspaces/ws-1/files/safe.txt").read_text()
        assert actual == original


# ---------------------------------------------------------------------------
# Failure contract: multiple matches
# ---------------------------------------------------------------------------


class TestPatchFileMultiMatch:
    """Multiple matches → error listing all match locations."""

    @pytest.mark.asyncio
    async def test_multi_match_error(self, tmp_path: Path) -> None:
        """Multiple matches produces an ambiguity error."""
        content = "x = 1\nx = 2\nx = 3\n"
        _setup_workspace_file(tmp_path, "ws-1", "dups.py", content)
        runner = _make_runner(tmp_path)

        result = await runner._handle_patch_file(
            {"path": "dups.py", "operations": [
                {"search": "x = ", "replace": "y = "},
            ]},
            "ws-1",
        )
        assert "3 matches found" in result.content
        assert "Expected exactly 1" in result.content
        assert "operation 1" in result.content

    @pytest.mark.asyncio
    async def test_multi_match_shows_locations(self, tmp_path: Path) -> None:
        """Multi-match error shows line numbers."""
        content = "foo()\nbar()\nfoo()\n"
        _setup_workspace_file(tmp_path, "ws-1", "locs.py", content)
        runner = _make_runner(tmp_path)

        result = await runner._handle_patch_file(
            {"path": "locs.py", "operations": [
                {"search": "foo()", "replace": "baz()"},
            ]},
            "ws-1",
        )
        assert "line 1" in result.content
        assert "line 3" in result.content

    @pytest.mark.asyncio
    async def test_multi_match_no_file_modification(self, tmp_path: Path) -> None:
        """File is NOT modified on ambiguity error."""
        original = "a = 1\na = 2\n"
        _setup_workspace_file(tmp_path, "ws-1", "ambig.py", original)
        runner = _make_runner(tmp_path)

        await runner._handle_patch_file(
            {"path": "ambig.py", "operations": [
                {"search": "a = ", "replace": "b = "},
            ]},
            "ws-1",
        )
        actual = (tmp_path / "workspaces/ws-1/files/ambig.py").read_text()
        assert actual == original


# ---------------------------------------------------------------------------
# Atomicity: partial failure
# ---------------------------------------------------------------------------


class TestPatchFileAtomicity:
    """Partial failure leaves the file unchanged."""

    @pytest.mark.asyncio
    async def test_second_op_fails_no_write(self, tmp_path: Path) -> None:
        """If operation 2 fails, operation 1's change is NOT written."""
        content = "line_a = 1\nline_b = 2\n"
        _setup_workspace_file(tmp_path, "ws-1", "atomic.py", content)
        runner = _make_runner(tmp_path)

        result = await runner._handle_patch_file(
            {"path": "atomic.py", "operations": [
                {"search": "line_a = 1", "replace": "line_a = 99"},
                {"search": "NONEXISTENT", "replace": "whatever"},
            ]},
            "ws-1",
        )
        assert "no match found" in result.content
        assert "operation 2" in result.content
        # File must be unchanged
        actual = (tmp_path / "workspaces/ws-1/files/atomic.py").read_text()
        assert actual == content

    @pytest.mark.asyncio
    async def test_third_op_multi_match_no_write(self, tmp_path: Path) -> None:
        """Multi-match on op 3 after two successful ops → no write."""
        content = "a\nb\nc\nc\n"
        _setup_workspace_file(tmp_path, "ws-1", "multi.py", content)
        runner = _make_runner(tmp_path)

        result = await runner._handle_patch_file(
            {"path": "multi.py", "operations": [
                {"search": "a\n", "replace": "A\n"},
                {"search": "b\n", "replace": "B\n"},
                {"search": "c\n", "replace": "C\n"},  # 2 matches after prior ops
            ]},
            "ws-1",
        )
        assert "2 matches found" in result.content
        actual = (tmp_path / "workspaces/ws-1/files/multi.py").read_text()
        assert actual == content


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestPatchFileEdgeCases:
    """Edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_missing_file(self, tmp_path: Path) -> None:
        """Patching a nonexistent file returns clear error."""
        runner = _make_runner(tmp_path)
        result = await runner._handle_patch_file(
            {"path": "nope.py", "operations": [
                {"search": "x", "replace": "y"},
            ]},
            "ws-1",
        )
        assert "File not found" in result.content

    @pytest.mark.asyncio
    async def test_empty_operations_list(self, tmp_path: Path) -> None:
        """Empty operations list returns error."""
        _setup_workspace_file(tmp_path, "ws-1", "empty.py", "content\n")
        runner = _make_runner(tmp_path)
        result = await runner._handle_patch_file(
            {"path": "empty.py", "operations": []},
            "ws-1",
        )
        assert "at least one operation" in result.content

    @pytest.mark.asyncio
    async def test_empty_search_string(self, tmp_path: Path) -> None:
        """Empty search string in an operation returns error."""
        _setup_workspace_file(tmp_path, "ws-1", "e.py", "content\n")
        runner = _make_runner(tmp_path)
        result = await runner._handle_patch_file(
            {"path": "e.py", "operations": [
                {"search": "", "replace": "x"},
            ]},
            "ws-1",
        )
        assert "empty 'search'" in result.content

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, tmp_path: Path) -> None:
        """Path traversal attempt is blocked."""
        _setup_workspace_file(tmp_path, "ws-1", "ok.py", "x\n")
        runner = _make_runner(tmp_path)
        result = await runner._handle_patch_file(
            {"path": "../../etc/passwd", "operations": [
                {"search": "x", "replace": "y"},
            ]},
            "ws-1",
        )
        assert "path traversal" in result.content.lower() or "not found" in result.content.lower()

    @pytest.mark.asyncio
    async def test_no_data_dir(self) -> None:
        """Missing data_dir returns error."""
        from formicos.engine.runner import RunnerCallbacks

        cb = RunnerCallbacks(emit=lambda e: None, data_dir="")
        runner = RoundRunner(cb)
        result = await runner._handle_patch_file(
            {"path": "x.py", "operations": [{"search": "a", "replace": "b"}]},
            "ws-1",
        )
        assert "no workspace directory" in result.content.lower()

    @pytest.mark.asyncio
    async def test_missing_path_arg(self, tmp_path: Path) -> None:
        """Missing path argument returns error."""
        runner = _make_runner(tmp_path)
        result = await runner._handle_patch_file(
            {"operations": [{"search": "a", "replace": "b"}]},
            "ws-1",
        )
        assert "path is required" in result.content
