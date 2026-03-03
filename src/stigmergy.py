"""
FormicOS v0.6.0 -- Stigmergy: Shared Workspace & File Watcher

Per-colony filesystem workspace where agents produce artifacts.  Monitored for
real-time file index updates via watchdog (optional dependency).  Optionally
git-managed for round-level commit/rollback.

Key patterns:
- All git operations use asyncio.to_thread() (blocking subprocess)
- Git failure is non-fatal: _git_enabled flips to False, warning logged
- Sandbox enforcement: resolved symlinks must stay within workspace root
- File watcher debounces rapid changes (100ms window)
- Watchdog is an optional dependency -- graceful degradation when absent
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("formicos.stigmergy")

# ── Optional watchdog import ──────────────────────────────────────────────

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = None  # type: ignore[assignment, misc]
    FileSystemEventHandler = object  # type: ignore[assignment, misc]

# ── Sandbox Helpers ───────────────────────────────────────────────────────


class SandboxViolationError(Exception):
    """Raised when a path escapes the workspace root after symlink resolution."""


def _resolve_and_validate(path: str | Path, workspace_root: Path) -> Path:
    """
    Resolve *path* (following symlinks) and verify it lives under
    *workspace_root*.  Returns the resolved Path.

    Raises SandboxViolationError if the resolved path escapes the workspace.
    """
    resolved = Path(path).resolve()
    root_resolved = workspace_root.resolve()
    # Use os.path for reliable prefix check on all platforms
    if not str(resolved).startswith(str(root_resolved) + os.sep) and resolved != root_resolved:
        raise SandboxViolationError(
            f"Path {path!r} resolves to {resolved}, which is outside "
            f"workspace root {root_resolved}"
        )
    return resolved


# ═════════════════════════════════════════════════════════════════════════
# SharedWorkspaceManager
# ═════════════════════════════════════════════════════════════════════════


class SharedWorkspaceManager:
    """
    Per-colony workspace directory with optional git version control.

    Public interface:
        .init_workspace(task_branch?)       -> None
        .round_commit(round_num, message)   -> commit_hash | None
        .rollback_to_round(round_num)       -> None
        .get_diff_since_round(round_num)    -> str
        .file_hash(path)                    -> str (SHA-256, first 16 chars)
    """

    def __init__(self, workspace_root: str | Path) -> None:
        self._root = Path(workspace_root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._git_enabled: bool = False

    # ── Properties ────────────────────────────────────────────────────

    @property
    def root(self) -> Path:
        return self._root

    @property
    def git_enabled(self) -> bool:
        return self._git_enabled

    # ── Init ──────────────────────────────────────────────────────────

    async def init_workspace(self, task_branch: str | None = None) -> None:
        """
        Initialize the workspace directory.  If git is available,
        initializes a git repo and optionally creates a task branch.

        Git failures set _git_enabled = False and log a warning.
        """
        self._root.mkdir(parents=True, exist_ok=True)

        try:
            await self._run_git("init")
            # Configure git user for commits (required in fresh repos)
            await self._run_git("config", "user.email", "formicos@colony.local")
            await self._run_git("config", "user.name", "FormicOS")
            self._git_enabled = True
            logger.info("Git initialized in workspace: %s", self._root)

            if task_branch:
                # Create an initial commit so we can branch
                await self._ensure_initial_commit()
                await self._run_git("checkout", "-b", task_branch)
                logger.info("Checked out task branch: %s", task_branch)

        except (FileNotFoundError, subprocess.SubprocessError, OSError) as exc:
            self._git_enabled = False
            logger.warning(
                "Git init failed, continuing without version control: %s", exc
            )

    # ── Round Commit ──────────────────────────────────────────────────

    async def round_commit(
        self, round_num: int, message: str
    ) -> str | None:
        """
        Stage all changes and commit with a round-tagged message.

        Returns the commit hash (short), or None if git is disabled or
        there are no changes to commit.
        """
        if not self._git_enabled:
            return None

        try:
            await self._run_git("add", "-A")

            # Check if there's anything to commit
            result = await self._run_git(
                "diff", "--cached", "--quiet", check=False
            )
            if result.returncode == 0:
                # No staged changes
                logger.debug("Round %d: no changes to commit", round_num)
                return None

            full_message = f"Round {round_num}: {message}"
            await self._run_git("commit", "-m", full_message)

            # Get the commit hash
            hash_result = await self._run_git(
                "rev-parse", "--short", "HEAD"
            )
            commit_hash = hash_result.stdout.strip()
            logger.info(
                "Round %d committed: %s (%s)", round_num, commit_hash, message
            )
            return commit_hash

        except subprocess.SubprocessError as exc:
            logger.warning("round_commit failed for round %d: %s", round_num, exc)
            return None

    # ── Rollback ──────────────────────────────────────────────────────

    async def rollback_to_round(self, round_num: int) -> None:
        """
        Roll back the workspace to the state at the end of *round_num*.

        Finds the commit whose message starts with ``Round {round_num}:``
        and does a hard reset to that commit.
        """
        if not self._git_enabled:
            logger.warning("rollback_to_round called but git is disabled")
            return

        commit_hash = await self._find_round_commit(round_num)
        if commit_hash is None:
            raise ValueError(
                f"No commit found for round {round_num}"
            )

        await self._run_git("reset", "--hard", commit_hash)
        logger.info("Rolled back to round %d (commit %s)", round_num, commit_hash)

    # ── Diff ──────────────────────────────────────────────────────────

    async def get_diff_since_round(self, round_num: int) -> str:
        """
        Return a unified diff of all changes since the end of *round_num*.
        """
        if not self._git_enabled:
            return ""

        commit_hash = await self._find_round_commit(round_num)
        if commit_hash is None:
            return ""

        result = await self._run_git("diff", f"{commit_hash}..HEAD")
        return result.stdout

    # ── File Hash ─────────────────────────────────────────────────────

    async def file_hash(self, path: str | Path) -> str:
        """
        Compute SHA-256 of a file's content.  Returns first 16 hex chars.

        Raises FileNotFoundError if the file does not exist.
        Retries once after 100ms on IOError (file being written).
        """
        full_path = self._root / path
        _resolve_and_validate(full_path, self._root)

        return await asyncio.to_thread(self._file_hash_sync, full_path)

    # ── Sandbox Validation ────────────────────────────────────────────

    def validate_path(self, path: str | Path) -> Path:
        """
        Validate that *path* is within the workspace sandbox.

        Returns the resolved absolute path.
        Raises SandboxViolationError on escape attempt.
        """
        full_path = self._root / path
        return _resolve_and_validate(full_path, self._root)

    # ── File Operations (for workspace browser) ─────────────────────

    async def list_files(self, subpath: str = "") -> list[dict[str, Any]]:
        """List files/dirs in workspace, excluding .git. Sandbox-validated."""
        target = self._root / subpath if subpath else self._root
        _resolve_and_validate(target, self._root)

        entries: list[dict[str, Any]] = []

        def _scan() -> None:
            if not target.exists() or not target.is_dir():
                return
            for item in sorted(target.iterdir()):
                if item.name == ".git":
                    continue
                rel = item.relative_to(self._root)
                stat = item.stat()
                entries.append({
                    "name": item.name,
                    "path": str(rel).replace("\\", "/"),
                    "is_dir": item.is_dir(),
                    "size": stat.st_size if item.is_file() else 0,
                    "modified": stat.st_mtime,
                })

        await asyncio.to_thread(_scan)
        return entries

    async def read_file(self, path: str) -> str:
        """Read a text file from the workspace. Sandbox-validated."""
        full = self._root / path
        _resolve_and_validate(full, self._root)
        if not full.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if not full.is_file():
            raise ValueError(f"Not a file: {path}")
        return await asyncio.to_thread(full.read_text, "utf-8", "replace")

    async def write_file(self, path: str, content: bytes) -> int:
        """Write a file to the workspace (for uploads). Sandbox-validated. Returns bytes written."""
        full = self._root / path
        _resolve_and_validate(full, self._root)
        full.parent.mkdir(parents=True, exist_ok=True)

        def _write() -> int:
            full.write_bytes(content)
            return len(content)

        return await asyncio.to_thread(_write)

    # ── Private Helpers ───────────────────────────────────────────────

    async def _run_git(
        self, *args: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        """
        Run a git command in the workspace directory via asyncio.to_thread().

        Returns the CompletedProcess result.  Raises SubprocessError on
        non-zero exit when check=True.
        """
        cmd = ["git", "-C", str(self._root), *args]

        def _run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=check,
                timeout=30,
            )

        return await asyncio.to_thread(_run)

    async def _find_round_commit(self, round_num: int) -> str | None:
        """Find the commit hash for a given round number."""
        try:
            result = await self._run_git(
                "log", "--all", "--oneline", f"--grep=Round {round_num}:"
            )
            lines = result.stdout.strip().splitlines()
            if not lines:
                return None
            # Return the most recent matching commit (first line)
            return lines[0].split()[0]
        except subprocess.SubprocessError:
            return None

    async def _ensure_initial_commit(self) -> None:
        """Create an initial empty commit if the repo has no commits yet."""
        try:
            await self._run_git("rev-parse", "HEAD")
        except subprocess.SubprocessError:
            # No commits yet — create an empty initial commit
            await self._run_git(
                "commit", "--allow-empty", "-m", "Initial commit"
            )

    @staticmethod
    def _file_hash_sync(full_path: Path) -> str:
        """Synchronous SHA-256 hash — called via asyncio.to_thread()."""
        for attempt in range(2):
            try:
                data = full_path.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                return digest[:16]
            except FileNotFoundError:
                raise
            except IOError:
                if attempt == 0:
                    time.sleep(0.1)  # Retry once after 100ms
                else:
                    raise


# ═════════════════════════════════════════════════════════════════════════
# StigmergyWatcher
# ═════════════════════════════════════════════════════════════════════════


class StigmergyWatcher:
    """
    Watchdog-based filesystem observer that keeps the Context Tree's
    ``project.file_index`` in sync with the workspace.

    On file create/modify/delete, updates the index with:
        { filename: { "hash": str, "timestamp": float } }

    Debounces rapid changes with a 100ms window.  Requires watchdog;
    logs a warning and becomes a no-op if watchdog is not installed.
    """

    def __init__(
        self,
        workspace_path: str | Path,
        context_tree: Any,
    ) -> None:
        self._workspace = Path(workspace_path)
        self._ctx = context_tree
        self._observer: Any | None = None
        self._running = False

        # Debounce state
        self._pending_events: dict[str, float] = {}
        self._debounce_lock = threading.Lock()
        self._debounce_timer: threading.Timer | None = None

    # ── Public Interface ──────────────────────────────────────────────

    def start(self) -> None:
        """
        Start watching the workspace directory for changes.

        If watchdog is not installed, logs a warning and returns.
        If already running, does nothing.
        """
        if not WATCHDOG_AVAILABLE:
            logger.warning(
                "watchdog not installed — StigmergyWatcher disabled. "
                "Install with: pip install watchdog"
            )
            return

        if self._running:
            logger.debug("StigmergyWatcher already running")
            return

        try:
            handler = _DebouncedHandler(self)
            self._observer = Observer()
            self._observer.schedule(handler, str(self._workspace), recursive=True)
            self._observer.daemon = True
            self._observer.start()
            self._running = True
            logger.info("StigmergyWatcher started on %s", self._workspace)
        except Exception as exc:
            logger.warning("StigmergyWatcher failed to start: %s", exc)
            self._running = False

    def stop(self) -> None:
        """Stop the filesystem observer."""
        if self._observer is not None and self._running:
            try:
                self._observer.stop()
                self._observer.join(timeout=5)
            except Exception as exc:
                logger.warning("Error stopping StigmergyWatcher: %s", exc)
            finally:
                self._observer = None
                self._running = False
                # Cancel any pending debounce timer
                if self._debounce_timer is not None:
                    self._debounce_timer.cancel()
                    self._debounce_timer = None
                logger.info("StigmergyWatcher stopped")

    @property
    def running(self) -> bool:
        return self._running

    # ── Internal: Debounced Update ────────────────────────────────────

    def _schedule_update(self, file_path: str, event_type: str) -> None:
        """
        Record a pending file event and schedule a debounced flush.

        Called from the watchdog handler thread.
        """
        with self._debounce_lock:
            self._pending_events[file_path] = time.time()

            # Reset debounce timer
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()

            self._debounce_timer = threading.Timer(
                0.1,  # 100ms debounce
                self._flush_pending,
            )
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    def _flush_pending(self) -> None:
        """
        Process all pending file events: compute hashes and update the
        context tree.  Runs on the debounce timer thread.
        """
        with self._debounce_lock:
            pending = dict(self._pending_events)
            self._pending_events.clear()
            self._debounce_timer = None

        if not pending:
            return

        # Get current file index from context tree
        current_index: dict[str, dict[str, Any]] = dict(
            self._ctx.get("project", "file_index", {}) or {}
        )

        for file_path_str, ts in pending.items():
            file_path = Path(file_path_str)

            # Skip .git directory
            try:
                rel = file_path.relative_to(self._workspace)
                if rel.parts and rel.parts[0] == ".git":
                    continue
            except ValueError:
                continue

            rel_str = str(rel)

            if file_path.exists() and file_path.is_file():
                # File created or modified
                try:
                    data = file_path.read_bytes()
                    file_hash = hashlib.sha256(data).hexdigest()[:16]
                    current_index[rel_str] = {
                        "hash": file_hash,
                        "timestamp": ts,
                    }
                except (IOError, OSError) as exc:
                    # File may be in the middle of being written; retry once
                    try:
                        time.sleep(0.1)
                        data = file_path.read_bytes()
                        file_hash = hashlib.sha256(data).hexdigest()[:16]
                        current_index[rel_str] = {
                            "hash": file_hash,
                            "timestamp": ts,
                        }
                    except (IOError, OSError):
                        logger.warning(
                            "Failed to hash file %s: %s", file_path, exc
                        )
            else:
                # File deleted
                current_index.pop(rel_str, None)

        # Update context tree (schedule coroutine on the event loop)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self._ctx.set("project", "file_index", current_index),
                    loop,
                )
            else:
                # Fallback: direct set if no running loop (testing scenario)
                loop.run_until_complete(
                    self._ctx.set("project", "file_index", current_index)
                )
        except RuntimeError:
            # No event loop available — store directly for testability
            logger.debug("No event loop; storing file_index synchronously")
            # Context tree .get() is lockless, but .set() needs async.
            # As a fallback, write directly to the internal scope dict.
            self._ctx._scopes["project"]["file_index"] = current_index


# ── Watchdog Handler ──────────────────────────────────────────────────────


class _DebouncedHandler(FileSystemEventHandler):  # type: ignore[misc]
    """
    Watchdog event handler that delegates to StigmergyWatcher's debouncer.

    Filters out directory events and .git internals.
    """

    def __init__(self, watcher: StigmergyWatcher) -> None:
        super().__init__()
        self._watcher = watcher

    def on_created(self, event: Any) -> None:
        if not getattr(event, "is_directory", False):
            self._watcher._schedule_update(event.src_path, "created")

    def on_modified(self, event: Any) -> None:
        if not getattr(event, "is_directory", False):
            self._watcher._schedule_update(event.src_path, "modified")

    def on_deleted(self, event: Any) -> None:
        if not getattr(event, "is_directory", False):
            self._watcher._schedule_update(event.src_path, "deleted")

    def on_moved(self, event: Any) -> None:
        if not getattr(event, "is_directory", False):
            self._watcher._schedule_update(event.src_path, "deleted")
            if hasattr(event, "dest_path"):
                self._watcher._schedule_update(event.dest_path, "created")
