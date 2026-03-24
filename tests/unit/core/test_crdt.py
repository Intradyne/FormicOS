"""Tests for CRDT primitives and ObservationCRDT (Wave 33 C1, C2)."""

from __future__ import annotations

import pytest

from formicos.core.crdt import GCounter, GSet, LWWRegister, ObservationCRDT


class TestGCounter:
    """GCounter: grow-only counter with pairwise-max merge."""

    def test_increment_and_value(self) -> None:
        c = GCounter()
        c.increment("A", 3)
        c.increment("B", 2)
        assert c.value() == 5

    def test_delta_must_be_positive(self) -> None:
        c = GCounter()
        with pytest.raises(ValueError, match="positive"):
            c.increment("A", 0)
        with pytest.raises(ValueError, match="positive"):
            c.increment("A", -1)

    def test_merge_commutative(self) -> None:
        a = GCounter(counts={"X": 3, "Y": 1})
        b = GCounter(counts={"X": 1, "Z": 5})
        assert a.merge(b).counts == b.merge(a).counts

    def test_merge_associative(self) -> None:
        a = GCounter(counts={"X": 3})
        b = GCounter(counts={"Y": 2})
        c = GCounter(counts={"X": 1, "Z": 4})
        ab_c = a.merge(b).merge(c)
        a_bc = a.merge(b.merge(c))
        assert ab_c.counts == a_bc.counts

    def test_merge_idempotent(self) -> None:
        a = GCounter(counts={"X": 3, "Y": 1})
        assert a.merge(a).counts == a.counts

    def test_merge_pairwise_max(self) -> None:
        a = GCounter(counts={"X": 3, "Y": 1})
        b = GCounter(counts={"X": 1, "Y": 5})
        merged = a.merge(b)
        assert merged.counts == {"X": 3, "Y": 5}

    def test_value_is_sum(self) -> None:
        c = GCounter(counts={"A": 10, "B": 20, "C": 30})
        assert c.value() == 60


class TestLWWRegister:
    """LWWRegister: last-writer-wins with node_id tie-breaking."""

    def test_higher_timestamp_wins(self) -> None:
        a = LWWRegister(value="old", timestamp=1.0, node_id="A")
        b = LWWRegister(value="new", timestamp=2.0, node_id="B")
        assert a.merge(b).value == "new"
        assert b.merge(a).value == "new"

    def test_tie_broken_by_node_id(self) -> None:
        a = LWWRegister(value="alpha", timestamp=1.0, node_id="A")
        b = LWWRegister(value="bravo", timestamp=1.0, node_id="B")
        # B > A lexicographically
        assert a.merge(b).value == "bravo"
        assert b.merge(a).value == "bravo"

    def test_assign_updates_on_newer(self) -> None:
        r = LWWRegister(value="old", timestamp=1.0, node_id="A")
        r.assign("new", 2.0, "B")
        assert r.value == "new"

    def test_assign_ignores_older(self) -> None:
        r = LWWRegister(value="current", timestamp=5.0, node_id="A")
        r.assign("old", 3.0, "B")
        assert r.value == "current"


class TestGSet:
    """GSet: grow-only set."""

    def test_add_and_contains(self) -> None:
        s = GSet()
        s.add("hello")
        assert "hello" in s
        assert "world" not in s

    def test_merge_is_union(self) -> None:
        a = GSet(elements={"x", "y"})
        b = GSet(elements={"y", "z"})
        merged = a.merge(b)
        assert merged.elements == {"x", "y", "z"}

    def test_elements_never_removed(self) -> None:
        a = GSet(elements={"x", "y", "z"})
        b = GSet(elements={"x"})
        merged = a.merge(b)
        assert "y" in merged
        assert "z" in merged


class TestObservationCRDT:
    """ObservationCRDT: composite type with query-time decay."""

    GAMMA_RATES = {"ephemeral": 0.98, "stable": 0.995, "permanent": 1.0}

    def test_merge_commutative(self) -> None:
        a = ObservationCRDT()
        a.successes.increment("inst-1", 3)
        b = ObservationCRDT()
        b.successes.increment("inst-2", 5)
        ab = a.merge(b)
        ba = b.merge(a)
        assert ab.successes.counts == ba.successes.counts

    def test_merge_idempotent(self) -> None:
        a = ObservationCRDT()
        a.successes.increment("inst-1", 3)
        a.failures.increment("inst-1", 1)
        merged = a.merge(a)
        assert merged.successes.counts == a.successes.counts
        assert merged.failures.counts == a.failures.counts

    def test_query_alpha_no_decay_permanent(self) -> None:
        """permanent decay_class → gamma=1.0, no decay."""
        crdt = ObservationCRDT()
        crdt.successes.increment("inst-1", 10)
        crdt.decay_class.assign("permanent", 1.0, "inst-1")
        crdt.last_obs_ts["inst-1"] = LWWRegister(
            value=None, timestamp=1000.0, node_id="inst-1",
        )
        now = 1000.0 + 86400.0 * 30  # 30 days later
        alpha = crdt.query_alpha(now, self.GAMMA_RATES, prior_alpha=5.0)
        # gamma=1.0, so alpha = 5.0 + 1.0^30 * 10 = 15.0
        assert alpha == pytest.approx(15.0)

    def test_query_alpha_with_ephemeral_decay(self) -> None:
        """ephemeral decay_class → gamma=0.98, alpha decays with elapsed time."""
        crdt = ObservationCRDT()
        crdt.successes.increment("inst-1", 10)
        crdt.last_obs_ts["inst-1"] = LWWRegister(
            value=None, timestamp=1000.0, node_id="inst-1",
        )
        now = 1000.0 + 86400.0 * 30
        alpha = crdt.query_alpha(now, self.GAMMA_RATES, prior_alpha=5.0)
        # gamma=0.98, elapsed=30 days: 0.98^30 ≈ 0.545
        expected = 5.0 + (0.98**30) * 10
        assert alpha == pytest.approx(expected, rel=1e-6)
        assert alpha < 15.0  # decayed compared to permanent

    def test_query_confidence(self) -> None:
        crdt = ObservationCRDT()
        crdt.successes.increment("inst-1", 10)
        crdt.failures.increment("inst-1", 2)
        crdt.decay_class.assign("permanent", 1.0, "inst-1")
        crdt.last_obs_ts["inst-1"] = LWWRegister(
            value=None, timestamp=1000.0, node_id="inst-1",
        )
        now = 1000.0
        conf = crdt.query_confidence(
            now, self.GAMMA_RATES, prior_alpha=5.0, prior_beta=5.0,
        )
        # alpha=15, beta=7, confidence=15/22
        assert conf == pytest.approx(15.0 / 22.0, rel=1e-6)

    def test_two_instances_merge_then_query(self) -> None:
        a = ObservationCRDT()
        a.successes.increment("inst-1", 5)
        a.last_obs_ts["inst-1"] = LWWRegister(
            value=None, timestamp=1000.0, node_id="inst-1",
        )

        b = ObservationCRDT()
        b.successes.increment("inst-2", 3)
        b.last_obs_ts["inst-2"] = LWWRegister(
            value=None, timestamp=1000.0, node_id="inst-2",
        )

        merged = a.merge(b)
        merged.decay_class.assign("permanent", 1.0, "inst-1")
        alpha = merged.query_alpha(
            1000.0, self.GAMMA_RATES, prior_alpha=5.0,
        )
        # permanent, no decay: 5.0 + 5 + 3 = 13.0
        assert alpha == pytest.approx(13.0)
