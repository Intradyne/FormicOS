**Wave:** 46 -- "The Proven Colony"

**Theme:** Make the system visible, operable, and measurably honest.
Product coherence first, measurement second. Every change in this wave
must pass one test:

**"Would a real operator want this even if no benchmark existed?"**

This is not a hard code freeze. It is a **no unearned features** wave.
The eval layer gets real engineering work. The product gets bounded
improvements when measurement exposes a genuine weakness that affects
arbitrary operator tasks too. Nothing ships that only exists to score well.

**Identity guard:**

- no benchmark-only core paths
- no task-specific hacks
- no one-off heuristics for a suite
- no event growth
- no new subsystem or adapter sprawl
- no architecture rewrites

**Prerequisite:** Wave 45 accepted, with Wave 45.5 loose-end cleanup landed.
The post-45.5 system includes:

- proactive foraging wired through maintenance dispatch
- competing-hypothesis surfacing through replay-derived projection state
- source-credibility-aware admission for forager entries
- 62 events in the closed union
- 33 frontend components
- 211 Python test files
- reactive + proactive + operator-triggered forager modes in the service path
- EgressGateway plus L1/L2 fetch pipeline with domain strategy memory
- BudgetEnforcer wired into colony spawn and model routing

**Current product gaps (not benchmark gaps):**

1. The Forager is still mostly invisible to operators.
   The service and projection state exist, but there is no real operator
   surface for manual trigger, domain override, cycle history, or domain
   strategy visibility.
2. Web-sourced knowledge still does not read as web-sourced knowledge in the UI.
   The metadata exists in entry dicts, but the operator does not see a clear
   web-source badge or source details in normal use.
3. The OTel adapter exists but is not wired into the app startup path.
4. Search still bypasses the full EgressGateway policy surface.
5. The eval harness still has three integrity gaps:
   workspace reuse across runs, empty `knowledge_used`, and thin conditions.
6. The task suite is still only 7 tasks in 1 suite.

**Contract:**

- no new event types (union stays at 62)
- no new adapters or subsystems
- no benchmark-specific product path
- product improvements are allowed when they pass the operator test
- the eval layer can grow substantially

---

## Why This Wave Exists

The system is now capable, hardened, and foraging. The next risk is drift:
either FormicOS becomes a benchmark-runner showcase with debt that only
exists to score well, or it becomes a product that is also measured honestly.

Wave 46 chooses the second path.

That means:

- the Forager becomes visible and operable for real people
- the measurement layer becomes credible enough to support publication
- small product improvements are allowed when the data proves they matter
- benchmark success is treated as a demonstration of product capability,
  not the reason for the product to exist

The wave shape is:

**measure -> analyze -> fix what generalizes -> re-measure -> publish what's true**

---

## Current Repo Truth At Wave Start

Grounded against the live post-Wave-45.5 tree:

### What exists

1. **Forager service loop is live.**
   Reactive handoff runs from retrieval into `ForagerService`. Proactive
   foraging runs from the maintenance loop through `MaintenanceDispatcher`.
2. **Forager projection state exists.**
   `ForageCycleCompleted`, `DomainStrategyUpdated`, and
   `ForagerDomainOverride` are replayed into projection state.
3. **Forager provenance exists in knowledge entries.**
   Entries store `source_url`, `fetch_timestamp`, `forager_query`,
   `source_domain`, `source_credibility`, and related metadata.
4. **Competing hypotheses are surfaced in retrieval.**
   Replay-derived competing pairs are rebuilt lazily and retrieval can expose
   `competing_with` context.
5. **Egress + fetch substrate is real.**
   Strict egress, robots handling, L1/L2 extraction, and domain strategy
   memory are all live.
6. **Eval harness exists but is still thin.**
   Sequential runner, compounding curve, and comparison tooling exist under
   `src/formicos/eval/`, but with only 7 tasks and 1 suite.

### What does not exist yet

1. No operator-facing Forager API surface.
2. No clear frontend differentiation for web-sourced knowledge.
3. No OTel sink wiring in app startup.
4. No full search-through-egress policy cohesion.
5. No clean-room run isolation in the sequential runner.
6. No populated `knowledge_used` attribution in eval output.
7. No run manifest strong enough for publication-grade reporting.
8. No 50+ task proof suite.

---

## Pillar 1: Forager Operator Surface

The Forager is FormicOS's newest and most distinctive subsystem. Right now it
operates mostly in the dark. That is a product coherence problem, not a
benchmark issue.

### 1A. Forager API endpoints -- Must

Add operator-facing HTTP routes for the existing forager/service truth:

- `POST /api/v1/workspaces/{ws}/forage`
  Manual forage trigger. Accepts `{topic, domains, context}` or equivalent.
  Uses operator-trigger mode in the existing Forager service path.
- `POST /api/v1/workspaces/{ws}/forager/domain-override`
  Thin wrapper over `ForagerDomainOverride` for `trust`, `distrust`, `reset`.
- `GET /api/v1/workspaces/{ws}/forager/cycles`
  Returns forage cycle summaries from projection state.
- `GET /api/v1/workspaces/{ws}/forager/domains`
  Returns domain strategy state plus operator overrides.

These are thin wrappers. The service and projection truth already exist.

### 1B. Knowledge entry web-source visibility -- Must

When an entry contains forager provenance, the operator should see that
immediately in the normal knowledge UI:

- "Web Source" badge or equivalent indicator
- source URL
- fetch timestamp
- forager query
- source credibility tier
- extraction quality score

The metadata already exists on the entry dict. This is a frontend truth pass,
not a data-model change.

### 1C. Forager activity in briefing surfaces -- Should

The proactive briefing should show bounded recent Forager activity when it
exists:

- recent forage cycles
- entries proposed vs admitted
- recent domain strategy changes
- domains currently trusted/distrusted by the operator

This strengthens the operator story without creating a new subsystem.

### Primary seams

- `src/formicos/surface/routes/api.py` or a bounded `forager_api.py`
- `frontend/src/components/knowledge-browser.ts`
- `frontend/src/components/proactive-briefing.ts`
- tests for new routes and surfaced metadata

---

## Pillar 2: Observability And Policy Cohesion

### 2A. Additive OTel wiring -- Must

`telemetry_otel.py` exists but is not added to the telemetry bus in `app.py`.

Wire it in as an additive optional sink:

- keep JSONL as the simple always-available path
- add OTel when enabled by env/config
- do not turn this into a telemetry redesign

This helps real operators debug runs, demos, and production issues.

### 2B. Search-through-egress consistency -- Should

Search should move closer to the same outbound policy story as fetch:

- reuse existing search adapter interface
- avoid a new search subsystem
- keep the distinction honest:
  search endpoints like DDG/Serper are not fetched pages, so this is about
  shared identity/policy/cohesion, not pretending the semantics are identical

This is a product coherence and security-story improvement.

### Primary seams

- `src/formicos/surface/app.py`
- any bounded tests around telemetry startup and search client wiring

---

## Pillar 3: Eval Harness Integrity

These changes make measurement credible. They also improve demo
reproducibility and causal auditability for normal operator use.

### 3A. Clean-room run isolation -- Blocker / Must

The sequential runner currently reuses the same workspace ID for repeated runs
of a suite. That contaminates every later run.

Fix:

- unique workspace per run/config
- explicit knowledge mode behavior:
  - `accumulate`: one workspace per run
  - `empty`: fresh workspace per task
  - `snapshot`: frozen knowledge checkpoint behavior

Without this, no ablation claim is trustworthy.

### 3B. Populate `knowledge_used` with real attribution -- Must

Right now `knowledge_used` is empty even though the runtime already records
replay-safe knowledge access traces.

Use existing truth:

- transcript/projection access traces for retrieved entry IDs
- previously produced knowledge IDs for attribution
- entry metadata for title/source context

The eval result should be able to say:

- which entries were used
- which earlier task/colony produced them
- whether they came from colony work or foraging

This is the audit demo backbone.

### 3C. Expand `ExperimentConditions` and write a run manifest -- Must

Replace thin fields with publication-grade run truth:

- `knowledge_mode`
- `snapshot_cutoff_index` when relevant
- `foraging_policy`
- `random_seed`
- `run_id`
- `commit_hash`
- stronger model/config/environment truth

Each run should produce a manifest beside the result JSON.

### 3D. Multi-run analysis with bootstrap / paired comparisons -- Should

Upgrade the curve tooling so it can support honest reporting:

- multi-run aggregation
- bootstrap 95% CIs
- paired-difference comparisons across configs
- stronger trend analysis than naive first-half/second-half
- entry-attribution analysis in the report layer

This is proof infrastructure, not product debt.

### Primary seams

- `src/formicos/eval/sequential_runner.py`
- `src/formicos/eval/compounding_curve.py`
- `src/formicos/eval/run.py`
- `src/formicos/eval/compare.py`

---

## Pillar 4: Task Suite Expansion

Only begin this after Pillar 3 truth is in place.

### 4A. Three categories

**Category A: language breadth**

- Exercism / Aider-comparable problems across multiple languages
- benchmark story
- language-specific accumulation effects

**Category B: multi-file depth**

- real repository tasks
- structural analysis and coordination
- some tasks where foraging should matter

**Category C: compounding clusters**

- grouped same-domain tasks
- intentionally ordered so later tasks should benefit from earlier knowledge
- the clearest test of the compounding thesis

### 4B. Multiple suites

Add at least:

- `pilot.yaml`
- `full.yaml`
- `benchmark.yaml`

Do not treat ordering as arbitrary. Task order is a locked condition.

### Primary seams

- `config/eval/tasks/`
- `config/eval/suites/`

---

## Pillar 5: Phased Measurement

### Phase 0: Harness validation -- Must

Run the current small suite with a minimal config comparison to verify:

- clean-room isolation works
- manifests are written
- `knowledge_used` is populated
- report generation handles the new data shape

### Phase 1: Pilot -- Must

Small enough to stop early if the signal is flat.

Recommended initial configs:

- single agent (strongest available)
- colony with `knowledge_mode=empty`
- colony with `knowledge_mode=accumulate` and full foraging

If the full colony does not materially beat the no-knowledge colony, stop and
investigate before spending more.

### Phase 2: Core proof -- Must

Scale up only after Phase 1 shows signal.

Add at least:

- colony with accumulated knowledge but foraging disabled

This isolates the forager contribution from the task-experience contribution.

### Phase 3: Full rigor -- If data warrants

Only if the earlier phases justify the spend.

Possible additions:

- cheaper single-agent baseline
- snapshot-mode plateau experiment
- more runs / stronger confidence intervals

### Operator improvement loop

Between phases:

1. inspect failures
2. tune parameters if the data justifies it
3. fix real bugs
4. re-run under locked conditions
5. document the changes honestly

This is not cheating. It is the correct measurement-driven improvement loop.

---

## Pillar 6: Demos And Publication

The three demos should be built from real measurement artifacts, not staged
stories disconnected from the run data.

### 6A. Live demo -- Must

- use a real measured task as the recording backbone
- keep a short live challenge beside the recorded run
- narrate failures honestly if they occur

### 6B. Benchmark demo -- Must

- honest score reporting
- no benchmark-specific code path
- show cost, variance, and compounding curve context

### 6C. Audit demo -- Must

Use real attribution and operator surfaces:

- why a colony retrieved a given entry
- where that entry came from
- what the Forager fetched
- what the operator overrode
- what competing hypotheses existed
- how replay preserved those edits

### 6D. Publication decision -- If data warrants

Three acceptable outcomes:

- rising curve -> publish the thesis
- mixed curve -> publish domain-specific findings
- flat curve -> publish the failure analysis honestly

---

## Priority Order

| Priority | Item | Pillar | Class | Operator test |
|----------|------|--------|-------|---------------|
| 1 | Forager API surface | 1 | Must | Yes |
| 2 | Web-source visibility in knowledge UI | 1 | Must | Yes |
| 3 | Clean-room run isolation | 3 | Must | Yes |
| 4 | Real `knowledge_used` attribution | 3 | Must | Yes |
| 5 | OTel wiring | 2 | Must | Yes |
| 6 | Conditions + manifest expansion | 3 | Must | Mostly yes |
| 7 | Search-through-egress consistency | 2 | Should | Yes |
| 8 | Forager activity in briefings | 1 | Should | Yes |
| 9 | Multi-run statistical analysis | 3 | Should | Indirectly |
| 10 | Task suite expansion | 4 | Should | No, but needed for proof |
| 11 | Phased measurement matrix | 5 | Must | No, but this is the point |
| 12 | Three demos from real artifacts | 6 | Must | Yes |

---

## Team Assignment

### Team 1: Forager Operator Surface + Product Cohesion

Owns:

- Pillar 1
- Pillar 2

Primary files:

- `src/formicos/surface/routes/api.py` or bounded route extraction
- `frontend/src/components/knowledge-browser.ts`
- `frontend/src/components/proactive-briefing.ts`
- `src/formicos/surface/app.py`

This team makes the newest subsystem visible and operable.

### Team 2: Eval Harness + Measurement Integrity

Owns:

- Pillar 3
- Pillar 4
- Pillar 5

Primary files:

- `src/formicos/eval/sequential_runner.py`
- `src/formicos/eval/compounding_curve.py`
- `src/formicos/eval/compare.py`
- `src/formicos/eval/run.py`
- `config/eval/tasks/`
- `config/eval/suites/`

This team makes proof credible instead of hand-wavy.

### Team 3: Analysis + Demos + Publication Scaffolding

Owns:

- Pillar 6
- measurement-facing docs and report scaffolds
- post-run documentation truth

Primary files:

- documentation/report templates created under `docs/waves/wave_46/`
- any bounded docs updates after Team 1/2 land

This team turns product truth and measurement truth into a story without
fabricating results.

### Overlap

- Team 1 and Team 2 may both read `app.py`, but only Team 1 should own edits there.
- Team 2 produces manifests/results; Team 3 consumes them.
- Team 3 should not invent measurements or demo outcomes ahead of data.

---

## What Wave 46 Does Not Include

- no new event types
- no new adapters or subsystems
- no benchmark-specific product paths
- no Playwright / Level 3 fetch
- no SearXNG deployment
- no semantic deduplication
- no learned routing or convergence prediction
- no architecture rewrites
- no task-specific heuristics or suite-only scoring rules

---

## Smoke Test

1. Operator can trigger a manual forage and inspect the result.
2. Operator can trust/distrust/reset a domain through the product surface.
3. Forage cycle history is readable through the API.
4. Web-sourced knowledge is visibly distinct in the normal UI.
5. OTel can be enabled additively beside JSONL.
6. Sequential runs use clean-room isolation and do not contaminate each other.
7. `knowledge_used` is populated from real replay-safe access truth.
8. Each run writes a manifest beside the result JSON.
9. At least the pilot suite can be run with credible output.
10. No benchmark-specific code path exists in product code.
11. The audit story can point to a real entry, its origin, and its use.

---

## After Wave 46

FormicOS is proven -- or its limitations are honestly characterized.
The operator can see inside the Forager, control it, and audit where
knowledge came from. The measurement story uses real attribution and
clean-room runs. The demos are built from the actual product, not a special
benchmark branch.

If the curve rises, publish the thesis.
If the curve is mixed, publish the domain-specific findings.
If the curve is flat, publish the failure analysis.

All three are honest contributions.

**empower -> deepen -> harden -> forage -> complete -> prove**

**FormicOS is an editable shared brain, not a benchmark runner. Wave 46
proves it on its own terms -- or honestly shows where it does not yet work.**
