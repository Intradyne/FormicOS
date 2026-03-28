# Wave 68 — Team A: Queen Memory & Planning

**Theme:** The Queen remembers plans and sessions across restarts.

## Context

Read `docs/waves/wave_68/design_note.md` first. You are bound by all three
invariants. In particular: plans and session summaries are FILES, not
`memory_entries`. They never enter the knowledge pipeline.

Read `CLAUDE.md` for hard constraints (event closed union, layer rules, etc.).
Read `AGENTS.md` for file ownership. This prompt overrides stale root
`AGENTS.md` for file ownership within this wave.

## Your Files (exclusive ownership)

- `src/formicos/surface/queen_tools.py` — `_propose_plan()` modification + `mark_plan_step` new tool
- `src/formicos/surface/queen_runtime.py` — `_build_thread_context()` plan injection (BOTTOM of method, after workflow steps section ~line 1411) + `respond()` session injection + `emit_session_summary()` new method
- `src/formicos/surface/runtime.py` — shutdown hook wiring
- `tests/unit/surface/test_plan_attention.py` — **new**
- `tests/unit/surface/test_session_continuity.py` — **new**

## Do Not Touch

- `projections.py` — no projection field changes, no replay handlers
- `core/types.py` — no EntrySubType additions
- `core/events.py` — no new event types
- `addon_loader.py` — Team C owns
- `knowledge_catalog.py` — invariant 2 (no retrieval changes)
- `colony_manager.py` — no colony lifecycle changes
- `_build_messages()` in `queen_runtime.py` — Team B owns
- Any frontend files
- `ThreadProjection.active_plan` — **DO NOT USE.** It carries
  `DelegationPlanPreview` from `ParallelPlanCreated` events
  (projections.py:1915-1919, typed as `DelegationPlanPreview` in
  frontend/src/types.ts:294). Using it for proposal-shaped data would
  break the parallel planning UI.

## Overlap Coordination

- **Team C** will insert ~4 lines at the TOP of `_build_thread_context()`
  (after line ~1356) for workspace tag injection. You insert at the BOTTOM
  (after line ~1411) for plan injection. No conflict.
- **Team B** touches `respond()` for deliberation frame injection and budget
  threading. Your session injection goes in `respond()` AFTER memory
  retrieval (same area as project_context injection, lines 795-815).
  Team B's deliberation detection goes INSIDE the tool loop (lines 968+).
  Different code regions.

---

## Track 1: Plan File Persistence

### Problem

The Queen proposes plans via `propose_plan` (queen_tools.py:3056-3176) but
immediately forgets them. The `active_plan` field on `ThreadProjection`
(projections.py:535) carries `DelegationPlanPreview` from
`ParallelPlanCreated` — it is NOT available for proposal plans.
`propose_plan` returns `(text, action_dict)` where the action dict has
`render: "proposal_card"`. The plan text scrolls out of context after
`_RECENT_WINDOW=10` messages (queen_runtime.py:146). For multi-step
threads, the Queen loses track of what it planned.

### Implementation

**1. Write plan file from `_propose_plan()`.**

In `queen_tools.py`, `_propose_plan()` (line 3056): after building the
proposal dict (line 3170), write a structured plan file.

```python
# After line 3170 (proposal dict built):
# Wave 68: persist plan to file for attention injection
try:
    _data_dir = self._runtime.settings.system.data_dir
    if isinstance(_data_dir, str) and _data_dir:
        _plan_dir = Path(_data_dir) / ".formicos" / "plans"
        _plan_dir.mkdir(parents=True, exist_ok=True)
        # thread_id must be passed — add it as a parameter
        _plan_path = _plan_dir / f"{thread_id}.md"
        _plan_lines = [f"# Plan: {summary[:200]}", ""]
        if recommendation:
            _plan_lines.append(f"**Approach:** {recommendation}")
            _plan_lines.append("")
        if enriched_options:
            _plan_lines.append("## Options")
            for i, opt in enumerate(enriched_options, 1):
                label = opt.get("label", f"Option {i}")
                desc = opt.get("description", "")
                _plan_lines.append(f"{i}. **{label}:** {desc}")
            _plan_lines.append("")
        _plan_lines.append("## Steps")
        _plan_lines.append("*(No steps defined yet. Use mark_plan_step to add.)*")
        _plan_path.write_text("\n".join(_plan_lines), encoding="utf-8")
except (OSError, TypeError):
    pass  # plan file is best-effort, not critical path
```

**Note:** `_propose_plan()` currently receives `inputs` and `workspace_id`
(line 3056-3059) but NOT `thread_id`. The dispatcher (queen_tools.py:167-206)
uses lambda wrapping: `"propose_plan": lambda i, w, t: self._propose_plan(i, w)`
which drops `t`. To get `thread_id`, change the lambda to pass `t` through
and add `thread_id: str` to the method signature:
```python
# In the handler registry (~line 185):
"propose_plan": lambda i, w, t: self._propose_plan(i, w, t),
```
Then update the method signature:
```python
def _propose_plan(self, inputs, workspace_id, thread_id):
```
Same pattern for `mark_plan_step` — register with the full `(i, w, t)` lambda.

The `.formicos/` directory pattern is established:
- Backups: `queen_runtime.py:658` — `target.parent / ".formicos" / "backups"`
- Project context: `queen_runtime.py:799` — `Path(_data_dir) / ".formicos" / "project_context.md"`
- Colony manager: `colony_manager.py:676` — `Path(_ws_dir) / ".formicos" / "project_context.md"`

Use the `data_dir` pattern from `queen_runtime.py:797`:
```python
_data_dir = self._runtime.settings.system.data_dir
```

**2. Add `mark_plan_step` Queen tool.**

New tool spec in the tool specs list:

```python
{
    "name": "mark_plan_step",
    "description": (
        "Update a plan step's status. Call after spawning a colony for "
        "a plan step or when a step completes/blocks."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "step_index": {
                "type": "integer",
                "description": "Zero-based step index in the plan"
            },
            "status": {
                "type": "string",
                "enum": ["pending", "started", "completed", "blocked"],
                "description": "New status for this step"
            },
            "description": {
                "type": "string",
                "description": "Step description (required when adding a new step)"
            },
            "colony_id": {
                "type": "string",
                "description": "Colony executing this step (optional)"
            },
            "note": {
                "type": "string",
                "description": "Brief status note (optional)"
            }
        },
        "required": ["step_index", "status"]
    }
}
```

Handler implementation:
1. Read the plan file from `.formicos/plans/{thread_id}.md`
2. Parse the `## Steps` section
3. Update or append the step at `step_index`
4. Write the file back
5. Return confirmation text

The step format in the file:
```markdown
## Steps
- [0] [started] Implement auth module (colony abc12345)
- [1] [pending] Write integration tests
- [2] [completed] Update API docs — Done, merged.
```

Register `mark_plan_step` in the tool dispatch. Follow the same pattern as
other Queen tools: add to the tool specs list, add to the dispatch handler.
Also add it to the Queen's tool list in `caste_recipes.yaml` (line 203) —
coordinate with Team C who also modifies this file. Add `mark_plan_step`
to the existing comma-separated list.

**3. Inject plan into `_build_thread_context()`.**

In `queen_runtime.py`, `_build_thread_context()` (line 1347): after the
workflow steps section (which ends at line 1411), inject the plan file:

```python
# Wave 68: inject plan file for persistent attention
try:
    _data_dir = self._runtime.settings.system.data_dir
    if isinstance(_data_dir, str) and _data_dir:
        _plan_path = Path(_data_dir) / ".formicos" / "plans" / f"{thread_id}.md"
        if _plan_path.is_file():
            _plan_text = _plan_path.read_text(encoding="utf-8")[:2000]
            if _plan_text:
                lines.append(f"\n{_plan_text}")
except (OSError, TypeError, AttributeError):
    pass
```

Cap at 2000 chars. The plan file is read on every `respond()` call — this
is the "read-heavy, write-light" pattern. The file is the attention
mechanism.

### Tests (`tests/unit/surface/test_plan_attention.py`)

5 tests:

1. **`test_propose_plan_writes_plan_file`** — Mock `_runtime.settings.system.data_dir`
   to a temp directory. Call `_propose_plan()` with summary/options/recommendation.
   Assert `.formicos/plans/{thread_id}.md` exists with correct content.

2. **`test_mark_plan_step_updates_file`** — Write a plan file with steps section.
   Call `mark_plan_step` handler with `step_index=0, status="completed"`.
   Assert file updated correctly.

3. **`test_mark_plan_step_adds_new_step`** — Call with a new `step_index` and
   `description`. Assert step appended.

4. **`test_build_thread_context_includes_plan`** — Write a plan file. Call
   `_build_thread_context()`. Assert output contains plan summary.

5. **`test_plan_injection_caps_at_2000_chars`** — Write an oversized plan file
   (5000 chars). Assert injected text is truncated.

---

## Track 2: Session Continuity via Files

### Problem

When the operator reopens a workspace, the Queen has no memory of what
happened in previous sessions. Thread context shows colony counts and
step statuses, but not what the Queen learned, what worked, or what was
abandoned.

### Implementation

**1. `emit_session_summary()` method on `QueenRuntime`.**

New method in `queen_runtime.py`:

```python
async def emit_session_summary(
    self, workspace_id: str, thread_id: str,
) -> None:
    """Write a session summary file for later startup injection.

    Content assembled deterministically from projections — no LLM call.
    File written to .formicos/sessions/{thread_id}.md.
    """
    thread = self._runtime.projections.get_thread(workspace_id, thread_id)
    if thread is None:
        return

    lines: list[str] = [
        f"# Session Summary: {thread.name}",
        f"**Thread:** {thread_id}",
        f"**Status:** {thread.status}",
        "",
    ]

    # Plan state (from plan file, if exists)
    try:
        _data_dir = self._runtime.settings.system.data_dir
        if isinstance(_data_dir, str) and _data_dir:
            _plan_path = Path(_data_dir) / ".formicos" / "plans" / f"{thread_id}.md"
            if _plan_path.is_file():
                _plan_text = _plan_path.read_text(encoding="utf-8")[:1000]
                lines.append("## Active Plan")
                lines.append(_plan_text)
                lines.append("")
    except (OSError, TypeError, AttributeError):
        pass

    # Colony outcomes this session
    lines.append("## Colony Activity")
    lines.append(
        f"- {thread.completed_colony_count} completed, "
        f"{thread.failed_colony_count} failed, "
        f"{thread.colony_count} total"
    )

    # Workflow step status
    if thread.workflow_steps:
        completed = sum(1 for s in thread.workflow_steps if s.get("status") == "completed")
        pending = sum(1 for s in thread.workflow_steps if s.get("status") == "pending")
        lines.append(f"- Workflow: {completed} steps completed, {pending} pending")

    # Last few Queen decisions (from conversation, last 5 queen messages)
    queen_msgs = [m for m in thread.queen_messages if m.role == "queen"]
    if queen_msgs:
        lines.append("")
        lines.append("## Recent Queen Activity")
        for msg in queen_msgs[-5:]:
            content = msg.content[:200] if hasattr(msg, "content") else ""
            if content:
                lines.append(f"- {content}")

    summary_text = "\n".join(lines)

    # Write to file
    try:
        _data_dir = self._runtime.settings.system.data_dir
        if isinstance(_data_dir, str) and _data_dir:
            _session_dir = Path(_data_dir) / ".formicos" / "sessions"
            _session_dir.mkdir(parents=True, exist_ok=True)
            _session_path = _session_dir / f"{thread_id}.md"
            _session_path.write_text(summary_text, encoding="utf-8")
    except (OSError, TypeError, AttributeError):
        log.warning("session_summary.write_failed",
                    workspace_id=workspace_id, thread_id=thread_id)
```

**2. Always-inject session summary in `respond()`.**

In `queen_runtime.py`, `respond()`: after the memory retrieval block
(lines 778-793) and project context block (lines 795-815), inject the
session summary file. **NOT gated on `if not thread.queen_messages`** —
always inject if the file exists. Cap at ~1000 tokens (~4000 chars).

```python
# Wave 68: session continuity — always inject prior session summary
try:
    _data_dir = self._runtime.settings.system.data_dir
    if isinstance(_data_dir, str) and _data_dir:
        _session_path = (
            Path(_data_dir) / ".formicos" / "sessions" / f"{thread_id}.md"
        )
        if _session_path.is_file():
            _session_text = _session_path.read_text(encoding="utf-8")[:4000]
            if _session_text:
                # Insert after system prompts, before conversation history
                _ss_insert = 0
                for _si, _sm in enumerate(messages):
                    if _sm.get("role") != "system":
                        _ss_insert = _si
                        break
                else:
                    _ss_insert = len(messages)
                messages.insert(_ss_insert, {
                    "role": "system",
                    "content": f"# Prior Session Context\n{_session_text}",
                })
except (OSError, TypeError, AttributeError):
    pass
```

This mirrors the project_context injection pattern (queen_runtime.py:795-815)
exactly — same `data_dir` resolution, same try/except, same insert-after-
system-prompts logic.

**3. Shutdown hook in `runtime.py`.**

In `runtime.py`, find the shutdown/cleanup sequence. Add a call that
iterates active workspaces and their threads, calling
`queen_runtime.emit_session_summary()` for each thread with recent
activity (any `QueenMessage` in the last 30 minutes).

Look for an existing `async def shutdown()` or `async def cleanup()` method
on the `Runtime` class. If none exists, add a method and wire it from the
application shutdown sequence in `app.py`.

```python
# In Runtime shutdown sequence:
async def _emit_session_summaries(self) -> None:
    """Emit session summaries for recently active threads on shutdown."""
    cutoff = datetime.now(UTC) - timedelta(minutes=30)
    for ws_id, ws in self.projections.workspaces.items():
        for thread_id, thread in ws.threads.items():
            if not thread.queen_messages:
                continue
            # Check last message timestamp
            last_msg = thread.queen_messages[-1]
            ts = _parse_projection_timestamp(
                last_msg.timestamp if hasattr(last_msg, "timestamp") else ""
            )
            if ts and ts > cutoff:
                try:
                    await self.queen.emit_session_summary(ws_id, thread_id)
                except Exception:
                    log.warning("shutdown.session_summary_failed",
                                workspace_id=ws_id, thread_id=thread_id)
```

Note: `_parse_projection_timestamp` is already defined in `queen_runtime.py`
(line 112). You may need to extract it or duplicate it depending on where
the shutdown method lives.

### Tests (`tests/unit/surface/test_session_continuity.py`)

4 tests:

1. **`test_emit_session_summary_writes_file`** — Mock projections with a
   thread that has colonies and messages. Call `emit_session_summary()`.
   Assert `.formicos/sessions/{thread_id}.md` exists with expected sections.

2. **`test_session_injection_always_fires`** — Write a session file. Create
   a thread with existing queen_messages (non-empty). Call `respond()` mock
   path. Assert session summary appears in messages list.

3. **`test_session_injection_caps_at_4000_chars`** — Write an oversized
   session file. Assert injected text is truncated.

4. **`test_session_summary_includes_plan_state`** — Write both a plan file
   and call `emit_session_summary()`. Assert session summary references
   the plan.

---

## Acceptance Gates

All gates must pass before declaring done:

- [ ] `propose_plan` writes `.formicos/plans/{thread_id}.md`
- [ ] `mark_plan_step` reads/writes plan file, updates step status
- [ ] `_build_thread_context()` includes plan file content (capped at 2000 chars)
- [ ] Plan survives conversation compaction (10+ messages)
- [ ] Plan file does NOT touch `ThreadProjection.active_plan`
- [ ] Session summary writes to `.formicos/sessions/{thread_id}.md` on shutdown
- [ ] Session summary is NOT a `MemoryEntryCreated` event
- [ ] Session injection fires on every `respond()`, not gated on empty messages
- [ ] Session injection capped at ~4000 chars
- [ ] No new event types added (event count stays at 69)
- [ ] No changes to `projections.py`

## Validation

```bash
# Unit tests
pytest tests/unit/surface/test_plan_attention.py -v
pytest tests/unit/surface/test_session_continuity.py -v

# Full CI
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```
