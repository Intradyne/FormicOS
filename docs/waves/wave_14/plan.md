# Wave 14 Plan: Dispatch Document

**Status:** Dispatch-ready  
**Theme:** Ready for Real Work  
**Streams:** A (foundation, sequential) -> B (safety) / C (chat + services + frontend) / D (hardening)  
**Event union:** 27 -> 35  
**Ports:** `core/ports.py` remains frozen

---

## Wave boundary

Wave 14 is the contract and mechanics wave that follows Wave 13's infra/retrieval work.

Wave 14 owns:
- structured castes and tiered spawn flow
- colony chat persistence
- service colonies
- sandboxed code execution
- safety controls around tool use and iteration budgets
- template/schema migration needed to support the new spawn model

Wave 14 does not reopen:
- vector-port shape
- Wave 13 retrieval architecture
- LanceDB fallback
- old hardcoded skill-bank collection names

---

## Pre-requisites

These are real gates, not optional cleanup.

1. Qdrant upgrade (confirmed: >= 1.15.2 required, pin v1.16.2)
- Current deployment: `qdrant/qdrant:v1.14.0` in `docker-compose.yml`.
- Server-side BM25 via `models.Document(text=..., model="Qdrant/bm25")` requires Qdrant >= 1.15.2 (confirmed from official Qdrant docs).
- Change: `image: qdrant/qdrant:v1.16.2` (matches Python client version, one-line edit).
- After upgrade: re-upsert existing `skill_bank_v2` points with sparse vectors.
- Verify: both dense and sparse prefetch branches contribute real results to RRF fusion.
- See `docs/decisions/021-qdrant-upgrade-bm25.md`.

2. SGLang benchmark spike
- Run the benchmark spike before committing to a Stream D inference swap.
- If benchmark results are weak or operationally expensive, Stream D becomes documentation + verification rather than deployment.

3. Resolve sync embedding consumers (ADR-025)
- Three sync consumers are degraded: convergence (Jaccard heuristic), stigmergic strategy (disabled, sequential fallback), KG entity resolution (exact match only).
- Resolution: add `async_embed_fn` parameter alongside `embed_fn` in all three consumers. Wire `Qwen3Embedder.embed` as the async path. Sync path remains as test fallback.
- Stream B implements this since it owns runner.py and strategy modifications.
- See `docs/decisions/025-sync-embedding-resolution.md` for exact implementation.

4. Keep KG visibility honest
- KG accumulation still depends on Archivist participation.
- Any Wave 14 verification path that expects visible KG data must use a template/recipe that actually includes Archivist.

---

## Contract math

Baseline before Wave 14:
- event union: 27
- type layer: current repo-native `pydantic.BaseModel` / `StrEnum` style in `core/types.py`
- ports: unchanged

Wave 14 contract opening:
- event union: 27 -> 35
- new types in `core/types.py`:
  - `SubcasteTier`
  - `CasteSlot`
  - `ChatSender`
  - `ToolCategory`
  - `CasteToolPolicy`
- modified event shape:
  - `ColonySpawned.caste_names: list[str]` -> `castes: list[CasteSlot]`
  - add `template_id`
- mirrors updated:
  - `docs/contracts/events.py`
  - `docs/contracts/types.ts`
  - `frontend/src/types.ts`

No port changes in Wave 14:
- `src/formicos/core/ports.py` stays frozen
- `docs/contracts/ports.py` stays frozen

New events to add:
- `ColonyChatMessage`
- `CodeExecuted`
- `ServiceQuerySent`
- `ServiceQueryResolved`
- `ColonyServiceActivated`
- `KnowledgeEntityCreated`
- `KnowledgeEdgeCreated`
- `KnowledgeEntityMerged`

---

## Repo-accurate seams

These are the live implementation seams. Plan against these, not against conceptual modules.

- HTTP routes live in `src/formicos/surface/app.py`
- WebSocket mutation lives in `src/formicos/surface/commands.py`
- runtime spawn/build/router logic lives in `src/formicos/surface/runtime.py`
- Queen orchestration lives in `src/formicos/surface/queen_runtime.py`
- colony lifecycle tracking lives in `src/formicos/surface/colony_manager.py`
- projections live in `src/formicos/surface/projections.py`
- view materialization lives in `src/formicos/surface/view_state.py`
- MCP tool registration lives in `src/formicos/surface/mcp_server.py`
- context assembly lives in `src/formicos/engine/context.py`
- round execution loop lives in `src/formicos/engine/runner.py`

Important correction:
- `Runtime.build_agents()` is in `src/formicos/surface/runtime.py`
- there is no existing `colony_manager.spawn()`
- there is no existing `colony_manager.inject_message()`; if Wave 14 uses it, Stream C creates it

---

## Stream A: Foundation

**One coder. Must land first.**

This is the contract-opening and spawn-migration pass.

### Scope

1. Replace `caste_names` with `castes: list[CasteSlot]`
2. Add Wave 14 event schemas
3. Add tier-aware routing input at the runtime layer
4. Migrate template format
5. Update contract mirrors and frontend type mirrors

### File order

| Order | File | Change |
|---|---|---|
| 1 | `src/formicos/core/types.py` | Add `SubcasteTier`, `CasteSlot`, `ChatSender` using repo-native Pydantic models and `StrEnum` |
| 2 | `src/formicos/core/events.py` | Add 8 events, update `ColonySpawned` |
| 3 | `src/formicos/surface/runtime.py` | Update `Runtime.build_agents()` and `LLMRouter.route()` tier override |
| 4 | `src/formicos/surface/commands.py` | Spawn WS payload now parses `castes` |
| 5 | `src/formicos/surface/mcp_server.py` | Update `spawn_colony`; add template listing/detail tools; update `suggest_team` output shape |
| 6 | `src/formicos/surface/colony_manager.py` | Remove remaining `caste_names` assumptions from lifecycle tracking |
| 7 | `src/formicos/surface/projections.py` | Update `ColonySpawned` handler; add event-handler stubs |
| 8 | `src/formicos/surface/view_state.py` | Snapshot adds `tier`, `template_id`; add `ColonyChatViewRegistry` skeleton |
| 9 | `src/formicos/surface/template_manager.py` | Edit: migrate `caste_names` to `castes: list[CasteSlot]`, add `governance:` block parsing. Module already exists from Wave 11 (ADR-016). |
| 10 | `config/templates/*.yaml` | New schema using `castes:` + `governance:` |
| 11 | `frontend/src/types.ts` | Mirror types and payload changes |
| 12 | `docs/contracts/events.py` | Mirror event changes |
| 13 | `docs/contracts/types.ts` | Mirror type changes |
| 14 | Tests | Remove all `caste_names` assumptions |

### Deliverables

- all `caste_names` references removed from live code and mirrors
- event union at 35
- template manager present
- template YAML migrated
- spawn payload moved to `castes`
- projection stubs added for all new events

### Validation

```bash
rg -n "caste_names" src frontend tests docs/contracts
uv run pyright src/formicos/core/types.py src/formicos/core/events.py src/formicos/surface/runtime.py
pytest
cd frontend && npm run build
```

---

## Stream B: Safety

**Starts after Stream A lands `core/types.py`, `core/events.py`, and `surface/runtime.py`.**

### Scope

1. Per-caste iteration caps and time limits
2. Tool permission enforcement
3. Budget regime injection
4. Sandboxed code execution
5. Provider cooldown cache
6. Structured LLM call logging
7. Sync embedding resolution (ADR-025): add `async_embed_fn` to RoundRunner, StigmergicStrategy, KnowledgeGraphAdapter. Wire `Qwen3Embedder.embed`. Add `embed_client` to `Runtime`.

### Files

| File | Change |
|---|---|
| `src/formicos/engine/runner.py` | Iteration caps, tool-permission enforcement, sandbox event/chat emission |
| `src/formicos/engine/context.py` | Budget regime injection |
| `src/formicos/surface/runtime.py` | Cooldown helpers on `LLMRouter` |
| `src/formicos/core/types.py` | Add `ToolCategory`, `CasteToolPolicy` in a second pass after Stream A |
| `config/caste_recipes.yaml` | Add per-caste execution limits |
| `src/formicos/adapters/sandbox_manager.py` | New |
| `src/formicos/adapters/ast_security.py` | New |
| `src/formicos/adapters/output_sanitizer.py` | New |
| `src/formicos/surface/mcp_server.py` | Register `code_execute` |
| `Dockerfile.sandbox` | New |

### Deliverables

- iteration/time guards with graceful degradation
- deny-by-default tool permission checks
- budget regime block in agent prompts
- `code_execute` wired through sandbox manager
- `CodeExecuted` events emitted
- provider cooldown logic documented and implemented
- measured decision on sync embedding consumers

### Specs

- `docs/specs/wave_14_safety.feature`
- `docs/specs/wave_14_sandbox.feature`

---

## Stream C: Colony Chat + Service Colonies + Frontend

**Starts after Stream A is fully green.**

### Scope

1. Colony chat persistence and materialization
2. Service-colony lifecycle and query routing
3. Frontend support for creator/chat/service flows
4. Template "Save As" UX against the migrated schema

### Files

| File | Change |
|---|---|
| `src/formicos/engine/service_router.py` | New `ServiceRouter` |
| `src/formicos/engine/runner.py` | Chat emission points and service-response detection only |
| `src/formicos/surface/commands.py` | `chat_colony` WS command |
| `src/formicos/surface/mcp_server.py` | Register `query_service`, `activate_service`, `chat_colony` |
| `src/formicos/surface/colony_manager.py` | Add `inject_message()` and `activate_service()` |
| `src/formicos/surface/projections.py` | Replace chat/service stubs |
| `src/formicos/surface/view_state.py` | Fill `ColonyChatViewRegistry` |
| `frontend/*` | Creator/chat/detail/service/template UI work |

### Deliverables

- `ColonyChatMessage` emission from system/operator/service paths
- persistent colony chat view rebuilt from replay
- service colony activation and query routing
- creator/detail/service UI updated to use `castes`
- template save flow aligned with the new schema

### Specs

- `docs/specs/wave_14_colony_chat.feature`
- `docs/specs/wave_14_service_colonies.feature`

---

## Stream D: Hardening

**Flexible timing. Prefer landing after Streams B/C stabilize.**

### Scope

1. KG event emission on top of the existing Wave 13 storage path
2. Qdrant BM25 verification after the pre-req upgrade
3. SGLang execution or explicit defer decision

### Files

| File | Change |
|---|---|
| `src/formicos/adapters/knowledge_graph.py` | Emit KG events alongside existing writes |
| `src/formicos/surface/projections.py` | Replace KG stubs |
| `docker-compose.yml` | Conditional SGLang deployment work |

### Deliverables

- KG events emitted from live storage paths
- Qdrant hybrid verification recorded after upgrade
- SGLang deployed or explicitly rejected with benchmark evidence

---

## Shared-workspace merge discipline

Overlap-prone files must merge in this order:

1. `src/formicos/core/types.py`
   - Stream A first
   - Stream B second

2. `src/formicos/surface/runtime.py`
   - Stream A first (`build_agents()`, `route()`)
   - Stream B second (cooldown helpers only)

3. `src/formicos/engine/runner.py`
   - Stream B first
   - Stream C second

4. `src/formicos/surface/projections.py`
   - Stream A stubs first
   - Stream C chat/service handlers
   - Stream D KG handlers

5. `src/formicos/surface/mcp_server.py`
   - Stream A tool/payload updates
   - Stream B `code_execute`
   - Stream C service/chat tools

6. `src/formicos/surface/colony_manager.py`
   - Stream A cleanup first
   - Stream C service/chat methods second

---

## Frozen files

| File | Reason |
|---|---|
| `src/formicos/core/ports.py` | No port changes in Wave 14 |
| `docs/contracts/ports.py` | Mirror of frozen ports |
| `src/formicos/adapters/vector_qdrant.py` | Wave 13 retrieval code stays stable; Wave 14 verifies environment support rather than reworking the adapter |
| `src/formicos/adapters/skill_dedup.py` | Stable Wave 11 feature |
| `src/formicos/adapters/store_sqlite.py` | No schema changes planned |
| `src/formicos/adapters/embedding_qwen3.py` | Stable Wave 13 adapter |

---

## Exit gate

- `rg -n "caste_names" src frontend tests docs/contracts` returns 0 matches
- event union is exactly 35
- all contract mirrors are updated
- `code_execute` works end-to-end through AST check, sandbox, and structured result
- budget regime injection is visible at all four thresholds
- tool denial returns a clear reason to the agent
- iteration cap hit produces graceful degradation and a chat message
- colony chat rebuilds from replay after restart
- at least one service colony answers a `query_service` call from a running colony
- creator payload uses `castes`
- tier routing is verified
- templates load in the new schema
- BM25 verification is real, not assumed
- all four Wave 14 specs pass
