"""Tests for qualityScore and skillsExtracted in view_state snapshot."""

from __future__ import annotations

from pathlib import Path

from formicos.core.settings import load_config
from formicos.surface.projections import (
    ColonyProjection,
    ProjectionStore,
    ThreadProjection,
    WorkspaceProjection,
)
from formicos.surface.view_state import build_snapshot

_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "formicos.yaml"
_SETTINGS = load_config(_CONFIG_PATH)


def _store_with_colony(
    quality_score: float = 0.0,
    skills_extracted: int = 0,
) -> ProjectionStore:
    """Build a ProjectionStore with one workspace/thread/colony."""
    store = ProjectionStore()
    colony = ColonyProjection(
        id="col-1",
        thread_id="th-1",
        workspace_id="ws-1",
        task="test task",
        status="completed",
        quality_score=quality_score,
        skills_extracted=skills_extracted,
    )
    thread = ThreadProjection(id="th-1", workspace_id="ws-1", name="main")
    thread.colonies["col-1"] = colony
    ws = WorkspaceProjection(id="ws-1", name="default")
    ws.threads["th-1"] = thread
    store.workspaces["ws-1"] = ws
    store.colonies["col-1"] = colony
    return store


class TestSnapshotFields:
    """Verify qualityScore and skillsExtracted appear in snapshot."""

    def test_quality_score_in_snapshot(self) -> None:
        store = _store_with_colony(quality_score=0.85)
        snapshot = build_snapshot(store, _SETTINGS)
        colony_node = snapshot["tree"][0]["children"][0]["children"][0]
        assert colony_node["qualityScore"] == 0.85

    def test_skills_extracted_in_snapshot(self) -> None:
        store = _store_with_colony(skills_extracted=3)
        snapshot = build_snapshot(store, _SETTINGS)
        colony_node = snapshot["tree"][0]["children"][0]["children"][0]
        assert colony_node["skillsExtracted"] == 3

    def test_defaults_zero(self) -> None:
        store = _store_with_colony()
        snapshot = build_snapshot(store, _SETTINGS)
        colony_node = snapshot["tree"][0]["children"][0]["children"][0]
        assert colony_node["qualityScore"] == 0.0
        assert colony_node["skillsExtracted"] == 0

    def test_runtime_registry_derives_no_key_for_cloud_models(
        self,
        monkeypatch,
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        store = _store_with_colony()
        snapshot = build_snapshot(store, _SETTINGS)
        registry = {
            entry["address"]: entry
            for entry in snapshot["runtimeConfig"]["models"]["registry"]
        }
        assert registry["openai/gpt-4o"]["status"] == "no_key"

    def test_active_goal_defaults_to_task(self) -> None:
        store = _store_with_colony()
        snapshot = build_snapshot(store, _SETTINGS)
        colony_node = snapshot["tree"][0]["children"][0]["children"][0]
        assert colony_node["activeGoal"] == "test task"

    def test_active_goal_from_projection(self) -> None:
        store = _store_with_colony()
        store.colonies["col-1"].active_goal = "redirected goal"
        snapshot = build_snapshot(store, _SETTINGS)
        colony_node = snapshot["tree"][0]["children"][0]["children"][0]
        assert colony_node["activeGoal"] == "redirected goal"

    def test_redirect_history_empty_default(self) -> None:
        store = _store_with_colony()
        snapshot = build_snapshot(store, _SETTINGS)
        colony_node = snapshot["tree"][0]["children"][0]["children"][0]
        assert colony_node["redirectHistory"] == []

    def test_redirect_history_populated(self) -> None:
        store = _store_with_colony()
        store.colonies["col-1"].redirect_history = [
            {"round": 2, "trigger": "queen", "newGoal": "new goal", "reason": "needed"},
        ]
        snapshot = build_snapshot(store, _SETTINGS)
        colony_node = snapshot["tree"][0]["children"][0]["children"][0]
        assert len(colony_node["redirectHistory"]) == 1
        assert colony_node["redirectHistory"][0]["trigger"] == "queen"

    def test_routing_override_none_default(self) -> None:
        store = _store_with_colony()
        snapshot = build_snapshot(store, _SETTINGS)
        colony_node = snapshot["tree"][0]["children"][0]["children"][0]
        assert colony_node["routingOverride"] is None

    def test_routing_override_populated(self) -> None:
        store = _store_with_colony()
        store.colonies["col-1"].routing_override = {
            "tier": "heavy",
            "reason": "complex task",
            "set_at_round": 3,
        }
        snapshot = build_snapshot(store, _SETTINGS)
        colony_node = snapshot["tree"][0]["children"][0]["children"][0]
        override = colony_node["routingOverride"]
        assert override["tier"] == "heavy"
        assert override["reason"] == "complex task"
        assert override["set_at_round"] == 3

    def test_runtime_registry_prefers_probed_local_context_window(self) -> None:
        store = _store_with_colony()
        snapshot = build_snapshot(
            store,
            _SETTINGS,
            probed_local={
                "http://localhost:8008": {
                    "status": "ok",
                    "context_window": 80000,
                    "vram": 28.0,
                }
            },
        )
        registry = {
            entry["address"]: entry
            for entry in snapshot["runtimeConfig"]["models"]["registry"]
        }
        local_entry = registry["llama-cpp/qwen3.5-35b"]
        assert local_entry["status"] == "loaded"
        assert local_entry["contextWindow"] == 80000
        assert snapshot["localModels"][0]["ctx"] == 80000
        assert snapshot["localModels"][0]["name"] == "Qwen3.5-35B-A3B-Q4_K_M"
