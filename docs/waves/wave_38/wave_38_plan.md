# Wave 38 Plan -- The Ecosystem Colony

**Wave:** 38 -- "The Ecosystem Colony"

**Theme:** Wave 37 made FormicOS trustworthy. Wave 38 makes it externally
callable, internally measurable on harder tasks, and harder to poison as the
ecosystem surface widens.

Wave 38 is not the public proving wave. It is the bridge between "trusted
local-first colony system" and "credible participant in a wider agent
ecosystem."

The wave has three pillars:

1. NemoClaw + A2A ecosystem integration
2. Internal benchmarking on external-style task slices
3. Full poisoning defense plus bi-temporal knowledge surfacing

**Prerequisite:** Wave 37 is accepted. The stigmergic loop is closed, trust and
provenance are visible, the internal benchmark harness exists, and the
admission-scoring seam is present. Admin-owned Wave 37 follow-up that actually
gates external exposure must be complete before claiming external readiness.

**Contract target:** Keep the core event union closed at 55. Wave 38 should
prefer existing route, adapter, projection, and read-model seams. If a narrow
contract expansion becomes unavoidable, stop and justify it through an ADR
before editing `core/`.

**Recommended ADRs:**

- External specialist integration boundary (tool-level first, model-level later)
- A2A compatibility policy and truth-in-advertising policy
- Bi-temporal knowledge validity policy

---

## Current Repo Truth At Wave Start

Wave 38 should start from the system that actually exists, not from the
roadmap abstraction.

- Inbound A2A already exists at `src/formicos/surface/routes/a2a.py` as a
  colony-backed submit / poll / attach / result lifecycle at `/a2a/tasks`.
- The Agent Card already exists at `/.well-known/agent.json` in
  `src/formicos/surface/routes/protocols.py` and already advertises MCP,
  AG-UI, and A2A.
- The Queen already has `query_service` in
  `src/formicos/surface/queen_tools.py`, backed by `ServiceRouter` in
  `src/formicos/engine/service_router.py`.
- `routing_override` already exists on colony projections and already drives
  tier escalation through `engine/runner.py`. This remains the governance-owned
  escalation seam. Provider fallback is a different system.
- `LLMPort` plus `tier_models` already make model-level external-agent wrapping
  possible later. That is Pattern 2 and is not the Wave 38 default.
- The Wave 37 admission seam already exists in `src/formicos/surface/admission.py`
  and is currently pass-through with explanatory scoring only.
- The four-axis memory scanner already exists in
  `src/formicos/surface/memory_scanner.py`.
- The knowledge graph adapter already stores temporal edge validity in
  `src/formicos/adapters/knowledge_graph.py` with `valid_at` and `invalid_at`.
- Wave 37 already left behind a repeated-domain benchmark harness in
  `tests/integration/test_wave37_stigmergic_loop.py`.

Wave 38 is therefore an extension and hardening wave, not a greenfield one.

---

## Why This Wave

Wave 37 made FormicOS believable inside its own repo:

- knowledge can bias topology
- outcomes now reinforce knowledge more truthfully
- the repo has a cleaner trust surface
- the system can measure parts of its own thesis

But FormicOS still has three gaps before it can credibly join a broader
ecosystem and later make a public benchmark claim.

First, the external-agent seams are only partially mature. FormicOS already has
MCP, AG-UI, Agent Card discovery, `query_service`, and inbound A2A task
lifecycle. What it does not yet have is a clean, audited bridge for calling
specialist external agents such as NemoClaw while preserving FormicOS's own
traceability, nor a clearly hardened and ecosystem-honest A2A surface.

Second, Wave 37's measurement harness proves local architectural deltas, but it
does not yet exercise external-style benchmark slices strongly enough to
support Wave 40's public thesis claim. Wave 38 needs internal evidence on
harder tasks before Wave 39 invests in adaptation and Wave 40 spends credibility
on a public result.

Third, widening ecosystem surfaces without stronger poisoning defenses and
temporal truth would be irresponsible. The system already has provenance,
admission hooks, federation trust, and a partially temporal knowledge graph.
Wave 38 needs to turn those into a real defense and a more time-aware knowledge
model.

The sequence matters:

1. make the ecosystem boundary honest and callable
2. prove the architecture internally on harder tasks
3. harden the knowledge substrate against poisoning and time drift

Only then should the system learn to escalate itself and attempt a public
benchmark claim.

---

## Pillar 1: Ecosystem Integration

Wave 38 should join the ecosystem through the seams that already exist, not by
inventing a second orchestration stack.

### 1A. NemoClaw As A Tool-Level Specialist Bridge

FormicOS should integrate NemoClaw through Pattern 1 first: external
agent-as-service, not external agent-as-model.

#### Implementation

1. Add a bounded adapter for calling a NemoClaw or OpenShell-backed specialist
   service over HTTP.
2. Register one or more deterministic `ServiceRouter` handlers in `app.py` so
   colonies and the Queen can call those specialists through the existing
   `query_service` flow.
3. Preserve existing service query traces by routing through
   `ServiceQuerySent` and `ServiceQueryResolved`, not by bypassing the router.
4. Document the integration as an external specialist boundary:
   - FormicOS colony remains the colony
   - NemoClaw remains an external specialist resource
   - no hidden colony state should live only inside the external service

Candidate service types:

- `service:external:nemoclaw:secure_coder`
- `service:external:nemoclaw:security_review`
- `service:external:nemoclaw:sandbox_analysis`

The exact names can be simpler, but they should stay explicit and
operator-readable.

#### Files

- `src/formicos/adapters/nemoclaw_client.py` or similarly bounded adapter
- `src/formicos/engine/service_router.py` only if a small additive seam is needed
- `src/formicos/surface/app.py`
- `src/formicos/surface/queen_tools.py`
- `src/formicos/surface/mcp_server.py` only if operator-callable tooling needs
  additive help
- `docs/NEMOCLAW_INTEGRATION.md`

#### Expected Improvement

- FormicOS can call real external specialists without flattening them into
  vague prompt text
- external capability is visible in normal service-query traces
- the license and runtime boundary stays clean

#### Risks

- hidden side effects in the external system
- auth and endpoint drift
- over-coupling Wave 38 to one vendor's surface

#### Guardrails

- do not wrap NemoClaw as `LLMPort` in Wave 38
- keep the integration tool-level and traceable
- preserve timeout, response preview, and auditability through existing service
  query events

#### Acceptance

A colony or the Queen can call a NemoClaw-backed specialist through
`query_service`, get a bounded result, and that call is visible in the normal
service-query trace path.

### 1B. A2A Compatibility Hardening

Wave 38 should treat A2A as an interoperability-hardening track, not as a
greenfield task-lifecycle build. The core lifecycle already exists.

#### Implementation

1. Keep the current `/a2a/tasks` submit / poll / attach / result lifecycle
   stable for existing clients.
2. Narrow the gap between the current implementation and ecosystem
   expectations:
   - make capability and auth truth clearer in the Agent Card
   - keep error shapes and task status envelopes consistent
   - document the supported subset explicitly
3. If a JSON-RPC compatibility wrapper is added, it must adapt to the existing
   colony-backed lifecycle rather than creating a second task store or second
   truth surface.
4. Preserve snapshot-then-live-tail SSE semantics for attach.

#### Files

- `src/formicos/surface/routes/a2a.py`
- `src/formicos/surface/routes/protocols.py`
- `src/formicos/surface/structured_error.py`
- `docs/A2A-TASKS.md`
- `docs/API_SURFACE_INTEGRATION_REFERENCE.md`

#### Expected Improvement

- external agent frameworks can understand what FormicOS supports without
  guessing
- future ecosystem clients face fewer protocol surprises
- the Agent Card becomes a truthful integration artifact, not marketing gloss

#### Risks

- overclaiming conformance
- breaking current A2A clients while chasing cleaner compatibility
- duplicating lifecycle logic in a second route family

#### Guardrails

- preserve the current `/a2a/tasks` path unless a compatibility wrapper is
  strictly additive
- do not create a second task store
- keep the Agent Card truthful about what is actually supported

#### Acceptance

The Agent Card, A2A docs, and actual route behavior all agree on:

- submission mode
- event attachment behavior
- result retrieval behavior
- auth status

### 1C. Ecosystem Operator Docs

Wave 38 should leave behind operator-facing integration guidance, not just
routes and adapters.

Required docs:

- NemoClaw integration setup
- A2A capability and compatibility notes
- local-only vs externally exposed deployment guidance
- known security and auth assumptions

This is part of the trust story, not optional polish.

---

## Pillar 2: Internal Benchmarking

Wave 40 will only be credible if Wave 38 proves the architecture internally on
harder tasks first.

### 2A. External-Style Internal Benchmark Suite

Extend the Wave 37 harness into a stronger internal suite using curated slices
from public benchmark styles rather than trying to replicate full public
leaderboards inside the repo.

#### Implementation

1. Keep the Wave 37 repeated-domain harness.
2. Add a curated coding benchmark suite inspired by:
   - HumanEval-style function tasks
   - SWE-bench-style multi-file bug-fix slices
3. Keep the suite bounded and reproducible:
   - small enough to run locally
   - deterministic or tightly constrained
   - no giant external benchmark dependency in Wave 38
4. Measure, at minimum:
   - task success
   - quality score
   - wall time
   - token / dollar cost
   - retrieval cost

#### Files

- `tests/integration/test_wave37_stigmergic_loop.py`
- `tests/integration/test_wave38_benchmarks.py`
- optional `scripts/benchmarks/*` helpers if they reduce duplication
- `docs/waves/wave_38/internal_benchmarking.md`

#### Expected Improvement

- FormicOS can judge whether the two-layer stigmergic architecture helps on
  more realistic code tasks
- Wave 39 has evidence to tune against
- Wave 40 has a grounded launch point instead of a cold public attempt

#### Risks

- brittle tests that are really benchmarks
- overfitting to tiny curated tasks
- accidental conflation of benchmark score and product truth

#### Guardrails

- keep the suite small and replay-safe
- prefer ablations and trend lines over one vanity score
- do not call it a public benchmark result

#### Acceptance

There is a local, reproducible benchmark suite that can compare:

1. Wave 36 / neutral baseline
2. Wave 37 loop-closure features
3. Wave 38 additions where applicable

### 2B. Escalation Outcome Matrix

Wave 39's auto-escalation and configuration learning depend on a clean record
of escalation outcomes. Wave 38 must collect that evidence before it automates
anything.

#### Implementation

Build a replay-derived outcome matrix that can answer:

- domain or task family
- starting tier
- whether `routing_override` was applied
- escalated tier
- reason
- round at override
- total cost
- wall time
- final quality
- success / failure

This must use the existing governance-owned `routing_override` seam, not
provider fallback logs.

#### Files

- `src/formicos/surface/projections.py`
- `src/formicos/surface/routes/api.py`
- optional operator-facing read surface if additive and low risk
- `tests/integration/test_wave38_escalation_matrix.py`

#### Expected Improvement

- Wave 39 will have real evidence for learned configuration suggestions and
  auto-escalation policy
- manual Queen escalations become measurable rather than anecdotal

#### Risks

- conflating provider fallback with capability escalation
- under-specifying "before vs after escalation" deltas

#### Guardrails

- provider fallback remains router-owned infrastructure behavior
- capability escalation remains governance-owned and replay-visible
- if the matrix cannot read it from `routing_override` and outcomes, it should
  not claim to know it

#### Acceptance

The system can produce a per-colony escalation report that distinguishes:

- no escalation
- manual capability escalation via `routing_override`
- final outcome and cost delta

### 2C. Internal Results Publication

Wave 38 should publish its own internal findings inside the repo even if the
numbers are mixed.

Deliverables may include:

- a benchmark readme
- a stored results template
- a short interpretation note of where the architecture helped and where it did
  not

This is internal publication, not external marketing.

---

## Pillar 3: Full Poisoning Defense And Bi-Temporal Knowledge

Wave 37 added the seams. Wave 38 turns them into a real substrate defense.

### 3A. Real Admission Scoring And Intake Policy

The current admission evaluator is pass-through with explanatory scoring only.
Wave 38 should make it materially affect intake and trust.

#### Implementation

Build a conservative admission policy that combines:

1. existing scanner findings from `memory_scanner.py`
2. future utility prior
3. factual confidence
4. semantic novelty
5. temporal recency
6. content-type prior
7. federation origin and peer trust

Use existing entry status surfaces where possible:

- `candidate`
- `active`
- `verified`
- `rejected`
- `stale`

Low-trust or suspicious entries should not silently become peers of verified
local knowledge.

#### Files

- `src/formicos/surface/admission.py`
- `src/formicos/surface/colony_manager.py`
- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/surface/memory_scanner.py`
- `tests/unit/surface/test_wave38_admission.py`

#### Expected Improvement

- poisoned or low-value knowledge is less likely to enter or dominate the
  knowledge field
- trust rationale becomes more meaningful than a cosmetic score

#### Risks

- over-rejecting useful knowledge
- making admission policy opaque
- breaking replay assumptions by mixing policy and projection carelessly

#### Guardrails

- keep the policy explicit and testable
- preserve operator-visible rationale
- prefer conservative gating over aggressive deletion

#### Acceptance

Admission scoring is no longer pass-through, suspicious entries can be blocked
or strongly demoted through existing status mechanisms, and the rationale is
inspectable.

### 3B. Federation Trust Hardening

The peer trust model exists. Wave 38 should make it harder for weak foreign
knowledge to outrank strong local knowledge.

#### Implementation

1. Strengthen asymmetric trust penalties for federated knowledge.
2. Review query-time trust discounting and hop handling.
3. Surface peer origin and trust context more clearly at retrieval time.
4. Ensure low-trust federated entries cannot dominate verified local entries by
   default unless semantic relevance is overwhelmingly stronger.

#### Files

- `src/formicos/surface/trust.py`
- `src/formicos/surface/federation.py`
- `src/formicos/surface/knowledge_catalog.py`
- `tests/unit/surface/test_wave38_federation_trust.py`

#### Acceptance

There are explicit tests showing that weak federated entries do not outrank
strong local verified entries under ordinary query conditions.

### 3C. Bi-Temporal Knowledge Surfacing

The knowledge graph already has temporal edge validity, but that temporal truth
is not yet a first-class operator-facing capability across the wider knowledge
surface.

#### Implementation

1. Treat event time / creation time as transaction time.
2. Surface validity windows separately as world-validity time where available.
3. For knowledge-graph edges:
   - expose `valid_at` and `invalid_at`
   - surface invalidation rather than silent overwrite
4. For institutional memory entries:
   - add optional validity fields in the existing entry payload / projection
     path where source truth supports them
   - default conservatively when no explicit validity window exists
5. Make contradiction handling prefer invalidation over disappearance where the
   underlying truth is "used to be true" rather than "never existed."

#### Files

- `src/formicos/adapters/knowledge_graph.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/surface/routes/knowledge_api.py`
- `frontend/src/components/knowledge-browser.ts`
- `tests/unit/adapters/test_knowledge_graph.py`
- `tests/unit/surface/test_wave38_bitemporal.py`

#### Risks

- pretending the whole knowledge layer is temporal when only part of it is
- accidental expansion into `core/` without an ADR
- confusing transaction time with validity time in operator surfaces

#### Guardrails

- label transaction time and validity time explicitly
- keep additive payload fields and read-model surfacing first
- if full typed memory-entry temporal fields require a core contract change,
  stop and ADR before editing `core/`

#### Acceptance

An operator can distinguish:

- when the system learned a fact
- when the fact was true
- when the fact was invalidated

at least for the temporalized parts of the knowledge surface.

---

## Priority Order

If Wave 38 must cut, cut from the bottom.

| Priority | Item | Pillar | Risk | Must / Should / Stretch |
|----------|------|--------|------|--------------------------|
| 1 | Real admission scoring | 3A | Medium | Must |
| 2 | Federation trust hardening | 3B | Medium | Must |
| 3 | External-style internal benchmark suite | 2A | Medium | Must |
| 4 | Escalation outcome matrix | 2B | Low | Must |
| 5 | NemoClaw tool-level specialist bridge | 1A | Medium | Must |
| 6 | A2A compatibility hardening | 1B | Medium | Must |
| 7 | Ecosystem operator docs | 1C | Low | Should |
| 8 | Bi-temporal edge surfacing | 3C | Medium | Should |
| 9 | Bi-temporal memory-entry validity windows | 3C | High | Stretch |
| 10 | Internal benchmark publication note | 2C | Low | Stretch |

The wave is not landed if it only has integrations without hardening, or
hardening without internal measurement.

---

## Team Assignment

### Team 1: Ecosystem Protocols And NemoClaw Bridge

Own:

- NemoClaw tool-level specialist integration
- A2A compatibility hardening
- Agent Card / protocol truth
- ecosystem operator docs

Primary files:

- `src/formicos/surface/routes/a2a.py`
- `src/formicos/surface/routes/protocols.py`
- `src/formicos/surface/structured_error.py`
- `src/formicos/surface/app.py`
- `src/formicos/engine/service_router.py` only if strictly additive
- `src/formicos/surface/queen_tools.py`
- `docs/A2A-TASKS.md`
- `docs/NEMOCLAW_INTEGRATION.md`

### Team 2: Internal Benchmarks And Escalation Matrix

Own:

- benchmark extension
- ablation outputs
- escalation outcome matrix
- internal results artifacts

Primary files:

- `tests/integration/test_wave37_stigmergic_loop.py`
- `tests/integration/test_wave38_benchmarks.py`
- `tests/integration/test_wave38_escalation_matrix.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/routes/api.py`
- `docs/waves/wave_38/internal_benchmarking.md`

### Team 3: Poisoning Defense And Bi-Temporal Knowledge

Own:

- real admission scoring
- federation trust hardening
- temporal knowledge surfacing

Primary files:

- `src/formicos/surface/admission.py`
- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/surface/federation.py`
- `src/formicos/surface/trust.py`
- `src/formicos/adapters/knowledge_graph.py`
- `src/formicos/surface/routes/knowledge_api.py`
- `frontend/src/components/knowledge-browser.ts`

### Overlap Seams

- `src/formicos/surface/routes/protocols.py`
  - Team 1 owns protocol truth and Agent Card updates
  - Team 3 does not touch it for trust-display work
- `src/formicos/surface/projections.py`
  - Team 2 owns escalation matrix additions
  - Team 3 owns temporal read-model additions if needed
  - reread before merge if both land
- `src/formicos/surface/knowledge_catalog.py`
  - Team 3 owns poisoning and temporal surfacing
  - Teams 1 and 2 should not widen retrieval semantics here in Wave 38

---

## What Wave 38 Does Not Include

- no model-level NemoClaw / `LLMPort` integration by default
- no governance-owned auto-escalation
- no earned autonomy
- no Aider adapter
- no public benchmark submission
- no silent conflation of provider fallback with capability escalation
- no casual `core/` expansion

Wave 38 is the ecosystem and internal-proof wave, not the learning wave and not
the proving wave.

---

## Wave 39 Hard Dependencies

Wave 39 depends on specific Wave 38 outputs.

- Earned autonomy depends on:
  - real internal benchmark evidence
  - escalation outcome matrix
  - continued operator behavior data from Wave 37
- Auto-escalation depends on:
  - governance-owned `routing_override` remaining the escalation seam
  - a clean dataset of start tier, escalated tier, round, cost, latency,
    quality, and outcome
- Model-level external agent wrapping depends on:
  - Wave 38 proving the tool-level boundary first
  - explicit decision not to hide side effects outside traceable colony state
- Wave 40 benchmark submission depends on:
  - Wave 38 internal benchmark evidence
  - Wave 39 adaptation and adapter work

---

## Smoke Test

1. Register a NemoClaw-backed specialist service and query it through
   `query_service`. Verify `ServiceQuerySent` / `ServiceQueryResolved` trace the
   call cleanly.
2. Read `/.well-known/agent.json` and `docs/A2A-TASKS.md`. Verify protocol
   truth matches actual route behavior and auth status.
3. Run the internal benchmark suite. Verify it can compare Wave 36 baseline,
   Wave 37 features, and Wave 38 slices with cost and wall-time reporting.
4. Manually escalate a colony through `routing_override`. Verify the escalation
   outcome matrix captures tier, reason, round, cost, latency, and outcome.
5. Attempt to ingest suspicious knowledge. Verify admission scoring is no
   longer pass-through and existing status mechanisms can demote or reject it.
6. Query knowledge where a weak federated entry competes with a strong local
   verified entry. Verify trust discounting prevents easy foreign dominance.
7. Inspect a temporalized knowledge item or graph edge. Verify the UI / API can
   distinguish learned-at time from valid-at / invalid-at time where available.
8. Full CI remains green.

---

## After Wave 38

FormicOS will have crossed the line from trusted local system to credible
ecosystem participant.

It will have:

- a real external specialist bridge through existing tool-level seams
- a more honest and harder-to-poison knowledge substrate
- stronger A2A protocol truth
- an internal benchmark story on external-style tasks
- the outcome matrix Wave 39 needs for learned escalation and configuration

Wave 39 can then focus on adaptation:

- earned autonomy
- governance-owned auto-escalation
- configuration optimization from accumulated outcomes
- Aider adapter engineering

Wave 40 can then spend public credibility on the benchmark claim with a cleaner
chain of evidence behind it.
