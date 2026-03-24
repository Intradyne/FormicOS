"""Wave 41 B4: Tests for cost efficiency reporting in proactive intelligence.

Validates:
  - CostEfficiencyReport computes correct metrics
  - Quality-by-cost-quartile analysis
  - Early stop candidate detection
  - Edge cases: empty outcomes, zero-cost, zero-quality
  - RetrievalMetrics tracking
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from formicos.surface.knowledge_catalog import RetrievalMetrics
from formicos.surface.proactive_intelligence import compute_cost_efficiency

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_outcome(
    colony_id: str,
    workspace_id: str = "ws-1",
    succeeded: bool = True,
    total_rounds: int = 5,
    total_cost: float = 0.5,
    quality_score: float = 0.7,
    entries_extracted: int = 2,
    entries_accessed: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        colony_id=colony_id,
        workspace_id=workspace_id,
        succeeded=succeeded,
        total_rounds=total_rounds,
        total_cost=total_cost,
        quality_score=quality_score,
        entries_extracted=entries_extracted,
        entries_accessed=entries_accessed,
    )


# ---------------------------------------------------------------------------
# CostEfficiencyReport
# ---------------------------------------------------------------------------


class TestCostEfficiency:
    def test_basic_metrics(self) -> None:
        outcomes = {
            "c1": _make_outcome("c1", total_cost=0.50, quality_score=0.8),
            "c2": _make_outcome("c2", total_cost=0.30, quality_score=0.6),
            "c3": _make_outcome("c3", total_cost=0.20, quality_score=0.9),
        }
        report = compute_cost_efficiency("ws-1", outcomes)
        assert report.total_colonies == 3
        assert report.successful_colonies == 3
        assert report.total_cost == pytest.approx(1.0)
        assert report.avg_cost_per_colony == pytest.approx(1.0 / 3, abs=0.01)

    def test_cost_per_quality_point(self) -> None:
        outcomes = {
            "c1": _make_outcome("c1", total_cost=1.0, quality_score=0.5),
        }
        report = compute_cost_efficiency("ws-1", outcomes)
        # cost/quality = 1.0 / 0.5 = 2.0
        assert report.avg_cost_per_quality_point == pytest.approx(2.0)

    def test_avg_rounds_to_success(self) -> None:
        outcomes = {
            "c1": _make_outcome("c1", total_rounds=4),
            "c2": _make_outcome("c2", total_rounds=6),
        }
        report = compute_cost_efficiency("ws-1", outcomes)
        assert report.avg_rounds_to_success == pytest.approx(5.0)

    def test_failed_colonies_excluded_from_success_metrics(self) -> None:
        outcomes = {
            "c1": _make_outcome("c1", succeeded=True, total_cost=0.5, quality_score=0.8),
            "c2": _make_outcome("c2", succeeded=False, total_cost=1.0, quality_score=0.1),
        }
        report = compute_cost_efficiency("ws-1", outcomes)
        assert report.total_colonies == 2
        assert report.successful_colonies == 1
        # Cost per quality should only consider the successful colony
        assert report.avg_cost_per_quality_point == pytest.approx(0.5 / 0.8, abs=0.01)

    def test_early_stop_candidates(self) -> None:
        outcomes = {
            "c1": _make_outcome("c1", total_rounds=12, quality_score=0.2, total_cost=1.0),
            "c2": _make_outcome("c2", total_rounds=3, quality_score=0.9, total_cost=0.3),
        }
        report = compute_cost_efficiency("ws-1", outcomes)
        assert len(report.early_stop_candidates) == 1
        assert report.early_stop_candidates[0]["colony_id"] == "c1"
        assert report.early_stop_candidates[0]["rounds"] == 12

    def test_no_early_stop_for_high_quality(self) -> None:
        outcomes = {
            "c1": _make_outcome("c1", total_rounds=12, quality_score=0.8, total_cost=1.0),
        }
        report = compute_cost_efficiency("ws-1", outcomes)
        assert len(report.early_stop_candidates) == 0

    def test_quality_by_cost_quartile(self) -> None:
        outcomes = {}
        for i in range(8):
            outcomes[f"c{i}"] = _make_outcome(
                f"c{i}",
                total_cost=0.1 * (i + 1),
                quality_score=0.5 + 0.05 * i,
            )
        report = compute_cost_efficiency("ws-1", outcomes)
        assert len(report.quality_by_cost_quartile) > 0
        for q in report.quality_by_cost_quartile:
            assert "quartile" in q
            assert "avg_quality" in q
            assert "avg_cost" in q

    def test_empty_outcomes(self) -> None:
        report = compute_cost_efficiency("ws-1", {})
        assert report.total_colonies == 0
        assert report.total_cost == 0.0
        assert report.avg_cost_per_colony == 0.0
        assert report.avg_cost_per_quality_point == 0.0

    def test_filters_by_workspace(self) -> None:
        outcomes = {
            "c1": _make_outcome("c1", workspace_id="ws-1"),
            "c2": _make_outcome("c2", workspace_id="ws-other"),
        }
        report = compute_cost_efficiency("ws-1", outcomes)
        assert report.total_colonies == 1

    def test_zero_quality_does_not_crash(self) -> None:
        outcomes = {
            "c1": _make_outcome("c1", quality_score=0.0, total_cost=0.5),
        }
        report = compute_cost_efficiency("ws-1", outcomes)
        # Zero quality means cost/quality is undefined — should be 0
        assert report.avg_cost_per_quality_point == 0.0


# ---------------------------------------------------------------------------
# RetrievalMetrics
# ---------------------------------------------------------------------------


class TestRetrievalMetrics:
    def test_record_access(self) -> None:
        m = RetrievalMetrics()
        m.record_access(["entry-1", "entry-2"])
        assert m.total_queries == 1
        assert m.total_results_returned == 2
        assert m.entries_accessed["entry-1"] == 1

    def test_multiple_accesses(self) -> None:
        m = RetrievalMetrics()
        m.record_access(["entry-1"])
        m.record_access(["entry-1", "entry-2"])
        assert m.total_queries == 2
        assert m.entries_accessed["entry-1"] == 2
        assert m.entries_accessed["entry-2"] == 1

    def test_snapshot(self) -> None:
        m = RetrievalMetrics()
        m.record_access(["e1", "e2"])
        snap = m.snapshot()
        assert snap["total_queries"] == 1
        assert snap["unique_entries_accessed"] == 2

    def test_reset(self) -> None:
        m = RetrievalMetrics()
        m.record_access(["e1"])
        m.reset()
        assert m.total_queries == 0
        assert len(m.entries_accessed) == 0

    def test_empty_access_list(self) -> None:
        m = RetrievalMetrics()
        m.record_access([])
        assert m.total_queries == 1
        assert m.total_results_returned == 0
