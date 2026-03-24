You own the Wave 51 replay-safety and backend-truth track.

This is the only track allowed to touch backend mutation truth for Wave 51.
Your job is to make shipped operator-visible capabilities durable where they
claim durability, classify ephemeral behavior honestly where they do not, and
leave the frontend and general docs teams free to work in parallel.

## Mission

Land the backend-heavy parts of Wave 51:

1. replay-safe escalation for `escalate_colony`
2. replay-safe Queen notes without leaking private notes into visible chat
3. replay-safe or explicitly ephemeral handling for `dismiss-autonomy`
4. proper deprecation signaling for the old Memory API
5. config-override route cleanup if it stays small and purely backend
6. canonical replay-safety documentation in `docs/REPLAY_SAFETY.md`
7. frozen/legacy event comments where helpful

The core rule still applies:

**If the benchmark disappeared tomorrow, would we still want this change in
FormicOS?**

Yes. Restart-safe operator actions and honest capability classification are
real product value.

## Read First

1. `AGENTS.md`
2. `CLAUDE.md`
3. `docs/waves/wave_51/wave_51_plan.md`
4. `docs/waves/wave_51/acceptance_gates.md`
5. `docs/waves/wave_51/backend_audit_findings.md`
6. `docs/waves/wave_51/backend_seam_map.md`
7. `docs/waves/wave_50/status_after_plan.md`
8. `src/formicos/core/events.py`
9. `src/formicos/surface/commands.py`
10. `src/formicos/surface/queen_tools.py`
11. `src/formicos/surface/queen_runtime.py`
12. `src/formicos/surface/projections.py`
13. `src/formicos/surface/routes/api.py`
14. `src/formicos/surface/routes/memory_api.py`
15. `docs/contracts/events.py`
16. `docs/contracts/types.ts`

Before editing, re-verify these truths in code:

- global promotion is already landed and is NOT your task
- learned-template enrichment is already landed and is NOT your task
- `escalate_colony` still mutates projection state directly
- `save_queen_note` is still in-memory only
- `queen_note` is still YAML-backed only
- `dismiss-autonomy` is still restart-lost overlay state

## Owned Files

- `src/formicos/core/events.py`
- `src/formicos/surface/commands.py`
- `src/formicos/surface/queen_tools.py`
- `src/formicos/surface/queen_runtime.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/routes/api.py`
- `src/formicos/surface/routes/memory_api.py`
- `docs/contracts/events.py`
- `docs/contracts/types.ts`
- `docs/REPLAY_SAFETY.md`
- `docs/decisions/*` only if a new ADR is required for a new event type
- targeted backend/contract tests you add for this track

## Do Not Touch

- frontend component files
- `frontend/src/state/store.ts`
- `frontend/src/types.ts`
- `docs/OPERATORS_GUIDE.md`
- `AGENTS.md`
- `CLAUDE.md`
- Wave 51 packet docs (`wave_51_plan.md`, `acceptance_gates.md`, `cloud_audit_prompt.md`)
- any Wave 50 substrate around global promotion or learned-template enrichment

Team 2 owns frontend surfaces. Team 3 owns general docs truth. You own backend
capability truth and `docs/REPLAY_SAFETY.md`.

## Parallel-Safe Coordination Rules

1. Team 1 is authoritative for any new event shapes.
2. If you add a new event type, update contract mirrors in the same track.
3. Do not require Team 2 to consume a new backend field for Wave 51 UI work.
4. Keep `docs/REPLAY_SAFETY.md` under Team 1 ownership so Team 3 can reference
   it later without merge conflict.

## Required Work

### Track A1: `escalate_colony` replay safety

Current truth:
- `escalate_colony` mutates `colony.routing_override` directly on the in-memory
  projection
- no event captures the override

Required outcome:
- escalation survives restart/replay or is explicitly demoted from durable behavior

Preferred implementation order:
1. encode escalation in an existing replay-safe event if that is genuinely clean
2. otherwise add a focused new event type and a matching projection path

If you add a new event type:
- update `docs/contracts/events.py`
- update `docs/contracts/types.ts`
- add a focused ADR under `docs/decisions/`

### Track A2: Queen note replay safety

Current truth:
- `save_queen_note` uses in-memory `thread_notes`
- `queen_note` writes YAML files
- neither survives replay as event truth

Critical seam rule:

**Queen notes are private working context, not visible operator chat.**

Do NOT persist notes by emitting ordinary visible `QueenMessage` events or by
rendering them as chat rows.

Required outcome:
- restart/replay restores thread-note context correctly
- operator chat does not gain visible note rows as a side effect

Preferred implementation order:
1. dedicated hidden note event + projection path
2. explicitly non-chat replay path that rebuilds `thread_notes`
3. keep YAML only as backup/export, not source of truth

### Track A5: `dismiss-autonomy` truth

Current truth:
- dismissal state is memory-only

Required outcome:
- either make it replay-safe
- or make its ephemeral nature explicit in the backend/documentation truth

Do not leave it in ambiguous middle ground.

### Track C4: Deprecated Memory API signaling

Required outcome:
- add `Sunset` headers to deprecated `/api/v1/memory` endpoints
- add cheap usage logging so future removal is evidence-based

Keep this bounded. This is not a full API redesign.

### Track C5: Config-override route cleanup

If this stays small and does not drag in frontend work:
- consolidate the duplicate route story
- or document the canonical path clearly in code/comments

If it starts expanding, stop and report it as follow-up debt rather than
sprawling the wave.

### Track C6/C7/C8: Canonical replay-safety doc and frozen-event truth

Create `docs/REPLAY_SAFETY.md` that classifies major capabilities as:

- event-sourced / durable
- file-backed / external
- in-memory / restart-lost
- intentionally ephemeral

Also:
- document the Memory/Knowledge naming bridge once
- add clear frozen/legacy comments in code where appropriate

## Hard Constraints

- Do not reopen Wave 50 work around global promotion or learned templates
- Do not persist Queen notes as visible chat rows
- Do not add backend subsystems
- Do not change frontend-owned files
- If a new event type is added, it must be justified by replay safety for a
  shipped capability, not by speculative design

## Validation

Run at minimum:

1. `python scripts/lint_imports.py`
2. `python -m ruff check src/formicos/core/events.py src/formicos/surface/commands.py src/formicos/surface/queen_tools.py src/formicos/surface/queen_runtime.py src/formicos/surface/projections.py src/formicos/surface/routes/api.py src/formicos/surface/routes/memory_api.py`
3. `python -m pytest tests/contract/test_events_contract.py tests/unit/core/test_events.py tests/unit/surface/test_queen_runtime.py tests/unit/surface/test_projection_handlers_full.py tests/unit/surface/test_config_endpoints.py tests/unit/surface/test_knowledge_api_filters.py -q`
4. any new targeted pytest files you add for escalation, notes, or deprecated API signaling

## Summary Must Include

- what you chose for escalation persistence and why
- how Queen notes now persist, explicitly confirming they are not visible chat
- whether `dismiss-autonomy` became durable or explicitly ephemeral
- whether any new event type was added
- whether an ADR was needed
- what `docs/REPLAY_SAFETY.md` now covers
- what you kept out to stay bounded
