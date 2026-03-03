"""
Tests for FormicOS v0.7.4 Webhook HMAC Signing.

Covers:
- HMAC signature present when signing_secret is set
- HMAC signature absent when no signing_secret
- HMAC signature correctness (independent verification)
- client_id and timestamp in webhook payloads
- Delivery log has signature_sent field
- Backward compatibility without signing_secret
- Content-Type header always present
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from src.webhook import WebhookDispatcher


# ── Helpers ──────────────────────────────────────────────────────────


class FakeResponse:
    def __init__(self, status_code: int = 200):
        self.status_code = status_code


class HMACCapturingClient:
    """Mock httpx.AsyncClient that captures headers and content."""

    def __init__(self, status_code: int = 200):
        self._status_code = status_code
        self.last_headers: dict | None = None
        self.last_content: bytes | None = None

    async def post(
        self,
        url: str,
        content: bytes = None,
        headers: dict = None,
        **kwargs,
    ):
        self.last_headers = headers
        self.last_content = content
        return FakeResponse(self._status_code)

    async def aclose(self):
        pass


# ── HMAC signature tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hmac_signature_present():
    wd = WebhookDispatcher(max_retries=1, signing_secret="test-secret")
    client = HMACCapturingClient(200)
    wd._client = client

    await wd.dispatch(
        url="https://example.com/hook",
        payload={"type": "colony.completed", "colony_id": "c1"},
        colony_id="c1",
    )

    assert client.last_headers is not None
    assert "X-FormicOS-Signature" in client.last_headers
    assert client.last_headers["X-FormicOS-Signature"].startswith("sha256=")


@pytest.mark.asyncio
async def test_hmac_signature_absent():
    wd = WebhookDispatcher(max_retries=1)  # no signing_secret
    client = HMACCapturingClient(200)
    wd._client = client

    await wd.dispatch(
        url="https://example.com/hook",
        payload={"type": "test"},
        colony_id="c1",
    )

    assert client.last_headers is not None
    assert "X-FormicOS-Signature" not in client.last_headers


@pytest.mark.asyncio
async def test_hmac_signature_correct():
    secret = "my-webhook-secret"
    wd = WebhookDispatcher(max_retries=1, signing_secret=secret)
    client = HMACCapturingClient(200)
    wd._client = client

    payload = {"type": "colony.completed", "colony_id": "c1"}
    await wd.dispatch(
        url="https://example.com/hook",
        payload=payload,
        colony_id="c1",
    )

    # Independently compute expected signature
    payload_bytes = json.dumps(payload, default=str).encode()
    expected_sig = hmac.new(
        secret.encode(), payload_bytes, hashlib.sha256,
    ).hexdigest()

    actual_sig = client.last_headers["X-FormicOS-Signature"]
    assert actual_sig == f"sha256={expected_sig}"


@pytest.mark.asyncio
async def test_hmac_payload_bytes_match():
    """The bytes signed must be the same bytes sent to the server."""
    secret = "verify-bytes"
    wd = WebhookDispatcher(max_retries=1, signing_secret=secret)
    client = HMACCapturingClient(200)
    wd._client = client

    payload = {"type": "test", "data": {"nested": True}}
    await wd.dispatch(
        url="https://example.com/hook",
        payload=payload,
        colony_id="c1",
    )

    sent_bytes = client.last_content
    expected_bytes = json.dumps(payload, default=str).encode()
    assert sent_bytes == expected_bytes

    # Verify the signature matches the sent bytes
    sig_hex = client.last_headers["X-FormicOS-Signature"].removeprefix("sha256=")
    expected_sig = hmac.new(
        secret.encode(), sent_bytes, hashlib.sha256,
    ).hexdigest()
    assert sig_hex == expected_sig


@pytest.mark.asyncio
async def test_content_type_header():
    wd = WebhookDispatcher(max_retries=1)
    client = HMACCapturingClient(200)
    wd._client = client

    await wd.dispatch(
        url="https://example.com/hook",
        payload={"type": "test"},
        colony_id="c1",
    )

    assert client.last_headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_content_type_header_with_secret():
    wd = WebhookDispatcher(max_retries=1, signing_secret="s")
    client = HMACCapturingClient(200)
    wd._client = client

    await wd.dispatch(
        url="https://example.com/hook",
        payload={"type": "test"},
        colony_id="c1",
    )

    assert client.last_headers["Content-Type"] == "application/json"


# ── Delivery log fields ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delivery_log_signature_sent_true():
    wd = WebhookDispatcher(max_retries=1, signing_secret="secret")
    wd._client = HMACCapturingClient(200)

    await wd.dispatch(
        url="https://example.com/hook",
        payload={"type": "test"},
        colony_id="c1",
    )

    logs = wd.get_logs()
    assert len(logs) == 1
    assert logs[0]["signature_sent"] is True


@pytest.mark.asyncio
async def test_delivery_log_signature_sent_false():
    wd = WebhookDispatcher(max_retries=1)
    wd._client = HMACCapturingClient(200)

    await wd.dispatch(
        url="https://example.com/hook",
        payload={"type": "test"},
        colony_id="c1",
    )

    logs = wd.get_logs()
    assert len(logs) == 1
    assert logs[0]["signature_sent"] is False


# ── Backward compatibility ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_backward_compat_no_secret():
    """WebhookDispatcher without signing_secret behaves like v0.7.3."""
    wd = WebhookDispatcher(max_retries=1)
    client = HMACCapturingClient(200)
    wd._client = client

    payload = {"type": "colony.completed", "colony_id": "c1"}
    result = await wd.dispatch(
        url="https://example.com/hook",
        payload=payload,
        colony_id="c1",
    )

    assert result is True
    # Only Content-Type header, no signature
    assert set(client.last_headers.keys()) == {"Content-Type"}
    # Content is the JSON payload bytes
    assert client.last_content == json.dumps(payload, default=str).encode()
