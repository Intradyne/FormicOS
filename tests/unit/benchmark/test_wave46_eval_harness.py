"""Wave 46 Team 2: Eval harness integrity tests.

Validates:
  - Clean-room isolation: unique run IDs and workspace IDs
  - Knowledge attribution: KnowledgeAttribution shape and population
  - Expanded ExperimentConditions: new fields present and serializable
  - Run manifests: manifest structure and content
  - Suite expansion: pilot/full/benchmark suites load correctly
  - Compounding curve: attribution data flows through curves
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

import pytest
import yaml

from formicos.eval.compounding_curve import compute_curves
from formicos.eval.sequential_runner import (
    ExperimentConditions,
    KnowledgeAttribution,
    SequentialRunResult,
    TaskResult,
    _append_partial_result,
    _config_hash,
    _validate_modes,
    _write_manifest,
    list_suites,
    load_suite,
)

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_conditions(**overrides: Any) -> ExperimentConditions:
    base: dict[str, Any] = {
        "suite_id": "test-suite",
        "task_order": ["a", "b"],
        "strategy": "stigmergic",
        "model_mix": {},
        "budget_per_task": 2.0,
        "max_rounds_per_task": 10,
        "escalation_policy": "none",
        "knowledge_mode": "accumulate",
        "foraging_policy": "disabled",
        "run_id": "abc123def456",
        "workspace_id": "seq-test-suite-abc123def456",
        "started_at": "2026-03-19T00:00:00Z",
        "config_hash": "deadbeef",
        "git_commit": "a1b2c3d",
        "task_profiles": {},
    }
    base.update(overrides)
    return ExperimentConditions(**base)


def _make_attribution(
    used: list[dict[str, Any]] | None = None,
    produced: list[dict[str, Any]] | None = None,
) -> KnowledgeAttribution:
    attr = KnowledgeAttribution()
    for u in (used or []):
        attr.used.append(u)
        attr.used_ids.append(u["id"])
    for p in (produced or []):
        attr.produced.append(p)
        attr.produced_ids.append(p["id"])
    return attr


def _make_task_result(
    task_id: str,
    seq: int,
    quality: float = 0.7,
    cost: float = 0.5,
    attribution: KnowledgeAttribution | None = None,
) -> TaskResult:
    attr = attribution or KnowledgeAttribution()
    return TaskResult(
        task_id=task_id,
        sequence_index=seq,
        colony_id=f"col-{task_id}",
        status="completed",
        quality_score=quality,
        cost=cost,
        wall_time_s=30.0,
        rounds_completed=5,
        entries_extracted=2,
        entries_accessed=len(attr.used_ids),
        knowledge_used=attr.used_ids,
        skills_extracted=2,
        knowledge_attribution=attr,
        timestamp="2026-03-19T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# Track A: Clean-room isolation
# ---------------------------------------------------------------------------


class TestCleanRoomIsolation:
    """Validate that each run gets a unique workspace."""

    def test_run_id_in_workspace_id(self) -> None:
        """Workspace ID must contain the run ID for uniqueness."""
        cond = _make_conditions(run_id="abc123def456")
        assert "abc123def456" in cond.workspace_id

    def test_two_conditions_different_run_ids(self) -> None:
        """Two conditions with different run_ids must have different workspace_ids."""
        c1 = _make_conditions(
            run_id="aaa",
            workspace_id="seq-test-suite-aaa",
        )
        c2 = _make_conditions(
            run_id="bbb",
            workspace_id="seq-test-suite-bbb",
        )
        assert c1.workspace_id != c2.workspace_id

    def test_knowledge_mode_field_present(self) -> None:
        cond = _make_conditions(knowledge_mode="empty")
        assert cond.knowledge_mode == "empty"

    def test_knowledge_mode_serializable(self) -> None:
        cond = _make_conditions(knowledge_mode="empty")
        d = cond.to_dict()
        serialized = json.dumps(d)
        parsed = json.loads(serialized)
        assert parsed["knowledge_mode"] == "empty"


# ---------------------------------------------------------------------------
# Track B: Knowledge attribution
# ---------------------------------------------------------------------------


class TestKnowledgeAttribution:
    """Validate structured knowledge attribution shape."""

    def test_empty_attribution(self) -> None:
        attr = KnowledgeAttribution()
        assert attr.used == []
        assert attr.produced == []
        assert attr.used_ids == []
        assert attr.produced_ids == []

    def test_attribution_with_used_entries(self) -> None:
        attr = _make_attribution(
            used=[
                {"id": "e1", "title": "Test", "source_task": "task-a", "source_colony": "col-a"},
                {"id": "e2", "title": "Test2", "source_task": None, "source_colony": None},
            ],
        )
        assert len(attr.used) == 2
        assert attr.used_ids == ["e1", "e2"]
        assert attr.used[0]["source_task"] == "task-a"

    def test_attribution_with_produced_entries(self) -> None:
        attr = _make_attribution(
            produced=[
                {"id": "e3", "title": "New skill", "category": "skill", "sub_type": "technique"},
            ],
        )
        assert len(attr.produced) == 1
        assert attr.produced_ids == ["e3"]
        assert attr.produced[0]["category"] == "skill"

    def test_attribution_serializable(self) -> None:
        attr = _make_attribution(
            used=[{"id": "e1", "title": "T", "source_task": None, "source_colony": None}],
            produced=[{"id": "e2", "title": "P", "category": "skill", "sub_type": "pattern"}],
        )
        d = asdict(attr)
        serialized = json.dumps(d)
        parsed = json.loads(serialized)
        assert parsed["used_ids"] == ["e1"]
        assert parsed["produced_ids"] == ["e2"]

    def test_task_result_includes_attribution(self) -> None:
        attr = _make_attribution(
            used=[{"id": "e1", "title": "T", "source_task": None, "source_colony": None}],
        )
        tr = _make_task_result("a", 0, attribution=attr)
        assert tr.knowledge_used == ["e1"]
        assert tr.knowledge_attribution.used_ids == ["e1"]
        assert tr.entries_accessed == 1


# ---------------------------------------------------------------------------
# Track C: Expanded conditions and manifests
# ---------------------------------------------------------------------------


class TestExpandedConditions:
    """Validate new ExperimentConditions fields."""

    def test_new_fields_present(self) -> None:
        cond = _make_conditions()
        d = cond.to_dict()
        assert "knowledge_mode" in d
        assert "foraging_policy" in d
        assert "run_id" in d
        assert "git_commit" in d
        assert "task_profiles" in d

    def test_default_values(self) -> None:
        cond = ExperimentConditions(
            suite_id="s",
            task_order=["a"],
            strategy="stigmergic",
            model_mix={},
            budget_per_task=1.0,
            max_rounds_per_task=5,
            escalation_policy="none",
        )
        assert cond.knowledge_mode == "accumulate"
        assert cond.foraging_policy == "disabled"
        assert cond.random_seed is None
        assert cond.run_id == ""
        assert cond.git_commit == ""
        assert cond.task_profiles == {}

    def test_random_seed_field(self) -> None:
        cond = _make_conditions(random_seed=42)
        d = cond.to_dict()
        assert d["random_seed"] == 42

    def test_foraging_policy_values(self) -> None:
        # Only "disabled" is behaviorally supported
        cond = _make_conditions(foraging_policy="disabled")
        assert cond.foraging_policy == "disabled"

    def test_full_serialization_roundtrip(self) -> None:
        cond = _make_conditions(
            knowledge_mode="empty",
            foraging_policy="disabled",
            random_seed=99,
            git_commit="abc1234",
        )
        serialized = json.dumps(cond.to_dict())
        parsed = json.loads(serialized)
        assert parsed["knowledge_mode"] == "empty"
        assert parsed["foraging_policy"] == "disabled"
        assert parsed["random_seed"] == 99
        assert parsed["git_commit"] == "abc1234"


class TestRunManifest:
    """Validate manifest writing."""

    def test_manifest_written(self, tmp_path: Path) -> None:
        cond = _make_conditions()
        attr = _make_attribution(
            used=[{"id": "e1", "title": "T", "source_task": None, "source_colony": None}],
            produced=[{"id": "e2", "title": "P", "category": "skill", "sub_type": "technique"}],
        )
        result = SequentialRunResult(
            conditions=cond,
            tasks=[_make_task_result("a", 0, attribution=attr)],
            total_cost=0.5,
            total_wall_time_s=30.0,
            completed_at="2026-03-19T00:01:00Z",
        )
        manifest_path = tmp_path / "manifest.json"
        _write_manifest(result, manifest_path)

        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["run_id"] == "abc123def456"
        assert manifest["suite_id"] == "test-suite"
        assert manifest["knowledge_mode"] == "accumulate"
        assert manifest["git_commit"] == "a1b2c3d"
        assert manifest["tasks_run"] == 1
        assert manifest["total_knowledge_used"] == 1
        assert manifest["total_knowledge_produced"] == 1

    def test_manifest_has_all_required_fields(self, tmp_path: Path) -> None:
        cond = _make_conditions()
        result = SequentialRunResult(
            conditions=cond,
            total_cost=0.0,
            completed_at="2026-03-19T00:00:00Z",
        )
        manifest_path = tmp_path / "manifest.json"
        _write_manifest(result, manifest_path)

        manifest = json.loads(manifest_path.read_text())
        required_fields = [
            "run_id", "suite_id", "started_at", "completed_at",
            "git_commit", "config_hash", "knowledge_mode",
            "foraging_policy", "strategy", "workspace_id",
            "tasks_run", "total_cost", "total_wall_time_s",
            "task_ids", "statuses",
            "total_knowledge_used", "total_knowledge_produced",
        ]
        for field in required_fields:
            assert field in manifest, f"Missing field: {field}"

    def test_partial_results_append_jsonl(self, tmp_path: Path) -> None:
        task = _make_task_result("a", 0)
        partial_path = tmp_path / "results.jsonl"

        _append_partial_result(partial_path, task)
        _append_partial_result(partial_path, _make_task_result("b", 1))

        lines = partial_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["task_id"] == "a"
        assert json.loads(lines[1])["task_id"] == "b"


# ---------------------------------------------------------------------------
# Track D: Suite expansion
# ---------------------------------------------------------------------------


class TestSuiteExpansion:
    """Validate pilot/full/benchmark suites and new task files."""

    def test_pilot_suite_loads(self) -> None:
        suite = load_suite("pilot")
        assert len(suite["task_order"]) == 3
        assert "email-validator" in suite["task_order"]

    def test_full_suite_loads(self) -> None:
        suite = load_suite("full")
        assert len(suite["task_order"]) == 10

    def test_benchmark_suite_loads(self) -> None:
        suite = load_suite("benchmark")
        assert len(suite["task_order"]) == 13
        # Should include all original + new tasks
        assert "refactor-plan" in suite["task_order"]

    def test_default_suite_still_works(self) -> None:
        suite = load_suite("default")
        assert len(suite["task_order"]) == 7

    def test_phase0_suite_defaults_to_sequential(self) -> None:
        suite = load_suite("phase0")
        assert suite["strategy"] == "sequential"

    def test_all_suites_listed(self) -> None:
        suites = list_suites()
        assert "pilot" in suites
        assert "full" in suites
        assert "benchmark" in suites
        assert "default" in suites

    def test_suite_task_ids_are_valid_files(self) -> None:
        """Every task_id in every suite must have a corresponding YAML file."""
        from pathlib import Path

        tasks_dir = Path(__file__).resolve().parents[3] / "config" / "eval" / "tasks"
        for suite_name in list_suites():
            suite = load_suite(suite_name)
            for task_id in suite["task_order"]:
                task_file = tasks_dir / f"{task_id}.yaml"
                assert task_file.exists(), (
                    f"Suite '{suite_name}' references task '{task_id}' "
                    f"but {task_file} does not exist"
                )

    def test_new_task_files_have_required_fields(self) -> None:
        """New task YAMLs must have id, description, difficulty, castes."""
        from pathlib import Path

        tasks_dir = Path(__file__).resolve().parents[3] / "config" / "eval" / "tasks"
        new_tasks = [
            "markdown-parser", "csv-analyzer", "rate-limiter",
            "plugin-system", "event-store", "cli-framework",
        ]
        for task_id in new_tasks:
            path = tasks_dir / f"{task_id}.yaml"
            with path.open("r", encoding="utf-8") as fh:
                task = yaml.safe_load(fh)
            assert task["id"] == task_id
            assert "description" in task
            assert "difficulty" in task
            assert "castes" in task
            assert "budget_limit" in task
            assert "max_rounds" in task

    def test_phase0_simple_tasks_use_fast_path_single_coder(self) -> None:
        from pathlib import Path

        tasks_dir = Path(__file__).resolve().parents[3] / "config" / "eval" / "tasks"
        for task_id in ("email-validator", "json-transformer", "haiku-writer"):
            with (tasks_dir / f"{task_id}.yaml").open("r", encoding="utf-8") as fh:
                task = yaml.safe_load(fh)
            assert task["fast_path"] is True
            assert task["max_rounds"] == 3
            assert len(task["castes"]) == 1
            assert task["castes"][0]["caste"] == "coder"

    def test_phase0_complex_tasks_keep_stigmergic(self) -> None:
        from pathlib import Path

        tasks_dir = Path(__file__).resolve().parents[3] / "config" / "eval" / "tasks"
        for task_id in ("rate-limiter", "api-design", "data-pipeline"):
            with (tasks_dir / f"{task_id}.yaml").open("r", encoding="utf-8") as fh:
                task = yaml.safe_load(fh)
            assert task["strategy"] == "stigmergic"
            assert task["max_rounds"] == 8


# ---------------------------------------------------------------------------
# Compounding curve with attribution
# ---------------------------------------------------------------------------


class TestCompoundingCurveAttribution:
    """Validate that attribution data flows through curve computation."""

    def test_curves_include_attribution_totals(self) -> None:
        run = {
            "conditions": _make_conditions().to_dict(),
            "tasks": [
                {
                    "task_id": "a",
                    "sequence_index": 0,
                    "quality_score": 0.7,
                    "cost": 0.5,
                    "wall_time_s": 30.0,
                    "entries_extracted": 2,
                    "entries_accessed": 1,
                    "knowledge_attribution": {
                        "used_ids": ["e1"],
                        "produced_ids": ["e2", "e3"],
                        "used": [],
                        "produced": [],
                    },
                },
                {
                    "task_id": "b",
                    "sequence_index": 1,
                    "quality_score": 0.8,
                    "cost": 0.4,
                    "wall_time_s": 25.0,
                    "entries_extracted": 1,
                    "entries_accessed": 2,
                    "knowledge_attribution": {
                        "used_ids": ["e2", "e3"],
                        "produced_ids": ["e4"],
                        "used": [],
                        "produced": [],
                    },
                },
            ],
            "total_cost": 0.9,
            "total_wall_time_s": 55.0,
        }
        curves = compute_curves(run)
        kc = curves["knowledge_contribution"]
        assert kc["total_knowledge_used"] == 3  # 1 + 2
        assert kc["total_knowledge_produced"] == 3  # 2 + 1

    def test_curves_without_attribution(self) -> None:
        """Backward compat: runs without knowledge_attribution still work."""
        run = {
            "conditions": {},
            "tasks": [
                {
                    "task_id": "a",
                    "sequence_index": 0,
                    "quality_score": 0.5,
                    "cost": 0.3,
                    "wall_time_s": 20.0,
                    "entries_extracted": 1,
                    "entries_accessed": 0,
                },
            ],
            "total_cost": 0.3,
        }
        curves = compute_curves(run)
        kc = curves["knowledge_contribution"]
        assert kc["total_knowledge_used"] == 0
        assert kc["total_knowledge_produced"] == 0


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """Existing test patterns must still work with expanded dataclasses."""

    def test_old_conditions_still_work(self) -> None:
        """ExperimentConditions without new fields uses defaults."""
        cond = ExperimentConditions(
            suite_id="test",
            task_order=["a"],
            strategy="stigmergic",
            model_mix={},
            budget_per_task=1.0,
            max_rounds_per_task=5,
            escalation_policy="none",
        )
        d = cond.to_dict()
        assert d["knowledge_mode"] == "accumulate"
        assert d["run_id"] == ""

    def test_task_result_without_attribution(self) -> None:
        """TaskResult without explicit attribution uses empty default."""
        tr = TaskResult(
            task_id="a",
            sequence_index=0,
            colony_id="col-a",
            status="completed",
            quality_score=0.7,
            cost=0.5,
            wall_time_s=30.0,
            rounds_completed=5,
            entries_extracted=2,
            entries_accessed=1,
            knowledge_used=[],
            skills_extracted=2,
        )
        assert tr.knowledge_attribution.used == []
        assert tr.knowledge_attribution.produced == []

    def test_sequential_run_result_serializable(self) -> None:
        cond = _make_conditions()
        attr = _make_attribution(
            used=[{"id": "e1", "title": "T", "source_task": None, "source_colony": None}],
        )
        result = SequentialRunResult(
            conditions=cond,
            tasks=[_make_task_result("a", 0, attribution=attr)],
            total_cost=0.5,
            completed_at="2026-03-19T00:00:00Z",
        )
        serialized = json.dumps(asdict(result), default=str)
        parsed = json.loads(serialized)
        assert parsed["conditions"]["run_id"] == "abc123def456"
        assert parsed["tasks"][0]["knowledge_attribution"]["used_ids"] == ["e1"]

    def test_config_hash_still_deterministic(self, tmp_path: Path) -> None:
        config = tmp_path / "config.yaml"
        config.write_text("models: {}")
        suite = {"task_order": ["a"]}
        h1 = _config_hash(config, suite)
        h2 = _config_hash(config, suite)
        assert h1 == h2


# ---------------------------------------------------------------------------
# Mode validation — no paper switches
# ---------------------------------------------------------------------------


class TestModeValidation:
    """Unsupported modes must fail fast, not silently record metadata."""

    def test_snapshot_mode_rejected(self) -> None:
        with pytest.raises(ValueError, match="snapshot"):
            _validate_modes("snapshot", "disabled")

    def test_unknown_knowledge_mode_rejected(self) -> None:
        with pytest.raises(ValueError, match="not supported"):
            _validate_modes("magic", "disabled")

    def test_reactive_foraging_rejected(self) -> None:
        with pytest.raises(ValueError, match="reactive"):
            _validate_modes("accumulate", "reactive")

    def test_proactive_foraging_rejected(self) -> None:
        with pytest.raises(ValueError, match="proactive"):
            _validate_modes("accumulate", "proactive")

    def test_unknown_foraging_policy_rejected(self) -> None:
        with pytest.raises(ValueError, match="not supported"):
            _validate_modes("accumulate", "auto")

    def test_accumulate_disabled_accepted(self) -> None:
        _validate_modes("accumulate", "disabled")  # should not raise

    def test_empty_disabled_accepted(self) -> None:
        _validate_modes("empty", "disabled")  # should not raise


# ---------------------------------------------------------------------------
# Source-task attribution from run-local map
# ---------------------------------------------------------------------------


class TestSourceTaskAttribution:
    """Source-task enrichment uses run-local map, not phantom fields."""

    def test_attribution_enriched_from_source_map(self) -> None:
        """When a used entry is in the run source map, source_task comes
        from the map, not from the (possibly missing) product field."""
        from formicos.eval.sequential_runner import _build_attribution

        # Simulate a colony projection with one knowledge access
        class FakeColony:
            colony_id = "col-b"
            knowledge_accesses = [
                {"items": [{"id": "e1"}]},
            ]

        # Simulate projections with the entry but no source_task_id
        class FakeProjections:
            memory_entries = {
                "e1": {
                    "title": "Extracted skill",
                    "source_colony_id": "col-a",
                    # Note: no source_task_id — this is the real-world case
                },
            }

        source_map = {
            "e1": {"task_id": "task-a", "seq": 0, "colony_id": "col-a"},
        }

        attr = _build_attribution(FakeColony(), FakeProjections(), source_map)
        assert len(attr.used) == 1
        assert attr.used[0]["source_task"] == "task-a"
        assert attr.used[0]["source_colony"] == "col-a"
        assert attr.used[0]["source_seq"] == 0

    def test_attribution_graceful_without_source_map(self) -> None:
        """Entries not in the source map still get whatever product
        fields exist (may be None)."""
        from formicos.eval.sequential_runner import _build_attribution

        class FakeColony:
            colony_id = "col-c"
            knowledge_accesses = [
                {"items": [{"id": "ext1"}]},
            ]

        class FakeProjections:
            memory_entries = {
                "ext1": {
                    "title": "External entry",
                    "source_colony_id": "col-x",
                },
            }

        attr = _build_attribution(FakeColony(), FakeProjections(), {})
        assert len(attr.used) == 1
        assert attr.used[0]["source_task"] is None  # not in source map
        assert attr.used[0]["source_colony"] == "col-x"  # from product

    def test_source_map_overrides_product_field(self) -> None:
        """Run-local map takes priority over product source_task_id."""
        from formicos.eval.sequential_runner import _build_attribution

        class FakeColony:
            colony_id = "col-d"
            knowledge_accesses = [
                {"items": [{"id": "e2"}]},
            ]

        class FakeProjections:
            memory_entries = {
                "e2": {
                    "title": "Has both fields",
                    "source_task_id": "old-product-value",
                    "source_colony_id": "col-old",
                },
            }

        source_map = {
            "e2": {"task_id": "run-task-a", "seq": 0, "colony_id": "col-new"},
        }

        attr = _build_attribution(FakeColony(), FakeProjections(), source_map)
        assert attr.used[0]["source_task"] == "run-task-a"
        assert attr.used[0]["source_colony"] == "col-new"

    def test_produced_entries_populate_source_map_pattern(self) -> None:
        """Verify the pattern: produced entries should be suitable for
        building a run-local source map."""
        attr = _make_attribution(
            produced=[
                {"id": "e5", "title": "Skill", "category": "skill", "sub_type": "technique"},
                {"id": "e6", "title": "Bug", "category": "experience", "sub_type": "bug"},
            ],
        )
        # Build source map from produced — same pattern as run_sequential
        source_map: dict[str, dict[str, Any]] = {}
        for prod in attr.produced:
            source_map[prod["id"]] = {
                "task_id": "task-a",
                "seq": 0,
                "colony_id": "col-a",
            }
        assert "e5" in source_map
        assert "e6" in source_map
        assert source_map["e5"]["task_id"] == "task-a"
