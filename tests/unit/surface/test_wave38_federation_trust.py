"""Federation trust hardening tests (Wave 38, Pillar 3B).

Validates that:
- asymmetric failure penalties make trust harder to earn
- trust discount is steeper with hop decay
- federated retrieval penalty prevents weak foreign dominance
- local verified entries outrank weak federated entries
"""

from __future__ import annotations

import pytest

from formicos.surface.trust import (
    PeerTrust,
    federated_retrieval_penalty,
    trust_discount,
)


class TestAsymmetricPenalties:
    """Failures count more than successes (Wave 38 hardening)."""

    def test_failure_adds_double_beta(self) -> None:
        """record_failure increments beta by 2.0, not 1.0."""
        trust = PeerTrust(alpha=5.0, beta=2.0)
        trust.record_failure()
        assert trust.beta == 4.0  # 2.0 + 2.0

    def test_success_adds_single_alpha(self) -> None:
        """record_success still increments alpha by 1.0."""
        trust = PeerTrust(alpha=5.0, beta=2.0)
        trust.record_success()
        assert trust.alpha == 6.0

    def test_asymmetry_makes_recovery_slower(self) -> None:
        """After one failure, one success doesn't restore original trust."""
        trust = PeerTrust(alpha=10.0, beta=2.0)
        original_score = trust.score
        trust.record_failure()
        trust.record_success()
        # Should still be lower than original despite balanced events
        assert trust.score < original_score

    def test_single_failure_tanks_trust_from_moderate(self) -> None:
        """A single failure from moderate trust significantly drops score.

        With asymmetric penalties (failure=+2 beta), a single failure
        from a peer with moderate observations should be clearly visible.
        """
        trust = PeerTrust(alpha=10.0, beta=3.0)
        before = trust.score
        trust.record_failure()
        after = trust.score
        # Beta went from 3 to 5, which should drop score noticeably
        assert after < before
        # The drop should be significant (more than symmetric would cause)
        assert before - after > 0.05


class TestTrustDiscount:
    """Trust discount with Wave 41 A1 posterior-aware hop decay."""

    def test_zero_hop_capped_at_half(self) -> None:
        """Even with perfect trust, federated entries cap at 0.5 weight."""
        discount = trust_discount(1.0, hop=0)
        assert discount == 0.5

    def test_one_hop_high_trust_capped(self) -> None:
        """High-trust at 1 hop still capped by the 0.5 ceiling."""
        discount = trust_discount(1.0, hop=1)
        assert discount == pytest.approx(0.5, abs=0.01)

    def test_two_hops_below_cap(self) -> None:
        """Two-hop entries get discounted. High trust decays slower."""
        discount = trust_discount(1.0, hop=2)
        # With trust=1.0, hop_base=0.85, 1.0*0.85^2=0.7225, capped at 0.5
        assert discount == pytest.approx(0.5, abs=0.01)
        # With moderate trust, discount drops below cap
        discount_moderate = trust_discount(0.4, hop=2)
        assert discount_moderate < 0.5

    def test_low_trust_low_discount(self) -> None:
        """Low-trust peers get very low discount."""
        discount = trust_discount(0.3, hop=0)
        assert discount == pytest.approx(0.3, abs=0.01)

    def test_never_exceeds_half(self) -> None:
        """Discount never exceeds 0.5 regardless of trust score."""
        for trust_score in [0.5, 0.8, 0.9, 0.95, 1.0]:
            assert trust_discount(trust_score) <= 0.5


class TestFederatedRetrievalPenalty:
    """Federated entries are penalized during retrieval."""

    def test_local_entry_no_penalty(self) -> None:
        """Local entries get multiplier of 1.0 (no penalty)."""
        entry = {"id": "e1", "status": "verified"}
        assert federated_retrieval_penalty(entry) == 1.0

    def test_federated_verified_mild_penalty(self) -> None:
        """Federated verified entries get mild penalty.

        Wave 41 A1: penalty is posterior-aware. Verified status floor (0.80)
        combined with default posterior gives a penalty in the 0.6-0.9 range.
        """
        entry = {"id": "e1", "status": "verified", "source_peer": "peer-1"}
        penalty = federated_retrieval_penalty(entry)
        assert 0.4 < penalty < 0.9

    def test_federated_active_moderate_penalty(self) -> None:
        """Federated active entries get moderate penalty.

        Wave 41 A1: posterior-aware. Active floor (0.55) blended with posterior.
        """
        entry = {"id": "e1", "status": "active", "source_peer": "peer-1"}
        penalty = federated_retrieval_penalty(entry)
        assert 0.3 < penalty < 0.8

    def test_federated_candidate_heavy_penalty(self) -> None:
        """Federated candidate entries get heavy penalty.

        Wave 41 A1: posterior-aware. Candidate floor (0.35) blended with posterior.
        """
        entry = {"id": "e1", "status": "candidate", "source_peer": "peer-1"}
        penalty = federated_retrieval_penalty(entry)
        assert 0.1 < penalty < 0.7


class TestLocalVerifiedDominance:
    """Local verified entries outrank weak federated entries."""

    def test_local_verified_beats_federated_candidate(self) -> None:
        """A local verified entry should score higher than a federated candidate.

        Even if the federated entry has equal semantic score, the retrieval
        penalty ensures the local entry dominates.
        """
        local_entry = {"id": "local-1", "status": "verified"}
        fed_entry = {"id": "fed-1", "status": "candidate", "source_peer": "peer-1"}

        local_penalty = federated_retrieval_penalty(local_entry)
        fed_penalty = federated_retrieval_penalty(fed_entry)

        # Local entry composite gets full weight, federated gets 45%
        assert local_penalty > fed_penalty
        assert local_penalty / fed_penalty > 2.0  # More than 2x advantage

    def test_high_trust_federated_verified_still_discounted(self) -> None:
        """Even verified federated entries don't match local entries."""
        local_entry = {"id": "local-1", "status": "verified"}
        fed_entry = {"id": "fed-1", "status": "verified", "source_peer": "peer-trusted"}

        assert federated_retrieval_penalty(local_entry) > federated_retrieval_penalty(fed_entry)


class TestTrustDecay:
    """Trust decay works correctly."""

    def test_decay_reduces_trust(self) -> None:
        """Trust decays over time."""
        trust = PeerTrust(alpha=20.0, beta=3.0)
        original_score = trust.score
        trust.decay(days=90)
        assert trust.score < original_score

    def test_decay_preserves_minimum(self) -> None:
        """Trust never decays below the prior (alpha=1, beta=1)."""
        trust = PeerTrust(alpha=2.0, beta=1.0)
        trust.decay(days=10000)
        assert trust.alpha >= 1.0
        assert trust.beta >= 1.0
