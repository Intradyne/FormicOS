"""Wave 76 Team A: Data Truth tests — BudgetSnapshot, reverse index, reconciliation, spend persistence."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from formicos.surface.projections import (
    AgentProjection,
    BudgetSnapshot,
    ColonyProjection,
    ProjectionStore,
)


# ---------------------------------------------------------------------------
# Track 1: BudgetSnapshot.total_tokens includes reasoning
# ---------------------------------------------------------------------------


class TestBudgetSnapshotTotalTokens:
    def test_total_tokens_includes_reasoning(self) -> None:
        snap = BudgetSnapshot()
        snap.record_token_spend("m", 100, 50, 0.01, reasoning_tokens=25)
        assert snap.total_tokens == 175  # 100 + 50 + 25

    def test_total_tokens_zero_reasoning(self) -> None:
        snap = BudgetSnapshot()
        snap.record_token_spend("m", 100, 50, 0.01, reasoning_tokens=0)
        assert snap.total_tokens == 150

    def test_total_tokens_excludes_cache_read(self) -> None:
        snap = BudgetSnapshot()
        snap.record_token_spend("m", 100, 50, 0.01, reasoning_tokens=25, cache_read_tokens=40)
        assert snap.total_tokens == 175  # cache_read not included

    def test_total_tokens_accumulates(self) -> None:
        snap = BudgetSnapshot()
        snap.record_token_spend("m", 100, 50, 0.01, reasoning_tokens=25)
        snap.record_token_spend("m", 200, 100, 0.02, reasoning_tokens=50)
        assert snap.total_tokens == 525  # (100+200) + (50+100) + (25+50)


# ---------------------------------------------------------------------------
# Track 2: Agent-to-colony reverse index
# ---------------------------------------------------------------------------


class TestAgentColonyIndex:
    def _make_store_with_colony(self) -> tuple[ProjectionStore, str]:
        store = ProjectionStore()
        colony = ColonyProjection(
            id="c1",
            workspace_id="ws1",
            thread_id="t1",
            task="test",
            status="running",
            strategy="sequential",
            castes=[],
        )
        store.colonies["c1"] = colony
        return store, "c1"

    def test_index_populated_on_agent_creation(self) -> None:
        store, _ = self._make_store_with_colony()
        # Simulate what _on_agent_turn_started does
        colony = store.colonies["c1"]
        colony.agents["agent_1"] = AgentProjection(id="agent_1", caste="coder", model="m")
        store._agent_colony_index["agent_1"] = "c1"
        assert store._agent_colony_index["agent_1"] == "c1"

    def test_index_cleaned_on_colony_completed(self) -> None:
        store, _ = self._make_store_with_colony()
        colony = store.colonies["c1"]
        colony.agents["a1"] = AgentProjection(id="a1", caste="coder", model="m")
        colony.agents["a2"] = AgentProjection(id="a2", caste="reviewer", model="m")
        store._agent_colony_index["a1"] = "c1"
        store._agent_colony_index["a2"] = "c1"

        # Simulate cleanup
        for aid in colony.agents:
            store._agent_colony_index.pop(aid, None)

        assert "a1" not in store._agent_colony_index
        assert "a2" not in store._agent_colony_index

    def test_index_initialized_empty(self) -> None:
        store = ProjectionStore()
        assert store._agent_colony_index == {}

    def test_index_survives_missing_colony(self) -> None:
        store = ProjectionStore()
        # Index points to non-existent colony — fallback should handle it
        store._agent_colony_index["orphan"] = "missing_colony"
        result = store.colonies.get(store._agent_colony_index.get("orphan", ""))
        assert result is None


# ---------------------------------------------------------------------------
# Track 3: Budget reconciliation
# ---------------------------------------------------------------------------


class TestReconcileColonyCost:
    def _make_dispatcher(self) -> Any:
        """Create a minimal MaintenanceDispatcher-like object for testing."""
        from formicos.surface.self_maintenance import MaintenanceDispatcher

        runtime = MagicMock()
        runtime.settings.system.data_dir = "/tmp/test_formicos"
        runtime.projections.workspaces = {}
        dispatcher = MaintenanceDispatcher(runtime)
        return dispatcher

    def test_reconcile_adjusts_spend_upward(self) -> None:
        d = self._make_dispatcher()
        d._estimated_costs["c1"] = 0.10
        d._daily_spend["ws1"] = 0.10
        with patch.object(d, "_persist_daily_spend"):
            d.reconcile_colony_cost("ws1", "c1", 0.15)
        assert d._daily_spend["ws1"] == pytest.approx(0.15)
        assert "c1" not in d._estimated_costs

    def test_reconcile_adjusts_spend_downward(self) -> None:
        d = self._make_dispatcher()
        d._estimated_costs["c1"] = 0.20
        d._daily_spend["ws1"] = 0.20
        with patch.object(d, "_persist_daily_spend"):
            d.reconcile_colony_cost("ws1", "c1", 0.05)
        assert d._daily_spend["ws1"] == pytest.approx(0.05)

    def test_reconcile_clamps_to_zero(self) -> None:
        d = self._make_dispatcher()
        d._estimated_costs["c1"] = 0.50
        d._daily_spend["ws1"] = 0.10
        with patch.object(d, "_persist_daily_spend"):
            d.reconcile_colony_cost("ws1", "c1", 0.0)
        assert d._daily_spend["ws1"] == 0.0

    def test_reconcile_ignores_unknown_colony(self) -> None:
        d = self._make_dispatcher()
        d._daily_spend["ws1"] = 0.10
        d.reconcile_colony_cost("ws1", "unknown", 0.50)
        assert d._daily_spend["ws1"] == 0.10  # unchanged

    def test_reconcile_no_op_for_zero_zero(self) -> None:
        d = self._make_dispatcher()
        d._estimated_costs["c1"] = 0.0
        d._daily_spend["ws1"] = 0.10
        d.reconcile_colony_cost("ws1", "c1", 0.0)
        assert d._daily_spend["ws1"] == 0.10  # unchanged


# ---------------------------------------------------------------------------
# Track 4: Daily spend persistence
# ---------------------------------------------------------------------------


class TestDailySpendPersistence:
    def _make_dispatcher(self, tmp_path: Path) -> Any:
        from formicos.surface.self_maintenance import MaintenanceDispatcher

        runtime = MagicMock()
        runtime.settings.system.data_dir = str(tmp_path)
        runtime.projections.workspaces = {}
        return MaintenanceDispatcher(runtime)

    def test_persist_and_load(self, tmp_path: Path) -> None:
        d = self._make_dispatcher(tmp_path)
        d._daily_spend["ws1"] = 1.23
        d._persist_daily_spend("ws1")

        loaded = d._load_daily_spend("ws1")
        assert loaded == pytest.approx(1.23)

    def test_load_returns_zero_if_absent(self, tmp_path: Path) -> None:
        d = self._make_dispatcher(tmp_path)
        assert d._load_daily_spend("ws_nonexistent") == 0.0

    def test_load_returns_zero_if_stale(self, tmp_path: Path) -> None:
        d = self._make_dispatcher(tmp_path)
        # Write a file with yesterday's date
        path = d._spend_path("ws1")
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "date": "2020-01-01",  # definitely stale
            "spend": 5.0,
            "last_updated": "2020-01-01T12:00:00+00:00",
        }
        path.write_text(json.dumps(data))
        assert d._load_daily_spend("ws1") == 0.0

    def test_load_survives_corrupt_file(self, tmp_path: Path) -> None:
        d = self._make_dispatcher(tmp_path)
        path = d._spend_path("ws1")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json at all")
        assert d._load_daily_spend("ws1") == 0.0

    def test_restart_reloads_spend(self, tmp_path: Path) -> None:
        """Simulates restart: new dispatcher instance loads persisted spend."""
        d1 = self._make_dispatcher(tmp_path)
        d1._daily_spend["ws1"] = 2.50
        d1._persist_daily_spend("ws1")

        # New instance (simulates restart)
        d2 = self._make_dispatcher(tmp_path)
        loaded = d2._load_daily_spend("ws1")
        assert loaded == pytest.approx(2.50)

    def test_spend_path_structure(self, tmp_path: Path) -> None:
        d = self._make_dispatcher(tmp_path)
        path = d._spend_path("ws1")
        assert path.name == "daily_spend.json"
        assert "ws1" in str(path)
        assert ".formicos" in str(path)
