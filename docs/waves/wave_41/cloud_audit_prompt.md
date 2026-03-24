Working directory:
`C:\Users\User\FormicOSa`

Primary docs to audit:

- `docs/waves/wave_41/wave_41_plan.md`
- `docs/waves/wave_41/acceptance_gates.md`
- `docs/waves/wave_41/coder_prompt_team_1.md`
- `docs/waves/wave_41/coder_prompt_team_2.md`
- `docs/waves/wave_41/coder_prompt_team_3.md`
- `docs/waves/session_decisions_2026_03_19.md`

Your job:

- do a seam-focused audit, not a rewrite
- use current repo truth, not roadmap memory
- identify stale assumptions, ownership mismatches, overclaims, hidden contract
  expansions, or places where benchmark framing is quietly replacing product
  framing
- prefer small, concrete corrections over philosophical rewrites

Important repo truth:

1. Wave 40 has landed cleanly enough to start Wave 41. All 2517 tests passed in
   the final reported Wave 40 state.
2. `src/formicos/engine/runner.py` has already been split down materially and
   `src/formicos/engine/tool_dispatch.py` now exists.
3. `src/formicos/adapters/sandbox_manager.py` is still a relatively small,
   Python-oriented seam and is not yet a full repo-execution substrate.
4. `src/formicos/surface/trust.py` still contains the live asymmetry between
   rich `PeerTrust` posteriors and coarse retrieval penalties / hop discount.
5. `src/formicos/surface/knowledge_catalog.py` already uses Thompson-style
   sampling in its live scoring path.
6. `src/formicos/engine/context.py` still uses a UCB-style exploration bonus.
7. `src/formicos/surface/conflict_resolution.py` exists, but contradiction
   detection / handling is still split in practice across additional surfaces
   such as `maintenance.py` and `proactive_intelligence.py`.
8. Wave 41 is not intended to add a benchmark-specific core path.
9. The compounding curve is the key output of Wave 41, but the product identity
   remains: FormicOS is an editable shared brain, not a benchmark runner.
10. No event expansion is preferred in Wave 41 unless a real replay blocker is
    discovered.

Read at minimum:

- `src/formicos/surface/trust.py`
- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/engine/context.py`
- `src/formicos/surface/conflict_resolution.py`
- `src/formicos/surface/maintenance.py`
- `src/formicos/surface/proactive_intelligence.py`
- `src/formicos/adapters/sandbox_manager.py`
- `src/formicos/engine/tool_dispatch.py`
- `src/formicos/engine/runner.py`
- `src/formicos/surface/colony_manager.py`
- `src/formicos/surface/queen_runtime.py`
- `tests/benchmark/profiling_harness.py`
- `tests/benchmark/*`

Audit goals:

1. Verify the Wave 41 packet is grounded against current repo truth.
2. Verify the acceptance gates protect capability-building rather than
   benchmark drift.
3. Verify Team 1's contradiction scope is staged realistically and does not
   overpromise full math replacement in one wave.
4. Verify Team 2 strengthens real execution and multi-file capability without
   inventing benchmark-only tooling or a second execution path.
5. Verify Team 3's measurement plan is credible, locked, and useful even if the
   compounding curve stays flat.
6. Verify file ownership and overlap rules are realistic.
7. Flag only real remaining issues.

What to return:

1. Findings first, ordered by severity
2. Then:
   - whether the Wave 41 packet is dispatch-ready
   - whether the acceptance gates are sufficient
   - whether any claims currently overreach repo truth
3. If not fully ready, give the smallest blocker list only

What not to do:

- do not rewrite Wave 41 into Wave 42
- do not relitigate Wave 40 acceptance
- do not turn the audit into a product-strategy essay
- do not casually propose event expansion
- do not assume the benchmark is the primary product identity
