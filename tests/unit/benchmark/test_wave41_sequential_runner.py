"""Wave 41 B3: Tests for the sequential task runner and locked conditions.

Validates:
  - ExperimentConditions record all required fields
  - Suite loading and listing
  - Curve computation from mock results
  - Condition locking (config hash stability)
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import yaml

from formicos.eval.sequential_runner import (
    ExperimentConditions,
    SequentialRunResult,
    TaskResult,
    _config_hash,
    _resolve_task_profile,
    list_suites,
    load_suite,
)

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# ExperimentConditions
# ---------------------------------------------------------------------------


class TestExperimentConditions:
    def test_all_required_fields_present(self) -> None:
        """Experiment conditions must record everything needed to reproduce."""
        cond = ExperimentConditions(
            suite_id="test-suite",
            task_order=["task-a", "task-b", "task-c"],
            strategy="stigmergic",
            model_mix={"coder": "anthropic/claude-3-haiku"},
            budget_per_task=2.0,
            max_rounds_per_task=10,
            escalation_policy="none",
            knowledge_mode="accumulate",
            workspace_id="ws-test",
            started_at="2026-03-19T00:00:00Z",
            config_hash="abc123",
        )
        d = cond.to_dict()
        assert d["suite_id"] == "test-suite"
        assert d["task_order"] == ["task-a", "task-b", "task-c"]
        assert d["strategy"] == "stigmergic"
        assert d["model_mix"] == {"coder": "anthropic/claude-3-haiku"}
        assert d["budget_per_task"] == 2.0
        assert d["max_rounds_per_task"] == 10
        assert d["escalation_policy"] == "none"
        assert d["knowledge_mode"] == "accumulate"
        assert d["config_hash"] == "abc123"

    def test_serializable(self) -> None:
        """Conditions must be JSON-serializable for locked recording."""
        cond = ExperimentConditions(
            suite_id="s",
            task_order=["a"],
            strategy="sequential",
            model_mix={},
            budget_per_task=1.0,
            max_rounds_per_task=5,
            escalation_policy="none",
            knowledge_mode="accumulate",
        )
        # Should not raise
        serialized = json.dumps(cond.to_dict())
        parsed = json.loads(serialized)
        assert parsed["suite_id"] == "s"


# ---------------------------------------------------------------------------
# Suite loading
# ---------------------------------------------------------------------------


class TestSuiteLoading:
    def test_load_suite_from_file(self, tmp_path: Path) -> None:
        suite_data = {
            "task_order": ["email-validator", "json-transformer"],
            "strategy": "stigmergic",
            "budget_per_task": 2.0,
            "max_rounds_per_task": 10,
            "escalation_policy": "none",
        }
        suite_file = tmp_path / "test-suite.yaml"
        with suite_file.open("w") as f:
            yaml.dump(suite_data, f)

        loaded = load_suite("test-suite", suites_dir=tmp_path)
        assert loaded["task_order"] == ["email-validator", "json-transformer"]
        assert loaded["strategy"] == "stigmergic"

    def test_load_suite_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_suite("nonexistent", suites_dir=tmp_path)

    def test_list_suites(self, tmp_path: Path) -> None:
        for name in ["alpha", "beta"]:
            p = tmp_path / f"{name}.yaml"
            with p.open("w") as f:
                yaml.dump({"task_order": []}, f)

        suites = list_suites(suites_dir=tmp_path)
        assert suites == ["alpha", "beta"]

    def test_list_suites_empty(self, tmp_path: Path) -> None:
        assert list_suites(suites_dir=tmp_path) == []


# ---------------------------------------------------------------------------
# Config hash stability
# ---------------------------------------------------------------------------


class TestConfigHash:
    def test_hash_is_deterministic(self, tmp_path: Path) -> None:
        """Same inputs must produce the same hash."""
        config = tmp_path / "config.yaml"
        config.write_text("models: {}")
        suite = {"task_order": ["a", "b"]}
        h1 = _config_hash(config, suite)
        h2 = _config_hash(config, suite)
        assert h1 == h2

    def test_hash_changes_with_config(self, tmp_path: Path) -> None:
        """Different config content must produce different hashes."""
        config = tmp_path / "config.yaml"
        suite = {"task_order": ["a"]}
        config.write_text("models: {}")
        h1 = _config_hash(config, suite)
        config.write_text("models: {changed: true}")
        h2 = _config_hash(config, suite)
        assert h1 != h2

    def test_hash_changes_with_suite(self, tmp_path: Path) -> None:
        """Different suite content must produce different hashes."""
        config = tmp_path / "config.yaml"
        config.write_text("models: {}")
        h1 = _config_hash(config, {"task_order": ["a"]})
        h2 = _config_hash(config, {"task_order": ["b"]})
        assert h1 != h2

    def test_hash_changes_with_task_payloads(self) -> None:
        base = Path(".wave53_hash_test")
        if base.exists():
            shutil.rmtree(base)
        base.mkdir()
        config = base / "config.yaml"
        config.write_text("models: {}")
        suite = {"task_order": ["a"]}
        h1 = _config_hash(config, suite, {"a": {"castes": [{"caste": "coder"}]}})
        h2 = _config_hash(config, suite, {"a": {"castes": [{"caste": "reviewer"}]}})
        assert h1 != h2
        shutil.rmtree(base)


class TestTaskProfileResolution:
    def test_task_uses_suite_defaults_when_unset(self) -> None:
        suite = {
            "strategy": "sequential",
            "budget_per_task": 2.0,
            "max_rounds_per_task": 5,
        }
        profile = _resolve_task_profile(
            {"castes": [{"caste": "coder", "tier": "standard", "count": 1}]},
            suite,
            {"coder": "llama-cpp/gpt-4"},
        )
        assert profile["strategy"] == "sequential"
        assert profile["budget_limit"] == 2.0
        assert profile["max_rounds"] == 5
        assert profile["fast_path"] is False
        assert profile["model_mix"] == {"coder": "llama-cpp/gpt-4"}

    def test_task_overrides_are_honored(self) -> None:
        suite = {
            "strategy": "stigmergic",
            "budget_per_task": 2.0,
            "max_rounds_per_task": 10,
        }
        profile = _resolve_task_profile(
            {
                "castes": [{"caste": "coder", "tier": "light", "count": 1}],
                "strategy": "sequential",
                "budget_limit": 0.5,
                "max_rounds": 3,
                "fast_path": True,
                "model_mix": {"coder": "llama-cpp/gpt-4"},
            },
            suite,
            {"reviewer": "llama-cpp/gpt-4"},
        )
        assert profile["strategy"] == "sequential"
        assert profile["budget_limit"] == 0.5
        assert profile["max_rounds"] == 3
        assert profile["fast_path"] is True
        assert profile["model_mix"]["reviewer"] == "llama-cpp/gpt-4"
        assert profile["model_mix"]["coder"] == "llama-cpp/gpt-4"


# ---------------------------------------------------------------------------
# TaskResult and SequentialRunResult
# ---------------------------------------------------------------------------


def _make_task_result(
    task_id: str, seq: int, quality: float = 0.7, cost: float = 0.5,
    wall_time: float = 30.0, extracted: int = 2, accessed: int = 1,
) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        sequence_index=seq,
        colony_id=f"col-{task_id}",
        status="completed",
        quality_score=quality,
        cost=cost,
        wall_time_s=wall_time,
        rounds_completed=5,
        entries_extracted=extracted,
        entries_accessed=accessed,
        knowledge_used=[],
        skills_extracted=extracted,
        timestamp="2026-03-19T00:00:00Z",
    )


class TestSequentialRunResult:
    def test_result_accumulates_tasks(self) -> None:
        cond = ExperimentConditions(
            suite_id="test",
            task_order=["a", "b"],
            strategy="stigmergic",
            model_mix={},
            budget_per_task=2.0,
            max_rounds_per_task=10,
            escalation_policy="none",
            knowledge_mode="accumulate",
        )
        result = SequentialRunResult(conditions=cond)
        result.tasks.append(_make_task_result("a", 0))
        result.tasks.append(_make_task_result("b", 1, quality=0.8, cost=0.3))
        result.total_cost = sum(t.cost for t in result.tasks)

        assert len(result.tasks) == 2
        assert result.total_cost == pytest.approx(0.8)

    def test_result_serializable(self) -> None:
        cond = ExperimentConditions(
            suite_id="test",
            task_order=["a"],
            strategy="sequential",
            model_mix={},
            budget_per_task=1.0,
            max_rounds_per_task=5,
            escalation_policy="none",
            knowledge_mode="accumulate",
        )
        result = SequentialRunResult(conditions=cond)
        result.tasks.append(_make_task_result("a", 0))
        serialized = json.dumps(asdict(result), default=str)
        parsed = json.loads(serialized)
        assert parsed["conditions"]["suite_id"] == "test"
        assert len(parsed["tasks"]) == 1
