"""Tests for inline dedup check at extraction time (Wave 33 A2)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.surface.colony_manager import ColonyManager


def _make_manager(
    *,
    memory_entries: dict[str, dict[str, Any]] | None = None,
    search_hits: list[Any] | None = None,
) -> ColonyManager:
    """Build a ColonyManager with mock runtime for inline dedup testing."""
    runtime = MagicMock()
    runtime.emit_and_broadcast = AsyncMock(return_value=1)

    projections = MagicMock()
    projections.memory_entries = memory_entries or {}
    runtime.projections = projections

    # Mock memory_store.search
    memory_store = MagicMock()
    memory_store.search = AsyncMock(return_value=search_hits or [])
    runtime.memory_store = memory_store

    mgr = ColonyManager.__new__(ColonyManager)
    mgr._runtime = runtime
    return mgr


def _make_hit(entry_id: str, score: float) -> Any:
    """Create a mock Qdrant search hit."""
    hit = MagicMock()
    hit.score = score
    hit.id = entry_id
    hit.payload = {"id": entry_id}
    return hit


class TestInlineDedup:
    @pytest.mark.asyncio
    async def test_above_threshold_returns_id(self) -> None:
        """Cosine > 0.92 should return the existing entry ID."""
        entries = {
            "mem-existing": {
                "conf_alpha": 6.0,
                "conf_beta": 4.0,
                "thread_id": "th-1",
            },
        }
        hit = _make_hit("mem-existing", 0.95)
        mgr = _make_manager(memory_entries=entries, search_hits=[hit])

        result = await mgr._check_inline_dedup("test content", "ws-1", succeeded=True)

        assert result == "mem-existing"
        # Should have emitted MemoryConfidenceUpdated
        mgr._runtime.emit_and_broadcast.assert_called_once()
        event = mgr._runtime.emit_and_broadcast.call_args[0][0]
        assert event.entry_id == "mem-existing"
        assert event.reason == "inline_dedup"
        assert event.new_alpha == 7.0  # 6.0 + 1.0 (success)

    @pytest.mark.asyncio
    async def test_below_threshold_returns_none(self) -> None:
        """Cosine <= 0.92 should return None (no dedup)."""
        hit = _make_hit("mem-existing", 0.88)
        mgr = _make_manager(search_hits=[hit])

        result = await mgr._check_inline_dedup("test content", "ws-1", succeeded=True)

        assert result is None
        mgr._runtime.emit_and_broadcast.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_projection_returns_none(self) -> None:
        """No search hits should return None."""
        mgr = _make_manager(search_hits=[])

        result = await mgr._check_inline_dedup("test content", "ws-1", succeeded=True)

        assert result is None

    @pytest.mark.asyncio
    async def test_failed_colony_reinforces_beta(self) -> None:
        """Failed colony should increment beta, not alpha."""
        entries = {
            "mem-existing": {
                "conf_alpha": 5.0,
                "conf_beta": 5.0,
                "thread_id": "",
            },
        }
        hit = _make_hit("mem-existing", 0.96)
        mgr = _make_manager(memory_entries=entries, search_hits=[hit])

        result = await mgr._check_inline_dedup("test content", "ws-1", succeeded=False)

        assert result == "mem-existing"
        event = mgr._runtime.emit_and_broadcast.call_args[0][0]
        assert event.new_alpha == 5.0  # unchanged
        assert event.new_beta == 6.0  # 5.0 + 1.0

    @pytest.mark.asyncio
    async def test_empty_content_returns_none(self) -> None:
        """Empty content should short-circuit."""
        mgr = _make_manager()
        result = await mgr._check_inline_dedup("", "ws-1", succeeded=True)
        assert result is None

    @pytest.mark.asyncio
    async def test_search_error_returns_none(self) -> None:
        """Search errors should not block extraction."""
        runtime = MagicMock()
        runtime.emit_and_broadcast = AsyncMock(return_value=1)
        runtime.projections = MagicMock()
        runtime.projections.memory_entries = {}
        runtime.memory_store = MagicMock()
        runtime.memory_store.search = AsyncMock(side_effect=RuntimeError("boom"))

        mgr = ColonyManager.__new__(ColonyManager)
        mgr._runtime = runtime

        result = await mgr._check_inline_dedup("test content", "ws-1", succeeded=True)
        assert result is None
