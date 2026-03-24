# Queen Orchestration Implementation Reference

Current-state reference for FormicOS queen orchestration: tool dispatch,
colony spawning, parallel DAG execution, workflow steps, thread management,
follow-up logic, and proactive briefing injection. Code-anchored to Wave 59.

---

## Architecture

The Queen is the operator-facing orchestration agent. It receives operator
messages, reasons with tools, spawns colonies, and manages workflow threads.

Three classes:
- `QueenAgent` (`surface/queen_runtime.py`) — main orchestration loop.
- `QueenToolDispatcher` (`surface/queen_tools.py`) — 21 tool handlers.
- `QueenThreadManager` (`surface/queen_thread.py`) — thread lifecycle.

---

## QueenAgent (`surface/queen_runtime.py`)

### Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `_MAX_TOOL_ITERATIONS` | 7 | Tool loop cap per respond() call |
| `_QUEEN_TOOL_OUTPUT_CAP` | 2000 | Max chars per tool result |
| `_QUEEN_MAX_TOOL_HISTORY_CHARS` | 16000 | 8x tool output cap |
| `_THREAD_TOKEN_BUDGET` | 6000 | Compaction threshold |
| `_RECENT_WINDOW` | 10 | Messages always kept raw |

### respond()

```python
async def respond(self, workspace_id: str, thread_id: str) -> QueenResponse
```

Execution flow:

1. **Thread validation** — fetch thread projection.
2. **Pre-spawn memory retrieval** (Wave 26 B3) — inject relevant knowledge
   from last operator message.
3. **Thread workflow context** (Wave 29) — append goal, step status, colony
   progress summary.
4. **Proactive intelligence briefing** (Wave 34-39) — inject up to:
   - 3 knowledge-health insights
   - 2 performance insights
   - 2 learning-loop insights
   - 3 evaporation recommendations
   - 4 configuration recommendations
5. **LLM completion loop** — up to 7 tool iterations. Tool results wrapped
   as untrusted data. History compacted when exceeding 16000 chars.
6. **Intent fallback** (Wave 13) — parse prose directives if no tool calls.
7. **Emit QueenMessage** with optional `intent`, `render`, `meta` fields
   (Wave 49 replay-safe card rendering).
8. Return `QueenResponse(reply, actions)`.

### follow_up_colony()

```python
async def follow_up_colony(
    self, colony_id: str, workspace_id: str, thread_id: str,
    step_continuation: str = "",
) -> None
```

Called when a Queen-spawned colony completes. Preconditions:
- Thread has operator message within last 30 minutes (or step_continuation
  present for gate relaxation).
- Colony was Queen-spawned in that thread.

Generates quality-aware summary (quality >= 0.7 / >= 0.4 / < 0.4), contract
satisfaction status, and optional step continuation prompt. Emits structured
metadata for frontend cards including colonyId, task, status, rounds, cost,
qualityScore, entriesExtracted, validatorVerdict, contractSatisfied.

### Thread History Compaction (Wave 49)

When total tokens > 6000 or messages > 10:
1. Split into older + recent (last 10 always raw).
2. Pin messages in older region: `intent == "ask"` (unresolved questions),
   `render == "preview_card"` (active decisions).
3. Compact older messages into structured summary blocks.
4. Return: compaction summary + pinned messages + recent window.

---

## Queen Tools (21 tools)

All defined in `QueenToolDispatcher.tool_specs()` in `surface/queen_tools.py`.

### Colony Management

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `spawn_colony` | Spawn single worker colony | task, castes, max_rounds (1-50, default 25), budget_limit (0.01-50, default 5.0), strategy, target_files, fast_path, preview |
| `spawn_parallel` | Multi-colony DAG orchestration | reasoning, tasks, parallel_groups, estimated_total_cost, knowledge_gaps, preview |
| `kill_colony` | Terminate running colony | colony_id |
| `redirect_colony` | Redirect colony to new goal | colony_id, new_goal, reason |
| `escalate_colony` | Escalate compute tier | colony_id, tier (standard/heavy/max), reason |
| `inspect_colony` | Detailed colony status | colony_id |
| `read_colony_output` | Full agent output for round | colony_id, round_number, agent_id |

### Workflow Management

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `set_thread_goal` | Set workflow goal + outputs | goal, expected_outputs |
| `complete_thread` | Mark thread complete | reason |
| `archive_thread` | Archive + decay entries | reason |
| `define_workflow_steps` | Define step sequence | steps array (description, expected_outputs, template_id, strategy, input_from_step) |

### Knowledge and Status

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `get_status` | Workspace overview | workspace_id |
| `memory_search` | Search institutional memory | query, entry_type, limit (max 10) |
| `queen_note` | Thread-scoped preferences | action (save/list), content |

### Configuration

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `suggest_config_change` | Propose config change | param_path, proposed_value, reason |
| `approve_config_change` | Apply pending proposal | — |
| `list_templates` | Available colony templates | — |
| `inspect_template` | Full template details | template_id |

### Workspace and Services

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `read_workspace_files` | List workspace data files | workspace_id |
| `write_workspace_file` | Write text file | filename, content |
| `query_service` | Query active service | service_type, query, timeout (max 60s) |

---

## Parallel Colony Orchestration (ADR-045)

### DelegationPlan Structure

```python
class ColonyTask(BaseModel):
    task_id: str
    task: str
    caste: str            # coder|reviewer|researcher|archivist
    strategy: str = "sequential"
    max_rounds: int = 5
    budget_limit: float = 1.0
    depends_on: list[str] = []     # task IDs that must complete first
    input_from: list[str] = []     # task IDs whose output feeds this
    target_files: list[str] = []

class DelegationPlan(BaseModel):
    reasoning: str
    tasks: list[ColonyTask]
    parallel_groups: list[list[str]]  # task IDs per execution group
    estimated_total_cost: float = 0.0
    knowledge_gaps: list[str] = []
```

### Execution Flow

1. **Validate** — unique task_ids, parallel_groups cover all tasks exactly
   once, depends_on references exist.
2. **DAG validation** — `_validate_dag()` using Kahn's algorithm. Builds
   adjacency from `depends_on`, counts in-degrees, processes zero-indegree
   nodes. Returns True if visited == total tasks (no cycles).
3. **Preview mode** — if `preview=True`, return validated plan summary
   without dispatching.
4. **Emit `ParallelPlanCreated`** event with plan, groups, reasoning,
   knowledge_gaps, estimated_cost.
5. **Sequential group execution** — for each group, concurrent dispatch
   via `asyncio.gather`. Each task: build CasteSlot, resolve input sources
   from completed tasks, spawn colony, start colony (fire-and-forget).

---

## Workflow Steps

### WorkflowStep Model (`core/types.py`)

```python
class WorkflowStep(BaseModel):
    step_index: int           # zero-based position
    description: str
    expected_outputs: list[str] = []
    template_id: str = ""
    strategy: str = "stigmergic"
    status: WorkflowStepStatus  # pending|running|completed|failed|skipped
    colony_id: str = ""
    input_from_step: int = -1   # -1 = no dependency
```

Steps are Queen scaffolding — the Queen always decides whether to proceed.
They are NOT an execution pipeline.

### Step Detection

Queen reads `thread.workflow_steps` during message building: shows last 5
completed + all pending/running. Colony completion triggers step continuation
(Wave 31 A1) via `follow_up_colony(step_continuation=...)`.

---

## Operator Directives (ADR-045 D3)

### Four Types

```python
class DirectiveType(StrEnum):
    context_update = "context_update"
    priority_shift = "priority_shift"
    constraint_add = "constraint_add"
    strategy_change = "strategy_change"
```

### Delivery

Directives are delivered via `ColonyChatMessage` event metadata. Stored in
`ColonyContext.pending_directives`. Injection: urgent directives appear
before task description; normal directives appear after task context.

```python
class OperatorDirective(BaseModel):
    directive_type: DirectiveType
    content: str
    priority: str = "normal"     # "normal" | "urgent"
    applies_to: str = "all"      # "all" | specific agent_id
```

---

## Thread Management (`surface/queen_thread.py`)

### archive_thread

Emits `ThreadStatusChanged` (-> "archived"). Applies archival decay to
thread entries: equivalent to 30 days of decay in one step. Uses
`ARCHIVAL_EQUIVALENT_DAYS = 30` with decay class gamma.

### Governance Alerts

`on_governance_alert()` reacts to governance alerts for Queen-spawned
colonies. Preconditions: recent operator activity (30 min), running colony,
redirect budget not exhausted.

---

## Configuration Proposals

### Two-gate Validation

1. **Structural safety** — `validate_config_update()` checks syntax.
2. **Queen scope** — `_is_experimentable()` checks against whitelist in
   `config/experimentable_params.yaml`.

Thread-scoped `PendingConfigProposal` with 30-minute TTL. Operator must
call `approve_config_change` to apply.

---

## Message Building

Injection order for Queen LLM context:
1. System prompt (from caste recipe).
2. Latest Queen notes (up to 10).
3. Metacognitive nudges (Wave 26 Track C): `memory_available`,
   `prior_failures`. Cooldown-gated.
4. Compacted conversation history (Wave 49).

Thread context block includes: thread name, goal, status, artifact progress
(done/missing), colony counts, pending steps.

---

## Events Emitted

| Event | Trigger |
|-------|---------|
| `QueenMessage` | Every Queen response (with optional intent/render/meta) |
| `ColonyNamed` | Colony display name generation |
| `ParallelPlanCreated` | spawn_parallel dispatch |
| `ThreadGoalSet` | set_thread_goal |
| `ThreadStatusChanged` | complete_thread, archive_thread |
| `WorkflowStepDefined` | define_workflow_steps |
| `ColonyRedirected` | redirect_colony |
| `ColonyEscalated` | escalate_colony |
| `QueenNoteSaved` | queen_note (save) |

---

## Key Source Files

| File | Purpose |
|------|---------|
| `surface/queen_runtime.py` | QueenAgent, respond(), follow_up, briefing injection |
| `surface/queen_tools.py` | QueenToolDispatcher, 21 tool specs + handlers |
| `surface/queen_thread.py` | QueenThreadManager, archive, workflow steps |
| `core/types.py` | ColonyTask, DelegationPlan, WorkflowStep, OperatorDirective |
| `core/events.py` | QueenMessage, ParallelPlanCreated, ThreadGoalSet |
| `config/experimentable_params.yaml` | Queen-experimentable config whitelist |
