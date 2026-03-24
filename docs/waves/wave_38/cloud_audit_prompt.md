You are auditing the Wave 38 planning packet for FormicOS.

Working directory:
C:\Users\User\FormicOSa

Primary docs to audit:
- `docs/waves/wave_38/wave_38_plan.md`
- `docs/waves/wave_38/acceptance_gates.md`
- `docs/waves/wave_38/coder_prompt_team_1.md`
- `docs/waves/wave_38/coder_prompt_team_2.md`
- `docs/waves/wave_38/coder_prompt_team_3.md`
- `docs/waves/session_decisions_2026_03_19.md`
- `docs/research/stigmergy_knowledge_substrate_research.md`

Your job:
- do a seam-focused audit, not a rewrite
- use current repo truth
- identify stale assumptions, ownership mismatches, overclaims, or hidden
  contract expansions
- prefer small, concrete corrections over philosophical rewrites

Important repo truth:
1. Wave 37 is accepted.
2. The event union remains at 55 and should stay closed unless a narrow ADR
   justification is truly required.
3. Inbound A2A already exists at:
   - `src/formicos/surface/routes/a2a.py`
4. The Agent Card already exists at:
   - `src/formicos/surface/routes/protocols.py`
5. `query_service` already exists and routes through:
   - `src/formicos/engine/service_router.py`
   - `src/formicos/surface/queen_tools.py`
6. `routing_override` already exists and is the governance-owned capability
   escalation seam. Provider fallback is a different system.
7. Wave 37 already left behind:
   - benchmark harness in `tests/integration/test_wave37_stigmergic_loop.py`
   - admission seam in `src/formicos/surface/admission.py`
8. The knowledge graph adapter already has temporal edge fields:
   - `valid_at`
   - `invalid_at`
9. Model-level external agent wrapping through `LLMPort` is intentionally not
   the default Wave 38 path.

Read at minimum:
- `src/formicos/surface/routes/a2a.py`
- `src/formicos/surface/routes/protocols.py`
- `src/formicos/engine/service_router.py`
- `src/formicos/surface/queen_tools.py`
- `src/formicos/surface/admission.py`
- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/surface/projections.py`
- `src/formicos/adapters/knowledge_graph.py`
- `tests/integration/test_wave37_stigmergic_loop.py`

Audit goals:
1. Verify the Wave 38 plan is grounded against current repo state
2. Verify the acceptance gates match the plan and protect the real thesis
3. Verify the plan does not accidentally conflate:
   - provider fallback
   - capability escalation
4. Verify the A2A/NemoClaw sections do not pretend FormicOS is starting from
   zero on protocol surfaces
5. Verify the bi-temporal plan is honest about current temporal seams and does
   not smuggle in a casual core contract change
6. Verify the coder prompts:
   - preserve Pattern 1 vs Pattern 2 correctly
   - keep provider fallback and capability escalation separate
   - do not overclaim fully temporalized memory truth
   - keep overlap seams realistic
7. Flag only real remaining issues

What to return:
1. Findings first, ordered by severity
2. Then:
   - whether the Wave 38 packet is planning-ready
   - whether the acceptance gates are sufficient
   - whether any claims currently overreach repo truth
3. If not fully ready, give the smallest blocker list only

What not to do:
- do not rewrite Wave 38 into Wave 39
- do not relitigate Wave 37 acceptance
- do not propose new event families casually
- do not turn the audit into a benchmark or product strategy essay
