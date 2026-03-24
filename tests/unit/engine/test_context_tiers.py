"""Tests for tiered context assembly in engine/context.py (ADR-008)."""

from __future__ import annotations

from typing import Any

import pytest

from formicos.core.types import (
    AgentConfig,
    CasteRecipe,
    ColonyContext,
    VectorSearchHit,
)
from formicos.engine.context import (
    DEFAULT_TIER_BUDGETS,
    TierBudgets,
    _MIN_KNOWLEDGE_SIMILARITY,
    _compact_summary,
    _split_sentences,
    _truncate,
    _truncate_preserve_edges,
    assemble_context,
    estimate_tokens,
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


def _ctx(prev_summary: str | None = None) -> ColonyContext:
    return ColonyContext(
        colony_id="col-1", workspace_id="ws-1", thread_id="th-1",
        goal="Build a widget", round_number=1,
        merge_edges=[], prev_round_summary=prev_summary,
    )


class MockVectorPort:
    def __init__(self, results: list[VectorSearchHit] | None = None) -> None:
        self._results = results or []

    async def search(self, collection: str, query: str, top_k: int = 5) -> list[VectorSearchHit]:
        return self._results

    async def upsert(self, collection: str, docs: Any) -> int:
        return 0

    async def delete(self, collection: str, ids: Any) -> int:
        return 0


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------


def test_estimate_tokens() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 400) == 100


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------


def test_truncate_short_text_unchanged() -> None:
    assert _truncate("hello", 100) == "hello"


def test_truncate_long_text_cut() -> None:
    text = "x" * 2000  # 500 tokens
    result = _truncate(text, 100)
    assert len(result) == 400  # 100 * 4


def test_truncate_preserve_edges_short() -> None:
    assert _truncate_preserve_edges("hello", 100) == "hello"


def test_truncate_preserve_edges_long() -> None:
    text = "A" * 1000 + "B" * 1000  # 500 tokens total
    result = _truncate_preserve_edges(text, 100)  # 400 chars budget
    assert result.startswith("A")
    assert result.endswith("B")
    assert "[... truncated ...]" in result


# ---------------------------------------------------------------------------
# Sentence splitting
# ---------------------------------------------------------------------------


def test_split_sentences_basic() -> None:
    text = "First sentence. Second sentence. Third one!"
    parts = _split_sentences(text)
    assert len(parts) == 3


def test_split_sentences_newlines() -> None:
    text = "Line one\nLine two\nLine three"
    parts = _split_sentences(text)
    assert len(parts) == 3


def test_split_sentences_empty() -> None:
    assert _split_sentences("") == []


# ---------------------------------------------------------------------------
# Compaction
# ---------------------------------------------------------------------------


def test_compact_summary_preserves_goal_relevant() -> None:
    text = (
        "The widget module was initialized. "
        "Database connections were established. "
        "The widget passed all tests successfully. "
        "Logging was configured for production."
    )
    result = _compact_summary(text, "widget tests", budget_tokens=50)
    # Should prioritize sentences mentioning "widget" and "tests"
    assert "widget" in result.lower()


def test_compact_summary_within_budget() -> None:
    text = "Sentence one. " * 50  # very long
    result = _compact_summary(text, "goal", budget_tokens=20)
    assert estimate_tokens(result) <= 20


def test_compact_summary_preserves_order() -> None:
    text = "First relevant goal sentence. Middle unrelated noise. Last relevant goal ending."
    result = _compact_summary(text, "goal sentence ending", budget_tokens=100)
    # If both first and last are included, first should come before last
    if "First" in result and "Last" in result:
        assert result.index("First") < result.index("Last")


# ---------------------------------------------------------------------------
# Tier budgets
# ---------------------------------------------------------------------------


def test_default_tier_budgets_values() -> None:
    b = DEFAULT_TIER_BUDGETS
    assert b.goal == 500
    assert b.routed_outputs == 1500
    assert b.max_per_source == 500
    assert b.skill_bank == 800
    assert b.compaction_threshold == 500


def test_custom_tier_budgets() -> None:
    b = TierBudgets(goal=100, routed_outputs=200)
    assert b.goal == 100
    assert b.routed_outputs == 200
    assert b.skill_bank == 800  # default


# ---------------------------------------------------------------------------
# Context assembly integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assemble_basic_structure() -> None:
    result = await assemble_context(
        agent=_agent(),
        colony_context=_ctx(),
        round_goal="Build a widget",
        routed_outputs={},
        merged_summaries=[],
        vector_port=None,
    )
    assert result.messages[0]["role"] == "system"
    assert "Round goal:" in result.messages[1]["content"]
    assert result.retrieved_skill_ids == []


@pytest.mark.asyncio
async def test_assemble_includes_routed_outputs() -> None:
    result = await assemble_context(
        agent=_agent(),
        colony_context=_ctx(),
        round_goal="Build a widget",
        routed_outputs={"coder-0": "wrote the code", "reviewer-1": "looks good"},
        merged_summaries=[],
        vector_port=None,
    )
    contents = [m["content"] for m in result.messages]
    assert any("[coder-0]" in c for c in contents)
    assert any("[reviewer-1]" in c for c in contents)


@pytest.mark.asyncio
async def test_assemble_routed_per_source_cap() -> None:
    """Per-source cap should truncate verbose agent output."""
    big_output = "x" * 10000  # way over 500 token cap
    budgets = TierBudgets(max_per_source=50)  # 50 tokens = 200 chars
    result = await assemble_context(
        agent=_agent(),
        colony_context=_ctx(),
        round_goal="goal",
        routed_outputs={"verbose-agent": big_output},
        merged_summaries=[],
        vector_port=None,
        tier_budgets=budgets,
    )
    routed = [m for m in result.messages if "[verbose-agent]" in m["content"]]
    assert len(routed) == 1
    assert "[... truncated ...]" in routed[0]["content"]


@pytest.mark.asyncio
async def test_assemble_prev_round_compacted() -> None:
    """Previous round summary over threshold should be compacted."""
    long_prev = "The widget module works great. " * 100  # way over 500 tokens
    budgets = TierBudgets(compaction_threshold=50, prev_round_summary=100)
    result = await assemble_context(
        agent=_agent(),
        colony_context=_ctx(prev_summary=long_prev),
        round_goal="widget improvements",
        routed_outputs={},
        merged_summaries=[],
        vector_port=None,
        tier_budgets=budgets,
    )
    prev_msgs = [m for m in result.messages if "Previous round:" in m["content"]]
    assert len(prev_msgs) == 1
    # Compacted text should be much shorter than original
    assert len(prev_msgs[0]["content"]) < len(long_prev)


@pytest.mark.asyncio
async def test_assemble_skill_bank_collection() -> None:
    """Skill bank should query 'skill_bank' collection, not workspace_id."""
    search_calls: list[str] = []

    class TrackingVP:
        async def search(self, collection: str, query: str, top_k: int = 5) -> list[VectorSearchHit]:
            search_calls.append(collection)
            return []

        async def upsert(self, collection: str, docs: Any) -> int:
            return 0

        async def delete(self, collection: str, ids: Any) -> int:
            return 0

    await assemble_context(
        agent=_agent(),
        colony_context=_ctx(),
        round_goal="test",
        routed_outputs={},
        merged_summaries=[],
        vector_port=TrackingVP(),  # type: ignore[arg-type]
    )
    assert "skill_bank_v2" in search_calls


@pytest.mark.asyncio
async def test_assemble_skill_results_included() -> None:
    """Skill bank results should appear in the message list with confidence annotation."""
    vp = MockVectorPort(results=[
        VectorSearchHit(
            id="s1", content="Use iterative decomposition", score=0.1,
            metadata={"confidence": 0.7},
        ),
    ])
    result = await assemble_context(
        agent=_agent(),
        colony_context=_ctx(),
        round_goal="test",
        routed_outputs={},
        merged_summaries=[],
        vector_port=vp,  # type: ignore[arg-type]
    )
    contents = " ".join(m["content"] for m in result.messages)
    assert "iterative decomposition" in contents
    assert "[conf:0.7]" in contents
    assert result.retrieved_skill_ids == ["s1"]


@pytest.mark.asyncio
async def test_assemble_merge_summaries() -> None:
    result = await assemble_context(
        agent=_agent(),
        colony_context=_ctx(),
        round_goal="goal",
        routed_outputs={},
        merged_summaries=["Colony A found X", "Colony B found Y"],
        vector_port=None,
    )
    contents = [m["content"] for m in result.messages]
    assert any("Colony A found X" in c for c in contents)
    assert any("Colony B found Y" in c for c in contents)


# ---------------------------------------------------------------------------
# RetrievalPipeline + KG augmentation (Wave 13 B-T3)
# ---------------------------------------------------------------------------

from formicos.engine.context import RetrievalPipeline  # noqa: E402


class MockKGAdapter:
    """Minimal KG adapter mock for retrieval tests."""

    def __init__(
        self,
        entities: list[dict[str, Any]] | None = None,
        neighbors: list[dict[str, Any]] | None = None,
    ) -> None:
        self._entities = entities or []
        self._neighbors = neighbors or []

    async def search_entities(
        self, text: str, workspace_id: str,
    ) -> list[dict[str, Any]]:
        return self._entities

    async def get_neighbors(
        self, entity_id: str, depth: int = 1, workspace_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._neighbors


@pytest.mark.asyncio
async def test_retrieval_pipeline_returns_vectors_and_triples() -> None:
    """RetrievalPipeline should return both vector hits and KG triples."""
    skill = VectorSearchHit(
        id="s1", content="FastAPI routing", score=0.2,
        metadata={"confidence": 0.9, "extracted_at": ""},
    )
    vector_port = MockVectorPort([skill])
    kg = MockKGAdapter(
        entities=[{"id": "e1", "name": "FastAPI", "entity_type": "MODULE"}],
        neighbors=[{
            "id": "edge1", "subject": "FastAPI", "predicate": "DEPENDS_ON",
            "object": "Starlette", "from_node": "e1", "to_node": "e2",
            "confidence": 0.9,
        }],
    )

    pipeline = RetrievalPipeline(vector_port, kg)  # type: ignore[arg-type]
    hits, triples = await pipeline.search("ws-1", "FastAPI routing")

    assert len(hits) == 1
    assert hits[0].id == "s1"
    assert len(triples) == 1
    assert triples[0]["subject"] == "FastAPI"
    assert triples[0]["predicate"] == "DEPENDS_ON"


@pytest.mark.asyncio
async def test_retrieval_pipeline_no_kg_entities() -> None:
    """Pipeline should return empty triples when no entities match."""
    skill = VectorSearchHit(
        id="s1", content="Testing", score=0.3,
        metadata={"confidence": 0.5},
    )
    vector_port = MockVectorPort([skill])
    kg = MockKGAdapter(entities=[], neighbors=[])

    pipeline = RetrievalPipeline(vector_port, kg)  # type: ignore[arg-type]
    hits, triples = await pipeline.search("ws-1", "testing stuff")

    assert len(hits) == 1
    assert len(triples) == 0


@pytest.mark.asyncio
async def test_assemble_context_with_kg_adapter() -> None:
    """assemble_context should include KG relationship context in skill text."""
    skill = VectorSearchHit(
        id="s1", content="FastAPI dependency injection pattern", score=0.2,
        metadata={"confidence": 0.8, "extracted_at": ""},
    )
    vector_port = MockVectorPort([skill])
    kg = MockKGAdapter(
        entities=[{"id": "e1", "name": "FastAPI", "entity_type": "MODULE"}],
        neighbors=[{
            "id": "edge1", "subject": "FastAPI", "predicate": "DEPENDS_ON",
            "object": "Starlette", "from_node": "e1", "to_node": "e2",
            "confidence": 0.9,
        }],
    )

    result = await assemble_context(
        agent=_agent(),
        colony_context=_ctx(),
        round_goal="Fix FastAPI routes",
        routed_outputs={},
        merged_summaries=[],
        vector_port=vector_port,  # type: ignore[arg-type]
        kg_adapter=kg,
    )

    contents = [m["content"] for m in result.messages]
    skill_msg = [c for c in contents if "Relevant skills" in c]
    assert len(skill_msg) == 1
    assert "Related knowledge:" in skill_msg[0]
    assert "FastAPI DEPENDS_ON Starlette" in skill_msg[0]


@pytest.mark.asyncio
async def test_assemble_context_without_kg_adapter() -> None:
    """assemble_context without kg_adapter should still work (backward-compatible)."""
    skill = VectorSearchHit(
        id="s1", content="Some pattern", score=0.2,
        metadata={"confidence": 0.7},
    )
    vector_port = MockVectorPort([skill])

    result = await assemble_context(
        agent=_agent(),
        colony_context=_ctx(),
        round_goal="Build something",
        routed_outputs={},
        merged_summaries=[],
        vector_port=vector_port,  # type: ignore[arg-type]
    )

    contents = [m["content"] for m in result.messages]
    skill_msg = [c for c in contents if "Relevant skills" in c]
    assert len(skill_msg) == 1
    assert "Related knowledge:" not in skill_msg[0]


@pytest.mark.asyncio
async def test_assemble_context_kg_adapter_failure_graceful() -> None:
    """If KG adapter raises, context assembly should still succeed."""

    class FailingKG:
        async def search_entities(self, **_: Any) -> list[Any]:
            raise ConnectionError("KG down")

        async def get_neighbors(self, **_: Any) -> list[Any]:
            return []

    skill = VectorSearchHit(
        id="s1", content="Pattern", score=0.2,
        metadata={"confidence": 0.6},
    )
    vector_port = MockVectorPort([skill])

    result = await assemble_context(
        agent=_agent(),
        colony_context=_ctx(),
        round_goal="Build it",
        routed_outputs={},
        merged_summaries=[],
        vector_port=vector_port,  # type: ignore[arg-type]
        kg_adapter=FailingKG(),
    )

    # Should still have skills, just no KG context
    contents = [m["content"] for m in result.messages]
    skill_msg = [c for c in contents if "Relevant skills" in c]
    assert len(skill_msg) == 1


# ---------------------------------------------------------------------------
# Wave 55.5: Semantic injection gate
# ---------------------------------------------------------------------------


def _make_knowledge_item(
    entry_id: str, title: str, score: float,
) -> dict[str, Any]:
    """Create a minimal knowledge item dict for testing."""
    return {
        "id": entry_id,
        "source_system": "institutional_memory",
        "canonical_type": "skill",
        "status": "candidate",
        "title": title,
        "content_preview": f"Content for {title}",
        "confidence": 0.5,
        "score": score,
    }


@pytest.mark.asyncio
async def test_knowledge_gate_filters_low_similarity() -> None:
    """Entries below _MIN_KNOWLEDGE_SIMILARITY are not injected."""
    items = [
        _make_knowledge_item("e1", "High relevance", 0.70),
        _make_knowledge_item("e2", "Below threshold", 0.30),
        _make_knowledge_item("e3", "Also below", 0.10),
    ]
    result = await assemble_context(
        agent=_agent(),
        colony_context=_ctx(),
        round_goal="Build a rate limiter",
        routed_outputs={},
        merged_summaries=[],
        vector_port=None,
        knowledge_items=items,
    )
    contents = " ".join(m["content"] for m in result.messages)
    assert "High relevance" in contents
    assert "Below threshold" not in contents
    assert "Also below" not in contents
    # Only the high-relevance entry should be in access items
    assert len(result.knowledge_items_used) == 1
    assert result.knowledge_items_used[0].id == "e1"


@pytest.mark.asyncio
async def test_knowledge_gate_passes_above_threshold() -> None:
    """Entries at or above _MIN_KNOWLEDGE_SIMILARITY are injected."""
    items = [
        _make_knowledge_item("e1", "Exact threshold", 0.50),
        _make_knowledge_item("e2", "Well above", 0.90),
    ]
    result = await assemble_context(
        agent=_agent(),
        colony_context=_ctx(),
        round_goal="Build something",
        routed_outputs={},
        merged_summaries=[],
        vector_port=None,
        knowledge_items=items,
    )
    contents = " ".join(m["content"] for m in result.messages)
    assert "Exact threshold" in contents
    assert "Well above" in contents
    assert len(result.knowledge_items_used) == 2


@pytest.mark.asyncio
async def test_knowledge_gate_all_filtered_no_header() -> None:
    """When all entries are below threshold, no System Knowledge block."""
    items = [
        _make_knowledge_item("e1", "Irrelevant A", 0.20),
        _make_knowledge_item("e2", "Irrelevant B", 0.30),
    ]
    result = await assemble_context(
        agent=_agent(),
        colony_context=_ctx(),
        round_goal="Build a rate limiter",
        routed_outputs={},
        merged_summaries=[],
        vector_port=None,
        knowledge_items=items,
    )
    contents = " ".join(m["content"] for m in result.messages)
    assert "[System Knowledge]" not in contents
    assert "[Available Knowledge]" not in contents
    assert len(result.knowledge_items_used) == 0


# ---------------------------------------------------------------------------
# Wave 58: Progressive disclosure (index-only format)
# ---------------------------------------------------------------------------


def _make_knowledge_item_full(
    entry_id: str,
    title: str,
    similarity: float,
    *,
    confidence: float = 0.72,
    status: str = "verified",
    canonical_type: str = "skill",
    sub_type: str = "technique",
    summary: str = "",
    content_preview: str = "",
) -> dict[str, Any]:
    """Create a knowledge item dict with all fields used by index format."""
    return {
        "id": entry_id,
        "source_system": "institutional_memory",
        "canonical_type": canonical_type,
        "status": status,
        "title": title,
        "summary": summary or f"Summary of {title}",
        "content_preview": content_preview or f"Full content of {title} " * 10,
        "confidence": confidence,
        "score": similarity,
        "similarity": similarity,
        "sub_type": sub_type,
    }


@pytest.mark.asyncio
async def test_index_injection_format() -> None:
    """Wave 58: injected knowledge uses index-only format with header."""
    items = [
        _make_knowledge_item_full("e1", "CSV Patterns", 0.65),
        _make_knowledge_item_full("e2", "Auth Middleware", 0.60),
        _make_knowledge_item_full("e3", "Rate Limiter", 0.58),
    ]
    result = await assemble_context(
        agent=_agent(),
        colony_context=_ctx(),
        round_goal="fix our CSV parser",
        routed_outputs={},
        merged_summaries=[],
        vector_port=None,
        knowledge_items=items,
    )
    knowledge_msg = [
        m for m in result.messages
        if "[Available Knowledge]" in m.get("content", "")
    ]
    assert len(knowledge_msg) == 1
    content = knowledge_msg[0]["content"]
    # Wave 59.5: header no longer includes passive tool hint
    assert "[Available Knowledge]" in content
    # Wave 59.5: top-1 entry gets full content (no "- [" prefix)
    assert "**CSV Patterns**" in content
    # Remaining entries use index-only format starting with "- ["
    entry_lines = [ln for ln in content.split("\n") if ln.startswith("- [")]
    assert len(entry_lines) == 2  # 3 items minus top-1 full content
    # No entry line exceeds 200 chars
    for ln in entry_lines:
        assert len(ln) < 200, f"Entry line too long ({len(ln)}): {ln[:80]}..."


@pytest.mark.asyncio
async def test_index_includes_entry_ids() -> None:
    """Wave 58: index entries include IDs for knowledge_detail calls."""
    items = [
        _make_knowledge_item_full(
            "mem-abc-s-0", "CSV Patterns", 0.65,
            summary="CSV parsing with DictReader",
        ),
    ]
    result = await assemble_context(
        agent=_agent(),
        colony_context=_ctx(),
        round_goal="fix our CSV parser",
        routed_outputs={},
        merged_summaries=[],
        vector_port=None,
        knowledge_items=items,
    )
    contents = " ".join(m["content"] for m in result.messages)
    assert "id: mem-abc-s-0" in contents


@pytest.mark.asyncio
async def test_index_skips_low_similarity() -> None:
    """Wave 58: per-entry similarity gate still applies in index format."""
    items = [
        _make_knowledge_item_full("mem-1", "Relevant", 0.65),
        _make_knowledge_item_full("mem-2", "Irrelevant", 0.35),
    ]
    result = await assemble_context(
        agent=_agent(),
        colony_context=_ctx(),
        round_goal="fix our auth middleware",
        routed_outputs={},
        merged_summaries=[],
        vector_port=None,
        knowledge_items=items,
    )
    contents = " ".join(m["content"] for m in result.messages)
    assert "mem-1" in contents
    assert "Relevant" in contents
    assert "mem-2" not in contents
    assert "Irrelevant" not in contents
    assert len(result.knowledge_items_used) == 1


@pytest.mark.asyncio
async def test_index_token_budget_reduction() -> None:
    """Wave 58: index format uses fewer tokens than old full-content format."""
    items = [
        _make_knowledge_item_full(f"e{i}", f"Entry {i}", 0.60 + i * 0.02)
        for i in range(5)
    ]
    result = await assemble_context(
        agent=_agent(),
        colony_context=_ctx(),
        round_goal="fix our widget parser",
        routed_outputs={},
        merged_summaries=[],
        vector_port=None,
        knowledge_items=items,
    )
    knowledge_msg = [
        m for m in result.messages
        if "[Available Knowledge]" in m.get("content", "")
    ]
    assert len(knowledge_msg) == 1
    tokens = estimate_tokens(knowledge_msg[0]["content"])
    # Index format: ~50 tok/entry * 5 + header ≈ 300 tokens.
    # Old format would be ~160 tok/entry * 5 ≈ 800 tokens.
    assert tokens < 500, f"Index format used {tokens} tokens, expected < 500"


@pytest.mark.asyncio
async def test_trajectory_display_in_index() -> None:
    """Wave 58: trajectory entries display with [TRAJECTORY] tag."""
    items = [
        _make_knowledge_item_full(
            "traj-col-1",
            "Trajectory: code_implementation (8 steps)",
            0.60,
            sub_type="trajectory",
            summary="code_implementation tool sequence, 8 steps, quality 0.50",
        ),
    ]
    result = await assemble_context(
        agent=_agent(),
        colony_context=_ctx(),
        round_goal="fix our deployment script",
        routed_outputs={},
        merged_summaries=[],
        vector_port=None,
        knowledge_items=items,
    )
    contents = " ".join(m["content"] for m in result.messages)
    assert "[TRAJECTORY]" in contents
    assert "[SKILL, VERIFIED]" not in contents
    assert "id: traj-col-1" in contents


# ---------------------------------------------------------------------------
# Wave 58.5: Domain-boundary filtering
# ---------------------------------------------------------------------------


def _ctx_with_task_class(task_class: str = "generic") -> ColonyContext:
    return ColonyContext(
        colony_id="col-1", workspace_id="ws-1", thread_id="th-1",
        goal="Build a widget", round_number=1,
        merge_edges=[], task_class=task_class,
    )


@pytest.mark.asyncio
async def test_domain_filter_keeps_matching_entries() -> None:
    """Entries whose primary_domain matches task_class are kept."""
    items = [
        {**_make_knowledge_item_full("e1", "Auth helper", 0.80),
         "primary_domain": "code_implementation"},
        {**_make_knowledge_item_full("e2", "Review tip", 0.75),
         "primary_domain": "code_review"},
    ]
    result = await assemble_context(
        agent=_agent(),
        colony_context=_ctx_with_task_class("code_implementation"),
        round_goal="implement auth endpoint",
        routed_outputs={},
        merged_summaries=[],
        vector_port=None,
        knowledge_items=items,
    )
    contents = " ".join(m["content"] for m in result.messages)
    assert "Auth helper" in contents
    assert "Review tip" not in contents


@pytest.mark.asyncio
async def test_domain_filter_passes_untagged_entries() -> None:
    """Entries without primary_domain pass through the filter."""
    items = [
        _make_knowledge_item_full("e1", "No domain tag", 0.80),
        {**_make_knowledge_item_full("e2", "Empty domain", 0.75),
         "primary_domain": ""},
    ]
    result = await assemble_context(
        agent=_agent(),
        colony_context=_ctx_with_task_class("code_implementation"),
        round_goal="implement something specific",
        routed_outputs={},
        merged_summaries=[],
        vector_port=None,
        knowledge_items=items,
    )
    contents = " ".join(m["content"] for m in result.messages)
    assert "No domain tag" in contents
    assert "Empty domain" in contents


@pytest.mark.asyncio
async def test_domain_filter_passes_generic_entries() -> None:
    """Entries with primary_domain='generic' pass through any filter."""
    items = [
        {**_make_knowledge_item_full("e1", "Generic entry", 0.80),
         "primary_domain": "generic"},
    ]
    result = await assemble_context(
        agent=_agent(),
        colony_context=_ctx_with_task_class("code_review"),
        round_goal="review this pull request",
        routed_outputs={},
        merged_summaries=[],
        vector_port=None,
        knowledge_items=items,
    )
    contents = " ".join(m["content"] for m in result.messages)
    assert "Generic entry" in contents


@pytest.mark.asyncio
async def test_domain_filter_skipped_for_generic_task_class() -> None:
    """When task_class is 'generic', no domain filtering occurs."""
    items = [
        {**_make_knowledge_item_full("e1", "Code impl entry", 0.80),
         "primary_domain": "code_implementation"},
        {**_make_knowledge_item_full("e2", "Review entry", 0.75),
         "primary_domain": "code_review"},
    ]
    result = await assemble_context(
        agent=_agent(),
        colony_context=_ctx_with_task_class("generic"),
        round_goal="do something generic",
        routed_outputs={},
        merged_summaries=[],
        vector_port=None,
        knowledge_items=items,
    )
    contents = " ".join(m["content"] for m in result.messages)
    assert "Code impl entry" in contents
    assert "Review entry" in contents
