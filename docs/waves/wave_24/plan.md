# Wave 24 Plan - Trust the Surfaces

**Wave:** 24 - "Trust the Surfaces"  
**Theme:** Every number, label, and control in the UI means exactly what it says. External agents get the one missing piece: "I submitted work, now let me watch it." This is the wave where the alpha earns trust.  
**Contract changes:** 0 new events. Event union stays at 37. Ports stay frozen. Additive read-model and frontend fields are allowed where needed for truth and failure clarity.  
**Estimated LOC delta:** ~250 Python, ~120 TypeScript, ~20 docs/config

---

## Why This Wave

Wave 23 made A2A honest, the Queen more composed, and the UX cleaner. But live operator use immediately surfaced a second class of alpha issues: not missing capability, but missing trust.

The current system has two broad gaps:

1. **Operator truth gaps**
   - the local runtime has conflicting identity cues for the same model
   - the tree collapse affordance looks clickable but does not collapse
   - effective context is lower than configured context with only a cryptic `(--fit on)` hint
   - VRAM units can look absurd depending on probe source
   - aggregate budget surfaces imply a meaningful denominator the operator cannot inspect or adjust
   - colony display names exist in projections but are not sent in the tree snapshot

2. **External attach gap**
   - A2A now gives external agents a clean submit/poll/result/cancel lifecycle
   - AG-UI gives a clean spawn-and-stream run surface
   - but there is still no honest "submit once, then attach to already-running work" story

Wave 24 fixes both halves:
- make the operator surfaces truthful
- add attach/replay under A2A without widening AG-UI's accepted contract

This is not a broad cleanup wave. It is a trust wave.

---

## Tracks

### Track A - Operator Truth

**Goal:** The operator-facing UI stops implying things it cannot explain and stops hiding names or controls behind confusing presentation.

**A1. Canonical local model identity.**

The backend already derives a human-readable local model name in `view_state.py`. The visible inconsistency is mostly presentation:
- local runtime surfaces emphasize the real model name
- policy/routing surfaces emphasize the alias or route address (`llama-cpp/gpt-4`)

Fix the display policy so the human-readable name is primary and the routing address is secondary wherever both matter.

Files touched:
- `frontend/src/components/model-registry.ts`
- `frontend/src/components/queen-overview.ts` only if it renders model identity directly
- `src/formicos/surface/view_state.py` only if a tiny backend truth fix is strictly needed

**A2. Tree collapse actually collapses.**

The static code in `tree-nav.ts` looks reasonable, but the operator reports live collapse failure. Treat this as a live behavior bug, not a code-reading exercise.

Required approach:
- reproduce live
- identify the actual failure mode
- fix the real cause
- remove any temporary debug instrumentation before finalizing

Files touched:
- `frontend/src/components/tree-nav.ts`

**A3. Context reduction is explained.**

When effective context is lower than configured context, the UI should explain why in plain language:
- effective context
- configured context
- auto-sizing due to llama.cpp `--fit`
- what the operator can do, if anything, to recover headroom

This is primarily a frontend explanation task, not a new runtime-control feature.

Files touched:
- `frontend/src/components/model-registry.ts`

**A4. VRAM units are normalized.**

The current VRAM probe chain mixes assumptions across `/metrics`, `/health`, and `nvidia-smi`. Normalize all probe outputs to MiB internally, then display GiB when appropriate.

Files touched:
- `src/formicos/surface/ws_handler.py`
- `frontend/src/components/model-registry.ts`
- `frontend/src/components/queen-overview.ts`

**A5. Aggregate budget surfaces become honest.**

The top-level cost/budget denominator is currently the sum of per-colony budget caps. That is truthful arithmetic but poor product communication.

Fix:
- top-level surfaces should show aggregate cost only
- per-colony budget remains in colony detail where it is meaningful

Files touched:
- `frontend/src/components/formicos-app.ts`
- `frontend/src/components/queen-overview.ts`

**A6. Colony display names appear in the tree.**

`ColonyProjection.display_name` already exists. The tree snapshot still emits `colony.id` as the visible node name. Add `displayName` to the tree node and prefer `display_name or id` for the node label.

Files touched:
- `src/formicos/surface/view_state.py`

**A7. Stale context commentary cleanup.**

If discovered in owned files while making the above changes, fix stale `131k`-era comments or wording that contradict the 80k local-default reality.

Files touched:
- `config/formicos.yaml` only if needed
- nearby docs only if directly touched by the truth work

---

### Track B - A2A Attach + Shared Event Translation

**Goal:** External agents can submit a task via A2A and then optionally attach to its live event stream. AG-UI stays untouched. Event translation logic is shared, not duplicated.

**B1. Multi-subscriber colony fan-out.**

`ws_handler.py` currently supports only one queue per colony subscription. Generalize this to multiple queues per colony id so AG-UI and A2A attach can observe the same colony simultaneously.

Files touched:
- `src/formicos/surface/ws_handler.py`

**B2. Shared event translator.**

The FormicOS-to-AG-UI translation logic currently lives inline in `agui_endpoint.py`. Extract it into a shared helper/module so AG-UI and A2A attach do not drift.

Files touched:
- `src/formicos/surface/event_translator.py` - new
- `src/formicos/surface/agui_endpoint.py`

**B3. A2A attach endpoint.**

Add:
- `GET /a2a/tasks/{task_id}/events`

Semantics:
- if task is running: snapshot first, then live tail
- if task is terminal: final snapshot plus terminal event, then close

This endpoint should stream AG-UI-shaped events, not invent a second event dialect.

Files touched:
- `src/formicos/surface/routes/a2a.py`

**B4. Agent Card, registry, and docs update.**

Once attach exists, A2A can honestly advertise streaming support at the protocol-entry level.

Files touched:
- `src/formicos/surface/routes/protocols.py`
- `src/formicos/surface/app.py`
- `docs/A2A-TASKS.md`
- `docs/decisions/039-a2a-attach-under-task-lifecycle.md`

---

### Track C - Failure Clarity + Confidence

**Goal:** When work fails or is killed, operators and external callers see structured, truthful failure metadata instead of just a terminal status.

This track must stay grounded in data the repo actually has today.

**C1. Store failure metadata in projections.**

The events already carry:
- `ColonyFailed.reason`
- `ColonyKilled.killed_by`

The projection handlers currently discard them. Persist those fields on `ColonyProjection`.

Files touched:
- `src/formicos/surface/projections.py`

**C2. Transcript and A2A status enrichment.**

Extend transcript and A2A status payloads with conservative failure metadata:
- `failure_reason`
- `failed_at_round`
- `killed_by`
- `killed_at_round`

Do not promise `governance_action` unless that data is actually stored in the projection during the same wave.

Files touched:
- `src/formicos/surface/transcript.py`
- `src/formicos/surface/routes/a2a.py`

**C3. Browser smoke assertions for truth surfaces.**

Expand the existing smoke spec with a few targeted truth assertions:
- model name rendering
- tree collapse
- cost header without misleading denominator
- named colony rendering when present

This is assertion expansion, not a new browser framework effort.

Files touched:
- `tests/browser/smoke.spec.ts`

---

## Execution Shape for 3 Parallel Coder Teams

| Team | Track | First Lands On | Dependencies |
|---|---|---|---|
| **Coder 1** | A | `view_state.py`, `ws_handler.py` (VRAM only), frontend truth surfaces | Rereads `ws_handler.py` if Coder 2 lands first |
| **Coder 2** | B | `ws_handler.py`, `event_translator.py`, `agui_endpoint.py`, `routes/a2a.py` | Starts immediately |
| **Coder 3** | C | `projections.py`, `transcript.py`, `routes/a2a.py`, `smoke.spec.ts` | Rereads `routes/a2a.py` after Coder 2 lands |

### Overlap-Prone Files

| File | Teams | Resolution |
|---|---|---|
| `src/formicos/surface/ws_handler.py` | A + B | Different methods, but same file. Coder 1 rereads after Coder 2 if B lands first. |
| `src/formicos/surface/routes/a2a.py` | B + C | Coder 2 adds attach endpoint. Coder 3 adds failure metadata to existing status/result routes. Coder 3 rereads after Coder 2. |
| `frontend/src/components/model-registry.ts` | A only | Single-track. |
| `tests/browser/smoke.spec.ts` | C only | Single-track. |

All other files are single-track.

---

## Acceptance Criteria

1. Model identity is consistent in the operator UI.
   - Human-readable local model name is primary.
   - Routing alias/address is still visible, but secondary.

2. Tree collapse works in live UI.
   - Click toggle.
   - Node collapses.
   - Click again.
   - Node expands.

3. Context reduction is explained when effective < configured.
   - The operator can understand why.
   - The UI does not rely on `(--fit on)` alone.

4. VRAM displays sane values with sane units.
   - No absurd byte-as-megabyte rendering.
   - GiB/MiB usage is consistent.

5. Aggregate cost/budget surfaces are honest.
   - Top-level surfaces show aggregate cost only.
   - Per-colony budget remains visible in colony detail.

6. Named colonies show display names in the tree.
   - Unnamed colonies still fall back to raw ids.

7. `GET /a2a/tasks/{id}/events` exists and works.
   - Running task: snapshot plus live tail.
   - Terminal task: final snapshot plus terminal event, then close.

8. Multi-subscriber colony fan-out works.
   - AG-UI and A2A attach can observe the same colony simultaneously.

9. Event translation is shared.
   - `agui_endpoint.py` and A2A attach use the same translator module.

10. Agent Card and registry advertise A2A attach truthfully.

11. Failed/killed colonies include structured failure metadata in transcript/A2A status when available.

12. Browser smoke covers the truth surfaces touched by this wave.

13. Full pytest suite is green.

14. Frontend build is green.

---

## Smoke Traces

1. **Model identity trace**  
   Open model registry -> see human-readable local model name -> see alias/address secondarily.

2. **Tree collapse trace**  
   Click workspace/thread toggle -> children collapse -> click again -> children expand.

3. **Context explanation trace**  
   Model with configured 80k but lower effective context -> UI explains auto-sizing due to fit/headroom.

4. **VRAM trace**  
   Model registry shows sane GiB or MiB values, not byte-scale nonsense.

5. **Cost trace**  
   Header/overview shows aggregate cost only, with no misleading denominator.

6. **Colony naming trace**  
   Named colony appears with display name in tree/cards/breadcrumbs.

7. **A2A attach trace**  
   `POST /a2a/tasks` -> get task id -> `GET /a2a/tasks/{id}/events` -> receive snapshot -> receive live events -> receive terminal event.

8. **Terminal attach trace**  
   Attach to already-completed task -> receive final snapshot and terminal event -> stream closes cleanly.

9. **Failure trace**  
   Failed or killed colony -> transcript/A2A status include failure metadata directly traceable to stored event data.

---

## Not In Wave 24

| Item | Reason |
|---|---|
| Outbound A2A | Different architectural surface |
| AG-UI Tier 2 steering | Not needed |
| AG-UI attach | Keep AG-UI spawn-only; attach lives under A2A |
| New events | Event surface stays frozen |
| New task entity/store | Tasks remain colonies |
| A2A auth/session framework | Single-operator localhost scope |
| Design-system rewrite | Not the problem |
| RL / self-evolution | Still post-alpha |
| Vector port contract changes | Not needed for this wave |

---

## Frozen Files

| File | Reason |
|---|---|
| `src/formicos/core/events.py` | No event changes |
| `src/formicos/core/ports.py` | No port changes |
| `src/formicos/core/types.py` | No core type changes |
| `src/formicos/engine/*` | Stable this wave |
| `src/formicos/adapters/*` | Stable this wave |
| `src/formicos/surface/queen_runtime.py` | Stable this wave |
| `src/formicos/surface/colony_manager.py` | Stable this wave |
| `src/formicos/surface/registry.py` | Stable; only consumed by updated route wiring |
| `src/formicos/surface/commands.py` | Stable |
| `config/caste_recipes.yaml` | Stable |
| `docker-compose.yml` | No changes |
| `Dockerfile` | No changes |

---

## Resolved Questions

1. **Attach lives under A2A.**  
   `GET /a2a/tasks/{id}/events`. AG-UI stays spawn-only.

2. **Attach semantics are snapshot-then-live-tail.**  
   Reuse transcript-backed snapshot plus shared translated live events.

3. **Multi-subscriber support is required.**  
   One queue per colony is no longer enough.

4. **Event translation is shared.**  
   Extract from AG-UI once; reuse in A2A attach.

5. **Failure metadata stays conservative.**  
   Use `failure_reason` and `killed_by` unless richer projection data is explicitly added.

6. **VRAM is normalized in MiB internally and displayed in GiB/MiB appropriately.**

7. **Aggregate budget denominator is removed from top-level UI.**

8. **Tree nodes carry `displayName` when available.**
