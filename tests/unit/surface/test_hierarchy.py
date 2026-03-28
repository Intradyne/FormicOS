"""Tests for Wave 67 knowledge hierarchy — materialized paths + branch confidence.

See ADR-049 for design rationale.
"""

from __future__ import annotations

from datetime import datetime, timezone

from formicos.core.events import (
    MemoryEntryCreated,
    WorkspaceCreated,
)
from formicos.core.events import WorkspaceConfigSnapshot
from formicos.surface.hierarchy import build_knowledge_tree, compute_branch_confidence
from formicos.surface.projections import ProjectionStore

_NOW = datetime(2026, 3, 25, tzinfo=timezone.utc)
_WS = "ws-hier"
_WS_CONFIG = WorkspaceConfigSnapshot(budget=5.0, strategy="stigmergic")


def _store_with_workspace() -> ProjectionStore:
    store = ProjectionStore()
    store.apply(WorkspaceCreated(
        seq=1, timestamp=_NOW, address=_WS,
        name=_WS, config=_WS_CONFIG,
    ))
    return store


def _add_entry(
    store: ProjectionStore,
    entry_id: str,
    domains: list[str] | None = None,
    conf_alpha: float = 5.0,
    conf_beta: float = 5.0,
    workspace_id: str = _WS,
) -> None:
    store.apply(MemoryEntryCreated(
        seq=10, timestamp=_NOW, address=f"{workspace_id}/t-1",
        workspace_id=workspace_id,
        entry={
            "id": entry_id,
            "entry_type": "skill",
            "status": "candidate",
            "polarity": "positive",
            "title": f"Entry {entry_id}",
            "content": f"Content for {entry_id}",
            "source_colony_id": "col-1",
            "source_artifact_ids": [],
            "workspace_id": workspace_id,
            "thread_id": "t-1",
            "domains": domains or [],
            "conf_alpha": conf_alpha,
            "conf_beta": conf_beta,
            "confidence": conf_alpha / (conf_alpha + conf_beta),
        },
    ))


class TestHierarchyPathOnProjection:
    """_on_memory_entry_created sets hierarchy_path from primary domain."""

    def test_sets_hierarchy_path_from_primary_domain(self) -> None:
        store = _store_with_workspace()
        _add_entry(store, "e-1", domains=["Python Testing", "CI"])
        entry = store.memory_entries["e-1"]
        assert entry["hierarchy_path"] == "/python_testing/"
        assert entry["parent_id"] == ""

    def test_normalizes_hyphens_and_spaces(self) -> None:
        store = _store_with_workspace()
        _add_entry(store, "e-2", domains=["web-development"])
        entry = store.memory_entries["e-2"]
        assert entry["hierarchy_path"] == "/web_development/"

    def test_no_domains_gets_uncategorized(self) -> None:
        store = _store_with_workspace()
        _add_entry(store, "e-3", domains=[])
        entry = store.memory_entries["e-3"]
        assert entry["hierarchy_path"] == "/uncategorized/"

    def test_multiple_spaces_collapse_to_single_underscore(self) -> None:
        store = _store_with_workspace()
        _add_entry(store, "e-4", domains=["python  testing"])
        entry = store.memory_entries["e-4"]
        assert entry["hierarchy_path"] == "/python_testing/"


class TestBranchConfidenceAggregation:
    """compute_branch_confidence aggregates children's Beta posteriors."""

    def test_aggregates_children_evidence(self) -> None:
        store = _store_with_workspace()
        # 3 entries under /engineering/ with known alpha/beta
        _add_entry(store, "e-1", domains=["engineering"], conf_alpha=10.0, conf_beta=3.0)
        _add_entry(store, "e-2", domains=["engineering"], conf_alpha=8.0, conf_beta=4.0)
        _add_entry(store, "e-3", domains=["engineering"], conf_alpha=7.0, conf_beta=2.0)

        result = compute_branch_confidence(store, "/engineering/")
        assert result["count"] == 3
        # Evidence: alpha_ev = (10-5)+(8-5)+(7-5) = 10, beta_ev = (3-5)+(4-5)+(2-5) = -6
        # Aggregated: alpha = 5+10 = 15, beta = max(5+(-6), 1.0) = 1.0 (clamped)
        assert result["alpha"] == 15.0
        assert result["beta"] == 1.0  # clamped from -1.0
        assert 0.0 <= result["mean"] <= 1.0  # valid probability

    def test_negative_evidence_clamps_to_floor(self) -> None:
        """When many children have conf < prior, aggregated params stay valid."""
        store = _store_with_workspace()
        # 5 entries with very low beta (1.0 each) -> beta evidence = 5*(1-5) = -20
        for i in range(5):
            _add_entry(
                store, f"e-{i}", domains=["lowbeta"],
                conf_alpha=10.0, conf_beta=1.0,
            )
        result = compute_branch_confidence(store, "/lowbeta/")
        assert result["count"] == 5
        assert result["alpha"] >= 1.0
        assert result["beta"] >= 1.0
        assert 0.0 <= result["mean"] <= 1.0

    def test_ess_cap_at_150(self) -> None:
        store = _store_with_workspace()
        # Create entries with high alpha/beta to exceed ESS 150
        _add_entry(store, "e-1", domains=["big"], conf_alpha=50.0, conf_beta=30.0)
        _add_entry(store, "e-2", domains=["big"], conf_alpha=45.0, conf_beta=25.0)
        _add_entry(store, "e-3", domains=["big"], conf_alpha=40.0, conf_beta=20.0)

        result = compute_branch_confidence(store, "/big/")
        ess = result["alpha"] + result["beta"]
        assert ess <= 150.0 + 0.01  # float tolerance

    def test_ess_cap_preserves_mean(self) -> None:
        store = _store_with_workspace()
        _add_entry(store, "e-1", domains=["cap"], conf_alpha=80.0, conf_beta=20.0)
        _add_entry(store, "e-2", domains=["cap"], conf_alpha=70.0, conf_beta=15.0)

        result = compute_branch_confidence(store, "/cap/")
        # Mean should be close to the uncapped mean
        # Uncapped: alpha = 5+(80-5)+(70-5) = 145, beta = 5+(20-5)+(15-5) = 30
        # Uncapped mean = 145/175 ≈ 0.829
        # Capped: should preserve the ratio
        assert abs(result["mean"] - 145.0 / 175.0) < 0.01

    def test_excludes_topic_nodes(self) -> None:
        store = _store_with_workspace()
        _add_entry(store, "e-1", domains=["mixed"], conf_alpha=10.0, conf_beta=5.0)
        # Manually inject a synthetic topic node
        store.memory_entries["topic-1"] = {
            "entry_type": "topic",
            "hierarchy_path": "/mixed/",
            "conf_alpha": 50.0,
            "conf_beta": 10.0,
            "workspace_id": _WS,
        }
        result = compute_branch_confidence(store, "/mixed/")
        assert result["count"] == 1  # only the real entry, not the topic

    def test_empty_prefix_returns_default(self) -> None:
        store = _store_with_workspace()
        result = compute_branch_confidence(store, "/nonexistent/")
        assert result["count"] == 0
        assert result["mean"] == 0.5  # default prior


class TestBuildKnowledgeTree:
    """build_knowledge_tree builds tree from hierarchy paths."""

    def test_builds_root_branches(self) -> None:
        store = _store_with_workspace()
        _add_entry(store, "e-1", domains=["engineering"])
        _add_entry(store, "e-2", domains=["engineering"])
        _add_entry(store, "e-3", domains=["testing"])

        tree = build_knowledge_tree(store, _WS)
        labels = [b["label"] for b in tree]
        assert "engineering" in labels
        assert "testing" in labels
        eng = next(b for b in tree if b["label"] == "engineering")
        assert eng["entryCount"] == 2

    def test_filters_by_workspace(self) -> None:
        store = _store_with_workspace()
        _add_entry(store, "e-1", domains=["eng"], workspace_id=_WS)
        _add_entry(store, "e-2", domains=["eng"], workspace_id="other-ws")

        tree = build_knowledge_tree(store, _WS)
        if tree:
            eng = next((b for b in tree if b["label"] == "eng"), None)
            assert eng is not None
            assert eng["entryCount"] == 1

    def test_empty_workspace_returns_empty(self) -> None:
        store = _store_with_workspace()
        tree = build_knowledge_tree(store, _WS)
        assert tree == []
