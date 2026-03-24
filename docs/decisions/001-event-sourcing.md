# ADR-001: Event Sourcing as Sole Persistence Mechanism

**Status:** Accepted
**Date:** 2026-03-12

## Context
FormicOS needs persistent state for workspaces, threads, colonies, agent turns,
configuration changes, and governance decisions. Traditional CRUD with an ORM would
require schema migrations, lose historical state, and make debugging agent behavior
nearly impossible.

## Decision
Every state change is captured as an immutable, append-only event in a single SQLite
database (WAL mode). Current state is derived by replaying events or reading materialized
projections. One logical event store — no second database, no shadow stores, no separate
telemetry DB.

CQRS read-model projections are materialized views updated synchronously within the same
SQLite transaction at alpha scale. Async projections deferred until scaling requires them.

## Consequences
- **Good:** Complete audit trail. Time-travel debugging. Crash recovery via replay.
  State can be rebuilt from scratch. Natural fit for WebSocket event streaming.
- **Good:** Single SQLite file simplifies backup, deployment, and local-first operation.
- **Bad:** Querying current state requires projections (more code than raw SQL queries).
- **Bad:** Event schema evolution requires migration tooling eventually.
- **Acceptable:** SQLite WAL handles ~5,000–8,000 writes/sec. FormicOS targets dozens/sec.
  Orders of magnitude of headroom. If scaling beyond single-machine, the EventStorePort
  abstraction enables migration to PostgreSQL without engine changes.

## FormicOS Impact
Affects: core/events.py, adapters/store_sqlite.py, all consumers of state.
