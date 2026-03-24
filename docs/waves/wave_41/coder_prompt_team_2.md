## Role

You own the execution and multi-file capability track of Wave 41.

Your job is to:

- make FormicOS materially stronger at real repo-backed work
- separate workspace execution concerns from sandbox isolation concerns
- improve multi-file coordination and validation without creating a
  benchmark-specific path

This is the "make the colony actually capable on hard code work" track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_41/wave_41_plan.md`
4. `docs/waves/wave_41/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `src/formicos/adapters/sandbox_manager.py`
7. `src/formicos/engine/tool_dispatch.py`
8. `src/formicos/engine/runner.py`
9. `src/formicos/surface/colony_manager.py`
10. `src/formicos/surface/queen_runtime.py`
11. `src/formicos/surface/queen_tools.py`

## Coordination rules

- Keep product-general capability as the goal. Do **not** invent a benchmark
  adapter or a second execution path.
- Treat workspace execution and sandbox execution as different concerns.
- Prefer one coherent execution lifecycle over a pile of narrow helper tools.
- If you add bounded tool-surface changes, keep them honest and reusable for
  ordinary operator tasks.
- Do **not** redesign colony planning from scratch when a bounded extension of
  the existing Queen / colony flow will do.
- Do **not** touch trust weighting or contradiction math files owned by Team 1.
- Do **not** own the compounding-curve harness or reporting path; Team 3 owns
  that.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `src/formicos/adapters/sandbox_manager.py` | OWN | sandbox isolation improvements only where still necessary |
| `src/formicos/engine/tool_dispatch.py` | OWN | repo/workspace execution handlers, structured result path |
| `src/formicos/engine/runner.py` | MODIFY | validator registration / execution integration only |
| `src/formicos/surface/colony_manager.py` | OWN | workspace lifecycle, working-directory truth |
| `src/formicos/surface/queen_runtime.py` | MODIFY | file-aware planning / coordination if justified |
| `src/formicos/surface/queen_tools.py` | MODIFY | only if a Queen tool seam must expose the improved capability |
| `tests/unit/engine/test_wave41_execution_surface.py` | CREATE | execution-path tests |
| `tests/integration/test_wave41_multifile_coordination.py` | CREATE | multi-file capability tests |
| `tests/integration/test_wave41_cross_file_validation.py` | CREATE | cross-file validator tests |

## DO NOT TOUCH

- `src/formicos/surface/trust.py` - Team 1 owns
- `src/formicos/engine/context.py` - Team 1 owns
- `src/formicos/surface/conflict_resolution.py` - Team 1 owns
- `tests/benchmark/*` - Team 3 owns
- evaluation / reporting docs - Team 3 owns
- frontend files - not this track

## Overlap rules

- Team 1 is tightening retrieval trust and contradiction seams.
  - Do not bake in assumptions that depend on the old trust / contradiction
    paths staying exactly as they were.
- Team 3 owns sequential measurement.
  - If you change execution result shapes or runtime metadata, leave a clear
    note so the measurement harness can consume them.
- If `runner.py` changes are broad enough to overlap with Team 1, reread the
  final `runner.py` before merge and preserve their math seam changes.

---

## B1. Production-grade execution surface

### Required scope

1. Strengthen repo-backed workspace execution so the colony can operate on real
   code tasks more cleanly than the current Python-only path allows.
2. Distinguish:
   - workspace / repo lifecycle
   - sandboxed code execution
3. Provide structured failure output for the main supported execution paths so
   retries can reason about what failed.
4. Keep the capability usable for normal operator tasks such as refactors, test
   writing, and debugging.

### Hard constraints

- Do **not** introduce a benchmark-only adapter.
- Do **not** fork task truth away from the existing colony execution path.
- Do **not** make git / repo handling the only way code tasks can run.

---

## B2. Multi-file task coordination

### Required scope

1. Make multi-file work more file-aware than the current generic colony
   decomposition.
2. Use the existing Queen / colony architecture rather than inventing a
   disconnected planner.
3. Improve the ability of specialists working on related files to coordinate
   through the shared substrate.

### Hard constraints

- Do **not** build an entirely separate "benchmark planner."
- Keep the new behavior inspectable through existing colony truth where
  practical.

---

## B3. Cross-file validation

### Required scope

1. Add a validator or equivalent execution truth that can judge whether a
   multi-file change is coherently complete.
2. Make the validator work against real changed-file sets or equivalent task
   scope, not just one-file success heuristics.
3. Keep validation truthful when execution is partial or inconclusive.

### Hard constraints

- Do **not** overclaim success on partial repo state.
- Do **not** conflate "a command ran" with "the code task is complete."

---

## Validation

Run, at minimum:

1. `python scripts/lint_imports.py`
2. targeted pytest for execution and multi-file seams
3. full `python -m pytest -q` if the execution path changes broadly enough

Your summary must include:

- what execution lifecycle was strengthened
- how workspace and sandbox concerns are separated
- what structured failure output now exists
- how multi-file coordination improved
- how cross-file validation decides pass / inconclusive / fail
