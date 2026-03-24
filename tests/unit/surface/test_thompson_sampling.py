"""Tests for Thompson Sampling distribution properties (Wave 31 B3).

Verifies that Beta distribution sampling used in knowledge retrieval
produces statistically correct results.
"""

from __future__ import annotations

import random
import statistics


class TestThompsonSamplingDistribution:
    """Verify Beta distribution properties used in Thompson Sampling retrieval."""

    def test_beta_mean_near_expected(self) -> None:
        """Beta(10, 5) samples should have mean near 10/(10+5) ≈ 0.667."""
        random.seed(42)
        alpha, beta_param = 10.0, 5.0
        samples = [random.betavariate(alpha, beta_param) for _ in range(2000)]
        mean = statistics.mean(samples)
        expected = alpha / (alpha + beta_param)
        assert abs(mean - expected) < 0.03, f"Mean {mean} too far from expected {expected}"

    def test_beta_variance_near_formula(self) -> None:
        """Beta(10, 5) variance should match a*b / ((a+b)^2 * (a+b+1))."""
        random.seed(42)
        alpha, beta_param = 10.0, 5.0
        samples = [random.betavariate(alpha, beta_param) for _ in range(2000)]
        var = statistics.variance(samples)
        expected_var = (alpha * beta_param) / (
            (alpha + beta_param) ** 2 * (alpha + beta_param + 1)
        )
        assert abs(var - expected_var) < 0.005, (
            f"Variance {var} too far from expected {expected_var}"
        )

    def test_seeded_deterministic_ranking(self) -> None:
        """With seed(42), known (alpha, beta) pairs produce deterministic ranking."""
        random.seed(42)
        entries = [
            ("high", 20.0, 5.0),      # high confidence
            ("medium", 10.0, 10.0),    # medium confidence
            ("low", 5.0, 20.0),        # low confidence
        ]
        samples = [(name, random.betavariate(a, b)) for name, a, b in entries]
        ranked = sorted(samples, key=lambda x: -x[1])

        # With seed(42), re-run to verify same order
        random.seed(42)
        samples2 = [(name, random.betavariate(a, b)) for name, a, b in entries]
        ranked2 = sorted(samples2, key=lambda x: -x[1])

        assert [r[0] for r in ranked] == [r[0] for r in ranked2]

    def test_beta_samples_bounded_zero_one(self) -> None:
        """All Beta samples must be in (0, 1)."""
        random.seed(42)
        samples = [random.betavariate(10.0, 5.0) for _ in range(1000)]
        assert all(0.0 < s < 1.0 for s in samples)

    def test_high_confidence_entry_ranked_above_low(self) -> None:
        """Over many trials, Beta(20, 5) dominates Beta(5, 20)."""
        random.seed(42)
        wins = 0
        trials = 1000
        for _ in range(trials):
            high = random.betavariate(20.0, 5.0)
            low = random.betavariate(5.0, 20.0)
            if high > low:
                wins += 1
        assert wins > 900, f"High-confidence entry should win most trials, got {wins}"

    def test_ks_distribution_if_scipy_available(self) -> None:
        """If scipy is available, verify Beta distribution via KS test."""
        try:
            from scipy import stats  # noqa: PLC0415
        except ImportError:
            return  # skip gracefully

        random.seed(42)
        alpha, beta_param = 10.0, 5.0
        samples = [random.betavariate(alpha, beta_param) for _ in range(10_000)]
        _stat, p_value = stats.kstest(samples, "beta", args=(alpha, beta_param))
        assert p_value > 0.01, f"KS test failed: p-value={p_value} (distribution mismatch)"
