# Wave 70.5 - Team B: Project Visibility

**Theme:** Make the project plan visible at the workspace level without asking
the operator to open a file or a thread.

## Context

Read `docs/waves/wave_70_5/wave_70_5_plan.md` first. Assume `70.0` landed
`GET /api/v1/project-plan`.

You are building a pure rendering slice. Do not parse markdown in the browser.

### Key seams to read before coding

- `queen-overview.ts` — already has plan card infrastructure:
  `_renderActivePlans()` (lines 511–570) renders per-thread plans with
  group progress bars. Your project-plan card is workspace-scoped (not
  thread-scoped) and should mount separately, near the budget panel
  (around lines 210–220). Existing card mount pattern: `.glass` cards in
  grid containers.
- `styles/shared.ts` — `.glass` class (line 82), Void Protocol tokens.

## Your Files (exclusive ownership)

- `frontend/src/components/project-plan-card.ts` — **new**
- `frontend/src/components/queen-overview.ts` — mount point only

## Do Not Touch

- `frontend/src/components/settings-view.ts` — Team C owns
- `frontend/src/components/proposal-card.ts` — Team C owns
- backend files

## Goal

Add a compact Project Plan card to the Queen overview. This is distinct from
the existing per-thread plan rendering in `_renderActivePlans()`.

## Requirements

### Data source

Fetch:

```text
GET /api/v1/project-plan
```

Use the response as-is. No frontend parsing, no inferred state.

### UI

Create `fc-project-plan-card` and render:

- plan goal
- updated timestamp
- milestone checklist
- status chips (`pending`, `active`, `completed`)
- thread links when present
- completion dates / notes when present

Mount it in `queen-overview.ts`.

### Visibility rules

- hide the card entirely when no project plan exists
- keep the card compact and dashboard-like, not full-document rendering

### Empty/error states

- no project plan
- endpoint unavailable

## Acceptance Gates

- [ ] `fc-project-plan-card` exists
- [ ] `queen-overview.ts` mounts it
- [ ] data comes only from `GET /api/v1/project-plan`
- [ ] no frontend markdown parsing
- [ ] milestone status/thread/date truth is preserved

## Validation

```bash
npm run build
npm run lint  # if lint config exists
```
