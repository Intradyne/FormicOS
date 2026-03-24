# Wave 21 Dispatch Prompts

Three parallel coder teams. Each prompt is self-contained and grounded in the current repo state.

Important note for all teams:

- read the current repo-root `AGENTS.md` first
- if a Wave 21-specific `AGENTS.md` lands during dispatch, reread it before writing

---

## Team 1 - Track A: Self-Describing System + Queen Power Tools

```text
You are Coder 1 for Wave 21. Your track is "Self-Describing System + Queen Power Tools."

Read first, in order:
1. C:\Users\User\FormicOSa\CLAUDE.md
2. C:\Users\User\FormicOSa\AGENTS.md
3. C:\Users\User\FormicOSa\docs\waves\wave_21\plan.md
4. C:\Users\User\FormicOSa\docs\waves\wave_21\algorithms.md
5. C:\Users\User\FormicOSa\docs\waves\wave_21\planning_findings.md

Mission:
Make the system describe itself mechanically, close the transcript input_sources truth gap, and give the Queen four high-value new tools.

Deliverables:

A1. Capability registry
- Add src/formicos/surface/registry.py
- Frozen dataclasses for registry/tool/protocol entries
- Registry carries names/inventories, not just counts
- Build it during app assembly and store on app.state.registry

A2. /debug/inventory
- Add GET /debug/inventory
- Return registry JSON

A3. Manifest-based parity
- Add EVENT_TYPE_NAMES to src/formicos/core/events.py
- Add EVENT_NAMES to frontend/src/types.ts
- Add a new parity test that checks events/tools/protocol inventories

A4. Fix input_sources persistence
- Add input_sources to ColonyProjection
- Populate from ColonySpawned in the projection handler

A5-A8. New Queen tools
- read_colony_output
- search_memory
- write_workspace_file
- queen_note

A9. Raise _MAX_TOOL_ITERATIONS from 5 to 7

Key constraints:
- Do not use FastMCP private internals for registry truth
- If MCP tool descriptions are needed, add a small explicit manifest in mcp_server.py
- search_memory must reuse the existing two-collection search pattern used by memory_search
- write_workspace_file must write to data/workspaces/{workspace_id}/files/
- queen_note must inject only a bounded latest-N note set into context
- Keep everything honest and bounded

Files you own:
- src/formicos/surface/registry.py
- src/formicos/surface/app.py
- src/formicos/surface/mcp_server.py
- src/formicos/core/events.py
- src/formicos/surface/projections.py
- src/formicos/surface/queen_runtime.py
- frontend/src/types.ts
- tests for registry/parity/Queen-tool coverage

Do not touch:
- src/formicos/core/ports.py
- src/formicos/core/types.py
- src/formicos/engine/*
- src/formicos/surface/view_state.py
- src/formicos/surface/agui_endpoint.py
- src/formicos/surface/transcript.py
- src/formicos/surface/routes/*
- config/*
- docker-compose.yml
- Dockerfile

Validation:
- uv run ruff check src/
- uv run pyright src/
- python scripts/lint_imports.py
- python -m pytest -q
```

---

## Team 2 - Track B: Structural Extraction

```text
You are Coder 2 for Wave 21. Your track is "Structural Extraction."

Read first, in order:
1. C:\Users\User\FormicOSa\CLAUDE.md
2. C:\Users\User\FormicOSa\AGENTS.md
3. C:\Users\User\FormicOSa\docs\waves\wave_21\plan.md
4. C:\Users\User\FormicOSa\docs\waves\wave_21\algorithms.md
5. C:\Users\User\FormicOSa\docs\waves\wave_21\planning_findings.md

Important sequencing rule:
- reread src/formicos/surface/app.py after Coder 1 lands registry construction

Mission:
Split app.py into route modules and make protocol truth consume the registry instead of duplicating facts.

Deliverables:

B1. Route extraction
- Create src/formicos/surface/routes/__init__.py
- Create src/formicos/surface/routes/api.py
- Create src/formicos/surface/routes/colony_io.py
- Create src/formicos/surface/routes/protocols.py
- Create src/formicos/surface/routes/health.py
- Shrink src/formicos/surface/app.py to factory/lifespan/assembly logic

B2. Registry consumers
- Update protocol truth in view_state.py to read from the registry
- Update Agent Card builder to read from the registry

B3. Stretch only
- Optional view_state helper extraction if B1 and B2 are already green

Key constraints:
- This is mechanical extraction, not behavioral redesign
- Route behavior must remain unchanged
- No global state in route modules; pass dependencies explicitly
- /debug/inventory is created by Track A and extracted here
- If the wave runs long, drop B3 first

Files you own:
- src/formicos/surface/routes/__init__.py
- src/formicos/surface/routes/api.py
- src/formicos/surface/routes/colony_io.py
- src/formicos/surface/routes/protocols.py
- src/formicos/surface/routes/health.py
- src/formicos/surface/app.py
- src/formicos/surface/view_state.py
- src/formicos/surface/view_helpers.py (stretch only)

Do not touch:
- src/formicos/core/*
- src/formicos/engine/*
- src/formicos/adapters/*
- src/formicos/surface/queen_runtime.py
- src/formicos/surface/projections.py
- src/formicos/surface/registry.py
- src/formicos/surface/mcp_server.py
- src/formicos/surface/agui_endpoint.py
- src/formicos/surface/transcript.py
- config/*
- frontend/* except stretch helper fallout if strictly necessary
- docker-compose.yml
- Dockerfile

Validation:
- uv run ruff check src/
- uv run pyright src/
- python scripts/lint_imports.py
- python -m pytest -q
```

---

## Team 3 - Track C: Evaluation Infrastructure

```text
You are Coder 3 for Wave 21. Your track is "Evaluation Infrastructure."

Read first, in order:
1. C:\Users\User\FormicOSa\CLAUDE.md
2. C:\Users\User\FormicOSa\AGENTS.md
3. C:\Users\User\FormicOSa\docs\waves\wave_21\plan.md
4. C:\Users\User\FormicOSa\docs\waves\wave_21\algorithms.md
5. C:\Users\User\FormicOSa\docs\waves\wave_21\planning_findings.md

Mission:
Build an exploratory A/B evaluation path that compares stigmergic vs sequential under held-constant conditions.

Deliverables:

C1. Task suite
- Add 6-8 YAML tasks under config/eval/tasks/
- Cover simple, moderate, and complex tasks

C2. In-process harness
- Add src/formicos/eval/__init__.py
- Add src/formicos/eval/run.py
- Run both strategies with identical task/budget/team/model settings
- Use runtime.spawn_colony() and build_transcript()

C3. Comparison artifact
- Add src/formicos/eval/compare.py
- Emit markdown and JSON artifacts
- Include explicit "exploratory only, not statistically significant" framing

Stretch:
- none required beyond core artifact generation

Key constraints:
- Keep this script/report-first
- Do not build a frontend comparison panel
- Do not claim benchmark-grade significance
- Hold all variables constant except coordination strategy
- Prefer in-process runtime usage over external protocol dependency

Files you own:
- config/eval/tasks/*.yaml
- src/formicos/eval/__init__.py
- src/formicos/eval/run.py
- src/formicos/eval/compare.py
- eval-specific tests only if you find them useful

Do not touch:
- src/formicos/core/*
- src/formicos/engine/*
- src/formicos/adapters/*
- src/formicos/surface/*
- frontend/*
- config/formicos.yaml
- config/caste_recipes.yaml
- docker-compose.yml
- Dockerfile

Validation:
- uv run ruff check src/
- uv run pyright src/
- python -m pytest -q
- run at least one task locally if stack/runtime conditions allow
```
