"""Tests for MemoryEntryMerged event and dedup handler modification (Wave 33 C4)."""

from __future__ import annotations

from datetime import datetime, timezone

from formicos.core.events import MemoryEntryMerged, MemoryEntryCreated
from formicos.surface.projections import ProjectionStore

_NOW = datetime(2026, 3, 18, tzinfo=timezone.utc)


def _seed_store_with_entries(
    store: ProjectionStore,
    target_content: str = "Target content",
    source_content: str = "Source content",
    target_domains: list[str] | None = None,
    source_domains: list[str] | None = None,
    target_merged_from: list[str] | None = None,
) -> None:
    """Seed a store with two memory entries for merge testing."""
    store.apply(MemoryEntryCreated(
        seq=1, timestamp=_NOW, address="ws-1/t-1",
        workspace_id="ws-1",
        entry={
            "id": "target-1", "entry_type": "skill",
            "status": "verified", "title": "Target",
            "content": target_content,
            "source_colony_id": "col-1", "source_artifact_ids": [],
            "workspace_id": "ws-1", "thread_id": "t-1",
            "conf_alpha": 10.0, "conf_beta": 2.0, "confidence": 0.83,
            "domains": target_domains or ["A", "B"],
            "merged_from": target_merged_from or [],
        },
    ))
    store.apply(MemoryEntryCreated(
        seq=2, timestamp=_NOW, address="ws-1/t-1",
        workspace_id="ws-1",
        entry={
            "id": "source-1", "entry_type": "skill",
            "status": "verified", "title": "Source",
            "content": source_content,
            "source_colony_id": "col-2", "source_artifact_ids": [],
            "workspace_id": "ws-1", "thread_id": "t-1",
            "conf_alpha": 6.0, "conf_beta": 4.0, "confidence": 0.6,
            "domains": source_domains or ["B", "C"],
        },
    ))


class TestMemoryEntryMergedProjection:
    """Projection handler for MemoryEntryMerged."""

    def test_target_updated_source_rejected(self) -> None:
        store = ProjectionStore()
        _seed_store_with_entries(store)

        store.apply(MemoryEntryMerged(
            seq=3, timestamp=_NOW, address="ws-1",
            target_id="target-1", source_id="source-1",
            merged_content="Target content",
            merged_domains=["A", "B", "C"],
            merged_from=["source-1"],
            content_strategy="keep_target",
            similarity=0.99,
            merge_source="dedup",
            workspace_id="ws-1",
        ))

        target = store.memory_entries["target-1"]
        assert target["content"] == "Target content"
        assert set(target["domains"]) == {"A", "B", "C"}
        assert target["merged_from"] == ["source-1"]
        assert target["merge_count"] == 1

        source = store.memory_entries["source-1"]
        assert source["status"] == "rejected"
        assert source["rejection_reason"] == "merged_into:target-1"


class TestContentStrategy:
    """Content selection strategy logic."""

    def test_keep_longer_when_source_bigger(self) -> None:
        """Source content 1.5x target → keep_longer strategy."""
        store = ProjectionStore()
        _seed_store_with_entries(
            store,
            target_content="Short",
            source_content="Much longer source content that exceeds 1.2x",
        )

        store.apply(MemoryEntryMerged(
            seq=3, timestamp=_NOW, address="ws-1",
            target_id="target-1", source_id="source-1",
            merged_content="Much longer source content that exceeds 1.2x",
            merged_domains=["A", "B", "C"],
            merged_from=["source-1"],
            content_strategy="keep_longer",
            similarity=0.99,
            merge_source="dedup",
            workspace_id="ws-1",
        ))

        assert store.memory_entries["target-1"]["content"] == (
            "Much longer source content that exceeds 1.2x"
        )

    def test_keep_target_when_similar_size(self) -> None:
        """Source content 0.8x target → keep_target strategy."""
        store = ProjectionStore()
        _seed_store_with_entries(
            store,
            target_content="Target content of moderate length",
            source_content="Source content similar",
        )

        store.apply(MemoryEntryMerged(
            seq=3, timestamp=_NOW, address="ws-1",
            target_id="target-1", source_id="source-1",
            merged_content="Target content of moderate length",
            merged_domains=["A", "B"],
            merged_from=["source-1"],
            content_strategy="keep_target",
            similarity=0.95,
            merge_source="dedup",
            workspace_id="ws-1",
        ))

        assert store.memory_entries["target-1"]["content"] == (
            "Target content of moderate length"
        )


class TestDomainsUnion:
    """Domain tag union on merge."""

    def test_domains_unioned(self) -> None:
        store = ProjectionStore()
        _seed_store_with_entries(
            store,
            target_domains=["A", "B"],
            source_domains=["B", "C"],
        )

        store.apply(MemoryEntryMerged(
            seq=3, timestamp=_NOW, address="ws-1",
            target_id="target-1", source_id="source-1",
            merged_content="Content",
            merged_domains=["A", "B", "C"],
            merged_from=["source-1"],
            content_strategy="keep_target",
            similarity=0.98,
            merge_source="dedup",
            workspace_id="ws-1",
        ))

        assert set(store.memory_entries["target-1"]["domains"]) == {"A", "B", "C"}


class TestMergedFromAccumulation:
    """merged_from provenance chain accumulation."""

    def test_chain_accumulates(self) -> None:
        """Target already has [X], source is Y → merged_from = [X, Y]."""
        store = ProjectionStore()
        _seed_store_with_entries(
            store,
            target_merged_from=["prev-entry"],
        )

        store.apply(MemoryEntryMerged(
            seq=3, timestamp=_NOW, address="ws-1",
            target_id="target-1", source_id="source-1",
            merged_content="Content",
            merged_domains=["A", "B", "C"],
            merged_from=["prev-entry", "source-1"],
            content_strategy="keep_target",
            similarity=0.98,
            merge_source="dedup",
            workspace_id="ws-1",
        ))

        assert store.memory_entries["target-1"]["merged_from"] == [
            "prev-entry", "source-1",
        ]


class TestMergeEventSerialization:
    """MemoryEntryMerged serialization/deserialization."""

    def test_roundtrip(self) -> None:
        from formicos.core.events import deserialize, serialize

        event = MemoryEntryMerged(
            seq=1, timestamp=_NOW, address="ws-1",
            target_id="t-1", source_id="s-1",
            merged_content="content",
            merged_domains=["d1", "d2"],
            merged_from=["s-1"],
            content_strategy="keep_target",
            similarity=0.95,
            merge_source="dedup",
            workspace_id="ws-1",
        )
        json_str = serialize(event)
        restored = deserialize(json_str)
        assert isinstance(restored, MemoryEntryMerged)
        assert restored.target_id == "t-1"
        assert restored.source_id == "s-1"
        assert restored.content_strategy == "keep_target"
