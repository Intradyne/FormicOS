# Wave 73 Team C: Settings Protocol Detail + Addon Polish + Documentation

## Mission

Verify the Settings protocol section shows the detail that topbar badges
used to show. Add search and health summary to the addons view. Write the
developer bridge documentation and refresh CLAUDE.md to reflect 73 waves
of evolution.

## Owned files

- `frontend/src/components/settings-view.ts` — protocol detail verification
- `frontend/src/components/addons-view.ts` — search filter, health summary
- `CLAUDE.md` — refresh
- `docs/DEVELOPER_BRIDGE.md` — new developer-facing guide (repo-level, for
  FormicOS contributors and users). Distinct from `.formicos/DEVELOPER_QUICKSTART.md`
  which Team A's `init-mcp` generates in end-user project directories.

### Do not touch

- `mcp_server.py` (Team A)
- `colony-creator.ts` (Team B)
- `template-editor.ts` (Team B)
- `formicos-app.ts` (Team B)
- `addon_loader.py`, `projections.py`, `events.py`

## Repo truth (read before coding)

### Protocol detail in settings-view.ts

1. **`_renderProtocolsSummary()`** at lines 680-723 — Wave 72.5 Team C
   already added protocol detail. Current implementation shows:
   - MCP: tool count from `(mcpProto as any)?.tools ?? 0`
   - AG-UI: event count (conditional on active status)
   - A2A: semantics + endpoint (conditional on active status)
   - Each row: status dot + name + detail span + status pill

2. **Verify this is complete.** The topbar badges (removed by Wave 72.5
   Team A) showed:
   - MCP: `{tools} tools`
   - AG-UI: `{events} events` or `inactive`
   - A2A: `{semantics} {endpoint}` or `inactive`

   If `_renderProtocolsSummary()` already shows all of this, mark Track 1
   as pre-completed and move on. If any detail is missing, add it.

3. **`.proto-detail` CSS** — check if this class exists in the component's
   styles. If not, add:
   ```css
   .proto-detail {
     font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim);
     margin-left: 4px;
   }
   ```

### Addons view (addons-view.ts)

4. **Read the full file.** Wave 72.5 Teams B and C expanded it significantly:
   - Sidebar list with addon cards
   - Detail panel with tools table (Try buttons), handlers, triggers, config
   - Error card with retry
   - Enable/disable toggle
   - "Trigger Now" buttons

5. **What's missing:**
   - **Search/filter**: No text input to filter the addon list
   - **Health summary card**: No aggregate stats at the top of the detail view

### Current MCP state (for CLAUDE.md)

6. **After Wave 73 Team A lands**, the MCP server will have:
   - 27 tools (22 existing + addon_status, toggle_addon, trigger_addon,
     log_finding, handoff_to_formicos)
   - 9 resources (6 existing + plan, procedures, journal)
   - 6 prompts (2 existing + morning-status, delegate-task,
     review-overnight-work, knowledge-for-context)
   - `init-mcp` CLI command
   Note: `log_finding` and `handoff_to_formicos` are tools (mutating), not
   prompts. MCP prompts must be read-only.

7. **Coordinate with Team A**: Get the final list of tools/prompts/resources
   before writing docs. If Team A's work isn't merged yet, write docs based
   on the plan and note that they'll be updated when Team A lands.

## Track 1: Verify Settings protocol section

### 1a. Read `_renderProtocolsSummary()`

Read settings-view.ts lines 680-723. Verify it shows:
- MCP tool count
- AG-UI event count (when active)
- A2A semantics + endpoint (when active)

### 1b. If already complete

Wave 72.5 Team C's acceptance report claimed this was done. If the code
confirms it, document it as pre-completed in your acceptance report.

### 1c. If any detail is missing

Add the missing detail following the pattern already established. The data
is in `this.protocolStatus` which has:
- `mcp: { status, tools }`
- `agui: { status, events }`
- `a2a: { status, semantics, endpoint, note }`

## Track 2: Addon search/filter

### 2a. Add search state

In addons-view.ts, add:
```typescript
@state() private _searchQuery = '';
```

### 2b. Add search input

At the top of the sidebar list (before the addon cards), add:
```html
<input class="addon-search" type="text" placeholder="Filter addons..."
  .value=${this._searchQuery}
  @input=${(e: Event) => { this._searchQuery = (e.target as HTMLInputElement).value; }}>
```

### 2c. Filter the addon list

Where addons are iterated for the sidebar, apply the filter:
```typescript
const filteredAddons = (addons ?? []).filter(a =>
  !this._searchQuery ||
  a.name.toLowerCase().includes(this._searchQuery.toLowerCase()) ||
  a.description.toLowerCase().includes(this._searchQuery.toLowerCase())
);
```

Use `filteredAddons` instead of the raw list for rendering.

### 2d. CSS

```css
.addon-search {
  width: 100%; box-sizing: border-box; padding: 6px 10px;
  background: var(--v-recessed); border: 1px solid var(--v-border);
  border-radius: 6px; color: var(--v-fg); font-family: var(--f-mono);
  font-size: 11px; outline: none; margin-bottom: 8px;
}
.addon-search:focus { border-color: rgba(232,88,26,0.3); }
.addon-search::placeholder { color: var(--v-fg-dim); }
```

## Track 3: Addon health summary card

### 3a. Add at top of detail panel

At the top of `_renderDetail()` (or equivalent), before the addon name/
version, add an aggregate stats row:

```typescript
private _renderHealthSummary(addons: AddonSummary[]) {
  const total = addons.length;
  const disabled = addons.filter(a => a.disabled).length;
  const errored = addons.filter(a => a.status === 'error').length;
  const totalTools = addons.reduce((sum, a) => sum + a.tools.length, 0);
  const totalCalls = addons.reduce((sum, a) =>
    sum + a.tools.reduce((s, t) => s + t.callCount, 0), 0);

  return html`
    <div class="health-summary">
      <span class="health-stat">${total} addons</span>
      <span class="health-stat">${totalTools} tools</span>
      <span class="health-stat">${totalCalls} calls</span>
      ${disabled > 0 ? html`<span class="health-stat warn">${disabled} disabled</span>` : nothing}
      ${errored > 0 ? html`<span class="health-stat error">${errored} errors</span>` : nothing}
    </div>
  `;
}
```

### 3b. Placement

Render this at the top of the detail panel, before any specific addon's
detail. It gives a quick overview of the addon ecosystem.

### 3c. CSS

```css
.health-summary {
  display: flex; gap: 12px; padding: 8px 12px;
  font-family: var(--f-mono); font-size: 10px;
  color: var(--v-fg-dim); margin-bottom: 12px;
  border-bottom: 1px solid var(--v-border);
}
.health-stat { display: flex; align-items: center; gap: 3px; }
.health-stat.warn { color: var(--v-warning, #f59e0b); }
.health-stat.error { color: var(--v-danger, #ef4444); }
```

## Track 4: `docs/DEVELOPER_BRIDGE.md`

### 4a. Purpose

This document is for developers who have never heard of FormicOS. They should
be productive in 5 minutes after reading it. Write for a senior developer
who uses Claude Code daily but doesn't know what stigmergic coordination or
Thompson Sampling is.

### 4b. Structure

```markdown
# FormicOS Developer Bridge

## What is FormicOS?

One paragraph: AI agent orchestration system. Manages background work, keeps
institutional memory, learns from outcomes.

## Quick Start (60 seconds)

1. Start FormicOS: `docker compose up`
2. Generate MCP config: `python -m formicos init-mcp`
3. Restart Claude Code
4. Try: "What's the status of my workspace?" (uses morning-status prompt)

## Daily Workflows

### Morning: What happened?
Use `morning-status` to get a briefing.

### Working: Need context?
Use `knowledge-for-context` to search institutional memory.

### Delegating: Too big for one session?
Use `delegate-task` to plan a colony, or `handoff-to-formicos` to transfer
your current work context.

### Discovered something?
Use `log-finding` to record it in institutional memory.

### End of day: Review autonomous work
Use `review-overnight-work` to see what FormicOS did on its own.

## Available MCP Prompts

{List all 6 prompts with one-line descriptions}

## Available MCP Tools

{List the key tools — not all 27, just the 10-12 most useful ones grouped
by workflow: colony management, knowledge, addons, approvals}

## Available MCP Resources

{List all 9 with descriptions}

## Shared Files

- `.formicos/project_plan.md` — project milestones
- `.formicos/project_context.md` — project instructions for colonies
- `.formicos/operations/*/operating_procedures.md` — autonomy rules
- `.formicos/operations/*/queen_journal.md` — what FormicOS did

## Architecture (for the curious)

Two paragraphs max: event-sourced, 4-layer, stigmergic coordination.
Link to `docs/` for details. Don't explain Thompson Sampling or CRDTs here.
```

### 4c. Tone

Direct, practical, zero jargon. Compare to a good README for a dev tool.
The reader cares about "what can I do" not "how does it work internally."

## Track 5: CLAUDE.md refresh

### 5a. What to update

Read the current CLAUDE.md. It's the project's system prompt for AI coding
assistants. Update these sections:

1. **Header**: Add mention of MCP developer bridge
2. **Tech stack**: Verify all deps are current
3. **Key paths table**: Add:
   - `surface/mcp_server.py` — MCP server (27 tools, 9 resources, 6 prompts)
   - `docs/DEVELOPER_BRIDGE.md` — Developer onboarding guide
4. **MCP tool count**: Update from whatever it currently says to 27
5. **Commands section**: Add `python -m formicos init-mcp` under existing commands
6. **Architecture section**: If it mentions MCP, update the counts

### 5b. What NOT to change

Don't restructure CLAUDE.md. Don't rewrite sections that are accurate.
Don't add architecture explanations for Wave 73 — it's not an architectural
change, it's a composition layer. Keep changes surgical.

### 5c. Verify before updating

Run a diff against the actual post-Team A state. If Team A hasn't merged
yet, use the planned counts from the design note:
- 27 MCP tools, 9 resources, 6 prompts, 4 CLI subcommands

## Coordination with Teams A and B

- **Team A merges first.** Wait for their final tool/prompt/resource list
  before finalizing DEVELOPER_BRIDGE.md and CLAUDE.md. You can draft both
  docs against the plan but verify against the actual code before declaring
  done.
- **Team B removes nothing from Settings.** Your Track 1 only verifies that
  the protocol detail Wave 72.5 added is still there. No coordination risk.

## Validation

```bash
cd frontend && npm run build && npm run lint
```

For docs: read through DEVELOPER_BRIDGE.md as if you've never heard of
FormicOS. Can you connect and be productive in 5 minutes?

## Acceptance criteria

- [ ] Settings protocol section shows MCP tool count, AG-UI event count,
      A2A endpoint detail (verified or added)
- [ ] Addon search/filter input filters sidebar list by name and description
- [ ] Addon health summary shows aggregate stats (total, tools, calls, errors)
- [ ] `docs/DEVELOPER_BRIDGE.md` is readable by a new developer in 5 minutes
- [ ] CLAUDE.md reflects post-Wave 73 state (MCP counts, CLI commands, key paths)
- [ ] No regressions — frontend builds clean, all lints pass
