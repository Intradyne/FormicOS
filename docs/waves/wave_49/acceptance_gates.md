Wave 49 is accepted when Queen chat becomes a replay-safe orchestration
surface rather than a thin message shell, without collapsing into a raw event
feed or a second transient UI state machine.

## Gate 1: Structured Queen Chat Metadata Is Replay-Safe

Must be true:

- `QueenMessage` gains only additive optional metadata fields
- older logs replay safely with defaults
- thread snapshots and incremental events rebuild the same structured chat state

Fail if:

- the card/intent state only exists in transient runtime memory
- a page refresh or snapshot rebuild destroys the conversational cards
- backward compatibility is broken for existing event logs

## Gate 2: Preview Cards Use Real Shared Preview Truth

Must be true:

- Queen preview proposals render as structured cards in chat
- card payloads come from the real backend preview substrate
- both single-colony and parallel-plan preview shapes are supportable

Fail if:

- the card scrapes LLM prose to reconstruct the plan
- the card uses a second heuristic preview implementation
- the flow invents fields the backend did not actually provide

## Gate 3: Result Cards Use Real Colony Outcome Truth

Must be true:

- colony completion can render as a structured result card in chat
- the card payload is grounded in replay-safe projection truth
- deep links use stable identifiers, not brittle text parsing

Fail if:

- the result card is assembled from guesswork or stale UI cache only
- the card vanishes on reconnect

## Gate 4: Chat Is The Primary Surface

Must be true:

- Queen chat is the default primary presentation inside the Queen view
- the dashboard is still available as a drill-down or reveal surface
- critical operator status remains visible in compact form

Fail if:

- chat is still effectively a side rail
- the dashboard disappears entirely
- hiding the dashboard also hides critical operational context

## Gate 5: Confirm Flow Stays Conversational And Visible

Must be true:

- preview confirmation can dispatch directly from stored preview parameters
- the thread shows a visible record of operator confirmation / acceptance
- the operator does not need to navigate away for the normal case

Fail if:

- confirmation is an invisible UI-only side effect
- chat confirm still requires a second natural-language restatement loop
- the main path bounces the operator back into a large configuration form

## Gate 6: Ask And Notify Stay Distinct

Must be true:

- ask vs notify semantics are represented explicitly
- rendering keeps those states visibly different
- the UI only uses heuristics as fallback, not as the primary source of truth

Fail if:

- every Queen message looks the same
- card/text/intent concerns are collapsed into one overloaded field
- the operator cannot tell when the Queen genuinely needs input

## Gate 7: Queen Chat Stays Queen-Thread-First

Must be true:

- the Queen remains the main authorial spine of the chat
- raw colony/Forager events stay supporting context
- the thread timeline remains the full chronology surface

Fail if:

- the Queen chat becomes a generic event feed
- Wave 49 duplicates the thread timeline inside chat
- the chat is flooded with low-level lifecycle rows

## Gate 8: Long Queen Conversations Degrade Gracefully

Must be true:

- the Queen thread path compacts older conversation history before prompt
  context becomes dangerously large
- compaction is deterministic and replay-safe
- recent messages and unresolved operator-facing decisions stay intact
- the compacted history prefers structured thread truth first and prose second

Fail if:

- Wave 49 ships a better chat surface that still relies on unbounded full
  thread replay
- preview/result/ask state can disappear from useful context after compaction
- compaction depends on a non-deterministic LLM summarizer in the first
  version
- a longer Queen session still degrades by abruptly hitting a hard context wall

## Gate 9: Product Identity Holds

Must be true:

- no new runtime or external dependency was introduced
- no external memory vault was added
- the wave still reads as a product-surface upgrade on existing FormicOS
  substrate

Fail if:

- the work starts depending on NeuroStack or similar systems
- the chat flow exists mainly to look benchmark-friendly rather than to help an
  operator do real work

## Gate 10: Docs And Recipes Match Reality

Must be true:

- Queen recipe guidance matches the actual conversational flow
- docs explain chat-first orchestration truthfully
- deferred items remain explicitly deferred

Fail if:

- docs claim cards/ask-notify behaviors that did not really land
- docs imply a new intelligence layer that the repo does not contain

## Gate 11: Wave 50+ Remains Native

Should be true:

- Wave 49 leaves the path to native cross-workspace learning intact
- nothing in the packet makes external memory dependencies feel required

Fail if:

- the packet quietly assumes an external memory system for the chat-first
  experience
- follow-on learning starts to depend on foreign retrieval semantics rather
  than FormicOS's own substrate
