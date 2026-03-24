## Role

You own the Wave 48 frontend flow and integration track.

This is the connected-operator-flow track. You are not building a new product
from scratch. You are connecting and upgrading surfaces that already exist.

## Mission

Land the frontend-heavy parts of Wave 48:

1. a thread-first timeline component and integration
2. Review-step preview/confirmation using the real backend preview path
3. cross-links between timeline, colony audit, colony detail, and knowledge
4. bounded running-state clarity if it can stay truthful

The core rule still applies:

**If the benchmark disappeared tomorrow, would we still want this change in
FormicOS?**

Yes. Operators need a coherent task story and real launch truth.

## Read First

1. `AGENTS.md`
2. `CLAUDE.md`
3. `docs/waves/wave_48/wave_48_plan.md`
4. `docs/waves/wave_48/acceptance_gates.md`
5. `frontend/src/components/thread-view.ts`
6. `frontend/src/components/colony-creator.ts`
7. `frontend/src/components/colony-detail.ts`
8. `frontend/src/components/colony-audit.ts`
9. `frontend/src/components/knowledge-browser.ts`
10. `frontend/src/components/queen-chat.ts`
11. `frontend/src/components/colony-chat.ts`
12. `frontend/src/components/formicos-app.ts`
13. `frontend/src/state/store.ts`

Before editing, reread the final Team 1 backend payload shape so the frontend
matches repo truth rather than wave intent.

## Owned Files

- `frontend/src/components/thread-timeline.ts`
- `frontend/src/components/thread-view.ts`
- `frontend/src/components/colony-creator.ts`
- `frontend/src/components/colony-audit.ts`
- `frontend/src/components/colony-detail.ts`
- `frontend/src/components/knowledge-browser.ts` only if filter/navigation
  plumbing is needed
- `frontend/src/components/formicos-app.ts` only if a small route/tab hook is
  necessary
- `frontend/src/state/store.ts`
- targeted frontend/store tests for the new flow

## Do Not Touch

- backend Python files
- `config/caste_recipes.yaml`
- docs files
- directive-panel UX beyond small integration polish

The directive panel already exists. Do not rebuild it.

## Required Work

### Track A: Thread Timeline Component

Create a new thread-scoped timeline component in the existing frontend style.

Requirements:

- chronological rows
- type badges
- expandable details
- lightweight filtering if it stays bounded
- reuse visual idioms from existing thread/chat/timeline surfaces

Keep v1 simple. This is an audit surface, not a dashboard contest.

### Track B: Integrate The Timeline Into Thread Flow

The timeline is thread-first.

Preferred integration:

- visible from `thread-view.ts`
- close to the operator's task context
- updated from store/API truth without inventing a second navigation universe

Do not make workspace-level audit the primary first surface.

### Track C: Upgrade The Existing Review Step

`frontend/src/components/colony-creator.ts` already has a Review/Launch step.
It currently uses a local rough estimate.

Replace that with the real preview path:

- call backend preview support from the Review step
- support both `spawn_colony` and `spawn_parallel`
- show actual launch truth before dispatch
- keep "Back" and "Launch" behavior clean

Do not introduce a separate confirmation subsystem first unless the existing
Review step proves impossible to adapt.

### Track D: Cross-Surface Connections

The timeline must connect to the rest of the operator story:

- timeline -> colony detail
- timeline -> knowledge browser
- colony audit -> knowledge browser
- colony audit -> source URL where truthful

This is a must. A disconnected log is not the Wave 48 goal.

### Track E: Running-State Clarity

This is lower priority than Tracks A-D.

If it can stay truthful and bounded, add a compact "Latest Activity" or
equivalent running-state block using existing truth:

- recent system event rows
- existing replay-safe previews
- recent round/action metadata already available in store state

Use the following framing when it helps:

- **notify:** non-blocking progress/status signals surfaced during execution
- **ask:** moments that need explicit operator input or redirection

Wave 48 should improve notify-style visibility. Do not turn normal progress
into blocking asks; the directive flow already exists for intervention.

Hard rules:

- do not fabricate detailed activity from weak signals
- do not jump to raw partial-file streaming in this wave

If it gets loose, defer it honestly.

## Hard Constraints

- Do not rebuild colony audit, directive panel, or Forager Activity from
  scratch
- Do not invent a workspace-first timeline as the primary operator surface
- Do not fabricate preview or progress data
- Do not expand into a broad visual redesign

## Validation

Run at minimum:

1. the repo's frontend build / type-check path
2. targeted frontend/store tests for timeline rendering and navigation
3. targeted tests for Review-step preview/launch behavior
4. any broader frontend slice needed if shared routing/store behavior changes

## Summary Must Include

- where the thread timeline is exposed in the UI
- how the Review step now uses real preview truth
- what cross-surface links landed
- whether running-state clarity shipped or was deferred
- what you kept out to stay bounded
