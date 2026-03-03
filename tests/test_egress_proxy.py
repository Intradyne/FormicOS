"""
Tests for FormicOS Cryptographic Egress Proxy.

Covers:
1. ExpenseRequest model validation
2. Canonical bytes determinism
3. Signature round-trip (sign → verify)
4. Tamper detection (amount, target_api, justification, nonce, timestamp)
5. Forged / missing / mismatched signatures
6. KeyVault construction
7. ProxyRouter.forward() — happy path, rejections, upstream errors, lifecycle
8. Nonce replay protection — idempotency ledger, concurrent replay attack
"""

from __future__ import annotations

import asyncio
import json
import time

import nacl.signing
import pytest

from src.core.network.egress_proxy import (
    ExpenseRequest,
    KeyVault,
    NonceLedger,
    ProxyReplayError,
    ProxyRouter,
    SignatureVerificationError,
    generate_keypair,
)


# ── Helpers ─────────────────────────────────────────────────────────────


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
            FakeResponse(200, {"id": "ch_123"}),
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


def _make_signed_request(
    signing_key: nacl.signing.SigningKey,
    amount: float = 49.99,
    target_api: str = "https://api.stripe.com/v1/charges",
    justification: str = "Cloud hosting invoice",
) -> ExpenseRequest:
    """Helper: create and sign an ExpenseRequest."""
    req = ExpenseRequest(
        amount=amount,
        target_api=target_api,
        justification=justification,
    )
    req.sign(signing_key)
    return req


# ── 1. Model Validation ───────────────────────────────────────────────


def test_expense_request_amount_must_be_positive():
    """amount=0 and amount=-1 should both be rejected."""
    with pytest.raises(Exception):
        ExpenseRequest(
            amount=0,
            target_api="https://api.stripe.com/v1/charges",
            justification="test",
        )
    with pytest.raises(Exception):
        ExpenseRequest(
            amount=-5,
            target_api="https://api.stripe.com/v1/charges",
            justification="test",
        )


def test_expense_request_target_api_must_be_url():
    """target_api without http(s):// should be rejected."""
    with pytest.raises(Exception):
        ExpenseRequest(
            amount=10.0,
            target_api="not-a-url",
            justification="test",
        )


def test_expense_request_justification_required():
    """Empty justification should be rejected."""
    with pytest.raises(Exception):
        ExpenseRequest(
            amount=10.0,
            target_api="https://api.stripe.com/v1/charges",
            justification="",
        )


def test_expense_request_auto_nonce():
    """Two requests should get distinct auto-generated nonces."""
    r1 = ExpenseRequest(
        amount=1.0,
        target_api="https://example.com",
        justification="a",
    )
    r2 = ExpenseRequest(
        amount=1.0,
        target_api="https://example.com",
        justification="a",
    )
    assert r1.nonce != r2.nonce
    assert len(r1.nonce) == 36  # UUID format


def test_expense_request_auto_timestamp():
    """Timestamp should be auto-populated near current time."""
    before = time.time()
    req = ExpenseRequest(
        amount=1.0,
        target_api="https://example.com",
        justification="a",
    )
    after = time.time()
    assert before <= req.timestamp <= after


# ── 2. Canonical Bytes ────────────────────────────────────────────────


def test_canonical_bytes_deterministic():
    """Same fields should produce identical canonical bytes."""
    req = ExpenseRequest(
        amount=25.50,
        target_api="https://api.stripe.com/v1/charges",
        justification="Server costs",
        nonce="fixed-nonce",
        timestamp=1700000000.0,
    )
    assert req.canonical_bytes() == req.canonical_bytes()


def test_canonical_bytes_excludes_signature():
    """The 'signature' key must NOT appear in canonical bytes."""
    sk, _ = generate_keypair()
    req = _make_signed_request(sk)
    assert req.signature != ""
    parsed = json.loads(req.canonical_bytes())
    assert "signature" not in parsed


def test_canonical_bytes_sorted_keys():
    """Keys in canonical JSON must be alphabetically sorted."""
    req = ExpenseRequest(
        amount=10.0,
        target_api="https://example.com",
        justification="test",
        nonce="abc",
        timestamp=1.0,
    )
    parsed = json.loads(req.canonical_bytes())
    keys = list(parsed.keys())
    assert keys == sorted(keys)


# ── 3. Signature Round-Trip ───────────────────────────────────────────


def test_sign_and_verify_succeeds():
    """Happy path: sign with private key, verify with public key."""
    sk, vk = generate_keypair()
    req = _make_signed_request(sk)
    assert req.verify(vk) is True


def test_signature_is_hex_string():
    """After sign(), signature should be a 128-char hex string (64 bytes)."""
    sk, _ = generate_keypair()
    req = _make_signed_request(sk)
    assert len(req.signature) == 128
    bytes.fromhex(req.signature)  # should not raise


# ── 4. Tamper Detection (CRITICAL SECURITY TESTS) ────────────────────


def test_tampered_amount_fails():
    """Changing amount after signing must invalidate the signature."""
    sk, vk = generate_keypair()
    req = _make_signed_request(sk, amount=49.99)
    req.amount = 4999.00  # attacker inflates the amount
    with pytest.raises(SignatureVerificationError):
        req.verify(vk)


def test_tampered_target_api_fails():
    """Changing target_api after signing must invalidate the signature."""
    sk, vk = generate_keypair()
    req = _make_signed_request(sk, target_api="https://api.stripe.com/v1/charges")
    req.target_api = "https://evil.com/drain"  # attacker redirects
    with pytest.raises(SignatureVerificationError):
        req.verify(vk)


def test_tampered_justification_fails():
    """Changing justification after signing must invalidate the signature."""
    sk, vk = generate_keypair()
    req = _make_signed_request(sk, justification="Cloud hosting invoice")
    req.justification = "CEO bonus"  # attacker changes purpose
    with pytest.raises(SignatureVerificationError):
        req.verify(vk)


def test_tampered_nonce_fails():
    """Changing nonce after signing must invalidate the signature."""
    sk, vk = generate_keypair()
    req = _make_signed_request(sk)
    req.nonce = "replaced-nonce"
    with pytest.raises(SignatureVerificationError):
        req.verify(vk)


def test_tampered_timestamp_fails():
    """Changing timestamp after signing must invalidate the signature."""
    sk, vk = generate_keypair()
    req = _make_signed_request(sk)
    req.timestamp = req.timestamp + 3600  # attacker shifts time
    with pytest.raises(SignatureVerificationError):
        req.verify(vk)


# ── 5. Forged / Missing / Mismatched Signatures ──────────────────────


def test_forged_signature_fails():
    """A random 64-byte hex string should not verify."""
    sk, vk = generate_keypair()
    req = _make_signed_request(sk)
    req.signature = "aa" * 64  # forged 64 bytes
    with pytest.raises(SignatureVerificationError):
        req.verify(vk)


def test_missing_signature_fails():
    """An empty signature should raise 'Missing signature'."""
    _, vk = generate_keypair()
    req = ExpenseRequest(
        amount=10.0,
        target_api="https://example.com",
        justification="test",
    )
    assert req.signature == ""
    with pytest.raises(SignatureVerificationError, match="Missing signature"):
        req.verify(vk)


def test_key_mismatch_fails():
    """Signing with key A and verifying with key B must fail."""
    sk_a, _ = generate_keypair()
    _, vk_b = generate_keypair()
    req = _make_signed_request(sk_a)
    with pytest.raises(SignatureVerificationError):
        req.verify(vk_b)


def test_invalid_hex_signature_fails():
    """A non-hex signature string should raise encoding error."""
    _, vk = generate_keypair()
    req = ExpenseRequest(
        amount=10.0,
        target_api="https://example.com",
        justification="test",
        signature="not_valid_hex_zzzz",
    )
    with pytest.raises(SignatureVerificationError, match="Invalid signature encoding"):
        req.verify(vk)


# ── 6. KeyVault ───────────────────────────────────────────────────────


def test_keyvault_from_hex():
    """Construct vault from hex-encoded public key, verify works."""
    sk, vk = generate_keypair()
    hex_str = vk.encode(encoder=nacl.encoding.HexEncoder).decode("ascii")
    vault = KeyVault.from_hex(hex_str)
    req = _make_signed_request(sk)
    assert req.verify(vault.verify_key) is True


def test_keyvault_from_bytes():
    """Construct vault from raw 32-byte public key, verify works."""
    sk, vk = generate_keypair()
    raw = bytes(vk)
    vault = KeyVault.from_bytes(raw)
    req = _make_signed_request(sk)
    assert req.verify(vault.verify_key) is True


def test_generate_keypair():
    """generate_keypair returns matching SigningKey and VerifyKey."""
    sk, vk = generate_keypair()
    assert isinstance(sk, nacl.signing.SigningKey)
    assert isinstance(vk, nacl.signing.VerifyKey)
    assert bytes(sk.verify_key) == bytes(vk)


# ── 7. ProxyRouter.forward() ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_forward_valid_signature():
    """Valid signature should forward and return upstream response."""
    sk, vk = generate_keypair()
    vault = KeyVault(vk)
    proxy = ProxyRouter(vault)
    proxy._client = FakeClient([FakeResponse(200, {"id": "ch_123"})])

    req = _make_signed_request(sk)
    resp = await proxy.forward(req)

    assert resp.status_code == 200
    assert resp.forwarded is True
    assert resp.body == {"id": "ch_123"}
    assert resp.error is None
    assert resp.request_nonce == req.nonce


@pytest.mark.asyncio
async def test_forward_invalid_signature_returns_403():
    """Tampered request should be rejected with 403."""
    sk, vk = generate_keypair()
    vault = KeyVault(vk)
    proxy = ProxyRouter(vault)
    proxy._client = FakeClient()

    req = _make_signed_request(sk)
    req.amount = 9999.99  # tamper after signing

    resp = await proxy.forward(req)

    assert resp.status_code == 403
    assert resp.forwarded is False
    assert "verification failed" in resp.error


@pytest.mark.asyncio
async def test_forward_missing_signature_returns_403():
    """Request without a signature should be rejected with 403."""
    _, vk = generate_keypair()
    vault = KeyVault(vk)
    proxy = ProxyRouter(vault)
    proxy._client = FakeClient()

    req = ExpenseRequest(
        amount=10.0,
        target_api="https://example.com",
        justification="test",
    )
    resp = await proxy.forward(req)

    assert resp.status_code == 403
    assert resp.forwarded is False
    assert "Missing signature" in resp.error


@pytest.mark.asyncio
async def test_forward_upstream_error_returns_502():
    """Upstream connection failure should return 502."""
    sk, vk = generate_keypair()
    vault = KeyVault(vk)
    proxy = ProxyRouter(vault)
    proxy._client = FakeClient([ConnectionError("refused")])

    req = _make_signed_request(sk)
    resp = await proxy.forward(req)

    assert resp.status_code == 502
    assert resp.forwarded is False
    assert "Upstream error" in resp.error


@pytest.mark.asyncio
async def test_forward_not_started_returns_503():
    """Proxy with no client (not started) should return 503."""
    sk, vk = generate_keypair()
    vault = KeyVault(vk)
    proxy = ProxyRouter(vault)
    # _client is None — never called start()

    req = _make_signed_request(sk)
    resp = await proxy.forward(req)

    assert resp.status_code == 503
    assert resp.forwarded is False
    assert "not initialized" in resp.error


@pytest.mark.asyncio
async def test_forward_target_allowlist_blocked():
    """Request targeting a URL not in the allowlist should get 403."""
    sk, vk = generate_keypair()
    vault = KeyVault(vk)
    proxy = ProxyRouter(vault, allowed_targets=["https://api.stripe.com"])
    proxy._client = FakeClient()

    req = _make_signed_request(
        sk, target_api="https://evil.com/drain",
    )
    resp = await proxy.forward(req)

    assert resp.status_code == 403
    assert resp.forwarded is False
    assert "not in allowlist" in resp.error


@pytest.mark.asyncio
async def test_forward_target_allowlist_allowed():
    """Request targeting an allowed URL prefix should forward."""
    sk, vk = generate_keypair()
    vault = KeyVault(vk)
    proxy = ProxyRouter(vault, allowed_targets=["https://api.stripe.com"])
    proxy._client = FakeClient([FakeResponse(200, {"ok": True})])

    req = _make_signed_request(
        sk, target_api="https://api.stripe.com/v1/charges",
    )
    resp = await proxy.forward(req)

    assert resp.status_code == 200
    assert resp.forwarded is True


@pytest.mark.asyncio
async def test_audit_log_records_success():
    """Successful forward should create an audit log entry."""
    sk, vk = generate_keypair()
    vault = KeyVault(vk)
    proxy = ProxyRouter(vault)
    proxy._client = FakeClient([FakeResponse(200, {"id": "ch_456"})])

    req = _make_signed_request(sk)
    await proxy.forward(req)

    log = proxy.get_audit_log()
    assert len(log) == 1
    assert log[0]["forwarded"] is True
    assert log[0]["nonce"] == req.nonce
    assert log[0]["amount"] == req.amount
    assert log[0]["error"] is None


@pytest.mark.asyncio
async def test_audit_log_records_rejection():
    """Rejected request should create an audit log entry with error."""
    sk, vk = generate_keypair()
    vault = KeyVault(vk)
    proxy = ProxyRouter(vault)
    proxy._client = FakeClient()

    req = _make_signed_request(sk)
    req.amount = 9999.99  # tamper

    await proxy.forward(req)

    log = proxy.get_audit_log()
    assert len(log) == 1
    assert log[0]["forwarded"] is False
    assert log[0]["error"] is not None
    assert log[0]["status_code"] == 403


@pytest.mark.asyncio
async def test_start_stop_lifecycle():
    """start() creates client, stop() closes it."""
    _, vk = generate_keypair()
    vault = KeyVault(vk)
    proxy = ProxyRouter(vault)

    assert proxy._client is None
    await proxy.start()
    assert proxy._client is not None
    await proxy.stop()
    assert proxy._client is None


# ── 8. Nonce Replay Protection ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_nonce_ledger_check_and_consume():
    """NonceLedger allows first use and rejects second use of a nonce."""
    ledger = NonceLedger()
    await ledger.check_and_consume("nonce-1")
    assert "nonce-1" in ledger
    assert len(ledger) == 1

    with pytest.raises(ProxyReplayError, match="already consumed"):
        await ledger.check_and_consume("nonce-1")


@pytest.mark.asyncio
async def test_nonce_ledger_distinct_nonces():
    """Different nonces are accepted independently."""
    ledger = NonceLedger()
    await ledger.check_and_consume("a")
    await ledger.check_and_consume("b")
    await ledger.check_and_consume("c")
    assert len(ledger) == 3


@pytest.mark.asyncio
async def test_nonce_ledger_ttl_eviction():
    """Expired nonces are evicted and can be reused."""
    ledger = NonceLedger(ttl=0.05)
    await ledger.check_and_consume("old-nonce")
    assert "old-nonce" in ledger

    # Wait for TTL to expire
    await asyncio.sleep(0.06)

    # Should succeed — nonce evicted
    await ledger.check_and_consume("old-nonce")


@pytest.mark.asyncio
async def test_nonce_ledger_max_entries():
    """Oldest entries evicted when max_entries exceeded."""
    ledger = NonceLedger(max_entries=5)
    for i in range(10):
        await ledger.check_and_consume(f"n-{i}")
    # Eviction runs before each insert, so after 10 inserts with max=5
    # we have at most max+1 entries (5 kept + 1 just inserted)
    assert len(ledger) <= 6
    # Newest entries kept, oldest evicted
    assert "n-9" in ledger
    assert "n-0" not in ledger


@pytest.mark.asyncio
async def test_replay_same_request_rejected():
    """Submitting the same signed request twice returns 403 on replay."""
    sk, vk = generate_keypair()
    vault = KeyVault(vk)
    proxy = ProxyRouter(vault)
    proxy._client = FakeClient([FakeResponse(200, {"id": "ch_1"})])

    req = _make_signed_request(sk)

    # First forward succeeds
    resp1 = await proxy.forward(req)
    assert resp1.status_code == 200
    assert resp1.forwarded is True

    # Second forward with same nonce is rejected
    resp2 = await proxy.forward(req)
    assert resp2.status_code == 403
    assert resp2.forwarded is False
    assert "already consumed" in resp2.error


@pytest.mark.asyncio
async def test_replay_distinct_nonces_both_succeed():
    """Two requests with different nonces both forward successfully."""
    sk, vk = generate_keypair()
    vault = KeyVault(vk)
    proxy = ProxyRouter(vault)
    proxy._client = FakeClient([
        FakeResponse(200, {"id": "ch_1"}),
        FakeResponse(200, {"id": "ch_2"}),
    ])

    req1 = _make_signed_request(sk, amount=10.0)
    req2 = _make_signed_request(sk, amount=20.0)
    assert req1.nonce != req2.nonce

    resp1 = await proxy.forward(req1)
    resp2 = await proxy.forward(req2)
    assert resp1.forwarded is True
    assert resp2.forwarded is True


@pytest.mark.asyncio
async def test_replay_audit_log_records_replay():
    """Replayed request creates an audit log entry with replay error."""
    sk, vk = generate_keypair()
    vault = KeyVault(vk)
    proxy = ProxyRouter(vault)
    proxy._client = FakeClient([FakeResponse(200, {"ok": True})])

    req = _make_signed_request(sk)
    await proxy.forward(req)
    await proxy.forward(req)  # replay

    log = proxy.get_audit_log()
    assert len(log) == 2
    assert log[0]["forwarded"] is True
    assert log[1]["forwarded"] is False
    assert log[1]["status_code"] == 403
    assert "already consumed" in log[1]["error"]


@pytest.mark.asyncio
async def test_proxy_replay_attack():
    """Submit the same signed request 500 times concurrently.

    Exactly ONE must be forwarded; the other 499 must be rejected as
    replay attacks (403).  This proves the nonce ledger is race-free
    under concurrent asyncio pressure.
    """
    sk, vk = generate_keypair()
    vault = KeyVault(vk)
    proxy = ProxyRouter(vault)
    proxy._client = FakeClient([FakeResponse(200, {"id": "ch_once"})])

    req = _make_signed_request(sk)

    # Fire 500 concurrent forwards of the same signed request
    results = await asyncio.gather(
        *[proxy.forward(req) for _ in range(500)]
    )

    forwarded = [r for r in results if r.forwarded]
    rejected = [r for r in results if not r.forwarded]

    assert len(forwarded) == 1, (
        f"Expected exactly 1 forwarded, got {len(forwarded)}"
    )
    assert len(rejected) == 499

    # The one success
    assert forwarded[0].status_code == 200
    assert forwarded[0].body == {"id": "ch_once"}

    # All rejections are 403 with replay error
    for r in rejected:
        assert r.status_code == 403
        assert "already consumed" in r.error

    # Audit log: 1 forwarded + 499 rejected = 500
    log = proxy.get_audit_log()
    assert len(log) == 500
    assert sum(1 for e in log if e["forwarded"]) == 1
    assert sum(1 for e in log if not e["forwarded"]) == 499
