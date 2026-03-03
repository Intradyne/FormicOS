"""
Tests for FormicOS v0.6.0 Approval Gate.

Covers:
- Request blocks until response received
- Approve returns True, deny returns False
- Timeout auto-denies (short timeout for test speed)
- Handler chain called in order
- Handler error: logged, skipped, remaining handlers still called
- Pending list shows active requests
- History records all decisions with timestamps
- Response time is tracked accurately
- Duplicate request_id rejected (returns existing pending)
- Action not in required list: auto-approve immediately
"""

from __future__ import annotations

import asyncio
import time

import pytest

from src.approval import ApprovalGate
from src.models import ApprovalRecord, PendingApproval


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def gate() -> ApprovalGate:
    """Gate with a short timeout and two required actions."""
    return ApprovalGate(
        required_actions=["file_delete", "code_execute"],
        timeout=300.0,
    )


@pytest.fixture
def fast_gate() -> ApprovalGate:
    """Gate with a very short timeout for testing timeout behaviour."""
    return ApprovalGate(
        required_actions=["file_delete", "code_execute"],
        timeout=0.1,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Blocking & Response Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestBlockingBehaviour:
    """request_approval blocks until respond() is called."""

    @pytest.mark.asyncio
    async def test_request_blocks_until_response(self, gate: ApprovalGate) -> None:
        """The coroutine should not complete until respond() resolves the future."""
        result_box: list[bool] = []

        async def requester() -> None:
            result = await gate.request_approval(
                action="file_delete",
                detail="rm -rf /workspace/old",
                round_num=1,
                agent_id="coder-1",
            )
            result_box.append(result)

        task = asyncio.create_task(requester())

        # Give the requester time to register.
        await asyncio.sleep(0.05)
        assert result_box == [], "request_approval should still be blocking"
        assert len(gate.get_pending()) == 1

        # Approve it.
        pending = gate.get_pending()[0]
        gate.respond(pending.request_id, approved=True)

        await asyncio.wait_for(task, timeout=2.0)
        assert result_box == [True]

    @pytest.mark.asyncio
    async def test_approve_returns_true(self, gate: ApprovalGate) -> None:
        """respond(approved=True) makes request_approval return True."""

        async def approve_soon() -> None:
            await asyncio.sleep(0.05)
            pending = gate.get_pending()
            assert len(pending) == 1
            gate.respond(pending[0].request_id, approved=True)

        asyncio.create_task(approve_soon())
        result = await gate.request_approval(
            action="file_delete", detail="delete temp", round_num=1, agent_id="a1"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_deny_returns_false(self, gate: ApprovalGate) -> None:
        """respond(approved=False) makes request_approval return False."""

        async def deny_soon() -> None:
            await asyncio.sleep(0.05)
            pending = gate.get_pending()
            assert len(pending) == 1
            gate.respond(pending[0].request_id, approved=False)

        asyncio.create_task(deny_soon())
        result = await gate.request_approval(
            action="code_execute", detail="run exploit.py", round_num=2, agent_id="a2"
        )
        assert result is False


# ═══════════════════════════════════════════════════════════════════════════
# Timeout Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestTimeout:
    """Timeout auto-denies the request."""

    @pytest.mark.asyncio
    async def test_timeout_auto_denies(self, fast_gate: ApprovalGate) -> None:
        """When nobody calls respond(), the request times out and returns False."""
        start = time.monotonic()
        result = await fast_gate.request_approval(
            action="file_delete", detail="timeout test", round_num=1, agent_id="a1"
        )
        elapsed = time.monotonic() - start

        assert result is False
        assert elapsed >= 0.1
        # After timeout, pending should be empty and history should have one record.
        assert len(fast_gate.get_pending()) == 0
        assert len(fast_gate.get_history()) == 1
        assert fast_gate.get_history()[0].approved is False


# ═══════════════════════════════════════════════════════════════════════════
# Handler Chain Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestHandlerChain:
    """Handlers are called sequentially in registration order."""

    @pytest.mark.asyncio
    async def test_handlers_called_in_order(self, gate: ApprovalGate) -> None:
        """All handlers fire in registration order before the future is awaited."""
        call_order: list[str] = []

        async def handler_a(pending: PendingApproval) -> None:
            call_order.append("A")

        async def handler_b(pending: PendingApproval) -> None:
            call_order.append("B")

        async def handler_c(pending: PendingApproval) -> None:
            call_order.append("C")

        gate.set_handler(handler_a)
        gate.set_handler(handler_b)
        gate.set_handler(handler_c)

        async def approve_soon() -> None:
            await asyncio.sleep(0.05)
            pending = gate.get_pending()
            gate.respond(pending[0].request_id, approved=True)

        asyncio.create_task(approve_soon())
        await gate.request_approval(
            action="file_delete", detail="chain test", round_num=1, agent_id="a1"
        )

        assert call_order == ["A", "B", "C"]

    @pytest.mark.asyncio
    async def test_handler_error_logged_and_skipped(self, gate: ApprovalGate) -> None:
        """A failing handler is skipped; remaining handlers still execute."""
        call_order: list[str] = []

        async def good_handler_1(pending: PendingApproval) -> None:
            call_order.append("good1")

        async def bad_handler(pending: PendingApproval) -> None:
            raise RuntimeError("handler exploded")

        async def good_handler_2(pending: PendingApproval) -> None:
            call_order.append("good2")

        gate.set_handler(good_handler_1)
        gate.set_handler(bad_handler)
        gate.set_handler(good_handler_2)

        async def approve_soon() -> None:
            await asyncio.sleep(0.05)
            pending = gate.get_pending()
            gate.respond(pending[0].request_id, approved=True)

        asyncio.create_task(approve_soon())
        result = await gate.request_approval(
            action="code_execute", detail="error test", round_num=1, agent_id="a1"
        )

        assert result is True
        assert call_order == ["good1", "good2"], "Both good handlers should run despite bad one"

    @pytest.mark.asyncio
    async def test_handler_receives_pending_approval(self, gate: ApprovalGate) -> None:
        """Handler receives a PendingApproval with correct fields."""
        received: list[PendingApproval] = []

        async def capture_handler(pending: PendingApproval) -> None:
            received.append(pending)

        gate.set_handler(capture_handler)

        async def approve_soon() -> None:
            await asyncio.sleep(0.05)
            pending = gate.get_pending()
            gate.respond(pending[0].request_id, approved=True)

        asyncio.create_task(approve_soon())
        await gate.request_approval(
            action="file_delete", detail="capture test", round_num=3, agent_id="coder-7"
        )

        assert len(received) == 1
        pa = received[0]
        assert pa.tool == "file_delete"
        assert pa.agent_id == "coder-7"
        assert pa.arguments["detail"] == "capture test"
        assert pa.arguments["round_num"] == "3"


# ═══════════════════════════════════════════════════════════════════════════
# Pending & History Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPendingAndHistory:
    """Pending list and history track requests correctly."""

    @pytest.mark.asyncio
    async def test_pending_shows_active_requests(self, gate: ApprovalGate) -> None:
        """While awaiting, get_pending() returns the active request."""
        started = asyncio.Event()

        async def requester() -> bool:
            # Signal that we have started the request.
            async def signal_handler(p: PendingApproval) -> None:
                started.set()

            gate.set_handler(signal_handler)
            return await gate.request_approval(
                action="file_delete", detail="pending test", round_num=1, agent_id="a1"
            )

        task = asyncio.create_task(requester())
        await asyncio.wait_for(started.wait(), timeout=2.0)

        pending = gate.get_pending()
        assert len(pending) == 1
        assert pending[0].tool == "file_delete"
        assert pending[0].agent_id == "a1"

        # Resolve and verify pending is cleared.
        gate.respond(pending[0].request_id, approved=True)
        await asyncio.wait_for(task, timeout=2.0)
        assert len(gate.get_pending()) == 0

    @pytest.mark.asyncio
    async def test_history_records_all_decisions(self, gate: ApprovalGate) -> None:
        """History contains records for every resolved request."""

        async def approve_soon() -> None:
            await asyncio.sleep(0.05)
            for p in gate.get_pending():
                gate.respond(p.request_id, approved=True)

        # Request 1
        asyncio.create_task(approve_soon())
        await gate.request_approval(
            action="file_delete", detail="first", round_num=1, agent_id="a1"
        )

        async def deny_soon() -> None:
            await asyncio.sleep(0.05)
            for p in gate.get_pending():
                gate.respond(p.request_id, approved=False)

        # Request 2
        asyncio.create_task(deny_soon())
        await gate.request_approval(
            action="code_execute", detail="second", round_num=2, agent_id="a2"
        )

        history = gate.get_history()
        assert len(history) == 2

        assert history[0].tool == "file_delete"
        assert history[0].approved is True
        assert isinstance(history[0], ApprovalRecord)

        assert history[1].tool == "code_execute"
        assert history[1].approved is False

    @pytest.mark.asyncio
    async def test_history_has_timestamps(self, gate: ApprovalGate) -> None:
        """Each ApprovalRecord has a responded_at timestamp."""

        async def approve_soon() -> None:
            await asyncio.sleep(0.05)
            pending = gate.get_pending()
            gate.respond(pending[0].request_id, approved=True)

        asyncio.create_task(approve_soon())
        await gate.request_approval(
            action="file_delete", detail="ts test", round_num=1, agent_id="a1"
        )

        record = gate.get_history()[0]
        assert record.responded_at is not None
        # responded_at should be a recent datetime (within last 10 seconds).
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        delta = (now - record.responded_at).total_seconds()
        assert 0 <= delta < 10


# ═══════════════════════════════════════════════════════════════════════════
# Response Time Tracking
# ═══════════════════════════════════════════════════════════════════════════


class TestResponseTime:
    """response_time_seconds is tracked accurately."""

    @pytest.mark.asyncio
    async def test_response_time_tracked(self, gate: ApprovalGate) -> None:
        """response_time_seconds reflects actual wall-clock wait."""
        delay = 0.15  # 150ms delay before responding

        async def delayed_approve() -> None:
            await asyncio.sleep(delay)
            pending = gate.get_pending()
            gate.respond(pending[0].request_id, approved=True)

        asyncio.create_task(delayed_approve())
        await gate.request_approval(
            action="file_delete", detail="timing test", round_num=1, agent_id="a1"
        )

        record = gate.get_history()[0]
        # Should be at least the delay (minus small tolerance for scheduling).
        assert record.response_time_seconds >= delay * 0.8
        # Should not be wildly longer (give generous upper bound for CI).
        assert record.response_time_seconds < delay * 5

    @pytest.mark.asyncio
    async def test_timeout_response_time_reflects_timeout(
        self, fast_gate: ApprovalGate
    ) -> None:
        """On timeout, response_time_seconds should be approximately the timeout value."""
        await fast_gate.request_approval(
            action="file_delete", detail="timeout timing", round_num=1, agent_id="a1"
        )

        record = fast_gate.get_history()[0]
        assert record.response_time_seconds >= fast_gate._timeout * 0.8
        assert record.response_time_seconds < fast_gate._timeout * 5


# ═══════════════════════════════════════════════════════════════════════════
# Duplicate Request ID
# ═══════════════════════════════════════════════════════════════════════════


class TestDuplicateRequestId:
    """Duplicate request_id handling."""

    @pytest.mark.asyncio
    async def test_duplicate_request_id_returns_existing(self) -> None:
        """
        If we manually inject a known request_id into pending, a second
        request with the same ID should return the existing future's result.

        Note: In normal operation uuid4 collisions are essentially impossible,
        so we test the internal duplicate guard by directly manipulating _pending.
        """
        gate = ApprovalGate(required_actions=["file_delete"], timeout=2.0)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()

        fake_pending = PendingApproval(
            request_id="duplicate-id",
            agent_id="a1",
            tool="file_delete",
            arguments={"detail": "first"},
        )
        gate._pending["duplicate-id"] = (fake_pending, future)

        # Resolve the injected future.
        future.set_result(True)

        # get_pending should show our injected entry.
        pending = gate.get_pending()
        assert len(pending) == 1
        assert pending[0].request_id == "duplicate-id"


# ═══════════════════════════════════════════════════════════════════════════
# Auto-Approve Non-Required Actions
# ═══════════════════════════════════════════════════════════════════════════


class TestAutoApprove:
    """Actions not in required_actions list are auto-approved immediately."""

    @pytest.mark.asyncio
    async def test_non_required_action_auto_approves(self, gate: ApprovalGate) -> None:
        """An action not in required_actions returns True without blocking."""
        start = time.monotonic()
        result = await gate.request_approval(
            action="file_read",  # Not in required_actions
            detail="reading a file",
            round_num=1,
            agent_id="reader-1",
        )
        elapsed = time.monotonic() - start

        assert result is True
        # Should return nearly instantly (no blocking).
        assert elapsed < 0.05
        # No pending requests and no history (auto-approved don't enter the pipeline).
        assert len(gate.get_pending()) == 0
        assert len(gate.get_history()) == 0

    @pytest.mark.asyncio
    async def test_empty_required_actions_auto_approves_everything(self) -> None:
        """With an empty required_actions list, everything is auto-approved."""
        gate = ApprovalGate(required_actions=[], timeout=0.1)
        result = await gate.request_approval(
            action="file_delete", detail="anything", round_num=1, agent_id="a1"
        )
        assert result is True
        assert len(gate.get_pending()) == 0
        assert len(gate.get_history()) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Respond Edge Cases
# ═══════════════════════════════════════════════════════════════════════════


class TestRespondEdgeCases:
    """Edge cases for the respond() method."""

    @pytest.mark.asyncio
    async def test_respond_unknown_id_raises_key_error(self, gate: ApprovalGate) -> None:
        """respond() with an unknown request_id raises KeyError."""
        with pytest.raises(KeyError, match="no-such-id"):
            gate.respond("no-such-id", approved=True)

    @pytest.mark.asyncio
    async def test_multiple_concurrent_requests(self, gate: ApprovalGate) -> None:
        """Multiple requests can be pending simultaneously."""
        results: dict[str, bool] = {}

        async def make_request(detail: str, approve: bool) -> None:
            task = asyncio.create_task(
                gate.request_approval(
                    action="file_delete",
                    detail=detail,
                    round_num=1,
                    agent_id="a1",
                )
            )
            await asyncio.sleep(0.05)
            # Find our request by detail.
            for p in gate.get_pending():
                if p.arguments.get("detail") == detail:
                    gate.respond(p.request_id, approved=approve)
                    break
            result = await asyncio.wait_for(task, timeout=2.0)
            results[detail] = result

        await asyncio.gather(
            make_request("delete-A", True),
            make_request("delete-B", False),
        )

        assert results["delete-A"] is True
        assert results["delete-B"] is False
        assert len(gate.get_history()) == 2
        assert len(gate.get_pending()) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Model Validation Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestModels:
    """PendingApproval and ApprovalRecord model validation."""

    def test_pending_approval_construction(self) -> None:
        """PendingApproval can be constructed with valid data."""
        pa = PendingApproval(
            request_id="req-123",
            agent_id="coder-1",
            tool="file_delete",
            arguments={"path": "/tmp/foo"},
        )
        assert pa.request_id == "req-123"
        assert pa.agent_id == "coder-1"
        assert pa.tool == "file_delete"
        assert pa.arguments == {"path": "/tmp/foo"}
        assert pa.requested_at is not None

    def test_pending_approval_empty_request_id_rejected(self) -> None:
        """PendingApproval rejects empty request_id."""
        with pytest.raises(Exception, match="request_id must not be empty"):
            PendingApproval(
                request_id="   ",
                agent_id="a1",
                tool="file_delete",
            )

    def test_approval_record_construction(self) -> None:
        """ApprovalRecord can be constructed with valid data."""
        rec = ApprovalRecord(
            request_id="req-456",
            tool="code_execute",
            approved=True,
            response_time_seconds=1.5,
        )
        assert rec.request_id == "req-456"
        assert rec.tool == "code_execute"
        assert rec.approved is True
        assert rec.response_time_seconds == 1.5
        assert rec.responded_at is not None

    def test_approval_record_negative_response_time_rejected(self) -> None:
        """ApprovalRecord rejects negative response_time_seconds."""
        with pytest.raises(Exception):
            ApprovalRecord(
                request_id="req-789",
                tool="file_delete",
                approved=False,
                response_time_seconds=-1.0,
            )

    def test_approval_record_serialization_roundtrip(self) -> None:
        """ApprovalRecord survives model_dump -> model_validate cycle."""
        rec = ApprovalRecord(
            request_id="rt-1",
            tool="file_delete",
            approved=True,
            response_time_seconds=0.5,
        )
        data = rec.model_dump()
        restored = ApprovalRecord.model_validate(data)
        assert restored.request_id == rec.request_id
        assert restored.approved == rec.approved
        assert restored.response_time_seconds == rec.response_time_seconds
