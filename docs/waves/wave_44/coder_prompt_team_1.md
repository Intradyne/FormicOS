## Role

You own the web-acquisition substrate track of Wave 44.

Your job is to:

- build the bounded egress layer
- build the first extraction pipeline
- score fetched content cheaply and legibly
- leave Team 2 a clean URL -> extracted-text substrate to consume

This is the "make cautious web acquisition real" track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_44/wave_44_plan.md`
4. `docs/waves/wave_44/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `pyproject.toml`
7. `src/formicos/engine/tool_dispatch.py`
8. `src/formicos/engine/runner.py`
9. `src/formicos/core/events.py`
10. `src/formicos/surface/knowledge_catalog.py`
11. `src/formicos/surface/admission.py`
12. `src/formicos/surface/proactive_intelligence.py`

## Coordination rules

- Strict egress is a Must-ship requirement.
- In v1, fetch only search-result URLs plus explicit operator overrides.
- The Forager runs in the main container, not in sandbox containers.
- Do **not** build Playwright, browser rendering, or crawling in this track.
- Do **not** build SearXNG or any new Docker service here.
- Keep domain strategy logic pure and bounded. Team 3 owns the replay event
  definition, and Team 2 owns the surface path that emits updates.
- Prefer additive dependencies only where clearly justified:
  `trafilatura` and `readability-lxml` are in scope; do not add a heavier
  extractor stack than the wave requires.
- Do **not** write directly to the knowledge lifecycle from this track.
- An `http_fetch` tool already exists in `tool_dispatch.py` with a handler in
  `runner.py`. Treat that as the natural transport/policy refactor seam rather
  than building around it as if nothing exists.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `pyproject.toml` | OWN | extraction dependencies only |
| `src/formicos/adapters/egress_gateway.py` | CREATE | outbound HTTP policy adapter |
| `src/formicos/adapters/fetch_pipeline.py` | CREATE | Level 1 and bounded Level 2 extraction |
| `src/formicos/adapters/content_quality.py` | CREATE | heuristic scoring without LLM calls |
| `tests/unit/adapters/` | CREATE/MODIFY | gateway, fetch, quality tests |

## DO NOT TOUCH

- `src/formicos/adapters/web_search.py` - Team 2 owns search
- `src/formicos/surface/forager.py` - Team 2 owns forager orchestration
- `src/formicos/surface/knowledge_catalog.py` - Team 2 owns reactive trigger hook
- `src/formicos/surface/admission.py` - Team 2 owns admission bridge changes
- `src/formicos/core/events.py` - Team 3 owns event additions
- `src/formicos/surface/projections.py` - Team 3 owns projection state
- docs and wave packet files - Team 3 owns visibility/docs

---

## Pillar 1: Egress and extraction

### Required scope

1. Build an `EgressGateway` adapter around `httpx`.
2. Enforce domain/rate/size/timeout policy.
3. Enforce the strict-fetch rule for v1.
4. Build Level 1 extraction with `trafilatura` in markdown mode.

### Optional scope

Only if it stays bounded:

- Level 2 extractor fallback using `trafilatura(favor_recall=True)` and
  `readability-lxml`
- simple pattern defaults for known domains

### Hard constraints

- Do **not** accept arbitrary URLs constructed by prompts or page content.
- Do **not** make the egress adapter decide admission or knowledge policy.
- Do **not** let extraction quality failures turn into browser work here.
- Do **not** add new event types from this track.

### Guidance

- `EgressGateway` should be a policy-and-transport adapter, not a surface
  orchestrator.
- The existing `http_fetch` handler already does `httpx` GET plus domain
  allowlisting, but HTML extraction is still just regex tag stripping. Extract
  or refactor that transport/policy logic into `egress_gateway.py`, replace
  the extraction path with the new fetch pipeline, and keep the tool
  registration compatible.
- `robots.txt` checking can stay simple and cached.
- Keep the API easy for Team 2 to call from a forager surface module.
- If you return extraction metadata, make it structured and auditable:
  content type, method used, text length, quality hints, failure reason.

---

## Pillar 1B: Domain strategy logic and quality scoring

### Required scope

1. Provide a bounded strategy shape for per-domain fetch preferences.
2. Provide update logic that can recommend escalation/de-escalation.
3. Build a cheap quality score that helps the admission path.

### Hard constraints

- Team 1 owns the logic, not the replay event shape.
- The strategy output must be simple enough for Team 2 to apply and Team 3 to
  persist without ambiguity.
- Do **not** make the quality score depend on live LLM calls.

### Guidance

- Think of domain strategy as pure recommendation logic plus structured state.
- Good enough beats perfect here. The first version should be easy to test and
  reason about.
- The quality score should help reject obvious junk and rank likely-useful
  content, not solve truth by itself.

---

## Validation

Run, at minimum:

1. `python scripts/lint_imports.py`
2. targeted adapter pytest for gateway, fetch, and quality seams
3. full `python -m pytest -q` if dependency or shared-adapter changes broaden
   across the repo

## Developmental evidence

Your summary must include:

- what egress controls were added
- what fetch levels actually landed
- what dependencies were added and why
- what domain strategy logic exists versus what was deferred
- what quality-scoring signals landed
- what you rejected to keep this track bounded
