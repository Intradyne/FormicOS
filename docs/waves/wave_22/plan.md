# Wave 22 Plan - Trust the Product

**Wave:** 22 - "Trust the Product"  
**Theme:** The Queen makes better decisions, colony scratch memory stops bleeding across unrelated work, and the UI becomes more truthful and usable.  
**Contract changes:** 0 new events. The event union stays at 37. Ports stay frozen. `caste_recipes.yaml` is unfrozen for the Queen prompt rewrite. Qdrant gets per-colony scratch collections by convention, not by port change.  
**Estimated LOC delta:** ~350 Python, ~150-220 TypeScript, ~80-120 config/test/docs

---

## Baseline

Wave 21 is now the baseline:

- route modules exist under `src/formicos/surface/routes/`
- the Queen already has 16 tools
- `_MAX_TOOL_ITERATIONS` is already 7
- the capability registry exists

Wave 22 is therefore not an infrastructure wave. It is a product-trust wave.

---

## Why This Wave

Live operator use after Waves 20-21 surfaced three recurring issues.

**1. The Queen still makes obviously bad operational choices.**  
The runtime can already accept `max_rounds`, `budget_limit`, `template_id`, and `strategy`, but the Queen's `spawn_colony` tool still does not expose or pass them through. The prompt also lags the live tool surface and gives weak guidance on team selection. The result is bad defaults, overlong trivial tasks, and coder-only teams where they do not belong.

**2. Colony scratch memory still bleeds across workspace work.**  
`memory_write` still writes to the workspace collection, and `memory_search` still reads the shared workspace collection back. That means Colony A's scratch notes can immediately leak into Colony B. For a system built around handling many distinct tasks, that is the wrong default.

**3. The UI still has truth and usability debt.**  
Raw ISO timestamps, a tiny tree toggle click target, no visible Queen thinking state, misleading cloud cost displays, and weak round-history presentation all reduce trust even when the backend is behaving correctly.

Wave 22 fixes those three problems without expanding the event or protocol surface.

---

## Tracks

### Track A - Queen Judgment + Spawn Controls

**Goal:** The Queen chooses more appropriate teams, budgets, round caps, and templates so simple tasks finish simply and complex tasks get the right structure.

#### A1. Expose spawn controls on `spawn_colony`

The runtime already supports:

- `max_rounds`
- `budget_limit`
- `template_id`
- `strategy`

The Queen's `spawn_colony` tool should expose them and pass them through.

This is the most important low-LOC/high-impact change in the wave. It is the direct fix for "25-round haiku" failures.

Suggested bounds:

- `max_rounds`: clamp to a sane range such as `1..50`
- `budget_limit`: clamp to a sane range such as `0.01..50.0`

#### A2. Rewrite the Queen prompt

Unfreeze `config/caste_recipes.yaml` for the Queen recipe only.

The new prompt should:

- reference the full live tool surface
- explain when to use coder vs reviewer vs researcher vs archivist
- explain trivial/moderate/complex round and budget heuristics
- explicitly recommend template lookup before inventing teams from scratch
- keep the Queen concise and action-first

Key heuristics to encode:

- non-code tasks -> researcher, not coder
- code implementation -> coder + reviewer
- code review -> reviewer first, add coder if fixes are expected
- trivial tasks -> sequential and low round caps
- complex tasks -> larger round caps and budget only when justified

Also update the Queen tool list in the recipe so it matches reality.

#### A3. Improve AG-UI default team

Today the AG-UI endpoint still defaults to a single coder when no castes are supplied.

For Wave 22, improve that default to something less failure-prone. The minimum acceptable step is:

- default to `[coder, reviewer]`

If a lightweight template-aware fallback is easy, that is a bonus, but not required for this wave.

---

### Track B - Scoped Memory + Knowledge Ingestion

**Goal:** Colony scratch memory becomes colony-private, workspace knowledge becomes operator-ingestable, and file scope becomes clearer in the UI.

#### B1. Per-colony scratch collection

Promote scoped scratch memory into an explicit architectural decision.

Rule:

- colony scratch writes go to `scratch_{colony_id}`
- colony scratch reads search:
  - `scratch_{colony_id}`
  - `workspace_id`
  - skill bank collection

This preserves:

- colony-private working memory
- workspace-shared library memory
- skill-bank recall

without changing the VectorPort API.

This decision belongs in:

- `docs/decisions/037-scoped-colony-memory.md`

#### B2. Keep Queen memory search workspace-scoped

The Queen does not belong to a colony. Her `search_memory` tool should continue to search:

- workspace memory
- skill bank

and should not search colony scratch collections by default.

That scope should be explicit in the tool description so operator expectations stay clear.

#### B3. Add explicit workspace knowledge ingestion

The operator can already upload workspace files, but those files are not automatically searchable memory.

Add an explicit ingestion path from the Knowledge view:

- upload file
- write file to workspace files directory
- embed/chunk file
- upsert into workspace memory collection
- preserve provenance metadata

Critical rule:

- only the Knowledge "Library" path embeds
- normal workspace-file upload stays as file storage only

That keeps ingestion an intentional operator action rather than a hidden side effect.

#### B4. Make file scope clearer in colony detail

Colony detail currently shows workspace files, which are the same across all colonies in the workspace.

Make the distinction explicit:

- **Colony Uploads**
- **Workspace Library**

This is mostly a presentation/trust fix, but it also supports the new ingestion story.

#### B5. Make `queen_note` thread-scoped on disk

`queen_note` currently stores notes per workspace.

Wave 22 should move storage to a thread-scoped path such as:

- `data/workspaces/{workspace_id}/threads/{thread_id}/queen_notes.yaml`

Important repo-accurate note:

- this change requires passing `thread_id` into the Queen note path/handler, not just changing a helper string

---

### Track C - UX Truth + Regression Hardening

**Goal:** UI behavior becomes more believable because timestamps, costs, controls, and feedback states all behave the way an operator expects.

#### C1. Relative timestamps

Replace raw ISO rendering with `timeAgo()` in:

- Queen chat
- colony chat
- event rows where applicable

This is a simple fix with an outsized trust payoff.

#### C2. Tree toggle usability

The tree toggle click target is too small.

Wave 22 should enlarge it to a clearly usable target and give it visible hover/interaction affordance. The logic is already fine; the ergonomics are the issue.

#### C3. Queen thinking indicator

Add an honest pending state in Queen chat between message send and first Queen response.

Important rule:

- clear the pending state on real Queen response arrival
- do not use a blind timeout

#### C4. Cost display audit

Make cost surfaces more truthful:

- show "spend not tracked" instead of `$0.00 / $0.00` for cloud spend that is not actually tracked
- show `<$0.01` for nonzero near-zero colony costs
- keep display logic honest about what the system does and does not know

#### C5. Round history centered on output

The round-history view should lead with what the colony produced, not with a dense chronological dump.

Suggested structure:

- Final Output
- Key artifacts / tool use
- Round detail as secondary expandable context

This should reuse data already present in the rounds/transcript-shaped surface rather than inventing another fetch path.

#### C6. Minimal browser smoke path

Add a lightweight browser smoke check for the exact class of regressions Wave 22 is targeting:

- app loads
- tree expands/collapses
- Queen chat accepts input
- timestamps render as relative, not raw ISO

This does not need to become a full frontend test framework. It just needs to catch obvious operator-facing breakage.

---

## Execution Shape

| Team | Track | First lands on | Dependencies |
|---|---|---|---|
| Coder 1 | A | `queen_runtime.py`, `caste_recipes.yaml`, `agui_endpoint.py` | Starts immediately |
| Coder 2 | B | `runner.py`, `routes/colony_io.py`, `knowledge-view.ts`, `colony-detail.ts`, `queen_runtime.py` | Rereads `queen_runtime.py` after Coder 1 |
| Coder 3 | C | frontend components and smoke test | Independent |

### Serialization rules

- Coder 1 lands first on `queen_runtime.py` for spawn controls.
- Coder 2 rereads `queen_runtime.py` before changing `queen_note` storage/thread scope.
- Coder 3 is independent.

### Overlap-prone files

| File | Teams | Resolution |
|---|---|---|
| `src/formicos/surface/queen_runtime.py` | 1 + 2 | Spawn-control changes first, note-path changes second |
| `src/formicos/engine/runner.py` | 2 only | Scratch-memory scope change |
| `src/formicos/surface/routes/colony_io.py` | 2 only | Workspace ingestion path |
| frontend components | 2 + 3 | Different components; keep ownership clear |

---

## Acceptance Criteria

Wave 22 is complete when:

1. The Queen can set `max_rounds`, `budget_limit`, `template_id`, and `strategy` on spawned colonies.
2. Trivial tasks can be spawned with small round caps and sensible strategies.
3. The Queen prompt teaches team selection and resource selection more explicitly.
4. AG-UI no longer defaults to a single coder when castes are omitted.
5. Colony scratch writes land in `scratch_{colony_id}`.
6. Colony scratch reads search colony scratch + workspace memory + skill bank.
7. The Queen's `search_memory` stays workspace-scoped and does not reach into colony scratch by default.
8. Knowledge view can explicitly ingest workspace files into searchable memory with provenance.
9. Colony detail clearly separates colony uploads from workspace library files.
10. `queen_note` is stored per thread, not per workspace.
11. Queen and colony timestamps render relatively, not as raw ISO strings.
12. Tree expand/collapse is comfortably clickable.
13. Queen chat shows a pending/thinking state while awaiting response.
14. Cost displays stop implying tracked spend when spend is not actually tracked.
15. Round history leads with final output.
16. A minimal browser smoke path covers tree/chat/timestamp basics.

### Smoke traces

1. Ask for a trivial haiku -> Queen spawns a small, low-round colony instead of a 25-round default.
2. Ask for a code task -> Queen uses coder + reviewer rather than coder-only by default.
3. Colony A writes scratch memory -> Colony B in the same workspace cannot see it via colony search.
4. Knowledge Library ingest -> uploaded doc becomes searchable in workspace memory with source filename visible.
5. Note saved in Thread A -> not visible when querying notes in Thread B.
6. Queen chat shows relative timestamps and a visible pending state.
7. Cloud spend surfaces show "not tracked" rather than a fake zero meter.

---

## Not In Wave 22

| Item | Reason |
|---|---|
| New events | Capability surface stays frozen |
| New protocol surfaces | Existing protocol set is enough |
| Full vector namespace redesign | Per-collection scratch scope is enough for now |
| Large frontend testing framework rollout | Smoke coverage is enough for this wave |
| RL / self-improvement work | Depends on post-Wave-21 evaluation outcomes |

---

## Final framing

Wave 22 should not feel like "more features." It should feel like the wave where the existing product starts making better decisions, keeps its own scratchpad straight, and stops lying through the UI by accident.
