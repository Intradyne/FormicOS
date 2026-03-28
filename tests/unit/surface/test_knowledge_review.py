"""Wave 72 Track 1: knowledge_review scanner tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from formicos.surface.action_queue import (
    STATUS_PENDING_REVIEW,
    append_action,
    create_action,
    read_actions,
)
from formicos.surface.knowledge_review import scan_knowledge_for_review


def _make_projections(
    entries: dict[str, dict[str, Any]] | None = None,
    usage: dict[str, dict[str, Any]] | None = None,
    outcomes: dict[str, Any] | None = None,
    pinned: set[str] | None = None,
) -> MagicMock:
    """Build a minimal mock ProjectionStore."""
    proj = MagicMock()
    proj.memory_entries = entries or {}
    proj.knowledge_entry_usage = usage or {}
    proj.colony_outcomes = outcomes or {}
    proj.operator_overlays = MagicMock()
    proj.operator_overlays.pinned_entries = pinned or set()
    return proj


def _make_entry(
    *,
    entry_id: str = "e1",
    title: str = "Test entry",
    workspace_id: str = "ws1",
    conf_alpha: float = 5.0,
    conf_beta: float = 5.0,
    created_at: str = "",
    decay_class: str = "stable",
    created_by: str = "extraction",
) -> dict[str, Any]:
    if not created_at:
        created_at = datetime.now(UTC).isoformat()
    return {
        "entry_id": entry_id,
        "title": title,
        "workspace_id": workspace_id,
        "content": f"Content for {title}",
        "conf_alpha": conf_alpha,
        "conf_beta": conf_beta,
        "created_at": created_at,
        "decay_class": decay_class,
        "created_by": created_by,
    }


def _make_outcome(
    colony_id: str,
    workspace_id: str = "ws1",
    succeeded: bool = True,
) -> MagicMock:
    outcome = MagicMock()
    outcome.colony_id = colony_id
    outcome.workspace_id = workspace_id
    outcome.succeeded = succeeded
    outcome.entries_accessed = 1
    return outcome


class TestOutcomeCorrelatedFailure:
    @pytest.mark.asyncio
    async def test_failure_correlated_entry_queues_review(self, tmp_path: Path) -> None:
        entry = _make_entry(entry_id="e1")
        # 4 colonies, 3 failed
        outcomes = {
            f"c{i}": _make_outcome(f"c{i}", succeeded=(i == 0))
            for i in range(4)
        }
        usage = {
            "e1": {"count": 4, "last_accessed": datetime.now(UTC).isoformat(),
                   "colonies": ["c0", "c1", "c2", "c3"]},
        }
        proj = _make_projections(
            entries={"e1": entry},
            usage=usage,
            outcomes=outcomes,
        )

        count = await scan_knowledge_for_review(str(tmp_path), "ws1", proj)
        assert count >= 1
        actions = read_actions(str(tmp_path), "ws1")
        review_actions = [a for a in actions if a["kind"] == "knowledge_review"]
        assert len(review_actions) >= 1
        assert review_actions[0]["payload"]["review_reason"] == "outcome_correlated_failure"


class TestContradiction:
    @pytest.mark.asyncio
    async def test_contradiction_insight_becomes_review(self, tmp_path: Path) -> None:
        entry = _make_entry(entry_id="e1")
        proj = _make_projections(entries={"e1": entry})
        insights: list[dict[str, object]] = [
            {
                "category": "contradiction",
                "detail": f"Entries e1 contradict each other",
                "entry_ids": ["e1"],
            },
        ]
        count = await scan_knowledge_for_review(
            str(tmp_path), "ws1", proj,
            briefing_insights=insights,
        )
        assert count >= 1
        actions = read_actions(str(tmp_path), "ws1")
        review_actions = [a for a in actions if a["kind"] == "knowledge_review"]
        assert any(a["payload"]["review_reason"] == "contradiction" for a in review_actions)


class TestStaleAuthority:
    @pytest.mark.asyncio
    async def test_stale_authority_queues_review(self, tmp_path: Path) -> None:
        old_date = (datetime.now(UTC) - timedelta(days=120)).isoformat()
        entry = _make_entry(
            entry_id="e1", conf_alpha=20.0, conf_beta=3.0,
            created_at=old_date,
        )
        usage = {"e1": {"count": 10, "last_accessed": old_date}}
        proj = _make_projections(entries={"e1": entry}, usage=usage)

        count = await scan_knowledge_for_review(str(tmp_path), "ws1", proj)
        assert count >= 1
        actions = read_actions(str(tmp_path), "ws1")
        review_actions = [a for a in actions if a["kind"] == "knowledge_review"]
        assert any(a["payload"]["review_reason"] == "stale_authority" for a in review_actions)

    @pytest.mark.asyncio
    async def test_permanent_entries_excluded_from_stale(self, tmp_path: Path) -> None:
        old_date = (datetime.now(UTC) - timedelta(days=120)).isoformat()
        entry = _make_entry(
            entry_id="e1", conf_alpha=20.0, conf_beta=3.0,
            created_at=old_date, decay_class="permanent",
        )
        usage = {"e1": {"count": 10, "last_accessed": old_date}}
        proj = _make_projections(entries={"e1": entry}, usage=usage)

        count = await scan_knowledge_for_review(str(tmp_path), "ws1", proj)
        # Should not queue stale review for permanent entries
        actions = read_actions(str(tmp_path), "ws1")
        stale = [
            a for a in actions
            if a.get("kind") == "knowledge_review"
            and a.get("payload", {}).get("review_reason") == "stale_authority"
        ]
        assert len(stale) == 0


class TestUnconfirmedMachine:
    @pytest.mark.asyncio
    async def test_unconfirmed_machine_generated_queues_review(self, tmp_path: Path) -> None:
        entry = _make_entry(entry_id="e1", created_by="extraction")
        usage = {"e1": {"count": 10, "last_accessed": datetime.now(UTC).isoformat()}}
        proj = _make_projections(entries={"e1": entry}, usage=usage)

        count = await scan_knowledge_for_review(str(tmp_path), "ws1", proj)
        assert count >= 1
        actions = read_actions(str(tmp_path), "ws1")
        review_actions = [a for a in actions if a["kind"] == "knowledge_review"]
        assert any(
            a["payload"]["review_reason"] == "unconfirmed_machine_generated"
            for a in review_actions
        )


class TestDedupe:
    @pytest.mark.asyncio
    async def test_dedupe_skips_existing_pending_review(self, tmp_path: Path) -> None:
        entry = _make_entry(entry_id="e1", created_by="extraction")
        usage = {"e1": {"count": 10, "last_accessed": datetime.now(UTC).isoformat()}}
        proj = _make_projections(entries={"e1": entry}, usage=usage)

        # Pre-create a pending review for e1
        existing = create_action(
            kind="knowledge_review",
            title="Existing review",
            payload={"entry_id": "e1"},
            created_by="knowledge_review_scanner",
        )
        append_action(str(tmp_path), "ws1", existing)

        count = await scan_knowledge_for_review(str(tmp_path), "ws1", proj)
        # Should not queue a second review for e1
        actions = read_actions(str(tmp_path), "ws1")
        review_actions = [
            a for a in actions
            if a["kind"] == "knowledge_review"
            and a["payload"].get("entry_id") == "e1"
        ]
        assert len(review_actions) == 1  # only the pre-existing one
