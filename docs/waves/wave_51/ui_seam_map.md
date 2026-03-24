# Wave 51: UI Seam Map

**Date:** 2026-03-20
**Scope:** End-to-end seam traces from frontend component through to backend
state, covering all major interaction paths.

---

## 1. Data Flow Architecture

```
Component  →  Custom Event / Direct Call  →  Store / WS Client  →  Backend
                                                                      ↓
Component  ←  Lit reactive property       ←  Store update       ←  Event broadcast
```

**Two mutation channels:**
- **WebSocket commands** (`ws/client.ts` → `ws_handler.py` → `commands.py`): 15 command types
- **REST endpoints** (`fetch()` → `routes/*.py`): 80+ endpoints

**One observation channel:**
- **WebSocket events** (`ws_handler.py` → store event handlers): all 62 event types broadcast to subscribed clients

**State snapshot on connect:**
- `subscribe` command → `build_snapshot()` in `view_state.py` → full `OperatorStateSnapshot` including tree, merges, threads, models, protocols, approvals

---

## 2. Queen Chat Seams

### Sending a message

```
fc-queen-chat (@keydown Enter / Send click)
  → formicos-app._handleQueenChat()
    → ws.send({ action: 'send_queen_message', workspaceId, payload: { threadId, content } })
      → commands.py handle_send_queen_message()
        → runtime.send_queen_message(threadId, content)
          → Queen processes message, spawns colonies, emits QueenMessage events
            → ws_handler broadcasts QueenMessage to subscribers
              → store handles QueenMessage: appends to queenThreads[threadId].messages
                → fc-queen-chat re-renders via Lit reactivity
```

### Structured cards (Wave 49)

```
Queen LLM response includes intent/render metadata
  → QueenMessage event carries: intent ('notify'|'ask'), render ('text'|'preview_card'|'result_card'), meta
    → store strips zero-width PARSED markers, preserves parsed flag
      → fc-queen-chat renders based on render field:
        - 'preview_card' → fc-preview-card (team, budget, template provenance)
        - 'result_card' → fc-result-card (quality, cost, entries)
        - 'text' → plain message bubble
```

### Preview → Spawn flow

```
fc-preview-card "Confirm" click
  → 'preview-confirm' custom event (bubbles up)
    → formicos-app handles: extracts meta, sends WS spawn_colony
      → commands.py handle_spawn()
        → runtime.spawn_colony() → ColonySpawned event
          → store adds colony node to tree
            → formicos-app auto-navigates to colony detail
```

### Thread creation

```
fc-queen-chat "+" tab click
  → 'new-thread' custom event
    → formicos-app: ws.send({ action: 'create_thread', payload: { name } })
      → commands.py: runtime.create_thread()
        → ThreadCreated event → store adds to queenThreads + tree
```

---

## 3. Colony Lifecycle Seams

### Spawn (via creator wizard)

```
fc-colony-creator "Launch" click
  → 'spawn-colony' custom event with { task, team, strategy, maxRounds, budgetLimit, targetFiles }
    → formicos-app: ws.send({ action: 'spawn_colony', payload })
      → commands.py: handle_spawn()
        → runtime.spawn_colony()
          → ColonySpawned → store adds colony node
          → RoundStarted → store updates round counter
          → AgentTurnStarted → store adds agent records
          → ... execution loop ...
          → ColonyCompleted/Failed → store updates status
```

### Kill colony

```
formicos-app (context menu or button)
  → ws.send({ action: 'kill_colony', payload: { colonyId } })
    → commands.py: runtime.kill_colony()
      → ColonyKilled event → store updates status to 'killed'
```

### Colony chat (operator message)

```
fc-colony-chat Send click
  → 'send-colony-message' event
    → formicos-app: ws.send({ action: 'chat_colony', payload: { colonyId, message } })
      → commands.py: colony_manager.inject_message()
        → ColonyChatMessage event → store appends to colony.chatMessages
```

### Colony export

```
fc-colony-detail export button click
  → fetch(`/api/v1/colonies/${colonyId}/export`)
    → routes/colony_io.py: build ZIP (uploads, outputs, chat, workspace_files)
      → binary ZIP response
```

### Rename colony

```
formicos-app
  → ws.send({ action: 'rename_colony', payload: { colonyId, name } })
    → commands.py: emit ColonyNamed event
      → store updates colony.displayName
```

---

## 4. Knowledge Browser Seams

### Search

```
fc-knowledge-browser search input (@input, debounced)
  → fetch(`/api/v1/knowledge/search?query=${q}&workspace=${ws}&limit=50`)
    → routes/knowledge_api.py: knowledge_catalog.search()
      → vector store + projection store → scored results
        → component renders result list
```

### Promote entry (thread → workspace)

```
fc-knowledge-browser "Promote" click
  → fetch(`/api/v1/knowledge/${id}/promote`, { body: { target_scope: 'workspace' } })
    → knowledge_api.py: emit MemoryEntryScopeChanged event
      → store handles event (if new scope == workspace)
```

### Promote entry (workspace → global) — PARTIAL

```
fc-knowledge-browser "Promote to Global" click
  → fetch(`/api/v1/knowledge/${id}/promote`, { body: { target_scope: 'global' } })
    → knowledge_api.py: attempts promotion
      → MemoryEntryScopeChanged event with new_workspace_id (planned)
        → BUT: global scope projections, retrieval, and display not landed
```

### Operator overlays (pin/mute/invalidate)

```
fc-knowledge-browser action button click
  → fetch(`/api/v1/knowledge/${id}/action`, { body: { action: 'pin', actor, reason } })
    → knowledge_api.py: emit KnowledgeEntryOperatorAction event
      → projection updates overlay state
```

### Knowledge graph

```
fc-knowledge-view graph tab
  → fetch(`/api/v1/knowledge-graph?workspace_id=${ws}`)
    → routes/api.py: build graph from KG projections
      → { nodes, edges, stats } → component renders SVG graph
```

### Library (file upload + ingest)

```
fc-knowledge-view library tab → Upload click
  → fetch(`/api/v1/workspaces/${ws}/ingest`, { formData })
    → colony_io.py: chunk + embed into workspace memory
      → { ingested: [{ name, bytes, chunks }] }
```

---

## 5. Settings / Config Seams

### Workspace model override

```
fc-workspace-config model dropdown @change
  → ws.send({ action: 'update_config', payload: { field: 'coderModel', value: 'model-address' } })
    → commands.py: emit WorkspaceConfigChanged event
      → store updates workspace config in tree
```

### Model policy edit

```
fc-model-registry policy input @change + save click
  → fetch(`/api/v1/models/${address}`, { method: 'PATCH', body: { max_output_tokens, ... } })
    → routes/api.py: update model record
      → response with updated record
```

### Caste recipe edit

```
fc-caste-editor Save click
  → fetch(`/api/v1/castes/${id}`, { method: 'PUT', body: recipe })
    → routes/api.py: update caste recipe YAML
      → updated CasteRecipe response
```

### Template CRUD

```
fc-template-editor Save click
  → fetch('/api/v1/templates', { method: 'POST', body: template })
    → routes/api.py: create template
      → ColonyTemplateCreated event (operator-authored)
```

---

## 6. Config Memory Seams (Wave 50)

### Three-endpoint fetch pattern

```
fc-config-memory refresh / mount
  → Promise.all([
      fetch(`/api/v1/workspaces/${ws}/config-recommendations`),  // proactive suggestions
      fetch(`/api/v1/workspaces/${ws}/config-overrides`),         // override history
      fetch(`/api/v1/workspaces/${ws}/templates`),                // learned + operator templates
    ])
  → Each wrapped in try/catch with silent failure (comment: "endpoint may not exist yet")
  → Renders combined view only if at least one returns data
```

**Silent failure risk:** If any endpoint returns 404 or 500, the component silently
shows partial data without indicating which data source failed.

---

## 7. Proactive Briefing Seams

```
fc-proactive-briefing refresh / mount
  → fetch(`/api/v1/workspaces/${ws}/briefing`)
    → routes/api.py: proactive_intelligence.generate_briefing()
      → 14 deterministic rules → insights array
  → fetch(`/api/v1/workspaces/${ws}/forager/cycles?limit=5`)
    → routes/api.py: projection store forage cycles
  → fetch(`/api/v1/workspaces/${ws}/forager/domains`)
    → routes/api.py: domain strategies + overrides
  → Renders insights, forage history, domain trust state
```

---

## 8. Navigation Seams

### Tree → Detail view

```
fc-tree-nav node click
  → 'node-select' custom event with { id, type }
    → formicos-app._handleNodeSelect()
      → sets selectedNode, selectedView based on node type:
        - workspace → workspace-config
        - thread → thread-view
        - colony → colony-detail
```

### Top nav → Major view

```
formicos-app tab click
  → sets selectedView directly:
    - 'queen' → fc-queen-overview
    - 'knowledge' → fc-knowledge-browser
    - 'playbook' → fc-playbook-view
    - 'models' → fc-model-registry
    - 'settings' → fc-settings-view
```

### Auto-navigation on colony spawn

```
store handles ColonySpawned event
  → formicos-app watches store.tree for new colonies
    → auto-navigates to colony-detail for newly spawned colony
```

---

## 9. WebSocket Connection Seams

### Connection lifecycle

```
formicos-app connectedCallback()
  → wsClient.connect(url)
    → WebSocket open → store.connection = 'connected'
      → formicos-app auto-subscribes all workspaces
        → ws.send({ action: 'subscribe', workspaceId })
          → commands.py: build_snapshot() → WSStateMessage { type: 'state', state: snapshot }
            → store processes snapshot: populates tree, threads, models, protocols
```

### Reconnection

```
WebSocket close/error
  → wsClient exponential backoff (up to 10 retries with jitter)
    → on reconnect: store.connection = 'connected'
      → formicos-app re-subscribes all workspaces
        → full state snapshot re-sent
```

### Event processing

```
WebSocket message received
  → wsClient.onmessage: JSON.parse
    → store.dispatch(event)
      → switch(event.type) → 40+ handlers update store state
        → Lit reactive properties trigger component re-renders
```

---

## 10. State Sources Summary

| Source | Freshness | Examples |
|--------|-----------|---------|
| **WebSocket events (live)** | Real-time | Colony status, round progress, chat messages, approvals |
| **WebSocket state snapshot** | On subscribe | Full tree, threads, models, protocols |
| **REST endpoints (on-demand)** | Request time | Knowledge search, briefings, outcomes, diagnostics, templates |
| **Replay-derived projections** | Event-sourced | Colony outcomes, forage cycles, domain strategies, overlays |
| **Optimistic local state** | Immediate | Expanded nodes, active filters, merge mode, editor state |

### Where the UI uses snapshot-only state

- Protocol status (MCP/AG-UI/A2A) — only refreshed on subscribe, not on live events
- Local models and cloud endpoints — only from snapshot, no live model-change events
- Runtime config — snapshot-only, no live config-change stream

### Where the UI uses replay-derived metadata

- Colony outcomes (`GET /api/v1/workspaces/{id}/outcomes`) — derived from events
- Knowledge confidence scores — Bayesian posteriors from MemoryConfidenceUpdated events
- Template stats (learned/operator counts) — derived from ColonyTemplateCreated events
- Forage cycle history — derived from ForageCycleCompleted events

### Where the UI makes optimistic local assumptions

- Tree node expansion state — local only, lost on refresh
- Knowledge browser filters/sort — local only
- Colony creator wizard state — local only
- Merge mode selection — local only
- Editor overlay state — local only
