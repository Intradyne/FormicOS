## Role

You own the Wave 48 Team 1 backend and fresh-information track.

This is the backend/read-model and research-grounding track. You are not
rebuilding the frontend and you are not rewriting the Forager into a normal
colony worker.

## Mission

Land the backend-heavy parts of Wave 48:

1. a thread-scoped timeline API
2. richer colony-audit Forager attribution
3. truthful preview response shaping where needed
4. the Researcher's fresh-information path, with the clean mediated design
   preferred

The core rule still applies:

**If the benchmark disappeared tomorrow, would we still want this change in
FormicOS?**

Yes. Operators need audit clarity, and specialists need grounded evidence.

## Read First

1. `AGENTS.md`
2. `CLAUDE.md`
3. `docs/waves/wave_48/wave_48_plan.md`
4. `docs/waves/wave_48/acceptance_gates.md`
5. `src/formicos/surface/routes/api.py`
6. `src/formicos/surface/projections.py`
7. `src/formicos/surface/queen_tools.py`
8. `src/formicos/surface/runtime.py`
9. `src/formicos/engine/tool_dispatch.py`
10. `src/formicos/engine/runner.py`

Before editing, verify the current Forager service seam and the current
`build_colony_audit_view()` payload shape directly.

## Owned Files

- `src/formicos/surface/routes/api.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/queen_tools.py`
- `src/formicos/surface/runtime.py` only if the fresh-information path needs
  runtime wiring
- `src/formicos/engine/tool_dispatch.py`
- `src/formicos/engine/runner.py`
- targeted tests for timeline query/builders, audit enrichment, preview shape,
  and the chosen fresh-information path

## Do Not Touch

- frontend files
- `config/caste_recipes.yaml`
- docs files
- unrelated Forager pipeline internals unless they are directly required for
  bounded reuse

Team 3 owns recipes/docs. Team 2 owns the frontend/store integration.

## Required Work

### Track A: Thread Timeline API

Add a thread-scoped timeline endpoint:

`GET /api/v1/workspaces/{ws}/threads/{thread}/timeline?limit=50`

Requirements:

- thread-first, not workspace-first
- chronological output
- entries grounded in replay-safe truth
- include colony, Forager, knowledge, and operator-action rows where truthfully
  available

Keep the payload compact and expandable. This is a read-model query, not a new
event stream.

### Track B: Colony Audit Forager Enrichment

Extend `build_colony_audit_view()` so the payload can support the desired UI:

- mark knowledge used by the colony that was Forager-sourced
- include provenance fields when truthfully available:
  - source URL
  - source domain
  - Forager query
  - source credibility
- include relevant forage-cycle context only when it can be linked honestly

Important nuance:

- `ForageRequested` includes more linkage context than the current compact
  `ForageCycleSummary`
- if the existing summary drops a needed link such as `colony_id`, enrich the
  read model in a replay-safe way
- do not invent fake linkage in the frontend

Explicit seam:

- `ForageCycleSummary` in `src/formicos/surface/projections.py` currently drops
  `colony_id` and `thread_id`
- `_on_forage_cycle_completed()` still has the originating `ForageRequested`
  available through the pending-request lookup
- preserve that linkage on the replay-derived summary rather than forcing the
  frontend to guess

### Track C: Preview Response Shaping

Preview already exists on both spawn paths.

Your job is to verify whether the response shape is sufficient for the frontend
Review step. If fields are missing, add only what is needed for truthful
display:

- estimated cost
- team shape
- strategy
- fast path
- target files
- parallel-plan shape where relevant

Do not create a second preview subsystem.

### Track D: Researcher Fresh-Information Path

Wave 48 requires a truthful fresh-information path for the Researcher.

**Preferred design:** add a bounded `request_forage` tool or equivalent
synchronous Forager mediation.

Preferred behavior:

- the Researcher asks for topic/domain/context
- the request goes through the existing Forager service / policy path
- the tool returns compressed findings and provenance, not raw web content
- domain trust/distrust, credibility scoring, and egress policy stay
  centralized

Important seam guidance:

- `ServiceRouter` has two registration paths:
  - colony-backed `register()`
  - handler-backed `register_handler()`
- the Forager service is not a colony
- if you use the service-router seam, prefer `register_handler()` with a thin
  async wrapper around the live Forager service/orchestrator path
- do not try to fake the Forager into the colony-backed service registration
  path

**Fallback design:** if the mediated path is too invasive or too slow for this
wave, enable a bounded direct web path for the Researcher using the existing
tool surface and document that tradeoff honestly for Team 3.

Hard rule:

- do not ship two fuzzy overlapping web-research stories without making one the
  documented default and the other the explicit fallback

## Hard Constraints

- No new event types
- No new adapters or subsystems
- No Forager-as-normal-caste rewrite
- No benchmark-specific paths
- No frontend work in this track

## Validation

Run at minimum:

1. `python scripts/lint_imports.py`
2. targeted tests for the timeline endpoint / query builder
3. targeted tests for the colony audit payload enrichment
4. targeted tests for preview payload behavior on both spawn paths
5. targeted tests for the chosen Researcher fresh-information path

If you touch shared dispatch behavior in `runner.py`, run the relevant broader
engine slice too.

## Summary Must Include

- whether the Researcher fresh-information path landed as mediated Forager
  access or direct web fallback
- exactly what Forager provenance fields were added to colony audit
- any forage-cycle linkage limit you found and how you handled it
- whether preview payload shaping changed or was already sufficient
- what you explicitly kept out to stay bounded
