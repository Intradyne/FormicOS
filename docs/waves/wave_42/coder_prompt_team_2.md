## Role

You own the contradiction-resolution and extraction-quality track of Wave 42.

Your job is to:

- make contradiction resolution respect the classification logic that already
  exists
- improve extraction quality without turning the gate into a blunt filter
- keep operator-facing truth inspectable

This is the "classification-aware resolution and cleaner knowledge input"
track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_42/wave_42_plan.md`
4. `docs/waves/wave_42/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `src/formicos/surface/conflict_resolution.py`
7. `src/formicos/surface/knowledge_catalog.py`
8. `src/formicos/surface/proactive_intelligence.py`
9. `src/formicos/surface/projections.py`
10. `src/formicos/surface/colony_manager.py`
11. `src/formicos/surface/admission.py`
12. `src/formicos/surface/maintenance.py`

## Coordination rules

- Stage 2 contradiction resolution is the Must-ship core of this track.
- Stage 3 competing-hypothesis surfacing is optional and should land only if it
  stays bounded.
- Do **not** turn this wave into a full Bayesian-fusion or knowledge-model
  redesign.
- Complements and temporal updates should not be forced through a winner-take-
  all contradiction path.
- Extraction quality gates must be conjunctive and evidence-aware, not just
  short-text filters.
- If you use structural-specificity signals, consume Team 1's workspace-scoped
  outputs through a clean seam and degrade gracefully when they are absent.
- Do **not** touch static-analysis or topology-prior seams owned by Team 1.
- Do **not** touch adaptive-evaporation runtime control owned by Team 3.
- Do **not** add event types unless you hit a real replay blocker and can prove
  it.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `src/formicos/surface/conflict_resolution.py` | OWN | Stage 2 resolution upgrade |
| `src/formicos/surface/knowledge_catalog.py` | OWN | optional Stage 3 retrieval surfacing |
| `src/formicos/surface/projections.py` | MODIFY | only if Stage 3 needs bounded projection truth |
| `src/formicos/surface/proactive_intelligence.py` | MODIFY | contradiction insight precision |
| `src/formicos/surface/colony_manager.py` | OWN | extraction-quality gating only |
| `src/formicos/surface/admission.py` | MODIFY | only if extraction/admission interaction needs bounded cleanup |
| `tests/unit/surface/test_wave42_resolution.py` | CREATE | class-aware resolution tests |
| `tests/unit/surface/test_wave42_extraction_quality.py` | CREATE | quality-gating tests |
| `tests/unit/surface/test_wave42_competing_hypotheses.py` | CREATE | only if Stage 3 lands |

## DO NOT TOUCH

- `src/formicos/adapters/code_analysis.py` - Team 1 owns
- `src/formicos/engine/runner.py` topology-prior seam - Team 1 owns
- `src/formicos/engine/runner.py` adaptive-evaporation seam - Team 3 owns
- `src/formicos/engine/strategies/stigmergic.py` - Team 1 owns if touched
- frontend files and wave docs - not this track

## Method-level overlap rules

`src/formicos/surface/colony_manager.py` is shared this wave.

- You own:
  - `_hook_memory_extraction`
  - `extract_institutional_memory`
  - `_check_inline_dedup`
  - any bounded extraction-quality helpers added for this track
- You do **not** own structural-analysis integration methods added by Team 1.
- If you need structural hints for extraction quality, consume Team 1's outputs
  through a clean seam instead of editing their analysis code.

---

## Pillar 3: Contradiction resolution upgrade

### Required scope

Stage 2:

1. Make `resolve_conflict()` respect the relation produced by
   `classify_pair()`.
2. Ensure:
   - contradiction pairs resolve as contradictions
   - complement pairs stay linked / co-usable
   - temporal updates behave like updates, not contradictions
3. Keep the resolution path inspectable and bounded.

### Optional scope

Stage 3:

- bounded competing-hypothesis surfacing in retrieval / projection truth

### Hard constraints

- Do **not** overclaim richer fusion than the code actually implements.
- Do **not** let Stage 3 sprawl across the whole product surface.
- Do **not** make Stage 3 depend on frontend redesign or broad audit-surface
  work in this wave.

---

## Pillar 5: Extraction quality gating

### Required scope

1. Improve extraction quality with conjunctive gates.
2. Use signals such as:
   - novelty
   - duplication
   - structural specificity
   - weak/low-value output characteristics
3. Preserve genuinely useful concise entries.

### Hard constraints

- Do **not** use "short alone" as a blanket demotion rule.
- Do **not** silently suppress large classes of useful memory.
- Keep the extraction/admission interaction understandable.

---

## Developmental eval

Include small focused evals for:

- contradiction pairs vs complement pairs vs temporal updates
- extraction quality before/after on noisy vs useful concise outputs

Report:

- what class-specific behavior changed
- whether obvious duplicate/noise extraction dropped
- whether concise useful entries still survive

This is a development check, not a public-proof evaluation.

---

## Validation

Run, at minimum:

1. `python scripts/lint_imports.py`
2. targeted pytest for contradiction and extraction seams
3. full `python -m pytest -q` if Stage 3 or projection changes broaden the risk

Your summary must include:

- what Stage 2 resolution behavior now does
- whether Stage 3 landed or was deferred
- what extraction-quality gates were added
- what you deliberately rejected to keep the track bounded
