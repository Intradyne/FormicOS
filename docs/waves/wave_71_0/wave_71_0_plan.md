# Wave 71.0: Operational Coherence Substrate

**Status:** Dispatch-ready packet
**Predecessor:** Wave 70.5
**Theme:** Give the Queen durable working memory, a real asynchronous action
loop, and a coherent cross-artifact model of what is in flight.

## Packet Authority

Use these docs:

- `docs/waves/wave_71_0/design_note.md`
- `docs/waves/wave_71_0/team_a_prompt.md`
- `docs/waves/wave_71_0/team_b_prompt.md`
- `docs/waves/wave_71_0/team_c_prompt.md`

## Locked Boundaries

- No new event types.
- Do not add new projection fields unless an existing surface is impossible
  without one.
- Keep operational state out of `memory_entries`.
- Reuse the existing approval event path for live gating.
- Land stable backend seams so `71.5` is mostly frontend work.

## Scope

| Track | Outcome | Team |
|------|---------|------|
| 1 | Shared operational-state helper + file layout | A |
| 2 | Queen journal + operating procedures + budgeted injection | A |
| 3 | Budget rebalance (7 → 9 slots) + journal/procedures endpoints | A |
| 4 | Durable action queue ledger | B |
| 5 | Approval-backed operator review endpoints | B |
| 6 | 30-minute operational sweeps on top of maintenance loop | B |
| 7 | Shared thread-plan helper | C |
| 8 | Operations coordinator (cross-artifact synthesis) | C |
| 9 | Operations summary endpoint + compact Queen continuity cue | C |

## Team Missions

### Team A - Operational Memory

Own the new operational artifacts:

- journal
- operating procedures
- helper functions and endpoints for reading/editing them
- Queen context injection for multi-day continuity

### Team B - Action Loop

Own the asynchronous action cycle:

- queue proposed actions durably through a generic typed action envelope
- route approvals through the existing governance path
- turn periodic proactive sweeps into queued/executed/rejected work

### Team C - Coherence Coordinator

Own the synthesis layer:

- inspect project plan, thread plans, session summaries, outcomes, and queue
- identify continuation candidates and sync issues
- give both the Queen and `71.5` a compact operational summary, including
  operator-idle truth

## Merge Order

Recommended merge order:

1. Team A
2. Team B
3. Team C

Why:

- Team A defines the new operational file layer and context budget seams.
- Team B builds on that layer for the durable action queue.
- Team C synthesizes across the new queue plus the existing plan/session
  artifacts.

## Shared Seams

- `src/formicos/surface/routes/api.py` is shared by all three teams:
  additive endpoint sections only. Workspace endpoints live at lines
  1717–1826. New `/operations/...` endpoints should go after the forager
  block (line 1769) and before the Knowledge CRUD block (line 1771).
- `src/formicos/surface/queen_runtime.py` is shared by Teams A and C.
  `respond()` starts at line 859. Current injection order in `respond()`:
  memory retrieval (895–929), project context (931–953), project plan
  (955–980), session summary (982–1010, **hardcoded `[:4000]` at line 993**),
  thread context (1012–1023), briefing (1025–1094), deliberation frame
  (1096–1119). Team A owns procedures/journal injection (insert after
  project plan, before session summary — lines 980–982). Team C owns
  a compact continuity-summary block (insert after briefing, before
  deliberation — lines 1094–1096). Team A also fixes session summary to use
  budget instead of the hardcoded cap.
- `src/formicos/surface/app.py` is Team B only in this packet.
  `_maint_dispatcher` is currently a local variable in the lifespan closure
  (line 885), **not** on `app.state` or `runtime`. Team B must wire it to
  `app.state.maintenance_dispatcher` so approve/reject routes can dispatch.
  Maintenance loop is at lines 892–920 with a 24-hour default interval
  (line 889: `FORMICOS_MAINTENANCE_INTERVAL_S`).
- `src/formicos/surface/queen_budget.py` and `docs/decisions/051-dynamic-context-caps.md`
  are Team A only in this packet. Current 7 slots and fractions at lines
  24–32; `QueenContextBudget` frozen dataclass at line 45.

## Out Of Scope

- knowledge review queue
- workflow template extraction
- full autonomous "resume work without asking" behavior
- new nav or polished UI surface

Those are natural follow-ons once this packet lands.

## Acceptance Focus

- operational artifacts have one canonical file layout
- procedures and journal are injected into Queen context explicitly
- session-summary injection no longer relies on a hardcoded 4000-char cap
- medium/high-risk proactive work enters a durable queue instead of vanishing
  into logs
- action queue is generic enough for future action kinds without schema churn
- operator approval/rejection can carry a reason and survive restarts
- continuation candidates come from real artifacts, not prompt-only heuristics
- operations summary exposes last-operator-activity / idle signals for later
  continuation work
- `71.5` can render the operational loop from endpoints instead of scraping
  markdown or runtime internals

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

## Success Condition

Wave 71.0 succeeds if the Queen can answer, deterministically and durably:

- what we were doing
- what is waiting on the operator
- what I should do next
- what standing procedures I should follow
