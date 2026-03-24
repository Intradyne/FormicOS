"""Tests for colony observation structlog hook in colony_manager._post_colony_hooks."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import structlog

from formicos.surface.colony_manager import ColonyManager


def _make_runtime() -> MagicMock:
    """Minimal runtime mock for ColonyManager."""
    runtime = MagicMock()
    runtime.vector_store = None  # no vector store → skip confidence update
    # Wave 28: knowledge catalog methods
    runtime.fetch_knowledge_for_colony = AsyncMock(return_value=[])
    runtime.make_catalog_search_fn = MagicMock(return_value=None)
    runtime.make_knowledge_detail_fn = MagicMock(return_value=None)
    runtime.make_artifact_inspect_fn = MagicMock(return_value=None)
    return runtime


def _make_colony(**overrides: Any) -> SimpleNamespace:
    """Colony-like object with required attributes."""
    defaults = {
        "task": "Build a widget",
        "castes": [{"caste": "coder"}, {"caste": "reviewer"}],
        "strategy": "sequential",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_observation_log_emitted() -> None:
    """_post_colony_hooks should emit a structlog 'colony_observation' entry."""
    runtime = _make_runtime()
    mgr = ColonyManager(runtime)

    captured: list[dict[str, Any]] = []

    def capture_log(logger: Any, method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        if event_dict.get("event") == "colony_observation":
            captured.append(dict(event_dict))
        return event_dict

    with structlog.testing.capture_logs() as cap_logs:
        await mgr._post_colony_hooks(
            colony_id="col-1",
            colony=_make_colony(),
            quality=0.85,
            total_cost=0.42,
            rounds_completed=3,
            skills_count=2,
            retrieved_skill_ids={"sk1", "sk2"},
            governance_warnings=1,
            stall_count=0,
            succeeded=True,
        )

    obs = [e for e in cap_logs if e.get("event") == "colony_observation"]
    assert len(obs) == 1


@pytest.mark.asyncio
async def test_observation_payload_fields() -> None:
    """Colony observation log should contain all required payload fields."""
    runtime = _make_runtime()
    mgr = ColonyManager(runtime)

    with structlog.testing.capture_logs() as cap_logs:
        await mgr._post_colony_hooks(
            colony_id="col-99",
            colony=_make_colony(task="Analyze data", castes=[{"caste": "analyst"}]),
            quality=0.72,
            total_cost=1.23,
            rounds_completed=5,
            skills_count=3,
            retrieved_skill_ids={"s1"},
            governance_warnings=2,
            stall_count=1,
            succeeded=True,
        )

    obs = [e for e in cap_logs if e.get("event") == "colony_observation"]
    assert len(obs) == 1
    entry = obs[0]

    assert entry["colony_id"] == "col-99"
    assert entry["task"] == "Analyze data"
    assert entry["castes"] == [{"caste": "analyst"}]
    assert entry["strategy"] == "sequential"
    assert entry["rounds_completed"] == 5
    assert entry["quality_score"] == 0.72
    assert entry["total_cost"] == 1.23
    assert entry["skills_extracted"] == 3
    assert entry["governance_warnings"] == 2
    assert entry["stall_rounds"] == 1
    assert "s1" in entry["skills_retrieved"]


@pytest.mark.asyncio
async def test_observation_on_failure() -> None:
    """Observation should fire on failure with succeeded=False."""
    runtime = _make_runtime()
    mgr = ColonyManager(runtime)

    with structlog.testing.capture_logs() as cap_logs:
        await mgr._post_colony_hooks(
            colony_id="col-fail",
            colony=_make_colony(),
            quality=0.0,
            total_cost=0.10,
            rounds_completed=1,
            skills_count=0,
            retrieved_skill_ids=set(),
            governance_warnings=0,
            stall_count=0,
            succeeded=False,
        )

    obs = [e for e in cap_logs if e.get("event") == "colony_observation"]
    assert len(obs) == 1
    assert obs[0]["quality_score"] == 0.0
    assert obs[0]["skills_retrieved"] == []


@pytest.mark.asyncio
async def test_legacy_skill_lifecycle_removed_wave30() -> None:
    """skill_lifecycle module was deleted in Wave 30. Verify it cannot be imported."""
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("formicos.surface.skill_lifecycle")
