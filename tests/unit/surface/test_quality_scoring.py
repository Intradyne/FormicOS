"""Tests for compute_quality_score (ADR-011 weighted geometric mean)."""

from __future__ import annotations

import pytest

from formicos.surface.colony_manager import compute_quality_score


class TestComputeQualityScore:
    """Verify the ADR-011 composite quality score formula."""

    def test_failed_colony_returns_zero(self) -> None:
        assert compute_quality_score(
            rounds_completed=5,
            max_rounds=10,
            convergence=0.9,
            governance_warnings=0,
            stall_rounds=0,
            completed_successfully=False,
        ) == 0.0

    def test_perfect_score(self) -> None:
        """One round, full convergence, no warnings, no stalls, high productivity → near 1.0."""
        score = compute_quality_score(
            rounds_completed=1,
            max_rounds=25,
            convergence=1.0,
            governance_warnings=0,
            stall_rounds=0,
            completed_successfully=True,
            productive_calls=10,
            total_calls=10,
        )
        assert 0.9 <= score <= 1.0

    def test_score_in_unit_interval(self) -> None:
        score = compute_quality_score(
            rounds_completed=10,
            max_rounds=25,
            convergence=0.7,
            governance_warnings=1,
            stall_rounds=2,
            completed_successfully=True,
        )
        assert 0.0 <= score <= 1.0

    def test_more_warnings_lower_score(self) -> None:
        base = compute_quality_score(
            rounds_completed=5,
            max_rounds=25,
            convergence=0.8,
            governance_warnings=0,
            stall_rounds=0,
            completed_successfully=True,
        )
        worse = compute_quality_score(
            rounds_completed=5,
            max_rounds=25,
            convergence=0.8,
            governance_warnings=2,
            stall_rounds=0,
            completed_successfully=True,
        )
        assert worse < base

    def test_more_stalls_lower_score(self) -> None:
        base = compute_quality_score(
            rounds_completed=10,
            max_rounds=25,
            convergence=0.8,
            governance_warnings=0,
            stall_rounds=0,
            completed_successfully=True,
        )
        worse = compute_quality_score(
            rounds_completed=10,
            max_rounds=25,
            convergence=0.8,
            governance_warnings=0,
            stall_rounds=5,
            completed_successfully=True,
        )
        assert worse < base

    def test_higher_convergence_higher_score(self) -> None:
        low = compute_quality_score(
            rounds_completed=5,
            max_rounds=25,
            convergence=0.3,
            governance_warnings=0,
            stall_rounds=0,
            completed_successfully=True,
        )
        high = compute_quality_score(
            rounds_completed=5,
            max_rounds=25,
            convergence=0.95,
            governance_warnings=0,
            stall_rounds=0,
            completed_successfully=True,
        )
        assert high > low

    def test_max_rounds_exhausted_still_scores(self) -> None:
        """When rounds_completed == max_rounds, round_efficiency is clamped to 0.20."""
        score = compute_quality_score(
            rounds_completed=25,
            max_rounds=25,
            convergence=0.9,
            governance_warnings=0,
            stall_rounds=0,
            completed_successfully=True,
        )
        assert 0.0 < score < 1.0

    def test_zero_max_rounds_does_not_divide_by_zero(self) -> None:
        score = compute_quality_score(
            rounds_completed=0,
            max_rounds=0,
            convergence=0.5,
            governance_warnings=0,
            stall_rounds=0,
            completed_successfully=True,
        )
        assert 0.0 <= score <= 1.0

    def test_higher_productivity_higher_score(self) -> None:
        """Wave 54.5: productive tool calls should raise quality score."""
        low = compute_quality_score(
            rounds_completed=8,
            max_rounds=8,
            convergence=0.5,
            governance_warnings=0,
            stall_rounds=0,
            completed_successfully=True,
            productive_calls=1,
            total_calls=20,
        )
        high = compute_quality_score(
            rounds_completed=8,
            max_rounds=8,
            convergence=0.5,
            governance_warnings=0,
            stall_rounds=0,
            completed_successfully=True,
            productive_calls=15,
            total_calls=20,
        )
        assert high > low

    def test_no_productivity_data_backward_compatible(self) -> None:
        """Without productive_calls/total_calls, score still works (defaults to floor)."""
        score = compute_quality_score(
            rounds_completed=5,
            max_rounds=25,
            convergence=0.8,
            governance_warnings=0,
            stall_rounds=0,
            completed_successfully=True,
        )
        assert 0.0 < score < 1.0

    def test_zero_convergence_clamped(self) -> None:
        """Zero convergence is clamped to 0.01, not log(0)."""
        score = compute_quality_score(
            rounds_completed=5,
            max_rounds=25,
            convergence=0.0,
            governance_warnings=0,
            stall_rounds=0,
            completed_successfully=True,
        )
        assert 0.0 < score < 1.0
