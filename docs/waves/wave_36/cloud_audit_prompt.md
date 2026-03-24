You are auditing the final Wave 36 planning packet for FormicOS.

Working directory:
C:\Users\User\FormicOSa

Primary docs to audit:
- `docs/waves/wave_36/wave_36_plan.md`
- `docs/decisions/047-outcome-metrics-retention.md`
- `docs/waves/wave_36/coder_prompt_team_1.md`
- `docs/waves/wave_36/coder_prompt_team_2.md`
- `docs/waves/wave_36/coder_prompt_team_3.md`

Your job:
- do a seam-focused audit, not a rewrite
- use current repo truth
- identify any remaining stale assumptions, ownership mismatches, or prompt gaps
- prefer small, concrete corrections over philosophical rewrites

Important repo truth:
1. Wave 35.5 landed and was accepted with follow-up debt.
2. That debt is now explicitly absorbed into Wave 36 A0:
   - `runningColonies` wiring at the Queen-chat mount points
   - `@send-colony-message` forwarding through the `fc-queen-overview` mount
   - maintenance posture consumption from replay-derived outcome data
3. `MaintenanceDispatcher` lives in `src/formicos/surface/self_maintenance.py`
4. `queen-overview.ts` and `routes/api.py` are shared seams between Tracks A and B
5. `ColonyOutcome` is already replay-derived in `src/formicos/surface/projections.py`
6. Wave 36 must not add a new event family; union stays at 55

Audit goals:
1. Verify the plan is grounded against real code and real post-35.5 state
2. Verify ADR-047 is correctly scoped and consistent with the Wave 36 plan
3. Verify the coder prompts:
   - have realistic ownership
   - respect overlap seams
   - do not miss obvious integration blockers
   - do not widen beyond Wave 36 scope
4. Flag only real remaining issues

Read at minimum:
- `frontend/src/components/formicos-app.ts`
- `frontend/src/components/queen-overview.ts`
- `frontend/src/components/queen-chat.ts`
- `frontend/src/components/colony-detail.ts`
- `frontend/src/components/workflow-view.ts`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/proactive_intelligence.py`
- `src/formicos/surface/self_maintenance.py`
- `src/formicos/surface/queen_runtime.py`
- `src/formicos/surface/routes/api.py`
- `README.md`
- `docs/OPERATORS_GUIDE.md`

What to return:
1. Findings first, ordered by severity
2. Then:
   - whether the plan is dispatch-ready
   - whether ADR-047 is appropriately scoped
   - whether the coder prompts are ready to send with minimal edits
3. If not fully ready, give the smallest blocker list only

What not to do:
- do not relitigate Wave 35.5
- do not suggest a new wave before Wave 36
- do not expand Wave 36 into Wave 37 experimentation work
- do not re-polish startup docs or already-resolved stale vocabulary issues
