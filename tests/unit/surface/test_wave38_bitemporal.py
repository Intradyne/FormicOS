"""Bi-temporal knowledge surfacing tests (Wave 38, Pillar 3C).

Validates that:
- graph edges include temporal fields (valid_at, invalid_at, transaction_time)
- edge history shows all versions of a relationship
- invalidated edges are surfaced with include_invalidated=True
- status change timestamps are tracked in projections
- temporal metadata is honestly surfaced where available
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from formicos.adapters.knowledge_graph import KnowledgeGraphAdapter
from formicos.core.events import (
    MemoryEntryCreated,
    MemoryEntryStatusChanged,
    WorkspaceConfigSnapshot,
    WorkspaceCreated,
)
from formicos.surface.projections import ProjectionStore

WS = "temporal-ws"


@pytest.fixture
async def kg(tmp_path):
    """Create a KnowledgeGraphAdapter backed by a temp SQLite file."""
    adapter = KnowledgeGraphAdapter(db_path=tmp_path / "temporal.db")
    yield adapter
    await adapter.close()


def _now() -> datetime:
    return datetime.now(tz=UTC)


_seq = 0


def _next_seq() -> int:
    global _seq
    _seq += 1
    return _seq


class TestEdgeTemporalFields:
    """Graph edges include bi-temporal fields."""

    @pytest.mark.asyncio
    async def test_edge_has_valid_at(self, kg) -> None:
        """New edges record valid_at timestamp."""
        n1 = await kg._create_entity("Auth", "MODULE", WS)
        n2 = await kg._create_entity("JWT", "CONCEPT", WS)
        await kg.add_edge(n1, n2, "IMPLEMENTS", WS)

        neighbors = await kg.get_neighbors(n1, workspace_id=WS)
        assert len(neighbors) == 1
        assert neighbors[0]["valid_at"] is not None
        assert neighbors[0]["invalid_at"] is None
        assert neighbors[0]["transaction_time"] is not None

    @pytest.mark.asyncio
    async def test_invalidated_edge_has_invalid_at(self, kg) -> None:
        """Invalidated edges have invalid_at set."""
        n1 = await kg._create_entity("A", "MODULE", WS)
        n2 = await kg._create_entity("B", "MODULE", WS)
        edge_id = await kg.add_edge(n1, n2, "DEPENDS_ON", WS)

        await kg.invalidate_edge(edge_id)

        # Default: invalidated edges are hidden
        neighbors = await kg.get_neighbors(n1, workspace_id=WS)
        assert len(neighbors) == 0

        # With include_invalidated: they're visible
        all_neighbors = await kg.get_neighbors(
            n1, workspace_id=WS, include_invalidated=True,
        )
        assert len(all_neighbors) == 1
        assert all_neighbors[0]["invalid_at"] is not None

    @pytest.mark.asyncio
    async def test_edge_update_creates_temporal_history(self, kg) -> None:
        """Updating an edge creates a new version; old one is invalidated."""
        n1 = await kg._create_entity("X", "CONCEPT", WS)
        n2 = await kg._create_entity("Y", "CONCEPT", WS)

        await kg.add_edge(n1, n2, "ENABLES", WS, confidence=0.5)
        await kg.add_edge(n1, n2, "ENABLES", WS, confidence=0.9)

        # Only current edge in default view
        current = await kg.get_neighbors(n1, workspace_id=WS)
        assert len(current) == 1
        assert current[0]["confidence"] == 0.9

        # Full history shows both
        all_edges = await kg.get_neighbors(
            n1, workspace_id=WS, include_invalidated=True,
        )
        assert len(all_edges) == 2
        invalidated = [e for e in all_edges if e["invalid_at"] is not None]
        assert len(invalidated) == 1


class TestEdgeHistory:
    """Edge history provides full temporal view of relationships."""

    @pytest.mark.asyncio
    async def test_edge_history_ordered(self, kg) -> None:
        """get_edge_history returns versions in chronological order."""
        n1 = await kg._create_entity("Router", "MODULE", WS)
        n2 = await kg._create_entity("Session", "CONCEPT", WS)

        await kg.add_edge(n1, n2, "DEPENDS_ON", WS, confidence=0.5)
        await kg.add_edge(n1, n2, "DEPENDS_ON", WS, confidence=0.7)
        await kg.add_edge(n1, n2, "DEPENDS_ON", WS, confidence=0.9)

        history = await kg.get_edge_history(n1, n2, "DEPENDS_ON", WS)
        assert len(history) == 3

        # Only the last one should be current
        current_versions = [h for h in history if h["is_current"]]
        assert len(current_versions) == 1
        assert current_versions[0]["confidence"] == 0.9

        # First two should be invalidated
        invalidated = [h for h in history if not h["is_current"]]
        assert len(invalidated) == 2

    @pytest.mark.asyncio
    async def test_edge_history_includes_source(self, kg) -> None:
        """Edge history includes source colony and round info."""
        n1 = await kg._create_entity("A", "MODULE", WS)
        n2 = await kg._create_entity("B", "MODULE", WS)

        await kg.add_edge(
            n1, n2, "VALIDATES", WS,
            source_colony="col-1", source_round=3,
        )

        history = await kg.get_edge_history(n1, n2, "VALIDATES", WS)
        assert len(history) == 1
        assert history[0]["source_colony"] == "col-1"
        assert history[0]["source_round"] == 3

    @pytest.mark.asyncio
    async def test_empty_edge_history(self, kg) -> None:
        """No edges returns empty history."""
        n1 = await kg._create_entity("Lone", "CONCEPT", WS)
        n2 = await kg._create_entity("Other", "CONCEPT", WS)
        history = await kg.get_edge_history(n1, n2, "DEPENDS_ON", WS)
        assert history == []


class TestProjectionTemporalTracking:
    """Projections track status change timestamps for temporal surfacing."""

    def test_status_change_records_timestamp(self) -> None:
        """MemoryEntryStatusChanged sets status_changed_at."""
        store = ProjectionStore()
        store.apply(WorkspaceCreated(
            seq=_next_seq(), timestamp=_now(), address=WS,
            name=WS,
            config=WorkspaceConfigSnapshot(budget=5.0, strategy="stigmergic"),
        ))

        store.apply(MemoryEntryCreated(
            seq=_next_seq(), timestamp=_now(), address=WS,
            entry={
                "id": "temporal-entry-1",
                "category": "skill",
                "title": "Test entry",
                "content": "Content",
                "status": "candidate",
                "conf_alpha": 10.0,
                "conf_beta": 3.0,
                "workspace_id": WS,
                "source_colony_id": "col-1",
                "polarity": "positive",
                "created_at": _now().isoformat(),
            },
            workspace_id=WS,
        ))

        change_time = _now()
        store.apply(MemoryEntryStatusChanged(
            seq=_next_seq(), timestamp=change_time, address=WS,
            entry_id="temporal-entry-1",
            old_status="candidate",
            new_status="verified",
            reason="colony completed",
            workspace_id=WS,
        ))

        entry = store.memory_entries["temporal-entry-1"]
        assert entry["status"] == "verified"
        assert "status_changed_at" in entry
        assert entry["status_changed_at"] == change_time.isoformat()

    def test_rejection_records_invalidated_at(self) -> None:
        """Rejecting an entry sets invalidated_at."""
        store = ProjectionStore()
        store.apply(WorkspaceCreated(
            seq=_next_seq(), timestamp=_now(), address=WS,
            name=WS,
            config=WorkspaceConfigSnapshot(budget=5.0, strategy="stigmergic"),
        ))

        store.apply(MemoryEntryCreated(
            seq=_next_seq(), timestamp=_now(), address=WS,
            entry={
                "id": "reject-entry-1",
                "category": "skill",
                "title": "Bad entry",
                "content": "Suspicious content",
                "status": "candidate",
                "conf_alpha": 5.0,
                "conf_beta": 5.0,
                "workspace_id": WS,
                "source_colony_id": "col-2",
                "polarity": "positive",
                "created_at": _now().isoformat(),
            },
            workspace_id=WS,
        ))

        reject_time = _now()
        store.apply(MemoryEntryStatusChanged(
            seq=_next_seq(), timestamp=reject_time, address=WS,
            entry_id="reject-entry-1",
            old_status="candidate",
            new_status="rejected",
            reason="contradiction with verified entry",
            workspace_id=WS,
        ))

        entry = store.memory_entries["reject-entry-1"]
        assert entry["status"] == "rejected"
        assert entry["invalidated_at"] == reject_time.isoformat()

    def test_non_rejection_no_invalidated_at(self) -> None:
        """Non-rejection status changes don't set invalidated_at."""
        store = ProjectionStore()
        store.apply(WorkspaceCreated(
            seq=_next_seq(), timestamp=_now(), address=WS,
            name=WS,
            config=WorkspaceConfigSnapshot(budget=5.0, strategy="stigmergic"),
        ))

        store.apply(MemoryEntryCreated(
            seq=_next_seq(), timestamp=_now(), address=WS,
            entry={
                "id": "active-entry-1",
                "category": "skill",
                "title": "Good entry",
                "content": "Good content",
                "status": "candidate",
                "conf_alpha": 10.0,
                "conf_beta": 3.0,
                "workspace_id": WS,
                "source_colony_id": "col-3",
                "polarity": "positive",
                "created_at": _now().isoformat(),
            },
            workspace_id=WS,
        ))

        store.apply(MemoryEntryStatusChanged(
            seq=_next_seq(), timestamp=_now(), address=WS,
            entry_id="active-entry-1",
            old_status="candidate",
            new_status="active",
            reason="promoted by operator",
            workspace_id=WS,
        ))

        entry = store.memory_entries["active-entry-1"]
        assert entry["status"] == "active"
        assert "status_changed_at" in entry
        assert entry.get("invalidated_at") is None
