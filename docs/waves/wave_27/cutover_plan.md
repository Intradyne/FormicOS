# Wave 27 Track C — Cutover Plan

This document records the migration steps completed in Wave 27 and the
deferred execution-layer cutover planned for Wave 28+.

## Completed in Wave 27

### Route migration
- `/api/v1/knowledge` renamed to `/api/v1/knowledge-graph` (KG data only).
- `/api/v1/knowledge` freed for Track A's unified knowledge catalog.
- Frontend `knowledge-view.ts` updated to fetch from `/api/v1/knowledge-graph`.

### Legacy deprecation labeling
- `GET /api/v1/skills` response wrapped: `{ "_deprecated": "...", "skills": [...] }`.
- `GET /api/v1/memory`, `/api/v1/memory/search`, `/api/v1/memory/{id}` responses
  include `_deprecated` field pointing consumers to `/api/v1/knowledge` and
  `/api/v1/knowledge/search`.
- Queen tool `search_memory` description prefixed with `[DEPRECATED]` marker
  directing the model to use `memory_search` instead.

### What stays active
- Legacy routes remain functional for one wave (removal target: Wave 29).
- `search_memory` tool handler unchanged; only the description is updated.
- Skill bank v2 Qdrant collection and institutional memory collection both
  continue to receive writes from their respective pipelines.

## Deferred to Wave 28+

### 1. Execution-layer context cutover (`engine/context.py`)
- Replace direct `vector_store.search(collection="skill_bank_v2", ...)` calls
  with `knowledge_catalog.search(...)` so that colony context retrieval uses
  the federated catalog.
- Update pre-spawn retrieval in `queen_runtime.py` to use catalog if not
  already done by Track A.

### 2. Runner tool cutover (`engine/runner.py`)
- If runner exposes any direct skill-search tool calls, repoint them through
  the catalog layer.

### 3. Legacy crystallization shutdown
- Once the catalog is the sole read path, stop the legacy skill crystallization
  pipeline (`skill_lifecycle.py` extract + Qdrant upsert).
- New skills should be written as `MemoryEntry(entry_type="skill")` only.

### 4. Skill bank v2 bridge / migration
- Write a one-time migration script that reads all `skill_bank_v2` Qdrant
  points and creates corresponding `MemoryEntry` records in institutional
  memory, preserving confidence, source colony, and domain tags.
- After migration is verified, the `skill_bank_v2` collection becomes
  read-only, then removable.

### 5. Legacy route removal (Wave 29)
- Remove `GET /api/v1/skills` route.
- Remove `GET /api/v1/memory`, `/api/v1/memory/search`, `/api/v1/memory/{id}`.
- Remove `search_memory` Queen tool definition and handler.
- Remove `fc-skill-browser` component and its import from `knowledge-view.ts`.

### 6. Frontend component consolidation
- `knowledge-browser.ts` (Track B) becomes the sole knowledge UI surface.
- `knowledge-view.ts` retains only the graph tab (or merges into
  `knowledge-browser.ts` as a sub-view).
- Remove `memory-browser.ts` nav entry from `formicos-app.ts`.

## Risk notes
- No execution-layer behavior changes in Wave 27 — colonies continue using
  their existing retrieval and skill pipelines unchanged.
- The `_deprecated` markers are informational only; no client breaks.
- KG route rename is a breaking change for any external consumer hitting
  `/api/v1/knowledge` expecting graph data. Since there are no external
  consumers, this is acceptable.
