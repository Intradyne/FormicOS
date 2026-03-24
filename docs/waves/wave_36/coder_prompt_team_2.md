# Wave 36 Team 2 - Guided Demo Path + Public Narrative

## Role

You own Track B of Wave 36: build the guided demo path, polish the
orchestration visualization for showpiece readability, and restructure the
public narrative so a GitHub visitor understands FormicOS in the first minute.

This is the "make it compelling in one session" track.

## Coordination rules

- `CLAUDE.md` defines evergreen repo rules. This prompt and
  `docs/waves/wave_36/wave_36_plan.md` are the authority for this dispatch.
- Read `docs/decisions/047-outcome-metrics-retention.md` for context only.
  Team 1 owns outcome surfacing.
- Track A lands first on `queen-overview.ts`. Reread before finalizing.
- Track C owns the full integration test, consistency audit, and final docs.
- The demo must use real execution, not simulation.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `config/templates/demo-workspace.yaml` | CREATE | Seeded demo workspace template |
| `frontend/src/components/demo-guide.ts` | CREATE | Persistent annotation bar |
| `frontend/src/components/workflow-view.ts` | OWN | Demo-friendly orchestration polish, animations, mini-DAG support |
| `frontend/src/components/queen-overview.ts` | MODIFY | "Try the Demo" button, mini-DAG in Active Plans only |
| `src/formicos/surface/routes/api.py` | MODIFY | Demo-workspace creation endpoint only |
| `README.md` | OWN | First-60-seconds restructure |
| `CHANGELOG.md` | CREATE | Narrative Wave 33-36 history |
| `docs/screenshots/*` | CREATE | Screenshot manifest / captions and any real captured assets available in this environment |

## DO NOT TOUCH

- `frontend/src/components/formicos-app.ts` - Team 1 owns A0 fix
- `frontend/src/components/colony-detail.ts` - Team 1 owns outcome section
- `frontend/src/components/proactive-briefing.ts`
- `frontend/src/components/queen-chat.ts`
- `frontend/src/components/settings-view.ts`
- `src/formicos/surface/proactive_intelligence.py` - Team 1 owns
- `src/formicos/surface/self_maintenance.py` - Team 1 owns
- `src/formicos/surface/queen_runtime.py` - Team 1 owns
- `tests/*` - Team 3 owns
- `docs/OPERATORS_GUIDE.md` - Team 3 owns
- `docs/KNOWLEDGE_LIFECYCLE.md` - Team 3 owns
- `AGENTS.md` - Team 3 owns
- `CLAUDE.md` - Team 3 owns
- `src/formicos/core/*`
- `src/formicos/engine/*` (includes `engine/runner.py` -- Team 1 owns A0c)

## Overlap rules

- `frontend/src/components/queen-overview.ts`
  - Team 1 owns layout, posture, knowledge pulse, and outcome data sections.
  - You own only:
    - the "Try the Demo" entry point
    - compact mini-DAG rendering inside Active Plans
- `src/formicos/surface/routes/api.py`
  - Team 1 owns the outcomes endpoint.
  - You own only the demo-workspace creation endpoint.

---

## B1. Guided demo workspace

Create `config/templates/demo-workspace.yaml` as a real seeded workspace:
- 8-10 seeded entries across two useful domains
- multiple confidence tiers
- multiple decay classes
- one deliberate contradiction
- maintenance policy configured for visible self-maintenance
- federation disabled

The seeded state should support the exact flow described in the plan:
- immediate proactive insight
- operator task kickoff
- visible plan execution
- knowledge extraction
- deterministic one-shot maintenance evaluation

Do not fake outputs. The demo must be real system execution on top of seeded
state.

### Backend route

Add a demo-workspace creation endpoint in `src/formicos/surface/routes/api.py`,
for example:
- `POST /api/v1/workspaces/create-demo`

It should create a real workspace from the template and return enough
information for the frontend to navigate there.

---

## B2. Demo guide component

Create `frontend/src/components/demo-guide.ts` as a compact, persistent
annotation bar that:
- appears below the proactive briefing during the demo
- explains what the operator should look at in the current step
- advances automatically from real AG-UI / app state changes
- can be dismissed at any time

This is not a modal tutorial and not a sidebar.

Keep it lightweight, visually intentional, and grounded in the real flow.
To keep the self-maintenance step demo-reliable, include a one-shot
maintenance evaluation trigger after the demo workspace is initially rendered
so the contradiction-resolution moment does not depend on waiting for the
periodic maintenance loop.

---

## B3. Workflow-view showpiece polish

Polish `workflow-view.ts` for public readability:
- group labels that read like meaningful execution phases
- animated node state transitions
- clearer dependency arrows
- running cost accumulator
- elapsed time per group / total where feasible
- compact mini-DAG variant for landing-page Active Plans

The most important result:
- a first-time user can see parallel work, understand dependencies, and feel
  that the Queen is orchestrating a real system, not just listing tasks

Do not rewrite the component from scratch if refinement will get you there.

---

## B4. Queen landing demo entry point

Add a "Try the Demo" entry point to `queen-overview.ts` after bootstrap.

Important:
- do not claim this exists in the startup shell
- the Wave 36 plan now explicitly scopes this to the Queen landing page after
  bootstrap

This entry point should:
- create the demo workspace
- navigate the operator into it
- start the guided demo flow cleanly

Keep this additive and visually obvious without overwhelming the page.

---

## B5. Public narrative assets

### README

Restructure `README.md` for the first-60-seconds experience:
1. one-paragraph elevator pitch
2. demo-first lead
3. four "what makes it different" bullets
4. preserve the strong technical sections already updated in Wave 35.5

This is a restructure, not a full rewrite.

### CHANGELOG

Create a narrative `CHANGELOG.md` covering the Wave 33-36 arc.
This is not a commit dump. It should tell the product story.

### Screenshots

Create `docs/screenshots/` support material.

If you can capture real assets in this environment, do so.
If you cannot, create:
- the directory
- a shot list / captions manifest
- explicit placeholders

Do not invent fake binaries or mocked screenshots.

---

## Acceptance targets for Track B

1. A real demo workspace can be created from the API.
2. The Queen landing page has a clear "Try the Demo" path after bootstrap.
3. The demo guide explains the flow without taking over the app.
4. Workflow DAGs feel demo-ready, not merely functional.
5. README tells the story fast and truthfully.

## Validation

```bash
python scripts/lint_imports.py
python -m pytest -q
cd frontend && npm run build
```

## Required report

- exact files changed
- demo-workspace template contents at a high level
- final demo creation endpoint path
- how demo-guide advances through real state changes
- what changed in `workflow-view.ts`
- whether screenshots were captured or a manifest was created instead
