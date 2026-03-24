# ADR-009: Real Cost Tracking from Model Registry

**Status:** Proposed
**Date:** 2026-03-13

## Context

`runner.py` hardcodes `estimated_cost = 0.0` for every agent turn. The
`TokensConsumed` event has a `cost` field that always reads `0.0`. The
`ColonyProjection.cost` accumulates these zeros. The budget check in
`colony_manager.py` (`colony.cost >= colony.config.budget_limit`) is
effectively dead code — it never fires because cost never accumulates.

Meanwhile, `core/types.py` already defines `ModelRecord` with
`cost_per_input_token` and `cost_per_output_token` fields (both `float | None`).
The model registry in `formicos.yaml` can carry these rates.

## Decision

Cost is computed from **model registry rates applied at the point of token
consumption in the runner**. The formula is simple multiplication:

```
cost = (input_tokens * cost_per_input_token) + (output_tokens * cost_per_output_token)
```

### Rate Source

Rates are declared per model in `formicos.yaml`:

```yaml
registry:
  - address: "llama-cpp/gpt-4"
    cost_per_input_token: 0.0
    cost_per_output_token: 0.0
    # ... other fields

  - address: "anthropic/claude-sonnet-4.6"
    cost_per_input_token: 0.000003    # $3.00 per 1M input tokens
    cost_per_output_token: 0.000015   # $15.00 per 1M output tokens
    # ... other fields

  - address: "anthropic/claude-haiku-4.5"
    cost_per_input_token: 0.0000008   # $0.80 per 1M input tokens
    cost_per_output_token: 0.000004   # $4.00 per 1M output tokens
    # ... other fields
```

Local models (llama-cpp, ollama) have rate 0.0. The hardware is a sunk cost.

### Rate Resolution

The runner needs access to model rates at agent turn time. Two approaches:

**Option A (chosen):** Pass a `cost_fn: Callable[[str, int, int], float]` into
`RoundRunner.__init__` alongside `emit` and `embed_fn`. The surface layer
constructs this function from the model registry at startup. The engine layer
never imports settings or the registry directly — it receives a function.

**Option B (rejected):** Pass the full settings/registry into the runner. This
violates the layer boundary — engine should not depend on surface-layer config
objects.

### Budget Enforcement

With real costs flowing, `colony_manager.py` can enforce budget limits:

1. After each `RoundResult`, accumulate `total_cost += result.cost`.
2. If `total_cost >= colony.budget_limit`, emit `ColonyFailed` with
   reason `"Budget exhausted ($X.XX of $Y.YY limit)"`.
3. Budget check happens AFTER the round completes (not mid-round). Stopping
   mid-round wastes the work already done and leaves incomplete state.

### Cost in Events

The existing `TokensConsumed` event already has all required fields. The
`RoundCompleted` event already has `cost: float`. Both just need real values
instead of `0.0`.

## Consequences

- **Good:** Budget limits actually work. Operators can set meaningful limits.
- **Good:** Cost-per-colony metric becomes available for the Experimentation
  Engine's fitness function.
- **Good:** The Queen's status digest can include real spend data.
- **Bad:** API rates change. Registry rates will go stale unless manually updated.
- **Acceptable:** At alpha scale, rate staleness is a minor annoyance. The
  Experimentation Engine (future work) will eventually make rate accuracy matter
  more. A `model_rates.yaml` sidecar file is a possible future refinement.

## FormicOS Impact

Affects: `engine/runner.py` (cost_fn injection), `surface/colony_manager.py`
(budget enforcement), `surface/app.py` (cost_fn construction from registry),
`config/formicos.yaml` (rate fields).
Reads: `core/types.py` (ModelRecord — already has cost fields).
