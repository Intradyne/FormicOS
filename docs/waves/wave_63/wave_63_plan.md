# Wave 63 -- The Queen Remembers, The Operator Controls

**Goal:** Give the Queen persistent memory across turns, failure awareness,
write agency, and negative-signal learning. Give the operator direct control
over the knowledge base, workflow steps, and project context. After Wave 63,
the operator curates memory and workflows directly -- the Queen is a
collaborator, not a gatekeeper.

**Event union:** 65 -> 66. One new event: `WorkflowStepUpdated`.
Justification: workflow step edits (reorder, rename, skip) from the UI need
a replay-safe event distinct from `WorkflowStepCompleted` (which records
colony-driven completion with success/failure semantics). Operator-driven
edits change description, order, or status to "skipped" -- different
semantics from colony completion.

Knowledge editing reuses existing events: `MemoryEntryRefined`
(source="operator_edit"), `MemoryConfidenceUpdated` (for soft-delete via
alpha=0/beta=100), `MemoryEntryCreated` (source="operator").

**Tests target:** +40 new tests minimum across all tracks.

---

## Track 1 -- Cross-Turn Tool Memory

**Problem:** The Queen runs `search_codebase("budget")`, gets 15 matches,
tells the operator about them. Next turn: zero recall. Tool results are
accumulated in the `messages` list during `respond()` (lines 699-706 in
queen_runtime.py) but only the final reply text is emitted as a QueenMessage
event (line 763). The operator says "show me that function" and the Queen
searches from scratch -- or hallucinates.

**Current state:**
- `_MAX_TOOL_ITERATIONS = 7` (line 51) controls within-turn tool loop
- Final QueenMessage emission at lines 763-766 via `_emit_queen_message()`
- `queen_note` tool (line 480 in queen_tools.py) is the only cross-turn
  persistence -- requires the Queen to explicitly save, which she rarely does
- Queen notes injected at lines 816-838 of `_build_messages()`

**Design:**

A. **Compact tool results into QueenMessage metadata.** After the tool loop
   completes (line 730 in queen_runtime.py), before emitting the final
   QueenMessage, build a `tool_memory` list:

   ```python
   tool_memory = []
   for msg in messages:
       if msg.get("role") == "tool" and msg.get("tool_use_id"):
           tool_memory.append({
               "tool": msg.get("tool_name", "unknown"),
               "summary": msg["content"][:500],  # truncate long outputs
           })
   ```

   Store in QueenMessage metadata: `meta={"tool_memory": tool_memory, ...}`.
   QueenMessage already has a `meta` field (dict[str,Any], line 744).

B. **Inject prior-turn tool memory into context.** In `_build_messages()`
   (line 801), after queen_notes injection (line 838) and before conversation
   history, scan the last 3 QueenMessage events for `tool_memory` in their
   metadata. Inject as a system message:

   ```
   # Prior tool results (last 3 turns)
   Turn -1: search_codebase -> "Found 15 matches: projections.py:325..."
   Turn -2: run_command -> "git log --oneline: 91151c0 deps: reduce..."
   ```

   Budget: cap at 1500 tokens total across all prior turns. Oldest turns
   get summarized more aggressively.

C. **Sliding window.** Only keep tool memory from the last 3 turns. Older
   tool results are already captured in the conversation text (the Queen's
   replies reference them). The raw outputs are what's lost -- 3 turns
   provides sufficient working memory.

**Code delta:** ~60 lines in queen_runtime.py (30 for collection, 30 for
injection in _build_messages).

**New tests (3):**
1. `test_tool_memory_collected` -- respond() with tool calls produces
   QueenMessage with `tool_memory` in meta
2. `test_tool_memory_injected` -- _build_messages() injects prior tool
   results when recent QueenMessages have tool_memory
3. `test_tool_memory_window` -- only last 3 turns are injected, older
   ones dropped

**Owned files:**
- `src/formicos/surface/queen_runtime.py` -- tool memory collection + injection
- `tests/unit/surface/test_queen_runtime.py` -- new tests (create if needed)

**Do not touch:** `core/events.py` (QueenMessage already has meta field),
`engine/runner.py`, `core/types.py`

**Validation:**
```bash
pytest tests/unit/surface/test_queen_runtime.py -q
ruff check src/ && python scripts/lint_imports.py
```

---

## Track 2 -- Failed Colony Notifications + Parallel Aggregation

**Problem:** Failed colonies are invisible to the Queen. `_hook_follow_up()`
at colony_manager.py:1231 gates on `succeeded=True`. The Queen learns about
failures only if the operator asks. For parallel colonies (`spawn_parallel`),
each colony triggers a separate `follow_up_colony()` with no grouping --
the Queen sees 3 disconnected result cards instead of one coherent summary.

**Current state:**
- `_hook_follow_up()` at colony_manager.py:1221-1238 fires only on success
- `_post_colony_hooks()` at line 1101 calls follow_up at line 1125
- `follow_up_colony()` in queen_runtime.py:334-472 builds quality-aware
  summary and emits with `render="result_card"`
- ParallelPlanCreated event (line 1470 in events.py) records colony groups
  but no aggregation on completion

**Design:**

A. **Remove the succeeded gate.** Change colony_manager.py:1231 from
   `if succeeded and ws_id and th_id:` to `if ws_id and th_id:`.

B. **Build failure-aware follow-up summary.** In queen_runtime.py
   `follow_up_colony()`, after the existing quality summary (lines 402-422),
   add a failure branch:

   ```python
   if not colony_outcome.succeeded:
       summary_parts.append(f"Colony FAILED after {colony_outcome.total_rounds} rounds.")
       summary_parts.append(f"Last error: {colony_outcome.failure_reason or 'stalled'}")
       summary_parts.append(f"Cost: ${colony_outcome.total_cost:.3f}")
       # Suggest retry or investigation
       summary_parts.append("Consider: retry with different model, inspect output, or abandon.")
   ```

   Emit with `render="result_card"` but add `"status": "failed"` to meta
   so the frontend can style it differently (red accent).

C. **Parallel colony aggregation.** Track in-flight parallel plan colonies
   in queen_runtime.py. When a colony completes that belongs to a parallel
   plan:
   - If other colonies in the plan are still running, store the result
   - When the last colony in the plan completes, emit ONE aggregated
     follow-up message: "Parallel plan complete: 2/3 succeeded.
     Colony-A: auth module (succeeded). Colony-B: tests (succeeded).
     Colony-C: migration (failed -- stalled at round 4)."
   - Use `render="result_card"` with `meta.plan_id` and `meta.group_results`

   Track parallel plan membership via projections -- ParallelPlanCreated
   already records colony_ids. Add a `_pending_parallel_plans` dict in
   queen_runtime.py keyed by plan_id -> {colony_id: result_or_None}.

**Code delta:** ~115 lines total. Gate removal at colony_manager.py:1231
is a 1-line change applied by Team B (see file overlap matrix).
40 lines in queen_runtime.py (failure summary), 75 in queen_runtime.py
(parallel aggregation tracker).

**New tests (5):**
1. `test_failed_colony_triggers_followup` -- failed colony calls follow_up
2. `test_failure_summary_includes_error` -- failure summary has cost + reason
3. `test_failure_card_has_failed_status` -- meta.status == "failed"
4. `test_parallel_aggregation_waits` -- first completion stored, no emission
5. `test_parallel_aggregation_emits_on_last` -- last colony triggers grouped
   result card with all colony outcomes

**Owned files:**
- `src/formicos/surface/queen_runtime.py` -- failure summary + aggregation
- `tests/unit/surface/test_queen_runtime.py` -- new tests

**Shared file (Team B applies):**
- `src/formicos/surface/colony_manager.py:1231` -- gate removal (1 line)

**Do not touch:** `core/events.py`, `engine/runner.py`

**Validation:**
```bash
pytest tests/unit/surface/test_queen_runtime.py tests/unit/surface/test_colony_manager.py -q
```

---

## Track 3 -- Queen Write Tools (edit_file + run_tests)

**Problem:** "Fix this typo in the config" requires spawning a colony: 60
seconds, 3 agents, governance rounds, knowledge extraction. The Queen needs
direct write agency for small edits, with operator confirmation.

**Current state:**
- `read_workspace_files` exists as a Queen tool (queen_tools.py)
- `write_workspace_file` exists as a Queen tool (queen_tools.py:666 spec,
  line 2204 handler) -- creates/overwrites files in the workspace files
  directory (.md, .txt, .json, .yaml, .yml, .csv only)
- `search_codebase` and `run_command` added in Wave 62
- No search-replace edit tool exists -- `write_workspace_file` overwrites
  whole files, it cannot patch a specific section
- No delete tool exists
- The proposal-card pattern from Wave 61 provides the confirmation UX

**Design:**

A. **`edit_file` Queen tool.**

   ```python
   {
     "name": "edit_file",
     "description": "Propose a file edit. Shows diff to operator for approval.",
     "parameters": {
       "path": "string -- workspace-relative file path",
       "old_text": "string -- exact text to replace",
       "new_text": "string -- replacement text",
       "reason": "string -- why this change"
     }
   }
   ```

   Handler flow:
   1. Read current file content (validate path exists, file readable)
   2. Verify `old_text` exists in file (exact match)
   3. Generate unified diff preview
   4. Emit QueenMessage with `render="edit_proposal"`, `intent="ask"`,
      `meta={"path": path, "diff": diff_text, "old_text": old, "new_text": new}`
   5. Do NOT apply the edit yet -- wait for operator confirmation

   On operator confirmation ("apply it", "yes", "go ahead"):
   - The Queen's next respond() detects the pending edit in recent messages
   - Calls internal `_apply_pending_edit()` which writes the file
   - Emits confirmation message with `render="result_card"`

   Safety: backup file to `.formicos/backups/{filename}.{timestamp}` before
   writing. Path validation: reject paths outside workspace root, reject
   binary files, reject files > 100KB.

B. **`run_tests` Queen tool.**

   ```python
   {
     "name": "run_tests",
     "description": "Run tests and return results.",
     "parameters": {
       "pattern": "string -- test file pattern or specific test path (optional)",
       "timeout": "integer -- max seconds, default 120, max 300"
     }
   }
   ```

   Handler: subprocess execution of `pytest {pattern} -q --tb=short` with
   timeout. Uses same allowlist/subprocess pattern as `run_command` from
   Wave 62. Output truncated to 2000 chars. Returns structured result:
   pass count, fail count, error summary.

C. **`delete_file` Queen tool.**

   ```python
   {
     "name": "delete_file",
     "description": "Propose deleting a workspace file. Requires operator approval.",
     "parameters": {
       "path": "string -- workspace-relative file path",
       "reason": "string -- why this file should be deleted"
     }
   }
   ```

   Confirmation required. Backup before delete.

   Note: for creating NEW files, the existing `write_workspace_file` tool
   already handles this (limited to .md/.txt/.json/.yaml/.yml/.csv). No
   new create_file tool is needed.

**Code delta:** ~200 lines in queen_tools.py (3 tool specs + 3 handlers +
shared validation + backup logic). ~30 lines in queen_runtime.py (pending
edit detection on confirmation turn).

**New tests (7):**
1. `test_edit_file_produces_diff` -- handler returns edit_proposal card
2. `test_edit_file_rejects_missing_old_text` -- old_text not found -> error
3. `test_edit_file_rejects_binary` -- binary file -> error
4. `test_edit_file_rejects_outside_workspace` -- path traversal -> error
5. `test_run_tests_returns_structured` -- pass/fail counts in result
6. `test_run_tests_timeout` -- respects timeout parameter
7. `test_delete_file_produces_proposal` -- returns confirmation card

**Owned files:**
- `src/formicos/surface/queen_tools.py` -- 4 new tools + handlers
- `src/formicos/surface/queen_runtime.py` -- pending edit confirmation
- `tests/unit/surface/test_queen_tools.py` -- new tests

**Do not touch:** `engine/runner.py`, `engine/tool_dispatch.py` (these are
agent tools, not Queen tools)

**Validation:**
```bash
pytest tests/unit/surface/test_queen_tools.py -q
ruff check src/ && python scripts/lint_imports.py
```

---

## Track 4 -- Negative Signal Extraction

**Problem:** The archivist extracts "what the colony learned" -- which is
always stuff the model already knows (CSV parsing, JWT tokens, etc.). The
valuable extraction is "what went WRONG" -- failure patterns, dead ends,
and anti-patterns specific to THIS project. This is the only knowledge
category where compounding should produce positive signal.

**Current state:**
- Extraction prompt in colony_manager.py `_hook_memory_extraction()` at
  line ~1260 asks for skills and experiences
- `sub_type` field supports: technique, pattern, anti_pattern (for skills);
  decision, convention, learning, bug (for experiences)
- `anti_pattern` and `bug` sub_types exist but are rarely produced because
  the prompt doesn't specifically ask for them

**Design:**

A. **Augment the extraction prompt.** Add explicit sections to the archivist
   extraction prompt:

   ```
   ## Failure Patterns (REQUIRED if colony had any failures or retries)
   For each failure or dead end encountered:
   - What approach was tried?
   - Why did it fail?
   - What should be done instead?
   Tag these as sub_type: "anti_pattern" (for skills) or "bug" (for experiences).

   ## Project Conventions Discovered
   For each convention or API pattern specific to THIS project:
   - What is the convention?
   - Where is it enforced?
   Tag these as sub_type: "convention".
   ```

B. **Weight negative signals in retrieval.** In the `_STATUS_BONUS` dict
   (surface/knowledge_catalog.py:231-234), add entries for anti_pattern
   and bug sub_types. Currently the dict maps entry status ("verified",
   "active", "candidate", "stale") to bonuses. Add a secondary check:
   when an entry's `sub_type` is "anti_pattern" or "bug", apply a 0.15
   status bonus if the query context matches their failure domain.
   This ensures "don't use recursive tree traversal > 1000 nodes" surfaces
   when a colony is about to do recursive tree traversal.

C. **Failed colony extraction.** Currently `_hook_memory_extraction()` may
   skip failed colonies or extract less from them. Ensure failed colonies
   get FULL extraction with emphasis on failure patterns. The most valuable
   knowledge comes from failures.

**Code delta:** ~40 lines in colony_manager.py (prompt changes), ~20 lines
in knowledge_catalog.py (status bonus for anti_pattern/bug sub_types).

**New tests (3):**
1. `test_extraction_prompt_includes_failure_section` -- prompt text check
2. `test_anti_pattern_status_bonus` -- scoring math gives bonus
3. `test_failed_colony_gets_extraction` -- failed colony triggers extraction

**Owned files:**
- `src/formicos/surface/colony_manager.py` -- extraction prompt
- `src/formicos/surface/knowledge_catalog.py` -- _STATUS_BONUS addition
- `tests/unit/surface/test_colony_manager.py` -- new tests
- `tests/unit/surface/test_knowledge_catalog.py` -- status bonus tests

**Do not touch:** `core/events.py`

**Validation:**
```bash
pytest tests/unit/surface/test_colony_manager.py tests/unit/surface/test_knowledge_catalog.py -q
```

---

## Track 5 -- UI: Queen Conversation Quality

**Problem:** The Queen's new capabilities (search_codebase, run_command,
edit_file, failure notifications, parallel aggregation) are invisible in
the chat UI. Tool results are buried in prose. Failed colonies look
identical to successes. Parallel colony results arrive as disconnected
cards.

**Current state (queen-chat.ts, 399 lines):**
- `_renderMessage()` at lines 205-296 dispatches on `render` hint
- Result cards rendered via `<fc-result-card>` at lines 240-256
- Proposal cards via `<fc-proposal-card>` at lines 259-279
- No edit proposal rendering
- No failure-specific styling
- No parallel group rendering

**Design:**

A. **Edit proposal card.** New `fc-edit-proposal` component
   (edit-proposal.ts, ~150 lines):
   - File path header
   - Unified diff view with syntax highlighting (red/green lines)
   - Reason text
   - "Apply" / "Reject" action buttons
   - Wire into queen-chat.ts: detect `render="edit_proposal"`

B. **Failure result card styling.** Modify `fc-result-card` to detect
   `meta.status === "failed"`:
   - Red left border accent (instead of green)
   - Error summary prominently displayed
   - "Retry" button that sends "retry colony {id} with different approach"
   - "Inspect" button that navigates to colony detail

C. **Parallel group card.** New `fc-parallel-result` component
   (parallel-result.ts, ~120 lines):
   - Plan summary header
   - Grid of colony result badges (green check / red X per colony)
   - Expandable per-colony detail
   - Overall cost and duration
   - Wire into queen-chat.ts: detect `render="result_card"` with
     `meta.plan_id`

D. **Tool result inline cards.** When the Queen uses search_codebase or
   run_command, show collapsible result cards inline:
   - Code search results: file list with line numbers, expandable
   - Command output: monospace block, collapsible if > 5 lines
   - These are rendered from the Queen's reply text using markdown
     code blocks -- enhance the markdown renderer to detect and style
     tool output patterns

**Code delta:** ~400 lines total. edit-proposal.ts (~150), parallel-result.ts
(~120), queen-chat.ts modifications (~80), result-card.ts failure styling
(~50).

**New tests:** Frontend components -- manual visual verification.
Add 2 unit tests for message dispatch routing in queen-chat.ts.

**Owned files:**
- `frontend/src/components/edit-proposal.ts` (NEW)
- `frontend/src/components/parallel-result.ts` (NEW)
- `frontend/src/components/queen-chat.ts` -- new render dispatches
- `frontend/src/components/result-card.ts` -- failure styling
- `frontend/src/types.ts` -- EditProposal, ParallelResult types

**Do not touch:** Backend files, `formicos-app.ts`

**Validation:**
```bash
# Visual verification: run docker compose, test each card type
# Type check:
npx tsc --noEmit  # if tsconfig exists, else visual only
```

---

## Track 6 -- Operator Knowledge Editing

**Problem:** The knowledge browser (knowledge-browser.ts, 1085 lines) is
read-only except for thumbs-up/thumbs-down feedback (Wave 60, lines
576-586). The operator cannot edit entry content, delete entries, change
tags, or manually create entries. The "institutional memory" is a black box.

**Current state:**
- Knowledge browser shows entries with: title, content preview, confidence
  bars, domain tags, score breakdown, feedback buttons
- `PUT /api/v1/knowledge/{id}/feedback` exists (routes/api.py)
- No PUT/DELETE/POST for knowledge entries themselves
- Events available: `MemoryEntryCreated` (line 744 in events.py),
  `MemoryEntryRefined` (line 1312, has `refinement_source` field),
  `MemoryConfidenceUpdated` (line 879)
- `KnowledgeEntryOperatorAction` (line 1472) exists for pin/unpin/mute etc.
- Projections track entries in `memory_entries` dict

**Design:**

A. **REST endpoints in routes/api.py:**

   `PUT /api/v1/knowledge/{entry_id}` -- update entry fields.
   Accepts JSON body: `{title?, content?, tags?, primary_domain?, sub_type?}`.
   Emits `MemoryEntryRefined` with `refinement_source="operator_edit"`.
   Updates projections. Re-embeds the entry in Qdrant if content changed.

   `DELETE /api/v1/knowledge/{entry_id}` -- soft delete.
   Sets status to "deprecated". Emits `MemoryConfidenceUpdated` with
   `new_alpha=0.01, new_beta=100` (effectively kills retrieval score).
   Does NOT delete from event store or Qdrant -- entry is just deprioritized
   to near-zero confidence. Reversible via future "restore" endpoint.

   `POST /api/v1/knowledge` -- create entry from operator input.
   Accepts JSON body: `{title, content, primary_domain?, sub_type?, tags?}`.
   Emits `MemoryEntryCreated` with `source="operator"` in entry dict.
   Default confidence: Beta(3, 2) -- slightly positive prior since operator
   manually authored it. Default status: "verified" (operator-authored
   entries skip candidate review). Default decay_class: "stable".

B. **Knowledge browser UI additions (knowledge-browser.ts):**

   "Add Entry" button at top of browser -> modal with fields:
   title (required), content (required, textarea), domain (dropdown from
   known domains + free text), sub_type (dropdown), tags (comma-separated).

   Per-entry "Edit" button -> same modal pre-filled with current values.
   On save: PUT to API, optimistic UI update.

   Per-entry "Delete" button -> confirmation dialog ("This will deprecate
   the entry. It can be restored later."). On confirm: DELETE to API,
   remove from visible list (or gray out with "deprecated" badge).

C. **Re-embedding on content edit.** When content changes via PUT, the
   API handler must re-embed the entry in Qdrant. Call the existing
   `vector_port.upsert()` with the new content embedding. This ensures
   edited entries are retrievable by their updated semantics.

**Code delta:** ~150 lines in routes/api.py (3 endpoints + validation),
~200 lines in knowledge-browser.ts (modal + buttons + API calls),
~30 lines in projections.py (handle operator-edited entries in replay).

**New tests (6):**
1. `test_put_knowledge_updates_entry` -- PUT returns 200, entry updated
2. `test_put_knowledge_emits_refined_event` -- MemoryEntryRefined emitted
3. `test_delete_knowledge_soft_deletes` -- DELETE sets deprecated status
4. `test_delete_knowledge_kills_confidence` -- alpha ~0, beta=100
5. `test_post_knowledge_creates_entry` -- POST returns 201, entry in store
6. `test_post_knowledge_operator_source` -- source="operator", status="verified"

**Owned files:**
- `src/formicos/surface/routes/api.py` -- 3 new endpoints
- `src/formicos/surface/projections.py` -- operator edit handling
- `frontend/src/components/knowledge-browser.ts` -- modal + buttons
- `frontend/src/types.ts` -- KnowledgeEditPayload type
- `tests/integration/test_knowledge_api.py` -- new tests

**Do not touch:** `core/events.py` (reusing existing event types),
`surface/knowledge_catalog.py` (retrieval unchanged)

**Validation:**
```bash
pytest tests/integration/test_knowledge_api.py -q
ruff check src/ && python scripts/lint_imports.py
```

---

## Track 7 -- Operator Workflow Editing

**Problem:** Workflow steps are Queen-mediated only. The operator can set
thread goals and add steps via the Queen, but cannot directly edit, reorder,
delete, or skip workflow steps from the UI. This makes workflows feel like
the Queen's plan, not the operator's plan.

**Current state:**
- `WorkflowStepDefined` event (events.py:907-915) with `step: WorkflowStep`
- `WorkflowStepCompleted` event (events.py:917-930)
- Projections store steps in `thread.workflow_steps` list (projections.py:530)
- `WorkflowStepPreview` type in types.ts:460-466
- Thread timeline includes workflow steps (projections.py:2314-2318)
- No REST endpoint for step CRUD (steps are created via Queen tool calls)

**Design -- new event:**

```python
class WorkflowStepUpdated(BaseModel):
    """Operator directly edited a workflow step (Wave 63)."""
    workspace_id: str
    thread_id: str
    step_index: int
    # Fields that changed (all optional -- only changed fields present)
    new_description: str = ""
    new_status: str = ""         # "pending" | "skipped" | "in_progress"
    new_position: int = -1       # -1 means no reorder
    notes: str = ""
```

This is event #66. Requires ADR-049 (operator approval obtained).
Justification: WorkflowStepCompleted records colony-driven completion
(with colony_id, success, artifacts). Operator edits are fundamentally
different -- they change description, skip steps, reorder, or add notes.
Mixing these into WorkflowStepCompleted would corrupt the colony-completion
semantics.

A. **REST endpoints in routes/api.py:**

   `GET /api/v1/workspaces/{ws_id}/threads/{thread_id}/steps` -- list steps.
   Returns workflow_steps from projections.

   `POST /api/v1/workspaces/{ws_id}/threads/{thread_id}/steps` -- add step.
   Emits WorkflowStepDefined (existing event). Returns the new step.

   `PUT /api/v1/workspaces/{ws_id}/threads/{thread_id}/steps/{index}` --
   edit step. Emits WorkflowStepUpdated (new event). Supports: description
   change, status change (pending/skipped/in_progress), notes, reorder.

   `DELETE /api/v1/workspaces/{ws_id}/threads/{thread_id}/steps/{index}` --
   mark step as skipped (not hard delete -- event store is append-only).
   Emits WorkflowStepUpdated with new_status="skipped".

B. **Projection handler for WorkflowStepUpdated:**

   In projections.py, add handler that updates the thread's workflow_steps
   list: applies description/status/notes changes, handles reorder by
   moving the step to new_position and shifting others.

C. **Workflow step editor UI.** Add to the thread detail view (or a new
   `fc-workflow-editor` component):

   - Step list with drag handles for reorder (use native HTML5 drag-and-drop
     or simple up/down buttons for v1)
   - Inline edit for step description (click to edit, Enter to save)
   - Status toggles: pending -> in_progress -> completed -> skipped
   - "Add Step" button at bottom
   - Notes field per step (expandable)
   - Each operation fires the appropriate API call

   For v1, use up/down arrow buttons instead of full drag-and-drop.
   Drag-and-drop is a polish item for a future wave.

**Code delta:** ~30 lines in events.py (new event + union update),
~100 lines in routes/api.py (4 endpoints), ~40 lines in projections.py
(handler), ~250 lines in frontend (workflow-editor component or thread
detail additions).

**New tests (5):**
1. `test_list_workflow_steps` -- GET returns step list
2. `test_add_workflow_step` -- POST emits WorkflowStepDefined
3. `test_edit_workflow_step` -- PUT emits WorkflowStepUpdated
4. `test_skip_workflow_step` -- DELETE sets status to skipped
5. `test_reorder_workflow_step` -- PUT with new_position reorders

**Owned files:**
- `src/formicos/core/events.py` -- WorkflowStepUpdated event (#66)
- `src/formicos/surface/routes/api.py` -- 4 endpoints
- `src/formicos/surface/projections.py` -- new handler
- `frontend/src/components/workflow-editor.ts` (NEW) or additions to
  existing thread detail view
- `frontend/src/types.ts` -- WorkflowStepEdit type
- `tests/integration/test_workflow_api.py` -- new tests

**Do not touch:** `engine/runner.py`, `surface/queen_runtime.py`
(Queen tools for workflow are unchanged -- operator UI is additive)

**Validation:**
```bash
pytest tests/integration/test_workflow_api.py tests/unit/core/test_settings.py -q
ruff check src/ && python scripts/lint_imports.py
```

---

## Track 8 -- Project Context Seeding

**Problem:** Every colony starts cold. The operator knows "this project uses
FastAPI with SQLAlchemy, auth expects JWT with workspace_id claim, we use
pytest with conftest.py fixtures" but the colony doesn't. The knowledge
system tries to accumulate this from colony outcomes -- slowly, noisily,
and with near-zero delta vs model training data. The operator should be
able to declare project context once and have it injected everywhere.

**Current state:**
- `assemble_context()` in engine/context.py:453-468 builds agent context
- Operational playbook injection at position 2.5 (lines 493-496)
- Common mistakes at position 2.6 (lines 498-503)
- Structural context (file listing) at position 2a (lines 505-511)
- Queen context built in `respond()` at queen_runtime.py:498-623
- No `.formicos/` directory convention exists

**Design:**

A. **`.formicos/project_context.md` file convention.** When a workspace
   has this file, its contents are treated as high-priority project-specific
   knowledge. Format: free-form markdown. Operator writes whatever they
   want about their project -- tech stack, conventions, API patterns,
   deployment targets, gotchas.

B. **Colony context injection.** In `assemble_context()` (engine/context.py),
   add a new position 2.4 -- BEFORE operational playbook (2.5) and common
   mistakes (2.6). Project context is the highest-priority injected
   knowledge because it's operator-authored and project-specific.

   ```python
   # Position 2.4: Project context (Wave 63)
   if project_context:
       _pc_text = project_context[:2000]  # cap at ~1200 tokens
       messages.append({
           "role": "system",
           "content": f"# Project Context (operator-authored)\n{_pc_text}",
       })
   ```

   The `project_context` parameter is passed from colony_manager.py which
   reads `.formicos/project_context.md` from the workspace at colony start.

C. **Queen context injection.** In `respond()` (queen_runtime.py), inject
   project context after knowledge retrieval (line 539) and before thread
   context (line 541). Same 2000-char cap.

D. **Archivist consistency check.** Add a line to the extraction prompt:
   "Check new extractions against the project context below. Do not extract
   entries that restate or contradict the operator's declared conventions."
   Include a truncated (500 char) version of project_context.md in the
   extraction prompt. This prevents "use SQLAlchemy for database access"
   entries when the operator already declared that.

E. **UI: project context editor.** The workspace browser
   (workspace-browser.ts) already shows workspace files. Add a
   "Project Context" tab or prominent button that:
   - Creates `.formicos/project_context.md` if it doesn't exist
   - Opens an inline editor (textarea with markdown preview)
   - Saves via the existing `write_workspace_file` mechanism

**Code delta:** ~50 lines in engine/context.py (position 2.4 injection),
~30 lines in queen_runtime.py (Queen injection), ~20 lines in
colony_manager.py (file read + parameter passing), ~15 lines in
colony_manager.py extraction prompt, ~60 lines in workspace-browser.ts.

**New tests (3):**
1. `test_project_context_injected_before_playbook` -- assembly order check
2. `test_project_context_caps_at_2000` -- truncation
3. `test_queen_sees_project_context` -- respond() includes it in messages

**Owned files:**
- `src/formicos/engine/context.py` -- position 2.4 injection
- `src/formicos/surface/queen_runtime.py` -- Queen injection
- `src/formicos/surface/colony_manager.py` -- file read + extraction prompt
- `frontend/src/components/workspace-browser.ts` -- editor UI
- `tests/unit/engine/test_context.py` -- new tests

**Do not touch:** `core/events.py`, `surface/knowledge_catalog.py`

**Validation:**
```bash
pytest tests/unit/engine/test_context.py -q
ruff check src/ && python scripts/lint_imports.py
```

---

## Dependency Graph

```
Track 1 (tool memory)      -- independent
Track 2 (failure + agg)    -- independent
Track 3 (write tools)      -- independent (benefits from Track 1 at runtime)
Track 4 (negative signals) -- independent
Track 5 (UI cards)         -- DEPENDS ON Track 2 (failure card), Track 3 (edit card)
Track 6 (knowledge edit)   -- independent
Track 7 (workflow edit)    -- independent (needs event addition to core/events.py)
Track 8 (project context)  -- independent
```

## Team Assignment (3 coder teams)

| Team | Tracks | Rationale |
|------|--------|-----------|
| Team A (Backend Queen) | 1, 2, 3 | All in queen_runtime.py + queen_tools.py. Sequential: 1 first (memory), then 2 (failure notifications + aggregation in queen_runtime.py), then 3 (write tools). Team A owns queen_runtime.py exclusively. Note: Track 2's gate removal at colony_manager.py:1231 is a 1-line change -- Team B applies it when they work on colony_manager.py for Tracks 4/8. |
| Team B (Backend Operator) | 4, 6, 7, 8 | Independent tracks touching routes/api.py, colony_manager.py, context.py, events.py. Team B owns colony_manager.py (including the 1-line gate removal from Track 2). Track 7 adds the new event. Track 8 is smallest, do last. |
| Team C (Frontend) | 5, 6-UI, 7-UI, 8-UI | All frontend components. Depends on Team A/B for API shapes. Start with Track 5 (cards), then 6-UI (knowledge modal), 7-UI (workflow editor), 8-UI (project context editor). |

## File Overlap Matrix

| File | Tracks | Resolution |
|------|--------|------------|
| queen_runtime.py | 1, 2, 3 | Team A owns exclusively. Sequential execution. |
| queen_tools.py | 3 | Team A only. |
| routes/api.py | 6, 7 | Team B owns. Track 6 endpoints first, then Track 7. |
| colony_manager.py | 2, 4, 8 | Team B owns exclusively. Gate removal from Track 2 (1 line at 1231) is applied by Team B. Extraction prompt (4) and file read (8) are non-overlapping sections. |
| projections.py | 6, 7 | Team B owns. Non-overlapping handlers. |
| events.py | 7 | Team B only. One new event type. |
| context.py | 8 | Team B only. |
| types.ts | 5, 6, 7 | Team C owns. Additive types, no conflicts. |
| knowledge-browser.ts | 6 | Team C only. |
| queen-chat.ts | 5 | Team C only. |
| workspace-browser.ts | 8 | Team C only. |

## Merge Order

1. Team B: Track 7 (events.py change FIRST -- other tracks need clean union)
2. Team A: Track 1 (tool memory -- foundation for everything else)
3. Team B: Track 4 (negative signals -- standalone)
4. Team A: Track 2 (failure notifications)
5. Team B: Track 8 (project context)
6. Team B: Track 6 (knowledge editing API)
7. Team A: Track 3 (write tools)
8. Team C: Track 5 + 6-UI + 7-UI + 8-UI (all frontend)

## Acceptance Criteria

After Wave 63:
- [ ] Queen remembers tool results from the last 3 turns
- [ ] Failed colonies produce follow-up notifications with error details
- [ ] Parallel colony results arrive as one grouped card
- [ ] Queen can propose file edits with diff preview, apply on confirmation
- [ ] Queen can run tests and return structured results
- [ ] Queen can create and delete files with confirmation
- [ ] Failed colonies get full extraction with emphasis on failure patterns
- [ ] Operator can create, edit, and soft-delete knowledge entries from UI
- [ ] Operator can add, edit, reorder, and skip workflow steps from UI
- [ ] Project context from `.formicos/project_context.md` is injected into
      every colony and every Queen response
- [ ] 66 event types (WorkflowStepUpdated added)
- [ ] 30 Queen tools (27 + edit_file + run_tests + delete_file)
- [ ] 3500+ tests passing

## Does NOT Do

- No new event types beyond WorkflowStepUpdated (knowledge editing reuses
  existing events)
- No hard-delete of knowledge entries (soft-delete only, reversible)
- No drag-and-drop workflow reorder (up/down buttons for v1)
- No auto-apply of edits without operator confirmation
- No edit_file on files outside the workspace root
- No streaming of test output (batch result only)
- No changes to the 7-signal retrieval weights (knowledge_catalog.py gets
  a minor status bonus for anti_patterns, not a weight change)
- No changes to the closed event union beyond the one addition
- No addon system work (that's Wave 64)
