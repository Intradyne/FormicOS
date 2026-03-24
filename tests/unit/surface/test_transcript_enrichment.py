"""Tests for transcript_search result enrichment (Wave 33.5 Team 2)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from formicos.surface.runtime import Runtime


def _make_runtime() -> Runtime:
    """Build a minimal Runtime with mocked dependencies."""
    rt = object.__new__(Runtime)
    rt.projections = MagicMock()
    return rt


class TestTranscriptSearchEnrichment:
    """Verify transcript_search results include quality and extraction count."""

    @pytest.mark.asyncio
    async def test_quality_score_displayed(self) -> None:
        """Quality score appears in formatted result."""
        rt = _make_runtime()
        colony = SimpleNamespace(
            id="colony-abc123",
            workspace_id="default",
            status="completed",
            task="Build a REST API",
            round_records=[],
            artifacts=[],
            quality_score=0.87,
            skills_extracted=["s1", "s2", "s3"],
        )
        rt.projections.colonies = {"colony-abc123": colony}

        fn = rt.make_transcript_search_fn()
        assert fn is not None

        result = await fn(query="REST API", workspace_id="default", top_k=3)
        assert "quality: 0.87" in result

    @pytest.mark.asyncio
    async def test_knowledge_count_displayed(self) -> None:
        """Knowledge extraction count appears in formatted result."""
        rt = _make_runtime()
        colony = SimpleNamespace(
            id="colony-abc123",
            workspace_id="default",
            status="completed",
            task="Build a REST API",
            round_records=[],
            artifacts=[],
            quality_score=0.5,
            skills_extracted=["s1", "s2", "s3"],
        )
        rt.projections.colonies = {"colony-abc123": colony}

        fn = rt.make_transcript_search_fn()
        assert fn is not None

        result = await fn(query="REST API", workspace_id="default", top_k=3)
        assert "Knowledge extracted: 3 entries" in result

    @pytest.mark.asyncio
    async def test_missing_quality_graceful(self) -> None:
        """Missing quality_score does not crash and is not displayed."""
        rt = _make_runtime()
        colony = SimpleNamespace(
            id="colony-xyz789",
            workspace_id="default",
            status="completed",
            task="Run tests",
            round_records=[],
            artifacts=[],
            # No quality_score or skills_extracted attributes
        )
        rt.projections.colonies = {"colony-xyz789": colony}

        fn = rt.make_transcript_search_fn()
        assert fn is not None

        result = await fn(query="tests", workspace_id="default", top_k=3)
        assert "colony-x" in result
        assert "quality:" not in result
