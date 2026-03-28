# FormicOS Developer Bridge

## What is FormicOS?

FormicOS is an AI agent orchestration system. It manages background work
across multiple AI agents (colonies), keeps institutional memory that
improves over time, and learns from outcomes to suggest better approaches.
Think of it as a persistent team of AI specialists that remembers what
worked and what didn't.

## Quick Start (60 seconds)

1. **Start FormicOS:**
   ```bash
   docker compose up
   ```

2. **Generate MCP config for your project:**
   ```bash
   python -m formicos init-mcp
   ```
   This creates `.formicos/mcp.json` with the connection config.

3. **Restart Claude Code** so it picks up the new MCP server.

4. **Try it:**
   Ask Claude Code: "What's the status of my workspace?" — it will use
   the `morning-status` prompt to give you a briefing.

## Daily Workflows

### Morning: What happened overnight?

Use the `morning-status` prompt to get a briefing on workspace activity,
completed colonies, knowledge changes, and pending actions.

### Working: Need institutional context?

Use `knowledge-for-context` to search what FormicOS has learned about
your codebase — conventions, bug patterns, architectural decisions.

### Delegating: Task too big for one session?

Use `delegate-task` to plan and spawn a colony of AI agents to handle it,
or `handoff-to-formicos` to transfer your current work context to a
background colony.

### Discovered something worth remembering?

Use `log-finding` to record it in institutional memory so future colonies
(and future you) benefit from it.

### End of day: Review autonomous work

Use `review-overnight-work` to see what FormicOS did autonomously — what
it dispatched, what it learned, and what needs your review.

## Available MCP Prompts

| Prompt | Purpose |
|--------|---------|
| `knowledge-query` | Search institutional memory for relevant context |
| `plan-task` | Plan a colony task with team composition |
| `morning-status` | Briefing on workspace activity and pending items |
| `delegate-task` | Plan and spawn a background colony for a task |
| `review-overnight-work` | Review autonomous actions and outcomes |
| `knowledge-for-context` | Retrieve relevant knowledge for current work |

## Key MCP Tools

### Colony Management
- `list_workspaces` — list all workspaces
- `get_status` — workspace status and active colonies
- `spawn_colony` — start a colony with a task
- `kill_colony` — stop a running colony
- `suggest_team` — get recommended team composition for a task

### Knowledge
- `log_finding` — record a finding in institutional memory
- `query_service` — query knowledge entries

### Approvals & Operations
- `approve` / `deny` — handle pending approval requests
- `get_maintenance_policy` / `set_maintenance_policy` — autonomy controls

### Addons
- `addon_status` — check addon health and call counts
- `toggle_addon` — enable/disable an addon
- `trigger_addon` — manually fire an addon trigger

### Handoff
- `handoff_to_formicos` — transfer work context to a background colony

## Available MCP Resources

| URI | Returns |
|-----|---------|
| `formicos://knowledge/{workspace}` | Knowledge entries for a workspace |
| `formicos://knowledge/{entry_id}` | Single knowledge entry detail |
| `formicos://threads/{workspace_id}` | Thread list for a workspace |
| `formicos://threads/{workspace_id}/{thread_id}` | Thread detail with colonies |
| `formicos://colonies/{colony_id}` | Colony detail with rounds and agents |
| `formicos://briefing/{workspace_id}` | Proactive intelligence briefing |
| `formicos://plan` | Project plan milestones (global) |
| `formicos://procedures/{workspace_id}` | Operating procedures |
| `formicos://journal/{workspace_id}` | Queen journal entries |

## Shared Files

FormicOS reads and writes files in your project's `.formicos/` directory:

- `.formicos/project_plan.md` — project milestones (Queen-managed)
- `.formicos/project_context.md` — project instructions for colonies
- `.formicos/operations/*/operating_procedures.md` — autonomy rules per workspace
- `.formicos/operations/*/queen_journal.md` — what FormicOS did and why

## Queen Command & Control

The Queen tab in the FormicOS UI provides direct visibility and control over
the Queen agent's behavior:

- **Display board** — structured observations with attention/urgent items
- **Active work** — continuation candidates, current goals, plan state
- **Operating procedures** — autonomy level, workspace rules
- **Behavioral overrides** — disable specific tools, inject custom rules,
  override team composition and round/budget heuristics
- **Health & budget** — trust score, tool usage counters, context budget

Behavioral overrides are workspace-scoped and stored as config fields. They
nudge the Queen's behavior without hard enforcement — the Queen sees them as
guidance in its context window.

## Architecture (for the curious)

FormicOS is event-sourced with a 4-layer architecture: Core (types, events),
Engine (pure colony execution), Adapters (LLM, vector DB, search), and
Surface (HTTP/WS/MCP wiring). Agents coordinate through shared environmental
signals (stigmergic coordination) rather than direct messaging.

Knowledge entries that prove useful gain confidence over time; unreliable
ones decay naturally. Multiple FormicOS instances can federate knowledge
with conflict-free merge semantics.

For internals, see `docs/` — architectural decision records, specs, and
subsystem documentation.
