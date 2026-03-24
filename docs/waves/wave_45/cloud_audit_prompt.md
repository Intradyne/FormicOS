Working directory: `c:\Users\User\FormicOSa`

Audit the Wave 45 packet against the live repo. This is a seam-focused audit,
not a rewrite exercise.

Primary docs to audit:

- [wave_45_plan.md](/c:/Users/User/FormicOSa/docs/waves/wave_45/wave_45_plan.md)
- [acceptance_gates.md](/c:/Users/User/FormicOSa/docs/waves/wave_45/acceptance_gates.md)
- [coder_prompt_team_1.md](/c:/Users/User/FormicOSa/docs/waves/wave_45/coder_prompt_team_1.md)
- [coder_prompt_team_2.md](/c:/Users/User/FormicOSa/docs/waves/wave_45/coder_prompt_team_2.md)
- [coder_prompt_team_3.md](/c:/Users/User/FormicOSa/docs/waves/wave_45/coder_prompt_team_3.md)
- [session_decisions_2026_03_19.md](/c:/Users/User/FormicOSa/docs/waves/session_decisions_2026_03_19.md)

Important repo truth to keep in mind:

- Wave 44 is accepted.
- Level 2 fetch fallback, pre-fetch relevance filtering, VCR recorded
  fixtures, and property-based replay tests are already shipped and should not
  be reintroduced as Wave 45 scope.
- `ForagerService` already owns the reactive service loop.
- `proactive_intelligence.py` already has the relevant insight rules and
  `suggested_colony` patterns, but does not yet trigger foraging.
- `conflict_resolution.py` already has Stage 3 `Resolution.competing`, but the
  result is not yet surfaced in projections/retrieval.
- `web_search.py` already accepts an injected `http_client`.
- `_compute_structural_affinity()` is still colony-level today.
- Wave 45 must add no new event types and no new subsystem.

Read at minimum:

- [proactive_intelligence.py](/c:/Users/User/FormicOSa/src/formicos/surface/proactive_intelligence.py)
- [self_maintenance.py](/c:/Users/User/FormicOSa/src/formicos/surface/self_maintenance.py)
- [forager.py](/c:/Users/User/FormicOSa/src/formicos/surface/forager.py)
- [content_quality.py](/c:/Users/User/FormicOSa/src/formicos/adapters/content_quality.py)
- [app.py](/c:/Users/User/FormicOSa/src/formicos/surface/app.py)
- [conflict_resolution.py](/c:/Users/User/FormicOSa/src/formicos/surface/conflict_resolution.py)
- [projections.py](/c:/Users/User/FormicOSa/src/formicos/surface/projections.py)
- [knowledge_catalog.py](/c:/Users/User/FormicOSa/src/formicos/surface/knowledge_catalog.py)
- [runner.py](/c:/Users/User/FormicOSa/src/formicos/engine/runner.py)
- [queen_tools.py](/c:/Users/User/FormicOSa/src/formicos/surface/queen_tools.py)

Audit goals:

1. Verify the packet stayed smaller after removing already-shipped items.
2. Check that proactive foraging is framed as a bounded signal/dispatcher
   upgrade, not a new subsystem.
3. Check that source credibility is treated as a provenance/admission signal,
   not as a replacement for content quality.
4. Check that Stage 3 contradiction surfacing stays projection/retrieval
   scoped and does not drift into event or frontend sprawl.
5. Check that the agent-level topology item is truly gated on existing data
   truth.
6. Check that no shared-file merge traps were introduced across the three
   teams.
7. Flag only real blockers, misleading assumptions, or scope mistakes.

Return format:

- findings first, ordered by severity
- then a short dispatch verdict
- then the smallest set of fixes needed before dispatch, if any

What not to do:

- do not relitigate Waves 43-44 acceptance
- do not casually add new event types
- do not turn this into Wave 46 measurement planning
- do not suggest a new foraging/search subsystem unless a real blocker demands it
