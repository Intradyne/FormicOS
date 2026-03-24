# ADR-012: Caste-Phase Compute Router

**Status:** Proposed
**Date:** 2026-03-13

## Context

The `LLMRouter` in `surface/runtime.py` routes LLM calls by provider prefix only.
Every agent call uses the statically-assigned model from the nullable cascade
(thread → workspace → system default, ADR-009). A reviewer doing structured text
comparison uses the same $15/MTok Claude Sonnet that a coder writing complex code
uses. There is no intelligence in the routing — every agent call is equally expensive.

Wave 8 delivered real cost tracking (ADR-009) and quality scoring (ADR-011). These
make it possible to measure the cost impact of routing decisions and the quality
impact of using cheaper models for simpler work.

Research (FrugalGPT, Stanford 2023; Hybrid LLM, ICLR 2024; RouteLLM, ICLR 2025)
converges on a clear finding: the gap between "no routing" and "rule-based routing"
is enormous (40–98% cost reduction with <2% quality loss). The gap between
"rule-based routing" and "ML-based routing" requires thousands of labeled production
decisions to exploit. Start with rules.

## Decision

Model selection uses a **(phase, caste) → model_address** routing table loaded from
`config/formicos.yaml`. The engine receives a `route_fn` callable and never imports
settings or config directly. The routing table is a static heuristic — no ML, no
learned weights, no training data required.

### Routing Table Schema

```yaml
routing:
  model_routing:            # dict keyed by PhaseName
    execute:                # Phase 4 — where agents do their main LLM work
      queen: "anthropic/claude-sonnet-4.6"
      coder: "anthropic/claude-sonnet-4.6"
      reviewer: "llama-cpp/gpt-4"
      researcher: "llama-cpp/gpt-4"
      archivist: "llama-cpp/gpt-4"
    goal:                   # Phase 1 — strategic goal-setting
      queen: "anthropic/claude-sonnet-4.6"
    # Phases not listed inherit the cascade default for all castes.
    # Castes not listed under a phase inherit the cascade default.
```

The table is intentionally sparse. Only override where the cost-quality tradeoff
matters. Missing entries are not errors — they fall through to the existing cascade.

### Decision Order (evaluated top to bottom, first match wins)

1. **Budget gate.** If `budget_remaining < $0.10`, return the cheapest registered
   model (lowest `cost_per_input_token`). This prevents the routing table from
   causing budget overruns.
2. **Routing table lookup.** Look up `model_routing[phase][caste]`. If found and
   the value is not null, select that model.
3. **Adapter check.** If the selected model's provider prefix has no registered
   adapter, fall back to the cascade default. Never crash on a misconfigured
   routing entry.
4. **Cascade default.** Return `default_model` (the static cascade resolution).

### Layer Boundary

The engine layer (`engine/runner.py`) does not import settings, config, or
routing tables. It receives a callable:

```python
route_fn: Callable[[str, str, int, float], str] | None
# Arguments: (caste, phase, round_num, budget_remaining) → model_address
```

The surface layer (`surface/runtime.py`) constructs this function from settings
and passes it to `RoundRunner.__init__()`. When `route_fn` is None, the runner
uses the static `agent.model` (existing behavior).

### Observability

Every routing decision is logged via structlog:

```
compute_router.route caste=coder phase=execute round_num=3
    selected=anthropic/claude-sonnet-4.6 reason=routing_table budget_remaining=0.85
```

The `reason` field is one of: `budget_gate`, `routing_table`, `adapter_fallback`,
`cascade_default`.

Colony observation hooks (structlog, not event-sourced) log the full execution
signature at colony completion for future analysis and template extraction.

### No New Events

Routing decisions are runtime observability, not domain state. They are logged
via structlog, not persisted in the event store. The `AgentTurnStarted.model`
field (which already exists in the event contract) is populated with the routed
model address, giving replay visibility into which model was actually used.

## Consequences

- **Good:** 40–60% cloud cost reduction with zero additional dependencies.
  Reviewers and archivists route to free local models. Only Queen goal-setting
  and coder execution use expensive cloud models.
- **Good:** Pure YAML config — operator can tune routing without code changes.
- **Good:** Budget gate prevents runaway cloud spend.
- **Good:** Generates structured routing decision data that the Experimentation
  Engine (Wave 10) will use to test and improve routing policies.
- **Bad:** The routing table is a heuristic. "Reviewer → local" may be wrong for
  some tasks. The operator must monitor quality scores to catch this.
- **Bad:** No automatic escalation on local model failure. If the local model
  produces garbage, the colony will score poorly. Future work (Wave 10+) adds
  quality-based escalation.
- **Acceptable:** Conservative defaults (cloud for queen/coder) mean the worst
  case is identical to the current behavior. The routing table only makes things
  cheaper, never worse, unless the operator overrides queen/coder to local.

## What This ADR Does NOT Cover

- ML-based routing or learned routing policies (Wave 11+)
- Gemini as a third routing tier (Wave 10)
- Automatic quality-based escalation (Wave 10+, requires Experimentation Engine)
- VRAM-aware scheduling (post-alpha, requires local inference metrics)

## FormicOS Impact

Affects: `engine/runner.py` (route_fn parameter), `surface/runtime.py` (LLMRouter.route),
`core/settings.py` (RoutingConfig model), `config/formicos.yaml` (routing table).
Reads: `core/ports.py` (LLMPort), `core/types.py` (ModelRecord for registry lookup).
No contract changes. No new event types. No new dependencies.
