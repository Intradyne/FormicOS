# Wave 75 Plan - The Economic Agent

## Goal

Turn raw FormicOS activity into economic truth.

Two halves:

- **75.0 - Economic Substrate**
  Billing, attribution, Agent Card economics, A2A contracts, receipts.
- **75.5 - Claude Code Force Multiplier**
  Make that economic truth and real knowledge retrieval available through MCP.

## Teams

### Team A: Metering, Billing, and Economic MCP

**75.0**
- build `surface/metering.py`
- add billing CLI commands to `__main__.py`
- add `GET /api/v1/billing/status`
- add the Wave 75 status note to `METERING.md`

**75.5**
- add `formicos://billing`
- add `formicos://receipt/{task_id}`
- add `economic-status`
- add `review-task-receipt`

### Team B: Attribution, Agent Card Economics, and Retrieval-backed MCP Search

**75.0**
- implement `scripts/attribution.py`
- enrich `/.well-known/agent.json` with `economics`
- add status note to `docs/CONTRIBUTOR_PAYOUT_OPS.md`

**75.5**
- add retrieval-backed `search_knowledge`
- upgrade `knowledge-for-context` and `knowledge-query` to use real retrieval
- verify `morning-status`; patch only if repo truth says it is stale

### Team C: A2A Contracts, Receipts, and Bridge Truth

**75.0**
- accept optional `contract` on `POST /a2a/tasks`
- persist contract at `.formicos/contracts/{colony_id}.json`
- generate deterministic `receipt` on `GET /a2a/tasks/{id}/result`
- add MCP `get_task_receipt`
- add status note to `docs/A2A_ECONOMICS.md`

**75.5**
- update `init-mcp` bridge template in `__main__.py`
- update `docs/DEVELOPER_BRIDGE.md`
- correct project-scoped `.mcp.json` guidance

## Merge Order

### 75.0

```text
Team A (metering) -> Team B (attribution) -> Team C (receipts)
```

All three can build in parallel. Team A should land first because it defines
the canonical fee function and billing aggregate surface.

### 75.5

```text
Team B (search) -> Team A (economic MCP) -> Team C (bridge polish)
```

Team B is independent. Team A consumes Team C's 75.0 receipt helper. Team C
finishes last so the bridge docs and generated quickstart reflect final names.

## Shared Seams

| File | Owners | Rule |
|---|---|---|
| `src/formicos/surface/mcp_server.py` | A, B, C | B owns `search_knowledge`, `knowledge-for-context`, `knowledge-query`, and tuple updates for its tool; C owns `get_task_receipt` and tuple update for its tool; A owns billing/receipt resources and economic prompts. Re-read before editing. |
| `src/formicos/__main__.py` | A, C | A owns `billing` subcommands in 75.0. C updates `_BRIDGE_TEMPLATE` / `init-mcp` wording in 75.5. |
| `docs/DEVELOPER_BRIDGE.md` | C | Single owner. |
| `METERING.md` | A | Single owner. |
| `docs/CONTRIBUTOR_PAYOUT_OPS.md` | B | Single owner. |
| `docs/A2A_ECONOMICS.md` | C | Single owner. |

## Repo Truth To Preserve

- `TokensConsumed` is at `src/formicos/core/events.py:444`
- SQLite event query is at `src/formicos/adapters/store_sqlite.py:118`
- `BudgetSnapshot.total_tokens` excludes reasoning tokens at
  `src/formicos/surface/projections.py:309`
- `knowledge_api.py:173` already exposes real `knowledge_catalog.search()`
- `knowledge-query` and `knowledge-for-context` in `mcp_server.py:948,1206`
  still use lightweight prompt-local retrieval logic
- `create_task` and `get_task_result` in `src/formicos/surface/routes/a2a.py:200,296`
  do not yet know about contracts or receipts
- `agent_card()` at `src/formicos/surface/routes/protocols.py:64` has no
  economics block yet
- `init-mcp` writes `.mcp.json` at `src/formicos/__main__.py:111-143`, while
  `docs/DEVELOPER_BRIDGE.md:22` still says `.formicos/mcp.json`

## Validation

```bash
ruff check src scripts tests
pyright src
python scripts/lint_imports.py
pytest
cd frontend && npm run build
```

## Success Criteria

1. Billing aggregates read the event store, not projections.
2. Billing totals include reasoning tokens.
3. `formicos billing status` and `formicos billing attest` work end-to-end.
4. `GET /api/v1/billing/status` returns real current-period billing data.
5. `scripts/attribution.py` deterministically computes surviving-line weights.
6. `/.well-known/agent.json` exposes an economics block with live historical stats.
7. `POST /a2a/tasks` accepts optional contracts without changing event schema.
8. `GET /a2a/tasks/{id}/result` returns a deterministic receipt for terminal tasks.
9. Claude Code can attach billing status and task receipts via MCP resources.
10. Claude Code can run a real retrieval-backed `search_knowledge` path instead of the current keyword-only prompt logic.
11. `init-mcp` and `docs/DEVELOPER_BRIDGE.md` teach the actual project-scoped MCP flow.
12. `METERING.md`, `docs/CONTRIBUTOR_PAYOUT_OPS.md`, and `docs/A2A_ECONOMICS.md` clearly mark implementation status.
