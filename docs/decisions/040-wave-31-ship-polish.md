# ADR-040: Wave 31 Ship Polish Decisions

**Status:** Accepted
**Date:** 2026-03-17
**Wave:** 31

---

## Context

Wave 31 is a polish wave. The system at Wave 30 has workflow threads, thread-scoped knowledge, Thompson Sampling retrieval, Bayesian confidence evolution, deterministic maintenance services, and LLM-confirmed dedup. Wave 31 makes this demonstrable: auto-continuing workflow steps, agent transcript search, documentation, test coverage, and edge case hardening. No new events. No new architectural concepts.

---

## D1. Step continuation appends to follow_up_colony summary, not a separate message

**Decision:** After WorkflowStepCompleted is emitted, step continuation context is appended to the existing follow_up_colony summary message. colony_manager builds the continuation text and passes it to queen.follow_up_colony() via a new `step_continuation` parameter. When step_continuation is present, the 30-minute operator activity gate is relaxed. A `continuation_depth` counter on ThreadProjection provides a hard safety limit (20 steps).

**Rationale:** follow_up_colony (Wave 18) already emits exactly one QueenMessage per successful colony completion. Appending step continuation to this message adds zero new messages to the Queen's conversation thread, avoiding context pollution over multi-step workflows. The 30-minute operator gate must be relaxed for workflow automation -- automated step sequences should not require the operator to be actively chatting. The continuation_depth counter is derived projection state (replay-safe, no new event) that prevents infinite workflow loops.

**Rejected alternative:** Emitting a standalone QueenMessage from colony_manager. This creates an extra persistent message per step completion. Over a 10-step workflow, 10 extra low-information messages accumulate in the Queen's conversation, degrading performance through context pollution (confirmed by Chroma Research 2025, JetBrains Research 2025).

**Rejected alternative:** Metacognitive nudge system. Nudges are cooldown-gated (5-minute default), ephemeral, and advisory. Step continuation is workflow-critical and must not be suppressed by cooldown.

**Rejected alternative:** Structured state machine / Temporal Signals pattern. FormicOS is event-sourced with a Queen-centric decision model. The Queen already sees step state via _build_thread_context. Adding a parallel state machine contradicts the single-source-of-truth architecture.

---

## D2. transcript_search is projection-based, not Qdrant-backed

**Decision:** The new transcript_search agent tool searches ColonyProjection data (task, agent outputs, artifacts) from the in-memory ProjectionStore. It does not create a new Qdrant collection for transcript embeddings.

**Rationale:** Colony projections already hold all the data needed: task description, per-round agent outputs, artifact metadata, and status. For alpha-scale workspaces (~100 colonies), iterating projections with keyword matching or optional embedding similarity is fast enough. A Qdrant collection would add: a new write path (upsert on colony completion), a new sync concern (projection vs vector store consistency), and a new failure mode (Qdrant down = no transcript search). None of this complexity is justified yet.

**When to revisit:** If workspaces exceed ~500 colonies and keyword search becomes slow (>500ms), create a `colony_transcripts` Qdrant collection with task + final_output embeddings, synced from ColonyCompleted events.

---

## D3. thread_id bug fix is a two-line change, not a new feature

**Decision:** Passing thread_id to fetch_knowledge_for_colony is classified as a bug fix (Wave 30 regression), not a Wave 31 feature.

**Rationale:** Wave 29 added thread-scoped knowledge retrieval with a 0.25 thread bonus via two-phase search in KnowledgeCatalog._search_thread_boosted(). Wave 30 did not change colony_manager's knowledge fetch call. The omission means thread-scoped entries never get their boost during colony execution -- the entire purpose of the feature is silently negated. This is a regression, not a missing feature.

---

## D4. No new events in Wave 31

**Decision:** The event union stays at 48 types. All new Wave 31 behavior composes from existing events.

**Rationale:**
- Step continuation uses QueenMessage (existing)
- Tool access tracing uses KnowledgeAccessRecorded with new access_mode values (existing event, new field values)
- Confidence reset uses MemoryConfidenceUpdated with reason="manual_reset" (existing)
- No new projections, no new state machines

Per ADR-015, every event must have both emitter and handler at time of union entry. Adding events for marginal behavioral distinctions (e.g., StepContinuationPrompted) would add union complexity without architectural benefit.

---

## D5. Dedup pagination deferred unless store exceeds 500 entries

**Decision:** The O(n^2) dedup scan in maintenance.py is acceptable for Wave 31. Pagination via Qdrant-based candidate pair search is deferred.

**Rationale:** For n verified entries, the current scan evaluates n*(n-1)/2 pairs. At n=100, that is 4,950 pairs -- each requiring one Qdrant similarity lookup. At n=500, it is 124,750 pairs. The correct fix is to replace the nested loop with per-entry Qdrant searches: for each entry, search the collection with the entry's content, filter results to the [0.82, 1.0) similarity band, and evaluate only those pairs. This drops complexity from O(n^2) to O(n*k) where k is the search top_k.

This fix is deferred because:
1. Alpha-scale stores are unlikely to exceed 200 verified entries in Wave 31
2. The Qdrant-based approach requires careful handling of the similarity score interpretation (Qdrant returns cosine similarity directly, but the current _compute_similarity function uses a search-and-match approach that is correct but roundabout)
3. The fix is self-contained and can land in any future wave without dependency on other work

**When to revisit:** If the maintenance timer logs show dedup taking >30 seconds, or if verified entry count exceeds 500.

---

## D6. Thompson Sampling tuning deferred to Wave 32

**Decision:** The Beta(5.0, 5.0) prior remains unchanged. Gamma-decay is not implemented. The confidence reset handler (service:consolidation:confidence_reset) provides a manual stopgap for entries stuck at mediocre confidence.

**Rationale:** Beta(5.0, 5.0) was deliberately chosen in ADR-039 to match the legacy DEFAULT_PRIOR_STRENGTH = 10.0 from ADR-017. Changing to Beta(1,1) would require either a migration event for all existing entries (violates "no new events") or accepting inconsistent priors across old and new entries. Gamma-decay (decaying alpha and beta toward the prior each update to cap effective observation count) is the principled long-term solution for convergence lock-in, but it modifies the confidence update formula, the archival decay formula, and introduces a new tunable parameter -- new architecture, not polish.

**Archival decay tension (documented for Wave 32):** The current archival decay formula (alpha *= 0.8, beta *= 1.2) is asymmetric -- it reduces the success count while increasing the failure count, actively biasing the posterior mean downward rather than just increasing uncertainty. When gamma-decay ships, this creates double-penalization and can push parameters below the prior floor, producing pathological U-shaped Beta distributions. The archival decay formula must be redesigned alongside gamma-decay. Options: (a) symmetric decay (alpha *= 0.9, beta *= 0.9), (b) lower-gamma variant for archived entries (gamma_archived=0.85 vs gamma_active=0.98), or (c) hard floor enforcement at alpha >= alpha_0 and beta >= beta_0 after any decay.

**Wave 32 scope:**
- Implement gamma-decay at gamma ~0.98 (half-life ~35 observations at 5 obs/day). gamma=0.95 is too aggressive (2.7-day half-life at 5 obs/day -- system forgets genuine quality signals). The formulation: alpha_new = gamma * alpha + (1-gamma) * alpha_0 + reward. Apply decay at observation time using event timestamps for replay determinism.
- Redesign archival decay formula alongside gamma-decay (see tension note above)
- Consider reducing prior to Beta(2,2) alongside gamma-decay
- RRF evaluation is deprioritized -- research shows it would suppress Thompson Sampling's exploration signal by discarding score magnitudes. RRF operates on rank positions and treats deliberate exploration as noise to suppress. Keep weighted linear scoring. If RRF is revisited, the only viable approach is a hybrid: RRF for deterministic signals (semantic, freshness, status, thread) with linear overlay for Thompson.
- Normalize status_bonus and thread_bonus to [0, 1] before combination (currently bounded but not normalized)
- Dedicated ADR required for all changes
