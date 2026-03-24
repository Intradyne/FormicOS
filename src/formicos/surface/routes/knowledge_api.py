"""Unified knowledge REST API -- federated over both backends (Wave 27)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from starlette.responses import JSONResponse
from starlette.routing import Route

from formicos.surface.structured_error import KNOWN_ERRORS, to_http_error

if TYPE_CHECKING:
    from starlette.requests import Request

    from formicos.surface.knowledge_catalog import KnowledgeCatalog
    from formicos.surface.projections import ProjectionStore
    from formicos.surface.runtime import Runtime


def routes(
    *,
    knowledge_catalog: KnowledgeCatalog | None = None,
    runtime: Runtime | None = None,
    projections: ProjectionStore | None = None,
    **_unused: Any,
) -> list[Route]:
    """Build unified knowledge API routes."""

    def _err_response(err_key: str, **overrides: Any) -> JSONResponse:
        err = KNOWN_ERRORS[err_key]
        if overrides:
            err = err.model_copy(update=overrides)
        status, body, headers = to_http_error(err)
        return JSONResponse(body, status_code=status, headers=headers)

    async def list_knowledge(request: Request) -> JSONResponse:
        if knowledge_catalog is None:
            return _err_response("KNOWLEDGE_CATALOG_UNAVAILABLE")
        source = request.query_params.get("source", "")
        ctype = request.query_params.get("type", "")
        workspace = request.query_params.get("workspace", "")
        source_colony_id = request.query_params.get("source_colony_id", "")
        sub_type = request.query_params.get("sub_type", "")
        try:
            limit = max(1, min(int(request.query_params.get("limit", "50")), 200))
        except ValueError:
            return _err_response("LIMIT_INVALID")

        scope = request.query_params.get("scope", "")
        items, total = await knowledge_catalog.list_all(
            source_system=source, canonical_type=ctype,
            workspace_id=workspace,
            source_colony_id=source_colony_id,
            limit=limit,
        )
        # Wave 50: scope filter (e.g. scope=global from knowledge-browser)
        if scope:
            items = [it for it in items if it.get("scope") == scope]
            total = len(items)
        # Client-side sub_type filter (catalog doesn't natively support it yet)
        if sub_type:
            items = [it for it in items if it.get("sub_type") == sub_type]
            total = len(items)
        # Wave 55: enrich with usage data from projections
        if projections is not None:
            for it in items:
                usage = projections.knowledge_entry_usage.get(it.get("id", ""))
                it["usage_count"] = usage["count"] if usage else 0
                it["last_accessed"] = usage["last_accessed"] if usage else None
        return JSONResponse({"items": items, "total": total})

    async def search_knowledge(request: Request) -> JSONResponse:
        if knowledge_catalog is None:
            return _err_response("KNOWLEDGE_CATALOG_UNAVAILABLE")
        query = request.query_params.get("q", "")
        if not query:
            return _err_response("QUERY_REQUIRED")
        source = request.query_params.get("source", "")
        ctype = request.query_params.get("type", "")
        workspace = request.query_params.get("workspace", "")
        thread = request.query_params.get("thread", "")
        source_colony_id = request.query_params.get("source_colony_id", "")
        sub_type = request.query_params.get("sub_type", "")
        try:
            limit = max(1, min(int(request.query_params.get("limit", "10")), 50))
        except ValueError:
            return _err_response("LIMIT_INVALID")

        results = await knowledge_catalog.search(
            query=query, source_system=source, canonical_type=ctype,
            workspace_id=workspace,
            thread_id=thread,
            source_colony_id=source_colony_id,
            top_k=limit,
        )
        # Wave 50: scope filter (e.g. scope=global from knowledge-browser)
        scope = request.query_params.get("scope", "")
        if scope:
            results = [r for r in results if r.get("scope") == scope]
        if sub_type:
            results = [r for r in results if r.get("sub_type") == sub_type]
        # Wave 55: enrich with usage data from projections
        if projections is not None:
            for r in results:
                usage = projections.knowledge_entry_usage.get(r.get("id", ""))
                r["usage_count"] = usage["count"] if usage else 0
                r["last_accessed"] = usage["last_accessed"] if usage else None
        return JSONResponse({"results": results, "total": len(results)})

    async def get_knowledge_item(request: Request) -> JSONResponse:
        if knowledge_catalog is None:
            return _err_response("KNOWLEDGE_CATALOG_UNAVAILABLE")
        item_id = request.path_params["item_id"]
        item = await knowledge_catalog.get_by_id(item_id)
        if item is None:
            return _err_response("KNOWLEDGE_ITEM_NOT_FOUND")
        return JSONResponse(item)

    # Wave 29 C4: Promote thread→workspace or workspace→global (extended Wave 50)
    async def promote_entry(request: Request) -> JSONResponse:
        if projections is None or runtime is None:
            return _err_response("KNOWLEDGE_CATALOG_UNAVAILABLE")
        item_id = request.path_params["item_id"]
        entry = projections.memory_entries.get(item_id)
        if entry is None:
            return _err_response("KNOWLEDGE_ITEM_NOT_FOUND")

        # Wave 50: explicit target_scope parameter
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        target_scope = body.get("target_scope", "workspace") if body else "workspace"

        old_thread = entry.get("thread_id", "")
        current_scope = entry.get("scope", "thread" if old_thread else "workspace")

        from formicos.core.events import MemoryEntryScopeChanged  # noqa: PLC0415

        if target_scope == "global":
            # Wave 50: workspace→global promotion
            if current_scope == "global":
                return _err_response("ALREADY_WORKSPACE_WIDE")
            await runtime.emit_and_broadcast(MemoryEntryScopeChanged(
                seq=0,
                timestamp=datetime.now(UTC),
                address=f"{entry.get('workspace_id', '')}/{old_thread}",
                entry_id=item_id,
                old_thread_id=old_thread,
                new_thread_id="",
                workspace_id=entry.get("workspace_id", ""),
                new_workspace_id="",  # empty = global
            ))
            return JSONResponse({
                "promoted": True, "entry_id": item_id, "scope": "global",
            })

        # Default: thread→workspace promotion (original Wave 29 behavior)
        if not old_thread:
            return _err_response("ALREADY_WORKSPACE_WIDE")

        await runtime.emit_and_broadcast(MemoryEntryScopeChanged(
            seq=0,
            timestamp=datetime.now(UTC),
            address=f"{entry.get('workspace_id', '')}/{old_thread}",
            entry_id=item_id,
            old_thread_id=old_thread,
            new_thread_id="",
            workspace_id=entry.get("workspace_id", ""),
        ))
        return JSONResponse({
            "promoted": True, "entry_id": item_id, "scope": "workspace",
        })

    # Wave 29 C5: Maintenance trigger (thin HTTP wrapper over ServiceRouter)
    async def query_service(request: Request) -> JSONResponse:
        if runtime is None:
            return _err_response("SERVICE_NOT_READY")
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return _err_response("INVALID_JSON")
        service_type = body.get("service_type", "")
        query_text = body.get("query", "")
        if not service_type or not query_text:
            return _err_response("MISSING_FIELD",
                                 message="service_type and query are required")

        cm = runtime.colony_manager
        if cm is None:
            return _err_response("COLONY_MANAGER_UNAVAILABLE")
        router = cm.service_router
        try:
            result = await router.query(
                service_type=service_type,
                query_text=query_text,
                sender_colony_id=None,
                timeout_s=30.0,
            )
            return JSONResponse({"result": result})
        except ValueError as exc:
            return _err_response("INVALID_SERVICE_TYPE", message=str(exc))
        except TimeoutError:
            return _err_response("SERVICE_TIMEOUT")

    # Wave 38: temporal edge history endpoint
    async def get_temporal_edges(request: Request) -> JSONResponse:
        """Return bi-temporal edge history for an entity.

        Surfaces when the system learned a relationship (transaction_time),
        when it was considered valid (valid_at), and when it was invalidated
        (invalid_at). Includes both current and historical edges.
        """
        if runtime is None:
            return _err_response("SERVICE_NOT_READY")
        entity_id = request.path_params["entity_id"]
        workspace = request.query_params.get("workspace", "")
        if not workspace:
            return _err_response("MISSING_FIELD", message="workspace is required")

        kg = getattr(runtime, "knowledge_graph", None)
        if kg is None:
            return _err_response("KNOWLEDGE_CATALOG_UNAVAILABLE",
                                 message="Knowledge graph not available")

        edges = await kg.get_neighbors(
            entity_id, workspace_id=workspace, include_invalidated=True,
        )
        # Annotate each edge with temporal classification
        for edge in edges:
            edge["temporal"] = {
                "transaction_time": edge.get("transaction_time", ""),
                "valid_from": edge.get("valid_at", ""),
                "valid_until": edge.get("invalid_at"),
                "is_current": edge.get("invalid_at") is None,
                "time_type_labels": {
                    "transaction_time": "When the system learned this",
                    "valid_from": "When this was considered true",
                    "valid_until": "When this stopped being true",
                },
            }
        return JSONResponse({
            "entity_id": entity_id,
            "edges": edges,
            "total": len(edges),
            "current_count": sum(1 for e in edges if e.get("invalid_at") is None),
            "invalidated_count": sum(
                1 for e in edges if e.get("invalid_at") is not None
            ),
        })

    # ------------------------------------------------------------------
    # Wave 39: Operator co-authorship endpoints (ADR-049)
    # ------------------------------------------------------------------

    async def operator_action(request: Request) -> JSONResponse:
        """Apply an operator editorial overlay (pin/unpin/mute/unmute/invalidate/reinstate)."""
        if runtime is None:
            return _err_response("SERVICE_NOT_READY")
        item_id = request.path_params["item_id"]
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return _err_response("INVALID_JSON")

        action = body.get("action", "")
        valid_actions = {"pin", "unpin", "mute", "unmute", "invalidate", "reinstate"}
        if action not in valid_actions:
            return _err_response(
                "MISSING_FIELD",
                message=f"action must be one of {sorted(valid_actions)}",
            )

        actor = body.get("actor", "operator")
        reason = body.get("reason", "")
        workspace_id = body.get("workspace_id", "")

        from formicos.core.events import KnowledgeEntryOperatorAction  # noqa: PLC0415

        await runtime.emit_and_broadcast(KnowledgeEntryOperatorAction(
            seq=0,
            timestamp=datetime.now(UTC),
            address=f"{workspace_id}/{item_id}",
            entry_id=item_id,
            workspace_id=workspace_id,
            action=action,
            actor=actor,
            reason=reason,
        ))
        return JSONResponse({"ok": True, "entry_id": item_id, "action": action})

    async def annotate_entry(request: Request) -> JSONResponse:
        """Add an operator annotation to a knowledge entry."""
        if runtime is None:
            return _err_response("SERVICE_NOT_READY")
        item_id = request.path_params["item_id"]
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return _err_response("INVALID_JSON")

        annotation_text = body.get("annotation_text", "")
        if not annotation_text:
            return _err_response("MISSING_FIELD", message="annotation_text is required")

        actor = body.get("actor", "operator")
        tag = body.get("tag", "")
        workspace_id = body.get("workspace_id", "")

        from formicos.core.events import KnowledgeEntryAnnotated  # noqa: PLC0415

        await runtime.emit_and_broadcast(KnowledgeEntryAnnotated(
            seq=0,
            timestamp=datetime.now(UTC),
            address=f"{workspace_id}/{item_id}",
            entry_id=item_id,
            workspace_id=workspace_id,
            annotation_text=annotation_text,
            tag=tag,
            actor=actor,
        ))
        return JSONResponse({"ok": True, "entry_id": item_id, "annotated": True})

    async def get_entry_annotations(request: Request) -> JSONResponse:
        """Get all operator annotations for a knowledge entry."""
        if projections is None:
            return _err_response("KNOWLEDGE_CATALOG_UNAVAILABLE")
        item_id = request.path_params["item_id"]
        overlays = projections.operator_overlays
        annotations = overlays.annotations.get(item_id, [])
        return JSONResponse({
            "entry_id": item_id,
            "annotations": [
                {
                    "annotation_text": a.annotation_text,
                    "tag": a.tag,
                    "actor": a.actor,
                    "timestamp": a.timestamp,
                }
                for a in annotations
            ],
            "total": len(annotations),
        })

    async def get_entry_overlay_status(request: Request) -> JSONResponse:
        """Get operator overlay status for a knowledge entry."""
        if projections is None:
            return _err_response("KNOWLEDGE_CATALOG_UNAVAILABLE")
        item_id = request.path_params["item_id"]
        overlays = projections.operator_overlays
        return JSONResponse({
            "entry_id": item_id,
            "pinned": item_id in overlays.pinned_entries,
            "muted": item_id in overlays.muted_entries,
            "invalidated": item_id in overlays.invalidated_entries,
            "annotation_count": len(overlays.annotations.get(item_id, [])),
        })

    async def override_config_suggestion(request: Request) -> JSONResponse:
        """Record an operator override of a system configuration suggestion."""
        if runtime is None:
            return _err_response("SERVICE_NOT_READY")
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return _err_response("INVALID_JSON")

        workspace_id = body.get("workspace_id", "")
        category = body.get("suggestion_category", "")
        original = body.get("original_config")
        overridden = body.get("overridden_config")
        if not category or original is None or overridden is None:
            return _err_response(
                "MISSING_FIELD",
                message="suggestion_category, original_config, and overridden_config required",
            )

        actor = body.get("actor", "operator")
        reason = body.get("reason", "")

        from formicos.core.events import ConfigSuggestionOverridden  # noqa: PLC0415

        await runtime.emit_and_broadcast(ConfigSuggestionOverridden(
            seq=0,
            timestamp=datetime.now(UTC),
            address=workspace_id,
            workspace_id=workspace_id,
            suggestion_category=category,
            original_config=original,
            overridden_config=overridden,
            reason=reason,
            actor=actor,
        ))
        return JSONResponse({"ok": True, "workspace_id": workspace_id, "overridden": True})

    return [
        Route("/api/v1/knowledge", list_knowledge, methods=["GET"]),
        Route(
            "/api/v1/knowledge/search",
            search_knowledge, methods=["GET"],
        ),
        Route(
            "/api/v1/knowledge/{item_id:str}/promote",
            promote_entry, methods=["POST"],
        ),
        Route(
            "/api/v1/knowledge/{item_id:str}",
            get_knowledge_item, methods=["GET"],
        ),
        Route(
            "/api/v1/knowledge/graph/{entity_id:str}/temporal",
            get_temporal_edges, methods=["GET"],
        ),
        Route(
            "/api/v1/services/query",
            query_service, methods=["POST"],
        ),
        # Wave 39: Operator co-authorship endpoints (ADR-049)
        Route(
            "/api/v1/knowledge/{item_id:str}/action",
            operator_action, methods=["POST"],
        ),
        Route(
            "/api/v1/knowledge/{item_id:str}/annotate",
            annotate_entry, methods=["POST"],
        ),
        Route(
            "/api/v1/knowledge/{item_id:str}/annotations",
            get_entry_annotations, methods=["GET"],
        ),
        Route(
            "/api/v1/knowledge/{item_id:str}/overlay",
            get_entry_overlay_status, methods=["GET"],
        ),
        Route(
            "/api/v1/knowledge/config-override",
            override_config_suggestion, methods=["POST"],
        ),
    ]
