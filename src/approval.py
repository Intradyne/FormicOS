"""
FormicOS v0.6.0 -- Approval Gate

Human-in-the-loop gating for high-risk tool calls.  Blocks agent execution
(via asyncio.Future) until a human approves or denies the operation, or until
the configurable timeout expires (default 5 minutes, auto-deny).

Supports a handler chain: multiple async handlers called sequentially for
audit, UI notification, and policy evaluation.  Handler errors are logged
and skipped -- remaining handlers still execute.

Design invariants:
  - Configurable required_actions per colony (not hardcoded).
  - Duplicate request_id: silently returns the existing pending future.
  - Actions NOT in required_actions list: auto-approve immediately (no blocking).
  - Thread-safe via asyncio primitives (no threading locks).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable

from src.models import ApprovalRecord, PendingApproval

log = logging.getLogger(__name__)

# Type alias for handler functions.
# A handler receives a PendingApproval and may perform side-effects
# (logging, sending a WS event, evaluating policy).  Return value is ignored.
HandlerFn = Callable[[PendingApproval], Awaitable[None]]


class ApprovalGate:
    """
    Manages approval gates for high-risk operations.

    Parameters
    ----------
    required_actions:
        List of tool/action names that require human approval.
        Actions not in this list are auto-approved immediately.
    timeout:
        Seconds to wait for a human response before auto-denying.
        Default: 300 (5 minutes).
    """

    def __init__(
        self,
        required_actions: list[str],
        timeout: float = 300.0,
    ) -> None:
        self._required_actions: set[str] = set(required_actions)
        self._timeout: float = timeout

        # request_id -> (PendingApproval, asyncio.Future[bool])
        self._pending: dict[str, tuple[PendingApproval, asyncio.Future[bool]]] = {}

        # Completed approval records (newest last).
        self._history: list[ApprovalRecord] = []

        # Ordered handler chain.
        self._handlers: list[HandlerFn] = []

    # ── Public API ────────────────────────────────────────────────────

    async def request_approval(
        self,
        action: str,
        detail: str,
        round_num: int = 0,
        agent_id: str = "",
    ) -> bool:
        """
        Request approval for *action*.

        If *action* is not in the required_actions list, returns ``True``
        immediately (auto-approve).

        Otherwise blocks until :meth:`respond` is called or the timeout
        expires.  Timeout results in auto-deny (``False``).

        Parameters
        ----------
        action:
            Tool or operation name (e.g. ``"file_delete"``).
        detail:
            Human-readable description of what the agent wants to do.
        round_num:
            Current orchestration round (informational).
        agent_id:
            ID of the requesting agent (informational).

        Returns
        -------
        bool
            ``True`` if approved, ``False`` if denied or timed out.
        """
        # Auto-approve actions not in the required list.
        if action not in self._required_actions:
            return True

        request_id = str(uuid.uuid4())

        # Build the pending approval model.
        pending = PendingApproval(
            request_id=request_id,
            agent_id=agent_id,
            tool=action,
            arguments={"detail": detail, "round_num": str(round_num)},
            requested_at=datetime.now(timezone.utc),
        )

        # Duplicate check -- if request_id already exists (astronomically
        # unlikely with uuid4, but the contract demands it), return the
        # existing future.
        if request_id in self._pending:
            log.warning("Duplicate request_id %s -- returning existing future", request_id)
            _, existing_future = self._pending[request_id]
            return await existing_future

        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._pending[request_id] = (pending, future)

        # Run handler chain (audit, UI, policy) -- errors logged & skipped.
        await self._run_handlers(pending)

        # Block until respond() resolves the future, or timeout.
        request_start = time.monotonic()
        try:
            approved = await asyncio.wait_for(future, timeout=self._timeout)
        except asyncio.TimeoutError:
            log.warning(
                "Approval request %s timed out after %.1fs -- auto-deny",
                request_id,
                self._timeout,
            )
            approved = False
            # Resolve the future so any other awaiter sees the result.
            if not future.done():
                future.set_result(False)

        # Record in history.
        elapsed = time.monotonic() - request_start
        record = ApprovalRecord(
            request_id=request_id,
            tool=action,
            approved=approved,
            responded_at=datetime.now(timezone.utc),
            response_time_seconds=round(elapsed, 4),
        )
        self._history.append(record)

        # Remove from pending.
        self._pending.pop(request_id, None)

        return approved

    def respond(self, request_id: str, approved: bool) -> None:
        """
        Resolve a pending approval request.

        Parameters
        ----------
        request_id:
            The ``request_id`` from the :class:`PendingApproval`.
        approved:
            ``True`` to approve, ``False`` to deny.

        Raises
        ------
        KeyError
            If *request_id* is not in the pending set.
        """
        if request_id not in self._pending:
            raise KeyError(f"No pending request with id {request_id!r}")

        _, future = self._pending[request_id]
        if not future.done():
            future.set_result(approved)

    def set_handler(self, handler_fn: HandlerFn) -> None:
        """
        Append *handler_fn* to the handler chain.

        Handlers are called sequentially in registration order when a new
        approval request is created.  Each handler receives the
        :class:`PendingApproval` and may perform side-effects (logging,
        UI notification, policy checks).  Handler errors are logged and
        skipped -- remaining handlers still execute.
        """
        self._handlers.append(handler_fn)

    def get_pending(self) -> list[PendingApproval]:
        """Return a snapshot of all currently pending approval requests."""
        return [pending for pending, _ in self._pending.values()]

    def get_history(self) -> list[ApprovalRecord]:
        """Return a snapshot of all resolved approval records."""
        return list(self._history)

    # ── Internal helpers ──────────────────────────────────────────────

    async def _run_handlers(self, pending: PendingApproval) -> None:
        """Execute every handler in the chain.  Log and skip on error."""
        for handler in self._handlers:
            try:
                await handler(pending)
            except Exception:
                log.exception(
                    "Handler %r raised an exception for request %s -- skipping",
                    handler,
                    pending.request_id,
                )
