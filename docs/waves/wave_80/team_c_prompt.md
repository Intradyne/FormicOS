# Wave 80 Team C Prompt

## Mission

Make file-mediated handoff a real part of parallel planning.

The Queen already has:

- `depends_on`
- `input_from`
- `target_files`

What is missing is the explicit declaration of what each colony is
expected to produce, plus automatic wiring of downstream file context.

## Owned Files

- `src/formicos/core/types.py`
- `src/formicos/surface/queen_tools.py`
- `tests/unit/surface/test_file_handoff.py` (new)

## Do Not Touch

- `src/formicos/surface/queen_runtime.py`
- `src/formicos/engine/playbook_loader.py`
- `src/formicos/surface/queen_budget.py`
- `src/formicos/engine/runner.py`

## Repo Truth To Read First

1. `src/formicos/core/types.py:879-896`
   `ColonyTask` already has:
   - `depends_on`
   - `input_from`
   - `target_files`

   It does not yet have `expected_outputs`.

2. `src/formicos/surface/queen_tools.py:500-598`
   The `spawn_parallel` tool schema already exposes a DAG contract, but
   the per-task schema is missing both `target_files` and
   `expected_outputs`.

3. `src/formicos/surface/queen_tools.py:2192-2355`
   `_spawn_parallel()` already:
   - validates the plan
   - builds `ColonyTask` objects
   - maps `input_from` into `InputSource(type="colony", ...)`
   - passes `target_files` through to `runtime.spawn_colony()`

This is an alignment and wiring task, not a new subsystem.

## What To Build

### 1. Add `expected_outputs` to `ColonyTask`

Extend `ColonyTask` in `core/types.py` with:

```python
expected_outputs: list[str] = Field(default_factory=list)
```

Keep it additive and replay-safe.

### 2. Align `spawn_parallel` tool schema

Add both of these to the per-task schema inside the `spawn_parallel`
tool definition:

- `expected_outputs`
- `target_files`

That makes the LLM-visible contract match the type-level contract.

### 3. Auto-wire downstream `target_files`

Inside `_spawn_parallel()`:

- after plan validation
- before preview formatting
- before dispatch

auto-wire `target_files` from upstream `expected_outputs` whenever:

- `task.depends_on` is non-empty
- `task.target_files` is empty
- upstream tasks declared outputs

Rules:

- Preserve explicit `target_files`
- Preserve upstream task order
- Deduplicate the final file list
- Do not auto-fill `input_from`; it is intentionally separate from
  `target_files`. `target_files` scopes what files a colony should read.
  `input_from` controls data provenance — which colony's transcript
  output gets injected as context via `InputSource(type="colony")`.
  Wiring both from the same upstream source would conflate file scope
  with execution context, breaking the existing semantics.

### 4. Make preview truthful

If preview mode is used, the operator should be able to see the resolved
file-handoff plan. Add the resolved `expected_outputs` and `target_files`
to preview text or preview metadata.

This is backend-only truth. Do not add frontend work in this wave.

## Important Constraints

- No new events
- No new route
- No new frontend work
- No runner changes
- Do not break existing `spawn_colony` behavior

## Validation

Add focused tests that prove:

1. `ColonyTask` accepts `expected_outputs`
2. `spawn_parallel` accepts `expected_outputs` and `target_files` in task
   items
3. auto-wiring fills downstream `target_files` only when explicit values
   are absent
4. duplicate upstream outputs are deduplicated
5. preview mode reflects the resolved handoff plan

Run:

- `python -m pytest tests/unit/surface/test_file_handoff.py -q`
- `python -m pytest tests/unit/surface/test_queen_tools.py -q`
- `python -m pytest tests/integration/test_wave41_multifile_coordination.py -q`

## Overlap Note

You are not alone in the codebase. Team A will benefit from your richer
parallel-plan contract but should not need to modify your files. Team B
is independent. Keep the handoff logic local to `queen_tools.py` and do
not revert other edits.
