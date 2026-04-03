"""Wave 88 Track C: enrichment cache + refresh tests."""

from __future__ import annotations

import time

import pytest

from formicos.addons.repo_activity.cache import CacheEntry, EnrichmentCache
from formicos.addons.repo_activity.refresh import (
    get_shared_cache,
    handle_refresh,
    reset_shared_cache,
)


def setup_function() -> None:
    reset_shared_cache()


# ---------------------------------------------------------------------------
# CacheEntry
# ---------------------------------------------------------------------------


class TestCacheEntry:
    def test_not_expired_within_ttl(self) -> None:
        entry = CacheEntry(data={"prs": 5}, fetched_at=time.monotonic(), ttl_s=300)
        assert not entry.expired

    def test_expired_past_ttl(self) -> None:
        entry = CacheEntry(data={}, fetched_at=time.monotonic() - 400, ttl_s=300)
        assert entry.expired

    def test_freshness_metadata(self) -> None:
        entry = CacheEntry(data={"x": 1}, fetched_at=time.monotonic(), ttl_s=60)
        f = entry.freshness
        assert f["cached"] is True
        assert f["ttl_s"] == 60
        assert not f["expired"]
        assert f["is_error"] is False

    def test_error_freshness(self) -> None:
        entry = CacheEntry(
            data={}, fetched_at=time.monotonic(), ttl_s=60,
            is_error=True, error_message="timeout",
        )
        f = entry.freshness
        assert f["is_error"] is True
        assert f["error_message"] == "timeout"


# ---------------------------------------------------------------------------
# EnrichmentCache
# ---------------------------------------------------------------------------


class TestEnrichmentCache:
    def test_miss_returns_none(self) -> None:
        cache = EnrichmentCache()
        assert cache.get("ws-1", "github:org/repo", "/dashboard") is None

    def test_put_then_hit(self) -> None:
        cache = EnrichmentCache()
        cache.put("ws-1", "github:org/repo", "/dashboard", {"prs": 3})
        hit = cache.get("ws-1", "github:org/repo", "/dashboard")
        assert hit is not None
        assert hit.data == {"prs": 3}
        assert not hit.expired

    def test_ttl_expiry(self) -> None:
        cache = EnrichmentCache(ttl_s=0.01)  # 10ms TTL
        cache.put("ws-1", "remote", "/dash", {"x": 1})
        time.sleep(0.02)
        hit = cache.get("ws-1", "remote", "/dash")
        assert hit is not None
        assert hit.expired

    def test_invalidate_specific(self) -> None:
        cache = EnrichmentCache()
        cache.put("ws-1", "remote", "/a", {"a": 1})
        cache.put("ws-1", "remote", "/b", {"b": 2})
        assert cache.invalidate("ws-1", "remote", "/a")
        assert cache.get("ws-1", "remote", "/a") is None
        assert cache.get("ws-1", "remote", "/b") is not None

    def test_invalidate_workspace(self) -> None:
        cache = EnrichmentCache()
        cache.put("ws-1", "r1", "/a", {"a": 1})
        cache.put("ws-1", "r2", "/b", {"b": 2})
        cache.put("ws-2", "r1", "/a", {"c": 3})
        assert cache.invalidate_workspace("ws-1") == 2
        assert cache.get("ws-1", "r1", "/a") is None
        assert cache.get("ws-2", "r1", "/a") is not None

    def test_put_error(self) -> None:
        cache = EnrichmentCache(ttl_s=300)
        entry = cache.put_error("ws-1", "remote", "/dash", "server timeout")
        assert entry.is_error
        assert entry.error_message == "server timeout"
        assert entry.ttl_s == 150  # half of normal TTL

    def test_clear(self) -> None:
        cache = EnrichmentCache()
        cache.put("ws-1", "r", "/a", {})
        cache.put("ws-2", "r", "/b", {})
        assert cache.clear() == 2
        assert cache.size == 0

    def test_different_keys_are_independent(self) -> None:
        cache = EnrichmentCache()
        cache.put("ws-1", "github:org/a", "/dash", {"repo": "a"})
        cache.put("ws-1", "github:org/b", "/dash", {"repo": "b"})
        a = cache.get("ws-1", "github:org/a", "/dash")
        b = cache.get("ws-1", "github:org/b", "/dash")
        assert a is not None and a.data["repo"] == "a"
        assert b is not None and b.data["repo"] == "b"

    def test_local_only_does_not_need_cache(self) -> None:
        cache = EnrichmentCache()
        assert cache.get("ws-1") is None
        assert cache.size == 0


# ---------------------------------------------------------------------------
# Shared cache + refresh handler
# ---------------------------------------------------------------------------


class TestSharedCache:
    def test_singleton(self) -> None:
        a = get_shared_cache()
        b = get_shared_cache()
        assert a is b

    def test_reset_clears(self) -> None:
        c = get_shared_cache()
        c.put("ws-1", "r", "/a", {"x": 1})
        reset_shared_cache()
        c2 = get_shared_cache()
        assert c2.size == 0


class TestHandleRefresh:
    @pytest.mark.anyio()
    async def test_refresh_workspace(self) -> None:
        cache = get_shared_cache()
        cache.put("ws-1", "github:org/repo", "/dash", {"prs": 5})
        result = await handle_refresh({}, "ws-1", "t-1")
        assert "1" in result  # "Invalidated 1 cached..."
        assert cache.get("ws-1", "github:org/repo", "/dash") is None

    @pytest.mark.anyio()
    async def test_refresh_targeted(self) -> None:
        reset_shared_cache()
        cache = get_shared_cache()
        cache.put("ws-1", "github:org/repo", "/dash", {"prs": 5})
        cache.put("ws-1", "gitlab:org/other", "/dash", {"mrs": 3})
        result = await handle_refresh(
            {"remote_target": "github:org/repo"}, "ws-1", "t-1",
        )
        assert "1" in result  # "Invalidated 1 cached entries..."
        assert cache.get("ws-1", "github:org/repo", "/dash") is None
        assert cache.get("ws-1", "gitlab:org/other", "/dash") is not None

    @pytest.mark.anyio()
    async def test_refresh_empty_cache(self) -> None:
        reset_shared_cache()
        result = await handle_refresh({}, "ws-1", "t-1")
        assert "0" in result
