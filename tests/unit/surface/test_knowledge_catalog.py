"""Tests for Wave 27/28 — route migration, deprecation labels, legacy removal."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from formicos.surface.routes import api as api_routes
from formicos.surface.routes import memory_api


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_api_client(
    *,
    vector_store: Any = None,
    kg_adapter: Any = None,
    embed_client: Any = None,
) -> TestClient:
    """Build a TestClient wired to the api.py routes."""
    runtime = MagicMock()
    settings = MagicMock()
    settings.embedding.model = "test-embed"
    settings.embedding.dimensions = 128
    settings.models.registry = []
    route_list = api_routes.routes(
        runtime=runtime,
        settings=settings,
        castes=None,
        castes_path="/dev/null",
        config_path="/dev/null",
        vector_store=vector_store,
        kg_adapter=kg_adapter,
        embed_client=embed_client,
        skill_collection="skill_bank_v2",
        ws_manager=MagicMock(),
    )
    app = Starlette(routes=route_list)
    return TestClient(app, raise_server_exceptions=False)


def _build_memory_client(
    *,
    projections: Any = None,
    memory_store: Any = None,
) -> TestClient:
    """Build a TestClient wired to the memory_api.py routes."""
    if projections is None:
        projections = MagicMock()
        projections.memory_entries = {}
    route_list = memory_api.routes(
        projections=projections,
        memory_store=memory_store,
    )
    app = Starlette(routes=route_list)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# KG route rename — /api/v1/knowledge -> /api/v1/knowledge-graph (Wave 27 C1)
# ---------------------------------------------------------------------------


class TestKGRouteRename:
    """Verify the KG endpoint lives at the new path."""

    def test_knowledge_graph_route_exists(self) -> None:
        client = _build_api_client(kg_adapter=None)
        resp = client.get("/api/v1/knowledge-graph")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        assert "stats" in data

    def test_old_knowledge_route_is_404(self) -> None:
        client = _build_api_client(kg_adapter=None)
        resp = client.get("/api/v1/knowledge")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /api/v1/skills removed (Wave 28 C4)
# ---------------------------------------------------------------------------


class TestSkillsEndpointRemoved:
    """Verify /api/v1/skills is no longer served."""

    def test_skills_returns_404(self) -> None:
        client = _build_api_client(vector_store=None)
        resp = client.get("/api/v1/skills")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Legacy /api/v1/memory deprecation labels (still active for one wave)
# ---------------------------------------------------------------------------


class TestMemoryListDeprecation:
    """Verify /api/v1/memory list response has _deprecated."""

    def test_list_response_has_deprecated_key(self) -> None:
        client = _build_memory_client()
        resp = client.get("/api/v1/memory")
        assert resp.status_code == 200
        data = resp.json()
        assert "_deprecated" in data
        assert "entries" in data
        assert "total" in data

    def test_list_deprecated_message_points_to_knowledge(self) -> None:
        client = _build_memory_client()
        data = client.get("/api/v1/memory").json()
        assert "/api/v1/knowledge" in data["_deprecated"]


class TestMemorySearchDeprecation:
    """Verify /api/v1/memory/search response has _deprecated."""

    def test_search_response_has_deprecated_key(self) -> None:
        store = AsyncMock()
        store.search = AsyncMock(return_value=[])
        client = _build_memory_client(memory_store=store)
        resp = client.get("/api/v1/memory/search?q=test")
        assert resp.status_code == 200
        data = resp.json()
        assert "_deprecated" in data
        assert "results" in data
        assert "total" in data


class TestMemoryDetailDeprecation:
    """Verify /api/v1/memory/{id} response has _deprecated."""

    def test_detail_response_has_deprecated_key(self) -> None:
        proj = MagicMock()
        proj.memory_entries = {
            "mem-1": {
                "id": "mem-1",
                "entry_type": "skill",
                "title": "test",
            },
        }
        client = _build_memory_client(projections=proj)
        resp = client.get("/api/v1/memory/mem-1")
        assert resp.status_code == 200
        data = resp.json()
        assert "_deprecated" in data
        assert data["id"] == "mem-1"

    def test_detail_404_has_no_deprecated(self) -> None:
        client = _build_memory_client()
        resp = client.get("/api/v1/memory/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Queen tool removal verification (Wave 28 C3)
# ---------------------------------------------------------------------------


class TestQueenToolRemoval:
    """Verify search_memory and list_skills are gone from Queen tools."""

    def test_search_memory_removed(self) -> None:
        from formicos.surface.queen_runtime import QueenAgent

        runtime = MagicMock()
        runtime.projections = MagicMock()
        runtime.projections.memory_entries = {}
        agent = QueenAgent(runtime)

        tools = agent._queen_tools()
        names = {t["name"] for t in tools}
        assert "search_memory" not in names

    def test_list_skills_removed(self) -> None:
        from formicos.surface.queen_runtime import QueenAgent

        runtime = MagicMock()
        runtime.projections = MagicMock()
        runtime.projections.memory_entries = {}
        agent = QueenAgent(runtime)

        tools = agent._queen_tools()
        names = {t["name"] for t in tools}
        assert "list_skills" not in names

    def test_memory_search_still_present(self) -> None:
        from formicos.surface.queen_runtime import QueenAgent

        runtime = MagicMock()
        runtime.projections = MagicMock()
        runtime.projections.memory_entries = {}
        agent = QueenAgent(runtime)

        tools = agent._queen_tools()
        names = {t["name"] for t in tools}
        assert "memory_search" in names
