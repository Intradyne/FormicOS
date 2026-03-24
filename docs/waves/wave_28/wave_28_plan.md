# Wave 28 Plan -- Knowledge Runtime Unification

**Wave:** 28 -- "Knowledge Runtime Unification"
**Theme:** Agents become knowledge-aware through the unified knowledge catalog. Knowledge access becomes replay-safe event truth. Progressive disclosure begins with two high-value agent tools. Legacy skill writes and confidence updates stop.
**Architectural thesis:** Surface resolves knowledge; engine consumes it. Layer discipline is maintained by threading normalized payloads through the existing call graph: `colony_manager -> run_round -> _run_agent -> assemble_context`.
**Contract changes:** Event union opens from 40 to 41 with one new event type: `KnowledgeAccessRecorded`. New frozen model `KnowledgeAccessItem` in `core/types.py`. Additive `knowledge_items` parameter on `run_round()` and `assemble_context()`. Additive `knowledge_items_used` field on `ContextResult` and `RoundResult`.
**Estimated LOC delta:** ~350 Python, ~60 TypeScript, ~20 YAML/config

---

## Why This Wave

Wave 27 unified the operator and Queen surfaces, but the execution layer still lives on legacy seams:

- `context.py` reads `skill_bank_v2` directly through the legacy `RetrievalPipeline`
- agent `memory_search` in `runner.py` searches scratch -> workspace -> `skill_bank_v2`
- `_crystallize_skills()` still writes to `skill_bank_v2` from two completion paths in `colony_manager.py` (lines 568 and 634)
- legacy confidence updates still run in `_post_colony_hooks()` (line 693) through `skill_lifecycle.update_skill_confidence()`
- agents cannot inspect a knowledge item or artifact on demand
- there is no durable record of what knowledge shaped agent execution

Wave 28 closes these gaps:

1. agents consume unified knowledge through the existing engine call graph
2. knowledge access becomes durable event truth
3. legacy skill writes and legacy confidence updates stop

After Wave 28, the knowledge lifecycle is:

```
colony completes
  -> institutional memory extraction (event-sourced, scan-on-write)
    -> Qdrant derived index
      -> knowledge catalog federates reads (institutional + legacy archival)
        -> Queen pre-spawn retrieval
        -> Queen memory_search tool
        -> Agent context injection (NEW)
        -> Agent memory_search / knowledge_detail / artifact_inspect (NEW)
        -> KnowledgeAccessRecorded events (NEW)
```

`skill_bank_v2` remains readable through the catalog but receives no new writes or confidence mutations.

---

## Current Repo Truth

This plan builds on current source tree state:

- `sourceColonyId` filtering in `knowledge-browser.ts` is already fixed
- `metacognition.py` already references `memory_search`
- `ports.py` is already current at 40 event names; Wave 28 adds the 41st only
- `memory-browser.ts` is effectively unrouted already
- `skill-browser.ts` is still imported by `formicos-app.ts` and `knowledge-view.ts`
- Queen still exposes `list_skills`, deprecated `search_memory`, and `memory_search`

Wave 28 focuses on runtime unification, not re-solving closed Wave 27 debt.

---

## Critical Design Decisions

### D1. Thread knowledge through the real call graph

The actual execution path is:

```
colony_manager._run_colony()
  -> creates RoundRunner
  -> calls runner.run_round(knowledge_items=...)
    -> run_round() calls _run_agent(knowledge_items=...)
      -> _run_agent() calls assemble_context(knowledge_items=...)
```

`knowledge_items` is fetched in `colony_manager.py` (surface layer, allowed to call the catalog), then threaded through the engine as plain dicts. The engine never imports surface code.

### D2. Unified knowledge is primary; legacy retrieval is fallback

The legacy Tier 6 skill retrieval path stays inside `context.py` as a fallback. This is the right placement because the engine knows when unified knowledge is empty and can try its own retrieval without a surface round-trip. The behavior:

- when `knowledge_items` is present and non-empty: inject as `[System Knowledge]` tier, skip legacy Tier 6
- when `knowledge_items` is empty or None: legacy Tier 6 `RetrievalPipeline` / `skill_bank_v2` runs as before

This is a soft migration. The legacy path works. Once institutional memory accumulates entries, the catalog path dominates naturally.

### D3. Access traces are events, not projection-only state

`KnowledgeAccessRecorded` is emitted from `colony_manager.py` after `run_round()` returns, carrying the round's aggregated `knowledge_items_used` from `RoundResult`.

Wave 28 traces post-round context injection only. Tool-driven accesses (`knowledge_detail`, `artifact_inspect`, `memory_search`) are not traced in this wave. The event includes an `access_mode` field defaulting to `"context_injection"` so Wave 29 can add `"tool_search"` and `"tool_detail"` modes without schema churn.

### D4. Progressive disclosure: two new agent tools

- `knowledge_detail`: full content of a knowledge item by ID. Category: `vector_query`.
- `artifact_inspect`: fetch artifact content from a prior colony by `colony_id` + `artifact_id`. Category: `read_fs`.

Both tools are implemented as runtime-provided callbacks injected into `RoundRunner`, maintaining layer discipline. Both require `caste_recipes.yaml` updates to appear in agent tool lists.

### D5. Legacy writes and confidence updates both stop

Wave 28 disables:

- both `_crystallize_skills()` call sites (lines 568 and 634 in `colony_manager.py`)
- legacy confidence updates and `SkillConfidenceUpdated` emission in `_post_colony_hooks()` (line 693)

`skills_count` becomes `0` for all new colonies. The `skills_extracted` field stays on `ColonyCompleted` for replay compatibility but is no longer meaningful for new work. Colony detail de-emphasizes it in favor of knowledge trace.

### D6. Dead legacy surfaces are removed

Wave 28 removes:

- Queen `search_memory` tool and handler
- Queen `list_skills` tool and handler
- `/api/v1/skills` endpoint
- `skill-browser.js` import from `formicos-app.ts`
- `skill-browser.js` import from `knowledge-view.ts` (making it graph-only)

Files stay on disk as inert reference code. Imports and routes are what get removed.

### D7. `skills_extracted` cleanup scope

Colony detail de-emphasizes `skills_extracted` in favor of the new knowledge trace display. Other surfaces that show it (Queen `inspect_colony` at line 1319, transcript output) continue showing historical values for completed colonies. This is acceptable because the field still carries correct data for pre-Wave-28 colonies and shows `0` for new ones. A later cleanup wave can remove it from display entirely.

---

## New Type + Event

### KnowledgeAccessItem (core/types.py)

```python
class KnowledgeAccessItem(BaseModel):
    """Single knowledge item accessed during a colony round (Wave 28)."""
    model_config = FrozenConfig

    id: str = Field(description="Knowledge item ID (mem-* or legacy UUID)")
    source_system: str = Field(description="legacy_skill_bank | institutional_memory")
    canonical_type: str = Field(description="skill | experience")
    title: str = Field(default="")
    confidence: float = Field(default=0.5)
    score: float = Field(default=0.0, description="Query relevance score")
```

### KnowledgeAccessRecorded (core/events.py)

```python
class KnowledgeAccessRecorded(EventEnvelope):
    """Knowledge items accessed during a colony round (Wave 28)."""
    model_config = FrozenConfig

    type: Literal["KnowledgeAccessRecorded"] = "KnowledgeAccessRecorded"
    colony_id: str = Field(..., description="Colony that accessed knowledge.")
    round_number: int = Field(..., ge=1)
    workspace_id: str = Field(...)
    access_mode: str = Field(
        default="context_injection",
        description="context_injection | tool_search | tool_detail (Wave 28: context_injection only)",
    )
    items: list[KnowledgeAccessItem] = Field(default_factory=list)
```

Event union: `40 -> 41`. `EventTypeName` in `ports.py` gains `"KnowledgeAccessRecorded"`.

---

## Tracks

### Track A -- Agent Context Bridge + Tool Repoint

**Goal:** Agents receive unified knowledge in context. Agent `memory_search` is repointed through the catalog. Two new progressive-disclosure tools become available.

**A1. Fetch unified knowledge in colony_manager.py.**

Before the round loop, fetch knowledge items through `runtime.fetch_knowledge_for_colony()`. On redirect / active-goal shift, re-fetch against the new active goal. Pass results into `run_round(knowledge_items=...)`.

Files: `src/formicos/surface/colony_manager.py`, `src/formicos/surface/runtime.py`

**A2. Thread knowledge_items through the engine path.**

Add `knowledge_items: list[dict[str, Any]] | None = None` to:
- `RoundRunner.run_round()`
- `RoundRunner._run_agent()`
- `assemble_context()`

`_run_agent()` passes knowledge items to `assemble_context()`.

Files: `src/formicos/engine/runner.py`, `src/formicos/engine/context.py`

**A3. Add [System Knowledge] tier in context.py.**

New tier between input sources (2b) and routed outputs (3). When present and non-empty, skip legacy Tier 6. Extend `ContextResult` with `knowledge_items_used: list[KnowledgeAccessItem]`.

Files: `src/formicos/engine/context.py`

**A4. Aggregate knowledge usage on RoundResult.**

Extend `RoundResult` with `knowledge_items_used: list[KnowledgeAccessItem]`. Aggregate per-agent `ContextResult.knowledge_items_used` into deduplicated round-level list.

Files: `src/formicos/engine/runner.py`

**A5. Repoint agent memory_search via callback.**

Add `catalog_search_fn` callback to `RoundRunner.__init__()`. In `_execute_tool`, when `tool_name == "memory_search"`, search scratch -> workspace -> catalog (via callback). If no callback, legacy behavior remains as fallback.

Files: `src/formicos/engine/runner.py`, `src/formicos/surface/colony_manager.py`

**A6. Add knowledge_detail and artifact_inspect tools.**

Two new entries in `TOOL_SPECS` and `TOOL_CATEGORY_MAP`. Handlers use runtime-provided callbacks (`knowledge_detail_fn`, `artifact_inspect_fn`) injected into `RoundRunner`. `artifact_inspect` takes `colony_id` + `artifact_id`.

Files: `src/formicos/engine/runner.py`

**A7. Update caste_recipes.yaml.**

Add `knowledge_detail` and `artifact_inspect` to tool lists for: coder, reviewer, researcher, archivist. Without this, the tools won't appear in agent prompts.

Files: `config/caste_recipes.yaml`

| File | Action |
|------|--------|
| `src/formicos/surface/runtime.py` | `fetch_knowledge_for_colony()`, callback factories |
| `src/formicos/surface/colony_manager.py` | fetch + pass knowledge_items, inject callbacks into RoundRunner |
| `src/formicos/engine/runner.py` | thread knowledge_items, repoint memory_search, add tools, extend RoundResult |
| `src/formicos/engine/context.py` | [System Knowledge] tier, extend ContextResult |
| `config/caste_recipes.yaml` | add tool availability |

Do not touch: `src/formicos/core/*`, `src/formicos/surface/knowledge_catalog.py`, `src/formicos/surface/memory_store.py`, `src/formicos/surface/skill_lifecycle.py`, `src/formicos/adapters/*`

---

### Track B -- Knowledge Access Traces

**Goal:** Knowledge access becomes durable event truth.

**B1. Add KnowledgeAccessItem and KnowledgeAccessRecorded.**

Files: `src/formicos/core/types.py`, `src/formicos/core/events.py`, `src/formicos/core/ports.py`

**B2. Projection support.**

Add `knowledge_accesses: list[dict[str, Any]]` to `ColonyProjection`. Handler for `KnowledgeAccessRecorded` appends to this list on replay.

Files: `src/formicos/surface/projections.py`

**B3. Emit trace after each run_round().**

After each round returns in `colony_manager.py`, emit `KnowledgeAccessRecorded` using `RoundResult.knowledge_items_used`. Emit only when items is non-empty.

Files: `src/formicos/surface/colony_manager.py`

**B4. Transcript + UI exposure.**

Include access traces in `build_transcript()`. Add "Knowledge Used" section to colony detail showing items with provenance links.

Files: `src/formicos/surface/transcript.py`, `frontend/src/components/colony-detail.ts`, `frontend/src/types.ts`

| File | Action |
|------|--------|
| `src/formicos/core/types.py` | `KnowledgeAccessItem` |
| `src/formicos/core/events.py` | `KnowledgeAccessRecorded`, union 40 -> 41 |
| `src/formicos/core/ports.py` | add event name |
| `src/formicos/surface/projections.py` | access-trace field + handler |
| `src/formicos/surface/colony_manager.py` | emit trace post-round |
| `src/formicos/surface/transcript.py` | expose trace |
| `frontend/src/components/colony-detail.ts` | "Knowledge Used" section |
| `frontend/src/types.ts` | access-trace types |

Do not touch: `src/formicos/engine/*`, `src/formicos/surface/runtime.py`, `src/formicos/surface/knowledge_catalog.py`

---

### Track C -- Legacy Decommission + Dead Surface Removal

**Goal:** Stop legacy skill mutation and remove confusing legacy surfaces.

**C1. Disable both legacy crystallization call sites.**

Replace both `_crystallize_skills()` calls (lines 568, 634) with `skills_count = 0`. Preserve the method body as reference.

Files: `src/formicos/surface/colony_manager.py`

**C2. Disable legacy confidence updates.**

In `_post_colony_hooks()`, skip `update_skill_confidence()` and `SkillConfidenceUpdated` emission. Comment out with explanation.

Files: `src/formicos/surface/colony_manager.py`

**C3. Remove deprecated Queen tools.**

Remove `search_memory`, `list_skills` from tool list, dispatch, and handlers in `queen_runtime.py`. Also remove from `caste_recipes.yaml` queen tools list. Keep `memory_search` as the single search tool.

Files: `src/formicos/surface/queen_runtime.py`, `config/caste_recipes.yaml`

**C4. Remove /api/v1/skills.**

Delete the endpoint and its handler from `routes/api.py`. Remove the `get_skill_bank_detail` import if no longer needed.

Files: `src/formicos/surface/routes/api.py`

**C5. Remove dead imports and simplify knowledge-view.ts.**

- Remove `import './skill-browser.js'` from `formicos-app.ts`
- Remove `import './skill-browser.js'` from `knowledge-view.ts`, making it graph-only

`skill-browser.ts` and `memory-browser.ts` stay on disk as inert files.

Files: `frontend/src/components/formicos-app.ts`, `frontend/src/components/knowledge-view.ts`

**C6. De-emphasize skills_extracted in colony detail.**

Visually favor knowledge trace over `skills_extracted` count. Keep the field for replay compatibility.

Files: `frontend/src/components/colony-detail.ts`

**C7. Test parity updates.**

Update event count assertions (40 -> 41). Remove tests expecting `/api/v1/skills`, `search_memory`, `list_skills`.

Files: `tests/*`

| File | Action |
|------|--------|
| `src/formicos/surface/colony_manager.py` | disable crystallization + confidence updates |
| `src/formicos/surface/queen_runtime.py` | remove legacy Queen tools |
| `config/caste_recipes.yaml` | remove legacy Queen tool names |
| `src/formicos/surface/routes/api.py` | remove /api/v1/skills |
| `frontend/src/components/formicos-app.ts` | remove skill-browser import |
| `frontend/src/components/knowledge-view.ts` | graph-only simplification |
| `frontend/src/components/colony-detail.ts` | de-emphasize skills_extracted |
| `tests/*` | parity updates |

Do not touch: `src/formicos/core/*`, `src/formicos/engine/*`, `src/formicos/surface/skill_lifecycle.py`, `src/formicos/surface/knowledge_catalog.py`, `src/formicos/adapters/*`

---

## Execution Shape for 3 Parallel Coder Teams

| Team | Track | First Lands On | Dependencies |
|------|-------|----------------|--------------|
| Coder 1 | A | `runtime.py`, `colony_manager.py`, `runner.py`, `context.py`, `caste_recipes.yaml` | None |
| Coder 2 | B | `core/types.py`, `core/events.py`, `core/ports.py`, `projections.py`, `transcript.py`, `colony-detail.ts`, `types.ts` | Depends on `RoundResult.knowledge_items_used` from Track A |
| Coder 3 | C | `colony_manager.py`, `queen_runtime.py`, `routes/api.py`, `caste_recipes.yaml`, `formicos-app.ts`, `knowledge-view.ts`, tests | None |

### Overlap-Prone Files

| File | Teams | Resolution |
|------|-------|------------|
| `colony_manager.py` | A (fetch + threading), B (trace emission), C (disable legacy hooks) | A first (round loop changes). B adds post-round trace emission. C disables completion hooks. All additive in different sections. |
| `colony-detail.ts` | B (trace display), C (de-emphasize skills_extracted) | Both additive. Low conflict. |
| `caste_recipes.yaml` | A (add new tools), C (remove legacy Queen tools) | Both additive in different sections. |

### Frozen Files

| File | Reason |
|------|--------|
| `src/formicos/surface/knowledge_catalog.py` | read from, not modified |
| `src/formicos/surface/memory_store.py` | unchanged |
| `src/formicos/surface/memory_extractor.py` | unchanged |
| `src/formicos/surface/memory_scanner.py` | unchanged |
| `src/formicos/surface/skill_lifecycle.py` | kept importable, no active call sites after C2 |
| `src/formicos/adapters/*` | no adapter changes |
| `docker-compose.yml` | no changes |
| `Dockerfile` | no changes |

---

## Acceptance Criteria

1. Agent context includes a `[System Knowledge]` block with unified entries and source labels.
2. When unified knowledge is present, legacy Tier 6 retrieval is skipped.
3. Agent `memory_search` returns scratch + workspace + unified catalog results.
4. Agent `knowledge_detail` returns full content for a knowledge item.
5. Agent `artifact_inspect` returns artifact content from a prior colony.
6. `KnowledgeAccessRecorded` events are emitted and survive replay.
7. Transcript includes replayed knowledge access trace.
8. Colony detail shows a "Knowledge Used" section.
9. Both `_crystallize_skills()` call sites are disabled.
10. Legacy confidence updates and `SkillConfidenceUpdated` emission are disabled.
11. Queen `search_memory` and `list_skills` are gone.
12. `/api/v1/skills` is gone.
13. `skill-browser` is no longer imported by active UI surfaces.
14. `knowledge-view.ts` is graph-only.
15. Layer discipline: `engine/` imports no `surface/` modules.
16. Full CI green.

### Smoke Traces

1. Colony with institutional memory -> agent prompt includes `[System Knowledge]`
2. Empty institutional memory -> legacy fallback works
3. Agent `memory_search` returns institutional results
4. Agent `knowledge_detail` returns full content
5. Agent `artifact_inspect` returns artifact content
6. Complete colony -> restart -> transcript shows knowledge access trace
7. Complete colony -> `skill_bank_v2` count unchanged
8. Queen tool list has no `search_memory` or `list_skills`
9. `/api/v1/skills` returns 404

---

## Not In Wave 28

| Item | Reason |
|------|--------|
| Bayesian confidence on MemoryEntry | Wave 29 |
| Dedup / contradiction detection | Wave 29 |
| Stale decay | Wave 29 |
| Deterministic colony primitive | Wave 29 |
| Tool-driven access tracing | Wave 29 (access_mode field is ready) |
| Deleting `skill_lifecycle.py` from disk | keep as reference |
| Full context-as-environment architecture | Wave 30+ |

---

## What This Enables Next

**Wave 29: Governed Consolidation + Confidence Evolution.** Bayesian confidence from retrieval traces + colony outcomes. Dedup, contradiction surfacing, stale decay. Tool-driven access tracing. First deterministic maintenance services. Legacy file cleanup.

**Wave 30: Ship Polish.** Composable workflows if deterministic primitives prove out. Documentation pass. Performance tuning. Edge case hardening. Onboarding UX.
