# Wave 71.0 - Team B: Action Loop

**Theme:** Turn proactive insights and autonomy guardrails into a real,
durable action queue instead of a mix of silent skips and transient logs.

## Context

Read these first:

- `docs/waves/wave_71_0/design_note.md`
- `docs/waves/wave_71_0/wave_71_0_plan.md`
- `CLAUDE.md`

### Key seams to read before coding

- `self_maintenance.py` — `evaluate_and_dispatch()` at line 281. Blast radius
  gate at lines 325–354: if recommendation == "escalate" → skips dispatch;
  if level == "medium" and auto_notify → skips dispatch. `suggest` autonomy
  level returns empty at line 293. Skipped insights are currently logged but
  not persisted. `run_proactive_dispatch()` at line 560.
- `app.py` — maintenance loop at lines 892–920. **Default interval: 86400s
  (24 hours)** via `FORMICOS_MAINTENANCE_INTERVAL_S` env var (line 889).
  `_maint_dispatcher` is a **local variable** in the lifespan closure
  (line 885), **not** on `app.state` or `runtime`. You must wire it to
  `app.state.maintenance_dispatcher` so your approve/reject route handlers
  can call dispatch machinery.
- `core/events.py` — `ApprovalRequested` (line 397), `ApprovalGranted`
  (line 407), `ApprovalDenied` (line 414). `ApprovalType` enum in
  `core/types.py` (line 261): `budget_increase`, `cloud_burst`,
  `tool_permission`, `expense`. None of these types cover maintenance
  actions — see note below.
- `routes/api.py` — workspace endpoints at lines 1717–1826. New
  `/operations/...` endpoints should go after the forager block (line 1769)
  and before the Knowledge CRUD block (line 1771).
- `runtime.py` — `approve()` at line 864 and `deny()` at line 870 emit
  `ApprovalGranted`/`ApprovalDenied` events.

Current repo truth:

- There is no action ledger yet.
- The existing approval system handles live pending approvals only — no
  durable history, no rejection reasons.
- Suggest-only and skipped proactive work vanishes into logs.

## Your Files (exclusive ownership)

- `src/formicos/surface/action_queue.py` - **new**
- `src/formicos/surface/self_maintenance.py`
- `src/formicos/surface/app.py`
- `src/formicos/surface/routes/api.py` - action queue endpoints only
- `tests/unit/surface/test_action_queue.py` - **new**

## Do Not Touch

- `src/formicos/surface/operational_state.py` - Team A owns
- `src/formicos/surface/queen_budget.py` - Team A owns
- `src/formicos/surface/queen_runtime.py` - Teams A/C own
- `src/formicos/surface/projections.py`
- `src/formicos/core/events.py`
- frontend files

## Overlap Coordination

- Reuse Team A's journal helper for action audit notes when useful.
- Team C may queue continuation/sync proposals through your helper. Keep the
  queue helper generic enough for both proactive-intelligence and
  continuation-type actions.
- In `routes/api.py`, you only own the action-list/approve/reject endpoints.

---

## Track 4: Durable Action Queue Ledger

Create `src/formicos/surface/action_queue.py` as the canonical durable action
ledger:

- `.formicos/operations/{workspace_id}/actions.jsonl`

Each action record should be stable and queryable. Suggested fields:

- `action_id`
- `created_at`
- `updated_at`
- `created_by`
- `status` (`pending_review`, `approved`, `rejected`, `executed`,
  `self_rejected`, `failed`)
- `kind` (`maintenance`, `continuation`, `sync`, etc.)
- `source_category`
- `source_ref`
- `title`
- `detail`
- `rationale`
- `payload`
- `thread_id` when relevant
- `estimated_cost`
- `blast_radius`
- `confidence`
- `requires_approval`
- `approval_request_id` when a live approval exists
- `executed_at`
- `operator_reason` for rejection or manual override notes

Keep the queue file append-friendly and easy to rewrite safely if status
updates need it.

Design rule:

- `kind` is the semantic authority for routing and UI.
- Do not make future surfaces infer semantics from `ApprovalType`.
- `payload` should be generic enough that Wave 72 can add knowledge-review,
  workflow-template, and procedure-suggestion items without replacing the
  ledger shape.

### Size management

Over weeks of autonomous operation, `actions.jsonl` will grow unbounded. Add
a `compact_action_log()` helper: when the file exceeds 1000 lines, archive
older entries to `actions.{date}.jsonl.gz` and keep only the last 500 entries
in the active file. Call it at the start of each operational sweep. This is
a one-time helper, not ongoing complexity — without it, file reads for the
queue listing will degrade over weeks.

---

## Track 5: Approval-Backed Operator Review

Do **not** invent a second approval mechanism.

The action queue is the durable audit/history layer. The existing approval
event path remains the live gating mechanism. Not every queued action needs
an approval event — only actions that require operator sign-off before
execution. For those, use `ApprovalType.expense` (the closest existing fit
for "spend budget on autonomous work"). Do not add new values to the
`ApprovalType` enum in `core/types.py` — that is a Core layer type and
requires operator approval to extend.

Important:

- the UI and API should surface queue `kind`, not `ApprovalType`, as the user-
  facing action meaning
- `ApprovalType` here is transport compatibility only

Use the existing approval event path for live pending approvals, but back it
with the new action ledger and richer endpoints:

- `GET /api/v1/workspaces/{workspace_id}/operations/actions`
- `POST /api/v1/workspaces/{workspace_id}/operations/actions/{action_id}/approve`
- `POST /api/v1/workspaces/{workspace_id}/operations/actions/{action_id}/reject`

Requirements:

1. Approve/reject endpoints update the durable action ledger.
2. If an action created a live approval request, approval resolution must emit
   the existing `ApprovalGranted` / `ApprovalDenied` path.
3. Reject endpoint accepts an optional reason and stores it in the ledger.
4. Approve endpoint dispatches the queued work through the existing runtime /
   maintenance machinery, not by duplicating colony-spawn logic in the route.
   Access the dispatcher via `request.app.state.maintenance_dispatcher` —
   you must wire this in `app.py` (see key seams above).

The queue endpoint should support basic filtering by status.

Frontload these now:

- `status` filter
- `kind` filter
- `limit`
- aggregate counts by status and kind in the response envelope

---

## Track 6: 30-Minute Operational Sweep

The existing maintenance loop runs consolidation services + proactive dispatch
on a 24-hour default cadence (lines 892–920). The operational queue needs a
faster cadence for queue processing and status checks without disrupting
consolidation.

### Implementation

Add a **second** `asyncio.create_task` in `app.py` alongside the existing
`_maintenance_loop`. Call it `_operational_sweep_loop`. Default interval:
1800 seconds via `FORMICOS_OPS_SWEEP_INTERVAL_S` env var. Do not change
the existing 24-hour consolidation cadence.

Requirements:

1. The sweep loop checks the action queue for pending work and processes
   approved actions through the maintenance dispatcher.
   Keep the existing longer maintenance cadence for consolidation services.

2. Change maintenance behavior so proactive insights do not simply disappear:

- low-risk autonomous work may still execute immediately when policy allows
- medium/high-risk work should become queued actions
- suggest-only work should become queued actions
- explicitly skipped work should be recorded as `self_rejected` with reason

3. Queue records should carry the originating briefing signal, blast-radius
   estimate, and estimated cost.

4. Where helpful, append concise journal notes through Team A's helper.

The goal is a real detect -> queue -> review/execute -> audit loop.

## Tests

Create `tests/unit/surface/test_action_queue.py` with at least:

1. queue appends and reads action records correctly
2. status transitions (pending → approved → executed, pending → rejected)
3. approve/reject endpoints update the ledger and return structured JSON
4. `compact_action_log()` archives old entries when threshold exceeded
5. **end-to-end operational loop**: proactive insight with medium blast radius
   → queued as `pending_review` → approved via endpoint → dispatched through
   maintenance machinery → journal note written. This is the "does the
   operational loop actually loop?" test.
6. self-rejected actions are recorded with reason when suggest-only or
   blast-radius gates block dispatch

## Acceptance Gates

- [ ] `action_queue.py` exists as the canonical action ledger
- [ ] queue uses existing approval events for live gating
- [ ] action history survives restart because it is file-backed
- [ ] operator can approve/reject with a reason through endpoints
- [ ] operational sweeps run on a 30-minute default cadence
- [ ] JSONL size management prevents unbounded growth
- [ ] proactive work is queued or logged, not silently dropped
- [ ] no new event types

## Validation

```bash
pytest tests/unit/surface/test_action_queue.py -v
ruff check src/
pyright src/
python scripts/lint_imports.py
```
