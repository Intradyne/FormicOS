"""
Tests for FormicOS v0.6.0 Audit Logger.

Covers:
- Buffer flushes when reaching 100 entries
- Buffer flushes after 5s timer (using asyncio)
- Rotation creates new files at 5MB threshold
- Events are valid JSON (can be parsed back)
- All log methods produce correct event_type
- Pydantic model payloads serialize correctly
- Disk write failure doesn't crash (logs to stderr)
- close() flushes remaining buffer
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from src.audit import (
    BUFFER_FLUSH_SIZE,
    ROTATION_SIZE_BYTES,
    AuditEntry,
    AuditLogger,
    _rotate_audit_file,
    _serialize_value,
)
from src.models import (
    AgentState,
    Caste,
    ColonyConfig,
    ColonyStatus,
    Decision,
    DecisionType,
    Episode,
    Topology,
    TopologyEdge,
)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def session_dir(tmp_path: Path) -> Path:
    """Provide a clean temporary session directory."""
    d = tmp_path / "sessions"
    d.mkdir()
    return d


@pytest.fixture
def audit_logger(session_dir: Path) -> AuditLogger:
    """Provide an AuditLogger instance pointed at the temp directory."""
    return AuditLogger(session_dir)


@pytest.fixture
def session_id() -> str:
    return "test-session-001"


# ═══════════════════════════════════════════════════════════════════════════
# AuditEntry Schema Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestAuditEntry:
    """Verify the AuditEntry Pydantic model."""

    def test_construction(self):
        entry = AuditEntry(
            timestamp=1234567890.0,
            session_id="sess-1",
            event_type="round",
            payload={"round_num": 1, "phase": "routing"},
        )
        assert entry.timestamp == 1234567890.0
        assert entry.session_id == "sess-1"
        assert entry.event_type == "round"
        assert entry.payload["round_num"] == 1

    def test_json_roundtrip(self):
        entry = AuditEntry(
            timestamp=time.time(),
            session_id="sess-1",
            event_type="decision",
            payload={"decision_type": "routing", "detail": "rerouted agent-1"},
        )
        json_str = entry.model_dump_json()
        restored = AuditEntry.model_validate_json(json_str)
        assert restored == entry


# ═══════════════════════════════════════════════════════════════════════════
# Serialization Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSerialization:
    """Verify Pydantic model_dump() serialization via _serialize_value."""

    def test_primitive_passthrough(self):
        assert _serialize_value("hello") == "hello"
        assert _serialize_value(42) == 42
        assert _serialize_value(3.14) == 3.14
        assert _serialize_value(True) is True
        assert _serialize_value(None) is None

    def test_pydantic_model_serialized(self):
        agent = AgentState(agent_id="a-1", caste=Caste.CODER)
        result = _serialize_value(agent)
        assert isinstance(result, dict)
        assert result["agent_id"] == "a-1"
        assert result["caste"] == "coder"

    def test_nested_pydantic_model(self):
        topo = Topology(
            edges=[TopologyEdge(sender="a", receiver="b", weight=0.5)],
            execution_order=["a", "b"],
            density=0.5,
        )
        result = _serialize_value(topo)
        assert isinstance(result, dict)
        assert len(result["edges"]) == 1
        assert result["edges"][0]["sender"] == "a"

    def test_dict_with_pydantic_values(self):
        data = {
            "agent": AgentState(agent_id="a-1", caste=Caste.MANAGER),
            "count": 5,
        }
        result = _serialize_value(data)
        assert isinstance(result["agent"], dict)
        assert result["agent"]["caste"] == "manager"
        assert result["count"] == 5

    def test_list_with_pydantic_items(self):
        decisions = [
            Decision(
                round_num=1,
                decision_type=DecisionType.ROUTING,
                detail="route to coder",
            ),
            Decision(
                round_num=2,
                decision_type=DecisionType.TERMINATION,
                detail="converged",
            ),
        ]
        result = _serialize_value(decisions)
        assert len(result) == 2
        assert result[0]["decision_type"] == "routing"
        assert result[1]["decision_type"] == "termination"

    def test_enum_value_extracted(self):
        assert _serialize_value(Caste.ARCHITECT) == "architect"
        assert _serialize_value(ColonyStatus.RUNNING) == "running"

    def test_non_serializable_falls_back_to_str(self):
        """Objects without model_dump or value attribute fall back to str()."""
        result = _serialize_value(object)
        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════════════
# Event Type Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestEventTypes:
    """Verify all log methods produce correct event_type values."""

    def test_log_round_event_type(self, audit_logger, session_id):
        audit_logger.log_round(session_id, 1, "routing", {"key": "val"})
        assert len(audit_logger._buffer) == 1
        assert audit_logger._buffer[0].event_type == "round"
        assert audit_logger._buffer[0].payload["round_num"] == 1
        assert audit_logger._buffer[0].payload["phase"] == "routing"

    def test_log_decision_event_type(self, audit_logger, session_id):
        audit_logger.log_decision(session_id, "routing", "rerouted agent-1")
        assert len(audit_logger._buffer) == 1
        assert audit_logger._buffer[0].event_type == "decision"
        assert audit_logger._buffer[0].payload["decision_type"] == "routing"
        assert audit_logger._buffer[0].payload["detail"] == "rerouted agent-1"

    def test_log_agent_action_event_type(self, audit_logger, session_id):
        audit_logger.log_agent_action(
            session_id, "agent-1", "tool_call", "called file_read"
        )
        assert len(audit_logger._buffer) == 1
        assert audit_logger._buffer[0].event_type == "agent_action"
        assert audit_logger._buffer[0].payload["agent_id"] == "agent-1"
        assert audit_logger._buffer[0].payload["action"] == "tool_call"

    def test_log_error_event_type(self, audit_logger, session_id):
        audit_logger.log_error(session_id, "timeout", "LLM timed out")
        assert len(audit_logger._buffer) == 1
        assert audit_logger._buffer[0].event_type == "error"
        assert audit_logger._buffer[0].payload["error_type"] == "timeout"
        assert "traceback" not in audit_logger._buffer[0].payload

    def test_log_error_with_traceback(self, audit_logger, session_id):
        audit_logger.log_error(
            session_id, "crash", "unexpected", traceback="Traceback ..."
        )
        entry = audit_logger._buffer[0]
        assert entry.payload["traceback"] == "Traceback ..."

    def test_log_session_start_event_type(self, audit_logger, session_id):
        audit_logger.log_session_start(
            session_id, "build a thing", {"max_rounds": 10}
        )
        assert len(audit_logger._buffer) == 1
        assert audit_logger._buffer[0].event_type == "session_start"
        assert audit_logger._buffer[0].payload["task"] == "build a thing"

    def test_log_session_end_event_type(self, audit_logger, session_id):
        audit_logger.log_session_end(session_id, "completed", "all goals met")
        assert len(audit_logger._buffer) == 1
        assert audit_logger._buffer[0].event_type == "session_end"
        assert audit_logger._buffer[0].payload["status"] == "completed"
        assert audit_logger._buffer[0].payload["outcome"] == "all goals met"

    def test_every_entry_has_required_fields(self, audit_logger, session_id):
        """Every log method must produce timestamp, session_id, event_type, payload."""
        audit_logger.log_round(session_id, 1, "execute", {})
        audit_logger.log_decision(session_id, "routing", "x")
        audit_logger.log_agent_action(session_id, "a1", "think", "d")
        audit_logger.log_error(session_id, "err", "msg")
        audit_logger.log_session_start(session_id, "task", {})
        audit_logger.log_session_end(session_id, "done", "ok")

        for entry in audit_logger._buffer:
            assert isinstance(entry.timestamp, float)
            assert entry.session_id == session_id
            assert isinstance(entry.event_type, str) and entry.event_type
            assert isinstance(entry.payload, dict)

    def test_timestamp_is_recent(self, audit_logger, session_id):
        before = time.time()
        audit_logger.log_round(session_id, 0, "init", {})
        after = time.time()
        ts = audit_logger._buffer[0].timestamp
        assert before <= ts <= after


# ═══════════════════════════════════════════════════════════════════════════
# Pydantic Payload Serialization Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPydanticPayloads:
    """Verify Pydantic models are correctly serialized in log payloads."""

    @pytest.mark.asyncio
    async def test_round_with_pydantic_data(self, audit_logger, session_id):
        episode = Episode(
            round_num=3,
            summary="completed phase 3",
            goal="build feature X",
            agent_outputs={"a1": "wrote code", "a2": "reviewed"},
        )
        audit_logger.log_round(session_id, 3, "summarize", episode)
        await audit_logger.flush()

        log_path = audit_logger._log_path(session_id)
        line = log_path.read_text(encoding="utf-8").strip()
        parsed = json.loads(line)

        data = parsed["payload"]["data"]
        assert isinstance(data, dict)
        assert data["round_num"] == 3
        assert data["summary"] == "completed phase 3"
        assert data["agent_outputs"]["a1"] == "wrote code"

    @pytest.mark.asyncio
    async def test_session_start_with_colony_config(
        self, audit_logger, session_id
    ):
        config = ColonyConfig(
            colony_id="col-1",
            task="build widget",
            max_rounds=5,
        )
        audit_logger.log_session_start(session_id, "build widget", config)
        await audit_logger.flush()

        log_path = audit_logger._log_path(session_id)
        line = log_path.read_text(encoding="utf-8").strip()
        parsed = json.loads(line)

        config_data = parsed["payload"]["config"]
        assert config_data["colony_id"] == "col-1"
        assert config_data["max_rounds"] == 5

    @pytest.mark.asyncio
    async def test_decision_enum_preserved(self, audit_logger, session_id):
        """DecisionType enum value should serialize as its string value."""
        audit_logger.log_decision(
            session_id,
            DecisionType.ESCALATION.value,
            "escalated to cloud",
        )
        await audit_logger.flush()

        log_path = audit_logger._log_path(session_id)
        line = log_path.read_text(encoding="utf-8").strip()
        parsed = json.loads(line)
        assert parsed["payload"]["decision_type"] == "escalation"


# ═══════════════════════════════════════════════════════════════════════════
# Buffer Flush Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestBufferFlush:
    """Verify buffering behavior: size threshold, timer, and explicit flush."""

    @pytest.mark.asyncio
    async def test_flush_writes_to_disk(
        self, audit_logger, session_id, session_dir
    ):
        audit_logger.log_round(session_id, 1, "routing", {"agents": 3})
        assert len(audit_logger._buffer) == 1

        await audit_logger.flush()
        assert len(audit_logger._buffer) == 0

        log_path = session_dir / session_id / "audit.jsonl"
        assert log_path.exists()

        content = log_path.read_text(encoding="utf-8").strip()
        parsed = json.loads(content)
        assert parsed["event_type"] == "round"

    @pytest.mark.asyncio
    async def test_buffer_flush_at_100_entries(
        self, session_dir, session_id
    ):
        """Buffer should auto-flush when reaching BUFFER_FLUSH_SIZE entries."""
        audit = AuditLogger(session_dir)

        # Fill buffer to exactly the threshold
        for i in range(BUFFER_FLUSH_SIZE):
            audit.log_round(session_id, i, "execute", {"i": i})

        # Give the overflow flush task a moment to run
        await asyncio.sleep(0.1)

        # Buffer should have been flushed
        assert len(audit._buffer) == 0

        log_path = session_dir / session_id / "audit.jsonl"
        assert log_path.exists()

        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == BUFFER_FLUSH_SIZE

        await audit.close()

    @pytest.mark.asyncio
    async def test_periodic_flush_timer(self, session_dir, session_id):
        """Buffer should flush after BUFFER_FLUSH_INTERVAL_SECONDS."""
        audit = AuditLogger(session_dir)

        # Temporarily reduce interval for fast test
        with patch("src.audit.BUFFER_FLUSH_INTERVAL_SECONDS", 0.2):
            # Re-create to pick up patched constant in _periodic_flush
            audit2 = AuditLogger(session_dir)
            audit2.log_round(session_id, 1, "routing", {})
            assert len(audit2._buffer) == 1

            # Wait for the periodic flush (patched to 0.2s)
            await asyncio.sleep(0.5)

            # Buffer should have been flushed by timer
            assert len(audit2._buffer) == 0

            log_path = session_dir / session_id / "audit.jsonl"
            assert log_path.exists()

            await audit2.close()

        await audit.close()

    @pytest.mark.asyncio
    async def test_flush_empty_buffer_is_noop(self, audit_logger):
        """Flushing an empty buffer should not create any files."""
        await audit_logger.flush()
        # No session dirs should have been created
        children = list(audit_logger._session_dir.iterdir())
        assert len(children) == 0

    @pytest.mark.asyncio
    async def test_multiple_sessions_in_buffer(self, audit_logger, session_dir):
        """Entries from different sessions go to separate files."""
        audit_logger.log_round("sess-A", 1, "routing", {})
        audit_logger.log_round("sess-B", 1, "routing", {})
        audit_logger.log_round("sess-A", 2, "execute", {})
        await audit_logger.flush()

        path_a = session_dir / "sess-A" / "audit.jsonl"
        path_b = session_dir / "sess-B" / "audit.jsonl"
        assert path_a.exists()
        assert path_b.exists()

        lines_a = path_a.read_text(encoding="utf-8").strip().split("\n")
        lines_b = path_b.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines_a) == 2
        assert len(lines_b) == 1


# ═══════════════════════════════════════════════════════════════════════════
# JSONL Validity Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestJSONLValidity:
    """Verify every written line is valid, parseable JSON."""

    @pytest.mark.asyncio
    async def test_all_event_types_produce_valid_jsonl(
        self, audit_logger, session_id
    ):
        audit_logger.log_round(session_id, 1, "routing", {"x": 1})
        audit_logger.log_decision(session_id, "routing", "route to a1")
        audit_logger.log_agent_action(session_id, "a1", "think", "reasoning")
        audit_logger.log_error(session_id, "timeout", "30s exceeded")
        audit_logger.log_session_start(session_id, "task", {"cfg": True})
        audit_logger.log_session_end(session_id, "completed", "done")
        await audit_logger.flush()

        log_path = audit_logger._log_path(session_id)
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 6

        expected_types = [
            "round",
            "decision",
            "agent_action",
            "error",
            "session_start",
            "session_end",
        ]
        for line, expected_type in zip(lines, expected_types):
            parsed = json.loads(line)  # Must not raise
            assert parsed["event_type"] == expected_type
            assert "timestamp" in parsed
            assert parsed["session_id"] == session_id
            assert isinstance(parsed["payload"], dict)

    @pytest.mark.asyncio
    async def test_entries_can_roundtrip_to_audit_entry(
        self, audit_logger, session_id
    ):
        """Written JSONL lines can be deserialized back into AuditEntry."""
        audit_logger.log_round(session_id, 5, "governance", {"agents": ["a"]})
        await audit_logger.flush()

        log_path = audit_logger._log_path(session_id)
        line = log_path.read_text(encoding="utf-8").strip()
        restored = AuditEntry.model_validate_json(line)
        assert restored.event_type == "round"
        assert restored.payload["round_num"] == 5


# ═══════════════════════════════════════════════════════════════════════════
# Log Rotation Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestLogRotation:
    """Verify log file rotation at 5MB threshold."""

    def test_no_rotation_under_threshold(self, tmp_path):
        """Files under 5MB should not be rotated."""
        log_file = tmp_path / "audit.jsonl"
        log_file.write_text("small content\n")
        _rotate_audit_file(log_file)
        assert log_file.exists()
        assert not (tmp_path / "audit.1.jsonl").exists()

    def test_rotation_at_threshold(self, tmp_path):
        """Files at/above 5MB should be rotated to .1.jsonl."""
        log_file = tmp_path / "audit.jsonl"
        # Write 5MB + 1 byte
        log_file.write_bytes(b"x" * (ROTATION_SIZE_BYTES + 1))

        _rotate_audit_file(log_file)

        # Original should be moved to .1
        assert not log_file.exists()
        assert (tmp_path / "audit.1.jsonl").exists()
        assert (tmp_path / "audit.1.jsonl").stat().st_size > ROTATION_SIZE_BYTES

    def test_rotation_shifts_existing_files(self, tmp_path):
        """Existing rotated files should be shifted: .1 -> .2, .2 -> .3."""
        log_file = tmp_path / "audit.jsonl"
        log_file.write_bytes(b"x" * (ROTATION_SIZE_BYTES + 1))

        # Pre-create rotated files
        (tmp_path / "audit.1.jsonl").write_text("old-1")
        (tmp_path / "audit.2.jsonl").write_text("old-2")

        _rotate_audit_file(log_file)

        assert not log_file.exists()
        assert (tmp_path / "audit.1.jsonl").stat().st_size > ROTATION_SIZE_BYTES
        assert (tmp_path / "audit.2.jsonl").read_text() == "old-1"
        assert (tmp_path / "audit.3.jsonl").read_text() == "old-2"

    def test_rotation_deletes_beyond_max(self, tmp_path):
        """Files beyond MAX_ROTATED_FILES should be deleted."""
        log_file = tmp_path / "audit.jsonl"
        log_file.write_bytes(b"x" * (ROTATION_SIZE_BYTES + 1))

        # Pre-create all rotated slots
        (tmp_path / "audit.1.jsonl").write_text("old-1")
        (tmp_path / "audit.2.jsonl").write_text("old-2")
        (tmp_path / "audit.3.jsonl").write_text("old-3")

        _rotate_audit_file(log_file)

        # .3 (max) should have been deleted, replaced by .2 -> .3
        assert (tmp_path / "audit.3.jsonl").read_text() == "old-2"
        # original old-3 is gone
        assert not (tmp_path / "audit.4.jsonl").exists()

    def test_rotation_nonexistent_file_is_noop(self, tmp_path):
        """Rotating a file that doesn't exist should be a no-op."""
        log_file = tmp_path / "nonexistent.jsonl"
        _rotate_audit_file(log_file)  # Should not raise

    @pytest.mark.asyncio
    async def test_rotation_triggered_by_flush(self, session_dir, session_id):
        """Flush should trigger rotation when the log file exceeds 5MB."""
        audit = AuditLogger(session_dir)
        log_path = audit._log_path(session_id)

        # Pre-fill log to just above threshold
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_bytes(b"x" * (ROTATION_SIZE_BYTES + 1))

        # Now log and flush -- should rotate before writing
        audit.log_round(session_id, 1, "execute", {})
        await audit.flush()

        # The old content should have been rotated to .1
        rotated = log_path.parent / "audit.1.jsonl"
        assert rotated.exists()
        assert rotated.stat().st_size > ROTATION_SIZE_BYTES

        # The new entry should be in the fresh file
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8").strip()
        parsed = json.loads(content)
        assert parsed["event_type"] == "round"

        await audit.close()


# ═══════════════════════════════════════════════════════════════════════════
# Error Resilience Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestErrorResilience:
    """Verify disk write failures don't crash the logger."""

    @pytest.mark.asyncio
    async def test_disk_write_failure_logs_to_stderr(
        self, audit_logger, session_id, capsys
    ):
        """If the write fails, error goes to stderr; no exception propagates."""
        audit_logger.log_round(session_id, 1, "routing", {})

        with patch.object(
            AuditLogger,
            "_write_lines_sync",
            side_effect=OSError("disk full"),
        ):
            await audit_logger.flush()  # Must NOT raise

        captured = capsys.readouterr()
        assert "Failed to flush" in captured.err
        assert "disk full" in captured.err

    @pytest.mark.asyncio
    async def test_disk_write_failure_clears_buffer(
        self, audit_logger, session_id
    ):
        """
        Buffer should be cleared even if write fails, to prevent
        unbounded memory growth.
        """
        audit_logger.log_round(session_id, 1, "routing", {})
        assert len(audit_logger._buffer) == 1

        with patch.object(
            AuditLogger,
            "_write_lines_sync",
            side_effect=PermissionError("no access"),
        ):
            await audit_logger.flush()

        # Buffer should be empty (entries were snapshotted and cleared)
        assert len(audit_logger._buffer) == 0

    @pytest.mark.asyncio
    async def test_permission_error_does_not_crash(
        self, audit_logger, session_id
    ):
        """PermissionError on file open should be caught gracefully."""
        audit_logger.log_error(session_id, "test", "msg")

        with patch.object(
            AuditLogger,
            "_write_lines_sync",
            side_effect=PermissionError("access denied"),
        ):
            await audit_logger.flush()  # Must NOT raise


# ═══════════════════════════════════════════════════════════════════════════
# Close Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestClose:
    """Verify close() flushes remaining buffer and stops timer."""

    @pytest.mark.asyncio
    async def test_close_flushes_remaining(
        self, audit_logger, session_id, session_dir
    ):
        audit_logger.log_round(session_id, 1, "routing", {})
        audit_logger.log_round(session_id, 2, "execute", {})
        assert len(audit_logger._buffer) == 2

        await audit_logger.close()

        assert len(audit_logger._buffer) == 0
        log_path = session_dir / session_id / "audit.jsonl"
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

    @pytest.mark.asyncio
    async def test_close_stops_periodic_flush(self, audit_logger, session_id):
        # Trigger periodic flush creation
        audit_logger.log_round(session_id, 1, "routing", {})
        await asyncio.sleep(0.05)  # Let task spin up

        await audit_logger.close()

        assert audit_logger._closed is True
        assert (
            audit_logger._flush_task is None
            or audit_logger._flush_task.done()
        )

    @pytest.mark.asyncio
    async def test_log_after_close_is_dropped(self, audit_logger, session_id):
        await audit_logger.close()

        # This should be silently dropped
        audit_logger.log_round(session_id, 1, "routing", {})
        assert len(audit_logger._buffer) == 0

    @pytest.mark.asyncio
    async def test_double_close_is_safe(self, audit_logger, session_id):
        audit_logger.log_round(session_id, 1, "routing", {})
        await audit_logger.close()
        await audit_logger.close()  # Should not raise


# ═══════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestIntegration:
    """End-to-end audit logging scenarios."""

    @pytest.mark.asyncio
    async def test_full_session_lifecycle(self, session_dir, session_id):
        """Simulate a complete colony session audit trail."""
        audit = AuditLogger(session_dir)

        config = ColonyConfig(colony_id="col-1", task="build it")
        audit.log_session_start(session_id, "build it", config)

        for round_num in range(1, 4):
            audit.log_round(session_id, round_num, "routing", {})
            audit.log_agent_action(
                session_id, f"agent-{round_num}", "execute", "did work"
            )
            audit.log_decision(
                session_id, "routing", f"round {round_num} routing"
            )

        audit.log_session_end(session_id, "completed", "all goals met")
        await audit.close()

        log_path = session_dir / session_id / "audit.jsonl"
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")

        # 1 start + 3*(round + action + decision) + 1 end = 11
        assert len(lines) == 11

        # Verify first and last entries
        first = json.loads(lines[0])
        last = json.loads(lines[-1])
        assert first["event_type"] == "session_start"
        assert last["event_type"] == "session_end"

        # Verify all lines are valid JSON
        for line in lines:
            parsed = json.loads(line)
            assert "timestamp" in parsed
            assert "session_id" in parsed
            assert "event_type" in parsed
            assert "payload" in parsed

    @pytest.mark.asyncio
    async def test_interleaved_sessions(self, session_dir):
        """Multiple concurrent sessions should write to separate files."""
        audit = AuditLogger(session_dir)

        audit.log_round("sess-A", 1, "routing", {})
        audit.log_round("sess-B", 1, "routing", {})
        audit.log_round("sess-A", 2, "execute", {})
        audit.log_round("sess-B", 2, "execute", {})
        await audit.close()

        for sid in ("sess-A", "sess-B"):
            log_path = session_dir / sid / "audit.jsonl"
            lines = log_path.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 2
            for line in lines:
                parsed = json.loads(line)
                assert parsed["session_id"] == sid

    @pytest.mark.asyncio
    async def test_large_batch_writes(self, session_dir, session_id):
        """Write more than BUFFER_FLUSH_SIZE entries and verify all are persisted."""
        audit = AuditLogger(session_dir)

        total = BUFFER_FLUSH_SIZE * 3 + 50  # 350 entries
        for i in range(total):
            audit.log_round(session_id, i, "execute", {"i": i})

        # Give auto-flush tasks time to complete
        await asyncio.sleep(0.3)
        await audit.close()

        log_path = session_dir / session_id / "audit.jsonl"
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == total
