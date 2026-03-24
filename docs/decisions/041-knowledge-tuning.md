# ADR-041: Knowledge Confidence Tuning — Gamma-Decay, Archival Decay Redesign, and Scoring Normalization

**Status:** Approved
**Date:** 2026-03-18
**Wave:** 32

---

## Context

After Wave 31, the knowledge system has Bayesian confidence posteriors (Beta(alpha, beta)) evolved by Thompson Sampling. Retrieval uses a composite score blending semantic similarity, Thompson samples, freshness, status bonus, and thread bonus. The system works but has three known problems:

1. **Convergence lock.** An entry observed 40+ times locks into its current confidence. Thompson Sampling effectively stops exploring it because the posterior variance shrinks with each observation. There is no mechanism for the system to adapt when knowledge quality changes over time.

2. **Asymmetric archival decay.** The current formula (`alpha *= 0.8, beta *= 1.2`) biases the posterior mean downward rather than widening uncertainty. Wave 31 added hard floors (`max(alpha, 1.0)`, `max(beta, 1.0)`) as a stopgap.

3. **Unnormalized scoring signals.** The composite formula mixes signals with different ranges: semantic/thompson/freshness are [0,1], but status_bonus ranges [-0.5, 0.3] and thread_bonus is {0.0, 0.25}. This makes weight tuning unreliable — a weight change has different effects depending on which signal it applies to.

---

## D1. Time-based gamma-decay at GAMMA_PER_DAY = 0.98

**Decision:** Apply exponential decay toward the prior based on elapsed wall-clock time between confidence updates, not based on observation count. Each confidence update decays the existing alpha/beta toward the prior proportional to time elapsed since the last update, then adds the new observation.

**Formulation:**

```
elapsed_days = (event_timestamp - entry_last_updated_timestamp) / 86400.0
gamma_effective = GAMMA_PER_DAY ** elapsed_days

alpha_new = gamma_effective * alpha_old + (1 - gamma_effective) * PRIOR_ALPHA + reward
beta_new  = gamma_effective * beta_old  + (1 - gamma_effective) * PRIOR_BETA  + (1 - reward)
```

Where:
- `GAMMA_PER_DAY = 0.98` (half-life: `ln(0.5) / ln(0.98)` ≈ 34.3 calendar days)
- `PRIOR_ALPHA = 5.0`, `PRIOR_BETA = 5.0` (constants, not per-entry)
- `reward = 1.0` if colony succeeded, `0.0` if failed
- Hard floor: `alpha >= 1.0`, `beta >= 1.0` (Wave 31, unchanged)

**Replay determinism:** Uses event timestamps exclusively, never the system clock. The `MemoryConfidenceUpdated` event carries `new_alpha` and `new_beta` — the projection handler applies these directly. Replay produces identical state regardless of when replay occurs because the decay computation happens in colony_manager (surface layer) and is baked into the emitted event values.

**Projection change:** Add `last_confidence_update: str` (ISO timestamp) to the `memory_entries` projection dict. Set by `_on_memory_entry_created` (initial value = `created_at`) and updated by `_on_memory_confidence_updated` (value = event timestamp). This is derived projection state, replay-safe.

**Rationale:** The orchestrator identified that per-observation decay (the original plan) creates access-frequency-dependent half-lives. A popular entry accessed by 50 colonies/day would have a half-life under 1 day at gamma=0.98 per observation. Time-based decay makes the forgetting rate independent of access frequency: an entry accessed once per day and one accessed 50 times per day both decay at the same calendar rate. Multiple observations on the same day barely decay between them because `elapsed_days` is small.

**Why gamma=0.98:** At 0.98/day, the half-life is ~34.3 days. This means the system meaningfully adapts to changing knowledge quality within 4-5 weeks while preserving genuine long-term signals. gamma=0.95 gives a ~13.5-day half-life — too aggressive, loses genuine long-term knowledge. gamma=0.99 gives a ~69-day half-life — too slow to respond to quality changes within a reasonable operator evaluation window.

**Rejected alternative:** Per-observation gamma-decay (gamma=0.98 per observation). Half-life depends on access frequency, making system behavior unpredictable. Popular entries would forget faster than rarely-accessed ones, which is the opposite of the intended behavior.

**Rejected alternative:** Reciprocal Rank Fusion (RRF). Research confirmed RRF would suppress Thompson Sampling's exploration signal by normalizing score magnitudes. The score magnitude IS the exploration signal in Thompson Sampling — entries with high variance produce occasional high samples that drive exploration. RRF destroys this by ranking, not scoring.

---

## D2. Archival decay via gamma-burst at 30-day equivalent

**Decision:** When a thread is archived, apply a burst of time-based decay equivalent to 30 calendar days of natural gamma-decay. This replaces the asymmetric `alpha *= 0.8, beta *= 1.2` formula.

**Formulation:**

```python
ARCHIVAL_EQUIVALENT_DAYS = 30
archival_gamma = GAMMA_PER_DAY ** ARCHIVAL_EQUIVALENT_DAYS  # 0.98^30 ≈ 0.545

new_alpha = max(archival_gamma * old_alpha + (1 - archival_gamma) * PRIOR_ALPHA, 1.0)
new_beta  = max(archival_gamma * old_beta  + (1 - archival_gamma) * PRIOR_BETA, 1.0)
```

**Properties:**
- Symmetric: both alpha and beta decay toward the prior at the same rate. Does not bias the posterior mean.
- Composes with gamma-decay: one formula family, two rates (daily natural decay vs. archival burst).
- Hard floor preserved: `max(..., 1.0)` prevents parameters going below Beta(1,1) = uniform.
- At 0.545, archiving roughly halves the distance between current parameters and the prior. Entries that were genuinely good will recover if re-accessed. Entries that were mediocre drift toward the prior and are explored less.

**Applied uniformly:** All knowledge entries scoped to the archived thread receive the burst, regardless of their individual access history. The purpose of archival decay is to reduce the influence of thread-scoped knowledge that's being retired — all entries in the thread are equally "retired."

**Hardcoded, not configurable.** This is an internal decay parameter, not an operator-facing tuning knob. If it needs changing, it's a code change with an ADR update. Keeps the system predictable.

**Rationale for 30 days:** The intent is "archival = a significant push toward the prior, but not a reset." At 30 days equivalent, an entry with alpha=20 (strong positive evidence) decays to `0.545 * 20 + 0.455 * 5 = 13.2`. Still above the prior, but with meaningfully wider uncertainty. An entry at alpha=50 decays to `0.545 * 50 + 0.455 * 5 = 29.5`. Still retains most of its signal. The 30-day value is a tuning knob to be evaluated empirically post-deployment.

**Rejected alternative:** Symmetric multiplicative decay (`alpha *= 0.9, beta *= 0.9`). Simple but creates a separate decay mechanism with different mathematical properties than gamma-decay. Two decay formulas means two sets of intuitions to maintain.

**Rejected alternative:** Remove archival decay entirely and let natural gamma-decay handle it. But archived entries that are never accessed again would never decay (time-based decay requires an observation event to trigger the computation). Stale sweep catches eventually, but the gap could be weeks.

---

## D3. Scoring signals normalized to [0, 1] with recalibrated weights

**Decision:** Normalize `status_bonus` and `thread_bonus` to [0, 1]. Recalibrate composite weights to preserve intended priority ordering. Validate with invariants, not frozen rankings.

**Normalized status bonus:**

```python
_STATUS_BONUS = {
    "verified": 1.0,
    "active": 0.8,
    "candidate": 0.5,
    "stale": 0.0,
}
# Unknown/missing status: 0.0 (no information, treated as stale)
```

**Normalized thread bonus:** `{0.0, 1.0}` (was `{0.0, 0.25}`).

**Recalibrated weights:**

```python
# Old: 0.35 semantic, 0.25 thompson, 0.15 freshness, 0.15 status, 0.10 thread
# New:
WEIGHTS = {
    "semantic": 0.40,   # dominant signal, slightly increased
    "thompson": 0.25,   # exploration budget, unchanged
    "freshness": 0.15,  # unchanged
    "status": 0.12,     # reduced — [0,1] range is wider than old [-0.5, 0.3]
    "thread": 0.08,     # reduced — [0,1] range is wider than old [0, 0.25]
}
# Sum: 1.00
```

**Rationale for weight changes:** The old effective contribution ranges were: status 0.15 * [-0.5, 0.3] = [-0.075, 0.045], thread 0.10 * [0, 0.25] = [0, 0.025]. After normalization to [0,1], keeping the same weights would dramatically increase both signals' influence. Reducing status to 0.12 and thread to 0.08 keeps their effective contribution in a similar range. The freed 0.05 goes to semantic (0.35 → 0.40) as semantic relevance should be the dominant ranking signal.

**Validation via invariants (not frozen rankings):**
- Invariant 1: At equal semantic similarity and freshness, a verified entry always outranks a stale entry
- Invariant 2: At equal everything else, a thread-matched entry outranks a non-matched entry
- Invariant 3: Thompson Sampling produces different rankings on successive calls with same inputs (exploration working)
- Invariant 4: A very old entry (freshness=0.0) can still rank highly if verified and semantically relevant (freshness doesn't dominate)

**Rejected alternative:** Frozen golden rankings as acceptance criteria. These break every time weights are tuned, creating brittle tests that test the wrong thing (specific numbers vs. desired ranking properties).

**Implementation note:** Only `knowledge_catalog.py` has composite scoring. `memory_store.py` delegates to Qdrant's native scoring and does not have a parallel `_composite_key`. Only one implementation needs to change.

---

## D4. Prior remains Beta(5.0, 5.0) — deferred

**Decision:** Do not reduce the prior from Beta(5,5) to Beta(2,2) in Wave 32. Evaluate gamma-decay empirically first.

**Rationale:** With time-based gamma-decay, the prior's influence is self-correcting. Even with a strong prior of Beta(5,5), after ~34 days without observations, an entry's alpha/beta have decayed halfway back toward (5,5) regardless of where they started. The prior mainly affects the speed at which new entries begin to express their true quality — at Beta(5,5), ~10 observations are needed before data dominates. This is conservative but not pathological.

If operator testing reveals that new entries take too long to differentiate, reduce the prior in Wave 33. The migration would emit `MemoryConfidenceUpdated` events with `reason="prior_migration"` for all existing entries, which is replay-safe.

---

## D5. RRF rejected — incompatible with Thompson Sampling

**Decision:** Do not use Reciprocal Rank Fusion for combining retrieval signals.

**Rationale:** Thompson Sampling's value comes from its score magnitudes, not just relative rankings. An entry with Beta(2, 20) occasionally produces a high Thompson sample (exploration), while an entry with Beta(20, 2) consistently produces high samples (exploitation). RRF discards these magnitudes by converting to rank positions, which would:
1. Suppress exploration: a Beta(2, 20) entry that luckily drew a high sample would be ranked the same as one with a slightly lower sample, losing the exploration signal.
2. Remove the natural balance between exploitation and exploration that Thompson Sampling provides.
3. Create a hybrid system where the exploration mechanism (Thompson) is fighting the aggregation mechanism (RRF), with unpredictable behavior.

The current weighted linear combination preserves Thompson's score magnitudes and allows the exploration/exploitation balance to work as designed.
