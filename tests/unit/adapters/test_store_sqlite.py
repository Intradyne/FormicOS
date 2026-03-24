"""Unit tests for SqliteEventStore adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from formicos.adapters.store_sqlite import SqliteEventStore
from formicos.core.events import (
    ColonySpawned,
    ThreadCreated,
    WorkspaceCreated,
    WorkspaceConfigSnapshot,
)
from formicos.core.types import CasteSlot


def _make_workspace_event(address: str = "ws1", seq: int = 0) -> WorkspaceCreated:
    return WorkspaceCreated(
        seq=seq,
        timestamp=datetime.now(UTC),
        address=address,
        name="test-workspace",
        config=WorkspaceConfigSnapshot(
            budget=10.0,
            strategy="stigmergic",
        ),
    )


def _make_thread_event(address: str = "ws1/t1", seq: int = 0) -> ThreadCreated:
    return ThreadCreated(
        seq=seq,
        timestamp=datetime.now(UTC),
        address=address,
        workspace_id="ws1",
        name="test-thread",
    )


def _make_colony_event(address: str = "ws1/t1/c1", seq: int = 0) -> ColonySpawned:
    return ColonySpawned(
        seq=seq,
        timestamp=datetime.now(UTC),
        address=address,
        thread_id="t1",
        task="do stuff",
        castes=[CasteSlot(caste="coder")],
        model_assignments={"coder": "anthropic/claude"},
        strategy="stigmergic",
        max_rounds=3,
        budget_limit=5.0,
    )


async def _make_store(tmp_path: Path) -> SqliteEventStore:
    store = SqliteEventStore(tmp_path / "test.db")
    await store._ensure_db()
    return store


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


async def test_append_and_query_round_trip(tmp_path: Path) -> None:
    store = await _make_store(tmp_path)
    event = _make_workspace_event()
    seq = await store.append(event)
    assert seq >= 1

    results = await store.query(address="ws1")
    assert len(results) == 1
    assert results[0].type == "WorkspaceCreated"
    assert results[0].address == "ws1"  # pyright: ignore[reportUnknownMemberType]
    await store.close()


async def test_query_by_event_type(tmp_path: Path) -> None:
    store = await _make_store(tmp_path)
    await store.append(_make_workspace_event())
    await store.append(_make_thread_event())
    await store.append(_make_colony_event())

    results = await store.query(event_type="ThreadCreated")
    assert len(results) == 1
    assert results[0].type == "ThreadCreated"

    results = await store.query(event_type="ColonySpawned")
    assert len(results) == 1
    assert results[0].type == "ColonySpawned"
    await store.close()


async def test_query_address_prefix(tmp_path: Path) -> None:
    store = await _make_store(tmp_path)
    await store.append(_make_workspace_event(address="ws1"))
    await store.append(_make_thread_event(address="ws1/t1"))
    await store.append(_make_colony_event(address="ws1/t1/c1"))
    await store.append(_make_thread_event(address="ws2/t2"))

    # Prefix "ws1" should match ws1, ws1/t1, ws1/t1/c1
    results = await store.query(address="ws1")
    assert len(results) == 3

    # Prefix "ws1/t1" should match ws1/t1 and ws1/t1/c1
    results = await store.query(address="ws1/t1")
    assert len(results) == 2

    # Prefix "ws2" should match only ws2/t2
    results = await store.query(address="ws2")
    assert len(results) == 1
    await store.close()


async def test_replay_ordering(tmp_path: Path) -> None:
    store = await _make_store(tmp_path)
    s1 = await store.append(_make_workspace_event(address="a"))
    s2 = await store.append(_make_thread_event(address="b"))
    s3 = await store.append(_make_colony_event(address="c"))

    events = []
    async for e in store.replay(after_seq=0):
        events.append(e)

    assert len(events) == 3
    assert events[0].type == "WorkspaceCreated"
    assert events[1].type == "ThreadCreated"
    assert events[2].type == "ColonySpawned"
    await store.close()


async def test_replay_after_seq(tmp_path: Path) -> None:
    store = await _make_store(tmp_path)
    s1 = await store.append(_make_workspace_event())
    s2 = await store.append(_make_thread_event())
    s3 = await store.append(_make_colony_event())

    events = []
    async for e in store.replay(after_seq=s2):
        events.append(e)

    assert len(events) == 1
    assert events[0].type == "ColonySpawned"
    await store.close()


async def test_wal_mode(tmp_path: Path) -> None:
    store = await _make_store(tmp_path)
    db = await store._ensure_db()
    cursor = await db.execute("PRAGMA journal_mode")
    row = await cursor.fetchone()
    assert row is not None
    assert row[0] == "wal"
    await store.close()
