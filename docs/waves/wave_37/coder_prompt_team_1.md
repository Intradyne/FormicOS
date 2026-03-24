# Wave 37 Team 1 - Stigmergic Loop Closure + Measurement

## Role

You own the architectural core of Wave 37.

Your job is to close the stigmergic loop between:

- Layer 1: short-term intra-colony pheromone routing
- Layer 2: long-term inter-colony knowledge traces

You also own the minimum measurement infrastructure needed to prove whether the
new loop actually helps.

This is the "make the thesis true and measurable" track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_37/wave_37_plan.md`
4. `docs/waves/wave_37/acceptance_gates.md`
5. `docs/research/stigmergy_knowledge_substrate_research.md`

## Coordination rules

- This prompt and the Wave 37 docs override stale older assumptions.
- No new event types. The union stays at 55.
- Do not modify `src/formicos/core/*`.
- In particular: do **not** modify `ColonyContext` in `core/types.py` for 1A.
- Team 2 shares `surface/knowledge_catalog.py` for trust/provenance surfacing.
- Team 3 shares `surface/proactive_intelligence.py` for adaptive-evaporation
  recommendations and may touch `surface/knowledge_catalog.py` only if Pillar 5
  stretch work lands.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `src/formicos/engine/strategies/stigmergic.py` | OWN | 1A knowledge-weighted topology initialization via optional runtime prior |
| `src/formicos/engine/runner.py` | OWN | 1A prior computation / handoff, 1C branching metrics if runner-side support is needed |
| `src/formicos/surface/colony_manager.py` | OWN | 1B outcome-weighted confidence updates |
| `src/formicos/surface/knowledge_catalog.py` | MODIFY | Team 1 owns scoring/retrieval semantics only |
| `src/formicos/surface/proactive_intelligence.py` | MODIFY | Team 1 owns branching diagnostics only |
| `tests/unit/engine/test_strategies.py` | MODIFY | 1A coverage |
| `tests/unit/engine/test_runner.py` | MODIFY | 1A / 1C coverage where appropriate |
| `tests/unit/surface/test_colony_manager.py` | MODIFY | 1B coverage |
| `tests/unit/surface/test_wave37_branching.py` | CREATE | 1C focused tests |
| `tests/integration/test_wave37_stigmergic_loop.py` | CREATE | repeated-domain benchmark harness / ablation support |

## DO NOT TOUCH

- `src/formicos/core/*`
- `src/formicos/surface/projections.py` - Team 3 owns
- `src/formicos/surface/queen_runtime.py` - Team 3 owns
- `src/formicos/surface/proactive_intelligence.py` outside 1C branching work
- `src/formicos/surface/knowledge_catalog.py` trust/provenance surfacing - Team 2 owns
- `.github/*` - Team 2 owns
- `SECURITY.md` - Team 2 owns
- `GOVERNANCE.md` - Team 2 owns
- `CODE_OF_CONDUCT.md` - Team 2 owns
- `CONTRIBUTING.md` - Team 2 owns
- frontend trust/provenance display files - Team 2 owns

## Overlap rules

- `src/formicos/surface/knowledge_catalog.py`
  - You own retrieval/scoring behavior only.
  - Team 2 owns trust/provenance metadata surfacing.
  - If Team 3 ships Pillar 5, they own only additive triple-tier prefilter /
    escalation logic.
- `src/formicos/surface/proactive_intelligence.py`
  - You own branching diagnostics only.
  - Team 3 owns adaptive-evaporation recommendations.

---

## 1A. Knowledge-weighted topology initialization

This item must use the engine-layer seam clarified by the Wave 37 cloud audit.

### Required implementation shape

1. Compute a runtime
   `knowledge_prior: dict[tuple[str, str], float] | None`
   in `engine/runner.py` immediately before topology resolution.
   The `knowledge_items` parameter on `run_round(...)` already contains the
   retrieved entries with confidence and domain data; use that existing round
   input to compute the prior before calling `resolve_topology(...)`.
2. Extend `StigmergicStrategy.resolve_topology(...)` with an optional
   `knowledge_prior` parameter.
3. Apply the multiplicative prior to the similarity matrix before thresholding:
   `sim_ij <- sim_ij * prior_ij`
4. Keep the prior narrow, such as `[0.85, 1.15]`.

### Hard constraints

- Do **not** add a field to `ColonyContext`.
- Do **not** touch the core layer.
- Keep this as a runtime prior derived from retrieval state already available to
  the round.
- Surface enough debug information that the bias can be inspected or asserted in
  tests.

### What success looks like

- repeated-domain colonies no longer always begin from a neutral social graph
- tests can prove that a non-neutral `knowledge_prior` actually affects the
  resolved topology

---

## 1B. Outcome-weighted knowledge reinforcement

The current reinforcement loop is too coarse.

### Required implementation shape

1. Replace constant success/failure updates with clipped quality-aware deltas.
2. Preserve priors, decay, and the current event model.
3. Thread `quality_score: float` into the confidence-update hook from the
   colony-finalization path.

### Critical seam

The current `_hook_confidence_update(...)` hook in `colony_manager.py` receives
`succeeded: bool`, not a quality score.

You must:

1. add `quality_score: float` to that hook
2. pass it from the colony-finalization path where quality is already known
3. use that float to drive the weighted update

Without this, the plan cannot actually be implemented.

### Constraints

- No new event types
- Use existing `MemoryConfidenceUpdated`
- Keep deltas bounded
- Do not break replay assumptions

### What success looks like

- higher-quality successful colonies reinforce accessed entries more than
  marginal successes
- tests can prove the delta is no longer a flat `+1`

---

## 1C. Branching-factor stagnation diagnostics

Add a real diagnostic for narrowing search breadth.

### Minimum scope

Support metrics for:

1. topology branching factor
2. knowledge branching factor
3. configuration branching factor

Generate diagnostics only when:

- branching is low
- and failures/warnings are rising
- and the same entries or configurations dominate recent work

### Constraints

- read-model diagnostic only
- no new event types
- keep the signal explainable, not a black box metric blob

### What success looks like

- an operator or test can see a warning before obvious repetitive failure
  patterns fully emerge

---

## 3A / 3B. Measurement infrastructure

Build the minimum harness needed to prove whether 1A/1B/1C helped.

### Required scope

- repeated-domain task suite
- outcome calibration checks
- retrieval-cost instrumentation hooks or assertions
- basic ablation support across:
  - Wave 36 baseline
  - +1A
  - +1B
  - +1C

This does **not** need to become a publishable benchmark suite in Wave 37.
It does need to leave behind a credible internal instrument.

### Constraints

- keep it lightweight enough to run in repo CI/dev workflows
- avoid giant brittle benchmarking machinery
- favor deterministic or tightly-bounded fixtures over sprawling benchmark code

---

## Acceptance targets for Team 1

1. `resolve_topology()` accepts an optional runtime `knowledge_prior`.
2. The prior is computed in `runner.py`, not by modifying core types.
3. Confidence reinforcement is quality-aware, not flat.
4. `quality_score` is explicitly threaded into the confidence-update hook.
5. Branching diagnostics are implemented and testable.
6. A lightweight internal harness exists to compare Wave 36 baseline vs Wave 37
   stigmergic changes.
7. No new event types were added.

## Validation

```bash
python scripts/lint_imports.py
uv run ruff check src/formicos/engine/strategies/stigmergic.py src/formicos/engine/runner.py src/formicos/surface/colony_manager.py src/formicos/surface/knowledge_catalog.py src/formicos/surface/proactive_intelligence.py tests/unit/engine/test_strategies.py tests/unit/engine/test_runner.py tests/unit/surface/test_colony_manager.py tests/unit/surface/test_wave37_branching.py tests/integration/test_wave37_stigmergic_loop.py
python -m pytest -q
```

## Required report

- exact files changed
- how 1A was implemented, including the `knowledge_prior` injection seam
- confirmation that `ColonyContext` and `core/` were not modified
- how `quality_score` was threaded into confidence updates for 1B
- what branching metrics landed for 1C
- what the benchmark harness measures
- confirmation that no new event types were added
