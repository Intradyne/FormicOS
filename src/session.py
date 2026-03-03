"""
FormicOS v0.6.0 -- Session Manager

Persistence layer for colony state. Handles autosave, crash recovery,
session lifecycle, and archival via atomic writes and PID-based lock files.

Key patterns:
- atomic_write_json: temp file + fsync + os.replace (never corrupts on crash)
- PID + hostname + timestamp lock files for cross-platform crash detection
- All blocking I/O wrapped in asyncio.to_thread()
- Backup rotation (keep last 3) for defense-in-depth recovery
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import os
import platform
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.models import PersistenceConfig

logger = logging.getLogger("formicos.session")

# ── Constants ─────────────────────────────────────────────────────────────

MAX_BACKUPS = 3

# How old a lock heartbeat can be before the lock is considered stale,
# even if the PID appears alive.  Safety net for PID reuse.
LOCK_TTL_SECONDS = 3600  # 1 hour

# How often the autosave loop refreshes the lock file timestamp.
# Must be significantly shorter than LOCK_TTL_SECONDS.
LOCK_HEARTBEAT_SECONDS = 60


# ── Data Models ───────────────────────────────────────────────────────────


class SessionInfo(BaseModel):
    """Metadata about a persisted session, returned by list_sessions()."""

    session_id: str
    task: str
    status: str  # "running" | "completed" | "failed" | "crashed"
    round: int = 0
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    file_size: int = 0


class LockStatus:
    """Enumeration of possible session lock states."""

    UNLOCKED = "unlocked"         # No lock file exists -- safe to start
    ACTIVE = "active"             # Lock holder is alive -- refuse to start
    STALE_CRASHED = "crashed"     # Lock holder is dead -- recovery needed
    STALE_EXPIRED = "expired"     # Lock TTL exceeded -- recovery needed
    CORRUPT = "corrupt"           # Lock file unreadable -- recovery needed


class SessionConflictError(Exception):
    """Raised when another instance owns the session."""

    pass


# ── Atomic File Operations ────────────────────────────────────────────────


def _fsync_directory(dir_path: Path) -> None:
    """
    Sync directory metadata to disk.  Ensures the rename is durable.

    On Linux: opens the directory fd and calls fsync.
    On Windows: no-op (NTFS journals directory metadata automatically).
    """
    if os.name == "nt":
        return
    fd = os.open(str(dir_path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_json(data: dict, target: Path) -> None:
    """
    Write JSON to disk with crash-safety guarantees.

    Protocol:
    1. Write to a temp file in the same directory as target
    2. fsync the temp file (ensures bytes are on disk, not in OS cache)
    3. Atomically replace target with temp file

    After this function returns, the data is guaranteed to be on disk.
    If the process crashes at ANY point during this function, the previous
    version of target remains intact (or target doesn't exist yet).
    """
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file in the SAME directory
    # (same directory guarantees same filesystem -> atomic replace)
    fd, tmp_path = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.stem}_",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())

        # Atomic replace
        os.replace(tmp_path, target)

        # Belt-and-suspenders: fsync the directory entry
        _fsync_directory(target.parent)

    except BaseException:
        # Clean up temp file on ANY failure (including KeyboardInterrupt)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _load_json(path: Path) -> dict:
    """Synchronous JSON load -- called via asyncio.to_thread()."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Backup Rotation ──────────────────────────────────────────────────────


def _rotate_backups(target: Path) -> None:
    """
    Rotate context.json -> context.json.1 -> context.json.2 -> ...

    Call BEFORE atomic_write_json so the current file becomes backup .1.
    """
    # Shift existing backups: .3 -> deleted, .2 -> .3, .1 -> .2
    for i in range(MAX_BACKUPS, 0, -1):
        src = target.parent / f"{target.name}.{i}"
        if i == MAX_BACKUPS:
            src.unlink(missing_ok=True)
        else:
            dst = target.parent / f"{target.name}.{i + 1}"
            if src.exists():
                shutil.move(str(src), str(dst))

    # Current file -> .1
    if target.exists():
        shutil.copy2(str(target), str(target.parent / f"{target.name}.1"))


# ── PID Liveness Checks ──────────────────────────────────────────────────


def _is_pid_alive(pid: int) -> bool:
    """
    Cross-platform PID liveness check.

    Linux/macOS: os.kill(pid, 0) succeeds if process exists.
    Windows: OpenProcess with PROCESS_QUERY_LIMITED_INFORMATION.
    """
    if platform.system() == "Windows":
        return _is_pid_alive_windows(pid)
    else:
        return _is_pid_alive_unix(pid)


def _is_pid_alive_unix(pid: int) -> bool:
    """
    Send signal 0 to the PID.  This doesn't actually send a signal --
    it just checks if the process exists and we have permission to signal it.
    """
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we can't signal it
        return True
    except OSError:
        return False


def _is_pid_alive_windows(pid: int) -> bool:
    """
    Use ctypes to call OpenProcess.  Avoids requiring pywin32.

    PROCESS_QUERY_LIMITED_INFORMATION (0x1000) is the least-privilege
    access right that still confirms process existence.
    """
    import ctypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if handle:
        kernel32.CloseHandle(handle)
        return True
    return False


# ── Lock File Operations ─────────────────────────────────────────────────


def write_lock_file(lock_path: Path) -> None:
    """
    Create or overwrite the session lock file.

    The lock file is NOT written atomically because its corruption
    is not catastrophic -- a corrupt lock file is treated as "stale"
    and the session is recoverable.  The context.json file is what
    must never corrupt.
    """
    lock_data = {
        "pid": os.getpid(),
        "hostname": platform.node(),
        "created_at": time.time(),
        "heartbeat_at": time.time(),
        "python_version": platform.python_version(),
        "platform": platform.system(),
    }
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w", encoding="utf-8") as f:
        json.dump(lock_data, f, indent=2)


def refresh_lock_heartbeat(lock_path: Path) -> None:
    """
    Update the heartbeat timestamp in the lock file.
    Called periodically by the autosave loop.
    """
    if not lock_path.exists():
        write_lock_file(lock_path)
        return
    try:
        with open(lock_path, encoding="utf-8") as f:
            data = json.load(f)
        data["heartbeat_at"] = time.time()
        with open(lock_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except (json.JSONDecodeError, OSError):
        # Lock file is corrupt -- rewrite it entirely
        write_lock_file(lock_path)


def remove_lock_file(lock_path: Path) -> None:
    """Remove on clean shutdown.  Ignore errors (file may already be gone)."""
    try:
        lock_path.unlink()
    except OSError:
        pass


def check_lock(lock_path: Path) -> tuple[str, dict | None]:
    """
    Determine the session lock status.

    Returns:
        (status: str, lock_data: dict | None)

    Decision tree:
    1. No lock file -> UNLOCKED
    2. Lock file unreadable -> CORRUPT (treat as stale)
    3. Different hostname -> ACTIVE (we can't check remote PIDs)
    4. PID alive AND heartbeat fresh -> ACTIVE
    5. PID alive BUT heartbeat expired -> STALE_EXPIRED
    6. PID dead -> STALE_CRASHED
    7. Heartbeat expired AND PID dead -> STALE_EXPIRED
    """
    if not lock_path.exists():
        return LockStatus.UNLOCKED, None

    # Parse lock file
    try:
        with open(lock_path, encoding="utf-8") as f:
            data = json.load(f)
        pid = data["pid"]
        hostname = data["hostname"]
        heartbeat = data["heartbeat_at"]
    except (json.JSONDecodeError, KeyError, OSError):
        return LockStatus.CORRUPT, None

    now = time.time()
    heartbeat_age = now - heartbeat
    is_same_host = hostname == platform.node()
    is_expired = heartbeat_age > LOCK_TTL_SECONDS

    # Different host: cannot check PID -- assume active unless expired
    if not is_same_host:
        if is_expired:
            return LockStatus.STALE_EXPIRED, data
        return LockStatus.ACTIVE, data

    # Same host: check if PID is alive
    pid_alive = _is_pid_alive(pid)

    if pid_alive and not is_expired:
        return LockStatus.ACTIVE, data
    elif pid_alive and is_expired:
        # Process exists but hasn't heartbeated -- likely hung
        return LockStatus.STALE_EXPIRED, data
    else:
        return LockStatus.STALE_CRASHED, data


# ── Session Manager ──────────────────────────────────────────────────────


class SessionManager:
    """
    Manages autosave lifecycle, crash detection, session CRUD, and archival.

    Responsibilities:
    - Periodic autosave on a configurable interval
    - Atomic writes (never corrupts the session file)
    - Dirty checking (skips saves when nothing changed)
    - Lock file management with heartbeat refresh
    - Backup rotation (keep last 3)
    - Session listing, deletion, recovery, and archival
    """

    def __init__(
        self,
        session_dir: Path | str,
        config: PersistenceConfig | None = None,
        autosave_interval: float | None = None,
    ) -> None:
        self.session_dir = Path(session_dir)
        self._config = config or PersistenceConfig()

        # Explicit interval overrides config
        if autosave_interval is not None:
            self.autosave_interval = autosave_interval
        else:
            self.autosave_interval = float(
                self._config.autosave_interval_seconds
            )

        self._autosave_task: asyncio.Task | None = None
        self._active_session_id: str | None = None
        self._active_ctx: Any = None  # AsyncContextTree reference
        self._started = False

    # ── Session Lifecycle ─────────────────────────────────────────────

    async def start_session(
        self,
        session_id: str,
        context_tree: Any,
        task: str,
    ) -> None:
        """
        Begin a new session: write lock file, save initial state, start autosave.

        Args:
            session_id: Unique identifier for this session.
            context_tree: The AsyncContextTree to persist.
            task: Human-readable description of the colony's task.
        """
        session_path = self.session_dir / session_id
        session_path.mkdir(parents=True, exist_ok=True)

        self._active_session_id = session_id
        self._active_ctx = context_tree

        # Write lock file
        lock_path = session_path / "session.lock"
        await asyncio.to_thread(write_lock_file, lock_path)

        # Write initial metadata
        meta = {
            "session_id": session_id,
            "task": task,
            "status": "running",
            "round": 0,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        meta_path = session_path / "meta.json"
        await asyncio.to_thread(atomic_write_json, meta, meta_path)

        # Initial save of context tree
        await self._save_context(session_id, context_tree)

        # Start autosave loop
        await self.start_autosave(session_id, context_tree)

        logger.info(
            f"Session '{session_id}' started. "
            f"Autosave every {self.autosave_interval}s"
        )

    async def end_session(
        self,
        session_id: str,
        context_tree: Any,
        status: str = "completed",
    ) -> SessionInfo:
        """
        End a session: final save, remove lock, update metadata.

        Returns:
            SessionInfo with final metadata.
        """
        session_path = self.session_dir / session_id

        # Stop autosave first
        await self.stop_autosave()

        # Final save
        await self._save_context(session_id, context_tree)

        # Update metadata
        meta_path = session_path / "meta.json"
        meta = await asyncio.to_thread(_load_json, meta_path)
        meta["status"] = status
        meta["updated_at"] = time.time()
        await asyncio.to_thread(atomic_write_json, meta, meta_path)

        # Remove lock file
        lock_path = session_path / "session.lock"
        await asyncio.to_thread(remove_lock_file, lock_path)

        self._active_session_id = None
        self._active_ctx = None

        context_path = session_path / "context.json"
        file_size = 0
        if context_path.exists():
            file_size = context_path.stat().st_size

        logger.info(f"Session '{session_id}' ended with status '{status}'.")

        return SessionInfo(
            session_id=meta["session_id"],
            task=meta.get("task", ""),
            status=meta["status"],
            round=meta.get("round", 0),
            created_at=meta.get("created_at", 0.0),
            updated_at=meta["updated_at"],
            file_size=file_size,
        )

    # ── Autosave ──────────────────────────────────────────────────────

    async def start_autosave(
        self,
        session_id: str,
        context_tree: Any,
    ) -> None:
        """Begin the autosave loop.  Call once at session start."""
        self._active_session_id = session_id
        self._active_ctx = context_tree
        self._started = True

        if self._autosave_task is not None:
            self._autosave_task.cancel()
            try:
                await self._autosave_task
            except asyncio.CancelledError:
                pass

        self._autosave_task = asyncio.create_task(
            self._autosave_loop(), name="session-autosave"
        )
        logger.info(
            f"Autosave started for session '{session_id}' "
            f"(interval={self.autosave_interval}s)"
        )

    async def stop_autosave(self) -> None:
        """Cancel the autosave loop and perform a final save."""
        if self._autosave_task is not None:
            self._autosave_task.cancel()
            try:
                await self._autosave_task
            except asyncio.CancelledError:
                pass
            self._autosave_task = None

        # Final save
        if self._active_session_id and self._active_ctx:
            try:
                await self._save_context(
                    self._active_session_id, self._active_ctx
                )
            except Exception:
                logger.exception("Final save on autosave stop failed")

        self._started = False
        logger.info("Autosave stopped.")

    async def _autosave_loop(self) -> None:
        """Runs as a background task.  Saves periodically if dirty."""
        while True:
            await asyncio.sleep(self.autosave_interval)
            try:
                if self._active_session_id and self._active_ctx:
                    await self._save_context(
                        self._active_session_id, self._active_ctx
                    )
                    # Refresh lock heartbeat
                    lock_path = (
                        self.session_dir
                        / self._active_session_id
                        / "session.lock"
                    )
                    await asyncio.to_thread(
                        refresh_lock_heartbeat, lock_path
                    )
            except Exception:
                logger.exception(
                    "Autosave/heartbeat failed -- will retry next interval"
                )

    async def _save_context(
        self,
        session_id: str,
        context_tree: Any,
    ) -> None:
        """
        Save context tree to disk with backup rotation.

        Uses snapshot() if the context tree supports it (AsyncContextTree),
        otherwise falls back to to_dict() or direct dict serialization.
        """
        session_path = self.session_dir / session_id
        context_path = session_path / "context.json"

        # Get serializable snapshot
        if hasattr(context_tree, "snapshot"):
            data = await context_tree.snapshot()
        elif hasattr(context_tree, "to_dict"):
            data = await context_tree.to_dict()
        elif isinstance(context_tree, dict):
            data = context_tree
        else:
            data = {"_raw": str(context_tree)}

        # Rotate backups, then write atomically -- both are blocking I/O
        await asyncio.to_thread(self._save_sync, data, context_path)

        # Update metadata round/timestamp
        meta_path = session_path / "meta.json"
        if meta_path.exists():
            try:
                meta = await asyncio.to_thread(_load_json, meta_path)
                meta["updated_at"] = time.time()
                if isinstance(data, dict):
                    # Try to extract round from context tree data
                    colony = data.get("colony", {})
                    if isinstance(colony, dict):
                        round_node = colony.get("round")
                        if isinstance(round_node, dict):
                            meta["round"] = round_node.get("value", 0)
                        elif isinstance(round_node, (int, float)):
                            meta["round"] = int(round_node)
                await asyncio.to_thread(atomic_write_json, meta, meta_path)
            except Exception:
                logger.debug("Failed to update session metadata", exc_info=True)

    @staticmethod
    def _save_sync(data: dict, context_path: Path) -> None:
        """Synchronous save: rotate backups then atomic write."""
        _rotate_backups(context_path)
        atomic_write_json(data, context_path)

    # ── Session Listing ───────────────────────────────────────────────

    async def list_sessions(self) -> list[SessionInfo]:
        """
        List all sessions in the session directory.

        Returns:
            List of SessionInfo objects sorted by updated_at descending.
        """
        return await asyncio.to_thread(self._list_sessions_sync)

    def _list_sessions_sync(self) -> list[SessionInfo]:
        """Synchronous session listing."""
        sessions: list[SessionInfo] = []

        if not self.session_dir.exists():
            return sessions

        for entry in self.session_dir.iterdir():
            if not entry.is_dir():
                continue

            meta_path = entry / "meta.json"
            if not meta_path.exists():
                continue

            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)

                context_path = entry / "context.json"
                file_size = (
                    context_path.stat().st_size if context_path.exists() else 0
                )

                sessions.append(
                    SessionInfo(
                        session_id=meta.get("session_id", entry.name),
                        task=meta.get("task", ""),
                        status=meta.get("status", "unknown"),
                        round=meta.get("round", 0),
                        created_at=meta.get("created_at", 0.0),
                        updated_at=meta.get("updated_at", 0.0),
                        file_size=file_size,
                    )
                )
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Skipping corrupt session dir {entry.name}: {e}")

        # Sort by updated_at descending
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    # ── Session Deletion ──────────────────────────────────────────────

    async def delete_session(self, session_id: str) -> None:
        """
        Delete a session directory and all its contents.

        Raises:
            FileNotFoundError: If the session does not exist.
        """
        session_path = self.session_dir / session_id
        if not session_path.exists():
            raise FileNotFoundError(f"Session '{session_id}' not found")

        # If deleting the active session, stop autosave first
        if session_id == self._active_session_id:
            await self.stop_autosave()
            self._active_session_id = None
            self._active_ctx = None

        await asyncio.to_thread(shutil.rmtree, str(session_path))
        logger.info(f"Session '{session_id}' deleted.")

    # ── Crash Detection ───────────────────────────────────────────────

    async def detect_crashed_sessions(self) -> list[str]:
        """
        Scan for sessions with stale lock files whose PID no longer exists.

        Returns:
            List of session_ids that appear to have crashed.
        """
        return await asyncio.to_thread(self._detect_crashed_sync)

    def _detect_crashed_sync(self) -> list[str]:
        """Synchronous crash detection scan."""
        crashed: list[str] = []

        if not self.session_dir.exists():
            return crashed

        for entry in self.session_dir.iterdir():
            if not entry.is_dir():
                continue

            lock_path = entry / "session.lock"
            status, _ = check_lock(lock_path)

            if status in (
                LockStatus.STALE_CRASHED,
                LockStatus.STALE_EXPIRED,
                LockStatus.CORRUPT,
            ):
                crashed.append(entry.name)

        return crashed

    # ── Session Recovery ──────────────────────────────────────────────

    async def recover_session(self, session_id: str) -> dict:
        """
        Recover a session's context tree from disk, falling back to backups.

        Removes the stale lock file and updates session metadata to 'crashed'.

        Returns:
            The deserialized context tree dict (or empty dict if unrecoverable).

        Raises:
            FileNotFoundError: If the session directory does not exist.
        """
        session_path = self.session_dir / session_id
        if not session_path.exists():
            raise FileNotFoundError(f"Session '{session_id}' not found")

        # Remove stale lock
        lock_path = session_path / "session.lock"
        await asyncio.to_thread(remove_lock_file, lock_path)

        # Try primary then backups
        context_path = session_path / "context.json"
        candidates = [context_path] + [
            session_path / f"context.json.{i}"
            for i in range(1, MAX_BACKUPS + 1)
        ]

        for path in candidates:
            if not path.exists():
                continue
            try:
                data = await asyncio.to_thread(_load_json, path)
                if path != context_path:
                    logger.warning(
                        f"Primary context.json was corrupt for session "
                        f"'{session_id}'. Recovered from backup: {path.name}"
                    )
                # Update metadata to mark as crashed
                meta_path = session_path / "meta.json"
                if meta_path.exists():
                    try:
                        meta = await asyncio.to_thread(_load_json, meta_path)
                        meta["status"] = "crashed"
                        meta["updated_at"] = time.time()
                        await asyncio.to_thread(
                            atomic_write_json, meta, meta_path
                        )
                    except Exception:
                        logger.debug(
                            "Failed to update metadata during recovery",
                            exc_info=True,
                        )

                logger.info(f"Session '{session_id}' recovered from {path.name}")
                return data
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning(
                    f"Failed to load {path.name} for session "
                    f"'{session_id}': {e}"
                )
                continue

        logger.error(
            f"Session '{session_id}' is unrecoverable -- "
            f"all context files are corrupt or missing."
        )
        return {}

    # ── Session Archival ──────────────────────────────────────────────

    async def archive_session(self, session_id: str) -> Path:
        """
        Compress a session's context.json to gzip and move to archive directory.

        Returns:
            Path to the archived gzip file.

        Raises:
            FileNotFoundError: If the session or its context file does not exist.
        """
        session_path = self.session_dir / session_id
        context_path = session_path / "context.json"

        if not context_path.exists():
            raise FileNotFoundError(
                f"No context.json for session '{session_id}'"
            )

        archive_dir = self.session_dir / ".archive"
        return await asyncio.to_thread(
            self._archive_sync, session_id, context_path, archive_dir
        )

    @staticmethod
    def _archive_sync(
        session_id: str, context_path: Path, archive_dir: Path
    ) -> Path:
        """Synchronous archival: read, gzip, write."""
        archive_dir.mkdir(parents=True, exist_ok=True)

        archive_path = archive_dir / f"{session_id}.json.gz"
        with open(context_path, "rb") as f_in:
            with gzip.open(archive_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

        return archive_path

    # ── Cleanup ───────────────────────────────────────────────────────

    async def cleanup_old_sessions(self, max_age_days: int = 30) -> int:
        """
        Remove sessions older than max_age_days.

        Returns:
            Number of sessions removed.
        """
        return await asyncio.to_thread(
            self._cleanup_sync, max_age_days
        )

    def _cleanup_sync(self, max_age_days: int) -> int:
        """Synchronous cleanup of old sessions."""
        removed = 0
        cutoff = time.time() - (max_age_days * 86400)

        if not self.session_dir.exists():
            return removed

        for entry in self.session_dir.iterdir():
            if not entry.is_dir() or entry.name.startswith("."):
                continue

            meta_path = entry / "meta.json"
            if not meta_path.exists():
                continue

            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)
                updated = meta.get("updated_at", 0.0)
                if updated < cutoff:
                    shutil.rmtree(str(entry))
                    removed += 1
            except (json.JSONDecodeError, OSError):
                continue

        return removed


# ── Session Acquisition (Startup Sequence) ────────────────────────────────


async def acquire_session(
    session_dir: Path,
    session_id: str,
    config: PersistenceConfig | None = None,
) -> tuple[dict, SessionManager]:
    """
    Full session acquisition sequence.  Called at FormicOS startup.

    Checks the lock file, recovers from crash if needed, and returns
    the loaded context data with a SessionManager ready to autosave.

    Returns:
        (context_data: dict, manager: SessionManager)

    Raises:
        SessionConflictError: If another instance is actively using this session.
    """
    session_path = Path(session_dir) / session_id
    lock_path = session_path / "session.lock"

    status, lock_data = check_lock(lock_path)

    if status == LockStatus.ACTIVE:
        hostname = lock_data.get("hostname", "unknown") if lock_data else "unknown"
        pid = lock_data.get("pid", "unknown") if lock_data else "unknown"
        raise SessionConflictError(
            f"Session '{session_id}' is active on "
            f"{hostname} (PID {pid}). "
            f"Stop the other instance first, or delete {lock_path} "
            f"if you're sure it's stale."
        )

    if status in (
        LockStatus.STALE_CRASHED,
        LockStatus.STALE_EXPIRED,
        LockStatus.CORRUPT,
    ):
        logger.warning(
            f"Detected {status} session '{session_id}'. "
            f"Attempting recovery..."
        )
        await asyncio.to_thread(remove_lock_file, lock_path)

    # Load or recover context data
    context_data: dict = {}
    context_path = session_path / "context.json"
    candidates = [context_path] + [
        session_path / f"context.json.{i}" for i in range(1, MAX_BACKUPS + 1)
    ]

    for path in candidates:
        if not path.exists():
            continue
        try:
            context_data = await asyncio.to_thread(_load_json, path)
            if path != context_path:
                logger.warning(
                    f"Primary context.json corrupt. "
                    f"Recovered from backup: {path.name}"
                )
            break
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to load {path.name}: {e}")
            continue

    manager = SessionManager(session_dir, config)
    return context_data, manager
