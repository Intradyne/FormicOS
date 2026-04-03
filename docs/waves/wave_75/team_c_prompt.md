# Wave 75 Team C - A2A Contracts, Receipts, and Bridge Truth

## Mission

Make FormicOS capable of proving completed work to external agents without
changing the event model:

- optional task contracts on submission
- deterministic receipts on result retrieval
- manual sponsor verification
- one MCP receipt tool
- truthful Claude bridge setup/docs

## Owned Files

- `src/formicos/surface/routes/a2a.py`
- `src/formicos/surface/task_receipts.py` - new helper module
- `src/formicos/surface/mcp_server.py` - `get_task_receipt` tool only
- `src/formicos/__main__.py` - update `init-mcp` quickstart/template text in 75.5
- `docs/A2A_ECONOMICS.md`
- `docs/DEVELOPER_BRIDGE.md`
- tests under `tests/unit/surface/` as needed

## Do Not Touch

- `src/formicos/surface/metering.py` - Team A
- `src/formicos/surface/routes/protocols.py` - Team B
- `docs/CONTRIBUTOR_PAYOUT_OPS.md` - Team B
- `METERING.md` - Team A
- `src/formicos/surface/knowledge_catalog.py` - read only
- `src/formicos/core/events.py` - read only

## Repo Truth (read before coding)

### Current A2A behavior

1. `create_task()` is at `src/formicos/surface/routes/a2a.py:200`.
   It currently accepts only:
   - `description`

   Then it:
   - selects a team
   - creates/uses `_DEFAULT_WORKSPACE = "default"`
   - creates a thread with `_A2A_THREAD_PREFIX = "a2a-"`
   - spawns a colony

   There is no contract intake.

2. `get_task_result()` is at `src/formicos/surface/routes/a2a.py:296`.
   It currently returns:
   - `task_id`
   - `status`
   - `output`
   - `transcript`
   - `quality_score`
   - `skills_extracted`
   - `cost`

   There is no receipt.

### Colony storage seam

3. `ColonyProjection` is at `src/formicos/surface/projections.py:351`.
   There is no generic `metadata` bag.

4. `budget_truth: BudgetSnapshot` exists on the colony at
   `src/formicos/surface/projections.py:408`.

5. `BudgetSnapshot.total_tokens` at `src/formicos/surface/projections.py:309`
   is broken -- it returns `input + output` and excludes reasoning tokens.
   Do NOT use that property.

   However, the per-field breakdown on `BudgetSnapshot` (`total_input_tokens`,
   `total_output_tokens`, `total_reasoning_tokens`) IS correct -- they are
   individually tracked from the same `TokensConsumed` events via
   `_on_tokens_consumed()` at `:1361`. Only the convenience property is wrong.

   For receipts, sum the three fields directly:

```python
total = (colony.budget_truth.total_input_tokens
         + colony.budget_truth.total_output_tokens
         + colony.budget_truth.total_reasoning_tokens)
```

### Existing economic docs

6. `docs/A2A_ECONOMICS.md` already specifies:
   - `ContributionContract` at `:59+`
   - `ContributionReceipt` at `:166+`
   - Agent Card economics at `:267+`

7. `docs/DEVELOPER_BRIDGE.md:22` is currently stale:
   it says `init-mcp` creates `.formicos/mcp.json`.
   Actual code in `src/formicos/__main__.py:111-143` writes `.mcp.json`.

8. `.formicos/DEVELOPER_QUICKSTART.md` is generated at runtime by `init-mcp`.
   It is not a repo file. Update the template in `__main__.py`, not a checked-in
   markdown file.

9. `MCP_TOOL_NAMES` is the manual MCP tool count tuple at
   `src/formicos/surface/mcp_server.py:24-53`.
   Because you are adding `get_task_receipt`, you must update the tuple as
   part of this track. You merge last in 75.0, so re-read the tuple after
   Team A and B land. Team B adds `search_knowledge` in 75.5 (after you),
   so no conflict in this phase. Add with a comment:
   ```python
   "get_task_receipt",     # Wave 75 Team C
   ```

## 75.0 - Contracts + Receipts

### Track 1: New `task_receipts.py`

Create a focused helper module, modeled after other surface helpers.

Suggested functions:

```python
def contracts_dir(data_dir: str) -> Path
def contract_path(data_dir: str, colony_id: str) -> Path
def save_contract(data_dir: str, colony_id: str, contract: dict[str, Any]) -> None
def load_contract(data_dir: str, colony_id: str) -> dict[str, Any] | None
def sponsors_path(data_dir: str) -> Path
def load_sponsors(data_dir: str) -> dict[str, Any]
def build_receipt(runtime: Runtime, colony_id: str) -> dict[str, Any] | None
```

This keeps `a2a.py` small and keeps all file-backed economics logic in one place.

### Track 2: Contract intake on `POST /a2a/tasks`

Extend request parsing to accept optional `contract`.

Rules:

- `description` is still required
- `contract` is optional
- if provided, validate minimally:
  - dict shape
  - `schema == "formicos/contribution-contract"`
  - `version == 1`
- after the colony is spawned and `colony_id` exists, save the contract to:
  `.formicos/contracts/{colony_id}.json`

Do not add new events. Do not try to persist this on projections.

### Track 3: Deterministic receipt on `GET /a2a/tasks/{id}/result`

Add a `receipt` field for terminal tasks.

Receipt requirements:

- deterministic across repeated calls
- uses stored contract if present
- uses canonical transcript hash:
  `sha256(json.dumps(transcript, sort_keys=True, separators=(",", ":")).encode())`
- uses correct token total:
  `input + output + reasoning`
- uses sponsor eligibility from `.formicos/sponsors.json`

Important detail:
do **not** generate `receipt_id` with `datetime.now()`.
Make it deterministic, e.g. from task/contract identity:

- `cr-{task_id}` or
- stable hash of `task_id + contract_id`

### Track 4: Sponsor verification

Use a simple manual registry:

`.formicos/sponsors.json`

Minimal shape can be:

```json
{
  "intradyne": { "verified": true, "cla_type": "corporate", "cla_version": "1.0" }
}
```

If the sponsor is missing or unverified:
- keep the receipt
- set `revenue_share.eligible = false`
- explain why in a note

### Track 5: MCP `get_task_receipt`

Add one new read-only tool to `src/formicos/surface/mcp_server.py`:

```python
@mcp.tool(annotations=_RO)
async def get_task_receipt(task_id: str) -> dict[str, Any]:
    ...
```

Return the structured receipt JSON. Team A will wrap the same helper in a
resource/prompt for Claude-friendly prose.

## 75.5 - Bridge Truth + Setup Polish

### Track 6: Update `init-mcp`

In `src/formicos/__main__.py`, update `_BRIDGE_TEMPLATE` so the generated
quickstart teaches the final Wave 75 affordances:

- `formicos://billing`
- `formicos://receipt/{task_id}`
- `economic-status`
- `review-task-receipt`
- `search_knowledge`

Do not change the file path behavior unless repo truth requires it.
`init-mcp` should continue writing project-scoped `.mcp.json`.

### Track 7: Update `docs/DEVELOPER_BRIDGE.md`

Fix the stale path note and add a short **Economic Participation** section:

- how to inspect billing status from Claude Code
- how to review receipts for completed work
- how revenue share works at a high level
- where CLA/sponsorship fits

Keep this developer-facing. Do not turn it into a legal doc.

### Track 8: Update `docs/A2A_ECONOMICS.md`

Add a short status note near the top:

- implemented now: contract intake, receipt generation, manual sponsor registry
- deferred: signing, automated sponsor verification, settlement automation

Do not rewrite the spec.

## Tests

Add coverage for:

- contract persistence under `.formicos/contracts/`
- receipt determinism across repeated calls
- transcript hash stability
- sponsor eligibility true/false cases
- `get_task_result()` returning `receipt`
- MCP `get_task_receipt` wrapping the same helper

Suggested files:

- `tests/unit/surface/test_a2a_routes.py`
- `tests/unit/surface/test_mcp_server.py`
- `tests/unit/surface/test_task_receipts.py`

## Validation

```bash
ruff check src tests
pyright src
python scripts/lint_imports.py
pytest tests/unit/surface/test_a2a_routes.py tests/unit/surface/test_mcp_server.py tests/unit/surface/test_task_receipts.py -q
```

## Acceptance

1. A2A task submission accepts optional contracts without event changes.
2. Contracts survive restart because they are file-backed.
3. Receipts are deterministic.
4. Receipt token totals include reasoning tokens.
5. Sponsor verification is explicit and honest.
6. Claude bridge docs and generated quickstart teach the real project-scoped MCP flow.
