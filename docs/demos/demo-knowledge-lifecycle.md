# Demo: Knowledge Lifecycle — From Creation to Decay and Recovery

This walkthrough traces a knowledge entry through every stage of its
lifecycle: creation, sub-type classification, confidence evolution, merge,
archival decay, and recovery on re-access.

---

## Prerequisites

- FormicOS running with a workspace
- Multiple colonies to drive confidence evolution

## Stage 1: Entry creation with sub-type

A coder colony completes a task and the archivist extracts:

```
Entry: "Always use parameterized queries to prevent SQL injection"
  entry_type: skill
  sub_type: anti_pattern (describes what NOT to do)
  decay_class: stable (domain knowledge, ~139 day half-life)
  conf_alpha: 5.0, conf_beta: 5.0 (Beta prior)
  status: candidate
  domains: ["security", "database"]
```

The security scan clears it (scan_status: safe), and the source colony
succeeded, so status promotes to `verified`.

**Proactive briefing**: No insight yet — entry is new and untested.

## Stage 2: Confidence evolution through colony outcomes

Over 20 colonies:
- 15 access the entry and succeed → `alpha += 15` → `alpha = 20`
- 3 access the entry and fail → `beta += 3` → `beta = 8`
- Posterior mean: 20/28 = 71.4% — tier HIGH

**Knowledge browser shows**:
- Green HIGH badge
- "High confidence (71%) — 18 observations, stable decay class."
- Hover: Mean 0.714 ± 0.167, 18 observations, stable decay

**Proactive briefing**:
```json
{
  "severity": "info",
  "category": "confidence",
  "title": "SQL injection prevention knowledge validated",
  "detail": "Entry has reached HIGH confidence after 18 observations."
}
```

## Stage 3: Duplicate detected and merged

A new colony extracts a similar entry:
"Use prepared statements to avoid SQL injection"
- Cosine similarity: 0.94 (above 0.92 auto-merge threshold)

Dedup consolidation runs:
1. `MemoryEntryMerged` event emitted
2. `content_strategy: keep_longer` (original has more content)
3. Domains unioned: `["security", "database", "sql"]`
4. `merged_from` provenance chain updated

**Knowledge browser**: Entry shows "merged x1" indicator.
**Power panel**: Shows merged_from IDs.

## Stage 4: Co-occurrence clustering

The SQL injection entry is frequently accessed alongside:
- "Database connection pooling patterns" (co-occurrence weight: 3.2)
- "Input validation strategies" (co-occurrence weight: 2.8)

These form a co-occurrence cluster. When one is retrieved, the others
get a slight boost in the composite scoring (Wave 34 weight: 0.05).

## Stage 5: Thread archival and decay

The thread containing the original work is archived.
Unpromoted thread-scoped entries undergo confidence decay:
- `alpha *= 0.8`, `beta *= 1.2`
- But this entry was promoted to workspace-wide, so it is **not affected**.

For comparison, an ephemeral entry in the same thread:
- Before: `Beta(8, 5)` → 61.5% confidence
- After archival: `Beta(6.4, 6.0)` → 51.6% confidence
- Plus gamma-decay at query time: `gamma=0.98` per day

## Stage 6: Staleness and prediction errors

After 60 days without access:
- Gamma-decay applied at query time: `0.995^60 ≈ 0.741`
- Effective alpha: `5 + 0.741 * 15 = 16.12` (stable decay class)
- Still HIGH tier — stable decay class prevents rapid degradation

If the entry were ephemeral:
- `0.98^60 ≈ 0.298` — effective alpha drops dramatically
- Would fall to MODERATE or LOW tier

## Stage 7: Recovery on re-access

A new colony accesses the entry and succeeds:
- `CRDTCounterIncremented(field="successes", delta=1)` with fresh timestamp
- The fresh observation has `gamma^0 = 1.0` weight — no decay
- Effective alpha jumps back up

After 3 re-observations:
- Entry climbs back to HIGH tier
- Thompson Sampling gives it strong scores again

**Proactive briefing**:
```json
{
  "severity": "info",
  "category": "confidence",
  "title": "SQL injection knowledge restored",
  "detail": "After 60 days dormant, 3 recent successes have restored confidence to 73%."
}
```

## Stage 8: Prediction errors

If a search query "how to sanitize HTML output" returns this SQL injection
entry as the top result (cosine < 0.38):
- `prediction_error_count += 1`
- After 5 prediction errors with < 3 accesses, the stale sweep would flag it
- But this entry has high access count, so it survives

**Proactive briefing** (if accumulated):
```json
{
  "severity": "attention",
  "category": "coverage",
  "title": "Coverage gap: HTML sanitization",
  "detail": "5 queries about HTML sanitization returned irrelevant results.",
  "suggested_action": "Consider creating targeted knowledge for HTML/XSS prevention."
}
```

## What to observe

- **Knowledge browser**: Watch the confidence bar grow, tier badge change
  from EXPLORATORY → MODERATE → HIGH over colony cycles.
- **Sub-type badge**: Visible in entry header (anti_pattern).
- **Power panel**: Raw alpha/beta, merged_from chain, decay class.
- **Proactive briefing**: Insights surface at each lifecycle transition.
- **Hover detail**: Mean ± CI, observation count, decay class, prediction
  errors all visible on hover.
