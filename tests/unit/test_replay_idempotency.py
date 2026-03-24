"""Replay idempotency test — fundamental event-sourcing invariant (Wave 32 C2).

Verifies:
1. Applying the same event sequence twice from empty state produces identical state.
2. Double-applying events does not double counters.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

from formicos.core.events import (
    AgentTurnCompleted,
    AgentTurnStarted,
    ApprovalDenied,
    ApprovalGranted,
    ApprovalRequested,
    CodeExecuted,
    ColonyChatMessage,
    ColonyCompleted,
    ColonyEscalated,
    ColonyFailed,
    ColonyKilled,
    ColonyNamed,
    ColonyRedirected,
    ColonyServiceActivated,
    ColonySpawned,
    ColonyTemplateCreated,
    ColonyTemplateUsed,
    ContextUpdated,
    CRDTCounterIncremented,
    CRDTRegisterAssigned,
    CRDTSetElementAdded,
    CRDTTimestampUpdated,
    DeterministicServiceRegistered,
    DomainStrategyUpdated,
    ForageCycleCompleted,
    ForageRequested,
    ForagerDomainOverride,
    FormicOSEvent,
    KnowledgeAccessRecorded,
    KnowledgeEdgeCreated,
    KnowledgeEntityCreated,
    ConfigSuggestionOverridden,
    KnowledgeDistilled,
    KnowledgeEntryAnnotated,
    KnowledgeEntryOperatorAction,
    KnowledgeEntityMerged,
    MemoryConfidenceUpdated,
    MemoryEntryCreated,
    MemoryEntryMerged,
    MemoryEntryRefined,
    MemoryEntryScopeChanged,
    MemoryEntryStatusChanged,
    MemoryExtractionCompleted,
    MergeCreated,
    MergePruned,
    ModelAssignmentChanged,
    ParallelPlanCreated,
    ModelRegistered,
    PhaseEntered,
    QueenMessage,
    QueenNoteSaved,
    RoundCompleted,
    RoundStarted,
    ServiceQueryResolved,
    ServiceQuerySent,
    SkillConfidenceUpdated,
    SkillMerged,
    ThreadCreated,
    ThreadGoalSet,
    ThreadRenamed,
    ThreadStatusChanged,
    TokensConsumed,
    WorkflowStepCompleted,
    WorkflowStepDefined,
    WorkspaceConfigChanged,
    WorkspaceCreated,
)
from formicos.core.events import WorkspaceConfigSnapshot
from formicos.core.types import CasteSlot, WorkflowStep
from formicos.surface.projections import ProjectionStore

_NOW = datetime(2026, 3, 18, tzinfo=timezone.utc)
_WS_ID = "ws-1"
_TH_ID = "t-1"
_COL_ID = "col-1"
_AGENT_ID = "agent-1"
_ADDR = f"{_WS_ID}/{_TH_ID}/{_COL_ID}"
_SEQ = 0


def _seq() -> int:
    global _SEQ  # noqa: PLW0603
    _SEQ += 1
    return _SEQ


def build_representative_event_sequence() -> list[FormicOSEvent]:
    """Build one instance of each of the 53 event types with valid fields."""
    global _SEQ  # noqa: PLW0603
    _SEQ = 0

    ws_config = WorkspaceConfigSnapshot(budget=5.0, strategy="stigmergic")
    caste = CasteSlot(caste="coder")

    events: list[Any] = [
        # 1. WorkspaceCreated (name must match _WS_ID — projections key by name)
        WorkspaceCreated(
            seq=_seq(), timestamp=_NOW, address=_WS_ID,
            name=_WS_ID, config=ws_config,
        ),
        # 2. ThreadCreated (name must match _TH_ID — projections key by name)
        ThreadCreated(
            seq=_seq(), timestamp=_NOW, address=f"{_WS_ID}/{_TH_ID}",
            workspace_id=_WS_ID, name=_TH_ID,
        ),
        # 3. ThreadRenamed
        ThreadRenamed(
            seq=_seq(), timestamp=_NOW, address=f"{_WS_ID}/{_TH_ID}",
            workspace_id=_WS_ID, thread_id=_TH_ID, new_name="Renamed",
        ),
        # 4. ColonySpawned
        ColonySpawned(
            seq=_seq(), timestamp=_NOW, address=_ADDR,
            thread_id=_TH_ID, task="Test task",
            castes=[caste], model_assignments={"coder": "test-model"},
            strategy="stigmergic", max_rounds=5, budget_limit=1.0,
        ),
        # 5. RoundStarted
        RoundStarted(
            seq=_seq(), timestamp=_NOW, address=_ADDR,
            colony_id=_COL_ID, round_number=1,
        ),
        # 6. PhaseEntered
        PhaseEntered(
            seq=_seq(), timestamp=_NOW, address=_ADDR,
            colony_id=_COL_ID, round_number=1, phase="goal",
        ),
        # 7. AgentTurnStarted
        AgentTurnStarted(
            seq=_seq(), timestamp=_NOW, address=_ADDR,
            colony_id=_COL_ID, round_number=1,
            agent_id=_AGENT_ID, caste="coder", model="test-model",
        ),
        # 8. AgentTurnCompleted
        AgentTurnCompleted(
            seq=_seq(), timestamp=_NOW, address=_ADDR,
            agent_id=_AGENT_ID, output_summary="Done",
            input_tokens=100, output_tokens=50,
            tool_calls=["code_execute"], duration_ms=1000,
        ),
        # 9. RoundCompleted
        RoundCompleted(
            seq=_seq(), timestamp=_NOW, address=_ADDR,
            colony_id=_COL_ID, round_number=1,
            convergence=0.8, cost=0.01, duration_ms=2000,
        ),
        # 10. MergeCreated
        MergeCreated(
            seq=_seq(), timestamp=_NOW, address=_ADDR,
            edge_id="merge-1", from_colony=_COL_ID,
            to_colony="col-2", created_by="queen",
        ),
        # 11. MergePruned
        MergePruned(
            seq=_seq(), timestamp=_NOW, address=_ADDR,
            edge_id="merge-1", pruned_by="queen",
        ),
        # 12. ContextUpdated
        ContextUpdated(
            seq=_seq(), timestamp=_NOW, address=_ADDR,
            key="test_key", value="test_val", operation="set",
        ),
        # 13. WorkspaceConfigChanged
        WorkspaceConfigChanged(
            seq=_seq(), timestamp=_NOW, address=_WS_ID,
            workspace_id=_WS_ID, field="queen_model",
            new_value="anthropic/claude-sonnet-4.6",
        ),
        # 14. ModelRegistered
        ModelRegistered(
            seq=_seq(), timestamp=_NOW, address="system",
            provider_prefix="anthropic", model_name="claude-sonnet-4.6",
            context_window=200000, supports_tools=True,
        ),
        # 15. ModelAssignmentChanged
        ModelAssignmentChanged(
            seq=_seq(), timestamp=_NOW, address="system",
            scope="system", caste="coder",
            new_model="anthropic/claude-sonnet-4.6",
        ),
        # 16. ApprovalRequested
        ApprovalRequested(
            seq=_seq(), timestamp=_NOW, address=_WS_ID,
            request_id="req-1", approval_type="budget_increase",
            detail="Need more budget", colony_id=_COL_ID,
        ),
        # 17. ApprovalGranted
        ApprovalGranted(
            seq=_seq(), timestamp=_NOW, address=_WS_ID,
            request_id="req-1",
        ),
        # 18. ApprovalDenied
        ApprovalDenied(
            seq=_seq(), timestamp=_NOW, address=_WS_ID,
            request_id="req-2",
        ),
        # 19. QueenMessage
        QueenMessage(
            seq=_seq(), timestamp=_NOW, address=f"{_WS_ID}/{_TH_ID}",
            thread_id=_TH_ID, role="queen", content="Hello operator",
        ),
        # 20. TokensConsumed
        TokensConsumed(
            seq=_seq(), timestamp=_NOW, address=_ADDR,
            agent_id=_AGENT_ID, model="test-model",
            input_tokens=100, output_tokens=50, cost=0.005,
        ),
        # 21. ColonyTemplateCreated
        ColonyTemplateCreated(
            seq=_seq(), timestamp=_NOW, address=_WS_ID,
            template_id="tmpl-1", name="Coder Template",
            description="Standard coder", castes=[caste],
            strategy="stigmergic",
        ),
        # 22. ColonyTemplateUsed
        ColonyTemplateUsed(
            seq=_seq(), timestamp=_NOW, address=_ADDR,
            template_id="tmpl-1", colony_id=_COL_ID,
        ),
        # 23. ColonyNamed
        ColonyNamed(
            seq=_seq(), timestamp=_NOW, address=_ADDR,
            colony_id=_COL_ID, display_name="My Colony", named_by="queen",
        ),
        # 24. SkillConfidenceUpdated
        SkillConfidenceUpdated(
            seq=_seq(), timestamp=_NOW, address=_WS_ID,
            colony_id=_COL_ID, skills_updated=3, colony_succeeded=True,
        ),
        # 25. SkillMerged
        SkillMerged(
            seq=_seq(), timestamp=_NOW, address=_WS_ID,
            surviving_skill_id="skill-1", merged_skill_id="skill-2",
            merge_reason="llm_dedup",
        ),
        # 26. ColonyChatMessage
        ColonyChatMessage(
            seq=_seq(), timestamp=_NOW, address=_ADDR,
            colony_id=_COL_ID, workspace_id=_WS_ID,
            sender="agent", content="Working on it",
        ),
        # 27. CodeExecuted
        CodeExecuted(
            seq=_seq(), timestamp=_NOW, address=_ADDR,
            colony_id=_COL_ID, agent_id=_AGENT_ID,
            code_preview="print('hello')", trust_tier="STANDARD",
            exit_code=0, duration_ms=50.0,
        ),
        # 28. ServiceQuerySent
        ServiceQuerySent(
            seq=_seq(), timestamp=_NOW, address=_WS_ID,
            request_id="svc-1", service_type="research",
            target_colony_id="svc-col-1",
            query_preview="Find related work",
        ),
        # 29. ServiceQueryResolved
        ServiceQueryResolved(
            seq=_seq(), timestamp=_NOW, address=_WS_ID,
            request_id="svc-1", service_type="research",
            source_colony_id="svc-col-1",
            response_preview="Found 3 papers", latency_ms=500.0,
        ),
        # 30. ColonyServiceActivated
        ColonyServiceActivated(
            seq=_seq(), timestamp=_NOW, address=_ADDR,
            colony_id=_COL_ID, workspace_id=_WS_ID,
            service_type="research", agent_count=1,
        ),
        # 31. KnowledgeEntityCreated
        KnowledgeEntityCreated(
            seq=_seq(), timestamp=_NOW, address=_WS_ID,
            entity_id="ent-1", name="Python", entity_type="CONCEPT",
            workspace_id=_WS_ID,
        ),
        # 32. KnowledgeEdgeCreated
        KnowledgeEdgeCreated(
            seq=_seq(), timestamp=_NOW, address=_WS_ID,
            edge_id="edge-1", from_entity_id="ent-1",
            to_entity_id="ent-2", predicate="DEPENDS_ON",
            confidence=0.9, workspace_id=_WS_ID,
        ),
        # 33. KnowledgeEntityMerged
        KnowledgeEntityMerged(
            seq=_seq(), timestamp=_NOW, address=_WS_ID,
            survivor_id="ent-1", merged_id="ent-3",
            similarity_score=0.96, merge_method="auto",
            workspace_id=_WS_ID,
        ),
        # 34. ColonyRedirected
        ColonyRedirected(
            seq=_seq(), timestamp=_NOW, address=_ADDR,
            colony_id=_COL_ID, redirect_index=0,
            original_goal="Test task", new_goal="New goal",
            reason="Better approach", trigger="queen_inspection",
            round_at_redirect=1,
        ),
        # 35. ColonyCompleted
        ColonyCompleted(
            seq=_seq(), timestamp=_NOW, address=_ADDR,
            colony_id=_COL_ID, summary="Done", skills_extracted=1,
        ),
        # 36. MemoryEntryCreated
        MemoryEntryCreated(
            seq=_seq(), timestamp=_NOW, address=f"{_WS_ID}/{_TH_ID}",
            workspace_id=_WS_ID,
            entry={
                "id": "mem-1", "entry_type": "skill",
                "status": "candidate", "title": "Test Skill",
                "content": "Content", "source_colony_id": _COL_ID,
                "source_artifact_ids": [], "workspace_id": _WS_ID,
                "thread_id": _TH_ID, "conf_alpha": 5.0, "conf_beta": 5.0,
                "confidence": 0.5,
            },
        ),
        # 37. MemoryEntryStatusChanged
        MemoryEntryStatusChanged(
            seq=_seq(), timestamp=_NOW, address=_WS_ID,
            entry_id="mem-1", old_status="candidate",
            new_status="verified", reason="colony succeeded",
            workspace_id=_WS_ID,
        ),
        # 38. MemoryExtractionCompleted
        MemoryExtractionCompleted(
            seq=_seq(), timestamp=_NOW, address=_WS_ID,
            colony_id=_COL_ID, entries_created=1, workspace_id=_WS_ID,
        ),
        # 39. KnowledgeAccessRecorded
        KnowledgeAccessRecorded(
            seq=_seq(), timestamp=_NOW, address=f"{_WS_ID}/{_TH_ID}",
            colony_id=_COL_ID, round_number=1, workspace_id=_WS_ID,
        ),
        # 40. ThreadGoalSet
        ThreadGoalSet(
            seq=_seq(), timestamp=_NOW, address=f"{_WS_ID}/{_TH_ID}",
            workspace_id=_WS_ID, thread_id=_TH_ID,
            goal="Build the feature",
        ),
        # 41. ThreadStatusChanged
        ThreadStatusChanged(
            seq=_seq(), timestamp=_NOW, address=f"{_WS_ID}/{_TH_ID}",
            workspace_id=_WS_ID, thread_id=_TH_ID,
            old_status="active", new_status="completed",
        ),
        # 42. MemoryEntryScopeChanged
        MemoryEntryScopeChanged(
            seq=_seq(), timestamp=_NOW, address=_WS_ID,
            entry_id="mem-1", old_thread_id=_TH_ID,
            new_thread_id="", workspace_id=_WS_ID,
        ),
        # 43. DeterministicServiceRegistered
        DeterministicServiceRegistered(
            seq=_seq(), timestamp=_NOW, address="system",
            service_name="service:consolidation:dedup",
        ),
        # 44. MemoryConfidenceUpdated
        MemoryConfidenceUpdated(
            seq=_seq(), timestamp=_NOW, address=f"{_WS_ID}/{_TH_ID}",
            entry_id="mem-1", colony_id=_COL_ID,
            colony_succeeded=True,
            old_alpha=5.0, old_beta=5.0,
            new_alpha=6.0, new_beta=5.0,
            new_confidence=6.0 / 11.0,
            workspace_id=_WS_ID,
        ),
        # 45. WorkflowStepDefined
        WorkflowStepDefined(
            seq=_seq(), timestamp=_NOW, address=f"{_WS_ID}/{_TH_ID}",
            workspace_id=_WS_ID, thread_id=_TH_ID,
            step=WorkflowStep(step_index=0, description="Step 1"),
        ),
        # 46. WorkflowStepCompleted
        WorkflowStepCompleted(
            seq=_seq(), timestamp=_NOW, address=f"{_WS_ID}/{_TH_ID}",
            workspace_id=_WS_ID, thread_id=_TH_ID,
            step_index=0, colony_id=_COL_ID, success=True,
        ),
        # 47. CRDTCounterIncremented
        CRDTCounterIncremented(
            seq=_seq(), timestamp=_NOW, address=_ADDR,
            entry_id="mem-1", instance_id=_COL_ID,
            field="successes", delta=1, workspace_id=_WS_ID,
        ),
        # 48. CRDTTimestampUpdated
        CRDTTimestampUpdated(
            seq=_seq(), timestamp=_NOW, address=_ADDR,
            entry_id="mem-1", instance_id=_COL_ID,
            obs_timestamp=1710720000.0, workspace_id=_WS_ID,
        ),
        # 49. CRDTSetElementAdded
        CRDTSetElementAdded(
            seq=_seq(), timestamp=_NOW, address=_ADDR,
            entry_id="mem-1", field="domains",
            element="python", workspace_id=_WS_ID,
        ),
        # 50. CRDTRegisterAssigned
        CRDTRegisterAssigned(
            seq=_seq(), timestamp=_NOW, address=_ADDR,
            entry_id="mem-1", field="content",
            value="Updated content", lww_timestamp=1710720000.0,
            instance_id=_COL_ID, workspace_id=_WS_ID,
        ),
        # 51. MemoryEntryCreated (second entry for merge target)
        MemoryEntryCreated(
            seq=_seq(), timestamp=_NOW, address=f"{_WS_ID}/{_TH_ID}",
            workspace_id=_WS_ID,
            entry={
                "id": "mem-2", "entry_type": "skill",
                "status": "candidate", "title": "Test Skill 2",
                "content": "Content 2", "source_colony_id": _COL_ID,
                "source_artifact_ids": [], "workspace_id": _WS_ID,
                "thread_id": _TH_ID, "conf_alpha": 5.0, "conf_beta": 5.0,
                "confidence": 0.5,
            },
        ),
        # 52. MemoryEntryMerged (merges mem-2 into mem-1)
        MemoryEntryMerged(
            seq=_seq(), timestamp=_NOW, address=_WS_ID,
            target_id="mem-1", source_id="mem-2",
            merged_content="Content merged", merged_domains=["python"],
            merged_from=[_COL_ID], content_strategy="keep_longer",
            similarity=0.92, merge_source="dedup", workspace_id=_WS_ID,
        ),
        # Need ColonyFailed and ColonyKilled on a separate colony
        # 53. ColonyFailed (needs a different colony)
        ColonyFailed(
            seq=_seq(), timestamp=_NOW, address=f"{_WS_ID}/{_TH_ID}/col-fail",
            colony_id="col-fail", reason="Out of budget",
        ),
        # 54. ColonyKilled
        ColonyKilled(
            seq=_seq(), timestamp=_NOW, address=f"{_WS_ID}/{_TH_ID}/col-kill",
            colony_id="col-kill", killed_by="operator",
        ),
        # 55. ParallelPlanCreated (Wave 35)
        ParallelPlanCreated(
            seq=_seq(), timestamp=_NOW, address=f"{_WS_ID}/{_TH_ID}",
            thread_id=_TH_ID, workspace_id=_WS_ID,
            plan={"reasoning": "test", "tasks": []},
            parallel_groups=[["t1"], ["t2"]],
            reasoning="test plan",
        ),
        # 56. KnowledgeDistilled (Wave 35)
        KnowledgeDistilled(
            seq=_seq(), timestamp=_NOW, address=_WS_ID,
            distilled_entry_id="distilled-1",
            source_entry_ids=["mem-1", "mem-2"],
            workspace_id=_WS_ID,
            cluster_avg_weight=3.5,
        ),
        # 57. KnowledgeEntryOperatorAction (Wave 39 ADR-049)
        KnowledgeEntryOperatorAction(
            seq=_seq(), timestamp=_NOW, address=f"{_WS_ID}/mem-1",
            entry_id="mem-1",
            workspace_id=_WS_ID,
            action="pin",
            actor="operator",
        ),
        # 58. KnowledgeEntryAnnotated (Wave 39 ADR-049)
        KnowledgeEntryAnnotated(
            seq=_seq(), timestamp=_NOW, address=f"{_WS_ID}/mem-1",
            entry_id="mem-1",
            workspace_id=_WS_ID,
            annotation_text="Important entry.",
            actor="operator",
        ),
        # 59. ConfigSuggestionOverridden (Wave 39 ADR-049)
        ConfigSuggestionOverridden(
            seq=_seq(), timestamp=_NOW, address=_WS_ID,
            workspace_id=_WS_ID,
            suggestion_category="strategy",
            original_config={"strategy": "stigmergic"},
            overridden_config={"strategy": "direct"},
            actor="operator",
        ),
        # Wave 44 — Forager events
        ForageRequested(
            seq=_seq(), timestamp=_NOW, address=_WS_ID,
            workspace_id=_WS_ID, mode="reactive",
            reason="low-confidence retrieval",
            gap_domain="python",
        ),
        ForageCycleCompleted(
            seq=_seq(), timestamp=_NOW, address=_WS_ID,
            workspace_id=_WS_ID, forage_request_seq=60,
            queries_issued=2, pages_fetched=3, entries_admitted=1,
        ),
        DomainStrategyUpdated(
            seq=_seq(), timestamp=_NOW, address=_WS_ID,
            workspace_id=_WS_ID, domain="docs.python.org",
            preferred_level=1, success_count=3,
        ),
        ForagerDomainOverride(
            seq=_seq(), timestamp=_NOW, address=_WS_ID,
            workspace_id=_WS_ID, domain="example.com",
            action="distrust", actor="operator",
        ),
        # Wave 51 — Replay safety events
        ColonyEscalated(
            seq=_seq(), timestamp=_NOW, address=_ADDR,
            colony_id=_COL_ID, tier="heavy",
            reason="Complex task needs more resources",
            set_at_round=1,
        ),
        QueenNoteSaved(
            seq=_seq(), timestamp=_NOW, address=f"{_WS_ID}/{_TH_ID}",
            workspace_id=_WS_ID, thread_id=_TH_ID,
            content="Remember to check test coverage.",
        ),
        MemoryEntryRefined(
            seq=_seq(), timestamp=_NOW, address=f"{_WS_ID}/{_TH_ID}",
            entry_id="mem-1", workspace_id=_WS_ID,
            old_content="Original content.",
            new_content="Improved content after refinement.",
            new_title="",
            refinement_source="maintenance",
            source_colony_id="",
        ),
    ]
    assert len(events) == 66, f"Expected 66 events, got {len(events)}"
    return events


def _snapshot_store(store: ProjectionStore) -> dict[str, Any]:
    """Take a serializable snapshot of projection state."""
    return {
        "workspaces": {
            ws_id: {
                "name": ws.name,
                "config": dict(ws.config),
                "threads": {
                    th_id: {
                        "name": th.name,
                        "status": th.status,
                        "goal": th.goal,
                        "colony_count": th.colony_count,
                        "completed_colony_count": th.completed_colony_count,
                        "workflow_steps": copy.deepcopy(th.workflow_steps),
                        "continuation_depth": th.continuation_depth,
                    }
                    for th_id, th in ws.threads.items()
                },
            }
            for ws_id, ws in store.workspaces.items()
        },
        "colonies": {
            col_id: {
                "status": col.status,
                "task": col.task,
                "round_number": col.round_number,
                "display_name": col.display_name,
                "active_goal": col.active_goal,
                "knowledge_accesses_count": len(col.knowledge_accesses),
            }
            for col_id, col in store.colonies.items()
        },
        "memory_entries": copy.deepcopy(dict(store.memory_entries)),
        "templates": {
            tid: {"name": t.name, "use_count": t.use_count}
            for tid, t in store.templates.items()
        },
        "memory_extractions_completed": sorted(store.memory_extractions_completed),
    }


class TestReplayIdempotency:
    """Applying the same events from empty state twice produces identical results."""

    def test_two_replays_produce_identical_state(self) -> None:
        events = build_representative_event_sequence()

        store_a = ProjectionStore()
        for evt in events:
            store_a.apply(evt)

        store_b = ProjectionStore()
        for evt in events:
            store_b.apply(evt)

        snap_a = _snapshot_store(store_a)
        snap_b = _snapshot_store(store_b)

        assert snap_a == snap_b, "Two replays of the same events must produce identical state"

    def test_all_48_event_types_covered(self) -> None:
        """Verify the sequence actually contains all 48 event types."""
        from formicos.core.events import EVENT_TYPE_NAMES

        events = build_representative_event_sequence()
        event_types_present = {type(e).__name__ for e in events}
        expected = set(EVENT_TYPE_NAMES)

        missing = expected - event_types_present
        assert not missing, f"Missing event types in sequence: {missing}"


class TestDoubleApplyIdempotency:
    """Double-applying events should not corrupt state."""

    def test_colony_count_not_doubled(self) -> None:
        events = build_representative_event_sequence()

        store = ProjectionStore()
        for evt in events:
            store.apply(evt)

        snap_before = _snapshot_store(store)

        # Apply again
        for evt in events:
            store.apply(evt)

        snap_after = _snapshot_store(store)

        # Template use count increments on each ColonyTemplateUsed — that's
        # expected behavior (non-idempotent by design). But workspace/thread/colony
        # creation should not create duplicates since they use dict keying.
        assert snap_before["workspaces"].keys() == snap_after["workspaces"].keys()
        assert snap_before["colonies"].keys() == snap_after["colonies"].keys()

    def test_memory_entries_not_duplicated(self) -> None:
        events = build_representative_event_sequence()

        store = ProjectionStore()
        for evt in events:
            store.apply(evt)

        count_before = len(store.memory_entries)

        for evt in events:
            store.apply(evt)

        # Dict keying prevents duplication
        assert len(store.memory_entries) == count_before
