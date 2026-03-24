"""Wave 42 Pillar 4: Tests for adaptive evaporation control law.

Validates:
  - Branching factor computation (exp(entropy) over pheromone weights)
  - Adaptive evaporation rate selection based on stagnation signals
  - Normal-path stability (healthy colonies use fixed 0.95 rate)
  - Stagnation response (low branching + stalls → faster evaporation)
  - _update_pheromones integrates stall_count correctly
  - Bounded behavior: rate stays in [0.85, 0.95]
"""

from __future__ import annotations

import math

import pytest

from formicos.engine.runner import (
    _EVAPORATE_MAX,
    _EVAPORATE_MIN,
    RoundRunner,
)

# ---------------------------------------------------------------------------
# Branching factor computation
# ---------------------------------------------------------------------------


class TestPheromBranchingFactor:
    def test_no_weights_returns_zero(self) -> None:
        assert RoundRunner._pheromone_branching_factor(None) == 0.0

    def test_empty_weights_returns_zero(self) -> None:
        assert RoundRunner._pheromone_branching_factor({}) == 0.0

    def test_single_edge(self) -> None:
        weights: dict[tuple[str, str], float] = {("a", "b"): 1.0}
        bf = RoundRunner._pheromone_branching_factor(weights)
        # Single edge: entropy=0, exp(0)=1.0
        assert bf == pytest.approx(1.0)

    def test_uniform_edges(self) -> None:
        """Uniform weights → max entropy → branching factor = edge count."""
        weights: dict[tuple[str, str], float] = {
            ("a", "b"): 1.0,
            ("b", "c"): 1.0,
            ("c", "d"): 1.0,
            ("d", "e"): 1.0,
        }
        bf = RoundRunner._pheromone_branching_factor(weights)
        assert bf == pytest.approx(4.0, abs=0.01)

    def test_skewed_edges(self) -> None:
        """Highly skewed weights → low entropy → low branching factor."""
        weights: dict[tuple[str, str], float] = {
            ("a", "b"): 10.0,
            ("b", "c"): 0.1,
            ("c", "d"): 0.1,
        }
        bf = RoundRunner._pheromone_branching_factor(weights)
        # Should be closer to 1.0 than to 3.0
        assert bf < 2.0

    def test_matches_exp_entropy_formula(self) -> None:
        """Verify the formula: exp(-sum(p*log(p)))."""
        weights: dict[tuple[str, str], float] = {
            ("a", "b"): 3.0,
            ("b", "c"): 1.0,
        }
        total = 4.0
        p1, p2 = 3.0 / total, 1.0 / total
        expected_entropy = -(p1 * math.log(p1) + p2 * math.log(p2))
        expected_bf = math.exp(expected_entropy)
        bf = RoundRunner._pheromone_branching_factor(weights)
        assert bf == pytest.approx(expected_bf, abs=0.001)


# ---------------------------------------------------------------------------
# Adaptive evaporation rate
# ---------------------------------------------------------------------------


class TestAdaptiveEvaporationRate:
    def test_no_stall_returns_max(self) -> None:
        """No stagnation → normal evaporation rate."""
        weights: dict[tuple[str, str], float] = {("a", "b"): 1.5}
        rate = RoundRunner._adaptive_evaporation_rate(weights, stall_count=0)
        assert rate == _EVAPORATE_MAX

    def test_high_branching_ignores_stalls(self) -> None:
        """High branching factor → normal rate even with stalls."""
        weights: dict[tuple[str, str], float] = {
            ("a", "b"): 1.0,
            ("b", "c"): 1.0,
            ("c", "d"): 1.0,
        }
        # bf = 3.0 ≥ 2.0 threshold
        rate = RoundRunner._adaptive_evaporation_rate(weights, stall_count=3)
        assert rate == _EVAPORATE_MAX

    def test_low_branching_with_stalls_lowers_rate(self) -> None:
        """Low branching + stalls → faster evaporation."""
        weights: dict[tuple[str, str], float] = {
            ("a", "b"): 10.0,
            ("b", "c"): 0.1,
        }
        # bf < 2.0 and stall_count > 0
        rate = RoundRunner._adaptive_evaporation_rate(weights, stall_count=2)
        assert rate < _EVAPORATE_MAX
        assert rate >= _EVAPORATE_MIN

    def test_max_stalls_gives_min_rate(self) -> None:
        """4+ stalls with low branching → minimum evaporation rate."""
        weights: dict[tuple[str, str], float] = {("a", "b"): 1.0}
        rate = RoundRunner._adaptive_evaporation_rate(weights, stall_count=4)
        assert rate == pytest.approx(_EVAPORATE_MIN)

    def test_stalls_beyond_four_capped(self) -> None:
        """Stall count beyond 4 doesn't go below minimum."""
        weights: dict[tuple[str, str], float] = {("a", "b"): 1.0}
        rate = RoundRunner._adaptive_evaporation_rate(weights, stall_count=10)
        assert rate == pytest.approx(_EVAPORATE_MIN)

    def test_interpolation_is_linear(self) -> None:
        """Rate interpolates linearly between max and min."""
        weights: dict[tuple[str, str], float] = {("a", "b"): 1.0}
        r1 = RoundRunner._adaptive_evaporation_rate(weights, stall_count=1)
        r2 = RoundRunner._adaptive_evaporation_rate(weights, stall_count=2)
        r3 = RoundRunner._adaptive_evaporation_rate(weights, stall_count=3)
        r4 = RoundRunner._adaptive_evaporation_rate(weights, stall_count=4)
        step = (_EVAPORATE_MAX - _EVAPORATE_MIN) / 4.0
        assert r1 == pytest.approx(_EVAPORATE_MAX - step, abs=0.001)
        assert r2 == pytest.approx(_EVAPORATE_MAX - 2 * step, abs=0.001)
        assert r3 == pytest.approx(_EVAPORATE_MAX - 3 * step, abs=0.001)
        assert r4 == pytest.approx(_EVAPORATE_MIN, abs=0.001)

    def test_none_weights_returns_max(self) -> None:
        """No weights → branching factor 0 but no stalls → max rate."""
        rate = RoundRunner._adaptive_evaporation_rate(None, stall_count=0)
        assert rate == _EVAPORATE_MAX

    def test_none_weights_with_stalls_returns_min(self) -> None:
        """No weights + stalls → bf=0 < threshold, adaptive kicks in."""
        rate = RoundRunner._adaptive_evaporation_rate(None, stall_count=4)
        assert rate == pytest.approx(_EVAPORATE_MIN)


# ---------------------------------------------------------------------------
# _update_pheromones with stall_count
# ---------------------------------------------------------------------------


class TestUpdatePheromonesAdaptive:
    def test_healthy_path_unchanged(self) -> None:
        """With stall_count=0, behavior matches the original fixed rate."""
        weights: dict[tuple[str, str], float] = {("a1", "a2"): 1.0}
        updated = RoundRunner._update_pheromones(
            weights=weights,
            active_edges=[("a1", "a2")],
            governance_action="continue",
            convergence_progress=0.1,
            stall_count=0,
        )
        # Evaporate: 1.0 + (1.0-1.0)*0.95 = 1.0, strengthen: 1.0*1.15 = 1.15
        assert updated[("a1", "a2")] == pytest.approx(1.15, abs=0.01)

    def test_stagnation_flattens_landscape(self) -> None:
        """Under stagnation, high weights decay faster toward 1.0."""
        high_weight: dict[tuple[str, str], float] = {("a", "b"): 1.8}
        # No stall: evap at 0.95
        normal = RoundRunner._update_pheromones(
            weights=high_weight,
            active_edges=[],
            governance_action="continue",
            convergence_progress=0.0,
            stall_count=0,
        )
        # With stall (low branching, 1 edge → bf=1.0 < 2.0)
        stagnant = RoundRunner._update_pheromones(
            weights=high_weight,
            active_edges=[],
            governance_action="continue",
            convergence_progress=0.0,
            stall_count=3,
        )
        # Stagnant path should evaporate more (weight closer to 1.0)
        assert stagnant[("a", "b")] < normal[("a", "b")]

    def test_default_stall_count_is_zero(self) -> None:
        """Calling without stall_count uses the default (0) — backward compat."""
        weights: dict[tuple[str, str], float] = {("a1", "a2"): 1.5}
        updated = RoundRunner._update_pheromones(
            weights=weights,
            active_edges=[("a1", "a2")],
            governance_action="warn",
            convergence_progress=0.0,
        )
        # Should use _EVAPORATE_MAX = 0.95 (same as old fixed rate)
        evap = 1.0 + (1.5 - 1.0) * 0.95  # 1.475
        weakened = evap * 0.75  # 1.10625
        assert updated[("a1", "a2")] == pytest.approx(weakened, abs=0.01)

    def test_evaporation_rate_bounded(self) -> None:
        """Even extreme stalls keep rate in [_EVAPORATE_MIN, _EVAPORATE_MAX]."""
        weights: dict[tuple[str, str], float] = {("a", "b"): 2.0}
        for stall in range(0, 10):
            updated = RoundRunner._update_pheromones(
                weights=weights,
                active_edges=[],
                governance_action="continue",
                convergence_progress=0.0,
                stall_count=stall,
            )
            # Weight should always be >= 1.0 (evaporation toward 1.0)
            # and the rate used should be bounded
            w = updated[("a", "b")]
            # Fastest possible: 1.0 + (2.0-1.0)*0.85 = 1.85
            # Slowest possible: 1.0 + (2.0-1.0)*0.95 = 1.95
            assert 1.85 <= w <= 1.95
