# FormicOS Architecture

High-level orientation for the current system. For the detailed knowledge and
maintenance lifecycle, also read [KNOWLEDGE_LIFECYCLE.md](KNOWLEDGE_LIFECYCLE.md).

## Layer Diagram

```
+------------------------------------------------------------------+
|                           SURFACE LAYER                          |
|  app.py | ws_handler.py | mcp_server.py | queen_runtime.py       |
|  queen_tools.py | colony_manager.py | projections.py | services  |
+------------------------------------------------------------------+
                |                          |
                v                          v
+--------------------------------+  +--------------------------------+
|          ENGINE LAYER          |  |         ADAPTERS LAYER         |
|  runner.py | context.py        |  |  store_sqlite.py              |
|  strategies/ | service_router  |  |  vector_qdrant.py             |
|                                |  |  llm_*.py | federation_*      |
|                                |  |  knowledge_graph.py           |
+--------------------------------+  +--------------------------------+
                \                          /
                 \                        /
                  v                      v
+------------------------------------------------------------------+
|                            CORE LAYER                            |
|  events.py (55 types) | ports.py | types.py | crdt.py | settings |
+------------------------------------------------------------------+
```

**Strict inward dependency:** each layer imports only from layers below it.
Core imports nothing. Engine and Adapters import only Core. Surface imports all.
Enforced by `scripts/lint_imports.py` (AST-based import analysis) in CI.

## Event Flow

An operator action flows through the system like this:

```
Browser UI                 FormicOS Server              SQLite
    |                           |                         |
    |-- WS command ----------->|                         |
    |   {action, workspaceId,  |                         |
    |    payload}              |                         |
    |                          |-- handle_command() ---->|
    |                          |   (surface/commands.py) |
    |                          |                         |
    |                          |-- event_store.append() -|-> events table
    |                          |                         |
    |                          |<- seq assigned ---------|
    |                          |                         |
    |                          |-- projections.apply() ->|
    |                          |   (in-memory update)    |
    |                          |                         |
    |<-- WS event fan-out -----|                         |
    |   {type: "event", ...}   |                         |
    |                          |                         |
    |<-- WS state snapshot ----|                         |
    |   {type: "state", ...}   |                         |
```

On startup, all events replay from SQLite into projections before accepting
connections. This keeps projections consistent with the event log and makes
the system crash-recoverable by design.

## Data Model

The data model is a tree:

```
System
  +-- Workspace ("default")
        +-- Thread ("main")
              +-- Colony (id: uuid)
                    +-- Round 1
                    |     +-- Agent Turn (coder)
                    |     +-- Agent Turn (reviewer)
                    +-- Round 2
                          +-- Agent Turn (coder)
                          +-- Agent Turn (reviewer)
```

Each level is represented by events:
- `WorkspaceCreated` / `ThreadCreated` -- structural events
- `ColonySpawned` / `ColonyCompleted` / `ColonyFailed` / `ColonyKilled` -- lifecycle
- `RoundStarted` / `RoundCompleted` -- execution progress
- `AgentTurnStarted` / `AgentTurnCompleted` -- per-agent work
- `QueenMessage` -- operator-Queen conversation (scoped to thread)

Threads can also carry:
- workflow steps (`WorkflowStepDefined`, `WorkflowStepCompleted`)
- parallel delegation plans (`ParallelPlanCreated`)
- operator steering metadata (directives delivered into colony context)

## Model Resolution Cascade

Model assignment follows a nullable cascade:

```
Thread override  -->  Workspace override  -->  System default
     (null)               (null)            "anthropic/claude-sonnet-4.6"
```

If a thread has no override, the workspace config is checked. If the workspace
has no override, the system default from `config/formicos.yaml` is used. This
lets operators run cheap local models for experimentation and cloud models for
production work, per-workspace.

Config changes emit `WorkspaceConfigChanged` or `ModelAssignmentChanged` events.

## Coordination Strategies

### Stigmergic (default)

Agents are connected by a weighted topology graph. Each round:

1. **Route phase** -- DyTopo algorithm builds execution order from pheromone weights
2. **Execute phase** -- agents run in the resolved order, each receiving context
   from upstream connections weighted by pheromone strength
3. **Compress phase** -- round output is compressed and pheromones update:
   - Successful paths: reinforce by `pheromone_reinforce_rate` (default 0.3)
   - All paths: decay by `pheromone_decay_rate` (default 0.1)
   - Cosine similarity between rounds drives convergence detection

### Sequential

Simple round-robin: agents execute in caste order (queen, coder, reviewer,
researcher, archivist). No pheromone graph. Useful for simple tasks or debugging.

## Knowledge and Persistence

- **Event store:** single SQLite database in WAL mode (`events.db`)
- **Knowledge index:** Qdrant-backed retrieval over replay-safe `MemoryEntry`
  events, with Bayesian confidence, decay, thread bonus, and co-occurrence
  scoring computed from projection state
- **Knowledge graph:** separate adapter/projection surface for entity/edge views
- **Projections:** in-memory dataclass trees rebuilt from events on startup

The event store is append-only. No updates, no deletes. Derived stores and
projections can always be rebuilt from the event log.

All persistent runtime data lives under `FORMICOS_DATA_DIR` (default `./data`,
`/data` in Docker).

## Protocol Surface

FormicOS exposes the same event-sourced runtime through multiple surfaces:

- **MCP** for tool/resource/prompt access from external agents
- **HTTP/REST** for browser and service integration endpoints
- **WebSocket** for state snapshots, command dispatch, and live event fan-out
- **AG-UI** for promoted operator-facing event streams
- **A2A** for agent discovery / interoperability surfaces

The important invariant is not “one protocol only”; it is that every surface
routes through the same mutation, event, and projection truth.
