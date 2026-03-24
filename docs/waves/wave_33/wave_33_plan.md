# Wave 33 Plan -- Intelligent Federation

**Wave:** 33 -- "Intelligent Federation"
**Theme:** The knowledge pipeline gains transcript-level extraction, inline dedup, and prediction error detection. Every API surface becomes self-guiding with structured errors, MCP resources, and response enrichment. Credential scanning closes the last security gap. Two FormicOS instances can share knowledge bidirectionally using Computational CRDTs with Bayesian trust discounting. After Wave 33, FormicOS is both externally operable and federatable.

**Prerequisite:** Wave 32.5 landed. StructuredError model + 5 mappers + 17 KNOWN_ERRORS in `surface/structured_error.py`. MCP annotations on all 19 tools. PromptsAsTools + ResourcesAsTools transforms registered. APPROVAL_NEEDED AG-UI promotion pattern established. `_next_actions` convention on spawn_colony. 1,564 tests passing, 0 pyright errors, 0 ruff violations, 0 layer violations.

**Contract changes:** Event union expands from 48 to 53 (requires operator approval + ADR-042). 5 new event types: 4 CRDT operation events + 1 MemoryEntryMerged. `detect-secrets` added as dependency. `decay_class` field added to MemoryEntry. `ObservationCRDT` model added to core. MCP resources and prompts added. Co-occurrence data collection infrastructure added (scoring integration deferred to Wave 34 + ADR-043).

**ADRs required before coder dispatch:**
- ADR-042: Event union expansion 48 to 53. Covers MemoryEntryMerged schema (dual-purpose: dedup handler + federation), 4 CRDT event schemas, rationale for breaking the closed-union constraint.
- ADR-043: Co-occurrence data model. Covers collection infrastructure (reinforcement hooks, decay in maintenance), explicit deferral of scoring integration to Wave 34 with weight rebalancing.

---

## What shaped this plan

### Research findings that changed the architecture

| Assumption | Finding | Source | Impact |
|---|---|---|---|
| G-Counters for federated alpha/beta | G-Counters are provably incompatible with gamma-decay (decay violates monotonic inflation requirement, Shapiro et al. 2011) | Implementation unknowns research | Must use Computational CRDT: raw G-Counter observation counts + LWW timestamps + query-time decay |
| Trust score = Beta mean | Mean-based trust lets a new peer reach 0.9 after only 9 successes -- gaming vulnerability | Implementation unknowns research | Use 10th percentile: `scipy.stats.beta.ppf(0.10, alpha, beta)`. Reaching 0.8 requires ~30+ successes |
| Conflict threshold fixed at 0.1 | 0.1 threshold keeps ~52% of conflicts as "competing hypotheses" -- far too permissive | Implementation unknowns research | Adaptive threshold: `0.05 + 2.0 / avg(evidence)` + Pareto dominance pre-filter |
| Gamma-decay unbounded | At 180+ days, gamma_eff < 0.026 and all entries converge to indistinguishable-from-prior | Implementation unknowns research | Cap max_elapsed_days at 180. Add decay_class (ephemeral/stable/permanent) |
| detect-secrets scan_line() API | No string-scanning API exists. Must write to temp files. transient_settings is not thread-safe | Credential scanning research | Temp file workaround + multiprocessing for parallel scans |
| Knowledge extractor sees full transcripts | Extractor only sees compressed final summary. Tool call outputs with credentials are invisible | Knowledge Pipeline Reference Section 1.3 | Transcript harvest at hook position 4.5 using chat_messages |
| Dedup handler only rejects duplicates | Rejecting the lower-confidence entry discards tags, provenance, and observation history | NeuroStack analysis item 8 | MemoryEntryMerged event with content selection, tag union, merged_from provenance |
| Near-duplicates caught by maintenance loop | 24-hour gap between extraction and dedup allows duplicates to compete in retrieval | NeuroStack analysis item 6.1 | Inline dedup check at extraction time (cosine > 0.92 against projection) |

### Orchestrator feedback that restructured the tracks

| Concern | Resolution |
|---|---|
| Track A overloaded (7 features touching 5 files) | Moved credential scanning from Track A to Track B. Track A stays at 4 knowledge-pipeline features + co-occurrence data collection |
| Co-occurrence weight at 0.05 changes composite formula again after ADR-041 just stabilized it | Deferred scoring integration to Wave 34. Wave 33 collects co-occurrence data only (reinforcement + decay). ADR-043 covers the deferral |
| Event union 48 to 53 is a hard constraint violation | Called out explicitly. Requires operator approval + ADR-042 with merge event schema and dual-purpose semantics documented |

---

## Track A: Knowledge Pipeline Intelligence

Four features, all internal to the knowledge pipeline. Plus co-occurrence data COLLECTION only (no scoring integration -- that's Wave 34).

### A1. Transcript harvest at hook position 4.5

The Knowledge Pipeline Reference Section 1.3 confirms the extractor only sees compressed summaries from the final round. Individual agent turns, tool call results, and inter-round progression are invisible. A second extraction pass on the full transcript catches bug root causes, operator conventions, tool configurations, and operational learnings that the compressed summary misses.

**Data source:** `colony_proj.chat_messages` (structured data), NOT `build_transcript()` (formatted text). chat_messages preserves agent_id, caste, tool_name, and output per turn. The security scanner needs raw text. The insight extractor needs to know which agent said what.

**Hook position:** Separate hook at position 4.5 in `_post_colony_hooks()`, between `_hook_memory_extraction` (position 4) and `_hook_confidence_update` (position 5). NOT an extension of the existing extraction hook -- different failure modes, different contract, and the harvest benefits from seeing extraction results (can read `memory_extractions_completed` to avoid re-extracting).

**Hook signature:**
```python
async def _hook_transcript_harvest(
    colony_id: str,
    workspace_id: str,
    colony_proj: ColonyProjection,
    succeeded: bool,
) -> None:
```

**Extraction prompt design:** Batch prompt processing agent turns. For each numbered turn, the LLM classifies as KEEP (with type: bug/decision/convention/learning and one-sentence summary) or SKIP. Include agent caste and round number per turn. No regex pre-filter -- use LLM for all classification with empty-result fallback.

**Dedup within harvest:** Before emitting MemoryEntryCreated for harvest entries, check embedding cosine similarity against Qdrant institutional_memory collection. Skip if >= 0.82 similar to any existing entry (matches the dedup handler's medium-similarity band from Knowledge Pipeline Reference Section 6.2).

**Tracking:** Extend `memory_extractions_completed` set with `"colony-abc123:harvest"` suffix to distinguish structured extraction from transcript harvest. On replay, both tokens rebuild from events.

**Concrete examples of what the harvest catches:**
- Bug root causes from test failure -> agent fix sequences in tool call results
- Operator corrections from chat_colony messages ("don't use subprocess, use the sandbox")
- Tool configuration discoveries ("Qdrant batch upsert limit: 100 points/call")

**Files touched:**
- `surface/colony_manager.py` -- add `_hook_transcript_harvest()`, wire at position 4.5 in dispatcher
- `surface/memory_extractor.py` -- add `build_harvest_prompt()` and `parse_harvest_response()` (separate from structured extraction functions)
- `surface/projections.py` -- extend `memory_extractions_completed` handling for `:harvest` suffix

### A2. Inline dedup check at extraction time

Concurrent colonies on related tasks can extract near-duplicate entries. The dedup maintenance handler catches this eventually (24-hour loop), but for up to 24 hours both entries exist and compete in retrieval. Thompson Sampling can make this worse by promoting one duplicate over the other stochastically.

**Implementation:** After `build_memory_entries()` constructs entries but BEFORE the security scan and MemoryEntryCreated emission, check the current projection for entries with cosine similarity > 0.92 (the auto-merge threshold):

```python
for entry in new_entries:
    existing = _find_similar_in_projection(
        entry["content"], projections.memory_entries, threshold=0.92,
        workspace_id=workspace_id,
    )
    if existing:
        # Reinforce existing entry's confidence instead of creating duplicate
        await _reinforce_existing_entry(runtime, existing["id"], succeeded)
        continue
    # Proceed with scan + emit
```

This is one embedding comparison against the projection, not a Qdrant search. Cheap and prevents the most obvious duplicates.

**Files touched:**
- `surface/colony_manager.py` -- add inline dedup check in extraction flow (between entry construction and scan/emit)

### A3. Prediction error counters

When the top search results have low semantic similarity to the query, the system is returning entries that were promoted by non-semantic signals (Thompson exploration, thread bonus, freshness) but aren't actually relevant. Logging these as prediction errors creates a staleness signal more accurate than age alone.

**Implementation:** Lightweight projection-only counters (not full events). High-volume, low-value individually, lossy by design. Rebuilt from zero on replay (ephemeral). Three projection fields per entry:

```python
"prediction_error_count": int         # incremented per detection
"last_prediction_error_at": str       # ISO timestamp
"prediction_error_queries": list[str] # last 3 triggering queries (truncated to 200 chars)
```

**Insertion point:** After ranking in `_search_thread_boosted()` (after the sort at line 365), check only the top-k results. Use raw semantic score (before composite weighting), NOT the composite score. Threshold: cosine sim < 0.38 (calibrate empirically after deployment by sampling 100 queries and setting at the 10th percentile of top-result similarities).

**Consumption:** The stale_sweep maintenance handler reads prediction_error_count as an additional staleness signal alongside age and access frequency. An entry with high prediction error count and low access frequency is drifting out of relevance.

**Files touched:**
- `surface/knowledge_catalog.py` -- add prediction error detection after ranking in `_search_thread_boosted()`
- `surface/maintenance.py` -- add prediction_error_count to stale_sweep criteria

### A4. Gamma-decay hardening

Two changes from the implementation unknowns research.

**Cap max_elapsed_days at 180:** Beyond this threshold, gamma_eff < 0.026 and all values converge to indistinguishable-from-prior. The cap preserves a trace of extreme prior confidence (alpha=500 stays at 18.04 vs 5.31 uncapped at 365 days).

```python
# knowledge_constants.py
MAX_ELAPSED_DAYS = 180.0
```

Apply in the confidence update hook (colony_manager.py) and archival decay (queen_thread.py):
```python
elapsed_days = min((event_ts - last_update) / 86400.0, MAX_ELAPSED_DAYS)
```

**Add decay_class to MemoryEntry:**

```python
# core/types.py
class DecayClass(StrEnum):
    ephemeral = "ephemeral"    # gamma=0.98, half-life ~34 days (task-specific observations)
    stable = "stable"          # gamma=0.995, half-life ~139 days (domain knowledge)
    permanent = "permanent"    # gamma=1.0, no decay (verified definitions, mathematical facts)

# knowledge_constants.py
GAMMA_RATES: dict[str, float] = {
    "ephemeral": 0.98,
    "stable": 0.995,
    "permanent": 1.0,
}
```

Default: `ephemeral` (preserves current behavior). The extraction prompt in `memory_extractor.py` gets an additional instruction to classify entries. Mathematical facts, verified definitions, and stable domain knowledge should be tagged `stable` or `permanent`. Existing entries default to `ephemeral` -- retroactive classification is a future maintenance handler.

**Files touched:**
- `core/types.py` -- DecayClass StrEnum, decay_class field on MemoryEntry
- `surface/knowledge_constants.py` -- GAMMA_RATES dict, MAX_ELAPSED_DAYS constant
- `surface/colony_manager.py` -- decay_class lookup in confidence update, max_elapsed_days cap
- `surface/queen_thread.py` -- max_elapsed_days cap in archival decay
- `surface/memory_extractor.py` -- decay_class in extraction prompt

### A5. Co-occurrence data collection (scoring deferred to Wave 34)

Build the co-occurrence reinforcement infrastructure WITHOUT adding it to the composite scoring formula. Wave 34 activates it as a scoring signal with proper weight rebalancing via a dedicated ADR.

**Data structure on projection store:**
```python
@dataclass
class CooccurrenceEntry:
    weight: float
    last_reinforced: str     # ISO timestamp
    reinforcement_count: int

# ProjectionStore
cooccurrence_weights: dict[tuple[str, str], CooccurrenceEntry]
```

Canonical pair ordering (entry_a_id < entry_b_id by string comparison) prevents duplicates. Sparse structure -- at 2,000 entries with 5 accessed per colony, actual density is well under 1% of the theoretical 2M pair maximum.

**Result-result reinforcement** in `_hook_confidence_update()` after colony completion: build pairs of all entries accessed in the colony. Reinforce weight by 1.1x for successful colonies, 0.0x for failed (don't reinforce co-occurrence of entries present during failure). Cap at 10.0.

**Query-result reinforcement** in `_search_thread_boosted()` after returning results: reinforce pairs of (query-matched entries, returned entries). Weight 0.5x per search event (many searches per colony, don't let search volume dominate).

**Decay** in the maintenance loop alongside stale_sweep: apply gamma=0.995/day (half-life ~138 days, 4x slower than knowledge confidence because structural relationships persist longer). Prune pairs with weight < 0.1.

**Files touched:**
- `surface/projections.py` -- CooccurrenceEntry dataclass, cooccurrence_weights dict, handler
- `surface/colony_manager.py` -- result-result reinforcement in confidence update hook
- `surface/knowledge_catalog.py` -- query-result reinforcement after search (lightweight, fire-and-forget pattern)
- `surface/maintenance.py` -- co-occurrence decay pass in maintenance loop

### Track A acceptance criteria

1. Colony completes -> transcript harvest runs -> extracts bug/decision/convention/learning entries that the structured extractor missed (verify with a colony that has a tool-call failure + fix sequence)
2. Two concurrent colonies on related tasks -> inline dedup prevents near-duplicate entries (verify with cosine > 0.92 check)
3. Search returns semantically-weak top result -> prediction_error_count incremented on the entry's projection
4. Entry not observed for 180+ days -> gamma_eff capped, alpha does not collapse below ~18 (for alpha=500)
5. Entry classified as `permanent` -> gamma_eff = 1.0, no decay applied
6. Successful colony -> co-occurrence weights reinforced for all accessed entry pairs
7. Maintenance loop -> co-occurrence weights decayed, pairs below 0.1 pruned
8. pytest clean, pyright clean

### Track A files (complete list)

| File | Changes |
|------|---------|
| `surface/colony_manager.py` | Hook dispatcher position 4.5, transcript harvest trigger, inline dedup check, co-occurrence reinforcement in confidence hook, max_elapsed_days cap |
| `surface/memory_extractor.py` | `build_harvest_prompt()`, `parse_harvest_response()`, decay_class in extraction prompt |
| `surface/knowledge_catalog.py` | Prediction error detection after ranking, query-result co-occurrence reinforcement |
| `surface/maintenance.py` | Prediction error in stale_sweep criteria, co-occurrence decay pass |
| `surface/projections.py` | CooccurrenceEntry, cooccurrence_weights dict, harvest tracking suffix |
| `surface/knowledge_constants.py` | GAMMA_RATES, MAX_ELAPSED_DAYS |
| `surface/queen_thread.py` | max_elapsed_days cap in archival decay |
| `core/types.py` | DecayClass StrEnum, decay_class field on MemoryEntry |

---

## Track B: Security + Self-Guiding API Surfaces

Credential scanning (moved from Track A per orchestrator feedback -- it's a security adapter, not knowledge-pipeline logic) plus the full StructuredError wiring, MCP resources/prompts, and AG-UI event promotions.

### B1. Credential scanning via detect-secrets

Create `surface/credential_scan.py` (~180 LOC) wrapping detect-secrets with the dual-config strategy for mixed prose-and-code content.

**Implementation constraints:**
- detect-secrets has NO string-scanning API. All content must be written to temp files via `SecretsCollection.scan_file()`.
- `transient_settings` modifies global state and is NOT thread-safe. Use multiprocessing for parallel scans, never threading.
- PEM keys detected by header line only -- multi-line redaction requires custom post-processing.
- `PotentialSecret.secret_value` is populated during live scans (not from serialized baselines), enabling character-position recovery via `line.find(secret.secret_value)`.

**Dual-config approach:** Shannon entropy for English prose (3.5-4.5 bits) overlaps the Base64 threshold (4.5), causing massive false positives on prose. Split content on code-fence markers. Apply CODE_CONFIG (includes Base64HighEntropyString + HexHighEntropyString) to code blocks. Apply PROSE_CONFIG (regex-only, no entropy) to prose. First pass scans full content with PROSE_CONFIG to catch structured secrets spanning code fence boundaries. Second pass scans code blocks with CODE_CONFIG for high-entropy tokens.

**Integration into extraction pipeline:** Add as 5th axis in `scan_entry()` in `memory_scanner.py` (Knowledge Pipeline Reference Section 2.7). Any finding adds +2.0 to composite score (guarantees "high" tier = rejected). The credential scan runs on the same content field that axes 1-4 scan.

**Dependency:** Add `detect-secrets>=1.5,<2.0` to pyproject.toml. Migration path if maintenance stalls: `bc-detect-secrets` (Bridgecrew fork, drop-in replacement) or standalone scanner using Secrets Patterns DB regex patterns.

### B2. Credential redaction on transcript exports

Higher priority than the extraction-pipeline scan because transcript endpoints are the active credential exposure surface. The extractor only sees compressed summaries, but the A2A `/tasks/{id}/result` and REST `/colonies/{id}/transcript` endpoints return full transcripts with tool outputs.

Add `redact_credentials(text: str) -> tuple[str, int]` to `credential_scan.py`. Sort findings by line number descending for safe replacement. Replace secret values with `[REDACTED:{finding_type}]`.

Wire into:
- `routes/a2a.py` `get_task_result()` -- redact transcript text before returning
- `routes/colony_io.py` transcript/artifact endpoints -- redact before returning
- `surface/transcript_view.py` (new, see C8) -- redact in the canonical builder

### B3. Retroactive credential sweep maintenance handler

New `service:consolidation:credential_sweep` registered in app.py (Knowledge Pipeline Reference Section 6.6 pattern). Track `last_scanned_pattern_version: int` per entry in projections. When new detect-secrets plugins are enabled, bump version and re-scan entries below current version. At 2,000 entries, estimated 10-30 seconds using multiprocessing.

### B4. Wire StructuredError across all 5 surfaces

The API Surface Integration Reference Section 6.2 inventories 35+ error paths. The KNOWN_ERRORS dict in `structured_error.py` (from Wave 32.5) covers 17. Extend to all 35+ and wire every error return/response.

**MCP tools:** Replace `return {"error": "..."}` with `return to_mcp_tool_error(KNOWN_ERRORS["ERROR_CODE"])`. Puts prose in `content[].text` (LLM sees this) AND structured data in `structuredContent` (programmatic consumers parse this). MCP has two distinct error channels -- StructuredError must exist in both.

**A2A routes:** Replace `JSONResponse({"error": "..."}, status_code=N)` with the `to_http_error()` mapper.

**WebSocket commands:** Replace `{"error": str}` frames with `to_ws_error()` frames.

**REST routes + AG-UI endpoint:** Same pattern as A2A.

### B5. MCP resources for knowledge catalog and workflow state

Five projection-backed resources using URI convention from API Surface Reference Section 8.4:

```
formicos://knowledge{?workspace,domain,min_confidence,limit}
formicos://knowledge/{entry_id}
formicos://threads/{workspace_id}
formicos://threads/{workspace_id}/{thread_id}
formicos://colonies/{colony_id}
```

Mutating tools that change knowledge, thread, or colony state emit `ResourceUpdatedNotification` for affected URIs. Notification does not include content -- clients issue `resources/read` to fetch updated data.

ResourcesAsTools transform (registered in Wave 32.5) automatically exposes these as tools for Cursor/Windsurf.

### B6. MCP prompts for structured interaction

```python
@mcp.prompt("knowledge-query")   # domain + question -> relevant entries + question
@mcp.prompt("plan-task")         # goal + workspace -> threads + templates
```

PromptsAsTools transform (registered in Wave 32.5) exposes as tools for clients that don't support prompts natively.

### B7. Extend _next_actions to all mutating MCP tools + A2A status

Wave 32.5 established the convention on spawn_colony. Apply to all 11 mutating tools with tool-specific next actions and context IDs.

Add `next_actions` to A2A status envelope: `["poll", "attach", "cancel"]` for running tasks, `["result"]` for completed.

### B8. AG-UI event promotions (4 remaining)

Wave 32.5 established APPROVAL_NEEDED pattern. Promote 4 more from CUSTOM passthrough to dedicated event types with structured payloads:

- `MemoryEntryCreated` -> `KNOWLEDGE_EXTRACTED` (entry_id, entry_type, domains, scan_status)
- `MemoryConfidenceUpdated` -> `CONFIDENCE_UPDATED` (entry_id, old/new confidence, reason)
- `KnowledgeAccessRecorded` -> `KNOWLEDGE_ACCESSED` (entry_id, access_mode, colony_id)
- `WorkflowStepCompleted` -> `STEP_COMPLETED` (step_id, status, next_pending_step)

### B9. Dynamic Agent Card with live state

Enrich `/.well-known/agent.json` with computed fields: knowledge_domains with entry counts and average confidence, active thread count, total knowledge entries, hardware profile, and federation section (enabled, peer count, trust scores).

### Track B acceptance criteria

1. Knowledge entry with embedded API key (`sk-proj-test123`) -> scan_status="high", status="rejected"
2. A2A `/tasks/{id}/result` transcript -> credentials redacted as `[REDACTED:OpenAI API Key]`
3. `query_service("credential_sweep")` -> newly-detected entries get rejected
4. MCP tool with bad input -> response includes error_code, recovery_hint, suggested_action in BOTH text content AND structuredContent
5. `formicos://knowledge` MCP resource returns entries. Subscription notification fires after colony extracts knowledge.
6. All 11 mutating MCP tools return `_next_actions` and `_context`
7. MemoryEntryCreated emits KNOWLEDGE_EXTRACTED (not generic CUSTOM) in AG-UI stream
8. Agent Card includes knowledge_domains with entry counts
9. pytest clean, pyright clean

### Track B files (complete list)

| File | Changes |
|------|---------|
| `surface/credential_scan.py` | NEW (~180 LOC): dual-config scanner, redaction function |
| `surface/memory_scanner.py` | 5th axis wiring |
| `surface/structured_error.py` | Extend KNOWN_ERRORS to 35+ entries |
| `surface/mcp_server.py` | StructuredError on all tools, resources, prompts, _next_actions on mutating tools, ResourceUpdatedNotification |
| `surface/routes/a2a.py` | StructuredError wiring, next_actions on status, credential redaction on result |
| `surface/routes/knowledge_api.py` | StructuredError wiring |
| `surface/routes/api.py` | StructuredError wiring |
| `surface/routes/colony_io.py` | StructuredError wiring, credential redaction on transcript |
| `surface/routes/protocols.py` | Dynamic Agent Card |
| `surface/ws_handler.py` | StructuredError wiring |
| `surface/commands.py` | StructuredError wiring |
| `surface/event_translator.py` | 4 AG-UI event promotions |
| `surface/agui_endpoint.py` | StructuredError on error responses |
| `surface/maintenance.py` | credential_sweep handler |
| `surface/app.py` | Register credential_sweep |
| `pyproject.toml` | Add detect-secrets>=1.5,<2.0 |

---

## Track C: Computational CRDTs + Federation

The research proved G-Counters are incompatible with gamma-decay. The replacement -- Computational CRDTs (raw observation counts as G-Counters + LWW timestamps + query-time decay) -- uses only proven CRDT primitives (Riak, Redis, Cassandra, Automerge). This track builds the data model, CRDT primitives, trust system, conflict resolution, federation protocol, and the MemoryEntryMerged event.

**Requires ADR-042 (event union expansion) before implementation begins.**

### C1. CRDT primitives (~300 LOC)

Create `core/crdt.py` with three primitive types. Design references: python3-crdt and ericmoritz/crdt (both abandoned, used as patterns only, not dependencies).

```python
@dataclass
class GCounter:
    """Grow-only counter. Per-node int values. Merge = pairwise max."""
    counts: dict[str, int]  # node_id -> value (integers, not floats)
    def increment(self, node_id: str, delta: int = 1) -> None: ...
    def merge(self, other: GCounter) -> GCounter: ...
    def value(self) -> int: ...  # sum of all node values

@dataclass
class LWWRegister:
    """Last-Writer-Wins Register. Timestamp from event timestamps, not wall clock."""
    value: Any
    timestamp: float  # epoch seconds
    node_id: str
    def assign(self, value: Any, timestamp: float, node_id: str) -> None: ...
    def merge(self, other: LWWRegister) -> LWWRegister: ...

@dataclass
class GSet:
    """Grow-only set. Merge = union."""
    elements: set[str]
    def add(self, element: str) -> None: ...
    def merge(self, other: GSet) -> GSet: ...
```

**Use integers for G-Counter observation counts.** The prior (5.0) and decay are applied at query time, not stored in the CRDT. This eliminates all floating-point precision concerns in the merge operation.

### C2. ObservationCRDT composite type

The Computational CRDT pattern (Navalho, Duarte, Preguica, PaPoC 2015): separate monotonic facts from derived computation.

```python
@dataclass
class ObservationCRDT:
    successes: GCounter         # positive observations per instance
    failures: GCounter          # negative observations per instance
    last_obs_ts: dict[str, LWWRegister]  # per-instance last observation time
    archived_by: GSet           # instance_ids that archived this entry
    content: LWWRegister        # latest content formulation
    entry_type: LWWRegister     # skill/experience/pattern
    domains: GSet               # domain tags (grow-only)
    decay_class: LWWRegister    # ephemeral/stable/permanent

    def merge(self, other: ObservationCRDT) -> ObservationCRDT:
        """All components merge independently using their own semantics."""
        ...

    def query_alpha(self, now: float) -> float:
        """Compute effective alpha at query time with per-instance decay."""
        gamma = GAMMA_RATES[self.decay_class.value]
        alpha = PRIOR_ALPHA
        for inst_id, count in self.successes.counts.items():
            ts = self.last_obs_ts[inst_id].timestamp if inst_id in self.last_obs_ts else now
            elapsed = min((now - ts) / 86400.0, MAX_ELAPSED_DAYS)
            alpha += (gamma ** elapsed) * count
        return max(alpha, 1.0)
```

**Archival composes correctly.** When Instance A archives, it adds its ID to `archived_by` GSet (monotonic, federates via union). At query time, A's observations are decayed from archive timestamp. B's unarchived observations use normal `last_obs_ts`. The archival decision is local policy applied at query time -- never corrupts shared CRDT state.

### C3. CRDT event types (4 new events, union 48 to 52)

```python
class CRDTCounterIncremented(EventEnvelope):
    entry_id: str
    instance_id: str
    field: str  # "successes" or "failures"
    delta: int

class CRDTTimestampUpdated(EventEnvelope):
    entry_id: str
    instance_id: str
    timestamp: float

class CRDTSetElementAdded(EventEnvelope):
    entry_id: str
    field: str  # "domains" or "archived_by"
    element: str

class CRDTRegisterAssigned(EventEnvelope):
    entry_id: str
    field: str  # "content", "entry_type", "decay_class"
    value: str
    timestamp: float
    instance_id: str
```

Projection handlers rebuild ObservationCRDT state from event replay. Foreign events are appended to the local event store first, then applied through the standard `projections.apply()` path (Knowledge Pipeline Reference Section 7.2).

### C4. MemoryEntryMerged event (1 new event, union 52 to 53)

Dual-purpose: emitted by the dedup handler AND by the federation conflict resolver. This replaces the current pattern where dedup emits `MemoryEntryStatusChanged(new_status="rejected")` which loses merge provenance.

```python
class MemoryEntryMerged(EventEnvelope):
    target_id: str           # surviving entry
    source_id: str           # absorbed entry (will be rejected)
    merged_content: str      # content that won
    merged_domains: list[str]  # unioned domains
    merged_from: list[str]   # provenance chain (source IDs)
    content_strategy: str    # "keep_longer" | "keep_target" | "llm_selected"
    similarity: float        # cosine similarity that triggered the merge
    merge_source: str        # "dedup" | "federation" (distinguishes the two emission paths)
```

**Projection handler:**
1. Update target entry content, domains, merge_count, merged_from
2. Set source entry status to "rejected" with reason=`"merged_into:{target_id}"`
3. Trigger Qdrant re-sync for both entries

**Dedup handler modification:** Replace the current `MemoryEntryStatusChanged(new_status="rejected")` for auto-merges (>= 0.98 similarity) with `MemoryEntryMerged`. For LLM-confirmed merges (0.82-0.98), same replacement. Content strategy: keep_longer (source wins if > 1.2x target length, otherwise target wins, following NeuroStack's heuristic). Domains: union. merged_from: accumulate.

### C5. Vector clocks for causal ordering (~80 LOC)

Create `core/vector_clock.py`. At 2-10 instances: 160-240 bytes per clock, nanosecond comparison, negligible overhead.

```python
@dataclass
class VectorClock:
    clock: dict[str, int]
    def increment(self, instance_id: str) -> VectorClock: ...
    def merge(self, other: VectorClock) -> VectorClock: ...  # pairwise max
    def happens_before(self, other: VectorClock) -> bool: ...
    def is_concurrent(self, other: VectorClock) -> bool: ...
```

### C6. Bayesian trust with conservative estimator (~150 LOC)

Create `surface/trust.py`. Research-driven: 10th percentile instead of Beta mean.

```python
@dataclass
class PeerTrust:
    alpha: float = 1.0
    beta: float = 1.0

    @property
    def score(self) -> float:
        """10th percentile of Beta posterior. Penalizes uncertainty."""
        return scipy.stats.beta.ppf(0.10, self.alpha, self.beta)

    def record_success(self) -> None:
        self.alpha += 1.0

    def record_failure(self) -> None:
        self.beta += 1.0
```

**Trust calibration:** New peers start at BetaTrust(1, 1) = trust_score ~0.0 (10th percentile of uniform). After 10 successes: ~0.79. After 30 successes: ~0.89. Natural probation period.

**Trust decay:** gamma_trust = 0.9995/day (retains 91.4% at 90 days, 83.5% at 180 days). Much slower than knowledge decay.

**Trust discount on foreign knowledge:** Applied at query time via the ObservationCRDT, not stored in the CRDT state. The discount factor (`trust_score * 0.9^hop`) scales the effective contribution of foreign observations in `query_alpha()`.

### C7. Conflict resolution with Pareto dominance + adaptive threshold (~200 LOC)

Create `surface/conflict_resolution.py`.

**Phase 1: Pareto dominance.** If one entry dominates on 2+ of 3 criteria (evidence, recency, provenance) with substantial margins (1.5x), it wins without consulting the threshold. Catches obvious cases where a weak-but-fresh entry would otherwise tie a strong-but-old entry.

**Phase 2: Composite score with adaptive threshold.** Weights: 0.6 evidence, 0.2 recency, 0.2 provenance. Threshold: `0.05 + 2.0 / avg(evidence_A, evidence_B)` -- wide when both entries are uncertain, narrow when both are strong.

**Phase 3: Keep both as competing hypotheses.** Higher-scoring entry is primary. Lower-scoring is linked with metadata indicating the conflict. Operator sees both. Programmatic consumers get both with scores.

### C8. Federation protocol + selective replication (~400 LOC)

Create `surface/federation.py` and `adapters/federation_transport.py`.

**Peer connection manager:**
```python
@dataclass
class PeerConnection:
    instance_id: str
    endpoint: str
    trust: PeerTrust
    replication_filter: ReplicationFilter
    last_sync_clock: VectorClock

class ReplicationFilter(BaseModel):
    domain_allowlist: list[str]
    min_confidence: float
    entry_types: list[str]
    exclude_thread_ids: list[str]  # privacy boundary
```

**Push/pull replication** (CouchDB pattern): scan local CRDT events since peer's last_sync_clock, apply ReplicationFilter, batch into FederatedEvent envelopes, send via A2A DataPart. Receiving instance verifies causal ordering, applies CRDT merge, emits local events. Cycle prevention: never re-replicate events from own instance_id.

**merged_from across federation:** Entry AB (merged on Instance 1) syncs to Instance 2 with `merged_from: [A, B]`. Instance 2 does NOT auto-apply the merge. Its own dedup handler discovers the overlap and makes an independent decision. merged_from is a hint (higher confidence in merge decision), not a mandate.

**Validation feedback:** When foreign knowledge is used in a colony, send `ValidationFeedback` to originating peer. Success -> `peer_trust.record_success()`. Failure -> `peer_trust.record_failure()`. Closes the trust loop.

### C9. PROV-JSONLD Lite schema + ColonyTranscriptView

**PROV-JSONLD Lite:** Plain JSON using PROV field names with a static `@context` reference. Zero runtime dependencies beyond Pydantic. In `core/types.py`:

```python
class ProvenanceChain(BaseModel):
    generated_by: str        # thread_id + step
    attributed_to: str       # instance_id or colony_id
    derived_from: list[str]  # source entry IDs
    generated_at: str        # ISO timestamp

class KnowledgeExchangeEntry(BaseModel):
    entry_id: str
    content: str
    entry_type: str
    polarity: str
    domains: list[str]
    observation_crdt: dict[str, Any]  # serialized ObservationCRDT
    provenance: ProvenanceChain
    exchange_hop: int = 0
    decay_class: str = "ephemeral"
```

Static context file at `docs/schemas/formicos-prov-context.jsonld`.

**ColonyTranscriptView:** Canonical transcript schema for export/exchange:

```python
class ColonyTranscriptView(BaseModel):
    colony_id: str
    thread_id: str
    workspace_id: str
    task: str
    strategy: str
    caste: str
    rounds: list[RoundView]
    artifacts: list[ArtifactView]
    knowledge_used: list[str]
    knowledge_produced: list[str]
    stats: ColonyStats
```

Adapters: `transcript_to_a2a_artifact()`, `transcript_to_mcp_resource()`. Credential redaction (B2) runs in the builder.

### Track C acceptance criteria

1. Two ObservationCRDTs with different observation counts -> merge -> query_alpha() produces correct decayed value at given timestamp
2. G-Counter merge is pairwise max (monotonic, commutative, associative, idempotent) -- property-based test
3. ObservationCRDT query_alpha() with decay_class="permanent" returns sum of counts + prior (no decay)
4. MemoryEntryMerged event -> target entry has unioned domains + merged_from provenance, source entry rejected
5. Dedup handler emits MemoryEntryMerged (not MemoryEntryStatusChanged) for auto-merges
6. PeerTrust with 10 successes -> score ~0.79 (10th percentile, NOT mean 0.917)
7. Conflict resolution: entry with 90 evidence + 180 days age vs entry with 6 evidence + 1 day age -> Pareto dominance resolves (evidence + provenance dominate)
8. Federation round-trip with mock transport: Instance A creates entry, replicates to B, B uses in colony, sends validation feedback to A, A's trust updated
9. Replay of CRDT events produces identical ObservationCRDT state
10. pytest clean, pyright clean, lint_imports clean (CRDT types in core/, no backward imports)

### Track C files (complete list)

| File | Changes |
|------|---------|
| `core/crdt.py` | NEW (~300 LOC): GCounter, LWWRegister, GSet, ObservationCRDT |
| `core/vector_clock.py` | NEW (~80 LOC) |
| `core/types.py` | ProvenanceChain, KnowledgeExchangeEntry, PeerConnection, ReplicationFilter, ValidationFeedback, Resolution enum, BetaTrust |
| `core/events.py` | 5 new event types (4 CRDT + MemoryEntryMerged) |
| `surface/trust.py` | NEW (~150 LOC): PeerTrust, discount functions |
| `surface/conflict_resolution.py` | NEW (~200 LOC): Pareto + adaptive threshold |
| `surface/federation.py` | NEW (~400 LOC): peer manager, push/pull replication, validation feedback |
| `surface/transcript_view.py` | NEW (~200 LOC): ColonyTranscriptView + adapters |
| `surface/projections.py` | CRDT state projection handlers, ObservationCRDT rebuild |
| `surface/maintenance.py` | Dedup handler -> emit MemoryEntryMerged instead of StatusChanged |
| `adapters/federation_transport.py` | NEW (~100 LOC): A2A DataPart transport |
| `docs/schemas/formicos-prov-context.jsonld` | Static JSON-LD context file |
| `docs/decisions/042-event-union-expansion.md` | ADR (written by orchestrator before dispatch) |

---

## Sequencing

**Track A and Track B can start in parallel immediately.** Track A touches knowledge pipeline internals. Track B touches API surfaces and security adapters. File overlap is minimal: both touch `maintenance.py` (A: co-occurrence decay + prediction error in stale_sweep; B: credential_sweep handler) but different functions.

**Track C has an internal dependency chain:** C1 (CRDT primitives) before C2 (ObservationCRDT) before C6-C8 (trust, conflict, federation). C3 (CRDT events), C4 (merge event), C5 (vector clocks) are independent of C1-C2 and can parallelize.

**Track C does NOT block on Track A or B.** CRDT/federation targets `core/` and new `surface/` files. API surface wiring targets existing `surface/routes/` and `surface/mcp_server.py`.

**Recommended dispatch:**

Team 1 (Track A): 2-3 sessions. Knowledge pipeline intelligence. Can split subagents: one for transcript harvest (A1) + inline dedup (A2), one for prediction errors (A3) + gamma hardening (A4) + co-occurrence collection (A5).

Team 2 (Track B): 2-3 sessions. Can split subagents: one for credential scanning (B1-B3), one for StructuredError wiring (B4), one for MCP resources/prompts + AG-UI + Agent Card (B5-B9).

Team 3 (Track C): 3-4 sessions. Internal sequencing: C1+C3+C4+C5 parallel first, then C2, then C6+C7+C8 parallel, then C9. Can split subagents: one for CRDT primitives + events + vector clocks (C1-C5), one for trust + conflict + federation (C6-C8), one for schemas + transcript view (C9).

**Integration pass** after all three land: verify credential redaction on A2A transcript export, verify StructuredError consistent across all surfaces, verify CRDT merge produces correct query-time alpha/beta, verify federation round-trip between two mock instances, verify prediction error counters populate from real searches, verify co-occurrence weights reinforce after colony completion.

---

## What Wave 33 Does NOT Include

- **No co-occurrence scoring integration.** Data collection only. Scoring activation is Wave 34 with proper weight rebalancing ADR.
- **No multi-hop federation.** Two-instance only. Deeply nested chains have no production precedent.
- **No tiered retrieval.** Title+summary cheap tier is Wave 34 (depends on co-occurrence data and prediction error signals being available).
- **No budget-aware context assembly.** Wave 34 (pairs with tiered retrieval).
- **No mastery-restoration bonus.** Open research question. Evaluate decay classes empirically first.
- **No TRAVOS trust model.** Simple Beta with 10th percentile is sufficient at 2-10 peers.
- **No token-level AG-UI streaming.** Still summary-at-turn-end (ADR-035).
- **No full PROV-JSONLD processing.** Lite approach only. No rdflib.
- **No automatic decay_class on existing entries.** New entries classified by extractor. Existing default to ephemeral.
- **No entity sub-types within skill/experience.** Wave 34 taxonomy enrichment.
- **No composite formula weight changes.** Weights remain at ADR-041 D3 values (0.40/0.25/0.15/0.12/0.08).

---

## ADR-042 Outline (orchestrator writes before dispatch)

**Title:** Event Union Expansion 48 to 53 -- CRDT Operations and Merge Audit

**D1:** 4 CRDT event types (CRDTCounterIncremented, CRDTTimestampUpdated, CRDTSetElementAdded, CRDTRegisterAssigned). Rationale: federation requires CRDT operations as first-class events for replay determinism and selective replication.

**D2:** MemoryEntryMerged event with dual-purpose semantics. Emitted by dedup handler (merge_source="dedup") and federation conflict resolver (merge_source="federation"). Captures target, source, merged content, unioned domains, merged_from provenance, content selection strategy, and similarity score. Replaces the current pattern of rejecting the lower-confidence duplicate via MemoryEntryStatusChanged (which loses merge provenance).

**D3:** The 48-type closed union constraint (from CLAUDE.md) is relaxed for architectural expansion. New constraint: event types require ADR approval. The union is no longer numerically capped.

## ADR-043 Outline (orchestrator writes before dispatch)

**Title:** Co-occurrence Data Model -- Collection Infrastructure and Deferred Scoring

**D1:** Co-occurrence weights collected in Wave 33 via result-result reinforcement (colony completion) and query-result reinforcement (search time). Decay at gamma=0.995/day in maintenance loop.

**D2:** Scoring integration (adding co-occurrence as a ~0.05 weight signal in `_composite_key()`) deferred to Wave 34. The composite weights remain at ADR-041 D3 values (0.40/0.25/0.15/0.12/0.08) throughout Wave 33. Wave 34 will rebalance with a dedicated ADR.

**D3:** Data structure: sparse dict on ProjectionStore keyed by canonically-ordered entry ID pairs. Ephemeral (rebuilt from reinforcement events or recomputed from colony access traces on replay).

---

## Smoke Test (Post-Integration)

1. Create workspace, thread, 3 workflow steps. Run colonies. Verify step continuation still works (Wave 31 regression check).
2. Colony with tool-call failure followed by fix -> transcript harvest extracts bug-type entry with root cause. Structured extraction does NOT capture it (only sees compressed summary).
3. Two colonies on related tasks complete within seconds -> inline dedup prevents near-duplicate entries.
4. Search returns semantically-weak top result -> entry's prediction_error_count incremented.
5. Entry with decay_class="permanent" -> no confidence decay after 30 days.
6. Entry with decay_class="ephemeral" not observed for 180 days -> alpha capped at ~18 (not collapsed to ~5).
7. Knowledge entry with embedded API key -> scan_status="high", status="rejected".
8. A2A `/tasks/{id}/result` -> credentials in tool outputs redacted as `[REDACTED:type]`.
9. MCP tool with bad workspace_id -> response includes WORKSPACE_NOT_FOUND error_code, "Check workspace ID with list_workspaces" recovery_hint, list_workspaces suggested_action.
10. `formicos://knowledge` MCP resource -> returns entries. Subscribe -> notification fires after colony extracts knowledge.
11. Agent Card at `/.well-known/agent.json` -> includes knowledge_domains with counts + federation section.
12. Successful colony -> co-occurrence weights reinforced for accessed entry pairs. Maintenance loop -> weights decayed.
13. Two ObservationCRDTs -> merge -> query_alpha() correct. G-Counter property tests pass.
14. PeerTrust(11, 1).score -> ~0.79 (10th percentile, not 0.917 mean).
15. Contradictory entries -> Pareto dominance resolves obvious case. Adaptive threshold handles close case.
16. Federation round-trip (mock transport): A creates entry -> replicates to B -> B uses in colony -> feedback to A -> A's trust updated.
17. Dedup auto-merge (>= 0.98 similarity) -> emits MemoryEntryMerged (not MemoryEntryStatusChanged) with unioned domains and merged_from.
18. Full replay of all event types including new CRDT events -> projections identical.
19. `pytest` all pass. `pyright src/` 0 errors. `lint_imports.py` 0 violations.

---

## Priority Stack (if scope must be cut)

| Priority | Item | Track | Rationale |
|----------|------|-------|-----------|
| 1 | B2: Transcript credential redaction | B | Active security exposure on public API endpoints |
| 2 | B1: detect-secrets in extraction pipeline | B | Prevents credentials entering knowledge store |
| 3 | B4: StructuredError wiring | B | Foundation exists from 32.5, wiring is mechanical, every consumer benefits |
| 4 | C1+C2: CRDT primitives + ObservationCRDT | C | Data model must be right before any federation |
| 5 | A1: Transcript harvest | A | Closes the biggest extraction quality gap |
| 6 | A4: Gamma hardening (cap + decay classes) | A | Research-identified edge cases |
| 7 | C4: MemoryEntryMerged event + dedup modification | C | Merge provenance needed for federation quality |
| 8 | B5: MCP resources | B | Zero-protocol-extension win, transforms already registered |
| 9 | C6+C7: Trust + conflict resolution | C | Federation quality depends on these |
| 10 | C8: Federation protocol | C | Headline capability, meaningless without C1-C7 |
| 11 | A2: Inline dedup | A | Prevents 24-hour duplicate window |
| 12 | A3: Prediction error counters | A | Improves stale_sweep accuracy |
| 13 | B8: AG-UI event promotions | B | Observability for external consumers |
| 14 | A5: Co-occurrence data collection | A | Infrastructure for Wave 34 scoring |
| 15 | B7: _next_actions on all tools | B | Ergonomic, not blocking |
| 16 | C9: PROV schema + transcript view | C | Foundation for future exchange |
| 17 | B3: Credential sweep handler | B | Retroactive scanning, can land anytime |
| 18 | C5: Vector clocks | C | Needed for federation ordering but simple |
| 19 | C3: CRDT event types | C | Needed for federation replay |
| 20 | B6+B9: MCP prompts + Agent Card | B | Nice-to-have |
