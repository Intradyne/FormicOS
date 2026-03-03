"""
Tests for FormicOS REPL Telemetry Pipeline.

Covers:
1. formic_read_bytes emits structured log records via formicos.repl
2. formic_subcall emits structured log records (start + complete)
3. Log records carry correct extra fields (offset, length, target_caste, etc.)
4. AuditLogger.log_repl_event() writes action="repl_execution" entries
5. TUI REPLLogHandler bridges log records to Textual messages
6. Integration: harness execute → logger → audit capture
"""

from __future__ import annotations

import asyncio
import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from src.audit import AuditLogger
from src.core.repl.harness import REPLHarness


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def captured_records():
    """Attach a handler to formicos.repl that captures LogRecords."""
    records: list[logging.LogRecord] = []

    class Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    repl_logger = logging.getLogger("formicos.repl")
    handler = Collector(level=logging.DEBUG)
    repl_logger.addHandler(handler)
    old_level = repl_logger.level
    repl_logger.setLevel(logging.DEBUG)

    yield records

    repl_logger.removeHandler(handler)
    repl_logger.setLevel(old_level)


@pytest.fixture
def harness():
    """Minimal REPLHarness with mocked memory and router."""
    memory = MagicMock()
    memory.read_slice.return_value = b"hello world"
    router = MagicMock()
    loop = MagicMock()
    return REPLHarness(memory=memory, router=router, loop=loop)


# ── 1. formic_read_bytes Telemetry ────────────────────────────────────


class TestReadBytesTelemetry:
    """formic_read_bytes must emit structured log records."""

    def test_read_bytes_emits_log(self, harness, captured_records):
        result = harness.execute("data = formic_read_bytes(0, 4096)\nprint(len(data))")
        assert "11" in result  # len("hello world") == 11

        repl_events = [r for r in captured_records if hasattr(r, "repl_event")]
        assert len(repl_events) >= 1

        rec = repl_events[0]
        assert rec.repl_event == "formic_read_bytes"
        assert rec.offset == 0
        assert rec.length == 4096
        assert rec.actual_bytes == 11

    def test_read_bytes_log_message_format(self, harness, captured_records):
        harness.execute("formic_read_bytes(100, 2048)")
        repl_events = [r for r in captured_records if getattr(r, "repl_event", None) == "formic_read_bytes"]
        assert len(repl_events) == 1
        msg = repl_events[0].getMessage()
        assert "offset=100" in msg
        assert "length=2048" in msg

    def test_multiple_reads_emit_multiple_events(self, harness, captured_records):
        harness.execute(
            "for i in range(3):\n"
            "    formic_read_bytes(i * 100, 50)\n"
        )
        repl_events = [r for r in captured_records if getattr(r, "repl_event", None) == "formic_read_bytes"]
        assert len(repl_events) == 3
        # Offsets should be 0, 100, 200
        offsets = [r.offset for r in repl_events]
        assert offsets == [0, 100, 200]


# ── 2. formic_subcall Telemetry ───────────────────────────────────────


class TestSubcallTelemetry:
    """formic_subcall must emit start and complete log records."""

    def test_subcall_emits_start_log(self, captured_records):
        memory = MagicMock()
        memory.read_slice.return_value = b""
        router = MagicMock()
        loop = MagicMock(spec=asyncio.AbstractEventLoop)

        # Mock run_coroutine_threadsafe to return a completed future
        future = MagicMock()
        future.result.return_value = "sub-agent output"

        harness = REPLHarness(memory=memory, router=router, loop=loop)

        with patch("asyncio.run_coroutine_threadsafe", return_value=future):
            result = harness.execute(
                'result = formic_subcall("Fix the bug", "def foo(): pass", "Coder")\n'
                'print(result)'
            )

        assert "sub-agent output" in result

        # Should have both start and complete events
        start_events = [r for r in captured_records if getattr(r, "repl_event", None) == "formic_subcall"]
        complete_events = [r for r in captured_records if getattr(r, "repl_event", None) == "formic_subcall_complete"]

        assert len(start_events) == 1
        assert start_events[0].target_caste == "Coder"
        assert "Fix the bug" in start_events[0].task_preview
        assert start_events[0].data_slice_len == len("def foo(): pass")
        assert start_events[0].subcall_num == 1

        assert len(complete_events) == 1
        assert complete_events[0].target_caste == "Coder"
        assert complete_events[0].result_len == len("sub-agent output")

    def test_subcall_log_message_format(self, captured_records):
        memory = MagicMock()
        memory.read_slice.return_value = b""
        router = MagicMock()
        loop = MagicMock(spec=asyncio.AbstractEventLoop)

        future = MagicMock()
        future.result.return_value = "done"

        harness = REPLHarness(memory=memory, router=router, loop=loop)

        with patch("asyncio.run_coroutine_threadsafe", return_value=future):
            harness.execute('formic_subcall("Refactor code", "x = 1", "Reviewer")')

        start_events = [r for r in captured_records if getattr(r, "repl_event", None) == "formic_subcall"]
        assert len(start_events) == 1
        msg = start_events[0].getMessage()
        assert "target_caste=Reviewer" in msg
        assert "Refactor code" in msg


# ── 3. AuditLogger.log_repl_event() ──────────────────────────────────


class TestAuditReplEvent:
    """AuditLogger must capture REPL events with action=repl_execution."""

    @pytest.fixture
    def audit_logger(self, tmp_path):
        return AuditLogger(tmp_path / "sessions")

    def test_log_repl_event_buffer(self, audit_logger):
        audit_logger.log_repl_event(
            session_id="test-sess",
            event_name="formic_read_bytes",
            detail={"offset": 0, "length": 4096, "actual_bytes": 4096},
        )
        assert len(audit_logger._buffer) == 1
        entry = audit_logger._buffer[0]
        assert entry.event_type == "agent_action"
        assert entry.payload["action"] == "repl_execution"
        assert entry.payload["event"] == "formic_read_bytes"
        assert entry.payload["offset"] == 0
        assert entry.payload["length"] == 4096

    def test_log_repl_event_subcall(self, audit_logger):
        audit_logger.log_repl_event(
            session_id="test-sess",
            event_name="formic_subcall",
            detail={
                "target_caste": "Coder",
                "task_preview": "Fix the auth bug",
                "data_slice_len": 500,
            },
        )
        entry = audit_logger._buffer[0]
        assert entry.payload["action"] == "repl_execution"
        assert entry.payload["event"] == "formic_subcall"
        assert entry.payload["target_caste"] == "Coder"

    @pytest.mark.asyncio
    async def test_log_repl_event_writes_valid_jsonl(self, audit_logger, tmp_path):
        audit_logger.log_repl_event(
            session_id="sess-1",
            event_name="formic_read_bytes",
            detail={"offset": 1000, "length": 8192, "actual_bytes": 5000},
        )
        await audit_logger.flush()

        log_path = tmp_path / "sessions" / "sess-1" / "audit.jsonl"
        assert log_path.exists()
        parsed = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert parsed["event_type"] == "agent_action"
        assert parsed["payload"]["action"] == "repl_execution"
        assert parsed["payload"]["event"] == "formic_read_bytes"
        assert parsed["payload"]["actual_bytes"] == 5000

    @pytest.mark.asyncio
    async def test_multiple_repl_events_in_sequence(self, audit_logger, tmp_path):
        for i in range(5):
            audit_logger.log_repl_event(
                session_id="sess-1",
                event_name="formic_read_bytes",
                detail={"offset": i * 8192, "length": 8192, "actual_bytes": 8192},
            )
        audit_logger.log_repl_event(
            session_id="sess-1",
            event_name="formic_subcall",
            detail={"target_caste": "Coder", "task_preview": "Write tests"},
        )
        await audit_logger.flush()

        log_path = tmp_path / "sessions" / "sess-1" / "audit.jsonl"
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 6

        # All should be agent_action / repl_execution
        for line in lines:
            parsed = json.loads(line)
            assert parsed["payload"]["action"] == "repl_execution"

        # Last should be subcall
        last = json.loads(lines[-1])
        assert last["payload"]["event"] == "formic_subcall"


# ── 4. TUI Handler ───────────────────────────────────────────────────


class TestTUIHandler:
    """Verify REPLLogHandler bridges logging to Textual messages."""

    def test_handler_import(self):
        """TUI module should import without error."""
        from src.tui.app import REPLLogHandler, FormicOSTUI
        assert REPLLogHandler is not None
        assert FormicOSTUI is not None

    def test_handler_emits_message(self):
        """REPLLogHandler.emit() calls app.call_from_thread with REPLEvent."""
        from src.tui.app import REPLLogHandler, REPLEvent

        mock_app = MagicMock()
        handler = REPLLogHandler(mock_app)

        record = logging.LogRecord(
            name="formicos.repl",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="formic_read_bytes  offset=0  length=4096  actual=4096",
            args=None,
            exc_info=None,
        )
        record.repl_event = "formic_read_bytes"
        record.offset = 0
        record.length = 4096
        record.actual_bytes = 4096

        handler.emit(record)

        mock_app.call_from_thread.assert_called_once()
        call_args = mock_app.call_from_thread.call_args
        # First positional arg is post_message, second is the REPLEvent
        assert call_args[0][0] == mock_app.post_message
        event = call_args[0][1]
        assert isinstance(event, REPLEvent)
        assert event.record.repl_event == "formic_read_bytes"

    def test_handler_survives_app_not_running(self):
        """Handler should not raise if app.call_from_thread fails."""
        from src.tui.app import REPLLogHandler

        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = RuntimeError("no event loop")
        handler = REPLLogHandler(mock_app)

        record = logging.LogRecord(
            name="formicos.repl",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=None,
            exc_info=None,
        )

        # Must NOT raise
        handler.emit(record)


# ── 5. Integration: Harness → Logger → Audit ─────────────────────────


class TestIntegration:
    """End-to-end: harness execute triggers log, audit captures it."""

    def test_harness_read_captured_by_logger(self, harness, captured_records):
        """Execute code → formic_read_bytes → log record appears."""
        harness.execute("x = formic_read_bytes(0, 1024)")
        repl_events = [r for r in captured_records if hasattr(r, "repl_event")]
        assert any(r.repl_event == "formic_read_bytes" for r in repl_events)

    def test_blocked_code_still_logs_via_harness_logger(self, captured_records):
        """AST-blocked code logs a warning but no repl_event."""
        memory = MagicMock()
        router = MagicMock()
        loop = MagicMock()
        h = REPLHarness(memory=memory, router=router, loop=loop)

        result = h.execute("while True:\n    pass")
        assert "BLOCKED" in result

        # No repl_event records (code never reached exec)
        repl_events = [r for r in captured_records if hasattr(r, "repl_event")]
        assert len(repl_events) == 0

    @pytest.mark.asyncio
    async def test_audit_captures_harness_events(self, harness, tmp_path):
        """Wire a logging handler that feeds into AuditLogger."""
        audit = AuditLogger(tmp_path / "sessions")
        session_id = "integration-test"

        # Create a handler that bridges log records → audit
        class AuditBridge(logging.Handler):
            def emit(self_, record: logging.LogRecord) -> None:
                repl_event = getattr(record, "repl_event", None)
                if repl_event:
                    detail = {}
                    for key in ("offset", "length", "actual_bytes", "target_caste",
                                "task_preview", "data_slice_len", "subcall_num", "result_len"):
                        val = getattr(record, key, None)
                        if val is not None:
                            detail[key] = val
                    audit.log_repl_event(session_id, repl_event, detail)

        repl_logger = logging.getLogger("formicos.repl")
        bridge = AuditBridge(level=logging.DEBUG)
        repl_logger.addHandler(bridge)
        old_level = repl_logger.level
        repl_logger.setLevel(logging.DEBUG)

        try:
            harness.execute("formic_read_bytes(0, 2048)")
            harness.execute("formic_read_bytes(2048, 2048)")

            await audit.flush()

            log_path = tmp_path / "sessions" / session_id / "audit.jsonl"
            assert log_path.exists()
            lines = log_path.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 2

            for line in lines:
                parsed = json.loads(line)
                assert parsed["payload"]["action"] == "repl_execution"
                assert parsed["payload"]["event"] == "formic_read_bytes"
        finally:
            repl_logger.removeHandler(bridge)
            repl_logger.setLevel(old_level)
            await audit.close()
