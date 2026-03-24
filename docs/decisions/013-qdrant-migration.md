# ADR-013: Qdrant Migration — Replace LanceDB with Qdrant behind VectorPort

**Status:** Accepted
**Date:** 2026-03-14
**Depends on:** ADR-010 (Skill Crystallization), Wave 9 (Skill Lifecycle)
**Supersedes:** LanceDB selection in Tech Stack Manifest (alpha default)

## Context

FormicOS runs Qdrant in docker-compose (port 6333/6334, named volume, healthcheck) but uses LanceDB (embedded, Python-native) for all vector operations. The `VectorPort` protocol in `docs/contracts/ports.py` defines three operations: `upsert()`, `search()`, `delete()`. LanceDB implements these through `adapters/vector_lancedb.py`.

Wave 9 added skill lifecycle operations (confidence-weighted retrieval, quality gates, confidence updates) that call VectorPort methods. These operations now need capabilities LanceDB lacks:

- **Payload-filtered search**: retrieve skills filtered by confidence range, source colony exclusion, algorithm version, or namespace — without post-filtering in application code.
- **Tenant-indexed multitenancy**: workspace isolation via indexed payload fields, not separate tables.
- **Collection statistics**: point counts, average confidence — needed by `get_skill_bank_summary()`.
- **Stable async API**: LanceDB's async support is limited and its API surface changes frequently.

Qdrant provides all of these. It is already deployed, already healthy, already consuming container resources.

## Decision

Replace LanceDB with Qdrant as the VectorPort adapter. The swap is behind a feature flag (`vector.backend: "qdrant"` in `formicos.yaml`). LanceDB remains in `pyproject.toml` as a fallback for one wave.

### Key design choices

**1. `query_points()` is the only search API.**
Qdrant v1.16.0 (December 2025) removed `search()`, `recommend()`, `search_batch()`, and `upload_records()`. The unified replacement is `query_points()`. All FormicOS code must target this API. Do NOT use `client.search()` — it does not exist.

**2. Single collection with payload-filtered multitenancy.**
One `skill_bank` collection with a `namespace` payload field indexed as tenant (`is_tenant=True`). Do NOT create collection-per-workspace. Qdrant strongly recommends this for < 100K entries — fewer collections means better HNSW efficiency.

**3. The adapter embeds queries internally.**
`VectorPort.search()` takes `query: str`, not a vector. The Qdrant adapter must embed the query text by calling the embedding endpoint before calling `query_points()`. This matches the LanceDB adapter's existing pattern via `embed_fn: Callable`.

**4. COSINE distance for BGE-M3.**
BGE-M3 produces L2-normalized dense vectors. COSINE and DOT yield identical rankings. Use COSINE for semantic clarity.

**5. Payload indexes on every filtered field.**
Without explicit indexes, Qdrant falls back to full scans. Create indexes on: `namespace` (KEYWORD, is_tenant=True), `confidence` (FLOAT), `algorithm_version` (KEYWORD), `created_at` (DATETIME), `source_colony` (KEYWORD).

**6. Graceful degradation on Qdrant failure.**
If Qdrant is unreachable, return empty search results. Log warning via structlog. Never crash a colony because vector search is down — skill retrieval is best-effort.

**7. Vector dimensions from config.**
The adapter reads `embedding.dimensions` from `formicos.yaml`. The current config says 384 (snowflake-arctic-embed-s) but the docker-compose BGE-M3 produces 1024-dim. The adapter must handle whichever value is configured — it does not hardcode dimensions.

### Migration path

1. Implement `QdrantVectorPort` in `adapters/vector_qdrant.py`
2. Run migration script: read LanceDB → upload to Qdrant (zero re-embedding)
3. Create payload indexes before switching traffic
4. Feature flag swap: `vector.backend: "qdrant"` in config
5. Validate search parity
6. Remove LanceDB in Wave 11

## Consequences

- **New dependency:** `qdrant-client>=1.16` added to `pyproject.toml`
- **No contract changes:** VectorPort interface is unchanged
- **No engine changes:** Engine calls VectorPort methods, never knows which backend
- **Migration cost:** One-shot script, < 1 second for < 50 entries
- **Rollback:** Feature flag reverts to LanceDB immediately
- **Future benefit:** Payload filtering enables the Phase 2-3 retrieval pipeline upgrades (BM25 hybrid search, cross-encoder reranking) without another migration
