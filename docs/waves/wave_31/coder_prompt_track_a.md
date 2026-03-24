# Wave 31 Track A — Step Continuation + Colony Manager Hardening

**Track:** A
**Wave:** 31 — "Ship Polish"
**Coder:** You own this track. Read this prompt fully before writing any code.

---

## Reading Order (mandatory before any code changes)

1. `docs/decisions/040-wave-31-ship-polish.md` — D1 (step continuation appends to follow_up_colony), D3 (thread_id bug fix), D4 (no new events)
2. `docs/waves/wave_31/wave_31_final_amendments.md` — Amendment 1 (ADOPT: append to follow_up_colony, NOT separate QueenMessage). **This supersedes the plan's A1 section where they conflict.**
3. `docs/waves/wave_31/wave_31_plan.md` — Track A sections (A1, A2, A3), file ownership matrix
4. `CLAUDE.md` — hard constraints, prohibited alternatives, validation commands

**IMPORTANT:** The plan's A1 section describes direct QueenMessage emission from colony_manager. **That approach was rejected in Amendment 1.** The correct approach is appending step continuation text to the existing `follow_up_colony` summary. The ADR-040 D1 reflects the correct (amended) decision. If you see conflicting guidance, the amendments and ADR win.

---

## Your Files

| File | Action |
|------|--------|
| `src/formicos/surface/colony_manager.py` | **OWN** — bug fix, reorder hooks, build step text, pass to follow_up |
| `src/formicos/surface/queen_runtime.py` | **OWN** — extend follow_up_colony, relax 30-min gate, thread context truncation, archival decay hard-floor |
| `src/formicos/surface/projections.py` | **OWN** — add continuation_depth to ThreadProjection |
| `src/formicos/surface/memory_store.py` | measure only — sync_entry latency (A2) |

## Do NOT Touch

- `engine/runner.py` (Track B)
- `surface/runtime.py` (Track B)
- `surface/knowledge_catalog.py` (Track C)
- `surface/maintenance.py` (Track C)
- `surface/app.py` (Track C)
- `config/caste_recipes.yaml` (Track B + C)
- Any `tests/` files (Track B)
- Any `docs/` files (Track C)
- `CLAUDE.md`, `AGENTS.md` (Track C)

---

## Task 0: Bug Fix — thread_id not passed to colony knowledge fetch

**Severity:** High. Negates Wave 29's thread-scoped knowledge boosting.

`colony_manager.py` line 374 calls `fetch_knowledge_for_colony(task=colony.task, workspace_id=colony.workspace_id, top_k=5)` without `thread_id`. The catalog's `_search_thread_boosted` path (0.25 thread bonus) is never reached during colony execution.

**Fix:** Two lines.

```python
# Line 374-376: add thread_id
knowledge_items = await self._runtime.fetch_knowledge_for_colony(
    task=colony.task, workspace_id=colony.workspace_id,
    thread_id=colony.thread_id, top_k=5,
)

# Line 390-392: add thread_id (redirect re-fetch)
knowledge_items = await self._runtime.fetch_knowledge_for_colony(
    task=goal, workspace_id=colony.workspace_id,
    thread_id=colony.thread_id, top_k=5,
)
```

The `fetch_knowledge_for_colony` signature already accepts `thread_id: str = ""` (runtime.py:1015). No downstream changes needed.

---

## Task 1: Step Continuation — Append to follow_up_colony (Amendment 1)

This is the headline feature. The pattern is: detect which workflow step completed, build continuation text, pass it into the existing `follow_up_colony` call so it appends to the summary. Zero new messages in the Queen's conversation.

### Step 1a: Add `continuation_depth` to ThreadProjection

In `projections.py`, add to the `ThreadProjection` dataclass (currently at line ~215):

```python
continuation_depth: int = 0  # Wave 31: replay-safe step continuation counter
```

In `_on_workflow_step_completed` (line 793), after updating the step status (line 803), increment:

```python
if e.success:
    thread.continuation_depth += 1
```

This is derived projection state — replay-safe, no new event needed.

### Step 1b: Reorder `_post_colony_hooks` — detect step completion BEFORE follow_up dispatch

Current order in `_post_colony_hooks()` (line 633):
1. Line 668-676: Queen follow-up summary (`_follow_up_colony`)
2. Line 678-694: Institutional memory extraction
3. Line 696-746: Bayesian confidence update
4. Line 748-794: Workflow step completion detection + WorkflowStepCompleted event

**New order:** Move the step completion DETECTION (not the event emission) above the follow_up dispatch. The goal is to know "which step completed and what's next" before calling `_follow_up_colony`, so we can pass `step_continuation` text.

Concretely:

1. **Before the follow_up block (before line 668)**, read the thread projection's `workflow_steps` to detect if this colony was running a step:

```python
# --- Wave 31 A1: detect step completion for continuation text ---
step_continuation = ""
if ws_id and th_id:
    thread_proj = self._runtime.projections.get_thread(ws_id, th_id)
    if thread_proj is not None:
        completed_step = None
        next_step = None
        for step in thread_proj.workflow_steps:
            if (
                step.get("colony_id") == colony_id
                and step.get("status") == "running"
            ):
                completed_step = step
            elif step.get("status") == "pending" and next_step is None:
                next_step = step

        if completed_step is not None and next_step is not None:
            depth = getattr(thread_proj, "continuation_depth", 0)
            if depth >= 20:
                step_continuation = (
                    "Step limit reached (20 consecutive steps). "
                    "Review workflow before continuing."
                )
            else:
                step_idx = completed_step.get("step_index", "?")
                next_idx = next_step.get("step_index", "?")
                next_desc = next_step.get("description", "")
                step_continuation = (
                    f"Step {step_idx} completed. "
                    f"Next pending: Step {next_idx} -- {next_desc}."
                )
                # Add template context if template-backed
                tmpl_id = next_step.get("template_id", "")
                expected = next_step.get("expected_outputs", [])
                if tmpl_id:
                    step_continuation += (
                        f"\nTemplate: {tmpl_id}"
                    )
                    if expected:
                        step_continuation += (
                            f", Expected: {', '.join(expected)}"
                        )
                step_continuation += (
                    "\nReview step status or spawn the next colony."
                )
```

2. **Pass `step_continuation` into `_follow_up_colony`** (the wrapper at line 796):

```python
# Line 672 area — modify the call:
if queen is not None and succeeded and ws_id and th_id:
    asyncio.create_task(self._follow_up_colony(
        colony_id=colony_id,
        workspace_id=ws_id,
        thread_id=th_id,
        step_continuation=step_continuation,
    ))
```

3. **Update `_follow_up_colony` wrapper** (line 796) to accept and pass through:

```python
async def _follow_up_colony(
    self, colony_id: str, workspace_id: str, thread_id: str,
    step_continuation: str = "",
) -> None:
    """Ask Queen to summarize a completed colony. Fire-and-forget, errors logged."""
    try:
        queen = self._runtime.queen
        if queen is None:
            return
        await queen.follow_up_colony(
            colony_id=colony_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            step_continuation=step_continuation,
        )
    except Exception:  # noqa: BLE001
        log.debug("colony_manager.follow_up_failed", colony_id=colony_id)
```

**IMPORTANT:** The WorkflowStepCompleted event emission (lines 748-794) stays exactly where it is. You are only moving the _detection logic_ (reading workflow_steps) earlier. The event still fires in its original location after the detection.

### Step 1c: Extend `follow_up_colony` in queen_runtime.py

Current signature (line 214):
```python
async def follow_up_colony(
    self, colony_id: str, workspace_id: str, thread_id: str,
) -> None:
```

**New signature:**
```python
async def follow_up_colony(
    self, colony_id: str, workspace_id: str, thread_id: str,
    step_continuation: str = "",
) -> None:
```

**Relax the 30-minute operator gate when step_continuation is present** (lines 232-244):

```python
has_recent_operator = any(
    m.role == "operator"
    and (parsed := _parse_projection_timestamp(m.timestamp)) is not None
    and parsed >= recent_cutoff
    for m in thread.queen_messages
)
if not has_recent_operator and not step_continuation:
    log.debug(
        "queen.follow_up_skipped",
        colony_id=colony_id, reason="no_recent_operator",
    )
    return

if step_continuation and not has_recent_operator:
    log.info(
        "queen.follow_up_gate_relaxed",
        reason="step_continuation",
        thread_id=thread_id,
        colony_id=colony_id,
    )
```

**Append step continuation to the summary** (after line 294, before the `_emit_queen_message` call at line 296):

```python
if step_continuation:
    summary += f"\n{step_continuation}"
```

---

## Task 2: Confidence Fan-Out Measurement (A2)

In the Bayesian confidence update loop (`_post_colony_hooks` lines 696-746), wrap the loop in timing:

```python
import time
_conf_start = time.monotonic()
# ... existing confidence update loop ...
_conf_elapsed = time.monotonic() - _conf_start
if _conf_elapsed > 0.1:  # 100ms threshold
    log.warning(
        "colony.confidence_fanout_slow",
        colony_id=colony_id,
        elapsed_ms=round(_conf_elapsed * 1000, 1),
        entries_updated=len(seen_ids),
    )
```

If the measurement consistently shows <100ms, that's the deliverable — document the measurement in your completion report. If >200ms, batch the Qdrant syncs (add `sync_entries()` to memory_store.py). **Measure first, optimize only if warranted.**

---

## Task 3: Thread Context Truncation (A3)

In `queen_runtime.py`, method `_build_thread_context` (line 595):

**Colonies:** Currently shows all colonies. Cap at last 10 in detail:

```python
# After line 619 (the "Colonies: X completed..." line)
# If total colonies > 10, summarize earlier ones
if thread.colony_count > 10:
    lines.append(f"(showing last 10 of {thread.colony_count} colonies)")
```

Then when listing colonies (if that section exists), only show the most recent 10.

**Workflow steps** (lines 628-636): Show last 5 completed + all pending, summarize the rest:

```python
if thread.workflow_steps:
    completed_steps = [s for s in thread.workflow_steps if s.get("status") in ("completed", "failed")]
    pending_steps = [s for s in thread.workflow_steps if s.get("status") in ("pending", "running")]

    lines.append("Steps:")
    if len(completed_steps) > 5:
        lines.append(f"  ({len(completed_steps) - 5} earlier steps completed)")
    for step in completed_steps[-5:]:
        idx = step.get("step_index", "?")
        status = step.get("status", "pending")
        desc = step.get("description", "")
        col = step.get("colony_id", "")
        col_info = f" (colony {col[:8]})" if col else ""
        lines.append(f"  [{idx}] [{status}] {desc}{col_info}")
    for step in pending_steps:
        idx = step.get("step_index", "?")
        status = step.get("status", "pending")
        desc = step.get("description", "")
        col = step.get("colony_id", "")
        col_info = f" (colony {col[:8]})" if col else ""
        lines.append(f"  [{idx}] [{status}] {desc}{col_info}")
```

---

## Task 4: Archival Decay Hard-Floor (frontloaded from Wave 32)

In `queen_runtime.py`, the archival decay block (lines 1282-1283):

```python
# Current:
new_alpha = old_alpha * 0.8
new_beta = old_beta * 1.2

# Add hard-floor immediately after:
new_alpha = max(new_alpha, 1.0)
new_beta = max(new_beta, 1.0)
```

This prevents pathological U-shaped Beta distributions if archival decay runs multiple times on the same entry. One defensive line per variable, zero risk.

---

## Acceptance Criteria

1. Colony completes a workflow step -> Queen chat shows step-continuation text appended to the existing follow_up summary (NOT a separate message)
2. Template-backed step continuation includes template_id in the text
3. Queen can ignore the continuation and do something different (she always decides)
4. `continuation_depth >= 20` -> safety message instead of next-step prompt
5. Colony knowledge fetch passes `thread_id` (verify with structlog trace in logs)
6. Thread context for 50+ colony thread is truncated (last 10 colonies, last 5 completed steps)
7. Archival decay clamps alpha >= 1.0 and beta >= 1.0 after decay
8. 30-minute operator gate is relaxed when `step_continuation` is present, with structlog trace
9. Confidence fan-out timing is measured and logged if >100ms

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Run this before declaring done. All must pass. The 70 pre-existing pyright errors are acceptable; do not introduce new ones.

## Overlap Rules

- **Track B** will add one line to the `RoundRunner(...)` instantiation at lines 344-358 (wiring `transcript_search_fn`). You own the surrounding code. Track B must reread your changes before adding their line. Do not add transcript_search_fn yourself.
- **Track C** touches `queen_runtime.py` for first-run welcome text only. Non-overlapping section. No conflict expected.
