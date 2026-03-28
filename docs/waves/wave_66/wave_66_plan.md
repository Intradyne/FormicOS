# Wave 66: Addons as First-Class Software

**Status:** Planning
**Predecessor:** Wave 65.5 (Addon System Polish)
**Theme:** Make addons visible, configurable, and extensible to the operator.

Wave 65 made every addon functional -- real git operations, real vector
search, real proactive intelligence. Wave 66 makes them visible: an Addons
tab with health monitoring, a config surface backed by existing events, and
a generic panel renderer that lets addons contribute UI to existing tabs.

## Contract Change Blocker

**Track 1 requires operator approval before work begins.** The
`OperatorStateSnapshot` interface must gain an `addons` field. This is a
contract file change affecting:

- `docs/contracts/types.ts:436-447` -- OperatorStateSnapshot interface
- `frontend/src/types.ts:650-661` -- mirrored OperatorStateSnapshot

Both files are under `docs/contracts/` governance. Approve before dispatch.

## Pre-existing State

**Addon infrastructure (Wave 64-65):** Manifest loader discovers
`addons/*/addon.yaml`, resolves handlers via `_resolve_handler()`,
registers tools into Queen's dispatcher, event handlers into
`service_router`, triggers into `TriggerDispatcher`. Runtime context
injection passes vector_port, event_store, projections, settings, and
workspace_root_fn to handlers that accept `runtime_context` kwargs.

**Addon manifests declare three unimplemented fields:**
`addon_loader.py:267-278` logs warnings for `panels`, `routes`, and
`templates` -- "registration is not yet implemented." No addon currently
declares any of these fields.

**AddonManifest has no `config` field:** `addon_loader.py:52-64` supports
name, version, description, author, tools, handlers, panels, templates,
routes, triggers. No config schema.

**No addon UI:** Zero addon references in `frontend/src/components/`.
`AddonLoaded`, `AddonUnloaded`, `ServiceTriggerFired` events are defined
in the type system but the frontend store ignores them.

**No addon REST endpoints:** No `/api/v1/addons` routes exist.

**Snapshot has no addon data:** `build_snapshot()` (`view_state.py:21-42`)
returns 10 fields. No `addons` field. `app.state.addon_manifests` is set
at `app.py:780` but `_addon_registrations` is a local variable
(`app.py:738`) never stored on `app.state`. T1 must add
`app.state.addon_registrations = _addon_registrations` after line 780
and pass it to the snapshot builder.

**WebSocket handler:** `ws_handler.py:332-349` calls `build_snapshot()`
and sends the result. No addon data flows to clients.

**TriggerDispatcher.fire_manual():** Returns a descriptor dict but does
not execute the handler (`trigger_dispatch.py:140-149`). Execution logic
exists in `queen_tools.py:_trigger_addon()`.

**MemoryEntryMerged Qdrant bug (confirmed):** `runtime.py:535-536` syncs
only `target_id` after a merge. The source entry is marked `rejected` in
projections (`projections.py:1820-1833`) but its Qdrant vector is never
deleted. `memory_store.py:82-99` has the correct deletion path for
rejected entries -- it just never receives the source_id. Stale embeddings
accumulate daily.

**Knowledge ROI rule gap (confirmed):** `_rule_knowledge_roi()` in
`rules.py:691-727` only checks `entries_extracted`. `entries_accessed` is
computed on `ColonyOutcome` (`projections.py:1057-1065`) but unused by
any proactive intelligence rule.

**CLAUDE.md composite weights stale:** Documents Wave 34 formula
(`0.15*freshness`, `0.05*cooccurrence`). Actual Wave 59.5 weights in
`knowledge_constants.py:33-41`: freshness=0.10, cooccurrence=0.04,
graph_proximity=0.06.

---

## Side Task S3: MemoryEntryMerged Qdrant Source Cleanup (Merge First)

**Correctness bug. Merge independently before tracks start.**

In `src/formicos/surface/runtime.py:535-536`, the `MemoryEntryMerged`
handler only syncs `target_id`:

```python
elif etype == "MemoryEntryMerged":
    sync_id = str(getattr(event_with_seq, "target_id", ""))
```

The source entry is marked `rejected` by the projection handler
(`projections.py:1829`) but `sync_entry()` is never called for it. Since
`sync_entry()` (`memory_store.py:89-91`) correctly calls
`vector_port.delete()` for rejected entries, the fix is to sync both IDs:

```python
elif etype == "MemoryEntryMerged":
    for _attr in ("target_id", "source_id"):
        _eid = str(getattr(event_with_seq, _attr, ""))
        if _eid:
            await self.memory_store.sync_entry(
                _eid, self.projections.memory_entries,
            )
    continue
```

**File:** `src/formicos/surface/runtime.py` -- lines 535-542 only.

**Test:** 1 new -- merge event triggers delete for source entry vector.

**Do not touch:** Any other file.

---

## Track 1: Addons Tab + Health Monitoring + Manual Trigger UI

### Problem

Addons are invisible. The operator cannot see what addons are installed,
whether they're healthy, when their tools were last used, or fire manual
triggers without asking the Queen. The 6-tab nav (Queen, Knowledge,
Workspace, Playbook, Models, Settings) has no addon surface.

### Fix

**1. Add `addons` field to OperatorStateSnapshot.**

After operator approval, add to both contract files and the frontend
mirror:

```typescript
// docs/contracts/types.ts:436-447 and frontend/src/types.ts:650-661
export interface OperatorStateSnapshot {
  // ... existing 10 fields ...
  addons: AddonSummary[];
}

export interface AddonSummary {
  name: string;
  version: string;
  description: string;
  tools: { name: string; description: string; callCount: number }[];
  handlers: { event: string; lastFired: string | null; errorCount: number }[];
  triggers: { type: string; schedule: string; lastFired: string | null }[];
  status: 'healthy' | 'degraded' | 'error';
  lastError: string | null;
}
```

**2. Extend `build_snapshot()` to include addon data.**

Add `addon_registrations` parameter to `build_snapshot()`
(`view_state.py:21-29`). Build `AddonSummary` entries from the
registration objects. Health status derived from handler error counts
(0 = healthy, 1-2 = degraded, 3+ = error).

**3. Pass addon registrations from `ws_handler.py`.**

`send_state()` (`ws_handler.py:332-349`) must pass addon registrations
to `build_snapshot()`. Store registrations on `WebSocketManager` the
same way `_projections` and `_settings` are stored.

**4. Add `AddonHealthSnapshot` tracking to `AddonRegistration`.**

Extend `AddonRegistration` (`addon_loader.py:142-150`) with runtime
counters: `tool_call_counts: dict[str, int]`, `last_tool_call: str | None`,
`handler_error_count: int`, `last_handler_fire: str | None`,
`last_error: str | None`. Increment counters in the tool/event wrapper
closures.

**5. REST endpoints.**

Add to `routes/api.py` (after line 1391):

- `GET /api/v1/addons` -- list installed addons with health summary.
  Data from `request.app.state.addon_registrations`.
- `POST /api/v1/addons/{name}/trigger` -- resolve handler via
  `_resolve_handler()`, execute with `runtime_context`, return result.
  Not just `fire_manual()` descriptor -- actual execution. Pattern from
  `app.py:808-828` cron loop.

**6. New `fc-addons-view.ts` component.**

Two-column layout: left sidebar lists addons with status dots
(green/amber/red), right panel shows selected addon detail. Detail
sections: description, version, tools table (name, description, call
count), handlers table (event, last fired, errors), triggers table
(type, schedule, last fired, "Trigger Now" button for manual type).

**7. Add Addons tab to nav.**

In `formicos-app.ts:26-35`:
- Add `'addons'` to `ViewId` union
- Add `{ id: 'addons', label: 'Addons', icon: '\u2699' }` to NAV array
  (position 4, after Workspace)
- Update `grid-template-columns` at line 60 from `repeat(6, ...)` to
  `repeat(7, ...)`
- Add `'addons': () => this._renderAddons()` to `_viewRegistry`
  (line 512-520)
- Add `_renderAddons()` method that renders `<fc-addons-view>`
- Add `import './addons-view.js'` to imports

**8. Update store.**

In `store.ts:57-71`: add `addons: AddonSummary[]` to `StoreState`. In
`applySnapshot()` (line 126-143): map `snap.addons` to state. In
`emptyState()` (line 75): default `addons: []`.

### Files

- `docs/contracts/types.ts` -- add AddonSummary + snapshot field (~15 lines)
- `frontend/src/types.ts` -- mirror contract change (~15 lines)
- `frontend/src/components/addons-view.ts` -- **new** (~250 lines)
- `frontend/src/components/formicos-app.ts` -- nav + view registry (~15 lines)
- `frontend/src/state/store.ts` -- state + snapshot mapping (~10 lines)
- `src/formicos/surface/view_state.py` -- build_snapshot addon field (~30 lines)
- `src/formicos/surface/ws_handler.py` -- pass registrations (~5 lines)
- `src/formicos/surface/addon_loader.py` -- AddonRegistration counters (~20 lines)
- `src/formicos/surface/routes/api.py` -- 2 endpoints (~50 lines)
- `src/formicos/surface/app.py` -- add `app.state.addon_registrations`
  after line 780 (currently only manifests are stored, not registrations)
  (~3 lines)

### Tests

4 new:
- Addon health snapshot includes installed addons
- GET /api/v1/addons returns addon list with health
- POST /api/v1/addons/{name}/trigger executes handler
- Tool wrapper increments call count on AddonRegistration

### Acceptance Gates

- Addons tab visible in nav with 7 columns
- Clicking an addon shows detail with tools, handlers, triggers
- "Trigger Now" button fires manual trigger and shows result
- WebSocket snapshot includes addon data on connect
- All existing tests pass

### Owner

Team 1. Merge first among tracks (unblocks T2).

### Do Not Touch

`queen_tools.py`, `queen_runtime.py`, `knowledge_catalog.py`, any
`core/` or `engine/` files, addon manifest YAML files.

---

## Track 2: Addon Config Surface

### Problem

Addons have no configurable parameters. The operator cannot toggle
git_auto_stage, change the reindex schedule, or disable specific
proactive rules without editing YAML files. `AddonManifest` has no
`config` field.

### Fix

**1. Add `AddonConfigParam` model and `config` field to manifest.**

In `addon_loader.py` (after `AddonTriggerSpec`, line 50):

```python
class AddonConfigParam(BaseModel):
    """A configurable parameter declared by an addon."""
    key: str
    type: Literal["boolean", "string", "integer", "cron", "select"] = "string"
    default: Any = None
    label: str = ""
    options: list[str] = Field(default_factory=list)  # for select type
```

Add `config: list[AddonConfigParam] = Field(default_factory=list)` to
`AddonManifest` (line 64).

**2. REST endpoints for config.**

Add to `routes/api.py`:

- `GET /api/v1/addons/{name}/config` -- returns config schema from
  manifest + current values from workspace config. Current values stored
  under `addon.{name}.{key}` dimension in `WorkspaceConfigChanged` events.
  Falls back to manifest defaults.
- `PUT /api/v1/addons/{name}/config` -- accepts `{key: value}` dict,
  emits `WorkspaceConfigChanged` event for each key using
  `field="addon.{name}.{key}"`, `new_value=value`. Existing pattern from
  `routes/api.py` config-overrides endpoint.

**3. Config form in addons-view.ts.**

Add a `_renderConfigPanel()` method to `addons-view.ts` (Team 1's
component). Renders controls based on config schema: toggle for boolean,
text input for string/cron, number input for integer, dropdown for select.
Save button POSTs to `/api/v1/addons/{name}/config`.

**4. Update addon manifests with config declarations.**

`addons/git-control/addon.yaml`:
```yaml
config:
  - key: git_auto_stage
    type: boolean
    default: true
    label: "Auto-stage modified files after colony completion"
```

`addons/codebase-index/addon.yaml`:
```yaml
config:
  - key: chunk_size
    type: integer
    default: 500
    label: "Chunk size (characters) for code splitting"
  - key: skip_dirs
    type: string
    default: "__pycache__,node_modules,.git,.venv"
    label: "Directories to skip (comma-separated)"
```

`addons/proactive-intelligence/addon.yaml`:
```yaml
config:
  - key: disabled_rules
    type: string
    default: ""
    label: "Rules to disable (comma-separated names)"
```

### Files

- `src/formicos/surface/addon_loader.py` -- AddonConfigParam + field (~15 lines)
- `src/formicos/surface/routes/api.py` -- 2 config endpoints (~40 lines)
- `frontend/src/components/addons-view.ts` -- config form section (~60 lines)
- `addons/git-control/addon.yaml` -- config block (~5 lines)
- `addons/codebase-index/addon.yaml` -- config block (~8 lines)
- `addons/proactive-intelligence/addon.yaml` -- config block (~5 lines)

### Overlap Rule

Team 2 adds a `_renderConfigPanel(addon: AddonSummary)` method to
`addons-view.ts`. Team 1 owns the component structure and calls
`this._renderConfigPanel(this._selectedAddon)` from the detail panel.
Team 2 must reread the component after Team 1 merges to confirm the
integration point. If T1 changes the selected addon property name or
detail panel structure, Team 2 adapts `_renderConfigPanel` to match --
the method signature (receives the selected addon object, returns a
`TemplateResult`) is the stable contract, not the call site.

### Tests

3 new:
- GET /api/v1/addons/{name}/config returns schema with defaults
- PUT /api/v1/addons/{name}/config emits WorkspaceConfigChanged
- AddonManifest parses config field from YAML

### Acceptance Gates

- Config panel renders controls matching manifest schema
- Changing a config value persists via WorkspaceConfigChanged event
- Config values survive replay (event-sourced, no shadow state)
- Addon handlers can read config from `runtime_context["settings"]`

### Owner

Team 2. Depends on T1 for component structure. Merge after T1.

### Do Not Touch

`queen_tools.py`, `queen_runtime.py`, `core/events.py`, any `core/` or
`engine/` files. Do not add new event types.

---

## Track 3: Addon Panels + Routes

### Problem

The manifest declares `panels` and `routes` fields but
`addon_loader.py:267-278` explicitly warns they are unimplemented. Addons
cannot contribute visible UI to existing tabs or register HTTP endpoints.
The codebase-index addon has no way to show "last indexed: 3h ago, 1,247
chunks" in the Knowledge tab. The git-control addon has no way to show
branch status in the Workspace tab.

### Fix

**1. Wire `routes` field in addon_loader.py.**

In `register_addon()` (`addon_loader.py:152-280`), after the existing
handler registration block: iterate `manifest.routes`, resolve each
handler via `_resolve_handler()`, store resolved routes on
`AddonRegistration` as `registered_routes: list[dict]`. Each dict:
`{"path": str, "handler": Callable, "addon_name": str}`.

**2. Mount addon routes in app.py.**

In `app.py` (after line 784, before routes construction at line 952):
iterate `_addon_registrations`, for each registered route create a
Starlette `Route` at `/addons/{addon_name}{path}`. Handler wraps the
resolved function in a Starlette request handler that extracts query
params and calls the addon handler with `runtime_context`.

**3. Wire `panels` field.**

Store panel declarations on `AddonRegistration` as
`registered_panels: list[dict]`. Each dict from manifest:
`{"target": str, "display_type": str, "path": str, "handler": str}`.
Include panel data in the `AddonSummary` sent via WebSocket snapshot
(coordinate with T1's snapshot field).

**4. New `fc-addon-panel.ts` component.**

Generic panel renderer. Receives a `src` URL (addon route endpoint) and
`display-type` attribute. On connect, fetches JSON from `src`. Renders
based on `display_type`:

- `status_card`: key-value grid. Each item: `{label: str, value: str}`.
  Rendered as a compact card with label/value pairs.
- `table`: `{columns: str[], rows: any[][]}`. Rendered as a data table.
- `log`: `{entries: {ts: str, message: str}[]}`. Rendered as timestamped
  list.

Auto-refreshes every 60 seconds.

**5. Panel injection into existing tabs.**

`knowledge-browser.ts`: at the top of the render method (after the title
row, line 18-19 area), add a panel injection zone. For each addon panel
with `target: "knowledge"`, render
`<fc-addon-panel src="/addons/{name}{path}" display-type="{type}">`.
Panel data comes from `store.state.addons`.

`workspace-browser.ts`: same injection zone at the top of the component.
Panels with `target: "workspace"` render here.

**6. Addon status endpoints.**

`src/formicos/addons/codebase_index/status.py` -- **new file**:
```python
async def get_status(
    inputs: dict, workspace_id: str, thread_id: str,
    *, runtime_context: dict | None = None,
) -> dict:
    """Return index status as status_card data."""
    # Query vector_port for collection stats
    # Return {display_type: "status_card", items: [...]}
```

`src/formicos/addons/git_control/status.py` -- **new file**:
```python
async def get_status(
    inputs: dict, workspace_id: str, thread_id: str,
    *, runtime_context: dict | None = None,
) -> dict:
    """Return git workspace status as status_card data."""
    # Run git status, git branch --show-current
    # Return {display_type: "status_card", items: [...]}
```

**7. Update addon manifests.**

`addons/codebase-index/addon.yaml`:
```yaml
panels:
  - target: knowledge
    display_type: status_card
    path: /status
    handler: status.py::get_status
routes:
  - path: /status
    handler: status.py::get_status
```

`addons/git-control/addon.yaml`:
```yaml
panels:
  - target: workspace
    display_type: status_card
    path: /status
    handler: status.py::get_status
routes:
  - path: /status
    handler: status.py::get_status
```

### Files

- `frontend/src/components/addon-panel.ts` -- **new** (~100 lines)
- `frontend/src/components/knowledge-browser.ts` -- panel injection zone (~10 lines)
- `frontend/src/components/workspace-browser.ts` -- panel injection zone (~10 lines)
- `src/formicos/surface/addon_loader.py` -- route + panel wiring (~30 lines)
- `src/formicos/surface/app.py` -- route mounting (~20 lines)
- `src/formicos/addons/codebase_index/status.py` -- **new** (~30 lines)
- `src/formicos/addons/git_control/status.py` -- **new** (~30 lines)
- `addons/codebase-index/addon.yaml` -- panels + routes block (~8 lines)
- `addons/git-control/addon.yaml` -- panels + routes block (~8 lines)

### Tests

4 new:
- Route mounting resolves addon handler and returns 200
- Panel endpoint returns valid status_card JSON
- fc-addon-panel renders status_card items
- Addon registration includes resolved routes

### Acceptance Gates

- `GET /addons/codebase-index/status` returns index stats
- `GET /addons/git-control/status` returns branch/staged info
- Knowledge browser shows codebase-index status card at top
- Workspace browser shows git-control status card at top
- Panels auto-refresh without page reload

### Owner

Team 3. Independent of T1 (panels inject into existing tabs, not the
Addons tab). Can merge before or after T2.

### Do Not Touch

`queen_tools.py`, `queen_runtime.py`, `formicos-app.ts` (Team 1 owns
nav), `store.ts` (Team 1 owns snapshot mapping), any `core/` or
`engine/` files.

---

## Side Task S2: Knowledge ROI Rule Fix

`_rule_knowledge_roi()` in `src/formicos/addons/proactive_intelligence/rules.py:691-727`
only checks `entries_extracted == 0` for successful colonies. The
`entries_accessed` field is computed on `ColonyOutcome`
(`projections.py:1057-1065`) but unused. Add a secondary insight: when
successful colonies access knowledge entries and produce good outcomes
(quality_score > 0.7), note the correlation. When colonies access zero
entries and have low quality, flag the pattern. ~15 lines added to the
existing function.

**File:** `src/formicos/addons/proactive_intelligence/rules.py` only.

**Test:** 1 new -- ROI rule fires when entries_accessed is zero across
multiple colonies.

**Owner:** Team 2 (touching proactive-intelligence addon config anyway).

---

## Side Task S4: CLAUDE.md Composite Weight Update

Update the retrieval formula in `CLAUDE.md` from the stale Wave 34 values:

```
# Old (stale):
0.38*semantic + 0.25*thompson + 0.15*freshness + 0.10*status + 0.07*thread + 0.05*cooccurrence

# New (Wave 59.5 actuals from knowledge_constants.py:33-41):
0.38*semantic + 0.25*thompson + 0.10*freshness + 0.10*status + 0.07*thread + 0.04*cooccurrence + 0.06*graph_proximity
```

**File:** `CLAUDE.md` only.

**Owner:** Whoever finishes first.

---

## Team Assignment

| Team | Tracks | Rationale |
|------|--------|-----------|
| Team 1 (Addons Tab) | T1, S3 | Addon tab is the anchor. S3 is a standalone bugfix merged first. |
| Team 2 (Config) | T2, S2, S4 | Config surface + proactive-intelligence config overlap. S2 and S4 are small. |
| Team 3 (Panels) | T3 | Panels + routes + status endpoints. Independent of T1. |

## Merge Order

```
S3 (merge Qdrant fix)          -- standalone bugfix, merge immediately
    |
T1 (addons tab + health)       -- anchor, merge first among tracks
    |
    +---> T2 (config surface)  -- depends on T1's component structure
    |
T3 (panels + routes)           -- independent, merge any time
    |
S2, S4                         -- independent, merge whenever
```

T3 is independent of T1 because panels inject into Knowledge and
Workspace tabs, not the Addons tab. The Addons tab showing panels inline
is additive after both T1 and T3 merge.

## What Wave 66 Does NOT Do

- No tab consolidation (Playbook and Models stay as-is)
- No knowledge hierarchy (parent_id, tree view) -- Wave 67
- No provenance chains -- Wave 67
- No graph proximity activation in standard retrieval -- Wave 67 (needs
  seed selection design for non-thread path)
- No new event types (stays at 69)
- No hot-reload for addons (restart required)
- No addon dependency graphs
- No addon marketplace or discovery
- No custom Lit components per addon (generic panel renderer only)
- No session continuity or doc ingestion
- No RL/self-evolution

## Acceptance Criteria

- Addons tab in nav shows installed addons with health status
- Addon detail view shows tools, handlers, triggers, config, and panels
- Config changes persist via WorkspaceConfigChanged events (replay-safe)
- Addon panels render in Knowledge and Workspace tabs
- Addon REST routes mountable from manifest declarations
- MemoryEntryMerged correctly cleans up source vectors from Qdrant
- CLAUDE.md composite weights match Wave 59.5 actuals
- Knowledge ROI rule uses entries_accessed signal
- 3650+ tests passing
- CI: ruff clean, pyright clean, imports clean

## Estimated Scope

~400 lines new frontend (addons-view.ts ~250, addon-panel.ts ~100,
store/types ~50). ~150 lines new backend (health monitoring, config
endpoints, route mounting, panel wiring). ~60 lines addon implementations
(status endpoints). ~50 lines side task fixes (S2, S3, S4). ~30 lines
manifest updates. 13 new tests.
