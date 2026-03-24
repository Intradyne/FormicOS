# Wave 27 Algorithms -- Implementation Reference

**Wave:** 27 -- "Unified Knowledge Workflow"
**Purpose:** Technical implementation guide for all three tracks.

---

## S1. Knowledge Catalog -- Federated Read Facade (Track A -- A1)

### Module: surface/knowledge_catalog.py

```python
"""Federated knowledge catalog -- read-only aggregation over both backends (Wave 27).

Normalizes legacy skill bank entries and institutional memory entries into
a common KnowledgeItem shape. Read-only -- does not write to either store.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from formicos.core.ports import VectorPort
    from formicos.surface.memory_store import MemoryStore
    from formicos.surface.projections import ProjectionStore

log = structlog.get_logger()

_LEGACY_SKILL_COLLECTION = "skill_bank_v2"


@dataclass(frozen=True)
class KnowledgeItem:
    """Normalized read model for unified knowledge display."""

    id: str = ""
    canonical_type: str = "skill"           # "skill" | "experience"
    source_system: str = ""                 # "legacy_skill_bank" | "institutional_memory"
    status: str = "active"
    confidence: float = 0.5
    title: str = ""
    summary: str = ""
    content_preview: str = ""
    source_colony_id: str = ""
    source_artifact_ids: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    tool_refs: list[str] = field(default_factory=list)
    created_at: str = ""
    polarity: str = "positive"
    legacy_metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0  # query relevance score for search results


def _normalize_legacy_skill(hit: Any) -> dict[str, Any]:
    """Convert a VectorSearchHit from skill_bank_v2 into KnowledgeItem dict."""
    meta = hit.metadata if hasattr(hit, "metadata") else {}
    content = hit.content if hasattr(hit, "content") else ""

    # Extract title from technique metadata or content prefix
    technique = meta.get("technique", "")
    title = technique if technique else content[:80].split("\n")[0]

    return asdict(KnowledgeItem(
        id=hit.id if hasattr(hit, "id") else "",
        canonical_type="skill",
        source_system="legacy_skill_bank",
        status="active",  # legacy skills have no candidate/verified lifecycle
        confidence=float(meta.get("confidence", 0.5)),
        title=title,
        summary=meta.get("when_to_use", ""),
        content_preview=content[:500],
        source_colony_id=meta.get("source_colony_id", meta.get("source_colony", "")),
        source_artifact_ids=[],  # legacy skills predate artifact model
        domains=[],  # legacy skills don't have domain tags
        tool_refs=[],  # legacy skills don't have tool refs
        created_at=meta.get("extracted_at", ""),
        polarity="positive",
        legacy_metadata={
            "conf_alpha": meta.get("conf_alpha"),
            "conf_beta": meta.get("conf_beta"),
            "merge_count": meta.get("merge_count", 0),
            "algorithm_version": meta.get("algorithm_version", ""),
            "failure_modes": meta.get("failure_modes", ""),
        },
        score=float(hit.score) if hasattr(hit, "score") else 0.0,
    ))


def _normalize_institutional(entry: dict[str, Any], score: float = 0.0) -> dict[str, Any]:
    """Convert an institutional memory search result into KnowledgeItem dict."""
    return asdict(KnowledgeItem(
        id=entry.get("id", ""),
        canonical_type=entry.get("entry_type", "skill"),
        source_system="institutional_memory",
        status=entry.get("status", "candidate"),
        confidence=float(entry.get("confidence", 0.5)),
        title=entry.get("title", ""),
        summary=entry.get("summary", ""),
        content_preview=entry.get("content", "")[:500],
        source_colony_id=entry.get("source_colony_id", ""),
        source_artifact_ids=entry.get("source_artifact_ids", []),
        domains=entry.get("domains", []),
        tool_refs=entry.get("tool_refs", []),
        created_at=entry.get("created_at", ""),
        polarity=entry.get("polarity", "positive"),
        legacy_metadata={},
        score=score,
    ))


class KnowledgeCatalog:
    """Federated read facade over legacy skill bank and institutional memory."""

    def __init__(
        self,
        memory_store: MemoryStore | None,
        vector_port: VectorPort | None,
        skill_collection: str = _LEGACY_SKILL_COLLECTION,
        projections: ProjectionStore | None = None,
    ) -> None:
        self._memory_store = memory_store
        self._vector = vector_port
        self._skill_collection = skill_collection
        self._projections = projections

    async def search(
        self,
        query: str,
        *,
        source_system: str = "",
        canonical_type: str = "",
        workspace_id: str = "",
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Federated search across both backends.

        Runs both searches in parallel, normalizes, merges, and returns
        sorted by composite relevance. If one backend is unavailable,
        the other still returns results.
        """
        tasks: list[Any] = []

        # Institutional memory search
        if (
            self._memory_store is not None
            and source_system in ("", "institutional_memory")
        ):
            entry_type = ""
            if canonical_type == "skill":
                entry_type = "skill"
            elif canonical_type == "experience":
                entry_type = "experience"
            tasks.append(self._search_institutional(
                query, entry_type=entry_type,
                workspace_id=workspace_id, top_k=top_k,
            ))
        else:
            tasks.append(self._empty())

        # Legacy skill bank search
        if (
            self._vector is not None
            and source_system in ("", "legacy_skill_bank")
            and canonical_type in ("", "skill")  # legacy only has skills
        ):
            tasks.append(self._search_legacy(query, top_k=top_k))
        else:
            tasks.append(self._empty())

        institutional_results, legacy_results = await asyncio.gather(*tasks)

        # Merge and deduplicate by ID
        seen: set[str] = set()
        merged: list[dict[str, Any]] = []
        for item in institutional_results + legacy_results:
            item_id = item.get("id", "")
            if item_id and item_id not in seen:
                seen.add(item_id)
                merged.append(item)

        # Sort by composite: score + status bonus + confidence tiebreak
        _STATUS_BONUS = {
            "verified": 0.3, "active": 0.25,
            "candidate": 0.0, "stale": -0.2,
        }
        merged.sort(
            key=lambda x: -(
                float(x.get("score", 0.0))
                + _STATUS_BONUS.get(str(x.get("status", "")), -0.5)
                + float(x.get("confidence", 0.0)) * 0.1
            ),
        )
        return merged[:top_k]

    async def list_all(
        self,
        *,
        source_system: str = "",
        canonical_type: str = "",
        workspace_id: str = "",
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        """List all knowledge items from both backends.

        Returns (items, total_count).
        """
        items: list[dict[str, Any]] = []

        # Institutional memory entries from projection state
        if (
            self._projections is not None
            and source_system in ("", "institutional_memory")
        ):
            for entry in self._projections.memory_entries.values():
                if workspace_id and entry.get("workspace_id") != workspace_id:
                    continue
                if canonical_type and entry.get("entry_type") != canonical_type:
                    continue
                items.append(_normalize_institutional(entry))

        # Legacy skill bank entries -- reuses the proven broad-query pattern
        # from get_skill_bank_detail() in view_state.py (line 605).
        if (
            self._vector is not None
            and source_system in ("", "legacy_skill_bank")
            and canonical_type in ("", "skill")
        ):
            try:
                results = await self._vector.search(
                    collection=self._skill_collection,
                    query="skill knowledge technique pattern",  # proven listing query from view_state.py
                    top_k=limit,
                )
                for hit in results:
                    items.append(_normalize_legacy_skill(hit))
            except Exception:
                log.debug("knowledge_catalog.legacy_list_failed")

        # Sort by newest
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        total = len(items)
        return items[:limit], total

    async def get_by_id(self, item_id: str) -> dict[str, Any] | None:
        """Retrieve a single knowledge item by ID."""
        # Institutional memory: check projection state
        if self._projections is not None:
            entry = self._projections.memory_entries.get(item_id)
            if entry is not None:
                return _normalize_institutional(entry)

        # Legacy skill bank: best-effort lookup. Legacy skills use plain UUIDs,
        # and VectorPort.search() is semantic, not by-ID. This is a convenience
        # fallback, not a guaranteed contract. The unified browser's primary
        # value for legacy items is list/search, not by-id detail.
        if self._vector is not None:
            try:
                results = await self._vector.search(
                    collection=self._skill_collection,
                    query=item_id,
                    top_k=5,
                )
                for hit in results:
                    if getattr(hit, "id", "") == item_id:
                        return _normalize_legacy_skill(hit)
            except Exception:
                log.debug("knowledge_catalog.legacy_get_failed", id=item_id)

        return None

    async def _search_institutional(
        self, query: str, *, entry_type: str, workspace_id: str, top_k: int,
    ) -> list[dict[str, Any]]:
        if self._memory_store is None:
            return []
        try:
            results = await self._memory_store.search(
                query=query, entry_type=entry_type,
                workspace_id=workspace_id, top_k=top_k,
            )
            return [
                _normalize_institutional(r, score=float(r.get("score", 0.0)))
                for r in results
            ]
        except Exception:
            log.debug("knowledge_catalog.institutional_search_failed")
            return []

    async def _search_legacy(self, query: str, *, top_k: int) -> list[dict[str, Any]]:
        if self._vector is None:
            return []
        try:
            results = await self._vector.search(
                collection=self._skill_collection,
                query=query, top_k=top_k,
            )
            return [_normalize_legacy_skill(hit) for hit in results]
        except Exception:
            log.debug("knowledge_catalog.legacy_search_failed")
            return []

    @staticmethod
    async def _empty() -> list[dict[str, Any]]:
        return []
```

---

## S2. Knowledge REST API (Track A -- A2)

### Module: surface/routes/knowledge_api.py

```python
"""Unified knowledge REST API -- federated over both backends (Wave 27)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.responses import JSONResponse
from starlette.routing import Route

if TYPE_CHECKING:
    from starlette.requests import Request

    from formicos.surface.knowledge_catalog import KnowledgeCatalog


def routes(
    *,
    knowledge_catalog: KnowledgeCatalog | None = None,
    **_unused: Any,
) -> list[Route]:
    """Build unified knowledge API routes."""

    async def list_knowledge(request: Request) -> JSONResponse:
        if knowledge_catalog is None:
            return JSONResponse({"error": "knowledge catalog not available"}, status_code=503)

        source = request.query_params.get("source", "")
        ctype = request.query_params.get("type", "")
        workspace = request.query_params.get("workspace", "")
        limit = min(int(request.query_params.get("limit", "50")), 200)

        items, total = await knowledge_catalog.list_all(
            source_system=source,
            canonical_type=ctype,
            workspace_id=workspace,
            limit=limit,
        )
        return JSONResponse({"items": items, "total": total})

    async def search_knowledge(request: Request) -> JSONResponse:
        if knowledge_catalog is None:
            return JSONResponse({"error": "knowledge catalog not available"}, status_code=503)

        query = request.query_params.get("q", "")
        if not query:
            return JSONResponse({"error": "query parameter 'q' required"}, status_code=400)

        source = request.query_params.get("source", "")
        ctype = request.query_params.get("type", "")
        workspace = request.query_params.get("workspace", "")
        limit = min(int(request.query_params.get("limit", "10")), 50)

        results = await knowledge_catalog.search(
            query=query,
            source_system=source,
            canonical_type=ctype,
            workspace_id=workspace,
            top_k=limit,
        )
        return JSONResponse({"results": results, "total": len(results)})

    async def get_knowledge_item(request: Request) -> JSONResponse:
        if knowledge_catalog is None:
            return JSONResponse({"error": "knowledge catalog not available"}, status_code=503)

        item_id = request.path_params["item_id"]
        item = await knowledge_catalog.get_by_id(item_id)
        if item is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(item)

    return [
        Route("/api/v1/knowledge", list_knowledge, methods=["GET"]),
        Route("/api/v1/knowledge/search", search_knowledge, methods=["GET"]),
        Route("/api/v1/knowledge/{item_id:str}", get_knowledge_item, methods=["GET"]),
    ]
```

---

## S3. Queen Search Repoint (Track A -- A3)

### In queen_runtime.py -- _tool_memory_search handler

Replace the direct `memory_store.search()` call with `knowledge_catalog.search()`:

```python
async def _tool_memory_search(
    self, inputs: dict[str, Any], workspace_id: str,
) -> tuple[str, dict[str, Any] | None]:
    """Handle the memory_search Queen tool -- unified knowledge search."""
    catalog = getattr(self._runtime, "knowledge_catalog", None)
    if catalog is None:
        return ("Knowledge catalog is not available.", None)

    query = inputs.get("query", "")
    if not query:
        return ("Error: query is required.", None)

    entry_type = inputs.get("entry_type", "")
    limit = min(int(inputs.get("limit", 5)), 10)

    results = await catalog.search(
        query=query,
        canonical_type=entry_type,
        workspace_id=workspace_id,
        top_k=limit,
    )

    if not results:
        return (f"No knowledge found for: {query}", None)

    lines = [f"Found {len(results)} entries:"]
    for r in results:
        source_tag = "LEGACY" if r.get("source_system") == "legacy_skill_bank" else "INST"
        ctype = str(r.get("canonical_type", "skill")).upper()
        status = str(r.get("status", ""))
        polarity = str(r.get("polarity", "positive"))
        polarity_tag = f" ({polarity})" if polarity != "positive" else ""
        title = r.get("title", "")
        content = str(r.get("content_preview", ""))[:200]
        lines.append(
            f"- [{ctype}, {status}, {source_tag}]{polarity_tag} "
            f'"{title}": {content}',
        )
        domains = r.get("domains", [])
        if domains:
            lines.append(f"  domains: {', '.join(domains)}")
        colony = r.get("source_colony_id", "")
        conf = r.get("confidence", 0.5)
        lines.append(f"  source: colony {colony}, confidence: {conf:.1f}")

    return ("\n".join(lines), None)
```

Also update the tool description:
```python
{
    "name": "memory_search",
    "description": (
        "Search all system knowledge -- skills, experiences, and legacy skill bank entries. "
        "Returns entries with provenance, trust status, and confidence scores."
    ),
    ...
}
```

### In runtime.py -- retrieve_relevant_memory

Replace `memory_store.search()` calls with `knowledge_catalog.search()`:

```python
async def retrieve_relevant_memory(
    self, task: str, workspace_id: str,
) -> str:
    catalog = getattr(self, "knowledge_catalog", None)
    if catalog is None:
        return ""

    try:
        results = await catalog.search(
            query=task,
            workspace_id=workspace_id,
            top_k=5,
        )
    except Exception:
        log.debug("runtime.memory_retrieval_failed", task=task[:80])
        return ""

    if not results:
        return ""

    lines = [f"[System Knowledge -- {len(results)} entries found]"]
    for entry in results:
        source = "LEGACY" if entry.get("source_system") == "legacy_skill_bank" else "INST"
        ctype = str(entry.get("canonical_type", "skill")).upper()
        status = str(entry.get("status", "")).upper()
        polarity = str(entry.get("polarity", "positive"))
        polarity_tag = f", {polarity}" if polarity != "positive" else ""
        title = entry.get("title", "")
        content = str(entry.get("content_preview", ""))[:300]
        colony = entry.get("source_colony_id", "")
        conf = entry.get("confidence", 0.5)
        lines.append(
            f'[{ctype}, {status}, {source}{polarity_tag}] "{title}": {content}',
        )
        lines.append(f"  source: colony {colony}, confidence: {conf:.1f}")

    return "\n".join(lines)
```

---

## S4. Legacy API Deprecation + KG Route Migration (Track C -- C1/C3)

### In routes/api.py -- get_skills endpoint

```python
async def get_skills(request: Request) -> JSONResponse:
    # ... existing logic returns skills list ...
    skills = await get_skill_bank_detail(...)
    return JSONResponse({
        "_deprecated": "Use GET /api/v1/knowledge or /api/v1/knowledge/search instead.",
        "skills": skills,
    })
```

Since no external consumers exist, the shape change from raw array to object wrapper is acceptable. The old consumer (`skill-browser.ts`) is replaced by `knowledge-browser.ts` in Track B.

### In routes/api.py -- KG route rename

```python
# Change:
Route("/api/v1/knowledge", get_knowledge),
Route("/api/v1/knowledge/search", search_knowledge),
# To:
Route("/api/v1/knowledge-graph", get_knowledge),
Route("/api/v1/knowledge-graph/search", search_knowledge),
```

This frees `/api/v1/knowledge` for the unified catalog.

### In frontend/src/components/knowledge-view.ts -- graph-only shim + fetch URL update

Add a tiny graph-only mode so the unified browser can reuse the KG component
without re-exposing the old internal skills/library tabs:

```typescript
@property({ type: Boolean }) graphOnly = false;
@property() initialTab: TabId = 'skills';

connectedCallback() {
  super.connectedCallback();
  this.tab = this.graphOnly ? 'graph' : this.initialTab;
  void this._fetchKG();
  if (!this.graphOnly) void this._fetchSkillCount();
}

// In render():
// - hide the tab row when graphOnly
// - render only _renderGraph() when graphOnly
// - skip _renderSkills() and _renderLibrary() in graphOnly mode
```

Then update the KG fetch URL:

```typescript
// Change all occurrences of:
fetch('/api/v1/knowledge')
fetch('/api/v1/knowledge/search')
// To:
fetch('/api/v1/knowledge-graph')
fetch('/api/v1/knowledge-graph/search')
```

### In routes/memory_api.py -- list_entries endpoint

```python
async def list_entries(request: Request) -> JSONResponse:
    # ... existing logic ...
    return JSONResponse({
        "_deprecated": "Use GET /api/v1/knowledge or /api/v1/knowledge/search instead.",
        "entries": entries[:limit],
        "total": len(entries),
    })
```

---

## S5. App Wiring (Track A -- A2)

### In app.py lifespan

```python
from formicos.surface.knowledge_catalog import KnowledgeCatalog

# After memory_store creation:
knowledge_catalog = KnowledgeCatalog(
    memory_store=memory_store,
    vector_port=vector_store,
    skill_collection=skill_collection,
    projections=projections,
)
runtime.knowledge_catalog = knowledge_catalog

# In route wiring:
from formicos.surface.routes import knowledge_api as knowledge_routes
routes.extend(knowledge_routes.routes(knowledge_catalog=knowledge_catalog))
```

---

## S6. Frontend KnowledgeItemPreview Type (Track B -- B4)

### In types.ts

```typescript
export type SourceSystem = 'legacy_skill_bank' | 'institutional_memory';
export type CanonicalType = 'skill' | 'experience';

export interface KnowledgeItemPreview {
  id: string;
  canonical_type: CanonicalType;
  source_system: SourceSystem;
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
  score: number;
}

export interface KnowledgeListResponse {
  items: KnowledgeItemPreview[];
  total: number;
  _deprecated?: string;
}

export interface KnowledgeSearchResponse {
  results: KnowledgeItemPreview[];
  total: number;
}
```

---

## S7. Files Changed Summary

### Track A (Coder 1)
| File | Action |
|------|--------|
| `src/formicos/surface/knowledge_catalog.py` | New -- federated read facade (~120 LOC) |
| `src/formicos/surface/routes/knowledge_api.py` | New -- unified REST API (~100 LOC) |
| `src/formicos/surface/routes/__init__.py` | Wire new routes (~3 LOC) |
| `src/formicos/surface/app.py` | Wire catalog + routes (~10 LOC) |
| `src/formicos/surface/queen_runtime.py` | Repoint memory_search handler + description (~15 LOC) |
| `src/formicos/surface/runtime.py` | Repoint pre-spawn retrieval (~10 LOC) |

### Track B (Coder 2)
| File | Action |
|------|--------|
| `frontend/src/components/knowledge-browser.ts` | New -- unified knowledge browser (~300 LOC) |
| `frontend/src/components/formicos-app.ts` | Nav restructure, remove Memory tab (~20 LOC) |
| `frontend/src/components/colony-detail.ts` | Knowledge link update (~8 LOC) |
| `frontend/src/types.ts` | KnowledgeItemPreview + related types (~20 LOC) |

### Track C (Coder 3)
| File | Action |
|------|--------|
| `src/formicos/surface/routes/api.py` | Deprecation field on /skills + KG route rename to /knowledge-graph (~10 LOC) |
| `src/formicos/surface/routes/memory_api.py` | Deprecation field on /memory (~3 LOC) |
| `src/formicos/surface/queen_runtime.py` | Deprecation marker on search_memory (~2 LOC) |
| `frontend/src/components/knowledge-view.ts` | Graph-only shim + update KG fetch URL to /knowledge-graph (~18 LOC) |
| `docs/waves/wave_27/cutover_plan.md` | New -- migration plan (~50 lines) |
| `tests/unit/surface/test_knowledge_catalog.py` | New -- catalog tests (~80 LOC) |
