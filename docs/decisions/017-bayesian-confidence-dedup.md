# ADR-017: Bayesian Skill Confidence + LLM-Gated Deduplication

**Status:** Accepted
**Date:** 2026-03-14
**Depends on:** ADR-010 (Skill Crystallization), ADR-013 (Qdrant Migration), ADR-015 (Event Union Expansion)

## Context

Wave 9 introduced skill confidence as a flat score: +/-0.1 on colony success/failure, clamped to [0.1, 1.0]. This works at < 50 skills but has two problems that become material as the skill bank grows:

1. **No uncertainty signal.** A skill with confidence 0.7 from 1 observation is treated identically to one at 0.7 from 100 observations. The retrieval pipeline cannot distinguish "probably good" from "definitely good."

2. **No exploration incentive.** New skills start at 0.5 and must get lucky to be retrieved. Well-established skills dominate retrieval even when newer, potentially better skills exist. There is no exploration bonus.

Wave 9 also introduced cosine > 0.92 dedup at ingestion time. This catches near-exact duplicates but misses skills that express the same concept in different words (cosine 0.85--0.91). These semantic duplicates accumulate and dilute retrieval quality.

## Decision

### Part A: Bayesian confidence via Beta distribution

Replace the flat confidence score with a Beta distribution parameterized by `alpha` (success count + prior) and `beta` (failure count + prior).

**Stored as Qdrant payload fields:**
- `conf_alpha: float` -- initialized from existing confidence: `alpha = conf * 10`
- `conf_beta: float` -- initialized: `beta = (1 - conf) * 10`
- `conf_last_validated: str` -- ISO timestamp of last confidence update
- `confidence: float` -- **derived, backward-compatible**: `alpha / (alpha + beta)`

The derived `confidence` field ensures existing retrieval, display, and filtering code works unchanged. New code accesses alpha/beta directly for richer decisions.

**Update rule:** On colony completion, for each skill retrieved during the colony's rounds:
- Colony succeeded: `alpha += 1.0`
- Colony failed: `beta += 1.0`

No per-caste authority weights in Wave 11. Keep it simple -- every observation weighs equally. Per-caste weighting is a Wave 12+ refinement if warranted by data.

**Uncertainty:** `variance = (a * b) / ((a + b)^2 * (a + b + 1))`. Surfaced in the skill browser as a +/- bar alongside the confidence score. High uncertainty = wide bar = skill needs more observation.

**UCB exploration bonus in composite scoring:**

The existing composite score is:
```
score = 0.50 * semantic + 0.25 * confidence + 0.25 * freshness
```

Add an exploration term:
```
n_observations = alpha + beta - 2  # subtract the prior
exploration = c * sqrt(ln(total_colonies) / max(n_observations, 1))
score = 0.50 * semantic + 0.25 * confidence + 0.20 * freshness + 0.05 * exploration
```

Where `c = 0.1` (small -- exploration should nudge, not dominate). `total_colonies` is the count of completed colonies, available from the projection store. This gives under-observed skills a small retrieval boost that decays as they accumulate observations.

**Migration:** One-time script runs at startup if `conf_alpha` field is missing from any Qdrant point. Reads existing `confidence`, computes `alpha = conf * 10, beta = (1 - conf) * 10`, upserts. Creates Qdrant payload indexes on `conf_alpha`, `conf_beta`, `conf_last_validated`.

**Event:** `SkillConfidenceUpdated` fires once per colony completion with `skills_updated` count and `colony_succeeded` flag. This is an audit trail event -- the actual alpha/beta values live in Qdrant metadata (fast, fire-and-forget). The event store doesn't need per-skill granularity.

### Part B: LLM-gated deduplication with two-band thresholds

Replace single cosine > 0.92 gate with a two-band system:

| Band | Cosine range | Action | Cost |
|------|-------------|--------|------|
| **Band 1: Exact** | >= 0.98 | NOOP -- silently skip | Zero |
| **Band 2: Semantic** | [0.82, 0.98) | LLM classification | ~1 LLM call per candidate |
| **Below threshold** | < 0.82 | ADD -- ingest normally | Zero |

**LLM classification prompt** (Gemini Flash or local, temperature 0.0):
```
Compare these two skill descriptions and classify the relationship.
EXISTING: {existing_skill_text}
CANDIDATE: {new_skill_text}

Respond with exactly one word:
ADD -- candidate contains genuinely new information not in existing
UPDATE -- candidate improves, extends, or corrects existing
NOOP -- candidate is redundant with existing
```

**On each classification result:**
- **ADD:** Ingest normally (existing behavior).
- **UPDATE:** Merge texts via a second LLM call ("Combine these two skills into one, preserving all specific details: ..."). Re-embed merged text. Update Qdrant point. Combine Beta distributions: `new_alpha = old_alpha + candidate_alpha - 1, new_beta = old_beta + candidate_beta - 1`. Emit `SkillMerged` event.
- **NOOP:** Skip ingestion. Log via structlog.

**Cost model:** At ingestion time, the candidate is compared against top-5 existing skills by cosine similarity. Only those in the [0.82, 0.98) band trigger LLM classification. At typical ingestion rates (1-3 skills per colony), this is 0-5 LLM calls per colony. At Gemini Flash pricing ($0.30/M input), the cost is negligible -- well under $0.001 per colony.

**The dedup logic lives in `adapters/skill_dedup.py`**, not in `skill_lifecycle.py`. This separates the LLM-dependent dedup decision from the confidence tracking logic. `skill_lifecycle.py` calls `skill_dedup.classify()` during ingestion and acts on the result.

## Implementation notes

**No new dependencies.** Beta distribution arithmetic uses stdlib `math`. LLM calls use existing adapters. No scipy, no numpy.

**Qdrant payload indexes:** Add indexes on `conf_alpha` (FLOAT) and `conf_beta` (FLOAT) during the migration pass. `conf_last_validated` uses the existing DATETIME index pattern.

**Backward compatibility:** The `confidence` field remains the primary display value. Existing code that reads `confidence` from Qdrant payloads continues to work -- it's now a derived field updated alongside alpha/beta.

## Consequences

- **Modified files:** `surface/skill_lifecycle.py` (confidence update logic), `engine/context.py` (UCB in composite scoring)
- **New file:** `adapters/skill_dedup.py` (~100 LOC for classification + merge logic)
- **New Qdrant payload fields:** `conf_alpha`, `conf_beta`, `conf_last_validated`
- **New event:** `SkillConfidenceUpdated` (Phase A), `SkillMerged` (Phase B)
- **No new dependencies**
- **Migration:** One-time alpha/beta initialization from existing confidence values
- **Cost impact:** ~0-5 Gemini Flash calls per colony for LLM dedup classification (~$0.001 or less)
- **Rollback:** Remove alpha/beta fields -> system falls back to existing flat confidence. UCB term -> remove from composite formula. LLM dedup -> revert to cosine > 0.92 gate.
