# Wave 7 Summary

**Completed:** 2026-03-12
**Stream:** T3 - LOC budget, layer boundaries, restart recovery
**Validation at delivery:** 350 tests passing, layer lint clean

## What shipped

### Unit tests
- `tests/unit/test_layer_boundaries.py` - AST-based import analysis verifying no backward imports across the 4-layer architecture: core imports nothing, engine only core, adapters only core, surface may import all.
- `tests/unit/test_restart_recovery.py` - Event serialization round-trips (WorkspaceCreated, ColonySpawned, RoundCompleted), SQLite store survives reopen, event ordering preserved, single database file constraint.

### Contract tests
- `tests/contract/test_loc_budget.py` - Counts non-blank non-comment Python lines across core+engine+adapters+surface and asserts the 15K LOC hard limit from CLAUDE.md rule 6.

## Approach

Layer boundary tests parse Python AST to extract `import` and `from ... import` statements, then classify each import into its FormicOS layer. Any backward import (e.g., core importing from engine) fails the test.

Restart recovery tests verify the event-sourcing guarantee: serialize events to JSON, deserialize them, and confirm field-level equality. The SQLite store test creates a real temp database, writes events, closes it, reopens it, and verifies all events replay correctly.

## Decisions made

1. **AST-based import scanning over regex.** More reliable for Python's import syntax variants and avoids false positives from string literals.
2. **LOC budget uses simple line counting.** Non-blank, non-comment lines. `#`-only lines excluded. Matches the spirit of the 15K LOC cap without over-engineering.
3. **Recovery tests use real SqliteEventStore.** Not mocked — the actual adapter is tested against a temp file to verify the full persistence path.

## Issues found

None. All tests green on first integration with the delivered Surface layer.
