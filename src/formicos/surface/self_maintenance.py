"""Self-maintenance dispatch engine (Wave 35, ADR-046).

Connects proactive insights to automatic colony dispatch. Runs after
generate_briefing() in the maintenance loop. Checks insights against
workspace autonomy policy. Dispatches eligible colonies.

Also handles distillation dispatch: when co-occurrence clusters reach
density thresholds and the maintenance policy allows, spawns archivist
colonies to synthesize knowledge.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

import structlog

from formicos.core.types import AutonomyLevel, CasteSlot, MaintenancePolicy

if TYPE_CHECKING:
    from formicos.surface.proactive_intelligence import KnowledgeInsight, ProactiveBriefing
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


class MaintenanceDispatcher:
    """Connects proactive insights to automatic colony dispatch.

    Runs after generate_briefing() in the maintenance loop. Checks insights
    against workspace autonomy policy. Dispatches eligible colonies.
    """

    def __init__(self, runtime: Runtime) -> None:
        self._runtime = runtime
        self._daily_spend: dict[str, float] = {}  # workspace_id -> USD spent today
        self._last_reset: date | None = None

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
                budget_remaining -= cost

        return dispatched

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
        workspace_ids = list(self._runtime.projections.workspaces.keys())
        for ws_id in workspace_ids:
            try:
                briefing = generate_briefing(ws_id, self._runtime.projections)
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


__all__ = ["MaintenanceDispatcher"]
