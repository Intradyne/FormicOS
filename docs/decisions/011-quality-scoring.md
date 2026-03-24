# ADR-011: Colony Quality Scoring from Existing Signals

**Status:** Proposed
**Date:** 2026-03-13

## Context

FormicOS needs a fitness signal for each colony run. This signal serves three
purposes: (1) the operator sees at a glance which colonies produced good work,
(2) the future Experimentation Engine uses it to compare control vs variant
configurations, (3) skill confidence scoring weights skills from high-quality
colonies higher.

The tempting approach is LLM-as-judge: after a colony completes, ask a separate
LLM to rate the output 0-10. This is circular for local models (the model that
produced the output judges its own output) and expensive for cloud models (an
additional API call per colony for quality assessment alone). Production systems
at Anthropic and McKinsey use LLM-as-judge, but they have access to frontier
models judging smaller-model outputs — FormicOS's alpha runs on a single local
model.

## Decision

Colony quality is a **composite score computed from signals the governance
engine already produces**. No additional LLM call. No new event types. The
score is a derived metric stored in the `ColonyProjection` and included in
the state snapshot.

### Input Signals

All signals are already available from existing events and round results:

| Signal | Source | Range | Meaning |
|--------|--------|-------|---------|
| `rounds_to_completion` | `ColonyCompleted.round_number` | 1–25 | Fewer = more efficient |
| `convergence_at_completion` | Last `RoundCompleted.convergence` | 0.0–1.0 | Higher = better agreement |
| `governance_warnings` | Count of `GovernanceDecision.action == "warn"` | 0–N | Fewer = smoother run |
| `stall_rounds` | Count of rounds with `is_stalled == True` | 0–N | Fewer = better progress |
| `total_cost` | Sum of `RoundCompleted.cost` | 0.0–∞ | Lower = more efficient |
| `completion_type` | `ColonyCompleted` vs `ColonyFailed` | binary | Success vs failure |

### Scoring Formula

The composite score uses a **weighted geometric mean** so that a single bad
signal dominates (a colony that converged quickly but had 5 governance warnings
is NOT high-quality). All signals are first normalized to [0, 1] where 1 = best.

```python
def compute_quality_score(
    rounds_completed: int,
    max_rounds: int,
    convergence: float,
    governance_warnings: int,
    stall_rounds: int,
    completed_successfully: bool,
) -> float:
    """
    Composite quality score in [0.0, 1.0].
    Uses weighted geometric mean so worst signal dominates.
    """
    if not completed_successfully:
        return 0.0

    # Normalize each signal to [0, 1] where 1 = best
    # Round efficiency: completing in fewer rounds is better
    round_efficiency = 1.0 - (rounds_completed / max_rounds)

    # Convergence: higher is better (already 0-1)
    convergence_score = convergence

    # Governance: fewer warnings is better. 0 warnings = 1.0, 3+ = 0.0
    governance_score = max(0.0, 1.0 - (governance_warnings / 3.0))

    # Stall ratio: fewer stall rounds relative to total is better
    stall_score = 1.0 - min(1.0, stall_rounds / max(rounds_completed, 1))

    # Weights (sum to 1.0)
    weights = {
        "round_efficiency": 0.25,
        "convergence": 0.30,
        "governance": 0.25,
        "stall": 0.20,
    }

    signals = {
        "round_efficiency": max(round_efficiency, 0.01),  # floor to avoid log(0)
        "convergence": max(convergence_score, 0.01),
        "governance": max(governance_score, 0.01),
        "stall": max(stall_score, 0.01),
    }

    # Weighted geometric mean
    import math
    log_sum = sum(
        weights[k] * math.log(signals[k]) for k in weights
    )
    return math.exp(log_sum)
```

### Where the Score is Computed

In `colony_manager.py`, immediately before emitting `ColonyCompleted`. The
round results are still in scope. The score is stored on `ColonyProjection`
via a new field `quality_score: float` and included in the state snapshot.

**Not a new event.** The quality score is a derived metric, not a state-changing
fact. It belongs on the projection, not in the event stream. If the formula
changes, all existing colony scores are recomputed on replay — which is the
correct behavior for a derived metric.

### Frontend Surface

The quality score appears as a colored indicator on the colony card in
`queen-overview.ts`:

- Score ≥ 0.7: green dot
- Score 0.4–0.7: amber dot
- Score < 0.4: red dot
- Failed colonies: gray dot

The numeric score appears on hover / in the colony detail view.

## Consequences

- **Good:** Immediate quality signal with zero additional LLM calls.
- **Good:** The formula is transparent and debuggable (each component visible).
- **Good:** Becomes the fitness function for the future Experimentation Engine.
- **Bad:** The formula is a proxy. A colony can score high while producing
  mediocre output if it converges quickly and doesn't trigger warnings.
- **Acceptable:** Proxy metrics are standard practice. The research shows that
  convergence speed, governance intervention frequency, and stall rate correlate
  well with output quality for well-defined tasks. For subjective tasks, post-
  alpha LLM-as-judge can be layered on top without replacing this formula.

## FormicOS Impact

Affects: `surface/colony_manager.py` (score computation), `surface/projections.py`
(new field on ColonyProjection), `surface/view_state.py` (include in snapshot),
`frontend/src/types.ts` (mirror field), `frontend/src/components/queen-overview.ts`
(render indicator).
