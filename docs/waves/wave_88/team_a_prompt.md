# Wave 88 Team A Prompt

## Mission

Build the governed MCP seam that makes optional remote enrichment safe
enough to run inside FormicOS.

This track is not about building a generic zero-trust platform. It is
about adding a small, truthful policy layer so the repo-activity addon
can enrich local git data with remote provider data without raw
pass-through access to every MCP tool.

## Owned Files

- `src/formicos/addons/mcp_bridge/client.py`
- one new gateway / policy helper module in `src/formicos/addons/mcp_bridge/`
- `src/formicos/addons/mcp_bridge/discovery.py` only if the public addon
  tools should respect the same policy surface
- `src/formicos/surface/addon_loader.py` if an additive manifest field is
  needed for addon MCP permissions
- targeted tests under `tests/unit/addons/` and `tests/unit/surface/`

## Do Not Touch

- `addons/repo-activity/addon.yaml`
- `src/formicos/addons/repo_activity/status.py`
- repo-activity cache / refresh helper files owned by Team C
- frontend files
- service-colony persistence or hot-reload work

## Repo Truth To Read First

1. `src/formicos/addons/mcp_bridge/client.py`
   The current bridge is raw pass-through:
   - configure servers
   - connect lazily
   - list tools
   - call tools

   It does not enforce policy.

2. `src/formicos/addons/mcp_bridge/discovery.py`
   The addon-facing MCP tools currently just forward calls to the bridge.

3. `src/formicos/surface/addon_loader.py`
   Addon manifests are parsed and stored on the registration object, so
   an additive manifest field is feasible.

4. Wave 88 scope
   This is per-addon governance, not per-colony governance, and it only
   governs optional remote enrichment. The panel must remain useful
   without MCP.

## What To Build

### 1. Add a simple addon MCP permission contract

Introduce an additive manifest field for addon MCP permissions.

Recommended contract:

- server
- allowed tool list
- mode (`read`)

Keep it narrow and explicit.

### 2. Build a governed wrapper around the raw bridge

The wrapper should:

- identify which addon is calling
- resolve that addon's allowed MCP tool list
- deny disallowed calls before they reach `McpBridge.call_tool()`
- return structured failures
- log audit information for every call attempt

### 3. Enforce read-only by allowlist

Do not attempt semantic tool classification.

For this wave, explicit allowlist enforcement is enough:

- allowed read tools pass
- everything else denies

### 4. Keep server auth/config unchanged

Do not redesign credentials or server configuration.

This wave governs what tools an addon may call. It does not change how
the bridge finds servers.

### 5. Make the gateway usable from addon handlers

The repo-activity addon should be able to ask for something like:

- `list pull requests`
- `list merge requests`
- `list commits`
- `list workflow runs`

through the governed path without knowing anything about bridge internals.

## Constraints

- Read-only only. No write-side provider actions.
- No per-colony or per-thread policy engine yet.
- No new frontend work.
- No hot-reload work.

## Validation

- `python -m pytest tests/unit/addons/test_mcp_bridge.py -q`
- targeted new tests for:
  - allowed tool succeeds
  - disallowed tool denies
  - audit event/log record is emitted or recorded
  - unavailable server returns clean error

## Overlap Note

- Team B owns the repo-activity addon manifest and main handler.
- Coordinate on the exact manifest field name and gateway call shape.
- Team C depends on the final gateway shape only indirectly through Team
  B's handler integration.
