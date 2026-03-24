## Role

You own the static workspace intelligence and topology-prior track of Wave 42.

Your job is to:

- add the cheapest useful non-LLM structural intelligence to the workspace path
- replace the weakest remaining topology bridge with a simple stronger one
- keep the first version small, legible, and grounded in the current substrate

This is the "static structure first, better priors second" track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_42/wave_42_plan.md`
4. `docs/waves/wave_42/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `src/formicos/engine/runner.py`
7. `src/formicos/surface/colony_manager.py`
8. `src/formicos/engine/strategies/stigmergic.py`
9. `src/formicos/adapters/ast_security.py`
10. `src/formicos/surface/knowledge_catalog.py`

## Coordination rules

- Keep the first version simple.
- Operate on the workspace tree the colony already has access to.
- Do **not** anchor this track to a repo-clone abstraction unless the current
  substrate truly needs it.
- Keep this track forward-compatible with future per-language container
  backends and stronger sandbox runtimes. Operate on workspace contents and
  paths, not Docker-specific assumptions.
- Do **not** bulk-dump structural facts into the main knowledge substrate by
  default.
- Prefer a workspace-scoped structural substrate or helper first.
- Budget structural context tightly. Target roughly 1-2K tokens per agent,
  ranked by relevance, rather than dumping a whole repository map.
- Replace the topology prior with structural dependency signals plus a neutral
  fallback. Do **not** jump to embedding affinity or asymmetric weighting in
  v1.
- Do **not** touch contradiction-resolution or adaptive-evaporation seams in
  this track.
- Do **not** add event types.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `src/formicos/adapters/code_analysis.py` | CREATE | lightweight structural analysis |
| `src/formicos/engine/runner.py` | OWN | `_compute_knowledge_prior` rewrite only |
| `src/formicos/engine/strategies/stigmergic.py` | MODIFY | only if structural priors need a clean application point |
| `src/formicos/surface/colony_manager.py` | MODIFY | structural-analysis integration only |
| `src/formicos/surface/knowledge_catalog.py` | MODIFY | only if a bounded structural substrate hook is truly needed |
| `tests/unit/adapters/test_code_analysis.py` | CREATE | structural analysis tests |
| `tests/integration/test_wave42_structural_knowledge.py` | CREATE | workspace-structure integration tests |
| `tests/unit/engine/test_wave42_topology_prior.py` | CREATE | prior behavior tests |

## DO NOT TOUCH

- `src/formicos/surface/conflict_resolution.py` - Team 2 owns
- `src/formicos/surface/projections.py` - Team 2 owns if Stage 3 lands
- `src/formicos/surface/proactive_intelligence.py` - Team 2 owns contradiction
  use sites
- `src/formicos/engine/runner.py` adaptive-evaporation seam - Team 3 owns
- frontend files and wave docs - not this track

## Method-level overlap rules

`src/formicos/surface/colony_manager.py` is shared this wave.

- You own any new structural-analysis methods and their invocation points.
- You do **not** own:
  - `_hook_memory_extraction`
  - `extract_institutional_memory`
  - `_check_inline_dedup`
  - `_hook_confidence_update`
- If you need a handoff seam in `colony_manager.py`, create one cleanly and
  note it in your summary instead of editing Team 2's extraction logic.

---

## Pillar 1: Static workspace analysis

### Required scope

1. Add a lightweight structural analysis path for the workspace tree.
2. Support at least:
   - Python
   - JavaScript / TypeScript
   - Go
3. Produce useful facts such as:
   - import / dependency relationships
   - top-level function / class inventory
   - rough file-role classification
4. Keep the implementation dependency-light and explainable.

### Hard constraints

- Do **not** add heavy parser dependencies for v1.
- Do **not** promise perfect parsing.
- Do **not** flood general knowledge storage with raw structural trivia.
- Do **not** assume the current sandbox/execution backend is permanent.

---

## Pillar 2: Structural topology prior v1

### Required scope

1. Replace the current domain-name-overlap topology prior with a structural
   dependency prior when structural facts are available.
2. Fall back cleanly to neutral when they are not.
3. Keep the prior bounded and modest.

### Hard constraints

- Do **not** start with embedding affinity.
- Do **not** start with asymmetric weights.
- Do **not** over-bias the topology because the prior "looks smarter."

---

## Developmental eval

Include a small before/after developmental eval for the landed changes:

- one or more repeated multi-file tasks
- structural analysis disabled vs enabled
- old prior vs structural prior

Report:

- whether relevant file sets were identified more accurately
- whether obvious wasted LLM structure-reading behavior decreased
- whether topology settled faster or more sensibly

This is a development check, not a public-proof benchmark.

---

## Validation

Run, at minimum:

1. `python scripts/lint_imports.py`
2. targeted pytest for analysis and topology seams
3. full `python -m pytest -q` if your changes touch shared runtime behavior

Your summary must include:

- what structural analysis actually supports
- where the structural facts live
- how `_compute_knowledge_prior` now works
- what you deliberately did **not** add in v1
