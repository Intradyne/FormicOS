"""
FormicOS v0.8.0 — External Network Gateway

Outbound API gateway that routes HTTP requests through the EgressProxy
with CFO caste approval.  The gateway creates unsigned ExpenseRequests,
writes them to the context tree's colony scope as pending expenses, and
blocks (via asyncio.Future) until the CFO caste signs or denies them.

Design mirrors ApprovalGate (src/approval.py):
  - asyncio.Future for async blocking
  - Configurable timeout with auto-deny
  - Pending request tracking by nonce

Lifecycle follows ProxyRouter / WebhookDispatcher pattern:
  gateway = ExternalNetworkGateway(proxy, ctx, target_url)
  await gateway.start()
  result = await gateway.query("quantum computing")
  await gateway.stop()

Flow:
  1. Agent calls query(topic)
  2. Gateway creates unsigned ExpenseRequest for target URL
  3. Writes pending expense to ctx("colony", "pending_expenses")
  4. Blocks on asyncio.Future[SigningKey | None]
  5. CFO caste calls authorize(nonce, signing_key)
  6. Future resolves → gateway signs → proxy.forward() → return body
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import nacl.signing

from src.context import AsyncContextTree
from src.core.network.egress_proxy import ExpenseRequest, ProxyRouter

logger = logging.getLogger("formicos.external_gateway")


class ExternalNetworkGateway:
    """Outbound API gateway with CFO approval via EgressProxy.

    Parameters
    ----------
    proxy:
        Started ProxyRouter instance for forwarding signed requests.
    ctx:
        Colony AsyncContextTree for pending expense coordination.
    target_url:
        Base URL for external API queries.
    default_amount:
        USD cost per query (default $0.01).
    timeout:
        Seconds to wait for CFO authorization before auto-deny.
    """

    def __init__(
        self,
        proxy: ProxyRouter,
        ctx: AsyncContextTree,
        target_url: str = "https://en.wikipedia.org/api/rest_v1/page/summary",
        default_amount: float = 0.01,
        timeout: float = 120.0,
    ) -> None:
        self._proxy = proxy
        self._ctx = ctx
        self._target_url = target_url.rstrip("/")
        self._default_amount = default_amount
        self._timeout = timeout

        # nonce → (unsigned ExpenseRequest, Future resolving to SigningKey|None)
        self._pending: dict[
            str, tuple[ExpenseRequest, asyncio.Future[nacl.signing.SigningKey | None]]
        ] = {}
        self._started = False

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        """Mark the gateway as ready."""
        self._started = True
        logger.info("ExternalNetworkGateway started (target: %s)", self._target_url)

    async def stop(self) -> None:
        """Cancel all pending futures and shut down."""
        for nonce, (_, future) in self._pending.items():
            if not future.done():
                future.cancel()
        self._pending.clear()
        self._started = False
        logger.info("ExternalNetworkGateway stopped")

    # ── Main Tool ─────────────────────────────────────────────────────

    async def query(
        self,
        topic: str,
        justification: str | None = None,
    ) -> str:
        """Query an external network resource via the EgressProxy.

        Creates an unsigned ExpenseRequest, writes it to the context tree
        as a pending expense, and blocks until :meth:`authorize` or
        :meth:`deny` is called — or the timeout expires.

        Returns the response body on success, or an error string on failure.
        Never raises — follows the agent tool convention.
        """
        if not self._started:
            return "ERROR: ExternalNetworkGateway not started"

        target_api = f"{self._target_url}/{topic}"
        expense = ExpenseRequest(
            amount=self._default_amount,
            target_api=target_api,
            justification=justification or f"External knowledge query: {topic}",
        )

        loop = asyncio.get_running_loop()
        future: asyncio.Future[nacl.signing.SigningKey | None] = loop.create_future()
        self._pending[expense.nonce] = (expense, future)

        # Write pending expenses to context tree for CFO discovery
        await self._ctx.set(
            "colony", "pending_expenses", self.get_pending(),
        )

        logger.info(
            "Expense request queued — nonce=%s amount=%.2f target=%s",
            expense.nonce, expense.amount, target_api,
        )

        # Block until CFO authorizes, denies, or timeout
        try:
            signing_key = await asyncio.wait_for(future, timeout=self._timeout)
        except asyncio.TimeoutError:
            logger.warning(
                "CFO approval timed out for nonce=%s after %.1fs",
                expense.nonce, self._timeout,
            )
            self._pending.pop(expense.nonce, None)
            await self._sync_pending()
            return (
                f"ERROR: CFO approval timed out for nonce {expense.nonce} "
                f"after {self._timeout}s"
            )
        except asyncio.CancelledError:
            self._pending.pop(expense.nonce, None)
            await self._sync_pending()
            return "ERROR: Request cancelled (gateway stopping)"

        # CFO denied
        if signing_key is None:
            logger.info("CFO denied expense nonce=%s", expense.nonce)
            self._pending.pop(expense.nonce, None)
            await self._sync_pending()
            return f"ERROR: CFO denied expense request (nonce {expense.nonce})"

        # Sign and forward through proxy
        expense.sign(signing_key)
        response = await self._proxy.forward(expense)

        self._pending.pop(expense.nonce, None)
        await self._sync_pending()

        if response.forwarded:
            body = response.body
            if isinstance(body, dict):
                return json.dumps(body)
            return str(body) if body is not None else ""
        return f"ERROR: Proxy rejected request: {response.error}"

    # ── CFO Interface ─────────────────────────────────────────────────

    def authorize(
        self,
        nonce: str,
        signing_key: nacl.signing.SigningKey,
    ) -> None:
        """Authorize a pending expense by providing the CFO signing key.

        Called by the CFO caste to unblock a waiting :meth:`query`.

        Raises
        ------
        KeyError
            If *nonce* is not in the pending set.
        """
        if nonce not in self._pending:
            raise KeyError(f"No pending expense with nonce {nonce!r}")
        _, future = self._pending[nonce]
        if not future.done():
            future.set_result(signing_key)

    def deny(self, nonce: str) -> None:
        """Deny a pending expense request.

        Raises
        ------
        KeyError
            If *nonce* is not in the pending set.
        """
        if nonce not in self._pending:
            raise KeyError(f"No pending expense with nonce {nonce!r}")
        _, future = self._pending[nonce]
        if not future.done():
            future.set_result(None)

    # ── Inspection ────────────────────────────────────────────────────

    def get_pending(self) -> list[dict[str, Any]]:
        """Return a snapshot of pending expense requests for CFO discovery."""
        return [
            {
                "nonce": req.nonce,
                "amount": req.amount,
                "target_api": req.target_api,
                "justification": req.justification,
                "timestamp": req.timestamp,
            }
            for req, _ in self._pending.values()
        ]

    # ── Internal ──────────────────────────────────────────────────────

    async def _sync_pending(self) -> None:
        """Update context tree with current pending expenses."""
        await self._ctx.set(
            "colony", "pending_expenses", self.get_pending(),
        )
