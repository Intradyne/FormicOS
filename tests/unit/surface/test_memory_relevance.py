"""Tests for Wave 26.5 Track B -- memory relevance fixes.

Covers:
- B1: _rank_and_trim preserves query relevance as primary signal
- B2: memory_available nudge is workspace-scoped
- B3: prior_failures nudge is task-scoped (domain overlap required)
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from formicos.surface.memory_store import MemoryStore

# ---------------------------------------------------------------------------
# B1: Ranking preserves query relevance
# ---------------------------------------------------------------------------


class TestRankAndTrim:
    """_rank_and_trim must use query score as the primary signal."""

    def test_high_score_candidate_beats_low_score_verified(self) -> None:
        """A highly relevant candidate must outrank a weakly relevant verified entry."""
        results = [
            {"id": "v1", "score": 0.3, "status": "verified", "confidence": 0.9},
            {"id": "c1", "score": 0.9, "status": "candidate", "confidence": 0.5},
        ]
        ranked = MemoryStore._rank_and_trim(results, top_k=2)
        assert ranked[0]["id"] == "c1", "High-relevance candidate should rank first"
        assert ranked[1]["id"] == "v1"

    def test_same_score_preserves_all(self) -> None:
        """At identical raw scores, _rank_and_trim preserves all entries.

        Wave 57 audit: status-based differentiation moved to
        knowledge_catalog._composite_key(). _rank_and_trim now sorts by
        raw Qdrant score only.
        """
        results = [
            {"id": "c1", "score": 0.7, "status": "candidate", "confidence": 0.5},
            {"id": "v1", "score": 0.7, "status": "verified", "confidence": 0.5},
        ]
        ranked = MemoryStore._rank_and_trim(results, top_k=2)
        assert len(ranked) == 2
        assert {r["id"] for r in ranked} == {"c1", "v1"}

    def test_top_k_trims(self) -> None:
        results = [
            {"id": f"e{i}", "score": 1.0 - i * 0.1, "status": "candidate", "confidence": 0.5}
            for i in range(5)
        ]
        ranked = MemoryStore._rank_and_trim(results, top_k=3)
        assert len(ranked) == 3
        # Thompson Sampling introduces randomness; only check trimming
        assert {r["id"] for r in ranked} <= {f"e{i}" for i in range(5)}

    def test_raw_score_dominates(self) -> None:
        """Higher raw score always wins (no composite in _rank_and_trim)."""
        results = [
            {"id": "hi_conf", "score": 0.3, "status": "candidate", "confidence": 1.0},
            {"id": "hi_rel", "score": 0.8, "status": "candidate", "confidence": 0.1},
        ]
        ranked = MemoryStore._rank_and_trim(results, top_k=2)
        assert ranked[0]["id"] == "hi_rel"


# ---------------------------------------------------------------------------
# B2: memory_available nudge is workspace-scoped
# ---------------------------------------------------------------------------


def _make_nudge_runtime(memory_entries: dict[str, dict[str, Any]]) -> MagicMock:
    """Build a minimal runtime mock for nudge testing."""
    runtime = MagicMock()
    runtime.projections = SimpleNamespace(memory_entries=memory_entries)
    return runtime


class TestMemoryAvailableWorkspaceScoped:
    """memory_available nudge should only count entries in the current workspace."""

    def test_fires_when_workspace_has_entries(self) -> None:
        from formicos.surface.queen_runtime import QueenAgent

        entries = {
            "e1": {"workspace_id": "ws-A", "polarity": "positive", "domains": []},
        }
        runtime = _make_nudge_runtime(entries)
        queen = QueenAgent(runtime)

        messages: list[dict[str, str]] = []
        queen._inject_nudges(messages, "ws-A")
        nudge_texts = [m["content"] for m in messages]
        assert any("memory is available" in t.lower() for t in nudge_texts)

    def test_does_not_fire_for_other_workspace(self) -> None:
        from formicos.surface.queen_runtime import QueenAgent

        entries = {
            "e1": {"workspace_id": "ws-A", "polarity": "positive", "domains": []},
        }
        runtime = _make_nudge_runtime(entries)
        queen = QueenAgent(runtime)

        messages: list[dict[str, str]] = []
        queen._inject_nudges(messages, "ws-B")
        nudge_texts = [m["content"] for m in messages]
        assert not any("memory is available" in t.lower() for t in nudge_texts)


# ---------------------------------------------------------------------------
# B3: prior_failures nudge is task-scoped
# ---------------------------------------------------------------------------


def _make_thread_mock(operator_msg: str) -> Any:
    msg = SimpleNamespace(role="operator", content=operator_msg)
    thread = SimpleNamespace(queen_messages=[msg])
    return thread


class TestPriorFailuresTaskScoped:
    """prior_failures nudge must only fire when task domains overlap negative entries."""

    def test_does_not_fire_for_unrelated_domain(self) -> None:
        """Negative experience in 'devops' should not fire for a 'creative' task."""
        from formicos.surface.queen_runtime import QueenAgent

        entries = {
            "e1": {
                "workspace_id": "ws-X",
                "polarity": "negative",
                "domains": ["devops"],
                "entry_type": "experience",
            },
        }
        runtime = _make_nudge_runtime(entries)
        queen = QueenAgent(runtime)

        thread = _make_thread_mock("write me a haiku about clouds")
        messages: list[dict[str, str]] = []
        queen._inject_nudges(messages, "ws-X", thread)
        nudge_texts = [m["content"] for m in messages]
        assert not any("prior colonies" in t.lower() for t in nudge_texts)

    def test_fires_when_task_domain_overlaps(self) -> None:
        """Negative experience in 'python' should fire for a python coding task."""
        from formicos.surface.queen_runtime import QueenAgent

        entries = {
            "e1": {
                "workspace_id": "ws-X",
                "polarity": "negative",
                "domains": ["code_implementation"],
                "entry_type": "experience",
            },
        }
        runtime = _make_nudge_runtime(entries)
        queen = QueenAgent(runtime)

        thread = _make_thread_mock("implement a retry decorator in python")
        messages: list[dict[str, str]] = []
        queen._inject_nudges(messages, "ws-X", thread)
        nudge_texts = [m["content"] for m in messages]
        assert any("prior colonies" in t.lower() for t in nudge_texts)

    def test_fires_on_keyword_domain_match(self) -> None:
        """Task containing 'testing' should match negative entry with 'testing' domain."""
        from formicos.surface.queen_runtime import QueenAgent

        entries = {
            "e1": {
                "workspace_id": "ws-Y",
                "polarity": "negative",
                "domains": ["testing"],
                "entry_type": "experience",
            },
        }
        runtime = _make_nudge_runtime(entries)
        queen = QueenAgent(runtime)

        thread = _make_thread_mock("fix the testing infrastructure")
        messages: list[dict[str, str]] = []
        queen._inject_nudges(messages, "ws-Y", thread)
        nudge_texts = [m["content"] for m in messages]
        assert any("prior colonies" in t.lower() for t in nudge_texts)

    def test_no_fire_without_thread(self) -> None:
        """Without a thread, prior_failures should not fire (no task context)."""
        from formicos.surface.queen_runtime import QueenAgent

        entries = {
            "e1": {
                "workspace_id": "ws-X",
                "polarity": "negative",
                "domains": ["code_implementation"],
            },
        }
        runtime = _make_nudge_runtime(entries)
        queen = QueenAgent(runtime)

        messages: list[dict[str, str]] = []
        queen._inject_nudges(messages, "ws-X")  # no thread
        nudge_texts = [m["content"] for m in messages]
        assert not any("prior colonies" in t.lower() for t in nudge_texts)
