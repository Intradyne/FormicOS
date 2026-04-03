# Wave 81 Team A Prompt

## Mission

Make FormicOS bind to a real project root without destroying the
existing workspace-library surface.

This is not a "replace `/files`" task. It is a "separate project truth
from library truth" task.

## Owned Files

- `docker-compose.yml`
- `.env.example`
- `src/formicos/surface/workspace_roots.py` (new)
- `src/formicos/surface/app.py`
- `src/formicos/surface/routes/colony_io.py`
- `src/formicos/surface/routes/api.py`
- `src/formicos/engine/runner.py`
- `src/formicos/surface/colony_manager.py`
- `src/formicos/surface/planning_brief.py`
- `tests/unit/surface/test_workspace_roots.py` (new)
- `tests/unit/surface/test_runtime.py`
- `tests/unit/engine/test_runner.py`
- `tests/unit/surface/test_planning_brief.py`

## Do Not Touch

- `src/formicos/surface/queen_tools.py`
- `src/formicos/surface/queen_runtime.py`
- `src/formicos/surface/runtime.py`
- `src/formicos/addons/codebase_index/status.py`
- frontend components

Track B owns `queen_tools.py` and the parallel-plan runtime truth fix.
Track D owns the frontend.

## Repo Truth To Read First

1. `src/formicos/surface/app.py`
   Addon runtime context already exposes `workspace_root_fn`, but it is
   hard-coded to `data/workspaces/{id}/files`.

2. `src/formicos/surface/routes/colony_io.py`
   `/api/v1/workspaces/{id}/files` is today the workspace-library
   surface used for uploads/shared files. Do not silently redefine it as
   the bound project tree.

3. `frontend/src/components/workspace-browser.ts`
   The UI already consumes `/files` as a library/browser surface and
   separately consumes AI filesystem data.

4. `src/formicos/engine/runner.py`
   Colony file tools still resolve against the workspace files
   directory.

5. `src/formicos/surface/colony_manager.py`
   Colony working directory resolution is one of the real execution
   seams.

6. `src/formicos/surface/planning_brief.py`
   Structural coupling only becomes useful when it reads the real
   project root.

## What To Build

### 1. Shared workspace-root helper

Create `src/formicos/surface/workspace_roots.py` with a tiny API that
separates:

- workspace library root
- bound project root
- runtime execution root
- binding-status payload

Recommended public helpers:

```python
def workspace_library_root(settings, workspace_id: str) -> Path: ...
def workspace_project_root(settings, workspace_id: str) -> Path | None: ...
def workspace_runtime_root(settings, workspace_id: str) -> Path: ...
def workspace_binding_status(settings, workspace_id: str) -> dict[str, Any]: ...
```

### 2. `PROJECT_DIR` bootstrap

Update `docker-compose.yml` and `.env.example` so the main container can
mount:

- formicos data at `/data`
- real project at `/project`

The runtime helper should treat `/project` as the project root only when
the mount exists and is a directory.

### 3. Runtime root adoption

Use the helper in:

- addon runtime context in `app.py`
- colony working directory resolution
- runner workspace reads/writes
- planning-brief structural analysis

### 4. Separate project-file routes

Keep `/files` as workspace-library truth.

Add separate project-file routes so the frontend can browse bound real
code without overloading the library route.

Recommended routes:

- `GET /api/v1/workspaces/{id}/project-files`
- `GET /api/v1/workspaces/{id}/project-files/{path}`
- `GET /api/v1/workspaces/{id}/project-binding`

These routes should degrade cleanly when no project is bound.

## Important Constraints

- Do not add a persisted per-workspace binding model in this wave
- Do not redefine `/files` to mean project files
- Do not invent frontend truth in this track
- Do not touch `queen_tools.py`; Track B will adopt your helper there

## Validation

Add focused tests that prove:

1. the helper returns project root when mounted and library root
   otherwise
2. project-file routes do not break the existing workspace-library
   routes
3. runner / planning-brief consumers use the runtime root helper
4. addon `workspace_root_fn` now points at the runtime root

Run:

- `python -m pytest tests/unit/surface/test_workspace_roots.py -q`
- `python -m pytest tests/unit/surface/test_runtime.py -q`
- `python -m pytest tests/unit/engine/test_runner.py -q`
- `python -m pytest tests/unit/surface/test_planning_brief.py -q`

## Overlap Note

You are not alone in the codebase. Track B will reread and consume your
helper from `queen_tools.py`. Keep the helper API small and stable. Do
not rework unrelated routes while you are in `colony_io.py` or `api.py`.
