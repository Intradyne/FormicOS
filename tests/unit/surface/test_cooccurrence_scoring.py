"""Tests for co-occurrence scoring activation (Wave 34 A3, ADR-044)."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

from formicos.surface.knowledge_catalog import (
    _composite_key,
    _cooccurrence_score,
    _sigmoid_cooccurrence,
)
from formicos.surface.knowledge_constants import COMPOSITE_WEIGHTS

# ---------------------------------------------------------------------------
# Sigmoid normalization tests (ADR-044 D1)
# ---------------------------------------------------------------------------


class TestSigmoidCooccurrence:
    def test_zero_returns_zero(self) -> None:
        assert _sigmoid_cooccurrence(0.0) == 0.0

    def test_negative_returns_zero(self) -> None:
        assert _sigmoid_cooccurrence(-1.0) == 0.0

    def test_raw_1_approx_045(self) -> None:
        result = _sigmoid_cooccurrence(1.0)
        assert abs(result - (1.0 - math.exp(-0.6))) < 0.01
        assert 0.44 < result < 0.46

    def test_raw_3_approx_083(self) -> None:
        result = _sigmoid_cooccurrence(3.0)
        assert 0.82 < result < 0.84

    def test_raw_5_approx_095(self) -> None:
        result = _sigmoid_cooccurrence(5.0)
        assert 0.94 < result < 0.96

    def test_raw_10_approx_1(self) -> None:
        result = _sigmoid_cooccurrence(10.0)
        assert result > 0.99

    def test_monotonically_increasing(self) -> None:
        values = [0.0, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0]
        results = [_sigmoid_cooccurrence(v) for v in values]
        for i in range(1, len(results)):
            assert results[i] > results[i - 1]


# ---------------------------------------------------------------------------
# Co-occurrence score helper tests
# ---------------------------------------------------------------------------


@dataclass
class _FakeCoEntry:
    weight: float = 1.0


class TestCooccurrenceScore:
    def _make_projections(
        self, weights: dict[tuple[str, str], float],
    ) -> Any:
        proj = MagicMock()
        proj.cooccurrence_weights = {
            k: _FakeCoEntry(weight=v) for k, v in weights.items()
        }
        return proj

    def test_no_projections_returns_zero(self) -> None:
        assert _cooccurrence_score("a", ["b", "c"], None) == 0.0

    def test_no_cooccurrence_data_returns_zero(self) -> None:
        proj = self._make_projections({})
        assert _cooccurrence_score("a", ["b"], proj) == 0.0

    def test_returns_max_sigmoid_weight(self) -> None:
        proj = self._make_projections({
            ("a", "b"): 2.0,
            ("a", "c"): 5.0,
        })
        result = _cooccurrence_score("a", ["b", "c"], proj)
        expected = _sigmoid_cooccurrence(5.0)
        assert abs(result - expected) < 0.001

    def test_empty_other_ids_returns_zero(self) -> None:
        proj = self._make_projections({("a", "b"): 3.0})
        assert _cooccurrence_score("a", [], proj) == 0.0


# ---------------------------------------------------------------------------
# Composite weights sanity
# ---------------------------------------------------------------------------


class TestCompositeWeights:
    def test_weights_sum_to_one(self) -> None:
        total = sum(COMPOSITE_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9

    def test_seven_signals(self) -> None:
        expected = {
            "semantic", "thompson", "freshness", "status",
            "thread", "cooccurrence", "graph_proximity",
        }
        assert set(COMPOSITE_WEIGHTS.keys()) == expected

    def test_semantic_dominant(self) -> None:
        assert COMPOSITE_WEIGHTS["semantic"] > COMPOSITE_WEIGHTS["thompson"]

    def test_thompson_unchanged(self) -> None:
        assert COMPOSITE_WEIGHTS["thompson"] == 0.25

    def test_cooccurrence_at_004(self) -> None:
        assert COMPOSITE_WEIGHTS["cooccurrence"] == 0.04


# ---------------------------------------------------------------------------
# ADR-044 D3: Six validation invariants
# ---------------------------------------------------------------------------


def _make_item(
    *,
    item_id: str = "e1",
    score: float = 0.7,
    conf_alpha: float = 15.0,
    conf_beta: float = 5.0,
    status: str = "active",
    created_at: str = "2026-03-18T00:00:00+00:00",
    thread_bonus: float = 0.0,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "score": score,
        "conf_alpha": conf_alpha,
        "conf_beta": conf_beta,
        "status": status,
        "created_at": created_at,
        "_thread_bonus": thread_bonus,
    }


class TestScoringInvariantsADR044:
    """ADR-044 D3: 6 invariants for the rebalanced composite weights."""

    def test_invariant_1_verified_outranks_stale(self) -> None:
        """Equal semantic + freshness → verified outranks stale."""
        verified = _make_item(status="verified")
        stale = _make_item(status="stale")
        # Run many times to overcome Thompson noise
        verified_wins = 0
        for _ in range(200):
            v_score = -_composite_key(verified)
            s_score = -_composite_key(stale)
            if v_score > s_score:
                verified_wins += 1
        # Status weight 0.10 * (1.0 - 0.0) = 0.10 advantage
        assert verified_wins > 150, f"Verified won {verified_wins}/200"

    def test_invariant_2_thread_matched_outranks_non_matched(self) -> None:
        """Equal everything → thread-matched outranks non-matched."""
        matched = _make_item(thread_bonus=1.0)
        unmatched = _make_item(thread_bonus=0.0)
        matched_wins = 0
        for _ in range(200):
            m_score = -_composite_key(matched)
            u_score = -_composite_key(unmatched)
            if m_score > u_score:
                matched_wins += 1
        # Thread weight 0.07 advantage
        assert matched_wins > 130, f"Matched won {matched_wins}/200"

    def test_invariant_3_thompson_produces_variation(self) -> None:
        """Thompson produces different rankings on successive calls."""
        item = _make_item()
        scores = {_composite_key(item) for _ in range(50)}
        assert len(scores) > 1, "Thompson should produce variation"

    def test_invariant_4_old_verified_can_rank_highly(self) -> None:
        """Very old entry (freshness≈0) can rank if verified + relevant."""
        old_verified = _make_item(
            score=0.9, status="verified",
            created_at="2020-01-01T00:00:00+00:00",
        )
        new_candidate = _make_item(
            score=0.3, status="candidate",
            created_at="2026-03-18T00:00:00+00:00",
        )
        old_wins = 0
        for _ in range(200):
            o_score = -_composite_key(old_verified)
            n_score = -_composite_key(new_candidate)
            if o_score > n_score:
                old_wins += 1
        # semantic(0.38*0.9=0.342) + status(0.10*1.0=0.10) vs
        # semantic(0.38*0.3=0.114) + freshness(0.10*1.0=0.10)
        assert old_wins > 100, f"Old verified won {old_wins}/200"

    def test_invariant_5_coaccessed_scores_higher(self) -> None:
        """Co-accessed entries score higher than identical without co-occurrence."""
        # This tests the cooccurrence_score helper directly since
        # _composite_key (non-closure form) doesn't include co-occurrence.
        # The closure version in _search_thread_boosted is tested via
        # integration tests. Here we verify the signal value.
        raw_weight = 5.0
        cooc_contribution = (
            COMPOSITE_WEIGHTS["cooccurrence"] * _sigmoid_cooccurrence(raw_weight)
        )
        assert cooc_contribution > 0.03  # ~0.04 * 0.95 ≈ 0.038

    def test_invariant_6_no_cluster_dominance(self) -> None:
        """No single cluster takes all top-5 >30% of 100 random queries.

        Property-based test: create 3 clusters of items and verify
        no single cluster takes all 5 slots more than 30% of the time.
        """
        random.seed(42)
        cluster_a = [_make_item(item_id=f"a{i}", score=0.7) for i in range(5)]
        cluster_b = [_make_item(item_id=f"b{i}", score=0.7) for i in range(5)]
        cluster_c = [_make_item(item_id=f"c{i}", score=0.7) for i in range(5)]
        all_items = cluster_a + cluster_b + cluster_c

        domination_count = 0
        for _ in range(100):
            scored = [(item, -_composite_key(item)) for item in all_items]
            scored.sort(key=lambda x: -x[1])
            top5 = scored[:5]
            # Check if all top-5 share the same cluster prefix
            prefixes = {item["id"][0] for item, _ in top5}
            if len(prefixes) == 1:
                domination_count += 1

        assert domination_count <= 30, (
            f"Single cluster dominated {domination_count}/100 times"
        )
