# Wave 13 Planning Findings

**Wave:** 13 — "Sharper Memory"
**Author:** Planning session, 2026-03-14
**Status:** Ready for dispatch

---

## What Wave 12 Left Us

Wave 12 was frontend-only. The prototype (`docs/prototype/formicos-v3.jsx`) is the visual spec for the production Lit implementation. Backend was frozen. After Wave 12, the system is feature-complete for alpha — an operator who didn't build it could use it.

Current baseline:
- **27 event types** in `core/events.py` (opened once in Wave 11)
- **5 port protocols** in `core/ports.py` (frozen since Phase 2)
- **672+ tests**, layer lint enforced
- Qdrant backend (Wave 10), Gemini adapter (Wave 10), defensive parser (Wave 10)
- Beta confidence, templates, suggest-team, colony naming (Wave 11)
- Embedding: `snowflake-arctic-embed-s` (384-dim) via `sentence-transformers`
- LanceDB retained as dead-code fallback

---

## Key Findings

### 1. The rough Waves 13–14 outline used wrong module names

6+ file references pointed to modules that don't exist:
- `engine/compute_router.py` → actual: `surface/runtime.py` (`LLMRouter` class)
- `surface/routes/suggest_team.py` → actual: route is in `surface/app.py`
- `surface/routes/colony.py` → actual: spawn logic in `surface/commands.py`
- No `engine/views.py` — view state lives in `surface/view_state.py`
- No `engine/retrieval.py` — context assembly is in `engine/context.py`

All dispatch docs rewritten against the real repo.

### 2. CasteSlot / subcaste tiers is a full-stack migration

Current spawn flow is string-caste based everywhere: WS command (`casteNames: list[str]`), `surface/commands.py`, `surface/runtime.py` (`Runtime.build_agents()`), `core/events.py` (`ColonySpawned` carries `caste_names`), `surface/projections.py`, `surface/view_state.py`, `frontend/src/types.ts`, `config/templates/*.yaml`.

Moving to structured `CasteSlot(caste, tier, count)` touches 14+ files across all four layers plus frontend. **Deferred to Wave 14.**

### 3. VectorPort.search() can stay unchanged

Current contract: `async def search(self, collection: str, query: str, top_k: int = 5) -> list[VectorSearchHit]`

Hybrid search (dense + BM25 + KG graph) works inside the adapter without changing this signature. The adapter receives the `query` string, internally does (1) embed via Qwen3-Embedding, (2) dense prefetch, (3) BM25 prefetch, (4) KG entity match + BFS, (5) RRF fusion, (6) returns `list[VectorSearchHit]` as before. The caller in `engine/context.py` sees no difference.

Explicit search-mode control (dense-only, sparse-only, graph-only) is a Wave 14 port extension if needed.

### 4. KG events should defer to Wave 14

The knowledge graph in Wave 13 is infrastructure — SQLite tables for Archivist TKG output, queried during retrieval. The operator can't see, browse, or act on it yet. Adding events (`KnowledgeEntityCreated` etc.) in Wave 13 means opening the event union, writing projection handlers, updating contract mirrors, and updating frontend types — for zero operator surface.

**Decision:** KG stays storage-only in Wave 13. The Archivist writes TKG tuples directly to `adapters/knowledge_graph.py` via method call. Events open in Wave 14 alongside chat/service/sandbox events as one coordinated batch.

### 5. Wave 13 should touch zero contract files

Concentrating all event-union changes in Wave 14 means one contract freeze-break instead of two. Wave 13 coders never open `core/events.py`, `core/ports.py`, or `core/types.py`. They work in `adapters/`, `engine/context.py`, `engine/runner.py`, `surface/queen_runtime.py`, and existing surface wiring files.

---

## Contract Opening Math

| File | Wave 13 Delta | Wave 14 Delta |
|------|---------------|---------------|
| `core/events.py` | **0** | **+8** (27→35) |
| `core/ports.py` | **0** | **+1** signature extension |
| `core/types.py` | **0** | **+3 enums, +1 dataclass** |
| `docs/contracts/*` | **0** | Mirror all Wave 14 changes |
| `frontend/src/types.ts` | **0** | Mirror all Wave 14 changes |

---

## Wave 13 / Wave 14 Boundary

**Wave 13** = infra + retrieval + Queen reliability + cleanup + frontend visibility
- Zero contract changes
- Embedding upgrade (adapter + infra)
- Hybrid search (adapter-internal)
- KG storage (adapter, no events)
- Graph-augmented retrieval (engine-internal)
- Queen fallback parser (adapter)
- LanceDB removal (cleanup)
- Frontend: Knowledge view, diagnostics, fallback badges

**Wave 14** = contract + mechanics wave
- Event union: 27→35 (8 new events in one batch)
- Port: VectorPort.search() signature extension
- Types: SubcasteTier, CasteSlot, ChatSender, ServiceColonyType
- CasteSlot full-stack migration
- Sandbox adapter + code_execute
- Egress gateway + web tools
- Service colonies
- Per-colony chat
- Colony Creator overhaul
- Template library (7 tier-aware templates)

---

## Docs Written

- `docs/waves/wave_13/plan.md` — dispatch with file ownership, merge order, acceptance criteria
- `docs/waves/wave_13/algorithms.md` — hybrid search RRF, entity resolution, KG schema, Queen fallback
- `docs/waves/wave_13/planning_findings.md` — this document
- `docs/decisions/019-hybrid-search-adapter-internal.md` — VectorPort stays unchanged
- No `.feature` specs (Wave 13 is infra/adapter work, no behavior changes needing Gherkin)
- No `orchestrator_prompt.md` (standard 3-coder dispatch, same pattern as Waves 10–11)

---

## Reference Docs in Project Knowledge

These existing documents contain implementation details for Wave 13 algorithms:

| Doc | Relevant content |
|---|---|
| `Hybrid_Vector_Retrieval_for_FormicOS.md` | Qwen3-Embedding sidecar config, Qdrant BM25 setup, RRF parameters, migration script |
| `FormicOS_Implementation_Reference.md` | KG SQLite schema (Graphiti-inspired bi-temporal model), entity resolution patterns |
| `Tool-Calling_Reliability_in_Local_LLMs.md` | Queen tool-call failure modes on Qwen3-30B-A3B |
