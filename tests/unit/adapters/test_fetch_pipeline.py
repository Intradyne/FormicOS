"""Tests for Wave 44 fetch pipeline and domain strategy."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from formicos.adapters.egress_gateway import EgressGateway, EgressPolicy, FetchResult
from formicos.adapters.fetch_pipeline import (
    LEVEL_1,
    LEVEL_2,
    DomainStrategy,
    ExtractionResult,
    FetchPipeline,
    _content_hash,
    _extract_json,
    _extract_plaintext,
    _should_escalate,
    get_default_strategy,
)


# ---------------------------------------------------------------------------
# Domain strategy
# ---------------------------------------------------------------------------


class TestDomainStrategy:
    def test_default_level_is_1(self) -> None:
        s = DomainStrategy(domain="example.com")
        assert s.preferred_level == LEVEL_1

    def test_record_success_updates(self) -> None:
        s = DomainStrategy(domain="example.com")
        updated = s.record_success(LEVEL_1)
        assert updated.success_count == 1
        assert updated.preferred_level == LEVEL_1
        assert updated.last_updated > 0

    def test_record_failure_escalates(self) -> None:
        s = DomainStrategy(domain="example.com", preferred_level=LEVEL_1)
        updated = s.record_failure(LEVEL_1)
        assert updated.preferred_level == LEVEL_2
        assert updated.failure_count == 1

    def test_failure_caps_at_level2(self) -> None:
        s = DomainStrategy(domain="example.com", preferred_level=LEVEL_2)
        updated = s.record_failure(LEVEL_2)
        assert updated.preferred_level == LEVEL_2

    def test_reprobe_down_after_age(self) -> None:
        old_time = time.time() - 86400 * 10  # 10 days ago
        s = DomainStrategy(
            domain="example.com",
            preferred_level=LEVEL_2,
            success_count=5,
            last_updated=old_time,
        )
        assert s.should_reprobe_down()

    def test_no_reprobe_when_recent(self) -> None:
        s = DomainStrategy(
            domain="example.com",
            preferred_level=LEVEL_2,
            success_count=5,
            last_updated=time.time(),
        )
        assert not s.should_reprobe_down()

    def test_no_reprobe_at_level1(self) -> None:
        s = DomainStrategy(domain="example.com", preferred_level=LEVEL_1)
        assert not s.should_reprobe_down()

    def test_roundtrip_dict(self) -> None:
        s = DomainStrategy(domain="x.com", preferred_level=2, success_count=3,
                           failure_count=1, last_updated=123.0)
        d = s.to_dict()
        s2 = DomainStrategy.from_dict(d)
        assert s2.domain == s.domain
        assert s2.preferred_level == s.preferred_level
        assert s2.success_count == s.success_count

    def test_known_level2_domains(self) -> None:
        s = get_default_strategy("medium.com")
        assert s.preferred_level == LEVEL_2

    def test_unknown_domain_defaults_level1(self) -> None:
        s = get_default_strategy("random-site.org")
        assert s.preferred_level == LEVEL_1


# ---------------------------------------------------------------------------
# Bypass extractors
# ---------------------------------------------------------------------------


class TestBypassExtractors:
    def test_plaintext_extraction(self) -> None:
        text, method = _extract_plaintext("  Hello world  ")
        assert text == "Hello world"
        assert method == "plaintext_bypass"

    def test_plaintext_empty(self) -> None:
        text, method = _extract_plaintext("   ")
        assert text == ""
        assert method == ""

    def test_json_extraction(self) -> None:
        text, method = _extract_json('{"key": "value"}')
        assert '"key"' in text
        assert method == "json_bypass"

    def test_json_empty(self) -> None:
        text, method = _extract_json("")
        assert text == ""


# ---------------------------------------------------------------------------
# Escalation logic
# ---------------------------------------------------------------------------


class TestEscalation:
    def test_short_text_triggers_escalation(self) -> None:
        assert _should_escalate("short", "<html>big page</html>")

    def test_good_text_does_not_escalate(self) -> None:
        good_text = "This is a comprehensive article about Python programming. " * 10
        html = f"<html><body>{good_text}</body></html>"
        assert not _should_escalate(good_text, html)

    def test_noscript_markers_trigger_escalation(self) -> None:
        text = "You need to enable JavaScript. Please enable JavaScript to continue."
        html = "<html>" + text + "</html>"
        assert _should_escalate(text, html)


# ---------------------------------------------------------------------------
# Content hash
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_same_text_same_hash(self) -> None:
        h1 = _content_hash("Hello World")
        h2 = _content_hash("Hello World")
        assert h1 == h2

    def test_whitespace_normalization(self) -> None:
        h1 = _content_hash("hello   world")
        h2 = _content_hash("hello world")
        assert h1 == h2

    def test_case_normalization(self) -> None:
        h1 = _content_hash("Hello World")
        h2 = _content_hash("hello world")
        assert h1 == h2

    def test_different_text_different_hash(self) -> None:
        h1 = _content_hash("alpha")
        h2 = _content_hash("beta")
        assert h1 != h2


# ---------------------------------------------------------------------------
# Pipeline with mocked gateway
# ---------------------------------------------------------------------------


class TestFetchPipeline:
    @pytest.mark.asyncio
    async def test_gateway_failure_propagates(self) -> None:
        gw = EgressGateway(EgressPolicy(denied_domains=["blocked.com"]))
        pipeline = FetchPipeline(gw)
        result = await pipeline.extract("https://blocked.com/page")
        assert not result.success
        assert "deny" in result.error.lower()

    @pytest.mark.asyncio
    async def test_plaintext_bypass(self) -> None:
        gw = EgressGateway(EgressPolicy(respect_robots_txt=False))
        pipeline = FetchPipeline(gw)

        fetch_result = FetchResult(
            url="https://example.com/data.txt",
            success=True,
            status_code=200,
            content_type="text/plain",
            raw_bytes=b"Plain text content here",
            text="Plain text content here",
            response_size=23,
        )

        with patch.object(gw, "fetch", AsyncMock(return_value=fetch_result)):
            result = await pipeline.extract("https://example.com/data.txt")

        assert result.success
        assert result.extraction_method == "plaintext_bypass"
        assert result.text == "Plain text content here"

    @pytest.mark.asyncio
    async def test_json_bypass(self) -> None:
        gw = EgressGateway(EgressPolicy(respect_robots_txt=False))
        pipeline = FetchPipeline(gw)

        fetch_result = FetchResult(
            url="https://api.example.com/data",
            success=True,
            status_code=200,
            content_type="application/json",
            raw_bytes=b'{"key": "value"}',
            text='{"key": "value"}',
            response_size=16,
        )

        with patch.object(gw, "fetch", AsyncMock(return_value=fetch_result)):
            result = await pipeline.extract("https://api.example.com/data")

        assert result.success
        assert result.extraction_method == "json_bypass"

    @pytest.mark.asyncio
    async def test_html_extraction_uses_trafilatura(self) -> None:
        gw = EgressGateway(EgressPolicy(respect_robots_txt=False))
        pipeline = FetchPipeline(gw)

        html = "<html><body><p>" + "Good content. " * 50 + "</p></body></html>"
        fetch_result = FetchResult(
            url="https://example.com/article",
            success=True,
            status_code=200,
            content_type="text/html",
            raw_bytes=html.encode(),
            text=html,
            response_size=len(html),
        )

        extracted = "Good content. " * 50
        with (
            patch.object(gw, "fetch", AsyncMock(return_value=fetch_result)),
            patch(
                "formicos.adapters.fetch_pipeline._extract_level1",
                return_value=(extracted, "trafilatura_markdown"),
            ),
        ):
            result = await pipeline.extract("https://example.com/article")

        assert result.success
        assert result.extraction_method == "trafilatura_markdown"
        assert result.extraction_level == LEVEL_1

    @pytest.mark.asyncio
    async def test_escalation_to_level2(self) -> None:
        gw = EgressGateway(EgressPolicy(respect_robots_txt=False))
        pipeline = FetchPipeline(gw)

        html = "<html><body>Short</body></html>"
        fetch_result = FetchResult(
            url="https://example.com/spa",
            success=True,
            status_code=200,
            content_type="text/html",
            raw_bytes=html.encode(),
            text=html,
            response_size=len(html),
        )

        good_text = "Extracted via level 2 recall. " * 20
        with (
            patch.object(gw, "fetch", AsyncMock(return_value=fetch_result)),
            patch(
                "formicos.adapters.fetch_pipeline._extract_level1",
                return_value=("", ""),
            ),
            patch(
                "formicos.adapters.fetch_pipeline._extract_level2",
                return_value=(good_text, "trafilatura_recall"),
            ),
        ):
            result = await pipeline.extract("https://example.com/spa")

        assert result.success
        assert result.extraction_level == LEVEL_2

    @pytest.mark.asyncio
    async def test_content_hash_present(self) -> None:
        gw = EgressGateway(EgressPolicy(respect_robots_txt=False))
        pipeline = FetchPipeline(gw)

        fetch_result = FetchResult(
            url="https://example.com/data.txt",
            success=True,
            status_code=200,
            content_type="text/plain",
            raw_bytes=b"Content for hashing",
            text="Content for hashing",
            response_size=19,
        )

        with patch.object(gw, "fetch", AsyncMock(return_value=fetch_result)):
            result = await pipeline.extract("https://example.com/data.txt")

        assert result.content_hash
        assert len(result.content_hash) == 64  # SHA-256 hex

    @pytest.mark.asyncio
    async def test_domain_strategy_updates_on_success(self) -> None:
        gw = EgressGateway(EgressPolicy(respect_robots_txt=False))
        pipeline = FetchPipeline(gw)

        fetch_result = FetchResult(
            url="https://example.com/page",
            success=True,
            status_code=200,
            content_type="text/html",
            raw_bytes=b"<html>content</html>",
            text="<html>content</html>",
            response_size=20,
        )

        extracted = "A long and useful article about many things. " * 20
        with (
            patch.object(gw, "fetch", AsyncMock(return_value=fetch_result)),
            patch(
                "formicos.adapters.fetch_pipeline._extract_level1",
                return_value=(extracted, "trafilatura_markdown"),
            ),
        ):
            await pipeline.extract("https://example.com/page")

        strategy = pipeline.domain_strategies.get("example.com")
        assert strategy is not None
        assert strategy.success_count == 1

    @pytest.mark.asyncio
    async def test_force_level_skips_strategy(self) -> None:
        gw = EgressGateway(EgressPolicy(respect_robots_txt=False))
        pipeline = FetchPipeline(gw)

        html = "<html><body>Content</body></html>"
        fetch_result = FetchResult(
            url="https://example.com/page",
            success=True,
            status_code=200,
            content_type="text/html",
            raw_bytes=html.encode(),
            text=html,
            response_size=len(html),
        )

        good_text = "Good text from level 2. " * 20
        with (
            patch.object(gw, "fetch", AsyncMock(return_value=fetch_result)),
            patch(
                "formicos.adapters.fetch_pipeline._extract_level2",
                return_value=(good_text, "trafilatura_recall"),
            ),
        ):
            result = await pipeline.extract(
                "https://example.com/page",
                force_level=LEVEL_2,
            )

        assert result.success
        assert result.extraction_level == LEVEL_2
