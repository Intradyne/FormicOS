# Wave 23 Plan - Operator Smoothness + External Handshake

**Wave:** 23 - "Operator Smoothness + External Handshake"  
**Theme:** Make the alpha feel deliberate to operate, make the Queen more useful through better behavior rather than more tools, and give external agents a clean inbound task lifecycle.  
**Contract changes:** 0 new events. Union stays at 37. Ports stay frozen. Additive route surface only.  
**Estimated LOC delta:** ~300 Python, ~120 TypeScript, ~40 docs/config

---

## Why This Wave

After Wave 22, FormicOS is capable and mostly truthful. The next pressure is usability and packaging, not missing core mechanics.

- The operator experience still has avoidable friction: weak empty states, a generic first-run welcome, and colony detail that still feels more diagnostic than outcome-led.
- The Queen now has enough tools. The gap is not missing capability; it is follow-through, composition guidance, and a few deterministic guardrails around high-value behaviors.
- External agents can already use FormicOS through MCP, transcript, and AG-UI, but they still have to understand FormicOS internals. What is missing is a thin submit/poll/result wrapper.

Wave 23 should feel like a quality wave, not a capability sprawl wave.

---

## Tracks

### Track A - Operator Experience Polish

Keep this track tightly bounded. Four exact tickets, no broad redesign.

**A1. Empty states across named views**

Add deliberate empty states to the main operator surfaces:

| View | Desired empty state |
|---|---|
| Queen chat | "Ask me anything - try 'write a haiku' or 'review this code'" |
| Knowledge / Skills | "No skills yet - colonies learn as they complete tasks" |
| Knowledge / Library | "Upload documents here to make them searchable by the Queen and colonies" |
| Thread view | "Spawn a colony to get started, or ask the Queen" |
| Round history | "Waiting for first round to complete..." |
| Colony detail, running with no completed rounds | show progress, not an empty panel |

Reuse the existing `.empty-hint` pattern instead of inventing a new visual treatment.

Files touched:
- `frontend/src/components/queen-chat.ts`
- `frontend/src/components/knowledge-view.ts`
- `frontend/src/components/thread-view.ts`
- `frontend/src/components/round-history.ts`
- `frontend/src/components/colony-detail.ts`

**A2. First-run welcome refinement**

Update the bootstrap Queen welcome message so it:

- suggests a concrete task to try
- mentions the Knowledge -> Library flow
- stays short enough to scan

This is a text refinement only. The first-run bootstrap path already exists.

Files touched:
- `src/formicos/surface/app.py`

**A3. Colony detail should lead with outcome**

For completed colonies:
- show a prominent "Final Output" section at the top of colony detail
- source it from the latest round output already present in the colony snapshot

For running colonies:
- show `Round N / M`
- add a thin progress bar
- keep metadata below the outcome/progress surface

No backend change is needed. The snapshot already carries `round`, `maxRounds`, and `rounds`.

Files touched:
- `frontend/src/components/colony-detail.ts`

**A4. Browser smoke runner story**

The Playwright smoke spec already exists, but the runner story is still manual. Make it operator-friendly:

- add a frontend script for smoke
- document the run flow in `CONTRIBUTING.md`
- keep it Windows-friendly

If the script lives in `frontend/package.json`, the path to the root-level test file should be `../tests/browser/smoke.spec.ts`, not `tests/browser/smoke.spec.ts`.

Files touched:
- `frontend/package.json`
- `CONTRIBUTING.md`

---

### Track B - Queen Composition + Behavior Guardrails

No new tool wave. The Queen already has 16 tools and `_MAX_TOOL_ITERATIONS = 7`. This track is about behavior from the existing surface.

**B1. Prior work surfacing on spawn**

When the Queen spawns a colony, append related prior work to the spawn confirmation if relevant hits exist in:

- workspace memory
- skill bank

Important honesty rule:
- this is post-decision surfacing
- it does not influence the team/round/budget choice already made by the Queen
- do not frame it as pre-spawn memory-informed planning unless the implementation point moves before the first Queen completion

Return the best available top hits. Do not hardcode a numeric relevance threshold in the plan.

Files touched:
- `src/formicos/surface/queen_runtime.py`

**B2. Quality-aware follow-up text**

`follow_up_colony()` should branch on quality band:

- high quality: positive summary
- medium quality: completed, may benefit from review
- low quality: suggest retry or a different approach

This is deterministic. It relies on the quality score already computed by the engine.

Files touched:
- `src/formicos/surface/queen_runtime.py`

**B3. Save-as-preference path**

Add an operator-visible, deterministic way to save a Queen message as a thread-scoped preference.

Preferred shape:
- a small pin/save affordance on Queen messages
- frontend dispatches an event
- `formicos-app.ts` sends an existing-style WS command
- backend command handler routes through the Queen's existing note-save path

Do not create a parallel persistence implementation. Reuse the existing Queen note logic. If needed, extract a tiny shared helper inside `QueenAgent` so both the tool path and WS command path call the same save code.

Files touched:
- `frontend/src/components/queen-chat.ts`
- `frontend/src/components/formicos-app.ts`
- `src/formicos/surface/commands.py`
- optionally `src/formicos/surface/queen_runtime.py` if a shared helper is extracted

**B4. Prompt refinement for composition**

Extend the Queen prompt with:

- multi-step workflow guidance
- chaining suggestions for complex tasks
- post-completion suggestions to save results
- retry suggestions for low-quality outcomes

Keep this additive. Wave 22 already gave the Queen a strong prompt.

Files touched:
- `config/caste_recipes.yaml`

---

### Track C - Inbound A2A Task Lifecycle

This is a thin packaging layer, not a new control plane.

**Design principle**

Tasks are colonies. A2A adds a cleaner external lifecycle:

- submit
- poll
- retrieve result
- cancel

It reuses existing runtime/projection/transcript behavior. No new events. No new core data model.

**C1. `POST /a2a/tasks`**

Accept a task description and create a colony using deterministic team selection:

1. template match first
2. simple keyword heuristics second
3. safe fallback last

Do not call the Queen LLM internally.

Return:
- `task_id`
- `status`
- team
- `max_rounds`
- `budget_limit`

No `stream_url` field in Wave 23.

**C2. `GET /a2a/tasks/{id}`**

Return:
- status
- round progress
- convergence
- cost
- quality score

Read directly from the colony projection.

**C3. `GET /a2a/tasks/{id}/result`**

Return transcript-backed results using `build_transcript()`.

- 409 if task still running
- 404 if not found

**C4. `DELETE /a2a/tasks/{id}`**

Cancel a running colony.

**C5. `GET /a2a/tasks`**

List recent tasks with optional `status` and `limit` filters.

**C6. Agent Card + registry update**

Advertise A2A in:
- Agent Card
- capability registry protocol list

Important honesty rule:
- do not advertise A2A streaming unless Wave 23 explicitly adds a separate attach/events endpoint

**C7. A2A docs**

Document the endpoint shapes and the fact that A2A is poll/result only in this wave.

Files touched:
- `src/formicos/surface/routes/a2a.py` (new)
- `src/formicos/surface/routes/__init__.py`
- `src/formicos/surface/routes/protocols.py`
- `src/formicos/surface/app.py`
- `docs/A2A-TASKS.md`

**Scoping choice**

Default A2A placement should be:
- normal workspace
- dedicated `a2a-*` thread naming

That preserves access to workspace memory/library/settings and keeps A2A work visible in the operator UI.

---

## Execution Shape

| Team | Track | First lands on | Dependencies |
|---|---|---|---|
| Coder 1 | A | frontend polish + welcome text | independent |
| Coder 2 | B | Queen behavior + prompt + note-save path | rereads `queen-chat.ts` after Coder 1 |
| Coder 3 | C | A2A route + Agent Card + registry | independent |

### Overlap-prone files

| File | Teams | Resolution |
|---|---|---|
| `frontend/src/components/queen-chat.ts` | A + B | Coder 1 lands empty state first, Coder 2 rereads before adding pin/save affordance |
| `src/formicos/surface/queen_runtime.py` | B only | single-owner for this wave |
| `src/formicos/surface/routes/protocols.py` | C only | single-owner |
| all other touched files | single-owner | no serialization needed |

---

## Acceptance Criteria

Wave 23 is complete when:

1. Queen chat, Knowledge views, Thread view, Round history, and running colony detail all have deliberate empty/progress states.
2. First-run welcome suggests a concrete task and mentions the Library flow.
3. Completed colonies lead with final output in colony detail.
4. Running colonies show `Round N / M` with a thin progress bar.
5. Frontend smoke has a clean documented runner path.
6. Queen follow-up text changes by quality band.
7. Spawn confirmation can surface related prior work without pretending it influenced the earlier decision.
8. Operator-visible save-preference flow exists and reuses thread-scoped Queen notes.
9. `POST /a2a/tasks` submits a task and returns a handle.
10. `GET /a2a/tasks/{id}` returns status with progress.
11. `GET /a2a/tasks/{id}/result` returns transcript-backed results.
12. `DELETE /a2a/tasks/{id}` cancels running tasks.
13. Agent Card advertises A2A.
14. A2A does not promise streaming in this version.
15. Full pytest suite is green.
16. Frontend build is green.

---

## Not In Wave 23

| Item | Reason |
|---|---|
| outbound A2A | separate architectural surface |
| AG-UI Tier 2 | not needed for alpha |
| attach-to-existing AG-UI/A2A streaming | honest defer unless explicitly implemented |
| new events | capability surface stays frozen |
| new core data models | tasks are colonies |
| Queen tool expansion wave | existing tool surface is already large enough |
| `create_template` as core scope | can wait; `write_workspace_file` is sufficient for alpha |
| design system overhaul | outside the wave's product goal |
| framework migration | outside scope |
| vector port contract changes | unnecessary for this wave |

---

## Open Questions To Resolve In Dispatch

1. Is the save-preference flow a pin button only, or also available from a menu/action surface?
2. Does Track B merely surface prior work after spawn, or does the team want to move that logic earlier in the Queen interaction loop in a later wave?
3. Should A2A task listing include only A2A-named threads, or all colonies?
4. Is A2A thread naming based on a slugged description, generated colony id, or both?

Default recommendations:
- pin button only
- post-spawn surfacing only in Wave 23
- list only A2A-tagged threads/tasks
- use `a2a-{description_slug}` with truncation
