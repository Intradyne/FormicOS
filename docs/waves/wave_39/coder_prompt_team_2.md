## Role

You own the operator co-authorship track of Wave 39.

Your job is to:

- implement ADR-049's narrow event expansion
- make operator knowledge edits durable and replay-safe
- keep operator editorial authority local-first rather than silently mutating
  shared epistemic truth

This is the "editable hive state without breaking replay or federation" track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_39/wave_39_plan.md`
4. `docs/waves/wave_39/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `src/formicos/core/events.py`
7. `src/formicos/surface/projections.py`
8. `src/formicos/surface/knowledge_catalog.py`
9. `src/formicos/surface/routes/knowledge_api.py`
10. `frontend/src/components/knowledge-browser.ts`

## Coordination rules

- ADR-049 must be the only intended Wave 39 event expansion.
- Keep the expansion to exactly 3 event families.
- Operator actions are **local-first editorial overlays**, not shared
  confidence mutations.
- Do **not** silently update `conf_alpha` / `conf_beta`.
- Do **not** federate behavioral overrides by default.
- Reversible actions must also be replayable actions.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `src/formicos/core/events.py` | OWN | 3 new event families only |
| `src/formicos/surface/projections.py` | OWN | overlay state, annotation index, config override history |
| `src/formicos/surface/knowledge_catalog.py` | OWN | retrieval respects pinned / muted / invalidated overlays |
| `src/formicos/surface/routes/knowledge_api.py` | MODIFY | operator-action and annotation endpoints if this is the better route surface |
| `src/formicos/surface/routes/api.py` | MODIFY | only if a small additive route is needed outside knowledge_api |
| `frontend/src/components/knowledge-browser.ts` | OWN | action menu, badges, annotation display |
| `tests/unit/core/test_wave39_operator_events.py` | CREATE | event-union and schema coverage |
| `tests/unit/surface/test_wave39_operator_overlays.py` | CREATE | replay / overlay retrieval coverage |

## DO NOT TOUCH

- `src/formicos/engine/*` - Team 1 owns
- `src/formicos/surface/colony_manager.py` - Team 1 only for small validator seam
- `src/formicos/surface/proactive_intelligence.py` - Team 3 owns
- `src/formicos/surface/queen_runtime.py` - Team 3 owns
- `frontend/src/components/proactive-briefing.ts` - Team 3 owns
- `frontend/src/components/workflow-view.ts` - Team 3 owns the pre-spawn edit UI
- `frontend/src/components/config-memory.ts` - Team 3 owns

## Overlap rules

- `src/formicos/surface/projections.py`
  - You own operator overlays, annotations, and override-history state.
  - Team 1 owns audit-view and validator support.
  - Team 3 owns operator response patterns.
  - Reread before merge.
- `src/formicos/surface/routes/api.py`
  - Prefer `knowledge_api.py` if the action is knowledge-centric.
  - Touch `api.py` only if there is a strong reason.

---

## 2A. ADR-049 event expansion

Implement exactly these 3 event families:

1. `KnowledgeEntryOperatorAction`
2. `KnowledgeEntryAnnotated`
3. `ConfigSuggestionOverridden`

### Required scope

For `KnowledgeEntryOperatorAction`, use one event family with an action enum:

- `pin`
- `unpin`
- `mute`
- `unmute`
- `invalidate`
- `reinstate`

For each family, define payloads narrowly and clearly.

Implementation note: `src/formicos/core/events.py` has an import-time
self-check that compares the event union and the `EVENT_TYPE_NAMES` manifest.
Add your 3 new event families to both, or import will fail.

### Hard constraints

- Do **not** split these into many tiny event types.
- Do **not** widen the event union beyond these three families.
- Do **not** quietly add helper event families later in the track.

### What success looks like

Replay from the event log reconstructs operator overlay and annotation state
without hidden side stores.

---

## 2B. Local-first operator overlays

Implement retrieval/editorial overlays, not confidence mutation.

### Required scope

1. Replay and project pinned entries.
2. Replay and project muted entries.
3. Replay and project invalidated entries.
4. Make retrieval respect those overlays locally.
5. Keep the original canonical entry intact unless a future explicit promotion
   path exists.

### Hard constraints

- `pin`, `mute`, and `invalidate` must not silently emit
  `MemoryConfidenceUpdated`.
- Local editorial actions must not alter shared Beta posteriors by default.
- Pins, mutes, and invalidations should be local-only by default.
- If you think a shared mutation is needed, stop and report it instead of
  sneaking it in.

### What success looks like

An operator can pin, mute, invalidate, and reverse those actions locally, and
the behavior survives replay without poisoning shared confidence truth.

---

## 2C. Knowledge annotations

Make operator annotations durable and visible.

### Required scope

1. Add annotation events and projection support.
2. Surface annotations in knowledge detail.
3. Surface annotations in trust / rationale views where appropriate.
4. Keep federation behavior explicit and policy-driven.

### Hard constraints

- Do not make every annotation globally federated by default.
- Do not treat annotation tags as automatic shared confidence penalties.
- Additive explanation is okay; hidden epistemic mutation is not.

### What success looks like

Operator annotations persist, replay cleanly, and appear in the main knowledge
surfaces.

---

## Acceptance targets for Team 2

1. The event union grows narrowly from 55 to 58 through exactly 3 event
   families.
2. Operator actions are replayable and reversible.
3. Operator actions are local-first and do not silently mutate shared
   confidence truth.
4. Knowledge annotations persist and surface correctly.
5. Federation behavior is explicit and local-first for behavioral overrides.

## Validation

```bash
python scripts/lint_imports.py
python -m pytest -q
cd frontend && npm run build
```

If the implementation starts drifting toward shared-confidence mutation, stop
and report that seam. That is a design boundary, not a polish detail.

## Required report

- exact files changed
- exact 3 event families added
- how replay rebuilds operator overlay state
- how retrieval now respects overlays
- how you kept operator actions local-first
- what federation behavior was chosen for annotations and overrides
- confirmation that no implicit confidence mutation was introduced
