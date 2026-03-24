# Wave 52: Information Flow and Tool Use Findings

**Date:** 2026-03-20

Audit of the seams that move information into models and route tool output back
through the system. Focus: prompt-boundary safety, context pressure, intake
reach, and external stream truth.

---

## Final Answers

### What are the highest-leverage seams?

1. **Queen tool-result prompt hygiene is behind the colony runner.**
   The colony runner wraps tool output as untrusted data and compacts old tool
   results under pressure. The Queen loop still feeds raw tool output back as
   plain user messages.

2. **Queen automatic retrieval is not thread-aware even though the retrieval
   layer supports it.**
   `retrieve_relevant_memory()` accepts `thread_id`, but `QueenAgent.respond()`
   does not pass it. Returning operators miss the thread-scoped boost on the
   most important entry path.

3. **External stream timeout semantics can lie about run completion.**
   A2A attach and AG-UI run streams emit `RUN_FINISHED` with `status=timeout`
   after 300s of inactivity even if the colony is still running.

### What is already good?

- The core mutation invariant still holds: everything important mutates through
  `runtime.emit_and_broadcast()`.
- The colony runner already has strong tool-result prompt hygiene:
  prompt-boundary sanitization, per-result truncation, and oldest-first history
  compaction.
- Queen notes are now replay-safe and remain private.
- A2A and AG-UI share one event translator, so event shape drift is low.
- Queen thread history compaction is deterministic and replay-safe.

---

## Findings

### F1: Queen tool-result prompt hygiene lags the colony runner (HIGH)

**Where:**
- `src/formicos/engine/runner.py`
- `src/formicos/surface/queen_runtime.py`

**Current truth:**
- The colony runner wraps tool output inside `<untrusted-data>`, strips prompt
  control characters, truncates large results, and replaces oldest tool results
  with placeholders when history grows too large.
- The Queen loop appends raw tool results back into the conversation as:

```text
[Tool result: tool_name]
<raw result text>
```

with no untrusted-data wrapper and no result-history compaction.

**Why it matters:**
- Prompt injection risk is higher on the Queen path than on the colony path.
- Multi-tool Queen turns can accumulate large raw results in a single response
  loop and crowd out the actual reasoning budget.
- This is exactly the sort of seam that makes tool use feel brittle under
  longer, more complex operator sessions.

**Bounded fix:**
- Mirror the runner seam in `queen_runtime.py`:
  - strip prompt-control characters
  - wrap tool output as untrusted data
  - cap per-result size
  - compact oldest tool results under history pressure

Do this in the Queen loop. Do not turn Wave 52 into a broad shared-helper
refactor unless it stays trivial.

### F2: Queen automatic retrieval ignores available thread context (HIGH)

**Where:**
- `src/formicos/surface/runtime.py::retrieve_relevant_memory()`
- `src/formicos/surface/queen_runtime.py::respond()`

**Current truth:**
- `retrieve_relevant_memory(task, workspace_id, thread_id="")` supports
  thread-aware retrieval.
- `QueenAgent.respond()` calls it with `workspace_id` only.

**Why it matters:**
- The Queen is the primary intelligence path.
- Thread-scoped retrieval exists specifically to make repeated work in the same
  thread compound more strongly.
- Right now, the most important path leaves that boost on the table.

**Bounded fix:**
- Pass `thread_id` into `retrieve_relevant_memory()` from the Queen path.

This is a small wiring change with outsized impact on returning-operator
intelligence.

### F3: A2A sees disk templates only; learned-template reach stops at the Queen/UI (HIGH)

**Where:**
- `src/formicos/surface/routes/a2a.py`
- `src/formicos/surface/template_manager.py`
- `src/formicos/surface/routes/protocols.py`

**Current truth:**
- A2A imports `load_templates()` (disk only).
- Queen tools and the workspace templates API already use
  `load_all_templates(... projection_templates=...)`.
- Agent Card skills also read disk templates only.

**Why it matters:**
- Learned templates are a real part of the system's intelligence substrate.
- Today they are visible to the Queen and operator UI, but not to A2A intake.
- External discovery surfaces underreport what the system has learned.

**Bounded fix:**
- A2A should use `load_all_templates(...)`.
- A2A should expose selection metadata so callers can see when a learned
  template was used.
- If Wave 52 touches Agent Card skill discovery, decide explicitly whether
  learned templates should be surfaced there too.

### F4: External budget truth is inconsistent, and spawn-gate parity is still missing (MEDIUM)

**Where:**
- `src/formicos/surface/queen_tools.py`
- `src/formicos/surface/routes/a2a.py`
- `src/formicos/surface/agui_endpoint.py`
- `src/formicos/surface/runtime.py::BudgetEnforcer`

**Current truth:**
- Queen path checks `BudgetEnforcer.check_spawn_allowed()`.
- A2A already passes a per-colony `budget_limit` from template/classifier
  selection, but does not use the Queen-style workspace spawn gate.
- AG-UI passes no `budget_limit` and silently falls back to the runtime
  default of `5.0`, and it also skips the workspace spawn gate.

**Why it matters:**
- This is a cost guardrail inconsistency across entry paths.
- It also means the control plane does not behave uniformly at the exact point
  where external automation is most likely.

**Bounded fix:**
- At minimum, remove AG-UI's silent `5.0` default and make budget behavior explicit.
- If Wave 52 keeps full parity in scope, add the same workspace spawn gate to
  A2A and AG-UI.

### F5: External SSE timeout semantics can misreport terminal state (MEDIUM)

**Where:**
- `src/formicos/surface/routes/a2a.py`
- `src/formicos/surface/agui_endpoint.py`

**Current truth:**
- after 300s without an event, both surfaces emit `RUN_FINISHED`
  with `status=timeout`
- the colony may still be running

**Why it matters:**
- This is a truth gap, not just a transport gap.
- A2A at least has polling, so recovery is possible.
- AG-UI currently has no separate poll/resume path, so a timeout can look more
  terminal than it really is.

**Bounded fix options:**
1. emit a non-terminal keepalive/idle event and continue streaming
2. emit state snapshot + idle marker instead of `RUN_FINISHED`
3. if behavior is intentionally retained, document it much more explicitly

### F6: A2A thread reuse is real but underdocumented (LOW)

**Where:**
- `src/formicos/surface/routes/a2a.py`
- `docs/A2A-TASKS.md`

**Current truth:**
- A2A derives thread IDs from a description slug and reuses that thread if it
  already exists.

**Why it matters:**
- repeated same-description tasks can share thread-scoped context implicitly
- that may be beneficial, but it is not obvious to integrators

**Bounded fix:**
- at minimum, document this behavior explicitly
- only change the behavior if the product intent is actually wrong

### F7: Queen manual memory search likely misses thread bonus too (LOW)

**Where:**
- `src/formicos/surface/queen_tools.py`

**Current truth:**
- `memory_search` passes `workspace_id` but not `thread_id`

**Why it matters:**
- smaller than F2 because this is a manual tool path
- still worth piggybacking if Team 1 is already touching Queen retrieval seams

---

## Recommended Packet Adjustments

### Add to Packet B as highest-priority backend work

1. **Queen tool-result hygiene parity**
2. **Thread-aware Queen retrieval**

These are higher leverage for actual intelligence stability than several of the
lighter control-plane text fixes.

### Keep in Packet B

- A2A learned-template reach
- external budget truth and any bounded spawn-gate parity
- learned-template briefing visibility
- recent outcome digest

### Add to Packet A if capacity allows

- external stream timeout truth

This is a genuine protocol-semantics issue, but it is slightly wider than the
other control-plane text cleanups.

---

## Bottom Line

The biggest remaining gaps are no longer "missing features." They are
information-flow seams:
- information is available but not routed into the right path
- tool output is available but not bounded/sanitized uniformly
- external streams can overstate terminality

Those are exactly the kinds of fixes that make the system feel rock solid
without inventing new substrate.
