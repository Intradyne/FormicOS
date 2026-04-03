"""Structured planning signal surface (Wave 82 Track A).

Assembles a typed signal dict from existing runtime sources. The
``planning_brief.py`` module formats this into the compact text block
injected into the Queen context. The structured object is also persisted
on ``ParallelPlanCreated`` events for replay and UI rendering.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from formicos.surface.runtime import Runtime

log = structlog.get_logger()

_FILE_HINT_RE = re.compile(r"[A-Za-z0-9_./-]+\.[A-Za-z0-9_]+")


async def build_planning_signals(
    runtime: Runtime,
    workspace_id: str,
    thread_id: str,
    operator_message: str,
) -> dict[str, Any]:
    """Build structured planning signals from existing sources.

    Returns a dict with keys: ``patterns``, ``playbook``, ``capability``,
    ``coupling``, ``previous_plans``.  Each section degrades to empty/None
    when its source is unavailable.
    """
    signals: dict[str, Any] = {
        "patterns": [],
        "playbook": None,
        "capability": None,
        "coupling": None,
        "previous_plans": [],
    }

    # 1. Patterns — knowledge catalog search
    signals["patterns"] = await _fetch_patterns(
        runtime, workspace_id, thread_id, operator_message,
    )

    # 2. Playbook hint
    signals["playbook"] = _fetch_playbook(operator_message)

    # 3. Capability profile
    signals["capability"] = _fetch_capability(runtime, workspace_id)

    # 4. Structural coupling (Team B helper when available)
    signals["coupling"] = _fetch_coupling(runtime, workspace_id, operator_message)

    # 5. Previous successful plans
    signals["previous_plans"] = _fetch_previous_plans(
        runtime, workspace_id, operator_message,
    )

    # 6. Saved plan patterns (Wave 84.5)
    signals["saved_patterns"] = _fetch_saved_patterns(
        runtime, workspace_id, operator_message,
    )

    return signals


async def _fetch_patterns(
    runtime: Runtime,
    workspace_id: str,
    thread_id: str,
    operator_message: str,
) -> list[dict[str, Any]]:
    """Search knowledge catalog for decomposition-relevant patterns."""
    catalog = getattr(runtime, "knowledge_catalog", None)
    if catalog is None:
        return []

    try:
        query = f"decomposition strategy for: {operator_message[:200]}"
        results: list[dict[str, Any]] = await catalog.search(
            query=query,
            workspace_id=workspace_id,
            thread_id=thread_id,
            top_k=5,
        )
    except Exception:
        return []

    hits: list[dict[str, Any]] = []
    for item in results:
        category = item.get("category", "")
        sub_type = item.get("sub_type", "")
        score = item.get("composite_score", 0.0)
        if (
            category in ("skill", "experience")
            or sub_type in ("pattern", "technique", "convention", "learning")
        ) and score > 0.3:
            hits.append({
                "title": (item.get("title", "") or "unnamed")[:40],
                "quality": round(item.get("quality_score", 0.0), 2),
                "score": round(score, 2),
                "category": category,
                "sub_type": sub_type,
            })
    return sorted(hits, key=lambda x: -x["score"])[:3]


def _fetch_playbook(operator_message: str) -> dict[str, Any] | None:
    """Get decomposition hints from playbook loader."""
    try:
        from formicos.engine.playbook_loader import (  # noqa: PLC0415
            get_decomposition_hints,
        )
        hint = get_decomposition_hints(operator_message)
        if hint:
            return {"hint": hint, "source": "playbook"}
    except (ImportError, AttributeError):
        pass
    return None


def _fetch_capability(
    runtime: Runtime,
    workspace_id: str,
) -> dict[str, Any] | None:
    """Get capability profile for the worker model."""
    try:
        model = runtime.resolve_model("coder", workspace_id)
        if not model:
            return None
        short = model.split("/")[-1]
        planner_model = ""
        try:
            planner_model = runtime.resolve_model("queen", workspace_id) or ""
        except Exception:
            planner_model = ""

        summary = None
        try:
            from formicos.surface.capability_profiles import (  # noqa: PLC0415
                get_capability_evidence,
                summarize_capability,
            )
            data_dir = runtime.settings.system.data_dir
            evidence = get_capability_evidence(
                model,
                projections=getattr(runtime, "projections", None),
                workspace_id=workspace_id,
                data_dir=data_dir,
                planner_model=planner_model,
            )
            summary = (
                _format_capability_summary(evidence)
                if evidence
                else summarize_capability(model, data_dir)
            )
        except (ImportError, AttributeError):
            pass

        return {
            "model": model,
            "short_name": short,
            "summary": summary,
        }
    except Exception:
        return None


def _format_capability_summary(evidence: dict[str, Any]) -> str:
    """Render structured capability evidence into the Wave 80 summary shape."""
    label = str(evidence.get("label", "worker"))
    sample_count = int(evidence.get("sample_count", 0) or 0)
    source = str(evidence.get("source", "shipped"))
    optimal = str(evidence.get("optimal_files", "?"))
    quality = float(evidence.get("quality_mean", 0.0) or 0.0)
    return (
        f"{label} (n={sample_count}, {source}) -> {optimal} files optimal, "
        f"focused can reach {quality:.3f}"
    )


def _fetch_coupling(
    runtime: Runtime,
    workspace_id: str,
    operator_message: str,
) -> dict[str, Any] | None:
    """Get structural coupling from Team B's helper or fallback."""
    # Team B structural_planner (when available)
    try:
        from formicos.surface.structural_planner import (  # noqa: PLC0415
            get_structural_hints,
        )
        hints = get_structural_hints(runtime, workspace_id, operator_message)
        if hints:
            return hints
    except (ImportError, AttributeError):
        pass

    # Fallback: lightweight file-reference detection
    lower = operator_message.lower()
    if not any(ind in lower for ind in ("file", "module", ".py", ".ts", "src/")):
        return None
    return {"source": "message_heuristic", "has_file_refs": True}


def _fetch_previous_plans(
    runtime: Runtime,
    workspace_id: str,
    operator_message: str,
) -> list[dict[str, Any]]:
    """Find relevant prior successful plans from workflow learning."""
    try:
        from formicos.surface.workflow_learning import (  # noqa: PLC0415
            get_relevant_outcomes,
        )
        return get_relevant_outcomes(
            runtime.projections,
            workspace_id=workspace_id,
            operator_message=operator_message,
            top_k=3,
        )
    except (ImportError, AttributeError):
        pass

    # Fallback: outcome stats
    try:
        stats = runtime.projections.outcome_stats(workspace_id)
        if stats:
            return [{"source": "outcome_stats", "stats": stats[:3]}]
    except Exception:
        pass
    return []


def _fetch_saved_patterns(
    runtime: Runtime,
    workspace_id: str,
    operator_message: str,
) -> list[dict[str, Any]]:
    """Retrieve saved plan patterns by deterministic matching (Wave 84.5).

    Uses task class + complexity + file overlap for scoring, NOT text
    similarity. Returns compact summaries (not full task_previews).
    """
    try:
        from formicos.surface.plan_patterns import list_patterns  # noqa: PLC0415
        from formicos.surface.task_classifier import classify_task  # noqa: PLC0415
    except ImportError:
        return []

    data_dir = getattr(runtime.settings.system, "data_dir", "")
    if not data_dir:
        return []

    try:
        patterns = list_patterns(data_dir, workspace_id)
    except Exception:
        return []
    if not patterns:
        return []

    task_class, _ = classify_task(operator_message)

    # Classify complexity locally to avoid circular import
    msg_len = len(operator_message)
    complexity = "complex" if msg_len > 160 or "```" in operator_message else "simple"

    file_refs = set(_FILE_HINT_RE.findall(operator_message))

    scored: list[dict[str, Any]] = []
    for p in patterns:
        # Wave 86: respect status — approved/operator patterns first
        status = p.get("status", "approved")  # legacy = approved
        score = 0.0
        source_query = p.get("source_query", "")
        p_class = ""
        if source_query:
            p_class, _ = classify_task(source_query)
        p_len = len(source_query)
        p_complexity = "complex" if p_len > 160 or "```" in source_query else "simple"

        if p_class and p_class == task_class:
            score += 0.5
        if p_complexity == complexity:
            score += 0.2

        p_files: set[str] = set()
        for tp in p.get("task_previews", []):
            p_files.update(tp.get("target_files", []))
        if file_refs & p_files:
            score += 0.3

        outcome = p.get("outcome_summary") or {}
        outcome_q = outcome.get("quality", 0) if isinstance(outcome, dict) else 0
        if outcome_q > 0.5:
            score += 0.2

        # Approved/operator patterns get a trust bonus
        if status == "approved":
            score += 0.1

        if score >= 0.5:
            colony_count = len(p.get("task_previews", []))
            group_count = len(p.get("groups", []))
            scored.append({
                "pattern_id": p.get("pattern_id", ""),
                "name": p.get("name", ""),
                "created_from": p.get("created_from", ""),
                "status": status,
                "match_score": round(score, 2),
                "colony_count": colony_count,
                "group_count": group_count,
                "outcome_quality": outcome_q,
            })

    scored.sort(key=lambda x: -x["match_score"])
    return scored[:1]
