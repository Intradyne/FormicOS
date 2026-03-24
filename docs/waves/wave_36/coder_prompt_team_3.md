# Wave 36 Team 3 - Cohesion + Final Hardening

## Role

You own Track C of Wave 36: consistency audit, demo-path hardening, final
documentation pass, and release-quality verification support.

This is the "make the public version feel finished" track.

## Coordination rules

- `CLAUDE.md` defines evergreen repo rules. This prompt and
  `docs/waves/wave_36/wave_36_plan.md` are the authority for this dispatch.
- Track C runs after Teams 1 and 2. Reread their landed work before finalizing.
- Do not invent new backend architecture, events, or hidden tuning logic.
- Prefer tightening and verifying what exists over adding extra features.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `frontend/src/components/*.ts` | MODIFY | Consistency audit on touched/public surfaces only |
| `frontend/src/styles/shared.ts` | MODIFY | Canonical tokens if needed for confidence colors / empty states / typography |
| `tests/integration/test_demo_flow.py` | CREATE | End-to-end demo path integration test |
| `tests/integration/test_performance.py` | CREATE | Performance / responsiveness benchmarks |
| `CLAUDE.md` | MODIFY | Final post-36 state |
| `docs/OPERATORS_GUIDE.md` | MODIFY | Complete operator manual including demo path |
| `docs/KNOWLEDGE_LIFECYCLE.md` | MODIFY | Add outcome feedback loop and scheduled refresh |
| `AGENTS.md` | MODIFY | Final operator/agent interaction truth |
| `docs/decisions/INDEX.md` | CREATE | ADR index with one-line summaries |

## DO NOT TOUCH

- `src/formicos/core/*`
- `src/formicos/engine/*` (includes `engine/runner.py` -- Team 1 owns A0c)
- `src/formicos/surface/proactive_intelligence.py` - Team 1 owns
- `src/formicos/surface/self_maintenance.py` - Team 1 owns
- `src/formicos/surface/queen_runtime.py` - Team 1 owns
- `src/formicos/surface/routes/api.py` - Teams 1 and 2 own
- `config/templates/demo-workspace.yaml` - Team 2 owns
- `README.md` - Team 2 owns
- `CHANGELOG.md` - Team 2 owns

## Overlap rules

- You may touch frontend components only for consistency, empty-state, loading,
  and typography polish after A and B land.
- Do not re-architect Team 1 or Team 2 surfaces.
- If a consistency issue requires a token or shared-style change, prefer
  `frontend/src/styles/shared.ts` over copy-paste CSS.

---

## C1. Consistency audit

Audit the public-facing surfaces touched by Waves 35.5 and 36:
- `queen-overview.ts`
- `workflow-view.ts`
- `colony-detail.ts`
- `knowledge-browser.ts`
- `proactive-briefing.ts`
- `directive-panel.ts`
- `federation-dashboard.ts`
- `demo-guide.ts`
- other directly affected surfaces only

Targets:
- confidence colors are canonical and consistent
- empty states are meaningful
- loading states do not blank-flash
- stats use consistent mono treatment
- labels / badges feel like one design system

This is a consistency pass, not a visual redesign.

---

## C2. Demo-path integration test

Create the most important integration test in the repo:
- create demo workspace
- seeded contradiction visible in briefing
- task kickoff / colony execution path works
- knowledge extraction occurs
- deterministic maintenance evaluation runs
- contradiction / maintenance flow completes sufficiently to prove the path

Keep it grounded in actual system seams.
Do not fake internal state that bypasses the demo path's real logic unless a
test-speed shortcut is already idiomatic in the repo.

---

## C3. Performance checks

Create performance-oriented tests or benchmarks for the key public path:
- command-center render / response expectations
- proactive briefing generation timing
- demo-workspace creation timing
- full demo path upper-bound timing where realistic

Keep these stable and repo-appropriate.
Avoid flaky wall-clock assertions that will fail on normal dev machines.
Use bounded, practical thresholds and test helpers where possible.

---

## C4. Final docs pass

Bring the operator and contributor docs fully in line with post-Wave-36 truth:

### `CLAUDE.md`
- post-36 capability set
- outcome intelligence
- scheduled refresh
- demo workspace
- key file paths current

### `docs/OPERATORS_GUIDE.md`
- first-run demo walkthrough
- landing page explanation
- directive usage
- maintenance posture
- federation setup
- troubleshooting

### `docs/KNOWLEDGE_LIFECYCLE.md`
- colony outcome feedback loop
- scheduled refresh triggers
- distillation refresh

### `AGENTS.md`
- final tool / interaction truth
- directive handling
- knowledge-feedback and maintenance reality

### `docs/decisions/INDEX.md`
- create a clean ADR index for 001-047
- one-line summary + status per ADR

Keep the docs clear for a new reader. This is a release-readiness pass, not an
essay contest.

---

## Acceptance targets for Track C

1. Demo path has a real integration test.
2. Public surfaces feel visually consistent enough for release.
3. Empty and loading states no longer undermine the public demo.
4. Core docs tell the post-36 story accurately and clearly.
5. No new architecture or event types were introduced during the hardening pass.

## Validation

```bash
python scripts/lint_imports.py
python -m pytest -q
cd frontend && npm run build
```

If your changes affect Python linting in owned files, also run:

```bash
uv run ruff check src/
```

## Required report

- exact files changed
- what surfaces were audited for consistency
- what the demo integration test covers
- what performance checks were added
- which docs were updated
- confirmation that no new events or backend subsystems were introduced
