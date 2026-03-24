## Role

You own the documentation-truth track of Wave 45.

Your job is to:

- make the post-Wave-45 system legible to operators and contributors
- update the docs only for what actually ships
- keep the proof wave from starting with stale operator guidance

This is the "tell the truth about the completed system before Wave 46 measures
it" track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/DEVELOPMENT_WORKFLOW.md`
4. `docs/waves/wave_45/wave_45_plan.md`
5. `docs/waves/wave_45/acceptance_gates.md`
6. `docs/waves/session_decisions_2026_03_19.md`
7. `docs/OPERATORS_GUIDE.md`
8. `docs/KNOWLEDGE_LIFECYCLE.md`
9. `docs/DEPLOYMENT.md`
10. `README.md`

## Coordination rules

- Document only what actually lands from Wave 45.
- Keep the docs aligned to the accepted code, not the plan's wish list.
- If the gated topology item does not land, say so plainly.
- If the search-through-egress `Should` does not land, do not imply that it
  did.
- Keep the operator-facing language concrete and useful rather than internal
  or research-shaped.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `CLAUDE.md` | OWN | current repo/wave truth |
| `AGENTS.md` | OWN | capability/coordinator truth if changed |
| `docs/OPERATORS_GUIDE.md` | OWN | operator-facing foraging + contradiction behavior |
| `docs/KNOWLEDGE_LIFECYCLE.md` | OWN | knowledge and contradiction truth |
| `docs/DEPLOYMENT.md` | OWN | egress/search config truth if changed |
| `README.md` | MODIFY | capability summary only if needed |

## DO NOT TOUCH

- implementation files owned by Team 1 or Team 2
- wave packet files after dispatch, unless explicitly asked for a docs-only fix

---

## Documentation scope

### Required scope

1. Update the docs for proactive foraging if it ships.
2. Update the docs for competing-hypothesis surfacing if it ships.
3. Update the docs for source credibility tiers if they ship.
4. Keep the current event-union and forager/deployment truth accurate.

### Hard constraints

- Do **not** invent stronger capabilities than the code supports.
- Do **not** expand this into a UI redesign or tutorial wave.
- Do **not** let docs trail the accepted system by a whole wave.

### Guidance

- Operators should be able to understand:
  - when foraging is reactive vs proactive
  - how domain trust/distrust and source credibility affect admission
  - what it means when two entries are surfaced as competing
  - what still remains bounded or deferred before Wave 46
- Contributors should be able to understand:
  - which Wave 45 seams are now closed
  - which gated/should items remained deferred

---

## Validation

Run, at minimum:

1. any existing doc-link or build checks if present
2. targeted readback against the files you documented

You do **not** need to turn this into a code test run unless your doc work
depends on it.

## Developmental evidence

Your summary must include:

- which docs were updated
- which new behaviors were documented
- which planned Wave 45 items did **not** land and were intentionally kept out
- any operator-facing caveats that still matter before Wave 46
