"""Tests for time-based gamma-decay confidence update (Wave 32 A1, ADR-041 D1).

Tests the gamma-decay formula directly by computing expected values
and verifying properties: decay prevents convergence lock, replay
determinism, hard floor enforcement.
"""

from __future__ import annotations

from formicos.surface.knowledge_constants import GAMMA_PER_DAY, PRIOR_ALPHA, PRIOR_BETA


def _gamma_update(
    old_alpha: float,
    old_beta: float,
    elapsed_days: float,
    succeeded: bool,
) -> tuple[float, float]:
    """Pure function replicating colony_manager gamma-decay logic."""
    gamma_eff = GAMMA_PER_DAY ** elapsed_days
    decayed_alpha = gamma_eff * old_alpha + (1 - gamma_eff) * PRIOR_ALPHA
    decayed_beta = gamma_eff * old_beta + (1 - gamma_eff) * PRIOR_BETA

    if succeeded:
        new_alpha = max(decayed_alpha + 1.0, 1.0)
        new_beta = max(decayed_beta, 1.0)
    else:
        new_alpha = max(decayed_alpha, 1.0)
        new_beta = max(decayed_beta + 1.0, 1.0)
    return new_alpha, new_beta


class TestGammaDecayBasic:
    def test_basic_decay_success(self) -> None:
        """Entry at Beta(5,5), elapsed_days=1.0, success."""
        new_a, new_b = _gamma_update(5.0, 5.0, 1.0, succeeded=True)
        # gamma_eff = 0.98; decayed_alpha = 0.98*5 + 0.02*5 = 5.0; +1.0 = 6.0
        assert abs(new_a - 6.0) < 0.001
        assert abs(new_b - 5.0) < 0.001

    def test_no_decay_same_timestamp(self) -> None:
        """elapsed_days=0 means no decay component."""
        new_a, new_b = _gamma_update(5.0, 5.0, 0.0, succeeded=True)
        assert abs(new_a - 6.0) < 0.001
        assert abs(new_b - 5.0) < 0.001

    def test_alpha_rises_after_success(self) -> None:
        """After success with elapsed time, alpha rises but less than +1.0."""
        old_a, old_b = 10.0, 5.0
        new_a, new_b = _gamma_update(old_a, old_b, 7.0, succeeded=True)
        assert new_a > old_a, "Alpha should increase on success"
        # With decay, increase is less than 1.0 from old value when alpha > prior
        gamma_eff = GAMMA_PER_DAY ** 7.0
        decayed = gamma_eff * old_a + (1 - gamma_eff) * PRIOR_ALPHA
        assert new_a < old_a + 1.0, "Decay should reduce effective increase"
        assert abs(new_a - (decayed + 1.0)) < 0.001

    def test_failure_increments_beta(self) -> None:
        """Colony failure adds 1.0 to beta."""
        new_a, new_b = _gamma_update(5.0, 5.0, 1.0, succeeded=False)
        assert abs(new_a - 5.0) < 0.001
        assert abs(new_b - 6.0) < 0.001


class TestGammaDecayConvergence:
    def test_accumulation_bounded(self) -> None:
        """After 100 alternating observations (1/day), alpha+beta stabilizes."""
        alpha, beta = PRIOR_ALPHA, PRIOR_BETA
        for i in range(100):
            succeeded = (i % 2 == 0)
            alpha, beta = _gamma_update(alpha, beta, 1.0, succeeded)
        # Without decay: alpha+beta would be 5+5+100 = 110
        # With gamma=0.98/day decay, steady state is bounded well below that
        assert alpha + beta < 70.0, (
            f"Decay should prevent unbounded growth: alpha+beta={alpha + beta}"
        )
        # Verify it actually stabilized (not still growing)
        prev_sum = alpha + beta
        for i in range(100, 120):
            succeeded = (i % 2 == 0)
            alpha, beta = _gamma_update(alpha, beta, 1.0, succeeded)
        assert abs((alpha + beta) - prev_sum) < 3.0, "Should have stabilized"

    def test_stabilization_around_prior(self) -> None:
        """40 alternating observations then 5 successes — mean shifts up."""
        alpha, beta = PRIOR_ALPHA, PRIOR_BETA
        for i in range(40):
            succeeded = (i % 2 == 0)
            alpha, beta = _gamma_update(alpha, beta, 1.0, succeeded)

        mean_after_alternating = alpha / (alpha + beta)

        for _ in range(5):
            alpha, beta = _gamma_update(alpha, beta, 1.0, succeeded=True)

        mean_after_successes = alpha / (alpha + beta)
        # After 5 consecutive successes, mean should be noticeably above 0.5
        assert 0.54 <= mean_after_successes <= 0.75, (
            f"Posterior mean {mean_after_successes} outside expected [0.54, 0.75]"
        )
        assert mean_after_successes > mean_after_alternating


class TestGammaDecayHardFloor:
    def test_hard_floor_on_decay(self) -> None:
        """Entry near minimum stays above 1.0 after decay + failure."""
        new_a, new_b = _gamma_update(1.1, 1.1, 30.0, succeeded=False)
        assert new_a >= 1.0
        assert new_b >= 1.0

    def test_hard_floor_extreme_decay(self) -> None:
        """Even with very long elapsed time, floors hold."""
        new_a, new_b = _gamma_update(1.0, 1.0, 365.0, succeeded=False)
        assert new_a >= 1.0
        assert new_b >= 1.0


class TestGammaDecayReplayDeterminism:
    def test_replay_produces_identical_results(self) -> None:
        """Same sequence of (elapsed_days, succeeded) pairs → identical results."""
        sequence = [
            (1.0, True), (0.5, False), (2.0, True), (0.0, True),
            (7.0, False), (1.0, True),
        ]

        def run_sequence() -> list[tuple[float, float]]:
            alpha, beta = PRIOR_ALPHA, PRIOR_BETA
            results = []
            for elapsed, succeeded in sequence:
                alpha, beta = _gamma_update(alpha, beta, elapsed, succeeded)
                results.append((alpha, beta))
            return results

        run1 = run_sequence()
        run2 = run_sequence()
        for (a1, b1), (a2, b2) in zip(run1, run2):
            assert a1 == a2, f"Alpha mismatch: {a1} != {a2}"
            assert b1 == b2, f"Beta mismatch: {b1} != {b2}"
