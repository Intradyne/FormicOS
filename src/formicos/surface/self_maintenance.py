"""Self-maintenance dispatch engine (Wave 35, ADR-046).

Connects proactive insights to automatic colony dispatch. Runs after
generate_briefing() in the maintenance loop. Checks insights against
workspace autonomy policy. Dispatches eligible colonies.

Also handles distillation dispatch: when co-occurrence clusters reach
density thresholds and the maintenance policy allows, spawns archivist
colonies to synthesize knowledge.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from formicos.core.types import AutonomyLevel, CasteSlot, MaintenancePolicy

if TYPE_CHECKING:
    from formicos.surface.proactive_intelligence import KnowledgeInsight, ProactiveBriefing
    from formicos.surface.projections import ProjectionStore
    from formicos.surface.runtime import Runtime

log = structlog.get_logger()


def _log_forage_dispatch_task(task: Any) -> None:
    """Error callback for background forage dispatch tasks."""
    if not task.cancelled() and task.exception() is not None:
        log.error(
            "maintenance.forage_dispatch_failed",
            error=str(task.exception()),
        )


# Per-caste cost estimates (USD per round)
_COST_PER_ROUND: dict[str, float] = {
    "researcher": 0.08,
    "archivist": 0.05,
    "coder": 0.12,
}


# ---------------------------------------------------------------------------
# Wave 70 Track 8: Blast Radius Estimator
# ---------------------------------------------------------------------------


@dataclass
class BlastRadiusEstimate:
    """Estimated scope and impact of a proposed autonomous action."""

    score: float  # 0.0 (trivial) to 1.0 (high impact)
    level: str  # "low", "medium", "high"
    factors: list[str]
    recommendation: str  # "proceed", "notify", "escalate"


def estimate_blast_radius(
    task: str,
    caste: str = "coder",
    max_rounds: int = 3,
    strategy: str = "sequential",
    workspace_id: str = "",
    projections: ProjectionStore | None = None,
) -> BlastRadiusEstimate:
    """Estimate the blast radius of a proposed autonomous dispatch.

    Uses deterministic heuristics only. No LLM calls.
    """
    score = 0.0
    factors: list[str] = []

    # Factor 1: task length as proxy for complexity
    task_len = len(task)
    if task_len > 500:
        score += 0.2
        factors.append("Long task description (complex scope)")
    elif task_len > 200:
        score += 0.1
        factors.append("Medium-length task description")

    # Factor 2: caste risk profile
    caste_risk: dict[str, float] = {
        "coder": 0.3,
        "reviewer": 0.1,
        "researcher": 0.1,
        "archivist": 0.05,
    }
    risk = caste_risk.get(caste, 0.2)
    score += risk
    if risk >= 0.3:
        factors.append(f"Caste '{caste}' can modify files")

    # Factor 3: round count as proxy for complexity
    if max_rounds > 5:
        score += 0.15
        factors.append(f"High round budget ({max_rounds} rounds)")
    elif max_rounds > 3:
        score += 0.05

    # Factor 4: strategy
    if strategy == "stigmergic":
        score += 0.1
        factors.append("Stigmergic strategy (multi-agent, harder to predict)")

    # Factor 5: keyword signals in task text
    # Keywords only carry full weight for castes that modify files (coder).
    # Read-only castes (researcher, reviewer, archivist) get reduced weight
    # because investigating a topic is not the same as changing it.
    high_risk_keywords = [
        "delete", "remove", "drop", "migrate", "refactor",
        "rename", "replace all", "database", "schema", "deploy",
        "production", "auth", "security", "permission",
    ]
    task_lower = task.lower()
    matched = [kw for kw in high_risk_keywords if kw in task_lower]
    if matched:
        # Only coders can act on these keywords; read-only castes just investigate
        kw_weight = 0.15 if caste in ("coder",) else 0.0
        score += kw_weight * min(len(matched), 3)
        factors.append(f"High-risk keywords: {', '.join(matched[:3])}")

    # Factor 6: prior outcome history for this caste/strategy
    if projections and workspace_id and hasattr(projections, "outcome_stats"):
        stats = projections.outcome_stats(workspace_id)
        for stat in stats:
            if stat["strategy"] == strategy and caste in stat.get("caste_mix", ""):
                if stat["success_rate"] < 0.5 and stat["total"] >= 3:
                    score += 0.2
                    factors.append(
                        f"Low historical success rate for {strategy}/{caste}: "
                        f"{stat['success_rate']:.0%}"
                    )
                break

    score = min(1.0, max(0.0, score))

    if score >= 0.6:
        level = "high"
        recommendation = "escalate"
    elif score >= 0.3:
        level = "medium"
        recommendation = "notify"
    else:
        level = "low"
        recommendation = "proceed"

    return BlastRadiusEstimate(
        score=round(score, 2),
        level=level,
        factors=factors,
        recommendation=recommendation,
    )


# ---------------------------------------------------------------------------
# Wave 70 Track 9: Graduated Autonomy Scoring
# ---------------------------------------------------------------------------


@dataclass
class AutonomyScore:
    """Graduated autonomy trust score from outcome history."""

    score: int  # 0-100
    grade: str  # "A", "B", "C", "D", "F"
    components: dict[str, float] = field(default_factory=lambda: {})
    recommendation: str = ""


def compute_autonomy_score(
    workspace_id: str,
    projections: ProjectionStore,
) -> AutonomyScore:
    """Compute graduated autonomy trust score from outcome history.

    Components:
    - success_rate (40%): fraction of successful colonies
    - volume (20%): log-scaled colony count (caps at 50 colonies)
    - cost_efficiency (20%): avg cost vs budget (lower is better)
    - operator_trust (20%): follow-through rate minus kill rate
    """
    outcomes = [
        o for o in projections.colony_outcomes.values()
        if o.workspace_id == workspace_id
    ]
    if not outcomes:
        return AutonomyScore(
            score=0,
            grade="F",
            components={
                "success_rate": 0.0, "volume": 0.0,
                "cost_efficiency": 0.0, "operator_trust": 0.0,
            },
            recommendation="No outcome history. Start with supervised dispatch.",
        )

    successes = sum(1 for o in outcomes if o.succeeded)
    success_rate = successes / len(outcomes)

    # Volume (log-scaled, caps at 50)
    volume = min(1.0, math.log(1 + len(outcomes)) / math.log(51))

    # Cost efficiency: avg cost relative to estimated budget
    avg_cost = sum(o.total_cost for o in outcomes) / len(outcomes)
    cost_efficiency = 1.0 / (1.0 + avg_cost * 2)

    # Operator trust: follow-through vs kills
    behavior = getattr(projections, "operator_behavior", None)
    operator_trust = 0.5  # neutral baseline
    if behavior is not None:
        total_acted = sum(behavior.suggestion_categories_acted_on.values())
        total_kills = len(behavior.kill_records)
        total_signals = total_acted + total_kills
        if total_signals > 0:
            operator_trust = total_acted / total_signals

    components = {
        "success_rate": round(success_rate, 2),
        "volume": round(volume, 2),
        "cost_efficiency": round(cost_efficiency, 2),
        "operator_trust": round(operator_trust, 2),
    }

    raw = (
        success_rate * 0.40
        + volume * 0.20
        + cost_efficiency * 0.20
        + operator_trust * 0.20
    )
    score_val = max(0, min(100, int(round(raw * 100))))

    if score_val >= 80:
        grade, recommendation = "A", (
            "Strong track record. Consider promoting to autonomous level."
        )
    elif score_val >= 65:
        grade, recommendation = "B", (
            "Good track record. Auto-notify with expanded categories "
            "is appropriate."
        )
    elif score_val >= 50:
        grade, recommendation = "C", (
            "Mixed results. Auto-notify with limited categories recommended."
        )
    elif score_val >= 35:
        grade, recommendation = "D", (
            "Below average. Suggest-only mode recommended until outcomes improve."
        )
    else:
        grade, recommendation = "F", (
            "Poor track record. Suggest-only mode recommended. Review "
            "recent colony failures."
        )

    return AutonomyScore(
        score=score_val,
        grade=grade,
        components=components,
        recommendation=recommendation,
    )


class MaintenanceDispatcher:
    """Connects proactive insights to automatic colony dispatch.

    Runs after generate_briefing() in the maintenance loop. Checks insights
    against workspace autonomy policy. Dispatches eligible colonies.
    """

    def __init__(self, runtime: Runtime) -> None:
        self._runtime = runtime
        self._daily_spend: dict[str, float] = {}  # workspace_id -> USD spent today
        self._last_reset: date | None = None
        self._estimated_costs: dict[str, float] = {}  # colony_id -> estimated cost at dispatch

    async def evaluate_and_dispatch(
        self, workspace_id: str, briefing: ProactiveBriefing,
    ) -> list[str]:
        """Check insights against autonomy policy. Dispatch eligible colonies.

        Also hands proactive forage signals to ForagerService when present.

        Returns list of spawned colony IDs.
        """
        self._reset_daily_budget_if_needed()
        policy = self._get_policy(workspace_id)

        if policy.autonomy_level == AutonomyLevel.suggest:
            # Wave 71.0: queue suggest-only insights instead of dropping
            self._queue_suggest_only(workspace_id, briefing)
            return []

        dispatched: list[str] = []
        active = self._count_active_maintenance_colonies(workspace_id)
        budget_remaining = (
            policy.daily_maintenance_budget
            - self._daily_spend.get(workspace_id, 0.0)
        )

        for insight in briefing.insights:
            # Proactive foraging path: hand forage_signal to ForagerService
            if insight.forage_signal is not None:
                await self._dispatch_forage_signal(
                    workspace_id, insight, policy,
                )

            if not insight.suggested_colony:
                continue
            if active >= policy.max_maintenance_colonies:
                break
            # Wave 60: estimated_cost is a planning estimate for API cost.
            # Local-only colonies have $0 real cost and don't decrement budget.
            cost = insight.suggested_colony.estimated_cost
            if cost > 0 and budget_remaining < cost:
                continue
            if (
                policy.autonomy_level == AutonomyLevel.auto_notify
                and insight.category not in policy.auto_actions
            ):
                # Wave 71.0: queue as self-rejected instead of dropping
                self._queue_insight(
                    workspace_id, insight,
                    reason=f"Category '{insight.category}' not in auto_actions",
                    self_rejected=True,
                )
                continue

            # Wave 70 Track 8: blast radius gate
            sc = insight.suggested_colony
            estimate = estimate_blast_radius(
                task=sc.task,
                caste=sc.caste,
                max_rounds=sc.max_rounds,
                strategy=sc.strategy,
                workspace_id=workspace_id,
                projections=self._runtime.projections,
            )
            if estimate.recommendation == "escalate":
                log.info(
                    "maintenance.blast_radius_escalation",
                    workspace_id=workspace_id,
                    category=insight.category,
                    score=estimate.score,
                    factors=estimate.factors,
                )
                # Wave 71.0: queue instead of silently dropping
                self._queue_insight(
                    workspace_id, insight,
                    blast_radius=estimate.score,
                    reason=f"Blast radius escalation (score={estimate.score:.2f})",
                )
                continue
            if (
                policy.autonomy_level == AutonomyLevel.auto_notify
                and estimate.recommendation == "notify"
            ):
                log.info(
                    "maintenance.blast_radius_notify_skip",
                    workspace_id=workspace_id,
                    category=insight.category,
                    score=estimate.score,
                )
                # Wave 71.0: queue instead of silently dropping
                self._queue_insight(
                    workspace_id, insight,
                    blast_radius=estimate.score,
                    reason=f"Blast radius notify (score={estimate.score:.2f})",
                )
                continue

            colony_id = await self._spawn_maintenance_colony(
                workspace_id, insight,
            )
            dispatched.append(colony_id)
            active += 1
            # Wave 60: only decrement daily budget for API-costing colonies
            if cost > 0:
                self._daily_spend[workspace_id] = (
                    self._daily_spend.get(workspace_id, 0.0) + cost
                )
                self._persist_daily_spend(workspace_id)
                self._estimated_costs[colony_id] = cost
                budget_remaining -= cost

        return dispatched

    # ------------------------------------------------------------------ #
    # Wave 71.0: action queue integration                                  #
    # ------------------------------------------------------------------ #

    def _get_data_dir(self) -> str:
        """Return the data directory string, or empty."""
        try:
            dd = self._runtime.settings.system.data_dir
            return str(dd) if isinstance(dd, str) and dd else ""
        except AttributeError:
            return ""

    def _queue_insight(
        self,
        workspace_id: str,
        insight: KnowledgeInsight,
        *,
        blast_radius: float = 0.0,
        reason: str = "",
        self_rejected: bool = False,
    ) -> None:
        """Queue a proactive insight as a durable action record."""
        data_dir = self._get_data_dir()
        if not data_dir:
            return
        try:
            from formicos.surface.action_queue import (  # noqa: PLC0415
                queue_from_insight,
            )

            sc = insight.suggested_colony
            sc_dict: dict[str, Any] | None = None
            if sc is not None:
                sc_dict = {
                    "caste": sc.caste,
                    "strategy": sc.strategy,
                    "max_rounds": sc.max_rounds,
                    "task": sc.task[:500],
                    "estimated_cost": sc.estimated_cost,
                }

            queue_from_insight(
                data_dir,
                workspace_id,
                insight_category=insight.category,
                insight_title=insight.title,
                insight_detail=str(insight.detail)[:500] if insight.detail else "",
                suggested_colony=sc_dict,
                blast_radius=blast_radius,
                estimated_cost=sc.estimated_cost if sc else 0.0,
                confidence=0.0,
                reason=reason,
                self_rejected=self_rejected,
            )
        except Exception:  # noqa: BLE001
            log.debug(
                "maintenance.queue_insight_failed",
                workspace_id=workspace_id,
            )

    def _queue_suggest_only(
        self,
        workspace_id: str,
        briefing: ProactiveBriefing,
    ) -> None:
        """Queue all suggest-only insights as pending_review."""
        for insight in briefing.insights:
            if insight.suggested_colony:
                self._queue_insight(
                    workspace_id, insight,
                    reason="Suggest-only autonomy level",
                )

    async def evaluate_distillation(
        self, workspace_id: str,
    ) -> list[str]:
        """Check distillation candidates and dispatch archivist colonies.

        Returns list of spawned colony IDs.
        """
        self._reset_daily_budget_if_needed()
        policy = self._get_policy(workspace_id)

        if policy.autonomy_level == AutonomyLevel.suggest:
            return []

        # Distillation requires explicit opt-in via auto_actions
        if (
            policy.autonomy_level == AutonomyLevel.auto_notify
            and "distillation" not in policy.auto_actions
        ):
            return []

        candidates = getattr(
            self._runtime.projections, "distillation_candidates", [],
        )
        if not candidates:
            return []

        dispatched: list[str] = []
        active = self._count_active_maintenance_colonies(workspace_id)
        budget_remaining = (
            policy.daily_maintenance_budget
            - self._daily_spend.get(workspace_id, 0.0)
        )

        for cluster in candidates:
            if active >= policy.max_maintenance_colonies:
                break
            estimated_cost = 3 * _COST_PER_ROUND["archivist"]  # 3 rounds
            if budget_remaining < estimated_cost:
                break

            colony_id = await self._spawn_distillation_colony(
                workspace_id, cluster,
            )
            dispatched.append(colony_id)
            active += 1
            self._daily_spend[workspace_id] = (
                self._daily_spend.get(workspace_id, 0.0) + estimated_cost
            )
            self._persist_daily_spend(workspace_id)
            if estimated_cost > 0 and colony_id:
                self._estimated_costs[colony_id] = estimated_cost
            budget_remaining -= estimated_cost

        return dispatched

    async def _dispatch_forage_signal(
        self,
        workspace_id: str,
        insight: KnowledgeInsight,
        policy: MaintenancePolicy,
    ) -> None:
        """Hand a proactive forage signal to ForagerService if policy allows.

        Forage signals piggyback on the existing auto_actions gate: the
        insight's category must be in the policy's auto_actions list for
        auto_notify level, or autonomy must be 'autonomous'.
        """
        if policy.autonomy_level == AutonomyLevel.suggest:
            return
        if (
            policy.autonomy_level == AutonomyLevel.auto_notify
            and insight.category not in policy.auto_actions
        ):
            return

        forager_svc = getattr(self._runtime, "forager_service", None)
        if forager_svc is None:
            log.debug(
                "maintenance.forage_signal_skipped",
                reason="no_forager_service",
                category=insight.category,
            )
            return

        signal: dict[str, Any] = {**insight.forage_signal}  # type: ignore[arg-type]
        signal["workspace_id"] = workspace_id

        import asyncio  # noqa: PLC0415

        task = asyncio.create_task(forager_svc.handle_forage_signal(signal))
        task.add_done_callback(_log_forage_dispatch_task)

        log.info(
            "maintenance.forage_signal_dispatched",
            workspace_id=workspace_id,
            trigger=signal.get("trigger", ""),
            category=insight.category,
        )

    # -- Internals ---------------------------------------------------------

    def _get_policy(self, workspace_id: str) -> MaintenancePolicy:
        """Retrieve maintenance policy from workspace config."""
        import json as _json

        ws = self._runtime.projections.workspaces.get(workspace_id)
        if ws is None:
            return MaintenancePolicy()
        raw = ws.config.get("maintenance_policy")
        if raw is None:
            return MaintenancePolicy()
        try:
            data = _json.loads(raw) if isinstance(raw, str) else raw
            return MaintenancePolicy(**data)
        except Exception:  # noqa: BLE001
            return MaintenancePolicy()

    def _count_active_maintenance_colonies(self, workspace_id: str) -> int:
        """Count running colonies tagged as maintenance in this workspace."""
        count = 0
        for colony in self._runtime.projections.colonies.values():
            if colony.workspace_id != workspace_id:
                continue
            if colony.status not in ("running", "pending"):
                continue
            # Check tags via colony metadata (stored on spawn)
            tags: list[str] = getattr(colony, "tags", [])
            if "maintenance" in tags:
                count += 1
        return count

    def _reset_daily_budget_if_needed(self) -> None:
        """Reset daily spend counters at midnight UTC."""
        today = datetime.now(UTC).date()
        if self._last_reset != today:
            self._daily_spend.clear()
            self._last_reset = today
            # Wave 76: reload persisted spend for current day
            try:
                for ws_id in self._runtime.projections.workspaces:
                    persisted = self._load_daily_spend(ws_id)
                    if persisted > 0:
                        self._daily_spend[ws_id] = persisted
            except (AttributeError, OSError):
                pass  # settings/data_dir not available (e.g. test mocks)

    # ------------------------------------------------------------------ #
    # Wave 76: budget reconciliation                                       #
    # ------------------------------------------------------------------ #

    def reconcile_colony_cost(
        self, workspace_id: str, colony_id: str, actual_cost: float,
    ) -> None:
        """Reconcile estimated vs actual colony cost in daily spend."""
        if colony_id not in self._estimated_costs:
            return  # only reconcile colonies that this dispatcher budgeted for
        estimated = self._estimated_costs.pop(colony_id, 0.0)
        if estimated == 0.0 and actual_cost == 0.0:
            return
        adjustment = actual_cost - estimated
        if adjustment != 0.0:
            self._daily_spend[workspace_id] = max(
                0.0,
                self._daily_spend.get(workspace_id, 0.0) + adjustment,
            )
            self._persist_daily_spend(workspace_id)

    # ------------------------------------------------------------------ #
    # Wave 76: daily spend persistence                                     #
    # ------------------------------------------------------------------ #

    def _spend_path(self, workspace_id: str) -> Path:
        data_dir = self._runtime.settings.system.data_dir
        return (
            Path(data_dir) / ".formicos" / "operations"
            / workspace_id / "daily_spend.json"
        )

    def _persist_daily_spend(self, workspace_id: str) -> None:
        """Write current daily spend to disk."""
        try:
            path = self._spend_path(workspace_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "date": str(datetime.now(UTC).date()),
                "spend": self._daily_spend.get(workspace_id, 0.0),
                "last_updated": datetime.now(UTC).isoformat(),
            }
            path.write_text(json.dumps(data, indent=2) + "\n")
        except (AttributeError, OSError):
            pass  # settings/data_dir not available

    def _load_daily_spend(self, workspace_id: str) -> float:
        """Load persisted daily spend, or 0.0 if absent or stale."""
        path = self._spend_path(workspace_id)
        if not path.exists():
            return 0.0
        try:
            data = json.loads(path.read_text())
            if data.get("date") != str(datetime.now(UTC).date()):
                return 0.0  # Stale -- different day
            return float(data.get("spend", 0.0))
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return 0.0

    async def _spawn_maintenance_colony(
        self, workspace_id: str, insight: KnowledgeInsight,
    ) -> str:
        """Spawn a colony from insight's suggested_colony."""
        sc = insight.suggested_colony
        assert sc is not None  # caller checks  # noqa: S101
        # Prefix task with maintenance context for traceability
        task = (
            f"[maintenance:{insight.category}] {sc.task}"
        )
        colony_id: str = await self._runtime.spawn_colony(
            workspace_id=workspace_id,
            thread_id="maintenance",
            task=task,
            castes=[CasteSlot(caste=sc.caste)],
            strategy=sc.strategy,
            max_rounds=sc.max_rounds,
        )
        return colony_id

    async def _spawn_distillation_colony(
        self, workspace_id: str, cluster: list[str],
    ) -> str:
        """Spawn archivist colony to synthesize a knowledge cluster."""
        entries: list[dict[str, Any]] = []
        for eid in cluster:
            e = self._runtime.projections.memory_entries.get(eid)
            if e is not None:
                entries.append(e)

        entry_summaries = "\n".join(
            f"- [{e.get('id', '')}] ({e.get('sub_type', 'unknown')}): "
            f"{e.get('title', '')}\n"
            f"  Content: {str(e.get('content', ''))[:300]}\n"
            for e in entries
        )

        task = (
            f"Synthesize these {len(cluster)} related knowledge entries into a "
            f"single comprehensive entry. Preserve all key insights. Resolve "
            f"any contradictions by noting the strongest evidence. The synthesis "
            f"should be more useful than any individual entry.\n\n{entry_summaries}"
        )

        colony_id: str = await self._runtime.spawn_colony(
            workspace_id=workspace_id,
            thread_id="maintenance",
            task=task,
            castes=[CasteSlot(caste="archivist")],
            strategy="sequential",
            max_rounds=3,
        )
        return colony_id


    async def run_proactive_dispatch(self) -> dict[str, list[str]]:
        """Generate briefings for all workspaces and dispatch eligible actions.

        Designed to be called from the scheduled maintenance loop.
        Returns {workspace_id: [colony_ids]} for any dispatched colonies.
        """
        from formicos.surface.proactive_intelligence import (  # noqa: PLC0415
            generate_briefing,
        )

        results: dict[str, list[str]] = {}
        self.last_briefing_insights: dict[str, list[dict[str, object]]] = {}
        workspace_ids = list(self._runtime.projections.workspaces.keys())
        for ws_id in workspace_ids:
            try:
                briefing = generate_briefing(ws_id, self._runtime.projections)
                self.last_briefing_insights[ws_id] = [
                    i.model_dump() if hasattr(i, "model_dump") else dict(i)
                    for i in briefing.insights
                ]
                dispatched = await self.evaluate_and_dispatch(ws_id, briefing)
                if dispatched:
                    results[ws_id] = dispatched
                    log.info(
                        "maintenance.proactive_dispatch",
                        workspace_id=ws_id,
                        dispatched_colonies=len(dispatched),
                    )
            except Exception:  # noqa: BLE001
                log.debug(
                    "maintenance.proactive_dispatch_failed",
                    workspace_id=ws_id,
                )
        return results

    # -- Wave 36 A4: scheduled refresh triggers --------------------------

    def evaluate_scheduled_triggers(
        self, workspace_id: str,
    ) -> list[KnowledgeInsight]:
        """Produce insights for approaching staleness, domain health, and
        distillation refresh. Returns insight objects compatible with the
        existing maintenance dispatch path.

        These are evaluated periodically (caller decides interval). They
        produce the same KnowledgeInsight objects the dispatcher already
        understands, so no new dispatch path is needed.
        """
        from formicos.surface.proactive_intelligence import (  # noqa: PLC0415
            KnowledgeInsight,
            SuggestedColony,
        )

        insights: list[KnowledgeInsight] = []
        entries = {
            eid: e
            for eid, e in self._runtime.projections.memory_entries.items()
            if e.get("workspace_id") == workspace_id
        }
        if not entries:
            return insights

        # --- Trigger 1: Approaching staleness ---
        # Entries with decay_class=ephemeral and alpha declining toward
        # threshold (alpha < 3 and was once > 5)
        stale_candidates: list[str] = []
        for eid, e in entries.items():
            decay_class = e.get("decay_class", "ephemeral")
            if decay_class != "ephemeral":
                continue
            alpha = float(e.get("conf_alpha", 5))
            peak = float(e.get("peak_alpha", alpha))
            if peak >= 5 and alpha < 3:
                stale_candidates.append(eid)

        if len(stale_candidates) >= 3:
            insights.append(KnowledgeInsight(
                severity="info",
                category="staleness",
                title=f"{len(stale_candidates)} entries approaching staleness",
                detail=(
                    f"{len(stale_candidates)} ephemeral entries have decayed "
                    f"below alpha=3 from peaks above 5. They may become "
                    f"unretrievable without refresh."
                ),
                affected_entries=stale_candidates[:5],
                suggested_action="Refresh or promote high-value entries.",
                suggested_colony=SuggestedColony(
                    task=(
                        f"Review {len(stale_candidates)} decaying knowledge entries. "
                        f"Validate which are still accurate and promote to stable."
                    ),
                    caste="researcher",
                    strategy="sequential",
                    max_rounds=5,
                    rationale="Ephemeral entries approaching retrieval threshold.",
                    estimated_cost=5 * _COST_PER_ROUND["researcher"],
                ),
            ))

        # --- Trigger 2: Domain health check ---
        # Domains with high error rates but no recent maintenance
        domain_errors: dict[str, int] = {}
        for e in entries.values():
            errors = int(e.get("prediction_error_count", 0))
            if errors < 2:
                continue
            for d in _safe_str_list(e.get("domains")):
                domain_errors[d] = domain_errors.get(d, 0) + errors

        for domain, total_errors in domain_errors.items():
            if total_errors >= 10:
                insights.append(KnowledgeInsight(
                    severity="attention",
                    category="coverage",
                    title=f"Domain '{domain}' needs health check",
                    detail=(
                        f"Domain '{domain}' has accumulated {total_errors} "
                        f"prediction errors. Knowledge quality is degrading."
                    ),
                    affected_entries=[],
                    suggested_action=f"Spawn a research colony to refresh '{domain}'.",
                    suggested_colony=SuggestedColony(
                        task=(
                            f"Audit and refresh knowledge in domain '{domain}'. "
                            f"High prediction error accumulation suggests stale content."
                        ),
                        caste="researcher",
                        strategy="sequential",
                        max_rounds=5,
                        rationale=f"{total_errors} accumulated prediction errors in '{domain}'.",
                        estimated_cost=5 * _COST_PER_ROUND["researcher"],
                    ),
                ))

        # --- Trigger 3: Distillation refresh ---
        # Re-check dense clusters that were distilled long ago
        candidates = getattr(
            self._runtime.projections, "distillation_candidates", [],
        )
        if len(candidates) >= 2:
            insights.append(KnowledgeInsight(
                severity="info",
                category="merge",
                title=f"{len(candidates)} clusters ready for distillation",
                detail=(
                    f"{len(candidates)} co-occurrence clusters meet the "
                    f"density threshold for synthesis. Distillation could "
                    f"consolidate these into higher-order entries."
                ),
                affected_entries=[],
                suggested_action="Enable distillation in maintenance policy.",
            ))

        return insights


def _safe_str_list(val: Any) -> list[str]:
    """Safely extract list[str] from a dict value."""
    if not isinstance(val, list):
        return []
    return [str(item) for item in val]


__all__ = [
    "AutonomyScore",
    "BlastRadiusEstimate",
    "MaintenanceDispatcher",
    "compute_autonomy_score",
    "estimate_blast_radius",
]
