"""Wave 41 A2: TS/UCB confidence-term unification tests."""

from __future__ import annotations

from formicos.engine.scoring_math import exploration_score


class TestExplorationScore:
    """Tests for the unified exploration-confidence helper."""

    def test_pure_thompson_bounded(self) -> None:
        """Thompson-only draws are in [0, 1]."""
        for _ in range(50):
            score = exploration_score(5.0, 5.0)
            assert 0.0 <= score <= 1.0

    def test_high_alpha_draws_high(self) -> None:
        """High alpha, low beta should draw high on average."""
        draws = [exploration_score(50.0, 2.0) for _ in range(100)]
        mean = sum(draws) / len(draws)
        assert mean > 0.7

    def test_low_alpha_draws_low(self) -> None:
        """Low alpha, high beta should draw low on average."""
        draws = [exploration_score(2.0, 50.0) for _ in range(100)]
        mean = sum(draws) / len(draws)
        assert mean < 0.3

    def test_ucb_weight_increases_score(self) -> None:
        """Positive UCB weight should increase scores for under-explored entries."""
        # Under-explored entry (low n_obs)
        pure = [exploration_score(2.0, 2.0) for _ in range(200)]
        with_ucb = [
            exploration_score(
                2.0, 2.0,
                total_observations=100,
                ucb_weight=0.3,
            )
            for _ in range(200)
        ]
        # UCB version should average higher due to exploration bonus
        assert sum(with_ucb) / len(with_ucb) > sum(pure) / len(pure)

    def test_ucb_zero_weight_equals_thompson(self) -> None:
        """With ucb_weight=0, result equals pure Thompson (tested via bounds)."""
        import random
        random.seed(42)
        pure = [exploration_score(10.0, 5.0) for _ in range(50)]
        random.seed(42)
        with_zero = [
            exploration_score(10.0, 5.0, ucb_weight=0.0) for _ in range(50)
        ]
        assert pure == with_zero

    def test_clamped_to_one(self) -> None:
        """Even with high UCB bonus, result is capped at 1.0."""
        for _ in range(50):
            score = exploration_score(
                50.0, 2.0,
                total_observations=10000,
                ucb_weight=1.0,
            )
            assert score <= 1.0

    def test_safe_with_zero_params(self) -> None:
        """Zero or negative alpha/beta doesn't crash."""
        score = exploration_score(0.0, 0.0)
        assert 0.0 <= score <= 1.0
        score = exploration_score(-1.0, 5.0)
        assert 0.0 <= score <= 1.0
