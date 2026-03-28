# Wave 73 Team A: MCP Prompts + Resources + Addon Tools + init-mcp

## Mission

Make FormicOS a first-class MCP server for Claude Code. Add 4 read-only MCP
prompts for developer workflows, 2 mutating MCP tools for developer actions,
3 prose-formatted resources for operational state, 3 addon control MCP tools,
and an `init-mcp` CLI command for 60-second onboarding.

## Owned files

- `src/formicos/surface/mcp_server.py` — all new prompts, resources, tools
- `src/formicos/__main__.py` — `init-mcp` subcommand
- `src/formicos/surface/runtime.py` — add `addon_registrations` attribute (1 line)
- `src/formicos/surface/app.py` — assign `runtime.addon_registrations` (1 line)

### Do not touch

- Any frontend files
- `routes/api.py`
- `addon_loader.py`, `projections.py`, `events.py`
- `knowledge_catalog.py` (read it, don't modify it)

## Repo truth (read before coding)

### Current MCP server state (mcp_server.py, 745 lines)

1. **22 MCP tools** registered via `@mcp.tool()`:
   - Lines 59-384: 19 tools listed in `MCP_TOOL_NAMES` tuple (line 24-44):
     `list_workspaces`, `get_status`, `create_workspace`, `create_thread`,
     `spawn_colony`, `list_templates`, `get_template_detail`, `suggest_team`,
     `code_execute`, `kill_colony`, `chat_queen`, `create_merge`,
     `prune_merge`, `broadcast`, `approve`, `deny`, `query_service`,
     `activate_service`, `chat_colony`.
   - Lines 394-544: 3 Wave 35 tools NOT in the tuple but still registered:
     `set_maintenance_policy` (line 394), `get_maintenance_policy` (line 457),
     `configure_scoring` (line 483). Total: 19 + 3 = 22.

2. **6 resources** registered via `@mcp.resource()`:
   - `formicos://knowledge/{workspace}` (line 550) — JSON list, capped at 50
   - `formicos://knowledge/{entry_id}` (line 589) — single entry JSON
   - `formicos://threads/{workspace_id}` (line 611) — thread list JSON
   - `formicos://threads/{workspace_id}/{thread_id}` (line 627) — thread detail
   - `formicos://colonies/{colony_id}` (line 657) — colony detail JSON
   - `formicos://briefing/{workspace_id}` (line 721) — proactive briefing JSON

3. **2 prompts** registered via `@mcp.prompt()`:
   - `knowledge-query` (line 680) — domain + question → knowledge context
   - `plan-task` (line 696) — goal + workspace_id → planning context

4. **Transforms active** (lines 730-740): `PromptsAsTools` and
   `ResourcesAsTools` make every prompt and resource also callable as a tool.
   This means your 4 new prompts will automatically be accessible as both
   prompts AND tools from Claude Code. (The 2 mutating actions —
   `log_finding` and `handoff_to_formicos` — are registered as proper
   `@mcp.tool()` definitions, not prompts.)

5. **Tool annotations**: `_RO` (read-only), `_MUT` (mutating), `_DEST`
   (destructive) defined at lines 46-48. Use `_RO` for informational
   prompts/resources, `_MUT` for state-changing tools.

6. **Error handling**: Uses `to_mcp_tool_error(KNOWN_ERRORS[...])` pattern
   from `formicos.surface.structured_error`. Follow this for all error cases.

7. **Runtime access**: The entire server is inside `create_mcp_server(runtime)`
   — the `runtime` closure variable gives access to `runtime.projections`,
   `runtime.emit_and_broadcast()`, `runtime.spawn_colony()`,
   `runtime.create_thread()`, `runtime.colony_manager`, etc.

### Data sources you will compose

8. **`operational_state.py`** — journal & procedures:
   - `load_procedures(data_dir, workspace_id) -> str` (line 49) — raw markdown
   - `read_journal_tail(data_dir, workspace_id, max_lines=30) -> str` (line 141)
   - `parse_journal_entries(text) -> list[dict[str, str]]` (line 180)
   - `render_procedures_for_queen(data_dir, workspace_id) -> str` (line 199)
   - `render_journal_for_queen(data_dir, workspace_id, max_lines=20) -> str` (line 210)
   - `get_journal_summary(data_dir, workspace_id, max_entries=50) -> dict` (line 230)
   - Access `data_dir` via `runtime.data_dir` (or find the attribute — search
     `runtime` for `data_dir` or `_data_dir` or `settings.data_dir`).

9. **`operations_coordinator.py`** — operational summary:
   - `build_operations_summary(data_dir, workspace_id, projections=None) -> dict`
     (line 31). Returns: `workspace_id`, `pending_review_count`,
     `active_milestone_count`, `stalled_thread_count`,
     `last_operator_activity_at`, `idle_for_minutes`, `operator_active`,
     `continuation_candidates`, `sync_issues`, `recent_progress`.
   - `render_continuity_block(summary) -> str` (line 103) — compact text.

10. **`action_queue.py`** — action queue:
    - `list_actions(data_dir, workspace_id, *, status="", kind="", limit=100) -> dict`
      (line 193). Returns: `{"actions": [...], "total": N, "counts_by_status": {...}, "counts_by_kind": {...}}`.
    - Action statuses: `pending_review`, `approved`, `rejected`, `executed`,
      `self_rejected`, `failed` (lines 29-34).

11. **`project_plan.py`** — project plan:
    - `load_project_plan(data_dir) -> dict` (line 131). Returns parsed plan
      with `exists`, `goal`, `milestones`, `updated`.
    - `render_for_queen(plan) -> str` (line 157). Compact text rendering.

12. **`self_maintenance.py`** — autonomy scoring:
    - `compute_autonomy_score(workspace_id, projections) -> AutonomyScore`
      (line 176). Returns `score`, `grade`, `components`, `recommendation`.
    - `MaintenanceDispatcher._daily_spend` tracks per-workspace daily spend
      (line 278) — but this is an instance attribute, not directly accessible.
      Check if there's a public method or if autonomy-status endpoint computes
      it. Search `routes/api.py` for `autonomy-status` to find how it exposes
      this data.

13. **`knowledge_catalog.py`** — knowledge search (for `knowledge_for_context`):
    - Search for `async def search` or `async def retrieve` in this file.
    - The existing MCP tool `knowledge-query` prompt (line 680) does a simple
      domain filter. For `knowledge_for_context`, use the full retrieval
      pipeline if available, or the simpler domain-filter approach.

14. **Addon registrations** — for addon MCP tools:
    - Currently stored on `app.state.addon_registrations` (app.py:803) and
      `ws_manager._addon_registrations` (app.py:804). **NOT on `runtime`.**
    - `queen_runtime.py` already accesses them via
      `getattr(getattr(self._runtime, "app", None), "state", None)` (line 1627).
    - **Your job (Track 5):** Expose on runtime directly by adding
      `self.addon_registrations: list[Any] | None = None` to runtime.py (after
      line 493, following the pattern of `colony_manager`, `queen`,
      `memory_store`) and assigning it in app.py alongside the existing
      `app.state.addon_registrations = ...` line.
    - Then in mcp_server.py, access via `runtime.addon_registrations or []`.
    - Each `AddonRegistration` has: `.manifest` (name, version, description,
      tools, handlers, config, hidden, disabled), `.health_status`,
      `.tool_call_counts`, `.last_error`, `.disabled`.

### CLI entry point (__main__.py, 79 lines)

15. **Existing subcommands** (lines 32-35): `start`, `reset`, `export-events`.
    Both `reset` and `export-events` print "not yet implemented".
16. **Parser structure**: `argparse.ArgumentParser` with `add_subparsers(dest="command")`.
    Add `init-mcp` as a new subparser with `--url` option.
17. **Dispatch** (lines 45-54): `if args.command == "start": ...` chain.
    Add `elif args.command == "init-mcp": ...`.

## Track 1: MCP Prompts (4 read-only) + MCP Tools (2 mutating)

**Critical design rule:** MCP prompts are for context injection — they MUST
be read-only. Claude Code treats prompts as slash-command context, not as
"safe to mutate." Any action that creates events, spawns colonies, or writes
state MUST be a `@mcp.tool()` with appropriate annotations, not a prompt.

- **Prompts (read-only):** `morning-status`, `delegate-task`,
  `review-overnight-work`, `knowledge-for-context`
- **Tools (mutating):** `log_finding`, `handoff_to_formicos`

Add prompts inside `create_mcp_server()`, after the existing prompts section
(after line 715, before the briefing resource at line 721). Add the 2
mutating tools alongside the other `@mcp.tool()` definitions.

### 1a. `morning_status(workspace_id)`

```python
@mcp.prompt("morning-status")
async def morning_status_prompt(workspace_id: str) -> str:
    """Get a complete status briefing for a workspace.

    Composes: operational summary, project plan, autonomy score,
    recent colony outcomes, pending actions. Returns natural-language
    markdown suitable for starting a work session.
    """
```

Implementation:
1. Call `build_operations_summary(data_dir, workspace_id, runtime.projections)`
   from `operations_coordinator`.
2. Call `load_project_plan(data_dir)` and `render_for_queen(plan)` from
   `project_plan`.
3. Call `compute_autonomy_score(workspace_id, runtime.projections)` from
   `self_maintenance`.
4. Call `list_actions(data_dir, workspace_id, status="pending_review", limit=10)`
   from `action_queue`.
5. Get recent colony outcomes: iterate `runtime.projections.workspaces[workspace_id].threads`
   and collect colonies with `status in ('completed', 'failed')`, last 5.
6. Compose into markdown sections:

```markdown
# Status Briefing — {workspace_name}

## Operational Health
{pending_review_count} actions pending review | {continuation_candidates} continuations available
Autonomy: {grade} ({score}/100) — {recommendation}

## Project Plan
{rendered_plan or "No project plan set."}

## Pending Actions
{list of pending_review actions with title and kind}

## Recent Colony Outcomes
{list of recent completed/failed colonies with task, status, cost}

## Continuation Candidates
{list from operations summary}
```

Return the composed markdown string.

### 1b. `delegate_task(task, context?, workspace_id?)`

```python
@mcp.prompt("delegate-task")
async def delegate_task_prompt(
    task: str,
    context: str = "",
    workspace_id: str = "",
) -> str:
    """Plan a colony delegation for a task.

    Resolves workspace, suggests a team, estimates blast radius.
    Returns a delegation plan — the developer confirms before spawning.
    """
```

Implementation:
1. If `workspace_id` is empty, pick the first workspace from
   `runtime.projections.workspaces`.
2. Call `runtime.suggest_team(task)` to get caste suggestions.
3. Call `estimate_blast_radius(task)` from `self_maintenance` with defaults.
4. Compose:

```markdown
# Delegation Plan

**Task:** {task}
**Workspace:** {workspace_id}
{f"**Context:** {context}" if context else ""}

## Suggested Team
{formatted suggestions}

## Blast Radius: {level} ({score:.1f})
{factors}

## Next Steps
To spawn this colony, call the `spawn_colony` tool with:
- workspace_id: {workspace_id}
- thread_id: {suggest existing or "create a new thread"}
- task: {task}
- castes: {suggested castes as JSON}
```

### 1c. `review_overnight_work(workspace_id)`

```python
@mcp.prompt("review-overnight-work")
async def review_overnight_work_prompt(workspace_id: str) -> str:
    """Review what happened while you were away.

    Shows: recently executed actions, pending review items, new knowledge
    entries, colony outcomes from last 24h.
    """
```

Implementation:
1. `list_actions(data_dir, workspace_id, status="executed", limit=20)` —
   recently executed.
2. `list_actions(data_dir, workspace_id, status="pending_review", limit=20)` —
   pending review.
3. Recent knowledge entries: iterate `runtime.projections.memory_entries`,
   filter by workspace_id, sort by `created_at` descending, take last 10.
4. Compose into reviewable markdown with sections for each category.

### 1d. `knowledge_for_context(query, workspace_id?)`

```python
@mcp.prompt("knowledge-for-context")
async def knowledge_for_context_prompt(
    query: str,
    workspace_id: str = "",
) -> str:
    """Search institutional memory and return relevant entries as prose.

    Returns top-5 knowledge entries formatted for context injection.
    """
```

Implementation:
1. Use the knowledge search infrastructure. Check if `knowledge_catalog.py`
   has an async search method. If not, do a simpler approach: iterate
   `runtime.projections.memory_entries`, filter by workspace, do basic
   keyword matching on title + content + domains.
2. For each match, format as prose:

```markdown
## {title} (confidence: {conf:.0%})
{content[:500]}
Source: colony {source_colony} ({created_at}), status: {status}
Domains: {domains}
```

### 1e. `log_finding` — MCP TOOL, not a prompt

**This is a `@mcp.tool(annotations=_MUT)`, not a prompt.** It creates a
`MemoryEntryCreated` event — that's a state mutation. Claude Code treats
prompts as context injection (read-only). Mutating actions must be tools.

```python
@mcp.tool(annotations=_MUT)
async def log_finding(
    title: str,
    content: str,
    domains: str = "",
    workspace_id: str = "",
) -> dict[str, Any]:
    """Record a developer discovery as a knowledge entry.

    Creates a knowledge entry at 'candidate' status for operator review.
    Domains: comma-separated list (e.g., "auth,security").
    """
```

Implementation:
1. Resolve workspace (first available if empty).
2. Parse domains from comma-separated string into a list.
3. Create a `MemoryEntryCreated` event via `runtime.emit_and_broadcast()`.
   Look at how existing knowledge creation works — search for
   `MemoryEntryCreated` in `routes/api.py` or `memory_store.py` to find
   the pattern. Follow it exactly.
4. Return:

```python
return {
    "status": "recorded",
    "entry_id": entry_id,
    "title": title,
    "domains": domain_list,
    "review_status": "candidate",
    "_next_actions": ["approve", "get_status"],
}
```

### 1f. `handoff_to_formicos` — MCP TOOL, not a prompt

**This is a `@mcp.tool(annotations=_MUT)`, not a prompt.** It creates a
thread and spawns a colony — that's unambiguously a mutation. The developer
invokes it knowing it will spawn work.

```python
@mcp.tool(annotations=_MUT)
async def handoff_to_formicos(
    task: str,
    context: str,
    what_was_tried: str = "",
    files: str = "",
    workspace_id: str = "",
) -> dict[str, Any]:
    """Hand off work from the developer to FormicOS.

    Creates a thread and spawns a colony with the developer's full context
    pre-loaded so the colony doesn't repeat failed approaches.
    """
```

Implementation:
1. Resolve workspace (first available if empty).
2. Build enriched task description that includes context, what was tried,
   and relevant files. Compose as a multi-section string the colony will
   see in its task description.
3. Call `runtime.suggest_team(task)` for caste recommendations.
4. Call `estimate_blast_radius(task)` from `self_maintenance`.
5. Create thread: `thread_id = await runtime.create_thread(workspace_id, thread_name)`.
6. Spawn colony: `colony_id = await runtime.spawn_colony(workspace_id, thread_id, enriched_task, ...)`.
7. Start colony: `asyncio.create_task(runtime.colony_manager.start_colony(colony_id))`.
8. Return:

```python
return {
    "status": "handed_off",
    "colony_id": colony_id,
    "thread_id": thread_id,
    "workspace_id": workspace_id,
    "task": task,
    "blast_radius": {"level": br.level, "score": br.score},
    "_next_actions": ["get_status", "chat_colony"],
    "_context": {"colony_id": colony_id, "workspace_id": workspace_id},
}
```

## Track 2: MCP Resources (3 new)

Add after the existing resources section (after line 728, before the
transforms block at line 730).

### 2a. `formicos://plan`

**Important:** The project plan is global (one per data root), NOT per-
workspace. `load_project_plan(data_dir)` takes only `data_dir` — there is
no workspace_id parameter. The URI reflects this: `formicos://plan`, not
`formicos://plan/{workspace_id}`.

```python
@mcp.resource("formicos://plan")
async def plan_resource() -> str:
    """Project plan formatted as markdown. Global to the FormicOS instance."""
```

Implementation: call `load_project_plan(data_dir)` and
`render_for_queen(plan)`. Return the rendered markdown. If no plan exists,
return `"No project plan configured."`.

### 2b. `formicos://procedures/{workspace_id}`

```python
@mcp.resource("formicos://procedures/{workspace_id}")
async def procedures_resource(workspace_id: str) -> str:
    """Operating procedures for a workspace, formatted as markdown."""
```

Implementation: call `render_procedures_for_queen(data_dir, workspace_id)`.
If empty, return `"No operating procedures configured."`.

### 2c. `formicos://journal/{workspace_id}`

```python
@mcp.resource("formicos://journal/{workspace_id}")
async def journal_resource(workspace_id: str) -> str:
    """Recent journal entries for a workspace, formatted as markdown."""
```

Implementation: call `render_journal_for_queen(data_dir, workspace_id, max_lines=30)`.
If empty, return `"No journal entries yet."`.

## Track 3: MCP Tools for Addon Control (3 new)

Add after the existing tools section (after `chat_colony` at line 384, or
after the Wave 35 tools section at line 544).

### 3a. `addon_status(workspace_id?)`

```python
@mcp.tool(annotations=_RO)
async def addon_status(workspace_id: str = "") -> list[dict[str, Any]]:
    """List installed addons with health status, tool counts, and errors."""
```

Implementation:
1. Get addon registrations via `runtime.addon_registrations or []` (you
   exposed this in Track 5).
2. Filter out hidden addons (`manifest.hidden`).
3. Return list of dicts with: `name`, `version`, `description`, `status`
   (health_status), `disabled`, `tool_count`, `handler_count`,
   `total_tool_calls`, `last_error`.

### 3b. `toggle_addon(addon_name, disabled, workspace_id?)`

```python
@mcp.tool(annotations=_MUT)
async def toggle_addon(
    addon_name: str,
    disabled: bool,
    workspace_id: str = "",
) -> dict[str, Any]:
    """Enable or disable an addon. Disabled addons' tools return errors if called."""
```

Implementation:
1. Find the registration by name.
2. Set `reg.disabled = disabled`.
3. Persist via workspace config if runtime supports it (same pattern as
   `toggle_addon()` in `routes/api.py` at line 1521).
4. Return `{"addon": addon_name, "disabled": reg.disabled}`.

### 3c. `trigger_addon(addon_name, handler, inputs?, workspace_id?)`

```python
@mcp.tool(annotations=_MUT)
async def trigger_addon(
    addon_name: str,
    handler: str,
    inputs: dict[str, Any] | None = None,
    workspace_id: str = "",
) -> dict[str, Any]:
    """Trigger an addon handler (e.g., reindex). Same as the REST trigger endpoint."""
```

Implementation:
1. Find the registration.
2. Check disabled.
3. Resolve handler function from the registration's registered_handlers or
   manifest triggers. Follow the same pattern as `trigger_addon()` in
   `routes/api.py` at line 1427 — read that function carefully.
4. Call with `(inputs or {}, workspace_id, "")` if handler expects positional
   args, otherwise call with just runtime_context.
5. Return `{"result": str(result)}`.

## Track 4: `init-mcp` CLI Command

### 4a. Add subparser

In `__main__.py`, after line 35 (`export-events` subparser):

```python
init_mcp = subs.add_parser(
    "init-mcp",
    help="Generate MCP config for Claude Code integration",
)
init_mcp.add_argument(
    "--url",
    default="http://localhost:8080/mcp",
    help="FormicOS MCP server URL (default: http://localhost:8080/mcp)",
)
```

### 4b. Add dispatch

After line 54, add:

```python
elif args.command == "init-mcp":
    _init_mcp(url=args.url)
```

### 4c. Handler function

```python
def _init_mcp(url: str = "http://localhost:8080/mcp") -> None:
    """Generate .mcp.json and .formicos/DEVELOPER_QUICKSTART.md.

    Two files serve different audiences:
    - `.mcp.json` — Claude Code MCP server config (machine-consumed)
    - `.formicos/DEVELOPER_QUICKSTART.md` — project-local quickstart for
      developers using this specific project with FormicOS. This is distinct
      from `docs/DEVELOPER_BRIDGE.md` in the FormicOS repo itself, which is
      the contributor-facing guide maintained by Team C.
    """
    import json
    from pathlib import Path

    cwd = Path.cwd()

    # Write .mcp.json
    mcp_config = {
        "mcpServers": {
            "formicos": {
                "type": "http",
                "url": url,
            }
        }
    }
    mcp_path = cwd / ".mcp.json"
    mcp_path.write_text(json.dumps(mcp_config, indent=2) + "\n")
    print(f"  Created {mcp_path}")

    # Write .formicos/DEVELOPER_QUICKSTART.md
    bridge_dir = cwd / ".formicos"
    bridge_dir.mkdir(exist_ok=True)
    bridge_path = bridge_dir / "DEVELOPER_QUICKSTART.md"
    bridge_path.write_text(_BRIDGE_TEMPLATE.format(url=url))
    print(f"  Created {bridge_path}")

    print()
    print("FormicOS MCP integration configured.")
    print("Restart Claude Code to connect. Then try:")
    print("  morning-status — get a complete briefing")
    print("  delegate-task — hand off work to FormicOS")
    print("  knowledge-for-context — search institutional memory")
```

### 4d. Bridge template

Define `_BRIDGE_TEMPLATE` as a module-level string constant above `main()`:

```python
_BRIDGE_TEMPLATE = """\
# FormicOS Developer Bridge

This project uses FormicOS for institutional memory, strategic delegation,
and autonomous background work. FormicOS MCP server: {url}

## MCP Prompts (context injection — read-only)

- **morning-status** — What happened, what's pending, project plan status
- **delegate-task** — Plan a colony to handle a task, get blast radius estimate
- **review-overnight-work** — Review autonomous actions, pending approvals, new knowledge
- **knowledge-for-context** — Search institutional memory for relevant entries

## MCP Tools (actions — may mutate state)

- `spawn_colony` — Create and start a colony directly
- `chat_queen` — Message the Queen for strategic guidance
- `get_status` — Workspace status with threads and colonies
- `approve` / `deny` — Review pending actions
- `log_finding` — Record a discovery as a knowledge entry
- `handoff_to_formicos` — Transfer work context to a new colony
- `addon_status` — Check installed addon health
- `toggle_addon` — Enable/disable addons
- `trigger_addon` — Run addon handlers (reindex, etc.)

## MCP Resources

- `formicos://plan` — Project plan (global)
- `formicos://procedures/{{workspace_id}}` — Operating procedures
- `formicos://journal/{{workspace_id}}` — Recent journal entries
- `formicos://knowledge/{{workspace}}` — Knowledge catalog
- `formicos://briefing/{{workspace_id}}` — Proactive intelligence briefing

## Shared Files

- `.formicos/project_plan.md` — Milestones (both you and FormicOS read/write)
- `.formicos/project_context.md` — Project instructions for colonies
- `.formicos/operations/*/operating_procedures.md` — Autonomy rules
- `.formicos/operations/*/queen_journal.md` — What FormicOS did (read-only)
"""
```

## Track 5: Expose `addon_registrations` on runtime (prerequisite for Track 3)

This is 2 lines of code but without it, the addon MCP tools have no clean
path to registrations from inside `mcp_server.py`.

### 5a. In `runtime.py`

After line 493 (where `self.memory_store: Any = None` is defined), add:

```python
# Set by app.py after addons are registered (Wave 64)
self.addon_registrations: list[Any] | None = None
```

This follows the exact pattern of `colony_manager`, `queen`, `memory_store` —
all lazy-assigned from `app.py` after construction.

### 5b. In `app.py`

Search `app.py` for where `_addon_registrations` is used after the
registration loop. You should find it assigned to `app.state` and/or
`ws_manager`. **Ensure both of these assignments exist** (add whichever
is missing):

```python
app.state.addon_registrations = _addon_registrations  # type: ignore[attr-defined]
runtime.addon_registrations = _addon_registrations  # type: ignore[attr-defined]
```

If `app.state.addon_registrations` is not already there, add it — the
WebSocket snapshot path (`build_snapshot()` in `view_state.py`) needs it
for the addons tab, and the REST addon endpoints in `routes/api.py` access
it via `request.app.state.addon_registrations`. Without it, the addons tab
shows empty and the toggle/trigger endpoints 404.

Belt and suspenders: both `app.state` and `runtime` get the same list
reference. `app.state` serves HTTP handlers and the WS snapshot. `runtime`
serves the MCP server closure.

## Finding the `data_dir`

Several data sources require `data_dir` as first argument. The answer:

```python
data_dir = runtime.settings.system.data_dir
```

Confirmed at `runtime.py:651` where `runtime.create_workspace()` uses this
exact path. All `operational_state`, `action_queue`, and `project_plan`
helpers accept this string.

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Verify MCP tool count by adding the new tools to `MCP_TOOL_NAMES` tuple
(line 24) or verify they're still registered without being in the tuple
(the Wave 35 tools aren't in the tuple but work fine).

## Acceptance criteria

- [ ] 4 read-only MCP prompts registered: morning-status, delegate-task, review-overnight-work, knowledge-for-context
- [ ] 2 mutating MCP tools registered: `log_finding` (annotations=_MUT), `handoff_to_formicos` (annotations=_MUT)
- [ ] 3 new MCP resources return prose-formatted markdown (plan is global URI, not per-workspace)
- [ ] 3 addon control MCP tools work: addon_status, toggle_addon, trigger_addon
- [ ] `runtime.addon_registrations` exposed (runtime.py + app.py, 2 lines)
- [ ] `python -m formicos init-mcp` generates `.mcp.json` with `"type": "http"` (NOT "url")
- [ ] `.formicos/DEVELOPER_QUICKSTART.md` generated by init-mcp (project-local onboarding)
- [ ] `morning-status` composes data from 4+ sources into a coherent briefing
- [ ] `delegate-task` suggests team, estimates blast radius, provides spawn instructions
- [ ] `handoff_to_formicos` actually creates thread + colony with developer context
- [ ] `log_finding` creates a knowledge entry via proper event path
- [ ] All new code follows existing error handling patterns (`to_mcp_tool_error`)
- [ ] No import of frontend, addon_loader, or projection code that violates layers
- [ ] All tests pass, no ruff/pyright errors
