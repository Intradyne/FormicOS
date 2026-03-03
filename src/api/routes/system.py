"""
FormicOS v0.7.9 -- V1 System Routes

Routes: /system, /system/health, /system/metrics, /models, /models/health,
        /tools, /tools/catalog, /suggest-team
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Request
from src.llm_client import AioLLMClient

from src.api.helpers import api_error_v1
from src.mcp_client import MCPGatewayClient
from src.model_registry import ModelRegistry
from src.models import FormicOSConfig, SuggestTeamRequest
from src.server import VERSION

logger = logging.getLogger("formicos.server")

router = APIRouter()


# -- System --

@router.get("/system")
async def v1_get_system(request: Request):
    app = request.app
    gpu = getattr(app.state, "gpu_stats", {"status": "unknown"})
    from src.context import AsyncContextTree
    ctx_sys: AsyncContextTree = app.state.ctx
    return {
        "version": VERSION,
        "schema_version": "1.0",
        "llm_model": ctx_sys.get("system", "llm_model"),
        "llm_endpoint": ctx_sys.get("system", "llm_endpoint"),
        "gpu": gpu,
        "vram_budget": app.state.model_registry.get_vram_budget(),
    }


@router.get("/system/health")
async def v1_system_health(request: Request):
    app = request.app
    checks: dict[str, str] = {}
    # LLM check
    mr: ModelRegistry = app.state.model_registry
    try:
        models = mr.list_models()
        checks["llm"] = "healthy" if models else "degraded"
    except Exception:
        checks["llm"] = "unhealthy"

    # MCP check
    mcp: MCPGatewayClient = app.state.mcp_client
    checks["mcp"] = "healthy" if mcp.connected else "unavailable"

    # Embedding check
    checks["embedding"] = "healthy" if app.state.routing_embedder else "unavailable"

    overall = "healthy"
    if any(v == "unhealthy" for v in checks.values()):
        overall = "degraded"
    return {"status": overall, "checks": checks}


@router.get("/system/metrics")
async def v1_system_metrics(request: Request):
    app = request.app
    metrics = getattr(app.state, "slo_metrics", {})
    result = {}
    for name, values in metrics.items():
        if not values:
            result[name] = {"count": 0}
            continue
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        result[name] = {
            "count": n,
            "p50": sorted_vals[int(n * 0.5)] if n > 0 else 0,
            "p95": sorted_vals[int(n * 0.95)] if n > 0 else 0,
            "p99": sorted_vals[int(n * 0.99)] if n > 0 else 0,
        }
    return result


# -- Models --

@router.get("/models")
async def v1_list_models(request: Request):
    mr: ModelRegistry = request.app.state.model_registry
    return mr.list_models()


@router.get("/models/health")
async def v1_models_health(request: Request):
    mr: ModelRegistry = request.app.state.model_registry
    models = mr.list_models()
    return {
        mid: {"status": info.get("status", "unknown")}
        for mid, info in models.items()
    }


# -- Tools --

@router.get("/tools")
async def v1_list_tools(request: Request):
    mcp: MCPGatewayClient = request.app.state.mcp_client
    return mcp.get_tools()


@router.get("/tools/catalog")
async def v1_tools_catalog(request: Request):
    mcp: MCPGatewayClient = request.app.state.mcp_client
    tools = mcp.get_tools()
    # Group by explicit server metadata when available, then fall back
    # to parsing known tool-id namespace separators.
    by_server: dict[str, list] = {}
    for t in tools:
        server_hint = ""
        if isinstance(t, dict):
            tool_id = str(t.get("id") or t.get("name") or "")
            server_hint = str(
                t.get("server")
                or t.get("source")
                or t.get("namespace")
                or ""
            )
        else:
            tool_id = str(t)
        if server_hint:
            prefix = server_hint
        elif "__" in tool_id:
            prefix = tool_id.split("__", 1)[0]
        elif ":" in tool_id:
            prefix = tool_id.split(":", 1)[0]
        elif "/" in tool_id:
            prefix = tool_id.split("/", 1)[0]
        else:
            prefix = "local"

        entry = dict(t) if isinstance(t, dict) else {"id": tool_id, "name": tool_id}
        entry["server"] = prefix
        by_server.setdefault(prefix, []).append(entry)
    for server_name in by_server:
        by_server[server_name].sort(key=lambda x: str(x.get("id") or x.get("name") or ""))
    return {"connected": mcp.connected, "servers": by_server}


# -- Suggest Team --

@router.post("/suggest-team")
async def v1_suggest_team(body: SuggestTeamRequest, request: Request):
    """Use the LLM to suggest an optimal team for a given task."""
    config_obj: FormicOSConfig = request.app.state.config

    # Build caste catalog for the prompt
    caste_lines = []
    for cname, cc in config_obj.castes.items():
        if cname == "manager":
            continue  # manager is always added automatically
        caste_lines.append(
            f"- {cname}: {cc.description or 'No description'} "
            f"(tools: {', '.join(cc.tools) or 'none'})"
        )
    caste_catalog = "\n".join(caste_lines)

    system_prompt = (
        "You are the FormicOS Supercolony Agent. Your job is to recommend "
        "the optimal team of AI agents for a given task.\n\n"
        "Available agent castes (manager is always included automatically):\n"
        f"{caste_catalog}\n\n"
        "Subcaste tiers control model size:\n"
        "- heavy: largest model, best quality, slowest\n"
        "- balanced: default, good quality/speed tradeoff\n"
        "- light: smallest model, fastest, for simple subtasks\n\n"
        "Respond with ONLY valid JSON, no markdown, no explanation:\n"
        '{"agents": [{"caste": "<name>", "subcaste_tier": "<tier>"}], '
        '"colony_name": "<short-kebab-name>", '
        '"max_rounds": <int 3-15>}'
    )

    user_prompt = f"Task: {body.task}"

    # Get LLM client from shared aiohttp session (v0.8.0)
    try:
        client = AioLLMClient(
            session=request.app.state.aio_session,
            base_url=config_obj.inference.endpoint,
        )
        model_string = config_obj.inference.model_alias or "gpt-4"
    except Exception as exc:
        return api_error_v1(
            503, "MODEL_ERROR", f"Cannot access LLM: {exc}"
        )

    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model_string,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=500,
            ),
            timeout=30,
        )
        raw = response.choices[0].message.content or "{}"

        # Parse response
        try:
            from json_repair import repair_json
            result = json.loads(repair_json(raw))
        except Exception:
            result = json.loads(raw)

        # Validate structure
        agents = result.get("agents", [])
        if not agents:
            agents = [
                {"caste": "architect", "subcaste_tier": "balanced"},
                {"caste": "coder", "subcaste_tier": "balanced"},
            ]

        return {
            "agents": agents,
            "colony_name": result.get(
                "colony_name",
                f"colony-{uuid.uuid4().hex[:6]}",
            ),
            "max_rounds": min(
                max(result.get("max_rounds", 5), 3), 15
            ),
        }

    except asyncio.TimeoutError:
        return api_error_v1(
            504, "LLM_TIMEOUT", "LLM did not respond in time"
        )
    except Exception as exc:
        logger.error("suggest-team LLM call failed: %s", exc)
        # Return sensible defaults on failure
        return {
            "agents": [
                {"caste": "architect", "subcaste_tier": "balanced"},
                {"caste": "coder", "subcaste_tier": "balanced"},
            ],
            "colony_name": f"colony-{uuid.uuid4().hex[:6]}",
            "max_rounds": 5,
        }
