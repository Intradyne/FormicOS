"""Unit tests for formicos.core.events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Union, get_args

import pytest
from pydantic import ValidationError

from formicos.core.events import (
    AddonLoaded,
    AddonUnloaded,
    AgentTurnCompleted,
    AgentTurnStarted,
    ApprovalDenied,
    ApprovalGranted,
    ApprovalRequested,
    CRDTCounterIncremented,
    CRDTRegisterAssigned,
    CRDTSetElementAdded,
    CRDTTimestampUpdated,
    CodeExecuted,
    ColonyChatMessage,
    ColonyCompleted,
    ColonyFailed,
    ColonyKilled,
    ColonyNamed,
    ColonyRedirected,
    ColonyServiceActivated,
    ColonySpawned,
    ColonyEscalated,
    ColonyTemplateCreated,
    ColonyTemplateUsed,
    ConfigSuggestionOverridden,
    ContextUpdated,
    DomainStrategyUpdated,
    ForageCycleCompleted,
    ForageRequested,
    ForagerDomainOverride,
    FormicOSEvent,
    QueenNoteSaved,
    KnowledgeAccessRecorded,
    KnowledgeDistilled,
    KnowledgeEdgeCreated,
    KnowledgeEntryAnnotated,
    KnowledgeEntryOperatorAction,
    KnowledgeEntityCreated,
    KnowledgeEntityMerged,
    DeterministicServiceRegistered,
    MemoryConfidenceUpdated,
    MemoryEntryCreated,
    MemoryEntryMerged,
    MemoryEntryRefined,
    MemoryEntryScopeChanged,
    MemoryEntryStatusChanged,
    MemoryExtractionCompleted,
    MergeCreated,
    ParallelPlanCreated,
    MergePruned,
    ModelAssignmentChanged,
    ModelRegistered,
    PhaseEntered,
    QueenMessage,
    RoundCompleted,
    RoundStarted,
    ServiceQueryResolved,
    ServiceQuerySent,
    ServiceTriggerFired,
    SkillConfidenceUpdated,
    SkillMerged,
    ThreadCreated,
    ThreadGoalSet,
    ThreadRenamed,
    ThreadStatusChanged,
    TokensConsumed,
    WorkflowStepCompleted,
    WorkflowStepDefined,
    WorkflowStepUpdated,
    WorkspaceConfigChanged,
    WorkspaceConfigSnapshot,
    WorkspaceCreated,
    deserialize,
    serialize,
)
from formicos.core.types import CasteSlot, InputSource, KnowledgeAccessItem, WorkflowStep

NOW = datetime.now(timezone.utc)
ADDR = "ws/th/col"
ENVELOPE = {"seq": 0, "timestamp": NOW, "address": ADDR}


def _make_config() -> WorkspaceConfigSnapshot:
    return WorkspaceConfigSnapshot(budget=10.0, strategy="stigmergic")


# Map of all 26 event types to sample instances
SAMPLE_EVENTS: dict[str, object] = {
    "WorkspaceCreated": WorkspaceCreated(
        **ENVELOPE, name="ws1", config=_make_config()
    ),
    "ThreadCreated": ThreadCreated(**ENVELOPE, workspace_id="ws1", name="th1"),
    "ThreadRenamed": ThreadRenamed(**ENVELOPE, workspace_id="ws1", thread_id="th1", new_name="renamed"),
    "ColonySpawned": ColonySpawned(
        **ENVELOPE,
        thread_id="th1",
        task="build it",
        castes=[CasteSlot(caste="coder")],
        model_assignments={"coder": "m1"},
        strategy="stigmergic",
        max_rounds=3,
        budget_limit=1.0,
    ),
    "ColonyCompleted": ColonyCompleted(
        **ENVELOPE, colony_id="col1", summary="done", skills_extracted=2
    ),
    "ColonyFailed": ColonyFailed(**ENVELOPE, colony_id="col1", reason="timeout"),
    "ColonyKilled": ColonyKilled(
        **ENVELOPE, colony_id="col1", killed_by="operator"
    ),
    "RoundStarted": RoundStarted(**ENVELOPE, colony_id="col1", round_number=1),
    "PhaseEntered": PhaseEntered(
        **ENVELOPE, colony_id="col1", round_number=1, phase="goal"
    ),
    "AgentTurnStarted": AgentTurnStarted(
        **ENVELOPE,
        colony_id="col1",
        round_number=1,
        agent_id="a1",
        caste="coder",
        model="m1",
    ),
    "AgentTurnCompleted": AgentTurnCompleted(
        **ENVELOPE,
        agent_id="a1",
        output_summary="wrote code",
        input_tokens=100,
        output_tokens=50,
        tool_calls=["read_file"],
        duration_ms=1200,
    ),
    "RoundCompleted": RoundCompleted(
        **ENVELOPE,
        colony_id="col1",
        round_number=1,
        convergence=0.8,
        cost=0.05,
        duration_ms=5000,
    ),
    "MergeCreated": MergeCreated(
        **ENVELOPE,
        edge_id="e1",
        from_colony="col1",
        to_colony="col2",
        created_by="queen",
    ),
    "MergePruned": MergePruned(**ENVELOPE, edge_id="e1", pruned_by="queen"),
    "ContextUpdated": ContextUpdated(
        **ENVELOPE, key="status", value="active", operation="set"
    ),
    "WorkspaceConfigChanged": WorkspaceConfigChanged(
        **ENVELOPE,
        workspace_id="ws1",
        field="budget",
        old_value="10.0",
        new_value="20.0",
    ),
    "ModelRegistered": ModelRegistered(
        **ENVELOPE,
        provider_prefix="anthropic",
        model_name="claude-3",
        context_window=200000,
        supports_tools=True,
    ),
    "ModelAssignmentChanged": ModelAssignmentChanged(
        **ENVELOPE,
        scope="system",
        caste="coder",
        old_model="m1",
        new_model="m2",
    ),
    "ApprovalRequested": ApprovalRequested(
        **ENVELOPE,
        request_id="r1",
        approval_type="budget_increase",
        detail="Need more budget",
        colony_id="col1",
    ),
    "ApprovalGranted": ApprovalGranted(**ENVELOPE, request_id="r1"),
    "ApprovalDenied": ApprovalDenied(**ENVELOPE, request_id="r1"),
    "QueenMessage": QueenMessage(
        **ENVELOPE, thread_id="th1", role="queen", content="hello"
    ),
    "TokensConsumed": TokensConsumed(
        **ENVELOPE,
        agent_id="a1",
        model="m1",
        input_tokens=100,
        output_tokens=50,
        cost=0.01,
    ),
    "ColonyTemplateCreated": ColonyTemplateCreated(
        **ENVELOPE,
        template_id="tmpl-001",
        name="Code Review",
        description="Coder + Reviewer pair.",
        castes=[CasteSlot(caste="coder"), CasteSlot(caste="reviewer")],
        strategy="stigmergic",
    ),
    "ColonyTemplateUsed": ColonyTemplateUsed(
        **ENVELOPE,
        template_id="tmpl-001",
        colony_id="colony-xyz",
    ),
    "ColonyNamed": ColonyNamed(
        **ENVELOPE,
        colony_id="col1",
        display_name="Phoenix Rising",
        named_by="queen",
    ),
    "SkillConfidenceUpdated": SkillConfidenceUpdated(
        **ENVELOPE,
        colony_id="col1",
        skills_updated=3,
        colony_succeeded=True,
    ),
    "SkillMerged": SkillMerged(
        **ENVELOPE,
        surviving_skill_id="skill-a",
        merged_skill_id="skill-b",
        merge_reason="llm_dedup",
    ),
    "ColonyChatMessage": ColonyChatMessage(
        **ENVELOPE,
        colony_id="col1",
        workspace_id="ws1",
        sender="operator",
        content="hello colony",
    ),
    "CodeExecuted": CodeExecuted(
        **ENVELOPE,
        colony_id="col1",
        agent_id="a1",
        code_preview="print('hi')",
        trust_tier="STANDARD",
        exit_code=0,
        duration_ms=100.0,
    ),
    "ServiceQuerySent": ServiceQuerySent(
        **ENVELOPE,
        request_id="sq1",
        service_type="research",
        target_colony_id="svc-col1",
        query_preview="find info about X",
    ),
    "ServiceQueryResolved": ServiceQueryResolved(
        **ENVELOPE,
        request_id="sq1",
        service_type="research",
        source_colony_id="svc-col1",
        response_preview="found info",
        latency_ms=500.0,
    ),
    "ColonyServiceActivated": ColonyServiceActivated(
        **ENVELOPE,
        colony_id="col1",
        workspace_id="ws1",
        service_type="research",
        agent_count=2,
    ),
    "KnowledgeEntityCreated": KnowledgeEntityCreated(
        **ENVELOPE,
        entity_id="ent1",
        name="AuthModule",
        entity_type="MODULE",
        workspace_id="ws1",
    ),
    "KnowledgeEdgeCreated": KnowledgeEdgeCreated(
        **ENVELOPE,
        edge_id="edge1",
        from_entity_id="ent1",
        to_entity_id="ent2",
        predicate="DEPENDS_ON",
        confidence=0.9,
        workspace_id="ws1",
    ),
    "KnowledgeEntityMerged": KnowledgeEntityMerged(
        **ENVELOPE,
        survivor_id="ent1",
        merged_id="ent2",
        similarity_score=0.96,
        merge_method="auto",
        workspace_id="ws1",
    ),
    "ColonyRedirected": ColonyRedirected(
        **ENVELOPE,
        colony_id="col1",
        redirect_index=0,
        original_goal="build it",
        new_goal="fix the bug instead",
        reason="colony was going off-track",
        trigger="queen_inspection",
        round_at_redirect=3,
    ),
    "MemoryEntryCreated": MemoryEntryCreated(
        **ENVELOPE,
        entry={"id": "mem-col1-s-0", "entry_type": "skill", "title": "test", "content": "test content"},
        workspace_id="ws1",
    ),
    "MemoryEntryStatusChanged": MemoryEntryStatusChanged(
        **ENVELOPE,
        entry_id="mem-col1-s-0",
        old_status="candidate",
        new_status="verified",
        reason="source colony completed",
        workspace_id="ws1",
    ),
    "MemoryExtractionCompleted": MemoryExtractionCompleted(
        **ENVELOPE,
        colony_id="col1",
        entries_created=2,
        workspace_id="ws1",
    ),
    "KnowledgeAccessRecorded": KnowledgeAccessRecorded(
        **ENVELOPE,
        colony_id="col1",
        round_number=1,
        workspace_id="ws1",
        access_mode="context_injection",
        items=[KnowledgeAccessItem(
            id="mem-col1-s-0",
            source_system="institutional_memory",
            canonical_type="skill",
            title="Test skill",
            confidence=0.8,
            score=0.9,
        )],
    ),
    "ThreadGoalSet": ThreadGoalSet(
        **ENVELOPE,
        workspace_id="ws1",
        thread_id="th1",
        goal="Build the widget",
        expected_outputs=["code", "test"],
    ),
    "ThreadStatusChanged": ThreadStatusChanged(
        **ENVELOPE,
        workspace_id="ws1",
        thread_id="th1",
        old_status="active",
        new_status="completed",
        reason="All outputs produced.",
    ),
    "MemoryEntryScopeChanged": MemoryEntryScopeChanged(
        **ENVELOPE,
        entry_id="mem-1",
        old_thread_id="th1",
        new_thread_id="",
        workspace_id="ws1",
    ),
    "DeterministicServiceRegistered": DeterministicServiceRegistered(
        **ENVELOPE,
        service_name="service:consolidation:dedup",
        description="Auto-merge duplicates",
        workspace_id="system",
    ),
    "MemoryConfidenceUpdated": MemoryConfidenceUpdated(
        **ENVELOPE,
        entry_id="mem-col1-s-0",
        colony_id="col1",
        colony_succeeded=True,
        old_alpha=5.0,
        old_beta=5.0,
        new_alpha=6.0,
        new_beta=5.0,
        new_confidence=6.0 / 11.0,
        workspace_id="ws1",
        thread_id="th1",
        reason="colony_outcome",
    ),
    "WorkflowStepDefined": WorkflowStepDefined(
        **ENVELOPE,
        workspace_id="ws1",
        thread_id="th1",
        step=WorkflowStep(step_index=0, description="Implement feature"),
    ),
    "WorkflowStepCompleted": WorkflowStepCompleted(
        **ENVELOPE,
        workspace_id="ws1",
        thread_id="th1",
        step_index=0,
        colony_id="col1",
        success=True,
        artifacts_produced=["code"],
    ),
    "WorkflowStepUpdated": WorkflowStepUpdated(
        **ENVELOPE,
        workspace_id="ws1",
        thread_id="th1",
        step_index=0,
        new_description="Revised step",
        new_status="in_progress",
    ),
    "CRDTCounterIncremented": CRDTCounterIncremented(
        **ENVELOPE,
        entry_id="mem-col1-s-0",
        instance_id="inst-1",
        field="successes",
        delta=1,
        workspace_id="ws1",
    ),
    "CRDTTimestampUpdated": CRDTTimestampUpdated(
        **ENVELOPE,
        entry_id="mem-col1-s-0",
        instance_id="inst-1",
        obs_timestamp=1700000000.0,
        workspace_id="ws1",
    ),
    "CRDTSetElementAdded": CRDTSetElementAdded(
        **ENVELOPE,
        entry_id="mem-col1-s-0",
        field="domains",
        element="python",
        workspace_id="ws1",
    ),
    "CRDTRegisterAssigned": CRDTRegisterAssigned(
        **ENVELOPE,
        entry_id="mem-col1-s-0",
        field="content",
        value="updated content",
        lww_timestamp=1700000000.0,
        instance_id="inst-1",
        workspace_id="ws1",
    ),
    "MemoryEntryMerged": MemoryEntryMerged(
        **ENVELOPE,
        target_id="mem-col1-s-0",
        source_id="mem-col2-s-0",
        merged_content="merged content here",
        merged_domains=["python", "testing"],
        merged_from=["mem-col2-s-0"],
        content_strategy="keep_longer",
        similarity=0.95,
        merge_source="dedup",
        workspace_id="ws1",
    ),
    "MemoryEntryRefined": MemoryEntryRefined(
        **ENVELOPE,
        entry_id="mem-col1-s-0",
        workspace_id="ws1",
        old_content="original content",
        new_content="improved content",
        new_title="Better title",
        refinement_source="maintenance",
    ),
    "ParallelPlanCreated": ParallelPlanCreated(
        **ENVELOPE,
        thread_id="th1",
        workspace_id="ws1",
        plan={"reasoning": "test", "tasks": []},
        parallel_groups=[["t1"], ["t2"]],
        reasoning="test plan",
    ),
    "KnowledgeDistilled": KnowledgeDistilled(
        **ENVELOPE,
        distilled_entry_id="distilled-1",
        source_entry_ids=["src-1", "src-2"],
        workspace_id="ws1",
        cluster_avg_weight=3.5,
    ),
    "KnowledgeEntryOperatorAction": KnowledgeEntryOperatorAction(
        **ENVELOPE,
        entry_id="entry-1",
        workspace_id="ws1",
        action="pin",
        actor="operator",
    ),
    "KnowledgeEntryAnnotated": KnowledgeEntryAnnotated(
        **ENVELOPE,
        entry_id="entry-1",
        workspace_id="ws1",
        annotation_text="Important for compliance.",
        actor="operator",
    ),
    "ConfigSuggestionOverridden": ConfigSuggestionOverridden(
        **ENVELOPE,
        workspace_id="ws1",
        suggestion_category="strategy",
        original_config={"strategy": "stigmergic"},
        overridden_config={"strategy": "direct"},
        actor="operator",
    ),
    "ForageRequested": ForageRequested(
        **ENVELOPE,
        workspace_id="ws1",
        mode="reactive",
        reason="low-confidence retrieval",
        gap_domain="python",
    ),
    "ForageCycleCompleted": ForageCycleCompleted(
        **ENVELOPE,
        workspace_id="ws1",
        forage_request_seq=10,
        queries_issued=2,
        pages_fetched=3,
        entries_admitted=1,
    ),
    "DomainStrategyUpdated": DomainStrategyUpdated(
        **ENVELOPE,
        workspace_id="ws1",
        domain="docs.python.org",
        preferred_level=1,
        success_count=3,
    ),
    "ForagerDomainOverride": ForagerDomainOverride(
        **ENVELOPE,
        workspace_id="ws1",
        domain="example.com",
        action="distrust",
        actor="operator",
    ),
    "ColonyEscalated": ColonyEscalated(
        **ENVELOPE,
        colony_id="colony-1",
        tier="heavy",
        reason="Needs stronger model",
        set_at_round=3,
    ),
    "QueenNoteSaved": QueenNoteSaved(
        **ENVELOPE,
        workspace_id="ws1",
        thread_id="thread-1",
        content="Remember to check edge cases",
    ),
    "AddonLoaded": AddonLoaded(
        **ENVELOPE,
        addon_name="test-addon",
        version="1.0.0",
        tools=["tool_a"],
        handlers=["handler_a"],
        panels=[],
    ),
    "AddonUnloaded": AddonUnloaded(
        **ENVELOPE,
        addon_name="test-addon",
        reason="shutdown",
    ),
    "ServiceTriggerFired": ServiceTriggerFired(
        **ENVELOPE,
        addon_name="test-addon",
        trigger_type="cron",
        workspace_id="ws1",
        details="Scheduled maintenance",
    ),
}


# ---------------------------------------------------------------------------
# Union has exactly 27 members
# ---------------------------------------------------------------------------


class TestFormicOSEventUnion:
    def test_union_has_36_members(self) -> None:
        # FormicOSEvent is Annotated[Union[...], ...] — unwrap to get the Union
        # get_args gives (Union[...], FieldInfo); get_args on the Union gives the members
        annotated_args = get_args(FormicOSEvent)
        union_type = annotated_args[0]
        members = get_args(union_type)
        assert len(members) == 69, f"Expected 69, got {len(members)}: {members}"

    def test_all_sample_events_covered(self) -> None:
        assert len(SAMPLE_EVENTS) == 69


# ---------------------------------------------------------------------------
# Round-trip serialize/deserialize for every event type
# ---------------------------------------------------------------------------


class TestRoundTrip:
    @pytest.mark.parametrize("event_name", list(SAMPLE_EVENTS.keys()))
    def test_round_trip(self, event_name: str) -> None:
        event = SAMPLE_EVENTS[event_name]
        json_str = serialize(event)  # type: ignore[arg-type]
        restored = deserialize(json_str)
        assert restored == event

    @pytest.mark.parametrize("event_name", list(SAMPLE_EVENTS.keys()))
    def test_round_trip_via_mapping(self, event_name: str) -> None:
        event = SAMPLE_EVENTS[event_name]
        data = event.model_dump()  # type: ignore[union-attr]
        restored = deserialize(data)
        assert restored == event


# ---------------------------------------------------------------------------
# Frozen events reject mutation
# ---------------------------------------------------------------------------


class TestFrozenEvents:
    def test_workspace_created_frozen(self) -> None:
        event = SAMPLE_EVENTS["WorkspaceCreated"]
        with pytest.raises(ValidationError):
            event.name = "changed"  # type: ignore[misc,union-attr]

    def test_colony_spawned_frozen(self) -> None:
        event = SAMPLE_EVENTS["ColonySpawned"]
        with pytest.raises(ValidationError):
            event.task = "changed"  # type: ignore[misc,union-attr]

    def test_tokens_consumed_frozen(self) -> None:
        event = SAMPLE_EVENTS["TokensConsumed"]
        with pytest.raises(ValidationError):
            event.cost = 999.0  # type: ignore[misc,union-attr]


class TestColonySpawnedInputSources:
    """ADR-033: ColonySpawned gains input_sources field."""

    def test_default_empty_list(self) -> None:
        event = SAMPLE_EVENTS["ColonySpawned"]
        assert isinstance(event, ColonySpawned)
        assert event.input_sources == []

    def test_with_input_sources(self) -> None:
        src = InputSource(type="colony", colony_id="col-abc", summary="prior result")
        event = ColonySpawned(
            **ENVELOPE,
            thread_id="th1",
            task="chained task",
            castes=[CasteSlot(caste="coder")],
            model_assignments={},
            strategy="stigmergic",
            max_rounds=3,
            budget_limit=1.0,
            input_sources=[src],
        )
        assert len(event.input_sources) == 1
        assert event.input_sources[0].colony_id == "col-abc"
        assert event.input_sources[0].summary == "prior result"

    def test_round_trip_with_input_sources(self) -> None:
        src = InputSource(type="colony", colony_id="col-xyz", summary="summary text")
        event = ColonySpawned(
            **ENVELOPE,
            thread_id="th1",
            task="chain test",
            castes=[CasteSlot(caste="coder")],
            model_assignments={},
            strategy="stigmergic",
            max_rounds=3,
            budget_limit=1.0,
            input_sources=[src],
        )
        json_str = serialize(event)
        restored = deserialize(json_str)
        assert isinstance(restored, ColonySpawned)
        assert len(restored.input_sources) == 1
        assert restored.input_sources[0].summary == "summary text"
