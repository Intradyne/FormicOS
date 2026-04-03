# Wave 76 Team C: Context Integrity + Identity Coherence

**Goal:** After this team's work, every Queen context injection respects its
budget slot, and workspaces don't interfere through shared file paths or
missing workspace propagation.

## Owned files

- `src/formicos/surface/queen_runtime.py` -- context injection budget caps, session path namespacing
- `src/formicos/surface/thread_plan.py` -- plan path namespacing
- `frontend/src/components/queen-chat.ts` -- workspace propagation in send-message events
- `frontend/src/components/settings-view.ts` -- workspace resolution
- `frontend/src/components/formicos-app.ts` -- `activeWorkspaceId` pass-through only
- `frontend/src/components/queen-overview.ts` -- active workspace resolution, including child props that still use `tree[0]`
- `tests/unit/surface/test_operations_coordinator.py` -- update thread-plan helper call if Track 14 changes the helper signature

## Do NOT touch

- `src/formicos/surface/projections.py` -- Team A
- `src/formicos/surface/self_maintenance.py` -- Team A
- `src/formicos/surface/action_queue.py` -- Team B
- `src/formicos/surface/app.py` -- Team B
- `src/formicos/surface/routes/api.py` -- Team B
- `src/formicos/surface/colony_manager.py` -- Teams A and B
- `src/formicos/surface/operations_coordinator.py` -- Team B

## Before you code, read these files

1. `src/formicos/surface/queen_runtime.py` -- this is a large file. Focus on:
   - `_respond_inner` method, all injection blocks from line 954 onward:
     - Memory retrieval injection at :954-972 (**NO budget cap**)
     - Project context at :983-1005 (capped at `budget.project_context * 4`)
     - Project plan at :1007-1032 (capped at `budget.project_plan * 4`)
     - Procedures at :1034-1060 (capped at `budget.operating_procedures * 4`)
     - Journal at :1062-1086 (capped at `budget.queen_journal * 4`)
     - Session summary at :1088-1117 (capped at `budget.thread_context * 4`)
     - Thread context at :1119-1130 (**NO budget cap**)
   - `_build_messages` method:
     - Notes injection at :1849-1871 (**NO budget cap** -- up to 10 notes * 500 chars)
   - Session summary write path at :849-859 (`.formicos/sessions/{thread_id}.md`)
   - `_build_thread_context` at :1987-2088 -- plan file read at :2068-2075 (`.formicos/plans/{thread_id}.md` with hardcoded 2000-char cap)
2. `src/formicos/surface/queen_budget.py` -- full file. Key slots:
   - `memory_retrieval`: fraction 0.13, fallback 1500 tokens
   - `thread_context`: fraction 0.13, fallback 1500 tokens
   - `tool_memory`: fraction 0.09, fallback 4000 tokens
3. `src/formicos/surface/thread_plan.py` -- line 36-38 (path resolution:
   `.formicos/plans/{thread_id}.md`)
4. `frontend/src/components/queen-chat.ts` -- search for `send-message` dispatches:
   - Lines 466-469, 475-478, 501-504, 611-614 (all send `threadId` + `content`, no `workspaceId`)
   - Line 228 (`wsId` derived from `this.activeThread?.workspaceId`)
5. `frontend/src/components/settings-view.ts`:
   - Line 241 (`_workspaceId` getter: `this.tree[0]?.id`)
   - Lines 403, 439 (also read `this.tree[0]` directly)
6. `frontend/src/components/formicos-app.ts` -- lines 346-351 (active workspace
   derivation from selected node), lines 627 and 746 (send-message routing:
   `e.detail.workspaceId || this.activeWorkspaceId`), line 612-638 (queen-overview
   render), line 729 (settings view render)
7. `docs/waves/architecture_audit_post_75.md` -- sections 1.2 (thread identity),
   6.1 (frontend workspace defaults), 6.2 (Queen chat workspace), 8.2 (memory
   retrieval unbounded), 8.3 (notes/thread context unbounded)

---

## Track 12: Budget-cap memory retrieval injection

The memory retrieval block at `queen_runtime.py:954-972` is the only
budget-slot injection that has NO truncation. Every other injection caps
at `budget.slot_name * 4`.

### Fix

After the memory block is retrieved and before it's inserted into messages,
add a cap:

```python
if memory_block:
    # Wave 76: cap memory retrieval to its budget slot
    memory_block = memory_block[:budget.memory_retrieval * 4]
    # ... existing insert_idx logic unchanged ...
```

Insert the cap line immediately after `if memory_block:` (line 960).

**One line.** The `budget.memory_retrieval` slot is 0.13 of context with
a 1500-token fallback. At `* 4` (chars-per-token estimate), the cap is
6000 chars minimum, which is generous for a memory block.

---

## Track 13: Budget-cap notes and thread context injections

### Notes injection

In `_build_messages` at lines 1849-1871, after constructing the notes
content block, cap it:

```python
if notes:
    latest = notes[-self._tool_dispatcher._INJECT_NOTES:]
    note_lines = [f"- {n.get('content', '')}" for n in latest]
    notes_content = (
        "Your saved notes (operator preferences and memory):\n"
        + "\n".join(note_lines)
    )
    # Wave 76: cap notes to tool_memory budget slot
    notes_content = notes_content[:budget.tool_memory * 4]
    messages.append({"role": "system", "content": notes_content})
```

`budget` is already passed into `_build_messages(...)` in the current code.
Use the existing parameter; do NOT reopen the method signature unless the
live file differs from the verified seam.

### Thread context injection

In `_respond_inner` at lines 1119-1130, after `_build_thread_context`
returns, cap the result:

```python
thread_ctx = self._build_thread_context(thread_id, workspace_id)
if thread_ctx:
    # Wave 76: cap thread context to its budget slot
    thread_ctx = thread_ctx[:budget.thread_context * 4]
    # ... existing insert logic unchanged ...
```

**Note:** `_build_thread_context` already has a hardcoded 2000-char cap
on the plan file read (around line 2075). The explicit budget cap here
is the authoritative guard -- the hardcoded cap inside the method is
defense-in-depth.

**Verify:** After both fixes, EVERY system block injected into the Queen's
context has an explicit budget cap. Walk the injection list:

| Injection | Cap | Verified |
|-----------|-----|----------|
| Memory retrieval | `budget.memory_retrieval * 4` | Track 12 |
| Project context | `budget.project_context * 4` | Existing (:991) |
| Project plan | `budget.project_plan * 4` | Existing (:1019) |
| Operating procedures | `budget.operating_procedures * 4` | Existing (:1046) |
| Queen journal | `budget.queen_journal * 4` | Existing (:1073) |
| Prior session context | `budget.thread_context * 4` | Existing (:1100) |
| Thread context | `budget.thread_context * 4` | Track 13 |
| Notes | `budget.tool_memory * 4` | Track 13 |
| Operations continuity | `budget.thread_context * 2` | Existing (:1219) |
| Warm-start continuation | `budget.thread_context * 2` | Existing (:1251) |

---

## Track 14: Thread file path namespacing

### Session summary paths

In `queen_runtime.py`, the session write path at lines 849-859:

```python
# Current (line 853-856):
_session_dir = Path(_data_dir) / ".formicos" / "sessions"
_session_dir.mkdir(parents=True, exist_ok=True)
_session_path = _session_dir / f"{thread_id}.md"
```

Change to workspace-scoped:

```python
# Wave 76: workspace-scoped session paths
_session_dir = Path(_data_dir) / ".formicos" / "sessions" / workspace_id
_session_dir.mkdir(parents=True, exist_ok=True)
_session_path = _session_dir / f"{thread_id}.md"
```

Then in the session read path at lines 1088-1117:

```python
# Current (line 1093-1095):
_session_path = (
    Path(_data_dir2) / ".formicos" / "sessions"
    / f"{thread_id}.md"
)
```

Change to check new path first, fall back to old:

```python
# Wave 76: workspace-scoped with migration fallback
_session_dir_new = Path(_data_dir2) / ".formicos" / "sessions" / workspace_id
_session_path = _session_dir_new / f"{thread_id}.md"
if not _session_path.is_file():
    # Migration fallback: try old unscoped path
    _session_path = (
        Path(_data_dir2) / ".formicos" / "sessions"
        / f"{thread_id}.md"
    )
```

**Verify:** The `workspace_id` variable is available at both sites. Check
that the read path has `workspace_id` in scope -- it's inside
`_respond_inner(self, workspace_id, thread_id)`, so yes.

### Thread plan paths

In `thread_plan.py:36-38`:

```python
# Current:
def thread_plan_path(data_dir: str, thread_id: str) -> Path:
    return Path(data_dir) / ".formicos" / "plans" / f"{thread_id}.md"
```

Change the signature to accept `workspace_id` and namespace:

```python
def thread_plan_path(
    data_dir: str, thread_id: str, workspace_id: str = "",
) -> Path:
    """Return the canonical thread plan path (workspace-scoped)."""
    if workspace_id:
        return (
            Path(data_dir) / ".formicos" / "plans"
            / workspace_id / f"{thread_id}.md"
        )
    # Legacy fallback for callers that don't pass workspace_id
    return Path(data_dir) / ".formicos" / "plans" / f"{thread_id}.md"
```

**Then update all callers** to pass `workspace_id`. Search the codebase for
every call to `thread_plan_path`. Each call site should have `workspace_id`
available from the thread or colony context. Update them to pass it.

For read paths, add migration fallback:

```python
path = thread_plan_path(data_dir, thread_id, workspace_id)
if not path.is_file():
    path = thread_plan_path(data_dir, thread_id)  # legacy fallback
```

Also update `_build_thread_context` in `queen_runtime.py` (the plan file
read at lines 2068-2075 builds `.formicos/plans/{thread_id}.md`) to use
the new namespaced path with fallback.

Important: `thread_plan.py` also has `load_all_thread_plans(data_dir)` at
:138-161, which scans only `.formicos/plans/*.md` (line 152). After this
change, namespaced plans live under `.formicos/plans/{workspace_id}/` and
will be invisible to that glob. Update `load_all_thread_plans` to also
scan `plans_dir.glob("*/*.md")` for workspace-scoped plans, or change
the signature to accept an optional `workspace_id` and scan the scoped
directory. The operations coordinator calls this function, so leaving it
broken will cause plans to disappear from the operations view.

**Test:** Write tests for:
1. New path resolution includes workspace_id
2. Fallback to old path when new doesn't exist
3. Write always goes to new path

---

## Track 15: Queen chat workspace propagation

In `queen-chat.ts`, all `send-message` event dispatches send `threadId`
and `content` but NOT `workspaceId`. The app shell at
`formicos-app.ts:627,746` falls back to `this.activeWorkspaceId` when
`e.detail.workspaceId` is missing.

### Fix

At line 228, the component already derives `wsId`:

```typescript
const wsId = this.activeThread?.workspaceId ?? 'default';
```

Add `workspaceId` to every `send-message` dispatch. There are four sites:

**Line 611-614** (primary send):
```typescript
this.dispatchEvent(new CustomEvent('send-message', {
  detail: {
    threadId: this.activeThread.id,
    workspaceId: this.activeThread?.workspaceId ?? '',
    content: this.input.trim(),
  },
  bubbles: true, composed: true,
}));
```

**Lines 466-469, 475-478, 501-504** (edit/delete/other dispatches):
Add `workspaceId: this.activeThread?.workspaceId ?? ''` to each detail
object.

**Verify:** After fixing, check `formicos-app.ts:627,746` to confirm
the routing logic reads `e.detail.workspaceId` correctly. The existing
code `e.detail.workspaceId || this.activeWorkspaceId` will now receive
the correct value instead of falling back.

---

## Track 16: Settings workspace resolution

In `settings-view.ts`, the workspace is resolved from `tree[0]` instead
of from the active workspace selection:

```typescript
// Line 241:
private get _workspaceId(): string {
  return this.tree[0]?.id ?? '';
}
```

### Fix

Change the component to accept an `activeWorkspaceId` prop from the app
shell, matching how other workspace-scoped components work:

```typescript
@property({ type: String }) activeWorkspaceId = '';

private get _workspaceId(): string {
  return this.activeWorkspaceId || this.tree[0]?.id || '';
}
```

Lines 403 and 439 also read `this.tree[0]` directly to get the workspace
**object** (not just its ID). Add a helper that finds the active workspace
by ID, falling back to `tree[0]`:

```typescript
private get _activeWorkspace() {
  const id = this._workspaceId;
  return this.tree.find(ws => ws.id === id) ?? this.tree[0];
}
```

Then replace `this.tree[0]` at lines 403 and 439 with `this._activeWorkspace`.

**Then** update the parent component (`formicos-app.ts`) to pass
`activeWorkspaceId` to `fc-settings-view`. The render is at line 729:

```typescript
return html`<fc-settings-view .protocolStatus=${s.protocolStatus}
  .runtimeConfig=${s.runtimeConfig} .skillBankStats=${s.skillBankStats}
  .tree=${this.tree} .addons=${s.addons}
  .activeWorkspaceId=${this.activeWorkspaceId}></fc-settings-view>`;
```

### queen-overview.ts -- same fix

`queen-overview.ts` has the same bug at line 195-196:

```typescript
private get activeWorkspaceId(): string {
  return this.tree[0]?.id ?? '';
}
```

And `this.tree[0]?.name` at line 200. There is also still a direct child prop
pass-through at line 174:

```typescript
<fc-queen-overrides .workspaceId=${this.activeWorkspaceId}
  .workspace=${this.tree[0] ?? null}></fc-queen-overrides>
```

Apply the same pattern: accept `activeWorkspaceId` prop, update the getter,
replace direct `tree[0]` accesses with an active-workspace helper, and pass
that active workspace object to `fc-queen-overrides` instead of `this.tree[0]`.
The render is at `formicos-app.ts:612-638`; add `.activeWorkspaceId=${this.activeWorkspaceId}`
to the prop list at line 613.

**Do NOT** change `formicos-app.ts` beyond the `activeWorkspaceId`
pass-through for `settings-view` and `queen-overview`.
The existing active workspace derivation at :346-351 is correct.

### Track 14 test caller note

If you change the `thread_plan_path(...)` signature, update the confirmed test
caller at `tests/unit/surface/test_operations_coordinator.py:31` in the same
patch so CI stays green. This is the only verified caller outside the Team C
production files.

---

## Validation

```bash
ruff check src/formicos/surface/queen_runtime.py src/formicos/surface/thread_plan.py
pyright src/formicos/surface/queen_runtime.py src/formicos/surface/thread_plan.py
pytest tests/ -x -q
```

For frontend changes, verify no TypeScript compilation errors:

```bash
cd frontend && npm run build
```

After all tests pass, run the full CI:

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

## Overlap rule

No overlap with Teams A or B. All owned files are exclusive to Team C.
If you find yourself needing to modify `projections.py`, `app.py`,
`action_queue.py`, or `colony_manager.py`, STOP and coordinate.


