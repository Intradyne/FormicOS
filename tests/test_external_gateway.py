"""
Tests for FormicOS External Network Gateway.

Covers the full CFO approval flow:
1. Gateway lifecycle (start/stop)
2. Pending expense queuing and context tree integration
3. CFO authorization (sign → forward → return)
4. CFO denial
5. Timeout auto-deny
6. Proxy rejection handling
7. Concurrent queries
8. End-to-end integration (keypair → sign → verify → forward)
"""

from __future__ import annotations

import asyncio
import json

import nacl.signing
import pytest

from src.context import AsyncContextTree
from src.core.network.egress_proxy import (
    KeyVault,
    ProxyRouter,
    generate_keypair,
)
from src.mcp.external_client import ExternalNetworkGateway


# ── Helpers ───────────────────────────────────────────────────────────────


class FakeResponse:
    """Mock httpx.Response."""

    def __init__(
        self,
        status_code: int = 200,
        json_data: dict | None = None,
        text: str = "ok",
    ):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        if self._json is not None:
            return self._json
        raise ValueError("No JSON")


class FakeClient:
    """Mock httpx.AsyncClient."""

    def __init__(self, responses: list | None = None):
        self._responses = responses or [
            FakeResponse(200, {"result": "external data"}),
        ]
        self._call_count = 0
        self.last_url: str | None = None
        self.last_json: dict | None = None

    async def post(self, url: str, **kwargs):
        self.last_url = url
        self.last_json = kwargs.get("json")
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        resp = self._responses[idx]
        if isinstance(resp, Exception):
            raise resp
        return resp

    async def aclose(self):
        pass


def _make_gateway(
    sk: nacl.signing.SigningKey | None = None,
    vk: nacl.signing.VerifyKey | None = None,
    fake_responses: list | None = None,
    timeout: float = 5.0,
    target_url: str = "https://api.example.com/v1/search",
) -> tuple[ExternalNetworkGateway, ProxyRouter, AsyncContextTree, nacl.signing.SigningKey]:
    """Create a fully wired gateway with mocked proxy for testing."""
    if sk is None or vk is None:
        sk, vk = generate_keypair()
    vault = KeyVault(vk)
    proxy = ProxyRouter(vault)
    proxy._client = FakeClient(fake_responses)
    ctx = AsyncContextTree()
    gateway = ExternalNetworkGateway(
        proxy=proxy,
        ctx=ctx,
        target_url=target_url,
        timeout=timeout,
    )
    return gateway, proxy, ctx, sk


# ── 1. Lifecycle ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_not_started_returns_error():
    """query() before start() returns an error string."""
    gateway, _, _, _ = _make_gateway()
    result = await gateway.query("test")
    assert result.startswith("ERROR")
    assert "not started" in result


@pytest.mark.asyncio
async def test_start_stop_lifecycle():
    """start() enables queries, stop() cancels pending."""
    gateway, _, _, _ = _make_gateway()
    assert not gateway._started
    await gateway.start()
    assert gateway._started
    await gateway.stop()
    assert not gateway._started


# ── 2. Pending Expense Queuing ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_writes_pending_to_context_tree():
    """After query() starts blocking, context tree has pending_expenses."""
    gateway, _, ctx, sk = _make_gateway(timeout=2.0)
    await gateway.start()

    # Launch query as background task (it will block waiting for CFO)
    task = asyncio.create_task(gateway.query("quantum computing"))
    await asyncio.sleep(0)  # yield to let query run to the await point

    # Verify pending expense written to context tree
    pending = ctx.get("colony", "pending_expenses", [])
    assert len(pending) == 1
    assert pending[0]["target_api"] == "https://api.example.com/v1/search/quantum computing"
    assert pending[0]["amount"] == 0.01
    assert "nonce" in pending[0]

    # Authorize to unblock
    nonce = pending[0]["nonce"]
    gateway.authorize(nonce, sk)
    await task

    await gateway.stop()


# ── 3. CFO Authorization Flow ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_authorize_unblocks_query():
    """Core flow: query blocks → authorize → signed request forwarded → body returned."""
    sk, vk = generate_keypair()
    gateway, proxy, ctx, _ = _make_gateway(sk=sk, vk=vk)
    await gateway.start()

    task = asyncio.create_task(gateway.query("AI research"))
    await asyncio.sleep(0)

    # CFO reads pending, authorizes
    pending = gateway.get_pending()
    assert len(pending) == 1
    nonce = pending[0]["nonce"]

    gateway.authorize(nonce, sk)
    result = await task

    # Verify result contains the mock response body
    assert "external data" in result

    # Verify the proxy received the request and it was signed
    assert proxy._client.last_url == "https://api.example.com/v1/search/AI research"

    # Verify pending cleared
    assert gateway.get_pending() == []
    assert ctx.get("colony", "pending_expenses", []) == []

    await gateway.stop()


@pytest.mark.asyncio
async def test_authorize_unknown_nonce_raises():
    """authorize() with unknown nonce raises KeyError."""
    gateway, _, _, _ = _make_gateway()
    await gateway.start()

    with pytest.raises(KeyError, match="No pending expense"):
        gateway.authorize("nonexistent-nonce", generate_keypair()[0])

    await gateway.stop()


# ── 4. CFO Denial ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deny_unblocks_query_with_error():
    """deny() resolves the future with None → query returns error string."""
    gateway, _, _, _ = _make_gateway()
    await gateway.start()

    task = asyncio.create_task(gateway.query("risky query"))
    await asyncio.sleep(0)

    nonce = gateway.get_pending()[0]["nonce"]
    gateway.deny(nonce)
    result = await task

    assert result.startswith("ERROR")
    assert "denied" in result
    assert gateway.get_pending() == []

    await gateway.stop()


@pytest.mark.asyncio
async def test_deny_unknown_nonce_raises():
    """deny() with unknown nonce raises KeyError."""
    gateway, _, _, _ = _make_gateway()
    await gateway.start()

    with pytest.raises(KeyError):
        gateway.deny("bad-nonce")

    await gateway.stop()


# ── 5. Timeout ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_timeout_returns_error():
    """Short timeout → auto-deny error string."""
    gateway, _, _, _ = _make_gateway(timeout=0.05)
    await gateway.start()

    result = await gateway.query("slow topic")

    assert result.startswith("ERROR")
    assert "timed out" in result

    await gateway.stop()


@pytest.mark.asyncio
async def test_timeout_clears_pending():
    """After timeout, pending list is empty."""
    gateway, _, ctx, _ = _make_gateway(timeout=0.05)
    await gateway.start()

    await gateway.query("slow topic")

    assert gateway.get_pending() == []
    assert ctx.get("colony", "pending_expenses", []) == []

    await gateway.stop()


# ── 6. Proxy Rejection ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_proxy_rejection_returns_error():
    """Proxy forwarded=False → error string returned to agent."""
    sk, vk = generate_keypair()
    # Use a different verify key so signature fails at the proxy
    _, wrong_vk = generate_keypair()
    vault = KeyVault(wrong_vk)
    proxy = ProxyRouter(vault)
    proxy._client = FakeClient()
    ctx = AsyncContextTree()
    gateway = ExternalNetworkGateway(
        proxy=proxy, ctx=ctx, target_url="https://api.example.com", timeout=5.0,
    )
    await gateway.start()

    task = asyncio.create_task(gateway.query("test"))
    await asyncio.sleep(0)

    nonce = gateway.get_pending()[0]["nonce"]
    gateway.authorize(nonce, sk)  # sign with sk, but proxy has wrong_vk
    result = await task

    assert result.startswith("ERROR")
    assert "rejected" in result.lower() or "verification failed" in result.lower()

    await gateway.stop()


# ── 7. Stop Cancels Pending ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stop_cancels_pending():
    """stop() cancels waiting futures gracefully."""
    gateway, _, _, _ = _make_gateway(timeout=60.0)
    await gateway.start()

    task = asyncio.create_task(gateway.query("will be cancelled"))
    await asyncio.sleep(0)

    assert len(gateway.get_pending()) == 1
    await gateway.stop()

    result = await task
    assert "ERROR" in result


# ── 8. Concurrent Queries ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_multiple_concurrent_queries():
    """3 concurrent queries, authorized independently."""
    sk, vk = generate_keypair()
    gateway, _, ctx, _ = _make_gateway(sk=sk, vk=vk)
    await gateway.start()

    tasks = [
        asyncio.create_task(gateway.query(f"topic_{i}"))
        for i in range(3)
    ]
    await asyncio.sleep(0)

    pending = gateway.get_pending()
    assert len(pending) == 3

    # Authorize in reverse order
    for p in reversed(pending):
        gateway.authorize(p["nonce"], sk)

    results = await asyncio.gather(*tasks)
    assert all("external data" in r for r in results)
    assert gateway.get_pending() == []

    await gateway.stop()


# ── 9. Context Tree Updated After Completion ──────────────────────────────


@pytest.mark.asyncio
async def test_context_tree_updated_after_completion():
    """pending_expenses cleared from context tree after successful forward."""
    sk, vk = generate_keypair()
    gateway, _, ctx, _ = _make_gateway(sk=sk, vk=vk)
    await gateway.start()

    task = asyncio.create_task(gateway.query("ephemeral"))
    await asyncio.sleep(0)

    # Verify pending in context tree
    assert len(ctx.get("colony", "pending_expenses", [])) == 1

    nonce = gateway.get_pending()[0]["nonce"]
    gateway.authorize(nonce, sk)
    await task

    # Verify cleared
    assert ctx.get("colony", "pending_expenses", []) == []

    await gateway.stop()


# ── 10. End-to-End Full Flow ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_end_to_end_full_flow():
    """Complete chain: agent → pending → CFO signs → proxy verifies → data returns.

    This test proves the cryptographic integrity of the entire pipeline:
    1. Generate Ed25519 keypair
    2. Create KeyVault and ProxyRouter with FakeClient
    3. Agent calls query_external_network("machine learning")
    4. Gateway creates unsigned ExpenseRequest, blocks
    5. CFO reads pending, signs with private key
    6. Gateway forwards signed request through ProxyRouter
    7. ProxyRouter verifies Ed25519 signature
    8. FakeClient returns mock API data
    9. Data flows back to agent
    """
    # Setup cryptographic infrastructure
    sk, vk = generate_keypair()
    vault = KeyVault(vk)
    proxy = ProxyRouter(vault)
    mock_api_response = {"title": "Machine learning", "extract": "ML is a subset of AI..."}
    proxy._client = FakeClient([FakeResponse(200, mock_api_response)])
    ctx = AsyncContextTree()

    gateway = ExternalNetworkGateway(
        proxy=proxy,
        ctx=ctx,
        target_url="https://en.wikipedia.org/api/rest_v1/page/summary",
        default_amount=0.01,
        timeout=5.0,
    )
    await gateway.start()

    # Agent calls tool
    query_task = asyncio.create_task(gateway.query("machine learning"))
    await asyncio.sleep(0)

    # Verify pending state
    pending = gateway.get_pending()
    assert len(pending) == 1
    expense_info = pending[0]
    assert expense_info["amount"] == 0.01
    assert "machine learning" in expense_info["target_api"]
    assert "machine learning" in expense_info["justification"]

    # Verify context tree has the pending expense
    ctx_pending = ctx.get("colony", "pending_expenses", [])
    assert len(ctx_pending) == 1
    assert ctx_pending[0]["nonce"] == expense_info["nonce"]

    # CFO signs the request
    gateway.authorize(expense_info["nonce"], sk)

    # Agent receives the result
    result = await query_task
    parsed = json.loads(result)
    assert parsed["title"] == "Machine learning"
    assert parsed["extract"] == "ML is a subset of AI..."

    # Verify the proxy actually received and forwarded a properly signed request
    assert proxy._client.last_url == (
        "https://en.wikipedia.org/api/rest_v1/page/summary/machine learning"
    )

    # Verify audit log shows the forwarded request
    audit = proxy.get_audit_log()
    assert len(audit) == 1
    assert audit[0]["forwarded"] is True
    assert audit[0]["amount"] == 0.01

    # Verify cleanup
    assert gateway.get_pending() == []
    assert ctx.get("colony", "pending_expenses", []) == []

    await gateway.stop()


# ── 11. Justification Passthrough ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_custom_justification():
    """Custom justification is forwarded in the ExpenseRequest."""
    sk, vk = generate_keypair()
    gateway, _, _, _ = _make_gateway(sk=sk, vk=vk)
    await gateway.start()

    task = asyncio.create_task(
        gateway.query("topic", justification="Critical research for colony objective")
    )
    await asyncio.sleep(0)

    pending = gateway.get_pending()
    assert pending[0]["justification"] == "Critical research for colony objective"

    gateway.authorize(pending[0]["nonce"], sk)
    await task

    await gateway.stop()
