"""Handler for colony addon — colony-authored dashboard."""

from __future__ import annotations

from typing import Any


async def get_overview(
    inputs: dict[str, Any],
    workspace_id: str,
    _thread_id: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a dashboard payload for the colony addon."""
    ctx = runtime_context or {}
    projections = ctx.get("projections")
    data_dir = ctx.get("data_dir", "")

    ws_id = inputs.get("workspace_id", "") or workspace_id or "default"

    items: list[dict[str, Any]] = []

    # Colony metrics
    colonies = []
    if projections:
        try:
            colonies = [
                c for c in projections.colonies.values()
                if getattr(c, "workspace_id", "") == ws_id
                and getattr(c, "status", "") in ("completed", "failed")
            ]
        except Exception:
            pass

    total = len(colonies)
    succeeded = sum(1 for c in colonies if getattr(c, "status", "") == "completed")
    failed = total - succeeded
    qualities = [
        getattr(c, "quality_score", 0.0) or 0.0
        for c in colonies
        if getattr(c, "status", "") == "completed"
        and getattr(c, "quality_score", None)
    ]
    avg_q = round(sum(qualities) / max(len(qualities), 1), 3)

    items.append({"label": "Colonies", "value": total, "status": "ok" if failed == 0 else "warn"})
    items.append({"label": "Succeeded", "value": succeeded})
    items.append({"label": "Failed", "value": failed, "status": "error" if failed > 0 else "ok"})
    items.append({"label": "Avg Quality", "value": f"{avg_q:.2f}", "trend": qualities[-10:]})

    # Memory entries
    entry_count = 0
    if projections:
        try:
            entry_count = len(getattr(projections, "memory_entries", {}))
        except Exception:
            pass
    items.append({"label": "Memory Entries", "value": entry_count})

    # Plan patterns
    approved = 0
    candidate = 0
    if data_dir:
        try:
            from formicos.surface.plan_patterns import list_patterns
            patterns = list_patterns(data_dir, ws_id)
            approved = sum(1 for p in patterns if p.get("status", "approved") == "approved")
            candidate = sum(1 for p in patterns if p.get("status") == "candidate")
        except Exception:
            pass
    pat_val = f"{approved} approved, {candidate} candidate"
    items.append({"label": "Patterns", "value": pat_val})

    # --- CUSTOMIZE BELOW: add additional dashboard sections ---
    # Example: items.append({"label": "Custom Metric", "value": 42})
    additional_items: list[dict[str, Any]] = []
    # --- CUSTOMIZE ABOVE ---

    items.extend(additional_items)

    return {
        "display_type": "kpi_card",
        "items": items,
        "refresh_interval_s": 30,
    }
