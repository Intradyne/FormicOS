## Role

You own the measurement and optimization track of Wave 41.

Your job is to:

- make the compounding curve measurable and credible
- keep evaluation truth publishable whether results are strong or weak
- improve cost / performance behavior only where the measurement supports it

This is the "measure whether the shared brain is actually learning" track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_41/wave_41_plan.md`
4. `docs/waves/wave_41/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `tests/benchmark/profiling_harness.py`
7. `tests/benchmark/*`
8. `src/formicos/eval/*`
9. `src/formicos/surface/knowledge_catalog.py`
10. `src/formicos/surface/proactive_intelligence.py`
11. `src/formicos/engine/runner.py`

## Coordination rules

- The compounding curve is the most important output of this wave.
- Your measurement path must be useful if the curve rises **or** stays flat.
- Lock and record experiment conditions tightly enough that later gains cannot
  be dismissed as drift in budgets, order, or escalation policy.
- Do **not** turn Wave 41 into a benchmark-only product path.
- Cost optimization is subordinate to measurement truth.
- Do **not** touch the primary execution substrate owned by Team 2 except where
  a measurement hook truly needs it.
- Do **not** push contradiction work past bounded follow-up stages unless Team 1
  has already stabilized the unified path.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `tests/benchmark/*` | OWN | sequential runner, experiment fixtures, reporting outputs |
| `src/formicos/eval/*` | OWN | evaluation utilities and run metadata |
| `src/formicos/surface/knowledge_catalog.py` | MODIFY | retrieval metrics / contribution tracking only |
| `src/formicos/surface/proactive_intelligence.py` | OWN | cost / performance reporting surfaces |
| `src/formicos/engine/runner.py` | MODIFY | only if a bounded metric hook is required |
| `docs/waves/wave_41/*` | DO NOT MODIFY | packet docs are not your deliverable |
| `tests/unit/benchmark/test_wave41_sequential_runner.py` | CREATE | locked-condition measurement tests |
| `tests/integration/test_wave41_compounding_curve.py` | CREATE | end-to-end curve behavior tests |
| `tests/unit/surface/test_wave41_cost_reporting.py` | CREATE | optimization reporting tests |

## DO NOT TOUCH

- `src/formicos/surface/trust.py` - Team 1 owns
- `src/formicos/engine/context.py` - Team 1 owns
- `src/formicos/surface/conflict_resolution.py` - Team 1 owns initially
- `src/formicos/adapters/sandbox_manager.py` - Team 2 owns
- `src/formicos/engine/tool_dispatch.py` - Team 2 owns
- frontend files and product docs - not this track

## Overlap rules

- Team 1 owns math bridges.
  - If they change retrieval score composition or contradiction outputs, reread
    `knowledge_catalog.py` and `proactive_intelligence.py` before finalizing.
- Team 2 owns execution.
  - Your harness should consume their execution truth rather than inventing a
    side-channel runner unless the existing path truly cannot support locked
    experiments.
- If later contradiction stages are touched here, keep them strictly bounded
  and only after Team 1's stages 1-2 are stable.

---

## B3. Compounding-curve infrastructure

### Required scope

1. Build or strengthen a sequential task runner that reuses one workspace's
   accumulated knowledge across many tasks.
2. Measure the compounding curve in three ways:
   - raw performance
   - cost-normalized performance
   - time-normalized performance
3. Record experiment conditions tightly enough that outsiders can understand
   what stayed fixed.
4. Track which earlier knowledge was retrieved and used on later tasks where
   that contribution can be measured honestly.

### Hard constraints

- Do **not** let model mix, ordering, budget policy, or escalation policy drift
  silently inside one reported curve.
- Do **not** hide flat or negative results.

---

## B4. Cost optimization

### Required scope

1. Improve cost-awareness where the data justifies it.
2. Keep reporting legible enough to answer:
   - what did the task cost?
   - what did the success buy us?
   - when should the colony stop earlier versus spend more?

### Hard constraints

- Do **not** optimize in ways that destroy comparability across sequential runs.
- Do **not** let caching or early stopping make the measurement dishonest.

---

## Optional follow-up contradiction scope

Only after Team 1 stabilizes the contradiction pipeline:

- limited contribution to later-stage hypothesis / evidence reporting
- only if the measurement harness genuinely needs it

Do not take ownership of the contradiction rewrite by default.

---

## Validation

Run, at minimum:

1. `python scripts/lint_imports.py`
2. targeted pytest for benchmark / eval / measurement seams
3. full `python -m pytest -q` if the harness or metric hooks touch shared
   runtime paths broadly

Your summary must include:

- how sequential runs are locked and recorded
- where raw, cost-normalized, and time-normalized curves are produced
- what knowledge contribution signal is measured
- what optimization changes landed and what you rejected to preserve validity
