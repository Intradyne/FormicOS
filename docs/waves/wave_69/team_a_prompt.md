# Wave 69 — Team A: Enriched Queen Chat

**Theme:** The Queen chat shows what happened, not just that something
happened.

## Context

Read `docs/waves/wave_69/wave_69_plan.md` first. This is a rendering wave —
the backend data already exists. Your job is to surface it in the chat.

Read `CLAUDE.md` for hard constraints. Read `docs/design-system-v4.md` for
the Void Protocol design system — every new component must follow it.

## Your Files (exclusive ownership)

### Frontend
- `frontend/src/components/queen-chat.ts` — inline progress cards,
  consulted-sources chips, diff preview enrichment, plan progress bar
- `frontend/src/components/colony-progress-card.ts` — **new**, reactive
  inline colony progress card
- `frontend/src/components/consulted-sources.ts` — **new**, citation chip
  strip
- `frontend/src/types.ts` — new type additions only (additive)
- `frontend/src/state/store.ts` — colony state subscription helpers
  (additive)

### Backend
- `src/formicos/surface/queen_runtime.py` — `consulted_entries` metadata
  on QueenMessage emission (small addition)
- `src/formicos/surface/runtime.py` — `retrieve_relevant_memory()` return
  type change only (return `(str, list)` tuple instead of `str`)
- `src/formicos/surface/routes/api.py` — thread plan read endpoint (small
  addition)

### Tests
- `tests/unit/surface/test_plan_read_endpoint.py` — **new**

## Do Not Touch

- `frontend/src/components/knowledge-browser.ts` — Team B owns
- `frontend/src/components/knowledge-view.ts` — Team B owns
- `frontend/src/components/settings-view.ts` — Team C owns
- `frontend/src/components/model-registry.ts` — Team C owns
- `frontend/src/components/addons-view.ts` — Team C owns
- `src/formicos/surface/projections.py` — no projection changes
- `src/formicos/core/events.py` — no new events
- `src/formicos/core/types.py` — no type changes
- `src/formicos/surface/knowledge_catalog.py` — no retrieval changes
- `config/caste_recipes.yaml` — stable from Wave 68

## Overlap Coordination

- Team B may add search result types to `types.ts`. Team C does not touch
  types. All additions are additive — no conflicts.
- Team B may add state to `store.ts` for search results. Your colony
  subscription additions are in a different area. Additive.
- `formicos-app.ts` — Team C may adjust nav items. You do not touch the
  nav. No conflict.

---

## Track 1: Inline Colony Progress Cards

### Problem

When the Queen spawns a colony, the operator must navigate to the colony
detail tab to see what's happening. The chat shows a preview card (spawn
intent) and later a result card (completion), but nothing in between. The
operator can't see progress without leaving the chat.

### Data already available

The store already processes these WebSocket events in real time:

- `ColonySpawned` (store.ts:247) — creates tree node with initial state
- `RoundStarted` (store.ts:369) — updates `colony.round`
- `RoundCompleted` (store.ts:374) — pushes to `convergenceHistory`
- `ColonyCompleted` / `ColonyFailed` — terminal state

The colony tree node carries: `round`, `maxRounds`, `status`, `caste`,
`strategy`, `convergenceHistory[]`, `cost`.

### Implementation

**1. New component `colony-progress-card.ts`.**

A reactive Lit component that subscribes to store updates for a specific
colony and renders inline progress:

```typescript
@customElement('fc-colony-progress')
export class ColonyProgressCard extends LitElement {
  @property() colonyId = '';
  @property() task = '';
  private _unsub?: () => void;

  connectedCallback() {
    super.connectedCallback();
    this._unsub = store.subscribe(() => this.requestUpdate());
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this._unsub?.();
  }

  render() {
    const node = findNode(store.state.tree, this.colonyId);
    if (!node) return nothing;
    // ... render progress
  }
}
```

This follows the exact subscription pattern from `colony-detail.ts`
(lines 285–307): subscribe on connect, unsubscribe on disconnect,
`requestUpdate()` on store change.

**Render states:**

- **Running:** Glass card with progress bar (round N / maxRounds), caste
  badge, strategy label, cost accumulator. If `convergenceHistory` has
  data, show a 3-line sparkline (tiny inline SVG, ~40x16px).
- **Completed:** Transition to compact result: success/failure indicator,
  files changed count, cost, quality score. Use `fc-dot` for status.
- **Failed:** Same compact result with danger styling.

Style with Void Protocol tokens. Card should be narrow — same width as
a text message, not full-width like preview cards.

**2. Mount progress cards in `queen-chat.ts`.**

In the message render dispatch (queen-chat.ts:212–345), after a
`preview_card` message that carries `meta.tool === 'spawn_colony'` and
`meta.colony_id`, insert a `<fc-colony-progress>` card. The progress card
renders below the preview card and updates reactively as the colony runs.

When the colony completes, the Queen emits a `result_card` message. At
that point the progress card can transition to its compact completed state
or be replaced by the result card. Prefer transition — it's less jarring.

**Detection logic:** When iterating messages, look for preview_card
messages where `meta?.tool === 'spawn_colony'` or where the action dict
from `queen_tools.py` includes `colony_id`. The colony ID is available
in `meta.colony_id` (see queen_tools.py spawn return at line 1536:
`{"tool": "spawn_colony", "colony_id": colony_id}`).

For `spawn_parallel`, the meta carries `colony_ids: string[]`. Render
one progress card per colony, or a grouped progress card that shows all
colonies in the parallel group with individual progress rows.

**3. Handle terminal state transition.**

When a `result_card` message arrives for the same `colonyId`, the
progress card should stop updating. Check if a later message in the
array has `render === 'result_card'` and matching `meta.colonyId`. If
so, render the progress card in its completed compact state (not the
full running state).

---

## Track 2: Consulted Sources

### Problem

When the Queen's response is informed by knowledge entries (via the
deliberation frame from Wave 68 Track 4, or via `memory_search` tool
results), the operator can't see which knowledge was consulted. The Queen
says "based on prior experience" but doesn't link to the actual entry.

### Correct framing

This is "consulted sources," not "citations." The deliberation frame
injects knowledge entries as context before the LLM call. The Queen
doesn't explicitly cite them — they were available during reasoning. The
UI should reflect this honestly: "Consulted Knowledge" or "Sources
Available," not "References" or "Citations."

### Implementation

**1. Backend: emit `consulted_entries` on QueenMessage metadata.**

In `queen_runtime.py`, in `respond()`, after the deliberation frame is
built (lines 1047–1070), record the knowledge entry IDs that were
injected. The deliberation frame's `_build_deliberation_frame()` method
assembles institutional memory coverage from projections — it has access
to the top domains and their entry counts.

Add to the response metadata:

```python
# After deliberation frame injection and before the LLM call
_consulted: list[dict[str, Any]] = []
```

Populate `_consulted` from real knowledge entries only:

1. **Memory retrieval results** — `respond()` calls
   `self._runtime.retrieve_relevant_memory()` (queen_runtime.py:892)
   which delegates to `catalog.search()` (runtime.py:1183) and returns
   a **formatted string**, not the structured results list.

   To capture structured entries, either:
   - **(preferred)** Have `retrieve_relevant_memory()` return a
     `(text, items)` tuple instead of just the string. The items list
     is already built at runtime.py:1183 — return it alongside the
     formatted text. Update the call site in `respond()` to unpack both.
   - **(alternative)** Call `catalog.search()` directly in `respond()`
     before `retrieve_relevant_memory()`, but this duplicates the search.

   With the structured results available, extract the top 5:
   ```python
   for _item in _memory_items[:5]:
       _consulted.append({
           "id": _item.get("id", ""),
           "title": _item.get("title", "")[:80],
           "confidence": round(_item.get("confidence", 0.5), 2),
       })
   ```

   **Note:** `retrieve_relevant_memory()` lives in `runtime.py` (line
   1163), not in `queen_runtime.py`. You own changes in
   `queen_runtime.py` but need a small edit to `runtime.py` for the
   return type change. This is the only runtime.py touch — keep it
   minimal.

Do **not** fabricate synthetic consulted entries like `__deliberation__`
or attach fake `confidence: 1.0` summaries. If you want to preserve the
fact that a deliberation frame was present, that belongs in a separate
label or boolean metadata field, not in the consulted-entry list.

Attach to the QueenMessage emission:

```python
if _consulted:
    # Add to the meta dict of the response QueenMessage
    _response_meta["consulted_entries"] = _consulted
```

The exact insertion point: `_emit_queen_message()` is called at the end
of the tool loop / response generation. The meta dict is already passed
through. Add `consulted_entries` to it.

**2. Frontend: `consulted-sources.ts` component.**

A horizontal strip of clickable chips rendered below a Queen message
when `meta.consulted_entries` is present.

Each chip shows:
- Entry title (truncated to ~40 chars)
- Confidence indicator: `fc-dot` with status mapping
  (`confidence >= 0.7` → loaded/green, `>= 0.4` → pending/gold,
  else → error/red)
- Click navigates to the knowledge browser detail view for that entry ID

Only render chips for real entry IDs. If a separate summary label exists,
render it as plain muted text, not as a pseudo-entry chip.

**3. Mount in `queen-chat.ts`.**

In the text message render path (queen-chat.ts:329–344), after the
message text, check `m.meta?.consulted_entries`. If present and non-empty,
render `<fc-consulted-sources .entries=${entries}></fc-consulted-sources>`.

---

## Track 3: Inline Diff Preview

### Problem

When a colony produces file changes (via `edit_file`), the result card
shows success/failure and cost, but not what changed. The operator must
navigate to workspace browser to see the diff.

### Data already available

- `EditProposalMeta` (types.ts:244–249) carries `filePath`, `diff`,
  `reason`, `colonyId`. This is already rendered by `fc-edit-proposal`.
- `ResultCardMeta` (types.ts:212–226) carries `colonyId` but not diff
  data directly.

### Implementation

**1. Enhance `fc-result-card` with a diff summary section.**

When a result card's colony produced file changes, show a compact diff
summary below the result stats. The diff data is not currently on
`ResultCardMeta` — it would need to come from the colony's artifact
output.

**Simpler approach:** The `edit_proposal` card type already renders
diffs inline via `fc-edit-proposal`. For result cards, add a small
"Files Changed" badge showing the count. Clicking expands to show the
file list. Each file entry links to the workspace browser.

The colony's file changes are tracked in the colony tree node — the
store processes `ArtifactCreated` events. Check whether the tree node
carries artifact/file data. If not, the simplest path is a small API
call: `GET /api/v1/colonies/{id}/transcript` already returns the full
transcript which includes file operations.

**2. For `edit_proposal` cards: already handled.**

The `fc-edit-proposal` component already renders inline diff. No changes
needed. This track is about enriching `result_card` — the post-completion
summary.

**Scope note:** Keep this lightweight. A "Files: 3 changed" badge with
expandable file list is sufficient. Full inline diff rendering is
already handled by `edit_proposal` cards. Don't duplicate that work.

---

## Track 4: Plan Progress Bar

### Problem

Wave 68 Track 1 persists plans to `.formicos/plans/{thread_id}.md`. The
Queen reads them for attention injection. But the operator can't see the
plan state at a glance without reading through conversation history.

### Implementation

**1. Backend: thread plan read endpoint.**

Add a small GET endpoint in `routes/api.py`:

```python
GET /api/v1/workspaces/{workspace_id}/threads/{thread_id}/plan
```

Read `.formicos/plans/{thread_id}.md` from the data directory. Parse the
`## Steps` section into structured data:

```python
# Return shape:
{
    "exists": true,
    "title": "Plan: Implement auth module",
    "approach": "Use OAuth2 with JWT tokens",
    "steps": [
        {"index": 0, "status": "completed", "description": "Set up OAuth provider", "colony_id": "abc123", "note": "Done, merged."},
        {"index": 1, "status": "started", "description": "Write integration tests", "colony_id": "def456"},
        {"index": 2, "status": "pending", "description": "Update API docs"}
    ]
}
```

If no plan file exists, return `{"exists": false}`.

The step format in the file (from Wave 68 Team A prompt):
```markdown
## Steps
- [0] [started] Implement auth module (colony abc12345)
- [1] [pending] Write integration tests
- [2] [completed] Update API docs — Done, merged.
```

Parse with a simple regex. This is a read-only endpoint — the Queen
writes plans via `propose_plan` and `mark_plan_step` tools.

**2. Frontend: plan progress bar in `queen-chat.ts`.**

Below the thread tabs and above the message list, render a persistent
plan progress bar when the active thread has a plan.

On thread switch or mount, fetch the plan:
```typescript
const res = await fetch(`/api/v1/workspaces/${wsId}/threads/${threadId}/plan`);
const plan = await res.json();
```

If `plan.exists`:
- Render a slim horizontal bar (glass card, 36px height) with:
  - Plan title (truncated)
  - Step indicators: small circles in a row. Green filled = completed,
    accent ring = started, dim = pending, red = blocked.
  - Step count: "2/5 completed"
- Clicking the bar expands to show the full step list with descriptions.

Poll or refresh the plan on each new QueenMessage (the plan may update
when `mark_plan_step` is called). A simple fetch on message arrival is
sufficient — this is not a real-time subscription, it's a read-heavy
file that changes infrequently.

**3. Write `tests/unit/surface/test_plan_read_endpoint.py`.**

4 tests:
1. `test_plan_endpoint_returns_parsed_steps` — write a plan file with
   steps, hit the endpoint, assert structured response.
2. `test_plan_endpoint_no_file_returns_not_exists` — no plan file,
   assert `{"exists": false}`.
3. `test_plan_endpoint_parses_colony_ids` — step with `(colony abc123)`,
   assert `colony_id` field populated.
4. `test_plan_endpoint_handles_malformed_gracefully` — garbage file
   content, assert no crash, returns partial data.

---

## Track 5: AG-UI Compatible Event Shapes (Tail Item)

### Problem

AG-UI defines standard event types for agent interaction. The existing
WebSocket events carry equivalent data but in custom shapes. A thin
compatibility layer would make future AG-UI client integration easier.

### Priority

This is a **tail item**. Only implement if Tracks 1–4 land cleanly.
Do not let this slow the card work. It is an internal adapter, not
user-facing.

### Implementation

Create `frontend/src/agui-compat.ts` (~50 lines). Map:

| FormicOS Event | AG-UI Shape | Notes |
|----------------|-------------|-------|
| `ColonySpawned` | `STEP_STARTED` | `stepId = colonyId` |
| `ColonyCompleted` / `ColonyFailed` | `STEP_FINISHED` | `status = success/error` |
| `QueenToolCallCompleted` (if exists) | `TOOL_CALL_END` | Tool name + result |
| Thread state delta | `STATE_DELTA` | Partial state update |

Export mapping functions, not a transport layer. The colony progress
card can optionally consume these mapped shapes internally.

---

## Empty States

First-run quality matters for a product surface. Handle:

- **Empty thread (no messages):** Show a centered prompt hint:
  "Ask the Queen anything — she'll plan, delegate, and track."
- **No active plan:** Plan progress bar hidden (not empty-state shown).
- **No colonies spawned yet:** No progress cards (nothing to show).
- **Colony completed with no file changes:** Result card shows stats
  only, no diff section.

---

## Acceptance Gates

- [ ] Colony progress cards render inline and update reactively
- [ ] Progress cards transition cleanly on colony completion
- [ ] Consulted-sources chips appear below Queen responses when entries
      were available
- [ ] Chips are labeled "Consulted Knowledge," not "Citations"
- [ ] Chips link to knowledge browser detail view
- [ ] Result cards show "Files Changed" count when applicable
- [ ] Plan progress bar renders below thread tabs when plan exists
- [ ] Plan read endpoint returns structured step data
- [ ] No new event types added
- [ ] No projection changes
- [ ] All new components follow Void Protocol design system
- [ ] `prefers-reduced-motion` respected on animations

## Validation

```bash
npm run build
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
pytest tests/unit/surface/test_plan_read_endpoint.py -v
```
