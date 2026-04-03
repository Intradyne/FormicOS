# FormicOS Architecture Audit - Post-Wave 75

This audit traces real code paths across the post-Wave 75 system and records
places where behavior is likely to surprise, confuse, break, or silently
produce wrong results in normal use.

It is organized by problem class, not by feature area. Findings are ordered
roughly by severity inside each section. Every finding is grounded in code.
Where a scaling concern is inferential rather than measured, it is labeled
speculative.

## Executive summary

Status after audit pass:
- 54 findings across 13 sections
- 8 Critical, 30 High, 15 Medium, 1 Low
- 2 issues fixed during the audit pass:
  - Wave 75 receipt and MCP code now uses `colony.round_number`
  - `task_receipts.py` now resolves contracts and sponsors under the same
    `.formicos` root as operations and billing state

The most important remaining risks are structural, not cosmetic:
- economic truth is still split between billing and the live budget surfaces
- workspace and thread identity are still inconsistent across runtime, disk,
  UI, and MCP paths
- overnight autonomy still relies on estimate-only budgeting, partial action
  queue durability, and incomplete journaling
- several external surfaces still assume one default or first workspace
- long-running deployments still replay from event 0 and do linear colony scans
  on token events

Highest-impact remaining risks by scenario:
- Solo developer, first week: the strongest risks are token-truth divergence,
  under-signaled knowledge review, session-summary overwrite, and unbounded
  Queen context injections in the intelligence layer
- Overnight autonomy: the strongest risks are estimate-only budget tracking,
  in-memory daily spend reset on restart, queue crash-safety gaps, incomplete
  journal coverage, and continuation retry loops
- Multi-workspace team: the strongest risks are thread identity collision,
  first-workspace defaults in multiple surfaces, Queen-chat message misrouting,
  and the split between global project files and workspace-scoped operations
- External agent submits work: the strongest risks are missing HTTP auth, A2A
  use of the shared default workspace, receipt semantics that are weaker than
  the contract surface implies, and sponsor eligibility that can change at
  receipt-read time
- Long-running production deployment: the strongest risks are full replay on
  startup, O(colonies) token-event scans, monotonic in-memory colony growth,
  and action-log/history behavior that degrades operational visibility over time

## 1. Data consistency issues

### Critical - Live token truth diverges between billing and the live budget surfaces
Scenarios: 1, 5

Issue: FormicOS has two different definitions of "total tokens." Billing uses
input + output + reasoning tokens, while the live projection and UI surfaces
still treat total tokens as input + output only.

Symptom: The operator can see one token total in the UI and a larger total in
`formicos billing status` for the same period. The live token panels therefore
understate the usage that the billing formula actually prices.

Evidence:
- `src/formicos/surface/projections.py:309-310` - `BudgetSnapshot.total_tokens`
  returns `total_input_tokens + total_output_tokens` only.
- `src/formicos/surface/projections.py:300` - `total_reasoning_tokens` is a
  separate field that IS correctly tracked (via `record_token_spend` at :329-346).
- `src/formicos/surface/metering.py:79-173` - billing aggregates from
  `TokensConsumed` events: `total_tokens = input + output + reasoning`.
- `frontend/src/components/budget-panel.ts:178-180` - UI "Total Tokens" renders
  `total_input_tokens + total_output_tokens`, excluding reasoning. Reasoning is
  shown separately at :188-189 as an "Efficiency" badge, but the headline total
  is understated.
- `src/formicos/surface/projections.py:1371` - per-agent `agent.tokens` accumulates
  `input_tokens + output_tokens` only (no reasoning).
- The Wave 75 MCP billing resource at `mcp_server.py:1410-1427` and receipt
  resource at `mcp_server.py:1429-1465` correctly include reasoning tokens.
  This means Claude Code sees one total while the browser UI shows another.

### Critical - Thread identity is workspace-qualified in events but thread-id-only in disk state and projection routing
Scenarios: 1, 3, 4

Issue: Runtime events treat a thread as `(workspace_id, thread_id)`, but
several downstream paths treat `thread_id` as globally unique across all
workspaces.

Symptom: Two workspaces with the same thread id can collide in session
summaries, thread plans, Queen message routing, and colony placement. The
wrong workspace can end up owning messages, plans, or colonies.

Evidence:
- `src/formicos/surface/runtime.py:663-672` emits `ThreadCreated` with both
  `workspace_id` and `name`.
- `src/formicos/surface/queen_runtime.py:854-855` writes session summaries to
  `.formicos/sessions/{thread_id}.md`.
- `src/formicos/surface/thread_plan.py:31-34` stores thread plans at
  `.formicos/plans/{thread_id}.md`.
- `src/formicos/surface/projections.py:991-1024` handles `ColonySpawned` by
  scanning all workspaces for the first matching `thread_id`.
- `src/formicos/surface/projections.py:1311-1323` handles `QueenMessage` by
  scanning all workspaces for the first matching `thread_id`.

### High - Knowledge review expects per-colony usage data that projections never store
Scenarios: 1, 2

Issue: The knowledge review scanner tries to reconstruct which entries were
used by which failed colonies, but the usage projection only stores aggregate
count and last-accessed time.

Symptom: Outcome-correlated review actions can silently underfire or never
fire, even when bad entries are repeatedly used in failing colonies.

Evidence:
- `src/formicos/surface/knowledge_review.py:282-301` expects
  `projections.knowledge_entry_usage[eid]["colonies"]`.
- `src/formicos/surface/projections.py:1572-1589` only writes
  `{"count": ..., "last_accessed": ...}` for `knowledge_entry_usage`.

### High - Economic state used a different .formicos root than the rest of operations and billing state
Scenarios: 4

**FIXED** during this audit. Both `.parent` calls in `task_receipts.py`
changed to use `Path(data_dir)` directly, matching every other surface module.

Original symptom: `task_receipts.py` resolved contracts and sponsors via
`Path(data_dir).parent / ".formicos"` while everything else used
`Path(data_dir) / ".formicos"`. With default `data_dir = ./data`, the two
trees landed at different filesystem roots.

Evidence (post-fix):
- `src/formicos/surface/task_receipts.py:19` - now `Path(data_dir) / ".formicos" / "contracts"`
- `src/formicos/surface/task_receipts.py:50` - now `Path(data_dir) / ".formicos" / "sponsors.json"`

## 2. Failure modes that lose data or produce wrong results

### Critical - Wave 75 economic surfaces referenced `colony.round` which does not exist on ColonyProjection
Scenarios: 4

**FIXED** during this audit. All three references changed to `colony.round_number`.
Test mock also corrected in `test_task_receipts.py:107`.

Original trigger: Any code path that renders a receipt, the
`formicos://receipt/{task_id}` MCP resource, or the `review-task-receipt`
MCP prompt for a terminal colony would crash with `AttributeError`.

Evidence (post-fix):
- `src/formicos/surface/task_receipts.py:134` - now `colony.round_number`
- `src/formicos/surface/mcp_server.py:1450` - now `colony.round_number`
- `src/formicos/surface/mcp_server.py:1516` - now `colony.round_number`

### High - The action queue can lose records on crash and silently discard partial lines on restart
Scenarios: 2, 5

Trigger: The process crashes or is terminated while appending a JSONL action,
or the file is partially written for any other reason.

Consequence: The active queue can lose pending or executed actions without any
explicit error. Malformed lines are dropped during read, so the queue can
silently forget actions.

Recovery on restart: Partial at best. Well-formed lines survive. Malformed
lines are skipped and not reconstructed.

Evidence:
- `src/formicos/surface/action_queue.py:117-126` appends directly to the JSONL
  file without a temp file, atomic replace, or fsync.
- `src/formicos/surface/action_queue.py:129-145` reads the file line by line
  and silently `continue`s on `json.JSONDecodeError`.
- `src/formicos/surface/action_queue.py:246-285` compaction reads through the
  same tolerant parser and can permanently rewrite the active file without the
  malformed line.

### High - Daily autonomy budget enforcement is estimate-based and never reconciled to actual colony cost
Scenarios: 2

Trigger: Autonomous dispatch happens through maintenance or continuation paths,
and the actual colony cost differs from the estimate.

Consequence: The daily maintenance budget can be exceeded while the system
still reports that it stayed within budget, because spend is tracked from
estimated cost only.

Recovery on restart: No automatic reconciliation. The estimate-based spend
state resets only when the daily budget is reset.

Evidence:
- `src/formicos/surface/self_maintenance.py:302-316` gates dispatch on
  `budget_remaining` versus estimated colony cost.
- `src/formicos/surface/self_maintenance.py:376-384` increments
  `_daily_spend` by estimated cost after spawn.
- `src/formicos/surface/self_maintenance.py:493-509` does the same for
  distillation dispatch.
- `src/formicos/surface/continuation.py:120` hardcodes all continuation
  estimates to `0.12 * 3 = $0.36` regardless of model or task complexity.
- `src/formicos/surface/continuation.py:242-275` increments `_daily_spend` by
  that fixed estimate after spawn.
- The actual colony cost depends on the LLM model, task complexity, and round
  count, and can easily be 5-10x the estimate for cloud models.

### High - Failed continuations can be re-queued indefinitely
Scenarios: 2

Trigger: A continuation action fails, but the underlying thread still has
pending work and remains a continuation candidate on the next sweep.

Consequence: The same work can be proposed again and again with no retry cap
in the continuation path.

Recovery on restart: No. The next sweep recomputes candidates from thread
state and can queue the same continuation again.

Evidence:
- `src/formicos/surface/continuation.py:68-83` deduplicates only against
  continuation actions that are still `pending_review`.
- `src/formicos/surface/continuation.py:214-216` only executes actions in
  `STATUS_APPROVED`.
- `src/formicos/surface/continuation.py:301-303` marks failed executions as
  `STATUS_FAILED`, which removes them from the dedupe set used during the next
  proposal pass.

### High - A2A tasks can run in a missing default workspace and then disappear from workspace-scoped task listings
Scenarios: 4

Trigger: External work is submitted before a `default` workspace exists.

Consequence: The budget gate allows the spawn, `ThreadCreated` is emitted
anyway, but the workspace projection never materializes. The colony may still
exist globally, while workspace-scoped task listings return empty.

Recovery on restart: No automatic repair. The same projection state is rebuilt
from the same event sequence.

Evidence:
- `src/formicos/surface/routes/a2a.py:50` hardcodes `_DEFAULT_WORKSPACE = "default"`.
- `src/formicos/surface/routes/a2a.py:240-250` checks budget, conditionally
  creates a thread in `default`, and spawns the colony there.
- `src/formicos/surface/runtime.py:663-672` emits `ThreadCreated` without
  verifying that the workspace exists.
- `src/formicos/surface/projections.py:933-940` ignores `ThreadCreated` if the
  workspace projection does not exist.
- `src/formicos/surface/projections.py:877-880` returns an empty list from
  `workspace_colonies(...)` when the workspace projection is missing.
- `src/formicos/surface/routes/a2a.py:299-302` lists tasks from
  `workspace_colonies(_DEFAULT_WORKSPACE)`.

## 3. Scaling bottlenecks

### High - Startup replay always rebuilds from event 0
Scenarios: 5

What grows: Total event count.

What slows down: Startup time, because the app replays the full event log into
in-memory projections and then rebuilds the memory store from projection state.

Approximate scale: User-visible once the event log reaches the tens of
thousands and startup becomes part of normal operational recovery.

Architecture note: This is an architectural bottleneck in the current replay
model, not just a local implementation quirk.

Evidence:
- `src/formicos/surface/app.py:504-516` replays all events on startup and then
  rebuilds the memory store from projection state.
- `src/formicos/surface/projections.py:772-776` replay is a plain loop over all
  events with no snapshot or checkpoint seam in this layer.

### High - Token accounting work is O(number of colonies) for every TokensConsumed event
Scenarios: 5

What grows: Number of colonies and number of token events.

What slows down: Replay and live token accounting, because each
`TokensConsumed` event scans every colony until it finds the matching agent.

Approximate scale: User-visible once token events become the dominant event
type and completed colonies number in the hundreds.

Architecture note: This is fixable inside the current architecture, but the
current path is linear in colony count.

Evidence:
- `src/formicos/surface/projections.py:1361-1377` loops over
  `store.colonies.values()` for every `TokensConsumed` event before it can
  update a single matching colony.

### Medium - Competing-pair rebuild is quadratic in eligible knowledge entries (speculative)
Scenarios: 5

What grows: Verified/promoted knowledge entries.

What slows down: Contradiction and competing-pair rebuilds after memory-affecting
changes.

Approximate scale: Likely user-visible once the verified knowledge set is in
the low thousands. This is inferred from the nested-loop implementation, not
from runtime measurements in this audit.

Architecture note: The cost is in the current implementation of the existing
architecture.

Evidence:
- `src/formicos/surface/projections.py:782-820` rebuilds competing pairs from
  the eligible memory set.
- `src/formicos/surface/conflict_resolution.py:142-182` performs pairwise
  contradiction scanning with nested iteration over candidate entries.

### Medium - Action queue queries are whole-file scans, and archived history drops out of the active query surface
Scenarios: 5

What grows: Action count.

What slows down: Action list endpoints and inbox aggregation, because each
query rereads and filters the active JSONL file in Python.

Approximate scale: The active file is capped at 500 entries after compaction,
so the hot-path cost is moderate. The more important long-run effect is that
older action history falls out of the active API surface once archived.

Architecture note: This is a limitation of the current JSONL-plus-gzip ledger
design.

Evidence:
- `src/formicos/surface/action_queue.py:129-145` rereads the whole active file.
- `src/formicos/surface/action_queue.py:193-216` filters and sorts in Python.
- `src/formicos/surface/action_queue.py:246-285` archives older actions and
  keeps only the newest 500 in the active file.

## 4. UX gaps where the operator is confused or uninformed

### High - First-week knowledge can accumulate with almost no review signal
Scenarios: 1

What the system does silently: It accumulates machine-generated entries, but
the review scanner mostly waits for 3 failed-colony accesses or 5 total
accesses, and the failure-correlated path is already mismatched with the stored
usage schema.

What the operator would need to see or control: Early visibility that the
knowledge base is growing without review, especially before entries become
heavily reused.

Existing surface that could host the information: The Operations inbox and the
knowledge health area already exist, but the scanner rarely feeds them in a new
workspace.

Evidence:
- `src/formicos/surface/knowledge_review.py:34-38` sets the gating thresholds
  for failure and influence.
- `src/formicos/surface/knowledge_review.py:237-242` only queues
  unconfirmed-machine review after 5 accesses.
- `src/formicos/surface/knowledge_review.py:282-301` cannot map per-colony
  accesses from the current usage schema.
- `src/formicos/surface/projections.py:1572-1589` stores only aggregate
  usage count and last-accessed time.

### High - Session continuity is reduced to one overwriteable summary file per thread
Scenarios: 1

What the system does silently: It rewrites the same session summary file for a
thread on each summary emission and then injects only that file on later
starts.

What the operator would need to see or control: A clear sense of whether the
current "prior session" context represents the whole thread or only the most
recent synthesized snapshot.

Existing surface that could host the information: The Operations journal and
Queen thread surfaces already exist, but the session summary path itself is not
operator-visible in the UI.

Evidence:
- `src/formicos/surface/queen_runtime.py:770-860` writes the session summary
  file for a thread.
- `src/formicos/surface/queen_runtime.py:854-855` overwrites
  `.formicos/sessions/{thread_id}.md`.
- `src/formicos/surface/queen_runtime.py:1077-1087` injects that file as the
  "prior session summary" on later responses.

### High - The Operations dashboard hardcodes "Pending Actions" to zero
Scenarios: 2

What the system does silently: It can have real pending review items in the
action queue while the top-level summary row still shows zero.

What the operator would need to see or control: An accurate top-level count
before drilling into the inbox.

Existing surface that could host the information: The existing Operations
summary row already has a dedicated "Pending Actions" slot.

Evidence:
- `frontend/src/components/operations-view.ts:180-189` renders
  `<div class="stat-value">0</div>` for pending actions.
- `frontend/src/components/operations-view.ts:154-160` mounts the real inbox
  component directly below that summary row.

### Medium - Queen history compaction happens inside prompt assembly with no operator-facing signal
Scenarios: 1

What the system does silently: Older Queen-thread history is collapsed into an
internal compacted system block when the estimated prompt budget is exceeded.

What the operator would need to see or control: A visible indication that older
conversation has been summarized away and is no longer being injected raw.

Existing surface that could host the information: The Queen chat or Queen
overview surfaces.

Evidence:
- `src/formicos/surface/queen_runtime.py:174-248` compacts older Queen message
  history into a synthetic "Earlier conversation" block.
- `src/formicos/surface/queen_runtime.py:1900-1905` applies that compaction at
  prompt-build time using the conversation-history budget slot.

### Medium - Project plan staleness is not part of continuation reasoning
Scenarios: 1, 2

What the system does silently: It parses project-plan `Updated:` timestamps but
continuation synthesis does not use them.

What the operator would need to see or control: Whether a milestone is merely
pending or actually stale.

Existing surface that could host the information: The Queen overview project
plan card and operations summary.

Evidence:
- `src/formicos/surface/project_plan.py:69-82` parses the `Updated:` timestamp.
- `src/formicos/surface/operations_coordinator.py:57-64` reduces project-plan
  state to milestone counts.
- `src/formicos/surface/operations_coordinator.py:264-313` computes
  continuation candidates from thread-plan counts, active colonies, and session
  presence, not milestone age.

## 5. Architectural assumptions that limit flexibility

### High - Project-level context is global while operational control is workspace-scoped
Scenarios: 3

Assumption: There is one `project_plan.md` and one `project_context.md` for the
whole instance, while journal, procedures, and action queue state are
workspace-specific.

What it prevents: Truly independent multi-workspace planning and context. A
workspace can have its own procedures and journal but still inherits a global
project plan and project context file.

Can it be relaxed without breaking behavior? Not cleanly in the current file
layout, because the global paths are part of current prompt injection.

Evidence:
- `src/formicos/surface/project_plan.py:37` resolves one global
  `.formicos/project_plan.md`.
- `src/formicos/surface/queen_runtime.py:976-980` reads one global
  `.formicos/project_context.md`.
- `src/formicos/surface/operational_state.py:29-41` resolves
  workspace-scoped journal and procedures files under
  `.formicos/operations/{workspace_id}/...`.

### High - External and Claude-facing surfaces still assume one default or first workspace
Scenarios: 3, 4

Assumption: When no workspace is supplied, the system can safely use either the
hardcoded `"default"` workspace or the first workspace in projection order.

What it prevents: Clean multi-workspace external use, especially from Claude
Code or other MCP clients that do not already know FormicOS' internal
workspace ids.

Can it be relaxed without breaking behavior? Not without touching the current
default-resolution behavior in A2A and MCP.

Evidence:
- `src/formicos/surface/routes/a2a.py:50` hardcodes `_DEFAULT_WORKSPACE = "default"`.
- `src/formicos/surface/mcp_server.py:851-853` defaults `search_knowledge` to
  the first workspace.
- `src/formicos/surface/mcp_server.py:1061-1064` defaults `knowledge-query` to
  the first workspace.
- `src/formicos/surface/mcp_server.py:1219-1221` defaults `delegate-task` to
  the first workspace or `"default"`.
- `src/formicos/surface/mcp_server.py:1338-1340` defaults
  `knowledge-for-context` to the first workspace.

### High - A2A thread identity is derived from task description, not task identity
Scenarios: 4

Assumption: A slugified task description is a stable thread identity for A2A
work.

What it prevents: Isolated repeated tasks with the same description. Reusing
the same description reuses the same thread and therefore the same thread
context.

Can it be relaxed without breaking behavior? Not without changing how A2A task
threads are named and discovered.

Evidence:
- `src/formicos/surface/routes/a2a.py:244-247` computes
  `thread_name = "a2a-" + _slugify(description)` and reuses the existing thread
  if that name already exists.

### Medium - Operator invalidation is retrieval-only, not storage-level cleanup
Scenarios: 5

Assumption: Invalidated entries should disappear from retrieval without being
removed from vector storage.

What it prevents: Storage cleanup and a one-to-one relationship between what
the operator considers invalid and what remains in the vector collections.

Can it be relaxed without breaking behavior? Possibly, but it would change the
current meaning of invalidation versus rejection.

Evidence:
- `src/formicos/surface/knowledge_catalog.py:995-1001` filters invalidated
  entries at retrieval time via operator overlays.
- `src/formicos/surface/memory_store.py:97-100` deletes vectors only when
  entry status becomes `rejected`.

## 6. Cross-surface inconsistencies

### High - Several frontend surfaces ignore the selected workspace and fall back to the first workspace
Scenarios: 3

Surfaces that disagree: Settings, Queen Overview, and the top-bar autonomy
popover versus the rest of the app shell.

Which is correct: The active workspace derived from the selected node in the
tree is the only consistent workspace context in the shell.

What causes the divergence: Some components read `tree[0]` directly instead of
using the shell's active workspace resolution.

Evidence:
- `frontend/src/components/formicos-app.ts:346-351` derives the active
  workspace from the selected node and only falls back to `tree[0]`.
- `frontend/src/components/settings-view.ts:241` sets `_workspaceId` to
  `this.tree[0]?.id`.
- `frontend/src/components/settings-view.ts:403` and
  `frontend/src/components/settings-view.ts:439` also read `this.tree[0]`
  directly.
- `frontend/src/components/queen-overview.ts:195-200` derives its active
  workspace from `this.tree[0]`.
- `frontend/src/components/formicos-app.ts:818` fetches autonomy status for
  `store.state.tree?.[0]?.id`.

### High - Queen chat knows the viewed thread's workspace but does not send it with operator messages
Scenarios: 3

Surfaces that disagree: The Queen chat component versus the app shell message
dispatcher.

Which is correct: The thread's own `workspaceId` is the correct routing target
for messages sent from that thread view.

What causes the divergence: `queen-chat` computes the thread workspace for plan
fetching, but omits `workspaceId` from `send-message` events. The app shell
then falls back to its own active-workspace guess.

Evidence:
- `frontend/src/components/queen-chat.ts:228` derives `wsId` from
  `this.activeThread?.workspaceId`.
- `frontend/src/components/queen-chat.ts:466-467`,
  `frontend/src/components/queen-chat.ts:475-476`,
  `frontend/src/components/queen-chat.ts:501-502`, and
  `frontend/src/components/queen-chat.ts:611-612` dispatch `send-message`
  events with `threadId` and `content`, but no `workspaceId`.
- `frontend/src/components/formicos-app.ts:627` and
  `frontend/src/components/formicos-app.ts:746` route those events using
  `e.detail.workspaceId || this.activeWorkspaceId`.

### Medium - Contract-aware A2A surfaces imply stronger completion semantics than the receipt actually provides
Scenarios: 4

Surfaces that disagree: Task submission with a `contract` versus task result
receipt rendering.

Which is correct: The current receipt only reflects colony terminal status and
stored contract metadata. It does not evaluate contract-defined
`acceptance_tests`.

What causes the divergence: Contract intake validates and stores the contract,
but receipt generation does not consume `acceptance_tests` or any separate
acceptance result.

Evidence:
- `src/formicos/surface/routes/a2a.py:211-227` validates and accepts a
  `contract` object at task submission time.
- `src/formicos/surface/routes/a2a.py:331-336` attaches a receipt to terminal
  results.
- `src/formicos/surface/task_receipts.py:126-145` builds the receipt from
  colony status, token totals, transcript hash, and sponsor status only.

### Medium - MCP defaults and UI defaults diverge in how they choose a workspace
Scenarios: 3

Surfaces that disagree: MCP prompts and tools versus the main UI.

Which is correct: Neither is universally correct. The UI tries to use the
selected workspace, while several MCP surfaces silently pick the first
workspace.

What causes the divergence: MCP helpers apply fallback resolution internally
when `workspace_id` is omitted.

Evidence:
- `src/formicos/surface/mcp_server.py:851-853` defaults `search_knowledge` to
  the first workspace.
- `src/formicos/surface/mcp_server.py:1061-1064` defaults `knowledge-query` to
  the first workspace.
- `src/formicos/surface/mcp_server.py:1219-1221` defaults `delegate-task` to
  the first workspace or `"default"`.
- `src/formicos/surface/mcp_server.py:1338-1340` defaults
  `knowledge-for-context` to the first workspace.
- `frontend/src/components/formicos-app.ts:346-351` uses selected-node
  workspace resolution in the main UI shell.

## 7. Agent-operator handoff gaps

### Critical - Operator-idle detection ignores Queen chat entirely
Scenarios: 2, 3

Specific decision point: Whether the system should treat the operator as idle
enough to continue work autonomously.

What the Queen/system does now: It only scans colony chat messages for recent
operator activity.

What the operator would expect: Queen chat activity should count as active
steering and block idle-time autonomous continuation.

Is the current behavior documented: Not in the code path that computes idle
state.

Evidence:
- `src/formicos/surface/operations_coordinator.py:211-253` computes operator
  activity by scanning only `colony.chat_messages`.
- `src/formicos/surface/projections.py:374` stores colony chat messages.
- `src/formicos/surface/projections.py:522` stores thread `queen_messages`,
  but that collection is not consulted by idle detection.

### High - Newly discovered continuation work does not auto-start without a separate approval transition
Scenarios: 2

Specific decision point: Whether idle-time autonomy should continue a thread
that the sweep just identified as ready for autonomy.

What the Queen/system does now: It always queues continuation proposals as
approval-required actions, and idle execution only consumes already-approved
continuation actions.

What the operator would expect: In an `autonomous` workspace, newly discovered
low-risk continuation work would either start automatically or be clearly
presented as approval-gated. The current behavior is internally split.

Is the current behavior documented: The code path itself is explicit, but the
automation boundary is not visible from the queue state alone.

Evidence:
- `src/formicos/surface/continuation.py:43-127` creates continuation actions
  with `requires_approval=True` and `status=pending_review`.
- `src/formicos/surface/continuation.py:207-216` refuses idle execution unless
  the continuation action is already `STATUS_APPROVED`.

### High - Overnight audit is incomplete because some approved-action execution paths do not write the journal
Scenarios: 2

Specific decision point: What counts as the authoritative operator-facing audit
trail for overnight or background actions.

What the Queen/system does now: Idle continuation execution writes the journal,
but other approved-action execution paths mutate queue state and spawn work
without a corresponding journal entry.

What the operator would expect: The journal should be able to reconstruct all
background actions that actually executed.

Is the current behavior documented: Not in code. The execution paths are split.

Evidence:
- `src/formicos/surface/continuation.py:282-289` journals idle continuation
  execution.
- `src/formicos/surface/routes/api.py:1847-1938` approves and executes queued
  actions through the API path without calling `append_journal_entry`.
- `src/formicos/surface/app.py:1027-1085` also processes approved actions in
  the sweep loop without calling `append_journal_entry`.

### High - Sponsor eligibility is decided at receipt-read time, not submission time
Scenarios: 4

Specific decision point: Whether a submitted task is revenue-share eligible.

What the Queen/system does now: It reads the sponsor registry when building the
receipt, not when accepting the task.

What the operator or external agent would expect: Eligibility for a submitted
task is usually expected to be stable once the task has been accepted.

Is the current behavior documented: The code path makes the timing clear, but
the behavior is easy to miss from the task API alone.

Evidence:
- `src/formicos/surface/routes/a2a.py:260-263` stores the contract at task
  submission time.
- `src/formicos/surface/task_receipts.py:104-123` loads the current sponsors
  file and computes `eligible` when the receipt is generated.

---

## 8. Expanded audit: Queen intelligence

### Critical - Concurrent Queen messages on the same thread race without mutual exclusion

Trigger: Operator sends two messages in quick succession on the same thread.

Consequence: Two concurrent `respond()` tasks run simultaneously. Both read
the same thread history, both call `_compact_thread_history()`, both emit
independent `QueenMessage` events. Responses can arrive out of order,
reference the same prior state, or contradict each other.

Evidence:
- `src/formicos/surface/commands.py:131` - `asyncio.create_task(runtime.queen.respond(...))` is fire-and-forget.
- No asyncio.Lock, queue, or per-thread serialization exists in `QueenAgent`.

### High - Memory retrieval injection has no budget guard

Trigger: Knowledge base grows large enough that memory retrieval returns
multi-thousand-character blocks.

Consequence: The memory block is inserted into the prompt with no character
cap, unlike other injections which truncate to `budget.slot * 4`. On small
models (8K context), this can crowd out conversation history.

Evidence:
- `src/formicos/surface/queen_runtime.py:943-961` - memory block inserted
  with no truncation.
- Compare to `queen_runtime.py:980` (project_context) and `:1008` (project_plan)
  which both cap at `budget.X * 4`.

### High - Queen notes and thread context are also unbounded

Trigger: Operator saves many notes or thread accumulates many workflow steps.

Consequence: Same crowding risk as memory retrieval. Up to 10 notes at 500
chars each = 5000 chars injected without budget guard. Thread context
(`_build_thread_context()`) can exceed 3000 chars for detailed threads.

Evidence:
- `src/formicos/surface/queen_runtime.py:1838-1860` - notes injection, no cap.
- `src/formicos/surface/queen_runtime.py:1108-1119` - thread context, no cap.
- `src/formicos/surface/queen_tools.py:147-148` - `_INJECT_NOTES=10`, `_MAX_NOTE_CHARS=500`.

### Medium - Deliberation safety net silently downgrades spawn to propose_plan

Trigger: Operator message matches deliberation regex (e.g., "How should",
"What if") while Queen generates a spawn_colony or spawn_parallel tool call.

Consequence: Tool call is mutated in-place from spawn to propose_plan. The
operator's explicit spawn intent (including strategy, fast_path, caste
selections) is lost. Only a log warning is emitted; no visible feedback.

Evidence:
- `src/formicos/surface/queen_runtime.py:1376-1396` - in-place mutation of
  tool call name from `spawn_colony`/`spawn_parallel` to `propose_plan`.

## 9. Expanded audit: Colony lifecycle

### Critical - Knowledge extraction lacks replay-safety gate

Trigger: Colony completes and server restarts before next checkpoint.

Consequence: `extract_institutional_memory()` has no replay guard (unlike
transcript harvest which checks `memory_extractions_completed`). On replay,
knowledge entries are extracted a second time, duplicating entries and
corrupting confidence tracking.

Evidence:
- `src/formicos/surface/colony_manager.py:1271-2400` - institutional memory
  extraction is fire-and-forget with no `memory_extractions_completed` check.
- `src/formicos/surface/colony_manager.py:1293-1294` - transcript harvest
  correctly checks `harvest_key = f"{colony_id}:harvest"`.
- `src/formicos/surface/projections.py:1665-1667` - handler stores plain
  `e.colony_id`, not the suffixed key that transcript harvest checks against.

### High - Colony kill and completion can race

Trigger: Operator kills a colony that is in the final moments of completing.

Consequence: `ColonyKilled` event emits, then `ColonyCompleted` event emits
from the still-running task. Projection status goes killed -> completed.
Post-colony hooks (knowledge extraction, confidence updates) run as if
colony succeeded.

Evidence:
- `src/formicos/surface/runtime.py:796-806` - kill emits event then cancels task.
- `src/formicos/surface/colony_manager.py:970` - ColonyCompleted can emit before
  CancelledError is received.
- No mutual exclusion between kill and completion paths.

### High - Budget enforcement checks after the round executes

Trigger: Colony is near budget limit, starts an expensive round.

Consequence: Round completes, cost is added, then the budget check fires and
marks the colony as failed. The expensive round already consumed tokens. No
pre-round cost estimation or mid-round budget kill.

Evidence:
- `src/formicos/surface/colony_manager.py:920-933` - budget check at `total_cost >= colony.budget_limit` happens after cost is added.

### Medium - Cost attribution excludes knowledge extraction LLM calls

Trigger: Colony completes and knowledge extraction runs.

Consequence: Extraction uses LLM calls that are not emitted as
`TokensConsumed` events attributed to the colony. Colony cost is
understated. Budget enforcement cannot account for extraction overhead.

Evidence:
- `src/formicos/engine/runner.py:1687-1696` - TokensConsumed emitted per
  agent during rounds only.
- Knowledge extraction LLM calls in colony_manager.py do not emit
  TokensConsumed events attributed back to the colony.

## 10. Expanded audit: Knowledge system

### High - Qdrant failure creates projection orphans

Trigger: Qdrant is temporarily unavailable when a MemoryEntryCreated event
is processed.

Consequence: Entry exists in projections (in-memory) but not in Qdrant
vector storage. The entry appears in `list_memory()` but is unretrievable
via semantic search. No reciprocal cleanup. Condition persists indefinitely.

Evidence:
- `src/formicos/surface/memory_store.py:100` - `self._vector.upsert()` with
  no error handling for upsert failure.
- `src/formicos/adapters/vector_qdrant.py:275-276` - on failure, returns 0
  and logs only, no exception raised.

### High - Federation trust penalties insufficient against high-confidence injection

Trigger: Malicious federation peer sends entries with artificially high
alpha/beta (e.g., alpha=100, beta=0.1).

Consequence: Even with hop discount and federation penalty floor, the
Thompson score is so high (~0.99) that the composite score still ranks the
entry competitively. No alpha/beta bounds validation exists.

Evidence:
- `src/formicos/surface/trust.py:128` - status floor allows 0.35 penalty minimum.
- `src/formicos/engine/scoring_math.py:56-57` - only clamps to 0.1 for safety,
  no upper bound.
- No validation in MemoryConfidenceUpdated that alpha/beta are sane.

### Medium - Dedup fails silently when content_preview is empty

Trigger: Entries with empty `content_preview` and `summary` fields.

Consequence: `_compute_similarity()` returns 0.0 immediately for
preview-less entries. Two identical entries with empty previews are never
flagged as duplicates.

Evidence:
- `src/formicos/surface/maintenance.py:405-407` - returns 0.0 if content
  string is empty.
- No fallback to full `content` field.

## 11. Expanded audit: Operational loop

### Critical - Workflow learning functions are synchronous but awaited in the sweep

Trigger: Every operational sweep iteration.

Consequence: `extract_workflow_patterns()` and `detect_operator_patterns()`
are synchronous functions (`def`, not `async def`). The sweep `await`s them,
which returns the dict/int result immediately (no coroutine). The sweep's
exception handler at app.py:1015-1019 catches and silently discards the
error. Workflow learning never actually runs.

Evidence:
- `src/formicos/surface/workflow_learning.py:36` - `def extract_workflow_patterns(` (not async).
- `src/formicos/surface/workflow_learning.py:129` - `def detect_operator_patterns(` (not async).
- `src/formicos/surface/app.py:1007-1012` - `await extract_workflow_patterns(...)`.

### High - Daily budget tracking is in-memory only, resets on restart

Trigger: Process restart during the same calendar day.

Consequence: `_daily_spend` is a runtime-only dict on `MaintenanceDispatcher`.
On restart, it reinitializes to empty, effectively granting a full daily
budget even if most of it was already consumed before the restart.

Evidence:
- `src/formicos/surface/self_maintenance.py:276-279` - `_daily_spend` is
  instance-scoped, no persistence.
- `src/formicos/surface/self_maintenance.py:591-596` - reset is
  in-memory date comparison only.

### High - Action queue compaction can archive unreviewed pending actions

Trigger: Action queue exceeds 1000 lines.

Consequence: `compact_action_log()` keeps the newest 500 by line order. Old
pending-review actions in the first 500 lines are archived to gzip and become
invisible to the operator, the Queen, and all API endpoints.

Evidence:
- `src/formicos/surface/action_queue.py:264-265` - blind slice with no
  status-aware filtering.
- `src/formicos/surface/action_queue.py:129-146` - `read_actions()` only
  reads the active `.jsonl`, never archives.

### Medium - No sweep reentrancy guard

Trigger: Operational sweep takes longer than 30 minutes.

Consequence: Next sweep iteration starts before the first completes. Both
call `evaluate_and_dispatch()` for the same workspaces, potentially
spawning duplicate colonies and queuing duplicate actions.

Evidence:
- `src/formicos/surface/app.py:924-927` - 30-minute interval with no lock.
- `src/formicos/surface/self_maintenance.py:281-388` - no mutex or dedup.

### Medium - Action queue state machine has no transition validation

Trigger: Any `update_action()` call.

Consequence: Status can transition in any direction (FAILED -> APPROVED,
EXECUTED -> PENDING_REVIEW, etc.). `_VALID_STATUSES` is defined but never
checked in `update_action()`.

Evidence:
- `src/formicos/surface/action_queue.py:149-170` - `act.update(updates)`
  with no state validation.
- `src/formicos/surface/action_queue.py:36-43` - `_VALID_STATUSES` unused.

## 12. Expanded audit: External surfaces

### Critical - No authentication or authorization on any HTTP endpoint

Trigger: Any HTTP client on the network.

Consequence: All REST, A2A, and WebSocket endpoints are unauthenticated.
Any caller can create workspaces, spawn colonies, kill colonies, approve
actions, modify configuration, and drain the LLM budget. No CORS middleware
is registered.

Evidence:
- `src/formicos/surface/app.py:189-192` - `create_app()` adds no auth middleware.
- `src/formicos/surface/routes/api.py` - zero authentication in any handler.
- No CORSMiddleware import or registration anywhere in surface/.

Note: This is a known single-operator design assumption, not an oversight.
But it blocks any shared or exposed deployment.

### High - WebSocket event queue drops events when full

Trigger: High event throughput (e.g., parallel colonies generating rapid
AgentTurnCompleted events).

Consequence: Subscriber queue is capped at 1000 entries. When full,
`queue.put_nowait()` raises `QueueFull`, the event is logged and dropped.
Frontend misses state updates with no catch-up mechanism.

Evidence:
- `src/formicos/surface/ws_handler.py:196` - `asyncio.Queue(maxsize=1000)`.
- `src/formicos/surface/ws_handler.py:246-249` - QueueFull caught, event
  dropped, warning logged.

### High - A2A callers share the default workspace with no isolation

Trigger: Multiple external agents submit tasks.

Consequence: All A2A tasks land in `_DEFAULT_WORKSPACE = "default"`.
External agents can read each other's results via task_id guessing, share
the same knowledge retrieval pool, and exhaust each other's budget.

Evidence:
- `src/formicos/surface/routes/a2a.py:50` - hardcoded default workspace.
- `src/formicos/surface/routes/a2a.py:240-250` - no per-caller isolation.

### Medium - Input validation missing on several endpoints

Trigger: Malformed or oversized payloads.

Consequence: No size limits on `description`, `contract`, `template`
payloads. A2A contract can be arbitrarily large, consuming memory on
`save_contract()`. Template creation accepts unlimited castes and tags.

Evidence:
- `src/formicos/surface/routes/a2a.py:201-290` - unbounded contract dict.
- `src/formicos/surface/routes/api.py:145-168` - unbounded template fields.

## 13. Expanded audit: Event store and replay

### High - Completed colonies are never removed from in-memory projections

What grows: Colony count.

Consequence: Every colony ever spawned persists in `store.colonies` with full
round records, agents, chat messages, artifacts, and knowledge accesses. At
50 colonies/day for a year, this is ~18,000 colonies at ~20KB each = 360MB.
No eviction or archival exists.

Evidence:
- `src/formicos/surface/projections.py:692` - `self.colonies: dict[str, ColonyProjection]`.
- No removal in ColonyCompleted, ColonyFailed, or ColonyKilled handlers.

### Medium - Replay injects non-deterministic monotonic timestamps

Trigger: Server restart and event replay.

Consequence: `last_activity_at` is set from `_time.monotonic()` during
replay, not from event timestamps. Two replays of the same log produce
different values. Governance decisions based on idle watchdog logic become
non-deterministic across restarts.

Evidence:
- `src/formicos/surface/projections.py:1214,1226,1260` - `_time.monotonic()`
  in RoundStarted, AgentTurnStarted, AgentTurnCompleted handlers.

### Medium - AgentTurnCompleted handler scans all colonies O(n)

What grows: Colony count and agent turn event count.

Consequence: Same O(n) per-event scan as TokensConsumed. Both handlers loop
over `store.colonies.values()` to find the matching agent. With 500 colonies
and 37,500 agent turn events, total work is O(18M) during replay.

Evidence:
- `src/formicos/surface/projections.py:1246-1249` - linear scan for agent match.

### Low - Four event types have no projection handlers

Events: `AddonLoaded`, `AddonUnloaded`, `ContextUpdated`, `ServiceTriggerFired`.

Consequence: These events are persisted but produce no projection updates.
They accumulate as inert log entries. Not harmful but means addon lifecycle
and context changes are not queryable from projections.

Evidence:
- `src/formicos/surface/projections.py:2136-2202` - `_HANDLERS` dict has 65
  of 69 event types mapped.


