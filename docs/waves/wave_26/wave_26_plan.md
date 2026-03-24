# Wave 26 Plan -- Institutional Memory

**Wave:** 26 -- "Institutional Memory"
**Theme:** Colonies produce durable, typed, provenance-carrying knowledge entries that survive restart, earn trust through validation, and get retrieved by future colonies. FormicOS transitions from a colony runner that forgets everything between runs to a colony operating system with institutional memory.
**Architectural thesis:** The event log remains the source of truth. Vector/BM25 stores are derived indexes, not primary memory stores.
**Contract changes:** Event union opens from 37 to 40. Three new event types: `MemoryEntryCreated`, `MemoryEntryStatusChanged`, `MemoryExtractionCompleted`. New `MemoryEntry`, `MemoryEntryType`, `MemoryEntryStatus` types in `core/types.py`. No new ports. No existing event modifications.
**Estimated LOC delta:** ~600 Python, ~120 TypeScript, ~30 config/templates

---

## Why This Wave

Wave 25 gave FormicOS typed outputs. Wave 25.5 made those outputs legible to the operator. The backend now knows what a colony produced. The next job is making that truth compound through memory.

Today, every colony starts cold. A colony that successfully debugs a tricky import-time test failure learns nothing durable -- the next colony facing the same pattern starts from scratch. The skill bank (Wave 8-11, `skill_lifecycle.py`) partially addresses this for procedural knowledge, but it writes directly to Qdrant with no event-sourced backing, has no concept of tactical lessons or failure patterns, no write-path validation, no status lifecycle, and no provenance chain back to the artifacts that generated the knowledge.

Wave 26 builds institutional memory as a complete, usable system:
- colonies crystallize learnings on completion
- entries are event-sourced, replay-safe, and auditable
- a trust gate validates entries before they become retrievable
- the Queen retrieves relevant knowledge before spawning work
- the operator can inspect what was learned, from which colony, and why it's trusted

The research basis is strong. XSkill (arXiv:2603.12056) demonstrates that separating skills from experiences produces independent, additive performance gains. Turnstone's production implementation proves that scan-on-write validation and BM25 hybrid retrieval work at scale with minimal overhead. SkillRL (arXiv:2602.08234) shows that skill libraries must co-evolve with the system that uses them -- static banks degrade over time.

---

## Critical Design Decisions

### D1. Event-sourced memory, not direct-to-Qdrant

Memory mutations flow through the event log. Qdrant collections are derived projections rebuilt from `MemoryEntryCreated` and `MemoryEntryStatusChanged` events, just like `ColonyProjection` rebuilds from colony events. This means:
- knowledge survives store migrations
- knowledge is auditable through the event log
- knowledge replays correctly on restart
- the event log is the single source of truth (ADR-001)

**Derived index update mechanism:** Both startup replay and live event handlers call the same `MemoryStore.sync_entry(entry_id)` method, which reads the current entry state from the projection dict and re-upserts into Qdrant. This is the single path for keeping retrieval truth consistent with event truth. There is no separate update-payload shortcut -- full re-upsert on every status change.

### D2. Build alongside the existing skill system, not retrofit

The current `skill_lifecycle.py` path is real, useful, and direct-to-Qdrant. It has ingestion gates, Bayesian confidence, dedup logic, and retrieval integration in `context.py`. Trying to retrofit event sourcing onto it in the same wave as adding experiences, statuses, validation, retrieval, and nudges is too much churn.

Wave 26 introduces a new institutional-memory path alongside the existing skill bank:
- `skill_bank_v2` continues operating as the legacy procedural skill path
- the new memory system uses separate event types, separate projection logic, and a separate Qdrant collection
- Wave 27 decides whether and how legacy skill data is bridged or deprecated

### D3. Dual-store is a logical contract, not a physical mandate

Skills and experiences are distinguished by `entry_type` on the `MemoryEntry` schema. Retrieval strategies differ by type:
- skills rank on applicability, structure, and verification status
- experiences rank on recency, exact keyword match, and similarity to current failure/tool context

The physical layout (one collection with `entry_type` filter vs two collections) is an implementation choice, not a wave-level contract. The plan does not mandate a specific collection topology.

### D4. Memory naming avoids collision with knowledge graph

The repo already has `KnowledgeEntityCreated`, `KnowledgeEdgeCreated`, `KnowledgeEntityMerged` events for KG/TKG entities. Wave 26 institutional memory uses `MemoryEntry*` naming to maintain clear separation:
- KG entities are structured graph nodes with predicates and edges
- memory entries are natural-language knowledge items with provenance and trust state
- they share source material (colony results) but are different systems with different retrieval semantics

### D5. Queen-facing search ships in Wave 26; agent-facing search waits

Queen-side memory search improves decomposition immediately and avoids widening `runner.py` too early. Worker/agent-facing memory search is Wave 27+ scope. Wave 26 provides:
- deterministic pre-spawn retrieval (automatic, before the Queen reasons about a task)
- explicit Queen search tool for follow-up reasoning during the tool loop

### D6. Negative experiences are first-class from day one

Wave 24/25 already provide failure context, replay-safe output truth, and transcript-level result structure. The `MemoryEntry` schema includes a `polarity` field (`positive | negative | neutral`) so failure knowledge starts accumulating immediately. Wave 27 deepens how negative experiences decay, consolidate, and surface strategically.

---

## The Memory Entry Schema (Track 0 Prerequisite)

This schema must be frozen before parallel tracks start. It lives in `core/types.py`. Tracks B and C must not modify it.

```python
class MemoryEntryType(StrEnum):
    """Discriminator for institutional memory entries."""
    skill = "skill"           # procedural: reusable workflows, tool patterns, how-to guidance
    experience = "experience"  # tactical: warnings, local heuristics, failure patterns

class MemoryEntryStatus(StrEnum):
    """Trust lifecycle for memory entries."""
    candidate = "candidate"   # newly extracted, not yet validated by colony success
    verified = "verified"     # source colony completed successfully
    rejected = "rejected"     # failed scan-on-write validation
    stale = "stale"           # marked stale by consolidation (Wave 27)

class MemoryEntryPolarity(StrEnum):
    """Outcome signal carried by the entry."""
    positive = "positive"     # this worked, do this
    negative = "negative"     # this failed, avoid this or watch for this
    neutral = "neutral"       # contextual, no strong outcome signal

class MemoryEntry(BaseModel):
    """Institutional memory entry -- skill or experience (Wave 26).

    Persisted as dicts on MemoryEntryCreated events for replay safety.
    The model is used for construction and validation.
    """
    model_config = FrozenConfig

    id: str = Field(description="Stable ID: mem-{colony_id}-{type[0]}-{index}")
    entry_type: MemoryEntryType = Field(description="skill or experience")
    status: MemoryEntryStatus = Field(default=MemoryEntryStatus.candidate)
    polarity: MemoryEntryPolarity = Field(default=MemoryEntryPolarity.positive)
    title: str = Field(description="Short descriptive title")
    content: str = Field(description="Full entry content")
    summary: str = Field(default="", description="One-line summary for search display")
    source_colony_id: str = Field(description="Colony that produced this entry")
    source_artifact_ids: list[str] = Field(
        default_factory=list,
        description="Artifact IDs from which this entry was derived (Wave 25 provenance chain)",
    )
    source_round: int = Field(default=0, description="Round number of source material")
    domains: list[str] = Field(
        default_factory=list,
        description="Domain tags: python, testing, api-design, devops, etc.",
    )
    tool_refs: list[str] = Field(
        default_factory=list,
        description="Tool names referenced: file_write, http_fetch, code_execute, etc.",
    )
    confidence: float = Field(default=0.5, description="Initial confidence score")
    scan_status: str = Field(default="pending", description="safe, low, medium, high, critical, pending")
    created_at: str = Field(default="", description="ISO timestamp")
    workspace_id: str = Field(default="", description="Workspace scope")
```

The `source_artifact_ids` field is the critical provenance link. Wave 25 made artifacts the provenance substrate. Wave 26 builds directly on that -- every memory entry traces back to the artifacts it was derived from.

---

## Event Union Expansion (37 -> 40)

Three new event types. No existing events modified.

```python
class MemoryEntryCreated(EventEnvelope):
    """A new institutional memory entry was extracted and persisted."""
    model_config = FrozenConfig
    type: Literal["MemoryEntryCreated"] = "MemoryEntryCreated"
    entry: dict[str, Any] = Field(..., description="Serialized MemoryEntry dict.")
    workspace_id: str = Field(..., description="Workspace scope.")

class MemoryEntryStatusChanged(EventEnvelope):
    """An entry's trust status changed (candidate -> verified, etc.)."""
    model_config = FrozenConfig
    type: Literal["MemoryEntryStatusChanged"] = "MemoryEntryStatusChanged"
    entry_id: str = Field(..., description="Memory entry being updated.")
    old_status: str = Field(..., description="Previous status.")
    new_status: str = Field(..., description="New status.")
    reason: str = Field(default="", description="Why the status changed.")
    workspace_id: str = Field(..., description="Workspace scope.")

class MemoryExtractionCompleted(EventEnvelope):
    """Memory extraction finished for a colony (even if zero entries produced).

    This is the durable receipt that extraction ran to completion.
    Without it, restart recovery cannot distinguish 'extraction crashed'
    from 'extraction ran but found nothing to extract.'
    """
    model_config = FrozenConfig
    type: Literal["MemoryExtractionCompleted"] = "MemoryExtractionCompleted"
    colony_id: str = Field(..., description="Colony whose extraction finished.")
    entries_created: int = Field(..., ge=0, description="Number of MemoryEntryCreated events emitted.")
    workspace_id: str = Field(..., description="Workspace scope.")
```

Note: `EventTypeName` in `ports.py` is currently stale (only covers through Wave 11). Wave 26 should update it to include all 40 event type names, or document it as known debt.

---

## Tracks

### Track A -- Knowledge Substrate + Crystallization

**Goal:** Memory entries are event-sourced, replay-safe, and extracted automatically from colony completion results. The extraction pipeline produces both skills and experiences from artifacts, transcripts, and failure context.

**A1. Core types.**

Add `MemoryEntry`, `MemoryEntryType`, `MemoryEntryStatus`, `MemoryEntryPolarity` to `core/types.py`. Schema as specified above.

Files touched: `src/formicos/core/types.py` (~50 LOC)

**A2. Event types.**

Add `MemoryEntryCreated`, `MemoryEntryStatusChanged`, and `MemoryExtractionCompleted` to `core/events.py`. Update the `FormicOSEvent` union from 37 to 40 members.

Files touched: `src/formicos/core/events.py` (~35 LOC)

**A3. Projection handlers.**

New `MemoryProjection` dataclass in `projections.py` holding in-memory state of all memory entries. Handlers for all three new events:
- `_on_memory_entry_created`: adds entry to projection store
- `_on_memory_entry_status_changed`: updates status field
- `_on_memory_extraction_completed`: marks a colony's extraction lifecycle as settled

Add both to `ProjectionStore`:
- `memory_entries: dict[str, dict[str, Any]]`
- `memory_extractions_completed: set[str]`

The `memory_extractions_completed` set is the replay-visible settled receipt used by startup backfill. `app.py` compares completed colony IDs against this set, not against `MemoryEntryCreated` rows.

Files touched: `src/formicos/surface/projections.py` (~50 LOC)

**A4. Memory extraction on colony completion.**

New module `surface/memory_extractor.py`. Called by `colony_manager.py` after colony completion (same hook point as existing skill crystallization). Runs as a fire-and-forget async task -- does NOT block the colony lifecycle.

The extractor receives:
- colony artifacts (from `ColonyCompleted.artifacts`)
- colony transcript (final output, round summaries)
- contract satisfaction result (from Track B in Wave 25)
- colony status (completed vs failed)
- colony failure context (if failed, from Wave 24)

Extraction is a single LLM call per colony completion, using the colony's own model assignment. Two extraction passes in one call:

**Skill extraction** (from successful colonies):
- "What general technique was used?"
- "Under what conditions does this technique apply?"
- "What is the minimal actionable instruction?"
- "What failure modes should future colonies watch for?"

**Experience extraction** (from both successful and failed colonies):
- "What tactical adjustments led to success or failure?"
- "What environmental conditions triggered these adjustments?"
- "What is the minimal warning for a future agent?" (1-2 sentences)
- "Which tools or tool combinations does this apply to?"

Failed colonies produce negative-polarity experience entries only (no skill extraction from failures).

**Entry lifecycle state machine (strict ordering):**

```
extract -> scan -> emit MemoryEntryCreated (with scan_status baked in)
                     |
                     +-- scan_status is high/critical:
                     |     entry.status = "rejected" on creation
                     |     (no Qdrant upsert, entry is audit-only)
                     |
                     +-- scan_status is safe/low/medium:
                     |     entry.status = "candidate" on creation
                     |     (Qdrant upsert happens)
                     |     |
                     |     +-- source colony completed successfully:
                     |           emit MemoryEntryStatusChanged(candidate -> verified)
                     |           (Qdrant re-upsert via sync_entry)
                     |
                     +-- source colony failed:
                           entry.status = "candidate" (never auto-verified)
                           (Qdrant upsert happens)
```

The scanner runs *before* `MemoryEntryCreated` is emitted. The `scan_status` field is set on the entry dict before serialization into the event, so it is part of the persisted event payload and survives replay. There is no post-creation mutation of `scan_status` -- it is immutable once the event is written.

Rejected entries are emitted as `MemoryEntryCreated` with `status="rejected"` directly. No separate `MemoryEntryStatusChanged` is needed for the rejection path -- the entry is born rejected. This eliminates the race between candidate-to-verified and candidate-to-rejected.

Verification (`MemoryEntryStatusChanged` from candidate to verified) only fires after the creation event is committed and only when the source colony completed successfully.

Extraction prompt returns structured JSON. If the model returns an empty array, no entries are emitted. In that case a `MemoryExtractionCompleted` event is emitted with `entries_created=0` to mark the extraction as settled, preventing infinite re-queue on restart.

**Extraction durability and restart recovery:**

Extraction runs as a fire-and-forget async task after colony completion. If the process crashes between `ColonyCompleted` and the extraction completing, the memory entries are lost.

To recover: on startup replay, the system compares the set of completed colony IDs (from `ColonyCompleted` events) against the set of colony IDs referenced in `MemoryExtractionCompleted` events. Any completed colony with no corresponding `MemoryExtractionCompleted` is added to a `pending_extraction` backfill set. After replay finishes, the backfill set is processed by re-running extraction for each missing colony. This is best-effort -- if the LLM is unavailable at startup, backfill is deferred to the next successful extraction cycle.

Colonies where extraction legitimately produced zero entries are NOT re-queued, because their `MemoryExtractionCompleted` event (with `entries_created=0`) serves as the durable receipt that extraction ran to completion.

This ensures that institutional memory is eventually consistent with colony completion, even across crashes, without re-extracting colonies that simply had nothing to teach.

Files touched:
- `src/formicos/surface/memory_extractor.py` -- new (~150 LOC)
- `src/formicos/surface/colony_manager.py` -- extraction hook after completion (~20 LOC)
- `src/formicos/surface/app.py` -- backfill check after replay (~15 LOC)

**A5. Qdrant projection (derived index).**

New `surface/memory_store.py` module that maintains the Qdrant collection as a derived projection from memory events. On startup, the projection store rebuilds from replayed events. On new events, the handler upserts/updates entries in Qdrant.

Each entry is stored with:
- dense vector from the existing embedding pipeline (`snowflake-arctic-embed-s`)
- sparse vector via Qdrant-native BM25 conversion (ADR-021)
- payload fields: all MemoryEntry fields plus `entry_type` and `status` for filtering

Collection name: `institutional_memory` (single collection, `entry_type` as payload filter for logical dual-store behavior).

Files touched:
- `src/formicos/surface/memory_store.py` -- new (~100 LOC)
- `src/formicos/surface/app.py` -- wire memory store into lifespan (~10 LOC)

| File | Action |
|------|--------|
| `src/formicos/core/types.py` | Add MemoryEntry, MemoryEntryType, MemoryEntryStatus, MemoryEntryPolarity |
| `src/formicos/core/events.py` | Add MemoryEntryCreated, MemoryEntryStatusChanged, MemoryExtractionCompleted; expand union 37->40 |
| `src/formicos/surface/projections.py` | Add memory_entries dict, memory_extractions_completed set, and three event handlers |
| `src/formicos/surface/memory_extractor.py` | New -- dual extraction pipeline |
| `src/formicos/surface/colony_manager.py` | Hook extraction after colony completion |
| `src/formicos/surface/memory_store.py` | New -- Qdrant projection from memory events |
| `src/formicos/surface/app.py` | Wire memory store into lifespan |

Do not touch:
- `src/formicos/surface/skill_lifecycle.py`
- `src/formicos/surface/queen_runtime.py`
- `src/formicos/engine/runner.py`
- `src/formicos/engine/context.py`
- `src/formicos/adapters/vector_qdrant.py`
- `frontend/*`

---

### Track B -- Trust on the Write Path + Queen Retrieval

**Goal:** New entries pass through synchronous scan-on-write validation before becoming retrievable. The Queen can search institutional memory before spawning colonies and during her tool loop.

**B1. Scan-on-write validation.**

New module `surface/memory_scanner.py`. Synchronous, sub-50ms, stdlib-only (regex). Called by the extraction pipeline *before* `MemoryEntryCreated` is emitted -- NOT as a reaction to the event.

Four risk axes, each scored independently, combined into a composite tier (safe / low / medium / high / critical):
- **Content risk**: dangerous command patterns, data exfiltration indicators
- **Supply chain risk**: pipe-to-shell patterns, transitive installs from URLs/git
- **Vulnerability risk**: prompt injection patterns, insecure credential handling
- **Capability risk**: references to dangerous tool combinations

The scanner result is baked into the entry before event emission:
- `scan_status` is set to the composite tier (immutable after creation)
- if the tier is `high` or `critical`, `status` is set to `rejected` on the entry before the `MemoryEntryCreated` event is emitted
- rejected entries are persisted in the event log for audit but are never upserted into Qdrant

This means scanning is part of the creation path, not a post-creation side effect. On replay, the `MemoryEntryCreated` event already contains the correct `scan_status` and `status` -- no re-scanning needed.

Files touched: `src/formicos/surface/memory_scanner.py` -- new (~120 LOC)

**B2. Queen retrieval -- deterministic pre-spawn search.**

Before the Queen reasons about a new task, the runtime performs a deterministic memory search using the task description as query. Results are injected into the Queen's context as a structured block:

```
[Institutional Memory -- 3 entries found]
[SKILL, verified] "Divide-and-conquer refactoring": Start with dependency graph extraction...
  source: colony abc123, confidence: 0.8
[EXPERIENCE, verified, negative] "Import-time test failures": When tests import modules with side effects...
  source: colony def456, confidence: 0.6
[EXPERIENCE, candidate] "Schema validation ordering": Validate schema before generating code...
  source: colony ghi789, confidence: 0.5
```

Retrieval rules:
- top 3 skills + top 2 experiences per task (configurable)
- verified entries outrank candidate entries (sort by status then confidence)
- rejected and stale entries are excluded from results
- experience queries use hybrid retrieval weighted toward sparse/BM25
- skill queries use hybrid retrieval weighted toward dense/semantic

**Retrieval implementation:** `MemoryStore.search()` uses `qdrant-client` directly (not generic `VectorPort.search()`) to perform payload-filtered queries. Filters for `status`, `entry_type`, and `workspace_id` are applied at the Qdrant query level, not as post-fetch Python filters. This ensures correct results regardless of collection size -- rejected entries are never returned, type filtering happens before ranking, and workspace scoping is enforced server-side.

This is a deterministic runtime action, not a prompt nudge. It runs before the Queen's LLM call, not during it.

Files touched:
- `src/formicos/surface/runtime.py` -- pre-spawn memory retrieval (~40 LOC)
- `src/formicos/surface/memory_store.py` -- search methods with payload-filtered Qdrant queries (~50 LOC)

**B3. Queen search tool.**

New tool `memory_search` in the Queen's tool set (added to `queen_runtime.py`'s tool loop). Allows the Queen to explicitly search institutional memory during follow-up reasoning:

```json
{
  "name": "memory_search",
  "description": "Search institutional memory for skills and experiences relevant to a query.",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "Search query"},
      "entry_type": {"type": "string", "enum": ["skill", "experience", ""], "description": "Filter by type. Empty for both."},
      "limit": {"type": "integer", "description": "Max results (default 5)"}
    },
    "required": ["query"]
  }
}
```

This is a Queen tool only. It does not go into `runner.py` or agent tool sets.

Files touched: `src/formicos/surface/queen_runtime.py` -- add tool spec + handler (~40 LOC)

**B4. Memory list/detail API endpoints.**

REST endpoints for operator inspection:
- `GET /api/v1/memory` -- list entries with filters (type, status, workspace, domain)
- `GET /api/v1/memory/{entry_id}` -- full entry detail with provenance
- `GET /api/v1/memory/search?q=...&type=...` -- search with hybrid retrieval

Files touched: `src/formicos/surface/routes/memory_api.py` -- new (~80 LOC)

| File | Action |
|------|--------|
| `src/formicos/surface/memory_scanner.py` | New -- scan-on-write validation |
| `src/formicos/surface/runtime.py` | Pre-spawn memory retrieval injection |
| `src/formicos/surface/memory_store.py` | Search methods (shared with Track A) |
| `src/formicos/surface/queen_runtime.py` | memory_search tool spec + handler |
| `src/formicos/surface/routes/memory_api.py` | New -- REST API for operator |
| `src/formicos/surface/app.py` | Wire memory routes (shared with Track A) |

Do not touch:
- `src/formicos/core/*` (Track A owns this)
- `src/formicos/engine/*`
- `src/formicos/surface/skill_lifecycle.py`
- `src/formicos/surface/projections.py` (Track A owns this)
- `src/formicos/surface/colony_manager.py` (Track A owns this)
- `src/formicos/adapters/vector_qdrant.py`
- `frontend/*`

---

### Track C -- Metacognitive Nudges + Operator Visibility

**Goal:** The system prompts memory use at the right moments and gives the operator clear visibility into what was learned, from where, and why it's trusted.

**C1. Metacognition module.**

New module `surface/metacognition.py`. Pure functions, no I/O. Follows the `task_classifier.py` pattern: logic lives in a helper, `queen_runtime.py` calls it.

Two categories of metacognitive behavior, explicitly separated:

**Deterministic orchestration triggers** (runtime actions, not prompt text):
- `on_completion`: trigger memory extraction (already handled by Track A's colony_manager hook)
- `on_failure`: trigger negative-experience extraction (already handled by Track A)
- `pre_spawn_retrieval`: inject relevant memory into Queen context (already handled by Track B)

**Model-facing nudges** (brief hints appended to Queen context when conditions are met):
- `nudge_check_prior_failures`: fires when a colony's task matches domains where negative experiences exist. "Prior colonies encountered failures in [domain] -- relevant experiences have been included above."
- `nudge_save_corrections`: fires when the Queen modifies a colony's approach mid-run (redirect, routing override). "Consider whether this correction should be preserved as an experience for future work."
- `nudge_memory_available`: fires on first task in a workspace with existing memory entries. "Institutional memory is available for this workspace. Relevant entries have been pre-loaded."

Each nudge type has an independent cooldown (configurable, default 300 seconds). Detection is based on projection state (memory entry counts, domain overlap with task), not on parsing agent output.

Files touched: `src/formicos/surface/metacognition.py` -- new (~80 LOC)

**C2. Nudge integration in Queen runtime.**

`queen_runtime.py` calls `metacognition.py` functions at three points:
- before the Queen's first LLM call on a new task (check `nudge_memory_available`)
- before follow-up reasoning after a colony completes or fails (check `nudge_save_corrections`)
- when pre-spawn retrieval returns negative experiences (check `nudge_check_prior_failures`)

The nudges are appended as developer messages in the Queen's message list, not injected into the system prompt. They are ephemeral -- present for one LLM call, not persisted.

Files touched: `src/formicos/surface/queen_runtime.py` -- nudge call sites (~25 LOC, additive only)

**C3. Frontend -- memory browser.**

New Lit component `memory-browser.ts`. Operator-facing surface for inspecting institutional memory:
- list view with type pills (skill/experience), status badges (candidate/verified/rejected/stale), polarity indicators
- search bar using the `/api/v1/memory/search` endpoint
- detail view showing: full content, provenance (source colony link, source artifact IDs), domains, tool refs, confidence, scan status, created timestamp
- filter controls: by type, status, domain, workspace

This replaces nothing -- it's a new nav destination alongside the existing skill browser.

Files touched: `frontend/src/components/memory-browser.ts` -- new (~200 LOC)

**C4. Frontend -- memory indicators on colony detail.**

On the colony detail page, show:
- how many memory entries were extracted from this colony (in the quality row)
- link to the memory browser filtered by `source_colony_id`

Files touched: `frontend/src/components/colony-detail.ts` (~15 LOC additive)

**C5. Frontend types and state.**

Add `MemoryEntryPreview` interface to `types.ts`. Wire the memory API into the state store.

Files touched:
- `frontend/src/types.ts` (~15 LOC)
- `frontend/src/state/store.ts` (~20 LOC)

| File | Action |
|------|--------|
| `src/formicos/surface/metacognition.py` | New -- nudge logic and detection |
| `src/formicos/surface/queen_runtime.py` | Nudge call sites (additive) |
| `frontend/src/components/memory-browser.ts` | New -- memory browser component |
| `frontend/src/components/colony-detail.ts` | Memory extraction indicators |
| `frontend/src/types.ts` | MemoryEntryPreview type |
| `frontend/src/state/store.ts` | Memory API wiring |

Do not touch:
- `src/formicos/core/*` (Track A owns this)
- `src/formicos/engine/*`
- `src/formicos/surface/projections.py` (Track A owns this)
- `src/formicos/surface/colony_manager.py` (Track A owns this)
- `src/formicos/surface/memory_store.py` (Tracks A/B own this)
- `src/formicos/surface/memory_scanner.py` (Track B owns this)
- `src/formicos/surface/runtime.py` (Track B owns this)

---

## Execution Shape for 3 Parallel Coder Teams

| Team | Track | First Lands On | Dependencies |
|------|-------|----------------|--------------|
| **Coder 1** | A (Substrate + Crystallization) | `core/types.py`, `core/events.py`, `projections.py`, `memory_extractor.py`, `colony_manager.py`, `memory_store.py`, `app.py` | None -- starts immediately (schema is Track 0) |
| **Coder 2** | B (Trust + Retrieval) | `memory_scanner.py`, `runtime.py`, `queen_runtime.py`, `routes/memory_api.py` | Uses MemoryEntry schema from Track A; uses memory_store search from Track A |
| **Coder 3** | C (Nudges + Frontend) | `metacognition.py`, `queen_runtime.py` (additive only), `frontend/*` | Uses memory API from Track B; uses projection state from Track A |

### Overlap-Prone Files

| File | Teams | Resolution |
|------|-------|------------|
| `queen_runtime.py` | B (search tool), C (nudge call sites) | B adds tool spec + handler. C adds nudge call sites. Both are additive. If needed, sequence B before C on this file. |
| `memory_store.py` | A (Qdrant projection), B (search methods) | A creates the module with upsert/rebuild. B adds search methods. Co-owned with A landing first. |
| `app.py` | A (wire store), B (wire routes) | Both are additive route/lifespan wiring. Low conflict risk. |

### Frozen Files

| File | Reason |
|------|--------|
| `src/formicos/surface/skill_lifecycle.py` | Legacy skill path -- not modified in Wave 26 |
| `src/formicos/engine/runner.py` | No agent-facing memory tools this wave |
| `src/formicos/engine/context.py` | Legacy skill retrieval path unchanged |
| `src/formicos/adapters/vector_qdrant.py` | VectorPort adapter -- unchanged |
| `src/formicos/adapters/knowledge_graph.py` | KG system -- explicitly separate from memory |
| `src/formicos/surface/artifact_extractor.py` | Stable from Wave 25 |
| `src/formicos/surface/transcript.py` | Stable from Wave 25.5 |
| `docker-compose.yml` | No changes |
| `Dockerfile` | No changes |

---

## Acceptance Criteria

1. **A completed colony produces at least one memory entry.** A code colony's completion triggers extraction that creates at least one skill or experience `MemoryEntryCreated` event.
2. **Entries survive restart.** After stopping and restarting FormicOS, memory entries are present in both the projection store and Qdrant (rebuilt from event replay).
3. **Provenance traces back to colony and artifacts.** Each entry's `source_colony_id` and `source_artifact_ids` resolve to real colony/artifact records.
4. **Scan-on-write validation runs.** Entries pass through the four-axis scanner. Entries scoring high/critical are automatically rejected.
5. **Verified entries outrank candidates.** Search results sort by status (verified first) then confidence.
6. **Rejected entries do not appear in retrieval.** The Queen's pre-spawn search and explicit `memory_search` tool exclude rejected entries.
7. **Experience retrieval benefits from keyword queries.** Searching for a tool name (e.g., "file_write") or error string returns relevant experiences via BM25/sparse scoring.
8. **Queen sees memory before spawning.** The pre-spawn injection block appears in the Queen's context with relevant entries and provenance summaries.
9. **Queen can search memory explicitly.** The `memory_search` tool returns results and the Queen can reason about them.
10. **Failed colonies produce negative experiences.** A failed colony with failure context generates at least one negative-polarity experience entry.
11. **Operator can inspect memory.** The memory browser shows entries with type/status/provenance/confidence. Filter and search work.
12. **Colony detail shows extraction count.** The colony detail page shows how many memory entries were extracted.
13. **Metacognitive nudges fire.** When conditions are met (prior failures in domain, first task with memory), nudges appear in the Queen's context.
14. **Full CI green.** `ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest`

### Smoke Traces

1. **Extraction:** Spawn code colony -> colony completes -> `GET /api/v1/memory` shows entries with `source_colony_id` matching
2. **Replay safety:** Complete a colony -> restart FormicOS -> `GET /api/v1/memory` still shows entries
3. **Negative experience:** Spawn colony that fails -> `GET /api/v1/memory?type=experience` shows negative-polarity entry
4. **Scan rejection:** (Unit test) Entry with `curl | sh` content -> scanner returns critical -> status becomes rejected
5. **Pre-spawn retrieval:** Create entries -> spawn new colony in same workspace -> Queen context includes memory block
6. **Queen search:** Queen calls `memory_search` tool -> receives formatted results
7. **Keyword search:** Create experience mentioning "file_write" -> search for "file_write" -> experience appears in results
8. **Memory browser:** Navigate to memory browser -> see entries with type pills, status badges, provenance links

---

## Not in Wave 26

| Item | Reason |
|------|--------|
| Retrofitting event sourcing onto existing `skill_lifecycle.py` | Too much churn; migration is Wave 27 scope |
| Agent-facing memory search tools in `runner.py` | Queen-facing search is higher value; agent search is Wave 27 |
| Contradiction detection | Requires consolidation logic; Wave 27 scope |
| Deduplication of memory entries | Wave 27 consolidation |
| Stale experience decay | Wave 27 consolidation |
| Domain-aware meta-knowledge synthesis | Wave 27+ |
| Autonomous template mutation based on memory | Explicitly excluded |
| External skill marketplace ingestion | Explicitly excluded |
| Self-experimentation loops | Explicitly excluded |
| Full RLM-style navigable environment | Wave 28+ |
| RL on execution reasoning | Post-substrate |

---

## Runtime Prerequisite

**Verify deployed Qdrant image at wave kickoff.** ADR-021 accepts the Qdrant upgrade for server-side BM25, but source-tree truth is not deployment truth. Before any Track A/B work begins, confirm the running Qdrant container version supports:
- sparse vector upsert
- server-side BM25 conversion
- hybrid query (dense + sparse fusion)

If the deployed image does not support these, upgrade first. This is a 10-minute Docker task, not a wave-level risk, but it must be verified before Track B's retrieval work begins.

---

## What This Enables Next

**Wave 27: Governed Consolidation + Deep Retrieval.** Background dedup, contradiction surfacing, stale decay, negative experience consolidation, domain-aware retrieval, operator governance surfaces. Migration or bridging of legacy `skill_bank_v2` data. Agent-facing memory search tools.

**Wave 28: Context as Environment.** Agents navigate knowledge rather than receiving flattened bundles. Full progressive disclosure with search/inspect operations over artifacts, skills, experiences, transcripts, and service capabilities. RLM-style recursive context decomposition.

**Wave 29: Composable Capability Routing.** Services declare typed capabilities. The Queen routes by matching type signatures. Sequential pipeline primitives.
