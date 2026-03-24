## Role

You own the recommendation-and-supervision surfaces track of Wave 39.

Your job is to:

- turn outcome/configuration evidence into editable recommendation surfaces
- add earned-autonomy recommendation UX
- own the pre-spawn configuration editing surface

This is the "show what tends to work here, and let the operator edit it"
track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_39/wave_39_plan.md`
4. `docs/waves/wave_39/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `src/formicos/surface/proactive_intelligence.py`
7. `src/formicos/surface/queen_runtime.py`
8. `src/formicos/surface/projections.py`
9. `frontend/src/components/proactive-briefing.ts`
10. `frontend/src/components/queen-overview.ts`
11. `frontend/src/components/workflow-view.ts`

## Coordination rules

- Recommendations remain recommendations in Wave 39.
- Earned autonomy should recommend promotion/demotion, not silently apply it.
- Pre-spawn editing is the UI home for `ConfigSuggestionOverridden`, but Team 2
  owns the event contract.
- Keep configuration memory evidence-backed and operator-readable.
- Do **not** touch `core/`.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `src/formicos/surface/proactive_intelligence.py` | OWN | earned-autonomy and configuration-memory recommendations |
| `src/formicos/surface/queen_runtime.py` | OWN | recommendation surfacing in briefing |
| `src/formicos/surface/projections.py` | OWN | operator response-pattern aggregation and config-memory support |
| `frontend/src/components/proactive-briefing.ts` | OWN | earned-autonomy recommendation UI |
| `frontend/src/components/config-memory.ts` | CREATE | configuration-memory panel |
| `frontend/src/components/queen-overview.ts` | OWN | mount configuration-memory surfaces |
| `frontend/src/components/workflow-view.ts` | OWN | pre-spawn edit overlay |
| `tests/unit/surface/test_wave39_earned_autonomy.py` | CREATE | earned-autonomy recommendation coverage |
| `tests/unit/surface/test_wave39_config_memory.py` | CREATE | config-memory and pre-spawn editing coverage |

## DO NOT TOUCH

- `src/formicos/core/*` - Team 2 owns the Wave 39 event expansion
- `src/formicos/engine/*` - Team 1 owns
- `src/formicos/surface/knowledge_catalog.py` - Team 2 owns
- `src/formicos/surface/routes/knowledge_api.py` - Team 2 owns
- `frontend/src/components/knowledge-browser.ts` - Team 2 owns
- `frontend/src/components/colony-audit.ts` - Team 1 owns
- `frontend/src/components/colony-detail.ts` - Team 1 owns

## Overlap rules

- `src/formicos/surface/projections.py`
  - You own operator-response and configuration-memory support.
  - Team 1 owns audit-view and validator support.
  - Team 2 owns operator overlays and annotations.
  - Reread before merge.
- `frontend/src/components/queen-overview.ts`
  - You own configuration-memory surfaces.
  - Team 1 owns compact audit / completion-truth additions.
  - Keep changes additive and reread before merge.
- `frontend/src/components/workflow-view.ts`
  - You own the pre-spawn editing overlay.
  - Do not widen unrelated DAG visualization behavior.

---

## 4B. Earned autonomy recommendations

Use operator-behavior evidence to recommend autonomy changes by category.

### Required scope

1. Add recommendation rules by insight category.
2. Use thresholds strong enough to avoid premature trust.
3. Make trust harder to earn than to lose.
4. Surface accept / dismiss controls in the operator-facing UI.
5. Keep actual promotion/demotion on the existing config-change path.

### Hard constraints

- Do **not** auto-apply autonomy changes in Wave 39.
- Do **not** make the recommendation engine spammy.
- Recommendations must include evidence the operator can inspect.

### What success looks like

The system can say, "you accepted 17 of 20 contradiction suggestions; promote
this category?" and the operator can inspect and act on that advice.

---

## 5A. Configuration memory surfaces

Render "what tends to work here" as an evidence-backed panel.

### Required scope

1. Show recommendations for:
   - strategy
   - caste composition
   - round limits
   - tier recommendations where evidence exists
2. Include evidence from outcomes and the escalation matrix.
3. Keep the recommendations editable rather than hidden heuristics.

### Hard constraints

- Do **not** present weak guesses as strong recommendations.
- Do **not** hide the evidence behind the panel.
- Keep the wording honest about what the system actually knows.

### What success looks like

An operator can see what the system recommends, why, and how that changed over
time if history ships.

---

## 5B. Pre-spawn configuration editing

Own the UI surface for editing suggested configs before launch.

### Required scope

1. Add an edit overlay in `workflow-view.ts` or the nearest equivalent
   pre-spawn surface.
2. Let the operator adjust the recommended config before colonies spawn.
3. Route accepted edits through the `ConfigSuggestionOverridden` event path
   implemented by Team 2.
4. Keep the original and overridden config clearly visible.

### Hard constraints

- Do **not** invent a second hidden override store.
- Do **not** silently rewrite plans without showing the operator what changed.
- Coordinate with Team 2 on the exact event payload shape.

### What success looks like

An operator can inspect a recommendation, edit it before spawn, and know that
the edit was durably recorded.

---

## Acceptance targets for Team 3

1. Earned-autonomy recommendations exist and are evidence-backed.
2. Configuration recommendations are visible and editable.
3. Pre-spawn editing routes through the durable override path instead of a
   hidden UI-only state.
4. Recommendation surfaces remain advisory and honest.
5. No new event types were added by this track.

## Validation

```bash
python scripts/lint_imports.py
python -m pytest -q
cd frontend && npm run build
```

If your UI needs a backend seam for override durability, coordinate with Team 2
rather than creating a parallel path.

## Required report

- exact files changed
- what earned-autonomy recommendation logic was added
- what the configuration-memory panel now shows
- how pre-spawn editing works
- how accepted edits route through the durable override path
- confirmation that recommendations remain advisory
- confirmation that no new event types were added by this track
