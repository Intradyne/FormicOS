# Wave 38 Team 2 - Internal Benchmarks + Escalation Matrix

## Role

You own the internal-proof track of Wave 38.

Your job is to:

- extend the Wave 37 harness into harder external-style task slices
- preserve clean ablation reporting
- and build the escalation outcome matrix that Wave 39 depends on

This is the "prove it internally before the public claim" track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_38/wave_38_plan.md`
4. `docs/waves/wave_38/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `tests/integration/test_wave37_stigmergic_loop.py`
7. `src/formicos/surface/projections.py`
8. `src/formicos/surface/routes/api.py`
9. `src/formicos/engine/runner.py`

## Coordination rules

- These are internal benchmarks, not public leaderboard claims.
- Reuse and extend the Wave 37 harness; do not throw it away.
- Do **not** implement auto-escalation in Wave 38.
- Do **not** mix provider fallback with capability escalation.
- The escalation outcome matrix must read from governance-owned
  `routing_override` truth, not hidden router behavior.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `tests/integration/test_wave37_stigmergic_loop.py` | MODIFY | additive benchmark extensions only if they keep the existing harness clear |
| `tests/integration/test_wave38_benchmarks.py` | CREATE | external-style internal benchmark slices |
| `tests/integration/test_wave38_escalation_matrix.py` | CREATE | escalation matrix coverage |
| `src/formicos/surface/projections.py` | OWN | replay-derived escalation outcome matrix support |
| `src/formicos/surface/routes/api.py` | MODIFY | additive read-only reporting surface if needed |
| `docs/waves/wave_38/internal_benchmarking.md` | CREATE | scope, metrics, and interpretation notes |

## DO NOT TOUCH

- `src/formicos/core/*`
- `src/formicos/engine/service_router.py` - Team 1 owns
- `src/formicos/surface/routes/a2a.py` - Team 1 owns
- `src/formicos/surface/routes/protocols.py` - Team 1 owns
- `src/formicos/surface/admission.py` - Team 3 owns
- `src/formicos/surface/knowledge_catalog.py` - Team 3 owns
- `src/formicos/surface/federation.py` - Team 3 owns
- `src/formicos/surface/trust.py` - Team 3 owns
- `src/formicos/adapters/knowledge_graph.py` - Team 3 owns
- `frontend/src/components/knowledge-browser.ts` - Team 3 owns

## Overlap rules

- `src/formicos/surface/projections.py`
  - You own escalation outcome matrix additions.
  - Team 3 may need additive temporal metadata elsewhere in this file.
  - If both land, reread before merge.
- `src/formicos/surface/routes/api.py`
  - Touch only additive read-only reporting for owned benchmark / matrix
    surfaces.
  - Do not widen unrelated API behavior.

---

## 2A. External-style internal benchmark suite

Build a stronger internal harness without turning the repo into a giant
benchmark runner.

### Required scope

1. Preserve the Wave 37 repeated-domain harness.
2. Add bounded HumanEval-style and SWE-bench-style task slices.
3. Report:
   - success
   - quality
   - cost
   - wall time
   - retrieval cost where available
4. Keep the suite reproducible and small enough to run locally.

### Hard constraints

- Do not market this as a public benchmark result.
- Avoid giant brittle benchmark scaffolding.
- Keep the results interpretable by another engineer reading the repo later.

### What success looks like

The benchmark suite can distinguish baseline / Wave 37 / Wave 38-relevant
configurations on harder task slices.

---

## 2B. Escalation outcome matrix

This is a Wave 39 dependency and must be clean.

### Required scope

For each relevant colony, be able to report:

- domain or task family
- starting tier
- escalated tier if any
- reason
- round at override
- total cost
- wall time
- quality score
- final outcome

Implementation note: `ColonyOutcome` in `src/formicos/surface/projections.py`
does not currently carry escalation fields. You will need to either extend that
replay-derived outcome shape with optional escalation fields or build a clearly
named separate derived view from `ColonyProjection.routing_override` plus final
outcome truth.

### Hard constraints

- Read from `routing_override` and replay-derived outcome truth.
- Do **not** treat provider fallback as escalation.
- Do **not** add auto-escalation in this wave.

### What success looks like

An escalated colony can be inspected after the fact and the matrix can answer
what changed, when, and what the result was.

---

## 2C. Internal results note

Leave behind enough documentation so Wave 39 can tell what to tune next.

The doc does not need to be a paper. It should answer:

- where the architecture helped
- where it did not
- what should be tuned next

---

## Acceptance targets for Team 2

1. Wave 38 has a bounded internal benchmark suite beyond the original Wave 37
   harness.
2. Benchmark output reports success, quality, cost, and wall time.
3. The escalation outcome matrix exists and reads from replay-safe governance
   truth.
4. Provider fallback is not conflated with capability escalation.
5. No new event types were added.

## Validation

```bash
python scripts/lint_imports.py
python -m pytest -q
```

If you add benchmark fixtures, keep them deterministic or tightly bounded. The
value is in comparative signal, not in scale theater.

## Required report

- exact files changed
- what new benchmark slices were added
- what the benchmark suite now measures
- how the escalation outcome matrix is derived
- how you kept provider fallback out of escalation reporting
- confirmation that no new event types were added
