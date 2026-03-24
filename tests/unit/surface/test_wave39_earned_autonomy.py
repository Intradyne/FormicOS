"""Earned autonomy recommendation tests (Wave 39, Pillar 4B).

Validates that:
- promotion requires ≥5 follow-throughs (asymmetric: harder to earn)
- demotion triggers on ≥3 kills (easier to lose trust)
- cooldown prevents dismissed recommendations from reappearing
- no recommendations when insufficient evidence
- autonomy level progression is correct
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from formicos.surface.proactive_intelligence import (
    KnowledgeInsight,
    _next_autonomy_level,
    _rule_earned_autonomy,
)
from formicos.surface.projections import ProjectionStore


def _make_store_with_workspace(
    ws_id: str = "ws-1",
    autonomy_level: str = "suggest",
    auto_actions: list[str] | None = None,
) -> ProjectionStore:
    """Create a ProjectionStore with a workspace and maintenance policy."""
    store = ProjectionStore()
    from formicos.surface.projections import WorkspaceProjection
    store.workspaces[ws_id] = WorkspaceProjection(
        id=ws_id,
        name="Test Workspace",
        config={
            "maintenance_policy": {
                "autonomy_level": autonomy_level,
                "auto_actions": auto_actions or [],
            },
        },
    )
    return store


class TestAutonomyLevelProgression:
    """Autonomy level ordering: suggest → auto_notify → autonomous."""

    def test_promote_from_suggest(self) -> None:
        assert _next_autonomy_level("suggest", "promote") == "auto_notify"

    def test_promote_from_auto_notify(self) -> None:
        assert _next_autonomy_level("auto_notify", "promote") == "autonomous"

    def test_promote_from_autonomous_is_none(self) -> None:
        assert _next_autonomy_level("autonomous", "promote") is None

    def test_demote_from_autonomous(self) -> None:
        assert _next_autonomy_level("autonomous", "demote") == "auto_notify"

    def test_demote_from_auto_notify(self) -> None:
        assert _next_autonomy_level("auto_notify", "demote") == "suggest"

    def test_demote_from_suggest_is_none(self) -> None:
        assert _next_autonomy_level("suggest", "demote") is None


class TestPromotionRecommendations:
    """Promotion requires ≥5 follow-throughs (harder to earn trust)."""

    def test_no_recommendation_with_few_follow_throughs(self) -> None:
        """4 follow-throughs is insufficient for promotion."""
        store = _make_store_with_workspace()
        for i in range(4):
            store.operator_behavior.record_suggestion_follow_through(
                insight_category="coverage",
                colony_id=f"col-{i}",
                workspace_id="ws-1",
                timestamp=datetime.now(tz=UTC).isoformat(),
            )
        insights = _rule_earned_autonomy(store, "ws-1")
        autonomy_insights = [i for i in insights if i.category == "earned_autonomy"]
        assert len(autonomy_insights) == 0

    def test_recommendation_at_5_follow_throughs(self) -> None:
        """5 follow-throughs should trigger promotion recommendation."""
        store = _make_store_with_workspace()
        for i in range(5):
            store.operator_behavior.record_suggestion_follow_through(
                insight_category="coverage",
                colony_id=f"col-{i}",
                workspace_id="ws-1",
                timestamp=datetime.now(tz=UTC).isoformat(),
            )
        insights = _rule_earned_autonomy(store, "ws-1")
        autonomy_insights = [i for i in insights if i.category == "earned_autonomy"]
        assert len(autonomy_insights) >= 1
        assert "promote" in autonomy_insights[0].title.lower()
        assert "coverage" in autonomy_insights[0].title

    def test_no_recommendation_when_already_in_auto_actions(self) -> None:
        """Category already in auto_actions should not get promotion rec."""
        store = _make_store_with_workspace(auto_actions=["coverage"])
        for i in range(6):
            store.operator_behavior.record_suggestion_follow_through(
                insight_category="coverage",
                colony_id=f"col-{i}",
                workspace_id="ws-1",
                timestamp=datetime.now(tz=UTC).isoformat(),
            )
        insights = _rule_earned_autonomy(store, "ws-1")
        coverage_insights = [
            i for i in insights
            if i.category == "earned_autonomy" and "coverage" in i.title
        ]
        assert len(coverage_insights) == 0

    def test_no_promotion_when_already_autonomous(self) -> None:
        """Already at 'autonomous' level — no further promotion possible."""
        store = _make_store_with_workspace(autonomy_level="autonomous")
        for i in range(6):
            store.operator_behavior.record_suggestion_follow_through(
                insight_category="coverage",
                colony_id=f"col-{i}",
                workspace_id="ws-1",
                timestamp=datetime.now(tz=UTC).isoformat(),
            )
        insights = _rule_earned_autonomy(store, "ws-1")
        autonomy_insights = [i for i in insights if i.category == "earned_autonomy"]
        promote_insights = [i for i in autonomy_insights if "promote" in i.title.lower()]
        assert len(promote_insights) == 0


class TestDemotionRecommendations:
    """Demotion triggers on ≥3 kills (easier to lose trust)."""

    def test_no_demotion_with_few_kills(self) -> None:
        """2 kills is insufficient for demotion."""
        store = _make_store_with_workspace(autonomy_level="auto_notify")
        for i in range(2):
            store.operator_behavior.record_kill(
                colony_id=f"col-{i}",
                workspace_id="ws-1",
                killed_by="operator",
                strategy="stigmergic",
                round_at_kill=3,
                timestamp=datetime.now(tz=UTC).isoformat(),
            )
        insights = _rule_earned_autonomy(store, "ws-1")
        demotion_insights = [
            i for i in insights
            if i.category == "earned_autonomy" and "demotion" in i.title.lower()
        ]
        assert len(demotion_insights) == 0

    def test_demotion_at_3_kills(self) -> None:
        """3 kills should trigger demotion recommendation."""
        store = _make_store_with_workspace(autonomy_level="auto_notify")
        for i in range(3):
            store.operator_behavior.record_kill(
                colony_id=f"col-{i}",
                workspace_id="ws-1",
                killed_by="operator",
                strategy="stigmergic",
                round_at_kill=3,
                timestamp=datetime.now(tz=UTC).isoformat(),
            )
        insights = _rule_earned_autonomy(store, "ws-1")
        demotion_insights = [
            i for i in insights
            if i.category == "earned_autonomy" and "demotion" in i.title.lower()
        ]
        assert len(demotion_insights) >= 1

    def test_no_demotion_at_suggest_level(self) -> None:
        """Already at 'suggest' — no further demotion possible."""
        store = _make_store_with_workspace(autonomy_level="suggest")
        for i in range(5):
            store.operator_behavior.record_kill(
                colony_id=f"col-{i}",
                workspace_id="ws-1",
                killed_by="operator",
                strategy="stigmergic",
                round_at_kill=3,
                timestamp=datetime.now(tz=UTC).isoformat(),
            )
        insights = _rule_earned_autonomy(store, "ws-1")
        demotion_insights = [
            i for i in insights
            if i.category == "earned_autonomy" and "demotion" in i.title.lower()
        ]
        assert len(demotion_insights) == 0

    def test_negative_feedback_triggers_demotion(self) -> None:
        """High negative feedback rate should trigger demotion."""
        store = _make_store_with_workspace(autonomy_level="auto_notify")
        # 3 negative, 1 positive = 75% negative rate
        for i in range(3):
            store.operator_behavior.record_feedback(
                entry_id=f"e-{i}",
                workspace_id="ws-1",
                colony_id=f"col-{i}",
                direction="negative",
                timestamp=datetime.now(tz=UTC).isoformat(),
                domains=["python"],
            )
        store.operator_behavior.record_feedback(
            entry_id="e-pos",
            workspace_id="ws-1",
            colony_id="col-pos",
            direction="positive",
            timestamp=datetime.now(tz=UTC).isoformat(),
            domains=["python"],
        )
        insights = _rule_earned_autonomy(store, "ws-1")
        feedback_insights = [
            i for i in insights
            if i.category == "earned_autonomy" and "negative feedback" in i.title.lower()
        ]
        assert len(feedback_insights) >= 1


class TestCooldownMechanism:
    """Dismissed recommendations should not reappear for 7 days."""

    def test_cooldown_prevents_reappearance(self) -> None:
        """Dismissed category should not generate new recommendation."""
        store = _make_store_with_workspace()
        for i in range(6):
            store.operator_behavior.record_suggestion_follow_through(
                insight_category="coverage",
                colony_id=f"col-{i}",
                workspace_id="ws-1",
                timestamp=datetime.now(tz=UTC).isoformat(),
            )
        # Dismiss the category
        store.autonomy_recommendation_dismissals["coverage"] = (
            datetime.now(tz=UTC).isoformat()
        )
        insights = _rule_earned_autonomy(store, "ws-1")
        coverage_insights = [
            i for i in insights
            if i.category == "earned_autonomy" and "coverage" in i.title
        ]
        assert len(coverage_insights) == 0

    def test_cooldown_expires_after_7_days(self) -> None:
        """After 7 days, dismissed recommendation should reappear."""
        store = _make_store_with_workspace()
        for i in range(6):
            store.operator_behavior.record_suggestion_follow_through(
                insight_category="coverage",
                colony_id=f"col-{i}",
                workspace_id="ws-1",
                timestamp=datetime.now(tz=UTC).isoformat(),
            )
        # Dismiss 8 days ago
        old_ts = (datetime.now(tz=UTC) - timedelta(days=8)).isoformat()
        store.autonomy_recommendation_dismissals["coverage"] = old_ts
        insights = _rule_earned_autonomy(store, "ws-1")
        coverage_insights = [
            i for i in insights
            if i.category == "earned_autonomy" and "coverage" in i.title
        ]
        assert len(coverage_insights) >= 1


class TestAsymmetricThresholds:
    """Earning trust is harder than losing it."""

    def test_promotion_requires_more_evidence_than_demotion(self) -> None:
        """Promotion needs 5 signals; demotion needs only 3."""
        store = _make_store_with_workspace(autonomy_level="auto_notify")

        # 4 follow-throughs: not enough for promotion
        for i in range(4):
            store.operator_behavior.record_suggestion_follow_through(
                insight_category="coverage",
                colony_id=f"col-{i}",
                workspace_id="ws-1",
                timestamp=datetime.now(tz=UTC).isoformat(),
            )
        # 3 kills: enough for demotion
        for i in range(3):
            store.operator_behavior.record_kill(
                colony_id=f"kill-{i}",
                workspace_id="ws-1",
                killed_by="operator",
                strategy="sequential",
                round_at_kill=2,
                timestamp=datetime.now(tz=UTC).isoformat(),
            )

        insights = _rule_earned_autonomy(store, "ws-1")
        promote_insights = [
            i for i in insights
            if i.category == "earned_autonomy" and "promote" in i.title.lower()
        ]
        demote_insights = [
            i for i in insights
            if i.category == "earned_autonomy" and "demotion" in i.title.lower()
        ]
        # 4 follow-throughs < 5 threshold → no promotion
        assert len(promote_insights) == 0
        # 3 kills >= 3 threshold → demotion fires
        assert len(demote_insights) >= 1


class TestNoWorkspace:
    """Graceful handling when workspace doesn't exist."""

    def test_no_insights_without_workspace(self) -> None:
        store = ProjectionStore()
        insights = _rule_earned_autonomy(store, "nonexistent")
        assert insights == []
