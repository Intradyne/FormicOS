# Wave 27 Plan -- Unified Knowledge Workflow

**Wave:** 27 -- "Unified Knowledge Workflow"
**Theme:** The operator, the Queen, and the API all see one canonical knowledge surface. Legacy skills and institutional memory remain separate storage backends, but the system presents, searches, and navigates them as one unified knowledge catalog. The interface stabilizes before the internals migrate.
**Architectural thesis:** Unify how knowledge is presented, searched, and understood -- not how it is stored or executed.
**Contract changes:** No core type, event, or port changes. Event union stays at 40. Surface API changes are intentional: `/api/v1/knowledge` is reclaimed from the KG for the unified catalog (KG moves to `/api/v1/knowledge-graph`), `/api/v1/skills` response shape changes to include deprecation wrapper. No external consumers exist.
**Estimated LOC delta:** ~400 Python, ~350 TypeScript (net, after removing old components)

---

## Why This Wave

Post-Wave 26, FormicOS has two knowledge systems that the operator, the Queen, and agents see differently:

- Legacy skills live in `skill_bank_v2` (Qdrant), flow through `context.py` for agent retrieval, `skill_lifecycle.py` for confidence updates, and `skill-browser.ts` (inside `knowledge-view.ts`) for operator inspection
- Institutional memory lives in `institutional_memory` (Qdrant), flows through `memory_store.py` for Queen retrieval, `memory_scanner.py` for validation, and `memory-browser.ts` for operator inspection
- The Queen has both legacy `search_memory` and new `memory_search` tools in `queen_runtime.py`
- The operator has two separate tabs: "Knowledge" (KG + legacy skills) and "Memory" (institutional)

This is a cognitive fragmentation problem. The operator cannot answer "what does the system know about X?" without checking two places. The Queen searches two different backends with different semantics. The API surface has `/api/v1/skills` and `/api/v1/memory` serving overlapping concepts.

Wave 27 solves this by creating one canonical read surface without touching the execution layer. The principle: **do not change how skills work yet; change how knowledge is surfaced and navigated.**

---

## Critical Design Decisions

### D1. Federated read facade, not storage migration

Wave 27 introduces a `knowledge_catalog.py` module that federates reads from both backends into one normalized shape. This is a read-only aggregation layer in `surface/`. It does not write to either store. It does not replace either store. It normalizes results into a common contract so consumers (API, UI, Queen) can search and browse without knowing which backend answered.

### D2. Explicit source labeling, not silent merging

Every knowledge item in the unified surface carries a `source_system` field: `"legacy_skill_bank"` or `"institutional_memory"`. The operator always knows provenance. Legacy-migrated items are visually distinguished, not silently blended.

### D3. No execution-layer changes

Wave 27 explicitly does not touch:
- `engine/context.py` (agent context injection still reads `skill_bank_v2`)
- `engine/runner.py` (agent `memory_search` tool still uses scratch/workspace/skill_bank)
- `surface/skill_lifecycle.py` (legacy confidence updates stay active)
- `surface/colony_manager.py` `_crystallize_skills()` (legacy writes stay active)

These are Wave 28 cutover tasks, after the unified surface has proven stable.

### D4. One operator-facing knowledge view

The current split between `knowledge-view.ts` (KG + legacy skills) and `memory-browser.ts` (institutional memory) is replaced by a single `knowledge-browser.ts`. The KG visualization component stays separate (it's a different data structure) and its API endpoints move from `/api/v1/knowledge` to `/api/v1/knowledge-graph`. The KG viewer becomes accessible from within the unified knowledge browser as a "Graph" sub-tab, not as its own top-level concept.

### D6. KG route migration

The existing `/api/v1/knowledge` endpoint (which serves KG entities/edges) moves to `/api/v1/knowledge-graph`. This is a simple route rename in `routes/api.py`. The `knowledge-view.ts` component is updated to fetch from the new path. Since no external consumers exist, this is a clean rename with no compatibility cost.

### D5. Queen search unification through the catalog

The Queen's `memory_search` tool is repointed to search via the knowledge catalog (which federates both backends). The legacy `search_memory` tool (which queries `skill_bank_v2` directly) is deprecated but kept for one wave as a fallback. In the Queen's tool list, `memory_search` becomes the canonical search tool and its description is updated to reflect "searches all system knowledge."

This is the one place Wave 27 changes Queen behavior -- but it's purely a read-path change through a facade, not a storage migration.

---

## The Knowledge Item Contract (Surface Layer)

This is a read-only surface contract consumed by the API and frontend. It lives in `surface/knowledge_catalog.py`, not in `core/types.py`. No event changes.

```python
@dataclass(frozen=True)
class KnowledgeItem:
    """Normalized read model for unified knowledge display."""
    id: str
    canonical_type: str           # "skill" | "experience"
    source_system: str            # "legacy_skill_bank" | "institutional_memory"
    status: str                   # "verified" | "candidate" | "rejected" | "stale" | "active" (legacy)
    confidence: float
    title: str
    summary: str
    content_preview: str          # first 500 chars
    source_colony_id: str
    source_artifact_ids: list[str]
    domains: list[str]
    tool_refs: list[str]
    created_at: str
    polarity: str                 # "positive" | "negative" | "neutral"
    legacy_metadata: dict[str, Any]  # alpha/beta/merge_count for legacy skills
```

Legacy skill entries are normalized into this shape:
- `canonical_type` = `"skill"` (always)
- `source_system` = `"legacy_skill_bank"`
- `status` = `"active"` (legacy skills don't have candidate/verified lifecycle)
- `title` = skill technique (from metadata)
- `summary` = when_to_use (from metadata)
- `content_preview` = first 500 chars of embedded text
- `source_colony_id` = from metadata `source_colony` or `source_colony_id`
- `source_artifact_ids` = `[]` (legacy skills predate artifact model)
- `polarity` = `"positive"` (legacy skills are always positive)
- `legacy_metadata` = `{conf_alpha, conf_beta, merge_count, algorithm_version}`

---

## Tracks

### Track A -- Knowledge Catalog Layer

**Goal:** A federated read facade in `surface/` that normalizes both knowledge backends into one searchable, browsable surface contract. Plus a REST API that replaces the need for separate `/skills` and `/memory` endpoints.

**A1. Knowledge catalog module.**

New `surface/knowledge_catalog.py` (~120 LOC). Federates reads:
- Queries institutional memory via `memory_store.search()`
- Queries legacy skill bank via `vector_port.search()` on `skill_bank_v2`
- Normalizes both into `KnowledgeItem` shape
- Merges, deduplicates by ID, and sorts by composite relevance

```python
class KnowledgeCatalog:
    def __init__(
        self,
        memory_store: MemoryStore | None,
        vector_port: VectorPort | None,
        skill_collection: str,
        projections: ProjectionStore,
    ) -> None: ...

    async def search(
        self, query: str, *,
        source_system: str = "",    # filter: "legacy_skill_bank" | "institutional_memory" | ""
        canonical_type: str = "",   # filter: "skill" | "experience" | ""
        workspace_id: str = "",
        top_k: int = 10,
    ) -> list[dict[str, Any]]: ...

    async def list_all(
        self, *,
        source_system: str = "",
        canonical_type: str = "",
        workspace_id: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]: ...

    async def get_by_id(self, item_id: str) -> dict[str, Any] | None: ...
```

The `search()` method runs both backends in parallel (`asyncio.gather`), normalizes results, merges, and returns sorted by composite score. If one backend is unavailable, the other still returns results.

The `list_all()` method combines projection-state listing from both systems (institutional `memory_entries` dict + legacy skill bank via vector search with empty query or list operation).

Files touched: `src/formicos/surface/knowledge_catalog.py` -- new (~120 LOC)

**A2. Knowledge REST API.**

New `surface/routes/knowledge_api.py` (~100 LOC). The canonical operator/search surface:

- `GET /api/v1/knowledge` -- list all knowledge items with filters (source_system, type, workspace, limit)
- `GET /api/v1/knowledge/search?q=...` -- federated search across both backends
- `GET /api/v1/knowledge/{id}` -- single item detail. Guaranteed for institutional memory entries (direct projection lookup by ID). Best-effort for legacy skills (semantic search fallback; may not find the exact entry by UUID). Legacy detail is a convenience, not a contract -- the unified browser's primary value is list and search, not by-id detail for legacy items.

These endpoints replace the current `/api/v1/knowledge` route (which previously served the knowledge graph). The KG endpoints move to `/api/v1/knowledge-graph`. The existing `/api/v1/skills` and `/api/v1/memory` endpoints gain `_deprecated` fields pointing to the new surface.

Files touched:
- `src/formicos/surface/routes/knowledge_api.py` -- new (~100 LOC)
- `src/formicos/surface/routes/__init__.py` -- wire new routes (~3 LOC)
- `src/formicos/surface/app.py` -- wire catalog + routes into lifespan (~10 LOC)

**A3. Queen search repoint.**

Repoint the Queen's `memory_search` tool handler (`_tool_memory_search` in `queen_runtime.py`) to search via `knowledge_catalog.search()` instead of `memory_store.search()` directly. Update the tool description to "Search all system knowledge (skills and experiences)."

The legacy `search_memory` tool (which calls `get_skill_bank_summary`) stays but its description is updated to note it's deprecated in favor of `memory_search`.

Pre-spawn retrieval (`retrieve_relevant_memory` in `runtime.py`) is also repointed to use the catalog, so the Queen sees both legacy skills and institutional entries before spawning.

Files touched:
- `src/formicos/surface/queen_runtime.py` -- repoint tool handler + description (~15 LOC changed)
- `src/formicos/surface/runtime.py` -- repoint pre-spawn retrieval to catalog (~10 LOC changed)

| File | Action |
|------|--------|
| `src/formicos/surface/knowledge_catalog.py` | New -- federated read facade |
| `src/formicos/surface/routes/knowledge_api.py` | New -- unified REST API |
| `src/formicos/surface/routes/__init__.py` | Wire new routes |
| `src/formicos/surface/app.py` | Wire catalog into lifespan |
| `src/formicos/surface/queen_runtime.py` | Repoint memory_search to catalog |
| `src/formicos/surface/runtime.py` | Repoint pre-spawn retrieval to catalog |

Do not touch:
- `src/formicos/core/*`
- `src/formicos/engine/*`
- `src/formicos/surface/skill_lifecycle.py`
- `src/formicos/surface/colony_manager.py`
- `src/formicos/surface/memory_store.py`
- `src/formicos/surface/memory_extractor.py`
- `src/formicos/surface/memory_scanner.py`
- `src/formicos/adapters/*`
- `frontend/*`

---

### Track B -- Unified Knowledge UX

**Goal:** One operator-facing knowledge browser replaces the current split between the skill browser and memory browser. The operator answers "what does the system know?" in one place.

**B1. Unified knowledge browser component.**

New `frontend/src/components/knowledge-browser.ts` (~300 LOC). Replaces both `skill-browser.ts` (inside `knowledge-view.ts`) and `memory-browser.ts` for the knowledge-browsing use case.

Features:
- One search box hitting `/api/v1/knowledge/search`
- Filter pills: `All` | `Legacy Skills` | `Institutional Skills` | `Experiences`
- Sort: `Newest` | `Confidence` | `Relevance` (when searching)
- Source badge on every item: `Legacy Skill` (amber) | `Institutional` (green)
- Type pill: `skill` | `experience`
- Status badge: `verified` | `candidate` | `active` (legacy)
- Polarity indicator for experiences (positive/negative/neutral)
- Confidence bar
- Provenance: source colony link, source artifact IDs (when available), scan status (when institutional)
- Detail expansion: full content, domains, tool refs, legacy metadata (alpha/beta when available)
- `sourceColonyId` prop for filtered views from colony detail

Does NOT include the KG graph visualization inline. Instead, the unified browser includes a "Graph" button or sub-tab that renders the existing `fc-knowledge-view` component (which Track C updates to use `/api/v1/knowledge-graph`). This is how acceptance criterion 10 ("KG visualization still accessible") is satisfied.

Files touched: `frontend/src/components/knowledge-browser.ts` -- new (~300 LOC)

**B2. KG access wiring inside the unified browser.**

The unified `knowledge-browser.ts` includes a toggle or sub-tab that renders the existing `fc-knowledge-view` component in **graph-only mode**. When the "Knowledge" nav tab is active and the operator clicks "Graph," the browser swaps to a KG-only rendering with no nested "skills / graph / library" tabs visible.

To make this explicit and safe, Track B also owns a tiny additive shim in `knowledge-view.ts`:
- add `graphOnly: boolean = false`
- optionally add `initialTab: 'skills' | 'graph' | 'library' = 'skills'`
- when `graphOnly` is true:
  - default to the graph tab
  - hide the internal tab row
  - do not render the legacy skill-browser section
  - do not render the library section

This avoids reintroducing the old split UX inside the new unified browser while preserving `fc-knowledge-view` for direct reuse.

Files touched:
- `frontend/src/components/knowledge-browser.ts` -- already counted in B1 (~20 LOC of the ~300 total)
- `frontend/src/components/knowledge-view.ts` -- small additive graph-only shim (~15 LOC)

**B3. Nav restructure.**

Current nav: Queen | Knowledge | Memory | Playbook | Models | Settings

New nav: Queen | Knowledge | Playbook | Models | Settings

The "Knowledge" tab now renders `fc-knowledge-browser` (the unified component). The "Memory" tab is removed from top-level nav.

The KG visualization (`knowledge-view.ts` minus its skill-browser import) becomes accessible from within the knowledge browser as a "Graph" sub-tab or from a dedicated button, not as its own top-level nav entry. This is a UX simplification, not a KG removal.

Files touched:
- `frontend/src/components/formicos-app.ts` -- update nav, remove "Memory" tab, update "Knowledge" case (~20 LOC changed)

**B4. Colony detail knowledge link.**

Update colony detail's memory indicator to link to the unified knowledge browser instead of the memory browser. Update the event name from `navigate-memory` to `navigate-knowledge`.

Files touched:
- `frontend/src/components/colony-detail.ts` (~8 LOC changed)
- `frontend/src/components/formicos-app.ts` -- handle `navigate-knowledge` event (~5 LOC)

**B5. Frontend types.**

Add `KnowledgeItemPreview` interface to `types.ts`. This mirrors the surface-layer `KnowledgeItem` contract.

```typescript
export interface KnowledgeItemPreview {
  id: string;
  canonical_type: 'skill' | 'experience';
  source_system: 'legacy_skill_bank' | 'institutional_memory';
  status: string;
  confidence: number;
  title: string;
  summary: string;
  content_preview: string;
  source_colony_id: string;
  source_artifact_ids: string[];
  domains: string[];
  tool_refs: string[];
  created_at: string;
  polarity: string;
  legacy_metadata: Record<string, any>;
}
```

Files touched: `frontend/src/types.ts` (~20 LOC)

| File | Action |
|------|--------|
| `frontend/src/components/knowledge-browser.ts` | New -- unified knowledge browser |
| `frontend/src/components/formicos-app.ts` | Nav restructure, route to new component |
| `frontend/src/components/colony-detail.ts` | Knowledge link update |
| `frontend/src/components/knowledge-view.ts` | Small additive graph-only shim for KG sub-tab |
| `frontend/src/types.ts` | KnowledgeItemPreview interface |

Do not touch:
- `src/formicos/*` (Track A owns backend)
- `frontend/src/components/skill-browser.ts` (kept as importable, not deleted yet)
- `frontend/src/components/memory-browser.ts` (kept as importable, not deleted yet)
- `frontend/src/components/knowledge-view.ts` except for the small graph-only shim owned by Track B and the route URL fix owned by Track C

---

### Track C -- Compatibility + Deprecation Labeling

**Goal:** Explicitly label what is legacy vs current across the codebase. Prepare the deprecation path without executing it. Keep legacy writes and reads fully functional.

**C1. Deprecation markers on legacy APIs.**

Add `_deprecated` field to both legacy endpoint responses:
- `/api/v1/skills` response becomes `{"_deprecated": "Use /api/v1/knowledge instead", "skills": [...]}`
- `/api/v1/memory` response gains `"_deprecated": "Use /api/v1/knowledge instead"`

Since no external consumers exist, the shape change on `/api/v1/skills` (from raw array to object wrapper) is acceptable. `skill-browser.ts` is being replaced by the unified `knowledge-browser.ts` in Track B, so the old consumer goes away in the same wave.

Files touched:
- `src/formicos/surface/routes/api.py` -- deprecation field + KG route rename to `/api/v1/knowledge-graph` (~10 LOC)
- `src/formicos/surface/routes/memory_api.py` -- add deprecation field (~3 LOC)

**C2. Legacy search_memory tool deprecation marker.**

Update the `search_memory` tool description in `queen_runtime.py` to include "(deprecated: use memory_search instead)". The tool continues to work. This is a prompt signal for the Queen to prefer the unified tool.

Files touched: `src/formicos/surface/queen_runtime.py` (~2 LOC changed)

**C3. KG route migration.**

Rename `/api/v1/knowledge` to `/api/v1/knowledge-graph` in `routes/api.py`. Update `knowledge-view.ts` to fetch from the new path. This frees `/api/v1/knowledge` for the unified catalog.

Files touched:
- `src/formicos/surface/routes/api.py` -- route rename (~5 LOC)
- `frontend/src/components/knowledge-view.ts` -- update fetch URL (~3 LOC)

**C4. Documentation: cutover plan.**

New `docs/waves/wave_27/cutover_plan.md` documenting the later execution-layer migration:

1. Repoint `context.py` agent retrieval from `skill_bank_v2` to `institutional_memory` (or knowledge catalog)
2. Unify agent `memory_search` in `runner.py` to use institutional memory
3. Stop legacy crystallization writes (`_crystallize_skills`)
4. Bridge remaining `skill_bank_v2` data into institutional memory (one-time migration)
5. Remove legacy `search_memory` Queen tool
6. Remove `skill_lifecycle.py` active call sites
7. Remove `/api/v1/skills` endpoint
8. Remove `skill-browser.ts` and old `knowledge-view.ts`

This document is planning scaffolding. It makes the later wave faster to plan.

Files touched: `docs/waves/wave_27/cutover_plan.md` -- new (~50 lines)

**C5. Smoke coverage for unified surfaces.**

Add BDD or unit test scenarios that verify:
- `/api/v1/knowledge/search` returns results from both backends
- source_system field is correctly set
- legacy skills normalize into KnowledgeItem shape
- Queen `memory_search` returns federated results
- pre-spawn retrieval includes both legacy and institutional entries

Files touched: `tests/unit/surface/test_knowledge_catalog.py` -- new (~80 LOC)

| File | Action |
|------|--------|
| `src/formicos/surface/routes/api.py` | Deprecation field on /skills + KG route rename to /knowledge-graph |
| `src/formicos/surface/routes/memory_api.py` | Deprecation field on /memory |
| `src/formicos/surface/queen_runtime.py` | Deprecation marker on search_memory tool |
| `frontend/src/components/knowledge-view.ts` | Update KG fetch URL to /knowledge-graph |
| `docs/waves/wave_27/cutover_plan.md` | New -- later migration plan |
| `tests/unit/surface/test_knowledge_catalog.py` | New -- catalog smoke tests |

Do not touch:
- `src/formicos/core/*`
- `src/formicos/engine/*`
- `src/formicos/surface/skill_lifecycle.py`
- `src/formicos/surface/colony_manager.py`
- `src/formicos/adapters/*`

---

## Execution Shape for 3 Parallel Coder Teams

| Team | Track | First Lands On | Dependencies |
|------|-------|----------------|--------------|
| **Coder 1** | A (Catalog + API + Queen repoint) | `knowledge_catalog.py`, `knowledge_api.py`, `app.py`, `runtime.py`, `queen_runtime.py` | None -- starts immediately |
| **Coder 2** | B (Frontend unification) | `knowledge-browser.ts`, `formicos-app.ts`, `colony-detail.ts`, `types.ts` | Uses `/api/v1/knowledge` from Track A |
| **Coder 3** | C (Compatibility + docs + tests) | `routes/api.py`, `routes/memory_api.py`, `queen_runtime.py`, `cutover_plan.md`, `test_knowledge_catalog.py` | Uses catalog from Track A |

### Overlap-Prone Files

| File | Teams | Resolution |
|------|-------|------------|
| `queen_runtime.py` | A (repoint handler), C (deprecation marker) | A changes the handler logic. C changes a description string. Both additive. Sequence A before C. |
| `app.py` | A only | No overlap. |

### Frozen Files

| File | Reason |
|------|--------|
| `src/formicos/core/*` | No contract changes this wave |
| `src/formicos/engine/context.py` | Agent retrieval stays on legacy -- Wave 28 cutover |
| `src/formicos/engine/runner.py` | Agent tools unchanged -- Wave 28 cutover |
| `src/formicos/surface/skill_lifecycle.py` | Legacy system stays active |
| `src/formicos/surface/colony_manager.py` | Legacy crystallization stays active |
| `src/formicos/surface/memory_store.py` | Unchanged -- catalog calls it |
| `src/formicos/surface/memory_extractor.py` | Unchanged |
| `src/formicos/surface/memory_scanner.py` | Unchanged |
| `src/formicos/adapters/*` | No adapter changes |
| `docker-compose.yml` | No changes |
| `Dockerfile` | No changes |

---

## Acceptance Criteria

1. **One knowledge search returns results from both systems.** `GET /api/v1/knowledge/search?q=python` returns items with both `source_system: "legacy_skill_bank"` and `source_system: "institutional_memory"`.
2. **Every item declares its source system.** No knowledge item is returned without an explicit `source_system` field.
3. **Legacy skills normalize correctly.** Legacy skill entries appear with `canonical_type: "skill"`, `status: "active"`, and `legacy_metadata` containing alpha/beta when available.
4. **Colony detail navigates to unified view.** Clicking memory count on colony detail opens the knowledge browser filtered by that colony.
5. **One operator-facing knowledge tab.** The nav has one "Knowledge" tab, not separate "Knowledge" and "Memory" tabs.
6. **Queen `memory_search` returns federated results.** The Queen's search tool returns results from both legacy skills and institutional memory.
7. **Pre-spawn retrieval includes both systems.** The Queen's pre-spawn context block can contain both legacy skills and institutional entries.
8. **Legacy endpoints still work.** `/api/v1/skills` and `/api/v1/memory` return results with `_deprecated` field.
9. **No execution-layer changes.** Agent context injection (`context.py`) still reads `skill_bank_v2`. Legacy crystallization still writes to `skill_bank_v2`. No agent tool semantics changed.
10. **KG visualization still accessible.** The knowledge graph viewer is reachable from the knowledge view, not deleted.
11. **Full CI green.** `ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest && cd frontend && npm run build`

### Smoke Traces

1. **Federated search:** Ensure both legacy skills and institutional memory exist -> `GET /api/v1/knowledge/search?q=testing` -> results include items from both systems
2. **Source labeling:** Each returned item has `source_system` set
3. **Unified browser:** Navigate to Knowledge tab -> see items from both systems with source badges
4. **Colony link:** Colony detail -> click memory count -> knowledge browser opens filtered by colony
5. **Queen search:** Queen calls `memory_search` -> response includes legacy skills alongside institutional entries
6. **Legacy compat:** `GET /api/v1/skills` still returns legacy skill data with `_deprecated` field

---

## Not in Wave 27

| Item | Reason |
|------|--------|
| Repointing `context.py` off `skill_bank_v2` | Execution-layer cutover is Wave 28 |
| Changing agent `memory_search` in `runner.py` | Execution-layer cutover is Wave 28 |
| Removing `_crystallize_skills()` | Legacy writes stay active until cutover |
| Removing `skill_lifecycle.py` | Legacy system stays active until cutover |
| Bayesian confidence on MemoryEntry | Requires event/schema changes; Wave 28+ |
| Dedup / contradiction detection | Consolidation is Wave 28+ |
| Stale decay / negative experience consolidation | Wave 28+ |
| One-time skill bank data migration to institutional memory | Wave 28 cutover |
| Event union changes | No new events this wave |
| MemoryEntry schema changes | No schema changes this wave |

---

## What This Enables Next

**Wave 28: Execution-Layer Cutover.** With the unified surface stable and proven, repoint `context.py` and `runner.py` to read from institutional memory. Stop legacy crystallization writes. Bridge or migrate remaining `skill_bank_v2` data. Bayesian confidence on `MemoryEntry` if needed. Remove legacy tool duplicates.

**Wave 29: Governed Consolidation.** Dedup, contradiction surfacing, stale decay, negative experience consolidation, domain-aware retrieval, operator governance surfaces. Confidence evolution lifecycle.

**Wave 30: Context as Environment.** Agents navigate knowledge via progressive disclosure. RLM-style recursive context decomposition. Full environment navigation.
