# Wave 72.5 Team B: Fix Addon Triggers + Interactive Addons + Metadata Expansion

## Mission

The addon trigger endpoint is broken — it calls handlers without required positional
arguments. Fix the backend. Then expand the addon metadata pipeline so the frontend has
the data it needs for interactive features (config editing, tool testing). Finally,
transform the addons tab from a read-only diagnostic dashboard into an interactive
operator surface.

## Owned files

- `src/formicos/surface/routes/api.py` — `trigger_addon()` endpoint (lines 1427-1491)
- `src/formicos/surface/view_state.py` — `_build_addons()` (lines 47-97)
- `frontend/src/types.ts` — `AddonToolSummary`, `AddonSummary` interfaces (lines 681-717)
- `frontend/src/components/addons-view.ts` — full component (221 lines)

### Do not touch

- `formicos-app.ts` (Team A)
- `addon_loader.py` (Team C)
- `settings-view.ts` (Team C)
- Addon source files (`src/formicos/addons/*/`)
- Addon manifests (`addons/*/addon.yaml`)

## Repo truth (read before coding)

### The trigger bug

1. **api.py lines 1471-1477** — the trigger endpoint calls handlers like this:
   ```python
   if accepts_ctx:
       result = await handler_fn(runtime_context=reg.runtime_context)
   else:
       result = await handler_fn()
   ```

2. **But handler signatures expect 3 positional args.** Both `codebase_index/search.py:94`
   and `docs_index/search.py:94` have:
   ```python
   async def handle_reindex(
       inputs: dict[str, Any],
       workspace_id: str,
       thread_id: str,
       *,
       runtime_context: dict[str, Any] | None = None,
   ) -> str:
   ```

3. **The error:** `handle_reindex() missing 3 required positional arguments: 'inputs', 'workspace_id', and 'thread_id'`

4. **How Queen tool dispatch does it right** — in `addon_loader.py` lines 239-260, the
   `_tool_wrapper` closure receives `(inputs, workspace_id, thread_id)` from the tool
   dispatch pipeline and passes them through to the real handler. The trigger endpoint
   bypasses this wrapper — it resolves the raw handler function via `_resolve_handler()`
   and calls it directly, which means it must provide those positional args itself.

### The metadata gap

5. **Current `AddonToolSummary`** in `types.ts:681-684` has only:
   ```typescript
   { name: string; description: string; callCount: number; }
   ```
   Missing: `handler` (needed for trigger endpoint call), `parameters` (JSON schema,
   needed for "Try" form generation).

6. **Current `AddonSummary`** in `types.ts:707-717` has no `config` field. The addon
   manifest declares `config: list[AddonConfigParam]` with fields
   `key`, `type` (boolean|string|integer|cron|select), `default`, `label`, `options`
   (addon_loader.py:52-59), but none of this reaches the frontend via the snapshot.

7. **`_build_addons()`** in `view_state.py:60-66` only emits `name`, `description`,
   `callCount` per tool. It does not emit `handler` or `parameters`.

8. **Addon config endpoints exist** — `GET /api/v1/addons/{name}/config?workspace_id=X`
   at api.py:1495 returns schema + current values. `PUT /api/v1/addons/{name}/config`
   saves values. These were shipped in Wave 66 but never wired into the frontend.

### The addons view

9. **addons-view.ts** is a 221-line component: sidebar list + detail panel. Detail shows
   name, version, status, description, error badge, tools table (name/desc/calls),
   handlers table (event/lastFired/errors), triggers table (type/schedule/button).
   Everything is read-only except the broken "Trigger Now" button.

10. **`_fireTrigger()`** at line 201-220 sends `POST /api/v1/addons/${addonName}/trigger`
    with body `{ handler: manualTrigger?.handler ?? '' }`. No workspace_id, no inputs.

## Track 1: Fix the trigger endpoint (BLOCKER — do this first)

The handler signature convention for addon tools is `(inputs, workspace_id, thread_id, *, runtime_context=None)`. The trigger endpoint must detect this and provide the args.

**In `trigger_addon()` at api.py line 1463**, after resolving `handler_fn` and checking
`accepts_ctx`, also detect whether the handler expects positional args:

```python
import inspect  # already imported above

sig = inspect.signature(handler_fn)
positional_params = [
    p for p in sig.parameters.values()
    if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    and p.name not in ('self', 'cls', 'runtime_context')
]
has_tool_args = len(positional_params) >= 3

inputs = body.get("inputs", {})
workspace_id = body.get("workspace_id", "")
thread_id = body.get("thread_id", "")

try:
    if has_tool_args and accepts_ctx:
        result = await handler_fn(
            inputs, workspace_id, thread_id,
            runtime_context=reg.runtime_context,
        )
    elif has_tool_args:
        result = await handler_fn(inputs, workspace_id, thread_id)
    elif accepts_ctx:
        result = await handler_fn(runtime_context=reg.runtime_context)
    else:
        result = await handler_fn()
```

This replaces the existing try block at lines 1471-1477. The rest of the function
(error handling, trigger_fire_times recording, response) stays the same.

**Frontend side** — in `_fireTrigger()` at addons-view.ts line 209, add `workspace_id`:
```typescript
body: JSON.stringify({
    handler: manualTrigger?.handler ?? '',
    workspace_id: store.state.tree?.[0]?.id ?? '',
}),
```

**Test this immediately** after implementing. Trigger the codebase-index reindex from
the Addons tab — it should return a success message instead of the positional args error.

## Track 2: Expand addon metadata pipeline

The frontend needs tool parameters and config schema to build interactive forms. Expand
the data pipeline in two places.

### 2a. Expand `view_state.py` `_build_addons()`

Add `handler` and `parameters` to tool summaries, and add `config` schema to addon
summaries. At view_state.py lines 60-66, change the tools list:

```python
"tools": [
    {
        "name": t.name,
        "description": t.description,
        "handler": t.handler,                    # NEW
        "parameters": t.parameters,              # NEW — JSON schema dict
        "callCount": reg.tool_call_counts.get(t.name, 0),
    }
    for t in manifest.tools
],
```

After the `"lastError"` field (line 95), add:

```python
"config": [
    {
        "key": c.key,
        "type": c.type,
        "default": c.default,
        "label": c.label,
        "options": c.options,
    }
    for c in manifest.config
],
```

### 2b. Expand `types.ts` interfaces

Update `AddonToolSummary` (types.ts:681):
```typescript
export interface AddonToolSummary {
  name: string;
  description: string;
  handler: string;                               // NEW
  parameters: Record<string, any>;               // NEW — JSON schema
  callCount: number;
}
```

Add a new interface:
```typescript
export interface AddonConfigParam {
  key: string;
  type: 'boolean' | 'string' | 'integer' | 'cron' | 'select';
  default: any;
  label: string;
  options: string[];
}
```

Update `AddonSummary` (types.ts:707):
```typescript
export interface AddonSummary {
  name: string;
  version: string;
  description: string;
  tools: AddonToolSummary[];
  handlers: AddonHandlerSummary[];
  triggers: AddonTriggerSummary[];
  panels: AddonPanelSummary[];
  config: AddonConfigParam[];                    // NEW
  status: 'healthy' | 'degraded' | 'error';
  lastError: string | null;
}
```

### 2c. Coordinate with Team C

Team C is adding `hidden: bool` and `disabled: bool` to addon data. Those fields will
also need to appear in the snapshot and types. If Team C adds them to `AddonRegistration`
and `AddonManifest`, you add them to `_build_addons()` and `types.ts`. Merge order:
**Team B lands first** (metadata expansion), then Team C adds their fields on top.

## Track 3: Interactive tool testing ("Try It")

Add a "Try" button to each row in the tools table. When clicked, expand an inline form
below the row.

### State additions

```typescript
@state() private _tryingTool: string | null = null;   // tool name being tested
@state() private _tryInputs: Record<string, any> = {}; // current form values
@state() private _tryResult: string = '';               // result text
@state() private _tryLoading = false;                   // loading indicator
```

### Tools table modification

In the tools table (lines 144-156), add a "Try" column header and button per row:

```html
<tr><th>Name</th><th>Description</th><th>Calls</th><th></th></tr>
${addon.tools.map(t => html`
  <tr>
    <td>${t.name}</td>
    <td style="color:var(--v-fg-dim)">${t.description}</td>
    <td>${t.callCount}</td>
    <td>
      <button class="trigger-btn"
        @click=${() => { this._tryingTool = this._tryingTool === t.name ? null : t.name; this._tryResult = ''; }}>
        ${this._tryingTool === t.name ? 'Close' : 'Try'}
      </button>
    </td>
  </tr>
  ${this._tryingTool === t.name ? html`
    <tr><td colspan="4">${this._renderTryForm(addon, t)}</td></tr>
  ` : nothing}
`)}
```

### The try form

`_renderTryForm(addon: AddonSummary, tool: AddonToolSummary)`:

1. Parse `tool.parameters` JSON schema. For each property in
   `tool.parameters.properties` (if it exists):
   - `string` type → `<input type="text">`
   - `integer`/`number` type → `<input type="number">`
   - `boolean` type → `<input type="checkbox">`
   - `array`/`object` type → `<textarea>` (user enters JSON)
   - Show the property description as a hint below the input
   - Use the property name as the label

2. If `tool.parameters` is empty or has no properties, show a single message:
   "No parameters — runs with empty inputs."

3. "Run" button:
   ```typescript
   @click=${async () => {
     this._tryLoading = true;
     this._tryResult = '';
     try {
       const resp = await fetch(`/api/v1/addons/${addon.name}/trigger`, {
         method: 'POST',
         headers: { 'Content-Type': 'application/json' },
         body: JSON.stringify({
           handler: tool.handler,
           inputs: this._tryInputs,
           workspace_id: store.state.tree?.[0]?.id ?? '',
         }),
       });
       const data = await resp.json();
       this._tryResult = resp.ok
         ? (data.result ?? 'ok')
         : `Error: ${data.error ?? resp.statusText}`;
     } catch (e) {
       this._tryResult = `Error: ${e}`;
     }
     this._tryLoading = false;
   }}
   ```

4. Result display: monospace pre-formatted block below the form with word-wrap.

### Form CSS

```css
.try-form {
  padding: 12px; background: rgba(6,6,12,0.5); border-radius: 8px;
  margin: 4px 0;
}
.try-field { margin-bottom: 8px; }
.try-field label {
  display: block; font-size: 10px; font-family: var(--f-mono);
  color: var(--v-fg-dim); margin-bottom: 2px;
}
.try-field input, .try-field textarea {
  width: 100%; box-sizing: border-box; padding: 5px 8px;
  background: var(--v-recessed); border: 1px solid var(--v-border);
  border-radius: 6px; color: var(--v-fg); font-family: var(--f-mono);
  font-size: 11px;
}
.try-result {
  margin-top: 8px; padding: 8px; background: var(--v-recessed);
  border-radius: 6px; font-family: var(--f-mono); font-size: 11px;
  white-space: pre-wrap; word-break: break-word; color: var(--v-fg);
  max-height: 200px; overflow-y: auto;
}
```

## Track 4: Inline addon config editing

Below the triggers table, add a "Configuration" section for addons that declare config
params.

### Implementation

1. The config schema is now in the snapshot (Track 2), so `addon.config` is available.
   Current config **values** still need to be fetched per-addon because the snapshot
   only has the schema (defaults), not workspace-scoped overrides.

2. State additions:
   ```typescript
   @state() private _configValues: Record<string, any> = {};
   @state() private _configLoading = false;
   @state() private _configSaving = false;
   @state() private _configSaved = false;
   ```

3. Fetch on addon selection: in the `_selectedAddon` getter or in `updated()`, when
   the selected addon changes and it has `config.length > 0`:
   ```typescript
   const resp = await fetch(
     `/api/v1/addons/${addon.name}/config?workspace_id=${store.state.tree?.[0]?.id ?? ''}`,
   );
   if (resp.ok) {
     const data = await resp.json();
     this._configValues = data.values ?? {};
   }
   ```

4. Render a config section after the triggers table:
   ```html
   ${addon.config.length > 0 ? html`
     <div class="section-title">Configuration</div>
     <div class="config-form">
       ${addon.config.map(c => this._renderConfigField(c))}
       <fc-btn variant="primary" sm
         ?disabled=${this._configSaving}
         @click=${() => this._saveConfig(addon.name)}>
         ${this._configSaving ? 'Saving…' : 'Save Config'}
       </fc-btn>
       ${this._configSaved ? html`<span style="...">✓ Saved</span>` : nothing}
     </div>
   ` : nothing}
   ```

5. `_renderConfigField(param: AddonConfigParam)`:
   - `boolean` → checkbox
   - `string` → text input
   - `integer` → number input
   - `select` → `<select>` with `param.options`
   - `cron` → text input with placeholder hint "0 3 * * *"
   - Label: `param.label || param.key`
   - Current value: `this._configValues[param.key] ?? param.default`

6. Save:
   ```typescript
   private async _saveConfig(addonName: string) {
     this._configSaving = true;
     try {
       await fetch(`/api/v1/addons/${addonName}/config`, {
         method: 'PUT',
         headers: { 'Content-Type': 'application/json' },
         body: JSON.stringify({
           workspace_id: store.state.tree?.[0]?.id ?? '',
           values: this._configValues,
         }),
       });
       this._configSaved = true;
       setTimeout(() => { this._configSaved = false; }, 2000);
     } catch { /* show error */ }
     this._configSaving = false;
   }
   ```

## Track 5: Better error display + trigger status

When `addon.lastError` is set, replace the simple red text (line 142) with a card that
includes a retry action:

```html
${addon.lastError ? html`
  <div class="error-card">
    <span class="error-text">⚠ ${addon.lastError}</span>
    <button class="trigger-btn" @click=${() => this._fireTrigger(addon.name)}>Retry</button>
  </div>
` : nothing}
```

**Error card CSS:**
```css
.error-card {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; border-radius: 8px;
  background: rgba(232,88,26,0.06); border: 1px solid rgba(232,88,26,0.15);
  margin-bottom: 12px;
}
.error-text {
  font-size: 11px; color: #E8581A; font-family: var(--f-mono); flex: 1;
}
```

## Validation

```bash
cd frontend && npm run build && npm run lint
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Verify in the running stack at http://localhost:8080:
- Navigate to Addons tab, select codebase-index
- "Trigger Now" works (no positional args error)
- Tools table has "Try" buttons
- Click "Try" on `semantic_search_code`, enter a query, click Run — result appears
- If addon has config params, Configuration section appears with editable fields
- Error display shows retry button

## Acceptance criteria

- [ ] Trigger endpoint passes `inputs`, `workspace_id`, `thread_id` to tool-convention handlers
- [ ] "Trigger Now" works for codebase-index and docs-index reindex
- [ ] `view_state.py` emits `handler`, `parameters` per tool and `config` schema per addon
- [ ] `types.ts` has `handler`, `parameters` on `AddonToolSummary` and `config` on `AddonSummary`
- [ ] Tools table has "Try" buttons that expand inline parameter forms
- [ ] Try form generates inputs from JSON schema and sends to trigger endpoint
- [ ] Try result displays in monospace block
- [ ] Config section renders for addons with config params
- [ ] Config values fetchable and saveable via existing config endpoints
- [ ] Error display includes retry button
- [ ] No regressions in addon functionality, frontend builds clean, all tests pass
