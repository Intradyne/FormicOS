# Wave 71.0 - Team A: Operational Memory

**Theme:** Give the Queen a durable working-memory layer that stays separate
from institutional memory and is readable by both runtime and operator.

## Context

Read these first:

- `docs/waves/wave_71_0/design_note.md`
- `docs/waves/wave_71_0/wave_71_0_plan.md`
- `CLAUDE.md`

### Key seams to read before coding

- `queen_budget.py` — current 7 slots: `system_prompt` 15%, `memory_retrieval`
  15%, `project_context` 10%, `project_plan` 5%, `thread_context` 15%,
  `tool_memory` 10%, `conversation_history` 30%. Fallbacks: 2000/1500/500/400/
  1500/4000/6000 tokens. `_FRACTIONS` at line 24, `_FALLBACKS` at line 33,
  `QueenContextBudget` frozen dataclass at line 45.
- `queen_runtime.py` `respond()` (line 859) injection order:
  - memory retrieval (lines 895–929, budget: `memory_retrieval`)
  - project context (lines 931–953, budget: `project_context` at line 939)
  - project plan (lines 955–980, budget: `project_plan` at line 967)
  - session summary (lines 982–1010, **hardcoded `[:4000]` at line 993** —
    not budget-backed, this is what you fix)
  - thread context (lines 1012–1023)
  - briefing (lines 1025–1094)
  - deliberation frame (lines 1096–1119, budget: `thread_context`)
- `queen_runtime.py` `emit_session_summary()` (line 764) — writes to
  `.formicos/sessions/{thread_id}.md`. This is where to add journal hook.
- `project_plan.py` — existing shared helper pattern to follow: `load_*()`,
  `render_for_queen()`, workspace-scoped file paths.
- `routes/api.py` — workspace endpoints at lines 1717–1826. New journal/
  procedures endpoints should go after the forager block (line 1769).

Current repo truth:

- No shared helper for operational files exists yet.
- No `.formicos/operations/` directory structure exists yet.

## Your Files (exclusive ownership)

- `src/formicos/surface/operational_state.py` - **new**
- `src/formicos/surface/queen_runtime.py`
- `src/formicos/surface/queen_budget.py`
- `src/formicos/surface/routes/api.py` - journal/procedures endpoints only
- `docs/decisions/051-dynamic-context-caps.md`
- `tests/unit/surface/test_operational_state.py` - **new**

## Do Not Touch

- `src/formicos/surface/self_maintenance.py` - Team B owns
- `src/formicos/surface/app.py` - Team B owns
- `src/formicos/surface/project_plan.py` - read only
- `src/formicos/surface/projections.py`
- `src/formicos/core/events.py`
- frontend files

## Overlap Coordination

- Team B will import your helper for journal notes and operational paths.
- Team C will consume your helper for journal/procedure reads and may add a
  separate continuity block to `queen_runtime.py`.
- In `routes/api.py`, you only own the journal/procedure endpoints. Team B and
  Team C add other `/operations/...` endpoints.

---

## Track 1: Shared Operational-State Helper

Create `src/formicos/surface/operational_state.py` as the single source of
truth for workspace-scoped operational files:

- `.formicos/operations/{workspace_id}/queen_journal.md`
- `.formicos/operations/{workspace_id}/operating_procedures.md`

Required helpers:

- resolve the workspace ops directory
- load/save operating procedures
- append a journal entry
- read a journal tail for UI/runtime use
- render compact procedures/journal text for Queen injection
- if clean, provide one structured helper for appending a rule under a
  markdown heading so future procedure suggestions do not need ad hoc text
  surgery

Rules:

- journal stays append-only in spirit
- procedures are editable and overwriteable
- keep helpers deterministic and file-backed
- do not route any of this through `memory_entries`

---

## Track 2: Journal + Procedures in Queen Context

### Requirements

1. Inject operating procedures into the Queen context as a dedicated system
   block when the file exists. Insert after the project plan block (line 980)
   and before the session summary block (line 982). Follow the same
   `[:budget.operating_procedures * 4]` pattern used by project plan at
   line 967.

2. Inject a compact journal tail into the Queen context as a dedicated system
   block when entries exist. Insert immediately after the procedures block.
   Cap with `[:budget.queen_journal * 4]`.

3. Stop using the hardcoded session-summary `[:4000]` cap at line 993.
   Replace with `[:budget.thread_context * 4]` to match the existing
   budget-backed pattern.

4. Add a deterministic journal append hook that other teams can reuse. At
   minimum, journal entries should be written for:

- session summary emission
- major Queen response milestones when easy to capture
- operator-facing operational notes from other tracks via helper import

Do not turn the journal into a verbose transcript dump. It should read like a
working log, not chat history.

---

## Track 3: Budget + Endpoints

### ADR / budget update

Update `queen_budget.py` and ADR-051 so the budget explicitly includes:

- `operating_procedures`
- `queen_journal`

Recommended split (changes marked):

- `system_prompt`: 15% (unchanged)
- `memory_retrieval`: 13% (**was 15% — reduced by 2%**)
- `project_context`: 8% (**was 10% — reduced by 2%**)
- `project_plan`: 5% (unchanged)
- `operating_procedures`: 5% (**new**)
- `queen_journal`: 4% (**new**)
- `thread_context`: 13% (**was 15% — reduced by 2%**)
- `tool_memory`: 9% (**was 10% — reduced by 1%**)
- `conversation_history`: 28% (**was 30% — reduced by 2%**)

This trades 9% across four existing slots for two new slots, keeping
conversation_history as the largest allocation. No single slot loses more
than 2 absolute points.

Keep `max(fallback, proportional)`. Recommended fallback floors for new
slots: `operating_procedures` 400 tokens, `queen_journal` 300 tokens.
Do not shrink existing fallback floors below current truth.

### Endpoints

Add additive endpoints:

- `GET /api/v1/workspaces/{workspace_id}/queen-journal`
- `GET /api/v1/workspaces/{workspace_id}/operating-procedures`
- `PUT /api/v1/workspaces/{workspace_id}/operating-procedures`

The journal endpoint can return a compact tail by default plus optional full
text. Keep the shape simple and machine-readable.

---

## Acceptance Gates

- [ ] `operational_state.py` exists and is the canonical helper
- [ ] operational files are workspace-scoped under `.formicos/operations/`
- [ ] procedures and journal inject into Queen context through explicit budget
      slots
- [ ] session-summary injection no longer uses a hardcoded 4000-char cap
- [ ] ADR-051 matches the new budget truth
- [ ] journal/procedures endpoints exist and are stable
- [ ] no new event types
- [ ] no `memory_entries` usage for operational artifacts

## Validation

```bash
pytest tests/unit/surface/test_operational_state.py -v
ruff check src/
pyright src/
python scripts/lint_imports.py
```
