"""Tests for co-occurrence data collection (Wave 33 A5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from formicos.surface.projections import (
    CooccurrenceEntry,
    cooccurrence_key,
)


class TestCooccurrenceKey:
    def test_canonical_ordering(self) -> None:
        assert cooccurrence_key("b", "a") == ("a", "b")
        assert cooccurrence_key("a", "b") == ("a", "b")

    def test_same_id(self) -> None:
        assert cooccurrence_key("x", "x") == ("x", "x")


class TestCooccurrenceEntry:
    def test_defaults(self) -> None:
        entry = CooccurrenceEntry()
        assert entry.weight == 1.0
        assert entry.last_reinforced == ""
        assert entry.reinforcement_count == 0


class TestResultResultReinforcement:
    """Test co-occurrence reinforcement in _hook_confidence_update."""

    def _make_runtime(
        self, *, memory_entries: dict[str, Any] | None = None,
        accesses: list[dict[str, Any]] | None = None,
    ) -> Any:
        from unittest.mock import AsyncMock, MagicMock

        runtime = MagicMock()
        runtime.emit_and_broadcast = AsyncMock(return_value=1)

        projections = MagicMock()
        projections.memory_entries = memory_entries or {}
        projections.cooccurrence_weights = {}

        colony_proj = MagicMock()
        colony_proj.knowledge_accesses = accesses or []
        colony_proj.artifacts = []
        colony_proj.summary = ""
        projections.get_colony = MagicMock(return_value=colony_proj)
        projections.get_thread = MagicMock(return_value=None)

        runtime.projections = projections
        return runtime

    @pytest.mark.asyncio
    async def test_successful_colony_creates_pairs(self) -> None:
        """3 accessed entries should create 3 co-occurrence pairs."""
        from formicos.surface.colony_manager import ColonyManager

        entries = {
            f"mem-{i}": {
                "conf_alpha": 5.0,
                "conf_beta": 5.0,
                "created_at": datetime.now(UTC).isoformat(),
            }
            for i in range(3)
        }
        accesses = [
            {"items": [{"id": f"mem-{i}"} for i in range(3)]},
        ]
        runtime = self._make_runtime(memory_entries=entries, accesses=accesses)

        # Create manager mock — we just need the hook
        mgr = ColonyManager.__new__(ColonyManager)
        mgr._runtime = runtime

        await mgr._hook_confidence_update("col-1", "ws-1", "th-1", succeeded=True)

        # Should have 3 pairs: (0,1), (0,2), (1,2)
        weights = runtime.projections.cooccurrence_weights
        assert len(weights) == 3
        for key, entry in weights.items():
            assert entry.weight == 1.0  # initial weight
            assert entry.reinforcement_count == 1

    @pytest.mark.asyncio
    async def test_failed_colony_no_reinforcement(self) -> None:
        from formicos.surface.colony_manager import ColonyManager

        entries = {
            f"mem-{i}": {
                "conf_alpha": 5.0,
                "conf_beta": 5.0,
                "created_at": datetime.now(UTC).isoformat(),
            }
            for i in range(3)
        }
        accesses = [{"items": [{"id": f"mem-{i}"} for i in range(3)]}]
        runtime = self._make_runtime(memory_entries=entries, accesses=accesses)

        mgr = ColonyManager.__new__(ColonyManager)
        mgr._runtime = runtime

        await mgr._hook_confidence_update("col-1", "ws-1", "th-1", succeeded=False)

        weights = runtime.projections.cooccurrence_weights
        assert len(weights) == 0

    @pytest.mark.asyncio
    async def test_weight_capped_at_10(self) -> None:
        from formicos.surface.colony_manager import ColonyManager

        entries = {
            "mem-0": {"conf_alpha": 5.0, "conf_beta": 5.0, "created_at": datetime.now(UTC).isoformat()},
            "mem-1": {"conf_alpha": 5.0, "conf_beta": 5.0, "created_at": datetime.now(UTC).isoformat()},
        }
        accesses = [{"items": [{"id": "mem-0"}, {"id": "mem-1"}]}]
        runtime = self._make_runtime(memory_entries=entries, accesses=accesses)

        # Pre-seed at near-cap weight
        key = cooccurrence_key("mem-0", "mem-1")
        runtime.projections.cooccurrence_weights[key] = CooccurrenceEntry(
            weight=9.5, last_reinforced=datetime.now(UTC).isoformat(), reinforcement_count=50,
        )

        mgr = ColonyManager.__new__(ColonyManager)
        mgr._runtime = runtime

        await mgr._hook_confidence_update("col-1", "ws-1", "th-1", succeeded=True)

        entry = runtime.projections.cooccurrence_weights[key]
        assert entry.weight == 10.0  # capped, not 9.5 * 1.1 = 10.45


class TestCooccurrenceDecay:
    @pytest.mark.asyncio
    async def test_decay_reduces_weight(self) -> None:
        from unittest.mock import MagicMock

        from formicos.surface.maintenance import make_cooccurrence_decay_handler

        runtime = MagicMock()
        old_time = (datetime.now(UTC) - timedelta(days=100)).isoformat()
        key = ("a", "b")
        runtime.projections.cooccurrence_weights = {
            key: CooccurrenceEntry(weight=5.0, last_reinforced=old_time, reinforcement_count=10),
        }

        handler = make_cooccurrence_decay_handler(runtime)
        result = await handler("", {})

        entry = runtime.projections.cooccurrence_weights[key]
        assert entry.weight < 5.0
        assert "1 pairs decayed" in result

    @pytest.mark.asyncio
    async def test_prune_below_threshold(self) -> None:
        from unittest.mock import MagicMock

        from formicos.surface.maintenance import make_cooccurrence_decay_handler

        runtime = MagicMock()
        old_time = (datetime.now(UTC) - timedelta(days=500)).isoformat()
        key = ("a", "b")
        runtime.projections.cooccurrence_weights = {
            key: CooccurrenceEntry(weight=0.2, last_reinforced=old_time, reinforcement_count=1),
        }

        handler = make_cooccurrence_decay_handler(runtime)
        result = await handler("", {})

        assert key not in runtime.projections.cooccurrence_weights
        assert "pruned" in result

    @pytest.mark.asyncio
    async def test_distillation_candidates_populated(self) -> None:
        """Wave 34.5: dense clusters flagged as distillation candidates."""
        from unittest.mock import MagicMock

        from formicos.surface.maintenance import make_cooccurrence_decay_handler

        runtime = MagicMock()
        now = datetime.now(UTC).isoformat()
        # Build a 5-node fully connected cluster with high weights
        entries = [f"e{i}" for i in range(5)]
        weights: dict[tuple[str, str], CooccurrenceEntry] = {}
        for i, a in enumerate(entries):
            for b in entries[i + 1:]:
                key = cooccurrence_key(a, b)
                weights[key] = CooccurrenceEntry(
                    weight=5.0, last_reinforced=now, reinforcement_count=10,
                )
        runtime.projections.cooccurrence_weights = weights
        runtime.projections.distillation_candidates = []

        handler = make_cooccurrence_decay_handler(runtime)
        result = await handler("", {})

        assert "distillation candidates" in result
        # Cluster should qualify: 5 entries, avg weight > 3.0
        assert len(runtime.projections.distillation_candidates) == 1
        assert sorted(runtime.projections.distillation_candidates[0]) == sorted(entries)

    @pytest.mark.asyncio
    async def test_no_distillation_when_cluster_too_small(self) -> None:
        """Clusters with < 5 entries are not distillation candidates."""
        from unittest.mock import MagicMock

        from formicos.surface.maintenance import make_cooccurrence_decay_handler

        runtime = MagicMock()
        now = datetime.now(UTC).isoformat()
        weights = {
            cooccurrence_key("a", "b"): CooccurrenceEntry(
                weight=5.0, last_reinforced=now, reinforcement_count=10,
            ),
            cooccurrence_key("b", "c"): CooccurrenceEntry(
                weight=5.0, last_reinforced=now, reinforcement_count=10,
            ),
        }
        runtime.projections.cooccurrence_weights = weights
        runtime.projections.distillation_candidates = []

        handler = make_cooccurrence_decay_handler(runtime)
        await handler("", {})

        assert runtime.projections.distillation_candidates == []
