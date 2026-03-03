"""
FormicOS v0.6.0 -- Colony Manager

Manages the lifecycle of multiple concurrent colonies.  Creates isolated
environments, starts/pauses/resumes/destroys colonies, and maintains the
durable supercolony registry.

State machine:
  CREATED -> {READY, RUNNING, QUEUED_PENDING_COMPUTE}
  QUEUED_PENDING_COMPUTE -> {RUNNING, FAILED}
  READY   -> {RUNNING}
  RUNNING -> {PAUSED, COMPLETED, FAILED}
  PAUSED  -> {RUNNING, FAILED}
  COMPLETED -> (terminal)
  FAILED  -> {CREATED}

Concurrency model:
  - One asyncio.Lock for all registry mutations
  - Per-colony orchestrator tasks are asyncio.Tasks
  - Context tree serialization happens under the tree's own lock
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from src.context import AsyncContextTree
from src.models import (
    ColonyConfig,
    ColonyStatus,
    DiagnosticsPayload,
    DocumentInject,
    FormicOSConfig,
    HardwareState,
    ResumeDirective,
    TeamConfig,
)

if TYPE_CHECKING:
    from src.approval import ApprovalGate
    from src.audit import AuditLogger
    from src.model_registry import ModelRegistry
    from src.mcp_client import MCPGatewayClient
    from src.rag import RAGEngine
    from src.session import SessionManager
    from src.skill_bank import SkillBank
    from src.webhook import WebhookDispatcher

logger = logging.getLogger("formicos.colony_manager")


# ── Valid State Transitions ───────────────────────────────────────────────

VALID_TRANSITIONS: dict[ColonyStatus, set[ColonyStatus]] = {
    ColonyStatus.CREATED: {
        ColonyStatus.READY,
        ColonyStatus.RUNNING,
        ColonyStatus.QUEUED_PENDING_COMPUTE,
    },
    ColonyStatus.READY: {ColonyStatus.RUNNING},
    ColonyStatus.RUNNING: {
        ColonyStatus.PAUSED,
        ColonyStatus.COMPLETED,
        ColonyStatus.FAILED,
        ColonyStatus.HALTED_BUDGET_EXHAUSTED,
    },
    ColonyStatus.PAUSED: {ColonyStatus.RUNNING, ColonyStatus.FAILED},
    ColonyStatus.COMPLETED: set(),
    ColonyStatus.FAILED: {ColonyStatus.CREATED},
    ColonyStatus.HALTED_BUDGET_EXHAUSTED: set(),  # terminal
    ColonyStatus.QUEUED_PENDING_COMPUTE: {
        ColonyStatus.RUNNING,
        ColonyStatus.FAILED,
    },
}

DEFAULT_WORKSPACE_BASE = Path("./workspace")
DEFAULT_REGISTRY_PATH = Path(".formicos/colony_registry.json")
DEFAULT_SESSION_BASE = Path(".formicos/sessions")
DESTROY_CANCEL_TIMEOUT = 10.0  # seconds to wait for task cancellation


# ── ColonyInfo ────────────────────────────────────────────────────────────


class ColonyInfo(BaseModel):
    """Public metadata about a colony, returned by get_all() and create()."""

    colony_id: str
    task: str
    status: ColonyStatus = ColonyStatus.CREATED
    round: int = 0
    max_rounds: int = 10
    agent_count: int = 0
    teams: list[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    origin: str = "ui"  # "ui" | "api"
    client_id: str | None = None
    webhook_url: str | None = None


class TeamInfo(BaseModel):
    """Public metadata about a team within a colony."""

    team_id: str
    name: str
    objective: str
    members: list[str] = Field(default_factory=list)


# ── Internal Colony State ─────────────────────────────────────────────────


@dataclass
class _ColonyState:
    """Internal per-colony state, not exposed to callers."""

    info: ColonyInfo
    context_tree: AsyncContextTree
    colony_config: ColonyConfig | None = None
    task: asyncio.Task | None = None
    orchestrator: Any | None = None  # Orchestrator (deferred import to avoid circular)
    workspace: Path = field(default_factory=lambda: Path("."))
    session_file: Path | None = None
    needs_crash_resume: bool = False  # v0.8.0: durable execution crash recovery


# ── Errors ────────────────────────────────────────────────────────────────


class ColonyNotFoundError(Exception):
    """Raised when a colony_id is not in the registry."""
    pass


class InvalidTransitionError(Exception):
    """Raised when a state transition violates the state machine."""
    pass


class DuplicateColonyError(Exception):
    """Raised when attempting to create a colony with a duplicate ID."""
    pass


class ColonyConfigError(Exception):
    """Raised when colony configuration is invalid."""
    pass


# ═══════════════════════════════════════════════════════════════════════════
# ColonyManager
# ═══════════════════════════════════════════════════════════════════════════


class ColonyManager:
    """
    Manages the lifecycle of multiple concurrent colonies.

    Parameters
    ----------
    config : FormicOSConfig
        Top-level config.
    model_registry : ModelRegistry
        For validating model assignments and creating agent clients.
    session_manager : SessionManager
        For session persistence and archival.
    rag_engine : RAGEngine | None
        For creating/deleting Qdrant namespaces.  Optional.
    workspace_base : Path
        Base directory for colony workspace directories.
    registry_path : Path
        Path to the persisted colony registry JSON file.
    """

    def __init__(
        self,
        config: FormicOSConfig,
        model_registry: ModelRegistry,
        session_manager: SessionManager,
        rag_engine: RAGEngine | None = None,
        mcp_client: MCPGatewayClient | None = None,
        embedder: Any | None = None,
        skill_bank: SkillBank | None = None,
        audit_logger: AuditLogger | None = None,
        approval_gate: ApprovalGate | None = None,
        webhook_dispatcher: WebhookDispatcher | None = None,
        workspace_base: Path | None = None,
        registry_path: Path | None = None,
        caste_recipes: dict | None = None,
    ) -> None:
        self._config: FormicOSConfig = config
        self._model_registry: ModelRegistry = model_registry
        self._session_manager: SessionManager = session_manager
        self._rag_engine: RAGEngine | None = rag_engine
        self._mcp_client: MCPGatewayClient | None = mcp_client
        self._embedder: Any | None = embedder
        self._skill_bank: SkillBank | None = skill_bank
        self._audit_logger: AuditLogger | None = audit_logger
        self._approval_gate: ApprovalGate | None = approval_gate
        self._webhook_dispatcher: WebhookDispatcher | None = webhook_dispatcher

        self._workspace_base = workspace_base or DEFAULT_WORKSPACE_BASE
        self._registry_path = registry_path or DEFAULT_REGISTRY_PATH

        # Caste recipes — opt-in Configuration as Code overlay
        from src.models import load_caste_recipes, CasteRecipe  # noqa: F811
        self._caste_recipes: dict[str, CasteRecipe] = (
            caste_recipes if caste_recipes is not None else load_caste_recipes()
        )

        # In-memory registry: colony_id -> _ColonyState
        self._colonies: dict[str, _ColonyState] = {}

        # Concurrency
        self._lock = asyncio.Lock()

        # Load persisted registry on construction (sync, before event loop)
        self._load_registry_sync()

    # ── Public API ────────────────────────────────────────────────────

    async def create(
        self,
        colony_config: ColonyConfig,
        origin: str = "ui",
        client_id: str | None = None,
    ) -> ColonyInfo:
        """
        Create a new colony.

        Validates config, creates workspace directory, creates per-colony
        AsyncContextTree, initializes colony scope, optionally creates
        Qdrant namespace, and registers in the registry.

        Parameters
        ----------
        colony_config : ColonyConfig
            Full colony configuration.

        Returns
        -------
        ColonyInfo
            Public metadata about the created colony.

        Raises
        ------
        DuplicateColonyError
            If colony_id already exists.
        ColonyConfigError
            If config validation fails.
        """
        colony_id = colony_config.colony_id

        async with self._lock:
            # Reject duplicate
            if colony_id in self._colonies:
                raise DuplicateColonyError(
                    f"Colony '{colony_id}' already exists"
                )

            # Validate model assignments
            self._validate_config(colony_config)

            # Create workspace directory
            workspace = self._workspace_base / colony_id
            workspace.mkdir(parents=True, exist_ok=True)

            # Create per-colony context tree
            ctx = AsyncContextTree()

            # Initialize colony scope
            agent_dicts = [
                {"agent_id": a.agent_id, "caste": a.caste, "model_id": a.model_override}
                for a in colony_config.agents
            ]
            team_ids = [t.team_id for t in (colony_config.teams or [])]
            await ctx.set("colony", "task", colony_config.task)
            await ctx.set("colony", "agents", agent_dicts)
            await ctx.set("colony", "status", ColonyStatus.CREATED.value)
            await ctx.set("colony", "round", 0)
            await ctx.set("colony", "max_rounds", colony_config.max_rounds)
            await ctx.set("colony", "colony_id", colony_id)

            # Client namespace (v0.7.5)
            if client_id:
                ctx.set_client_namespace(client_id)

            # Build ColonyInfo
            info = ColonyInfo(
                colony_id=colony_id,
                task=colony_config.task,
                status=ColonyStatus.CREATED,
                round=0,
                max_rounds=colony_config.max_rounds,
                agent_count=len(colony_config.agents),
                teams=team_ids,
                origin=origin,
                client_id=client_id,
                webhook_url=colony_config.webhook_url,
            )

            # Register in memory
            state = _ColonyState(
                info=info,
                context_tree=ctx,
                colony_config=colony_config,
                workspace=workspace,
            )
            self._colonies[colony_id] = state

            # Persist registry
            self._persist_registry_sync()

        # Create Qdrant namespace (outside lock, may be slow)
        if self._rag_engine is not None:
            try:
                await self._rag_engine.create_colony_namespace(colony_id)
            except Exception as exc:
                logger.warning(
                    "Failed to create Qdrant namespace for colony '%s': %s",
                    colony_id, exc,
                )

        logger.info("Colony '%s' created (task: %s)", colony_id, colony_config.task)
        return info

    async def ingest_documents(
        self, colony_id: str, documents: list[DocumentInject],
    ) -> int:
        """Ingest DocumentInject objects into a colony's RAG namespace.

        Returns total chunks ingested across all documents.
        """
        if not self._rag_engine or not documents:
            return 0

        collection = f"colony_{colony_id}_docs"
        total = 0
        for doc in documents:
            try:
                n = await self._rag_engine.ingest_document_inject(
                    doc, collection,
                )
                total += n
            except Exception as exc:
                logger.warning(
                    "Failed to ingest document '%s' for colony '%s': %s",
                    doc.filename, colony_id, exc,
                )
        return total

    async def enqueue(self, colony_id: str) -> None:
        """Transition a colony to QUEUED_PENDING_COMPUTE.

        Called by v1_create_colony when a colony should be queued
        for automatic worker promotion rather than started immediately.

        Raises
        ------
        ColonyNotFoundError
            If colony_id not found.
        InvalidTransitionError
            If current status does not allow transition.
        """
        async with self._lock:
            state = self._get_state(colony_id)
            self._validate_transition(
                state.info.status, ColonyStatus.QUEUED_PENDING_COMPUTE,
            )
            self._set_status(state, ColonyStatus.QUEUED_PENDING_COMPUTE)
            self._persist_registry_sync()
        logger.info("Colony '%s' enqueued for compute", colony_id)

    async def start(
        self,
        colony_id: str,
        callbacks: dict[str, Any] | None = None,
    ) -> None:
        """
        Start a colony by launching the orchestrator as a background task.

        Parameters
        ----------
        colony_id : str
            Colony to start.
        callbacks : dict | None
            Optional callbacks dict forwarded to the orchestrator.

        Raises
        ------
        ColonyNotFoundError
            If colony_id not found.
        InvalidTransitionError
            If current status does not allow transition to RUNNING.
        """
        async with self._lock:
            state = self._get_state(colony_id)
            self._validate_transition(state.info.status, ColonyStatus.RUNNING)

            # Import orchestrator and agent factory lazily to avoid circular imports
            from src.orchestrator import Orchestrator
            from src.agents import AgentFactory

            # Build agents
            colony_config = self._get_colony_config(colony_id)
            factory = AgentFactory(
                model_registry=dict(self._config.model_registry),
                config=self._config,
                model_clients=self._model_registry.get_cached_clients(),
                mcp_client=self._mcp_client,
                caste_recipes=self._caste_recipes,
                rag_engine=self._rag_engine,
            )

            agents = []
            ws_root = str(state.workspace)
            for agent_cfg in colony_config.agents:
                agent = factory.create(
                    agent_id=agent_cfg.agent_id,
                    caste=agent_cfg.caste,
                    model_override=agent_cfg.model_override,
                    subcaste_tier=agent_cfg.subcaste_tier,
                    workspace_root=ws_root,
                    colony_id=colony_id,
                )
                agents.append(agent)

            # v0.8.0: Wire REPL harness for root_architect agents
            root_arch_agents = [a for a in agents if a.caste == "root_architect"]
            if root_arch_agents:
                from src.core.orchestrator.router import SubcallRouter
                from src.core.repl.harness import REPLHarness
                from src.core.repl.secured_memory import SecuredTopologicalMemory

                subcall_router = SubcallRouter(
                    factory=factory,
                    workspace_root=ws_root,
                    colony_id=colony_id,
                )
                loop = asyncio.get_running_loop()

                for agent in root_arch_agents:
                    memory_path = Path(ws_root) / "repo.bin"
                    if memory_path.exists():
                        memory = SecuredTopologicalMemory(str(memory_path))
                        harness = REPLHarness(
                            memory=memory,
                            router=subcall_router,
                            loop=loop,
                            workspace_root=ws_root,
                        )
                        agent.config["repl_harness"] = harness
                        logger.info(
                            "REPL harness attached to root_architect '%s' "
                            "(memory: %s, %s bytes)",
                            agent.id, memory_path.name, memory.file_size,
                        )

            # v0.8.0: Wire CFO toolkit for egress proxy signing
            cfo_agents = [a for a in agents if a.caste == "cfo"]
            cfo_toolkit = None
            if cfo_agents:
                import os as _os
                from src.core.network.egress_proxy import generate_keypair
                from src.core.cfo import CFOToolkit

                signing_key, verify_key = generate_keypair()
                budget_limit = getattr(colony_config, "budget_limit_usd", 100.0)
                stripe_key = _os.environ.get("STRIPE_API_KEY")

                cfo_toolkit = CFOToolkit(
                    signing_key=signing_key,
                    colony_id=colony_id,
                    budget_limit_usd=budget_limit,
                    stripe_api_key=stripe_key,
                )
                for agent in cfo_agents:
                    agent.config["cfo_toolkit"] = cfo_toolkit

                logger.info(
                    "CFO toolkit attached — verify_key=%s, budget=$%.2f",
                    verify_key.encode().hex()[:16] + "...",
                    budget_limit,
                )

            # Validate escalation fallback model IDs (warn, don't fail)
            for caste_name, recipe in self._caste_recipes.items():
                if recipe.escalation_fallback:
                    for step in recipe.escalation_fallback:
                        if not self._model_registry.has_model(step.model_id):
                            logger.warning(
                                "Recipe '%s' references unknown fallback model '%s'",
                                caste_name, step.model_id,
                            )

            # v0.7.8: Test flight mode overrides
            is_test_flight = getattr(colony_config, "is_test_flight", False)
            if is_test_flight:
                for agent in agents:
                    agent.temperature = 0.0
                    agent.seed = 42
                if self._mcp_client:
                    self._mcp_client.enable_mock_mode()

            # Create archivist and governance for this colony run
            from src.archivist import Archivist
            from src.governance import GovernanceEngine

            archivist = None
            try:
                primary_client, primary_model = self._model_registry.get_client(
                    self._config.inference.model
                )
                archivist = Archivist(primary_client, primary_model, self._config)
            except Exception as exc:
                logger.warning("Failed to create Archivist for colony '%s': %s", colony_id, exc)

            governance = GovernanceEngine(self._config)

            # Validate wiring contract
            from src.models import RuntimeWiringContract
            wiring = RuntimeWiringContract(
                model_registry=True,
                archivist=archivist is not None,
                governance=True,
                skill_bank=self._skill_bank is not None,
                audit_logger=self._audit_logger is not None,
                approval_gate=self._approval_gate is not None,
                rag_engine=self._rag_engine is not None,
            )
            missing = wiring.validate_mandatory()
            if missing:
                logger.warning(
                    "Colony '%s' wiring incomplete — missing: %s",
                    colony_id, ", ".join(missing),
                )

            # Create orchestrator with full dependency wiring
            orchestrator = Orchestrator(
                context_tree=state.context_tree,
                config=self._config,
                colony_id=colony_id,
                archivist=archivist,
                governance=governance,
                skill_bank=self._skill_bank,
                audit_logger=self._audit_logger,
                embedder=self._embedder,
                is_test_flight=is_test_flight,
                caste_recipes=self._caste_recipes,
            )

            # v0.8.0: Wire voting nodes if configured
            if colony_config.voting_nodes:
                orchestrator.configure_voting_nodes(colony_config.voting_nodes)

            # v0.8.0: Wire CFO toolkit into orchestrator for Phase 4.5
            if cfo_toolkit is not None:
                orchestrator._cfo_toolkit = cfo_toolkit
                orchestrator._cfo_factory = factory

            # Wire webhook dispatcher if colony has a webhook_url
            webhook_url = getattr(state.info, "webhook_url", None)
            if webhook_url and self._webhook_dispatcher:
                orchestrator._webhook_dispatcher = self._webhook_dispatcher
                orchestrator._webhook_url = webhook_url
                orchestrator._client_id = state.info.client_id

            state.orchestrator = orchestrator

            # Launch as background task
            task = asyncio.create_task(
                self._run_colony(
                    colony_id=colony_id,
                    orchestrator=orchestrator,
                    agents=agents,
                    max_rounds=state.info.max_rounds,
                    callbacks=callbacks,
                ),
                name=f"colony-{colony_id}",
            )
            state.task = task

            # Update status
            self._set_status(state, ColonyStatus.RUNNING)
            self._persist_registry_sync()

        logger.info("Colony '%s' started (wiring: archivist=%s governance=True skill_bank=%s audit=%s)",
                     colony_id, archivist is not None, self._skill_bank is not None,
                     self._audit_logger is not None)

    async def pause(self, colony_id: str) -> Path:
        """
        Pause a running colony.

        Signals the orchestrator to stop, waits for the current phase to
        complete, serializes the context tree, and cancels the task.

        Parameters
        ----------
        colony_id : str
            Colony to pause.

        Returns
        -------
        Path
            Path to the serialized session file.

        Raises
        ------
        ColonyNotFoundError
            If colony_id not found.
        InvalidTransitionError
            If current status is not RUNNING.
        """
        async with self._lock:
            state = self._get_state(colony_id)
            self._validate_transition(state.info.status, ColonyStatus.PAUSED)

            # Signal orchestrator to stop
            if state.orchestrator is not None:
                try:
                    state.orchestrator.cancel()
                except Exception as exc:
                    logger.warning(
                        "Error signaling orchestrator cancel for '%s': %s",
                        colony_id, exc,
                    )

        # Wait for task to finish (outside lock, may block)
        if state.task is not None and not state.task.done():
            try:
                state.task.cancel()
                await asyncio.wait_for(
                    asyncio.shield(state.task),
                    timeout=DESTROY_CANCEL_TIMEOUT,
                )
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        # Serialize context tree
        session_dir = DEFAULT_SESSION_BASE / colony_id
        session_dir.mkdir(parents=True, exist_ok=True)
        session_file = session_dir / "context.json"
        await state.context_tree.save(session_file)
        state.session_file = session_file

        async with self._lock:
            state.task = None
            state.orchestrator = None
            self._set_status(state, ColonyStatus.PAUSED)
            self._persist_registry_sync()

        logger.info("Colony '%s' paused. Session saved to %s", colony_id, session_file)
        return session_file

    async def resume(
        self,
        colony_id: str,
        callbacks: dict[str, Any] | None = None,
    ) -> None:
        """
        Resume a paused colony from its saved session file.

        Parameters
        ----------
        colony_id : str
            Colony to resume.
        callbacks : dict | None
            Optional callbacks dict.

        Raises
        ------
        ColonyNotFoundError
            If colony_id not found.
        InvalidTransitionError
            If current status is not PAUSED.
        """
        async with self._lock:
            state = self._get_state(colony_id)
            self._validate_transition(state.info.status, ColonyStatus.RUNNING)

        # Load context tree from session file
        session_file = state.session_file
        if session_file is None:
            session_file = DEFAULT_SESSION_BASE / colony_id / "context.json"

        if session_file.exists():
            try:
                state.context_tree = await AsyncContextTree.load(session_file)
            except Exception as exc:
                logger.error(
                    "Failed to load session for colony '%s': %s. "
                    "Starting fresh.",
                    colony_id, exc,
                )
                state.context_tree = AsyncContextTree()
        else:
            logger.warning(
                "No session file for colony '%s'. Starting with existing tree.",
                colony_id,
            )

        async with self._lock:
            from src.orchestrator import Orchestrator
            from src.agents import AgentFactory
            from src.archivist import Archivist
            from src.governance import GovernanceEngine

            colony_config = self._get_colony_config(colony_id)
            factory = AgentFactory(
                model_registry=dict(self._config.model_registry),
                config=self._config,
                model_clients=self._model_registry.get_cached_clients(),
                mcp_client=self._mcp_client,
                caste_recipes=self._caste_recipes,
                rag_engine=self._rag_engine,
            )

            agents = []
            ws_root = str(state.workspace)
            for agent_cfg in colony_config.agents:
                agent = factory.create(
                    agent_id=agent_cfg.agent_id,
                    caste=agent_cfg.caste,
                    model_override=agent_cfg.model_override,
                    subcaste_tier=agent_cfg.subcaste_tier,
                    workspace_root=ws_root,
                    colony_id=colony_id,
                )
                agents.append(agent)

            # Create archivist and governance for resumed colony
            archivist = None
            try:
                primary_client, primary_model = self._model_registry.get_client(
                    self._config.inference.model
                )
                archivist = Archivist(primary_client, primary_model, self._config)
            except Exception as exc:
                logger.warning("Failed to create Archivist for colony '%s': %s", colony_id, exc)

            governance = GovernanceEngine(self._config)

            # v0.8.0: Check for durable checkpoint in loaded context tree
            resume_directive = None
            checkpoint_data = state.context_tree.get("colony", "checkpoint")
            if checkpoint_data is not None:
                logger.info(
                    "Colony '%s' has checkpoint at round %d — resuming from checkpoint",
                    colony_id, checkpoint_data.get("completed_round", -1),
                )
                resume_directive = ResumeDirective(
                    colony_id=colony_id,
                    resume_from_round=checkpoint_data["completed_round"] + 1,
                    max_rounds=checkpoint_data["max_rounds"],
                    session_id=checkpoint_data.get("session_id", ""),
                    round_history=checkpoint_data.get("round_history", []),
                    pheromone_weights=checkpoint_data.get("pheromone_weights", {}),
                    convergence_streak=checkpoint_data.get("convergence_streak", 0),
                    prev_summary_vec=checkpoint_data.get("prev_summary_vec"),
                )

            orchestrator = Orchestrator(
                context_tree=state.context_tree,
                config=self._config,
                colony_id=colony_id,
                archivist=archivist,
                governance=governance,
                skill_bank=self._skill_bank,
                audit_logger=self._audit_logger,
                embedder=self._embedder,
                caste_recipes=self._caste_recipes,
                resume_directive=resume_directive,
            )

            # v0.8.0: Wire voting nodes if configured
            colony_config_obj = self._get_colony_config(colony_id)
            if colony_config_obj and colony_config_obj.voting_nodes:
                orchestrator.configure_voting_nodes(colony_config_obj.voting_nodes)

            # Wire webhook dispatcher if colony has a webhook_url
            webhook_url = getattr(state.info, "webhook_url", None)
            if webhook_url and self._webhook_dispatcher:
                orchestrator._webhook_dispatcher = self._webhook_dispatcher
                orchestrator._webhook_url = webhook_url
                orchestrator._client_id = state.info.client_id

            state.orchestrator = orchestrator

            task = asyncio.create_task(
                self._run_colony(
                    colony_id=colony_id,
                    orchestrator=orchestrator,
                    agents=agents,
                    max_rounds=state.info.max_rounds,
                    callbacks=callbacks,
                ),
                name=f"colony-{colony_id}",
            )
            state.task = task

            self._set_status(state, ColonyStatus.RUNNING)
            self._persist_registry_sync()

        logger.info("Colony '%s' resumed (wiring: archivist=%s governance=True skill_bank=%s audit=%s resume=%s)",
                     colony_id, archivist is not None, self._skill_bank is not None,
                     self._audit_logger is not None, resume_directive is not None)

    async def destroy(self, colony_id: str) -> Path:
        """
        Destroy a colony: cancel task, archive session, clean up workspace
        and Qdrant namespace, remove from registry.

        Parameters
        ----------
        colony_id : str
            Colony to destroy.

        Returns
        -------
        Path
            Path to the archive file (if session was archived).

        Raises
        ------
        ColonyNotFoundError
            If colony_id not found.
        """
        state = self._get_state(colony_id)

        # If running, pause first (which cancels the task)
        if state.info.status == ColonyStatus.RUNNING:
            try:
                await self.pause(colony_id)
            except Exception as exc:
                logger.warning(
                    "Error pausing colony '%s' during destroy: %s",
                    colony_id, exc,
                )
                # Force-cancel the task
                if state.task is not None and not state.task.done():
                    state.task.cancel()
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(state.task),
                            timeout=DESTROY_CANCEL_TIMEOUT,
                        )
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass

        # Archive session
        archive_path = Path(".formicos/archive")
        archive_path.mkdir(parents=True, exist_ok=True)
        archive_file = archive_path / f"{colony_id}.json"

        session_file = state.session_file
        if session_file is None:
            session_file = DEFAULT_SESSION_BASE / colony_id / "context.json"

        if session_file.exists():
            try:
                shutil.copy2(str(session_file), str(archive_file))
            except Exception as exc:
                logger.warning(
                    "Failed to archive session for colony '%s': %s",
                    colony_id, exc,
                )

        # Clean up workspace directory
        if state.workspace.exists():
            try:
                shutil.rmtree(str(state.workspace))
            except Exception as exc:
                logger.warning(
                    "Failed to remove workspace for colony '%s': %s",
                    colony_id, exc,
                )

        # Delete Qdrant namespace
        if self._rag_engine is not None:
            try:
                await self._rag_engine.delete_colony_namespace(colony_id)
            except Exception as exc:
                logger.warning(
                    "Failed to delete Qdrant namespace for colony '%s': %s",
                    colony_id, exc,
                )

        # Remove from registry
        async with self._lock:
            self._colonies.pop(colony_id, None)
            self._persist_registry_sync()

        # Clean up V1 event sequence counter
        from src.api.helpers import cleanup_seq
        cleanup_seq(colony_id)

        logger.info("Colony '%s' destroyed. Archive: %s", colony_id, archive_file)
        return archive_file

    async def extend(
        self,
        colony_id: str,
        rounds: int,
        hint: str | None = None,
    ) -> int:
        """
        Extend a running colony by additional rounds.

        Parameters
        ----------
        colony_id : str
            Colony to extend.
        rounds : int
            Number of additional rounds to add.
        hint : str | None
            Optional operator hint injected into the manager prompt.

        Returns
        -------
        int
            The new max_rounds value.

        Raises
        ------
        ColonyNotFoundError
            If colony_id not found.
        """
        state = self._get_state(colony_id)

        new_max = state.info.max_rounds + rounds

        # Forward to orchestrator if running
        if state.orchestrator is not None:
            try:
                new_max = state.orchestrator.extend_rounds(rounds, hint)
            except Exception as exc:
                logger.warning(
                    "extend_rounds failed for colony '%s': %s",
                    colony_id, exc,
                )

        async with self._lock:
            state.info.max_rounds = new_max
            state.info.updated_at = time.time()
            self._persist_registry_sync()

        logger.info(
            "Colony '%s' extended to %d rounds", colony_id, new_max
        )
        return new_max

    async def reuse(
        self,
        colony_id: str,
        task: str,
        max_rounds: int | None = None,
        preserve_history: bool = True,
        clear_workspace: bool = False,
    ) -> ColonyInfo:
        """
        Reuse an existing colony with a new task while optionally preserving context.

        This resets lifecycle status/round so the colony can be started again, but
        keeps the same colony_id and context tree by default.
        """
        if not task or not task.strip():
            raise ColonyConfigError("task must not be empty")

        async with self._lock:
            state = self._get_state(colony_id)
            if state.info.status == ColonyStatus.RUNNING and state.task is not None and not state.task.done():
                raise InvalidTransitionError(
                    "Cannot reuse a running colony. Pause or wait for completion first."
                )

            previous_task = state.info.task
            previous_status = state.info.status.value
            previous_round = state.info.round

        if clear_workspace and state.workspace.exists():
            try:
                shutil.rmtree(str(state.workspace))
                state.workspace.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                logger.warning(
                    "Failed to clear workspace for colony '%s': %s",
                    colony_id, exc,
                )

        async with self._lock:
            state = self._get_state(colony_id)

            state.task = None
            state.orchestrator = None

            state.info.task = task.strip()
            state.info.round = 0
            if max_rounds is not None and max_rounds > 0:
                state.info.max_rounds = max_rounds
            self._set_status(state, ColonyStatus.CREATED)

            if state.colony_config is not None:
                state.colony_config.task = state.info.task
                if max_rounds is not None and max_rounds > 0:
                    state.colony_config.max_rounds = state.info.max_rounds

            ctx = state.context_tree
            await ctx.set("colony", "task", state.info.task)
            await ctx.set("colony", "round", 0)
            await ctx.set("colony", "status", ColonyStatus.CREATED.value)
            await ctx.set("colony", "max_rounds", state.info.max_rounds)
            await ctx.set("colony", "final_answer", None)
            await ctx.set("colony", "error_detail", None)
            await ctx.set("colony", "operator_hint", None)

            if preserve_history:
                reuse_history = ctx.get("colony", "reuse_history", [])
                if not isinstance(reuse_history, list):
                    reuse_history = []
                reuse_history.append({
                    "ts": time.time(),
                    "from_task": previous_task,
                    "from_status": previous_status,
                    "from_round": previous_round,
                    "to_task": state.info.task,
                })
                await ctx.set("colony", "reuse_history", reuse_history)
            else:
                await ctx.set("decisions", "history", [])
                await ctx.set("episodes", "items", [])
                await ctx.set("colony", "topology_history", [])
                await ctx.set("tkg", "tuples", [])
                await ctx.set("epochs", "summaries", [])

            self._persist_registry_sync()

        logger.info(
            "Colony '%s' reused: '%s' -> '%s' (preserve_history=%s clear_workspace=%s)",
            colony_id, previous_task, task.strip(), preserve_history, clear_workspace,
        )
        return state.info

    def get_all(self) -> list[ColonyInfo]:
        """Return public metadata for all colonies."""
        return [s.info for s in self._colonies.values()]

    def get_info(self, colony_id: str) -> ColonyInfo:
        """Return public metadata for a single colony.

        Raises
        ------
        ColonyNotFoundError
            If colony_id not found.
        """
        state = self._get_state(colony_id)
        return state.info

    def get_context(self, colony_id: str) -> AsyncContextTree:
        """
        Return the context tree for a colony.

        Raises
        ------
        ColonyNotFoundError
            If colony_id not found.
        """
        state = self._get_state(colony_id)
        return state.context_tree

    async def spawn_team(
        self,
        colony_id: str,
        directive: TeamConfig,
    ) -> TeamInfo:
        """
        Spawn a new team within a colony.

        Parameters
        ----------
        colony_id : str
            Colony to add the team to.
        directive : TeamConfig
            Team configuration.

        Returns
        -------
        TeamInfo
            Public metadata about the spawned team.

        Raises
        ------
        ColonyNotFoundError
            If colony_id not found.
        """
        state = self._get_state(colony_id)

        team_info = TeamInfo(
            team_id=directive.team_id,
            name=directive.name,
            objective=directive.objective,
            members=list(directive.members),
        )

        async with self._lock:
            # Add to colony info
            if directive.team_id not in state.info.teams:
                state.info.teams.append(directive.team_id)
                state.info.updated_at = time.time()

            # Store team config in context tree
            teams_data = state.context_tree.get("colony", "teams") or {}
            teams_data[directive.team_id] = {
                "name": directive.name,
                "objective": directive.objective,
                "members": list(directive.members),
            }
            await state.context_tree.set("colony", "teams", teams_data)

            self._persist_registry_sync()

        logger.info(
            "Team '%s' spawned in colony '%s'",
            directive.team_id, colony_id,
        )
        return team_info

    async def disband_team(self, colony_id: str, team_id: str) -> None:
        """
        Disband (remove) a team from a colony.

        Parameters
        ----------
        colony_id : str
            Colony containing the team.
        team_id : str
            Team to disband.

        Raises
        ------
        ColonyNotFoundError
            If colony_id not found.
        """
        state = self._get_state(colony_id)

        async with self._lock:
            if team_id in state.info.teams:
                state.info.teams.remove(team_id)
                state.info.updated_at = time.time()

            # Remove from context tree
            teams_data = state.context_tree.get("colony", "teams") or {}
            teams_data.pop(team_id, None)
            await state.context_tree.set("colony", "teams", teams_data)

            self._persist_registry_sync()

        logger.info(
            "Team '%s' disbanded in colony '%s'",
            team_id, colony_id,
        )

    # ── Background Colony Runner ──────────────────────────────────────

    async def _run_colony(
        self,
        colony_id: str,
        orchestrator: Any,
        agents: list,
        max_rounds: int,
        callbacks: dict[str, Any] | None,
    ) -> None:
        """
        Run the orchestrator in a background task.  On completion, update
        colony status to COMPLETED or FAILED.
        """
        try:
            result = await orchestrator.run(
                task=self._colonies[colony_id].info.task,
                agents=agents,
                max_rounds=max_rounds,
                callbacks=callbacks,
            )

            # Determine final status from result
            final_status = ColonyStatus.COMPLETED
            if result is not None and hasattr(result, "status"):
                if result.status == ColonyStatus.FAILED:
                    final_status = ColonyStatus.FAILED

            # Store timeline spans from orchestrator (v0.7.7)
            if hasattr(orchestrator, "_timeline_spans") and orchestrator._timeline_spans:
                try:
                    ctx = self._colonies[colony_id].context_tree
                    timeline = [s.model_dump() for s in orchestrator._timeline_spans]
                    await ctx.set("colony", "timeline_spans", timeline)
                except Exception as tl_exc:
                    logger.warning("Failed to store timeline spans for '%s': %s", colony_id, tl_exc)

            async with self._lock:
                state = self._colonies.get(colony_id)
                if state is not None:
                    self._set_status(state, final_status)
                    # Update round from context tree
                    current_round = state.context_tree.get("colony", "round", 0)
                    state.info.round = current_round if isinstance(current_round, int) else 0
                    # Store final_answer to context tree (backup in case orchestrator missed it)
                    if result is not None and hasattr(result, "final_answer") and result.final_answer:
                        await state.context_tree.set("colony", "final_answer", result.final_answer)
                    self._persist_registry_sync()

        except asyncio.CancelledError:
            logger.info("Colony '%s' orchestrator cancelled", colony_id)
            # Status already set to PAUSED by pause()
        except Exception as exc:
            logger.error(
                "Colony '%s' orchestrator failed: %s", colony_id, exc,
                exc_info=True,
            )
            async with self._lock:
                state = self._colonies.get(colony_id)
                if state is not None:
                    self._set_status(state, ColonyStatus.FAILED)
                    # v0.7.8: Store traceback for diagnostics API
                    import traceback as tb
                    try:
                        await state.context_tree.set(
                            "colony", "error_traceback", tb.format_exc(),
                        )
                    except Exception:
                        pass
                    self._persist_registry_sync()
        finally:
            # v0.7.8: Disable MCP mock mode if it was enabled for test flight
            if self._mcp_client and getattr(self._mcp_client, "_mock_mode", False):
                self._mcp_client.disable_mock_mode()

            # v0.8.0: Close SecuredTopologicalMemory for root_architect agents
            for agent in agents:
                harness = agent.config.get("repl_harness")
                if harness is not None and hasattr(harness, "_memory"):
                    try:
                        harness._memory.close()
                    except Exception:
                        pass

    async def get_diagnostics(self, colony_id: str) -> DiagnosticsPayload:
        """
        v0.7.9: Return a structured diagnostic payload for a colony.
        Designed for consumption by an autonomous Cloud Model debugger.
        Returns DiagnosticsPayload (Pydantic model) instead of raw dict.
        """
        state = self._get_state(colony_id)
        ctx = state.context_tree

        # Gather data from context tree
        error_traceback = ctx.get("colony", "error_traceback")
        decisions = list(ctx._decisions[-10:]) if hasattr(ctx, "_decisions") else []
        episodes = list(ctx._episodes[-10:]) if hasattr(ctx, "_episodes") else []
        epoch_summaries = [
            es.model_dump() if hasattr(es, "model_dump") else str(es)
            for es in ctx.get_epoch_summaries()
        ] if hasattr(ctx, "get_epoch_summaries") else []
        timeline_spans = ctx.get("colony", "timeline_spans") or []

        # Hardware state
        from src.worker import WorkerManager
        free_vram = WorkerManager.get_free_vram_mb()

        return DiagnosticsPayload(
            colony_id=colony_id,
            status=state.info.status.value if hasattr(state.info.status, "value") else str(state.info.status),
            round=state.info.round,
            max_rounds=state.info.max_rounds,
            created_at=state.info.created_at,
            origin=state.info.origin,
            client_id=state.info.client_id,
            hardware_state=HardwareState(free_vram_mb=free_vram),
            error_traceback=error_traceback,
            last_decisions=[
                d.model_dump() if hasattr(d, "model_dump") else str(d)
                for d in decisions
            ],
            last_episodes=[
                e.model_dump() if hasattr(e, "model_dump") else str(e)
                for e in episodes
            ],
            epoch_summaries=epoch_summaries,
            timeline_spans=timeline_spans[-10:] if isinstance(timeline_spans, list) else [],
        )

    # ── Internal Helpers ──────────────────────────────────────────────

    def _get_state(self, colony_id: str) -> _ColonyState:
        """Retrieve colony state or raise ColonyNotFoundError."""
        state = self._colonies.get(colony_id)
        if state is None:
            raise ColonyNotFoundError(
                f"Colony '{colony_id}' not found in registry"
            )
        return state

    def _get_colony_config(self, colony_id: str) -> ColonyConfig:
        """
        Retrieve the original ColonyConfig for a colony.

        Falls back to building a minimal config from the stored ColonyInfo.
        """
        # Check stored colony state first (dashboard runs store config here)
        state = self._get_state(colony_id)
        if state.colony_config is not None:
            return state.colony_config

        # Check if config stores colony definitions
        if hasattr(self._config, "colonies") and colony_id in self._config.colonies:
            return self._config.colonies[colony_id]

        # Reconstruct minimal config from stored info (last resort)
        return ColonyConfig(
            colony_id=colony_id,
            task=state.info.task,
            agents=[],
            max_rounds=state.info.max_rounds,
        )

    def _validate_config(self, colony_config: ColonyConfig) -> None:
        """
        Validate colony configuration.

        Raises ColonyConfigError on failure.
        """
        # Validate model_override references exist in registry
        for agent in colony_config.agents:
            if agent.model_override:
                if not self._model_registry.has_model(agent.model_override):
                    raise ColonyConfigError(
                        f"Agent '{agent.agent_id}' references unknown model "
                        f"'{agent.model_override}'. "
                        f"Registered: {self._model_registry.model_ids}"
                    )

        # Validate manager model override if present
        if colony_config.manager and colony_config.manager.model_override:
            if not self._model_registry.has_model(colony_config.manager.model_override):
                raise ColonyConfigError(
                    f"Manager references unknown model "
                    f"'{colony_config.manager.model_override}'"
                )

    @staticmethod
    def _validate_transition(
        current: ColonyStatus, target: ColonyStatus,
    ) -> None:
        """
        Validate that a state transition is allowed.

        Raises InvalidTransitionError on illegal transition.
        """
        allowed = VALID_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition from {current.value} to {target.value}. "
                f"Allowed: {sorted(s.value for s in allowed)}"
            )

    @staticmethod
    def _set_status(state: _ColonyState, new_status: ColonyStatus) -> None:
        """Update colony status and timestamp."""
        state.info.status = new_status
        state.info.updated_at = time.time()

    # ── Registry Persistence ──────────────────────────────────────────

    def _persist_registry_sync(self) -> None:
        """
        Persist the colony registry to JSON.

        Called under self._lock.  Uses synchronous I/O since this is called
        within async lock context and the data is small.
        """
        registry_data = {}
        for cid, state in self._colonies.items():
            registry_data[cid] = state.info.model_dump()

        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._registry_path, "w", encoding="utf-8") as f:
                json.dump(registry_data, f, indent=2, default=str)
        except Exception as exc:
            logger.error(
                "Failed to persist colony registry: %s", exc,
            )

    def _load_registry_sync(self) -> None:
        """
        Load the persisted colony registry from JSON on startup.

        Creates _ColonyState entries with fresh AsyncContextTrees for
        each colony found.  Colonies in RUNNING state are treated as
        crashed (set to PAUSED) since there is no live task.
        """
        if not self._registry_path.exists():
            return

        try:
            with open(self._registry_path, encoding="utf-8") as f:
                registry_data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "Failed to load colony registry: %s", exc,
            )
            return

        for colony_id, info_data in registry_data.items():
            try:
                info = ColonyInfo.model_validate(info_data)

                # Colonies found in RUNNING state without a live task are crashed
                has_checkpoint = False
                if info.status == ColonyStatus.RUNNING:
                    # v0.8.0: Check if session file contains a checkpoint
                    session_file = DEFAULT_SESSION_BASE / colony_id / "context.json"
                    if session_file.exists():
                        try:
                            with open(session_file, encoding="utf-8") as sf:
                                session_data = json.load(sf)
                            # Checkpoint is stored at colony.checkpoint in ctx
                            colony_scope = session_data.get("colony", {})
                            if isinstance(colony_scope, dict) and "checkpoint" in colony_scope:
                                has_checkpoint = True
                                logger.info(
                                    "Colony '%s' crashed with checkpoint at round %d — "
                                    "eligible for auto-resume",
                                    colony_id,
                                    colony_scope["checkpoint"].get("completed_round", -1),
                                )
                        except (json.JSONDecodeError, OSError):
                            pass

                    logger.warning(
                        "Colony '%s' was RUNNING at shutdown -- treating as PAUSED"
                        " (checkpoint=%s)",
                        colony_id, has_checkpoint,
                    )
                    info.status = ColonyStatus.PAUSED

                workspace = self._workspace_base / colony_id
                state = _ColonyState(
                    info=info,
                    context_tree=AsyncContextTree(),
                    workspace=workspace,
                    needs_crash_resume=has_checkpoint,
                )

                # Check for saved session file
                session_file = DEFAULT_SESSION_BASE / colony_id / "context.json"
                if session_file.exists():
                    state.session_file = session_file

                self._colonies[colony_id] = state

            except Exception as exc:
                logger.warning(
                    "Skipping corrupt registry entry '%s': %s",
                    colony_id, exc,
                )

    # ── Durable Execution: Auto-Resume (v0.8.0) ─────────────────────

    async def auto_resume_crashed(
        self,
        callbacks: dict[str, Any] | None = None,
    ) -> list[str]:
        """Auto-resume colonies that crashed with a valid checkpoint.

        Called during lifespan startup after ``_load_registry_sync()`` has
        populated the registry.  Iterates colonies with
        ``needs_crash_resume=True`` and attempts to resume each from its
        last checkpoint.

        Returns
        -------
        list[str]
            Colony IDs that were successfully resumed.
        """
        resumed: list[str] = []
        candidates = [
            cid for cid, state in self._colonies.items()
            if state.needs_crash_resume
        ]

        for colony_id in candidates:
            try:
                await self._resume_from_checkpoint(colony_id, callbacks)
                resumed.append(colony_id)
            except Exception as exc:
                logger.error(
                    "Auto-resume failed for colony '%s': %s",
                    colony_id, exc,
                )
                # Clear flag so we don't retry endlessly
                state = self._colonies.get(colony_id)
                if state:
                    state.needs_crash_resume = False

        return resumed

    async def _resume_from_checkpoint(
        self,
        colony_id: str,
        callbacks: dict[str, Any] | None = None,
    ) -> None:
        """Resume a single colony from its durable checkpoint.

        Loads the context tree, extracts ``CheckpointMeta`` from the
        colony scope, builds a ``ResumeDirective``, and launches the
        orchestrator from the last completed round.
        """
        state = self._get_state(colony_id)
        session_file = state.session_file
        if session_file is None:
            session_file = DEFAULT_SESSION_BASE / colony_id / "context.json"

        # Load context tree from saved session
        if not session_file.exists():
            raise FileNotFoundError(
                f"Session file not found for colony '{colony_id}': {session_file}"
            )

        state.context_tree = await AsyncContextTree.load(session_file)

        # Extract checkpoint from context tree
        checkpoint_data = state.context_tree.get("colony", "checkpoint")
        if checkpoint_data is None:
            raise ValueError(
                f"No checkpoint found in session file for colony '{colony_id}'"
            )

        # Build ResumeDirective
        resume_directive = ResumeDirective(
            colony_id=colony_id,
            resume_from_round=checkpoint_data["completed_round"] + 1,
            max_rounds=checkpoint_data["max_rounds"],
            session_id=checkpoint_data.get("session_id", ""),
            round_history=checkpoint_data.get("round_history", []),
            pheromone_weights=checkpoint_data.get("pheromone_weights", {}),
            convergence_streak=checkpoint_data.get("convergence_streak", 0),
            prev_summary_vec=checkpoint_data.get("prev_summary_vec"),
        )

        async with self._lock:
            from src.orchestrator import Orchestrator
            from src.agents import AgentFactory
            from src.archivist import Archivist
            from src.governance import GovernanceEngine

            colony_config = self._get_colony_config(colony_id)
            factory = AgentFactory(
                model_registry=dict(self._config.model_registry),
                config=self._config,
                model_clients=self._model_registry.get_cached_clients(),
                mcp_client=self._mcp_client,
                caste_recipes=self._caste_recipes,
                rag_engine=self._rag_engine,
            )

            agents = []
            ws_root = str(state.workspace)
            for agent_cfg in colony_config.agents:
                agent = factory.create(
                    agent_id=agent_cfg.agent_id,
                    caste=agent_cfg.caste,
                    model_override=agent_cfg.model_override,
                    subcaste_tier=agent_cfg.subcaste_tier,
                    workspace_root=ws_root,
                    colony_id=colony_id,
                )
                agents.append(agent)

            # Create archivist and governance
            archivist = None
            try:
                primary_client, primary_model = self._model_registry.get_client(
                    self._config.inference.model
                )
                archivist = Archivist(primary_client, primary_model, self._config)
            except Exception as exc:
                logger.warning(
                    "Failed to create Archivist for auto-resume colony '%s': %s",
                    colony_id, exc,
                )

            governance = GovernanceEngine(self._config)

            orchestrator = Orchestrator(
                context_tree=state.context_tree,
                config=self._config,
                colony_id=colony_id,
                archivist=archivist,
                governance=governance,
                skill_bank=self._skill_bank,
                audit_logger=self._audit_logger,
                embedder=self._embedder,
                caste_recipes=self._caste_recipes,
                resume_directive=resume_directive,
            )

            # Wire voting nodes if configured
            if colony_config.voting_nodes:
                orchestrator.configure_voting_nodes(colony_config.voting_nodes)

            # Wire webhook dispatcher
            webhook_url = getattr(state.info, "webhook_url", None)
            if webhook_url and self._webhook_dispatcher:
                orchestrator._webhook_dispatcher = self._webhook_dispatcher
                orchestrator._webhook_url = webhook_url
                orchestrator._client_id = state.info.client_id

            state.orchestrator = orchestrator

            task = asyncio.create_task(
                self._run_colony(
                    colony_id=colony_id,
                    orchestrator=orchestrator,
                    agents=agents,
                    max_rounds=state.info.max_rounds,
                    callbacks=callbacks,
                ),
                name=f"colony-{colony_id}",
            )
            state.task = task

            # Clear crash flag, update status
            state.needs_crash_resume = False
            self._set_status(state, ColonyStatus.RUNNING)
            self._persist_registry_sync()

        logger.info(
            "Colony '%s' auto-resumed from checkpoint (round %d/%d)",
            colony_id, resume_directive.resume_from_round,
            resume_directive.max_rounds,
        )
