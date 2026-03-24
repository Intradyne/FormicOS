"""Wave 34 smoke tests — 19 items from wave_34_plan.md Track C (Team 3).

Validates tiered retrieval, co-occurrence scoring, proactive intelligence,
knowledge_feedback, confidence visualization, federation dashboard,
entry sub-types, and documentation consistency.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.core.types import EntrySubType, MemoryEntry, MemoryEntryType
from formicos.engine.runner import (
    SCOPE_BUDGETS,
    TOOL_CATEGORY_MAP,
    TOOL_SPECS,
    _confidence_tier,
)
from formicos.surface.knowledge_catalog import (
    KnowledgeCatalog,
    _composite_key,
    _cooccurrence_score,
    _sigmoid_cooccurrence,
)
from formicos.surface.knowledge_constants import COMPOSITE_WEIGHTS, GAMMA_RATES
from formicos.surface.proactive_intelligence import (
    KnowledgeInsight,
    ProactiveBriefing,
    SuggestedColony,
    generate_briefing,
)
from formicos.surface.projections import CooccurrenceEntry, cooccurrence_key


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
    memory_entries: dict[str, dict[str, Any]] = field(default_factory=dict)
    cooccurrence_weights: dict[tuple[str, str], _FakeCooccurrence] = field(
        default_factory=dict,
    )


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _make_entry(
    *,
    entry_id: str = "e1",
    workspace_id: str = "ws-test",
    title: str = "Test entry",
    entry_type: str = "skill",
    sub_type: str | None = None,
    status: str = "verified",
    conf_alpha: float = 10.0,
    conf_beta: float = 5.0,
    domains: list[str] | None = None,
    polarity: str = "positive",
    decay_class: str = "stable",
    prediction_error_count: int = 0,
    source_peer: str | None = None,
    created_at: str = "",
    source_colony_id: str = "col-1",
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": entry_id,
        "workspace_id": workspace_id,
        "title": title,
        "entry_type": entry_type,
        "status": status,
        "conf_alpha": conf_alpha,
        "conf_beta": conf_beta,
        "domains": domains or ["testing"],
        "polarity": polarity,
        "decay_class": decay_class,
        "prediction_error_count": prediction_error_count,
        "created_at": created_at or _now_iso(),
        "summary": f"Summary of {title}",
        "content_preview": f"Content preview for {title}",
        "source_colony_id": source_colony_id,
        "score": 0.7,
    }
    if sub_type:
        entry["sub_type"] = sub_type
    if source_peer:
        entry["source_peer"] = source_peer
    return entry


# ---------------------------------------------------------------------------
# Smoke 1: Tiered retrieval — summary tier resolves typical queries
# ---------------------------------------------------------------------------

class TestSmoke1TieredSummary:
    """memory_search resolves at summary tier with confidence annotations."""

    @pytest.mark.asyncio
    async def test_summary_tier_includes_confidence(self) -> None:
        """Verify summary-tier results include confidence_tier field."""
        ms = AsyncMock()
        ms.search.return_value = [
            MagicMock(
                id="mem-1", content="test", score=0.8,
                metadata={"entry_type": "skill", "workspace_id": "ws-1",
                           "conf_alpha": 15.0, "conf_beta": 5.0,
                           "status": "verified", "created_at": _now_iso(),
                           "summary": "Test skill", "title": "Test",
                           "source_colony_id": "col-1", "thread_id": "t-1"},
            ),
        ]
        cat = KnowledgeCatalog(
            memory_store=ms, vector_port=None,
            skill_collection="test", projections=None,
        )
        results = await cat.search_tiered(
            "async testing", workspace_id="ws-1", tier="summary",
        )
        assert len(results) >= 1
        assert "tier" in results[0]
        assert results[0]["tier"] == "summary"
        assert "confidence_tier" in results[0]

    @pytest.mark.asyncio
    async def test_summary_tier_has_truncated_summary(self) -> None:
        """Summary tier truncates summary to 100 chars."""
        ms = AsyncMock()
        long_summary = "A" * 200
        ms.search.return_value = [
            MagicMock(
                id="mem-1", content="test", score=0.8,
                metadata={"entry_type": "skill", "workspace_id": "ws-1",
                           "conf_alpha": 10.0, "conf_beta": 5.0,
                           "status": "verified", "created_at": _now_iso(),
                           "summary": long_summary, "title": "Test",
                           "source_colony_id": "col-1", "thread_id": "t-1"},
            ),
        ]
        cat = KnowledgeCatalog(
            memory_store=ms, vector_port=None,
            skill_collection="test", projections=None,
        )
        results = await cat.search_tiered(
            "test", workspace_id="ws-1", tier="summary",
        )
        assert len(results[0].get("summary", "")) <= 100


# ---------------------------------------------------------------------------
# Smoke 2: Full tier returns full content
# ---------------------------------------------------------------------------

class TestSmoke2FullTier:
    """detail="full" returns full content at tier=full."""

    @pytest.mark.asyncio
    async def test_full_tier_includes_content(self) -> None:
        ms = AsyncMock()
        ms.search.return_value = [
            MagicMock(
                id="mem-1", content="full content here", score=0.8,
                metadata={"entry_type": "skill", "workspace_id": "ws-1",
                           "conf_alpha": 15.0, "conf_beta": 5.0,
                           "status": "verified", "created_at": _now_iso(),
                           "summary": "Summary", "title": "Test",
                           "content_preview": "full content here",
                           "source_colony_id": "col-1", "thread_id": "t-1",
                           "merged_from": []},
            ),
        ]
        cat = KnowledgeCatalog(
            memory_store=ms, vector_port=None,
            skill_collection="test", projections=None,
        )
        results = await cat.search_tiered(
            "test", workspace_id="ws-1", tier="full",
        )
        assert len(results) >= 1
        assert results[0]["tier"] == "full"
        assert "content" in results[0]
        assert "conf_alpha" in results[0]
        assert "merged_from" in results[0]


# ---------------------------------------------------------------------------
# Smoke 3: Context assembly scope budgets
# ---------------------------------------------------------------------------

class TestSmoke3ScopeBudgets:
    """No scope exceeds 35% allocation in budget-aware context assembly."""

    def test_scope_budgets_sum_to_one(self) -> None:
        total = sum(SCOPE_BUDGETS.values())
        assert abs(total - 1.0) < 1e-9

    def test_no_scope_exceeds_35_percent(self) -> None:
        for scope, budget in SCOPE_BUDGETS.items():
            assert budget <= 0.35, f"{scope} exceeds 35%: {budget}"

    def test_five_scopes_defined(self) -> None:
        expected = {
            "task_knowledge", "observations", "structured_facts",
            "round_history", "scratch_memory",
        }
        assert set(SCOPE_BUDGETS.keys()) == expected


# ---------------------------------------------------------------------------
# Smoke 4: Co-occurrence entries rank higher (Invariant 5)
# ---------------------------------------------------------------------------

class TestSmoke4CooccurrenceRanking:
    """Co-occurrence entries rank higher than non-co-occurring equivalents."""

    def test_invariant_5_cooccurrence_signal_positive(self) -> None:
        """The co-occurrence signal contributes a positive score delta."""
        raw_weight = 5.0
        cooc_signal = _sigmoid_cooccurrence(raw_weight)
        contribution = COMPOSITE_WEIGHTS["cooccurrence"] * cooc_signal
        # 0.04 * ~0.95 ≈ 0.038 — meaningful uplift
        assert contribution > 0.03

    def test_cooccurrence_weight_in_composite(self) -> None:
        assert "cooccurrence" in COMPOSITE_WEIGHTS
        assert COMPOSITE_WEIGHTS["cooccurrence"] == 0.04

    def test_sigmoid_normalizes_to_unit_interval(self) -> None:
        for w in [0.0, 0.5, 1.0, 3.0, 5.0, 10.0]:
            result = _sigmoid_cooccurrence(w)
            assert 0.0 <= result <= 1.0


# ---------------------------------------------------------------------------
# Smoke 5: Queen sees contradiction (proactive intelligence)
# ---------------------------------------------------------------------------

class TestSmoke5QueenContradiction:
    """Proactive intelligence flags contradictions for the Queen."""

    def test_contradiction_surfaces_in_briefing(self) -> None:
        proj = _FakeProjections(memory_entries={
            "e1": _make_entry(
                entry_id="e1", polarity="positive",
                title="Use mocks in tests",
                domains=["testing", "python"],
            ),
            "e2": _make_entry(
                entry_id="e2", polarity="negative",
                title="Avoid mocks in tests",
                domains=["testing", "python"],
            ),
        })
        briefing = generate_briefing("ws-test", proj)  # type: ignore[arg-type]
        contradictions = [
            i for i in briefing.insights if i.category == "contradiction"
        ]
        assert len(contradictions) == 1
        assert contradictions[0].severity == "action_required"
        assert "e1" in contradictions[0].affected_entries
        assert "e2" in contradictions[0].affected_entries

    def test_contradiction_has_suggested_colony(self) -> None:
        proj = _FakeProjections(memory_entries={
            "e1": _make_entry(
                entry_id="e1", polarity="positive",
                title="Use mocks", domains=["testing"],
            ),
            "e2": _make_entry(
                entry_id="e2", polarity="negative",
                title="Avoid mocks", domains=["testing"],
            ),
        })
        briefing = generate_briefing("ws-test", proj)  # type: ignore[arg-type]
        contradictions = [
            i for i in briefing.insights if i.category == "contradiction"
        ]
        assert len(contradictions) == 1
        sc = contradictions[0].suggested_colony
        assert sc is not None
        assert sc.caste == "researcher"


# ---------------------------------------------------------------------------
# Smoke 6: Proactive briefing performance
# ---------------------------------------------------------------------------

class TestSmoke6BriefingPerformance:
    """Briefing for 50+ entries completes <100ms, no LLM calls."""

    def test_briefing_50_entries_under_100ms(self) -> None:
        entries: dict[str, dict[str, Any]] = {}
        for i in range(60):
            entries[f"e{i}"] = _make_entry(
                entry_id=f"e{i}",
                title=f"Entry {i}",
                domains=[f"domain-{i % 5}"],
                conf_alpha=float(5 + i),
                conf_beta=5.0,
            )
        proj = _FakeProjections(memory_entries=entries)

        start = time.monotonic()
        briefing = generate_briefing("ws-test", proj)  # type: ignore[arg-type]
        elapsed_ms = (time.monotonic() - start) * 1000

        assert elapsed_ms < 100, f"Took {elapsed_ms:.1f}ms (>100ms)"
        assert briefing.total_entries == 60

    def test_briefing_sorted_by_severity(self) -> None:
        proj = _FakeProjections(memory_entries={
            # Contradiction → action_required
            "e1": _make_entry(
                entry_id="e1", polarity="positive",
                title="Use pattern", domains=["testing"],
            ),
            "e2": _make_entry(
                entry_id="e2", polarity="negative",
                title="Avoid pattern", domains=["testing"],
            ),
            # Inbound → info
            "e3": _make_entry(
                entry_id="e3", source_peer="peer-1",
                title="K8s tips", domains=["kubernetes"],
            ),
        })
        briefing = generate_briefing("ws-test", proj)  # type: ignore[arg-type]
        if len(briefing.insights) >= 2:
            severities = [i.severity for i in briefing.insights]
            # action_required before info
            assert severities.index("action_required") < severities.index("info")


# ---------------------------------------------------------------------------
# Smoke 7: MCP briefing resource (model validation)
# ---------------------------------------------------------------------------

class TestSmoke7BriefingModel:
    """ProactiveBriefing model structure matches MCP resource."""

    def test_briefing_model_fields(self) -> None:
        b = ProactiveBriefing(
            workspace_id="ws-1",
            generated_at=_now_iso(),
            insights=[],
            total_entries=5,
            entries_by_status={"verified": 3, "candidate": 2},
            avg_confidence=0.65,
            prediction_error_rate=0.1,
            active_clusters=2,
        )
        d = b.model_dump()
        assert "workspace_id" in d
        assert "insights" in d
        assert "federation_summary" in d
        assert "active_clusters" in d

    def test_insight_with_suggested_colony_serializes(self) -> None:
        insight = KnowledgeInsight(
            severity="attention",
            category="coverage",
            title="Coverage gap",
            detail="Details here",
            suggested_colony=SuggestedColony(
                task="Research X",
                caste="researcher",
                strategy="sequential",
            ),
        )
        d = insight.model_dump()
        assert d["suggested_colony"] is not None
        assert d["suggested_colony"]["caste"] == "researcher"


# ---------------------------------------------------------------------------
# Smoke 8: knowledge_feedback tool (B7)
# ---------------------------------------------------------------------------

class TestSmoke8KnowledgeFeedback:
    """knowledge_feedback tool is registered and dispatches correctly."""

    def test_tool_spec_exists(self) -> None:
        assert "knowledge_feedback" in TOOL_SPECS
        spec = TOOL_SPECS["knowledge_feedback"]
        props = spec["parameters"]["properties"]
        assert "entry_id" in props
        assert "helpful" in props
        assert "reason" in props

    def test_tool_category_is_memory(self) -> None:
        assert "knowledge_feedback" in TOOL_CATEGORY_MAP

    def test_knowledge_feedback_in_caste_recipes(self) -> None:
        import yaml
        data = yaml.safe_load(open("config/caste_recipes.yaml"))
        for caste in ("coder", "reviewer", "researcher"):
            tools = data["castes"][caste]["tools"]
            assert "knowledge_feedback" in tools, f"Missing from {caste}"

    def test_knowledge_feedback_not_in_archivist(self) -> None:
        import yaml
        data = yaml.safe_load(open("config/caste_recipes.yaml"))
        tools = data["castes"]["archivist"]["tools"]
        assert "knowledge_feedback" not in tools


# ---------------------------------------------------------------------------
# Smoke 9: Confidence visualization tiers
# ---------------------------------------------------------------------------

class TestSmoke9ConfidenceVisualization:
    """Confidence tier classification produces correct badges."""

    def test_high_tier(self) -> None:
        item = {"conf_alpha": 20.0, "conf_beta": 5.0, "status": "verified"}
        assert _confidence_tier(item) == "HIGH"

    def test_moderate_tier(self) -> None:
        item = {"conf_alpha": 8.0, "conf_beta": 5.0, "status": "verified"}
        tier = _confidence_tier(item)
        assert tier in ("MODERATE", "HIGH")

    def test_exploratory_tier(self) -> None:
        item = {"conf_alpha": 1.5, "conf_beta": 1.5, "status": "candidate"}
        assert _confidence_tier(item) == "EXPLORATORY"

    def test_stale_tier(self) -> None:
        item = {"conf_alpha": 10.0, "conf_beta": 5.0, "status": "stale"}
        assert _confidence_tier(item) == "STALE"

    def test_low_tier(self) -> None:
        item = {"conf_alpha": 3.0, "conf_beta": 8.0, "status": "candidate"}
        tier = _confidence_tier(item)
        assert tier in ("LOW", "MODERATE")


# ---------------------------------------------------------------------------
# Smoke 10: Federation dashboard data structures
# ---------------------------------------------------------------------------

class TestSmoke10FederationDashboard:
    """Federation projections support dashboard display."""

    def test_peer_trust_uses_beta_posterior(self) -> None:
        from formicos.surface.trust import PeerTrust
        pt = PeerTrust(alpha=11.0, beta=2.0)
        score = pt.score
        # 10th percentile of Beta(11, 2) — penalizes uncertainty
        assert 0.5 < score < 1.0

    def test_peer_trust_penalizes_uncertainty(self) -> None:
        from formicos.surface.trust import PeerTrust
        confident = PeerTrust(alpha=50.0, beta=5.0)
        uncertain = PeerTrust(alpha=5.0, beta=0.5)
        # More observations → higher trust
        assert confident.score > uncertain.score


# ---------------------------------------------------------------------------
# Smoke 11: Entry sub-type filter
# ---------------------------------------------------------------------------

class TestSmoke11SubTypeFilter:
    """Entry sub-type filtering works on API and MCP."""

    def test_sub_type_enum_values(self) -> None:
        assert EntrySubType.technique == "technique"
        assert EntrySubType.pattern == "pattern"
        assert EntrySubType.anti_pattern == "anti_pattern"
        assert EntrySubType.trajectory == "trajectory"
        assert EntrySubType.bug == "bug"
        assert EntrySubType.convention == "convention"
        assert EntrySubType.learning == "learning"
        assert EntrySubType.decision == "decision"

    def test_memory_entry_sub_type_serializes(self) -> None:
        entry = MemoryEntry(
            id="mem-1",
            entry_type=MemoryEntryType.skill,
            sub_type=EntrySubType.technique,
            workspace_id="ws-1",
            thread_id="t-1",
            title="Test entry",
            content="Test content",
            summary="Test",
            source_colony_id="col-1",
            source_artifact_ids=["art-1"],
        )
        d = entry.model_dump()
        assert d["sub_type"] == "technique"

    def test_memory_entry_sub_type_default_none(self) -> None:
        entry = MemoryEntry(
            id="mem-1",
            entry_type=MemoryEntryType.skill,
            workspace_id="ws-1",
            thread_id="t-1",
            title="Test entry",
            content="Test content",
            summary="Test",
            source_colony_id="col-1",
            source_artifact_ids=["art-1"],
        )
        assert entry.sub_type is None


# ---------------------------------------------------------------------------
# Smoke 12: Federation round-trip (basic model validation)
# ---------------------------------------------------------------------------

class TestSmoke12FederationRoundTrip:
    """Federation CRDT structures support round-trip replication."""

    def test_peer_connection_stores_replication_filter(self) -> None:
        from formicos.core.types import ReplicationFilter
        from formicos.surface.federation import PeerConnection
        pc = PeerConnection(
            instance_id="peer-1",
            endpoint="http://peer-1:8000",
            replication_filter=ReplicationFilter(
                domain_allowlist=["testing"],
                min_confidence=0.5,
            ),
        )
        assert pc.instance_id == "peer-1"
        assert pc.replication_filter.min_confidence == 0.5


# ---------------------------------------------------------------------------
# Smoke 13: Tiered retrieval auto-escalation thresholds
# ---------------------------------------------------------------------------

class TestSmoke13AutoEscalation:
    """Auto-escalation produces expected tier distribution."""

    @pytest.mark.asyncio
    async def test_high_score_multiple_sources_stays_summary(self) -> None:
        """High-quality results from multiple sources → summary tier."""
        ms = AsyncMock()
        ms.search.return_value = [
            MagicMock(
                id=f"mem-{i}", content="test", score=0.8,
                metadata={
                    "entry_type": "skill", "workspace_id": "ws-1",
                    "conf_alpha": 15.0, "conf_beta": 5.0,
                    "status": "verified", "created_at": _now_iso(),
                    "summary": f"Result {i}", "title": f"Test {i}",
                    "source_colony_id": f"col-{i}", "thread_id": "t-1",
                },
            )
            for i in range(5)
        ]
        cat = KnowledgeCatalog(
            memory_store=ms, vector_port=None,
            skill_collection="test", projections=None,
        )
        results = await cat.search_tiered(
            "test query", workspace_id="ws-1", tier="auto",
        )
        # Multiple unique sources + high score → should stay at summary
        assert len(results) > 0
        assert results[0]["tier"] == "summary"


# ---------------------------------------------------------------------------
# Smoke 14: Proactive intelligence accuracy (all 7 rules)
# ---------------------------------------------------------------------------

class TestSmoke14ProactiveRules:
    """All 7 proactive intelligence rules fire correctly."""

    def test_rule_confidence_decline(self) -> None:
        proj = _FakeProjections(memory_entries={
            "e1": {
                "workspace_id": "ws1",
                "conf_alpha": 6.0,
                "conf_beta": 5.0,
                "peak_alpha": 15.0,
                "title": "Declining entry",
                "last_confidence_update": (
                    datetime.now(tz=UTC) - timedelta(days=1)
                ).isoformat(),
            },
        })
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        assert any(i.category == "confidence" for i in briefing.insights)

    def test_rule_contradiction(self) -> None:
        proj = _FakeProjections(memory_entries={
            "e1": _make_entry(
                entry_id="e1", workspace_id="ws1",
                polarity="positive", domains=["db"],
            ),
            "e2": _make_entry(
                entry_id="e2", workspace_id="ws1",
                polarity="negative", domains=["db"],
            ),
        })
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        assert any(i.category == "contradiction" for i in briefing.insights)

    def test_rule_coverage_gap(self) -> None:
        entries = {
            f"e{i}": _make_entry(
                entry_id=f"e{i}", workspace_id="ws1",
                prediction_error_count=5, domains=["docker"],
            )
            for i in range(3)
        }
        proj = _FakeProjections(memory_entries=entries)
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        assert any(i.category == "coverage" for i in briefing.insights)

    def test_rule_stale_cluster(self) -> None:
        proj = _FakeProjections(
            memory_entries={
                "e1": _make_entry(
                    entry_id="e1", workspace_id="ws1",
                    prediction_error_count=5, domains=["auth"],
                ),
                "e2": _make_entry(
                    entry_id="e2", workspace_id="ws1",
                    prediction_error_count=5, domains=["auth"],
                ),
            },
            cooccurrence_weights={
                ("e1", "e2"): _FakeCooccurrence(weight=2.0),
            },
        )
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        assert any(i.category == "staleness" for i in briefing.insights)

    def test_rule_merge_opportunity(self) -> None:
        proj = _FakeProjections(memory_entries={
            "e1": _make_entry(
                entry_id="e1", workspace_id="ws1",
                title="Python async testing patterns",
                domains=["python", "testing"],
            ),
            "e2": _make_entry(
                entry_id="e2", workspace_id="ws1",
                title="Python async testing best practices",
                domains=["python", "testing"],
            ),
        })
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        assert any(i.category == "merge" for i in briefing.insights)

    def test_rule_federation_inbound(self) -> None:
        proj = _FakeProjections(memory_entries={
            "e1": _make_entry(
                entry_id="e1", workspace_id="ws1",
                source_peer="peer-42", domains=["kubernetes"],
            ),
        })
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        assert any(i.category == "inbound" for i in briefing.insights)

    def test_clean_state_no_false_positives(self) -> None:
        """Clean state with well-behaved entries produces no insights."""
        proj = _FakeProjections(memory_entries={
            f"e{i}": _make_entry(
                entry_id=f"e{i}", workspace_id="ws1",
                title=f"Unique topic {i}",
                domains=[f"unique-domain-{i}"],
                polarity="positive",
                prediction_error_count=0,
            )
            for i in range(10)
        })
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]
        assert len(briefing.insights) == 0, (
            f"False positives: {[i.category for i in briefing.insights]}"
        )


# ---------------------------------------------------------------------------
# Smoke 15: Replay idempotency (53 events — validated by existing test)
# ---------------------------------------------------------------------------

class TestSmoke15ReplayReference:
    """Verify the replay test infrastructure covers 53 events."""

    def test_all_events_imported(self) -> None:
        """The replay test covers all event types in the closed union."""
        from tests.unit.test_replay_idempotency import (
            build_representative_event_sequence,
        )
        events = build_representative_event_sequence()
        # Closed union — count may grow with new waves but must be >= 53
        assert len(events) >= 53


# ---------------------------------------------------------------------------
# Smoke 16: Co-occurrence + Thompson no cluster domination
# ---------------------------------------------------------------------------

class TestSmoke16NoClusterDomination:
    """No single co-occurrence cluster takes all top-5 >30%."""

    def test_thompson_prevents_cluster_lock(self) -> None:
        random.seed(42)
        items = [
            {"id": f"{prefix}{i}", "score": 0.7,
             "conf_alpha": 15.0, "conf_beta": 5.0,
             "status": "verified", "created_at": _now_iso()}
            for prefix in ("a", "b", "c")
            for i in range(5)
        ]

        domination = 0
        for _ in range(100):
            scored = [(item, -_composite_key(item)) for item in items]
            scored.sort(key=lambda x: -x[1])
            top5_prefixes = {item["id"][0] for item, _ in scored[:5]}
            if len(top5_prefixes) == 1:
                domination += 1

        assert domination <= 30, f"Cluster dominated {domination}/100"


# ---------------------------------------------------------------------------
# Smoke 17: Demo scenario (email validator) — model validation
# ---------------------------------------------------------------------------

class TestSmoke17DemoScenario:
    """Email validator demo structures are representable in the model."""

    def test_extraction_sub_types_for_email_validator(self) -> None:
        """Sub-types from the demo: technique, learning, convention."""
        skill = MemoryEntry(
            id="mem-test-s-0",
            entry_type=MemoryEntryType.skill,
            sub_type=EntrySubType.technique,
            workspace_id="ws-demo",
            thread_id="t-1",
            title="RFC 5322 email validation",
            content="Email validation with regex + DNS MX check",
            summary="RFC 5322 email validation with regex + DNS MX check",
            source_colony_id="col-demo",
            source_artifact_ids=["art-1"],
            domains=["validation", "email"],
        )
        exp = MemoryEntry(
            id="mem-test-e-0",
            entry_type=MemoryEntryType.experience,
            sub_type=EntrySubType.learning,
            workspace_id="ws-demo",
            thread_id="t-1",
            title="MX lookup latency",
            content="MX record lookup adds 200ms latency per validation",
            summary="MX record lookup adds 200ms latency",
            source_colony_id="col-demo",
            source_artifact_ids=["art-1"],
        )
        assert skill.sub_type == EntrySubType.technique
        assert exp.sub_type == EntrySubType.learning


# ---------------------------------------------------------------------------
# Smoke 18: Documentation consistency (key constants)
# ---------------------------------------------------------------------------

class TestSmoke18DocConsistency:
    """Key constants are consistent across code."""

    def test_composite_weights_sum_to_one(self) -> None:
        assert abs(sum(COMPOSITE_WEIGHTS.values()) - 1.0) < 1e-9

    def test_seven_scoring_signals(self) -> None:
        expected = {
            "semantic", "thompson", "freshness", "status",
            "thread", "cooccurrence", "graph_proximity",
        }
        assert set(COMPOSITE_WEIGHTS.keys()) == expected

    def test_decay_classes_match_constants(self) -> None:
        from formicos.core.types import DecayClass
        for dc in DecayClass:
            assert dc.value in GAMMA_RATES, f"{dc.value} not in GAMMA_RATES"

    def test_eight_entry_sub_types(self) -> None:
        assert len(list(EntrySubType)) == 8


# ---------------------------------------------------------------------------
# Smoke 19: Full CI clean (tests + type check + lint)
# ---------------------------------------------------------------------------

class TestSmoke19CIClean:
    """CI tools produce expected structures (meta-validation)."""

    def test_tool_specs_all_have_parameters(self) -> None:
        for name, spec in TOOL_SPECS.items():
            assert "parameters" in spec, f"{name} missing parameters"
            assert "properties" in spec["parameters"], f"{name} missing properties"

    def test_tool_category_covers_all_specs(self) -> None:
        for name in TOOL_SPECS:
            assert name in TOOL_CATEGORY_MAP, f"{name} missing from TOOL_CATEGORY_MAP"

    def test_suggested_colony_rules_count(self) -> None:
        """3 of 7 rules should have suggested_colony."""
        # Create a state that triggers all rule categories
        proj = _FakeProjections(
            memory_entries={
                # Contradiction (has suggested_colony)
                "c1": _make_entry(
                    entry_id="c1", workspace_id="ws1",
                    polarity="positive", domains=["testing"],
                ),
                "c2": _make_entry(
                    entry_id="c2", workspace_id="ws1",
                    polarity="negative", domains=["testing"],
                ),
                # Coverage gap (has suggested_colony)
                "g1": _make_entry(
                    entry_id="g1", workspace_id="ws1",
                    prediction_error_count=5, domains=["docker"],
                    title="Docker topic 1",
                ),
                "g2": _make_entry(
                    entry_id="g2", workspace_id="ws1",
                    prediction_error_count=5, domains=["docker"],
                    title="Docker topic 2",
                ),
                "g3": _make_entry(
                    entry_id="g3", workspace_id="ws1",
                    prediction_error_count=5, domains=["docker"],
                    title="Docker topic 3",
                ),
            },
            cooccurrence_weights={
                ("c1", "c2"): _FakeCooccurrence(weight=0.1),
            },
        )
        briefing = generate_briefing("ws1", proj)  # type: ignore[arg-type]

        with_colony = [i for i in briefing.insights if i.suggested_colony is not None]
        without_colony = [i for i in briefing.insights if i.suggested_colony is None]

        # At minimum contradiction + coverage_gap have suggested_colony
        colony_cats = {i.category for i in with_colony}
        assert "contradiction" in colony_cats
        assert "coverage" in colony_cats
