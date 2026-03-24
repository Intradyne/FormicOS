# Wave 32 Planning Seed -- Knowledge Tuning + Structural Hardening

**Status:** Pre-planning. Wave 31 is in progress. This document captures verified findings and deferred scope to seed Wave 32 planning after Wave 31 lands and is operator-tested.
**Date:** 2026-03-17
**Inputs:** ADR-040 D6 (deferred Wave 31 scope), orchestrator ground-up codebase audit (18 findings), two deep research passes

---

## Two themes converge in Wave 32

**Theme 1: Knowledge Tuning (from ADR-040 D6).** Gamma-decay for Thompson Sampling, archival decay formula redesign, scoring normalization. This was explicitly deferred from Wave 31 as "new architecture, not polish." The research established gamma ~0.98, the archival decay asymmetry problem, and RRF deprioritization. All details are in ADR-040 D6.

**Theme 2: Structural Hardening (from codebase audit).** The orchestrator's audit found 18 issues across data integrity, architectural debt, error handling, test coverage, and security. None are Wave 31 blockers, but several compound over time: silent Qdrant write failures, swallowed exceptions in the agent tool pipeline, a 2,352-line god object, and 41 source files with zero test coverage.

These themes are independent. They can run as parallel tracks.

---

## Verified audit findings (all confirmed against codebase)

### Data integrity -- could lose data or corrupt state

| # | Finding | File | Severity | Verified |
|---|---------|------|----------|----------|
| 1 | Qdrant upsert silently returns 0 on failure -- no retry, no error distinction | vector_qdrant.py:238 | HIGH | 10+ except-and-return-0 blocks confirmed |
| 2 | conf_alpha/conf_beta accept 0.0 -- causes division by zero in posterior mean | types.py:313-320 | HIGH | No gt=0 validator, Field(default=5.0) only |
| 3 | ColonyCompleted.artifacts is list[dict] not list[Artifact] -- malformed dicts pass validation | events.py:181 | MEDIUM | Artifact model exists in types.py but unused in events |
| 4 | 6 stringly-typed event fields (scan_status, approval_type, access_mode, priority, trigger, merge reason) | events.py various | MEDIUM | Confirmed: bare str, no StrEnum |

### Architectural debt -- will compound

| # | Finding | File | Impact |
|---|---------|------|--------|
| 5 | RoundRunner.__init__ has 16+ parameters (growing ~3/wave) | runner.py:663-679 | Testing burden, constructor fragility |
| 6 | queen_runtime.py is 2,352 lines, 27 methods: LLM loop + 16 tools + nudging + governance | queen_runtime.py | Any tool change requires full-class context load |
| 7 | _post_colony_hooks() is 200+ lines spanning 5 waves of concerns | colony_manager.py:633-794 | Wave 31 adds step continuation, making it worse |
| 8 | N+1 query in thread-boosted search (2 Qdrant round-trips) | knowledge_catalog.py:233-299 | Doubles retrieval latency for thread-scoped queries |

### Reliability -- silent failures

| # | Finding | File | Impact |
|---|---------|------|--------|
| 9 | Embedding fallback silently switches embedding spaces (Qwen3 -> sentence-transformers) | app.py:194-220 | Incomparable vectors, wrong results with no warning |
| 10 | sentence-transformers has no version pin | pyproject.toml | Future release could break all vector indexes |
| 11 | 7 asyncio.create_task() calls with no error callback | colony_manager.py, app.py | Failed tasks invisible to operator |
| 12 | 4 except Exception: pass blocks in agent tool pipeline | runner.py:387-430 | Infrastructure failures completely swallowed |

### Test gaps

| # | Finding | Impact |
|---|---------|--------|
| 13 | 41 source files with zero test coverage (most dangerous: view_state, memory_store, maintenance, mcp_server, ast_security, output_sanitizer) | UI bugs, persistence bugs, security bypasses slip through |
| 14 | Projection handler coverage ~50% (23/46). Wave 30 handlers untested. | Replay correctness unverified for newest features |
| 15 | No replay idempotency test (apply same events twice -> identical state) | Fundamental event-sourcing invariant never checked |
| 16 | MockLLM always returns "Test output" -- ignores all inputs | Prompt construction bugs, tool-call parsing issues invisible |

### Security

| # | Finding | Impact |
|---|---------|--------|
| 17 | AST security check is allowlist-via-blocklist -- untested paths for numpy.ctypeslib, reflection, eval workarounds | Primary defense is Docker sandbox, AST check is porous |
| 18 | Docker socket mounted in compose for code_execute -- no rate limiting on sandbox creation | Host compromise risk if sandbox manager exploited |

---

## Recommended Wave 32 shape: 3 parallel tracks

### Track A: Knowledge Tuning (ADR-040 D6 scope)

This is the deferred Wave 31 work. Requires a dedicated ADR (ADR-041).

**A1. Gamma-decay implementation.**
- Formulation: `alpha_new = gamma * alpha + (1-gamma) * alpha_0 + reward`
- gamma = 0.98 (half-life ~35 observations at 5 obs/day)
- Apply decay at observation time using event timestamps for replay determinism
- Never use system clock during replay -- always event timestamps
- Modifies: colony_manager.py _post_colony_hooks A3 block (confidence update loop)

**A2. Archival decay redesign.**
- Current: asymmetric `alpha *= 0.8, beta *= 1.2` (biases mean downward, compounds with gamma-decay)
- Wave 31 adds hard-floor enforcement (alpha >= 1.0, beta >= 1.0) as a stopgap
- Wave 32 options (choose one): (a) symmetric decay (alpha *= 0.9, beta *= 0.9), (b) lower-gamma for archived entries (gamma_archived = 0.85 vs gamma_active = 0.98), (c) remove archival decay entirely and let gamma-decay + stale sweep handle it
- Modifies: queen_runtime.py archive_thread handler (lines 1275-1308)

**A3. Prior reduction evaluation.**
- Consider reducing from Beta(5.0, 5.0) to Beta(2.0, 2.0) alongside gamma-decay
- Requires migration strategy for existing entries: either (a) migration event that resets all priors, (b) apply gamma-decay retroactively from creation time, or (c) accept dual-prior coexistence
- This is a tuning decision -- evaluate empirically before committing

**A4. Scoring normalization.**
- Normalize status_bonus from {-0.5, -0.2, 0.0, 0.25, 0.3} to [0, 1]
- Normalize thread_bonus from {0.0, 0.25} to [0, 1]
- Verify semantic similarity, Thompson sample, and freshness are already [0, 1]
- RRF is deprioritized (would cripple Thompson exploration) -- keep weighted linear
- Modifies: knowledge_catalog.py _composite_key, memory_store.py composite scoring

**Track A files:**
- `surface/colony_manager.py` -- gamma-decay in confidence update loop
- `surface/queen_runtime.py` -- archival decay redesign
- `surface/knowledge_catalog.py` -- scoring normalization
- `surface/memory_store.py` -- scoring normalization (parallel implementation)
- `core/types.py` -- prior default change if A3 proceeds

### Track B: Structural Refactoring + Reliability

**B1. Extract RunnerCallbacks dataclass.**
- Collapse 16+ __init__ parameters into a frozen dataclass
- Makes testing vastly simpler (one mock object instead of 16 keyword args)
- Modifies: engine/runner.py (class definition), surface/colony_manager.py (construction site)

**B2. Split queen_runtime.py into 3 modules.**
- `queen_runtime.py` -- QueenAgent class: LLM loop, message building, nudges (~400 lines)
- `queen_tools.py` -- tool implementations: spawn_colony, kill_colony, get_status, etc. (~800 lines)
- `queen_thread.py` -- thread management: archive, complete, workflow steps, context building (~400 lines)
- Keep the public interface unchanged -- QueenAgent delegates to the other modules
- This is the single highest-value refactor for developer velocity

**B3. Split _post_colony_hooks into per-concern handlers.**
- Extract into named async functions: `_hook_observation_log`, `_hook_step_continuation`, `_hook_follow_up`, `_hook_memory_extraction`, `_hook_confidence_update`, `_hook_workflow_step_completion`
- Each handler is independently testable
- The main method becomes a dispatcher that calls them in sequence
- Modifies: surface/colony_manager.py

**B4. Qdrant write retry with error distinction.**
- Distinguish "Qdrant unavailable" (ConnectionError, TimeoutError) from "malformed input" (ValueError, validation errors)
- Retry transient failures with exponential backoff (3 attempts, 0.5s/1s/2s)
- Log permanent failures at ERROR (not WARNING) with entry_id for reconciliation
- Add a "pending sync" set: entries that failed Qdrant write get queued for retry on next successful health check
- Modifies: adapters/vector_qdrant.py

**B5. conf_alpha/conf_beta validators.**
- Add `gt=0` to both Field definitions in types.py
- Add `ge=0.1` floor to the `max()` call in _composite_key (already uses max(alpha, 0.1) but this makes it schema-enforced)
- One-line change, prevents division-by-zero on corrupted replay

**B6. Fire-and-forget error capture.**
- Add error callback to all 7 asyncio.create_task() calls
- Pattern: `task = asyncio.create_task(coro); task.add_done_callback(_log_task_error)`
- Where `_log_task_error` checks `task.exception()` and logs at ERROR with task name
- Promotes invisible failures to operator-visible structured logs

**B7. Upgrade swallowed exceptions in runner.py.**
- Replace 4 `except Exception: pass` blocks (lines 387-430) with `except Exception: log.debug("tool_pipeline.swallowed", ...)`
- Not WARNING (these are expected during normal operation when catalog is unavailable) but DEBUG ensures they appear in verbose diagnostic logs

**B8. Pin sentence-transformers version.**
- Add version pin in pyproject.toml: `"sentence-transformers>=2.7,<3.0"` (or whatever the current installed version is)
- Prevents silent embedding space changes on dependency updates

**B9. Embedding fallback: fail loud.**
- When Qwen3 sidecar fails and sentence-transformers is available, log at WARNING: "embedding_fallback_activated: switching from qwen3 to sentence-transformers -- results may be incomparable"
- Consider: if both embedding models produce vectors stored in the same Qdrant collection, the fallback creates mixed-space indexes. This is a data integrity issue that should be flagged, not silently tolerated.

**Track B files:**
- `engine/runner.py` -- RunnerCallbacks extraction, swallowed exception upgrades
- `surface/queen_runtime.py` -- split into 3 files
- `surface/queen_tools.py` -- new file (extracted from queen_runtime)
- `surface/queen_thread.py` -- new file (extracted from queen_runtime)
- `surface/colony_manager.py` -- _post_colony_hooks split, RunnerCallbacks wiring, create_task callbacks
- `adapters/vector_qdrant.py` -- retry logic, error distinction
- `core/types.py` -- conf_alpha/conf_beta validators
- `surface/app.py` -- embedding fallback warning, create_task callbacks
- `pyproject.toml` -- sentence-transformers version pin

### Track C: Test Coverage + Security

**C1. Security-critical tests (highest priority).**
- ast_security.py: test that blocked modules are actually blocked, test bypass vectors (numpy.ctypeslib, importlib, exec/eval indirection, class reflection)
- output_sanitizer.py: test that sanitization catches known XSS/injection patterns in agent output
- These are 81 + 26 lines of security-critical code with zero tests

**C2. Projection handler coverage to 100%.**
- Currently 23/46 handlers tested
- Wave 31 adds 8 test files but doesn't target projection handlers directly
- Write Given/When/Then tests for all 23 untested handlers
- Focus on Wave 28-30 handlers: MemoryConfidenceUpdated, WorkflowStepCompleted, KnowledgeAccessRecorded, MemoryEntryScopeChanged, DeterministicServiceRegistered, ThreadStatusChanged

**C3. Replay idempotency test.**
- Apply event sequence -> snapshot state -> apply same events again -> compare state
- This is a fundamental event-sourcing invariant that must hold
- Test both full-replay (from empty) and partial-replay (from snapshot + tail)
- Include all 48 event types in the test sequence

**C4. StrEnum migration for 6 stringly-typed fields.**
- Create StrEnums: ScanStatus, ApprovalType, AccessMode, PriorityLevel, TriggerType, MergeReason
- Migrate event field types from bare str to the corresponding StrEnum
- Pydantic v2 handles StrEnum serialization transparently -- existing events in SQLite will deserialize correctly if the string values match enum members
- Add tests verifying backward compatibility: old string values in events must deserialize into the new enum type

**C5. Untested high-risk file coverage.**
- view_state.py (638 LOC) -- UI serialization, most dangerous untested surface file
- memory_store.py (402 LOC) -- knowledge persistence layer
- maintenance.py (382 LOC) -- Wave 31 adds confidence_reset handler but the 3 original handlers (dedup, stale, contradiction) need dedicated tests beyond the Wave 31 B3 end-to-end tests
- mcp_server.py (295 LOC) -- 41 MCP tools, zero tests

**C6. MockLLM upgrade.**
- Current MockLLM returns "Test output" regardless of input
- Upgrade to record calls (messages, tools, temperature) and return configurable responses
- Enable tests to verify: prompt construction, tool-call parsing, multi-turn conversation assembly, fallback behavior
- This is a force multiplier -- every future test benefits

**Track C files:**
- `tests/unit/adapters/test_ast_security.py` -- new
- `tests/unit/adapters/test_output_sanitizer.py` -- new
- `tests/unit/surface/test_projections_wave30.py` -- new (or extend existing)
- `tests/unit/test_replay_idempotency.py` -- new
- `tests/unit/surface/test_view_state.py` -- new
- `tests/unit/surface/test_memory_store.py` -- new
- `tests/unit/surface/test_maintenance_handlers.py` -- new
- `tests/unit/surface/test_mcp_server.py` -- new
- `tests/conftest.py` -- MockLLM upgrade
- `core/events.py` -- StrEnum field types (additive, backward-compatible)
- `core/types.py` -- new StrEnum definitions

---

## What Wave 32 does NOT include

- **No new agent tools.** Wave 31 adds transcript_search (tool #9). Tool count stays at 9.
- **No new events.** Union stays at 48. StrEnum migration changes field types, not event types.
- **No RRF.** Research shows it would cripple Thompson Sampling. Keep weighted linear scoring.
- **No circuit breaker infrastructure.** Qdrant retry (B4) is simpler and sufficient for alpha scale.
- **No three-tier autonomy model.** Wave 31's continuation_depth counter is the safety mechanism. Full autonomy tiers are Wave 33+ at earliest.
- **No composable dashboards.** Still aspirational.

---

## Sequencing considerations

Track A (Knowledge Tuning) and Track B (Structural Refactoring) both touch `colony_manager.py` and `queen_runtime.py`. However:

- Track A modifies the confidence update loop and archival decay handler (specific functions)
- Track B splits queen_runtime.py into 3 files and refactors _post_colony_hooks into per-concern handlers

**These must be sequenced, not parallelized.** Track B's refactoring changes the file structure that Track A targets. Recommended: **Track B lands first** (structural), then Track A applies tuning changes to the cleaner structure. Track C is fully independent and can run in parallel with either.

Alternative: If 3 parallel tracks are required, Track B2 (queen_runtime split) can be deferred to Wave 33, keeping only B1 (RunnerCallbacks) and B3 (_post_colony_hooks split) which are lower-conflict.

---

## Dependencies on Wave 31 outcome

This planning seed assumes Wave 31 lands cleanly. Items that depend on Wave 31 completion:

- A1 (gamma-decay) modifies the same confidence update block that Wave 31 adds step continuation to
- A2 (archival decay) builds on Wave 31's hard-floor enforcement
- B3 (_post_colony_hooks split) must account for Wave 31's step continuation addition
- C2 (projection coverage) should include the Wave 31 continuation_depth handler

**After Wave 31 is operator-tested, re-read the changed files before finalizing Wave 32 coder prompts.**

---

## Estimated scope

| Track | New files | Modified files | New test files | Estimated LOC delta |
|-------|-----------|---------------|---------------|-------------------|
| A: Knowledge Tuning | 0 | 4-5 | 3-4 | +200 net |
| B: Structural + Reliability | 2 (queen_tools.py, queen_thread.py) | 8 | 2-3 | +100 net (mostly restructure) |
| C: Test Coverage + Security | 0 | 2 (events.py, types.py for StrEnums) | 8-10 | +800 tests |
| **Total** | **2** | **~14** | **~15** | **+1,100** |

---

## Priority order if scope must be cut

1. **B5: conf validators** (1 line, prevents division by zero -- ship immediately)
2. **C1: security tests** (107 LOC of untested security code)
3. **A1+A2: gamma-decay + archival redesign** (the headline deferred work)
4. **B6+B7: error capture upgrades** (invisible failures become visible)
5. **B8: sentence-transformers pin** (1 line, prevents silent breakage)
6. **C3: replay idempotency test** (fundamental invariant, never verified)
7. **B2: queen_runtime split** (highest developer velocity impact)
8. **B1: RunnerCallbacks** (testing ergonomics)
9. **A4: scoring normalization** (correctness improvement, low urgency)
10. **C4-C6: remaining test debt** (valuable but not blocking)
