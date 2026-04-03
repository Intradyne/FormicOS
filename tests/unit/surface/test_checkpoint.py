"""Tests for shadow git checkpoint manager (Wave 78 Track 1)."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from formicos.surface.checkpoint import (
    CheckpointManager,
    _shadow_dir,
)
from formicos.surface.queen_tools import (
    _is_destructive_command,
    _summarize_inputs,
)


class TestShadowDir:
    def test_deterministic_hash(self, tmp_path: Path) -> None:
        d1 = _shadow_dir(str(tmp_path), "/some/workspace")
        d2 = _shadow_dir(str(tmp_path), "/some/workspace")
        assert d1 == d2

    def test_different_dirs_different_hashes(self, tmp_path: Path) -> None:
        d1 = _shadow_dir(str(tmp_path), "/workspace/a")
        d2 = _shadow_dir(str(tmp_path), "/workspace/b")
        assert d1 != d2

    def test_path_under_data_dir(self, tmp_path: Path) -> None:
        result = _shadow_dir(str(tmp_path), "/some/dir")
        assert str(result).startswith(str(tmp_path))
        assert ".formicos" in str(result)
        assert "checkpoints" in str(result)


class TestCheckpointManager:
    @pytest.fixture()
    def mgr(self, tmp_path: Path) -> CheckpointManager:
        return CheckpointManager(str(tmp_path))

    @pytest.fixture()
    def workspace(self, tmp_path: Path) -> Path:
        ws = tmp_path / "test_workspace"
        ws.mkdir()
        (ws / "file.txt").write_text("hello world")
        return ws

    def _git_available(self) -> bool:
        try:
            subprocess.run(  # noqa: S603
                ["git", "--version"],
                capture_output=True, timeout=5, check=False,
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @pytest.mark.asyncio()
    async def test_create_checkpoint_no_git(
        self, mgr: CheckpointManager, workspace: Path,
    ) -> None:
        """When git is not available, create_checkpoint returns None."""
        with patch(
            "formicos.surface.checkpoint._git",
            side_effect=FileNotFoundError("git"),
        ):
            result = await mgr.create_checkpoint(str(workspace), "test")
            assert result is None

    @pytest.mark.asyncio()
    async def test_create_checkpoint_nonexistent_dir(
        self, mgr: CheckpointManager,
    ) -> None:
        result = await mgr.create_checkpoint("/nonexistent/path", "test")
        assert result is None

    def test_list_checkpoints_no_repo(
        self, mgr: CheckpointManager,
    ) -> None:
        result = mgr.list_checkpoints("/nonexistent/path")
        assert result == []

    @pytest.mark.asyncio()
    async def test_rollback_no_repo(
        self, mgr: CheckpointManager,
    ) -> None:
        result = await mgr.rollback_to("/nonexistent/path")
        assert "No checkpoints" in result

    def test_auto_prune_no_repo(
        self, mgr: CheckpointManager,
    ) -> None:
        result = mgr.auto_prune("/nonexistent/path")
        assert result == 0

    @pytest.mark.asyncio()
    async def test_full_lifecycle(
        self, mgr: CheckpointManager, workspace: Path,
    ) -> None:
        """End-to-end: create, list, modify, create, rollback."""
        try:
            subprocess.run(  # noqa: S603
                ["git", "--version"],
                capture_output=True, timeout=5, check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pytest.skip("git not available")

        # Create first checkpoint
        h1 = await mgr.create_checkpoint(str(workspace), "initial state")
        assert h1 is not None
        assert len(h1) == 40  # full SHA

        # Verify checkpoint appears in list
        cps = mgr.list_checkpoints(str(workspace))
        assert len(cps) == 1
        assert cps[0].hash == h1

        # Modify workspace
        (workspace / "file.txt").write_text("modified content")
        (workspace / "new_file.md").write_text("new stuff")

        # Create second checkpoint
        h2 = await mgr.create_checkpoint(str(workspace), "after modification")
        assert h2 is not None
        assert h2 != h1

        # List should show 2 checkpoints
        cps = mgr.list_checkpoints(str(workspace))
        assert len(cps) == 2

        # Rollback to first checkpoint
        result = await mgr.rollback_to(str(workspace), h1)
        assert "Rolled back" in result

        # Verify content restored
        assert (workspace / "file.txt").read_text() == "hello world"


class TestDestructiveDetection:
    def test_rm_rf_detected(self) -> None:
        assert _is_destructive_command("rm -rf /tmp/foo")

    def test_rm_r_detected(self) -> None:
        assert _is_destructive_command("rm -r /tmp/foo")

    def test_git_reset_hard_detected(self) -> None:
        assert _is_destructive_command("git reset --hard")

    def test_git_clean_f_detected(self) -> None:
        assert _is_destructive_command("git clean -fd")

    def test_drop_table_detected(self) -> None:
        assert _is_destructive_command("DROP TABLE users")

    def test_safe_command_not_flagged(self) -> None:
        assert not _is_destructive_command("ls -la")

    def test_git_status_not_flagged(self) -> None:
        assert not _is_destructive_command("git status")

    def test_cat_not_flagged(self) -> None:
        assert not _is_destructive_command("cat file.txt")


class TestSummarizeInputs:
    def test_path_input(self) -> None:
        result = _summarize_inputs({"path": "/foo/bar.py"})
        assert "path=/foo/bar.py" in result

    def test_filename_input(self) -> None:
        result = _summarize_inputs({"filename": "readme.md"})
        assert "filename=readme.md" in result

    def test_command_input(self) -> None:
        result = _summarize_inputs({"command": "ls -la"})
        assert "command=ls -la" in result

    def test_empty_inputs(self) -> None:
        result = _summarize_inputs({})
        assert result == "no details"
