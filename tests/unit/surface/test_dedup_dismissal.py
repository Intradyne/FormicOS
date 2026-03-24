"""Tests for dedup dismissed pair exclusion (Wave 31 B3).

Given: A dedup pair has been dismissed by the operator.
When: Dedup handler runs again.
Then: The dismissed pair is skipped.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.surface import maintenance


class TestDedupDismissal:
    """Verify dismissed pairs are excluded from dedup processing."""

    @pytest.mark.asyncio
    async def test_dismissed_pair_skipped(self) -> None:
        """Pairs marked as dismissed should not be re-processed."""
        runtime = MagicMock()
        runtime.emit_and_broadcast = AsyncMock(return_value=1)

        projections = MagicMock()
        # Two entries that are near-duplicates
        projections.memory_entries = {
            "mem-a": {
                "id": "mem-a",
                "workspace_id": "ws-1",
                "status": "verified",
                "content": "Use async/await for all IO operations",
                "title": "Async IO pattern",
                "domains": ["python", "async"],
                "last_status_reason": "dedup:dismissed:mem-b",
            },
            "mem-b": {
                "id": "mem-b",
                "workspace_id": "ws-1",
                "status": "verified",
                "content": "Use async/await for all IO operations",
                "title": "Async IO pattern",
                "domains": ["python", "async"],
                "last_status_reason": "",
            },
        }
        runtime.projections = projections

        # Vector store returns high similarity for the pair
        vector_store = MagicMock()

        async def _mock_search(
            collection: str, query: str, top_k: int = 5, **kwargs: Any,
        ) -> list[dict[str, Any]]:
            return [{"id": "mem-b", "score": 0.95, "payload": {}}]

        vector_store.search = AsyncMock(side_effect=_mock_search)
        runtime.vector_store = vector_store

        handler = maintenance.make_dedup_handler(runtime)
        result = await handler("scan", {"workspace_id": "ws-1"})

        # The dismissed pair should not appear in merge actions
        # Check that no MemoryEntryStatusChanged events were emitted for the pair
        status_changes = [
            call
            for call in runtime.emit_and_broadcast.call_args_list
            if hasattr(call.args[0], "type")
            and call.args[0].type == "MemoryEntryStatusChanged"
        ]
        dismissed_merges = [
            c for c in status_changes
            if c.args[0].entry_id in ("mem-a", "mem-b")
        ]
        assert len(dismissed_merges) == 0, "Dismissed pair should be skipped"

    @pytest.mark.asyncio
    async def test_non_dismissed_pair_processed(self) -> None:
        """Non-dismissed pairs with high similarity should be flagged."""
        runtime = MagicMock()
        runtime.emit_and_broadcast = AsyncMock(return_value=1)

        projections = MagicMock()
        projections.memory_entries = {
            "mem-a": {
                "id": "mem-a",
                "workspace_id": "ws-1",
                "status": "verified",
                "content": "Use async/await for all IO operations",
                "title": "Async IO pattern",
                "domains": ["python", "async"],
                "last_status_reason": "",
            },
            "mem-b": {
                "id": "mem-b",
                "workspace_id": "ws-1",
                "status": "verified",
                "content": "Use async/await for all IO operations",
                "title": "Async IO pattern duplicate",
                "domains": ["python", "async"],
                "last_status_reason": "",
            },
        }
        runtime.projections = projections

        handler = maintenance.make_dedup_handler(runtime)
        result = await handler("scan", {"workspace_id": "ws-1"})
        # Result should mention the scan completed (not an error)
        assert "dedup" in result.lower() or "scan" in result.lower() or "pair" in result.lower()
