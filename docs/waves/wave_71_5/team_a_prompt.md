# Wave 71.5 - Team A: Operations Shell

**Theme:** Give the operational loop a first-class home in the product
surface.

## Context

Read these first:

- `docs/waves/wave_71_5/wave_71_5_plan.md`
- `docs/waves/wave_71_0/design_note.md`
- `CLAUDE.md`

### Key seams to read before coding

- `formicos-app.ts` — `ViewId` type union at line 27. `NAV` array at lines
  29–37 (7 entries). Nav grid at line 62: `repeat(7, minmax(72px, auto))` —
  must become `repeat(8, ...)`. Responsive breakpoint at line 239:
  `repeat(5, ...)` — verify 8 tabs fit or adjust. `navTab()` at line 322.
  View routing switch in the render method.
- Void Protocol tokens and `sharedStyles` in `../styles/shared.js` — follow
  existing card/layout patterns from `settings-view.ts`.

Assume `71.0` landed:

- `GET /api/v1/workspaces/{workspace_id}/operations/summary`
- `GET /api/v1/workspaces/{workspace_id}/operations/actions`
- `GET /api/v1/workspaces/{workspace_id}/queen-journal`
- `GET /api/v1/workspaces/{workspace_id}/operating-procedures`
- `PUT /api/v1/workspaces/{workspace_id}/operating-procedures`

## Your Files (exclusive ownership)

- `frontend/src/components/operations-view.ts` - **new**
- `frontend/src/components/formicos-app.ts`
- `frontend/src/components/system-overview.ts` only if a tiny badge/summary
  tweak is needed

## Do Not Touch

- `frontend/src/components/operations-inbox.ts` - Team B owns
- `frontend/src/components/queen-journal-panel.ts` - Team C owns
- `frontend/src/components/operating-procedures-editor.ts` - Team C owns
- `frontend/src/components/operations-summary-card.ts` - Team C owns
- backend files unless a tiny presentational payload shim is unavoidable

## Overlap Coordination

- You are the only owner of `operations-view.ts`.
- Team B and Team C deliver leaf components; mount them, do not rewrite them.

---

## Track 1: Operations Tab + Nav Integration

Add a new top-level `Operations` tab to the app shell.

Requirements:

- add the tab in `formicos-app.ts`
- mount `fc-operations-view`
- keep the current nav legible; do not create a second side rail
- if useful, surface a pending-review badge on the Operations tab using the
  summary endpoint

This is the right moment to add a new surface. Do not bury the operational
loop inside Settings.

---

## Track 2: Operations View Shell

Create `fc-operations-view` as the integrator for Wave 71.5.

Suggested layout:

- top summary/header row
- left column: Team B action inbox
- right column: Team C summary card, journal panel, procedures editor

Requirements:

- fetch and pass the active workspace ID cleanly
- use the existing design system and current visual language
- give the page strong empty states:
  - no pending actions
  - no journal yet
  - no procedures written yet

Do not parse backend markdown or derive your own operational summary in the
browser. Use the `71.0` seams.

## Acceptance Gates

- [ ] `Operations` appears as a top-level nav item
- [ ] `fc-operations-view` exists and is the only shell owner
- [ ] Team B and Team C components mount cleanly inside it
- [ ] a pending-review badge is shown if clean and cheap
- [ ] no duplicate queue UI scattered across multiple tabs

## Validation

```bash
npm run build
npm run lint  # if lint config exists
```
