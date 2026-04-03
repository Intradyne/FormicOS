"""Manual refresh helper for repo-activity remote enrichment (Wave 88 Track C).

Provides an addon-trigger-compatible handler that invalidates the remote
enrichment cache, forcing the next panel poll to re-fetch from the provider.

Intended to be wired into the addon trigger surface so operators and the
Queen can force a refresh without waiting for TTL expiry.
"""

from __future__ import annotations

from typing import Any

import structlog

from formicos.addons.repo_activity.cache import EnrichmentCache

log = structlog.get_logger()

# Module-level singleton. Team B's handler should import and use the same
# instance so cache state is shared within the process.
_cache: EnrichmentCache | None = None


def get_shared_cache(*, ttl_s: float = 300) -> EnrichmentCache:
    """Return the process-wide shared enrichment cache.

    Creates the singleton on first call. Subsequent calls return the same
    instance regardless of ``ttl_s``.
    """
    global _cache  # noqa: PLW0603
    if _cache is None:
        _cache = EnrichmentCache(ttl_s=ttl_s)
    return _cache


async def handle_refresh(
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> str:
    """Addon trigger handler: invalidate remote enrichment cache.

    Can be invoked via:
    - ``trigger_addon(addon="repo-activity", trigger="refresh")``
    - ``POST /api/v1/addons/repo-activity/trigger/refresh``

    Accepts optional ``remote_target`` in inputs to scope invalidation.
    If omitted, invalidates all entries for the workspace.
    """
    cache = get_shared_cache()
    remote_target = inputs.get("remote_target", "")

    if remote_target:
        # Invalidate all routes for this workspace+target
        count = 0
        for key in list(cache._store):  # noqa: SLF001
            if key[0] == workspace_id and key[1] == remote_target:
                del cache._store[key]  # noqa: SLF001
                count += 1
        log.info(
            "repo_activity.refresh_targeted",
            workspace_id=workspace_id,
            remote_target=remote_target,
            removed=count,
        )
        return (
            f"Invalidated {count} cached entries for {remote_target}."
            if count
            else f"No cached entries for {remote_target}."
        )

    count = cache.invalidate_workspace(workspace_id)
    log.info(
        "repo_activity.refresh_workspace",
        workspace_id=workspace_id,
        removed=count,
    )
    return f"Invalidated {count} cached enrichment entries for workspace."


def reset_shared_cache() -> None:
    """Clear and reset the singleton (for testing)."""
    global _cache  # noqa: PLW0603
    if _cache is not None:
        _cache.clear()
    _cache = None


__all__ = ["get_shared_cache", "handle_refresh", "reset_shared_cache"]
