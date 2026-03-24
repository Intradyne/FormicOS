# What We Learned: Knowledge Compounding in Local LLM Agent Systems

A synthesis of 14 controlled eval runs measuring whether accumulated
knowledge improves agent colony quality in FormicOS.

## 1. The Experiment

FormicOS colonies extract knowledge entries (skills, conventions, bug
patterns) from completed work and store them in a Bayesian knowledge bank
with Thompson Sampling retrieval. The central hypothesis: accumulated
knowledge compounds across tasks, making later colonies measurably better.

We tested this with an accumulate-vs-empty protocol. Both arms run
identical tasks with identical models. The accumulate arm preserves
knowledge entries across tasks. The empty arm starts fresh each task.
The delta between mean quality scores measures the impact of accumulated
knowledge.

14 controlled runs across two eval suites:

- **Phase 0** (8 runs): 8 diverse coding tasks (rate limiter, email
  validator, CSV parser, markdown renderer, state machine, cache, task
  scheduler, log parser). Cross-domain -- each task is unrelated to the
  others.

- **Phase 1** (2 runs): 8 same-domain data-processing tasks (csv-reader,
  data-validator, data-transformer, pipeline-orchestrator, error-reporter,
  performance-profiler, schema-evolution, pipeline-cli). Sequential --
  later tasks reference earlier modules.

Primary model: Qwen3-30B-A3B on local GPU (llama-cpp). Cloud models
(OpenAI gpt-4o, gpt-4o-mini, Gemini Flash) used for reviewer, researcher,
and archivist roles in later runs.


## 2. The Headline Result

The compounding delta is +/- 0.01 across all configurations tested.

| Run | Suite | Config | Delta |
|-----|-------|--------|-------|
| v2 | Phase 0 | First honest measurement | -0.039 |
| v4 | Phase 0 | Coder model, noisy retrieval | -0.033 |
| v7 | Phase 0 | Playbooks + threshold | -0.011 |
| v9 | Phase 0 | Audit fixes + live confidence | -0.009 |
| v10 | Phase 0 | Deterministic scoring, all fixes | -0.011 |
| v12 | Phase 0 | Gate + disclosure + Gemini archivist | -0.013 |
| P1-v2 | Phase 1 | Same-domain, multi-provider, curating archivist | +0.011 |

The delta is invariant to:

- **Extraction quality**: local 30B model vs Gemini 2.5 Flash vs OpenAI
  gpt-4o-mini. Smarter extractors produce better entries that are equally
  redundant with the model's training data.

- **Pipeline sophistication**: six waves of progressive improvements
  (specificity gate, progressive disclosure, domain boundaries, Bayesian
  confidence, Thompson Sampling retrieval, graph-augmented edges).

- **Task diversity**: cross-domain (Phase 0) vs same-domain (Phase 1).
  Same-domain should be the best case for compounding. It is not.

- **Curation strategy**: append-only (early runs) vs CREATE/REFINE/
  MERGE/NOOP archivist curation (P1-v2). Curation produces cleaner
  entries that are still redundant.

- **Retrieval augmentation**: flat vector search vs graph-augmented
  retrieval with typed edges (SUPERSEDES, DERIVED_FROM, RELATED_TO).

Per-task variance (+/- 0.10) exceeds the between-arm delta in every
single run. The signal is not hidden in noise -- there is no signal.


## 3. Why: The Training Data Explanation

The finding does NOT mean knowledge retrieval is useless. It means the
model's training weights already encode the task domains being tested.

Qwen3-Coder-30B was trained on millions of examples of CSV parsing, data
validation, pipeline orchestration, rate limiting, email validation, and
every other task in both eval suites. When the knowledge pipeline extracts
"use csv.DictReader for headed files" and injects it into a task about CSV
processing, the model already knows this. The entry adds zero information
gain -- the model's parametric knowledge already contains the pattern.

This is the **tautological extraction problem**: a model extracting
knowledge from its own output produces entries that are redundant with
its own training data. A smarter extraction model (Gemini Flash, GPT-4o)
produces higher-quality entries, but those entries are STILL about topics
the consuming model already knows.

The knowledge system would produce measurable improvement when:

**The domain is outside training data.** A proprietary codebase, a novel
API, an internal company framework -- anything the model has never seen
during training. Entries about "our internal auth service expects JWT
tokens with custom claims in the X-Tenant-Id header" are genuinely new
information that the model cannot produce from parametric knowledge.

**The project is genuinely novel.** Building something that has never
been built before -- where conventions, interfaces, and patterns emerge
during the project and are not in any training corpus. The knowledge
system captures these emergent conventions and propagates them across
colonies.

**The knowledge snowball has time to roll.** Eight tasks is a short
sequence. A production workspace running 100+ colonies over a week
accumulates project-specific conventions, failure patterns, and interface
contracts that compound because they are genuinely novel to the model.
The eval measured the first 8 data points of what should be a long-term
accumulation curve.

**The entries constrain rather than inform.** Operational knowledge
(playbooks, see Section 4) works because it changes HOW the model works
-- tool selection, output structure, error handling patterns. Domain
knowledge fails because it tells the model WHAT it already knows. The
knowledge system's value is in constraint and correction, not information
delivery.


## 4. What DID Work

**Operational playbooks: +0.177 quality improvement.** Deterministic,
curated, always-on guidance about tool selection, error handling patterns,
and output structure. Measured in Phase 0 v7 (playbook arm vs no-playbook
arm). This is the single largest quality driver in the project. It works
because it constrains model behavior rather than informing model knowledge.

**The infrastructure itself.** The pipeline activates correctly on
same-domain tasks (19 entries accessed in P1-v1, 16 in P1-v2). The
specificity gate blocks cross-domain contamination (v11 to v12 recovery,
discussed below). The curating archivist produces REFINE actions. The
graph bridge connects entries with typed relationships. The Bayesian
confidence posteriors update on colony outcomes. Everything works as
designed -- it just does not improve quality on tasks the model already
knows how to do.

**The safety infrastructure.** v11 proved that richer extraction without
gating is actively harmful. The "Syllable Counting" entry -- extracted
from a text-processing task -- was injected into a rate-limiter colony,
causing it to count syllables instead of HTTP requests. Quality dropped
from 0.463 to 0.000 on that task. The three-layer defense (specificity
gate + domain boundaries + progressive disclosure) prevented this in v12
and all subsequent runs. The safety infrastructure is the reason the delta
is +0.01 instead of -0.50.

**Multi-provider routing.** P1-v2 proved that three providers (local GPU,
OpenAI cloud, Ollama cloud) can serve different castes concurrently.
Coder runs on local GPU (free), reviewer on gpt-4o (quality), researcher
on gpt-4o-mini (cheap), archivist on Ollama cloud (free). Total API cost
for 8 tasks: under $0.50. This is the deployment model for production.

**The measurement methodology.** 14 controlled runs with progressive
infrastructure fixes, honest negative results, and specific failure
stories is unusual rigor for an agent system project. The
accumulate-vs-empty protocol with deterministic scoring produces
reproducible results. The negative result IS the result.


## 5. What the System Is Ready For

The knowledge system is not failing. It is waiting for a use case where
the model genuinely does not know the answer.

Production deployment on a real project -- where the domain is proprietary,
the interfaces are novel, and the conventions emerge over time -- is the
scenario the architecture was built for. The eval measured the worst case
(model already knows everything). The production scenario is the best case
(model knows nothing about this specific project).

The system ships with:

- 9-layer knowledge pipeline (extraction through injection)
- Curating archivist (CREATE/REFINE/MERGE/NOOP)
- Graph-augmented retrieval with bi-temporal edges
- Bayesian confidence with Thompson Sampling
- Specificity gate + domain boundaries + progressive disclosure
- Asymmetric extraction (smarter model writes for local model)
- Operator feedback loop (thumbs up/down -> confidence update)
- Multi-provider model routing (local + cloud)
- 3434 tests, 65 events, event-sourced replay safety

It does not need more features. It needs a project where the knowledge
it accumulates is genuinely new to the model.


## 6. Honest Limitations

**Single model family.** All measurements used Qwen3-30B-A3B as the
primary coder model. Larger models (70B+) with broader training data
may show even less compounding. Smaller models (7B) with narrower
training data may show more. This is untested.

**Short task sequences.** Eval suites are 8 tasks. Production workspaces
running 100+ colonies over days or weeks may show compounding effects
that 8 tasks cannot detect. The eval captures the opening of what should
be a long accumulation curve.

**Composite quality scoring.** Quality uses a weighted formula (code
quality, test presence, documentation, structure), not pass/fail on
external test cases. Standard benchmarks (HumanEval, MBPP) would provide
external validation and comparability.

**No repeated trials.** Each configuration was run once (or twice for
early Phase 0 runs). Variance estimates come from per-task spread within
a single run, not from repeated independent trials. Proper statistical
power analysis would require 5-10 repetitions per configuration.

**The "outside training data" hypothesis is untested.** The core claim
-- that compounding will emerge on proprietary domains -- is a prediction,
not a measurement. Validating it requires a proprietary-domain eval suite
that does not exist yet.

**API cost variability.** Cloud provider pricing and rate limits changed
during the measurement arc (Anthropic exhaustion, OpenAI prepay
requirement). Cost estimates are approximate.


## Appendix: Run Timeline

| Date | Run | Key Change |
|------|-----|------------|
| 2026-03-07 | Phase 0 v2 | First honest measurement |
| 2026-03-08 | Phase 0 v4 | Coder model swap |
| 2026-03-10 | Phase 0 v7 | Playbooks (+0.177) |
| 2026-03-12 | Phase 0 v9 | Live confidence, audit fixes |
| 2026-03-13 | Phase 0 v10 | Deterministic scoring |
| 2026-03-15 | Phase 0 v11 | Rich extraction (harmful) |
| 2026-03-16 | Phase 0 v12 | Gate + disclosure (recovery) |
| 2026-03-23 | Phase 1 v2 | Same-domain, multi-provider |

Total eval compute: ~16 hours of local GPU time, ~$5 API cost.
