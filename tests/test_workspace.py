"""
Tests for SharedWorkspaceManager & StigmergyWatcher (stigmergy.py) -- FormicOS v0.6.0

Covers:
  1.  init_workspace creates directory
  2.  init_workspace with git creates .git
  3.  init_workspace git failure falls back gracefully
  4.  round_commit creates git commit
  5.  round_commit with no changes returns None
  6.  rollback_to_round restores files
  7.  get_diff_since_round returns diff string
  8.  file_hash returns 16-char hex string
  9.  file_hash on missing file raises FileNotFoundError
  10. StigmergyWatcher detects file creation
  11. StigmergyWatcher detects file modification
  12. StigmergyWatcher detects file deletion
  13. StigmergyWatcher debounces rapid changes
  14. Sandbox: path traversal rejected
  15. Sandbox: symlink escape rejected
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.stigmergy import (
    SharedWorkspaceManager,
    StigmergyWatcher,
    SandboxViolationError,
    WATCHDOG_AVAILABLE,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _git_available() -> bool:
    """Check if git is available on this system."""
    try:
        subprocess.run(
            ["git", "--version"],
            capture_output=True,
            check=True,
            timeout=5,
        )
        return True
    except (FileNotFoundError, subprocess.SubprocessError):
        return False


GIT_AVAILABLE = _git_available()
requires_git = pytest.mark.skipif(
    not GIT_AVAILABLE, reason="git not available on this system"
)
requires_watchdog = pytest.mark.skipif(
    not WATCHDOG_AVAILABLE, reason="watchdog not installed"
)


def _make_mock_ctx() -> MagicMock:
    """
    Create a mock AsyncContextTree with the interface used by StigmergyWatcher.

    .get(scope, key, default) returns from an internal dict.
    .set(scope, key, value) is an AsyncMock that updates the internal dict.
    """
    ctx = MagicMock()

    store: dict[str, dict[str, object]] = {"project": {}}
    # _scopes must be the same dict as store so the watcher's fallback
    # path (writes ctx._scopes[scope][key] from a timer thread when no
    # event loop is available) shares state with get/set.
    ctx._scopes = store

    def _get(scope: str, key: str, default: object = None) -> object:
        return store.get(scope, {}).get(key, default)

    async def _set(scope: str, key: str, value: object) -> None:
        store.setdefault(scope, {})[key] = value

    ctx.get = MagicMock(side_effect=_get)
    ctx.set = AsyncMock(side_effect=_set)
    ctx._store = store  # Expose for assertions
    return ctx


# ═══════════════════════════════════════════════════════════════════════════
# 1. init_workspace creates directory
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_init_workspace_creates_directory(tmp_path: Path) -> None:
    """init_workspace should create the workspace directory if it doesn't exist."""
    ws_path = tmp_path / "colony_workspace"
    _mgr = SharedWorkspaceManager(ws_path)
    # Constructor should create the directory
    assert ws_path.is_dir()


# ═══════════════════════════════════════════════════════════════════════════
# 2. init_workspace with git creates .git
# ═══════════════════════════════════════════════════════════════════════════


@requires_git
@pytest.mark.asyncio
async def test_init_workspace_with_git(tmp_path: Path) -> None:
    """init_workspace should create a .git directory when git is available."""
    ws_path = tmp_path / "git_workspace"
    mgr = SharedWorkspaceManager(ws_path)
    await mgr.init_workspace()

    assert (ws_path / ".git").is_dir()
    assert mgr.git_enabled is True


# ═══════════════════════════════════════════════════════════════════════════
# 3. init_workspace git failure falls back gracefully
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_init_workspace_git_failure_fallback(tmp_path: Path) -> None:
    """If git init fails, _git_enabled should be False and no exception raised."""
    ws_path = tmp_path / "no_git_workspace"
    mgr = SharedWorkspaceManager(ws_path)

    # Patch _run_git to simulate git not being available
    with patch.object(
        mgr,
        "_run_git",
        side_effect=FileNotFoundError("git not found"),
    ):
        await mgr.init_workspace()

    assert mgr.git_enabled is False
    # Workspace directory should still exist
    assert ws_path.is_dir()


# ═══════════════════════════════════════════════════════════════════════════
# 4. round_commit creates git commit
# ═══════════════════════════════════════════════════════════════════════════


@requires_git
@pytest.mark.asyncio
async def test_round_commit_creates_commit(tmp_path: Path) -> None:
    """round_commit should create a git commit and return a hash."""
    ws_path = tmp_path / "commit_workspace"
    mgr = SharedWorkspaceManager(ws_path)
    await mgr.init_workspace()

    # Create a file to commit
    (ws_path / "output.txt").write_text("Hello from round 1")

    commit_hash = await mgr.round_commit(1, "initial work")
    assert commit_hash is not None
    assert len(commit_hash) >= 7  # Short hash is typically 7+ chars

    # Verify the commit exists in git log
    result = subprocess.run(
        ["git", "-C", str(ws_path), "log", "--oneline"],
        capture_output=True,
        text=True,
    )
    assert "Round 1: initial work" in result.stdout


# ═══════════════════════════════════════════════════════════════════════════
# 5. round_commit with no changes returns None
# ═══════════════════════════════════════════════════════════════════════════


@requires_git
@pytest.mark.asyncio
async def test_round_commit_no_changes_returns_none(tmp_path: Path) -> None:
    """round_commit with nothing staged should return None."""
    ws_path = tmp_path / "empty_commit_workspace"
    mgr = SharedWorkspaceManager(ws_path)
    await mgr.init_workspace()

    # No files created — nothing to commit
    result = await mgr.round_commit(1, "empty round")
    assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# 6. rollback_to_round restores files
# ═══════════════════════════════════════════════════════════════════════════


@requires_git
@pytest.mark.asyncio
async def test_rollback_to_round_restores_files(tmp_path: Path) -> None:
    """rollback_to_round should restore the workspace to a previous state."""
    ws_path = tmp_path / "rollback_workspace"
    mgr = SharedWorkspaceManager(ws_path)
    await mgr.init_workspace()

    # Round 1: create file
    (ws_path / "file.txt").write_text("round 1 content")
    await mgr.round_commit(1, "round 1 work")

    # Round 2: modify file
    (ws_path / "file.txt").write_text("round 2 content")
    (ws_path / "extra.txt").write_text("extra file")
    await mgr.round_commit(2, "round 2 work")

    # Verify round 2 state
    assert (ws_path / "file.txt").read_text() == "round 2 content"
    assert (ws_path / "extra.txt").exists()

    # Rollback to round 1
    await mgr.rollback_to_round(1)

    assert (ws_path / "file.txt").read_text() == "round 1 content"
    assert not (ws_path / "extra.txt").exists()


# ═══════════════════════════════════════════════════════════════════════════
# 7. get_diff_since_round returns diff string
# ═══════════════════════════════════════════════════════════════════════════


@requires_git
@pytest.mark.asyncio
async def test_get_diff_since_round(tmp_path: Path) -> None:
    """get_diff_since_round should return a unified diff string."""
    ws_path = tmp_path / "diff_workspace"
    mgr = SharedWorkspaceManager(ws_path)
    await mgr.init_workspace()

    # Round 1
    (ws_path / "code.py").write_text("def hello():\n    pass\n")
    await mgr.round_commit(1, "initial code")

    # Round 2
    (ws_path / "code.py").write_text("def hello():\n    return 'world'\n")
    await mgr.round_commit(2, "improved code")

    # Get diff since round 1
    diff = await mgr.get_diff_since_round(1)
    assert isinstance(diff, str)
    assert "hello" in diff
    assert "world" in diff


# ═══════════════════════════════════════════════════════════════════════════
# 8. file_hash returns 16-char hex string
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_file_hash_returns_16_char_hex(tmp_path: Path) -> None:
    """file_hash should return a 16-character hex string (SHA-256 prefix)."""
    ws_path = tmp_path / "hash_workspace"
    mgr = SharedWorkspaceManager(ws_path)

    test_file = ws_path / "test.txt"
    test_file.write_text("Hello, FormicOS!")

    result = await mgr.file_hash("test.txt")
    assert isinstance(result, str)
    assert len(result) == 16
    # Verify it's valid hex
    int(result, 16)

    # Same content should produce the same hash
    result2 = await mgr.file_hash("test.txt")
    assert result == result2


# ═══════════════════════════════════════════════════════════════════════════
# 9. file_hash on missing file raises FileNotFoundError
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_file_hash_missing_file_raises(tmp_path: Path) -> None:
    """file_hash on a nonexistent file should raise FileNotFoundError."""
    ws_path = tmp_path / "missing_hash_workspace"
    mgr = SharedWorkspaceManager(ws_path)

    with pytest.raises(FileNotFoundError):
        await mgr.file_hash("nonexistent.txt")


# ═══════════════════════════════════════════════════════════════════════════
# 10. StigmergyWatcher detects file creation
# ═══════════════════════════════════════════════════════════════════════════


@requires_watchdog
@pytest.mark.asyncio
async def test_watcher_detects_file_creation(tmp_path: Path) -> None:
    """StigmergyWatcher should detect a new file and update the context tree."""
    ws_path = tmp_path / "watch_create"
    ws_path.mkdir()

    ctx = _make_mock_ctx()
    watcher = StigmergyWatcher(ws_path, ctx)
    watcher.start()

    try:
        assert watcher.running

        # Create a file
        (ws_path / "new_file.txt").write_text("created")

        # Wait for debounce + processing
        await asyncio.sleep(0.5)

        # Check that the file index was updated
        file_index = ctx._store.get("project", {}).get("file_index", {})
        assert "new_file.txt" in file_index
        assert "hash" in file_index["new_file.txt"]
        assert len(file_index["new_file.txt"]["hash"]) == 16
    finally:
        watcher.stop()

    assert not watcher.running


# ═══════════════════════════════════════════════════════════════════════════
# 11. StigmergyWatcher detects file modification
# ═══════════════════════════════════════════════════════════════════════════


@requires_watchdog
@pytest.mark.asyncio
async def test_watcher_detects_file_modification(tmp_path: Path) -> None:
    """StigmergyWatcher should detect a modified file and update the hash."""
    ws_path = tmp_path / "watch_modify"
    ws_path.mkdir()

    test_file = ws_path / "mutable.txt"
    test_file.write_text("version 1")

    ctx = _make_mock_ctx()
    watcher = StigmergyWatcher(ws_path, ctx)
    watcher.start()

    try:
        # Wait for initial settle
        await asyncio.sleep(0.3)

        # Get initial hash (if watcher picked it up)
        initial_index = dict(ctx._store.get("project", {}).get("file_index", {}))

        # Modify the file
        test_file.write_text("version 2")

        # Wait for debounce + processing
        await asyncio.sleep(0.5)

        updated_index = ctx._store.get("project", {}).get("file_index", {})
        assert "mutable.txt" in updated_index

        # If we had an initial hash, verify it changed
        if "mutable.txt" in initial_index:
            assert updated_index["mutable.txt"]["hash"] != initial_index["mutable.txt"]["hash"]
    finally:
        watcher.stop()


# ═══════════════════════════════════════════════════════════════════════════
# 12. StigmergyWatcher detects file deletion
# ═══════════════════════════════════════════════════════════════════════════


@requires_watchdog
@pytest.mark.asyncio
async def test_watcher_detects_file_deletion(tmp_path: Path) -> None:
    """StigmergyWatcher should remove a deleted file from the index."""
    ws_path = tmp_path / "watch_delete"
    ws_path.mkdir()

    doomed_file = ws_path / "doomed.txt"
    doomed_file.write_text("soon to be deleted")

    ctx = _make_mock_ctx()
    watcher = StigmergyWatcher(ws_path, ctx)
    watcher.start()

    try:
        # Wait for initial detection
        await asyncio.sleep(0.5)

        # Verify file was indexed
        index_before = ctx._store.get("project", {}).get("file_index", {})
        # The file might or might not be indexed yet depending on OS events;
        # seed the index manually to make the test deterministic
        if "doomed.txt" not in index_before:
            await ctx.set("project", "file_index", {
                "doomed.txt": {"hash": "0" * 16, "timestamp": time.time()}
            })

        # Delete the file
        doomed_file.unlink()

        # Wait for debounce + processing
        await asyncio.sleep(0.5)

        index_after = ctx._store.get("project", {}).get("file_index", {})
        assert "doomed.txt" not in index_after
    finally:
        watcher.stop()


# ═══════════════════════════════════════════════════════════════════════════
# 13. StigmergyWatcher debounces rapid changes
# ═══════════════════════════════════════════════════════════════════════════


@requires_watchdog
@pytest.mark.asyncio
async def test_watcher_debounces_rapid_changes(tmp_path: Path) -> None:
    """
    Rapid file writes within the 100ms debounce window should be collapsed
    into a single context tree update.
    """
    ws_path = tmp_path / "watch_debounce"
    ws_path.mkdir()

    ctx = _make_mock_ctx()
    watcher = StigmergyWatcher(ws_path, ctx)
    watcher.start()

    try:
        rapid_file = ws_path / "rapid.txt"

        # Write rapidly (well within 100ms debounce window)
        for i in range(10):
            rapid_file.write_text(f"version {i}")

        # Wait for debounce window to expire and processing
        await asyncio.sleep(0.5)

        # The file should exist in the index with the final content's hash
        file_index = ctx._store.get("project", {}).get("file_index", {})
        assert "rapid.txt" in file_index

        # The set() call count should be significantly less than 10
        # (debounce should collapse the rapid writes)
        set_calls = [
            c for c in ctx.set.call_args_list
            if c[0][0] == "project" and c[0][1] == "file_index"
        ]
        # Due to debouncing, we expect far fewer updates than 10
        assert len(set_calls) < 10, (
            f"Expected debouncing to reduce updates, got {len(set_calls)} calls"
        )
    finally:
        watcher.stop()


# ═══════════════════════════════════════════════════════════════════════════
# 14. Sandbox: path traversal rejected
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sandbox_path_traversal_rejected(tmp_path: Path) -> None:
    """Paths using .. to escape the workspace should be rejected."""
    ws_path = tmp_path / "sandbox_workspace"
    mgr = SharedWorkspaceManager(ws_path)

    # Attempt to access a file outside the workspace via path traversal
    with pytest.raises(SandboxViolationError):
        mgr.validate_path("../../etc/passwd")

    with pytest.raises(SandboxViolationError):
        mgr.validate_path("../sibling/secret.txt")

    # file_hash should also reject traversal
    with pytest.raises(SandboxViolationError):
        await mgr.file_hash("../../etc/passwd")


# ═══════════════════════════════════════════════════════════════════════════
# 15. Sandbox: symlink escape rejected
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sandbox_symlink_escape_rejected(tmp_path: Path) -> None:
    """A symlink pointing outside the workspace should be rejected."""
    ws_path = tmp_path / "symlink_workspace"
    ws_path.mkdir(parents=True)

    # Create a directory outside the workspace
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    secret = outside_dir / "secret.txt"
    secret.write_text("sensitive data")

    # Create a symlink inside the workspace pointing outside
    symlink_path = ws_path / "escape_link"
    try:
        symlink_path.symlink_to(outside_dir)
    except OSError:
        pytest.skip("Symlink creation not supported (requires privileges on Windows)")

    mgr = SharedWorkspaceManager(ws_path)

    # The symlink resolves outside the workspace -- should be rejected
    with pytest.raises(SandboxViolationError):
        mgr.validate_path("escape_link/secret.txt")

    with pytest.raises(SandboxViolationError):
        await mgr.file_hash("escape_link/secret.txt")


# ═══════════════════════════════════════════════════════════════════════════
# Additional edge cases
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_watcher_no_watchdog_graceful() -> None:
    """StigmergyWatcher.start() should be a no-op when watchdog is not installed."""
    ctx = _make_mock_ctx()

    with patch("src.stigmergy.WATCHDOG_AVAILABLE", False):
        watcher = StigmergyWatcher("/fake/path", ctx)
        watcher.start()
        assert not watcher.running
        watcher.stop()  # Should not raise


@pytest.mark.asyncio
async def test_round_commit_git_disabled(tmp_path: Path) -> None:
    """round_commit should return None when git is disabled."""
    ws_path = tmp_path / "no_git"
    mgr = SharedWorkspaceManager(ws_path)
    # git_enabled is False by default (no init_workspace called)
    assert mgr.git_enabled is False

    result = await mgr.round_commit(1, "test")
    assert result is None


@pytest.mark.asyncio
async def test_get_diff_since_round_git_disabled(tmp_path: Path) -> None:
    """get_diff_since_round should return empty string when git is disabled."""
    ws_path = tmp_path / "no_git_diff"
    mgr = SharedWorkspaceManager(ws_path)

    diff = await mgr.get_diff_since_round(1)
    assert diff == ""


@requires_git
@pytest.mark.asyncio
async def test_rollback_to_nonexistent_round(tmp_path: Path) -> None:
    """rollback_to_round with a non-existent round should raise ValueError."""
    ws_path = tmp_path / "rollback_fail"
    mgr = SharedWorkspaceManager(ws_path)
    await mgr.init_workspace()

    with pytest.raises(ValueError, match="No commit found for round"):
        await mgr.rollback_to_round(999)


@requires_git
@pytest.mark.asyncio
async def test_init_workspace_with_task_branch(tmp_path: Path) -> None:
    """init_workspace with task_branch should create and checkout that branch."""
    ws_path = tmp_path / "branch_workspace"
    mgr = SharedWorkspaceManager(ws_path)
    await mgr.init_workspace(task_branch="colony-42")

    result = subprocess.run(
        ["git", "-C", str(ws_path), "branch", "--show-current"],
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "colony-42"


@pytest.mark.asyncio
async def test_validate_path_within_workspace(tmp_path: Path) -> None:
    """validate_path should succeed for paths within the workspace."""
    ws_path = tmp_path / "valid_workspace"
    mgr = SharedWorkspaceManager(ws_path)

    # Create a file inside the workspace
    (ws_path / "safe.txt").write_text("safe content")

    resolved = mgr.validate_path("safe.txt")
    assert resolved == (ws_path / "safe.txt").resolve()
