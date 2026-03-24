This document compresses the Wave 39 plan into the smallest set of gates that
must be true before the wave can be accepted as landed.

Primary source of truth:
- `docs/waves/wave_39/wave_39_plan.md`

---

## Must Ship

### Gate 1: Operator co-authorship is durable and replay-safe

All of the following must be true:

1. ADR-049 lands before Pillar 2 implementation begins.
2. Operator actions survive replay.
3. Operator actions are reversible.
4. Operator actions are local-first by default.
5. Local operator actions do not silently mutate shared confidence truth.

Passing evidence:

- pin / unpin / mute / unmute / invalidate / reinstate survive replay
- no local operator action implicitly emits shared confidence mutations
- federation policy is explicit and matches ADR-049

### Gate 2: The audit trail explains colony behavior without lying about history

All of the following must be true:

1. A colony-level audit surface exists.
2. The audit surface helps answer "why did this happen?" without raw transcript
   spelunking.
3. Exact runtime-only internals are not presented as exact historical truth
   unless they are replay-safe.
4. The audit trail remains a read-model / projection surface, not a second
   hidden truth store.

Passing evidence:

- directives, knowledge use, governance actions, and escalations are visible
- replay-safe truth is clearly separated from explanatory reconstruction

### Gate 3: Completion truth is more honest across task types

All of the following must be true:

1. Deterministic validators exist for at least the bounded task families in
   scope.
2. Colony status surfaces distinguish validated, unvalidated, and stalled.
3. Validator state is replay-derivable or derived from existing projection
   truth, not hidden runtime-only state.

Passing evidence:

- a research or documentation colony can complete with validator `pass` or
  `fail`
- the UI distinguishes Done (validated), Done (unvalidated), and Stalled

### Gate 4: Auto-escalation remains governance-owned and visible

All of the following must be true:

1. Auto-escalation flows through `routing_override`.
2. Provider fallback is still not conflated with capability escalation.
3. Auto-escalation is bounded and budget-aware.
4. Auto-escalation is visible in audit and outcome surfaces.

Passing evidence:

- the escalation outcome matrix continues to read cleanly
- the operator can inspect why the escalation fired and what changed

### Gate 5: Configuration recommendations are inspectable and editable

All of the following must be true:

1. The operator can see what configuration the system recommends and why.
2. The operator can edit at least the bounded pre-spawn configuration surface.
3. Overrides are durable where they are supposed to be durable.
4. Recommendations remain advisory, not hidden automation.

Passing evidence:

- recommendation surfaces include evidence
- operator edits are recorded through `ConfigSuggestionOverridden`

---

## Should Ship

### Gate 6: Earned autonomy recommendations are evidence-backed

The repo should include:

- recommendation logic by insight category
- visible accept / dismiss surfaces
- cooldown and threshold behavior that prevent spammy or under-evidenced advice

### Gate 7: Decision provenance extends beyond one colony

The repo should include:

- a Queen-plan-to-colony-outcome causal chain
- enough visibility to explain why a plan was proposed and how it turned out

---

## Stretch

### Gate 8: Configuration history is visible over time

If configuration history ships, all of the following must be true:

1. it is grounded in actual prior recommendations or outcomes
2. it does not fabricate historical recommendations that were never stored
3. it remains explanatory rather than pretending to reconstruct missing truth

### Gate 9: Expanded validator-result presentation ships cleanly

If richer validator UI ships, it should:

1. remain consistent with the tri-state model
2. not imply validator coverage where no validator exists

---

## Cut Line

If Wave 39 runs long, cut in this order:

1. configuration history
2. richer validator result presentation
3. extended decision provenance beyond the core colony audit view

Do not cut:

1. ADR-049 and the narrow 3-event expansion
2. replay-safe operator overlays
3. colony reasoning audit view
4. task-type validators
5. tri-state completion display
6. governance-owned auto-escalation
7. editable pre-spawn recommendation surface

Those are the wave.

---

## Final Acceptance Statement

Wave 39 should only be called landed if FormicOS is stronger in all three of
these ways:

- **control-plane trust:** operators can inspect and correct important system
  behavior without their edits vanishing on replay
- **governance trust:** completion and escalation behavior are more honest and
  more inspectable
- **editorial trust:** local operator preference is kept separate from shared
  epistemic truth
