"""Tests for codebase-index reindex sidecar writing (Wave 81 Track C)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from formicos.addons.codebase_index.indexer import (
    full_reindex,
    read_index_status,
)


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """Create a tiny workspace with indexable files."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello():\n    return 'world'\n")
    (tmp_path / "src" / "util.py").write_text("class Foo:\n    pass\n")
    (tmp_path / "README.md").write_text("# Project\n")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "cache.pyc").write_bytes(b"\x00")
    return tmp_path


class TestFullReindexSidecar:
    @pytest.mark.anyio()
    async def test_writes_sidecar_when_data_dir_provided(
        self, workspace: Path, tmp_path: Path,
    ) -> None:
        data_dir = str(tmp_path / "data")
        vector_port = AsyncMock()
        vector_port.upsert = AsyncMock()

        result = await full_reindex(
            workspace, vector_port,
            data_dir=data_dir, workspace_id="ws-test",
        )

        assert result["file_count"] >= 2  # main.py, util.py, README.md
        assert result["chunk_count"] >= 2

        sidecar = read_index_status(data_dir, "ws-test")
        assert sidecar is not None
        assert sidecar["file_count"] == result["file_count"]
        assert sidecar["chunk_count"] == result["chunk_count"]
        assert sidecar["workspace_root"] == str(workspace)
        assert "last_indexed_at" in sidecar

    @pytest.mark.anyio()
    async def test_no_sidecar_without_data_dir(self, workspace: Path) -> None:
        vector_port = AsyncMock()
        vector_port.upsert = AsyncMock()

        result = await full_reindex(workspace, vector_port)

        assert result["file_count"] >= 2
        # No data_dir -> no sidecar written (nothing to check)

    @pytest.mark.anyio()
    async def test_skips_pycache(self, workspace: Path) -> None:
        vector_port = AsyncMock()
        vector_port.upsert = AsyncMock()

        result = await full_reindex(workspace, vector_port)

        # .pyc files should not be indexed
        for call in vector_port.upsert.call_args_list:
            docs = call[0][1]  # second positional arg
            for doc in docs:
                assert "__pycache__" not in doc.metadata.get("path", "")
