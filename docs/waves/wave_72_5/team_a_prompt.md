# Wave 72.5 Team A: Topbar Cleanup + Cost Popover

## Mission

Remove decorative protocol badges and the always-on connection dot from the
topbar. Make the `$X.XX spent` display clickable — it opens a budget popover
showing all money-related settings in one place. The topbar should be clean:
logo, nav, cost button, approval badge.

## Owned files

- `frontend/src/components/formicos-app.ts` — topbar layout, protocol bar, cost display, connection indicator

### Do not touch

- `settings-view.ts` (Team C)
- `addons-view.ts` (Team B)
- `routes/api.py` (Team B)
- `addon_loader.py` (Team C)
- `view_state.py` (Team B)
- `types.ts` (Team B)

## Repo truth (read before coding)

1. **formicos-app.ts lines 749-768** — `renderProtocolBar(ps)` renders 3 protocol items
   (MCP, AG-UI, A2A) as `proto-item` divs with status dots, labels, and detail text.
   Called at line 390. Each shows: label, status dot, detail (tool count / event count /
   A2A endpoint). This data is NOT shown elsewhere in equivalent detail — the Settings
   Protocols section only shows name + status pill (no counts, no endpoints). Team C is
   responsible for adding equivalent detail to Settings before this removal is safe.

2. **formicos-app.ts lines 736-747** — `_renderConnectionIndicator(conn)` renders a
   green/yellow/red dot with optional label. Called at line 392. When connected, it
   renders a green dot with no label — pure visual noise. When disconnected, the app
   already visibly stops working (colonies freeze, WS messages stop), so the dot adds
   no information the operator doesn't already have.

3. **formicos-app.ts lines 388-399** — `topbar-right-wrap` contains: protocol bar,
   `$X.XX spent` text, connection indicator, and approval badge. The approval badge
   stays — it's useful and actionable (navigates to Queen on click).

4. **formicos-app.ts lines 52-57** — topbar CSS: 3-column grid
   `minmax(0,1fr) auto minmax(0,1fr)`.

5. **formicos-app.ts line 350** — cost calculation:
   `colonies.reduce((a,c) => a + ((c as any).cost ?? 0), 0)`

6. **Protocol status data** lives in `store.state.protocolStatus`. It's already consumed
   by `settings-view.ts` in the Integrations card (`_renderProtocolsSummary()` at
   line 676). The Settings tab is the correct home for protocol diagnostics. Team C will
   enhance it to show the same detail level (tool count, event count, endpoint) that the
   topbar badges currently show, so nothing is lost.

7. **Budget data sources** the popover needs:
   - **Total cost across all colonies**: already computed at line 350.
   - **Default budget per colony**: `store.state.runtimeConfig?.governance?.defaultBudgetPerColony`
     (default $1.00 from formicos.yaml:561, editable in Settings governance card).
   - **Daily maintenance budget + autonomy status**: NOT in the WebSocket snapshot. The
     `<fc-autonomy-card>` component fetches this lazily from
     `GET /api/v1/workspaces/{id}/autonomy-status`. The popover should either embed that
     component or fetch the same endpoint. The maintenance policy itself is at
     `GET /api/v1/workspaces/{id}/maintenance-policy`.
   - The workspace ID for the fetch: `store.state.tree?.[0]?.id` (first workspace) or
     track the selected workspace if multiple exist.

## Track 1: Remove protocol badges

1. **Delete `renderProtocolBar()`** (lines 749-768) entirely.
2. **Remove its call** at line 390: `${this.renderProtocolBar(s.protocolStatus)}`
3. **Delete all `.proto-*` CSS rules** — search the static styles block for `proto-bar`,
   `proto-item`, `proto-label`, `proto-detail`. Remove them all.
4. Protocol data (`store.state.protocolStatus`) stays in the store — Settings still uses it.

## Track 2: Remove the connection indicator

1. **Delete `_renderConnectionIndicator()`** (lines 736-747).
2. **Remove its call** at line 392: `${this._renderConnectionIndicator(s.connection)}`
3. **Delete `.conn-indicator`, `.conn-dot`, `.conn-label` CSS rules** from the static
   styles block.
4. Connection state stays in the store — the reconnection logic is unaffected.

## Track 3: Clickable cost display with budget popover

Replace the plain `$X.XX spent` text with a clickable element that toggles a popover.

### State additions

```typescript
@state() private _showBudgetPopover = false;
@state() private _policyData: { daily_maintenance_budget: number; autonomy_level: string } | null = null;
@state() private _autonomyData: { grade: string; level: string; budget_spent: number; budget_total: number } | null = null;
```

### The cost element

```html
<span class="cost-btn" @click=${(e: Event) => {
  e.stopPropagation();
  this._showBudgetPopover = !this._showBudgetPopover;
  if (this._showBudgetPopover) this._fetchBudgetData();
}}>
  ${formatCost(totalCost)} spent
</span>
```

Style `cost-btn`: cursor pointer, subtle hover highlight (`rgba(232,88,26,0.1)`),
border-radius 6px, padding 4px 8px. Make it look tappable.

### The popover

Absolutely positioned below/left of the cost button. Rendered conditionally:

```html
${this._showBudgetPopover ? html`
  <div class="budget-backdrop" @click=${() => { this._showBudgetPopover = false; }}></div>
  <div class="budget-popover">
    ${this._renderBudgetPopover(totalCost)}
  </div>
` : nothing}
```

**Popover CSS:**
- `position: absolute; top: 100%; right: 0; margin-top: 6px;`
- `background: var(--v-recessed); border: 1px solid var(--v-border);`
- `border-radius: 10px; padding: 16px; min-width: 260px; z-index: 100;`
- `box-shadow: 0 8px 32px rgba(0,0,0,0.4);`
- Backdrop: `position: fixed; inset: 0; z-index: 99;` (transparent, catches click-outside)

**Popover content** — 4 rows, compact:

| Row | Label | Value | Source |
|-----|-------|-------|--------|
| 1 | Total spent | `$X.XX` | `totalCost` (already computed) |
| 2 | Per-colony cap | `$Y.YY` | `store.state.runtimeConfig?.governance?.defaultBudgetPerColony` |
| 3 | Daily maintenance | `$A.AA / $B.BB` | Fetched from autonomy-status endpoint |
| 4 | Autonomy | `Grade F · suggest` | Fetched from autonomy-status endpoint |

Each row: label on left (10px mono, dim), value on right (12px mono, accent for costs).
Compact vertical spacing (8px gap between rows).

Below the rows, a subtle link: `<span class="popover-link" @click=${() => this.navTab('settings')}>All budget settings →</span>` that navigates to the Settings tab.

### Data fetching

```typescript
private async _fetchBudgetData() {
  const wsId = store.state.tree?.[0]?.id;
  if (!wsId) return;
  try {
    const resp = await fetch(`/api/v1/workspaces/${wsId}/autonomy-status`);
    if (resp.ok) this._autonomyData = await resp.json();
  } catch { /* popover shows what it has */ }
}
```

Cache the result — don't re-fetch on every open. Clear cache when store updates
(in the store subscription callback, set `_autonomyData = null`).

### The resulting topbar-right

```html
<div class="topbar-right-wrap">
  <div class="topbar-right" style="position:relative">
    <span class="cost-btn" @click=${...}>
      ${formatCost(totalCost)} spent
    </span>
    ${budgetPopover}
  </div>
  ${approvalBadge}
</div>
```

## Validation

```bash
cd frontend && npm run build && npm run lint
```

Verify in the running stack at http://localhost:8080:
- Topbar has no protocol badges
- Topbar has no green/red connection dot
- `$X.XX spent` is clickable and shows the budget popover
- Popover shows all 4 rows with real data
- Click-outside closes the popover
- "All budget settings →" link navigates to Settings

## Acceptance criteria

- [ ] `renderProtocolBar()` method and CSS deleted
- [ ] `_renderConnectionIndicator()` method and CSS deleted
- [ ] No protocol badges or connection dot visible in topbar
- [ ] `$X.XX spent` is clickable with hover highlight
- [ ] Budget popover shows: total spent, per-colony cap, daily maintenance budget/remaining, autonomy grade+level
- [ ] Popover closes on click-outside
- [ ] Popover includes "All budget settings →" link to Settings tab
- [ ] Topbar is clean: logo + nav + cost button + approval badge only
- [ ] Protocol status data still flows to Settings (no store changes)
- [ ] Frontend builds and lints clean
