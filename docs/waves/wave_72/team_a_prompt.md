# Wave 72 - Team A: Knowledge Governance

Theme: surface knowledge quality problems in the Operations inbox, and make
document ingest visible on the active Knowledge surface.

## Read First

- `docs/waves/wave_72/wave_72_plan.md`
- `docs/waves/wave_72/design_note.md`
- `docs/waves/wave_72_polish_reference.md`
- `CLAUDE.md`

## Repo Truth You Must Start From

- The active Knowledge tab is `frontend/src/components/knowledge-browser.ts`.
- There is already a working upload/ingest flow in
  `frontend/src/components/knowledge-view.ts`, but `formicos-app.ts` does not
  render that component.
- The existing workspace ingest backend already exists in
  `src/formicos/surface/routes/colony_io.py`:
  - `POST /api/v1/workspaces/{workspace_id}/ingest`
  - `GET /api/v1/workspaces/{workspace_id}/files`
- Manual knowledge entry already exists in `knowledge-browser.ts`.
- Both addon trigger bugs are real:
  - `addons/docs-index/addon.yaml` manual trigger points at
    `indexer.py::incremental_reindex`
  - `addons/codebase-index/addon.yaml` manual trigger points at
    `indexer.py::incremental_reindex`
  - both should point to `search.py::handle_reindex`
- `knowledge_entry_usage` is a separate dict in `projections.py`; it is not
  embedded on the memory entry objects themselves.
- Team B owns `app.py` and the operational sweep call order.

## Key Seams To Read Before Coding

- `src/formicos/surface/app.py`
  Read `_operational_sweep_loop()`. Team B owns the scheduler, but your
  scanner runs from that loop.
- `src/formicos/surface/self_maintenance.py`
  Read `run_proactive_dispatch()`, `_queue_insight()`, and the blast-radius /
  autonomy helpers so your scan output matches the existing action style.
- `src/formicos/surface/action_queue.py`
  Read `create_action()`, `append_action()`, `read_actions()`,
  `update_action()`, and `list_actions()`.
- `src/formicos/surface/projections.py`
  Read `memory_entries`, `knowledge_entry_usage`, and `colony_outcomes`.
- `src/formicos/surface/routes/api.py`
  Read the existing action endpoints and knowledge CRUD endpoints.
- `src/formicos/surface/routes/knowledge_api.py`
  Read:
  - `POST /api/v1/knowledge/{entry_id}/feedback`
  - operator action endpoint for `invalidate` / `reinstate`
- `src/formicos/surface/routes/colony_io.py`
  Read `ingest_workspace_file()` and `upload_workspace_files()`.
- `frontend/src/components/operations-inbox.ts`
  Read `_kindClass()` and the current approve/reject flow.
- `frontend/src/components/knowledge-browser.ts`
  Read the active Knowledge tab rendering.
- `frontend/src/components/knowledge-view.ts`
  Read the existing `Upload & Ingest` UI and reuse it.
- `addons/docs-index/addon.yaml`
- `addons/codebase-index/addon.yaml`
- `src/formicos/addons/docs_index/search.py`
- `src/formicos/addons/codebase_index/search.py`

## Your Files

- `src/formicos/surface/knowledge_review.py` - new
- `src/formicos/surface/routes/api.py` - additive review endpoint only
- `frontend/src/components/operations-inbox.ts` - add `knowledge_review` card
- `frontend/src/components/knowledge-health-card.ts` - new
- `frontend/src/components/knowledge-browser.ts` - visible ingest/reindex flow
- `addons/docs-index/addon.yaml` - trigger fix
- `addons/codebase-index/addon.yaml` - trigger fix
- `tests/unit/surface/test_knowledge_review.py` - new

Read but do not own:

- `frontend/src/components/knowledge-view.ts`
- `src/formicos/surface/routes/colony_io.py`
- `src/formicos/surface/app.py`

## Do Not Touch

- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/queen_runtime.py`
- `frontend/src/components/settings-view.ts`
- `frontend/src/components/formicos-app.ts`
- `frontend/src/components/caste-editor.ts`

## Overlap Rules

- Team B owns the scheduler in `app.py`. You provide pure helper functions.
- Team C adds different inbox kinds in `operations-inbox.ts`. Coordinate, but
  do not reopen each other's rendering logic.
- Team C owns Settings / top-nav polish. Keep your UI work inside the active
  Knowledge tab and the inbox.

## Track 1: Knowledge Review Scanner

Create `src/formicos/surface/knowledge_review.py` with a pure scan function:

```python
async def scan_knowledge_for_review(
    data_dir: str,
    workspace_id: str,
    projections: ProjectionStore,
    *,
    briefing_insights: list[dict[str, object]] | None = None,
) -> int:
    """Queue review actions for entries that need human attention."""
```

Requirements:

- queue `kind="knowledge_review"` actions only
- use existing action queue helpers
- dedupe against existing pending review actions for the same `entry_id`
- do not mutate knowledge directly

Review criteria:

1. Outcome-correlated failures
- entry accessed by at least 3 colonies
- more than 50% of those colonies failed

2. Contradictions
- reuse existing contradiction insight logic
- do not generate a second full briefing inside the same sweep cycle
- preferred seam: Team B passes the already-generated briefing insights into
  your scanner

3. Stale authority
- high-confidence entry
- old `last_accessed`
- not `decay_class="permanent"`

4. Unconfirmed machine-generated entries
- influential entries with no operator-confirmed provenance signal

Payload should include enough detail for the inbox to explain why the entry
was flagged:

- `entry_id`
- `title`
- `content_preview`
- `review_reason`
- `confidence`
- `access_count`
- failure stats when applicable

Tests:

1. failure-correlated entry queues review action
2. contradiction insight becomes review action
3. stale authority queues review action
4. unconfirmed machine-generated entry queues review action
5. permanent entries are excluded from stale review
6. dedupe skips an existing pending review for the same entry

## Track 2: Review Processing

Add a dedicated endpoint:

`POST /api/v1/workspaces/{workspace_id}/operations/actions/{action_id}/review`

Body:

```json
{ "decision": "confirm" | "invalidate", "reason": "..." }
```

Processing rules:

- `confirm`
  Reuse the same replay-safe confidence path as
  `POST /api/v1/knowledge/{entry_id}/feedback` with positive operator feedback,
  then mark the action executed.
- `invalidate`
  Reuse the existing operator overlay invalidation path from
  `knowledge_api.py`, then mark the action executed.
- `edit`
  stays on the existing `PUT /api/v1/knowledge/{entry_id}` path from the
  Knowledge tab UI; do not invent a second edit backend.

Important:

- do not invent a brand-new raw mutation scheme if a replay-safe operator
  action already exists elsewhere
- the action queue item is the workflow wrapper, not the source of truth for
  knowledge mutation semantics

## Track 3: Inbox Rendering + Health Card

In `frontend/src/components/operations-inbox.ts`:

- add `knowledge_review` to `_kindClass()`
- add a card rendering branch for `knowledge_review`
- show:
  - entry title
  - preview
  - review reason
  - confidence
  - usage stats
  - failure stats when present
- actions:
  - `Confirm`
  - `Edit`
  - `Invalidate`

Create `frontend/src/components/knowledge-health-card.ts`.

Use real routes:

- `GET /api/v1/knowledge?workspace={id}&limit=200`
- `GET /api/v1/workspaces/{id}/operations/actions?kind=knowledge_review`

Show:

- total entries
- pending review count
- average confidence
- top domains
- stale review count
- contradiction review count

Mount the health card in `knowledge-browser.ts`, near the active Knowledge
header/search surface. Keep it compact.

## Track 4: Visible Upload And Ingest + Trigger Fix

This track is about surfacing an existing capability that is currently hidden.

Do this in `knowledge-browser.ts`:

- add an `Upload & Ingest` control by porting/reusing the existing logic from
  `knowledge-view.ts`
- add a `Refresh Library` or equivalent status refresh
- add a small reindex group:
  - `Reindex Docs`
  - `Reindex Code`
- show inline success/failure status for ingest and reindex operations

Use existing backend seams:

- `POST /api/v1/workspaces/{workspace_id}/ingest`
- `GET /api/v1/workspaces/{workspace_id}/files`
- `POST /api/v1/addons/docs-index/trigger`
- `POST /api/v1/addons/codebase-index/trigger`

Do not invent:

- a second upload pipeline
- fake addon `/status` routes
- a second knowledge-ingest backend

Fix both addon manifests:

- `addons/docs-index/addon.yaml` -> `search.py::handle_reindex`
- `addons/codebase-index/addon.yaml` -> `search.py::handle_reindex`

## Acceptance Gates

- knowledge review actions queue from the operational sweep
- contradiction reuse does not require a second full briefing pass
- review decisions use replay-safe existing knowledge mutation paths
- inbox renders `knowledge_review` cards cleanly
- knowledge health card is visible on the active Knowledge tab
- the active Knowledge tab has visible `Upload & Ingest`
- both manual addon triggers point at `handle_reindex`
- reindex controls work from the Knowledge tab

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
npm run build
```
