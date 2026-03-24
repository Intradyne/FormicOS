# ADR-043: Co-occurrence Data Model — Collection Infrastructure and Deferred Scoring

**Status:** Proposed
**Date:** 2026-03-18
**Wave:** 33 (collection), Wave 34 (scoring activation)
**Depends on:** ADR-041 (knowledge tuning — composite weights)

---

## Context

NeuroStack's `reinforce_cooccurrence()` demonstrates that knowledge entries accessed together in successful operations develop structural relationships worth tracking. Entries that co-occur frequently in successful colonies are likely complementary — retrieving one should boost the other.

However, ADR-041 D3 just stabilized the composite scoring weights at `0.40*semantic + 0.25*thompson + 0.15*freshness + 0.12*status + 0.08*thread`. Adding a new signal immediately would destabilize the weights before they've been validated in production.

This ADR separates data collection (Wave 33) from scoring integration (Wave 34).

---

## D1. Co-occurrence weights collected via reinforcement and decay

**Decision:** Build the full co-occurrence data collection infrastructure in Wave 33. Two reinforcement paths and one decay path.

### Result-result reinforcement (colony completion)

After a colony completes, build pairs of all knowledge entries accessed during the colony (from `KnowledgeAccessRecorded` events). For successful colonies, reinforce each pair's weight by multiplying by 1.1 (capped at 10.0). For failed colonies, do not reinforce (weight 0.0× — absence of reinforcement, not punishment).

**Location:** `_hook_confidence_update()` in `colony_manager.py` (line 789), after the per-entry confidence update loop. This hook already iterates over accessed entries.

### Query-result reinforcement (search time)

After `_search_thread_boosted()` returns results, build pairs of (query-matched entries × returned entries). Reinforce at 0.5× per search event. This is lower than colony-completion reinforcement because search volume is higher (many searches per colony) and individual searches are weaker signals than colony outcomes.

**Location:** `_search_thread_boosted()` in `knowledge_catalog.py` (line 300), after the sort at line 365. Fire-and-forget — never blocks the search response.

### Decay in maintenance loop

Apply gamma=0.995/day (half-life ≈ 138 days) to all co-occurrence weights during the maintenance loop, alongside `stale_sweep`. The 4× slower decay rate (vs. knowledge confidence's gamma=0.98, half-life ≈ 34 days) reflects that structural relationships between knowledge entries persist longer than individual entry relevance. Prune pairs with weight < 0.1.

**Location:** New function in `maintenance.py`, registered as a maintenance pass.

---

## D2. Scoring integration deferred to Wave 34

**Decision:** The composite scoring formula in `_composite_key()` (knowledge_catalog.py:130) does NOT change in Wave 33. The weights remain at ADR-041 D3 values:

```python
WEIGHTS = {
    "semantic": 0.40,
    "thompson": 0.25,
    "freshness": 0.15,
    "status": 0.12,
    "thread": 0.08,
}
# Sum: 1.00 — unchanged in Wave 33
```

Wave 34 will:
1. Analyze collected co-occurrence data to validate the signal's discriminative power
2. Determine the appropriate weight (estimated ~0.05, taken from semantic)
3. Rebalance all weights in a dedicated ADR
4. Add co-occurrence lookup to `_composite_key()`

**Rationale:** ADR-041 D3 was validated with 1,564 passing tests and 4 ranking invariants. Adding a 6th signal without empirical data risks degrading retrieval quality. The 138-day half-life means Wave 34 (likely 2-4 weeks after Wave 33) will have meaningful co-occurrence data to evaluate.

---

## D3. Data structure — sparse projection dict

**Decision:** Co-occurrence weights stored as a sparse dictionary on `ProjectionStore`, keyed by canonically-ordered entry ID pairs.

```python
@dataclass
class CooccurrenceEntry:
    weight: float              # reinforcement weight, capped at 10.0
    last_reinforced: str       # ISO timestamp
    reinforcement_count: int   # total reinforcement events

# On ProjectionStore:
cooccurrence_weights: dict[tuple[str, str], CooccurrenceEntry]
```

**Canonical ordering:** `(min(id_a, id_b), max(id_a, id_b))` by string comparison. Prevents duplicate pairs.

**Sparsity:** At 2,000 knowledge entries with 5 accessed per colony, the theoretical pair space is ~2M. Actual density will be well under 1% because most entries never co-occur. Memory overhead is negligible.

**Ephemeral on replay:** Co-occurrence weights are NOT rebuilt from events on replay. They are recomputed from `KnowledgeAccessRecorded` event traces during projection rebuild. This makes them lossy (query-result reinforcement from search events is not event-sourced) but keeps the event store clean. The query-result path is a supplementary signal — losing it on replay is acceptable.

**Alternative considered — event-sourced co-occurrence:** Emitting `CooccurrenceReinforced` events for every pair would generate O(n²) events per colony (where n = accessed entries). At 5 entries per colony, that's 10 events per colony completion plus potentially hundreds from search reinforcement. The event store volume doesn't justify the replay fidelity gain for a supplementary scoring signal.

---

## D4. Interaction with federation (Wave 33 Track C)

Co-occurrence weights are instance-local. They are NOT federated. Each instance builds its own co-occurrence structure from its own colony execution patterns. Federating co-occurrence weights would require:
- Merging sparse pair dictionaries across instances (non-trivial)
- Reconciling different reinforcement histories
- No clear benefit (co-occurrence patterns are usage-dependent, not knowledge-dependent)

If future waves determine that cross-instance co-occurrence patterns are valuable, a separate federation channel can sync aggregated pair weights.

---

## Rejected Alternatives

**Immediate scoring integration at weight 0.05:** Would change the composite formula sum to either >1.00 (breaking normalization) or require shaving 0.05 from semantic (0.40→0.35), reverting the ADR-041 increase. Premature without empirical data.

**Event-sourced co-occurrence events:** O(n²) event volume per colony makes this impractical. See D3.

**Federated co-occurrence weights:** Instance-local patterns are more useful than cross-instance averages. See D4.

**NeuroStack's unbounded reinforcement (cap at 100.0):** NeuroStack caps at 100.0 with no decay. FormicOS caps at 10.0 with gamma=0.995 decay. The lower cap plus decay prevents stale associations from dominating, which is the known failure mode NeuroStack exhibits.
