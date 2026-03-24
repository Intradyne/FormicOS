# Wave 16 Dispatch Prompts

Use these prompts directly. They assume the corrected Wave 16 planning surface is now the source of truth.

## Launch order

1. Launch Stream A, Stream B, and Stream C in parallel.
2. Stream A owns the first pass on `frontend/src/components/formicos-app.ts`.
3. Stream B must reread `frontend/src/components/formicos-app.ts` after Stream A lands before doing the Playbook regroup.
4. Stream A owns the first pass on `frontend/src/components/colony-detail.ts`.
5. Stream C may start backend work immediately, but must reread `frontend/src/components/colony-detail.ts` after Stream A lands before adding upload/export UI.
6. Stream A owns the first pass on `frontend/src/types.ts`.
7. Stream B may take a second pass on `frontend/src/types.ts` only if needed for template-editor shape.

---

## Stream A Prompt

```text
# Wave 16 — Stream A: Bug Fixes + Rename + Operator Audit

Working directory: C:\Users\User\FormicOSa

Read first, in order:
1. CLAUDE.md
2. AGENTS.md
3. docs/waves/wave_16/plan.md
4. docs/waves/wave_16/algorithms.md
5. docs/waves/wave_16/planning_findings.md
6. src/formicos/surface/runtime.py
7. src/formicos/surface/commands.py
8. src/formicos/surface/projections.py
9. src/formicos/surface/view_state.py
10. src/formicos/surface/model_registry_view.py
11. src/formicos/core/events.py
12. docs/contracts/events.py
13. frontend/src/types.ts
14. frontend/src/styles/shared.ts
15. frontend/src/components/atoms.ts
16. frontend/src/components/formicos-app.ts
17. frontend/src/components/model-registry.ts
18. frontend/src/components/thread-view.ts
19. frontend/src/components/colony-detail.ts

You own:
- src/formicos/core/events.py
- docs/contracts/events.py
- src/formicos/surface/runtime.py
- src/formicos/surface/commands.py
- src/formicos/surface/projections.py
- src/formicos/surface/view_state.py
- src/formicos/surface/model_registry_view.py if helper parity is needed
- frontend/src/types.ts
- frontend/src/styles/shared.ts
- frontend/src/components/atoms.ts
- frontend/src/components/formicos-app.ts
- frontend/src/components/model-registry.ts
- frontend/src/components/thread-view.ts
- frontend/src/components/colony-detail.ts
- tests you need for these seams

Do NOT touch:
- src/formicos/surface/app.py
- template authoring files
- upload/export backend or UI beyond preserving compatibility in colony-detail until Stream C lands

Mission:
Fix the operator-control bugs in the current Wave 15 shell and add thread/colony rename.

Critical repo facts:
- Runtime.create_thread() already exists
- the WS surface does not currently expose create_thread
- model misclassification root cause is in surface/view_state.py, not only in the frontend registry component
- empty API key env vars currently look present because the code checks `is not None`
- ThreadCreated currently uses `name` as the stable thread identifier; ThreadRenamed must be display-only

Required outcomes:
1. Add-thread works end-to-end
2. `create_thread` is added to frontend WS command typing and backend WS command handling
3. Colony rename works via the existing ColonyNamed event
4. Thread rename works via new ThreadRenamed event
5. Local/cloud model grouping is correct in the snapshot
6. Missing or empty API keys show `no_key`
7. Readability is materially improved in the shell and high-traffic components
8. Current nav no longer degrades at common desktop widths

Audit allowance:
While in your owned files, fix additional low-risk operator-facing paper cuts you discover if they stay inside your ownership. Report them explicitly.

Validation:
- python scripts/lint_imports.py
- python -m pytest -q
- cd frontend && npm run build

Report back with:
- files changed
- exact create_thread path you added
- exact ThreadRenamed contract shape
- exact local/cloud grouping rule now used
- exact no_key derivation fix
- any extra audit/polish fixes you included
- validation results
```

---

## Stream B Prompt

```text
# Wave 16 — Stream B: Playbook + Template Authoring + UX Polish

Working directory: C:\Users\User\FormicOSa

Read first, in order:
1. CLAUDE.md
2. AGENTS.md
3. docs/waves/wave_16/plan.md
4. docs/waves/wave_16/algorithms.md
5. docs/waves/wave_16/planning_findings.md
6. docs/decisions/028-nav-regroup-playbook.md
7. frontend/src/components/formicos-app.ts
8. frontend/src/components/fleet-view.ts
9. frontend/src/components/template-browser.ts
10. frontend/src/components/colony-creator.ts
11. frontend/src/types.ts
12. src/formicos/surface/app.py
13. src/formicos/surface/template_manager.py

You own:
- frontend/src/components/playbook-view.ts
- frontend/src/components/fleet-view.ts
- frontend/src/components/formicos-app.ts after rereading Stream A's version
- frontend/src/components/template-editor.ts
- frontend/src/components/template-browser.ts
- frontend/src/types.ts only if needed for template editor shape
- tests you need for these frontend/template seams

Do NOT touch:
- src/formicos/core/*
- src/formicos/surface/commands.py
- src/formicos/surface/runtime.py
- src/formicos/surface/view_state.py
- src/formicos/surface/app.py
- file I/O/export work owned by Stream C

Mission:
Replace Fleet with Playbook and add template create/edit/duplicate from the UI.

Critical repo facts:
- the backend already supports POST /api/v1/templates
- the backend already supports template_id, version, tags, budget_limit, and max_rounds
- the live template schema is flat: castes + top-level budget_limit/max_rounds
- do not invent a nested governance object

Required outcomes:
1. Playbook replaces Fleet
2. Models becomes a standalone top-level tab
3. New Template UI exists
4. Edit Template UI exists
5. Duplicate Template UI exists
6. Edit mode preserves template_id and increments version coherently
7. Template editor carries through tags if present

Important overlap rule:
- reread frontend/src/components/formicos-app.ts after Stream A lands before editing it
- only take a second pass on frontend/src/types.ts if template editor shape really requires it

Audit allowance:
While in your owned files, fix additional low-risk Playbook/template UX issues you discover if they stay inside your ownership. Report them explicitly.

Validation:
- cd frontend && npm run build
- python -m pytest -q if you add or touch template-related tests

Report back with:
- files changed
- whether you replaced or renamed fleet-view
- exact final nav shape
- exact template editor payload shape
- how versioning is handled in edit vs duplicate mode
- any extra audit/polish fixes you included
- validation results
```

---

## Stream C Prompt

```text
# Wave 16 — Stream C: Colony File I/O + Export + Smoke Polish

Working directory: C:\Users\User\FormicOSa

Read first, in order:
1. CLAUDE.md
2. AGENTS.md
3. docs/waves/wave_16/plan.md
4. docs/waves/wave_16/algorithms.md
5. docs/waves/wave_16/planning_findings.md
6. docs/decisions/029-colony-file-io-rest.md
7. src/formicos/surface/app.py
8. src/formicos/surface/projections.py
9. src/formicos/surface/colony_manager.py
10. frontend/src/components/colony-detail.ts

You own:
- src/formicos/surface/app.py
- frontend/src/components/colony-detail.ts after rereading Stream A's version
- tests you need for upload/export

Do NOT touch:
- src/formicos/core/*
- src/formicos/surface/runtime.py
- src/formicos/surface/commands.py
- Playbook/template authoring files

Mission:
Add colony-scoped document upload and artifact export without opening new events.

Critical repo facts:
- uploads are colony-scoped in Wave 16; no pre-spawn staging workflow
- running-colony injection should use colony_manager.inject_message()
- export must use real repo data sources:
  - uploaded files on disk
  - colony.round_records[*].agent_outputs
  - colony.chat_messages content/timestamp
  - skills if they can be fetched by source colony
- do not implement against fake fields like agent.output or msg.ts

Required outcomes:
1. POST /api/v1/colonies/{id}/files exists
2. GET /api/v1/colonies/{id}/export exists
3. text-file limits are enforced
4. uploaded files are stored under the data dir
5. running-colony upload injection works
6. export zip supports category selection
7. uploaded files can be specifically selected for inclusion
8. colony-detail exposes upload and export affordances cleanly

Important overlap rule:
- you may start backend work immediately
- reread frontend/src/components/colony-detail.ts after Stream A lands before editing it

Audit allowance:
While in your owned files, fix additional low-risk upload/export UX issues you discover if they stay inside your ownership. Report them explicitly.

Validation:
- python -m pytest -q
- cd frontend && npm run build

Report back with:
- files changed
- exact upload storage path used
- exact export selection shape used
- exact projection/file data sources used for export
- any extra audit/polish fixes you included
- validation results
```
