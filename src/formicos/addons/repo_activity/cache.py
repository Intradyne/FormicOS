"""Lightweight TTL cache for remote enrichment data (Wave 88 Track C).

In-memory, per-process. Restart clears the cache. No durable persistence.
Designed to prevent repeated remote provider API calls during panel polling.

Local git data does NOT use this cache — it is cheap and always available.
This cache is only for remote enrichment (PRs, CI, remote branches).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import structlog

log = structlog.get_logger()

# Default TTL: 5 minutes. Panels poll every 15-30s, so this avoids
# ~10-20 redundant remote calls per TTL window.
DEFAULT_TTL_S = 300


@dataclass
class CacheEntry:
    """A single cached remote enrichment payload."""

    data: dict[str, Any]
    fetched_at: float
    ttl_s: float
    is_error: bool = False
    error_message: str = ""

    @property
    def age_s(self) -> float:
        return time.monotonic() - self.fetched_at

    @property
    def expired(self) -> bool:
        return self.age_s > self.ttl_s

    @property
    def freshness(self) -> dict[str, Any]:
        """Metadata for the panel to surface cache state to the operator."""
        return {
            "cached": True,
            "fetched_at_mono": self.fetched_at,
            "age_s": round(self.age_s, 1),
            "ttl_s": self.ttl_s,
            "expired": self.expired,
            "is_error": self.is_error,
            "error_message": self.error_message,
        }


class EnrichmentCache:
    """In-memory TTL cache for remote enrichment payloads.

    Cache keys are ``(workspace_id, remote_target, panel_route)`` tuples.

    Usage from an addon handler::

        cache = EnrichmentCache(ttl_s=300)

        hit = cache.get("ws-1", "github:org/repo", "/dashboard")
        if hit is not None and not hit.expired:
            return {**hit.data, "_cache": hit.freshness}

        # Cache miss or expired — fetch remote data
        data = await fetch_remote(...)
        cache.put("ws-1", "github:org/repo", "/dashboard", data)
        return {**data, "_cache": cache.get(...).freshness}
    """

    def __init__(self, *, ttl_s: float = DEFAULT_TTL_S) -> None:
        self._ttl_s = ttl_s
        self._store: dict[tuple[str, str, str], CacheEntry] = {}

    def _key(self, workspace_id: str, remote_target: str, route: str) -> tuple[str, str, str]:
        return (workspace_id, remote_target, route)

    def get(
        self,
        workspace_id: str,
        remote_target: str = "",
        route: str = "",
    ) -> CacheEntry | None:
        """Return the cached entry, or ``None`` on miss.

        Does NOT auto-evict expired entries — the caller decides whether
        to use stale data or refresh.
        """
        return self._store.get(self._key(workspace_id, remote_target, route))

    def put(
        self,
        workspace_id: str,
        remote_target: str,
        route: str,
        data: dict[str, Any],
        *,
        ttl_s: float | None = None,
    ) -> CacheEntry:
        """Store a successful remote enrichment result."""
        entry = CacheEntry(
            data=data,
            fetched_at=time.monotonic(),
            ttl_s=ttl_s if ttl_s is not None else self._ttl_s,
        )
        self._store[self._key(workspace_id, remote_target, route)] = entry
        log.debug(
            "enrichment_cache.put",
            workspace_id=workspace_id,
            remote_target=remote_target,
            route=route,
        )
        return entry

    def put_error(
        self,
        workspace_id: str,
        remote_target: str,
        route: str,
        error_message: str,
        *,
        ttl_s: float | None = None,
    ) -> CacheEntry:
        """Store a failed remote enrichment attempt.

        Caches the error so repeated polls don't hammer a failing provider.
        Uses half the normal TTL by default to retry sooner.
        """
        effective_ttl = (ttl_s if ttl_s is not None else self._ttl_s) / 2
        entry = CacheEntry(
            data={},
            fetched_at=time.monotonic(),
            ttl_s=effective_ttl,
            is_error=True,
            error_message=error_message,
        )
        self._store[self._key(workspace_id, remote_target, route)] = entry
        log.debug(
            "enrichment_cache.put_error",
            workspace_id=workspace_id,
            remote_target=remote_target,
            error=error_message,
        )
        return entry

    def invalidate(
        self,
        workspace_id: str,
        remote_target: str = "",
        route: str = "",
    ) -> bool:
        """Remove a specific cache entry. Returns True if an entry was removed."""
        key = self._key(workspace_id, remote_target, route)
        if key in self._store:
            del self._store[key]
            log.debug(
                "enrichment_cache.invalidated",
                workspace_id=workspace_id,
                remote_target=remote_target,
            )
            return True
        return False

    def invalidate_workspace(self, workspace_id: str) -> int:
        """Remove all cache entries for a workspace. Returns count removed."""
        to_remove = [k for k in self._store if k[0] == workspace_id]
        for k in to_remove:
            del self._store[k]
        if to_remove:
            log.debug(
                "enrichment_cache.invalidated_workspace",
                workspace_id=workspace_id,
                count=len(to_remove),
            )
        return len(to_remove)

    def clear(self) -> int:
        """Clear the entire cache. Returns count removed."""
        count = len(self._store)
        self._store.clear()
        return count

    @property
    def size(self) -> int:
        return len(self._store)


__all__ = ["CacheEntry", "DEFAULT_TTL_S", "EnrichmentCache"]
