"""Tests for Wave 67.5 provenance chain on projections."""

from __future__ import annotations

from datetime import datetime, timezone

from formicos.core.events import (
    KnowledgeEntryAnnotated,
    KnowledgeEntryOperatorAction,
    MemoryConfidenceUpdated,
    MemoryEntryCreated,
    MemoryEntryMerged,
    WorkspaceCreated,
)
from formicos.core.events import WorkspaceConfigSnapshot
from formicos.surface.projections import ProjectionStore

_NOW = datetime(2026, 3, 25, tzinfo=timezone.utc)
_WS = "ws-prov"
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
    entry_id: str = "e-1",
    source_colony_id: str = "col-1",
) -> None:
    store.apply(MemoryEntryCreated(
        seq=10, timestamp=_NOW, address=f"{_WS}/t-1",
        workspace_id=_WS,
        entry={
            "id": entry_id,
            "entry_type": "skill",
            "status": "candidate",
            "polarity": "positive",
            "title": f"Entry {entry_id}",
            "content": f"Content for {entry_id}",
            "source_colony_id": source_colony_id,
            "source_artifact_ids": [],
            "workspace_id": _WS,
            "thread_id": "t-1",
            "domains": ["testing"],
            "conf_alpha": 5.0,
            "conf_beta": 5.0,
            "confidence": 0.5,
        },
    ))


class TestProvenanceChainOnCreation:
    def test_memory_entry_created_seeds_provenance_chain(self) -> None:
        store = _store_with_workspace()
        _add_entry(store, "e-1", source_colony_id="col-1")
        entry = store.memory_entries["e-1"]
        chain = entry.get("provenance_chain", [])
        assert len(chain) == 1
        item = chain[0]
        assert item["event_type"] == "MemoryEntryCreated"
        assert item["actor_id"] == "col-1"
        assert "Created by colony col-1" in item["detail"]
        assert item["confidence_delta"] is None


class TestProvenanceChainOnConfidenceUpdate:
    def test_memory_confidence_updated_appends_delta(self) -> None:
        store = _store_with_workspace()
        _add_entry(store, "e-1")
        store.apply(MemoryConfidenceUpdated(
            seq=20, timestamp=_NOW, address=f"{_WS}/t-1/col-2",
            entry_id="e-1",
            colony_id="col-2",
            colony_succeeded=True,
            old_alpha=5.0,
            old_beta=5.0,
            new_alpha=6.0,
            new_beta=5.0,
            new_confidence=6.0 / 11.0,
            workspace_id=_WS,
            thread_id="t-1",
            reason="colony_outcome",
        ))
        entry = store.memory_entries["e-1"]
        chain = entry.get("provenance_chain", [])
        assert len(chain) == 2  # created + confidence update
        conf_item = chain[1]
        assert conf_item["event_type"] == "MemoryConfidenceUpdated"
        assert conf_item["actor_id"] == "col-2"
        assert "colony_outcome" in conf_item["detail"]
        assert conf_item["confidence_delta"] is not None
        # old mean = 5/10 = 0.5, new mean = 6/11 ≈ 0.5455
        assert abs(conf_item["confidence_delta"] - (6.0 / 11.0 - 0.5)) < 0.001


class TestProvenanceChainOnMerge:
    def test_memory_entry_merged_updates_target_and_source_chains(self) -> None:
        store = _store_with_workspace()
        _add_entry(store, "e-target")
        _add_entry(store, "e-source")
        store.apply(MemoryEntryMerged(
            seq=30, timestamp=_NOW, address=f"{_WS}/t-1",
            target_id="e-target",
            source_id="e-source",
            merged_content="merged content",
            merged_domains=["testing"],
            merged_from=["e-source"],
            content_strategy="keep_longer",
            similarity=0.95,
            merge_source="dedup",
            workspace_id=_WS,
        ))

        target_chain = store.memory_entries["e-target"].get("provenance_chain", [])
        source_chain = store.memory_entries["e-source"].get("provenance_chain", [])

        # Target gets creation + merge
        assert len(target_chain) == 2
        assert target_chain[1]["event_type"] == "MemoryEntryMerged"
        assert "e-source" in target_chain[1]["detail"]

        # Source gets creation + merge
        assert len(source_chain) == 2
        assert source_chain[1]["event_type"] == "MemoryEntryMerged"
        assert "e-target" in source_chain[1]["detail"]


class TestProvenanceEndpoint:
    def test_provenance_endpoint_returns_chain(self) -> None:
        """Verify provenance_chain is accessible from projections (endpoint is thin wrapper)."""
        store = _store_with_workspace()
        _add_entry(store, "e-1", source_colony_id="col-1")
        store.apply(MemoryConfidenceUpdated(
            seq=20, timestamp=_NOW, address=f"{_WS}/t-1/col-2",
            entry_id="e-1",
            colony_id="col-2",
            colony_succeeded=True,
            old_alpha=5.0, old_beta=5.0,
            new_alpha=6.0, new_beta=5.0,
            new_confidence=6.0 / 11.0,
            workspace_id=_WS,
            thread_id="t-1",
            reason="colony_outcome",
        ))
        entry = store.memory_entries["e-1"]
        chain = entry.get("provenance_chain", [])
        # Simulate endpoint response shape
        response = {"entry_id": "e-1", "chain": chain, "total": len(chain)}
        assert response["total"] == 2
        assert response["chain"][0]["event_type"] == "MemoryEntryCreated"
        assert response["chain"][1]["event_type"] == "MemoryConfidenceUpdated"


class TestProvenanceOperatorAnnotation:
    def test_operator_annotation_appends_provenance_item(self) -> None:
        store = _store_with_workspace()
        _add_entry(store, "e-1")
        store.apply(KnowledgeEntryAnnotated(
            seq=40, timestamp=_NOW, address=f"{_WS}/e-1",
            entry_id="e-1",
            workspace_id=_WS,
            annotation_text="Reviewed and confirmed",
            tag="reviewed",
            actor="operator",
        ))
        chain = store.memory_entries["e-1"].get("provenance_chain", [])
        assert len(chain) == 2  # created + annotation
        ann = chain[1]
        assert ann["event_type"] == "KnowledgeEntryAnnotated"
        assert ann["actor_id"] == "operator"
        assert "[reviewed]" in ann["detail"]

    def test_operator_action_appends_provenance_item(self) -> None:
        store = _store_with_workspace()
        _add_entry(store, "e-1")
        store.apply(KnowledgeEntryOperatorAction(
            seq=50, timestamp=_NOW, address=f"{_WS}/e-1",
            entry_id="e-1",
            workspace_id=_WS,
            action="pin",
            actor="operator",
            reason="important entry",
        ))
        chain = store.memory_entries["e-1"].get("provenance_chain", [])
        assert len(chain) == 2  # created + operator action
        act = chain[1]
        assert act["event_type"] == "KnowledgeEntryOperatorAction"
        assert "pin" in act["detail"]
