# Wave 51: Backend Audit Findings

Audit date: 2026-03-20. Findings ordered by severity.

---

## Blockers

None identified. The backend capability surface is coherent and the event-sourced
substrate is consistent.

---

## Substrate-Truth Debt

### S1. `escalate_colony` routing override is NOT replay-safe (HIGH)

**File**: `queen_tools.py` ~L1768-1825

The `escalate_colony` Queen tool sets `colony.routing_override` directly on the
in-memory projection without emitting an event. This means:

- Escalation is lost on server restart
- Escalation does not appear in replay
- Colony audit view references the override but it won't exist after replay

**Evidence**: No event emission in handler; `routing_override` is set as a dict
on the projection object directly.

**Fix**: Add `ColonyEscalated` event to the closed union (requires ADR), or
encode escalation in an existing event (e.g. ColonyChatMessage metadata).

### S2. `save_queen_note` (WS command) is NOT replay-safe (HIGH)

**File**: `commands.py` L268-279

Notes are stored in the Queen object's in-memory `thread_notes` dict. They do
not survive restart or replay. The Queen tool `queen_note` uses a YAML file
which is better but still external to the event log.

**Evidence**: No event emitted; stored in `self._queen.thread_notes`.

### S3. `queen_note` tool uses YAML persistence, not event log (MEDIUM)

**File**: `queen_tools.py` ~L2054-2080

The `queen_note` tool persists to `queen_notes.yaml` files per-thread. This is
better than pure in-memory but:

- Not event-sourced (no QueenNoteAdded event)
- Not replayed from event stream
- YAML corruption would lose notes silently
- Not visible in projection state

### S4. `suggest_config_change` proposals are ephemeral (MEDIUM)

**File**: `queen_tools.py` ~L1563-1621

Pending config proposals are stored in an in-memory dict with 5-minute TTL.
If the server restarts between proposal and approval, the proposal is lost.
This is acceptable for the TTL window but the operator receives no notification.

### S5. `write_workspace_file` is not event-sourced (LOW)

**File**: `queen_tools.py` ~L1954-2000

Files written by the Queen tool exist only on the filesystem. This is acceptable
for ephemeral outputs but there is no event trail for what the Queen wrote.

---

## Surface-Truth Debt

### F1. Deprecated Memory API still present (MEDIUM)

**File**: `routes/memory_api.py`

Three endpoints (`/api/v1/memory`, `/api/v1/memory/search`, `/api/v1/memory/{id}`)
still exist and return data with deprecation warnings. The Knowledge API
(`/api/v1/knowledge/*`) is the intended replacement.

**Risk**: External integrations may still target the deprecated endpoints.
**Recommendation**: Add `Sunset` headers, log usage, plan removal.

### F2. `dismiss-autonomy` is memory-only (MEDIUM)

**File**: `routes/api.py` — `post_dismiss_autonomy()`

Dismissing autonomy recommendations is stored only in OperatorOverlays memory.
It is NOT event-sourced. A server restart would un-dismiss all recommendations.

**Evidence**: No event emitted; stored in `overlays.dismissed_categories`.

### F3. Knowledge `config-override` has two routes (LOW)

**Files**: `routes/api.py` L(`post_config_override`) and `routes/knowledge_api.py`
L(`override_config_suggestion`)

Both emit `ConfigSuggestionOverridden` events but via different paths. The API
route accepts `dimension`/`original`/`overridden`; the knowledge route accepts
`suggestion_category`/`original_config`/`overridden_config`. Same event, different
parameter names.

**Recommendation**: Consolidate to one route or document both as intentional.

### F4. Agent Card is dynamic but not versioned (LOW)

**File**: `routes/protocols.py` — `agent_card()`

The `/.well-known/agent.json` endpoint returns a dynamic Agent Card built from
live state (skills, domains, threads, federation, hardware). There is no
versioning or cache control. External agents may cache stale capabilities.

### F5. Colony export ZIP has no streaming (LOW)

**File**: `routes/colony_io.py` — `export_colony()`

ZIP is generated fully in memory before returning. Large colonies with many
artifacts could cause memory pressure. Not a blocker for current usage.

---

## Runtime/Deployment Debt

### D1. LLM streaming has no fallback (MEDIUM)

**File**: `runtime.py` — `LLMRouter.stream()`

The `stream()` method delegates directly to the resolved adapter without
implementing the fallback chain. If the primary provider fails during streaming,
the call fails entirely. `complete()` has full fallback support.

### D2. Local model probe is best-effort (LOW)

**File**: `view_state.py` — `_probe_local_endpoints()`

The local model health probe calls llama.cpp `/health` and `/metrics` endpoints
with httpx. If llama.cpp is down or slow, the probe returns stale/empty data.
The UI shows "unknown" status but doesn't clearly indicate probe failure.

### D3. File upload whitelist is hardcoded (LOW)

**File**: `routes/colony_io.py`

Allowed extensions (.txt, .md, .py, .json, .yaml, .yml, .csv) and size limits
(10MB per file, 50MB per colony) are hardcoded. Not configurable per workspace.

---

## Docs Debt

### X1. No single canonical capability reference (HIGH)

The backend has 15 WS commands, 60+ REST routes, 21+ Queen tools, and 19
projection classes, but no single reference document lists them all. Frontend
developers, external integrators, and operators must read source code.

**This audit is the first such document.**

### X2. Deprecated vs. current endpoint mapping missing (MEDIUM)

Memory API → Knowledge API migration has no explicit mapping document. External
consumers need a clear "use X instead of Y" reference.

### X3. Replay-safety classification not documented (MEDIUM)

No existing document classifies which capabilities are replay-safe vs.
runtime-only. The distinction matters for operators reasoning about restart
behavior.

---

## Hidden / Frozen / Stale Capabilities

### H1. `ContextUpdated` event exists but has no projection handler

**File**: `core/events.py`

The event type exists in the closed union but no projection handler processes it.
It may be a historical artifact from early development.

### H2. `SkillConfidenceUpdated` and `SkillMerged` are legacy

**File**: `core/events.py`

These events predate the unified MemoryEntry system (Wave 26+). They exist in
the union for replay compatibility with old event logs. New code uses
`MemoryConfidenceUpdated` and `MemoryEntryMerged` respectively.

### H3. `DeterministicServiceRegistered` is a no-op

**File**: `projections.py`

The handler for this event exists but does nothing meaningful — it's an audit
marker. The actual service registration happens via `ColonyServiceActivated`.

### H4. `ServiceQuerySent` / `ServiceQueryResolved` are audit-only

**File**: `core/events.py`

These events are emitted for audit trail purposes but the projection handlers
only increment counters. No behavioral logic depends on them.

---

## Naming / Taxonomy Observations

### Current implicit groupings

| Category | Capabilities |
|----------|-------------|
| **Orchestration** | spawn_colony, spawn_parallel, kill_colony, redirect_colony, escalate_colony, broadcast, create_merge, prune_merge |
| **Knowledge** | memory_search, knowledge list/search/get, promote, feedback, annotations, overlays |
| **Templates** | list_templates, inspect_template, workspace templates, ColonyTemplateCreated/Used |
| **Configuration** | update_config, suggest_config_change, approve_config_change, config-recommendations, config-overrides |
| **Governance** | approve, deny, check_spawn_allowed, budget_summary, hard_stop |
| **Workflow** | set_thread_goal, complete_thread, archive_thread, define_workflow_steps |
| **Maintenance** | briefing, maintenance dispatcher, proactive intelligence, self-maintenance |
| **Foraging** | forage trigger, domain override, cycles, domain strategies |
| **Files** | workspace files, colony files, upload, ingest, export |
| **Observability** | get_status, inspect_colony, read_colony_output, audit view, timeline, transcript |
| **Protocols** | A2A tasks, AG-UI runs, MCP mount, Agent Card |

### Naming inconsistencies

- WS uses `chat_colony`, Queen tool uses `redirect_colony` — both inject into
  colony context but via different mechanisms
- REST uses `/knowledge/{id}/action` for pin/mute/invalidate — "action" is
  generic and could be confused with other operations
- Template routes split between `/api/v1/templates` (operator) and
  `/api/v1/workspaces/{ws}/templates` (operator + learned) — the workspace
  route is a superset
- "memory" vs "knowledge" naming split: deprecated API uses "memory", current
  uses "knowledge", projections use "memory_entries"

---

## Top 10 Findings Summary

| # | Finding | Severity | Category |
|---|---------|----------|----------|
| 1 | `escalate_colony` not replay-safe (no event) | High | Substrate |
| 2 | `save_queen_note` (WS) not replay-safe | High | Substrate |
| 3 | No single backend capability reference doc | High | Docs |
| 4 | `queen_note` tool uses YAML, not event log | Medium | Substrate |
| 5 | Deprecated Memory API still present | Medium | Surface |
| 6 | `dismiss-autonomy` is memory-only | Medium | Surface |
| 7 | LLM streaming has no fallback | Medium | Runtime |
| 8 | Replay-safety classification undocumented | Medium | Docs |
| 9 | Config override has two routes with different param names | Low | Surface |
| 10 | 3 legacy/frozen event types with no behavioral handlers | Low | Substrate |

---

## Capabilities Clearly Replay-Safe and Operator-Real

These capabilities are fully event-sourced, survive restart, and are exposed
to the operator via at least one surface (WS, REST, or Queen tool):

- Workspace/thread/colony lifecycle (create, spawn, kill, complete, archive)
- Colony redirection (ColonyRedirected event)
- Knowledge creation, status transitions, confidence updates, scope promotion
- Operator co-authorship (pin, mute, invalidate, annotate)
- Config changes (WorkspaceConfigChanged, ModelAssignmentChanged)
- Template creation and usage tracking
- Merge topology (create, prune, broadcast)
- Workflow steps and thread goals
- Parallel plan creation (DelegationPlan DAG)
- Forager cycles and domain strategy
- Approval requests and grants/denials
- Colony outcome intelligence (derived projections)

## Capabilities That Are Partial/Hidden/Frozen

| Capability | Issue |
|------------|-------|
| `escalate_colony` | Shipped, operator-real, but NOT replay-safe |
| `queen_note` | Shipped, operator-real, but NOT event-sourced |
| `save_queen_note` (WS) | Shipped but NOT replay-safe at all |
| `dismiss-autonomy` | Runtime-only, lost on restart |
| `suggest_config_change` proposals | Ephemeral (5min TTL, in-memory) |
| `write_workspace_file` | Filesystem-only, no event trail |
| `query_service` | Non-deterministic, results not persisted |
| `ContextUpdated` event | No projection handler (historical artifact) |
| `SkillConfidenceUpdated/SkillMerged` | Legacy compatibility, superseded |
| `DeterministicServiceRegistered` | No-op audit marker |
| Memory API (`/api/v1/memory/*`) | Deprecated, still serving with warnings |
