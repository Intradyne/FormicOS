# Wave 71.5 - Team C: Operational Memory Surfaces

**Theme:** Make the Queen's working memory and standing procedures visible and
editable without making the operator open raw files unless they want to.

## Context

Read these first:

- `docs/waves/wave_71_5/wave_71_5_plan.md`
- `docs/waves/wave_71_0/design_note.md`
- `CLAUDE.md`

### Key seams to read before coding

- `settings-view.ts` — existing card pattern (`.settings-card` class, read-only
  labels, inline editing). Follow this for the procedures editor save UX.
- `autonomy-card.ts` — existing self-contained component pattern with fetch +
  render + empty state. Follow this for all three components.
- Void Protocol tokens in `../styles/shared.js` — use existing design system.

Assume `71.0` landed:

- `GET /api/v1/workspaces/{workspace_id}/queen-journal`
- `GET /api/v1/workspaces/{workspace_id}/operating-procedures`
- `PUT /api/v1/workspaces/{workspace_id}/operating-procedures`
- `GET /api/v1/workspaces/{workspace_id}/operations/summary`

## Your Files (exclusive ownership)

- `frontend/src/components/queen-journal-panel.ts` - **new**
- `frontend/src/components/operating-procedures-editor.ts` - **new**
- `frontend/src/components/operations-summary-card.ts` - **new**

## Do Not Touch

- `frontend/src/components/operations-view.ts` - Team A owns
- `frontend/src/components/operations-inbox.ts` - Team B owns
- backend files unless a tiny payload shim is unavoidable

## Overlap Coordination

- Build self-contained leaf components that Team A can mount directly.
- Keep the operational summary card concise; the inbox already handles action
  detail.

---

## Track 3A: Journal Panel

Create `fc-queen-journal-panel`.

Requirements:

- fetch the Queen journal from the `71.0` endpoint
- default to recent entries, with a simple "load more" or refresh affordance
- present entries as an operational log, not as chat bubbles
- include good empty-state copy when no journal exists yet

This panel is for "what happened while I was away?"

---

## Track 3B: Operating Procedures Editor

Create `fc-operating-procedures-editor`.

Requirements:

- fetch current procedures
- allow direct text editing
- save via `PUT /api/v1/workspaces/{workspace_id}/operating-procedures`
- show subtle save state and failure state
- include a helpful empty template for first-time users

This editor is the standing-policy surface for autonomy. Treat it as important.

---

## Track 3C: Operations Summary Card

Create `fc-operations-summary-card`.

Use the operations summary endpoint to show compact, high-signal state:

- pending review count
- active milestone count
- operator idle / active state
- top continuation candidate
- top sync issue, if any
- recent progress snippet

If the endpoint exposes counts by action kind, show them compactly. This helps
Wave 72 add knowledge-review and procedure-suggestion actions without
redesigning the summary card.

Do not duplicate the full inbox or the full journal here. This is the
at-a-glance orientation card.

## Acceptance Gates

- [ ] journal panel exists and reads from the journal endpoint
- [ ] procedures editor exists and writes through the procedures endpoint
- [ ] summary card exists and reads from the operations summary endpoint
- [ ] all three components have strong empty states
- [ ] no raw markdown parsing in the browser

## Validation

```bash
npm run build
npm run lint  # if lint config exists
```
