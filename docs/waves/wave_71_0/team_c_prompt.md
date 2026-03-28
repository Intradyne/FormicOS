# Wave 71.0 - Team C: Coherence Coordinator

**Theme:** Synthesize project plan, thread plans, session summaries, recent
outcomes, and queued actions into one compact operational model that both the
Queen and the future UI can read.

## Context

Read these first:

- `docs/waves/wave_71_0/design_note.md`
- `docs/waves/wave_71_0/wave_71_0_plan.md`
- `CLAUDE.md`

### Key seams to read before coding

- `project_plan.py` — existing shared helper pattern. `load_project_plan()`
  returns `{"exists": bool, "goal": str, "milestones": [...]}`.
  `render_for_queen()` returns compact text. Follow this pattern for thread
  plans.
- `queen_tools.py` — `_propose_plan()` at line 3205 writes thread plans to
  `.formicos/plans/{thread_id}.md`. `_STEP_RE` regex at line 3390:
  `r"^- \[(\d+)\] \[(\w+)\] (.*)$"`. This is the format you must parse.
- `queen_runtime.py` — `emit_session_summary()` at line 764 writes session
  summaries to `.formicos/sessions/{thread_id}.md`. Session file contains:
  plan excerpt (`[:1000]`), colony activity, step status, recent Queen
  messages. `_build_thread_context()` at line 1736 reads thread plans with
  a hardcoded `[:2000]` cap at line 1824.
- `queen_runtime.py` `respond()` injection order — your continuity-summary
  block goes after briefing (line 1094) and before deliberation frame
  (line 1096). Team A adds procedures/journal blocks between lines 980–982.
- Team A's post-rebalance budget: `thread_context` will be 13% (was 15%).
  Your continuity block should use `[:budget.thread_context * 2]` (half the
  thread-context allocation, ~2600 chars on a 32K model) as a conservative
  cap. This is intentionally smaller than a full slot — if the summary needs
  more space, it belongs in a dedicated slot in a future wave.

Current repo truth:

- No shared thread-plan parser/helper exists yet.
- No endpoint answers "what should we continue next?"

## Your Files (exclusive ownership)

- `src/formicos/surface/thread_plan.py` - **new**
- `src/formicos/surface/operations_coordinator.py` - **new**
- `src/formicos/surface/queen_runtime.py` - continuity-summary block only
- `src/formicos/surface/routes/api.py` - operations summary endpoint only
- `tests/unit/surface/test_operations_coordinator.py` - **new**

## Do Not Touch

- `src/formicos/surface/operational_state.py` - Team A owns
- `src/formicos/surface/action_queue.py` - Team B owns
- `src/formicos/surface/self_maintenance.py` - Team B owns
- `src/formicos/surface/queen_budget.py` - Team A owns
- `src/formicos/surface/projections.py`
- `src/formicos/core/events.py`
- frontend files

## Overlap Coordination

- You may read Team A and Team B helpers, but do not take ownership of them.
- If you decide a continuation/sync issue should become a queued action, route
  it through Team B's action-queue helper instead of emitting direct Queen
  messages or direct autonomous dispatch.
- In `queen_runtime.py`, you only own a compact continuity-summary block.

---

## Track 7: Shared Thread-Plan Helper

Create `src/formicos/surface/thread_plan.py` as the canonical helper for
reading `.formicos/plans/{thread_id}.md`.

Keep it simple:

- resolve thread-plan path
- parse a step list and coarse statuses
- expose compact summary data

Do not try to replace the plan-file format. This helper exists so the
coordinator and API route stop doing ad hoc markdown scraping.

---

## Track 8: Operations Coordinator

Create `src/formicos/surface/operations_coordinator.py`.

It should inspect:

- project plan
- thread plans
- session summaries
- recent colony outcomes
- queued actions summary

From those, derive:

- `continuation_candidates`
- `sync_issues`
- `recent_progress`
- compact counts for pending review / stalled work / active milestones
- operator-availability signals (`last_operator_activity_at`,
  `idle_for_minutes`, `operator_active`)

Examples of useful findings:

- a milestone is still pending but its thread plan is fully complete
- a thread has pending steps, no active colony, and recent successful context
- a thread had failures last session and probably needs operator review
- there is a backlog of queued actions but no clear active milestone owner

This coordinator is a synthesis layer, not a second source of truth.

---

## Track 9: Summary Endpoint + Queen Cue

Add:

- `GET /api/v1/workspaces/{workspace_id}/operations/summary`

Suggested shape:

```json
{
  "workspace_id": "ws_123",
  "pending_review_count": 2,
  "active_milestone_count": 1,
  "last_operator_activity_at": "2026-03-26T18:10:00Z",
  "idle_for_minutes": 47,
  "operator_active": false,
  "continuation_candidates": [],
  "sync_issues": [],
  "recent_progress": []
}
```

Also add a compact `# Operational Loop Summary` system block in
`queen_runtime.py` using the coordinator output.

Rules:

- keep it short and operational
- do not dump full plans or full journal text here
- cap it with `[:budget.thread_context * 2]` (half the thread-context
  allocation, conservative by design — see key seams above)

Shape the continuation candidates for future automation now. Each candidate
should already carry a concise `blocked_reason` or `ready_for_autonomy` style
signal so Wave 72 does not need a contract rewrite just to distinguish
"interesting" from "actually executable."

If it is cheap and clean, queue continuation/sync proposals through Team B's
helper. Do not directly auto-dispatch them in this packet.

## Acceptance Gates

- [ ] `thread_plan.py` exists as the canonical thread-plan helper
- [ ] `operations_coordinator.py` synthesizes real artifacts
- [ ] `GET /api/v1/workspaces/{workspace_id}/operations/summary` exists
- [ ] Queen gets a compact operational continuity cue
- [ ] no duplicate source of truth for plans or approvals
- [ ] no new event types

## Validation

```bash
pytest tests/unit/surface/test_operations_coordinator.py -v
ruff check src/
pyright src/
python scripts/lint_imports.py
```
