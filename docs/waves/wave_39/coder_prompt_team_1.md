## Role

You own the audit-and-governance track of Wave 39.

Your job is to:

- build the colony reasoning audit surface
- make completion truth more honest across task types
- add bounded governance-owned auto-escalation

This is the "why did this happen, and what did governance do?" track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_39/wave_39_plan.md`
4. `docs/waves/wave_39/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `src/formicos/engine/runner.py`
7. `src/formicos/surface/projections.py`
8. `src/formicos/surface/colony_manager.py`
9. `frontend/src/components/colony-detail.ts`
10. `frontend/src/components/queen-overview.ts`

## Coordination rules

- The audit trail is a read-model / UI track, not a second truth store.
- Do **not** claim exact runtime `knowledge_prior` or retrieval ranking truth
  unless that data is already replay-safe.
- If a datum is reconstructed from available state, label it as explanatory or
  reconstructed rather than exact historical fact.
- Auto-escalation must flow through `routing_override`, not provider fallback.
- Keep provider fallback and capability escalation separate.
- Do **not** touch `core/` in this track.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `src/formicos/engine/runner.py` | OWN | validator dispatch and bounded auto-escalation |
| `src/formicos/surface/projections.py` | OWN | additive audit-view assembly and replay-derivable validator support |
| `src/formicos/surface/colony_manager.py` | MODIFY | only if a small additive seam is needed for validator display/storage |
| `src/formicos/surface/routes/api.py` | MODIFY | additive audit read route only if needed |
| `frontend/src/components/colony-audit.ts` | CREATE | colony reasoning surface |
| `frontend/src/components/colony-detail.ts` | MODIFY | mount audit view and tri-state completion |
| `frontend/src/components/queen-overview.ts` | MODIFY | compact audit / tri-state completion surfaces |
| `tests/unit/engine/test_wave39_validators.py` | CREATE | validator and auto-escalation coverage |
| `tests/unit/surface/test_wave39_audit_view.py` | CREATE | audit-view assembly coverage |

## DO NOT TOUCH

- `src/formicos/core/*` - Team 2 owns the only Wave 39 event expansion
- `src/formicos/surface/knowledge_catalog.py` - Team 2 owns
- `src/formicos/surface/routes/knowledge_api.py` - Team 2 owns
- `frontend/src/components/knowledge-browser.ts` - Team 2 owns
- `src/formicos/surface/proactive_intelligence.py` - Team 3 owns
- `src/formicos/surface/queen_runtime.py` - Team 3 owns
- `frontend/src/components/proactive-briefing.ts` - Team 3 owns
- `frontend/src/components/workflow-view.ts` - Team 3 owns
- `frontend/src/components/config-memory.ts` - Team 3 owns

## Overlap rules

- `src/formicos/surface/projections.py`
  - You own audit-view and validator additions.
  - Team 2 owns operator overlays and annotations.
  - Team 3 owns operator response patterns and config-memory support.
  - Reread before merge.
- `frontend/src/components/queen-overview.ts`
  - You own compact audit and completion-truth additions.
  - Team 3 owns configuration-memory surfaces.
  - Keep your changes additive and reread before merge.
- `src/formicos/surface/routes/api.py`
  - Touch only additive read-only audit surfaces if the frontend truly needs a
    new endpoint.
  - Do not widen unrelated route behavior.

---

## 1A. Colony reasoning audit view

Build a structured colony audit surface from replay-safe truth.

### Required scope

1. Show retrieved knowledge and trust/provenance context where replay-safe
   state already exists.
2. Show directives received during execution.
3. Show manual or automatic escalations and governance actions.
4. Show outputs / extracted knowledge and downstream reuse where available.
5. Keep the view compact enough to answer "why did this happen?" quickly.

### Hard constraints

- Do **not** present runtime-only internals as exact if they are not replay-safe.
- Do **not** build a giant transcript viewer and call it an audit trail.
- Do **not** add new event types for audit polish.

### What success looks like

An operator can open a colony and understand its major decision path without
reading the raw transcript.

---

## 1B. Task-type validators and tri-state completion

Add bounded deterministic validators for non-code task families.

### Required scope

1. Preserve the existing code-task success path.
2. Add lightweight validators for at least:
   - research tasks
   - documentation tasks
   - review tasks
3. Distinguish:
   - `pass`
   - `fail`
   - `inconclusive`
4. Surface tri-state completion in the main UI surfaces:
   - Done (validated)
   - Done (unvalidated)
   - Stalled

### Hard constraints

- Validators must be deterministic and inspectable.
- Validator state must be replay-derivable or derived from existing projection
  truth.
- Do **not** hide validator truth in runtime-only fields that vanish on replay.

### What success looks like

Operators can tell whether a colony was validated, merely completed, or
stalled.

---

## 1C. Governance-owned auto-escalation

Add one bounded auto-escalation rule.

### Required scope

1. If a colony stalls and has a heavier tier available, give it one more chance
   via `routing_override`.
2. Keep the reason explicit, such as `auto_escalated_on_stall`.
3. Keep the rule budget-aware and bounded.
4. Ensure the outcome remains visible to the Wave 38 escalation matrix.

Implementation note: implement escalation as a post-governance step in the
round loop, not inside `_evaluate_governance()` itself. That helper is a
`@staticmethod` with no access to tier or budget state.

### Hard constraints

- Do **not** implement this through provider fallback.
- Do **not** assume the colony started at `light`; use the colony's actual
  starting tier and the next available tier.
- Do **not** let repeated escalation loops emerge.

### What success looks like

The colony gets one governance-owned second chance with a higher tier before
force-halt, and the reason is inspectable afterward.

---

## Acceptance targets for Team 1

1. A colony-level audit surface exists and is grounded in replay-safe truth.
2. Exact runtime-only internals are not overclaimed as exact history.
3. Task-type validators and tri-state completion are visible and honest.
4. Auto-escalation flows through `routing_override`, not router fallback.
5. No new event types were added by this track.

## Validation

```bash
python scripts/lint_imports.py
python -m pytest -q
cd frontend && npm run build
```

If your audit view starts tempting you toward new truth capture, stop and
report that seam rather than widening the contract casually.

## Required report

- exact files changed
- what the audit trail now shows
- which parts are replay-safe truth versus reconstructed explanation
- what task-type validators were added
- how auto-escalation is triggered and bounded
- confirmation that provider fallback and capability escalation remained
  separate
- confirmation that no new event types were added
