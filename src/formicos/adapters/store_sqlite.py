"""SQLite-backed event store adapter.

Implements ``EventStorePort`` via aiosqlite with WAL journaling.
Schema follows algorithms.md section 12.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

from formicos.core.events import FormicOSEvent, deserialize
from formicos.core.ports import EventTypeName

logger = structlog.get_logger(__name__)

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS events (
    seq       INTEGER PRIMARY KEY AUTOINCREMENT,
    type      TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    address   TEXT NOT NULL,
    payload   TEXT NOT NULL,
    trace_id  TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_address ON events(address, seq);
CREATE INDEX IF NOT EXISTS idx_events_type    ON events(type, seq);
CREATE INDEX IF NOT EXISTS idx_events_trace   ON events(trace_id) WHERE trace_id IS NOT NULL;
"""


class SqliteEventStore:
    """Append-only event store backed by a single SQLite file.

    Satisfies :class:`formicos.core.ports.EventStorePort` via structural
    subtyping (Protocol, no ABC).
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_db(self) -> aiosqlite.Connection:
        """Lazily open the connection and apply the schema.

        Wave 43: Fuller WAL-oriented PRAGMA profile for deployment safety.

        - journal_mode=WAL: concurrent reads during writes
        - synchronous=NORMAL: safe for WAL (fsync on checkpoint, not every commit)
        - busy_timeout=15000: wait up to 15s for locks instead of failing immediately
        - cache_size=-64000: 64MB page cache (negative = KiB)
        - wal_autocheckpoint=1000: checkpoint every 1000 pages (~4MB)

        Deployment rules (enforced by named volumes in docker-compose.yml):
        - .db, .db-wal, and .db-shm MUST reside on the same filesystem
        - Never bind-mount on macOS/Windows Docker Desktop (WAL relies on
          shared-memory semantics that don't survive cross-OS mounts)
        - FormicOS is a single-writer backend; do not point multiple
          processes at the same database file
        """
        if self._db is not None:
            return self._db

        logger.info("sqlite_store.opening", path=str(self._db_path))
        db = await aiosqlite.connect(str(self._db_path))
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("PRAGMA busy_timeout=15000")
        await db.execute("PRAGMA cache_size=-64000")
        await db.execute("PRAGMA wal_autocheckpoint=1000")
        await db.execute("PRAGMA mmap_size=268435456")
        await db.executescript(_SCHEMA_SQL)
        await db.commit()
        db.row_factory = aiosqlite.Row  # pyright: ignore[reportAttributeAccessIssue]
        self._db = db
        logger.info("sqlite_store.pragmas_applied",
                     journal_mode="WAL", synchronous="NORMAL",
                     busy_timeout=15000, cache_size=-64000,
                     wal_autocheckpoint=1000, mmap_size=268435456)
        return db

    # ------------------------------------------------------------------
    # EventStorePort interface
    # ------------------------------------------------------------------

    async def append(self, event: FormicOSEvent) -> int:
        """Persist *event* and return the assigned sequence number."""
        db = await self._ensure_db()

        payload = event.model_dump_json()
        # Extract envelope fields from the event model.
        data: dict[str, Any] = json.loads(payload)
        evt_type: str = data["type"]
        timestamp: str = data["timestamp"]
        address: str = data["address"]
        trace_id: str | None = data.get("trace_id")

        cursor = await db.execute(
            "INSERT INTO events (type, timestamp, address, payload, trace_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (evt_type, timestamp, address, payload, trace_id),
        )
        await db.commit()
        seq = cursor.lastrowid
        assert seq is not None  # noqa: S101 — SQLite always returns lastrowid on INSERT
        logger.debug("sqlite_store.appended", seq=seq, type=evt_type, address=address)
        return int(seq)

    async def query(
        self,
        address: str | None = None,
        event_type: EventTypeName | None = None,
        after_seq: int = 0,
        limit: int = 1000,
    ) -> list[FormicOSEvent]:
        """Return events matching optional filters, ordered by seq."""
        db = await self._ensure_db()

        clauses: list[str] = ["seq > ?"]
        params: list[Any] = [after_seq]

        if address is not None:
            clauses.append("address LIKE ? || '%'")
            params.append(address)

        if event_type is not None:
            clauses.append("type = ?")
            params.append(event_type)

        where = " AND ".join(clauses)
        sql = f"SELECT payload FROM events WHERE {where} ORDER BY seq LIMIT ?"  # noqa: S608
        params.append(limit)

        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()
        return [deserialize(row[0]) for row in rows]  # pyright: ignore[reportUnknownArgumentType]

    async def replay(self, after_seq: int = 0) -> AsyncIterator[FormicOSEvent]:
        """Yield events in sequence order starting after *after_seq*."""
        db = await self._ensure_db()
        cursor = await db.execute(
            "SELECT payload FROM events WHERE seq > ? ORDER BY seq",
            (after_seq,),
        )
        async for row in cursor:
            yield deserialize(row[0])  # pyright: ignore[reportUnknownArgumentType]

    # ------------------------------------------------------------------
    # Maintenance helpers
    # ------------------------------------------------------------------

    async def checkpoint(self) -> None:
        """Force a WAL checkpoint (TRUNCATE mode)."""
        db = await self._ensure_db()
        await db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        logger.info("sqlite_store.checkpoint_complete")

    async def event_count(self) -> int:
        """Return total number of stored events (for cold-start profiling)."""
        db = await self._ensure_db()
        cursor = await db.execute("SELECT COUNT(*) FROM events")
        row = await cursor.fetchone()
        return int(row[0]) if row else 0  # pyright: ignore[reportIndexIssue]

    async def profile_replay(self) -> dict[str, float]:
        """Measure cold-start replay performance.

        Wave 43: Returns timing and count data for operator visibility into
        replay cost. This is measurement, not optimization — snapshot or
        watermark machinery is only justified if these numbers warrant it.
        """
        import time
        db = await self._ensure_db()

        t0 = time.monotonic()
        cursor = await db.execute("SELECT COUNT(*) FROM events")
        row = await cursor.fetchone()
        total = int(row[0]) if row else 0  # pyright: ignore[reportIndexIssue]
        t_count = time.monotonic() - t0

        t0 = time.monotonic()
        cursor = await db.execute("SELECT payload FROM events ORDER BY seq LIMIT 100")
        rows = list(await cursor.fetchall())
        t_sample = time.monotonic() - t0

        result = {
            "total_events": float(total),
            "count_query_ms": round(t_count * 1000, 2),
            "sample_100_read_ms": round(t_sample * 1000, 2),
            "estimated_full_replay_ms": round(
                (t_sample / max(len(rows), 1)) * total * 1000, 2,
            ) if rows else 0.0,
        }
        logger.info("sqlite_store.replay_profile", **result)
        return result

    async def close(self) -> None:
        """Close the database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None
            logger.info("sqlite_store.closed")


__all__ = ["SqliteEventStore"]
