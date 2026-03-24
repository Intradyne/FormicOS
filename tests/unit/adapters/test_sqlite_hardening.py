"""Tests for Wave 43 SQLite WAL hardening and cold-start profiling."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from formicos.adapters.store_sqlite import SqliteEventStore


@pytest.fixture
async def store(tmp_path: Path) -> SqliteEventStore:
    """Create a temporary SQLite store for testing."""
    db_path = tmp_path / "test_events.db"
    s = SqliteEventStore(db_path)
    # Force initialization
    await s._ensure_db()
    return s


class TestSqliteWALHardening:
    """Verify Wave 43 PRAGMA profile is applied."""

    @pytest.mark.asyncio
    async def test_journal_mode_wal(self, store: SqliteEventStore) -> None:
        db = await store._ensure_db()
        cursor = await db.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
        assert row[0] == "wal"  # pyright: ignore[reportIndexIssue]

    @pytest.mark.asyncio
    async def test_synchronous_normal(self, store: SqliteEventStore) -> None:
        db = await store._ensure_db()
        cursor = await db.execute("PRAGMA synchronous")
        row = await cursor.fetchone()
        # NORMAL = 1
        assert row[0] in (1, "normal")  # pyright: ignore[reportIndexIssue]

    @pytest.mark.asyncio
    async def test_busy_timeout_set(self, store: SqliteEventStore) -> None:
        db = await store._ensure_db()
        cursor = await db.execute("PRAGMA busy_timeout")
        row = await cursor.fetchone()
        assert row[0] == 15000  # pyright: ignore[reportIndexIssue]

    @pytest.mark.asyncio
    async def test_cache_size_set(self, store: SqliteEventStore) -> None:
        db = await store._ensure_db()
        cursor = await db.execute("PRAGMA cache_size")
        row = await cursor.fetchone()
        assert row[0] == -64000  # pyright: ignore[reportIndexIssue]

    @pytest.mark.asyncio
    async def test_wal_autocheckpoint_set(self, store: SqliteEventStore) -> None:
        db = await store._ensure_db()
        cursor = await db.execute("PRAGMA wal_autocheckpoint")
        row = await cursor.fetchone()
        assert row[0] == 1000  # pyright: ignore[reportIndexIssue]


class TestColdStartProfiling:
    """Verify cold-start measurement helpers."""

    @pytest.mark.asyncio
    async def test_event_count_empty(self, store: SqliteEventStore) -> None:
        count = await store.event_count()
        assert count == 0

    @pytest.mark.asyncio
    async def test_profile_replay_empty(self, store: SqliteEventStore) -> None:
        result = await store.profile_replay()
        assert result["total_events"] == 0.0
        assert "count_query_ms" in result
        assert "sample_100_read_ms" in result
        assert "estimated_full_replay_ms" in result

    @pytest.mark.asyncio
    async def test_profile_replay_returns_timing(self, store: SqliteEventStore) -> None:
        result = await store.profile_replay()
        # All timing values should be non-negative
        assert result["count_query_ms"] >= 0
        assert result["sample_100_read_ms"] >= 0


class TestStoreLifecycle:
    """Verify store opens and closes cleanly with new PRAGMAs."""

    @pytest.mark.asyncio
    async def test_open_close_cycle(self, tmp_path: Path) -> None:
        db_path = tmp_path / "lifecycle_test.db"
        store = SqliteEventStore(db_path)
        await store._ensure_db()
        await store.close()
        # Re-open should work
        await store._ensure_db()
        count = await store.event_count()
        assert count == 0
        await store.close()

    @pytest.mark.asyncio
    async def test_idempotent_ensure_db(self, store: SqliteEventStore) -> None:
        """Calling _ensure_db multiple times should be safe."""
        db1 = await store._ensure_db()
        db2 = await store._ensure_db()
        assert db1 is db2
