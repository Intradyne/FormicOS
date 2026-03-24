"""Configuration memory recommendation tests (Wave 39, Pillar 5).

Validates that:
- config recommendations require minimum evidence (≥3 outcomes)
- strategy recommendations surface best-performing strategy
- caste recommendations surface best-performing composition
- round range recommendations surface optimal bucket
- model tier recommendations surface best tier
- empty/insufficient data returns no recommendations
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from formicos.surface.proactive_intelligence import (
    ConfigRecommendation,
    generate_config_recommendations,
)
from formicos.surface.projections import ColonyOutcome, ProjectionStore


def _make_outcome(
    colony_id: str,
    workspace_id: str = "ws-1",
    strategy: str = "stigmergic",
    quality_score: float = 0.7,
    total_rounds: int = 5,
    caste_composition: list[str] | None = None,
    succeeded: bool = True,
    starting_tier: str | None = None,
    escalated_tier: str | None = None,
) -> ColonyOutcome:
    return ColonyOutcome(
        colony_id=colony_id,
        workspace_id=workspace_id,
        thread_id="t-1",
        succeeded=succeeded,
        total_rounds=total_rounds,
        total_cost=0.5,
        duration_ms=10000,
        entries_extracted=1,
        entries_accessed=3,
        quality_score=quality_score,
        caste_composition=caste_composition or ["coder"],
        strategy=strategy,
        starting_tier=starting_tier,
        escalated_tier=escalated_tier,
    )


def _make_store_with_outcomes(
    outcomes: list[ColonyOutcome],
) -> ProjectionStore:
    store = ProjectionStore()
    for o in outcomes:
        store.colony_outcomes[o.colony_id] = o
    return store


class TestMinimumEvidence:
    """Config recommendations require ≥3 successful outcomes."""

    def test_no_recommendations_with_0_outcomes(self) -> None:
        store = ProjectionStore()
        recs = generate_config_recommendations("ws-1", store)
        assert recs == []

    def test_no_recommendations_with_2_outcomes(self) -> None:
        outcomes = [
            _make_outcome("c1"),
            _make_outcome("c2"),
        ]
        store = _make_store_with_outcomes(outcomes)
        recs = generate_config_recommendations("ws-1", store)
        assert recs == []

    def test_recommendations_with_3_outcomes(self) -> None:
        outcomes = [
            _make_outcome("c1", strategy="stigmergic", quality_score=0.8),
            _make_outcome("c2", strategy="stigmergic", quality_score=0.7),
            _make_outcome("c3", strategy="stigmergic", quality_score=0.9),
        ]
        store = _make_store_with_outcomes(outcomes)
        recs = generate_config_recommendations("ws-1", store)
        assert len(recs) >= 1  # At least strategy recommendation

    def test_failed_outcomes_excluded(self) -> None:
        """Only successful outcomes count toward evidence."""
        outcomes = [
            _make_outcome("c1", succeeded=True, quality_score=0.8),
            _make_outcome("c2", succeeded=True, quality_score=0.7),
            _make_outcome("c3", succeeded=False, quality_score=0.3),
            _make_outcome("c4", succeeded=False, quality_score=0.2),
        ]
        store = _make_store_with_outcomes(outcomes)
        recs = generate_config_recommendations("ws-1", store)
        # Only 2 successful → below threshold
        assert recs == []


class TestStrategyRecommendation:
    """Strategy recommendation surfaces best-performing strategy."""

    def test_best_strategy_recommended(self) -> None:
        outcomes = [
            _make_outcome("c1", strategy="stigmergic", quality_score=0.9),
            _make_outcome("c2", strategy="stigmergic", quality_score=0.8),
            _make_outcome("c3", strategy="sequential", quality_score=0.5),
            _make_outcome("c4", strategy="sequential", quality_score=0.4),
        ]
        store = _make_store_with_outcomes(outcomes)
        recs = generate_config_recommendations("ws-1", store)
        strat_recs = [r for r in recs if r.dimension == "strategy"]
        assert len(strat_recs) == 1
        assert strat_recs[0].recommended_value == "stigmergic"
        assert strat_recs[0].avg_quality > 0.8

    def test_confidence_based_on_sample_size(self) -> None:
        """5+ samples → high confidence."""
        outcomes = [
            _make_outcome(f"c{i}", strategy="stigmergic", quality_score=0.8)
            for i in range(6)
        ]
        store = _make_store_with_outcomes(outcomes)
        recs = generate_config_recommendations("ws-1", store)
        strat_recs = [r for r in recs if r.dimension == "strategy"]
        assert len(strat_recs) == 1
        assert strat_recs[0].confidence == "high"
        assert strat_recs[0].sample_size >= 5


class TestCasteRecommendation:
    """Caste recommendation surfaces best-performing composition."""

    def test_best_caste_recommended(self) -> None:
        outcomes = [
            _make_outcome("c1", caste_composition=["coder", "reviewer"], quality_score=0.9),
            _make_outcome("c2", caste_composition=["coder", "reviewer"], quality_score=0.8),
            _make_outcome("c3", caste_composition=["coder"], quality_score=0.5),
            _make_outcome("c4", caste_composition=["coder"], quality_score=0.6),
        ]
        store = _make_store_with_outcomes(outcomes)
        recs = generate_config_recommendations("ws-1", store)
        caste_recs = [r for r in recs if r.dimension == "caste"]
        assert len(caste_recs) == 1
        assert "coder" in caste_recs[0].recommended_value
        assert "reviewer" in caste_recs[0].recommended_value


class TestRoundRangeRecommendation:
    """Round range recommendation surfaces optimal bucket."""

    def test_optimal_round_range(self) -> None:
        outcomes = [
            _make_outcome("c1", total_rounds=3, quality_score=0.9),
            _make_outcome("c2", total_rounds=4, quality_score=0.85),
            _make_outcome("c3", total_rounds=5, quality_score=0.8),
            _make_outcome("c4", total_rounds=12, quality_score=0.5),
            _make_outcome("c5", total_rounds=15, quality_score=0.4),
        ]
        store = _make_store_with_outcomes(outcomes)
        recs = generate_config_recommendations("ws-1", store)
        round_recs = [r for r in recs if r.dimension == "max_rounds"]
        assert len(round_recs) == 1
        assert round_recs[0].recommended_value == "1-5"


class TestModelTierRecommendation:
    """Model tier recommendation surfaces best tier from escalation data."""

    def test_best_tier_recommended(self) -> None:
        outcomes = [
            _make_outcome("c1", starting_tier="light", quality_score=0.5),
            _make_outcome("c2", starting_tier="light", quality_score=0.4),
            _make_outcome("c3", starting_tier="standard", quality_score=0.9),
            _make_outcome("c4", starting_tier="standard", quality_score=0.85),
        ]
        store = _make_store_with_outcomes(outcomes)
        recs = generate_config_recommendations("ws-1", store)
        tier_recs = [r for r in recs if r.dimension == "model_tier"]
        assert len(tier_recs) == 1
        assert tier_recs[0].recommended_value == "standard"

    def test_escalated_tier_used_when_available(self) -> None:
        outcomes = [
            _make_outcome("c1", starting_tier="light", escalated_tier="standard", quality_score=0.9),
            _make_outcome("c2", starting_tier="light", escalated_tier="standard", quality_score=0.85),
            _make_outcome("c3", starting_tier="light", quality_score=0.5),
        ]
        store = _make_store_with_outcomes(outcomes)
        recs = generate_config_recommendations("ws-1", store)
        tier_recs = [r for r in recs if r.dimension == "model_tier"]
        assert len(tier_recs) == 1
        assert tier_recs[0].recommended_value == "standard"


class TestWorkspaceScoping:
    """Recommendations are workspace-scoped."""

    def test_only_workspace_outcomes_used(self) -> None:
        outcomes = [
            _make_outcome("c1", workspace_id="ws-1", quality_score=0.9),
            _make_outcome("c2", workspace_id="ws-1", quality_score=0.8),
            _make_outcome("c3", workspace_id="ws-1", quality_score=0.7),
            _make_outcome("c4", workspace_id="ws-other", quality_score=0.1),
            _make_outcome("c5", workspace_id="ws-other", quality_score=0.1),
        ]
        store = _make_store_with_outcomes(outcomes)
        recs = generate_config_recommendations("ws-1", store)
        # Should recommend based on ws-1 outcomes (high quality), not ws-other
        strat_recs = [r for r in recs if r.dimension == "strategy"]
        if strat_recs:
            assert strat_recs[0].avg_quality > 0.7


class TestConfigRecommendationFields:
    """All recommendation fields are properly populated."""

    def test_recommendation_has_all_fields(self) -> None:
        outcomes = [
            _make_outcome(f"c{i}", quality_score=0.8) for i in range(4)
        ]
        store = _make_store_with_outcomes(outcomes)
        recs = generate_config_recommendations("ws-1", store)
        for r in recs:
            assert r.dimension in ("strategy", "caste", "max_rounds", "model_tier")
            assert r.recommended_value != ""
            assert r.evidence_summary != ""
            assert r.sample_size >= 2
            assert 0.0 <= r.avg_quality <= 1.0
            assert r.confidence in ("high", "moderate", "low")
