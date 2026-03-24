"""Scoring invariant tests for knowledge catalog (Wave 32 A3, ADR-041 D3).

Validates structural properties of the composite scoring function,
not frozen numerical values. All signals should be in [0,1].
"""

from __future__ import annotations

from formicos.surface.knowledge_catalog import _composite_key, _STATUS_BONUS


def _make_item(
    *,
    score: float = 0.5,
    conf_alpha: float = 5.0,
    conf_beta: float = 5.0,
    created_at: str = "2026-01-01T00:00:00+00:00",
    status: str = "active",
    thread_bonus: float = 0.0,
) -> dict[str, object]:
    return {
        "score": score,
        "conf_alpha": conf_alpha,
        "conf_beta": conf_beta,
        "created_at": created_at,
        "status": status,
        "_thread_bonus": thread_bonus,
    }


class TestScoringInvariant1:
    """At equal semantic and freshness, verified outranks stale."""

    def test_verified_outranks_stale(self) -> None:
        verified = _make_item(status="verified")
        stale = _make_item(status="stale")
        # Run many times to account for Thompson Sampling randomness
        verified_wins = 0
        trials = 200
        for _ in range(trials):
            if _composite_key(verified) < _composite_key(stale):  # negative for sort
                verified_wins += 1
        # Verified should win most of the time (status bonus difference is large)
        assert verified_wins > trials * 0.7, (
            f"Verified only won {verified_wins}/{trials} times"
        )


class TestScoringInvariant2:
    """At equal everything else, thread-matched outranks non-matched."""

    def test_thread_matched_outranks(self) -> None:
        matched = _make_item(thread_bonus=1.0)
        unmatched = _make_item(thread_bonus=0.0)
        matched_wins = 0
        trials = 200
        for _ in range(trials):
            if _composite_key(matched) < _composite_key(unmatched):
                matched_wins += 1
        assert matched_wins > trials * 0.7, (
            f"Thread-matched only won {matched_wins}/{trials} times"
        )


class TestScoringInvariant3:
    """Thompson Sampling produces different rankings on successive calls."""

    def test_thompson_exploration(self) -> None:
        items = [
            _make_item(conf_alpha=5.0, conf_beta=5.0),
            _make_item(conf_alpha=5.0, conf_beta=5.0),
        ]
        scores = set()
        for _ in range(50):
            s = _composite_key(items[0])
            scores.add(round(s, 6))
        # With Beta(5,5), Thompson samples should vary
        assert len(scores) > 1, "Thompson Sampling produced identical scores"


class TestScoringInvariant4:
    """Very old entry can rank highly if verified and semantically relevant."""

    def test_old_verified_relevant_ranks_high(self) -> None:
        # Old entry (low freshness) but verified + high semantic
        old_verified = _make_item(
            score=0.95,
            status="verified",
            conf_alpha=15.0,
            conf_beta=3.0,
            created_at="2024-01-01T00:00:00+00:00",
        )
        # Recent entry, stale, low semantic
        recent_stale = _make_item(
            score=0.3,
            status="stale",
            conf_alpha=3.0,
            conf_beta=15.0,
            created_at="2026-03-01T00:00:00+00:00",
        )
        old_wins = 0
        trials = 200
        for _ in range(trials):
            if _composite_key(old_verified) < _composite_key(recent_stale):
                old_wins += 1
        assert old_wins > trials * 0.8, (
            f"Old verified entry only won {old_wins}/{trials} — freshness dominates"
        )


class TestStatusBonusNormalized:
    """All status bonus values should be in [0, 1]."""

    def test_all_values_in_unit_range(self) -> None:
        for status, bonus in _STATUS_BONUS.items():
            assert 0.0 <= bonus <= 1.0, (
                f"Status '{status}' bonus {bonus} outside [0, 1]"
            )

    def test_verified_is_max(self) -> None:
        assert _STATUS_BONUS["verified"] == 1.0

    def test_stale_is_min(self) -> None:
        assert _STATUS_BONUS["stale"] == 0.0
