# Retrieval Quality Audit -- Phase 0 v4 Investigation

**Date**: 2026-03-22
**Run audited**: Phase 0 v4, Arm 1 (accumulate), Qwen3-Coder model
**Run ID**: `a055f566be6e`
**Comparison run**: Phase 0 v3, Arm 1 (accumulate), Qwen3-30B general model
**Comparison run ID**: `be34e691864f`

## 1. Knowledge Pool at Task 6 (rate-limiter)

When rate-limiter starts (sequence position 6), the knowledge pool contains
entries extracted from the first 5 completed tasks. The extraction pipeline
runs asynchronously after colony completion, so entries are available by the
time the next task starts.

### v4 (Qwen3-Coder) pool: 27 entries from 5 source tasks

| Source Task | Colony | Entries | Sample Titles |
|-------------|--------|---------|---------------|
| email-validator | colony-6bdcf1ef | 6 | "Validate Email Format Using RFC 5322 Basics", "Comprehensive Email Validation with Error Reporting", "Using write_workspace_file Instead of patch_file" |
| json-transformer | colony-e4460188 | 7 | "Group Data by Hierarchical Structure", "Handle Duplicate IDs with Validation", "Sanitize and Normalize Group Keys", "Use Default Dict for Nested Grouping" |
| csv-analyzer | colony-2c5742a4 | 10 | "Validate CSV File Structure Before Processing", "Detect Column Types Dynamically", "Handle Missing Values with Robust Counting", "Compute Summary Statistics Based on Data Type" |
| markdown-parser | colony-09d9bb39 | 6 | "Parse Markdown to AST with Nested Formatting", "Validate and Test Markdown Parsers", "Pytest is not installed in the environment", "Test Runner Fails Due to Missing pytest" |

**Total**: 29 entries available (some extracted after rate-limiter started).

### v3 (general) pool at same point: ~24 entries from 5 source tasks

Comparable count. The v3 model extracted fewer entries per task (4-7 vs 6-10
for v4), but the domain distribution is the same: email validation, JSON
transformation, CSV analysis, markdown parsing. None of these source tasks
are about concurrency, rate limiting, or token bucket algorithms.

### Key observation: no relevant source material exists

Neither pool contains a single entry about rate limiting, concurrency,
threading, token buckets, or related algorithms. The closest entries are
generic Python patterns ("Use Default Dict for Nested Grouping", "Validate
CSV File Structure Before Processing"). The retrieval system cannot return
relevant knowledge that doesn't exist.

## 2. Rate-limiter Retrieved Entries (v4)

Colony `colony-a3cdabfe` retrieved **the same 5 entries across all 8 rounds**
(no round-adaptive retrieval). The `score` field is the raw Qdrant vector
cosine similarity, not the composite score.

| # | Entry Title | Source Task | Vector Score | Conf | Relevant to Rate Limiter? |
|---|------------|------------|-------------|------|---------------------------|
| 1 | Comprehensive Email Validation with Error Reporting | email-validator | 0.6667 | 0.50 | **No** — regex patterns for email format |
| 2 | Extracting Transferable Knowledge from Colony Results | email-validator | 0.5000 | 0.50 | **No** — meta-knowledge about the system |
| 3 | Hierarchical Grouping Improves Data Usability | json-transformer | 0.3409 | 0.50 | **No** — dict grouping for user records |
| 4 | Validate CSV File Structure Before Processing | csv-analyzer | 0.4103 | 0.50 | **No** — CSV file validation |
| 5 | Use Default Dict for Nested Grouping | json-transformer | 0.4103 | 0.50 | **Marginal** — defaultdict is a general Python pattern |

**Relevance: 0/5** genuinely relevant. 1/5 marginally relevant.

### Composite score decomposition

Since all entries have identical non-semantic signals (all candidate status,
all Beta(5,5) priors, all created within minutes, same thread, no
cooccurrence), the composite ordering is determined entirely by the semantic
(vector similarity) signal:

| Signal | Weight | Value (all entries) | Contribution |
|--------|--------|-------------------|--------------|
| semantic | 0.38 | varies (0.34-0.67) | **only differentiator** |
| thompson | 0.25 | 0.50 (Beta(5,5)) | 0.125 (constant) |
| freshness | 0.15 | ~1.0 (minutes old) | 0.150 (constant) |
| status | 0.10 | 0.50 (candidate) | 0.050 (constant) |
| thread | 0.07 | 0.0 (no thread) | 0.000 (constant) |
| cooccurrence | 0.05 | 0.0 (no usage yet) | 0.000 (constant) |
| **Non-semantic floor** | | | **0.325** |

With 62% of the composite score being a constant floor across all entries,
the ranking is determined by a 38% band. The top entry ("Comprehensive
Email Validation") beats the bottom entry by only
`0.38 * (0.6667 - 0.3409) = 0.124` composite points.

### The embedding quality problem

The Qwen3-Embedding-0.6B model assigns cosine similarity of **0.6667** between
the rate-limiter task description ("implement a rate limiter with token bucket
algorithm, thread-safe, with burst support...") and "Comprehensive Email
Validation with Error Reporting." This is a high similarity score for
semantically unrelated content.

The embedding model appears to encode structural patterns (validation,
structured results, error handling) rather than domain-specific meaning.
Email validation and rate limiter implementation share structural patterns
(input checking, structured output, error reporting) but are completely
different domains.

## 3. Rate-limiter Retrieved Entries (v3 for comparison)

Colony `colony-8d065e89` in the v3 run retrieved:

| # | Entry Title | Source Task | Vector Score | Relevant? |
|---|------------|------------|-------------|-----------|
| 1 | Test Edge Cases in Data Processing Pipelines | csv-analyzer | 0.7500 | **No** — testing patterns for data processing |
| 2 | Validate CSV File Structure Before Processing | csv-analyzer | 0.6111 | **No** — CSV validation |
| 3 | Test Runner Not Available During Execution | csv-analyzer | 0.4762 | **No** — environment issue |
| 4 | Structure Validation Results with Local Part and Domain | email-validator | 0.3250 | **No** — email parsing |
| 5 | Detect and Resolve Duplicate IDs | json-transformer | 0.4500 | **No** — deduplication |

**Relevance: 0/5** in v3 as well. The v3 run also retrieved irrelevant
entries for rate-limiter. The key difference: v3 rate-limiter scored 0.5082
quality (vs 0.3508 in v4), but this delta is not caused by retrieval — both
arms got equally useless knowledge. The quality difference is model behavior.

## 4. Data-pipeline Retrieved Entries (v4)

Colony `colony-a0c7a148` retrieved **the same 5 entries across all 8 rounds**:

| # | Entry Title | Source Task | Vector Score | Relevant to Data Pipeline? |
|---|------------|------------|-------------|---------------------------|
| 1 | Compute Summary Statistics Based on Data Type | csv-analyzer | 0.7000 | **Yes** — data aggregation patterns |
| 2 | Use Default Dict for Nested Grouping | json-transformer | 0.3269 | **Marginal** — general Python pattern |
| 3 | Detect Column Types Dynamically | csv-analyzer | 0.5000 | **Yes** — data type inference |
| 4 | Structure Validation Results with Local Part and Domain | email-validator | 0.2588 | **No** — email parsing |
| 5 | Group Data by Hierarchical Structure | json-transformer | 0.2917 | **Marginal** — hierarchical data |

**Relevance: 2/5** genuinely relevant. 2/5 marginally relevant. 1/5 irrelevant.

### Why data-pipeline gets better retrievals

The csv-analyzer task ("analyze CSV files, compute statistics, detect types")
is semantically close to the data-pipeline task ("process web server logs,
extract fields, aggregate statistics"). Both involve data processing, type
detection, and summary computation. The embedding model correctly ranks
csv-analyzer entries highest for data-pipeline.

This confirms: **when the knowledge pool contains domain-relevant entries,
retrieval works. When it doesn't, retrieval returns noise.**

## 5. Data-pipeline Retrieved Entries (v3 for comparison)

| # | Entry Title | Source Task | Vector Score | Relevant? |
|---|------------|------------|-------------|-----------|
| 1 | Handle Missing or Invalid Fields Gracefully | json-transformer | 0.8333 | **Yes** — error handling in data processing |
| 2 | Detect Column Types Dynamically with Type Inference | csv-analyzer | 0.5714 | **Yes** — type inference |
| 3 | Group Data by Hierarchical Structure | json-transformer | 0.2857 | **Marginal** |
| 4 | Validate CSV File Structure Before Processing | csv-analyzer | 0.3611 | **Marginal** |
| 5 | Test Edge Cases in Data Processing Pipelines | csv-analyzer | 0.2588 | **Marginal** |

**Relevance: 2/5** in v3 as well. Comparable hit rate. The quality delta
(v3 0.5373 vs v4 0.5281) is within noise, confirming retrieval quality is
similar when the pool has relevant entries.

## 6. Failure Pattern Diagnosis

### Pattern 1: Irrelevant but high-confidence entries — **NOT the cause**

All entries have identical confidence (Beta(5,5) = 0.50). Thompson sampling
cannot differentiate because no entries have been used enough to evolve
their priors. The confidence signal is completely flat.

### Pattern 2: Generic entries beating task-specific ones — **PARTIAL match**

"Comprehensive Email Validation with Error Reporting" has structural overlap
with many tasks (validation, error reporting, structured results). But the
root cause is deeper: the embedding model itself assigns high similarity to
structurally similar but domain-distant content. This isn't a retrieval
scoring problem — it's an embedding quality problem.

### Pattern 3: Same-cluster entries crowding out diversity — **PARTIAL match**

Rate-limiter's top-5 contains 2 entries from email-validator, 2 from
json-transformer, 1 from csv-analyzer. No single source dominates (max 2
from one colony), so per-source dedup wouldn't help much. But the 5 entries
span only 3 source tasks out of 5 available.

### Root cause: **No relevant knowledge exists in the pool**

The primary failure is not retrieval scoring — it's **knowledge pool
composition**. The first 5 tasks in the Phase 0 suite (email validation,
JSON transformation, haiku writing, CSV analysis, markdown parsing) produce
zero knowledge about concurrency, rate limiting, or token bucket algorithms.
No scoring formula can retrieve relevant entries that don't exist.

The retrieval system correctly identifies the *least irrelevant* entries
(data processing patterns from csv-analyzer are closer to rate-limiter than
haiku writing). But "least irrelevant" is still irrelevant.

### Secondary cause: **Static retrieval across rounds**

The same 5 entries are retrieved for all 8 rounds of a colony. The query
is the task description, which doesn't change between rounds. This means:

1. If the initial retrieval is bad, it stays bad for the entire colony
2. No opportunity to retrieve entries produced by the colony itself
3. No adaptation based on what tools were called or what was learned

### Tertiary cause: **Flat non-semantic signals in eval context**

In a real production workspace with accumulated usage history, entries
would have differentiated Thompson scores (from varied alpha/beta),
different statuses (candidate vs verified vs stale), cooccurrence weights,
and thread bonuses. In the eval context, all of these are constant:

| Signal | Weight | Eval context value | Information content |
|--------|--------|--------------------|-------------------|
| semantic | 0.38 | varies | **sole differentiator** |
| thompson | 0.25 | 0.50 (all Beta(5,5)) | zero |
| freshness | 0.15 | ~1.0 (all new) | zero |
| status | 0.10 | 0.50 (all candidate) | zero |
| thread | 0.07 | 0.0 (no threads) | zero |
| cooccurrence | 0.05 | 0.0 (no usage) | zero |

In the eval context, the composite score is effectively:
`0.38 * semantic + 0.325` — a linear rescaling of vector similarity.
The 62% non-semantic weight is pure noise that compresses the score
range without adding information.

## 7. Why v4 Accumulate Underperforms v4 Empty

The compounding reversal (-0.033) is not caused by retrieval returning
harmful knowledge. It has three contributing factors:

### A. Context token waste (confirmed)

Each round, 5 irrelevant entries consume ~375 tokens (75 tokens each at
standard tier) from the context budget. Over 8 rounds, that's ~3000 tokens
of irrelevant content injected into the model's context. The empty arm
spends those tokens on... nothing. But "nothing" is better than noise that
could confuse the model.

For data-pipeline, 2/5 relevant entries provide useful context, offsetting
the noise from 3/5 irrelevant entries. Net effect: +0.122 advantage.

For rate-limiter, 0/5 relevant entries means pure noise. Net effect: -0.157
disadvantage.

### B. Model distraction (plausible, not proven)

The Qwen3-Coder model may be more susceptible to context distraction than
the general model. The v3 general model also got 0/5 relevant entries for
rate-limiter but still scored 0.5082 (vs v4's 0.3508). This suggests the
Coder model may over-attend to injected knowledge context, even when
irrelevant.

### C. Knowledge production overhead (minor)

The v4 accumulate arm extracted 21 entries (vs 9 in v3), which means more
extraction LLM calls and Qdrant upserts. This doesn't affect quality
directly but adds latency and may affect the model's context in subsequent
rounds through extraction-related system messages.

## 8. Recommended Fixes

### Fix 1: Minimum semantic threshold (HIGH PRIORITY)

Do not include entries in context if their raw vector similarity is below a
threshold (e.g., 0.5). For rate-limiter, this would have excluded entries
#3, #4, #5 (scores 0.34, 0.41, 0.41), reducing noise from 5 to 2 entries.
Even 2 irrelevant entries at 0.67 and 0.50 is better than 5.

**Implementation**: Single line in `context.py` before the
`knowledge_access_items.append()` call:
```python
if float(item.get("score", 0.0)) < 0.50:
    continue
```

This is the simplest fix with the highest impact. It's a quality gate,
not a scoring change.

### Fix 2: Round-adaptive query (MEDIUM PRIORITY)

Use the task description for round 1, but for subsequent rounds, include
the most recent tool call outputs or summaries in the query. This would
allow retrieval to adapt as the colony produces artifacts.

### Fix 3: Source diversity cap (LOW PRIORITY)

Max 2 entries per source colony in the top-5. Currently rate-limiter gets
2 from email-validator, 2 from json-transformer, 1 from csv-analyzer. A
diversity cap would force inclusion of entries from markdown-parser and
csv-analyzer, which are marginally more relevant.

### Fix 4: Eval-specific entry maturation (LOW PRIORITY)

In the eval runner, promote entries to `active` status (0.8 bonus) and
update their Beta priors based on task completion quality. This would
give the non-semantic signals some information content in the eval context.

### Not recommended: Weight adjustment

Increasing semantic weight would not help when the semantic signal itself
is low-quality. The Qwen3-Embedding-0.6B model's similarity scores do not
reliably distinguish domain relevance from structural similarity. The fix
is a quality gate (Fix 1), not weight tuning.

### Not recommended: Task-class affinity

There is no task-class metadata on knowledge entries. Adding it would
require changes to the extraction pipeline and event schema. The simpler
semantic threshold achieves most of the same benefit.

## 9. Summary

| Finding | Evidence |
|---------|----------|
| Rate-limiter got 0/5 relevant entries | All 5 are from email/JSON/CSV tasks |
| Data-pipeline got 2/5 relevant entries | csv-analyzer entries match data processing |
| Same entries returned all 8 rounds | Query is static (task description) |
| All non-semantic signals are constant | Beta(5,5), candidate status, no usage |
| Composite is effectively `0.38*semantic + 0.325` | 62% of score is noise floor |
| Embedding model conflates structural and domain similarity | Email validation scores 0.67 vs rate-limiter task |
| v3 had same problem but less quality impact | General model less sensitive to context noise |

**Root cause**: Not a retrieval scoring bug. The knowledge pool has no relevant
entries for rate-limiter. The fix is a semantic quality gate to avoid injecting
noise when no relevant knowledge exists.

**The compounding signal is real but conditional**: it works when the
knowledge pool contains domain-relevant entries (data-pipeline: +0.122) and
hurts when it doesn't (rate-limiter: -0.157). A semantic threshold would
let the system know the difference.
