# Wave 51: Backend Seam Map

Audit date: 2026-03-20. Traces end-to-end capability seams through the backend.

---

## 1. WebSocket Command → Event → Projection → Frontend

```
Operator (UI)
  → WebSocket message {action: "spawn_colony", ...}
  → ws_handler.py: WebSocketManager.dispatch_command()
  → commands.py: handle_command() dispatch table
  → commands.py: _handle_spawn_colony()
    → runtime.spawn_colony(ws, thread, task, castes, ...)
      → constructs ColonySpawned event (seq=0)
      → runtime.emit_and_broadcast(event)
        → event_store.append(event) → assigned seq
        → projections.apply(event) → ColonyProjection created
        → ws_manager.fan_out_event() → broadcast to all WS subscribers
      → colony_manager.start_colony() → async round loop
    → returns {colonyId}
  → WS response to client
  → Frontend receives state update via WS broadcast
```

**Key seam**: `emit_and_broadcast()` is THE ONE MUTATION PATH. Every state
change flows through it. Projection update and WS broadcast are synchronous
within the same call.

---

## 2. REST Route → Handler → Runtime/Store/Projection

### Read path (typical)

```
HTTP GET /api/v1/workspaces/{ws}/outcomes?period=7d
  → routes/api.py: get_workspace_outcomes()
  → projections.colony_outcomes (dict lookup)
  → filters by period, computes summary stats
  → returns JSON response
```

### Write path (typical)

```
HTTP POST /api/v1/knowledge/{item_id}/promote
  → routes/knowledge_api.py: promote_entry()
  → validates item exists in projections.memory_entries
  → runtime.emit_and_broadcast(MemoryEntryScopeChanged)
    → event_store.append()
    → projections.apply() → updates entry scope
    → ws_manager.fan_out_event()
    → memory_store sync (if Qdrant available)
  → returns {promoted: true, scope}
```

### File I/O path (no events)

```
HTTP POST /api/v1/workspaces/{ws}/files
  → routes/colony_io.py: upload_workspace_files()
  → validates extension whitelist, size limits
  → writes to {data_dir}/workspaces/{ws}/files/
  → returns {uploaded: [...]}
  (NO events emitted — filesystem-only)
```

---

## 3. Queen Tool → Dispatcher → Runtime → Events

```
Queen LLM output includes tool_call: {name: "spawn_parallel", arguments: {...}}
  → queen_runtime.py: _handle_queen_tool_call()
  → queen_tools.py: QueenToolDispatcher.dispatch(tool_name, inputs)
    → validates inputs
    → _spawn_parallel(inputs, workspace_id, thread_id)
      → constructs DelegationPlan, validates DAG (Kahn's algorithm)
      → runtime.emit_and_broadcast(ParallelPlanCreated)
      → for each parallel_group:
          asyncio.gather(*[spawn_colony_for_task(t) for t in group])
      → returns plan summary text
  → Queen receives tool result as assistant message
  → Queen continues conversation with operator
```

**Thread-delegated tools** (archive_thread, define_workflow_steps):
```
dispatch() returns DELEGATE_THREAD sentinel
  → queen_runtime.py routes to QueenThreadManager
  → thread manager handles lifecycle + events
```

---

## 4. State Snapshot Path → Projections/View State → Frontend

```
WS client subscribes to workspace
  → ws_handler.py: _subscribe()
  → view_state.py: build_snapshot(projections, settings, castes, ...)
    → builds tree: Workspace → Thread → Colony hierarchy
    → builds merges: active merge edges
    → builds queenThreads: per-thread Queen conversation
    → builds approvals: pending requests
    → builds protocolStatus: MCP/AG-UI/A2A health
    → builds localModels: LLM probe data
    → builds cloudEndpoints: provider status
    → builds castes: recipe configs
    → builds runtimeConfig: full settings
    → builds skillBankStats: knowledge summary
  → sends {type: "state", state: snapshot} via WS
```

**Incremental updates** after snapshot:
```
Any event via emit_and_broadcast()
  → ws_manager.fan_out_event(event)
  → each subscribed client receives {type: "event", event: {...}}
  → Frontend applies event to local store (store.ts)
```

---

## 5. Memory / Knowledge Path

### Creation (colony extraction)

```
Colony round completes → extraction hook
  → LLM extracts skills/experiences from transcript
  → runtime.emit_and_broadcast(MemoryEntryCreated)
    → projections.apply() → memory_entries dict updated
    → memory_store.upsert() → Qdrant vector indexed
  → 5-axis security scan (prompt injection, data exfil, credential, code safety, detect-secrets)
  → If passes: emit MemoryEntryStatusChanged(candidate → verified)
```

### Retrieval (agent context)

```
Colony needs context for next round
  → colony_manager calls runtime.fetch_knowledge_for_colony()
  → knowledge_catalog.search(query, workspace_id, top_k)
    → vector_store.search() → semantic matches
    → 6-signal composite scoring (ADR-044):
      0.38*semantic + 0.25*thompson + 0.15*freshness + 0.10*status + 0.07*thread + 0.05*cooccurrence
    → tier-based detail level (summary/standard/full/auto)
    → budget-aware context assembly
  → returns formatted knowledge items for agent context
```

### Scope promotion

```
Operator clicks "Promote to Global" in UI
  → HTTP POST /api/v1/knowledge/{id}/promote {target_scope: "global"}
  → knowledge_api.py: promote_entry()
  → runtime.emit_and_broadcast(MemoryEntryScopeChanged)
    → projections.apply() → entry.scope updated, workspace_id cleared for global
    → ws_manager broadcast
    → memory_store sync
```

### Operator co-authorship

```
Operator pins/mutes/invalidates entry via UI
  → HTTP POST /api/v1/knowledge/{id}/action {action: "pin", ...}
  → knowledge_api.py: operator_action()
  → runtime.emit_and_broadcast(KnowledgeEntryOperatorAction)
    → projections.apply() → OperatorOverlayState updated
    → Does NOT mutate Beta confidence (local-first overlay)
```

---

## 6. Template / Config Memory Path

### Template creation (learned)

```
Colony completes successfully with good quality
  → projection handler detects ColonyCompleted
  → If quality_score > threshold AND pattern matches existing category:
    → runtime.emit_and_broadcast(ColonyTemplateCreated)
      → projections.apply() → TemplateProjection added (learned=true)
  → Template carries: castes, strategy, max_rounds, budget_limit, task_category
```

### Template usage

```
Queen spawns colony with template_id
  → queen_tools.py: _spawn_colony() resolves template
  → Loads template (operator from YAML, learned from projections)
  → Applies template: castes, strategy, max_rounds, budget_limit
  → runtime.emit_and_broadcast(ColonyTemplateUsed)
    → projections.apply() → template.use_count++, tracks success/failure
```

### Config recommendations

```
GET /api/v1/workspaces/{ws}/config-recommendations
  → api.py: get_config_recommendations()
  → proactive_intelligence.generate_config_recommendations(projections, ws)
    → analyzes ColonyOutcomes for patterns
    → returns recommendations with dimension, value, evidence, confidence
```

### Config override flow

```
Queen proposes config change via suggest_config_change tool
  → queen_tools.py: _suggest_config_change()
    → Gate 1: config_validator.validate_config_update() (structural)
    → Gate 2: _is_experimentable() (scope whitelist)
    → Stores PendingConfigProposal in memory (TTL=5min)
  → Operator approves → Queen calls approve_config_change
    → Re-validates both gates
    → runtime.apply_config_change()
      → emit_and_broadcast(WorkspaceConfigChanged)
      → _persist_castes() if caste field
```

---

## 7. Provider / Router Capability Path

### Model resolution

```
Colony needs LLM call
  → colony_manager → runner.py builds round context
  → runtime.resolve_model(caste, workspace_id)
    → Check workspace config overrides (WorkspaceConfigChanged events)
    → Fall back to system defaults
  → LLMRouter.route(caste, phase, round, budget_remaining, default_model)
    → Budget gate: < $0.10 → cheapest model
    → Routing table: phase-based override
    → Adapter existence check
    → Return resolved model address
```

### Completion with fallback

```
LLMRouter.complete(model, messages, tools, ...)
  → Check provider cooldown (ADR-024)
    → If cooled down → skip to fallback
  → Resolve adapter for provider prefix
  → adapter.complete(model, messages, ...)
  → On failure:
    → _ProviderCooldown.record_failure(provider)
    → _complete_with_fallback(original, messages, ...)
      → Try fallback chain: [gemini-flash → llama-cpp → claude-sonnet]
      → Skip cooled-down providers
      → Clamp max_tokens to fallback model policy
      → Return first successful result
  → On Gemini content block (stop_reason="blocked") → fallback
```

### Provider health visibility

```
view_state.py: build_snapshot()
  → llm_router.provider_health() → {provider: "ok"|"cooldown"}
  → _probe_local_endpoints() → httpx to llama.cpp /health, /metrics
  → Cloud provider API key presence check
  → All surfaced in cloudEndpoints + localModels snapshot components
```

---

## 8. Replay Path

### Startup replay

```
app.py lifespan():
  1. Create ProjectionStore()
  2. event_store.replay(after_seq=0) → yield all events
  3. for event in events:
       projections.apply(event)  # rebuild all read-model state
  4. projections.last_seq = highest seq seen
  5. memory_store.rebuild_from_projection(projections.memory_entries)
  6. Restart backfill for incomplete extractions
```

### What survives replay

- All 19 projection classes (event-driven, deterministic handlers)
- Memory entries with full confidence history
- Operator overlays (pins, mutes, annotations)
- Template stats (success/failure/use counts)
- Colony outcomes (derived from completion events)
- Forage cycle history
- Domain strategy memory

### What does NOT survive replay

- Queen notes (YAML file, external to event log)
- Escalation routing overrides (in-memory projection mutation)
- Pending config proposals (in-memory dict with TTL)
- Service query results (non-deterministic)
- Written workspace files (filesystem-only)
- LLM conversation context (only summaries persisted)
- Provider cooldown state (runtime-only)

---

## 9. A2A / AG-UI / MCP Protocol Seams

### A2A (Agent-to-Agent)

```
External agent → POST /a2a/tasks {description}
  → a2a.py: create_task()
  → spawn_colony() with default workspace/thread
  → returns task_id + status
  → External agent polls GET /a2a/tasks/{id} or attaches to SSE stream
  → On completion: GET /a2a/tasks/{id}/result → transcript + output
```

### AG-UI

```
AG-UI client → POST /ag-ui/runs {run request}
  → protocols.py: handle_agui_run()
  → AG-UI protocol handler
  → Returns AG-UI response
```

### MCP

```
MCP client → mounted at /mcp
  → FastMCP HTTP transport
  → MCP tool calls → surface/mcp_tools.py handlers
  → Same runtime methods as WS commands
```

---

## 10. Maintenance / Self-Healing Path

```
Scheduled maintenance tick
  → self_maintenance.py: MaintenanceDispatcher.evaluate()
  → proactive_intelligence.generate_briefing(projections, ws)
    → 14 deterministic rules evaluate current state
    → Returns insights with suggested_colony configs
  → MaintenanceDispatcher checks autonomy level:
    → suggest: surface only, no dispatch
    → auto_notify: dispatch opted-in categories + notify operator
    → autonomous: dispatch all eligible
  → If eligible: spawn_colony(maintenance_source="self-maintenance")
  → Budget tracking: daily reset at UTC midnight
```
