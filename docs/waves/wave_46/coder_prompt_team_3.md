## Role

You own the analysis, demo, and publication-scaffolding track of Wave 46.

Your job is to prepare the truth-bearing artifacts that will consume Team 1's
product surfaces and Team 2's run data, without fabricating results before the
measurement exists.

This is a documentation-and-story track, not a place to invent numbers.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_46/wave_46_plan.md`
4. `docs/waves/wave_46/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `README.md`
7. `docs/OPERATORS_GUIDE.md`
8. `docs/KNOWLEDGE_LIFECYCLE.md`
9. any run manifests / eval outputs once Team 2 lands them
10. Team 1’s final endpoint/UI summaries once that work lands

## Core rule

Before you land any change, apply this test:

**If the benchmark disappeared tomorrow, would we still want this change in FormicOS?**

For this track, that means:

- clearer operator truth
- better audit/demo scaffolding
- more honest reporting artifacts

Not:

- glossy benchmark framing unsupported by the product

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `docs/waves/wave_46/` | OWN | analysis/report/demo/publication scaffolds created during this wave |
| `README.md` | MODIFY | only after real Wave 46 product surfaces/data exist |
| `docs/OPERATORS_GUIDE.md` | MODIFY | only after Team 1 lands operator surfaces |
| `docs/KNOWLEDGE_LIFECYCLE.md` | MODIFY | only if new user-facing truth needs documenting |
| other product docs | MODIFY | only for truthful post-Wave-46 updates |

## DO NOT TOUCH

- `src/formicos/eval/` - Team 2 owns
- `src/formicos/surface/routes/` and frontend files - Team 1 owns
- product core code
- event-union files

## Hard constraints

- Do not fabricate measurements.
- Do not write benchmark claims before the data exists.
- Do not overclaim “publication-ready” if only a pilot exists.
- Keep the product identity ahead of the benchmark story.

---

## Track A: Analysis scaffolding (`Must`)

Prepare the documents/templates that will later consume real data:

1. compounding-curve analysis template
2. architecture analysis/report template
3. run-review checklist
4. publication decision checklist

These should be scaffolded around the actual questions Wave 46 needs to answer:

- did the curve rise?
- was the gain from knowledge, foraging, coordination, or none of the above?
- where did the system fail?
- which entries actually mattered?

Do not fill them with made-up results.

---

## Track B: Demo scaffolding (`Must`)

Prepare the truth-based structure for:

1. live demo
2. benchmark demo
3. audit demo

### Guidance

- The audit demo should explicitly rely on real `knowledge_used` attribution.
- The operator surface from Team 1 should be part of the audit story, not
  treated as optional decoration.
- Prefer checklists, runbook steps, and capture templates over marketing copy.

---

## Track C: Publication and docs truth (`Should`)

Once Team 1 and Team 2 land real code/data:

1. update the main docs to reflect the new operator surfaces truthfully
2. add Wave 46 report references where appropriate
3. keep benchmark framing subordinate to product framing

### Explicitly keep out

- no fake leaderboard text
- no “we proved X” language before the data exists
- no stretching a pilot into a publication claim

---

## Validation

Run, at minimum:

1. `python scripts/lint_imports.py` if you touch any Python-side docs helpers
2. docs consistency spot-checks against Team 1 and Team 2 outputs
3. if you update README/operator docs, verify the claims against live files or accepted team summaries

## Summary must include

- which analysis/demo/publication scaffolds were created
- which docs were updated only after real code/data existed
- what still remains intentionally provisional pending measurement
- how you protected the product identity from benchmark drift
