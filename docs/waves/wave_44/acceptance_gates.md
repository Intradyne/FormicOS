This document compresses the Wave 44 plan into the smallest set of gates that
must be true before the wave can be accepted as landed.

Primary source of truth:
- [wave_44_plan.md](/c:/Users/User/FormicOSa/docs/waves/wave_44/wave_44_plan.md)

---

## Must Ship

### Gate 1: Controlled egress and bounded fetch exist

All of the following must be true:

1. A real `EgressGateway` exists and enforces bounded outbound HTTP policy.
2. A Level 1 fetch path exists using `httpx` plus content extraction.
3. The first fetch path works without requiring browser automation.
4. Strict egress is real: v1 fetches only search-result URLs plus explicit
   operator overrides.

Passing evidence:

- an adapter enforces rate/size/time/domain controls
- Level 1 extraction works on real HTML pages
- no Playwright dependency is required for Must-ship acceptance
- caller-side or gateway-side checks prevent arbitrary URL fetches

### Gate 2: Search and query formation are real but still bounded

All of the following must be true:

1. The system can execute a simple web search through a bounded backend.
2. Query formation is deterministic in v1.
3. Search-result filtering exists so fetch budget is not spent blindly.
4. Retrieval only triggers foraging; it does not perform network I/O inline.

Passing evidence:

- a search adapter returns structured results
- deterministic templates are visible in code/tests
- a relevance or bounded filter exists before fetch
- `knowledge_catalog.py` only detects and hands off

### Gate 3: Web knowledge enters the ordinary lifecycle conservatively

All of the following must be true:

1. Exact deduplication exists for fetched content.
2. Forager-admitted output reuses `MemoryEntryCreated`.
3. The existing seven admission dimensions are still the gate.
4. Web-sourced entries start with cautious priors and auditable provenance.

Passing evidence:

- duplicated fetched content can be rejected or coalesced
- no `KnowledgeCandidateProposed` event was added
- admission mapping is visible and tested
- resulting entries show source/fetch metadata

### Gate 4: The Forager is a real colony capability

All of the following must be true:

1. Reactive foraging exists for low-confidence live-task gaps.
2. A Forager caste/config path exists.
3. Domain strategy memory is replayable state.
4. Operators can control domain trust/distrust/reset behavior.

Passing evidence:

- a reactive trigger path exists
- the config surface includes the Forager
- domain strategy state survives replay
- operator domain overrides actually affect fetch behavior

### Gate 5: The replay surface stays minimal and justified

All of the following must be true:

1. Exactly 4 new event types were added.
2. Existing event types were not mutated just to fit the Forager.
3. `MemoryEntryCreated` was reused for admitted entries.
4. Search/fetch/rejection detail stayed log-only unless a real replay blocker
   forced something stronger.

Passing evidence:

- the union grows from 58 to 62, not beyond
- the new events are limited to request/completion/strategy/override state
- individual search and fetch records are audit logs, not automatic event
  sprawl

---

## Should Ship

### Gate 6: Level 2 fetch fallback lands without turning into browser work

If Level 2 lands, it should:

1. remain extractor-based
2. stay bounded to obvious fallback cases
3. avoid smuggling Playwright into the Must path

### Gate 7: Proactive foraging remains secondary to reactive value

If proactive triggers land, they should:

1. be driven by the existing insight rules
2. stay interruptible and lower priority than reactive work
3. avoid turning Wave 44 into a general autonomous browsing wave

### Gate 8: Extra quality/dedup intelligence stays bounded

If MinHash, stronger credibility tiers, or richer relevance logic land, they
should:

1. improve the cautious-admission path
2. avoid introducing major new infrastructure
3. remain explainable to operators and reviewers

---

## Non-Goals Check

Wave 44 should **not** require any of the following for acceptance:

- Playwright
- SearXNG
- semantic deduplication
- strategy-bandit query selection
- maintenance-mode web sweeps
- public proof or benchmark work
