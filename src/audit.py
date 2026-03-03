"""
FormicOS v0.6.0 -- Audit Logger

Append-only JSONL log per session. Provides an immutable record of all colony
activity for debugging, compliance, and post-mortem analysis.

Key patterns:
- Buffered writes: flush at 100 entries or 5 seconds, whichever comes first
- Log rotation: 5 MB threshold, keep 3 rotated files
- Structured events via Pydantic model_dump() (never default=str)
- Disk write failure logs to stderr, never crashes the colony
- Async-safe: buffer flush runs via asyncio.to_thread()
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import sys
import time
import traceback as tb_module
from pathlib import Path
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger("formicos.audit")

# ── Constants ─────────────────────────────────────────────────────────────

BUFFER_FLUSH_SIZE = 100
BUFFER_FLUSH_INTERVAL_SECONDS = 5.0
ROTATION_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_ROTATED_FILES = 3


# ── Audit Event Schema ────────────────────────────────────────────────────


class AuditEntry(BaseModel):
    """A single audit log entry. Every entry follows this schema."""

    timestamp: float
    session_id: str
    event_type: str
    payload: dict[str, Any]


# ── Pydantic-safe Serialization ──────────────────────────────────────────


def _serialize_value(value: Any) -> Any:
    """
    Recursively serialize a value for JSON output.

    Uses Pydantic model_dump() for BaseModel instances instead of
    default=str, preserving type information for datetimes, enums, etc.
    """
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_value(item) for item in value]
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    # Enums
    if hasattr(value, "value"):
        return value.value
    # Last resort -- but we prefer explicit serialization
    return str(value)


# ── Log Rotation ──────────────────────────────────────────────────────────


def _rotate_audit_file(log_path: Path) -> None:
    """
    Rotate audit log when it exceeds ROTATION_SIZE_BYTES.

    Naming: session.audit.jsonl -> session.audit.1.jsonl -> .2.jsonl -> .3.jsonl
    Files beyond MAX_ROTATED_FILES are deleted.

    This is a synchronous function -- call via asyncio.to_thread().
    """
    if not log_path.exists():
        return

    if log_path.stat().st_size < ROTATION_SIZE_BYTES:
        return

    stem = log_path.stem  # e.g. "session.audit" from "session.audit.jsonl"
    parent = log_path.parent
    suffix = log_path.suffix  # ".jsonl"

    # Shift existing rotated files: .3 -> deleted, .2 -> .3, .1 -> .2
    for i in range(MAX_ROTATED_FILES, 0, -1):
        rotated = parent / f"{stem}.{i}{suffix}"
        if i == MAX_ROTATED_FILES:
            rotated.unlink(missing_ok=True)
        else:
            dst = parent / f"{stem}.{i + 1}{suffix}"
            if rotated.exists():
                shutil.move(str(rotated), str(dst))

    # Current file -> .1
    dst_1 = parent / f"{stem}.1{suffix}"
    shutil.move(str(log_path), str(dst_1))


# ── Audit Logger ──────────────────────────────────────────────────────────


class AuditLogger:
    """
    Buffered, rotation-aware JSONL audit logger.

    Usage:
        logger = AuditLogger(session_dir)
        logger.log_session_start(session_id, task, config)
        logger.log_round(session_id, round_num, phase, data)
        ...
        await logger.flush()
        await logger.close()

    The logger is async-safe: log methods append to an in-memory buffer
    synchronously (safe to call from any coroutine), while flush and
    close perform blocking I/O via asyncio.to_thread().
    """

    def __init__(self, session_dir: str | Path) -> None:
        self._session_dir = Path(session_dir)
        self._buffer: list[AuditEntry] = []
        self._flush_task: asyncio.Task[None] | None = None
        self._closed = False
        self._last_flush_time: float = time.time()

    # ── Log Path Helper ──────────────────────────────────────────────

    def _log_path(self, session_id: str) -> Path:
        """Return the JSONL log file path for a session."""
        session_path = self._session_dir / session_id
        session_path.mkdir(parents=True, exist_ok=True)
        return session_path / "audit.jsonl"

    # ── Buffer Management ────────────────────────────────────────────

    def _append(self, entry: AuditEntry) -> None:
        """
        Add an entry to the in-memory buffer.

        If the buffer reaches BUFFER_FLUSH_SIZE, schedule an immediate flush.
        Also starts the periodic flush timer if not already running.
        """
        if self._closed:
            logger.warning(
                "AuditLogger is closed; dropping event: %s", entry.event_type
            )
            return

        self._buffer.append(entry)

        # Start periodic flush timer on first entry
        if self._flush_task is None or self._flush_task.done():
            try:
                loop = asyncio.get_running_loop()
                self._flush_task = loop.create_task(
                    self._periodic_flush(), name="audit-flush-timer"
                )
            except RuntimeError:
                # No running event loop -- caller is not in async context.
                # Buffer will be flushed on next explicit flush() or close().
                pass

        # Immediate flush if buffer is full
        if len(self._buffer) >= BUFFER_FLUSH_SIZE:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.flush(), name="audit-flush-overflow")
            except RuntimeError:
                # No running loop -- do synchronous flush
                self._flush_sync()

    async def _periodic_flush(self) -> None:
        """Background task: flush buffer every BUFFER_FLUSH_INTERVAL_SECONDS."""
        try:
            while not self._closed:
                await asyncio.sleep(BUFFER_FLUSH_INTERVAL_SECONDS)
                if self._buffer:
                    await self.flush()
        except asyncio.CancelledError:
            pass

    # ── Public Log Methods ───────────────────────────────────────────

    def log_round(
        self,
        session_id: str,
        round_num: int,
        phase: str,
        data: Any,
    ) -> None:
        """Log an orchestration round event."""
        self._append(
            AuditEntry(
                timestamp=time.time(),
                session_id=session_id,
                event_type="round",
                payload={
                    "round_num": round_num,
                    "phase": phase,
                    "data": _serialize_value(data),
                },
            )
        )

    def log_decision(
        self,
        session_id: str,
        decision_type: str,
        detail: str,
    ) -> None:
        """Log a governance decision."""
        self._append(
            AuditEntry(
                timestamp=time.time(),
                session_id=session_id,
                event_type="decision",
                payload={
                    "decision_type": decision_type,
                    "detail": detail,
                },
            )
        )

    def log_agent_action(
        self,
        session_id: str,
        agent_id: str,
        action: str,
        detail: str,
    ) -> None:
        """Log an individual agent action."""
        self._append(
            AuditEntry(
                timestamp=time.time(),
                session_id=session_id,
                event_type="agent_action",
                payload={
                    "agent_id": agent_id,
                    "action": action,
                    "detail": detail,
                },
            )
        )

    def log_repl_event(
        self,
        session_id: str,
        event_name: str,
        detail: dict[str, Any],
    ) -> None:
        """Log a REPL execution event (formic_read_bytes, formic_subcall).

        Taxonomy: ``event_type="agent_action"`` with ``action="repl_execution"``.
        The ``event_name`` distinguishes the primitive (e.g. ``formic_read_bytes``,
        ``formic_subcall``, ``formic_subcall_complete``).
        """
        self._append(
            AuditEntry(
                timestamp=time.time(),
                session_id=session_id,
                event_type="agent_action",
                payload={
                    "action": "repl_execution",
                    "event": event_name,
                    **{k: _serialize_value(v) for k, v in detail.items()},
                },
            )
        )

    def log_error(
        self,
        session_id: str,
        error_type: str,
        message: str,
        traceback: str | None = None,
    ) -> None:
        """Log an error event, optionally including a traceback string."""
        payload: dict[str, Any] = {
            "error_type": error_type,
            "message": message,
        }
        if traceback is not None:
            payload["traceback"] = traceback
        self._append(
            AuditEntry(
                timestamp=time.time(),
                session_id=session_id,
                event_type="error",
                payload=payload,
            )
        )

    def log_session_start(
        self,
        session_id: str,
        task: str,
        config: Any,
    ) -> None:
        """Log session start with task description and colony config."""
        self._append(
            AuditEntry(
                timestamp=time.time(),
                session_id=session_id,
                event_type="session_start",
                payload={
                    "task": task,
                    "config": _serialize_value(config),
                },
            )
        )

    def log_session_end(
        self,
        session_id: str,
        status: str,
        outcome: str,
    ) -> None:
        """Log session completion with final status and outcome."""
        self._append(
            AuditEntry(
                timestamp=time.time(),
                session_id=session_id,
                event_type="session_end",
                payload={
                    "status": status,
                    "outcome": outcome,
                },
            )
        )

    # ── Flush / Close ────────────────────────────────────────────────

    async def flush(self) -> None:
        """
        Flush the in-memory buffer to disk.

        Groups entries by session_id so each session's JSONL file
        receives only its own entries. Performs log rotation check
        before writing.

        All blocking I/O runs in asyncio.to_thread().
        """
        if not self._buffer:
            return

        # Snapshot and clear buffer atomically (single-threaded swap)
        entries = self._buffer[:]
        self._buffer.clear()
        self._last_flush_time = time.time()

        # Group by session_id
        by_session: dict[str, list[AuditEntry]] = {}
        for entry in entries:
            by_session.setdefault(entry.session_id, []).append(entry)

        for session_id, session_entries in by_session.items():
            log_path = self._log_path(session_id)
            lines = [
                entry.model_dump_json() + "\n" for entry in session_entries
            ]
            try:
                await asyncio.to_thread(
                    self._write_lines_sync, log_path, lines
                )
            except Exception:
                # Spec: disk write failure logs to stderr, never crashes
                print(
                    f"[AuditLogger] Failed to flush {len(lines)} entries "
                    f"for session '{session_id}': "
                    f"{tb_module.format_exc()}",
                    file=sys.stderr,
                )

    def _flush_sync(self) -> None:
        """
        Synchronous flush -- used when no event loop is running.
        Same logic as flush() but without asyncio.
        """
        if not self._buffer:
            return

        entries = self._buffer[:]
        self._buffer.clear()
        self._last_flush_time = time.time()

        by_session: dict[str, list[AuditEntry]] = {}
        for entry in entries:
            by_session.setdefault(entry.session_id, []).append(entry)

        for session_id, session_entries in by_session.items():
            log_path = self._log_path(session_id)
            lines = [
                entry.model_dump_json() + "\n" for entry in session_entries
            ]
            try:
                self._write_lines_sync(log_path, lines)
            except Exception:
                print(
                    f"[AuditLogger] Failed to flush {len(lines)} entries "
                    f"for session '{session_id}': "
                    f"{tb_module.format_exc()}",
                    file=sys.stderr,
                )

    @staticmethod
    def _write_lines_sync(log_path: Path, lines: list[str]) -> None:
        """
        Write JSONL lines to disk with rotation check.

        Called via asyncio.to_thread() -- must be fully synchronous.
        """
        # Check rotation BEFORE writing
        _rotate_audit_file(log_path)

        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.writelines(lines)

    async def close(self) -> None:
        """
        Flush remaining buffer and stop the periodic flush timer.

        After close(), further log calls are silently dropped.
        """
        self._closed = True

        # Cancel periodic flush task
        if self._flush_task is not None and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None

        # Final flush
        await self.flush()
