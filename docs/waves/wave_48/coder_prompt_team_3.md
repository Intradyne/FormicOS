## Role

You own the Wave 48 recipe and docs-truth track.

This is the grounded-specialist and operator-guidance pass. You are not
inventing runtime behavior. You are aligning recipes and docs with what Teams 1
and 2 actually ship.

## Mission

Update the repo guidance to reflect Wave 48 reality:

1. ground the Reviewer and Researcher recipes
2. document the connected operator flow truthfully
3. keep the Wave 48 packet honest about what shipped and what deferred

The core rule still applies:

**If the benchmark disappeared tomorrow, would we still want this change in
FormicOS?**

Yes. Honest guidance and grounded castes make the real system usable.

## Read First

1. `AGENTS.md`
2. `CLAUDE.md`
3. `docs/OPERATORS_GUIDE.md`
4. `docs/waves/wave_48/wave_48_plan.md`
5. `docs/waves/wave_48/acceptance_gates.md`
6. `config/caste_recipes.yaml`

Before editing, reread the final Team 1 and Team 2 landed files so the recipes
and docs match repo truth rather than the planned ideal.

## Owned Files

- `config/caste_recipes.yaml`
- `AGENTS.md`
- `CLAUDE.md`
- `docs/OPERATORS_GUIDE.md`
- `README.md` only if a small truthful capability update is warranted
- `docs/waves/wave_48/*`

## Do Not Touch

- product code
- frontend code
- backend code
- contract/event code

## Required Work

### Track A: Ground The Reviewer And Researcher Recipes

Update recipe guidance to match the landed tool surface and the intended role:

- Reviewer: narrow, skeptical, read-only verifier with access to real repo
  truth
- Researcher: project-aware synthesizer with a truthful fresh-information path

Important guidance rule:

- do not revert to a "radical specialization through blindness" story
- the correct framing is specialization without blindness
- keep automatically injected or recipe-described context tight and curated;
  do not bloat prompts with low-signal auto-context

### Track B: Document The Fresh-Information Decision Honestly

One of two outcomes will exist after Team 1 lands:

1. preferred: mediated Forager access / `request_forage`
2. fallback: direct Researcher web access

Document whichever one actually shipped.

If the fallback shipped, say so plainly and preserve the tradeoff note. Do not
pretend the clean mediated split landed if it did not.

Also keep the Forager story truthful:

- the Forager remains a service-backed acquisition path
- do not rewrite the docs into a rigid six-caste canonical model that outruns
  repo truth

### Track B2: Minimal Colony First

The research and current product direction both support a small-team default.

Update Queen-facing guidance so it clearly recommends:

- `fast_path` / single-agent or smallest viable team for simple tasks
- multi-caste colonies only when the task genuinely needs coordination,
  broader evidence gathering, or independent verification

This is not benchmark tuning. It is the product rule that simple work should
not pay unnecessary multi-agent overhead.

### Track C: Operator Docs Truth

Update only where truth is settled:

- thread timeline
- enriched colony audit with Forager attribution
- Review-step preview/confirmation
- running-state clarity only if it actually landed

Do not overclaim progress richness.

### Track D: Wave 48 Packet Truth

Refresh the Wave 48 docs after the substrate lands:

- what shipped
- what deferred
- where the final implementation narrowed the original plan

Keep one explicit note for follow-on work:

- post-Wave-48 measurement should isolate caste-grounding effects

## Hard Constraints

- Do not fabricate shipped behavior
- Do not overclaim the Researcher/Forager split
- Do not publish a rigid caste taxonomy that conflicts with live repo truth
- Do not broaden into a docs overhaul

## Validation

Run at minimum:

1. a grep sweep for stale recipe/tool/path claims you replace
2. any lightweight docs validation already used in the repo, if applicable

## Summary Must Include

- exactly how Reviewer and Researcher recipes changed
- whether the fresh-information path landed as mediated Forager access or
  direct web fallback
- which Wave 48 UI behaviors you documented as shipped
- which items you kept explicitly deferred
