"""Wave 83 Track B: Saved plan-pattern store.

YAML-backed operator asset store for reviewed parallel plans.
Separate from single-colony templates. Explicit provenance.

Patterns are stored under ``<data_dir>/.formicos/plan_patterns/<workspace>/``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()


def _patterns_dir(data_dir: str, workspace_id: str) -> Path:
    return Path(data_dir) / ".formicos" / "plan_patterns" / workspace_id


def _normalize_groups(groups: Any) -> list[dict[str, Any]]:
    """Normalize stored group shapes to the workbench contract."""
    if not isinstance(groups, list):
        return []

    normalized: list[dict[str, Any]] = []
    for group in groups:
        if isinstance(group, list):
            normalized.append({
                "taskIds": [str(task_id) for task_id in group],
                "tasks": [],
            })
            continue
        if isinstance(group, dict):
            task_ids = group.get("taskIds", group.get("task_ids", []))
            tasks = group.get("tasks", [])
            normalized.append({
                "taskIds": [str(task_id) for task_id in task_ids if task_id],
                "tasks": [str(task) for task in tasks if task],
            })
    return normalized


def list_patterns(data_dir: str, workspace_id: str) -> list[dict[str, Any]]:
    """Return all saved plan patterns for a workspace."""
    import yaml  # noqa: PLC0415

    d = _patterns_dir(data_dir, workspace_id)
    if not d.is_dir():
        return []

    results: list[dict[str, Any]] = []
    for path in sorted(d.glob("*.yaml")):
        try:
            data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            data["groups"] = _normalize_groups(data.get("groups", []))
            data["_file"] = path.stem
            results.append(data)
        except Exception:
            log.warning("plan_patterns.parse_error", path=str(path))
    return results


def get_pattern(
    data_dir: str, workspace_id: str, pattern_id: str,
) -> dict[str, Any] | None:
    """Return a single saved pattern by ID, or None if not found."""
    import yaml  # noqa: PLC0415

    d = _patterns_dir(data_dir, workspace_id)
    path = d / f"{pattern_id}.yaml"
    if not path.exists():
        return None
    try:
        data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        data["groups"] = _normalize_groups(data.get("groups", []))
        data["_file"] = path.stem
        return data
    except Exception:
        log.warning("plan_patterns.parse_error", path=str(path))
        return None


def save_pattern(
    data_dir: str,
    workspace_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Persist a reviewed plan as a named pattern. Returns the saved data."""
    import yaml  # noqa: PLC0415

    d = _patterns_dir(data_dir, workspace_id)
    d.mkdir(parents=True, exist_ok=True)

    pattern_id = payload.get("pattern_id") or f"pp-{uuid.uuid4().hex[:12]}"

    data: dict[str, Any] = {
        "pattern_id": pattern_id,
        "name": payload.get("name", "Untitled pattern"),
        "description": payload.get("description", ""),
        "workspace_id": workspace_id,
        "thread_id": payload.get("thread_id", ""),
        "source_query": payload.get("source_query", ""),
        "planner_model": payload.get("planner_model", ""),
        "task_previews": payload.get("task_previews", []),
        "groups": _normalize_groups(payload.get("groups", [])),
        "created_at": datetime.now(UTC).isoformat(),
        "created_from": payload.get("created_from", "reviewed_plan"),
    }

    # Optional outcome summary (if saved after execution)
    if "outcome_summary" in payload:
        data["outcome_summary"] = payload["outcome_summary"]

    # Wave 86: additive trust fields
    if "status" in payload:
        data["status"] = payload["status"]
    if "learning_source" in payload:
        data["learning_source"] = payload["learning_source"]
    if "evidence" in payload:
        data["evidence"] = payload["evidence"]
    if "_bundle_key" in payload:
        data["_bundle_key"] = payload["_bundle_key"]

    path = d / f"{pattern_id}.yaml"
    path.write_text(
        yaml.safe_dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )

    log.info(
        "plan_patterns.saved",
        pattern_id=pattern_id,
        workspace_id=workspace_id,
        tasks=len(data.get("task_previews", [])),
    )
    data["_file"] = path.stem
    return data


def _derive_bundle_key(
    task_class: str,
    route: str,
    target_files: list[str],
    group_count: int,
    colony_count: int,
) -> str:
    """Derive a deterministic dedup key from plan structure."""
    import hashlib  # noqa: PLC0415

    norm_files = sorted(set(f.lower().strip() for f in target_files if f))
    parts = [task_class, route, str(group_count), str(colony_count)]
    parts.extend(norm_files[:10])
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def verify_outcome(
    quality: float,
    *,
    validator_verdict: str = "",
    productive_calls: int = 0,
    total_calls: int = 0,
    failed_colonies: int = 0,
    total_colonies: int = 1,
) -> dict[str, Any]:
    """Evaluate an outcome for learning eligibility.

    Returns a dict with ``state``, ``learnable``, and ``reasons``.
    """
    reasons: list[str] = []
    state = "validated"

    if quality < 0.4:
        state = "failed_delivery"
        reasons.append(f"low quality ({quality:.2f})")
    elif quality < 0.6:
        state = "needs_review"
        reasons.append(f"marginal quality ({quality:.2f})")

    if validator_verdict and validator_verdict not in ("pass", "ok", ""):
        state = "failed_delivery"
        reasons.append(f"validator: {validator_verdict}")

    if total_calls > 0 and productive_calls / total_calls < 0.3:
        if state == "validated":
            state = "needs_review"
        reasons.append("low productivity ratio")

    if failed_colonies > 0 and failed_colonies / max(total_colonies, 1) > 0.5:
        state = "failed_delivery"
        reasons.append(f"{failed_colonies}/{total_colonies} colonies failed")

    learnable = state == "validated" and quality >= 0.6
    return {"state": state, "learnable": learnable, "reasons": reasons}


def auto_learn_pattern(
    data_dir: str,
    workspace_id: str,
    *,
    plan_data: dict[str, Any],
    outcome: dict[str, Any],
    task_class: str = "",
    route: str = "",
) -> dict[str, Any] | None:
    """Auto-save a candidate pattern from a validated plan outcome.

    Deduplicates by deterministic bundle. Promotes existing candidates
    to approved on repeated success.
    """
    task_previews = plan_data.get("task_previews") or plan_data.get("tasks", [])
    groups = plan_data.get("groups") or plan_data.get("parallel_groups", [])
    colony_count = len(task_previews)
    group_count = len(groups)

    # Derive target files from task previews
    target_files: list[str] = []
    for tp in task_previews:
        target_files.extend(tp.get("target_files", []))

    bundle_key = _derive_bundle_key(
        task_class, route, target_files, group_count, colony_count,
    )

    # Check for existing pattern with same bundle
    existing = list_patterns(data_dir, workspace_id)
    for pat in existing:
        if pat.get("_bundle_key") == bundle_key:
            # Promote candidate -> approved on repeated success
            if pat.get("status") == "candidate":
                _promote_pattern(data_dir, workspace_id, pat, outcome)
                return pat
            # Already approved — update evidence
            _update_evidence(data_dir, workspace_id, pat, outcome)
            return pat

    # Save new candidate pattern
    payload: dict[str, Any] = {
        "name": plan_data.get("name", f"auto-{bundle_key[:8]}"),
        "source_query": plan_data.get("source_query", ""),
        "planner_model": plan_data.get("planner_model", ""),
        "task_previews": task_previews,
        "groups": groups,
        "created_from": "auto_learned",
        "status": "candidate",
        "learning_source": "auto",
        "_bundle_key": bundle_key,
        "evidence": {
            "success_count": 1,
            "last_quality": outcome.get("quality", 0.0),
            "task_class": task_class,
            "route": route,
        },
        "outcome_summary": {
            "quality": outcome.get("quality", 0.0),
            "succeeded": outcome.get("succeeded", 0),
            "total": outcome.get("total", 0),
        },
    }

    saved = save_pattern(data_dir, workspace_id, payload)
    log.info(
        "plan_patterns.auto_learned",
        pattern_id=saved.get("pattern_id"),
        bundle_key=bundle_key,
        status="candidate",
    )
    return saved


def _promote_pattern(
    data_dir: str,
    workspace_id: str,
    pattern: dict[str, Any],
    outcome: dict[str, Any],
) -> None:
    """Promote a candidate pattern to approved."""
    import yaml  # noqa: PLC0415

    pattern_id = pattern.get("pattern_id", "")
    d = _patterns_dir(data_dir, workspace_id)
    path = d / f"{pattern_id}.yaml"
    if not path.exists():
        return

    data: dict[str, Any] = yaml.safe_load(
        path.read_text(encoding="utf-8"),
    ) or {}
    data["status"] = "approved"
    evidence = data.get("evidence", {})
    evidence["success_count"] = evidence.get("success_count", 0) + 1
    evidence["last_quality"] = outcome.get("quality", 0.0)
    data["evidence"] = evidence
    data["outcome_summary"] = {
        "quality": outcome.get("quality", 0.0),
        "succeeded": outcome.get("succeeded", 0),
        "total": outcome.get("total", 0),
    }

    path.write_text(
        yaml.safe_dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    log.info(
        "plan_patterns.promoted",
        pattern_id=pattern_id,
        status="approved",
    )


def _update_evidence(
    data_dir: str,
    workspace_id: str,
    pattern: dict[str, Any],
    outcome: dict[str, Any],
) -> None:
    """Update evidence counters on an existing approved pattern."""
    import yaml  # noqa: PLC0415

    pattern_id = pattern.get("pattern_id", "")
    d = _patterns_dir(data_dir, workspace_id)
    path = d / f"{pattern_id}.yaml"
    if not path.exists():
        return

    data: dict[str, Any] = yaml.safe_load(
        path.read_text(encoding="utf-8"),
    ) or {}
    evidence = data.get("evidence", {})
    evidence["success_count"] = evidence.get("success_count", 0) + 1
    evidence["last_quality"] = outcome.get("quality", 0.0)
    data["evidence"] = evidence

    path.write_text(
        yaml.safe_dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


__all__ = [
    "auto_learn_pattern",
    "get_pattern",
    "list_patterns",
    "save_pattern",
    "verify_outcome",
]
