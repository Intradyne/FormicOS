"""
Tests for FormicOS v0.7.3 Webhook Dispatcher (webhook.py).

Covers:
- Successful delivery on first attempt
- Retry on server error (5xx)
- Max retries exhausted → status "failed"
- Delivery log capped at _MAX_LOG_ENTRIES
- get_logs filters by colony_id
- get_logs returns all when colony_id is None
- Dispatch without start() returns False
- Delivery record fields (timestamp, payload_size_bytes, etc.)
- Timeout handling records "timeout" status_code
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from src.webhook import WebhookDispatcher, _MAX_LOG_ENTRIES


# ── Helpers ──────────────────────────────────────────────────────────


class FakeResponse:
    def __init__(self, status_code: int = 200):
        self.status_code = status_code


class FakeClient:
    """Mock httpx.AsyncClient."""

    def __init__(self, responses: list[FakeResponse | Exception] | None = None):
        self._responses = responses or [FakeResponse(200)]
        self._call_count = 0

    async def post(self, url: str, **kwargs):
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        resp = self._responses[idx]
        if isinstance(resp, Exception):
            raise resp
        return resp

    async def aclose(self):
        pass


# ── Tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_successful_delivery():
    wd = WebhookDispatcher(max_retries=3)
    wd._client = FakeClient([FakeResponse(200)])

    result = await wd.dispatch(
        url="https://example.com/hook",
        payload={"type": "colony.completed", "colony_id": "c1"},
        colony_id="c1",
    )

    assert result is True
    logs = wd.get_logs()
    assert len(logs) == 1
    assert logs[0]["status"] == "delivered"
    assert logs[0]["status_code"] == 200
    assert logs[0]["colony_id"] == "c1"


@pytest.mark.asyncio
async def test_retry_on_5xx():
    """Server error on first attempt, success on second."""
    wd = WebhookDispatcher(max_retries=3)
    wd._client = FakeClient([FakeResponse(500), FakeResponse(200)])

    # Patch sleep to avoid actual delays
    with patch("src.webhook.asyncio.sleep", new_callable=AsyncMock):
        result = await wd.dispatch(
            url="https://example.com/hook",
            payload={"type": "test"},
            colony_id="c1",
        )

    assert result is True
    logs = wd.get_logs()
    assert len(logs) == 1
    assert logs[0]["status"] == "delivered"
    assert logs[0]["attempts"] == 2


@pytest.mark.asyncio
async def test_max_retries_exhausted():
    wd = WebhookDispatcher(max_retries=2)
    wd._client = FakeClient([FakeResponse(500), FakeResponse(503)])

    with patch("src.webhook.asyncio.sleep", new_callable=AsyncMock):
        result = await wd.dispatch(
            url="https://example.com/hook",
            payload={"type": "test"},
            colony_id="c1",
        )

    assert result is False
    logs = wd.get_logs()
    assert len(logs) == 1
    assert logs[0]["status"] == "failed"
    assert logs[0]["attempts"] == 2


@pytest.mark.asyncio
async def test_timeout_records_error():
    wd = WebhookDispatcher(max_retries=1)
    wd._client = FakeClient([ConnectionError("timed out")])

    with patch("src.webhook.asyncio.sleep", new_callable=AsyncMock):
        result = await wd.dispatch(
            url="https://example.com/hook",
            payload={"type": "test"},
            colony_id="c1",
        )

    assert result is False
    logs = wd.get_logs()
    assert len(logs) == 1
    assert logs[0]["status"] == "failed"
    assert logs[0]["status_code"] == "timeout"
    assert "timed out" in logs[0]["last_error"]


@pytest.mark.asyncio
async def test_dispatch_without_start():
    wd = WebhookDispatcher()
    # _client is None by default (not started)

    result = await wd.dispatch(
        url="https://example.com/hook",
        payload={"type": "test"},
    )

    assert result is False


@pytest.mark.asyncio
async def test_log_capped():
    wd = WebhookDispatcher(max_retries=1)
    wd._client = FakeClient([FakeResponse(200)])

    with patch("src.webhook.asyncio.sleep", new_callable=AsyncMock):
        for i in range(_MAX_LOG_ENTRIES + 10):
            await wd.dispatch(
                url="https://example.com/hook",
                payload={"type": "test", "i": i},
                colony_id=f"c{i}",
            )

    logs = wd.get_logs()
    assert len(logs) == _MAX_LOG_ENTRIES


@pytest.mark.asyncio
async def test_get_logs_filter_by_colony():
    wd = WebhookDispatcher(max_retries=1)
    wd._client = FakeClient([FakeResponse(200)])

    await wd.dispatch(url="https://example.com/hook", payload={"type": "test"}, colony_id="c1")
    await wd.dispatch(url="https://example.com/hook", payload={"type": "test"}, colony_id="c2")
    await wd.dispatch(url="https://example.com/hook", payload={"type": "test"}, colony_id="c1")

    c1_logs = wd.get_logs(colony_id="c1")
    assert len(c1_logs) == 2
    assert all(entry["colony_id"] == "c1" for entry in c1_logs)

    all_logs = wd.get_logs()
    assert len(all_logs) == 3


@pytest.mark.asyncio
async def test_delivery_record_fields():
    wd = WebhookDispatcher(max_retries=1)
    wd._client = FakeClient([FakeResponse(200)])

    payload = {"type": "colony.completed", "colony_id": "c1", "status": "completed"}
    await wd.dispatch(url="https://hooks.example.com/formicos", payload=payload, colony_id="c1")

    log = wd.get_logs()[0]
    assert "delivery_id" in log
    assert log["url"] == "https://hooks.example.com/formicos"
    assert log["payload_type"] == "colony.completed"
    assert log["payload_size_bytes"] == len(json.dumps(payload, default=str).encode())
    assert log["payload"] == payload
    assert "timestamp" in log
    assert log["colony_id"] == "c1"


@pytest.mark.asyncio
async def test_start_stop_lifecycle():
    wd = WebhookDispatcher()
    assert wd._client is None

    await wd.start()
    assert wd._client is not None

    await wd.stop()
    assert wd._client is None
