Working directory:
`C:\Users\User\FormicOSa`

Primary docs to audit:

- `docs/waves/wave_42/wave_42_plan.md`
- `docs/waves/wave_42/acceptance_gates.md`
- `docs/waves/wave_42/coder_prompt_team_1.md`
- `docs/waves/wave_42/coder_prompt_team_2.md`
- `docs/waves/wave_42/coder_prompt_team_3.md`
- `docs/waves/session_decisions_2026_03_19.md`

Your job:

- do a seam-focused audit, not a rewrite
- use current repo truth, not roadmap memory
- identify stale assumptions, ownership mismatches, overclaims, hidden contract
  expansions, or places where the draft is importing more research complexity
  than the current substrate can support
- prefer small, concrete corrections over philosophical rewrites

Important repo truth:

1. Wave 41 is treated as accepted for this packet.
2. Static workspace/code analysis does not yet exist as a first-class adapter.
   There is no `src/formicos/adapters/code_analysis.py` today.
3. `_compute_knowledge_prior()` in `src/formicos/engine/runner.py` still uses
   a domain-overlap heuristic and is the clearest remaining weak topology seam.
4. `classify_pair()` / `detect_contradictions()` now exist in
   `src/formicos/surface/conflict_resolution.py`, but `resolve_conflict()`
   still uses the older linear scorer.
5. `_EVAPORATE = 0.95` is still fixed in `src/formicos/engine/runner.py`.
6. `src/formicos/surface/colony_manager.py` already contains the extraction and
   confidence-update hooks that Wave 42 will build on.
7. Wave 42 is a build wave, not a public measurement wave.
8. No event expansion is preferred unless a real replay blocker is discovered.
9. The tightened guidance for this wave is:
   - operate on the workspace tree, not an assumed repo-clone abstraction
   - keep structural topology prior v1 simple
   - make contradiction Stage 2 Must and Stage 3 optional
   - keep adaptive evaporation runtime-local
   - use conjunctive extraction quality gates

Read at minimum:

- `src/formicos/engine/runner.py`
- `src/formicos/surface/conflict_resolution.py`
- `src/formicos/surface/colony_manager.py`
- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/surface/proactive_intelligence.py`
- `src/formicos/surface/admission.py`
- `src/formicos/adapters/sandbox_manager.py`

Audit goals:

1. Verify the Wave 42 packet is grounded in the actual post-Wave-41 substrate.
2. Verify the acceptance gates protect a build-wave thesis rather than hidden
   measurement drift.
3. Verify Team 1's static-analysis and topology work stays simple-first.
4. Verify Team 2's contradiction scope is staged realistically and does not
   imply a full knowledge-model rewrite.
5. Verify Team 3's adaptive-evaporation work stays runtime-local.
6. Verify overlap ownership, especially in `colony_manager.py` and `runner.py`.
7. Flag only real remaining issues.

What to return:

1. Findings first, ordered by severity
2. Then:
   - whether the Wave 42 packet is dispatch-ready
   - whether the acceptance gates are sufficient
   - whether any claims currently overreach repo truth
3. If not fully ready, give the smallest blocker list only

What not to do:

- do not rewrite Wave 42 into Wave 43
- do not relitigate Wave 41 acceptance
- do not turn the audit into a product-strategy essay
- do not casually propose new event expansion
- do not assume this wave should be a public measurement or benchmark wave
