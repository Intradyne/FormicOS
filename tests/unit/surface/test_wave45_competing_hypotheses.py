"""Wave 45 Team 2: Competing hypothesis surfacing tests.

Tests cover:
- ProjectionStore.rebuild_competing_pairs() detects competing entries
- ProjectionStore.get_competing_context() returns competitor metadata
- knowledge_catalog._format_tier() annotates with competing_with
- Domain-strategy projection tuning (reason, level_changes, success_rate)
- Agent-level topology gate documentation (gate fails)
- Wave 45.5: lazy rebuild via dirty flag and event-driven invalidation
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from formicos.core.events import (
    MemoryConfidenceUpdated,
    MemoryEntryCreated,
    MemoryEntryMerged,
    MemoryEntryStatusChanged,
)
from formicos.core.types import Resolution
from formicos.surface.projections import (
    DomainStrategyProjection,
    ProjectionStore,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    entry_id: str,
    *,
    polarity: str = "positive",
    domains: list[str] | None = None,
    conf_alpha: float = 10.0,
    conf_beta: float = 5.0,
    entry_type: str = "skill",
    status: str = "verified",
    title: str = "",
    content: str = "",
) -> dict[str, Any]:
    return {
        "id": entry_id,
        "polarity": polarity,
        "domains": domains or ["python", "testing"],
        "conf_alpha": conf_alpha,
        "conf_beta": conf_beta,
        "entry_type": entry_type,
        "status": status,
        "created_at": datetime.now(UTC).isoformat(),
        "merged_from": [],
        "title": title or f"Entry {entry_id}",
        "content": content or f"Content for {entry_id}",
        "summary": f"Summary for {entry_id}",
    }


def _make_store_with_entries(
    entries: list[dict[str, Any]],
) -> ProjectionStore:
    store = ProjectionStore()
    for e in entries:
        store.memory_entries[e["id"]] = e
    return store


# ---------------------------------------------------------------------------
# Competing hypothesis projection tracking
# ---------------------------------------------------------------------------


class TestRebuildCompetingPairs:
    """Test the rebuild_competing_pairs() method on ProjectionStore."""

    def test_no_entries_produces_empty(self) -> None:
        store = ProjectionStore()
        store.rebuild_competing_pairs()
        assert store.competing_pairs == {}

    def test_single_entry_no_pairs(self) -> None:
        store = _make_store_with_entries([
            _make_entry("e1"),
        ])
        store.rebuild_competing_pairs()
        assert store.competing_pairs == {}

    def test_non_contradicting_entries_no_pairs(self) -> None:
        """Entries with same polarity and same domains aren't contradictions."""
        store = _make_store_with_entries([
            _make_entry("e1", polarity="positive", domains=["python"]),
            _make_entry("e2", polarity="positive", domains=["rust"]),
        ])
        store.rebuild_competing_pairs()
        assert store.competing_pairs == {}

    def test_competing_entries_detected(self) -> None:
        """Two contradicting entries with close confidence resolve as competing."""
        # Create entries with opposite polarity and overlapping domains
        # but very close confidence scores (Phase 3 → competing)
        store = _make_store_with_entries([
            _make_entry(
                "e1", polarity="positive", domains=["python", "testing"],
                conf_alpha=10.0, conf_beta=5.0,
            ),
            _make_entry(
                "e2", polarity="negative", domains=["python", "testing"],
                conf_alpha=10.0, conf_beta=5.0,
            ),
        ])
        store.rebuild_competing_pairs()
        # Both entries should reference each other as competing
        assert "e2" in store.competing_pairs.get("e1", set())
        assert "e1" in store.competing_pairs.get("e2", set())

    def test_winner_resolution_not_tracked(self) -> None:
        """When one entry clearly wins, no competing pair is recorded."""
        store = _make_store_with_entries([
            _make_entry(
                "e1", polarity="positive", domains=["python", "testing"],
                conf_alpha=50.0, conf_beta=2.0,  # very high confidence
            ),
            _make_entry(
                "e2", polarity="negative", domains=["python", "testing"],
                conf_alpha=5.0, conf_beta=20.0,  # very low confidence
            ),
        ])
        store.rebuild_competing_pairs()
        # Clear winner → not tracked as competing
        assert store.competing_pairs == {}

    def test_unverified_entries_excluded(self) -> None:
        """Entries with status other than verified/stable/promoted are skipped."""
        store = _make_store_with_entries([
            _make_entry(
                "e1", polarity="positive", domains=["python"],
                status="candidate",
            ),
            _make_entry(
                "e2", polarity="negative", domains=["python"],
                status="candidate",
            ),
        ])
        store.rebuild_competing_pairs()
        assert store.competing_pairs == {}

    def test_low_alpha_entries_excluded(self) -> None:
        """Entries with conf_alpha < 5.0 are excluded from scanning."""
        store = _make_store_with_entries([
            _make_entry(
                "e1", polarity="positive", domains=["python"],
                conf_alpha=3.0,
            ),
            _make_entry(
                "e2", polarity="negative", domains=["python"],
                conf_alpha=3.0,
            ),
        ])
        store.rebuild_competing_pairs()
        assert store.competing_pairs == {}

    def test_rebuild_clears_stale_pairs(self) -> None:
        """Rebuilding replaces previous competing pairs entirely."""
        store = _make_store_with_entries([])
        store.competing_pairs = {"old1": {"old2"}, "old2": {"old1"}}
        store.rebuild_competing_pairs()
        assert store.competing_pairs == {}


class TestGetCompetingContext:
    """Test the get_competing_context() method."""

    def test_no_competitors_returns_empty(self) -> None:
        store = ProjectionStore()
        assert store.get_competing_context("e1") == []

    def test_returns_competitor_metadata(self) -> None:
        store = ProjectionStore()
        store.memory_entries["e2"] = _make_entry(
            "e2", conf_alpha=10.0, conf_beta=5.0, title="Competitor entry",
        )
        store.competing_pairs = {"e1": {"e2"}}
        ctx = store.get_competing_context("e1")
        assert len(ctx) == 1
        assert ctx[0]["id"] == "e2"
        assert ctx[0]["title"] == "Competitor entry"
        assert ctx[0]["confidence_mean"] == round(10.0 / 15.0, 3)
        assert ctx[0]["status"] == "verified"

    def test_missing_competitor_entry_skipped(self) -> None:
        """If a competing entry was deleted, it's silently skipped."""
        store = ProjectionStore()
        store.competing_pairs = {"e1": {"e_missing"}}
        ctx = store.get_competing_context("e1")
        assert ctx == []

    def test_multiple_competitors(self) -> None:
        store = ProjectionStore()
        store.memory_entries["e2"] = _make_entry("e2")
        store.memory_entries["e3"] = _make_entry("e3")
        store.competing_pairs = {"e1": {"e2", "e3"}}
        ctx = store.get_competing_context("e1")
        assert len(ctx) == 2
        ids = {c["id"] for c in ctx}
        assert ids == {"e2", "e3"}


# ---------------------------------------------------------------------------
# Retrieval annotation
# ---------------------------------------------------------------------------


class TestRetrievalCompetingAnnotation:
    """Test that _format_tier annotates competing entries."""

    def _make_catalog(
        self,
        projections: ProjectionStore | None = None,
    ) -> Any:
        from formicos.surface.knowledge_catalog import KnowledgeCatalog

        return KnowledgeCatalog(
            memory_store=None,
            vector_port=None,
            skill_collection="test-skills",
            projections=projections,
        )

    def test_competing_annotation_at_standard_tier(self) -> None:
        store = ProjectionStore()
        store.memory_entries["e2"] = _make_entry(
            "e2", title="Opposing view",
        )
        store.competing_pairs = {"e1": {"e2"}}

        catalog = self._make_catalog(projections=store)
        results = [
            {
                "id": "e1",
                "title": "Main entry",
                "summary": "A summary",
                "_confidence_tier": "high",
                "content_preview": "preview",
                "domains": ["python"],
                "decay_class": "stable",
            },
        ]
        formatted = catalog._format_tier(results, "standard")
        assert len(formatted) == 1
        assert "competing_with" in formatted[0]
        assert formatted[0]["competing_with"][0]["id"] == "e2"

    def test_competing_annotation_at_full_tier(self) -> None:
        store = ProjectionStore()
        store.memory_entries["e2"] = _make_entry("e2")
        store.competing_pairs = {"e1": {"e2"}}

        catalog = self._make_catalog(projections=store)
        results = [
            {
                "id": "e1",
                "title": "Main entry",
                "summary": "A summary",
                "_confidence_tier": "high",
                "content_preview": "preview",
                "domains": ["python"],
                "decay_class": "stable",
                "conf_alpha": 10.0,
                "conf_beta": 5.0,
                "merged_from": [],
            },
        ]
        formatted = catalog._format_tier(results, "full")
        assert "competing_with" in formatted[0]

    def test_no_annotation_at_summary_tier(self) -> None:
        """Summary tier doesn't include competing annotations."""
        store = ProjectionStore()
        store.competing_pairs = {"e1": {"e2"}}
        store.memory_entries["e2"] = _make_entry("e2")

        catalog = self._make_catalog(projections=store)
        results = [
            {
                "id": "e1",
                "title": "Main entry",
                "summary": "A summary",
                "_confidence_tier": "high",
            },
        ]
        formatted = catalog._format_tier(results, "summary")
        assert "competing_with" not in formatted[0]

    def test_no_annotation_without_projections(self) -> None:
        """No crash when projections are not available."""
        catalog = self._make_catalog(projections=None)
        results = [
            {
                "id": "e1",
                "title": "Main entry",
                "summary": "A summary",
                "_confidence_tier": "high",
                "content_preview": "preview",
                "domains": ["python"],
                "decay_class": "stable",
            },
        ]
        formatted = catalog._format_tier(results, "standard")
        assert "competing_with" not in formatted[0]

    def test_no_annotation_when_no_competitors(self) -> None:
        store = ProjectionStore()
        catalog = self._make_catalog(projections=store)
        results = [
            {
                "id": "e1",
                "title": "Main entry",
                "summary": "A summary",
                "_confidence_tier": "high",
                "content_preview": "preview",
                "domains": ["python"],
                "decay_class": "stable",
            },
        ]
        formatted = catalog._format_tier(results, "standard")
        assert "competing_with" not in formatted[0]


# ---------------------------------------------------------------------------
# Domain-strategy projection tuning
# ---------------------------------------------------------------------------


class TestDomainStrategyTuning:
    """Test Wave 45 domain-strategy projection enhancements."""

    def test_success_rate_property(self) -> None:
        proj = DomainStrategyProjection(
            domain="example.com",
            preferred_level=1,
            success_count=8,
            failure_count=2,
        )
        assert proj.success_rate == pytest.approx(0.8)

    def test_success_rate_zero_fetches(self) -> None:
        proj = DomainStrategyProjection(
            domain="example.com",
            preferred_level=1,
        )
        assert proj.success_rate == 0.0

    def test_reason_stored(self) -> None:
        proj = DomainStrategyProjection(
            domain="example.com",
            preferred_level=2,
            reason="Level 1 extraction failed",
        )
        assert proj.reason == "Level 1 extraction failed"

    def test_level_changes_tracked_on_update(self) -> None:
        """Handler tracks how many times the preferred level changed."""
        from formicos.core.events import DomainStrategyUpdated

        store = ProjectionStore()
        ts = datetime.now(UTC)

        # First update: level 1
        ev1 = DomainStrategyUpdated(
            seq=1, timestamp=ts, address="ws-1",
            workspace_id="ws-1", domain="docs.python.org",
            preferred_level=1, success_count=1, failure_count=0,
            reason="initial",
        )
        store.apply(ev1)
        proj = store.domain_strategies["ws-1"]["docs.python.org"]
        assert proj.level_changes == 0
        assert proj.reason == "initial"

        # Second update: same level
        ev2 = DomainStrategyUpdated(
            seq=2, timestamp=ts, address="ws-1",
            workspace_id="ws-1", domain="docs.python.org",
            preferred_level=1, success_count=2, failure_count=0,
            reason="more fetches",
        )
        store.apply(ev2)
        proj = store.domain_strategies["ws-1"]["docs.python.org"]
        assert proj.level_changes == 0  # no level change

        # Third update: level changed to 2
        ev3 = DomainStrategyUpdated(
            seq=3, timestamp=ts, address="ws-1",
            workspace_id="ws-1", domain="docs.python.org",
            preferred_level=2, success_count=2, failure_count=1,
            reason="level 1 failed",
        )
        store.apply(ev3)
        proj = store.domain_strategies["ws-1"]["docs.python.org"]
        assert proj.level_changes == 1
        assert proj.reason == "level 1 failed"

    def test_cumulative_counts_accurate(self) -> None:
        """Handler stores the cumulative counts from the event."""
        from formicos.core.events import DomainStrategyUpdated

        store = ProjectionStore()
        ts = datetime.now(UTC)

        ev = DomainStrategyUpdated(
            seq=1, timestamp=ts, address="ws-1",
            workspace_id="ws-1", domain="example.com",
            preferred_level=1, success_count=10, failure_count=3,
            reason="test",
        )
        store.apply(ev)
        proj = store.domain_strategies["ws-1"]["example.com"]
        assert proj.success_count == 10
        assert proj.failure_count == 3
        assert proj.success_rate == pytest.approx(10 / 13)


# ---------------------------------------------------------------------------
# Agent-level topology gate
# ---------------------------------------------------------------------------


class TestTopologyGate:
    """Document that the agent-level topology gate fails.

    AgentConfig does not carry per-agent file scope. The Queen's planner
    assigns target_files at colony level only. _compute_structural_affinity
    correctly applies a uniform boost to all agents in the colony.

    Gate outcome: FAIL — topology prior stays colony-level.
    """

    def test_agent_config_has_no_file_scope(self) -> None:
        """AgentConfig model fields do not include file assignments."""
        from formicos.core.types import AgentConfig

        fields = set(AgentConfig.model_fields.keys())
        # Verify no file-scope field exists
        file_related = {"files", "target_files", "file_scope", "assigned_files"}
        assert fields.isdisjoint(file_related), (
            f"AgentConfig gained file-scope fields: {fields & file_related}. "
            f"Re-evaluate the topology gate."
        )

    def test_structural_affinity_is_uniform(self) -> None:
        """All agents get the same affinity — confirming colony-level prior."""
        from formicos.core.types import AgentConfig, CasteRecipe
        from formicos.engine.runner import _compute_structural_affinity

        recipe = CasteRecipe(
            name="coder", description="test",
            system_prompt="test", temperature=0.0,
            max_tokens=4096, tools=[], max_iterations=5,
            max_execution_time_s=120,
        )
        agents = [
            AgentConfig(
                id=f"agent-{i}", name=f"Agent {i}",
                caste="coder", model="test-model", recipe=recipe,
            )
            for i in range(3)
        ]
        deps = {"a.py": ["b.py"], "b.py": ["c.py"]}
        targets = ["a.py", "b.py"]

        result = _compute_structural_affinity(agents, deps, targets)
        # All agents get the same score
        scores = list(result.values())
        assert len(scores) == 3
        assert all(s == scores[0] for s in scores)


# ---------------------------------------------------------------------------
# Wave 45.5: Lazy competing-pairs rebuild via dirty flag
# ---------------------------------------------------------------------------


def _ts() -> datetime:
    return datetime.now(UTC)


class TestLazyCompetingPairsRebuild:
    """Verify competing pairs are rebuilt lazily when projection state changes."""

    def test_new_store_not_dirty(self) -> None:
        store = ProjectionStore()
        assert store._competing_pairs_dirty is False

    def test_memory_entry_created_sets_dirty(self) -> None:
        store = ProjectionStore()
        ev = MemoryEntryCreated(
            seq=1, timestamp=_ts(), address="ws-1",
            workspace_id="ws-1",
            entry={"id": "e1", "title": "Test", "status": "verified"},
        )
        store.apply(ev)
        assert store._competing_pairs_dirty is True

    def test_memory_status_changed_sets_dirty(self) -> None:
        store = ProjectionStore()
        store.memory_entries["e1"] = _make_entry("e1")
        ev = MemoryEntryStatusChanged(
            seq=2, timestamp=_ts(), address="ws-1",
            workspace_id="ws-1", entry_id="e1",
            old_status="candidate", new_status="verified",
        )
        store.apply(ev)
        assert store._competing_pairs_dirty is True

    def test_memory_confidence_updated_sets_dirty(self) -> None:
        store = ProjectionStore()
        store.memory_entries["e1"] = _make_entry("e1")
        ev = MemoryConfidenceUpdated(
            seq=3, timestamp=_ts(), address="ws-1",
            workspace_id="ws-1", entry_id="e1",
            old_alpha=10.0, old_beta=5.0,
            new_alpha=12.0, new_beta=5.0,
            new_confidence=0.7, reason="test",
        )
        store.apply(ev)
        assert store._competing_pairs_dirty is True

    def test_memory_entry_merged_sets_dirty(self) -> None:
        store = ProjectionStore()
        store.memory_entries["e1"] = _make_entry("e1")
        store.memory_entries["e2"] = _make_entry("e2")
        ev = MemoryEntryMerged(
            seq=4, timestamp=_ts(), address="ws-1",
            target_id="e1", source_id="e2",
            merged_content="merged", merged_domains=["python"],
            merged_from=["e2"], content_strategy="keep_longer",
            similarity=0.9, merge_source="dedup", workspace_id="ws-1",
        )
        store.apply(ev)
        assert store._competing_pairs_dirty is True

    def test_get_competing_context_clears_dirty_flag(self) -> None:
        store = ProjectionStore()
        store._competing_pairs_dirty = True
        # No entries → rebuild produces empty, but flag should clear
        store.get_competing_context("e1")
        assert store._competing_pairs_dirty is False

    def test_lazy_rebuild_detects_competing_pairs(self) -> None:
        """get_competing_context triggers rebuild and returns live results."""
        store = _make_store_with_entries([
            _make_entry(
                "e1", polarity="positive", domains=["python", "testing"],
                conf_alpha=10.0, conf_beta=5.0,
            ),
            _make_entry(
                "e2", polarity="negative", domains=["python", "testing"],
                conf_alpha=10.0, conf_beta=5.0,
            ),
        ])
        # Manually set dirty (as event handlers would)
        store._competing_pairs_dirty = True
        # Should lazily rebuild and find the competing pair
        ctx = store.get_competing_context("e1")
        assert len(ctx) == 1
        assert ctx[0]["id"] == "e2"

    def test_explicit_rebuild_clears_dirty(self) -> None:
        store = ProjectionStore()
        store._competing_pairs_dirty = True
        store.rebuild_competing_pairs()
        assert store._competing_pairs_dirty is False

    def test_replay_leaves_dirty_for_lazy_rebuild(self) -> None:
        """After replay with memory events, pairs are rebuilt on first access."""
        store = ProjectionStore()
        events = [
            MemoryEntryCreated(
                seq=1, timestamp=_ts(), address="ws-1",
                workspace_id="ws-1",
                entry=_make_entry(
                    "e1", polarity="positive", domains=["python"],
                ),
            ),
            MemoryEntryCreated(
                seq=2, timestamp=_ts(), address="ws-1",
                workspace_id="ws-1",
                entry=_make_entry(
                    "e2", polarity="negative", domains=["python"],
                ),
            ),
        ]
        store.replay(events)
        # Dirty flag should be set from MemoryEntryCreated handlers
        assert store._competing_pairs_dirty is True
        # Accessing competing context should trigger rebuild
        store.get_competing_context("e1")
        assert store._competing_pairs_dirty is False
