"""Tests for VectorClock (Wave 33 C5)."""

from __future__ import annotations

from formicos.core.vector_clock import VectorClock


class TestVectorClock:
    """VectorClock: causal ordering for federated instances."""

    def test_happens_before_true(self) -> None:
        a = VectorClock(clock={"A": 1})
        b = VectorClock(clock={"A": 2})
        assert a.happens_before(b) is True

    def test_happens_before_false_when_greater(self) -> None:
        a = VectorClock(clock={"A": 2})
        b = VectorClock(clock={"A": 1})
        assert a.happens_before(b) is False

    def test_happens_before_false_when_equal(self) -> None:
        a = VectorClock(clock={"A": 1})
        b = VectorClock(clock={"A": 1})
        assert a.happens_before(b) is False

    def test_is_concurrent(self) -> None:
        a = VectorClock(clock={"A": 1, "B": 0})
        b = VectorClock(clock={"A": 0, "B": 1})
        assert a.is_concurrent(b) is True

    def test_not_concurrent_when_ordered(self) -> None:
        a = VectorClock(clock={"A": 1})
        b = VectorClock(clock={"A": 2})
        assert a.is_concurrent(b) is False

    def test_merge_pairwise_max(self) -> None:
        a = VectorClock(clock={"A": 3, "B": 1})
        b = VectorClock(clock={"A": 1, "B": 5, "C": 2})
        merged = a.merge(b)
        assert merged.clock == {"A": 3, "B": 5, "C": 2}

    def test_increment_only_specified_instance(self) -> None:
        vc = VectorClock(clock={"A": 1, "B": 2})
        result = vc.increment("A")
        assert result.clock == {"A": 2, "B": 2}
        # Original unchanged
        assert vc.clock == {"A": 1, "B": 2}

    def test_increment_new_instance(self) -> None:
        vc = VectorClock()
        result = vc.increment("X")
        assert result.clock == {"X": 1}

    def test_concurrent_three_instances(self) -> None:
        a = VectorClock(clock={"X": 2, "Y": 1})
        b = VectorClock(clock={"X": 1, "Y": 2})
        assert a.is_concurrent(b) is True
        assert b.is_concurrent(a) is True
