## Wave 49 — The Conversational Colony

**Theme:** Make the Queen chat the primary orchestration surface.

The backend already understands natural-language tasks. The frontend already
has a Queen surface and a working chat. The gap is that the current Queen chat
is still a message shell, not a true orchestration interface.

Wave 49 turns the Queen chat into the front door without adding a new runtime,
new dependencies, or a second intelligence stack.

**Identity test:** Would a real operator want this if the benchmark
disappeared tomorrow?

Yes. Real operators want to state a task conversationally, see the proposed
plan inline, confirm with one click, monitor meaningful progress, and drill
into audit details only when they need them.

**Prerequisite:** Wave 48 accepted. The thread timeline exists, colony audit
has Forager attribution, the preview substrate is real on both spawn paths, the
frontend preview API seam exists, and the Reviewer / Researcher are grounded.
Wave start validation: Team 1's Wave 48 cleanup landed the shared preview
builder and `POST /api/v1/preview-colony`; reported validation was `3294`
passing tests with the same 3 pre-existing Team 3 recipe failures outside this
wave's scope.

## Contract

- No new event types. The event union remains at 62.
- Additive fields on existing `QueenMessage` are allowed if they are optional
  and replay-safe.
- No new backend intelligence. The Queen already understands tasks, tool
  calls, and intent fallback.
- No new backend subsystems.
- No new external dependencies.
- No NeuroStack or external knowledge vault.
- No new sandboxing layer.
- The dashboard remains available; chat simply becomes the primary landing
  surface.

## Why This Wave

The current repo already has:

- natural-language Queen orchestration in `src/formicos/surface/queen_runtime.py`
- preview on both spawn paths in `src/formicos/surface/queen_tools.py`
- a preview API for the frontend creator flow
- the app defaulting to the Queen surface in
  `frontend/src/components/formicos-app.ts`
- a working Queen chat component in
  `frontend/src/components/queen-chat.ts`
- thread timeline, colony audit, and connected audit links from Wave 48

What is still missing:

- preview data in Queen chat still renders as plain text instead of a card
- result summaries still feel like messages or event rows rather than
  actionable conversational outcomes
- the Queen chat does not distinguish "notify" from "ask"
- the chat layout is still secondary to the dashboard in practice
- the current store/UI path only really understands persisted `QueenMessage`
  text, not replay-safe structured message metadata
- the Queen still rebuilds context from the full thread history with no
  deterministic conversation compaction, which becomes a real pressure point
  once chat is the primary surface

The key architectural correction for Wave 49 is:

**structured conversational cards must ride on persisted Queen thread
messages, not only on transient runtime return values**

That keeps the conversational surface aligned with FormicOS's core strengths:
replay, snapshot rebuilds, reconnect correctness, and a single truth path.

## Repo Truth At Wave Start

Grounded against the live post-Wave-48 tree:

- `src/formicos/surface/queen_runtime.py` already executes Queen tool calls,
  captures tool-returned `actions`, and emits `QueenMessage` replies.
- `src/formicos/core/events.py` still defines `QueenMessage` as text-only:
  `thread_id`, `role`, `content`.
- `src/formicos/surface/projections.py` rebuilds thread chat history from
  `QueenMessage` events into `QueenMessageProjection`.
- `frontend/src/state/store.ts` rebuilds Queen chat from snapshots and
  incremental `QueenMessage` events; it currently only strips the parsed-intent
  marker and appends text.
- `frontend/src/components/queen-chat.ts` currently renders:
  - plain text bubbles
  - compact event rows
  - the directive panel
- `src/formicos/surface/queen_runtime.py` already has a
  `follow_up_colony()` path that summarizes completed colonies back into the
  thread. This is the natural spine for result-card-style follow-ups.
- `frontend/src/components/queen-overview.ts` already has a `chatExpanded`
  layout toggle. The dashboard is rich, but chat is still structurally a side
  rail rather than the primary orchestration mode.

## Governing Principles

Three design rules govern the whole wave:

1. **Replay-safe conversational state**
   - Preview cards, result cards, and ask/notify cues should reconstruct from
     persisted thread history and projections.

2. **Queen-thread-first, not event-feed-first**
   - The Queen chat should feel like a collaborator.
   - Raw colony and Forager events remain supporting context, not the main
     conversational spine.
   - The Queen should summarize what matters rather than dumping the full
     event stream into the thread.

3. **Deterministic structure-first compaction**
   - Long Queen conversations should degrade gracefully rather than hitting a
     hard context wall.
   - Compaction should prefer structured thread truth first and prose second.
   - The first version should be deterministic and token-aware, not an LLM
     summarizer.

## Pillar 1: Replay-Safe Structured Queen Messages

**Class:** Must

Wave 49 should enrich the existing `QueenMessage` path rather than invent a
parallel transient response channel.

### 1A. Add structured metadata to `QueenMessage`

Add optional fields to `QueenMessage` and its projections / frontend mirrors:

- `intent?: 'notify' | 'ask' | null`
- `render?: 'text' | 'preview_card' | 'result_card' | null`
- `meta?: dict | None`

This keeps semantics, rendering, and payload shape separate.

The message text remains the human-readable content. The metadata gives the UI
enough truth to render structured cards and ask/notify state without scraping
LLM prose.

### 1B. Preview metadata rides on persisted thread messages

When the Queen proposes a plan through preview mode:

- preserve the preview payload on the emitted Queen thread message
- include the structured fields needed for rendering and later confirm/cancel
- support both:
  - single-colony preview
  - parallel-plan preview

Do not rely on transient `QueenResponse.actions` alone. Those actions are
useful runtime scaffolding, but replay-safe card rendering must come from the
persisted thread message path.

### 1C. Result metadata rides on Queen follow-up messages

Reuse the existing `follow_up_colony()` pattern for completions.

When the Queen summarizes a completed colony, include enough structured
metadata for a result card:

- colony ID
- task / display name
- completion status
- cost / rounds
- quality score where available
- extracted-knowledge count
- validator state where available

Deep-link targets should be carried as stable identifiers, not pre-rendered
URLs.

### 1D. Ask/notify classification stays explicit

Classify Queen-authored messages using explicit backend intent where possible:

- preview proposals -> `notify` + `preview_card`
- completion summaries -> `notify` + `result_card`
- genuine requests for operator input -> `ask`

Frontend heuristics may exist as fallback, but backend intent should be the
primary source of truth.

### Seams

- `src/formicos/core/events.py`
- `docs/contracts/events.py`
- `docs/contracts/types.ts`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/queen_runtime.py`
- `frontend/src/types.ts`

## Pillar 2: Structured Chat Rendering

**Class:** Must

### 2A. Preview card component

Build a preview card that renders inline in Queen chat using persisted message
metadata.

Must support:

- task summary
- team shape
- strategy
- fast-path state
- target files where present
- estimated cost
- Confirm / Cancel actions

Should support:

- bounded inline adjust controls
- an "Open full editor" drill-down for complex changes

### 2B. Result card component

Build a result card that renders inline for structured Queen completion
follow-ups.

Must support:

- status
- task / colony name
- rounds
- cost
- extracted knowledge count
- deep links to:
  - audit
  - timeline
  - colony detail / diff-oriented view where applicable

### 2C. Notify/ask styling

Render Queen chat messages according to intent:

- `notify`: compact, low-interruption, easy to ignore
- `ask`: visually highlighted, input-focused, clearly waiting on operator
- `text`: normal conversational message
- `preview_card` / `result_card`: card rendering using `meta`

Hard rule: do not overload one field to mean both "what this message is doing"
and "how to display it."

### Seams

- `frontend/src/components/queen-chat.ts`
- `frontend/src/components/fc-preview-card.ts` (new)
- `frontend/src/components/fc-result-card.ts` (new)
- `frontend/src/types.ts`
- `frontend/src/state/store.ts`

## Pillar 3: Chat-First Layout And Dispatch Flow

**Class:** Must

### 3A. Chat becomes the default primary surface

Flip the Queen overview default so chat is the main experience and the full
dashboard is revealed on demand.

This should be a layout and hierarchy change, not a dashboard deletion.

### 3B. Keep critical operational context visible

When the dashboard is hidden, keep a compact status header above the chat with
the highest-signal operator information:

- running colony count
- session cost
- active plans count
- optionally one or two critical posture signals

### 3C. Confirm preview directly from stored preview params

When an operator confirms a preview card, dispatch directly from the stored
preview parameters rather than asking the Queen LLM to restate the same plan.

Important nuance:

- the confirm action should still leave a thread-visible record of operator
  confirmation or acceptance
- this should not become an invisible side-effect outside the thread story

### 3D. Drill-down stays available

Complex editing and rich inspection still belong in structured surfaces:

- full colony creator
- colony detail
- colony audit
- thread timeline

Wave 49 keeps those surfaces. It simply makes chat the default orchestration
front door.

### Seams

- `frontend/src/components/queen-overview.ts`
- `frontend/src/components/formicos-app.ts`
- `frontend/src/components/colony-creator.ts` only if prefill/drill-down
  support is needed
- `frontend/src/state/store.ts`

## Pillar 4: Bounded Progress In Chat

**Class:** Should

Wave 49 should improve progress visibility without turning chat into a raw
event log.

### 4A. Prefer Queen-authored progress summaries

For the conversational spine, prefer Queen-authored summaries of important
state changes:

- colony started
- colony blocked
- colony completed
- relevant Forager outcome

This is better than flooding the chat with raw lifecycle rows.

### 4B. Use selective notify rows only where they help

The chat may still include compact notify rows for a few things when useful,
but they should remain bounded:

- operator-interesting progress
- forage completion tied to the active thread
- explicit asks or approvals

### 4C. Do not become a generic activity feed

Fail this wave if Queen chat becomes:

- a mirror of every colony event
- a second timeline
- a noisy log viewer that dilutes the conversational thread

The thread timeline from Wave 48 already exists for full chronology.

## Pillar 5: Queen Thread Compaction

**Class:** Must

Wave 49 makes chat the primary surface. That increases the importance of long
conversation behavior on the Queen path.

The colony round path already has bounded assembly and summary compaction.
The Queen thread path does not. Today it still appends the full thread history
into prompt context. Wave 49 should fix that as part of the conversational
surface work rather than deferring it to a later rescue pass.

### 5A. Trigger compaction by token pressure

Do not compact solely by raw message count.

The compaction seam should trigger when the Queen thread message history
crosses a bounded token threshold, with a recent-message window kept raw.

### 5B. Keep recent and unresolved items pinned

The compactor should preserve in full:

- the last bounded window of recent messages
- unresolved `ask` messages
- active preview-card messages that still represent a live operator decision
- current workflow / active-plan state that would be dangerous to collapse too
  early

### 5C. Build one deterministic earlier-conversation block

Older thread history should collapse into one bounded summary block such as
`Earlier conversation:` followed by structured, replay-safe condensed truth.

Prefer assembling that block from structured data first:

- confirmed preview metadata
- result-card metadata
- workflow state
- Queen notes / pinned preferences where already available

Only use compacted older prose where the structured state is insufficient.

### 5D. No LLM summarizer in v1

The first version should be deterministic and cheap:

- stable across replay
- safe on local models
- free of non-deterministic summary drift

This is a compaction helper, not a new intelligence subsystem.

### Seams

- `src/formicos/surface/queen_runtime.py`
- `src/formicos/core/events.py`
- `src/formicos/surface/projections.py`
- `frontend/src/types.ts` only if metadata mirrors require it

## Priority Order

| Priority | Item | Pillar | Class |
|----------|------|--------|-------|
| 1 | Replay-safe structured `QueenMessage` metadata | 1A | Must |
| 2 | Preview metadata on persisted Queen thread messages | 1B | Must |
| 3 | Preview card with confirm/cancel | 2A + 3C | Must |
| 4 | Result-card metadata on Queen follow-up messages | 1C | Must |
| 5 | Result card with deep links | 2B | Must |
| 6 | Chat-first default layout | 3A | Must |
| 7 | Compact always-visible status header | 3B | Must |
| 8 | Ask/notify classification and rendering | 1D + 2C | Must |
| 9 | Deterministic Queen thread compaction | 5A + 5B + 5C + 5D | Must |
| 10 | Bounded inline adjust / drill-down handoff | 2A + 3D | Should |
| 11 | Selective progress notify rows / summaries | 4A + 4B | Should |

## Team Assignment

### Team 1: Backend Message Enrichment

Owns:

- additive `QueenMessage` metadata
- projection support
- contract mirrors
- structured preview/result payload attachment
- ask/notify classification
- deterministic Queen thread compaction

Primary files:

- `src/formicos/core/events.py`
- `docs/contracts/events.py`
- `docs/contracts/types.ts`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/queen_runtime.py`
- `frontend/src/types.ts`

### Team 2: Chat Components + Layout

Owns:

- preview card UI
- result card UI
- Queen chat rendering expansion
- chat-first layout
- compact header
- confirm/cancel UI flow
- deep-link navigation

Primary files:

- `frontend/src/components/queen-chat.ts`
- `frontend/src/components/fc-preview-card.ts`
- `frontend/src/components/fc-result-card.ts`
- `frontend/src/components/queen-overview.ts`
- `frontend/src/components/formicos-app.ts`
- `frontend/src/state/store.ts`
- `frontend/src/components/colony-creator.ts` only if drill-down prefill is
  needed

### Team 3: Recipes + Docs + Polish

Owns:

- Queen recipe guidance for chat-first, preview-first orchestration
- docs truth for conversational flow
- packet/status truth after Teams 1 and 2 land
- end-to-end flow wording and operator guidance

Primary files:

- `config/caste_recipes.yaml`
- `AGENTS.md`
- `CLAUDE.md`
- `docs/OPERATORS_GUIDE.md`
- `docs/waves/wave_49/*`

## What Wave 49 Does Not Include

- no new event types
- no new model-routing intelligence
- no voice interface
- no NeuroStack or external memory dependency
- no cross-workspace/global knowledge tier
- no new runtime
- no dashboard removal
- no raw-event-log-as-chat redesign

## Smoke Test

1. Operator types a task in Queen chat.
2. Queen proposes a structured preview card inline in the thread.
3. Refresh/reconnect preserves the card because it is rebuilt from persisted
   Queen thread state.
4. Operator clicks Confirm and the colony dispatches without restating the plan
   through another LLM round.
5. The thread records the operator confirmation in a visible way.
6. Queen chat stays the primary visible surface by default.
7. A compact status header remains visible above chat.
8. Colony completion produces a structured result card with deep links.
9. Clicking Audit or Timeline drills into the existing Wave 48 surfaces.
10. The chat feels Queen-thread-first, not like a raw colony event log.
11. Long Queen conversations degrade gracefully because older history compacts
    into a bounded earlier-conversation block while recent and unresolved items
    remain intact.
12. Full CI remains clean.

## After Wave 49

FormicOS opens to a conversation, not a configuration ritual.

The operator states the task in chat. The Queen proposes a plan with real
preview truth. The operator confirms inline. Progress is communicated as
bounded notifications, not log spam. Results come back as actionable cards
with links into the full audit surfaces. The dashboard remains available, but
it is no longer the first thing the operator must navigate through.

**empower → deepen → harden → forage → complete → prove → fluency → operability
→ conversation**
