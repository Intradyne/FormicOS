# Wave 70.0 - Team B: Project Intelligence Substrate

**Theme:** Give the Queen a project-wide planning substrate that spans threads
and has its own stable parser, endpoint, and context budget.

## Context

Read `docs/waves/wave_70_0/wave_70_0_plan.md` first. This is backend work.
Do not build the UI card here; build the contracts that `70.5` will render.

Read `CLAUDE.md` for hard constraints.

### Key seams to read before coding

- `queen_budget.py` — current 6 slots: `system_prompt` 15%, `memory_retrieval`
  15%, `project_context` 10%, `thread_context` 20%, `tool_memory` 10%,
  `conversation_history` 30%. Fallbacks: 2000/1500/500/1500/4000/6000 tokens.
  `QueenContextBudget` is a frozen dataclass (line 44). No `project_plan`
  slot exists yet.
- `queen_runtime.py` `respond()` injection points (in order):
  - memory retrieval (lines 903–920, budget: `memory_retrieval`)
  - project context (lines 931–953, budget: `project_context` at line 939)
  - session summary (lines 955–983, **hardcoded** 4000 chars — not yet
    budget-backed)
  - thread context (lines 985–996, budget: `thread_context`)
  - briefing (lines 998–1065, summary-capped)
  - deliberation frame (lines 1069–1092, budget: `thread_context`)
  - Plan file in `_build_thread_context()` (line 1779, **hardcoded** 2000
    chars — not yet budget-backed)
- `queen_tools.py` — `_propose_plan()` (line 3131), `_mark_plan_step()`
  (line 3292), `_STEP_RE` regex (line 3288:
  `r"^- \[(\d+)\] \[(\w+)\] (.*)$"`). Plan file path:
  `{data_dir}/.formicos/plans/{thread_id}.md`
- `routes/api.py` — thread plan endpoint already exists at line 1715:
  `GET /api/v1/workspaces/{workspace_id}/threads/{thread_id}/plan`.
  No project-plan endpoint exists yet.
- `docs/decisions/051-dynamic-context-caps.md` — documents current 6-slot
  structure. Must be updated to reflect the new 7-slot structure.

## Your Files (exclusive ownership)

- `src/formicos/surface/project_plan.py` — **new**, shared parser/helper
- `src/formicos/surface/queen_tools.py` — `propose_project_milestone` and
  `complete_project_milestone` handlers only (add to handler registry near
  line 198 and tool spec list before `*self._addon_tool_specs` at line 1411)
- `src/formicos/surface/queen_runtime.py` — project-plan injection block only.
  Insert immediately after the project context block (lines 931–953), before
  the session summary block (lines 955–983). Team A owns the deliberation
  frame section (lines 1456–1495); do not touch it.
- `src/formicos/surface/queen_budget.py` — add `project_plan` slot
- `src/formicos/surface/routes/api.py` — `GET /api/v1/project-plan` only
  (add to the route table near the existing workspace endpoints, lines
  1600–1720)
- `docs/decisions/051-dynamic-context-caps.md` — update to match new slots
- `config/caste_recipes.yaml` — append tool names to Queen tools array
  (line 207)
- `tests/unit/surface/test_project_plan.py` — **new**

## Do Not Touch

- frontend files
- `src/formicos/surface/addon_loader.py` - Team A owns
- `src/formicos/surface/self_maintenance.py` - Team C owns
- `src/formicos/surface/projections.py`
- `src/formicos/core/events.py`
- `src/formicos/core/types.py`

## Overlap Coordination

- Team A and Team C also add tools to `queen_tools.py`. Keep your tool changes
  additive and self-contained.
- Team A and Team C also touch `routes/api.py`. You only own the project-plan
  endpoint section.
- In `queen_runtime.py`, you own project-plan injection only (insert between
  lines 953–955). Team A owns the deliberation frame addon coverage section
  (lines 1456–1495). Team C does not touch this file.

---

## Track 4: Shared Project Plan Helper

### Goal

Stop duplicating plan-file parsing logic across tools, runtime injection, and
API routes.

### Implementation

Create `src/formicos/surface/project_plan.py` as the single source of truth
for:

- resolving the project plan path
- parsing markdown into structured milestones
- rendering parsed plan back into compact Queen context text
- updating `Updated:` timestamps consistently

Suggested return shape:

```python
{
    "exists": True,
    "goal": "...",
    "updated": "...",
    "milestones": [
        {
            "index": 0,
            "status": "completed",
            "description": "...",
            "thread_id": "...",
            "completed_at": "...",
            "note": "...",
        }
    ],
}
```

Use this helper everywhere in this track. No duplicated regex parsing in
multiple files.

---

## Track 5: Milestone Tools + Read Endpoint + Budget Slot

### Requirements

**1. Two explicit Queen tools**

Use explicit names:

- `propose_project_milestone`
- `complete_project_milestone`

Avoid the ambiguous `complete_milestone` name. We already have other
step/milestone concepts in the system.

These tools should:

- create `.formicos/project_plan.md` if needed
- append/update milestones through the shared helper
- stamp the active `thread_id` when relevant
- keep the file append-only in spirit, even if the markdown file is rewritten

**2. `GET /api/v1/project-plan`**

Add a read endpoint that returns structured JSON from the shared helper.

Why this endpoint exists in `70.0`:

- `70.5` must not parse markdown in the browser
- `70.5` project-plan UI should be almost pure rendering work

**3. Dedicated context budget**

The project plan must **not** share the `project_context` slot.

Update `queen_budget.py` so the Queen gets a dedicated `project_plan`
allocation. The current slots sum to 1.0 across 6 fields. Adding a 7th
requires rebalancing. Recommended split (changes marked):

- `system_prompt`: 15% (unchanged)
- `memory_retrieval`: 15% (unchanged)
- `project_context`: 10% (unchanged)
- `project_plan`: 5% (**new**)
- `thread_context`: 15% (**was 20% — reduced by 5%**)
- `tool_memory`: 10% (unchanged)
- `conversation_history`: 30% (unchanged)

This trades 5% of thread context for the project plan slot. Thread context
still gets the `max(fallback=1500, proportional)` guarantee, so on large
context windows the absolute allocation stays high.

Add the new field to `QueenContextBudget` (frozen dataclass, line 44),
`_FRACTIONS` (line 24), and `_FALLBACKS` (line 33). Recommended fallback
floor for `project_plan`: 400 tokens.

Keep the `max(fallback, proportional)` rule.

Update ADR-051 so the budget doc matches the code truth.

---

## Track 6: Project Plan Injection

### Goal

Make the Queen project-aware on startup and in new conversations.

### Requirements

- inject the parsed project plan into Queen context as its own system message
  block, following the same insertion pattern as project context (lines 931–953)
- cap it with the dedicated `project_plan` budget:
  `[:budget.project_plan * 4]` (chars-per-token ratio matches existing usage)
- use the shared helper to render the compact context form
- keep this separate from `project_context.md` and separate from thread plans
- label the injected block `# Project Plan (cross-thread)` so the Queen
  knows this spans threads

This is additional context, not a replacement for the workspace project
context file.

## Tests

Create `tests/unit/surface/test_project_plan.py` with at least:

1. parser returns structured milestones from markdown
2. milestone tools create/update the plan file correctly
3. `GET /api/v1/project-plan` returns helper-derived JSON
4. malformed markdown is handled gracefully
5. Queen budget includes a dedicated `project_plan` slot
6. project-plan injection uses the project-plan budget, not `project_context`

## Acceptance Gates

- [ ] `project_plan.py` exists as the single parser/helper
- [ ] milestone tools use explicit project-plan names
- [ ] `GET /api/v1/project-plan` returns structured JSON
- [ ] project plan has its own Queen context budget
- [ ] ADR-051 is updated to match the new slot structure
- [ ] project-plan injection is separate from `project_context.md`
- [ ] no frontend changes
- [ ] no new event types

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
pytest tests/unit/surface/test_project_plan.py -v
```
