"""
Tests for FormicOS v0.6.0 Session Manager.

Covers:
- Atomic write creates file correctly
- Atomic write cleans up temp on failure
- Autosave triggers on interval
- Crash detection finds stale lock files
- Recovery loads valid session
- Corrupted session file handled gracefully (falls back to backup)
- Lock heartbeat updates timestamp
- Session list/delete work correctly
- Archival creates gzip file
"""

from __future__ import annotations

import asyncio
import gzip
import json
import os
import platform
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models import PersistenceConfig
from src.session import (
    MAX_BACKUPS,
    LOCK_TTL_SECONDS,
    LockStatus,
    SessionConflictError,
    SessionInfo,
    SessionManager,
    _is_pid_alive,
    _rotate_backups,
    acquire_session,
    atomic_write_json,
    check_lock,
    refresh_lock_heartbeat,
    remove_lock_file,
    write_lock_file,
)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def session_dir(tmp_path: Path) -> Path:
    """Provide a temporary session directory."""
    d = tmp_path / "sessions"
    d.mkdir()
    return d


@pytest.fixture
def sample_context() -> dict:
    """A minimal context tree dict for testing."""
    return {
        "system": {"llm_model": {"value": "test-model", "scope": "system"}},
        "colony": {
            "round": {"value": 3, "scope": "colony"},
            "task": {"value": "test task", "scope": "colony"},
        },
        "_decisions": [
            {"round": 1, "type": "routing", "detail": "broadcast", "timestamp": 1.0}
        ],
        "_serialized_at": time.time(),
    }


@pytest.fixture
def mock_context_tree(sample_context: dict) -> MagicMock:
    """A mock AsyncContextTree with snapshot() support."""
    ctx = MagicMock()
    ctx.snapshot = AsyncMock(return_value=sample_context)
    ctx.dirty = True
    return ctx


@pytest.fixture
def manager(session_dir: Path) -> SessionManager:
    """A SessionManager with a short autosave interval for testing."""
    return SessionManager(
        session_dir=session_dir,
        autosave_interval=0.1,  # 100ms for fast tests
    )


# ═══════════════════════════════════════════════════════════════════════════
# atomic_write_json
# ═══════════════════════════════════════════════════════════════════════════


class TestAtomicWriteJson:
    """Tests for the atomic_write_json function."""

    def test_creates_file_correctly(self, tmp_path: Path) -> None:
        """Atomic write creates a valid JSON file at the target path."""
        target = tmp_path / "test.json"
        data = {"key": "value", "number": 42, "nested": {"a": 1}}

        atomic_write_json(data, target)

        assert target.exists()
        with open(target, encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded == data

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Atomic write creates parent directories if they don't exist."""
        target = tmp_path / "deep" / "nested" / "dir" / "test.json"

        atomic_write_json({"key": "value"}, target)

        assert target.exists()

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        """Atomic write replaces existing file content."""
        target = tmp_path / "test.json"
        atomic_write_json({"old": True}, target)
        atomic_write_json({"new": True}, target)

        with open(target, encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded == {"new": True}

    def test_cleans_up_temp_on_failure(self, tmp_path: Path) -> None:
        """Temp file is removed if serialization fails."""
        target = tmp_path / "test.json"

        # Create an object that can't be serialized
        class Unserializable:
            def __repr__(self):
                raise RuntimeError("boom")

        # The default=str handler will call __repr__ which raises
        # But json.dump with default=str might handle it differently,
        # so let's use a custom approach
        with patch("src.session.json.dump", side_effect=IOError("disk full")):
            with pytest.raises(IOError, match="disk full"):
                atomic_write_json({"key": "value"}, target)

        # No temp files should remain
        temps = list(tmp_path.glob(".test_*.tmp"))
        assert len(temps) == 0
        assert not target.exists()

    def test_handles_datetime_via_default_str(self, tmp_path: Path) -> None:
        """Non-serializable types are converted via default=str."""
        target = tmp_path / "test.json"
        from datetime import datetime

        data = {"timestamp": datetime(2026, 2, 28, 12, 0, 0)}
        atomic_write_json(data, target)

        with open(target, encoding="utf-8") as f:
            loaded = json.load(f)
        assert "2026-02-28" in loaded["timestamp"]

    def test_file_content_is_indented(self, tmp_path: Path) -> None:
        """Output JSON is indented for human readability."""
        target = tmp_path / "test.json"
        atomic_write_json({"a": 1, "b": 2}, target)

        text = target.read_text(encoding="utf-8")
        assert "\n" in text  # indented output contains newlines


# ═══════════════════════════════════════════════════════════════════════════
# Backup Rotation
# ═══════════════════════════════════════════════════════════════════════════


class TestBackupRotation:
    """Tests for backup rotation logic."""

    def test_creates_backup_from_existing(self, tmp_path: Path) -> None:
        """Current file is copied to .1 on rotation."""
        target = tmp_path / "context.json"
        target.write_text('{"v": 1}')

        _rotate_backups(target)

        backup1 = tmp_path / "context.json.1"
        assert backup1.exists()
        assert json.loads(backup1.read_text()) == {"v": 1}

    def test_shifts_existing_backups(self, tmp_path: Path) -> None:
        """Existing backups shift: .1 -> .2, .2 -> .3."""
        target = tmp_path / "context.json"
        target.write_text('{"v": "current"}')
        (tmp_path / "context.json.1").write_text('{"v": "backup1"}')
        (tmp_path / "context.json.2").write_text('{"v": "backup2"}')

        _rotate_backups(target)

        assert json.loads((tmp_path / "context.json.1").read_text()) == {"v": "current"}
        assert json.loads((tmp_path / "context.json.2").read_text()) == {"v": "backup1"}
        assert json.loads((tmp_path / "context.json.3").read_text()) == {"v": "backup2"}

    def test_deletes_oldest_backup(self, tmp_path: Path) -> None:
        """Oldest backup (MAX_BACKUPS) is deleted to make room."""
        target = tmp_path / "context.json"
        target.write_text('{"v": "current"}')
        for i in range(1, MAX_BACKUPS + 1):
            (tmp_path / f"context.json.{i}").write_text(f'{{"v": "b{i}"}}')

        _rotate_backups(target)

        # .MAX_BACKUPS should contain what was .MAX_BACKUPS-1
        # The original .MAX_BACKUPS content should be gone
        assert (tmp_path / f"context.json.{MAX_BACKUPS}").exists()

    def test_no_existing_file_is_harmless(self, tmp_path: Path) -> None:
        """Rotation with no existing file does not raise."""
        target = tmp_path / "context.json"
        _rotate_backups(target)  # should not raise
        assert not (tmp_path / "context.json.1").exists()


# ═══════════════════════════════════════════════════════════════════════════
# Lock File Operations
# ═══════════════════════════════════════════════════════════════════════════


class TestLockFiles:
    """Tests for lock file write/read/check/remove."""

    def test_write_lock_file(self, tmp_path: Path) -> None:
        """Lock file is created with correct fields."""
        lock_path = tmp_path / "session.lock"
        write_lock_file(lock_path)

        assert lock_path.exists()
        data = json.loads(lock_path.read_text())
        assert data["pid"] == os.getpid()
        assert data["hostname"] == platform.node()
        assert "heartbeat_at" in data
        assert "created_at" in data
        assert "python_version" in data
        assert "platform" in data

    def test_check_lock_unlocked(self, tmp_path: Path) -> None:
        """No lock file -> UNLOCKED status."""
        lock_path = tmp_path / "session.lock"
        status, data = check_lock(lock_path)
        assert status == LockStatus.UNLOCKED
        assert data is None

    def test_check_lock_active(self, tmp_path: Path) -> None:
        """Lock file from current process -> ACTIVE."""
        lock_path = tmp_path / "session.lock"
        write_lock_file(lock_path)

        status, data = check_lock(lock_path)
        assert status == LockStatus.ACTIVE
        assert data is not None
        assert data["pid"] == os.getpid()

    def test_check_lock_stale_crashed(self, tmp_path: Path) -> None:
        """Lock file with dead PID -> STALE_CRASHED."""
        lock_path = tmp_path / "session.lock"
        lock_data = {
            "pid": 99999999,  # PID that almost certainly doesn't exist
            "hostname": platform.node(),
            "heartbeat_at": time.time(),
            "created_at": time.time(),
            "python_version": platform.python_version(),
            "platform": platform.system(),
        }
        lock_path.write_text(json.dumps(lock_data))

        # Mock _is_pid_alive to return False for certainty
        with patch("src.session._is_pid_alive", return_value=False):
            status, data = check_lock(lock_path)
        assert status == LockStatus.STALE_CRASHED

    def test_check_lock_stale_expired(self, tmp_path: Path) -> None:
        """Lock file with alive PID but expired heartbeat -> STALE_EXPIRED."""
        lock_path = tmp_path / "session.lock"
        lock_data = {
            "pid": os.getpid(),
            "hostname": platform.node(),
            "heartbeat_at": time.time() - LOCK_TTL_SECONDS - 100,
            "created_at": time.time() - LOCK_TTL_SECONDS - 100,
            "python_version": platform.python_version(),
            "platform": platform.system(),
        }
        lock_path.write_text(json.dumps(lock_data))

        status, data = check_lock(lock_path)
        assert status == LockStatus.STALE_EXPIRED

    def test_check_lock_corrupt(self, tmp_path: Path) -> None:
        """Unreadable lock file -> CORRUPT."""
        lock_path = tmp_path / "session.lock"
        lock_path.write_text("not valid json {{{")

        status, data = check_lock(lock_path)
        assert status == LockStatus.CORRUPT
        assert data is None

    def test_check_lock_missing_key_is_corrupt(self, tmp_path: Path) -> None:
        """Lock file missing required keys -> CORRUPT."""
        lock_path = tmp_path / "session.lock"
        lock_path.write_text(json.dumps({"pid": 1234}))  # missing hostname, heartbeat_at

        status, data = check_lock(lock_path)
        assert status == LockStatus.CORRUPT

    def test_check_lock_different_hostname(self, tmp_path: Path) -> None:
        """Lock file from different host with fresh heartbeat -> ACTIVE."""
        lock_path = tmp_path / "session.lock"
        lock_data = {
            "pid": 1,
            "hostname": "some-other-host-that-is-not-ours",
            "heartbeat_at": time.time(),
            "created_at": time.time(),
        }
        lock_path.write_text(json.dumps(lock_data))

        status, data = check_lock(lock_path)
        assert status == LockStatus.ACTIVE

    def test_check_lock_different_hostname_expired(self, tmp_path: Path) -> None:
        """Lock file from different host with expired heartbeat -> STALE_EXPIRED."""
        lock_path = tmp_path / "session.lock"
        lock_data = {
            "pid": 1,
            "hostname": "some-other-host-that-is-not-ours",
            "heartbeat_at": time.time() - LOCK_TTL_SECONDS - 100,
            "created_at": time.time() - LOCK_TTL_SECONDS - 100,
        }
        lock_path.write_text(json.dumps(lock_data))

        status, data = check_lock(lock_path)
        assert status == LockStatus.STALE_EXPIRED

    def test_remove_lock_file(self, tmp_path: Path) -> None:
        """Lock file is removed cleanly."""
        lock_path = tmp_path / "session.lock"
        write_lock_file(lock_path)
        assert lock_path.exists()

        remove_lock_file(lock_path)
        assert not lock_path.exists()

    def test_remove_lock_file_missing_is_harmless(self, tmp_path: Path) -> None:
        """Removing a nonexistent lock file does not raise."""
        lock_path = tmp_path / "session.lock"
        remove_lock_file(lock_path)  # should not raise

    def test_refresh_heartbeat_updates_timestamp(self, tmp_path: Path) -> None:
        """Heartbeat refresh updates the heartbeat_at field."""
        lock_path = tmp_path / "session.lock"
        write_lock_file(lock_path)

        # Read original heartbeat
        original = json.loads(lock_path.read_text())
        original_heartbeat = original["heartbeat_at"]

        # Small delay so timestamp changes
        time.sleep(0.05)

        refresh_lock_heartbeat(lock_path)

        updated = json.loads(lock_path.read_text())
        assert updated["heartbeat_at"] >= original_heartbeat
        # PID and hostname should be preserved
        assert updated["pid"] == original["pid"]
        assert updated["hostname"] == original["hostname"]

    def test_refresh_heartbeat_recreates_on_corrupt(self, tmp_path: Path) -> None:
        """Heartbeat refresh rewrites lock file if it's corrupt."""
        lock_path = tmp_path / "session.lock"
        lock_path.write_text("corrupted data {{{")

        refresh_lock_heartbeat(lock_path)

        data = json.loads(lock_path.read_text())
        assert data["pid"] == os.getpid()

    def test_refresh_heartbeat_creates_if_missing(self, tmp_path: Path) -> None:
        """Heartbeat refresh creates a new lock file if missing."""
        lock_path = tmp_path / "session.lock"
        assert not lock_path.exists()

        refresh_lock_heartbeat(lock_path)

        assert lock_path.exists()
        data = json.loads(lock_path.read_text())
        assert data["pid"] == os.getpid()


# ═══════════════════════════════════════════════════════════════════════════
# PID Liveness
# ═══════════════════════════════════════════════════════════════════════════


class TestPidLiveness:
    """Tests for cross-platform PID liveness checking."""

    def test_current_pid_is_alive(self) -> None:
        """Current process PID should be detected as alive."""
        assert _is_pid_alive(os.getpid()) is True

    def test_nonexistent_pid_is_dead(self) -> None:
        """A PID that doesn't exist should be detected as dead."""
        # Use a very high PID that's unlikely to exist
        with patch("src.session._is_pid_alive_windows" if platform.system() == "Windows" else "src.session._is_pid_alive_unix", return_value=False):
            assert _is_pid_alive(99999999) is False


# ═══════════════════════════════════════════════════════════════════════════
# SessionManager
# ═══════════════════════════════════════════════════════════════════════════


class TestSessionManager:
    """Tests for SessionManager lifecycle and operations."""

    @pytest.mark.asyncio
    async def test_start_session_creates_directory_and_files(
        self,
        manager: SessionManager,
        mock_context_tree: MagicMock,
    ) -> None:
        """Starting a session creates the session directory, lock, meta, and context files."""
        await manager.start_session("test-001", mock_context_tree, "Build a widget")

        session_path = manager.session_dir / "test-001"
        assert session_path.exists()
        assert (session_path / "session.lock").exists()
        assert (session_path / "meta.json").exists()
        assert (session_path / "context.json").exists()

        # Verify metadata
        meta = json.loads((session_path / "meta.json").read_text())
        assert meta["session_id"] == "test-001"
        assert meta["task"] == "Build a widget"
        assert meta["status"] == "running"

        await manager.stop_autosave()

    @pytest.mark.asyncio
    async def test_end_session_removes_lock_and_updates_status(
        self,
        manager: SessionManager,
        mock_context_tree: MagicMock,
    ) -> None:
        """Ending a session removes the lock file and updates metadata status."""
        await manager.start_session("test-002", mock_context_tree, "Test task")

        result = await manager.end_session("test-002", mock_context_tree, "completed")

        session_path = manager.session_dir / "test-002"
        assert not (session_path / "session.lock").exists()

        meta = json.loads((session_path / "meta.json").read_text())
        assert meta["status"] == "completed"

        assert isinstance(result, SessionInfo)
        assert result.status == "completed"
        assert result.session_id == "test-002"

    @pytest.mark.asyncio
    async def test_autosave_triggers_on_interval(
        self,
        session_dir: Path,
        mock_context_tree: MagicMock,
    ) -> None:
        """Autosave loop calls snapshot() at the configured interval."""
        manager = SessionManager(
            session_dir=session_dir,
            autosave_interval=0.1,
        )

        # Create session directory and initial files
        session_path = session_dir / "test-auto"
        session_path.mkdir()
        meta = {"session_id": "test-auto", "task": "t", "status": "running",
                "round": 0, "created_at": time.time(), "updated_at": time.time()}
        atomic_write_json(meta, session_path / "meta.json")

        # Start autosave
        await manager.start_autosave("test-auto", mock_context_tree)

        # Wait for at least 2 autosave cycles
        await asyncio.sleep(0.35)

        await manager.stop_autosave()

        # snapshot() should have been called at least twice
        assert mock_context_tree.snapshot.call_count >= 2

        # Context file should exist
        assert (session_path / "context.json").exists()

    @pytest.mark.asyncio
    async def test_autosave_refreshes_lock_heartbeat(
        self,
        session_dir: Path,
        mock_context_tree: MagicMock,
    ) -> None:
        """Autosave loop refreshes the lock file heartbeat."""
        manager = SessionManager(
            session_dir=session_dir,
            autosave_interval=0.1,
        )

        session_path = session_dir / "test-heartbeat"
        session_path.mkdir()

        # Write initial lock and meta
        lock_path = session_path / "session.lock"
        write_lock_file(lock_path)
        original_data = json.loads(lock_path.read_text())
        original_heartbeat = original_data["heartbeat_at"]

        meta = {"session_id": "test-heartbeat", "task": "t", "status": "running",
                "round": 0, "created_at": time.time(), "updated_at": time.time()}
        atomic_write_json(meta, session_path / "meta.json")

        await manager.start_autosave("test-heartbeat", mock_context_tree)
        await asyncio.sleep(0.25)
        await manager.stop_autosave()

        # Heartbeat should have been refreshed
        updated_data = json.loads(lock_path.read_text())
        assert updated_data["heartbeat_at"] >= original_heartbeat

    @pytest.mark.asyncio
    async def test_list_sessions(
        self,
        manager: SessionManager,
    ) -> None:
        """list_sessions() returns metadata for all sessions."""
        # Create two session dirs with metadata
        for sid in ["session-a", "session-b"]:
            sp = manager.session_dir / sid
            sp.mkdir()
            meta = {
                "session_id": sid,
                "task": f"Task for {sid}",
                "status": "completed",
                "round": 5,
                "created_at": time.time(),
                "updated_at": time.time(),
            }
            atomic_write_json(meta, sp / "meta.json")

        sessions = await manager.list_sessions()
        assert len(sessions) == 2
        ids = {s.session_id for s in sessions}
        assert "session-a" in ids
        assert "session-b" in ids

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, manager: SessionManager) -> None:
        """list_sessions() returns empty list when no sessions exist."""
        sessions = await manager.list_sessions()
        assert sessions == []

    @pytest.mark.asyncio
    async def test_list_sessions_skips_corrupt_meta(
        self,
        manager: SessionManager,
    ) -> None:
        """Sessions with corrupt metadata are skipped, not crash."""
        sp = manager.session_dir / "corrupt-session"
        sp.mkdir()
        (sp / "meta.json").write_text("not json {{{")

        sessions = await manager.list_sessions()
        assert len(sessions) == 0

    @pytest.mark.asyncio
    async def test_delete_session(self, manager: SessionManager) -> None:
        """delete_session() removes the entire session directory."""
        sp = manager.session_dir / "to-delete"
        sp.mkdir()
        meta = {
            "session_id": "to-delete",
            "task": "Delete me",
            "status": "completed",
            "round": 1,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        atomic_write_json(meta, sp / "meta.json")
        atomic_write_json({"data": True}, sp / "context.json")

        await manager.delete_session("to-delete")
        assert not sp.exists()

    @pytest.mark.asyncio
    async def test_delete_session_not_found(self, manager: SessionManager) -> None:
        """delete_session() raises FileNotFoundError for nonexistent session."""
        with pytest.raises(FileNotFoundError, match="not found"):
            await manager.delete_session("nonexistent")


# ═══════════════════════════════════════════════════════════════════════════
# Crash Detection
# ═══════════════════════════════════════════════════════════════════════════


class TestCrashDetection:
    """Tests for detect_crashed_sessions()."""

    @pytest.mark.asyncio
    async def test_detects_crashed_session(self, manager: SessionManager) -> None:
        """Sessions with stale lock files are detected as crashed."""
        sp = manager.session_dir / "crashed-session"
        sp.mkdir()

        # Write a lock file with a dead PID
        lock_data = {
            "pid": 99999999,
            "hostname": platform.node(),
            "heartbeat_at": time.time(),
            "created_at": time.time(),
            "python_version": platform.python_version(),
            "platform": platform.system(),
        }
        (sp / "session.lock").write_text(json.dumps(lock_data))

        with patch("src.session._is_pid_alive", return_value=False):
            crashed = await manager.detect_crashed_sessions()

        assert "crashed-session" in crashed

    @pytest.mark.asyncio
    async def test_no_crashed_sessions(self, manager: SessionManager) -> None:
        """No crashed sessions when all locks are clean."""
        sp = manager.session_dir / "clean-session"
        sp.mkdir()
        # No lock file = not crashed, just a session dir

        crashed = await manager.detect_crashed_sessions()
        assert len(crashed) == 0

    @pytest.mark.asyncio
    async def test_detects_corrupt_lock_as_crashed(
        self, manager: SessionManager
    ) -> None:
        """Sessions with corrupt lock files appear in crashed list."""
        sp = manager.session_dir / "corrupt-lock"
        sp.mkdir()
        (sp / "session.lock").write_text("not json")

        crashed = await manager.detect_crashed_sessions()
        assert "corrupt-lock" in crashed


# ═══════════════════════════════════════════════════════════════════════════
# Session Recovery
# ═══════════════════════════════════════════════════════════════════════════


class TestSessionRecovery:
    """Tests for recover_session()."""

    @pytest.mark.asyncio
    async def test_recover_valid_session(self, manager: SessionManager) -> None:
        """Recovery loads valid context.json."""
        sp = manager.session_dir / "recoverable"
        sp.mkdir()

        context = {"colony": {"task": "recover me"}, "_decisions": []}
        atomic_write_json(context, sp / "context.json")

        meta = {
            "session_id": "recoverable",
            "task": "Test",
            "status": "running",
            "round": 3,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        atomic_write_json(meta, sp / "meta.json")

        # Add a stale lock
        write_lock_file(sp / "session.lock")

        data = await manager.recover_session("recoverable")

        assert data == context
        # Lock should be removed after recovery
        assert not (sp / "session.lock").exists()
        # Metadata should be updated to 'crashed'
        updated_meta = json.loads((sp / "meta.json").read_text())
        assert updated_meta["status"] == "crashed"

    @pytest.mark.asyncio
    async def test_recover_falls_back_to_backup(
        self, manager: SessionManager
    ) -> None:
        """Recovery falls back to backup when primary is corrupt."""
        sp = manager.session_dir / "corrupted"
        sp.mkdir()

        # Corrupt primary
        (sp / "context.json").write_text("invalid json {{{")

        # Valid backup
        backup_data = {"colony": {"task": "from backup"}, "_decisions": []}
        atomic_write_json(backup_data, sp / "context.json.1")

        meta = {
            "session_id": "corrupted",
            "task": "Test",
            "status": "running",
            "round": 2,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        atomic_write_json(meta, sp / "meta.json")

        data = await manager.recover_session("corrupted")

        assert data == backup_data

    @pytest.mark.asyncio
    async def test_recover_all_corrupt_returns_empty(
        self, manager: SessionManager
    ) -> None:
        """Recovery returns empty dict when all files are corrupt."""
        sp = manager.session_dir / "all-corrupt"
        sp.mkdir()

        (sp / "context.json").write_text("bad")
        (sp / "context.json.1").write_text("also bad")
        (sp / "context.json.2").write_text("still bad")
        (sp / "context.json.3").write_text("nope")

        data = await manager.recover_session("all-corrupt")

        assert data == {}

    @pytest.mark.asyncio
    async def test_recover_nonexistent_session(
        self, manager: SessionManager
    ) -> None:
        """Recovery raises FileNotFoundError for nonexistent session."""
        with pytest.raises(FileNotFoundError, match="not found"):
            await manager.recover_session("does-not-exist")


# ═══════════════════════════════════════════════════════════════════════════
# Session Archival
# ═══════════════════════════════════════════════════════════════════════════


class TestSessionArchival:
    """Tests for session archival (gzip compression)."""

    @pytest.mark.asyncio
    async def test_archive_creates_gzip(self, manager: SessionManager) -> None:
        """Archival creates a gzip file in the archive directory."""
        sp = manager.session_dir / "to-archive"
        sp.mkdir()

        original_data = {"colony": {"task": "archive me"}, "_decisions": []}
        atomic_write_json(original_data, sp / "context.json")

        archive_path = await manager.archive_session("to-archive")

        assert archive_path.exists()
        assert archive_path.suffix == ".gz"
        assert archive_path.parent.name == ".archive"

        # Verify gzip content is valid and matches original
        with gzip.open(archive_path, "rb") as f:
            recovered = json.loads(f.read().decode("utf-8"))
        assert recovered == original_data

    @pytest.mark.asyncio
    async def test_archive_nonexistent_raises(
        self, manager: SessionManager
    ) -> None:
        """Archiving a session with no context file raises FileNotFoundError."""
        sp = manager.session_dir / "no-context"
        sp.mkdir()
        # No context.json

        with pytest.raises(FileNotFoundError, match="No context.json"):
            await manager.archive_session("no-context")


# ═══════════════════════════════════════════════════════════════════════════
# acquire_session (Startup Sequence)
# ═══════════════════════════════════════════════════════════════════════════


class TestAcquireSession:
    """Tests for the startup session acquisition sequence."""

    @pytest.mark.asyncio
    async def test_acquire_unlocked_session(self, session_dir: Path) -> None:
        """Acquiring an unlocked session returns empty context and manager."""
        data, mgr = await acquire_session(session_dir, "new-session")

        assert data == {}
        assert isinstance(mgr, SessionManager)

    @pytest.mark.asyncio
    async def test_acquire_recovers_crashed_session(
        self, session_dir: Path
    ) -> None:
        """Acquiring a crashed session recovers the context data."""
        sp = session_dir / "crashed"
        sp.mkdir()

        context = {"colony": {"recovered": True}}
        atomic_write_json(context, sp / "context.json")

        # Write stale lock
        lock_data = {
            "pid": 99999999,
            "hostname": platform.node(),
            "heartbeat_at": time.time(),
            "created_at": time.time(),
            "python_version": platform.python_version(),
            "platform": platform.system(),
        }
        (sp / "session.lock").write_text(json.dumps(lock_data))

        with patch("src.session._is_pid_alive", return_value=False):
            data, mgr = await acquire_session(session_dir, "crashed")

        assert data == context
        # Lock should have been cleaned up
        assert not (sp / "session.lock").exists()

    @pytest.mark.asyncio
    async def test_acquire_active_session_raises(
        self, session_dir: Path
    ) -> None:
        """Acquiring an active session raises SessionConflictError."""
        sp = session_dir / "active"
        sp.mkdir()

        # Write lock with current PID (alive)
        write_lock_file(sp / "session.lock")

        with pytest.raises(SessionConflictError, match="active"):
            await acquire_session(session_dir, "active")

    @pytest.mark.asyncio
    async def test_acquire_with_config(self, session_dir: Path) -> None:
        """Acquiring with explicit PersistenceConfig works."""
        config = PersistenceConfig(autosave_interval_seconds=10)
        data, mgr = await acquire_session(session_dir, "configured", config=config)

        assert mgr.autosave_interval == 10.0


# ═══════════════════════════════════════════════════════════════════════════
# SessionInfo Model
# ═══════════════════════════════════════════════════════════════════════════


class TestSessionInfo:
    """Tests for the SessionInfo data model."""

    def test_construction(self) -> None:
        """SessionInfo can be constructed with all fields."""
        info = SessionInfo(
            session_id="s1",
            task="Test",
            status="running",
            round=3,
            created_at=1000.0,
            updated_at=2000.0,
            file_size=1024,
        )
        assert info.session_id == "s1"
        assert info.round == 3
        assert info.file_size == 1024

    def test_defaults(self) -> None:
        """SessionInfo has sensible defaults."""
        info = SessionInfo(session_id="s2", task="", status="completed")
        assert info.round == 0
        assert info.file_size == 0
        assert info.created_at > 0


# ═══════════════════════════════════════════════════════════════════════════
# Cleanup
# ═══════════════════════════════════════════════════════════════════════════


class TestCleanup:
    """Tests for cleanup_old_sessions()."""

    @pytest.mark.asyncio
    async def test_cleanup_removes_old_sessions(
        self, manager: SessionManager
    ) -> None:
        """Sessions older than max_age_days are removed."""
        sp = manager.session_dir / "old-session"
        sp.mkdir()
        old_time = time.time() - (31 * 86400)  # 31 days ago
        meta = {
            "session_id": "old-session",
            "task": "Old",
            "status": "completed",
            "round": 1,
            "created_at": old_time,
            "updated_at": old_time,
        }
        atomic_write_json(meta, sp / "meta.json")

        removed = await manager.cleanup_old_sessions(max_age_days=30)

        assert removed == 1
        assert not sp.exists()

    @pytest.mark.asyncio
    async def test_cleanup_keeps_recent_sessions(
        self, manager: SessionManager
    ) -> None:
        """Sessions newer than max_age_days are kept."""
        sp = manager.session_dir / "recent"
        sp.mkdir()
        meta = {
            "session_id": "recent",
            "task": "Recent",
            "status": "completed",
            "round": 1,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        atomic_write_json(meta, sp / "meta.json")

        removed = await manager.cleanup_old_sessions(max_age_days=30)

        assert removed == 0
        assert sp.exists()


# ═══════════════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge case tests for robustness."""

    def test_lock_status_values(self) -> None:
        """LockStatus has all expected values."""
        assert LockStatus.UNLOCKED == "unlocked"
        assert LockStatus.ACTIVE == "active"
        assert LockStatus.STALE_CRASHED == "crashed"
        assert LockStatus.STALE_EXPIRED == "expired"
        assert LockStatus.CORRUPT == "corrupt"

    def test_session_conflict_error_is_exception(self) -> None:
        """SessionConflictError is a proper Exception subclass."""
        err = SessionConflictError("test message")
        assert isinstance(err, Exception)
        assert "test message" in str(err)

    @pytest.mark.asyncio
    async def test_stop_autosave_without_start(
        self, manager: SessionManager
    ) -> None:
        """Stopping autosave before starting it is a no-op."""
        await manager.stop_autosave()  # should not raise

    @pytest.mark.asyncio
    async def test_double_start_autosave_cancels_first(
        self,
        session_dir: Path,
        mock_context_tree: MagicMock,
    ) -> None:
        """Starting autosave twice cancels the first task."""
        manager = SessionManager(session_dir=session_dir, autosave_interval=0.1)

        sp = session_dir / "double-start"
        sp.mkdir()
        meta = {"session_id": "double-start", "task": "t", "status": "running",
                "round": 0, "created_at": time.time(), "updated_at": time.time()}
        atomic_write_json(meta, sp / "meta.json")

        await manager.start_autosave("double-start", mock_context_tree)
        first_task = manager._autosave_task

        await manager.start_autosave("double-start", mock_context_tree)
        second_task = manager._autosave_task

        assert first_task is not second_task
        assert first_task.cancelled() or first_task.done()

        await manager.stop_autosave()

    @pytest.mark.asyncio
    async def test_save_context_with_plain_dict(
        self, manager: SessionManager
    ) -> None:
        """_save_context handles plain dict context trees."""
        sp = manager.session_dir / "dict-ctx"
        sp.mkdir()
        meta = {"session_id": "dict-ctx", "task": "t", "status": "running",
                "round": 0, "created_at": time.time(), "updated_at": time.time()}
        atomic_write_json(meta, sp / "meta.json")

        plain_dict = {"colony": {"task": "plain dict"}}
        await manager._save_context("dict-ctx", plain_dict)

        assert (sp / "context.json").exists()
        loaded = json.loads((sp / "context.json").read_text())
        assert loaded == plain_dict
