Audit the live repo against the Wave 49 packet before implementation starts.

This is not a brainstorming exercise. It is a repo-truth check for the
planned seams, the replay-safe conversational-state design, the team split,
and the product-identity guard.

## Core Questions

1. Is the current Queen chat still mostly a message shell rather than a
   structured orchestration interface?
2. Does the current store/UI path still depend primarily on persisted
   `QueenMessage` text rather than structured conversational metadata?
3. Is additive `QueenMessage` metadata the cleanest replay-safe seam for cards,
   or is there already another persisted structured message path we should use?
4. Does the existing `follow_up_colony()` path make result cards practical
   without inventing a second completion-summary system?
5. Is the current Queen surface still dashboard-first in practice even though
   the app defaults to the Queen tab?
6. Does the Wave 49 plan preserve a Queen-thread-first conversation, or is it
   drifting toward event-feed-in-chat?
7. Does the packet now handle long Queen conversations gracefully, or does the
   current design still risk full-thread context blow-up?

## Read First

1. `docs/waves/wave_49/wave_49_plan.md`
2. `docs/waves/wave_49/acceptance_gates.md`
3. `docs/waves/wave_49/coder_prompt_team_1.md`
4. `docs/waves/wave_49/coder_prompt_team_2.md`
5. `docs/waves/wave_49/coder_prompt_team_3.md`
6. `AGENTS.md`
7. `CLAUDE.md`

Then verify the relevant code seams directly.

## Verify These Specific Claims

### Claim A: Queen chat is still a message shell

Check:

- `frontend/src/components/queen-chat.ts`
- `frontend/src/components/queen-overview.ts`

Confirm whether the live chat can already render anything beyond:

- text bubbles
- event rows
- directive panel

### Claim B: The UI/store path is centered on persisted `QueenMessage` text

Check:

- `src/formicos/core/events.py`
- `src/formicos/surface/projections.py`
- `frontend/src/state/store.ts`
- `frontend/src/types.ts`

Confirm whether the live chat state is rebuilt primarily from:

- `QueenMessage` events
- thread snapshots / projections

Call out any existing structured message metadata we may be overlooking.

### Claim C: `QueenResponse.actions` are not enough on their own

Check:

- `src/formicos/surface/queen_runtime.py`
- the path from `respond()` to emitted `QueenMessage` events

Confirm whether action metadata already reaches the frontend/store in a
replay-safe form, or whether it is currently runtime-local scaffolding only.

### Claim D: `follow_up_colony()` is a real result-card seam

Check:

- `src/formicos/surface/queen_runtime.py`
- `src/formicos/surface/colony_manager.py`

Confirm whether completed colonies already generate Queen-authored follow-up
messages in the thread and whether this looks like the right spine for
result-card rendering.

### Claim E: Queen surface is still dashboard-first in practice

Check:

- `frontend/src/components/formicos-app.ts`
- `frontend/src/components/queen-overview.ts`

Confirm whether the app lands in the Queen view but still presents the
dashboard as the primary visual weight, with chat acting more like a side rail.

### Claim F: Preview truth is now available as a shared substrate

Check:

- `src/formicos/surface/queen_tools.py`
- `src/formicos/surface/routes/api.py`
- `frontend/src/components/colony-creator.ts`

Confirm whether Wave 48 cleanup really closed the preview seam enough that Wave
49 can stand on shared preview truth rather than inventing a second plan-card
builder.

### Claim G: The packet avoids event-feed drift

Check the plan and prompts against the live repo and answer explicitly:

- does the packet keep chat Queen-thread-first?
- does it keep the thread timeline as the full chronology surface?
- is there any planned work that would accidentally duplicate the timeline
  inside chat?

### Claim H: Queen compaction is now a first-class requirement

Check:

- `src/formicos/surface/queen_runtime.py`
- `src/formicos/core/events.py`
- `src/formicos/surface/projections.py`
- `docs/waves/wave_49/wave_49_plan.md`
- `docs/waves/wave_49/coder_prompt_team_1.md`

Confirm whether the packet now correctly treats Queen thread compaction as:

- deterministic
- structure-first
- token-aware rather than crude message-count-only trimming
- pinned around unresolved asks / active preview decisions

Also confirm whether the current repo still lacks Queen-thread compaction at
wave start, making this a real Wave 49 seam rather than speculative scope.

## Team-Split Audit

Check whether the proposed ownership is still clean:

- Team 1: event/contract/projection/runtime message enrichment
- Team 2: chat rendering, store, layout, confirm flow
- Team 3: recipes/docs truth

Call out hidden overlap risk, especially in:

- `src/formicos/core/events.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/queen_runtime.py`
- `frontend/src/types.ts`
- `frontend/src/state/store.ts`

## Product-Identity Audit

Answer explicitly:

1. Does each Must item help arbitrary operators, not just benchmark demos?
2. Does the packet stay within "chat-first product surface" rather than "new
   intelligence layer"?
3. Does the packet avoid new dependencies and external memory systems?
4. Does the packet preserve replay-safe truth rather than introducing transient
   UI-only state?

## Output Format

Return:

1. Findings first, ordered by severity, with file references
2. Repo-truth confirmation of the main Wave 49 seams
3. Any corrections needed before coder dispatch
4. A product-identity / event-feed-drift check
5. A long-conversation / compaction check
6. A short verdict: dispatch-ready or not, and why

## Important Guardrails

- Do not evaluate Wave 49 by whether it "looks more like ChatGPT."
- Evaluate it by whether it makes FormicOS feel like talking to a real
  collaborator while staying replay-safe and truthful.
- If a planned item is too loose, recommend narrowing it rather than expanding
  scope.
