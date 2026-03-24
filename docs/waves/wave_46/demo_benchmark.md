# Benchmark Demo Scaffold

A runbook for presenting FormicOS measurement results. This demo shows
honest score reporting with full context — cost, variance, conditions,
and limitations.

---

## Prerequisites

- [ ] At least one complete eval run with the pilot suite (or larger)
- [ ] Compounding curve analysis filled from real data
      ([compounding_curve_analysis.md](compounding_curve_analysis.md))
- [ ] Run review checklist completed
      ([run_review_checklist.md](run_review_checklist.md))
- [ ] Run manifests available with locked conditions

---

## Demo Structure (target: 8-12 minutes)

### Part 1: What We Measured (2 min)

1. State the suite: how many tasks, what categories, what order
2. State the configs compared:
   - single-agent baseline (if run)
   - colony with knowledge=empty
   - colony with knowledge=accumulate
   - colony with knowledge=accumulate + foraging (if run)
3. State what was locked: model mix, budget, escalation policy, task order
4. State what was NOT controlled (if anything)

### Part 2: The Compounding Curve (3-4 min)

Present the real curve from the analysis template.

1. Show the raw quality curve
   - Point out the trend direction
   - Call out specific inflection points
2. Show the cost-normalized curve
   - Did quality-per-dollar improve?
3. Show the knowledge contribution table
   - entries_extracted and entries_accessed by task
   - access_ratio — did knowledge actually transfer?
4. If multiple configs were compared:
   - Show the comparison table
   - State which config won, by how much, and with what confidence

### Part 3: Where It Broke (2-3 min)

Show failures honestly. This is the most important part for credibility.

1. Show failed tasks and their failure modes
2. Show tasks where knowledge was available but not retrieved
3. Show tasks where retrieved knowledge was not useful
4. If the curve is flat: say so. Explain the most likely reason.

### Part 4: What We Claim (2 min)

State claims precisely:

- "In this {N}-task pilot with {model}, quality trend was {X}%
  {rising/declining} from first half to second half."
- "Knowledge access ratio was {Y}, meaning {Z}% of later tasks
  retrieved entries from earlier tasks."
- "Total cost was ${C} across {N} tasks."

Do NOT say:
- "FormicOS proves compounding intelligence"
- "The system consistently outperforms"
- "Publication-quality results" (unless the publication checklist passes)

---

## Data Artifacts to Prepare

| Artifact | Source | Status |
|----------|--------|--------|
| Raw curve chart | `compute_curves()` output | |
| Cost-normalized chart | `compute_curves()` output | |
| Comparison table | Manual from multiple run manifests | |
| Failure analysis | `compounding_curve_analysis.md` section 7 | |
| Locked conditions summary | Run manifest `conditions` block | |

---

## Presentation Integrity Rules

1. Every number shown must come from a real run manifest
2. If only 1 run exists, do not show error bars or confidence intervals
3. `knowledge_used` and `knowledge_attribution` are populated from
   projection truth — use real entry IDs and titles in attribution claims
4. Cost must always appear alongside quality
5. The benchmark framing must be subordinate to the product framing:
   "We measured FormicOS doing real tasks" not "FormicOS scores X on
   benchmark Y"
