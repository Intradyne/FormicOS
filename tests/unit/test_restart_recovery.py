"""Restart recovery tests — verify event-sourced state survives store rebuild.

Tests that the SqliteEventStore can:
1. Persist events across close/reopen
2. Replay events to rebuild materialized state
3. Maintain event ordering and integrity
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from formicos.core.events import (
    ColonySpawned,
    RoundCompleted,
    RoundStarted,
    ThreadCreated,
    WorkspaceConfigSnapshot,
    WorkspaceCreated,
    deserialize,
    serialize,
)
from formicos.core.types import CasteSlot

NOW = datetime.now(UTC)
ADDR = "ws-1/th-1/col-1"
ENVELOPE = {"seq": 0, "timestamp": NOW, "address": ADDR}


def _make_config() -> WorkspaceConfigSnapshot:
    return WorkspaceConfigSnapshot(budget=10.0, strategy="stigmergic")


# ---------------------------------------------------------------------------
# Event serialization round-trip (restart prerequisite)
# ---------------------------------------------------------------------------


class TestEventPersistence:
    def test_workspace_created_survives_serialization(self) -> None:
        event = WorkspaceCreated(**ENVELOPE, name="research", config=_make_config())
        restored = deserialize(serialize(event))
        assert restored == event

    def test_colony_spawned_survives_serialization(self) -> None:
        event = ColonySpawned(
            **ENVELOPE, thread_id="th-1", task="build it",
            castes=[CasteSlot(caste="coder"), CasteSlot(caste="reviewer")],
            model_assignments={"coder": "m1", "reviewer": "m2"},
            strategy="stigmergic", max_rounds=5, budget_limit=2.0,
        )
        restored = deserialize(serialize(event))
        assert restored == event

    def test_round_completed_survives_serialization(self) -> None:
        event = RoundCompleted(
            **ENVELOPE, colony_id="col-1", round_number=3,
            convergence=0.87, cost=0.15, duration_ms=4500,
        )
        restored = deserialize(serialize(event))
        assert restored == event


# ---------------------------------------------------------------------------
# SQLite store restart (requires adapter)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sqlite_store_survives_reopen(tmp_path: Path) -> None:
    """Events persisted in SQLite survive closing and reopening the store."""
    from formicos.adapters.store_sqlite import SqliteEventStore

    db_path = tmp_path / "test.db"

    # Write events
    store1 = SqliteEventStore(str(db_path))
    ws_event = WorkspaceCreated(**ENVELOPE, name="research", config=_make_config())
    seq1 = await store1.append(ws_event)
    assert seq1 >= 1

    th_event = ThreadCreated(
        seq=0, timestamp=NOW, address="ws-1/th-1",
        workspace_id="ws-1", name="main",
    )
    seq2 = await store1.append(th_event)
    assert seq2 > seq1
    await store1.close()

    # Reopen and verify
    store2 = SqliteEventStore(str(db_path))

    events: list[object] = []
    async for e in store2.replay():
        events.append(e)

    assert len(events) == 2
    assert events[0].type == "WorkspaceCreated"
    assert events[1].type == "ThreadCreated"
    await store2.close()


@pytest.mark.asyncio
async def test_event_ordering_preserved(tmp_path: Path) -> None:
    """Events replayed in sequence order after restart."""
    from formicos.adapters.store_sqlite import SqliteEventStore

    db_path = tmp_path / "ordering.db"
    store = SqliteEventStore(str(db_path))

    # Append several events
    for i in range(5):
        event = RoundStarted(
            seq=0, timestamp=NOW, address=ADDR,
            colony_id="col-1", round_number=i + 1,
        )
        await store.append(event)
    await store.close()

    # Reopen and verify ordering
    store2 = SqliteEventStore(str(db_path))
    events: list[object] = []
    async for e in store2.replay():
        events.append(e)

    assert len(events) == 5
    for i, e in enumerate(events):
        assert e.round_number == i + 1
    await store2.close()


@pytest.mark.asyncio
async def test_single_database_file(tmp_path: Path) -> None:
    """Only one SQLite database file exists (no shadow databases)."""
    from formicos.adapters.store_sqlite import SqliteEventStore

    db_path = tmp_path / "single.db"
    store = SqliteEventStore(str(db_path))
    await store.append(WorkspaceCreated(**ENVELOPE, name="ws", config=_make_config()))
    await store.close()

    db_files = list(tmp_path.glob("*.db"))
    assert len(db_files) == 1
    assert db_files[0].name == "single.db"
