# Wave 75 Team B - Attribution, Agent Card Economics, and Retrieval-backed MCP Search

## Mission

Make FormicOS economically legible to contributors and externally legible to
Claude Code:

- contributors can verify attribution from git history
- the Agent Card publishes economic terms and live historical stats
- Claude Code gets a real retrieval-backed knowledge search path instead of the
  current keyword-only prompt heuristic

## Owned Files

- `scripts/attribution.py` - new standalone script
- `src/formicos/surface/routes/protocols.py` - Agent Card economics block
- `src/formicos/surface/mcp_server.py` - `search_knowledge` tool, retrieval-backed `knowledge-for-context` and `knowledge-query`
- `docs/CONTRIBUTOR_PAYOUT_OPS.md` - implementation-status note
- tests under `tests/unit/surface/` and `tests/unit/` as needed

## Do Not Touch

- `src/formicos/surface/routes/a2a.py` - Team C
- `src/formicos/surface/metering.py` - Team A
- `METERING.md` - Team A
- `docs/A2A_ECONOMICS.md` - Team C
- `docs/DEVELOPER_BRIDGE.md` - Team C
- `src/formicos/surface/knowledge_catalog.py` - read only

## Repo Truth (read before coding)

### Attribution source

1. `docs/CONTRIBUTOR_PAYOUT_OPS.md:44-52` explicitly says the attribution
   script is still "to be implemented".

2. The documented formula is:
   - `git blame -w --line-porcelain`
   - ignore revs file
   - exclude whitespace-only lines
   - maintainer floor 50%
   - minimum payout threshold $25

3. This script should stay standalone. Do not import FormicOS runtime code.

### Agent Card current state

4. `agent_card()` is in `src/formicos/surface/routes/protocols.py:64`.
   It currently returns:
   - capabilities
   - protocols
   - skills
   - knowledge stats
   - thread count
   - external specialists
   - federation
   - hardware

   There is no `economics` block yet.

5. `docs/A2A_ECONOMICS.md:267-301` already specifies the desired economics
   shape for the Agent Card, including:
   - `contract_schema`
   - `receipt_schema`
   - `compensation_summary`
   - `sponsorship_required`
   - `historical_stats`

### Historical-stats seam

6. `projections.colony_outcomes` exists at
   `src/formicos/surface/projections.py:703`.
   `ColonyOutcome` is defined at `:90`.

7. Important repo truth:
   `ColonyOutcome` does **not** carry a completion timestamp.
   If you want "last 30 days" stats, join `colony_outcomes[colony_id]` with
   `projections.colonies[colony_id].completed_at`.

### Current Claude-facing knowledge path

8. `knowledge-for-context` in `src/formicos/surface/mcp_server.py:1206`
   currently performs a naive keyword scan over `runtime.projections.memory_entries`.
   It does not use:
   - `knowledge_catalog.search()`
   - thread boost
   - Thompson sampling
   - graph proximity
   - real retrieval ranking

9. The real search seam already exists:
   `src/formicos/surface/routes/knowledge_api.py:173` calls
   `knowledge_catalog.search(...)`.
   Avoid self-HTTP calls; use `runtime.knowledge_catalog.search()` directly.

10. `MCP_TOOL_NAMES` is the manual MCP tool count tuple at
    `src/formicos/surface/mcp_server.py:24-53`.
    Because you are adding `search_knowledge`, you must update the tuple as
    part of this track. Team C is also adding `get_task_receipt` in 75.0
    (before your 75.5 merge). After Team C's 75.0 lands, re-read the tuple
    before adding your entry. Add with a comment:
    ```python
    "search_knowledge",     # Wave 75 Team B
    ```

## 75.0 - Attribution + Agent Card Economics

### Track 1: `scripts/attribution.py`

Build a deterministic standalone script with flags like:

```bash
python scripts/attribution.py ^
  --repo . ^
  --branch main ^
  --revenue 1250.00 ^
  --maintainer-floor 0.50 ^
  --min-payout 25.00 ^
  --ignore-revs .git-blame-ignore-revs ^
  --aliases .formicos/email-aliases.json ^
  --output reports/attribution-2026-Q2.json
```

Requirements:

- run `git blame -w --line-porcelain`
- cover `src/`, `frontend/src/`, `config/`, `addons/`
- ignore whitespace-only lines
- apply email aliases if the aliases file exists
- compute gross percentages from surviving lines
- apply maintainer floor cleanly and transparently
- mark below-threshold contributors without losing accrued truth
- output both JSON and human-readable stdout

Structure the script around small pure helpers so it is testable.

### Track 2: Agent Card economics block

Add `economics` to `/.well-known/agent.json` in `routes/protocols.py`.

Match the intent of `docs/A2A_ECONOMICS.md:267-301`, but keep values honest:

- `contract_schema`: `formicos/contribution-contract@1`
- `receipt_schema`: `formicos/contribution-receipt@1`
- `compensation_model`: `revenue_share_pool`
- `compensation_summary`
- `sponsorship_required`: `true`
- `accepted_cla_versions`: `["1.0"]`
- `licensing` block
- `historical_stats`

`historical_stats` should include:

- `tasks_completed_30d`
- `acceptance_rate_30d`
- `median_quality_score_30d`
- `median_cost_usd_30d`

Use `projections.colony_outcomes` joined to `projections.colonies` for the
30-day window. Do not fake the window with all-time data.

Repo-truth note: there is no separate human acceptance ledger today, so
`acceptance_rate_30d` in v1 should be the share of terminal colonies in the
30-day window that completed successfully.

### Track 3: Ops doc status note

Add a short status note to the top of `docs/CONTRIBUTOR_PAYOUT_OPS.md`:

- implemented now: attribution script
- still operational/manual: payout execution, Stripe Connect setup, tax ops

Do not rewrite the whole document.

## 75.5 - Retrieval-backed Claude Search

### Track 4: `search_knowledge` MCP tool

Add one new high-value tool to `src/formicos/surface/mcp_server.py`:

```python
@mcp.tool(annotations=_RO)
async def search_knowledge(query: str, workspace_id: str = "", top_k: int = 5) -> str:
    ...
```

Requirements:

- use the real retrieval pipeline via `runtime.knowledge_catalog.search()`
- default `workspace_id` to the first workspace if omitted
- cap `top_k` reasonably (5-8)
- render markdown/prose, not raw JSON
- surface title, short content snippet, confidence, status, and domains/provenance where available

This is the one new tool in the wave because queryable search is inherently
tool-shaped.

### Track 5: Upgrade `knowledge-for-context` and `knowledge-query`

Replace the current naive keyword-scoring implementation with the same real
retrieval path.

Keep the UX the same:
- query in
- Claude-ready markdown out

But stop scanning `runtime.projections.memory_entries` directly.
Apply the same truth fix to the older `knowledge-query` prompt at
`mcp_server.py:948` so both knowledge prompts reflect the real retrieval path.

### Track 6: Verify `morning-status`

Read the existing prompt at `mcp_server.py:989`.

If it is still repo-true after Wave 74/72.5, leave it alone.
If it is stale or visibly broken, patch only the stale bits. Do not rewrite it
for style.

## Tests

Add bounded coverage for:

- attribution alias handling
- whitespace-line exclusion
- maintainer floor math
- Agent Card economics block shape
- retrieval-backed MCP search returning ranked results
- upgraded `knowledge-for-context` and `knowledge-query` using real retrieval

Suggested files:

- `tests/unit/test_attribution.py`
- `tests/unit/surface/test_mcp_server.py`
- `tests/unit/surface/test_mcp_resources.py`

## Validation

```bash
ruff check src scripts tests
pyright src
python scripts/lint_imports.py
pytest tests/unit/test_attribution.py tests/unit/surface/test_mcp_server.py tests/unit/surface/test_knowledge_api_filters.py -q
```

## Acceptance

1. `scripts/attribution.py` is deterministic and public-verifiable.
2. Agent Card economics block matches live repo truth.
3. Historical stats really are 30-day stats, not all-time approximations.
4. `search_knowledge` uses the real retrieval pipeline.
5. `knowledge-for-context` and `knowledge-query` no longer do naive keyword scanning.
6. `MCP_TOOL_NAMES` reflects the added `search_knowledge` tool.
7. Claude Code gets a materially better institutional-memory bridge after this wave.
