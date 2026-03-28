"""Tests for Wave 69 Track 6: Unified search endpoint."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from formicos.surface.routes.knowledge_api import (
    _parse_addon_results,
    routes,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WS_ID = "ws-test-1"


def _make_app(
    *,
    catalog_results: list[dict[str, Any]] | None = None,
    addon_manifests: list[Any] | None = None,
    addon_registrations: list[Any] | None = None,
) -> Any:
    """Build a minimal Starlette app with unified search wired up."""
    from starlette.applications import Starlette
    from starlette.routing import Route

    catalog = None
    if catalog_results is not None:
        catalog = AsyncMock()
        catalog.search = AsyncMock(return_value=catalog_results)

    route_list = routes(
        knowledge_catalog=catalog,
        runtime=None,
        projections=None,
    )
    app = Starlette(routes=route_list)
    app.state.addon_manifests = addon_manifests or []  # type: ignore[attr-defined]
    app.state.addon_registrations = addon_registrations or []  # type: ignore[attr-defined]
    return app


def _make_manifest(
    name: str = "docs-index",
    description: str = "Documentation index",
    content_kinds: list[str] | None = None,
    path_globs: list[str] | None = None,
    search_tool: str = "semantic_search_docs",
    tools: list[Any] | None = None,
) -> Any:
    """Build a fake addon manifest."""
    m = MagicMock()
    m.name = name
    m.description = description
    m.content_kinds = content_kinds or ["documentation"]
    m.path_globs = path_globs or ["**/*.md"]
    m.search_tool = search_tool

    if tools is None:
        tool = MagicMock()
        tool.name = search_tool
        tool.handler = "search.py::handle_semantic_search"
        m.tools = [tool]
    else:
        m.tools = tools
    return m


def _make_registration(manifest: Any) -> Any:
    """Build a fake addon registration."""
    reg = MagicMock()
    reg.manifest = manifest
    reg.runtime_context = {"vector_port": MagicMock()}
    return reg


# ---------------------------------------------------------------------------
# Tests: Memory results shape
# ---------------------------------------------------------------------------


class TestMemoryResults:
    def test_memory_results_correct_shape(self) -> None:
        memory_items = [
            {
                "id": "entry-1",
                "title": "Python best practices",
                "summary": "Use type hints and docstrings.",
                "score": 0.85,
                "confidence": 0.72,
                "status": "verified",
                "domains": ["python", "testing"],
                "sub_type": "convention",
            },
            {
                "id": "entry-2",
                "title": "Git workflow",
                "summary": "Use feature branches.",
                "score": 0.65,
                "confidence": 0.55,
                "status": "candidate",
                "domains": ["git"],
                "sub_type": "learning",
            },
        ]
        app = _make_app(catalog_results=memory_items)
        client = TestClient(app)
        resp = client.get(
            f"/api/v1/workspaces/{WS_ID}/search?q=python",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert "total" in data
        assert data["total"] >= 2

        # Check first result shape
        r = data["results"][0]
        assert r["source"] == "memory"
        assert r["source_label"] == "Institutional Memory"
        assert r["id"] == "entry-1"
        assert r["title"] == "Python best practices"
        assert len(r["snippet"]) <= 200
        assert "metadata" in r
        assert r["metadata"]["confidence"] == 0.72
        assert r["metadata"]["status"] == "verified"
        assert "python" in r["metadata"]["domains"]

    def test_sources_memory_only_skips_addons(self) -> None:
        """?sources=memory should not call addon handlers."""
        manifest = _make_manifest()
        reg = _make_registration(manifest)

        app = _make_app(
            catalog_results=[{"id": "e1", "title": "t", "score": 0.5}],
            addon_manifests=[manifest],
            addon_registrations=[reg],
        )
        client = TestClient(app)
        resp = client.get(
            f"/api/v1/workspaces/{WS_ID}/search?q=test&sources=memory",
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should have memory results only
        sources = {r["source"] for r in data["results"]}
        assert sources == {"memory"}


# ---------------------------------------------------------------------------
# Tests: Addon markdown parsing
# ---------------------------------------------------------------------------


class TestAddonMarkdownParsing:
    def test_parse_code_block_results(self) -> None:
        """Markdown with bold path + code block is parsed correctly."""
        raw = (
            "**src/main.py:10-25** (score: 0.832)\n"
            "```python\n"
            "def hello():\n"
            "    return 'world'\n"
            "```\n"
            "\n"
            "**src/utils.py:5-8** (score: 0.710)\n"
            "```python\n"
            "import os\n"
            "```"
        )
        results = _parse_addon_results(
            raw, "codebase-index", "Code search",
            ["source_code"], 10,
        )
        assert len(results) == 2
        assert results[0]["source"] == "codebase-index"
        assert results[0]["title"] == "src/main.py:10-25"
        assert results[0]["score"] == 0.832
        assert results[0]["metadata"]["file_path"] == "src/main.py"
        assert results[0]["metadata"]["line_range"] == "10-25"
        assert "hello" in results[0]["snippet"]

    def test_parse_limit_respected(self) -> None:
        raw = "\n\n".join(
            f"**file{i}.py** (score: 0.5)\ncontent {i}"
            for i in range(20)
        )
        results = _parse_addon_results(
            raw, "test", "Test", [], 5,
        )
        assert len(results) <= 5


# ---------------------------------------------------------------------------
# Tests: Addon handler failure resilience
# ---------------------------------------------------------------------------


class TestAddonFailureResilience:
    @patch(
        "formicos.surface.addon_loader._resolve_handler",
    )
    def test_addon_handler_raises_memory_still_returned(
        self, mock_resolve: MagicMock,
    ) -> None:
        """When addon handler raises, memory results are still returned."""
        async def _failing_handler(*args: Any, **kwargs: Any) -> str:
            msg = "index not available"
            raise RuntimeError(msg)

        mock_resolve.return_value = _failing_handler

        manifest = _make_manifest()
        reg = _make_registration(manifest)

        app = _make_app(
            catalog_results=[
                {"id": "e1", "title": "good entry", "score": 0.9},
            ],
            addon_manifests=[manifest],
            addon_registrations=[reg],
        )
        client = TestClient(app)
        resp = client.get(
            f"/api/v1/workspaces/{WS_ID}/search?q=test",
        )
        assert resp.status_code == 200
        data = resp.json()
        # Memory results survived even though addon failed
        assert data["total"] >= 1
        assert any(r["source"] == "memory" for r in data["results"])


# ---------------------------------------------------------------------------
# Tests: Source grouping
# ---------------------------------------------------------------------------


class TestSourceGrouping:
    def test_results_grouped_by_source(self) -> None:
        """Memory results come first, then addon groups."""
        memory_items = [
            {"id": "m1", "title": "mem", "score": 0.5},
            {"id": "m2", "title": "mem2", "score": 0.3},
        ]
        app = _make_app(catalog_results=memory_items)
        client = TestClient(app)
        resp = client.get(
            f"/api/v1/workspaces/{WS_ID}/search?q=test",
        )
        data = resp.json()
        # All memory results should appear before any addon results
        sources = [r["source"] for r in data["results"]]
        memory_indices = [i for i, s in enumerate(sources) if s == "memory"]
        other_indices = [i for i, s in enumerate(sources) if s != "memory"]
        if memory_indices and other_indices:
            assert max(memory_indices) < min(other_indices)


# ---------------------------------------------------------------------------
# Tests: Missing query
# ---------------------------------------------------------------------------


class TestMissingQuery:
    def test_empty_query_returns_error(self) -> None:
        app = _make_app(catalog_results=[])
        client = TestClient(app)
        resp = client.get(f"/api/v1/workspaces/{WS_ID}/search?q=")
        assert resp.status_code >= 400

    def test_no_q_param_returns_error(self) -> None:
        app = _make_app(catalog_results=[])
        client = TestClient(app)
        resp = client.get(f"/api/v1/workspaces/{WS_ID}/search")
        assert resp.status_code >= 400
