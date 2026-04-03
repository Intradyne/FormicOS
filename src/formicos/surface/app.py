"""Starlette application factory — wires adapters, engine, and surface.

Creates the ASGI application with:
- Adapter instantiation (SQLite, Qdrant, LLM)
- Provider-prefix model routing (algorithms.md §11)
- Embedding function injection
- Capability registry construction (ADR-036)
- Route assembly from surface/routes/ modules
- Lifespan: event replay into projections on startup, colony rehydration
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
import yaml
from starlette.applications import Starlette
from starlette.routing import Mount, WebSocketRoute
from starlette.staticfiles import StaticFiles

import formicos
from formicos.adapters.embedding_qwen3 import Qwen3Embedder
from formicos.adapters.knowledge_graph import KnowledgeGraphAdapter
from formicos.adapters.llm_anthropic import AnthropicLLMAdapter
from formicos.adapters.llm_gemini import GeminiAdapter
from formicos.adapters.llm_openai_compatible import OpenAICompatibleLLMAdapter
from formicos.adapters.store_sqlite import SqliteEventStore
from formicos.adapters.vector_qdrant import QdrantVectorPort
from formicos.core.events import EVENT_TYPE_NAMES, QueenMessage
from formicos.core.ports import LLMPort
from formicos.core.settings import (
    CasteRecipeSet,
    _interpolate_recursive,  # pyright: ignore[reportPrivateUsage]
    load_castes,
    load_config,
)
from formicos.core.types import ModelRecord
from formicos.surface.agui_endpoint import AGUI_EVENT_TYPES
from formicos.surface.colony_manager import ColonyManager
from formicos.surface.mcp_server import MCP_TOOL_NAMES, create_mcp_server
from formicos.surface.projections import ProjectionStore
from formicos.surface.queen_runtime import (
    QueenAgent,
    _parse_projection_timestamp,  # pyright: ignore[reportPrivateUsage]
)
from formicos.surface.registry import CapabilityRegistry, ProtocolEntry, ToolEntry
from formicos.surface.routes import (
    a2a_routes,
    api_routes,
    colony_io_routes,
    health_routes,
    knowledge_routes,
    memory_routes,
    protocol_routes,
)
from formicos.surface.runtime import LLMRouter, Runtime
from formicos.surface.template_manager import load_templates
from formicos.surface.ws_handler import WebSocketManager, ws_endpoint

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

log = structlog.get_logger()


def _log_task_exception(task: asyncio.Task[Any]) -> None:
    """Error callback for fire-and-forget tasks."""
    if not task.cancelled() and task.exception() is not None:
        log.error(
            "fire_and_forget_failed",
            task_name=task.get_name(),
            error=str(task.exception()),
        )


# Feature flag: sentence-transformers may not be installed in test environments.
_EMBED_AVAILABLE = False  # pyright: ignore[reportConstantRedefinition]
try:
    from sentence_transformers import SentenceTransformer  # pyright: ignore[reportMissingImports]
    _EMBED_AVAILABLE = True  # pyright: ignore[reportConstantRedefinition]
except ImportError:
    pass


def _ensure_v1(base_url: str) -> str:
    """Ensure Ollama/OpenAI-compatible base_url ends with /v1."""
    stripped = base_url.rstrip("/")
    if not stripped.endswith("/v1"):
        return f"{stripped}/v1"
    return stripped


def route_model_to_adapter(
    model_address: str,
    adapters: dict[str, LLMPort],
) -> LLMPort:
    """Route a model address to the correct LLM adapter (algorithms.md §11)."""
    provider_prefix = model_address.split("/", 1)[0]
    adapter = adapters.get(provider_prefix)
    if adapter is None:
        raise ValueError(f"No adapter registered for provider '{provider_prefix}'")
    return adapter


def _build_embed_fn(
    model_name: str,
) -> Any | None:  # noqa: ANN401
    """Load sentence-transformers and return an embed_fn, or None if unavailable.

    Best-effort fallback only — returns None if the library is missing or the
    model cannot be loaded (e.g. not a valid HuggingFace model ID).
    The primary Wave 13 embedding path is the Qwen3 sidecar HTTP client.
    """
    if not _EMBED_AVAILABLE:
        log.info("sentence_transformers.unavailable", model=model_name)
        return None
    if model_name.lower().startswith("qwen3-embedding"):
        log.info(
            "sentence_transformers.skipped_for_sidecar_model",
            model=model_name,
        )
        return None
    try:
        st_model = SentenceTransformer(model_name, trust_remote_code=True)  # pyright: ignore[reportPossiblyUnbound,reportPossiblyUnboundVariable]
    except Exception as exc:  # noqa: BLE001
        log.info("sentence_transformers.model_load_failed", model=model_name, error=str(exc))
        return None

    def embed_fn(texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        prefix = "search_query: " if is_query else "search_document: "
        prefixed = [prefix + t for t in texts]
        return st_model.encode(prefixed, normalize_embeddings=True).tolist()  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType,reportAttributeAccessIssue]

    return embed_fn


def _load_vector_config(config_path: str | Path) -> dict[str, Any]:
    """Read the raw 'vector' section from the YAML config file."""
    try:
        with Path(config_path).open("r", encoding="utf-8") as fh:
            raw: dict[str, Any] = _interpolate_recursive(yaml.safe_load(fh)) or {}  # pyright: ignore[reportAssignmentType]
        return dict(raw.get("vector", {}))  # pyright: ignore[reportUnknownArgumentType]
    except Exception:  # noqa: BLE001
        return {}


def _load_embed_config(config_path: str | Path) -> dict[str, Any]:
    """Read the 'embedding' section from YAML config."""
    try:
        with Path(config_path).open("r", encoding="utf-8") as fh:
            raw: dict[str, Any] = _interpolate_recursive(yaml.safe_load(fh)) or {}  # pyright: ignore[reportAssignmentType]
        return dict(raw.get("embedding", {}))  # pyright: ignore[reportUnknownArgumentType]
    except Exception:  # noqa: BLE001
        return {}


def _load_kg_config(config_path: str | Path) -> dict[str, Any]:
    """Read the 'knowledge_graph' section from YAML config."""
    try:
        with Path(config_path).open("r", encoding="utf-8") as fh:
            raw: dict[str, Any] = _interpolate_recursive(yaml.safe_load(fh)) or {}  # pyright: ignore[reportAssignmentType]
        return dict(raw.get("knowledge_graph", {}))  # pyright: ignore[reportUnknownArgumentType]
    except Exception:  # noqa: BLE001
        return {}


def _build_cost_fn(
    registry: list[ModelRecord],
) -> Any:  # noqa: ANN401
    """Build a cost function: (model, input_tokens, output_tokens) -> USD (ADR-009)."""
    rate_map: dict[str, tuple[float, float]] = {}
    for model in registry:
        input_rate = model.cost_per_input_token or 0.0
        output_rate = model.cost_per_output_token or 0.0
        rate_map[model.address] = (input_rate, output_rate)

    def cost_fn(model: str, input_tokens: int, output_tokens: int) -> float:
        rates = rate_map.get(model, (0.0, 0.0))
        return (input_tokens * rates[0]) + (output_tokens * rates[1])

    return cost_fn


def _configure_asyncio_debug_from_env() -> None:
    """Enable asyncio slow-callback diagnostics when explicitly requested."""
    if os.environ.get("FORMICOS_ASYNCIO_DEBUG", "").lower() not in (
        "1", "true", "yes",
    ):
        return
    loop = asyncio.get_running_loop()
    loop.set_debug(True)
    loop.slow_callback_duration = 0.1
    log.info(
        "app.asyncio_debug_enabled",
        slow_callback_duration_s=loop.slow_callback_duration,
    )


def create_app(
    config_path: str | Path = "config/formicos.yaml",
    castes_path: str | Path = "config/caste_recipes.yaml",
) -> Starlette:
    """Build the Starlette ASGI application with all wiring."""
    settings = load_config(config_path)
    castes: CasteRecipeSet | None = None
    if Path(castes_path).exists():
        castes = load_castes(castes_path)

    data_dir = Path(settings.system.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    # -- Adapters --
    event_store = SqliteEventStore(data_dir / "events.db")

    # -- Embedding: sidecar client (when EMBED_URL is set) or sentence-transformers fallback --
    embed_cfg = _load_embed_config(config_path)
    embed_endpoint = str(embed_cfg.get("endpoint", ""))
    embed_instruction = str(embed_cfg.get("instruction", ""))
    embed_client: Qwen3Embedder | None = None
    embed_fn = None
    # Wave 77: skip sidecar when EMBED_URL is empty (cloud-first default).
    # The YAML endpoint template is "${EMBED_URL:}/v1/embeddings", so an
    # empty EMBED_URL produces "/v1/embeddings" — no host, not a valid URL.
    if embed_endpoint and "://" in embed_endpoint:
        embed_client = Qwen3Embedder(
            url=embed_endpoint,
            instruction=embed_instruction,
        )
        log.info(
            "app.embed_client",
            model=settings.embedding.model,
            url=embed_endpoint,
            dimensions=settings.embedding.dimensions,
        )
    # Fallback: try sentence-transformers (best-effort, no crash on failure)
    embed_fn = _build_embed_fn(settings.embedding.model)

    # -- Vector store (ADR-013: Qdrant is the sole vector backend) --
    vector_cfg = _load_vector_config(config_path)
    skill_collection = vector_cfg.get("collection_name", "skill_bank_v2")
    vector_store: QdrantVectorPort | None = None
    if embed_client is not None or embed_fn is not None:
        qdrant_url = vector_cfg.get("qdrant_url", "http://localhost:6333")
        prefer_grpc = vector_cfg.get("qdrant_prefer_grpc", True)
        vector_store = QdrantVectorPort(
            url=qdrant_url,
            embed_fn=embed_fn,
            embed_client=embed_client,
            prefer_grpc=bool(prefer_grpc),
            default_collection=skill_collection,
            vector_dimensions=settings.embedding.dimensions,
        )
        log.info(
            "app.vector_backend",
            backend="qdrant", url=qdrant_url,
            dimensions=settings.embedding.dimensions,
            hybrid=embed_client is not None,
            collection=skill_collection,
        )

    # -- Knowledge graph (Wave 13 A-T3 / B-T3, ADR-025 async embed) --
    kg_cfg = _load_kg_config(config_path)
    kg_adapter: KnowledgeGraphAdapter | None = None
    if kg_cfg:
        threshold = float(kg_cfg.get("entity_similarity_threshold", 0.85))
        predicates_list = kg_cfg.get("predicates", [])
        kg_async_embed = embed_client.embed if embed_client is not None else None
        kg_adapter = KnowledgeGraphAdapter(
            db_path=data_dir / "formicos.db",
            embed_fn=embed_fn,
            async_embed_fn=kg_async_embed,
            similarity_threshold=threshold,
            predicates=frozenset(predicates_list) if predicates_list else None,
        )
        log.info("app.knowledge_graph", threshold=threshold)

    # LLM adapters keyed by (provider:endpoint) pair.
    # Wave 64: per-endpoint adapter instances — two models with the same
    # provider prefix but different endpoints get separate adapters.
    # Cloud adapters are only created when the API key is present.
    # Wave 78.5: validate endpoints against metadata/SSRF targets at startup.
    from formicos.surface.ssrf_validate import validate_endpoint_url  # noqa: PLC0415

    llm_adapters: dict[str, LLMPort] = {}
    for model in settings.models.registry:
        if model.endpoint:
            try:
                validate_endpoint_url(model.endpoint)
            except ValueError as exc:
                log.warning(
                    "app.endpoint_blocked",
                    address=model.address,
                    endpoint=model.endpoint,
                    error=str(exc),
                )
                continue
        adapter_key = (
            f"{model.provider}:{model.endpoint or 'default'}"
        )
        if adapter_key in llm_adapters:
            continue
        if model.provider == "anthropic":
            api_key = os.environ.get(model.api_key_env or "ANTHROPIC_API_KEY", "")
            if not api_key:
                log.info("app.adapter_skipped", provider="anthropic", reason="no_key")
                continue
            llm_adapters[adapter_key] = AnthropicLLMAdapter(api_key=api_key)  # type: ignore[assignment]
        elif model.provider == "gemini":
            api_key = os.environ.get(model.api_key_env or "GEMINI_API_KEY", "")
            if not api_key:
                log.info("app.adapter_skipped", provider="gemini", reason="no_key")
                continue
            llm_adapters[adapter_key] = GeminiAdapter(api_key=api_key)  # type: ignore[assignment]
        else:
            # Wave 55: extract API key for cloud OpenAI-compatible providers
            api_key = (
                os.environ.get(model.api_key_env or "", "")
                if model.api_key_env
                else ""
            )
            base_url = _ensure_v1(model.endpoint or "http://localhost:8008")
            # Wave 58: scale timeout by the highest time_multiplier for
            # this prefix.  A cpu/cloud archivist with time_multiplier 3.0
            # gets 360s timeout.  Default (1.0) keeps 120s.
            max_mult = max(
                (m.time_multiplier or 1.0
                 for m in settings.models.registry
                 if m.provider == model.provider),
                default=1.0,
            )
            llm_adapters[adapter_key] = OpenAICompatibleLLMAdapter(  # type: ignore[assignment]
                base_url=base_url,
                api_key=api_key if api_key else None,
                timeout_s=120.0 * max(1.0, max_mult),
                max_concurrent=model.max_concurrent,
            )

    # Wave 64: unknown prefix fallback — if a model has a provider prefix
    # not in the known set but has an endpoint, create OpenAI-compatible.
    _KNOWN_PROVIDERS = {
        "anthropic", "gemini", "llama-cpp", "ollama",
        "openai", "deepseek",
    }
    for model in settings.models.registry:
        adapter_key = (
            f"{model.provider}:{model.endpoint or 'default'}"
        )
        if adapter_key in llm_adapters:
            continue
        if model.provider not in _KNOWN_PROVIDERS and model.endpoint:
            api_key = (
                os.environ.get(model.api_key_env or "", "")
                if model.api_key_env
                else ""
            )
            base_url = _ensure_v1(model.endpoint)
            llm_adapters[adapter_key] = OpenAICompatibleLLMAdapter(  # type: ignore[assignment]
                base_url=base_url,
                api_key=api_key if api_key else None,
                max_concurrent=model.max_concurrent,
            )

    # -- Institutional memory store (Wave 26) --
    from formicos.surface.memory_store import MemoryStore

    memory_store: MemoryStore | None = None
    if vector_store is not None:
        memory_store = MemoryStore(vector_port=vector_store)  # type: ignore[arg-type]

    # -- Projections --
    projections = ProjectionStore()

    # -- Knowledge catalog (Wave 27) --
    from formicos.surface.knowledge_catalog import KnowledgeCatalog

    knowledge_catalog = KnowledgeCatalog(
        memory_store=memory_store,
        vector_port=vector_store,  # type: ignore[arg-type]
        skill_collection=skill_collection,
        projections=projections,
        kg_adapter=kg_adapter,  # Wave 59.5: graph-augmented retrieval
    )

    # -- LLM Router (with compute routing table from ADR-012) --
    llm_router = LLMRouter(
        llm_adapters,
        routing_table=settings.routing.model_routing,
        registry=settings.models.registry,
    )

    # -- Cost function from model registry (ADR-009) --
    cost_fn = _build_cost_fn(settings.models.registry)

    # -- WebSocket manager (runtime set below) --
    ws_manager = WebSocketManager(projections, settings, castes)

    # -- Runtime (the ONE mutation path) --
    runtime = Runtime(
        event_store=event_store,  # pyright: ignore[reportArgumentType]
        projections=projections,
        ws_manager=ws_manager,
        settings=settings,
        castes=castes,
        llm_router=llm_router,
        embed_fn=embed_fn,
        vector_store=vector_store,  # type: ignore[arg-type]
        cost_fn=cost_fn,
        kg_adapter=kg_adapter,
        embed_client=embed_client,
    )

    # Wire runtime back to ws_manager
    ws_manager._runtime = runtime  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    # Wave 50: wire cooldown notify callback so operators see provider issues
    def _on_provider_cooldown(provider: str) -> None:
        log.warning("provider_cooldown_activated", provider=provider)

    llm_router._cooldown._notify_callback = _on_provider_cooldown  # noqa: SLF001

    # Wire memory store into runtime (Wave 26 B3/B4)
    runtime.memory_store = memory_store

    # Wire knowledge catalog into runtime (Wave 27)
    runtime.knowledge_catalog = knowledge_catalog  # type: ignore[attr-defined]

    # -- Queen agent --
    queen = QueenAgent(runtime)
    runtime.queen = queen

    # -- Colony manager --
    colony_manager = ColonyManager(runtime)
    runtime.colony_manager = colony_manager

    # -- Forager service (Wave 44) --
    from formicos.adapters.content_quality import score_content  # noqa: PLC0415
    from formicos.adapters.egress_gateway import EgressGateway, EgressPolicy  # noqa: PLC0415
    from formicos.adapters.fetch_pipeline import FetchPipeline  # noqa: PLC0415
    from formicos.adapters.web_search import WebSearchAdapter  # noqa: PLC0415
    from formicos.surface.forager import (  # noqa: PLC0415
        ForagerFetchAdapter,
        ForagerOrchestratorWithEmit,
        ForagerService,
    )

    egress_policy = EgressPolicy(respect_robots_txt=True)
    egress_gateway = EgressGateway(egress_policy)
    fetch_pipeline = FetchPipeline(egress_gateway)
    forager_fetch = ForagerFetchAdapter(fetch_pipeline, score_content)
    serper_key = os.environ.get("SERPER_API_KEY", "")
    search_adapter = WebSearchAdapter.create(serper_api_key=serper_key)
    # Egress-configured httpx client for search — shares user-agent and
    # timeout with the fetch substrate, but search API endpoints (DDG, Serper)
    # do not need domain allow/deny, rate-limiting, or robots.txt checks.
    import httpx as _httpx  # noqa: PLC0415

    search_http_client = _httpx.AsyncClient(
        timeout=egress_policy.timeout_seconds,
        headers={"User-Agent": egress_policy.user_agent},
    )
    forager_orchestrator = ForagerOrchestratorWithEmit(
        search_adapter=search_adapter,
        fetch_port=forager_fetch,
        search_http_client=search_http_client,
        runtime=runtime,
    )
    forager_service = ForagerService(runtime, forager_orchestrator)
    runtime.forager_service = forager_service  # type: ignore[attr-defined]

    # -- MCP server --
    mcp = create_mcp_server(runtime)

    # -- Capability registry (ADR-036) --
    # Wave 78 Track 2: read Queen tool names from self-describing registry
    queen_tool_defs = queen._queen_tools()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    registry = CapabilityRegistry(
        event_names=tuple(EVENT_TYPE_NAMES),
        mcp_tools=tuple(
            ToolEntry(name=name, description="")
            for name in MCP_TOOL_NAMES
        ),
        queen_tools=tuple(
            ToolEntry(
                name=t.get("name", ""),
                description=t.get("description", ""),
            )
            for t in queen_tool_defs
        ),
        agui_events=tuple(sorted(AGUI_EVENT_TYPES)),
        protocols=(
            ProtocolEntry(
                name="MCP",
                status="active",
                endpoint="/mcp",
                transport="Streamable HTTP",
            ),
            ProtocolEntry(
                name="AG-UI",
                status="active",
                endpoint="/ag-ui/runs",
                semantics="summary-at-turn-end",
            ),
            ProtocolEntry(
                name="A2A",
                status="active",
                endpoint="/a2a/tasks",
                semantics="submit/poll/attach/result",
                note="Task lifecycle (ADR-038). Attach: /a2a/tasks/{id}/events.",
            ),
        ),
        castes=tuple(
            sorted(castes.castes.keys()) if castes else ()
        ),
        version=formicos.__version__,
    )
    ws_manager._registry = registry  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    # -- MCP Streamable HTTP transport (ADR-034) --
    from fastmcp.server.http import create_streamable_http_app

    mcp_http = create_streamable_http_app(
        server=mcp,
        streamable_http_path="/mcp",
        stateless_http=True,
    )

    # -- Lifespan --
    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncGenerator[None]:
        log.info("app.starting", data_dir=str(data_dir))
        _configure_asyncio_debug_from_env()
        # Replay events into projections
        async for event in event_store.replay():
            projections.apply(event)
        log.info("app.replay_complete", last_seq=projections.last_seq)

        # Rebuild memory store from projection state (Wave 26 A7)
        if memory_store is not None and projections.memory_entries:
            mem_count = await memory_store.rebuild_from_projection(
                projections.memory_entries,
            )
            log.info("app.memory_store_rebuilt", entries=mem_count)

        # Wave 59.5: rebuild entry_kg_nodes mapping after replay
        await runtime._rebuild_entry_kg_nodes()  # noqa: SLF001

        # Restart backfill: re-queue extraction for completed/failed colonies
        # that have no MemoryExtractionCompleted receipt (Wave 26.5).
        #
        # Run this as a single background drain and wait for live work to go
        # idle before each extraction so replay/backfill cannot consume the
        # entire local LLM pool during startup.
        if memory_store is not None:
            settled_ids = {
                cid for cid, proj in projections.colonies.items()
                if getattr(proj, "status", "") in ("completed", "failed")
            }
            extracted_ids = projections.memory_extractions_completed
            missing = sorted(settled_ids - extracted_ids)
            if missing:
                log.info(
                    "app.memory_backfill_queued",
                    count=len(missing),
                    colony_ids=missing[:10],
                )

                async def _run_memory_backfill(
                    colony_ids: list[str],
                ) -> None:
                    initial_delay_s = float(
                        os.environ.get(
                            "FORMICOS_MEMORY_BACKFILL_DELAY_S",
                            "10",
                        ),
                    )
                    if initial_delay_s > 0:
                        await asyncio.sleep(initial_delay_s)
                    for cid in colony_ids:
                        while any(
                            getattr(proj, "status", "") == "running"
                            for proj in projections.colonies.values()
                        ):
                            await asyncio.sleep(5)
                        proj = projections.colonies.get(cid)
                        if proj is None:
                            continue
                        final_summary = ""
                        if proj.round_records:
                            last_rr = proj.round_records[-1]
                            final_summary = "\n".join(
                                f"[{aid}] {out[:1000]}"
                                for aid, out in last_rr.agent_outputs.items()
                            )
                        try:
                            await colony_manager.extract_institutional_memory(
                                colony_id=cid,
                                workspace_id=proj.workspace_id,
                                colony_status=proj.status,
                                final_summary=final_summary,
                                artifacts=proj.artifacts,
                                failure_reason=proj.failure_reason,
                            )
                        except Exception:  # noqa: BLE001
                            log.warning(
                                "app.memory_backfill_failed",
                                colony_id=cid,
                                exc_info=True,
                            )

                _memory_backfill_task = asyncio.create_task(
                    _run_memory_backfill(missing),
                )
                _memory_backfill_task.add_done_callback(_log_task_exception)

        # First-run bootstrap: create default workspace + thread if store is empty
        if projections.last_seq == 0:
            log.info("app.first_run_detected")
            await runtime.create_workspace("default")
            await runtime.create_thread("default", "main")

            # Verify default templates are readable
            templates = await load_templates()
            log.info(
                "app.first_run_templates_visible",
                count=len(templates),
                names=[t.name for t in templates],
            )

            # Welcome Queen message
            await runtime.emit_and_broadcast(QueenMessage(
                seq=0,
                timestamp=datetime.now(UTC),
                address="default/main",
                thread_id="main",
                role="queen",
                content=(
                    "Welcome to FormicOS. I'm the Queen, your strategic "
                    "coordinator.\n\n"
                    "The stack is live. You can click + to spawn a colony "
                    "or ask me to shape the task for you.\n\n"
                    "Try asking me to:\n"
                    "- Plan a feature and recommend a colony template\n"
                    "- Review a code snippet for bugs, risks, and missing tests\n"
                    "- Research an API design choice and summarize tradeoffs\n\n"
                    "Organize your work:\n"
                    "- Try setting a thread goal to organize your work\n"
                    "- I can define workflow steps to break down complex projects\n"
                    "- I learn from each colony — check the Knowledge tab "
                    "after your first task completes\n\n"
                    "Startup tips:\n"
                    "- Open Knowledge to inspect skills, experiences, and the graph\n"
                    "- Open a colony detail view to inspect generated artifacts\n"
                    "- If startup feels stuck, check /health or docker compose logs formicos"
                ),
            ))
            log.info(
                "app.first_run_bootstrapped",
                workspace="default", thread="main",
            )

        # Best-effort rehydration of running colonies
        await colony_manager.rehydrate()

        # Wave 29: register deterministic service handlers
        from formicos.surface.maintenance import (  # noqa: PLC0415
            make_confidence_reset_handler,
            make_contradiction_handler,
            make_cooccurrence_decay_handler,
            make_credential_sweep_handler,
            make_curation_handler,
            make_dedup_handler,
            make_stale_handler,
        )

        service_router = colony_manager.service_router
        if service_router is not None:  # type: ignore[reportUnnecessaryComparison]
            service_router.register_handler(
                "service:consolidation:dedup",
                make_dedup_handler(runtime),
            )
            service_router.register_handler(
                "service:consolidation:stale_sweep",
                make_stale_handler(runtime),
            )
            service_router.register_handler(
                "service:consolidation:contradiction",
                make_contradiction_handler(runtime),
            )
            service_router.register_handler(
                "service:consolidation:confidence_reset",
                make_confidence_reset_handler(runtime),
            )
            # Wave 33 A5: co-occurrence weight decay
            service_router.register_handler(
                "service:consolidation:cooccurrence_decay",
                make_cooccurrence_decay_handler(runtime),
            )
            # Wave 33 B3: retroactive credential sweep
            service_router.register_handler(
                "service:consolidation:credential_sweep",
                make_credential_sweep_handler(runtime),
            )
            # Wave 59: knowledge curation
            service_router.register_handler(
                "service:consolidation:curation",
                make_curation_handler(runtime),
            )
            service_router.set_emit_fn(runtime.emit_and_broadcast)

            # Wave 38 1A: register NemoClaw external specialist handlers
            from formicos.adapters.nemoclaw_client import (  # noqa: PLC0415
                SPECIALIST_SERVICES,
                NemoClawClient,
                make_nemoclaw_handler,
            )

            nemoclaw_client = NemoClawClient()
            if nemoclaw_client.is_configured:
                for svc_name, spec_type in SPECIALIST_SERVICES.items():
                    service_router.register_handler(
                        svc_name,
                        make_nemoclaw_handler(nemoclaw_client, spec_type),
                    )
                log.info(
                    "app.nemoclaw_registered",
                    specialists=list(SPECIALIST_SERVICES.keys()),
                )
            else:
                log.info("app.nemoclaw_skipped", reason="no_endpoint")

            # Emit registration events for operator visibility
            from formicos.core.events import (  # noqa: PLC0415
                DeterministicServiceRegistered,
            )

            _registration_services = [
                (
                    "service:consolidation:dedup",
                    "Auto-merge near-duplicate knowledge entries",
                ),
                (
                    "service:consolidation:stale_sweep",
                    "Transition stale entries and decay confidence",
                ),
                (
                    "service:consolidation:contradiction",
                    "Detect contradicting knowledge entries",
                ),
                (
                    "service:consolidation:confidence_reset",
                    "Reset stuck entries to prior confidence",
                ),
                (
                    "service:consolidation:cooccurrence_decay",
                    "Decay and prune co-occurrence weights",
                ),
                (
                    "service:consolidation:credential_sweep",
                    "Retroactive credential scanning of knowledge entries",
                ),
            ]
            # Add NemoClaw services if configured
            if nemoclaw_client.is_configured:
                _registration_services.extend([
                    (
                        "service:external:nemoclaw:secure_coder",
                        "External NemoClaw secure code generation specialist",
                    ),
                    (
                        "service:external:nemoclaw:security_review",
                        "External NemoClaw security review specialist",
                    ),
                    (
                        "service:external:nemoclaw:sandbox_analysis",
                        "External NemoClaw sandboxed analysis specialist",
                    ),
                ])

            for svc_name, svc_desc in _registration_services:
                await runtime.emit_and_broadcast(DeterministicServiceRegistered(
                    seq=0,
                    timestamp=datetime.now(UTC),
                    address="system",
                    service_name=svc_name,
                    description=svc_desc,
                ))

        # Wave 64 Track 6a: load addon manifests and register components
        from formicos.core.events import AddonLoaded  # noqa: PLC0415
        from formicos.surface.addon_loader import (  # noqa: PLC0415
            build_addon_tool_specs,
            discover_addons,
            register_addon,
        )

        _addons_dir = Path(__file__).resolve().parents[3] / "addons"
        if not _addons_dir.is_dir():
            _addons_dir = Path("/app/addons")  # Docker layout
        _addon_manifests = discover_addons(_addons_dir)
        _addon_registrations = []
        # Wave 70.0: initialise MCP bridge (lazy connections, no I/O here)
        from formicos.addons.mcp_bridge.client import McpBridge  # noqa: PLC0415

        _mcp_bridge = McpBridge()
        # Load server config from settings or MCP_SERVERS env var
        import json as _json  # noqa: PLC0415
        _mcp_servers_raw = getattr(
            getattr(runtime, "settings", None), "mcp_servers", None,
        )
        if _mcp_servers_raw is None:
            _mcp_servers_raw = os.environ.get("MCP_SERVERS", "[]")
        if isinstance(_mcp_servers_raw, str):
            try:
                _mcp_servers_raw = _json.loads(_mcp_servers_raw)
            except (ValueError, TypeError):
                _mcp_servers_raw = []
        if isinstance(_mcp_servers_raw, list) and _mcp_servers_raw:
            _mcp_bridge.configure(_mcp_servers_raw)
            log.info("mcp_bridge.configured", server_count=len(_mcp_servers_raw))

        def _ws_runtime_root(data_dir: str, ws_id: str) -> Path:
            from formicos.surface.workspace_roots import workspace_runtime_root  # noqa: PLC0415

            return workspace_runtime_root(data_dir, ws_id)

        _addon_runtime_context: dict[str, Any] = {
            "vector_port": getattr(
                getattr(runtime, "memory_store", None), "_vector", None
            ) or getattr(runtime, "memory_store", None),
            "embed_fn": getattr(runtime, "embed_fn", None),
            "workspace_root_fn": (
                lambda ws_id: _ws_runtime_root(str(data_dir), ws_id)
            ),
            "data_dir": str(data_dir),
            "event_store": getattr(runtime, "event_store", None),
            "settings": getattr(runtime, "settings", {}),
            "projections": getattr(runtime, "projections", None),
            "runtime": runtime,
            "mcp_bridge": _mcp_bridge,
            "get_bridge_health": _mcp_bridge.get_bridge_health,
        }
        # Wave 88: wire shared cache into addon context
        try:
            from formicos.addons.repo_activity.refresh import get_shared_cache  # noqa: PLC0415

            _addon_runtime_context["addon_cache"] = get_shared_cache()
        except ImportError:
            pass
        # Wave 88: wire per-addon governed MCP gateway after addon registration
        # (deferred to per-addon context in register_addon loop below)
        for _manifest in _addon_manifests:
            # Wave 88: per-addon governed gateway from manifest permissions
            _per_addon_ctx = dict(_addon_runtime_context)
            if getattr(_manifest, "mcp_permissions", None) and _mcp_bridge:
                try:
                    from formicos.addons.mcp_bridge.gateway import (  # noqa: PLC0415
                        create_gateway_for_addon,
                    )

                    _per_addon_ctx["mcp_gateway"] = create_gateway_for_addon(
                        _mcp_bridge, _manifest.name, _manifest.mcp_permissions,
                    )
                except (ImportError, Exception):
                    pass

            _reg = register_addon(
                _manifest,
                tool_registry=(
                    queen._tool_dispatcher._handlers  # pyright: ignore[reportPrivateUsage]
                    if queen is not None else None
                ),
                service_router=service_router,
                runtime_context=_per_addon_ctx,
            )
            _addon_registrations.append(_reg)
            await runtime.emit_and_broadcast(AddonLoaded(
                seq=0,
                timestamp=datetime.now(UTC),
                address="system",
                addon_name=_manifest.name,
                version=_manifest.version,
                tools=_reg.registered_tools,
                handlers=_reg.registered_handlers,
                panels=[p.get("target", "") for p in _manifest.panels],
            ))
            log.info(
                "app.addon_loaded",
                addon=_manifest.name,
                tools=_reg.registered_tools,
                handlers=_reg.registered_handlers,
            )

        # Expose addon tool specs for Queen tool list and wire into dispatcher
        app.state.addon_tool_specs = build_addon_tool_specs(_addon_manifests)  # type: ignore[attr-defined]
        app.state.addon_manifests = _addon_manifests  # type: ignore[attr-defined]
        app.state.addon_registrations = _addon_registrations  # type: ignore[attr-defined]
        runtime.addon_registrations = _addon_registrations  # type: ignore[attr-defined]
        ws_manager._addon_registrations = _addon_registrations  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        if queen is not None:
            queen._tool_dispatcher._addon_tool_specs = app.state.addon_tool_specs  # pyright: ignore[reportPrivateUsage]
            queen._tool_dispatcher._addon_manifests = _addon_manifests  # pyright: ignore[reportPrivateUsage]
            queen._tool_dispatcher._addon_runtime_context = _addon_runtime_context  # pyright: ignore[reportPrivateUsage]

        # Wave 65 Track 4: wire TriggerDispatcher for addon cron/manual triggers
        from formicos.core.events import ServiceTriggerFired  # noqa: PLC0415
        from formicos.surface.trigger_dispatch import TriggerDispatcher  # noqa: PLC0415

        _trigger_dispatcher = TriggerDispatcher()
        for _manifest in _addon_manifests:
            _trigger_dispatcher.register_triggers(_manifest.name, _manifest.triggers)

        async def _trigger_loop() -> None:
            """Evaluate cron triggers every 60 seconds."""
            while True:
                await asyncio.sleep(60)
                fired = _trigger_dispatcher.evaluate_cron_triggers()
                for desc in fired:
                    try:
                        addon_name = desc["addon_name"]
                        handler_ref = desc["handler"]
                        # Find the matching addon registration for handler resolution
                        import inspect as _insp  # noqa: PLC0415

                        from formicos.surface.addon_loader import (  # noqa: PLC0415
                            _resolve_handler,
                        )
                        handler_fn = _resolve_handler(addon_name, handler_ref)
                        try:
                            sig = _insp.signature(handler_fn)
                        except (ValueError, TypeError):
                            sig = None
                        if sig and "runtime_context" in sig.parameters:
                            await handler_fn(runtime_context=_addon_runtime_context)
                        elif sig and len(sig.parameters) == 0:
                            await handler_fn()
                        else:
                            log.warning(
                                "trigger_dispatch.unsupported_handler_signature",
                                addon=addon_name,
                                handler=handler_ref,
                                params=list(sig.parameters.keys()),
                            )
                            continue
                        # Track trigger fire time on registration
                        _match_reg = next(
                            (r for r in _addon_registrations
                             if r.manifest.name == addon_name),
                            None,
                        )
                        if _match_reg is not None:
                            _match_reg.trigger_fire_times[handler_ref] = (
                                datetime.now(UTC).isoformat()
                            )
                        await runtime.emit_and_broadcast(ServiceTriggerFired(
                            seq=0,
                            timestamp=datetime.now(UTC),
                            address="system",
                            addon_name=addon_name,
                            trigger_type="cron",
                            handler=handler_ref,
                        ))
                    except Exception:  # noqa: BLE001
                        log.warning(
                            "trigger_dispatch.handler_error",
                            addon=desc.get("addon_name"),
                            handler=desc.get("handler"),
                            exc_info=True,
                        )

        _trigger_task = asyncio.create_task(_trigger_loop())
        _trigger_task.add_done_callback(_log_task_exception)
        app.state.trigger_dispatcher = _trigger_dispatcher  # type: ignore[attr-defined]

        # Wave 45.5: MaintenanceDispatcher for proactive briefing evaluation
        from formicos.surface.self_maintenance import (  # noqa: PLC0415
            MaintenanceDispatcher,
        )

        _maint_dispatcher = MaintenanceDispatcher(runtime)
        app.state.maintenance_dispatcher = _maint_dispatcher  # type: ignore[attr-defined]
        # Wave 76: wire dispatcher for cost reconciliation
        colony_manager.set_maintenance_dispatcher(_maint_dispatcher)

        # Wave 30 A7: scheduled maintenance timer
        _maint_interval = int(os.environ.get(
            "FORMICOS_MAINTENANCE_INTERVAL_S", "86400",
        ))

        async def _maintenance_loop(
            router: Any = service_router,
            interval_s: int = _maint_interval,
        ) -> None:
            """Periodic dispatch of consolidation services only.

            Proactive dispatch moved to _operational_sweep_loop (Wave 72).
            """
            while True:
                await asyncio.sleep(interval_s)
                for svc in [
                    "service:consolidation:dedup",
                    "service:consolidation:stale_sweep",
                    "service:consolidation:contradiction",
                ]:
                    try:
                        await router.query(
                            service_type=svc,
                            query_text="scheduled_run",
                            timeout_s=300.0,
                        )
                    except Exception:  # noqa: BLE001
                        log.debug(
                            "maintenance.scheduled_run_failed",
                            service=svc,
                        )

        _maint_task = asyncio.create_task(_maintenance_loop())
        _maint_task.add_done_callback(_log_task_exception)

        # Wave 71.0 Track 6: operational sweep loop (30-minute default)
        _ops_sweep_interval = int(os.environ.get(
            "FORMICOS_OPS_SWEEP_INTERVAL_S", "1800",
        ))

        _sweep_lock = asyncio.Lock()

        async def _operational_sweep_loop(
            interval_s: int = _ops_sweep_interval,
        ) -> None:
            """Consolidated operational sweep (Wave 72 Track 6).

            Order:
            1. run_proactive_dispatch()
            2. Team A scan_knowledge_for_review() — stub until Team A lands
            3. queue_continuation_proposals()
            4. execute_idle_continuations()
            5. Team C extract_workflow_patterns() — stub until Team C lands
            6. Team C detect_operator_patterns() — stub until Team C lands
            7. Approved-action processing + compaction
            """
            while True:
                await asyncio.sleep(interval_s)
                # Wave 76: reentrancy guard — skip if prior sweep still running
                if _sweep_lock.locked():
                    log.warning("ops_sweep.skipped_reentrant")
                    continue
                async with _sweep_lock:
                    await _operational_sweep_body()

        async def _operational_sweep_body() -> None:
            """Inner sweep body extracted for reentrancy guard."""
            data_dir_str = str(data_dir)
            workspace_ids = list(
                runtime.projections.workspaces.keys(),
            )

            # --- Step 1: Proactive dispatch (moved from _maintenance_loop) ---
            try:
                await _maint_dispatcher.run_proactive_dispatch()
            except Exception:  # noqa: BLE001
                log.debug("ops_sweep.proactive_dispatch_failed")

            # --- Step 2: Team A knowledge review (stub) ---
            for ws_id in workspace_ids:
                try:
                    from formicos.surface.knowledge_review import (  # noqa: PLC0415
                        scan_knowledge_for_review,
                    )

                    await scan_knowledge_for_review(
                        data_dir_str, ws_id, runtime.projections,
                        briefing_insights=getattr(
                            _maint_dispatcher, "last_briefing_insights", {},
                        ).get(ws_id),
                    )
                except ImportError:
                    pass  # Team A not landed yet
                except Exception:  # noqa: BLE001
                    log.debug(
                        "ops_sweep.knowledge_review_failed",
                        workspace_id=ws_id,
                    )

            # --- Steps 3-4: Continuation proposals + idle execution ---
            for ws_id in workspace_ids:
                try:
                    from formicos.surface.continuation import (  # noqa: PLC0415
                        execute_idle_continuations,
                        queue_continuation_proposals,
                    )

                    await queue_continuation_proposals(
                        data_dir_str, ws_id,
                        runtime.projections, _maint_dispatcher,
                    )
                    await execute_idle_continuations(
                        data_dir_str, ws_id,
                        runtime.projections, _maint_dispatcher,
                    )
                except Exception:  # noqa: BLE001
                    log.debug(
                        "ops_sweep.continuation_failed",
                        workspace_id=ws_id,
                    )

            # --- Steps 5-6: Team C workflow/operator patterns (stubs) ---
            for ws_id in workspace_ids:
                try:
                    from formicos.surface.workflow_learning import (  # noqa: PLC0415
                        detect_operator_patterns,
                        extract_workflow_patterns,
                    )

                    await extract_workflow_patterns(
                        data_dir_str, ws_id, runtime.projections,
                    )
                    await detect_operator_patterns(
                        data_dir_str, ws_id, runtime.projections,
                    )
                except ImportError:
                    pass  # Team C not landed yet
                except Exception:  # noqa: BLE001
                    log.debug(
                        "ops_sweep.workflow_learning_failed",
                        workspace_id=ws_id,
                    )

            # --- Step 7: Approved-action processing + compaction ---
            try:
                from formicos.surface.action_queue import (  # noqa: PLC0415
                    STATUS_APPROVED,
                    STATUS_EXECUTED,
                    STATUS_FAILED,
                    compact_action_log,
                    update_action,
                )
                from formicos.surface.action_queue import (
                    read_actions as _read_actions,
                )

                for ws_id in workspace_ids:
                    compact_action_log(data_dir_str, ws_id)

                    actions = _read_actions(data_dir_str, ws_id)
                    for act in actions:
                        if act.get("status") != STATUS_APPROVED:
                            continue
                        sc = act.get("payload", {}).get(
                            "suggested_colony",
                        )
                        if not sc:
                            continue
                        try:
                            from datetime import (  # noqa: PLC0415
                                UTC as _UTC,
                            )
                            from datetime import (
                                datetime as _dt,
                            )

                            from formicos.core.types import (  # noqa: PLC0415
                                CasteSlot as _CS,
                            )

                            await runtime.spawn_colony(
                                workspace_id=ws_id,
                                thread_id=act.get(
                                    "thread_id", "maintenance",
                                ) or "maintenance",
                                task=sc.get(
                                    "task", act.get("title", ""),
                                ),
                                castes=[
                                    _CS(
                                        caste=sc.get(
                                            "caste", "researcher",
                                        ),
                                    ),
                                ],
                                strategy=sc.get(
                                    "strategy", "sequential",
                                ),
                                max_rounds=sc.get("max_rounds", 3),
                            )
                            update_action(
                                data_dir_str, ws_id,
                                act["action_id"],
                                {
                                    "status": STATUS_EXECUTED,
                                    "executed_at": _dt.now(
                                        _UTC,
                                    ).isoformat(),
                                },
                            )
                            # Wave 76: journal coverage for sweep-executed actions
                            from formicos.surface.operational_state import (  # noqa: PLC0415
                                append_journal_entry as _aje,
                            )

                            title = act.get("title", act.get("action_id", ""))
                            _aje(
                                data_dir_str, ws_id,
                                source="sweep",
                                message=f"Sweep executed: {title}",
                            )
                        except Exception:  # noqa: BLE001
                            update_action(
                                data_dir_str, ws_id,
                                act["action_id"],
                                {"status": STATUS_FAILED},
                            )
            except Exception:  # noqa: BLE001
                log.debug("ops_sweep.action_processing_failed")

            # --- Step 8: Post sweep observations to display board ---
            try:
                from formicos.surface.operational_state import (  # noqa: PLC0415
                    post_sweep_observations as _post_sweep,
                )
                from formicos.surface.operations_coordinator import (  # noqa: PLC0415
                    build_operations_summary as _build_ops,
                )

                for ws_id in workspace_ids:
                    _ops_summary = _build_ops(
                        data_dir_str, ws_id, runtime.projections,
                    )
                    _post_sweep(
                        data_dir_str, ws_id, _ops_summary,
                        runtime.projections,
                    )
            except Exception:  # noqa: BLE001
                log.debug("ops_sweep.display_board_posting_failed")

        _ops_sweep_task = asyncio.create_task(_operational_sweep_loop())
        _ops_sweep_task.add_done_callback(_log_task_exception)

        # Telemetry bus (Wave 17 A2): start with JSONL sink + optional OTel
        from formicos.adapters.telemetry_jsonl import JSONLSink
        from formicos.engine.telemetry_bus import get_telemetry_bus

        telemetry_bus = get_telemetry_bus()
        telemetry_bus.add_sink(JSONLSink(data_dir / "telemetry.jsonl"))

        # Wave 46: OTel sink beside JSONL — opt-in via FORMICOS_OTEL_ENABLED
        if os.environ.get("FORMICOS_OTEL_ENABLED", "").lower() in ("1", "true", "yes"):
            from formicos.adapters.telemetry_otel import OTelAdapter, OTelSink

            _otel = OTelAdapter.create()
            if _otel.enabled:
                telemetry_bus.add_sink(OTelSink(_otel))
                log.info("app.otel_sink_enabled")
            else:
                log.info("app.otel_sink_skipped", reason="opentelemetry not installed")

        await telemetry_bus.start()

        yield
        # Shutdown
        _trigger_task.cancel()
        # Wave 64: emit AddonUnloaded for each loaded addon
        import contextlib  # noqa: PLC0415

        from formicos.core.events import AddonUnloaded  # noqa: PLC0415
        for _reg in _addon_registrations:
            with contextlib.suppress(Exception):
                await runtime.emit_and_broadcast(AddonUnloaded(
                    seq=0,
                    timestamp=datetime.now(UTC),
                    address="system",
                    addon_name=_reg.manifest.name,
                    reason="shutdown",
                ))
        # Wave 68: emit session summaries for recently active threads
        _cutoff = datetime.now(UTC) - timedelta(minutes=30)
        for _ws_id, _ws in projections.workspaces.items():
            for _tid, _thr in _ws.threads.items():
                if not _thr.queen_messages:
                    continue
                _last_msg = _thr.queen_messages[-1]
                _ts = _parse_projection_timestamp(_last_msg.timestamp)
                if _ts and _ts > _cutoff:
                    try:
                        queen.emit_session_summary(_ws_id, _tid)
                    except Exception:
                        log.warning(
                            "shutdown.session_summary_failed",
                            workspace_id=_ws_id,
                            thread_id=_tid,
                        )

        await telemetry_bus.stop()
        await event_store.close()
        log.info("app.stopped")

    # -- WebSocket handler --
    async def websocket_handler(ws: WebSocket) -> None:
        await ws_endpoint(ws, ws_manager)

    # -- Route assembly from modules --
    shared_deps: dict[str, Any] = {
        "runtime": runtime,
        "projections": projections,
        "settings": settings,
        "castes": castes,
        "castes_path": castes_path,
        "config_path": config_path,
        "data_dir": data_dir,
        "vector_store": vector_store,
        "kg_adapter": kg_adapter,
        "embed_client": embed_client,
        "skill_collection": skill_collection,
        "ws_manager": ws_manager,
        "registry": registry,
        "mcp_http": mcp_http,
        "memory_store": memory_store,
        "knowledge_catalog": knowledge_catalog,
    }

    routes: list[Any] = []

    # Wave 66 T3: catch-all addon route handler (resolves from app.state at request time)
    async def _addon_route_handler(request: Any) -> Any:
        import inspect as _ri  # noqa: PLC0415

        from starlette.responses import JSONResponse  # noqa: PLC0415

        addon_name = request.path_params.get("addon_name", "")
        route_path = "/" + request.path_params.get("path", "")
        regs: list[Any] = getattr(request.app.state, "addon_registrations", [])
        for reg in regs:
            for aroute in reg.registered_routes:
                if aroute["addon_name"] == addon_name and aroute["path"] == route_path:
                    handler_fn = aroute["handler"]
                    try:
                        _accepts = "runtime_context" in _ri.signature(handler_fn).parameters
                    except (ValueError, TypeError):
                        _accepts = False
                    ctx = reg.runtime_context
                    # Wave 87: pass query params as inputs for workspace-scoped panels
                    _inputs = dict(request.query_params)
                    if _accepts:
                        result = await handler_fn(_inputs, "", "", runtime_context=ctx)
                    else:
                        result = await handler_fn(_inputs, "", "")
                    return JSONResponse(result)
        return JSONResponse({"error": "addon route not found"}, status_code=404)

    from starlette.routing import Route  # noqa: PLC0415
    routes.append(Route(
        "/addons/{addon_name:str}/{path:path}",
        _addon_route_handler,
        methods=["GET"],
    ))

    routes.extend(health_routes(**shared_deps))
    routes.extend(api_routes(**shared_deps))
    routes.extend(colony_io_routes(**shared_deps))
    routes.extend(protocol_routes(**shared_deps))
    routes.extend(a2a_routes(**shared_deps))
    routes.extend(memory_routes(**shared_deps))
    routes.extend(knowledge_routes(**shared_deps))
    routes.append(WebSocketRoute("/ws", websocket_handler))

    # Serve frontend/dist/ if it exists (built via vite)
    frontend_dir = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if not frontend_dir.is_dir():
        # Docker layout: frontend/dist is at /app/frontend/dist
        frontend_dir = Path("/app/frontend/dist")
    if frontend_dir.is_dir():
        routes.append(
            Mount("/", app=StaticFiles(directory=str(frontend_dir), html=True)),
        )

    @asynccontextmanager
    async def combined_lifespan(app: Starlette) -> AsyncGenerator[None]:
        async with AsyncExitStack() as stack:
            mcp_lifespan = getattr(mcp_http, "lifespan", None)
            if callable(mcp_lifespan):
                await stack.enter_async_context(mcp_lifespan(app))
            await stack.enter_async_context(lifespan(app))
            yield

    app = Starlette(
        debug=False,
        lifespan=combined_lifespan,
        routes=routes,
    )

    # Store references for access from tests and extensions
    app.state.event_store = event_store  # type: ignore[attr-defined]
    app.state.projections = projections  # type: ignore[attr-defined]
    app.state.settings = settings  # type: ignore[attr-defined]
    app.state.castes = castes  # type: ignore[attr-defined]
    app.state.llm_adapters = llm_adapters  # type: ignore[attr-defined]
    app.state.vector_store = vector_store  # type: ignore[attr-defined]
    app.state.embed_fn = embed_fn  # type: ignore[attr-defined]
    app.state.ws_manager = ws_manager  # type: ignore[attr-defined]
    app.state.mcp = mcp  # type: ignore[attr-defined]
    app.state.runtime = runtime  # type: ignore[attr-defined]
    app.state.route_model = route_model_to_adapter  # type: ignore[attr-defined]
    app.state.kg_adapter = kg_adapter  # type: ignore[attr-defined]
    app.state.registry = registry  # type: ignore[attr-defined]

    return app


__all__ = ["create_app", "route_model_to_adapter"]
