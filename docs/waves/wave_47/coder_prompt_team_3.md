## Role

You own the Wave 47 Team 3 documentation and recipe track.

This is the truth-and-guidance pass after Teams 1 and 2 land the substrate.
You are not inventing new runtime behavior. You are aligning prompts, recipes,
and docs with what actually shipped.

## Mission

Update the repo guidance to reflect Wave 47 reality:

1. coder/queen recipe text for the new tool surface and fast-path behavior
2. operator/contributor docs for patch-file, git primitives, and preview
3. Wave 47 docs truth after the code lands

The core rule still applies:

**If the benchmark disappeared tomorrow, would we still want this change in
FormicOS?**

Yes. Good guidance and honest docs protect product identity and make the new
capabilities usable.

## Read First

1. `AGENTS.md`
2. `CLAUDE.md`
3. `docs/OPERATORS_GUIDE.md`
4. `docs/waves/wave_47/wave_47_plan.md`
5. `docs/waves/wave_47/acceptance_gates.md`
6. `config/caste_recipes.yaml`

Before editing, reread the final Team 1 and Team 2 landed files so the docs
match repo truth rather than wave intent.

## Owned Files

- `config/caste_recipes.yaml`
- `AGENTS.md`
- `CLAUDE.md`
- `docs/OPERATORS_GUIDE.md`
- `docs/waves/wave_47/*`

## Do Not Touch

- product code
- eval code
- frontend code
- contract/event code

## Required Work

### Track A: Recipe Truth

Update recipe prose for the real landed capabilities:

- `patch_file`
- accepted git tools
- `fast_path` guidance for simple tasks
- preview behavior if it shipped

Keep the recipe advice practical. Do not tell agents to use tools that did not
actually land.

### Track B: Operator/Contributor Docs

Update only where truth is settled:

- what `patch_file` is for
- what git tools exist
- what fast path means operationally
- how preview works, if it shipped on both spawn paths

If progress summary did not land, say nothing or mark it clearly deferred.

### Track C: Wave 47 Packet Truth

Refresh the Wave 47 docs after substrate acceptance:

- what shipped
- what was deferred
- any narrowed scope from the original plan

## Hard Constraints

- Do not fabricate shipped behavior
- Do not overclaim preview/progress support
- Do not write benchmark-first copy
- Do not broaden into a docs overhaul

## Validation

Run at minimum:

1. a grep sweep for stale field/tool names you replace
2. any lightweight docs validation already used in the repo, if applicable

## Summary Must Include

- which tools/behaviors you documented as shipped
- which items you kept explicitly deferred
- whether preview/progress made it into operator docs
- any places where the final code narrowed the original plan
