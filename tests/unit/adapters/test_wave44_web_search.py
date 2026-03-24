"""Wave 44 Pillar 2: Web search adapter tests.

Covers:
- DuckDuckGo HTML backend parsing
- Serper backend response parsing
- Pre-fetch relevance filtering
- WebSearchAdapter facade and backend selection
- SearchResult / SearchResponse data shapes
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.adapters.web_search import (
    DuckDuckGoBackend,
    SearchResponse,
    SearchResult,
    SerperBackend,
    WebSearchAdapter,
    filter_results,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DDG_HTML = """
<html>
<body>
<table>
  <tr>
    <td><a class="result-link" href="https://docs.python.org/3/library/asyncio.html">Python asyncio docs</a></td>
  </tr>
  <tr>
    <td class="result-snippet">Official Python documentation for asyncio library.</td>
  </tr>
  <tr>
    <td><a class="result-link" href="https://realpython.com/async-io-python/">Real Python Async IO</a></td>
  </tr>
  <tr>
    <td class="result-snippet">Comprehensive guide to async IO in Python with examples.</td>
  </tr>
  <tr>
    <td><a class="result-link" href="https://example.com/spam">Totally Unrelated Page</a></td>
  </tr>
  <tr>
    <td class="result-snippet">Buy cheap shoes online now!</td>
  </tr>
</table>
</body>
</html>
"""

SERPER_RESPONSE = {
    "organic": [
        {
            "title": "Python asyncio tutorial",
            "link": "https://docs.python.org/3/library/asyncio.html",
            "snippet": "Official asyncio documentation.",
        },
        {
            "title": "Async patterns in Python",
            "link": "https://realpython.com/async-io-python/",
            "snippet": "Learn async patterns with practical examples.",
        },
    ],
}


# ---------------------------------------------------------------------------
# DuckDuckGo backend tests
# ---------------------------------------------------------------------------


class TestDuckDuckGoBackend:
    def test_parse_html_extracts_results(self) -> None:
        backend = DuckDuckGoBackend()
        results = backend._parse_html(DDG_HTML, max_results=5)
        assert len(results) == 3
        assert results[0].url == "https://docs.python.org/3/library/asyncio.html"
        assert results[0].title == "Python asyncio docs"
        assert "Official Python" in results[0].snippet
        assert results[0].source == "duckduckgo"

    def test_parse_html_respects_max_results(self) -> None:
        backend = DuckDuckGoBackend()
        results = backend._parse_html(DDG_HTML, max_results=1)
        assert len(results) == 1

    def test_parse_html_empty(self) -> None:
        backend = DuckDuckGoBackend()
        results = backend._parse_html("<html></html>", max_results=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_search_with_mock_client(self) -> None:
        backend = DuckDuckGoBackend()
        mock_resp = MagicMock()
        mock_resp.text = DDG_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        results = await backend.search(
            "python asyncio", max_results=3, http_client=mock_client,
        )
        assert len(results) == 3
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_handles_http_error(self) -> None:
        backend = DuckDuckGoBackend()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("network error"))

        results = await backend.search(
            "python asyncio", http_client=mock_client,
        )
        assert results == []

    def test_backend_name(self) -> None:
        assert DuckDuckGoBackend().name == "duckduckgo"


# ---------------------------------------------------------------------------
# Serper backend tests
# ---------------------------------------------------------------------------


class TestSerperBackend:
    def test_parse_response(self) -> None:
        results = SerperBackend._parse_response(SERPER_RESPONSE, max_results=5)
        assert len(results) == 2
        assert results[0].url == "https://docs.python.org/3/library/asyncio.html"
        assert results[0].title == "Python asyncio tutorial"
        assert results[0].source == "serper"

    def test_parse_response_respects_max(self) -> None:
        results = SerperBackend._parse_response(SERPER_RESPONSE, max_results=1)
        assert len(results) == 1

    def test_parse_empty_response(self) -> None:
        results = SerperBackend._parse_response({}, max_results=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_search_with_mock_client(self) -> None:
        backend = SerperBackend(api_key="test-key")
        mock_resp = MagicMock()
        mock_resp.json.return_value = SERPER_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        results = await backend.search(
            "python asyncio", max_results=2, http_client=mock_client,
        )
        assert len(results) == 2
        # Verify API key was sent
        call_kwargs = mock_client.post.call_args
        assert call_kwargs[1]["headers"]["X-API-KEY"] == "test-key"

    def test_backend_name(self) -> None:
        assert SerperBackend(api_key="k").name == "serper"


# ---------------------------------------------------------------------------
# Pre-fetch relevance filter tests
# ---------------------------------------------------------------------------


class TestFilterResults:
    def test_filters_irrelevant_results(self) -> None:
        results = [
            SearchResult(url="https://a.com", title="Python asyncio guide", snippet="Learn asyncio"),
            SearchResult(url="https://b.com", title="Buy shoes", snippet="Cheap shoes online"),
        ]
        filtered = filter_results(results, "python asyncio")
        assert len(filtered) == 1
        assert filtered[0].url == "https://a.com"

    def test_keeps_all_relevant(self) -> None:
        results = [
            SearchResult(url="https://a.com", title="Python patterns", snippet="asyncio examples"),
            SearchResult(url="https://b.com", title="Async Python", snippet="tutorial guide"),
        ]
        filtered = filter_results(results, "python async")
        assert len(filtered) == 2

    def test_empty_results(self) -> None:
        assert filter_results([], "anything") == []

    def test_min_overlap_parameter(self) -> None:
        results = [
            SearchResult(url="https://a.com", title="Python", snippet="short"),
        ]
        # 1 word overlap with "python" query
        assert len(filter_results(results, "python", min_overlap=1)) == 1
        assert len(filter_results(results, "python", min_overlap=2)) == 0


# ---------------------------------------------------------------------------
# WebSearchAdapter facade tests
# ---------------------------------------------------------------------------


class TestWebSearchAdapter:
    def test_create_selects_ddg_by_default(self) -> None:
        adapter = WebSearchAdapter.create()
        assert adapter.backend_name == "duckduckgo"

    def test_create_selects_serper_with_key(self) -> None:
        adapter = WebSearchAdapter.create(serper_api_key="test-key")
        assert adapter.backend_name == "serper"

    @pytest.mark.asyncio
    async def test_search_returns_response(self) -> None:
        mock_backend = AsyncMock()
        mock_backend.name = "test"
        mock_backend.search = AsyncMock(return_value=[
            SearchResult(url="https://a.com", title="Result", snippet="text"),
        ])
        adapter = WebSearchAdapter(backend=mock_backend)
        response = await adapter.search("test query")
        assert isinstance(response, SearchResponse)
        assert response.query == "test query"
        assert len(response.results) == 1
        assert response.backend == "test"
        assert response.error == ""

    @pytest.mark.asyncio
    async def test_search_handles_backend_error(self) -> None:
        mock_backend = AsyncMock()
        mock_backend.name = "test"
        mock_backend.search = AsyncMock(side_effect=Exception("fail"))
        adapter = WebSearchAdapter(backend=mock_backend)
        response = await adapter.search("test query")
        assert "fail" in response.error
        assert response.results == []


# ---------------------------------------------------------------------------
# Data shape tests
# ---------------------------------------------------------------------------


class TestSearchResult:
    def test_frozen(self) -> None:
        r = SearchResult(url="https://a.com", title="T", snippet="S")
        with pytest.raises(AttributeError):
            r.url = "changed"  # type: ignore[misc]

    def test_default_source(self) -> None:
        r = SearchResult(url="u", title="t", snippet="s")
        assert r.source == ""

    def test_source_set(self) -> None:
        r = SearchResult(url="u", title="t", snippet="s", source="ddg")
        assert r.source == "ddg"
