# ADR-024: Provider Cooldown Cache

**Status:** Accepted  
**Date:** 2026-03-14  
**Stream:** B

## Decision

Add a cooldown cache to `LLMRouter` in `surface/runtime.py` so provider outages and repeated transient failures route around unhealthy providers automatically.

## Context

FormicOS now spans local plus multiple cloud providers. Without a cooldown layer, an outage or repeated rate-limit burst can cascade across an entire colony run.

## Rules

- track failures per provider in a sliding window
- after repeated failures, cool the provider down for a category-specific duration
- when the provider is cooled down, route to the next viable fallback
- when all cloud providers are unavailable, route local
- Gemini content-blocked responses are per-request fallback cases, not global provider-health failures

## Consequences

- cooldown state is in-memory only
- this is not a full circuit-breaker state machine
- operator visibility should come from routing/chat logs, not a new persistent control plane

## Rejected alternatives

**Full circuit-breaker framework**  
Rejected. Too much machinery for the current provider count.

**No resilience layer**  
Rejected. It would burn budget and reduce colony reliability during outages.

## Implementation note

See `docs/waves/wave_14/algorithms.md`, Section 5.
