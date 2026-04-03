"""System-health addon handler — reads live runtime state (Wave 87).

Returns declarative panel payloads for the workspace-mounted health
dashboard. Reads projections and data-dir state directly via
``runtime_context`` — no self-HTTP calls.
"""

from __future__ import annotations

from typing import Any


async def get_overview(
    inputs: dict[str, Any],
    workspace_id: str,
    _thread_id: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a system-health overview payload."""
    ctx = runtime_context or {}
    projections = ctx.get("projections")
    data_dir = ctx.get("data_dir", "")

    # Use workspace_id from query params if provided
    ws_id = inputs.get("workspace_id", "") or workspace_id or "default"

    result: dict[str, Any] = {
        "display_type": "status_card",
        "items": [],
    }
    items: list[dict[str, str]] = result["items"]

    # Colony metrics
    colony_stats = _colony_stats(projections, ws_id)
    items.append({"label": "Recent Colonies", "value": str(colony_stats["total"])})
    items.append({"label": "Succeeded", "value": str(colony_stats["succeeded"])})
    items.append({"label": "Failed", "value": str(colony_stats["failed"])})
    items.append({"label": "Avg Quality", "value": f"{colony_stats['avg_quality']:.2f}"})

    # Memory entries
    entry_count = _memory_entry_count(projections)
    items.append({"label": "Memory Entries", "value": str(entry_count)})

    # Plan patterns
    pattern_stats = _pattern_stats(data_dir, ws_id)
    items.append({
        "label": "Plan Patterns",
        "value": (
            f"{pattern_stats['approved']} approved, "
            f"{pattern_stats['candidate']} candidate"
        ),
    })

    # Codebase index
    index_health = await _index_health(ctx, ws_id)
    items.append({"label": "Code Index", "value": index_health})

    return result


def _colony_stats(projections: Any, workspace_id: str) -> dict[str, Any]:
    """Aggregate recent colony outcomes."""
    if projections is None:
        return {"total": 0, "succeeded": 0, "failed": 0, "avg_quality": 0.0}

    try:
        colonies = list(projections.colonies.values())
    except Exception:
        return {"total": 0, "succeeded": 0, "failed": 0, "avg_quality": 0.0}

    ws_colonies = [
        c for c in colonies
        if getattr(c, "workspace_id", "") == workspace_id
        and getattr(c, "status", "") in ("completed", "failed")
    ]

    total = len(ws_colonies)
    succeeded = sum(1 for c in ws_colonies if c.status == "completed")
    failed = total - succeeded

    qualities = [
        getattr(c, "quality_score", 0.0) or 0.0
        for c in ws_colonies
        if c.status == "completed" and getattr(c, "quality_score", None)
    ]
    avg_q = sum(qualities) / max(len(qualities), 1)

    return {
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "avg_quality": round(avg_q, 3),
    }


def _memory_entry_count(projections: Any) -> int:
    """Count total memory entries."""
    if projections is None:
        return 0
    try:
        return len(getattr(projections, "memory_entries", {}))
    except Exception:
        return 0


def _pattern_stats(data_dir: str, workspace_id: str) -> dict[str, int]:
    """Count approved vs candidate plan patterns."""
    if not data_dir:
        return {"approved": 0, "candidate": 0}
    try:
        from formicos.surface.plan_patterns import list_patterns  # noqa: PLC0415

        patterns = list_patterns(data_dir, workspace_id)
        approved = sum(
            1 for p in patterns
            if p.get("status", "approved") == "approved"
        )
        candidate = sum(
            1 for p in patterns if p.get("status") == "candidate"
        )
        return {"approved": approved, "candidate": candidate}
    except Exception:
        return {"approved": 0, "candidate": 0}


async def _index_health(ctx: dict[str, Any], workspace_id: str) -> str:
    """Summarize codebase index health."""
    try:
        from formicos.addons.codebase_index.status import get_status  # noqa: PLC0415

        result = get_status({}, workspace_id, "", runtime_context=ctx)
        if hasattr(result, "__await__"):
            result = await result
        items = result.get("items", [])
        for item in items:
            if item.get("label") == "Status":
                return str(item.get("value", "unknown"))
        return "available"
    except Exception:
        return "not configured"
