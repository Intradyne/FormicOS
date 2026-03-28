# Wave 73 Team B: Frontend Truth + Workspace Creation

## Mission

Every number the UI shows must be correct. Kill hardcoded defaults in colony
creation and template editing. Wire `runtimeConfig` to components that need
it. Add workspace creation UI. Fix addon config type coercion.

## Owned files

- `frontend/src/components/colony-creator.ts` — budget, maxRounds, tier costs
- `frontend/src/components/template-editor.ts` — budget, maxRounds defaults
- `frontend/src/components/formicos-app.ts` — runtimeConfig wiring, workspace creation
- `frontend/src/types.ts` — type additions if needed
- `frontend/src/components/playbook-view.ts` — pass governance to template-editor (1 line)
- `src/formicos/surface/routes/api.py` — workspace creation endpoint + addon config type coercion

### Do not touch

- `mcp_server.py` (Team A)
- `settings-view.ts` (Team C)
- `addons-view.ts` (Team C)
- `addon_loader.py`, `projections.py`, `events.py`

## Repo truth (read before coding)

### Colony creator hardcoded defaults (colony-creator.ts, 654 lines)

1. **Line 159**: `@state() private budget = 2.0;` — hardcoded $2.00 budget.
   Should read from governance config: `defaultBudgetPerColony`.

2. **Line 160**: `@state() private maxRounds = 10;` — hardcoded 10 rounds.
   Should read from governance config: `maxRoundsPerColony`.

3. **Lines 371-374** — fabricated tier cost rates in `_renderLaunch()`:
   ```typescript
   const rate = t.tier === 'light' ? 0 : t.tier === 'flash' ? 0.01 : t.tier === 'heavy' ? 0.08 : 0.02;
   ```
   These numbers (`0`, `0.01`, `0.08`, `0.02`) are made up. They don't
   reflect actual model pricing.

4. **Line 342**: `@input` handler fallback: `parseFloat(...) || 2.0` — uses
   hardcoded 2.0 as fallback. Should use governance default.

5. **Line 348**: `@input` handler fallback: `parseInt(...) || 10` — uses
   hardcoded 10 as fallback. Should use governance default.

6. **Lines 636-644** — `reset()` method re-hardcodes:
   ```typescript
   this.budget = 2.0;
   this.maxRounds = 10;
   ```

7. **Line 22-26** — `TIERS` constant has `costHint` strings:
   ```typescript
   light: { ..., costHint: 'free' },
   standard: { ..., costHint: '~$0.02/turn' },
   heavy: { ..., costHint: '~$0.08/turn' },
   flash: { ..., costHint: '~$0.01/turn' },
   ```
   These are display hints, not calculation rates. They're less harmful than
   the calculation rates but still fabricated.

8. **Component does NOT receive `runtimeConfig`** as a property. It receives:
   - `@property() castes: CasteDefinition[]` (line 143)
   - `@property() initialObjective` (line 144)
   - `@property() initialTemplateId` (line 145)
   - `@property() availableServices: Colony[]` (line 147)
   That's it. No governance data flows in.

### How runtimeConfig flows in formicos-app.ts

9. **formicos-app.ts** passes `runtimeConfig` to several child components:
   - Line 589: `fc-colony-overview`
   - Line 651: `fc-workspace-config`
   - Line 683: `fc-playbook-view`
   - Line 694: `fc-model-registry`
   - Line 699: `fc-settings-view`
   - Line 775: Used in `_renderBudgetPopover()` directly

10. **formicos-app.ts does NOT pass `runtimeConfig` to `fc-colony-creator`**
    (lines 461-469). The colony creator is rendered with only `.castes` and
    `.initialTemplateId`.

### Template editor hardcoded defaults (template-editor.ts)

11. **Line 108-109** (verify exact lines): `budgetLimit = 1.0` and
    `maxRounds = 5` as state defaults. Same problem as colony-creator.

### Addon config type coercion (routes/api.py)

12. **`put_addon_config()` at line 1602** receives values from the frontend
    as JSON. But HTML form inputs send strings. The manifest declares each
    config param's type (`boolean`, `string`, `integer`, `cron`, `select`
    at addon_loader.py:52-59). The PUT handler should coerce values to match
    the declared type before saving.

### Governance config in the store

13. **`runtimeConfig.governance`** is available in the WebSocket snapshot.
    Check `view_state.py`'s `_build_runtime_config()` — it includes:
    ```python
    "governance": {
        "maxRoundsPerColony": ...,
        "defaultBudgetPerColony": ...,
    }
    ```
    This data reaches the frontend via `store.state.runtimeConfig.governance`.

## Track 0: Verify Wave 72.5 topbar cleanup landed

Before starting, check whether Wave 72.5 Team A's topbar changes are in
the codebase. Look for `renderProtocolBar()` in `formicos-app.ts`:

- **If it's already gone:** 72.5 landed. Move on.
- **If it still exists:** Delete the method, its call site in the topbar
  render, and all `.proto-*` CSS rules. Protocol data stays in the store
  for the Settings view. This is ~10 lines of deletion, not a feature.

Same check for the cost popover — if 72.5 Team A added it, verify it's
there. If not, the cost display in the topbar should at least show the
real `$spent` value, not a hardcoded one.

## Track 1: Wire runtimeConfig to colony-creator

### 1a. Add property to colony-creator.ts

Add a new property for governance config. The simplest approach:

```typescript
@property({ type: Object }) governance: { defaultBudgetPerColony: number; maxRoundsPerColony: number } | null = null;
```

### 1b. Use governance defaults for initial state

Change the hardcoded defaults to read from governance when available:

```typescript
@state() private budget = 0;  // Set from governance in connectedCallback
@state() private maxRounds = 0;

connectedCallback() {
  super.connectedCallback();
  this._applyGovernanceDefaults();
}

private _applyGovernanceDefaults() {
  if (this.governance) {
    if (!this.budget) this.budget = this.governance.defaultBudgetPerColony ?? 1.0;
    if (!this.maxRounds) this.maxRounds = this.governance.maxRoundsPerColony ?? 10;
  } else {
    // Fallback if governance not available yet
    if (!this.budget) this.budget = 1.0;
    if (!this.maxRounds) this.maxRounds = 10;
  }
}
```

Also update `updated()` to re-apply when `governance` property changes:
```typescript
updated(changed: Map<string, unknown>) {
  if (changed.has('governance') && this.governance) {
    this._applyGovernanceDefaults();
  }
  // ... existing updated() logic ...
}
```

### 1c. Fix input fallbacks

Line 342: Change `parseFloat(...) || 2.0` to use governance default:
```typescript
@input=${(e: Event) => {
  this.budget = parseFloat((e.target as HTMLInputElement).value)
    || this.governance?.defaultBudgetPerColony || 1.0;
}}
```

Line 348: Change `parseInt(...) || 10`:
```typescript
@input=${(e: Event) => {
  this.maxRounds = parseInt((e.target as HTMLInputElement).value)
    || this.governance?.maxRoundsPerColony || 10;
}}
```

### 1d. Fix reset() method

Lines 636-644: Use governance defaults in reset:
```typescript
reset() {
  // ...
  this.budget = this.governance?.defaultBudgetPerColony ?? 1.0;
  this.maxRounds = this.governance?.maxRoundsPerColony ?? 10;
  // ...
}
```

### 1e. Fix tier cost estimation

Lines 371-374: Remove the fabricated cost rates. Replace with a transparent
message or remove the estimate entirely:

**Option A (preferred — remove fabricated estimate):**
Replace the `estCost` calculation and display with:
```typescript
// Remove: const estCost = this.team.reduce(...)
// In the launch-meta div, replace the estCost line:
<span style="color:var(--v-fg-dim)">cost varies by model</span>
```

**Option B (if preview data is available):**
If `this.previewData?.estimatedCost` is populated by the backend, show that
instead:
```typescript
${this.previewData?.estimatedCost
  ? html`<span style="color:var(--v-accent)">est. ~$${this.previewData.estimatedCost.toFixed(2)}</span>`
  : html`<span style="color:var(--v-fg-dim)">cost varies by model</span>`}
```

### 1f. Pass governance from formicos-app.ts

In formicos-app.ts, find where `fc-colony-creator` is rendered (around
line 461-469). Add the governance property:

```typescript
<fc-colony-creator
  .castes=${...}
  .initialTemplateId=${...}
  .governance=${store.state.runtimeConfig?.governance ?? null}
  ...
></fc-colony-creator>
```

Also check if `availableServices` is being passed. The component has the
property — make sure it's wired.

## Track 2: Fix template-editor.ts

### 2a. Same governance wiring

Add `governance` property to `template-editor.ts`. Use governance defaults
for `budgetLimit` (line 108, currently `1.0`) and `maxRounds` (line 109,
currently `5`). Fix the reset in `_populateFromTemplate()` at lines 138-139.

### 2b. Wire governance through playbook-view.ts

**This is why `playbook-view.ts` is in your owned files.** The template
editor is instantiated from `playbook-view.ts` at line 163:
```html
<fc-template-editor .mode=${this.editorMode} .template=${this.editorTemplate} ...>
```

`playbook-view.ts` already receives `runtimeConfig` as a property (line 109).
Add `.governance` passthrough:
```html
<fc-template-editor
  .mode=${this.editorMode}
  .template=${this.editorTemplate}
  .governance=${this.runtimeConfig?.governance ?? null}
  ...>
```

This is 1 line of change in `playbook-view.ts`.

## Track 3: Workspace creation UI

### 3a. Current state — NO workspace creation path exists

There is no frontend path to create a workspace. The backend situation:

- `runtime.create_workspace(name)` exists at runtime.py:647 — emits
  `WorkspaceCreated` event, creates workspace directory.
- The MCP tool `create_workspace` exists (mcp_server.py:89) — calls
  `runtime.create_workspace()`.
- **NO WS command handler exists.** `store.send()` requires a
  `WSCommandAction` (types.ts:836) and `create_workspace` is NOT in that
  union. The WS command dispatch (`commands.py`) has no workspace creation
  handler.
- **NO REST endpoint exists.** The only workspace-creation HTTP route is
  `POST /api/v1/workspaces/create-demo` (api.py:2273) which creates a
  seeded demo workspace — not a general-purpose create.

### 3b. Add REST endpoint for workspace creation (routes/api.py)

Add a new endpoint near the existing workspace routes:

```python
async def create_workspace_endpoint(request: Request) -> JSONResponse:
    """Create a new workspace."""
    try:
        body = await request.json()
    except Exception:
        return _err_response("INVALID_JSON")

    name = body.get("name", "").strip()
    if not name:
        return _err_response(
            "INVALID_PARAMETER",
            message="Workspace name is required",
            status_code=400,
        )

    # Check if workspace already exists
    runtime = request.app.state.runtime
    if name in runtime.projections.workspaces:
        return _err_response(
            "INVALID_PARAMETER",
            message=f"Workspace '{name}' already exists",
            status_code=409,
        )

    workspace_id = await runtime.create_workspace(name)
    return JSONResponse({"workspace_id": workspace_id, "name": name}, status_code=201)
```

Register the route near the existing workspace routes:
```python
Route("/api/v1/workspaces", create_workspace_endpoint, methods=["POST"]),
```

### 3c. Frontend workspace creation (formicos-app.ts)

Add state and UI for creating workspaces:

```typescript
@state() private _showCreateWorkspace = false;
@state() private _newWorkspaceName = '';
@state() private _creatingWorkspace = false;
```

In the sidebar workspace list (find where workspaces are rendered), add:

```html
<button class="create-ws-btn" @click=${() => { this._showCreateWorkspace = true; }}>
  + New Workspace
</button>
```

Modal/inline form:
```html
${this._showCreateWorkspace ? html`
  <div class="create-ws-form glass" style="padding:12px;margin:8px 0">
    <input class="config-input" type="text" placeholder="Workspace name"
      .value=${this._newWorkspaceName}
      @input=${(e: Event) => { this._newWorkspaceName = (e.target as HTMLInputElement).value; }}
      @keydown=${(e: KeyboardEvent) => { if (e.key === 'Enter') this._createWorkspace(); }}>
    <div style="display:flex;gap:6px;margin-top:8px">
      <fc-btn variant="ghost" sm @click=${() => { this._showCreateWorkspace = false; this._newWorkspaceName = ''; }}>Cancel</fc-btn>
      <fc-btn variant="primary" sm
        ?disabled=${!this._newWorkspaceName.trim() || this._creatingWorkspace}
        @click=${() => this._createWorkspace()}>
        ${this._creatingWorkspace ? 'Creating...' : 'Create'}
      </fc-btn>
    </div>
  </div>
` : nothing}
```

Handler — uses the new REST endpoint, NOT `store.send()`:
```typescript
private async _createWorkspace() {
  if (!this._newWorkspaceName.trim()) return;
  this._creatingWorkspace = true;
  try {
    const resp = await fetch('/api/v1/workspaces', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: this._newWorkspaceName.trim() }),
    });
    if (resp.ok) {
      this._showCreateWorkspace = false;
      this._newWorkspaceName = '';
      // The WS snapshot will auto-update with the new workspace
    } else {
      const data = await resp.json();
      console.error('Failed to create workspace:', data.error ?? resp.statusText);
    }
  } catch (e) {
    console.error('Failed to create workspace:', e);
  }
  this._creatingWorkspace = false;
}
```

**Why REST and not WS:** Adding a WS command requires changes to
`commands.py`, `types.ts` (WSCommandAction union), and `ws_handler.py` —
3 files outside Team B's ownership. The REST endpoint is self-contained
in `routes/api.py` which Team B already owns for type coercion. The WS
snapshot auto-broadcasts after the `WorkspaceCreated` event, so the UI
updates automatically.

### 3c. CSS for create button

```css
.create-ws-btn {
  display: block; width: 100%; padding: 6px 12px; margin-top: 4px;
  background: transparent; border: 1px dashed var(--v-border);
  border-radius: 6px; color: var(--v-fg-dim); font-size: 10px;
  font-family: var(--f-mono); cursor: pointer; text-align: left;
}
.create-ws-btn:hover { border-color: var(--v-accent); color: var(--v-accent); }
```

## Track 4: Addon config type coercion

### 4a. In `put_addon_config()` (routes/api.py, line 1602)

After parsing the request body, before saving values, coerce each value
to match the config param's declared type:

```python
# After: values = body.get("values", {})
# Find the addon's config schema:
config_schema = reg.manifest.config  # list[AddonConfigParam]
for param in config_schema:
    if param.key in values:
        val = values[param.key]
        if param.type == "boolean" and isinstance(val, str):
            values[param.key] = val.lower() in ("true", "1", "yes")
        elif param.type == "integer" and isinstance(val, str):
            try:
                values[param.key] = int(val)
            except ValueError:
                pass
```

This is a small, targeted fix. Don't restructure the endpoint.

## Validation

```bash
cd frontend && npm run build && npm run lint
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Verify in the running stack:
- Colony creator shows governance budget and maxRounds (not $2.00 / 10)
- Template editor shows governance defaults
- Tier cost estimate says "cost varies by model" or shows backend estimate
- "New Workspace" button visible and functional
- Addon config saves with correct types

## Acceptance criteria

- [ ] Colony creator reads `defaultBudgetPerColony` from governance config
- [ ] Colony creator reads `maxRoundsPerColony` from governance config
- [ ] `runtimeConfig.governance` passed to `fc-colony-creator` from `formicos-app.ts`
- [ ] Template editor reads governance defaults instead of hardcoded 1.0/5
- [ ] Governance passed through `playbook-view.ts` to `fc-template-editor`
- [ ] Fabricated tier cost rates removed or replaced with backend estimate
- [ ] `reset()` uses governance defaults, not hardcoded values
- [ ] Input fallbacks use governance defaults, not hardcoded values
- [ ] `POST /api/v1/workspaces` endpoint exists, calls `runtime.create_workspace()`
- [ ] Workspace creation accessible from the frontend via REST (not WS)
- [ ] Addon config type coercion for boolean and integer values
- [ ] No regressions — all tests pass, frontend builds clean
