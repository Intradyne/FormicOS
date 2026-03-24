from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from formicos.surface.knowledge_catalog import KnowledgeCatalog


@pytest.mark.anyio()
async def test_get_by_id_returns_full_content_for_institutional_entry() -> None:
    projections = SimpleNamespace(memory_entries={
        "mem-1": {
            "id": "mem-1",
            "entry_type": "skill",
            "status": "verified",
            "confidence": 0.8,
            "title": "Use retries on flaky I/O",
            "summary": "Retry transient operations.",
            "content": "full institutional content" * 40,
            "source_colony_id": "colony-1",
            "source_artifact_ids": ["art-1"],
            "domains": ["python"],
            "tool_refs": ["http_fetch"],
            "created_at": "2026-03-17T00:00:00Z",
            "polarity": "positive",
        },
    })
    catalog = KnowledgeCatalog(
        memory_store=None,
        vector_port=None,
        skill_collection="skill_bank_v2",
        projections=projections,
    )

    item = await catalog.get_by_id("mem-1")

    assert item is not None
    assert item["id"] == "mem-1"
    assert item["content"].startswith("full institutional content")
    assert len(item["content"]) > len(item["content_preview"])


@pytest.mark.anyio()
async def test_get_by_id_returns_full_content_for_legacy_entry() -> None:
    hit = SimpleNamespace(
        id="legacy-1",
        content="legacy skill body" * 50,
        score=0.9,
        metadata={
            "technique": "Legacy technique",
            "when_to_use": "When older patterns apply",
            "confidence": 0.7,
            "source_colony_id": "colony-legacy",
            "extracted_at": "2026-03-17T00:00:00Z",
        },
    )
    vector_port = AsyncMock()
    vector_port.search = AsyncMock(return_value=[hit])
    catalog = KnowledgeCatalog(
        memory_store=None,
        vector_port=vector_port,
        skill_collection="skill_bank_v2",
        projections=None,
    )

    item = await catalog.get_by_id("legacy-1")

    assert item is not None
    assert item["id"] == "legacy-1"
    assert item["content"].startswith("legacy skill body")
    assert len(item["content"]) > len(item["content_preview"])


@pytest.mark.anyio()
async def test_list_all_filters_by_source_colony_id_across_sources() -> None:
    projections = SimpleNamespace(memory_entries={
        "mem-1": {
            "id": "mem-1",
            "entry_type": "skill",
            "status": "verified",
            "confidence": 0.8,
            "title": "Institutional",
            "summary": "Institutional summary",
            "content": "institutional content",
            "source_colony_id": "colony-1",
            "source_artifact_ids": [],
            "domains": [],
            "tool_refs": [],
            "created_at": "2026-03-17T00:00:00Z",
            "polarity": "positive",
            "workspace_id": "ws-1",
        },
        "mem-2": {
            "id": "mem-2",
            "entry_type": "experience",
            "status": "verified",
            "confidence": 0.7,
            "title": "Other institutional",
            "summary": "Other summary",
            "content": "other content",
            "source_colony_id": "colony-2",
            "source_artifact_ids": [],
            "domains": [],
            "tool_refs": [],
            "created_at": "2026-03-16T00:00:00Z",
            "polarity": "negative",
            "workspace_id": "ws-1",
        },
    })
    vector_port = AsyncMock()
    vector_port.search = AsyncMock(return_value=[
        SimpleNamespace(
            id="legacy-1",
            content="legacy one",
            score=0.8,
            metadata={"source_colony_id": "colony-1", "confidence": 0.6},
        ),
        SimpleNamespace(
            id="legacy-2",
            content="legacy two",
            score=0.5,
            metadata={"source_colony_id": "colony-2", "confidence": 0.4},
        ),
    ])
    catalog = KnowledgeCatalog(
        memory_store=None,
        vector_port=vector_port,
        skill_collection="skill_bank_v2",
        projections=projections,
    )

    items, total = await catalog.list_all(
        workspace_id="ws-1",
        source_colony_id="colony-1",
        limit=10,
    )

    assert total == 2
    assert {item["id"] for item in items} == {"mem-1", "legacy-1"}
    assert all(item["source_colony_id"] == "colony-1" for item in items)


@pytest.mark.anyio()
async def test_search_filters_by_source_colony_id_across_sources() -> None:
    memory_store = AsyncMock()
    memory_store.search = AsyncMock(return_value=[
        {
            "id": "mem-1",
            "entry_type": "skill",
            "status": "verified",
            "confidence": 0.9,
            "title": "Institutional",
            "summary": "Institutional summary",
            "content": "institutional content",
            "source_colony_id": "colony-1",
            "source_artifact_ids": [],
            "domains": [],
            "tool_refs": [],
            "created_at": "2026-03-17T00:00:00Z",
            "polarity": "positive",
            "score": 0.9,
        },
        {
            "id": "mem-2",
            "entry_type": "skill",
            "status": "verified",
            "confidence": 0.8,
            "title": "Other institutional",
            "summary": "Other summary",
            "content": "other content",
            "source_colony_id": "colony-2",
            "source_artifact_ids": [],
            "domains": [],
            "tool_refs": [],
            "created_at": "2026-03-16T00:00:00Z",
            "polarity": "positive",
            "score": 0.95,
        },
    ])
    vector_port = AsyncMock()
    vector_port.search = AsyncMock(return_value=[
        SimpleNamespace(
            id="legacy-1",
            content="legacy one",
            score=0.85,
            metadata={"source_colony_id": "colony-1", "confidence": 0.6},
        ),
        SimpleNamespace(
            id="legacy-2",
            content="legacy two",
            score=0.95,
            metadata={"source_colony_id": "colony-2", "confidence": 0.5},
        ),
    ])
    catalog = KnowledgeCatalog(
        memory_store=memory_store,
        vector_port=vector_port,
        skill_collection="skill_bank_v2",
        projections=None,
    )

    items = await catalog.search("retry", source_colony_id="colony-1", top_k=10)

    assert {item["id"] for item in items} == {"mem-1", "legacy-1"}
    assert all(item["source_colony_id"] == "colony-1" for item in items)
