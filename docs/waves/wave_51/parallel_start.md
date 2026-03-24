# Wave 51 Parallel Start Notes

All three teams can start immediately.

## Why This Is Parallel-Safe

### Team 1 owns backend mutation truth

Owned seams:
- `src/formicos/core/events.py`
- `src/formicos/surface/commands.py`
- `src/formicos/surface/queen_tools.py`
- `src/formicos/surface/projections.py`
- backend routes
- `docs/REPLAY_SAFETY.md`

### Team 2 owns frontend surface truth

Owned seams:
- frontend components
- `frontend/src/state/store.ts`
- no backend files

### Team 3 owns surrounding docs truth

Owned seams:
- `AGENTS.md`
- `CLAUDE.md`
- `docs/OPERATORS_GUIDE.md`
- `docs/waves/wave_51/status_after_plan.md`

Team 3 explicitly does **not** own `docs/REPLAY_SAFETY.md`, which removes the
biggest docs-overlap risk.

## Only Real Coordination Points

1. If Team 1 adds a new event type, Team 1 must update contract mirrors in the
   same track.
2. Team 1 must keep Queen notes private working context, not visible chat rows.
3. Team 3 should reread Team 1's final `docs/REPLAY_SAFETY.md` before its final
   truth-refresh pass.
4. Team 3 should reread Team 2's final label choices before finalizing docs.

## Recommended Launch Order

Start all three now:

1. Team 1 -- backend replay-safety work
2. Team 2 -- frontend visible-degradation and vocabulary work
3. Team 3 -- Phase 1 docs prep immediately, then final truth refresh after
   Teams 1 and 2 land

## Things No Team Should Reopen

- Global promotion is already landed
- Learned-template enrichment is already landed
- Streaming fallback is deferred out of Wave 51

## Success Condition

If each team stays inside its owned files, Wave 51 can be run as a true
parallel pass rather than a serialized cleanup wave.
