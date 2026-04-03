# Planning Workbench

Operator guide for reviewing, editing, and dispatching parallel plans
before launch.

---

## Opening the workbench

The planning workbench opens from two places:

- **Plan preview card** in Queen chat: click **Open Workbench** on any
  parallel plan the Queen proposes.
- **Thread DAG view**: click **Edit Plan** on the workflow visualization
  before any colonies have started.

The workbench edits the real reviewed-plan contract that `spawn_parallel`
consumes. There is no shadow plan model.

---

## Workbench layout

| Section | Purpose |
|---------|---------|
| Header | Plan title, planner model, close button |
| Validation bar | Live status: valid (green), errors (red), or validating (gray) |
| Editor (left column) | Inline editing of tasks, groups, dependencies, and files |
| Sidebar (right column) | "Why this plan" signals, saved patterns, planning history |
| Footer | Save Pattern, Close, Dispatch |

---

## Editing a plan

The editor supports these operations:

| Operation | How |
|-----------|-----|
| Edit task text | Click the task description textarea |
| Change caste | Select from the caste dropdown on each task card |
| Split a task | Click **Split** to create a new task in the same group |
| Merge tasks | Use **Merge...** dropdown to fold one task into another in the same group |
| Move task between groups | Use **Move...** dropdown to relocate a task |
| Reorder groups | Arrow buttons on group headers |
| Delete a task | Click the delete button on a task card |
| Remove a target file | Click the x on a file pill |
| Remove an expected output | Click the x on an output pill |
| Add a dependency | Use **Add dependency...** dropdown |
| Remove a dependency | Click the x on a dependency pill |

Edited fields are visually distinguished from the Queen's original
proposal (accent border on changed task cards). A change counter shows
how many edits have been made. **Reset** restores the original proposal.

---

## Validation

Validation runs automatically as you edit (debounced) and is backed by
the backend reviewed-plan pipeline. The same rules apply to both dry-run
validation and final dispatch.

### Blocking errors

- No tasks in plan
- Empty or duplicate task IDs
- Tasks missing from all groups (orphaned)
- Groups referencing non-existent tasks
- Self-dependencies
- Cross-group dependency violations (task in group N depends on task in
  group N or later)
- Dependency cycles

### Non-blocking warnings

- Multiple tasks targeting the same file
- Task has `depends_on` but no `input_from` (implicit data provenance)
- Empty task description text

Errors block dispatch. Warnings are shown but do not prevent launch.

---

## Comparing plans

The sidebar shows two comparison surfaces with different semantics.

### Saved plan patterns

- Full DAG structure (tasks, groups, dependencies, files)
- Created by operators from reviewed plans
- Can be applied as the starting shape for the editor
- Scoped per workspace

### Planning history (summary-only)

- Compact outcome summaries from prior parallel plans
- Shows strategy, colony count, average quality, success rate
- Does **not** reconstruct the original task graph
- Read-only: cannot be applied as a template

This distinction is intentional. Saved patterns preserve the full
reviewed structure for reuse. Planning history preserves aggregate
outcome metrics for comparison. Summary history is not a full DAG
replay.

---

## Saving a pattern

1. Edit or review a plan in the workbench
2. Click **Save Pattern**
3. Enter a name in the sidebar
4. Click **Save**

The pattern is stored under the workspace data directory as a YAML file.
It preserves the full task/group/dependency/file structure for later
reuse.

To apply a saved pattern: open the comparison sidebar, find the pattern,
and click **Apply**. This replaces the editor contents with the saved
structure, which you can then customize before dispatch.

---

## Dispatching

Click **Dispatch Plan** in the footer. The workbench:

1. Runs backend validation (same rules as the live validation bar)
2. If errors exist: shows them inline; dispatch is blocked
3. If valid: dispatches the reviewed plan through the deterministic
   `confirm_reviewed_plan` path
4. Records a `QueenMessage` confirming dispatch
5. Closes the workbench

Dispatch is deterministic. The backend executes the exact plan shown in
the editor. There is no second Queen LLM call to reinterpret the plan.

### After dispatch

- Colonies spawn according to the group structure
- Tasks in the same group run in parallel
- Later groups wait for earlier groups to complete
- The thread DAG view reflects the reviewed shape
- Result cards and group-state truth match the dispatched plan

---

## What the workbench does not do

- No drag-and-drop (explicit controls preferred for reliability)
- No freeform graph drawing
- No automatic plan generation from the editor
- No silent auto-application of saved patterns
- Planning history does not reconstruct historical DAGs
