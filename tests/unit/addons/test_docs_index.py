"""Tests for the docs-index addon — chunking, search, reindex, status."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.addons.docs_index.indexer import DocChunk, chunk_document

# ---------------------------------------------------------------------------
# Chunking tests
# ---------------------------------------------------------------------------


class TestMarkdownChunking:
    def test_splits_on_headings(self) -> None:
        content = "# Intro\nHello world\n## Details\nSome details here\n### Sub\nDeep content\n"
        chunks = chunk_document(content, "README.md")
        assert len(chunks) == 3
        assert chunks[0].section == "Intro"
        assert chunks[1].section == "Details"
        assert chunks[2].section == "Sub"

    def test_single_section(self) -> None:
        content = "# Only heading\nJust one section.\n"
        chunks = chunk_document(content, "doc.md")
        assert len(chunks) == 1
        assert chunks[0].section == "Only heading"

    def test_intro_before_first_heading(self) -> None:
        content = "Some preamble text\n# First heading\nBody\n"
        chunks = chunk_document(content, "doc.md")
        assert len(chunks) == 2
        assert chunks[0].section == "(intro)"
        assert chunks[1].section == "First heading"


class TestChunkMetadata:
    def test_includes_section_and_lines(self) -> None:
        content = "# Title\nLine 1\nLine 2\n## Next\nLine 3\n"
        chunks = chunk_document(content, "test.md")
        for chunk in chunks:
            assert isinstance(chunk, DocChunk)
            assert chunk.section
            assert chunk.line_start >= 1
            assert chunk.line_end >= chunk.line_start
            assert chunk.path == "test.md"

    def test_chunk_id_is_deterministic(self) -> None:
        content = "# Heading\nBody text\n"
        chunks_a = chunk_document(content, "a.md")
        chunks_b = chunk_document(content, "a.md")
        assert chunks_a[0].id == chunks_b[0].id


class TestRstChunking:
    def test_splits_on_underlines(self) -> None:
        content = "Title\n=====\nIntro text\n\nSubtitle\n--------\nMore text\n"
        chunks = chunk_document(content, "doc.rst")
        assert len(chunks) == 2
        assert chunks[0].section == "Title"
        assert chunks[1].section == "Subtitle"


class TestHtmlChunking:
    def test_splits_on_heading_tags(self) -> None:
        content = "<h1>Welcome</h1>\n<p>Hello</p>\n<h2>Details</h2>\n<p>Info</p>\n"
        chunks = chunk_document(content, "page.html")
        assert len(chunks) == 2
        assert chunks[0].section == "Welcome"
        assert chunks[1].section == "Details"


class TestTextChunking:
    def test_splits_on_blank_lines(self) -> None:
        content = "Paragraph one line one\nLine two\n\nParagraph two\n"
        chunks = chunk_document(content, "notes.txt")
        assert len(chunks) == 2


# ---------------------------------------------------------------------------
# Search handler tests
# ---------------------------------------------------------------------------


class TestHandleSemanticSearch:
    @pytest.mark.asyncio
    async def test_queries_docs_index(self) -> None:
        from formicos.addons.docs_index.search import handle_semantic_search

        mock_hit = MagicMock()
        mock_hit.metadata = {}
        mock_hit.payload = {
            "path": "docs/guide.md",
            "section": "Setup",
            "line_start": 1,
            "line_end": 5,
            "content": "Install with pip",
        }
        mock_hit.score = 0.95

        vector_port = AsyncMock()
        vector_port.search = AsyncMock(return_value=[mock_hit])

        result = await handle_semantic_search(
            {"query": "installation"},
            workspace_id="ws-1",
            thread_id="th-1",
            runtime_context={"vector_port": vector_port},
        )

        vector_port.search.assert_called_once_with("docs_index", "installation", 10)
        assert "docs/guide.md" in result
        assert "Setup" in result

    @pytest.mark.asyncio
    async def test_missing_query_returns_error(self) -> None:
        from formicos.addons.docs_index.search import handle_semantic_search

        result = await handle_semantic_search(
            {},
            workspace_id="ws-1",
            thread_id="th-1",
        )
        assert "Error" in result


# ---------------------------------------------------------------------------
# Reindex handler tests
# ---------------------------------------------------------------------------


class TestHandleReindex:
    @pytest.mark.asyncio
    async def test_indexes_docs_from_workspace(self, tmp_path: Any) -> None:
        from formicos.addons.docs_index.search import handle_reindex

        # Create a doc file in the temp workspace
        doc = tmp_path / "guide.md"
        doc.write_text("# Guide\nSome guide content\n")

        vector_port = AsyncMock()
        vector_port.upsert = AsyncMock()

        result = await handle_reindex(
            {},
            workspace_id="ws-1",
            thread_id="th-1",
            runtime_context={
                "vector_port": vector_port,
                "workspace_root_fn": lambda ws_id: tmp_path,
            },
        )

        assert "1 files" in result
        vector_port.upsert.assert_called_once()


# ---------------------------------------------------------------------------
# Status endpoint test
# ---------------------------------------------------------------------------


class TestStatusEndpoint:
    @pytest.mark.asyncio
    async def test_returns_status_card(self) -> None:
        from formicos.addons.docs_index.status import get_status

        vector_port = AsyncMock()
        vector_port.collection_info = AsyncMock(return_value={"points_count": 42})

        result = await get_status(
            {},
            workspace_id="ws-1",
            _thread_id="th-1",
            runtime_context={"vector_port": vector_port},
        )

        assert result["display_type"] == "status_card"
        items = result["items"]
        labels = [i["label"] for i in items]
        assert "Documents indexed" in labels
        assert "Collection" in labels
