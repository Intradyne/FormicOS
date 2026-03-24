## Role

You own the search, admission-bridge, and trigger/orchestration track of
Wave 44.

Your job is to:

- turn gap signals into bounded search requests
- turn search/fetch output into cautious candidate entries
- wire the reactive handoff without contaminating retrieval with network I/O
- make the Forager a real colony capability instead of a pile of adapters

This is the "make the colony actually forage" track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_44/wave_44_plan.md`
4. `docs/waves/wave_44/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `src/formicos/surface/knowledge_catalog.py`
7. `src/formicos/surface/admission.py`
8. `src/formicos/core/events.py`
9. `src/formicos/core/types.py`
10. `config/caste_recipes.yaml`
11. `src/formicos/engine/tool_dispatch.py`
12. `src/formicos/engine/runner.py`

## Coordination rules

- Retrieval may detect and request foraging, but it must **not** do web I/O
  inline.
- Query formation is deterministic in v1. Do **not** add LLM rewriting,
  HyDE, multi-query search, or a strategy bandit.
- Reuse `MemoryEntryCreated` for admitted forager entries. Do **not** add a
  `KnowledgeCandidateProposed` event.
- Keep search simple and pluggable. Do **not** require SearXNG for v1.
- Prefer an `httpx`-based search integration if possible to avoid unnecessary
  dependency overlap.
- Web content starts with conservative priors and must earn trust through the
  existing lifecycle.
- The Forager should be real, but bounded: no crawling, no spidering, no
  authenticated web flows, no Queen-logic rewrite.
- The existing `http_fetch` tool already has domain allowlisting, but its
  default policy is broader than the Forager's v1 strict-egress rule. Treat
  Wave 44 as tightening and upgrading that seam, not bypassing it.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `src/formicos/adapters/web_search.py` | CREATE | bounded search adapter |
| `src/formicos/surface/forager.py` | CREATE | main forager orchestration path |
| `src/formicos/surface/knowledge_catalog.py` | MODIFY | reactive trigger detection + handoff only |
| `src/formicos/surface/admission.py` | MODIFY | bounded forager provenance/admission bridge only if needed |
| `config/caste_recipes.yaml` | MODIFY | Forager recipe/config surface |
| `tests/unit/surface/` | CREATE/MODIFY | query, orchestration, admission, trigger tests |
| `tests/integration/` | CREATE/MODIFY | bounded end-to-end forager flows if needed |

## DO NOT TOUCH

- `pyproject.toml` - Team 1 owns extraction dependency changes
- `src/formicos/adapters/egress_gateway.py` - Team 1 owns
- `src/formicos/adapters/fetch_pipeline.py` - Team 1 owns
- `src/formicos/adapters/content_quality.py` - Team 1 owns
- `src/formicos/core/events.py` - Team 3 owns event additions
- `src/formicos/surface/projections.py` - Team 3 owns replay/projection state
- docs and wave packet files - Team 3 owns visibility/docs

---

## Pillar 2: Search and deterministic query formation

### Required scope

1. Build a simple web-search adapter.
2. Convert real gap signals into deterministic search queries.
3. Add a bounded pre-fetch filter so obviously irrelevant results are skipped.

### Hard constraints

- Do **not** make search depend on a new always-on Docker service.
- Do **not** make query formation depend on LLM calls.
- Do **not** let search logic leak into `knowledge_catalog.py`.

### Guidance

- Favor simple query templates keyed by gap type.
- A search adapter returning `{url, title, snippet}` is enough for v1.
- Keep backend choice configurable so the operator can use a simple default or
  a credentialed provider.
- It is acceptable for the very first version to have only one genuinely solid
  backend as long as the interface is pluggable.
- If Team 1 keeps `http_fetch` compatible while upgrading it under the hood,
  you may use that bounded fetch path as the transport seam instead of
  inventing a second unrelated HTTP path.

---

## Pillar 3: Content-to-knowledge bridge

### Required scope

1. Chunk extracted content into candidate-sized units.
2. Add exact-hash deduplication.
3. Map forager output into the existing seven admission dimensions.
4. Write admitted entries through `MemoryEntryCreated` as `candidate`.

### Hard constraints

- Do **not** add a special lifecycle for web content.
- Do **not** start web entries with high confidence.
- Do **not** hide provenance; it must stay inspectable inside the entry.

### Guidance

- Keep the bridge conservative and auditable.
- `MemoryEntryCreated` already carries the full entry dict, so provenance
  fields belong there rather than in a new event.
- If admission changes are unnecessary, prefer preparing the entry correctly in
  `forager.py` and leaving `admission.py` minimally touched.

---

## Pillar 4: Reactive trigger, caste, and operator controls

### Required scope

1. Add the reactive trigger path for low-confidence retrieval.
2. Build the surface/orchestration flow that consumes Team 1's substrate.
3. Add the Forager caste recipe.
4. Wire operator domain controls into real behavior.

### Hard constraints

- The reactive trigger is a handoff, not inline web research inside retrieval.
- Keep the first version bounded enough that tasks do not become permanently
  blocked on slow foraging.
- Do **not** add new Queen tools or rewrite governance behavior.

### Guidance

- A clean request path is more important than a fancy synchronous experience.
- If you need async/background behavior, keep the contract explicit and test it.
- The Forager recipe should match the real v1 capability surface, not the full
  research wishlist.

---

## Validation

Run, at minimum:

1. `python scripts/lint_imports.py`
2. targeted pytest for search, forager orchestration, admission bridge, and
   reactive-trigger seams
3. full `python -m pytest -q` if your handoff touches shared lifecycle or
   retrieval surfaces broadly

## Developmental evidence

Your summary must include:

- which search backend(s) actually landed
- what deterministic query templates were implemented
- how the reactive handoff works without inline network I/O
- how admitted entries reuse `MemoryEntryCreated`
- what provenance metadata is preserved
- what you rejected to keep this track bounded
