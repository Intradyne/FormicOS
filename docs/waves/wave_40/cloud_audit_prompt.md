Working directory:
`C:\Users\User\FormicOSa`

Primary docs to audit:

- `docs/waves/wave_40/wave_40_plan.md`
- `docs/waves/wave_40/acceptance_gates.md`
- `docs/waves/wave_40/coder_prompt_team_1.md`
- `docs/waves/wave_40/coder_prompt_team_2.md`
- `docs/waves/wave_40/coder_prompt_team_3.md`
- `docs/waves/session_decisions_2026_03_19.md`

Your job:

- do a seam-focused audit, not a rewrite
- use current repo truth, not roadmap memory
- identify stale assumptions, ownership mismatches, overclaims, hidden contract
  expansions, or places where protocol / replay truth is being overclaimed
- prefer small, concrete corrections over philosophical rewrites

Important repo truth:

1. Wave 39 has landed. Validator truth is replay-safe through
   `RoundCompleted`. Config overrides are durable through event-backed paths.
2. The current event union is 58. Wave 40 is not intended to expand it.
3. Current high-traffic file sizes are:
   - `src/formicos/engine/runner.py` - 2314
   - `src/formicos/surface/queen_tools.py` - 1885
   - `src/formicos/surface/projections.py` - 1655
   - `src/formicos/surface/proactive_intelligence.py` - 1623
   - `src/formicos/surface/colony_manager.py` - 1575
   - `src/formicos/surface/runtime.py` - 1315
   - `src/formicos/core/events.py` - 1358
   - `src/formicos/surface/knowledge_catalog.py` - 908
4. Current frontend hotspots are:
   - `frontend/src/components/colony-detail.ts` - 1010
   - `frontend/src/components/knowledge-browser.ts` - 845
   - `frontend/src/components/formicos-app.ts` - 622
   - `frontend/src/components/queen-overview.ts` - 561
   - `frontend/src/components/workflow-view.ts` - 439
5. Current test shape is:
   - `tests/unit` - 135
   - `tests/unit/surface` - 92
   - `tests/integration` - 14
   - `tests/browser` - 1
6. `src/formicos/surface/routes/a2a.py` already implements a colony-backed
   REST task lifecycle where `task_id == colony_id` and there is no second
   store.
7. `src/formicos/surface/routes/protocols.py` already advertises that surface
   honestly as custom colony-backed REST rather than full Google A2A JSON-RPC.
8. `docs/A2A-TASKS.md` already documents the current REST task lifecycle
   honestly.
9. Wave 39.25 already landed a partial docs truth pass across `README.md`,
   `CLAUDE.md`, `AGENTS.md`, `docs/OPERATORS_GUIDE.md`,
   `docs/KNOWLEDGE_LIFECYCLE.md`, and `docs/decisions/INDEX.md`.
10. A spot scan of `src/formicos/surface` and `src/formicos/adapters` did not
    find obvious plain `"Error: ..."` return debt, so Wave 40's error work
    should be audited by boundary and contract rather than by stale string-count
    claims.

Read at minimum:

- `src/formicos/engine/runner.py`
- `src/formicos/surface/colony_manager.py`
- `src/formicos/surface/queen_tools.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/proactive_intelligence.py`
- `src/formicos/surface/runtime.py`
- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/surface/routes/a2a.py`
- `src/formicos/surface/routes/protocols.py`
- `frontend/src/components/colony-detail.ts`
- `frontend/src/components/knowledge-browser.ts`
- `frontend/src/components/queen-overview.ts`
- `frontend/src/components/workflow-view.ts`

Audit goals:

1. Verify the Wave 40 packet is grounded against current repo truth.
2. Verify the acceptance gates protect the actual Wave 40 thesis:
   coherence, interaction trust, docs truth, and protocol honesty.
3. Verify the packet does **not** accidentally turn "cleanup" into hidden
   feature work.
4. Verify Team 1's profiling-first requirement is concrete enough.
5. Verify Team 2's interaction matrix covers the real riskiest seams.
6. Verify Team 3's dual-API work does **not** imply a second task store or
   second execution path.
7. Verify the plan's docs work acknowledges the partial 39.25 truth pass
   instead of pretending docs are untouched.
8. Flag only real remaining issues.

What to return:

1. Findings first, ordered by severity
2. Then:
   - whether the Wave 40 packet is dispatch-ready
   - whether the acceptance gates are sufficient
   - whether any claims currently overreach repo truth
3. If not fully ready, give the smallest blocker list only

What not to do:

- do not rewrite Wave 40 into Wave 41
- do not relitigate Wave 39 acceptance
- do not casually propose new event families
- do not turn the audit into a product-strategy essay
