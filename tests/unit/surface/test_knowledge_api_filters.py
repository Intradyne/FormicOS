from __future__ import annotations

from unittest.mock import AsyncMock

from starlette.applications import Starlette
from starlette.testclient import TestClient

from formicos.surface.routes import knowledge_api


def _build_client(catalog: AsyncMock) -> TestClient:
    app = Starlette(routes=knowledge_api.routes(knowledge_catalog=catalog))
    return TestClient(app, raise_server_exceptions=False)


class TestKnowledgeApiFilters:
    def test_list_forwards_source_colony_id_and_workspace(self) -> None:
        catalog = AsyncMock()
        catalog.list_all = AsyncMock(return_value=([], 0))
        client = _build_client(catalog)

        resp = client.get(
            "/api/v1/knowledge?limit=25&workspace=ws-1&source_colony_id=colony-1",
        )

        assert resp.status_code == 200
        catalog.list_all.assert_awaited_once_with(
            source_system="",
            canonical_type="",
            workspace_id="ws-1",
            source_colony_id="colony-1",
            limit=25,
        )

    def test_search_forwards_source_colony_id_and_workspace(self) -> None:
        catalog = AsyncMock()
        catalog.search = AsyncMock(return_value=[])
        client = _build_client(catalog)

        resp = client.get(
            "/api/v1/knowledge/search?q=test&limit=12&workspace=ws-1&source_colony_id=colony-1",
        )

        assert resp.status_code == 200
        catalog.search.assert_awaited_once_with(
            query="test",
            source_system="",
            canonical_type="",
            workspace_id="ws-1",
            thread_id="",
            source_colony_id="colony-1",
            top_k=12,
        )

    def test_list_rejects_non_integer_limit(self) -> None:
        catalog = AsyncMock()
        client = _build_client(catalog)

        resp = client.get("/api/v1/knowledge?limit=bad")

        assert resp.status_code == 400
        assert resp.json()["error_code"] == "LIMIT_INVALID"

    def test_search_rejects_non_integer_limit(self) -> None:
        catalog = AsyncMock()
        client = _build_client(catalog)

        resp = client.get("/api/v1/knowledge/search?q=test&limit=bad")

        assert resp.status_code == 400
        assert resp.json()["error_code"] == "LIMIT_INVALID"
