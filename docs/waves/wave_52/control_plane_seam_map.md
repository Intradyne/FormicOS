# Wave 52 — Control-Plane Seam Map

## Purpose

End-to-end seam traces for every control plane, showing how requests enter
the system, what shared infrastructure they use, and where they diverge.
Duplication, drift, and hidden dependencies are called out explicitly.

---

## 1. Queen Task Intake

```
Operator message (MCP chat_queen / WS send_queen_message)
  → runtime.queen_respond(workspace_id, thread_id, content)
    → Queen LLM call with 21 tools + thread context + knowledge briefing
      → tool calls dispatched via QueenToolDispatcher
        → spawn_colony / spawn_parallel / memory_search / etc.
          → runtime.emit_and_broadcast() for mutations
            → ProjectionStore rebuild + WS fan-out to subscribers
```

**Shared dependencies:** QueenRuntime, ProjectionStore, emit_and_broadcast,
knowledge retrieval (knowledge_catalog.py), thread manager

**Key note:** Queen has 21 tools, MCP has 19 tools. These are DIFFERENT tool
sets with partial overlap (see Track C findings). Queen tools are
LLM-callable only; MCP tools are externally callable.

---

## 2. WebSocket Command Path

```
WS JSON message { type: "command", ... }
  → ws_handler.dispatch_command(command_type, payload)
    → command-specific handler (17 command types)
      → runtime.* method call
        → runtime.emit_and_broadcast()
          → ProjectionStore rebuild + WS fan-out
            → UI re-render via store.applySnapshot() / incremental event
```

**WS-exclusive commands (not available via MCP or REST):**
- `rename_colony` → ColonyNamed event
- `rename_thread` → ThreadRenamed event
- `save_queen_note` → QueenNoteSaved event (Queen also has `queen_note`)

**Shared dependencies:** Same runtime, same emit_and_broadcast, same projections

**State delivery:** WS delivers full OperatorStateSnapshot on subscribe, then
incremental events. Frontend state store applies both.

---

## 3. REST API Path

```
HTTP request → Starlette route handler (api.py, colony_io.py, knowledge_api.py, etc.)
  → Reads from ProjectionStore (observation endpoints)
  → OR runtime.emit_and_broadcast() (mutation endpoints)
    → ProjectionStore rebuild + WS fan-out
```

**REST-exclusive capabilities (not available via MCP, Queen, or WS):**
- Colony file upload/export/transcript/artifacts
- Workspace file upload/preview/ingest
- Template creation
- Caste recipe CRUD
- Model policy updates
- Knowledge promotion
- Forager trigger/domain-override/cycles/domains
- Outcomes/escalation-matrix
- Config overrides/recommendations
- Demo workspace creation
- Thread timeline
- Colony audit view
- Retrieval diagnostics
- Knowledge graph

**Note:** REST is the richest surface for diagnostic and administrative
operations. Many REST-only endpoints are consumed by the frontend but have
no MCP/Queen equivalent.

---

## 4. MCP Path

```
MCP JSON-RPC request (Streamable HTTP at /mcp)
  → FastMCP tool dispatch
    → Tool handler function
      → runtime.* method call
        → runtime.emit_and_broadcast() (mutations)
        → OR ProjectionStore read (observations)
```

**MCP-exclusive capabilities (not available via Queen, WS, or REST):**
- `code_execute` — sandboxed Python execution
- `configure_scoring` — workspace-scoped retrieval weight overrides
- `set_maintenance_policy` / `get_maintenance_policy`
- `create_workspace`

**MCP Resources (5, read-only, auto-exposed as tools):**
- `formicos://knowledge/{workspace}` — list entries
- `formicos://knowledge/{entry_id}` — entry detail
- `formicos://threads/{workspace_id}` — list threads
- `formicos://threads/{workspace_id}/{thread_id}` — thread detail
- `formicos://colonies/{colony_id}` — colony status
- `formicos://briefing/{workspace_id}` — proactive briefing

**MCP Prompts (2, auto-exposed as tools):**
- `knowledge-query` — knowledge-augmented question prompt
- `plan-task` — workspace-context task planning prompt

---

## 5. AG-UI Path

```
POST /ag-ui/runs { task, castes?, workspace_id?, thread_id? }
  → agui_endpoint.handle_agui_run()
    → runtime.spawn_colony()
      → emit_and_broadcast(ColonySpawned)
    → Subscribe to colony event queue
    → Emit SSE frames via event_translator.translate_event()
      → 9 Tier-1 frames (RUN_STARTED, STEP_STARTED, TEXT_MESSAGE_*, etc.)
      → 39+ CUSTOM frames (knowledge, governance, forager, etc.)
    → Close on terminal event or 300s idle timeout
```

**Shared with A2A:** Same `event_translator.translate_event()` function
produces identical event shapes for both AG-UI and A2A SSE streams.

**AG-UI limitations:**
- No token streaming (summary-at-turn-end per ADR-035)
- No TOOL_CALL_START/END events (runner doesn't emit per-tool granularity)
- No STATE_DELTA (no JSON-patch source)
- Single colony per run (no parallel DAG support)

---

## 6. A2A Path

```
POST /a2a/tasks { description }
  → a2a.create_task()
    → Deterministic team selection (template match → keyword classify → fallback)
    → runtime.spawn_colony() in "default" workspace, thread "a2a-{slug}"
      → emit_and_broadcast(ColonySpawned)
    → Return { task_id, status: "running", team, ... }

GET /a2a/tasks/{id} (poll)
  → Read ColonyProjection → status envelope

GET /a2a/tasks/{id}/events (SSE attach)
  → Same event_translator as AG-UI
  → Snapshot-then-live-tail pattern

GET /a2a/tasks/{id}/result
  → Build transcript from colony records
  → Return { output, transcript, quality_score, cost, ... }

DELETE /a2a/tasks/{id}
  → runtime.kill_colony() → emit_and_broadcast(ColonyKilled)
```

**A2A constraints:**
- Always uses "default" workspace
- Deterministic team selection (no LLM suggest_team)
- No Queen mediation — direct colony spawn
- Thread naming: `a2a-{slug}` prefix
- Task ID === Colony ID (no second store)

**Shared with AG-UI:** Event translator, SSE delivery, colony event queues

---

## 7. Agent Card Discovery Path

```
GET /.well-known/agent.json
  → protocols.agent_card_endpoint()
    → Reads from:
      - CapabilityRegistry (protocols, tools, events)
      - ProjectionStore (knowledge stats, thread count)
      - Template projections (skills)
      - Registry (external specialists)
      - GPU detection (hardware)
      - Federation state (peer count, trust)
    → Returns dynamic JSON agent card
```

**No mutation.** Pure observation endpoint. Describes the entire system in
one response.

---

## 8. Shared Infrastructure Map

```
                    ┌─────────────┐
                    │   Operator   │
                    └──────┬──────┘
          ┌────────────────┼────────────────┐
          │                │                │
       ┌──▼──┐         ┌──▼──┐         ┌──▼──┐
       │ MCP │         │ WS  │         │ REST│
       └──┬──┘         └──┬──┘         └──┬──┘
          │                │                │
          │    ┌───────────┼───────────┐    │
          │    │           │           │    │
       ┌──▼───▼──┐   ┌───▼───┐   ┌──▼───▼──┐
       │ Runtime  │   │ Queen │   │ProjectionStore│
       └────┬─────┘   └───┬───┘   └─────────┘
            │              │              ▲
            │      (21 tools)             │
            │              │              │
            ▼              ▼              │
     ┌──────────────────────────┐         │
     │  emit_and_broadcast()    │─────────┘
     └──────────┬───────────────┘
                │
     ┌──────────▼───────────────┐
     │    SQLite Event Store    │
     └──────────────────────────┘
```

External surfaces (A2A, AG-UI, Agent Card) connect through the same
Runtime but with different entry constraints.

---

## 9. Duplication and Drift Notes

### Same capability, different names

| Capability | MCP name | Queen name | WS name | REST path |
|------------|----------|------------|---------|-----------|
| Chat queen | `chat_queen` | — | `send_queen_message` | — |
| Colony status | `get_status` | `get_status` | `subscribe` (snapshot) | various |
| List templates | `list_templates` | `list_templates` | — | `GET /templates` |
| Template detail | `get_template_detail` | `inspect_template` | — | `GET /templates/{id}` |
| Query service | `query_service` | `query_service` | — | `POST /services/query` |
| Queen notes | — | `queen_note` | `save_queen_note` | — |

### Hidden shared dependencies

1. **event_translator.py** — shared by both AG-UI and A2A SSE streams
2. **knowledge_catalog.py** — shared by Queen context assembly, MCP resources,
   REST search, and retrieval diagnostics
3. **ProjectionStore** — shared by ALL surfaces for reads
4. **emit_and_broadcast()** — shared by ALL surfaces for writes
5. **CapabilityRegistry** — shared by Agent Card, `/debug/inventory`, and
   `view_state.py` protocol status builder

### Configuration split

- **Retrieval weights:** MCP `configure_scoring` only. Not via REST, WS, or Queen.
- **Maintenance policy:** MCP `set_maintenance_policy` only. Not via REST, WS, or Queen.
- **Caste recipes:** REST `PUT /castes/{id}` only. Not via MCP, WS, or Queen.
- **Model policy:** REST `PATCH /models/{addr}` only. Not via MCP, WS, or Queen.
- **Forager controls:** REST only. Not via MCP, WS, or Queen.

This split is arguably intentional: MCP for programmatic integration,
REST for operator UI, Queen for autonomous decisions. But it means no
single surface can do everything.
