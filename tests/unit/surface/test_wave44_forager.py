"""Wave 44 Pillars 2-4: Forager orchestration tests.

Covers:
- Deterministic query template expansion
- Content chunking
- Exact-hash deduplication
- Entry preparation with forager provenance
- Admission bridge scoring
- Domain policy controls
- Forage cycle orchestration (with mock fetch substrate)
- Reactive trigger detection in knowledge_catalog
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from formicos.surface.forager import (
    DomainPolicy,
    FetchResult,
    ForageCycleResult,
    ForageRequest,
    ForagerOrchestrator,
    build_query,
    chunk_content,
    content_hash,
    deduplicate_chunks,
    prepare_forager_entry,
    score_forager_entry,
)


# ---------------------------------------------------------------------------
# Deterministic query template tests (Pillar 2B)
# ---------------------------------------------------------------------------


class TestBuildQuery:
    def test_reactive_trigger(self) -> None:
        req = ForageRequest(
            workspace_id="ws-1",
            trigger="reactive",
            gap_description="Low coverage",
            topic="python asyncio patterns",
            context="error handling",
        )
        query = build_query(req)
        assert "python asyncio patterns" in query
        assert "error handling" in query

    def test_confidence_decline_includes_year(self) -> None:
        req = ForageRequest(
            workspace_id="ws-1",
            trigger="proactive:confidence_decline",
            gap_description="Confidence dropped",
            topic="react hooks",
        )
        query = build_query(req)
        assert "react hooks" in query
        year = str(datetime.now(UTC).year)
        assert year in query

    def test_coverage_gap_template(self) -> None:
        req = ForageRequest(
            workspace_id="ws-1",
            trigger="proactive:coverage_gap",
            gap_description="No entries for testing",
            topic="pytest fixtures",
            context="parameterize tests",
        )
        query = build_query(req)
        assert "pytest fixtures" in query
        assert "parameterize tests" in query

    def test_falls_back_to_domains_when_no_topic(self) -> None:
        req = ForageRequest(
            workspace_id="ws-1",
            trigger="reactive",
            gap_description="gap",
            domains=["python", "asyncio", "networking"],
        )
        query = build_query(req)
        assert "python" in query
        assert "asyncio" in query

    def test_unknown_trigger_uses_default(self) -> None:
        req = ForageRequest(
            workspace_id="ws-1",
            trigger="unknown_trigger",
            gap_description="gap",
            topic="some topic",
        )
        query = build_query(req)
        assert "some topic" in query

    def test_query_length_capped(self) -> None:
        req = ForageRequest(
            workspace_id="ws-1",
            trigger="reactive",
            gap_description="gap",
            topic="x " * 150,
            context="y " * 150,
        )
        query = build_query(req)
        assert len(query) <= 200

    def test_whitespace_collapsed(self) -> None:
        req = ForageRequest(
            workspace_id="ws-1",
            trigger="reactive",
            gap_description="gap",
            topic="  python   asyncio  ",
            context="  patterns  ",
        )
        query = build_query(req)
        assert "  " not in query


# ---------------------------------------------------------------------------
# Chunking tests (Pillar 3A)
# ---------------------------------------------------------------------------


class TestChunkContent:
    def test_short_text_single_chunk(self) -> None:
        text = "Short text that fits in one chunk."
        chunks = chunk_content(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_empty_text_no_chunks(self) -> None:
        assert chunk_content("") == []
        assert chunk_content("   ") == []

    def test_paragraph_splitting(self) -> None:
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = chunk_content(text, chunk_size=30, overlap=5)
        assert len(chunks) >= 2

    def test_sentence_splitting(self) -> None:
        text = "First sentence. Second sentence. Third sentence. Fourth sentence. Fifth sentence."
        chunks = chunk_content(text, chunk_size=40, overlap=5)
        assert len(chunks) >= 2

    def test_character_fallback(self) -> None:
        # No paragraph or sentence breaks
        text = "a" * 100
        chunks = chunk_content(text, chunk_size=30, overlap=5)
        assert len(chunks) >= 3
        # All content is covered
        combined = "".join(c[:25] for c in chunks)  # rough check
        assert len(combined) > 50

    def test_overlap_preserved(self) -> None:
        text = "a" * 100
        chunks = chunk_content(text, chunk_size=40, overlap=10)
        assert len(chunks) >= 2
        # Last characters of first chunk should appear in second
        if len(chunks) >= 2:
            overlap_region = chunks[0][-10:]
            assert overlap_region in chunks[1]

    def test_large_text_produces_multiple_chunks(self) -> None:
        text = "This is a paragraph.\n\n" * 50
        chunks = chunk_content(text, chunk_size=200, overlap=20)
        assert len(chunks) > 1


# ---------------------------------------------------------------------------
# Deduplication tests (Pillar 3B)
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_deterministic(self) -> None:
        h1 = content_hash("hello world")
        h2 = content_hash("hello world")
        assert h1 == h2

    def test_whitespace_normalized(self) -> None:
        h1 = content_hash("hello  world")
        h2 = content_hash("hello world")
        assert h1 == h2

    def test_case_normalized(self) -> None:
        h1 = content_hash("Hello World")
        h2 = content_hash("hello world")
        assert h1 == h2

    def test_different_content_different_hash(self) -> None:
        h1 = content_hash("hello")
        h2 = content_hash("world")
        assert h1 != h2


class TestDeduplicateChunks:
    def test_removes_exact_duplicates(self) -> None:
        chunks = ["hello world", "hello world", "different text"]
        unique, skipped = deduplicate_chunks(chunks)
        assert len(unique) == 2
        assert skipped == 1

    def test_respects_existing_hashes(self) -> None:
        existing = {content_hash("already known")}
        chunks = ["already known", "new text"]
        unique, skipped = deduplicate_chunks(chunks, existing)
        assert len(unique) == 1
        assert unique[0] == "new text"
        assert skipped == 1

    def test_empty_input(self) -> None:
        unique, skipped = deduplicate_chunks([])
        assert unique == []
        assert skipped == 0

    def test_all_unique(self) -> None:
        chunks = ["a", "b", "c"]
        unique, skipped = deduplicate_chunks(chunks)
        assert len(unique) == 3
        assert skipped == 0


# ---------------------------------------------------------------------------
# Entry preparation tests (Pillar 3C/3D)
# ---------------------------------------------------------------------------


class TestPrepareForagerEntry:
    def test_entry_has_required_fields(self) -> None:
        entry = prepare_forager_entry(
            "Python asyncio allows concurrent programming.",
            source_url="https://docs.python.org",
            title="Python asyncio",
            workspace_id="ws-1",
        )
        assert entry["entry_type"] == "experience"
        assert entry["sub_type"] == "learning"
        assert entry["status"] == "candidate"
        assert entry["polarity"] == "positive"
        assert entry["workspace_id"] == "ws-1"
        assert entry["scan_status"] == "pending"
        assert entry["decay_class"] == "ephemeral"
        assert entry["conf_alpha"] == 5.0
        assert entry["conf_beta"] == 5.0

    def test_entry_has_provenance(self) -> None:
        entry = prepare_forager_entry(
            "content",
            source_url="https://example.com/article",
            title="Example",
            workspace_id="ws-1",
            trigger="reactive",
            query="python patterns",
            quality_score=0.7,
        )
        prov = entry["forager_provenance"]
        assert prov["source_url"] == "https://example.com/article"
        assert prov["forager_trigger"] == "reactive"
        assert prov["forager_query"] == "python patterns"
        assert prov["quality_score"] == 0.7
        assert prov["fetch_timestamp"]  # non-empty

    def test_entry_id_is_content_based(self) -> None:
        e1 = prepare_forager_entry("same content", source_url="u", title="t", workspace_id="ws")
        e2 = prepare_forager_entry("same content", source_url="u", title="t", workspace_id="ws")
        assert e1["id"] == e2["id"]  # deterministic from content

    def test_different_content_different_id(self) -> None:
        e1 = prepare_forager_entry("content A", source_url="u", title="t", workspace_id="ws")
        e2 = prepare_forager_entry("content B", source_url="u", title="t", workspace_id="ws")
        assert e1["id"] != e2["id"]

    def test_title_truncated(self) -> None:
        entry = prepare_forager_entry(
            "content",
            source_url="u",
            title="x" * 200,
            workspace_id="ws",
        )
        assert len(entry["title"]) <= 120

    def test_domains_preserved(self) -> None:
        entry = prepare_forager_entry(
            "content",
            source_url="u",
            title="t",
            workspace_id="ws",
            domains=["python", "web"],
        )
        assert entry["domains"] == ["python", "web"]


# ---------------------------------------------------------------------------
# Admission bridge tests (Pillar 3C)
# ---------------------------------------------------------------------------


class TestScoreForagerEntry:
    def test_well_formed_entry_admitted(self) -> None:
        entry = prepare_forager_entry(
            "Python asyncio provides a framework for writing concurrent code.",
            source_url="https://docs.python.org",
            title="Python asyncio guide",
            workspace_id="ws-1",
            domains=["python"],
        )
        result = score_forager_entry(entry)
        # Entry with content, title, source should be admitted (at least as candidate)
        assert result.admitted is True

    def test_entry_starts_conservative(self) -> None:
        entry = prepare_forager_entry(
            "Some content from web.",
            source_url="https://example.com",
            title="Example",
            workspace_id="ws-1",
        )
        result = score_forager_entry(entry)
        # Conservative priors shouldn't give high scores
        assert result.score < 0.8

    def test_admission_uses_all_seven_signals(self) -> None:
        entry = prepare_forager_entry(
            "content",
            source_url="https://example.com",
            title="title",
            workspace_id="ws-1",
        )
        result = score_forager_entry(entry)
        assert "confidence" in result.signal_scores
        assert "provenance" in result.signal_scores
        assert "scanner" in result.signal_scores
        assert "federation" in result.signal_scores
        assert "observation_mass" in result.signal_scores
        assert "content_type" in result.signal_scores
        assert "recency" in result.signal_scores


# ---------------------------------------------------------------------------
# Domain policy tests (Pillar 4C)
# ---------------------------------------------------------------------------


class TestDomainPolicy:
    def test_default_allows_all(self) -> None:
        policy = DomainPolicy()
        assert policy.is_allowed("example.com") is True

    def test_distrust_blocks(self) -> None:
        policy = DomainPolicy()
        policy.distrust("spam.com")
        assert policy.is_allowed("spam.com") is False
        assert policy.is_allowed("good.com") is True

    def test_trust_restricts_to_trusted_only(self) -> None:
        policy = DomainPolicy()
        policy.trust("docs.python.org")
        assert policy.is_allowed("docs.python.org") is True
        assert policy.is_allowed("other.com") is False

    def test_distrust_overrides_trust(self) -> None:
        policy = DomainPolicy()
        policy.trust("example.com")
        policy.distrust("example.com")
        assert policy.is_allowed("example.com") is False

    def test_trust_removes_distrust(self) -> None:
        policy = DomainPolicy()
        policy.distrust("example.com")
        policy.trust("example.com")
        assert policy.is_allowed("example.com") is True

    def test_reset_removes_both(self) -> None:
        policy = DomainPolicy()
        policy.trust("a.com")
        policy.distrust("b.com")
        policy.reset("a.com")
        policy.reset("b.com")
        assert policy.is_allowed("a.com") is True
        assert policy.is_allowed("b.com") is True

    def test_case_insensitive(self) -> None:
        policy = DomainPolicy()
        policy.distrust("SPAM.COM")
        assert policy.is_allowed("spam.com") is False


# ---------------------------------------------------------------------------
# Forage cycle orchestration tests (Pillar 4)
# ---------------------------------------------------------------------------


class _MockFetchPort:
    """Mock fetch port for testing the orchestration cycle."""

    def __init__(self, results: dict[str, FetchResult] | None = None) -> None:
        self._results = results or {}

    async def fetch(self, url: str) -> FetchResult:
        if url in self._results:
            return self._results[url]
        return FetchResult(
            url=url,
            text=f"Content from {url}. This is a useful article about Python patterns.",
            title=f"Article from {url}",
            quality_score=0.6,
        )


class TestForagerOrchestrator:
    @pytest.mark.asyncio
    async def test_full_cycle_with_fetch(self) -> None:
        from formicos.adapters.web_search import SearchResponse, SearchResult, WebSearchAdapter

        mock_backend = AsyncMock()
        mock_backend.name = "test"
        mock_backend.search = AsyncMock(return_value=[
            SearchResult(url="https://docs.python.org/asyncio", title="Asyncio docs", snippet="Python asyncio guide"),
        ])
        search_adapter = WebSearchAdapter(backend=mock_backend)
        fetch_port = _MockFetchPort()

        orchestrator = ForagerOrchestrator(
            search_adapter=search_adapter,
            fetch_port=fetch_port,
        )
        request = ForageRequest(
            workspace_id="ws-1",
            trigger="reactive",
            gap_description="Low coverage for asyncio",
            topic="python asyncio",
        )
        result = await orchestrator.execute(request)

        assert isinstance(result, ForageCycleResult)
        assert len(result.queries_executed) == 1
        assert result.urls_fetched == 1
        assert result.chunks_produced >= 1
        assert result.entries_admitted >= 1
        assert result.error == ""

    @pytest.mark.asyncio
    async def test_cycle_without_fetch_substrate(self) -> None:
        """When Team 1's fetch port isn't available yet."""
        from formicos.adapters.web_search import SearchResult, WebSearchAdapter

        mock_backend = AsyncMock()
        mock_backend.name = "test"
        mock_backend.search = AsyncMock(return_value=[
            SearchResult(url="https://example.com", title="Example", snippet="Some text"),
        ])
        search_adapter = WebSearchAdapter(backend=mock_backend)

        orchestrator = ForagerOrchestrator(
            search_adapter=search_adapter,
            fetch_port=None,  # No fetch substrate
        )
        request = ForageRequest(
            workspace_id="ws-1",
            trigger="reactive",
            gap_description="gap",
            topic="test",
        )
        result = await orchestrator.execute(request)
        assert result.urls_fetched == 0
        assert result.error == ""

    @pytest.mark.asyncio
    async def test_domain_policy_blocks_fetch(self) -> None:
        from formicos.adapters.web_search import SearchResult, WebSearchAdapter

        mock_backend = AsyncMock()
        mock_backend.name = "test"
        mock_backend.search = AsyncMock(return_value=[
            SearchResult(url="https://blocked.com/page", title="Blocked", snippet="text"),
        ])
        search_adapter = WebSearchAdapter(backend=mock_backend)
        policy = DomainPolicy()
        policy.distrust("blocked.com")

        orchestrator = ForagerOrchestrator(
            search_adapter=search_adapter,
            fetch_port=_MockFetchPort(),
            domain_policy=policy,
        )
        request = ForageRequest(
            workspace_id="ws-1",
            trigger="reactive",
            gap_description="gap",
            topic="test",
        )
        result = await orchestrator.execute(request)
        assert result.urls_fetched == 0

    @pytest.mark.asyncio
    async def test_deduplication_in_cycle(self) -> None:
        """Second fetch of same content should be deduplicated."""
        from formicos.adapters.web_search import SearchResult, WebSearchAdapter

        mock_backend = AsyncMock()
        mock_backend.name = "test"
        mock_backend.search = AsyncMock(return_value=[
            SearchResult(url="https://a.com/page", title="Python guide A", snippet="python patterns"),
            SearchResult(url="https://b.com/page", title="Python guide B", snippet="python patterns"),
        ])
        search_adapter = WebSearchAdapter(backend=mock_backend)

        # Both URLs return identical content
        same_content = "Exactly the same article content about Python patterns."
        fetch_port = _MockFetchPort({
            "https://a.com/page": FetchResult(url="https://a.com/page", text=same_content, title="A"),
            "https://b.com/page": FetchResult(url="https://b.com/page", text=same_content, title="B"),
        })

        orchestrator = ForagerOrchestrator(
            search_adapter=search_adapter,
            fetch_port=fetch_port,
        )
        request = ForageRequest(
            workspace_id="ws-1",
            trigger="reactive",
            gap_description="gap",
            topic="python",
        )
        result = await orchestrator.execute(request)
        assert result.duplicates_skipped >= 1

    @pytest.mark.asyncio
    async def test_search_error_handled(self) -> None:
        from formicos.adapters.web_search import SearchResponse, WebSearchAdapter

        mock_backend = AsyncMock()
        mock_backend.name = "test"
        mock_backend.search = AsyncMock(side_effect=Exception("search down"))
        search_adapter = WebSearchAdapter(backend=mock_backend)

        orchestrator = ForagerOrchestrator(
            search_adapter=search_adapter,
            fetch_port=_MockFetchPort(),
        )
        request = ForageRequest(
            workspace_id="ws-1",
            trigger="reactive",
            gap_description="gap",
            topic="test",
        )
        result = await orchestrator.execute(request)
        assert "search_failed" in result.error or "search down" in result.error

    @pytest.mark.asyncio
    async def test_fetch_failure_skipped(self) -> None:
        from formicos.adapters.web_search import SearchResult, WebSearchAdapter

        mock_backend = AsyncMock()
        mock_backend.name = "test"
        mock_backend.search = AsyncMock(return_value=[
            SearchResult(url="https://broken.com/page", title="Broken", snippet="text"),
        ])
        search_adapter = WebSearchAdapter(backend=mock_backend)

        fetch_port = _MockFetchPort({
            "https://broken.com/page": FetchResult(url="https://broken.com/page", error="404"),
        })

        orchestrator = ForagerOrchestrator(
            search_adapter=search_adapter,
            fetch_port=fetch_port,
        )
        request = ForageRequest(
            workspace_id="ws-1",
            trigger="reactive",
            gap_description="gap",
            topic="test",
        )
        result = await orchestrator.execute(request)
        assert result.urls_fetched == 0
        assert result.entries_admitted == 0

    @pytest.mark.asyncio
    async def test_admitted_entries_have_provenance(self) -> None:
        from formicos.adapters.web_search import SearchResult, WebSearchAdapter

        mock_backend = AsyncMock()
        mock_backend.name = "test"
        mock_backend.search = AsyncMock(return_value=[
            SearchResult(url="https://docs.example.com/guide", title="Python patterns guide", snippet="python patterns tutorial"),
        ])
        search_adapter = WebSearchAdapter(backend=mock_backend)

        orchestrator = ForagerOrchestrator(
            search_adapter=search_adapter,
            fetch_port=_MockFetchPort(),
        )
        request = ForageRequest(
            workspace_id="ws-1",
            trigger="reactive",
            gap_description="Knowledge gap",
            topic="python patterns",
            domains=["python"],
        )
        result = await orchestrator.execute(request)
        assert result.entries_admitted >= 1
        # Entry IDs should contain "forager" prefix
        for eid in result.admitted_entry_ids:
            assert eid.startswith("mem-forager-")


# ---------------------------------------------------------------------------
# ForageRequest data shape tests
# ---------------------------------------------------------------------------


class TestForageRequest:
    def test_defaults(self) -> None:
        req = ForageRequest(
            workspace_id="ws-1",
            trigger="reactive",
            gap_description="gap",
        )
        assert req.domains == []
        assert req.topic == ""
        assert req.max_results == 5
        assert req.budget_limit == 0.50

    def test_full_construction(self) -> None:
        req = ForageRequest(
            workspace_id="ws-1",
            trigger="proactive:coverage_gap",
            gap_description="No entries for testing",
            domains=["python", "testing"],
            topic="pytest fixtures",
            context="parameterized tests",
            colony_id="col-1",
            thread_id="th-1",
            max_results=3,
            budget_limit=1.0,
        )
        assert req.workspace_id == "ws-1"
        assert req.trigger == "proactive:coverage_gap"
        assert len(req.domains) == 2
