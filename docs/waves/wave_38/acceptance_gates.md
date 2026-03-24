# Wave 38 Acceptance Gates

This document compresses the Wave 38 plan into the smallest set of gates that
must be true before the wave can be accepted as landed.

Primary source of truth:
- `docs/waves/wave_38/wave_38_plan.md`

---

## Must Ship

### Gate 1: FormicOS is more callable from the ecosystem without lying about its protocols

All of the following must be true:

1. NemoClaw or equivalent external specialists can be called through the
   existing tool-level service seam.
2. The call path is traceable through existing service-query events.
3. The Agent Card, A2A docs, and actual routes agree on what FormicOS supports.
4. Wave 38 does not pretend that model-level external agents already landed.

Passing evidence:

- a NemoClaw-style specialist call works through `query_service`
- `/.well-known/agent.json` and `docs/A2A-TASKS.md` describe the live surface
  truthfully

### Gate 2: Internal benchmarking is strong enough to guide Wave 39 and de-risk Wave 40

All of the following must be true:

1. The Wave 37 harness is extended to harder external-style task slices.
2. The benchmark suite reports success, quality, cost, and wall time.
3. The suite can compare baseline / Wave 37 / Wave 38-relevant configurations.
4. Results are reproducible locally, not just anecdotal.

Passing evidence:

- benchmark output distinguishes multiple configurations
- internal benchmark docs explain what the suite does and does not prove

### Gate 3: The escalation outcome matrix exists before any auto-escalation work begins

All of the following must be true:

1. Manual or governance-owned escalation through `routing_override` is visible
   in a replay-derived outcome matrix.
2. The matrix captures start tier, escalated tier, reason, round, cost, wall
   time, quality, and final outcome.
3. Provider fallback is not mixed into this matrix as if it were capability
   escalation.

Passing evidence:

- an escalated colony can be inspected and reported cleanly
- the matrix is grounded in `routing_override`, not hidden router behavior

### Gate 4: Poisoning defense is no longer pass-through

All of the following must be true:

1. Admission scoring materially affects intake or downstream trust, rather than
   being explanatory only.
2. Scanner findings and admission policy work together.
3. Weak federated entries cannot easily dominate strong local verified entries.
4. Operators can still understand why an entry was trusted, demoted, or blocked.

Passing evidence:

- suspicious entries are blocked or strongly demoted through existing status
  surfaces
- federation trust tests show local verified dominance under normal conditions

### Gate 5: Bi-temporal knowledge is visible enough to reason about time honestly

All of the following must be true:

1. Temporal validity is surfaced where the repo actually has temporal truth.
2. Transaction time and validity time are distinguished explicitly.
3. Contradicted facts can be invalidated rather than only disappearing.
4. Wave 38 does not overclaim a fully temporalized knowledge layer if only part
   of the substrate is temporalized.

Passing evidence:

- at least graph edges and selected knowledge-entry surfaces show validity
  windows where available
- operator-facing surfaces explain the distinction clearly

---

## Should Ship

### Gate 6: Ecosystem operator docs are good enough for another team to follow

The repo should include:

- NemoClaw integration setup guidance
- A2A capability and compatibility notes
- explicit auth and deployment assumptions

### Gate 7: Internal benchmark interpretation is recorded

The repo should keep an internal note or template describing:

- where the architecture helped
- where it did not
- what Wave 39 should tune next

---

## Stretch

### Gate 8: Bi-temporal memory-entry validity windows ship without forcing a casual core change

If deeper temporalization of institutional memory ships, all of the following
must be true:

1. It stays replay-safe.
2. It remains honest about missing validity windows.
3. It does not casually widen `core/` without an ADR-backed reason.

If those conditions are not met, edge-level and additive read-model temporal
surfacing is still a valid Wave 38 landing point.

---

## Cut Line

If Wave 38 runs long, cut in this order:

1. internal benchmark publication note
2. deeper bi-temporal memory-entry validity windows
3. ecosystem-doc polish beyond the operational essentials

Do not cut:

1. tool-level external specialist bridge
2. A2A truth and compatibility hardening
3. external-style internal benchmark suite
4. escalation outcome matrix
5. real admission scoring
6. federation trust hardening
7. temporal truth surfacing where the substrate already supports it

Those are the wave.

---

## Final Acceptance Statement

Wave 38 should only be called landed if FormicOS is stronger in all three of
these ways:

- **ecosystem trust:** external systems can call it through truthful,
  documented, auditable seams
- **measurement trust:** the system can judge its own architecture on harder
  tasks before going public
- **knowledge trust:** the substrate is harder to poison and more honest about
  time
