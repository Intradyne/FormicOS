"""Workflow learning — pattern recognition and procedure suggestions (Wave 72 Track 8-9).

Deterministic extractors that propose ``workflow_template`` and
``procedure_suggestion`` actions through the existing action queue.
Called by the operational sweep in ``app.py`` (Team B wires the order).

No LLM calls. No new events. All proposals flow through ``action_queue``.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, cast

import structlog

from formicos.surface.action_queue import (
    STATUS_PENDING_REVIEW,
    append_action,
    create_action,
    read_actions,
)

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Track 8: Workflow pattern recognition
# ---------------------------------------------------------------------------

# Minimum successful occurrences before proposing a template
_MIN_SUCCESS_COUNT = 3
# Minimum distinct threads to count as a real pattern
_MIN_DISTINCT_THREADS = 2


async def extract_workflow_patterns(
    data_dir: str,
    workspace_id: str,
    outcomes: list[Any],
    existing_templates: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Scan colony outcomes for repeating successful patterns.

    Returns list of proposed actions (already persisted to the queue).
    """
    if not data_dir or not workspace_id:
        return []

    # Group successful outcomes by (strategy, caste_set) fingerprint
    fingerprints: dict[str, list[Any]] = {}
    for outcome in outcomes:
        if not _is_successful(outcome):
            continue
        fp = _fingerprint(outcome)
        if fp:
            fingerprints.setdefault(fp, []).append(outcome)

    # Check for pending workflow_template actions to avoid duplicates
    existing_actions = read_actions(data_dir, workspace_id)
    pending_fps = _pending_workflow_fps(existing_actions)

    # Check existing learned templates to avoid re-proposing
    template_fps = _template_fingerprints(existing_templates or [])

    proposals: list[dict[str, Any]] = []
    for fp, group in fingerprints.items():
        if len(group) < _MIN_SUCCESS_COUNT:
            continue
        if fp in pending_fps or fp in template_fps:
            continue

        # Require multiple distinct threads
        thread_ids = {_get_thread_id(o) for o in group if _get_thread_id(o)}
        if len(thread_ids) < _MIN_DISTINCT_THREADS:
            continue

        # Build proposal
        representative = group[0]
        strategy = _get_strategy(representative)
        castes = _get_castes(representative)
        avg_cost = sum(_get_cost(o) for o in group) / len(group)

        action = create_action(
            kind="workflow_template",
            title=f"Learned pattern: {strategy} with {', '.join(sorted(castes))}",
            detail=(
                f"Observed {len(group)} successful colonies across "
                f"{len(thread_ids)} threads using strategy={strategy}, "
                f"castes={sorted(castes)}. Avg cost ${avg_cost:.3f}."
            ),
            source_category="workflow_learning",
            rationale=(
                f"Repeated success pattern ({len(group)} occurrences, "
                f"{len(thread_ids)} threads) suggests a reusable template."
            ),
            payload={
                "fingerprint": fp,
                "strategy": strategy,
                "castes": sorted(castes),
                "occurrence_count": len(group),
                "avg_cost": round(avg_cost, 4),
                "thread_ids": sorted(thread_ids)[:5],
            },
            estimated_cost=round(avg_cost, 4),
            confidence=min(0.9, 0.5 + 0.1 * len(group)),
            created_by="workflow_learning",
        )
        append_action(data_dir, workspace_id, action)
        proposals.append(action)

    if proposals:
        log.info(
            "workflow_learning.patterns_proposed",
            workspace_id=workspace_id,
            count=len(proposals),
        )

    return proposals


# ---------------------------------------------------------------------------
# Track 9: Procedure suggestions
# ---------------------------------------------------------------------------

# Minimum repeated behavior count to propose a procedure
_MIN_BEHAVIOR_COUNT = 3


async def detect_operator_patterns(
    data_dir: str,
    workspace_id: str,
    actions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Scan operator behavior for recurring patterns that suggest procedures.

    Conservative heuristics only:
    - Repeated rejection of autonomous work on shared keywords
    - Repeated review-after-coding patterns
    - Repeated testing-after-change behavior

    Returns list of proposed actions (already persisted to the queue).
    """
    if not data_dir or not workspace_id:
        return []

    all_actions = actions if actions is not None else read_actions(data_dir, workspace_id)

    # Avoid duplicate proposals
    pending_suggestions = {
        a.get("payload", {}).get("pattern_key", "")
        for a in all_actions
        if a.get("kind") == "procedure_suggestion"
        and a.get("status") == STATUS_PENDING_REVIEW
    }

    proposals: list[dict[str, Any]] = []

    # Pattern 1: Repeated rejection of specific kinds/categories
    rejection_patterns = _find_rejection_patterns(all_actions)
    for pattern_key, detail in rejection_patterns:
        if pattern_key in pending_suggestions:
            continue
        action = _create_procedure_suggestion(
            data_dir, workspace_id, pattern_key, detail,
        )
        proposals.append(action)

    # Pattern 2: Repeated approval of review-type work
    review_patterns = _find_review_patterns(all_actions)
    for pattern_key, detail in review_patterns:
        if pattern_key in pending_suggestions:
            continue
        action = _create_procedure_suggestion(
            data_dir, workspace_id, pattern_key, detail,
        )
        proposals.append(action)

    if proposals:
        log.info(
            "workflow_learning.procedure_suggestions",
            workspace_id=workspace_id,
            count=len(proposals),
        )

    return proposals


# ---------------------------------------------------------------------------
# Internal helpers — pattern fingerprinting
# ---------------------------------------------------------------------------


def _fingerprint(outcome: Any) -> str:
    """Create a stable fingerprint from (strategy, sorted castes)."""
    strategy = _get_strategy(outcome)
    castes = _get_castes(outcome)
    if not strategy or not castes:
        return ""
    return f"{strategy}:{','.join(sorted(castes))}"


def _is_successful(outcome: Any) -> bool:
    """Check if an outcome represents a successful colony."""
    if hasattr(outcome, "succeeded"):
        return bool(outcome.succeeded)
    if isinstance(outcome, dict):
        return bool(cast("dict[str, Any]", outcome).get("succeeded", False))
    return False


def _get_strategy(outcome: Any) -> str:
    if hasattr(outcome, "strategy"):
        return str(outcome.strategy)
    if isinstance(outcome, dict):
        return str(cast("dict[str, Any]", outcome).get("strategy", ""))
    return ""


def _get_castes(outcome: Any) -> set[str]:
    cc: Any
    if hasattr(outcome, "caste_composition"):
        cc = outcome.caste_composition
    elif isinstance(outcome, dict):
        cc = cast("dict[str, Any]", outcome).get("caste_composition", {})
    else:
        return set()
    if isinstance(cc, dict):
        return set(cast("dict[str, Any]", cc).keys())
    return set()


def _get_cost(outcome: Any) -> float:
    if hasattr(outcome, "total_cost"):
        return float(outcome.total_cost)
    if isinstance(outcome, dict):
        return float(cast("dict[str, Any]", outcome).get("total_cost", 0.0))
    return 0.0


def _get_thread_id(outcome: Any) -> str:
    if hasattr(outcome, "colony_id"):
        return str(getattr(outcome, "thread_id", "")) or str(outcome.colony_id)[:12]
    if isinstance(outcome, dict):
        d = cast("dict[str, Any]", outcome)
        return str(d.get("thread_id", "")) or str(d.get("colony_id", ""))[:12]
    return ""


def _pending_workflow_fps(actions: list[dict[str, Any]]) -> set[str]:
    """Get fingerprints of pending workflow_template actions."""
    return {
        a.get("payload", {}).get("fingerprint", "")
        for a in actions
        if a.get("kind") == "workflow_template"
        and a.get("status") == STATUS_PENDING_REVIEW
    }


def _template_fingerprints(templates: list[Any]) -> set[str]:
    """Get fingerprints of existing learned templates."""
    fps: set[str] = set()
    for t in templates:
        strategy = getattr(t, "strategy", "") or ""
        castes_raw = getattr(t, "castes", []) or []
        castes = sorted(
            c.caste if hasattr(c, "caste") else str(c) for c in castes_raw
        )
        if strategy and castes:
            fps.add(f"{strategy}:{','.join(castes)}")
    return fps


# ---------------------------------------------------------------------------
# Internal helpers — procedure suggestion patterns
# ---------------------------------------------------------------------------


def _find_rejection_patterns(
    actions: list[dict[str, Any]],
) -> list[tuple[str, dict[str, Any]]]:
    """Find repeated rejection of specific action categories."""
    results: list[tuple[str, dict[str, Any]]] = []

    # Count rejections by source_category
    rejection_counts: Counter[str] = Counter()
    for a in actions:
        if a.get("status") != "rejected":
            continue
        cat = a.get("source_category", "")
        if cat:
            rejection_counts[cat] += 1

    for category, count in rejection_counts.items():
        if count >= _MIN_BEHAVIOR_COUNT:
            pattern_key = f"reject:{category}"
            results.append((pattern_key, {
                "heading": "Autonomy",
                "rule": (
                    f"Require my approval before running {category} actions "
                    f"(rejected {count} times)."
                ),
                "reason": (
                    f"You rejected {count} actions from category '{category}'. "
                    f"This suggests a standing rule may be appropriate."
                ),
                "pattern_type": "rejection",
                "category": category,
                "count": count,
            }))

    return results


def _find_review_patterns(
    actions: list[dict[str, Any]],
) -> list[tuple[str, dict[str, Any]]]:
    """Find patterns suggesting review-after-work procedures."""
    results: list[tuple[str, dict[str, Any]]] = []

    # Count approved maintenance actions — repeated approval of a category
    # suggests the operator wants to keep reviewing rather than auto-approving
    approval_counts: Counter[str] = Counter()
    for a in actions:
        if a.get("status") != "approved" or a.get("kind") != "maintenance":
            continue
        cat = a.get("source_category", "")
        if cat:
            approval_counts[cat] += 1

    for category, count in approval_counts.items():
        if count >= _MIN_BEHAVIOR_COUNT:
            pattern_key = f"review:{category}"
            results.append((pattern_key, {
                "heading": "Autonomy",
                "rule": (
                    f"Always review {category} actions before execution "
                    f"(approved {count} manually)."
                ),
                "reason": (
                    f"You manually approved {count} '{category}' actions. "
                    f"Formalizing this as a standing rule ensures consistent review."
                ),
                "pattern_type": "review",
                "category": category,
                "count": count,
            }))

    return results


def _create_procedure_suggestion(
    data_dir: str,
    workspace_id: str,
    pattern_key: str,
    detail: dict[str, Any],
) -> dict[str, Any]:
    """Create and persist a procedure_suggestion action."""
    action = create_action(
        kind="procedure_suggestion",
        title=f"Suggested rule: {detail['rule'][:80]}",
        detail=detail.get("reason", ""),
        source_category="workflow_learning",
        rationale=detail.get("reason", ""),
        payload={
            "pattern_key": pattern_key,
            "heading": detail.get("heading", "General"),
            "rule": detail["rule"],
            "pattern_type": detail.get("pattern_type", ""),
            "category": detail.get("category", ""),
            "count": detail.get("count", 0),
        },
        confidence=0.6,
        created_by="workflow_learning",
    )
    append_action(data_dir, workspace_id, action)
    return action


# ---------------------------------------------------------------------------
# Wave 82 Track A: Planning-side read path
# ---------------------------------------------------------------------------


def get_relevant_outcomes(
    projections: Any,  # noqa: ANN401
    *,
    workspace_id: str,
    operator_message: str,
    planner_model: str = "",
    worker_model: str = "",
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Return relevant prior plan outcomes for planning-time comparison.

    Surfaces the most informative successful prior decompositions from
    replay-derived outcome stats.
    """
    try:
        stats = projections.outcome_stats(workspace_id)
    except Exception:
        return []

    if not stats:
        return []

    results: list[dict[str, Any]] = []

    for entry in stats:
        strategy = entry.get("strategy", "unknown")
        avg_q = entry.get("avg_quality", 0.0)
        count = entry.get("count", 0)
        avg_rounds = entry.get("avg_rounds", 0.0)
        caste_mix = entry.get("caste_mix", "")
        success_rate = entry.get("success_rate", 0.0)

        if count < 1:
            continue

        # Simple relevance: prefer entries with higher quality and count
        relevance = avg_q * 0.5 + min(count / 10.0, 0.3) + success_rate * 0.2

        results.append({
            "strategy": strategy,
            "avg_quality": round(avg_q, 3),
            "count": count,
            "avg_rounds": round(avg_rounds, 1),
            "caste_mix": caste_mix,
            "success_rate": round(success_rate, 3),
            "planner_model": planner_model,
            "worker_model": worker_model,
            "relevance": round(relevance, 3),
            "evidence": (
                f"{strategy}, n={count}, "
                f"q={avg_q:.2f}, sr={success_rate:.2f}"
            ),
        })

    results.sort(key=lambda x: -x["relevance"])
    return results[:top_k]
