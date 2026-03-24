"""Backward compatibility tests for StrEnum field migration (Wave 32 C3).

Verifies that Pydantic v2 transparently deserializes plain string values
into the new StrEnum types on all 6 migrated fields.
"""

from __future__ import annotations

from datetime import datetime, timezone

from formicos.core.events import (
    ApprovalRequested,
    ColonyRedirected,
    KnowledgeAccessRecorded,
    ServiceQuerySent,
    SkillMerged,
)
from formicos.core.types import (
    AccessMode,
    ApprovalType,
    MemoryEntry,
    MergeReason,
    RedirectTrigger,
    ScanStatus,
    ServicePriority,
)

_NOW = datetime(2026, 3, 18, tzinfo=timezone.utc)
_TS = _NOW.isoformat()


class TestApprovalTypeCompat:
    """ApprovalRequested.approval_type deserializes from plain strings."""

    def test_from_string(self) -> None:
        evt = ApprovalRequested(
            seq=1, timestamp=_NOW, address="ws-1",
            request_id="req-1", approval_type="budget_increase",
            detail="Need more budget", colony_id="col-1",
        )
        assert evt.approval_type == ApprovalType.budget_increase
        assert isinstance(evt.approval_type, ApprovalType)
        assert evt.approval_type.value == "budget_increase"

    def test_all_values(self) -> None:
        for val in ["budget_increase", "cloud_burst", "tool_permission", "expense"]:
            evt = ApprovalRequested(
                seq=1, timestamp=_NOW, address="ws-1",
                request_id="req-1", approval_type=val,
                detail="test", colony_id="col-1",
            )
            assert evt.approval_type == val
            assert isinstance(evt.approval_type, ApprovalType)


class TestServicePriorityCompat:
    """ServiceQuerySent.priority deserializes from plain strings."""

    def test_from_string(self) -> None:
        evt = ServiceQuerySent(
            seq=1, timestamp=_NOW, address="ws-1",
            request_id="req-1", service_type="test",
            target_colony_id="col-1", query_preview="q",
            priority="high",
        )
        assert evt.priority == ServicePriority.high
        assert isinstance(evt.priority, ServicePriority)
        assert evt.priority.value == "high"

    def test_default_normal(self) -> None:
        evt = ServiceQuerySent(
            seq=1, timestamp=_NOW, address="ws-1",
            request_id="req-1", service_type="test",
            target_colony_id="col-1", query_preview="q",
        )
        assert evt.priority == ServicePriority.normal


class TestRedirectTriggerCompat:
    """ColonyRedirected.trigger deserializes from plain strings."""

    def test_from_string(self) -> None:
        evt = ColonyRedirected(
            seq=1, timestamp=_NOW, address="ws-1",
            colony_id="col-1", redirect_index=0,
            original_goal="old", new_goal="new",
            reason="test", trigger="governance_alert",
            round_at_redirect=1,
        )
        assert evt.trigger == RedirectTrigger.governance_alert
        assert isinstance(evt.trigger, RedirectTrigger)
        assert evt.trigger.value == "governance_alert"

    def test_all_values(self) -> None:
        for val in ["queen_inspection", "governance_alert", "operator_request"]:
            evt = ColonyRedirected(
                seq=1, timestamp=_NOW, address="ws-1",
                colony_id="col-1", redirect_index=0,
                original_goal="old", new_goal="new",
                reason="test", trigger=val,
                round_at_redirect=1,
            )
            assert evt.trigger == val


class TestMergeReasonCompat:
    """SkillMerged.merge_reason deserializes from plain strings."""

    def test_from_string(self) -> None:
        evt = SkillMerged(
            seq=1, timestamp=_NOW, address="ws-1",
            surviving_skill_id="s-1", merged_skill_id="s-2",
            merge_reason="llm_dedup",
        )
        assert evt.merge_reason == MergeReason.llm_dedup
        assert isinstance(evt.merge_reason, MergeReason)
        assert evt.merge_reason.value == "llm_dedup"


class TestAccessModeCompat:
    """KnowledgeAccessRecorded.access_mode deserializes from plain strings."""

    def test_from_string(self) -> None:
        evt = KnowledgeAccessRecorded(
            seq=1, timestamp=_NOW, address="ws-1",
            colony_id="col-1", round_number=1,
            workspace_id="ws-1", access_mode="tool_search",
        )
        assert evt.access_mode == AccessMode.tool_search
        assert isinstance(evt.access_mode, AccessMode)
        assert evt.access_mode.value == "tool_search"

    def test_all_values(self) -> None:
        for val in ["context_injection", "tool_search", "tool_detail", "tool_transcript"]:
            evt = KnowledgeAccessRecorded(
                seq=1, timestamp=_NOW, address="ws-1",
                colony_id="col-1", round_number=1,
                workspace_id="ws-1", access_mode=val,
            )
            assert evt.access_mode == val

    def test_default(self) -> None:
        evt = KnowledgeAccessRecorded(
            seq=1, timestamp=_NOW, address="ws-1",
            colony_id="col-1", round_number=1,
            workspace_id="ws-1",
        )
        assert evt.access_mode == AccessMode.context_injection


class TestScanStatusCompat:
    """MemoryEntry.scan_status deserializes from plain strings."""

    def test_from_string(self) -> None:
        entry = MemoryEntry(
            id="mem-1", entry_type="skill",
            title="Test", content="Content",
            source_colony_id="col-1", source_artifact_ids=[],
            scan_status="safe",
        )
        assert entry.scan_status == ScanStatus.safe
        assert isinstance(entry.scan_status, ScanStatus)
        assert entry.scan_status.value == "safe"

    def test_all_values(self) -> None:
        for val in ["pending", "safe", "low", "medium", "high", "critical"]:
            entry = MemoryEntry(
                id="mem-1", entry_type="skill",
                title="Test", content="Content",
                source_colony_id="col-1", source_artifact_ids=[],
                scan_status=val,
            )
            assert entry.scan_status == val

    def test_default_pending(self) -> None:
        entry = MemoryEntry(
            id="mem-1", entry_type="skill",
            title="Test", content="Content",
            source_colony_id="col-1", source_artifact_ids=[],
        )
        assert entry.scan_status == ScanStatus.pending
