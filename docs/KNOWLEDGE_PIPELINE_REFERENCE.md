# Knowledge Pipeline Integration Reference

Complete data-flow map from colony execution through knowledge extraction,
security scanning, storage, retrieval, and confidence evolution. Use this
document to identify exact insertion points for new features without
re-reading the codebase.

ASCII-only. Section numbers are stable -- reference them from other documents.

---

## 1. Colony Completion to Knowledge Extraction

### 1.1 Colony Completion Events

Colony execution terminates in `colony_manager.py` via two paths:

- **Early completion** (convergence threshold met): line 583-588 emits
  `ColonyCompleted` with `summary=result.round_summary`.
- **Max-rounds exhaustion**: line 633-638 emits `ColonyCompleted` with the
  last round's summary.

Both paths immediately call `_post_colony_hooks()` (line 649).

**File:** `src/formicos/surface/colony_manager.py`

### 1.2 Hook Dispatch Order

`_post_colony_hooks()` (lines 649-674) dispatches hooks sequentially:

```
1. _hook_observation_log(...)        -- telemetry
2. _hook_step_detection(...)         -- workflow step matching
3. _hook_follow_up(...)              -- Queen continuation signal
4. _hook_memory_extraction(...)      -- TRIGGERS KNOWLEDGE PIPELINE
5. _hook_confidence_update(...)      -- Bayesian confidence updates
6. _hook_step_completion(...)        -- workflow step state machine
```

**File:** `src/formicos/surface/colony_manager.py`, lines 649-674

### 1.3 Memory Extraction Trigger

`_hook_memory_extraction()` (lines 772-787) is fire-and-forget via
`asyncio.create_task`. It passes:

| Parameter | Value | Source |
|-----------|-------|--------|
| colony_id | Colony identifier | Direct parameter |
| workspace_id | Workspace scope | `colony.workspace_id` |
| colony_status | "completed" or "failed" | `succeeded` flag |
| final_summary | Compressed round summary | `colony_proj.summary` |
| artifacts | List of artifact dicts | `colony_proj.artifacts` |
| failure_reason | Error string or None | `succeeded` flag |

**Critical limitation:** `final_summary` is the compressed output from the
final round only (`"\n".join(f"{aid}: {out}" for aid, out in outputs.items())`
built at `runner.py` line 842-844). The extractor does NOT have access to the
full colony transcript (individual agent turns, tool calls, tool outputs).
It sees only the compressed summary and artifact previews.

### 1.4 LLM Extraction Call

`extract_institutional_memory()` (lines 955-963) builds the extraction prompt
and calls the LLM:

1. **Prompt construction:** `build_extraction_prompt()` in
   `memory_extractor.py` (lines 29-72) assembles:
   - Task description (`colony.task`)
   - Colony status and failure reason
   - Final output truncated to 2000 chars
   - Up to 5 artifact previews, each truncated to 200 chars
   - JSON schema for skills and experiences

2. **LLM call** (colony_manager.py lines 1003-1019):
   - Model: `runtime.resolve_model("archivist", workspace_id)`
   - Temperature: 0.0 (deterministic)
   - Max tokens: 2048
   - System prompt: "You extract institutional memory from colony results.
     Return valid JSON only."

3. **Response parsing:** `parse_extraction_response()` in
   `memory_extractor.py` (lines 118-139) handles code fences, partial JSON,
   and balanced-brace extraction. Falls back to `{"skills": [], "experiences": []}`.

**File:** `src/formicos/surface/memory_extractor.py`

### 1.5 Entry Construction

`build_memory_entries()` in `memory_extractor.py` (lines 75-115) converts
LLM output into `MemoryEntry` dicts. Each entry is initialized with:

| Field | Initial Value |
|-------|---------------|
| id | `mem-{colony_id}-{s|e}-{index}` |
| entry_type | `skill` or `experience` |
| status | `candidate` |
| polarity | positive (skills), varies (experiences) |
| confidence | 0.5 (success) or 0.4 (failure) |
| conf_alpha | 5.0 (Beta prior) |
| conf_beta | 5.0 (Beta prior) |
| scan_status | `pending` |
| created_at | ISO timestamp |

Content shorter than 30 characters is silently dropped (line 84, 97).

Thread ID is attached later (colony_manager.py lines 1043-1047) from
`colony_proj.thread_id`.

### 1.6 Extension Points -- Section 1

| Feature | Insertion Point | Details |
|---------|----------------|---------|
| Full transcript access | `_hook_memory_extraction()` line 783 | Pass `colony_proj.chat_messages` or transcript assembly instead of `summary` |
| Additional extraction fields | `build_memory_entries()` line 75 | Add fields to `MemoryEntry()` constructor call |
| Custom extraction prompt | `build_extraction_prompt()` line 29 | Modify prompt template in `memory_extractor.py` |
| Alternative LLM model | `runtime.resolve_model("archivist", ws)` | Configure archivist model per workspace |

---

## 2. Security Scanning

### 2.1 Scanner Architecture

The security scanner runs synchronously on every entry BEFORE
`MemoryEntryCreated` is emitted, so `scan_status` is baked into the
persisted event payload. No re-scanning on replay.

**File:** `src/formicos/surface/memory_scanner.py` (163 lines)

### 2.2 The Four Scan Axes

**Axis 1 -- Content Risk** (lines 36-48):

| Pattern | Regex | Score |
|---------|-------|-------|
| exec/eval | `\beval\s*[(]`, `\bexec\s*[(]`, `subprocess.*`, `os.system/popen` | +1.0 |
| sudo usage | `\bsudo\s+\S+` | +0.8 |
| data exfiltration | `curl.*-d`, `wget.*--post`, `requests.post` | +1.2 |

**Axis 2 -- Supply Chain Risk** (lines 50-60):

| Pattern | Regex | Score |
|---------|-------|-------|
| pipe-to-shell | `curl/wget ... \| sh/bash` | +1.5 |
| transitive install | `pip install git+`, `npm install https://`, `npx` | +1.0 |

**Axis 3 -- Vulnerability Risk** (lines 62-73):

| Pattern | Regex | Score |
|---------|-------|-------|
| prompt injection | `ignore previous/all/above instructions`, `system: you are` | +1.5 |
| embedded credential | `api_key/password/secret/token := "8+ chars"` | +1.0 |

**Axis 4 -- Capability Risk** (lines 76-83):

Checks `tool_refs` for dangerous combinations. Each match adds +0.8:
- `{http_fetch, file_write}`
- `{code_execute, http_fetch}`
- `{file_write, code_execute}`

### 2.3 Tier Assignment

Composite score = sum of all four axis scores. Tier thresholds
(lines 20-32):

| Composite Score | Tier | Entry Fate |
|----------------|------|------------|
| >= 2.8 | critical | rejected |
| >= 2.0 | high | rejected |
| >= 1.2 | medium | candidate (proceeds) |
| >= 0.5 | low | candidate (proceeds) |
| < 0.5 | safe | candidate (proceeds) |

`ScanStatus` is a StrEnum in `core/types.py` lines 296-304 with values:
`pending`, `safe`, `low`, `medium`, `high`, `critical`.

### 2.4 Decision Point

The rejection decision happens at `colony_manager.py` lines 1055-1056:

```python
if scan_result["tier"] in ("high", "critical"):
    entry["status"] = "rejected"
```

After this, `MemoryEntryCreated` is emitted (line 1065) with scan_status
and status baked in. Non-rejected entries from completed colonies are
auto-promoted to `verified` via `MemoryEntryStatusChanged` (line 1072-1080).

### 2.5 AST Security Check

Separate from the 4-axis scanner. Used for sandboxed Python code execution
screening before code runs, not during knowledge extraction.

**File:** `src/formicos/adapters/ast_security.py` (81 lines)

**Function:** `check_ast_safety(code: str) -> ASTCheckResult`

Blocks 15 module roots (`os`, `subprocess`, `sys`, `shutil`, `signal`,
`ctypes`, `multiprocessing`, `threading`, `socket`, `http`, `importlib`,
`code`, `compileall`, `runpy`, `pathlib`) and 6 builtins (`eval`, `exec`,
`compile`, `__import__`, `breakpoint`, `open`).

Does NOT check: string literal content, credential patterns, prompt
injection in strings, dynamic imports, or supply chain attacks.

### 2.6 Output Sanitizer

Post-execution cleanup for sandboxed code output.

**File:** `src/formicos/adapters/output_sanitizer.py` (26 lines)

**Function:** `sanitize_output(text: str) -> str`

Strips ANSI escape sequences and truncates to 10,000 characters. Does NOT
inspect content for credentials, PII, or injection patterns.

### 2.7 Extension Points -- Section 2

To add a 5th scanning axis, modify `scan_entry()` in `memory_scanner.py`:

1. Define pattern regexes before `scan_entry()` (after line 83)
2. Add axis key to `scores` dict (line 111-116):
   `"your_axis": 0.0`
3. Add scan logic inside `scan_entry()` (after line 150):
   ```python
   if _RE_YOUR_PATTERN.search(content):
       scores["your_axis"] += X.X
       findings.append("description")
   ```
4. No other changes needed -- composite score auto-incorporates the new
   axis, and tier thresholds apply unchanged.

**Required interface:** `scan_entry(entry: dict[str, Any]) -> dict` with
return keys `"tier"`, `"score"`, `"axes"`, `"findings"`.

| Feature | Insertion Point |
|---------|----------------|
| Credential/secrets scan | New axis in `scan_entry()` after line 150 |
| Entropy analysis | New axis (compute Shannon entropy of content) |
| Keyword-context detection | New axis with contextual pattern matching |
| Per-axis rejection thresholds | Modify `_tier_from_score()` line 28 to accept axis dict |

---

## 3. Knowledge Storage and Projection

### 3.1 MemoryEntryCreated Event

Emitted at `colony_manager.py` line 1065-1069:

```python
await self._runtime.emit_and_broadcast(MemoryEntryCreated(
    seq=0, timestamp=_now(), address=address,
    entry=entry,            # Full dict, source of truth for replay
    workspace_id=workspace_id,
))
```

Event definition: `core/events.py` lines 668-677. The `entry` field is a
`dict[str, Any]` containing the serialized MemoryEntry.

Address format: `{workspace_id}/{thread_id}/{colony_id}`.

### 3.2 Projection Handler

**File:** `src/formicos/surface/projections.py`

**Handler:** `_on_memory_entry_created()` (lines 724-732)

```python
def _on_memory_entry_created(store: ProjectionStore, event: FormicOSEvent) -> None:
    entry = e.entry
    entry_id = entry.get("id", "")
    if entry_id:
        data = dict(entry)
        data.setdefault("last_confidence_update", data.get("created_at", ""))
        store.memory_entries[entry_id] = data
```

Registered in `_HANDLERS` dict at line 855.

### 3.3 Projection Schema

`ProjectionStore.memory_entries` is `dict[str, dict[str, Any]]` keyed by
entry ID. Full field inventory:

| Field | Type | Source | Updated By |
|-------|------|--------|------------|
| id | str | MemoryEntryCreated | -- |
| entry_type | str | MemoryEntryCreated | -- |
| status | str | MemoryEntryCreated | MemoryEntryStatusChanged |
| polarity | str | MemoryEntryCreated | -- |
| title | str | MemoryEntryCreated | -- |
| content | str | MemoryEntryCreated | -- |
| summary | str | MemoryEntryCreated | -- |
| source_colony_id | str | MemoryEntryCreated | -- |
| source_artifact_ids | list[str] | MemoryEntryCreated | -- |
| domains | list[str] | MemoryEntryCreated | -- |
| tool_refs | list[str] | MemoryEntryCreated | -- |
| confidence | float | MemoryEntryCreated | MemoryConfidenceUpdated |
| scan_status | str | MemoryEntryCreated | -- |
| created_at | str | MemoryEntryCreated | -- |
| workspace_id | str | MemoryEntryCreated | -- |
| thread_id | str | MemoryEntryCreated | MemoryEntryScopeChanged |
| conf_alpha | float | MemoryEntryCreated | MemoryConfidenceUpdated |
| conf_beta | float | MemoryEntryCreated | MemoryConfidenceUpdated |
| last_confidence_update | str | Derived (Wave 32 A1) | MemoryConfidenceUpdated |
| last_status_reason | str | Derived | MemoryEntryStatusChanged |

### 3.4 Qdrant Sync Path

`emit_and_broadcast()` in `runtime.py` (lines 426-446) is the ONE mutation
path. After appending to the event store and applying to projections, it
live-syncs memory events to Qdrant:

```
emit_and_broadcast(event)
  -> event_store.append(event)           # persist
  -> projections.apply(event)            # in-memory read model
  -> ws_manager.fan_out_event(event)     # operator visibility
  -> memory_store.sync_entry(id, entries) # Qdrant sync (if memory event)
```

Sync triggers on `MemoryEntryCreated` and `MemoryEntryStatusChanged` events.
If entry status is `rejected`, Qdrant point is deleted. Otherwise,
`upsert_entry()` in `memory_store.py` (lines 53-88) constructs:

- Embedding text from `title + content + summary + tool_refs + domains`
- `VectorDocument` with full metadata payload
- Qdrant `PointStruct` with named vectors:
  - `dense`: embedding from configured model
  - `sparse`: BM25 via `Qdrant/bm25`

Qdrant collection: `institutional_memory`. Payload indexes on: namespace,
confidence, algorithm_version, extracted_at, source_colony, source_colony_id.

### 3.5 Startup Replay and Rebuild

At startup (`app.py` lines 407-420):

1. Event store `replay()` yields all events in sequence order
2. Each event is applied via `projections.apply()` -- handlers rebuild
   in-memory state deterministically
3. `memory_store.rebuild_from_projection()` re-upserts all non-rejected
   entries to Qdrant from projection state

### 3.6 Pattern for Adding Derived Fields

Three patterns exist in the projection handlers:

**On creation** (seed a default):
```python
data.setdefault("new_field", data.get("created_at", ""))
```

**On update** (mutate from event):
```python
entry["new_field"] = e.new_value
```

**On status change** (attach reason):
```python
entry["last_status_reason"] = e.reason
```

Derived fields are NOT persisted as event data -- they are recomputed from
events during replay.

### 3.7 Extension Points -- Section 3

| Feature | Where to Add | Pattern |
|---------|-------------|---------|
| `last_scanned_pattern_version` | `_on_memory_entry_created` handler, line 731 | `data.setdefault("last_scanned_pattern_version", 1)` |
| `last_confidence_update` timestamp | Already exists (Wave 32 A1) | Updated in `_on_memory_confidence_updated` handler, line 784 |
| `provenance` metadata | Add to MemoryEntry model in `types.py` line 331 + projection handler | Set from extraction context, flow through event |
| Federation CRDT fields | Add to MemoryEntry model + new projection handler for merge events | See Section 5.6 for confidence merge point |

---

## 4. Knowledge Retrieval and Scoring

### 4.1 Agent Tool Call Entry Point

An agent invokes `memory_search` tool defined in `engine/runner.py`
(lines 53-75):

```
Tool: memory_search
Parameters: query (required, string), top_k (optional, int, default 5, max 10)
Category: ToolCategory.vector_query
```

Execution dispatcher (`_execute_tool()` at line 1257) calls
`_handle_memory_search()` (lines 388-482) which searches three tiers:

1. Colony scratch memory: `scratch_{colony_id}` collection
2. Workspace memory: `workspace_id` collection
3. **Knowledge catalog**: `catalog_search_fn()` callback

The catalog callback is wired via `runtime.make_catalog_search_fn()`
(runtime.py lines 1037-1052) which delegates to `KnowledgeCatalog.search()`.

### 4.2 Composite Scoring Formula

**File:** `src/formicos/surface/knowledge_catalog.py`
**Function:** `_composite_key()` (lines 130-145)

```
composite = 0.40 * semantic
           + 0.25 * thompson
           + 0.15 * freshness
           + 0.12 * status
           + 0.08 * thread_bonus
```

Returns negative value for ascending sort (higher composite ranks first).

| Signal | Weight | Range | Source |
|--------|--------|-------|--------|
| semantic | 0.40 | [0, 1] | Cosine similarity from Qdrant vector search |
| thompson | 0.25 | [0, 1] | `random.betavariate(conf_alpha, conf_beta)` -- stochastic |
| freshness | 0.15 | [0, 1] | `2.0 ** (-age_days / 90.0)` -- 90-day half-life |
| status | 0.12 | [0, 1] | Lookup: verified=1.0, active=0.8, candidate=0.5, stale=0.0 |
| thread_bonus | 0.08 | {0, 1} | 1.0 if thread matches, 0.0 otherwise |

**Note:** The code weights (0.40, 0.25, 0.15, 0.12, 0.08) differ from
`KNOWLEDGE_LIFECYCLE.md` which documents (0.35, 0.25, 0.15, 0.15, 0.10).
The code is authoritative.

### 4.3 Freshness Decay

`_compute_freshness()` (lines 108-120): exponential decay with 90-day
half-life. Returns 1.0 for empty or invalid timestamps. Does not cap
values above 1.0 (future timestamps produce values > 1.0).

### 4.4 Status Bonus Table

`_STATUS_BONUS` dict (lines 124-127):

```python
{"verified": 1.0, "active": 0.8, "candidate": 0.5, "stale": 0.0}
```

Unknown status values default to 0.0.

### 4.5 Thread-Boosted Two-Phase Search

`_search_thread_boosted()` (lines 300-366) runs when `thread_id` is
provided:

**Phase 1** (lines 314-328): Search institutional memory filtered by
`thread_id`. Each result gets `item["_thread_bonus"] = 1.0`.

**Phase 2** (lines 330-341): Search institutional memory workspace-wide
(no thread filter). Thread bonus defaults to 0.0.

**Merge** (lines 343-363): Thread-boosted version wins dedup (thread
items appear first in concatenation, `seen` set prevents duplicates).
Legacy skills (no thread concept) are appended.

**Sort** (line 365): `merged.sort(key=_composite_key)` applies the full
composite formula including thread bonus.

### 4.6 Keyword Fallback Path

`_projection_keyword_fallback()` (lines 264-298) activates when Qdrant
is unavailable (any exception in `_search_vector()`).

- Reads directly from `projections.memory_entries.values()`
- Filters by workspace_id and status in (verified, active, candidate)
- BM25-style word-overlap scoring on `{title, content, domains}` combined
- No composite scoring -- pure word overlap count
- Results tagged with `source="keyword_fallback"`

New fields in the projection dict are NOT automatically included in
keyword fallback. To include a field (e.g., provenance), add it to the
text construction at line 284-287.

### 4.7 Extension Points -- Section 4

| Feature | Insertion Point | Pattern |
|---------|----------------|---------|
| New scoring signal | `_composite_key()` line 130 | Extract from item dict, add weighted term |
| Provenance depth | `_composite_key()` | `item.get("_provenance_depth", 0.0)` with new weight |
| Peer trust score | `_composite_key()` | Populate during normalization, weight in composite |
| Federation hop count | `_composite_key()` | Penalty signal: `1.0 / (1 + hops)` |
| New fallback field | `_projection_keyword_fallback()` line 284-287 | Add field to text string |

To add a new scoring signal:
1. Add a weight constant (rebalance sum to ~1.00 if desired)
2. Extract the signal value from `item.get("_signal_name", default)`
3. Add `+ weight * signal` to the composite return expression
4. Populate `_signal_name` in normalization functions
   (`_normalize_institutional()` line 84 or `_normalize_legacy_skill()` line 50)

---

## 5. Confidence Evolution

### 5.1 Post-Colony Confidence Update

**File:** `src/formicos/surface/colony_manager.py`
**Function:** `_hook_confidence_update()` (lines 789-878)

Triggered from `_post_colony_hooks()` (line 673) after every colony
completes or fails.

**Process:**
1. Extract all knowledge entry IDs accessed during the colony from
   `colony_proj.knowledge_accesses` (traces with items)
2. For each accessed entry (deduped):
   a. Read current `conf_alpha`, `conf_beta` from projection
   b. Apply gamma-decay (time-based)
   c. Apply observation (colony outcome)
   d. Emit `MemoryConfidenceUpdated` event

### 5.2 Gamma-Decay Formulation (ADR-041 D1)

**Constants:** `src/formicos/surface/knowledge_constants.py`

```
GAMMA_PER_DAY = 0.98        (half-life: ~34.3 calendar days)
PRIOR_ALPHA = 5.0
PRIOR_BETA = 5.0
ARCHIVAL_EQUIVALENT_DAYS = 30
```

**Formula** (colony_manager.py lines 834-836):

```
elapsed_days = (event_ts - last_confidence_update) / 86400.0
gamma_eff = GAMMA_PER_DAY ** elapsed_days

alpha_decayed = gamma_eff * alpha_old + (1 - gamma_eff) * PRIOR_ALPHA
beta_decayed  = gamma_eff * beta_old  + (1 - gamma_eff) * PRIOR_BETA
```

Properties:
- Time-based, not observation-based -- popularity does not affect decay rate
- Multiple same-day observations barely decay between them
- Half-life of ~34 days allows meaningful adaptation within 4-5 weeks
- Decays toward prior (5.0, 5.0) -- increases uncertainty over time

### 5.3 Observation Application

After decay, the colony outcome updates the posterior
(colony_manager.py lines 838-843):

```
If succeeded: new_alpha = max(decayed_alpha + 1.0, 1.0)
If failed:    new_beta  = max(decayed_beta  + 1.0, 1.0)
```

Posterior mean: `new_confidence = new_alpha / (new_alpha + new_beta)`

### 5.4 Archival Decay / Gamma-Burst (ADR-041 D2)

**File:** `src/formicos/surface/queen_thread.py`
**Function:** `archive_thread()` (lines 111-173)

Triggered when a thread transitions to `archived` status. Applies a
one-time gamma-burst equivalent to 30 days of natural decay:

```
archival_gamma = GAMMA_PER_DAY ** ARCHIVAL_EQUIVALENT_DAYS  # 0.98^30 ~ 0.545

new_alpha = max(archival_gamma * old_alpha + (1 - archival_gamma) * PRIOR_ALPHA, 1.0)
new_beta  = max(archival_gamma * old_beta  + (1 - archival_gamma) * PRIOR_BETA, 1.0)
```

Properties:
- **Symmetric:** Both alpha and beta decay toward prior at same rate (does
  not bias posterior mean, only widens uncertainty)
- **Composes** with time-decay (same gamma family, different rate)
- **Uniform:** All thread-scoped entries receive burst regardless of
  individual history
- Example: `alpha=20` -> `0.545 * 20 + 0.455 * 5 = 13.2` (still above
  prior, wider uncertainty)

Each entry's update emits `MemoryConfidenceUpdated` with
`reason="archival_decay"` (lines 150-166).

### 5.5 Alpha/Beta Read and Write Points

Every location where `conf_alpha` and `conf_beta` are read or written:

| Operation | File | Lines | Context |
|-----------|------|-------|---------|
| **WRITE** projection | projections.py | 780-781 | `_on_memory_confidence_updated` handler |
| **WRITE** timestamp | projections.py | 784 | `last_confidence_update` derived field |
| **READ** confidence hook | colony_manager.py | 814-815 | Before gamma-decay |
| **READ** archival burst | queen_thread.py | 143-144 | Before archival decay |
| **READ** confidence reset | maintenance.py | 344-345 | Threshold check |
| **READ** Thompson scoring | knowledge_catalog.py | 133-134 | Composite retrieval |
| **READ** contradiction | maintenance.py | 312-313 | Report display |

### 5.6 Extension Points -- Section 5

| Feature | Insertion Point | Details |
|---------|----------------|---------|
| Foreign confidence evidence (federation) | Between READ and gamma-decay in `_hook_confidence_update()` lines 814-836 | CRDT G-Counter merge: `alpha = max(local_alpha, remote_alpha)` before decay |
| Merge-before-update step | New function called at line 814, before decay | Read remote alpha/beta, merge, then proceed with decay + observation |
| Alternative decay rate | `knowledge_constants.py` | Change `GAMMA_PER_DAY` or make it per-entry |
| Time-based decay without observation | New scheduled hook | Apply gamma-decay periodically without colony outcome |

**Federation merge pattern:** The CRDT G-Counter merge for alpha/beta must
happen BEFORE the gamma-decay step. The sequence would be:

```
1. Read local alpha/beta from projection
2. Merge with remote alpha/beta: alpha = max(local, remote) for each
3. Apply gamma-decay to merged values
4. Apply observation (colony outcome)
5. Emit MemoryConfidenceUpdated with merged + decayed + observed values
```

---

## 6. Maintenance Services

### 6.1 Registration Pattern

**File:** `src/formicos/surface/app.py` (lines 509-534)

Handlers are async closures created by factory functions in
`maintenance.py`, registered via:

```python
service_router.register_handler(
    "service:consolidation:NAME",
    make_NAME_handler(runtime),
)
```

**ServiceRouter API** (`engine/service_router.py` lines 108-119):

```python
def register_handler(
    self,
    service_type: str,
    handler: Callable[[str, dict[str, Any]], Awaitable[str]],
) -> None:
```

Handler signature: `async (query_text: str, ctx: dict[str, Any]) -> str`

Each registration emits a `DeterministicServiceRegistered` event for
operator visibility (app.py lines 537-566).

**Scheduled loop** (app.py lines 573-598): Runs dedup, stale_sweep, and
contradiction every 24 hours (configurable via
`FORMICOS_MAINTENANCE_INTERVAL_S` env var). Timeout: 300s per service.

### 6.2 Dedup Handler

**File:** `src/formicos/surface/maintenance.py`, lines 22-198
**Service type:** `service:consolidation:dedup`

Scans all verified entries sorted by creation time:

- **High similarity (>= 0.98):** Auto-merge. Emits
  `MemoryEntryStatusChanged(new_status="rejected")` for lower-confidence
  entry. Reason: `"dedup:auto_merge (similarity X.XXX, kept ID)"`

- **Medium similarity (0.82-0.98):** LLM review (Wave 30 B9). Checks
  previous dismissals via `last_status_reason` containing
  `"dedup:dismissed"`. If not dismissed, queries LLM: "Do these describe
  the same thing?" (temperature 0.0, max_tokens 10). Confirmed merges
  emit rejection event. Dismissals emit status-unchanged event as durable
  marker.

### 6.3 Stale Sweep Handler

**File:** `src/formicos/surface/maintenance.py`, lines 201-249
**Service type:** `service:consolidation:stale_sweep`

Criteria: entry not already `rejected`/`stale`, age > 90 days, entry ID
not in `accessed_ids` set (built from colony knowledge access traces).

Action: Emits `MemoryEntryStatusChanged(new_status="stale")`.

Confidence decay during stale sweep is NOT implemented -- deferred to
avoid mutating projection state without a proper event.

### 6.4 Contradiction Detection Handler

**File:** `src/formicos/surface/maintenance.py`, lines 275-325
**Service type:** `service:consolidation:contradiction`
**Added:** Wave 30 S14

Algorithm: For verified entries with non-neutral polarity and at least one
domain, checks all pairs for opposite polarity + domain overlap (Jaccard
similarity > 0.3).

Returns JSON report only -- no automatic action. Operator decides
resolution.

### 6.5 Confidence Reset Handler

**File:** `src/formicos/surface/maintenance.py`, lines 328-374
**Service type:** `service:consolidation:confidence_reset`

Manual-only (not in scheduled loop). Criteria:
- Total observations beyond prior >= 50: `(alpha + beta - 10.0) >= 50`
- Posterior mean in indecisive range: `0.35 <= mean <= 0.65`

Action: Reset to prior (`alpha=5.0, beta=5.0, confidence=0.5`). Emits
`MemoryConfidenceUpdated` with `reason="manual_reset"`.

### 6.6 Extension Points -- Section 6

| Feature | Pattern | Details |
|---------|---------|---------|
| `credential_sweep` handler | `make_credential_sweep_handler(runtime)` in maintenance.py | Iterate `memory_entries`, re-scan with new patterns, emit `MemoryEntryStatusChanged` for newly-rejected entries |
| `federation_sync` handler | `make_federation_sync_handler(runtime)` in maintenance.py | Pull remote events, apply CRDT merge, emit local `MemoryConfidenceUpdated` events |
| Any new handler | 1. Factory in `maintenance.py` 2. Register in `app.py` line 519-534 3. Add to scheduled loop if recurring | Follow handler signature: `async (query_text, ctx) -> str` |

---

## 7. Cross-Cutting Concerns

### 7.1 Event Emission Pattern

**File:** `src/formicos/surface/runtime.py`
**Function:** `emit_and_broadcast()` (lines 426-446)

```python
async def emit_and_broadcast(self, event: FormicOSEvent) -> int:
    """The ONE mutation path: append -> project -> fan out to WS."""
    seq = await self.event_store.append(event)
    event_with_seq = event.model_copy(update={"seq": seq})
    self.projections.apply(event_with_seq)
    await self.ws_manager.fan_out_event(event_with_seq)
    # ... Qdrant live sync for memory events ...
    return seq
```

Signature: `async (self, event: FormicOSEvent) -> int`

Returns the assigned sequence number. All state changes in the system
flow through this single function. There is no other write path.

### 7.2 Projection Rebuild

**File:** `src/formicos/surface/projections.py`

`ProjectionStore` (line 235) maintains in-memory read models:
- `workspaces: dict[str, WorkspaceProjection]`
- `colonies: dict[str, ColonyProjection]`
- `merges: dict[str, MergeProjection]`
- `approvals: dict[str, ApprovalProjection]`
- `templates: dict[str, TemplateProjection]`
- `memory_entries: dict[str, dict[str, Any]]`
- `memory_extractions_completed: set[str]`
- `last_seq: int`

**Replay method:** `apply(event)` dispatches to `_HANDLERS[event_type_name]`.
`replay(events)` applies a batch sequentially. The `_HANDLERS` dict maps
45 event types to pure handler functions (lines 817-865).

**Startup sequence** (app.py lines 407-420):
1. `async for event in event_store.replay(): projections.apply(event)`
2. `memory_store.rebuild_from_projection(projections.memory_entries)`

Federation note: Replaying CRDT events from a peer must go through the
same `apply()` path to produce correct projection state. Foreign events
would need to be appended to the local event store first, then applied.

### 7.3 StrEnum Fields (Wave 32 C3)

All StrEnum classes are defined in `src/formicos/core/types.py`. A
federation protocol must serialize these as their string values.

| StrEnum | Values | Used By |
|---------|--------|---------|
| ApprovalType | budget_increase, cloud_burst, tool_permission, expense | `ApprovalRequested.approval_type` |
| ServicePriority | normal, high | Service query priority |
| RedirectTrigger | queen_inspection, governance_alert, operator_request | `ColonyRedirected.trigger` |
| MergeReason | llm_dedup | `SkillMerged.merge_reason` |
| AccessMode | context_injection, tool_search, tool_detail, tool_transcript | `KnowledgeAccessRecorded.access_mode` |
| ScanStatus | pending, safe, low, medium, high, critical | `MemoryEntry.scan_status` |
| MemoryEntryType | skill, experience | `MemoryEntry.entry_type` |
| MemoryEntryStatus | candidate, verified, rejected, stale | `MemoryEntry.status` |
| MemoryEntryPolarity | positive, negative, neutral | `MemoryEntry.polarity` |
| WorkflowStepStatus | pending, running, completed, failed, skipped | `WorkflowStep.status` |

Earlier StrEnums (pre-Wave 32): `SubcasteTier`, `ChatSender`,
`ArtifactType`, `ToolCategory`, `NodeType`.

Pydantic v2 transparently deserializes plain strings into StrEnums, so
existing persisted events remain compatible. A federation peer sending
plain string values will deserialize correctly.

### 7.4 Handler Registration Summary

45 event types have projection handlers registered in `_HANDLERS`
(projections.py lines 817-865). `DeterministicServiceRegistered` has a
no-op handler (`lambda store, event: None`). Three event types from the
48-event union have no projection effect and are not registered.

---

## Appendix A: File Reference Index

| File | Section | Lines of Interest |
|------|---------|-------------------|
| `src/formicos/surface/colony_manager.py` | 1, 5 | 583-588 (completion), 649-674 (hooks), 772-787 (extraction trigger), 789-878 (confidence), 955-963 (extraction main), 1051-1069 (scan + emit) |
| `src/formicos/surface/memory_extractor.py` | 1 | 29-72 (prompt), 75-115 (entry construction), 118-139 (parsing) |
| `src/formicos/surface/memory_scanner.py` | 2 | 20-32 (tiers), 36-83 (patterns), 91-159 (scan_entry) |
| `src/formicos/adapters/ast_security.py` | 2 | 27-38 (blocked lists), 41-81 (check_ast_safety) |
| `src/formicos/adapters/output_sanitizer.py` | 2 | 17-26 (sanitize_output) |
| `src/formicos/surface/projections.py` | 3, 7 | 235-266 (ProjectionStore), 724-732 (memory created), 774-784 (confidence updated), 817-865 (handler registry) |
| `src/formicos/surface/runtime.py` | 3, 7 | 426-446 (emit_and_broadcast), 1037-1052 (catalog callback) |
| `src/formicos/surface/knowledge_catalog.py` | 4 | 108-120 (freshness), 124-127 (status bonus), 130-145 (composite key), 165-194 (search), 264-298 (keyword fallback), 300-366 (thread boosted) |
| `src/formicos/engine/runner.py` | 4 | 53-75 (tool spec), 282-287 (category map), 388-482 (memory search handler), 1257-1272 (dispatch) |
| `src/formicos/surface/knowledge_constants.py` | 5 | GAMMA_PER_DAY, PRIOR_ALPHA, PRIOR_BETA, ARCHIVAL_EQUIVALENT_DAYS |
| `src/formicos/surface/queen_thread.py` | 5 | 111-173 (archival decay) |
| `src/formicos/surface/maintenance.py` | 6 | 22-198 (dedup), 201-249 (stale), 275-325 (contradiction), 328-374 (confidence reset) |
| `src/formicos/surface/app.py` | 3, 6 | 296-303 (catalog init), 407-420 (replay), 509-534 (handler registration), 573-598 (scheduled loop) |
| `src/formicos/core/types.py` | 3, 7 | 257-328 (StrEnums), 331-372 (MemoryEntry model) |
| `src/formicos/core/events.py` | 3, 7 | 668-677 (MemoryEntryCreated) |
| `src/formicos/engine/service_router.py` | 6 | 108-119 (register_handler), 150-183 (dispatch) |
