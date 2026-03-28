# Wave 74 Plan — Queen Command & Control

## Goal

Transform the Queen tab from a fleet dashboard into a command surface. The
operator sees what the Queen wants, what she's doing, what rules she follows,
and how she's performing — without scrolling through chat history.

Two halves, one coherent product change:

- **74.0** — Elevation: make visible what's already computed. No new Queen
  tools, no new backend mechanisms. Fast.
- **74.5** — Invention: display board, tool tracking, behavioral overrides.
  New Queen tool, backend instrumentation, structured observations.

## Teams

### Team A: Queen Tab Shell + Display Board + Tool Tracking

**Scope:** Restructure `queen-overview.ts` into the 4-question layout and act
as the single composition owner for the Queen tab. Build the display board
(journal extension + `post_observation` Queen tool + sweep auto-posting). Add
tool usage counters. Mount Team B and Team C components in the final shell.

**Owned files:**
- `frontend/src/components/queen-overview.ts` — restructure into Queen C&C layout
- `frontend/src/components/queen-display-board.ts` — new component (reads filtered journal)
- `frontend/src/components/queen-tool-stats.ts` — new component (tool usage table)
- `src/formicos/surface/operational_state.py` — extend `append_journal_entry()` + `parse_journal_entries()`
- `src/formicos/surface/queen_tools.py` — add `post_observation` tool
- `src/formicos/surface/queen_runtime.py` — tool call counter in `_execute_tool()`
- `src/formicos/surface/routes/api.py` — `GET .../queen-tool-stats` endpoint
- `src/formicos/surface/app.py` — sweep auto-posting at end of operational sweep loop
- `config/caste_recipes.yaml` — add `post_observation` to Queen tools list + replace tool section with `{TOOL_INVENTORY}` placeholder

**Do not touch:** `queen_budget.py`, `projections.py`, `events.py`,
`workspace-config.ts`, `workspace-browser.ts`, `formicos-app.ts` (except
event wiring if needed).

### Team B: Elevation Components — Continuations, Autonomy, Budget, Workspace Move

**Scope:** Elevate existing computed data to the Queen tab. Build continuation
candidates renderer, autonomy score card, context budget visualizer. Move
colony cards from Queen tab to workspace view. Define the exact mount contract
for the existing procedures editor so Team A can place it in the Queen tab.

**Owned files:**
- `frontend/src/components/queen-continuations.ts` — new component (reads operations summary)
- `frontend/src/components/queen-autonomy-card.ts` — new component (reads autonomy-status)
- `frontend/src/components/queen-budget-viz.ts` — new component (context budget stacked bar)
- `frontend/src/components/workspace-config.ts` — absorb colony cards section
- `src/formicos/surface/routes/api.py` — `GET /api/v1/queen-budget` endpoint (~15 lines)
- `frontend/src/components/formicos-app.ts` — wire new events from workspace-config

**Do not touch:** `queen_runtime.py`, `queen_tools.py`, `operational_state.py`,
`app.py`, `events.py`, `projections.py`.

### Team C: Behavioral Overrides + Documentation

**Scope:** Build workspace-scoped Queen behavioral override forms. Store via
existing `WorkspaceConfigChanged`. Inject into Queen context. Update docs.
Ship the overrides component and its prop/event contract; Team A mounts it in
the Queen tab shell.

**Owned files:**
- `frontend/src/components/queen-overrides.ts` — new component (override forms)
- `src/formicos/surface/queen_runtime.py` — override injection in `_build_messages()` (5-15 lines)
- `CLAUDE.md` — update Queen tab description, tool count (42)
- `docs/DEVELOPER_BRIDGE.md` — update with Queen C&C description

**Do not touch:** `queen_tools.py`, `queen_budget.py`, `operational_state.py`,
`app.py`, `events.py`, `projections.py`, `queen-overview.ts`.

## Merge order

```
Team B (elevation)      — merges first (components + workspace relocation)
Team C (overrides)      — merges second (runtime injection + component contract + docs)
Team A (shell + board)  — merges last (final Queen tab composition + backend changes)
```

All three develop in parallel. Shared-file coordination:
- `routes/api.py` — Team A adds queen-tool-stats, Team B adds queen-budget.
  Different functions, different routes. No conflict.
- `queen_runtime.py` — Team A adds counter (line 2005) + tool inventory
  injection from `tool_specs()` (before line 1733) + per-workspace initial
  board population. Team C adds override injection (after line 1733).
  Different locations. No conflict.
- `queen-overview.ts` — Team A is the only editor. Team B/C provide child
  components and prop contracts; they do not patch the shell directly.

## 74.0 / 74.5 split

**74.0 (elevation — Team B components + Team A shell composition):**
- Queen tab layout restructure (remove colony cards, arrange sections)
- Continuation candidates renderer
- Autonomy score card
- Context budget visualizer
- Procedures editor elevation (Team B verifies tag/contract, Team A mounts)
- Colony cards move to workspace-config.ts

**74.5 (invention — Team A display board + Team C overrides):**
- Journal extension (heading/metadata)
- `post_observation` Queen tool
- Sweep auto-posting
- Tool usage tracking
- Behavioral override mechanism + forms

## Shared seams

- `queen-overview.ts` is single-owner: Team A mounts `fc-queen-continuations`,
  `fc-queen-autonomy-card`, `fc-queen-budget-viz`,
  `fc-operating-procedures-editor`, `fc-queen-overrides`, and
  `fc-queen-tool-stats`.
- Journal metadata must not leak into Queen context. Team A updates parsing and
  journal rendering together.
- Override support is not complete unless all 4 keys are covered:
  `queen.disabled_tools`, `queen.custom_rules`, `queen.team_composition`,
  `queen.round_budget`.

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
cd frontend && npm run build
```

## Success criteria

1. Queen tab answers 4 questions: what does she want, what is she doing, what rules, how performing
2. Display board shows structured observations with severity-based styling
3. `post_observation` Queen tool writes to journal with display_board metadata
4. Operational sweep auto-posts notable findings to display board
5. Display board populated on first `respond()` call (no 30-min wait for first sweep)
6. Tool usage stats visible (session-scoped call counts per Queen tool)
7. Continuation candidates visible with readiness/blocker status
8. Autonomy score card shows grade (A-F), 4 components, recommendation
9. Context budget visualizer shows 9-slot allocation
10. Operating procedures editor accessible from Queen tab
11. Behavioral overrides stored via WorkspaceConfigChanged, injected into Queen context, all 4 keys covered
12. Colony cards removed from Queen tab, present in workspace view
13. Queen system prompt tool inventory is self-assembled from registered handlers (no manual tool list drift)
14. No regressions — all tests pass, frontend builds clean
