# Wave 74 Team B: Elevation — Procedures, Plans, Autonomy, Budget Viz

## Mission

Elevate existing computed data to the Queen tab. Build continuation candidates
renderer, autonomy score card, context budget visualizer. Move colony cards
from Queen tab to workspace view. All the data already exists — this is pure
"make visible what's already computed."

## Owned files

- `frontend/src/components/queen-continuations.ts` — new component
- `frontend/src/components/queen-autonomy-card.ts` — new component
- `frontend/src/components/queen-budget-viz.ts` — new component
- `frontend/src/components/workspace-config.ts` — add colony cards section
- `frontend/src/components/formicos-app.ts` — wire new events if needed
- `src/formicos/surface/routes/api.py` — `GET /api/v1/queen-budget` endpoint

### Do not touch

- `queen-overview.ts` (Team A restructures it)
- `queen_runtime.py`, `queen_tools.py` (Team A + Team C)
- `operational_state.py`, `app.py` (Team A)
- `queen_budget.py` (read-only — you read it for the endpoint, don't modify)
- `projections.py`, `events.py`

## Repo truth (read before coding)

### Continuation candidates (operations_coordinator.py)

1. **`build_operations_summary()`** at operations_coordinator.py:31-100 returns:
   ```python
   {
     "workspace_id": str,
     "pending_review_count": int,
     "active_milestone_count": int,
     "stalled_thread_count": int,
     "last_operator_activity_at": str,  # ISO timestamp
     "idle_for_minutes": int,
     "operator_active": bool,           # idle < 15 min
     "continuation_candidates": [
       {
         "thread_id": str,
         "description": str,
         "ready_for_autonomy": bool,
         "blocked_reason": str | None,
         "priority": str,
       }
     ],
     "sync_issues": [...],
     "recent_progress": [...],
   }
   ```

2. **REST endpoint already exists:**
   `GET /api/v1/workspaces/{id}/operations/summary` — returns this dict.
   Your component reads from it directly. No new endpoint needed.

### Autonomy score (self_maintenance.py)

3. **`compute_autonomy_score()`** at self_maintenance.py:176-266 returns:
   ```python
   {
     "score": int,          # 0-100
     "grade": str,          # "A", "B", "C", "D", "F"
     "components": {
       "success_rate": float,    # 40% weight
       "volume": float,          # 20% weight
       "cost_efficiency": float, # 20% weight
       "operator_trust": float,  # 20% weight
     },
     "recommendation": str,  # graded advice text
   }
   ```

4. **REST endpoint already exists:**
   `GET /api/v1/workspaces/{id}/autonomy-status` (api.py:1029-1099) returns
   all above fields PLUS:
   - `daily_budget`, `daily_spend`, `remaining`
   - `active_maintenance_colonies`, `max_maintenance_colonies`
   - `auto_actions` list
   - `recent_actions` list

### Context budget (queen_budget.py)

5. **`QueenContextBudget`** at queen_budget.py:52-64 has 9 slots.
   **`_FRACTIONS`** at lines 27-37:
   ```python
   _FRACTIONS = {
     "system_prompt": 0.15,
     "memory_retrieval": 0.13,
     "project_context": 0.08,
     "project_plan": 0.05,
     "operating_procedures": 0.05,
     "queen_journal": 0.04,
     "thread_context": 0.13,
     "tool_memory": 0.09,
     "conversation_history": 0.28,
   }
   ```

   These are static fractions (not tunable per workspace). The endpoint just
   returns them plus their fallback token floors.

6. **`_FALLBACKS`** at lines 39-49:
   ```python
   _FALLBACKS = {
     "system_prompt": 2000,
     "memory_retrieval": 1500,
     "project_context": 500,
     "project_plan": 400,
     "operating_procedures": 400,
     "queen_journal": 300,
     "thread_context": 1500,
     "tool_memory": 4000,
     "conversation_history": 6000,
   }
   ```

### Colony cards in queen-overview.ts

7. **Running colonies by workspace** at lines 242-259. These are grouped by
   workspace, with `renderColonyCard(c)` for each.

8. **Recent completions** at lines 262-267. Last 6 completed colonies.

9. **Service colonies** at line 240 via `_renderServiceColonies()`.

   Team A removes all three of these. Your job is to give them a new home
   in workspace-config.ts.

### workspace-config.ts current state

10. **Renders** (lines 44-147): header, model cascade overrides, governance
    grid, threads list, new colony button, description, quick-nav cards.

    Colony cards should go ABOVE the threads list. When the operator clicks a
    workspace, they should see active colonies first, then threads.

### Operating procedures editor

11. **`operations-view.ts`** at lines 157-166 mounts:
    - `<fc-operations-inbox>` (left column)
    - `<fc-queen-journal-panel>` (right column)
    - `<fc-operating-procedures-editor>` (right column, below journal)

    The procedures editor component already exists as a standalone element.
    The exact tag is:
    ```html
    <fc-operating-procedures-editor .workspaceId=${workspaceId}>
    </fc-operating-procedures-editor>
    ```

12. **`queen-overview.ts` is Team A-owned.**
    You do not patch the Queen shell directly. Your responsibility is to:
    - verify the exact procedures-editor tag/prop contract,
    - build your child components to that same contract style,
    - hand Team A the final mount snippet for the Queen tab.

## Track 1: Continuation candidates component

### 1a. New `queen-continuations.ts`

Fetches from `GET /api/v1/workspaces/{id}/operations/summary`.
Renders `continuation_candidates` as a compact list.

```typescript
@customElement('fc-queen-continuations')
export class FcQueenContinuations extends LitElement {
  @property() workspaceId = '';
  @state() private _candidates: ContinuationCandidate[] = [];
```

Each candidate shows:
- Thread description (truncated to 60 chars)
- Ready badge (green "ready" or amber "blocked: {reason}")
- Priority pill

```html
<div class="s-label">Continuations</div>
${this._candidates.length === 0 ? html`
  <div style="font-size:10px;color:var(--v-fg-dim);font-family:var(--f-mono)">No pending continuations</div>
` : this._candidates.map(c => html`
  <div class="glass" style="padding:8px 10px;margin-bottom:4px;display:flex;align-items:center;gap:6px">
    <span style="font-size:11px;font-family:var(--f-mono);color:var(--v-fg);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${c.description}</span>
    ${c.ready_for_autonomy
      ? html`<fc-pill color="var(--v-green, #22c55e)" sm>ready</fc-pill>`
      : html`<fc-pill color="var(--v-warning, #f59e0b)" sm>blocked</fc-pill>`}
  </div>
`)}
```

Refresh every 60s or on workspaceId change.

## Track 2: Autonomy score card

### 2a. New `queen-autonomy-card.ts`

Fetches from `GET /api/v1/workspaces/{id}/autonomy-status`.

Renders:
- Grade badge (A-F) with color coding: A/B green, C amber, D/F red
- Score number (0-100)
- 4-component breakdown as mini bars:
  ```
  Success Rate  ████████░░ 0.82  (40%)
  Volume        ██████░░░░ 0.65  (20%)
  Cost Eff.     █████████░ 0.91  (20%)
  Trust         ███████░░░ 0.70  (20%)
  ```
- Recommendation text (the graded advice)
- Autonomy level pill (suggest/auto_notify/autonomous)
- Daily budget bar: `$spent / $budget`

### 2b. Compact mode

The card should have a compact mode for the Queen tab (grade + score +
autonomy level on one row) and an expanded mode (full breakdown).

```html
<div class="s-label">Queen Health</div>
<div class="glass" style="padding:12px">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
    <span class="grade-badge grade-${this._grade.toLowerCase()}">${this._grade}</span>
    <span style="font-family:var(--f-mono);font-size:12px;color:var(--v-fg)">${this._score}/100</span>
    <fc-pill color="var(--v-fg-dim)" sm>${this._autonomyLevel}</fc-pill>
    <span style="margin-left:auto;font-size:10px;font-family:var(--f-mono);color:var(--v-fg-dim)">$${this._dailySpend.toFixed(2)} / $${this._dailyBudget.toFixed(2)}</span>
  </div>
  ${this._expanded ? this._renderBreakdown() : nothing}
  <div style="text-align:center">
    <fc-btn variant="ghost" sm @click=${() => { this._expanded = !this._expanded; }}>
      ${this._expanded ? 'Less' : 'Details'}
    </fc-btn>
  </div>
</div>
```

## Track 3: Context budget visualizer

### 3a. New `GET /api/v1/queen-budget` endpoint

In `routes/api.py`:

```python
async def get_queen_budget(request: Request) -> JSONResponse:
    """Return the Queen's 9-slot context budget allocation."""
    from formicos.surface.queen_budget import _FRACTIONS, _FALLBACKS

    slots = [
        {"name": name, "fraction": frac, "fallback_tokens": _FALLBACKS.get(name, 0)}
        for name, frac in _FRACTIONS.items()
    ]
    return JSONResponse({"slots": slots})
```

Route: `Route("/api/v1/queen-budget", get_queen_budget)`

This is ~10 lines. Pure read from module constants.

### 3b. New `queen-budget-viz.ts`

Renders a stacked bar showing the 9 slots:

```
System prompt     ████████░░░░░░░░░░░░ 15%  (2000 min)
Memory retrieval  ██████░░░░░░░░░░░░░░ 13%  (1500 min)
Project context   ████░░░░░░░░░░░░░░░░  8%  (500 min)
...
Conversation      ██████████████░░░░░░ 28%  (6000 min)
```

Each bar is a colored div at `width: ${frac * 100}%` inside a fixed-width
container. Use muted colors — this is informational, not a dashboard graph.

Label format: `${name} · ${Math.round(frac * 100)}% · ${fallback} min tokens`

The whole thing should be collapsible (default collapsed, showing just
a one-line summary: "Context: 9 slots, largest=conversation 28%").

## Track 4: Move colony cards to workspace view

### 4a. Add running colonies section to workspace-config.ts

After the header and before the grid (around line 60), add a running
colonies section:

```typescript
${this._runningColonies.length > 0 ? html`
  <div class="s-label">Active Colonies</div>
  <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:6px;margin-bottom:14px">
    ${this._runningColonies.map(c => html`
      <div class="glass clickable" style="padding:8px 10px" @click=${() => this.fire('navigate', c.id)}>
        <div style="display:flex;align-items:center;gap:5px">
          <span style="width:6px;height:6px;border-radius:50%;background:var(--v-green, #22c55e)"></span>
          <span style="font-size:10.5px;font-family:var(--f-mono);color:var(--v-fg);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${c.name}</span>
        </div>
        <div style="font-size:9px;font-family:var(--f-mono);color:var(--v-fg-dim);margin-top:2px">${c.status} · R${(c as any).rounds ?? 0}</div>
      </div>
    `)}
  </div>
` : nothing}
```

Use `allColonies([ws]).filter(c => c.status === 'running')` for the list
(the `allColonies` helper is already imported).

Also add recent completions below the threads section:

```typescript
${this._recentCompletions.length > 0 ? html`
  <div class="s-label" style="margin-top:14px">Recent Completions</div>
  ${this._recentCompletions.slice(0, 4).map(c => html`
    <div class="glass" style="padding:6px 10px;margin-bottom:4px;font-size:10px;font-family:var(--f-mono);color:var(--v-fg-dim)">
      ${c.name} — ${c.status}
    </div>
  `)}
` : nothing}
```

### 4b. Procedures editor elevation contract

Do not edit `queen-overview.ts`. Instead, verify the exact procedures editor
tag and prop contract, then hand Team A the mount snippet:

```html
<fc-operating-procedures-editor .workspaceId=${workspaceId}>
</fc-operating-procedures-editor>
```

Verify the exact tag name by reading `frontend/src/components/` for the
procedures editor component file. It was created in Wave 71.5.

## Track 5: Wire in formicos-app.ts

If workspace-config.ts emits new events (e.g., `navigate` to colony nodes),
verify they bubble through to formicos-app.ts. The existing `@navigate`
handler at formicos-app.ts:679 should handle colony navigation already.

## Validation

```bash
cd frontend && npm run build
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Verify in the running stack:
- Workspace view shows active colonies and recent completions
- Queen tab has continuation candidates (may be empty if no pending work)
- Autonomy card shows grade and components
- Context budget viz shows 9-slot breakdown
- Procedures editor accessible from Queen tab

## Acceptance criteria

- [ ] `queen-continuations.ts` reads from operations/summary endpoint
- [ ] Continuation candidates show ready/blocked status
- [ ] `queen-autonomy-card.ts` reads from autonomy-status endpoint
- [ ] Autonomy card shows grade (A-F), 4-component breakdown, recommendation
- [ ] `queen-budget-viz.ts` reads from new queen-budget endpoint
- [ ] Budget viz shows 9-slot stacked bar with fractions and fallback floors
- [ ] `GET /api/v1/queen-budget` endpoint returns slot data from queen_budget.py
- [ ] Colony cards (running + completed) appear in workspace-config.ts
- [ ] Procedures editor tag/prop contract verified and handed to Team A for Queen-tab mounting
- [ ] No regressions — all tests pass, frontend builds clean
