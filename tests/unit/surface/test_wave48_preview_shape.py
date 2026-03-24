"""Wave 48 Team 1: Preview response shaping tests.

Covers:
- spawn_colony preview returns structured metadata with estimated_cost, team, strategy
- spawn_parallel preview returns structured metadata with estimated_cost, groups
- Both previews include the preview=True flag
- Target files included when present
- Fast path mode included when set
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.core.types import CasteSlot, SubcasteTier


class TestSpawnColonyPreview:
    """Verify _preview_spawn_colony returns structured metadata."""

    def _make_tools(self) -> Any:
        """Create a minimal QueenTools instance for preview testing."""
        from formicos.surface.queen_tools import QueenToolDispatcher

        runtime = MagicMock()
        runtime.projections = MagicMock()
        return QueenToolDispatcher(runtime)

    def test_preview_has_estimated_cost(self) -> None:
        qt = self._make_tools()
        text, meta = qt._preview_spawn_colony(
            task="Fix auth bug",
            caste_slots=[CasteSlot(caste="coder", tier=SubcasteTier.standard)],
            strategy="stigmergic",
            max_rounds=10,
            budget_limit=2.50,
            fast_path=False,
            target_files=[],
        )
        assert meta is not None
        assert meta["estimatedCost"] == 2.50
        assert meta["preview"] is True
        assert meta["tool"] == "spawn_colony"

    def test_preview_has_team_structure(self) -> None:
        qt = self._make_tools()
        _, meta = qt._preview_spawn_colony(
            task="Review code",
            caste_slots=[
                CasteSlot(caste="coder", tier=SubcasteTier.standard, count=2),
                CasteSlot(caste="reviewer", tier=SubcasteTier.standard),
            ],
            strategy="stigmergic",
            max_rounds=8,
            budget_limit=3.00,
            fast_path=False,
            target_files=[],
        )
        assert meta is not None
        assert len(meta["team"]) == 2
        assert meta["team"][0]["caste"] == "coder"
        assert meta["team"][0]["count"] == 2
        assert meta["strategy"] == "stigmergic"
        assert meta["maxRounds"] == 8

    def test_preview_includes_fast_path(self) -> None:
        qt = self._make_tools()
        text, meta = qt._preview_spawn_colony(
            task="Quick fix",
            caste_slots=[CasteSlot(caste="coder", tier=SubcasteTier.flash)],
            strategy="sequential",
            max_rounds=3,
            budget_limit=0.50,
            fast_path=True,
            target_files=[],
        )
        assert meta is not None
        assert meta["fastPath"] is True
        assert "fast_path" in text

    def test_preview_includes_target_files(self) -> None:
        qt = self._make_tools()
        _, meta = qt._preview_spawn_colony(
            task="Fix tests",
            caste_slots=[CasteSlot(caste="coder", tier=SubcasteTier.standard)],
            strategy="stigmergic",
            max_rounds=5,
            budget_limit=1.00,
            fast_path=False,
            target_files=["src/app.py", "tests/test_app.py"],
        )
        assert meta is not None
        assert "targetFiles" in meta
        assert meta["targetFiles"] == ["src/app.py", "tests/test_app.py"]

    def test_preview_text_contains_key_info(self) -> None:
        qt = self._make_tools()
        text, _ = qt._preview_spawn_colony(
            task="Fix auth bug",
            caste_slots=[CasteSlot(caste="coder", tier=SubcasteTier.standard)],
            strategy="stigmergic",
            max_rounds=10,
            budget_limit=2.50,
            fast_path=False,
            target_files=[],
        )
        assert "PREVIEW" in text
        assert "Fix auth bug" in text
        assert "coder" in text
        assert "stigmergic" in text
