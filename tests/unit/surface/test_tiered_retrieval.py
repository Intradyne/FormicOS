"""Tests for tiered retrieval with auto-escalation (Wave 34 A1)."""

from __future__ import annotations

from typing import Any

import pytest

from formicos.surface.knowledge_catalog import KnowledgeCatalog


def _make_result(
    *,
    item_id: str = "e1",
    title: str = "Test Entry",
    summary: str = "A test summary that is fairly long to test truncation behavior",
    content_preview: str = "Full content preview text here",
    score: float = 0.6,
    source_colony_id: str = "col-1",
    status: str = "active",
    domains: list[str] | None = None,
    conf_alpha: float = 15.0,
    conf_beta: float = 5.0,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "title": title,
        "summary": summary,
        "content_preview": content_preview,
        "score": score,
        "source_colony_id": source_colony_id,
        "status": status,
        "domains": domains or ["python", "testing"],
        "conf_alpha": conf_alpha,
        "conf_beta": conf_beta,
        "source_system": "institutional_memory",
        "created_at": "2026-03-18T00:00:00+00:00",
        "_thread_bonus": 0.0,
        "merged_from": [],
    }


def _make_catalog(
    search_results: list[dict[str, Any]],
) -> KnowledgeCatalog:
    """Create a catalog with mocked _search_thread_boosted."""
    catalog = KnowledgeCatalog(
        memory_store=None, vector_port=None,
        skill_collection="test", projections=None,
    )

    async def _mock_search(
        _query: str, **kwargs: Any,
    ) -> list[dict[str, Any]]:
        return search_results

    catalog._search_thread_boosted = _mock_search  # type: ignore[assignment]
    return catalog


class TestAutoEscalation:
    """Auto-escalation tier selection based on coverage."""

    @pytest.mark.asyncio
    async def test_summary_tier_two_sources_high_score(self) -> None:
        """2+ unique sources and top_score > 0.5 → summary."""
        results = [
            _make_result(item_id="e1", source_colony_id="col-1", score=0.7),
            _make_result(item_id="e2", source_colony_id="col-2", score=0.6),
        ]
        catalog = _make_catalog(results)
        out = await catalog.search_tiered(
            "test query", workspace_id="ws1",
        )
        assert all(item["tier"] == "summary" for item in out)

    @pytest.mark.asyncio
    async def test_standard_tier_one_source_moderate_score(self) -> None:
        """1 source and top_score 0.35-0.5 → standard."""
        results = [
            _make_result(item_id="e1", source_colony_id="col-1", score=0.4),
        ]
        catalog = _make_catalog(results)
        out = await catalog.search_tiered(
            "test query", workspace_id="ws1",
        )
        assert all(item["tier"] == "standard" for item in out)

    @pytest.mark.asyncio
    async def test_full_tier_no_good_matches(self) -> None:
        """No good matches → full."""
        results = [
            _make_result(item_id="e1", source_colony_id="", score=0.1),
        ]
        catalog = _make_catalog(results)
        out = await catalog.search_tiered(
            "test query", workspace_id="ws1",
        )
        assert all(item["tier"] == "full" for item in out)

    @pytest.mark.asyncio
    async def test_explicit_full_tier(self) -> None:
        """Explicit tier='full' always returns full regardless of scores."""
        results = [
            _make_result(item_id="e1", source_colony_id="col-1", score=0.9),
            _make_result(item_id="e2", source_colony_id="col-2", score=0.8),
        ]
        catalog = _make_catalog(results)
        out = await catalog.search_tiered(
            "test query", workspace_id="ws1", tier="full",
        )
        assert all(item["tier"] == "full" for item in out)

    @pytest.mark.asyncio
    async def test_empty_results_returns_empty(self) -> None:
        catalog = _make_catalog([])
        out = await catalog.search_tiered(
            "test query", workspace_id="ws1",
        )
        assert out == []


class TestFormatTier:
    """Tier-specific formatting of results."""

    def _catalog(self) -> KnowledgeCatalog:
        return KnowledgeCatalog(
            memory_store=None, vector_port=None,
            skill_collection="test", projections=None,
        )

    def test_summary_has_title_and_short_summary(self) -> None:
        result = _make_result(summary="A" * 200)
        catalog = self._catalog()
        formatted = catalog._format_tier([result], "summary")
        assert len(formatted) == 1
        item = formatted[0]
        assert item["tier"] == "summary"
        assert item["title"] == "Test Entry"
        assert len(item["summary"]) == 100
        assert "content_preview" not in item
        assert "domains" not in item
        assert "content" not in item

    def test_standard_has_preview_and_domains(self) -> None:
        result = _make_result()
        catalog = self._catalog()
        formatted = catalog._format_tier([result], "standard")
        item = formatted[0]
        assert item["tier"] == "standard"
        assert "content_preview" in item
        assert "domains" in item
        assert "decay_class" in item
        assert "content" not in item
        assert "conf_alpha" not in item

    def test_full_has_everything(self) -> None:
        result = _make_result()
        catalog = self._catalog()
        formatted = catalog._format_tier([result], "full")
        item = formatted[0]
        assert item["tier"] == "full"
        assert "content" in item
        assert "conf_alpha" in item
        assert "conf_beta" in item
        assert "merged_from" in item
        assert "co_occurrence_cluster" in item

    def test_standard_preview_truncated_to_200(self) -> None:
        result = _make_result(content_preview="X" * 500)
        catalog = self._catalog()
        formatted = catalog._format_tier([result], "standard")
        assert len(formatted[0]["content_preview"]) == 200

    def test_full_content_not_truncated(self) -> None:
        long_content = "Y" * 500
        result = _make_result(content_preview=long_content)
        catalog = self._catalog()
        formatted = catalog._format_tier([result], "full")
        assert formatted[0]["content"] == long_content


class TestSearchTieredTopK:
    """search_tiered respects top_k."""

    @pytest.mark.asyncio
    async def test_top_k_limits_results(self) -> None:
        results = [
            _make_result(item_id=f"e{i}", source_colony_id=f"col-{i}", score=0.8)
            for i in range(10)
        ]
        catalog = _make_catalog(results)
        out = await catalog.search_tiered(
            "test query", workspace_id="ws1", top_k=3,
        )
        assert len(out) == 3

    @pytest.mark.asyncio
    async def test_fetches_4x_top_k_for_headroom(self) -> None:
        """Verify _search_thread_boosted is called with 4x top_k."""
        catalog = KnowledgeCatalog(
            memory_store=None, vector_port=None,
            skill_collection="test", projections=None,
        )
        call_args: dict[str, Any] = {}

        async def _capture_search(
            _query: str, **kwargs: Any,
        ) -> list[dict[str, Any]]:
            call_args["query"] = _query
            call_args.update(kwargs)
            return []

        catalog._search_thread_boosted = _capture_search  # type: ignore[assignment]
        await catalog.search_tiered("q", workspace_id="ws1", top_k=5)
        assert call_args["top_k"] == 20
