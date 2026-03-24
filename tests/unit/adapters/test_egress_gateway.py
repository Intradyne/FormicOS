"""Tests for Wave 44 EgressGateway adapter."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from formicos.adapters.egress_gateway import (
    EgressGateway,
    EgressPolicy,
    FetchOrigin,
    FetchResult,
    _TokenBucket,
)


# ---------------------------------------------------------------------------
# Token bucket
# ---------------------------------------------------------------------------


class TestTokenBucket:
    def test_initial_burst_allows_requests(self) -> None:
        bucket = _TokenBucket(rate=1.0, burst=3)
        assert bucket.try_consume()
        assert bucket.try_consume()
        assert bucket.try_consume()

    def test_burst_exhausted_blocks(self) -> None:
        bucket = _TokenBucket(rate=1.0, burst=2)
        assert bucket.try_consume()
        assert bucket.try_consume()
        assert not bucket.try_consume()

    def test_wait_seconds_positive_when_empty(self) -> None:
        bucket = _TokenBucket(rate=1.0, burst=1)
        bucket.try_consume()
        assert bucket.wait_seconds > 0

    def test_wait_seconds_zero_when_available(self) -> None:
        bucket = _TokenBucket(rate=1.0, burst=5)
        assert bucket.wait_seconds == 0.0


# ---------------------------------------------------------------------------
# Domain policy
# ---------------------------------------------------------------------------


class TestDomainPolicy:
    def test_denylist_blocks(self) -> None:
        gw = EgressGateway(EgressPolicy(denied_domains=["evil.com"]))
        ok, reason = gw._check_domain("evil.com", FetchOrigin.SEARCH_RESULT)
        assert not ok
        assert "deny" in reason.lower()

    def test_denylist_blocks_subdomain(self) -> None:
        gw = EgressGateway(EgressPolicy(denied_domains=["evil.com"]))
        ok, _ = gw._check_domain("sub.evil.com", FetchOrigin.SEARCH_RESULT)
        assert not ok

    def test_denylist_wins_over_allowlist(self) -> None:
        gw = EgressGateway(EgressPolicy(
            allowed_domains=["evil.com"],
            denied_domains=["evil.com"],
        ))
        ok, _ = gw._check_domain("evil.com", FetchOrigin.SEARCH_RESULT)
        assert not ok

    def test_allowlist_permits_listed_domain(self) -> None:
        gw = EgressGateway(EgressPolicy(allowed_domains=["docs.python.org"]))
        ok, _ = gw._check_domain("docs.python.org", FetchOrigin.SEARCH_RESULT)
        assert ok

    def test_allowlist_blocks_unlisted_domain(self) -> None:
        gw = EgressGateway(EgressPolicy(allowed_domains=["docs.python.org"]))
        ok, _ = gw._check_domain("evil.com", FetchOrigin.SEARCH_RESULT)
        assert not ok

    def test_empty_allowlist_permits_search_results(self) -> None:
        gw = EgressGateway(EgressPolicy())
        ok, _ = gw._check_domain("anything.com", FetchOrigin.SEARCH_RESULT)
        assert ok

    def test_operator_approved_requires_listing(self) -> None:
        gw = EgressGateway(EgressPolicy(
            operator_approved_domains=["trusted.io"],
        ))
        ok, _ = gw._check_domain("trusted.io", FetchOrigin.OPERATOR_APPROVED)
        assert ok

    def test_operator_approved_rejects_unlisted(self) -> None:
        gw = EgressGateway(EgressPolicy(
            operator_approved_domains=["trusted.io"],
        ))
        ok, _ = gw._check_domain("other.com", FetchOrigin.OPERATOR_APPROVED)
        assert not ok


# ---------------------------------------------------------------------------
# Origin validation
# ---------------------------------------------------------------------------


class TestOriginValidation:
    @pytest.mark.asyncio
    async def test_invalid_origin_rejected(self) -> None:
        gw = EgressGateway()
        result = await gw.fetch("https://example.com", origin="arbitrary")
        assert not result.success
        assert "Invalid fetch origin" in result.error

    @pytest.mark.asyncio
    async def test_search_result_origin_accepted(self) -> None:
        gw = EgressGateway(EgressPolicy(denied_domains=["example.com"]))
        # Denied domain, but origin itself is valid — domain check rejects it
        result = await gw.fetch("https://example.com", origin=FetchOrigin.SEARCH_RESULT)
        assert not result.success
        assert "deny" in result.error.lower()


# ---------------------------------------------------------------------------
# robots.txt parsing
# ---------------------------------------------------------------------------


class TestRobotsParsing:
    def test_parse_disallow(self) -> None:
        robots = """
User-agent: *
Disallow: /private/
Disallow: /admin/
Allow: /
"""
        disallowed = EgressGateway._parse_robots(robots)
        assert "/private/" in disallowed
        assert "/admin/" in disallowed

    def test_parse_formicos_agent(self) -> None:
        robots = """
User-agent: FormicOS-Forager
Disallow: /api/

User-agent: *
Disallow: /other/
"""
        disallowed = EgressGateway._parse_robots(robots)
        assert "/api/" in disallowed
        assert "/other/" in disallowed

    def test_parse_ignores_irrelevant_agents(self) -> None:
        robots = """
User-agent: Googlebot
Disallow: /google-only/

User-agent: *
Allow: /
"""
        disallowed = EgressGateway._parse_robots(robots)
        assert "/google-only/" not in disallowed

    def test_path_disallowed_check(self) -> None:
        assert EgressGateway._path_disallowed("/private/data", ["/private/"])
        assert not EgressGateway._path_disallowed("/public/data", ["/private/"])


# ---------------------------------------------------------------------------
# Fetch with mocked httpx
# ---------------------------------------------------------------------------


class TestFetchIntegration:
    @pytest.mark.asyncio
    async def test_empty_url_rejected(self) -> None:
        gw = EgressGateway()
        result = await gw.fetch("", origin=FetchOrigin.SEARCH_RESULT)
        assert not result.success

    @pytest.mark.asyncio
    async def test_unparseable_url_rejected(self) -> None:
        gw = EgressGateway()
        result = await gw.fetch("not-a-url", origin=FetchOrigin.SEARCH_RESULT)
        assert not result.success

    @pytest.mark.asyncio
    async def test_successful_fetch(self) -> None:
        gw = EgressGateway(EgressPolicy(respect_robots_txt=False))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"Hello world"
        mock_resp.text = "Hello world"
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.encoding = "utf-8"
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("formicos.adapters.egress_gateway.httpx.AsyncClient",
                    return_value=mock_client):
            result = await gw.fetch(
                "https://example.com/page",
                origin=FetchOrigin.SEARCH_RESULT,
            )

        assert result.success
        assert result.status_code == 200
        assert result.text == "Hello world"
        assert result.response_size == 11

    @pytest.mark.asyncio
    async def test_size_limit_enforced(self) -> None:
        gw = EgressGateway(EgressPolicy(
            max_response_bytes=10,
            respect_robots_txt=False,
        ))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"A" * 100
        mock_resp.text = "A" * 100
        mock_resp.headers = {"content-type": "text/plain"}
        mock_resp.encoding = "utf-8"
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("formicos.adapters.egress_gateway.httpx.AsyncClient",
                    return_value=mock_client):
            result = await gw.fetch(
                "https://example.com/big",
                origin=FetchOrigin.SEARCH_RESULT,
            )

        assert result.success
        assert result.response_size <= 10


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestGatewayStats:
    def test_get_stats_returns_dict(self) -> None:
        gw = EgressGateway(EgressPolicy(
            allowed_domains=["a.com", "b.com"],
            denied_domains=["evil.com"],
        ))
        stats = gw.get_stats()
        assert stats["policy_allowed_domains"] == 2
        assert stats["policy_denied_domains"] == 1

    def test_domain_is_allowed_check(self) -> None:
        gw = EgressGateway(EgressPolicy(denied_domains=["blocked.com"]))
        assert not gw.domain_is_allowed("blocked.com", FetchOrigin.SEARCH_RESULT)
        assert gw.domain_is_allowed("ok.com", FetchOrigin.SEARCH_RESULT)
