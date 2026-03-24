You own the Wave 49 backend message-enrichment track.

This is the replay-safe conversational-state track. You are not building the
frontend cards themselves and you are not changing the Queen's underlying
intelligence. Your job is to make the existing Queen thread message path rich
enough that Team 2 can render structured orchestration cards truthfully.

## Mission

Land the backend-heavy parts of Wave 49:

1. additive replay-safe `QueenMessage` metadata
2. projection / contract support for that metadata
3. structured preview payloads on persisted Queen thread messages
4. structured result payloads on Queen follow-up messages
5. explicit ask/notify classification where the backend can state it honestly
6. deterministic Queen thread compaction so long chat sessions degrade
   gracefully

The core rule still applies:

**If the benchmark disappeared tomorrow, would we still want this change in
FormicOS?**

Yes. Replay-safe conversational orchestration is a real operator feature.

## Read First

1. `AGENTS.md`
2. `CLAUDE.md`
3. `docs/waves/wave_49/wave_49_plan.md`
4. `docs/waves/wave_49/acceptance_gates.md`
5. `src/formicos/core/events.py`
6. `docs/contracts/events.py`
7. `docs/contracts/types.ts`
8. `src/formicos/surface/projections.py`
9. `src/formicos/surface/queen_runtime.py`
10. `frontend/src/types.ts`
11. `tests/unit/surface/test_queen_runtime.py`
12. `tests/unit/test_restart_recovery.py`

Before editing, verify how `QueenMessage` currently flows:

- emitted in `queen_runtime.py`
- stored in projections
- rebuilt in snapshots
- mirrored in frontend types

## Owned Files

- `src/formicos/core/events.py`
- `docs/contracts/events.py`
- `docs/contracts/types.ts`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/queen_runtime.py`
- `frontend/src/types.ts`
- targeted tests for replay-safe Queen message metadata and follow-up payloads

## Do Not Touch

- `frontend/src/components/**`
- `frontend/src/state/store.ts`
- `frontend/src/components/queen-overview.ts`
- `config/caste_recipes.yaml`
- docs files outside the Wave 49 packet
- unrelated preview/timeline/audit code from Wave 48

Team 2 owns rendering/layout. Team 3 owns docs/recipes truth.

## Required Work

### Track A: Additive `QueenMessage` Metadata

Extend `QueenMessage` in a backward-compatible way.

Requirements:

- no new event types
- only additive optional fields
- older logs replay safely with defaults
- projection rebuild stays correct
- verify the propagation path you own:
  - event
  - projection
  - contract mirrors
  - frontend type

Important handoff:

- Team 2 owns `frontend/src/state/store.ts` and chat rendering
- the current store handler only builds `QueenChatMessage` from role/text/ts
- Team 2 will extend that path to read your new fields after your final type
  shape lands

Preferred shape:

- `intent`: `notify` | `ask` | `null`
- `render`: `text` | `preview_card` | `result_card` | `null`
- `meta`: optional structured payload

Hard rule:

- do not overload one field to mean both semantics and rendering

### Track B: Structured Preview Payload On Persisted Queen Messages

When the Queen proposes a plan through preview mode:

- preserve the structured preview payload on the emitted Queen thread message
- support the current shared preview truth from Wave 48
- do not rely on transient `QueenResponse.actions` alone

Important nuance:

- `QueenResponse.actions` can remain useful runtime scaffolding
- but Team 2 must be able to reconstruct the card after refresh/replay from
  persisted thread message state
- the main plumbing seam is `_emit_queen_message(...)` in
  `src/formicos/surface/queen_runtime.py`; it currently only accepts plain
  text and should be enriched to carry optional `intent`, `render`, and
  `meta`

Support both:

- single-colony preview
- parallel-plan preview

### Track C: Structured Result Payload On Follow-Up Messages

Use the existing `follow_up_colony()` path rather than inventing a second
completion-summary mechanism.

When the Queen emits a completion follow-up, include structured metadata for a
result card:

- colony ID
- task / display name
- completion status
- rounds
- cost
- quality score where available
- extracted-knowledge count where available
- validator summary where available

Carry stable identifiers for drill-downs. Do not precompute frontend routes.

Implementation hint:

- `follow_up_colony()` already extracts most of the result-card truth from
  projections
- enrich the same `_emit_queen_message(...)` helper rather than inventing a
  parallel result-message path

### Track D: Ask / Notify Classification

Add explicit backend classification where it is honest and low-risk:

- preview proposal -> `notify`
- completion follow-up -> `notify`
- genuine operator-input request -> `ask`

Keep this conservative.

Do not:

- classify every Queen text by brittle punctuation heuristics in the backend
- turn the backend into a speculative "message mood detector"

The frontend can still apply fallback heuristics where metadata is absent.

### Track E: Backward Compatibility And Replay Truth

This wave touches an existing persisted event type.

You must verify:

- older stored `QueenMessage` events deserialize cleanly
- projections rebuild with new defaults
- snapshots and incremental events remain aligned

If contract mirrors need updates, make them in this track.

### Track F: Deterministic Queen Thread Compaction

Wave 49 makes chat the primary surface. The current Queen path still rebuilds
prompt context from the full thread message history. Fix that here.

Requirements:

- compact older Queen thread history before prompt context grows without bound
- trigger compaction by token pressure, not only raw message count
- keep a bounded recent window of messages raw
- pin unresolved `ask` messages and active preview-card decisions so they do
  not get compacted too early
- build one bounded earlier-conversation block from structured thread truth
  first and older prose second
- keep the first version deterministic; do not add an LLM summarizer here

Useful guidance:

- Track F depends on Track A metadata landing first
- as Wave 49 metadata lands, the compactor should prefer:
  - confirmed preview-card metadata
  - result-card metadata
  - workflow / active-plan state
  - Queen notes or other existing structured preferences
- use prose only to fill gaps

Fallback:

- if you need an intermediate step while Track A settles, prose-only
  compaction is acceptable temporarily
- it is not the target design for final acceptance

Hard rule:

- do not build a crude message-count-only sliding window and call it done

## Hard Constraints

- No new event types
- No new event stream
- No new runtime subsystem
- No transient-only card path that bypasses replay
- No frontend rendering work in this track
- No non-deterministic LLM-based conversation summarizer in this track

## Validation

Run at minimum:

1. `python scripts/lint_imports.py`
2. `python -m ruff check src/formicos/core/events.py src/formicos/surface/projections.py src/formicos/surface/queen_runtime.py tests/unit/surface/test_queen_runtime.py`
3. targeted tests for:
   - new Queen message metadata / follow-up payloads
   - Queen thread compaction behavior
4. `python -m pytest tests/unit/surface/test_queen_runtime.py tests/unit/test_restart_recovery.py -q`

If you add a new focused test file, include it explicitly in the validation
command.

## Summary Must Include

- exact additive fields added to `QueenMessage`
- whether contract mirrors were updated
- how preview metadata now reaches persisted thread messages
- how result-card metadata now reaches follow-up messages
- how ask/notify classification is determined
- how Queen thread compaction is triggered and what it preserves
- what you explicitly kept out to stay bounded
