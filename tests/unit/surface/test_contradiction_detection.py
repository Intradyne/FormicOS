"""Tests for contradiction detection (Wave 31 B3).

Given: Two verified entries with overlapping domains and opposite polarity.
When: Contradiction detection handler runs.
Then: The pair is flagged in the report.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.surface import maintenance


def _make_runtime_with_entries(entries: dict) -> MagicMock:
    runtime = MagicMock()
    runtime.emit_and_broadcast = AsyncMock(return_value=1)
    projections = MagicMock()
    projections.memory_entries = entries
    runtime.projections = projections
    return runtime


class TestContradictionDetection:
    """Verify contradiction detector flags opposing entries."""

    @pytest.mark.asyncio
    async def test_opposite_polarity_flagged(self) -> None:
        """Two entries with overlapping domains and opposite polarity are flagged."""
        entries = {
            "mem-pos": {
                "id": "mem-pos",
                "workspace_id": "ws-1",
                "status": "verified",
                "polarity": "positive",
                "domains": ["caching", "performance"],
                "confidence": 0.7,
            },
            "mem-neg": {
                "id": "mem-neg",
                "workspace_id": "ws-1",
                "status": "verified",
                "polarity": "negative",
                "domains": ["caching", "performance", "memory"],
                "confidence": 0.6,
            },
        }
        runtime = _make_runtime_with_entries(entries)
        handler = maintenance.make_contradiction_handler(runtime)
        result = await handler("scan", {"workspace_id": "ws-1"})

        assert "1 pair" in result or "1" in result
        assert "mem-pos" in result or "contradiction" in result.lower()

    @pytest.mark.asyncio
    async def test_same_polarity_not_flagged(self) -> None:
        """Two entries with same polarity should not be flagged."""
        entries = {
            "mem-a": {
                "id": "mem-a",
                "workspace_id": "ws-1",
                "status": "verified",
                "polarity": "positive",
                "domains": ["caching", "performance"],
                "confidence": 0.7,
            },
            "mem-b": {
                "id": "mem-b",
                "workspace_id": "ws-1",
                "status": "verified",
                "polarity": "positive",
                "domains": ["caching", "performance"],
                "confidence": 0.6,
            },
        }
        runtime = _make_runtime_with_entries(entries)
        handler = maintenance.make_contradiction_handler(runtime)
        result = await handler("scan", {"workspace_id": "ws-1"})

        assert "0 pair" in result or "0" in result.split("\n")[0]

    @pytest.mark.asyncio
    async def test_no_domain_overlap_not_flagged(self) -> None:
        """Entries with opposite polarity but no domain overlap are not flagged."""
        entries = {
            "mem-a": {
                "id": "mem-a",
                "workspace_id": "ws-1",
                "status": "verified",
                "polarity": "positive",
                "domains": ["caching"],
                "confidence": 0.7,
            },
            "mem-b": {
                "id": "mem-b",
                "workspace_id": "ws-1",
                "status": "verified",
                "polarity": "negative",
                "domains": ["networking"],
                "confidence": 0.6,
            },
        }
        runtime = _make_runtime_with_entries(entries)
        handler = maintenance.make_contradiction_handler(runtime)
        result = await handler("scan", {"workspace_id": "ws-1"})

        assert "0 pair" in result or "0" in result.split("\n")[0]

    @pytest.mark.asyncio
    async def test_neutral_polarity_excluded(self) -> None:
        """Entries with neutral or empty polarity should be excluded."""
        entries = {
            "mem-a": {
                "id": "mem-a",
                "workspace_id": "ws-1",
                "status": "verified",
                "polarity": "neutral",
                "domains": ["caching"],
                "confidence": 0.7,
            },
            "mem-b": {
                "id": "mem-b",
                "workspace_id": "ws-1",
                "status": "verified",
                "polarity": "negative",
                "domains": ["caching"],
                "confidence": 0.6,
            },
        }
        runtime = _make_runtime_with_entries(entries)
        handler = maintenance.make_contradiction_handler(runtime)
        result = await handler("scan", {"workspace_id": "ws-1"})

        assert "0 pair" in result or "0" in result.split("\n")[0]
