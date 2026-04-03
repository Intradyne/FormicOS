"""Operator state snapshot builder.

Assembles the ``OperatorStateSnapshot`` from projection store and config,
matching the ``docs/contracts/types.ts`` shape for WebSocket state messages.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, cast

from formicos.core.settings import CasteRecipeSet, SystemSettings
from formicos.surface.projections import ProjectionStore

if TYPE_CHECKING:
    from formicos.surface.registry import CapabilityRegistry

_SKILL_COLLECTION = "skill_bank_v2"


def build_snapshot(
    store: ProjectionStore,
    settings: SystemSettings,
    castes: CasteRecipeSet | None = None,
    skill_bank_stats: dict[str, Any] | None = None,
    probed_local: dict[str, dict[str, Any]] | None = None,
    provider_health: dict[str, str] | None = None,
    registry: CapabilityRegistry | None = None,
    addon_registrations: list[Any] | None = None,
) -> dict[str, Any]:
    """Build the full operator state snapshot matching types.ts OperatorStateSnapshot."""
    return {
        "tree": _build_tree(store),
        "merges": _build_merges(store),
        "queenThreads": _build_queen_threads(store),
        "approvals": _build_approvals(store),
        "protocolStatus": _build_protocol_status(registry),
        "localModels": _build_local_models(settings, probed=probed_local),
        "cloudEndpoints": _build_cloud_endpoints(settings, provider_health),
        "castes": _build_castes(castes),
        "runtimeConfig": _build_runtime_config(settings, probed=probed_local),
        "skillBankStats": skill_bank_stats or {"total": 0, "avgConfidence": 0.0},
        "addons": _build_addons(addon_registrations),
    }


def _build_addons(
    registrations: list[Any] | None,
) -> list[dict[str, Any]]:
    """Build addon summaries from AddonRegistration objects."""
    if not registrations:
        return []
    result: list[dict[str, Any]] = []
    for reg in registrations:
        manifest = reg.manifest
        if getattr(manifest, "hidden", False):
            continue
        result.append({
            "name": manifest.name,
            "version": manifest.version,
            "description": manifest.description,
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "handler": t.handler,
                    "parameters": t.parameters,
                    "callCount": reg.tool_call_counts.get(t.name, 0),
                }
                for t in manifest.tools
            ],
            "handlers": [
                {
                    "event": h.event,
                    "lastFired": reg.last_handler_fire,
                    "errorCount": reg.handler_error_count,
                }
                for h in manifest.handlers
            ],
            "triggers": [
                {
                    "type": t.type,
                    "schedule": t.schedule,
                    "handler": t.handler,
                    "lastFired": reg.trigger_fire_times.get(t.handler),
                }
                for t in manifest.triggers
            ],
            "panels": [
                {
                    "target": p.get("target", ""),
                    "displayType": p.get("display_type", "status_card"),
                    "path": p.get("path", ""),
                    "addonName": p.get("addon_name", manifest.name),
                    "refreshIntervalS": p.get("refresh_interval_s", 0),
                }
                for p in reg.registered_panels
            ],
            "config": [
                {
                    "key": c.key,
                    "type": c.type,
                    "default": c.default,
                    "label": c.label,
                    "options": c.options,
                }
                for c in manifest.config
            ],
            "status": reg.health_status,
            "lastError": reg.last_error,
            "disabled": getattr(reg, "disabled", False),
        })
    return result


_MAX_COLONIES_PER_THREAD = 20


def _build_tree(store: ProjectionStore) -> list[dict[str, Any]]:
    """Build tree nodes from workspaces → threads → colonies.

    Wave 87: skip archived threads and cap colonies per thread to the
    most recent ``_MAX_COLONIES_PER_THREAD`` to bound snapshot size.
    """
    nodes: list[dict[str, Any]] = []
    for ws in store.workspaces.values():
        ws_node: dict[str, Any] = {
            "id": ws.id,
            "type": "workspace",
            "name": ws.name,
            "parentId": None,
            "config": ws.config,
            "children": [],
        }
        for thread in ws.threads.values():
            # Wave 87: skip archived threads from default snapshot
            if getattr(thread, "status", "active") == "archived":
                continue
            thread_node: dict[str, Any] = {
                "id": thread.id,
                "type": "thread",
                "name": thread.name,
                "parentId": ws.id,
                "children": [],
            }
            # Wave 87: cap colonies to most recent N by sequence/recency
            all_colonies = list(thread.colonies.values())
            if len(all_colonies) > _MAX_COLONIES_PER_THREAD:
                all_colonies = all_colonies[-_MAX_COLONIES_PER_THREAD:]
            for colony in all_colonies:
                colony_node: dict[str, Any] = {
                    "id": colony.id,
                    "type": "colony",
                    "name": colony.display_name or colony.id,
                    "displayName": colony.display_name,
                    "parentId": thread.id,
                    "workspaceId": ws.id,
                    "status": colony.status,
                    "round": colony.round_number,
                    "maxRounds": colony.max_rounds,
                    "task": colony.task,
                    "strategy": colony.strategy,
                    "convergence": colony.convergence,
                    "cost": colony.cost,
                    "budgetLimit": colony.budget_limit,
                    "castes": [
                        s.model_dump() if hasattr(s, "model_dump") else s
                        for s in colony.castes
                    ],
                    "templateId": getattr(colony, "template_id", ""),
                    "agents": [
                        {
                            "id": a.id,
                            "name": a.id,
                            "caste": a.caste,
                            "model": a.model,
                            "tokens": a.tokens,
                            "status": a.status,
                            "pheromone": _agent_pheromone(
                                a.id, getattr(colony, "pheromone_weights", None),
                            ),
                        }
                        for a in colony.agents.values()
                    ],
                    "modelsUsed": list({
                        a.model for a in colony.agents.values()
                    }),
                    "qualityScore": colony.quality_score,
                    "skillsExtracted": colony.skills_extracted,
                    "serviceType": getattr(colony, "service_type", None),
                    "chatMessages": [
                        {
                            "sender": m.sender,
                            "text": m.content,
                            "ts": m.timestamp,
                            "eventKind": m.event_kind,
                            "sourceColony": m.source_colony,
                        }
                        for m in getattr(colony, "chat_messages", [])
                    ],
                    "pheromones": _build_pheromones(colony),
                    "topology": _build_topology(colony),
                    "defense": None,
                    "activeGoal": getattr(colony, "active_goal", "") or colony.task,
                    "redirectHistory": getattr(colony, "redirect_history", []),
                    "routingOverride": getattr(colony, "routing_override", None),
                    "validatorVerdict": getattr(colony, "validator_verdict", None),
                    "validatorTaskType": getattr(colony, "validator_task_type", None),
                    "validatorReason": getattr(colony, "validator_reason", None),
                    "rounds": [
                        {
                            "roundNumber": r.round_number,
                            "phase": r.current_phase,
                            "agents": [
                                _build_round_agent(colony, aid, output, r.tool_calls.get(aid, []))
                                for aid, output in r.agent_outputs.items()
                            ],
                            "convergence": r.convergence,
                            "cost": r.cost,
                            "durationMs": r.duration_ms,
                        }
                        for r in colony.round_records
                    ],
                    # Wave 55: productivity + knowledge-assisted signals
                    "productiveCalls": colony.productive_calls,
                    "observationCalls": colony.observation_calls,
                    "entriesAccessed": len({
                        item.get("id", "")
                        for access in colony.knowledge_accesses
                        for item in access.get("items", [])
                        if item.get("id", "")
                    }),
                }
                thread_node["children"].append(colony_node)
            ws_node["children"].append(thread_node)
        nodes.append(ws_node)
    return nodes


# -- Caste → color map for topology nodes --
_CASTE_COLORS: dict[str, str] = {
    "queen": "#E8581A", "coder": "#2DD4A8", "reviewer": "#A78BFA",
    "researcher": "#5B9CF5", "archivist": "#F5B731",
}


def _agent_pheromone(
    agent_id: str,
    weights: dict[tuple[str, str], float] | None,
) -> float:
    """Derive aggregate pheromone weight for an agent from the weight map.

    Returns the average of all outbound edge weights for this agent.
    Falls back to 0.0 when no pheromone data is available (truthful default).
    """
    if not weights:
        return 0.0
    edges = [w for (src, _dst), w in weights.items() if src == agent_id]
    return round(sum(edges) / len(edges), 3) if edges else 0.0


def _build_pheromones(colony: Any) -> list[dict[str, Any]]:
    """Derive PheromoneEdge[] from colony projection's pheromone_weights."""
    weights: dict[tuple[str, str], float] | None = getattr(
        colony, "pheromone_weights", None,
    )
    if not weights:
        return []
    return [
        {"from": src, "to": dst, "weight": round(w, 3), "trend": "stable"}
        for (src, dst), w in weights.items()
        if w > 0.01
    ]


def _build_topology(colony: Any) -> dict[str, Any] | None:
    """Derive TopologySnapshot from agents + pheromone weights.

    Lays agents in a circle and creates edges from pheromone weights.
    Returns None when the colony has no agents (pre-spawn).
    """
    import math

    agents = list(colony.agents.values())
    if not agents:
        return None

    weights: dict[tuple[str, str], float] | None = getattr(
        colony, "pheromone_weights", None,
    )

    cx, cy, radius = 200, 135, 100
    nodes: list[dict[str, Any]] = []
    for i, a in enumerate(agents):
        angle = (2 * math.pi * i) / len(agents) - math.pi / 2
        nodes.append({
            "id": a.id,
            "label": a.caste.upper(),
            "x": round(cx + radius * math.cos(angle)),
            "y": round(cy + radius * math.sin(angle)),
            "color": _CASTE_COLORS.get(a.caste, "#888888"),
            "caste": a.caste,
        })

    edges: list[dict[str, Any]] = []
    if weights:
        for (src, dst), w in weights.items():
            if w > 0.01:
                edges.append({"from": src, "to": dst, "weight": round(w, 3)})

    return {"nodes": nodes, "edges": edges}


def _build_round_agent(
    colony: Any,
    agent_id: str,
    output: str,
    tool_calls: list[str],
) -> dict[str, Any]:
    agent = colony.agents.get(agent_id)
    return {
        "agentId": agent_id,
        "id": agent_id,
        "name": agent.id if agent is not None else agent_id,
        "model": agent.model if agent is not None else "",
        "tokens": agent.tokens if agent is not None else 0,
        "status": agent.status if agent is not None else "done",
        "output": output,
        "toolCalls": tool_calls,
    }


def _build_merges(store: ProjectionStore) -> list[dict[str, Any]]:
    return [
        {
            "id": m.id,
            "from": m.from_colony,
            "to": m.to_colony,
            "active": m.active,
            "createdBy": m.created_by,
        }
        for m in store.merges.values()
    ]


def _build_queen_threads(store: ProjectionStore) -> list[dict[str, Any]]:
    threads: list[dict[str, Any]] = []
    for ws in store.workspaces.values():
        for thread in ws.threads.values():
            threads.append({
                "id": thread.id,
                "name": thread.name,
                "workspaceId": ws.id,
                "messages": [
                    {
                        "role": m.role, "text": m.content, "ts": m.timestamp,
                        **({"intent": m.intent} if m.intent else {}),
                        **({"render": m.render} if m.render else {}),
                        **({"meta": m.meta} if m.meta else {}),
                    }
                    for m in thread.queen_messages
                ],
            })
    return threads


def _build_approvals(store: ProjectionStore) -> list[dict[str, Any]]:
    return [
        {
            "id": a.id,
            "type": a.approval_type,
            "agent": "",
            "detail": a.detail,
            "colony": a.colony_id,
        }
        for a in store.approvals.values()
    ]


def _build_protocol_status(
    registry: CapabilityRegistry | None = None,
) -> dict[str, Any]:
    # When the capability registry is available, derive protocol status from it.
    if registry is not None:
        result: dict[str, Any] = {}
        for proto in registry.protocols:
            key = proto.name.lower().replace("-", "")
            entry: dict[str, Any] = {"status": proto.status}
            if proto.endpoint is not None:
                entry["endpoint"] = proto.endpoint
            if proto.transport is not None:
                entry["transport"] = proto.transport
            if proto.semantics is not None:
                entry["semantics"] = proto.semantics
            if proto.note is not None:
                entry["note"] = proto.note
            # Add tool/event counts from registry
            if key == "mcp":
                entry["tools"] = len(registry.mcp_tools)
            elif key == "agui":
                entry["events"] = len(registry.agui_events)
            result[key] = entry
        return result

    # Fallback: derive from explicit manifests when registry is not passed.
    try:
        from formicos.surface.mcp_server import MCP_TOOL_NAMES

        mcp_tools = len(MCP_TOOL_NAMES)
    except Exception:  # noqa: BLE001
        mcp_tools = 27  # known tool count from mcp_server.py
    try:
        from formicos.surface.agui_endpoint import AGUI_EVENT_TYPES

        agui_events = len(AGUI_EVENT_TYPES)
    except Exception:  # noqa: BLE001
        agui_events = 9
    return {
        "mcp": {
            "status": "active",
            "tools": mcp_tools,
            "transport": "streamable_http",
            "endpoint": "/mcp",
        },
        "agui": {
            "status": "active",
            "events": agui_events,
            "endpoint": "/ag-ui/runs",
            "semantics": "summary-at-turn-end",
        },
        "a2a": {
            "status": "active",
            "endpoint": "/a2a/tasks",
            "semantics": "submit/poll/attach/result",
            "note": "Inbound task lifecycle with attach events endpoint.",
        },
    }


_LOCAL_PROVIDERS = {"llama-cpp", "llama-cpp-swarm", "ollama", "local"}
_CLOUD_PROVIDERS = {"anthropic", "gemini", "openai", "ollama-cloud", "deepseek", "minimax"}


def _derive_registry_status(
    model: Any,
    probe: dict[str, Any] | None = None,
) -> str:
    """Derive truthful model status from config, env, and live probe data."""
    configured = getattr(model, "status", "available")
    if configured in ("error", "unavailable"):
        return configured
    api_key_env = getattr(model, "api_key_env", None)
    if api_key_env and not os.environ.get(api_key_env):
        return "no_key"
    if getattr(model, "provider", "") in _LOCAL_PROVIDERS:
        probe_status = (probe or {}).get("status")
        if probe_status == "ok":
            return "loaded"
        if probe_status == "error":
            return "error"
    return configured


def _derive_context_window(
    configured: int,
    probe: dict[str, Any] | None = None,
) -> int:
    """Prefer runtime-probed context window when the local server exposes one."""
    probe = probe or {}
    for key in (
        "context_window",
        "contextWindow",
        "ctx_size",
        "ctxSize",
        "n_ctx",
        "nCtx",
        "max_context_length",
        "maxContextLength",
        "context_length",
        "contextLength",
    ):
        val = probe.get(key)
        if isinstance(val, int) and val > 0:
            return val
    nested = probe.get("default_generation_settings")
    if isinstance(nested, dict):
        nested_d = cast("dict[str, Any]", nested)
        for key in ("n_ctx", "ctx_size", "context_window"):
            val = nested_d.get(key)
            if isinstance(val, int) and val > 0:
                return val
    return configured


def _humanize_local_model_name(raw: Any) -> str | None:
    """Convert a local model filename/path into a short display label."""
    if not isinstance(raw, str) or not raw:
        return None
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    if name.lower().endswith(".gguf"):
        name = name[:-5]
    if "-Instruct" in name:
        name = name.split("-Instruct", 1)[0]
    return name or None


def _derive_local_model_name(model: Any, probe: dict[str, Any]) -> str:
    """Choose a human-readable local model name while preserving alias/address elsewhere."""
    for key in ("model_path", "modelPath", "model_file", "modelFile", "model_name", "modelName"):
        label = _humanize_local_model_name(probe.get(key))
        if label:
            return label

    if getattr(model, "provider", "") == "llama-cpp":
        env_label = _humanize_local_model_name(
            os.environ.get("LLM_MODEL_FILE", "Qwen3.5-35B-A3B-Q4_K_M.gguf"),
        )
        if env_label:
            return env_label

    address = getattr(model, "address", "")
    return address.split("/", 1)[-1] if "/" in address else address


def _build_local_models(
    settings: SystemSettings,
    probed: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Derive local model entries from registry config + optional probe data.

    ``probed`` maps endpoint URLs to health data from the local LLM server
    (keys: status, slots_idle, slots_processing, total_slots, slot_details).
    When absent, fields that require runtime telemetry use honest defaults.

    VRAM is only included when backed by a real probe source (currently none
    available from llama.cpp REST API). Phantom gpu/quant fields removed —
    llama.cpp does not expose these via /health or /props.
    """
    models: list[dict[str, Any]] = []
    for m in settings.models.registry:
        if m.provider not in _LOCAL_PROVIDERS:
            continue
        endpoint = m.endpoint or ""
        probe = (probed or {}).get(endpoint, {})
        probe_status = probe.get("status")
        idle = probe.get("slots_idle", 0)
        processing = probe.get("slots_processing", 0)
        total_slots = probe.get("total_slots", idle + processing if probe_status else 0)
        runtime_ctx = _derive_context_window(m.context_window, probe)

        # Slot details (from /health?include_slots)
        raw_details: list[dict[str, Any]] | None = probe.get("slot_details")
        slot_details: list[dict[str, Any]] | None = None
        if isinstance(raw_details, list) and raw_details:
            slot_details = [
                {
                    "id": d.get("id", 0),
                    "state": d.get("state", 0),
                    "nCtx": d.get("n_ctx", 0),
                    "promptTokens": d.get("prompt_tokens", 0),
                }
                for d in raw_details
            ]

        models.append({
            "id": m.address.split("/", 1)[-1] if "/" in m.address else m.address,
            "name": _derive_local_model_name(m, probe),
            "status": _derive_registry_status(m, probe),
            "vram": probe.get("vram"),  # {usedMb, totalMb} from probe or None
            "ctx": runtime_ctx,
            "configuredCtx": m.context_window,
            "maxCtx": runtime_ctx,
            "backend": m.provider,
            "provider": m.provider,
            "slotsTotal": total_slots if probe_status else 0,
            "slotsIdle": idle if probe_status else 0,
            "slotsProcessing": processing if probe_status else 0,
            "slotDetails": slot_details,
        })
    return models


def _build_cloud_endpoints(
    settings: SystemSettings,
    provider_health: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    endpoints: list[dict[str, Any]] = []
    providers_seen: set[str] = set()
    health = provider_health or {}
    for model in settings.models.registry:
        provider = model.provider
        if provider not in _CLOUD_PROVIDERS:
            continue
        if provider in providers_seen:
            continue
        providers_seen.add(provider)
        api_key_set = bool(os.environ.get(model.api_key_env or ""))
        if not api_key_set:
            status = "no_key"
        elif health.get(provider) == "cooldown":
            status = "cooldown"
        else:
            status = "connected"
        endpoints.append({
            "id": provider,
            "provider": provider,
            "models": [
                m.address for m in settings.models.registry if m.provider == provider
            ],
            "status": status,
            "spend": 0,
            "limit": 0,
        })
    return endpoints


def _build_castes(castes: CasteRecipeSet | None) -> list[dict[str, Any]]:
    # FIX BUG 8: Use lowercase keys to match recipe.name from caste_recipes.yaml
    # which has capitalized names like "Queen", "Coder", etc.
    caste_colors = {
        "queen": "#E8581A", "coder": "#2DD4A8", "reviewer": "#A78BFA",
        "researcher": "#5B9CF5", "archivist": "#F5B731",
    }
    caste_icons = {
        "queen": "\u265B", "coder": "</>", "reviewer": "\u2713",
        "researcher": "\u25CE", "archivist": "\u29EB",
    }
    result: list[dict[str, Any]] = []
    if castes is not None:
        for recipe in castes.castes.values():
            key = recipe.name.lower()
            result.append({
                "id": key,
                "name": recipe.name.title(),
                "icon": caste_icons.get(key, "\u25CB"),
                "color": caste_colors.get(key, "#888888"),
                "desc": recipe.description,
            })
    return result


def _build_runtime_config(
    settings: SystemSettings,
    probed: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "system": {
            "host": settings.system.host,
            "port": settings.system.port,
            "dataDir": settings.system.data_dir,
        },
        "models": {
            "defaults": settings.models.defaults.model_dump(),
            "registry": [
                {
                    "address": m.address,
                    "provider": m.provider,
                    "contextWindow": _derive_context_window(
                        m.context_window,
                        (probed or {}).get(m.endpoint or "", {}),
                    ),
                    "supportsTools": m.supports_tools,
                    "status": _derive_registry_status(
                        m,
                        (probed or {}).get(m.endpoint or "", {}),
                    ),
                    "maxOutputTokens": m.max_output_tokens,
                    "timeMultiplier": m.time_multiplier,
                    "toolCallMultiplier": m.tool_call_multiplier,
                }
                for m in settings.models.registry
            ],
        },
        "embedding": {
            "model": settings.embedding.model,
            "dimensions": settings.embedding.dimensions,
        },
        "governance": {
            "maxRoundsPerColony": settings.governance.max_rounds_per_colony,
            "stallDetectionWindow": settings.governance.stall_detection_window,
            "convergenceThreshold": settings.governance.convergence_threshold,
            "defaultBudgetPerColony": settings.governance.default_budget_per_colony,
            "maxRedirectsPerColony": settings.governance.max_redirects_per_colony,
        },
        "routing": {
            "defaultStrategy": settings.routing.default_strategy,
            "tauThreshold": settings.routing.tau_threshold,
            "kInCap": settings.routing.k_in_cap,
            "pheromoneDecayRate": settings.routing.pheromone_decay_rate,
            "pheromoneReinforceRate": settings.routing.pheromone_reinforce_rate,
        },
    }


async def get_skill_bank_detail(
    vector_port: Any,  # noqa: ANN401  — VectorPort protocol
    sort_by: str = "confidence",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch skills with full metadata for the skill browser.

    Uses VectorPort.search() with a broad query to retrieve entries,
    then sorts application-side by the requested field.
    """
    if vector_port is None:
        return []

    results = await vector_port.search(
        collection=_SKILL_COLLECTION,
        query="skill knowledge technique pattern",
        top_k=min(limit, 200),
    )

    entries: list[dict[str, Any]] = []
    for hit in results:
        entries.append({
            "id": hit.id,
            "text_preview": (hit.content or "")[:100],
            "confidence": hit.metadata.get("confidence", 0.5),
            "conf_alpha": hit.metadata.get("conf_alpha"),
            "conf_beta": hit.metadata.get("conf_beta"),
            "algorithm_version": hit.metadata.get("algorithm_version", "v1"),
            "extracted_at": hit.metadata.get("extracted_at", ""),
            "source_colony": (
                hit.metadata.get("source_colony")
                or hit.metadata.get("source_colony_id")
                or "unknown"
            ),
            "merge_count": hit.metadata.get("merge_count", 0),
        })

    if sort_by == "confidence":
        entries.sort(key=lambda e: e["confidence"], reverse=True)
    elif sort_by == "freshness":
        entries.sort(key=lambda e: e["extracted_at"], reverse=True)

    return entries[:limit]


__all__ = ["build_snapshot", "get_skill_bank_detail"]
