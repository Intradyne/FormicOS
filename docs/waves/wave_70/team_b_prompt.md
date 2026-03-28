# Wave 70 — Team B: Project Intelligence

**Theme:** The Queen maintains awareness across threads via a persistent
project plan.

## Context

Read `docs/waves/wave_70/wave_70_plan.md` first. Read `CLAUDE.md` for hard
constraints.

FormicOS threads are isolated conversations. The Queen has session summaries
(`.formicos/sessions/{thread_id}.md`) and thread-scoped plans
(`.formicos/plans/{thread_id}.md`), but nothing that spans threads. When an
operator starts a new thread, the Queen loses project-level context.

Wave 68 introduced `propose_plan` and `mark_plan_step` for thread-scoped
plans. This wave adds a **project-level** plan that persists across threads,
tracks milestones, and orients every new conversation.

**Key insight:** Project plans are files, not memory entries, not events.
They live at `.formicos/project_plan.md` (one per data directory). The
Queen reads and writes them via tools. Injection follows the existing
pattern from session summaries and project context injection in `respond()`.

## Your Files (exclusive ownership)

### Surface
- `src/formicos/surface/queen_tools.py` — `propose_project_milestone` and
  `complete_milestone` new Queen tools (additive to handler registry)
- `src/formicos/surface/queen_runtime.py` — project plan injection in
  `respond()` (small addition alongside existing injection points)
- `config/caste_recipes.yaml` — add `propose_project_milestone` and
  `complete_milestone` to Queen tool list, update tool count

### Tests
- `tests/unit/surface/test_project_plan.py` — **new**

## Do Not Touch

- `src/formicos/surface/addon_loader.py` — Team A owns
- `src/formicos/surface/self_maintenance.py` — Team C owns
- `src/formicos/surface/projections.py`
- `src/formicos/core/events.py`
- `src/formicos/core/types.py`
- `src/formicos/engine/` — any file
- `frontend/` — no frontend changes this wave

## Overlap Coordination

- Team A adds `discover_mcp_tools` to `queen_tools.py` and
  `caste_recipes.yaml`. You add `propose_project_milestone` and
  `complete_milestone`. Both are additive to different sections. No conflict.
- Team C adds `check_autonomy_budget` to `queen_tools.py`. Same: additive,
  different section.
- All three teams touch `caste_recipes.yaml` to append tool names. The
  changes are additive. Merge last team's changes carefully.

---

## Track 4: Project-Level Plan Persistence

### Problem

The operator may work on a multi-week project across many threads. Each
thread has its own plan, but there's no persistent artifact that tracks
project-level milestones, goals, and status across all threads.

### File format

The project plan lives at:
```
{data_dir}/.formicos/project_plan.md
```

This is a single file per FormicOS data directory. Format:

```markdown
# Project Plan

**Goal:** Build the auth module with OAuth2 support

**Updated:** 2026-03-26T14:30:00Z

## Milestones

- [0] [completed] Set up OAuth provider integration
  Thread: abc123 | Completed: 2026-03-24
  Note: Using Auth0 as primary provider

- [1] [active] Implement token refresh flow
  Thread: def456

- [2] [pending] Write integration test suite

- [3] [pending] Deploy to staging
```

### Implementation

The project plan file is read and written by Queen tools only. It is not an
event, not a projection, not a memory entry. It follows the same file-based
pattern as thread plans (`.formicos/plans/{thread_id}.md`) and session
summaries (`.formicos/sessions/{thread_id}.md`).

**No new infrastructure needed.** The `_data_dir` resolution pattern is
already established in `queen_tools.py` at line 3256 (`propose_plan`) and
`queen_runtime.py` at line 842 (session summary write). Reuse the same
`self._runtime.settings.system.data_dir` path.

---

## Track 5: `propose_project_milestone` + `complete_milestone` Queen Tools

### Problem

The Queen needs to create and update project milestones. Two new tools:
one to propose a milestone (or initialize the project plan), one to mark
a milestone as completed.

### Implementation

**1. `propose_project_milestone` tool handler in `queen_tools.py`.**

Add to the handler registry (around line 198, alongside `mark_plan_step`):

```python
"propose_project_milestone": lambda i, w, t: self._propose_project_milestone(i, w, t),
"complete_milestone": lambda i, w, t: self._complete_milestone(i, w, t),
```

**Handler: `_propose_project_milestone`**

```python
def _propose_project_milestone(
    self,
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
) -> tuple[str, dict[str, Any] | None]:
    """Add a milestone to the project plan. Creates the plan file if needed."""
    goal = inputs.get("goal", "")
    milestone = inputs.get("milestone", "")
    if not milestone:
        return ("Error: milestone description is required.", None)

    try:
        _data_dir = self._runtime.settings.system.data_dir
        if not isinstance(_data_dir, str) or not _data_dir:
            return ("No data directory configured.", None)

        _plan_path = Path(_data_dir) / ".formicos" / "project_plan.md"
        _plan_path.parent.mkdir(parents=True, exist_ok=True)

        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        if _plan_path.is_file():
            text = _plan_path.read_text(encoding="utf-8")
        else:
            # Initialize new project plan
            _goal = goal or "Project plan"
            text = (
                f"# Project Plan\n\n"
                f"**Goal:** {_goal}\n\n"
                f"**Updated:** {now}\n\n"
                f"## Milestones\n"
            )

        # Parse existing milestones to find next index
        lines = text.split("\n")
        max_index = -1
        for line in lines:
            m = _re.match(r"^- \[(\d+)\]", line)
            if m:
                max_index = max(max_index, int(m.group(1)))

        next_index = max_index + 1
        new_line = f"- [{next_index}] [pending] {milestone}"
        if thread_id:
            new_line += f"\n  Thread: {thread_id}"

        # Update timestamp
        text = _re.sub(
            r"\*\*Updated:\*\* .*",
            f"**Updated:** {now}",
            text,
        )

        # Update goal if provided and plan was just created
        if goal and "**Goal:**" in text:
            text = _re.sub(
                r"\*\*Goal:\*\* .*",
                f"**Goal:** {goal}",
                text,
            )

        # Append milestone
        if text.endswith("\n"):
            text += f"\n{new_line}\n"
        else:
            text += f"\n\n{new_line}\n"

        _plan_path.write_text(text, encoding="utf-8")

        return (
            f"Added project milestone [{next_index}]: {milestone}",
            {"tool": "propose_project_milestone", "index": next_index},
        )
    except (OSError, TypeError) as exc:
        return (f"Failed to write project plan: {exc}", None)
```

**Handler: `_complete_milestone`**

```python
def _complete_milestone(
    self,
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
) -> tuple[str, dict[str, Any] | None]:
    """Mark a project milestone as completed."""
    index = inputs.get("index")
    note = inputs.get("note", "")
    if index is None:
        return ("Error: milestone index is required.", None)

    try:
        _data_dir = self._runtime.settings.system.data_dir
        if not isinstance(_data_dir, str) or not _data_dir:
            return ("No data directory configured.", None)

        _plan_path = Path(_data_dir) / ".formicos" / "project_plan.md"
        if not _plan_path.is_file():
            return ("No project plan exists. Use propose_project_milestone first.", None)

        text = _plan_path.read_text(encoding="utf-8")
        lines = text.split("\n")
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        found = False
        for i, line in enumerate(lines):
            m = _re.match(r"^- \[(\d+)\] \[(\w+)\] (.*)$", line)
            if m and int(m.group(1)) == index:
                desc = m.group(3)
                lines[i] = f"- [{index}] [completed] {desc}"
                # Add completion metadata on next line
                completion_line = f"  Completed: {now[:10]}"
                if note:
                    completion_line += f" | {note}"
                # Check if next line is indented metadata
                if i + 1 < len(lines) and lines[i + 1].startswith("  "):
                    lines.insert(i + 1, completion_line)
                else:
                    lines.insert(i + 1, completion_line)
                found = True
                break

        if not found:
            return (f"Milestone [{index}] not found in project plan.", None)

        # Update timestamp
        text = "\n".join(lines)
        text = _re.sub(
            r"\*\*Updated:\*\* .*",
            f"**Updated:** {now}",
            text,
        )

        _plan_path.write_text(text, encoding="utf-8")

        return (
            f"Milestone [{index}] marked as completed.",
            {"tool": "complete_milestone", "index": index},
        )
    except (OSError, TypeError) as exc:
        return (f"Failed to update project plan: {exc}", None)
```

**Tool specs — add to `_queen_tools()` list** (before the `*self._addon_tool_specs` spread at line 1411):

```python
# Wave 70 Track 5: project-level milestone management
{
    "name": "propose_project_milestone",
    "description": (
        "Add a milestone to the project plan. Creates the plan if "
        "it doesn't exist. Use for tracking cross-thread goals."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "milestone": {
                "type": "string",
                "description": "Milestone description",
            },
            "goal": {
                "type": "string",
                "description": (
                    "Project goal (used when creating a new plan)"
                ),
            },
        },
        "required": ["milestone"],
    },
},
{
    "name": "complete_milestone",
    "description": (
        "Mark a project milestone as completed."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "index": {
                "type": "integer",
                "description": "Milestone index number to complete",
            },
            "note": {
                "type": "string",
                "description": "Completion note (optional)",
            },
        },
        "required": ["index"],
    },
},
```

**2. Update `caste_recipes.yaml`.**

Add `"propose_project_milestone"` and `"complete_milestone"` to the Queen
tools array (line 207). Update the comment if it mentions tool count.

---

## Track 6: Project Plan Injection on Startup + Thread Creation

### Problem

When the Queen starts a new thread or responds in any thread, she should
be aware of the project plan. Without injection, she won't know what
milestones exist or which are active.

### Implementation

**1. Inject project plan in `respond()` in `queen_runtime.py`.**

The existing injection pattern is at lines 931–953 (project context) and
lines 955–983 (session summary). Add a project plan injection block
immediately after the project context injection:

```python
# Wave 70 Track 6: inject project plan for cross-thread awareness
try:
    _data_dir_pp = self._runtime.settings.system.data_dir
    if isinstance(_data_dir_pp, str) and _data_dir_pp:
        _pp_path = Path(_data_dir_pp) / ".formicos" / "project_plan.md"
        if _pp_path.is_file():
            _pp_text = _pp_path.read_text(
                encoding="utf-8",
            )[:budget.project_context * 4]
            if _pp_text:
                _pp_insert = 0
                for _ppi, _ppm in enumerate(messages):
                    if _ppm.get("role") != "system":
                        _pp_insert = _ppi
                        break
                else:
                    _pp_insert = len(messages)
                messages.insert(_pp_insert, {
                    "role": "system",
                    "content": (
                        "# Project Plan (cross-thread)\n"
                        f"{_pp_text}"
                    ),
                })
except (AttributeError, TypeError, OSError):
    pass
```

**Key decisions:**
- Uses `budget.project_context` token budget (same as project context).
  The project plan shares this budget — it's injected alongside project
  context, not as a separate allocation.
- Injected after system prompts, before conversation. Same pattern as
  all other injections.
- Labeled `(cross-thread)` so the Queen knows this spans threads.
- If no project plan file exists, nothing is injected.

**2. No special "thread creation" handling needed.**

The injection happens on every `respond()` call. When a new thread is
created, the first `respond()` call will inject the project plan. The Queen
will see the active milestones and can orient the conversation.

---

## Tests

Create `tests/unit/surface/test_project_plan.py`:

1. `test_propose_project_milestone_creates_file` — no existing plan file,
   call handler, assert file created with correct format, milestone at
   index 0 with status `pending`.

2. `test_propose_project_milestone_appends_to_existing` — existing plan
   with 2 milestones, call handler, assert new milestone at index 2.

3. `test_complete_milestone_updates_status` — existing plan with 3
   milestones, complete index 1, assert status changed to `completed`
   with completion date.

4. `test_complete_milestone_missing_index` — complete a non-existent
   index, assert error message returned.

5. `test_complete_milestone_no_plan_file` — no plan file exists, assert
   error message referencing `propose_project_milestone`.

6. `test_propose_project_milestone_sets_goal` — provide `goal` param,
   assert `**Goal:**` line contains the goal text.

7. `test_project_plan_injection_reads_file` — create a plan file, mock
   the respond() path, verify the plan text appears in injected messages.

**Test setup pattern:** Mock `self._runtime.settings.system.data_dir` to
point to a tmp directory. Use `tmp_path` fixture for file I/O. Follow the
pattern from existing queen_tools tests (mock Runtime with minimal stubs).

---

## Acceptance Gates

- [ ] `.formicos/project_plan.md` created on first `propose_project_milestone`
- [ ] Milestones appended with sequential indices
- [ ] `complete_milestone` updates status from any state to `completed`
- [ ] Completion includes date and optional note
- [ ] Project plan injected in `respond()` on every call when file exists
- [ ] Injection labeled `(cross-thread)` for Queen awareness
- [ ] No injection overhead when no plan file exists
- [ ] Tools visible in Queen's tool list via `caste_recipes.yaml`
- [ ] No new event types
- [ ] No projection changes
- [ ] No frontend changes
- [ ] All tests pass

## Validation

```bash
pytest tests/unit/surface/test_project_plan.py -v
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```
