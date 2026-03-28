# Wave 70.0 - Team A: MCP Bridge Substrate

**Theme:** Give the Queen a generic, healthy bridge into external MCP tool
ecosystems without hardcoding special-case routing.

## Context

Read `docs/waves/wave_70_0/wave_70_0_plan.md` first. This is a backend packet.
Your job is to land the MCP bridge substrate and the machine-readable health
seams that `70.5` will later surface.

Read `CLAUDE.md` for hard constraints.

### Key seams to read before coding

- `addon_loader.py` — `register_addon()` (line 198), `AddonRegistration`
  (line 170, fields: `health_status` property at 188, `tool_call_counts`,
  `handler_error_count`), tool wrapper (lines 239–262)
- `queen_tools.py` — `_list_addons()` (lines 4027–4053, already generic —
  iterates manifests, no addon-name branching), `_addon_tool_specs` (line 164,
  populated from `app.py:787`)
- `queen_runtime.py` — deliberation frame addon coverage (lines 1456–1495)
- `routes/api.py` — `/api/v1/addons` (lines 1295–1344, returns status from
  `reg.health_status`, tools with callCount, handlers, triggers, panels, config)
- FastMCP is `>=3.0,<4.0` (pyproject.toml line 13). Server import:
  `from fastmcp import FastMCP`. Client: `from fastmcp.client import Client`.
  Verify the Client class API against FastMCP 3.x docs — it may differ from
  2.x examples online.

## Your Files (exclusive ownership)

- `addons/mcp-bridge/addon.yaml` — **new**
- `src/formicos/addons/mcp_bridge/__init__.py` — **new**
- `src/formicos/addons/mcp_bridge/client.py` — **new**
- `src/formicos/addons/mcp_bridge/discovery.py` — **new**
- `src/formicos/surface/addon_loader.py`
- `src/formicos/surface/queen_tools.py` — `discover_mcp_tools` handler only
- `src/formicos/surface/queen_runtime.py` — deliberation frame addon coverage
  section only (lines 1456–1495)
- `src/formicos/surface/routes/api.py` — additive fields in the existing
  `/api/v1/addons` handler (lines 1295–1344) only
- `config/caste_recipes.yaml` — tool list only
- `tests/unit/addons/test_mcp_bridge.py` — **new**

## Do Not Touch

- frontend files
- `src/formicos/surface/projections.py`
- `src/formicos/core/events.py`
- `src/formicos/core/types.py`
- `src/formicos/surface/self_maintenance.py` - Team C owns
- project-plan parsing or budget code - Team B owns

## Overlap Coordination

- Team B and Team C also add tools to `queen_tools.py` and entries to
  `caste_recipes.yaml`. Keep your changes additive.
- Team B and Team C also touch `routes/api.py` to add endpoints. You only own
  the existing addon-summary route section, not new endpoint definitions.
- In `queen_runtime.py`, you only touch the addon-coverage part of the
  deliberation frame (lines 1456–1495). Team B owns project-plan injection.
  Team C does not touch this file.

---

## Track 1: MCP Bridge Addon Core

### Goal

Add a new `mcp-bridge` addon that can connect to remote MCP servers and call
their tools through the existing addon/tool infrastructure.

### Requirements

- use FastMCP `>=3.0` Client (already in deps — `from fastmcp.client import Client`).
  Verify the 3.x Client API before coding; the constructor, `list_tools()`, and
  `call_tool()` signatures may differ from 2.x blog posts
- keep the bridge as an addon, not new core architecture
- support multiple configured servers
- cache connections and track per-server health
- degrade gracefully when a server is unavailable

### Implementation Notes

- the bridge may store server configuration using the existing addon config
  path even if the underlying value is persisted as JSON; `70.5` will provide
  a real UI abstraction on top of it
- export one structured helper from `client.py`, for example
  `get_bridge_health()`, that returns connection health by server name
- do not bury health only in log text; `70.5` needs machine-readable status

---

## Track 2: Dynamic Tool Discovery

### Goal

Let the Queen discover MCP tools without hardcoding them into FormicOS.

### Requirements

- add `discover_mcp_tools` to `queen_tools.py`
- use the bridge to list remote tools and expose them in a FormicOS-friendly
  way
- if dynamic registration is supported cleanly, use it
- if not, keep the generic proxy path as the safety net

### Rule

The bridge must still work if discovery fails. Discovery is a power feature,
not a single point of failure.

---

## Track 3: Generic Bridge Health Exposure

### Goal

Make bridge state visible generically to both the Queen and future UI work.

### Requirements

**1. `_list_addons()` enhancement** (lines 4027–4053)

The method is already generic — it iterates manifests without name checks.
Do **not** add `if addon_name == "mcp-bridge"` branching. Instead:

- define a capability-based protocol: if an addon registration exposes a
  `get_bridge_health` callable (or similar) in its `runtime_context`, include
  a short health summary in `_list_addons()` text
- keep the logic capability-based, not addon-name-based

**2. Deliberation frame** (lines 1456–1495 in `queen_runtime.py`)

In the addon coverage section of the Queen deliberation frame, surface MCP
bridge status in a compact form when available:

- connected server count
- unhealthy server count
- discovered remote tool count if known

This is for Queen reasoning, not UI polish.

**3. `/api/v1/addons` summary** (lines 1295–1344 in `routes/api.py`)

The endpoint already returns per-addon: name, version, description, status,
lastError, tools (with callCount), handlers, triggers, panels, config.
Expand the payload additively so `70.5` can consume bridge health:

- add a `bridgeHealth` (or equivalent) structured field when an addon
  exposes bridge health through the capability protocol above
- no hardcoded UI-specific formatting

## Tests

Create `tests/unit/addons/test_mcp_bridge.py` with at least:

1. bridge connects to configured server
2. bridge health reports disconnected/error states cleanly
3. discovery handles unavailable server gracefully
4. `_list_addons()` includes generic bridge health text without name-based branching
5. addon summary payload exposes bridge health additively when available

## Acceptance Gates

- [ ] `mcp-bridge` addon exists and registers cleanly
- [ ] remote tool calls work through the addon path
- [ ] `discover_mcp_tools` lands as an additive Queen tool
- [ ] bridge health is structured and reusable
- [ ] `_list_addons()` uses generic logic, not `addon_name == "mcp-bridge"`
- [ ] deliberation frame can see MCP bridge status
- [ ] `/api/v1/addons` exposes bridge health additively
- [ ] no frontend changes
- [ ] no new event types

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
pytest tests/unit/addons/test_mcp_bridge.py -v
```
