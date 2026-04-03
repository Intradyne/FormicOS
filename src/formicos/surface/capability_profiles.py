"""Capability profiles — shipped priors + replay-derived overlays (Wave 82).

Provides planning-time capability summaries keyed by (planner, worker,
task_class, granularity). Shipped JSON is the bootstrap prior; replay-
derived colony outcomes are the authority when enough evidence exists.

No external database, no new events. Derived from existing projections.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from formicos.surface.projections import ProjectionStore

log = structlog.get_logger()

_CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"
_SHIPPED_PATH = _CONFIG_DIR / "capability_profiles.json"

_PROFILES: dict[str, dict[str, Any]] | None = None

# Minimum observations before replay overlays override shipped priors.
_MIN_REPLAY_OBSERVATIONS = 3

# Granularity buckets derived from colony file counts.
_GRANULARITY_THRESHOLDS = {
    "focused_single": (1, 1),
    "fine_split": (2, 3),
    "grouped_small": (4, 6),
    "grouped_medium": (7, 999),
}


def _classify_granularity(file_count: int) -> str:
    """Map a file count to a granularity bucket."""
    for bucket, (lo, hi) in _GRANULARITY_THRESHOLDS.items():
        if lo <= file_count <= hi:
            return bucket
    return "grouped_medium"


def _dominant_worker_model(
    model_usage: dict[str, dict[str, float]],
    planner_model: str,
) -> str:
    """Return the model with highest total tokens, excluding the planner."""
    best = ""
    best_tokens = 0.0
    for model, usage in model_usage.items():
        if model == planner_model:
            continue
        total = usage.get("input_tokens", 0.0) + usage.get("output_tokens", 0.0)
        if total > best_tokens:
            best_tokens = total
            best = model
    return best or planner_model


# ---------------------------------------------------------------------------
# Shipped profile loading (unchanged from Wave 80)
# ---------------------------------------------------------------------------


def _load_profiles(data_dir: str = "") -> dict[str, dict[str, Any]]:
    """Load shipped defaults, optionally merging a runtime override file."""
    global _PROFILES  # noqa: PLW0603
    if _PROFILES is not None:
        return _PROFILES

    profiles: dict[str, dict[str, Any]] = {}

    # Shipped defaults
    if _SHIPPED_PATH.exists():
        try:
            raw = json.loads(_SHIPPED_PATH.read_text(encoding="utf-8"))
            profiles.update(raw.get("profiles", {}))
        except Exception:
            log.warning("capability_profiles.shipped_load_error")

    # Runtime override (additive merge)
    if data_dir:
        override_path = (
            Path(data_dir) / ".formicos" / "runtime" / "capability_profiles.json"
        )
        if override_path.exists():
            try:
                raw = json.loads(override_path.read_text(encoding="utf-8"))
                for key, val in raw.get("profiles", {}).items():
                    if key in profiles:
                        profiles[key] = {**profiles[key], **val}
                    else:
                        profiles[key] = val
                log.info(
                    "capability_profiles.runtime_override_loaded",
                    path=str(override_path),
                    count=len(raw.get("profiles", {})),
                )
            except Exception:
                log.warning("capability_profiles.runtime_load_error")

    _PROFILES = profiles
    return profiles


def _resolve_profile(
    model_addr: str, profiles: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Resolve a model address to a capability profile.

    Resolution order:
    1. Exact full address (e.g. ``llama-cpp-swarm/qwen3.5-4b-swarm``)
    2. Last path segment (e.g. ``qwen3.5-4b-swarm``)
    3. Suffix normalization: strip ``-swarm`` (e.g. ``qwen3.5-4b``)
    """
    if model_addr in profiles:
        return profiles[model_addr]

    segment = model_addr.rsplit("/", 1)[-1] if "/" in model_addr else model_addr
    if segment in profiles:
        return profiles[segment]

    normalized = segment.removesuffix("-swarm")
    if normalized != segment and normalized in profiles:
        return profiles[normalized]

    return None


# ---------------------------------------------------------------------------
# Replay-derived overlays
# ---------------------------------------------------------------------------


def derive_overlays_from_projections(
    projections: ProjectionStore,
    *,
    workspace_id: str = "",
) -> dict[str, dict[str, Any]]:
    """Derive capability overlays from replay-derived colony outcomes.

    Returns a dict keyed by ``"{planner}|{worker}|{task_class}|{granularity}"``
    with aggregated evidence.
    """
    overlays: dict[str, list[dict[str, Any]]] = {}

    for outcome in getattr(projections, "outcomes", {}).values():
        if workspace_id and outcome.workspace_id != workspace_id:
            continue
        if not outcome.succeeded:
            continue

        # Derive planner model from thread's plan event or default queen model
        colony = projections.colonies.get(outcome.colony_id)
        if not colony:
            continue

        budget = projections.budgets.get(outcome.colony_id)
        model_usage = budget.model_usage if budget else {}

        # Planner = queen model assignment, worker = dominant non-queen model
        planner = colony.model_assignments.get("queen", "")
        worker = _dominant_worker_model(model_usage, planner) if model_usage else ""
        if not worker:
            worker = next(
                (m for c, m in colony.model_assignments.items() if c != "queen"),
                planner,
            )

        # Task class: use caste composition as a rough proxy
        task_class = "_".join(sorted(outcome.caste_composition)) or "unknown"

        # Granularity: derive from colony file scope
        target_files = getattr(colony, "target_files", []) or []
        granularity = _classify_granularity(len(target_files)) if target_files else "unknown"

        key = f"{planner}|{worker}|{task_class}|{granularity}"
        overlays.setdefault(key, []).append({
            "quality": outcome.quality_score,
            "rounds": outcome.total_rounds,
            "cost": outcome.total_cost,
            "duration_ms": outcome.duration_ms,
            "strategy": outcome.strategy,
        })

    # Aggregate
    result: dict[str, dict[str, Any]] = {}
    for key, observations in overlays.items():
        n = len(observations)
        parts = key.split("|")
        avg_quality = sum(o["quality"] for o in observations) / n
        avg_rounds = sum(o["rounds"] for o in observations) / n

        if n >= 10:
            tier = "high"
        elif n >= _MIN_REPLAY_OBSERVATIONS:
            tier = "moderate"
        else:
            tier = "low"

        result[key] = {
            "planner": parts[0] if len(parts) > 0 else "",
            "worker": parts[1] if len(parts) > 1 else "",
            "task_class": parts[2] if len(parts) > 2 else "",
            "granularity": parts[3] if len(parts) > 3 else "",
            "sample_count": n,
            "quality_mean": round(avg_quality, 3),
            "rounds_mean": round(avg_rounds, 1),
            "evidence_tier": tier,
            "observations": observations,
        }

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_capability_evidence(
    model_addr: str,
    *,
    projections: ProjectionStore | None = None,
    workspace_id: str = "",
    data_dir: str = "",
    planner_model: str = "",
    task_class: str = "",
    granularity: str = "",
) -> dict[str, Any] | None:
    """Return structured capability evidence for a model.

    Merges shipped priors with replay-derived overlays. Returns ``None``
    if no profile or evidence matches.

    Returned shape::

        {
            "label": "qwen3.5-4b",
            "source": "replay" | "shipped" | "merged",
            "sample_count": 24,
            "quality_mean": 0.738,
            "rounds_mean": 4.2,
            "evidence_tier": "high" | "moderate" | "low" | "prior_only",
            "optimal_files": "3-4",
            "notes": "...",
            "warnings": [],
        }
    """
    profiles = _load_profiles(data_dir)
    shipped = _resolve_profile(model_addr, profiles)

    # Try replay overlays
    replay_match: dict[str, Any] | None = None
    if projections is not None:
        overlays = derive_overlays_from_projections(
            projections, workspace_id=workspace_id,
        )
        # Try progressively less specific key prefixes.
        # Overlay keys use full model addresses (e.g. "llama-cpp/qwen3.5-35b").
        worker_full = model_addr
        worker_segment = model_addr.rsplit("/", 1)[-1] if "/" in model_addr else model_addr
        candidates = [
            f"{planner_model}|{worker_full}|{task_class}|{granularity}",
            f"{planner_model}|{worker_full}|{task_class}|",
            f"{planner_model}|{worker_full}|",
            f"|{worker_full}|",
            f"|{worker_segment}|",
        ]
        for candidate_prefix in candidates:
            prefix = candidate_prefix.rstrip("|")
            for key, val in overlays.items():
                if key.startswith(prefix) and val["sample_count"] >= _MIN_REPLAY_OBSERVATIONS:
                    replay_match = val
                    break
            if replay_match:
                break

    # Merge
    if replay_match and shipped:
        return {
            "label": shipped.get("label", model_addr.rsplit("/", 1)[-1]),
            "source": "merged",
            "sample_count": replay_match["sample_count"],
            "quality_mean": replay_match["quality_mean"],
            "rounds_mean": replay_match["rounds_mean"],
            "evidence_tier": replay_match["evidence_tier"],
            "optimal_files": shipped.get("optimal_files", "?"),
            "notes": shipped.get("notes", ""),
            "warnings": [],
        }
    if replay_match:
        return {
            "label": replay_match.get("worker", model_addr.rsplit("/", 1)[-1]),
            "source": "replay",
            "sample_count": replay_match["sample_count"],
            "quality_mean": replay_match["quality_mean"],
            "rounds_mean": replay_match["rounds_mean"],
            "evidence_tier": replay_match["evidence_tier"],
            "optimal_files": "?",
            "notes": "",
            "warnings": [],
        }
    if shipped:
        return {
            "label": shipped.get("label", model_addr.rsplit("/", 1)[-1]),
            "source": "shipped",
            "sample_count": shipped.get("observations", 0),
            "quality_mean": shipped.get("focused_quality", 0.0),
            "rounds_mean": 0.0,
            "evidence_tier": "prior_only",
            "optimal_files": shipped.get("optimal_files", "?"),
            "notes": shipped.get("notes", ""),
            "warnings": ["Using shipped priors only — no replay evidence yet"],
        }

    return None


def summarize_capability(model_addr: str, data_dir: str = "") -> str | None:
    """Return a one-line capability summary for a model.

    Returns ``None`` if no profile matches. Backward-compatible with Wave 80.
    """
    evidence = get_capability_evidence(model_addr, data_dir=data_dir)
    if evidence is None:
        return None

    label = evidence["label"]
    n = evidence["sample_count"]
    optimal = evidence.get("optimal_files", "?")
    quality = evidence.get("quality_mean", 0.0)
    source = evidence.get("source", "shipped")

    return (
        f"{label} (n={n}, {source}) -> {optimal} files optimal, "
        f"focused can reach {quality:.3f}"
    )


def clear_cache() -> None:
    """Clear cached profiles (for testing)."""
    global _PROFILES  # noqa: PLW0603
    _PROFILES = None


__all__ = [
    "clear_cache",
    "derive_overlays_from_projections",
    "get_capability_evidence",
    "summarize_capability",
]
