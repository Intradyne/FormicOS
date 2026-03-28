# Wave 71.5 - Team B: Action Review

**Theme:** Turn the backend action queue into a real operator inbox with
review, reasoning, and continuation control.

## Context

Read these first:

- `docs/waves/wave_71_5/wave_71_5_plan.md`
- `docs/waves/wave_71_0/design_note.md`
- `CLAUDE.md`

### Key seams to read before coding

- `proposal-card.ts` — existing blast-radius rendering pattern (score, level
  pill, recommendation pill, factors list). Follow this visual language for
  action items that carry blast-radius metadata.
- `approval-queue.ts` — existing live-pending widget. Small and
  overview-friendly. The new inbox is the richer replacement for the
  Operations tab; the approval queue stays as-is for the Queen overview.
- Wave 72 is expected to add new action kinds. Build this inbox so new kinds
  can slot in without changing the overall component shape.
- Void Protocol tokens in `../styles/shared.js` — use existing design system.

## Your Files (exclusive ownership)

- `frontend/src/components/operations-inbox.ts` - **new**
- `frontend/src/components/approval-queue.ts` only if a tiny compact refresh is
  useful for consistency

## Do Not Touch

- `frontend/src/components/operations-view.ts` - Team A owns
- Team C operational-memory components
- backend files unless a tiny payload shim is unavoidable

## Overlap Coordination

- Build a self-contained leaf component. Team A will mount it.
- If you touch `approval-queue.ts`, keep it compact and overview-friendly.
  The rich workflow belongs in `operations-inbox.ts`.

---

## Track 2: Operations Inbox

Create `fc-operations-inbox`.

It should fetch:

- `GET /api/v1/workspaces/{workspace_id}/operations/actions`

And render sections such as:

- Pending Review
- Recent Automatic Actions
- Deferred / Self-Rejected
- Continuation Suggestions

Do not hardcode the inbox around continuation-only semantics. The component
should fundamentally render by action `status` and `kind`, with
continuation-specific decoration as just one variant.

Each item should show:

- title
- rationale
- action kind
- source category
- blast radius
- estimated cost
- confidence
- thread / milestone context when present

---

## Approve / Reject Workflow

Use the new action endpoints:

- `POST .../approve`
- `POST .../reject`

Requirements:

- approving is one click
- rejecting captures an optional reason in the UI
- reason entry should be lightweight, not a heavy modal workflow
- do not recompute blast radius or autonomy in the browser
- do not use legacy `ApprovalType` labels as the operator-facing action meaning

If an item is already executed or rejected, render it as history, not as an
actionable card.

## Acceptance Gates

- [ ] `fc-operations-inbox` exists and is self-contained
- [ ] pending, recent, and deferred states render clearly
- [ ] rejection reason can be entered and submitted
- [ ] continuation items are visible in the same inbox, not hidden elsewhere
- [ ] no browser-side recomputation of queue semantics

## Validation

```bash
npm run build
npm run lint  # if lint config exists
```
