## Role

You own the forager-completion track of Wave 45.

Your job is to:

- wire proactive foraging without polluting the diagnostic layer
- add bounded source-credibility tiers to the forager admission path
- optionally tighten search/fetch policy consistency if it stays small

This is the "finish the forager subsystem we already built" track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_45/wave_45_plan.md`
4. `docs/waves/wave_45/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `src/formicos/surface/proactive_intelligence.py`
7. `src/formicos/surface/forager.py`
8. `src/formicos/surface/self_maintenance.py`
9. `src/formicos/adapters/content_quality.py`
10. `src/formicos/surface/app.py`
11. `src/formicos/adapters/web_search.py`

## Coordination rules

- Prefer Option A from the plan: proactive insights emit a bounded
  `forage_signal`, and an existing/lightweight dispatcher hands it to the
  Forager service.
- Keep `proactive_intelligence.py` pure. Do **not** turn it into a network or
  event-emission module.
- Do **not** add event types for proactive foraging.
- Keep source credibility as a provenance/admission signal. Do **not** muddle
  it into the structural content-quality score itself.
- Search-through-egress consistency is a `Should`, not a `Must`.
- If you tighten search/fetch consistency, keep the search adapter interface
  stable and bounded.
- Do **not** add a new adapter or subsystem.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `src/formicos/surface/proactive_intelligence.py` | OWN | bounded proactive forage signals on existing high-value rules |
| `src/formicos/surface/forager.py` | OWN | proactive signal handling + credibility tier consumption |
| `src/formicos/surface/self_maintenance.py` | MODIFY | lightweight dispatcher path if needed |
| `src/formicos/adapters/content_quality.py` | MODIFY | bounded domain-tier lookup only if you keep it here |
| `src/formicos/surface/app.py` | MODIFY | optional search-through-egress consistency wiring |
| `tests/` | CREATE/MODIFY | proactive-foraging, credibility-tier, and consistency tests |

## DO NOT TOUCH

- `src/formicos/surface/projections.py` - Team 2 owns
- `src/formicos/surface/knowledge_catalog.py` - Team 2 owns
- `src/formicos/engine/runner.py` - Team 2 owns gated topology work
- docs and wave packet files - Team 3 owns documentation truth
- event-union files - out of scope for this wave

---

## Bucket 1A: Proactive foraging triggers

### Required scope

1. Add bounded forage signals to the highest-value existing insight rules.
2. Keep the signal shape simple and compatible with `ForagerService`.
3. Reuse the existing service loop for proactive work.

### Hard constraints

- Do **not** replace or break existing `suggested_colony` behavior.
- Additive is the right move: keep `suggested_colony`, add `forage_signal`
  beside it where appropriate.
- Do **not** emit `ForageRequested` directly from `proactive_intelligence.py`
  unless you hit a real blocker and can prove the dispatcher approach fails.
- Do **not** make proactive foraging a broad autonomous browsing system.

### Guidance

- Start with `_rule_stale_cluster`, `_rule_coverage_gap`, and
  `_rule_confidence_decline`.
- `KnowledgeInsight` is the natural place to carry a lightweight signal if you
  need to extend the model.
- `self_maintenance.py` is already the existing dispatcher-shaped seam for
  insight follow-through. Prefer reusing or extending that pattern over
  inventing a new orchestration surface.

---

## Bucket 1B: Source credibility tiers

### Required scope

1. Add a simple domain-tier mapping.
2. Feed that signal into the forager provenance/admission path.
3. Preserve override semantics (`trust` boosts, `distrust` blocks).

### Hard constraints

- Keep the mapping small and legible.
- Do **not** turn this into a learned reputation system.
- Do **not** replace existing content-quality logic with source tiers.

### Guidance

- This is more provenance than content quality. If the cleanest home is
  `forager.py`, that is preferable to forcing it into `content_quality.py`.
- The admission path should end up with a materially better provenance signal,
  not a second parallel trust system.

---

## Bucket 1C: Search-through-egress consistency (`Should`)

### Optional scope

If you land this:

1. keep `web_search.py` interface-compatible
2. reuse the existing startup wiring seam in `surface/app.py`
3. make search/fetch identity and timeout policy more consistent without
   pretending DDG/Serper are fetched pages subject to the same robots rules

### Hard constraints

- Do **not** redesign the search adapter.
- Do **not** create a new search client subsystem.

---

## Validation

Run, at minimum:

1. `python scripts/lint_imports.py`
2. targeted pytest for proactive-intelligence, forager, and search/egress
   seams
3. full `python -m pytest -q` if your changes broaden across maintenance,
   runtime, or forager integration surfaces

## Developmental evidence

Your summary must include:

- which insight rules now produce proactive forage signals
- where the dispatcher bridge lives
- how source credibility changes the admission path
- whether search-through-egress consistency landed or stayed deferred
- what you rejected to keep this track bounded
