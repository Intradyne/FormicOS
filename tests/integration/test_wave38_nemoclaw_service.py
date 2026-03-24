"""Wave 38 integration tests: NemoClaw tool-level specialist bridge.

Verifies that:
- NemoClawClient is configurable and handles errors gracefully
- ServiceRouter handler factories produce callable handlers
- Specialist calls flow through ServiceQuerySent/ServiceQueryResolved
- Unconfigured endpoints skip registration without error
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from formicos.adapters.nemoclaw_client import (
    SPECIALIST_SERVICES,
    NemoClawClient,
    NemoClawError,
    make_nemoclaw_handler,
)

# ---------------------------------------------------------------------------
# NemoClawClient unit tests
# ---------------------------------------------------------------------------


class TestNemoClawClient:
    """Test the bounded HTTP client for external specialists."""

    def test_unconfigured_is_not_configured(self) -> None:
        client = NemoClawClient()
        assert not client.is_configured

    def test_configured_with_endpoint(self) -> None:
        client = NemoClawClient(endpoint="http://localhost:9090")
        assert client.is_configured

    def test_configured_via_env(self) -> None:
        with patch.dict("os.environ", {"NEMOCLAW_ENDPOINT": "http://test:9090"}):
            client = NemoClawClient()
            assert client.is_configured

    @pytest.mark.asyncio
    async def test_query_raises_when_unconfigured(self) -> None:
        client = NemoClawClient()
        with pytest.raises(NemoClawError, match="not configured"):
            await client.query("secure_coder", "test task")

    @pytest.mark.asyncio
    async def test_query_success_json_response(self) -> None:
        """Successful JSON response is parsed correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"result": "secure code output"}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            client = NemoClawClient(endpoint="http://localhost:9090")
            result = await client.query("secure_coder", "write safe code")

        assert result == "secure code output"

    @pytest.mark.asyncio
    async def test_query_success_plain_text_response(self) -> None:
        """Plain text response is returned as-is."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.text = "plain text result"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            client = NemoClawClient(endpoint="http://localhost:9090")
            result = await client.query("security_review", "review this")

        assert result == "plain text result"

    @pytest.mark.asyncio
    async def test_query_http_error_raises(self) -> None:
        """Non-200 response raises NemoClawError."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            client = NemoClawClient(endpoint="http://localhost:9090")
            with pytest.raises(NemoClawError, match="HTTP 500"):
                await client.query("secure_coder", "test")

    @pytest.mark.asyncio
    async def test_query_timeout_raises(self) -> None:
        """Transport timeout raises NemoClawError."""
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=httpx.TimeoutException("timed out"),
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            client = NemoClawClient(endpoint="http://localhost:9090")
            with pytest.raises(NemoClawError, match="timed out"):
                await client.query("secure_coder", "test")

    @pytest.mark.asyncio
    async def test_query_json_output_field(self) -> None:
        """JSON response with 'output' field (alternative to 'result')."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"output": "alternative output"}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            client = NemoClawClient(endpoint="http://localhost:9090")
            result = await client.query("sandbox_analysis", "analyze")

        assert result == "alternative output"


# ---------------------------------------------------------------------------
# ServiceRouter handler factory tests
# ---------------------------------------------------------------------------


class TestNemoClawHandlers:
    """Test handler factories for ServiceRouter integration."""

    @pytest.mark.asyncio
    async def test_handler_returns_result_on_success(self) -> None:
        """Handler returns specialist result on success."""
        client = MagicMock(spec=NemoClawClient)
        client.query = AsyncMock(return_value="secure code output")

        handler = make_nemoclaw_handler(client, "secure_coder")
        result = await handler("write safe code", {"sender_colony_id": "col-1"})

        assert result == "secure code output"
        client.query.assert_awaited_once_with("secure_coder", "write safe code")

    @pytest.mark.asyncio
    async def test_handler_returns_error_string_on_failure(self) -> None:
        """Handler returns error message instead of raising."""
        client = MagicMock(spec=NemoClawClient)
        client.query = AsyncMock(side_effect=NemoClawError("connection refused"))

        handler = make_nemoclaw_handler(client, "security_review")
        result = await handler("review code", {"sender_colony_id": None})

        assert "Error:" in result
        assert "connection refused" in result

    @pytest.mark.asyncio
    async def test_handler_passes_no_sender(self) -> None:
        """Handler works when sender_colony_id is None."""
        client = MagicMock(spec=NemoClawClient)
        client.query = AsyncMock(return_value="ok")

        handler = make_nemoclaw_handler(client, "sandbox_analysis")
        result = await handler("test", {})

        assert result == "ok"


# ---------------------------------------------------------------------------
# Service name registry
# ---------------------------------------------------------------------------


class TestSpecialistServices:
    """Test the specialist service name mapping."""

    def test_all_services_have_expected_prefix(self) -> None:
        for svc_name in SPECIALIST_SERVICES:
            assert svc_name.startswith("service:external:nemoclaw:")

    def test_expected_specialists_present(self) -> None:
        specialist_types = set(SPECIALIST_SERVICES.values())
        assert "secure_coder" in specialist_types
        assert "security_review" in specialist_types
        assert "sandbox_analysis" in specialist_types

    def test_three_specialists_registered(self) -> None:
        assert len(SPECIALIST_SERVICES) == 3


# ---------------------------------------------------------------------------
# ServiceRouter integration (traceability path)
# ---------------------------------------------------------------------------


class TestServiceRouterIntegration:
    """Verify specialist calls flow through existing service-query traces."""

    @pytest.mark.asyncio
    async def test_handler_callable_through_service_router(self) -> None:
        """Handler can be registered and called through ServiceRouter."""
        from formicos.engine.service_router import ServiceRouter

        router = ServiceRouter()
        emit_calls: list[Any] = []

        async def mock_emit(event: Any) -> int:
            emit_calls.append(event)
            return 1

        router.set_emit_fn(mock_emit)

        client = MagicMock(spec=NemoClawClient)
        client.query = AsyncMock(return_value="reviewed code is safe")

        handler = make_nemoclaw_handler(client, "security_review")
        router.register_handler(
            "service:external:nemoclaw:security_review", handler,
        )

        result = await router.query(
            service_type="service:external:nemoclaw:security_review",
            query_text="check this code",
            sender_colony_id="col-test",
        )

        assert result == "reviewed code is safe"

        # Verify service trace events were emitted
        from formicos.core.events import ServiceQueryResolved, ServiceQuerySent

        sent_events = [e for e in emit_calls if isinstance(e, ServiceQuerySent)]
        resolved_events = [
            e for e in emit_calls if isinstance(e, ServiceQueryResolved)
        ]
        assert len(sent_events) == 1
        assert len(resolved_events) == 1
        assert sent_events[0].service_type == "service:external:nemoclaw:security_review"
        assert resolved_events[0].service_type == "service:external:nemoclaw:security_review"
        assert resolved_events[0].latency_ms >= 0
