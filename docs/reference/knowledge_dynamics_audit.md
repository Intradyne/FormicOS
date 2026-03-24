# Knowledge Dynamics Audit — Phase 0 v9 Post-Mortem

Audit date: 2026-03-22. Research-only; no code changes.

> **STATUS (2026-03-23):** Several findings have been addressed in subsequent waves:
>
> - **Section 3 (Playbook-knowledge conflicts):** Context positions 2.5 (playbook)
>   and 2.6 (common mistakes) are now implemented and correctly documented. The
>   conflict analysis remains valid — playbooks dominate by position.
> - **Section 5 (Dead paths):** `playbook_generation` stamp is still set but not read
>   (still valid). Three freshness functions still duplicated (still valid).
>   Domain normalization is now addressed via `primary_domain` stamping (Wave 58.5)
>   which adds a task-class domain tag. Domain tag variant spelling (Section 1 of
>   `knowledge_flow_audit.md`) partially mitigated but not fully solved.
> - **R3 (Use or remove playbook_generation):** Still valid — the field remains dead.
> - **R5 (Consolidate freshness functions):** Still valid — three copies remain.
>
> Findings in Sections 1-2 (Thompson Sampling math, signal independence) and Section 4
> (extraction classification) remain current and accurate.

## 1. Confidence lifecycle effectiveness

### Thompson Sampling math

The system uses `random.betavariate(alpha, beta)` as the Thompson Sampling
draw. The expected value of Beta(a, b) = a / (a + b).

| Distribution | E[X] | Difference from Beta(5,5) |
|---|---|---|
| Beta(5.0, 5.0) | 0.5000 | baseline |
| Beta(5.5, 5.0) | 0.5238 | +0.0238 |
| Beta(6.0, 5.0) | 0.5455 | +0.0455 |
| Beta(10.0, 5.0) | 0.6667 | +0.1667 |
| Beta(15.0, 5.0) | 0.7500 | +0.2500 |

### How many accesses to flip a ranking?

The composite formula in `knowledge_catalog.py` (the canonical path for
institutional memory retrieval) is:

```
score = 0.38*semantic + 0.25*thompson + 0.15*freshness + 0.10*status
        + 0.07*thread + 0.05*cooccurrence
```

To flip a ranking when two entries differ by 0.01 in semantic score:

```
delta_needed = 0.38 * 0.01 / 0.25 = 0.0152 in thompson expected value
```

Since E[Beta(a, b)] = a/(a+b), and starting from a=5, b=5 (E=0.5):

```
(a / (a + 5)) - 0.5 = 0.0152
a / (a + 5) = 0.5152
a = 5.313
```

So an alpha increase of ~0.31 (from 5.0 to 5.31) compensates for a 0.01
semantic score gap. In practice, `MemoryConfidenceUpdated` events increment
alpha by outcome-weighted amounts; 10 events in Phase 0 v9 is the first
time this path has fired at all.

### BUT: Thompson Sampling is stochastic, not deterministic

The system calls `random.betavariate()` — a single stochastic draw, not
the expected value. The standard deviation of Beta(5, 5) is ~0.151.
This means a single draw from Beta(5.5, 5.0) vs Beta(5.0, 5.0) has a
negligible effect on any individual ranking. The stochastic variance
(std=0.151) overwhelms the expected-value shift (0.024). Only after many
retrieval events does the bias emerge statistically.

**Finding: At current alpha/beta values (~5), Thompson Sampling adds
randomized exploration more than confidence-weighted ranking. It would
take alpha ~15-20 (10+ positive observations) for confidence to
reliably influence rankings against a 0.05 semantic score gap.**

### Three different scoring formulas

The codebase contains three distinct composite scoring implementations:

1. **`knowledge_catalog.py:_composite_key()`** — 6-signal formula with
   co-occurrence, thread bonus, pin boost, federation penalty. Used for
   catalog search results. Weights from `COMPOSITE_WEIGHTS`.

2. **`memory_store.py:_rank_and_trim()`** — 4-signal formula:
   `0.40*semantic + 0.25*thompson + 0.15*freshness + 0.12*status`.
   Missing: thread bonus, co-occurrence. Different semantic weight (0.40
   vs 0.38). This scores results from Qdrant before they reach the
   catalog layer.

3. **`context.py` legacy skill bank path** — 4-signal formula:
   `0.50*semantic + 0.25*confidence + 0.20*freshness + 0.05*exploration`.
   Uses raw confidence (not Thompson draw), UCB exploration bonus.
   Only active when `skip_legacy_skills=False` (no institutional memory).

**Finding: Results are double-ranked. `memory_store._rank_and_trim()` sorts
results before passing them to `knowledge_catalog.py`, which re-sorts
with a different formula. The first sort's top-k truncation may discard
entries that would rank higher under the second formula.**

## 2. Signal independence in eval vs production

### Eval scenario (Phase 0 v9: 8 tasks, fresh workspace, no threads)

In a fresh eval workspace with entries created minutes ago and no thread
context:

| Signal | Value | Weight | Contribution |
|---|---|---|---|
| semantic | variable (0.3-0.7) | 0.38 | 0.114-0.266 |
| thompson | ~0.50 (Beta(5,5) draw, high variance) | 0.25 | ~0.125 |
| freshness | ~1.0 (entries are minutes old) | 0.15 | 0.150 |
| status | 0.5 (all entries are "candidate") | 0.10 | 0.050 |
| thread | 0.0 (no thread_id match) | 0.07 | 0.000 |
| cooccurrence | 0.0 (no usage history) | 0.05 | 0.000 |

**Effective formula in eval:**
```
score = 0.38*semantic + 0.25*thompson + 0.200 (constant)
```

Four of six signals are constant. The ranking is driven entirely by
semantic similarity (38% weight) plus random noise from Thompson draws
(25% weight). The random noise has std ~0.038 (0.25 * 0.151), which is
comparable in magnitude to a 0.10 difference in semantic score.

**Finding: In eval, retrieval is "semantic + noise". The sophisticated
6-signal composite degenerates to a 2-signal formula where one signal
is pure randomness. This explains why retrieval adds ~zero quality:
the ranking is semi-random at current alpha/beta priors.**

### Production scenario

In production (long-running workspace, threads, verified entries):
- freshness varies (entries age)
- status varies (candidate/verified/active)
- thread bonus kicks in (0.07 weight for same-thread)
- co-occurrence builds (requires repeated co-retrieval)

The formula only becomes meaningfully multi-signal after sustained usage.
For short eval runs, it is effectively broken.

## 3. Playbook-knowledge conflicts

### Context assembly order

From `context.py:assemble_context()`:

```
Position 1:   System prompt
Position 2:   Round goal
Position 2.5: Operational playbook (<operational_playbook> XML)
Position 2.6: Common mistakes (<common_mistakes> XML)
Position 2a:  Structural context
Position 2b:  Input sources (chained colonies)
Position 2c:  [System Knowledge] — retrieved entries
Position 3:   Routed agent outputs
Position 4:   Merge summaries
Position 5:   Previous round summary
Position 6:   Legacy skill bank
```

### Conflict analysis

Playbooks are deterministic, XML-tagged, and position-dominant (2.5).
Knowledge entries are probabilistic, lower-priority (2c), and formatted
as plain text with `[SKILL, CANDIDATE, INST]` tags.

**Potential conflicts:**

1. **Observation limit**: Playbooks set `observation_limit: 2-4` (e.g.,
   "Read the target file once"). Knowledge entries might say "always
   read multiple files before coding" if such a convention was extracted.
   Playbook wins by position and XML salience.

2. **Tool workflow**: Playbooks prescribe specific tool sequences
   ("Read -> Write -> Test -> Fix"). Knowledge entries describing
   alternative workflows would create ambiguity, but playbooks have
   structural advantage (XML tags, earlier position, always present).

3. **No semantic contradiction detected**: The playbooks focus on
   *procedure* (which tool to call when). The extraction prompt asks
   for *reusable techniques and patterns*. These are different
   categories — the overlap is low by design.

**Finding: No hard contradiction exists. Playbooks dominate by position
and structural formatting. The risk is noise, not conflict: retrieved
entries that weakly echo playbook guidance (e.g., "test after writing")
consume context budget without adding new information.**

## 4. Extraction output classification

### Extraction prompt analysis

`build_extraction_prompt()` explicitly asks for:

- **Skills**: "actionable instruction", "when_to_use", "failure_modes"
  with sub-types technique/pattern/anti_pattern
- **Experiences**: "1-2 sentences", "trigger", "polarity" with sub-types
  decision/convention/learning/bug

The prompt says: *"Focus on reusable techniques, not task-specific details.
Ask: would an agent working on a completely different problem benefit?"*

### Harvest prompt analysis

`build_harvest_prompt()` classifies transcript turns as:
bug / decision / convention / learning

Harvest output is always `summary` (one sentence).

### Classification

| Source | Content type | Overlap with playbooks |
|---|---|---|
| Extraction: skills | Domain techniques, tool patterns | Medium — "how to use a tool" overlaps with playbook tool guidance |
| Extraction: experiences | Tactical lessons, bug reports | Low — specific to encountered situations |
| Harvest: conventions | "always do X" process rules | **High** — directly overlaps playbook steps |
| Harvest: decisions | "chose X because Y" | Low — contextual rationale |
| Harvest: bugs | "X failed because Y" | Low — specific failure modes |

**Finding: Harvest conventions are the highest-overlap category with
playbooks. A convention like "always run tests after writing code" is
exactly what playbooks already encode statically. The extraction prompt's
focus on "reusable techniques" is appropriately scoped, but the harvest
prompt's "convention" type captures operational guidance that duplicates
playbook content.**

### Do extracted entries add anything unique?

Yes — domain-specific techniques (how to structure a rate limiter, CSV
parsing patterns) are genuinely outside playbook scope. But conventions
and anti-patterns often restate operational guidance that playbooks already
provide with more structural authority.

## 5. Dead paths and unused stamps

### Playbook generation stamp

The `playbook_generation` field is:

- **Defined**: `core/types.py:430` — `MemoryEntry.playbook_generation`
- **SET at 2 locations**: `colony_manager.py:1335` (harvest path) and
  `colony_manager.py:1941` (extraction path)
- **NEVER READ**: No code in the entire codebase reads this field for
  any operational decision. It is stamped on entries and then ignored.
  Tests verify the stamp is computed correctly but no production code
  consumes it.

**Finding: `playbook_generation` is dead metadata. It was designed (Wave
56.5 C) as a provenance marker to correlate knowledge entries with the
playbook version that was active during extraction, presumably for
future filtering of entries extracted under obsolete playbooks. That
consumer does not exist.**

### Three duplicate freshness functions

Three identical implementations of 90-day half-life freshness decay:
- `engine/context.py:_compute_freshness()` (line 184)
- `surface/knowledge_catalog.py:_compute_freshness()` (line 213)
- `surface/memory_store.py:_ms_compute_freshness()` (line 31)

All use `2.0 ** (-age_days / 90.0)`. This is copy-paste duplication.

### Dual extraction paths

Both fire for every colony completion (line 1060-1061 of colony_manager.py):
```python
self._hook_memory_extraction(colony_id, ws_id, succeeded)   # extraction
self._hook_transcript_harvest(colony_id, ws_id, succeeded)   # harvest
```

Both run in parallel (fire-and-forget asyncio tasks). Both call the LLM.
Both emit `MemoryEntryCreated` events. The harvest path does dedup against
existing entries (similarity > 0.82 threshold), which should prevent
exact duplicates, but near-duplicates with different framing can survive.

**Finding: Every colony completion triggers two LLM calls for knowledge
extraction. The harvest path was designed for a different input (raw
transcript turns vs final summary), but the overlap between "conventions
from transcript" and "skills from output" creates near-duplicate entries
that the 0.82 similarity threshold may not catch.**

### Legacy skill bank

The legacy skill bank (`skill_bank_v2` collection) is still queried in
parallel with institutional memory by `knowledge_catalog.py`. Comments
say "Legacy skill crystallization disabled (Wave 28)" and "Wave 30"
but the search path remains active. In a fresh workspace, the legacy
collection is empty, so this is a no-op query.

### Double-ranking

As noted in Section 1: `memory_store._rank_and_trim()` sorts with a
4-signal formula, then `knowledge_catalog.py` re-sorts the same results
with a 6-signal formula. The first sort truncates to top-k before the
second sort sees the results. This can discard entries that would rank
higher under the canonical 6-signal formula.

## 6. The "remove retrieval" thought experiment

### What would break

1. **`memory_search` agent tool** — agents can explicitly search knowledge
   via tool call. Would need removal or stubbing. (~50 lines in
   `tool_dispatch.py`, ~30 lines in `runtime.py`)

2. **`knowledge_feedback` agent tool** — explicit quality feedback on
   retrieved entries. Dead without retrieval.

3. **Proactive intelligence** — 14 briefing rules analyze knowledge health.
   Several rules (confidence decline, stale cluster, coverage gap,
   contradiction) inspect the knowledge store. These would lose their
   data source but could still operate on projection state.

4. **Knowledge browser UI** — REST endpoints serve knowledge entries for
   operator inspection. Would lose search but could keep listing.

5. **Forager reactive trigger** — gap detection in `knowledge_catalog.py`
   triggers foraging when retrieval coverage is thin. No retrieval =
   no gap detection.

6. **Co-occurrence reinforcement** — builds up over retrieval queries.
   Dead without retrieval.

7. **Confidence evolution** — `MemoryConfidenceUpdated` events are
   triggered by knowledge access and feedback. No retrieval = no
   confidence lifecycle.

### What would simplify

1. Remove `[System Knowledge]` block from context assembly (~45 lines
   in `context.py`)
2. Remove `fetch_knowledge_for_colony()` call from colony_manager round
   loop
3. Remove `_rank_and_trim()` from `memory_store.py` (unused if no
   context injection)
4. Simplify `knowledge_catalog.py` search path (1072 lines, much of
   which is scoring/ranking)

### LOC in the retrieval path

| File | Lines | Purpose |
|---|---|---|
| `knowledge_catalog.py` | 1072 | Federated search, scoring, tiered retrieval |
| `memory_store.py` | 468 | Qdrant projection, search, rank_and_trim |
| `context.py` | 637 | Context assembly (knowledge is ~45 lines) |
| `knowledge_constants.py` | 63 | Composite weights, gamma constants |
| `scoring_math.py` | 66 | Thompson draw + UCB blend |
| `memory_extractor.py` | 344 | Extraction prompts (write path, not retrieval) |
| **Total** | **2650** | Retrieval + scoring infrastructure |

### Value of keeping retrieval active for observability

Even with zero quality impact, retrieval provides:
- **Operator visibility**: Knowledge browser shows what the system has
  learned, with trust rationale and provenance
- **Compounding measurement**: `RetrievalMetrics` tracks access patterns
  for compounding-curve analysis
- **Future signal**: As alpha/beta values diverge from priors through
  sustained use, Thompson Sampling becomes meaningful
- **Forager trigger**: Gap detection enables proactive knowledge acquisition

**Finding: Removing retrieval saves ~45 lines of context assembly but
breaks 7 downstream systems. The zero-quality-impact result is an eval
artifact: the 6-signal formula degenerates to "semantic + noise" in
fresh workspaces. In sustained production use, the additional signals
would activate.**

## 7. Recommendations

### R1: Fix the double-ranking pipeline

`memory_store._rank_and_trim()` sorts and truncates results before
`knowledge_catalog.py` re-sorts them with a different formula. The
first truncation can discard entries that the canonical formula would
rank higher. Either: (a) remove `_rank_and_trim()` and let the catalog
do all scoring, or (b) increase the over-fetch multiplier so truncation
loss is negligible. The memory_store already over-fetches 2x (`top_k * 2`
at line 324); increasing to 4x would reduce but not eliminate the problem.

### R2: Make Thompson Sampling deterministic for eval

In eval, replace `random.betavariate(alpha, beta)` with the expected
value `alpha / (alpha + beta)`. This removes the noise floor that makes
the 6-signal composite degenerate to "semantic + random". A feature flag
(`FORMICOS_DETERMINISTIC_SCORING=1`) would allow deterministic scoring
for eval while preserving exploration in production.

### R3: Use the playbook generation stamp or remove it

`playbook_generation` is stamped on every extracted entry but never read.
Either: (a) add a retrieval-time filter that deprioritizes entries
extracted under obsolete playbook generations, or (b) remove the field
and the two stamping call sites. The field was designed for a purpose
that does not yet exist.

### R4: Merge harvest conventions with playbook updates

Harvest "convention" entries overlap with playbook content. Consider:
(a) excluding `convention` from harvest types when the playbook
generation stamp matches (conventions were already captured statically),
or (b) feeding high-confidence conventions back into playbook YAML as
a semi-automated update path.

### R5: Consolidate the three freshness functions

Three identical `2.0 ** (-age_days / 90.0)` implementations exist in
`context.py`, `knowledge_catalog.py`, and `memory_store.py`. Move to a
single shared function in `knowledge_constants.py` or `scoring_math.py`
and import from all three call sites.
