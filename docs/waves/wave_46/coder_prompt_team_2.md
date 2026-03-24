## Role

You own the measurement-integrity track of Wave 46.

Your job is to make the eval harness honest enough that the product can be
measured without contaminating runs or bluffing about causal knowledge use.

This is **not** permission to turn FormicOS into a benchmark-specific runner.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_46/wave_46_plan.md`
4. `docs/waves/wave_46/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `src/formicos/eval/sequential_runner.py`
7. `src/formicos/eval/compounding_curve.py`
8. `src/formicos/eval/run.py`
9. `src/formicos/eval/compare.py`
10. `src/formicos/surface/transcript.py`
11. `src/formicos/surface/transcript_view.py`
12. `src/formicos/surface/projections.py`
13. `config/eval/suites/default.yaml`
14. `config/eval/tasks/`

## Core rule

Before you land any change, apply this test:

**If the benchmark disappeared tomorrow, would we still want this change in FormicOS?**

For this track, the acceptable answers are:

- yes, because it improves reproducibility, auditability, or honest reporting
- no, then keep it out of product code and out of the harness too

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `src/formicos/eval/sequential_runner.py` | OWN | clean-room isolation, knowledge attribution, richer conditions |
| `src/formicos/eval/compounding_curve.py` | OWN | multi-run aggregation, bounded rigor, attribution analysis |
| `src/formicos/eval/run.py` | OWN | run-manifest support where appropriate |
| `src/formicos/eval/compare.py` | OWN | keep comparison output aligned to richer run truth |
| `config/eval/tasks/` | OWN | task suite expansion |
| `config/eval/suites/` | OWN | pilot/full/benchmark suites |
| `tests/` | CREATE/MODIFY | eval harness, attribution, and suite-loading coverage |

## DO NOT TOUCH

- `src/formicos/surface/routes/` - Team 1 owns product routes
- `src/formicos/surface/app.py` - Team 1 owns app/startup edits
- frontend files - Team 1 owns
- docs packet files in `docs/waves/wave_46/` - Team 3 owns report/documentation scaffolds
- product runtime/planner seams unless you hit a real blocker and escalate

## Hard constraints

- No benchmark-only runtime path in product code.
- No new event types.
- No new subsystem or adapter.
- Prefer reading existing replay-safe truth over inventing new truth.
- Keep the harness thin where possible.

---

## Track A: Clean-room integrity (`Must`)

### Required scope

1. Fix workspace reuse across repeated sequential runs.
2. Make `knowledge_mode` explicit enough to support:
   - `accumulate`
   - `empty`
   - `snapshot`
3. Ensure repeated runs/configs do not contaminate each other.

### Guidance

- Unique run/workspace IDs are the minimum acceptable fix.
- If `empty` mode needs fresh workspace per task, implement that cleanly.
- Do not change production knowledge semantics just to satisfy the harness.

---

## Track B: Real knowledge attribution (`Must`)

### Required scope

1. Populate `knowledge_used` from existing replay-safe access truth.
2. Add `knowledge_produced` or equivalent per-task output truth if needed.
3. Attribute accessed entries back to prior tasks/colonies when possible.

### Guidance

- Start from `knowledge_trace` / `knowledge_accesses`, not a new log path.
- `transcript_view.py` already computes `knowledge_used` and
  `knowledge_produced` from colony projection data. Use or adapt that logic
  rather than rebuilding attribution from scratch.
- Prefer a structured shape over a bare list of IDs if that makes attribution
  and later analysis more truthful.
- This is the backbone of the audit demo and the compounding argument.

### Explicitly keep out

- no new attribution subsystem
- no product event changes just for eval

---

## Track C: Conditions, manifests, and bounded statistical rigor (`Must` / `Should`)

### Must

1. Expand `ExperimentConditions` to support:
   - richer knowledge mode
   - foraging policy
   - random seed
   - run ID
   - commit/config truth
2. Write a manifest beside each run result.

### Should

If you land multi-run reporting now:

1. keep it bounded
2. base it on actual run artifacts
3. prefer bootstrap/paired comparison utilities over a bespoke analysis stack

If this starts turning into a research framework, stop and report the boundary.

---

## Track D: Task suite expansion (`Should`)

### Required scope

Add the suite structure needed for the phased plan:

- `pilot`
- `full`
- `benchmark`

### Guidance

- Category A: language breadth
- Category B: multi-file depth
- Category C: compounding clusters

Do not pad the suite with filler just to hit a number. The ordering and
purpose of each task should be legible.

---

## Validation

Run, at minimum:

1. `python scripts/lint_imports.py`
2. targeted pytest for:
   - sequential runner
   - compounding curve
   - any new suite/task loaders
   - attribution logic
3. full `python -m pytest -q` if your changes alter shared eval data shapes

## Summary must include

- how clean-room isolation now works
- what shape `knowledge_used` now has and where it comes from
- what new condition/manifest fields were added
- whether multi-run/bootstrap analysis landed or stayed deferred
- what suite expansion actually landed
- what you explicitly kept out to avoid benchmark-only debt
