**Wave:** 42 -- "The Intelligent Colony"

**Theme:** Synthesize the strongest remaining research insights into live
code, but only where they attach to clear existing seams in the current
system. This is not a research buffet and it is not a measurement wave. It is
the last major research-to-code wave: replace the weakest justified
heuristics, add the highest-leverage non-LLM intelligence, and leave the
system materially stronger than Wave 41 without turning it into a benchmark
special case.

The governing discipline for Wave 42 is simple:

- keep the work grounded in the actual Wave 41 substrate
- keep first versions simple where a simple version already beats the current
  heuristic
- use small developmental evals to confirm a change helped before calling it
  "intelligence"

Wave 42 is still a build wave. Wave 43 hardens. Wave 44 proves.

**Prerequisite:** Wave 41 is accepted. In particular:

- continuous trust weighting, TS/UCB unification, and contradiction
  classification are live
- workspace execution and multi-file targeting are reachable through the
  canonical colony path
- the sequential runner and compounding-curve infrastructure exist, but they
  are not the center of this wave

**Contract target:** Wave 42 should stay additive and bounded.

- no new event types unless a real replay-truth blocker is proven
- no new Queen tools unless static analysis or workspace intelligence truly
  needs one
- existing heuristic behavior remains the fallback when new intelligence inputs
  are absent
- no benchmark-specific core path

If a proposed upgrade cannot degrade gracefully to the pre-Wave-42 path, it is
probably too large for this wave.

**Architectural constraint (from hardening research):** Every Wave 42
execution or workspace feature must be compatible with a future per-language
container backend and stronger sandbox runtime (Sysbox, gVisor). Do not assume
the current Docker socket pattern is permanent. Wave 43 will migrate to Sysbox
and per-language slim images; nothing built in Wave 42 should make that harder.

---

## Current Repo Truth At Wave Start

Wave 42 should start from the current codebase, not from the research notes.

### The strongest remaining weak seams are visible in code

1. **Topology prior seam**
   - `_compute_knowledge_prior()` still lives in
     `src/formicos/engine/runner.py`.
   - It still maps knowledge to agent affinity mostly through domain-name
     overlap between retrieved entry domains and caste / recipe names.
   - This is the weakest remaining bridge between knowledge and topology.

2. **Contradiction resolution seam**
   - `classify_pair()` and `detect_contradictions()` now exist in
     `src/formicos/surface/conflict_resolution.py`.
   - `resolve_conflict()` still uses the older linear evidence/recency/
     provenance scorer.
   - Classification is ahead of resolution.

3. **Static structure seam**
   - there is no `src/formicos/adapters/code_analysis.py`
   - there is no cheap structural workspace intelligence layer for imports,
     test-file relationships, or function/class inventory
   - the colony still burns LLM context to understand code structure it could
     infer cheaply

4. **Adaptive runtime-control seam**
   - branching diagnostics already exist in
     `src/formicos/surface/proactive_intelligence.py`
   - pheromone evaporation in `src/formicos/engine/runner.py` is still fixed
     via `_EVAPORATE = 0.95`
   - the runtime does not yet adapt its exploration pressure based on
     stagnation state

5. **Extraction quality seam**
   - memory extraction and confidence-update hooks already exist in
     `src/formicos/surface/colony_manager.py`
   - prediction-error and staleness signals already exist in
     `maintenance.py`, `knowledge_catalog.py`, and
     `proactive_intelligence.py`
   - extraction quality is still more permissive than the current substrate
     probably deserves

### Current hotspots relevant to Wave 42

| File | Lines | Why it matters now |
|------|-------|--------------------|
| `src/formicos/engine/runner.py` | 2134 | topology prior and pheromone update both live here |
| `src/formicos/surface/colony_manager.py` | 1636 | extraction hooks, lifecycle wiring, future workspace analysis handoff |
| `src/formicos/surface/proactive_intelligence.py` | 1739 | branching and staleness diagnostics already exist |
| `src/formicos/surface/knowledge_catalog.py` | 958 | retrieval surfacing and hypothesis display seam |
| `src/formicos/adapters/sandbox_manager.py` | 386 | workspace execution substrate exists but is still young |
| `src/formicos/surface/conflict_resolution.py` | 304 | contradiction upgrade seam |

### Current test shape relevant to Wave 42

- unit test surface is already large and should absorb targeted new math and
  analysis tests cleanly
- integration and benchmark seams now exist and can support small
  before/after developmental evals
- Wave 42 should add targeted evals for each pillar, not a new public-proof
  harness

### Research validation (grounded findings only)

Recent research confirms the approaches in this plan:

- Python `ast` parsing achieves 0.5-2ms per file on typical 200-500 line
  files, well within the sub-100ms target (Gauge.sh measurements).
- Regex-based multi-language import extraction achieves 90-95% accuracy on
  standard static imports across JS/TS, Go, Rust, Java, C++ (community
  benchmarks).
- Test-to-source naming heuristics achieve 70-80% accuracy alone, rising to
  85-92% when combined with import analysis (traceability literature).
- RepoGraph (ICLR 2025) showed 32.8% relative improvement on SWE-bench from
  structural context alone -- the strongest quantitative evidence for
  Pillar 1.
- Aider's proven repo map pattern: file inventory + function/class signatures
  + dependency edges, ranked by relevance, budgeted to ~1K tokens per agent.
- Mavrovouniotis & Yang (2013, 20+ papers) proved adaptive evaporation
  consistently outperforms any fixed rate across dynamic environments --
  directly validates Pillar 4.
- ExpeRepair ablation (47.7% vs 41.3% without experience, June 2025) proves
  knowledge accumulation genuinely improves agent performance -- validates
  the extraction quality investment in Pillar 5.

---

## Why This Wave

By the end of Wave 41, FormicOS should already be capable. Wave 42 is about
making that capability more intelligent without changing the product identity.

The system still has three clear kinds of avoidable token burn or heuristic
weakness:

1. it uses string matching where structural workspace intelligence could do
   better
2. it classifies contradictions more cleanly than it resolves them
3. it observes stagnation but does not yet adapt its runtime control law in
   response

Wave 42 should close those gaps and no more.

The success condition is not "better benchmark numbers." The success condition
is:

- the colony understands code structure more cheaply
- the topology prior is less embarrassing and more justified
- contradiction handling respects its own classification
- runtime exploration pressure responds more intelligently to stagnation
- extracted knowledge becomes cleaner input to later waves

---

## Pillar 1: Static Workspace Analysis

This is the highest-leverage non-LLM upgrade in the current roadmap.
RepoGraph (ICLR 2025) demonstrated a 32.8% relative improvement on SWE-bench
from providing structural context to agents. The key finding: "without grasp of
global repository structures, agents tend to focus narrowly on specific files,
resulting in local optimums."

### 1A. Lightweight structural analysis

Build a small workspace analysis adapter that can cheaply derive:

- import / dependency relationships
- top-level function and class inventory (names and rough signatures)
- rough file-role classification:
  - source
  - test (with test-to-source mapping via naming + import analysis)
  - config
  - docs

The first version should stay deliberately lightweight:

- Python: stdlib `ast` (0.5-2ms per file, zero external dependencies)
- JavaScript / TypeScript: import/export regex (90%+ accuracy on static
  imports; known gaps: dynamic imports, conditional requires, template
  literal edge cases)
- Go: import block parsing (highly regex-friendly due to structured syntax)
- Rust: `use` statement parsing (best-effort, similar accuracy profile)

This is not a tree-sitter wave. The goal is 80-95% useful structure at tiny
cost. Known regex gaps (dynamic imports, macro-based includes) are accepted
and documented, not chased.

### 1B. Workspace-scoped structural substrate

Structural facts should not be bulk-dumped into the main knowledge substrate by
default. The risk is turning the knowledge base into a noisy repository mirror.

Preferred order:

1. workspace-scoped structural index / derived substrate
2. selective promotion of the most useful structural facts into ephemeral
   knowledge entries only where doing so improves retrieval

Examples of acceptable structural facts:

- file A imports from file B
- file A is likely a test companion for file B (naming heuristic + import
  verification achieves 85-92% accuracy)
- file A defines class Z and function Y

The default storage target should remain local to the workspace and task
context unless there is a clear reason to promote.

**Token budget discipline:** Following Aider's proven repo map pattern, budget
structural context to approximately 1-2K tokens per agent. Rank structural
facts by relevance to the current task (dependency distance from the target
files, not just all available structure). This prevents structural noise from
competing with actual task content in the context window.

### 1C. Multi-file coordination integration

The Queen and colony path should be able to consume this structure for
multi-file work:

- planning can see likely file dependencies
- cross-file validation can inspect import-chain consistency
- later topology work can use structural relationships rather than string
  overlap

### 1D. Forward compatibility constraint

All structural analysis must operate on the workspace tree as it currently
exists in the filesystem. Do not assume a specific repository lifecycle
(clone, branch, etc.) as the defining anchor. If the workspace came from a
git clone, that is incidental. The analysis reads files from a directory; it
does not own the directory's lifecycle.

The analysis must also work regardless of the underlying execution backend.
Wave 43 will introduce per-language sandbox containers and stronger isolation.
Nothing in the structural analysis path should depend on direct filesystem
access from the backend process to the sandbox filesystem; prefer analysis
that runs on the workspace tree before sandbox dispatch.

### Developmental eval

Run a small before/after comparison on real multi-file tasks:

- with structural analysis disabled
- with structural analysis enabled

Check:

- did the colony identify the relevant file set more accurately?
- did it reduce obvious "read the whole codebase with the LLM" behavior?
- did it catch import-chain breakage earlier?
- was the structural context budget (~1-2K tokens) sufficient or too tight?

### Primary seams

- `src/formicos/adapters/code_analysis.py` (new)
- `src/formicos/surface/colony_manager.py`
- optionally a small workspace-structure helper or read model in surface
- tests in `tests/unit/adapters/` and `tests/integration/`

---

## Pillar 2: Structural Topology Prior

Replace the weakest remaining topology bridge with the simplest stronger one.

### 2A. Structural prior v1

The first version should be simple:

- use structural dependency relationships from Pillar 1 when they exist
- fall back to neutral when they do not

That means:

- no embedding-affinity bridge in v1
- no asymmetric edge weighting in v1
- no complicated learning loop in v1

If agent or task context indicates that two active file scopes are connected by
an import / dependency relationship, use that to bias the corresponding
topology edge prior. Otherwise return the existing neutral path.

The prior should remain bounded and modest. The pheromone system still does the
real adaptation work. The structural prior just gives the system a better
starting point so it wastes fewer rounds correcting a bad initial topology.

### 2B. Optional second-order prior work

Only if v1 is clearly too weak or too noisy:

- stronger structural weighting
- richer dependency classes
- later asymmetric weighting if the simple symmetric structural prior still
  leaves obvious pathologies

Do not start with this.

### Developmental eval

Compare old vs new prior on repeated-domain or repeated-codebase tasks:

- how many rounds until the colony settles into a useful topology?
- how often does the new prior save a correction round?
- does it reduce obviously bad initial communication patterns?

### Primary seams

- `src/formicos/engine/runner.py`
- `src/formicos/engine/strategies/stigmergic.py` only if the application point
  really requires it
- tests in `tests/unit/engine/`

---

## Pillar 3: Contradiction Resolution Upgrade

Wave 41 landed classification. Wave 42 should make resolution respect that
classification.

### 3A. Stage 2 resolution upgrade (Must)

Upgrade `resolve_conflict()` so that it does not ignore the relation type
already produced by `classify_pair()`.

Expected behavior:

- **contradiction**
  - resolve using a cleaner confidence-aware scorer than the current
    linear heuristic
  - use posterior-aware evidence (Beta mean instead of raw observation count)
    and better temporal handling where practical
- **complement**
  - do not resolve into a winner
  - keep both and link them as complementary (co-occurrence link so retrieval
    surfaces them together)
- **temporal_update**
  - treat as update, not contradiction
  - preserve the older item as historical truth where appropriate
  - use bi-temporal metadata if available (Wave 38 knowledge graph has
    `valid_at`/`invalid_at`)

This is the real Must-ship contradiction upgrade for Wave 42.

### 3B. Stage 3 competing-hypothesis surfacing (Should)

If the resolution path still produces competing outcomes after the Stage 2
upgrade, the retrieval and projection layers may optionally surface that more
explicitly:

- competing links in projection state
- retrieval note that one entry has a competing alternative
- operator-visible context that there is unresolved tension

This is useful, but it touches more surfaces than it looks (retrieval,
projections, operator UX, possibly audit surfaces, documentation). It is
Should-level, not Must-ship. If it threatens to sprawl, defer it rather than
rushing it.

### Developmental eval

Build a small contradiction fixture set and compare:

- contradiction pairs
- complement pairs
- temporal-update pairs

Verify that the upgraded path produces the right class-specific behavior and
that operator-facing truth is more legible.

### Primary seams

- `src/formicos/surface/conflict_resolution.py`
- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/surface/projections.py` only if Stage 3 lands
- `src/formicos/surface/proactive_intelligence.py`

---

## Pillar 4: Adaptive Evaporation

This is a runtime-control upgrade, not a reporting feature. Research (20+
papers from Mavrovouniotis & Yang, EvoSTOC 2013) proves adaptive evaporation
consistently outperforms any fixed rate across dynamic environments.

### 4A. Runtime-local adaptive evaporation

Keep the control logic inside `runner.py`.

Use the same branching concepts already proven useful in diagnostics, but do
not make runtime behavior depend directly on briefing/reporting code.

**Critical layer constraint:** Engine cannot import from surface. The branching
factor computation (`exp(entropy)` over pheromone edge weights) must be
re-implemented as a runner-local helper function, not imported from
`proactive_intelligence.py`. The concept is the same; the code is duplicated
across the layer boundary. This is architecturally correct.

The first version should:

- detect healthy vs narrowing vs stagnating exploration state using the
  runner-local branching factor
- adjust evaporation within a small bounded range
- remain understandable and reversible
- preserve the current fixed-rate behavior as the default when no stagnation
  signal is present

### 4B. Optional smoothing and reinforcement-mode changes

If adaptive rate alone is not enough:

- add bounded pheromone smoothing under strong stagnation
- optionally switch reinforcement emphasis toward more recent useful edges
  (iteration-best vs global-best)

These are Should-level runtime refinements, not automatic Must-ship work.

### Developmental eval

Run a small set of tasks known to exhibit stagnation-like behavior and compare:

- fixed evaporation
- adaptive evaporation

Check whether the colony escapes repetitive low-value patterns faster without
destabilizing healthy runs.

### Primary seams

- `src/formicos/engine/runner.py`
- tests in `tests/unit/engine/`

---

## Pillar 5: Extraction Quality Gating

Better knowledge quality is still a multiplier on every later wave. The
ExpeRepair ablation (47.7% vs 41.3% without accumulated experience) proves
that knowledge accumulation genuinely helps -- but only if the accumulated
knowledge is clean.

### 5A. Conjunctive quality gates

Extraction quality should improve, but the gate must not be blunt.

Prefer conjunctions such as:

- short **and** low novelty
- short **and** low structural specificity
- highly duplicative **and** weakly differentiated
- low-value output from weak or escalated runs where the extracted content adds
  little

Do not use "short alone" as a universal demotion rule. Some short entries are
genuinely high-value.

### 5B. Structural context for domain inference

If Pillar 1 lands well, structural workspace context may improve domain tagging
for extracted entries:

- file-role hints
- dependency neighborhood
- likely test/source pairing

This should remain supportive metadata, not a full replacement for content
understanding.

### Developmental eval

Check whether the gated path reduces duplicate or obviously noisy entries
without suppressing genuinely useful concise knowledge.

### Primary seams

- `src/formicos/surface/colony_manager.py`
- `src/formicos/surface/admission.py`
- tests in `tests/unit/surface/`

---

## Priority Order (cut from the bottom)

| Priority | Item | Pillar | Class |
|----------|------|--------|-------|
| 1 | lightweight static workspace analysis | 1 | Must |
| 2 | structural substrate integration for multi-file work | 1 | Must |
| 3 | structural topology prior v1 | 2 | Must |
| 4 | contradiction Stage 2 resolution upgrade | 3 | Must |
| 5 | runtime-local adaptive evaporation | 4 | Must |
| 6 | conjunctive extraction quality gating | 5 | Should |
| 7 | contradiction Stage 3 competing-hypothesis surfacing | 3 | Should |
| 8 | adaptive smoothing / reinforcement refinements | 4 | Should |
| 9 | structural-assisted domain inference | 5 | Should |
| 10 | richer structural weighting beyond v1 | 2 | Stretch |

---

## Team Assignment

### Team 1: Static Analysis + Topology

Owns:

- Pillar 1
- Pillar 2

Primary files:

- `src/formicos/adapters/code_analysis.py`
- `src/formicos/engine/runner.py` (`_compute_knowledge_prior` seam)
- `src/formicos/surface/colony_manager.py` for structural-analysis integration
- optional workspace-structure helper / read model files

### Team 2: Contradiction + Extraction

Owns:

- Pillar 3
- Pillar 5

Primary files:

- `src/formicos/surface/conflict_resolution.py`
- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/surface/projections.py` if Stage 3 lands
- `src/formicos/surface/proactive_intelligence.py`
- `src/formicos/surface/colony_manager.py` extraction hooks
- `src/formicos/surface/admission.py`

### Team 3: Adaptive Runtime Control

Owns:

- Pillar 4
- any bounded runtime-local refinements that support it

Primary files:

- `src/formicos/engine/runner.py` (`_update_pheromones` seam)
- `tests/unit/engine/`

### Overlap

Wave 42 has two important overlap seams:

- `src/formicos/engine/runner.py`
  - Team 1 owns `_compute_knowledge_prior`
  - Team 3 owns `_update_pheromones`
  - these seams are distant (~89 lines apart) and should remain that way

- `src/formicos/surface/colony_manager.py`
  - Team 1 owns structural-analysis integration methods
  - Team 2 owns `_hook_memory_extraction`, `extract_institutional_memory`,
    `_check_inline_dedup`, and extraction-quality changes
  - ownership is method-level; do not blur it; reread before merge

---

## What Wave 42 Does Not Include

- no new event families unless a real replay blocker is proven
- no benchmark runs or public-proof work
- no Docker hardening or deployment packaging (Wave 43 owns that)
- no learned routing from outcome history
- no convergence prediction model
- no Rodriguez governance constraints
- no submodular context optimizer
- no large retrieval redesign beyond contradiction-stage consequences
- no Sysbox migration (Wave 43)
- no per-language sandbox images (Wave 43)
- no hierarchical budget tracking (Wave 43)

Wave 42 is the last major research-to-code wave, not the first public-proof
wave. Wave 43 is the production architecture wave. Wave 44 is the proof wave.

---

## Smoke Test

1. lightweight structural analysis works on at least Python plus two additional
   common languages
2. structural workspace facts are available to multi-file work without
   polluting the main knowledge substrate by default
3. structural context is budgeted to approximately 1-2K tokens per agent
4. `_compute_knowledge_prior()` uses structural dependency information when it
   exists and falls back cleanly when it does not
5. contradiction resolution respects contradiction vs complement vs temporal
   update
6. adaptive evaporation changes runtime behavior under stagnation without
   breaking the normal path
7. adaptive evaporation uses a runner-local branching factor, not an import
   from proactive_intelligence.py
8. extraction quality gating reduces obvious low-value knowledge without
   suppressing concise useful entries
9. targeted developmental evals are documented for each landed pillar
10. no Wave 42 feature depends on direct Docker socket access or assumes the
    current sandbox isolation model is permanent
11. full CI remains clean

---

## After Wave 42

FormicOS should be more intelligent in four ways:

1. **structural intelligence** -- it understands code and workspace structure
   more cheaply
2. **topology intelligence** -- its initial communication prior is no longer
   driven mainly by string overlap
3. **epistemic intelligence** -- contradiction handling respects its own
   classification and treats updates and complements differently
4. **runtime intelligence** -- exploration pressure responds to stagnation
   more intelligently than a fixed evaporation rate can

Wave 43 hardens this system for deployment. The hardening research gives
Wave 43 a concrete production architecture spine:

- Sysbox migration to eliminate Docker socket trust
- SQLite WAL deployment rules with Litestream backup
- per-language slim sandbox images with warm-pool pre-pulling
- hierarchical event-sourced budget tracking
- OpenTelemetry / Langfuse observability
- git clone and supply chain security defenses
- deployment docs, runbooks, and capacity planning

Wave 44 proves the hardened system with disciplined measurement: SWE-Bench-CL
forward transfer metrics, paired empty-vs-accumulated comparisons, bootstrap
confidence intervals, and three public demos (live, benchmark, audit).
