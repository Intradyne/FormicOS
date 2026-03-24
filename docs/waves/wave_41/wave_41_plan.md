**Wave:** 41 -- "The Capable Colony"

**Theme:** Make FormicOS genuinely powerful at hard operator tasks by
tightening the mathematical bridges between systems that already work and by
shipping production-grade execution capability for real codebases. The product
is not a benchmark runner. The product is an editable shared brain the
operator can point at difficult work.

Wave 41 is therefore not "benchmark prep" in the narrow sense. It is the wave
that makes the Queen materially more capable on real repositories, real test
suites, and real multi-file coordination problems. If that same system can
later run a benchmark suite well, that is evidence, not identity.

This wave has two reinforcing tracks:

1. mathematical bridge-tightening
2. production capability

The single most important output is the compounding curve measured under
controlled conditions. If later tasks measurably benefit from earlier
accumulated knowledge, the thesis is real. If not, the system may still be
useful, but the strongest claim must soften.

**Prerequisite:** Wave 40 is accepted. The repo has passed its refinement wave:

- profiling-first cleanup landed
- `runner.py` has been reduced and split with `tool_dispatch.py`
- docs and protocol surfaces are more truthful
- the demo path still works
- interaction testing is materially stronger
- Wave 40 documented two known tuning gaps:
  - `_compute_knowledge_prior()` does not respect operator overlays
  - co-occurrence reinforcement does not respect operator overlays

**Contract target:** Wave 41 should avoid event expansion unless a real replay
truth blocker is discovered. The preferred path is:

- no new event types
- no benchmark-specific core path
- bounded tool-surface changes only if they are necessary for real task
  execution and remain coherent with caste policy and operator visibility

If contradiction work discovers durable state that cannot be replay-derived,
stop and justify the smallest ADR-backed contract change instead of smuggling
it into "math cleanup."

---

## Current Repo Truth At Wave Start

Wave 41 should start from the code that exists now.

### The bridge seams are real and narrow

1. **Trust seam**
   - `src/formicos/surface/trust.py` already has Bayesian `PeerTrust` with a
     mean, a conservative 10th-percentile score, asymmetric failure penalty,
     and decay.
   - But live retrieval still uses coarse status-band penalties through
     `federated_retrieval_penalty()` plus fixed hop discounting.

2. **Exploration seam**
   - `src/formicos/surface/knowledge_catalog.py` uses Thompson-style sampling
     in the retrieval composite.
   - `src/formicos/engine/context.py` still uses a UCB-style exploration bonus
     in context assembly.
   - Both are trying to solve exploration vs exploitation on the same
     underlying confidence model.

3. **Contradiction seam**
   - `src/formicos/surface/conflict_resolution.py` contains the main scoring
     heuristic for contradictions.
   - `src/formicos/surface/maintenance.py` and
     `src/formicos/surface/proactive_intelligence.py` still detect
     contradictions with lighter polarity / overlap heuristics.
   - Detection and resolution are not one coherent pipeline yet.

### The capability seams are also real

1. **Execution seam**
   - `src/formicos/adapters/sandbox_manager.py` is still Python-only.
   - `code_execute` is documented and shaped around Python snippets, not
     real repo-backed multi-language work.
   - There is no first-class workspace executor lifecycle yet.

2. **Tool seam**
   - `src/formicos/engine/tool_dispatch.py` now exists and is the natural
     place to upgrade code execution, repo operations, and structured test
     feedback.

3. **Coordination seam**
   - Parallel planning and topology routing exist.
   - Multi-file coordination is still indirect rather than explicitly file-
     aware.
   - Cross-file consistency validation is not yet a first-class success path.

4. **Measurement seam**
   - Wave 37 / 38 already produced internal benchmark and profiling harnesses.
   - `tests/benchmark/profiling_harness.py` now exists and can be extended.
   - There is not yet a sequential task runner that measures compounding over
     many tasks in the same workspace under locked conditions.

### Current hotspot sizes relevant to Wave 41

| File | Lines | Why it matters now |
|------|-------|--------------------|
| `src/formicos/engine/runner.py` | 1908 | validator registration, round execution, topology bridge |
| `src/formicos/engine/tool_dispatch.py` | 383 | natural seam for execution-surface expansion |
| `src/formicos/surface/colony_manager.py` | 1597 | colony lifecycle and future workspace-executor ownership |
| `src/formicos/surface/knowledge_catalog.py` | 908 | trust weighting and retrieval scoring seam |
| `src/formicos/engine/context.py` | 574 | UCB-style exploration seam |
| `src/formicos/surface/conflict_resolution.py` | 115 | contradiction-resolution starting point |
| `src/formicos/surface/trust.py` | 123 | continuous trust weighting seam |
| `src/formicos/adapters/sandbox_manager.py` | 156 | current Python-only execution limit |
| `src/formicos/surface/proactive_intelligence.py` | 1623 | cost / learning / recommendation surfaces |

---

## Why This Wave

By the end of Wave 40, FormicOS should be clean enough that future failures
mean something real. Wave 41 is where the system earns the claim that it can
handle hard work, not just explain itself well.

That requires two things at once:

1. the math systems must stop disagreeing with each other at key seams
2. the execution substrate must support real coding workflows rather than
   mostly synthetic or Python-only flows

The product story that Wave 41 supports is:

- the live demo works because the Queen can genuinely do hard work
- the benchmark demo is meaningful because the same system can tackle public
  suites without a benchmark-only core path
- the audit demo stays meaningful because all of this remains inspectable

Wave 41 therefore builds capability without letting benchmark pressure become
the center of gravity.

---

## Track A: Mathematical Bridge-Tightening

These upgrades should replace heuristics where good local math already exists
on both sides of the seam.

### A1. Continuous Beta trust weighting in retrieval

Current problem:

- Bayesian peer trust exists in `trust.py`
- retrieval still collapses it into coarse fixed bands and fixed hop decay

Wave 41 should replace the live retrieval penalty path with a continuous trust
weight grounded in the peer posterior, while preserving the qualitative
backward-compatible behavior that local truth should still dominate weak
federated truth.

Expected direction:

- derive retrieval weight from posterior mean with uncertainty penalty
- replace fixed hop discounting with trust-informed hop discounting
- preserve the local-first retrieval outcome that Wave 38 hardened

Primary seams:

- `src/formicos/surface/trust.py`
- `src/formicos/surface/knowledge_catalog.py`

### A2. TS / UCB confidence-term unification

Current problem:

- retrieval uses Thompson-style sampling
- context assembly uses a UCB-style bonus
- both operate on the same confidence substrate with different exploration math

Wave 41 should introduce one shared confidence / exploration helper and route
both paths through it. This does not mean replacing the full composite formulas
in either path. It means replacing the exploration-confidence term inside each
composite so the system stops speaking two dialects of uncertainty.

Primary seams:

- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/engine/context.py`
- a new shared scoring helper module if justified

### A3. Contradiction pipeline overhaul (staged)

This is the weakest mathematical seam in the repo, but the first problem is
plumbing, not fancy fusion.

Wave 41 should stage this work aggressively:

1. **Stage 1: unify detection**
   - one contradiction detector path
   - classify contradiction vs complement vs temporal update

2. **Stage 2: unify resolution API**
   - one resolution entry point used by maintenance and intelligence surfaces

3. **Stage 3: hypothesis-aware retrieval / display policy**
   - stop forcing weak winner-take-all where evidence is genuinely close

4. **Stage 4: richer Bayesian fusion**
   - only after the pipeline is coherent

Wave 41 should aim to land Stages 1-2 as must-ship, with Stages 3-4 depending
on stability and evidence.

Primary seams:

- `src/formicos/surface/conflict_resolution.py`
- `src/formicos/surface/maintenance.py`
- `src/formicos/surface/proactive_intelligence.py`
- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/surface/projections.py` only if projection truth truly needs it

### Track A discipline

Wave 41 should not overreach here.

- Trust weighting is the cleanest single-file math win.
- TS / UCB unification is bounded and should land early.
- Contradiction work should not sprawl into a whole-knowledge redesign.

---

## Track B: Production Capability

These upgrades should make the Queen meaningfully better at real code work.

### B1. Production-grade execution surface

Current problem:

- the sandbox is Python-only
- `code_execute` is still shaped like a snippet executor, not a repo worker
- there is no clear separation between workspace lifecycle and sandbox lifecycle

Wave 41 should distinguish:

1. **workspace executor**
   - repo checkout / copy / lifecycle
   - working directory setup and cleanup
   - git-aware operations if justified

2. **sandbox executor**
   - bounded code / test execution
   - resource limits
   - isolated process behavior

The key product requirement is not "support benchmarks." It is "support real
repo-backed work cleanly."

Expected capabilities:

- repo-aware working directory handling
- language-aware test execution
- structured test failure feedback rather than raw stderr only
- stronger cleanup and isolation discipline

Primary seams:

- `src/formicos/adapters/sandbox_manager.py`
- `src/formicos/engine/tool_dispatch.py`
- `src/formicos/surface/colony_manager.py`

### B2. Multi-file task coordination

Current problem:

- planning and topology exist
- file-aware decomposition is still weak
- cross-file consistency validation is not a first-class success path

Wave 41 should make multi-file work a real strength by improving:

- file-aware decomposition
- propagation of file/dependency knowledge through the substrate
- validation that checks whole-task consistency rather than isolated fragments

Primary seams:

- `src/formicos/surface/queen_runtime.py`
- `src/formicos/engine/runner.py`
- `src/formicos/surface/colony_manager.py`
- knowledge-extraction / retrieval surfaces where codebase structure becomes
  reusable knowledge

### B3. Compounding-curve infrastructure

This is the most important measurement output of the wave.

Wave 41 should build a sequential task runner that:

- runs many tasks in the same workspace
- allows knowledge to persist across tasks
- measures at least three curves:
  - raw performance over sequence
  - cost-normalized improvement
  - time-normalized improvement

The experiment conditions must be locked enough that the result is credible.

At minimum, lock or record:

- task order
- model mix
- budget policy
- escalation policy
- random seed or other stochastic controls where practical

Primary seams:

- `tests/benchmark/`
- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/surface/proactive_intelligence.py`
- evaluation helpers already present in `src/formicos/eval/`

### B4. Cost optimization

Wave 41 capability work should also reduce the chance that gains are only
coming from uncontrolled spend.

Expected areas:

- tier-aware routing
- better use of escalation budget
- prompt / context reuse where practical
- early stopping when evidence says additional rounds are not paying off

This is subordinate to measurement truth, not a substitute for it.

---

## Priority Order (cut from the bottom)

| Priority | Item | Track | Class |
|----------|------|-------|-------|
| 1 | continuous trust weighting in retrieval | A1 | Must |
| 2 | TS / UCB confidence-term unification | A2 | Must |
| 3 | contradiction pipeline Stage 1-2 | A3 | Must |
| 4 | production-grade execution surface | B1 | Must |
| 5 | multi-file coordination + cross-file validation | B2 | Must |
| 6 | compounding-curve runner with locked conditions | B3 | Must |
| 7 | cost-normalized and time-normalized reporting | B3 | Must |
| 8 | cost optimization pass | B4 | Should |
| 9 | contradiction pipeline Stage 3 | A3 | Should |
| 10 | contradiction pipeline Stage 4 | A3 | Stretch |

---

## Team Assignment

### Team 1: Math Bridges

Owns Track A early priorities:

- continuous trust weighting
- TS / UCB unification
- contradiction pipeline Stage 1-2

Primary files:

- `src/formicos/surface/trust.py`
- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/engine/context.py`
- `src/formicos/surface/conflict_resolution.py`
- `src/formicos/surface/maintenance.py`
- `src/formicos/surface/proactive_intelligence.py`

### Team 2: Execution + Multi-file Capability

Owns the execution and coordination substrate:

- production-grade execution surface
- workspace vs sandbox executor separation
- multi-file coordination
- cross-file validation

Primary files:

- `src/formicos/adapters/sandbox_manager.py`
- `src/formicos/engine/tool_dispatch.py`
- `src/formicos/engine/runner.py`
- `src/formicos/surface/colony_manager.py`
- `src/formicos/surface/queen_runtime.py`

### Team 3: Measurement + Optimization

Owns the evidence layer:

- compounding-curve runner
- locked-condition measurement
- cost / performance reporting and optimization
- later contradiction scoring work only after Team 1 stabilizes the pipeline

Primary files:

- `tests/benchmark/`
- `src/formicos/eval/`
- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/surface/proactive_intelligence.py`

### Overlap

Overlap is real in Wave 41 and must be acknowledged.

- `knowledge_catalog.py` is shared between Team 1 and Team 3.
  - Team 1 owns trust-math and retrieval-confidence changes.
  - Team 3 owns measurement and reporting additions.
  - Reread before merge.
- `proactive_intelligence.py` is shared between Team 1 and Team 3.
  - Team 1 owns contradiction-related use sites if needed.
  - Team 3 owns measurement / optimization surfaces.
- `runner.py` is shared between Team 1 and Team 2.
  - Team 1 owns confidence / contradiction-adjacent seams.
  - Team 2 owns execution / validation capability changes.

Wave 41 will need more deliberate seam rereads than Wave 40 did.

---

## What Wave 41 Does Not Include

- no benchmark-specific core path
- no public-proof narrative work
- no assumption that advanced stagnation math must land now
- no automatic contradiction redesign beyond what the staged pipeline justifies
- no identity drift into "benchmark runner"

Wave 41 is about capability. Wave 42 will validate and publish what this wave
actually builds.

---

## Smoke Test

1. trust weighting and exploration unification land without retrieval regressions
2. contradiction detection and resolution use one coherent pipeline
3. repo-backed execution works under controlled conditions
4. multi-file work can be planned, executed, and validated coherently
5. the compounding-curve runner exists and measures all three curves
6. experimental conditions are explicit enough that the measurement is
   publishable regardless of result
7. full CI remains clean

---

## After Wave 41

FormicOS should be more capable in three ways:

1. **retrieval trust** -- the confidence and trust math flows through the live
   retrieval path more honestly
2. **execution trust** -- the Queen can work against real repo-backed tasks,
   not just snippet-shaped coding work
3. **learning evidence** -- the system can measure whether it actually gets
   better across sequential tasks

That is the system Wave 42 should validate and publish. Wave 42 should not
become another large implementation wave by default. It should demonstrate and
measure what Wave 41 really built.
