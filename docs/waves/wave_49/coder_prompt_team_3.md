You own the Wave 49 recipe, docs-truth, and conversational-guidance track.

This is the guidance-and-truth pass. You are not inventing runtime behavior.
You are aligning Queen guidance, operator docs, and the Wave 49 packet with
what Teams 1 and 2 actually ship.

## Mission

Update the repo guidance to reflect Wave 49 reality:

1. document the chat-first orchestration flow truthfully
2. align Queen recipe guidance with preview-first / ask-vs-notify behavior
3. keep the Wave 49 packet honest about what shipped and what deferred

The core rule still applies:

**If the benchmark disappeared tomorrow, would we still want this change in
FormicOS?**

Yes. A truthful conversational front door is a real operator improvement.

## Read First

1. `AGENTS.md`
2. `CLAUDE.md`
3. `docs/OPERATORS_GUIDE.md`
4. `config/caste_recipes.yaml`
5. `docs/waves/wave_49/wave_49_plan.md`
6. `docs/waves/wave_49/acceptance_gates.md`

Before editing, reread the final Team 1 and Team 2 landed files. Do not
document the planned ideal if the code landed a narrower reality.

## Owned Files

- `config/caste_recipes.yaml`
- `AGENTS.md`
- `CLAUDE.md`
- `docs/OPERATORS_GUIDE.md`
- `docs/waves/wave_49/*`
- `README.md` only if a very small truthful capability summary update is
  warranted

## Do Not Touch

- product code
- frontend code
- backend code
- contract/event code

## Required Work

### Track A: Queen Guidance For Conversational Flow

Update the Queen recipe guidance to match the shipped Wave 49 flow.

Desired framing:

- chat-first orchestration
- preview-first before dispatch when appropriate
- ask vs notify discipline
- deterministic long-conversation behavior if Queen thread compaction lands
- minimal-colony-first still applies from Wave 48

Do not imply that the Queen became smarter in Wave 49. The intelligence
already existed; the presentation and interaction flow improved.

### Track B: Conversational Flow Docs Truth

Document only what really lands:

- preview cards
- result cards
- ask/notify conversational cues
- chat-first Queen layout
- Queen thread compaction if it truly shipped
- drill-downs into existing Wave 48 surfaces

If inline adjust is partial or absent, say so clearly.

### Track C: Packet Truth

Refresh the Wave 49 packet after the substrate lands:

- what shipped
- what deferred
- where the implementation narrowed the original plan
- whether chat stayed Queen-thread-first or drifted toward event feed
- whether Queen thread compaction landed fully, partially, or deferred

### Track D: Architectural Truth

Keep these points explicit:

- no new event types were added
- additive `QueenMessage` metadata was the key contract move
- deterministic Queen thread compaction is part of the conversational surface,
  not a new intelligence subsystem, if it ships
- no new runtime or external dependency was introduced
- no NeuroStack / external memory dependency is required for the
  conversational layer

### Track E: Operator Expectations

Explain the intended operator flow succinctly:

1. type task in Queen chat
2. see preview card
3. confirm inline
4. watch bounded progress
5. inspect result card
6. drill into audit/timeline/detail only when needed

This should read like a product guide, not an architecture manifesto.

## Hard Constraints

- Do not fabricate shipped card behaviors
- Do not overclaim ask/notify intelligence
- Do not imply a new intelligence engine
- Do not reintroduce NeuroStack / external-memory dependency language
- Do not let the docs describe Queen chat as a raw event feed if the product
  correctly avoids that

## Validation

Run at minimum:

1. a grep sweep for stale Wave 48 / Wave 49 Queen-chat claims
2. any lightweight docs validation already used in the repo, if applicable

## Summary Must Include

- exactly how the Queen recipe guidance changed
- which conversational behaviors you documented as shipped
- which parts of the original Wave 49 sketch you kept explicitly deferred
- how the final docs describe the replay-safe `QueenMessage` metadata move
- how the final docs describe Queen thread compaction status
