"""Wave 42 Team 2: class-aware contradiction resolution tests.

Tests cover:
- resolve_classified() dispatches by relation type
- contradiction resolution uses Beta posterior mean
- complement resolution keeps both entries linked
- temporal update resolution picks newer entry
- proactive intelligence class-specific insight generation
- Resolution enum new values
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from formicos.core.types import Resolution
from formicos.surface.conflict_resolution import (
    ClassifiedPair,
    ConflictResult,
    PairRelation,
    classify_pair,
    resolve_classified,
    resolve_conflict,
    _beta_mean,
    _recency_score,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(
    id: str,
    *,
    polarity: str = "positive",
    domains: list[str] | None = None,
    conf_alpha: float = 10.0,
    conf_beta: float = 5.0,
    entry_type: str = "skill",
    created_at: str = "",
    merged_from: list[str] | None = None,
) -> dict:
    return {
        "id": id,
        "polarity": polarity,
        "domains": domains or ["python", "testing"],
        "conf_alpha": conf_alpha,
        "conf_beta": conf_beta,
        "entry_type": entry_type,
        "created_at": created_at or datetime.now(UTC).isoformat(),
        "merged_from": merged_from or [],
        "title": f"Entry {id}",
        "content": f"Content for {id}",
    }


# ---------------------------------------------------------------------------
# Resolution enum
# ---------------------------------------------------------------------------


class TestResolutionEnum:
    def test_complement_value_exists(self) -> None:
        assert Resolution.complement == "complement"

    def test_temporal_update_value_exists(self) -> None:
        assert Resolution.temporal_update == "temporal_update"

    def test_all_values(self) -> None:
        values = {r.value for r in Resolution}
        assert values == {"winner", "competing", "complement", "temporal_update"}


# ---------------------------------------------------------------------------
# Beta mean helper
# ---------------------------------------------------------------------------


class TestBetaMean:
    def test_equal_alpha_beta(self) -> None:
        assert _beta_mean({"conf_alpha": 10, "conf_beta": 10}) == pytest.approx(0.5)

    def test_high_alpha(self) -> None:
        assert _beta_mean({"conf_alpha": 90, "conf_beta": 10}) == pytest.approx(0.9)

    def test_defaults(self) -> None:
        assert _beta_mean({}) == pytest.approx(0.5)

    def test_zero_both(self) -> None:
        assert _beta_mean({"conf_alpha": 0, "conf_beta": 0}) == 0.5


# ---------------------------------------------------------------------------
# Recency score (Wave 42 upgrade)
# ---------------------------------------------------------------------------


class TestRecencyScore:
    def test_empty_string(self) -> None:
        assert _recency_score({}) == 0.0

    def test_recent_entry(self) -> None:
        now = datetime.now(UTC).isoformat()
        score = _recency_score({"created_at": now})
        assert score > 0.9  # very recent → near 1.0

    def test_old_entry(self) -> None:
        old = (datetime.now(UTC) - timedelta(days=365)).isoformat()
        score = _recency_score({"created_at": old})
        assert score < 0.2  # 1 year old → significantly decayed

    def test_invalid_timestamp(self) -> None:
        assert _recency_score({"created_at": "not-a-date"}) == 0.0


# ---------------------------------------------------------------------------
# resolve_classified() — complement path
# ---------------------------------------------------------------------------


class TestResolveComplement:
    def test_complement_resolution(self) -> None:
        ea = _make_entry("a", polarity="positive")
        eb = _make_entry("b", polarity="positive")
        pair = ClassifiedPair("a", "b", PairRelation.complement, 0.8)
        result = resolve_classified(ea, eb, pair)
        assert result.resolution == Resolution.complement
        assert result.method == "complement"
        assert result.primary_id in ("a", "b")
        assert result.secondary_id in ("a", "b")
        assert result.primary_id != result.secondary_id

    def test_complement_higher_confidence_is_primary(self) -> None:
        ea = _make_entry("a", conf_alpha=20.0, conf_beta=5.0)
        eb = _make_entry("b", conf_alpha=5.0, conf_beta=5.0)
        pair = ClassifiedPair("a", "b", PairRelation.complement, 0.7)
        result = resolve_classified(ea, eb, pair)
        assert result.primary_id == "a"
        assert result.primary_score > result.secondary_score

    def test_complement_detail_is_inspectable(self) -> None:
        ea = _make_entry("a")
        eb = _make_entry("b")
        pair = ClassifiedPair("a", "b", PairRelation.complement, 0.6)
        result = resolve_classified(ea, eb, pair)
        assert "Complementary" in result.detail
        assert "co-usable" in result.detail


# ---------------------------------------------------------------------------
# resolve_classified() — temporal update path
# ---------------------------------------------------------------------------


class TestResolveTemporalUpdate:
    def test_temporal_newer_wins(self) -> None:
        old_ts = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        new_ts = datetime.now(UTC).isoformat()
        ea = _make_entry("a", created_at=old_ts)
        eb = _make_entry("b", created_at=new_ts)
        pair = ClassifiedPair("a", "b", PairRelation.temporal_update, 0.8, newer_id="b")
        result = resolve_classified(ea, eb, pair)
        assert result.resolution == Resolution.temporal_update
        assert result.primary_id == "b"
        assert result.secondary_id == "a"
        assert result.method == "temporal_update"

    def test_temporal_older_preserved(self) -> None:
        ea = _make_entry("a")
        eb = _make_entry("b")
        pair = ClassifiedPair("a", "b", PairRelation.temporal_update, 0.9, newer_id="a")
        result = resolve_classified(ea, eb, pair)
        assert result.primary_id == "a"
        assert result.secondary_id == "b"
        assert "supersedes" in result.detail
        assert "historical" in result.detail


# ---------------------------------------------------------------------------
# resolve_classified() — contradiction path
# ---------------------------------------------------------------------------


class TestResolveContradiction:
    def test_contradiction_uses_beta_mean(self) -> None:
        # Entry A: high posterior mean (0.9), entry B: low (0.33)
        ea = _make_entry("a", polarity="positive", conf_alpha=90, conf_beta=10)
        eb = _make_entry("b", polarity="negative", conf_alpha=5, conf_beta=10)
        pair = ClassifiedPair("a", "b", PairRelation.contradiction, 0.8)
        result = resolve_classified(ea, eb, pair)
        assert result.resolution == Resolution.winner
        assert result.primary_id == "a"

    def test_contradiction_close_scores_are_competing(self) -> None:
        ea = _make_entry("a", polarity="positive", conf_alpha=10, conf_beta=10)
        eb = _make_entry("b", polarity="negative", conf_alpha=10, conf_beta=10)
        pair = ClassifiedPair("a", "b", PairRelation.contradiction, 0.6)
        result = resolve_classified(ea, eb, pair)
        assert result.resolution == Resolution.competing
        assert result.method == "competing"

    def test_contradiction_pareto_dominance(self) -> None:
        now = datetime.now(UTC).isoformat()
        old = (datetime.now(UTC) - timedelta(days=200)).isoformat()
        ea = _make_entry(
            "a", polarity="positive", conf_alpha=50, conf_beta=5,
            created_at=now, merged_from=["x", "y", "z"],
        )
        eb = _make_entry(
            "b", polarity="negative", conf_alpha=5, conf_beta=10,
            created_at=old,
        )
        pair = ClassifiedPair("a", "b", PairRelation.contradiction, 0.7)
        result = resolve_classified(ea, eb, pair)
        assert result.resolution == Resolution.winner
        assert result.method == "pareto"
        assert result.primary_id == "a"

    def test_contradiction_detail_is_inspectable(self) -> None:
        ea = _make_entry("a", polarity="positive", conf_alpha=30, conf_beta=5)
        eb = _make_entry("b", polarity="negative", conf_alpha=5, conf_beta=10)
        pair = ClassifiedPair("a", "b", PairRelation.contradiction, 0.5)
        result = resolve_classified(ea, eb, pair)
        assert result.detail  # non-empty inspectable detail


# ---------------------------------------------------------------------------
# resolve_classified() — auto-classification fallback
# ---------------------------------------------------------------------------


class TestResolveClassifiedAutoClassify:
    def test_auto_classifies_contradiction(self) -> None:
        ea = _make_entry("a", polarity="positive", domains=["python"])
        eb = _make_entry("b", polarity="negative", domains=["python"])
        result = resolve_classified(ea, eb)
        # Should auto-classify as contradiction and resolve
        assert result.resolution in (Resolution.winner, Resolution.competing)

    def test_auto_classifies_complement(self) -> None:
        ea = _make_entry("a", polarity="positive", domains=["python"])
        eb = _make_entry("b", polarity="positive", domains=["python"])
        # Different types → complement (not temporal update)
        ea["entry_type"] = "skill"
        eb["entry_type"] = "experience"
        result = resolve_classified(ea, eb)
        assert result.resolution == Resolution.complement

    def test_no_overlap_falls_back(self) -> None:
        ea = _make_entry("a", domains=["python"])
        eb = _make_entry("b", domains=["cooking"])
        result = resolve_classified(ea, eb)
        # Falls back to legacy resolve_conflict (no overlap)
        assert result.resolution in (Resolution.winner, Resolution.competing)


# ---------------------------------------------------------------------------
# Legacy resolve_conflict() backward compatibility
# ---------------------------------------------------------------------------


class TestResolveConflictLegacy:
    def test_still_returns_result(self) -> None:
        ea = _make_entry("a", polarity="positive")
        eb = _make_entry("b", polarity="negative")
        result = resolve_conflict(ea, eb)
        assert isinstance(result, ConflictResult)

    def test_delegates_to_resolve_classified(self) -> None:
        ea = _make_entry("a", polarity="positive", conf_alpha=50, conf_beta=5)
        eb = _make_entry("b", polarity="negative", conf_alpha=5, conf_beta=10)
        result = resolve_conflict(ea, eb)
        # Should now use the Wave 42 Beta-mean-based scoring
        assert result.resolution in (Resolution.winner, Resolution.competing)


# ---------------------------------------------------------------------------
# Proactive intelligence class-specific insights
# ---------------------------------------------------------------------------


class TestProactiveContradictionRule:
    def test_contradiction_gives_action_required(self) -> None:
        from formicos.surface.proactive_intelligence import _rule_contradiction

        entries = {
            "a": _make_entry("a", polarity="positive", conf_alpha=10, conf_beta=2),
            "b": _make_entry("b", polarity="negative", conf_alpha=10, conf_beta=2),
        }
        entries["a"]["status"] = "verified"
        entries["b"]["status"] = "verified"
        insights = _rule_contradiction(entries)
        contradictions = [i for i in insights if i.severity == "action_required"]
        assert len(contradictions) >= 1
        assert contradictions[0].category == "contradiction"

    def test_temporal_update_gives_attention(self) -> None:
        from formicos.surface.proactive_intelligence import _rule_contradiction

        old_ts = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        new_ts = datetime.now(UTC).isoformat()
        entries = {
            "a": _make_entry("a", created_at=old_ts, conf_alpha=10, conf_beta=2),
            "b": _make_entry("b", created_at=new_ts, conf_alpha=10, conf_beta=2),
        }
        entries["a"]["status"] = "verified"
        entries["b"]["status"] = "verified"
        insights = _rule_contradiction(entries)
        temporal = [i for i in insights if i.severity == "attention"]
        assert len(temporal) >= 1
        assert "supersedes" in temporal[0].title.lower() or "temporal" in temporal[0].title.lower()

    def test_complement_not_surfaced_as_action_required(self) -> None:
        from formicos.surface.proactive_intelligence import _rule_contradiction

        entries = {
            "a": _make_entry("a", polarity="positive", conf_alpha=10, conf_beta=2,
                             entry_type="skill"),
            "b": _make_entry("b", polarity="positive", conf_alpha=10, conf_beta=2,
                             entry_type="experience"),
        }
        entries["a"]["status"] = "verified"
        entries["b"]["status"] = "verified"
        insights = _rule_contradiction(entries)
        action_required = [i for i in insights if i.severity == "action_required"]
        assert len(action_required) == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_resolve_classified_with_none_classification(self) -> None:
        ea = _make_entry("a", domains=["unique_domain_xyz"])
        eb = _make_entry("b", domains=["totally_different"])
        result = resolve_classified(ea, eb, None)
        assert isinstance(result, ConflictResult)

    def test_temporal_update_with_same_id_newer(self) -> None:
        ea = _make_entry("a")
        eb = _make_entry("b")
        pair = ClassifiedPair("a", "b", PairRelation.temporal_update, 0.9, newer_id="a")
        result = resolve_classified(ea, eb, pair)
        assert result.primary_id == "a"
        assert result.secondary_id == "b"
