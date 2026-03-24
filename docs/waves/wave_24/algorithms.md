# Wave 24 Algorithms

**Wave:** 24 - "Trust the Surfaces"  
**Purpose:** Implementation reference for the three Wave 24 tracks.

---

## A1. Model Identity Reconciliation

### Current repo truth

- The backend already derives a human-readable local model name in [view_state.py](/c:/Users/User/FormicOSa/src/formicos/surface/view_state.py).
- The operator-facing inconsistency is mostly presentation:
  - some surfaces show the human name
  - other surfaces emphasize the routing alias or address such as `llama-cpp/gpt-4`

### Goal

Show one canonical display pattern everywhere:

- primary: human-readable model name, for example `Qwen3-30B-A3B`
- secondary: routing address, for example `llama-cpp/gpt-4`

### Implementation notes

- Keep the snapshot shape stable.
- Prefer using the existing `name` field from the backend for the primary label.
- Frontend surfaces should render the routing address as secondary, not as the main identity.

Files:

- [view_state.py](/c:/Users/User/FormicOSa/src/formicos/surface/view_state.py)
- [model-registry.ts](/c:/Users/User/FormicOSa/frontend/src/components/model-registry.ts)
- [queen-overview.ts](/c:/Users/User/FormicOSa/frontend/src/components/queen-overview.ts)

---

## A2. Tree Collapse Debugging

### Current repo truth

- The static code in [tree-nav.ts](/c:/Users/User/FormicOSa/frontend/src/components/tree-nav.ts) looks plausible.
- The operator reports that the collapse control is clickable but does not collapse.
- This means the acceptance check must be browser-driven, not code-review-only.

### Goal

Make the collapse affordance actually collapse and expand the tree.

### Implementation notes

- Reproduce the bug live before deciding on the fix.
- Likely causes:
  - click propagation from the toggle into the parent node handler
  - local expanded-state updates being visually overridden by re-render timing
  - toggle state logic behaving differently under live updates than in static reading
- Temporary logging is acceptable while debugging, but must be removed before landing.

Acceptance:

- browser smoke or live manual verification must prove collapse works

File:

- [tree-nav.ts](/c:/Users/User/FormicOSa/frontend/src/components/tree-nav.ts)

---

## A3. Effective vs Configured Context

### Current repo truth

- The UI already shows effective and configured context values.
- The operator can see the reduction, but not why it happened or what to do about it.
- The repo also still contains a stale `131k` context comment in [formicos.yaml](/c:/Users/User/FormicOSa/config/formicos.yaml).

### Goal

When effective context is lower than configured context, the UI should explain:

- what the two numbers mean
- why the effective value is lower
- what the operator can change, if anything

### Implementation notes

- Keep the data model unchanged.
- Add explanatory text in the model registry when `configuredCtx !== ctx`.
- The explanation should reference llama.cpp fit behavior in plain language.
- Clean up stale comments in config so docs and UI do not disagree.

Files:

- [model-registry.ts](/c:/Users/User/FormicOSa/frontend/src/components/model-registry.ts)
- [formicos.yaml](/c:/Users/User/FormicOSa/config/formicos.yaml)

---

## A4. VRAM Normalization and Display Units

### Current repo truth

- The VRAM probe paths in [ws_handler.py](/c:/Users/User/FormicOSa/src/formicos/surface/ws_handler.py) use mixed assumptions:
  - Prometheus path reads bytes
  - health path may return bytes or already-normalized values
  - `nvidia-smi` path returns MiB
- The frontend currently renders numbers that can look absurd if the source units are inconsistent.

### Goal

Normalize all VRAM values to MiB internally and render them in a sane human-readable unit.

### Implementation notes

- Keep JSON field names stable: `usedMb` and `totalMb`
- Normalize source values to MiB in the backend
- Use a shared frontend formatter:
  - GiB when value is >= 1024 MiB
  - MiB otherwise
- Update every operator-visible VRAM surface, not just one

Files:

- [ws_handler.py](/c:/Users/User/FormicOSa/src/formicos/surface/ws_handler.py)
- [model-registry.ts](/c:/Users/User/FormicOSa/frontend/src/components/model-registry.ts)
- [queen-overview.ts](/c:/Users/User/FormicOSa/frontend/src/components/queen-overview.ts)

---

## A5. Aggregate Budget Truth

### Current repo truth

- The app-level budget denominator is the sum of per-colony `budgetLimit` values.
- That is technically truthful arithmetic, but it reads like a global spend cap even though the operator cannot control it from the header.
- The same misleading aggregate budget framing appears in more than one frontend surface.

### Goal

Aggregate surfaces should show real session cost, not a fake-looking global budget fraction.

### Implementation notes

- Top-level summary surfaces should show cost only, for example `"$0.02 spent"`
- Per-colony budget remains visible in colony detail, where it is meaningful
- Fix all aggregate displays together so the operator does not see contradictory budget stories

Files:

- [formicos-app.ts](/c:/Users/User/FormicOSa/frontend/src/components/formicos-app.ts)
- [queen-overview.ts](/c:/Users/User/FormicOSa/frontend/src/components/queen-overview.ts)

---

## A6. Colony Display Names in Tree and Cards

### Current repo truth

- `ColonyProjection` already stores `display_name`
- the frontend helper already prefers `displayName`
- but the snapshot tree currently still sends raw colony ids as the node name

### Goal

Named colonies should appear as named colonies in the tree and other derived views.

### Implementation notes

- This is intentionally small and high-leverage
- Add `displayName` to the tree node and prefer `display_name or id` for the primary label
- Let existing frontend helpers do the rest

Files:

- [view_state.py](/c:/Users/User/FormicOSa/src/formicos/surface/view_state.py)
- [helpers.ts](/c:/Users/User/FormicOSa/frontend/src/helpers.ts) for verification only

---

## B1. Multi-Subscriber Colony Fan-Out

### Current repo truth

- [ws_handler.py](/c:/Users/User/FormicOSa/src/formicos/surface/ws_handler.py) currently stores only one colony-specific queue per colony id.
- That works for the current spawn-and-stream AG-UI flow.
- It will not support attach semantics well.

### Goal

Support multiple simultaneous listeners for the same running colony.

### Implementation notes

- Change the internal structure from single queue to a list or set of queues per colony id
- `subscribe_colony()` should return a dedicated queue for that subscriber
- `unsubscribe_colony()` should remove a specific queue, not wipe the whole colony entry
- fan-out should write to every queue for the matching colony

This is the technical prerequisite for A2A attach.

Files:

- [ws_handler.py](/c:/Users/User/FormicOSa/src/formicos/surface/ws_handler.py)
- [agui_endpoint.py](/c:/Users/User/FormicOSa/src/formicos/surface/agui_endpoint.py)

---

## B2. Shared Event Translation

### Current repo truth

- [agui_endpoint.py](/c:/Users/User/FormicOSa/src/formicos/surface/agui_endpoint.py) still contains inline FormicOS-to-AG-UI translation logic.
- If A2A gets a live events endpoint, copying that logic would create drift risk immediately.

### Goal

Extract one shared translator used by both AG-UI and A2A attach.

### Implementation notes

- Create a new surface helper module for translation
- Move the AG-UI-shaped SSE builders there
- Expose a single `translate_event(...)` entry point
- Keep behavior equivalent for the existing AG-UI path

Files:

- [event_translator.py](/c:/Users/User/FormicOSa/src/formicos/surface/event_translator.py)
- [agui_endpoint.py](/c:/Users/User/FormicOSa/src/formicos/surface/agui_endpoint.py)
- [routes/a2a.py](/c:/Users/User/FormicOSa/src/formicos/surface/routes/a2a.py)

---

## B3. A2A Attach Endpoint

### Current repo truth

- A2A is currently poll/result only.
- AG-UI is currently spawn-and-stream only.
- There is no path for "submit work, then attach later."

### Goal

Add `GET /a2a/tasks/{task_id}/events` as the missing attach surface.

### Semantics

- A2A remains the task lifecycle surface
- attach belongs under A2A, not AG-UI
- behavior should be snapshot-then-live-tail:
  - first send a current snapshot of the colony state
  - then stream live translated events
- if the task is already terminal:
  - send final snapshot
  - send terminal event
  - close

### Implementation notes

- Do not add a new task model
- `task_id == colony_id` remains true
- Do not advertise streaming until the endpoint exists and works

Files:

- [routes/a2a.py](/c:/Users/User/FormicOSa/src/formicos/surface/routes/a2a.py)
- [transcript.py](/c:/Users/User/FormicOSa/src/formicos/surface/transcript.py)
- [routes/protocols.py](/c:/Users/User/FormicOSa/src/formicos/surface/routes/protocols.py)
- [app.py](/c:/Users/User/FormicOSa/src/formicos/surface/app.py)
- [A2A-TASKS.md](/c:/Users/User/FormicOSa/docs/A2A-TASKS.md)

---

## C1. Failure Metadata Storage

### Current repo truth

- [events.py](/c:/Users/User/FormicOSa/src/formicos/core/events.py) already carries:
  - `ColonyFailed.reason`
  - `ColonyKilled.killed_by`
- [projections.py](/c:/Users/User/FormicOSa/src/formicos/surface/projections.py) currently discards that metadata.

### Goal

Preserve the failure details the repo already has, without inventing richer semantics than the system currently stores.

### Implementation notes

- Add conservative fields to `ColonyProjection`
- Populate them from existing event handlers
- Do not promise governance metadata that is not actually stored

Files:

- [projections.py](/c:/Users/User/FormicOSa/src/formicos/surface/projections.py)
- [events.py](/c:/Users/User/FormicOSa/src/formicos/core/events.py) for reference only

---

## C2. Transcript and A2A Failure Context

### Current repo truth

- [transcript.py](/c:/Users/User/FormicOSa/src/formicos/surface/transcript.py) does not currently include structured failure context.
- A2A result payloads depend on `build_transcript()`, so improving transcript truth improves A2A results automatically.

### Goal

When a colony fails or is killed, expose a small truthful `failure_context` block.

### Implementation notes

- Keep the shape conservative:
  - `failure_reason`
  - `failed_at_round`
  - `killed_by`
  - `killed_at_round`
- Include it only when the data exists
- Keep the A2A status endpoint aligned with transcript output

Files:

- [transcript.py](/c:/Users/User/FormicOSa/src/formicos/surface/transcript.py)
- [routes/a2a.py](/c:/Users/User/FormicOSa/src/formicos/surface/routes/a2a.py)

---

## C3. Browser Smoke Expansion

### Current repo truth

- [smoke.spec.ts](/c:/Users/User/FormicOSa/tests/browser/smoke.spec.ts) already exists.
- The next step is to cover the new truth surfaces, not to turn this into a huge browser suite.

### Goal

Add a few assertions that guard the operator-facing truths this wave fixes.

Suggested checks:

- tree collapse actually changes visibility
- model registry shows human-readable model naming
- colony display names appear when available
- aggregate cost display no longer uses a misleading denominator

File:

- [smoke.spec.ts](/c:/Users/User/FormicOSa/tests/browser/smoke.spec.ts)

---

## Ownership Summary

### Track A

- [view_state.py](/c:/Users/User/FormicOSa/src/formicos/surface/view_state.py)
- [ws_handler.py](/c:/Users/User/FormicOSa/src/formicos/surface/ws_handler.py) for VRAM normalization only
- [model-registry.ts](/c:/Users/User/FormicOSa/frontend/src/components/model-registry.ts)
- [queen-overview.ts](/c:/Users/User/FormicOSa/frontend/src/components/queen-overview.ts)
- [formicos-app.ts](/c:/Users/User/FormicOSa/frontend/src/components/formicos-app.ts)
- [tree-nav.ts](/c:/Users/User/FormicOSa/frontend/src/components/tree-nav.ts)
- [formicos.yaml](/c:/Users/User/FormicOSa/config/formicos.yaml)

### Track B

- [ws_handler.py](/c:/Users/User/FormicOSa/src/formicos/surface/ws_handler.py) for colony fan-out
- [event_translator.py](/c:/Users/User/FormicOSa/src/formicos/surface/event_translator.py)
- [agui_endpoint.py](/c:/Users/User/FormicOSa/src/formicos/surface/agui_endpoint.py)
- [routes/a2a.py](/c:/Users/User/FormicOSa/src/formicos/surface/routes/a2a.py)
- [routes/protocols.py](/c:/Users/User/FormicOSa/src/formicos/surface/routes/protocols.py)
- [app.py](/c:/Users/User/FormicOSa/src/formicos/surface/app.py)
- [A2A-TASKS.md](/c:/Users/User/FormicOSa/docs/A2A-TASKS.md)

### Track C

- [projections.py](/c:/Users/User/FormicOSa/src/formicos/surface/projections.py)
- [transcript.py](/c:/Users/User/FormicOSa/src/formicos/surface/transcript.py)
- [routes/a2a.py](/c:/Users/User/FormicOSa/src/formicos/surface/routes/a2a.py) after Track B reread
- [smoke.spec.ts](/c:/Users/User/FormicOSa/tests/browser/smoke.spec.ts)
