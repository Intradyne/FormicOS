# Compounding Curve Analysis Template

**Run ID:** _(from manifest)_
**Date:** _(from manifest completed_at)_
**Suite:** _(from conditions.suite_id)_
**Commit:** _(from manifest or `git rev-parse HEAD`)_

---

## 1. Conditions Summary

Fill from the run manifest (`data/eval/sequential/{suite_id}/manifest_{timestamp}_{run_id}.json`)
and result file (`run_{timestamp}_{run_id}.json`):

| Field | Value |
|-------|-------|
| run_id | |
| suite_id | |
| task_order | |
| strategy | |
| model_mix | |
| budget_per_task | |
| max_rounds_per_task | |
| escalation_policy | |
| config_hash | |
| knowledge_mode | _(accumulate / empty / snapshot)_ |
| foraging_policy | _(disabled / reactive / proactive)_ |
| random_seed | |
| git_commit | |

If any condition changed between this run and a comparison run, note that
explicitly before drawing conclusions.

---

## 2. Raw Curve

Plot `quality_score` vs `sequence_index` from `compute_curves()` output.

| Task | Seq | Quality | Status | Rounds | Cost |
|------|-----|---------|--------|--------|------|
| | | | | | |

**Trend:** _(rising / flat / declining, with % change from first half to second half)_

Questions to answer:
- Did quality improve as knowledge accumulated?
- Were there sudden drops? What task caused them?
- Did any task fail outright? Why?

---

## 3. Cost-Normalized Curve

Plot `quality_per_dollar` vs `sequence_index`.

| Task | Seq | Quality/$ |
|------|-----|-----------|
| | | |

**Trend:** _(rising / flat / declining)_

Questions to answer:
- Did later tasks get cheaper per unit of quality?
- Or did knowledge accumulation add overhead without benefit?

---

## 4. Time-Normalized Curve

Plot `quality_per_second` vs `sequence_index`.

| Task | Seq | Quality/s |
|------|-----|-----------|
| | | |

**Trend:** _(rising / flat / declining)_

Questions to answer:
- Did wall-clock time decrease for later tasks?
- Was the time reduction from knowledge retrieval or from fewer rounds?

---

## 5. Knowledge Contribution

From `knowledge_contribution` in curve output:

| Metric | Value |
|--------|-------|
| total_extracted | |
| total_accessed | |
| access_ratio | |

**Extraction by task:**

| Task | Entries Extracted | Entries Accessed |
|------|-------------------|------------------|
| | | |

Questions to answer:
- Which tasks produced knowledge that later tasks consumed?
- Was the access ratio above zero? (If zero, knowledge never transferred.)
- Which specific entries were accessed most? _(requires populated knowledge_used)_

---

## 6. Knowledge Attribution

From `knowledge_attribution` in TaskResult (populated from projection truth
via `_build_attribution()`). Each task records `used` (entries accessed) and
`produced` (entries created), with entry IDs, titles, source task/colony,
category, and sub_type.

Fill:

| Later Task | Entry Used | Produced By | Entry Type | Source |
|------------|-----------|-------------|------------|--------|
| | | | | colony / forager |

Questions to answer:
- Did colony-extracted knowledge compound across tasks?
- Did forager-sourced knowledge contribute to task success?
- Were any entries accessed but not useful (negative feedback)?

---

## 7. Failure Analysis

For each failed or low-quality task:

| Task | Quality | Failure Mode | Root Cause | Knowledge Gap? |
|------|---------|--------------|------------|----------------|
| | | | | |

Categories:
- **task difficulty** — the task was genuinely hard
- **knowledge gap** — relevant knowledge existed but was not retrieved
- **knowledge miss** — no relevant knowledge existed yet
- **model limitation** — the model could not solve regardless of knowledge
- **harness bug** — the eval harness contaminated the result

---

## 8. Comparison (if multiple configs)

| Config | Avg Quality | Avg Cost | Trend | Notes |
|--------|-------------|----------|-------|-------|
| single-agent | | | | |
| colony, knowledge=empty | | | | |
| colony, knowledge=accumulate | | | | |
| colony, knowledge=accumulate+foraging | | | | |

Questions to answer:
- Did the full colony materially beat the no-knowledge colony?
- Did foraging add signal beyond colony-extracted knowledge alone?
- If the colony did not beat single-agent, why?

---

## 9. Conclusion

_(One paragraph. What did the curve show? What is the honest takeaway?)_

Three acceptable outcomes:
- **Rising curve** — knowledge compounds. State which domain/task cluster showed the strongest effect.
- **Mixed curve** — knowledge compounds in specific domains but not universally. State which domains benefited and which did not.
- **Flat curve** — no measurable compounding. State the most likely reason and what would need to change.

Do not overclaim. If the pilot is small, say so.
