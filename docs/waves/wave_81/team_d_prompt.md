# Wave 81 Team D Prompt

## Mission

Make workspace truth and plan truth visible to the operator.

This is not polish. This is where the operator should be able to see the
same truth that backend engineers were reconstructing from logs.

## Owned Files

- `frontend/src/components/workspace-browser.ts`
- `frontend/src/components/settings-view.ts`
- `frontend/src/components/queen-overview.ts`
- `frontend/src/components/fc-preview-card.ts`
- `frontend/src/components/fc-result-card.ts`
- `frontend/src/components/formicos-app.ts`
- `frontend/src/types.ts`

## Do Not Touch

- backend project-binding code
- backend parallel-plan runtime code
- codebase-index addon backend files

If a backend field is missing, note it for the integrator instead of
inventing frontend-only truth.

## Repo Truth To Read First

1. `frontend/src/components/workspace-browser.ts`
   Already shows workspace-library files, AI filesystem sections, and
   upload/ingest controls. It is the right place to separate Project
   Files, Workspace Library, Working Memory, and Artifacts.

2. `frontend/src/components/settings-view.ts`
   Already owns writable workspace configuration UI and is the right
   place for bound-path and index-status truth.

3. `frontend/src/components/queen-overview.ts`
   Already renders active plans, but it only infers `done/active/pending`
   from colony statuses. It has no `blocked` truth for later groups.

4. `frontend/src/components/fc-preview-card.ts`
   Already renders preview metadata. It is the right place to show full
   group structure and planned task coverage.

5. `frontend/src/components/fc-result-card.ts`
   Already renders result metadata, including output files. It is the
   right place to show partial / blocked plan truth once Track B exposes
   it.

6. `frontend/src/components/knowledge-browser.ts`
   Already exposes `Reindex Code`; this is a useful reference for
   reindex UX, but Wave 81 should surface that truth in Workspace and
   Settings too.

## What To Build

### 1. Workspace truth

Update the workspace surface to show distinct sections for:

- `Project Files` when a binding is active
- `Workspace Library`
- `Working Memory`
- `Artifacts`

Do not call everything "workspace files."

### 2. Binding + index truth

Show, in Settings and/or Workspace:

- bound path
- binding mode
- code-index status
- last indexed time
- reindex action / status

These should come from backend truth, not from hardcoded assumptions.

### 3. Plan-group truth

Update active-plan and card surfaces so the operator can see:

- total groups
- pending groups
- running groups
- blocked groups
- completed groups
- failed groups

The operator should be able to catch "Group 2 never launched" without
opening logs.

### 4. Real-repo benchmark dashboard

Use the `rtp-xx` task-pack naming convention plus the existing workspace
outcomes surface to render a small benchmark dashboard in-product.

Keep it simple:

- task ID / title
- last run
- status
- quality
- rounds
- cost or time

## Important Constraints

- Do not build the full Wave 83 planning workbench yet
- Do not add hidden heuristics that reinterpret backend state
- Prefer truthful labels over clever ones

## Validation

Run:

- `cd frontend; npm run build`

Manual smoke:

1. a bound workspace clearly shows `Project Files`
2. workspace-library upload/ingest still exists
3. active plans can show blocked later groups
4. result cards do not collapse partial plans into simple success
5. task-pack results are visible in the product

## Overlap Note

You are not alone in the codebase. Track B will change the meaning of
plan status. Wait for those backend states before finalizing labels and
icons. Keep the UI additive so Wave 82 can layer plan explainability on
top rather than replacing this work.
