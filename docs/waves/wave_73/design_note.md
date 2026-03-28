# Wave 73 Design Note — The Developer Bridge

## Purpose

Wave 73 makes FormicOS usable from Claude Code. The system already has the
substrate: 19 MCP tools, 6 resources, 2 prompts, 43 Queen tools, 5 addon
REST endpoints, an operational layer with journals/procedures/action queues.
What's missing is **composition** — developer-facing workflows that compose
existing primitives into useful sequences — and **discoverability** — a way
for Claude Code to find and connect to FormicOS in 60 seconds.

## Invariants

### 1. Compose existing tools into workflows, don't duplicate

The 19 MCP tools and 6 resources already cover core operations. New prompts
compose them into developer workflows. New resources surface operational state
that's currently internal-only. No new tool should duplicate an existing
tool's capability.

Existing MCP tools (19): `list_workspaces`, `get_status`, `create_workspace`,
`create_thread`, `spawn_colony`, `list_templates`, `get_template_detail`,
`suggest_team`, `code_execute`, `kill_colony`, `chat_queen`, `create_merge`,
`prune_merge`, `broadcast`, `approve`, `deny`, `query_service`,
`activate_service`, `chat_colony`.

Existing MCP tools added in later waves (3): `set_maintenance_policy`,
`get_maintenance_policy`, `configure_scoring`.

Total existing: 22 MCP tools. (The `MCP_TOOL_NAMES` tuple at mcp_server.py:24
lists 19; the 3 Wave 35 tools are defined outside that tuple but are still
registered via `@mcp.tool()`. 19 + 3 = 22.)

Existing resources (6): `formicos://knowledge/{workspace}`,
`formicos://knowledge/{entry_id}`, `formicos://threads/{workspace_id}`,
`formicos://threads/{workspace_id}/{thread_id}`,
`formicos://colonies/{colony_id}`, `formicos://briefing/{workspace_id}`.

Existing prompts (2): `knowledge-query`, `plan-task`.

### 2. Resources return prose, not JSON

New resources (`plan`, `procedures`, `journal`) return markdown formatted for
context injection into Claude Code conversations. Existing resources keep
their current JSON contract — we don't break existing consumers. Prose
resources are new URI paths, not replacements.

### 3. `PromptsAsTools` means prompts ARE tools

Lines 730-740 of `mcp_server.py` activate FastMCP `PromptsAsTools` and
`ResourcesAsTools` transforms. Every `@mcp.prompt()` is automatically
callable as a tool. Design prompts knowing they'll be invoked both ways.
The prompt text should work as both context injection and direct response.

### 4. Frontend fixes are behavioral corrections, not new features

Hardcoded defaults that produce wrong numbers are bugs. Colony creator shows
`$2.00` budget instead of the governance-configured default. Template editor
shows `$1.00` / `5 rounds`. These are trust-destroying inaccuracies. Fixing
them is not a feature — it's trust maintenance.

## What Wave 73 does NOT do

- No new event types (stays at 69)
- No retrieval or scoring changes
- No new projection fields
- No new Queen tools (MCP tools are separate from Queen tools)
- No VS Code extension (MCP IS the extension protocol)
- No push notifications
- No automatic sync between Claude Code MEMORY.md and FormicOS knowledge
- No changes to `addon_loader.py`, `projections.py`, `events.py`, or
  `knowledge_catalog.py`

## Post-wave state

| Surface | Before 73 | After 73 |
|---------|-----------|----------|
| MCP tools | 22 | 27 (+ addon_status, toggle_addon, trigger_addon, log_finding, handoff_to_formicos) |
| MCP resources | 6 | 9 (+ plan, procedures, journal) |
| MCP prompts | 2 | 6 (+ morning-status, delegate-task, review-overnight-work, knowledge-for-context) |
| CLI subcommands | 3 (start, reset, export-events) | 4 (+ init-mcp) |
| REST endpoints | 0 workspace creation | 1 (POST /api/v1/workspaces) |
| Frontend hardcoded defaults | 6+ | 0 |

Note: `log_finding` and `handoff_to_formicos` are MCP **tools** (mutating),
not prompts. MCP prompts must be read-only — Claude Code treats them as
context injection, not safe-to-execute actions.
