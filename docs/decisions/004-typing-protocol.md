# ADR-004: typing.Protocol for Port Interfaces

**Status:** Accepted
**Date:** 2026-03-12

## Context
The four-layer architecture requires port interfaces in core/ that adapters implement.
Two Python approaches: Abstract Base Classes (abc.ABC) requiring inheritance, or
typing.Protocol enabling structural subtyping (duck typing with static checking).

## Decision
All port interfaces (LLMPort, EventStorePort, VectorPort, CoordinationStrategy,
SandboxPort) use `typing.Protocol`. No ABC inheritance required. Adapters satisfy
the protocol by implementing the right method signatures — pyright verifies this
statically without runtime registration.

## Consequences
- **Good:** No inheritance coupling between core/ and adapters/. True structural subtyping.
- **Good:** Easier testing — any object with the right methods satisfies the protocol.
- **Good:** pyright strict mode catches protocol violations at type-check time.
- **Bad:** No runtime isinstance() checks unless @runtime_checkable is added.
- **Acceptable:** Runtime type checking is not needed — wiring happens once at startup
  in surface/app.py, and pyright catches mismatches before CI completes.

## FormicOS Impact
Affects: core/ports.py, all adapter implementations, surface/app.py (wiring).
