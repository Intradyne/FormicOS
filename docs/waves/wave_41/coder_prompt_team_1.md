## Role

You own the mathematical bridge-tightening track of Wave 41.

Your job is to:

- tighten live math seams that are already visible in the repo
- make retrieval and contradiction handling more coherent
- improve reasoning quality without turning this wave into a wholesale knowledge
  redesign

This is the "better bridges, not benchmark tricks" track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_41/wave_41_plan.md`
4. `docs/waves/wave_41/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `src/formicos/surface/trust.py`
7. `src/formicos/surface/knowledge_catalog.py`
8. `src/formicos/engine/context.py`
9. `src/formicos/surface/conflict_resolution.py`
10. `src/formicos/surface/maintenance.py`
11. `src/formicos/surface/proactive_intelligence.py`

## Coordination rules

- Keep the product identity straight: this wave strengthens FormicOS as a
  general-purpose colony system, not as a benchmark runner.
- Do **not** replace the full retrieval composite. Only tighten the live
  confidence / exploration seams inside it.
- Preserve overlay locality, replay truth, and federation-locality behavior.
- Stage contradiction work aggressively:
  - detection / classification first
  - resolution entry point second
  - richer hypothesis and fusion work only if the early stages are sound
- Do **not** add event families unless you hit a real replay blocker and can
  prove it.
- Do **not** touch execution substrate, workspace lifecycle, or measurement
  harness files in this track.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `src/formicos/surface/trust.py` | OWN | continuous trust weighting, hop-discount cleanup |
| `src/formicos/surface/knowledge_catalog.py` | OWN | retrieval math seam updates only |
| `src/formicos/engine/context.py` | OWN | exploration-confidence seam unification |
| `src/formicos/surface/conflict_resolution.py` | OWN | unified contradiction path |
| `src/formicos/surface/maintenance.py` | MODIFY | delegate contradiction logic to shared seam |
| `src/formicos/surface/proactive_intelligence.py` | MODIFY | contradiction rule should call the shared seam |
| `src/formicos/surface/scoring_math.py` | CREATE | only if a shared helper materially improves clarity |
| `tests/unit/surface/test_wave41_trust_weighting.py` | CREATE | trust weighting tests |
| `tests/unit/engine/test_wave41_confidence_scoring.py` | CREATE | TS/UCB seam tests |
| `tests/unit/surface/test_wave41_contradiction_pipeline.py` | CREATE | contradiction staging tests |

## DO NOT TOUCH

- `src/formicos/adapters/sandbox_manager.py` - Team 2 owns
- `src/formicos/engine/tool_dispatch.py` - Team 2 owns
- `src/formicos/surface/colony_manager.py` - Team 2 owns for workspace
  lifecycle work
- `tests/benchmark/*` - Team 3 owns
- optimization / evaluation reporting surfaces - Team 3 owns
- frontend files and top-level docs - not this track

## Overlap rules

- Team 2 owns repo-backed execution and multi-file validation.
  - Do not force them into a new execution contract unless the current seam is
    genuinely unusable.
- Team 3 owns measurement and optimization.
  - If you touch `knowledge_catalog.py` in a way that changes available
    retrieval metrics, note it clearly in your summary.
  - Reread `knowledge_catalog.py` after Team 3 lands if both tracks touched it.
- If richer contradiction stages do not fit cleanly after stages 1-2, stop at
  the cleaner plumbing boundary and report the follow-up.

---

## A1. Continuous Beta trust weighting in retrieval

### Required scope

1. Replace the coarse status-band retrieval seam with live posterior-aware trust
   weighting where the current code already has access to `PeerTrust`.
2. Replace fixed hop discounting with a more honest posterior-aware path if the
   live seam supports it cleanly.
3. Keep the change bounded so the retrieval path remains understandable.

### Hard constraints

- Do **not** hide uncertainty behind a new magic constant soup.
- Do **not** regress local-first overlay behavior.
- Do **not** break existing federation tests without replacing them with a
  stronger equivalent.

---

## A2. TS/UCB confidence-term unification

### Required scope

1. Create one shared exploration-confidence helper or equivalent seam for:
   - `knowledge_catalog.py`
   - `context.py`
2. Replace only the confidence / exploration term, not the whole scoring model.
3. Keep the surrounding composite weights legible and stable unless a small
   correction is clearly required.

### Hard constraints

- Do **not** introduce a second competing exploration strategy.
- Do **not** bury the logic in unrelated helper layers.

---

## A3. Contradiction pipeline overhaul

### Required scope

Stage 1:
- unify contradiction detection / classification
- distinguish:
  - contradiction
  - complement
  - temporal update

Stage 2:
- expose one clearer resolution entry point
- make `maintenance.py` and `proactive_intelligence.py` depend on that seam
  instead of carrying rival partial logic

### Optional later scope

Only if stages 1-2 are clearly stable:

Stage 3:
- bounded hypothesis-set handling for close conflicts

Stage 4:
- richer Bayesian / evidence-weighted fusion

### Hard constraints

- Do **not** jump straight to a full knowledge-model rewrite.
- Do **not** claim richer fusion than the code actually implements.
- Keep operator-facing truth inspectable.

---

## Validation

Run, at minimum:

1. `python scripts/lint_imports.py`
2. targeted pytest for trust, retrieval, context scoring, and contradiction
   seams
3. full `python -m pytest -q` if your changes reach across multiple owned files

Your summary must include:

- what changed in trust weighting
- how the TS/UCB seam was unified
- which contradiction stages actually landed
- what you deliberately deferred and why
