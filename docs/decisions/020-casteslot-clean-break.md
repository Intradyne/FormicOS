# ADR-020: CasteSlot Clean Break

**Status:** Accepted  
**Date:** 2026-03-14  
**Stream:** A

## Decision

Replace `caste_names: list[str]` with `castes: list[CasteSlot]` across the stack in one coordinated migration. There is no backward-compatible dual format in Wave 14.

## Context

The old spawn flow carries only string caste names. It cannot represent:
- per-caste tier overrides
- repeated castes with explicit counts
- template-driven spawn metadata cleanly

FormicOS is still pre-release with no external consumers of the event schema, so a clean break is cheaper than scaffolding a long deprecation window.

## Consequences

- `ColonySpawned` changes shape from `caste_names` to `castes`
- `template_id` becomes part of the spawn/event shape
- all mirrors and tests that still reference `caste_names` must update in the same pass
- pre-Wave-14 event-store data is not expected to remain schema-compatible

## Rejected alternatives

**Dual-format support**  
Rejected. It would add parsing branches, tests, and migration debt to a pre-release system with no external API consumers.

**Gradual migration over multiple waves**  
Rejected. This is the correct wave to open the contracts once.

## Implementation note

See `docs/waves/wave_14/algorithms.md`, Section 10, for the ordered migration sequence.
