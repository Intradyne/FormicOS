# Wave 88 Team B Prompt

## Mission

Build the first repository-hosted capability as a real shipped addon:
`Repo Activity`.

This is a hand-built addon. Its purpose is to prove the runtime thesis,
not to prove colony-authored addon generation.

## Owned Files

- `addons/repo-activity/addon.yaml`
- `src/formicos/addons/repo_activity/__init__.py`
- `src/formicos/addons/repo_activity/status.py`
- any small package-local helpers not owned by Team C
- targeted tests under `tests/unit/addons/`

## Do Not Touch

- MCP governance files owned by Team A
- repo-activity cache / refresh helper files owned by Team C
- frontend files
- runtime addon hot-load work
- service-colony persistence

## Repo Truth To Read First

1. Existing addon examples:
   - `addons/system-health/addon.yaml`
   - `src/formicos/addons/system_health/status.py`
   - `addons/codebase-index/addon.yaml`

2. Wave 87 host surface
   The panel system already supports:
   - declarative richer payloads
   - query-param passthrough
   - manifest-driven refresh intervals

3. `git-control` addon
   The repo already has a truthful local git seam:
   - `addons/git-control/addon.yaml`
   - `src/formicos/addons/git_control/status.py`
   - `src/formicos/addons/git_control/tools.py`

   Reuse its workspace-root + git subprocess pattern for local data.

4. Wave 88 phasing
   This addon is repo-authored and startup-loaded. Do not depend on
   runtime addon discovery.

## What To Build

### 1. Create the `repo-activity` addon

Add a shipped addon package under:

- `addons/repo-activity/`
- `src/formicos/addons/repo_activity/`

### 2. Build local git as the base layer

The addon must be useful even with no remote provider configured.

Use the project-bound local repository to show things like:

- current branch
- modified / uncommitted files
- recent commits
- diff summary / cleanliness

Concrete local git signals can come from commands like:

- `git branch --show-current`
- `git status --porcelain`
- `git log --oneline -n <k>`
- `git diff --stat`

This base layer should not depend on MCP or third-party uptime.

### 3. Add optional remote enrichment

When a remote MCP provider is configured, enrich the local view with
optional data such as:

- open PR / MR count
- recent PRs / MRs
- CI / workflow state
- remote branch comparison

The addon should degrade gracefully to local-only mode when:

- no MCP server is configured
- auth is unavailable
- the provider is down
- the governed gateway denies a tool

### 4. Return useful declarative dashboard payloads

Recommended panel sections:

- KPI cards:
  - local modified file count
  - recent local activity / last commit
  - open PR / MR count when remote available
  - CI health summary when remote available
- tables:
  - recent local commits
  - open PRs / MRs when remote available
- status rows:
  - last refresh
  - local repo state
  - remote provider state when configured
  - cache freshness for remote enrichment

Keep the addon focused and operator-valuable.

### 5. Route all remote calls through Team A's governed gateway

Do not call the raw bridge directly.

This addon is the first consumer of the governed MCP seam.

### 6. Integrate Team C's cache helper for remote data only

The route handler should use the shared cache / refresh helper instead of
calling the remote provider on every panel request.

Do not over-cache local git data. It is cheap and should stay live.

Reread Team C's interface before finalizing the handler.

### 7. Keep the addon read-only

No mutation actions.
No remote writes.
No action buttons that imply write capability.

### 8. Fit the existing operator surface

The panel should appear in the workspace browser alongside the existing
system-health panel.

The operator experience should feel like:

- hosted capability available on startup
- local repo data always visible
- richer remote data when configured
- no extra deployment step

## Constraints

- No hot-reload.
- No colony generation.
- No service colony backing.
- No broad provider-specific client feature sprawl.

## Validation

- `python -m pytest tests/unit/addons/test_repo_activity.py -q`

Add targeted tests for:

- manifest parses and registers
- route payload shape is valid
- local-only mode works without remote config
- remote enrichment appears when configured
- remote failure degrades to local-only instead of breaking the panel

## Overlap Note

- Team A owns the gateway / permission seam.
- Team C owns remote cache / refresh helper modules.
- You own the manifest, main handler, and capability shape.
