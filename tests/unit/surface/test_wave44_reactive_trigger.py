"""Wave 44 Pillar 4A: Reactive forage trigger detection tests.

Verifies that knowledge_catalog detects low-confidence/thin coverage
and emits a ForageRequest signal without performing network I/O.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from formicos.surface.knowledge_catalog import KnowledgeCatalog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_catalog(
    *,
    memory_store: Any = None,
    vector_port: Any = None,
    projections: Any = None,
) -> KnowledgeCatalog:
    """Create a KnowledgeCatalog with minimal mocks."""
    return KnowledgeCatalog(
        memory_store=memory_store,
        vector_port=vector_port,
        skill_collection="test-skills",
        projections=projections,
    )


def _make_result(
    entry_id: str,
    score: float,
    *,
    source_colony_id: str = "col-1",
    status: str = "verified",
    conf_alpha: float = 10.0,
    conf_beta: float = 5.0,
) -> dict[str, Any]:
    """Create a minimal search result dict."""
    return {
        "id": entry_id,
        "title": f"Entry {entry_id}",
        "score": score,
        "source_colony_id": source_colony_id,
        "status": status,
        "conf_alpha": conf_alpha,
        "conf_beta": conf_beta,
        "domains": ["python"],
        "created_at": "2026-03-19T12:00:00+00:00",
        "content_preview": "Some content",
        "summary": "A summary",
        "decay_class": "stable",
    }


# ---------------------------------------------------------------------------
# Trigger detection tests
# ---------------------------------------------------------------------------


class TestForageTriggerDetection:
    """Test the _detect_forage_trigger method."""

    def test_no_trigger_when_results_strong(self) -> None:
        catalog = _make_catalog()
        results = [
            _make_result("e1", 0.8, source_colony_id="col-1"),
            _make_result("e2", 0.7, source_colony_id="col-2"),
        ]
        signal = catalog._detect_forage_trigger(
            results,
            query="python patterns",
            workspace_id="ws-1",
            thread_id="",
            source_colony_id="",
            top_score=0.8,
            unique_sources=2,
        )
        assert signal is None

    def test_trigger_when_top_score_low(self) -> None:
        catalog = _make_catalog()
        results = [
            _make_result("e1", 0.2, source_colony_id="col-1"),
        ]
        signal = catalog._detect_forage_trigger(
            results,
            query="obscure topic",
            workspace_id="ws-1",
            thread_id="th-1",
            source_colony_id="col-a",
            top_score=0.2,
            unique_sources=1,
        )
        assert signal is not None
        assert signal["trigger"] == "reactive"
        assert signal["workspace_id"] == "ws-1"
        assert "obscure topic" in signal["gap_description"]

    def test_trigger_when_few_results(self) -> None:
        catalog = _make_catalog()
        results = [
            _make_result("e1", 0.4, source_colony_id="col-1"),
        ]
        signal = catalog._detect_forage_trigger(
            results,
            query="rare query",
            workspace_id="ws-1",
            thread_id="",
            source_colony_id="",
            top_score=0.4,
            unique_sources=1,
        )
        assert signal is not None

    def test_no_trigger_with_many_sources(self) -> None:
        catalog = _make_catalog()
        results = [
            _make_result("e1", 0.5, source_colony_id="col-1"),
            _make_result("e2", 0.4, source_colony_id="col-2"),
            _make_result("e3", 0.3, source_colony_id="col-3"),
        ]
        signal = catalog._detect_forage_trigger(
            results,
            query="python patterns",
            workspace_id="ws-1",
            thread_id="",
            source_colony_id="",
            top_score=0.5,
            unique_sources=3,
        )
        assert signal is None

    def test_trigger_includes_domains(self) -> None:
        catalog = _make_catalog()
        results = [
            _make_result("e1", 0.1, source_colony_id="col-1"),
        ]
        results[0]["domains"] = ["python", "asyncio"]
        signal = catalog._detect_forage_trigger(
            results,
            query="asyncio patterns",
            workspace_id="ws-1",
            thread_id="th-1",
            source_colony_id="col-x",
            top_score=0.1,
            unique_sources=1,
        )
        assert signal is not None
        assert "python" in signal["domains"]
        assert "asyncio" in signal["domains"]

    def test_trigger_preserves_thread_and_colony(self) -> None:
        catalog = _make_catalog()
        results = [_make_result("e1", 0.1)]
        signal = catalog._detect_forage_trigger(
            results,
            query="query",
            workspace_id="ws-1",
            thread_id="th-42",
            source_colony_id="col-99",
            top_score=0.1,
            unique_sources=0,
        )
        assert signal is not None
        assert signal["thread_id"] == "th-42"
        assert signal["colony_id"] == "col-99"


class TestSearchTieredForageTrigger:
    """Test that search_tiered attaches forage signals to results."""

    @pytest.mark.asyncio
    async def test_forage_signal_attached_to_thin_results(self) -> None:
        """When coverage is thin, search_tiered should attach _forage_requested."""
        catalog = _make_catalog()

        # Mock the internal search to return weak results
        weak_results = [
            _make_result("e1", 0.2, source_colony_id="col-1"),
        ]

        with patch.object(
            catalog, "_search_thread_boosted",
            new_callable=AsyncMock,
            return_value=weak_results,
        ):
            results = await catalog.search_tiered(
                "obscure topic",
                workspace_id="ws-1",
                thread_id="th-1",
                top_k=5,
                tier="auto",
            )

        # Results should have forage signal attached
        assert len(results) >= 1
        assert results[0].get("_forage_requested") is True
        signal = results[0].get("_forage_signal")
        assert signal is not None
        assert signal["trigger"] == "reactive"

    @pytest.mark.asyncio
    async def test_no_forage_signal_on_strong_results(self) -> None:
        """When coverage is good, no forage signal should be attached."""
        catalog = _make_catalog()

        strong_results = [
            _make_result("e1", 0.8, source_colony_id="col-1"),
            _make_result("e2", 0.7, source_colony_id="col-2"),
            _make_result("e3", 0.6, source_colony_id="col-3"),
        ]

        with patch.object(
            catalog, "_search_thread_boosted",
            new_callable=AsyncMock,
            return_value=strong_results,
        ):
            results = await catalog.search_tiered(
                "well-known topic",
                workspace_id="ws-1",
                top_k=5,
                tier="auto",
            )

        # No forage signal
        for r in results:
            assert r.get("_forage_requested") is not True
