# Wave 13 Plan — "Sharper Memory"

**Theme:** Every retrieval path in the system gets materially better. The embedding model jumps from 384-dim to 1024-dim. Hybrid search adds BM25. A knowledge graph gives TKG tuples a permanent home. The Queen gets a deterministic fallback. LanceDB gets removed. After Wave 13, an operator running a colony gets better skill injection, better context, and a more reliable Queen.

**Contract discipline:** Zero changes to `core/events.py`, `core/ports.py`, or `core/types.py`. All contract/mechanics changes defer to Wave 14.

---

## Scope

### In scope
- Qwen3-Embedding-0.6B sidecar (384→1024 dim upgrade)
- Qdrant `skill_bank_v2` collection with named dense + sparse vectors
- Hybrid search (dense + BM25 + RRF fusion) inside `adapters/vector_qdrant.py`
- Knowledge graph SQLite tables (`kg_nodes`, `kg_edges`) — storage only, no events
- Archivist TKG wiring into KG storage
- Graph-augmented retrieval (entity match + BFS + RRF) in `engine/context.py`
- Queen deterministic fallback (intent parser for when local tool-calling fails)
- Remove LanceDB dependency
- Evaluate `sentence-transformers` removal (measure DyTopo latency via HTTP)
- Frontend: Knowledge view, retrieval diagnostics, Queen fallback badges

### NOT in scope
- Event union changes (deferred to Wave 14)
- `VectorPort.search()` signature changes (ADR-019: stays unchanged)
- CasteSlot / subcaste tiers (full-stack migration, Wave 14)
- Service colonies, per-colony chat, sandbox (Wave 14)
- Inference swap / SGLang (benchmark sprint, Wave 14 pre-gate)

---

## Phase A — "One Migration, Three Upgrades"

Three coders, each with distinct file ownership. Deploy the embedding sidecar, create the new Qdrant collection with hybrid vector config, and stand up the KG storage.

### T1 — Qwen3-Embedding-0.6B deployment + collection migration

Deploy Qwen3-Embedding-0.6B Q8_0 (639MB GGUF) as a llama.cpp sidecar on port 8200. Shares the RTX 5090 (~700MB VRAM additional, total ~22GB of 32GB).

Key deployment details (from `Hybrid_Vector_Retrieval_for_FormicOS.md`):
- `--pooling last` (decoder model, not CLS/mean)
- Append `<|endoftext|>` to all inputs before sending
- Manually L2-normalize output vectors (server doesn't support `--embd-normalize`)
- Query prefix: `Instruct: Given a skill description, retrieve the matching agent capability\nQuery:{text}`
- Document encoding: raw text, no prefix

Create `skill_bank_v2` collection with named vectors:
- `dense`: 1024-dim, COSINE distance
- `sparse`: IDF modifier (for Qdrant server-side BM25)

Batch re-embed all existing skills from `skill_bank`. Validate top-3 retrieval parity against 20 representative queries covering: code patterns, error messages, tool usage, architectural concepts. Atomic alias swap via Qdrant collection aliases. Drop old collection after validation.

| File | Action |
|---|---|
| `src/formicos/adapters/embedding_qwen3.py` | **New** — httpx client to port 8200, L2-normalize, instruction prefix logic |
| `scripts/migrate_skill_bank_v2.py` | **New** — one-shot migration: create collection, re-embed all skills, alias swap, drop old |
| `docker-compose.yml` | **Edit** — add `formicos-embed` sidecar service |
| `config/formicos.yaml` | **Edit** — embedding section: `model: qwen3-embedding-0.6b`, `endpoint: http://localhost:8200`, `dimensions: 1024` |

**Acceptance criteria:**
- [ ] Sidecar starts, healthcheck passes, embeds a test string to 1024-dim
- [ ] `skill_bank_v2` created with both `dense` and `sparse` named vector configs
- [ ] All existing skills re-embedded and upserted
- [ ] Top-3 retrieval on 20 test queries: ≥ parity with old 384-dim collection
- [ ] Old collection dropped, alias `skill_bank_active` points to v2
- [ ] `embedding_qwen3.py` has unit tests for normalize + instruction prefix

### T2 — Hybrid search (adapter-internal)

Wire BM25 sparse vectors into `skill_bank_v2`. Zero new Python dependencies — Qdrant handles BM25 tokenization server-side via `models.Document(text=..., model="Qdrant/bm25")`. Requires Qdrant ≥ 1.15.2.

At ingestion (upsert path): generate both dense vector (from T1's endpoint) and sparse vector (via `models.Document`) per skill.

At query time: two-branch prefetch + RRF fusion:
```
Prefetch 1: dense query vector → "dense" named vector, limit=20
Prefetch 2: models.Document(text=query_text, model="Qdrant/bm25") → "sparse", limit=20
Fusion: RrfQuery(rrf=Rrf(k=60))
```

**No port contract change.** The `VectorPort.search(collection, query, top_k)` signature is unchanged. The adapter internally does hybrid search and returns `list[VectorSearchHit]` as before. See ADR-019.

The existing composite scoring (semantic + confidence + freshness + UCB) stays downstream of RRF. RRF merges dense and sparse candidate sets; the reranker in `engine/context.py` applies.

Gradual migration: points without sparse vectors don't appear in sparse prefetch — no errors, no crashes. Dense prefetch still finds them.

| File | Action |
|---|---|
| `src/formicos/adapters/vector_qdrant.py` | **Edit** — BM25 upsert via `models.Document`, prefetch + RRF in `search()`, named vector addressing |

**Acceptance criteria:**
- [ ] Skills upserted with both dense and sparse vectors
- [ ] `search()` returns RRF-fused results from both branches
- [ ] Existing callers (`engine/context.py`) see no interface change
- [ ] Query with keyword-heavy input (error message, function name) returns better results than dense-only

**Depends on:** T1 (collection must exist with sparse config)

### T3 — Knowledge graph storage

SQLite adjacency tables (`kg_nodes`, `kg_edges`) via aiosqlite in the existing `formicos.db` file. No events emitted — data goes directly to SQLite. The retrieval pipeline (Phase B-T3) reads it.

Schema follows the Graphiti-inspired bi-temporal model from `FormicOS_Implementation_Reference.md`:

```sql
CREATE TABLE kg_nodes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,  -- MODULE, CONCEPT, SKILL, TOOL, PERSON, ORGANIZATION
    summary TEXT,
    source_colony TEXT,
    workspace_id TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_kg_nodes_name ON kg_nodes(name);
CREATE INDEX idx_kg_nodes_type ON kg_nodes(entity_type);
CREATE INDEX idx_kg_nodes_ws ON kg_nodes(workspace_id);

CREATE TABLE kg_edges (
    id TEXT PRIMARY KEY,
    from_node TEXT NOT NULL REFERENCES kg_nodes(id),
    to_node TEXT NOT NULL REFERENCES kg_nodes(id),
    predicate TEXT NOT NULL,  -- DEPENDS_ON, ENABLES, IMPLEMENTS, VALIDATES, MIGRATED_TO, FAILED_ON
    confidence REAL DEFAULT 0.7,
    valid_at TEXT,
    invalid_at TEXT,
    source_colony TEXT,
    source_round INTEGER,
    workspace_id TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_kg_edges_from ON kg_edges(from_node);
CREATE INDEX idx_kg_edges_to ON kg_edges(to_node);
CREATE INDEX idx_kg_edges_ws ON kg_edges(workspace_id);
```

Entity resolution: normalize entity names (lowercase, strip whitespace), embed with Qwen3-Embedding (reuse T1's endpoint), cosine similarity ≥ 0.85 → candidate duplicate, LLM confirmation for ambiguous cases (Gemini Flash, 500ms timeout).

Six starter predicates: `DEPENDS_ON`, `ENABLES`, `IMPLEMENTS`, `VALIDATES`, `MIGRATED_TO`, `FAILED_ON`.

Wire Archivist's TKG tuple output — currently used for stall detection then discarded. After this, tuples persist and accumulate across colonies.

| File | Action |
|---|---|
| `src/formicos/adapters/knowledge_graph.py` | **New** — SQLite table init, CRUD, entity resolution, BFS traversal |
| `src/formicos/engine/runner.py` | **Edit (small)** — after Archivist compress phase, call `kg_adapter.ingest_tuples()` |
| `config/formicos.yaml` | **Edit** — KG section: `predicates`, `entity_similarity_threshold: 0.85` |

**Acceptance criteria:**
- [ ] KG tables created on first startup (migration in `knowledge_graph.py.__init__`)
- [ ] Archivist TKG tuples written to `kg_nodes`/`kg_edges` after each compress phase
- [ ] Entity resolution deduplicates "FastAPI_router" and "fastapi_router" as same entity
- [ ] `get_neighbors(entity_id, depth=1)` returns 1-hop BFS results
- [ ] Unit tests for CRUD, entity resolution, BFS

**Merge order:** T1 first (creates collection + embedding endpoint). T2 second (wires BM25 into T1's collection). T3 is independent of T1/T2.

---

## Phase B — "Queen Reliability + Cleanup"

Three coders. Queen fallback, LanceDB removal, graph-augmented retrieval.

### T1 — Queen deterministic fallback

Build a deterministic intent parser for when local tool-calling fails. Two-pass architecture:
1. Primary: existing tool-call parse from defensive parser (Wave 10)
2. Fallback (only when primary returns no actions): regex + classification on Queen prose

**First task: collect real failure data.** Run the Queen on Qwen3-30B-A3B with 5+ real tasks. Capture every case where tool-calling produces prose instead of structured output. Build regex patterns from these actual outputs, not hypothetical examples.

Regex patterns for the 4 core directives:
- SPAWN: "spawn/create/start/launch a colony for/to {objective}"
- KILL: "kill/terminate/stop colony {id}"
- REDIRECT: "redirect/refocus colony {id} to/toward {new_objective}"
- APOPTOSIS: "colony {id} should/can self-terminate/complete/finish"

Plus: lightweight Gemini Flash classification fallback for ambiguous prose (500ms timeout, same pattern as Queen naming from Wave 11). Runs only when regex matches nothing.

Emits the same events as tool-call parsing — the engine never knows the difference. The colony chat (Wave 14 frontend) will show "parsed from intent" indicator on these directives.

| File | Action |
|---|---|
| `src/formicos/adapters/queen_intent_parser.py` | **New** — regex patterns, Gemini Flash fallback, structured output matching existing directive types |
| `src/formicos/surface/queen_runtime.py` | **Edit** — if primary defensive parse returns no actions, invoke intent parser as second pass |

**Acceptance criteria:**
- [ ] 20+ real Queen failure outputs collected and saved as test fixtures
- [ ] Regex catches ≥80% of collected SPAWN intents from prose output
- [ ] Gemini Flash fallback catches remaining ambiguous cases (with timeout)
- [ ] Parser emits identical event structures to tool-call parse
- [ ] Unit tests with real failure fixtures
- [ ] Fallback invocation logged via structlog with `via="intent_parser"`

### T2 — Remove LanceDB + dependency audit

Drop the dead-code LanceDB fallback. Evaluate whether `sentence-transformers` can also be removed.

| File | Action |
|---|---|
| `pyproject.toml` | **Edit** — remove `lancedb` from dependencies |
| `src/formicos/adapters/vector_lancedb.py` | **Delete** |
| `config/formicos.yaml` | **Edit** — remove `VECTOR_BACKEND` feature flag if present |
| `src/formicos/surface/app.py` | **Edit (small)** — remove LanceDB adapter import and wiring from bootstrap |

**sentence-transformers evaluation:** Now that Qwen3-Embedding runs as a sidecar (port 8200, httpx), the Python `sentence-transformers` library is only needed for DyTopo intent embedding in `engine/runner.py`. Measure:
- In-process MiniLM latency (current): ~5ms per embed
- HTTP to sidecar latency: ~80-100ms per embed

If ≤100ms is acceptable for DyTopo routing frequency (once per round per agent, not latency-critical), remove `sentence-transformers` and its PyTorch transitive chain from `pyproject.toml`. Update DyTopo intent embedding in `engine/runner.py` to call `adapters/embedding_qwen3.py`.

If >100ms is unacceptable, keep `sentence-transformers` and document the measured latency comparison as a decision record.

**Acceptance criteria:**
- [ ] `lancedb` removed from `pyproject.toml`
- [ ] `adapters/vector_lancedb.py` deleted
- [ ] No import of LanceDB anywhere in codebase (`grep -r "lancedb"` returns nothing)
- [ ] Docker image size measured before/after (expect ≥400MB reduction from PyArrow removal)
- [ ] `sentence-transformers` decision documented with measured latency numbers
- [ ] All existing tests pass

### T3 — Graph-augmented retrieval pipeline

Connect Phase A's three components (embedding, hybrid search, KG) into a unified retrieval path. Three-stage query:

1. **Entity extraction:** Before calling `vector_port.search()`, extract entity mentions from the goal text by matching against known entity names from `kg_nodes`. Simple pattern matching — not LLM-gated.

2. **Parallel retrieval:** (a) Hybrid Qdrant search via `vector_port.search()` (which internally does dense + BM25 + RRF per T2). (b) SQLite KG entity match + 1-hop BFS traversal via `kg_adapter.get_neighbors()`.

3. **Merge:** Combine Qdrant results with KG context. KG results provide structured relationship context ("Module A DEPENDS_ON Module B") that enriches the flat skill text from Qdrant. The merged result set feeds into the existing composite scoring (semantic + confidence + freshness + UCB).

**Architecture decision:** Retrieval orchestration lives in `engine/context.py` as a `RetrievalPipeline` helper class, injected with both `vector_port` and `kg_adapter` from `surface/app.py`. This keeps the logic in the engine layer. The KG adapter is injected as a dependency, not imported directly — same DI pattern as all other adapters.

| File | Action |
|---|---|
| `src/formicos/engine/context.py` | **Edit** — add `RetrievalPipeline` class, update context assembly to use it |
| `src/formicos/adapters/vector_qdrant.py` | **Edit (small)** — no new public methods, but T3 may need to coordinate timing |
| `src/formicos/adapters/knowledge_graph.py` | **Read-only dependency** — T3 calls `get_neighbors()` and `search_entities()` |
| `src/formicos/surface/app.py` | **Edit (small)** — inject `kg_adapter` into engine context assembly |

**Acceptance criteria:**
- [ ] Entity mentions extracted from goal text match known KG entities
- [ ] KG 1-hop BFS returns relevant relationship triples
- [ ] Merged results include both vector-matched skills and KG relationship context
- [ ] Graph traversal adds ≤5ms at <1000 nodes
- [ ] Existing tests for context assembly still pass (backward-compatible)
- [ ] Integration test: colony with KG data gets richer context than colony without

**Depends on:** Phase A (all three T1/T2/T3 must have landed)

**Merge order:** T1 and T2 are independent. T3 must be last (reads from KG tables created by A-T3, uses hybrid search from A-T2).

---

## Phase C — "Frontend + Visibility"

Three coders. Frontend-only work building on the new backend capabilities.

### T1 — Knowledge view

New view combining Skills and Knowledge Graph in a single tabbed interface, matching the "Knowledge" tab in `docs/prototype/formicos-v3.jsx`.

Skills tab: existing skill browser enhanced with embedding model badge (`qwen3-embedding-0.6b`), search mode indicator (`hybrid: dense+BM25+graph`).

Graph tab: SVG entity-relationship visualization. Entity nodes colored by type (MODULE, CONCEPT, TOOL). Predicate-labeled edges. Type filter pills. Click-to-inspect with detail panel showing entity name, type, source colony, connections.

New REST endpoint: `GET /api/v1/knowledge?workspace_id=X` returning `{ nodes: [...], edges: [...] }`.

| File | Action |
|---|---|
| `frontend/src/components/knowledge-view.ts` (or equivalent) | **New** — Lit component with skills + graph tabs |
| `src/formicos/surface/app.py` | **Edit** — add `GET /api/v1/knowledge` route |

### T2 — Retrieval diagnostics

New panel in Settings view showing retrieval pipeline performance, matching the diagnostics section in the prototype.

Per-stage latency meters: embedding, Qdrant dense, BM25 sparse, graph traversal, RRF fusion, total pipeline. Skill bank size, KG entity/edge counts. Embedding model name and search mode.

Backend: add structlog timing to the `RetrievalPipeline` in `engine/context.py` (Phase B-T3). Expose via a new REST endpoint or WebSocket state update.

| File | Action |
|---|---|
| `frontend/src/components/settings-diagnostics.ts` (or equivalent) | **New** — latency meters, counts |
| `src/formicos/engine/context.py` | **Edit (small)** — structlog timing on each retrieval stage |

### T3 — Queen fallback visibility

Colony detail and Queen chat show "parsed from intent" badge when directives came from the fallback parser. Skill browser shows embedding model name. Confirm all existing components handle hybrid search results gracefully (no data shape changes, just better results).

| File | Action |
|---|---|
| Frontend colony detail / chat components | **Edit (small)** — fallback badge rendering |
| Frontend skill browser | **Edit (small)** — model name badge |

---

## File Overlap Analysis

| File | Touched by | Risk |
|---|---|---|
| `adapters/vector_qdrant.py` | A-T2, B-T3 | **Low** — A-T2 rewrites `search()` internals, B-T3 reads results. Merge A-T2 first. |
| `engine/context.py` | B-T3, C-T2 | **Low** — B-T3 adds RetrievalPipeline, C-T2 adds timing. B-T3 merges first. |
| `config/formicos.yaml` | A-T1, A-T3, B-T2 | **Low** — different sections (embedding, kg, vector_backend). No conflict. |
| `surface/app.py` | B-T2, C-T1, B-T3 | **Low** — B-T2 removes LanceDB wiring, C-T1 adds KG route, B-T3 adds KG injection. Merge B-T2 first, then B-T3, then C-T1. |
| `docker-compose.yml` | A-T1 only | **None** |
| `surface/queen_runtime.py` | B-T1 only | **None** |
| `engine/runner.py` | A-T3 only (small edit) | **None** |

---

## Exit Gate

Wave 13 is done when:
- [ ] `skill_bank_v2` serves all retrieval with hybrid (dense + BM25) search
- [ ] Top-3 retrieval quality ≥ parity with old 384-dim dense-only on 20 test queries
- [ ] Knowledge graph accumulates TKG tuples across at least 2 colony completions
- [ ] Queen issues at least 1 directive via fallback parser in smoke test
- [ ] LanceDB fully removed, Docker image size reduced by ≥400MB
- [ ] Frontend: Knowledge view renders with real skills + KG data
- [ ] Frontend: Retrieval diagnostics shows real latency numbers
- [ ] Frontend: Fallback badge appears on parsed-from-intent directives
- [ ] Zero changes to `core/events.py`, `core/ports.py`, `core/types.py`
- [ ] All 672+ existing tests still pass

---

## What Wave 14 Inherits

Wave 14 picks up with:
- 1024-dim hybrid retrieval (dense + BM25 + graph) fully operational
- Knowledge graph populated with accumulated TKG tuples
- Queen reliable on local models (fallback parser catches prose output)
- Clean dependency set (no LanceDB, potentially no sentence-transformers)
- Prototype `docs/prototype/formicos-v3.jsx` as visual spec for all Wave 14 frontend work

Wave 14 opens contracts: 8 new events, CasteSlot migration, VectorPort extension, service colonies, per-colony chat, sandbox, structured castes. See ADR-019 for the boundary rationale.
