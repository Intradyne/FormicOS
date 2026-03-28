# Wave 72.5 Team C: Addon Lifecycle + Protocol Detail + Git Audit

## Mission

Add soft addon disable (runtime flag, not loader rewrite). Enhance the Settings
protocol section to show the detail that topbar badges currently show (Team A is
removing them). Hide the hello-world scaffold. Audit the git-control addon. Clean up
addon metadata for the disable/hidden flags.

## Owned files

- `src/formicos/surface/addon_loader.py` — `AddonManifest`, `AddonRegistration`, `register_addon()`
- `addons/*/addon.yaml` — addon manifests (all of them)
- `frontend/src/components/settings-view.ts` — Protocols section, Integrations card
- `src/formicos/surface/routes/api.py` — addon toggle endpoint (NEW, add near line 1491)

### Shared files with Team B (merge order: B first, then C)

- `src/formicos/surface/view_state.py` — Team B adds `handler`/`parameters`/`config`;
  you add `hidden` and `disabled` fields.
- `frontend/src/types.ts` — Team B expands `AddonToolSummary` and `AddonSummary`;
  you add `hidden` and `disabled` to `AddonSummary`.

### Do not touch

- `formicos-app.ts` (Team A)
- `addons-view.ts` (Team B — they own the UI for the disable toggle too)

## Repo truth (read before coding)

### Why addon disable is hard

1. **Registration is global, not workspace-scoped.** `register_addon()` at
   addon_loader.py:198 writes tools into `tool_registry` (process-wide dict) and
   handlers into `service_router` (process-wide). These registries are populated once
   at startup. There is no per-workspace tool routing layer.

2. **True workspace-scoped disable** would require either:
   - A dispatch-time filter (Queen tool dispatch checks workspace before calling addon tool)
   - Or re-registration on workspace config change
   Both are bigger than 72.5 scope.

3. **What we CAN do in 72.5: soft disable.** A `disabled` flag on `AddonRegistration`
   that is checked at runtime:
   - The `_tool_wrapper` (addon_loader.py:239-260) already has `_reg` in its closure.
     Add a check: `if _reg.disabled: return "Addon is disabled"` at the top.
   - The trigger endpoint (api.py:1471) already has `reg`. Add a check before calling.
   - The `_event_wrapper` for handlers — same pattern.
   - This means a disabled addon's tools are still *registered* in the Queen's tool list
     but return "Addon is disabled" if called. The UI marks them disabled so the operator
     knows. The Queen won't choose disabled tools because they return error results.

4. **Persistence**: Store the disabled flag via `WorkspaceConfigChanged` event at key
   `addon.{name}.disabled`. Read it on startup from projections. This follows the
   existing config pattern used by maintenance policy.

### Protocol detail gap

5. **Current Settings protocol section** at settings-view.ts:676-702 —
   `_renderProtocolsSummary()` shows 3 rows: protocol name + status pill (`active`/`inactive`).
   That's it. No tool count, no event count, no A2A endpoint/semantics.

6. **Current topbar badges** (being removed by Team A) show:
   - MCP: `{tools} tools`
   - AG-UI: `{events} events` or `inactive`
   - A2A: `{semantics} {endpoint}` (e.g., `poll/result /a2a/tasks`) or `inactive`

7. **Protocol data** is in `store.state.protocolStatus` which has:
   - `mcp: { status, tools }` (tool count)
   - `agui: { status, events }` (event count)
   - `a2a: { status, semantics, endpoint, note }` (endpoint info)

   This data is already available in `settings-view.ts` via `this.protocolStatus`.

### Addon manifests

8. **hello-world/addon.yaml** — scaffold addon, 1 tool (`hello_greet`). Dev reference
   only, clutters the operator UI.

9. **git-control/addon.yaml** — 4 tools: `smart_commit`, `branch_analysis`,
   `create_branch`, `stash_operations`. If all show 0 calls in production, the addon
   is unused and should explain when to use it vs MCP bridge.

## Track 1: Soft addon disable

### 1a. Add `disabled` to `AddonRegistration`

In `AddonRegistration.__init__()` (addon_loader.py:173), add:
```python
self.disabled: bool = False
```

### 1b. Add `hidden` to `AddonManifest`

In `AddonManifest` (addon_loader.py:62), add:
```python
hidden: bool = False  # Hide from operator UI (dev scaffolds)
```

### 1c. Modify `_tool_wrapper` to check disabled flag

In the `_tool_wrapper` closure (addon_loader.py:239-260), add at the top of the
function body (after the `_reg` increment lines are fine — add BEFORE the actual call):

```python
async def _tool_wrapper(
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
    *,
    _bound_fn: Callable[..., Any] = _fn,
    _pass_ctx: bool = _accepts_ctx,
    _bound_ctx: dict[str, Any] = _ctx,
    _tool_name: str = tool_spec.name,
    _reg: AddonRegistration = result,
) -> Any:
    if _reg.disabled:
        return f"Addon '{_reg.manifest.name}' is currently disabled."
    from datetime import UTC, datetime
    # ... rest of existing wrapper ...
```

### 1d. Modify event handler wrappers similarly

In the event handler registration loop (addon_loader.py:278+), the handler wrappers
should also check `_reg.disabled` and skip execution (log a debug message, don't
raise).

### 1e. Add toggle endpoint

Add a new endpoint near the trigger endpoint in `routes/api.py`:

```python
async def toggle_addon(request: Request) -> JSONResponse:
    """Enable or disable an addon."""
    addon_name = request.path_params["addon_name"]
    try:
        body = await request.json()
    except Exception:
        return _err_response("INVALID_JSON")

    disabled = body.get("disabled", False)

    regs: list[Any] = getattr(request.app.state, "addon_registrations", [])
    reg = next((r for r in regs if r.manifest.name == addon_name), None)
    if reg is None:
        return _err_response(
            "ADDON_NOT_FOUND",
            message=f"Addon '{addon_name}' not installed",
            status_code=404,
        )

    reg.disabled = bool(disabled)

    # Persist via workspace config (best-effort — survives restart)
    runtime = getattr(request.app.state, "runtime", None)
    workspace_id = body.get("workspace_id", "")
    if runtime and workspace_id:
        try:
            await runtime.set_workspace_config(
                workspace_id,
                f"addon.{addon_name}.disabled",
                disabled,
            )
        except Exception:
            pass  # In-memory flag still set; persistence is best-effort

    return JSONResponse({
        "addon": addon_name,
        "disabled": reg.disabled,
    })
```

Register the route:
```python
Route(
    "/api/v1/addons/{addon_name:str}/toggle",
    toggle_addon, methods=["POST"],
),
```

**Check whether `runtime.set_workspace_config()` exists.** If not, the in-memory
toggle is still useful for the session. Persistence can be added later. Search for
`set_workspace_config` or `WorkspaceConfigChanged` emit patterns in `runtime.py`.

### 1f. Load disabled state on startup

In the addon loading path (search for where `register_addon()` is called in `app.py`
or `runtime.py`), after registration, check workspace config projections for
`addon.{name}.disabled` and set `reg.disabled` accordingly.

### 1g. Add to snapshot and types

**view_state.py** — in `_build_addons()`, after Team B's changes, add to each addon dict:
```python
"hidden": manifest.hidden,
"disabled": reg.disabled,
```

Filter hidden addons from the snapshot:
```python
for reg in registrations:
    manifest = reg.manifest
    if manifest.hidden:
        continue
    # ... rest of existing code ...
```

**types.ts** — add to `AddonSummary`:
```typescript
export interface AddonSummary {
  // ... existing fields (after Team B's additions) ...
  disabled: boolean;                              // NEW
}
```
(`hidden` addons don't appear in the snapshot, so no `hidden` field needed in types.)

### 1h. Team B builds the UI toggle

You provide the backend (`/toggle` endpoint, `disabled` flag in snapshot). Team B's
`addons-view.ts` renders the toggle. Coordinate: tell Team B the endpoint shape is
`POST /api/v1/addons/{name}/toggle` with body `{ disabled: bool, workspace_id: string }`.

If Team B doesn't have capacity, add a minimal toggle to the detail panel yourself:
a simple checkbox at the top of `_renderDetail()`. But prefer Team B does it since they
own the file.

## Track 2: Expand Settings protocol section (MANDATORY)

Team A is removing topbar protocol badges. The information they showed must move to the
Settings Integrations card. This is not optional — without it, protocol detail is lost.

### Current state (settings-view.ts:676-702)

`_renderProtocolsSummary()` renders:
```html
<div class="proto-row">
  <fc-dot status="loaded|pending" size=4></fc-dot>
  <span class="proto-name">MCP</span>
  <fc-pill color="..." sm>active</fc-pill>
</div>
```

Three rows, name + status only.

### Target state

Each protocol row should show the detail that the topbar badge showed:

```html
<div class="proto-row">
  <fc-dot .status=${mcpStatus === 'active' ? 'loaded' : 'pending'} .size=${4}></fc-dot>
  <span class="proto-name">MCP</span>
  <span class="proto-detail">${mcpProto?.tools ?? 0} tools</span>
  <fc-pill color="var(--v-fg-dim)" sm style="margin-left:auto">${mcpStatus}</fc-pill>
</div>
<div class="proto-row">
  <fc-dot .status=${aguiStatus === 'active' ? 'loaded' : 'pending'} .size=${4}></fc-dot>
  <span class="proto-name">AG-UI</span>
  <span class="proto-detail">${aguiStatus === 'active'
    ? `${aguiProto?.events ?? 0} events` : ''}</span>
  <fc-pill color="var(--v-fg-dim)" sm style="margin-left:auto">${aguiStatus}</fc-pill>
</div>
<div class="proto-row">
  <fc-dot .status=${a2aStatus === 'active' ? 'loaded' : 'pending'} .size=${4}></fc-dot>
  <span class="proto-name">A2A</span>
  <span class="proto-detail">${a2aStatus === 'active'
    ? `${a2aProto?.semantics ?? ''} ${a2aProto?.endpoint ?? ''}`.trim() : ''}</span>
  <fc-pill color="var(--v-fg-dim)" sm style="margin-left:auto">${a2aStatus}</fc-pill>
</div>
```

Add CSS for `.proto-detail`:
```css
.proto-detail {
  font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim);
  margin-left: 4px;
}
```

This is ~20 lines of template change. Small but critical — without it, Team A's badge
removal creates an information regression.

## Track 3: Hide hello-world from production

1. Add `hidden: true` to `addons/hello-world/addon.yaml`:
   ```yaml
   name: hello-world
   version: "1.0.0"
   hidden: true
   description: "Trivial test addon — validates the addon loader pipeline"
   ```

2. The hidden filter in `_build_addons()` (Track 1g) ensures it doesn't appear in the
   operator snapshot. The addon still loads and its tool still works (testable via API),
   it just doesn't clutter the UI.

## Track 4: Git addon audit + description update

### Investigation (do first, informs the description)

1. Check the running instance: are any git-control tools showing non-zero call counts?
2. Check `config/caste_recipes.yaml`: are `smart_commit`, `branch_analysis`,
   `create_branch`, or `stash_operations` in any caste's tool list?
3. If the answer to both is "no," the addon is dormant.

### Update the description

In `addons/git-control/addon.yaml`, update the description field:

```yaml
description: >
  Git intelligence for the Queen — smart_commit, branch_analysis,
  create_branch, and stash_operations. If you have a git MCP server
  connected via the mcp-bridge addon, these tools overlap and this
  addon can be disabled.
```

This gives the operator the information they need to decide whether to disable it
(using the new Track 1 toggle).

## Coordination with Team B

### Merge order: Team B first, then Team C

Team B expands `view_state.py` and `types.ts` with tool metadata and config schema.
You add `hidden`/`disabled` fields on top. Both teams should communicate their changes
so merges are clean.

### Shared understanding

- **Team B** provides: expanded `AddonToolSummary` (+ handler, parameters),
  `AddonConfigParam` type, `config` field on `AddonSummary`.
- **Team C** provides: `disabled` on `AddonSummary`, `hidden` filter in `_build_addons()`,
  toggle endpoint, soft disable in tool/handler wrappers.
- **Team B** renders the disable toggle in `addons-view.ts` using the `disabled` field
  and calling `POST /api/v1/addons/{name}/toggle`.

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
cd frontend && npm run build && npm run lint
```

Verify in the running stack:
- Settings > Integrations > Protocols shows tool count, event count, endpoint detail
- hello-world addon does not appear in the Addons tab
- Addon toggle endpoint works: `curl -X POST localhost:8080/api/v1/addons/git-control/toggle -d '{"disabled": true, "workspace_id": "default"}'`
- After disabling, git-control tools return "Addon is disabled" if called
- git-control addon description mentions MCP bridge overlap

## Acceptance criteria

- [ ] `AddonManifest` has `hidden: bool = False` field
- [ ] `AddonRegistration` has `disabled: bool = False` field
- [ ] `_tool_wrapper` checks `_reg.disabled` and returns early if disabled
- [ ] Event handler wrappers check disabled flag similarly
- [ ] `POST /api/v1/addons/{name}/toggle` endpoint exists and sets flag
- [ ] Disabled state persisted via workspace config (or clearly documented as session-only)
- [ ] hello-world addon hidden from operator UI via `hidden: true` in manifest
- [ ] `_build_addons()` filters hidden addons from snapshot
- [ ] `disabled` field in snapshot and `types.ts`
- [ ] Settings protocol section shows MCP tool count, AG-UI event count, A2A endpoint detail
- [ ] git-control addon description updated with MCP bridge comparison note
- [ ] No regressions — all tests pass, frontend builds clean
