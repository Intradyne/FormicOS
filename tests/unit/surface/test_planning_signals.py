"""Tests for planning_signals capability integration polish."""

from __future__ import annotations

from unittest.mock import MagicMock

import formicos.surface.capability_profiles as capability_profiles
from formicos.surface.planning_signals import _fetch_capability


def _mock_runtime() -> MagicMock:
    runtime = MagicMock()
    runtime.settings.system.data_dir = "/tmp/formicos-test"
    runtime.projections = MagicMock()

    def _resolve_model(caste: str, workspace_id: str) -> str:
        assert workspace_id == "ws1"
        if caste == "coder":
            return "llama-cpp/qwen3.5-35b"
        if caste == "queen":
            return "anthropic/claude-sonnet-4-6"
        return ""

    runtime.resolve_model.side_effect = _resolve_model
    return runtime


def test_fetch_capability_uses_structured_evidence(monkeypatch) -> None:
    runtime = _mock_runtime()
    captured: dict[str, object] = {}

    def _fake_evidence(
        model_addr: str,
        *,
        projections: object | None = None,
        workspace_id: str = "",
        data_dir: str = "",
        planner_model: str = "",
        task_class: str = "",
        granularity: str = "",
    ) -> dict[str, object]:
        captured.update({
            "model_addr": model_addr,
            "projections": projections,
            "workspace_id": workspace_id,
            "data_dir": data_dir,
            "planner_model": planner_model,
            "task_class": task_class,
            "granularity": granularity,
        })
        return {
            "label": "qwen3.5-35b",
            "source": "replay",
            "sample_count": 5,
            "quality_mean": 0.712,
            "optimal_files": "5-8",
        }

    monkeypatch.setattr(
        capability_profiles,
        "get_capability_evidence",
        _fake_evidence,
    )

    result = _fetch_capability(runtime, "ws1")

    assert result == {
        "model": "llama-cpp/qwen3.5-35b",
        "short_name": "qwen3.5-35b",
        "summary": "qwen3.5-35b (n=5, replay) -> 5-8 files optimal, focused can reach 0.712",
    }
    assert captured == {
        "model_addr": "llama-cpp/qwen3.5-35b",
        "projections": runtime.projections,
        "workspace_id": "ws1",
        "data_dir": "/tmp/formicos-test",
        "planner_model": "anthropic/claude-sonnet-4-6",
        "task_class": "",
        "granularity": "",
    }


def test_fetch_capability_falls_back_to_summary(monkeypatch) -> None:
    runtime = _mock_runtime()

    monkeypatch.setattr(
        capability_profiles,
        "get_capability_evidence",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        capability_profiles,
        "summarize_capability",
        lambda model_addr, data_dir="": f"fallback::{model_addr}::{data_dir}",
    )

    result = _fetch_capability(runtime, "ws1")

    assert result == {
        "model": "llama-cpp/qwen3.5-35b",
        "short_name": "qwen3.5-35b",
        "summary": "fallback::llama-cpp/qwen3.5-35b::/tmp/formicos-test",
    }
