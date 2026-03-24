"""Tests for the GET /api/v1/skills REST endpoint and get_skill_bank_detail()."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from formicos.core.types import VectorSearchHit
from formicos.surface.view_state import get_skill_bank_detail


def _make_hit(
    doc_id: str,
    content: str,
    confidence: float = 0.5,
    source_colony: str = "col-1",
    algorithm_version: str = "v1",
    extracted_at: str = "2026-03-13T12:00:00Z",
) -> VectorSearchHit:
    return VectorSearchHit(
        id=doc_id,
        content=content,
        score=0.9,
        metadata={
            "confidence": confidence,
            "source_colony": source_colony,
            "algorithm_version": algorithm_version,
            "extracted_at": extracted_at,
        },
    )


@pytest.fixture()
def mock_vector_port() -> AsyncMock:
    port = AsyncMock()
    port._default_collection = "skill_bank_v2"
    port.search = AsyncMock(return_value=[
        _make_hit("s1", "Use dependency injection for testability", 0.8, "col-a"),
        _make_hit("s2", "Always write unit tests for edge cases", 0.4, "col-b"),
        _make_hit("s3", "Prefer composition over inheritance", 0.9, "col-a", "v2"),
    ])
    return port


@pytest.mark.asyncio()
async def test_returns_correct_shape(mock_vector_port: AsyncMock) -> None:
    result = await get_skill_bank_detail(mock_vector_port)
    assert len(result) == 3
    entry = result[0]
    assert "id" in entry
    assert "text_preview" in entry
    assert "confidence" in entry
    assert "algorithm_version" in entry
    assert "extracted_at" in entry
    assert "source_colony" in entry


@pytest.mark.asyncio()
async def test_sort_by_confidence(mock_vector_port: AsyncMock) -> None:
    result = await get_skill_bank_detail(mock_vector_port, sort_by="confidence")
    confidences = [e["confidence"] for e in result]
    assert confidences == sorted(confidences, reverse=True)


@pytest.mark.asyncio()
async def test_sort_by_freshness(mock_vector_port: AsyncMock) -> None:
    port = AsyncMock()
    port.search = AsyncMock(return_value=[
        _make_hit("s1", "Old skill", extracted_at="2026-03-10T00:00:00Z"),
        _make_hit("s2", "New skill", extracted_at="2026-03-13T00:00:00Z"),
        _make_hit("s3", "Mid skill", extracted_at="2026-03-12T00:00:00Z"),
    ])
    result = await get_skill_bank_detail(port, sort_by="freshness")
    dates = [e["extracted_at"] for e in result]
    assert dates == sorted(dates, reverse=True)


@pytest.mark.asyncio()
async def test_respects_limit(mock_vector_port: AsyncMock) -> None:
    result = await get_skill_bank_detail(mock_vector_port, limit=2)
    assert len(result) == 2


@pytest.mark.asyncio()
async def test_handles_none_vector_port() -> None:
    result = await get_skill_bank_detail(None)
    assert result == []


@pytest.mark.asyncio()
async def test_handles_empty_collection() -> None:
    port = AsyncMock()
    port.search = AsyncMock(return_value=[])
    result = await get_skill_bank_detail(port)
    assert result == []


@pytest.mark.asyncio()
async def test_text_preview_truncated() -> None:
    long_content = "x" * 200
    port = AsyncMock()
    port.search = AsyncMock(return_value=[
        _make_hit("s1", long_content),
    ])
    result = await get_skill_bank_detail(port)
    assert len(result[0]["text_preview"]) == 100


@pytest.mark.asyncio()
async def test_passes_collection_and_top_k(mock_vector_port: AsyncMock) -> None:
    await get_skill_bank_detail(mock_vector_port, limit=25)
    mock_vector_port.search.assert_called_once_with(
        collection="skill_bank_v2",
        query="skill knowledge technique pattern",
        top_k=25,
    )
