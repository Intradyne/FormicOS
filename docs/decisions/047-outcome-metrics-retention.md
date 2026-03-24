# ADR-047: Colony Outcome Metrics Retention and Surfacing

**Status:** Accepted (shipped in Wave 36; ColonyOutcome projection and REST endpoint operational)
**Date:** 2026-03-18
**Wave:** 36
**Depends on:** Wave 35.5 (Surface Alignment, silent `ColonyOutcome` projection), ADR-039 (knowledge metabolism), ADR-046 (autonomy levels)

---

## Context

Wave 35.5 added a replay-derived `ColonyOutcome` view in
`src/formicos/surface/projections.py`. It is intentionally silent: no new
event family, no new operator-visible protocol surface, no recommendations
layer. It exists so the system can later reason about colony quality, cost,
knowledge extraction, and maintenance effectiveness without introducing
non-replayable state.

Wave 36 is the first wave that surfaces this capability:

1. **Command center posture:** Queen landing page shows recent completion
   metrics, knowledge pulse, and maintenance budget consumption.
2. **Colony intelligence:** Completed colonies show quality, cost, and
   extraction impact in both the landing page and detail view.
3. **Performance briefing:** The Queen can reference outcome patterns in her
   briefing alongside knowledge-health insights.
4. **Demo reliability:** The guided demo uses the same real outcome substrate
   as production work. No demo-only instrumentation should exist.

That requires a clear policy:
- What is canonical truth?
- What is retained versus recomputed?
- What can be surfaced in APIs and UI?
- What must remain informational rather than auto-tuning?

---

## D1. `ColonyOutcome` remains a replay-derived read model

**Decision:** `ColonyOutcome` stays a projection-derived read model built from
existing events. No new `OutcomeRecorded` event is added in Wave 36.

Canonical truth remains the existing event log:
- `ColonySpawned`
- `RoundStarted`
- `RoundCompleted`
- `ColonyCompleted`
- `ColonyFailed`
- `ColonyKilled`
- `MemoryEntryCreated`
- `KnowledgeAccessRecorded`
- existing quality / chat / agent projection data already emitted in prior waves

`ColonyOutcome` is rebuilt during replay and stored in projection memory for
querying. If replay and the derived outcome ever disagree, replay wins.

**Rationale:**
- Wave 35.5 already proved the projection can be computed from existing events.
- Wave 36 needs visibility, not another event-union expansion.
- The outcome model is analytical, not a first-class external contract yet.

---

## D2. Surfacing is additive, aggregated, and workspace-scoped

**Decision:** Wave 36 may expose outcome data through additive,
workspace-scoped read APIs and UI sections, but not as a new mutation surface.

Allowed Wave 36 surfacing:
- per-colony outcome badges on existing UI surfaces
- colony detail outcome section
- workspace aggregate outcome endpoint, for example:
  - `GET /api/v1/workspaces/{id}/outcomes?period=24h|7d|30d`
- command-center summaries such as:
  - recent completions
  - maintenance spend today
  - extraction counts
  - average quality

Not allowed in Wave 36:
- direct editing of outcome records
- per-outcome persistence outside replay
- operator-authored outcome annotations as canonical truth

**Rationale:**
- The first public release needs understandable summaries, not a second
  competing source of truth.
- Aggregated, windowed reads are enough for command-center and demo needs.

---

## D3. Retention policy is "event log forever, derived view on replay"

**Decision:** Outcome retention follows the same policy as other projections:

- The event log is the durable record.
- `ColonyOutcome` is reconstructed on replay.
- Time-window queries (`24h`, `7d`, `30d`) are produced from the current
  replayed projection state, not from separately persisted aggregates.
- If retention or performance becomes a concern later, the system may add
  derived caches, but they must remain disposable and rebuildable.

Wave 36 therefore treats outcomes as:
- durable in principle because replay is durable
- ephemeral in implementation because the projection can be rebuilt at any time

**Rationale:**
- This keeps outcome intelligence aligned with the event-sourced architecture.
- It avoids creating a hidden analytics database during the public-release wave.

---

## D4. Outcome metrics inform humans and the Queen, not automatic tuning

**Decision:** Outcome metrics in Wave 36 are informational and advisory.

They may be used for:
- command-center summaries
- demo annotations
- Queen performance briefings
- operator interpretation of colony quality / efficiency

They may not be used in Wave 36 for:
- automatic config changes
- autonomous strategy tuning
- hidden weighting changes
- experimental policy rollouts

If the Queen references outcome insights, she does so as a recommendation:
- "Stigmergic strategy has completed 23% faster in similar cases"
- not as an automatic override

**Rationale:**
- Wave 36 is the public-visibility wave.
- Wave 37 is the correct point for experimentation or controlled adaptation.

---

## D5. Maintenance spend is derived from tagged maintenance colonies

**Decision:** Maintenance budget consumption shown in Wave 36 is derived from
completed and running maintenance-tagged colonies in the current day window.

The command-center posture should compute:
- policy limit from workspace maintenance policy
- spend from replay-derived colony outcomes tagged as maintenance work

This keeps the operator-facing posture card truthful without adding a new
"maintenance spend ledger" event family.

**Rationale:**
- The budget card needs spent-vs-limit visibility for demo and operations.
- The necessary data already exists in tags, outcome cost, and workspace policy.

---

## Rejected Alternatives

**Add `OutcomeRecorded` as a 56th event type now.**
Rejected. The value in Wave 36 is visibility, not a new event contract.
Wave 35.5 already established that outcome data is replay-derivable.

**Persist rolling daily / weekly aggregates as first-class state.**
Rejected. This would create a second analytics truth and complicate replay.
Windowed aggregates can be computed from the replayed projection.

**Use outcome metrics for silent automatic strategy tuning in Wave 36.**
Rejected. That would move the system from "explainable" to "self-modifying"
without enough operator trust or experimental controls.

**Make demo-only outcome metrics separate from production metrics.**
Rejected. The demo must use the same real substrate as the rest of the system.
No fake demo analytics.

---

## Consequences

Wave 36 can safely surface colony intelligence without reopening the event
contract. The system remains replay-first. Operators and the Queen gain
interpretable performance signals. Future waves can build experimentation or
auto-tuning on top of the same substrate, but only after Wave 36 proves the
value of making outcomes visible.
