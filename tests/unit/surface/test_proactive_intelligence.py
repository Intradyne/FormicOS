"""Tests for proactive intelligence briefing (Wave 34 Track B Team 2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from formicos.surface.proactive_intelligence import (
    KnowledgeInsight,
    ProactiveBriefing,
    SuggestedColony,
    generate_briefing,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class _FakeCooccurrence:
    weight: float = 1.0
    last_reinforced: str = ""
    reinforcement_count: int = 0


@dataclass
class _FakeProjections:
    """Minimal projection stand-in for testing."""

    memory_entries: dict[str, dict[str, Any]] = field(default_factory=dict)
    cooccurrence_weights: dict[tuple[str, str], _FakeCooccurrence] = field(
        default_factory=dict,
    )
    knowledge_entry_usage: dict[str, dict[str, Any]] = field(default_factory=dict)


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _recent_iso() -> str:
    return (datetime.now(tz=UTC) - timedelta(days=1)).isoformat()


# ---------------------------------------------------------------------------
# B1: Queen prompt tests
# ---------------------------------------------------------------------------


class TestQueenPromptRedesign:
    """Verify the Queen prompt has required system awareness sections."""

    def test_prompt_within_line_limit(self) -> None:
        import yaml
        data = yaml.safe_load(open("config/caste_recipes.yaml"))
        prompt = data["castes"]["queen"]["system_prompt"]
        lines = prompt.strip().split("\n")
        assert 80 <= len(lines) <= 170, f"Queen prompt is {len(lines)} lines"

    @pytest.mark.parametrize("keyword", [
        "decay class",
        "co-occurrence",
        "prediction error",
        "federation",
        "contradiction",
        "detail=",
    ])
    def test_prompt_contains_keyword(self, keyword: str) -> None:
        import yaml
        data = yaml.safe_load(open("config/caste_recipes.yaml"))
        prompt = data["castes"]["queen"]["system_prompt"].lower()
        assert keyword in prompt, f"Missing keyword: {keyword}"

    def test_prompt_contains_tiered(self) -> None:
        import yaml
        data = yaml.safe_load(open("config/caste_recipes.yaml"))
        prompt = data["castes"]["queen"]["system_prompt"].lower()
        assert "tiered" in prompt


# ---------------------------------------------------------------------------
# B2: Proactive intelligence insight rules
# ---------------------------------------------------------------------------


class TestConfidenceDecline:
    """Rule 1: confidence decline detection."""

    def test_decline_detected(self) -> None:
        proj = _FakeProjections(memory_entries={
            "e1": {
                "workspace_id": "ws1",
                "conf_alpha": 8.0,
                "conf_beta": 5.0,
                "peak_alpha": 15.0,
                "title": "Testing patterns",
                "last_confidence_update": _recent_iso(),
            },
        })
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        confidence_insights = [
            i for i in briefing.insights if i.category == "confidence"
        ]
        assert len(confidence_insights) == 1
        assert confidence_insights[0].severity == "attention"
        assert "e1" in confidence_insights[0].affected_entries

    def test_no_decline_when_stable(self) -> None:
        proj = _FakeProjections(memory_entries={
            "e1": {
                "workspace_id": "ws1",
                "conf_alpha": 14.0,
                "conf_beta": 5.0,
                "peak_alpha": 15.0,
                "title": "Stable entry",
                "last_confidence_update": _recent_iso(),
            },
        })
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        confidence_insights = [
            i for i in briefing.insights if i.category == "confidence"
        ]
        assert len(confidence_insights) == 0


class TestContradiction:
    """Rule 2: contradiction detection."""

    def test_contradiction_detected(self) -> None:
        proj = _FakeProjections(memory_entries={
            "e1": {
                "workspace_id": "ws1",
                "status": "verified",
                "conf_alpha": 10.0,
                "conf_beta": 3.0,
                "polarity": "positive",
                "domains": ["testing", "python"],
                "title": "Use mocks",
            },
            "e2": {
                "workspace_id": "ws1",
                "status": "verified",
                "conf_alpha": 12.0,
                "conf_beta": 4.0,
                "polarity": "negative",
                "domains": ["testing", "python"],
                "title": "Avoid mocks",
            },
        })
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        contradiction_insights = [
            i for i in briefing.insights if i.category == "contradiction"
        ]
        assert len(contradiction_insights) == 1
        assert contradiction_insights[0].severity == "action_required"

    def test_no_contradiction_same_polarity(self) -> None:
        proj = _FakeProjections(memory_entries={
            "e1": {
                "workspace_id": "ws1",
                "status": "verified",
                "conf_alpha": 10.0,
                "conf_beta": 3.0,
                "polarity": "positive",
                "domains": ["testing"],
                "title": "Use mocks",
            },
            "e2": {
                "workspace_id": "ws1",
                "status": "verified",
                "conf_alpha": 12.0,
                "conf_beta": 4.0,
                "polarity": "positive",
                "domains": ["testing"],
                "title": "Use stubs",
            },
        })
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        contradiction_insights = [
            i for i in briefing.insights if i.category == "contradiction"
        ]
        assert len(contradiction_insights) == 0


class TestCoverageGap:
    """Rule 4: coverage gap detection via prediction errors."""

    def test_coverage_gap_detected(self) -> None:
        proj = _FakeProjections(memory_entries={
            "e1": {
                "workspace_id": "ws1",
                "prediction_error_count": 5,
                "domains": ["docker"],
            },
            "e2": {
                "workspace_id": "ws1",
                "prediction_error_count": 4,
                "domains": ["docker"],
            },
            "e3": {
                "workspace_id": "ws1",
                "prediction_error_count": 3,
                "domains": ["docker"],
            },
        })
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        coverage_insights = [
            i for i in briefing.insights if i.category == "coverage"
        ]
        assert len(coverage_insights) == 1
        assert coverage_insights[0].severity == "attention"  # 3+ entries


class TestStaleCluster:
    """Rule 5: stale co-occurrence cluster."""

    def test_stale_cluster_detected(self) -> None:
        proj = _FakeProjections(
            memory_entries={
                "e1": {
                    "workspace_id": "ws1",
                    "prediction_error_count": 5,
                    "domains": ["auth"],
                },
                "e2": {
                    "workspace_id": "ws1",
                    "prediction_error_count": 4,
                    "domains": ["auth"],
                },
            },
            cooccurrence_weights={
                ("e1", "e2"): _FakeCooccurrence(weight=2.0),
            },
        )
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        stale_insights = [
            i for i in briefing.insights if i.category == "staleness"
        ]
        assert len(stale_insights) == 1


class TestMergeOpportunity:
    """Rule 6: merge opportunity detection."""

    def test_merge_detected(self) -> None:
        proj = _FakeProjections(memory_entries={
            "e1": {
                "workspace_id": "ws1",
                "title": "Python async testing patterns",
                "domains": ["python", "testing"],
            },
            "e2": {
                "workspace_id": "ws1",
                "title": "Python async testing best practices",
                "domains": ["python", "testing"],
            },
        })
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        merge_insights = [
            i for i in briefing.insights if i.category == "merge"
        ]
        assert len(merge_insights) == 1
        assert merge_insights[0].severity == "info"


class TestFederationInbound:
    """Rule 7: federation inbound knowledge."""

    def test_inbound_detected(self) -> None:
        proj = _FakeProjections(memory_entries={
            "e1": {
                "workspace_id": "ws1",
                "source_peer": "peer-42",
                "domains": ["kubernetes"],
                "title": "K8s patterns",
            },
        })
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        inbound_insights = [
            i for i in briefing.insights if i.category == "inbound"
        ]
        assert len(inbound_insights) == 1

    def test_no_inbound_when_local_exists(self) -> None:
        proj = _FakeProjections(memory_entries={
            "e1": {
                "workspace_id": "ws1",
                "source_peer": "peer-42",
                "domains": ["python"],
                "title": "Python patterns",
            },
            "e2": {
                "workspace_id": "ws1",
                "domains": ["python"],
                "title": "Local python knowledge",
            },
        })
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        inbound_insights = [
            i for i in briefing.insights if i.category == "inbound"
        ]
        assert len(inbound_insights) == 0


class TestBriefingGeneral:
    """General briefing behavior tests."""

    def test_sorted_by_severity(self) -> None:
        """action_required comes before attention comes before info."""
        proj = _FakeProjections(memory_entries={
            # Contradiction (action_required)
            "e1": {
                "workspace_id": "ws1",
                "status": "verified",
                "conf_alpha": 10.0,
                "conf_beta": 3.0,
                "polarity": "positive",
                "domains": ["testing"],
                "title": "Use mocks",
            },
            "e2": {
                "workspace_id": "ws1",
                "status": "verified",
                "conf_alpha": 12.0,
                "conf_beta": 4.0,
                "polarity": "negative",
                "domains": ["testing"],
                "title": "Avoid mocks",
            },
            # Inbound (info)
            "e3": {
                "workspace_id": "ws1",
                "source_peer": "peer-1",
                "domains": ["kubernetes"],
                "title": "K8s",
            },
        })
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        assert len(briefing.insights) >= 2
        # action_required should come first
        assert briefing.insights[0].severity == "action_required"

    def test_empty_workspace(self) -> None:
        proj = _FakeProjections()
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        assert briefing.total_entries == 0
        assert briefing.insights == []
        assert briefing.avg_confidence == 0.0

    def test_stats_computed(self) -> None:
        proj = _FakeProjections(memory_entries={
            "e1": {
                "workspace_id": "ws1",
                "status": "candidate",
                "conf_alpha": 10.0,
                "conf_beta": 5.0,
            },
            "e2": {
                "workspace_id": "ws1",
                "status": "verified",
                "conf_alpha": 20.0,
                "conf_beta": 3.0,
            },
        })
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        assert briefing.total_entries == 2
        assert briefing.entries_by_status["candidate"] == 1
        assert briefing.entries_by_status["verified"] == 1
        assert 0.0 < briefing.avg_confidence < 1.0

    def test_workspace_filtering(self) -> None:
        """Only entries from the requested workspace are included."""
        proj = _FakeProjections(memory_entries={
            "e1": {"workspace_id": "ws1", "status": "candidate"},
            "e2": {"workspace_id": "ws2", "status": "candidate"},
        })
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        assert briefing.total_entries == 1


class TestKnowledgeFeedbackCasteConfig:
    """B7: Verify knowledge_feedback tool in caste tool lists."""

    def test_knowledge_feedback_in_worker_castes(self) -> None:
        import yaml
        data = yaml.safe_load(open("config/caste_recipes.yaml"))
        for caste in ("coder", "reviewer", "researcher"):
            tools = data["castes"][caste]["tools"]
            assert "knowledge_feedback" in tools, (
                f"knowledge_feedback missing from {caste}"
            )

    def test_knowledge_feedback_not_in_archivist(self) -> None:
        import yaml
        data = yaml.safe_load(open("config/caste_recipes.yaml"))
        tools = data["castes"]["archivist"]["tools"]
        assert "knowledge_feedback" not in tools


# ---------------------------------------------------------------------------
# Wave 34.5 Team 2: SuggestedColony tests
# ---------------------------------------------------------------------------


class TestSuggestedColony:
    """Verify suggested_colony populated on exactly 3 of 7 rules."""

    def test_contradiction_has_suggested_colony(self) -> None:
        proj = _FakeProjections(memory_entries={
            "e1": {
                "workspace_id": "ws1",
                "status": "verified",
                "conf_alpha": 10.0,
                "conf_beta": 3.0,
                "polarity": "positive",
                "domains": ["testing", "python"],
                "title": "Use mocks",
            },
            "e2": {
                "workspace_id": "ws1",
                "status": "verified",
                "conf_alpha": 12.0,
                "conf_beta": 4.0,
                "polarity": "negative",
                "domains": ["testing", "python"],
                "title": "Avoid mocks",
            },
        })
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        contradiction = [
            i for i in briefing.insights if i.category == "contradiction"
        ]
        assert len(contradiction) == 1
        sc = contradiction[0].suggested_colony
        assert sc is not None
        assert sc.caste == "researcher"
        assert sc.strategy == "sequential"
        assert "Use mocks" in sc.task
        assert "Avoid mocks" in sc.task

    def test_coverage_gap_has_suggested_colony(self) -> None:
        proj = _FakeProjections(memory_entries={
            "e1": {
                "workspace_id": "ws1",
                "prediction_error_count": 5,
                "domains": ["docker"],
            },
            "e2": {
                "workspace_id": "ws1",
                "prediction_error_count": 4,
                "domains": ["docker"],
            },
            "e3": {
                "workspace_id": "ws1",
                "prediction_error_count": 3,
                "domains": ["docker"],
            },
        })
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        coverage = [
            i for i in briefing.insights if i.category == "coverage"
        ]
        assert len(coverage) == 1
        sc = coverage[0].suggested_colony
        assert sc is not None
        assert sc.caste == "researcher"
        assert "docker" in sc.task

    def test_stale_cluster_has_suggested_colony(self) -> None:
        proj = _FakeProjections(
            memory_entries={
                "e1": {
                    "workspace_id": "ws1",
                    "prediction_error_count": 5,
                    "domains": ["auth"],
                },
                "e2": {
                    "workspace_id": "ws1",
                    "prediction_error_count": 4,
                    "domains": ["auth"],
                },
            },
            cooccurrence_weights={
                ("e1", "e2"): _FakeCooccurrence(weight=2.0),
            },
        )
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        stale = [
            i for i in briefing.insights if i.category == "staleness"
        ]
        assert len(stale) == 1
        sc = stale[0].suggested_colony
        assert sc is not None
        assert sc.caste == "researcher"
        assert "auth" in sc.task

    def test_confidence_decline_no_suggested_colony(self) -> None:
        proj = _FakeProjections(memory_entries={
            "e1": {
                "workspace_id": "ws1",
                "conf_alpha": 8.0,
                "conf_beta": 5.0,
                "peak_alpha": 15.0,
                "title": "Testing patterns",
                "last_confidence_update": _recent_iso(),
            },
        })
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        confidence = [
            i for i in briefing.insights if i.category == "confidence"
        ]
        assert len(confidence) == 1
        assert confidence[0].suggested_colony is None

    def test_merge_no_suggested_colony(self) -> None:
        proj = _FakeProjections(memory_entries={
            "e1": {
                "workspace_id": "ws1",
                "title": "Python async testing patterns",
                "domains": ["python", "testing"],
            },
            "e2": {
                "workspace_id": "ws1",
                "title": "Python async testing best practices",
                "domains": ["python", "testing"],
            },
        })
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        merge = [
            i for i in briefing.insights if i.category == "merge"
        ]
        assert len(merge) == 1
        assert merge[0].suggested_colony is None

    def test_inbound_no_suggested_colony(self) -> None:
        proj = _FakeProjections(memory_entries={
            "e1": {
                "workspace_id": "ws1",
                "source_peer": "peer-42",
                "domains": ["kubernetes"],
                "title": "K8s patterns",
            },
        })
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        inbound = [
            i for i in briefing.insights if i.category == "inbound"
        ]
        assert len(inbound) == 1
        assert inbound[0].suggested_colony is None


class TestDistillationCandidates:
    """Verify distillation_candidates count in briefing."""

    def test_zero_when_no_candidates(self) -> None:
        proj = _FakeProjections()
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        assert briefing.distillation_candidates == 0

    def test_count_from_projections(self) -> None:
        proj = _FakeProjections()
        # Simulate maintenance loop having set distillation_candidates
        proj.distillation_candidates = [["e1", "e2", "e3", "e4", "e5"]]  # type: ignore[attr-defined]
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        assert briefing.distillation_candidates == 1


# ---------------------------------------------------------------------------
# Wave 58.5: Popular but unexamined rule
# ---------------------------------------------------------------------------


class TestPopularUnexamined:
    """Verify rule 15: popular-but-unexamined entry detection."""

    def test_popular_unexamined_fires(self) -> None:
        """Entry with access_count >= 5 and low confidence triggers insight."""
        proj = _FakeProjections(
            memory_entries={
                "e1": {
                    "workspace_id": "ws1",
                    "status": "verified",
                    "title": "Vague pattern",
                    "conf_alpha": 5.5,
                    "conf_beta": 5.0,
                },
            },
            knowledge_entry_usage={
                "e1": {"count": 7, "last_accessed": _now_iso()},
            },
        )
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        popular = [i for i in briefing.insights if i.category == "popular_unexamined"]
        assert len(popular) == 1
        assert "e1" in popular[0].affected_entries
        assert "7 times" in popular[0].detail

    def test_popular_unexamined_skips_high_conf(self) -> None:
        """Entry with high confidence (>= 0.65) should not trigger."""
        proj = _FakeProjections(
            memory_entries={
                "e1": {
                    "workspace_id": "ws1",
                    "status": "verified",
                    "title": "Strong pattern",
                    "conf_alpha": 10.0,
                    "conf_beta": 5.0,  # confidence = 10/15 = 0.667
                },
            },
            knowledge_entry_usage={
                "e1": {"count": 7, "last_accessed": _now_iso()},
            },
        )
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        popular = [i for i in briefing.insights if i.category == "popular_unexamined"]
        assert len(popular) == 0

    def test_popular_unexamined_skips_low_access(self) -> None:
        """Entry with access_count < 5 should not trigger."""
        proj = _FakeProjections(
            memory_entries={
                "e1": {
                    "workspace_id": "ws1",
                    "status": "verified",
                    "title": "Rarely used",
                    "conf_alpha": 5.0,
                    "conf_beta": 5.0,
                },
            },
            knowledge_entry_usage={
                "e1": {"count": 2, "last_accessed": _now_iso()},
            },
        )
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        popular = [i for i in briefing.insights if i.category == "popular_unexamined"]
        assert len(popular) == 0
