"""Tests for symmetric archival gamma-burst (Wave 32 A2, ADR-041 D2).

Validates that archival decay is symmetric, preserves posterior mean,
converges toward prior, and respects hard floors.
"""

from __future__ import annotations

from formicos.surface.knowledge_constants import (
    ARCHIVAL_EQUIVALENT_DAYS,
    GAMMA_PER_DAY,
    PRIOR_ALPHA,
    PRIOR_BETA,
)


def _archival_decay(old_alpha: float, old_beta: float) -> tuple[float, float]:
    """Pure function replicating queen_thread archival decay logic."""
    archival_gamma = GAMMA_PER_DAY ** ARCHIVAL_EQUIVALENT_DAYS
    new_alpha = max(archival_gamma * old_alpha + (1 - archival_gamma) * PRIOR_ALPHA, 1.0)
    new_beta = max(archival_gamma * old_beta + (1 - archival_gamma) * PRIOR_BETA, 1.0)
    return new_alpha, new_beta


class TestArchivalDecaySymmetry:
    def test_posterior_mean_direction_preserved(self) -> None:
        """After archival decay, posterior mean stays on same side of 0.5."""
        old_a, old_b = 20.0, 5.0
        new_a, new_b = _archival_decay(old_a, old_b)
        old_mean = old_a / (old_a + old_b)
        new_mean = new_a / (new_a + new_b)
        # Both params decay toward same prior, so mean moves toward 0.5
        # but stays on the same side
        assert new_mean > 0.5, f"Mean crossed 0.5: {new_mean}"
        assert new_mean < old_mean, f"Mean should converge toward 0.5: {new_mean} >= {old_mean}"

    def test_symmetric_equal_params(self) -> None:
        """Beta(10,10) decays symmetrically — both params change equally."""
        new_a, new_b = _archival_decay(10.0, 10.0)
        assert abs(new_a - new_b) < 0.001, f"Asymmetric: alpha={new_a}, beta={new_b}"


class TestArchivalDecayConvergence:
    def test_convergence_toward_prior(self) -> None:
        """Entry at Beta(20, 5) moves closer to prior after archival."""
        old_a, old_b = 20.0, 5.0
        new_a, new_b = _archival_decay(old_a, old_b)
        # Alpha should move closer to PRIOR_ALPHA
        assert abs(new_a - PRIOR_ALPHA) < abs(old_a - PRIOR_ALPHA)
        # Beta stays at prior (5.0 == PRIOR_BETA)
        assert abs(new_b - PRIOR_BETA) <= abs(old_b - PRIOR_BETA) + 0.001

    def test_magnitude_check(self) -> None:
        """Entry at Beta(20, 20) → verify specific decay magnitude."""
        new_a, new_b = _archival_decay(20.0, 20.0)
        archival_gamma = GAMMA_PER_DAY ** ARCHIVAL_EQUIVALENT_DAYS
        expected = archival_gamma * 20.0 + (1 - archival_gamma) * 5.0
        assert abs(new_a - expected) < 0.01, f"Expected {expected}, got {new_a}"
        assert abs(new_b - expected) < 0.01, f"Expected {expected}, got {new_b}"


class TestArchivalDecayHardFloor:
    def test_hard_floor_low_params(self) -> None:
        """Entry at Beta(1.5, 1.5) → both still >= 1.0 after archival."""
        new_a, new_b = _archival_decay(1.5, 1.5)
        assert new_a >= 1.0, f"Alpha floor violated: {new_a}"
        assert new_b >= 1.0, f"Beta floor violated: {new_b}"

    def test_hard_floor_at_minimum(self) -> None:
        """Entry at Beta(1.0, 1.0) → floors hold."""
        new_a, new_b = _archival_decay(1.0, 1.0)
        assert new_a >= 1.0
        assert new_b >= 1.0


class TestArchivalDecayNotReset:
    def test_strong_signal_partially_retained(self) -> None:
        """Entry at Beta(50, 2) → alpha still > PRIOR_ALPHA after archival."""
        new_a, new_b = _archival_decay(50.0, 2.0)
        assert new_a > PRIOR_ALPHA, (
            f"Strong signal lost: new_alpha={new_a} <= prior={PRIOR_ALPHA}"
        )

    def test_not_a_full_reset(self) -> None:
        """Archival is not a reset to prior."""
        new_a, new_b = _archival_decay(30.0, 3.0)
        assert new_a != PRIOR_ALPHA or new_b != PRIOR_BETA, "Should not fully reset to prior"
