"""Operations coordinator — cross-artifact synthesis (Wave 71.0 Track 8).

Inspects project plan, thread plans, session summaries, recent colony
outcomes, and queued actions to derive:

- continuation_candidates
- sync_issues
- recent_progress
- compact counts (pending_review, stalled, active milestones)
- operator-availability signals

This is a synthesis layer, not a second source of truth.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_operations_summary(
    data_dir: str,
    workspace_id: str,
    projections: Any = None,
) -> dict[str, Any]:
    """Build a compact operational summary from all available artifacts.

    Gracefully degrades when Team A/B helpers or projections are absent.
    """
    result: dict[str, Any] = {
        "workspace_id": workspace_id,
        "pending_review_count": 0,
        "active_milestone_count": 0,
        "stalled_thread_count": 0,
        "last_operator_activity_at": None,
        "idle_for_minutes": None,
        "operator_active": False,
        "continuation_candidates": [],
        "sync_issues": [],
        "recent_progress": [],
    }

    if not data_dir:
        return result

    # -- 1. Project plan --
    _pp = _load_project_plan_safe(data_dir)
    milestones: list[dict[str, Any]] = (
        _pp.get("milestones", []) if _pp.get("exists") else []
    )
    result["active_milestone_count"] = sum(
        1 for m in milestones if m.get("status") != "completed"
    )

    # -- 2. Thread plans --
    thread_plans = _load_thread_plans_safe(data_dir)

    # -- 3. Session summaries --
    sessions = _load_session_summaries_safe(data_dir)

    # -- 4. Action queue --
    actions = _load_actions_safe(data_dir, workspace_id)
    result["pending_review_count"] = sum(
        1 for a in actions if a.get("status") == "pending_review"
    )

    # -- 5. Operator activity --
    result.update(_compute_operator_activity(projections, workspace_id))

    # -- 6. Derive continuation candidates --
    result["continuation_candidates"] = _find_continuation_candidates(
        thread_plans, sessions, projections, workspace_id,
    )

    # -- 7. Derive sync issues --
    result["sync_issues"] = _find_sync_issues(
        milestones, thread_plans, actions,
    )

    # -- 8. Recent progress --
    result["recent_progress"] = _collect_recent_progress(
        thread_plans, milestones,
    )

    # -- 9. Stalled threads --
    result["stalled_thread_count"] = _count_stalled_threads(
        thread_plans, projections, workspace_id,
    )

    return result


def render_continuity_block(summary: dict[str, Any]) -> str:
    """Render the operational summary into compact text for Queen injection.

    Returns an empty string if there is nothing useful to report.
    """
    parts: list[str] = []

    # Counts header
    pending = summary.get("pending_review_count", 0)
    active_ms = summary.get("active_milestone_count", 0)
    stalled = summary.get("stalled_thread_count", 0)
    idle_min = summary.get("idle_for_minutes")

    counts: list[str] = []
    if pending:
        counts.append(f"{pending} pending review")
    if active_ms:
        counts.append(f"{active_ms} active milestones")
    if stalled:
        counts.append(f"{stalled} stalled threads")
    if idle_min is not None:
        counts.append(f"operator idle {idle_min}m")

    if counts:
        parts.append("# Operational Loop Summary")
        parts.append("Status: " + ", ".join(counts))

    # Continuation candidates
    candidates = summary.get("continuation_candidates", [])
    if candidates:
        parts.append("Continuations:")
        for c in candidates[:3]:
            ready = c.get("ready_for_autonomy", False)
            reason = c.get("blocked_reason", "")
            tag = "READY" if ready else f"BLOCKED: {reason}" if reason else "review"
            parts.append(f"  - [{tag}] {c.get('description', '?')}")

    # Sync issues
    issues = summary.get("sync_issues", [])
    if issues:
        parts.append("Sync issues:")
        for issue in issues[:3]:
            parts.append(f"  - {issue.get('description', '?')}")

    # Recent progress
    progress = summary.get("recent_progress", [])
    if progress:
        parts.append("Recent:")
        for p in progress[:3]:
            parts.append(f"  - {p.get('description', '?')}")

    if len(parts) <= 1:
        return ""

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Internal helpers — each loads one artifact safely
# ---------------------------------------------------------------------------


def _load_project_plan_safe(data_dir: str) -> dict[str, Any]:
    try:
        from formicos.surface.project_plan import load_project_plan  # noqa: PLC0415

        return load_project_plan(data_dir)
    except (ImportError, OSError, TypeError):
        return {"exists": False}


def _load_thread_plans_safe(data_dir: str) -> list[dict[str, Any]]:
    try:
        from formicos.surface.thread_plan import load_all_thread_plans  # noqa: PLC0415

        return load_all_thread_plans(data_dir)
    except (ImportError, OSError, TypeError):
        return []


def _load_session_summaries_safe(data_dir: str) -> dict[str, str]:
    """Return {thread_id: summary_text} for all session files."""
    sessions: dict[str, str] = {}
    sessions_dir = Path(data_dir) / ".formicos" / "sessions"
    if not sessions_dir.is_dir():
        return sessions

    try:
        for sf in sessions_dir.glob("*.md"):
            text = sf.read_text(encoding="utf-8")[:2000]
            sessions[sf.stem] = text
    except OSError:
        pass

    return sessions


def _load_actions_safe(
    data_dir: str, workspace_id: str,
) -> list[dict[str, Any]]:
    try:
        from formicos.surface.action_queue import read_actions  # noqa: PLC0415

        return read_actions(data_dir, workspace_id)
    except (ImportError, OSError, TypeError):
        return []


def _compute_operator_activity(
    projections: Any,
    workspace_id: str,
) -> dict[str, Any]:
    """Derive operator idle/active signal from projections."""
    result: dict[str, Any] = {
        "last_operator_activity_at": None,
        "idle_for_minutes": None,
        "operator_active": False,
    }

    if projections is None:
        return result

    ws = None
    if hasattr(projections, "workspaces"):
        ws = projections.workspaces.get(workspace_id)
    if ws is None:
        return result

    # Scan colonies for the most recent operator chat message
    latest_ts: str = ""
    colonies: list[Any] = []
    if hasattr(projections, "list_colonies"):
        colonies = projections.list_colonies(workspace_id)
    for colony_proj in colonies:
        if not hasattr(colony_proj, "chat_messages"):
            continue
        for msg in colony_proj.chat_messages:
            sender = getattr(msg, "sender", "")
            ts = getattr(msg, "timestamp", "")
            if sender == "operator" and ts > latest_ts:
                latest_ts = ts

    if latest_ts:
        result["last_operator_activity_at"] = latest_ts
        try:
            last_dt = datetime.fromisoformat(latest_ts.replace("Z", "+00:00"))
            now = datetime.now(UTC)
            delta = now - last_dt
            idle_minutes = int(delta.total_seconds() / 60)
            result["idle_for_minutes"] = max(0, idle_minutes)
            result["operator_active"] = idle_minutes < 15
        except (ValueError, TypeError):
            pass

    return result


# ---------------------------------------------------------------------------
# Synthesis — continuation candidates
# ---------------------------------------------------------------------------


def _find_continuation_candidates(
    thread_plans: list[dict[str, Any]],
    sessions: dict[str, str],
    projections: Any,
    workspace_id: str,
) -> list[dict[str, Any]]:
    """Identify threads that could be continued."""
    candidates: list[dict[str, Any]] = []

    for plan in thread_plans:
        summary = plan.get("summary", {})
        total = summary.get("total", 0)
        completed = summary.get("completed", 0)
        failed = summary.get("failed", 0)
        pending = summary.get("pending", 0)
        tid = plan.get("thread_id", "")

        if pending == 0:
            continue  # Fully complete or empty

        # Check for active colonies on this thread
        has_active_colony = _thread_has_active_colony(
            projections, workspace_id, tid,
        )

        # Has a session summary? (indicates prior work)
        has_session = tid in sessions

        # Check for failures
        if failed > 0:
            candidates.append({
                "thread_id": tid,
                "description": f"Thread {tid[:12]} has {failed} failed step(s), "
                               f"{pending} pending",
                "ready_for_autonomy": False,
                "blocked_reason": "prior failures need review",
                "priority": "medium",
            })
        elif not has_active_colony and has_session and pending > 0:
            candidates.append({
                "thread_id": tid,
                "description": f"Thread {tid[:12]}: {completed}/{total} steps done, "
                               f"no active colony",
                "ready_for_autonomy": True,
                "blocked_reason": "",
                "priority": "high",
            })
        elif not has_active_colony and pending > 0:
            candidates.append({
                "thread_id": tid,
                "description": f"Thread {tid[:12]}: {pending} pending steps, "
                               f"no active colony, no prior session",
                "ready_for_autonomy": False,
                "blocked_reason": "no prior session context",
                "priority": "low",
            })

    return sorted(candidates, key=lambda c: {"high": 0, "medium": 1, "low": 2}.get(
        c.get("priority", "low"), 3,
    ))


def _thread_has_active_colony(
    projections: Any,
    workspace_id: str,
    thread_id: str,
) -> bool:
    """Check if a thread currently has an active (running) colony."""
    if projections is None or not hasattr(projections, "list_colonies"):
        return False

    try:
        colonies = projections.list_colonies(workspace_id)
        for colony in colonies:
            cid = getattr(colony, "thread_id", "")
            status = getattr(colony, "status", "")
            if cid == thread_id and status in ("running", "spawning"):
                return True
    except (AttributeError, TypeError):
        pass

    return False


# ---------------------------------------------------------------------------
# Synthesis — sync issues
# ---------------------------------------------------------------------------


def _find_sync_issues(
    milestones: list[dict[str, Any]],
    thread_plans: list[dict[str, Any]],
    actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Identify cross-artifact sync problems."""
    issues: list[dict[str, Any]] = []

    # Build thread_id → plan lookup
    plan_by_thread: dict[str, dict[str, Any]] = {}
    for plan in thread_plans:
        tid = plan.get("thread_id", "")
        if tid:
            plan_by_thread[tid] = plan

    # Check: milestone still pending but thread plan fully complete
    for ms in milestones:
        if ms.get("status") == "completed":
            continue
        tid = ms.get("thread_id", "")
        if tid and tid in plan_by_thread:
            plan = plan_by_thread[tid]
            summary = plan.get("summary", {})
            if summary.get("total", 0) > 0 and summary.get("pending", 0) == 0:
                issues.append({
                    "type": "milestone_plan_mismatch",
                    "description": (
                        f"Milestone '{ms.get('description', '?')[:50]}' is pending "
                        f"but thread {tid[:12]} plan is fully complete"
                    ),
                })

    # Check: pending actions with no clear milestone owner
    pending_actions = [a for a in actions if a.get("status") == "pending_review"]
    if len(pending_actions) > 3:
        active_tids = {ms.get("thread_id") for ms in milestones
                       if ms.get("status") != "completed" and ms.get("thread_id")}
        orphan_actions = [
            a for a in pending_actions
            if a.get("thread_id") and a["thread_id"] not in active_tids
        ]
        if orphan_actions:
            issues.append({
                "type": "orphan_actions",
                "description": (
                    f"{len(orphan_actions)} pending action(s) reference "
                    f"threads with no active milestone"
                ),
            })

    return issues


# ---------------------------------------------------------------------------
# Synthesis — recent progress
# ---------------------------------------------------------------------------


def _collect_recent_progress(
    thread_plans: list[dict[str, Any]],
    milestones: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collect recently completed steps and milestones."""
    progress: list[dict[str, Any]] = []

    # Recently completed milestones
    for ms in milestones:
        if ms.get("status") == "completed":
            progress.append({
                "type": "milestone_completed",
                "description": f"Milestone completed: {ms.get('description', '?')[:60]}",
            })

    # Completed steps from thread plans
    for plan in thread_plans:
        tid = plan.get("thread_id", "")
        summary = plan.get("summary", {})
        completed = summary.get("completed", 0)
        total = summary.get("total", 0)
        if completed > 0:
            progress.append({
                "type": "thread_progress",
                "description": f"Thread {tid[:12]}: {completed}/{total} steps completed",
            })

    return progress[:5]


# ---------------------------------------------------------------------------
# Stalled thread count
# ---------------------------------------------------------------------------


def _count_stalled_threads(
    thread_plans: list[dict[str, Any]],
    projections: Any,
    workspace_id: str,
) -> int:
    """Count threads with pending work but no active colony."""
    stalled = 0
    for plan in thread_plans:
        summary = plan.get("summary", {})
        if summary.get("pending", 0) == 0:
            continue
        tid = plan.get("thread_id", "")
        if not _thread_has_active_colony(projections, workspace_id, tid):
            stalled += 1
    return stalled
