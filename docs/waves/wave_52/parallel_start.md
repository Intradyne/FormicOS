# Wave 52 Parallel Start Notes

All three teams can start immediately.

## Why This Is Parallel-Safe

### Team 1 owns backend coherence and intelligence reach

Owned seams:
- `src/formicos/__init__.py`
- `src/formicos/surface/app.py`
- `src/formicos/surface/routes/protocols.py`
- `src/formicos/surface/routes/a2a.py`
- `src/formicos/surface/agui_endpoint.py`
- `src/formicos/surface/proactive_intelligence.py`
- `src/formicos/surface/queen_runtime.py`
- `src/formicos/surface/queen_tools.py` only if a tiny Queen retrieval piggyback stays bounded

### Team 2 owns frontend protocol truth

Owned seams:
- `frontend/src/components/settings-view.ts`
- `frontend/src/components/formicos-app.ts`
- `frontend/src/state/store.ts` only if needed

### Team 3 owns docs and ADR truth

Owned seams:
- `AGENTS.md`
- `CLAUDE.md`
- `docs/A2A-TASKS.md`
- `docs/AG-UI-EVENTS.md`
- ADRs 045/046/047
- `docs/waves/wave_52/status_after_plan.md`

No shared file is jointly owned. That is what makes the launch parallel-safe.

## Only Real Coordination Points

1. If Team 1 changes A2A selection metadata, Team 3 must reread that before finalizing docs.
2. If Team 1 changes AG-UI omitted-default behavior, Team 3 must document the final truth, not the planned truth.
3. If Team 1 needs a tiny protocol status shape change for Team 2, keep it additive and report it clearly.
4. Team 3 should finish last, but it should start now on Phase 1 prep.

## Recommended Launch Order

Start all three now:

1. Team 1 -- backend coherence + intelligence reach
2. Team 2 -- frontend protocol truth cleanup
3. Team 3 -- Phase 1 docs/ADR prep immediately, then final truth refresh after
   Teams 1 and 2 land

## Things No Team Should Reopen

- No AG-UI Tier 2 work
- No full A2A conformance push
- No token streaming work
- No MCP expansion
- No new event types
- No new subsystem work
- No measurement redesign inside Wave 52

## Packet Discipline

### Packet A

Description truth only:
- version
- event count
- ADR status
- transport/status text
- stale docs claims

### Packet B

Wiring and visible learning only:
- Queen tool-result hygiene parity
- thread-aware Queen retrieval
- A2A learned-template reach
- external budget truth and any bounded spawn-gate parity
- AG-UI omitted-default improvement if bounded
- learned-template briefing visibility
- recent outcome digest

Do not blur these packets into a vague "improve everything" wave.

## Success Condition

Wave 52 can run as a true parallel pass if:
- Team 1 stays in backend files
- Team 2 stays in frontend protocol/status files
- Team 3 stays in docs/ADR files
- Team 3 performs the final truth-refresh pass last
