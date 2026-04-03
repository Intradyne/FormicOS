# Wave 87 Team A Prompt

## Mission

Build panel zero as a real addon and land the minimum backend plumbing it
needs.

This track proves that addons are the durable host shell for FormicOS
capabilities. The addon should read live FormicOS state through
`runtime_context` and return declarative panel payloads.

## Owned Files

- `addons/system-health/addon.yaml`
- `src/formicos/addons/system_health/__init__.py`
- `src/formicos/addons/system_health/status.py` or equivalent handler module
- `src/formicos/surface/app.py`
- `src/formicos/surface/addon_loader.py`
- relevant tests under `tests/unit/addons/` and `tests/unit/surface/`

## Do Not Touch

- `src/formicos/surface/view_state.py`
- `src/formicos/surface/queen_runtime.py`
- frontend component files
- playbook provenance or external-data integration

## Repo Truth To Read First

1. `app.py`
   Addon routes are mounted as GET-only catch-all routes and currently
   call handlers with empty `inputs`, empty `workspace_id`, and empty
   `thread_id`.

2. `addon_loader.py`
   Panel registration currently preserves only:
   - `target`
   - `display_type`
   - `path`
   - `addon_name`

3. Existing addon packages:
   - `addons/codebase-index/`
   - `addons/git-control/`
   - `src/formicos/addons/codebase_index/status.py`

4. `app.py` addon runtime context
   The addon already receives:
   - `runtime`
   - `projections`
   - `settings`
   - `data_dir`
   - `mcp_bridge`

## What To Build

### 1. Create the `system-health` addon

Add a new addon package under:

- `addons/system-health/`
- `src/formicos/addons/system_health/`

Keep it simple:

- workspace-mounted panel(s)
- route-backed
- no tools
- no service colony dependency

### 2. Read local state directly, not via self-HTTP

The route handler should inspect `runtime_context` / projections directly.

Do not make same-process HTTP calls back into `/api/v1/...` routes from
the addon handler.

The goal is to reuse existing truth, not add latency and duplicate
transport.

### 3. Return declarative panel payloads

Good payloads for panel zero:

- overview KPI payload
- trend payload with recent quality values
- compact tables for pattern/addon/index status

Useful metrics:

- recent colony count and success/failure split
- average quality
- memory entry count
- approved vs candidate plan patterns
- codebase index health
- addon health summary

### 4. Pass query params through addon routes

In `app.py`, pass `request.query_params` to the addon handler as the
`inputs` dict.

This is the required seam for workspace-scoped panels.

### 5. Preserve `refresh_interval_s` during addon registration

Add an additive panel field:

- `refresh_interval_s`

Store it in addon registration so the snapshot/frontend path can carry
it later.

You do not own `view_state.py`; Team C will expose the registered field
to snapshots. Keep the field naming simple and stable.

## Constraints

- Do not add new public API endpoints for panel zero.
- Do not build service-colony plumbing here.
- Do not invent arbitrary runtime UI execution.
- Do not touch snapshot capping or Queen routing.

## Validation

- `python -m pytest tests/unit/addons/test_addon_panels_routes.py -q`
- `python -m pytest tests/unit/surface/test_addon_loader.py -q`
- `python -m pytest tests/unit/surface/test_app.py -q`

Add targeted tests for:

- query-param passthrough to addon handlers
- `refresh_interval_s` preserved in addon registration
- system-health addon route payload shape

## Overlap Note

- Team B will consume the new panel field in frontend types/components.
- Team C will expose the new field through `view_state.py`.
- Do not reopen those files; coordinate on the field name only.
