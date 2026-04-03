# Wave 87 Team B Prompt

## Mission

Expand the addon panel surface just enough for a daily-use dashboard.

This is a declarative host-surface track, not a dynamic component
runtime. The renderer owns layout and paint. Addons return data shapes.

## Owned Files

- `frontend/src/components/addon-panel.ts`
- `frontend/src/components/workspace-browser.ts`
- `frontend/src/components/knowledge-browser.ts`
- `frontend/src/components/formicos-app.ts`
- `frontend/src/types.ts`
- `docs/contracts/types.ts`

## Do Not Touch

- backend addon files owned by Team A
- `src/formicos/surface/view_state.py`
- `src/formicos/surface/queen_runtime.py`
- service-colony or MCP gateway work

## Repo Truth To Read First

1. `addon-panel.ts`
   Current renderer supports only:
   - `status_card`
   - `table`
   - `log`

   It also hardcodes a 60-second polling interval.

2. `workspace-browser.ts` and `knowledge-browser.ts`
   Panels are mounted from a static addon path and filtered by `target`.

3. `formicos-app.ts`, `frontend/src/types.ts`, `docs/contracts/types.ts`
   Addon panel summary currently exposes only:
   - `target`
   - `displayType`
   - `path`
   - `addonName`

## What To Build

### 1. Expand the declarative vocabulary

Add lightweight support for a richer set of panel shapes, such as:

- `kpi_card`
- simple sparkline / bar-strip trend
- grouped or status-aware table

Use inline SVG for simple trend rendering.

Do not add a chart library for this wave.

### 2. Consume `refresh_interval_s`

Panels should accept and honor a per-panel refresh interval from the
snapshot path instead of always polling at 60 seconds.

Use a sensible default when the field is absent so existing addons keep
working.

### 3. Append workspace context to panel fetch URLs

Workspace-mounted addon panels should include at minimum:

- `?workspace_id=<active workspace>`

in their fetch URL.

This should work for current workspace-mounted panels as well, not just
the new system-health addon.

### 4. Keep the renderer declarative

Do not introduce:

- arbitrary generated React execution
- iframe component sandboxes
- remote code loading

This wave proves the host surface with declarative shapes only.

## Constraints

- Keep existing panel types backward-compatible.
- No new frontend state subsystem.
- No builder-mode redesign here.
- No styling bloat; prioritize legibility and low risk.

## Validation

- `cd frontend; npm run build`

If you add or update frontend/unit contract tests, keep them targeted.

## Overlap Note

- Team A defines the backend field and addon payloads.
- Team C exposes the panel refresh field through snapshot state.
- You own the frontend type mirrors and component consumption.
