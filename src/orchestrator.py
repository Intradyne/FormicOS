"""
FormicOS v0.6.0 -- Orchestrator

Runs the 5-phase DyTopo loop for a single colony.  Progresses from task
decomposition through agent execution to compression and governance.

Phase 1 -- Goal:       Manager sets round objectives.
Phase 2 -- Intent:     Each agent produces {key, query} descriptors.
Phase 3 -- Routing:    Embed descriptors, build DAG via DyTopo router.
Phase 3.5 -- Skill:    Query SkillBank for relevant skills.
Phase 4 -- Execution:  Execute agents in topological order with context.
Phase 5 -- Compress:   Archivist summarizes, TKG extraction, governance.

Post-Colony:           Skill distillation, session save, colony_complete.

Error handling:
  - Agent failure:  log, skip agent, continue round.
  - LLM timeout:    retry once, then mark agent failed for round.
  - Governance force_halt:  end loop, COMPLETED with note.
  - Context Tree lock timeout:  wait 30s, proceed without write.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time as _time
import traceback
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from src.agents import Agent, AgentOutput, ContextExceededError
from src.models import (
    BudgetConstraints,
    CheckpointMeta,
    ColonyMetrics,
    ColonyStatus,
    ConvergenceMetrics,
    Decision,
    DecisionType,
    Episode,
    FormicOSConfig,
    ResumeDirective,
    RoundMetrics,
    SessionResult,
    TimelineSpan,
    Topology,
    TopologyEdge,
    VotingGroupResult,
    VotingNodeConfig,
)

if TYPE_CHECKING:
    from src.archivist import Archivist
    from src.audit import AuditLogger
    from src.context import AsyncContextTree
    from src.governance import GovernanceEngine
    from src.skill_bank import SkillBank
    from src.webhook import WebhookDispatcher

logger = logging.getLogger("formicos.orchestrator")

# Timeout for individual agent execution (seconds).  Overridden by
# config.inference.timeout_seconds when available.
_DEFAULT_AGENT_TIMEOUT = 120

# Timeout for Context Tree lock acquisition (seconds).
_CTX_LOCK_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _fire_callback(
    callbacks: dict[str, Any] | None,
    name: str,
    *args: Any,
) -> Any:
    """Invoke a callback by name if it exists.  Swallows exceptions."""
    if callbacks is None:
        return None
    cb = callbacks.get(name)
    if cb is None:
        return None
    try:
        result = cb(*args)
        if asyncio.iscoroutine(result) or asyncio.isfuture(result):
            return await result
        return result
    except Exception as exc:
        logger.warning("Callback '%s' raised: %s", name, exc)
        return None


def _fire_sync_callback(
    callbacks: dict[str, Any] | None,
    name: str,
    *args: Any,
) -> None:
    """Invoke a synchronous callback by name.  Swallows exceptions."""
    if callbacks is None:
        return
    cb = callbacks.get(name)
    if cb is None:
        return
    try:
        cb(*args)
    except Exception as exc:
        logger.warning("Sync callback '%s' raised: %s", name, exc)


# ===========================================================================
# Metrics Accumulator (v0.7.3)
# ===========================================================================


class MetricsAccumulator:
    """Tracks per-round and aggregate token/tool metrics for a colony."""

    def __init__(self, colony_id: str) -> None:
        self.colony_id = colony_id
        self._rounds: list[RoundMetrics] = []

    def record_round(
        self,
        round_num: int,
        agent_outputs: dict[str, AgentOutput],
        duration_ms: float,
        agent_castes: dict[str, str] | None = None,
    ) -> RoundMetrics:
        """Record metrics from a completed round."""
        tokens_prompt = 0
        tokens_completion = 0
        tool_calls_count = 0
        agent_activity: dict[str, int] = {}
        caste_activity: dict[str, int] = {}

        castes = agent_castes or {}

        for agent_id, output in agent_outputs.items():
            agent_tokens = output.tokens_prompt + output.tokens_completion
            if agent_tokens == 0:
                agent_tokens = output.tokens_used
            tokens_prompt += output.tokens_prompt
            tokens_completion += output.tokens_completion
            tool_calls_count += len(output.tool_calls)
            agent_activity[agent_id] = agent_tokens

            caste = castes.get(agent_id, "unknown")
            caste_activity[caste] = caste_activity.get(caste, 0) + agent_tokens

        rm = RoundMetrics(
            round_num=round_num,
            tokens_prompt=tokens_prompt,
            tokens_completion=tokens_completion,
            tool_calls_count=tool_calls_count,
            agent_activity=agent_activity,
            caste_activity=caste_activity,
            duration_ms=duration_ms,
        )
        self._rounds.append(rm)
        return rm

    def get_colony_metrics(self) -> ColonyMetrics:
        """Aggregate metrics across all recorded rounds."""
        total_prompt = sum(r.tokens_prompt for r in self._rounds)
        total_completion = sum(r.tokens_completion for r in self._rounds)
        total_tools = sum(r.tool_calls_count for r in self._rounds)

        caste_agg: dict[str, int] = {}
        for r in self._rounds:
            for caste, tokens in r.caste_activity.items():
                caste_agg[caste] = caste_agg.get(caste, 0) + tokens

        return ColonyMetrics(
            colony_id=self.colony_id,
            total_tokens_prompt=total_prompt,
            total_tokens_completion=total_completion,
            total_tool_calls=total_tools,
            rounds=list(self._rounds),
            caste_activity=caste_agg,
        )

    @property
    def total_tokens(self) -> int:
        """Total tokens (prompt + completion) across all rounds."""
        m = self.get_colony_metrics()
        return m.total_tokens_prompt + m.total_tokens_completion


# ===========================================================================
# Topology Janitor (v0.7.7)
# ===========================================================================


class TopologyJanitor:
    """Evaluates convergence metrics and applies route penalties/rewards.

    Penalty algorithm:
    - If round wall-clock > 1.5x baseline, apply penalty_weight to all
      edges in the topology that carried traffic this round.
    - If round wall-clock <= baseline AND governance didn't intervene,
      apply reward_weight (positive) to those edges.

    Parameters
    ----------
    baseline_ms : float
        Expected round duration in milliseconds (default 45000 = 45s).
    penalty_weight : float
        Weight factor for penalized routes (default -0.8, meaning 20% of original).
    reward_weight : float
        Weight factor for rewarded routes (default 0.2, meaning 120% of original).
    """

    def __init__(
        self,
        baseline_ms: float = 45000.0,
        penalty_weight: float = -0.8,
        reward_weight: float = 0.2,
    ) -> None:
        self.baseline_ms = baseline_ms
        self.penalty_weight = penalty_weight
        self.reward_weight = reward_weight
        self._pheromone_weights: dict[tuple[str, str], float] = {}
        self._history: list[ConvergenceMetrics] = []

    def evaluate(
        self,
        round_num: int,
        wall_clock_ms: float,
        topology: Topology,
        governance_intervened: bool = False,
    ) -> ConvergenceMetrics:
        """Evaluate convergence and update pheromone weights."""
        adjustments: list[dict[str, Any]] = []
        penalty = 0.0
        reward = 0.0

        if wall_clock_ms > self.baseline_ms * 1.5:
            # Penalize all active edges
            penalty = self.penalty_weight
            for edge in topology.edges:
                key = (edge.sender, edge.receiver)
                current = self._pheromone_weights.get(key, 1.0)
                new_weight = max(0.1, current * (1.0 + penalty))
                self._pheromone_weights[key] = new_weight
                adjustments.append({
                    "sender": edge.sender,
                    "receiver": edge.receiver,
                    "old_weight": current,
                    "new_weight": new_weight,
                    "reason": "slow_round",
                })
        elif not governance_intervened:
            # Reward edges (cap at 2.0)
            reward = self.reward_weight
            for edge in topology.edges:
                key = (edge.sender, edge.receiver)
                current = self._pheromone_weights.get(key, 1.0)
                new_weight = min(2.0, current * (1.0 + reward))
                self._pheromone_weights[key] = new_weight
                adjustments.append({
                    "sender": edge.sender,
                    "receiver": edge.receiver,
                    "old_weight": current,
                    "new_weight": new_weight,
                    "reason": "good_round",
                })

        metrics = ConvergenceMetrics(
            round_num=round_num,
            wall_clock_ms=wall_clock_ms,
            baseline_ms=self.baseline_ms,
            penalty_applied=penalty,
            reward_applied=reward,
            route_adjustments=adjustments,
        )
        self._history.append(metrics)
        return metrics

    @property
    def pheromone_weights(self) -> dict[tuple[str, str], float]:
        return dict(self._pheromone_weights)

    @property
    def history(self) -> list[ConvergenceMetrics]:
        return list(self._history)


# ===========================================================================
# Orchestrator
# ===========================================================================


class Orchestrator:
    """
    Runs the 5-phase DyTopo loop for a single colony.

    Parameters
    ----------
    context_tree : AsyncContextTree
        Shared colony state store.
    config : FormicOSConfig
        Top-level configuration.
    colony_id : str
        Unique colony identifier.
    archivist : Archivist | None
        Round summarizer / TKG extractor / skill distiller.
    governance : GovernanceEngine | None
        Convergence and stall detector.
    skill_bank : SkillBank | None
        Cross-colony skill library.
    audit_logger : AuditLogger | None
        Append-only JSONL audit log.
    embedder : Any | None
        Sentence embedding model for DyTopo routing.
    """

    def __init__(
        self,
        context_tree: AsyncContextTree,
        config: FormicOSConfig,
        colony_id: str,
        *,
        archivist: Archivist | None = None,
        governance: GovernanceEngine | None = None,
        skill_bank: SkillBank | None = None,
        audit_logger: AuditLogger | None = None,
        embedder: Any | None = None,
        is_test_flight: bool = False,
        caste_recipes: dict | None = None,
        resume_directive: ResumeDirective | None = None,
    ) -> None:
        self.ctx: AsyncContextTree = context_tree
        self.config: FormicOSConfig = config
        self.colony_id = colony_id
        self.archivist: Archivist | None = archivist
        self.governance: GovernanceEngine | None = governance
        self.skill_bank: SkillBank | None = skill_bank
        self.audit: AuditLogger | None = audit_logger
        self.embedder: Any | None = embedder

        # Mutable loop state
        self._current_round: int = 0
        self._max_rounds: int = 0
        self._cancelled: bool = False
        self._direction_hint: str | None = None

        # Round history for Phase 1 injection
        self._round_history: list[dict[str, Any]] = []

        # Topology cache (Phase 3)
        self._cached_topology: Topology | None = None
        self._cached_intents: dict[str, dict[str, str]] | None = None

        # Governance intervention for next Phase 1
        self._pending_intervention: str | None = None

        # Previous round summary vector for governance convergence check
        self._prev_summary_vec: Any | None = None

        # Agent timeout from config
        self._agent_timeout: int = _DEFAULT_AGENT_TIMEOUT
        if hasattr(config, "inference") and hasattr(config.inference, "timeout_seconds"):
            self._agent_timeout = config.inference.timeout_seconds

        # Session ID (generated at run start)
        self._session_id: str = ""

        # Metrics accumulator (v0.7.3)
        self._metrics = MetricsAccumulator(colony_id)

        # Budget constraints (v0.7.3) — set via run() from ColonyConfig
        self._budget: BudgetConstraints | None = None

        # Webhook dispatcher (v0.7.3) — set externally before run()
        self._webhook_dispatcher: WebhookDispatcher | None = None
        self._webhook_url: str | None = None
        self._client_id: str | None = None

        # Janitor Protocol (v0.7.7)
        self._janitor = TopologyJanitor()
        self._timeline_spans: list[TimelineSpan] = []

        # v0.8.0: CFO expense audit (set by colony_manager when CFO agents exist)
        self._cfo_toolkit: Any | None = None
        self._cfo_factory: Any | None = None

        # Test flight mode (v0.7.8)
        self._is_test_flight: bool = is_test_flight

        # Caste recipes — Configuration as Code overlay (v0.8.0)
        self._caste_recipes: dict = caste_recipes or {}

        # Durable execution — resume directive (v0.8.0)
        self._resume_directive: ResumeDirective | None = resume_directive

        # Voting parallelism — node configs (v0.8.0)
        self._voting_configs: dict[str, VotingNodeConfig] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        task: str,
        agents: list[Agent],
        max_rounds: int,
        callbacks: dict[str, Any] | None = None,
    ) -> SessionResult:
        """
        Execute the 5-phase DyTopo loop.

        Parameters
        ----------
        task : str
            The colony objective.
        agents : list[Agent]
            Pre-constructed agent instances.  The first agent whose
            caste is ``manager`` is used for Phase 1 goal-setting.
        max_rounds : int
            Maximum number of orchestration rounds.
        callbacks : dict | None
            Optional dict with keys:
              on_round_update(round, phase, data)
              on_stream_token(agent_id, token)
              on_tool_call(agent_id, tool, args)
              on_approval_request(agent_id, tool, args) -> bool

        Returns
        -------
        SessionResult
        """
        rd = self._resume_directive

        if rd is not None:
            # ── RESUME path: restore state from checkpoint ────────────
            self._session_id = rd.session_id
            self._current_round = rd.resume_from_round
            self._max_rounds = rd.max_rounds
            self._cancelled = False
            self._round_history = list(rd.round_history)
            self._cached_topology = None
            self._cached_intents = None
            self._pending_intervention = None
            self._metrics = MetricsAccumulator(self.colony_id)
            self._timeline_spans = []
            self._janitor = TopologyJanitor()
            self._loop_epoch = _time.monotonic()

            # Restore pheromone weights (string keys → tuple keys)
            for key_str, weight in rd.pheromone_weights.items():
                parts = key_str.split("|", 1)
                if len(parts) == 2:
                    self._janitor._pheromone_weights[(parts[0], parts[1])] = weight

            # Restore governance convergence streak
            if self.governance and rd.convergence_streak:
                if hasattr(self.governance, "_convergence_streak"):
                    self.governance._convergence_streak = rd.convergence_streak

            # Restore prev_summary_vec
            if rd.prev_summary_vec is not None:
                self._prev_summary_vec = np.array(
                    rd.prev_summary_vec, dtype=np.float64,
                )
            else:
                self._prev_summary_vec = None

            # Consume directive (one-shot)
            self._resume_directive = None

            logger.info(
                "Resuming colony '%s' from round %d (session %s, "
                "max_rounds=%d, history_len=%d)",
                self.colony_id, self._current_round, self._session_id,
                self._max_rounds, len(self._round_history),
            )
        else:
            # ── FRESH start path (existing behavior) ──────────────────
            self._session_id = f"{self.colony_id}_{uuid.uuid4().hex[:8]}"
            self._current_round = 0
            self._max_rounds = max_rounds
            self._cancelled = False
            self._round_history = []
            self._cached_topology = None
            self._cached_intents = None
            self._pending_intervention = None
            self._prev_summary_vec = None
            self._metrics = MetricsAccumulator(self.colony_id)
            self._timeline_spans = []
            self._janitor = TopologyJanitor()
            self._loop_epoch = _time.monotonic()

        # Separate manager from worker agents
        manager = self._find_manager(agents)
        workers = [a for a in agents if a is not manager] if manager else list(agents)

        # Apply per-caste governance trigger overrides (most conservative wins)
        if self._caste_recipes and self.governance:
            active_castes = {a.caste for a in agents}
            for caste_name in active_castes:
                recipe = self._caste_recipes.get(caste_name)
                if recipe and getattr(recipe, "governance_triggers", None):
                    self.governance.apply_overrides(recipe.governance_triggers)

        # Store initial colony state in context tree
        await self._ctx_set("colony", "task", task)
        await self._ctx_set("colony", "status", ColonyStatus.RUNNING.value)
        await self._ctx_set("colony", "session_id", self._session_id)
        await self._ctx_set("colony", "colony_id", self.colony_id)

        if self.audit:
            self.audit.log_session_start(self._session_id, task, {
                "colony_id": self.colony_id,
                "max_rounds": max_rounds,
                "agent_count": len(agents),
            })

        status = ColonyStatus.COMPLETED
        final_answer: str | None = None
        governance_note: str | None = None
        skill_ids: list[str] = []

        try:
            # ── Main loop (while, not for -- allows extend_rounds) ────
            while self._current_round < self._max_rounds:
                if self._cancelled:
                    status = ColonyStatus.COMPLETED
                    governance_note = "Cancelled by operator."
                    break

                round_num = self._current_round
                _round_start = _time.monotonic()
                await self._ctx_set("colony", "round", round_num)

                # ── Phase 1: Goal ─────────────────────────────────────
                await _fire_callback(callbacks, "on_round_update", round_num, "phase_1_goal", {})
                round_goal, terminate, answer = await self._phase1_goal(
                    task, manager, round_num, callbacks,
                )
                if terminate:
                    final_answer = answer
                    break

                if self.audit:
                    self.audit.log_round(self._session_id, round_num, "goal", {"goal": round_goal})

                # ── Phase 2 & 3: Intent + Routing ─────────────────────
                # Round 0: broadcast — all agents execute in parallel,
                # no routing. Agents have no work yet so intent
                # descriptors are meaningless on the first round.
                if round_num == 0:
                    logger.info("Phase 2/3: Round 0 — broadcast mode (skip routing)")
                    intents = {}
                    topology = self._broadcast_topology(workers)
                else:
                    await _fire_callback(callbacks, "on_round_update", round_num, "phase_2_intent", {})
                    intents = await self._phase2_intent(task, workers, callbacks)
                    logger.info("Phase 2: %d intents generated", len(intents))

                    if self.audit:
                        self.audit.log_round(self._session_id, round_num, "intent", intents)

                    await _fire_callback(callbacks, "on_round_update", round_num, "phase_3_routing", {})
                    topology = await self._phase3_routing(workers, intents, callbacks)

                if self.audit:
                    self.audit.log_round(self._session_id, round_num, "routing", {
                        "execution_order": topology.execution_order,
                        "edge_count": len(topology.edges),
                    })

                # Record routing decision
                await self._record_decision(
                    round_num, DecisionType.ROUTING,
                    f"Topology: {len(topology.edges)} edges, "
                    f"order: {topology.execution_order}",
                )

                # Store topology in context tree for API visibility
                topo_snapshot = {
                    "round": round_num,
                    "edges": [
                        {"sender": e.sender, "receiver": e.receiver, "weight": e.weight}
                        for e in topology.edges
                    ],
                    "execution_order": topology.execution_order,
                    "density": topology.density,
                    "nodes": [
                        {
                            "id": w.id,
                            "caste": w.caste.value if hasattr(w.caste, "value") else str(w.caste),
                        }
                        for w in workers
                    ],
                }
                await self._ctx_set("colony", "topology", topo_snapshot)

                # Append to topology history (one snapshot per round)
                topo_history = self.ctx.get("colony", "topology_history", [])
                topo_history.append(topo_snapshot)
                await self._ctx_set("colony", "topology_history", topo_history)

                # ── Phase 3.5: Skill Injection ────────────────────────
                await _fire_callback(callbacks, "on_round_update", round_num, "phase_3_5_skills", {})
                skill_context = await self._phase35_skills(round_goal)

                # ── Phase 4: Execution ────────────────────────────────
                await _fire_callback(callbacks, "on_round_update", round_num, "phase_4_execution", {})
                agent_outputs = await self._phase4_execution(
                    workers, topology, round_goal, skill_context, callbacks,
                )

                logger.info(
                    "Phase 4: %d agents executed, outputs: %s",
                    len(agent_outputs),
                    {aid: len(out.output) for aid, out in agent_outputs.items()},
                )

                if self.audit:
                    self.audit.log_round(self._session_id, round_num, "execution", {
                        "agents_completed": list(agent_outputs.keys()),
                    })

                # ── Phase 4.5: Expense Audit ──────────────────────────
                # If any agent created pending expense requests, pause
                # and instantiate a CFO agent to review and sign them.
                if self._cfo_toolkit is not None and self._cfo_factory is not None:
                    await self._phase45_expense_audit(
                        workers, agent_outputs, round_goal,
                        skill_context, callbacks,
                    )

                # ── Phase 5: Compression & Governance ─────────────────
                await _fire_callback(callbacks, "on_round_update", round_num, "phase_5_governance", {})
                should_halt, halt_reason = await self._phase5_compression_governance(
                    round_num, round_goal, agent_outputs, callbacks,
                )

                # Record round in history
                self._round_history.append({
                    "round": round_num,
                    "goal": round_goal,
                    "summary": f"Round {round_num}: {round_goal}",
                    "agent_outputs": {
                        aid: {
                            "approach": out.approach,
                            "output": out.output[:500],
                        }
                        for aid, out in agent_outputs.items()
                    },
                })

                await _fire_callback(callbacks, "on_round_update", round_num, "round_complete", {
                    "goal": round_goal,
                    "agents": list(agent_outputs.keys()),
                })

                # Record round duration metric
                _round_duration_ms = (_time.monotonic() - _round_start) * 1000
                _fire_sync_callback(callbacks, "on_metric", "colony_round_duration_ms", _round_duration_ms)

                # Record per-round token metrics (v0.7.3)
                agent_castes = {a.id: a.caste for a in agents if hasattr(a, "caste")}
                self._metrics.record_round(
                    round_num, agent_outputs, _round_duration_ms, agent_castes,
                )

                # Timeline span: full round (v0.7.7)
                _round_start_ms = (_round_start - self._loop_epoch) * 1000
                self._record_span(
                    round_num, "round",
                    start_ms=_round_start_ms,
                    duration_ms=_round_duration_ms,
                    is_critical_path=True,
                    agents=list(agent_outputs.keys()),
                )

                # Janitor Protocol: evaluate convergence (v0.7.7)
                governance_intervened = (
                    self._pending_intervention is not None or should_halt
                )
                self._janitor.evaluate(
                    round_num, _round_duration_ms, topology, governance_intervened,
                )

                # Check budget constraints (v0.7.3)
                budget_exceeded, budget_reason = self._check_budget()
                if budget_exceeded:
                    governance_note = budget_reason
                    status = ColonyStatus.HALTED_BUDGET_EXHAUSTED
                    break

                if should_halt:
                    governance_note = halt_reason
                    break

                self._current_round += 1

                # v0.8.0: Durable checkpoint between rounds
                try:
                    await self._checkpoint()
                except Exception as ckpt_exc:
                    logger.warning(
                        "Checkpoint write failed (colony %s, round %d): %s",
                        self.colony_id, self._current_round, ckpt_exc,
                    )

        except Exception as exc:
            logger.error(
                "Orchestrator loop failed (colony %s, round %d): %s",
                self.colony_id, self._current_round, exc,
            )
            if self.audit:
                self.audit.log_error(
                    self._session_id, "orchestrator_crash",
                    str(exc), traceback.format_exc(),
                )
            status = ColonyStatus.FAILED
            governance_note = f"Orchestrator error: {exc}"

        # ── Fallback final answer extraction ──────────────────────────
        # If max_rounds completed without explicit manager termination
        # AND no governance halt, extract the best answer from outputs.
        if not final_answer and not governance_note and self._round_history:
            logger.info("No explicit termination — extracting fallback final answer")
            last_round = self._round_history[-1]
            agent_outs = last_round.get("agent_outputs", {})

            # Prefer coder/architect output (most likely to have deliverables)
            preferred_castes = ["coder", "architect", "designer", "researcher", "reviewer"]
            best_output = None
            for caste_pref in preferred_castes:
                for aid, out_info in agent_outs.items():
                    if caste_pref in aid.lower() and out_info.get("output"):
                        best_output = out_info["output"]
                        break
                if best_output:
                    break

            # Fallback: any agent's last output
            if not best_output:
                for aid, out_info in agent_outs.items():
                    if out_info.get("output"):
                        best_output = out_info["output"]
                        break

            if best_output:
                final_answer = best_output
                logger.info(
                    "Fallback final answer extracted (%d chars)",
                    len(final_answer),
                )

        # ── Post-colony ───────────────────────────────────────────────
        skill_ids = await self._post_colony(task, status, governance_note)

        await self._ctx_set("colony", "status", status.value)
        if final_answer or governance_note:
            await self._ctx_set("colony", "final_answer", final_answer or governance_note)

        if self.audit:
            self.audit.log_session_end(
                self._session_id, status.value,
                final_answer or governance_note or "completed",
            )

        await _fire_callback(callbacks, "on_round_update", self._current_round, "colony_complete", {
            "status": status.value,
            "rounds_completed": self._current_round,
        })

        # Fire the dedicated colony_complete callback (broadcasts distinct WS event)
        await _fire_callback(callbacks, "on_colony_complete", status.value)

        # Webhook dispatch (v0.7.3, enriched v0.7.4, v0.7.5 epoch summaries)
        if self._webhook_dispatcher and self._webhook_url:
            metrics = self._metrics.get_colony_metrics().model_dump()
            epoch_summaries = [
                es.model_dump() for es in self.ctx.get_epoch_summaries()
            ]
            await self._webhook_dispatcher.dispatch(
                url=self._webhook_url,
                payload={
                    "type": "colony.completed",
                    "colony_id": self.colony_id,
                    "client_id": self._client_id,
                    "status": status.value,
                    "rounds_completed": self._current_round,
                    "metrics": metrics,
                    "epoch_summaries": epoch_summaries,
                    "final_answer": final_answer or governance_note,
                    "timestamp": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
                },
                colony_id=self.colony_id,
            )

        return SessionResult(
            session_id=self._session_id,
            task=task,
            status=status,
            rounds_completed=self._current_round,
            final_answer=final_answer or governance_note,
            skill_ids=skill_ids,
        )

    def extend_rounds(
        self,
        n: int,
        direction_hint: str | None = None,
    ) -> int:
        """Extend the maximum round count by *n*.

        Returns the new max_rounds value.
        """
        self._max_rounds += n
        if direction_hint:
            self._direction_hint = direction_hint
        return self._max_rounds

    def cancel(self) -> None:
        """Signal the orchestrator to stop after the current round."""
        self._cancelled = True

    def _check_budget(self) -> tuple[bool, str | None]:
        """Check if budget constraints are exceeded.

        Returns (exceeded: bool, reason: str | None).
        """
        if self._budget is None:
            return False, None

        if self._budget.max_epochs and self._current_round + 1 >= self._budget.max_epochs:
            return True, (
                f"Budget: max_epochs ({self._budget.max_epochs}) reached"
            )

        if self._budget.max_total_tokens:
            total = self._metrics.total_tokens
            if total >= self._budget.max_total_tokens:
                return True, (
                    f"Budget: max_total_tokens ({self._budget.max_total_tokens}) "
                    f"exceeded ({total})"
                )

        if self._budget.max_usd_cents:
            logger.info(
                "Budget max_usd_cents=%d set but cost enforcement deferred to v0.8.0",
                self._budget.max_usd_cents,
            )

        return False, None

    # ------------------------------------------------------------------
    # Durable Execution -- Checkpoint (v0.8.0)
    # ------------------------------------------------------------------

    async def _checkpoint(self) -> None:
        """Write a durable checkpoint to the context tree after a completed round.

        Captures all ephemeral orchestrator state needed to resume from the
        last completed round: round_history, metrics, janitor pheromone
        weights, governance convergence streak, and prev_summary_vec.

        Persists the context tree to the session file using atomic write
        (STRICTURE-002 compliant — I/O offloaded via ctx.save → to_thread).
        """
        # Serialize pheromone weights with string keys for JSON compat
        pheromone: dict[str, float] = {}
        if hasattr(self._janitor, "_pheromone_weights"):
            pheromone = {
                f"{s}|{r}": w
                for (s, r), w in self._janitor._pheromone_weights.items()
            }

        # Serialize prev_summary_vec (numpy array → list)
        prev_vec: list[float] | None = None
        if self._prev_summary_vec is not None:
            if hasattr(self._prev_summary_vec, "tolist"):
                prev_vec = self._prev_summary_vec.tolist()
            else:
                prev_vec = list(self._prev_summary_vec)

        checkpoint = CheckpointMeta(
            colony_id=self.colony_id,
            session_id=self._session_id,
            completed_round=self._current_round,
            max_rounds=self._max_rounds,
            task=self.ctx.get("colony", "task", ""),
            round_history=list(self._round_history),
            pheromone_weights=pheromone,
            convergence_streak=(
                self.governance._convergence_streak
                if self.governance and hasattr(self.governance, "_convergence_streak")
                else 0
            ),
            prev_summary_vec=prev_vec,
        )

        await self._ctx_set("colony", "checkpoint", checkpoint.model_dump())

        # Persist context tree to session file (atomic write, threaded)
        # STRICTURE-002: offload mkdir to thread in async context
        session_dir = Path(f".formicos/sessions/{self.colony_id}")
        await asyncio.to_thread(session_dir.mkdir, parents=True, exist_ok=True)
        session_file = session_dir / "context.json"
        await self.ctx.save(session_file)

        logger.info(
            "Checkpoint written: colony=%s round=%d session=%s",
            self.colony_id, self._current_round, self._session_id,
        )

    # ------------------------------------------------------------------
    # Voting Parallelism -- Configuration (v0.8.0)
    # ------------------------------------------------------------------

    def configure_voting_nodes(
        self,
        voting_nodes: list[VotingNodeConfig],
    ) -> None:
        """Register voting node configurations before run().

        Called by ColonyManager.start() after constructing the orchestrator
        but before calling run().
        """
        for vn in voting_nodes:
            self._voting_configs[vn.node_id] = vn
        if self._voting_configs:
            logger.info(
                "Voting parallelism configured: %d node(s): %s",
                len(self._voting_configs),
                list(self._voting_configs.keys()),
            )

    # ------------------------------------------------------------------
    # Phase 1 -- Goal
    # ------------------------------------------------------------------

    async def _phase1_goal(
        self,
        task: str,
        manager: Agent | None,
        round_num: int,
        callbacks: dict[str, Any] | None,
    ) -> tuple[str, bool, str | None]:
        """
        Call the Manager agent to produce the round goal.

        Uses execute_raw() for a direct LLM call with the manager's own
        JSON schema {"goal", "terminate", "final_answer"} — not the worker
        execution wrapper {"approach", "output", "status"}.

        Returns (goal, terminate, final_answer).
        """
        if manager is None:
            return f"Continue working on: {task}", False, None

        logger.info("═══ Round %d/%d ═══", round_num, self._max_rounds)

        # Build round history with actual agent outputs (Fix 5)
        history_block = ""
        if self._round_history:
            history_lines: list[str] = []
            for rh in self._round_history[-3:]:
                line = f"\n--- Round {rh['round']} (goal: {rh.get('goal', 'N/A')}) ---\n"
                agent_outs = rh.get("agent_outputs", {})
                if agent_outs:
                    for aid, out_info in agent_outs.items():
                        out_text = out_info.get("output", "")[:300]
                        line += f"  [{aid}]: {out_text}\n"
                else:
                    line += f"  {rh.get('summary', 'No outputs')}\n"
                history_lines.append(line)
            history_block = "\n".join(history_lines)
        else:
            history_block = "(first round — no previous outputs yet)"

        # Inject direction hint from extend_rounds if present
        hint_block = ""
        if self._direction_hint:
            hint_block = f"\n\nOPERATOR DIRECTION: {self._direction_hint}"
            self._direction_hint = None  # consume once

        # Inject governance intervention if present
        intervention_block = ""
        if self._pending_intervention:
            intervention_block = (
                f"\n\nGOVERNANCE INTERVENTION: {self._pending_intervention}"
            )
            self._pending_intervention = None  # consume once

        user_prompt = (
            f"TASK: {task}\n\n"
            f"PREVIOUS ROUND OUTPUTS:\n{history_block}\n\n"
            f"CURRENT ROUND: {round_num} of {self._max_rounds}"
            f"{hint_block}"
            f"{intervention_block}\n\n"
            "Based on the task and previous outputs, set a specific goal for this round.\n"
            "If the task is complete, terminate with the final answer.\n\n"
            "Respond with ONLY a JSON object:\n"
            '{"goal": "<specific round goal>", "terminate": false}\n'
            "or if complete:\n"
            '{"goal": "", "terminate": true, "final_answer": "<complete answer with all deliverables>"}'
        )

        try:
            raw = await asyncio.wait_for(
                manager.execute_raw(
                    system_override=manager.system_prompt,
                    user_prompt=user_prompt,
                ),
                timeout=self._agent_timeout,
            )

            # Parse manager response directly
            try:
                from json_repair import repair_json
                parsed = json.loads(repair_json(raw))
            except Exception:
                parsed = {"goal": raw[:500], "terminate": False}

            goal = parsed.get("goal", f"Continue: {task}")
            terminate = parsed.get("terminate", False)
            final_answer = parsed.get("final_answer") if terminate else None

            logger.info(
                "Phase 1: goal='%s' terminate=%s",
                goal[:80], terminate,
            )

            # Record manager goal decision
            await self._record_decision(
                round_num, DecisionType.MANAGER_GOAL,
                f"Goal: {goal}" + (f" | TERMINATE: {final_answer[:200] if final_answer else ''}" if terminate else ""),
            )

            return goal, bool(terminate), final_answer

        except asyncio.TimeoutError:
            logger.warning(
                "Manager timed out in Phase 1 (round %d)", round_num,
            )
            return f"Continue working on: {task}", False, None
        except Exception as exc:
            logger.error("Phase 1 manager failed: %s", exc)
            return f"Continue working on: {task}", False, None

    # ------------------------------------------------------------------
    # Phase 2 -- Intent
    # ------------------------------------------------------------------

    async def _phase2_intent(
        self,
        task: str,
        workers: list[Agent],
        callbacks: dict[str, Any] | None,
    ) -> dict[str, dict[str, str]]:
        """
        Each worker agent produces {key, query} intent descriptors.
        """
        intents: dict[str, dict[str, str]] = {}

        async def _get_intent(agent: Agent) -> None:
            try:
                intent = await asyncio.wait_for(
                    agent.generate_intent(task, self._round_history),
                    timeout=self._agent_timeout,
                )
                intents[agent.id] = intent
            except asyncio.TimeoutError:
                logger.warning("Agent '%s' timed out in Phase 2", agent.id)
                intents[agent.id] = {
                    "key": f"{agent.caste.value if hasattr(agent.caste, 'value') else agent.caste} output",
                    "query": "general input",
                }
            except Exception as exc:
                logger.error("Agent '%s' Phase 2 failed: %s", agent.id, exc)
                intents[agent.id] = {
                    "key": f"{agent.caste.value if hasattr(agent.caste, 'value') else agent.caste} output",
                    "query": "general input",
                }

        # Run all intent generations concurrently
        await asyncio.gather(*[_get_intent(a) for a in workers])
        return intents

    # ------------------------------------------------------------------
    # Phase 3 -- Routing
    # ------------------------------------------------------------------

    async def _phase3_routing(
        self,
        workers: list[Agent],
        intents: dict[str, dict[str, str]],
        callbacks: dict[str, Any] | None,
    ) -> Topology:
        """
        Build the DyTopo routing DAG from intent embeddings.

        Caches the topology if intents have not changed significantly
        (cosine delta < 0.05 from previous round).
        """
        if not workers or not intents:
            return Topology(edges=[], execution_order=[a.id for a in workers])

        # Check topology cache -- reuse if intents unchanged
        if self._cached_topology and self._cached_intents:
            if self._intents_unchanged(intents):
                logger.debug("Phase 3: reusing cached topology (intents unchanged)")
                return self._cached_topology

        # Check broadcast_fallback config
        broadcast_fallback = True
        if hasattr(self.config, "routing"):
            broadcast_fallback = getattr(
                self.config.routing, "broadcast_fallback", True
            )

        # Need an embedder for routing
        if self.embedder is None:
            logger.warning(
                "Phase 3: no embedder available, using chain fallback"
            )
            return self._chain_topology(sorted(intents.keys()))

        try:
            from src.router import build_topology

            agent_ids = sorted(intents.keys())
            tau = 0.35
            k_in = 3
            if hasattr(self.config, "routing"):
                tau = getattr(self.config.routing, "tau", 0.35)
                k_in = getattr(self.config.routing, "k_in", 3)

            logger.info(
                "Phase 3: routing %d agents, tau=%.2f, k_in=%d",
                len(agent_ids), tau, k_in,
            )

            # v0.7.8: Fix DyTopo seed for deterministic routing
            if self._is_test_flight:
                np.random.seed(42)

            topology = build_topology(
                agent_ids=agent_ids,
                descriptors=intents,
                embedder=self.embedder,
                tau=tau,
                k_in=k_in,
                pheromone_weights=self._janitor.pheromone_weights or None,
            )

            logger.info(
                "Phase 3: %d edges, order=%s, density=%.3f",
                len(topology.edges), topology.execution_order,
                topology.density,
            )

            # Broadcast fallback: if routing produced 0 edges but we
            # have 2+ agents, fall back to a chain so outputs flow
            if (
                not topology.edges
                and len(agent_ids) >= 2
                and broadcast_fallback
            ):
                logger.info(
                    "Phase 3: 0 edges from DyTopo, applying chain fallback"
                )
                topology = self._chain_topology(agent_ids)

            # Cache for next round
            self._cached_topology = topology
            self._cached_intents = {
                aid: dict(d) for aid, d in intents.items()
            }

            return topology

        except Exception as exc:
            logger.error("Phase 3 routing failed: %s", exc)
            return self._chain_topology(sorted(intents.keys()))

    def _intents_unchanged(
        self,
        new_intents: dict[str, dict[str, str]],
    ) -> bool:
        """Check if intents have changed from cached version."""
        if self._cached_intents is None:
            return False
        if set(new_intents.keys()) != set(self._cached_intents.keys()):
            return False
        for aid in new_intents:
            if aid not in self._cached_intents:
                return False
            old = self._cached_intents[aid]
            new = new_intents[aid]
            if old.get("key") != new.get("key") or old.get("query") != new.get("query"):
                return False
        return True

    @staticmethod
    def _broadcast_topology(workers: list[Agent]) -> Topology:
        """Build a broadcast topology: all agents execute in parallel, no edges.

        Used for Round 0 when agents have no prior work to route.
        """
        agent_ids = [a.id for a in workers]
        return Topology(
            edges=[],
            execution_order=agent_ids,
            density=0.0,
            isolated_agents=[],
        )

    @staticmethod
    def _chain_topology(agent_ids: list[str]) -> Topology:
        """Build a linear chain topology: agent[0] → agent[1] → ... → agent[N-1].

        Used as broadcast fallback when DyTopo produces 0 edges.
        """
        edges = []
        for i in range(len(agent_ids) - 1):
            edges.append(TopologyEdge(
                sender=agent_ids[i],
                receiver=agent_ids[i + 1],
                weight=1.0,
            ))
        density = len(edges) / max(len(agent_ids) * (len(agent_ids) - 1), 1)
        return Topology(
            edges=edges,
            execution_order=list(agent_ids),
            density=density,
            isolated_agents=[],
        )

    # ------------------------------------------------------------------
    # Phase 3.5 -- Skill Injection
    # ------------------------------------------------------------------

    async def _phase35_skills(
        self,
        round_goal: str,
    ) -> str | None:
        """Query SkillBank for skills relevant to the round goal."""
        if self.skill_bank is None:
            return None

        try:
            skills = self.skill_bank.retrieve(round_goal)
            if not skills:
                return None

            skill_text = self.skill_bank.format_for_injection(skills)

            # Store in context tree for agent context assembly
            await self._ctx_set("colony", "skill_context", skill_text)

            return skill_text
        except Exception as exc:
            logger.warning("Phase 3.5 skill retrieval failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Phase 4 -- Execution (parallel by topological level)
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_topo_levels(
        agent_ids: list[str],
        edges: list[TopologyEdge],
    ) -> list[list[str]]:
        """Partition agents into topological levels for parallel execution.

        Level 0: agents with no upstream dependencies (in-degree 0).
        Level k: agents whose all dependencies are in levels < k.

        Broadcast (0 edges) produces one level — maximum parallelism.
        Chain produces N levels of 1 — sequential (same as before).
        """
        predecessors: dict[str, set[str]] = {aid: set() for aid in agent_ids}
        for edge in edges:
            if edge.receiver in predecessors:
                predecessors[edge.receiver].add(edge.sender)

        assigned: set[str] = set()
        levels: list[list[str]] = []

        while len(assigned) < len(agent_ids):
            # Agents whose all predecessors have already been assigned
            level = sorted(
                a for a in agent_ids
                if a not in assigned and predecessors[a] <= assigned
            )
            if not level:
                # Safety: force-assign remaining (cycle or orphan)
                level = sorted(a for a in agent_ids if a not in assigned)
            levels.append(level)
            assigned.update(level)

        return levels

    async def _execute_agent(
        self,
        agent: Agent,
        topology: Topology,
        agent_outputs: dict[str, AgentOutput],
        round_goal: str,
        skill_context: str | None,
        callbacks: dict[str, Any] | None,
    ) -> tuple[str, AgentOutput]:
        """Execute a single agent with fault isolation.

        Returns (agent_id, AgentOutput).  Reads from *agent_outputs*
        for upstream messages — safe because all upstream agents are in
        previous topological levels and already finished.
        """
        agent_id = agent.id

        # Gather routed messages from upstream agents
        routed_messages = self._gather_routed_messages(
            agent_id, topology, agent_outputs,
        )

        # Inject agent's own previous-round output so it can build on it
        if self._round_history:
            prev_outs = self._round_history[-1].get("agent_outputs", {})
            prev_own = prev_outs.get(agent_id)
            if prev_own and getattr(prev_own, "output", ""):
                routed_messages.insert(
                    0,
                    f"[YOUR PREVIOUS ROUND OUTPUT — build on this, do NOT repeat it]:\n"
                    f"{prev_own.output[:3000]}",
                )

        # Assemble context from the context tree (budget-capped to avoid
        # KV cache bloat — prompts must stay well under ctx-size 8192)
        context = self.ctx.assemble_agent_context(
            agent_id=agent_id,
            caste=agent.caste.value if hasattr(agent.caste, "value") else str(agent.caste),
            token_budget=4000,
        )

        try:
            output = await asyncio.wait_for(
                agent.execute(
                    context=context,
                    round_goal=round_goal,
                    routed_messages=routed_messages,
                    skill_context=skill_context,
                    callbacks=self._agent_callbacks(callbacks),
                ),
                timeout=self._agent_timeout,
            )
            return agent_id, output

        except asyncio.TimeoutError:
            logger.warning(
                "Agent '%s' timed out in Phase 4 (timeout=%ds)",
                agent_id, self._agent_timeout,
            )
            if self.audit:
                self.audit.log_error(
                    self._session_id, "agent_timeout",
                    f"Agent '{agent_id}' timed out in Phase 4",
                )
            return agent_id, AgentOutput(
                output=f"ERROR: Agent '{agent_id}' timed out after {self._agent_timeout}s.",
            )

        except ContextExceededError as ctx_exc:
            logger.warning(
                "Agent '%s' hit hard context window limit: %s",
                agent_id, ctx_exc,
            )
            if self.audit:
                self.audit.log_error(
                    self._session_id, "context_exceeded",
                    f"Agent '{agent_id}': {ctx_exc}",
                )
            return agent_id, AgentOutput(
                output=(
                    "[SYSTEM_HALT] You exceeded the hard context window. "
                    "Truncate your slice requests immediately."
                ),
            )

        except Exception as exc:
            logger.error(
                "Agent '%s' failed in Phase 4: %s", agent_id, exc,
            )
            if self.audit:
                self.audit.log_error(
                    self._session_id, "agent_execution_error",
                    f"Agent '{agent_id}': {exc}",
                )
            return agent_id, AgentOutput(
                output=f"ERROR: {type(exc).__name__}: {str(exc)[:500]}",
            )

    async def _phase4_execution(
        self,
        workers: list[Agent],
        topology: Topology,
        round_goal: str,
        skill_context: str | None,
        callbacks: dict[str, Any] | None,
    ) -> dict[str, AgentOutput]:
        """Execute agents in parallel by topological level.

        Agents at the same level have no inter-dependencies and run
        concurrently via ``asyncio.gather()``.  Agents in later levels
        wait for all earlier levels to complete first, so upstream
        outputs are available for routed message gathering.
        """
        agent_map = {a.id: a for a in workers}
        agent_outputs: dict[str, AgentOutput] = {}

        # Build execution order (fall back to agent_map keys if topology empty)
        exec_ids = topology.execution_order
        if not exec_ids:
            exec_ids = sorted(agent_map.keys())

        # Compute topological levels for parallel execution
        levels = self._compute_topo_levels(exec_ids, topology.edges)
        logger.info(
            "Phase 4: %d agents in %d topological level(s): %s",
            len(exec_ids), len(levels),
            [len(lvl) for lvl in levels],
        )

        for level_idx, level_agents in enumerate(levels):
            if self._cancelled:
                break

            # Filter to agents that actually exist, separate voting nodes
            regular_agents: list[Agent] = []
            voting_agents: list[Agent] = []
            for agent_id in level_agents:
                agent = agent_map.get(agent_id)
                if agent is None:
                    logger.warning("Agent '%s' in execution order but not found", agent_id)
                    continue
                if agent_id in self._voting_configs:
                    voting_agents.append(agent)
                else:
                    regular_agents.append(agent)

            all_agents = regular_agents + voting_agents
            if not all_agents:
                continue

            # Build coroutines — voting agents use _execute_voting_group
            coros = []
            for agent in regular_agents:
                coros.append(
                    self._execute_agent(
                        agent, topology, agent_outputs,
                        round_goal, skill_context, callbacks,
                    )
                )
            for agent in voting_agents:
                coros.append(
                    self._execute_voting_group(
                        agent, topology, agent_outputs,
                        round_goal, skill_context, callbacks,
                    )
                )

            if len(coros) == 1:
                aid, output = await coros[0]
                agent_outputs[aid] = output
            else:
                logger.info(
                    "Phase 4 level %d: running %d agents in parallel "
                    "(%d regular, %d voting): %s",
                    level_idx, len(all_agents),
                    len(regular_agents), len(voting_agents),
                    [a.id for a in all_agents],
                )
                results = await asyncio.gather(*coros)
                for aid, output in results:
                    agent_outputs[aid] = output

        return agent_outputs

    # ------------------------------------------------------------------
    # Phase 4.5 -- Expense Audit (CFO)
    # ------------------------------------------------------------------

    async def _phase45_expense_audit(
        self,
        workers: list[Agent],
        agent_outputs: dict[str, AgentOutput],
        round_goal: str,
        skill_context: str | None,
        callbacks: dict[str, Any] | None,
    ) -> None:
        """Scan workspace for pending expenses and run CFO agent if found.

        Creates an ephemeral CFO agent via AgentFactory when unsigned
        expense requests exist in ``expenses/pending/``.  The CFO reviews
        and approves or rejects each request, writing signed results to
        ``expenses/approved/`` or ``expenses/rejected/``.

        Only triggers when ``self._cfo_toolkit`` is set (i.e., the colony
        has a CFO caste).  No-op for colonies without CFO agents.
        """
        # Use the first worker's workspace (shared across colony)
        if not workers:
            return
        ws_root = workers[0].workspace_root
        pending_dir = Path(ws_root) / "expenses" / "pending"
        if not pending_dir.exists():
            return

        pending_files = list(pending_dir.glob("*.json"))
        if not pending_files:
            return

        logger.info(
            "Phase 4.5: %d pending expense(s) found — instantiating CFO agent",
            len(pending_files),
        )

        # Create ephemeral CFO agent via factory
        cfo_agent = self._cfo_factory.create(
            agent_id=f"cfo-{uuid.uuid4().hex[:8]}",
            caste="cfo",
            workspace_root=ws_root,
            colony_id=self.colony_id,
        )
        cfo_agent.config["cfo_toolkit"] = self._cfo_toolkit
        cfo_agent.config["colony_objective"] = round_goal

        # Build context listing all pending expenses
        expense_summaries: list[str] = []
        for pf in pending_files:
            try:
                data = json.loads(pf.read_text(encoding="utf-8"))
                expense_summaries.append(
                    f"- [{data.get('nonce', '?')}] ${data.get('amount', 0):.2f} → "
                    f"{data.get('target_api', '?')}: {data.get('justification', '?')}"
                )
            except Exception:
                continue

        context = (
            f"COLONY OBJECTIVE: {round_goal}\n\n"
            f"PENDING EXPENSE REQUESTS ({len(pending_files)}):\n"
            + "\n".join(expense_summaries)
        )

        try:
            cfo_output = await asyncio.wait_for(
                cfo_agent.execute(
                    context=context,
                    round_goal="Review and approve/reject all pending expense requests.",
                    routed_messages=None,
                    skill_context=skill_context,
                    callbacks=callbacks,
                ),
                timeout=120.0,
            )
            agent_outputs[cfo_agent.id] = cfo_output
            logger.info(
                "Phase 4.5: CFO '%s' completed — %d chars output",
                cfo_agent.id, len(cfo_output.output),
            )
        except asyncio.TimeoutError:
            logger.warning("Phase 4.5: CFO agent timed out after 120s")
        except Exception as exc:
            logger.error("Phase 4.5: CFO agent failed: %s", exc)

    def _gather_routed_messages(
        self,
        agent_id: str,
        topology: Topology,
        agent_outputs: dict[str, AgentOutput],
    ) -> list[str]:
        """
        Collect outputs from upstream agents based on topology edges.

        An edge with receiver == agent_id means the sender's output
        should be routed to this agent.
        """
        messages: list[str] = []
        for edge in topology.edges:
            if edge.receiver == agent_id and edge.sender in agent_outputs:
                upstream_output = agent_outputs[edge.sender]
                messages.append(
                    f"[{edge.sender}]: {upstream_output.output[:2000]}"
                )
        return messages

    # ------------------------------------------------------------------
    # Phase 4b -- Voting Parallelism
    # ------------------------------------------------------------------

    async def _execute_voting_group(
        self,
        agent: Agent,
        topology: Topology,
        agent_outputs: dict[str, AgentOutput],
        round_goal: str,
        skill_context: str | None,
        callbacks: dict[str, Any] | None,
    ) -> tuple[str, AgentOutput]:
        """Execute a voting node: spawn N replicas in parallel, collect outputs.

        Each replica gets an isolated workspace subdirectory and a divergent
        seed.  All replica outputs are stored in ``agent_outputs`` keyed by
        ``{node_id}_replica_{i}`` so the downstream reviewer can receive them
        via normal ``_gather_routed_messages()``.

        Synthetic ``TopologyEdge`` entries are injected from each replica to
        the configured ``reviewer_agent_id`` so Phase 4 routing works
        transparently at the reviewer's topological level.

        Returns ``(node_id, best_output)`` — where best_output is the first
        successful replica output (final selection is the reviewer's job).
        """
        node_id = agent.id
        voting_cfg = self._voting_configs[node_id]
        num_replicas = voting_cfg.replicas

        # Gather upstream messages (shared across all replicas)
        routed_messages = self._gather_routed_messages(
            node_id, topology, agent_outputs,
        )

        # Inject previous-round output (same as _execute_agent)
        if self._round_history:
            prev_outs = self._round_history[-1].get("agent_outputs", {})
            prev_own = prev_outs.get(node_id)
            if prev_own and getattr(prev_own, "output", ""):
                routed_messages.insert(
                    0,
                    f"[YOUR PREVIOUS ROUND OUTPUT — build on this, do NOT repeat it]:\n"
                    f"{prev_own.output[:3000]}",
                )

        # Assemble shared context
        context = self.ctx.assemble_agent_context(
            agent_id=node_id,
            caste=agent.caste.value if hasattr(agent.caste, "value") else str(agent.caste),
            token_budget=4000,
        )

        # Create workspace subdirectories for each replica (STRICTURE-002:
        # mkdir is sync I/O, offload to thread in async context)
        base_workspace = getattr(agent, "workspace_root", "./workspace")
        voting_dir = Path(base_workspace) / "_voting" / node_id

        def _create_replica_dirs() -> None:
            for i in range(num_replicas):
                (voting_dir / str(i)).mkdir(parents=True, exist_ok=True)

        await asyncio.to_thread(_create_replica_dirs)

        # Build replica coroutines
        base_seed = agent.seed or 42
        replica_coros = []
        replica_ids = []
        for i in range(num_replicas):
            replica_id = f"{node_id}_replica_{i}"
            replica_ids.append(replica_id)
            replica_workspace = str(voting_dir / str(i))

            # Clone agent config with divergent seed and isolated workspace
            replica_config = dict(agent.config)
            replica_config["seed"] = base_seed + i
            replica_config["workspace_root"] = replica_workspace

            replica_agent = Agent(
                id=replica_id,
                caste=agent.caste,
                system_prompt=agent.system_prompt,
                model_client=agent.model_client,
                model_name=agent.model_name,
                tools=list(agent.tools),
                config=replica_config,
            )

            replica_coros.append(
                self._execute_replica(
                    replica_agent, context, round_goal,
                    list(routed_messages), skill_context, callbacks,
                )
            )

        # Run all replicas in parallel with fault isolation
        results = await asyncio.gather(*replica_coros, return_exceptions=True)

        # Collect outputs, fault-isolate failures
        successful_outputs: list[tuple[str, AgentOutput]] = []
        voting_result = VotingGroupResult(node_id=node_id)

        for i, result in enumerate(results):
            replica_id = replica_ids[i]
            if isinstance(result, Exception):
                logger.warning(
                    "Voting replica '%s' failed: %s", replica_id, result,
                )
                error_output = AgentOutput(
                    output=f"ERROR: Replica {replica_id} failed: {result}",
                )
                agent_outputs[replica_id] = error_output
                voting_result.replica_outputs[replica_id] = error_output.output
            else:
                agent_outputs[replica_id] = result
                successful_outputs.append((replica_id, result))
                voting_result.replica_outputs[replica_id] = result.output

        # Inject synthetic edges from each replica to the reviewer
        reviewer_id = voting_cfg.reviewer_agent_id
        for replica_id in replica_ids:
            topology.edges.append(TopologyEdge(
                sender=replica_id,
                receiver=reviewer_id,
                weight=1.0,
            ))

        logger.info(
            "Voting group '%s': %d/%d replicas succeeded, "
            "synthetic edges injected to reviewer '%s'",
            node_id, len(successful_outputs), num_replicas, reviewer_id,
        )

        # Return node_id with the first successful output (reviewer does final pick)
        if successful_outputs:
            best_id, best_output = successful_outputs[0]
            voting_result.selected_replica = best_id
            return node_id, best_output
        else:
            return node_id, AgentOutput(
                output=f"ERROR: All {num_replicas} voting replicas failed for node '{node_id}'.",
            )

    async def _execute_replica(
        self,
        replica_agent: Agent,
        context: str,
        round_goal: str,
        routed_messages: list[str],
        skill_context: str | None,
        callbacks: dict[str, Any] | None,
    ) -> AgentOutput:
        """Execute a single voting replica with fault isolation and timeout.

        Returns AgentOutput on success, raises on failure (caught by
        asyncio.gather(return_exceptions=True) in _execute_voting_group).
        """
        try:
            output = await asyncio.wait_for(
                replica_agent.execute(
                    context=context,
                    round_goal=round_goal,
                    routed_messages=routed_messages,
                    skill_context=skill_context,
                    callbacks=self._agent_callbacks(callbacks),
                ),
                timeout=self._agent_timeout,
            )
            return output
        except asyncio.TimeoutError:
            logger.warning(
                "Voting replica '%s' timed out (timeout=%ds)",
                replica_agent.id, self._agent_timeout,
            )
            return AgentOutput(
                output=f"ERROR: Replica '{replica_agent.id}' timed out "
                       f"after {self._agent_timeout}s.",
            )

    # ------------------------------------------------------------------
    # Phase 5 -- Compression & Governance
    # ------------------------------------------------------------------

    async def _phase5_compression_governance(
        self,
        round_num: int,
        round_goal: str,
        agent_outputs: dict[str, AgentOutput],
        callbacks: dict[str, Any] | None,
    ) -> tuple[bool, str | None]:
        """
        Phase 5: Archivist summarization + TKG extraction + governance.

        Returns (should_halt, halt_reason).
        """
        output_strings = {
            aid: out.output for aid, out in agent_outputs.items()
        }

        # -- Archivist: summarize round -> episode --
        episode: Episode | None = None
        if self.archivist:
            try:
                episode = await self.archivist.summarize_round(
                    round_num, round_goal, output_strings,
                )
                await self.ctx.record_episode(episode)
            except Exception as exc:
                logger.warning("Archivist summarize_round failed: %s", exc)

        # -- Archivist: extract TKG tuples --
        tkg_tuples = []
        if self.archivist:
            try:
                tkg_tuples = await self.archivist.extract_tkg_tuples(
                    round_num, output_strings,
                )
                for t in tkg_tuples:
                    await self.ctx.record_tkg_tuple(t)
            except Exception as exc:
                logger.warning("Archivist extract_tkg_tuples failed: %s", exc)

        # -- Archivist: maybe compress epochs --
        if self.archivist:
            try:
                await self.archivist.maybe_compress_epochs(self.ctx)
            except Exception as exc:
                logger.warning("Archivist epoch compression failed: %s", exc)

        # -- Governance --
        should_halt = False
        halt_reason: str | None = None

        if self.governance:
            try:
                # Convergence check (uses summary vectors if available)
                curr_summary_vec = None
                if episode and self.embedder:
                    try:
                        vecs = self.embedder.encode(
                            [episode.summary],
                            convert_to_numpy=True,
                            normalize_embeddings=True,
                        )
                        curr_summary_vec = vecs[0]
                    except Exception:
                        pass

                decision = self.governance.enforce(
                    round_num,
                    self._prev_summary_vec,
                    curr_summary_vec,
                )

                self._prev_summary_vec = curr_summary_vec

                if decision.action == "force_halt":
                    should_halt = True
                    halt_reason = decision.reason
                    await self._record_decision(
                        round_num, DecisionType.TERMINATION,
                        f"Governance force_halt: {decision.reason}",
                        decision.recommendations,
                    )

                elif decision.action == "intervene":
                    self._pending_intervention = (
                        f"{decision.reason}\n"
                        f"Recommendations: {', '.join(decision.recommendations)}"
                    )
                    await self._record_decision(
                        round_num, DecisionType.INTERVENTION,
                        f"Governance intervene: {decision.reason}",
                        decision.recommendations,
                    )

                # Path diversity check
                tunnel_decision = self.governance.check_tunnel_vision(
                    self._round_history, round_num,
                )
                if tunnel_decision:
                    if self._pending_intervention:
                        self._pending_intervention += (
                            f"\n\nTUNNEL VISION WARNING: {tunnel_decision.reason}"
                        )
                    else:
                        self._pending_intervention = tunnel_decision.reason

            except Exception as exc:
                logger.warning("Governance check failed: %s", exc)

        return should_halt, halt_reason

    # ------------------------------------------------------------------
    # Post-colony
    # ------------------------------------------------------------------

    async def _post_colony(
        self,
        task: str,
        status: ColonyStatus,
        governance_note: str | None,
    ) -> list[str]:
        """
        Post-colony cleanup: skill distillation + storage.

        Returns list of stored skill IDs.
        """
        skill_ids: list[str] = []

        if self.archivist and self._round_history:
            try:
                # Build round summaries string
                summaries = "\n".join(
                    f"Round {rh['round']}: {rh.get('goal', 'N/A')}"
                    for rh in self._round_history
                )

                outcome = status.value
                if governance_note:
                    outcome += f" -- {governance_note}"

                skills = await self.archivist.distill_skills(
                    task, outcome, summaries,
                )

                if skills and self.skill_bank:
                    stored = self.skill_bank.store(skills)
                    skill_ids = [s.skill_id for s in skills[:stored]]
                    logger.info(
                        "Post-colony: distilled %d skills, stored %d",
                        len(skills), stored,
                    )

            except Exception as exc:
                logger.warning("Post-colony skill distillation failed: %s", exc)

        return skill_ids

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_manager(self, agents: list[Agent]) -> Agent | None:
        """Find the first agent with caste == 'manager'."""
        for agent in agents:
            caste = agent.caste
            caste_name = caste.value if hasattr(caste, "value") else str(caste).lower()
            if caste_name == "manager":
                return agent
        return None

    def _agent_callbacks(
        self,
        callbacks: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """
        Translate orchestrator-level callbacks to agent-level callbacks.
        """
        if callbacks is None:
            return None
        result: dict[str, Any] = {}
        if "on_stream_token" in callbacks:
            result["stream_callback"] = callbacks["on_stream_token"]
        if "on_tool_call" in callbacks:
            result["tool_call_callback"] = callbacks["on_tool_call"]
        if "on_approval_request" in callbacks:
            result["approval_callback"] = callbacks["on_approval_request"]
        return result if result else None

    async def _ctx_set(
        self,
        scope: str,
        key: str,
        value: Any,
    ) -> None:
        """Set a value in the context tree with timeout protection."""
        try:
            await asyncio.wait_for(
                self.ctx.set(scope, key, value),
                timeout=_CTX_LOCK_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Context tree lock timeout (%ss) for %s.%s",
                _CTX_LOCK_TIMEOUT, scope, key,
            )
        except Exception as exc:
            logger.warning(
                "Context tree set failed (%s.%s): %s", scope, key, exc,
            )

    async def _record_decision(
        self,
        round_num: int,
        decision_type: DecisionType,
        detail: str,
        recommendations: list[str] | None = None,
    ) -> None:
        """Record a governance decision in the context tree."""
        decision = Decision(
            round_num=round_num,
            decision_type=decision_type,
            detail=detail,
            recommendations=recommendations or [],
        )
        try:
            await self.ctx.record_decision(decision)
        except Exception as exc:
            logger.warning("Failed to record decision: %s", exc)

        if self.audit:
            self.audit.log_decision(
                self._session_id,
                decision_type.value,
                detail,
            )

    def _record_span(
        self,
        round_num: int,
        activity_type: str,
        start_ms: float,
        duration_ms: float,
        agent_id: str | None = None,
        agent_role: str | None = None,
        is_critical_path: bool = False,
        **metadata: Any,
    ) -> None:
        """Record a timeline span for Gantt visualization (v0.7.7)."""
        span = TimelineSpan(
            span_id=f"{self.colony_id}_r{round_num}_{activity_type}_{uuid.uuid4().hex[:6]}",
            round_num=round_num,
            agent_id=agent_id,
            agent_role=agent_role,
            activity_type=activity_type,
            start_ms=start_ms,
            duration_ms=duration_ms,
            is_critical_path=is_critical_path,
            metadata=dict(metadata),
        )
        self._timeline_spans.append(span)
