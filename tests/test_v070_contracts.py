"""
Tests for v0.7.0 contract models.

Validates serialization round-trips, required fields, defaults,
and RuntimeWiringContract behaviour.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models import (
    AgentInfoV1,
    ApiErrorDetail,
    ApiErrorV1,
    ArtifactRefsV1,
    ColonyResultV1,
    ColonyStateV1,
    EventEnvelopeV1,
    EventTrace,
    FailureInfoV1,
    RecoveryReportV1,
    RuntimeWiringContract,
    SessionSnapshotV1,
    SkillMetadataV1,
    SkillV1,
    SnapshotMetadataV1,
    TeamInfoV1,
    ToolApprovalPolicy,
    ToolSpecV1,
    WorkspaceMetaV1,
)


# ═══════════════════════════════════════════════════════════════════════
# ApiErrorV1
# ═══════════════════════════════════════════════════════════════════════


class TestApiErrorV1:
    def test_round_trip(self):
        err = ApiErrorV1(
            error=ApiErrorDetail(
                code="COLONY_NOT_FOUND",
                message="Colony xyz not found",
                detail={"colony_id": "xyz"},
                request_id="req-123",
                ts="2026-02-28T00:00:00Z",
            )
        )
        data = err.model_dump()
        assert data["error"]["code"] == "COLONY_NOT_FOUND"
        assert data["error"]["detail"] == {"colony_id": "xyz"}
        restored = ApiErrorV1.model_validate(data)
        assert restored.error.code == err.error.code

    def test_detail_optional(self):
        err = ApiErrorV1(
            error=ApiErrorDetail(
                code="INTERNAL_ERROR",
                message="oops",
                request_id="r1",
                ts="2026-02-28T00:00:00Z",
            )
        )
        assert err.error.detail is None

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            ApiErrorV1(error=ApiErrorDetail(code="X", message="Y"))  # type: ignore[call-arg]


# ═══════════════════════════════════════════════════════════════════════
# EventEnvelopeV1
# ═══════════════════════════════════════════════════════════════════════


class TestEventEnvelopeV1:
    def test_round_trip(self):
        env = EventEnvelopeV1(
            event_id="evt-1",
            seq=42,
            ts="2026-02-28T00:00:00Z",
            colony_id="col-1",
            type="agent.token",
            payload={"agent_id": "a1", "token": "hello"},
            trace=EventTrace(request_id="req-1", round=3),
        )
        data = env.model_dump()
        assert data["seq"] == 42
        assert data["trace"]["round"] == 3
        restored = EventEnvelopeV1.model_validate(data)
        assert restored.type == "agent.token"

    def test_defaults(self):
        env = EventEnvelopeV1(
            event_id="e1", seq=0, ts="now", type="test"
        )
        assert env.colony_id is None
        assert env.payload == {}
        assert env.trace.request_id is None

    def test_colony_id_optional(self):
        env = EventEnvelopeV1(
            event_id="e1", seq=1, ts="now", type="system.boot"
        )
        assert env.colony_id is None


# ═══════════════════════════════════════════════════════════════════════
# ColonyStateV1
# ═══════════════════════════════════════════════════════════════════════


class TestColonyStateV1:
    def test_full_round_trip(self):
        state = ColonyStateV1(
            colony_id="col-1",
            status="running",
            task="Build a snake game",
            round=3,
            max_rounds=10,
            agents=[
                AgentInfoV1(agent_id="a1", caste="coder", model_id="gpt-4"),
                AgentInfoV1(agent_id="a2", caste="reviewer"),
            ],
            teams=[TeamInfoV1(team_id="t1", name="dev", members=["a1", "a2"])],
            workspace=WorkspaceMetaV1(root="./workspace/col-1", artifact_count=5),
            artifacts=ArtifactRefsV1(session_ref="sess-1"),
            created_ts="2026-02-28T00:00:00Z",
            updated_ts="2026-02-28T01:00:00Z",
        )
        data = state.model_dump()
        assert len(data["agents"]) == 2
        assert data["agents"][1]["model_id"] is None
        assert data["workspace"]["artifact_count"] == 5
        restored = ColonyStateV1.model_validate(data)
        assert restored.colony_id == "col-1"

    def test_defaults(self):
        state = ColonyStateV1(
            colony_id="c1",
            status="created",
            task="test",
            workspace=WorkspaceMetaV1(root="/ws"),
            created_ts="now",
            updated_ts="now",
        )
        assert state.round == 0
        assert state.max_rounds == 10
        assert state.agents == []
        assert state.teams == []
        assert state.artifacts.results_ref is None

    def test_missing_workspace_fails(self):
        with pytest.raises(ValidationError):
            ColonyStateV1(
                colony_id="c1",
                status="created",
                task="test",
                created_ts="now",
                updated_ts="now",
            )  # type: ignore[call-arg]


# ═══════════════════════════════════════════════════════════════════════
# ColonyResultV1
# ═══════════════════════════════════════════════════════════════════════


class TestColonyResultV1:
    def test_completed(self):
        result = ColonyResultV1(
            colony_id="c1",
            status="completed",
            final_answer="Here is the snake game",
            files=["snake.py", "README.md"],
            completed_ts="2026-02-28T02:00:00Z",
        )
        data = result.model_dump()
        assert data["status"] == "completed"
        assert len(data["files"]) == 2
        assert data["failure"]["code"] is None

    def test_failed(self):
        result = ColonyResultV1(
            colony_id="c1",
            status="failed",
            failure=FailureInfoV1(code="LLM_TIMEOUT", detail="Model timed out"),
        )
        data = result.model_dump()
        assert data["failure"]["code"] == "LLM_TIMEOUT"
        assert data["final_answer"] is None

    def test_defaults(self):
        result = ColonyResultV1(colony_id="c1", status="completed")
        assert result.files == []
        assert result.session_ref is None


# ═══════════════════════════════════════════════════════════════════════
# ToolSpecV1
# ═══════════════════════════════════════════════════════════════════════


class TestToolSpecV1:
    def test_round_trip(self):
        tool = ToolSpecV1(
            id="file_write",
            source="builtin",
            schema={"type": "object", "properties": {"path": {"type": "string"}}},
            approval_policy=ToolApprovalPolicy(mode="required", timeout_seconds=60),
            timeout=30,
            enabled=True,
        )
        data = tool.model_dump(by_alias=True)
        assert data["schema"]["type"] == "object"
        assert data["approval_policy"]["mode"] == "required"

    def test_defaults(self):
        tool = ToolSpecV1(id="test", source="mcp")
        assert tool.timeout == 30
        assert tool.retry_policy.max_attempts == 2
        assert tool.approval_policy.mode == "auto"
        assert tool.enabled is True

    def test_populate_by_name(self):
        tool = ToolSpecV1(id="t", source="builtin", schema_def={"x": 1})
        assert tool.schema_def == {"x": 1}


# ═══════════════════════════════════════════════════════════════════════
# SkillV1
# ═══════════════════════════════════════════════════════════════════════


class TestSkillV1:
    def test_round_trip(self):
        skill = SkillV1(
            skill_id="gen_abc123",
            content="Always validate inputs before processing",
            tier="general",
            category="best_practices",
            metadata=SkillMetadataV1(
                source_colony="col-1",
                retrieval_count=5,
                success_correlation=0.8,
            ),
        )
        data = skill.model_dump()
        assert data["metadata"]["retrieval_count"] == 5
        restored = SkillV1.model_validate(data)
        assert restored.content == skill.content

    def test_defaults(self):
        skill = SkillV1(skill_id="s1", content="test", tier="lesson")
        assert skill.category is None
        assert skill.metadata.retrieval_count == 0
        assert skill.metadata.source_colony is None


# ═══════════════════════════════════════════════════════════════════════
# SessionSnapshotV1
# ═══════════════════════════════════════════════════════════════════════


class TestSessionSnapshotV1:
    def test_round_trip(self):
        snap = SessionSnapshotV1(
            session_id="sess-1",
            colony_id="col-1",
            state={"colony": {"task": "test", "round": 3}},
            topology_history=[{"round": 1, "edges": []}],
            episodes=[{"round_num": 1, "summary": "did stuff"}],
            tkg=[{"subject": "a1", "predicate": "wrote", "object_": "file.py"}],
            metadata=SnapshotMetadataV1(
                saved_ts="2026-02-28T00:00:00Z",
                save_reason="pause",
            ),
        )
        data = snap.model_dump()
        assert data["metadata"]["schema_version"] == "1.0"
        assert data["metadata"]["save_reason"] == "pause"
        restored = SessionSnapshotV1.model_validate(data)
        assert len(restored.topology_history) == 1

    def test_missing_metadata_fails(self):
        with pytest.raises(ValidationError):
            SessionSnapshotV1(
                session_id="s1", colony_id="c1"
            )  # type: ignore[call-arg]

    def test_defaults(self):
        snap = SessionSnapshotV1(
            session_id="s1",
            colony_id="c1",
            metadata=SnapshotMetadataV1(saved_ts="now"),
        )
        assert snap.state == {}
        assert snap.topology_history == []
        assert snap.episodes == []
        assert snap.tkg == []
        assert snap.metadata.save_reason == "autosave"


# ═══════════════════════════════════════════════════════════════════════
# RecoveryReportV1
# ═══════════════════════════════════════════════════════════════════════


class TestRecoveryReportV1:
    def test_success(self):
        report = RecoveryReportV1(
            recovery_mode="cold_resume",
            success=True,
            restored_round=5,
            restored_agents=["a1", "a2"],
        )
        data = report.model_dump()
        assert data["recovery_mode"] == "cold_resume"
        assert data["warnings"] == []

    def test_failure_with_warnings(self):
        report = RecoveryReportV1(
            recovery_mode="crash_recover",
            success=False,
            warnings=["Corrupt topology data", "Missing TKG tuples"],
        )
        assert len(report.warnings) == 2
        assert report.restored_round is None


# ═══════════════════════════════════════════════════════════════════════
# RuntimeWiringContract
# ═══════════════════════════════════════════════════════════════════════


class TestRuntimeWiringContract:
    def test_all_wired(self):
        contract = RuntimeWiringContract(
            model_registry=True,
            archivist=True,
            governance=True,
            skill_bank=True,
            audit_logger=True,
            approval_gate=True,
            rag_engine=True,
        )
        assert contract.validate_mandatory() == []

    def test_all_missing(self):
        contract = RuntimeWiringContract()
        missing = contract.validate_mandatory()
        assert len(missing) == 6
        assert "model_registry" in missing
        assert "archivist" in missing
        assert "governance" in missing
        assert "skill_bank" in missing
        assert "audit_logger" in missing
        assert "approval_gate" in missing

    def test_rag_optional(self):
        """RAG engine is optional — not in mandatory list."""
        contract = RuntimeWiringContract(
            model_registry=True,
            archivist=True,
            governance=True,
            skill_bank=True,
            audit_logger=True,
            approval_gate=True,
            rag_engine=False,
        )
        assert contract.validate_mandatory() == []

    def test_partial_missing(self):
        contract = RuntimeWiringContract(
            model_registry=True,
            archivist=True,
            governance=False,
            skill_bank=True,
            audit_logger=False,
            approval_gate=True,
        )
        missing = contract.validate_mandatory()
        assert missing == ["governance", "audit_logger"]

    def test_round_trip(self):
        contract = RuntimeWiringContract(
            model_registry=True,
            archivist=True,
            governance=True,
            skill_bank=True,
            audit_logger=True,
            approval_gate=True,
        )
        data = contract.model_dump()
        restored = RuntimeWiringContract.model_validate(data)
        assert restored.validate_mandatory() == []
