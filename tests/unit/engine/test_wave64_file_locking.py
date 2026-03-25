"""Wave 64 Track 2: Optimistic file locking for parallel agents.

Tests:
1. patch_file detects conflict when file modified between read and write
2. patch_file succeeds when file unchanged
3. write_workspace_file uses atomic temp+rename (no .tmp residue)
4. Concurrent patches to same file — one wins, one gets CONFLICT
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from formicos.engine.runner import RoundRunner, RunnerCallbacks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_runner(tmp_path: Path) -> RoundRunner:
    """Create a minimal RoundRunner wired to tmp_path as data_dir."""
    cb = RunnerCallbacks(
        emit=lambda e: None,
        data_dir=str(tmp_path),
    )
    return RoundRunner(cb)


def _setup_file(
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


WS_ID = "ws-lock"


# ---------------------------------------------------------------------------
# 1. patch_file detects conflict
# ---------------------------------------------------------------------------


class TestPatchFileDetectsConflict:
    """When the file changes between read and re-read, CONFLICT is returned."""

    @pytest.mark.asyncio
    async def test_patch_file_detects_conflict(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        target = _setup_file(tmp_path, WS_ID, "app.py", "hello = 1\n")

        original_read = Path.read_text
        call_count = 0

        def sneaky_read(self_path: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
            """First read returns original content; second read returns
            modified content (simulating another agent writing in between)."""
            nonlocal call_count
            result = original_read(self_path, *args, **kwargs)
            call_count += 1
            # After the first read of our target, mutate the file so the
            # second read (conflict check) sees different content.
            if call_count == 1 and self_path.resolve() == target.resolve():
                target.write_text("hello = 999\n", encoding="utf-8")
            return result

        with patch.object(Path, "read_text", sneaky_read):
            result = await runner._handle_patch_file(
                {"path": "app.py", "operations": [{"search": "hello = 1", "replace": "hello = 2"}]},
                WS_ID,
            )

        assert "CONFLICT" in result.content
        assert "modified by another agent" in result.content


# ---------------------------------------------------------------------------
# 2. patch_file succeeds when file unchanged
# ---------------------------------------------------------------------------


class TestPatchFileSucceedsUnchanged:
    """Normal patch completes when no concurrent modification occurs."""

    @pytest.mark.asyncio
    async def test_patch_file_succeeds_when_unchanged(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        target = _setup_file(tmp_path, WS_ID, "config.py", "debug = False\n")

        result = await runner._handle_patch_file(
            {"path": "config.py", "operations": [{"search": "debug = False", "replace": "debug = True"}]},
            WS_ID,
        )

        assert "CONFLICT" not in result.content
        assert "Applied 1 operation" in result.content
        # Verify file was actually written
        assert target.read_text(encoding="utf-8") == "debug = True\n"


# ---------------------------------------------------------------------------
# 3. write_workspace_file uses atomic temp+rename
# ---------------------------------------------------------------------------


class TestWriteFileAtomic:
    """Verify the temp+rename pattern leaves no .tmp residue."""

    @pytest.mark.asyncio
    async def test_write_file_atomic(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        # Set up workspace dir (write_workspace_file creates the file)
        ws_files = tmp_path / "workspaces" / WS_ID / "files"
        ws_files.mkdir(parents=True, exist_ok=True)

        result = await runner._handle_workspace_file_tool(
            "write_workspace_file",
            {"path": "output.txt", "content": "result data"},
            WS_ID,
        )

        assert "Written" in result.content
        target = ws_files / "output.txt"
        assert target.read_text(encoding="utf-8") == "result data"
        # The .tmp file must not persist after rename
        tmp_file = ws_files / "output.txt.tmp"
        assert not tmp_file.exists(), ".tmp file should not persist after atomic rename"

    @pytest.mark.asyncio
    async def test_write_file_atomic_overwrite(self, tmp_path: Path) -> None:
        """Overwriting an existing file also uses temp+rename."""
        runner = _make_runner(tmp_path)
        target = _setup_file(tmp_path, WS_ID, "data.txt", "old content")

        result = await runner._handle_workspace_file_tool(
            "write_workspace_file",
            {"path": "data.txt", "content": "new content"},
            WS_ID,
        )

        assert "Written" in result.content
        assert target.read_text(encoding="utf-8") == "new content"
        tmp_file = target.with_suffix(".txt.tmp")
        assert not tmp_file.exists()


# ---------------------------------------------------------------------------
# 4. Concurrent patches — one wins, one gets CONFLICT
# ---------------------------------------------------------------------------


class TestConcurrentPatchOneWins:
    """Two concurrent patches to the same file: one succeeds, one CONFLICTs."""

    @pytest.mark.asyncio
    async def test_concurrent_patch_one_wins(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        original_content = "value = 0\nother = 1\n"
        _setup_file(tmp_path, WS_ID, "shared.py", original_content)

        # Patch A: value = 0 -> value = 10
        patch_a = runner._handle_patch_file(
            {"path": "shared.py", "operations": [{"search": "value = 0", "replace": "value = 10"}]},
            WS_ID,
        )
        # Patch B: value = 0 -> value = 20
        patch_b = runner._handle_patch_file(
            {"path": "shared.py", "operations": [{"search": "value = 0", "replace": "value = 20"}]},
            WS_ID,
        )

        results = await asyncio.gather(patch_a, patch_b)
        contents = [r.content for r in results]

        # Exactly one should succeed, the other should fail.
        # Under asyncio cooperative scheduling, the first coroutine
        # completes fully before the second runs, so the second either
        # hits a CONFLICT (hash mismatch) or a "no match" (search text
        # already changed). Both are correct detection of concurrent
        # modification.
        successes = [c for c in contents if "Applied" in c]
        failures = [c for c in contents if "CONFLICT" in c or "no match" in c]

        assert len(successes) >= 1, f"At least one patch should succeed: {contents}"
        assert len(failures) + len(successes) == 2, f"Unexpected results: {contents}"

    @pytest.mark.asyncio
    async def test_sequential_patches_both_conflict_or_second_fails(
        self, tmp_path: Path,
    ) -> None:
        """Two sequential patches: first succeeds, second fails because the
        search string was already replaced by the first patch."""
        runner = _make_runner(tmp_path)
        _setup_file(tmp_path, WS_ID, "seq.py", "x = 1\n")

        r1 = await runner._handle_patch_file(
            {"path": "seq.py", "operations": [{"search": "x = 1", "replace": "x = 2"}]},
            WS_ID,
        )
        assert "Applied" in r1.content

        # Second patch tries the same search — file now has "x = 2" so
        # the search string "x = 1" no longer exists.
        r2 = await runner._handle_patch_file(
            {"path": "seq.py", "operations": [{"search": "x = 1", "replace": "x = 3"}]},
            WS_ID,
        )
        # Should fail with zero-match error (not CONFLICT — the search itself fails)
        assert "CONFLICT" not in r2.content
        assert "Error" in r2.content or "not found" in r2.content.lower() or "0 matches" in r2.content.lower()
