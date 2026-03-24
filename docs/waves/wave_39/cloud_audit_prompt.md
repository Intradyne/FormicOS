Working directory:
`C:\Users\User\FormicOSa`

Primary docs to audit:
- `docs/waves/wave_39/wave_39_plan.md`
- `docs/waves/wave_39/acceptance_gates.md`
- `docs/waves/wave_39/coder_prompt_team_1.md`
- `docs/waves/wave_39/coder_prompt_team_2.md`
- `docs/waves/wave_39/coder_prompt_team_3.md`
- `docs/waves/session_decisions_2026_03_19.md`

Your job:
- do a seam-focused audit, not a rewrite
- use current repo truth
- identify stale assumptions, ownership mismatches, overclaims, hidden contract
  expansions, or places where replay-truth is being overclaimed
- prefer small, concrete corrections over philosophical rewrites

Important repo truth:

1. Wave 38 is accepted or at final acceptance stage with its escalation-matrix
   truth issue fixed.
2. The current event union is 55. Wave 39 intentionally grows it to 58 through
   exactly three new event families and no more.
3. `routing_override` is the current capability-escalation seam. Provider
   fallback is a different system.
4. Colony knowledge accesses, directives, and planning traces already exist in
   projection state.
5. The current round and turn events do **not** preserve exact runtime
   `knowledge_prior` or exact retrieval-ranking snapshots.
6. Wave 39's operator actions are intended to be local-first editorial
   overlays, not automatic confidence mutations.
7. `frontend/src/components/colony-detail.ts`,
   `frontend/src/components/queen-overview.ts`,
   `frontend/src/components/proactive-briefing.ts`,
   `frontend/src/components/workflow-view.ts`, and
   `frontend/src/components/knowledge-browser.ts` already exist and are the
   natural Wave 39 UI seams.

Read at minimum:

- `src/formicos/engine/runner.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/surface/colony_manager.py`
- `src/formicos/surface/proactive_intelligence.py`
- `src/formicos/surface/queen_runtime.py`
- `src/formicos/core/events.py`
- `frontend/src/components/colony-detail.ts`
- `frontend/src/components/queen-overview.ts`
- `frontend/src/components/workflow-view.ts`
- `frontend/src/components/knowledge-browser.ts`

Audit goals:

1. Verify the Wave 39 plan is grounded against current repo truth.
2. Verify the acceptance gates protect the real Wave 39 thesis.
3. Verify the packet does **not** accidentally conflate:
   - local editorial overlays
   - shared epistemic confidence truth
4. Verify the packet does **not** promise exact audit history where current
   repo truth only supports reconstructed explanation.
5. Verify the coder prompts keep auto-escalation on the governance-owned
   `routing_override` path and keep provider fallback separate.
6. Verify Team 2's event expansion is narrow, reversible, and local-first.
7. Verify Team 3 owns pre-spawn configuration editing UI and does not create a
   second hidden override path.
8. Flag only real remaining issues.

What to return:

1. Findings first, ordered by severity
2. Then:
   - whether the Wave 39 packet is planning-ready
   - whether the acceptance gates are sufficient
   - whether any claims currently overreach repo truth
3. If not fully ready, give the smallest blocker list only

What not to do:

- do not rewrite Wave 39 into Wave 40
- do not relitigate Wave 38 acceptance
- do not casually propose more event families
- do not turn the audit into a product-strategy essay
