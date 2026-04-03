# Wave 89 Plan: Colony-Authored Living Capabilities

## Status

Dispatch-ready. Grounded in source truth as of 2026-04-02.

## Summary

Wave 88 proved that FormicOS can host useful capabilities inside its own
surface.

Wave 89 should prove the next, narrower claim:

**Can FormicOS create and mount one brand-new internal hosted capability
from operator intent, without restart or manual wiring?**

This wave is intentionally about **generation + deployment**, not full
hosted-capability lifecycle. The proof should use internal data only so
it isolates the new risk:

- colony-authored addon package generation
- strict deployment validation
- runtime loading of a brand-new addon
- visible hosted panel without restart

Three active tracks:

- Track A: strict runtime addon loading plus `deploy_addon`
- Track B: Queen `host` doctrine integration and colony authoring path
- Track C: lightweight hosted-capability observation plus any minimal
  panel vocabulary expansion needed by the first generated dashboard

Deferred:

- existing-addon hot-reload / replace
- colony-modified existing addon reload without restart
- generated MCP-backed addons
- service-colony-backed persistence
- autonomous repair
- workstream lifecycle architecture beyond Wave 87's snapshot cap

## One Falsifiable Goal

After this wave ships, the operator should be able to tell the Queen:

`Build me a dashboard showing colony quality trends and auto-learned pattern count.`

And FormicOS should:

1. classify that request as `host`
2. spawn a constrained colony that writes a valid addon package into the
   project-bound repo
3. validate and load that new addon at runtime with `deploy_addon`
4. show the new panel in the workspace browser without restart

If the operator can see that new dashboard alongside:

- `System Health`
- `Repo Activity`

then FormicOS has crossed from "hosts hand-built capabilities" to
"creates hosted capabilities from intent."

## Verified Repo Truth

### 1. `host` is a real planning output, but not yet a real execution path

`planning_policy.py` already classifies the durability ladder:

- `reply`
- `inspect`
- `edit`
- `execute`
- `host`
- `operate`

But `queen_runtime.py` currently only logs `capability_mode`; it does
not yet have a dedicated `host` execution path. Host requests still fall
through the ordinary colony-routing behavior unless this wave adds the
specialized prompt and deployment path.

### 2. Colonies can already write into the live repo when project-bound

Colony file tools resolve to the workspace runtime root:

- bound project root when `PROJECT_DIR` is available
- workspace library root otherwise

So colony-authored addon files can land in:

- `addons/<name>/addon.yaml`
- `src/formicos/addons/<package>/...`

when the workspace is project-bound. This is the substrate Wave 89
needs.

### 3. The minimum useful addon package is small, but import resolution is strict

Addon loading already expects:

- `addons/<name>/addon.yaml`
- importable Python modules under `formicos.addons.<package>`
- handler references in `module.py::function_name` format

`register_addon()` is forgiving at startup: malformed pieces can skip
registration instead of crashing the app. That is good for boot
resilience, but wrong for deployment. Wave 89 needs a **strict
validation + load helper** before runtime mounting.

### 4. New-addon runtime loading is much closer than full hot-reload

Startup addon wiring in `app.py` already does most of the work:

- discovers manifests
- constructs shared runtime context
- creates per-addon governed gateway context when needed
- calls `register_addon()`
- appends registrations and tool specs
- emits `AddonLoaded`
- registers triggers

The current system has **no deregistration / replace path**. That means:

- loading a brand-new addon is plausible in this wave
- replacing an already-loaded addon is a different problem

Wave 89 should therefore support **new addons only**.

### 5. The addon HTTP route is already catch-all and resolves registrations at request time

`app.py` mounts:

- `GET /addons/{addon_name}/{path}`

and resolves handlers from `app.state.addon_registrations` at request
time.

That means runtime loading of a brand-new addon does **not** require
route-table surgery. Once the new registration is appended to
`app.state.addon_registrations`, the catch-all route can serve it.

### 6. Addon triggers and summaries already have live seams

FormicOS already has:

- manifest triggers
- `TriggerDispatcher.register_triggers()`
- addon summaries in `view_state.py`
- addon APIs and Queen tools for listing / firing addon triggers

That means a lightweight `check_hosted_capabilities` tool can start from
current registration and summary truth instead of inventing a background
probing subsystem.

### 7. The current panel vocabulary is probably sufficient for the first proof

`addon-panel.ts` already supports:

- `status_card`
- `table`
- `log`
- `kpi_card`
- inline sparkline trends via `trend`

That is likely enough for the first generated internal dashboard. Wave
89 should expand the panel vocabulary only if the concrete proof case is
actually blocked.

## Track A: Strict Runtime Addon Loading And `deploy_addon`

## Goal

Create the infrastructure that can safely load one brand-new addon at
runtime after a colony writes it into the project-bound repo.

This is the core deployment seam for Wave 89.

## Scope

### 1. Add a constrained addon template skeleton

Create the template the `host` colony should fill in.

Keep it intentionally tight:

- one addon manifest
- one importable handler module
- one workspace panel
- one route

The colony should write data logic and declarative panel payloads, not
invent addon structure.

The template context should include:

- addon manifest skeleton
- handler boilerplate
- panel vocabulary reference
- runtime_context fields that are safe/expected
- one truthful working example such as the system-health handler

### 2. Build `load_new_addon()` with strict validation

Add a helper that loads a **new** addon into the running app.

It should validate before registration:

- manifest file exists
- manifest parses
- addon name is not already loaded
- handler module imports
- referenced handler functions resolve
- declared route/panel paths do not collide with an existing addon

On success, it should update the live addon state surfaces that already
exist in the startup path:

- `app.state.addon_manifests`
- `app.state.addon_registrations`
- `app.state.addon_tool_specs`
- `runtime.addon_registrations`
- `ws_manager._addon_registrations`
- Queen dispatcher addon spec / manifest surfaces
- trigger dispatcher registrations

Do not attempt replacement or deregistration in this wave.

### 3. Add `deploy_addon` as a Queen tool

The Queen needs a first-class tool to:

- validate the generated addon package
- load it into the running app
- return structured success or failure

Good failure modes:

- manifest parse error
- missing file
- handler import error
- duplicate addon name
- route/panel collision

The Queen should be able to relay those failures directly or use them to
inform a repair attempt later.

### 4. Reuse, do not duplicate, the startup registration truth

The startup path in `app.py` already knows how to build addon runtime
context and registration state.

Wave 89 should extract or centralize that truth instead of copying it
into a second, divergent runtime-loader implementation.

## Owned Files

- `src/formicos/surface/addon_loader.py`
- `src/formicos/surface/app.py` if startup addon wiring must be
  extracted into a reusable helper or stored on app state
- `src/formicos/surface/queen_tools.py`
- one small new helper/template module under `src/formicos/surface/` if
  needed
- targeted tests under `tests/unit/surface/` and `tests/unit/addons/`

## Track B: Queen `host` Doctrine Integration

## Goal

Make `capability_mode == "host"` do something materially different from
ordinary execute-mode colony work.

This track turns the Wave 87 doctrine into a real generation path.

## Scope

### 1. Add a host-specific colony prompt path

When the planning decision classifies a request as `host`, the Queen
should inject host-specific context before spawning work:

- addon template skeleton
- handler boilerplate expectations
- declarative panel vocabulary
- safe runtime_context fields
- output file locations inside the project-bound repo
- instruction to finish by calling `deploy_addon`

The colony should not invent addon structure. It should fill in the
template.

### 2. Keep the first generated proof internal-data only

The first hosted capability should use internal FormicOS data such as:

- colony outcomes
- quality trends
- plan pattern counts
- learning-summary-style state

Do not make the first generated addon depend on MCP or remote provider
availability.

Wave 88 already proved external hosting. Wave 89 should isolate
generation + deployment.

### 3. Bias the first host path toward the smallest viable colony

The first `host` proof should prefer a single coder colony unless the
task clearly needs decomposition.

Do not widen into colony-authored lifecycle management or broad addon
marketplace behavior in this wave.

### 4. Keep modification of existing addons explicitly out of the proof

If you touch the follow-up modification path at all, keep it clearly
non-gating and restart-required.

The real Wave 89 proof is:

- new addon generated
- new addon deployed
- panel appears without restart

## Owned Files

- `src/formicos/surface/queen_runtime.py`
- `src/formicos/surface/planning_policy.py` only if host-mode
  calibration or tests need adjustment
- targeted tests under `tests/unit/surface/`

## Track C: Hosted Capability Observation And Minimal Surface Support

## Goal

Give the Queen a lightweight way to answer:

`What hosted capabilities are currently mounted and how are they doing?`

This is observation, not autonomous repair.

## Scope

### 1. Add `check_hosted_capabilities`

Build a lightweight Queen tool that reports current hosted capability
state from existing truth surfaces such as:

- addon registrations
- addon summaries / view-state fields
- registration health/error counters
- trigger metadata
- panel config such as target/path/refresh interval

This tool should answer the current snapshot, not introduce a polling
daemon or new monitoring subsystem.

### 2. Surface enough panel information for operator trust

The result should make it easy to see:

- which panels are mounted
- which addon owns them
- refresh interval
- registration status / disabled state
- last known error
- available trigger or refresh paths when present

### 3. Only expand panel vocabulary if the first generated dashboard is blocked

The current `kpi_card` + table + sparkline surface may already be
enough.

Only add new declarative shapes if the concrete internal quality-trends
dashboard genuinely needs them.

## Owned Files

- one new helper module under `src/formicos/surface/` if needed for
  hosted-capability status assembly
- `src/formicos/surface/queen_tools.py` for `check_hosted_capabilities`
- `frontend/src/components/addon-panel.ts` only if the first generated
  dashboard is blocked by missing declarative rendering
- targeted tests under `tests/unit/surface/` and frontend-adjacent tests
  if required

## Merge Order

Recommended order:

1. Track A first, because runtime deployment infrastructure must exist
   before the Queen can use it.
2. Tracks B and C next.

Single-owner and reread notes:

- Track A owns the deployment infrastructure and the primary runtime
  addon-loading seam.
- `queen_tools.py` is the one shared seam in this packet.
  Track C should reread Track A's landed changes before finalizing
  `check_hosted_capabilities`.
- Track B should not invent its own deployment path. It must consume the
  `deploy_addon` path from Track A.

## What Wave 89 Does Not Do

- no existing-addon hot-reload / replace
- no generated MCP-backed addons as the first proof
- no service-colony-backed persistence
- no autonomous repair
- no full workstream lifecycle layer
- no promise that operator-requested addon modifications update live
  without restart

## Success Criteria

Wave 89 is successful if:

1. A `host` request can trigger a constrained colony that writes a new
   addon package into the project-bound repo.
2. `deploy_addon` validates and loads that addon without restart.
3. The new panel appears in the workspace browser alongside the existing
   hosted panels.
4. The first generated addon uses real internal FormicOS data and
   renders through the declarative panel surface.
5. Deployment failures return structured errors instead of partial or
   silent registration.
6. `check_hosted_capabilities` can report the currently mounted hosted
   capability set from live registration truth.

## Clean-Room Acceptance

After merge, run a clean-state or freshly restarted acceptance pass that
proves:

1. The Queen classifies the example request as `host`.
2. A colony writes the addon package into the live project tree.
3. `deploy_addon` loads it without app restart.
4. The new panel is visible in the workspace browser.
5. The panel renders truthful internal data.
6. `check_hosted_capabilities` reports the mounted panel set and current
   health snapshot.
7. Existing addons (`System Health`, `Repo Activity`) still function.

## Post-Wave Decision Gate

After Wave 89:

- If colony-authored internal addons deploy cleanly and feel useful,
  proceed to generated addon modification and then generated external
  data integrations.
- If deployment works but generated addons are unreliable, tighten the
  template and validation seam before widening scope.
- Do not jump to existing-addon hot-reload until new-addon generation
  from intent feels dependable.
