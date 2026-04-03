# Wave 76 Design Note: Structural Integrity

**Status:** Packet ready for dispatch
**Predecessor:** Wave 75 (A2A Economic Protocol) + Post-75 Architecture Audit
**Theme:** Every number correct, every operation safe, every identity consistent.

Wave 76 is not a feature wave. It fixes root causes discovered in the
post-75 architecture audit (54 findings, 8 Critical / 30 High / 15 Medium
/ 1 Low). Six root-cause fixes resolve ~25 individual findings.

## Already fixed (Wave 75 immediate fixes)

Five critical findings were patched before this wave:

| Finding | Fix | Files |
|---------|-----|-------|
| Knowledge extraction replay-safety gate | Guard + mark in `colony_manager.py` | `colony_manager.py:1276-1278,2412` |
| Concurrent Queen respond() races | Per-thread `asyncio.Lock` via `_respond_locks` | `queen_runtime.py:293,889-895` |
| Workflow learning `def` awaited as coroutine | Changed to `async def` | `workflow_learning.py:36,129` |
| Action queue no fsync | Added `f.flush()` + `os.fsync()` | `action_queue.py:127-129` |
| Continuation retry infinite loop | Failed-attempt counter, cap at 3 | `continuation.py:68-91` |

These are verified landed. Wave 76 does NOT re-fix them.

## Root-cause map

Six root-cause fixes resolve ~25 remaining audit findings:

| Root cause | Audit findings resolved | Est. lines |
|------------|------------------------|------------|
| `BudgetSnapshot.total_tokens` excludes reasoning | Token truth divergence across UI, MCP, billing (Audit 1.1) | ~1 |
| No agent-to-colony index on `ProjectionStore` | O(n) scans on `TokensConsumed` and `AgentTurnCompleted` (Audit 3.2, 13.3) | ~15 |
| Daily spend is in-memory only, estimate-based | Budget resets on restart, no reconciliation (Audit 2.3, 11.2) | ~40 |
| Action queue lacks safety invariants | Pending archived, no state validation, pending count hardcoded (Audit 2.2, 11.3, 11.5, 4.3) | ~50 |
| Queen context injections partially unbounded | Memory retrieval, notes, thread context crowd out conversation (Audit 8.2, 8.3) | ~15 |
| Operator-idle ignores Queen chat | Autonomous work starts while operator chats (Audit 7.1) | ~10 |

## Invariants

### 1. No new events, no new projections, no architectural redesign

Every fix works within the existing architecture:

- Event union stays at 69
- ProjectionStore keeps its public shape (agent-colony index is internal)
- Budget model stays proportional
- Action queue stays JSONL
- Changes are correctness fixes and missing guardrails

### 2. Thread identity namespacing is a forward migration

Changing file paths from `.formicos/sessions/{thread_id}.md` to
`.formicos/sessions/{workspace_id}/{thread_id}.md` requires migration.
The code checks new path first, falls back to old path on read, always
writes to new path. Existing installations migrate naturally.

### 3. Budget reconciliation is eventual, not transactional

Daily spend reconciliation reads actual colony costs after terminal state.
It does NOT block dispatch on a real-time cost check. The estimate gates
dispatch; reconciliation corrects the running total afterward.

## Team decomposition

| Team | Focus | Primary files |
|------|-------|---------------|
| A: Data Truth | Fix every wrong number | `projections.py`, `self_maintenance.py`, `continuation.py`, `colony_manager.py` (hooks), `app.py` (startup handoff only), `budget-panel.ts` |
| B: Operational Safety | Fix every unsafe operation | `action_queue.py`, `app.py`, `colony_manager.py` (run loop), `operations_coordinator.py`, `routes/api.py`, `operations-view.ts` |
| C: Context + Identity | Fix context assembly and identity model | `queen_runtime.py`, `thread_plan.py`, `queen-chat.ts`, `settings-view.ts`, `formicos-app.ts`, `queen-overview.ts` |

### Shared file analysis

- `colony_manager.py` -- Team A touches the `_post_colony_hooks` method body (~line 1131-1172), Team B touches the colony run loop before `ColonyCompleted` emission (~line 968-970). Different methods, no overlap if both teams stay inside those methods.
- `app.py` -- shared by Teams A and B. Team A needs only the dispatcher handoff at startup; Team B owns the operational sweep loop.
- `formicos-app.ts` -- Team C needs `activeWorkspaceId` pass-through props for `settings-view` (:729) and `queen-overview` (:612-638).
- `queen-overview.ts` -- Team C applies the same `tree[0]` -> `activeWorkspaceId` fix as `settings-view.ts`.

### Merge order

```
Team A (data truth)         -- first (token fix cascades everywhere)
Team B (operational safety) -- second (action queue + sweep fixes)
Team C (context + identity) -- third (context caps + path changes)
```

## What Wave 76 does NOT do

- No new event types (stays at 69)
- No projection schema changes (index is internal)
- No new Queen tools or MCP tools/resources/prompts
- No startup snapshot/checkpoint (future wave)
- No colony archival/eviction (future wave)
- No workspace-scoped project plans (future wave)
- No HTTP auth (deployment concern)

## Success condition

Wave 76 succeeds if:

1. `BudgetSnapshot.total_tokens` includes reasoning tokens everywhere
2. `TokensConsumed` and `AgentTurnCompleted` handlers are O(1) via index
3. Daily spend survives restart and reflects actual colony costs
4. Action queue compaction never archives `pending_review` items
5. Action queue rejects invalid state transitions
6. Operations dashboard shows real pending count
7. Operational sweep never re-enters
8. Colony completion paths honor pre-existing terminal killed/failed state
9. API approval and sweep execution write journal entries
10. Autonomous work does not start while operator chats with Queen
11. Memory retrieval injection respects its budget slot
12. Notes and thread context injections respect their budget slots
13. Session summaries and thread plans don't collide across workspaces
14. Queen chat messages carry the correct workspaceId
15. Settings resolves the active workspace, not `tree[0]`

