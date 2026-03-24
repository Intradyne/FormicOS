"""Protocol routes — Agent Card, AG-UI endpoint, MCP mount."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

import formicos
from formicos.surface.agui_endpoint import handle_agui_run
from formicos.surface.template_manager import load_all_templates

if TYPE_CHECKING:
    from starlette.applications import Starlette
    from starlette.requests import Request

    from formicos.surface.projections import ProjectionStore
    from formicos.surface.runtime import Runtime


def _compute_domain_stats(
    memory_entries: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compute per-domain entry counts and average confidence."""
    domain_data: dict[str, list[float]] = {}
    for entry in memory_entries.values():
        if entry.get("status") == "rejected":
            continue
        alpha = float(entry.get("conf_alpha", 5.0))
        beta = float(entry.get("conf_beta", 5.0))
        conf = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.5
        for domain in entry.get("domains", []):
            domain_data.setdefault(domain, []).append(conf)
    return sorted(
        [
            {
                "name": name,
                "count": len(confs),
                "avg_confidence": round(sum(confs) / len(confs), 3),
            }
            for name, confs in domain_data.items()
        ],
        key=lambda d: d["count"],
        reverse=True,
    )


def _check_gpu() -> bool:
    """Best-effort GPU availability check (no import cost)."""
    import os  # noqa: PLC0415
    return bool(os.environ.get("CUDA_VISIBLE_DEVICES") or os.environ.get("NVIDIA_VISIBLE_DEVICES"))


def routes(
    *,
    runtime: Runtime,
    projections: ProjectionStore,
    mcp_http: Starlette,
    **_unused: Any,
) -> list[BaseRoute]:
    """Build protocol routes (Agent Card, AG-UI, MCP)."""

    async def agent_card(request: Request) -> JSONResponse:
        """Serve /.well-known/agent.json for A2A agent discovery.

        Wave 33 B9: dynamic Agent Card with live state.
        """
        templates = await load_all_templates(
            projection_templates=projections.templates,
        )
        skills = [
            {
                "id": t.template_id,
                "name": t.name,
                "description": t.description,
                "tags": t.tags,
                "examples": [f"Run a {t.name.lower()} colony"],
            }
            for t in templates
        ]

        # Dynamic knowledge stats
        domains = _compute_domain_stats(projections.memory_entries)
        non_rejected = sum(
            1 for e in projections.memory_entries.values()
            if e.get("status") != "rejected"
        )

        # Active thread count
        active_threads = 0
        for ws in projections.workspaces.values():
            for t in ws.threads.values():
                if getattr(t, "status", "active") == "active":
                    active_threads += 1

        # Wave 38 1A: detect configured external specialists
        external_specialists: list[dict[str, str]] = []
        cm = getattr(runtime, "colony_manager", None)
        if cm is not None:
            sr = getattr(cm, "service_router", None)
            if sr is not None:
                for svc_type in sr.active_services:
                    if svc_type.startswith("service:external:"):
                        external_specialists.append({
                            "service_type": svc_type,
                            "status": "active",
                        })

        card: dict[str, Any] = {
            "name": "FormicOS",
            "description": (
                "Stigmergic multi-agent colony framework. "
                "Accepts tasks, spawns agent colonies, returns results."
            ),
            "url": str(request.base_url).rstrip("/"),
            "version": formicos.__version__,
            "capabilities": {
                "streaming": True,
                "pushNotifications": False,
            },
            "protocols": {
                "mcp": {
                    "endpoint": "/mcp",
                    "transport": "Streamable HTTP",
                },
                "agui": {
                    "endpoint": "/ag-ui/runs",
                    "semantics": "summary-at-turn-end",
                },
                "a2a": {
                    "endpoint": "/a2a/tasks",
                    "version": "custom-colony-backed",
                    "conformance_note": (
                        "Colony-backed task lifecycle. Not a full Google A2A "
                        "JSON-RPC implementation. Supports REST submit/poll/"
                        "attach/result/cancel over HTTP."
                    ),
                    "submission": "POST /a2a/tasks with {description: string}",
                    "polling": "GET /a2a/tasks/{task_id}",
                    "events": "GET /a2a/tasks/{task_id}/events (SSE, snapshot-then-live-tail)",
                    "result": "GET /a2a/tasks/{task_id}/result (available when terminal)",
                    "cancel": "DELETE /a2a/tasks/{task_id}",
                    "streaming": True,
                    "authentication": "none (local-first deployment)",
                },
            },
            "defaultInputModes": ["text/plain"],
            "defaultOutputModes": ["text/plain"],
            "skills": skills,
            "knowledge": {
                "total_entries": non_rejected,
                "domains": domains,
            },
            "threads": {
                "active_count": active_threads,
            },
            "external_specialists": external_specialists,
            "federation": {
                "enabled": hasattr(runtime, "federation_manager"),
                "peer_count": 0,
                "trust_scores": {},
            },
            "hardware": {
                "gpu_available": _check_gpu(),
            },
        }
        return JSONResponse(card)

    return [
        Route("/.well-known/agent.json", agent_card, methods=["GET"]),
        Route("/ag-ui/runs", handle_agui_run, methods=["POST"]),
        *list(mcp_http.routes),
    ]
