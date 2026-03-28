# A2A Task Lifecycle

FormicOS exposes an inbound task lifecycle at `/a2a/tasks`. This is the
**native Colony Task API** — the first-class surface for external task
submission, not a compatibility shim.

External agents can submit tasks, poll status, attach to live event streams,
retrieve results, and cancel running work through a standard REST interface.
Under the hood, every task is a normal FormicOS colony (`task_id == colony_id`).
There is no second task store or second execution path.

## Compatibility Note

FormicOS implements a **colony-backed REST task lifecycle**, not a full
Google A2A JSON-RPC protocol. The surface is inspired by A2A semantics
(submit, poll, attach, result, cancel) but uses plain REST endpoints with
JSON payloads rather than JSON-RPC message framing.

What this means for integrators:

- **Supported:** task submission, status polling, SSE event streaming,
  transcript-backed result retrieval, task cancellation.
- **Not supported:** JSON-RPC envelope, push notifications,
  multi-turn conversation within a single task, artifact upload during
  task execution.
- **Authentication:** none by default (local-first deployment posture).
  Add a reverse proxy or middleware for production exposure.

The Agent Card at `/.well-known/agent.json` reflects this accurately.

## Endpoints

### POST /a2a/tasks

Submit a new task.

**Request:**

```json
{
  "description": "Write a Python email validator with tests"
}
```

**Response (201):**

```json
{
  "task_id": "colony-a1b2c3d4",
  "status": "running",
  "team": [
    {"caste": "coder", "tier": "standard", "count": 1},
    {"caste": "reviewer", "tier": "standard", "count": 1}
  ],
  "strategy": "stigmergic",
  "max_rounds": 10,
  "budget_limit": 2.0,
  "selection": {
    "source": "classifier",
    "template_id": null,
    "learned": false,
    "category": "code_implementation"
  }
}
```

The `selection` field shows how the team was chosen: `source` is
`"template"` or `"classifier"`, `template_id` and `learned` identify
the matched template if any, and `category` is the classified task type.

### GET /a2a/tasks

List recent A2A tasks.

**Query parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `status` | string | (all) | Filter by status: `pending`, `running`, `completed`, `failed`, `killed` |
| `limit` | int | 50 | Maximum number of tasks to return |

**Response:**

```json
{
  "tasks": [
    {
      "task_id": "colony-a1b2c3d4",
      "status": "completed",
      "progress": {
        "round": 5,
        "max_rounds": 10,
        "convergence": 0.92
      },
      "cost": 0.0342,
      "quality_score": 0.85,
      "next_actions": ["result"]
    }
  ]
}
```

### GET /a2a/tasks/{task_id}

Poll a single task's status.

**Response (200):**

```json
{
  "task_id": "colony-a1b2c3d4",
  "status": "running",
  "progress": {
    "round": 3,
    "max_rounds": 10,
    "convergence": 0.45
  },
  "cost": 0.012,
  "quality_score": 0.0,
  "next_actions": ["poll", "attach", "cancel"]
}
```

**404** if task not found.

### GET /a2a/tasks/{task_id}/events

Attach to a task's live event stream (SSE). Semantics are
snapshot-then-live-tail:

- **Running tasks:** Returns a `RUN_STARTED` event, a `STATE_SNAPSHOT` of the
  current colony state, then live AG-UI-shaped events as work progresses.
  Ends with a `RUN_FINISHED` event when the colony completes, fails, or is killed.
  If no colony event arrives for 300 seconds, the stream sends a keepalive
  state snapshot and remains open. After 15 minutes of total inactivity, the
  stream disconnects with an `idle_disconnect` CUSTOM event. This is a
  non-terminal idle disconnect -- the colony may still be running. Poll
  `GET /a2a/tasks/{task_id}` to check actual colony status.

- **Terminal tasks:** Returns `RUN_STARTED`, final `STATE_SNAPSHOT`, and
  `RUN_FINISHED` with the terminal status, then closes.

Event types follow the AG-UI Tier 1 format: `RUN_STARTED`, `RUN_FINISHED`,
`STEP_STARTED`, `STEP_FINISHED`, `TEXT_MESSAGE_START`, `TEXT_MESSAGE_CONTENT`,
`TEXT_MESSAGE_END`, `STATE_SNAPSHOT`, `CUSTOM`.

**404** if task not found.

### GET /a2a/tasks/{task_id}/result

Retrieve transcript-backed results for a completed task.

**Response (200):**

```json
{
  "task_id": "colony-a1b2c3d4",
  "status": "completed",
  "output": "...",
  "transcript": {
    "colony_id": "colony-a1b2c3d4",
    "display_name": "Email Validator",
    "original_task": "Write a Python email validator with tests",
    "status": "completed",
    "quality_score": 0.85,
    "cost": 0.034,
    "rounds_completed": 5,
    "final_output": "...",
    "team": ["..."],
    "round_summaries": ["..."]
  },
  "quality_score": 0.85,
  "skills_extracted": 2,
  "cost": 0.034
}
```

**409** if task is still running or pending.
**404** if task not found.

### DELETE /a2a/tasks/{task_id}

Cancel a running task.

**Response (200):**

```json
{
  "task_id": "colony-a1b2c3d4",
  "status": "killed"
}
```

**409** if task is already terminal (completed, failed, killed).
**404** if task not found.

## Task Status Values

| Status | Description | Next actions |
|--------|-------------|--------------|
| `pending` | Queued, not yet started | poll, attach, cancel |
| `running` | Colony executing rounds | poll, attach, cancel |
| `completed` | Finished successfully | result |
| `failed` | Colony failed | result, retry |
| `killed` | Cancelled by operator or A2A client | result, retry |

## Error Responses

All error responses use structured error envelopes:

```json
{
  "error_code": "TASK_NOT_FOUND",
  "message": "Task not found",
  "severity": "permanent",
  "category": "not_found",
  "recovery_hint": "Task ID may be wrong or colony never existed"
}
```

Common error codes: `TASK_NOT_FOUND` (404), `TASK_NOT_TERMINAL` (409),
`TASK_ALREADY_TERMINAL` (409), `INVALID_JSON` (400),
`DESCRIPTION_REQUIRED` (400).

## Deterministic Team Selection

A2A does **not** call the Queen LLM to select teams. Selection is deterministic:

1. **Template match:** If any loaded colony template has tags that overlap with
   words in the task description, that template's team/strategy/rounds/budget
   are used. Both disk-authored templates (`config/templates/*.yaml`) and
   learned templates (from successful colony completions) are consulted.
   Disk-authored templates take precedence on ID collision.

2. **Keyword heuristics:** If no template matches:
   - `review`, `audit`, `check`, `inspect` -> single reviewer, sequential, 5 rounds, $1.00
   - `research`, `summarize`, `analyze`, `explain`, `compare` -> single researcher, sequential, 8 rounds, $1.00
   - `code`, `implement`, `write`, `build`, `fix`, `debug`, `script` -> coder + reviewer, stigmergic, 10 rounds, $2.00

3. **Fallback:** coder + reviewer, stigmergic, 10 rounds, $2.00

Operator-defined templates are checked first, so customizing A2A behavior is as
simple as creating templates with appropriate tags.

## Economic Protocol

For autonomous agents that need to evaluate whether participation is
worth their tokens, FormicOS provides a machine-readable economic
layer on top of this task lifecycle. See
[A2A_ECONOMICS.md](../A2A_ECONOMICS.md) for:

- **ContributionContract** -- submitted alongside the task to specify
  sponsor, deliverables, acceptance tests, and compensation terms
- **ContributionReceipt** -- issued after completion with acceptance
  verdict, artifact hashes, and revenue-share eligibility
- **Agent Card economics** -- advertised at `/.well-known/agent.json`
  so external agents can discover compensation model and stats
- **Sponsor model** -- agents act on behalf of CLA-signing humans or
  corporations, not as independent principals

## Design Notes

- **Tasks are colonies.** `task_id == colony_id`. There is no separate task store.
- **A2A tasks live in the normal workspace** with `a2a-` prefixed thread names,
  so they have access to workspace memory and library and are visible in the
  operator UI.
- **Attach is snapshot-then-live-tail.** The `/events` endpoint first sends the
  current state, then streams live events. This means a client can submit, poll,
  and then attach at any point without missing the current state.
- **Event format is AG-UI-shaped.** Both the AG-UI SSE bridge and the A2A attach
  endpoint share the same event translator, so event shapes are identical.
- **Agent Card** at `/.well-known/agent.json` advertises A2A under `protocols.a2a`
  with accurate conformance notes and endpoint documentation.
- **No JSON-RPC.** This is a REST lifecycle, not a JSON-RPC protocol.
  If JSON-RPC wrapping is needed in the future, it will be an additive
  compatibility layer mapped onto this same colony-backed lifecycle.
- **Budget behavior.** A2A passes a per-colony `budget_limit` from template
  or classifier selection (visible in the submit response). The workspace-level
  spawn gate (`BudgetEnforcer.check_spawn_allowed()`) is applied before spawn,
  matching the Queen path's budget discipline.
- **No push notifications.** Clients must poll or attach to SSE streams.
- **Authentication.** None by default. FormicOS is designed as a local-first
  system. For external exposure, deploy behind a reverse proxy with auth.

See [ADR-038](docs/decisions/038-a2a-task-lifecycle.md) for the architectural decision.
