# Wave 13 Algorithms

Implementation reference for offline coders. Every code pattern here maps to a file in the dispatch.

---

## 1. Qwen3-Embedding-0.6B Client (`adapters/embedding_qwen3.py`)

### Endpoint

llama.cpp sidecar on port 8200. OpenAI-compatible `/v1/embeddings` endpoint. The model is a decoder-only transformer with last-token pooling — different from the current MiniLM encoder.

### Critical implementation details

```python
EMBED_URL = "http://localhost:8200/v1/embeddings"
INSTRUCTION = "Given a skill description, retrieve the matching agent capability"

async def embed(
    texts: list[str],
    *,
    is_query: bool = False,
    client: httpx.AsyncClient,
) -> list[list[float]]:
    """Embed texts via the Qwen3-Embedding sidecar.
    
    Three mandatory steps llama.cpp doesn't handle:
    1. Prepend instruction for queries (not documents)
    2. Append EOS token to ALL inputs
    3. L2-normalize the output vectors
    """
    if is_query:
        inputs = [f"Instruct: {INSTRUCTION}\nQuery:{t}<|endoftext|>" for t in texts]
    else:
        inputs = [f"{t}<|endoftext|>" for t in texts]
    
    resp = await client.post(
        EMBED_URL,
        json={"input": inputs, "encoding_format": "float"},
        timeout=30.0,
    )
    resp.raise_for_status()
    raw = [d["embedding"] for d in resp.json()["data"]]
    
    # L2-normalize (mandatory — server returns raw logits)
    import numpy as np
    vecs = [np.array(v, dtype=np.float32) for v in raw]
    return [(v / np.linalg.norm(v)).tolist() for v in vecs]
```

### Docker sidecar configuration

```yaml
# docker-compose.yml addition
formicos-embed:
  image: ghcr.io/ggml-org/llama.cpp:server
  command: >
    --model /models/Qwen3-Embedding-0.6B-Q8_0.gguf
    --embedding
    --pooling last
    -ub 8192
    --port 8200
    --host 0.0.0.0
  ports:
    - "8200:8200"
  volumes:
    - ./models:/models:ro
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8200/health"]
    interval: 10s
    start_period: 30s
```

VRAM usage: ~700MB for Q8_0 quantization. Combined with Qwen3-30B-A3B (~21.1GB), total ~21.8GB of 32GB.

---

## 2. Qdrant Hybrid Collection Setup (`scripts/migrate_skill_bank_v2.py`)

### Collection creation with named vectors

```python
from qdrant_client import QdrantClient, models

client = QdrantClient(url="http://localhost:6333")

client.create_collection(
    collection_name="skill_bank_v2",
    vectors_config={
        "dense": models.VectorParams(
            size=1024,
            distance=models.Distance.COSINE,
        ),
    },
    sparse_vectors_config={
        "sparse": models.SparseVectorParams(
            modifier=models.Modifier.IDF,  # server-side IDF weighting
        ),
    },
)
```

The `modifier=models.Modifier.IDF` is critical — Qdrant maintains collection-level IDF statistics automatically. The BM25 implementation omits IDF from the sparse vector values, expecting Qdrant to apply it at query time.

### Upsert with both vector types

```python
client.upsert(
    collection_name="skill_bank_v2",
    points=[
        models.PointStruct(
            id=skill_id,
            payload=existing_payload,  # preserve all skill metadata
            vector={
                "dense": dense_embedding,           # list[float], 1024-dim
                "sparse": models.Document(
                    text=skill_text,
                    model="Qdrant/bm25",            # server-side tokenization
                ),
            },
        ),
    ],
)
```

Requires Qdrant ≥ 1.15.2 for `models.Document` server-side BM25.

### Migration script flow

```
1. Create skill_bank_v2 with named vector config
2. Scroll all points from skill_bank (old 384-dim collection)
3. For each point:
   a. Extract text from payload (text_preview or description field)
   b. Re-embed with Qwen3-Embedding (1024-dim dense)
   c. Upsert to skill_bank_v2 with dense + sparse (models.Document)
4. Validate: run 20 test queries against both collections, compare top-3
5. Create alias: skill_bank_active → skill_bank_v2
6. Drop old skill_bank collection
```

At <50 skills, the full migration takes seconds.

---

## 3. Hybrid Search with RRF Fusion (`adapters/vector_qdrant.py`)

### Query-time hybrid search

```python
async def search(
    self,
    collection: str,
    query: str,
    top_k: int = 5,
) -> list[VectorSearchHit]:
    """Hybrid search — dense + BM25 with RRF fusion.
    
    Port signature unchanged. Hybrid logic is adapter-internal.
    """
    # Step 1: Embed query via Qwen3-Embedding
    query_dense = await self._embed_client.embed(
        [query], is_query=True
    )
    
    # Step 2: Two-branch prefetch + RRF fusion
    results = self._qdrant.query_points(
        collection_name=collection,
        prefetch=[
            models.Prefetch(
                query=query_dense[0],
                using="dense",
                limit=top_k * 4,  # overfetch for fusion quality
            ),
            models.Prefetch(
                query=models.Document(
                    text=query,
                    model="Qdrant/bm25",
                ),
                using="sparse",
                limit=top_k * 4,
            ),
        ],
        query=models.RrfQuery(rrf=models.Rrf(k=60)),  # standard RRF constant
        limit=top_k,
        with_payload=True,
    )
    
    # Step 3: Convert to VectorSearchHit (existing return type)
    return [
        VectorSearchHit(
            id=str(point.id),
            score=point.score,
            payload=point.payload or {},
        )
        for point in results.points
    ]
```

### RRF formula

Reciprocal Rank Fusion merges two ranked lists:

```
RRF_score(d) = Σ_i  1 / (k + rank_i(d))
```

Where `k=60` (Qdrant default for `Rrf(k=60)`) and `rank_i(d)` is the rank of document `d` in the i-th result list. Documents found by both branches get boosted. Documents found by only one branch still appear but with lower scores.

### Performance at <500 entries

Qdrant uses brute-force scan below its indexing threshold. Both dense and sparse searches complete in sub-millisecond time. Hybrid search adds two parallel scans + fusion — still under 1ms total.

---

## 4. Knowledge Graph Schema (`adapters/knowledge_graph.py`)

### Table definitions

See `plan.md` for the full CREATE TABLE statements. Key design decisions:

**Bi-temporal edges.** Every edge has `valid_at` (when the fact was true in the real world) and `invalid_at` (when it stopped being true). Old edges are invalidated, never deleted. This follows the Graphiti model from the implementation reference.

**Six starter predicates.** `DEPENDS_ON`, `ENABLES`, `IMPLEMENTS`, `VALIDATES`, `MIGRATED_TO`, `FAILED_ON`. These cover the patterns the Archivist currently extracts for stall detection. Extensible via `config/formicos.yaml`.

**Entity types.** `MODULE`, `CONCEPT`, `SKILL`, `TOOL`, `PERSON`, `ORGANIZATION`. Matches the extraction schema from the implementation reference.

### Entity resolution algorithm

```python
async def resolve_entity(
    self,
    name: str,
    entity_type: str,
    workspace_id: str,
) -> str:
    """Find or create an entity. Deduplicates by name similarity.
    
    Returns the entity ID (existing or new).
    """
    # Step 1: Normalize
    normalized = name.strip().lower().replace("_", " ")
    
    # Step 2: Exact match
    existing = await self._find_by_name(normalized, workspace_id)
    if existing:
        return existing.id
    
    # Step 3: Fuzzy match via embedding similarity
    candidates = await self._find_similar(
        name=name,
        workspace_id=workspace_id,
        threshold=0.85,  # from config
    )
    
    if not candidates:
        # No match — create new entity
        return await self._create_entity(name, entity_type, workspace_id)
    
    if len(candidates) == 1 and candidates[0].similarity >= 0.95:
        # High confidence — auto-merge
        return candidates[0].id
    
    # Step 4: LLM confirmation for ambiguous cases
    # Gemini Flash, 500ms timeout, same pattern as Queen naming (Wave 11)
    confirmed = await self._llm_confirm_merge(name, candidates)
    if confirmed:
        return confirmed.id
    
    return await self._create_entity(name, entity_type, workspace_id)
```

### BFS neighbor traversal

```python
async def get_neighbors(
    self,
    entity_id: str,
    depth: int = 1,
    workspace_id: str | None = None,
) -> list[KGTriple]:
    """1-hop BFS from an entity. Returns relationship triples.
    
    At <1000 nodes, this completes in <1ms.
    """
    query = """
        SELECT e.id, e.predicate, e.from_node, e.to_node,
               n1.name as from_name, n2.name as to_name
        FROM kg_edges e
        JOIN kg_nodes n1 ON e.from_node = n1.id
        JOIN kg_nodes n2 ON e.to_node = n2.id
        WHERE (e.from_node = ? OR e.to_node = ?)
          AND e.invalid_at IS NULL
    """
    params = [entity_id, entity_id]
    if workspace_id:
        query += " AND e.workspace_id = ?"
        params.append(workspace_id)
    
    async with aiosqlite.connect(self._db_path) as db:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
    
    return [KGTriple(
        subject=row["from_name"],
        predicate=row["predicate"],
        object=row["to_name"],
    ) for row in rows]
```

---

## 5. Graph-Augmented Retrieval (`engine/context.py`)

### RetrievalPipeline

```python
class RetrievalPipeline:
    """Orchestrates hybrid vector search + KG graph traversal.
    
    Injected from surface/app.py with both vector_port and kg_adapter.
    """
    
    def __init__(
        self,
        vector_port: VectorPort,
        kg_adapter: KnowledgeGraphAdapter,
    ):
        self._vectors = vector_port
        self._kg = kg_adapter
    
    async def search(
        self,
        workspace_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        """Three-stage retrieval: entity extraction → parallel search → merge."""
        
        # Stage 1: Extract entity mentions from query
        known_entities = await self._kg.search_entities(
            text=query,
            workspace_id=workspace_id,
        )
        
        # Stage 2a: Hybrid vector search (adapter internally does dense + BM25 + RRF)
        vector_hits = await self._vectors.search(
            collection=f"skill_bank_v2",
            query=query,
            top_k=top_k,
        )
        
        # Stage 2b: KG graph traversal for matched entities
        kg_context = []
        for entity in known_entities[:3]:  # limit to top 3 entity matches
            neighbors = await self._kg.get_neighbors(
                entity_id=entity.id,
                depth=1,
                workspace_id=workspace_id,
            )
            kg_context.extend(neighbors)
        
        # Stage 3: Merge — vector hits are primary, KG provides enrichment
        results = []
        for hit in vector_hits:
            results.append(RetrievalResult(
                skill=hit,
                kg_context=[
                    t for t in kg_context
                    if t.subject in hit.payload.get("text_preview", "")
                    or t.object in hit.payload.get("text_preview", "")
                ],
            ))
        
        return results
```

### Integration into context assembly

The existing `engine/context.py` context assembly calls `vector_port.search()` for skill injection. Replace that call with `retrieval_pipeline.search()`. The retrieval result includes both the skill text (for the agent's context window) and KG relationship triples (appended as structured context).

```python
# Before (existing):
skills = await self.vector_port.search(namespace, goal, top_k=3)
skill_text = "\n".join(s.content for s in skills)

# After (Wave 13):
results = await self.retrieval_pipeline.search(workspace_id, goal, top_k=3)
skill_text = "\n".join(r.skill.payload.get("text_preview", "") for r in results)
kg_text = "\n".join(
    f"  {t.subject} {t.predicate} {t.object}"
    for r in results for t in r.kg_context
)
if kg_text:
    skill_text += f"\n\nRelated knowledge:\n{kg_text}"
```

---

## 6. Queen Intent Parser (`adapters/queen_intent_parser.py`)

### Two-pass architecture

```
Queen LLM output
  │
  ├──► Pass 1: Defensive parser (existing, Wave 10)
  │     ├── tool_call block found → extract structured directive → done
  │     └── no tool_call → fall through to Pass 2
  │
  └──► Pass 2: Intent parser (new, Wave 13)
        ├── Regex match → extract directive fields → done
        └── No regex match → Gemini Flash classification (500ms) → done or "no directive"
```

### Regex patterns

**Build from real failure data.** These are starter patterns — the actual regex should be refined against the 20+ collected failure outputs.

```python
import re

INTENT_PATTERNS = {
    "SPAWN": re.compile(
        r"(?i)(?:let(?:'s|\s+us)?|I(?:'ll|\s+will)?|we\s+should|going\s+to)?\s*"
        r"(?:spawn|create|start|launch|kick\s+off)\s+"
        r"(?:a\s+)?(?:new\s+)?(?:colony|team|task)\s+"
        r"(?:for|to|targeting|focused\s+on)\s+"
        r"(.+?)(?:\.|$)",
        re.DOTALL,
    ),
    "KILL": re.compile(
        r"(?i)(?:kill|terminate|stop|abort|shut\s+down)\s+"
        r"(?:the\s+)?(?:colony\s+)?(\S+)",
    ),
    "REDIRECT": re.compile(
        r"(?i)(?:redirect|refocus|pivot|change)\s+"
        r"(?:the\s+)?(?:colony\s+)?(\S+)\s+"
        r"(?:to|toward|towards)\s+"
        r"(.+?)(?:\.|$)",
        re.DOTALL,
    ),
    "APOPTOSIS": re.compile(
        r"(?i)(?:colony\s+)?(\S+)\s+"
        r"(?:should|can|is\s+ready\s+to)\s+"
        r"(?:self[- ]terminate|complete|finish|wrap\s+up)",
    ),
}


def parse_intent(text: str) -> dict | None:
    """Try to extract a directive from Queen prose output.
    
    Returns None if no intent detected.
    Returns dict with 'action' and action-specific fields if found.
    """
    for action, pattern in INTENT_PATTERNS.items():
        match = pattern.search(text)
        if match:
            if action == "SPAWN":
                return {"action": "SPAWN", "objective": match.group(1).strip()}
            elif action == "KILL":
                return {"action": "KILL", "colony_id": match.group(1).strip()}
            elif action == "REDIRECT":
                return {"action": "REDIRECT", "colony_id": match.group(1).strip(), "new_objective": match.group(2).strip()}
            elif action == "APOPTOSIS":
                return {"action": "APOPTOSIS", "colony_id": match.group(1).strip()}
    return None
```

### Gemini Flash classification fallback

When regex returns `None`, call Gemini Flash with a classification prompt:

```python
CLASSIFY_PROMPT = """Classify the following Queen agent output into one of these actions:
- SPAWN: The Queen wants to create a new colony for a task
- KILL: The Queen wants to terminate a colony  
- REDIRECT: The Queen wants to change a colony's focus
- APOPTOSIS: The Queen says a colony should self-terminate
- NONE: No clear directive

Output ONLY a JSON object: {"action": "SPAWN|KILL|REDIRECT|APOPTOSIS|NONE", "details": "..."}

Queen output:
{text}"""
```

500ms timeout. If timeout or parse failure, return `None` (no directive detected). This matches the Queen naming pattern from Wave 11 — same Gemini Flash endpoint, same timeout, same fallback-to-nothing behavior.

### Logging

Every fallback invocation logged:
```python
logger.info(
    "queen_intent_parsed",
    action=result["action"],
    via="regex" if regex_matched else "gemini_flash",
    text_preview=text[:100],
)
```

The `via` field is what the frontend uses to show the "parsed from intent" badge (Wave 14 colony chat, but the field is available in structlog now).
