Working directory: `c:\Users\User\FormicOSa`

Audit the Wave 44 packet against the live repo. This is a seam-focused audit,
not a rewrite exercise.

Primary docs to audit:

- [wave_44_plan.md](/c:/Users/User/FormicOSa/docs/waves/wave_44/wave_44_plan.md)
- [acceptance_gates.md](/c:/Users/User/FormicOSa/docs/waves/wave_44/acceptance_gates.md)
- [coder_prompt_team_1.md](/c:/Users/User/FormicOSa/docs/waves/wave_44/coder_prompt_team_1.md)
- [coder_prompt_team_2.md](/c:/Users/User/FormicOSa/docs/waves/wave_44/coder_prompt_team_2.md)
- [coder_prompt_team_3.md](/c:/Users/User/FormicOSa/docs/waves/wave_44/coder_prompt_team_3.md)
- [session_decisions_2026_03_19.md](/c:/Users/User/FormicOSa/docs/waves/session_decisions_2026_03_19.md)

Important repo truth to keep in mind:

- Wave 43 is accepted.
- `httpx` already exists in [pyproject.toml](/c:/Users/User/FormicOSa/pyproject.toml),
  but there is no live `EgressGateway`, fetch pipeline, search adapter,
  `forager.py`, or forager-specific event surface in `src/`.
- `trafilatura`, `readability-lxml`, and browser tooling are not currently
  present as dependencies.
- [proactive_intelligence.py](/c:/Users/User/FormicOSa/src/formicos/surface/proactive_intelligence.py)
  already has 14 deterministic insight rules.
- [admission.py](/c:/Users/User/FormicOSa/src/formicos/surface/admission.py)
  already has the seven admission dimensions that should remain the gate.
- [events.py](/c:/Users/User/FormicOSa/src/formicos/core/events.py#L685)
  already has `MemoryEntryCreated`, which should be reused for admitted
  forager entries.
- The packet intentionally adds **4** new event types, not 5+.
- The retrieval path should detect low-confidence gaps and hand off to
  foraging. It should **not** do network I/O inline.
- Query formation in v1 should be deterministic.
- Egress in v1 should only allow fetches for search-result URLs plus explicit
  operator overrides.
- Wave 44 is a Forager foundation wave, not the full research architecture.

Read at minimum:

- [pyproject.toml](/c:/Users/User/FormicOSa/pyproject.toml)
- [events.py](/c:/Users/User/FormicOSa/src/formicos/core/events.py)
- [types.py](/c:/Users/User/FormicOSa/src/formicos/core/types.py)
- [admission.py](/c:/Users/User/FormicOSa/src/formicos/surface/admission.py)
- [knowledge_catalog.py](/c:/Users/User/FormicOSa/src/formicos/surface/knowledge_catalog.py)
- [proactive_intelligence.py](/c:/Users/User/FormicOSa/src/formicos/surface/proactive_intelligence.py)
- [projections.py](/c:/Users/User/FormicOSa/src/formicos/surface/projections.py)
- [tool_dispatch.py](/c:/Users/User/FormicOSa/src/formicos/engine/tool_dispatch.py)
- [caste_recipes.yaml](/c:/Users/User/FormicOSa/config/caste_recipes.yaml)
- [KNOWLEDGE_LIFECYCLE.md](/c:/Users/User/FormicOSa/docs/KNOWLEDGE_LIFECYCLE.md)
- [OPERATORS_GUIDE.md](/c:/Users/User/FormicOSa/docs/OPERATORS_GUIDE.md)

Audit goals:

1. Verify the packet is grounded in the actual missing Wave 44 substrate.
2. Check that the event expansion stays minimal and justified.
3. Check that `MemoryEntryCreated` reuse is explicit and correct.
4. Check that Team 2 is told to keep retrieval free of inline web I/O.
5. Check that deterministic query templates are treated as v1 truth.
6. Check that strict egress is framed as a real hard constraint.
7. Check overlap boundaries, especially:
   - Team 1 vs Team 2 around adapters vs surface orchestration
   - Team 2 vs Team 3 around event emission vs event definition
   - Team 2 vs Team 3 around `knowledge_catalog.py` / projections visibility
8. Flag only real blockers, misleading assumptions, or scope mistakes.

Return format:

- findings first, ordered by severity
- then a short dispatch verdict
- then the smallest set of fixes needed before dispatch, if any

What not to do:

- do not relitigate Wave 43 acceptance
- do not turn this into Wave 45 methodology planning
- do not casually expand the event surface beyond the packet
- do not assume a live web-search or egress substrate already exists
- do not suggest broad browser/crawling architecture unless a real blocker
  demands it
