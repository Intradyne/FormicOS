"""Tests for codebase index addon — chunking, reindex, search."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.addons.codebase_index.indexer import (
    chunk_code,
    full_reindex,
    incremental_reindex,
    on_scheduled_reindex,
)
from formicos.addons.codebase_index.search import (
    handle_reindex,
    handle_semantic_search,
)


class TestCodeChunking:
    """Test the code chunking logic."""

    def test_chunks_on_function_boundary(self) -> None:
        code = (
            "import os\n"
            "\n"
            "def foo():\n"
            "    return 1\n"
            "\n"
            "def bar():\n"
            "    return 2\n"
        )
        chunks = chunk_code(code, "test.py", chunk_size=30)
        assert len(chunks) >= 2
        assert "foo" in chunks[0].text
        assert chunks[0].path == "test.py"
        assert chunks[0].line_start >= 1

    def test_empty_content(self) -> None:
        chunks = chunk_code("", "empty.py")
        assert chunks == []

    def test_whitespace_only_skipped(self) -> None:
        chunks = chunk_code("   \n  \n", "blank.py")
        assert chunks == []

    def test_single_function(self) -> None:
        code = "def hello():\n    print('hi')\n"
        chunks = chunk_code(code, "small.py")
        assert len(chunks) >= 1
        assert "hello" in chunks[0].text

    def test_chunk_ids_are_deterministic(self) -> None:
        code = "def a():\n    pass\ndef b():\n    pass\n"
        chunks1 = chunk_code(code, "f.py", chunk_size=20)
        chunks2 = chunk_code(code, "f.py", chunk_size=20)
        assert [c.id for c in chunks1] == [c.id for c in chunks2]

    def test_large_file_splits(self) -> None:
        """A file larger than 2x chunk_size is forcibly split."""
        code = "x = 1\n" * 200  # ~1200 chars
        chunks = chunk_code(code, "big.py", chunk_size=100)
        assert len(chunks) > 1


class TestFullReindex:
    """Test the full reindex function."""

    @pytest.mark.asyncio()
    async def test_reindex_indexes_code_files(self, tmp_path: Path) -> None:
        (tmp_path / "hello.py").write_text(
            "def greet():\n    return 'hi'\n", encoding="utf-8",
        )
        (tmp_path / "readme.md").write_text("# Hello\n", encoding="utf-8")
        (tmp_path / "data.bin").write_bytes(b"\x00" * 100)

        vector_port = AsyncMock()
        vector_port.upsert = AsyncMock(return_value=1)

        result = await full_reindex(tmp_path, vector_port)
        assert result["file_count"] >= 1
        assert result["chunk_count"] >= 1
        assert result["errors"] == 0
        assert vector_port.upsert.call_count >= 1

    @pytest.mark.asyncio()
    async def test_reindex_skips_pycache(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "mod.cpython-312.pyc").write_bytes(b"\x00")
        (tmp_path / "real.py").write_text("x = 1\n", encoding="utf-8")

        vector_port = AsyncMock()
        vector_port.upsert = AsyncMock(return_value=1)

        result = await full_reindex(tmp_path, vector_port)
        assert result["file_count"] == 1


class TestIncrementalReindex:
    """Test incremental reindex."""

    @pytest.mark.asyncio()
    async def test_incremental_only_changed(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("def a(): pass\n", encoding="utf-8")
        (tmp_path / "b.py").write_text("def b(): pass\n", encoding="utf-8")

        vector_port = AsyncMock()
        vector_port.upsert = AsyncMock(return_value=1)

        result = await incremental_reindex(
            tmp_path, vector_port,
            changed_files=["a.py"],
        )
        assert result["file_count"] == 1

    @pytest.mark.asyncio()
    async def test_incremental_none_falls_back_to_full(
        self, tmp_path: Path,
    ) -> None:
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

        vector_port = AsyncMock()
        vector_port.upsert = AsyncMock(return_value=1)

        result = await incremental_reindex(
            tmp_path, vector_port, changed_files=None,
        )
        assert result["file_count"] >= 1


class TestOnScheduledReindex:
    """Test the cron trigger wrapper."""

    @pytest.mark.asyncio()
    async def test_skips_without_deps(self) -> None:
        """Does nothing when vector_port is missing."""
        await on_scheduled_reindex(runtime_context={})

    @pytest.mark.asyncio()
    async def test_skips_without_projections(self) -> None:
        """Does nothing when no workspaces to index."""
        await on_scheduled_reindex(
            runtime_context={
                "vector_port": AsyncMock(),
                "workspace_root_fn": lambda ws: Path("/tmp") / ws,
            },
        )


class TestHandleReindex:
    """Test the Queen tool handler for reindex."""

    def test_missing_vector_port(self) -> None:
        result = asyncio.run(
            handle_reindex({}, "ws1", "th1", runtime_context={})
        )
        assert "unavailable" in result.lower()

    def test_missing_workspace(self) -> None:
        mock_path = MagicMock()
        mock_path.is_dir.return_value = False
        result = asyncio.run(
            handle_reindex(
                {}, "ws1", "th1",
                runtime_context={
                    "vector_port": AsyncMock(),
                    "workspace_root_fn": lambda _: mock_path,
                },
            )
        )
        assert "not found" in result.lower()


class TestSemanticSearch:
    """Test the semantic search handler."""

    def test_no_vector_port_returns_unavailable(self) -> None:
        result = asyncio.run(
            handle_semantic_search(
                {"query": "authentication handlers", "top_k": 5},
                "ws1",
                "th1",
            )
        )
        assert "unavailable" in result.lower()

    def test_with_runtime_context_searches_vector_port(self) -> None:
        """When runtime_context has vector_port, calls search."""
        mock_hit = MagicMock()
        mock_hit.metadata = {
            "path": "auth.py", "line_start": 10,
            "line_end": 20, "content": "def login():",
        }
        mock_hit.payload = mock_hit.metadata
        mock_hit.score = 0.95

        mock_port = MagicMock()
        mock_port.search = AsyncMock(return_value=[mock_hit])

        result = asyncio.run(
            handle_semantic_search(
                {"query": "authentication", "top_k": 3},
                "ws1",
                "th1",
                runtime_context={"vector_port": mock_port},
            )
        )
        assert "auth.py" in result
        assert "0.950" in result
        mock_port.search.assert_called_once()

    def test_empty_query_returns_error(self) -> None:
        result = asyncio.run(
            handle_semantic_search({}, "ws1", "th1")
        )
        assert "Error" in result
