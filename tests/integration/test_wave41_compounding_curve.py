"""Wave 41 B3: Integration tests for compounding-curve computation and reporting.

Validates:
  - Curve computation produces all three views
  - Trend detection works correctly
  - Reports are generated as valid markdown
  - Knowledge contribution tracking is coherent
  - Edge cases: empty runs, zero-cost tasks, single-task sequences
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from formicos.eval.compounding_curve import (
    _trend_indicator,
    compute_curves,
    generate_compounding_report,
    generate_curve_report,
)

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_run(
    tasks: list[dict[str, Any]] | None = None,
    suite_id: str = "test-suite",
) -> dict[str, Any]:
    """Build a mock sequential run result."""
    if tasks is None:
        tasks = [
            {
                "task_id": "task-a",
                "sequence_index": 0,
                "quality_score": 0.6,
                "cost": 0.50,
                "wall_time_s": 30.0,
                "entries_extracted": 2,
                "entries_accessed": 0,
            },
            {
                "task_id": "task-b",
                "sequence_index": 1,
                "quality_score": 0.65,
                "cost": 0.45,
                "wall_time_s": 28.0,
                "entries_extracted": 1,
                "entries_accessed": 2,
            },
            {
                "task_id": "task-c",
                "sequence_index": 2,
                "quality_score": 0.75,
                "cost": 0.40,
                "wall_time_s": 25.0,
                "entries_extracted": 3,
                "entries_accessed": 3,
            },
            {
                "task_id": "task-d",
                "sequence_index": 3,
                "quality_score": 0.80,
                "cost": 0.35,
                "wall_time_s": 22.0,
                "entries_extracted": 2,
                "entries_accessed": 5,
            },
        ]
    return {
        "conditions": {
            "suite_id": suite_id,
            "task_order": [t["task_id"] for t in tasks],
            "strategy": "stigmergic",
            "model_mix": {},
            "budget_per_task": 2.0,
            "max_rounds_per_task": 10,
            "escalation_policy": "none",
            "knowledge_persistence": True,
            "config_hash": "abc123",
        },
        "tasks": tasks,
        "total_cost": sum(t["cost"] for t in tasks),
        "total_wall_time_s": sum(t["wall_time_s"] for t in tasks),
    }


# ---------------------------------------------------------------------------
# Curve computation
# ---------------------------------------------------------------------------


class TestComputeCurves:
    def test_produces_all_three_curves(self) -> None:
        run = _make_run()
        curves = compute_curves(run)
        assert "raw_curve" in curves
        assert "cost_curve" in curves
        assert "time_curve" in curves
        assert len(curves["raw_curve"]) == 4
        assert len(curves["cost_curve"]) == 4
        assert len(curves["time_curve"]) == 4

    def test_raw_curve_values(self) -> None:
        run = _make_run()
        curves = compute_curves(run)
        qualities = [p["quality_score"] for p in curves["raw_curve"]]
        assert qualities == [0.6, 0.65, 0.75, 0.80]

    def test_cost_normalized_values(self) -> None:
        run = _make_run()
        curves = compute_curves(run)
        for p in curves["cost_curve"]:
            assert p["quality_per_dollar"] > 0

    def test_time_normalized_values(self) -> None:
        run = _make_run()
        curves = compute_curves(run)
        for p in curves["time_curve"]:
            assert p["quality_per_second"] > 0

    def test_cumulative_view(self) -> None:
        run = _make_run()
        curves = compute_curves(run)
        cum = curves["cumulative"]
        assert len(cum) == 4
        # Cumulative quality should be monotonically increasing
        for i in range(1, len(cum)):
            assert cum[i]["cum_quality"] >= cum[i - 1]["cum_quality"]
        # Cumulative cost should be monotonically increasing
        for i in range(1, len(cum)):
            assert cum[i]["cum_cost"] >= cum[i - 1]["cum_cost"]

    def test_knowledge_contribution(self) -> None:
        run = _make_run()
        curves = compute_curves(run)
        kc = curves["knowledge_contribution"]
        assert kc["total_extracted"] == 8  # 2+1+3+2
        assert kc["total_accessed"] == 10  # 0+2+3+5
        assert kc["access_ratio"] > 0

    def test_empty_run(self) -> None:
        run = _make_run(tasks=[])
        curves = compute_curves(run)
        assert curves["raw_curve"] == []
        assert curves["cost_curve"] == []
        assert curves["time_curve"] == []

    def test_zero_cost_task(self) -> None:
        tasks = [
            {
                "task_id": "free-task",
                "sequence_index": 0,
                "quality_score": 0.5,
                "cost": 0.0,
                "wall_time_s": 10.0,
                "entries_extracted": 0,
                "entries_accessed": 0,
            },
        ]
        run = _make_run(tasks=tasks)
        curves = compute_curves(run)
        # Should not crash on division by zero
        assert curves["cost_curve"][0]["quality_per_dollar"] == 0.0

    def test_single_task(self) -> None:
        tasks = [
            {
                "task_id": "only-task",
                "sequence_index": 0,
                "quality_score": 0.7,
                "cost": 0.5,
                "wall_time_s": 30.0,
                "entries_extracted": 1,
                "entries_accessed": 0,
            },
        ]
        run = _make_run(tasks=tasks)
        curves = compute_curves(run)
        assert len(curves["raw_curve"]) == 1
        assert curves["knowledge_contribution"]["total_extracted"] == 1


# ---------------------------------------------------------------------------
# Trend detection
# ---------------------------------------------------------------------------


class TestTrendIndicator:
    def test_rising(self) -> None:
        assert "rising" in _trend_indicator([0.5, 0.5, 0.8, 0.9])

    def test_declining(self) -> None:
        assert "declining" in _trend_indicator([0.9, 0.8, 0.4, 0.3])

    def test_flat(self) -> None:
        assert "flat" in _trend_indicator([0.5, 0.5, 0.5, 0.5])

    def test_insufficient_data(self) -> None:
        assert _trend_indicator([0.5]) == "insufficient data"

    def test_empty(self) -> None:
        assert _trend_indicator([]) == "insufficient data"


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


class TestCurveReport:
    def test_report_is_valid_markdown(self) -> None:
        run = _make_run()
        curves = compute_curves(run)
        report = generate_curve_report("test-suite", run, curves)
        assert report.startswith("# Compounding Curve Report:")
        assert "## Experiment Conditions (Locked)" in report
        assert "## 1. Raw Performance Curve" in report
        assert "## 2. Cost-Normalized Curve" in report
        assert "## 3. Time-Normalized Curve" in report
        assert "## 4. Knowledge Contribution" in report
        assert "## 5. Cumulative View" in report

    def test_report_includes_locked_conditions(self) -> None:
        run = _make_run()
        curves = compute_curves(run)
        report = generate_curve_report("test-suite", run, curves)
        assert "stigmergic" in report
        assert "abc123" in report
        assert "task-a" in report

    def test_report_includes_trend(self) -> None:
        run = _make_run()
        curves = compute_curves(run)
        report = generate_curve_report("test-suite", run, curves)
        assert "**Trend:**" in report

    def test_report_includes_disclaimer(self) -> None:
        run = _make_run()
        curves = compute_curves(run)
        report = generate_curve_report("test-suite", run, curves)
        assert "Exploratory measurement" in report
        assert "flat curve is an honest finding" in report

    def test_file_based_report_generation(self, tmp_path: Path) -> None:
        """Test end-to-end file generation."""
        # Set up data directory with a mock run result
        suite_dir = tmp_path / "eval" / "sequential" / "test-suite"
        suite_dir.mkdir(parents=True)
        run = _make_run(suite_id="test-suite")
        run_file = suite_dir / "run_20260319T000000.json"
        with run_file.open("w") as f:
            json.dump(run, f)

        result_path = generate_compounding_report(
            "test-suite", data_dir=tmp_path,
        )
        assert result_path is not None
        assert result_path.exists()

        content = result_path.read_text()
        assert "Compounding Curve Report" in content

        # Also check curve data JSON was created
        data_path = tmp_path / "eval" / "reports" / "compounding_test-suite_data.json"
        assert data_path.exists()
