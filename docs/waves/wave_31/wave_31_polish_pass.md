# Wave 31 Polish Pass — Hardening Quick Wins

**Track:** Single coder
**Wave:** 31 — post-integration polish
**Scope:** Mechanical fixes only. No new features, no structural refactors.

---

## Reading Order

1. This file (you're reading it)
2. `CLAUDE.md` — hard constraints, prohibited alternatives
3. `pyproject.toml` — dependency list

---

## Your Files

| File | Action |
|------|--------|
| `src/formicos/core/types.py` | **EDIT** — conf_alpha/conf_beta validators |
| `pyproject.toml` | **EDIT** — sentence-transformers version pin |
| `src/formicos/engine/runner.py` | **EDIT** — upgrade swallowed exceptions to debug logs |
| `src/formicos/surface/colony_manager.py` | **EDIT** — add error callbacks to fire-and-forget tasks |
| `src/formicos/surface/app.py` | **EDIT** — add error callback to maintenance loop task |
| `src/formicos/surface/queen_runtime.py` | **EDIT** — add error callback to fire-and-forget task |

## Do NOT Touch

- Any `tests/` files (add no new tests — these are mechanical fixes)
- Any `docs/` files
- `CLAUDE.md`, `AGENTS.md`
- `surface/knowledge_catalog.py`
- `surface/maintenance.py`
- `surface/runtime.py`
- `surface/projections.py`
- `frontend/` files
- `config/` files
- `core/events.py`

---

## Task 1: conf_alpha/conf_beta Validators (types.py)

**Why:** Division by zero if `alpha + beta == 0`. Corrupted replay or bad event data could produce this. One-line defensive guard per field.

In `src/formicos/core/types.py`, lines 313-320. Current:

```python
conf_alpha: float = Field(
    default=5.0,
    description="Beta distribution alpha. Prior strength 10 split evenly (Wave 30).",
)
conf_beta: float = Field(
    default=5.0,
    description="Beta distribution beta. Prior strength 10 split evenly (Wave 30).",
)
```

Add `gt=0` to both:

```python
conf_alpha: float = Field(
    default=5.0,
    gt=0,
    description="Beta distribution alpha. Prior strength 10 split evenly (Wave 30).",
)
conf_beta: float = Field(
    default=5.0,
    gt=0,
    description="Beta distribution beta. Prior strength 10 split evenly (Wave 30).",
)
```

This is Pydantic v2 schema-level enforcement. Any event or type carrying these fields will reject `0.0` or negative values at deserialization time.

---

## Task 2: Pin sentence-transformers Version (pyproject.toml)

**Why:** Unpinned dependency. A major version bump could silently change the embedding space, making all stored vectors incomparable with new ones. The currently installed version is **5.3.0**.

In `pyproject.toml`, line 12. Current:

```toml
"sentence-transformers",
```

Change to:

```toml
"sentence-transformers>=5.3,<6.0",
```

This pins to the current major version while allowing patch/minor updates.

---

## Task 3: Upgrade Swallowed Exceptions in runner.py

**Why:** Four `except Exception: pass` blocks in the `_build_memory_context` function (lines 413, 422, 443, 455) completely swallow infrastructure failures. If Qdrant is down, the agent gets empty results with zero diagnostic signal.

These are in the memory search pipeline (`_build_memory_context`, lines ~405-456). They are expected during normal operation when a collection doesn't exist yet, so use `log.debug` (not WARNING).

Replace all four blocks. Pattern:

```python
# BEFORE (4 occurrences):
except Exception:
    pass

# AFTER:
except Exception:
    log.debug("memory_context.search_failed", collection=<collection_var>, query=query[:80])
```

Specific replacements:

**Line 413** (scratch collection search):
```python
except Exception:
    log.debug("memory_context.scratch_search_failed", collection=scratch_coll)
```

**Line 422** (workspace memory search):
```python
except Exception:
    log.debug("memory_context.workspace_search_failed", collection=workspace_id)
```

**Line 443** (knowledge catalog search):
```python
except Exception:
    log.debug("memory_context.catalog_search_failed")
```

**Line 455** (legacy skill bank fallback):
```python
except Exception:
    log.debug("memory_context.skillbank_search_failed", collection=skill_coll)
```

Ensure `log` is already imported at the top of the file (it should be — check for `structlog.get_logger`). If not, add:
```python
import structlog
log = structlog.get_logger()
```

---

## Task 4: Fire-and-Forget Error Callbacks (colony_manager.py, app.py, queen_runtime.py)

**Why:** `asyncio.create_task()` without an error callback means unhandled exceptions in the coroutine are silently dropped (Python logs a "Task exception was never retrieved" warning to stderr, but structlog never sees it). These are fire-and-forget tasks where failures should be visible in structured logs.

### Step 4a: Add a shared helper at the top of colony_manager.py

After the existing `log = structlog.get_logger()` line, add:

```python
def _log_task_exception(task: asyncio.Task[Any]) -> None:
    """Error callback for fire-and-forget tasks."""
    if not task.cancelled() and task.exception() is not None:
        log.error(
            "fire_and_forget_failed",
            task_name=task.get_name(),
            error=str(task.exception()),
        )
```

### Step 4b: Attach to fire-and-forget tasks in colony_manager.py

There are 4 fire-and-forget `create_task` calls that need the callback. For each, assign the task to a variable (if not already) and add `.add_done_callback(_log_task_exception)`.

**Line 191** (`_name_colony`):
```python
_naming_task = asyncio.create_task(self._name_colony(colony_id))
_naming_task.add_done_callback(_log_task_exception)
```

**Lines 495-502** (governance alert):
```python
_gov_task = asyncio.create_task(
    self._runtime.queen.on_governance_alert(
        colony_id=colony_id,
        workspace_id=colony.workspace_id,
        thread_id=colony.thread_id,
        alert_type="stall_detected",
    ),
)
_gov_task.add_done_callback(_log_task_exception)
```

**Lines 722-727** (`_follow_up_colony`):
```python
_followup_task = asyncio.create_task(self._follow_up_colony(
    colony_id=colony_id,
    workspace_id=ws_id,
    thread_id=th_id,
    step_continuation=step_continuation,
))
_followup_task.add_done_callback(_log_task_exception)
```

**Lines 738+** (`_extract_institutional_memory`):
```python
_memory_task = asyncio.create_task(self._extract_institutional_memory(
    ...  # existing args unchanged
))
_memory_task.add_done_callback(_log_task_exception)
```

**Note:** The `_run_colony` task at line 193 already has a done callback (line 195) — do NOT add a second one.

### Step 4c: app.py maintenance loop task

Find the `asyncio.create_task(_maintenance_loop())` call (line 586). Add a callback:

```python
_maint_task = asyncio.create_task(_maintenance_loop())
_maint_task.add_done_callback(_log_task_exception)
```

You will need to either import the helper from colony_manager or define a local version. **Define a local version** — do not create a cross-module import for a 5-line helper. Copy the same pattern:

```python
def _log_task_exception(task: asyncio.Task[Any]) -> None:
    if not task.cancelled() and task.exception() is not None:
        log.error("fire_and_forget_failed", task_name=task.get_name(), error=str(task.exception()))
```

Place it near the top of the lifespan function or at module level.

### Step 4d: queen_runtime.py fire-and-forget task

Search for `asyncio.create_task` in queen_runtime.py. There should be one at approximately line 1442. Apply the same pattern.

Define the same local `_log_task_exception` helper (same pattern — do not import from colony_manager).

---

## Acceptance Criteria

1. `conf_alpha: float = Field(default=5.0, gt=0, ...)` in types.py
2. `conf_beta: float = Field(default=5.0, gt=0, ...)` in types.py
3. `sentence-transformers>=5.3,<6.0` in pyproject.toml
4. Zero `except Exception: pass` blocks in runner.py `_build_memory_context`
5. All fire-and-forget `create_task` calls in colony_manager.py have `_log_task_exception` callback
6. app.py maintenance loop task has error callback
7. queen_runtime.py fire-and-forget task has error callback

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Run this before declaring done. All must pass. The 73 pre-existing pyright errors are acceptable; do not introduce new ones.

## What This Does NOT Include

- No new tests (these are defensive guards, not new behavior)
- No structural refactors (RunnerCallbacks, queen split, hooks decomposition — those are Wave 32)
- No StrEnum migration (Wave 32 Track C)
- No Qdrant retry logic (Wave 32 Track B)
- No scoring normalization (Wave 32 Track A)
- No embedding fallback warning (requires design decision about mixed-space indexes)
