"""Wave 41 A1: Continuous Beta trust weighting tests."""

from __future__ import annotations

import pytest

from formicos.surface.trust import (
    entry_confidence_score,
    federated_retrieval_penalty,
    trust_discount,
)


class TestEntryConfidenceScore:
    """Tests for live posterior confidence scoring."""

    def test_high_confidence_entry(self) -> None:
        """Entry with high alpha, low beta should score high."""
        entry = {"conf_alpha": 30.0, "conf_beta": 3.0}
        score = entry_confidence_score(entry)
        assert score > 0.7

    def test_low_confidence_entry(self) -> None:
        """Entry with low alpha, high beta should score low."""
        entry = {"conf_alpha": 3.0, "conf_beta": 30.0}
        score = entry_confidence_score(entry)
        assert score < 0.2

    def test_balanced_entry(self) -> None:
        """Entry with balanced alpha/beta should score near 0.5."""
        entry = {"conf_alpha": 10.0, "conf_beta": 10.0}
        score = entry_confidence_score(entry)
        assert 0.3 < score < 0.6

    def test_missing_params_returns_conservative(self) -> None:
        """Entry without Beta params defaults to conservative 0.4."""
        assert entry_confidence_score({}) == 0.4
        assert entry_confidence_score({"conf_alpha": 0}) == 0.4

    def test_returns_bounded_zero_to_one(self) -> None:
        """Score is always in [0, 1]."""
        for a, b in [(1, 1), (100, 1), (1, 100), (50, 50)]:
            score = entry_confidence_score({"conf_alpha": a, "conf_beta": b})
            assert 0.0 <= score <= 1.0


class TestFederatedRetrievalPenalty:
    """Tests for posterior-aware federated retrieval penalty."""

    def test_local_entry_no_penalty(self) -> None:
        """Local entries always get 1.0 (no penalty)."""
        entry = {"source_peer": "", "conf_alpha": 5.0, "conf_beta": 5.0}
        assert federated_retrieval_penalty(entry) == 1.0

    def test_federated_verified_high_confidence(self) -> None:
        """High-confidence verified federated entry gets mild penalty."""
        entry = {
            "source_peer": "peer-1",
            "status": "verified",
            "conf_alpha": 30.0,
            "conf_beta": 3.0,
        }
        penalty = federated_retrieval_penalty(entry)
        assert 0.7 < penalty <= 0.9

    def test_federated_candidate_low_confidence(self) -> None:
        """Low-confidence candidate federated entry gets heavy penalty."""
        entry = {
            "source_peer": "peer-1",
            "status": "candidate",
            "conf_alpha": 2.0,
            "conf_beta": 10.0,
        }
        penalty = federated_retrieval_penalty(entry)
        assert penalty < 0.4

    def test_verified_beats_candidate(self) -> None:
        """Same confidence params, but verified status should score higher."""
        base = {"source_peer": "peer-1", "conf_alpha": 10.0, "conf_beta": 5.0}
        verified = {**base, "status": "verified"}
        candidate = {**base, "status": "candidate"}
        assert federated_retrieval_penalty(verified) > federated_retrieval_penalty(candidate)

    def test_penalty_bounded(self) -> None:
        """Penalty never goes below 0.1 or above 0.9."""
        extremes = [
            {"source_peer": "p", "status": "verified", "conf_alpha": 100, "conf_beta": 1},
            {"source_peer": "p", "status": "stale", "conf_alpha": 1, "conf_beta": 100},
        ]
        for entry in extremes:
            p = federated_retrieval_penalty(entry)
            assert 0.1 <= p <= 0.9

    def test_hop_discount_applied_for_multihop(self) -> None:
        """Multi-hop entries get additional penalty via trust_discount."""
        zero_hop = {
            "source_peer": "peer-1",
            "status": "active",
            "conf_alpha": 10.0,
            "conf_beta": 5.0,
            "federation_hop": 0,
        }
        two_hop = {**zero_hop, "federation_hop": 2}
        # Multi-hop should be penalized more
        assert federated_retrieval_penalty(two_hop) <= federated_retrieval_penalty(zero_hop)

    def test_peer_trust_score_used_when_provided(self) -> None:
        """Explicit peer_trust_score overrides using entry posterior as proxy."""
        entry = {
            "source_peer": "peer-1",
            "status": "verified",
            "conf_alpha": 30.0,
            "conf_beta": 3.0,
            "federation_hop": 1,
        }
        # High peer trust → milder penalty
        high_trust = federated_retrieval_penalty(entry, peer_trust_score=0.9)
        # Low peer trust → harsher penalty
        low_trust = federated_retrieval_penalty(entry, peer_trust_score=0.2)
        assert high_trust > low_trust

    def test_trust_discount_live_in_retrieval_path(self) -> None:
        """Verify trust_discount is exercised by federated_retrieval_penalty.

        This test ensures the A1 bridge is complete: trust_discount is
        not dead code but is actually called by the retrieval path.
        """
        entry = {
            "source_peer": "peer-1",
            "status": "active",
            "conf_alpha": 10.0,
            "conf_beta": 5.0,
            "federation_hop": 3,
        }
        penalty = federated_retrieval_penalty(entry)
        # 3-hop entry should be significantly penalized
        assert penalty < 0.5
        assert 0.1 <= penalty <= 0.9


class TestTrustDiscount:
    """Tests for posterior-aware hop discounting."""

    def test_zero_hops(self) -> None:
        """With zero hops, discount = min(trust_score, 0.5)."""
        assert trust_discount(0.8, hop=0) == 0.5  # capped
        assert trust_discount(0.3, hop=0) == 0.3

    def test_high_trust_decays_slower(self) -> None:
        """High-trust peers decay less per hop than low-trust peers."""
        high_trust_2hop = trust_discount(0.9, hop=2)
        low_trust_2hop = trust_discount(0.3, hop=2)
        # High trust at 2 hops should retain more than low trust
        assert high_trust_2hop > low_trust_2hop

    def test_cap_at_half(self) -> None:
        """Even perfect trust is capped at 0.5."""
        assert trust_discount(1.0, hop=0) == 0.5

    def test_multi_hop_decreases(self) -> None:
        """More hops = lower discount."""
        ts = 0.8
        assert trust_discount(ts, hop=0) >= trust_discount(ts, hop=1)
        assert trust_discount(ts, hop=1) >= trust_discount(ts, hop=2)
