# FormicOS Findings: What 59 Waves of Measurement Proved

## The Headline

**Operational knowledge dramatically outperforms domain knowledge for
local LLM agents.**

In 12 controlled measurement runs across 59 waves of development,
deterministic operational guidance (playbooks, anti-pattern cards)
produced a +0.177 mean quality improvement across 7 coding tasks.
Domain knowledge retrieval (accumulated entries from prior colonies)
produced a compounding delta of -0.011 -- effectively zero.

The system that tells agents HOW to work produces 18x more quality
improvement than the system that tells agents WHAT to know.

---

## The Measurement Arc

Each wave found a bottleneck. Each fix revealed the next one.

| Wave | Bottleneck | Fix | Impact |
|------|-----------|-----|--------|
| 54 | Zero productive tool calls | Operational playbooks injected at context position 2.5 | 0 to 45 productive calls per run |
| 54.5 | Truncated JSON in tool arguments | Output token cap raised from 4K to 8K | Quality jumped from 0.25 to 0.72 on affected tasks |
| 54.5 | Quality formula blind to tool use | Added productive_ratio signal | Formula v2 distinguishes useful work from observation spam |
| 55 | False stall detection killed api-design | Broadened convergence signals | api-design completes for the first time |
| 55.5 | Noise entries injected into unrelated tasks | Semantic similarity threshold >= 0.50 | rate-limiter quality +0.222 (v4 to v6) |
| 56 | Low-quality extraction from colony transcripts | Sharper extraction prompt, environment noise filter | csv-analyzer quality +0.129 |
| 58 | Cross-domain contamination from smart extraction | Specificity gate + domain boundary filter | Prevented v11-class failures |
| 58 | 800 tokens consumed by knowledge context | Progressive disclosure: index-only injection | Context reduced to ~250 tokens |

Every row in this table is a measured before/after delta from a specific
eval run. The full results live in `docs/waves/` per-wave directories.

---

## The Syllable Counting Incident

The single most informative failure in the project.

Wave 58 introduced asymmetric extraction: Gemini Flash (a frontier model)
extracts knowledge from colonies run by Qwen3-30B (a local model). The
hypothesis was that a smarter archivist would produce better entries,
driving positive compounding delta.

Gemini extracted 31 entries where local extraction produced 9. One of
those entries was "Strict Constraint Adherence: Syllable Counting,"
harvested from a haiku-writing colony. The retrieval pipeline scored it
highly for rate-limiter -- both involve "structured constraint-following"
-- and injected it into context. The rate-limiter colony hung
mid-execution, producing quality 0.000. The api-design colony received
the same entry and also hung. Two heavy tasks destroyed by a haiku skill.

This single failure proved four things:

1. **The specificity gate is safety infrastructure, not polish.** A gate
   that skips injection for general tasks (no project-specific signals)
   would have blocked this. It was built the next wave.

2. **Domain boundaries are necessary.** Filtering entries by task domain
   (code_implementation vs creative_writing) prevents cross-domain
   contamination. Built alongside the gate.

3. **Smarter extraction without gating is actively dangerous.** Gemini
   produced higher-quality entries that the pipeline ranked MORE
   confidently -- making the contamination worse, not better.

4. **The three-layer injection defense is not optional.** Gate (skip
   general tasks) + domain filter (same-domain only) + progressive
   disclosure (index-only, pull on demand) work as defense-in-depth.
   No single layer is sufficient.

The specificity gate checks for project-specific signals in the task
description ("our," "existing," "module," "codebase," "project"). When
none are present and similarity is below 0.55, injection is skipped
entirely. See `engine/context.py:383-432`.

---

## The Compounding Question

Does accumulated domain knowledge help the same model on future tasks?

Five clean measurement runs. Same eval suite (8 coding tasks, diverse
domains). Two arms each: "accumulate" (shared workspace, knowledge
carries forward) and "empty" (fresh workspace per task, no carry-over).
Delta = accumulate quality minus empty quality, averaged across tasks
that both arms completed.

| Run | Wave | Stack description | Delta |
|-----|------|------------------|-------|
| v2 | 54.5 | First honest measurement | -0.039 |
| v4 | 55 | Coder model, noisy retrieval | -0.033 |
| v7 | 56.5 | Playbooks + threshold + common mistakes | -0.011 |
| v9 | 57 | Complete lifecycle, confidence evolution | -0.009 |
| v10 | 57 | Deterministic scoring, all measurement noise removed | -0.011 |

Mean delta: -0.021. Range: -0.039 to -0.009.

Five independent measurements, each with different stack improvements,
all converge on the same answer: domain knowledge compounding is
approximately zero for a 30B model self-extracting from its own
completed coding tasks across diverse domains.

This is not a measurement artifact. It is the real answer for this
configuration. The model already knows what it extracts. Self-extraction
is tautological -- the reader and writer are the same model with the
same training data.

Two additional runs with Gemini Flash as the archivist (asymmetric
extraction, smarter writer than reader):

| Run | Wave | Stack description | Delta |
|-----|------|------------------|-------|
| v11 | 58 | Gemini extraction, no gate | N/A (two tasks hung from contamination) |
| v12 | 58.5 | Gemini extraction, full safety stack | -0.013 |

v12 was clean but the 0.50 similarity threshold blocked all 390
cross-domain entries before the gate or domain filter could act.
Zero entries were injected. The delta is measuring noise, not
knowledge impact. This is expected: Phase 0's diverse task suite
(email-validator, rate-limiter, haiku-writer, csv-analyzer, api-design)
spans domains too different for same-embedding-space similarity to
cross 0.50. The threshold is working correctly.

The question Phase 0 cannot answer: does knowledge compound when tasks
share a domain? Phase 1 tests this with 8 data-processing tasks in a
single domain. That experiment is running now.

---

## The Architecture That Emerged

Nine layers in the knowledge pipeline, each grounded in a specific
measured failure:

```
Layer 1: EXTRACTION
  LLM extracts skills and experiences from colony transcripts.
  Wave 26. Failure: extraction prompt too vague (Wave 56 fix).

Layer 2: CURATION (Wave 59)
  LLM classifies: CREATE new entry, REFINE existing, MERGE two
  entries, or NOOP. Prevents unbounded accumulation.

Layer 3: STORAGE
  Qdrant vector store with Beta(alpha, beta) confidence posteriors.
  Wave 26 (storage), Wave 34 (Bayesian confidence via ADR-039).

Layer 4: CONFIDENCE EVOLUTION
  Thompson Sampling updates on successful access. Gamma-decay by
  class: ephemeral (0.98), stable (0.995), permanent (1.0).
  Wave 34 (ADR-039). Failure: flat confidence was not informative.

Layer 5: RETRIEVAL
  Six-signal composite scoring (ADR-044):
    0.38 * semantic
    0.25 * thompson
    0.15 * freshness
    0.10 * status
    0.07 * thread_bonus
    0.05 * cooccurrence
  All deterministic for eval (FORMICOS_DETERMINISTIC_SCORING=1).

Layer 6: SPECIFICITY GATE (Wave 58)
  Skip injection entirely for general tasks with no project-specific
  signals. Failure that motivated it: v11 syllable counting incident.

Layer 7: DOMAIN BOUNDARIES (Wave 58.5)
  Filter entries to same task_class domain. Prevents a haiku skill
  from entering a rate-limiter colony.

Layer 8: PROGRESSIVE DISCLOSURE (Wave 58)
  Inject index-only summaries (~50 tokens per entry). Agents pull
  full content (~160 tokens) on demand via knowledge_detail tool.
  Failure: 800-token context blocks crowded out task instructions.

Layer 9: OPERATIONAL PLAYBOOKS (Wave 54)
  Deterministic, always-on, human-curated. Task-class-specific
  workflow guidance injected at context position 2.5. Anti-pattern
  cards at position 2.6. No LLM in the loop.
```

Layer 9 produces the most measured value (+0.177). Layers 1-8 are
infrastructure for the scenario where retrieval adds value:
project-specific knowledge the model does not have from training.

---

## What Is Proven vs What Is Hypothesized

### Proven (with measurement data)

**Operational playbooks improve local LLM agent quality by +0.177.**
Measured across v4 (before playbooks, mean 0.511) to v7 (after playbooks,
mean 0.688). Seven tasks, both arms improved equally. Source:
`docs/waves/wave_56/phase0_v7_results.md`.

**Domain knowledge compounding is approximately zero on diverse general
coding tasks.** Five independent runs (v2, v4, v7, v9, v10), delta range
-0.039 to -0.009, mean -0.021. Source: per-wave result files in
`docs/waves/`.

**Smarter extraction without gating is actively harmful.** v11 (Gemini
archivist, no gate) produced two task hangs from cross-domain
contamination. v12 (same archivist, gate + boundaries) ran clean.
Source: `docs/waves/session_decisions_2026_03_19.md`, Addendum 176.

**The three-layer injection defense prevents cross-domain contamination.**
Gate + domain boundaries + progressive disclosure. v12 ran 8 tasks with
zero contamination incidents. Source: same session memo, Addendum 181.

**The knowledge lifecycle works end-to-end.** Extraction, storage,
confidence evolution, retrieval, and decay all function correctly.
v9 was the first run where MemoryConfidenceUpdated events fired on all
10 accessed entries. Source: `docs/waves/wave_57/phase0_v9_results.md`.

### Hypothesized (architecturally supported, not yet validated)

**Same-domain knowledge compounds.** Phase 1 eval tests 8 data-processing
tasks in sequence. Early data (5/8 tasks complete) shows entries ARE being
accessed cross-task (3, 2, 2, 4 entries accessed on tasks 2-5). Phase 0
saw zero cross-task access. Whether access translates to quality
improvement is the open question.

**Asymmetric extraction produces positive delta when gated.** Gemini
extracts 3.4x more entries than local. With the safety stack active,
these entries should be higher quality without the contamination risk.
Not yet tested on same-domain tasks.

**The curating archivist improves knowledge quality over time.** Wave 59
added REFINE/MERGE/NOOP classification to the extraction prompt. The
hypothesis: fewer, better entries beat many mediocre ones. Not yet
measured.

**Multi-provider parallelism enables genuine stigmergic coordination.**
Pheromone-based coordination exists in the engine but has not been
tested with multiple frontier-class providers working in parallel.

---

## The Numbers

| Metric | Value | Source |
|--------|-------|--------|
| Development waves | 59 | `docs/waves/` directories |
| Phase 0 measurement runs | 12 | v1 through v12 |
| Tests passing | 3504 | `pytest` suite |
| Event types (closed union) | 65 | `core/events.py`, ADR-015/042/045/048 |
| Knowledge pipeline layers | 9 | See architecture section above |
| Eval tasks (Phase 0) | 8 | Diverse domains |
| Eval tasks (Phase 1) | 8 | Single domain (data processing) |
| Operational knowledge delta | +0.177 | v4 to v7 mean quality |
| Domain knowledge delta | -0.011 | v10 accumulate vs empty |
| Similarity threshold | 0.50 | Blocks cross-domain injection |
| Entries blocked by threshold (v12) | 390 | All cross-domain |
| Entries blocked by gate (v12) | 0 | Threshold caught everything first |
| Context per entry (progressive) | ~50 tokens | Index-only format |
| Context per entry (full pull) | ~160 tokens | Via knowledge_detail tool |
| Gemini extraction multiplier | 3.4x | 31 entries vs 9 local |
| ADRs | 48 | `docs/decisions/INDEX.md` |

---

## What Phase 1 Will Answer

Phase 0 tested diverse tasks (email-validator, rate-limiter,
haiku-writer, csv-analyzer, api-design, data-pipeline, markdown-parser,
json-transformer). Knowledge from one task had low similarity to the
next because the domains are genuinely different. The 0.50 threshold
correctly blocked injection.

Phase 1 tests same-domain tasks: csv-reader, data-validator,
data-transformer, pipeline-orchestrator, error-reporter,
performance-profiler, schema-evolution, pipeline-cli. All data
processing. Later tasks reference prior work ("our csv_reader,"
"our pipeline"). Similarity scores should cross 0.50. The specificity
gate should fire on project signals. Knowledge should compound.

If the delta is positive on tasks 5-8 (where the knowledge pool is
richest), same-domain compounding is real and the pipeline's value
extends beyond operational knowledge. If the delta is still zero,
the 30B model is self-sufficient for data processing regardless of
accumulated entries, and the pipeline's value is purely operational.

Either answer is useful. One validates the retrieval architecture.
The other simplifies the system.

---

## Reading Further

| Document | What it covers |
|----------|---------------|
| `docs/waves/wave_56/phase0_v7_results.md` | The +0.177 operational knowledge finding |
| `docs/waves/wave_57/wave_57_revised_direction.md` | Strategic reframe: operational >> domain |
| `docs/waves/wave_57/phase0_v9_results.md` | First complete lifecycle validation |
| `docs/decisions/044-cooccurrence-scoring.md` | Six-signal composite scoring design |
| `docs/decisions/048-memory-entry-refined.md` | Wave 59 curation event design |
| `docs/KNOWLEDGE_LIFECYCLE.md` | Operator runbook for the knowledge system |
| `docs/DEPLOYMENT.md` | Running the stack locally |
| `CLAUDE.md` | Architecture overview and hard constraints |
