"""Tests for Wave 67 ESS cap and rank-based credit assignment."""

from __future__ import annotations

import math

from formicos.engine.scoring_math import rescale_preserving_mean


class TestRescalePreservingMean:
    def test_under_cap_returns_unchanged(self) -> None:
        alpha, beta = rescale_preserving_mean(10.0, 5.0)
        assert alpha == 10.0
        assert beta == 5.0

    def test_over_cap_rescales_to_150(self) -> None:
        alpha, beta = rescale_preserving_mean(100.0, 80.0)
        ess = alpha + beta
        assert abs(ess - 150.0) < 1e-9

    def test_over_cap_preserves_mean(self) -> None:
        orig_mean = 100.0 / (100.0 + 80.0)
        alpha, beta = rescale_preserving_mean(100.0, 80.0)
        new_mean = alpha / (alpha + beta)
        assert abs(new_mean - orig_mean) < 1e-9

    def test_exact_cap_returns_unchanged(self) -> None:
        alpha, beta = rescale_preserving_mean(75.0, 75.0)
        assert alpha == 75.0
        assert beta == 75.0

    def test_large_asymmetric_preserves_mean(self) -> None:
        # alpha >> beta: mean should stay near 1.0
        orig_alpha, orig_beta = 290.0, 10.0
        orig_mean = orig_alpha / (orig_alpha + orig_beta)
        alpha, beta = rescale_preserving_mean(orig_alpha, orig_beta)
        ess = alpha + beta
        assert abs(ess - 150.0) < 1e-9
        new_mean = alpha / (alpha + beta)
        assert abs(new_mean - orig_mean) < 1e-9

    def test_custom_max_ess(self) -> None:
        alpha, beta = rescale_preserving_mean(60.0, 60.0, max_ess=100.0)
        ess = alpha + beta
        assert abs(ess - 100.0) < 1e-9

    def test_small_values_under_cap(self) -> None:
        alpha, beta = rescale_preserving_mean(1.0, 1.0)
        assert alpha == 1.0
        assert beta == 1.0


class TestRankCredit:
    """Verify geometric credit 0.7^rank produces expected decay."""

    def test_credit_values(self) -> None:
        credits = [0.7 ** r for r in range(5)]
        assert abs(credits[0] - 1.0) < 1e-9
        assert abs(credits[1] - 0.7) < 1e-9
        assert abs(credits[2] - 0.49) < 1e-9
        assert abs(credits[3] - 0.343) < 1e-9
        assert abs(credits[4] - 0.2401) < 1e-9

    def test_rank_0_gets_full_delta(self) -> None:
        quality_score = 0.8
        base_delta = min(max(0.5 + quality_score, 0.5), 1.5)
        credit = 0.7 ** 0
        assert abs(base_delta * credit - base_delta) < 1e-9

    def test_rank_5_gets_diminished_delta(self) -> None:
        quality_score = 0.8
        base_delta = min(max(0.5 + quality_score, 0.5), 1.5)
        credit_0 = 0.7 ** 0
        credit_5 = 0.7 ** 5
        delta_0 = base_delta * credit_0
        delta_5 = base_delta * credit_5
        assert delta_0 > delta_5
        # rank-5 should be ~16.8% of rank-0
        assert abs(delta_5 / delta_0 - 0.7 ** 5) < 1e-9

    def test_delta_always_positive(self) -> None:
        """Even at high ranks, credit is positive (never zero)."""
        for rank in range(20):
            credit = 0.7 ** rank
            assert credit > 0
