# Wave 02 Plan

## Goal
Build the first executable back-end slice: event store, vector store, LLM adapters,
and the engine round runner with sequential and stigmergic strategies.

## Dependency gate
Requires Wave 01 outputs from Streams A and G.

## Wave ownership
| Stream | Owns | Must not touch |
|---|---|---|
| B - Adapters | `src/formicos/adapters/store_sqlite.py`, `src/formicos/adapters/vector_lancedb.py`, `tests/unit/adapters/test_store_sqlite.py`, `tests/unit/adapters/test_vector_lancedb.py` | core/, engine/, surface/, frontend/ |
| C - LLM | `src/formicos/adapters/llm_anthropic.py`, `src/formicos/adapters/llm_openai_compatible.py`, `tests/unit/adapters/test_llm_anthropic.py`, `tests/unit/adapters/test_llm_openai_compatible.py` | core/, engine/, surface/, frontend/ |
| E - Engine | `src/formicos/engine/context.py`, `src/formicos/engine/runner.py`, `src/formicos/engine/strategies/sequential.py`, `src/formicos/engine/strategies/stigmergic.py`, `tests/unit/engine/test_runner.py`, `tests/unit/engine/test_strategies.py` | core/, adapters/, surface/, frontend/ |

## LOC budget
- Stream B: <= 500 LOC
- Stream C: <= 450 LOC
- Stream E: <= 700 LOC
- Wave total target: <= 1,650 LOC

## Stream B Dispatch
### Context bundle
- Read `CLAUDE.md`, `AGENTS.md`, ADR-001, ADR-002, and ADR-004.
- Read frozen contracts in `docs/contracts/events.py` and `docs/contracts/ports.py`.
- Read `docs/specs/persistence.feature` and `docs/specs/merge_prune_broadcast.feature`.

### Task
Implement the SQLite event store and LanceDB vector adapter against the frozen ports.

### Produce
- `src/formicos/adapters/store_sqlite.py`
- `src/formicos/adapters/vector_lancedb.py`
- `tests/unit/adapters/test_store_sqlite.py`
- `tests/unit/adapters/test_vector_lancedb.py`

### Constraints
- One logical event store only.
- Preserve append order and monotonic `seq`.
- Keep adapter imports limited to core.

### Verify
- `python -m py_compile src/formicos/adapters/store_sqlite.py src/formicos/adapters/vector_lancedb.py`
- `pytest tests/unit/adapters/test_store_sqlite.py tests/unit/adapters/test_vector_lancedb.py -q`

## Stream C Dispatch
### Context bundle
- Read `CLAUDE.md`, `AGENTS.md`, ADR-004, and the frozen port contract.
- Read `config/formicos.yaml` for model registry shapes.
- Read `docs/waves/phase2/algorithms.md`.
- Read `docs/specs/model_cascade.feature`, `docs/specs/queen_chat.feature`, and `docs/specs/external_mcp.feature`.

### Task
Implement Anthropic and OpenAI-compatible LLM adapters that satisfy `LLMPort`.

### Produce
- `src/formicos/adapters/llm_anthropic.py`
- `src/formicos/adapters/llm_openai_compatible.py`
- `tests/unit/adapters/test_llm_anthropic.py`
- `tests/unit/adapters/test_llm_openai_compatible.py`

### Constraints
- Match the frozen request/response models exactly.
- Keep provider-specific translation inside adapters, not in engine.
- No retry policy beyond the frozen contract semantics.

### Verify
- `python -m py_compile src/formicos/adapters/llm_anthropic.py src/formicos/adapters/llm_openai_compatible.py`
- `pytest tests/unit/adapters/test_llm_anthropic.py tests/unit/adapters/test_llm_openai_compatible.py -q`

## Stream E Dispatch
### Context bundle
- Read `CLAUDE.md`, `AGENTS.md`, ADR-001, ADR-004, and the frozen algorithms doc.
- Read `docs/specs/round_execution.feature`, `docs/specs/merge_prune_broadcast.feature`, `docs/specs/approval_workflow.feature`, and `docs/specs/thread_workspace.feature`.

### Task
Implement colony round execution, context assembly, and coordination strategies.

### Produce
- `src/formicos/engine/context.py`
- `src/formicos/engine/runner.py`
- `src/formicos/engine/strategies/sequential.py`
- `src/formicos/engine/strategies/stigmergic.py`
- `tests/unit/engine/test_runner.py`
- `tests/unit/engine/test_strategies.py`

### Constraints
- Import only core and standard library modules.
- Sequential strategy is the correctness fallback.
- Stigmergic strategy must follow the frozen pseudocode exactly.

### Verify
- `python -m py_compile src/formicos/engine/context.py src/formicos/engine/runner.py src/formicos/engine/strategies/sequential.py src/formicos/engine/strategies/stigmergic.py`
- `pytest tests/unit/engine/test_runner.py tests/unit/engine/test_strategies.py -q`

## Acceptance criteria
- `docs/specs/round_execution.feature`
- `docs/specs/merge_prune_broadcast.feature`
- `docs/specs/approval_workflow.feature`
- `docs/specs/persistence.feature`
