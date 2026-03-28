# FormicOS Addon Development Guide

Addons extend FormicOS with tools, event handlers, triggers, and UI panels
without modifying core code. The addon loader discovers YAML manifests at
startup, resolves Python handlers, and registers components into the Queen
tool dispatch, service router, and trigger scheduler.

## Quick Start: Create an Addon in 5 Minutes

```bash
# 1. Create the manifest directory
mkdir addons/my-addon

# 2. Create the addon manifest
cat > addons/my-addon/addon.yaml << 'EOF'
name: my-addon
version: "1.0.0"
description: "What this addon does"
author: "your-name"

tools:
  - name: my_tool
    description: "What this tool does"
    handler: handler.py::handle_my_tool
    parameters:
      type: object
      properties:
        query:
          type: string
          description: "Input query"
      required: ["query"]
EOF

# 3. Create the Python handler package
mkdir -p src/formicos/addons/my_addon
touch src/formicos/addons/my_addon/__init__.py

cat > src/formicos/addons/my_addon/handler.py << 'PYEOF'
"""My addon handler."""
from __future__ import annotations
from typing import Any

async def handle_my_tool(
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
) -> str:
    query = inputs.get("query", "")
    return f"Result for: {query}"
PYEOF

# 4. Restart FormicOS -- the addon loads automatically
docker compose restart formicos
```

The Queen will now see `my_tool` in her tool list. Use `list_addons` to
verify.

## Directory Layout

Addons have two parts:

```
addons/my-addon/               # Manifest (discovered at startup)
    addon.yaml                 # Manifest file (required)

src/formicos/addons/my_addon/  # Python handlers (imported at runtime)
    __init__.py
    handler.py                 # Tool/event handler implementations
```

The manifest directory name uses hyphens (`my-addon`). The Python package
uses underscores (`my_addon`). The loader resolves handler references like
`handler.py::handle_my_tool` to `formicos.addons.my_addon.handler::handle_my_tool`.

## Manifest Reference

```yaml
# addon.yaml -- all fields except name are optional
name: my-addon                   # Required. Unique addon identifier.
version: "1.0.0"                 # SemVer string.
description: "Short description" # Shown in list_addons output.
author: "your-name"              # For attribution.

# Queen tools -- registered into the Queen's tool dispatch
tools:
  - name: my_tool                # Unique tool name (snake_case)
    description: "..."           # Shown to the Queen LLM
    handler: handler.py::fn      # module::function reference
    parameters:                  # JSON Schema for tool inputs
      type: object
      properties:
        query:
          type: string
          description: "..."
      required: ["query"]

# Event handlers -- called when matching events fire
handlers:
  - event: ColonyCompleted       # Event type name (from core/events.py)
    handler: handler.py::on_done # Async function receiving the event

# Triggers -- cron schedules and manual triggers
triggers:
  - type: cron                   # cron | manual
    schedule: "0 3 * * *"        # 5-field cron (minute hour dom month dow)
    handler: handler.py::reindex # Called when schedule matches
  - type: manual
    handler: handler.py::reindex # Fired via trigger_addon Queen tool

# Frontend panels (future -- not yet wired)
panels:
  - id: my-panel
    component: panel.ts
```

## Handler Signatures

### Tool handlers

Tool handlers receive parsed inputs, workspace ID, and thread ID. They
return a string result that the Queen sees.

```python
async def handle_my_tool(
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
) -> str:
    """Handle a Queen tool call."""
    query = inputs.get("query", "")
    # Do work...
    return f"Result: {query}"
```

If the handler accepts a `runtime_context` keyword argument, the loader
injects a dict containing runtime ports:

```python
async def handle_my_tool(
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> str:
    """Handler with runtime access."""
    ctx = runtime_context or {}
    vector_port = ctx.get("vector_port")    # Qdrant vector store
    embed_fn = ctx.get("embed_fn")          # Embedding function
    workspace_root = ctx.get("workspace_root_fn")  # fn(ws_id) -> Path
    event_store = ctx.get("event_store")    # Event persistence
    settings = ctx.get("settings")          # Runtime settings
    # Use ports...
    return "done"
```

### Event handlers

Event handlers receive the event object and optional keyword context:

```python
async def on_colony_completed(
    event: Any,
    *,
    workspace_path: str | None = None,
    workspace_config: dict[str, Any] | None = None,
) -> None:
    """React to a ColonyCompleted event."""
    colony_id = getattr(event, "colony_id", "")
    # Do work...
```

### Trigger handlers

Trigger handlers are called when their schedule matches or when manually
fired via the `trigger_addon` Queen tool:

```python
async def reindex(
    *,
    runtime_context: dict[str, Any] | None = None,
) -> None:
    """Called on cron schedule or manual trigger."""
    ctx = runtime_context or {}
    # Do work...
```

## Cron Schedule Format

Five fields: `minute hour day-of-month month day-of-week`

| Field | Range | Special |
|-------|-------|---------|
| minute | 0-59 | `*`, `*/5`, `1,15,30`, `10-20` |
| hour | 0-23 | same |
| day-of-month | 1-31 | same |
| month | 1-12 | same |
| day-of-week | 0-6 | 0=Monday, 6=Sunday |

Examples:
- `"0 3 * * *"` -- daily at 3:00 AM
- `"*/15 * * * *"` -- every 15 minutes
- `"0 0 * * 0"` -- weekly on Sunday at midnight
- `"30 9 1 * *"` -- 9:30 AM on the 1st of each month

Values are validated at registration time. Out-of-range values raise
`ValueError`.

## Testing Your Addon

```python
"""tests/unit/addons/test_my_addon.py"""
import pytest
from formicos.addons.my_addon.handler import handle_my_tool


@pytest.mark.anyio()
async def test_my_tool_returns_result():
    result = await handle_my_tool(
        {"query": "test"}, "ws-1", "t-1",
    )
    assert "test" in result


@pytest.mark.anyio()
async def test_my_tool_with_runtime_context():
    from unittest.mock import MagicMock
    mock_vector = MagicMock()
    ctx = {"vector_port": mock_vector}
    result = await handle_my_tool(
        {"query": "test"}, "ws-1", "t-1",
        runtime_context=ctx,
    )
    assert result
```

Run tests:
```bash
uv run pytest tests/unit/addons/test_my_addon.py -v
```

## Conventions

1. **Tool names** use `snake_case`. Prefix with your addon name if the
   name might collide (e.g., `myapp_search` not just `search`).
2. **Handler modules** live in `src/formicos/addons/<package>/`. Never
   import from `formicos.engine` or `formicos.adapters` directly -- use
   `runtime_context` ports instead.
3. **Return strings** from tool handlers. The Queen reads these as tool
   results. Keep them concise and structured.
4. **Log with structlog**. Use `structlog.get_logger()` with addon-prefixed
   event names (e.g., `my_addon.search_complete`).
5. **No new event types** from addons. Use `ServiceTriggerFired` for
   trigger-related events. If you need a new event type, propose an ADR.
6. **Version your manifest**. Bump the version when changing tool
   signatures or handler behavior.

## Built-in Addons

| Addon | Tools | Handlers | Triggers |
|-------|-------|----------|----------|
| hello-world | `hello` | -- | -- |
| proactive-intelligence | `query_briefing` | -- | -- |
| codebase-index | `semantic_search_code`, `reindex_codebase` | -- | daily cron, manual |
| docs-index | `semantic_search_docs`, `reindex_docs` | -- | manual |
| git-control | `git_smart_commit`, `git_branch_analysis`, `git_create_branch`, `git_stash` | `ColonyCompleted` (auto-stage) | -- |
| mcp-bridge | `discover_mcp_tools`, `call_mcp_tool` | -- | -- |

## Architecture

```
Startup (app.py lifespan)
    |
    v
discover_addons()          -- scan addons/*/addon.yaml
    |
    v
register_addon()           -- for each manifest:
    |-- resolve tool handlers -> wrap with standard signature
    |-- register into queen._tool_dispatcher._handlers
    |-- register event handlers into service_router
    |-- emit AddonLoaded event
    |
    v
build_addon_tool_specs()   -- build JSON tool specs for Queen LLM
    |
    v
queen._tool_dispatcher._addon_tool_specs = specs
    |
    v
TriggerDispatcher          -- register cron/manual triggers
    |-- background task evaluates every 60s
    |-- emits ServiceTriggerFired on match
```

The addon loader wraps each handler with a closure that captures the
function reference using default parameter binding (avoiding the late-binding
closure bug). Tool handlers get the standard `(inputs, workspace_id,
thread_id)` signature. Runtime context is injected as a keyword argument
for handlers that declare it.
