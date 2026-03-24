"""Shared constants for knowledge confidence tuning (ADR-041, Wave 32+33)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from formicos.surface.projections import ProjectionStore

# Gamma-decay: exponential decay toward prior per calendar day
GAMMA_PER_DAY: float = 0.98

# Prior parameters for Beta distribution
PRIOR_ALPHA: float = 5.0
PRIOR_BETA: float = 5.0

# Archival decay equivalent days (D2)
ARCHIVAL_EQUIVALENT_DAYS: int = 30

# Wave 33 A4: cap elapsed days to prevent unbounded decay convergence
MAX_ELAPSED_DAYS: float = 180.0

# Wave 33 A4: per-DecayClass gamma rates (ADR-041 D1)
GAMMA_RATES: dict[str, float] = {
    "ephemeral": 0.98,    # half-life ~34 days (default, current behavior)
    "stable": 0.995,      # half-life ~139 days (domain knowledge)
    "permanent": 1.0,     # no decay (verified definitions)
}

# Wave 34 A3: rebalanced composite weights with co-occurrence (ADR-044 D2)
# Wave 59.5: +graph_proximity, redistributed from freshness (-0.05) and
# cooccurrence (-0.01).
COMPOSITE_WEIGHTS: dict[str, float] = {
    "semantic": 0.38,           # was 0.40 (-0.02)
    "thompson": 0.25,           # unchanged — exploration budget is sacred
    "freshness": 0.10,          # was 0.15 (-0.05, Wave 59.5)
    "status": 0.10,             # was 0.12 (-0.02)
    "thread": 0.07,             # was 0.08 (-0.01)
    "cooccurrence": 0.04,       # was 0.05 (-0.01, Wave 59.5)
    "graph_proximity": 0.06,    # NEW — Wave 59.5
}


def get_workspace_weights(
    workspace_id: str,
    projections: ProjectionStore | Any,  # noqa: ANN401
) -> dict[str, float]:
    """Return composite weights for a workspace. Falls back to defaults (ADR-044 D4)."""
    if projections is None:
        return dict(COMPOSITE_WEIGHTS)
    ws = projections.workspaces.get(workspace_id)
    if ws is not None:
        override: Any = ws.config.get("composite_weights")  # noqa: ANN401
        if override:
            # Handle both dict (direct) and str (JSON-serialized via WorkspaceConfigChanged)
            if isinstance(override, str):
                import json  # noqa: PLC0415

                try:
                    override = json.loads(override)
                except (ValueError, TypeError):
                    return dict(COMPOSITE_WEIGHTS)
            if isinstance(override, dict):
                d = cast("dict[str, Any]", override)
                return {str(k): float(v) for k, v in d.items()}
    return dict(COMPOSITE_WEIGHTS)
