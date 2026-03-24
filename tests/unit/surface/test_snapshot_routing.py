"""Tests for modelsUsed derivation and skillBankStats passthrough in snapshots."""

from __future__ import annotations

from pathlib import Path

from formicos.core.settings import load_config
from formicos.surface.projections import (
    AgentProjection,
    ColonyProjection,
    ProjectionStore,
    ThreadProjection,
    WorkspaceProjection,
)
from formicos.surface.view_state import build_snapshot

_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "formicos.yaml"
_SETTINGS = load_config(_CONFIG_PATH)


def _store_with_agents(
    agents: dict[str, AgentProjection] | None = None,
) -> ProjectionStore:
    """Build a ProjectionStore with one colony containing the given agents."""
    store = ProjectionStore()
    colony = ColonyProjection(
        id="col-1",
        thread_id="th-1",
        workspace_id="ws-1",
        task="test task",
        status="running",
    )
    if agents:
        colony.agents = agents
    thread = ThreadProjection(id="th-1", workspace_id="ws-1", name="main")
    thread.colonies["col-1"] = colony
    ws = WorkspaceProjection(id="ws-1", name="default")
    ws.threads["th-1"] = thread
    store.workspaces["ws-1"] = ws
    store.colonies["col-1"] = colony
    return store


def _colony_from_snapshot(snapshot: dict) -> dict:  # type: ignore[type-arg]
    return snapshot["tree"][0]["children"][0]["children"][0]


# ---------------------------------------------------------------------------
# modelsUsed derivation
# ---------------------------------------------------------------------------


class TestModelsUsed:
    def test_single_local_model(self) -> None:
        store = _store_with_agents({
            "a1": AgentProjection(id="a1", caste="coder", model="llama-cpp/gpt-4"),
            "a2": AgentProjection(id="a2", caste="reviewer", model="llama-cpp/gpt-4"),
        })
        colony = _colony_from_snapshot(build_snapshot(store, _SETTINGS))
        assert colony["modelsUsed"] == ["llama-cpp/gpt-4"]

    def test_mixed_models(self) -> None:
        store = _store_with_agents({
            "a1": AgentProjection(
                id="a1", caste="coder", model="anthropic/claude-sonnet-4.6",
            ),
            "a2": AgentProjection(
                id="a2", caste="reviewer", model="llama-cpp/gpt-4",
            ),
        })
        colony = _colony_from_snapshot(build_snapshot(store, _SETTINGS))
        assert set(colony["modelsUsed"]) == {
            "anthropic/claude-sonnet-4.6", "llama-cpp/gpt-4",
        }

    def test_no_agents(self) -> None:
        store = _store_with_agents({})
        colony = _colony_from_snapshot(build_snapshot(store, _SETTINGS))
        assert colony["modelsUsed"] == []

    def test_single_cloud_model(self) -> None:
        store = _store_with_agents({
            "a1": AgentProjection(
                id="a1", caste="queen", model="anthropic/claude-sonnet-4.6",
            ),
        })
        colony = _colony_from_snapshot(build_snapshot(store, _SETTINGS))
        assert colony["modelsUsed"] == ["anthropic/claude-sonnet-4.6"]


# ---------------------------------------------------------------------------
# skillBankStats passthrough
# ---------------------------------------------------------------------------


class TestSkillBankStats:
    def test_stats_passed_through(self) -> None:
        store = _store_with_agents({})
        stats = {"total": 42, "avgConfidence": 0.73}
        snapshot = build_snapshot(store, _SETTINGS, skill_bank_stats=stats)
        assert snapshot["skillBankStats"] == {"total": 42, "avgConfidence": 0.73}

    def test_none_defaults_to_zero(self) -> None:
        store = _store_with_agents({})
        snapshot = build_snapshot(store, _SETTINGS, skill_bank_stats=None)
        assert snapshot["skillBankStats"] == {"total": 0, "avgConfidence": 0.0}

    def test_omitted_defaults_to_zero(self) -> None:
        store = _store_with_agents({})
        snapshot = build_snapshot(store, _SETTINGS)
        assert snapshot["skillBankStats"] == {"total": 0, "avgConfidence": 0.0}

    def test_empty_stats_replaced(self) -> None:
        store = _store_with_agents({})
        snapshot = build_snapshot(store, _SETTINGS, skill_bank_stats={})
        # Empty dict is falsy, so defaults apply
        assert snapshot["skillBankStats"] == {"total": 0, "avgConfidence": 0.0}
