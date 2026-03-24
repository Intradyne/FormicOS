You own the Wave 51 surface-truth and visible-degradation track.

This is the operator-surface pass. You are not inventing backend capability,
and you are not reopening Wave 50 substrate that is already landed. Your job is
to make the shipped surface honest: unavailable data should look unavailable,
dead code should disappear, misleading labels should stop leaking, and visible
capabilities should actually be reachable.

## Mission

Land the frontend-heavy parts of Wave 51:

1. config-memory unavailable states
2. Queen overview no-data / unavailable states
3. model/protocol freshness visibility
4. proactive briefing domain override actions
5. inert settings strategy pills
6. remove dead `fleet-view.ts`
7. operator-facing "Knowledge" / "Configuration" vocabulary cleanup

The core rule still applies:

**If the benchmark disappeared tomorrow, would we still want this change in
FormicOS?**

Yes. Operators want a surface that tells the truth, not one that requires
insider interpretation.

## Read First

1. `AGENTS.md`
2. `CLAUDE.md`
3. `docs/waves/wave_51/wave_51_plan.md`
4. `docs/waves/wave_51/acceptance_gates.md`
5. `docs/waves/wave_51/ui_audit_findings.md`
6. `docs/waves/wave_51/ui_seam_map.md`
7. `docs/waves/wave_50/status_after_plan.md`
8. `frontend/src/components/config-memory.ts`
9. `frontend/src/components/queen-overview.ts`
10. `frontend/src/components/proactive-briefing.ts`
11. `frontend/src/components/settings-view.ts`
12. `frontend/src/components/formicos-app.ts`
13. `frontend/src/components/model-registry.ts`
14. `frontend/src/components/fleet-view.ts`
15. `frontend/src/state/store.ts`

Before editing, re-verify these truths in code:

- global promotion is already landed and should NOT be hidden or marked planned
- learned-template enrichment is already landed and should NOT be relabeled as future
- config-memory still has silent fetch failure paths
- Queen overview still hides unavailable sections
- strategy pills still look interactive
- `fleet-view.ts` is still dead

## Owned Files

- `frontend/src/components/config-memory.ts`
- `frontend/src/components/queen-overview.ts`
- `frontend/src/components/proactive-briefing.ts`
- `frontend/src/components/settings-view.ts`
- `frontend/src/components/formicos-app.ts`
- `frontend/src/components/model-registry.ts`
- `frontend/src/components/fleet-view.ts`
- `frontend/src/state/store.ts`
- targeted frontend/UI tests if you add them

## Do Not Touch

- backend Python files
- `src/formicos/core/events.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/routes/*`
- `frontend/src/types.ts`
- `docs/REPLAY_SAFETY.md`
- `AGENTS.md`
- `CLAUDE.md`
- Wave 51 packet docs

Team 1 owns backend truth. Team 3 owns general docs truth.

## Parallel-Safe Coordination Rules

1. Do not invent backend fields, events, or routes from the frontend.
2. Build against current landed backend truth, not the earlier stale audit findings.
3. If you think you need a backend contract change, stop and report it rather
   than editing Team 1 files.
4. You can start immediately; none of your required work depends on Team 1
   landing a new field first.

## Required Work

### Track B1: Config-memory unavailable states

Current truth:
- multiple fetches can fail independently
- failed sections silently disappear into partial data

Required outcome:
- a failed section renders a muted unavailable state
- partial data no longer looks like complete data

Do not rebuild the view. Patch the current sections honestly.

### Track B2: Queen overview no-data / unavailable states

Current truth:
- federation and outcomes sections can vanish on failure

Required outcome:
- render explicit no-data / unavailable placeholders instead of silent absence

### Track B3: Model / protocol freshness

Current truth:
- model/protocol state is snapshot-heavy

Required outcome:
- the operator can see freshness truth directly

Implementation preference:
1. if cheap, add a small periodic refresh
2. regardless, surface "last updated" / stale state visibly

Keep this bounded. Do not invent a new event system for freshness.

### Track A7: Proactive briefing domain override actions

Current truth:
- trust state is visible
- the inline action path is missing
- the backend endpoint already exists

Required outcome:
- trust / distrust / reset actions are reachable from the briefing surface

Use the existing REST endpoint. Do not invent a new action path.

### Track C9: Strategy pills must look inert

Required outcome:
- remove false affordance
- no hover/click styling that implies configurability

### Track C1: Remove `fleet-view.ts`

Required outcome:
- delete dead code unless you discover a real live reference

Do not resurrect it just to avoid deleting it.

### Track C2/C3: Vocabulary cleanup

Required outcome:
- operator-facing labels should say "Knowledge" instead of legacy "Skill Bank"
- "Config Memory" should be renamed to a clearer operator-facing label

Important boundary:
- do not rename the underlying wire/store contract fields if they are
  replay-sensitive or shared with backend state

### Preserve landed Wave 50 truth

Do NOT:
- hide global promotion
- relabel learned templates as unshipped
- add "planned" treatment to already-landed substrate

## Hard Constraints

- No backend edits
- No frontend contract/type edits in `frontend/src/types.ts`
- No UI-only fabrication of backend state
- No visual redesign detached from seam truth
- Keep the wave subtractive: hide, show, rename, delete, clarify

## Validation

Run at minimum:

1. `cd frontend; npm run build`
2. `rg -n "Skill Bank|Config Memory" frontend/src`
3. any targeted UI tests you add for the changed surfaces

If you touch model/protocol freshness with polling, note exactly what refresh
path you chose and why it stayed bounded.

## Summary Must Include

- how config-memory now distinguishes unavailable from no data
- how Queen overview now explains missing sections
- whether you added freshness visibility only or freshness visibility plus polling
- how proactive briefing domain overrides are now reachable
- confirmation that global promotion and learned-template UI were not regressed
- what dead/stale surface artifacts were removed
