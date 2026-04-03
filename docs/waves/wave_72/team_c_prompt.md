# Wave 72 - Team C: Workflow Learning, Product Polish, And Docs

Theme: learn from successful work, codify operator preferences, and fix the
product surfaces that still feel cluttered or underpowered.

## Read First

- `docs/waves/wave_72/wave_72_plan.md`
- `docs/waves/wave_72/design_note.md`
- `docs/waves/wave_72/wave_72_polish_reference.md`
- `CLAUDE.md`

## Repo Truth You Must Start From

- `settings-view.ts` is structurally inverted: mostly read-only inventory, very
  little real control.
- `config-overrides` is not a trustworthy generic settings-persistence seam for
  product polish. Do not build fake saves on top of it.
- model policy is only partially editable today
  (`PATCH /api/v1/models/{address}`), and model add/hide are still missing.
- selection surfaces still expose models that are `no_key` / unavailable unless
  the frontend filters them out.
- the top nav is overcrowded and centered.
- the protocol badges look interactive but are not.
- Team B owns `app.py` and calls your workflow-learning helpers from the sweep.

## Key Seams To Read Before Coding

- `src/formicos/surface/workflow_learning.py` - you will create this
- `src/formicos/surface/operational_state.py`
  Read `append_procedure_rule()`, `load_procedures()`, and `save_procedures()`.
- `src/formicos/surface/action_queue.py`
  Read queue creation and status update helpers.
- `src/formicos/surface/routes/api.py`
  Read:
  - `approve_action()` / `reject_action()`
  - `update_model_policy()`
  - `get_autonomy_status()`
  - addon config routes
- `src/formicos/surface/model_registry_view.py`
- `src/formicos/core/types.py`
  Read `ModelRecord` and `MaintenancePolicy`.
- `src/formicos/surface/mcp_server.py`
  Read `set_maintenance_policy()` / `get_maintenance_policy()` so your HTTP
  route, if added, mirrors the existing contract instead of inventing a new one.
- `frontend/src/components/operations-inbox.ts`
- `frontend/src/components/settings-view.ts`
- `frontend/src/components/model-registry.ts`
- `frontend/src/components/caste-editor.ts`
- `frontend/src/components/formicos-app.ts`

## Your Files

- `src/formicos/surface/workflow_learning.py` - new
- `src/formicos/surface/operational_state.py` - additive helper only
- `src/formicos/surface/routes/api.py` - additive model-admin /
  maintenance-policy routes if needed
- `src/formicos/surface/model_registry_view.py` - additive hidden-field support
- `src/formicos/core/types.py` - additive model field only if needed
- `frontend/src/components/operations-inbox.ts` - new action kinds
- `frontend/src/components/settings-view.ts` - writable-first restructure
- `frontend/src/components/model-registry.ts` - model admin
- `frontend/src/components/caste-editor.ts` - model filtering
- `frontend/src/components/formicos-app.ts` - nav cleanup + badge fix
- `CLAUDE.md`
- `docs/AUTONOMOUS_OPERATIONS.md` - new
- `tests/unit/surface/test_workflow_learning.py` - new

## Do Not Touch

- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/queen_runtime.py`
- `src/formicos/surface/app.py`
- `frontend/src/components/knowledge-browser.ts`

## Overlap Rules

- Team A owns active Knowledge-tab ingest/reindex work.
- Team B owns the scheduler in `app.py`.
- You provide pure learning helpers and UI/admin surfaces.

## Track 8: Workflow Pattern Recognition

Create `src/formicos/surface/workflow_learning.py` with a deterministic pattern
extractor that proposes `kind="workflow_template"` actions.

Requirements:

- derive patterns from successful outcome history
- keep matching deterministic
- dedupe against existing learned templates and pending workflow-template
  actions
- queue proposals through the existing action queue only

Keep the pattern heuristic simple:

- similar caste set
- same strategy
- clear repeated task-shape overlap
- repeated success across multiple threads

When approved, save a learned template using the existing template manager.

Important:

- approval should extend the existing approve-action flow, not create a second
  template-approval mechanism

## Track 9: Procedure Suggestions

Add a second detector in `workflow_learning.py` that proposes
`kind="procedure_suggestion"` actions from repeated operator behavior.

Use conservative heuristics only. Good starting signals:

- repeated rejection of autonomous work on a shared keyword/domain
- repeated "review after coding" patterns
- repeated testing-after-change behavior

When approved, append the rule through `append_procedure_rule()`.

Keep the logic explainable. The inbox card should be able to say why the system
noticed the pattern.

## Track 10: Product Surface Polish

### A. Make Settings writable-first

Restructure `frontend/src/components/settings-view.ts` around real operator
controls:

1. Workspace
2. Budgeting
3. Governance
4. Model defaults / selection policy
5. Integrations

Collapse or move read-only diagnostics:

- system overview
- protocol inventory
- addon summary inventory
- full model inventory table
- retrieval diagnostics

Do not leave Settings as a second dashboard.

### B. Use a real persistence seam for budgeting and autonomy

If there is no clean HTTP route yet, add a small
`GET/PUT /api/v1/workspaces/{workspace_id}/maintenance-policy` pair that mirrors
the JSON contract already used by the MCP maintenance-policy helpers.

Use that route for:

- autonomy level
- daily maintenance budget
- max maintenance colonies
- auto-action policy if surfaced

Do not fake these saves through `config-overrides`.

For workspace taxonomy tags:

- if there is no clean dedicated write seam, keep them read-only this wave
- do not invent a fake save path just to make the card editable

### C. Add model admin, not just model filtering

This wave should close the biggest model-lifecycle gaps called out in the
polish reference.

Add a bounded model-admin surface in `model-registry.ts`:

- `Add Model` flow
- `Hide / Unhide` model
- `Show unavailable` toggle
- existing policy edit remains

Recommended backend shape:

- extend `ModelRecord` with additive `hidden: bool = False` — this is an
  additive field with a default; it does not affect the event union, replay
  safety, or existing serialization. No ADR required.
- surface `hidden` through `model_registry_view.py`
- extend `PATCH /api/v1/models/{address}` to allow `hidden`
- add `POST /api/v1/models` to append a new registry entry and persist it

Selection rules:

- default selectors must hide models that are:
  - `hidden`
  - `no_key`
  - `unavailable`
  - `error`
- admin views may still show them

`caste-editor.ts` must honor that default filtering.

### D. Clean up the top nav

In `formicos-app.ts`:

- left-align the main workflow tabs
- split primary vs secondary destinations
- keep `Queen`, `Knowledge`, `Workspace`, and `Operations` visually primary

This should feel like a product nav, not a debug toolbar.

### E. Fix the protocol badges

Either:

- make them real controls that navigate to the relevant Integrations /
  protocol details surface

or:

- visually demote them so they no longer look clickable

Do not leave animated pseudo-buttons that do nothing.

## Track 11: Documentation Refresh

### CLAUDE.md

Refresh it to match the post-Wave-72 reality:

- operational layer / action queue / procedures / journal
- workflow learning additions
- product-surface truth
- current tool count and main seams

### docs/AUTONOMOUS_OPERATIONS.md

Write the operator guide for:

- autonomy levels
- budgeting and maintenance policy
- operations inbox
- continuation behavior
- knowledge review
- workflow-template proposals
- procedure suggestions
- journal / procedures

Write for someone operating the system, not for someone reading ADRs.

## Acceptance Gates

- workflow-template proposals appear through the action queue
- approved workflow-template actions create learned templates
- procedure suggestions append to operating procedures on approval
- Settings is clearly writable-first
- budget/autonomy persistence uses a real route, not fake config-overrides saves
- the Models tab can add and hide models
- default model selectors hide hidden / no-key / unavailable models
- the nav is visually simplified
- the protocol badges are either functional or clearly passive
- `CLAUDE.md` and `docs/AUTONOMOUS_OPERATIONS.md` reflect the shipped system

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
npm run build && npm run lint
```
