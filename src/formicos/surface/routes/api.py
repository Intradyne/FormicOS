"""API routes — knowledge, diagnostics, suggest-team, templates, castes, playbooks, demo."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
import yaml
from starlette.responses import JSONResponse
from starlette.routing import Route

from formicos.core.settings import (
    CasteRecipeSet,
    save_castes,
    save_model_registry,
)
from formicos.core.types import CasteRecipe, ModelRecord
from formicos.engine.context import get_last_retrieval_timing
from formicos.surface.structured_error import KNOWN_ERRORS, to_http_error
from formicos.surface.template_manager import (
    ColonyTemplate,
    get_template,
    list_templates,
    load_all_templates,
    new_template_id,
    save_template,
)

if TYPE_CHECKING:
    from starlette.requests import Request

    from formicos.adapters.embedding_qwen3 import Qwen3Embedder
    from formicos.adapters.knowledge_graph import KnowledgeGraphAdapter
    from formicos.adapters.vector_qdrant import QdrantVectorPort
    from formicos.core.settings import SystemSettings
    from formicos.surface.runtime import Runtime
    from formicos.surface.ws_handler import WebSocketManager

log = structlog.get_logger()


def routes(
    *,
    runtime: Runtime,
    settings: SystemSettings,
    castes: CasteRecipeSet | None,
    castes_path: str | Path,
    config_path: str | Path,
    vector_store: QdrantVectorPort | None,
    kg_adapter: KnowledgeGraphAdapter | None,
    embed_client: Qwen3Embedder | None,
    skill_collection: str,
    ws_manager: WebSocketManager,
    **_unused: Any,
) -> list[Route]:
    """Build API routes for knowledge, diagnostics, templates, castes."""

    def _err_response(err_key: str, **overrides: Any) -> JSONResponse:
        err = KNOWN_ERRORS[err_key]
        if overrides:
            err = err.model_copy(update=overrides)
        status, body, headers = to_http_error(err)
        return JSONResponse(body, status_code=status, headers=headers)

    async def suggest_team(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return _err_response("INVALID_JSON")
        objective = body.get("objective", "")
        if not objective:
            return _err_response("MISSING_FIELD", message="objective is required")
        team = await runtime.suggest_team(objective)
        return JSONResponse({"objective": objective, "castes": team})

    async def preview_colony(request: Request) -> JSONResponse:
        """Return structured preview metadata without dispatching a colony.

        Reuses the same preview substrate as Queen tools (Wave 48).
        """
        from formicos.core.types import CasteSlot, SubcasteTier  # noqa: PLC0415
        from formicos.surface.queen_tools import build_colony_preview  # noqa: PLC0415

        try:
            body = await request.json()
        except Exception:
            return _err_response("INVALID_JSON")

        task = body.get("task", "")
        if not task:
            return _err_response("MISSING_FIELD", message="task is required")

        raw_castes = body.get("castes", [])
        if not isinstance(raw_castes, list) or not raw_castes:
            return _err_response(
                "MISSING_FIELD", message="castes must be a non-empty array",
            )

        try:
            caste_slots = [
                CasteSlot(
                    caste=c["caste"],
                    tier=SubcasteTier(c.get("tier", "standard")),
                    count=int(c.get("count", 1)),
                )
                for c in raw_castes
            ]
        except (KeyError, ValueError, TypeError) as exc:
            return _err_response(
                "MISSING_FIELD",
                message=f"invalid castes entry: {exc}",
            )

        strategy = body.get("strategy", "stigmergic")
        max_rounds = max(1, min(int(body.get("max_rounds", 10)), 50))
        budget_limit = max(0.0, float(body.get("budget_limit", 2.0)))
        fast_path = bool(body.get("fast_path", False))
        target_files = body.get("target_files", [])
        if not isinstance(target_files, list):
            target_files = []

        preview = build_colony_preview(
            task=task,
            caste_slots=caste_slots,
            strategy=strategy,
            max_rounds=max_rounds,
            budget_limit=budget_limit,
            fast_path=fast_path,
            target_files=target_files,
        )
        return JSONResponse(preview)

    # -- Template endpoints (ADR-016) --

    async def get_templates(request: Request) -> JSONResponse:
        templates = await list_templates()
        return JSONResponse(templates)

    async def create_template(request: Request) -> JSONResponse:
        try:
            body: dict[str, Any] = await request.json()
        except Exception:
            return _err_response("INVALID_JSON")
        name = body.get("name", "")
        if not name:
            return _err_response("MISSING_FIELD", message="name is required")
        raw_castes = body.get("castes", [])
        if not raw_castes:
            return _err_response("MISSING_FIELD", message="castes is required")
        from formicos.core.types import CasteSlot
        slots = [CasteSlot(**c) if isinstance(c, dict) else c for c in raw_castes]  # pyright: ignore[reportUnknownArgumentType]
        tmpl = ColonyTemplate(
            template_id=body.get("template_id", new_template_id()),
            name=name,
            description=body.get("description", ""),
            version=body.get("version", 1),
            castes=slots,
            strategy=body.get("strategy", "stigmergic"),
            budget_limit=body.get("budget_limit", body.get("budgetLimit", 1.0)),
            max_rounds=body.get("max_rounds", body.get("maxRounds", 25)),
            tags=body.get("tags", []),
            source_colony_id=body.get("source_colony_id", body.get("sourceColonyId")),
        )
        saved = await save_template(tmpl, runtime)
        return JSONResponse(saved.model_dump(), status_code=201)

    async def get_template_detail(request: Request) -> JSONResponse:
        template_id = request.path_params["template_id"]
        tmpl = await get_template(template_id)
        if tmpl is None:
            return _err_response("TEMPLATE_NOT_FOUND")
        return JSONResponse(tmpl.model_dump())

    # -- Workspace-scoped template listing (Wave 50) --

    async def get_workspace_templates(request: Request) -> JSONResponse:
        """Return operator + learned templates for a workspace."""
        proj = runtime.projections if runtime else None
        proj_templates = list(proj.templates.values()) if proj else []
        templates = await load_all_templates(
            projection_templates=proj_templates,
        )
        return JSONResponse({
            "templates": [t.model_dump() for t in templates],
        })

    # -- Caste recipe endpoints (Wave 16 Final Pass) --

    async def get_castes_api(_request: Request) -> JSONResponse:
        """Return all caste recipes as a dict."""
        if castes is None:
            return JSONResponse({})
        return JSONResponse({
            k: v.model_dump() for k, v in castes.castes.items()
        })

    async def upsert_caste(request: Request) -> JSONResponse:
        """Create or update a single caste recipe and save to YAML."""
        caste_id = request.path_params["caste_id"]
        try:
            body: dict[str, Any] = await request.json()
        except Exception:
            return _err_response("INVALID_JSON")
        try:
            recipe = CasteRecipe(**body)
        except Exception as exc:
            return _err_response("VALIDATION_FAILED", message=str(exc))
        if castes is None:
            return _err_response("NO_CASTES_LOADED")
        castes.castes[caste_id] = recipe
        save_castes(castes_path, castes)
        runtime.castes = castes
        ws_manager._castes = castes  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        log.info("caste.upserted", caste_id=caste_id)
        return JSONResponse(recipe.model_dump(), status_code=200)

    # -- Model registry edit endpoint --

    async def update_model_policy(request: Request) -> JSONResponse:
        """Update policy fields on a single model registry entry."""
        address = request.path_params["address"]
        try:
            body: dict[str, Any] = await request.json()
        except Exception:
            return _err_response("INVALID_JSON")

        target: ModelRecord | None = None
        for m in settings.models.registry:
            if m.address == address:
                target = m
                break
        if target is None:
            return _err_response("MODEL_NOT_FOUND",
                                 message=f"model '{address}' not found in registry")

        _EDITABLE = {
            "max_output_tokens", "time_multiplier", "tool_call_multiplier",
        }
        updates: dict[str, Any] = {
            k: v for k, v in body.items() if k in _EDITABLE
        }
        if not updates:
            return _err_response("MISSING_FIELD",
                                 message="no editable fields provided")

        try:
            trial = target.model_copy(update=updates)
            _ = trial
        except Exception as exc:
            return _err_response("VALIDATION_FAILED",
                                 message=f"validation failed: {exc}")

        idx = settings.models.registry.index(target)
        settings.models.registry[idx] = target.model_copy(update=updates)

        save_model_registry(config_path, settings)
        log.info("model_policy.updated", address=address, updates=updates)
        return JSONResponse(
            settings.models.registry[idx].model_dump(), status_code=200,
        )

    # -- Knowledge graph endpoint (Wave 13 C-T1, renamed Wave 27 C1) --

    async def get_knowledge_graph(request: Request) -> JSONResponse:
        workspace_id = request.query_params.get("workspace_id", "")
        empty: dict[str, Any] = {"nodes": [], "edges": [], "stats": {"nodes": 0, "edges": 0}}
        if kg_adapter is None:
            return JSONResponse(empty)
        try:
            db = await kg_adapter._ensure_db()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            if workspace_id:
                cur_n = await db.execute(
                    "SELECT id, name, entity_type, summary, source_colony, "
                    "workspace_id, created_at FROM kg_nodes WHERE workspace_id = ?",
                    [workspace_id],
                )
            else:
                cur_n = await db.execute(
                    "SELECT id, name, entity_type, summary, source_colony, "
                    "workspace_id, created_at FROM kg_nodes",
                )
            nodes = [dict(row) for row in await cur_n.fetchall()]  # pyright: ignore[reportUnknownArgumentType]
            if workspace_id:
                cur_e = await db.execute(
                    "SELECT id, from_node, to_node, predicate, confidence, "
                    "source_colony, source_round, created_at "
                    "FROM kg_edges WHERE workspace_id = ? AND invalid_at IS NULL",
                    [workspace_id],
                )
            else:
                cur_e = await db.execute(
                    "SELECT id, from_node, to_node, predicate, confidence, "
                    "source_colony, source_round, created_at "
                    "FROM kg_edges WHERE invalid_at IS NULL",
                )
            edges = [dict(row) for row in await cur_e.fetchall()]  # pyright: ignore[reportUnknownArgumentType]
            st = await kg_adapter.stats(workspace_id or None)
            return JSONResponse({"nodes": nodes, "edges": edges, "stats": st})
        except Exception:
            log.exception("knowledge_graph.route_error")
            return JSONResponse(empty)

    # -- Retrieval diagnostics endpoint (Wave 13 F3) --

    async def get_retrieval_diagnostics(_request: Request) -> JSONResponse:
        """Ephemeral operator diagnostics for the retrieval pipeline."""
        timing = get_last_retrieval_timing()

        skill_count = 0
        if vector_store is not None:
            try:
                count_result = await vector_store._client.count(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
                    collection_name=skill_collection,
                )
                skill_count = count_result.count
            except Exception:
                pass

        kg_stats: dict[str, int] = {"nodes": 0, "edges": 0}
        if kg_adapter is not None:
            try:
                kg_stats = await kg_adapter.stats()
            except Exception:
                log.debug("diagnostics.kg_stats_failed")

        return JSONResponse({
            "timing": {
                "graphMs": timing.get("graph_ms", 0.0),
                "vectorMs": timing.get("vector_ms", 0.0),
                "totalMs": timing.get("total_ms", 0.0),
            },
            "counts": {
                "skillBankSize": skill_count,
                "kgEntities": kg_stats.get("nodes", 0),
                "kgEdges": kg_stats.get("edges", 0),
            },
            "embedding": {
                "model": settings.embedding.model,
                "dimensions": settings.embedding.dimensions,
            },
            "searchMode": "hybrid dense+BM25+graph" if embed_client else "dense",
        })

    # -- Wave 34 B2: proactive intelligence briefing --

    async def get_briefing(request: Request) -> JSONResponse:
        workspace_id = request.path_params["workspace_id"]
        from formicos.surface.proactive_intelligence import (
            generate_briefing as _gen,  # noqa: PLC0415
        )
        briefing = _gen(workspace_id, runtime.projections)
        return JSONResponse(briefing.model_dump())

    # -- Wave 39 5A: configuration recommendations --

    async def get_config_recommendations(request: Request) -> JSONResponse:
        workspace_id = request.path_params["workspace_id"]
        from dataclasses import asdict  # noqa: PLC0415

        from formicos.surface.proactive_intelligence import (
            generate_config_recommendations as _gen_config,  # noqa: PLC0415
        )
        recs = _gen_config(workspace_id, runtime.projections)
        return JSONResponse({"recommendations": [asdict(r) for r in recs]})

    # -- Wave 39 5B/5C: config override history --
    # NOTE: POST also exists at /api/v1/knowledge/config-override (knowledge_api.py)
    # with canonical field names. This route accepts both short (dimension/original/
    # overridden) and canonical names for backwards compatibility with the frontend.
    # Both emit the same ConfigSuggestionOverridden event. Intentional dual path.

    async def get_config_overrides(request: Request) -> JSONResponse:
        workspace_id = request.path_params["workspace_id"]
        from dataclasses import asdict  # noqa: PLC0415
        overrides = runtime.projections.operator_overlays.config_overrides.get(
            workspace_id, [],
        )
        return JSONResponse({
            "overrides": [asdict(o) for o in overrides],
        })

    # -- Wave 39 5B: record a config suggestion override --

    async def post_config_override(request: Request) -> JSONResponse:
        workspace_id = request.path_params["workspace_id"]
        from datetime import UTC, datetime  # noqa: PLC0415

        from formicos.core.events import ConfigSuggestionOverridden  # noqa: PLC0415

        body = await request.json()
        category = body.get("dimension", body.get("suggestion_category", ""))
        original = body.get("original", body.get("original_config", {}))
        overridden = body.get("overridden", body.get("overridden_config", {}))
        reason = body.get("reason", "")
        actor = body.get("actor", "operator")

        await runtime.emit_and_broadcast(ConfigSuggestionOverridden(
            seq=0,
            timestamp=datetime.now(tz=UTC),
            address=workspace_id,
            workspace_id=workspace_id,
            suggestion_category=category,
            original_config=original,
            overridden_config=overridden,
            reason=reason,
            actor=actor,
        ))
        return JSONResponse({"status": "recorded", "workspace_id": workspace_id})

    # -- Wave 39 4B: dismiss autonomy recommendation --
    # INTENTIONALLY EPHEMERAL (Wave 51): dismissals are runtime-only and do
    # not survive restart. Autonomy recommendations regenerate on each
    # briefing cycle, so persisting dismissals would create stale state
    # that outlives the recommendation it dismissed. Operators can re-dismiss
    # after restart if the same recommendation reappears.

    async def post_dismiss_autonomy(request: Request) -> JSONResponse:
        from datetime import UTC, datetime  # noqa: PLC0415
        body = await request.json()
        category = body.get("category", "")
        if category:
            runtime.projections.autonomy_recommendation_dismissals[category] = (
                datetime.now(tz=UTC).isoformat()
            )
        return JSONResponse({"status": "dismissed", "category": category, "ephemeral": True})

    # -- Wave 36 A2: workspace colony outcomes --

    async def get_workspace_outcomes(request: Request) -> JSONResponse:
        workspace_id = request.path_params["workspace_id"]
        period = request.query_params.get("period", "24h")
        from dataclasses import asdict  # noqa: PLC0415

        outcomes = runtime.projections.colony_outcomes
        hours_by_period = {
            "24h": 24,
            "7d": 24 * 7,
            "30d": 24 * 30,
        }
        normalized_period = period if period in hours_by_period else "24h"
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=hours_by_period[normalized_period])  # noqa: UP017

        ws_outcomes: list[Any] = []
        for outcome in outcomes.values():
            if outcome.workspace_id != workspace_id:
                continue
            colony = runtime.projections.colonies.get(outcome.colony_id)
            if colony is None or not colony.completed_at:
                continue
            try:
                completed_at = datetime.fromisoformat(colony.completed_at)
            except ValueError:
                continue
            if completed_at >= cutoff:
                ws_outcomes.append((outcome, completed_at))

        total = len(ws_outcomes)
        succeeded = sum(1 for o, _ in ws_outcomes if o.succeeded)
        total_cost = sum(o.total_cost for o, _ in ws_outcomes)
        total_extracted = sum(o.entries_extracted for o, _ in ws_outcomes)
        total_accessed = sum(o.entries_accessed for o, _ in ws_outcomes)
        avg_quality = (
            sum(o.quality_score for o, _ in ws_outcomes if o.quality_score > 0)
            / max(1, sum(1 for o, _ in ws_outcomes if o.quality_score > 0))
        )
        maintenance_spend = sum(
            o.total_cost for o, _ in ws_outcomes if o.maintenance_source
        )

        recent = sorted(
            ws_outcomes,
            key=lambda pair: pair[1],
            reverse=True,
        )[:20]

        return JSONResponse({
            "workspace_id": workspace_id,
            "period": normalized_period,
            "summary": {
                "total_colonies": total,
                "succeeded": succeeded,
                "failed": total - succeeded,
                "total_cost": round(total_cost, 4),
                "total_extracted": total_extracted,
                "total_accessed": total_accessed,
                "avg_quality": round(avg_quality, 3),
                "maintenance_spend": round(maintenance_spend, 4),
            },
            "outcomes": [asdict(o) for o, _ in recent],
        })

    # -- Wave 38 2B: escalation outcome matrix --

    async def get_escalation_matrix(request: Request) -> JSONResponse:
        """Report escalation outcomes derived from routing_override and colony outcomes.

        Reads from governance-owned routing_override truth. Provider fallback
        is explicitly excluded — only capability escalation is reported.
        """
        workspace_id = request.path_params["workspace_id"]
        outcomes = runtime.projections.colony_outcomes
        escalated: list[dict[str, Any]] = []
        non_escalated_count = 0

        for outcome in outcomes.values():
            if outcome.workspace_id != workspace_id:
                continue
            if outcome.escalated:
                colony = runtime.projections.colonies.get(outcome.colony_id)
                row: dict[str, Any] = {
                    "colony_id": outcome.colony_id,
                    "thread_id": outcome.thread_id,
                    "task_family": outcome.strategy,
                    "starting_tier": outcome.starting_tier,
                    "escalated_tier": outcome.escalated_tier,
                    "reason": outcome.escalation_reason,
                    "round_at_override": outcome.escalation_round,
                    "total_rounds": outcome.total_rounds,
                    "total_cost": round(outcome.total_cost, 6),
                    "pre_escalation_cost": round(outcome.pre_escalation_cost, 6),
                    "post_escalation_cost": round(
                        outcome.total_cost - outcome.pre_escalation_cost, 6,
                    ),
                    "duration_ms": outcome.duration_ms,
                    "quality_score": outcome.quality_score,
                    "succeeded": outcome.succeeded,
                    "caste_composition": outcome.caste_composition,
                    "display_name": colony.display_name if colony else None,
                }
                escalated.append(row)
            else:
                non_escalated_count += 1

        # Summary statistics
        total_escalated = len(escalated)
        escalated_succeeded = sum(1 for e in escalated if e["succeeded"])
        avg_quality_escalated = (
            sum(e["quality_score"] for e in escalated) / total_escalated
            if total_escalated else 0.0
        )
        total_escalation_cost = sum(e["total_cost"] for e in escalated)

        return JSONResponse({
            "workspace_id": workspace_id,
            "summary": {
                "total_escalated": total_escalated,
                "total_non_escalated": non_escalated_count,
                "escalated_success_rate": (
                    escalated_succeeded / total_escalated
                    if total_escalated else 0.0
                ),
                "avg_quality_escalated": round(avg_quality_escalated, 3),
                "total_escalation_cost": round(total_escalation_cost, 6),
            },
            "escalations": escalated,
        })

    # -- Wave 36 B1: demo workspace creation --

    async def create_demo_workspace(_request: Request) -> JSONResponse:
        """Create a demo workspace from the seeded template."""
        from uuid import uuid4  # noqa: PLC0415

        from formicos.core.events import (  # noqa: PLC0415
            MemoryEntryCreated,
            WorkspaceConfigChanged,
        )

        template_path = (
            Path(__file__).resolve().parents[4]
            / "config" / "templates" / "demo-workspace.yaml"
        )
        if not template_path.exists():
            return _err_response(
                "TEMPLATE_NOT_FOUND",
                message="demo-workspace.yaml template not found",
            )
        raw = yaml.safe_load(template_path.read_text(encoding="utf-8"))

        ws_name = raw.get("workspace_name", "FormicOS Demo")
        ws_id = await runtime.create_workspace(ws_name)

        # Apply maintenance policy via WorkspaceConfigChanged event
        policy = raw.get("maintenance_policy")
        if policy:
            await runtime.emit_and_broadcast(WorkspaceConfigChanged(
                seq=0,
                timestamp=datetime.now(tz=timezone.utc),  # noqa: UP017
                address=ws_id,
                workspace_id=ws_id,
                field="maintenance_policy",
                old_value=None,
                new_value=json.dumps(policy),
            ))

        # Seed knowledge entries
        seeded_entries = raw.get("seeded_entries", [])
        entry_count = 0
        for entry_def in seeded_entries:
            entry_id = entry_def.get("entry_id", f"demo-{uuid4().hex[:8]}")
            conf = entry_def.get("confidence", {})
            entry_dict: dict[str, Any] = {
                "id": entry_id,
                "category": entry_def.get("category", "skill"),
                "sub_type": entry_def.get("sub_type", "technique"),
                "title": entry_def.get("title", ""),
                "content": entry_def.get("content", ""),
                "domains": entry_def.get("domains", []),
                "decay_class": entry_def.get("decay_class", "ephemeral"),
                "status": entry_def.get("status", "observed"),
                "alpha": conf.get("alpha", 5.0),
                "beta": conf.get("beta", 2.0),
                "workspace_id": ws_id,
                "source_colony_id": "demo-seed",
                "source_round": 0,
                "created_at": datetime.now(tz=timezone.utc).isoformat(),  # noqa: UP017
            }
            await runtime.emit_and_broadcast(MemoryEntryCreated(
                seq=0,
                timestamp=datetime.now(tz=timezone.utc),  # noqa: UP017
                address=ws_id,
                entry=entry_dict,
                workspace_id=ws_id,
            ))
            entry_count += 1

        log.info(
            "demo_workspace.created",
            workspace_id=ws_id,
            entries_seeded=entry_count,
        )
        return JSONResponse({
            "workspace_id": ws_id,
            "workspace_name": ws_name,
            "entries_seeded": entry_count,
            "suggested_task": raw.get("suggested_demo_task", ""),
        }, status_code=201)

    # -- Wave 39 1A: colony audit view --

    # -- Wave 48 1A: thread-scoped timeline --

    async def get_thread_timeline(request: Request) -> JSONResponse:
        """Return chronological thread-scoped timeline (read-model, replay-safe)."""
        from formicos.surface.projections import build_thread_timeline

        workspace_id = request.path_params["workspace_id"]
        thread_id = request.path_params["thread_id"]
        try:
            limit = max(1, min(int(request.query_params.get("limit", "50")), 200))
        except ValueError:
            limit = 50

        ws = runtime.projections.workspaces.get(workspace_id)
        if ws is None:
            return _err_response("WORKSPACE_NOT_FOUND")
        if thread_id not in ws.threads:
            return _err_response("THREAD_NOT_FOUND")

        timeline = build_thread_timeline(
            runtime.projections, workspace_id, thread_id, limit=limit,
        )
        return JSONResponse({
            "workspace_id": workspace_id,
            "thread_id": thread_id,
            "entries": timeline,
            "count": len(timeline),
        })

    async def get_colony_audit(request: Request) -> JSONResponse:
        """Return structured audit view for a colony (read-model, replay-safe)."""
        from formicos.surface.projections import build_colony_audit_view

        colony_id = request.path_params["colony_id"]
        colony = runtime.projections.get_colony(colony_id)
        if colony is None:
            return _err_response("COLONY_NOT_FOUND")
        audit = build_colony_audit_view(colony, store=runtime.projections)
        return JSONResponse(audit)

    # -- Wave 46: Forager operator surface --

    async def post_forage_trigger(request: Request) -> JSONResponse:
        """Trigger a manual bounded forage cycle for a workspace."""
        workspace_id = request.path_params["workspace_id"]
        forager_svc = getattr(runtime, "forager_service", None)
        if forager_svc is None:
            return _err_response(
                "SERVICE_NOT_READY", message="Forager service not available",
            )
        try:
            body = await request.json()
        except Exception:
            return _err_response("INVALID_JSON")

        topic = body.get("topic", "")
        if not topic:
            return _err_response("MISSING_FIELD", message="topic is required")

        signal = {
            "workspace_id": workspace_id,
            "trigger": "operator",
            "gap_description": body.get("gap_description", topic),
            "topic": topic,
            "domains": body.get("domains", []),
            "max_results": min(int(body.get("max_results", 5)), 20),
        }
        import asyncio as _asyncio  # noqa: PLC0415

        _asyncio.create_task(forager_svc.handle_forage_signal(signal))
        return JSONResponse({
            "ok": True,
            "workspace_id": workspace_id,
            "topic": topic,
            "status": "dispatched",
        }, status_code=202)

    async def post_domain_override(request: Request) -> JSONResponse:
        """Record an operator domain trust/distrust/reset override."""
        workspace_id = request.path_params["workspace_id"]
        try:
            body = await request.json()
        except Exception:
            return _err_response("INVALID_JSON")

        domain = body.get("domain", "")
        action = body.get("action", "")
        if not domain or action not in ("trust", "distrust", "reset"):
            return _err_response(
                "MISSING_FIELD",
                message="domain and action (trust|distrust|reset) are required",
            )

        actor = body.get("actor", "operator")
        reason = body.get("reason", "")

        from formicos.core.events import ForagerDomainOverride  # noqa: PLC0415

        await runtime.emit_and_broadcast(ForagerDomainOverride(
            seq=0,
            timestamp=datetime.now(tz=timezone.utc),  # noqa: UP017
            address=workspace_id,
            workspace_id=workspace_id,
            domain=domain,
            action=action,
            actor=actor,
            reason=reason,
        ))

        # Apply to live domain policy if forager service is present
        forager_svc = getattr(runtime, "forager_service", None)
        if forager_svc is not None:
            dp = getattr(forager_svc._orchestrator, "_domain_policy", None)  # noqa: SLF001
            if dp is not None:
                getattr(dp, action)(domain)

        return JSONResponse({
            "ok": True,
            "workspace_id": workspace_id,
            "domain": domain,
            "action": action,
        })

    async def get_forage_cycles(request: Request) -> JSONResponse:
        """Return forage cycle history for a workspace."""
        workspace_id = request.path_params["workspace_id"]
        cycles = runtime.projections.forage_cycles.get(workspace_id, [])
        try:
            limit = max(1, min(int(request.query_params.get("limit", "50")), 200))
        except ValueError:
            limit = 50
        # Most recent first
        recent = list(reversed(cycles))[:limit]
        from dataclasses import asdict as _asdict  # noqa: PLC0415

        return JSONResponse({
            "workspace_id": workspace_id,
            "cycles": [_asdict(c) for c in recent],
            "total": len(cycles),
        })

    async def get_domain_strategies(request: Request) -> JSONResponse:
        """Return domain fetch strategies and operator overrides for a workspace."""
        workspace_id = request.path_params["workspace_id"]
        strategies = runtime.projections.domain_strategies.get(workspace_id, {})
        overrides = runtime.projections.domain_overrides.get(workspace_id, {})
        from dataclasses import asdict as _asdict  # noqa: PLC0415

        return JSONResponse({
            "workspace_id": workspace_id,
            "strategies": {
                domain: _asdict(strat)
                for domain, strat in strategies.items()
            },
            "overrides": {
                domain: _asdict(ovr)
                for domain, ovr in overrides.items()
            },
        })

    # --- Wave 55 Team 2: learning summary ---

    async def get_learning_summary(request: Request) -> JSONResponse:
        """Return compact learning loop summary for the workspace."""
        workspace_id = request.path_params["workspace_id"]
        proj = runtime.projections

        # Template counts from projection store
        all_templates = list(proj.templates.values())
        learned = [t for t in all_templates if getattr(t, "learned", False)]
        top_template: dict[str, Any] | None = None
        if learned:
            best = max(learned, key=lambda t: getattr(t, "use_count", 0))
            top_template = {
                "id": best.id,
                "name": best.name,
                "use_count": getattr(best, "use_count", 0),
            }

        # Knowledge entry count for this workspace
        ws_entries = [
            e for e in proj.memory_entries.values()
            if e.get("workspace_id") == workspace_id
        ]
        entry_count = len(ws_entries)

        # Recent quality trend: avg quality from last N completed outcomes
        ws_outcomes = [
            o for o in proj.colony_outcomes.values()
            if o.workspace_id == workspace_id and o.quality_score > 0
        ]
        ws_outcomes_sorted = sorted(
            ws_outcomes,
            key=lambda o: getattr(
                proj.colonies.get(o.colony_id), "completed_at", "",
            ) or "",
            reverse=True,
        )
        recent = ws_outcomes_sorted[:10]
        quality_trend: list[float] = [o.quality_score for o in recent]

        return JSONResponse({
            "workspace_id": workspace_id,
            "learned_template_count": len(learned),
            "total_template_count": len(all_templates),
            "top_template": top_template,
            "knowledge_entry_count": entry_count,
            "quality_trend": quality_trend,
        })

    # --- Wave 60 B1: Knowledge entry relationships ---

    async def get_entry_relationships(request: Request) -> JSONResponse:
        """Return graph relationships for a knowledge entry."""
        entry_id = request.path_params["entry_id"]
        kg_node_id = runtime.projections.entry_kg_nodes.get(entry_id, "")
        if not kg_node_id or kg_adapter is None:
            return JSONResponse({"relationships": [], "entry_id": entry_id})

        ws_id = runtime.projections.memory_entries.get(
            entry_id, {},
        ).get("workspace_id", "")
        try:
            neighbors = await kg_adapter.get_neighbors(
                kg_node_id, workspace_id=ws_id or None,
            )
        except Exception:
            log.exception("entry_relationships.get_neighbors_failed", entry_id=entry_id)
            return JSONResponse({"relationships": [], "entry_id": entry_id})

        # Build reverse index: kg node → entry id
        node_to_entry = {
            nid: eid for eid, nid in runtime.projections.entry_kg_nodes.items()
        }

        relationships: list[dict[str, Any]] = []
        for nbr in neighbors:
            # Determine which end is the neighbor (not the seed)
            other_node = (
                nbr.get("to_node") if nbr.get("from_node") == kg_node_id
                else nbr.get("from_node")
            )
            other_eid = node_to_entry.get(other_node or "", "")
            if other_eid:
                relationships.append({
                    "entry_id": other_eid,
                    "predicate": nbr.get("predicate", "RELATED_TO"),
                    "confidence": nbr.get("confidence", 0.0),
                    "title": runtime.projections.memory_entries.get(
                        other_eid, {},
                    ).get("title", ""),
                })

        return JSONResponse({"relationships": relationships, "entry_id": entry_id})

    # --- Wave 60 B2: Operator knowledge feedback ---

    async def submit_entry_feedback(request: Request) -> JSONResponse:
        """Record operator thumbs-up/down on a knowledge entry."""
        from formicos.core.events import MemoryConfidenceUpdated  # noqa: PLC0415

        entry_id = request.path_params["entry_id"]
        entry = runtime.projections.memory_entries.get(entry_id)
        if entry is None:
            return _err_response(
                "KNOWLEDGE_ITEM_NOT_FOUND",
                message=f"Entry {entry_id} not found",
            )

        try:
            body = await request.json()
        except Exception:
            return _err_response("INVALID_JSON")
        is_positive = body.get("positive", True)

        old_alpha = float(entry.get("conf_alpha", 5.0))  # default prior Beta(5,5)
        old_beta = float(entry.get("conf_beta", 5.0))
        # ±1.0 per click — matches colony outcome weight
        delta = 1.0
        new_alpha = old_alpha + (delta if is_positive else 0.0)
        new_beta = old_beta + (0.0 if is_positive else delta)

        ws_id = entry.get("workspace_id", "")
        await runtime.emit_and_broadcast(MemoryConfidenceUpdated(
            seq=0,
            timestamp=datetime.now(UTC),
            address=f"{ws_id}/feedback",
            entry_id=entry_id,
            old_alpha=old_alpha,
            old_beta=old_beta,
            new_alpha=new_alpha,
            new_beta=new_beta,
            new_confidence=new_alpha / (new_alpha + new_beta),
            workspace_id=ws_id,
            reason="operator_feedback",
        ))

        return JSONResponse({
            "entry_id": entry_id,
            "feedback": "positive" if is_positive else "negative",
            "new_confidence": round(new_alpha / (new_alpha + new_beta), 4),
        })

    # --- Playbook listing (Wave 55, Team 3) ---

    async def get_playbooks(_request: Request) -> JSONResponse:
        """Return all operational playbooks for read-only display."""
        from formicos.engine.playbook_loader import load_all_playbooks  # noqa: PLC0415

        playbooks = load_all_playbooks()
        return JSONResponse({"playbooks": playbooks})

    return [
        Route("/api/v1/knowledge-graph", get_knowledge_graph),
        # Wave 60: entry relationships + operator feedback
        Route(
            "/api/v1/knowledge/{entry_id:str}/relationships",
            get_entry_relationships, methods=["GET"],
        ),
        Route(
            "/api/v1/knowledge/{entry_id:str}/feedback",
            submit_entry_feedback, methods=["POST"],
        ),
        Route("/api/v1/retrieval-diagnostics", get_retrieval_diagnostics),
        Route("/api/v1/suggest-team", suggest_team, methods=["POST"]),
        Route("/api/v1/preview-colony", preview_colony, methods=["POST"]),
        Route("/api/v1/templates", get_templates, methods=["GET"]),
        Route("/api/v1/templates", create_template, methods=["POST"]),
        Route("/api/v1/templates/{template_id:str}", get_template_detail),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/templates",
            get_workspace_templates, methods=["GET"],
        ),
        Route("/api/v1/playbooks", get_playbooks, methods=["GET"]),
        Route("/api/v1/castes", get_castes_api, methods=["GET"]),
        Route("/api/v1/castes/{caste_id:str}", upsert_caste, methods=["PUT"]),
        Route("/api/v1/models/{address:path}", update_model_policy, methods=["PATCH"]),
        Route("/api/v1/workspaces/{workspace_id:str}/briefing", get_briefing),
        Route("/api/v1/workspaces/{workspace_id:str}/outcomes", get_workspace_outcomes),
        Route("/api/v1/workspaces/{workspace_id:str}/escalation-matrix", get_escalation_matrix),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/config-recommendations",
            get_config_recommendations,
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/config-overrides",
            get_config_overrides, methods=["GET"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/config-overrides",
            post_config_override, methods=["POST"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/dismiss-autonomy",
            post_dismiss_autonomy, methods=["POST"],
        ),
        Route("/api/v1/workspaces/create-demo", create_demo_workspace, methods=["POST"]),
        # Wave 55: learning summary
        Route(
            "/api/v1/workspaces/{workspace_id:str}/learning-summary",
            get_learning_summary, methods=["GET"],
        ),
        Route("/api/v1/colonies/{colony_id:str}/audit", get_colony_audit),
        # Wave 48: thread-scoped timeline
        Route(
            "/api/v1/workspaces/{workspace_id:str}/threads/{thread_id:str}/timeline",
            get_thread_timeline, methods=["GET"],
        ),
        # Wave 46: Forager operator surface
        Route(
            "/api/v1/workspaces/{workspace_id:str}/forager/trigger",
            post_forage_trigger, methods=["POST"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/forager/domain-override",
            post_domain_override, methods=["POST"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/forager/cycles",
            get_forage_cycles, methods=["GET"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/forager/domains",
            get_domain_strategies, methods=["GET"],
        ),
    ]
