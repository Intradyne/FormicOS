"""Wave 83 Track B: Plan pattern store tests."""

from __future__ import annotations

import shutil
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import yaml

from formicos.surface.plan_patterns import (
    auto_learn_pattern,
    get_pattern,
    list_patterns,
    save_pattern,
    verify_outcome,
)


@contextmanager
def _scratch_dir() -> Path:
    root = Path.cwd() / ".tmp_test_cases" / f"plan_patterns_{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _sample_payload(**overrides: object) -> dict:
    base = {
        "name": "Auth refactor plan",
        "description": "3-colony parallel plan for auth module",
        "thread_id": "th-001",
        "source_query": "refactor the auth module",
        "planner_model": "anthropic/claude-sonnet-4-6",
        "task_previews": [
            {"task_id": "t1", "task": "rewrite auth handler", "caste": "coder"},
            {"task_id": "t2", "task": "update auth tests", "caste": "coder"},
            {"task_id": "t3", "task": "review auth changes", "caste": "reviewer"},
        ],
        "groups": [["t1", "t2"], ["t3"]],
        "created_from": "reviewed_plan",
    }
    base.update(overrides)
    return base


class TestSavePattern:
    def test_save_and_retrieve(self) -> None:
        with _scratch_dir() as tmpdir:
            result = save_pattern(str(tmpdir), "ws1", _sample_payload())
            assert "pattern_id" in result
            assert result["name"] == "Auth refactor plan"
            assert result["created_from"] == "reviewed_plan"
            assert len(result["task_previews"]) == 3
            assert len(result["groups"]) == 2
            assert result["groups"][0]["taskIds"] == ["t1", "t2"]
            assert result["created_at"]  # non-empty ISO timestamp

    def test_save_generates_id(self) -> None:
        with _scratch_dir() as tmpdir:
            result = save_pattern(str(tmpdir), "ws1", _sample_payload())
            assert result["pattern_id"].startswith("pp-")

    def test_save_with_explicit_id(self) -> None:
        with _scratch_dir() as tmpdir:
            result = save_pattern(str(tmpdir), "ws1", _sample_payload(pattern_id="my-custom-id"))
            assert result["pattern_id"] == "my-custom-id"

    def test_save_with_outcome_summary(self) -> None:
        with _scratch_dir() as tmpdir:
            result = save_pattern(str(tmpdir), "ws1", _sample_payload(
                outcome_summary={"succeeded": 3, "total": 3, "quality_mean": 0.82},
            ))
            assert result["outcome_summary"]["succeeded"] == 3

    def test_save_creates_yaml_file(self) -> None:
        with _scratch_dir() as tmpdir:
            result = save_pattern(str(tmpdir), "ws1", _sample_payload())
            pid = result["pattern_id"]
            path = tmpdir / ".formicos" / "plan_patterns" / "ws1" / f"{pid}.yaml"
            assert path.exists()


class TestListPatterns:
    def test_empty_workspace(self) -> None:
        with _scratch_dir() as tmpdir:
            patterns = list_patterns(str(tmpdir), "ws1")
            assert patterns == []

    def test_list_returns_saved_patterns(self) -> None:
        with _scratch_dir() as tmpdir:
            save_pattern(str(tmpdir), "ws1", _sample_payload(name="Plan A"))
            save_pattern(str(tmpdir), "ws1", _sample_payload(name="Plan B"))
            patterns = list_patterns(str(tmpdir), "ws1")
            assert len(patterns) == 2
            names = {p["name"] for p in patterns}
            assert "Plan A" in names
            assert "Plan B" in names

    def test_list_isolated_per_workspace(self) -> None:
        with _scratch_dir() as tmpdir:
            save_pattern(str(tmpdir), "ws1", _sample_payload(name="WS1 plan"))
            save_pattern(str(tmpdir), "ws2", _sample_payload(name="WS2 plan"))
            ws1 = list_patterns(str(tmpdir), "ws1")
            ws2 = list_patterns(str(tmpdir), "ws2")
            assert len(ws1) == 1
            assert ws1[0]["name"] == "WS1 plan"
            assert len(ws2) == 1
            assert ws2[0]["name"] == "WS2 plan"


class TestGetPattern:
    def test_get_existing(self) -> None:
        with _scratch_dir() as tmpdir:
            saved = save_pattern(str(tmpdir), "ws1", _sample_payload())
            pid = saved["pattern_id"]
            result = get_pattern(str(tmpdir), "ws1", pid)
            assert result is not None
            assert result["pattern_id"] == pid
            assert result["name"] == "Auth refactor plan"

    def test_get_nonexistent_returns_none(self) -> None:
        with _scratch_dir() as tmpdir:
            assert get_pattern(str(tmpdir), "ws1", "nonexistent") is None

    def test_get_wrong_workspace_returns_none(self) -> None:
        with _scratch_dir() as tmpdir:
            saved = save_pattern(str(tmpdir), "ws1", _sample_payload())
            pid = saved["pattern_id"]
            assert get_pattern(str(tmpdir), "ws2", pid) is None

    def test_get_normalizes_legacy_group_shape(self) -> None:
        with _scratch_dir() as tmpdir:
            saved = save_pattern(str(tmpdir), "ws1", _sample_payload())
            pid = saved["pattern_id"]
            path = tmpdir / ".formicos" / "plan_patterns" / "ws1" / f"{pid}.yaml"
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            data["groups"] = [["t1", "t2"], ["t3"]]
            path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

            result = get_pattern(str(tmpdir), "ws1", pid)
            assert result is not None
            assert result["groups"][0]["taskIds"] == ["t1", "t2"]
            assert result["groups"][1]["taskIds"] == ["t3"]


class TestPatternFields:
    def test_minimum_fields_present(self) -> None:
        with _scratch_dir() as tmpdir:
            result = save_pattern(str(tmpdir), "ws1", _sample_payload())
            required = {
                "pattern_id", "name", "description", "workspace_id",
                "thread_id", "source_query", "planner_model",
                "task_previews", "groups", "created_at", "created_from",
            }
            assert required.issubset(set(result.keys()))

    def test_defaults_for_missing_fields(self) -> None:
        with _scratch_dir() as tmpdir:
            result = save_pattern(str(tmpdir), "ws1", {"name": "Minimal"})
            assert result["description"] == ""
            assert result["task_previews"] == []
            assert result["groups"] == []
            assert result["created_from"] == "reviewed_plan"


# ---------------------------------------------------------------------------
# Wave 86: Verification + Auto-learning
# ---------------------------------------------------------------------------


class TestVerifyOutcome:
    def test_high_quality_validated(self) -> None:
        v = verify_outcome(0.8)
        assert v["state"] == "validated"
        assert v["learnable"] is True

    def test_low_quality_failed(self) -> None:
        v = verify_outcome(0.2)
        assert v["state"] == "failed_delivery"
        assert v["learnable"] is False

    def test_marginal_needs_review(self) -> None:
        v = verify_outcome(0.5)
        assert v["state"] == "needs_review"
        assert v["learnable"] is False

    def test_validator_failure(self) -> None:
        v = verify_outcome(0.9, validator_verdict="fail")
        assert v["state"] == "failed_delivery"
        assert v["learnable"] is False

    def test_too_many_failed_colonies(self) -> None:
        v = verify_outcome(0.7, failed_colonies=3, total_colonies=4)
        assert v["state"] == "failed_delivery"

    def test_reasons_populated(self) -> None:
        v = verify_outcome(0.3, validator_verdict="fail")
        assert len(v["reasons"]) >= 1


class TestAutoLearnPattern:
    def test_creates_candidate_on_first_success(self) -> None:
        with _scratch_dir() as tmpdir:
            plan_data = {
                "task_previews": [
                    {"task_id": "t1", "task": "impl auth", "caste": "coder",
                     "target_files": ["auth.py"]},
                ],
                "groups": [{"taskIds": ["t1"], "tasks": ["impl auth"]}],
                "source_query": "implement auth",
            }
            result = auto_learn_pattern(
                str(tmpdir), "ws1",
                plan_data=plan_data,
                outcome={"quality": 0.8, "succeeded": 1, "total": 1},
                task_class="code_implementation",
            )
            assert result is not None
            assert result.get("status") == "candidate"
            assert result.get("learning_source") == "auto"

    def test_promotes_on_second_success(self) -> None:
        with _scratch_dir() as tmpdir:
            plan_data = {
                "task_previews": [
                    {"task_id": "t1", "task": "impl", "caste": "coder",
                     "target_files": ["auth.py"]},
                ],
                "groups": [{"taskIds": ["t1"], "tasks": ["impl"]}],
                "source_query": "implement",
            }
            outcome = {"quality": 0.8, "succeeded": 1, "total": 1}
            # First save -> candidate
            auto_learn_pattern(
                str(tmpdir), "ws1",
                plan_data=plan_data, outcome=outcome,
                task_class="code_implementation",
            )
            # Second save -> should promote
            auto_learn_pattern(
                str(tmpdir), "ws1",
                plan_data=plan_data, outcome=outcome,
                task_class="code_implementation",
            )
            patterns = list_patterns(str(tmpdir), "ws1")
            assert len(patterns) == 1  # deduped
            assert patterns[0].get("status") == "approved"

    def test_no_duplicate_on_same_bundle(self) -> None:
        with _scratch_dir() as tmpdir:
            plan_data = {
                "task_previews": [{"task_id": "t1", "task": "x", "caste": "coder"}],
                "groups": [],
                "source_query": "x",
            }
            outcome = {"quality": 0.8}
            auto_learn_pattern(
                str(tmpdir), "ws1",
                plan_data=plan_data, outcome=outcome,
                task_class="code_implementation",
            )
            auto_learn_pattern(
                str(tmpdir), "ws1",
                plan_data=plan_data, outcome=outcome,
                task_class="code_implementation",
            )
            patterns = list_patterns(str(tmpdir), "ws1")
            assert len(patterns) == 1
