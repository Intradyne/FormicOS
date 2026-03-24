# API Surface Integration Reference

Status: Current as of 2026-03-18 (Wave 32)
Purpose: Map every external-facing surface's response format, error handling,
and extension points for adding structured guidance (recovery hints, next
actions, human escalation signals).

Any future feature (structured errors, MCP resources, AG-UI events, A2A
enrichment, federation endpoints) should use this document to understand
how each surface works today and where changes plug in.

---

## Table of Contents

- 1 MCP Surface
- 2 A2A Surface
- 3 AG-UI Surface
- 4 WebSocket Surface
- 5 HTTP REST Surface
- 6 Error Handling Cross-Reference
- 7 Response Enrichment Extension Points
- 8 Cross-Surface Consistency

---

## 1. MCP Surface (surface/mcp_server.py)

### 1.1 Server Configuration

| Property              | Value                                      |
|-----------------------|--------------------------------------------|
| FastMCP version       | >=3.0,<4.0 (pyproject.toml)                |
| Transport             | Streamable HTTP (ADR-034)                  |
| Endpoint              | /mcp                                       |
| Stateless             | Yes (stateless_http=True)                  |
| @mcp.resource()       | Not used                                   |
| @mcp.prompt()         | Not used                                   |
| PromptsAsTools        | Not used                                   |
| ResourcesAsTools      | Not used                                   |
| MCP Annotations       | Not used (no readOnlyHint/destructiveHint) |

Mount setup in app.py:
```python
create_streamable_http_app(server=mcp, streamable_http_path="/mcp", stateless_http=True)
```

### 1.2 Tool Registry (19 tools)

Tool ordering is defined by MCP_TOOL_NAMES tuple (lines 21-41) and @mcp.tool()
decorator order in create_mcp_server().

#### 1.2.1 Read-Only Tools

**list_workspaces**
- Signature: `async def list_workspaces() -> list[dict[str, str]]`
- Returns: `[{"id": str, "name": str}, ...]`
- Error handling: None (always returns list, may be empty)
- Projection: runtime.projections.workspaces

**get_status**
- Signature: `async def get_status(workspace_id: str) -> dict`
- Returns: `{"id", "name", "threads": [{"id", "name", "colonies": [{"id", "status", "round"}]}]}`
- Error: `{"error": "workspace '<id>' not found"}`
- Projection: workspaces -> threads -> colonies

**list_templates**
- Signature: `async def list_templates() -> list[dict]`
- Returns: Template list via template_manager.list_templates()
- Error handling: None

**get_template_detail**
- Signature: `async def get_template_detail(template_id: str) -> dict`
- Returns: template.model_dump() or `{"error": "template '<id>' not found"}`

**suggest_team**
- Signature: `async def suggest_team(objective: str) -> list[dict]`
- Returns: Team composition suggestion list
- Error handling: None

**code_execute**
- Signature: `async def code_execute(code: str, timeout_s: int = 10) -> dict`
- Returns (blocked): `{"blocked": true, "reason": str, "exit_code": -1}`
- Returns (ok): `{"blocked": false, "stdout": str, "stderr": str, "exit_code": int}`
- Security: AST-screened via ast_security.check_ast_safety()
- timeout_s clamped to <=30s

**query_service**
- Signature: `async def query_service(service_type: str, query: str, timeout: int = 30) -> dict`
- Returns: `{"response": str}` or `{"error": str}`
- Errors: "colony manager not available", ValueError, TimeoutError

**chat_colony**
- Signature: `async def chat_colony(colony_id: str, message: str) -> dict`
- Returns: `{"status": "sent"}` or `{"error": "colony '<id>' not found"}`
- Event emitted: ColonyChatMessage

#### 1.2.2 Mutating Tools

| Tool              | Parameters                                    | Returns                    | Event(s) Emitted          |
|-------------------|-----------------------------------------------|----------------------------|---------------------------|
| create_workspace  | name                                          | {"workspace_id": name}     | WorkspaceCreated          |
| create_thread     | workspace_id, name                            | {"thread_id": name}        | ThreadCreated             |
| spawn_colony      | workspace_id, thread_id, task, castes,        | {"colony_id": str}         | ColonySpawned             |
|                   | strategy="stigmergic", max_rounds=25,         |                            | + start_colony background |
|                   | budget_limit=5.0, model_assignments, template |                            |                           |
| kill_colony       | workspace_id, colony_id, killed_by="operator" | {"status": "killed"}       | ColonyKilled              |
| chat_queen        | workspace_id, thread_id, content              | {"status": "sent"}         | QueenMessage              |
|                   |                                               |                            | + queen.respond background|
| create_merge      | workspace_id, from_colony, to_colony,         | {"edge_id": str}           | MergeCreated              |
|                   | created_by="operator"                         |                            |                           |
| prune_merge       | workspace_id, edge_id, pruned_by="operator"   | {"status": "pruned"}       | MergePruned               |
| broadcast         | workspace_id, thread_id, from_colony          | {"edges": [str, ...]}      | MergeCreated (N)          |
| approve           | workspace_id, request_id                      | {"status": "approved"}     | ApprovalGranted           |
| deny              | workspace_id, request_id                      | {"status": "denied"}       | ApprovalDenied            |
| activate_service  | workspace_id, colony_id, service_type         | {"status": "activated",    | (service-emitted)         |
|                   |                                               |  "service_type": str}      |                           |
|                   |                                               | or {"error": str}          |                           |

#### 1.2.3 Error Reporting Patterns

Two styles coexist:

1. Error dict return (primary): `return {"error": "descriptive message"}`
   Used by: get_status, get_template_detail, query_service, activate_service,
   chat_colony

2. Exception raise (pre-mutation): ValueError for invalid input (e.g., bad
   source colony in spawn_colony). Only query_service and activate_service
   explicitly catch exceptions.

No custom error classes. No blocking/retry logic.

### 1.3 Projection Data Access Patterns

**Knowledge Catalog (memory_entries)**
- Access: runtime.projections.memory_entries (dict[str, dict])
- Created by: MemoryEntryCreated event
- Updated by: MemoryEntryStatusChanged, MemoryConfidenceUpdated,
  MemoryEntryScopeChanged
- Retrieval: KnowledgeCatalog with composite scoring
  (0.40 semantic + 0.25 thompson + 0.15 freshness + 0.12 status + 0.08 thread)
- Confidence: Beta(alpha, beta) posteriors with Thompson Sampling

**Thread/Workflow State**
- Access: workspace.threads (dict[str, ThreadProjection])
- Fields: id, workspace_id, name, goal, expected_outputs, status
  (active|completed|archived), colonies, queen_messages, workflow_steps,
  continuation_depth, colony_count, completed_colony_count

**Colony Status**
- Access: runtime.projections.colonies[colony_id] (ColonyProjection)
- Fields: id, thread_id, workspace_id, task, status, round_number,
  max_rounds, strategy, castes, model_assignments, convergence, cost,
  budget_limit, quality_score, skills_extracted, display_name, service_type,
  agents, round_records, chat_messages, artifacts, knowledge_accesses,
  failure_reason, failed_at_round, killed_by, killed_at_round

**Workspace Config**
- Access: workspace.config (dict)
- Updated by: WorkspaceConfigChanged, ModelAssignmentChanged
- Fields: budget, strategy, caste-model overrides

**Maintenance Service Status**
- Not projected. Service handlers registered on colony_manager.service_router.
- Handlers: service:consolidation:dedup, service:consolidation:stale_sweep,
  service:consolidation:contradiction, service:consolidation:confidence_reset
- Scheduled via _maintenance_loop() every FORMICOS_MAINTENANCE_INTERVAL_S
  (default 86400s)

### 1.4 Extension Points

1. **MCP Resources** -- FastMCP >=3.0 supports @mcp.resource(). Five
   projection-backed data sources are candidates for MCP resource URIs:
   - `formicos://workspaces/{id}/knowledge` (memory_entries)
   - `formicos://workspaces/{id}/threads` (thread/workflow state)
   - `formicos://colonies/{id}` (colony status)
   - `formicos://workspaces/{id}/config` (workspace config)
   - `formicos://maintenance/status` (maintenance state)
   Mutating tools that change these would need to emit
   ResourceUpdatedNotification for subscription support.

2. **MCP Annotations** -- readOnlyHint, destructiveHint, idempotentHint can
   be added to all 19 tools. Classification above provides the data needed.

3. **MCP Prompts** -- @mcp.prompt() available but unused. Could expose
   prompt templates for common colony patterns.

4. **Structured error returns** -- Current dict returns can be enriched
   with error_code, recovery_hint, suggested_action without breaking the
   existing dict contract. Tools already return dicts, so adding keys is
   backward-compatible for MCP clients that ignore unknown keys.

---

## 2. A2A Surface (surface/routes/a2a.py)

### 2.1 Endpoints

Design: Task ID === Colony ID. No second store (ADR-038).

#### POST /a2a/tasks -- Create Task

Request:
```json
{"description": "<string, required>"}
```

Response (201):
```json
{
  "task_id": "colony-<8-char-hex>",
  "status": "running",
  "team": [{"caste": str, "tier": str, "count": int}],
  "strategy": str,
  "max_rounds": int,
  "budget_limit": float
}
```

Errors:
- 400: `{"error": "invalid JSON body"}`
- 400: `{"error": "description is required"}`

Team selection: template tag match -> keyword classifier -> fallback.
Thread naming: `a2a-<slugified description, max 40 chars>`.
Workspace: always "default".
Non-blocking: colony start scheduled as background asyncio task.

#### GET /a2a/tasks -- List Tasks

Query params: status (optional filter), limit (default 50, clamped [1,100])

Response (200):
```json
{
  "tasks": [{
    "task_id": str,
    "status": str,
    "progress": {"round": int, "max_rounds": int, "convergence": float},
    "cost": float,
    "quality_score": float,
    "failure_context": {...}  // conditional, if failed/killed
  }]
}
```

Error: 400 `{"error": "limit must be an integer"}`

Filter: only colonies whose thread_id starts with "a2a-".
Order: task_id descending (most recent first).

#### GET /a2a/tasks/{task_id} -- Poll Status

Response (200): Same envelope as list item above.
Error: 404 `{"error": "task not found"}`

#### GET /a2a/tasks/{task_id}/result -- Get Result

Response (200):
```json
{
  "task_id": str,
  "status": str,
  "output": str,
  "transcript": {full transcript object},
  "quality_score": float,
  "skills_extracted": int,
  "cost": float
}
```

Errors:
- 404: `{"error": "task not found"}`
- 409: `{"error": "task still running", "status": "<current>"}`

#### DELETE /a2a/tasks/{task_id} -- Cancel Task

Response (200): `{"task_id": str, "status": "killed"}`
Errors:
- 404: `{"error": "task not found"}`
- 409: `{"error": "task already terminal", "status": "<current>"}`

Side effect: runtime.kill_colony(task_id, killed_by="a2a")

#### GET /a2a/tasks/{task_id}/events -- SSE Stream

Content-Type: text/event-stream
Error: 404 `{"error": "task not found"}` (JSON, not SSE)
Timeout: 300s idle timeout per event

Pattern: snapshot-then-live-tail
- Running tasks: RUN_STARTED -> STATE_SNAPSHOT -> live events -> RUN_FINISHED
- Terminal tasks: RUN_STARTED -> STATE_SNAPSHOT -> RUN_FINISHED (immediate)

### 2.2 Status Envelope (_colony_status_envelope)

```python
{
    "task_id": colony.id,
    "status": colony.status,  # pending|running|completed|failed|killed
    "progress": {
        "round": colony.round_number,
        "max_rounds": colony.max_rounds,
        "convergence": colony.convergence,
    },
    "cost": colony.cost,
    "quality_score": colony.quality_score,
}
```

Conditional failure_context appended for failed/killed:
- Failed: `{"failure_reason": str, "failed_at_round": int}`
- Killed: `{"killed_by": str, "killed_at_round": int}`

### 2.3 Task Classifier (surface/task_classifier.py)

Deterministic team selection (no LLM). Five categories:

| Category            | Keywords                                          | Castes           | Strategy    | Rounds | Budget |
|---------------------|---------------------------------------------------|------------------|-------------|--------|--------|
| code_implementation | implement, write, build, create, code, function,  | coder, reviewer  | stigmergic  | 10     | $2.00  |
|                     | script, program, develop, fix, debug              |                  |             |        |        |
| code_review         | review, audit, check, inspect, evaluate           | reviewer         | sequential  | 5      | $1.00  |
| research            | research, summarize, analyze, explain, compare,   | researcher       | sequential  | 8      | $1.00  |
|                     | investigate, describe                             |                  |             |        |        |
| design              | design, architect, plan, schema, api, structure   | coder, reviewer  | stigmergic  | 10     | $2.00  |
| creative            | haiku, poem, story, essay, translate              | researcher       | sequential  | 3      | $0.50  |

Fallback (no match): coder + reviewer, stigmergic, 10 rounds, $2.00.

Selection order in _select_team():
1. Template tag overlap with description words
2. Keyword classifier (classify_task)
3. Fallback defaults

### 2.4 Task Lifecycle

```
POST /a2a/tasks
  -> spawn_colony() emits ColonySpawned
  -> status = "pending"
  -> start_colony() scheduled as background task
  -> RoundRunner executes rounds
  -> [SUCCESS] ColonyCompleted -> status = "completed"
  -> [FAILURE] ColonyFailed    -> status = "failed"
  -> [CANCEL]  ColonyKilled    -> status = "killed"
```

State constraints:
- GET /result: only succeeds if terminal (409 if pending/running)
- DELETE: only succeeds if non-terminal (409 if already terminal)

### 2.5 SSE Event Payloads

All SSE frames: `{"event": type, "data": json.dumps(payload)}`

| SSE Type             | Payload                                                    |
|----------------------|------------------------------------------------------------|
| RUN_STARTED          | {type, runId, timestamp}                                   |
| RUN_FINISHED         | {type, runId, status (completed/failed/killed/timeout),    |
|                      |  timestamp}                                                |
| STEP_STARTED         | {type, runId, stepId ({id}-r{round}), step, timestamp}     |
| STEP_FINISHED        | {type, runId, stepId, step, timestamp}                     |
| TEXT_MESSAGE_START   | {type, messageId ({id}-{agent}-r{round}), role (caste),   |
|                      |  timestamp}                                                |
| TEXT_MESSAGE_CONTENT | {type, messageId, content (output_summary),                |
|                      |  contentType: "summary"}                                   |
| TEXT_MESSAGE_END     | {type, messageId, timestamp}                               |
| STATE_SNAPSHOT       | {type, snapshot: {full transcript dict}}                   |
| CUSTOM               | {type, name (event class name), runId, value (serialized)} |

### 2.6 Extension Points

1. **Status envelope enrichment** -- next_actions, estimated_completion,
   poll_interval can be added as top-level fields alongside task_id/status.
   Existing clients ignore unknown keys.

2. **Structured errors** -- Error responses currently use `{"error": str}`.
   Can be extended to `{"error": str, "error_code": str, "recovery_hint": str,
   "suggested_action": str}` without breaking existing consumers.

3. **Agent Card extensions** -- /.well-known/agent.json already lists
   capabilities and skills. Can add structured error schema, resource URIs,
   and federation metadata.

4. **SSE CUSTOM events** -- 41 of 48 event types fall through to CUSTOM.
   High-value candidates for dedicated AG-UI mappings: MemoryEntryCreated,
   MemoryConfidenceUpdated, KnowledgeAccessRecorded, WorkflowStepCompleted.

---

## 3. AG-UI Surface (surface/event_translator.py + agui_endpoint.py)

### 3.1 Event Translator (event_translator.py, 188 lines)

#### Function Signatures

```python
def sse_frame(event_type: str, data: dict[str, Any]) -> dict[str, str]
def run_started(colony_id: str) -> dict[str, str]
def run_finished(colony_id: str, event: FormicOSEvent, *, timed_out: bool = False) -> dict[str, str]
def step_started(colony_id: str, round_number: int) -> dict[str, str]
def step_finished(colony_id: str, round_number: int) -> dict[str, str]
def text_message_start(colony_id: str, event: AgentTurnStarted, round_number: int) -> dict[str, str]
def text_message_content(colony_id: str, event: AgentTurnCompleted, round_number: int) -> dict[str, str]
def text_message_end(colony_id: str, event: AgentTurnCompleted, round_number: int) -> dict[str, str]
def state_snapshot(colony_id: str, colony: Any) -> dict[str, str]
def custom_event(colony_id: str, event: FormicOSEvent) -> dict[str, str]
def translate_event(colony_id: str, event: FormicOSEvent, current_round: int) -> Iterator[dict[str, str]]
```

#### AG-UI Tier 1 Event Types (9 total)

```python
AGUI_EVENT_TYPES = frozenset({
    "RUN_STARTED", "RUN_FINISHED",
    "STEP_STARTED", "STEP_FINISHED",
    "TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_END",
    "STATE_SNAPSHOT", "CUSTOM",
})
```

#### Event Mapping Table (All 48 Events)

| # | Internal Event               | AG-UI Type                         | Notes                              |
|---|------------------------------|------------------------------------|------------------------------------|
| 1 | WorkspaceCreated             | CUSTOM                             | Workspace lifecycle                |
| 2 | ThreadCreated                | CUSTOM                             | Thread lifecycle                   |
| 3 | ThreadRenamed                | CUSTOM                             | Thread metadata                    |
| 4 | ColonySpawned                | CUSTOM                             | Before RUN_STARTED                 |
| 5 | ColonyCompleted              | RUN_FINISHED (status="completed")  | Terminal                           |
| 6 | ColonyFailed                 | RUN_FINISHED (status="failed")     | Terminal                           |
| 7 | ColonyKilled                 | RUN_FINISHED (status="killed")     | Terminal                           |
| 8 | RoundStarted                 | STEP_STARTED                       | Direct map                         |
| 9 | PhaseEntered                 | CUSTOM                             | Round phase signal                 |
| 10| AgentTurnStarted             | TEXT_MESSAGE_START                  | Direct map                         |
| 11| AgentTurnCompleted           | TEXT_MESSAGE_CONTENT + _END         | 2 frames                           |
| 12| RoundCompleted               | STEP_FINISHED                      | Caller emits STATE_SNAPSHOT after  |
| 13| MergeCreated                 | CUSTOM                             |                                    |
| 14| MergePruned                  | CUSTOM                             |                                    |
| 15| ContextUpdated               | CUSTOM                             |                                    |
| 16| WorkspaceConfigChanged       | CUSTOM                             |                                    |
| 17| ModelRegistered              | CUSTOM                             |                                    |
| 18| ModelAssignmentChanged       | CUSTOM                             |                                    |
| 19| ApprovalRequested            | CUSTOM                             | Candidate: requires_human=true     |
| 20| ApprovalGranted              | CUSTOM                             |                                    |
| 21| ApprovalDenied               | CUSTOM                             |                                    |
| 22| QueenMessage                 | CUSTOM                             |                                    |
| 23| TokensConsumed               | CUSTOM                             |                                    |
| 24| ColonyTemplateCreated        | CUSTOM                             |                                    |
| 25| ColonyTemplateUsed           | CUSTOM                             |                                    |
| 26| ColonyNamed                  | CUSTOM                             |                                    |
| 27| SkillConfidenceUpdated       | CUSTOM                             |                                    |
| 28| SkillMerged                  | CUSTOM                             |                                    |
| 29| ColonyChatMessage            | CUSTOM                             |                                    |
| 30| CodeExecuted                 | CUSTOM                             |                                    |
| 31| ServiceQuerySent             | CUSTOM                             |                                    |
| 32| ServiceQueryResolved         | CUSTOM                             |                                    |
| 33| ColonyServiceActivated       | CUSTOM                             |                                    |
| 34| KnowledgeEntityCreated       | CUSTOM                             | KG node (Wave 13)                  |
| 35| KnowledgeEdgeCreated         | CUSTOM                             | KG edge (Wave 13)                  |
| 36| KnowledgeEntityMerged        | CUSTOM                             | KG consolidation (Wave 13)         |
| 37| ColonyRedirected             | CUSTOM                             | Service redirect (Wave 21)         |
| 38| MemoryEntryCreated           | CUSTOM                             | Memory extraction (Wave 26)        |
| 39| MemoryEntryStatusChanged     | CUSTOM                             | Memory status (Wave 26)            |
| 40| MemoryExtractionCompleted    | CUSTOM                             | Extraction signal (Wave 26)        |
| 41| KnowledgeAccessRecorded      | CUSTOM                             | Knowledge injection (Wave 28)      |
| 42| ThreadGoalSet                | CUSTOM                             | Thread coordination (Wave 29)      |
| 43| ThreadStatusChanged          | CUSTOM                             | Thread state (Wave 29)             |
| 44| MemoryEntryScopeChanged      | CUSTOM                             | Memory scope change (Wave 29)      |
| 45| DeterministicServiceRegistered| CUSTOM                            | Service registration (Wave 29)     |
| 46| MemoryConfidenceUpdated      | CUSTOM                             | Thompson posteriors (Wave 30)      |
| 47| WorkflowStepDefined          | CUSTOM                             | Workflow scaffolding (Wave 30)     |
| 48| WorkflowStepCompleted        | CUSTOM                             | Step completion (Wave 30)          |

Gap summary: 7 events directly mapped, 41 fall through to CUSTOM.

### 3.2 AG-UI SSE Endpoint (surface/agui_endpoint.py, 149 lines)

Route: POST /ag-ui/runs
Handler: handle_agui_run(request) -> EventSourceResponse | JSONResponse

Request:
```json
{
  "task": "...",               // required
  "castes": [...],             // optional, default [coder, reviewer]
  "workspace_id": "default",   // optional
  "thread_id": "main"          // optional
}
```

Streaming semantics: "summary-at-turn-end" (ADR-035)
- TEXT_MESSAGE_CONTENT carries output_summary (not token-streamed)
- STATE_SNAPSHOT emitted after each RoundCompleted
- No TOOL_CALL_START/END, STATE_DELTA, or token streaming

Stream lifecycle:
1. Emit RUN_STARTED
2. Subscribe to colony event queue
3. For each event (300s timeout):
   - translate_event() -> yield SSE frames
   - If RoundCompleted: also emit STATE_SNAPSHOT
   - If terminal: break
4. On timeout: emit RUN_FINISHED with status="timeout"
5. Unsubscribe from colony queue

Error responses:
- 400: `{"error": "..."}` (invalid request)
- 500: `{"error": "..."}` (spawn failure)

### 3.3 Extension Points

1. **Dedicated AG-UI event types** -- High-value CUSTOM events to promote:
   - MemoryEntryCreated -> KNOWLEDGE_CREATED (extraction visibility)
   - MemoryConfidenceUpdated -> CONFIDENCE_UPDATED (learning visibility)
   - KnowledgeAccessRecorded -> KNOWLEDGE_INJECTED (retrieval visibility)
   - WorkflowStepCompleted -> WORKFLOW_STEP_DONE (orchestration visibility)
   - ApprovalRequested -> APPROVAL_NEEDED (human-in-the-loop signal)

2. **Token streaming** -- Currently summary-at-turn-end. Adding
   TEXT_MESSAGE_CONTENT with contentType="delta" requires runner granularity
   changes (engine layer).

3. **CUSTOM event filtering** -- Clients currently receive all 41 CUSTOM
   events. A category filter query param on /ag-ui/runs and /a2a/events
   would let clients opt in to specific CUSTOM event names.

---

## 4. WebSocket Surface (surface/ws_handler.py)

### 4.1 Connection Lifecycle

Route: WS /ws
Handler: ws_endpoint(ws, ws_manager)

1. Accept WebSocket connection
2. Send initial state snapshot (full workspace/colony/config state)
3. Loop: receive JSON messages, dispatch commands or subscriptions
4. On disconnect: unsubscribe_all(ws)

### 4.2 Subscription Model

**Dual-tier architecture:**

Tier 1 -- Workspace-scoped (broadcast fan-out):
- subscribe(ws, workspace_id) -- adds client to workspace subscriber set
- unsubscribe(ws, workspace_id)
- Events matching workspace prefix broadcast to all subscribers
- Payload: `{"type": "event", "event": {serialized FormicOS event}}`

Tier 2 -- Colony-scoped (queue-based, for SSE attach):
- subscribe_colony(colony_id) -> asyncio.Queue (maxsize=1000)
- unsubscribe_colony(colony_id, queue)
- Multiple consumers per colony (AG-UI + A2A can attach simultaneously)
- Used by /ag-ui/runs and /a2a/tasks/{id}/events

### 4.3 Outbound Message Types

| Type    | Shape                                        | When Sent                    |
|---------|----------------------------------------------|------------------------------|
| state   | {"type": "state", "state": {snapshot}}       | On connect, after commands   |
| event   | {"type": "event", "event": {serialized}}     | On every FormicOS event      |
| error   | {"error": str}                               | On invalid input             |

State snapshot includes: workspace threads, colonies, costs, provider health,
local endpoint probes (llama.cpp /health + /props + VRAM), skill stats.

### 4.4 Inbound Commands (15 types)

Defined in surface/commands.py (285 lines).

Command format from client:
```json
{"action": str, "workspaceId": str, "payload": {...}}
```

| Command          | Key Payload Fields                       | Response                        |
|------------------|------------------------------------------|---------------------------------|
| create_thread    | threadName -> threadId                   | {"threadId": str}               |
| spawn_colony     | templateId, castes, task, threadId,      | {"colonyId": str,               |
|                  | strategy, maxRounds, budgetLimit,        |  "templateId": str}             |
|                  | modelAssignments                         |                                 |
| kill_colony      | colonyId, killedBy                       | {"status": "killed"}            |
| send_queen_message| threadId, content                       | {"status": "sent"}              |
| create_merge     | fromColony, toColony, createdBy          | {"edgeId": str}                 |
| prune_merge      | edgeId                                   | {"status": "pruned"}            |
| broadcast        | fromColony, threadId                     | {"edges": [str, ...]}           |
| approve          | requestId                                | {"status": "approved"}          |
| deny             | requestId                                | {"status": "denied"}            |
| update_config    | field, value                             | {"status": "updated"}           |
| chat_colony      | colonyId, message                        | {"status": "sent"}              |
| activate_service | colonyId, serviceType                    | {"status": "activated", ...}    |
| rename_colony    | colonyId, name                           | {"status": "renamed"}           |
| rename_thread    | threadId, name                           | {"status": "renamed"}           |
| save_queen_note  | threadId, content                        | {"status": "saved",             |
|                  |                                          |  "noteCount": int}              |

Command errors:
- Missing field: `{"error": "missing required field: <key>"}`
- Unknown action: `{"error": "unknown action '<action>'"}`
- Exception: `{"error": "command '<action>' failed unexpectedly"}`

### 4.5 Relationship to AG-UI Translator

WebSocket and AG-UI are independent paths:
- WebSocket: sends raw serialized FormicOS events (no translation)
- AG-UI: uses event_translator.py to map to Tier 1 AG-UI event types
- Both use WebSocketManager for subscription/fan-out infrastructure
- Colony-scoped queues serve both AG-UI and A2A SSE attach

### 4.6 Extension Points

1. **Command-response enrichment** -- Commands return result dicts. Adding
   suggested_next (array of follow-up action names) to responses would guide
   frontend flows without breaking existing clients that ignore unknown keys.

2. **Structured errors** -- Current `{"error": str}` format can be extended
   with error_code and recovery_hint fields.

3. **Event filtering** -- Currently all events broadcast to workspace
   subscribers. A subscription filter (event type allowlist) would reduce
   frontend noise. Client would send:
   `{"action": "subscribe", "workspaceId": str, "filter": ["ColonyCompleted", ...]}`

4. **State diff** -- Currently full state snapshot sent after every command.
   A delta/patch mechanism would reduce payload size.

---

## 5. HTTP REST Surface

### 5.1 Route Organization

Routes registered in app.py create_app() (lines 638-646):
```python
routes.extend(health_routes(**shared_deps))
routes.extend(api_routes(**shared_deps))
routes.extend(colony_io_routes(**shared_deps))
routes.extend(protocol_routes(**shared_deps))
routes.extend(a2a_routes(**shared_deps))
routes.extend(memory_routes(**shared_deps))
routes.extend(knowledge_routes(**shared_deps))
routes.append(WebSocketRoute("/ws", websocket_handler))
```

Static frontend served from / if dist/ exists.

### 5.2 Health and Diagnostics (routes/health.py)

**GET /health**

Response (200):
```json
{
  "status": "ok",
  "last_seq": int,
  "bootstrapped": bool,
  "workspaces": int,
  "threads": int,
  "colonies": int,
  "memory_entries": int,
  "memory_extractions": int
}
```

**GET /debug/inventory**

Response (200): CapabilityRegistry.to_dict() (ADR-036)
Contains: event type names, MCP tools, Queen tools, AG-UI events, protocols,
castes list.

### 5.3 API Routes (routes/api.py)

| Method | Path                           | Purpose                    | Response (200)                   | Errors            |
|--------|--------------------------------|----------------------------|----------------------------------|--------------------|
| POST   | /api/v1/suggest-team           | Suggest caste team         | {objective, castes}              | 400                |
| GET    | /api/v1/templates              | List colony templates      | [ColonyTemplate, ...]            | --                 |
| POST   | /api/v1/templates              | Create template            | ColonyTemplate (201)             | 400                |
| GET    | /api/v1/templates/{id}         | Get template detail        | ColonyTemplate                   | 404                |
| GET    | /api/v1/castes                 | List caste recipes         | {caste_id: CasteRecipe, ...}    | --                 |
| PUT    | /api/v1/castes/{id}            | Create/update caste        | CasteRecipe                      | 400, 500           |
| PATCH  | /api/v1/models/{address:path}  | Update model policy        | ModelRecord                      | 400, 404           |
| GET    | /api/v1/knowledge-graph        | Get KG nodes and edges     | {nodes, edges, stats}            | 500 (fallback)     |
| GET    | /api/v1/retrieval-diagnostics  | Retrieval pipeline stats   | {timing, counts, embedding, ...} | --                 |

### 5.4 Colony I/O Routes (routes/colony_io.py)

| Method | Path                                        | Purpose                  | Constraints                   |
|--------|---------------------------------------------|--------------------------|-------------------------------|
| GET    | /api/v1/colonies/{id}/files                 | List uploaded files      | --                            |
| POST   | /api/v1/colonies/{id}/files                 | Upload files             | 10 MB/file, 50 MB/colony,    |
|        |                                             |                          | .txt/.md/.py/.json/.yaml/.csv |
| GET    | /api/v1/colonies/{id}/export                | Export as ZIP            | items= filter param           |
| GET    | /api/v1/colonies/{id}/transcript            | Full transcript          | --                            |
| GET    | /api/v1/colonies/{id}/artifacts             | List artifacts           | 500-char preview              |
| GET    | /api/v1/colonies/{id}/artifacts/{aid}       | Full artifact detail     | --                            |
| GET    | /api/v1/workspaces/{id}/files               | List workspace files     | --                            |
| GET    | /api/v1/workspaces/{id}/files/{name}        | Preview file             | 20,000-char max               |
| POST   | /api/v1/workspaces/{id}/files               | Upload workspace files   | Same constraints as colony    |
| POST   | /api/v1/workspaces/{id}/ingest              | Upload + embed to Qdrant | 1000-char chunks, 200 overlap |

### 5.5 Unified Knowledge API (routes/knowledge_api.py, Wave 27)

Federated over institutional memory + skill bank.

| Method | Path                               | Purpose             | Key Params                         | Errors       |
|--------|------------------------------------|--------------------|-------------------------------------|--------------|
| GET    | /api/v1/knowledge                  | List entries        | source, type, workspace, limit     | 400, 503     |
| GET    | /api/v1/knowledge/search           | Hybrid search       | q (required), source, type,        | 400, 503     |
|        |                                    |                    | workspace, thread, limit            |              |
| GET    | /api/v1/knowledge/{id}             | Get detail          | --                                  | 404, 503     |
| POST   | /api/v1/knowledge/{id}/promote     | Promote scope       | --                                  | 400, 404, 503|
| POST   | /api/v1/services/query             | Trigger maintenance | service_type, query                 | 400,404,503,504|

Promote emits MemoryEntryScopeChanged event.
Services: dedup, stale_sweep, contradiction, confidence_reset (30s timeout).

### 5.6 Deprecated Memory API (routes/memory_api.py, Wave 26)

All responses include `"_deprecated": "Use /api/v1/knowledge... instead."`.

| Method | Path                    | Purpose        | Replacement                    |
|--------|-------------------------|----------------|--------------------------------|
| GET    | /api/v1/memory          | List entries   | /api/v1/knowledge              |
| GET    | /api/v1/memory/{id}     | Get detail     | /api/v1/knowledge/{id}         |
| GET    | /api/v1/memory/search   | Search entries | /api/v1/knowledge/search       |

### 5.7 Protocol Routes (routes/protocols.py)

| Method | Path                       | Purpose              |
|--------|----------------------------|----------------------|
| GET    | /.well-known/agent.json    | Agent discovery card |
| POST   | /ag-ui/runs                | AG-UI SSE endpoint   |
| Mount  | /mcp                       | FastMCP HTTP         |

Agent Card response (200):
```json
{
  "name": "FormicOS",
  "description": "Stigmergic multi-agent colony framework...",
  "url": "<base_url>",
  "version": "0.21.0",
  "capabilities": {"streaming": true, "pushNotifications": false},
  "protocols": {
    "mcp": "/mcp",
    "agui": "/ag-ui/runs",
    "a2a": {
      "endpoint": "/a2a/tasks",
      "mode": "submit/poll/attach/result",
      "streaming": true,
      "events_endpoint": "/a2a/tasks/{task_id}/events"
    }
  },
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "skills": [{id, name, description, tags, examples}]
}
```

### 5.8 Shared Dependencies

All route factories receive shared_deps:
```python
{
    "runtime": Runtime,
    "projections": ProjectionStore,
    "settings": SystemSettings,
    "castes": CasteRecipeSet | None,
    "castes_path": str | Path,
    "config_path": str | Path,
    "data_dir": Path,
    "vector_store": QdrantVectorPort | None,
    "kg_adapter": KnowledgeGraphAdapter | None,
    "embed_client": Qwen3Embedder | None,
    "skill_collection": str,
    "ws_manager": WebSocketManager,
    "registry": CapabilityRegistry,
    "mcp_http": Starlette,
    "memory_store": MemoryStore | None,
    "knowledge_catalog": KnowledgeCatalog,
}
```

### 5.9 Extension Points

1. **REST structured errors** -- All REST errors use `{"error": str}`. Can
   extend to StructuredError schema (see Section 8) at each endpoint.

2. **Knowledge event webhooks** -- POST /api/v1/knowledge/{id}/promote is
   the only mutating knowledge endpoint. Adding webhook/callback support for
   knowledge lifecycle changes would enable external integrations.

3. **Pagination** -- List endpoints use limit param but no cursor/offset.
   Adding cursor-based pagination enables large result sets.

4. **Batch operations** -- No batch endpoints exist. POST /api/v1/knowledge/batch
   for bulk status changes, confidence resets, etc.

---

## 6. Error Handling Cross-Reference

### 6.1 Current Error Formats by Surface

| Surface   | Format                                 | HTTP Status Codes Used      |
|-----------|----------------------------------------|-----------------------------|
| MCP       | `{"error": str}` dict return           | N/A (tool return)           |
| A2A       | `{"error": str}` JSON response         | 400, 404, 409               |
| AG-UI     | `{"error": str}` JSON response         | 400, 500                    |
| WebSocket | `{"error": str}` JSON frame            | N/A (WS frame)              |
| REST      | `{"error": str}` JSON response         | 400, 404, 409, 500, 503, 504|

### 6.2 Error Inventory with Structured Error Mapping

| Surface | Endpoint/Tool        | Current Error                              | Status | Proposed error_code         | recovery_hint                                | suggested_action          | requires_human |
|---------|---------------------|--------------------------------------------|--------|-----------------------------|----------------------------------------------|---------------------------|----------------|
| MCP     | get_status          | workspace not found                        | --     | WORKSPACE_NOT_FOUND         | Check workspace ID with list_workspaces      | list_workspaces           | false          |
| MCP     | get_template_detail | template not found                         | --     | TEMPLATE_NOT_FOUND          | Check template ID with list_templates        | list_templates            | false          |
| MCP     | query_service       | colony manager not available               | --     | SERVICE_UNAVAILABLE         | Colony manager not started; retry after init | --                        | false          |
| MCP     | query_service       | ValueError                                 | --     | INVALID_SERVICE_TYPE        | Check valid service types                    | --                        | false          |
| MCP     | query_service       | TimeoutError                               | --     | SERVICE_TIMEOUT             | Service took too long; retry with longer timeout | query_service (timeout+) | false          |
| MCP     | chat_colony         | colony not found                           | --     | COLONY_NOT_FOUND            | Colony may have completed or been killed      | get_status                | false          |
| MCP     | activate_service    | colony manager not available               | --     | SERVICE_UNAVAILABLE         | Colony manager not started                   | --                        | false          |
| MCP     | activate_service    | ValueError                                 | --     | INVALID_SERVICE_TYPE        | Check valid service types                    | --                        | false          |
| A2A     | POST /tasks         | invalid JSON body                          | 400    | INVALID_REQUEST             | Send valid JSON with description field       | --                        | false          |
| A2A     | POST /tasks         | description is required                    | 400    | MISSING_FIELD               | Provide non-empty description string         | --                        | false          |
| A2A     | GET /tasks          | limit must be an integer                   | 400    | INVALID_PARAMETER           | Provide integer limit in [1, 100]            | --                        | false          |
| A2A     | GET /tasks/{id}     | task not found                             | 404    | TASK_NOT_FOUND              | Task ID may be wrong or colony never existed | GET /a2a/tasks            | false          |
| A2A     | GET /tasks/{id}/result | task not found                          | 404    | TASK_NOT_FOUND              | Task ID may be wrong                         | GET /a2a/tasks            | false          |
| A2A     | GET /tasks/{id}/result | task still running                      | 409    | TASK_NOT_TERMINAL           | Poll status or attach to event stream        | GET /tasks/{id}/events    | false          |
| A2A     | DELETE /tasks/{id}  | task not found                             | 404    | TASK_NOT_FOUND              | Task may never have existed                  | GET /a2a/tasks            | false          |
| A2A     | DELETE /tasks/{id}  | task already terminal                      | 409    | TASK_ALREADY_TERMINAL       | Task finished; retrieve result instead       | GET /tasks/{id}/result    | false          |
| REST    | POST suggest-team   | objective is required                      | 400    | MISSING_FIELD               | Provide objective string                     | --                        | false          |
| REST    | GET templates/{id}  | template not found                         | 404    | TEMPLATE_NOT_FOUND          | Check ID with GET /templates                 | GET /api/v1/templates     | false          |
| REST    | PUT castes/{id}     | invalid JSON body                          | 400    | INVALID_REQUEST             | Send valid CasteRecipe JSON                  | --                        | false          |
| REST    | PUT castes/{id}     | no caste recipes loaded                    | 500    | SERVICE_NOT_READY           | Caste recipes file not loaded at startup     | --                        | true           |
| REST    | PATCH models/{addr} | model not found in registry                | 404    | MODEL_NOT_FOUND             | Check address with GET /health inventory     | GET /debug/inventory      | false          |
| REST    | PATCH models/{addr} | no editable fields provided                | 400    | MISSING_FIELD               | Provide max_output_tokens, time_multiplier,  | --                        | false          |
|         |                     |                                            |        |                             | or tool_call_multiplier                      |                           |                |
| REST    | knowledge/search    | query parameter 'q' required               | 400    | MISSING_FIELD               | Provide search query via ?q= parameter       | --                        | false          |
| REST    | knowledge/*         | knowledge catalog not available             | 503    | SERVICE_UNAVAILABLE         | Knowledge catalog not initialized; check     | GET /health               | false          |
|         |                     |                                            |        |                             | vector store and embedder availability       |                           |                |
| REST    | knowledge/promote   | already workspace-wide                     | 400    | INVALID_STATE               | Entry already has workspace scope            | --                        | false          |
| REST    | services/query      | service_type and query required             | 400    | MISSING_FIELD               | Provide both service_type and query          | --                        | false          |
| REST    | services/query      | timeout                                    | 504    | SERVICE_TIMEOUT             | Service took >30s; try smaller scope         | --                        | false          |
| REST    | colony files        | colony not found                           | 404    | COLONY_NOT_FOUND            | Colony ID may be wrong                       | GET /health               | false          |
| REST    | workspace files     | workspace not found                        | 404    | WORKSPACE_NOT_FOUND         | Workspace ID may be wrong                    | --                        | false          |
| REST    | workspace/ingest    | vector store not available                 | 503    | SERVICE_UNAVAILABLE         | Qdrant not configured or unreachable         | GET /health               | true           |
| WS      | command dispatch     | missing required field: {key}             | --     | MISSING_FIELD               | Include {key} in payload                     | --                        | false          |
| WS      | command dispatch     | unknown action '{action}'                 | --     | UNKNOWN_COMMAND             | Check available commands                     | --                        | false          |
| WS      | command dispatch     | command failed unexpectedly               | --     | INTERNAL_ERROR              | Unexpected error; check server logs          | --                        | true           |

### 6.3 High-Value Recovery Guidance Candidates

These errors benefit most from structured guidance because they change agent
behavior:

1. **"task still running" (409)** -- Add retry_after_s (estimated from
   round progress and max_rounds) and poll_url fields.

2. **"knowledge catalog not available" (503)** -- Add dependency_status
   showing which subsystem is down (Qdrant? embedder? both?).

3. **ApprovalRequested events** -- Not an error but a blocking state. AG-UI
   CUSTOM event should carry requires_human=true, approval_type, detail.

4. **"colony not found"** -- Distinguish never-existed vs. was-killed vs.
   completed-and-archived. The projection has enough data to disambiguate.

5. **Service timeouts** -- Add retry_after_s and scope_hint (suggest
   narrower query).

---

## 7. Response Enrichment Extension Points

### 7.1 MCP Tool Returns

Current: All tools return dict. Adding keys to existing dicts is
backward-compatible for MCP clients.

Pattern:
```python
# Current
return {"colony_id": cid}

# Enriched
return {
    "colony_id": cid,
    "_next_actions": ["get_status", "chat_colony"],
    "_context": {"thread_id": tid, "workspace_id": wid},
}
```

Considerations:
- FastMCP serializes dict returns to JSON content blocks
- Underscore-prefixed keys signal metadata without polluting the primary response
- MCP resource subscriptions require ResourceUpdatedNotification for mutating
  tools that change observable state

### 7.2 A2A Responses

Current: Top-level JSON dicts. Adding fields is backward-compatible.

Pattern for status envelope:
```python
{
    "task_id": "...",
    "status": "running",
    "progress": {...},
    "cost": 0.42,
    "quality_score": 0.0,
    # New enrichment fields:
    "next_actions": ["poll", "attach", "cancel"],
    "poll_interval_s": 5,
    "estimated_completion_round": 8,
}
```

Pattern for error responses:
```python
{
    "error": "task still running",
    "error_code": "TASK_NOT_TERMINAL",
    "status": "running",
    "recovery_hint": "Poll status or attach to event stream",
    "suggested_action": "GET /a2a/tasks/{id}/events",
    "retry_after_s": 10,
}
```

### 7.3 WebSocket Commands

Current: Command responses are result dicts. After sending result, a full
state snapshot follows.

Pattern:
```python
# Current command result
{"colonyId": "colony-abc123", "templateId": ""}

# Enriched
{
    "colonyId": "colony-abc123",
    "templateId": "",
    "suggested_next": ["chat_colony", "send_queen_message"],
}
```

### 7.4 AG-UI Events

CUSTOM events already carry arbitrary payloads via the value field. Domain-
specific enrichment can be added to CUSTOM event values without protocol
changes:

```python
{
    "type": "CUSTOM",
    "name": "ApprovalRequested",
    "runId": "colony-abc",
    "value": {
        ...event fields...,
        "requires_human": true,
        "suggested_action": "approve or deny via MCP tool",
    }
}
```

For promoted events (future dedicated AG-UI types), enrichment lives in the
event payload directly.

---

## 8. Cross-Surface Consistency

### 8.1 StructuredError Model

Proposed unified model for all surfaces:

```python
class StructuredError:
    error: str              # Human-readable message (existing field)
    error_code: str         # Machine-readable code (SCREAMING_SNAKE)
    recovery_hint: str      # What to do about it
    suggested_action: str   # Specific endpoint/tool to call next
    retry_after_s: int      # Seconds to wait before retry (0 = don't retry)
    requires_human: bool    # Whether human intervention is needed
```

Surface-specific serialization:

| Surface   | Serialization                                            |
|-----------|----------------------------------------------------------|
| MCP       | Dict return with all fields                              |
| A2A       | JSON response body with all fields + HTTP status         |
| AG-UI     | Not applicable (errors are JSON responses, not SSE)      |
| WebSocket | JSON frame with all fields                               |
| REST      | JSON response body with all fields + HTTP status         |

### 8.2 Error Code Naming Conventions

Format: SCREAMING_SNAKE_CASE, max 30 chars.

Categories:
- MISSING_FIELD -- required parameter absent
- INVALID_REQUEST -- malformed request body
- INVALID_PARAMETER -- bad query parameter value
- INVALID_STATE -- operation not valid in current state
- *_NOT_FOUND -- resource does not exist (WORKSPACE_, COLONY_, TASK_, etc.)
- TASK_NOT_TERMINAL -- task still running
- TASK_ALREADY_TERMINAL -- task already finished
- SERVICE_UNAVAILABLE -- dependency not ready
- SERVICE_TIMEOUT -- operation exceeded time limit
- SERVICE_NOT_READY -- system component not initialized
- UNKNOWN_COMMAND -- unrecognized WebSocket command
- INTERNAL_ERROR -- unexpected server error

### 8.3 Response Envelope Conventions

All surfaces should converge on:
- Primary data at top level (no wrapper object)
- Metadata fields prefixed with underscore in MCP returns
- Error responses always include at minimum: error (str) + error_code (str)
- List responses include total count field
- Mutating responses include the created/modified resource ID

### 8.4 Resource URI Naming (MCP)

Proposed convention for MCP resource URIs:

```
formicos://workspaces                          # list
formicos://workspaces/{id}                     # detail
formicos://workspaces/{id}/threads             # list
formicos://workspaces/{id}/threads/{id}        # detail
formicos://colonies/{id}                       # detail
formicos://colonies/{id}/transcript            # read-only
formicos://knowledge/{id}                      # detail
formicos://knowledge?workspace={id}&q={query}  # search
formicos://maintenance/status                  # singleton
```

### 8.5 Event Type Coverage Matrix

Summary of which events each surface handles natively vs. passthrough:

| Event Category        | Count | MCP Emitters    | AG-UI Native | AG-UI CUSTOM | WS (raw) |
|-----------------------|-------|-----------------|--------------|--------------|----------|
| Colony lifecycle      | 5     | spawn, kill     | 3 (terminal) | 2            | 5        |
| Round lifecycle       | 4     | --              | 4            | 0            | 4        |
| Agent lifecycle       | 2     | --              | 2 (3 frames) | 0            | 2        |
| Knowledge/Memory      | 8     | --              | 0            | 8            | 8        |
| Knowledge Graph       | 3     | --              | 0            | 3            | 3        |
| Approval              | 3     | approve, deny   | 0            | 3            | 3        |
| Thread/Workflow       | 6     | --              | 0            | 6            | 6        |
| Merge                 | 2     | create, prune   | 0            | 2            | 2        |
| Config/Model          | 3     | --              | 0            | 3            | 3        |
| Service               | 4     | activate, query | 0            | 4            | 4        |
| Other (chat, code...) | 8     | chat_colony     | 0            | 8            | 8        |
| **Total**             | **48**| **10 emitters** | **9 native** | **39 custom**| **48**   |

### 8.6 Projection Access Patterns (Summary)

All external surfaces ultimately read from ProjectionStore, which is rebuilt
deterministically from event replay. No surface has a separate data store.

| Projection              | MCP | A2A | AG-UI | WS  | REST |
|-------------------------|-----|-----|-------|-----|------|
| workspaces              | Yes | --  | --    | Yes | Yes  |
| threads                 | Yes | --  | --    | Yes | Yes  |
| colonies                | Yes | Yes | Yes*  | Yes | Yes  |
| memory_entries          | --  | --  | --    | --  | Yes  |
| merges                  | --  | --  | --    | Yes | --   |
| approvals               | --  | --  | --    | Yes | --   |
| knowledge_catalog       | --  | --  | --    | --  | Yes  |
| template_manager        | Yes | --  | --    | --  | Yes  |

*AG-UI accesses colonies via build_transcript() for STATE_SNAPSHOT.

---

End of document.
