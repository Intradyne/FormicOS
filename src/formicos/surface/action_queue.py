"""Durable action queue ledger (Wave 71.0 Track 4).

Canonical operational inbox for proposed, approved, rejected, and executed
actions. Backed by workspace-scoped JSONL files:
``.formicos/operations/{workspace_id}/actions.jsonl``

The queue is generic — ``kind`` is the semantic authority for routing and UI.
Future action kinds (continuation, knowledge-review, workflow-template) slot
in without schema changes.
"""

from __future__ import annotations

import gzip
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

STATUS_PENDING_REVIEW = "pending_review"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_EXECUTED = "executed"
STATUS_SELF_REJECTED = "self_rejected"
STATUS_FAILED = "failed"

_VALID_STATUSES = {
    STATUS_PENDING_REVIEW,
    STATUS_APPROVED,
    STATUS_REJECTED,
    STATUS_EXECUTED,
    STATUS_SELF_REJECTED,
    STATUS_FAILED,
}

# Wave 76: valid state transitions — terminal states have no outgoing edges
_VALID_TRANSITIONS: dict[str, set[str]] = {
    STATUS_PENDING_REVIEW: {STATUS_APPROVED, STATUS_REJECTED, STATUS_SELF_REJECTED},
    STATUS_APPROVED: {STATUS_EXECUTED, STATUS_FAILED},
    STATUS_REJECTED: set(),
    STATUS_EXECUTED: set(),
    STATUS_SELF_REJECTED: set(),
    STATUS_FAILED: {STATUS_PENDING_REVIEW},  # allow retry
}

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_COMPACT_THRESHOLD = 1000
_COMPACT_KEEP = 500


def _actions_dir(data_dir: str, workspace_id: str) -> Path:
    return Path(data_dir) / ".formicos" / "operations" / workspace_id


def _actions_path(data_dir: str, workspace_id: str) -> Path:
    return _actions_dir(data_dir, workspace_id) / "actions.jsonl"


# ---------------------------------------------------------------------------
# Action record creation
# ---------------------------------------------------------------------------


def new_action_id() -> str:
    return f"act-{uuid.uuid4().hex[:12]}"


def create_action(  # noqa: PLR0913
    *,
    kind: str,
    title: str,
    detail: str = "",
    source_category: str = "",
    source_ref: str = "",
    rationale: str = "",
    payload: dict[str, Any] | None = None,
    thread_id: str = "",
    estimated_cost: float = 0.0,
    blast_radius: float = 0.0,
    confidence: float = 0.0,
    requires_approval: bool = True,
    created_by: str = "system",
) -> dict[str, Any]:
    """Build a new action record dict (not yet persisted)."""
    now = datetime.now(UTC).isoformat()
    return {
        "action_id": new_action_id(),
        "created_at": now,
        "updated_at": now,
        "created_by": created_by,
        "status": STATUS_PENDING_REVIEW,
        "kind": kind,
        "source_category": source_category,
        "source_ref": source_ref,
        "title": title,
        "detail": detail,
        "rationale": rationale,
        "payload": payload or {},
        "thread_id": thread_id,
        "estimated_cost": estimated_cost,
        "blast_radius": blast_radius,
        "confidence": confidence,
        "requires_approval": requires_approval,
        "approval_request_id": "",
        "executed_at": "",
        "operator_reason": "",
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def append_action(
    data_dir: str,
    workspace_id: str,
    action: dict[str, Any],
) -> None:
    """Append a single action record to the JSONL ledger."""
    path = _actions_path(data_dir, workspace_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(action, default=str) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_actions(
    data_dir: str,
    workspace_id: str,
) -> list[dict[str, Any]]:
    """Read all action records from the JSONL ledger."""
    path = _actions_path(data_dir, workspace_id)
    if not path.is_file():
        return []
    actions: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            actions.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return actions


def update_action(
    data_dir: str,
    workspace_id: str,
    action_id: str,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    """Update an action record in-place. Returns the updated record or None."""
    actions = read_actions(data_dir, workspace_id)
    target: dict[str, Any] | None = None

    for act in actions:
        if act.get("action_id") == action_id:
            # Wave 76: validate state transitions
            new_status = updates.get("status")
            if new_status is not None:
                old_status = act.get("status", "")
                allowed = _VALID_TRANSITIONS.get(old_status, set())
                if new_status not in allowed:
                    log.warning(
                        "action_queue.invalid_transition",
                        action_id=action_id,
                        old_status=old_status,
                        new_status=new_status,
                    )
                    raise ValueError(f"invalid transition: {old_status} -> {new_status}")
            act.update(updates)
            act["updated_at"] = datetime.now(UTC).isoformat()
            target = act
            break

    if target is None:
        return None

    _rewrite_actions(data_dir, workspace_id, actions)
    return target


def _rewrite_actions(
    data_dir: str,
    workspace_id: str,
    actions: list[dict[str, Any]],
) -> None:
    """Rewrite the entire JSONL file atomically."""
    path = _actions_path(data_dir, workspace_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for act in actions:
            f.write(json.dumps(act, default=str) + "\n")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Filtering + aggregation
# ---------------------------------------------------------------------------


def list_actions(
    data_dir: str,
    workspace_id: str,
    *,
    status: str = "",
    kind: str = "",
    limit: int = 100,
) -> dict[str, Any]:
    """List actions with optional filtering and aggregation.

    Returns::

        {
            "actions": [...],
            "total": N,
            "counts_by_status": {...},
            "counts_by_kind": {...},
        }
    """
    all_actions = read_actions(data_dir, workspace_id)

    # Aggregate counts over the full set
    counts_by_status: dict[str, int] = {}
    counts_by_kind: dict[str, int] = {}
    for act in all_actions:
        s = act.get("status", "")
        k = act.get("kind", "")
        counts_by_status[s] = counts_by_status.get(s, 0) + 1
        counts_by_kind[k] = counts_by_kind.get(k, 0) + 1

    # Filter
    filtered = all_actions
    if status:
        filtered = [a for a in filtered if a.get("status") == status]
    if kind:
        filtered = [a for a in filtered if a.get("kind") == kind]

    # Most recent first
    filtered.sort(key=lambda a: a.get("created_at", ""), reverse=True)

    return {
        "actions": filtered[:limit],
        "total": len(filtered),
        "counts_by_status": counts_by_status,
        "counts_by_kind": counts_by_kind,
    }


# ---------------------------------------------------------------------------
# Compaction — prevents unbounded growth
# ---------------------------------------------------------------------------


def compact_action_log(data_dir: str, workspace_id: str) -> bool:
    """Archive old entries when the JSONL exceeds the threshold.

    When the file has > ``_COMPACT_THRESHOLD`` lines, archive older entries
    to ``actions.{date}.jsonl.gz`` and keep only the last
    ``_COMPACT_KEEP`` entries in the active file.

    Returns True if compaction was performed.
    """
    path = _actions_path(data_dir, workspace_id)
    if not path.is_file():
        return False

    actions = read_actions(data_dir, workspace_id)
    if len(actions) <= _COMPACT_THRESHOLD:
        return False

    # Wave 76: partition by status — never archive pending_review items
    pending = [a for a in actions if a.get("status") == STATUS_PENDING_REVIEW]
    settled = [a for a in actions if a.get("status") != STATUS_PENDING_REVIEW]

    if len(settled) <= _COMPACT_KEEP:
        return False  # Not enough settled items to compact

    archive_entries = settled[:-_COMPACT_KEEP]
    keep_entries = pending + settled[-_COMPACT_KEEP:]

    date_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    archive_path = _actions_dir(data_dir, workspace_id) / f"actions.{date_str}.jsonl.gz"

    with gzip.open(archive_path, "wt", encoding="utf-8") as gz:
        for act in archive_entries:
            gz.write(json.dumps(act, default=str) + "\n")

    _rewrite_actions(data_dir, workspace_id, keep_entries)

    log.info(
        "action_queue.compacted",
        workspace_id=workspace_id,
        archived=len(archive_entries),
        kept=len(keep_entries),
    )
    return True


# ---------------------------------------------------------------------------
# Convenience: queue from proactive insight
# ---------------------------------------------------------------------------


def queue_from_insight(
    data_dir: str,
    workspace_id: str,
    *,
    insight_category: str,
    insight_title: str,
    insight_detail: str = "",
    suggested_colony: dict[str, Any] | None = None,
    blast_radius: float = 0.0,
    estimated_cost: float = 0.0,
    confidence: float = 0.0,
    reason: str = "",
    self_rejected: bool = False,
) -> dict[str, Any]:
    """Create and persist an action from a proactive intelligence insight."""
    action = create_action(
        kind="maintenance",
        title=insight_title,
        detail=insight_detail,
        source_category=insight_category,
        rationale=reason,
        payload={"suggested_colony": suggested_colony} if suggested_colony else {},
        estimated_cost=estimated_cost,
        blast_radius=blast_radius,
        confidence=confidence,
        requires_approval=not self_rejected,
        created_by="proactive_intelligence",
    )
    if self_rejected:
        action["status"] = STATUS_SELF_REJECTED
        action["operator_reason"] = reason
    append_action(data_dir, workspace_id, action)
    return action
