"""Unit tests for codebase index status functionality.

Tests the status.py module which provides index status information
by merging vector-store collection info with persisted reindex sidecar data.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from formicos.addons.codebase_index.indexer import (
    _STATUS_FILENAME,
    read_index_status,
    write_index_status,
)
from formicos.addons.codebase_index.status import get_status


class TestWriteReadSidecar:
    def test_write_and_read(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        write_index_status(data_dir, "ws-1", "/project/root", {
            "file_count": 42,
            "chunk_count": 210,
            "errors": 1,
        })
        result = read_index_status(data_dir, "ws-1")
        assert result is not None
        assert result["workspace_root"] == "/project/root"
        assert result["file_count"] == 42
        assert result["chunk_count"] == 210
        assert result["error_count"] == 1
        assert result["collection"] == "code_index"
        assert "last_indexed_at" in result

    def test_read_returns_none_when_missing(self, tmp_path: Path) -> None:
        assert read_index_status(str(tmp_path), "ws-missing") is None

    def test_write_is_deterministic_json(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        write_index_status(data_dir, "ws-1", "/root", {"file_count": 5, "chunk_count": 25, "errors": 0})
        path = tmp_path / ".formicos" / "runtime" / "ws-1" / _STATUS_FILENAME
        assert path.exists()
        parsed = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(parsed, dict)
        assert parsed["file_count"] == 5

    def test_overwrite_on_second_write(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        write_index_status(data_dir, "ws-1", "/root", {"file_count": 5, "chunk_count": 25, "errors": 0})
        write_index_status(data_dir, "ws-1", "/root", {"file_count": 10, "chunk_count": 50, "errors": 2})
        result = read_index_status(data_dir, "ws-1")
        assert result is not None
        assert result["file_count"] == 10


class TestGetStatus:
    @pytest.mark.anyio()
    async def test_status_with_sidecar_and_vector(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        write_index_status(data_dir, "ws-1", "/project", {
            "file_count": 10, "chunk_count": 50, "errors": 0,
        })
        vector_port = AsyncMock()
        vector_port.collection_info = AsyncMock(return_value={"points_count": 50})
        ctx = {"vector_port": vector_port, "data_dir": data_dir}

        result = await get_status({}, "ws-1", "t-1", runtime_context=ctx)
        assert result["display_type"] == "status_card"
        items = {i["label"]: i["value"] for i in result["items"]}
        assert "Bound root" in items
        assert items["Bound root"] == "/project"
        assert "Live chunks" in items
        assert items["Live chunks"] == "50"
        assert "Last indexed" in items

    @pytest.mark.anyio()
    async def test_status_without_sidecar(self, tmp_path: Path) -> None:
        vector_port = AsyncMock()
        vector_port.collection_info = AsyncMock(return_value={"points_count": 0})
        ctx = {"vector_port": vector_port, "data_dir": str(tmp_path)}

        result = await get_status({}, "ws-1", "t-1", runtime_context=ctx)
        items = {i["label"]: i["value"] for i in result["items"]}
        assert "Bound root" not in items
        assert "Live chunks" in items

    @pytest.mark.anyio()
    async def test_status_no_vector_no_sidecar(self) -> None:
        result = await get_status({}, "ws-1", "t-1", runtime_context={})
        items = {i["label"]: i["value"] for i in result["items"]}
        assert "not configured" in items.get("Vector store", "")

    @pytest.mark.anyio()
    async def test_status_vector_unavailable(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        write_index_status(data_dir, "ws-1", "/project", {
            "file_count": 5, "chunk_count": 25, "errors": 0,
        })
        vector_port = AsyncMock()
        vector_port.collection_info = AsyncMock(side_effect=Exception("down"))
        ctx = {"vector_port": vector_port, "data_dir": data_dir}

        result = await get_status({}, "ws-1", "t-1", runtime_context=ctx)
        items = {i["label"]: i["value"] for i in result["items"]}
        assert items.get("Vector store") == "unavailable"
        assert "Bound root" in items  # sidecar still shows
