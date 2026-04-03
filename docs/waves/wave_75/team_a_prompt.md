# Wave 75 Team A - Metering, Billing, and Economic MCP

## Mission

Build the canonical economic substrate for operators:

- event-store-backed token aggregation
- one shared fee function
- billing CLI
- billing status API
- Claude-facing billing and receipt resources/prompts

This is the truth layer. If this is wrong, the rest of the wave is ornamental.

## Owned Files

- `src/formicos/surface/metering.py` - new module
- `src/formicos/__main__.py` - add `billing` subcommands only
- `src/formicos/surface/routes/api.py` - add billing status route
- `src/formicos/surface/mcp_server.py` - add economic resources/prompts only
- `METERING.md` - add implementation-status note and truth fixes if needed
- new tests under `tests/unit/surface/` and `tests/unit/` as appropriate

## Do Not Touch

- `src/formicos/surface/routes/a2a.py` - Team C
- `src/formicos/surface/routes/protocols.py` - Team B
- `docs/CONTRIBUTOR_PAYOUT_OPS.md` - Team B
- `docs/A2A_ECONOMICS.md` - Team C
- `docs/DEVELOPER_BRIDGE.md` - Team C
- `src/formicos/surface/knowledge_catalog.py` - read only
- `src/formicos/surface/task_receipts.py` - read only (Team C, you call `build_receipt()` in 75.5)
- `src/formicos/surface/projections.py` - read only
- `src/formicos/core/events.py` - read only

## Repo Truth (read before coding)

### Metering source of truth

1. `TokensConsumed` is defined at `src/formicos/core/events.py:444`.
   Current event fields are:
   - `agent_id`
   - `model`
   - `input_tokens`
   - `output_tokens`
   - `cost`
   - `reasoning_tokens`
   - `cache_read_tokens`

   There is **no** `provider` field on the event.

2. SQLite event query seam is `src/formicos/adapters/store_sqlite.py:118`:
   ```python
   async def query(address=None, event_type=None, after_seq=0, limit=1000)
   ```
   It supports sequence pagination and event-type filtering, not date filtering.
   Period filtering must happen in Python after query.

3. `BudgetSnapshot` is at `src/formicos/surface/projections.py:290`.
   The bug is real:
   - `total_reasoning_tokens` is tracked
   - `_on_tokens_consumed()` at `src/formicos/surface/projections.py:1361`
     passes reasoning tokens into `record_token_spend()`
   - but `BudgetSnapshot.total_tokens` at line 309 returns only
     `total_input_tokens + total_output_tokens`

   Do not use that property for billing.

4. `METERING.md:13-29` defines Total Tokens correctly as:
   `input + output + reasoning`
   and explicitly says cache-read tokens are informational only.

### CLI/runtime seam

5. `src/formicos/__main__.py` currently has:
   - `start`
   - `reset`
   - `export-events`
   - `init-mcp`

   No billing group exists yet.

6. `create_app()` lives at `src/formicos/surface/app.py:189`.
   It builds the full runtime and event store. The event store is created at
   `app.py:203`, attached to runtime at `app.py:372`, and exposed on
   `app.state.event_store` at `app.py:1271`.

   There is no lightweight billing bootstrap helper yet. The billing CLI
   must NOT use `create_app()` -- that starts the full runtime with
   projections, colony manager, MCP server, etc. Instead, build a minimal
   bootstrap that opens settings + event store only:

   ```python
   def _billing_bootstrap():
       """Minimal bootstrap for billing CLI -- settings + event store only."""
       from formicos.core.settings import load_settings
       from formicos.adapters.store_sqlite import SqliteEventStore
       from pathlib import Path

       settings = load_settings()
       data_dir = Path(settings.system.data_dir)
       event_store = SqliteEventStore(data_dir / "events.db")
       return settings, event_store
   ```

   `load_settings()` is at `core/settings.py` and reads from
   `config/formicos.yaml` + environment variables -- the same path
   `create_app()` uses at its start. The billing CLI needs nothing else.

### MCP seam

7. `src/formicos/surface/mcp_server.py` already exposes:
   - 28 named tools in `MCP_TOOL_NAMES` at `:24-54`
   - 9 resources at `:818,857,879,895,925,1266,1279,1293,1303`
   - 6 prompts at `:948,964,989,1084,1137,1206`
   - resource/prompt transforms activated at `:1313`
   After Wave 75: 30 tools (+search_knowledge from B, +get_task_receipt from C),
   11 resources (+billing, +receipt from you), 8 prompts (+economic-status,
   +review-task-receipt from you).

8. Billing is instance-scoped, so your billing resource should be:
   - `formicos://billing`
   not a workspace-specific URI.

## 75.0 - Metering + Billing CLI

### Track 1: New `surface/metering.py`

Create a new helper module with deterministic, pure-ish functions:

```python
async def aggregate_period(event_store, period_start, period_end) -> dict[str, Any]
def compute_fee(total_tokens: int) -> float
def compute_chain_hash(events: list[TokensConsumed]) -> str
async def generate_attestation(event_store, period_start, period_end, license_id: str) -> dict[str, Any]
```

Required behavior:

- page through `event_store.query(event_type="TokensConsumed", after_seq=N, limit=1000)`
- filter by event timestamp in Python
- compute:
  - `input_tokens`
  - `output_tokens`
  - `reasoning_tokens`
  - `cache_read_tokens`
  - `total_tokens = input + output + reasoning`
  - `event_count`
  - `first_event_seq`
  - `last_event_seq`
  - `by_model`
- `by_provider` is optional/best-effort only because the event does not carry
  provider directly. If you include it, derive it conservatively from current
  model registry/provider prefix and document it as derived, not canonical.

`compute_fee()` must be the single source of truth:

```python
round(2.00 * math.sqrt(total_tokens / 1_000_000), 2)
```

### Track 2: Billing CLI

Add a `billing` subparser group to `src/formicos/__main__.py`:

- `formicos billing status`
- `formicos billing estimate`
- `formicos billing attest --period YYYY-MM --license-id <id>`
- `formicos billing history`
- `formicos billing self-test`

Output should be readable and operator-grade. Minimum fields:

- period
- total tokens
- input/output/reasoning/cache-read breakdown
- by-model summary
- event count
- computed fee
- free-tier reminder

`history` should read attestation files from:
`.formicos/billing/attestations/`

### Track 3: Billing status API

Add:

`GET /api/v1/billing/status`

Return JSON with the same aggregate truth as the CLI. Use the event store,
not `ws.budget` / projections.

### Track 4: Attestation generation

Generate unsigned v1 attestations matching the spirit of `METERING.md`, but
be honest about repo truth:

- current event schema uses `cost`, not `cost_usd`
- current event schema does not carry `provider`

Save to:

`.formicos/billing/attestations/YYYY-MM.json`

`signature` should be `"unsigned"` in v1.

## 75.5 - Economic MCP

### Track 5: Billing and receipt resources

Add to `src/formicos/surface/mcp_server.py`:

- `@mcp.resource("formicos://billing")`
- `@mcp.resource("formicos://receipt/{task_id}")`

Both should return readable markdown, not raw JSON blobs.

`formicos://billing` should render:
- current period
- total tokens
- input/output/reasoning/cache-read breakdown
- computed fee
- note that Tier status depends on revenue, not token count alone

`formicos://receipt/{task_id}` should call Team C's receipt helper and render:
- task status
- quality
- rounds
- total tokens
- cost
- sponsor/revenue-share eligibility

### Track 6: Economic prompts

Add two read-only prompts:

- `economic-status`
- `review-task-receipt`

These should wrap the same metering/receipt truth in Claude-friendly prose.
Because prompt transforms are already active, these become slash-command-like
entry points for Claude Code automatically.

## Docs truth

Add a short status note at the top of `METERING.md`:

- implemented now: aggregate, fee computation, attestation generation, CLI
- deferred: signing, submission flow

Also correct any stale claims that contradict repo truth. In particular, do
not leave the document implying that provider is an event-native field if the
implementation derives provider best-effort.

## Tests

Add targeted coverage for:

- aggregate includes reasoning tokens
- cache-read tokens do not double-count into total tokens
- chain hash is deterministic
- fee computation matches formula
- billing status API returns current-period data
- billing resource/prompt render sensible content

Suggested files:

- `tests/unit/surface/test_metering.py`
- `tests/unit/surface/test_mcp_resources.py`
- `tests/unit/surface/test_api_billing.py`

## Validation

```bash
ruff check src tests
pyright src
python scripts/lint_imports.py
pytest tests/unit/surface/test_metering.py tests/unit/surface/test_mcp_resources.py tests/unit/surface/test_a2a_routes.py -q
```

## Acceptance

1. Billing aggregation uses the event store.
2. Total tokens include reasoning tokens.
3. `compute_fee()` is reused everywhere fee is shown.
4. `formicos billing status` works without starting the HTTP server manually.
5. `GET /api/v1/billing/status` is truthful and stable.
6. `formicos://billing` and `economic-status` are readable from Claude Code.
7. `formicos://receipt/{task_id}` and `review-task-receipt` render Team C's receipt cleanly.
