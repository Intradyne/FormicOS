"""
Tests for FormicOS v0.6.0 Governance Engine.

Covers:
- Convergence fires after N consecutive high-similarity rounds
- Convergence does NOT fire if similarity drops below threshold mid-streak
- Path diversity detects single-approach tunneling
- Path diversity counts correctly with varied approaches
- Stall detection finds repeated failures in TKG
- Stall detection scopes by team_id
- Recommendations are non-empty when action is "intervene"
- Missing summary vectors returns "continue"
- Force halt after configurable streak count
"""

from __future__ import annotations

import numpy as np
import pytest

from src.governance import (
    GovernanceDecision,
    GovernanceEngine,
    _cosine_similarity,
)
from src.models import ConvergenceConfig, TemporalConfig, TKGTuple


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_config(
    similarity_threshold: float = 0.95,
    rounds_before_force_halt: int = 2,
    path_diversity_warning_after: int = 3,
    stall_repeat_threshold: int = 3,
    stall_window_minutes: int = 20,
) -> object:
    """Build a minimal config object with convergence + temporal settings."""

    class _Cfg:
        pass

    cfg = _Cfg()
    cfg.convergence = ConvergenceConfig(
        similarity_threshold=similarity_threshold,
        rounds_before_force_halt=rounds_before_force_halt,
        path_diversity_warning_after=path_diversity_warning_after,
    )
    cfg.temporal = TemporalConfig(
        stall_repeat_threshold=stall_repeat_threshold,
        stall_window_minutes=stall_window_minutes,
    )
    return cfg


def _unit_vec(dim: int = 128, seed: int = 42) -> list[float]:
    """Create a random unit vector of given dimension."""
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim)
    v = v / np.linalg.norm(v)
    return v.tolist()


def _near_identical_vec(base: list[float], noise: float = 0.001, seed: int = 99) -> list[float]:
    """Return a vector nearly identical to *base* (cosine sim ~1.0)."""
    rng = np.random.default_rng(seed)
    arr = np.asarray(base)
    perturbed = arr + rng.standard_normal(arr.shape) * noise
    perturbed = perturbed / np.linalg.norm(perturbed)
    return perturbed.tolist()


def _orthogonal_vec(base: list[float], seed: int = 7) -> list[float]:
    """Return a vector roughly orthogonal to *base* (low cosine sim)."""
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(len(base))
    base_arr = np.asarray(base)
    # Gram-Schmidt: remove component along base
    v = v - np.dot(v, base_arr) * base_arr
    norm = np.linalg.norm(v)
    if norm > 0:
        v = v / norm
    return v.tolist()


# ═══════════════════════════════════════════════════════════════════════════
# GovernanceDecision dataclass
# ═══════════════════════════════════════════════════════════════════════════


class TestGovernanceDecision:
    """Validate GovernanceDecision construction and constraints."""

    def test_valid_actions(self) -> None:
        for action in ("continue", "force_halt", "intervene", "warn_tunnel_vision"):
            d = GovernanceDecision(action=action, reason="test")
            assert d.action == action

    def test_invalid_action_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid action"):
            GovernanceDecision(action="explode", reason="boom")

    def test_recommendations_default_empty(self) -> None:
        d = GovernanceDecision(action="continue", reason="ok")
        assert d.recommendations == []


# ═══════════════════════════════════════════════════════════════════════════
# Cosine similarity helper
# ═══════════════════════════════════════════════════════════════════════════


class TestCosineSimilarity:

    def test_identical_vectors(self) -> None:
        v = np.array([1.0, 2.0, 3.0])
        assert _cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self) -> None:
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert _cosine_similarity(a, b) == pytest.approx(0.0)

    def test_zero_vector_returns_zero(self) -> None:
        a = np.array([0.0, 0.0])
        b = np.array([1.0, 2.0])
        assert _cosine_similarity(a, b) == 0.0

    def test_opposite_vectors(self) -> None:
        a = np.array([1.0, 0.0])
        b = np.array([-1.0, 0.0])
        assert _cosine_similarity(a, b) == pytest.approx(-1.0)


# ═══════════════════════════════════════════════════════════════════════════
# Convergence detection
# ═══════════════════════════════════════════════════════════════════════════


class TestConvergenceDetection:

    def test_missing_prev_vector_returns_continue(self) -> None:
        """Missing summary vectors -> action 'continue'."""
        engine = GovernanceEngine(_make_config())
        decision = engine.enforce(1, None, [1.0, 2.0])
        assert decision.action == "continue"
        assert "Missing" in decision.reason

    def test_missing_curr_vector_returns_continue(self) -> None:
        engine = GovernanceEngine(_make_config())
        decision = engine.enforce(1, [1.0, 2.0], None)
        assert decision.action == "continue"

    def test_both_vectors_none_returns_continue(self) -> None:
        engine = GovernanceEngine(_make_config())
        decision = engine.enforce(1, None, None)
        assert decision.action == "continue"

    def test_low_similarity_returns_continue(self) -> None:
        """Similarity below threshold -> continue, streak reset."""
        base = _unit_vec()
        other = _orthogonal_vec(base)
        engine = GovernanceEngine(_make_config(similarity_threshold=0.95))
        decision = engine.enforce(1, base, other)
        assert decision.action == "continue"
        assert "below" in decision.reason.lower() or "reset" in decision.reason.lower()

    def test_single_high_similarity_returns_intervene(self) -> None:
        """First high-similarity round -> intervene (streak=1, halt_after=2)."""
        base = _unit_vec()
        similar = _near_identical_vec(base, noise=0.0001)
        engine = GovernanceEngine(
            _make_config(similarity_threshold=0.95, rounds_before_force_halt=2)
        )
        decision = engine.enforce(1, base, similar)
        assert decision.action == "intervene"
        assert len(decision.recommendations) > 0

    def test_force_halt_after_streak(self) -> None:
        """Force halt fires after rounds_before_force_halt consecutive high-sim rounds."""
        base = _unit_vec()
        engine = GovernanceEngine(
            _make_config(similarity_threshold=0.95, rounds_before_force_halt=2)
        )

        # Round 1: high similarity -> intervene (streak=1)
        sim1 = _near_identical_vec(base, noise=0.0001, seed=10)
        d1 = engine.enforce(1, base, sim1)
        assert d1.action == "intervene"

        # Round 2: still high similarity -> force_halt (streak=2)
        sim2 = _near_identical_vec(base, noise=0.0001, seed=20)
        d2 = engine.enforce(2, sim1, sim2)
        assert d2.action == "force_halt"
        assert "convergence" in d2.reason.lower() or "consecutive" in d2.reason.lower()

    def test_force_halt_after_configurable_streak_3(self) -> None:
        """Force halt with rounds_before_force_halt=3 requires 3 consecutive rounds."""
        base = _unit_vec()
        engine = GovernanceEngine(
            _make_config(similarity_threshold=0.95, rounds_before_force_halt=3)
        )

        prev = base
        for i in range(2):
            curr = _near_identical_vec(prev, noise=0.0001, seed=100 + i)
            d = engine.enforce(i + 1, prev, curr)
            assert d.action == "intervene", f"Round {i + 1} should be intervene"
            prev = curr

        # Round 3: force_halt
        curr = _near_identical_vec(prev, noise=0.0001, seed=200)
        d3 = engine.enforce(3, prev, curr)
        assert d3.action == "force_halt"

    def test_streak_broken_by_low_similarity(self) -> None:
        """Similarity drop mid-streak resets the counter -- no force_halt."""
        base = _unit_vec()
        engine = GovernanceEngine(
            _make_config(similarity_threshold=0.95, rounds_before_force_halt=2)
        )

        # Round 1: high sim (streak=1)
        sim1 = _near_identical_vec(base, noise=0.0001, seed=10)
        d1 = engine.enforce(1, base, sim1)
        assert d1.action == "intervene"

        # Round 2: LOW similarity -- streak resets
        ortho = _orthogonal_vec(sim1)
        d2 = engine.enforce(2, sim1, ortho)
        assert d2.action == "continue"

        # Round 3: high sim again (streak=1, not 2)
        sim3 = _near_identical_vec(ortho, noise=0.0001, seed=30)
        d3 = engine.enforce(3, ortho, sim3)
        assert d3.action == "intervene"  # not force_halt

    def test_force_halt_has_recommendations(self) -> None:
        """force_halt decisions include non-empty recommendations."""
        base = _unit_vec()
        engine = GovernanceEngine(
            _make_config(similarity_threshold=0.95, rounds_before_force_halt=2)
        )
        sim1 = _near_identical_vec(base, noise=0.0001, seed=10)
        engine.enforce(1, base, sim1)
        sim2 = _near_identical_vec(sim1, noise=0.0001, seed=20)
        d = engine.enforce(2, sim1, sim2)
        assert d.action == "force_halt"
        assert len(d.recommendations) > 0
        assert all(isinstance(r, str) and len(r) > 0 for r in d.recommendations)

    def test_dimension_mismatch_returns_continue(self) -> None:
        """Mismatched vector dimensions -> continue."""
        engine = GovernanceEngine(_make_config())
        d = engine.enforce(1, [1.0, 2.0], [1.0, 2.0, 3.0])
        assert d.action == "continue"
        assert "mismatch" in d.reason.lower()


# ═══════════════════════════════════════════════════════════════════════════
# Path diversity
# ═══════════════════════════════════════════════════════════════════════════


class TestPathDiversity:

    def test_empty_history_returns_zero(self) -> None:
        engine = GovernanceEngine(_make_config())
        assert engine.path_diversity_score([]) == 0

    def test_single_approach_returns_one(self) -> None:
        history = [
            {"agent_outputs": {"a1": {"approach": "REST API"}}},
            {"agent_outputs": {"a2": {"approach": "rest api"}}},  # case-insensitive
        ]
        engine = GovernanceEngine(_make_config())
        assert engine.path_diversity_score(history) == 1

    def test_multiple_approaches_counted(self) -> None:
        history = [
            {"agent_outputs": {"a1": {"approach": "REST API"}}},
            {"agent_outputs": {"a2": {"approach": "GraphQL"}}},
            {"agent_outputs": {"a3": {"approach": "gRPC"}}},
        ]
        engine = GovernanceEngine(_make_config())
        assert engine.path_diversity_score(history) == 3

    def test_window_limits_recent_rounds(self) -> None:
        """Only the last `window` rounds should be considered."""
        # 6 rounds, window=3 -> only last 3 count
        history = [
            {"agent_outputs": {"a": {"approach": "old_approach_1"}}},
            {"agent_outputs": {"a": {"approach": "old_approach_2"}}},
            {"agent_outputs": {"a": {"approach": "old_approach_3"}}},
            {"agent_outputs": {"a": {"approach": "new_A"}}},
            {"agent_outputs": {"a": {"approach": "new_B"}}},
            {"agent_outputs": {"a": {"approach": "new_A"}}},  # duplicate
        ]
        engine = GovernanceEngine(_make_config())
        score = engine.path_diversity_score(history, window=3)
        assert score == 2  # new_A and new_B

    def test_flat_approach_format(self) -> None:
        """Entries with a flat 'approach' key (no agent_outputs nesting)."""
        history = [
            {"approach": "Alpha"},
            {"approach": "Beta"},
        ]
        engine = GovernanceEngine(_make_config())
        assert engine.path_diversity_score(history) == 2

    def test_mixed_formats(self) -> None:
        """Mix of nested agent_outputs and flat approach entries."""
        history = [
            {"agent_outputs": {"a1": {"approach": "REST"}}, "approach": "REST"},
            {"approach": "GraphQL"},
        ]
        engine = GovernanceEngine(_make_config())
        assert engine.path_diversity_score(history) == 2

    def test_no_approach_keys_returns_zero(self) -> None:
        history = [
            {"agent_outputs": {"a1": {"result": "ok"}}},
            {"agent_outputs": {"a2": {"result": "fail"}}},
        ]
        engine = GovernanceEngine(_make_config())
        assert engine.path_diversity_score(history) == 0

    def test_invalid_history_type_returns_zero(self) -> None:
        engine = GovernanceEngine(_make_config())
        assert engine.path_diversity_score("not a list") == 0  # type: ignore[arg-type]

    def test_strips_whitespace(self) -> None:
        history = [
            {"approach": "  REST API  "},
            {"approach": "rest api"},
        ]
        engine = GovernanceEngine(_make_config())
        assert engine.path_diversity_score(history) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Tunnel vision detection
# ═══════════════════════════════════════════════════════════════════════════


class TestTunnelVision:

    def test_no_tunnel_vision_with_diverse_approaches(self) -> None:
        engine = GovernanceEngine(_make_config())
        history = [
            {"approach": "A"},
            {"approach": "B"},
        ]
        result = engine.check_tunnel_vision(history, round_num=2)
        assert result is None

    def test_tunnel_vision_after_two_consecutive_single_approach_checks(self) -> None:
        engine = GovernanceEngine(_make_config())
        history = [{"approach": "REST"}]

        # Check 1: diversity=1, streak=1 -> not yet triggered
        r1 = engine.check_tunnel_vision(history, round_num=1)
        assert r1 is None

        # Check 2: diversity still 1, streak=2 -> warn
        r2 = engine.check_tunnel_vision(history, round_num=2)
        assert r2 is not None
        assert r2.action == "warn_tunnel_vision"
        assert len(r2.recommendations) > 0

    def test_tunnel_vision_streak_resets_on_diversity(self) -> None:
        engine = GovernanceEngine(_make_config())

        # Check 1: single approach
        engine.check_tunnel_vision([{"approach": "REST"}], round_num=1)

        # Check 2: diversity > 1 -> streak resets
        engine.check_tunnel_vision(
            [{"approach": "REST"}, {"approach": "GraphQL"}], round_num=2
        )

        # Check 3: single approach again -> streak=1, no warning yet
        r3 = engine.check_tunnel_vision([{"approach": "REST"}], round_num=3)
        assert r3 is None


# ═══════════════════════════════════════════════════════════════════════════
# Stall detection
# ═══════════════════════════════════════════════════════════════════════════


class TestStallDetection:

    def _make_failure_tuples(
        self,
        subject: str = "auth_module",
        predicate: str = "Failed_Test",
        count: int = 3,
        team_id: str | None = None,
    ) -> list[TKGTuple]:
        return [
            TKGTuple(
                subject=subject,
                predicate=predicate,
                object_=f"failure_{i}",
                round_num=i,
                team_id=team_id,
            )
            for i in range(count)
        ]

    def test_stall_detected_at_threshold(self) -> None:
        """Stall fires when occurrences >= stall_repeat_threshold."""
        engine = GovernanceEngine(_make_config(stall_repeat_threshold=3))
        tuples = self._make_failure_tuples(count=3)
        reports = engine.detect_stalls(tuples, round_num=3)
        assert len(reports) == 1
        assert reports[0].subject == "auth_module"
        assert reports[0].predicate == "Failed_Test"
        assert reports[0].occurrences == 3

    def test_no_stall_below_threshold(self) -> None:
        """Below threshold -> no stall report."""
        engine = GovernanceEngine(_make_config(stall_repeat_threshold=3))
        tuples = self._make_failure_tuples(count=2)
        reports = engine.detect_stalls(tuples, round_num=2)
        assert len(reports) == 0

    def test_stall_scoped_by_team_id(self) -> None:
        """team_id filter limits stall detection to that team."""
        engine = GovernanceEngine(_make_config(stall_repeat_threshold=2))

        team_a_tuples = self._make_failure_tuples(count=3, team_id="team_a")
        team_b_tuples = self._make_failure_tuples(
            subject="db_module", count=3, team_id="team_b"
        )
        all_tuples = team_a_tuples + team_b_tuples

        # Scope to team_a: should only see auth_module failures
        reports_a = engine.detect_stalls(all_tuples, round_num=3, team_id="team_a")
        assert len(reports_a) == 1
        assert reports_a[0].subject == "auth_module"
        assert reports_a[0].team_id == "team_a"

        # Scope to team_b: should only see db_module failures
        reports_b = engine.detect_stalls(all_tuples, round_num=3, team_id="team_b")
        assert len(reports_b) == 1
        assert reports_b[0].subject == "db_module"
        assert reports_b[0].team_id == "team_b"

    def test_stall_ignores_non_failure_predicates(self) -> None:
        """Non-failure predicates are not counted."""
        engine = GovernanceEngine(_make_config(stall_repeat_threshold=2))
        tuples = [
            TKGTuple(
                subject="auth_module",
                predicate="Passed_Test",
                object_="ok",
                round_num=i,
            )
            for i in range(5)
        ]
        reports = engine.detect_stalls(tuples, round_num=5)
        assert len(reports) == 0

    def test_stall_with_error_predicate(self) -> None:
        """'Error' predicate also triggers stall detection."""
        engine = GovernanceEngine(_make_config(stall_repeat_threshold=2))
        tuples = self._make_failure_tuples(predicate="Error", count=3)
        reports = engine.detect_stalls(tuples, round_num=3)
        assert len(reports) == 1
        assert reports[0].predicate == "Error"

    def test_stall_multiple_subjects(self) -> None:
        """Multiple distinct subjects each crossing threshold."""
        engine = GovernanceEngine(_make_config(stall_repeat_threshold=2))
        tuples = (
            self._make_failure_tuples(subject="mod_a", count=2)
            + self._make_failure_tuples(subject="mod_b", count=3)
        )
        reports = engine.detect_stalls(tuples, round_num=3)
        assert len(reports) == 2
        subjects = {r.subject for r in reports}
        assert subjects == {"mod_a", "mod_b"}

    def test_stall_with_dict_tuples(self) -> None:
        """detect_stalls accepts plain dicts as well as TKGTuple objects."""
        engine = GovernanceEngine(_make_config(stall_repeat_threshold=2))
        tuples = [
            {
                "subject": "api",
                "predicate": "Failed_Test",
                "object_": "err",
                "round_num": i,
                "team_id": None,
            }
            for i in range(3)
        ]
        reports = engine.detect_stalls(tuples, round_num=3)
        assert len(reports) == 1
        assert reports[0].subject == "api"

    def test_stall_round_nums_sorted(self) -> None:
        """StallReport.round_nums should be sorted."""
        engine = GovernanceEngine(_make_config(stall_repeat_threshold=2))
        tuples = [
            TKGTuple(subject="x", predicate="Error", object_="e", round_num=5),
            TKGTuple(subject="x", predicate="Error", object_="e", round_num=2),
            TKGTuple(subject="x", predicate="Error", object_="e", round_num=8),
        ]
        reports = engine.detect_stalls(tuples, round_num=8)
        assert reports[0].round_nums == [2, 5, 8]

    def test_stall_no_team_filter_returns_all(self) -> None:
        """Without team_id filter, all tuples are scanned."""
        engine = GovernanceEngine(_make_config(stall_repeat_threshold=2))
        tuples = (
            self._make_failure_tuples(subject="a", count=2, team_id="t1")
            + self._make_failure_tuples(subject="a", count=2, team_id="t2")
        )
        # No team filter -> all 4 failures for subject "a" are counted together
        reports = engine.detect_stalls(tuples, round_num=3, team_id=None)
        assert len(reports) == 1
        assert reports[0].occurrences == 4


# ═══════════════════════════════════════════════════════════════════════════
# Intervene recommendations
# ═══════════════════════════════════════════════════════════════════════════


class TestInterventionRecommendations:

    def test_intervene_has_non_empty_recommendations(self) -> None:
        """When action is 'intervene', recommendations must be non-empty strings."""
        base = _unit_vec()
        sim = _near_identical_vec(base, noise=0.0001)
        engine = GovernanceEngine(
            _make_config(similarity_threshold=0.95, rounds_before_force_halt=3)
        )
        d = engine.enforce(1, base, sim)
        assert d.action == "intervene"
        assert len(d.recommendations) > 0
        for rec in d.recommendations:
            assert isinstance(rec, str)
            assert len(rec.strip()) > 0

    def test_tunnel_vision_has_recommendations(self) -> None:
        engine = GovernanceEngine(_make_config())
        history = [{"approach": "only_one"}]
        engine.check_tunnel_vision(history, round_num=1)
        r = engine.check_tunnel_vision(history, round_num=2)
        assert r is not None
        assert len(r.recommendations) > 0
        for rec in r.recommendations:
            assert isinstance(rec, str)
            assert len(rec.strip()) > 0


# ═══════════════════════════════════════════════════════════════════════════
# Config acceptance
# ═══════════════════════════════════════════════════════════════════════════


class TestConfigAcceptance:

    def test_dict_config(self) -> None:
        """GovernanceEngine accepts a plain dict config."""
        cfg = {
            "convergence": ConvergenceConfig(similarity_threshold=0.90),
            "temporal": TemporalConfig(stall_repeat_threshold=5),
        }
        engine = GovernanceEngine(cfg)
        assert engine._conv.similarity_threshold == 0.90
        assert engine._temp.stall_repeat_threshold == 5

    def test_defaults_when_keys_missing(self) -> None:
        """Missing config keys fall back to defaults."""
        engine = GovernanceEngine({})
        assert engine._conv.similarity_threshold == 0.95
        assert engine._temp.stall_repeat_threshold == 3

    def test_object_config(self) -> None:
        """GovernanceEngine accepts an object with attributes."""
        cfg = _make_config(similarity_threshold=0.80, stall_repeat_threshold=10)
        engine = GovernanceEngine(cfg)
        assert engine._conv.similarity_threshold == 0.80
        assert engine._temp.stall_repeat_threshold == 10
