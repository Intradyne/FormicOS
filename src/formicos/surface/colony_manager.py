"""Colony lifecycle manager â€" runs colony round loops as background tasks.

Lives in surface/ because it depends on runtime, projections, and adapters.
Engine imports only core.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import structlog

from formicos.adapters.code_analysis import WorkspaceStructure, analyze_workspace
from formicos.core.events import (
    ColonyCompleted,
    ColonyEscalated,
    ColonyFailed,
    ColonyServiceActivated,
    ColonyTemplateCreated,
    MemoryConfidenceUpdated,
    MemoryEntryStatusChanged,
)
from formicos.core.types import AccessMode, ColonyContext
from formicos.engine.context import TierBudgets as EngineTierBudgets
from formicos.engine.runner import (
    CodeExecuteHandler,
    RoundRunner,
    RunnerCallbacks,
    ToolExecutionResult,
)
from formicos.engine.service_router import ServiceRouter
from formicos.engine.strategies.sequential import SequentialStrategy
from formicos.engine.strategies.stigmergic import StigmergicStrategy
from formicos.surface.artifact_extractor import extract_artifacts
from formicos.surface.knowledge_constants import (
    GAMMA_PER_DAY,
    GAMMA_RATES,
    MAX_ELAPSED_DAYS,
    PRIOR_ALPHA,
    PRIOR_BETA,
)

# Wave 56: auto-promote candidate â†' verified after sustained successful usage.
# Alpha starts at 5.0 (PRIOR_ALPHA). Each successful access adds 0.5â€"1.5.
# Threshold 8.0 â‰ˆ 6 successful accesses at minimum delta.
_PROMOTION_ALPHA_THRESHOLD = 8.0

if TYPE_CHECKING:
    from formicos.surface.runtime import Runtime

# Legacy confidence updates disabled (Wave 28).
# SkillConfidenceUpdated import and _HAS_CONFIDENCE_EVENT flag removed.

log = structlog.get_logger()


def _log_task_exception(task: asyncio.Task[Any]) -> None:
    """Error callback for fire-and-forget tasks."""
    if not task.cancelled() and task.exception() is not None:
        log.error(
            "fire_and_forget_failed",
            task_name=task.get_name(),
            error=str(task.exception()),
        )


def _safe_data_dir(runtime: Any) -> str:
    """Extract data_dir from runtime settings, returning '' on mock or missing."""
    try:
        val = runtime.settings.system.data_dir
        return val if isinstance(val, str) else ""
    except (AttributeError, TypeError):
        return ""


def _build_code_execute_handler() -> CodeExecuteHandler:
    """Build an injectable code_execute handler (engineâ†'adapters boundary)."""
    import time as _time

    from formicos.adapters.ast_security import check_ast_safety
    from formicos.adapters.output_sanitizer import sanitize_output
    from formicos.adapters.sandbox_manager import execute_sandboxed
    from formicos.core.events import (
        CodeExecuted,
        ColonyChatMessage,
        FormicOSEvent,
    )

    async def _handle(
        arguments: dict[str, Any],
        colony_id: str,
        agent_id: str,
        address: str,
        emit_fn: Callable[[FormicOSEvent], Any],
    ) -> ToolExecutionResult:
        code = arguments.get("code", "")
        timeout_s = min(arguments.get("timeout_s", 10), 30)

        # AST safety screen
        ast_result = check_ast_safety(code)
        if not ast_result.safe:
            # Emit blocked event
            ev = emit_fn(CodeExecuted(
                seq=0,
                timestamp=datetime.now(UTC),
                address=address,
                colony_id=colony_id,
                agent_id=agent_id,
                code_preview=code[:200],
                trust_tier="STANDARD",
                exit_code=-1,
                duration_ms=0.0,
                blocked=True,
            ))
            if asyncio.iscoroutine(ev):
                await ev
            return ToolExecutionResult(
                content=f"Code blocked: {ast_result.reason}",
                code_execute_failed=True,
            )

        # Execute in sandbox
        t0 = _time.monotonic()
        exec_result = await execute_sandboxed(
            code, timeout_s=timeout_s,
        )
        duration_ms = ((_time.monotonic() - t0) * 1000)
        output = sanitize_output(
            exec_result.stdout + exec_result.stderr,
        )

        # Emit CodeExecuted event
        ev = emit_fn(CodeExecuted(
            seq=0,
            timestamp=datetime.now(UTC),
            address=address,
            colony_id=colony_id,
            agent_id=agent_id,
            code_preview=code[:200],
            trust_tier="STANDARD",
            exit_code=exec_result.exit_code,
            stdout_preview=exec_result.stdout[:500],
            stderr_preview=exec_result.stderr[:500],
            duration_ms=duration_ms,
        ))
        if asyncio.iscoroutine(ev):
            await ev

        # Emit operator-facing chat summary
        workspace_id = address.split("/", 1)[0] if "/" in address else ""
        summary = (
            f"Code executed (exit={exec_result.exit_code}): "
            f"{code[:80]}..."
        )
        chat_ev = emit_fn(ColonyChatMessage(
            seq=0,
            timestamp=datetime.now(UTC),
            address=address,
            colony_id=colony_id,
            workspace_id=workspace_id,
            sender="system",
            event_kind="code_executed",
            content=summary,
            agent_id=agent_id,
            caste="",
        ))
        if asyncio.iscoroutine(chat_ev):
            await chat_ev

        return ToolExecutionResult(
            content=output,
            code_execute_succeeded=(exec_result.exit_code == 0),
            code_execute_failed=(exec_result.exit_code != 0),
        )

    return _handle


def _build_workspace_execute_handler(
    data_dir: str,
) -> Callable[..., Any]:
    """Build an injectable workspace_execute handler (Wave 41 B1).

    Returns an async callable (command, workspace_id, timeout_s) that
    executes commands in the workspace directory with structured output.
    """
    from pathlib import Path

    from formicos.adapters.sandbox_manager import execute_workspace_command
    from formicos.core.types import WorkspaceExecutionResult

    async def _handle(
        command: str,
        workspace_id: str,
        timeout_s: int,
    ) -> WorkspaceExecutionResult:
        # Resolve workspace working directory
        ws_dir = str(Path(data_dir) / "workspaces" / workspace_id / "files")
        return await execute_workspace_command(command, ws_dir, timeout_s)

    return _handle


def _now() -> datetime:
    return datetime.now(UTC)


def _cm_cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity (Wave 60 semantic gate). Module-private duplicate."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Wave 42: Conjunctive extraction quality gate
# ---------------------------------------------------------------------------

# Thresholds â€" tuned to catch noise without blocking useful concise entries
_SHORT_CONTENT_CHARS = 40
_SHORT_TITLE_CHARS = 15
_GENERIC_PHRASES = frozenset({
    "general knowledge", "common practice", "best practice",
    "standard approach", "typical pattern", "well known",
    "as expected", "nothing special", "no issues",
})


def _check_extraction_quality(entry: dict[str, Any]) -> str:
    """Conjunctive quality gate for extracted knowledge entries.

    Returns empty string if the entry passes, or a reason string if it
    should be skipped. Uses conjunctive rules â€" no single signal alone
    causes rejection.

    Wave 42 Pillar 5: extraction quality gating.
    """
    content = str(entry.get("content", ""))
    title = str(entry.get("title", ""))
    summary = str(entry.get("summary", ""))
    domains = entry.get("domains", [])

    # Signal: content length
    is_short = len(content.strip()) < _SHORT_CONTENT_CHARS
    # Signal: title length
    has_weak_title = len(title.strip()) < _SHORT_TITLE_CHARS
    # Signal: generic/boilerplate phrasing
    combined_lower = f"{title} {summary} {content}".lower()
    has_generic_phrase = any(p in combined_lower for p in _GENERIC_PHRASES)
    # Signal: no domain tags
    has_no_domains = not domains or all(not str(d).strip() for d in domains)
    # Signal: empty or near-empty content
    is_empty = len(content.strip()) < 5

    # Rule 1: empty content â€" always reject
    if is_empty:
        return "empty_content"

    # Rule 2: short AND generic phrasing (conjunctive)
    if is_short and has_generic_phrase:
        return "short_and_generic"

    # Rule 3: short AND weak title AND no domains (triple conjunctive)
    if is_short and has_weak_title and has_no_domains:
        return "short_weak_title_no_domains"

    # Rule 4: generic phrasing AND no domains AND weak title (triple conjunctive)
    if has_generic_phrase and has_no_domains and has_weak_title:
        return "generic_no_domains_weak_title"

    return ""


# ---------------------------------------------------------------------------

def compute_quality_score(
    rounds_completed: int,
    max_rounds: int,
    convergence: float,
    governance_warnings: int,
    stall_rounds: int,
    completed_successfully: bool,
    productive_calls: int = 0,
    total_calls: int = 0,
) -> float:
    """Composite quality score in [0.0, 1.0] using weighted geometric mean (ADR-011).

    Wave 54.5: added productive_ratio signal so quality reflects actual tool
    productivity, not just round/convergence structure.  Round-efficiency floor
    raised from 0.01 to 0.20 so colonies that use all rounds aren't penalised
    to near-zero.
    """
    if not completed_successfully:
        return 0.0

    round_efficiency = max(1.0 - (rounds_completed / max(max_rounds, 1)), 0.20)
    convergence_score = max(convergence, 0.01)
    governance_score = max(1.0 - (governance_warnings / 3.0), 0.01)
    stall_score = max(1.0 - (stall_rounds / max(rounds_completed, 1)), 0.01)
    productive_ratio = (
        max(productive_calls / total_calls, 0.01) if total_calls > 0 else 0.01
    )

    w = {"re": 0.20, "cs": 0.25, "gs": 0.20, "ss": 0.15, "pr": 0.20}
    log_sum = (
        w["re"] * math.log(round_efficiency)
        + w["cs"] * math.log(convergence_score)
        + w["gs"] * math.log(governance_score)
        + w["ss"] * math.log(stall_score)
        + w["pr"] * math.log(productive_ratio)
    )
    return round(math.exp(log_sum), 4)


# Wave 39 1C: tier ordering for auto-escalation
_TIER_ORDER = ("light", "standard", "heavy")


def _next_available_tier(castes: list[Any]) -> str | None:
    """Return the next heavier tier above the colony's starting tier, or None.

    Derives the starting tier from the actual spawned caste slots. If a heavier
    tier exists in the ordering, returns it. Returns None if the colony is
    already at the heaviest tier or has no castes.
    """
    if not castes:
        current = "standard"
    else:
        tiers = {str(getattr(c, "tier", "standard")) for c in castes}
        # Use the heaviest tier present as the starting point
        current = "standard"
        for t in _TIER_ORDER:
            if t in tiers:
                current = t
    try:
        idx = _TIER_ORDER.index(current)
    except ValueError:
        return None
    if idx + 1 < len(_TIER_ORDER):
        return _TIER_ORDER[idx + 1]
    return None


def _tier_to_model_address(runtime: Any, workspace_id: str, tier: str) -> str:
    """Resolve the model address a tier escalation would actually target."""
    if tier == "standard":
        return runtime.resolve_model("coder", workspace_id)
    tier_map = {
        "heavy": "anthropic/claude-sonnet-4-6",
        "max": "anthropic/claude-opus-4-6",
    }
    return tier_map.get(tier, runtime.resolve_model("coder", workspace_id))


def _tier_is_viable(runtime: Any, workspace_id: str, tier: str) -> bool:
    """Return True when the tier points to a live, non-cooled provider."""
    model = _tier_to_model_address(runtime, workspace_id, tier)
    prefix = model.split("/", 1)[0]
    router = getattr(runtime, "llm_router", None)
    if router is None:
        return True
    adapters = getattr(router, "_adapters", {})
    if prefix not in adapters:
        return False
    cooldown = getattr(router, "_cooldown", None)
    return not (cooldown is not None and cooldown.is_cooled_down(prefix))


def _next_viable_tier(
    castes: list[Any],
    runtime: Any,
    workspace_id: str,
) -> str | None:
    """Return the next heavier tier that has a viable provider."""
    current = "standard"
    if castes:
        tiers = {str(getattr(c, "tier", "standard")) for c in castes}
        for tier in _TIER_ORDER:
            if tier in tiers:
                current = tier
    try:
        idx = _TIER_ORDER.index(current)
    except ValueError:
        return None
    for candidate in _TIER_ORDER[idx + 1:]:
        if _tier_is_viable(runtime, workspace_id, candidate):
            return candidate
    return None


class ColonyManager:
    """Manages colony lifecycle â€" each colony runs as an asyncio.Task."""

    def __init__(self, runtime: Runtime) -> None:
        self._runtime = runtime
        self._active: dict[str, asyncio.Task[None]] = {}
        self._service_router = ServiceRouter(inject_fn=self.inject_message)
        # Injected messages queue â€" operator messages to be included in next round context
        self._injected_messages: dict[str, list[dict[str, Any]]] = {}

    @property
    def service_router(self) -> ServiceRouter:
        return self._service_router

    async def start_colony(self, colony_id: str) -> None:
        """Start a colony's round loop as a background task."""
        colony = self._runtime.projections.get_colony(colony_id)
        if colony is None or colony_id in self._active:
            return
        if colony.status != "running":
            return

        # Queen naming â€" fire-and-forget (ADR-016)
        _naming_task = asyncio.create_task(self._name_colony(colony_id))
        _naming_task.add_done_callback(_log_task_exception)

        task = asyncio.create_task(self._run_colony(colony_id))
        self._active[colony_id] = task
        task.add_done_callback(lambda _t: self._active.pop(colony_id, None))
        log.info("colony_manager.started", colony_id=colony_id)

    async def stop_colony(self, colony_id: str) -> None:
        """Cancel a running colony's round loop."""
        task = self._active.pop(colony_id, None)
        if task:
            task.cancel()
            log.info("colony_manager.stopped", colony_id=colony_id)

    async def rehydrate(self) -> None:
        """Best-effort restart of colonies that were running when server stopped."""
        for colony in self._runtime.projections.colonies.values():
            if colony.status == "running" and colony.id not in self._active:
                log.info("colony_manager.rehydrating", colony_id=colony.id)
                await self.start_colony(colony.id)

    @property
    def active_count(self) -> int:
        return len(self._active)

    async def inject_message(
        self,
        colony_id: str,
        message: str,
        *,
        directive_type: str | None = None,
        directive_priority: str = "normal",
    ) -> None:
        """Queue a message for injection into a colony's next round context."""
        if colony_id not in self._injected_messages:
            self._injected_messages[colony_id] = []
        entry: dict[str, Any] = {"content": message}
        if directive_type is not None:
            entry["directive_type"] = directive_type
            entry["directive_priority"] = directive_priority
        self._injected_messages[colony_id].append(entry)
        log.info(
            "colony_manager.message_injected",
            colony_id=colony_id,
            directive_type=directive_type,
        )

    def drain_injected_messages(self, colony_id: str) -> list[dict[str, Any]]:
        """Drain and return any pending injected messages for a colony."""
        return self._injected_messages.pop(colony_id, [])

    async def activate_service(self, colony_id: str, service_type: str) -> None:
        """Activate a completed colony as a service colony."""
        colony = self._runtime.projections.get_colony(colony_id)
        if colony is None:
            msg = f"Colony '{colony_id}' not found"
            raise ValueError(msg)
        if colony.status != "completed":
            msg = "Colony must be completed before activation"
            raise ValueError(msg)

        # Register in service router
        self._service_router.register(service_type, colony_id)

        # Update projection status
        colony.status = "service"

        # Emit activation event
        address = f"{colony.workspace_id}/{colony.thread_id}/{colony_id}"
        await self._runtime.emit_and_broadcast(ColonyServiceActivated(
            seq=0, timestamp=_now(), address=address,
            colony_id=colony_id,
            workspace_id=colony.workspace_id,
            service_type=service_type,
            agent_count=len(colony.agents),
            skill_count=colony.skills_extracted,
        ))

        log.info(
            "colony_manager.service_activated",
            colony_id=colony_id, service_type=service_type,
        )

    async def _name_colony(self, colony_id: str) -> None:
        """Ask Queen to name this colony. Fire-and-forget, errors logged."""
        try:
            colony = self._runtime.projections.get_colony(colony_id)
            if colony is None:
                return
            queen = self._runtime.queen
            if queen is None:
                return
            await queen.name_colony(
                colony_id=colony_id,
                task=colony.task,
                workspace_id=colony.workspace_id,
                thread_id=colony.thread_id,
            )
        except Exception:  # noqa: BLE001
            log.debug("colony_manager.naming_failed", colony_id=colony_id)

    # ===================================================================
    # Section 1: Colony round loop
    # ===================================================================

    async def _run_colony(self, colony_id: str) -> None:
        """Execute rounds until governance terminates the colony.

        On exit (any path), pushes a fresh state snapshot to workspace
        subscribers so derived fields like qualityScore and skillsExtracted
        are visible immediately without waiting for a manual reconnect.
        """
        colony = self._runtime.projections.get_colony(colony_id)
        if colony is None:
            return

        workspace_id = colony.workspace_id
        try:
            await self._run_colony_inner(colony_id)
        finally:
            # Push updated snapshot so qualityScore / skillsExtracted appear live
            try:
                await self._runtime.ws_manager.send_state_to_workspace(workspace_id)
            except Exception:  # noqa: BLE001
                log.debug("colony_manager.state_push_failed", colony_id=colony_id)

    async def _run_colony_inner(self, colony_id: str) -> None:
        """Core round loop â€" extracted so _run_colony can wrap with try/finally."""
        import time as _time  # noqa: PLC0415

        colony = self._runtime.projections.get_colony(colony_id)
        if colony is None:
            return

        agents = self._runtime.build_agents(colony_id)
        if not agents:
            log.warning("colony_manager.no_agents", colony_id=colony_id)
            await self._runtime.emit_and_broadcast(ColonyFailed(
                seq=0, timestamp=_now(),
                address=f"{colony.workspace_id}/{colony.thread_id}/{colony.id}",
                colony_id=colony_id, reason="No agents could be built from caste recipes",
            ))
            return

        strategy = self._make_strategy(colony.strategy)
        address = f"{colony.workspace_id}/{colony.thread_id}/{colony.id}"

        # Map settings context config â†' engine TierBudgets (keeps engine config-agnostic)
        ctx_cfg = self._runtime.settings.context
        engine_budgets = EngineTierBudgets(
            goal=ctx_cfg.tier_budgets.goal,
            routed_outputs=ctx_cfg.tier_budgets.routed_outputs,
            max_per_source=ctx_cfg.tier_budgets.max_per_source,
            merge_summaries=ctx_cfg.tier_budgets.merge_summaries,
            prev_round_summary=ctx_cfg.tier_budgets.prev_round_summary,
            skill_bank=ctx_cfg.tier_budgets.skill_bank,
            compaction_threshold=ctx_cfg.compaction_threshold,
        )

        # Build route_fn closure (ADR-012, T1 seam)
        def _route_fn(
            caste: str, phase: str, round_num: int, budget_remaining: float,
        ) -> str:
            default = self._runtime.resolve_model(caste, colony.workspace_id)
            # Wave 43: workspace-level model downgrade when approaching budget
            if _budget_enforcer.check_model_downgrade(
                colony.workspace_id, budget_remaining,
            ):
                cheapest = self._runtime.llm_router._cheapest  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
                if cheapest:
                    return cheapest
            return self._runtime.llm_router.route(
                caste=caste, phase=phase, round_num=round_num,
                budget_remaining=budget_remaining, default_model=default,
            )

        # Build async_embed_fn from embed_client (ADR-025)
        async_embed_fn = None
        if self._runtime.embed_client is not None:
            async_embed_fn = self._runtime.embed_client.embed

        runner = RoundRunner(RunnerCallbacks(
            emit=self._runtime.emit_and_broadcast,
            embed_fn=self._runtime.embed_fn,
            async_embed_fn=async_embed_fn,
            cost_fn=self._runtime.cost_fn,
            tier_budgets=engine_budgets,
            route_fn=_route_fn,
            kg_adapter=self._runtime.kg_adapter,
            max_rounds=colony.max_rounds,
            code_execute_handler=_build_code_execute_handler(),
            workspace_execute_handler=_build_workspace_execute_handler(
                data_dir=_safe_data_dir(self._runtime),
            ),
            data_dir=_safe_data_dir(self._runtime),
            service_router=self._service_router,
            catalog_search_fn=self._runtime.make_catalog_search_fn(),
            knowledge_detail_fn=self._runtime.make_knowledge_detail_fn(),
            artifact_inspect_fn=self._runtime.make_artifact_inspect_fn(),
            transcript_search_fn=self._runtime.make_transcript_search_fn(),
            knowledge_feedback_fn=self._runtime.make_knowledge_feedback_fn(
                colony_id=colony_id,
                workspace_id=colony.workspace_id,
                thread_id=colony.thread_id,
            ),
            forage_fn=self._runtime.make_forage_fn(),
        ))

        pheromone_weights: dict[tuple[str, str], float] = {}
        prev_summary: str | None = None
        stall_count = 0
        recent_successful_code_execute = False
        recent_productive_action = False  # Wave 55: broader than code_execute
        governance_warnings = 0
        total_productive_calls = 0  # Wave 54.5
        total_total_calls = 0  # Wave 54.5
        total_cost = 0.0
        last_convergence = 0.0
        retrieved_skill_ids: set[str] = set()
        redirect_boundaries: list[int] = list(
            getattr(colony, "redirect_boundaries", []),
        )
        start_round = colony.round_number + 1 if colony.round_number > 0 else 1

        # Fetch unified knowledge for agent context injection (Wave 28 A1)
        _prev_goal = colony.task
        knowledge_items = await self._runtime.fetch_knowledge_for_colony(
            task=colony.task, workspace_id=colony.workspace_id,
            thread_id=colony.thread_id, top_k=8,
        )

        # Wave 42 P1 / Wave 47: structural analysis
        # Initial analysis runs once; per-round refresh for colonies with target_files
        _ws_dir = _safe_data_dir(self._runtime)
        _target = list(getattr(colony, "target_files", []))
        workspace_structure = _analyze_workspace_safe(_ws_dir)
        _structural_ctx = workspace_structure.relevant_context(_target) if _target else ""
        _structural_deps = _extract_deps_subset(workspace_structure, _target)

        # Wave 54: load task-class-keyed operational playbook
        from formicos.engine.playbook_loader import clear_cache as _pb_clear  # noqa: PLC0415
        from formicos.engine.playbook_loader import load_playbook  # noqa: PLC0415
        from formicos.surface.task_classifier import classify_task  # noqa: PLC0415

        _task_class_name, _task_cat = classify_task(colony.task)
        # Use the first caste's name for playbook selection
        _primary_caste = agents[0].caste if agents else "coder"
        _operational_playbook = load_playbook(_task_class_name, _primary_caste)

        # Wave 43: workspace-level budget enforcement
        from formicos.surface.runtime import BudgetEnforcer  # noqa: PLC0415

        _budget_enforcer = BudgetEnforcer(self._runtime.projections)

        for round_num in range(start_round, colony.max_rounds + 1):
            # Re-check colony status (may have been killed)
            fresh = self._runtime.projections.get_colony(colony_id)
            if fresh is None or fresh.status != "running":
                return

            # Wave 43: workspace-level hard stop (checked each round)
            ws_stop, ws_reason = _budget_enforcer.check_workspace_hard_stop(
                colony.workspace_id,
            )
            if ws_stop:
                log.warning(
                    "colony_manager.workspace_budget_exhausted",
                    colony_id=colony_id,
                    workspace_id=colony.workspace_id,
                )
                await self._runtime.emit_and_broadcast(ColonyFailed(
                    seq=0, timestamp=_now(), address=address,
                    colony_id=colony_id,
                    reason=ws_reason,
                ))
                return

            # Prefer active_goal (set by redirect) over immutable task
            _active = getattr(fresh, "active_goal", None)
            goal = _active if isinstance(_active, str) and _active else colony.task

            # Re-fetch knowledge and playbook on goal change (redirect / active-goal shift)
            if goal != _prev_goal:
                knowledge_items = await self._runtime.fetch_knowledge_for_colony(
                    task=goal, workspace_id=colony.workspace_id,
                    thread_id=colony.thread_id, top_k=8,
                )
                # Wave 54: re-classify and re-load playbook for new goal
                _task_class_name, _task_cat = classify_task(goal)
                _pb_clear()  # invalidate since task class may have changed
                _operational_playbook = load_playbook(_task_class_name, _primary_caste)
                _prev_goal = goal

            # Wave 47: per-round structural refresh for coding colonies
            # Only colonies with target_files pay this cost (round > 1 only,
            # since the initial analysis already covers round 1).
            if _target and round_num > start_round:
                workspace_structure = _analyze_workspace_safe(_ws_dir)
                _structural_ctx = workspace_structure.relevant_context(_target)
                _structural_deps = _extract_deps_subset(workspace_structure, _target)

            # Drain any operator directives queued since last round (Wave 35 C1)
            drained = self.drain_injected_messages(colony_id)
            directives = [m for m in drained if m.get("directive_type")]

            context = ColonyContext(
                colony_id=colony_id,
                workspace_id=colony.workspace_id,
                thread_id=colony.thread_id,
                goal=goal,
                round_number=round_num,
                pheromone_weights=pheromone_weights or None,
                merge_edges=[],
                prev_round_summary=prev_summary,
                pending_directives=directives,
                target_files=_target,
                workspace_dir=_ws_dir,
                structural_context=_structural_ctx,
                structural_deps=_structural_deps,
                operational_playbook=_operational_playbook,  # Wave 54
                task_class=_task_class_name,  # Wave 58.5
                stall_count=stall_count,  # Wave 54
                convergence_progress=last_convergence,  # Wave 54
            )

            try:
                result = await runner.run_round(
                    colony_context=context,
                    agents=agents,
                    strategy=strategy,
                    llm_port=self._runtime.llm_router,  # type: ignore[arg-type]
                    vector_port=self._runtime.vector_store,  # type: ignore[arg-type]
                    event_store_address=address,
                    budget_limit=colony.budget_limit,
                    total_colony_cost=total_cost,
                    routing_override=getattr(fresh, "routing_override", None),
                    knowledge_items=knowledge_items,
                    prior_stall_count=stall_count,
                    recent_successful_code_execute=recent_successful_code_execute,
                    recent_productive_action=recent_productive_action,
                    fast_path=getattr(colony, "fast_path", False),
                )
            except asyncio.CancelledError:
                log.info("colony_manager.cancelled", colony_id=colony_id, round=round_num)
                return
            except Exception:
                log.exception("colony_manager.round_error", colony_id=colony_id, round=round_num)
                await self._runtime.emit_and_broadcast(ColonyFailed(
                    seq=0, timestamp=_now(), address=address,
                    colony_id=colony_id, reason="Round execution error",
                ))
                return

            pheromone_weights = result.updated_weights
            prev_summary = result.round_summary
            total_cost += result.cost
            last_convergence = result.convergence.score
            retrieved_skill_ids.update(result.retrieved_skill_ids)

            # Emit knowledge access trace (Wave 28 B4)
            if getattr(result, "knowledge_items_used", None):
                from formicos.core.events import KnowledgeAccessRecorded

                await self._runtime.emit_and_broadcast(KnowledgeAccessRecorded(
                    seq=0,
                    timestamp=_now(),
                    address=address,
                    colony_id=colony_id,
                    round_number=round_num,
                    workspace_id=colony.workspace_id,
                    access_mode=AccessMode.context_injection,
                    items=result.knowledge_items_used,
                ))

            # Persist pheromone weights to projection for topology display
            proj = self._runtime.projections.get_colony(colony_id)
            if proj is not None:
                proj.pheromone_weights = pheromone_weights
                # Wave 57: governance state for eval timeout decisions
                proj.last_governance_action = result.governance.action
                proj.last_round_productive = result.productive_calls > 0
                proj.last_round_productive_ratio = (
                    result.productive_calls / result.total_calls
                    if result.total_calls > 0 else 0.0
                )
                proj.last_round_completed_at = _time.monotonic()

            # Wave 25: extract artifacts from full agent outputs (live accumulation)
            for agent_id, agent_output in result.outputs.items():
                if agent_output:
                    new_arts = extract_artifacts(
                        output=agent_output,
                        colony_id=colony_id,
                        agent_id=agent_id,
                        round_number=round_num,
                    )
                    art_proj = self._runtime.projections.get_colony(colony_id)
                    if art_proj is not None:
                        art_proj.artifacts.extend(new_arts)

            # Push refreshed snapshot so subscribers see live topology/pheromone/model truth
            try:
                await self._runtime.ws_manager.send_state_to_workspace(
                    colony.workspace_id,
                )
            except Exception:  # noqa: BLE001
                log.debug("colony_manager.mid_round_push_failed", colony_id=colony_id)

            # Governance warning tracking (ADR-011)
            if result.governance.action == "warn":
                governance_warnings += 1

            # Stall tracking â€" use runner's authoritative count
            stall_count = result.stall_count
            recent_successful_code_execute = (
                result.recent_successful_code_execute
            )
            recent_productive_action = result.recent_productive_action

            # Wave 54.5: accumulate productive/total tool counts
            total_productive_calls += result.productive_calls
            total_total_calls += result.total_calls

            # Wave 39 1B: update validator state on projection
            if result.validator is not None:
                val_proj = self._runtime.projections.get_colony(colony_id)
                if val_proj is not None:
                    val_proj.validator_task_type = result.validator.task_type
                    val_proj.validator_verdict = result.validator.verdict
                    val_proj.validator_reason = result.validator.reason

            # Governance alert â†' Queen notification (Wave 19, ADR-032)
            if (
                result.governance.action == "warn"
                and self._runtime.queen is not None
            ):
                _gov_task = asyncio.create_task(
                    self._runtime.queen.on_governance_alert(
                        colony_id=colony_id,
                        workspace_id=colony.workspace_id,
                        thread_id=colony.thread_id,
                        alert_type="stall_detected",
                    ),
                )
                _gov_task.add_done_callback(_log_task_exception)

            # Check for redirect events â€" reset stall state (ADR-032)
            fresh_proj = self._runtime.projections.get_colony(colony_id)
            if fresh_proj is not None:
                rh = getattr(fresh_proj, "redirect_history", [])
                if len(rh) > len(redirect_boundaries):
                    # A redirect happened â€" reset convergence/stall
                    stall_count = 0
                    recent_successful_code_execute = False
                    recent_productive_action = False
                    governance_warnings = 0
                    last_convergence = 0.0
                    redirect_boundaries = list(
                        getattr(fresh_proj, "redirect_boundaries", []),
                    )
                    log.info(
                        "colony_manager.redirect_reset",
                        colony_id=colony_id,
                        redirect_index=len(rh) - 1,
                    )

            # Budget enforcement (ADR-009)
            if total_cost >= colony.budget_limit:
                log.warning(
                    "colony_manager.budget_exhausted",
                    colony_id=colony_id, total_cost=total_cost,
                    budget_limit=colony.budget_limit,
                )
                await self._runtime.emit_and_broadcast(ColonyFailed(
                    seq=0, timestamp=_now(), address=address,
                    colony_id=colony_id,
                    reason=f"Budget exhausted (${total_cost:.2f}"
                    f" of ${colony.budget_limit:.2f} limit)",
                ))
                return

            # Terminal governance
            if result.governance.action == "complete":
                quality = compute_quality_score(
                    rounds_completed=round_num,
                    max_rounds=colony.max_rounds,
                    convergence=last_convergence,
                    governance_warnings=governance_warnings,
                    stall_rounds=stall_count,
                    completed_successfully=True,
                    productive_calls=total_productive_calls,
                    total_calls=total_total_calls,
                )
                # Store quality on projection (not an event â€" derived metric)
                proj = self._runtime.projections.get_colony(colony_id)
                if proj is not None:
                    proj.quality_score = quality
                # Legacy skill crystallization disabled (Wave 28).
                # Institutional memory extraction is the sole active knowledge
                # write path.  skill_bank_v2 continues as read-only archival
                # data via the knowledge catalog.
                skills_count = 0
                # Chat: colony completion (algorithms.md Â§8)
                from formicos.core.events import ColonyChatMessage
                await self._runtime.emit_and_broadcast(ColonyChatMessage(
                    seq=0, timestamp=_now(), address=address,
                    colony_id=colony_id, workspace_id=colony.workspace_id,
                    sender="system", event_kind="complete",
                    content=(
                        f"Completed in {round_num} rounds "
                        f"(${total_cost:.2f})"
                    ),
                ))
                # Wave 25: persist accumulated artifacts on completion
                completion_proj = self._runtime.projections.get_colony(colony_id)
                final_artifacts = completion_proj.artifacts if completion_proj else []
                await self._runtime.emit_and_broadcast(ColonyCompleted(
                    seq=0, timestamp=_now(), address=address,
                    colony_id=colony_id, summary=result.round_summary,
                    skills_extracted=skills_count,
                    artifacts=final_artifacts,
                ))
                # Confidence update + observation (fire-and-forget)
                await self._post_colony_hooks(
                    colony_id=colony_id, colony=colony,
                    quality=quality, total_cost=total_cost,
                    rounds_completed=round_num,
                    skills_count=skills_count,
                    retrieved_skill_ids=retrieved_skill_ids,
                    governance_warnings=governance_warnings,
                    stall_count=stall_count, succeeded=True,
                    productive_calls=total_productive_calls,
                    total_calls=total_total_calls,
                )
                return
            if result.governance.action in ("force_halt", "halt"):
                # Wave 39 1C: governance-owned auto-escalation
                # If the colony stalls and a heavier tier is available,
                # give it one more chance via routing_override instead of
                # halting immediately.
                fresh_esc = self._runtime.projections.get_colony(colony_id)
                already_escalated = (
                    fresh_esc is not None
                    and fresh_esc.routing_override is not None
                )
                if (
                    not already_escalated
                    and total_cost < colony.budget_limit * 0.9
                ):
                    next_tier = _next_viable_tier(
                        colony.castes if hasattr(colony, "castes") else [],
                        self._runtime,
                        colony.workspace_id,
                    )
                    if next_tier is not None:
                        await self._runtime.emit_and_broadcast(ColonyEscalated(
                            seq=0,
                            timestamp=_now(),
                            address=address,
                            colony_id=colony_id,
                            tier=next_tier,
                            reason="auto_escalated_on_stall",
                            set_at_round=round_num,
                        ))
                        # Reset stall state so the colony gets a fair chance
                        stall_count = 0
                        governance_warnings = 0
                        log.info(
                            "colony_manager.auto_escalation",
                            colony_id=colony_id,
                            next_tier=next_tier,
                            round_number=round_num,
                            total_cost=total_cost,
                        )
                        continue  # give the colony another round

                await self._runtime.emit_and_broadcast(ColonyFailed(
                    seq=0, timestamp=_now(), address=address,
                    colony_id=colony_id, reason=result.governance.reason,
                ))
                await self._post_colony_hooks(
                    colony_id=colony_id, colony=colony,
                    quality=0.0, total_cost=total_cost,
                    rounds_completed=round_num,
                    skills_count=0,
                    retrieved_skill_ids=retrieved_skill_ids,
                    governance_warnings=governance_warnings,
                    stall_count=stall_count, succeeded=False,
                )
                return

        # Max rounds exhausted â€" complete with quality score
        quality = compute_quality_score(
            rounds_completed=colony.max_rounds,
            max_rounds=colony.max_rounds,
            convergence=last_convergence,
            governance_warnings=governance_warnings,
            stall_rounds=stall_count,
            completed_successfully=True,
            productive_calls=total_productive_calls,
            total_calls=total_total_calls,
        )
        proj = self._runtime.projections.get_colony(colony_id)
        if proj is not None:
            proj.quality_score = quality
        # Legacy skill crystallization disabled (Wave 28).
        skills_count = 0
        # Wave 25: persist accumulated artifacts on completion (max-rounds path)
        max_proj = self._runtime.projections.get_colony(colony_id)
        max_artifacts = max_proj.artifacts if max_proj else []
        await self._runtime.emit_and_broadcast(ColonyCompleted(
            seq=0, timestamp=_now(), address=address,
            colony_id=colony_id, summary=prev_summary or "",
            skills_extracted=skills_count,
            artifacts=max_artifacts,
        ))
        await self._post_colony_hooks(
            colony_id=colony_id, colony=colony,
            quality=quality, total_cost=total_cost,
            rounds_completed=colony.max_rounds,
            skills_count=skills_count,
            retrieved_skill_ids=retrieved_skill_ids,
            governance_warnings=governance_warnings,
            stall_count=stall_count, succeeded=True,
            productive_calls=total_productive_calls,
            total_calls=total_total_calls,
        )

    # ===================================================================
    # Section 2: Post-colony hooks (observation, steps, follow-up)
    # ===================================================================

    async def _post_colony_hooks(
        self,
        colony_id: str,
        colony: Any,
        quality: float,
        total_cost: float,
        rounds_completed: int,
        skills_count: int,
        retrieved_skill_ids: set[str],
        governance_warnings: int,
        stall_count: int,
        succeeded: bool,
        productive_calls: int = 0,
        total_calls: int = 0,
    ) -> None:
        """Dispatch post-colony lifecycle hooks in order."""
        ws_id = getattr(colony, "workspace_id", "")
        th_id = getattr(colony, "thread_id", "")

        self._hook_observation_log(
            colony_id, colony, quality, total_cost, rounds_completed,
            skills_count, retrieved_skill_ids, governance_warnings, stall_count,
        )
        step_text = self._hook_step_detection(colony_id, ws_id, th_id)
        self._hook_follow_up(colony_id, ws_id, th_id, step_text, succeeded)
        self._hook_memory_extraction(colony_id, ws_id, succeeded)
        self._hook_transcript_harvest(colony_id, ws_id, succeeded)
        await self._hook_confidence_update(
            colony_id, ws_id, th_id, succeeded, quality_score=quality,
        )
        await self._hook_step_completion(colony_id, ws_id, th_id, succeeded)
        # Wave 50: auto-template from qualifying colony completions
        if succeeded:
            await self._hook_auto_template(
                colony_id, colony, quality, rounds_completed,
            )
        # Wave 58: trajectory extraction from successful colonies
        if succeeded:
            await self._hook_trajectory_extraction(
                colony_id, ws_id, quality,
                productive_calls, total_calls,
            )

    # -- Individual post-colony hooks (Wave 32 B3) --

    def _hook_observation_log(
        self,
        colony_id: str,
        colony: Any,
        quality: float,
        total_cost: float,
        rounds_completed: int,
        skills_count: int,
        retrieved_skill_ids: set[str],
        governance_warnings: int,
        stall_count: int,
    ) -> None:
        """Colony observation (structlog only, not event-sourced)."""
        log.info(
            "colony_observation",
            colony_id=colony_id,
            task=colony.task[:200],
            castes=[s.model_dump() if hasattr(s, "model_dump") else s for s in colony.castes],
            strategy=colony.strategy,
            rounds_completed=rounds_completed,
            quality_score=quality,
            total_cost=total_cost,
            skills_retrieved=sorted(retrieved_skill_ids),
            skills_extracted=skills_count,
            governance_warnings=governance_warnings,
            stall_rounds=stall_count,
        )

    def _hook_step_detection(
        self, colony_id: str, ws_id: str, th_id: str,
    ) -> str:
        """Detect step completion and build continuation text (Wave 31 A1)."""
        if not ws_id or not th_id:
            return ""
        thread_proj = self._runtime.projections.get_thread(ws_id, th_id)
        if thread_proj is None:
            return ""

        completed_step = None
        next_step = None
        for step in thread_proj.workflow_steps:
            if (
                step.get("colony_id") == colony_id
                and step.get("status") == "running"
            ):
                completed_step = step
            elif step.get("status") == "pending" and next_step is None:
                next_step = step

        if completed_step is None or next_step is None:
            return ""

        depth = getattr(thread_proj, "continuation_depth", 0)
        if depth >= 20:
            return (
                "Step limit reached (20 consecutive steps). "
                "Review workflow before continuing."
            )

        step_idx = completed_step.get("step_index", "?")
        next_idx = next_step.get("step_index", "?")
        next_desc = next_step.get("description", "")
        text = (
            f"Step {step_idx} completed. "
            f"Next pending: Step {next_idx} -- {next_desc}."
        )
        tmpl_id = next_step.get("template_id", "")
        expected = next_step.get("expected_outputs", [])
        if tmpl_id:
            text += f"\nTemplate: {tmpl_id}"
            if expected:
                text += f", Expected: {', '.join(expected)}"
        text += "\nReview step status or spawn the next colony."
        return text

    def _hook_follow_up(
        self,
        colony_id: str,
        ws_id: str,
        th_id: str,
        step_continuation: str,
        succeeded: bool,
    ) -> None:
        """Queen follow-up summary (Wave 18 B2) â€" fire-and-forget."""
        queen = self._runtime.queen
        if queen is not None and succeeded and ws_id and th_id:
            _followup_task = asyncio.create_task(self._follow_up_colony(
                colony_id=colony_id,
                workspace_id=ws_id,
                thread_id=th_id,
                step_continuation=step_continuation,
            ))
            _followup_task.add_done_callback(_log_task_exception)

    def _hook_memory_extraction(
        self, colony_id: str, ws_id: str, succeeded: bool,
    ) -> None:
        """Institutional memory extraction (Wave 26 A5) â€" fire-and-forget."""
        colony_proj = self._runtime.projections.get_colony(colony_id)
        if colony_proj is not None and ws_id:
            art_list: list[dict[str, Any]] = list(colony_proj.artifacts or [])
            _memory_task = asyncio.create_task(self.extract_institutional_memory(
                colony_id=colony_id,
                workspace_id=ws_id,
                colony_status="completed" if succeeded else "failed",
                final_summary=getattr(colony_proj, "summary", "") or "",
                artifacts=art_list,
                failure_reason=None if succeeded else "Colony failed",
            ))
            _memory_task.add_done_callback(_log_task_exception)

    def _hook_transcript_harvest(
        self, colony_id: str, ws_id: str, succeeded: bool,
    ) -> None:
        """Transcript harvest at hook position 4.5 (Wave 33 A1) â€" fire-and-forget."""
        harvest_key = f"{colony_id}:harvest"
        if harvest_key in self._runtime.projections.memory_extractions_completed:
            return  # replay-safe: already harvested

        colony_proj = self._runtime.projections.get_colony(colony_id)
        if colony_proj is None or not ws_id:
            return

        _harvest_coro = self._run_transcript_harvest(
            colony_id, ws_id, succeeded, colony_proj,
        )
        _harvest_task = asyncio.create_task(_harvest_coro)
        if not isinstance(_harvest_task, asyncio.Task):
            # Some tests patch asyncio.create_task with a plain mock. Close the
            # coroutine in that case so the test doesn't leak an un-awaited coro.
            _harvest_coro.close()
        _harvest_task.add_done_callback(_log_task_exception)

    async def _run_transcript_harvest(
        self,
        colony_id: str,
        ws_id: str,
        succeeded: bool,
        colony_proj: Any,
    ) -> None:
        """Execute transcript harvest extraction (Wave 33 A1)."""
        from formicos.core.events import (  # noqa: PLC0415
            MemoryEntryCreated,
            MemoryExtractionCompleted,
        )
        from formicos.surface.memory_extractor import (  # noqa: PLC0415
            HARVEST_TYPES,
            build_harvest_prompt,
            is_environment_noise_text,
            parse_harvest_response,
        )

        address = f"{ws_id}/{getattr(colony_proj, 'thread_id', '')}/{colony_id}"

        # Build harvest turns from round records. chat_messages no longer retain
        # the agent/caste/round fields harvest classification depends on.
        agent_turns: list[dict[str, Any]] = []
        for rec in getattr(colony_proj, "round_records", []):
            for agent_id, output in getattr(rec, "agent_outputs", {}).items():
                agent_proj = getattr(colony_proj, "agents", {}).get(agent_id)
                agent_turns.append({
                    "agent_id": agent_id,
                    "caste": getattr(agent_proj, "caste", "unknown"),
                    "content": output,
                    "event_kind": "agent_turn",
                    "round_number": getattr(rec, "round_number", 0),
                })

        if not agent_turns:
            return

        prompt = build_harvest_prompt(agent_turns)
        model = self._runtime.resolve_model("archivist", ws_id)
        try:
            response = await self._runtime.llm_router.complete(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You classify colony transcript turns. Return valid JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=2048,
            )
        except Exception:  # noqa: BLE001
            log.warning("transcript_harvest.llm_failed", colony_id=colony_id)
            return

        entries = parse_harvest_response(response.content)
        _HARVEST_SIMILARITY_THRESHOLD = 0.82  # noqa: N806

        emitted = 0
        memory_store = getattr(self._runtime, "memory_store", None)
        now = _now()
        thread_id = getattr(colony_proj, "thread_id", "") or ""

        for harvest_entry in entries:
            turn_idx = harvest_entry.get("turn_index", 0)
            summary = harvest_entry.get("summary", "")
            h_type = harvest_entry.get("type", "learning")
            entry_type = HARVEST_TYPES.get(h_type, "experience")
            # Wave 57 polish: conventions overlap with playbooks + extraction skills.
            # Playbooks provide better operational guidance deterministically.
            if h_type == "convention":
                continue
            if is_environment_noise_text(summary):
                continue

            # Dedup against existing entries
            if memory_store and summary:
                try:
                    hits = await memory_store.search(
                        query=summary, workspace_id=ws_id, top_k=1,
                    )
                    top_score = float(getattr(hits[0], "score", 0.0))
                    if hits and top_score >= _HARVEST_SIMILARITY_THRESHOLD:
                        continue
                except Exception:  # noqa: BLE001
                    pass

            # Build agent info from the turn
            source_turn: dict[str, Any] = cast(
                "dict[str, Any]",
                agent_turns[turn_idx] if turn_idx < len(agent_turns) else {},
            )
            agent_id = str(source_turn.get("agent_id") or "")
            rnd = int(source_turn.get("round_number") or 0)

            from formicos.core.types import (  # noqa: PLC0415
                MemoryEntry,
                MemoryEntryPolarity,
                MemoryEntryStatus,
                MemoryEntryType,
                ScanStatus,
            )

            entry_dict = MemoryEntry(
                id=f"mem-{colony_id}-h-{emitted}",
                entry_type=MemoryEntryType(entry_type),
                status=MemoryEntryStatus.candidate,
                polarity=(
                    MemoryEntryPolarity.negative
                    if h_type == "bug"
                    else MemoryEntryPolarity.positive
                ),
                title=summary[:80],
                content=summary,
                summary=f"Harvested from {agent_id} round {rnd}: {h_type}",
                source_colony_id=colony_id,
                source_artifact_ids=[],
                source_round=rnd,
                domains=[],
                tool_refs=[],
                confidence=0.4,
                scan_status=ScanStatus.pending,
                created_at=now.isoformat(),
                workspace_id=ws_id,
                thread_id=thread_id,
            ).model_dump()

            # Wave 56.5 C: stamp playbook generation hash
            from formicos.engine.playbook_loader import compute_playbook_generation  # noqa: PLC0415

            entry_dict["playbook_generation"] = compute_playbook_generation()

            await self._runtime.emit_and_broadcast(MemoryEntryCreated(
                seq=0, timestamp=now, address=address,
                entry=entry_dict, workspace_id=ws_id,
            ))
            emitted += 1

        # Emit completion receipt
        await self._runtime.emit_and_broadcast(MemoryExtractionCompleted(
            seq=0, timestamp=now, address=address,
            colony_id=colony_id,
            entries_created=emitted,
            workspace_id=ws_id,
        ))

        # Mark as harvested for replay safety
        self._runtime.projections.memory_extractions_completed.add(f"{colony_id}:harvest")

        log.info(
            "transcript_harvest.complete",
            colony_id=colony_id,
            turns_scanned=len(agent_turns),
            entries_harvested=emitted,
        )

    # ===================================================================
    # Section 3: Bayesian confidence updates (gamma-decay, mastery
    #            restoration, co-occurrence reinforcement)
    #
    # Entry point: _hook_confidence_update() â€" called after every colony.
    # Applies decay, success/failure deltas, mastery restoration bonus,
    # and post-success co-occurrence reinforcement.
    # ===================================================================

    async def _hook_confidence_update(
        self,
        colony_id: str,
        ws_id: str,
        th_id: str,
        succeeded: bool,
        quality_score: float = 0.0,
    ) -> None:
        """Bayesian confidence update from knowledge access traces (Wave 30 A3).

        Wave 37 1B: quality_score drives the update magnitude instead of
        a flat +1.  delta_alpha = clip(0.5 + quality_score, 0.5, 1.5) on
        success; delta_beta = clip(0.5 + failure_penalty, 0.5, 1.5) on
        failure.
        """
        import time as _time  # noqa: PLC0415

        _conf_start = _time.monotonic()
        _conf_updated = 0
        seen_ids: set[str] = set()
        colony_proj = self._runtime.projections.get_colony(colony_id)
        if colony_proj is not None:
            accesses: list[dict[str, Any]] = getattr(
                colony_proj, "knowledge_accesses", [],
            )
            for trace in accesses:
                for item in trace.get("items", []):
                    item_id = item.get("id", "")
                    if not item_id or item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)
                    entry = self._runtime.projections.memory_entries.get(
                        item_id,
                    )
                    if entry is None:
                        continue
                    old_alpha = float(entry.get("conf_alpha", PRIOR_ALPHA))
                    old_beta = float(entry.get("conf_beta", PRIOR_BETA))

                    # Wave 32 A1: time-based gamma-decay (ADR-041 D1)
                    event_ts = _now()
                    last_updated = entry.get(
                        "last_confidence_update",
                        entry.get("created_at", ""),
                    )
                    if last_updated:
                        try:
                            elapsed_days = (
                                event_ts - datetime.fromisoformat(last_updated)
                            ).total_seconds() / 86400.0
                            elapsed_days = max(elapsed_days, 0.0)
                        except (ValueError, TypeError):
                            elapsed_days = 0.0
                    else:
                        elapsed_days = 0.0

                    # Wave 33 A4: cap elapsed days + DecayClass-aware gamma
                    elapsed_days = min(elapsed_days, MAX_ELAPSED_DAYS)
                    decay_class = entry.get("decay_class", "ephemeral")
                    gamma = GAMMA_RATES.get(decay_class, GAMMA_PER_DAY)
                    gamma_eff = gamma ** elapsed_days
                    decayed_alpha = gamma_eff * old_alpha + (1 - gamma_eff) * PRIOR_ALPHA
                    decayed_beta = gamma_eff * old_beta + (1 - gamma_eff) * PRIOR_BETA

                    if succeeded:
                        # Wave 37 1B: quality-aware delta replaces flat +1
                        delta_alpha = min(max(0.5 + quality_score, 0.5), 1.5)
                        new_alpha = max(decayed_alpha + delta_alpha, 1.0)
                        new_beta = max(decayed_beta, 1.0)

                        # Wave 35 C3: mastery-restoration bonus
                        peak_alpha = float(
                            entry.get("peak_alpha", entry.get("conf_alpha", PRIOR_ALPHA)),
                        )
                        if (
                            decayed_alpha < peak_alpha * 0.5
                            and decay_class in ("stable", "permanent")
                        ):
                            gap = peak_alpha - decayed_alpha
                            restoration = gap * 0.2
                            new_alpha += restoration
                    else:
                        # Wave 37 1B: quality-aware failure penalty
                        # Low quality (near 0) â†' higher penalty (1.5)
                        # quality_score is 0 on failure path, so penalty is 1.0
                        failure_penalty = 1.0 - quality_score
                        delta_beta = min(max(0.5 + failure_penalty, 0.5), 1.5)
                        new_alpha = max(decayed_alpha, 1.0)
                        new_beta = max(decayed_beta + delta_beta, 1.0)
                    new_confidence = new_alpha / (new_alpha + new_beta)

                    address = (
                        f"{ws_id}/{th_id}/{colony_id}"
                        if ws_id
                        else colony_id
                    )
                    await self._runtime.emit_and_broadcast(
                        MemoryConfidenceUpdated(
                            seq=0,
                            timestamp=event_ts,
                            address=address,
                            entry_id=item_id,
                            colony_id=colony_id,
                            colony_succeeded=succeeded,
                            old_alpha=old_alpha,
                            old_beta=old_beta,
                            new_alpha=new_alpha,
                            new_beta=new_beta,
                            new_confidence=new_confidence,
                            workspace_id=ws_id,
                            thread_id=th_id,
                            reason="colony_outcome",
                        ),
                    )
                    _conf_updated += 1

                    # Wave 56: deterministic promotion candidate â†' verified
                    entry_status = entry.get("status", "")
                    if (
                        succeeded
                        and entry_status == "candidate"
                        and new_alpha >= _PROMOTION_ALPHA_THRESHOLD
                    ):
                        await self._runtime.emit_and_broadcast(
                            MemoryEntryStatusChanged(
                                seq=0,
                                timestamp=event_ts,
                                address=address,
                                entry_id=item_id,
                                old_status="candidate",
                                new_status="verified",
                                reason="consumption_promotion",
                                workspace_id=ws_id,
                            ),
                        )
                        log.info(
                            "colony.knowledge_promoted",
                            entry_id=item_id,
                            new_alpha=round(new_alpha, 2),
                            colony_id=colony_id,
                        )

        # Wave 33 A5: co-occurrence result-result reinforcement (successful colonies only)
        if succeeded and seen_ids:
            from formicos.surface.projections import (  # noqa: PLC0415
                CooccurrenceEntry,
                cooccurrence_key,
            )

            accessed_list = list(seen_ids)
            now_iso = _now().isoformat()
            for i, id_a in enumerate(accessed_list):
                for id_b in accessed_list[i + 1 :]:
                    key = cooccurrence_key(id_a, id_b)
                    co_entry = self._runtime.projections.cooccurrence_weights.get(key)
                    if co_entry is None:
                        co_entry = CooccurrenceEntry(
                            weight=1.0, last_reinforced=now_iso, reinforcement_count=1,
                        )
                    else:
                        co_entry.weight = min(co_entry.weight * 1.1, 10.0)
                        co_entry.last_reinforced = now_iso
                        co_entry.reinforcement_count += 1
                    self._runtime.projections.cooccurrence_weights[key] = co_entry

        _conf_elapsed = _time.monotonic() - _conf_start
        if _conf_elapsed > 0.1:
            log.warning(
                "colony.confidence_fanout_slow",
                colony_id=colony_id,
                elapsed_ms=round(_conf_elapsed * 1000, 1),
                entries_updated=_conf_updated,
            )

    async def _hook_step_completion(
        self, colony_id: str, ws_id: str, th_id: str, succeeded: bool,
    ) -> None:
        """Emit WorkflowStepCompleted for the running step (Wave 30 B5)."""
        if not ws_id or not th_id:
            return
        thread_proj = self._runtime.projections.get_thread(ws_id, th_id)
        if thread_proj is None:
            return
        for step in thread_proj.workflow_steps:
            if (
                step.get("colony_id") == colony_id
                and step.get("status") == "running"
            ):
                arts_produced: list[str] = []
                col_proj = self._runtime.projections.get_colony(colony_id)
                if col_proj is not None:
                    col_arts: list[dict[str, Any]] = getattr(
                        col_proj, "artifacts", [],
                    )
                    for art in col_arts:
                        atype = str(art.get("artifact_type", "generic"))
                        if atype:
                            arts_produced.append(atype)

                from formicos.core.events import WorkflowStepCompleted  # noqa: PLC0415

                address = (
                    f"{ws_id}/{th_id}/{colony_id}"
                    if ws_id
                    else colony_id
                )
                await self._runtime.emit_and_broadcast(
                    WorkflowStepCompleted(
                        seq=0,
                        timestamp=_now(),
                        address=address,
                        workspace_id=ws_id,
                        thread_id=th_id,
                        step_index=int(step.get("step_index", -1)),
                        colony_id=colony_id,
                        success=succeeded,
                        artifacts_produced=arts_produced,
                    ),
                )
                break

    async def _hook_auto_template(
        self,
        colony_id: str,
        colony: Any,
        quality: float,
        rounds_completed: int,
    ) -> None:
        """Emit ColonyTemplateCreated for qualifying colony completions (Wave 50).

        Qualification:
        - quality >= 0.7
        - rounds >= 3 (fast_path one-shots are not interesting)
        - spawn_source == "queen"
        - no existing learned template for same task_category + strategy
        """
        proj = self._runtime.projections.get_colony(colony_id)
        if proj is None:
            return

        # Quality gate
        if quality < 0.7:
            return
        # Rounds gate â€" skip trivial one-shots
        if rounds_completed < 3:
            return
        # Provenance gate â€" only Queen-spawned colonies qualify
        spawn_source = getattr(proj, "spawn_source", "")
        if spawn_source != "queen":
            return

        from formicos.surface.task_classifier import classify_task  # noqa: PLC0415

        cat_name, _ = classify_task(colony.task)

        # Dedup gate â€" no existing learned template for same category + strategy
        for tmpl in self._runtime.projections.templates.values():
            if (
                tmpl.learned
                and tmpl.task_category == cat_name
                and tmpl.strategy == proj.strategy
            ):
                return

        from formicos.surface.template_manager import new_template_id  # noqa: PLC0415

        template_id = new_template_id()
        castes = list(proj.castes)
        # Derive compact target_files_pattern from colony target_files
        target_pattern = ""
        target_files: list[str] = getattr(proj, "target_files", [])
        if target_files:
            # Use first file's directory as a compact pattern
            from pathlib import PurePosixPath  # noqa: PLC0415

            dirs = {str(PurePosixPath(f).parent) for f in target_files if f}
            if len(dirs) == 1:
                target_pattern = f"{next(iter(dirs))}/*"

        address = f"{proj.workspace_id}/{proj.thread_id}/{colony_id}"
        await self._runtime.emit_and_broadcast(ColonyTemplateCreated(
            seq=0,
            timestamp=_now(),
            address=address,
            template_id=template_id,
            name=f"learned-{cat_name}-{proj.strategy}",
            description=(
                f"Auto-learned from colony {colony_id}: {colony.task[:100]}"
            ),
            castes=castes,
            strategy=proj.strategy,  # type: ignore[arg-type]
            source_colony_id=colony_id,
            learned=True,
            task_category=cat_name,
            max_rounds=proj.max_rounds,
            budget_limit=proj.budget_limit,
            fast_path=getattr(proj, "fast_path", False),
            target_files_pattern=target_pattern,
        ))
        log.info(
            "colony_manager.auto_template_created",
            colony_id=colony_id,
            template_id=template_id,
            task_category=cat_name,
            quality=quality,
        )

    async def _hook_trajectory_extraction(
        self,
        colony_id: str,
        workspace_id: str,
        quality: float,
        productive_calls: int,
        total_calls: int,
    ) -> None:
        """Extract tool-call trajectory from successful colonies (Wave 58).

        Deterministic: reads tool_calls from round records in the projection.
        No LLM call.
        """
        # Quality gate
        if quality < 0.30:
            log.debug("trajectory.skip_low_quality", colony_id=colony_id, quality=quality)
            return

        # Productivity gate: at least 60% productive calls
        if total_calls == 0:
            return
        productive_ratio = productive_calls / total_calls
        if productive_ratio < 0.6:
            log.debug(
                "trajectory.skip_low_productivity",
                colony_id=colony_id,
                productive_ratio=round(productive_ratio, 2),
            )
            return

        # Read round records from projection
        colony_proj = self._runtime.projections.get_colony(colony_id)
        if colony_proj is None:
            return

        # Build trajectory steps from round records.
        # ColonyProjection is a dataclass with round_records: list[RoundProjection]
        # RoundProjection.tool_calls: dict[str, list[str]] (agent_id -> [tool_name, ...])
        steps: list[dict[str, Any]] = []
        round_records = getattr(colony_proj, "round_records", [])

        for round_rec in round_records:
            round_num = getattr(round_rec, "round_number", 0)
            tool_call_map = getattr(round_rec, "tool_calls", {})
            for agent_id, tool_names in (tool_call_map or {}).items():
                for tool_name in tool_names:
                    steps.append({
                        "tool": str(tool_name),
                        "agent_id": str(agent_id),
                        "round_number": round_num,
                    })

        if len(steps) < 2:
            log.debug("trajectory.skip_trivial", colony_id=colony_id, steps=len(steps))
            return

        # Classify task
        from formicos.surface.task_classifier import classify_task  # noqa: PLC0415

        goal = getattr(colony_proj, "task", "")
        task_class, _ = classify_task(goal)

        # Build human-readable content for embedding
        tool_seq = " -> ".join(s["tool"] for s in steps[:20])
        rounds_completed = getattr(
            colony_proj, "round_number", len(round_records),
        )

        content = (
            f"Successful {task_class} pattern "
            f"({rounds_completed} rounds, quality {quality:.2f}, "
            f"productivity {productive_ratio:.0%}): {tool_seq}."
        )

        from formicos.core.events import MemoryEntryCreated  # noqa: PLC0415
        from formicos.core.types import (  # noqa: PLC0415
            DecayClass,
            EntrySubType,
            MemoryEntry,
            MemoryEntryPolarity,
            MemoryEntryStatus,
            MemoryEntryType,
            ScanStatus,
        )

        now_str = datetime.now(UTC).isoformat()
        entry = MemoryEntry(
            id=f"traj-{colony_id}",
            entry_type=MemoryEntryType.skill,
            sub_type=EntrySubType.trajectory,
            status=MemoryEntryStatus.verified,
            polarity=MemoryEntryPolarity.positive,
            title=f"Trajectory: {task_class} ({len(steps)} steps)",
            content=content,
            summary=f"{task_class} tool sequence, {len(steps)} steps, quality {quality:.2f}",
            source_colony_id=colony_id,
            source_artifact_ids=[],
            domains=[task_class],
            tool_refs=list({s["tool"] for s in steps}),
            confidence=min(quality, 0.8),
            conf_alpha=max(2.0, quality * 10),
            conf_beta=max(2.0, (1.0 - quality) * 10),
            decay_class=DecayClass.stable,
            scan_status=ScanStatus.safe,
            trajectory_data=steps[:30],
            workspace_id=workspace_id,
            created_at=now_str,
        )

        address = f"{workspace_id}/{getattr(colony_proj, 'thread_id', '')}/{colony_id}"
        entry_dict = entry.model_dump()
        entry_dict["primary_domain"] = task_class  # Wave 58.5
        await self._runtime.emit_and_broadcast(MemoryEntryCreated(
            seq=0,
            timestamp=datetime.now(UTC),
            address=address,
            workspace_id=workspace_id,
            entry=entry_dict,
        ))
        log.info(
            "trajectory.extracted",
            colony_id=colony_id,
            task_class=task_class,
            steps=len(steps),
            quality=round(quality, 2),
        )

    async def _follow_up_colony(
        self, colony_id: str, workspace_id: str, thread_id: str,
        step_continuation: str = "",
    ) -> None:
        """Ask Queen to summarize a completed colony. Fire-and-forget, errors logged."""
        try:
            queen = self._runtime.queen
            if queen is None:
                return
            await queen.follow_up_colony(
                colony_id=colony_id,
                workspace_id=workspace_id,
                thread_id=thread_id,
                step_continuation=step_continuation,
            )
        except Exception:  # noqa: BLE001
            log.debug("colony_manager.follow_up_failed", colony_id=colony_id)

    async def _crystallize_skills(
        self,
        colony_id: str,
        task: str,
        final_summary: str,
        round_count: int,
    ) -> int:
        """Legacy skill crystallization â€" disabled (Wave 30)."""
        return 0

    async def _check_inline_dedup(
        self,
        entry_content: str,
        workspace_id: str,
        succeeded: bool,
    ) -> str | None:
        """Check if a near-duplicate exists (cosine > 0.92). Returns existing entry_id or None.

        If a match is found, emits MemoryConfidenceUpdated to reinforce the existing entry.
        Wave 33 A2.
        """
        _INLINE_DEDUP_THRESHOLD = 0.92  # noqa: N806

        if not entry_content or not workspace_id:
            return None

        memory_store = getattr(self._runtime, "memory_store", None)
        if memory_store is None:
            return None

        try:
            hits = await memory_store.search(
                query=entry_content,
                workspace_id=workspace_id,
                top_k=1,
            )
        except Exception:  # noqa: BLE001
            return None

        if not hits:
            return None

        best = hits[0]
        score = float(getattr(best, "score", 0.0))
        if score <= _INLINE_DEDUP_THRESHOLD:
            return None

        # Found a near-duplicate â€" reinforce its confidence
        existing_id = str(getattr(best, "id", ""))
        if not existing_id and hasattr(best, "payload"):
            existing_id = str(best.payload.get("id", ""))
        if not existing_id:
            return None

        entry = self._runtime.projections.memory_entries.get(existing_id)
        if entry is None:
            return existing_id  # still skip, just can't reinforce

        old_alpha = float(entry.get("conf_alpha", PRIOR_ALPHA))
        old_beta = float(entry.get("conf_beta", PRIOR_BETA))
        if succeeded:
            new_alpha = max(old_alpha + 1.0, 1.0)
            new_beta = max(old_beta, 1.0)
        else:
            new_alpha = max(old_alpha, 1.0)
            new_beta = max(old_beta + 1.0, 1.0)
        new_confidence = new_alpha / (new_alpha + new_beta)

        await self._runtime.emit_and_broadcast(
            MemoryConfidenceUpdated(
                seq=0,
                timestamp=_now(),
                address=workspace_id,
                entry_id=existing_id,
                colony_id="",
                colony_succeeded=succeeded,
                old_alpha=old_alpha,
                old_beta=old_beta,
                new_alpha=new_alpha,
                new_beta=new_beta,
                new_confidence=new_confidence,
                workspace_id=workspace_id,
                thread_id=entry.get("thread_id", ""),
                reason="inline_dedup",
            ),
        )
        return existing_id

    # ===================================================================
    # Section 4: Memory extraction pipeline (LLM-based skill/experience
    #            extraction, inline dedup, security scanning, admission)
    # ===================================================================

    async def extract_institutional_memory(
        self,
        colony_id: str,
        workspace_id: str,
        colony_status: str,
        final_summary: str,
        artifacts: list[dict[str, Any]],
        failure_reason: str | None,
    ) -> None:
        """Extract institutional memory entries from a completed/failed colony.

        Fire-and-forget. Errors are logged, never propagated.
        Lifecycle: extract â†' scan â†' emit MemoryEntryCreated â†' emit
        MemoryEntryStatusChanged (verified for successful) â†' always emit
        MemoryExtractionCompleted.
        """
        from formicos.core.events import (
            MemoryEntryCreated,
            MemoryEntryStatusChanged,
            MemoryExtractionCompleted,
        )
        from formicos.surface.memory_extractor import (
            build_extraction_prompt,
            build_memory_entries,
            parse_extraction_response,
        )
        from formicos.surface.memory_scanner import scan_entry

        colony = self._runtime.projections.get_colony(colony_id)
        if colony is None:
            return

        address = f"{workspace_id}/{colony.thread_id}/{colony_id}"

        # Wave 58.5: classify task for domain-boundary tagging
        from formicos.surface.task_classifier import classify_task  # noqa: PLC0415

        _task_class, _ = classify_task(colony.task)

        # Build artifact dicts for prompt context
        artifact_ids = [str(a.get("id", "")) for a in artifacts]
        art_dicts: list[dict[str, Any]] = list(artifacts)

        # Wave 59: fetch existing entries for curation context
        existing_entries: list[dict[str, Any]] = []
        try:
            _kc = getattr(self._runtime, "knowledge_catalog", None)
            if _kc is not None:
                existing_entries = await _kc.search(
                    query=colony.task,
                    workspace_id=workspace_id,
                    top_k=10,
                )
                # Enrich with access counts
                for _item in existing_entries:
                    _usage = self._runtime.projections.knowledge_entry_usage.get(
                        _item.get("id", ""), {},
                    )
                    _item["access_count"] = _usage.get("count", 0)
        except Exception:  # noqa: BLE001
            log.warning("curation.existing_fetch_failed", colony_id=colony_id)
            existing_entries = []

        prompt = build_extraction_prompt(
            task=colony.task,
            final_output=final_summary,
            artifacts=art_dicts,
            colony_status=colony_status,
            failure_reason=failure_reason,
            contract_result=None,
            task_class=_task_class,
            existing_entries=existing_entries,
        )

        # Call LLM for extraction
        model = self._runtime.resolve_model("archivist", workspace_id)
        try:
            response = await self._runtime.llm_router.complete(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You extract institutional memory from colony results. "
                            "Return valid JSON only."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=2048,
            )
        except Exception:  # noqa: BLE001
            log.warning(
                "memory_extraction.llm_failed",
                colony_id=colony_id,
            )
            # Still emit completion receipt so we don't re-queue on restart
            await self._runtime.emit_and_broadcast(MemoryExtractionCompleted(
                seq=0, timestamp=_now(), address=address,
                colony_id=colony_id,
                entries_created=0,
                workspace_id=workspace_id,
            ))
            return

        raw = parse_extraction_response(response.content)

        # Wave 59: action-aware dispatch
        refine_actions: list[dict[str, Any]] = []
        merge_actions: list[dict[str, Any]] = []
        if "actions" in raw:
            entries = []
            for action in raw.get("actions", []):
                action_type = action.get("type", "").upper()
                if action_type == "CREATE":
                    entry_data = action.get("entry", action)
                    cat = entry_data.get(
                        "canonical_type",
                        entry_data.get("entry_type", "skill"),
                    )
                    if cat in ("skill", "technique", "pattern", "anti_pattern"):
                        single_raw = {"skills": [entry_data], "experiences": []}
                    else:
                        single_raw = {"skills": [], "experiences": [entry_data]}
                    entries.extend(build_memory_entries(
                        raw=single_raw,
                        colony_id=colony_id,
                        workspace_id=workspace_id,
                        artifact_ids=artifact_ids,
                        colony_status=colony_status,
                    ))
                elif action_type == "REFINE":
                    refine_actions.append({
                        "entry_id": action.get("entry_id", ""),
                        "new_content": action.get("new_content", ""),
                        "new_title": action.get("new_title", ""),
                    })
                elif action_type == "MERGE":
                    merge_actions.append({
                        "target_id": action.get("target_id", ""),
                        "source_id": action.get("source_id", ""),
                        "merged_content": action.get("merged_content", ""),
                    })
                elif action_type == "NOOP":
                    log.debug(
                        "curation.noop",
                        entry_id=action.get("entry_id", ""),
                    )
        else:
            entries = build_memory_entries(
                raw=raw,
                colony_id=colony_id,
                workspace_id=workspace_id,
                artifact_ids=artifact_ids,
                colony_status=colony_status,
            )

        # Wave 29: tag entries with source colony's thread scope
        colony_proj = self._runtime.projections.get_colony(colony_id)
        _thread_id = colony_proj.thread_id if colony_proj else ""
        for entry in entries:
            entry["thread_id"] = _thread_id
            entry["primary_domain"] = _task_class  # Wave 58.5

        emitted_count = 0
        for entry in entries:
            # Wave 42: conjunctive extraction quality gate (before dedup/scan)
            quality_rejection = _check_extraction_quality(entry)
            if quality_rejection:
                log.info(
                    "memory.quality_gate_skip",
                    entry_id=entry.get("id"),
                    reason=quality_rejection,
                )
                continue

            # Wave 33 A2: inline dedup â€" skip near-duplicates, reinforce existing
            dedup_id = await self._check_inline_dedup(
                entry.get("content", ""),
                workspace_id,
                colony_status == "completed",
            )
            if dedup_id is not None:
                log.info(
                    "memory.inline_dedup_skip",
                    entry_id=entry.get("id"),
                    existing_id=dedup_id,
                )
                continue

            # Scan BEFORE event emission â€" bake scan_status into payload
            scan_result = scan_entry(entry)
            entry["scan_status"] = scan_result["tier"]

            # Wave 38: admission policy â€" combines scanner + confidence +
            # provenance + federation trust + content type + recency
            from formicos.surface.admission import evaluate_entry as _evaluate  # noqa: PLC0415

            admission = _evaluate(entry, scanner_result=scan_result)
            entry["admission_score"] = admission.score
            entry["admission_flags"] = admission.flags

            if not admission.admitted:
                entry["status"] = "rejected"
                log.warning(
                    "memory.admission_rejected",
                    entry_id=entry.get("id"),
                    score=admission.score,
                    rationale=admission.rationale,
                    flags=admission.flags,
                )
            elif admission.status_override:
                entry["status"] = admission.status_override
                log.info(
                    "memory.admission_demoted",
                    entry_id=entry.get("id"),
                    score=admission.score,
                    status_override=admission.status_override,
                )

            # Wave 56.5 C: stamp playbook generation hash
            from formicos.engine.playbook_loader import compute_playbook_generation  # noqa: PLC0415

            entry["playbook_generation"] = compute_playbook_generation()

            # Emit MemoryEntryCreated with scan_status and status baked in
            await self._runtime.emit_and_broadcast(MemoryEntryCreated(
                seq=0, timestamp=_now(), address=address,
                entry=entry,
                workspace_id=workspace_id,
            ))

            # Verification: non-rejected entries from successful colonies
            if entry["status"] != "rejected" and colony_status == "completed":
                await self._runtime.emit_and_broadcast(MemoryEntryStatusChanged(
                    seq=0, timestamp=_now(), address=address,
                    entry_id=entry["id"],
                    old_status="candidate",
                    new_status="verified",
                    reason="source colony completed successfully",
                    workspace_id=workspace_id,
                ))
                emitted_count += 1
            elif entry["status"] != "rejected":
                emitted_count += 1

        # Wave 56: extraction observability — log what was produced vs filtered
        raw_skills = len(raw.get("skills", []))
        raw_experiences = len(raw.get("experiences", []))
        log.info(
            "memory.extraction_summary",
            colony_id=colony_id,
            colony_status=colony_status,
            raw_skills=raw_skills,
            raw_experiences=raw_experiences,
            raw_total=raw_skills + raw_experiences,
            emitted=emitted_count,
            filtered=raw_skills + raw_experiences - emitted_count,
        )

        # Wave 59: dispatch REFINE actions
        from formicos.core.events import MemoryEntryRefined  # noqa: PLC0415

        for ra in refine_actions:
            rid = ra["entry_id"]
            existing = self._runtime.projections.memory_entries.get(rid)
            if existing is None:
                log.warning("curation.refine_missing_entry", entry_id=rid)
                continue
            new_content = ra["new_content"].strip()
            if len(new_content) < 20:
                log.warning("curation.refine_empty_content", entry_id=rid)
                continue
            old_content = existing.get("content", "")
            if new_content == old_content:
                log.debug("curation.refine_no_change", entry_id=rid)
                continue
            # Wave 60: semantic preservation gate — reject rewrites that
            # drift too far from the original meaning
            _embed = self._runtime.embed_fn
            if old_content and _embed:
                try:
                    old_emb = _embed([old_content])
                    new_emb = _embed([new_content])
                    if old_emb and new_emb:
                        sim = _cm_cosine_similarity(old_emb[0], new_emb[0])
                        if sim < 0.75:
                            log.warning(
                                "curation.refine_rejected",
                                entry_id=rid,
                                similarity=round(sim, 3),
                                reason="semantic_drift",
                            )
                            continue
                except Exception:  # noqa: BLE001
                    log.warning("curation.semantic_gate_embed_failed", entry_id=rid)
            await self._runtime.emit_and_broadcast(MemoryEntryRefined(
                seq=0,
                timestamp=_now(),
                address=address,
                entry_id=rid,
                workspace_id=workspace_id,
                old_content=old_content,
                new_content=new_content,
                new_title=ra.get("new_title", ""),
                refinement_source="extraction",
                source_colony_id=colony_id,
            ))
            log.info(
                "curation.entry_refined",
                entry_id=rid,
                colony_id=colony_id,
                old_len=len(old_content),
                new_len=len(new_content),
            )

        # Wave 59: dispatch MERGE actions
        from formicos.core.events import MemoryEntryMerged  # noqa: PLC0415

        for ma in merge_actions:
            target_id = ma["target_id"]
            source_id = ma["source_id"]
            merged_content = ma.get("merged_content", "")
            target = self._runtime.projections.memory_entries.get(target_id)
            source = self._runtime.projections.memory_entries.get(source_id)
            if target is None or source is None:
                log.warning(
                    "curation.merge_missing_entry",
                    target_id=target_id, source_id=source_id,
                )
                continue
            if len(merged_content.strip()) < 20:
                log.warning("curation.merge_empty_content", target_id=target_id)
                continue
            await self._runtime.emit_and_broadcast(MemoryEntryMerged(
                seq=0,
                timestamp=_now(),
                address=address,
                target_id=target_id,
                source_id=source_id,
                merged_content=merged_content,
                merged_domains=list(
                    set(target.get("domains", [])
                        + source.get("domains", [])),
                ),
                merged_from=list(
                    set(target.get("merged_from", [target_id])
                        + source.get("merged_from", [source_id])),
                ),
                content_strategy="llm_selected",
                similarity=0.0,
                merge_source="extraction",
                workspace_id=workspace_id,
            ))
            log.info(
                "curation.entries_merged",
                target_id=target_id,
                source_id=source_id,
                colony_id=colony_id,
            )

        # ALWAYS emit extraction receipt — even when zero entries
        await self._runtime.emit_and_broadcast(MemoryExtractionCompleted(
            seq=0, timestamp=_now(), address=address,
            colony_id=colony_id,
            entries_created=emitted_count,
            workspace_id=workspace_id,
        ))

        log.info(
            "memory_extraction.complete",
            colony_id=colony_id,
            entries_extracted=len(entries),
            entries_emitted=emitted_count,
        )

    def _make_strategy(self, name: str) -> Any:  # noqa: ANN401
        """Create the appropriate coordination strategy.

        ADR-025: async_embed_fn (Qwen3 sidecar) is the preferred path.
        Sync embed_fn is the fallback. _STIGMERGIC_AVAILABLE gate removed.
        """
        if name != "stigmergic":
            return SequentialStrategy()

        async_embed_fn = None
        if self._runtime.embed_client is not None:
            async_embed_fn = self._runtime.embed_client.embed

        if async_embed_fn is not None or self._runtime.embed_fn is not None:
            return StigmergicStrategy(
                embed_fn=self._runtime.embed_fn,
                async_embed_fn=async_embed_fn,
                tau=self._runtime.settings.routing.tau_threshold,
                k_in=self._runtime.settings.routing.k_in_cap,
            )
        return SequentialStrategy()


def _analyze_workspace_safe(workspace_dir: str) -> WorkspaceStructure:
    """Run structural analysis, returning empty structure on failure."""
    try:
        return analyze_workspace(workspace_dir)
    except Exception:
        log.warning("code_analysis.failed", workspace_dir=workspace_dir, exc_info=True)
        return WorkspaceStructure()


def _extract_deps_subset(
    structure: WorkspaceStructure,
    target_files: list[str],
) -> dict[str, list[str]]:
    """Extract dependency graph subset relevant to *target_files*."""
    if not target_files or not structure.dependency_graph:
        return {}
    deps: dict[str, list[str]] = {}
    relevant = set(target_files)
    for tf in target_files:
        relevant.update(structure.neighbors(tf, max_hops=1))
    for f in relevant:
        if f in structure.dependency_graph:
            deps[f] = sorted(structure.dependency_graph[f])
    return deps


__all__ = ["ColonyManager", "compute_quality_score"]
