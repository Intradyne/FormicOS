This document compresses the Wave 45 plan into the smallest set of gates that
must be true before the wave can be accepted as landed.

Primary source of truth:
- [wave_45_plan.md](/c:/Users/User/FormicOSa/docs/waves/wave_45/wave_45_plan.md)

---

## Must Ship

### Gate 1: Proactive foraging is real and stays bounded

All of the following must be true:

1. At least the highest-value existing insight rules can trigger background
   foraging.
2. The proactive path reuses the existing Forager service loop.
3. The diagnostic layer stays pure; it does not become a new event emitter or
   network client.
4. Reactive foraging behavior does not regress.
5. A live maintenance/briefing-follow-through path actually calls the
   proactive dispatcher. A helper method plus tests is not enough.

Passing evidence:

- at least `_rule_stale_cluster` and `_rule_coverage_gap` can produce bounded
  forage signals
- the signal is consumed by a lightweight dispatcher or equivalent bridge
- `ForagerService` remains the service that emits `ForageRequested`
- the dispatcher is reachable from real runtime flow, not only unit tests
- no new event types were added just to support proactive wiring

### Gate 2: Competing hypotheses are operator-visible

All of the following must be true:

1. Stage 3 "competing" outcomes become visible in replay-derived state.
2. Retrieval surfaces the competing relationship when a competing entry is
   returned.
3. The operator can inspect the disagreement without reading raw transcripts.
4. No new frontend subsystem or event type was required to get there.
5. The competing state is rebuilt from a live code path, not just an
   isolated helper.

Passing evidence:

- projection state tracks competing relationships or equivalent replay-safe
  context
- `knowledge_catalog.py` annotates retrieval results with competing context
- the competing-state rebuild is actually invoked during normal operation
- the contradiction path remains compatible with existing resolution classes

### Gate 3: Source credibility affects admission provenance

All of the following must be true:

1. Web-sourced entries no longer give the same provenance signal to known
   authoritative domains and unknown domains.
2. The credibility signal feeds the existing admission path.
3. Existing domain overrides still work with the new tiering.
4. The change remains bounded and explainable.

Passing evidence:

- a small domain-tier mapping or equivalent signal exists
- the provenance dimension changes for known authoritative domains
- `ForagerDomainOverride` trust/distrust behavior still composes cleanly

### Gate 4: The wave completes without scope blowout

All of the following must be true:

1. No new event types were added.
2. No new subsystem or adapter was introduced.
3. New dependencies were avoided unless clearly justified.
4. The work remained focused on proof-critical carry-forwards from Waves 42-44.

Passing evidence:

- event union stays at 62
- packet scope remains inside the existing seams
- any gated or stretch item that lacked justification stayed cut

---

## Should Ship

### Gate 5: Search and fetch policy become more consistent

If search-through-egress consistency lands, it should:

1. reuse the existing search adapter interface
2. avoid introducing a new search subsystem
3. stay a bounded consistency upgrade, not a redesign

### Gate 6: Documentation tells the post-Wave-45 truth

If the docs pass lands, it should:

1. describe proactive foraging accurately if it shipped
2. describe competing-hypothesis surfacing accurately if it shipped
3. keep operator/deployment docs aligned to the accepted code
4. remove stale "not yet wired" or "still deferred" claims for code that is
   already live

### Gate 7: Domain-strategy projection tuning stays small

If projection tuning lands, it should:

1. improve success/failure count truth
2. avoid changing the event surface
3. remain a refinement, not a subsystem rewrite

---

## Gated / Stretch

### Gate 8: Agent-level topology prior lands only if the current planner supports it

If agent-level topology prior lands, it should:

1. consume already-available per-agent or per-group file scope
2. avoid planner or Queen-tool redesign
3. remain a local improvement to the current runner seam

If that input truth is not available, the correct outcome is to leave the
prior colony-level and document the gap.

### Gate 9: MinHash only lands if it solves visible noise

If MinHash near-duplicate detection lands, it should:

1. address real duplicate noise observed in Wave 44 foraging
2. remain bounded in implementation and dependency cost
3. avoid turning Wave 45 into a data-curation subsystem wave
