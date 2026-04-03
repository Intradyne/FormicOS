"""Autonomous continuation engine (Wave 72 Track 5 + 7).

Queues continuation proposals from stalled/idle threads and executes
low-risk continuations during operator idle time.  All actions flow
through the existing action queue and ``approve_action()`` contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from formicos.surface.action_queue import (
    STATUS_APPROVED,
    STATUS_EXECUTED,
    STATUS_FAILED,
    STATUS_PENDING_REVIEW,
    append_action,
    create_action,
    read_actions,
    update_action,
)
from formicos.surface.operational_state import append_journal_entry
from formicos.surface.operations_coordinator import build_operations_summary
from formicos.surface.self_maintenance import estimate_blast_radius

if TYPE_CHECKING:
    from formicos.surface.projections import ProjectionStore
    from formicos.surface.self_maintenance import MaintenanceDispatcher

log = structlog.get_logger()

# Default idle threshold (minutes) before autonomous continuation kicks in.
_DEFAULT_IDLE_THRESHOLD_MINUTES = 60


# ---------------------------------------------------------------------------
# Track 5: Continuation Proposals
# ---------------------------------------------------------------------------


async def queue_continuation_proposals(
    data_dir: str,
    workspace_id: str,
    projections: ProjectionStore,
    dispatcher: MaintenanceDispatcher,
) -> int:
    """Queue continuation actions for work that is ready to resume.

    Returns the number of newly queued proposals.
    """
    if not data_dir:
        return 0

    summary = build_operations_summary(data_dir, workspace_id, projections)

    # Guard 1: operator recently active — do not queue
    if summary.get("operator_active", False):
        return 0

    candidates = summary.get("continuation_candidates", [])
    if not candidates:
        return 0

    # Dedupe: read existing pending continuation actions by thread_id
    # Wave 75 audit fix: also count failed attempts to prevent infinite re-proposal
    existing_actions = read_actions(data_dir, workspace_id)
    pending_thread_ids: set[str] = set()
    failed_counts: dict[str, int] = {}
    for act in existing_actions:
        if act.get("kind") != "continuation":
            continue
        tid = act.get("thread_id") or act.get("payload", {}).get("thread_id", "")
        if not tid:
            continue
        if act.get("status") == STATUS_PENDING_REVIEW:
            pending_thread_ids.add(tid)
        elif act.get("status") == STATUS_FAILED:
            failed_counts[tid] = failed_counts.get(tid, 0) + 1

    queued = 0
    for candidate in candidates:
        thread_id = candidate.get("thread_id", "")
        if not thread_id:
            continue
        if thread_id in pending_thread_ids:
            continue
        # Wave 75 audit fix: stop re-proposing after 3 failures
        if failed_counts.get(thread_id, 0) >= 3:
            continue

        description = candidate.get("description", "Continue stalled work")
        priority = candidate.get("priority", "medium")

        # Estimate blast radius
        blast = estimate_blast_radius(
            task=description,
            caste="coder",
            max_rounds=3,
            strategy="sequential",
            workspace_id=workspace_id,
            projections=projections,
        )

        action = create_action(
            kind="continuation",
            title=f"Continue: {description[:80]}",
            detail=description,
            source_category="continuation",
            source_ref=thread_id,
            rationale=f"Thread has pending work (priority={priority})",
            payload={
                "thread_id": thread_id,
                "description": description,
                "priority": priority,
                "blast_radius_score": blast.score,
                "blast_radius_level": blast.level,
                "suggested_colony": {
                    "task": description,
                    "caste": "coder",
                    "strategy": "sequential",
                    "max_rounds": 3,
                },
            },
            thread_id=thread_id,
            estimated_cost=0.12 * 3,  # coder cost * rounds
            blast_radius=blast.score,
            confidence=1.0 if candidate.get("ready_for_autonomy") else 0.5,
            requires_approval=True,
            created_by="continuation_engine",
        )
        append_action(data_dir, workspace_id, action)
        pending_thread_ids.add(thread_id)
        queued += 1

        log.info(
            "continuation.proposal_queued",
            workspace_id=workspace_id,
            thread_id=thread_id,
            blast_radius=blast.score,
            priority=priority,
        )

    return queued


# ---------------------------------------------------------------------------
# Track 7: Idle-Time Execution
# ---------------------------------------------------------------------------


def _get_idle_threshold(dispatcher: MaintenanceDispatcher, workspace_id: str) -> int:
    """Read idle threshold from maintenance policy, with fallback."""
    try:
        policy = dispatcher._get_policy(workspace_id)  # pyright: ignore[reportPrivateUsage]
        raw = getattr(policy, "idle_threshold_minutes", None)
        if isinstance(raw, (int, float)) and raw > 0:
            return int(raw)
    except Exception:  # noqa: BLE001
        pass
    return _DEFAULT_IDLE_THRESHOLD_MINUTES


def _check_daily_budget(
    dispatcher: MaintenanceDispatcher,
    workspace_id: str,
    estimated_cost: float,
) -> bool:
    """Return True if the daily budget has capacity for estimated_cost."""
    try:
        policy = dispatcher._get_policy(workspace_id)  # pyright: ignore[reportPrivateUsage]
        spent = dispatcher._daily_spend.get(workspace_id, 0.0)  # pyright: ignore[reportPrivateUsage]
        return (policy.daily_maintenance_budget - spent) >= estimated_cost
    except Exception:  # noqa: BLE001
        return False


async def execute_idle_continuations(
    data_dir: str,
    workspace_id: str,
    projections: ProjectionStore,
    dispatcher: MaintenanceDispatcher,
    *,
    max_per_sweep: int = 1,
) -> int:
    """Execute low-risk continuation actions during operator idle time.

    Returns the number of continuations executed.
    """
    if not data_dir:
        return 0

    # Guard 1: workspace autonomy level must be 'autonomous'
    try:
        policy = dispatcher._get_policy(workspace_id)  # pyright: ignore[reportPrivateUsage]
    except Exception:  # noqa: BLE001
        return 0

    from formicos.core.types import AutonomyLevel  # noqa: PLC0415

    if policy.autonomy_level != AutonomyLevel.autonomous:
        return 0

    # Guard 2: operator idle time exceeds threshold
    summary = build_operations_summary(data_dir, workspace_id, projections)
    idle_minutes = summary.get("idle_for_minutes")
    threshold = _get_idle_threshold(dispatcher, workspace_id)
    if idle_minutes is None or idle_minutes < threshold:
        return 0

    # Guard 3: no pending-review actions of any kind
    actions = read_actions(data_dir, workspace_id)
    if any(a.get("status") == STATUS_PENDING_REVIEW for a in actions):
        return 0

    # Find approved continuation actions ready for execution
    approved_continuations = [
        a for a in actions
        if a.get("kind") == "continuation"
        and a.get("status") == STATUS_APPROVED
    ]
    if not approved_continuations:
        return 0

    executed = 0
    for act in approved_continuations[:max_per_sweep]:
        # Guard 4: re-check blast radius at execution time
        sc = act.get("payload", {}).get("suggested_colony", {})
        blast = estimate_blast_radius(
            task=sc.get("task", act.get("title", "")),
            caste=sc.get("caste", "coder"),
            max_rounds=sc.get("max_rounds", 3),
            strategy=sc.get("strategy", "sequential"),
            workspace_id=workspace_id,
            projections=projections,
        )
        if blast.score >= 0.6:
            log.info(
                "continuation.idle_execution_skipped",
                workspace_id=workspace_id,
                action_id=act["action_id"],
                reason="blast_radius_too_high",
                score=blast.score,
            )
            continue

        # Guard 5: daily budget check
        estimated_cost = act.get("estimated_cost", 0.36)
        if not _check_daily_budget(dispatcher, workspace_id, estimated_cost):
            log.info(
                "continuation.idle_execution_skipped",
                workspace_id=workspace_id,
                action_id=act["action_id"],
                reason="budget_exhausted",
            )
            break

        # Execute via runtime.spawn_colony
        try:
            from datetime import UTC, datetime  # noqa: PLC0415

            from formicos.core.types import CasteSlot  # noqa: PLC0415

            runtime = dispatcher._runtime  # pyright: ignore[reportPrivateUsage]
            colony_id: str = await runtime.spawn_colony(
                workspace_id=workspace_id,
                thread_id=act.get("thread_id") or "maintenance",
                task=sc.get("task", act.get("title", "")),
                castes=[CasteSlot(caste=sc.get("caste", "coder"))],
                strategy=sc.get("strategy", "sequential"),
                max_rounds=sc.get("max_rounds", 3),
            )

            update_action(
                data_dir, workspace_id, act["action_id"],
                {"status": STATUS_EXECUTED, "executed_at": datetime.now(UTC).isoformat()},
            )

            # Increment daily spend
            dispatcher._daily_spend[workspace_id] = (  # pyright: ignore[reportPrivateUsage]
                dispatcher._daily_spend.get(workspace_id, 0.0) + estimated_cost  # pyright: ignore[reportPrivateUsage]
            )
            dispatcher._persist_daily_spend(workspace_id)  # pyright: ignore[reportPrivateUsage]
            if estimated_cost > 0 and colony_id:
                dispatcher._estimated_costs[colony_id] = estimated_cost  # pyright: ignore[reportPrivateUsage]

            # Journal the autonomous continuation
            import contextlib  # noqa: PLC0415

            with contextlib.suppress(Exception):
                append_journal_entry(
                    data_dir, workspace_id,
                    source="continuation",
                    message=(
                        f"Auto-executed continuation: {act.get('title', '?')[:60]} "
                        f"(colony={colony_id[:12]}, blast={blast.score:.2f})"
                    ),
                )

            executed += 1
            log.info(
                "continuation.idle_execution_completed",
                workspace_id=workspace_id,
                action_id=act["action_id"],
                colony_id=colony_id,
                blast_radius=blast.score,
            )

        except Exception:  # noqa: BLE001
            update_action(
                data_dir, workspace_id, act["action_id"],
                {"status": STATUS_FAILED},
            )
            log.debug(
                "continuation.idle_execution_failed",
                workspace_id=workspace_id,
                action_id=act["action_id"],
            )

    return executed


# ---------------------------------------------------------------------------
# Track 7: Warm-start cue builder
# ---------------------------------------------------------------------------


def build_warm_start_cue(
    data_dir: str,
    workspace_id: str,
    projections: ProjectionStore,
    *,
    max_candidates: int = 3,
) -> str:
    """Build a continuation cue for the Queen's first returning-session turn.

    Returns empty string if there are no actionable candidates.
    """
    if not data_dir:
        return ""

    summary = build_operations_summary(data_dir, workspace_id, projections)
    candidates = summary.get("continuation_candidates", [])
    if not candidates:
        return ""

    lines: list[str] = ["# Continuation Opportunities"]
    lines.append(
        "The following threads have pending work and no active colony. "
        "Confirm which to resume, or redirect."
    )
    lines.append("")

    for c in candidates[:max_candidates]:
        ready = c.get("ready_for_autonomy", False)
        blocked = c.get("blocked_reason", "")
        priority = c.get("priority", "medium")
        tag = "READY" if ready else f"BLOCKED: {blocked}" if blocked else "review"
        lines.append(f"- [{tag}] (priority={priority}) {c.get('description', '?')}")

    remaining = len(candidates) - max_candidates
    if remaining > 0:
        lines.append(f"  (+{remaining} more)")

    return "\n".join(lines)
