# Wave 88 Plan: Panel One

## Status

Dispatch-ready. Grounded in source truth as of 2026-04-01.

## Summary

Wave 87 proved that FormicOS can host a useful internal capability inside
its own surface.

Wave 88 should prove the next, harder claim:

**Can FormicOS host one operator-useful repository capability inside the
existing addon surface, using local git as the always-available base and
governed MCP as optional enrichment?**

This is the first external-data runtime proof, but it is intentionally
more robust than a GitHub-only experiment. The panel should still be
useful when:

- no MCP server is configured
- the remote provider is down
- auth is expired
- the operator uses GitLab, Gitea, Forgejo, Codeberg, or plain local git

It is intentionally narrower than "colony-generated addons" or
"hot-reloaded hosted software." The ambition in this wave is not how the
repo panel is authored. The ambition is what it proves once it is
running.

Three active tracks:

- Track A: governed MCP enrichment layer
- Track B: hand-built repo-activity addon that mounts in the existing
  host surface
- Track C: lightweight cache / refresh seam for remote enrichment

Deferred:

- colony-generated addon authoring
- runtime addon hot-load / replace
- service-colony-backed persistent data managers
- write-side MCP operations
- broader addon marketplace / generalized hosted-capability authoring

## One Falsifiable Goal

After this wave ships, the operator should be able to open FormicOS and
see two live panels in the workspace browser:

- `System Health`
- `Repo Activity`

The repo panel should show useful local repository truth such as:

- current branch
- modified / uncommitted file count
- recent commits
- diff summary

And when a remote MCP provider is configured, it should optionally add:

- open PR / MR count
- recent PR / MR list
- CI / workflow state

If the operator starts checking both panels as part of normal work,
FormicOS has crossed from "task executor with a dashboard" to "runtime
hosting useful capabilities."

## Verified Repo Truth

### 1. Addons are a real host shell, but they are still startup-loaded

`app.py` discovers and registers addons at startup via:

- `discover_addons()`
- `register_addon()`

The loader itself is reusable, but there is no true runtime
load/replace helper yet. New addon loading is relatively close.
Clean hot-reload of an existing addon is not.

Wave 88 should therefore use a hand-built addon that loads on normal app
startup, not runtime addon generation plus hot-mounting.

### 2. The minimum useful addon package is small

The simplest working addon pattern in the repo is:

- `addons/<name>/addon.yaml`
- `src/formicos/addons/<package>/__init__.py`
- one importable async handler module

`register_addon()` is forgiving: malformed pieces tend to skip
registration rather than crash the whole app.

This means colony-authored addon generation is plausible in the future,
but it does not need to be proven in this wave.

### 3. Addon handlers already get rich runtime context

Addon route handlers already receive `runtime_context`, including:

- `runtime`
- `projections`
- `settings`
- `data_dir`
- `mcp_bridge`
- bridge health helper
- `workspace_root_fn`

This is enough to build a same-process hosted capability without adding
new internal HTTP APIs.

### 4. Wave 87 already proved the host surface

The current addon surface already supports:

- mounted workspace panels
- declarative richer panel shapes
- query-param passthrough to addon route handlers
- manifest-driven refresh intervals

Wave 88 should build on those seams, not reopen them.

### 5. `McpBridge` is raw pass-through today

The existing MCP bridge:

- loads server config from settings
- lazily opens remote clients
- lists tools
- calls tools

It does **not** currently provide:

- per-addon permission scopes
- read-only enforcement
- operator approval policy
- meaningful per-call audit policy

So "governed remote enrichment" is real new work in this wave.

### 6. Service colonies are not yet persistent data managers

`activate_service()` currently turns a completed colony into a queryable
service routing target.

It does **not** provide:

- auth refresh
- polling schedules
- cached external state
- live restart recovery for colony-backed services

That gap is too large for this wave. Wave 88 should therefore use a
lightweight in-process cache, not a service-colony-backed data plane.

### 7. Workspace writes can reach the live repo only when the workspace is project-bound

`write_workspace_file` writes to the workspace runtime root:

- bound project root when present
- otherwise the workspace library root

This means a colony could eventually write addon files into the real repo
when project-bound. But Wave 88 should not depend on this.

### 8. Existing addon config and trigger seams are already available

The repo already exposes addon operations through:

- addon config endpoints
- addon trigger endpoints
- `list_addons`
- `trigger_addon`

Wave 88 should reuse those seams for repo configuration and optional
manual refresh, not invent a second control plane.

### 9. Local git is already a viable always-on substrate

The existing `git-control` addon already reads local repository state via
the project-bound workspace root and direct git subprocess calls.

That means Wave 88 does not need to depend on a third-party provider's
uptime to prove usefulness. The correct proof is:

- local git base layer always available
- optional MCP enrichment when a remote provider is configured

This also keeps the panel provider-agnostic:

- GitHub
- GitLab
- Gitea / Forgejo / Codeberg
- or no remote at all

## Track A: Governed MCP Enrichment Layer

## Goal

Insert a permissioned, read-only policy layer between addon handlers and
the raw `McpBridge`.

This track is the security and control seam that makes optional remote
enrichment acceptable to run inside FormicOS.

## Scope

### 1. Add an additive addon-side MCP policy contract

Introduce a simple manifest-level contract for addon MCP permissions.

Recommended shape:

- server name
- allowed tool list
- access mode (`read`)

Example intent:

- repo addon may call remote read / status tools
- repo addon may not call mutation tools such as issue / PR / merge
  actions

Keep the contract narrow and explicit. Do not design a generic policy
language.

### 2. Build a governed wrapper around the raw bridge

The wrapper should:

- identify which addon is calling
- resolve that addon's allowed MCP tool list
- deny disallowed calls before they reach `McpBridge.call_tool()`
- return structured failures
- log audit information for every call attempt

Recommended audit data:

- addon name
- server
- tool
- allowed / denied
- timestamp
- error summary when applicable

### 3. Keep auth and transport simple

Do not redesign how MCP servers are configured in this wave.

Server config can continue to come from settings / the existing bridge
configuration path. This wave governs tool usage, not credential
distribution.

### 4. Enforce read-only by allowlist

Do not attempt semantic tool classification.

For this wave, explicit allowlist enforcement is enough:

- allowed read tools pass
- everything else denies

### 5. Expose errors cleanly to addon handlers

Addon handlers should receive structured, usable failures rather than
opaque exceptions or raw transport traces.

Good examples:

- server unavailable
- tool not allowed for this addon
- tool timed out
- tool returned invalid data

## Owned Files

- `src/formicos/addons/mcp_bridge/client.py`
- one new gateway / policy helper module in `src/formicos/addons/mcp_bridge/`
- `src/formicos/addons/mcp_bridge/discovery.py` if the public addon tools
  need to respect the same policy surface
- `src/formicos/surface/addon_loader.py` for additive manifest-policy
  parsing if needed
- targeted tests under `tests/unit/addons/` and `tests/unit/surface/`

## Track B: Repo-Activity Addon

## Goal

Ship one hand-built repository addon that proves the runtime thesis:

**FormicOS can host a useful, operator-facing capability inside its own
surface, with local git truth always available and remote enrichment when
configured.**

## Scope

### 1. Create a real shipped addon package

Add a real addon package under:

- `addons/repo-activity/addon.yaml`
- `src/formicos/addons/repo_activity/__init__.py`
- `src/formicos/addons/repo_activity/status.py` or equivalent

This is a committed repo addon, loaded the same way as existing shipped
addons.

Do not implement runtime hot-load in this wave.

### 2. Build local git as the base layer

The addon must be useful even with no remote provider configured.

Base-layer data should come from the project-bound local repo, for
example:

- current branch
- modified / uncommitted file count
- recent commits
- diff stat / repo cleanliness
- ahead / behind or branch divergence when cheap and available

This is the uptime-safe proof surface.

The addon should reuse existing local git patterns already present in the
repo, such as the `git-control` addon's use of `workspace_root_fn` and
git subprocess calls.

### 3. Add optional remote enrichment

When a remote MCP server is configured, the addon should enrich the local
view with optional remote signals.

Recommended config:

- MCP server name
- remote provider / repository identity fields as needed

Remote enrichment examples:

- open PR / MR count
- recent PR / MR list
- workflow / CI state
- remote branch comparison

If no remote is configured, or the remote is unavailable, the addon
should degrade gracefully to local-only.

### 4. Return useful declarative dashboard payloads

Build the panel from the Wave 87 declarative vocabulary.

Recommended sections:

- KPI cards:
  - local modified file count
  - recent local activity / last commit
  - open PR / MR count when remote available
  - CI health summary when remote available
- tables:
  - recent local commits
  - open PRs / MRs when remote available
- status summary:
  - last refresh
  - local repo state
  - remote provider state when configured
  - cache freshness for remote enrichment

Keep this as a dashboard, not a generalized git hosting client.

### 5. Use the governed gateway, not the raw bridge

The addon handler should never call `McpBridge` directly.

All remote tool access should route through the governed layer from
Track A.

The addon should still function without the gateway when no remote is
configured, by falling back to local-only mode.

### 6. Keep the entire addon read-only

No mutation actions.
No remote writes.
No action buttons that imply write capability.

This wave proves visibility, graceful degradation, and usefulness, not
automation.

### 7. Fit the existing operator surface

The panel should appear in the workspace browser alongside the existing
system-health panel.

The operator experience should feel like:

- hosted capability available on startup
- local repo data always visible
- richer remote data when configured
- no extra deployment step

## Owned Files

- `addons/repo-activity/addon.yaml`
- `src/formicos/addons/repo_activity/__init__.py`
- `src/formicos/addons/repo_activity/status.py`
- any small package-local helpers not owned by Track C
- targeted tests under `tests/unit/addons/`

## Track C: Cache And Refresh Seam

## Goal

Make the repo panel sustainable under polling without introducing a
service-colony-backed persistence layer yet.

This is the seed of a future live data plane, but in this wave it should
stay intentionally small.

## Scope

### 1. Add a lightweight in-process cache helper for remote enrichment

Create a small cache helper for remote-enrichment data.

Recommended cache key dimensions:

- workspace
- remote repo target
- route / panel parameters that affect fetched remote data

Recommended cached payload:

- normalized remote panel-ready data
- fetch timestamp
- cache-hit metadata
- last error metadata when applicable

Local git data should not require this cache. It is cheap and always
available.

### 2. Keep cache policy simple and time-based

Do not invent event sourcing, durable cache replay, or distributed state.

For Wave 88:

- in-memory cache is fine
- restart clearing the cache is fine
- TTL-based invalidation is fine

The goal is to avoid hitting remote provider APIs on every 15-second
poll, not to build final persistence.

### 3. Support manual refresh through existing addon seams

Use the existing addon trigger surface where practical so the operator or
Queen can force a refresh.

A good implementation is:

- invalidate remote cache on manual trigger
- optionally warm the cache on next normal request

Do not create a second refresh control surface.

### 4. Surface freshness to the panel

The repo panel should be able to show:

- last refresh timestamp
- whether the current remote payload came from cache
- last refresh error when relevant

This is operator trust work, not just performance work.

### 5. Do not turn this into service-colony work

No auth refresh.
No polling daemon.
No restart-recovered external state.
No service-colony backing.

## Owned Files

- `src/formicos/addons/repo_activity/cache.py`
- `src/formicos/addons/repo_activity/refresh.py` or equivalent manual
  refresh helper
- targeted cache / refresh tests under `tests/unit/addons/`

## Merge Order

Recommended order:

1. Track A first, because the addon must depend on the governed MCP seam,
   not the raw bridge.
2. Tracks B and C next, in lockstep.

Single-owner seams:

- MCP governance / policy contract: Team A only
- addon manifest and main repo-activity route handler: Team B only
- repo-activity cache / refresh helper modules: Team C only

Overlap reread rule:

- Team B should reread Team C's cache helper API before finalizing the
  route handler
- Team C should not edit Team B's main handler file

## What Wave 88 Does Not Do

- no colony-generated addon authoring
- no runtime addon hot-load / replace
- no service-colony-backed external data manager
- no write-side remote actions
- no broad MCP permission system for every caller in the stack
- no generalized external dashboard framework beyond this proof case

## Success Criteria

Wave 88 is successful if:

1. A new workspace-mounted `Repo Activity` addon is visible on startup.
2. The addon is useful in local-only mode with no remote provider
   configured.
3. When a remote MCP provider is configured, the addon reads enrichment
   data through governed access, not raw bridge pass-through.
4. The addon remains read-only and denies disallowed remote tools
   cleanly.
5. The panel degrades gracefully to local-only when the remote provider
   is unavailable.
6. Repeated panel refreshes inside the TTL do not cause repeated remote
   fetches.
7. The panel surfaces freshness and recent failure state clearly enough
   for operator trust.
8. The operator can view both `System Health` and `Repo Activity`
   side-by-side as hosted capabilities inside FormicOS.

## Clean-Room Acceptance

After merge, run a clean-state or freshly restarted acceptance pass that
proves:

1. The repo-activity addon loads on startup like any other shipped
   addon.
2. The panel renders useful local git data with no remote configured.
3. When a remote is configured, the panel renders enrichment data
   without losing the local base layer.
4. A disallowed remote tool call is denied by policy before reaching the
   raw bridge.
5. Two successive panel loads inside the TTL reuse cached remote data.
6. When the remote is unavailable, the panel remains usable in local-only
   mode.
7. A manual refresh path invalidates the remote cache cleanly.
8. The panel remains usable alongside the existing system-health panel.

## Post-Wave Decision Gate

After Wave 88:

- If the operator checks both panels as part of normal work, proceed to
  colony-authored addon modification and then addon generation.
- If the panel is technically correct but not used, stop and inspect the
  product value before widening the hosted-capability surface.
- Do not jump to hot-reload or service-backed persistence until this
  repository-capability proof is actually useful.
