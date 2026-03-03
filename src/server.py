"""
FormicOS v0.6.0 -- API Gateway (server.py)

Stateless HTTP + WebSocket server that exposes colony operations to the
dashboard and external clients.

Architecture:
  - FastAPI + uvicorn
  - Lifespan async context manager (NOT @app.on_event)
  - create_app() factory pattern -- lifespan variables must be params
  - Static files served from src/web/
  - Structured error responses: {error_code, error_detail, request_id}

Key patterns:
  - All backend services are initialised in the lifespan and stored on app.state
  - GPU polling via asyncio.to_thread (non-blocking nvidia-smi)
  - VRAM sanity check: cascading /1024 if used > total * 2
  - WebSocket keepalive: 25s client-side ping
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiohttp


from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, APIRouter, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from src.approval import ApprovalGate
from src.audit import AuditLogger
from src.colony_manager import ColonyManager, ColonyNotFoundError, InvalidTransitionError
from src.context import AsyncContextTree
from src.mcp_client import MCPGatewayClient
from src.model_registry import ModelRegistry
from src.models import (
    AgentConfig,
    ApproveRequest,
    CasteConfig,
    CasteCreateRequest,
    CasteUpdateRequest,
    ColonyConfig,
    ColonyCreateRequest,  # re-exported for tests
    ColonyStatus,
    ExtendRequest,
    FormicOSConfig,
    FormicOSError,
    InterveneRequest,
    ProblemDetail,
    PromptUpdateRequest,
    RunRequest,
    SkillCreateRequest,  # re-exported for tests
    SkillUpdateRequest,
    SubcasteMapEntry,
    SuggestTeamRequest,
    SUGGESTED_FIXES,
    load_config,
)
from src.session import SessionManager
from src.skill_bank import SkillBank
from src.auth import APIKeyStore, ClientAPIKey, get_current_client
from src.webhook import WebhookDispatcher
from src.worker import (
    WorkerManager,
    DEFAULT_MAX_CONCURRENT,
    DEFAULT_VRAM_THRESHOLD_MB,
)

logger = logging.getLogger("formicos.server")

# Enable INFO-level logging for FormicOS modules so phase/round progress is visible
logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")
logging.getLogger("formicos").setLevel(logging.INFO)

VERSION = "0.9.0"

# ── GPU polling interval ──────────────────────────────────────────────────

GPU_POLL_INTERVAL_SECONDS = 10


# ── Request / Response Models ────────────────────────────────────────────
# v0.7.9: Moved to src/models.py. Re-exported via imports above.


# ── WebSocket Connection Manager ─────────────────────────────────────────
# v0.7.9: Moved to src/api/ws.py. Imported for backward compat + legacy routes.

from src.api.ws import ConnectionManager, ConnectionManagerV1  # noqa: E402


# ── GPU Polling ──────────────────────────────────────────────────────────


async def _poll_gpu() -> dict[str, Any]:
    """Read nvidia-smi and return VRAM stats.

    Runs nvidia-smi in a thread so the event loop is never blocked.
    Applies cascading /1024 correction if the driver returns unexpected
    units (seen on some Windows/RTX 5090 driver versions).
    """
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total,name",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(",")
            used, total = float(parts[0].strip()), float(parts[1].strip())
            name = parts[2].strip() if len(parts) > 2 else "Unknown"
            # Sanity check: some Windows/RTX drivers return unexpected units
            if used > total * 2:
                used /= 1024
            if used > total * 2:
                used /= 1024
            return {
                "used_gb": round(used / 1024, 2),
                "total_gb": round(total / 1024, 2),
                "name": name,
            }
    except Exception:
        pass
    return {"used_gb": 0, "total_gb": 0, "status": "unknown"}


# ── WS Callback Factory ─────────────────────────────────────────────────
# v0.7.9: Moved to src/api/callbacks.py. Imported for legacy routes.

from src.api.callbacks import make_ws_callbacks  # noqa: E402


# ── Context Tree Helper ──────────────────────────────────────────────────


def _active_ctx(app: FastAPI) -> AsyncContextTree:
    """Return the active colony's context tree, falling back to dashboard ctx."""
    cm: ColonyManager = app.state.colony_manager
    dashboard_ctx: AsyncContextTree = app.state.ctx
    colony_id = dashboard_ctx.get("colony", "colony_id")
    if colony_id:
        try:
            return cm.get_context(colony_id)
        except (ColonyNotFoundError, KeyError):
            pass
    return dashboard_ctx


# ── Error & Serialisation Helpers ────────────────────────────────────────
# v0.7.9: Canonical versions in src/api/helpers.py. Thin wrappers kept for
# legacy routes and backward-compat imports.

from src.api.helpers import (  # noqa: E402
    error_response as _error_response_impl,
    safe_serialize as _safe_serialize,
    event_envelope as _event_envelope,
    check_colony_ownership as _check_colony_ownership_impl,
)


def _error_response(
    status_code: int,
    error_code: str,
    detail: str,
    request_id: str | None = None,
) -> JSONResponse:
    """Build a structured error JSONResponse."""
    return _error_response_impl(status_code, error_code, detail, request_id)


def _check_legacy_ownership(
    colony_id: str,
    client: ClientAPIKey | None,
    cm: ColonyManager,
) -> JSONResponse | None:
    """Ownership check for legacy routes. Returns 403 JSONResponse or None."""
    return _check_colony_ownership_impl(colony_id, client, cm)


# ═══════════════════════════════════════════════════════════════════════════
# create_app() -- the factory that builds the FastAPI application
# ═══════════════════════════════════════════════════════════════════════════


def create_app(config: FormicOSConfig) -> FastAPI:
    """
    Build the FastAPI application with all routes and services.

    Parameters
    ----------
    config : FormicOSConfig
        Validated top-level configuration.  Must be passed explicitly so
        the lifespan closure can see it (it is NOT an ``app_factory()``
        local -- see V0.4.0 boot crash lesson).
    """
    ws_manager = ConnectionManager()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # ── Startup ──────────────────────────────────────────────
        logger.info("FormicOS v%s server starting", VERSION)

        # 0. Shared aiohttp session for LLM inference (v0.8.0)
        aio_connector = aiohttp.TCPConnector(
            limit=20,
            limit_per_host=10,
            keepalive_timeout=30,
            ttl_dns_cache=300,
        )
        aio_session = aiohttp.ClientSession(connector=aio_connector)
        app.state.aio_session = aio_session

        # 1. Model Registry
        model_registry = ModelRegistry(config, aio_session=aio_session)
        app.state.model_registry = model_registry

        # 2. Session Manager
        session_dir = Path(config.persistence.session_dir)
        session_manager = SessionManager(session_dir, config.persistence)
        app.state.session_manager = session_manager

        # 3. MCP Gateway Client (non-blocking, log on failure)
        mcp_client = MCPGatewayClient(config.mcp_gateway)
        app.state.mcp_client = mcp_client
        if config.mcp_gateway.enabled:
            try:
                await mcp_client.connect()
            except Exception as exc:
                logger.warning("MCP Gateway connection failed at startup: %s", exc)

        # 4. SkillBank
        skill_bank = SkillBank(
            storage_path=config.skill_bank.storage_file,
            config=config.skill_bank,
            embedder=None,  # embedder loaded separately if available
        )
        app.state.skill_bank = skill_bank

        # 5. Approval Gate
        approval_gate = ApprovalGate(
            required_actions=list(config.approval_required),
            timeout=300.0,
        )
        app.state.approval_gate = approval_gate

        # 6. Audit Logger
        audit_logger = AuditLogger(session_dir)
        app.state.audit_logger = audit_logger

        # 7. Routing embedder (MiniLM-L6-v2 for DyTopo)
        routing_embedder = None
        try:
            from sentence_transformers import SentenceTransformer
            routing_embedder = SentenceTransformer(
                config.embedding.routing_model
            )
            logger.info(
                "Routing embedder loaded: %s", config.embedding.routing_model
            )
        except ImportError:
            logger.warning(
                "sentence-transformers not installed — "
                "DyTopo routing will fall back to sorted-order execution"
            )
        except Exception as exc:
            logger.warning("Failed to load routing embedder: %s", exc)

        app.state.routing_embedder = routing_embedder

        # 7b. RAG Engine (BGE-M3 embeddings + Qdrant)
        from src.rag import RAGEngine
        rag_engine = RAGEngine(
            qdrant_config=config.qdrant,
            embedding_config=config.embedding,
        )
        app.state.rag_engine = rag_engine

        # 7c. Document Ingestor (async perception queue)
        from src.services.ingestion import AsyncDocumentIngestor
        ingestor = AsyncDocumentIngestor(
            rag_engine=rag_engine, max_concurrent=2,
        )
        app.state.ingestor = ingestor

        # 8. Webhook dispatcher (created early so ColonyManager can reference it)
        webhook_secret = os.environ.get("FORMICOS_WEBHOOK_SECRET")
        webhook_dispatcher = WebhookDispatcher(signing_secret=webhook_secret)
        await webhook_dispatcher.start()
        app.state.webhook_dispatcher = webhook_dispatcher

        # 8b. API Key store (in-memory, v0.7.4)
        app.state.api_key_store = APIKeyStore()

        # 9. Colony Manager
        colony_manager = ColonyManager(
            config=config,
            model_registry=model_registry,
            session_manager=session_manager,
            mcp_client=mcp_client,
            embedder=routing_embedder,
            skill_bank=skill_bank,
            audit_logger=audit_logger,
            approval_gate=approval_gate,
            webhook_dispatcher=webhook_dispatcher,
        )
        app.state.colony_manager = colony_manager

        # 9a. Worker Manager (auto-scaling compute pool, v0.7.6)
        worker_manager = WorkerManager(
            colony_manager=colony_manager,
            max_concurrent=DEFAULT_MAX_CONCURRENT,
            vram_threshold_mb=DEFAULT_VRAM_THRESHOLD_MB,
            webhook_dispatcher=webhook_dispatcher,
        )
        app.state.worker_manager = worker_manager

        # 9b. Shared dashboard context tree
        ctx = AsyncContextTree()
        app.state.ctx = ctx

        # Initialise system scope
        await ctx.set("system", "llm_model", config.inference.model)
        await ctx.set("system", "llm_endpoint", config.inference.endpoint)
        await ctx.set("system", "version", VERSION)

        # 10. SLO metrics store
        app.state.slo_metrics = {
            "colony_round_duration_ms": [],
            "event_dispatch_latency_ms": [],
            "llm_call_latency_ms": [],
            "tool_call_latency_ms": [],
            "session_save_duration_ms": [],
            "approval_wait_ms": [],
        }

        # 11. GPU polling background task
        async def _gpu_poll_loop() -> None:
            while True:
                stats = await _poll_gpu()
                await ctx.set("system", "gpu_stats", stats)
                app.state.gpu_stats = stats
                await asyncio.sleep(GPU_POLL_INTERVAL_SECONDS)

        gpu_task = asyncio.create_task(_gpu_poll_loop(), name="gpu-poll")
        app.state.gpu_task = gpu_task

        # 12. Worker Manager poll loop (v0.7.6)
        worker_poll_task = worker_manager.start()
        app.state.worker_poll_task = worker_poll_task

        # 13. Store config on app.state for route access
        app.state.config = config

        # 14. Durable execution: auto-resume crashed colonies (v0.8.0)
        try:
            resumed = await colony_manager.auto_resume_crashed()
            if resumed:
                logger.info(
                    "Auto-resumed %d crashed colonies: %s",
                    len(resumed), resumed,
                )
        except Exception as exc:
            logger.warning("Auto-resume check failed: %s", exc)

        # 15. Inbound MCP memory server daemon (v0.8.0)
        mcp_memory_proc = None
        if os.environ.get("FORMICOS_MCP_MEMORY_SERVER", "1") == "1":
            try:
                mcp_memory_proc = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "src.mcp.inbound_memory_server",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                app.state.mcp_memory_proc = mcp_memory_proc
                logger.info(
                    "Inbound MCP memory server started (PID %d)",
                    mcp_memory_proc.pid,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to start inbound MCP memory server: %s", exc,
                )

        logger.info("FormicOS v%s server ready", VERSION)

        yield

        # ── Shutdown ─────────────────────────────────────────────
        logger.info("FormicOS server shutting down")
        await worker_manager.stop()
        gpu_task.cancel()
        try:
            await gpu_task
        except asyncio.CancelledError:
            pass

        if mcp_client.connected:
            await mcp_client.disconnect()

        await webhook_dispatcher.stop()

        if mcp_memory_proc and mcp_memory_proc.returncode is None:
            mcp_memory_proc.terminate()
            try:
                await asyncio.wait_for(mcp_memory_proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                mcp_memory_proc.kill()

        await audit_logger.flush()
        await audit_logger.close()

        # Close shared aiohttp session (v0.8.0)
        await aio_session.close()

        logger.info("FormicOS server stopped")

    app = FastAPI(
        title="FormicOS",
        version=VERSION,
        lifespan=lifespan,
    )

    # Store ws_manager on app.state immediately (before lifespan)
    # so route modules can access it even in test mode
    app.state.ws_manager = ws_manager

    # ── Exception handlers ───────────────────────────────────────────

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return _error_response(
            status_code=exc.status_code,
            error_code=f"HTTP_{exc.status_code}",
            detail=str(exc.detail),
        )

    @app.exception_handler(FormicOSError)
    async def formicos_error_handler(request: Request, exc: FormicOSError):
        logger.warning("FormicOSError: %s %s — %s", exc.status, exc.code, exc.message)
        body = ProblemDetail(
            type=f"https://formicos.dev/errors/{exc.code.lower().replace('_', '-')}",
            title=exc.code.replace("_", " ").title(),
            status=exc.status,
            detail=exc.message,
            instance=f"urn:formicos:request:{uuid.uuid4()}",
            suggested_fix=exc.suggested_fix or SUGGESTED_FIXES.get(exc.code),
            error_code=exc.code,
        )
        return JSONResponse(
            status_code=exc.status,
            content=body.model_dump(exclude_none=True),
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception: %s", exc)
        return _error_response(
            status_code=500,
            error_code="INTERNAL_ERROR",
            detail=str(exc),
        )

    # ══════════════════════════════════════════════════════════════════
    # REST Endpoints
    # ══════════════════════════════════════════════════════════════════

    # ── System ───────────────────────────────────────────────────────

    @app.get("/api/system")
    async def get_system():
        gpu = getattr(app.state, "gpu_stats", {"status": "unknown"})
        ctx: AsyncContextTree = app.state.ctx
        return {
            "version": VERSION,
            "llm_model": ctx.get("system", "llm_model"),
            "llm_endpoint": ctx.get("system", "llm_endpoint"),
            "gpu": gpu,
            "vram_budget": app.state.model_registry.get_vram_budget(),
        }

    # ── Colony State (read-only) ─────────────────────────────────────

    @app.get("/api/colony")
    async def get_colony():
        ctx = _active_ctx(app)
        colony_id = ctx.get("colony", "colony_id")

        # List workspace files for this colony (normalize to forward slashes)
        workspace_files: list[str] = []
        if colony_id:
            ws = Path("./workspace") / colony_id
            if ws.exists():
                workspace_files = sorted(
                    str(p.relative_to(ws)).replace("\\", "/")
                    for p in ws.rglob("*") if p.is_file()
                )

        return {
            "task": ctx.get("colony", "task"),
            "agents": ctx.get("colony", "agents", []),
            "round": ctx.get("colony", "round", 0),
            "status": ctx.get("colony", "status"),
            "colony_id": colony_id,
            "max_rounds": ctx.get("colony", "max_rounds"),
            "final_answer": ctx.get("colony", "final_answer"),
            "teams": ctx.get("colony", "teams", []),
            "workspace_files": workspace_files,
        }

    @app.get("/api/topology")
    async def get_topology():
        ctx = _active_ctx(app)
        topo = ctx.get("colony", "topology")
        if topo is None:
            return {"edges": [], "execution_order": [], "density": 0.0}
        return _safe_serialize(topo)

    @app.get("/api/topology/history")
    async def get_topology_history():
        ctx = _active_ctx(app)
        history = ctx.get("colony", "topology_history", [])
        return _safe_serialize(history)

    @app.get("/api/decisions")
    async def get_decisions():
        ctx = _active_ctx(app)
        decisions = ctx.get_decisions()
        return [_safe_serialize(d) for d in decisions]

    @app.get("/api/episodes")
    async def get_episodes():
        ctx = _active_ctx(app)
        episodes = ctx.get_episodes()
        return [_safe_serialize(e) for e in episodes]

    @app.get("/api/tkg")
    async def get_tkg():
        ctx = _active_ctx(app)
        tuples = ctx.query_tkg()
        return [_safe_serialize(t) for t in tuples]

    @app.get("/api/epochs")
    async def get_epochs():
        ctx = _active_ctx(app)
        summaries = ctx.get_epoch_summaries()
        return [_safe_serialize(s) for s in summaries]

    # ── Supercolony Operations ───────────────────────────────────────

    @app.get("/api/supercolony")
    async def get_supercolony(
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        cm: ColonyManager = app.state.colony_manager
        all_colonies = cm.get_all()
        page = all_colonies[offset:offset + limit]
        return {
            "items": [_safe_serialize(c) for c in page],
            "total": len(all_colonies),
            "limit": limit,
            "offset": offset,
        }

    @app.post("/api/colony/{colony_id}/create")
    async def create_colony(
        colony_id: str,
        body: ColonyCreateRequest,
        client: ClientAPIKey | None = Depends(get_current_client),
    ):
        cm: ColonyManager = app.state.colony_manager

        # Build agent configs from body or defaults
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
            # Default: manager + architect + coder (minimum viable team)
            agent_configs.append(AgentConfig(
                agent_id=f"manager_{uuid.uuid4().hex[:6]}",
                caste="manager",
            ))
            agent_configs.append(AgentConfig(
                agent_id=f"architect_{uuid.uuid4().hex[:6]}",
                caste="architect",
            ))
            agent_configs.append(AgentConfig(
                agent_id=f"coder_{uuid.uuid4().hex[:6]}",
                caste="coder",
            ))

        colony_config = ColonyConfig(
            colony_id=colony_id,
            task=body.task,
            agents=agent_configs,
            max_rounds=body.max_rounds,
        )

        client_id = client.client_id if client else None

        try:
            info = await cm.create(colony_config, origin="ui", client_id=client_id)

            # Emit colony.spawned (v0.7.3)
            await ws_manager_v1.emit(_event_envelope(
                "colony.spawned", colony_id,
                {"status": "created", "origin": "ui", "client_id": client_id},
            ))
            await ws_manager.broadcast({
                "type": "colony_spawned", "colony_id": colony_id,
                "status": "created", "origin": "ui", "client_id": client_id,
            })

            return _safe_serialize(info)
        except Exception as exc:
            return _error_response(409, "COLONY_CREATE_FAILED", str(exc))

    @app.post("/api/colony/{colony_id}/start")
    async def start_colony(colony_id: str, client: ClientAPIKey | None = Depends(get_current_client)):
        cm: ColonyManager = app.state.colony_manager
        ownership_err = _check_legacy_ownership(colony_id, client, cm)
        if ownership_err:
            return ownership_err
        try:
            callbacks = make_ws_callbacks(colony_id, ws_manager)
            await cm.start(colony_id, callbacks=callbacks)
            return {"status": "started", "colony_id": colony_id}
        except ColonyNotFoundError:
            return _error_response(404, "COLONY_NOT_FOUND", f"Colony '{colony_id}' not found")
        except InvalidTransitionError as exc:
            return _error_response(409, "INVALID_TRANSITION", str(exc))
        except Exception as exc:
            return _error_response(500, "COLONY_START_FAILED", str(exc))

    @app.post("/api/colony/{colony_id}/pause")
    async def pause_colony(colony_id: str, client: ClientAPIKey | None = Depends(get_current_client)):
        cm: ColonyManager = app.state.colony_manager
        ownership_err = _check_legacy_ownership(colony_id, client, cm)
        if ownership_err:
            return ownership_err
        try:
            session_file = await cm.pause(colony_id)
            return {"status": "paused", "colony_id": colony_id, "session_file": str(session_file)}
        except ColonyNotFoundError:
            return _error_response(404, "COLONY_NOT_FOUND", f"Colony '{colony_id}' not found")
        except InvalidTransitionError as exc:
            return _error_response(409, "INVALID_TRANSITION", str(exc))
        except Exception as exc:
            return _error_response(500, "COLONY_PAUSE_FAILED", str(exc))

    @app.post("/api/colony/{colony_id}/resume")
    async def resume_colony(colony_id: str, client: ClientAPIKey | None = Depends(get_current_client)):
        cm: ColonyManager = app.state.colony_manager
        ownership_err = _check_legacy_ownership(colony_id, client, cm)
        if ownership_err:
            return ownership_err
        try:
            callbacks = make_ws_callbacks(colony_id, ws_manager)
            await cm.resume(colony_id, callbacks=callbacks)
            return {"status": "resumed", "colony_id": colony_id}
        except ColonyNotFoundError:
            return _error_response(404, "COLONY_NOT_FOUND", f"Colony '{colony_id}' not found")
        except InvalidTransitionError as exc:
            return _error_response(409, "INVALID_TRANSITION", str(exc))
        except Exception as exc:
            return _error_response(500, "COLONY_RESUME_FAILED", str(exc))

    @app.delete("/api/colony/{colony_id}/destroy")
    async def destroy_colony(colony_id: str, client: ClientAPIKey | None = Depends(get_current_client)):
        cm: ColonyManager = app.state.colony_manager
        ownership_err = _check_legacy_ownership(colony_id, client, cm)
        if ownership_err:
            return ownership_err
        try:
            archive_path = await cm.destroy(colony_id)
            return {"status": "destroyed", "colony_id": colony_id, "archive": str(archive_path)}
        except ColonyNotFoundError:
            return _error_response(404, "COLONY_NOT_FOUND", f"Colony '{colony_id}' not found")
        except Exception as exc:
            return _error_response(500, "COLONY_DESTROY_FAILED", str(exc))

    @app.post("/api/colony/extend")
    async def extend_colony(body: ExtendRequest):
        cm: ColonyManager = app.state.colony_manager
        try:
            new_max = await cm.extend(body.colony_id, body.rounds, body.hint)
            return {"colony_id": body.colony_id, "new_max_rounds": new_max}
        except ColonyNotFoundError:
            return _error_response(404, "COLONY_NOT_FOUND", f"Colony '{body.colony_id}' not found")
        except Exception as exc:
            return _error_response(500, "COLONY_EXTEND_FAILED", str(exc))

    # ── Colony View (set active colony for dashboard) ────────────────

    @app.post("/api/colony/{colony_id}/view")
    async def view_colony(colony_id: str):
        """Set the active colony for the dashboard context tree."""
        cm: ColonyManager = app.state.colony_manager
        ctx: AsyncContextTree = app.state.ctx

        try:
            colony_ctx = cm.get_context(colony_id)
        except (ColonyNotFoundError, KeyError):
            return _error_response(404, "COLONY_NOT_FOUND", f"Colony '{colony_id}' not found")

        # Sync dashboard context with the target colony's context
        await ctx.set("colony", "colony_id", colony_id)
        await ctx.set("colony", "task", colony_ctx.get("colony", "task"))
        await ctx.set("colony", "status", colony_ctx.get("colony", "status"))
        await ctx.set("colony", "round", colony_ctx.get("colony", "round", 0))
        await ctx.set("colony", "max_rounds", colony_ctx.get("colony", "max_rounds"))
        await ctx.set("colony", "agents", colony_ctx.get("colony", "agents", []))
        await ctx.set("colony", "final_answer", colony_ctx.get("colony", "final_answer"))
        await ctx.set("colony", "session_id", colony_ctx.get("colony", "session_id"))

        return {"status": "viewing", "colony_id": colony_id}

    # ── Legacy single-colony run ─────────────────────────────────────

    @app.post("/api/run")
    async def run_colony(body: RunRequest):
        cm: ColonyManager = app.state.colony_manager
        ctx: AsyncContextTree = app.state.ctx

        colony_id = f"dashboard_{uuid.uuid4().hex[:8]}"

        # Clear previous dashboard context
        await ctx.clear_colony()

        # Build agent configs
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
            # Default: manager + architect + coder (minimum viable team)
            agent_configs.append(AgentConfig(
                agent_id=f"manager_{uuid.uuid4().hex[:6]}",
                caste="manager",
            ))
            agent_configs.append(AgentConfig(
                agent_id=f"architect_{uuid.uuid4().hex[:6]}",
                caste="architect",
            ))
            agent_configs.append(AgentConfig(
                agent_id=f"coder_{uuid.uuid4().hex[:6]}",
                caste="coder",
            ))

        colony_config = ColonyConfig(
            colony_id=colony_id,
            task=body.task,
            agents=agent_configs,
            max_rounds=body.max_rounds,
        )

        try:
            _info = await cm.create(colony_config, origin="ui")

            # Emit colony.spawned (v0.7.3)
            await ws_manager_v1.emit(_event_envelope(
                "colony.spawned", colony_id,
                {"status": "created", "origin": "ui", "client_id": None},
            ))
            await ws_manager.broadcast({
                "type": "colony_spawned", "colony_id": colony_id,
                "status": "created", "origin": "ui", "client_id": None,
            })

            # Update dashboard context
            await ctx.set("colony", "task", body.task)
            await ctx.set("colony", "colony_id", colony_id)
            await ctx.set("colony", "status", ColonyStatus.RUNNING.value)
            await ctx.set("colony", "round", 0)
            await ctx.set("colony", "max_rounds", body.max_rounds)
            await ctx.set("colony", "agents", [a.agent_id for a in agent_configs])
            await ctx.set("colony", "session_id", colony_id)

            # Start colony with WS callbacks
            callbacks = make_ws_callbacks(colony_id, ws_manager)
            await cm.start(colony_id, callbacks=callbacks)

            return {
                "colony_id": colony_id,
                "status": "running",
                "task": body.task,
            }
        except Exception as exc:
            return _error_response(500, "RUN_FAILED", str(exc))

    @app.post("/api/resume")
    async def resume_last():
        ctx: AsyncContextTree = app.state.ctx
        colony_id = ctx.get("colony", "colony_id")
        if not colony_id:
            return _error_response(404, "NO_ACTIVE_COLONY", "No colony to resume")

        cm: ColonyManager = app.state.colony_manager
        try:
            callbacks = make_ws_callbacks(colony_id, ws_manager)
            await cm.resume(colony_id, callbacks=callbacks)
            return {"status": "resumed", "colony_id": colony_id}
        except Exception as exc:
            return _error_response(500, "RESUME_FAILED", str(exc))

    # ── Sessions ─────────────────────────────────────────────────────

    @app.get("/api/sessions")
    async def list_sessions():
        sm: SessionManager = app.state.session_manager
        sessions = await sm.list_sessions()
        return [_safe_serialize(s) for s in sessions]

    @app.delete("/api/sessions/{session_id}")
    async def delete_session(session_id: str):
        sm: SessionManager = app.state.session_manager
        ctx: AsyncContextTree = app.state.ctx

        try:
            await sm.delete_session(session_id)

            # Clear dashboard context if deleting the active session
            active_sid = ctx.get("colony", "session_id")
            if active_sid == session_id:
                await ctx.clear_colony()

            return {"status": "deleted", "session_id": session_id}
        except FileNotFoundError:
            return _error_response(404, "SESSION_NOT_FOUND", f"Session '{session_id}' not found")
        except Exception as exc:
            return _error_response(500, "SESSION_DELETE_FAILED", str(exc))

    # ── Model Registry ───────────────────────────────────────────────

    @app.get("/api/models")
    async def get_models():
        mr: ModelRegistry = app.state.model_registry
        return mr.list_models()

    # ── Prompts ──────────────────────────────────────────────────────

    @app.get("/api/prompts")
    async def list_prompts():
        prompts_dir = Path("config/prompts")
        if not prompts_dir.exists():
            return []
        return [
            f.stem
            for f in sorted(prompts_dir.iterdir())
            if f.suffix == ".md" and not f.stem.startswith("_")
        ]

    @app.get("/api/prompt/{caste}")
    async def get_prompt(caste: str):
        prompt_path = Path("config/prompts") / f"{caste}.md"
        if not prompt_path.exists():
            return _error_response(404, "PROMPT_NOT_FOUND", f"Prompt for '{caste}' not found")
        content = prompt_path.read_text(encoding="utf-8")
        return {"caste": caste, "content": content}

    @app.put("/api/prompt/{caste}")
    async def update_prompt(caste: str, body: PromptUpdateRequest):
        prompt_path = Path("config/prompts") / f"{caste}.md"
        if not prompt_path.exists():
            return _error_response(404, "PROMPT_NOT_FOUND", f"Prompt for '{caste}' not found")
        prompt_path.write_text(body.content, encoding="utf-8")
        return {"caste": caste, "status": "updated"}

    # ── SkillBank CRUD ───────────────────────────────────────────────

    @app.get("/api/skill-bank")
    async def get_skill_bank():
        sb: SkillBank = app.state.skill_bank
        grouped = sb.get_all()
        return {
            tier: [_safe_serialize(s) for s in skills]
            for tier, skills in grouped.items()
        }

    @app.get("/api/skill-bank/skill/{skill_id}")
    async def get_skill(skill_id: str):
        sb: SkillBank = app.state.skill_bank
        try:
            skill = sb._find_skill(skill_id)
            return _safe_serialize(skill)
        except KeyError:
            return _error_response(404, "SKILL_NOT_FOUND", f"Skill '{skill_id}' not found")

    @app.post("/api/skill-bank/skill")
    async def create_skill(body: SkillCreateRequest):
        sb: SkillBank = app.state.skill_bank
        try:
            skill_id = sb.store_single(
                content=body.content,
                tier=body.tier,
                category=body.category,
            )
            return {"skill_id": skill_id, "status": "created"}
        except ValueError as exc:
            return _error_response(409, "SKILL_DUPLICATE", str(exc))
        except Exception as exc:
            return _error_response(500, "SKILL_CREATE_FAILED", str(exc))

    @app.put("/api/skill-bank/skill/{skill_id}")
    async def update_skill(skill_id: str, body: SkillUpdateRequest):
        sb: SkillBank = app.state.skill_bank
        try:
            sb.update(skill_id, body.content)
            return {"skill_id": skill_id, "status": "updated"}
        except KeyError:
            return _error_response(404, "SKILL_NOT_FOUND", f"Skill '{skill_id}' not found")
        except Exception as exc:
            return _error_response(500, "SKILL_UPDATE_FAILED", str(exc))

    @app.delete("/api/skill-bank/skill/{skill_id}")
    async def delete_skill(skill_id: str):
        sb: SkillBank = app.state.skill_bank
        try:
            sb.delete(skill_id)
            return {"skill_id": skill_id, "status": "deleted"}
        except KeyError:
            return _error_response(404, "SKILL_NOT_FOUND", f"Skill '{skill_id}' not found")
        except Exception as exc:
            return _error_response(500, "SKILL_DELETE_FAILED", str(exc))

    # ── MCP ──────────────────────────────────────────────────────────

    @app.get("/api/mcp/status")
    async def get_mcp_status():
        mcp: MCPGatewayClient = app.state.mcp_client
        return {
            "connected": mcp.connected,
            "error": mcp.connect_error,
            "tools": mcp.get_tools(),
        }

    @app.post("/api/mcp/reconnect")
    async def mcp_reconnect():
        mcp: MCPGatewayClient = app.state.mcp_client
        if mcp.connected:
            await mcp.disconnect()
        success = await mcp.connect()
        return {
            "connected": success,
            "error": mcp.connect_error,
            "tools_count": len(mcp.get_tools()) if success else 0,
        }

    # ── Caste CRUD ───────────────────────────────────────────────────

    @app.get("/api/castes")
    async def list_castes():
        """List all castes with full config and prompt content."""
        config: FormicOSConfig = app.state.config
        result = {}
        for name, cc in config.castes.items():
            prompt_content = ""
            prompt_path = Path("config/prompts") / cc.system_prompt_file
            if prompt_path.exists():
                prompt_content = prompt_path.read_text(encoding="utf-8")
            result[name] = {
                "name": name,
                "system_prompt": prompt_content,
                "tools": cc.tools,
                "mcp_tools": cc.mcp_tools,
                "model_override": cc.model_override,
                "subcaste_overrides": {
                    k: v.model_dump() if hasattr(v, "model_dump") else v
                    for k, v in cc.subcaste_overrides.items()
                },
                "description": cc.description,
            }
        return result

    @app.post("/api/castes")
    async def create_caste(body: CasteCreateRequest):
        """Create a new caste."""
        config: FormicOSConfig = app.state.config
        name = body.name.strip().lower()
        if not name:
            return _error_response(400, "INVALID_NAME", "Caste name cannot be empty")
        if name in config.castes:
            return _error_response(409, "CASTE_EXISTS", f"Caste '{name}' already exists")

        # Write prompt file
        prompt_file = f"{name}.md"
        prompt_path = Path("config/prompts") / prompt_file
        prompt_path.write_text(body.system_prompt or f"# {name.title()} Agent\n\nYou are a {name} agent.\n", encoding="utf-8")

        # Parse subcaste overrides
        sub_overrides = {}
        for tier_key, entry_data in body.subcaste_overrides.items():
            if isinstance(entry_data, dict):
                sub_overrides[tier_key] = SubcasteMapEntry(**entry_data)
            else:
                sub_overrides[tier_key] = SubcasteMapEntry(primary=str(entry_data))

        # Add to runtime config
        config.castes[name] = CasteConfig(
            system_prompt_file=prompt_file,
            tools=body.tools,
            mcp_tools=body.mcp_tools,
            model_override=body.model_override,
            subcaste_overrides=sub_overrides,
            description=body.description,
        )
        return {"name": name, "status": "created"}

    @app.put("/api/castes/{name}")
    async def update_caste(name: str, body: CasteUpdateRequest):
        """Update an existing caste's config and/or prompt."""
        config: FormicOSConfig = app.state.config
        name = name.strip().lower()
        if name not in config.castes:
            return _error_response(404, "CASTE_NOT_FOUND", f"Caste '{name}' not found")

        cc = config.castes[name]

        # Update prompt file if provided
        if body.system_prompt is not None:
            prompt_path = Path("config/prompts") / cc.system_prompt_file
            prompt_path.write_text(body.system_prompt, encoding="utf-8")

        # Update config fields
        if body.tools is not None:
            cc.tools = body.tools
        if body.mcp_tools is not None:
            cc.mcp_tools = body.mcp_tools
        if body.model_override is not None:
            cc.model_override = body.model_override if body.model_override else None
        if body.description is not None:
            cc.description = body.description
        if body.subcaste_overrides is not None:
            sub_overrides = {}
            for tier_key, entry_data in body.subcaste_overrides.items():
                if isinstance(entry_data, dict):
                    sub_overrides[tier_key] = SubcasteMapEntry(**entry_data)
                else:
                    sub_overrides[tier_key] = SubcasteMapEntry(primary=str(entry_data))
            cc.subcaste_overrides = sub_overrides

        return {"name": name, "status": "updated"}

    @app.delete("/api/castes/{name}")
    async def delete_caste(name: str):
        """Delete a caste. Cannot delete 'manager'."""
        config: FormicOSConfig = app.state.config
        name = name.strip().lower()
        if name == "manager":
            return _error_response(403, "PROTECTED_CASTE", "Cannot delete the manager caste")
        if name not in config.castes:
            return _error_response(404, "CASTE_NOT_FOUND", f"Caste '{name}' not found")

        cc = config.castes.pop(name)

        # Optionally delete prompt file
        prompt_path = Path("config/prompts") / cc.system_prompt_file
        if prompt_path.exists():
            prompt_path.unlink()

        return {"name": name, "status": "deleted"}

    # ── Supercolony Agent — Team Suggestion ──────────────────────────

    @app.post("/api/suggest-team")
    async def suggest_team(body: SuggestTeamRequest):
        """Use the LLM to suggest an optimal team for a given task."""
        config_obj: FormicOSConfig = app.state.config

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
            aio_sess = app.state.aio_session
            from src.llm_client import AioLLMClient
            client = AioLLMClient(
                session=aio_sess,
                base_url=config_obj.inference.endpoint,
            )
            model_string = config_obj.inference.model_alias or "gpt-4"
        except Exception as exc:
            return _error_response(
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
            return _error_response(
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

    # ── Workspace File API ───────────────────────────────────────────

    @app.get("/api/workspace/{colony_id}/files")
    async def list_workspace_files(colony_id: str, path: str = ""):
        """List files in a colony's workspace directory."""
        from src.stigmergy import SharedWorkspaceManager, SandboxViolationError
        workspace = Path("./workspace") / colony_id
        if not workspace.exists():
            return []
        mgr = SharedWorkspaceManager(workspace)
        try:
            return await mgr.list_files(path)
        except SandboxViolationError:
            return _error_response(403, "SANDBOX_VIOLATION", "Path escapes workspace")

    @app.get("/api/workspace/{colony_id}/file")
    async def read_workspace_file(colony_id: str, path: str = ""):
        """Read a single file from a colony's workspace."""
        from src.stigmergy import SharedWorkspaceManager, SandboxViolationError
        workspace = Path("./workspace") / colony_id
        # Normalize path separators (Windows backslashes → forward slashes)
        path = path.replace("\\", "/")
        mgr = SharedWorkspaceManager(workspace)
        try:
            content = await mgr.read_file(path)
            return {"path": path, "content": content}
        except FileNotFoundError:
            return _error_response(404, "FILE_NOT_FOUND", f"File not found: {path}")
        except SandboxViolationError:
            return _error_response(403, "SANDBOX_VIOLATION", "Path escapes workspace")

    @app.post("/api/workspace/{colony_id}/upload")
    async def upload_workspace_file(colony_id: str, request: Request):
        """Upload a file to a colony's workspace via raw body with X-Filename header."""
        from src.stigmergy import SharedWorkspaceManager, SandboxViolationError
        workspace = Path("./workspace") / colony_id
        workspace.mkdir(parents=True, exist_ok=True)
        mgr = SharedWorkspaceManager(workspace)

        filename = request.headers.get("X-Filename", "")
        if not filename:
            return _error_response(400, "MISSING_FILENAME", "X-Filename header required")

        body_bytes = await request.body()
        try:
            written = await mgr.write_file(filename, body_bytes)
            return {"path": filename, "bytes_written": written}
        except SandboxViolationError:
            return _error_response(403, "SANDBOX_VIOLATION", "Path escapes workspace")

    # ── Human-in-the-Loop ────────────────────────────────────────────

    @app.post("/api/approve")
    async def approve(body: ApproveRequest):
        gate: ApprovalGate = app.state.approval_gate
        try:
            gate.respond(body.request_id, body.approved)
            return {
                "request_id": body.request_id,
                "approved": body.approved,
                "status": "resolved",
            }
        except KeyError:
            return _error_response(
                404, "APPROVAL_NOT_FOUND",
                f"No pending approval with id '{body.request_id}'",
            )

    @app.post("/api/intervene")
    async def intervene(body: InterveneRequest):
        ctx: AsyncContextTree = app.state.ctx
        colony_id = body.colony_id or ctx.get("colony", "colony_id")
        if not colony_id:
            return _error_response(404, "NO_ACTIVE_COLONY", "No colony to intervene in")

        await ctx.set("colony", "operator_hint", body.hint)

        # Also broadcast via WS
        await ws_manager.broadcast({
            "type": "round_update",
            "colony_id": colony_id,
            "phase": "intervention",
            "data": {"hint": body.hint},
        })

        return {"colony_id": colony_id, "hint": body.hint, "status": "injected"}

    # ── WebSocket ────────────────────────────────────────────────────

    @app.websocket("/ws/stream")
    async def ws_stream(ws: WebSocket):
        await ws_manager.connect(ws)
        try:
            while True:
                try:
                    data = await asyncio.wait_for(ws.receive_json(), timeout=60.0)
                    if data.get("type") == "ping":
                        await ws.send_json({"type": "pong"})
                except asyncio.TimeoutError:
                    # No message from client in 60s — send server-side ping
                    try:
                        await ws.send_json({"type": "ping"})
                    except Exception:
                        break  # Connection dead
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            ws_manager.disconnect(ws)

    # ══════════════════════════════════════════════════════════════════
    # API v1 Router (v0.7.9: extracted to src/api/routes/)
    # ══════════════════════════════════════════════════════════════════

    # Store WS managers on app.state for route modules
    ws_manager_v1 = ConnectionManagerV1()
    app.state.ws_manager_v1 = ws_manager_v1

    # V1 Router Assembly
    from src.api.routes import system, auth, colonies, workspace, admin, sessions, castes, ingestion
    v1 = APIRouter(prefix="/api/v1")
    v1.include_router(system.router)
    v1.include_router(auth.router)
    v1.include_router(colonies.router)
    v1.include_router(workspace.router)
    v1.include_router(admin.router)
    v1.include_router(sessions.router)
    v1.include_router(castes.router)
    v1.include_router(ingestion.router)
    app.include_router(v1)

    # ── Static Files ─────────────────────────────────────────────────

    web_dir = Path(__file__).parent / "web"
    if web_dir.exists():
        app.mount(
            "/",
            StaticFiles(directory=str(web_dir), html=True),
            name="static",
        )

    return app


# ═══════════════════════════════════════════════════════════════════════════
# app_factory() -- entry point for uvicorn
# ═══════════════════════════════════════════════════════════════════════════


def app_factory() -> FastAPI:
    """Load config and build the application.  Called by uvicorn."""
    config = load_config()
    return create_app(config)
