This document compresses the Wave 40 plan into the smallest set of gates that
must be true before the wave can be accepted as landed.

Primary source of truth:
- `docs/waves/wave_40/wave_40_plan.md`

---

## Must Ship

### Gate 1: Profiling-first backend coherence lands without substrate drift

All of the following must be true:

1. A baseline profiling report exists.
2. The main backend refactors are grounded in measured hotspots or obvious
   coherence debt, not speculative cleanup.
3. The highest-risk files become easier to navigate without changing the
   substrate contract.
4. No hidden event expansion or product-scope creep is introduced.

Passing evidence:

- `docs/waves/wave_40/profiling_report.md` exists
- `colony_manager.py` is meaningfully cleaner or more clearly factored
- `runner.py` is more navigable where it was targeted
- any moved helpers preserve behavior and import stability where practical

### Gate 2: Cross-feature interaction truth is materially stronger

All of the following must be true:

1. The repo includes new tests for the highest-risk interaction pairs.
2. The interaction tests cover real multi-wave seams rather than only
   single-feature assertions.
3. No known replay-truth or reporting-truth regression is introduced.

Passing evidence:

- top interaction pairs are covered
- escalation / validator / overlay / federation / config-memory seams are
  tested where applicable

### Gate 3: Frontend surfaces are more consistent and the demo still works

All of the following must be true:

1. The main operator-facing surfaces use a more consistent visual language.
2. Empty states and loading states are not silently broken.
3. The Wave 36 demo flow still works against the post-Wave-39 codebase.

Passing evidence:

- the main command-center and knowledge surfaces feel consistent
- the browser smoke or equivalent demo validation passes
- no Wave 39 surface breaks the demo path

### Gate 4: Documentation truth catches up to the code

All of the following must be true:

1. The primary docs describe the post-Wave-39 system honestly.
2. Event-count, overlay, validator, escalation, and configuration truth are
   correct.
3. The ADR index does not overclaim decisions that are not actually in the
   repo.

Passing evidence:

- `CLAUDE.md` and `docs/OPERATORS_GUIDE.md` are accurate
- the knowledge-lifecycle and protocol docs are aligned with code reality
- docs no longer describe pre-Wave-38 / pre-Wave-39 behavior as current truth

### Gate 5: Protocol surfaces are honest and do not fork task truth

All of the following must be true:

1. The native colony-backed task API is clearly the first-class surface.
2. Any A2A compatibility work remains a thin translation layer over the same
   task truth.
3. No second task store or second execution path is introduced.
4. The Agent Card and docs advertise conformance levels honestly.

Passing evidence:

- REST colony task lifecycle remains the canonical task truth
- any JSON-RPC wrapper maps to the same underlying colony-backed task flow
- protocol docs and Agent Card match the implementation

---

## Should Ship

### Gate 6: Large-file audits leave the repo more legible

The repo should include:

- a clear `queen_tools.py` coherence outcome
- a clear `projections.py` organization outcome
- a justified `proactive_intelligence.py` rule-assembly cleanup if touched

### Gate 7: Flaky or under-explained test behavior is reduced

The repo should include:

- a flaky-test audit
- fixes or quarantines for genuinely unstable tests
- clearer deterministic behavior where stochastic seams were hiding

### Gate 8: Frontend decomposition happens only where it earns its keep

If sub-components are extracted, all of the following must be true:

1. they improve navigability
2. they do not change product scope
3. they reduce complexity in an existing oversized surface

---

## Stretch

### Gate 9: Coverage gap analysis lands cleanly

If coverage-gap work ships, it should:

1. target genuinely weak high-traffic surfaces
2. remain focused
3. avoid turning Wave 40 into generic test spam

### Gate 10: Large-entry frontend review ships cleanly

If the knowledge-browser performance review ships, it should:

1. be grounded in real large-entry behavior
2. fix actual rendering or scroll issues
3. not drift into redesign work

---

## Cut Line

Cut from the bottom first:

1. coverage-gap extras
2. optional frontend decomposition
3. large-entry browser polish
4. secondary doc cleanup

Do not cut:

1. baseline profiling report
2. main backend coherence work
3. core interaction tests
4. demo-path validation
5. primary docs truth
6. protocol honesty

---

## Final Acceptance Statement

Wave 40 is acceptable when FormicOS is more trustworthy in three ways:

1. **Code trust** -- the highest-risk files are cleaner, more legible, and less
   likely to hide avoidable failures.
2. **Interaction trust** -- cross-feature behavior is tested where multi-wave
   seams were previously thin.
3. **Operator truth** -- docs, UI, and protocol surfaces describe the system as
   it actually is, not as earlier waves left it.
