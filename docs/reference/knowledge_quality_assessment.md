# Knowledge Quality & Intentionality Assessment

**Date**: 2026-03-21
**Scope**: Phase 0 v3 + v4 knowledge entries, extraction pipeline, retrieval lifecycle
**Source runs**: v3 (`be34e691864f`, Qwen3-30B general), v4 (`a055f566be6e`, Qwen3-Coder-30B)
**Cross-reference**: `docs/waves/wave_55/retrieval_quality_audit.md`

> **STATUS (2026-03-23):** This audit reflects Phase 0 v3/v4 eval data on earlier
> stacks. Several recommendations have been addressed:
>
> - **R1 (Transferability criteria):** Partially addressed — Wave 59 curating
>   extraction shows existing entries to the LLM, enabling REFINE/MERGE/NOOP
>   actions instead of blind CREATE. The extraction prompt now includes existing
>   entries as context for comparison.
> - **R2 (Environment noise filter):** ✅ IMPLEMENTED — `is_environment_noise_text()`
>   now includes "pytest is not installed", "module not found", "pip install",
>   "package not installed", "import error", "no module named" (16 phrases total).
> - **R3 (Usage-based promotion):** Not yet implemented. Promotion still requires
>   source colony completion.
> - **R4 (Content-type signal):** Not directly implemented as a prompt change, but
>   admission scoring includes content-type priors that bias toward high-value types.
> - **R5 (Log entry content in eval):** Addressed in subsequent eval harness updates.
>
> The core insight — "the system extracts what the LLM finds interesting rather than
> what would be useful to future tasks" — remains valid. Wave 59 curation is the
> primary mitigation, enabling refinement of existing entries over blind creation.

---

## Phase 1: What's in the Brain

### v4 Knowledge Pool (27-29 entries from 5 source tasks)

Data reconstructed from retrieval quality audit entry tables and run metadata.
Entries listed below are those surfaced by retrieval for rate-limiter and
data-pipeline tasks, plus inferred entries from extraction counts.

| Source Task | Colony | Extracted | Sample Titles |
|-------------|--------|-----------|---------------|
| email-validator | colony-6bdcf1ef | 6 | "Validate Email Format Using RFC 5322 Basics", "Comprehensive Email Validation with Error Reporting", "Using write_workspace_file Instead of patch_file" |
| json-transformer | colony-e4460188 | 7 | "Group Data by Hierarchical Structure", "Handle Duplicate IDs with Validation", "Sanitize and Normalize Group Keys", "Use Default Dict for Nested Grouping" |
| csv-analyzer | colony-2c5742a4 | 10 | "Validate CSV File Structure Before Processing", "Detect Column Types Dynamically", "Handle Missing Values with Robust Counting", "Compute Summary Statistics Based on Data Type" |
| markdown-parser | colony-09d9bb39 | 6 | "Parse Markdown to AST with Nested Formatting", "Validate and Test Markdown Parsers", "Pytest is not installed in the environment", "Test Runner Fails Due to Missing pytest" |
| haiku-writer | (colony) | 0 | (none extracted) |

**Total**: ~29 entries. All start as `candidate` status with `Beta(5,5)` priors
(confidence 0.50). All classified as `ephemeral` decay class by default.

### v3 Knowledge Pool (smaller: ~24 entries)

v3 general model extracted fewer entries per task (4-7 vs 6-10 for v4).
Same domain distribution. Sample titles from retrieval audit:

- "Test Edge Cases in Data Processing Pipelines" (csv-analyzer)
- "Validate CSV File Structure Before Processing" (csv-analyzer)
- "Test Runner Not Available During Execution" (csv-analyzer)
- "Structure Validation Results with Local Part and Domain" (email-validator)
- "Detect and Resolve Duplicate IDs" (json-transformer)
- "Handle Missing or Invalid Fields Gracefully" (json-transformer)

### Entry Classification

Based on titles and available content fragments, each entry is classified by
transferability:

| Classification | Count (est.) | Examples |
|----------------|-------------|----------|
| **Transferable** | 4-6 | "Handle Missing Values with Robust Counting", "Detect Column Types Dynamically", "Use Default Dict for Nested Grouping", "Handle Duplicate IDs with Validation" |
| **Domain-specific** | 10-14 | "Validate Email Format Using RFC 5322 Basics", "Compute Summary Statistics Based on Data Type", "Parse Markdown to AST with Nested Formatting", "Validate CSV File Structure Before Processing" |
| **Task-specific** | 4-6 | "Comprehensive Email Validation with Error Reporting", "Group Data by Hierarchical Structure", "Sanitize and Normalize Group Keys" |
| **Noise** | 3-5 | "Pytest is not installed in the environment", "Test Runner Fails Due to Missing pytest", "Test Runner Not Available During Execution" |
| **Meta** | 1-2 | "Using write_workspace_file Instead of patch_file", "Extracting Transferable Knowledge from Colony Results" |

**Key finding**: Roughly 15-25% of entries are genuinely transferable.
50-55% are domain-specific (useful for same-kind tasks only). 15-25% are
noise or meta-knowledge about the system itself.

### Environment noise entries that passed gates

Two entries from markdown-parser are pure environment noise:
- "Pytest is not installed in the environment"
- "Test Runner Fails Due to Missing pytest"

These describe sandbox limitations, not transferable knowledge. The
`is_environment_noise_text()` filter catches phrases like "not available in
the current environment" but does NOT catch "is not installed in the
environment" — a near-miss in the noise filter vocabulary.

Similarly from v3: "Test Runner Not Available During Execution" — same
pattern. The noise filter catches "not available" only when combined with
environment/tool context words, but "Test Runner" doesn't match the context
list (`_ENVIRONMENT_NOISE_CONTEXTS = ("workspace", "environment", "git",
"tool", "command", "sandbox")`).

---

## Phase 2: Extraction Prompt Quality

### Main extraction prompt (`memory_extractor.py:55-108`)

**Strengths:**
- Dual extraction (skills + experiences) with distinct schemas
- Failure-path extraction limited to negative experiences only
- `decay_class` classification with clear definitions
- Artifact and contract context provided to the LLM

**Weaknesses:**

1. **No definition of "transferable"**. The prompt says "Extract transferable
   knowledge" and "Be conservative" but never defines what transferable means.
   It does not say "knowledge that would help a DIFFERENT task in a DIFFERENT
   domain" vs "knowledge specific to THIS task." The LLM defaults to
   extracting everything it finds interesting, which produces domain-specific
   and task-specific entries that aren't useful beyond the source task.

2. **No domain vocabulary**. The prompt says `"domains" (list)` but provides
   no guidance on what domains should be. The LLM invents ad-hoc tags per
   task. There is no controlled vocabulary anywhere in the codebase —
   `domains` is `list[str]` with no validation (`core/types.py:399`).
   Domains are unused in retrieval scoring (not in the 6-signal composite)
   and unused in admission scoring (not in the 7-signal admission formula).

3. **No negative examples**. The prompt doesn't say "Do NOT extract entries
   about environment issues, missing tools, or sandbox limitations." The
   `is_environment_noise_text()` filter catches some noise post-hoc, but
   the extraction LLM isn't told to avoid generating it.

4. **No quality criteria for content**. The prompt asks for "actionable
   instruction" (skills) and "1-2 sentences" (experiences) but doesn't
   define what actionable means. Entries like "Validate CSV File Structure
   Before Processing" have titles that sound actionable but content that
   may be task-specific boilerplate.

### Harvest prompt (`memory_extractor.py:225-251`)

**Strengths:**
- Per-turn classification (KEEP/SKIP) is efficient
- Four types (bug, decision, convention, learning) are well-defined

**Weaknesses:**

1. **No transferability filter**. The harvest prompt classifies turns by type
   but doesn't ask whether the knowledge is transferable to other tasks. A
   "bug" about pytest not being installed is classified as KEEP because it's
   a valid bug — but it's not useful knowledge.

2. **Overlap with extraction**. Harvest types `convention` maps to `skill`,
   while `bug/decision/learning` map to `experience`. If both extraction and
   harvest run on the same colony, they can produce duplicate entries about
   the same topic with different framings. The inline dedup (similarity
   threshold 0.82) may or may not catch these.

3. **500-char turn truncation**. Each turn is truncated to 500 chars. For
   turns with tool outputs (code execution results, file contents), the
   most informative content is often beyond 500 chars.

### Quality gate (`colony_manager.py:206-262`)

**Design**: Conjunctive — no single signal alone causes rejection. Four rules:
1. Empty content (<5 chars) — always reject
2. Short (<40 chars) AND generic phrase — reject
3. Short AND weak title (<15 chars) AND no domains — reject
4. Generic phrase AND no domains AND weak title — reject

**Assessment**: The gate is calibrated to minimize false rejections, not to
maximize quality. It catches only the most obviously low-quality entries.

**Gaps the gate misses:**

| Pattern | Example | Why it passes |
|---------|---------|---------------|
| Environment noise with good title | "Pytest is not installed in the environment" (content >40 chars, title >15 chars, has domains) | Content is long enough, title is descriptive, domains present |
| Meta-knowledge about FormicOS | "Using write_workspace_file Instead of patch_file" | Not generic, has content, has title |
| Domain-specific with generic content | "Comprehensive Email Validation with Error Reporting" | Long content, good title |
| Structurally sound but non-transferable | "Validate CSV File Structure Before Processing" | All signals look healthy |

The gate rejects ~5-10% of entries (empty, very short + generic). The
remaining 90-95% pass regardless of transferability. **The gate checks form,
not substance.**

---

## Phase 3: Entry Quality by Source Task

### v4 (Coder model) — 21 entries extracted, 8 tasks

| Source Task | Count | Transferable | Domain-specific | Task-specific | Noise | Meta |
|-------------|-------|-------------|----------------|--------------|-------|------|
| email-validator | 6 | 1 | 3 | 1 | 0 | 1 |
| json-transformer | 7 | 2 | 3 | 2 | 0 | 0 |
| csv-analyzer | 10 | 3 | 5 | 2 | 0 | 0 |
| markdown-parser | 6 | 1 | 2 | 1 | 2 | 0 |
| haiku-writer | 0 | — | — | — | — | — |
| rate-limiter | 4 | ~2 | ~1 | ~1 | 0 | 0 |
| api-design | 8 | ~3 | ~3 | ~2 | 0 | 0 |
| data-pipeline | 6 | ~2 | ~2 | ~1 | ~1 | 0 |
| **Total** | **~47** | **~14 (30%)** | **~19 (40%)** | **~10 (21%)** | **~3 (6%)** | **~1 (2%)** |

*Note: Rate-limiter through data-pipeline counts are estimated from
extraction totals and patterns observed in earlier tasks.*

### v3 (General model) — 9 entries extracted (accumulate arm)

| Source Task | Count | Notes |
|-------------|-------|-------|
| email-validator | 0 | No extraction |
| json-transformer | 0 | No extraction |
| haiku-writer | 0 | No extraction |
| csv-analyzer | 0 | No extraction |
| markdown-parser | 2 | Some extraction |
| rate-limiter | 4 | Heavy extraction |
| api-design | 0 | No extraction |
| data-pipeline | 3 | Some extraction |

The general model is far more conservative (9 vs 21 entries), but the
entries it does extract tend to be higher-signal because the model is
more selective.

### Patterns

1. **Multi-round tasks produce more entries**. csv-analyzer (5 rounds, 10
   entries) vs email-validator (1 round, 6 entries). More rounds = more
   artifacts = more extractable content.

2. **The Coder model over-extracts**. 2.3x more entries than the general
   model, but quality per entry is lower. More entries does not mean more
   signal — it means more noise in the retrieval pool.

3. **Simple tasks produce the most noise**. Markdown-parser produced 2/6
   noise entries (33%). Heavy tasks like rate-limiter produce 0% noise
   because the content is substantive enough to pass all gates.

4. **No task class produces primarily transferable knowledge**. Even
   csv-analyzer (the best producer) has only 3/10 transferable entries.
   The majority of all entries are domain-specific or task-specific.

---

## Phase 4: What's Missing

### Knowledge that SHOULD have been extracted but wasn't

1. **Tool-call sequences (trajectory knowledge)**. Successful colonies
   follow patterns: read → write → test → patch. Failed colonies show
   anti-patterns: write → test → fail → write → test → fail. These
   sequential patterns are highly transferable but never extracted. The
   extraction prompt operates on final output and artifacts, not on the
   tool-call trajectory.

2. **Domain-crossing patterns**. csv-analyzer and data-pipeline both
   involve "parse structured text → validate → aggregate → report." This
   is a transferable workflow pattern, but neither extraction nor harvest
   identifies cross-task structural similarity.

3. **Failure recovery strategies**. When a colony encounters a test
   failure and successfully patches, the recovery strategy (read error →
   diagnose → fix → re-test) is transferable. The extraction prompt
   captures the final state but not the recovery arc.

4. **Tool effectiveness ratings**. "code_execute is productive for
   implementation tasks; read_workspace_file is productive for analysis
   tasks." This is derivable from colony outcomes but never extracted.

5. **Specific code patterns by language**. csv-analyzer could extract
   "use csv.DictReader for column-keyed access" or "handle BOM markers
   with encoding='utf-8-sig'." These are highly specific, highly reusable
   patterns. The extraction prompt's "actionable instruction" guidance
   doesn't push the LLM toward this level of specificity.

### What the retrieval audit proved is missing

For rate-limiter: zero entries about concurrency, threading, token buckets,
or related algorithms. The knowledge pool is structurally incapable of
helping this task because no prior task was in the same domain.

**This is not a retrieval failure — it's a pool composition problem.** The
compounding signal can only work when task sequence contains domain overlap.
In a diverse 8-task sequence, domain overlap is sparse by design.

---

## Phase 5: Embedding Quality

### Qwen3-Embedding-0.6B characteristics

- 1024-dimensional vectors, L2-normalized
- Hybrid search: dense (Qwen3) + BM25 sparse, RRF fusion (k=60)
- Query preprocessing: instruction prefix + `<|endoftext|>` token
- Document preprocessing: `<|endoftext|>` only (no instruction prefix)
- Embedded field: full document `content` only; title/summary stored as
  metadata, not embedded

### Observed similarity scores (from retrieval audit)

| Entry Title | Source | Similarity to rate-limiter task | Relevant? |
|-------------|--------|--------------------------------|-----------|
| Comprehensive Email Validation with Error Reporting | email-validator | **0.6667** | No |
| Extracting Transferable Knowledge from Colony Results | email-validator | 0.5000 | No |
| Validate CSV File Structure Before Processing | csv-analyzer | 0.4103 | No |
| Use Default Dict for Nested Grouping | json-transformer | 0.4103 | No |
| Hierarchical Grouping Improves Data Usability | json-transformer | 0.3409 | No |

| Entry Title | Source | Similarity to data-pipeline task | Relevant? |
|-------------|--------|----------------------------------|-----------|
| Compute Summary Statistics Based on Data Type | csv-analyzer | **0.7000** | Yes |
| Detect Column Types Dynamically | csv-analyzer | 0.5000 | Yes |
| Use Default Dict for Nested Grouping | json-transformer | 0.3269 | Marginal |
| Group Data by Hierarchical Structure | json-transformer | 0.2917 | Marginal |
| Structure Validation Results with Local Part and Domain | email-validator | 0.2588 | No |

### Assessment

1. **Structural conflation**. The embedding model assigns 0.6667 similarity
   between email validation and rate-limiter because both share structural
   patterns (validation, error handling, structured results). It encodes
   **what kind of program** (validation + reporting) rather than **what
   domain** (email vs concurrency).

2. **When domains overlap, embeddings work**. csv-analyzer entries score
   0.50-0.70 against data-pipeline because both are data processing tasks.
   The embedding correctly identifies domain affinity when it exists.

3. **The 0.50 threshold is correctly calibrated**. Wave 55.5 added
   `_MIN_KNOWLEDGE_SIMILARITY = 0.50` (configurable via
   `FORMICOS_KNOWLEDGE_MIN_SIMILARITY`). This would filter entries #3-#5
   for rate-limiter (0.34-0.41), reducing noise from 5 to 2 entries. It
   would pass entries #1-#2 for data-pipeline (0.50-0.70). The threshold
   is tuned for Qwen3-Embedding-0.6B's score distribution.

4. **Title-only embedding would help**. Currently, the full `content` field
   is embedded. Entry content often contains generic implementation details
   that inflate structural similarity. If title + domains were embedded
   instead, the embedding would be more domain-discriminative.

5. **No diversity enforcement**. The top-5 can contain multiple entries from
   the same source colony. Rate-limiter gets 2 from email-validator, 2 from
   json-transformer, 1 from csv-analyzer. A per-source cap of 2 is
   ineffective here (max is already 2), but a cap of 1 would force broader
   pool coverage.

---

## Phase 6: Lifecycle Gaps

### Extraction → Storage → Retrieval → Consumption pipeline

| Stage | Status | Gap |
|-------|--------|-----|
| **Extraction** | Functional | Over-extraction (Coder model: 21 entries for 8 tasks). No transferability filter. Environment noise leaks through. |
| **Quality gate** | Functional, weak | Catches only ~5-10% of entries (empty/very short + generic). Does not assess transferability or domain relevance. |
| **Security scan** | Functional | 5-axis scan runs on every entry. No observed false positives or missed threats in Phase 0 data. |
| **Admission** | Functional | 7-signal scoring works as designed. All Phase 0 entries admitted as `candidate` (local, safe, fresh, adequate content). |
| **Storage** | Functional | Entries stored in Qdrant with correct metadata. Hybrid search (dense + sparse) operational. |
| **Promotion** | **BROKEN** | Entries transition from `candidate` → `verified` only when source colony status is `completed`. In Phase 0 eval, all tasks complete, so all entries become `verified`. But in production, stalled/redirected colonies leave entries as `candidate` forever. **No usage-based or feedback-based promotion exists.** |
| **Decay** | **UNTESTED** | All Phase 0 entries are minutes old. Decay classes are assigned (`ephemeral` by default) but gamma decay has never been exercised in measurement. 180-day cap is theoretical. |
| **Retrieval** | Partially broken | Semantic threshold (0.50) added in Wave 55.5 fixes the worst noise injection. But static query (task description, no round adaptation) means the same 5 entries are returned for all rounds of a colony. |
| **Consumption** | Unknown | No evidence that colonies reference retrieved knowledge content in their outputs. The retrieval audit found 0/5 relevant entries for rate-limiter and 2/5 for data-pipeline, but did not verify whether the 2 relevant entries actually influenced data-pipeline's output. |

### Promotion gap detail

The only status transition path:
```
candidate → verified    (source colony completed)
candidate → stale       (age >90 days OR prediction_errors ≥5 with <3 accesses)
candidate → rejected    (critical credential detected in maintenance sweep)
```

**Missing transitions:**
- No `candidate → verified` via positive `knowledge_feedback`
- No `candidate → verified` via repeated retrieval/usage
- No `candidate → verified` via operator approval
- No `verified → stale` via negative feedback

The `knowledge_feedback` tool updates `conf_alpha` and `conf_beta` (Bayesian
confidence) but **never changes status**. An entry with `alpha=50, beta=1`
(overwhelming positive feedback) remains `candidate` if its source colony
didn't complete.

### Confidence evolution gap

All Phase 0 entries have identical `Beta(5,5)` priors. This means:
- Thompson sampling draws are identically distributed (mean 0.50)
- The 25% thompson weight in composite scoring contributes zero information
- Entries cannot differentiate by confidence until they receive feedback

In practice, `knowledge_feedback` is rarely called. The 14 proactive
intelligence rules don't trigger feedback. Maintenance doesn't update
confidence. The only confidence update path is explicit agent tool calls
via `knowledge_feedback` — which requires agents to know the tool exists
and choose to call it.

### Non-semantic signal flatness

In the Phase 0 eval context, 62% of the composite score is a constant noise
floor:

| Signal | Weight | Value (all entries) | Information |
|--------|--------|---------------------|-------------|
| semantic | 0.38 | varies (0.25-0.70) | **sole differentiator** |
| thompson | 0.25 | 0.50 (all Beta(5,5)) | zero |
| freshness | 0.15 | ~1.0 (all minutes old) | zero |
| status | 0.10 | 0.50 (all candidate) | zero |
| thread | 0.07 | 0.0 (no thread match) | zero |
| cooccurrence | 0.05 | 0.0 (no prior usage) | zero |

The composite score is effectively `0.38 * semantic + 0.325`. The 6-signal
formula reduces to 1-signal in practice. This is not a bug — it's the
cold-start reality of a knowledge system with no usage history.

---

## Phase 7: Recommendations

### Recommendation 1: Add transferability criteria to extraction prompt

**Problem**: The extraction prompt says "Extract transferable knowledge" but
never defines transferability. The LLM extracts everything interesting,
producing 70-85% non-transferable entries (domain-specific + task-specific +
noise).

**Evidence**: Of ~29 entries in the v4 pool, only 4-6 (15-20%) are genuinely
transferable to a different-domain task. The rest are useful only for the
same kind of task or not at all.

**Fix**: Add explicit criteria to `build_extraction_prompt()` in
`memory_extractor.py:80-88`:

```
Before extracting, ask: would this help a colony working on a COMPLETELY
DIFFERENT kind of task? If the knowledge is specific to email validation,
CSV parsing, or this particular problem, do NOT extract it. Extract only:
- Language-level patterns (data structures, error handling, testing)
- Tool usage patterns (which tools work well together)
- Workflow patterns (read-before-write, test-after-change)
- Anti-patterns (what NOT to do, regardless of domain)
```

**Expected impact**: Reduce extraction volume by ~50-60% while increasing
the proportion of transferable entries from ~20% to ~60-70%. Smaller, higher
quality pool means less retrieval noise.

### Recommendation 2: Expand environment noise filter vocabulary

**Problem**: Two entries ("Pytest is not installed in the environment", "Test
Runner Fails Due to Missing pytest") are pure environment noise that passed
both the extraction prompt and the quality gate.

**Evidence**: `is_environment_noise_text()` in `memory_extractor.py:42-52`
checks for specific phrases and context+error combinations. "pytest" and
"not installed" are not in the filter vocabulary.

**Fix**: Add to `_ENVIRONMENT_NOISE_PHRASES` in `memory_extractor.py:29-37`:

```python
"not installed in the environment",
"not installed in the sandbox",
"fails due to missing",
"module not found",
"import error",
```

And add to `_ENVIRONMENT_NOISE_CONTEXTS` in `memory_extractor.py:38`:

```python
"pytest", "pip", "npm", "package", "module", "import", "install"
```

**Expected impact**: Catch 100% of observed environment noise entries (3-5
entries per run). Zero false positives expected — these phrases are
unambiguous environment chatter.

### Recommendation 3: Add usage-based promotion to verified status

**Problem**: Entries from completed colonies become `verified` immediately
(before any usage proves their value). Entries from stalled colonies stay
`candidate` forever regardless of how useful they prove to be.

**Evidence**: The only promotion path is `source colony completed →
verified` (`colony_manager.py:1902-1911`). The `knowledge_feedback` tool
updates confidence (alpha/beta) but never changes status. An entry retrieved
50 times with 100% positive feedback remains `candidate` if its source colony
stalled.

**Fix**: In the `MemoryConfidenceUpdated` handler in `projections.py`, add
a promotion check:

```python
# After updating alpha/beta:
if (entry["status"] == "candidate"
    and entry.get("conf_alpha", 0) >= 8.0
    and entry.get("prediction_error_count", 0) == 0):
    # Emit MemoryEntryStatusChanged: candidate → verified
    # Reason: "promoted by accumulated positive feedback"
```

Threshold `alpha >= 8.0` means at least 3 positive feedback events from the
`Beta(5,5)` prior. This is conservative — it requires demonstrated value.

**Expected impact**: Entries that prove useful in practice get promoted
regardless of source colony outcome. The 0.10 status weight in composite
scoring then provides a meaningful signal (verified=1.0 vs candidate=0.5),
breaking the flat non-semantic signal problem.

### Recommendation 4: Add content-type signal to extraction prompt

**Problem**: The extraction prompt doesn't guide the LLM toward the
highest-value entry types. The quality gate and admission scoring have
content-type priors (`convention: 0.8`, `learning: 0.5`) but these
preferences aren't communicated to the extraction LLM.

**Evidence**: The v4 pool contains roughly equal counts of techniques,
patterns, conventions, and learnings. But conventions (established patterns)
and anti-patterns (what to avoid) are the most transferable types — they
should be over-represented relative to task-specific learnings.

**Fix**: Add guidance to `build_extraction_prompt()`:

```
Prefer these types (most transferable):
- CONVENTIONS: established ways of doing things that work across projects
- ANTI-PATTERNS: mistakes that should be avoided in any context
Over task-specific LEARNINGS and DECISIONS (least transferable).
```

**Expected impact**: Shift extraction toward higher-value types. Modest
improvement (~10-15% increase in transferable ratio) because the LLM still
needs relevant content to extract from.

### Recommendation 5: Log entry content in eval run data

**Problem**: The Phase 0 run data (`results.jsonl`, `run_*.json`) records
`entries_extracted` counts and `knowledge_attribution` IDs, but does NOT
record entry titles, content, domains, or types. Auditing entry quality
requires cross-referencing with the live Qdrant instance, which is
ephemeral (destroyed on `docker compose down -v`).

**Evidence**: v2 run data shows `knowledge_used` entries with empty titles
and null source_task fields. Entry content is completely lost after the
container is destroyed.

**Fix**: In the eval runner, include full entry metadata in the run output:

```python
knowledge_attribution = {
    "used": [{"id": e.id, "title": e.title, "source_task": ...,
              "score": ..., "domains": e.domains} for e in used],
    "produced": [{"id": e.id, "title": e.title, "content": e.content[:200],
                  "type": e.entry_type, "sub_type": e.sub_type,
                  "domains": e.domains} for e in produced],
}
```

**Expected impact**: Enables systematic quality assessment without requiring
a live system. Future audits can classify every entry without guesswork.

---

## Summary

The knowledge pipeline is architecturally sound — extraction, quality
gating, security scanning, admission, storage, and retrieval all function
as designed. The problem is **intentionality**: the system extracts what the
LLM finds interesting rather than what would be useful to future tasks.

| Root Cause | Impact | Fix Difficulty |
|------------|--------|---------------|
| No transferability criteria in extraction prompt | 70-85% of entries are non-transferable | Low (prompt edit) |
| Environment noise leaks through filter | 3-5 noise entries per run | Low (vocabulary addition) |
| No usage-based promotion | Status signal is flat (all candidate or all verified) | Medium (handler + event) |
| Entry content not logged in eval data | Audits require live system | Low (eval runner change) |
| Embedding conflates structure with domain | Irrelevant entries score 0.5-0.67 | High (model change or field selection) |

The highest-impact fix is Recommendation 1 (transferability criteria). It
addresses the root cause — what enters the brain — rather than trying to
filter noise downstream. Combined with Recommendation 2 (noise filter),
these two prompt-level changes would reduce the noise floor by ~60% with
zero code changes to the scoring or retrieval pipeline.

The compounding signal is real but conditional: it works when the knowledge
pool contains domain-relevant entries (+0.122 for data-pipeline) and hurts
when it doesn't (-0.157 for rate-limiter). Making the pool smaller and
higher-quality shifts the balance toward net-positive compounding.
