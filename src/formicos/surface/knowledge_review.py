"""Knowledge review scanner (Wave 72 Track 1).

Pure scan function that queues ``kind="knowledge_review"`` actions for entries
that need human attention. Runs from the operational sweep loop; does not mutate
knowledge directly.

Four review criteria:
  1. Outcome-correlated failures — entry accessed by 3+ colonies, >50% failed
  2. Contradictions — reuses already-generated briefing insights
  3. Stale authority — high-confidence old entries (not permanent)
  4. Unconfirmed machine-generated — influential entries with no operator confirmation
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

from formicos.surface.action_queue import (
    STATUS_PENDING_REVIEW,
    append_action,
    create_action,
    read_actions,
)

if TYPE_CHECKING:
    from formicos.surface.projections import ProjectionStore

log = structlog.get_logger()

# Thresholds
_MIN_COLONY_ACCESS = 3
_FAILURE_RATE_THRESHOLD = 0.5
_HIGH_CONFIDENCE_THRESHOLD = 0.75
_STALE_DAYS = 90
_MIN_ACCESS_FOR_INFLUENTIAL = 5


def _content_preview(entry: dict[str, Any], max_len: int = 120) -> str:
    content = entry.get("content", "")
    if len(content) > max_len:
        return content[:max_len] + "..."
    return content


def _entry_confidence(entry: dict[str, Any]) -> float:
    alpha = float(entry.get("conf_alpha", 5.0))
    beta = float(entry.get("conf_beta", 5.0))
    return alpha / (alpha + beta) if (alpha + beta) > 0 else 0.5


def _existing_pending_entry_ids(
    data_dir: str,
    workspace_id: str,
) -> set[str]:
    """Return entry_ids that already have a pending knowledge_review action."""
    actions = read_actions(data_dir, workspace_id)
    ids: set[str] = set()
    for act in actions:
        if (
            act.get("kind") == "knowledge_review"
            and act.get("status") == STATUS_PENDING_REVIEW
        ):
            eid = act.get("payload", {}).get("entry_id", "")
            if eid:
                ids.add(eid)
    return ids


async def scan_knowledge_for_review(
    data_dir: str,
    workspace_id: str,
    projections: ProjectionStore,
    *,
    briefing_insights: list[dict[str, object]] | None = None,
) -> int:
    """Queue review actions for entries that need human attention.

    Returns the number of actions queued.
    """
    existing = _existing_pending_entry_ids(data_dir, workspace_id)
    queued = 0

    # Build workspace entry set
    entries = {
        eid: e
        for eid, e in projections.memory_entries.items()
        if e.get("workspace_id") == workspace_id
    }

    # Build per-entry outcome stats from colony outcomes
    entry_colony_results: dict[str, dict[str, int]] = {}  # entry_id -> {ok, fail}
    for outcome in projections.colony_outcomes.values():
        if outcome.workspace_id != workspace_id:
            continue
        accessed = _get_accessed_entries(outcome.colony_id, projections)
        for eid in accessed:
            stats = entry_colony_results.setdefault(eid, {"ok": 0, "fail": 0})
            if outcome.succeeded:
                stats["ok"] += 1
            else:
                stats["fail"] += 1

    now = datetime.now(UTC)

    # --- Criterion 1: Outcome-correlated failures ---
    for eid, stats in entry_colony_results.items():
        if eid in existing:
            continue
        entry = entries.get(eid)
        if entry is None:
            continue
        total = stats["ok"] + stats["fail"]
        if total < _MIN_COLONY_ACCESS:
            continue
        fail_rate = stats["fail"] / total
        if fail_rate <= _FAILURE_RATE_THRESHOLD:
            continue

        action = create_action(
            kind="knowledge_review",
            title=f"Failure-correlated: {entry.get('title', eid[:12])}",
            detail=f"{stats['fail']}/{total} colonies failed when using this entry",
            source_category="outcome_correlation",
            rationale=f"Entry accessed by {total} colonies with {fail_rate:.0%} failure rate",
            payload={
                "entry_id": eid,
                "title": entry.get("title", ""),
                "content_preview": _content_preview(entry),
                "review_reason": "outcome_correlated_failure",
                "confidence": round(_entry_confidence(entry), 4),
                "access_count": total,
                "failure_count": stats["fail"],
                "failure_rate": round(fail_rate, 4),
            },
            confidence=_entry_confidence(entry),
            created_by="knowledge_review_scanner",
        )
        append_action(data_dir, workspace_id, action)
        existing.add(eid)
        queued += 1

    # --- Criterion 2: Contradictions from briefing insights ---
    if briefing_insights:
        for insight in briefing_insights:
            cat = str(insight.get("category", ""))
            if cat != "contradiction":
                continue
            detail_str = str(insight.get("detail", ""))
            # Extract entry IDs from insight metadata
            entry_ids = _extract_entry_ids_from_insight(insight, entries)
            for eid in entry_ids:
                if eid in existing:
                    continue
                entry = entries.get(eid)
                if entry is None:
                    continue
                action = create_action(
                    kind="knowledge_review",
                    title=f"Contradiction: {entry.get('title', eid[:12])}",
                    detail=detail_str or "Entry involved in a contradiction",
                    source_category="contradiction",
                    rationale="Detected via briefing contradiction analysis",
                    payload={
                        "entry_id": eid,
                        "title": entry.get("title", ""),
                        "content_preview": _content_preview(entry),
                        "review_reason": "contradiction",
                        "confidence": round(_entry_confidence(entry), 4),
                        "access_count": _get_access_count(eid, projections),
                    },
                    confidence=_entry_confidence(entry),
                    created_by="knowledge_review_scanner",
                )
                append_action(data_dir, workspace_id, action)
                existing.add(eid)
                queued += 1

    # --- Criterion 3: Stale authority ---
    stale_cutoff = now - timedelta(days=_STALE_DAYS)
    for eid, entry in entries.items():
        if eid in existing:
            continue
        if entry.get("decay_class") == "permanent":
            continue
        conf = _entry_confidence(entry)
        if conf < _HIGH_CONFIDENCE_THRESHOLD:
            continue
        # Check last_accessed from usage tracking
        usage = projections.knowledge_entry_usage.get(eid, {})
        last_accessed_str = usage.get("last_accessed", "")
        if not last_accessed_str:
            # Never accessed — use created_at
            last_accessed_str = entry.get("created_at", "")
        if not last_accessed_str:
            continue
        try:
            last_accessed = datetime.fromisoformat(last_accessed_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        if last_accessed >= stale_cutoff:
            continue

        access_count = usage.get("count", 0)
        action = create_action(
            kind="knowledge_review",
            title=f"Stale authority: {entry.get('title', eid[:12])}",
            detail=f"High-confidence entry not accessed in {_STALE_DAYS}+ days",
            source_category="stale_authority",
            rationale=f"Confidence {conf:.2f} but last accessed {last_accessed_str[:10]}",
            payload={
                "entry_id": eid,
                "title": entry.get("title", ""),
                "content_preview": _content_preview(entry),
                "review_reason": "stale_authority",
                "confidence": round(conf, 4),
                "access_count": access_count,
            },
            confidence=conf,
            created_by="knowledge_review_scanner",
        )
        append_action(data_dir, workspace_id, action)
        existing.add(eid)
        queued += 1

    # --- Criterion 4: Unconfirmed machine-generated ---
    confirmed_entries = projections.operator_overlays.pinned_entries
    for eid, entry in entries.items():
        if eid in existing:
            continue
        # Skip if operator has confirmed (pinned = confirmation signal)
        if eid in confirmed_entries:
            continue
        # Must be machine-generated (not operator-created)
        if entry.get("created_by") == "operator":
            continue
        # Must be influential (accessed often)
        usage = projections.knowledge_entry_usage.get(eid, {})
        access_count = usage.get("count", 0)
        if access_count < _MIN_ACCESS_FOR_INFLUENTIAL:
            continue

        conf = _entry_confidence(entry)
        action = create_action(
            kind="knowledge_review",
            title=f"Unconfirmed: {entry.get('title', eid[:12])}",
            detail=f"Machine-generated entry accessed {access_count} times, never confirmed",
            source_category="unconfirmed_machine",
            rationale=f"Influential entry (accessed {access_count}x) with no operator confirmation",
            payload={
                "entry_id": eid,
                "title": entry.get("title", ""),
                "content_preview": _content_preview(entry),
                "review_reason": "unconfirmed_machine_generated",
                "confidence": round(conf, 4),
                "access_count": access_count,
            },
            confidence=conf,
            created_by="knowledge_review_scanner",
        )
        append_action(data_dir, workspace_id, action)
        existing.add(eid)
        queued += 1

    if queued > 0:
        log.info(
            "knowledge_review.scan_complete",
            workspace_id=workspace_id,
            actions_queued=queued,
        )

    return queued


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_accessed_entries(
    colony_id: str,
    projections: ProjectionStore,
) -> list[str]:
    """Get entry IDs accessed by a colony from access records."""
    result: list[str] = []
    for eid, usage in projections.knowledge_entry_usage.items():
        # Usage tracks per-entry, not per-colony — use colony outcomes
        # to infer which entries were accessed by checking access events
        colonies = usage.get("colonies", [])
        if colony_id in colonies:
            result.append(eid)
    # Fallback: if colonies not tracked in usage, use the outcome's entries_accessed
    if not result:
        outcome = projections.colony_outcomes.get(colony_id)
        if outcome and outcome.entries_accessed > 0:
            # Cannot map individual entries without colony-level tracking;
            # return empty — this criterion requires per-colony access data
            pass
    return result


def _get_access_count(entry_id: str, projections: ProjectionStore) -> int:
    usage = projections.knowledge_entry_usage.get(entry_id, {})
    return usage.get("count", 0)


def _extract_entry_ids_from_insight(
    insight: dict[str, object],
    entries: dict[str, dict[str, Any]],
) -> list[str]:
    """Extract entry IDs from a contradiction insight."""
    result: list[str] = []
    # Insights may have entry_ids directly
    raw_ids: object = insight.get("entry_ids", [])
    if isinstance(raw_ids, list):
        for raw_eid in raw_ids:  # type: ignore[reportUnknownVariableType]
            eid = str(raw_eid)  # type: ignore[reportUnknownArgumentType]
            if eid in entries:
                result.append(eid)
    # Or they may reference entries in detail text
    if not result:
        detail = str(insight.get("detail", ""))
        for eid in entries:
            if eid in detail:
                result.append(eid)
    return result
