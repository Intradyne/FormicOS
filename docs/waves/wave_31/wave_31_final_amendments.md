# Wave 31 Final Amendments -- Research + Codebase Verification

**Date:** 2026-03-17
**Inputs:** Deep research audit (7 areas), operator orchestrator codebase-grounded assessment, original wave_31_plan.md v2

This document records the final decisions from the research/verification pass. Each amendment is either ADOPT (change the plan), DEFER (acknowledge but push to Wave 32+), or VALIDATE (plan was already correct).

---

## Amendment 1: Step Continuation -- Append to follow_up_colony, Not Separate QueenMessage

**Status: ADOPT -- significant plan revision**

### Problem with the v2 plan

The plan emits a standalone QueenMessage from colony_manager for step continuation. This creates an extra persistent message per step completion in the Queen's conversation thread. Over a 10-step workflow, that is 10 extra messages of low-information-density tokens polluting context. The research confirms context pollution degrades LLM performance as conversation length grows.

### What the codebase actually supports

`follow_up_colony` (queen_runtime.py:214-298) already emits exactly one QueenMessage per successful colony completion with a quality summary and contract status. This is the established injection point. Step continuation should be appended to this summary -- zero new messages.

The step completion block in `_post_colony_hooks()` (colony_manager.py:748-794) runs AFTER the `follow_up_colony` dispatch (line 672). This ordering must be adjusted: detect step completion first, then pass step info into `follow_up_colony`.

### Revised implementation

1. **Reorder `_post_colony_hooks`:** Move the step completion detection (lines 748-794) ABOVE the follow_up dispatch (line 672). The WorkflowStepCompleted event emission stays where it is. But the detection of "which step completed and what is next" can happen earlier by reading the thread projection's workflow_steps.

2. **Extend `follow_up_colony` signature:**
   ```python
   async def follow_up_colony(
       self, colony_id: str, workspace_id: str, thread_id: str,
       step_continuation: str = "",  # NEW: appended to summary if non-empty
   ) -> None:
   ```

3. **Relax the 30-minute operator gate when step_continuation is present.** Automated multi-step workflows should not require the operator to have sent a message recently. If `step_continuation` is truthy, skip the `has_recent_operator` check. **Add a structlog trace when the gate is relaxed:** `log.info("queen.follow_up_gate_relaxed", reason="step_continuation", thread_id=thread_id)` so operators have visibility into when the gate was bypassed. Note: a full three-tier autonomy model (attended/supervised/autonomous) is Wave 33+ scope -- the continuation_depth counter is the correct safety mechanism for Wave 31.

4. **Append step continuation to the summary** (between line 294 and 296):
   ```python
   if step_continuation:
       summary += f"\n{step_continuation}"
   ```

5. **Format the continuation text in colony_manager** before passing to follow_up:
   ```
   Step {N} completed. Next pending: Step {N+1} -- {description}.
   {Template: {template_id}, Expected: {expected_outputs} if template-backed}
   Review step status or spawn the next colony.
   ```

6. **Add `continuation_depth: int = 0` to ThreadProjection.** Increment in the `_on_workflow_step_completed` projection handler. No new event needed -- this is derived state, replay-safe.

7. **Check depth in colony_manager before building continuation text.** If `thread.continuation_depth >= 20`, set continuation text to: "Step limit reached (20 consecutive steps). Review workflow before continuing."

### Files touched (revised for Track A)

- `surface/colony_manager.py` -- reorder _post_colony_hooks, build step continuation text, pass to follow_up, fix thread_id bug
- `surface/queen_runtime.py` -- extend follow_up_colony signature, relax 30-min gate (with structlog trace) when step_continuation present, append to summary, add archival decay hard-floor (lines 1282-1283: clamp alpha >= 1.0, beta >= 1.0)
- `surface/projections.py` -- add continuation_depth to ThreadProjection, increment in _on_workflow_step_completed handler

### What this replaces

- Removes: standalone QueenMessage emission from colony_manager (the v2 plan's approach)
- Removes: the code example showing `QueenMessage(role="queen", ...)` emission from colony_manager
- Keeps: everything else in Track A (thread_id bug fix, confidence fan-out measurement, thread context truncation)

---

## Amendment 2: Transcript Search -- BM25 as Primary, Embeddings Optional

**Status: ADOPT -- minor plan refinement**

The plan already said "keyword matching with optional embedding similarity." The amendment makes this more specific: use `bm25s` (pure Python, fast) as the primary search path over colony projection task + final_output text. Embedding similarity is a true optional enhancement, not a co-primary path.

Research finding: agents naturally search with keywords, not questions. BM25 has no vocabulary gap when the same system wrote both query and corpus. At 100-1000 colonies, BM25 in-memory is sub-millisecond.

### Implementation detail

```python
import bm25s  # add to pyproject.toml

# Build index over colony tasks + final outputs at search time (or cache)
corpus = [f"{c.task} {_last_round_output(c)}" for c in workspace_colonies]
retriever = bm25s.BM25()
retriever.index(bm25s.tokenize(corpus))
results = retriever.retrieve(bm25s.tokenize([query]), k=top_k)
```

Note: `bm25s` is a new dependency. This requires operator approval per CLAUDE.md hard constraint. If denied, fall back to Jaccard word overlap (the plan's original approach) which requires no new dependencies.

**Code-aware tokenizer (required).** The default bm25s splitter fails on camelCase (e.g., `getAgentStatus` becomes one token). Ship with a custom tokenizer from day one:

```python
import re
def code_tokenizer(text):
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)    # camelCase split
    text = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', text)  # ABCDef split
    tokens = re.findall(r'\w+', text.lower())
    return [t for t in tokens if len(t) > 1]
```

Pass as `splitter=code_tokenizer` to `bm25s.tokenize()`.

**Tool description: include a "when NOT to use" clause.** Research on tool overuse (SMART 2025, AutoGen Issue #1824) shows agents become enthusiastic about new tools. The transcript_search description should include neutral negative guidance:

```
"description": "Search past colony transcripts for relevant approaches and patterns. Returns colony IDs and snippets -- use artifact_inspect to see full details. Do NOT use this tool for the current colony's data (use memory_search instead) or for general knowledge queries (use knowledge_detail instead)."
```

Place transcript_search mid-list in the tool specs (not first, not last) to reduce ordering bias.

### Files touched

No change to file list -- same files as v2 plan. The implementation detail changes inside `make_transcript_search_fn()` in runtime.py.

---

## Amendment 3: Thompson Sampling Prior -- Keep Beta(5.0, 5.0), Document Tradeoffs

**Status: DEFER to Wave 32**

The research correctly identifies Beta(5,5) as slow to learn (needs ~10 observations before data dominates prior). However:

- Beta(5,5) is already deployed in types.py:313-320 and baked into every existing MemoryEntry
- Changing to Beta(1,1) would require a migration event (violates "no new events") or accepting inconsistent priors across old/new entries
- The 5.0/5.0 prior was deliberately chosen in ADR-039 to match legacy DEFAULT_PRIOR_STRENGTH = 10.0
- This is a tuning decision, not a bug

### Action for Wave 31

- Document the prior choice and its tradeoffs in KNOWLEDGE_LIFECYCLE.md (Track C)
- Add monitoring guidance: "If entries plateau at ~0.5 confidence after 20+ observations, consider reducing the prior in a future wave"
- Add to ADR-040: "D6: Thompson Sampling tuning deferred to Wave 32."

### Wave 32 scope (for future reference)

- Implement gamma-decay at gamma ~0.98 (half-life ~35 observations at 5 obs/day) in the confidence update formula. gamma=0.95 is too aggressive (2.7-day half-life).
- Consider reducing prior to Beta(2,2) alongside gamma-decay
- Both changes require a dedicated ADR and tuning validation

---

## Amendment 4: Gamma-Decay for Thompson Sampling -- Defer to Wave 32

**Status: DEFER to Wave 32**

The research correctly identifies convergence lock-in (Beta(50,50) = exploration ceases) and recommends gamma-decay. The orchestrator correctly classifies this as "new architecture, not polish." Gamma-decay modifies:

- The confidence update formula in `_post_colony_hooks`
- The archival decay formula
- Introduces a new tunable parameter

This belongs in a "Knowledge Tuning" wave with a dedicated ADR.

### Action for Wave 31

- Document the convergence problem in KNOWLEDGE_LIFECYCLE.md
- Document the archival decay tension: the current asymmetric formula (alpha *= 0.8, beta *= 1.2) pushes confidence downward by design. When gamma-decay ships, this must be replaced with symmetric decay or subsumed into the gamma-decay mechanism. A hard floor of alpha >= alpha_0 and beta >= beta_0 should be enforced.
- **Frontloaded from Wave 32: Add hard-floor enforcement to the existing archival decay in `queen_runtime.py`.** After the `alpha *= 0.8, beta *= 1.2` operation, clamp: `new_alpha = max(new_alpha, 1.0)` and `new_beta = max(new_beta, 1.0)`. This is a one-line defensive guard (Track A touches queen_runtime.py already) that prevents pathological U-shaped Beta distributions if archival decay runs multiple times on the same entry. Zero risk, prevents a real edge case.
- Keep the manual confidence reset handler (Track C) as a stopgap for stuck entries
- Note in ADR-040 D6 that gamma-decay is the principled long-term solution

---

## Amendment 5: Qdrant Fallback -- BM25 Keyword Search, Not Raw Recency

**Status: ADOPT -- plan revision**

The research is right: "5 most recent entries by created_at" provides no relevance signal. The orchestrator's scoping is correct: BM25 keyword search on projections is the right fallback, but 4-tier degradation + circuit breaker is overscoped for a polish wave.

### Revised implementation

Replace the plan's "5 most recent verified entries sorted by created_at" with:

```python
# In knowledge_catalog.py, when Qdrant search raises
def _projection_keyword_fallback(
    self, query: str, workspace_id: str, top_k: int = 5,
) -> list[dict[str, Any]]:
    """BM25 keyword fallback when Qdrant is unavailable."""
    entries = [
        e for e in self._projections.memory_entries.values()
        if e.get("workspace_id") == workspace_id
        and e.get("status") in ("verified", "active", "candidate")
    ]
    if not entries:
        return []
    # Simple word-overlap scoring (no new dependency)
    query_words = set(query.lower().split())
    scored = []
    for e in entries:
        text = f"{e.get('title', '')} {e.get('content', '')} {' '.join(e.get('domains', []))}".lower()
        entry_words = set(text.split())
        overlap = len(query_words & entry_words)
        if overlap > 0:
            scored.append((overlap, e))
    scored.sort(key=lambda x: -x[0])
    return [_normalize_institutional(e, score=0.0) for _, e in scored[:top_k]]
```

Tag fallback results with `source: "keyword_fallback"` so agents know they are getting degraded results.

If `bm25s` is approved as a dependency (Amendment 2), use it here too for better ranking. If not, word-overlap is acceptable.

### Deferred to future wave

- Semantic cache (in-memory Qdrant result cache with TTL)
- Circuit breaker pattern with half-open probing
- OpenTelemetry instrumentation of fallback paths
- Tiered degradation with health check endpoints

---

## Amendment 6: Composite Scoring Normalization -- Investigate Only

**Status: DEFER -- investigate in Wave 32**

The research flags that mixing stochastic (Thompson sample) and deterministic (similarity, freshness) signals in a linear combination requires normalization to [0, 1]. The current formula's signals are:

- semantic similarity: already [0, 1] (cosine similarity from Qdrant)
- Thompson sample: already [0, 1] (Beta distribution sample)
- freshness: already [0, 1] (exponential decay function)
- status bonus: {-0.5, -0.2, 0.0, 0.25, 0.3} -- NOT normalized to [0, 1]
- thread bonus: {0.0, 0.25} -- NOT normalized to [0, 1]

The status bonus range [-0.5, 0.3] and thread bonus [0.0, 0.25] are not [0,1] but they are bounded and small. The weights (0.35, 0.25, 0.15, 0.15, 0.10) sum to 1.0. The formula "works" in practice because the bounded signals do not cause extreme scores. But it is mathematically imprecise.

### Action for Wave 31

- Do nothing. Changing the scoring formula in a polish wave risks regression.
- Document the formula and its signal ranges in KNOWLEDGE_LIFECYCLE.md
- Note in Wave 32 scope: consider RRF (Reciprocal Rank Fusion) as an alternative that avoids normalization issues entirely

---

## Amendment 7: Testing -- Add Seeded Deterministic and KS Tests

**Status: ADOPT -- minor plan enhancement**

The plan's test list is good. Add these specific techniques:

- **Seeded deterministic tests:** Use `random.seed(42)` to make Thompson Sampling tests reproducible. Verify specific rankings for known (alpha, beta) values with a fixed seed.
- **KS test for distribution correctness:** Run 10,000+ samples from `_composite_key` with known inputs, verify the Thompson component follows the expected Beta distribution using `scipy.stats.kstest`.
- **Given/When/Then Events pattern** for projection tests: matches existing BDD style in `docs/specs/`.

No change to file list or test count. These are implementation techniques for the coders.

---

## Amendment 8: New Decision D6 for ADR-040

Add D6 to the ADR:

**D6: Thompson Sampling tuning deferred to Wave 32.** Prior remains Beta(5.0, 5.0). Gamma-decay not implemented. Confidence reset handler provides a manual stopgap for stuck entries. Rationale: retroactive prior changes risk data inconsistency; gamma-decay is new architecture; both require dedicated ADR and validation in a tuning-focused wave.

---

## Summary of All Amendments

| # | Area | Action | Impact on plan |
|---|------|--------|----------------|
| 1 | Step continuation | ADOPT: append to follow_up_colony | Major revision to A1 implementation |
| 2 | Transcript search | ADOPT: BM25 primary | Minor clarification |
| 3 | TS prior | DEFER | Document only, no code change |
| 4 | Gamma-decay | DEFER | Document + frontload archival decay hard-floor (1 line) |
| 5 | Qdrant fallback | ADOPT: BM25 keyword search | Revision to C5 fallback |
| 6 | Scoring normalization | DEFER | Document only |
| 7 | Testing techniques | ADOPT | Implementation detail, no plan structure change |
| 8 | ADR-040 D6 | ADOPT | Add one decision to ADR |

### Net impact on Track ownership

**Track A files (revised):**
- `surface/colony_manager.py` -- reorder hooks, build step text, pass to follow_up, fix thread_id bug (**still OWN**)
- `surface/queen_runtime.py` -- extend follow_up_colony signature, relax 30-min gate with structlog trace, archival decay hard-floor (**now touched by A, was previously "no changes needed"**)
- `surface/projections.py` -- add continuation_depth (**new touch for A**)

**Track B files:** Unchanged.

**Track C files (revised):**
- `surface/knowledge_catalog.py` -- BM25 keyword fallback instead of raw recency (**same ownership, better implementation**)
- All doc files unchanged in scope, but add TS tuning documentation and scoring formula documentation

### Revised File Ownership Matrix

| File | Track A | Track B | Track C | Notes |
|------|---------|---------|---------|-------|
| `surface/colony_manager.py` | **OWN** | wire callback | -- | A: reorder hooks, step text, thread_id fix; B: one RoundRunner line |
| `surface/queen_runtime.py` | **OWN** | -- | first-run text | A: extend follow_up_colony, relax 30-min gate, thread context truncation, archival decay hard-floor |
| `surface/projections.py` | **OWN** | read only | -- | A: add continuation_depth, increment in step completed handler |
| `engine/runner.py` | -- | **OWN** | -- | B: tool spec/dispatch/category/init param |
| `surface/runtime.py` | -- | **OWN** | -- | B: transcript_search callback factory (BM25 primary) |
| `surface/knowledge_catalog.py` | -- | -- | **OWN** | C: BM25 keyword fallback |
| `surface/maintenance.py` | -- | -- | **OWN** | C: confidence reset handler |
| `surface/app.py` | -- | -- | **OWN** | C: register confidence reset handler |
| `surface/memory_store.py` | measure only | -- | -- | A: sync_entry latency measurement |
| `config/caste_recipes.yaml` | -- | **OWN** | Queen prompt | B: transcript_search tool; C: Queen system prompt |
| `tests/unit/surface/test_*.py` | -- | **OWN** | -- | B: all 8 test files |
| `CLAUDE.md` | -- | -- | **OWN** | C: rewrite with verified tech stack |
| `AGENTS.md` | -- | -- | **OWN** | C: update agent tools |
| `docs/KNOWLEDGE_LIFECYCLE.md` | -- | -- | **OWN** | C: new, includes TS tuning notes |
| `docs/decisions/040-*.md` | -- | -- | **OWN** | C: add D6 |
| `frontend/src/components/knowledge-browser.ts` | -- | -- | **OWN** | C: empty state |
