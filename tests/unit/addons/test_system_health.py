"""Wave 87 Track A: system-health addon tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from formicos.addons.system_health.status import get_overview


def _mock_projections(colonies: list | None = None) -> MagicMock:
    proj = MagicMock()
    if colonies is not None:
        proj.colonies = {c.id: c for c in colonies}
    else:
        proj.colonies = {}
    proj.memory_entries = {}
    return proj


def _mock_colony(
    cid: str,
    ws: str = "ws1",
    status: str = "completed",
    quality: float = 0.7,
) -> MagicMock:
    c = MagicMock()
    c.id = cid
    c.workspace_id = ws
    c.status = status
    c.quality_score = quality
    return c


class TestGetOverview:
    @pytest.mark.asyncio()
    async def test_returns_status_card(self) -> None:
        result = await get_overview(
            {}, "ws1", "",
            runtime_context={"projections": None, "data_dir": ""},
        )
        assert result["display_type"] == "status_card"
        assert "items" in result

    @pytest.mark.asyncio()
    async def test_colony_stats_populated(self) -> None:
        colonies = [
            _mock_colony("c1", quality=0.8),
            _mock_colony("c2", quality=0.6),
            _mock_colony("c3", status="failed"),
        ]
        proj = _mock_projections(colonies)
        result = await get_overview(
            {}, "ws1", "",
            runtime_context={"projections": proj, "data_dir": ""},
        )
        items = {i["label"]: i["value"] for i in result["items"]}
        assert items["Recent Colonies"] == "3"
        assert items["Succeeded"] == "2"
        assert items["Failed"] == "1"

    @pytest.mark.asyncio()
    async def test_workspace_scoped_via_query_params(self) -> None:
        colonies = [
            _mock_colony("c1", ws="ws1"),
            _mock_colony("c2", ws="ws2"),
        ]
        proj = _mock_projections(colonies)
        result = await get_overview(
            {"workspace_id": "ws1"}, "", "",
            runtime_context={"projections": proj, "data_dir": ""},
        )
        items = {i["label"]: i["value"] for i in result["items"]}
        assert items["Recent Colonies"] == "1"

    @pytest.mark.asyncio()
    async def test_no_context_graceful(self) -> None:
        result = await get_overview({}, "ws1", "")
        assert result["display_type"] == "status_card"
        items = {i["label"]: i["value"] for i in result["items"]}
        assert items["Recent Colonies"] == "0"

    @pytest.mark.asyncio()
    async def test_memory_entries_counted(self) -> None:
        proj = _mock_projections()
        proj.memory_entries = {"e1": {}, "e2": {}, "e3": {}}
        result = await get_overview(
            {}, "ws1", "",
            runtime_context={"projections": proj, "data_dir": ""},
        )
        items = {i["label"]: i["value"] for i in result["items"]}
        assert items["Memory Entries"] == "3"
