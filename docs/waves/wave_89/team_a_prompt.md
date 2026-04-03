# Wave 89 Team A Prompt

## Mission

Build the strict deployment seam that makes colony-authored addon
generation mountable at runtime.

This track is not about full addon lifecycle. It is about:

- constrained addon template truth
- strict validation
- new-addon runtime loading
- a Queen tool that deploys a brand-new addon safely

## Owned Files

- `src/formicos/surface/addon_loader.py`
- `src/formicos/surface/app.py` if startup addon wiring must be
  extracted into a reusable helper or stored on app state
- `src/formicos/surface/queen_tools.py`
- one small new helper/template module under `src/formicos/surface/` if
  needed
- targeted tests under `tests/unit/surface/` and `tests/unit/addons/`

## Do Not Touch

- `src/formicos/surface/queen_runtime.py`
- `src/formicos/surface/planning_policy.py`
- frontend files unless the deployment path is impossible without a tiny
  contract fix
- service-colony persistence
- existing-addon replace / deregistration work
- generated MCP-backed addon work

## Repo Truth To Read First

1. `src/formicos/surface/app.py`
   Startup addon loading already:
   - discovers manifests
   - builds base runtime context
   - creates per-addon governed MCP context when needed
   - calls `register_addon()`
   - appends registrations / tool specs
   - registers triggers

   Reuse this truth. Do not fork it.

2. `src/formicos/surface/addon_loader.py`
   Addon loading already has:
   - manifest schema
   - import-based handler resolution
   - forgiving registration

   For Wave 89 deployment, you need a stricter wrapper.

3. `src/formicos/surface/app.py` catch-all addon route
   The route resolves from `app.state.addon_registrations` at request
   time, which means a brand-new addon can become routable by updating
   registrations rather than editing the route table.

4. Wave 89 scope
   New addons only. No replace path. No hot-reload of existing addons.

## What To Build

### 1. Add a constrained addon template skeleton

Provide the template truth that host-mode colonies should fill in.

Keep it intentionally narrow:

- `addons/<name>/addon.yaml`
- `src/formicos/addons/<package>/__init__.py`
- one handler module with one async dashboard function

The template should constrain structure so the colony is solving:

- data access
- declarative panel payloads

not addon packaging.

### 2. Build `load_new_addon()` with strict validation

Add a helper that loads a **brand-new** addon into the running app.

It should fail before registration when:

- manifest parse fails
- addon name already exists
- handler module import fails
- handler reference cannot resolve
- panel/route path conflicts with an existing addon

Do not allow partial runtime registration on failure.

### 3. Add `deploy_addon` as a Queen tool

The Queen needs a first-class deployment tool that:

- validates the generated addon package
- loads it into the running app
- returns structured success or structured failure

Keep the failure output good enough for a Queen follow-up or operator
message.

### 4. Reuse startup addon registration truth

You will probably need to extract or centralize some of the startup path
instead of reimplementing it.

If you must add app-state helpers, keep them small and truthful.

## Constraints

- New addons only.
- No replace / deregistration path.
- No service-colony persistence.
- No generated external/MCP addon proof in this track.
- No generic plugin marketplace work.

## Validation

- targeted tests for:
  - valid new addon loads at runtime
  - duplicate addon name fails cleanly
  - handler import error fails cleanly
  - route/panel collision fails cleanly
  - deployed addon appears in the live addon registration surfaces

If you need a minimal deploy-path smoke, keep it bounded to a tiny
internal test addon.

## Overlap Note

- Team B will consume `deploy_addon` and the template truth.
- Team C will touch `queen_tools.py` later for observation; keep your
  changes localized and readable.
- Do not require Team B to invent or duplicate deployment logic.
