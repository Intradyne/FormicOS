# ADR-044: Composite Scoring with Co-occurrence — Weight Rebalancing

**Status:** Proposed
**Date:** 2026-03-18
**Wave:** 34 (scoring activation), Wave 35 (per-workspace configuration)
**Depends on:** ADR-041 (knowledge tuning — current weights), ADR-043 (co-occurrence data model)

---

## Context

Wave 33 collected co-occurrence data silently (ADR-043). Result-result reinforcement fires on colony completion (1.1× for success). Query-result reinforcement fires after search (1.05×). Decay at gamma=0.995/day prunes stale associations. The infrastructure is operational and collecting data.

Wave 34 activates co-occurrence as the 6th signal in the composite scoring formula. This requires rebalancing all weights to preserve the existing ranking invariants while adding the new signal.

The composite formula in `_composite_key()` (knowledge_catalog.py:130) currently uses 5 signals with ADR-041 D3 weights:

```python
WEIGHTS = {
    "semantic": 0.40,
    "thompson": 0.25,
    "freshness": 0.15,
    "status": 0.12,
    "thread": 0.08,
}
# Sum: 1.00
```

---

## D1. Co-occurrence activates at 0.05 weight with sigmoid normalization

**Decision:** Add co-occurrence as the 6th signal in `_composite_key()`. Raw co-occurrence weight (0.0–10.0, from the `cooccurrence_weights` projection) is normalized to [0, 1] via sigmoid before applying the composite weight.

**Sigmoid normalization:**

```python
def _sigmoid_cooccurrence(raw_weight: float) -> float:
    """Normalize co-occurrence weight to [0, 1] via sigmoid.

    At raw=0.0: 0.0 (no co-occurrence history)
    At raw=1.0: ~0.46 (single reinforcement)
    At raw=3.0: ~0.88 (moderate cluster)
    At raw=5.0: ~0.97 (strong cluster)
    At raw=10.0: ~1.0 (cap)
    """
    if raw_weight <= 0.0:
        return 0.0
    return 1.0 - math.exp(-0.6 * raw_weight)
```

The 0.6 steepness parameter is calibrated so that moderate co-occurrence (3-5 reinforcements) contributes meaningfully but doesn't dominate. Entries with no co-occurrence history contribute 0.0 (neutral, not penalized).

**Co-occurrence score for an entry:** For a given search result, the co-occurrence score is the maximum sigmoid-normalized weight between that entry and any other entry in the top-k results. This rewards entries that cluster with other relevant results.

```python
def _cooccurrence_score(entry_id: str, other_ids: list[str], projections) -> float:
    max_weight = 0.0
    for other_id in other_ids:
        key = cooccurrence_key(entry_id, other_id)
        entry = projections.cooccurrence_weights.get(key)
        if entry:
            max_weight = max(max_weight, entry.weight)
    return _sigmoid_cooccurrence(max_weight)
```

**Rationale for 0.05 weight:** The co-occurrence signal is supplementary — it boosts entries that travel together in successful colonies, but it should never override strong semantic relevance or high Thompson samples. At 0.05, the maximum contribution is 0.05 (when sigmoid=1.0), comparable to the thread bonus range (0.08 × [0,1] = max 0.08). This is enough to break ties between semantically-similar entries in favor of those with proven co-access patterns.

---

## D2. Rebalanced weights — 6 signals summing to 1.00

**Decision:** The 0.05 for co-occurrence is sourced from semantic (-0.02) and status (-0.02) and thread (-0.01).

```python
WEIGHTS = {
    "semantic": 0.38,       # was 0.40 (-0.02)
    "thompson": 0.25,       # unchanged — exploration budget is sacred
    "freshness": 0.15,      # unchanged — recency signal unchanged
    "status": 0.10,         # was 0.12 (-0.02)
    "thread": 0.07,         # was 0.08 (-0.01)
    "cooccurrence": 0.05,   # NEW
}
# Sum: 1.00
```

**Rationale for sourcing:**
- Semantic reduced 0.40→0.38: Still dominant. The 0.02 reduction is offset by co-occurrence providing a complementary relevance signal (entries that co-occur with semantically relevant entries are likely relevant themselves).
- Thompson unchanged at 0.25: The exploration budget is the system's learning mechanism. Reducing it would slow adaptation.
- Freshness unchanged at 0.15: Recency is independent of co-occurrence.
- Status reduced 0.12→0.10: Status is a coarse signal (4 discrete values). Co-occurrence provides finer-grained quality information.
- Thread reduced 0.08→0.07: Thread affinity is a binary signal. The 0.01 reduction has minimal ranking impact.

**These weights are provisional.** Track C's stress test (C2) will validate that they produce the correct ranking behavior. If the stress test shows cluster domination (>30% of top-5 slots from one cluster), reduce co-occurrence to 0.03 and redistribute.

---

## D3. Six validation invariants

The 4 existing invariants from ADR-041 D3 are preserved. Two new invariants added:

**Invariant 1** (ADR-041): At equal semantic similarity and freshness, a verified entry always outranks a stale entry. *Preserved — status weight (0.10) still dominates over co-occurrence (0.05).*

**Invariant 2** (ADR-041): At equal everything else, a thread-matched entry outranks a non-matched entry. *Preserved — thread weight (0.07) > co-occurrence (0.05).*

**Invariant 3** (ADR-041): Thompson Sampling produces different rankings on successive calls with same inputs. *Preserved — thompson weight unchanged at 0.25.*

**Invariant 4** (ADR-041): A very old entry (freshness=0.0) can still rank highly if verified and semantically relevant. *Preserved — semantic (0.38) + status (0.10) = 0.48, easily overcomes freshness=0.0.*

**Invariant 5** (NEW): Entries frequently co-accessed in successful colonies score higher than identical entries without co-occurrence history, all else equal. *Co-occurrence weight 0.05 × sigmoid(5.0) ≈ 0.05 × 0.97 ≈ 0.049 additional score.*

**Invariant 6** (NEW): No single co-occurrence cluster takes all top-5 slots more than 30% of the time across a representative query set. *Validated by Track C stress test (C2). If violated, reduce co-occurrence weight.*

---

## D4. Default weights in knowledge_constants.py — per-workspace deferred to Wave 35

**Decision:** Wave 34 implements co-occurrence scoring with default weights as module-level constants. `_composite_key()` reads from `knowledge_constants.py`. No per-workspace configuration.

```python
# knowledge_constants.py
COMPOSITE_WEIGHTS: dict[str, float] = {
    "semantic": 0.38,
    "thompson": 0.25,
    "freshness": 0.15,
    "status": 0.10,
    "thread": 0.07,
    "cooccurrence": 0.05,
}
```

**Wave 35 forward reference:** Per-workspace weight configuration via `WorkspaceConfigChanged` is deferred to Wave 35. That change requires:
- `_composite_key()` receiving weights as a parameter instead of reading module constants
- Workspace projection storing override weights
- `WorkspaceConfigChanged` event handling for weight updates
- Invariants parameterized by workspace weight config
- Test surface doubled (default + custom weight paths)

None of this adds value for initial deployment. The default weights work for all workspaces. Per-workspace tuning is an optimization for operators running multiple distinct workspaces with different domain characteristics.

---

## Rejected Alternatives

**Co-occurrence at 0.10 weight (taken from semantic):** Would reduce semantic to 0.30 — too aggressive. Co-occurrence is a supplementary signal, not a primary one. At 0.10, a strong co-occurrence cluster could override moderate semantic relevance, which violates the design intent.

**RRF instead of weighted linear combination:** Rejected in ADR-041 D5 and still rejected. Thompson Sampling's exploration signal depends on score magnitudes. RRF destroys magnitudes.

**Per-workspace weights in Wave 34:** Discussed above (D4). Deferred to Wave 35 — complexity doesn't justify the value at initial deployment.

**Co-occurrence as a post-filter instead of scoring signal:** Applying co-occurrence after scoring (boost top-k results that cluster together) would avoid weight rebalancing but creates a non-composable two-stage pipeline. Keeping all signals in one linear combination is simpler and more predictable.
