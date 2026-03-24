"""Bounded web-search adapter for FormicOS forager (Wave 44, Pillar 2).

Pluggable search backends for deterministic query execution. V1 ships a
DuckDuckGo HTML backend (no API key required) and a Serper backend
(requires ``SERPER_API_KEY``). The adapter returns structured
``SearchResult`` objects — url, title, snippet — and nothing more.

The adapter lives in the adapters layer (imports only core + stdlib).
All actual HTTP work goes through an injected ``httpx.AsyncClient`` so
the caller controls timeouts, rate limits, and egress policy.

Usage:
    from formicos.adapters.web_search import WebSearchAdapter, SearchResult

    adapter = WebSearchAdapter.create()      # auto-selects best backend
    results = await adapter.search("python asyncio patterns", max_results=5)
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import structlog

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchResult:
    """A single search result returned by a backend."""

    url: str
    title: str
    snippet: str
    source: str = ""  # backend name that produced this result


@dataclass
class SearchResponse:
    """Aggregated response from a search query."""

    query: str
    results: list[SearchResult] = field(default_factory=lambda: list[SearchResult]())
    backend: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Backend protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class SearchBackend(Protocol):
    """Pluggable search-backend contract."""

    @property
    def name(self) -> str: ...

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        http_client: Any = None,
    ) -> list[SearchResult]: ...


# ---------------------------------------------------------------------------
# DuckDuckGo HTML backend (no API key required)
# ---------------------------------------------------------------------------


class DuckDuckGoBackend:
    """Lightweight DuckDuckGo search via the HTML-only endpoint.

    This backend is self-contained and requires no API key. It parses
    the ``lite.duckduckgo.com`` HTML response for result links and
    snippets. Quality is adequate for v1 deterministic queries.
    """

    @property
    def name(self) -> str:
        return "duckduckgo"

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        http_client: Any = None,
    ) -> list[SearchResult]:
        if http_client is None:
            import httpx  # noqa: PLC0415

            http_client = httpx.AsyncClient(timeout=15.0)

        try:
            resp = await http_client.post(
                "https://lite.duckduckgo.com/lite/",
                data={"q": query},
                headers={"User-Agent": "FormicOS-Forager/1.0"},
            )
            resp.raise_for_status()
            return self._parse_html(resp.text, max_results)
        except Exception:  # noqa: BLE001
            log.warning("web_search.ddg_backend_failed", query=query[:100])
            return []

    @staticmethod
    def _parse_html(body: str, max_results: int) -> list[SearchResult]:
        """Extract results from DuckDuckGo lite HTML."""
        results: list[SearchResult] = []
        # DDG lite wraps each result in a <a> with class "result-link"
        # and snippets in <td class="result-snippet">
        link_pattern = re.compile(
            r'<a[^>]+class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            re.DOTALL,
        )
        snippet_pattern = re.compile(
            r'<td[^>]+class="result-snippet"[^>]*>(.*?)</td>',
            re.DOTALL,
        )

        links = link_pattern.findall(body)
        snippets = snippet_pattern.findall(body)

        for i, (url, title_html) in enumerate(links[:max_results]):
            title = _strip_html(title_html).strip()
            snippet = _strip_html(snippets[i]).strip() if i < len(snippets) else ""
            if url and title:
                results.append(SearchResult(
                    url=url, title=title, snippet=snippet, source="duckduckgo",
                ))
        return results


# ---------------------------------------------------------------------------
# Serper backend (API key required)
# ---------------------------------------------------------------------------


class SerperBackend:
    """Google Search via the Serper.dev API.

    Requires ``SERPER_API_KEY`` environment variable or explicit key.
    Higher-quality results than DDG but requires credentials.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "serper"

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        http_client: Any = None,
    ) -> list[SearchResult]:
        if http_client is None:
            import httpx  # noqa: PLC0415

            http_client = httpx.AsyncClient(timeout=15.0)

        try:
            resp = await http_client.post(
                "https://google.serper.dev/search",
                json={"q": query, "num": max_results},
                headers={
                    "X-API-KEY": self._api_key,
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return self._parse_response(data, max_results)
        except Exception:  # noqa: BLE001
            log.warning("web_search.serper_backend_failed", query=query[:100])
            return []

    @staticmethod
    def _parse_response(
        data: dict[str, Any], max_results: int,
    ) -> list[SearchResult]:
        results: list[SearchResult] = []
        for item in data.get("organic", [])[:max_results]:
            url = item.get("link", "")
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            if url and title:
                results.append(SearchResult(
                    url=url, title=title, snippet=snippet, source="serper",
                ))
        return results


# ---------------------------------------------------------------------------
# Pre-fetch relevance filter
# ---------------------------------------------------------------------------


def filter_results(
    results: list[SearchResult],
    query: str,
    *,
    min_overlap: int = 1,
) -> list[SearchResult]:
    """Bounded pre-fetch relevance filter.

    Keeps results whose title+snippet share at least ``min_overlap``
    words with the query. Protects fetch budget from irrelevant results.
    """
    query_words = set(query.lower().split())
    filtered: list[SearchResult] = []
    for r in results:
        text_words = set(f"{r.title} {r.snippet}".lower().split())
        overlap = len(query_words & text_words)
        if overlap >= min_overlap:
            filtered.append(r)
    return filtered


# ---------------------------------------------------------------------------
# Adapter facade
# ---------------------------------------------------------------------------


class WebSearchAdapter:
    """Facade over pluggable search backends.

    Auto-selects the best available backend at creation time.
    """

    def __init__(self, backend: SearchBackend) -> None:
        self._backend = backend

    @classmethod
    def create(cls, *, serper_api_key: str = "") -> WebSearchAdapter:
        """Create with the best available backend.

        Prefers Serper if a key is provided, else falls back to DDG.
        """
        if serper_api_key:
            log.info("web_search.backend_selected", backend="serper")
            return cls(SerperBackend(api_key=serper_api_key))
        log.info("web_search.backend_selected", backend="duckduckgo")
        return cls(DuckDuckGoBackend())

    @property
    def backend_name(self) -> str:
        return self._backend.name

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        http_client: Any = None,
    ) -> SearchResponse:
        """Execute a bounded search query."""
        try:
            results = await self._backend.search(
                query, max_results=max_results, http_client=http_client,
            )
            log.info(
                "web_search.completed",
                backend=self._backend.name,
                query=query[:80],
                result_count=len(results),
            )
            return SearchResponse(
                query=query, results=results, backend=self._backend.name,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "web_search.failed",
                backend=self._backend.name,
                query=query[:80],
                error=str(exc),
            )
            return SearchResponse(
                query=query, backend=self._backend.name, error=str(exc),
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text)


__all__ = [
    "DuckDuckGoBackend",
    "SearchBackend",
    "SearchResponse",
    "SearchResult",
    "SerperBackend",
    "WebSearchAdapter",
    "filter_results",
]
