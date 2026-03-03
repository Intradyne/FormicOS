"""
FormicOS v0.7.9 -- V1 Colony Routes

All colony CRUD, lifecycle actions, runtime views, results, timeline, export.
Also includes the V1 WebSocket endpoint.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response, StreamingResponse

from src.api.callbacks import make_ws_callbacks_v1
from src.api.helpers import (
    api_error_v1,
    build_colony_result_v1,
    build_colony_state_v1,
    check_colony_ownership,
    event_envelope,
    safe_serialize,
)
from src.auth import ClientAPIKey, get_current_client
from src.colony_manager import ColonyManager, ColonyNotFoundError, InvalidTransitionError
from src.models import (
    AgentConfig,
    ColonyConfig,
    ColonyCreateRequest,
    ColonyReuseRequest,
    ExtendRequestV1,
    InterveneRequest,
)
from src.worker import WorkerManager

logger = logging.getLogger("formicos.server")

router = APIRouter()


# -- Colony CRUD --

@router.get("/colonies")
async def v1_list_colonies(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    client: ClientAPIKey | None = Depends(get_current_client),
):
    cm: ColonyManager = request.app.state.colony_manager
    all_colonies = cm.get_all()
    if client is not None:
        all_colonies = [
            c for c in all_colonies
            if c.client_id == client.client_id
        ]
    page = all_colonies[offset:offset + limit]
    return {
        "items": [safe_serialize(c) for c in page],
        "total": len(all_colonies),
        "limit": limit,
        "offset": offset,
    }


@router.post("/colonies")
async def v1_create_colony(
    body: ColonyCreateRequest,
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    app = request.app
    cm: ColonyManager = app.state.colony_manager
    client_id = client.client_id if client else None

    if body.colony_id and body.colony_id.strip():
        candidate = re.sub(r"[^a-zA-Z0-9._-]+", "-", body.colony_id.strip()).strip("-").lower()
        colony_id = candidate or (body.task.lower().replace(" ", "-")[:20] + f"-{uuid.uuid4().hex[:6]}")
    else:
        colony_id = body.task.lower().replace(" ", "-")[:20] + f"-{uuid.uuid4().hex[:6]}"

    agent_configs = []
    if body.agents:
        for a in body.agents:
            agent_configs.append(AgentConfig(
                agent_id=a.agent_id or f"{a.caste}_{uuid.uuid4().hex[:6]}",
                caste=a.caste,
                model_override=a.model_override,
                subcaste_tier=a.subcaste_tier,
            ))
    else:
        for caste in ("manager", "architect", "coder"):
            agent_configs.append(AgentConfig(
                agent_id=f"{caste}_{uuid.uuid4().hex[:6]}",
                caste=caste,
            ))

    colony_config = ColonyConfig(
        colony_id=colony_id,
        task=body.task,
        agents=agent_configs,
        max_rounds=body.max_rounds,
        webhook_url=body.webhook_url,
        budget_constraints=body.budget_constraints,
        is_test_flight=body.is_test_flight,
        voting_nodes=body.voting_nodes,
    )

    try:
        info = await cm.create(
            colony_config, origin="api", client_id=client_id,
        )

        # Ingest injected documents into RAG (v0.7.5)
        docs_ingested = 0
        if body.injected_documents:
            docs_ingested = await cm.ingest_documents(
                colony_id, body.injected_documents,
            )

        # Emit colony.spawned (v0.7.3)
        ws_manager_v1 = app.state.ws_manager_v1
        ws_manager = app.state.ws_manager
        await ws_manager_v1.emit(event_envelope(
            "colony.spawned", colony_id,
            {"status": "created", "origin": "api", "client_id": client_id},
        ))
        await ws_manager.broadcast({
            "type": "colony_spawned", "colony_id": colony_id,
            "status": "created", "origin": "api", "client_id": client_id,
        })

        # Queue-based headless execution (v0.7.6)
        queued = False
        if body.webhook_url:
            try:
                await cm.enqueue(colony_id)
                wm: WorkerManager = app.state.worker_manager
                wm.enqueue(
                    colony_id=colony_id,
                    client_id=client_id,
                    priority=body.priority,
                    callbacks_factory=lambda cid: make_ws_callbacks_v1(cid, app),
                )
                queued = True
            except Exception as enqueue_exc:
                logger.warning(
                    "Enqueue failed for colony '%s': %s",
                    colony_id, enqueue_exc,
                )

        result = safe_serialize(info)
        result["docs_ingested"] = docs_ingested
        result["queued"] = queued

        if queued:
            return JSONResponse(
                content=result, status_code=202,
            )
        return result
    except Exception as exc:
        return api_error_v1(409, "COLONY_CREATE_FAILED", str(exc))


@router.get("/colonies/{colony_id}")
async def v1_get_colony(
    colony_id: str,
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    cm: ColonyManager = request.app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err
    try:
        state = build_colony_state_v1(colony_id, cm)
        return state.model_dump()
    except (ColonyNotFoundError, KeyError):
        return api_error_v1(404, "COLONY_NOT_FOUND", f"Colony '{colony_id}' not found")


@router.get("/colonies/{colony_id}/metrics")
async def v1_colony_metrics(
    colony_id: str,
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    cm: ColonyManager = request.app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err
    try:
        state = cm._colonies.get(colony_id)
        if state is None:
            return api_error_v1(404, "COLONY_NOT_FOUND", f"Colony '{colony_id}' not found")
        orch = state.orchestrator
        if orch is None or not hasattr(orch, "_metrics"):
            return {"colony_id": colony_id, "metrics": None, "note": "No metrics available"}
        return orch._metrics.get_colony_metrics().model_dump()
    except Exception as exc:
        return api_error_v1(500, "METRICS_FETCH_FAILED", str(exc))


@router.delete("/colonies/{colony_id}")
async def v1_destroy_colony(
    colony_id: str,
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    cm: ColonyManager = request.app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err
    try:
        archive_path = await cm.destroy(colony_id)
        return {"status": "destroyed", "colony_id": colony_id, "archive": str(archive_path)}
    except ColonyNotFoundError:
        return api_error_v1(404, "COLONY_NOT_FOUND", f"Colony '{colony_id}' not found")
    except Exception as exc:
        return api_error_v1(500, "COLONY_DESTROY_FAILED", str(exc))


# -- Colony Lifecycle --

@router.post("/colonies/{colony_id}/start")
async def v1_start_colony(
    colony_id: str,
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    app = request.app
    cm: ColonyManager = app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err
    try:
        callbacks = make_ws_callbacks_v1(colony_id, app)
        await cm.start(colony_id, callbacks=callbacks)
        return {"status": "started", "colony_id": colony_id}
    except ColonyNotFoundError:
        return api_error_v1(404, "COLONY_NOT_FOUND", f"Colony '{colony_id}' not found")
    except InvalidTransitionError as exc:
        return api_error_v1(409, "INVALID_TRANSITION", str(exc))
    except Exception as exc:
        return api_error_v1(500, "COLONY_START_FAILED", str(exc))


@router.post("/colonies/{colony_id}/pause")
async def v1_pause_colony(
    colony_id: str,
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    cm: ColonyManager = request.app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err
    try:
        session_file = await cm.pause(colony_id)
        return {"status": "paused", "colony_id": colony_id, "session_file": str(session_file)}
    except ColonyNotFoundError:
        return api_error_v1(404, "COLONY_NOT_FOUND", f"Colony '{colony_id}' not found")
    except InvalidTransitionError as exc:
        return api_error_v1(409, "INVALID_TRANSITION", str(exc))
    except Exception as exc:
        return api_error_v1(500, "COLONY_PAUSE_FAILED", str(exc))


@router.post("/colonies/{colony_id}/resume")
async def v1_resume_colony(
    colony_id: str,
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    app = request.app
    cm: ColonyManager = app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err
    try:
        callbacks = make_ws_callbacks_v1(colony_id, app)
        await cm.resume(colony_id, callbacks=callbacks)
        return {"status": "resumed", "colony_id": colony_id}
    except ColonyNotFoundError:
        return api_error_v1(404, "COLONY_NOT_FOUND", f"Colony '{colony_id}' not found")
    except InvalidTransitionError as exc:
        return api_error_v1(409, "INVALID_TRANSITION", str(exc))
    except Exception as exc:
        return api_error_v1(500, "COLONY_RESUME_FAILED", str(exc))


@router.post("/colonies/{colony_id}/extend")
async def v1_extend_colony(
    colony_id: str,
    body: ExtendRequestV1,
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    cm: ColonyManager = request.app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err
    try:
        new_max = await cm.extend(colony_id, body.rounds, body.hint)
        return {"colony_id": colony_id, "new_max_rounds": new_max}
    except ColonyNotFoundError:
        return api_error_v1(404, "COLONY_NOT_FOUND", f"Colony '{colony_id}' not found")
    except Exception as exc:
        return api_error_v1(500, "COLONY_EXTEND_FAILED", str(exc))


@router.post("/colonies/{colony_id}/reuse")
async def v1_reuse_colony(
    colony_id: str,
    body: ColonyReuseRequest,
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    app = request.app
    cm: ColonyManager = app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err
    try:
        info = await cm.reuse(
            colony_id=colony_id,
            task=body.task,
            max_rounds=body.max_rounds,
            preserve_history=body.preserve_history,
            clear_workspace=body.clear_workspace,
        )
        started = False
        if body.start_immediately:
            callbacks = make_ws_callbacks_v1(colony_id, app)
            await cm.start(colony_id, callbacks=callbacks)
            started = True
        return {
            "status": "reused_and_started" if started else "reused",
            "colony_id": colony_id,
            "started": started,
            "task": info.task,
            "max_rounds": info.max_rounds,
        }
    except ColonyNotFoundError:
        return api_error_v1(404, "COLONY_NOT_FOUND", f"Colony '{colony_id}' not found")
    except (InvalidTransitionError, ValueError) as exc:
        return api_error_v1(409, "INVALID_TRANSITION", str(exc))
    except Exception as exc:
        return api_error_v1(500, "COLONY_REUSE_FAILED", str(exc))


@router.post("/colonies/{colony_id}/intervene")
async def v1_intervene_colony(
    colony_id: str,
    body: InterveneRequest,
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    app = request.app
    cm: ColonyManager = app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err
    try:
        ctx_int = cm.get_context(colony_id)
    except ColonyNotFoundError:
        return api_error_v1(404, "COLONY_NOT_FOUND", f"Colony '{colony_id}' not found")
    await ctx_int.set("colony", "operator_hint", body.hint)
    env = event_envelope(
        "governance.decision", colony_id,
        {"type": "intervention", "hint": body.hint},
    )
    ws_manager_v1 = app.state.ws_manager_v1
    await ws_manager_v1.emit(env)
    return {"colony_id": colony_id, "hint": body.hint, "status": "injected"}


# -- Colony Runtime Views --

@router.get("/colonies/{colony_id}/topology")
async def v1_get_topology(
    colony_id: str,
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    cm: ColonyManager = request.app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err
    try:
        ctx_topo = cm.get_context(colony_id)
    except (ColonyNotFoundError, KeyError):
        return api_error_v1(404, "COLONY_NOT_FOUND", f"Colony '{colony_id}' not found")
    topo = ctx_topo.get("colony", "topology")
    if topo is None:
        return {"edges": [], "execution_order": [], "density": 0.0}
    return safe_serialize(topo)


@router.get("/colonies/{colony_id}/topology/history")
async def v1_get_topology_history(
    colony_id: str,
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    cm: ColonyManager = request.app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err
    try:
        ctx_th = cm.get_context(colony_id)
    except (ColonyNotFoundError, KeyError):
        return api_error_v1(404, "COLONY_NOT_FOUND", f"Colony '{colony_id}' not found")
    history = ctx_th.get("colony", "topology_history", [])
    return safe_serialize(history)


@router.get("/colonies/{colony_id}/decisions")
async def v1_get_decisions(
    colony_id: str,
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    cm: ColonyManager = request.app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err
    try:
        ctx_d = cm.get_context(colony_id)
    except (ColonyNotFoundError, KeyError):
        return api_error_v1(404, "COLONY_NOT_FOUND", f"Colony '{colony_id}' not found")
    decisions = ctx_d.get_decisions()
    return [safe_serialize(d) for d in decisions]


@router.get("/colonies/{colony_id}/episodes")
async def v1_get_episodes(
    colony_id: str,
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    cm: ColonyManager = request.app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err
    try:
        ctx_e = cm.get_context(colony_id)
    except (ColonyNotFoundError, KeyError):
        return api_error_v1(404, "COLONY_NOT_FOUND", f"Colony '{colony_id}' not found")
    episodes = ctx_e.get_episodes()
    return [safe_serialize(e) for e in episodes]


@router.get("/colonies/{colony_id}/tkg")
async def v1_get_tkg(
    colony_id: str,
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    cm: ColonyManager = request.app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err
    try:
        ctx_tkg = cm.get_context(colony_id)
    except (ColonyNotFoundError, KeyError):
        return api_error_v1(404, "COLONY_NOT_FOUND", f"Colony '{colony_id}' not found")
    tuples = ctx_tkg.query_tkg()
    return [safe_serialize(t) for t in tuples]


# -- Timeline & Export (v0.7.7) --

@router.get("/colonies/{colony_id}/timeline")
async def v1_get_timeline(
    colony_id: str,
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    """Return timeline spans for Gantt chart visualization."""
    cm: ColonyManager = request.app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err
    try:
        ctx_tl = cm.get_context(colony_id)
    except (ColonyNotFoundError, KeyError):
        return api_error_v1(404, "COLONY_NOT_FOUND", f"Colony '{colony_id}' not found")
    spans = ctx_tl.get("colony", "timeline_spans", [])
    return {"colony_id": colony_id, "spans": spans}


@router.get("/colonies/{colony_id}/export")
async def v1_export_colony(
    colony_id: str,
    request: Request,
    format: str = Query(default="jsonl"),
    scrub: bool = Query(default=False),
    client: ClientAPIKey | None = Depends(get_current_client),
):
    """DataClaw export: JSONL, ShareGPT, or Zip archive."""
    if format not in ("jsonl", "sharegpt", "zip"):
        return api_error_v1(400, "INVALID_FORMAT", f"Unsupported format: {format}")
    cm: ColonyManager = request.app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err
    try:
        ctx_ex = cm.get_context(colony_id)
    except (ColonyNotFoundError, KeyError):
        return api_error_v1(404, "COLONY_NOT_FOUND", f"Colony '{colony_id}' not found")

    # Gather colony data
    episodes = [safe_serialize(e) for e in ctx_ex.get_episodes()]
    decisions = [safe_serialize(d) for d in ctx_ex.get_decisions()]
    timeline = ctx_ex.get("colony", "timeline_spans", [])
    epoch_summaries = [safe_serialize(es) for es in ctx_ex.get_epoch_summaries()]

    if scrub:
        for ep in episodes:
            ep.pop("agent_outputs", None)
        for d in decisions:
            d.pop("recommendations", None)

    if format == "sharegpt":
        conversations = []
        for ep in episodes:
            conversations.append({
                "conversations": [
                    {"from": "system", "value": ep.get("goal", "")},
                    {"from": "assistant", "value": ep.get("summary", "")},
                ],
                "round_num": ep.get("round_num", 0),
            })
        lines = [json.dumps(c) for c in conversations]
        content = "\n".join(lines)
        headers = {
            "Content-Disposition": f'attachment; filename="{colony_id}-sharegpt.jsonl"',
        }
        return Response(content=content, media_type="application/x-ndjson", headers=headers)

    elif format == "zip":
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("episodes.json", json.dumps(episodes, indent=2))
            zf.writestr("decisions.json", json.dumps(decisions, indent=2))
            zf.writestr("timeline.json", json.dumps(timeline, indent=2))
            zf.writestr("epoch_summaries.json", json.dumps(epoch_summaries, indent=2))
        buf.seek(0)
        headers = {
            "Content-Disposition": f'attachment; filename="{colony_id}-export.zip"',
        }
        return StreamingResponse(buf, media_type="application/zip", headers=headers)

    else:  # jsonl
        records = []
        for ep in episodes:
            records.append({"type": "episode", **ep})
        for d in decisions:
            records.append({"type": "decision", **d})
        for s in timeline:
            records.append({"type": "timeline_span", **(s if isinstance(s, dict) else safe_serialize(s))})
        for es in epoch_summaries:
            records.append({"type": "epoch_summary", **es})
        content = "\n".join(json.dumps(r) for r in records)
        headers = {
            "Content-Disposition": f'attachment; filename="{colony_id}-export.jsonl"',
        }
        return Response(content=content, media_type="application/x-ndjson", headers=headers)


# -- Results --

@router.get("/colonies/{colony_id}/results")
async def v1_get_results(
    colony_id: str,
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    cm: ColonyManager = request.app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err
    try:
        result = build_colony_result_v1(colony_id, cm)
        return result.model_dump()
    except (ColonyNotFoundError, KeyError):
        return api_error_v1(404, "COLONY_NOT_FOUND", f"Colony '{colony_id}' not found")


@router.get("/colonies/{colony_id}/results/files")
async def v1_get_result_files(
    colony_id: str,
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    cm: ColonyManager = request.app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err
    ws_path = Path("./workspace") / colony_id
    if not ws_path.exists():
        return []
    return sorted(
        str(p.relative_to(ws_path)).replace("\\", "/")
        for p in ws_path.rglob("*") if p.is_file()
    )


# -- V1 WebSocket --

@router.websocket("/ws/events")
async def v1_ws_events(ws: WebSocket):
    app = ws.app
    ws_manager_v1 = app.state.ws_manager_v1
    await ws_manager_v1.connect(ws)
    try:
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_json(), timeout=60.0)
                msg_type = data.get("type") or data.get("action")
                if msg_type == "ping":
                    await ws.send_json({"type": "pong"})
                elif msg_type == "subscribe":
                    cid = data.get("colony_id")
                    ws_manager_v1.subscribe(ws, cid)
                    await ws.send_json({"type": "subscribed", "colony_id": cid})
                elif msg_type == "unsubscribe":
                    cid = data.get("colony_id")
                    ws_manager_v1.unsubscribe(ws, cid)
                    await ws.send_json({"type": "unsubscribed", "colony_id": cid})
            except asyncio.TimeoutError:
                try:
                    await ws.send_json({"type": "ping"})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        ws_manager_v1.disconnect(ws)
