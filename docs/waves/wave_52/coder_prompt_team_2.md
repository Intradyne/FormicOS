You own the Wave 52 frontend protocol-truth track.

This is the only track allowed to touch frontend protocol/status presentation
for Wave 52. Your job is to remove stale fallback protocol language and make
the UI describe the live control plane honestly without redesigning it.

## Mission

Land the frontend-heavy parts of Wave 52 Packet A:

1. remove stale fallback language for live protocols
2. normalize protocol transport/status presentation
3. make settings/topbar surfaces derive from live truth instead of old pessimistic copy

This is a truth-alignment pass, not a redesign pass.

## Read First

1. `AGENTS.md`
2. `CLAUDE.md`
3. `docs/waves/wave_52/wave_52_plan.md`
4. `docs/waves/wave_52/acceptance_gates.md`
5. `docs/waves/wave_52/capability_control_inventory.md`
6. `docs/waves/wave_52/control_plane_seam_map.md`
7. `docs/waves/wave_52/control_plane_findings.md`
8. `frontend/src/components/settings-view.ts`
9. `frontend/src/components/formicos-app.ts`
10. `frontend/src/state/store.ts`

Before editing, re-verify these truths:

- AG-UI is live and should not be described as `Not implemented`
- A2A is live and should not be described as `Agent Card discovery only`
- transport naming still drifts between frontend and backend
- some fallback counts/statuses remain hardcoded today

## Owned Files

- `frontend/src/components/settings-view.ts`
- `frontend/src/components/formicos-app.ts`
- `frontend/src/state/store.ts` only if strictly needed for protocol status shape

## Do Not Touch

- backend Python files
- `AGENTS.md`
- `CLAUDE.md`
- protocol docs under `docs/`
- ADR files
- Wave 52 audit docs

Team 1 owns backend/control-plane behavior. Team 3 owns docs/ADR truth.

## Parallel-Safe Coordination Rules

1. Do not assume a new backend field will appear unless Team 1 actually lands it.
2. Prefer consuming already-live protocol status truth over adding new frontend constants.
3. If Team 1 does not change a backend status field, keep your cleanup within
   text/derivation/presentation bounds.

## Required Work

### Track A4: Transport naming normalization

Required outcome:
- frontend uses the same human-facing transport naming as the live backend truth

### Track A5: Dead fallback text cleanup

Required outcome:
- live protocols are no longer described as `Not implemented`, `planned`, or
  `Agent Card discovery only`
- UI uses real status where possible

### Track A2/A6 support if needed

If a stale count or protocol description is directly embedded in these frontend
files, fix it while you are in scope.

Do not turn this into a broader frontend pass.

## Hard Constraints

- No backend changes
- No broad restyling
- No new UI surfaces
- No protocol redesign
- No expansion work

## Validation

Run at minimum:

1. `cd frontend; npm run build`
2. any targeted frontend tests you add
3. verify that stale strings for live protocols are gone from owned files

## Summary Must Include

- which stale fallback texts were removed
- how transport naming was normalized
- whether `store.ts` needed changes or not
- confirmation that no backend files were touched
- what you deliberately left alone to stay bounded
