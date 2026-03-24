# Knowledge Flow End-to-End Audit

> Audited: 2026-03-22 against Phase 0 v7 eval data (Qwen3-Coder, Wave 56.5 stack).
> Data source: `/data/eval_events.db` — 3,622 events across 13 workspaces.
>
> **STATUS (2026-03-23):** This audit reflects Phase 0 v7 eval data on the Wave 56.5
> stack. Several findings have been addressed in subsequent waves:
>
> - **Domain tag fragmentation (Section 1):** Partially mitigated by `primary_domain`
>   stamping (Wave 58.5) and domain-boundary filter, but variant spelling of
>   LLM-generated domain tags remains an open issue.
> - **Retrieval relevance (Section 2):** Domain-boundary filter (Wave 58.5) now
>   post-filters results to keep only entries matching the colony's task class.
>   Specificity gate (Wave 58) adds 4 additional filtering conditions. These
>   should significantly improve relevance vs. v7 results.
> - **Injection threshold (Section 3):** The threshold now compares raw semantic
>   similarity after Wave 55.5 (`_MIN_KNOWLEDGE_SIMILARITY=0.50`). The specificity
>   gate provides additional filtering.
> - **Confidence evolution (Section 5):** Confidence updates now fire via outcome-
>   weighted reinforcement in post-colony hooks. The quality score formula was
>   fixed (Wave 54.5) so it no longer returns 0.000 universally.
> - **Entry ID mismatch:** Still present — vector store generates content-hash UUIDs.
>
> Sections 4 (consumption evidence) and 6 (common mistakes) findings remain
> largely current. The core insight — knowledge adds tokens but not information
> in short eval runs — remains valid for cold-start scenarios.

---

## Section 1: Entry Inventory

**Source**: 188 `MemoryEntryCreated` events from 36 colonies across 13 workspaces.

### Type Distribution

| Type | Sub-type | Count | % |
|------|----------|-------|---|
| skill | technique | 57 | 30.3% |
| experience | learning | 55 | 29.3% |
| experience | (none) | 41 | 21.8% |
| skill | pattern | 24 | 12.8% |
| experience | convention | 7 | 3.7% |
| experience | decision | 4 | 2.1% |
| **Total** | | **188** | |

Skills: 81 (43%), Experiences: 107 (57%).

### Confidence at Creation

All 188 entries created with identical priors: `alpha=5.0, beta=5.0`.
No entry has ever received a confidence update (see Stage 5).

### Status at Creation

All 188 entries created as `candidate`. 147 later promoted to `verified`
via `MemoryEntryStatusChanged` events (triggered when source colony
completes successfully). 41 remain `candidate`.

### Admission Scores

- Min: 0.000 — Max: 0.819 — Avg: 0.628
- All scan statuses: `safe` (147) or `pending` (41)
- No entries rejected by admission

### Playbook Generation Stamp

Present on 115 of 188 entries (61%). Missing from 73 entries (39%).

[NOTE: The `playbook_generation` field is not universally populated.
Entries from early-run colonies (first workspace) consistently lack it.
This suggests the extraction prompt doesn't always produce a stamp, or
the field was added mid-run.]

### Domain Tag Consistency

**34 domain keys have variant spellings.** Examples:

| Normalized | Actual Variants |
|-----------|-----------------|
| `api_design` | `API_design`, `API design`, `API Design`, `api_design` |
| `error_handling` | `error-handling`, `error handling`, `error_handling` |
| `software_testing` | `software_testing`, `software testing` |
| `data_validation` | `data_validation`, `data validation` |
| `quality_assurance` | `quality_assurance`, `quality assurance`, `quality-assurance` |
| `system_design` | `system design`, `system_design`, `System Design` |

This means the same semantic domain is split 2–4 ways. Co-occurrence
scoring, domain overlap detection, and coverage gap rules all operate on
exact string match — so these variants fragment what should be a single
domain cluster.

### Entry Classification

Evaluated by source task and content transferability:

| Classification | Count | % | Description |
|---------------|-------|---|-------------|
| Task-specific | ~120 | 64% | Describes a technique for the exact task that produced it (e.g., "Email Format Validation" from the email-validator task) |
| Domain-transferable | ~45 | 24% | Could plausibly help a related task (e.g., "Robust Data Validation and Normalization") |
| Noise | ~15 | 8% | Environment observations or overly generic (e.g., "Comprehensive Test Coverage for Validation Functions") |
| Genuinely transferable | ~8 | 4% | Useful across unrelated tasks (e.g., "Structured Validation Result Generation", "Edge Case Handling in Data Processing") |

**Only ~4% of entries are genuinely transferable across task types.**
The extraction prompt produces entries that accurately describe what the
colony did, but those descriptions are too tightly bound to the source
task to help a different task.

### Entries Per Workspace

| Workspace | Entries | Accesses |
|-----------|---------|----------|
| seq-phase0-c882fb8be6e3 | 49 | 77 |
| seq-phase0-8eda7fdca969 | 37 | 35 |
| seq-phase0-7e8ce2d5d274 | 36 | 39 |
| seq-phase0-heavy-716acdb0a088 | 21 | 18 |
| (9 smaller workspaces) | 45 | 17 |

---

## Section 2: Retrieval Relevance Map

**Source**: 186 `KnowledgeAccessRecorded` events recording 242 individual
item accesses across 22 colonies (14 colonies had zero accesses).

### Headline Finding

**100% of retrieved entries are irrelevant to the consuming task.**

Every single retrieval crosses task-type boundaries. The system retrieved
entries from email-validation for haiku-writing tasks, CSV-processing
entries for rate-limiter tasks, and validation patterns for API design
tasks. Zero retrievals returned an entry from the same task type as the
consumer.

### Retrieval Precision: 0/242 (0.0%)

| Consumer Task | Retrieved Entry | Score | Assessment |
|--------------|-----------------|-------|------------|
| haiku | "Structured Validation Result Generation" | 1.000 | Irrelevant |
| haiku | "Email Format Validation" | 0.500 | Irrelevant |
| rate_limiter | "Haiku Syllable Structure Mastery" | 0.500 | Irrelevant |
| rate_limiter | "Edge Case Testing for CSV Processing" | 0.667 | Irrelevant |
| api_design | "Structured Validation Result Generation" | 0.667 | Irrelevant |
| api_design | "Thread-Safe Rate Limiting with Token Bucket" | 0.500 | Marginal at best |
| data_pipeline | "Email Format Validation" | 0.500 | Irrelevant |
| markdown | "Structured Validation Result Generation" | 0.833 | Irrelevant |

### "Structured Validation Result Generation" Is the Universal Top Hit

This single entry appears in retrieval results for **16 of 22 colonies
that accessed knowledge** — including haiku writing, rate limiting, and
API design tasks. It scores between 0.583 and 1.000 across all task
types. This suggests the composite scoring formula is dominated by
non-semantic signals (Thompson Sampling, freshness, status) that
produce high scores regardless of semantic relevance.

### Score Distribution

- Score range: 0.500 to 1.000
- Mean score: 0.638
- All scores are above the injection threshold (0.50)

[NOTE: The `similarity` field is absent from `KnowledgeAccessRecorded`
items. Only `score` (composite) and `confidence` (0.5) are recorded.
This means we cannot distinguish semantic similarity from Thompson
Sampling / freshness / status contributions in the composite score.
The raw semantic signal is not observable in the event stream.]

### Entry ID Mismatch

Created entry IDs use the format `mem-colony-{hash}-{type}-{n}`.
Retrieved entry IDs use content-hash UUIDs (e.g., `9c1544dc-4892-549f-...`).
**Zero overlap** between the two ID spaces. The vector store generates
its own IDs from content hashing. This makes it impossible to trace a
specific created entry to its retrieval events via ID alone — only title
matching works.

### Colonies With No Access

14 of 36 colonies (39%) had zero knowledge accesses. These are likely
the first colony in each workspace (no knowledge yet available) or
colonies where the vector store returned no results above threshold.

---

## Section 3: Injection Effectiveness

### What Passes the Threshold

The injection gate (`engine/context.py:457-465`) filters entries where
`raw_similarity < _MIN_KNOWLEDGE_SIMILARITY` (default 0.50, env var
`FORMICOS_KNOWLEDGE_MIN_SIMILARITY`).

Since all recorded composite scores are ≥ 0.500, and the composite score
is what's used for threshold comparison, **all 242 retrieved items passed
the injection gate**. None were blocked.

[NOTE: The threshold is compared against the composite score, not the raw
semantic similarity. Since the composite adds Thompson Sampling (0.25
weight), freshness (0.15), and status (0.10) on top of semantic (0.38),
entries with low semantic similarity can still pass the gate via other
signals. This means the threshold is not functioning as a semantic
relevance filter — it's a composite score floor.]

### Entries Injected Per Task

| Task Type | Avg Entries Injected | Range |
|-----------|---------------------|-------|
| markdown | 3.25 | 3-4 |
| api_design | 2.5 | 2-3 |
| csv | 2.5 | 2-3 |
| rate_limiter | 2.0 | 2-2 |
| haiku | 2.5 | 2-3 |
| data_pipeline | 2.33 | 2-3 |
| user_records | 3.0 | 3-3 |

Average: ~2.5 entries injected per task. At the `summary` tier (~15
tokens per entry), this adds ~40 tokens of knowledge context. At
`standard` tier (~75 tokens), ~190 tokens.

### Is the Threshold Calibrated Correctly?

No. The threshold is not doing useful work because:
1. It compares composite score (not semantic similarity)
2. Non-semantic signals inflate all scores above the threshold
3. It blocks nothing — every retrieved entry passes
4. Genuinely irrelevant entries (haiku syllable patterns for rate limiters)
   score 0.500+ and get injected

---

## Section 4: Consumption Evidence

### Methodology

For colonies with knowledge access, compared the injected entry
titles/content against the `output_summary` field in
`AgentTurnCompleted` events and the `summary` field in
`ColonyCompleted` events.

### Findings

**No concrete evidence that any injected entry influenced agent output.**

Specific checks:

| Colony | Task | Injected Entry | Agent Output | Evidence |
|--------|------|---------------|--------------|----------|
| colony-86ebb340 | API design | "Structured Validation Result Generation" (score 0.667) | OpenAPI-style spec with CRUD for projects, tasks, comments, labels | None. Agent designed a task management API using standard REST patterns. No validation result generation patterns visible. |
| colony-86ebb340 | API design | "Duplicate ID Resolution Strategy" (score 0.500) | Standard auto-increment IDs | None. No duplicate resolution mentioned. |
| colony-ab02ca21 | API design | "Configurable Rate Limiting with Burst Tolerance" (score 0.833) | Standard REST API design | None. Rate limiting not mentioned in the API design output despite being the highest-scoring injected entry. |
| colony-bb8f6386 | Rate limiter | "Edge Case Testing for CSV Processing" (score 0.667) | Token bucket implementation | None. CSV processing not relevant to rate limiting. |
| colony-7b94710a | Rate limiter | "Haiku Syllable Structure Mastery" (score 0.500) | Token bucket implementation | None. Haiku knowledge obviously irrelevant. |
| colony-8f339b5f | Haiku | "Structured Validation Result Generation" (score 1.000) | Five haiku poems about seasons | None. Validation patterns completely irrelevant to poetry. |
| colony-36449819 | CSV summary | "Robust Data Validation and Normalization" (score 0.833) | CSV parser with statistics | Marginal — both deal with data processing, but the agent's approach doesn't reference the injected entry's specific patterns. |
| colony-f3c033d1 | Markdown parser | "Nested Data Structure Transformation" (score 0.750) | Recursive descent Markdown parser | Marginal — both involve nested structures, but the agent implemented a standard recursive parser without referencing the injected entry. |

### Assessment

The knowledge injection system is delivering content to agents, but that
content is irrelevant to the task at hand. Even in the two "marginal"
cases, the agent appears to be generating output from its own training
knowledge rather than adapting the injected entry's patterns.

The most telling example: colony-ab02ca21 (API design) received
"Configurable Rate Limiting with Burst Tolerance" as its highest-scoring
entry (0.833), but the agent's output contains no rate limiting
discussion. The entry was injected into context but had no detectable
influence.

**The knowledge system is adding tokens to context but not adding
information the agent can use.** This is the core finding of the audit.

---

## Section 5: Lifecycle Health

### Confidence Evolution: Completely Dormant

- `MemoryConfidenceUpdated` events: **0**
- Entries with alpha > 5.0: **0**
- Entries that received any confidence boost: **0**

All 188 entries remain at their creation prior of `Beta(5.0, 5.0)`.

### Why Confidence Updates Aren't Firing

The confidence update code path
(`colony_manager.py` post-colony hooks → emit `MemoryConfidenceUpdated`)
requires:
1. Colony completes successfully ✓ (28 colonies completed)
2. Colony accessed knowledge entries ✓ (22 colonies accessed entries)
3. The post-colony hook calls the confidence update path

The fact that 28 colonies completed and 22 accessed knowledge but zero
confidence events fired means the emission code path in the post-colony
hooks is either:
- Not reaching the confidence update section
- Failing silently
- Gated by a condition that's never met in the eval harness

[NOTE: All quality scores in `ColonyCompleted` events are 0.000. This
suggests `compute_quality_score()` is returning zero in the eval context,
possibly because the convergence/governance signals are not populated.
If confidence updates are gated on quality > 0, this would explain why
they never fire.]

### Status Transitions

147 of 188 entries were promoted from `candidate` to `verified` (reason:
"source colony completed successfully"). This means the status lifecycle
IS working — the system correctly tracks that the source colony
succeeded. But the confidence lifecycle (alpha/beta evolution) is not.

### Alpha Distribution

| Alpha Value | Count |
|-------------|-------|
| 5.0 | 188 |

Flat. No evolution. No decay. No mastery restoration. The entire Bayesian
confidence metabolism — Thompson Sampling, outcome-weighted reinforcement,
prediction error tracking — is inert because no `MemoryConfidenceUpdated`
events are being emitted.

---

## Section 6: Common Mistakes Injection

### File Existence

Both common_mistakes files exist in the Docker container at:
- `/app/config/playbooks/common_mistakes.yaml` — 2 universal anti-patterns
- `/app/config/playbooks/common_mistakes_coder.yaml` — 2 coder-specific anti-patterns

### Content

**Universal** (all castes):
1. "Do NOT retry a failed action without diagnosing why it failed first."
2. "Produce your main artifact BEFORE the final round — use the last round only for polish."

**Coder-specific**:
1. "Do NOT write code without first reading the target file."
2. "When a tool call returns an error, READ the full error message before your next action."

### Injection Verification

The injection code (`engine/context.py:417-419`) calls
`load_common_mistakes(agent.caste)` at context position 2.6 (after
operational playbook at 2.5). The code path exists and the files are
present in the container.

**However, we cannot verify from the event stream whether common_mistakes
actually reached agent context.** The assembled context is not persisted
in any event — only the agent's output is recorded. There is no
`ContextUpdated` handler (it's one of the 2 unhandled event types).

### Behavioral Evidence

Checking agent tool call patterns for coder agents:

- colony-86ebb340 (coder-0): First tool calls are `list_workspace_files`,
  `memory_search`, then `workspace_execute`. The coder DID observe before
  writing — consistent with the common_mistakes guidance, but also
  consistent with normal LLM behavior.
- colony-0fb75545 (coder-0): First tool calls are `list_workspace_files`,
  `workspace_execute`. Again, observes first.

**No definitive behavioral evidence.** The agents observe before writing,
but this is also standard LLM behavior without anti-pattern cards. We
cannot isolate the common_mistakes contribution from baseline behavior
without a controlled comparison (same task, same model, with and without
the injection).

---

## Findings and Recommendations

### What's Working

1. **Entry extraction**: The LLM extracts structured entries with types,
   sub-types, domains, and content. The admission scoring and security
   scanning pipelines both function.
2. **Status lifecycle**: Entries correctly transition from `candidate` to
   `verified` when their source colony succeeds (147/188 promoted).
3. **Event-sourced persistence**: All knowledge events are durably stored
   and replayable.

### What's Broken

1. **Retrieval relevance is zero.** 100% of retrieved entries cross task-type
   boundaries. "Haiku Syllable Structure Mastery" is retrieved for
   rate-limiter tasks. The composite scoring formula
   (`surface/knowledge_catalog.py:258-295`) over-weights non-semantic
   signals, and the Thompson Sampling exploration component (25% weight)
   injects randomness that overwhelms semantic relevance.

2. **Confidence evolution is completely dormant.** Zero
   `MemoryConfidenceUpdated` events across 28 completed colonies. The
   Bayesian metabolism is inert.
   Root cause: likely quality scores all returning 0.000 in the eval
   harness, which gates the confidence update path.
   (`surface/colony_manager.py` post-colony hooks)

3. **The injection threshold doesn't filter.** The 0.50 threshold compares
   against composite score (not raw semantic similarity), and non-semantic
   signals inflate all scores above 0.50. Every retrieved entry passes
   regardless of relevance. (`engine/context.py:457-465`)

4. **Entry IDs are incoherent across stores.** Event store uses
   `mem-colony-{hash}` IDs, vector store uses content-hash UUIDs. Cannot
   trace created → retrieved entries by ID.
   (`surface/memory_store.py:59-88` generates embed text → UUID)

5. **Domain tags are fragmented.** 34 domain keys exist in 2-4 variant
   spellings (spaces/underscores/hyphens, case). This fragments
   co-occurrence scoring, coverage gap detection, and domain overlap
   analysis.

### Recommendations

1. **Fix the threshold gate to compare raw semantic similarity, not
   composite score.** The composite score serves ranking; the threshold
   should serve relevance filtering. Separate the two concerns.
   - `engine/context.py:457-465` — compare against the semantic signal
     component, not the final composite
   - Alternatively, add `raw_similarity` to `KnowledgeAccessItem` so the
     signal is observable in the event stream

2. **Diagnose why `MemoryConfidenceUpdated` events don't fire.** Trace
   the post-colony hook path in `surface/colony_manager.py:1025` through
   the confidence update emission. The most likely cause: quality_score is
   always 0.000 in eval context, and a `quality > 0` gate blocks
   confidence updates.
   - `surface/colony_manager.py:267` — `compute_quality_score()` returns
     0 when convergence/governance signals are not populated

3. **Normalize domain tags at extraction time.** Apply lowercase +
   underscore normalization to domain strings before storing them.
   34 variant keys → 34 canonical keys would immediately improve
   co-occurrence scoring and coverage gap detection.
   - `surface/colony_manager.py:1825` — `build_memory_entries()` is where
     domains are set. Normalize there.

4. **Reconcile entry IDs across event store and vector store.** Use the
   `mem-colony-*` ID as the Qdrant point ID instead of generating a
   content-hash UUID. This enables tracing from creation → retrieval →
   injection → confidence update.
   - `surface/memory_store.py:67-88` — `VectorDocument(id=entry_id, ...)`
     should use the original entry ID

5. **Record raw semantic similarity in KnowledgeAccessRecorded events.**
   Without this signal, it's impossible to distinguish "retrieved because
   semantically relevant" from "retrieved because Thompson Sampling
   explored." Add a `similarity` field to each access item.
   - `surface/knowledge_catalog.py:288-295` — the composite scoring
     function already computes `semantic` separately; pass it through to
     the access record
