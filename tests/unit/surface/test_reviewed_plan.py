"""Tests for reviewed-plan normalization and validation (Wave 83 Track A)."""

from __future__ import annotations

from formicos.surface.reviewed_plan import normalize_preview, validate_plan


def _make_preview(
    *,
    tasks: list | None = None,
    groups: list | None = None,
) -> dict:
    if tasks is None:
        tasks = [
            {"task_id": "t1", "task": "Write scanner", "caste": "coder"},
            {"task_id": "t2", "task": "Write tests", "caste": "coder",
             "depends_on": ["t1"]},
        ]
    if groups is None:
        groups = [
            {"taskIds": ["t1"]},
            {"taskIds": ["t2"]},
        ]
    return {
        "taskPreviews": tasks,
        "groups": groups,
        "estimatedCost": 1.5,
    }


class TestNormalizePreview:
    def test_basic_normalization(self) -> None:
        preview = _make_preview()
        result = normalize_preview(preview)
        assert len(result["tasks"]) == 2
        assert len(result["parallel_groups"]) == 2
        assert result["tasks"][0]["task_id"] == "t1"
        assert result["estimated_total_cost"] == 1.5

    def test_preserves_max_rounds_from_preview(self) -> None:
        preview = _make_preview(tasks=[
            {"task_id": "t1", "task": "X", "caste": "coder", "max_rounds": 12},
        ], groups=[{"taskIds": ["t1"]}])
        result = normalize_preview(preview)
        assert result["tasks"][0]["max_rounds"] == 12

    def test_defaults_max_rounds_when_absent(self) -> None:
        preview = _make_preview(tasks=[
            {"task_id": "t1", "task": "X", "caste": "coder"},
        ], groups=[{"taskIds": ["t1"]}])
        result = normalize_preview(preview)
        assert result["tasks"][0]["max_rounds"] == 8

    def test_input_from_separate_from_depends_on(self) -> None:
        preview = _make_preview(tasks=[
            {"task_id": "t1", "task": "X", "caste": "coder"},
            {"task_id": "t2", "task": "Y", "caste": "coder",
             "depends_on": ["t1"], "input_from": ["t1"]},
        ])
        result = normalize_preview(preview)
        assert result["tasks"][1]["depends_on"] == ["t1"]
        assert result["tasks"][1]["input_from"] == ["t1"]

    def test_input_from_falls_back_to_depends_on(self) -> None:
        preview = _make_preview(tasks=[
            {"task_id": "t1", "task": "X", "caste": "coder"},
            {"task_id": "t2", "task": "Y", "caste": "coder",
             "depends_on": ["t1"]},
        ])
        result = normalize_preview(preview)
        assert result["tasks"][1]["input_from"] == ["t1"]


class TestValidatePlan:
    def test_valid_plan_passes(self) -> None:
        normalized = normalize_preview(_make_preview())
        errors, warnings = validate_plan(normalized)
        assert errors == []

    def test_empty_tasks_rejected(self) -> None:
        errors, _ = validate_plan({"tasks": [], "parallel_groups": [[]]})
        assert any("no tasks" in e.lower() for e in errors)

    def test_empty_groups_rejected(self) -> None:
        errors, _ = validate_plan({
            "tasks": [{"task_id": "t1"}],
            "parallel_groups": [],
        })
        assert any("no parallel groups" in e.lower() for e in errors)

    def test_duplicate_task_ids_rejected(self) -> None:
        preview = _make_preview(tasks=[
            {"task_id": "t1", "task": "A", "caste": "coder"},
            {"task_id": "t1", "task": "B", "caste": "coder"},
        ], groups=[{"taskIds": ["t1"]}])
        normalized = normalize_preview(preview)
        errors, _ = validate_plan(normalized)
        assert any("duplicate" in e.lower() for e in errors)

    def test_orphaned_task_rejected(self) -> None:
        preview = _make_preview(tasks=[
            {"task_id": "t1", "task": "A", "caste": "coder"},
            {"task_id": "t2", "task": "B", "caste": "coder"},
        ], groups=[{"taskIds": ["t1"]}])
        normalized = normalize_preview(preview)
        errors, _ = validate_plan(normalized)
        assert any("not in any group" in e.lower() for e in errors)

    def test_phantom_group_reference_rejected(self) -> None:
        preview = _make_preview(tasks=[
            {"task_id": "t1", "task": "A", "caste": "coder"},
        ], groups=[{"taskIds": ["t1", "t99"]}])
        normalized = normalize_preview(preview)
        errors, _ = validate_plan(normalized)
        assert any("nonexistent" in e.lower() for e in errors)

    def test_self_dependency_rejected(self) -> None:
        preview = _make_preview(tasks=[
            {"task_id": "t1", "task": "A", "caste": "coder",
             "depends_on": ["t1"]},
        ], groups=[{"taskIds": ["t1"]}])
        normalized = normalize_preview(preview)
        errors, _ = validate_plan(normalized)
        assert any("itself" in e.lower() for e in errors)

    def test_group_order_violation_rejected(self) -> None:
        preview = _make_preview(tasks=[
            {"task_id": "t1", "task": "A", "caste": "coder",
             "depends_on": ["t2"]},
            {"task_id": "t2", "task": "B", "caste": "coder"},
        ], groups=[
            {"taskIds": ["t1"]},
            {"taskIds": ["t2"]},
        ])
        normalized = normalize_preview(preview)
        errors, _ = validate_plan(normalized)
        assert any("group order" in e.lower() for e in errors)

    def test_dependency_cycle_rejected(self) -> None:
        preview = _make_preview(tasks=[
            {"task_id": "t1", "task": "A", "caste": "coder",
             "depends_on": ["t2"]},
            {"task_id": "t2", "task": "B", "caste": "coder",
             "depends_on": ["t1"]},
        ], groups=[
            {"taskIds": ["t1", "t2"]},
        ])
        normalized = normalize_preview(preview)
        errors, _ = validate_plan(normalized)
        # Either group-order or cycle error
        assert len(errors) > 0

    def test_shared_file_warns(self) -> None:
        preview = _make_preview(tasks=[
            {"task_id": "t1", "task": "A", "caste": "coder",
             "target_files": ["main.py"]},
            {"task_id": "t2", "task": "B", "caste": "coder",
             "target_files": ["main.py"]},
        ], groups=[{"taskIds": ["t1", "t2"]}])
        normalized = normalize_preview(preview)
        _, warnings = validate_plan(normalized)
        assert any("main.py" in w for w in warnings)

    def test_missing_input_from_warns(self) -> None:
        preview = _make_preview(tasks=[
            {"task_id": "t1", "task": "A", "caste": "coder"},
            {"task_id": "t2", "task": "B", "caste": "coder",
             "depends_on": ["t1"]},
        ])
        normalized = normalize_preview(preview)
        # input_from falls back to depends_on, so no warning
        _, warnings = validate_plan(normalized)
        # Should NOT warn because normalize fills input_from from depends_on
        assert not any("input_from" in w for w in warnings)

    def test_empty_task_text_warns(self) -> None:
        preview = _make_preview(tasks=[
            {"task_id": "t1", "task": "", "caste": "coder"},
        ], groups=[{"taskIds": ["t1"]}])
        normalized = normalize_preview(preview)
        _, warnings = validate_plan(normalized)
        assert any("empty text" in w.lower() for w in warnings)

    def test_empty_group_rejected(self) -> None:
        preview = _make_preview(tasks=[
            {"task_id": "t1", "task": "A", "caste": "coder"},
        ], groups=[{"taskIds": ["t1"]}, {"taskIds": []}])
        normalized = normalize_preview(preview)
        errors, _ = validate_plan(normalized)
        assert any("empty" in e.lower() for e in errors)
