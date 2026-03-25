"""Proactive intelligence addon handlers — bridges addon signature to rules."""

from __future__ import annotations

import json
from typing import Any

import structlog

log = structlog.get_logger()


async def handle_query_briefing(
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> str:
    """Query proactive intelligence briefing for a workspace.

    Bridges the standard addon handler signature to
    ``generate_briefing(workspace_id, projections)``.
    """
    from formicos.addons.proactive_intelligence.rules import (  # noqa: PLC0415
        generate_briefing,
    )

    ctx = runtime_context or {}
    projections = ctx.get("projections")
    if projections is None:
        return "Briefing unavailable — projections not in runtime context."

    target_ws = inputs.get("workspace_id", workspace_id)
    categories = inputs.get("categories")

    briefing = generate_briefing(target_ws, projections)

    # Filter by categories if specified
    if categories:
        cat_set = set(categories)
        briefing.insights = [
            i for i in briefing.insights if i.category in cat_set
        ]

    if not briefing.insights:
        return f"No proactive insights for workspace '{target_ws}'."

    lines: list[str] = [
        f"## Proactive Briefing — {len(briefing.insights)} insights\n",
    ]
    for insight in briefing.insights:
        lines.append(
            f"- **[{insight.category}]** {insight.title}: "
            f"{insight.detail}"
        )
        if insight.suggested_colony:
            lines.append(
                f"  → Suggested colony: {insight.suggested_colony.task}"
            )
    return "\n".join(lines)


async def on_scheduled_briefing(
    *,
    runtime_context: dict[str, Any] | None = None,
) -> None:
    """Cron trigger wrapper: run briefing for all workspaces and log results."""
    from formicos.addons.proactive_intelligence.rules import (  # noqa: PLC0415
        generate_briefing,
    )

    ctx = runtime_context or {}
    projections = ctx.get("projections")
    if projections is None:
        log.warning("proactive_intelligence.cron_skip", reason="no projections")
        return

    workspace_ids = list(getattr(projections, "workspaces", {}).keys())
    for ws_id in workspace_ids:
        briefing = generate_briefing(ws_id, projections)
        if briefing.insights:
            log.info(
                "proactive_intelligence.cron_briefing",
                workspace=ws_id,
                insight_count=len(briefing.insights),
            )


async def handle_proactive_configure(
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> str:
    """Enable or disable individual proactive rules per workspace.

    Stores overrides via WorkspaceConfigChanged event.
    """
    ctx = runtime_context or {}

    action = inputs.get("action", "list")
    rule_name = inputs.get("rule_name", "")

    if action == "list":
        return (
            "Available rules: confidence_decline, contradiction, "
            "federation_trust, coverage_gap, stale_cluster, "
            "merge_opportunity, federation_inbound, strategy_efficiency, "
            "diminishing_rounds, cost_outlier, knowledge_roi, "
            "evaporation, branching_stagnation, earned_autonomy, "
            "learned_template_health, recent_outcome_digest, "
            "popular_unexamined"
        )

    if not rule_name:
        return "Error: rule_name is required for enable/disable actions."

    try:
        from datetime import UTC, datetime  # noqa: PLC0415

        from formicos.core.events import WorkspaceConfigChanged  # noqa: PLC0415

        config_key = "proactive_disabled_rules"
        projections = ctx.get("projections")
        current_disabled: list[str] = []
        if projections:
            ws_config = getattr(projections, "workspace_configs", {}).get(
                workspace_id, {},
            )
            current_disabled = list(ws_config.get(config_key, []))

        if action == "disable":
            if rule_name not in current_disabled:
                current_disabled.append(rule_name)
            msg = f"Rule '{rule_name}' disabled."
        elif action == "enable":
            current_disabled = [
                r for r in current_disabled if r != rule_name
            ]
            msg = f"Rule '{rule_name}' enabled."
        else:
            return (
                f"Unknown action '{action}'. "
                "Use 'list', 'enable', or 'disable'."
            )

        runtime = ctx.get("runtime")
        emit_fn = getattr(runtime, "emit_and_broadcast", None)
        if emit_fn is not None:
            await emit_fn(WorkspaceConfigChanged(
                seq=0,
                timestamp=datetime.now(UTC),
                address=workspace_id,
                workspace_id=workspace_id,
                field=config_key,
                new_value=json.dumps(current_disabled),
            ))

        return msg
    except Exception as exc:  # noqa: BLE001
        return f"Failed to update rule config: {exc}"
