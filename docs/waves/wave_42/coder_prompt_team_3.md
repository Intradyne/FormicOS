## Role

You own the adaptive runtime-control track of Wave 42.

Your job is to:

- replace fixed evaporation with bounded adaptive runtime behavior
- keep the logic local to the runner path
- improve stagnation handling without destabilizing the normal path

This is the "runtime gets smarter under stagnation" track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_42/wave_42_plan.md`
4. `docs/waves/wave_42/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `src/formicos/engine/runner.py`
7. `src/formicos/surface/proactive_intelligence.py`
8. `tests/unit/engine/`

## Coordination rules

- Keep the control logic inside `runner.py`.
- Reuse the same branching concepts already proven useful in diagnostics, but
  do **not** make runtime behavior depend on briefing/reporting code paths.
- Engine cannot import from surface. Re-implement the branching-factor math
  (`exp(entropy)` over pheromone weights) as a runner-local helper rather than
  importing it from `proactive_intelligence.py`.
- Adaptive evaporation is the Must-ship core of this track.
- Any smoothing or reinforcement refinements are optional and must remain
  bounded.
- Keep this work independent of the current sandbox/container backend so Wave
  43 hardening does not have to undo it.
- Do **not** turn this into a governance-policy redesign.
- Do **not** touch static-analysis or contradiction/extraction seams owned by
  the other teams.
- Do **not** add event types.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `src/formicos/engine/runner.py` | OWN | `_update_pheromones` and adjacent stagnation-control logic |
| `tests/unit/engine/test_wave42_adaptive_evaporation.py` | CREATE | adaptive control tests |
| `tests/integration/test_wave42_stagnation_recovery.py` | CREATE | only if a bounded integration check is needed |

## DO NOT TOUCH

- `src/formicos/adapters/code_analysis.py` - Team 1 owns
- `src/formicos/surface/conflict_resolution.py` - Team 2 owns
- `src/formicos/surface/colony_manager.py` - Teams 1 and 2 own their separate
  seams there
- `src/formicos/surface/proactive_intelligence.py` - read for concepts only,
  do not make it the runtime owner
- frontend files and wave docs - not this track

## Overlap rules

- Team 1 owns `_compute_knowledge_prior()` in `runner.py`.
  - Stay out of that seam.
- Your ownership is the evaporation / reinforcement control path.
  - Keep edits local.
- If you need new runner-local helper functions, keep them physically close to
  `_update_pheromones()` so the control law stays legible.

---

## Pillar 4: Adaptive evaporation

### Required scope

1. Replace the fully fixed evaporation path with a bounded adaptive one.
2. Use branching / stagnation concepts already supported by the current runner
   and diagnostics vocabulary.
3. Preserve normal behavior when the colony is not stagnating.

### Optional scope

Only if adaptive rate alone is clearly insufficient:

- bounded pheromone smoothing
- bounded reinforcement-mode refinements

### Hard constraints

- Do **not** make the control law so complex that nobody can reason about it.
- Do **not** couple runtime behavior to briefing-generation code.
- Do **not** silently broaden this into a full governance rewrite.

---

## Developmental eval

Include a small before/after eval on tasks known to exhibit stagnation-like
behavior.

Report:

- whether adaptive evaporation changed the colony's search behavior
- whether repetitive low-value patterns broke sooner
- whether healthy runs remained stable

This is a development check, not a publication artifact.

---

## Validation

Run, at minimum:

1. `python scripts/lint_imports.py`
2. targeted pytest for runner control-law behavior
3. full `python -m pytest -q` if the runtime seam broadens beyond the local
   pheromone update path

Your summary must include:

- how the new evaporation behavior works
- whether smoothing or other optional refinements landed
- what you rejected to keep the control law simple
