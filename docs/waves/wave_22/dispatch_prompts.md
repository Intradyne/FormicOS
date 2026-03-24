# Wave 22 Dispatch Prompts

Three parallel coder teams. Each prompt is self-contained and assumes Wave 21 is already the live baseline.

Important note for all teams:

- read the current repo-root `AGENTS.md` first
- if the Wave 22 `AGENTS.md` update lands after you started, reread it before editing shared files

---

## Team 1 - Track A: Queen Judgment + Spawn Controls

```text
You are Coder 1 for Wave 22. Your track is "Queen Judgment + Spawn Controls."

Read first, in order:
1. C:\Users\User\FormicOSa\CLAUDE.md
2. C:\Users\User\FormicOSa\AGENTS.md
3. C:\Users\User\FormicOSa\docs\waves\wave_22\plan.md
4. C:\Users\User\FormicOSa\docs\waves\wave_22\algorithms.md
5. C:\Users\User\FormicOSa\docs\waves\wave_22\planning_findings.md

Mission:
Teach the Queen to make better spawning decisions and raise the AG-UI default team floor.

Deliverables:

A1. Expose spawn controls on spawn_colony
- Add max_rounds, budget_limit, template_id, and strategy to the Queen spawn_colony tool definition
- Pass them through in the handler to runtime.spawn_colony()
- Clamp values to sane ranges

A2. Rewrite the Queen prompt
- Update the Queen recipe in config/caste_recipes.yaml
- Teach team composition heuristics
- Teach round/budget heuristics
- Teach template-first behavior
- Keep the prompt concise and action-oriented
- Make sure the recipe tool list reflects the live 16-tool surface

A3. Improve AG-UI default team
- Change the AG-UI no-castes default from single coder to a more sensible default
- Minimum acceptable default: [coder, reviewer]

Key constraints:
- Do not change runtime.spawn_colony() signature
- Do not add new tools in this track
- Make "non-code task -> researcher, not coder" explicit
- Make "trivial task -> small rounds, sequential" explicit
- Keep prompt changes scoped to the Queen recipe

Files you own:
- src/formicos/surface/queen_runtime.py
- config/caste_recipes.yaml
- src/formicos/surface/agui_endpoint.py

Do not touch:
- src/formicos/core/*
- src/formicos/engine/*
- src/formicos/surface/routes/*
- src/formicos/surface/view_state.py
- frontend/*
- docker-compose.yml
- Dockerfile

Validation:
- uv run ruff check src/
- uv run pyright src/
- python scripts/lint_imports.py
- python -m pytest -q
```

---

## Team 2 - Track B: Scoped Memory + Knowledge Ingestion

```text
You are Coder 2 for Wave 22. Your track is "Scoped Memory + Knowledge Ingestion."

Read first, in order:
1. C:\Users\User\FormicOSa\CLAUDE.md
2. C:\Users\User\FormicOSa\AGENTS.md
3. C:\Users\User\FormicOSa\docs\waves\wave_22\plan.md
4. C:\Users\User\FormicOSa\docs\waves\wave_22\algorithms.md
5. C:\Users\User\FormicOSa\docs\waves\wave_22\planning_findings.md

Important sequencing rule:
- reread src/formicos/surface/queen_runtime.py after Coder 1 lands, because you will touch queen_note threading there

Mission:
Stop colony scratch memory from bleeding across workspaces, add explicit knowledge ingestion, and make scope boundaries clearer.

Deliverables:

B1. Per-colony scratch memory
- Change memory_write to write to scratch_{colony_id}
- Change memory_search to search scratch_{colony_id}, workspace_id, and skill bank
- Thread colony_id through the search path as needed

B2. Queen search_memory scope check
- Keep Queen search_memory on workspace + skill bank
- Clarify the description if needed

B3. Knowledge ingestion
- Extend workspace file upload path with an explicit embed option
- Chunk and upsert ingested docs into workspace memory
- Preserve provenance metadata
- Add Library upload/ingest UI in knowledge-view.ts

B4. Colony/workspace file scope clarity
- Separate Colony Uploads from Workspace Library in colony detail

B5. Thread-scoped queen_note
- Move queen_note storage from workspace scope to thread scope
- Update handler path/signature as needed, not just the helper string

Key constraints:
- No VectorPort API change
- Use scratch_{colony_id} consistently
- Knowledge embedding is explicit operator action only
- Use runtime.vector_store or the existing route dependency path; do not invent a second backend surface

Files you own:
- src/formicos/engine/runner.py
- src/formicos/surface/routes/colony_io.py
- src/formicos/surface/queen_runtime.py
- frontend/src/components/knowledge-view.ts
- frontend/src/components/colony-detail.ts

Do not touch:
- src/formicos/core/*
- src/formicos/adapters/*
- config/caste_recipes.yaml
- src/formicos/surface/agui_endpoint.py
- frontend components owned by Team 3
- docker-compose.yml
- Dockerfile

Validation:
- uv run ruff check src/
- uv run pyright src/
- python scripts/lint_imports.py
- python -m pytest -q
```

---

## Team 3 - Track C: UX Truth + Regression Hardening

```text
You are Coder 3 for Wave 22. Your track is "UX Truth + Regression Hardening."

Read first, in order:
1. C:\Users\User\FormicOSa\CLAUDE.md
2. C:\Users\User\FormicOSa\AGENTS.md
3. C:\Users\User\FormicOSa\docs\waves\wave_22\plan.md
4. C:\Users\User\FormicOSa\docs\waves\wave_22\algorithms.md
5. C:\Users\User\FormicOSa\docs\waves\wave_22\planning_findings.md

Mission:
Make the UI more truthful and operator-friendly without redesigning it.

Deliverables:

C1. Relative timestamps
- Use timeAgo() in Queen chat, colony chat, and event rows where raw ISO is still rendered

C2. Tree toggle usability
- Enlarge the tree toggle click target and add visible hover affordance

C3. Queen thinking indicator
- Add a pending state between send and first Queen response
- Clear it on real response arrival, not on a timer

C4. Cost display audit
- Replace misleading zero-valued cloud spend surfaces with honest "not tracked" messaging
- Show near-zero nonzero costs as < $0.01

C5. Round history emphasis
- Lead with final output / outcome rather than only chronological round dump

C6. Minimal browser smoke path
- Add a small browser smoke test for load, tree toggle, chat input, and timestamp rendering

Key constraints:
- Prefer targeted truth/usability fixes over broad redesign
- Reuse existing frontend helpers and state where possible
- Keep the browser test minimal and focused on the regressions this wave targets

Files you own:
- frontend/src/components/queen-chat.ts
- frontend/src/components/tree-nav.ts
- frontend/src/components/model-registry.ts
- frontend/src/components/atoms.ts
- frontend/src/components/round-history.ts
- frontend/src/components/formicos-app.ts
- frontend/src/components/colony-chat.ts if needed
- tests/browser/smoke.spec.ts
- package.json if browser smoke tooling needs a dev dependency

Do not touch:
- src/formicos/**/*.py
- config/*
- frontend components owned by Team 2
- docker-compose.yml
- Dockerfile

Validation:
- cd frontend && npm run build
- browser smoke path if tooling is available
```
