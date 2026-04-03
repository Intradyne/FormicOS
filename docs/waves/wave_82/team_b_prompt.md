# Wave 82 Team B Prompt

## Mission

Turn real project structure into planning-grade signals using the seams
that already exist.

This is not a new repo-map subsystem. It is a structural-planner layer
over the existing project root, code analysis, and knowledge graph.

## Owned Files

- `src/formicos/adapters/code_analysis.py`
- `src/formicos/adapters/knowledge_graph.py`
- `src/formicos/surface/structural_planner.py` (new)
- `tests/unit/adapters/test_code_analysis.py`
- `tests/unit/surface/test_structural_planner.py` (new)
- `tests/unit/surface/test_knowledge_catalog.py`

## Do Not Touch

- `src/formicos/surface/planning_brief.py`
- `src/formicos/surface/workflow_learning.py`
- `src/formicos/surface/capability_profiles.py`
- `src/formicos/surface/routes/api.py`
- frontend components

Track A will consume your helper.
Track D will render its outputs.

## Repo Truth To Read First

1. `src/formicos/adapters/code_analysis.py`
   This already extracts imports, reverse dependencies, and test
   companions. It is the right substrate for planning hints.

2. `src/formicos/adapters/knowledge_graph.py`
   This already supports `MODULE`, `DEPENDS_ON`, and
   `personalized_pagerank(...)`.

3. `src/formicos/surface/knowledge_catalog.py`
   Graph proximity is already live. Structural work should reinforce
   this path, not bypass it.

4. `src/formicos/surface/planning_brief.py`
   The current coupling line is a thin proof-of-concept. Your helper is
   the replacement seam Track A should consume.

5. Wave 81 project binding
   Use the real project root, not the workspace-library fallback, when
   the workspace is bound.

6. Project binding + code index status are now live
   The current stack exposes bound-project truth and ready index counts.
   Treat that as a supporting seam, but keep your core structural truth
   grounded in deterministic project-root analysis and the knowledge
   graph rather than semantic-search availability alone.

## What To Build

### 1. Structural-planner helper

Create:

- `src/formicos/surface/structural_planner.py`

Recommended public API:

```python
def get_structural_hints(runtime, workspace_id: str, operator_message: str, *, max_groups: int = 3) -> dict[str, Any]:
    ...
```

Return:

- matched files/modules
- coupling pairs
- suggested file groups
- confidence + rationale per group

### 2. Graph reflection from real code

Use the bound project root plus `code_analysis.py` output to create or
update:

- `MODULE` entities
- `DEPENDS_ON` edges

Keep it incremental and additive.

### 3. Planning-grade suggestions

Your helper should be good enough to answer:

- which files are structurally coupled?
- which files likely belong in the same colony?
- when is the evidence weak enough that the planner should omit the line?

### 4. Omit weak guesses

If structure is weak or unproved, return less.
Do not fill the UI with decorative graph language.

## Important Constraints

- Use the Wave 81 project root helpers
- Do not create a second graph system
- Do not rewrite codebase-index
- Do not build a full auto-grouping engine in this wave
- Prefer proof over completeness

## Validation

Run:

- `python -m pytest tests/unit/adapters/test_code_analysis.py -q`
- `python -m pytest tests/unit/surface/test_structural_planner.py -q`
- `python -m pytest tests/unit/surface/test_knowledge_catalog.py -q`

## Overlap Note

You are not alone in the codebase.

- Track A will consume your public helper in the planning-signals layer
- Track D will render your groups and coupling hints

Keep the helper API small and stable. Do not spill UI-specific shapes
into the adapter layer.
