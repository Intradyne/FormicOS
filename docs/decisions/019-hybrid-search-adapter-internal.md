# ADR-019: Hybrid Search Stays Adapter-Internal in Wave 13

**Status:** Accepted
**Date:** 2026-03-14
**Context:** Wave 13 "Sharper Memory" planning

---

## Decision

Wave 13 hybrid search (dense + BM25 + knowledge graph) is implemented entirely inside `adapters/vector_qdrant.py` and `engine/context.py`. The `VectorPort.search()` signature in `core/ports.py` remains unchanged:

```python
async def search(self, collection: str, query: str, top_k: int = 5) -> list[VectorSearchHit]
```

No changes to `core/ports.py`, `docs/contracts/ports.py`, or `frontend/src/types.ts`.

---

## Context

Wave 13 adds three retrieval improvements:
1. Qwen3-Embedding-0.6B (1024-dim dense vectors replacing 384-dim)
2. Qdrant server-side BM25 (sparse vectors via `models.Document`)
3. Knowledge graph traversal (SQLite adjacency tables, 1-hop BFS)

The question: should `VectorPort.search()` gain new parameters (`text_query`, `graph_context`, `search_mode`) to expose these capabilities, or should the adapter handle everything internally?

---

## Why adapter-internal

**1. No caller needs explicit control yet.** The only caller of `VectorPort.search()` is `engine/context.py` for skill injection. It passes a query string and wants the best results back. It doesn't need to choose between dense-only, sparse-only, or graph-only search - it always wants the best fusion of all available signals.

**2. Zero contract changes = zero coordination cost.** Changing a port contract requires updating `core/ports.py`, `docs/contracts/ports.py`, `docs/contracts/types.ts`, and `frontend/src/types.ts`. In a shared-workspace, no-git environment, touching contract files in Wave 13 while Wave 14 plans a separate batch of contract changes creates merge risk and double-coordination.

**3. The adapter already has the query text.** `VectorPort.search()` receives `query: str`. The adapter can internally: (a) embed it for dense search, (b) pass it as-is for BM25, (c) extract entity mentions for KG lookup. No additional input is needed.

**4. Future extensibility is not blocked.** If Wave 14 or later needs explicit search-mode control (for example, "dense-only for DyTopo intent matching" versus "full hybrid for skill injection"), the port can be extended at that time with optional kwargs that default to the current behavior. Wave 13's adapter-internal implementation becomes the default path for the extended signature.

---

## How it works

The adapter's `search()` method:
1. Embeds the query via `adapters/embedding_qwen3.py` (1024-dim)
2. Runs Qdrant two-branch prefetch: dense + BM25 sparse
3. Fuses via `RrfQuery(rrf=Rrf(k=60))`
4. Returns `list[VectorSearchHit]` - same type as before

The `RetrievalPipeline` in `engine/context.py`:
1. Calls `vector_port.search()` (which does step 1-4 above)
2. Calls `kg_adapter.get_neighbors()` for matched entities
3. Merges KG context into the results for the agent's context window

The `RetrievalPipeline` is an engine-layer orchestrator, not a port change. It's injected from `surface/app.py` with both dependencies.

---

## Consequences

**Positive:**
- Wave 13 has zero contract changes - cleaner dispatch, no merge risk with Wave 14
- Existing callers work without modification
- Hybrid search is transparent - agents get better results without knowing how

**Negative:**
- No way for callers to request specific search modes (dense-only, sparse-only)
- KG augmentation logic lives in the engine layer, not exposed via the port

**Acceptable because:** No Wave 13 caller needs search-mode control. Wave 14 can extend the port if needed.

---

## Alternatives considered

### Extend VectorPort with optional kwargs

```python
async def search(
    self,
    collection: str,
    query: str,
    top_k: int = 5,
    *,
    text_query: str | None = None,
    use_graph: bool = False,
) -> list[VectorSearchHit]
```

Rejected: adds contract churn for parameters no Wave 13 caller uses.

### Create a new HybridSearchPort

Rejected: violates the principle of minimal port surface. The existing `VectorPort` covers the use case.

### Leave search dense-only, add hybrid as a separate method

Rejected: forces callers to choose. The adapter should always return the best available results.
