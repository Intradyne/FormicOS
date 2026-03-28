# Wave 72 Polish Reference

This note is the repo-truth reference for the next operator-surface polish pass.
It replaces earlier assumptions that treated several already-landed surfaces as
missing.

The core product judgment is:

- `Settings` should be a writable control surface, not a second diagnostics page.
- Model lifecycle and document ingestion are the two biggest missing operator
  flows.
- Addon reindexing needs a backend seam fix before any "easy docs ingest" UI
  will feel trustworthy.

## Repo-Truth Corrections

- Manual knowledge entry already exists.
  `frontend/src/components/knowledge-browser.ts` has a `+ Create Entry` flow and
  `POST /api/v1/workspaces/{workspace_id}/knowledge` exists in
  `src/formicos/surface/routes/api.py`.
- Model policy is already partially editable.
  `frontend/src/components/model-registry.ts` saves `max_output_tokens`,
  `time_multiplier`, and `tool_call_multiplier` through
  `PATCH /api/v1/models/{address}`.
- `Settings` already edits a narrow governance slice.
  `frontend/src/components/settings-view.ts` persists
  `routing.default_strategy`, `governance.max_rounds_per_colony`,
  `governance.default_budget_per_colony`, and
  `governance.convergence_threshold`.
- Generic addon config is still not surfaced cleanly in the main UI.
  There is an addon config route (`/api/v1/addons/{addon_name}/config`), but
  the only dedicated writable card in Settings today is `mcp-servers-card`.
- The docs-index trigger bug is real.
  `addons/docs-index/addon.yaml` still exposes a manual trigger wired to
  `indexer.py::incremental_reindex`, even though the runtime-context-safe seam
  is `search.py::handle_reindex`.
- Codebase-index has the same manual-trigger seam and should be fixed in the
  same pass.
  `addons/codebase-index/addon.yaml` also points manual trigger at
  `indexer.py::incremental_reindex`.

## Severity-Ordered Catalog

### 1. Settings is structurally wrong
Severity: High
Backend seam status: Mostly frontend restructure; a few missing write paths.

Current truth:
- `frontend/src/components/settings-view.ts` mixes writable controls with large
  read-only inventory blocks.
- It repeats information that already has dedicated surfaces:
  `Models`, `Addons`, protocol status, system overview.
- It still omits several operator-important controls.

Why this matters:
- The page feels busy without feeling powerful.
- The operator has to read a lot of status while only a small part is actually
  editable.

Recommendation:
- Make `Settings` explicitly writable-first.
- Move or collapse read-only inventory into dedicated tabs or an advanced
  diagnostics drawer.
- Keep Settings focused on controls the operator expects to change.

### 2. Budgeting belongs in Settings, but mostly is not there
Severity: High
Backend seam status: Partly shipped, partly missing.

Current truth:
- `Settings` edits only `governance.default_budget_per_colony`.
- A read-only budget surface already exists in
  `frontend/src/components/budget-panel.ts`.
- `GET /api/v1/workspaces/{workspace_id}/budget` exists.
- `GET /api/v1/workspaces/{workspace_id}/autonomy-status` exists.

Gap:
- There is no cohesive budgeting card in Settings for:
  - default per-colony budget
  - workspace/API spend cap
  - daily autonomy budget / remaining budget
  - maintenance/autonomous spend policy

Recommendation:
- Add a dedicated `Budgeting` section to Settings.
- Reuse existing budget/autonomy read APIs.
- Add missing write paths only where needed, instead of keeping budget controls
  split between governance, operations, and a read-only budget panel.

### 3. Model selection should hide models with no key by default
Severity: High
Backend seam status: Frontend bug / selection policy gap.

Current truth:
- Model entries already carry effective status:
  `available`, `loaded`, `no_key`, `unavailable`, `error`.
- `frontend/src/components/caste-editor.ts` currently builds selection options
  from the raw registry list and does not filter out `no_key` entries.

Recommendation:
- All operator-facing model selection controls should default to
  `available | loaded`.
- `no_key`, `unavailable`, and `error` models should remain visible in the
  `Models` admin view, but not appear in normal assignment pickers.
- If a "show unavailable" toggle exists, it should be explicit and off by
  default.

### 4. Model lifecycle is incomplete: add and hide are missing
Severity: High
Backend seam status: Needs new write seam.

Current truth:
- The UI can edit policy on existing models.
- There is no UI path to add a newly launched model.
- There is no operator-facing hide/unhide control for individual models.
- The existing `PATCH /api/v1/models/{address}` route does not cover registry
  creation or operator-level visibility.
- Type contract divergence: `docs/contracts/types.ts` defines ModelRecord
  status as `"available" | "unavailable" | "no_key" | "loaded"` (4 values),
  but Python core allows 5 (adds `"error"`). Frontend `CloudEndpoint` uses
  `"connected"` and `"cooldown"` instead of `"available"` / `"unavailable"`.
  This must be aligned before model filtering can be reliable.

Recommendation:
- Add a proper model-admin flow in the `Models` tab:
  - create a new registry entry
  - hide / unhide a model
  - optionally mark a model as deprecated
- Keep the `Models` tab as the full inventory/admin view.
- Settings should reference model defaults and selection policy, not duplicate
  the add/hide controls.

### 5. Document ingestion is the real knowledge-input gap
Severity: High
Backend seam status: Shipped but not surfaced as a top-level flow.

Current truth:
- Manual text entry exists in Knowledge (`+ Create Entry` in knowledge-browser).
- Workspace file upload exists in `colony-detail.ts` (`+ Add` button), but is
  buried in colony detail rather than presented as a clear "add documents to
  knowledge" action.
- There is no simple top-level operator flow for:
  1. upload documents
  2. index them
  3. verify they are searchable

Recommendation:
- Add an explicit document-ingest flow on the Knowledge side:
  - upload or choose workspace files
  - trigger docs-index reindex
  - show indexed file count / last run / errors
- Do not solve this with another free-form text entry form.

### 6. Addon manual reindex triggers are miswired
Severity: High
Backend seam status: Confirmed backend bug.

Current truth:
- `addons/docs-index/addon.yaml` and `addons/codebase-index/addon.yaml`
  expose manual triggers bound directly to `indexer.py::incremental_reindex`.
- The safe runtime-context-aware seam already exists in each addon's
  `search.py::handle_reindex`.
- This is why docs-index currently errors with missing `workspace_path` and
  `vector_port`.

Recommendation:
- Rewire both manifests to the `handle_reindex` wrapper.
- Treat this as a blocker for any user-facing ingest/reindex polish.

### 7. Generic addon configuration is still weak
Severity: Medium
Backend seam status: Read/write API exists; UI is incomplete.

Current truth:
- `GET/PUT /api/v1/addons/{addon_name}/config` exists.
- `frontend/src/components/addons-view.ts` mostly shows read-only detail plus
  manual trigger buttons.
- `MCP` is the special case with a dedicated settings card.

Recommendation:
- Surface generic addon config editing in the Addons view.
- Keep MCP's richer card if needed, but stop making it the only writable addon
  story.
- Improve trigger feedback so success, failure, and last-run state are obvious.

### 8. The top bar is overcrowded
Severity: Medium
Backend seam status: Frontend only.

Current truth:
- `frontend/src/components/formicos-app.ts` centers an 8-tab nav in the top
  bar.
- The primary workflow tabs are mixed with admin/deep-dive tabs.

Recommendation:
- Left-align the main workflow tabs.
- Treat `Queen`, `Knowledge`, `Workspace`, and `Operations` as the primary
  destinations.
- Move `Addons`, `Playbook`, `Models`, and `Settings` into a secondary cluster,
  overflow menu, or utility rail if needed.

### 9. The protocol badges blink but do not do anything
Severity: Medium
Backend seam status: Frontend only.

Current truth:
- The `MCP`, `AG-UI`, and `A2A` badges render as glowing status chips in the
  top bar.
- They look interactive, but they are not wired to any action.

Recommendation:
- Either make them real controls that open protocol details / diagnostics, or
  demote them to passive status text without the button-like treatment.
- Do not keep blinking decorative elements that imply click behavior.

## Recommended Settings Shape

Settings should become the place for writable operator controls:

1. Workspace
- name / identity
- taxonomy tags
- project-level operator preferences

2. Budgeting
- default per-colony budget
- workspace/API budget cap
- autonomy daily budget
- maintenance spend policy

3. Governance
- default strategy
- max rounds
- convergence threshold
- autonomy level and related policy

4. Models (defaults and selection policy only)
- default model assignments per caste
- selection filter policy (hide unavailable by default, toggle)
- link to Models tab for full admin (add, hide/unhide, deprecate)

5. Integrations
- MCP server management
- addon config and reindex controls

Diagnostics should move out of the main settings path or collapse by default:

- system overview
- protocol inventory
- addon summary inventory
- full model inventory table
- retrieval diagnostics

## Recommended Sequencing

### Phase 1: unblock broken seams
- Fix docs-index and codebase-index manual trigger wiring.
- Filter `no_key` / unavailable models out of selection controls.
- Remove or wire up the inert protocol badges.

### Phase 2: make Settings useful
- Restructure Settings around writable sections.
- Add a real Budgeting card.
- Add model hide/add controls.

### Phase 3: improve knowledge/addon usability
- Add an explicit document-ingest flow.
- Add generic addon config editing and better reindex feedback.
- Clean up the top navigation once the Settings/Addons/Models boundaries are
  clearer.

## Short Version

The current problem is not that the product lacks settings surfaces.
It is that the wrong things are in `Settings`, and several important operator
workflows still live nowhere obvious:

- model lifecycle
- budgeting
- easy document ingestion
- addon configuration
- clean navigation

That is the right polish focus.
