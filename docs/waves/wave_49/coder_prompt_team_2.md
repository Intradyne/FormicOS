You own the Wave 49 frontend conversational-surface track.

This is the chat-components and layout track. You are not redesigning the
Queen's intelligence, and you are not inventing new preview/result data on the
frontend. Your job is to make the Queen chat feel like talking to a
collaborator using the replay-safe metadata Team 1 lands.

## Mission

Land the frontend-heavy parts of Wave 49:

1. render preview cards inline in Queen chat
2. render result cards inline in Queen chat
3. distinguish ask vs notify visually
4. make chat the primary Queen surface
5. preserve drill-down access to the richer Wave 48 surfaces

The core rule still applies:

**If the benchmark disappeared tomorrow, would we still want this change in
FormicOS?**

Yes. Operators want to stay in the conversation for the 80% case.

## Read First

1. `AGENTS.md`
2. `CLAUDE.md`
3. `docs/waves/wave_49/wave_49_plan.md`
4. `docs/waves/wave_49/acceptance_gates.md`
5. `frontend/src/components/queen-chat.ts`
6. `frontend/src/components/queen-overview.ts`
7. `frontend/src/components/formicos-app.ts`
8. `frontend/src/components/colony-creator.ts`
9. `frontend/src/state/store.ts`
10. `frontend/src/types.ts`

Before editing, reread Team 1's final `QueenMessage` metadata shape. The
frontend must follow repo truth, not the original wave sketch.

## Owned Files

- `frontend/src/components/queen-chat.ts`
- `frontend/src/components/fc-preview-card.ts`
- `frontend/src/components/fc-result-card.ts`
- `frontend/src/components/queen-overview.ts`
- `frontend/src/components/formicos-app.ts`
- `frontend/src/state/store.ts`
- `frontend/src/components/colony-creator.ts` only if bounded drill-down
  prefill support is needed
- targeted frontend/store tests for card rendering and confirm flow

## Do Not Touch

- backend Python files
- `src/formicos/core/events.py`
- `src/formicos/surface/queen_runtime.py`
- `config/caste_recipes.yaml`
- docs files
- unrelated Wave 48 timeline/audit code unless a tiny deep-link hook is
  necessary

Team 1 owns message metadata. Team 3 owns recipes/docs truth.

## Required Work

### Track A: Preview Card Rendering

Create a bounded preview card component rendered from replay-safe Queen thread
message metadata.

Requirements:

- render task, team shape, strategy, fast-path mode, target files, estimated
  cost when available
- support Confirm and Cancel
- use the stored preview params for Confirm
- do not parse LLM prose to rebuild the card

If the metadata is absent, fall back to text rendering gracefully.

### Track B: Result Card Rendering

Create a result card component rendered from structured Queen follow-up
messages.

Requirements:

- show status, task/name, rounds, cost, and extracted-knowledge summary when
  available
- provide deep-link actions to existing drill-down surfaces:
  - colony detail / audit
  - thread timeline
  - other bounded destinations only if already real

Hard rule:

- do not make the card depend on a separate ad hoc frontend fetch if the
  needed identifiers are already available

### Track C: Ask / Notify Rendering

Use Team 1's structured metadata when present.

Render:

- `notify` messages as compact, low-interruption rows or muted bubbles
- `ask` messages as clearly highlighted prompts
- `preview_card` and `result_card` via the new components

Fallback heuristics are acceptable only when structured metadata is absent.

### Track D: Chat-First Layout

Flip the Queen overview default so chat is the primary visible surface.

Requirements:

- `chatExpanded` (or equivalent) defaults to chat-first
- full dashboard remains available on demand
- a compact always-visible header preserves critical operational context

Do not delete the dashboard. Reprioritize it.

### Track E: Confirm Flow And Drill-Down

The normal operator path should be:

1. type task
2. see preview card
3. click Confirm
4. watch conversational progress
5. click result-card links only when needed

Bounded extras allowed:

- a minimal inline adjust affordance if it stays small and truthful
- an "Open full editor" path if you need a clean escape hatch

Do not turn Wave 49 into a second full colony-creator implementation inside
chat.

### Track F: Keep Chat Queen-Thread-First

This is critical.

Do not turn Queen chat into:

- a raw colony event feed
- a second thread timeline
- a noisy log view

If you surface progress/status rows, keep them selective and bounded. The
conversational spine should remain Queen-authored messages and cards.

## Hard Constraints

- Do not fabricate preview/result data
- Do not parse free text when structured metadata exists
- Do not duplicate the full dashboard inside chat
- Do not duplicate the full timeline inside chat
- Do not rebuild colony-creator inside chat

## Validation

Run at minimum:

1. the repo's frontend build / type-check path
2. targeted tests for:
   - preview card rendering
   - result card rendering
   - confirm flow
   - ask/notify rendering fallback behavior where relevant

If store behavior changes materially, include the relevant broader frontend
slice.

## Summary Must Include

- where preview/result cards render in the Queen surface
- how confirm dispatch works
- how chat-first layout changed
- what deep links landed
- whether inline adjust shipped or was deferred
- how you prevented chat from becoming an event feed
