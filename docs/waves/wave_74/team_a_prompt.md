# Wave 74 Team A: Queen Tab Shell + Display Board + Tool Tracking

## Mission

Restructure the Queen tab into a command surface. Build the display board
(journal extension + `post_observation` Queen tool + sweep auto-posting).
Add tool usage counters. The Queen tab should answer "what does she want
from me?" at the top, with the display board self-populating during
operational sweeps.

## Owned files

- `frontend/src/components/queen-overview.ts` — restructure layout
- `frontend/src/components/queen-display-board.ts` — new display board component
- `frontend/src/components/queen-tool-stats.ts` — new tool stats component
- `src/formicos/surface/operational_state.py` — journal extension
- `src/formicos/surface/queen_tools.py` — `post_observation` tool
- `src/formicos/surface/queen_runtime.py` — tool call counter (lines 1980-2005) + tool inventory injection from `tool_specs()` (lines 1729-1733) + per-workspace initial board population set
- `src/formicos/surface/routes/api.py` — queen-tool-stats endpoint
- `src/formicos/surface/app.py` — sweep auto-posting
- `config/caste_recipes.yaml` — add `post_observation` to Queen tool list

### Do not touch

- `queen_budget.py` (Team B reads it)
- `projections.py`, `events.py`
- `workspace-config.ts`, `workspace-browser.ts` (Team B)
- `queen-overrides.ts` (Team C)
- `queen_runtime.py` `_build_messages()` after line 1733 (Team C injects overrides there; your tool inventory injection is BEFORE line 1733, Team C's is AFTER)

## Repo truth (read before coding)

### Journal current state (operational_state.py)

1. **`append_journal_entry()`** at line 116-138:
   ```python
   def append_journal_entry(
       data_dir: str,
       workspace_id: str,
       source: str,
       message: str,
   ) -> None:
   ```
   Writes: `- [YYYY-MM-DD HH:MM] [source] message\n`
   File: `.formicos/operations/{workspace_id}/queen_journal.md`

2. **`parse_journal_entries()`** at line 180-191:
   Returns: `list[dict[str, str]]` with keys `timestamp`, `source`, `message`.
   Regex: `r"^- \[([^\]]+)\] \[([^\]]+)\] (.*)$"`

3. **Frontend `queen-journal-panel.ts`** already expects a RICHER format:
   ```typescript
   interface JournalEntry {
     timestamp: string;
     heading: string;   // ← NOT in current backend
     body: string;      // ← NOT in current backend
   }
   ```
   The component renders `heading` as a monospace header and `body` below it.
   The backend doesn't produce these fields. This is the seam you're filling.

4. **API endpoint** `GET /api/v1/workspaces/{id}/queen-journal` at api.py:2182
   calls `get_journal_summary()` which returns:
   ```python
   {"exists": bool, "totalEntries": int, "entries": [{timestamp, source, message}]}
   ```

5. **Queen prompt context currently reads raw journal text.**
   `render_journal_for_queen()` uses `read_journal_tail()` raw output. If you
   add metadata comment lines for display-board filtering, those comments will
   leak into Queen context unless you strip them in the read/render path. The
   display board can be rich; the Queen prompt should stay clean.

### Queen tool dispatch (queen_runtime.py)

6. **`_execute_tool()`** at lines 1980-2005 is the single funnel for all
   Queen tool calls:
   ```python
   async def _execute_tool(self, tc: dict[str, Any], workspace_id: str, thread_id: str) -> tuple[str, dict[str, Any] | None]
   ```
   Delegates to `self._tool_dispatcher.dispatch(tc, workspace_id, thread_id)`
   at line 1987. Single return point at line 2005.

7. **`QueenToolDispatcher.dispatch()`** at queen_tools.py:1492-1522.
   Handler registry: `self._handlers.get(name)` at line 1513.

### Operational sweep (app.py)

8. **`_operational_sweep_loop()`** at app.py:929-1098. Default interval 1800s
   (30 min). Steps in order:
   - Line 950: `run_proactive_dispatch()`
   - Line 956: knowledge scan (stub)
   - Line 977: continuation proposals + idle execution
   - Line 999: workflow patterns (stub)
   - Line 1021: approved-action processing + compaction

   **No end-of-sweep summary is written.** This is where auto-posting goes.

### Queen overview current sections (queen-overview.ts)

9. The current queen-overview.ts has 14 sections. What stays vs moves:

   **STAYS (elevated/reorganized):**
   - Proactive briefing (`<fc-proactive-briefing>`, line 200)
   - Budget panel (`<fc-budget-panel>`, line 211)
   - Project plan card (`<fc-project-plan-card>`, line 214)
   - Approval queue (`<fc-approval-queue>`, line 217)
   - Active plans (`_renderActivePlans()`, line 223)
   - Queen chat column (lines 269-278)

   **MOVES TO WORKSPACE (Team B handles the receiving side):**
   - Colony cards — running by workspace (lines 242-259)
   - Recent completions (lines 262-267)
   - Service colonies (`_renderServiceColonies()`, line 240)

   **REMOVE (redundant with new sections):**
   - Health grid (lines 226-230) — replaced by autonomy card (Team B)
   - Learning card (line 233) — can stay or move
   - Config memory (lines 236-238) — subsumed by overrides (Team C)

   **NEW (you build):**
   - Display board (top of page)
   - Tool stats panel

10. **You are the single composition owner for `queen-overview.ts`.**
    Team B and Team C ship child components plus prop contracts. You mount:
    - `fc-queen-continuations`
    - `fc-queen-autonomy-card`
    - `fc-queen-budget-viz`
    - existing `fc-operating-procedures-editor`
    - `fc-queen-overrides`
    - `fc-queen-tool-stats`
    Keep `queen-overview.ts` single-owner so the wave parallelizes cleanly.

## Track 1: Extend journal for display board

### 1a. Extend `append_journal_entry()` signature

Add optional `heading` and `metadata` parameters. Backward-compatible — all
existing callers pass only `source` and `message`.

```python
def append_journal_entry(
    data_dir: str,
    workspace_id: str,
    source: str,
    message: str,
    *,
    heading: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
```

**New format when heading is provided:**
```
- [YYYY-MM-DD HH:MM] [source] [heading] message
```

When heading is empty, write the old format (backward-compatible):
```
- [YYYY-MM-DD HH:MM] [source] message
```

If `metadata` is provided, write it as a JSON comment on the next line:
```
- [YYYY-MM-DD HH:MM] [queen] [Knowledge Gap] 3 entries with conflicting confidence
  <!-- {"display_board":true,"type":"concern","priority":"attention"} -->
```

### 1b. Extend `parse_journal_entries()` regex

Update the regex to capture the optional heading:
```python
_JOURNAL_ENTRY_RE = re.compile(
    r"^- \[([^\]]+)\] \[([^\]]+)\](?: \[([^\]]+)\])? (.*)$",
)
```

Return dict now includes:
```python
{
    "timestamp": str,
    "source": str,
    "heading": str | None,  # group 3, None if legacy format
    "message": str,         # group 4 (or group 3 if no heading)
}
```

Also parse the metadata comment from the following line if present.

### 1c. Keep metadata out of Queen prompt context

If you write metadata comment lines like:
```html
<!-- {"display_board":true,"type":"concern","priority":"attention"} -->
```
update the journal read/render path so those lines do not flow into Queen
context. Minimum acceptable fix:
- `read_journal_tail()` strips metadata comment lines, or
- `render_journal_for_queen()` filters them before prompt injection.

The operator/UI should see metadata; the Queen should see only natural-language
journal content.

### 1d. Update `get_journal_summary()` response

Map the parsed entries to match the frontend's expected shape:
```python
{
    "timestamp": entry["timestamp"],
    "heading": entry.get("heading") or entry["source"],  # fallback: source becomes heading
    "body": entry["message"],
    "source": entry["source"],
    "metadata": entry.get("metadata"),  # None for legacy entries
}
```

This bridges the existing mismatch: legacy entries get `source` as heading,
new entries get the explicit heading. The frontend's `JournalEntry` interface
is already compatible.

## Track 2: Display board frontend component

### 2a. New `queen-display-board.ts`

Fetches from `GET /api/v1/workspaces/{id}/queen-journal` and filters entries
where `metadata?.display_board === true` (or shows all entries if few exist).

```typescript
@customElement('fc-queen-display-board')
export class FcQueenDisplayBoard extends LitElement {
  @property() workspaceId = '';
  @state() private _entries: JournalEntry[] = [];
  @state() private _loading = false;
```

Renders entries as cards grouped by priority:
- `urgent` → red left border, appears first
- `attention` → amber left border
- `normal` → no accent

Each card shows: heading (bold), body text, timestamp (dim), source badge.

If no display board entries exist, show a subtle empty state:
```html
<div class="empty-hint">No observations yet. The Queen posts here during operational sweeps.</div>
```

### 2b. Placement in queen-overview.ts

At the TOP of the left column, before everything else. This is the answer to
"what does she want from me?"

```html
<fc-queen-display-board .workspaceId=${this.activeWorkspaceId}></fc-queen-display-board>
```

### 2c. CSS

```css
.board-card {
  padding: 10px 12px; margin-bottom: 6px;
  border-left: 3px solid transparent;
  font-family: var(--f-mono); font-size: 11px;
}
.board-card.urgent { border-left-color: var(--v-danger, #ef4444); }
.board-card.attention { border-left-color: var(--v-warning, #f59e0b); }
.board-heading { font-weight: 600; color: var(--v-fg); margin-bottom: 3px; }
.board-body { color: var(--v-fg-dim); line-height: 1.5; }
.board-meta { font-size: 9px; color: var(--v-fg-muted); margin-top: 4px; }
```

## Track 3: `post_observation` Queen tool

### 3a. Add tool to queen_tools.py

In `tool_specs()` (before the `*self._addon_tool_specs` line at 1485), add:

```python
{
    "name": "post_observation",
    "description": "Post a structured observation to the display board. Use for status updates, flagged concerns, notable findings. The operator sees these when they open the Queen tab.",
    "parameters": {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["observation", "status", "concern", "metric"],
                "description": "Kind of observation.",
            },
            "priority": {
                "type": "string",
                "enum": ["normal", "attention", "urgent"],
                "description": "Display priority. Use 'urgent' sparingly — only for items requiring immediate operator action.",
            },
            "title": {
                "type": "string",
                "description": "Short heading (under 80 chars).",
            },
            "content": {
                "type": "string",
                "description": "Body text with details. Keep under 200 chars.",
            },
        },
        "required": ["type", "title", "content"],
    },
},
```

### 3b. Add handler in dispatch registry

In `QueenToolDispatcher.__init__()` where handlers are registered:

```python
self._handlers["post_observation"] = self._post_observation
```

Implementation:

```python
async def _post_observation(
    self, inputs: dict[str, Any], workspace_id: str, thread_id: str,
) -> tuple[str, dict[str, Any] | None]:
    from formicos.surface.operational_state import append_journal_entry

    obs_type = inputs.get("type", "observation")
    priority = inputs.get("priority", "normal")
    title = inputs.get("title", "")
    content = inputs.get("content", "")

    data_dir = self._runtime.settings.system.data_dir
    append_journal_entry(
        data_dir, workspace_id,
        source="queen",
        message=content,
        heading=f"{obs_type}:{priority} — {title}",
        metadata={"display_board": True, "type": obs_type, "priority": priority},
    )
    return (f"Posted {obs_type}: {title}", None)
```

### 3c. Add to caste recipe

In `config/caste_recipes.yaml`, add `"post_observation"` to the Queen's
tools list (line 207). Update the tool count comment from `## Tools (41)`
to `## Tools (42)`.

## Track 4: Tool usage counter

### 4a. Add counter to QueenRuntime

In `queen_runtime.py`, add instance attributes (in `__init__` or wherever
instance state is initialized):

```python
self._tool_call_counts: dict[str, int] = {}
self._tool_last_status: dict[str, str] = {}
```

### 4b. Instrument `_execute_tool()`

At the single return point (line 2005), before `return result`:

```python
tool_name = tc.get("name", "")
self._tool_call_counts[tool_name] = self._tool_call_counts.get(tool_name, 0) + 1
self._tool_last_status[tool_name] = "error" if (result[1] is None and "failed" in result[0].lower()) else "ok"
```

Keep it simple. Don't over-engineer the error detection — `"ok"` vs `"error"`
based on result text is sufficient for a session-scoped counter.

### 4c. Add endpoint

In `routes/api.py`, add:

```python
async def get_queen_tool_stats(request: Request) -> JSONResponse:
    """Return session-scoped Queen tool call counts."""
    runtime = request.app.state.runtime
    queen = runtime.queen
    counts = getattr(queen, "_tool_call_counts", {})
    statuses = getattr(queen, "_tool_last_status", {})
    tools = [
        {"name": name, "calls": count, "last_status": statuses.get(name, "unknown")}
        for name, count in sorted(counts.items(), key=lambda x: -x[1])
    ]
    return JSONResponse({"tools": tools, "total_calls": sum(counts.values())})
```

Route: `Route("/api/v1/queen-tool-stats", get_queen_tool_stats)`

### 4d. Frontend component `queen-tool-stats.ts`

Compact table sorted by call count. Shows: tool name, call count, last status
dot (green/red). No pagination needed — 42 tools max.

```typescript
@customElement('fc-queen-tool-stats')
export class FcQueenToolStats extends LitElement {
  @state() private _tools: { name: string; calls: number; last_status: string }[] = [];
  @state() private _total = 0;
```

Fetch from `/api/v1/queen-tool-stats` on connected + periodic refresh.

## Track 5: Sweep auto-posting

### 5a. Create new `post_sweep_observations()` function

This function does NOT exist yet. Create it as a pure function in
`operational_state.py` (or a new small module `sweep_observations.py` if
you prefer — but operational_state.py is simpler):

```python
def post_sweep_observations(
    data_dir: str,
    workspace_id: str,
    summary: dict[str, Any],
    projections: ProjectionStore,
) -> int:
    """Post notable findings from the operational sweep to the display board.
    Returns the number of observations posted."""
    posted = 0

    # Ready continuations
    ready = [c for c in summary.get("continuation_candidates", []) if c.get("ready_for_autonomy")]
    if ready:
        append_journal_entry(
            data_dir, workspace_id, source="maintenance",
            message=f"{len(ready)} continuation(s) ready for autonomous execution",
            heading="status:normal — Continuations ready",
            metadata={"display_board": True, "type": "status", "priority": "normal"},
        )
        posted += 1

    # Failed colonies (check recent outcomes)
    # ... similar pattern for stale knowledge, budget warnings, etc.

    return posted
```

### 5b. Call from sweep loop

At the end of `_operational_sweep_loop()` in app.py, after the action
processing block (the last `except` at line 1094-1095), before the function's
sleep/loop continues. The function is defined at line 929.

**Important:** `build_operations_summary()` is NOT async. Its signature is:
```python
def build_operations_summary(data_dir: str, workspace_id: str, projections=None) -> dict
```

Call it correctly:
```python
# Post operational observations to display board
from formicos.surface.operational_state import post_sweep_observations
from formicos.surface.operations_coordinator import build_operations_summary

summary = build_operations_summary(
    data_dir_str,  # already available in the sweep loop scope
    ws_id,
    runtime.projections,
)
post_sweep_observations(data_dir_str, ws_id, summary, runtime.projections)
```

Keep the heuristics conservative. Start with 3-4 observation types:
- Ready continuations
- Failed colonies in last sweep period
- Budget utilization > 80%
- Stale knowledge clusters

Don't over-post. The display board should have 2-5 items, not 20.

### 5c. Populate display board on first respond() per workspace

The sweep runs every 30 minutes. If the operator opens the Queen tab immediately
after starting FormicOS, the display board is empty. Fix this by also calling
`post_sweep_observations()` on the first `respond()` call for each workspace.

In `queen_runtime.py`, add a per-workspace set:
```python
self._board_populated_workspaces: set[str] = set()
```

At the start of `respond()` (or the warm-start entry point), before the LLM call:
```python
if workspace_id and workspace_id not in self._board_populated_workspaces:
    from formicos.surface.operational_state import post_sweep_observations
    from formicos.surface.operations_coordinator import build_operations_summary
    summary = build_operations_summary(data_dir, workspace_id, self._runtime.projections)
    post_sweep_observations(data_dir, workspace_id, summary, self._runtime.projections)
    self._board_populated_workspaces.add(workspace_id)
```

This is ~6 lines. Each workspace gets its own initial population on first
interaction. The set resets on restart (session-scoped, like tool counters).

## Track 6: Self-assembling tool inventory in system prompt

### 6a. Reconcile the full tool surface vs system prompt

Before any tool count update, actually count the tools. The full tool surface
is `self._tool_dispatcher.tool_specs()`, NOT `_handlers.keys()`. Three sources
contribute to `tool_specs()`:

1. **`_handlers` dict** (queen_tools.py:167-215) — ~37 tools with direct dispatch
2. **Special-cased tools** — `archive_thread` and `define_workflow_steps` are in
   `tool_specs()` but NOT in `_handlers`; they're dispatched via `DELEGATE_THREAD`
   sentinel in `_execute_tool()` (queen_runtime.py:1992-2003)
3. **Addon tools** — `*self._addon_tool_specs` (queen_tools.py:1485), appended
   dynamically by `app.py` addon loader

If you derive from `_handlers.keys()` you'll miss #2 and #3. Derive from
`tool_specs()` — that's the canonical full surface.

Verify: count the names returned by `tool_specs()` and compare with the `## Tools`
section in the caste recipe system prompt. Reconcile any mismatches. Tools in
`tool_specs()` but not in the system prompt are callable but invisible to the
Queen's reasoning. Tools in the system prompt but not in `tool_specs()` will
cause call errors.

### 6b. Make the tool section self-assembling

In `caste_recipes.yaml`, replace the `## Tools (36)` section and the manually
listed tool names with a single placeholder line. Keep any category prose above
it if desired, but the tool name list itself becomes:
```yaml
system_prompt: |
  ...existing prose sections...
  {TOOL_INVENTORY}
```

Note: the placeholder is just `{TOOL_INVENTORY}` — it does NOT include a
`## Tools` heading. The replacement code generates the heading.

In `queen_runtime.py` `_build_messages()`, after reading the base prompt (line 1732)
and BEFORE `messages.append()` (line 1733), inject the live tool inventory:

```python
# Derive tool inventory from the full tool surface (tool_specs),
# not _handlers alone — includes special-cased + addon tools
all_specs = self._tool_dispatcher.tool_specs()
tool_names = [s["name"] for s in all_specs]
tool_section = f"## Tools ({len(tool_names)})\n{', '.join(sorted(tool_names))}"
system_prompt = system_prompt.replace("{TOOL_INVENTORY}", tool_section)
```

This is ~5 lines. After this, the Queen's system prompt always reflects the
actual callable tools — handlers, special-cased, and addon tools. No manual
count updates. No drift.

**Note:** This modifies the `system_prompt` string before it's appended to
messages at line 1733. Team C's override injection goes AFTER the append.
No conflict.

## Track 7: Queen tab restructure

### 7a. Remove colony cards from queen-overview.ts

Delete these sections:
- Service colonies (`_renderServiceColonies()`, line 240)
- Running colonies by workspace (lines 242-259)
- Recent completions (lines 262-267)

Also remove:
- Health grid (lines 226-230) — replaced by Team B's autonomy card
- Config memory (lines 236-238) — replaced by Team C's overrides

### 7b. New layout order

The left column should render in this order:

1. `<fc-queen-display-board>` — what does she want from me?
2. `<fc-project-plan-card>` + `<fc-approval-queue>` — what is she doing?
3. `_renderActivePlans()` — active parallel plans
4. `<fc-queen-continuations>` — Team B component
5. `<fc-operating-procedures-editor>` — existing component, elevated here
6. `<fc-queen-autonomy-card>` + `<fc-queen-budget-viz>` — Team B components
7. `<fc-queen-overrides>` — Team C component
8. `<fc-queen-tool-stats>` — tool usage

Do not leave placeholder comments as the end state. You are the integrator for
the Queen shell and should mount the actual components once their contracts are
known.

The right column stays as Queen chat (collapsible rail).

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
cd frontend && npm run build
```

Verify in the running stack:
- Display board renders (may be empty initially)
- `post_observation` tool callable from Queen chat ("post an observation that tests are failing")
- Tool stats endpoint returns data after Queen interactions
- Colony cards no longer on Queen tab

## Acceptance criteria

- [ ] `append_journal_entry()` accepts optional `heading` and `metadata`
- [ ] `parse_journal_entries()` handles both legacy and new format
- [ ] API returns entries with `heading` and `body` fields
- [ ] Display board component renders filtered journal entries with priority styling
- [ ] Journal metadata comments are stripped from Queen prompt context
- [ ] `post_observation` Queen tool exists with type/priority/title/content params
- [ ] `post_observation` added to Queen caste recipe (42 tools total)
- [ ] Tool call counter incremented in `_execute_tool()` at line 2005
- [ ] `GET /api/v1/queen-tool-stats` returns sorted tool call counts
- [ ] Sweep auto-posts observations for ready continuations, failed colonies, budget warnings
- [ ] Display board populated on first `respond()` call (no 30-min wait)
- [ ] Tool inventory section in Queen system prompt is self-assembled from `tool_specs()` (full surface: handlers + special-cased + addon tools)
- [ ] `{TOOL_INVENTORY}` placeholder in caste recipe replaced at runtime with live tool list
- [ ] `tool_specs()` output reconciled with system prompt tool names (no ghost tools, no missing tools)
- [ ] Colony cards, service colonies, recent completions removed from Queen tab
- [ ] Health grid removed (replaced by Team B's autonomy card)
- [ ] Queen tab mounts Team B components, existing procedures editor, and Team C overrides component
- [ ] No regressions — all tests pass, frontend builds clean
