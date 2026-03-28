"""Tests for Wave 68 Track 5: addon capability metadata."""

from __future__ import annotations

from typing import Any

from formicos.surface.addon_loader import AddonManifest


class TestManifestCapabilityFields:
    def test_parses_with_capability_fields(self) -> None:
        manifest = AddonManifest(
            name="test-addon",
            version="1.0.0",
            description="Test addon",
            content_kinds=["documentation"],
            path_globs=["**/*.md", "**/*.rst"],
            search_tool="semantic_search_docs",
        )
        assert manifest.content_kinds == ["documentation"]
        assert manifest.path_globs == ["**/*.md", "**/*.rst"]
        assert manifest.search_tool == "semantic_search_docs"

    def test_parses_without_capability_fields(self) -> None:
        manifest = AddonManifest(
            name="legacy-addon",
            version="0.1.0",
        )
        assert manifest.content_kinds == []
        assert manifest.path_globs == []
        assert manifest.search_tool == ""

    def test_existing_fields_preserved(self) -> None:
        manifest = AddonManifest(
            name="full-addon",
            version="2.0.0",
            description="Full addon",
            content_kinds=["source_code"],
            path_globs=["**/*.py"],
            search_tool="semantic_search_code",
            tools=[],
            handlers=[],
            config=[],
        )
        assert manifest.name == "full-addon"
        assert manifest.tools == []
        assert manifest.content_kinds == ["source_code"]


class TestListAddonsCapabilityText:
    def _make_dispatcher(
        self, manifests: list[AddonManifest],
    ) -> Any:
        """Create a minimal mock dispatcher with manifests."""
        from unittest.mock import MagicMock

        dispatcher = MagicMock()
        dispatcher._addon_manifests = manifests
        dispatcher._addon_tool_specs = []
        dispatcher._handlers = {}
        # Bind the real method
        from formicos.surface.queen_tools import QueenToolDispatcher
        dispatcher._list_addons = (
            QueenToolDispatcher._list_addons.__get__(dispatcher)
        )
        return dispatcher

    def test_includes_capability_text(self) -> None:
        from formicos.surface.addon_loader import (
            AddonToolSpec,
        )

        manifest = AddonManifest(
            name="docs-index",
            description="Semantic documentation search",
            content_kinds=["documentation"],
            path_globs=["**/*.md", "**/*.rst"],
            search_tool="semantic_search_docs",
            tools=[
                AddonToolSpec(
                    name="semantic_search_docs",
                    description="Search docs",
                    handler="search.py::handle_semantic_search",
                ),
            ],
        )
        dispatcher = self._make_dispatcher([manifest])
        text, meta = dispatcher._list_addons()

        assert "Content: documentation" in text
        assert "Files: **/*.md, **/*.rst" in text
        assert "Search via: semantic_search_docs" in text

    def test_includes_refresh_path_when_present(self) -> None:
        from formicos.surface.addon_loader import (
            AddonTriggerSpec,
        )

        manifest = AddonManifest(
            name="docs-index",
            description="Docs search",
            content_kinds=["documentation"],
            search_tool="semantic_search_docs",
            triggers=[
                AddonTriggerSpec(
                    type="manual",
                    handler="indexer.py::incremental_reindex",
                ),
            ],
        )
        dispatcher = self._make_dispatcher([manifest])
        text, _ = dispatcher._list_addons()

        assert "Index via: indexer.py::incremental_reindex" in text

    def test_no_manifests_shows_empty(self) -> None:
        dispatcher = self._make_dispatcher([])
        text, _ = dispatcher._list_addons()
        assert "No addons installed" in text
