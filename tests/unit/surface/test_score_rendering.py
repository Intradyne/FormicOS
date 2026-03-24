"""Score breakdown rendering tests (Wave 35 A3).

Validates that _format_tier() includes ranking_explanation at standard/full tiers,
score_breakdown dict at full tier only, and nothing at summary tier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from formicos.surface.knowledge_catalog import KnowledgeCatalog


def _make_result(**overrides: Any) -> dict[str, Any]:
    """Build a minimal search result dict with score breakdown."""
    base: dict[str, Any] = {
        "id": "mem-1",
        "title": "Test entry",
        "summary": "A test knowledge entry",
        "content_preview": "Full content of the test entry for preview purposes",
        "domains": ["python"],
        "decay_class": "stable",
        "conf_alpha": 10.0,
        "conf_beta": 3.0,
        "merged_from": [],
        "status": "verified",
        "_confidence_tier": "HIGH",
        "_score_breakdown": {
            "semantic": 0.85,
            "thompson": 0.72,
            "freshness": 0.60,
            "status": 1.0,
            "thread": 0.0,
            "cooccurrence": 0.45,
            "composite": 0.72,
            "weights": {
                "semantic": 0.38,
                "thompson": 0.25,
                "freshness": 0.15,
                "status": 0.10,
                "thread": 0.07,
                "cooccurrence": 0.05,
            },
        },
    }
    base.update(overrides)
    return base


@dataclass
class _FakeProjections:
    cooccurrence_weights: dict[str, Any] = field(default_factory=dict)
    memory_entries: dict[str, dict[str, Any]] = field(default_factory=dict)
    workspaces: dict[str, Any] = field(default_factory=dict)
    competing_pairs: dict[str, set[str]] = field(default_factory=dict)

    def get_competing_context(self, entry_id: str) -> list[dict[str, Any]]:
        return []


def _make_catalog() -> KnowledgeCatalog:
    return KnowledgeCatalog(
        memory_store=None,
        vector_port=None,
        skill_collection="test",
        projections=_FakeProjections(),  # type: ignore[arg-type]
    )


class TestScoreBreakdownFullTier:
    """Full tier: includes score_breakdown dict and ranking_explanation."""

    def test_full_tier_includes_score_breakdown(self) -> None:
        catalog = _make_catalog()
        results = [_make_result()]
        formatted = catalog._format_tier(results, "full")
        assert len(formatted) == 1
        item = formatted[0]
        assert "score_breakdown" in item
        assert item["score_breakdown"]["semantic"] == 0.85

    def test_full_tier_includes_ranking_explanation(self) -> None:
        catalog = _make_catalog()
        results = [_make_result()]
        formatted = catalog._format_tier(results, "full")
        item = formatted[0]
        assert "ranking_explanation" in item
        assert "dominant:" in item["ranking_explanation"]

    def test_full_tier_dominant_signal_is_semantic(self) -> None:
        catalog = _make_catalog()
        # semantic: 0.85 * 0.38 = 0.323 — highest weighted contribution
        results = [_make_result()]
        formatted = catalog._format_tier(results, "full")
        item = formatted[0]
        assert "(dominant: semantic)" in item["ranking_explanation"]


class TestScoreBreakdownStandardTier:
    """Standard tier: includes ranking_explanation but NOT full score_breakdown."""

    def test_standard_tier_has_ranking_explanation(self) -> None:
        catalog = _make_catalog()
        results = [_make_result()]
        formatted = catalog._format_tier(results, "standard")
        item = formatted[0]
        assert "ranking_explanation" in item
        assert "dominant:" in item["ranking_explanation"]

    def test_standard_tier_no_score_breakdown_dict(self) -> None:
        catalog = _make_catalog()
        results = [_make_result()]
        formatted = catalog._format_tier(results, "standard")
        item = formatted[0]
        # Standard tier should NOT include the full score_breakdown dict
        assert "score_breakdown" not in item

    def test_standard_tier_ranking_explanation_format(self) -> None:
        catalog = _make_catalog()
        results = [_make_result()]
        formatted = catalog._format_tier(results, "standard")
        item = formatted[0]
        expl = item["ranking_explanation"]
        # Should contain all 6 signal names
        for signal in ("semantic", "thompson", "freshness", "status", "thread", "cooccurrence"):
            assert signal in expl


class TestScoreBreakdownSummaryTier:
    """Summary tier: NO score data at all."""

    def test_summary_tier_no_ranking_explanation(self) -> None:
        catalog = _make_catalog()
        results = [_make_result()]
        formatted = catalog._format_tier(results, "summary")
        item = formatted[0]
        assert "ranking_explanation" not in item

    def test_summary_tier_no_score_breakdown(self) -> None:
        catalog = _make_catalog()
        results = [_make_result()]
        formatted = catalog._format_tier(results, "summary")
        item = formatted[0]
        assert "score_breakdown" not in item


class TestDominantSignalDetection:
    """Verify ranking_explanation identifies the correct dominant signal."""

    def test_thompson_dominant_when_highest_contribution(self) -> None:
        catalog = _make_catalog()
        sb = {
            "semantic": 0.30,
            "thompson": 0.95,  # 0.95 * 0.25 = 0.2375
            "freshness": 0.20,
            "status": 0.50,
            "thread": 0.0,
            "cooccurrence": 0.0,
            "composite": 0.50,
            "weights": {
                "semantic": 0.38,  # 0.30 * 0.38 = 0.114
                "thompson": 0.25,
                "freshness": 0.15,
                "status": 0.10,
                "thread": 0.07,
                "cooccurrence": 0.05,
            },
        }
        results = [_make_result(_score_breakdown=sb)]
        formatted = catalog._format_tier(results, "standard")
        assert "(dominant: thompson)" in formatted[0]["ranking_explanation"]

    def test_no_breakdown_no_explanation(self) -> None:
        catalog = _make_catalog()
        result = _make_result()
        del result["_score_breakdown"]
        formatted = catalog._format_tier([result], "standard")
        assert "ranking_explanation" not in formatted[0]
