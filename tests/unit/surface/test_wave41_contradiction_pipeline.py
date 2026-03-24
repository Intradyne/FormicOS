"""Wave 41 A3: Contradiction pipeline overhaul tests."""

from __future__ import annotations

from formicos.surface.conflict_resolution import (
    ClassifiedPair,
    PairRelation,
    classify_pair,
    detect_contradictions,
    jaccard,
)


class TestJaccard:
    """Tests for the shared Jaccard helper."""

    def test_identical_sets(self) -> None:
        assert jaccard({"a", "b"}, {"a", "b"}) == 1.0

    def test_disjoint_sets(self) -> None:
        assert jaccard({"a"}, {"b"}) == 0.0

    def test_partial_overlap(self) -> None:
        assert jaccard({"a", "b", "c"}, {"b", "c", "d"}) == 0.5

    def test_both_empty(self) -> None:
        assert jaccard(set(), set()) == 0.0

    def test_one_empty(self) -> None:
        assert jaccard({"a"}, set()) == 0.0


class TestClassifyPair:
    """Tests for pair classification."""

    def _entry(
        self,
        *,
        id: str = "e1",
        polarity: str = "positive",
        domains: list[str] | None = None,
        entry_type: str = "skill",
        created_at: str = "2026-01-01T00:00:00",
    ) -> dict:
        return {
            "id": id,
            "polarity": polarity,
            "domains": domains or ["python", "testing"],
            "entry_type": entry_type,
            "created_at": created_at,
        }

    def test_contradiction_opposite_polarity(self) -> None:
        """Opposite polarity + domain overlap = contradiction."""
        a = self._entry(id="a", polarity="positive")
        b = self._entry(id="b", polarity="negative")
        result = classify_pair(a, b)
        assert result is not None
        assert result.relation == PairRelation.contradiction
        assert result.domain_overlap == 1.0

    def test_complement_same_polarity(self) -> None:
        """Same polarity + overlap = complement."""
        a = self._entry(id="a", polarity="positive")
        b = self._entry(id="b", polarity="positive", domains=["python", "testing", "ci"])
        result = classify_pair(a, b)
        assert result is not None
        assert result.relation == PairRelation.complement

    def test_temporal_update(self) -> None:
        """Same type, high overlap, different timestamps = temporal update."""
        a = self._entry(
            id="a", polarity="neutral",
            domains=["python", "testing", "ci"],
            created_at="2026-01-01T00:00:00",
        )
        b = self._entry(
            id="b", polarity="neutral",
            domains=["python", "testing", "ci"],
            created_at="2026-03-01T00:00:00",
        )
        result = classify_pair(a, b)
        assert result is not None
        assert result.relation == PairRelation.temporal_update
        assert result.newer_id == "b"

    def test_no_overlap_returns_none(self) -> None:
        """Entries with no domain overlap return None."""
        a = self._entry(id="a", domains=["python"])
        b = self._entry(id="b", domains=["javascript"])
        result = classify_pair(a, b)
        assert result is None

    def test_custom_threshold(self) -> None:
        """Custom threshold controls overlap sensitivity."""
        a = self._entry(id="a", domains=["a", "b", "c", "d"])
        b = self._entry(id="b", domains=["c", "d", "e", "f"])
        # Jaccard = 2/6 = 0.33
        assert classify_pair(a, b, overlap_threshold=0.5) is None
        result = classify_pair(a, b, overlap_threshold=0.3)
        assert result is not None


class TestDetectContradictions:
    """Tests for batch contradiction detection."""

    def _make_entries(self) -> dict[str, dict]:
        return {
            "e1": {
                "id": "e1",
                "status": "verified",
                "polarity": "positive",
                "domains": ["python", "testing"],
                "conf_alpha": 10.0,
                "conf_beta": 3.0,
                "entry_type": "skill",
                "created_at": "2026-01-01",
            },
            "e2": {
                "id": "e2",
                "status": "verified",
                "polarity": "negative",
                "domains": ["python", "testing"],
                "conf_alpha": 8.0,
                "conf_beta": 4.0,
                "entry_type": "skill",
                "created_at": "2026-02-01",
            },
            "e3": {
                "id": "e3",
                "status": "candidate",
                "polarity": "positive",
                "domains": ["rust", "systems"],
                "conf_alpha": 2.0,
                "conf_beta": 2.0,
                "entry_type": "experience",
                "created_at": "2026-01-15",
            },
        }

    def test_finds_contradiction(self) -> None:
        """Detects contradiction between e1 and e2."""
        entries = self._make_entries()
        results = detect_contradictions(entries)
        contradictions = [r for r in results if r.relation == PairRelation.contradiction]
        assert len(contradictions) == 1
        pair = contradictions[0]
        ids = {pair.entry_a_id, pair.entry_b_id}
        assert ids == {"e1", "e2"}

    def test_status_filter(self) -> None:
        """Status filter limits which entries are scanned."""
        entries = self._make_entries()
        # Only scan candidates — e1 and e2 are verified, so no contradiction
        results = detect_contradictions(
            entries, status_filter={"candidate"},
        )
        assert len(results) == 0

    def test_min_alpha_filter(self) -> None:
        """Entries below min_alpha are excluded."""
        entries = self._make_entries()
        # Set high min_alpha — only e1 (alpha=10) qualifies
        results = detect_contradictions(entries, min_alpha=9.0)
        assert len(results) == 0  # only 1 entry qualifies, no pairs

    def test_no_duplicates(self) -> None:
        """Same pair is not returned twice."""
        entries = self._make_entries()
        results = detect_contradictions(entries)
        pair_keys = {
            (min(r.entry_a_id, r.entry_b_id), max(r.entry_a_id, r.entry_b_id))
            for r in results
        }
        assert len(pair_keys) == len(results)

    def test_empty_entries(self) -> None:
        """Empty entry dict returns empty list."""
        assert detect_contradictions({}) == []
