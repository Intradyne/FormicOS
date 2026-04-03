# Wave 80 Team A Prompt

## Mission

Build the Wave 80 planning brief: a tiny, scored, conditional planning
overlay that helps the Queen decompose work before the first LLM call.

This is not a new planner. It is a small helper that reuses existing
signals.

## Owned Files

- `src/formicos/surface/planning_brief.py` (new)
- `src/formicos/surface/queen_runtime.py`
- `tests/unit/surface/test_planning_brief.py` (new)

## Do Not Touch

- `src/formicos/surface/queen_budget.py`
- `src/formicos/surface/knowledge_constants.py`
- `src/formicos/surface/queen_tools.py`
- `src/formicos/core/types.py`
- `src/formicos/engine/runner.py`

If you need a new signal provider, call the helper Team B adds instead of
reimplementing it in `queen_runtime.py`.

## Repo Truth To Read First

1. `src/formicos/surface/queen_runtime.py:1108-1237`
   `respond()` (line 1108) delegates to `_respond_inner()` (line 1121).
   The actual work happens in `_respond_inner()` which:
   - builds messages
   - classifies relevant toolsets at `:1185`
   - loads tool specs at `:1188`
   - retrieves memory at `:1200`
   Your injection point is inside `_respond_inner()`, not `respond()`.

2. `src/formicos/surface/runtime.py:1190-1230`
   `retrieve_relevant_memory()` already exists. Do not replace it.

3. `src/formicos/surface/knowledge_catalog.py:388-520`
   `search()` already returns scored items with score breakdown metadata.

4. `src/formicos/surface/projections.py:739-759`
   `outcome_stats()` already provides simple planning-oriented historical
   summaries.

5. `src/formicos/adapters/code_analysis.py:87-165`
   `relevant_context()` and `analyze_workspace()` already provide a
   lightweight structural dependency view.

   **Important:** These operate on the workspace file tree under the
   data dir (`/data/workspaces/{id}/files/`), which currently contains
   colony output artifacts — not the operator's host project code.
   The coupling signal will be thin until a future wave adds a host
   mount. This is fine: the prompt already says to only emit the
   coupling line when you have a confident match. If the workspace is
   sparse, omit the line entirely.

6. `src/formicos/surface/runtime.py:931-939`
   `resolve_model()` is the right worker-model resolution seam.

## What To Build

Create `src/formicos/surface/planning_brief.py` with a small public
helper, for example:

```python
async def build_planning_brief(
    runtime: Runtime,
    workspace_id: str,
    thread_id: str,
    operator_message: str,
    *,
    token_budget: int,
) -> str:
    ...
```

The helper should compose up to four scored lines:

1. `Patterns`
   - Search the existing knowledge catalog with a decomposition-oriented
     query derived from the operator message
   - Post-filter for pattern-like entries using title/content/domains
   - If the knowledge base is sparse, fall back to a short empirical line
     from `runtime.projections.outcome_stats(workspace_id)`

2. `Playbook`
   - Call Team B's `get_decomposition_hints(task_description)`

3. `Worker`
   - Use Team B's capability-profile helper with
     `runtime.resolve_model("coder", workspace_id)`

4. `Coupling`
   - Use `analyze_workspace()` against the workspace file tree under the
     runtime data dir
   - Only emit this line if the operator message references files or
     modules you can match with confidence

## Injection Rules

Integrate in `queen_runtime.py` only.

- Only build the brief when `"colony"` is in the resolved toolsets
- Do not add a new context-budget slot
- Use the existing `memory_retrieval` slot
- Reserve at most `min(500, budget.memory_retrieval // 3)` tokens for
  the brief
- If the brief is empty, existing memory retrieval behavior must remain
  unchanged

Recommended insertion point:

- after toolsets are resolved at `queen_runtime.py:1185-1188`
- before or alongside the existing memory injection path beginning at
  `queen_runtime.py:1200`

## Formatting Rules

- Keep the whole brief under about 2000 characters
- Prefer one-line sections
- Every emitted line must include evidence:
  - `q=...`
  - `score=...`
  - `conf=...`
  - `n=...`
- Omit weak sections rather than writing generic filler

Good:

```text
PLANNING BRIEF
- Patterns: addon-build (q=0.59, score=0.82) | refactor (q=0.72, score=0.76)
- Playbook: code_implementation (conf=1.00) -> 3-5 colonies, grouped files
- Worker: qwen3.5-4b (n=24) -> 3-4 files optimal, 1-file -16%
```

Bad:

```text
The system has some prior knowledge about decomposition and should think
carefully before spawning colonies.
```

## Important Constraints

- Do not change `classify_relevant_toolsets()`
- Do not retune graph weights
- Do not add new events
- Do not add an LLM call to build the brief
- Do not turn this into another large context block

## Validation

Add focused tests that prove:

1. The brief is only built on colony-capable turns
2. The brief disappears on status-only turns
3. The brief respects the token budget
4. Empty or low-signal sections are omitted cleanly
5. Structural coupling lines only appear when a real file/module match exists

Run:

- `python -m pytest tests/unit/surface/test_planning_brief.py -q`
- `python -m pytest tests/unit/surface/test_queen_runtime.py -q`
- `python -m pytest tests/unit/adapters/test_code_analysis.py -q`

## Overlap Note

You are not alone in the codebase. Team B owns playbook hints and
capability profiles. Team C owns `ColonyTask` and `spawn_parallel`.
Adjust to their landed helpers and do not revert their work.
