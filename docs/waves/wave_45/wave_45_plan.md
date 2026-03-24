**Wave:** 45 -- "The Complete Colony"

**Theme:** Close the highest-leverage carry-forwards from Waves 42-44 and
tighten the proof-critical seams. This is a consolidation wave, not a
capability wave.

**Intake rule (hard):**

- no brand-new subsystem
- no research imports just because they are interesting
- only pull in deferred items that materially improve the exact system
  Wave 46 will measure
- prefer bounded seam upgrades over broad rewrites
- if an item does not make the compounding curve, the three demos, or the
  audit trail materially better, it does not belong in this wave

**Prerequisite:** Wave 44 accepted. The post-44 system includes:

- EgressGateway with strict egress, rate limiting, robots.txt, domain
  allowlisting (393 lines)
- Level 1 AND Level 2 fetch pipeline with domain strategy memory (453 lines)
- Content quality scoring with 5 heuristic signals (261 lines)
- Web search adapter with pre-fetch relevance filtering (317 lines)
- ForagerService with full reactive service loop (926 lines)
- Reactive trigger detection in knowledge_catalog.py (lines 683-883)
- Reactive handoff wired in runtime.py (line 1074)
- Domain policy (trust/distrust/reset)
- 4 new events: ForageRequested, ForageCycleCompleted, DomainStrategyUpdated,
  ForagerDomainOverride (union at 62)
- Deterministic query templates for both reactive AND proactive trigger types
- Deduplication (SHA-256 exact hash)
- Admission bridge via MemoryEntryCreated with forager provenance
- Forager caste recipe in caste_recipes.yaml
- VCR recorded fixtures (Wave 43)
- Property-based replay tests (Wave 43)

**Contract target:** Wave 45 completes without expanding scope.

- no new event types (union stays at 62)
- no new subsystems or adapters
- no new dependencies unless clearly justified
- existing tests must continue passing

---

## What Wave 44 Already Shipped (removed from Wave 45 scope)

The provisional plan included items that landed in Wave 44:

- ~~Level 2 fetch fallback~~ -- landed: fetch_pipeline.py has full L1+L2 with
  trafilatura(favor_recall) and readability-lxml fallback
- ~~Pre-fetch relevance scoring~~ -- landed: web_search.py filter_results()
  used in forager.py at lines 424-435 and 799-817
- ~~Property-based replay tests~~ -- landed in Wave 43:
  test_wave43_replay_properties.py
- ~~VCR recorded fixtures~~ -- landed in Wave 43:
  test_wave43_recorded_fixtures.py

---

## What Is Actually Deferred

Grounded against the live post-44 tree:

### Gap 1: Proactive foraging is templated but not live-wired

ForagerService already handles proactive trigger strings (line 662:
`if trigger.startswith("proactive")`). Query templates exist for all proactive
trigger types (lines 86-95). But proactive_intelligence.py has ZERO
ForageRequested emission. The insight rules detect gaps and generate
KnowledgeInsight objects; they do not yet trigger foraging.

The wiring gap is: insight rule fires -> needs to emit ForageRequested (or
a lighter signal) -> ForagerService picks it up as a background forage cycle.
It is not enough for the dispatcher helper to exist in isolation; a live
maintenance or briefing-follow-through path must actually call it.

### Gap 2: No source credibility tiers

content_quality.py scores structural quality, spam signals, readability,
information density, and text-to-markup ratio. It does NOT distinguish
docs.python.org from random-blog.com. The admission provenance dimension
gets the same weight regardless of source authority.

### Gap 3: Contradiction Stage 3 is not yet live in replay-derived state

conflict_resolution.py produces "competing" outcomes (line 385-393) when
evidence is too close to resolve. But this only matters if replay-derived
state is actually rebuilt from a live path. It is not enough to add a helper
method on projections; the system must call that rebuild logic during normal
operation so knowledge_catalog.py can surface the tension during retrieval.
Until then, the operator cannot reliably see that two entries disagree.

### Gap 4: Topology prior is colony-level, not agent-level

_compute_structural_affinity (runner.py line 2089) explicitly comments
"For now all agents share the same target_files" (line 2114). Every agent
gets the same structural boost. The prior does not know which agent works
on which file.

### Gap 5: Search bypasses EgressGateway

web_search.py uses its own httpx.AsyncClient (lines 101-104, 172-175)
rather than routing through EgressGateway. The orchestrator noted this as
an intentional design choice, not a blocker. It means search requests do
not get the same rate limiting, domain policy, or robots.txt checking as
fetch requests.

### Gap 6: Domain-strategy projection tuning debt

The orchestrator noted domain-strategy projection updates are optimized
around level changes. Success/failure counts may not be perfectly current
in the projection. Minor tuning, not architectural.

### Gap 7: MinHash near-duplicate detection

Only SHA-256 exact hash deduplication exists. Near-duplicates (rephrased
content from multiple sources) are not caught.

---

## Bucket 1: Forager Completion

### 1A. Proactive foraging triggers (P3) -- Must

Wire the existing insight rules to emit forage signals:

- `_rule_stale_cluster` -> ForageRequested with trigger
  "proactive:stale_cluster"
- `_rule_coverage_gap` -> ForageRequested with trigger
  "proactive:coverage_gap"
- `_rule_confidence_decline` -> ForageRequested with trigger
  "proactive:confidence_decline"

The templates already exist in forager.py (lines 86-95). The ForagerService
already handles proactive mode (line 662). The only missing piece is the
bridge from proactive_intelligence.py to the forager signal path.

Two implementation options:

**Option A (simpler):** The insight rules add a `forage_signal` dict to
their KnowledgeInsight output. The briefing consumer (or a new lightweight
dispatcher) checks for forage signals and calls
`forager_service.handle_forage_signal()`. This keeps proactive_intelligence
pure (no event emission from a diagnostic module).

**Option B (direct):** The insight rules emit ForageRequested directly
through a provided event emitter. This is more coupled but avoids an
intermediate consumer.

Prefer Option A. It keeps the diagnostic layer clean and the forager
service as the sole emitter of ForageRequested events. The acceptance bar is
live behavior, not just a dispatcher method plus tests.

**Seams:** `surface/proactive_intelligence.py` (MODIFY: add forage_signal
to relevant insight outputs), `surface/forager.py` or a lightweight
dispatcher (MODIFY: consume proactive forage signals).

### 1B. Source credibility tier system -- Must

Add a domain-to-trust-tier mapping:

| Tier | Score | Examples |
|------|-------|---------|
| T1 | 1.0 | docs.python.org, developer.mozilla.org, official docs |
| T2 | 0.85 | arxiv.org, .edu/.gov, major engineering blogs |
| T3 | 0.70 | Stack Overflow accepted answers, Wikipedia |
| T4 | 0.50 | Medium, dev.to, conference talks |
| T5 | 0.30 | Unknown domains (default) |

The tier feeds into the admission provenance dimension when preparing
forager entries. Operator can override via existing ForagerDomainOverride
(trust action promotes, distrust blocks).

Implementation: a small dict or config in content_quality.py or forager.py.
Consumed by `prepare_forager_entry()` (forager.py line 242) when building
the admission-ready entry dict.

**Seams:** `adapters/content_quality.py` or `surface/forager.py` (MODIFY:
add tier lookup), `surface/forager.py` (MODIFY: consume tier in provenance
mapping).

### 1C. Search-through-EgressGateway consistency -- Should

Route web_search.py HTTP requests through the EgressGateway client instead
of creating standalone httpx.AsyncClient instances. This gives search
requests the same rate limiting and policy enforcement as fetch requests.

The web_search.py already accepts an `http_client` parameter (lines 73,
99, 170). Passing the EgressGateway's internal httpx client (or a
lightweight wrapper) at construction time in app.py would close this gap
without changing web_search.py's interface.

**Seams:** `surface/app.py` (MODIFY: inject EgressGateway-backed client
into search adapter construction).

---

## Bucket 2: Epistemic/Audit Completion

### 2A. Contradiction Stage 3: Competing hypothesis surfacing -- Must

conflict_resolution.py already produces "competing" outcomes. Make them
visible:

- Add `competing_with: list[str]` field to the knowledge projection model
- When resolve_classified returns Resolution.competing, tag both entries
  in the projection
- When retrieval surfaces one competing entry, annotate the result with
  the competing alternative's ID and confidence
- The operator resolves via existing pin/mute/invalidate

This directly strengthens the Wave 46 audit demo: "these two entries
disagree, the system kept both, here is what each claims."

**Scope guard:** Projection tracking + retrieval annotation only. No new
frontend components. The frontend can display the `competing_with` field
if present; no new surfaces.

**Seams:** `surface/projections.py` (MODIFY: competing_with tracking on
knowledge entries), `surface/knowledge_catalog.py` (MODIFY: annotate
retrieval results with competing context), and the existing contradiction
insight path rooted in `surface/proactive_intelligence.py` or a new bounded
consumer that reads `resolve_classified()` results through the existing
briefing/insight flow (Team 2 reads this output but does not modify the
detection logic).

---

## Bucket 3: Proof-Readiness

### 3A. Agent-level topology prior -- Gated

**Gate:** Only land if the Queen's planner already provides per-agent or
per-group file scope that `_compute_structural_affinity()` can consume
without planner changes.

If the gate passes: split `target_files` by agent assignment, compute
structural affinity per-agent rather than per-colony. Agents working on
files with import dependencies get stronger inter-agent edges.

If the gate does not pass: document that the topology prior remains
colony-level and note this as future work. This is tuning debt, not a
measurement blocker.

**Seams:** `engine/runner.py` (MODIFY: `_compute_structural_affinity`).

### 3B. Domain-strategy projection tuning -- Should

Ensure domain-strategy projection accurately reflects current success and
failure counts, not just level-change snapshots. Small projection handler
refinement.

**Seams:** `surface/projections.py` (MODIFY: DomainStrategyUpdated handler).

### 3C. MinHash near-duplicate detection -- Stretch

Add datasketch-based MinHash with LSH for Jaccard similarity >= 0.80 on
fetched content chunks. Catches rephrased content from multiple sources
that exact hash misses.

Only land if the forager is producing visible near-duplicate noise in
testing. If exact hash is catching enough, defer.

**Seams:** `surface/forager.py` (MODIFY: dedup path).

### 3D. Documentation truth pass -- Should

Update all operator-facing docs to reflect the complete post-Wave-44
system:

- CLAUDE.md: event union 62, forager capability, Waves 41-44 features,
  current file sizes
- AGENTS.md: forager caste and tools
- OPERATORS_GUIDE.md: forager controls, domain trust/distrust, budget
  enforcement, workspace isolation
- KNOWLEDGE_LIFECYCLE.md: forager input channel, proactive foraging
  (if 1A lands), competing hypothesis surfacing (if 2A lands)
- DEPLOYMENT.md: EgressGateway config, search backend setup, forager
  budget limits

---

## Priority Order (cut from the bottom)

| Priority | Item | Bucket | Class |
|----------|------|--------|-------|
| 1 | Proactive foraging triggers (P3) | 1 | Must |
| 2 | Contradiction Stage 3 competing hypothesis surfacing | 2 | Must |
| 3 | Source credibility tier system | 1 | Must |
| 4 | Documentation truth pass | 3 | Should |
| 5 | Search-through-EgressGateway consistency | 1 | Should |
| 6 | Domain-strategy projection tuning | 3 | Should |
| 7 | Agent-level topology prior | 3 | Gated |
| 8 | MinHash near-duplicate detection | 3 | Stretch |

---

## Team Assignment

### Team 1: Forager Completion

Owns Bucket 1: proactive triggers, source credibility, search-egress
consistency.

Primary files:

- `surface/proactive_intelligence.py` (P3 signal emission)
- `surface/forager.py` (P3 handling, credibility tier consumption)
- `adapters/content_quality.py` (credibility tier lookup)
- `surface/app.py` (search-egress wiring, Should)

### Team 2: Epistemic Completion + Proof-Readiness

Owns Bucket 2 (Stage 3) + Bucket 3A (topology, gated) + 3B (projection
tuning).

Primary files:

- `surface/projections.py` (competing_with tracking, domain-strategy tuning)
- `surface/knowledge_catalog.py` (competing hypothesis retrieval annotation)
- `engine/runner.py` (agent-level prior, gated)

### Team 3: Documentation

Owns Bucket 3D.

Primary files:

- CLAUDE.md, AGENTS.md, OPERATORS_GUIDE.md, KNOWLEDGE_LIFECYCLE.md,
  DEPLOYMENT.md, README.md

### Overlap

- `surface/forager.py`: Team 1 only
- `surface/projections.py`: Team 2 only
- `surface/knowledge_catalog.py`: Team 2 only
- `surface/proactive_intelligence.py`: Team 1 only

No shared files between teams. Clean separation.

---

## What Wave 45 Does NOT Include

- no new event types (union stays at 62)
- no new subsystems or adapters
- no Playwright / Level 3 browser rendering
- no SearXNG deployment
- no semantic deduplication
- no Thompson Sampling for query strategies
- no learned routing from outcome history
- no convergence prediction model
- no Bayesian/DS fusion (Stage 4 contradictions)
- no benchmark runs or public proof (Wave 46)
- no Level 2 fetch (already shipped in Wave 44)
- no pre-fetch relevance scoring (already shipped in Wave 44)
- no property-based replay tests (already shipped in Wave 43)
- no VCR recorded fixtures (already shipped in Wave 43)

---

## Smoke Test

1. proactive foraging triggers fire from at least _rule_stale_cluster and
   _rule_coverage_gap, producing background forage cycles
2. source credibility tiers distinguish docs.python.org from unknown domains
   in admission provenance scoring
3. competing hypothesis entries are tagged from a live rebuild path in
   projections and annotated during retrieval
4. operator-facing docs reflect the complete post-Wave-44 system
5. no event union expansion beyond 62
6. full CI remains clean

---

## After Wave 45

FormicOS is complete. The Forager actively maintains knowledge through both
reactive and proactive channels. Contradictions are surfaced as visible
competing hypotheses. Source credibility feeds into admission trust. The
documentation tells the truth about the complete system.

Wave 46 measures, demos, polishes, and publishes on the finished system:
compounding curve, ablation, three public demos (live, benchmark, audit),
and optional publication.

**empower -> deepen -> harden -> forage -> complete -> prove**
