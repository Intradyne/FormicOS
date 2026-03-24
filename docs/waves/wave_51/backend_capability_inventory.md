# Wave 51: Backend Capability Inventory

Audit date: 2026-03-20. Source: live codebase inspection.

---

## 1. WebSocket Commands (15 total)

All commands route through `ws_handler.py` → `commands.py` → `runtime.emit_and_broadcast()`.

| # | Command | Handler (commands.py) | Required Inputs | Events Emitted | Source of Truth | Status |
|---|---------|----------------------|-----------------|----------------|-----------------|--------|
| 1 | `create_thread` | `_handle_create_thread` L232 | workspace_id, name | ThreadCreated | Event | Shipped |
| 2 | `spawn_colony` | `_handle_spawn_colony` L51 | workspace_id, threadId, task, castes/team (or templateId) | ColonySpawned, ColonyTemplateUsed (if template) | Event | Shipped |
| 3 | `kill_colony` | `_handle_kill_colony` L118 | colonyId | ColonyKilled | Event | Shipped |
| 4 | `send_queen_message` | `_handle_send_queen_message` L125 | threadId, content | QueenMessage | Event | Shipped |
| 5 | `create_merge` | `_handle_create_merge` L135 | fromColony, toColony | MergeCreated | Event | Shipped |
| 6 | `prune_merge` | `_handle_prune_merge` L145 | edgeId | MergePruned | Event | Shipped |
| 7 | `broadcast` | `_handle_broadcast` L152 | fromColony, threadId | Multiple MergeCreated | Event | Shipped |
| 8 | `approve` | `_handle_approve` L165 | requestId | ApprovalGranted | Event | Shipped |
| 9 | `deny` | `_handle_deny` L172 | requestId | ApprovalDenied | Event | Shipped |
| 10 | `update_config` | `_handle_update_config` L179 | field, value | ModelAssignmentChanged or WorkspaceConfigChanged | Event | Shipped |
| 11 | `chat_colony` | `_handle_chat_colony` L186 | colonyId, message | ColonyChatMessage | Event + runtime injection | Shipped |
| 12 | `activate_service` | `_handle_activate_service` L214 | colonyId, serviceType | ColonyServiceActivated | Event | Shipped |
| 13 | `rename_colony` | `_handle_rename_colony` L239 | colonyId, name | ColonyNamed | Event | Shipped |
| 14 | `rename_thread` | `_handle_rename_thread` L259 | threadId, name | ThreadRenamed | Event | Shipped |
| 15 | `save_queen_note` | `_handle_save_queen_note` L268 | threadId, content | None | Runtime-only (Queen object) | Shipped, NOT replay-safe |

**Built-in WS actions** (non-command, no events):
- `subscribe` — Subscribe client to workspace events, sends state snapshot
- `unsubscribe` — Remove client subscription

**Replay safety**: 14/15 commands are replay-safe (event-sourced). `save_queen_note` stores notes in Queen object memory only.

---

## 2. REST API Routes (60+ endpoints)

### 2.1 Health & Debug (`routes/health.py`)

| Method | Path | Returns | Source of Truth | Status |
|--------|------|---------|-----------------|--------|
| GET | `/health` | Health status + projection counters | ProjectionStore (live) | Shipped |
| GET | `/debug/inventory` | CapabilityRegistry dump | Runtime | Shipped |

### 2.2 Core API (`routes/api.py`)

#### Team & Colony Preview

| Method | Path | Inputs | Returns | Source of Truth | Status |
|--------|------|--------|---------|-----------------|--------|
| POST | `/api/v1/suggest-team` | objective (body) | castes recommendation | LLM (runtime) | Shipped |
| POST | `/api/v1/preview-colony` | task, castes, strategy, max_rounds, budget_limit, fast_path, target_files | Preview metadata (no dispatch) | Pure function | Wave 48 |

#### Templates

| Method | Path | Inputs | Returns | Source of Truth | Status |
|--------|------|--------|---------|-----------------|--------|
| GET | `/api/v1/templates` | — | All templates | Template manager (filesystem) | Shipped |
| POST | `/api/v1/templates` | name, castes, description, etc. | Created template (201) | Template manager | Shipped |
| GET | `/api/v1/templates/{template_id}` | template_id | Template detail | Template manager | Shipped |
| GET | `/api/v1/workspaces/{workspace_id}/templates` | workspace_id | Operator + learned templates | Projections + templates | Wave 50 |

#### Caste Recipes

| Method | Path | Inputs | Returns | Source of Truth | Status |
|--------|------|--------|---------|-----------------|--------|
| GET | `/api/v1/castes` | — | All caste recipes | YAML config | Shipped |
| PUT | `/api/v1/castes/{caste_id}` | Full CasteRecipe body | Upserted recipe | YAML config | Shipped |

#### Model Registry

| Method | Path | Inputs | Returns | Source of Truth | Status |
|--------|------|--------|---------|-----------------|--------|
| PATCH | `/api/v1/models/{address}` | max_output_tokens, time_multiplier, tool_call_multiplier | Updated model | SystemSettings | Shipped |

#### Knowledge & Diagnostics

| Method | Path | Inputs | Returns | Source of Truth | Status |
|--------|------|--------|---------|-----------------|--------|
| GET | `/api/v1/knowledge-graph` | workspace_id (query, optional) | nodes, edges, stats | KG adapter (SQLite) | Shipped |
| GET | `/api/v1/retrieval-diagnostics` | — | Timing, counts, embedding info | Projections + Vector store | Shipped |

#### Briefing & Proactive Intelligence

| Method | Path | Inputs | Returns | Source of Truth | Status |
|--------|------|--------|---------|-----------------|--------|
| GET | `/api/v1/workspaces/{ws}/briefing` | workspace_id | 14-rule briefing | proactive_intelligence | Shipped |
| GET | `/api/v1/workspaces/{ws}/config-recommendations` | workspace_id | Config recommendations | proactive_intelligence | Wave 39 |
| GET | `/api/v1/workspaces/{ws}/config-overrides` | workspace_id | Override history | OperatorOverlays | Wave 39 |
| POST | `/api/v1/workspaces/{ws}/config-overrides` | dimension, original, overridden, reason, actor | recorded (201) | ConfigSuggestionOverridden event | Wave 39 |
| POST | `/api/v1/workspaces/{ws}/dismiss-autonomy` | category | dismissed | OperatorOverlays (memory-only) | Wave 39 |

#### Colony Outcomes & Escalation

| Method | Path | Inputs | Returns | Source of Truth | Status |
|--------|------|--------|---------|-----------------|--------|
| GET | `/api/v1/workspaces/{ws}/outcomes` | period (24h/7d/30d) | Summary + outcomes | ColonyOutcome projections | Shipped |
| GET | `/api/v1/workspaces/{ws}/escalation-matrix` | — | Escalation outcome matrix | ColonyOutcome | Wave 38 |

#### Demo, Audit, Timeline

| Method | Path | Inputs | Returns | Source of Truth | Status |
|--------|------|--------|---------|-----------------|--------|
| POST | `/api/v1/workspaces/create-demo` | — | workspace_id, entries_seeded (201) | Events | Wave 36 |
| GET | `/api/v1/colonies/{id}/audit` | colony_id | Structured audit view | Projection read-model | Wave 39 |
| GET | `/api/v1/workspaces/{ws}/threads/{t}/timeline` | limit (max 200) | Chronological timeline | Projection read-model | Wave 48 |

#### Forager

| Method | Path | Inputs | Returns | Source of Truth | Status |
|--------|------|--------|---------|-----------------|--------|
| POST | `/api/v1/workspaces/{ws}/forager/trigger` | topic, gap_description, domains, max_results | dispatched (202) | ForageRequested event | Wave 46 |
| POST | `/api/v1/workspaces/{ws}/forager/domain-override` | domain, action, actor, reason | ok | ForagerDomainOverride event | Wave 46 |
| GET | `/api/v1/workspaces/{ws}/forager/cycles` | limit (max 200) | Recent forage cycles | Projections | Wave 46 |
| GET | `/api/v1/workspaces/{ws}/forager/domains` | — | Domain strategies + overrides | Projections | Wave 46 |

### 2.3 Knowledge API (`routes/knowledge_api.py`)

| Method | Path | Inputs | Returns | Source of Truth | Status |
|--------|------|--------|---------|-----------------|--------|
| GET | `/api/v1/knowledge` | source, type, workspace, scope, sub_type, limit | items, total | KnowledgeCatalog | Wave 27 |
| GET | `/api/v1/knowledge/search` | q, source, type, workspace, thread, scope, limit | results, total | KnowledgeCatalog | Wave 27 |
| GET | `/api/v1/knowledge/{item_id}` | item_id | Full entry | KnowledgeCatalog | Wave 27 |
| POST | `/api/v1/knowledge/{item_id}/promote` | target_scope (workspace/global) | promoted, scope | MemoryEntryScopeChanged event | Wave 29/50 |
| GET | `/api/v1/knowledge/graph/{entity_id}/temporal` | entity_id, workspace | Temporal edges | KG adapter | Wave 38 |
| POST | `/api/v1/services/query` | service_type, query | result | ServiceRouter | Wave 29 |
| POST | `/api/v1/knowledge/{item_id}/action` | action (pin/unpin/mute/unmute/invalidate/reinstate), actor, reason, workspace_id | ok | KnowledgeEntryOperatorAction event | Wave 39 |
| POST | `/api/v1/knowledge/{item_id}/annotate` | annotation_text, tag, actor, workspace_id | ok | KnowledgeEntryAnnotated event | Wave 39 |
| GET | `/api/v1/knowledge/{item_id}/annotations` | item_id | Annotation list | OperatorOverlays | Wave 39 |
| GET | `/api/v1/knowledge/{item_id}/overlay` | item_id | Pin/mute/invalidate status | OperatorOverlays | Wave 39 |
| POST | `/api/v1/knowledge/config-override` | workspace_id, suggestion_category, original_config, overridden_config, actor, reason | ok | ConfigSuggestionOverridden event | Wave 39 |

### 2.4 Memory API — DEPRECATED (`routes/memory_api.py`)

| Method | Path | Status |
|--------|------|--------|
| GET | `/api/v1/memory` | Deprecated — returns deprecation warning, proxies to projections |
| GET | `/api/v1/memory/search` | Deprecated — proxies to MemoryStore |
| GET | `/api/v1/memory/{entry_id}` | Deprecated — proxies to projections |

### 2.5 Colony I/O (`routes/colony_io.py`)

| Method | Path | Inputs | Returns | Source of Truth | Status |
|--------|------|--------|---------|-----------------|--------|
| GET | `/api/v1/colonies/{id}/files` | colony_id | File list | Filesystem | Shipped |
| POST | `/api/v1/colonies/{id}/files` | files (multipart) | uploaded list | Filesystem | Shipped |
| GET | `/api/v1/colonies/{id}/transcript` | colony_id | Full transcript | Projection + redaction | Shipped |
| GET | `/api/v1/colonies/{id}/artifacts` | colony_id | Artifact previews (500 char) | Projection | Wave 25.5 |
| GET | `/api/v1/colonies/{id}/artifacts/{aid}` | colony_id, artifact_id | Full artifact | Projection | Wave 25.5 |
| GET | `/api/v1/colonies/{id}/export` | items query | ZIP file | Filesystem + projections | Shipped |
| GET | `/api/v1/workspaces/{ws}/files` | workspace_id | File list | Filesystem | Shipped |
| GET | `/api/v1/workspaces/{ws}/files/{name}` | workspace_id, file_name | File preview (20k chars) | Filesystem | Shipped |
| POST | `/api/v1/workspaces/{ws}/files` | files (multipart) | uploaded list | Filesystem | Shipped |
| POST | `/api/v1/workspaces/{ws}/ingest` | files (multipart) | ingested with chunk counts | Filesystem + Vector store | Wave 22 |

### 2.6 A2A Task Lifecycle (`routes/a2a.py`)

| Method | Path | Inputs | Returns | Source of Truth | Status |
|--------|------|--------|---------|-----------------|--------|
| POST | `/a2a/tasks` | description | task_id, status, team (201) | Events | Shipped |
| GET | `/a2a/tasks` | status, limit (max 100) | Task list | Projections | Shipped |
| GET | `/a2a/tasks/{id}` | task_id | Task status | Projections | Shipped |
| GET | `/a2a/tasks/{id}/result` | task_id | Output, transcript, cost | Projections + transcript | Shipped |
| GET | `/a2a/tasks/{id}/events` | task_id | SSE stream | WS manager + event stream | Shipped |
| DELETE | `/a2a/tasks/{id}` | task_id | killed status | ColonyKilled event | Shipped |

### 2.7 Protocol Routes (`routes/protocols.py`)

| Method | Path | Returns | Status |
|--------|------|---------|--------|
| GET | `/.well-known/agent.json` | Dynamic Agent Card (skills, domains, federation, hardware) | Wave 33 |
| POST | `/ag-ui/runs` | AG-UI response | Shipped |
| Mount | `/mcp` | MCP HTTP transport | Shipped |

---

## 3. Queen Tools (21 operator-facing + 2 internal)

All tools route through `QueenToolDispatcher.dispatch()` in `queen_tools.py`.

| # | Tool Name | Parameters | Events Emitted | Replay-Safe | Status |
|---|-----------|-----------|----------------|-------------|--------|
| 1 | `spawn_colony` | task, castes, input_from, max_rounds, budget_limit, template_id, strategy, step_index, target_files, fast_path, preview | ColonySpawned | Yes | Shipped |
| 2 | `spawn_parallel` | reasoning, tasks[], parallel_groups[][], estimated_total_cost, knowledge_gaps, preview | ParallelPlanCreated | Yes | Shipped |
| 3 | `kill_colony` | colony_id | ColonyKilled | Yes | Shipped |
| 4 | `get_status` | workspace_id | None (read-only) | Yes | Shipped |
| 5 | `list_templates` | — | None (read-only) | Yes | Shipped |
| 6 | `inspect_template` | template_id | None (read-only) | Yes | Shipped |
| 7 | `inspect_colony` | colony_id | None (read-only) | Yes | Shipped |
| 8 | `read_workspace_files` | workspace_id | None (read-only) | Yes | Shipped |
| 9 | `suggest_config_change` | param_path, proposed_value, reason | None (in-memory proposal) | Partial | Shipped |
| 10 | `approve_config_change` | — (uses pending proposal) | WorkspaceConfigChanged | Yes | Shipped |
| 11 | `redirect_colony` | colony_id, new_goal, reason | ColonyRedirected | Yes | Shipped |
| 12 | `escalate_colony` | colony_id, tier, reason | None | **NO** (in-memory only) | Shipped |
| 13 | `read_colony_output` | colony_id, round_number, agent_id | None (read-only) | Yes | Shipped |
| 14 | `memory_search` | query, entry_type, limit | None (read-only) | Yes | Shipped |
| 15 | `write_workspace_file` | filename, content | None | **NO** (filesystem only) | Shipped |
| 16 | `queen_note` | action (save/list), content | None | Partial (YAML file) | Shipped |
| 17 | `set_thread_goal` | goal, expected_outputs | ThreadGoalSet | Yes | Shipped |
| 18 | `complete_thread` | reason | ThreadStatusChanged | Yes | Shipped |
| 19 | `archive_thread` | reason | ThreadArchived | Yes | Shipped |
| 20 | `define_workflow_steps` | steps[] | WorkflowStepsCreated | Yes | Shipped |
| 21 | `query_service` | service_type, query, timeout | None | **NO** (external) | Shipped |

**Internal (not in tool_specs):**
- `name_colony` — Auto-names colonies via Gemini Flash (emits ColonyNamed)
- `follow_up_colony` — Proactive colony summary in chat (emits QueenMessage)

---

## 4. Projections & View State

### 4.1 Projection Classes (19 total)

| Projection | Key Events Processed | Survives Replay | Notes |
|------------|---------------------|-----------------|-------|
| WorkspaceProjection | WorkspaceCreated, WorkspaceConfigChanged | Yes | Budget is Wave 43 |
| ThreadProjection | ThreadCreated, ThreadRenamed, ThreadGoalSet, ThreadStatusChanged, WorkflowStepDefined, WorkflowStepCompleted, ParallelPlanCreated | Yes | Wave 30-35 |
| ColonyProjection | ColonySpawned, ColonyCompleted, ColonyFailed, ColonyKilled, ColonyNamed, ColonyServiceActivated, ColonyRedirected, Round*, AgentTurn*, TokensConsumed, ColonyTemplateUsed | Yes | Most complex |
| AgentProjection | AgentTurnStarted | Yes | Simple |
| RoundProjection | RoundStarted, PhaseEntered, AgentTurnCompleted, RoundCompleted | Yes | Per-round metrics |
| MergeProjection | MergeCreated, MergePruned | Yes | Colony edges |
| ApprovalProjection | ApprovalRequested, ApprovalGranted, ApprovalDenied | Yes | Transient |
| TemplateProjection | ColonyTemplateCreated, ColonyTemplateUsed | Yes | Wave 50: learned fields |
| QueenMessageProjection | QueenMessage | Yes | Wave 49: metadata |
| ColonyOutcome | Derived from completion events | Yes | ADR-047, no new events |
| OperatorBehaviorProjection | OperatorAction, ColonyKilled, ColonyChatMessage, MemoryConfidenceUpdated | Yes | Wave 37 |
| OperatorOverlayState | OperatorAction, Annotated, ConfigOverridden | Yes | Wave 39 ADR-049 |
| BudgetSnapshot | TokensConsumed, RoundCompleted | Yes | Wave 43 |
| DomainStrategyProjection | DomainStrategyUpdated | Yes | Wave 44 |
| ForageCycleSummary | ForageRequested, ForageCycleCompleted | Yes | Wave 44-48 |
| DomainOverrideProjection | ForagerDomainOverride | Yes | Wave 44 |
| Memory entries | MemoryEntryCreated, StatusChanged, ConfidenceUpdated, ScopeChanged, Merged, Distilled, CRDT* | Yes | Knowledge base |
| Competing pairs | Lazy rebuild from memory entries | Yes | Wave 45 |

### 4.2 View State Snapshot (`view_state.py`)

`build_snapshot()` produces `OperatorStateSnapshot` with 10 components:
1. **tree** — Workspace → Thread → Colony hierarchy with agents, rounds, pheromones, topology
2. **merges** — Active merge edges
3. **queenThreads** — Thread-scoped Queen conversations (Wave 49: intent, render, meta)
4. **approvals** — Pending approval requests
5. **protocolStatus** — MCP/AG-UI/A2A health
6. **localModels** — Local LLM registry with probe data
7. **cloudEndpoints** — Cloud provider status + cooldowns
8. **castes** — Configured caste recipes
9. **runtimeConfig** — Full system configuration
10. **skillBankStats** — Knowledge summary

---

## 5. Runtime Operator Methods (`runtime.py`)

### Core Mutation Methods (all go through `emit_and_broadcast`)

| Method | Events Emitted | Called From |
|--------|---------------|-------------|
| `create_workspace(name)` | WorkspaceCreated | Routes, MCP |
| `create_thread(ws, name, goal, expected_outputs)` | ThreadCreated | Routes, MCP, Queen |
| `rename_thread(ws, thread, name, renamed_by)` | ThreadRenamed | Queen, MCP |
| `spawn_colony(ws, thread, task, castes, ...)` | ColonySpawned | Queen, Routes, API |
| `kill_colony(colony_id, killed_by)` | ColonyKilled | Queen, Routes |
| `send_queen_message(ws, thread, content)` | QueenMessage | WS commands |
| `create_merge(ws, from, to, created_by)` | MergeCreated | WS commands |
| `prune_merge(ws, edge_id)` | MergePruned | WS commands |
| `broadcast(ws, thread, from_colony)` | Multiple MergeCreated | WS commands |
| `approve(ws, request_id)` | ApprovalGranted | Queen, MCP |
| `deny(ws, request_id)` | ApprovalDenied | Queen, MCP |
| `update_config(ws, field, value)` | ModelAssignmentChanged or WorkspaceConfigChanged | MCP, WS |
| `apply_config_change(param_path, value, ws)` | WorkspaceConfigChanged | Governance (post-approval) |

### Read-Only / Utility Methods

| Method | Purpose | Called From |
|--------|---------|-------------|
| `resolve_model(caste, ws)` | Model cascade: workspace override → defaults | Agent building |
| `build_agents(colony_id)` | Construct AgentConfig list from castes + recipes | Colony manager |
| `suggest_team(objective)` | LLM team recommendation (Gemini Flash) | Routes |
| `retrieve_relevant_memory(task, ws, thread)` | Pre-spawn knowledge retrieval | Queen |
| `fetch_knowledge_for_colony(task, ws, thread, top_k)` | Agent context knowledge fetch | Colony manager |

### Tool Callback Factories

| Factory | Returns | Used By |
|---------|---------|---------|
| `make_catalog_search_fn()` | `_catalog_search(query, ws, top_k, tier)` | Agent tools |
| `make_knowledge_detail_fn()` | `_knowledge_detail(item_id)` | Agent tools |
| `make_artifact_inspect_fn()` | `_artifact_inspect(colony_id, artifact_id)` | Agent tools |
| `make_transcript_search_fn()` | `_transcript_search(query, ws, top_k)` | Agent tools |
| `make_knowledge_feedback_fn()` | `_knowledge_feedback(entry_id, success, tier)` | Agent tools |
| `make_forage_fn()` | `_request_forage(query, domain, max_results)` | Agent tools |

---

## 6. Internal Services & Subsystems

### LLMRouter (`runtime.py`)

- Provider-neutral routing with fallback chain (ADR-014)
- Budget gate: < $0.10 → cheapest model
- Provider cooldown (ADR-024): sliding-window failure tracking → auto-cooldown
- Streaming support (no fallback for streams)

### GovernanceController (`runtime.py`)

- `check_spawn_allowed(ws)` — Budget + hard stop check
- `check_model_downgrade(ws, caste, model)` — Cost comparison guard
- `check_workspace_hard_stop(ws)` — Emergency stop
- `budget_summary(ws)` — Full budget breakdown

### Proactive Intelligence (`proactive_intelligence.py`)

- 14 deterministic rules (no LLM calls)
- 7 knowledge-health + 4 performance + evaporation + branching + earned autonomy
- Consumed by briefing route and maintenance dispatcher

### Self-Maintenance (`self_maintenance.py`)

- MaintenanceDispatcher: 3 autonomy levels (suggest, auto_notify, autonomous)
- Budget tracking (daily reset at UTC midnight)
- Dispatches colonies for: dedup, stale sweep, contradiction, distillation

### Forager (`forager.py`)

- 3 trigger modes: reactive (gap detection), proactive (briefing), operator (manual)
- Orchestrates: search → fetch → quality score → admission
- Domain strategy memory with operator trust overrides

---

## 7. Event Type Registry (62 events, closed union)

```
WorkspaceCreated, ThreadCreated, ThreadRenamed,
ColonySpawned, ColonyCompleted, ColonyFailed, ColonyKilled,
RoundStarted, PhaseEntered, AgentTurnStarted, AgentTurnCompleted,
RoundCompleted, MergeCreated, MergePruned, ContextUpdated,
WorkspaceConfigChanged, ModelRegistered, ModelAssignmentChanged,
ApprovalRequested, ApprovalGranted, ApprovalDenied,
QueenMessage, TokensConsumed,
ColonyTemplateCreated, ColonyTemplateUsed, ColonyNamed,
SkillConfidenceUpdated, SkillMerged,
ColonyChatMessage, CodeExecuted,
ServiceQuerySent, ServiceQueryResolved, ColonyServiceActivated,
KnowledgeEntityCreated, KnowledgeEdgeCreated, KnowledgeEntityMerged,
ColonyRedirected,
MemoryEntryCreated, MemoryEntryStatusChanged, MemoryExtractionCompleted,
KnowledgeAccessRecorded, ThreadGoalSet, ThreadStatusChanged,
MemoryEntryScopeChanged, DeterministicServiceRegistered,
MemoryConfidenceUpdated, WorkflowStepDefined, WorkflowStepCompleted,
CRDTCounterIncremented, CRDTTimestampUpdated,
CRDTSetElementAdded, CRDTRegisterAssigned, MemoryEntryMerged,
ParallelPlanCreated, KnowledgeDistilled,
KnowledgeEntryOperatorAction, KnowledgeEntryAnnotated, ConfigSuggestionOverridden,
ForageRequested, ForageCycleCompleted, DomainStrategyUpdated, ForagerDomainOverride
```
