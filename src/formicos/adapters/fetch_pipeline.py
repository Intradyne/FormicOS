# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Fetch pipeline — graduated content extraction (Wave 44).

Converts raw HTTP responses into clean extracted text with structured
metadata. Three extraction levels with automatic escalation on quality
failures.

Level 1 (Must):  trafilatura in markdown mode
Level 2 (Should): trafilatura(favor_recall=True), then readability-lxml
Level 3 (Defer):  Playwright / browser rendering — NOT in Wave 44

Also contains domain strategy logic: pure recommendation about which
fetch level works per domain. Team 3 owns the replay event shape,
Team 2 owns the surface path that applies updates.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from formicos.adapters.egress_gateway import EgressGateway, FetchOrigin, FetchResult

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Extraction levels
# ---------------------------------------------------------------------------

LEVEL_1 = 1  # trafilatura default
LEVEL_2 = 2  # trafilatura(favor_recall) + readability-lxml
LEVEL_3 = 3  # browser rendering (deferred)

# Quality thresholds for escalation
_MIN_TEXT_LENGTH = 100  # chars
_MIN_TEXT_TO_MARKUP_RATIO = 0.1
_NOSCRIPT_MARKERS = [
    "you need to enable javascript",
    "please enable javascript",
    "this page requires javascript",
    "noscript",
    "<noscript>",
    "loading...",
    "please wait while",
]


# ---------------------------------------------------------------------------
# Extraction result
# ---------------------------------------------------------------------------


@dataclass
class ExtractionResult:
    """Result of content extraction from a fetched page."""

    url: str
    success: bool
    text: str = ""
    text_length: int = 0
    content_type: str = ""
    extraction_method: str = ""
    extraction_level: int = 0
    content_hash: str = ""  # SHA-256 of normalized text for dedup
    fetch_duration_ms: float = 0.0
    extraction_duration_ms: float = 0.0
    quality_hints: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    raw_size: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Domain strategy (pure logic — Team 1 owns logic, Team 3 owns event shape)
# ---------------------------------------------------------------------------


@dataclass
class DomainStrategy:
    """Per-domain fetch strategy state."""

    domain: str
    preferred_level: int = LEVEL_1
    success_count: int = 0
    failure_count: int = 0
    last_updated: float = 0.0

    def record_success(self, level: int) -> DomainStrategy:
        """Return updated strategy after a successful fetch at this level."""
        return DomainStrategy(
            domain=self.domain,
            preferred_level=level,
            success_count=self.success_count + 1,
            failure_count=self.failure_count,
            last_updated=time.time(),
        )

    def record_failure(self, level: int) -> DomainStrategy:
        """Return updated strategy after a failed extraction at this level."""
        new_level = min(level + 1, LEVEL_2)  # escalate, cap at Level 2
        return DomainStrategy(
            domain=self.domain,
            preferred_level=new_level,
            success_count=self.success_count,
            failure_count=self.failure_count + 1,
            last_updated=time.time(),
        )

    def should_reprobe_down(self, max_age_seconds: float = 86400 * 7) -> bool:
        """After enough time, allow re-probing at a lower level."""
        if self.preferred_level <= LEVEL_1:
            return False
        if self.last_updated == 0.0:
            return False
        age = time.time() - self.last_updated
        return age > max_age_seconds and self.success_count >= 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "preferred_level": self.preferred_level,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DomainStrategy:
        return cls(
            domain=str(d.get("domain", "")),
            preferred_level=int(d.get("preferred_level", LEVEL_1)),
            success_count=int(d.get("success_count", 0)),
            failure_count=int(d.get("failure_count", 0)),
            last_updated=float(d.get("last_updated", 0.0)),
        )


# Known domain defaults — domains that typically need Level 2
_KNOWN_LEVEL2_DOMAINS = [
    "medium.com",
    "dev.to",
    "substack.com",
]


def get_default_strategy(domain: str) -> DomainStrategy:
    """Return a default strategy for a domain, using known patterns."""
    for known in _KNOWN_LEVEL2_DOMAINS:
        if domain == known or domain.endswith(f".{known}"):
            return DomainStrategy(domain=domain, preferred_level=LEVEL_2)
    return DomainStrategy(domain=domain, preferred_level=LEVEL_1)


# ---------------------------------------------------------------------------
# Extractors
# ---------------------------------------------------------------------------


def _extract_level1(html: str, url: str) -> tuple[str, str]:
    """Level 1: trafilatura in markdown output mode."""
    try:
        import trafilatura  # noqa: PLC0415

        text = trafilatura.extract(
            html,
            url=url,
            output_format="markdown",
            include_links=True,
            include_tables=True,
            no_fallback=True,
        )
        if text:
            return text, "trafilatura_markdown"
    except Exception as exc:  # noqa: BLE001
        log.debug("fetch_pipeline.level1_failed", url=url, error=str(exc))

    return "", ""


def _extract_level2(html: str, url: str) -> tuple[str, str]:
    """Level 2: trafilatura(favor_recall) then readability-lxml fallback."""
    # Try trafilatura with favor_recall
    try:
        import trafilatura  # noqa: PLC0415

        text = trafilatura.extract(
            html,
            url=url,
            output_format="markdown",
            include_links=True,
            include_tables=True,
            favor_recall=True,
        )
        if text and len(text) >= _MIN_TEXT_LENGTH:
            return text, "trafilatura_recall"
    except Exception as exc:  # noqa: BLE001
        log.debug("fetch_pipeline.level2_trafilatura_failed", url=url, error=str(exc))

    # Fallback: readability-lxml
    try:
        from readability import Document  # noqa: PLC0415  # pyright: ignore[reportMissingTypeStubs]

        doc = Document(html)
        summary_html = doc.summary()
        # Strip HTML tags for clean text
        text = re.sub(r"<[^>]+>", " ", summary_html)
        text = re.sub(r"\s+", " ", text).strip()
        if text and len(text) >= _MIN_TEXT_LENGTH:
            return text, "readability_lxml"
    except Exception as exc:  # noqa: BLE001
        log.debug("fetch_pipeline.level2_readability_failed", url=url, error=str(exc))

    return "", ""


def _extract_plaintext(text: str) -> tuple[str, str]:
    """Bypass extraction for plaintext content."""
    cleaned = text.strip()
    if cleaned:
        return cleaned, "plaintext_bypass"
    return "", ""


def _extract_json(text: str) -> tuple[str, str]:
    """Bypass extraction for JSON content — return as-is."""
    stripped = text.strip()
    if stripped:
        return stripped, "json_bypass"
    return "", ""


# ---------------------------------------------------------------------------
# Quality check for escalation decisions
# ---------------------------------------------------------------------------


def _should_escalate(text: str, html: str) -> bool:
    """Decide if extraction quality is too low and should escalate."""
    if len(text) < _MIN_TEXT_LENGTH:
        return True

    # Text-to-markup ratio
    html_len = len(html)
    if html_len > 0:
        ratio = len(text) / html_len
        if ratio < _MIN_TEXT_TO_MARKUP_RATIO:
            return True

    # Noscript / hydration markers
    text_lower = text.lower()
    noscript_hits = sum(1 for marker in _NOSCRIPT_MARKERS if marker in text_lower)
    return noscript_hits >= 2


# ---------------------------------------------------------------------------
# Content hash for dedup
# ---------------------------------------------------------------------------


def _content_hash(text: str) -> str:
    """SHA-256 hash of normalized text for exact dedup."""
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# FetchPipeline
# ---------------------------------------------------------------------------


class FetchPipeline:
    """Graduated content extraction pipeline.

    Uses EgressGateway for transport, then extracts clean text with
    automatic level escalation on quality failures.
    """

    def __init__(
        self,
        gateway: EgressGateway,
        domain_strategies: dict[str, DomainStrategy] | None = None,
    ) -> None:
        self._gateway = gateway
        self._domain_strategies: dict[str, DomainStrategy] = domain_strategies or {}

    @property
    def domain_strategies(self) -> dict[str, DomainStrategy]:
        return self._domain_strategies

    def set_domain_strategy(self, strategy: DomainStrategy) -> None:
        self._domain_strategies[strategy.domain] = strategy

    async def extract(
        self,
        url: str,
        *,
        origin: str = FetchOrigin.SEARCH_RESULT,
        force_level: int | None = None,
    ) -> ExtractionResult:
        """Fetch and extract content from a URL.

        Args:
            url: The URL to fetch.
            origin: Fetch origin declaration for egress policy.
            force_level: Force a specific extraction level (skip strategy).
        """
        # 1. Fetch via gateway
        fetch_result = await self._gateway.fetch(url, origin=origin)
        if not fetch_result.success:
            return ExtractionResult(
                url=url,
                success=False,
                error=fetch_result.error,
                fetch_duration_ms=fetch_result.fetch_duration_ms,
            )

        # 2. Determine content type and extraction path
        ct = fetch_result.content_type.lower()
        is_html = "html" in ct or "xhtml" in ct
        is_json = "json" in ct
        is_plain = "text/plain" in ct

        # 3. Non-HTML bypass paths
        if is_json:
            text, method = _extract_json(fetch_result.text)
            return self._build_result(url, fetch_result, text, method, 0)

        if is_plain:
            text, method = _extract_plaintext(fetch_result.text)
            return self._build_result(url, fetch_result, text, method, 0)

        if not is_html:
            # Unknown content type — try as plaintext
            text, method = _extract_plaintext(fetch_result.text)
            return self._build_result(url, fetch_result, text, method, 0)

        # 4. HTML extraction with graduated levels
        domain = self._get_domain(url)
        start_level = force_level or self._get_start_level(domain)

        return self._extract_html(url, fetch_result, domain, start_level)

    def _extract_html(
        self,
        url: str,
        fetch_result: FetchResult,
        domain: str,
        start_level: int,
    ) -> ExtractionResult:
        """Extract text from HTML with graduated escalation."""
        t0 = time.monotonic()
        html = fetch_result.text
        text = ""
        method = ""

        # Level 1
        if start_level <= LEVEL_1:
            text, method = _extract_level1(html, url)
            if text and not _should_escalate(text, html):
                elapsed = (time.monotonic() - t0) * 1000
                self._update_strategy(domain, LEVEL_1, success=True)
                return self._build_result(
                    url, fetch_result, text, method, LEVEL_1,
                    extraction_duration_ms=elapsed,
                )

        # Level 2
        if start_level <= LEVEL_2:
            text, method = _extract_level2(html, url)
            if text and not _should_escalate(text, html):
                elapsed = (time.monotonic() - t0) * 1000
                self._update_strategy(domain, LEVEL_2, success=True)
                return self._build_result(
                    url, fetch_result, text, method, LEVEL_2,
                    extraction_duration_ms=elapsed,
                )

        # All levels exhausted
        elapsed = (time.monotonic() - t0) * 1000
        self._update_strategy(domain, LEVEL_2, success=False)

        # Return whatever we got, even if low quality
        if text:
            return self._build_result(
                url, fetch_result, text, method or "fallback", LEVEL_2,
                extraction_duration_ms=elapsed,
            )

        return ExtractionResult(
            url=url,
            success=False,
            error="All extraction levels failed to produce usable text",
            fetch_duration_ms=fetch_result.fetch_duration_ms,
            extraction_duration_ms=elapsed,
            raw_size=fetch_result.response_size,
            content_type=fetch_result.content_type,
        )

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _get_domain(url: str) -> str:
        from urllib.parse import urlparse  # noqa: PLC0415
        return urlparse(url).hostname or ""

    def _get_start_level(self, domain: str) -> int:
        strategy = self._domain_strategies.get(domain)
        if strategy is None:
            strategy = get_default_strategy(domain)
        if strategy.should_reprobe_down():
            return max(strategy.preferred_level - 1, LEVEL_1)
        return strategy.preferred_level

    def _update_strategy(self, domain: str, level: int, *, success: bool) -> None:
        current = self._domain_strategies.get(domain) or get_default_strategy(domain)
        if success:
            self._domain_strategies[domain] = current.record_success(level)
        else:
            self._domain_strategies[domain] = current.record_failure(level)

    @staticmethod
    def _build_result(
        url: str,
        fetch_result: FetchResult,
        text: str,
        method: str,
        level: int,
        extraction_duration_ms: float = 0.0,
    ) -> ExtractionResult:
        return ExtractionResult(
            url=url,
            success=bool(text),
            text=text,
            text_length=len(text),
            content_type=fetch_result.content_type,
            extraction_method=method,
            extraction_level=level,
            content_hash=_content_hash(text) if text else "",
            fetch_duration_ms=fetch_result.fetch_duration_ms,
            extraction_duration_ms=extraction_duration_ms,
            raw_size=fetch_result.response_size,
            metadata={
                "status_code": fetch_result.status_code,
                "encoding": fetch_result.encoding,
            },
        )
