## Role

You own the epistemic-completion and proof-readiness track of Wave 45.

Your job is to:

- surface Stage 3 competing hypotheses so operators and retrieval can see them
- tighten domain-strategy projection truth
- land agent-level topology prior only if the current planner truth already
  supports it

This is the "make the system more inspectable and proof-ready without opening
new architecture" track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_45/wave_45_plan.md`
4. `docs/waves/wave_45/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `src/formicos/surface/conflict_resolution.py`
7. `src/formicos/surface/projections.py`
8. `src/formicos/surface/knowledge_catalog.py`
9. `src/formicos/engine/runner.py`
10. `src/formicos/core/types.py`
11. `src/formicos/surface/queen_tools.py`

## Coordination rules

- Competing-hypothesis surfacing is a `Must`. Keep it to projection state plus
  retrieval annotation.
- Do **not** add event types for Stage 3.
- Do **not** build new frontend surfaces in this wave.
- Gated topology work only lands if current planner/runtime truth already
  provides usable per-agent or per-group file scope.
- If the topology gate fails, document it and stop. Do **not** redesign the
  planner to make the item fit.
- Domain-strategy tuning is small refinement work, not a second major feature.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `src/formicos/surface/conflict_resolution.py` | MODIFY | only if a bounded helper or clearer competing metadata is needed |
| `src/formicos/surface/projections.py` | OWN | competing-hypothesis state + domain-strategy tuning |
| `src/formicos/surface/knowledge_catalog.py` | OWN | competing-context retrieval annotation |
| `src/formicos/engine/runner.py` | OWN | gated agent-level topology prior only if data truth exists |
| `tests/` | CREATE/MODIFY | contradiction, projection, retrieval, and topology tests |

## DO NOT TOUCH

- `src/formicos/surface/proactive_intelligence.py` - Team 1 owns proactive wiring
- `src/formicos/surface/forager.py` - Team 1 owns
- `src/formicos/adapters/content_quality.py` - Team 1 owns credibility work
- `src/formicos/surface/app.py` - Team 1 owns optional search consistency
- docs and wave packet files - Team 3 owns documentation truth

---

## Bucket 2A: Competing hypothesis surfacing

### Required scope

1. Make Stage 3 "competing" outcomes visible in replay-derived state.
2. Annotate retrieval results with the competing relationship.
3. Keep the operator path legible without requiring transcript archaeology.

### Hard constraints

- Do **not** add event types.
- Do **not** add a broad new contradiction-management subsystem.
- Do **not** broaden this into frontend work.

### Guidance

- `resolve_classified()` already returns `Resolution.competing`; use that
  existing truth rather than recreating contradiction logic elsewhere.
- The contradiction detection that produces `Resolution.competing` already
  happens in `proactive_intelligence._rule_contradiction()`, which Team 1
  owns for a different concern. Read those results through the existing
  briefing/insight path to update projection state. Do **not** modify the
  detection logic in that file.
- Projection tracking such as `competing_with` or equivalent linked state is
  the right target.
- Retrieval annotation should be enough for the audit story: "this entry has a
  competing alternative, here is the other ID / summary / confidence context."

---

## Bucket 3A: Agent-level topology prior (`Gated`)

### Gate

Only proceed if the current planner/runtime seam already provides per-agent or
per-group file scope that `_compute_structural_affinity()` can consume.

### If the gate passes

1. tighten the prior from colony-level to agent-level or group-level
2. keep the change local to the current runner seam
3. preserve the neutral fallback when the data is absent

### If the gate fails

- stop, document the reason, and leave the prior colony-level

### Hard constraints

- Do **not** redesign Queen planning.
- Do **not** change event or tool surfaces to force this in.

---

## Bucket 3B: Domain-strategy projection tuning

### Required scope

1. Improve domain-strategy projection truth if counts are lagging behind
   reality.
2. Keep the change event-compatible and small.

### Hard constraints

- Do **not** change the event surface.
- Do **not** turn this into a separate domain-analytics subsystem.

---

## Validation

Run, at minimum:

1. `python scripts/lint_imports.py`
2. targeted pytest for contradiction, projection, retrieval, and runner seams
3. full `python -m pytest -q` if your changes broaden across shared lifecycle
   or topology surfaces

## Developmental evidence

Your summary must include:

- how competing hypotheses are now surfaced in projections and retrieval
- whether the topology gate passed or failed, and why
- what domain-strategy tuning landed
- what you explicitly kept out to preserve the bounded scope
