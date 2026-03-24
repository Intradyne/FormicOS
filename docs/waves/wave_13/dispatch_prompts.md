# Wave 13 Dispatch Prompts

These prompts assume:
- shared workspace
- no git branches
- coders must obey root `AGENTS.md`
- Wave 13 contracts remain frozen

Use the launch order below to reduce overlap risk.

---

## Launch order

### Phase A
1. Launch A-T1 immediately.
2. Launch A-T3 immediately, but A-T3 must not edit `config/formicos.yaml` until A-T1 is done.
3. Launch A-T2 only after A-T1 has landed.

### Phase B
1. Start only after Phase A is green.
2. Launch B-T1 and B-T2 immediately.
3. Launch B-T3 after B-T2 lands, because both touch `src/formicos/surface/app.py`.

### Phase C
1. Start only after Phase B is green.
2. Launch C-T1, C-T2, and C-T3 in parallel.
3. If C-T1 and C-T2 both need final backend polish, C-T2 lands first and C-T1 takes the last small pass on `src/formicos/surface/app.py`.

---

## Phase A - T1 Prompt

```text
# Wave 13 Phase A - T1: Embedding Sidecar + Collection Migration

Working directory: C:\Users\User\FormicOSa

Read first:
1. CLAUDE.md
2. AGENTS.md
3. docs/decisions/013-qdrant-migration.md
4. docs/decisions/019-hybrid-search-adapter-internal.md
5. docs/waves/wave_13/planning_findings.md
6. docs/waves/wave_13/plan.md
7. docs/waves/wave_13/algorithms.md
8. src/formicos/adapters/vector_qdrant.py
9. config/formicos.yaml
10. docker-compose.yml

You own:
- src/formicos/adapters/embedding_qwen3.py
- scripts/migrate_skill_bank_v2.py
- docker-compose.yml
- config/formicos.yaml (embedding section only)

Do NOT touch:
- src/formicos/core/*
- src/formicos/engine/*
- src/formicos/surface/*
- frontend/*
- docs/contracts/*
- src/formicos/adapters/vector_qdrant.py

Mission:
Deploy Qwen3-Embedding-0.6B as the Wave 13 embedding sidecar and migrate the skill bank to a new 1024-dim hybrid-ready Qdrant collection.

Required behavior:
- llama.cpp sidecar on port 8200
- query instruction prefix
- append <|endoftext|> to all inputs
- manual L2 normalization
- create skill_bank_v2 with named dense+sparse vectors
- one-shot re-embed + alias swap migration

Shared-workspace rule:
- you are the first editor of config/formicos.yaml this phase
- once done, report clearly so A-T3 can take the KG config pass

Validation:
- run the targeted validation you judge appropriate for the new adapter/script
- if docker or live migration cannot be run, say so explicitly

Report back with:
- files changed
- exact embedding endpoint/config added
- migration flow implemented
- whether config/formicos.yaml is now safe for A-T3 to edit
```

## Phase A - T2 Prompt

```text
# Wave 13 Phase A - T2: Hybrid Search

Working directory: C:\Users\User\FormicOSa

Dependency:
Start coding only after A-T1 lands. You depend on the new collection shape and embedding client.

Read first:
1. CLAUDE.md
2. AGENTS.md
3. docs/decisions/013-qdrant-migration.md
4. docs/decisions/019-hybrid-search-adapter-internal.md
5. docs/waves/wave_13/planning_findings.md
6. docs/waves/wave_13/plan.md
7. docs/waves/wave_13/algorithms.md
8. src/formicos/adapters/vector_qdrant.py
9. src/formicos/core/ports.py (read-only contract)

You own:
- src/formicos/adapters/vector_qdrant.py

Do NOT touch:
- src/formicos/core/*
- src/formicos/engine/*
- src/formicos/surface/*
- frontend/*
- docs/contracts/*
- config/*

Mission:
Upgrade the Qdrant adapter to hybrid retrieval using dense + BM25 + RRF, without changing the VectorPort contract.

Required behavior:
- no port signature change
- use models.Document for BM25 sparse branch
- named vectors: dense + sparse
- prefetch both branches
- fuse with RRF
- keep return type unchanged

Key constraint:
- all hybrid behavior must stay adapter-internal per ADR-019

Validation:
- run targeted adapter tests and any existing retrieval tests you touch

Report back with:
- files changed
- exact hybrid query flow implemented
- confirmation that VectorPort.search() signature stayed unchanged
- validation result
```

## Phase A - T3 Prompt

```text
# Wave 13 Phase A - T3: Knowledge Graph Storage

Working directory: C:\Users\User\FormicOSa

Read first:
1. CLAUDE.md
2. AGENTS.md
3. docs/waves/wave_13/planning_findings.md
4. docs/waves/wave_13/plan.md
5. docs/waves/wave_13/algorithms.md
6. src/formicos/engine/runner.py
7. config/formicos.yaml

You own:
- src/formicos/adapters/knowledge_graph.py
- src/formicos/engine/runner.py (small KG write only)
- config/formicos.yaml (KG section only)

Do NOT touch:
- src/formicos/core/*
- src/formicos/surface/*
- frontend/*
- docs/contracts/*
- src/formicos/engine/context.py

Shared-workspace rule:
- do not edit config/formicos.yaml until A-T1 has landed
- reread config/formicos.yaml immediately before editing

Mission:
Add durable SQLite-backed knowledge graph storage for Archivist tuples without opening the event union.

Required behavior:
- kg_nodes and kg_edges tables
- bi-temporal edge model
- entity resolution with similarity threshold
- 1-hop BFS helper
- runner hook that writes Archivist tuples after compress
- no event emission

Validation:
- run targeted tests for CRUD/entity resolution/BFS and any runner tests you touch

Report back with:
- files changed
- schema created
- exact runner hook location
- confirmation that no new events were introduced
- validation result
```

## Phase B - T1 Prompt

```text
# Wave 13 Phase B - T1: Queen Deterministic Fallback

Working directory: C:\Users\User\FormicOSa

Start only after Phase A is green.

Read first:
1. CLAUDE.md
2. AGENTS.md
3. docs/waves/wave_13/planning_findings.md
4. docs/waves/wave_13/plan.md
5. docs/waves/wave_13/algorithms.md
6. src/formicos/surface/queen_runtime.py
7. src/formicos/adapters/parse_defensive.py

You own:
- src/formicos/adapters/queen_intent_parser.py
- src/formicos/surface/queen_runtime.py

Do NOT touch:
- src/formicos/core/*
- src/formicos/engine/*
- src/formicos/surface/app.py
- frontend/*
- docs/contracts/*

Mission:
Make the Queen reliable on weaker local models by adding a deterministic fallback when prose appears instead of tool calls.

Required behavior:
- first gather or encode real failure fixtures
- primary path stays the existing defensive tool-call parse
- fallback path uses regex intent detection
- Gemini Flash fallback classifier only for ambiguous prose
- emit the same downstream actions/events as the primary path

Validation:
- run targeted tests for the parser and any Queen/runtime tests you touch

Report back with:
- files changed
- failure fixture coverage
- fallback decision order
- validation result
```

## Phase B - T2 Prompt

```text
# Wave 13 Phase B - T2: LanceDB Removal + Dependency Audit

Working directory: C:\Users\User\FormicOSa

Start only after Phase A is green.

Read first:
1. CLAUDE.md
2. AGENTS.md
3. docs/decisions/013-qdrant-migration.md
4. docs/waves/wave_13/planning_findings.md
5. docs/waves/wave_13/plan.md
6. docs/waves/wave_13/algorithms.md
7. pyproject.toml
8. src/formicos/surface/app.py
9. src/formicos/adapters/vector_lancedb.py
10. src/formicos/engine/runner.py

You own:
- pyproject.toml
- src/formicos/adapters/vector_lancedb.py (delete)
- config/formicos.yaml (vector backend cleanup only)
- src/formicos/surface/app.py (remove LanceDB wiring only)
- optionally src/formicos/engine/runner.py only if you prove sentence-transformers can be removed

Do NOT touch:
- src/formicos/core/*
- src/formicos/engine/context.py
- src/formicos/surface/queen_runtime.py
- frontend/*
- docs/contracts/*

Shared-workspace rule:
- B-T3 also needs src/formicos/surface/app.py later
- you own the first pass on app.py; report when it is safe for B-T3 to take the second pass

Mission:
Remove dead LanceDB fallback code and evaluate whether sentence-transformers can also be removed safely.

Required behavior:
- remove lancedb dependency and adapter
- remove dead bootstrap/config wiring
- measure DyTopo embedding latency before removing sentence-transformers
- only remove sentence-transformers if the measured replacement is acceptable

Validation:
- run full Python validation if feasible, because dependency removal is cross-cutting

Report back with:
- files changed
- dependencies removed
- measured latency result for sentence-transformers replacement
- whether B-T3 can now safely edit src/formicos/surface/app.py
- validation result
```

## Phase B - T3 Prompt

```text
# Wave 13 Phase B - T3: Graph-Augmented Retrieval

Working directory: C:\Users\User\FormicOSa

Start only after:
- Phase A is green
- B-T2 has landed its app.py cleanup pass

Read first:
1. CLAUDE.md
2. AGENTS.md
3. docs/decisions/019-hybrid-search-adapter-internal.md
4. docs/waves/wave_13/planning_findings.md
5. docs/waves/wave_13/plan.md
6. docs/waves/wave_13/algorithms.md
7. src/formicos/engine/context.py
8. src/formicos/surface/app.py
9. src/formicos/adapters/knowledge_graph.py

You own:
- src/formicos/engine/context.py
- src/formicos/surface/app.py (KG injection only)

Do NOT touch:
- src/formicos/core/*
- pyproject.toml
- src/formicos/surface/queen_runtime.py
- frontend/*
- docs/contracts/*

Mission:
Add RetrievalPipeline orchestration that combines hybrid vector retrieval with KG entity lookup/BFS, while keeping VectorPort unchanged.

Required behavior:
- retrieval orchestration lives in engine/context.py
- dependencies injected from surface/app.py
- no port changes
- merge vector and KG context cleanly
- backward-compatible output for context assembly

Validation:
- run targeted context/retrieval tests and any integration tests you add for richer retrieval

Report back with:
- files changed
- exact RetrievalPipeline design
- confirmation that src/formicos/surface/app.py was reread after B-T2
- validation result
```

## Phase C - T1 Prompt

```text
# Wave 13 Phase C - T1: Knowledge View

Working directory: C:\Users\User\FormicOSa

Start only after Phase B is green.

Read first:
1. CLAUDE.md
2. AGENTS.md
3. docs/prototype/formicos-v3.jsx
4. docs/waves/wave_13/plan.md
5. docs/waves/wave_13/algorithms.md
6. frontend/src/components/*
7. src/formicos/surface/app.py

You own:
- new frontend knowledge view component(s)
- src/formicos/surface/app.py (GET /api/v1/knowledge only)

Do NOT touch:
- src/formicos/core/*
- src/formicos/surface/queen_runtime.py
- src/formicos/surface/commands.py
- src/formicos/surface/projections.py
- docs/contracts/*
- frontend/src/types.ts

Mission:
Ship the Wave 13 Knowledge view and the backing REST route, using the existing backend/storage shape.

Required behavior:
- skills + graph tabbed view
- route returns KG nodes/edges for a workspace
- frontend matches the prototype direction in formicos-v3.jsx
- degrade gracefully if no KG data exists yet

Validation:
- run frontend build
- run targeted backend tests for the new route

Report back with:
- files changed
- route shape
- build/test result
```

## Phase C - T2 Prompt

```text
# Wave 13 Phase C - T2: Retrieval Diagnostics

Working directory: C:\Users\User\FormicOSa

Start only after Phase B is green.

Read first:
1. CLAUDE.md
2. AGENTS.md
3. docs/prototype/formicos-v3.jsx
4. docs/waves/wave_13/plan.md
5. docs/waves/wave_13/algorithms.md
6. src/formicos/engine/context.py
7. frontend/src/components/*

You own:
- new frontend diagnostics component(s)
- src/formicos/engine/context.py (timing/logging only)

Do NOT touch:
- src/formicos/core/*
- src/formicos/surface/app.py
- src/formicos/surface/queen_runtime.py
- docs/contracts/*
- frontend/src/types.ts

Mission:
Expose real retrieval-stage timing and diagnostic visibility without changing contracts.

Required behavior:
- stage timing for embedding, vector search, graph traversal, fusion, total
- diagnostics UI that reflects real data
- no contract/type changes

Validation:
- run frontend build
- run targeted retrieval/context tests

Report back with:
- files changed
- exact timing points added
- build/test result
```

## Phase C - T3 Prompt

```text
# Wave 13 Phase C - T3: Queen Fallback Visibility

Working directory: C:\Users\User\FormicOSa

Start only after Phase B is green.

Read first:
1. CLAUDE.md
2. AGENTS.md
3. docs/prototype/formicos-v3.jsx
4. docs/waves/wave_13/plan.md
5. frontend/src/components/*

You own:
- frontend colony/chat components for fallback badges
- frontend skill browser polish for embedding-model visibility

Do NOT touch:
- any backend file
- docs/contracts/*
- frontend/src/types.ts

Mission:
Surface the Queen intent-parser fallback path and the upgraded embedding/retrieval context in the UI.

Required behavior:
- fallback badge on parsed-from-intent directives
- embedding model visibility in the skill browser
- no backend contract assumptions beyond existing Wave 13 backend outputs

Validation:
- run frontend build

Report back with:
- files changed
- badge/model visibility behavior added
- build result
```
