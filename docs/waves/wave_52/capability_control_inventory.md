# Wave 52 — Capability / Control-Plane Inventory

## Purpose

Canonical inventory of every operator and external capability, which surfaces
expose it, mutation vs observation, and persistence status. Source of truth
for coherence audits.

---

## 1. Control Planes

| Surface | Transport | Mount | Primary Role | Tool/Route Count |
|---------|-----------|-------|--------------|------------------|
| **MCP** | Streamable HTTP | `/mcp` | External integration, operator tooling | 19 tools + 5 resources + 2 prompts |
| **Queen** | LLM tool-use (internal) | N/A | Autonomous orchestration | 21 tools |
| **WebSocket** | WS | `/ws` | Live operator UI, state fan-out | 17 commands |
| **REST** | HTTP | `/api/v1/*` | CRUD, diagnostics, colony I/O | ~60 endpoints |
| **A2A** | REST + SSE | `/a2a/tasks` | External agent task lifecycle | 6 endpoints |
| **AG-UI** | SSE | `/ag-ui/runs` | External UI integration | 9 Tier-1 events + 39 CUSTOM |
| **Agent Card** | HTTP GET | `/.well-known/agent.json` | External discovery | 1 endpoint (dynamic) |

**Single mutation path:** All surfaces funnel mutations through
`runtime.emit_and_broadcast()` → SQLite event store → projection rebuild.
No shadow databases.

---

## 2. Capability Inventory

### 2.1 Colony Lifecycle

| Capability | MCP | Queen | WS | REST | A2A | Persistence |
|------------|-----|-------|----|------|-----|-------------|
| Spawn colony | `spawn_colony` | `spawn_colony` | `spawn_colony` | `preview-colony` (preview only) | `POST /a2a/tasks` | Event: ColonySpawned |
| Spawn parallel DAG | — | `spawn_parallel` | — | — | — | Event: ParallelPlanCreated |
| Kill colony | `kill_colony` | `kill_colony` | `kill_colony` | — | `DELETE /a2a/tasks/{id}` | Event: ColonyKilled |
| Redirect colony | — | `redirect_colony` | — | — | — | Event: ColonyRedirected |
| Escalate colony | — | `escalate_colony` | — | — | — | Event: ColonyEscalated |
| Inspect colony | — | `inspect_colony` | — | `GET /colonies/{id}/audit` | `GET /a2a/tasks/{id}` | Read-only |
| Rename colony | — | — | `rename_colony` | — | — | Event: ColonyNamed |
| Chat colony | `chat_colony` | — | `chat_colony` | — | — | Runtime-only (injected to context) |
| Activate service | `activate_service` | — | `activate_service` | — | — | Event: ServiceActivated |
| Colony transcript | — | `read_colony_output` | — | `GET /colonies/{id}/transcript` | `GET /a2a/tasks/{id}/result` | Derived from events |
| Colony artifacts | — | — | — | `GET /colonies/{id}/artifacts` | — | Read-only |
| Colony files upload | — | — | — | `POST /colonies/{id}/files` | — | Filesystem |
| Colony export ZIP | — | — | — | `GET /colonies/{id}/export` | — | Read-only |

### 2.2 Queen & Thread Management

| Capability | MCP | Queen | WS | REST | Persistence |
|------------|-----|-------|----|------|-------------|
| Chat Queen | `chat_queen` | — | `send_queen_message` | — | Event: QueenMessage |
| Set thread goal | — | `set_thread_goal` | — | — | Event: ThreadGoalSet |
| Complete thread | — | `complete_thread` | — | — | Event: ThreadCompleted |
| Archive thread | — | `archive_thread` | — | — | Event: ThreadArchived |
| Rename thread | — | — | `rename_thread` | — | Event: ThreadRenamed |
| Define workflow steps | — | `define_workflow_steps` | — | — | Event: WorkflowStepDefined |
| Queen notes | — | `queen_note` | `save_queen_note` | — | Event: QueenNoteSaved |
| Create thread | `create_thread` | — | `create_thread` | — | Event: ThreadCreated |
| Thread timeline | — | — | — | `GET /threads/{id}/timeline` | Derived from events |

### 2.3 Knowledge & Memory

| Capability | MCP | Queen | WS | REST | Persistence |
|------------|-----|-------|----|------|-------------|
| List knowledge | Resource: `formicos://knowledge/{ws}` | — | — | `GET /knowledge` | Read-only |
| Search knowledge | — | `memory_search` | — | `GET /knowledge/search` | Read-only |
| Get entry detail | Resource: `formicos://knowledge/{id}` | — | — | `GET /knowledge/{id}` | Read-only |
| Promote entry | — | — | — | `POST /knowledge/{id}/promote` | Event: MemoryEntryPromoted |
| Temporal edges | — | — | — | `GET /knowledge/{id}/temporal-edges` | Read-only |
| Config override | — | — | — | `POST /knowledge/config-override` | Event: ConfigSuggestionOverridden |
| Query service | `query_service` | `query_service` | — | `POST /services/query` | Runtime-only |
| Briefing | Resource: `formicos://briefing/{ws}` | — | — | `GET /briefing` | Derived |
| Knowledge graph | — | — | — | `GET /knowledge-graph` | Read-only |
| Retrieval diagnostics | — | — | — | `GET /retrieval-diagnostics` | Read-only |

### 2.4 Workspace & Configuration

| Capability | MCP | Queen | WS | REST | Persistence |
|------------|-----|-------|----|------|-------------|
| List workspaces | `list_workspaces` | — | — | — | Read-only |
| Create workspace | `create_workspace` | — | — | — | Event: WorkspaceCreated |
| Create demo workspace | — | — | — | `POST /workspaces/create-demo` | Events |
| Get status | `get_status` | `get_status` | `subscribe` (snapshot) | — | Derived |
| Configure scoring | `configure_scoring` | — | — | — | Event: WorkspaceConfigChanged |
| Suggest config change | — | `suggest_config_change` | — | — | Queen-mediated |
| Approve config change | — | `approve_config_change` | — | — | Event |
| Update config | — | — | `update_config` | — | Event: WorkspaceConfigChanged |
| Config recommendations | — | — | — | `GET /config-recommendations` | Derived |
| Config overrides | — | — | — | `GET/POST /config-overrides` | Event-sourced |
| Outcomes | — | — | — | `GET /outcomes?period=` | Derived |
| Escalation matrix | — | — | — | `GET /escalation-matrix` | Derived |

### 2.5 Maintenance & Autonomy

| Capability | MCP | Queen | WS | REST | Persistence |
|------------|-----|-------|----|------|-------------|
| Set maintenance policy | `set_maintenance_policy` | — | — | — | Event: WorkspaceConfigChanged |
| Get maintenance policy | `get_maintenance_policy` | — | — | — | Read-only |
| Dismiss autonomy rec | — | — | — | `POST /dismiss-autonomy` | **Ephemeral** (runtime-only) |

### 2.6 Web Foraging

| Capability | MCP | Queen | WS | REST | Persistence |
|------------|-----|-------|----|------|-------------|
| Trigger forage | — | — | — | `POST /forager/trigger` | Event: ForageRequested |
| Domain override | — | — | — | `POST /forager/domain-override` | Event: ForagerDomainOverride |
| Forage cycles | — | — | — | `GET /forager/cycles` | Event-sourced |
| Domain strategies | — | — | — | `GET /forager/domains` | Event-sourced |

### 2.7 Governance & Merges

| Capability | MCP | Queen | WS | REST | Persistence |
|------------|-----|-------|----|------|-------------|
| Approve | `approve` | — | `approve` | — | Event |
| Deny | `deny` | — | `deny` | — | Event |
| Create merge | `create_merge` | — | `create_merge` | — | Event: MergeEdgeCreated |
| Prune merge | `prune_merge` | — | `prune_merge` | — | Event: MergeEdgePruned |
| Broadcast | `broadcast` | — | `broadcast` | — | Events |

### 2.8 Templates & Team

| Capability | MCP | Queen | WS | REST | Persistence |
|------------|-----|-------|----|------|-------------|
| List templates | `list_templates` | `list_templates` | — | `GET /templates` | Read-only |
| Get template | `get_template_detail` | `inspect_template` | — | `GET /templates/{id}` | Read-only |
| Create template | — | — | — | `POST /templates` | Event |
| Workspace templates | — | — | — | `GET /workspaces/{id}/templates` | Read-only |
| Suggest team | `suggest_team` | — | — | `POST /suggest-team` | Runtime-only (LLM call) |

### 2.9 Models, Castes, Code Execution

| Capability | MCP | Queen | WS | REST | Persistence |
|------------|-----|-------|----|------|-------------|
| Code execute | `code_execute` | — | — | — | Runtime-only (sandbox) |
| List castes | — | — | — | `GET /castes` | Read-only |
| Update caste | — | — | — | `PUT /castes/{id}` | YAML file |
| Update model policy | — | — | — | `PATCH /models/{addr}` | Settings file |

### 2.10 Files & Workspace Persistence

| Capability | MCP | Queen | WS | REST | Persistence |
|------------|-----|-------|----|------|-------------|
| Read workspace files | — | `read_workspace_files` | — | `GET /workspaces/{id}/files` | Filesystem |
| Write workspace file | — | `write_workspace_file` | — | `POST /workspaces/{id}/files` | Filesystem |
| Ingest workspace file | — | — | — | `POST /workspaces/{id}/ingest` | Qdrant embeddings |

---

## 3. Discovery Surface

The **Agent Card** (`/.well-known/agent.json`) is the canonical external
contract. It is dynamically generated and includes:

- Protocol endpoints and transports (MCP, AG-UI, A2A)
- Skills derived from colony templates
- Live knowledge stats (total entries, domain breakdown, avg confidence)
- Active thread count
- External specialist status
- Federation status (enabled, peer count, trust scores)
- Hardware availability (GPU detection)

The Agent Card is the only surface that describes the *whole system* in a
single response. All other surfaces describe their own slice.

---

## 4. Capability Registry

`CapabilityRegistry` (ADR-036) is the single programmatic source:

| Field | Content | Dynamic? |
|-------|---------|----------|
| `event_names` | 64 event types | Static (code-defined) |
| `mcp_tools` | 19 tool specs | Static (registered at startup) |
| `queen_tools` | 21 tool specs | Static (registered at startup) |
| `agui_events` | 9 AG-UI event types | Static |
| `protocols` | 3 protocol entries | Static (configured at startup) |
| `castes` | 5 caste types | Static |
| `version` | System version string | Static |

Exposed at `GET /debug/inventory` (debug endpoint, not in production routes).
