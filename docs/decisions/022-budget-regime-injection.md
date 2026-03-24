# ADR-022: Budget Regime Injection into Agent Prompts

**Status:** Accepted  
**Date:** 2026-03-14  
**Stream:** B

## Decision

Inject a budget status block into every agent's system prompt before each LLM call. The block shows remaining budget, iteration count, round progress, and a regime-specific advice string. This is mandatory for Wave 14.

## Context

Budget awareness is only useful if it is visible to the agent at decision time. A hard cutoff alone is reactive. The prompt block gives the agent proactive context about how much effort is still affordable.

## Regimes

| Regime | Budget remaining | Advice |
|---|---|---|
| HIGH | >=70% | Explore freely when helpful |
| MEDIUM | 30-70% | Stay focused on the strongest path |
| LOW | 10-30% | Wrap up and reduce exploration |
| CRITICAL | <10% | Answer with what you have |

## Consequences

- every LLM call gains a small prompt overhead
- colony cost tracking must remain accurate enough to make the prompt meaningful
- the budget block and iteration caps are complementary, not competing, controls

## Rejected alternatives

**Hard cutoff only**  
Rejected. It gives the agent no chance to adapt behavior before the cutoff.

**Optional flag**  
Rejected. It creates configuration surface without a strong reason.

## Implementation note

See `docs/waves/wave_14/algorithms.md`, Section 3.
