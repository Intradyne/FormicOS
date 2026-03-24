You are auditing the Wave 37 planning packet for FormicOS.

Working directory:
C:\Users\User\FormicOSa

Primary docs to audit:
- `docs/waves/wave_37/wave_37_plan.md`
- `docs/waves/wave_37/acceptance_gates.md`
- `docs/research/stigmergy_knowledge_substrate_research.md`
- `docs/waves/wave_37/coder_prompt_team_1.md`
- `docs/waves/wave_37/coder_prompt_team_2.md`
- `docs/waves/wave_37/coder_prompt_team_3.md`

Your job:
- do a seam-focused audit, not a rewrite
- use current repo truth
- identify any stale assumptions, ownership mismatches, overclaims, or
  measurement gaps
- prefer small, concrete corrections over philosophical rewrites

Important repo truth:
1. Wave 36 already landed.
2. The event union remains closed at 55.
3. The active topology seam is:
   - `src/formicos/engine/strategies/stigmergic.py`
   not `engine/topology.py`
4. Existing CI already exists in:
   - `.github/workflows/ci.yml`
5. `CONTRIBUTING.md` already exists and should be treated as an existing asset,
   not a greenfield file.
6. `ColonyOutcome` is replay-derived in:
   - `src/formicos/surface/projections.py`
7. Solved coding colonies can now be truthfully classified as completed through
   the recent governance fix in:
   - `src/formicos/engine/runner.py`
8. Suggestion acceptance/rejection is not obviously a first-class event surface
   today; audit any claims about tracking it carefully.

Read at minimum:
- `src/formicos/engine/strategies/stigmergic.py`
- `src/formicos/engine/runner.py`
- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/surface/colony_manager.py`
- `src/formicos/surface/proactive_intelligence.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/queen_runtime.py`
- `.github/workflows/ci.yml`
- `CONTRIBUTING.md`

Audit goals:
1. Verify the Wave 37 plan is grounded against real code and current repo state
2. Verify the acceptance gates match the plan and do not leave critical gaps
3. Verify "no new event types" is respected by the proposed data collection and
   diagnostics
4. Verify the plan distinguishes repo-owned work from GitHub/admin-owned work
5. Verify the coder prompts:
   - have realistic ownership
   - preserve overlap seams
   - do not overclaim current event-surface capabilities
   - reflect the 1A injection seam and 1B quality-score handoff correctly
6. Flag only real remaining issues

What to return:
1. Findings first, ordered by severity
2. Then:
   - whether the plan is dispatch-ready
   - whether the acceptance gates are sufficient
   - whether any claims currently overreach current repo truth
3. If not fully ready, give the smallest blocker list only

What not to do:
- do not rewrite Wave 37 into Wave 38
- do not relitigate Wave 36
- do not suggest new event families unless absolutely necessary
- do not turn the audit into a benchmark or product strategy essay
