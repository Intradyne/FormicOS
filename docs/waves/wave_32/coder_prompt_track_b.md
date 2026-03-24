# Wave 32 — Track B Coder Dispatch: Structural Refactoring

**Wave:** 32
**Track:** B — Structural Refactoring (Lands First — Unblocks Track A)
**Prerequisite:** Wave 31 landed. 1,394 tests passing, 0 pyright errors.
**Priority:** This track MUST land before Track A starts. Track C runs in parallel.

---

## Coordination rules

- **Read `CLAUDE.md` and `docs/decisions/` before making architectural choices.**
- **Read `docs/contracts/` before modifying any interface.**
- **If your change contradicts an ADR, STOP and flag the conflict.**
- **Event types are a CLOSED union of 48 — do NOT add new events.**
- Root `AGENTS.md` may be historical. This dispatch prompt and `docs/waves/wave_32/wave_32_plan.md` are the active coordination source for Wave 32.

---

## Your file ownership

You may ONLY modify these files:

| File | Task | Notes |
|------|------|-------|
| `engine/runner.py` | B1 | RunnerCallbacks dataclass + `__init__` refactor |
| `surface/colony_manager.py` | B1 + B3 | RunnerCallbacks construction + hooks decomposition |
| `surface/queen_runtime.py` | B2 | Shrink to ~600 lines |
| `surface/queen_tools.py` | B2 | **CREATE** — QueenToolDispatcher class |
| `surface/queen_thread.py` | B2 | **CREATE** — QueenThreadManager class |
| `adapters/vector_qdrant.py` | B4 | Retry logic on 3 operations |

**Do NOT touch:** `core/events.py`, `core/types.py`, `docs/contracts/events.py`, `surface/knowledge_catalog.py`, `surface/projections.py`, any test files outside of fixing existing tests that break from your refactoring.

---

## Task B1: Extract RunnerCallbacks frozen dataclass

**Goal:** Collapse `RoundRunner.__init__`'s 16 keyword parameters into a frozen dataclass.

**Current state:** `RoundRunner.__init__` at `engine/runner.py:689-707` takes 16 params:
`emit`, `embed_fn`, `async_embed_fn`, `cost_fn`, `tier_budgets`, `route_fn`, `kg_adapter`, `max_rounds`, `code_execute_handler`, `service_router`, `data_dir`, `effector_config`, `catalog_search_fn`, `knowledge_detail_fn`, `artifact_inspect_fn`, `transcript_search_fn`.

**Implementation:**

1. Define `RunnerCallbacks` in `engine/runner.py` above the `RoundRunner` class:

```python
@dataclass(frozen=True)
class RunnerCallbacks:
    """Injected dependencies for RoundRunner (engine never imports surface)."""
    emit: Callable[[FormicOSEvent], Any]
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None
    async_embed_fn: AsyncEmbedFn | None = None
    cost_fn: Callable[[str, int, int], float] | None = None
    tier_budgets: TierBudgets | None = None
    route_fn: Callable[[str, str, int, float], str] | None = None
    kg_adapter: Any | None = None
    code_execute_handler: CodeExecuteHandler | None = None
    service_router: ServiceRouter | None = None
    catalog_search_fn: Callable[..., Any] | None = None
    knowledge_detail_fn: Callable[..., Any] | None = None
    artifact_inspect_fn: Callable[..., Any] | None = None
    transcript_search_fn: Callable[..., Any] | None = None
    max_rounds: int = 25
    data_dir: str = ""
    effector_config: dict[str, Any] | None = None
```

2. Refactor `RoundRunner.__init__` to take `callbacks: RunnerCallbacks` as its sole parameter. Update all `self._emit`, `self._embed_fn`, etc. to read from `self._cb.emit`, `self._cb.embed_fn`, etc. Or unpack them in `__init__` — either pattern is fine, pick whichever produces cleaner diffs.

3. Update the construction site in `surface/colony_manager.py` (around line 355) to build a `RunnerCallbacks` instance and pass it to `RoundRunner`.

4. Run `pytest` after this task. Fix any test that constructs `RoundRunner` directly — they'll need to build `RunnerCallbacks` instead. These are likely in `tests/unit/engine/` or `tests/integration/`.

**Acceptance:**
- `RoundRunner.__init__` takes a single `RunnerCallbacks` parameter
- All existing tests pass (with updated mock construction)
- `pyright src/` clean

---

## Task B2: Split queen_runtime.py into 3 modules

**Goal:** Decompose `QueenAgent` (2,365 lines, 34 methods) into 3 focused modules while preserving the public interface.

**Current state:** `QueenAgent` class at `surface/queen_runtime.py:158`. `__init__` at line 161. `_execute_tool` at line 1203.

**Full 34-method inventory:**
1. `__init__`, 2. `name_colony`, 3. `follow_up_colony`, 4. `_emit_queen_message`, 5. `respond`, 6. `_resolve_queen_model`, 7. `_queen_temperature`, 8. `_queen_max_tokens`, 9. `_build_messages`, 10. `_inject_nudges`, 11. `_build_thread_context`, 12. `_queen_tools`, 13. `_execute_tool`, 14. `_tool_spawn_colony`, 15. `_tool_get_status`, 16. `_tool_list_templates`, 17. `_tool_inspect_template`, 18. `_tool_inspect_colony`, 19. `_tool_read_workspace_files`, 20. `_tool_suggest_config_change`, 21. `_tool_approve_config_change`, 22. `_tool_redirect_colony`, 23. `on_governance_alert`, 24. `_tool_escalate_colony`, 25. `_tool_read_colony_output`, 26. `_tool_memory_search`, 27. `_tool_write_workspace_file`, 28. `_queen_notes_path`, 29. `_load_queen_notes`, 30. `_save_queen_notes`, 31. `save_thread_note`, 32. `_tool_queen_note`, 33. `_resolve_current_value`, 34. `_tool_define_workflow_steps`

**Decomposition target:**

### queen_runtime.py (~600 lines) — QueenAgent core
Retains: `__init__`, `name_colony`, `follow_up_colony`, `_emit_queen_message`, `respond`, `_resolve_queen_model`, `_queen_temperature`, `_queen_max_tokens`, `_build_messages`, `_inject_nudges`, `_build_thread_context`. This is the LLM interaction loop and conversation assembly. Delegates tool dispatch and thread lifecycle to the other modules.

In `__init__`, instantiate:
```python
self._tool_dispatcher = QueenToolDispatcher(self._runtime)
self._thread_mgr = QueenThreadManager(self._runtime)
```

Replace `_queen_tools()` to call `self._tool_dispatcher.tool_specs()`.
Replace `_execute_tool()` to call `self._tool_dispatcher.dispatch(name, inputs, workspace_id, thread_id)`, except for thread lifecycle tools which delegate to `self._thread_mgr`.

### queen_tools.py (~1,200 lines) — NEW: QueenToolDispatcher

```python
class QueenToolDispatcher:
    def __init__(self, runtime: Runtime) -> None:
        self._runtime = runtime

    def tool_specs(self) -> list[dict[str, Any]]:
        """Return the tool spec list for the Queen."""
        ...

    async def dispatch(
        self, name: str, inputs: dict, workspace_id: str, thread_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        if name == "spawn_colony":
            return await self._spawn_colony(inputs, workspace_id, thread_id)
        ...
```

Move all `_tool_*` methods (14-22, 24-27, 32-33) here as methods on the dispatcher. Each becomes `self._spawn_colony`, `self._get_status`, etc. They access `self._runtime` for projections, emit_and_broadcast, llm_router, vector_store, template loading.

### queen_thread.py (~500 lines) — NEW: QueenThreadManager

```python
class QueenThreadManager:
    def __init__(self, runtime: Runtime) -> None:
        self._runtime = runtime
```

Move: `on_governance_alert` (#23), `_tool_define_workflow_steps` (#34), `_queen_notes_path` (#28), `_load_queen_notes` (#29), `_save_queen_notes` (#30), `save_thread_note` (#31). Plus the archival decay logic currently in `_execute_tool` under the `archive_thread` tool case (around lines 1301-1356).

**Key constraint:** The public interface does NOT change. External code still does `from formicos.surface.queen_runtime import QueenAgent`. The split is internal.

**Mechanical approach:** Move methods ONE AT A TIME. After each move, run `pytest` and `pyright`. Do NOT batch moves. Start with tool implementations (largest, most self-contained), then thread lifecycle.

**Layer imports:** `scripts/lint_imports.py` explicitly allows surface-to-surface imports. No layer violations from the new modules importing each other or importing from queen_runtime.

**Acceptance:**
- `queen_runtime.py` under 700 lines
- `queen_tools.py` and `queen_thread.py` exist and contain the extracted methods
- `from formicos.surface.queen_runtime import QueenAgent` still works
- All existing tests pass
- `python scripts/lint_imports.py` clean
- `pyright src/` clean

---

## Task B3: Decompose _post_colony_hooks into per-concern handlers

**Goal:** Break `_post_colony_hooks` (220 lines, 6 concerns) into named handlers with a thin dispatcher.

**Current state:** `_post_colony_hooks` at `surface/colony_manager.py:648-660` (signature), body through ~867.

**Concern map with verified line ranges:**

| # | Concern | Lines | Hook Name |
|---|---------|-------|-----------|
| 1 | Colony observation log | 662-676 | `_hook_observation_log` |
| 2 | Step detection for continuation | 686-730 | `_hook_step_detection` |
| 3 | Queen follow-up dispatch | 732-740 | `_hook_follow_up` |
| 4 | Institutional memory extraction | 742-754 | `_hook_memory_extraction` |
| 5 | Bayesian confidence update | 756-811 | `_hook_confidence_update` |
| 6 | Workflow step completion | 823-866 | `_hook_step_completion` |

**Ordering dependencies (MUST preserve):**
- Step detection (#2) MUST run before follow-up (#3) — builds `step_continuation` text
- Confidence update (#5) MUST run after memory extraction (#4) — extraction creates entries

**NOTE:** Lines 693-700 (step detection) and 827-831 (step completion) both scan `workflow_steps` for the running step. Consolidate this into a shared helper if it simplifies things; or leave both lookups if the cost of the abstraction outweighs the duplication.

**Target dispatcher:**

```python
async def _post_colony_hooks(self, ...) -> None:
    """Dispatch post-colony lifecycle hooks in order."""
    self._hook_observation_log(colony_id, colony, ...)
    step_text = await self._hook_step_detection(colony_id, colony, ...)
    await self._hook_follow_up(colony_id, colony, step_text, ...)
    await self._hook_memory_extraction(colony_id, colony, ...)
    await self._hook_confidence_update(colony_id, colony, ...)
    await self._hook_step_completion(colony_id, colony, ...)
```

Each hook is a private method on `ColonyManager`. Keep them in the same file — they share `self._runtime`, `self._projections`, etc.

**Acceptance:**
- `_post_colony_hooks` is under 30 lines (dispatcher only)
- 6 hook methods exist as named private methods
- Step continuation still fires (existing Wave 31 tests pass)
- All tests pass

---

## Task B4: Qdrant write retry with error distinction

**Goal:** Add retry logic for transient Qdrant failures. Surface permanent failures as ERROR logs.

**Current state:** `adapters/vector_qdrant.py` has 3 public operations with `except Exception: return 0`:
- `upsert()` at line 172
- `search()` at line 245
- `delete()` at line 279

Do NOT wrap `ensure_collection()` — it's idempotent, called once at startup, and already has its own error handling.

**Implementation:**

```python
import asyncio

_TRANSIENT = (ConnectionError, TimeoutError, OSError)

async def _retry_qdrant(self, operation, *args, retries=3, **kwargs):
    for attempt in range(retries):
        try:
            return await operation(*args, **kwargs)
        except _TRANSIENT as exc:
            if attempt == retries - 1:
                log.error("qdrant.transient_failure_exhausted", error=str(exc), attempt=attempt)
                return 0
            await asyncio.sleep(0.5 * (2 ** attempt))
        except Exception as exc:
            log.error("qdrant.permanent_failure", error=str(exc))
            return 0
    return 0
```

Wrap the internal Qdrant client calls in `upsert`, `search`, and `delete` with `_retry_qdrant`. The public method signatures and return types do NOT change. Callers still receive `0` on failure — the improvement is that transient failures get 3 retries and all failures log at ERROR.

**Acceptance:**
- Transient failures (ConnectionError, TimeoutError, OSError) retry 3x with exponential backoff (0.5s, 1s, 2s)
- Permanent failures (any other Exception) log at ERROR immediately, no retry
- Existing callers unchanged — still receive `0` on failure
- `pyright src/` clean

---

## Validation (run before declaring done)

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

All four must pass. Zero regressions.

**Track B acceptance summary:**
1. `RoundRunner.__init__` takes a single `RunnerCallbacks` parameter
2. All existing tests pass (mock construction updates only)
3. `queen_runtime.py` is under 700 lines; `queen_tools.py` and `queen_thread.py` exist
4. `_post_colony_hooks()` is under 30 lines (dispatcher only); 6 hook methods exist
5. Qdrant transient failures retry 3 times; permanent failures log at ERROR
6. `pyright src/` clean. `python scripts/lint_imports.py` clean. All tests pass.

---

## Do NOT

- Add new events (union stays at 48)
- Change scoring weights or gamma-decay logic (that's Track A)
- Modify `core/types.py` or `core/events.py` (that's Track C)
- Add new test files (fix broken existing tests only)
- Change the public interface of `QueenAgent` (external imports must still work)
- Change behavioral logic — Track B is purely structural refactoring
