"""Wave 48 Team 1: Thread timeline API and builder tests.

Covers:
- build_thread_timeline produces chronological entries from replay-safe truth
- Colony lifecycle rows (spawned, completed, failed)
- Queen message / operator directive rows
- Forage cycle rows linked by thread_id
- Knowledge entry rows linked by source colony
- Limit parameter works correctly
- Empty thread returns empty list
"""

from __future__ import annotations

from dataclasses import field
from typing import Any

import pytest

from formicos.surface.projections import (
    ColonyProjection,
    ForageCycleSummary,
    ProjectionStore,
    QueenMessageProjection,
    ThreadProjection,
    WorkspaceProjection,
    build_thread_timeline,
)


def _make_store_with_thread() -> tuple[ProjectionStore, str, str]:
    """Create a ProjectionStore with a workspace, thread, and colonies."""
    store = ProjectionStore()
    ws_id = "ws-1"
    thread_id = "thread-1"

    ws = WorkspaceProjection(id=ws_id, name="Test Workspace")
    thread = ThreadProjection(id=thread_id, workspace_id=ws_id, name="Fix auth bug")
    thread.goal = "Fix the authentication bug"

    # Colony 1: completed
    c1 = ColonyProjection(
        id="col-aaa", thread_id=thread_id, workspace_id=ws_id,
        task="Implement auth fix", status="completed",
        strategy="stigmergic", castes=["coder", "reviewer"],
        spawned_at="2026-03-19T10:00:00+00:00",
        completed_at="2026-03-19T10:05:00+00:00",
        round_number=3, max_rounds=10, cost=0.85,
        quality_score=0.9, entries_extracted_count=2,
    )
    thread.colonies["col-aaa"] = c1

    # Colony 2: running
    c2 = ColonyProjection(
        id="col-bbb", thread_id=thread_id, workspace_id=ws_id,
        task="Test auth fix", status="running",
        strategy="sequential",
        spawned_at="2026-03-19T10:06:00+00:00",
        round_number=1, max_rounds=5,
    )
    thread.colonies["col-bbb"] = c2

    # Queen messages
    thread.queen_messages = [
        QueenMessageProjection(
            role="operator",
            content="Fix the auth login endpoint",
            timestamp="2026-03-19T09:55:00+00:00",
        ),
        QueenMessageProjection(
            role="queen",
            content="Spawning auth fix colony with coder+reviewer",
            timestamp="2026-03-19T09:56:00+00:00",
        ),
    ]

    ws.threads[thread_id] = thread
    store.workspaces[ws_id] = ws

    return store, ws_id, thread_id


class TestBuildThreadTimeline:
    """Verify build_thread_timeline produces correct chronological entries."""

    def test_basic_timeline_has_entries(self) -> None:
        store, ws_id, thread_id = _make_store_with_thread()
        timeline = build_thread_timeline(store, ws_id, thread_id)
        # Colony spawned x2 + colony completed x1 + queen messages x2 = 5
        assert len(timeline) >= 5

    def test_chronological_order(self) -> None:
        store, ws_id, thread_id = _make_store_with_thread()
        timeline = build_thread_timeline(store, ws_id, thread_id)
        timestamps = [e["timestamp"] for e in timeline if e["timestamp"]]
        assert timestamps == sorted(timestamps)

    def test_colony_spawned_entries(self) -> None:
        store, ws_id, thread_id = _make_store_with_thread()
        timeline = build_thread_timeline(store, ws_id, thread_id)
        spawned = [e for e in timeline if e.get("subtype") == "spawned"]
        assert len(spawned) == 2
        assert any("col-aaa" in e["summary"] for e in spawned)

    def test_colony_completed_entries(self) -> None:
        store, ws_id, thread_id = _make_store_with_thread()
        timeline = build_thread_timeline(store, ws_id, thread_id)
        completed = [
            e for e in timeline
            if e["type"] == "colony" and e["subtype"] in ("validated", "unvalidated")
        ]
        assert len(completed) == 1
        assert "col-aaa" in completed[0]["summary"]

    def test_queen_message_entries(self) -> None:
        store, ws_id, thread_id = _make_store_with_thread()
        timeline = build_thread_timeline(store, ws_id, thread_id)
        operator = [e for e in timeline if e["type"] == "operator"]
        queen = [e for e in timeline if e["type"] == "queen"]
        assert len(operator) == 1
        assert len(queen) == 1

    def test_forage_cycle_linked_by_thread(self) -> None:
        store, ws_id, thread_id = _make_store_with_thread()
        # Add a forage cycle linked to this thread
        store.forage_cycles[ws_id] = [
            ForageCycleSummary(
                forage_request_seq=1,
                mode="reactive",
                reason="knowledge gap",
                queries_issued=2,
                entries_admitted=1,
                timestamp="2026-03-19T10:01:00+00:00",
                thread_id=thread_id,
                colony_id="col-aaa",
            ),
            ForageCycleSummary(
                forage_request_seq=2,
                mode="proactive",
                reason="stale entry",
                timestamp="2026-03-19T10:02:00+00:00",
                thread_id="other-thread",  # different thread
            ),
        ]
        timeline = build_thread_timeline(store, ws_id, thread_id)
        forage = [e for e in timeline if e["type"] == "forage"]
        assert len(forage) == 1
        assert forage[0]["subtype"] == "reactive"

    def test_knowledge_entries_linked_by_colony(self) -> None:
        store, ws_id, thread_id = _make_store_with_thread()
        store.memory_entries["mem-1"] = {
            "id": "mem-1",
            "title": "Auth pattern",
            "category": "skill",
            "source_colony_id": "col-aaa",
            "created_at": "2026-03-19T10:04:00+00:00",
            "status": "observed",
        }
        store.memory_entries["mem-2"] = {
            "id": "mem-2",
            "title": "Unrelated",
            "category": "skill",
            "source_colony_id": "col-zzz",  # not in thread
            "created_at": "2026-03-19T10:04:00+00:00",
        }
        timeline = build_thread_timeline(store, ws_id, thread_id)
        knowledge = [e for e in timeline if e["type"] == "knowledge"]
        assert len(knowledge) == 1
        assert knowledge[0]["detail"]["entry_id"] == "mem-1"

    def test_limit_parameter(self) -> None:
        store, ws_id, thread_id = _make_store_with_thread()
        timeline = build_thread_timeline(store, ws_id, thread_id, limit=2)
        assert len(timeline) <= 2

    def test_unknown_thread_returns_empty(self) -> None:
        store, ws_id, _ = _make_store_with_thread()
        timeline = build_thread_timeline(store, ws_id, "nonexistent")
        assert timeline == []

    def test_entry_structure(self) -> None:
        store, ws_id, thread_id = _make_store_with_thread()
        timeline = build_thread_timeline(store, ws_id, thread_id)
        for entry in timeline:
            assert "type" in entry
            assert "subtype" in entry
            assert "timestamp" in entry
            assert "summary" in entry
            assert "detail" in entry
