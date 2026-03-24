# ADR-033: Colony Chaining Through Input Sources

**Status:** Accepted  
**Date:** 2026-03-15  
**Wave:** 19

## Decision

Extend colony spawning with `input_sources` so a new colony can receive compressed output from a completed colony as seed context. Resolution happens at spawn time and the resolved summary is stored on the event.

## Context

Colonies currently run as isolated executions. Even when one colony produces exactly the material the next colony needs, the handoff is manual or indirect through the skill bank.

That is the wrong level of abstraction for task-specific carry-forward. The skill bank is for durable learned patterns; chaining is for passing a concrete prior result into the next colony with explicit attribution.

Wave 19 adds this through a spawn parameter rather than a new lifecycle event.

## Data Model

An `InputSource` is added in core types with a `type` discriminator.

Wave 19 implements:
- `type: "colony"`
- `colony_id`
- `summary`

`ColonySpawned` gains:
- `input_sources: list[InputSource]`

This remains backward-compatible because the default is an empty list.

## Resolution Rules

For `type: "colony"`:
- the source colony must exist
- the source colony must be `completed`
- the summary is resolved at spawn time
- the summary is stored on the event so replay does not depend on later lookups

Resolution preference:
1. Archivist summary if available
2. otherwise a truncated final-round summary/output bundle

## Context Injection

Resolved input sources are injected as seed context for the new colony with clear attribution, for example:

`[Context from prior colony X]: ...`

They should sit alongside other high-priority routed context, not be treated as a low-value add-on.

## Future Extensions

The discriminator leaves room for future source types without redesigning the structure:
- `file`
- `url`
- `skill_set`

Wave 19 intentionally implements only `colony`.

## Consequences

- the Queen can orchestrate simple multi-step workflows cleanly
- colony-to-colony handoffs become explicit and auditable
- no separate chaining event is needed
- replay remains safe because source summaries are resolved eagerly

## Rejected Alternatives

### Create a separate `ColonyChained` event

Rejected. Chaining is part of colony creation, not a separate lifecycle transition.

### Resolve the source lazily in round 1

Rejected. That creates hidden runtime coupling and weakens replay behavior.

### Inject raw full outputs

Rejected. Full outputs are too large and too inconsistent for reliable context carry-forward.

## Implementation Note

See [algorithms.md](/c:/Users/User/FormicOSa/docs/waves/wave_19/algorithms.md).
