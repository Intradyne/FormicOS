# Wave 32 — Track C Coder Dispatch: Test Coverage + Type Safety

**Wave:** 32
**Track:** C — Test Coverage + Type Safety (Independent — Parallel with Track B)
**Prerequisite:** Wave 31 landed. 1,394 tests passing, 0 pyright errors.
**Priority:** Runs in parallel with Track B. No dependency on Track B or Track A.

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
| `tests/unit/adapters/test_ast_security.py` | C1 | **CREATE** |
| `tests/unit/adapters/test_output_sanitizer.py` | C1 | **CREATE** |
| `tests/unit/test_replay_idempotency.py` | C2 | **CREATE** |
| `core/types.py` | C3 | StrEnum definitions + scan_status field migration |
| `core/events.py` | C3 | 5 field type changes |
| `docs/contracts/events.py` | C3 | Mirror field type changes |
| `tests/unit/surface/test_projection_handlers_full.py` | C4 | **CREATE** |
| `tests/conftest.py` | C6 | MockLLM class addition |

**Do NOT touch:** `surface/queen_runtime.py`, `surface/colony_manager.py`, `engine/runner.py`, `adapters/vector_qdrant.py` (Track B owns those), `surface/knowledge_catalog.py`, `surface/projections.py` (Track A owns those).

---

## Task C1: Security-critical tests

**Goal:** Test the two security-critical adapter files that currently have zero unit test coverage.

### C1a: ast_security.py tests

**Source file:** `adapters/ast_security.py` (81 lines). Main function: `check_ast_safety(code: str) -> ASTCheckResult` at line 41.

Read the source file first to understand the exact blocking rules and return type.

**Create `tests/unit/adapters/test_ast_security.py`** with at least these test cases:

1. **Blocked modules** — each of these should be blocked: `import os`, `import subprocess`, `import sys`, `import shutil`, `import socket`, `import ctypes`
2. **Bypass vectors** — each of these should be caught:
   - `importlib.import_module("os")`
   - `eval("__import__('os')")`
   - `getattr(__builtins__, '__import__')`
3. **Nested imports** — `from os import path` inside a function body should be blocked
4. **Allowed operations** — these should pass: `import math`, string operations, list comprehensions, function definitions, `import json`
5. **Syntax error handling** — malformed code should not crash the checker

**At least 8 test cases total.**

### C1b: output_sanitizer.py tests

**Source file:** `adapters/output_sanitizer.py` (26 lines). Main function: `sanitize_output(text: str) -> str` at line 17.

Read the source file first to understand the exact sanitization rules.

**Create `tests/unit/adapters/test_output_sanitizer.py`** with at least these test cases:

1. **XSS payloads blocked:** `<script>alert(1)</script>`, `<img onerror=...>`, `javascript:` URLs
2. **Clean text passthrough** — normal text returned unchanged
3. **Multi-line output** — mixed clean and malicious content
4. **Edge cases:** nested tags, attribute injection, event handlers in HTML attributes

**At least 5 test cases total.**

---

## Task C2: Replay idempotency test

**Goal:** Verify the fundamental event-sourcing invariant: applying the same event sequence twice from empty state produces identical projection state.

**Create `tests/unit/test_replay_idempotency.py`:**

1. **Build `build_representative_event_sequence()`** — a function that constructs at least one instance of each of the 48 event types with valid field values. The event types are defined in `core/events.py:904-953` (`EVENT_TYPE_NAMES`). Use the `FormicOSEvent` factory or construct events directly. Check the existing test files (e.g., `tests/unit/surface/test_projections_w11.py`) for patterns on how to construct events.

2. **Test: replay produces identical state**
   - Create `ProjectionStore` A, replay all events → snapshot state
   - Create `ProjectionStore` B, replay all events → snapshot state
   - Assert A == B (deep equality on all projection dicts)

3. **Test: double-apply doesn't double counters**
   - Create `ProjectionStore` C, replay events, then replay the same events again
   - Counters like `colony_count` must not double — projection handlers should be idempotent to re-applied events

**Read `surface/projections.py` to understand:**
- How `ProjectionStore` works (the `apply()` method)
- What state dicts exist (workspaces, threads, colonies, memory_entries, etc.)
- How the 46 `_on_*` handlers update state

**This is a critical invariant test.** Take time to construct valid events that exercise real projection paths, not just empty events that get silently ignored.

---

## Task C3: StrEnum migration for 6 fields

**Goal:** Replace 6 stringly-typed fields with StrEnum types for type safety at the event/model boundary.

### Step 1: Define StrEnums in `core/types.py`

Read the codebase to verify exhaustive values before defining. The values below are from grep — verify them:

```python
from enum import StrEnum

class ApprovalType(StrEnum):
    BUDGET_INCREASE = "budget_increase"
    CLOUD_BURST = "cloud_burst"
    TOOL_PERMISSION = "tool_permission"
    EXPENSE = "expense"

class ServicePriority(StrEnum):
    NORMAL = "normal"
    HIGH = "high"

class RedirectTrigger(StrEnum):
    QUEEN_INSPECTION = "queen_inspection"
    GOVERNANCE_ALERT = "governance_alert"
    OPERATOR_REQUEST = "operator_request"

class MergeReason(StrEnum):
    LLM_DEDUP = "llm_dedup"

class AccessMode(StrEnum):
    CONTEXT_INJECTION = "context_injection"
    TOOL_SEARCH = "tool_search"
    TOOL_DETAIL = "tool_detail"
    TOOL_TRANSCRIPT = "tool_transcript"

class ScanStatus(StrEnum):
    PENDING = "pending"
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
```

**IMPORTANT:** Before defining, grep the codebase for all string literal values used for each field. If you find values not listed above, include them in the StrEnum. Missing a value will break deserialization.

### Step 2: Migrate event fields in `core/events.py`

Change 5 field type annotations from `str` to their StrEnum:

| Field | Event Class | Line | New Type |
|-------|------------|------|----------|
| `approval_type` | `ApprovalRequested` | ~370 | `ApprovalType` |
| `priority` | `ServiceQuerySent` | ~540 | `ServicePriority` |
| `trigger` | `ColonyRedirected` | ~649 | `RedirectTrigger` |
| `merge_reason` | `SkillMerged` | ~453 | `MergeReason` |
| `access_mode` | `KnowledgeAccessRecorded` | ~724 | `AccessMode` |

### Step 3: Migrate model field in `core/types.py`

| Field | Model | Line | New Type |
|-------|-------|------|----------|
| `scan_status` | `MemoryEntry` | ~306 | `ScanStatus` |

### Step 4: Mirror in `docs/contracts/events.py`

Apply the same 5 field type changes to the contract mirror. Import the StrEnums from `core.types`.

### Step 5: Backward compatibility test

Add a test (in `tests/unit/core/test_strenum_compat.py` — create this file) that:
- Constructs events from raw dicts with plain string values (e.g., `{"approval_type": "budget_increase", ...}`)
- Verifies StrEnum fields populate correctly after Pydantic v2 deserialization
- Verifies `.value` returns the original string
- Cover all 6 StrEnum types

**Acceptance:**
- 6 StrEnum types defined in `core/types.py`
- 5 event fields + 1 model field use StrEnum types
- `docs/contracts/events.py` mirrors the changes
- Pydantic v2 still deserializes plain string values into StrEnums
- All existing tests pass (Pydantic handles the coercion transparently)
- `pyright src/` clean

---

## Task C4: Projection handler coverage

**Goal:** Add tests for the 9 untested projection handlers added in Waves 28-31.

**Source:** `surface/projections.py` — 46 `_on_*` handlers total, 23 currently tested.

**Create `tests/unit/surface/test_projection_handlers_full.py`** covering these priority handlers:

1. `_on_memory_entry_created` (line 724) — verify memory_entries dict is populated with correct fields
2. `_on_memory_confidence_updated` (line 771) — verify alpha/beta are updated on the correct entry
3. `_on_workflow_step_defined` — verify step appears in thread's workflow_steps list
4. `_on_workflow_step_completed` — verify step status updated AND `continuation_depth` incremented (Wave 31 addition)
5. `_on_knowledge_access_recorded` — verify access tracking state
6. `_on_memory_entry_scope_changed` — verify scope field updated
7. `_on_thread_status_changed` — verify thread status field updated
8. `_on_deterministic_service_registered` — verify service appears in registry
9. `_on_memory_entry_status_changed` — verify entry status field updated

**Pattern:** For each handler:
1. Create a fresh `ProjectionStore`
2. Apply prerequisite events (e.g., `WorkspaceCreated` → `ThreadCreated` → `MemoryEntryCreated` before testing `MemoryConfidenceUpdated`)
3. Apply the target event
4. Assert projection state

**Read existing tests** at `tests/unit/surface/test_projections_w11.py` and `tests/unit/surface/test_round_projections.py` for the exact pattern and helper imports.

**At least 9 test cases** — one per handler. More is fine if edge cases warrant it (e.g., step completion with `success=True` vs `success=False`).

---

## Task C6: MockLLM creation

**Goal:** Create a configurable LLM mock that records calls, for use across all future test waves.

**Current state:** `tests/conftest.py` is minimal — path setup and pytest-bdd plugin registration only. No MockLLM exists.

**Add to `tests/conftest.py`:**

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MockResponse:
    """Minimal mock of an LLM response."""
    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class MockLLM:
    """Configurable mock for LLM calls. Records all invocations.

    Usage:
        mock = MockLLM(responses=["First response", "Second response"])
        result = await mock.complete(model="test", messages=[...])
        assert mock.calls[0]["model"] == "test"
    """

    def __init__(self, responses: list[str] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses = responses or ["Test output"]
        self._call_idx = 0

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> MockResponse:
        self.calls.append({
            "model": model,
            "messages": messages,
            "tools": tools,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        response_text = self._responses[min(self._call_idx, len(self._responses) - 1)]
        self._call_idx += 1
        return MockResponse(content=response_text)

    def reset(self) -> None:
        """Clear recorded calls and reset response index."""
        self.calls.clear()
        self._call_idx = 0
```

**Read the actual LLM call interface** before finalizing. Check how `llm_router` or the LLM adapter is called in `engine/runner.py` and `surface/queen_runtime.py` to ensure MockLLM's `complete()` signature matches what the real code expects. Adjust parameter names and return types to match the real interface.

**Also add a simple test** in `tests/unit/test_mock_llm.py` (CREATE) that verifies:
1. MockLLM records call arguments
2. MockLLM returns responses in sequence
3. MockLLM repeats last response when exhausted
4. `reset()` clears state

**Acceptance:**
- MockLLM class exists in `tests/conftest.py`
- Records call arguments (model, messages, tools, temperature, max_tokens)
- Returns configurable responses in sequence
- Signature matches the real LLM call interface used by the codebase
- Simple self-test passes

---

## Validation (run before declaring done)

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

All four must pass. Zero regressions.

**Track C acceptance summary:**
1. ast_security tests: at least 8 test cases covering blocked modules, bypass vectors, allowed ops
2. output_sanitizer tests: at least 5 test cases covering XSS payloads and clean passthrough
3. Replay idempotency: identical state from two replays; no counter doubling on double-apply
4. 6 StrEnum types created, 5 event fields + 1 model field migrated, backward compat test passes
5. At least 9 new projection handler tests for Wave 28-31 handlers
6. MockLLM records calls and returns configurable responses
7. `pytest` clean after all changes

---

## Do NOT

- Add new events (union stays at 48)
- Modify surface layer files owned by Track B or Track A
- Change scoring weights, gamma-decay logic, or archival decay formulas
- Delete or disable existing tests — fix the code if tests fail
- Add dependencies not in `pyproject.toml`
