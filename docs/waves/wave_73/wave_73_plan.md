# Wave 73 Plan — The Developer Bridge

## Goal

Make FormicOS a Claude Code force multiplier: connect in 60 seconds, compose
workflows via MCP prompts, fix every wrong number in the frontend.

## Teams

### Team A: MCP Prompts + Resources + Addon Tools + init-mcp

**Scope:** 6 new MCP prompts, 3 new MCP resources, 3 new MCP tools for addon
control, `init-mcp` CLI subcommand.

**Owned files:**
- `src/formicos/surface/mcp_server.py` — all new prompts, resources, tools
- `src/formicos/__main__.py` — `init-mcp` subcommand
- `src/formicos/surface/runtime.py` — add `addon_registrations` attribute (1 line)
- `src/formicos/surface/app.py` — assign `runtime.addon_registrations` (1 line)

**Data sources (read-only):**
- `src/formicos/surface/operational_state.py` — journal, procedures
- `src/formicos/surface/operations_coordinator.py` — `build_operations_summary()`
- `src/formicos/surface/action_queue.py` — `list_actions()`
- `src/formicos/surface/project_plan.py` — `load_project_plan()`, `render_for_queen()`
- `src/formicos/surface/self_maintenance.py` — `compute_autonomy_score()`
- `src/formicos/surface/knowledge_catalog.py` — search (for knowledge_for_context)
- `src/formicos/surface/memory_store.py` — knowledge entry creation (for log_finding)

**Do not touch:** `addon_loader.py`, `projections.py`, `events.py`,
any frontend files, `routes/api.py`.

### Team B: Frontend Truth + Workspace Creation

**Scope:** Kill hardcoded defaults in colony-creator and template-editor. Wire
`runtimeConfig` to components that need it. Add workspace creation UI. Fix
addon config type coercion.

**Owned files:**
- `frontend/src/components/colony-creator.ts` — budget/maxRounds/tier costs
- `frontend/src/components/template-editor.ts` — budget/maxRounds defaults
- `frontend/src/components/playbook-view.ts` — pass governance to template-editor (1 line)
- `frontend/src/components/formicos-app.ts` — pass runtimeConfig to colony-creator, workspace creation modal
- `frontend/src/types.ts` — RuntimeConfig property additions if needed
- `src/formicos/surface/routes/api.py` — workspace creation endpoint + addon config type coercion

**Do not touch:** `mcp_server.py`, `settings-view.ts`, `addons-view.ts`,
`addon_loader.py`, `projections.py`.

### Team C: Settings Protocol Detail + Addon Polish + Documentation

**Scope:** Verify Settings protocol detail (may already be done by Wave 72.5
Team C). Addon search/filter. Addon health summary card. CLAUDE.md refresh.
`docs/DEVELOPER_BRIDGE.md`.

**Owned files:**
- `frontend/src/components/settings-view.ts` — verify/adjust protocol detail
- `frontend/src/components/addons-view.ts` — search, health summary
- `CLAUDE.md` — refresh with post-73 state
- `docs/DEVELOPER_BRIDGE.md` — new developer-facing guide

**Do not touch:** `mcp_server.py` (Team A), `colony-creator.ts` (Team B),
`formicos-app.ts` (Team B), `addon_loader.py`, `projections.py`.

## Merge order

```
Team A (MCP surface)     — merges first (defines the MCP surface)
Team B (frontend truth)  — merges second (independent of MCP)
Team C (docs + polish)   — merges third (docs reflect final state)
```

All three develop in parallel. No shared-file conflicts between teams.

## Coordination points

- Team B removes nothing from Settings — Team C verifies protocol detail
  is already there from Wave 72.5. If it's missing, Team C adds it.
- Team A defines the MCP surface. Team C documents it in DEVELOPER_BRIDGE.md
  and CLAUDE.md. Team C must wait for Team A's final tool/prompt/resource
  list before writing docs.

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
cd frontend && npm run build && npm run lint
```

## Success criteria

1. `python -m formicos init-mcp` generates `.mcp.json` (with `"type": "http"`) and `.formicos/DEVELOPER_QUICKSTART.md`
2. Claude Code connects to FormicOS MCP server and sees 27 tools + 9 resources + 6 prompts
3. `morning_status` prompt returns a complete briefing from Claude Code
4. `delegate_task` prompt composes workspace resolution + team suggestion + blast radius estimate
5. `knowledge_for_context` prompt searches institutional memory and returns prose
6. `handoff_to_formicos` tool creates thread + colony with developer context
7. Colony creator shows governance-configured budget and maxRounds (not hardcoded 2.0/10)
8. Template editor shows governance-configured defaults (not hardcoded 1.0/5)
9. `POST /api/v1/workspaces` endpoint exists, workspace creation accessible from the frontend
10. Addon config saves with correct types (boolean, integer, not strings)
11. `docs/DEVELOPER_BRIDGE.md` is readable by a new developer in 5 minutes
12. CLAUDE.md reflects 73 waves of evolution
