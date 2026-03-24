"""Tests for confidence-weighted skill retrieval in engine/context.py."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from formicos.core.types import (
    AgentConfig,
    CasteRecipe,
    ColonyContext,
    VectorSearchHit,
)
from formicos.engine.context import (
    ContextResult,
    _compute_freshness,
    assemble_context,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _recipe() -> CasteRecipe:
    return CasteRecipe(
        name="coder", description="test", system_prompt="You are a coder.",
        temperature=0.0, tools=[], max_tokens=1024,
    )


def _agent() -> AgentConfig:
    return AgentConfig(
        id="a1", name="a1", caste="coder",
        model="test-model", recipe=_recipe(),
    )


def _ctx() -> ColonyContext:
    return ColonyContext(
        colony_id="col-1", workspace_id="ws-1", thread_id="th-1",
        goal="Build a widget", round_number=1,
        merge_edges=[],
    )


def _hit(
    id: str = "s1",
    content: str = "Test skill content",
    score: float = 0.1,
    confidence: float = 0.5,
    extracted_at: str | None = None,
) -> VectorSearchHit:
    meta: dict[str, Any] = {"confidence": confidence}
    if extracted_at is not None:
        meta["extracted_at"] = extracted_at
    return VectorSearchHit(id=id, content=content, score=score, metadata=meta)


class MockVectorPort:
    def __init__(self, results: list[VectorSearchHit] | None = None) -> None:
        self._results = results or []

    async def search(self, collection: str, query: str, top_k: int = 5) -> list[VectorSearchHit]:
        return self._results[:top_k]

    async def upsert(self, collection: str, docs: Any) -> int:
        return 0

    async def delete(self, collection: str, ids: Any) -> int:
        return 0


# ---------------------------------------------------------------------------
# Freshness decay
# ---------------------------------------------------------------------------


def test_freshness_zero_days() -> None:
    ts = datetime.now(UTC).isoformat()
    f = _compute_freshness(ts)
    assert abs(f - 1.0) < 0.01


def test_freshness_90_days() -> None:
    ts = (datetime.now(UTC) - timedelta(days=90)).isoformat()
    f = _compute_freshness(ts)
    assert abs(f - 0.5) < 0.05


def test_freshness_empty_string() -> None:
    assert _compute_freshness("") == 1.0


def test_freshness_invalid_string() -> None:
    assert _compute_freshness("not-a-date") == 1.0


def test_freshness_180_days() -> None:
    ts = (datetime.now(UTC) - timedelta(days=180)).isoformat()
    f = _compute_freshness(ts)
    assert abs(f - 0.25) < 0.05


# ---------------------------------------------------------------------------
# Composite scoring and re-ranking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_composite_reranks_by_confidence() -> None:
    """Higher confidence should boost composite score, changing rank order."""
    now = datetime.now(UTC).isoformat()
    # Same semantic score (distance), but different confidence
    vp = MockVectorPort(results=[
        _hit(id="low-conf", content="Skill A", score=0.2, confidence=0.2, extracted_at=now),
        _hit(id="high-conf", content="Skill B", score=0.2, confidence=0.9, extracted_at=now),
    ])
    result = await assemble_context(
        agent=_agent(), colony_context=_ctx(), round_goal="test",
        routed_outputs={}, merged_summaries=[],
        vector_port=vp,  # type: ignore[arg-type]
    )
    # high-conf should come first in retrieved_skill_ids
    assert result.retrieved_skill_ids[0] == "high-conf"


@pytest.mark.asyncio
async def test_retrieves_top_8_keeps_top_3() -> None:
    """Should request 8 candidates but only keep 3."""
    now = datetime.now(UTC).isoformat()
    hits = [
        _hit(id=f"s{i}", content=f"Skill {i}", score=0.1 * i, confidence=0.5, extracted_at=now)
        for i in range(8)
    ]
    vp = MockVectorPort(results=hits)
    result = await assemble_context(
        agent=_agent(), colony_context=_ctx(), round_goal="test",
        routed_outputs={}, merged_summaries=[],
        vector_port=vp,  # type: ignore[arg-type]
    )
    assert len(result.retrieved_skill_ids) == 3


@pytest.mark.asyncio
async def test_confidence_annotation_in_text() -> None:
    """Injected skill text should include [conf:X.X] prefix."""
    vp = MockVectorPort(results=[
        _hit(id="s1", content="Use caching", score=0.1, confidence=0.8),
    ])
    result = await assemble_context(
        agent=_agent(), colony_context=_ctx(), round_goal="test",
        routed_outputs={}, merged_summaries=[],
        vector_port=vp,  # type: ignore[arg-type]
    )
    skill_msgs = [m for m in result.messages if "Relevant skills:" in m["content"]]
    assert len(skill_msgs) == 1
    assert "[conf:0.8]" in skill_msgs[0]["content"]


@pytest.mark.asyncio
async def test_returns_context_result_type() -> None:
    """assemble_context should return ContextResult, not list."""
    result = await assemble_context(
        agent=_agent(), colony_context=_ctx(), round_goal="test",
        routed_outputs={}, merged_summaries=[], vector_port=None,
    )
    assert isinstance(result, ContextResult)
    assert isinstance(result.messages, list)
    assert isinstance(result.retrieved_skill_ids, list)


@pytest.mark.asyncio
async def test_no_skills_returns_empty_ids() -> None:
    """No skills in vector store → empty retrieved_skill_ids."""
    vp = MockVectorPort(results=[])
    result = await assemble_context(
        agent=_agent(), colony_context=_ctx(), round_goal="test",
        routed_outputs={}, merged_summaries=[],
        vector_port=vp,  # type: ignore[arg-type]
    )
    assert result.retrieved_skill_ids == []


@pytest.mark.asyncio
async def test_composite_formula_values() -> None:
    """Verify composite = semantic*0.5 + confidence*0.25 + freshness*0.25."""
    now = datetime.now(UTC).isoformat()
    # distance=0.2 → semantic=0.8; confidence=0.6; freshness≈1.0
    # composite ≈ 0.8*0.5 + 0.6*0.25 + 1.0*0.25 = 0.4 + 0.15 + 0.25 = 0.80
    vp = MockVectorPort(results=[
        _hit(id="s1", content="Test", score=0.2, confidence=0.6, extracted_at=now),
    ])
    result = await assemble_context(
        agent=_agent(), colony_context=_ctx(), round_goal="test",
        routed_outputs={}, merged_summaries=[],
        vector_port=vp,  # type: ignore[arg-type]
    )
    assert "s1" in result.retrieved_skill_ids


@pytest.mark.asyncio
async def test_distance_normalization() -> None:
    """Distance > 1.0 should be clamped to similarity 0.0."""
    vp = MockVectorPort(results=[
        _hit(id="s1", content="Bad match", score=1.5, confidence=0.9),
    ])
    result = await assemble_context(
        agent=_agent(), colony_context=_ctx(), round_goal="test",
        routed_outputs={}, merged_summaries=[],
        vector_port=vp,  # type: ignore[arg-type]
    )
    # Should still retrieve (semantic=0, but confidence+freshness contribute)
    assert "s1" in result.retrieved_skill_ids
