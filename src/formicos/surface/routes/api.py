"""API routes — knowledge, diagnostics, suggest-team, templates, castes, playbooks, demo."""

from __future__ import annotations

import contextlib
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
            "hidden",
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

    # -- Wave 67: knowledge hierarchy tree --

    async def get_knowledge_tree(request: Request) -> JSONResponse:
        """Return knowledge entry hierarchy as a tree grouped by domain."""
        workspace_id = request.path_params["workspace_id"]
        from formicos.surface.hierarchy import build_knowledge_tree  # noqa: PLC0415

        branches = build_knowledge_tree(runtime.projections, workspace_id)
        return JSONResponse({"branches": branches})

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

    # -- Wave 73 B3: workspace creation --

    async def create_workspace_endpoint(request: Request) -> JSONResponse:
        """Create a new workspace."""
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return _err_response("INVALID_JSON")

        name = body.get("name", "").strip()
        if not name:
            return _err_response(
                "INVALID_PARAMETER",
                message="Workspace name is required",
                status_code=400,
            )

        if name in runtime.projections.workspaces:
            return _err_response(
                "INVALID_PARAMETER",
                message=f"Workspace '{name}' already exists",
                status_code=409,
            )

        workspace_id = await runtime.create_workspace(name)
        return JSONResponse(
            {"workspace_id": workspace_id, "name": name},
            status_code=201,
        )

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

    # --- Wave 61 Track 5: workspace budget control panel ---

    async def get_workspace_budget(request: Request) -> JSONResponse:
        """Return detailed budget snapshot for a workspace."""
        workspace_id = request.path_params["workspace_id"]
        ws = runtime.projections.workspaces.get(workspace_id)
        if ws is None:
            return _err_response("WORKSPACE_NOT_FOUND")

        budget = ws.budget
        limit = ws.budget_limit
        utilization_pct = (
            round(budget.total_cost / limit * 100, 2) if limit > 0 else 0.0
        )

        colony_list: list[dict[str, Any]] = []
        for colony in runtime.projections.workspace_colonies(workspace_id):
            colony_list.append({
                "colony_id": colony.id,
                "name": colony.display_name or colony.id[:12],
                "status": colony.status,
                "cost": round(colony.budget_truth.total_cost, 6),
                "rounds": colony.round_number,
            })

        return JSONResponse({
            "workspace_id": workspace_id,
            "total_cost": round(budget.total_cost, 6),
            "budget_limit": limit,
            "utilization_pct": utilization_pct,
            "total_input_tokens": budget.total_input_tokens,
            "total_output_tokens": budget.total_output_tokens,
            "total_reasoning_tokens": budget.total_reasoning_tokens,
            "total_cache_read_tokens": budget.total_cache_read_tokens,
            "model_usage": dict(budget.model_usage),
            "colonies": colony_list,
        })

    # --- Wave 74 B3 / Wave 77.5 A3: Queen context budget endpoint ---

    async def get_queen_budget(request: Request) -> JSONResponse:
        """Return the Queen's 9-slot context budget with allocation and consumption."""
        from formicos.surface.queen_budget import (  # noqa: PLC0415
            _FALLBACKS,
            _FRACTIONS,
            compute_queen_budget,
        )

        workspace_id = request.query_params.get("workspace_id", "")
        ctx_window: int | None = None
        output_reserve = 4096
        num_slots = 1
        queen_model = ""

        queen_rt = runtime.queen
        if queen_rt:
            queen_model = queen_rt._resolve_queen_model(workspace_id) or ""
            output_reserve = queen_rt._queen_max_tokens(workspace_id)
            for rec in runtime.settings.models.registry:
                if rec.address == queen_model:
                    ctx_window = rec.context_window
                    break
            # Shared-pool KV: each slot has full context_window (hybrid arch).
            # Wave 81 TODO: read actual n_ctx from /slots endpoint at startup.

        budget = compute_queen_budget(
            ctx_window, output_reserve, num_slots=num_slots,
        )

        effective_per_slot = 0
        if ctx_window and ctx_window > 0:
            per_slot = ctx_window // max(1, num_slots) if num_slots > 1 else ctx_window
            effective_per_slot = max(0, per_slot - output_reserve)

        slot_list = []
        for name, frac in _FRACTIONS.items():
            allocated = getattr(budget, name, 0)
            consumed = 0
            if queen_rt and hasattr(queen_rt, "_last_budget_usage_by_workspace"):
                ws_usage = queen_rt._last_budget_usage_by_workspace.get(
                    workspace_id, {},
                )
                consumed = ws_usage.get("slots", {}).get(name, 0)
            slot_list.append({
                "name": name,
                "fraction": frac,
                "fallback_tokens": _FALLBACKS.get(name, 0),
                "allocated": allocated,
                "consumed": consumed,
                "utilization": round(consumed / allocated, 3) if allocated > 0 else 0,
            })

        total_consumed = sum(s["consumed"] for s in slot_list)

        return JSONResponse({
            "queen_model": queen_model,
            "queen_model_type": "local" if queen_model.startswith("llama-cpp/") else "cloud",
            "context_window": ctx_window or 0,
            "num_slots": num_slots,
            "effective_context": (
                ctx_window // max(1, num_slots)
                if ctx_window and num_slots > 1
                else ctx_window or 0
            ),
            "output_reserve": output_reserve,
            "available": effective_per_slot,
            "slots": slot_list,
            "total_consumed": total_consumed,
            "total_utilization": (
                round(total_consumed / effective_per_slot, 3)
                if effective_per_slot > 0
                else 0
            ),
        })

    # --- Wave 74 Track 4: Queen tool stats endpoint ---

    async def get_queen_tool_stats(request: Request) -> JSONResponse:
        """Return session-scoped Queen tool call counts."""
        runtime = request.app.state.runtime
        queen = runtime.queen
        counts: dict[str, int] = getattr(queen, "_tool_call_counts", {})
        statuses: dict[str, str] = getattr(queen, "_tool_last_status", {})
        tools = [
            {"name": name, "calls": count, "last_status": statuses.get(name, "unknown")}
            for name, count in sorted(counts.items(), key=lambda x: -x[1])
        ]
        return JSONResponse({"tools": tools, "total_calls": sum(counts.values())})

    # --- Wave 70.0 Track 9: autonomy status endpoint ---

    async def get_autonomy_status(request: Request) -> JSONResponse:
        """Return structured autonomy trust data for a workspace."""
        import json as _json  # noqa: PLC0415

        from formicos.core.types import MaintenancePolicy  # noqa: PLC0415
        from formicos.surface.self_maintenance import (  # noqa: PLC0415
            compute_autonomy_score,
        )

        workspace_id = request.path_params["workspace_id"]
        ws = runtime.projections.workspaces.get(workspace_id)
        if ws is None:
            return _err_response("WORKSPACE_NOT_FOUND")

        raw_policy = ws.config.get("maintenance_policy")
        policy = MaintenancePolicy()
        if raw_policy is not None:
            try:
                data = _json.loads(raw_policy) if isinstance(raw_policy, str) else raw_policy
                policy = MaintenancePolicy(**data)
            except Exception:  # noqa: BLE001
                pass

        dispatcher = getattr(runtime, "maintenance_dispatcher", None)
        daily_spend = 0.0
        active_maintenance = 0
        if dispatcher is not None:
            dispatcher._reset_daily_budget_if_needed()  # pyright: ignore[reportPrivateUsage]
            daily_spend = dispatcher._daily_spend.get(workspace_id, 0.0)  # pyright: ignore[reportPrivateUsage]
            active_maintenance = dispatcher._count_active_maintenance_colonies(  # pyright: ignore[reportPrivateUsage]
                workspace_id,
            )

        budget_limit = policy.daily_maintenance_budget
        remaining = max(0.0, budget_limit - daily_spend)

        auto_score = compute_autonomy_score(workspace_id, runtime.projections)

        # Build recent actions from colony outcomes
        recent_actions: list[dict[str, Any]] = []
        outcomes = sorted(
            (
                o for o in runtime.projections.colony_outcomes.values()
                if o.workspace_id == workspace_id
            ),
            key=lambda o: getattr(o, "colony_id", ""),
            reverse=True,
        )
        for o in outcomes[:10]:
            recent_actions.append({
                "colony_id": o.colony_id,
                "strategy": o.strategy,
                "outcome": "completed" if o.succeeded else "failed",
                "cost": round(o.total_cost, 4),
                "quality_score": round(o.quality_score, 2),
            })

        return JSONResponse({
            "level": str(policy.autonomy_level),
            "score": auto_score.score,
            "grade": auto_score.grade,
            "daily_budget": budget_limit,
            "daily_spend": round(daily_spend, 4),
            "remaining": round(remaining, 4),
            "active_maintenance_colonies": active_maintenance,
            "max_maintenance_colonies": policy.max_maintenance_colonies,
            "auto_actions": policy.auto_actions,
            "components": auto_score.components,
            "recommendation": auto_score.recommendation,
            "recent_actions": recent_actions,
        })

    # --- Wave 64 Track 5: provider health endpoint ---

    async def get_provider_health(_request: Request) -> JSONResponse:
        """Return per-provider health status and model availability."""
        health = runtime.llm_router.provider_health()
        # Build per-provider summary from model registry
        providers: dict[str, dict[str, Any]] = {}
        for rec in runtime.settings.models.registry:
            key = rec.provider
            if key not in providers:
                providers[key] = {
                    "status": health.get(
                        f"{key}:{rec.endpoint or 'default'}", "ok"
                    ),
                    "models": [],
                    "endpoint": rec.endpoint,
                }
            providers[key]["models"].append({
                "address": rec.address,
                "status": rec.status,
                "max_concurrent": rec.max_concurrent,
            })
        return JSONResponse({"providers": providers})

    # --- Playbook listing (Wave 55, Team 3) ---

    async def get_playbooks(_request: Request) -> JSONResponse:
        """Return all operational playbooks for read-only display."""
        from formicos.engine.playbook_loader import load_all_playbooks  # noqa: PLC0415

        playbooks = load_all_playbooks()
        return JSONResponse({"playbooks": playbooks})

    # Wave 78 Track 4: Playbook write/delete/approve
    async def create_playbook(request: Request) -> JSONResponse:
        """Save a new playbook from POST body."""
        from formicos.engine.playbook_loader import save_playbook  # noqa: PLC0415

        try:
            body: dict[str, Any] = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)
        result = save_playbook(body)
        if not result:
            return JSONResponse({"error": "Save refused"}, status_code=409)
        return JSONResponse({"ok": True, "playbook": result})

    async def delete_playbook_route(request: Request) -> JSONResponse:
        """Delete an auto-generated playbook by filename."""
        from formicos.engine.playbook_loader import (  # noqa: PLC0415
            delete_playbook,
        )

        filename = request.path_params.get("filename", "")
        if not filename:
            return JSONResponse({"error": "filename required"}, status_code=400)
        deleted = delete_playbook(filename)
        if not deleted:
            return JSONResponse({"error": "Not found or protected"}, status_code=404)
        return JSONResponse({"ok": True})

    async def approve_playbook_route(request: Request) -> JSONResponse:
        """Mark a candidate playbook as approved."""
        from formicos.engine.playbook_loader import (  # noqa: PLC0415
            approve_playbook,
        )

        filename = request.path_params.get("filename", "")
        if not filename:
            return JSONResponse({"error": "filename required"}, status_code=400)
        result = approve_playbook(filename)
        if not result:
            return JSONResponse({"error": "Not found"}, status_code=404)
        return JSONResponse({"ok": True, "playbook": result})

    # --- Wave 63 Track 6: Knowledge CRUD ---

    async def update_knowledge_entry(request: Request) -> JSONResponse:
        """Update a knowledge entry's content, title, tags, or domain."""
        from formicos.core.events import MemoryEntryRefined  # noqa: PLC0415

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

        old_content = str(entry.get("content", ""))
        new_content = str(body.get("content", old_content))
        new_title = str(body.get("title", ""))

        ws_id = str(entry.get("workspace_id", ""))
        await runtime.emit_and_broadcast(MemoryEntryRefined(
            seq=0,
            timestamp=datetime.now(UTC),
            address=f"{ws_id}/knowledge_edit",
            entry_id=entry_id,
            workspace_id=ws_id,
            old_content=old_content,
            new_content=new_content,
            new_title=new_title,
            refinement_source="operator",
            source_colony_id="",
        ))

        # Apply tag/domain updates directly to projection
        if "primary_domain" in body:
            entry["primary_domain"] = str(body["primary_domain"])
        if "sub_type" in body:
            entry["sub_type"] = str(body["sub_type"])
        if "tags" in body and isinstance(body["tags"], list):
            entry["tags"] = [str(t) for t in body["tags"]]

        return JSONResponse({
            "entry_id": entry_id,
            "updated": True,
        })

    async def delete_knowledge_entry(request: Request) -> JSONResponse:
        """Soft-delete a knowledge entry (set deprecated, kill confidence)."""
        from formicos.core.events import MemoryConfidenceUpdated  # noqa: PLC0415

        entry_id = request.path_params["entry_id"]
        entry = runtime.projections.memory_entries.get(entry_id)
        if entry is None:
            return _err_response(
                "KNOWLEDGE_ITEM_NOT_FOUND",
                message=f"Entry {entry_id} not found",
            )

        old_alpha = float(entry.get("conf_alpha", 5.0))
        old_beta = float(entry.get("conf_beta", 5.0))
        ws_id = str(entry.get("workspace_id", ""))

        # Kill confidence: alpha ~0, beta=100
        await runtime.emit_and_broadcast(MemoryConfidenceUpdated(
            seq=0,
            timestamp=datetime.now(UTC),
            address=f"{ws_id}/knowledge_delete",
            entry_id=entry_id,
            old_alpha=old_alpha,
            old_beta=old_beta,
            new_alpha=0.01,
            new_beta=100.0,
            new_confidence=0.0001,
            workspace_id=ws_id,
            reason="operator_delete",
        ))

        # Mark as deprecated in projection
        entry["status"] = "deprecated"

        return JSONResponse({
            "entry_id": entry_id,
            "deleted": True,
        })

    async def create_knowledge_entry(request: Request) -> JSONResponse:
        """Create a knowledge entry from operator input."""
        from formicos.core.events import MemoryEntryCreated  # noqa: PLC0415

        try:
            body = await request.json()
        except Exception:
            return _err_response("INVALID_JSON")

        title = str(body.get("title", "")).strip()
        content = str(body.get("content", "")).strip()
        if not title or not content:
            return _err_response(
                "VALIDATION_ERROR",
                message="title and content are required",
            )

        workspace_id = request.path_params.get("workspace_id", "")
        import uuid  # noqa: PLC0415

        entry_id = f"op-{uuid.uuid4().hex[:12]}"
        entry_dict: dict[str, Any] = {
            "id": entry_id,
            "category": body.get("category", "experience"),
            "sub_type": body.get("sub_type", "convention"),
            "title": title,
            "content": content,
            "primary_domain": body.get("primary_domain", ""),
            "domains": [body.get("primary_domain", "")] if body.get("primary_domain") else [],
            "tags": body.get("tags", []),
            "status": "verified",  # operator-authored = trusted
            "decay_class": "stable",
            "conf_alpha": 3.0,  # slightly positive prior
            "conf_beta": 2.0,
            "workspace_id": workspace_id,
            "source_system": "institutional_memory",
            "source": "operator",
            "created_at": datetime.now(UTC).isoformat(),
        }

        await runtime.emit_and_broadcast(MemoryEntryCreated(
            seq=0,
            timestamp=datetime.now(UTC),
            address=f"{workspace_id}/knowledge_create",
            entry=entry_dict,
            workspace_id=workspace_id,
        ))

        return JSONResponse({"entry_id": entry_id, "created": True}, status_code=201)

    # --- Wave 63 Track 7: Workflow step CRUD ---

    async def list_workflow_steps(request: Request) -> JSONResponse:
        """List workflow steps for a thread."""
        workspace_id = request.path_params["workspace_id"]
        thread_id = request.path_params["thread_id"]
        ws = runtime.projections.workspaces.get(workspace_id)
        if ws is None:
            return _err_response("WORKSPACE_NOT_FOUND")
        thread = ws.threads.get(thread_id)
        if thread is None:
            return _err_response("THREAD_NOT_FOUND")
        return JSONResponse({
            "workspace_id": workspace_id,
            "thread_id": thread_id,
            "steps": thread.workflow_steps,
        })

    async def add_workflow_step(request: Request) -> JSONResponse:
        """Add a workflow step to a thread."""
        from formicos.core.events import WorkflowStepDefined  # noqa: PLC0415
        from formicos.core.types import WorkflowStep  # noqa: PLC0415

        workspace_id = request.path_params["workspace_id"]
        thread_id = request.path_params["thread_id"]
        ws = runtime.projections.workspaces.get(workspace_id)
        if ws is None:
            return _err_response("WORKSPACE_NOT_FOUND")
        thread = ws.threads.get(thread_id)
        if thread is None:
            return _err_response("THREAD_NOT_FOUND")
        try:
            body = await request.json()
        except Exception:
            return _err_response("INVALID_JSON")

        description = str(body.get("description", "")).strip()
        if not description:
            return _err_response(
                "VALIDATION_ERROR", message="description is required",
            )

        step_index = len(thread.workflow_steps)
        step = WorkflowStep(
            step_index=step_index,
            description=description,
            expected_outputs=body.get("expected_outputs", []),
        )
        await runtime.emit_and_broadcast(WorkflowStepDefined(
            seq=0,
            timestamp=datetime.now(UTC),
            address=f"{workspace_id}/workflow",
            workspace_id=workspace_id,
            thread_id=thread_id,
            step=step,
        ))
        return JSONResponse({
            "step_index": step_index,
            "created": True,
        }, status_code=201)

    async def update_workflow_step(request: Request) -> JSONResponse:
        """Update a workflow step (description, status, position, notes)."""
        from formicos.core.events import WorkflowStepUpdated  # noqa: PLC0415

        workspace_id = request.path_params["workspace_id"]
        thread_id = request.path_params["thread_id"]
        step_index = int(request.path_params["step_index"])
        ws = runtime.projections.workspaces.get(workspace_id)
        if ws is None:
            return _err_response("WORKSPACE_NOT_FOUND")
        thread = ws.threads.get(thread_id)
        if thread is None:
            return _err_response("THREAD_NOT_FOUND")
        # Verify step exists
        if not any(s.get("step_index") == step_index for s in thread.workflow_steps):
            return _err_response(
                "VALIDATION_ERROR", message=f"Step {step_index} not found",
            )
        try:
            body = await request.json()
        except Exception:
            return _err_response("INVALID_JSON")

        await runtime.emit_and_broadcast(WorkflowStepUpdated(
            seq=0,
            timestamp=datetime.now(UTC),
            address=f"{workspace_id}/workflow",
            workspace_id=workspace_id,
            thread_id=thread_id,
            step_index=step_index,
            new_description=str(body.get("description", "")),
            new_status=str(body.get("status", "")),
            new_position=int(body.get("position", -1)),
            notes=str(body.get("notes", "")),
        ))
        return JSONResponse({"step_index": step_index, "updated": True})

    async def delete_workflow_step(request: Request) -> JSONResponse:
        """Mark a workflow step as skipped."""
        from formicos.core.events import WorkflowStepUpdated  # noqa: PLC0415

        workspace_id = request.path_params["workspace_id"]
        thread_id = request.path_params["thread_id"]
        step_index = int(request.path_params["step_index"])
        ws = runtime.projections.workspaces.get(workspace_id)
        if ws is None:
            return _err_response("WORKSPACE_NOT_FOUND")
        thread = ws.threads.get(thread_id)
        if thread is None:
            return _err_response("THREAD_NOT_FOUND")
        if not any(s.get("step_index") == step_index for s in thread.workflow_steps):
            return _err_response(
                "VALIDATION_ERROR", message=f"Step {step_index} not found",
            )

        await runtime.emit_and_broadcast(WorkflowStepUpdated(
            seq=0,
            timestamp=datetime.now(UTC),
            address=f"{workspace_id}/workflow",
            workspace_id=workspace_id,
            thread_id=thread_id,
            step_index=step_index,
            new_status="skipped",
        ))
        return JSONResponse({"step_index": step_index, "skipped": True})

    # -- Wave 66 T1: Addon endpoints --

    async def list_addons(request: Request) -> JSONResponse:
        """List installed addons with health summaries."""
        regs: list[Any] = getattr(request.app.state, "addon_registrations", [])
        addons = []
        for reg in regs:
            m = reg.manifest
            addons.append({
                "name": m.name,
                "version": m.version,
                "description": m.description,
                "status": reg.health_status,
                "lastError": reg.last_error,
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "callCount": reg.tool_call_counts.get(t.name, 0),
                    }
                    for t in m.tools
                ],
                "handlers": [
                    {
                        "event": h.event,
                        "lastFired": reg.last_handler_fire,
                        "errorCount": reg.handler_error_count,
                    }
                    for h in m.handlers
                ],
                "triggers": [
                    {
                        "type": t.type,
                        "schedule": t.schedule,
                        "handler": t.handler,
                        "lastFired": reg.trigger_fire_times.get(t.handler),
                    }
                    for t in m.triggers
                ],
                "panels": reg.registered_panels,
                "config": [
                    {
                        "key": c.key,
                        "type": c.type,
                        "default": c.default,
                        "label": c.label or c.key,
                        "options": c.options,
                    }
                    for c in m.config
                ],
            })
            # Wave 70.0: capability-based bridge health (no addon-name check)
            _bhfn = (reg.runtime_context or {}).get("get_bridge_health")
            if callable(_bhfn):
                with contextlib.suppress(Exception):
                    addons[-1]["bridgeHealth"] = _bhfn()
        return JSONResponse(addons)

    async def trigger_addon(request: Request) -> JSONResponse:
        """Manually fire an addon trigger handler."""
        from formicos.surface.addon_loader import _resolve_handler  # noqa: PLC0415

        addon_name = request.path_params["addon_name"]
        try:
            body = await request.json()
        except Exception:
            return _err_response("INVALID_JSON")

        handler_ref = body.get("handler", "")
        if not handler_ref:
            return _err_response(
                "MISSING_FIELD", message="handler is required",
            )

        regs: list[Any] = getattr(
            request.app.state, "addon_registrations", [],
        )
        reg = next(
            (r for r in regs if r.manifest.name == addon_name), None,
        )
        if reg is None:
            return _err_response(
                "ADDON_NOT_FOUND",
                message=f"Addon '{addon_name}' not installed",
                status_code=404,
            )

        if getattr(reg, "disabled", False):
            return JSONResponse(
                {"error": f"Addon '{addon_name}' is currently disabled"},
                status_code=409,
            )

        try:
            handler_fn = _resolve_handler(addon_name, handler_ref)
        except (ValueError, AttributeError) as exc:
            return JSONResponse(
                {"error": str(exc)}, status_code=400,
            )

        import inspect  # noqa: PLC0415
        try:
            sig = inspect.signature(handler_fn)
            accepts_ctx = "runtime_context" in sig.parameters
            # Detect tool-convention handlers: (inputs, workspace_id, thread_id, *, ...)
            positional_params = [
                p for p in sig.parameters.values()
                if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                and p.name not in ("self", "cls", "runtime_context")
            ]
            has_tool_args = len(positional_params) >= 3
        except (ValueError, TypeError):
            accepts_ctx = False
            has_tool_args = False

        inputs = body.get("inputs", {})
        trigger_ws_id = body.get("workspace_id", "")
        trigger_thread_id = body.get("thread_id", "")

        try:
            if has_tool_args and accepts_ctx:
                result = await handler_fn(
                    inputs, trigger_ws_id, trigger_thread_id,
                    runtime_context=reg.runtime_context,
                )
            elif has_tool_args:
                result = await handler_fn(
                    inputs, trigger_ws_id, trigger_thread_id,
                )
            elif accepts_ctx:
                result = await handler_fn(
                    runtime_context=reg.runtime_context,
                )
            else:
                result = await handler_fn()
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(
                {"error": f"Trigger failed: {exc}"}, status_code=500,
            )

        # Record trigger fire time
        from datetime import UTC, datetime  # noqa: PLC0415
        reg.trigger_fire_times[handler_ref] = datetime.now(tz=UTC).isoformat()

        return JSONResponse({
            "addon": addon_name,
            "handler": handler_ref,
            "result": str(result) if result is not None else "ok",
        })

    # -- Wave 72.5 Track 1e: Soft addon disable toggle --

    async def toggle_addon(request: Request) -> JSONResponse:
        """Enable or disable an addon at runtime."""
        addon_name = request.path_params["addon_name"]
        try:
            body = await request.json()
        except Exception:
            return _err_response("INVALID_JSON")

        disabled = bool(body.get("disabled", False))

        regs: list[Any] = getattr(
            request.app.state, "addon_registrations", [],
        )
        reg = next(
            (r for r in regs if r.manifest.name == addon_name), None,
        )
        if reg is None:
            return _err_response(
                "ADDON_NOT_FOUND",
                message=f"Addon '{addon_name}' not installed",
                status_code=404,
            )

        reg.disabled = disabled
        return JSONResponse({
            "addon": addon_name,
            "disabled": reg.disabled,
        })

    # -- Wave 66 T2: Addon config surface --

    async def get_addon_config(request: Request) -> JSONResponse:
        """Return addon config schema + current values for a workspace."""
        addon_name = request.path_params["addon_name"]
        workspace_id = request.query_params.get("workspace_id", "")

        regs: list[Any] = getattr(
            request.app.state, "addon_registrations", [],
        )
        reg = next(
            (r for r in regs if r.manifest.name == addon_name), None,
        )
        if reg is None:
            return _err_response(
                "ADDON_NOT_FOUND",
                message=f"Addon '{addon_name}' not installed",
                status_code=404,
            )

        import json as _json  # noqa: PLC0415

        manifest = reg.manifest
        params = []
        for cp in manifest.config:
            # Current value from workspace config (if workspace_id given)
            current = cp.default
            if workspace_id:
                dim = f"addon.{addon_name}.{cp.key}"
                ws_proj = runtime.projections.workspaces.get(workspace_id)
                if ws_proj is not None:
                    ws_config = getattr(ws_proj, "config", {})
                    if dim in ws_config:
                        # Config values stored as JSON strings in projection
                        try:
                            current = _json.loads(ws_config[dim])
                        except (ValueError, TypeError):
                            current = ws_config[dim]
            params.append({
                "key": cp.key,
                "type": cp.type,
                "default": cp.default,
                "label": cp.label or cp.key,
                "options": cp.options,
                "value": current,
            })

        return JSONResponse({
            "addon": addon_name,
            "config": params,
        })

    async def put_addon_config(request: Request) -> JSONResponse:
        """Update addon config values for a workspace via WorkspaceConfigChanged."""
        import json as _json  # noqa: PLC0415
        from datetime import UTC, datetime  # noqa: PLC0415

        from formicos.core.events import WorkspaceConfigChanged  # noqa: PLC0415

        addon_name = request.path_params["addon_name"]

        try:
            body = await request.json()
        except Exception:
            return _err_response("INVALID_JSON")

        workspace_id = body.get("workspace_id", "")
        if not workspace_id:
            return _err_response(
                "MISSING_FIELD", message="workspace_id is required",
            )
        values: dict[str, Any] = body.get("values", {})
        if not values:
            return _err_response(
                "MISSING_FIELD", message="values dict is required",
            )

        regs: list[Any] = getattr(
            request.app.state, "addon_registrations", [],
        )
        reg = next(
            (r for r in regs if r.manifest.name == addon_name), None,
        )
        if reg is None:
            return _err_response(
                "ADDON_NOT_FOUND",
                message=f"Addon '{addon_name}' not installed",
                status_code=404,
            )

        # Validate keys against manifest schema
        valid_keys = {cp.key for cp in reg.manifest.config}
        unknown = set(values.keys()) - valid_keys
        if unknown:
            return _err_response(
                "MISSING_FIELD",
                message=f"Unknown config keys: {sorted(unknown)}",
            )

        # Wave 73 B4: coerce values to match declared types
        for param in reg.manifest.config:
            if param.key in values:
                val = values[param.key]
                if param.type == "boolean" and isinstance(val, str):
                    values[param.key] = val.lower() in ("true", "1", "yes")
                elif param.type == "integer" and isinstance(val, str):
                    with contextlib.suppress(ValueError):
                        values[param.key] = int(val)

        # Emit WorkspaceConfigChanged for each key
        updated = []
        for key, new_val in values.items():
            dim = f"addon.{addon_name}.{key}"
            # Get old value
            old_val = None
            ws_proj = runtime.projections.workspaces.get(workspace_id)
            if ws_proj is not None:
                ws_config = getattr(ws_proj, "config", {})
                old_val = ws_config.get(dim)

            await runtime.emit_and_broadcast(WorkspaceConfigChanged(
                seq=0,
                timestamp=datetime.now(tz=UTC),
                address=workspace_id,
                workspace_id=workspace_id,
                field=dim,
                old_value=old_val if isinstance(old_val, str) else (
                    _json.dumps(old_val) if old_val is not None else None
                ),
                new_value=_json.dumps(new_val),
            ))
            updated.append(key)

        return JSONResponse({
            "addon": addon_name,
            "workspace_id": workspace_id,
            "updated": updated,
        })

    # Wave 69 Track 4: thread plan read endpoint
    import re as _re
    _PLAN_STEP_RE = _re.compile(
        r"^- \[(\d+)\] \[(\w+)\] (.*)$",
    )

    async def get_thread_plan(request: Request) -> JSONResponse:
        thread_id = request.path_params["thread_id"]
        data_dir = getattr(settings, "system", None)
        data_dir_str = getattr(data_dir, "data_dir", "") if data_dir else ""
        if not data_dir_str:
            return JSONResponse({"exists": False})

        plan_path = Path(data_dir_str) / ".formicos" / "plans" / f"{thread_id}.md"
        if not plan_path.is_file():
            return JSONResponse({"exists": False})

        try:
            text = plan_path.read_text(encoding="utf-8")
        except OSError:
            return JSONResponse({"exists": False})

        title = ""
        approach = ""
        steps: list[dict[str, Any]] = []

        for line in text.splitlines():
            if line.startswith("# Plan: "):
                title = line[8:].strip()
            elif line.startswith("**Approach:**"):
                approach = line[len("**Approach:**"):].strip()
            else:
                m = _PLAN_STEP_RE.match(line)
                if m:
                    idx_str, status, desc = m.groups()
                    step: dict[str, Any] = {
                        "index": int(idx_str),
                        "status": status,
                        "description": desc,
                    }
                    # Parse optional colony ID: (colony abc123)
                    col_match = _re.search(
                        r"\(colony\s+(\S+)\)", desc,
                    )
                    if col_match:
                        step["colony_id"] = col_match.group(1)
                    # Parse optional note after em-dash
                    if " \u2014 " in desc:
                        step["note"] = desc.split(" \u2014 ", 1)[1]
                    steps.append(step)

        return JSONResponse({
            "exists": True,
            "title": title or "Plan",
            "approach": approach,
            "steps": steps,
        })

    # Wave 71.0 Track 5: action queue endpoints
    async def list_operation_actions(request: Request) -> JSONResponse:
        workspace_id = request.path_params["workspace_id"]
        data_dir = getattr(settings, "system", None)
        data_dir_str = getattr(data_dir, "data_dir", "") if data_dir else ""
        if not data_dir_str:
            return JSONResponse({
                "actions": [], "total": 0,
                "counts_by_status": {}, "counts_by_kind": {},
            })

        from formicos.surface.action_queue import list_actions as _list_actions  # noqa: PLC0415

        status_filter = request.query_params.get("status", "")
        kind_filter = request.query_params.get("kind", "")
        limit = min(int(request.query_params.get("limit", "100")), 500)
        result = _list_actions(
            data_dir_str, workspace_id,
            status=status_filter, kind=kind_filter, limit=limit,
        )
        return JSONResponse(result)

    async def approve_action(request: Request) -> JSONResponse:
        workspace_id = request.path_params["workspace_id"]
        action_id = request.path_params["action_id"]
        data_dir = getattr(settings, "system", None)
        data_dir_str = getattr(data_dir, "data_dir", "") if data_dir else ""
        if not data_dir_str:
            return JSONResponse({"error": "No data directory"}, status_code=500)

        from formicos.core.types import CasteSlot as _CasteSlot  # noqa: PLC0415
        from formicos.surface.action_queue import (  # noqa: PLC0415
            STATUS_APPROVED,
            STATUS_EXECUTED,
            STATUS_FAILED,
        )
        from formicos.surface.action_queue import (
            update_action as _update_action,
        )

        try:
            updated = _update_action(
                data_dir_str, workspace_id, action_id,
                {"status": STATUS_APPROVED},
            )
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=409)
        if updated is None:
            return JSONResponse({"error": "Action not found"}, status_code=404)

        # If there is a maintenance dispatcher, attempt dispatch
        dispatcher = getattr(request.app.state, "maintenance_dispatcher", None)
        if dispatcher is not None and updated.get("payload", {}).get("suggested_colony"):
            try:
                sc = updated["payload"]["suggested_colony"]
                colony_id: str = await runtime.spawn_colony(
                    workspace_id=workspace_id,
                    thread_id=updated.get("thread_id") or "maintenance",
                    task=sc.get("task", updated.get("title", "")),
                    castes=[_CasteSlot(caste=sc.get("caste", "researcher"))],
                    strategy=sc.get("strategy", "sequential"),
                    max_rounds=sc.get("max_rounds", 3),
                )
                _update_action(
                    data_dir_str, workspace_id, action_id,
                    {"status": STATUS_EXECUTED, "executed_at": datetime.now(UTC).isoformat()},
                )
                # Wave 76: journal coverage
                from formicos.surface.operational_state import append_journal_entry  # noqa: PLC0415
                append_journal_entry(
                    data_dir_str, workspace_id,
                    source="operator",
                    message=f"Approved and executed: {updated.get('title', action_id)}",
                )
                return JSONResponse({"ok": True, "action_id": action_id, "colony_id": colony_id})
            except Exception as exc:  # noqa: BLE001
                _update_action(
                    data_dir_str, workspace_id, action_id,
                    {"status": STATUS_FAILED, "operator_reason": str(exc)},
                )
                return JSONResponse({"ok": True, "action_id": action_id, "error": str(exc)})

        # Wave 72: handle workflow_template approval — save as learned template
        if updated.get("kind") == "workflow_template":
            try:
                payload = updated.get("payload", {})
                from formicos.core.types import CasteSlot as _CasteSlot2  # noqa: PLC0415
                from formicos.surface.template_manager import (  # noqa: PLC0415
                    ColonyTemplate,
                    new_template_id,
                    save_template,
                )

                castes_list = payload.get("castes", ["researcher"])
                tmpl = ColonyTemplate(
                    template_id=new_template_id(),
                    name=updated.get("title", "Learned template"),
                    description=updated.get("detail", ""),
                    castes=[_CasteSlot2(caste=c) for c in castes_list],
                    strategy=payload.get("strategy", "sequential"),
                    learned=True,
                    task_category="",
                )
                await save_template(tmpl)
                _update_action(
                    data_dir_str, workspace_id, action_id,
                    {"status": STATUS_EXECUTED, "executed_at": datetime.now(UTC).isoformat()},
                )
                # Wave 76: journal coverage
                from formicos.surface.operational_state import append_journal_entry  # noqa: PLC0415
                append_journal_entry(
                    data_dir_str, workspace_id,
                    source="operator",
                    message=f"Approved workflow template: {updated.get('title', action_id)}",
                )
                return JSONResponse({
                    "ok": True, "action_id": action_id,
                    "template_id": tmpl.template_id,
                })
            except Exception as exc:  # noqa: BLE001
                _update_action(
                    data_dir_str, workspace_id, action_id,
                    {"status": STATUS_FAILED, "operator_reason": str(exc)},
                )
                return JSONResponse({"ok": True, "action_id": action_id, "error": str(exc)})

        # Wave 72: handle procedure_suggestion approval — append to procedures
        if updated.get("kind") == "procedure_suggestion":
            try:
                from formicos.surface.operational_state import (  # noqa: PLC0415
                    append_procedure_rule,
                )

                payload = updated.get("payload", {})
                heading = payload.get("heading", "General")
                rule = payload.get("rule", updated.get("title", ""))
                append_procedure_rule(data_dir_str, workspace_id, heading, rule)
                _update_action(
                    data_dir_str, workspace_id, action_id,
                    {"status": STATUS_EXECUTED, "executed_at": datetime.now(UTC).isoformat()},
                )
                # Wave 76: journal coverage
                from formicos.surface.operational_state import append_journal_entry  # noqa: PLC0415
                append_journal_entry(
                    data_dir_str, workspace_id,
                    source="operator",
                    message=f"Approved procedure suggestion: {updated.get('title', action_id)}",
                )
                return JSONResponse({"ok": True, "action_id": action_id, "appended": True})
            except Exception as exc:  # noqa: BLE001
                _update_action(
                    data_dir_str, workspace_id, action_id,
                    {"status": STATUS_FAILED, "operator_reason": str(exc)},
                )
                return JSONResponse({"ok": True, "action_id": action_id, "error": str(exc)})

        return JSONResponse({"ok": True, "action_id": action_id})

    async def reject_action(request: Request) -> JSONResponse:
        workspace_id = request.path_params["workspace_id"]
        action_id = request.path_params["action_id"]
        data_dir = getattr(settings, "system", None)
        data_dir_str = getattr(data_dir, "data_dir", "") if data_dir else ""
        if not data_dir_str:
            return JSONResponse({"error": "No data directory"}, status_code=500)

        import contextlib  # noqa: PLC0415

        from formicos.surface.action_queue import (  # noqa: PLC0415
            STATUS_REJECTED,
        )
        from formicos.surface.action_queue import (
            update_action as _update_action,
        )

        body: dict[str, Any] = {}
        with contextlib.suppress(Exception):
            body = await request.json()

        reason = body.get("reason", "")

        updated = _update_action(
            data_dir_str, workspace_id, action_id,
            {"status": STATUS_REJECTED, "operator_reason": reason},
        )
        if updated is None:
            return JSONResponse({"error": "Action not found"}, status_code=404)

        return JSONResponse({"ok": True, "action_id": action_id})

    # Wave 72 Track 2: Knowledge review processing
    async def review_action(request: Request) -> JSONResponse:
        """Process a knowledge review decision (confirm or invalidate)."""
        workspace_id = request.path_params["workspace_id"]
        action_id = request.path_params["action_id"]
        data_dir = getattr(settings, "system", None)
        data_dir_str = getattr(data_dir, "data_dir", "") if data_dir else ""
        if not data_dir_str:
            return JSONResponse({"error": "No data directory"}, status_code=500)

        import contextlib  # noqa: PLC0415

        from formicos.surface.action_queue import (  # noqa: PLC0415
            STATUS_EXECUTED,
        )
        from formicos.surface.action_queue import (
            read_actions as _read_actions,
        )
        from formicos.surface.action_queue import (
            update_action as _update_action,
        )

        body: dict[str, Any] = {}
        with contextlib.suppress(Exception):
            body = await request.json()

        decision = body.get("decision", "")
        reason = body.get("reason", "")

        if decision not in ("confirm", "invalidate"):
            return JSONResponse(
                {"error": "decision must be 'confirm' or 'invalidate'"},
                status_code=400,
            )

        # Find the action and extract entry_id from payload
        actions = _read_actions(data_dir_str, workspace_id)
        target = None
        for act in actions:
            if act.get("action_id") == action_id:
                target = act
                break
        if target is None:
            return JSONResponse({"error": "Action not found"}, status_code=404)

        entry_id = target.get("payload", {}).get("entry_id", "")
        if not entry_id:
            return JSONResponse({"error": "No entry_id in action payload"}, status_code=400)

        entry = runtime.projections.memory_entries.get(entry_id)
        if entry is None:
            return JSONResponse(
                {"error": f"Entry {entry_id} not found"},
                status_code=404,
            )

        if decision == "confirm":
            # Reuse the replay-safe feedback path: positive operator feedback
            from formicos.core.events import MemoryConfidenceUpdated  # noqa: PLC0415

            old_alpha = float(entry.get("conf_alpha", 5.0))
            old_beta = float(entry.get("conf_beta", 5.0))
            new_alpha = old_alpha + 1.0
            new_beta = old_beta
            await runtime.emit_and_broadcast(MemoryConfidenceUpdated(
                seq=0,
                timestamp=datetime.now(UTC),
                address=f"{workspace_id}/review",
                entry_id=entry_id,
                old_alpha=old_alpha,
                old_beta=old_beta,
                new_alpha=new_alpha,
                new_beta=new_beta,
                new_confidence=new_alpha / (new_alpha + new_beta),
                workspace_id=workspace_id,
                reason=f"review_confirmed: {reason}" if reason else "review_confirmed",
            ))
        else:
            # Reuse the operator overlay invalidation path
            from formicos.core.events import KnowledgeEntryOperatorAction  # noqa: PLC0415

            await runtime.emit_and_broadcast(KnowledgeEntryOperatorAction(
                seq=0,
                timestamp=datetime.now(UTC),
                address=f"{workspace_id}/{entry_id}",
                entry_id=entry_id,
                workspace_id=workspace_id,
                action="invalidate",
                actor="operator",
                reason=f"review_invalidated: {reason}" if reason else "review_invalidated",
            ))

        # Mark the action as executed
        _update_action(
            data_dir_str, workspace_id, action_id,
            {
                "status": STATUS_EXECUTED,
                "operator_reason": reason,
                "executed_at": datetime.now(UTC).isoformat(),
            },
        )

        return JSONResponse({
            "ok": True,
            "action_id": action_id,
            "entry_id": entry_id,
            "decision": decision,
        })

    # --- Wave 72 Track 10B: maintenance-policy GET/PUT ---

    async def get_maintenance_policy(request: Request) -> JSONResponse:
        """Return current maintenance policy for a workspace."""
        from formicos.core.types import MaintenancePolicy  # noqa: PLC0415

        workspace_id = request.path_params["workspace_id"]
        ws = runtime.projections.workspaces.get(workspace_id)
        if ws is None:
            return _err_response("WORKSPACE_NOT_FOUND")

        raw = ws.config.get("maintenance_policy")
        if raw is None:
            return JSONResponse(MaintenancePolicy().model_dump())
        if isinstance(raw, str):
            try:
                return JSONResponse(json.loads(raw))
            except (ValueError, TypeError):
                return JSONResponse(MaintenancePolicy().model_dump())
        if isinstance(raw, dict):
            return JSONResponse(dict(raw))  # type: ignore[arg-type]
        return JSONResponse(MaintenancePolicy().model_dump())

    async def put_maintenance_policy(request: Request) -> JSONResponse:
        """Update maintenance policy for a workspace."""
        from formicos.core.events import WorkspaceConfigChanged  # noqa: PLC0415
        from formicos.core.types import AutonomyLevel, MaintenancePolicy  # noqa: PLC0415

        workspace_id = request.path_params["workspace_id"]
        ws = runtime.projections.workspaces.get(workspace_id)
        if ws is None:
            return _err_response("WORKSPACE_NOT_FOUND")

        try:
            body = await request.json()
        except Exception:
            return _err_response("INVALID_JSON")

        autonomy_level = body.get("autonomy_level", "suggest")
        valid_levels = {e.value for e in AutonomyLevel}
        if autonomy_level not in valid_levels:
            return _err_response(
                "INVALID_PARAMETER",
                message=f"autonomy_level must be one of {sorted(valid_levels)}",
            )

        budget = float(body.get("daily_maintenance_budget", 1.0))
        if budget <= 0:
            return _err_response(
                "INVALID_PARAMETER",
                message="daily_maintenance_budget must be > 0",
            )

        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel(autonomy_level),
            auto_actions=body.get("auto_actions", []),
            max_maintenance_colonies=int(body.get("max_maintenance_colonies", 2)),
            daily_maintenance_budget=budget,
        )

        old_raw = ws.config.get("maintenance_policy")
        old_json = str(old_raw) if old_raw is not None else None
        await runtime.emit_and_broadcast(WorkspaceConfigChanged(
            seq=0,
            timestamp=datetime.now(UTC),
            address=workspace_id,
            workspace_id=workspace_id,
            field="maintenance_policy",
            old_value=old_json,
            new_value=policy.model_dump_json(),
        ))
        return JSONResponse({"status": "updated", "policy": policy.model_dump()})

    # --- Wave 72 Track 10C: add model endpoint ---

    async def add_model(request: Request) -> JSONResponse:
        """Add a new model to the registry."""
        try:
            body: dict[str, Any] = await request.json()
        except Exception:
            return _err_response("INVALID_JSON")

        address = str(body.get("address", "")).strip()
        if not address:
            return _err_response("MISSING_FIELD", message="address is required")

        # Check for duplicates
        for m in settings.models.registry:
            if m.address == address:
                return _err_response(
                    "VALIDATION_ERROR", message=f"model '{address}' already exists",
                )

        provider = str(body.get("provider", address.split("/")[0] if "/" in address else "custom"))
        try:
            new_model = ModelRecord(
                address=address,
                provider=provider,
                endpoint=body.get("endpoint"),
                api_key_env=body.get("api_key_env"),
                context_window=int(body.get("context_window", 8192)),
                supports_tools=bool(body.get("supports_tools", True)),
                supports_vision=bool(body.get("supports_vision", False)),
                cost_per_input_token=body.get("cost_per_input_token"),
                cost_per_output_token=body.get("cost_per_output_token"),
                max_output_tokens=int(body.get("max_output_tokens", 4096)),
                hidden=bool(body.get("hidden", False)),
            )
        except (ValueError, TypeError) as exc:
            return _err_response("VALIDATION_FAILED", message=f"invalid fields: {exc}")

        settings.models.registry.append(new_model)
        save_model_registry(config_path, settings)
        log.info("model.added", address=address)
        return JSONResponse(new_model.model_dump(), status_code=201)

    # Wave 70.0 Track 5: project plan read endpoint
    async def get_project_plan(request: Request) -> JSONResponse:
        data_dir = getattr(settings, "system", None)
        data_dir_str = getattr(data_dir, "data_dir", "") if data_dir else ""
        if not data_dir_str:
            return JSONResponse({"exists": False})

        from formicos.surface.project_plan import load_project_plan  # noqa: PLC0415

        plan = load_project_plan(data_dir_str)
        return JSONResponse(plan)

    # -- Wave 71.0 Track 3: Journal / Procedures endpoints --

    async def get_queen_journal(request: Request) -> JSONResponse:
        """Return structured journal entries for a workspace."""
        from formicos.surface.operational_state import (  # noqa: PLC0415
            get_journal_summary,
        )

        workspace_id = request.path_params["workspace_id"]
        data_dir = getattr(settings, "system", None)
        data_dir_str = getattr(data_dir, "data_dir", "") if data_dir else ""
        if not data_dir_str:
            return JSONResponse({"exists": False, "entries": []})

        return JSONResponse(get_journal_summary(data_dir_str, workspace_id))

    async def get_operating_procedures(request: Request) -> JSONResponse:
        """Return operating procedures for a workspace."""
        from formicos.surface.operational_state import (  # noqa: PLC0415
            get_procedures_summary,
        )

        workspace_id = request.path_params["workspace_id"]
        data_dir = getattr(settings, "system", None)
        data_dir_str = getattr(data_dir, "data_dir", "") if data_dir else ""
        if not data_dir_str:
            return JSONResponse({"exists": False, "content": ""})

        return JSONResponse(get_procedures_summary(data_dir_str, workspace_id))

    async def put_operating_procedures(request: Request) -> JSONResponse:
        """Update operating procedures for a workspace."""
        from formicos.surface.operational_state import (  # noqa: PLC0415
            save_procedures,
        )

        workspace_id = request.path_params["workspace_id"]
        data_dir = getattr(settings, "system", None)
        data_dir_str = getattr(data_dir, "data_dir", "") if data_dir else ""
        if not data_dir_str:
            return _err_response(
                "DATA_DIR_NOT_SET", message="data_dir not configured",
            )

        try:
            body = await request.json()
        except Exception:
            return _err_response("INVALID_JSON")

        content = body.get("content", "")
        if not isinstance(content, str):
            return _err_response(
                "VALIDATION_ERROR", message="content must be a string",
            )

        save_procedures(data_dir_str, workspace_id, content)
        return JSONResponse({"updated": True})

    # Wave 71.0 Track 9: Operations summary endpoint
    async def get_operations_summary(request: Request) -> JSONResponse:
        """Return synthesized operational summary for a workspace."""
        from formicos.surface.operations_coordinator import (  # noqa: PLC0415
            build_operations_summary,
        )

        workspace_id = request.path_params["workspace_id"]
        data_dir = getattr(settings, "system", None)
        data_dir_str = getattr(data_dir, "data_dir", "") if data_dir else ""
        if not data_dir_str:
            return JSONResponse({
                "workspace_id": workspace_id,
                "pending_review_count": 0,
                "active_milestone_count": 0,
                "stalled_thread_count": 0,
                "last_operator_activity_at": None,
                "idle_for_minutes": None,
                "operator_active": False,
                "continuation_candidates": [],
                "sync_issues": [],
                "recent_progress": [],
            })

        proj = runtime.projections if runtime else None
        return JSONResponse(build_operations_summary(
            data_dir_str, workspace_id, proj,
        ))

    # Wave 75 Track 3: billing status
    async def get_billing_status(request: Any) -> JSONResponse:
        from formicos.surface.metering import (  # noqa: PLC0415
            aggregate_period,
            current_period,
        )

        event_store = getattr(request.app.state, "event_store", None)
        if event_store is None:
            return to_http_error(KNOWN_ERRORS["service_unavailable"])
        start, end = current_period()
        agg = await aggregate_period(event_store, start, end)
        return JSONResponse(agg)

    # --- Wave 77.5 A5: project context, project plan PUT, AI filesystem ---

    async def get_project_context(request: Request) -> JSONResponse:
        """Return project context markdown for a workspace."""
        workspace_id = request.path_params["workspace_id"]
        data_dir = getattr(settings, "system", None)
        data_dir_str = getattr(data_dir, "data_dir", "") if data_dir else ""
        if not data_dir_str:
            return JSONResponse({"content": ""})
        path = Path(data_dir_str) / ".formicos" / "workspaces" / workspace_id / "project_context.md"
        content = path.read_text(encoding="utf-8") if path.is_file() else ""
        return JSONResponse({"content": content})

    async def put_project_context(request: Request) -> JSONResponse:
        """Save project context markdown for a workspace."""
        workspace_id = request.path_params["workspace_id"]
        data_dir = getattr(settings, "system", None)
        data_dir_str = getattr(data_dir, "data_dir", "") if data_dir else ""
        if not data_dir_str:
            return to_http_error(KNOWN_ERRORS["workspace_not_found"])
        body = await request.json()
        path = Path(data_dir_str) / ".formicos" / "workspaces" / workspace_id / "project_context.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body.get("content", ""), encoding="utf-8")
        return JSONResponse({"ok": True})

    async def put_project_plan(request: Request) -> JSONResponse:
        """Save project plan markdown for a workspace."""
        workspace_id = request.path_params["workspace_id"]
        data_dir = getattr(settings, "system", None)
        data_dir_str = getattr(data_dir, "data_dir", "") if data_dir else ""
        if not data_dir_str:
            return to_http_error(KNOWN_ERRORS["workspace_not_found"])
        body = await request.json()
        # Workspace-scoped path takes precedence if it exists
        ws_path = Path(data_dir_str) / ".formicos" / "workspaces" / workspace_id / "project_plan.md"
        fallback_path = Path(data_dir_str) / ".formicos" / "project_plan.md"
        target = ws_path if ws_path.is_file() else fallback_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body.get("content", ""), encoding="utf-8")
        return JSONResponse({"ok": True})

    async def get_ai_filesystem(request: Request) -> JSONResponse:
        """Return AI Filesystem tree listing for a workspace."""
        from formicos.surface.ai_filesystem import (  # noqa: PLC0415
            _artifacts_root,  # pyright: ignore[reportPrivateUsage]
            _runtime_root,  # pyright: ignore[reportPrivateUsage]
        )

        workspace_id = request.path_params["workspace_id"]
        data_dir = getattr(settings, "system", None)
        data_dir_str = getattr(data_dir, "data_dir", "") if data_dir else ""
        if not data_dir_str:
            return JSONResponse({"runtime": [], "artifacts": []})

        def _walk(root: Path) -> list[dict[str, Any]]:
            if not root.is_dir():
                return []
            entries: list[dict[str, Any]] = []
            for item in sorted(root.iterdir()):
                if item.is_file():
                    entries.append({"name": item.name, "type": "file", "size": item.stat().st_size})
                elif item.is_dir():
                    entries.append({"name": item.name, "type": "dir", "children": _walk(item)})
            return entries

        return JSONResponse({
            "runtime": _walk(_runtime_root(data_dir_str, workspace_id)),
            "artifacts": _walk(_artifacts_root(data_dir_str, workspace_id)),
        })

    # --- Wave 79.5 C2: AI filesystem preview + promote ---

    async def get_ai_fs_file(request: Request) -> JSONResponse:
        """Preview a file from the AI filesystem."""
        from formicos.surface.ai_filesystem import preview_file  # noqa: PLC0415

        workspace_id = request.path_params["workspace_id"]
        scope = request.query_params.get("scope", "runtime")
        rel_path = request.query_params.get("path", "")
        if not rel_path:
            return JSONResponse({"content": "", "error": "path is required"}, status_code=400)
        data_dir = getattr(settings, "system", None)
        data_dir_str = getattr(data_dir, "data_dir", "") if data_dir else ""
        if not data_dir_str:
            return JSONResponse({"content": "", "error": "no data dir"})
        content = preview_file(data_dir_str, workspace_id, scope, rel_path)
        is_error = content.startswith("Error:")
        return JSONResponse({
            "content": "" if is_error else content,
            "error": content if is_error else "",
        })

    async def post_ai_fs_promote(request: Request) -> JSONResponse:
        """Promote a runtime file to artifacts."""
        from formicos.surface.ai_filesystem import promote_to_artifact  # noqa: PLC0415

        workspace_id = request.path_params["workspace_id"]
        body = await request.json()
        rel_path = body.get("path", "")
        target_subdir = body.get("target_subdir", "deliverables")
        if not rel_path:
            return JSONResponse({"ok": False, "error": "path is required"}, status_code=400)
        data_dir = getattr(settings, "system", None)
        data_dir_str = getattr(data_dir, "data_dir", "") if data_dir else ""
        if not data_dir_str:
            return JSONResponse({"ok": False, "error": "no data dir"})
        result = promote_to_artifact(data_dir_str, workspace_id, rel_path, target_subdir)
        is_error = result.startswith("Error")
        return JSONResponse({
            "ok": not is_error,
            "path": result if not is_error else "",
            "error": result if is_error else "",
        })

    # --- Wave 81 Track A: project binding + project-file routes ---

    async def get_project_binding(request: Request) -> JSONResponse:
        """Return workspace binding status (project vs library root) + code index."""
        from formicos.surface.workspace_roots import (  # noqa: PLC0415
            workspace_binding_status,
        )

        workspace_id = request.path_params["workspace_id"]
        data_dir = getattr(settings, "system", None)
        data_dir_str = getattr(data_dir, "data_dir", "") if data_dir else ""
        if not data_dir_str:
            return JSONResponse({"project_bound": False, "bound": False})
        payload = workspace_binding_status(data_dir_str, workspace_id)

        # Wave 81 seam: merge code-index sidecar status for Track D frontend
        try:
            from formicos.addons.codebase_index.indexer import read_index_status  # noqa: PLC0415

            sidecar = read_index_status(data_dir_str, workspace_id)
            if sidecar:
                payload["code_index"] = {
                    "status": "ready",
                    "chunks_indexed": sidecar.get("chunk_count", 0),
                    "last_indexed_at": sidecar.get("last_indexed_at", ""),
                    "last_file_count": sidecar.get("file_count", 0),
                    "last_error_count": sidecar.get("error_count", 0),
                }
            else:
                payload["code_index"] = {"status": "not_indexed", "chunks_indexed": 0}
        except ImportError:
            payload["code_index"] = {"status": "unavailable", "chunks_indexed": 0}

        return JSONResponse(payload)

    async def list_project_files(request: Request) -> JSONResponse:
        """List files in the bound project root."""
        from formicos.surface.workspace_roots import (  # noqa: PLC0415
            workspace_project_root,
        )

        workspace_id = request.path_params["workspace_id"]
        project = workspace_project_root(workspace_id)
        if project is None or not project.is_dir():
            return JSONResponse({"files": [], "project_bound": False})

        files: list[dict[str, Any]] = []
        try:
            for item in sorted(project.rglob("*")):
                if item.is_file() and len(files) < 500:
                    rel = str(item.relative_to(project))
                    # Skip hidden/large/binary paths
                    if any(p.startswith(".") for p in item.parts[len(project.parts):]):
                        continue
                    try:
                        size = item.stat().st_size
                    except OSError:
                        size = 0
                    files.append({"name": rel, "bytes": size})
        except OSError:
            pass

        return JSONResponse({"files": files, "project_bound": True})

    async def preview_project_file(request: Request) -> JSONResponse:
        """Preview a file from the bound project root."""
        from formicos.surface.workspace_roots import (  # noqa: PLC0415
            workspace_project_root,
        )

        workspace_id = request.path_params["workspace_id"]
        file_path = request.path_params.get("file_path", "")
        project = workspace_project_root(workspace_id)
        if project is None:
            return JSONResponse({"content": "", "error": "No project bound"})

        rel = Path(file_path)
        if rel.is_absolute() or ".." in rel.parts:
            return JSONResponse({"content": "", "error": "Invalid path"}, status_code=400)

        target = project / rel
        if not target.is_file():
            return JSONResponse({"content": "", "error": "File not found"})

        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            truncated = len(content) > 50000
            if truncated:
                content = content[:50000]
            return JSONResponse({
                "content": content,
                "truncated": truncated,
            })
        except OSError as exc:
            return JSONResponse({"content": "", "error": str(exc)})

    # --- Wave 82 Track A: planning history compare route ---

    async def get_planning_history(request: Request) -> JSONResponse:
        """Return similar successful prior plans for compare."""
        from formicos.surface.workflow_learning import (  # noqa: PLC0415
            get_relevant_outcomes,
        )

        workspace_id = request.path_params["workspace_id"]
        query = request.query_params.get("query", "")
        top_k = min(int(request.query_params.get("top_k", "3")), 10)

        if not query:
            return JSONResponse({"plans": []})

        outcomes = get_relevant_outcomes(
            runtime.projections,
            workspace_id=workspace_id,
            operator_message=query,
            top_k=top_k,
        )
        # Wave 83 B3: label each entry as summary-only history
        for o in outcomes:
            o.setdefault("evidence_type", "summary_history")
            o.setdefault("has_dag_structure", False)
        return JSONResponse({"plans": outcomes})

    # --- Wave 83 polish: reviewed-plan validation route ---

    async def post_validate_reviewed_plan(request: Request) -> JSONResponse:
        """Validate a reviewed plan via HTTP for the workbench UI."""
        from formicos.surface.reviewed_plan import (  # noqa: PLC0415
            normalize_preview,
            validate_plan,
        )

        try:
            body: dict[str, Any] = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        preview = body.get("preview", {})
        if not isinstance(preview, dict) or not preview:
            return JSONResponse({
                "valid": False,
                "errors": ["preview is required"],
                "warnings": [],
            })

        normalized = normalize_preview(preview)
        errors, warnings = validate_plan(normalized)
        return JSONResponse({
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        })

    # --- Wave 83 Track B: plan patterns ---

    async def list_plan_patterns(request: Request) -> JSONResponse:
        """Return all saved plan patterns for a workspace."""
        from formicos.surface.plan_patterns import list_patterns  # noqa: PLC0415

        workspace_id = request.path_params["workspace_id"]
        data_dir = getattr(settings.system, "data_dir", "")
        patterns = list_patterns(data_dir, workspace_id)
        return JSONResponse({"patterns": patterns})

    async def create_plan_pattern(request: Request) -> JSONResponse:
        """Save a reviewed plan as a named pattern."""
        from formicos.surface.plan_patterns import save_pattern  # noqa: PLC0415

        workspace_id = request.path_params["workspace_id"]
        data_dir = getattr(settings.system, "data_dir", "")
        try:
            body: dict[str, Any] = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)
        result = save_pattern(data_dir, workspace_id, body)
        return JSONResponse({"ok": True, "pattern": result})

    async def get_plan_pattern(request: Request) -> JSONResponse:
        """Return a single saved plan pattern by ID."""
        from formicos.surface.plan_patterns import get_pattern  # noqa: PLC0415

        workspace_id = request.path_params["workspace_id"]
        pattern_id = request.path_params["pattern_id"]
        data_dir = getattr(settings.system, "data_dir", "")
        pattern = get_pattern(data_dir, workspace_id, pattern_id)
        if pattern is None:
            return JSONResponse({"error": "Pattern not found"}, status_code=404)
        return JSONResponse({"pattern": pattern})

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
        Route("/api/v1/playbooks", create_playbook, methods=["POST"]),
        Route(
            "/api/v1/playbooks/{filename:str}",
            delete_playbook_route, methods=["DELETE"],
        ),
        Route(
            "/api/v1/playbooks/{filename:str}/approve",
            approve_playbook_route, methods=["PUT"],
        ),
        Route("/api/v1/system/providers", get_provider_health, methods=["GET"]),
        Route("/api/v1/castes", get_castes_api, methods=["GET"]),
        Route("/api/v1/castes/{caste_id:str}", upsert_caste, methods=["PUT"]),
        Route("/api/v1/models/{address:path}", update_model_policy, methods=["PATCH"]),
        Route("/api/v1/workspaces/{workspace_id:str}/briefing", get_briefing),
        Route("/api/v1/workspaces/{workspace_id:str}/outcomes", get_workspace_outcomes),
        Route("/api/v1/workspaces/{workspace_id:str}/knowledge-tree", get_knowledge_tree),
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
        # Wave 73 B3: workspace creation
        Route("/api/v1/workspaces", create_workspace_endpoint, methods=["POST"]),
        # Wave 55: learning summary
        Route(
            "/api/v1/workspaces/{workspace_id:str}/learning-summary",
            get_learning_summary, methods=["GET"],
        ),
        # Wave 61: budget control panel
        Route(
            "/api/v1/workspaces/{workspace_id:str}/budget",
            get_workspace_budget, methods=["GET"],
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
        # Wave 71.0 Track 3: Journal / Procedures
        Route(
            "/api/v1/workspaces/{workspace_id:str}/queen-journal",
            get_queen_journal, methods=["GET"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/operating-procedures",
            get_operating_procedures, methods=["GET"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/operating-procedures",
            put_operating_procedures, methods=["PUT"],
        ),
        # Wave 71.0 Track 5: Action queue endpoints
        Route(
            "/api/v1/workspaces/{workspace_id:str}/operations/actions",
            list_operation_actions, methods=["GET"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/operations/actions/{action_id:str}/approve",
            approve_action, methods=["POST"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/operations/actions/{action_id:str}/reject",
            reject_action, methods=["POST"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/operations/actions/{action_id:str}/review",
            review_action, methods=["POST"],
        ),
        # Wave 71.0 Track 9: Operations summary
        Route(
            "/api/v1/workspaces/{workspace_id:str}/operations/summary",
            get_operations_summary, methods=["GET"],
        ),
        # Wave 63 Track 6: Knowledge CRUD
        Route(
            "/api/v1/knowledge/{entry_id:str}",
            update_knowledge_entry, methods=["PUT"],
        ),
        Route(
            "/api/v1/knowledge/{entry_id:str}",
            delete_knowledge_entry, methods=["DELETE"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/knowledge",
            create_knowledge_entry, methods=["POST"],
        ),
        # Wave 63 Track 7: Workflow step CRUD
        Route(
            "/api/v1/workspaces/{workspace_id:str}/threads/{thread_id:str}/steps",
            list_workflow_steps, methods=["GET"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/threads/{thread_id:str}/steps",
            add_workflow_step, methods=["POST"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/threads/{thread_id:str}/steps/{step_index:int}",
            update_workflow_step, methods=["PUT"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/threads/{thread_id:str}/steps/{step_index:int}",
            delete_workflow_step, methods=["DELETE"],
        ),
        # Wave 66 T1: addon endpoints
        Route("/api/v1/addons", list_addons, methods=["GET"]),
        Route(
            "/api/v1/addons/{addon_name:str}/trigger",
            trigger_addon, methods=["POST"],
        ),
        Route(
            "/api/v1/addons/{addon_name:str}/toggle",
            toggle_addon, methods=["POST"],
        ),
        # Wave 69: thread plan read endpoint
        Route(
            "/api/v1/workspaces/{workspace_id:str}/threads/{thread_id:str}/plan",
            get_thread_plan, methods=["GET"],
        ),
        # Wave 70.0 Track 5: project plan read endpoint
        Route("/api/v1/project-plan", get_project_plan, methods=["GET"]),
        # Wave 66 T2: addon config surface
        Route(
            "/api/v1/addons/{addon_name:str}/config",
            get_addon_config, methods=["GET"],
        ),
        Route(
            "/api/v1/addons/{addon_name:str}/config",
            put_addon_config, methods=["PUT"],
        ),
        # Wave 74 B3: Queen context budget
        Route("/api/v1/queen-budget", get_queen_budget),
        # Wave 70.0 Track 9: autonomy status
        Route(
            "/api/v1/workspaces/{workspace_id:str}/autonomy-status",
            get_autonomy_status, methods=["GET"],
        ),
        # Wave 72 Track 10B: maintenance policy
        Route(
            "/api/v1/workspaces/{workspace_id:str}/maintenance-policy",
            get_maintenance_policy, methods=["GET"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/maintenance-policy",
            put_maintenance_policy, methods=["PUT"],
        ),
        # Wave 72 Track 10C: add model
        Route("/api/v1/models", add_model, methods=["POST"]),
        # Wave 74 Track 4: Queen tool stats
        Route("/api/v1/queen-tool-stats", get_queen_tool_stats, methods=["GET"]),
        # Wave 75 Track 3: billing status
        Route("/api/v1/billing/status", get_billing_status, methods=["GET"]),
        # Wave 77.5 A5: project context, project plan PUT, AI filesystem
        Route(
            "/api/v1/workspaces/{workspace_id:str}/project-context",
            get_project_context, methods=["GET"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/project-context",
            put_project_context, methods=["PUT"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/project-plan",
            put_project_plan, methods=["PUT"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/ai-filesystem",
            get_ai_filesystem, methods=["GET"],
        ),
        # Wave 79.5 C2: AI filesystem file preview + promote
        Route(
            "/api/v1/workspaces/{workspace_id:str}/ai-filesystem/file",
            get_ai_fs_file, methods=["GET"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/ai-filesystem/promote",
            post_ai_fs_promote, methods=["POST"],
        ),
        # Wave 81 Track A: project binding + project-file routes
        Route(
            "/api/v1/workspaces/{workspace_id:str}/project-binding",
            get_project_binding, methods=["GET"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/project-files",
            list_project_files, methods=["GET"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/project-files/{file_path:path}",
            preview_project_file, methods=["GET"],
        ),
        # Wave 82 Track A: planning history compare
        Route(
            "/api/v1/workspaces/{workspace_id:str}/planning-history",
            get_planning_history, methods=["GET"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/validate-reviewed-plan",
            post_validate_reviewed_plan, methods=["POST"],
        ),
        # Wave 83 Track B: plan patterns
        Route(
            "/api/v1/workspaces/{workspace_id:str}/plan-patterns",
            list_plan_patterns, methods=["GET"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/plan-patterns",
            create_plan_pattern, methods=["POST"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/plan-patterns/{pattern_id:str}",
            get_plan_pattern, methods=["GET"],
        ),
    ]
