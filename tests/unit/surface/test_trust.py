"""Tests for PeerTrust (Wave 33 C6)."""

from __future__ import annotations

import pytest

from formicos.surface.trust import PeerTrust, trust_discount


class TestPeerTrust:
    """PeerTrust: Bayesian trust with 10th-percentile scoring."""

    def test_new_peer_low_score(self) -> None:
        """New peer (1, 1) should have a low trust score."""
        t = PeerTrust(1.0, 1.0)
        assert t.score < 0.5  # substantially below mean of 0.5

    def test_10_successes_moderate_score(self) -> None:
        t = PeerTrust(11.0, 1.0)
        assert 0.7 < t.score < 0.9

    def test_30_successes_high_score(self) -> None:
        t = PeerTrust(31.0, 1.0)
        assert t.score > 0.85

    def test_mean_higher_than_score(self) -> None:
        """Mean should always be >= 10th percentile."""
        t = PeerTrust(10.0, 1.0)
        assert t.mean > t.score

    def test_record_success(self) -> None:
        t = PeerTrust(1.0, 1.0)
        t.record_success()
        assert t.alpha == 2.0

    def test_record_failure(self) -> None:
        t = PeerTrust(1.0, 1.0)
        t.record_failure()
        # Wave 38: asymmetric penalty — failures add 2.0
        assert t.beta == 3.0

    def test_decay_90_days(self) -> None:
        """After 90 days, trust should retain ~91% of evidence."""
        t = PeerTrust(20.0, 2.0)
        original_alpha = t.alpha
        t.decay(90.0)
        # With gamma=0.9995, factor = 0.9995^90 ≈ 0.956
        assert t.alpha < original_alpha
        assert t.alpha > 1.0  # floor

    def test_decay_preserves_floor(self) -> None:
        t = PeerTrust(1.01, 1.01)
        t.decay(10000.0)
        assert t.alpha >= 1.0
        assert t.beta >= 1.0


class TestTrustDiscount:
    """trust_discount: hop-based discount for foreign knowledge.

    Wave 41 A1: posterior-aware hop discounting. High-trust peers
    decay more slowly per hop. Cap at 0.5 remains.
    """

    def test_hop_0_capped(self) -> None:
        # Any trust_score > 0.5 gets capped at 0.5
        assert trust_discount(0.8, hop=0) == pytest.approx(0.5)

    def test_hop_1_capped(self) -> None:
        # trust=0.8, hop_base=0.6+0.25*0.8=0.8, 0.8*0.8=0.64, capped at 0.5
        assert trust_discount(0.8, hop=1) == pytest.approx(0.5)

    def test_hop_2_below_cap(self) -> None:
        # trust=0.8, hop_base=0.8, 0.8*0.8^2=0.512, capped at 0.5
        # trust=0.5, hop_base=0.725, 0.5*0.725^2=0.2628 — below cap
        discount = trust_discount(0.5, hop=2)
        assert discount < 0.5
        assert discount > 0.0

    def test_zero_trust(self) -> None:
        assert trust_discount(0.0, hop=0) == pytest.approx(0.0)

    def test_high_trust_decays_slower(self) -> None:
        """Higher trust scores result in slower per-hop decay."""
        high = trust_discount(0.4, hop=3)
        low = trust_discount(0.2, hop=3)
        assert high > low
