# Wave 75 Design Note - The Economic Agent

## Purpose

Wave 75 gives FormicOS an economic substrate that is honest, deterministic,
and useful from both sides of the bridge:

- operators can see what the system costs,
- contributors can verify how attribution would be computed,
- external agents can receive structured receipts for completed work,
- Claude Code can read that economic state through MCP without opening the UI.

This wave is split into two halves:

- **75.0** builds the economic substrate
- **75.5** makes that substrate Claude-legible

## Invariants

### 1. Billing reads the event store, not projections

`TokensConsumed` is the source of truth at
`src/formicos/core/events.py:444`. The query seam is
`src/formicos/adapters/store_sqlite.py:118`.

Do **not** bill from `BudgetSnapshot.total_tokens` at
`src/formicos/surface/projections.py:309`. That property currently returns
`input + output` and excludes reasoning tokens, while `METERING.md:13-17`
defines Total Tokens as:

`input_tokens + output_tokens + reasoning_tokens`

The projections layer is useful for live UI truth. It is not the canonical
billing source.

### 2. Billing is instance-scoped

The commercial formula in `LICENSE:117-146` applies to total metered runtime
usage for the billing period, not to a single workspace. Wave 75 therefore
adds:

- `GET /api/v1/billing/status`
- `formicos://billing`

not a workspace-scoped billing contract.

Workspace filtering can be added later as an informational view, but it is not
the legal billing primitive.

### 3. No new event types

Economic persistence in this wave is file-backed or replay-derived:

- task contracts live at `.formicos/contracts/{colony_id}.json`
- sponsor verification reads `.formicos/sponsors.json`
- receipts are computed on demand from existing colony state
- billing attestations are derived from the append-only event log

No new event types, no replay-safety burden, no second source of truth.

### 4. Economic artifacts are deterministic

The same underlying state must always produce the same artifact:

- same event-store slice -> same billing aggregate and attestation
- same git history -> same attribution report
- same colony outcome + same stored contract -> same receipt

No LLM calls, no randomness, no external APIs in the computation path.

### 5. Unsigned is the right v1

Wave 75 ships the computation, not the crypto ceremony.

- Attestations may compute a chain hash and mark `signature: "unsigned"`
- Receipts may include deterministic hashes and `attestation: { "signature": "unsigned" }`

Ed25519 signing and submission flow stay deferred until there is an actual
licensee or external integration that needs non-repudiation.

### 6. Claude-legible means resources, prompts, and one real search tool

Claude Code is most useful when FormicOS exposes:

- attachable context via MCP resources
- readable workflows via MCP prompts
- a small number of high-value tools where tool-shape is actually correct

Wave 75 therefore adds:

- billing and receipt resources
- economic review prompts
- one real retrieval-backed `search_knowledge` tool

It does **not** try to turn every economic operation into another generic tool.

### 7. Status notes are part of the product

The economic docs in the repo are already strong, but they currently describe
more than the code implements. Wave 75 must leave the root/docs packet in an
honest state:

- `METERING.md`
- `docs/CONTRIBUTOR_PAYOUT_OPS.md`
- `docs/A2A_ECONOMICS.md`

Each needs a short "implemented vs specified" note after this wave.

## What Wave 75 does NOT do

- No Ed25519 key derivation, signing, or verification pipeline
- No billing submission endpoint or `formicos billing submit`
- No Stripe Connect automation
- No GitHub CLA app / automated sponsor verification
- No execution-weighted attribution
- No new event types
- No replacement of Claude Code's direct edit loop

## Pre / Post State

| Surface | Before 75 | After 75 |
|---|---|---|
| Billing truth | Spec only | Event-store-backed aggregate + fee computation |
| Billing CLI | None | `billing status/estimate/attest/history/self-test` |
| Billing API | None | `GET /api/v1/billing/status` |
| Attribution | Ops doc only | Deterministic `scripts/attribution.py` |
| Agent Card economics | None | Economics block + historical stats |
| A2A contract intake | None | Optional file-backed contract |
| A2A result receipt | None | Deterministic structured receipt |
| Claude economic context | Browser/docs only | MCP billing + receipt resources/prompts |
| Claude knowledge retrieval | Prompt-local keyword scan | Real retrieval-backed search path |
| MCP tool count | 28 | 30 (+search_knowledge, +get_task_receipt) |
| MCP resource count | 9 | 11 (+formicos://billing, +formicos://receipt/{task_id}) |
| MCP prompt count | 6 | 8 (+economic-status, +review-task-receipt) |
