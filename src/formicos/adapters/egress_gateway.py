# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""EgressGateway — bounded outbound HTTP policy adapter (Wave 44).

Policy-and-transport layer only. Does NOT decide admission, knowledge policy,
or orchestration. The caller (fetch_pipeline, forager surface) decides what
to do with the response.

Strict v1 rule: fetch only URLs that came from the search layer or explicit
operator-approved domain overrides. Callers must pass ``origin`` to declare
where the URL came from.

Controls enforced:
  - domain allowlist / denylist
  - per-domain rate limiting (token bucket)
  - maximum response size
  - request timeout
  - honest user-agent string
  - robots.txt checking with TTL cache
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_USER_AGENT = "FormicOS-Forager/0.1 (+https://github.com/Intradyne/FormicOS)"
_DEFAULT_TIMEOUT = 15.0
_DEFAULT_MAX_BYTES = 500_000  # 500 KB
_DEFAULT_RATE_LIMIT = 2.0  # requests per second per domain
_DEFAULT_RATE_BURST = 5  # burst capacity
_ROBOTS_CACHE_TTL = 3600  # 1 hour


@dataclass(frozen=True)
class EgressPolicy:
    """Immutable egress policy configuration."""

    allowed_domains: list[str] = field(default_factory=list)
    denied_domains: list[str] = field(default_factory=list)
    operator_approved_domains: list[str] = field(default_factory=list)
    max_response_bytes: int = _DEFAULT_MAX_BYTES
    timeout_seconds: float = _DEFAULT_TIMEOUT
    rate_limit_per_second: float = _DEFAULT_RATE_LIMIT
    rate_burst: int = _DEFAULT_RATE_BURST
    user_agent: str = _DEFAULT_USER_AGENT
    respect_robots_txt: bool = True


# ---------------------------------------------------------------------------
# Fetch origin declaration
# ---------------------------------------------------------------------------


class FetchOrigin:
    """Declares where a URL came from (strict v1 rule)."""

    SEARCH_RESULT = "search_result"
    OPERATOR_APPROVED = "operator_approved"


# ---------------------------------------------------------------------------
# Fetch result
# ---------------------------------------------------------------------------


@dataclass
class FetchResult:
    """Structured result from an egress fetch."""

    url: str
    success: bool
    status_code: int = 0
    content_type: str = ""
    raw_bytes: bytes = b""
    text: str = ""
    encoding: str = "utf-8"
    error: str = ""
    response_size: int = 0
    fetch_duration_ms: float = 0.0
    robots_blocked: bool = False


# ---------------------------------------------------------------------------
# Rate limiter (token bucket per domain)
# ---------------------------------------------------------------------------


class _TokenBucket:
    __slots__ = ("_rate", "_burst", "_tokens", "_last_refill")

    def __init__(self, rate: float, burst: int) -> None:
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()

    def try_consume(self) -> bool:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(float(self._burst), self._tokens + elapsed * self._rate)
        self._last_refill = now
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False

    @property
    def wait_seconds(self) -> float:
        if self._tokens >= 1.0:
            return 0.0
        return (1.0 - self._tokens) / self._rate


# ---------------------------------------------------------------------------
# Robots.txt cache
# ---------------------------------------------------------------------------


@dataclass
class _RobotsEntry:
    disallowed_paths: list[str]
    fetched_at: float


# ---------------------------------------------------------------------------
# EgressGateway
# ---------------------------------------------------------------------------


class EgressGateway:
    """Bounded outbound HTTP gateway with policy enforcement."""

    def __init__(self, policy: EgressPolicy | None = None) -> None:
        self._policy = policy or EgressPolicy()
        self._rate_limiters: dict[str, _TokenBucket] = {}
        self._robots_cache: dict[str, _RobotsEntry] = {}
        self._lock = asyncio.Lock()

    @property
    def policy(self) -> EgressPolicy:
        return self._policy

    def update_policy(self, policy: EgressPolicy) -> None:
        self._policy = policy

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    async def fetch(
        self,
        url: str,
        *,
        origin: str,
        max_bytes: int | None = None,
        timeout: float | None = None,
    ) -> FetchResult:
        """Fetch a URL with full policy enforcement.

        Args:
            url: The URL to fetch.
            origin: Must be FetchOrigin.SEARCH_RESULT or OPERATOR_APPROVED.
            max_bytes: Override max response bytes (capped by policy).
            timeout: Override timeout (capped by policy).
        """
        t0 = time.monotonic()
        effective_max = min(max_bytes or self._policy.max_response_bytes,
                           self._policy.max_response_bytes)
        effective_timeout = min(timeout or self._policy.timeout_seconds,
                                self._policy.timeout_seconds)

        # 1. Validate origin
        if origin not in (FetchOrigin.SEARCH_RESULT, FetchOrigin.OPERATOR_APPROVED):
            return FetchResult(
                url=url, success=False,
                error=f"Invalid fetch origin: {origin!r}. "
                      "v1 only allows search_result or operator_approved.",
            )

        # 2. Parse and validate domain
        parsed = urlparse(url)
        domain = parsed.hostname or ""
        if not domain:
            return FetchResult(url=url, success=False, error="Could not parse domain from URL")

        # 3. Domain policy check
        domain_ok, domain_reason = self._check_domain(domain, origin)
        if not domain_ok:
            return FetchResult(url=url, success=False, error=domain_reason)

        # 4. Rate limit
        rate_ok = await self._check_rate_limit(domain)
        if not rate_ok:
            return FetchResult(
                url=url, success=False,
                error=f"Rate limit exceeded for domain {domain}",
            )

        # 5. robots.txt
        if self._policy.respect_robots_txt:
            robots_ok = await self._check_robots(url, domain, parsed.path or "/",
                                                  effective_timeout)
            if not robots_ok:
                return FetchResult(
                    url=url, success=False, robots_blocked=True,
                    error=f"Blocked by robots.txt for {domain}",
                )

        # 6. Fetch
        try:
            async with httpx.AsyncClient(
                timeout=effective_timeout,
                headers={"User-Agent": self._policy.user_agent},
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()

                # Enforce size limit
                raw = resp.content[:effective_max]
                content_type = resp.headers.get("content-type", "")
                encoding = resp.encoding or "utf-8"

                elapsed_ms = (time.monotonic() - t0) * 1000

                return FetchResult(
                    url=url,
                    success=True,
                    status_code=resp.status_code,
                    content_type=content_type,
                    raw_bytes=raw,
                    text=raw.decode(encoding, errors="replace"),
                    encoding=encoding,
                    response_size=len(raw),
                    fetch_duration_ms=elapsed_ms,
                )

        except httpx.HTTPStatusError as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000
            return FetchResult(
                url=url, success=False,
                status_code=exc.response.status_code,
                error=f"HTTP {exc.response.status_code}: {exc}",
                fetch_duration_ms=elapsed_ms,
            )
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = (time.monotonic() - t0) * 1000
            return FetchResult(
                url=url, success=False,
                error=f"Fetch error: {exc}",
                fetch_duration_ms=elapsed_ms,
            )

    # -----------------------------------------------------------------------
    # Domain policy
    # -----------------------------------------------------------------------

    def _check_domain(self, domain: str, origin: str) -> tuple[bool, str]:
        """Check domain against allow/deny lists."""
        # Denylist always wins
        if self._domain_matches(domain, self._policy.denied_domains):
            return False, f"Domain {domain} is on the deny list"

        # Operator-approved domains always pass
        if origin == FetchOrigin.OPERATOR_APPROVED:
            if self._domain_matches(domain, self._policy.operator_approved_domains):
                return True, ""
            return False, (
                f"Domain {domain} not in operator-approved list "
                "for operator_approved origin"
            )

        # Search results: if allowlist is set, domain must match
        if self._policy.allowed_domains:
            if self._domain_matches(domain, self._policy.allowed_domains):
                return True, ""
            return False, f"Domain {domain} not in allowlist"

        # No allowlist = open (search results only)
        return True, ""

    @staticmethod
    def _domain_matches(domain: str, domain_list: list[str]) -> bool:
        """Check if domain matches any entry (supports subdomain matching)."""
        return any(domain == d or domain.endswith(f".{d}") for d in domain_list)

    # -----------------------------------------------------------------------
    # Rate limiting
    # -----------------------------------------------------------------------

    async def _check_rate_limit(self, domain: str) -> bool:
        async with self._lock:
            bucket = self._rate_limiters.get(domain)
            if bucket is None:
                bucket = _TokenBucket(
                    self._policy.rate_limit_per_second,
                    self._policy.rate_burst,
                )
                self._rate_limiters[domain] = bucket
            return bucket.try_consume()

    # -----------------------------------------------------------------------
    # robots.txt
    # -----------------------------------------------------------------------

    async def _check_robots(
        self, url: str, domain: str, path: str, timeout: float,
    ) -> bool:
        """Check robots.txt. Returns True if fetch is allowed."""
        now = time.monotonic()

        # Check cache
        cached = self._robots_cache.get(domain)
        if cached and (now - cached.fetched_at) < _ROBOTS_CACHE_TTL:
            return not self._path_disallowed(path, cached.disallowed_paths)

        # Fetch robots.txt
        robots_url = f"{urlparse(url).scheme}://{domain}/robots.txt"
        disallowed: list[str] = []

        try:
            async with httpx.AsyncClient(
                timeout=min(timeout, 5.0),
                headers={"User-Agent": self._policy.user_agent},
            ) as client:
                resp = await client.get(robots_url, follow_redirects=True)
                if resp.status_code == 200:
                    disallowed = self._parse_robots(resp.text)
        except Exception:  # noqa: BLE001
            # If we can't fetch robots.txt, allow the request
            pass

        self._robots_cache[domain] = _RobotsEntry(
            disallowed_paths=disallowed,
            fetched_at=now,
        )
        return not self._path_disallowed(path, disallowed)

    @staticmethod
    def _parse_robots(text: str) -> list[str]:
        """Parse robots.txt for Disallow rules targeting * or FormicOS."""
        disallowed: list[str] = []
        in_relevant_block = False

        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue

            if line.lower().startswith("user-agent:"):
                agent = line.split(":", 1)[1].strip().lower()
                in_relevant_block = agent in ("*", "formicos-forager")
            elif line.lower().startswith("disallow:") and in_relevant_block:
                path = line.split(":", 1)[1].strip()
                if path:
                    disallowed.append(path)

        return disallowed

    @staticmethod
    def _path_disallowed(path: str, disallowed: list[str]) -> bool:
        return any(path.startswith(d) for d in disallowed)

    # -----------------------------------------------------------------------
    # Introspection
    # -----------------------------------------------------------------------

    def domain_is_allowed(self, domain: str, origin: str) -> bool:
        """Check if a domain would be allowed under current policy."""
        ok, _ = self._check_domain(domain, origin)
        return ok

    def get_stats(self) -> dict[str, Any]:
        """Return gateway statistics for observability."""
        return {
            "rate_limiters_active": len(self._rate_limiters),
            "robots_cache_size": len(self._robots_cache),
            "policy_allowed_domains": len(self._policy.allowed_domains),
            "policy_denied_domains": len(self._policy.denied_domains),
            "policy_operator_approved": len(self._policy.operator_approved_domains),
        }
