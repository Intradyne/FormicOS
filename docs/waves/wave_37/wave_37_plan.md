# Wave 37 Plan -- The Hardened Colony

**Wave:** 37 -- "The Hardened Colony"

**Theme:** Every future wave -- NemoClaw integration, A2A federation, external
benchmarking, earned autonomy, and community contribution -- goes faster and
safer if the foundation is right. Wave 37 closes the stigmergic loop, hardens
the repo and project surface for external trust, builds measurement
infrastructure so FormicOS can judge its own improvements, and lays the minimum
poisoning-defense and operator-data foundations that Wave 38 depends on.

**Prerequisite:** Wave 36 landed. The guided demo works end to end. The command
center surfaces briefing, active plans, maintenance posture, federation health,
and outcome badges. `ColonyOutcome` is surfaced with truthful success labeling
for verified coding work. Scheduled refresh and performance insight rules are
active. The public README explains the demo path. The closed event union
remains at 55.

**Contract changes:** No new event types. The union stays at 55. All Wave 37
changes operate inside existing `engine/` and `surface/` seams. Triple-tier
retrieval is implemented as a derived projection and staged retrieval path, not
as a new event family. Operator-behavior collection reuses existing event
surfaces and inference from current projections where possible. One ADR is
recommended: **ADR-048** for knowledge-weighted topology initialization policy.

**Current repo truth at wave start:**

- [CONTRIBUTING.md](/c:/Users/User/FormicOSa/CONTRIBUTING.md) already exists and
  should be expanded, not rewritten from scratch.
- [.github/workflows/ci.yml](/c:/Users/User/FormicOSa/.github/workflows/ci.yml)
  already runs lint, typecheck, layer-check, tests, and Docker build. Wave 37
  augments the existing CI surface.
- The active topology seam is
  [src/formicos/engine/strategies/stigmergic.py](/c:/Users/User/FormicOSa/src/formicos/engine/strategies/stigmergic.py),
  not `engine/topology.py`.
- Knowledge confidence, decay, co-occurrence, and outcome projections are
  already live in:
  - [src/formicos/surface/knowledge_catalog.py](/c:/Users/User/FormicOSa/src/formicos/surface/knowledge_catalog.py)
  - [src/formicos/surface/colony_manager.py](/c:/Users/User/FormicOSa/src/formicos/surface/colony_manager.py)
  - [src/formicos/surface/projections.py](/c:/Users/User/FormicOSa/src/formicos/surface/projections.py)
  - [src/formicos/surface/proactive_intelligence.py](/c:/Users/User/FormicOSa/src/formicos/surface/proactive_intelligence.py)

---

## Why This Wave

Wave 36 made FormicOS visible. A new operator can land on the command center,
run the demo, watch colonies execute in parallel, see knowledge extract and
maintenance fire, and understand what the system is doing.

But "visible" is not yet "trustworthy."

Three gaps remain before FormicOS can safely participate in an external
ecosystem.

First, the stigmergic thesis is still only partially closed. The knowledge
system is already a genuine environmental coordination substrate -- Thompson
Sampling, gamma decay, co-occurrence reinforcement, proactive maintenance,
federation -- but it still does not feed back into topology strongly enough.
Colonies begin from a knowledge-blind social graph even when the environment
already knows what tends to work in that domain. Outcomes reinforce knowledge,
but too coarsely. The system can detect stalled colonies and degraded knowledge
regions, but it still lacks a clean measure of when the search field itself is
narrowing into a premature attractor.

Second, the project surface is not yet mature enough for serious external
evaluation. The repo needs the supply-chain, vulnerability-handling, legal, and
contributor-process signals that security reviewers and outside collaborators
expect.

Third, FormicOS still has weak measurement infrastructure for its own thesis.
Wave 36 can show the system. Wave 37 needs to instrument it. Without an
internal benchmark harness, outcome-calibration checks, retrieval-cost
instrumentation, and stagnation metrics, the system cannot actually tell whether
its most important improvements are helping.

Wave 37 fixes those gaps in order:

1. close the stigmergic loop,
2. make the project trustworthy,
3. build the instruments,
4. then attempt risky retrieval optimization.

If the wave runs short, it should cut from the bottom, not the top.

---

## Pillar 1: Close the Stigmergic Loop

This is the architectural core of the wave. The goal is to close the feedback
loop between:

- **Layer 1:** short-term, intra-colony pheromone routing
- **Layer 2:** long-term, inter-colony knowledge traces

Three proposals from the "Knowledge as Pheromone" research memo form the core.

### 1A. Knowledge-Weighted Topology Initialization

When a colony spawns, the initial topology should not be knowledge-blind.
Relevant, high-confidence knowledge should bias the initial edge weights between
agents before any round-level pheromone adaptation begins.

#### Implementation

At colony start:

1. compute a compact knowledge-bias summary from already retrieved entries:
   - dominant domains
   - average posterior mean per domain
   - posterior mass / certainty per domain
   - optionally, recent successful strategy/caste patterns in those domains
2. map those domains onto agent descriptors or recipe responsibilities
3. compute a runtime `knowledge_prior: dict[tuple[str, str], float] | None`
   in
   [src/formicos/engine/runner.py](/c:/Users/User/FormicOSa/src/formicos/engine/runner.py)
   immediately before topology resolution, using retrieval state already
   available to the round
4. in
   [src/formicos/engine/strategies/stigmergic.py](/c:/Users/User/FormicOSa/src/formicos/engine/strategies/stigmergic.py),
   extend `resolve_topology()` with an optional `knowledge_prior` parameter and
   apply a narrow multiplicative prior before thresholding:

`sim_ij <- sim_ij * prior_ij`

where `prior_ij` is derived from domain trace quality and capped within a small
band such as `[0.85, 1.15]`.

This should be a runtime prior, not a persisted new object model. Do **not**
modify `ColonyContext` in `core/types.py` for this. Keep the seam in the
engine-layer call path so the core contract remains untouched.

#### Files

- [src/formicos/engine/strategies/stigmergic.py](/c:/Users/User/FormicOSa/src/formicos/engine/strategies/stigmergic.py)
- [src/formicos/engine/runner.py](/c:/Users/User/FormicOSa/src/formicos/engine/runner.py)
- [src/formicos/surface/knowledge_catalog.py](/c:/Users/User/FormicOSa/src/formicos/surface/knowledge_catalog.py)

#### Expected improvement

- fewer warmup rounds before useful agent routing emerges
- lower token cost on repeated-domain tasks
- better early-round convergence where the workspace already knows the domain

#### Risks

- over-biasing toward stale local habits
- suppressing new team shapes too early
- topology becoming too sensitive to retrieval mistakes

#### Guardrails

- keep the prior narrow
- gate by certainty and freshness
- surface the applied bias in debug or operator-visible rationale when feasible

#### Acceptance

Repeated-domain colonies show improved rounds-to-first-useful-output against a
neutral baseline, as measured by the internal harness.

### 1B. Outcome-Weighted Knowledge Reinforcement

FormicOS already reinforces accessed knowledge entries based on colony success
and failure. The current loop is directionally right but too coarse. A marginal
success and a clean, verified, high-quality success should not reinforce the
environment equally.

#### Implementation

In
[src/formicos/surface/colony_manager.py](/c:/Users/User/FormicOSa/src/formicos/surface/colony_manager.py),
replace constant `+1` updates with clipped quality-aware deltas:

- `delta_alpha = clip(0.5 + quality_score, 0.5, 1.5)`
- `delta_beta = clip(0.5 + failure_penalty, 0.5, 1.5)`

Optional refinements, if they stay bounded:

- weight by access mode:
  - `context_injection` strongest
  - `tool_detail` medium
  - `tool_search` weakest unless reused downstream
- add a bonus when:
  - the colony had verified successful `code_execute`
  - or the colony extracted new knowledge after using the source trace

No new event types are needed; `MemoryConfidenceUpdated` already carries
arbitrary old/new alpha and beta values.

Implementation note: the existing `_hook_confidence_update(...)` hook currently
receives `succeeded: bool`, not a quality score. Wave 37 must thread
`quality_score: float` into that hook from the colony-finalization path where
quality is already available, then use that float to drive the weighted update.

#### Files

- [src/formicos/surface/colony_manager.py](/c:/Users/User/FormicOSa/src/formicos/surface/colony_manager.py)
- [src/formicos/surface/projections.py](/c:/Users/User/FormicOSa/src/formicos/surface/projections.py)

#### Expected improvement

- stronger correlation between posterior confidence and actual downstream
  usefulness
- faster emergence of domain-specialized trusted entries
- lower persistence of entries that are often retrieved but rarely helpful

#### Risks

- rich-get-richer effects
- too much concentration growth in a few entries or domains

#### Guardrails

- clipped deltas
- keep Thompson Sampling
- preserve decay and priors
- track posterior mass growth per domain

#### Acceptance

Retrieved-entry usefulness correlates more strongly with posterior mean and
posterior mass after the change than before it.

### 1C. Branching-Factor Stagnation Diagnostics

FormicOS currently detects:

- stalled colonies
- degraded knowledge regions
- contradictions and coverage gaps

It does **not** yet detect "the search space is collapsing around one narrow
attractor."

#### Implementation

Add three branching metrics:

1. **Topology branching factor**
   - entropy or effective count over normalized active edge weights per agent
2. **Knowledge branching factor**
   - effective count over top-k retrieval posterior mass
3. **Configuration branching factor**
   - diversity of successful strategy/caste selections over a moving window

Generate a `KnowledgeInsight` or equivalent operator-visible signal only when:

- branching is low
- and failures or warnings are rising
- and the same entries or configurations dominate recent work

This remains a read-model diagnostic. No new event types are required.

#### Files

- [src/formicos/surface/proactive_intelligence.py](/c:/Users/User/FormicOSa/src/formicos/surface/proactive_intelligence.py)
- [src/formicos/engine/runner.py](/c:/Users/User/FormicOSa/src/formicos/engine/runner.py)
- optionally
  [src/formicos/surface/queen_runtime.py](/c:/Users/User/FormicOSa/src/formicos/surface/queen_runtime.py)

#### Expected improvement

- earlier warning before the operator sees repetitive failure patterns
- cleaner rationale for diversification or maintenance intervention

#### Acceptance

Low branching-factor readings correlate with subsequent colony failures or
stagnation clusters in the internal benchmark runs.

---

## Pillar 2: Trust Foundations

This pillar has three tracks:

- supply-chain security
- contributor/legal infrastructure
- poisoning-defense foundations

### 2A. Supply-Chain Security

Wave 37 should augment the existing CI rather than replacing it. The project
already has
[.github/workflows/ci.yml](/c:/Users/User/FormicOSa/.github/workflows/ci.yml);
the goal is to make that CI produce trust signals that outside evaluators expect.

#### Repo-owned deliverables

- `SECURITY.md` with disclosure path, response expectations, and supported
  versions
- CodeQL in GitHub Actions
- Trivy container scanning in GitHub Actions
- SLSA provenance generation
- SBOM generation attached to releases
- Dependabot configuration committed to the repo
- documented license-compliance scanning path if account-backed tooling is used

#### Admin/secret-backed deliverables

These may require operator-owned setup outside the repo:

- service accounts or tokens for external compliance tools
- branch protection / required checks policy
- release-secret management where needed

#### Trust bar

The goal is **not** a vanity badge count or a fake coverage threshold.

The real trust bar is:

- reproducible builds
- visible dependency/security posture
- reliable CI on critical paths
- documentation that helps contributors avoid architectural violations

Critical-path coverage matters more than raw percentage. In practice, that means
all of the following should be exercised by tests:

- event handlers
- projection builders
- retrieval scoring
- governance decisions
- core safety regressions

### 2B. Contributor And Legal Infrastructure

The project already has
[CONTRIBUTING.md](/c:/Users/User/FormicOSa/CONTRIBUTING.md). Wave 37 should
expand it into a real onboarding and contribution packet.

#### Repo-owned deliverables

- expand `CONTRIBUTING.md` with:
  - layer rules
  - event-sourcing constraints
  - key file paths
  - local run/test flows
  - PR expectations
- `GOVERNANCE.md`
- `CODE_OF_CONDUCT.md`
- issue templates
- PR templates
- a small curated starter-task list in repo docs if labels are not yet applied

#### Admin-owned deliverables

- CLA Assistant installation and configuration
- DCO/signoff enforcement if used
- `good-first-issue` label application on real issues

#### Non-negotiable point

The CLA is urgent. FormicOS should not accept external PRs without a CLA path in
place if the dual-license model matters.

### 2C. Poisoning-Defense Foundation

This is **not** the full Wave 38 poisoning-defense program. It is the minimum
substrate work that becomes expensive to retrofit once external surfaces widen.

#### Scope

1. **Admission scoring hooks**
   - create a clear evaluation seam in the knowledge-ingestion path
   - use pass-through behavior initially
   - defer A-MAC-like scoring policy to Wave 38
2. **Provenance visibility**
   - surface source colony, agent, round, and federation origin more directly
   - the data mostly already exists; the problem is surfacing and explanation
3. **Trust surfacing on retrieved entries**
   - show why an entry is trusted in operator-facing retrieval surfaces
   - not only raw score breakdown
4. **Review federation trust discounting**
   - confirm low-trust foreign entries cannot dominate strong local entries in
     normal retrieval

#### Files

- [src/formicos/surface/knowledge_catalog.py](/c:/Users/User/FormicOSa/src/formicos/surface/knowledge_catalog.py)
- [src/formicos/surface/projections.py](/c:/Users/User/FormicOSa/src/formicos/surface/projections.py)
- relevant frontend knowledge views if surfaced in this wave

#### Acceptance

An operator can inspect a retrieved entry and understand where it came from and
why the system currently trusts it, without needing to parse the full score
breakdown math.

---

## Pillar 3: Measurement Infrastructure

Wave 37 should build the instruments, not publish the paper. External
benchmarking remains a Wave 38 concern. But Wave 37 must leave behind enough
measurement substrate to tell whether Pillar 1 actually helped.

### 3A. Internal Benchmark Harness

Build an internal harness focused on repeated-domain work rather than generic
one-off tasks.

#### Minimum scope

- 10-20 coding tasks across 3-4 recurring domains
- include tasks where accumulated knowledge should help
- include control tasks where it should not help much

#### Measurements

- colony outcome calibration:
  - compare `ColonyOutcome.quality_score` against actual task correctness
- retrieval-cost instrumentation:
  - track token or retrieval-cost footprint per colony
- branching metrics:
  - log the topology, knowledge, and configuration branching factors
- rounds-to-first-useful-output
- total rounds and total cost

### 3B. Ablation Infrastructure

The harness should support toggling the three Pillar 1 features independently:

1. current Wave 36 substrate baseline
2. + knowledge-weighted topology initialization
3. + outcome-weighted reinforcement
4. + branching diagnostics

This is what makes Wave 38's external benchmarking believable later.

### 3C. Regression Fixtures

Wave 37 should add regression fixtures for the most important substrate truths:

- poisoning regression:
  a bad or low-trust entry does not dominate retrieval over legitimate local
  entries
- decay regression:
  stale entries lose influence predictably
- federation regression:
  low-trust foreign entries do not override high-trust local ones
- outcome-truth regression:
  solved coding colonies with verified execution are marked completed with
  non-zero quality

---

## Pillar 4: Adaptive Evaporation And Operator-Data Foundation

### 4A. Adaptive Evaporation Recommendations

The current `ephemeral` / `stable` / `permanent` system is correct, but coarse.
Wave 37 should make decay more explainable and recommendation-driven before any
future automation.

#### Implementation

- keep current class-level defaults
- add workspace-level recommendation capability for domain-specific overrides
- infer candidate recommendations from:
  - prediction errors
  - reuse half-life
  - refresh-colony frequency
  - positive/negative `knowledge_feedback`

This remains recommendation-only. No automatic tuning in Wave 37.

#### Files

- [src/formicos/surface/knowledge_catalog.py](/c:/Users/User/FormicOSa/src/formicos/surface/knowledge_catalog.py)
- [src/formicos/surface/proactive_intelligence.py](/c:/Users/User/FormicOSa/src/formicos/surface/proactive_intelligence.py)
- [src/formicos/surface/queen_runtime.py](/c:/Users/User/FormicOSa/src/formicos/surface/queen_runtime.py)

### 4B. Operator-Behavior Data Collection

Collect silently now. Use later.

#### Signals already available or inferable

- `knowledge_feedback`
- `ColonyKilled`
- directive traffic and target colony types
- operator interaction with suggestions where inference is possible from
  follow-on action

#### Important constraint

Explicit "suggestion accepted vs rejected" is **not** currently a fully clean
event surface. Wave 37 should not overclaim exact tracking here under the
closed-event rule.

Instead:

- infer **accepted** suggestions from a matching colony spawn shortly after an
  insight or recommendation
- defer exact **rejected** suggestion tracking until there is a justified
  replay-safe surface for it

This keeps the wave honest under the "no new events" rule.

#### Files

- [src/formicos/surface/projections.py](/c:/Users/User/FormicOSa/src/formicos/surface/projections.py)
- any derived operator-behavior read models added in `surface/`

### 4C. Design Adaptive Evaporation And Operator Data Together

These are separate deliverables but should share a mental model. Operator
demotions and promotions are strong evidence for which domains decay too slowly
or too quickly. Wave 37 should design the recommender and the operator-signal
projection so that Wave 39's earned-autonomy work has the right substrate.

---

## Pillar 5: Triple-Tier Retrieval Foundation (Stretch)

This is the highest-risk optimization in the wave. It should be built as
projection-first, fallback-safe infrastructure, not as a sweeping retrieval
rewrite.

### 5A. Triple Extraction

At knowledge-entry creation or projection time, derive lightweight
subject-predicate-object triples as a compressed retrieval tier.

Examples:

- "use `asyncio.TaskGroup` for concurrent async Python work"
  becomes `(async Python, uses, asyncio.TaskGroup)`

These triples are a derived projection, not a new event type.

### 5B. Staged Retrieval

Use triples as a cheap prefilter or first pass.

- if triple-tier confidence is high, return early
- if not, escalate aggressively to summaries or full entries

The initial rollout should err on the side of escalation.

### 5C. Promotion Gate

Triple-tier retrieval should **not** become the default path unless the
benchmark harness shows:

- materially lower retrieval cost
- no measurable drop in colony success
- no meaningful increase in prediction errors or contradiction drift

If the data is mixed, keep the projection and delay activation.

#### Files

- [src/formicos/surface/knowledge_catalog.py](/c:/Users/User/FormicOSa/src/formicos/surface/knowledge_catalog.py)
- [src/formicos/surface/projections.py](/c:/Users/User/FormicOSa/src/formicos/surface/projections.py)

---

## Priority Order

If scope must be cut, cut from the bottom.

| Priority | Item | Pillar | Risk | Class |
|---|---|---|---|---|
| 1 | Knowledge-weighted topology initialization | 1A | Medium | Must |
| 2 | Outcome-weighted knowledge reinforcement | 1B | Low | Must |
| 3 | Branching-factor diagnostics | 1C | Low | Must |
| 4 | CLA + contributor/legal hardening | 2B | Low | Must |
| 5 | SECURITY + CodeQL + Trivy + SBOM/provenance | 2A | Low | Must |
| 6 | Internal benchmark harness | 3A | Low | Must |
| 7 | Admission hooks + provenance/trust surfacing | 2C | Low | Must |
| 8 | Operator behavior collection | 4B | Low | Should |
| 9 | Adaptive evaporation recommendations | 4A | Medium | Should |
| 10 | Ablation infrastructure | 3B | Low | Should |
| 11 | Regression fixtures | 3C | Low | Should |
| 12 | Triple extraction projection | 5A | Medium | Stretch |
| 13 | Staged triple-first retrieval | 5B | High | Stretch |

---

## Team Assignment

### Team 1: Stigmergic Loop Closure + Core Measurement

Owns:

- Pillar 1A, 1B, 1C
- Pillar 3A and 3B

Primary files:

- [src/formicos/engine/strategies/stigmergic.py](/c:/Users/User/FormicOSa/src/formicos/engine/strategies/stigmergic.py)
- [src/formicos/engine/runner.py](/c:/Users/User/FormicOSa/src/formicos/engine/runner.py)
- [src/formicos/surface/knowledge_catalog.py](/c:/Users/User/FormicOSa/src/formicos/surface/knowledge_catalog.py)
- [src/formicos/surface/colony_manager.py](/c:/Users/User/FormicOSa/src/formicos/surface/colony_manager.py)
- [src/formicos/surface/proactive_intelligence.py](/c:/Users/User/FormicOSa/src/formicos/surface/proactive_intelligence.py)
- benchmark/test infrastructure for the new harness

### Team 2: Trust Foundations + Poisoning Foundation

Owns:

- Pillar 2A, 2B, 2C

Primary files:

- `.github/` workflow/config files
- `SECURITY.md`
- `GOVERNANCE.md`
- `CODE_OF_CONDUCT.md`
- [CONTRIBUTING.md](/c:/Users/User/FormicOSa/CONTRIBUTING.md)
- [src/formicos/surface/knowledge_catalog.py](/c:/Users/User/FormicOSa/src/formicos/surface/knowledge_catalog.py)
  for trust/provenance surfacing only

### Team 3: Operator Data + Adaptive Evaporation + Retrieval Stretch

Owns:

- Pillar 4A, 4B, 4C
- Pillar 5 if there is remaining time

Primary files:

- [src/formicos/surface/projections.py](/c:/Users/User/FormicOSa/src/formicos/surface/projections.py)
- [src/formicos/surface/proactive_intelligence.py](/c:/Users/User/FormicOSa/src/formicos/surface/proactive_intelligence.py)
- [src/formicos/surface/queen_runtime.py](/c:/Users/User/FormicOSa/src/formicos/surface/queen_runtime.py)
- workspace-config surfaces
- retrieval projection path if triple-tier work begins

### Overlap seams

- [src/formicos/surface/knowledge_catalog.py](/c:/Users/User/FormicOSa/src/formicos/surface/knowledge_catalog.py)
  is shared by Teams 1 and 2.
  Team 1 owns scoring/retrieval behavior.
  Team 2 owns trust/provenance surfacing.
  If Pillar 5 ships, Team 3 also touches this file for triple-tier prefiltering.
  In that case, Team 3 owns only the additive triple-tier projection and staged
  escalation path.
- [src/formicos/surface/proactive_intelligence.py](/c:/Users/User/FormicOSa/src/formicos/surface/proactive_intelligence.py)
  is shared by Teams 1 and 3.
  Team 1 owns branching diagnostics.
  Team 3 owns evaporation recommendations.

---

## What Wave 37 Does Not Include

- no Experimentation Engine
- no NemoClaw integration
- no A2A protocol implementation
- no external benchmark publication
- no earned autonomy
- no automatic configuration tuning
- no bi-temporal knowledge model
- no new event types

Wave 37 builds the foundation for those later moves. It does not try to do all
of them at once.

---

## Wave 38 Hard Dependencies

Wave 38 should not widen external or federation-facing surfaces without these
Wave 37 outputs in place:

- CLA and contributor/legal foundation
- security posture and provenance basics
- admission scoring hooks
- provenance visibility and trust surfacing
- benchmark harness and ablation support

That is a hard dependency, not a nice-to-have. External ingestion surfaces
without substrate trust and poisoning-defense foundations are not responsible.

---

## Post-Integration Smoke

1. Spawn a repeated-domain coding colony with existing high-confidence
   knowledge.
   Verify that the initial topology is knowledge-biased rather than neutral.
2. Complete a verified coding colony.
   Verify that accessed entries receive quality-aware reinforcement rather than
   a constant update.
3. Run many colonies in one domain.
   Verify that branching diagnostics warn before obvious repetitive failure
   patterns.
4. Push a PR or simulate the repo workflow path.
   If CLA Assistant is configured, verify the PR path blocks until signed. If it
   is not yet configured, verify the documentation describes the required admin
   setup path and CI security jobs run.
5. Retrieve knowledge in operator surfaces.
   Verify provenance and trust rationale are visible.
6. Run the internal benchmark suite.
   Verify retrieval cost, outcome calibration, and branching metrics are logged.
7. Use `knowledge_feedback` and kill or steer colonies.
   Verify operator-signal projections capture the evidence that is currently
   derivable.
8. If triple-tier retrieval shipped:
   verify triple extraction, conservative escalation, and zero-regression on the
   harness.
9. Full validation:
   `ruff`, `pyright`, `lint_imports`, `pytest`, frontend build, and CI security
   jobs all pass.

---

## After Wave 37

After this wave, FormicOS should be able to claim something stronger than
"working demo" and more specific than "advanced multi-agent framework."

It should be able to claim:

- the stigmergic loop is closed
- the project surface is credible to outside evaluators
- the system has instrumentation to judge its own improvements
- the poisoning-defense substrate is in place before ecosystem expansion
- operator behavior is being collected in a replay-safe way for future earned
  autonomy

Wave 38 can then safely open outward: ecosystem integration, external
benchmarking, broader poisoning defenses, and the deeper temporal knowledge
model. Wave 37 is the foundation wave that makes those moves responsible rather
than merely ambitious.
