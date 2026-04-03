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
   This creates `.mcp.json` (project-scoped MCP config) and
   `.formicos/DEVELOPER_QUICKSTART.md` with usage reference.

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
| `economic-status` | Economic overview: billing, receipts, revenue share |
| `review-task-receipt` | Review the economic receipt for a completed task |

## Key MCP Tools

### Colony Management
- `list_workspaces` — list all workspaces
- `get_status` — workspace status and active colonies
- `spawn_colony` — start a colony with a task
- `kill_colony` — stop a running colony
- `suggest_team` — get recommended team composition for a task

### Knowledge
- `log_finding` — record a finding in institutional memory
- `search_knowledge` — search institutional memory using full retrieval pipeline
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

### Economic
- `get_task_receipt` — get a deterministic receipt for completed A2A work

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
| `formicos://billing` | Current-period billing status |
| `formicos://receipt/{task_id}` | Deterministic receipt for a completed task |

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

## Economic Participation

FormicOS tracks the economics of agent work through A2A task contracts and
receipts:

- **Task contracts** — when submitting work via A2A, include an optional
  `contract` describing acceptance criteria and sponsorship
- **Task receipts** — completed tasks produce deterministic receipts with
  cost, token totals, quality scores, and transcript hashes
- **Revenue share** — receipts include eligibility status based on sponsor
  verification in `.formicos/sponsors.json`

From Claude Code, use `get_task_receipt` to inspect receipts for completed
work. See `docs/A2A_ECONOMICS.md` for the full protocol specification.

## Claude Desktop Setup

FormicOS supports multiple MCP clients simultaneously. Both Claude Code and
Claude Desktop can connect to the same running FormicOS server at the same
time -- they share the same workspaces, knowledge, and Queen.

### Claude Code

```bash
python -m formicos init-mcp
# Creates .mcp.json and .formicos/DEVELOPER_QUICKSTART.md
# Restart Claude Code to connect
```

### Claude Desktop

Claude Desktop connects to local MCP servers via `claude_desktop_config.json`.
FormicOS is an HTTP MCP server, so it needs the `mcp-remote` bridge (a
lightweight npm package that translates between Claude Desktop's stdio
transport and FormicOS's HTTP transport).

**Prerequisites:** [Node.js](https://nodejs.org/) (for `npx`).

1. Open Claude Desktop > Settings > Developer > Edit Config
   (or manually edit the config file):
   - **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
   - **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

2. Add FormicOS:

```json
{
  "mcpServers": {
    "formicOSa": {
      "command": "npx",
      "args": ["mcp-remote", "http://localhost:8080/mcp"]
    }
  }
}
```

Or generate the snippet from the CLI:

```bash
python -m formicos init-mcp --desktop
```

3. Restart Claude Desktop. Look for the hammer icon in the chat input --
   that confirms the MCP tools are loaded.

4. Test: Ask Claude to call `get_status` or try the `morning-status` prompt.

Both Claude Code and Claude Desktop connect to the same FormicOS instance
and share the same workspaces, knowledge, and Queen.

## Populating Institutional Memory from Claude Desktop

Use `log_finding` from Claude Desktop to record discoveries in institutional
memory. This is the primary ingestion path for developer-sourced knowledge.

**Tool signature:**
```
log_finding(title, content, domains, workspace_id)
```

- `title` -- short descriptive name for the finding
- `content` -- the full text of the finding
- `domains` -- comma-separated domain tags (e.g., `"auth,security"`)
- `workspace_id` -- target workspace; defaults to the first workspace if omitted.
  Specify explicitly for bulk operations to avoid ambiguity.

Entries are created at `candidate` status with `decay_class="stable"` and
balanced priors (`Beta(5, 5)`). They require operator confirmation via the
Operations inbox to become `verified`. Until confirmed, entries participate
in retrieval but with a status penalty in the scoring formula.

Use `search_knowledge` to retrieve entries after population. It uses the
full 7-signal retrieval pipeline (semantic, Thompson sampling, freshness,
status, co-occurrence, graph proximity, thread bonus).

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
