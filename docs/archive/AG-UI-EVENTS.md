# AG-UI Event Reference — FormicOS

FormicOS exposes a Tier 1 AG-UI bridge at `POST /ag-ui/runs`.
This document covers the `CUSTOM` passthrough events and payload guidance
for external AG-UI clients.

## Standard AG-UI Events Emitted

| Event | Source | Notes |
|---|---|---|
| `RUN_STARTED` | Colony spawned | `runId` = colony ID |
| `RUN_FINISHED` | Colony completed/failed/killed | `status`: completed, failed, killed |
| `STEP_STARTED` | Round started | `stepId` = `{colonyId}-r{roundNumber}` |
| `STEP_FINISHED` | Round completed | |
| `TEXT_MESSAGE_START` | Agent turn started | `role` = caste name (coder, reviewer, etc.) |
| `TEXT_MESSAGE_CONTENT` | Agent turn completed | **Summary content only** — `contentType: "summary"` |
| `TEXT_MESSAGE_END` | After agent turn | |
| `STATE_SNAPSHOT` | After each round | Full colony projection snapshot |
| `CUSTOM` | All other FormicOS events | See below |

## NOT Emitted

| Event | Reason |
|---|---|
| `TOOL_CALL_START` | Runner does not emit per-tool-call start events |
| `TOOL_CALL_END` | Tool results are not available as discrete events |
| `STATE_DELTA` | No native JSON-patch delta source |
| Token streaming | Runner returns complete responses, not token streams |

## TEXT_MESSAGE_CONTENT Semantics

`TEXT_MESSAGE_CONTENT` carries `output_summary` from `AgentTurnCompleted`,
not a real-time token stream. The `contentType` field is set to `"summary"`
to make this explicit. Clients should render this as a complete message,
not as streaming text.

## CUSTOM Event Names

FormicOS passes through all internal events not mapped to standard AG-UI
events as `CUSTOM` events. The `name` field contains the FormicOS event
type. The `value` field contains the full event payload.

This list is intentionally non-exhaustive. It highlights the most useful
`CUSTOM` names for external clients and only includes event types that
exist in the live FormicOS event union.

| Custom Name | When | Payload Highlights |
|---|---|---|
| `PhaseEntered` | Colony enters a new phase within a round | `phase`, `round_number` |
| `TokensConsumed` | Agent consumes tokens | `agent_id`, `input_tokens`, `output_tokens`, `model` |
| `SkillConfidenceUpdated` | A skill's Bayesian confidence changes | `skill_id`, `new_confidence` |
| `ColonyChatMessage` | Operator or system chat message | `sender`, `content` |
| `ColonyNamed` | Colony receives a display name | `display_name` |
| `ColonyRedirected` | Queen redirects colony goal | `new_goal`, `redirect_index` |
| `CodeExecuted` | Sandbox code execution result | `exit_code`, `stdout`, `stderr`, `blocked` |
| `ApprovalRequested` | Colony requests operator approval | `approval_type`, `detail` |
| `ApprovalGranted` | Operator grants approval | `request_id` |
| `ApprovalDenied` | Operator denies approval | `request_id` |
| `QueenMessage` | Queen posts into a thread | `role`, `content` |
| `ColonyServiceActivated` | Colony activated as a service | `service_type` |
| `WorkspaceConfigChanged` | Workspace config mutated | `field`, `old_value`, `new_value` |
| `ServiceQuerySent` | Service colony query begins | `service_type`, `query_preview` |
| `ServiceQueryResolved` | Service colony query completes | `service_type`, `response_preview` |
| `MergeCreated` | Broadcast/merge edge created | `edge_id`, `from_colony`, `to_colony` |
| `MergePruned` | Merge edge removed | `edge_id`, `pruned_by` |
| `KnowledgeEntityCreated` | Knowledge graph node extracted | `entity_id`, `name`, `entity_type` |
| `KnowledgeEdgeCreated` | Knowledge graph edge extracted | `edge_id`, `from_entity_id`, `to_entity_id` |
| `KnowledgeEntityMerged` | Duplicate knowledge entities merged | `survivor_id`, `merged_id` |

### Rendering Guidance

- **Safe to ignore:** `TokensConsumed`, `PhaseEntered`, `ServiceQuerySent` - these are mostly execution telemetry.
- **Useful for dashboards:** `CodeExecuted`, `ColonyRedirected`, `ApprovalRequested`, `QueenMessage` - these represent operator-visible state changes.
- **For audit UIs:** `WorkspaceConfigChanged`, `SkillConfidenceUpdated`, `ApprovalGranted`, `ApprovalDenied` - these track system evolution.

## Request Format

```json
POST /ag-ui/runs
Content-Type: application/json

{
  "task": "Write a Python function that validates email addresses",
  "castes": [{"caste": "coder", "tier": "standard"}],
  "workspace_id": "default",
  "thread_id": "main"
}
```

All fields except `task` are optional.

**Defaults when omitted:**

| Field | Default | Notes |
|-------|---------|-------|
| `workspace_id` | `"default"` | |
| `thread_id` | `"main"` | |
| `castes` | Server-selected via `classify_task()` | Deterministic keyword classification; result depends on task content |
| `budget_limit` | Server-selected via `classify_task()` | Explicit classifier-derived budget; no silent runtime default |

When castes or budget are omitted, the server uses deterministic task
classification (same keyword heuristics as A2A) to select defaults. The
workspace-level spawn gate (`BudgetEnforcer.check_spawn_allowed()`) is
applied before spawn.

## Response Format

SSE stream with `event` and `data` fields per the AG-UI protocol.
Each `data` field is a JSON object with at minimum a `type` field
matching the event name.

## Stream Idle Behavior

If no colony event arrives for 300 seconds, the stream sends a keepalive
state snapshot and remains open. After 15 minutes of total inactivity,
the stream disconnects with an `idle_disconnect` CUSTOM event. This is a
**non-terminal** disconnect -- the underlying colony may still be
running. Clients that need to track actual colony completion should poll
the colony status after disconnect.
