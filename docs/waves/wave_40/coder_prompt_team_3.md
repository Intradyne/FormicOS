## Role

You own the frontend consistency, docs truth, and dual-API track of Wave 40.

Your job is to:

- make the main UI surfaces more consistent
- finish and verify the post-Wave-39 docs truth pass
- make the native task API and A2A compatibility story clean and honest

This is the "what operators, contributors, and ecosystem clients actually see"
track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `README.md`
4. `docs/OPERATORS_GUIDE.md`
5. `docs/KNOWLEDGE_LIFECYCLE.md`
6. `docs/A2A-TASKS.md`
7. `docs/NEMOCLAW_INTEGRATION.md`
8. `docs/waves/wave_40/wave_40_plan.md`
9. `docs/waves/wave_40/acceptance_gates.md`
10. `docs/waves/session_decisions_2026_03_19.md`
11. `src/formicos/surface/routes/a2a.py`
12. `src/formicos/surface/routes/protocols.py`
13. `frontend/src/components/colony-detail.ts`
14. `frontend/src/components/knowledge-browser.ts`
15. `frontend/src/components/queen-overview.ts`
16. `frontend/src/components/workflow-view.ts`
17. `frontend/src/components/formicos-app.ts`
18. `frontend/src/components/demo-guide.ts`
19. `tests/browser/smoke.spec.ts`

## Coordination rules

- Wave 39.25 already refreshed parts of the docs layer.
  - Finish and verify that work.
  - Do not rewrite everything from scratch.
- The current `/a2a/tasks` implementation is already a colony-backed REST task
  lifecycle.
  - Build on that truth.
  - Do **not** create a second task store.
  - Do **not** create a second execution path.
- AG-UI stays honestly documented as the surface it currently is.
- No new product features in this track.
- Small decomposition sub-components are allowed only if they simplify an
  existing oversized frontend surface.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `frontend/src/components/colony-detail.ts` | OWN | consistency cleanup and optional decomposition |
| `frontend/src/components/knowledge-browser.ts` | OWN | consistency, overlay coherence, large-state sanity |
| `frontend/src/components/queen-overview.ts` | OWN | consistency cleanup |
| `frontend/src/components/workflow-view.ts` | OWN | demo and launch-surface truth |
| `frontend/src/components/formicos-app.ts` | OWN | shell-level consistency only if needed |
| `frontend/src/components/demo-guide.ts` | OWN | demo flow truth |
| `frontend/src/components/*` | CREATE | only small decomposition sub-components if justified |
| `tests/browser/smoke.spec.ts` | MODIFY | keep browser smoke truthful for post-Wave-39 state |
| `README.md` | OWN | capability and quick-start truth |
| `CLAUDE.md` | OWN | post-Wave-39 system truth |
| `AGENTS.md` | OWN | current tool / capability truth |
| `docs/OPERATORS_GUIDE.md` | OWN | operator-facing truth |
| `docs/KNOWLEDGE_LIFECYCLE.md` | OWN | current knowledge and overlay truth |
| `docs/A2A-TASKS.md` | OWN | native task API / compatibility truth |
| `docs/NEMOCLAW_INTEGRATION.md` | OWN | specialist-surface truth |
| `docs/decisions/INDEX.md` | OWN | ADR index honesty |
| `CONTRIBUTING.md` | OWN | current testing / workflow truth |
| `src/formicos/surface/routes/a2a.py` | OWN | native task API cleanup / shared handler extraction if needed |
| `src/formicos/surface/routes/protocols.py` | OWN | Agent Card conformance truth |
| `src/formicos/surface/routes/a2a_rpc.py` | CREATE | only if a thin JSON-RPC wrapper is the cleanest implementation |

## DO NOT TOUCH

- `src/formicos/core/*` - no event work in this track
- main backend refactors in `runner.py`, `colony_manager.py`,
  `proactive_intelligence.py`, `queen_tools.py`, `projections.py` - Team 1 owns
- broad testing-only infrastructure - Team 2 owns

## Overlap rules

- Team 1 may refactor backend helpers underneath you.
  - Build protocol and docs work over stable behavior, not private helper
    layout.
- Team 2 will test your surfaces.
  - Keep API behavior and docs honest so their tests can stay behavior-focused.

---

## 3A. Frontend consistency audit

Audit the main surfaces for:

1. shared confidence-color token usage
2. meaningful empty states
3. sane loading behavior
4. consistent stat styling and typography
5. action and badge consistency across knowledge and colony surfaces

### Hard constraints

- Do **not** redesign the UI.
- Do **not** add new product surfaces under the label of consistency.

---

## 3B. Large-component assessment

Assess whether:

- `colony-detail.ts`
- `knowledge-browser.ts`

want small extracted presentational sub-components.

If yes, do it. If no, say so clearly in your summary. Do not split files only
because they are large.

---

## 3C. Demo path re-validation

Run the Wave 36 demo path against the post-Wave-39 repo state and fix truth or
surface regressions you find.

Minimum scope:

1. workspace setup still works
2. briefing truth still appears
3. workflow / colony rendering still reads cleanly
4. Wave 39 surfaces do not break the guided flow

---

## 4A. Documentation truth pass

Wave 39.25 already started this work. Finish and verify it.

Priority truth areas:

1. event union is 58
2. overlays are local-first and replay-safe
3. validator and completion truth is current
4. escalation and override behavior is current
5. federation and admission hardening are current
6. native task API and A2A compatibility truth is current

### Hard constraints

- Do **not** claim ADRs exist if the files are not actually checked in.
- Do **not** describe future-wave work as landed behavior.

---

## 5. Dual API surface

Wave 40's protocol job is to make the current story cleaner, not to create a
parallel architecture.

### Required scope

1. Treat the current colony-backed task lifecycle as the native task API.
2. If you add a JSON-RPC compatibility wrapper, make it thin and translation-
   only over the same task truth.
3. Update the Agent Card so native and compatibility conformance are explicit.
4. Keep `docs/A2A-TASKS.md` and any related docs honest.

### Hard constraints

- No second task store
- No second execution path
- No hidden divergence between REST and wrapper truth
- AG-UI remains honestly described, not overclaimed

If the cleanest implementation is to extract shared task handlers from
`a2a.py` and have REST and JSON-RPC call the same helpers, that is in scope.

---

## Validation

Run, at minimum:

1. `cd frontend; npm run build`
2. browser smoke coverage if your changes touch the demo or top-level flows
3. targeted pytest for any protocol-route changes you make

Your summary must include:

- which docs were materially corrected
- whether you extracted any frontend sub-components and why
- whether the dual-API wrapper landed or whether only native-surface truth was
  tightened
- confirmation that no second task architecture was created
