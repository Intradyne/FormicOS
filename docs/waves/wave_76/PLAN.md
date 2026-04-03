# Wave 76 Plan: Structural Integrity

**Theme:** Root-cause correctness fixes from the post-75 architecture audit.
**Teams:** 3 parallel tracks, sequential merge.
**Estimated total change:** ~200 lines of production code + ~100 lines of tests.

## Pre-dispatch checklist

- [x] Architecture audit read in full (`docs/waves/architecture_audit_post_75.md`)
- [x] All 5 Wave 75 immediate fixes verified landed
- [x] Every line number verified against live codebase (2026-03-28)
- [x] No ADR conflicts (no new events, no layer violations)
- [x] Shared-file ownership boundaries confirmed (`colony_manager.py`, `app.py`, and Team C pass-through shell files called out explicitly)

## Team A: Data Truth

Fix every place where the system computes or displays a wrong number.

| Track | Summary | Files | Lines |
|-------|---------|-------|-------|
| 1 | Fix projection and UI token totals to include reasoning | `projections.py:309-310`, `frontend/src/components/budget-panel.ts:178-180` | ~5 |
| 2 | Agent-to-colony reverse index for O(1) lookup | `projections.py` (init, handlers) | ~20 |
| 3 | Budget reconciliation from actual colony costs | `self_maintenance.py`, `continuation.py`, `colony_manager.py:1131-1172`, `app.py` (startup handoff) | ~40 |
| 4 | Daily spend persistence to disk | `self_maintenance.py`, `continuation.py` | ~25 |

**Merge first.** Token fix cascades to every UI/MCP/billing consumer.

## Team B: Operational Safety

Fix every path where the operational loop can lose data or violate invariants.

| Track | Summary | Files | Lines |
|-------|---------|-------|-------|
| 5 | Action queue compaction preserves pending items | `action_queue.py:249-285` | ~15 |
| 6 | Action queue state transition validation | `action_queue.py:152-173` | ~20 |
| 7 | Operations dashboard real pending count | `operations-view.ts:189` | ~15 |
| 8 | Sweep reentrancy guard | `app.py:929-944` | ~10 |
| 9 | Colony kill/completion race guard | `colony_manager.py:968-975` | ~5 |
| 10 | Journal coverage for API and sweep approved actions | `routes/api.py:1846-1876`, `app.py:1021-1095` | ~15 |
| 11 | Operator-idle includes Queen chat | `operations_coordinator.py:211-257` | ~15 |

**Merge second.**

## Team C: Context Integrity + Identity Coherence

Fix Queen context assembly and workspace identity model.

| Track | Summary | Files | Lines |
|-------|---------|-------|-------|
| 12 | Budget-cap memory retrieval injection | `queen_runtime.py:954-972` | ~1 |
| 13 | Budget-cap notes and thread context injections | `queen_runtime.py:1849-1871,1119-1130` | ~5 |
| 14 | Thread file path namespacing (sessions + plans + plan loader) | `queen_runtime.py:852-856,2068-2075`, `thread_plan.py:36-38,138-161` | ~30 |
| 15 | Queen chat workspace propagation | `queen-chat.ts:466,475,501,611` | ~10 |
| 16 | Settings workspace resolution | `settings-view.ts:241,403,439`, `formicos-app.ts:729`, `queen-overview.ts:195-200` | ~15 |

**Merge third.**

## Validation

Each team runs the full CI before declaring done:

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Post-merge integration check: verify that `BudgetSnapshot.total_tokens`
consumers in UI, MCP, and billing all agree by tracing `total_tokens`
through `budget-panel.ts`, `mcp_server.py` receipt/billing resources,
and `metering.py`.
