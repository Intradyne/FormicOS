# ADR-002: Pydantic v2 as Sole Serialization Library

**Status:** Accepted
**Date:** 2026-03-12

## Context
The v1 alpha planned a dual-serialization approach: msgspec for hot-path events
(10–75× faster encode/decode) and Pydantic v2 for config/API validation. This
created constant confusion about which serializer to use where, doubled the
testing surface, and introduced a single-maintainer risk with msgspec.

## Decision
Pydantic v2 is the sole serialization library. All types — events, config, API
models — use `pydantic.BaseModel`. Immutable event types use
`model_config = ConfigDict(frozen=True)`. The discriminated union for events uses
`Annotated[Union[...], Field(discriminator='type')]`.

No msgspec. No dataclasses for serialized types.

## Consequences
- **Good:** One library to learn, one pattern to follow, one test surface.
- **Good:** Pydantic v2's validation, coercion, and error messages work everywhere.
- **Bad:** ~5–12× slower than msgspec on microsecond serialization benchmarks.
- **Acceptable:** FormicOS spends 100ms–10s per step on LLM inference. At alpha
  scale (dozens of events/sec), serialization overhead is invisible. If scaling
  pressure makes this matter (thousands of events/sec), the EventStorePort
  abstraction enables a targeted hot-path migration without touching engine code.

## FormicOS Impact
Affects: core/events.py, core/types.py, all serialization boundaries.
