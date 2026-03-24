You own the Wave 51 docs-truth and vocabulary-alignment track.

This is the truth-refresh pass. You are not changing backend behavior and you
are not changing frontend rendering logic. Your job is to make the surrounding
docs and operator guidance reflect the product that Teams 1 and 2 are shipping
without reopening scope or fabricating capability.

## Mission

Land the docs-heavy parts of Wave 51:

1. propagate replay-safety truth into operator/contributor docs
2. document the Memory/Knowledge naming bridge once, cleanly
3. align operator-facing docs with renamed surfaces and deprecations
4. produce a truthful Wave 51 status handoff after Teams 1 and 2 land

The core rule still applies:

**If the benchmark disappeared tomorrow, would we still want this change in
FormicOS?**

Yes. A product that knows how to describe itself clearly is more trustworthy.

## Read First

1. `AGENTS.md`
2. `CLAUDE.md`
3. `docs/OPERATORS_GUIDE.md`
4. `docs/waves/wave_51/wave_51_plan.md`
5. `docs/waves/wave_51/acceptance_gates.md`
6. `docs/waves/wave_51/ui_audit_findings.md`
7. `docs/waves/wave_51/backend_audit_findings.md`
8. `docs/waves/wave_50/status_after_plan.md`

Then do a grep sweep for stale wording before editing.

## Owned Files

- `AGENTS.md`
- `CLAUDE.md`
- `docs/OPERATORS_GUIDE.md`
- `docs/waves/wave_51/status_after_plan.md` (create/update)
- small doc-only follow-ups in `docs/waves/wave_51/` if needed for truthful handoff

## Do Not Touch

- backend code
- frontend code
- `docs/REPLAY_SAFETY.md` (Team 1 owns this)
- `docs/waves/wave_51/wave_51_plan.md`
- `docs/waves/wave_51/acceptance_gates.md`
- `docs/waves/wave_51/cloud_audit_prompt.md`

Team 1 owns backend truth and `docs/REPLAY_SAFETY.md`. Team 2 owns the surface.

## Parallel-Safe Coordination Rules

You can start immediately, but your work is intentionally two-pass:

### Phase 1 -- start now

- grep for stale operator-facing language
- draft the doc updates that are already clearly true
- create a Wave 51 status handoff skeleton
- prepare wording changes that depend on Team 1 / Team 2 outcomes

### Phase 2 -- final truth refresh after Teams 1 and 2 land

Before finalizing docs, reread:

- Team 1's final `docs/REPLAY_SAFETY.md`
- Team 2's final surface labels / renamed views

Then make the final truth pass. This lets you start in parallel without
creating merge conflicts or stale claims.

## Required Work

### Track C6/C8: Replay-safety and naming truth in docs

After Team 1 lands `docs/REPLAY_SAFETY.md`:
- reference its classification in operator/contributor docs where useful
- document the Memory/Knowledge naming bridge once instead of letting it leak
  as scattered ambiguity

Do not duplicate the full classification matrix. Point to the canonical doc.

### Track C2/C3/C9: Surface vocabulary alignment

After Team 2 lands:
- update docs so operator-facing names match the actual UI
- reflect the final chosen label for the "Config Memory" surface
- remove stale "Skill Bank" language from operator-facing docs where it no
  longer matches the UI

### Track C4/C5: Deprecation and canonical-path truth

Once Team 1 lands deprecated Memory API signaling and any config-route cleanup:
- document the current path vs deprecated path clearly
- avoid overclaiming removal if the old route still serves

### Wave 51 status handoff

Create `docs/waves/wave_51/status_after_plan.md` that records:

- what actually shipped
- what stayed deferred
- which stale audit findings were correctly removed from scope
- the final truth of the replay-safety seams
- any remaining debt classified as surface-truth, docs debt, or follow-up debt

This file should be finished after the other two teams land, but you can create
the structure immediately.

## Hard Constraints

- Do not edit product code
- Do not invent capability that code does not ship
- Do not duplicate `docs/REPLAY_SAFETY.md`
- Do not reopen stale A3/A4 findings in docs
- Keep docs ASCII-clean and concise

## Validation

Run at minimum:

1. `rg -n "Skill Bank|Config Memory|/api/v1/memory|replay-safe|replay safety|Knowledge|Memory" AGENTS.md CLAUDE.md docs/OPERATORS_GUIDE.md docs/waves/wave_51`
2. a manual reread of Team 1 and Team 2 landed seams before finalizing `status_after_plan.md`

## Summary Must Include

- which stale terms you removed or clarified
- how the docs now point to replay-safety truth
- how Memory/Knowledge mapping is explained
- whether deprecated API mapping is now explicit
- what `status_after_plan.md` records as shipped vs deferred
