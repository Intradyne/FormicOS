## Role

You own the product-coherence track of Wave 46.

Your job is to make the Forager visible, operable, and inspectable for real
operators, then tighten the smallest remaining observability/policy seams that
clearly help normal product use.

This is **not** a benchmark track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_46/wave_46_plan.md`
4. `docs/waves/wave_46/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `src/formicos/surface/app.py`
7. `src/formicos/surface/routes/api.py`
8. `src/formicos/surface/forager.py`
9. `src/formicos/surface/projections.py`
10. `frontend/src/components/knowledge-browser.ts`
11. `frontend/src/components/proactive-briefing.ts`
12. `src/formicos/adapters/telemetry_otel.py`

## Core rule

Before you land any change, apply this test:

**If the benchmark disappeared tomorrow, would we still want this in FormicOS?**

If the answer is no, it does not belong in this track.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `src/formicos/surface/routes/api.py` | OWN | add thin forager operator endpoints or extract a bounded route module |
| `src/formicos/surface/app.py` | OWN | OTel startup wiring; bounded search/fetch coherence work |
| `frontend/src/components/knowledge-browser.ts` | OWN | web-source visibility for forager provenance |
| `frontend/src/components/proactive-briefing.ts` | OWN | bounded forager activity surfacing |
| `tests/` | CREATE/MODIFY | endpoint, product-surface, and startup-path coverage |

## DO NOT TOUCH

- `src/formicos/eval/` - Team 2 owns
- `config/eval/` - Team 2 owns
- product core event files
- `src/formicos/surface/self_maintenance.py`
- `src/formicos/surface/proactive_intelligence.py`
- docs packet files in `docs/waves/wave_46/` - Team 3 owns wave-doc polish

## Hard constraints

- No new event types.
- No new adapter or subsystem.
- No benchmark-specific product surface.
- Reuse existing Forager service and projection truth.
- Keep OTel additive beside JSONL.
- If you touch search/fetch consistency, keep it bounded and interface-stable.

---

## Track A: Forager operator surface (`Must`)

### Required scope

1. Add a manual forage trigger route.
2. Add a domain override route for `trust` / `distrust` / `reset`.
3. Add a forage cycle history route.
4. Add a domain strategy / override visibility route.

### Guidance

- Thin wrappers are the right implementation.
- Reuse `ForagerService` and projection state.
- The `ForagerService` instance is attached to runtime at
  `runtime.forager_service` in `app.py`. Your API routes access it through
  the runtime object, following the same pattern as other route handlers.
- Route assembly can stay in `api.py` or move to a bounded route module if
  that keeps the file saner. Do **not** turn this into a routing redesign.
- The operator should be able to inspect what the Forager did and steer it.

### Explicitly keep out

- no new forager event types
- no long-running orchestration layer
- no separate forager dashboard backend

---

## Track B: Web-source visibility in product UI (`Must`)

### Required scope

When an entry has forager provenance, the operator should see at least:

1. a visible web-source indicator
2. source URL
3. one or more of:
   - fetch timestamp
   - forager query
   - source credibility
   - extraction quality score

### Guidance

- Reuse the existing knowledge detail / entry payload.
- Do not invent a second provenance system in the frontend.
- The change should make the audit demo possible from the normal UI.

### Explicitly keep out

- no new frontend subsystem
- no separate “benchmark mode” knowledge view

---

## Track C: Observability and policy cohesion (`Must` + `Should`)

### Must: OTel wiring

1. Add OTel sink wiring beside JSONL in app startup.
2. Keep it opt-in and simple.
3. Do not require OTel for local/dev use.

### Should: search/fetch consistency

If you land this:

1. keep the current search adapter interface stable
2. move search closer to the same identity/timeout/policy story as fetch
3. stay honest that search endpoints are not fetched pages with identical rules

If this turns into redesign pressure, stop and report it as deferred.

---

## Validation

Run, at minimum:

1. `python scripts/lint_imports.py`
2. targeted pytest for:
   - new forager endpoints
   - app startup / telemetry wiring
   - surfaced knowledge provenance
3. `cd frontend; npm run build`
4. full `python -m pytest -q` if your changes broaden across shared route/app seams

## Summary must include

- which operator-facing forager routes now exist
- how the operator can see forager provenance in the UI
- whether OTel wiring landed and how it is enabled
- whether search/fetch consistency landed or stayed deferred
- what you explicitly kept out to stay product-first
