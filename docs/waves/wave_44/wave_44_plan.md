**Wave:** 44 -- "The Foraging Colony"

**Theme:** Give the colony the ability to actively seek knowledge from the
web. Wave 42 built the abstraction substrate. Wave 43 hardened it for real
deployment. Wave 44 adds the second compounding source: the colony learns not
just from what it does, but from what it seeks.

This is a **Forager foundation** wave, not the full research system. The
governing discipline for Wave 44 is simple:

- build a real web-acquisition substrate before layering sophistication
- reuse the existing knowledge lifecycle instead of inventing a parallel one
- keep web knowledge cautious by default
- keep retrieval fast and deterministic by handing off to foraging rather than
  doing network I/O inline
- keep the replay surface minimal and justified

Wave 44 is still a build wave. Wave 45 proves. Wave 45.5 polishes.

**Prerequisite:** Wave 43 is accepted. In particular:

- sandbox hardening and workspace isolation are live
- `BudgetEnforcer` is wired into the live runtime/spawn path
- SQLite WAL PRAGMAs are deployed
- deployment docs describe shipped code honestly

**Contract target:** Wave 44 adds a new input channel to the existing
knowledge lifecycle without changing the lifecycle itself.

- exactly **4** new event types are added to the closed union
- no existing event types are changed
- no changes are made to Queen planning or governance logic
- forager-sourced knowledge enters through the existing
  `MemoryEntryCreated` path at `candidate` status
- the existing admission-scoring pipeline remains the terminal gate
- web-sourced content starts with conservative priors and never outranks
  colony-earned knowledge by default

**Architectural constraint:** The Forager runs in the main container, not in
sandbox containers. All external requests flow through a new
`EgressGateway` adapter with rate limits, domain controls, and strict fetch
rules. In v1, the system may fetch only URLs returned by the search layer,
plus explicit operator-approved overrides.

**The Princeton connection:** The abstraction substrate now becomes actively
self-improving. "Abstraction first, then generalization" grows into active
abstraction acquisition: the colony can detect a knowledge gap and go looking
for a cautious, auditable answer.

---

## Current Repo Truth At Wave Start

Wave 44 should start from the live repo, not from the reference architecture
as if it already existed.

### What already exists

1. **`httpx` is already a dependency**
   - [pyproject.toml](/c:/Users/User/FormicOSa/pyproject.toml) already
     includes `httpx>=0.28,<1.0`.

2. **There is no live web-acquisition substrate**
   - There is no `EgressGateway`, no fetch pipeline, no search adapter, no
     forager surface module, and no forager-specific event types in `src/`.

3. **The proactive diagnostic layer is real**
   - [proactive_intelligence.py](/c:/Users/User/FormicOSa/src/formicos/surface/proactive_intelligence.py)
     is 1,514 lines and already contains 14 deterministic insight rules.
   - Several rules are natural foraging triggers: confidence decline, stale
     clusters, coverage gaps, and knowledge ROI.

4. **Admission scoring already exists and should be reused**
   - [admission.py](/c:/Users/User/FormicOSa/src/formicos/surface/admission.py)
     already scores entries across the existing seven dimensions:
     confidence, provenance, scanner, federation, observation mass,
     content type, and recency.

5. **The knowledge lifecycle is already mature**
   - Candidate -> active -> verified already exists, along with decay,
     Thompson-style retrieval, co-occurrence reinforcement, and operator
     overrides.

6. **`MemoryEntryCreated` already provides the right entry bridge**
   - [events.py](/c:/Users/User/FormicOSa/src/formicos/core/events.py#L685)
     already carries the full serialized entry dict.
   - That means forager-admitted entries can reuse the normal lifecycle entry
     path instead of introducing a new "knowledge proposed" event type.

7. **Operator co-authorship already exists**
   - Pin, mute, annotate, and invalidate are already replayable.
   - Wave 44 extends that idea to domain-level control rather than inventing a
     new operator model.

8. **The tool-registration pattern already exists**
   - [tool_dispatch.py](/c:/Users/User/FormicOSa/src/formicos/engine/tool_dispatch.py)
     is 469 lines and is the existing pattern for tool or service dispatch
     integration if a bounded hook is needed.

9. **The event union is currently stable**
   - [events.py](/c:/Users/User/FormicOSa/src/formicos/core/events.py) is
     1,121 lines and the union is at 58 event types before Wave 44.

10. **Budget and deployment hardening now exist**
   - Wave 43 established the operational baseline. Wave 44 should use that
     substrate, not work around it.

### What does not exist

- no egress-control adapter
- no HTML -> clean-text extraction pipeline
- no search integration
- no content-quality scoring for web material
- no domain strategy memory
- no forager caste recipe
- no forager event surface

This wave builds the whole Forager foundation from scratch.

---

## Why This Wave

The colony currently has a one-sided knowledge substrate. It learns from what
it does: task work produces entries, entries are scored, the substrate
reinforces what proves useful, and low-confidence knowledge fades. But when
retrieval exposes a gap, the system still has no direct response other than
"try again with what we already know."

Wave 44 closes that gap. It gives the colony a bounded way to:

1. detect that a gap matters
2. search for relevant public information
3. extract and score that information conservatively
4. admit only what clears the existing lifecycle gate
5. let usage decide whether the new knowledge earns trust

This is the smallest credible version of active knowledge seeking. It is not
crawling, not autonomous browsing, and not a generalized research agent. It is
a cautious, auditable acquisition channel feeding the same substrate that Waves
36-43 already built.

---

## Pillar 1: Web Acquisition Substrate

The Forager cannot exist without a controlled egress path and a bounded
content-extraction stack.

### 1A. `EgressGateway` adapter

Build [egress_gateway.py](/c:/Users/User/FormicOSa/src/formicos/adapters/egress_gateway.py)
as a thin `httpx`-based HTTP adapter that enforces:

- domain allowlist and denylist controls
- request rate limits
- maximum response size
- default timeout
- an honest user-agent string
- `robots.txt` checking and caching

Strict rule for v1:

- fetch only URLs that came from the search layer
- plus explicit operator-approved domain overrides

The gateway should be policy and transport only. It should **not** become the
place where query formation, search orchestration, admission logic, or
knowledge writes happen.

### 1B. Graduated fetch pipeline

Build [fetch_pipeline.py](/c:/Users/User/FormicOSa/src/formicos/adapters/fetch_pipeline.py)
with bounded escalation.

**Level 1 (Must):**

- `httpx` GET through `EgressGateway`
- content-type detection
- `trafilatura` extraction in Markdown mode for HTML pages
- plaintext and JSON bypass extraction

**Level 2 (Should):**

- fallback `trafilatura(favor_recall=True)`
- then `readability-lxml`

**Level 3 (Defer):**

- Playwright / browser rendering

Escalation should be driven by simple quality failures such as:

- extracted text too short
- obviously shell-like pages
- text-to-markup ratio too low
- common noscript / hydration markers

### 1C. Domain strategy memory

The Forager should learn what fetch level works per domain, but the first
version should stay small and legible.

Track, at minimum:

- preferred level
- success count
- failure count
- last-updated timestamp

Expected behavior:

- after repeated failures, escalate
- after enough time without contact, allow bounded re-probing downward
- allow simple pattern defaults for known domains

Important boundary:

- Team 1 owns the strategy logic and data shape
- Team 3 owns the replay event definition and projection state
- Team 2 owns the surface/orchestration path that emits those events

### 1D. Content-quality scoring without LLMs

Build [content_quality.py](/c:/Users/User/FormicOSa/src/formicos/adapters/content_quality.py)
with a cheap heuristic score that is explainable and testable.

Signals should remain bounded and O(n), for example:

- text-to-markup ratio
- information density
- readability range
- structural quality
- spam / SEO indicators

The resulting score should feed the **scanner** dimension of admission.

### Primary seams

- [egress_gateway.py](/c:/Users/User/FormicOSa/src/formicos/adapters/egress_gateway.py)
  - CREATE
- [fetch_pipeline.py](/c:/Users/User/FormicOSa/src/formicos/adapters/fetch_pipeline.py)
  - CREATE
- [content_quality.py](/c:/Users/User/FormicOSa/src/formicos/adapters/content_quality.py)
  - CREATE
- [pyproject.toml](/c:/Users/User/FormicOSa/pyproject.toml)
  - MODIFY for extraction dependencies only
- `tests/unit/adapters/`
  - CREATE/MODIFY for gateway, fetch, and quality tests

---

## Pillar 2: Search + Deterministic Query Formulation

Wave 44 needs search, but it does not need a research-grade search stack yet.

### 2A. Simple search backend

Start with the smallest viable backend.

Acceptable v1 paths:

- a simple DuckDuckGo-style HTML search path
- a Serper-backed path if the operator provides credentials

Requirements:

- keep the adapter pluggable
- do **not** require SearXNG deployment for Wave 44 acceptance
- prefer `httpx`-based integration over new heavy dependencies if possible

### 2B. Deterministic query templates

Start with deterministic templates. Do **not** make v1 query formulation
depend on LLM rewriting, HyDE, multi-query generation, or a strategy bandit.

Examples:

- stale entry -> `"{topic} latest {year}"`
- prediction error -> `"{topic} {error_context}"`
- low-confidence cluster -> `"{domain} tutorial reference"`
- coverage gap -> `"{task_topic} how to {task_action}"`

The point of v1 is not clever query generation. The point is to establish an
auditable path from gap signal to bounded web search.

### 2C. Pre-fetch relevance filtering

Before spending fetch budget, apply a bounded relevance filter to search
results. This can stay simple in v1:

- query/snippet overlap
- freshness cues
- crude domain credibility
- optional lightweight similarity checks

This protects budget and reduces pointless fetches.

### Primary seams

- [web_search.py](/c:/Users/User/FormicOSa/src/formicos/adapters/web_search.py)
  - CREATE
- [forager.py](/c:/Users/User/FormicOSa/src/formicos/surface/forager.py)
  - CREATE for query formation + forage-cycle orchestration
- `tests/unit/adapters/`
  - CREATE/MODIFY for search adapter tests
- `tests/unit/surface/`
  - CREATE/MODIFY for forager query/orchestration tests

---

## Pillar 3: Content-to-Knowledge Bridge

The Forager does not get a privileged admission path. It must translate fetched
content into ordinary candidate entries.

### 3A. Chunking and entry preparation

Use a bounded recursive chunking approach with overlap. Keep the first version
practical and cheap rather than trying to perfect semantic chunking.

### 3B. Deduplication

**Must:** exact-hash deduplication on normalized text

**Should:** MinHash near-duplicate detection if it stays bounded

**Defer:** semantic deduplication

### 3C. Admission bridge

Map forager output into the existing seven admission dimensions.

Conservative defaults matter:

- confidence starts low-to-moderate, not high
- provenance comes from a simple domain-tier mapping
- scanner comes from content-quality scoring
- federation and observation mass start near zero
- recency uses extracted page metadata where available

Important invariant:

- if a fetched entry clears admission, it should be written through the normal
  `MemoryEntryCreated` path as a `candidate`
- do **not** add a parallel "proposed knowledge" event

### 3D. Provenance metadata

Forager-origin entries should carry auditable metadata inside the entry dict,
for example:

- `source_url`
- `fetch_timestamp`
- `fetch_level`
- `forager_trigger`
- `forager_query`
- `quality_score`

This is enough to tell the operator what was found and why, without inventing
a new storage substrate.

### Primary seams

- [forager.py](/c:/Users/User/FormicOSa/src/formicos/surface/forager.py)
  - EXTEND for chunking + admission bridge
- [admission.py](/c:/Users/User/FormicOSa/src/formicos/surface/admission.py)
  - MODIFY only if a bounded hook is needed for forager provenance
- `tests/unit/surface/`
  - CREATE/MODIFY for admission and entry-preparation tests

---

## Pillar 4: Triggers, Caste, and Operator Controls

This is where the Forager becomes a real colony capability rather than just an
adapter stack.

### 4A. Reactive trigger (Must)

Reactive foraging is the highest-value first trigger.

When retrieval exposes low-confidence knowledge in a live task:

- `knowledge_catalog.py` detects the condition
- it requests foraging via the bounded forager path
- the actual search/fetch cycle runs elsewhere

Hard rule:

- `knowledge_catalog.py` must **not** become the place that performs network
  I/O inline

The retrieval path stays fast and deterministic. The foraging path can run in
parallel or as a follow-up bounded workflow.

### 4B. Forager caste recipe

Add a Forager caste/config recipe so the capability exists as a real colony
track rather than an invisible internal helper.

The recipe should reflect v1 truth:

- main-container / network-enabled operation
- no sandbox code-execution tools
- bounded search/fetch budget
- only the minimal capabilities needed for foraging

### 4C. Operator domain controls

Add domain-level operator control via a new replayable override event:

- `trust`
- `distrust`
- `reset`

This extends the existing operator co-authorship model without inventing a new
governance system.

### 4D. Proactive triggers (Should)

If reactive foraging lands cleanly, wire selected proactive rules as background
triggers:

- stale clusters
- confidence decline
- coverage gaps
- knowledge ROI

These should remain bounded, interruptible, and strictly lower priority than
reactive or operator-directed foraging.

### Primary seams

- [forager.py](/c:/Users/User/FormicOSa/src/formicos/surface/forager.py)
  - EXTEND for trigger logic and cycle orchestration
- [knowledge_catalog.py](/c:/Users/User/FormicOSa/src/formicos/surface/knowledge_catalog.py)
  - MODIFY for reactive trigger detection only
- [caste_recipes.yaml](/c:/Users/User/FormicOSa/config/caste_recipes.yaml)
  - MODIFY for the Forager recipe
- `tests/unit/surface/`
  - CREATE/MODIFY for trigger and operator-control behavior

---

## Pillar 5: Event Schema and Replay Surface

Wave 44 should add the smallest replay surface that still makes the Forager
auditable and stateful.

### First-class events (exactly 4)

1. **`ForageRequested`**
   - replay-critical because the system decided to forage
   - carries mode, reason/gap, limits, and linkage context

2. **`ForageCycleCompleted`**
   - replay-critical summary of what the cycle accomplished
   - useful for projections, operator views, and auditability

3. **`DomainStrategyUpdated`**
   - replay-critical because learned fetch strategy is durable state

4. **`ForagerDomainOverride`**
   - replay-critical because it is an operator action that must survive replay

### What stays log-only in v1

- individual search requests
- individual fetch attempts
- security/content rejections

These are useful audit details, but they do not need to become first-class
replay state in Wave 44.

### The non-negotiable reuse rule

- admitted forager output reuses `MemoryEntryCreated`
- do **not** add `KnowledgeCandidateProposed`
- do **not** add fetch/search/rejection events just because they are
  interesting to log

### Primary seams

- [events.py](/c:/Users/User/FormicOSa/src/formicos/core/events.py)
  - MODIFY for the 4 new event types only
- [projections.py](/c:/Users/User/FormicOSa/src/formicos/surface/projections.py)
  - MODIFY for domain-strategy and forage-cycle projection state
- `tests/unit/surface/`
  - CREATE/MODIFY for projection handlers and replay expectations

---

## Priority Order (Cut From The Bottom)

| Priority | Item | Pillar | Class |
|----------|------|--------|-------|
| 1 | `EgressGateway` adapter | 1 | Must |
| 2 | Level 1 fetch pipeline (`httpx` + `trafilatura`) | 1 | Must |
| 3 | Content-quality scoring (no LLM) | 1 | Must |
| 4 | Simple search backend | 2 | Must |
| 5 | Deterministic query templates | 2 | Must |
| 6 | 4 first-class forager events | 5 | Must |
| 7 | Exact-hash deduplication | 3 | Must |
| 8 | Admission bridge via `MemoryEntryCreated` | 3 | Must |
| 9 | Reactive trigger handoff | 4 | Must |
| 10 | Forager caste recipe | 4 | Must |
| 11 | Domain strategy memory | 1 | Must |
| 12 | Operator domain controls | 4 | Must |
| 13 | Level 2 fetch fallback | 1 | Should |
| 14 | Pre-fetch relevance filtering | 2 | Should |
| 15 | Proactive triggers | 4 | Should |
| 16 | MinHash near-duplicate detection | 3 | Should |
| 17 | Source credibility tier system | 3 | Should |
| 18 | Serper secondary backend | 2 | Stretch |
| 19 | SearXNG self-hosting | 2 | Defer |
| 20 | Level 3 browser rendering | 1 | Defer |
| 21 | Semantic deduplication | 3 | Defer |
| 22 | Thompson Sampling over query strategies | 2 | Defer |

---

## Team Assignment

### Team 1: Web Acquisition Substrate

Owns:

- Pillar 1
- fetch/extraction dependency additions needed for Pillar 1

Primary files:

- [egress_gateway.py](/c:/Users/User/FormicOSa/src/formicos/adapters/egress_gateway.py)
- [fetch_pipeline.py](/c:/Users/User/FormicOSa/src/formicos/adapters/fetch_pipeline.py)
- [content_quality.py](/c:/Users/User/FormicOSa/src/formicos/adapters/content_quality.py)
- [pyproject.toml](/c:/Users/User/FormicOSa/pyproject.toml)
- `tests/unit/adapters/`

This team owns transport, extraction, and quality. It does **not** own the
knowledge lifecycle, event schema, or surface orchestration.

### Team 2: Search, Admission Bridge, and Triggers

Owns:

- Pillars 2-4
- the main `forager.py` surface orchestration path

Primary files:

- [web_search.py](/c:/Users/User/FormicOSa/src/formicos/adapters/web_search.py)
- [forager.py](/c:/Users/User/FormicOSa/src/formicos/surface/forager.py)
- [knowledge_catalog.py](/c:/Users/User/FormicOSa/src/formicos/surface/knowledge_catalog.py)
- [admission.py](/c:/Users/User/FormicOSa/src/formicos/surface/admission.py)
- [caste_recipes.yaml](/c:/Users/User/FormicOSa/config/caste_recipes.yaml)
- `tests/unit/surface/`
- `tests/integration/`

This team owns the intelligence and handoff path. It consumes Team 1's
substrate and Team 3's event definitions.

### Team 3: Event Schema, Projections, and Visibility

Owns:

- Pillar 5
- forager projection state
- docs that explain the capability truthfully

Primary files:

- [events.py](/c:/Users/User/FormicOSa/src/formicos/core/events.py)
- [projections.py](/c:/Users/User/FormicOSa/src/formicos/surface/projections.py)
- [KNOWLEDGE_LIFECYCLE.md](/c:/Users/User/FormicOSa/docs/KNOWLEDGE_LIFECYCLE.md)
- [OPERATORS_GUIDE.md](/c:/Users/User/FormicOSa/docs/OPERATORS_GUIDE.md)
- [CLAUDE.md](/c:/Users/User/FormicOSa/CLAUDE.md)
- `tests/unit/surface/`

This team owns the replay surface, operator-visible summaries, and minimal docs
updates tied to what actually lands.

### Overlap seams

- `forager.py`
  - Team 2 owns the file
  - Team 3 owns the event definitions it emits
- domain strategy memory
  - Team 1 owns the pure strategy logic
  - Team 2 owns the surface path that applies updates
  - Team 3 owns the replay event and projection state
- `knowledge_catalog.py`
  - Team 2 may add detection and handoff only
  - it must not absorb network/search logic

---

## What Wave 44 Does Not Include

- no Playwright / Level 3 browser rendering
- no SearXNG deployment
- no semantic deduplication
- no Thompson Sampling over query strategies
- no maintenance-mode foraging
- no crawling or spidering
- no authenticated web access
- no multi-forager coordination
- no claim-check blob storage
- no changes to Queen planning or governance logic
- no changes to existing event types
- no public benchmarks, demos, or publication work

---

## Smoke Test

1. `EgressGateway` enforces rate limits and domain controls on outbound HTTP.
2. Level 1 fetch extracts clean markdown from multiple page types.
3. Content-quality scoring produces stable, non-LLM scores.
4. Search returns results for a simple technical query.
5. Deterministic query templates produce a query from a real gap signal.
6. Exact-hash dedup catches duplicated fetched content.
7. Admitted forager entries are created through `MemoryEntryCreated` at
   `candidate` status.
8. Admission mapping gives web content conservative priors and visible
   provenance.
9. Low-confidence retrieval triggers a foraging request without performing
   network I/O inline in `knowledge_catalog.py`.
10. Domain strategy memory updates and replays correctly.
11. Operator domain distrust blocks future fetches for that domain.
12. Exactly 4 new event types exist and all have projection handlers.
13. Forager provenance metadata is visible on resulting entries.
14. Existing lifecycle, retrieval, and admission tests continue to pass.
15. Full CI remains clean.

---

## After Wave 44

FormicOS now has two compounding knowledge sources:

1. task experience
2. active web foraging

The colony can detect a gap, look outward for a bounded public answer, extract
it cautiously, admit it through the same lifecycle as any other candidate, and
let usage decide whether it deserves trust.

That makes Wave 45 a much stronger proof wave. The question is no longer only
"does the colony remember?" It becomes:

- does the colony improve when it both remembers and forages?
- does reactive foraging reduce failure on real tasks?
- does the cautious admission path keep the second knowledge source honest?

**The system measured in Wave 45 should be the system that learned from work in
Waves 36-42, survived production hardening in Wave 43, and gained bounded web
foraging in Wave 44.**
