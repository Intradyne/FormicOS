# Wave 32 Plan — Knowledge Tuning + Structural Hardening

**Wave:** 32 — "Knowledge Tuning + Structural Hardening"
**Theme:** The knowledge system gains a principled non-stationarity mechanism (gamma-decay) and the two worst structural debts (queen god object, runner parameter explosion) are resolved. Security-critical code gets test coverage. The fundamental event-sourcing invariant (replay idempotency) is verified for the first time. After Wave 32, the system is structurally complete.
**Prerequisite:** Wave 31 landed and polished. 1,394 tests passing, 0 pyright errors, 0 ruff violations, 0 layer violations. LOC limit already resolved (20K soft, test removed).
**Contract changes:** Event union stays at 48. No new event types. 5 existing `str` fields migrate to `StrEnum` (additive, backward-compatible). New ADR-041 for gamma-decay decisions.
**Estimated LOC delta:** ~300 Python net new (mostly tests), ~800 test LOC. Net runtime LOC near-zero (queen split is restructure, RunnerCallbacks removes boilerplate). Well within 20K budget (current: 18,727).

---

## What Wave 31 Already Resolved

These items from the wave_32_planning_seed are DONE. Do not re-implement.

| Seed Item | Status | Wave 31 Resolution |
|-----------|--------|--------------------|
| B5: conf_alpha/conf_beta validators | DONE | `gt=0` on both Field definitions in types.py:313-320 |
| B6: Fire-and-forget error capture | DONE | `_log_task_exception` + `.add_done_callback()` on 6 tasks across 3 files |
| B7: Swallowed exceptions in runner.py | DONE | 4 `except Exception: pass` blocks upgraded to `log.debug` |
| B8: sentence-transformers pin | DONE | `>=5.3,<6.0` in pyproject.toml |
| Pyright errors | DONE | 73 → 0 across two fix passes |
| LOC limit | DONE | CLAUDE.md updated to ≤20K soft limit. `test_loc_budget.py` removed entirely. |
| queen_runtime test failures | DONE | isinstance guard restored with `# type: ignore[reportUnnecessaryIsInstance]` |

---

## Track B: Structural Refactoring (Lands First — Unblocks Track A)

Track B changes the shape of the files that Track A will modify. It must land and be validated before Track A starts. Track C is independent and can run in parallel with Track B.

### B1. Extract RunnerCallbacks frozen dataclass

Collapse `RoundRunner.__init__`'s 16 keyword parameters into a frozen dataclass.

**Current state verified:** `RoundRunner.__init__` at `engine/runner.py:689-707` takes exactly 16 params:
`emit`, `embed_fn`, `async_embed_fn`, `cost_fn`, `tier_budgets`, `route_fn`, `kg_adapter`, `max_rounds`, `code_execute_handler`, `service_router`, `data_dir`, `effector_config`, `catalog_search_fn`, `knowledge_detail_fn`, `artifact_inspect_fn`, `transcript_search_fn`.

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

`RoundRunner.__init__` takes `callbacks: RunnerCallbacks` as its sole parameter. Construction in `colony_manager.py` builds the dataclass, passes it in.

**Files touched:**
- `engine/runner.py` — define RunnerCallbacks, refactor `__init__` and all `self._*` accesses
- `surface/colony_manager.py` — construction site (build RunnerCallbacks, pass to RoundRunner)

**Acceptance:** Existing tests pass with minimal mock construction changes. Pyright clean.

### B2. Split queen_runtime.py into 3 modules

The headline structural refactor. **2,365 lines and 34 methods** → 3 focused files.

**Full method inventory (34 methods on QueenAgent):**
1. `__init__`, 2. `name_colony`, 3. `follow_up_colony`, 4. `_emit_queen_message`, 5. `respond`, 6. `_resolve_queen_model`, 7. `_queen_temperature`, 8. `_queen_max_tokens`, 9. `_build_messages`, 10. `_inject_nudges`, 11. `_build_thread_context`, 12. `_queen_tools`, 13. `_execute_tool`, 14. `_tool_spawn_colony`, 15. `_tool_get_status`, 16. `_tool_list_templates`, 17. `_tool_inspect_template`, 18. `_tool_inspect_colony`, 19. `_tool_read_workspace_files`, 20. `_tool_suggest_config_change`, 21. `_tool_approve_config_change`, 22. `_tool_redirect_colony`, 23. `on_governance_alert`, 24. `_tool_escalate_colony`, 25. `_tool_read_colony_output`, 26. `_tool_memory_search`, 27. `_tool_write_workspace_file`, 28. `_queen_notes_path`, 29. `_load_queen_notes`, 30. `_save_queen_notes`, 31. `save_thread_note`, 32. `_tool_queen_note`, 33. `_resolve_current_value`, 34. `_tool_define_workflow_steps`

**Decomposition:**

- `queen_runtime.py` (~600 lines) — QueenAgent class retains: `__init__`, `name_colony`, `follow_up_colony`, `_emit_queen_message`, `respond`, `_resolve_queen_model`, `_queen_temperature`, `_queen_max_tokens`, `_build_messages`, `_inject_nudges`, `_build_thread_context`. The LLM interaction loop and conversation assembly. Delegates tool dispatch and thread lifecycle to the other modules. **~11 methods stay.**

- `queen_tools.py` (~1,200 lines) — `QueenToolDispatcher` class. Contains: `queen_tool_specs()` (tool spec list), `dispatch()` (routing switch), and all tool implementations as methods: `_spawn_colony`, `_get_status`, `_list_templates`, `_inspect_template`, `_inspect_colony`, `_read_workspace_files`, `_suggest_config_change`, `_approve_config_change`, `_redirect_colony`, `_escalate_colony`, `_read_colony_output`, `_memory_search`, `_write_workspace_file`, `_queen_note`, `_resolve_current_value`. The dispatcher takes `runtime` as its single constructor dependency. **~16 methods + dispatch.**

```python
# queen_tools.py
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

- `queen_thread.py` (~500 lines) — `QueenThreadManager` class. Thread lifecycle and notes: `on_governance_alert`, `define_workflow_steps`, `notes_path`, `load_notes`, `save_notes`, `save_thread_note`. Plus the archival decay logic (currently in `_execute_tool` under the `archive_thread` tool case, lines ~1301-1356). Takes `runtime` as single constructor dependency. **~7 methods.**

**Key constraint:** The public interface of QueenAgent does not change. External code (colony_manager.py, app.py) still imports `QueenAgent` from `queen_runtime.py`. The split is internal — QueenAgent instantiates `self._tool_dispatcher = QueenToolDispatcher(self._runtime)` and `self._thread_mgr = QueenThreadManager(self._runtime)` once, delegates tool calls and thread lifecycle to them.

**Mechanical approach:** Move methods one at a time. After each move, run `pytest` and `pyright`. Do not batch moves. Start with tool implementations (largest, most self-contained), then thread lifecycle.

**Verified:** `scripts/lint_imports.py` explicitly allows surface-to-surface imports (line 25: `"surface": {"core", "engine", "adapters", "surface"}`; line 80: same-layer imports always allowed). No layer violations from the new modules.

**Files created:**
- `surface/queen_tools.py` (new)
- `surface/queen_thread.py` (new)

**Files modified:**
- `surface/queen_runtime.py` (shrinks from 2,365 to ~600 lines)

**Acceptance:** All existing tests pass. `from formicos.surface.queen_runtime import QueenAgent` still works. No layer violations. Pyright clean.

### B3. Decompose _post_colony_hooks into per-concern handlers

**Current state verified:** `_post_colony_hooks` spans lines 648-867 in colony_manager.py (220 lines, 6 concerns).

**Concern map with verified line numbers:**

| # | Concern | Current Lines | Hook Name |
|---|---------|--------------|-----------|
| 1 | Colony observation log | 662-676 | `_hook_observation_log` |
| 2 | Step detection for continuation | 686-730 | `_hook_step_detection` |
| 3 | Queen follow-up dispatch | 732-740 | `_hook_follow_up` |
| 4 | Institutional memory extraction | 742-754 | `_hook_memory_extraction` |
| 5 | Bayesian confidence update | 756-811 | `_hook_confidence_update` |
| 6 | Workflow step completion | 823-866 | `_hook_step_completion` |

**Ordering dependencies (verified in code):**
- Step detection (2) MUST run before follow-up (3) — step detection builds `step_continuation` text that follow-up passes to `queen.follow_up_colony`
- Confidence update (5) MUST run after memory extraction (4) — extraction creates entries that confidence updates reference

**Note:** Lines 693-700 (step detection) and 827-831 (step completion) both scan `workflow_steps` for the running step. The decomposition should consolidate this into a shared lookup.

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

**Files touched:**
- `surface/colony_manager.py` — decompose _post_colony_hooks into 6 named handlers + dispatcher

**Acceptance:** Dispatcher is <30 lines. Each handler is independently testable. All Wave 31 tests still pass. Step continuation still fires.

### B4. Qdrant write retry with error distinction

**Current state verified:** `adapters/vector_qdrant.py` has **3 public operations** with `except Exception: return 0`:
- `upsert()` (line 238)
- `search()` (line 272)
- `delete()` (line 303)

Plus 2 internal handlers in `ensure_collection()`: line 158 (`pass` on index creation) and line 162 (logs warning on collection setup). These are NOT the "10+" the cloud estimated — the scope is smaller.

**Implementation:**

```python
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

Wrap `upsert`, `delete`, and `search` calls. Do NOT wrap `ensure_collection` (idempotent, called once at startup, already has its own error handling).

**Files touched:**
- `adapters/vector_qdrant.py` — add `_retry_qdrant`, wrap 3 public operations

**Acceptance:** Transient failures retry 3x with exponential backoff. Permanent failures log at ERROR. Existing callers unchanged (still receive 0 on failure).

### Track B acceptance criteria

1. `RoundRunner.__init__` takes a single `RunnerCallbacks` parameter
2. All existing tests pass (mock construction updates only)
3. `queen_runtime.py` is under 700 lines; `queen_tools.py` and `queen_thread.py` exist
4. `_post_colony_hooks()` is under 30 lines (dispatcher only); 6 hook methods exist
5. Qdrant transient failures retry 3 times; permanent failures log at ERROR
6. `pyright src/` clean. `python scripts/lint_imports.py` clean. All tests pass.

### Track B file ownership

| File | Owner | Notes |
|------|-------|-------|
| `engine/runner.py` | B1 | RunnerCallbacks dataclass + `__init__` refactor |
| `surface/colony_manager.py` | B1 + B3 | RunnerCallbacks construction + hooks decomposition |
| `surface/queen_runtime.py` | B2 | Shrink to ~600 lines |
| `surface/queen_tools.py` | B2 | NEW — extracted tool implementations |
| `surface/queen_thread.py` | B2 | NEW — extracted thread/workflow/notes |
| `adapters/vector_qdrant.py` | B4 | Retry logic on 3 operations |

---

## Track A: Knowledge Tuning (After Track B Lands)

Track A applies gamma-decay and scoring normalization to the clean, decomposed code that Track B produces. **Requires ADR-041 — write and get operator approval before implementing.**

### A1. Gamma-decay for Thompson Sampling confidence (TIME-BASED)

The headline feature. Decay alpha and beta toward the prior based on elapsed wall-clock time between confidence updates, then add the new observation. See ADR-041 D1.

**Critical design decision:** Decay is **time-based, not observation-count-based.** Per-observation decay creates access-frequency-dependent half-lives — a popular entry accessed 50 times/day would forget in <1 day. Time-based decay makes the forgetting rate independent of access frequency.

**Formulation:**

```
elapsed_days = (event_timestamp - entry_last_updated_timestamp) / 86400.0
gamma_effective = GAMMA_PER_DAY ** elapsed_days

alpha_new = gamma_effective * alpha_old + (1 - gamma_effective) * PRIOR_ALPHA + reward
beta_new  = gamma_effective * beta_old  + (1 - gamma_effective) * PRIOR_BETA  + (1 - reward)
```

Where:
- `GAMMA_PER_DAY = 0.98` (half-life: `ln(0.5) / ln(0.98)` ≈ 34.3 calendar days)
- `PRIOR_ALPHA = 5.0`, `PRIOR_BETA = 5.0` (constants, not per-entry)
- `reward = 1.0` if colony succeeded, `0.0` if failed
- Hard floor: `alpha >= 1.0`, `beta >= 1.0` (Wave 31, unchanged)

**Projection prerequisite:** Add `last_confidence_update: str` (ISO timestamp) to the `memory_entries` projection dict. Set by `_on_memory_entry_created` (initial value = `created_at`) and updated by `_on_memory_confidence_updated` (value = event timestamp). This is derived projection state, replay-safe.

**Event-sourcing determinism:** Uses event timestamps exclusively, never the system clock. Each `MemoryConfidenceUpdated` event carries `new_alpha` and `new_beta` — the projection handler applies these directly. Replay produces identical state because the decay computation is baked into the emitted event values.

**Implementation site (verified):** The confidence update loop at `colony_manager.py:778-785`. Currently:

```python
old_alpha = float(entry.get("conf_alpha", 5.0))
old_beta = float(entry.get("conf_beta", 5.0))
if succeeded:
    new_alpha = old_alpha + 1.0
    new_beta = old_beta
else:
    new_alpha = old_alpha
    new_beta = old_beta + 1.0
```

Post-B3, this becomes `_hook_confidence_update`. Replace with:

```python
from datetime import datetime, timezone

GAMMA_PER_DAY = 0.98
PRIOR_ALPHA = 5.0
PRIOR_BETA = 5.0

old_alpha = float(entry.get("conf_alpha", PRIOR_ALPHA))
old_beta = float(entry.get("conf_beta", PRIOR_BETA))

# Time-based decay: use event timestamp and entry's last update timestamp
last_updated = entry.get("last_confidence_update", entry.get("created_at", ""))
if last_updated:
    elapsed_days = (event_ts - datetime.fromisoformat(last_updated)).total_seconds() / 86400.0
    elapsed_days = max(elapsed_days, 0.0)  # guard against clock skew
else:
    elapsed_days = 0.0

gamma_eff = GAMMA_PER_DAY ** elapsed_days

decayed_alpha = gamma_eff * old_alpha + (1 - gamma_eff) * PRIOR_ALPHA
decayed_beta  = gamma_eff * old_beta  + (1 - gamma_eff) * PRIOR_BETA

if succeeded:
    new_alpha = max(decayed_alpha + 1.0, 1.0)
    new_beta  = max(decayed_beta, 1.0)
else:
    new_alpha = max(decayed_alpha, 1.0)
    new_beta  = max(decayed_beta + 1.0, 1.0)
```

**What this solves:** An entry observed many times locks into its current confidence. With time-based gamma-decay, entries that aren't accessed for ~34 days have their alpha/beta decayed halfway back toward the prior, widening uncertainty and re-enabling Thompson Sampling exploration. Multiple observations on the same day barely decay between them (elapsed_days is small).

**Numerical expectations for test assertions:**
- Entry starts at Beta(5,5). Observed once per day for 40 days alternating success/failure. After 40 days, alpha and beta stabilize around ~5.5 (prior + small accumulated signal that gets decayed). After 5 more consecutive successes, posterior mean should be in [0.58, 0.72].
- Simpler test: after 100 alternating observations (1/day), `alpha + beta < 20` (decay prevents unbounded accumulation).
- After success: `new_alpha > old_alpha` AND `new_alpha < old_alpha + 1.0` (decay ate some).

**Files touched:**
- `surface/colony_manager.py` — gamma-decay in `_hook_confidence_update`
- `surface/projections.py` — add `last_confidence_update` field to memory_entries projection

### A2. Archival decay redesign — gamma-burst at 30-day equivalent

**Current formula (verified at queen_runtime.py:1330-1331):**
```python
new_alpha = max(old_alpha * 0.8, 1.0)
new_beta = max(old_beta * 1.2, 1.0)
```

This is asymmetric — biases the posterior mean downward rather than just widening uncertainty.

**Wave 32 replacement — gamma-burst at 30-day equivalent (ADR-041 D2):**

```python
ARCHIVAL_EQUIVALENT_DAYS = 30
archival_gamma = GAMMA_PER_DAY ** ARCHIVAL_EQUIVALENT_DAYS  # 0.98^30 ≈ 0.545

new_alpha = max(archival_gamma * old_alpha + (1 - archival_gamma) * PRIOR_ALPHA, 1.0)
new_beta  = max(archival_gamma * old_beta  + (1 - archival_gamma) * PRIOR_BETA, 1.0)
```

**Properties:**
- Symmetric: both alpha and beta decay toward the prior at the same rate. Does not bias the posterior mean.
- Composes with gamma-decay: one formula family, two rates.
- Hard floor preserved: `max(..., 1.0)` prevents parameters going below Beta(1,1).
- At 0.545, archiving roughly halves the distance from current parameters to the prior. An entry with alpha=20 decays to ~13.2. Still above prior, but with wider uncertainty.

**Applied uniformly** to all thread-scoped entries. **Hardcoded, not configurable.**

**Files touched:**
- `surface/queen_thread.py` (post-B2) — the archive_thread tool handler moves here

### A3. Scoring normalization

**CORRECTION from cloud plan:** There is NO parallel `_composite_key` in `memory_store.py`. Memory store delegates to Qdrant's native scoring. Only `knowledge_catalog.py` has composite scoring.

**Current values (verified at knowledge_catalog.py:124-127, 137, 163):**

```python
# Status bonus — NOT [0,1]
_STATUS_BONUS = {"verified": 0.3, "active": 0.25, "candidate": 0.0, "stale": -0.2}
# Default for unknown: -0.5

# Thread bonus — NOT [0,1]
_THREAD_BONUS = 0.25
```

**Normalized (ADR-041 D3):**

```python
_STATUS_BONUS = {"verified": 1.0, "active": 0.8, "candidate": 0.5, "stale": 0.0}
# Default for unknown: 0.0 (no information, treated as stale)

_THREAD_BONUS = 1.0  # weight 0.08 already scales contribution
```

**Recalibrated weights (sum to 1.00):**

```python
# Old: 0.35 semantic, 0.25 thompson, 0.15 freshness, 0.15 status, 0.10 thread
# New:
WEIGHTS = {
    "semantic": 0.40,   # dominant signal, slightly increased
    "thompson": 0.25,   # exploration budget, unchanged
    "freshness": 0.15,  # unchanged
    "status": 0.12,     # reduced — [0,1] range wider than old [-0.5, 0.3]
    "thread": 0.08,     # reduced — [0,1] range wider than old [0, 0.25]
}
```

**Validate with invariants (not frozen rankings):**
1. At equal semantic similarity and freshness, a verified entry always outranks stale
2. At equal everything else, a thread-matched entry outranks non-matched
3. Thompson Sampling produces different rankings on successive calls (exploration working)
4. A very old entry (freshness=0.0) can still rank highly if verified and semantically relevant

**Files touched:**
- `surface/knowledge_catalog.py` — `_composite_key`, `_STATUS_BONUS`, `_THREAD_BONUS`, weights

**NOT touched:** `surface/memory_store.py` (no composite scoring implementation exists there)

### A4. ADR-041: Knowledge Tuning

**ALREADY WRITTEN** at `docs/decisions/041-knowledge-tuning.md`. Status: Proposed. Requires operator approval before A1-A3 implementation begins.

Decisions documented:
- D1: Time-based gamma-decay at GAMMA_PER_DAY=0.98 (half-life ~34.3 calendar days)
- D2: Archival decay via gamma-burst at 30-day equivalent (0.98^30 ≈ 0.545)
- D3: Scoring normalized to [0,1], recalibrated weights summing to 1.00
- D4: Prior remains Beta(5.0, 5.0) — deferred pending empirical evaluation
- D5: RRF rejected — incompatible with Thompson Sampling exploration signal

### Track A acceptance criteria

1. Gamma-decay: entry observed 40 times at 50/50 then 5 more times at 100% success — alpha rises meaningfully (not locked at ~0.5)
2. Gamma-decay: replay of same events produces identical confidence values (deterministic)
3. Archival decay: symmetric (doesn't bias mean), converges toward prior not toward zero
4. Archival decay: hard floor (alpha >= 1.0, beta >= 1.0) still holds
5. Scoring: all signals in [0, 1] in `_composite_key`. Existing Thompson Sampling ranking tests pass after recalibration.

### Track A file ownership

| File | Owner | Notes |
|------|-------|-------|
| `surface/colony_manager.py` | A1 | Gamma-decay in `_hook_confidence_update` |
| `surface/projections.py` | A1 | Add `last_confidence_update` field to memory_entries |
| `surface/queen_thread.py` | A2 | Archival decay redesign (post-B2 extraction) |
| `surface/knowledge_catalog.py` | A3 | Scoring normalization + weight recalibration |
| `docs/decisions/041-knowledge-tuning.md` | A4 | ALREADY WRITTEN — needs operator approval |

---

## Track C: Test Coverage + Type Safety (Independent — Parallel with B)

### C1. Security-critical tests

81 lines in `adapters/ast_security.py` and 26 lines in `adapters/output_sanitizer.py` have zero unit tests. Only indirect feature-level coverage exists in `tests/features/steps/wave14_steps.py`.

**ast_security.py tests:**
- Blocked modules: os, subprocess, sys, shutil, socket, ctypes
- Bypass vectors: `importlib.import_module("os")`, `eval("__import__('os')")`, `getattr(__builtins__, '__import__')`, `numpy.ctypeslib` (if numpy available)
- Allowed operations: math, string ops, list comprehensions, function definitions
- Nested imports: `from os import path` inside a function body

**output_sanitizer.py tests:**
- XSS payloads: `<script>alert(1)</script>`, `<img onerror=...>`, `javascript:` URLs
- Clean text passthrough unchanged
- Multi-line output with mixed clean and malicious content
- Edge cases: nested tags, attribute injection, event handlers

**Files created:**
- `tests/unit/adapters/test_ast_security.py`
- `tests/unit/adapters/test_output_sanitizer.py`

### C2. Replay idempotency test

Fundamental event-sourcing invariant: applying the same event sequence twice from empty state produces identical projection state.

**Implementation:**
1. Build `build_representative_event_sequence()` covering all 48 event types (verified: 48 types in `EVENT_TYPE_NAMES` at events.py:904-953)
2. Create ProjectionStore A, replay all events → snapshot
3. Create ProjectionStore B, replay all events → snapshot
4. Assert A == B (deep equality)
5. Double-apply test: replay events, then replay again — counters like `colony_count` must not double

**Files created:**
- `tests/unit/test_replay_idempotency.py`

### C3. StrEnum migration for 6 fields

**CORRECTION from cloud plan:** `scan_status` is on `MemoryEntry` in `core/types.py`, NOT an event field. It requires a different migration path (model field type change, not event field change).

**Event fields (5) — in `core/events.py`:**

| Field | Event Class | Line | Values |
|-------|------------|------|--------|
| `approval_type` | `ApprovalRequested` | 370 | "budget_increase", "cloud_burst", "tool_permission", "expense" |
| `priority` | `ServiceQuerySent` | 540-541 | "normal" (default), "high" |
| `trigger` | `ColonyRedirected` | 649-651 | "queen_inspection", "governance_alert", "operator_request" |
| `merge_reason` | `SkillMerged` | 453 | "llm_dedup" |
| `access_mode` | `KnowledgeAccessRecorded` | 724-729 | "context_injection", "tool_search", "tool_detail", "tool_transcript" |

**Model field (1) — in `core/types.py`:**

| Field | Model | Values |
|-------|-------|--------|
| `scan_status` | `MemoryEntry` | "pending", "safe", "low", "medium", "high", "critical" |

Create StrEnums in `core/types.py`. Migrate the 5 event fields in `core/events.py` and the 1 model field in `core/types.py`. Mirror changes in `docs/contracts/events.py`.

**Backward compatibility:** Pydantic v2 deserializes strings into StrEnums transparently. Add a test: construct events from raw dicts with string values, verify StrEnum fields populate correctly.

**Enumerate actual values from codebase usage** before defining the enums. The values listed above come from grep — the coder should verify exhaustiveness.

**Files touched:**
- `core/types.py` — StrEnum definitions + `scan_status` field migration
- `core/events.py` — 5 field type changes
- `docs/contracts/events.py` — mirror changes

### C4. Projection handler coverage toward 100%

**Verified:** 46 `_on_*` handlers in `surface/projections.py`. 23 tested across `test_projections_w11.py` and `test_round_projections.py`.

**Priority untested handlers (Wave 28-31 additions):**
- `_on_memory_confidence_updated`
- `_on_workflow_step_defined`
- `_on_workflow_step_completed` (including Wave 31 `continuation_depth` increment)
- `_on_knowledge_access_recorded`
- `_on_memory_entry_scope_changed`
- `_on_thread_status_changed`
- `_on_deterministic_service_registered`
- `_on_memory_entry_created`
- `_on_memory_entry_status_changed`

**Pattern:** For each handler: construct a ProjectionStore, apply prerequisite events, apply the target event, assert projection state.

**Files created:**
- `tests/unit/surface/test_projection_handlers_full.py`

### C5. Untested high-risk file coverage — DEFERRED TO WAVE 33

Deferred per cloud decision. Will be dramatically easier to write once MockLLM (C6) exists.

| File | LOC | Wave 33 test file |
|------|-----|-----------|
| `surface/view_state.py` | 638 | `test_view_state.py` |
| `surface/memory_store.py` | 402 | `test_memory_store_ops.py` |
| `surface/maintenance.py` | 382 | `test_maintenance_handlers.py` |
| `surface/mcp_server.py` | 295 | `test_mcp_server.py` |

### C6. MockLLM creation (IN SCOPE — force multiplier for Wave 33)

**CORRECTION:** No MockLLM currently exists in `tests/conftest.py` — conftest.py is minimal (path setup + pytest-bdd plugin registration only). This is a fresh creation, not an upgrade.

```python
class MockLLM:
    """Configurable mock for LLM calls. Records all invocations."""
    def __init__(self, responses: list[str] | None = None):
        self.calls: list[dict[str, Any]] = []
        self._responses = responses or ["Test output"]
        self._call_idx = 0

    async def complete(self, *, model, messages, tools=None, temperature=0.0, max_tokens=4096):
        self.calls.append({"model": model, "messages": messages, "tools": tools, "temperature": temperature})
        response_text = self._responses[min(self._call_idx, len(self._responses) - 1)]
        self._call_idx += 1
        return MockResponse(content=response_text, tool_calls=[])
```

**Files touched:**
- `tests/conftest.py` — add MockLLM class

### Track C acceptance criteria

1. ast_security tests cover blocked modules + 3 bypass vectors (at least 8 test cases)
2. output_sanitizer tests cover XSS payloads + clean passthrough (at least 5 test cases)
3. Replay idempotency: applying events twice produces identical state; double-apply doesn't double counters
4. 6 StrEnum types created, 5 event fields + 1 model field migrated, backward compatibility test passes
5. At least 9 new projection handler tests covering Wave 28-31 handlers
6. MockLLM records call arguments and supports configurable responses
7. `pytest` clean after all changes

### Track C file ownership

| File | Owner | Notes |
|------|-------|-------|
| `tests/unit/adapters/test_ast_security.py` | C1 | NEW |
| `tests/unit/adapters/test_output_sanitizer.py` | C1 | NEW |
| `tests/unit/test_replay_idempotency.py` | C2 | NEW |
| `core/types.py` | C3 | StrEnum definitions + scan_status migration |
| `core/events.py` | C3 | 5 field type changes |
| `docs/contracts/events.py` | C3 | Mirror field type changes |
| `tests/unit/surface/test_projection_handlers_full.py` | C4 | NEW |
| `tests/conftest.py` | C6 | MockLLM creation (IN SCOPE) |

---

## File Ownership Matrix

| File | Track A | Track B | Track C | Notes |
|------|---------|---------|---------|-------|
| `surface/colony_manager.py` | A1: gamma-decay | B1 + B3: callbacks + hooks | — | **B lands first, A modifies clean structure** |
| `surface/projections.py` | A1: `last_confidence_update` | — | — | New derived field on memory_entries |
| `surface/queen_runtime.py` | — | B2: split to ~600 lines | — | |
| `surface/queen_tools.py` | — | B2: **CREATE** (`QueenToolDispatcher`) | — | |
| `surface/queen_thread.py` | A2: archival decay | B2: **CREATE** (`QueenThreadManager`) | — | A2 targets this after B2 creates it |
| `surface/knowledge_catalog.py` | A3: scoring normalization | — | — | |
| `engine/runner.py` | — | B1: RunnerCallbacks | — | |
| `adapters/vector_qdrant.py` | — | B4: retry logic | — | |
| `core/types.py` | — | — | C3: StrEnums + scan_status | |
| `core/events.py` | — | — | C3: field migrations | |
| `docs/contracts/events.py` | — | — | C3: mirror | |
| `docs/decisions/041-*.md` | A4: **ALREADY WRITTEN** | — | — | Needs operator approval |
| `tests/` (various) | — | — | C1-C4, C6: **CREATE** 5 files | |

---

## Sequencing

**Critical constraint: Track B must land before Track A.**

Track B restructures the files that Track A modifies. If Track A runs on the old structure and Track B then restructures, Track A's changes land in the wrong files.

**Execution order:**

1. **Track C starts immediately** (fully independent — tests and type safety)
2. **Track B starts immediately** (structural refactoring, no behavioral changes)
3. **Track A starts after Track B lands** (behavioral changes to the cleaned-up structure)
4. **Integration pass** after all three land

**Track B parallel teams:**
- Team 1: B1 (RunnerCallbacks) + B3 (_post_colony_hooks decomposition) — both touch colony_manager.py but B1 changes the constructor while B3 changes the hook method, non-overlapping
- Team 2: B2 (queen_runtime split) — the big one, independent
- Team 3: B4 (Qdrant retry) — adapters layer, fully independent

**Track C parallel teams:**
- Team 1: C1 (security tests) + C4 (projection handlers) — new test files, no source overlap
- Team 2: C3 (StrEnums) + C2 (replay idempotency) — core changes + fundamental invariant
- Team 3: C6 (MockLLM) — standalone, no source overlap (C5 deferred to Wave 33)

**If 3 teams must start simultaneously:** Start B and C in parallel. Third team writes ADR-041 and gamma-decay acceptance tests while waiting for B. Once B lands, third team implements A1-A3.

---

## What Wave 32 Does NOT Include

- **No new events.** Union stays at 48. StrEnum migration changes field types, not event types.
- **No new agent tools.** Tool count stays at 11.
- **No RRF.** Research confirmed it suppresses Thompson Sampling's exploration signal.
- **No three-tier autonomy.** Wave 31's continuation_depth counter remains the safety mechanism.
- **No prior reduction.** Evaluate gamma-decay empirically first. Revisit Beta(2,2) in Wave 33 if needed.
- **No high-risk file test coverage (C5).** Deferred to Wave 33. MockLLM (C6) is in scope as a force multiplier.
- **No composable dashboards.** Still aspirational.

---

## Priority Stack (if scope must be cut)

| Priority | Item | Rationale |
|----------|------|-----------|
| 1 | C1: Security tests | 107 LOC of untested security code |
| 2 | C2: Replay idempotency | Fundamental invariant, never verified |
| 3 | A1+A2: Gamma-decay + archival redesign | Headline deferred work from Wave 31 |
| 4 | B2: queen_runtime split | Highest developer-velocity impact |
| 5 | B1: RunnerCallbacks | Testing ergonomics for every future wave |
| 6 | C3: StrEnum migration | Type safety at event boundary |
| 7 | B3: _post_colony_hooks decomposition | Maintainability, independently testable hooks |
| 8 | B4: Qdrant retry | Silent write failures become visible + retried |
| 9 | A3: Scoring normalization | Correctness improvement, low urgency |
| 10 | C4: Projection handler coverage | Valuable but not blocking |
| 11 | C6: MockLLM | In scope but lowest priority within Wave 32 |
| — | C5: Untested high-risk files | Deferred to Wave 33 |

---

## ADR-041 — Already Written

Full ADR at `docs/decisions/041-knowledge-tuning.md`. Status: Proposed. Requires operator approval before Track A implementation begins.

Key decisions:
- D1: **Time-based** gamma-decay at GAMMA_PER_DAY=0.98 (half-life ~34.3 calendar days, not per-observation)
- D2: Archival decay via gamma-burst at **30-day** equivalent (0.98^30 ≈ 0.545)
- D3: Scoring normalized to [0,1], weights recalibrated to sum to 1.00 (0.40/0.25/0.15/0.12/0.08)
- D4: Prior stays Beta(5.0, 5.0) — deferred
- D5: RRF rejected

---

## Smoke Test (Post-Integration)

1. Create workspace, thread, goal, 3 workflow steps
2. Run 3 colonies through the workflow (step continuation from Wave 31 should still work)
3. Verify gamma-decay: inspect confidence values after colony completion — alpha/beta should show decay toward prior
4. Archive the thread — verify symmetric archival decay (both alpha and beta move toward prior)
5. Check scoring: all composite score signals in [0, 1] (temporary `log.debug` in `_composite_key`)
6. Verify replay idempotency: export events, rebuild projections, compare
7. Full test suite passes including new security, replay, projection, and StrEnum tests
8. `pyright src/` — zero errors
9. `python scripts/lint_imports.py` — zero violations
10. `queen_runtime.py` under 700 lines

Record whether smoke tests code-as-written or code-as-deployed. If Docker was not rebuilt, say so.

---

## Corrections from Local Audit

These corrections were applied to this plan based on codebase verification:

| Cloud Assumption | Reality | Impact |
|-----------------|---------|--------|
| memory_store.py has parallel `_composite_key` | No composite scoring in memory_store — delegates to Qdrant | A3 scope reduced: only knowledge_catalog.py needs changes |
| QueenAgent has 27 methods | 34 methods | B2 extraction is larger but more justified |
| queen_runtime.py is 2,352 lines | 2,365 lines | Minor drift, no impact |
| Qdrant has 10+ `except Exception` blocks | 3 public + 2 internal = 5 total | B4 scope reduced: wrap 3 operations, not 10+ |
| scan_status is an event field | It's on MemoryEntry in types.py | C3 needs split approach: 5 event fields + 1 model field |
| MockLLM exists in conftest.py | conftest.py is minimal, no MockLLM | C6 is creation, not upgrade |
| LOC limit needs resolution | Already done in Wave 31 (20K soft, test removed) | Remove from Wave 32 scope entirely |
| Tests: 1,397 | 1,394 (post queen_runtime fix) | Minor — 3 test count variance from LOC budget test removal |
