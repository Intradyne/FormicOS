You own the Wave 52 docs/ADR truth track.

This track keeps the written system description aligned with the live repo and
with the bounded Packet A / Packet B work. You do not own backend behavior or
frontend protocol UI. You own the docs truth layer and the final wave handoff.

## Mission

Land the docs-heavy parts of Wave 52:

1. correct stale event-count references
2. update ADR 045/046/047 status truth
3. align A2A / AG-UI docs with final landed Wave 52 behavior
4. create the final Wave 52 handoff/status doc

This track should start immediately, but it finishes last.

## Read First

1. `AGENTS.md`
2. `CLAUDE.md`
3. `docs/waves/wave_52/wave_52_plan.md`
4. `docs/waves/wave_52/acceptance_gates.md`
5. `docs/waves/wave_52/capability_control_inventory.md`
6. `docs/waves/wave_52/control_plane_findings.md`
7. `docs/waves/wave_52/task_intelligence_inventory.md`
8. `docs/waves/wave_52/intelligence_findings.md`
9. `docs/waves/wave_52/information_tool_flow_findings.md`
10. `docs/A2A-TASKS.md`
11. `docs/AG-UI-EVENTS.md`
12. `docs/decisions/045-event-union-parallel-distillation.md`
13. `docs/decisions/046-autonomy-levels.md`
14. `docs/decisions/047-outcome-metrics-retention.md`

## Owned Files

- `AGENTS.md`
- `CLAUDE.md`
- `docs/A2A-TASKS.md`
- `docs/AG-UI-EVENTS.md`
- `docs/decisions/045-event-union-parallel-distillation.md`
- `docs/decisions/046-autonomy-levels.md`
- `docs/decisions/047-outcome-metrics-retention.md`
- `docs/waves/wave_52/status_after_plan.md`

## Do Not Touch

- backend Python files
- frontend files
- Wave 52 audit docs
- `docs/waves/wave_52/wave_52_plan.md`
- `docs/waves/wave_52/acceptance_gates.md`

Team 1 owns backend behavior truth. Team 2 owns frontend protocol/status truth.

## Parallel-Safe Coordination Rules

### Phase 1 -- Start immediately

You can begin now on:
- stale event-count cleanup
- ADR status correction
- obvious stale protocol text in docs
- preparing `status_after_plan.md` scaffold

### Phase 2 -- Finish after reread

Before finalizing docs that depend on landed behavior:
- reread Team 1 summary and final files
- reread Team 2 summary and final files

This is the only real timing dependency in the wave. It is expected.

## Required Work

### Track A2: Event count truth

Required outcome:
- owned docs stop referring to stale counts and align on `64`

### Track A3: ADR status correction

Required outcome:
- ADR 045/046/047 read as accepted/shipped truth
- keep historical context, but do not misdescribe the live repo

### Track A6: Protocol/control-plane docs truth

Required outcome:
- A2A / AG-UI docs match the final landed Packet A / Packet B behavior
- if Team 1 leaves AG-UI omitted-default behavior unchanged, document that
- if Team 1 lands learned-template reach for A2A, document that
- if Team 1 changes timeout semantics or keeps them, document the final truth clearly

### Final handoff doc

Create `docs/waves/wave_52/status_after_plan.md` that records:
- all three teams shipped
- which acceptance gates passed
- what remained intentionally out of scope
- any residual debt classifications

## Hard Constraints

- Do not guess final behavior before rereading Team 1 / Team 2 outcomes
- Do not document protocol expansion that did not land
- Do not rewrite unrelated docs just because you are nearby

## Validation

Run at minimum:

1. verify final docs claims against the files Team 1 and Team 2 actually changed
2. `python -m pytest -q` only if you make test-affecting doc/code examples and need a sanity check

## Summary Must Include

- which stale counts were corrected
- how ADR 045/046/047 status was updated
- whether A2A docs now mention learned-template reach
- whether AG-UI docs now mention budget behavior and omitted-default behavior accurately
- what `status_after_plan.md` records
- any intentionally deferred items left for a future wave
