# Wave 88 Team C Prompt

## Mission

Add the smallest possible refresh / cache seam that makes remote
enrichment sustainable under polling.

This is not a service-colony track. It is an in-process cache track.

## Owned Files

- `src/formicos/addons/repo_activity/cache.py`
- `src/formicos/addons/repo_activity/refresh.py` or equivalent manual
  refresh helper
- targeted tests under `tests/unit/addons/`

## Do Not Touch

- MCP governance files owned by Team A
- `addons/repo-activity/addon.yaml`
- `src/formicos/addons/repo_activity/status.py`
- frontend files
- service-colony persistence

## Repo Truth To Read First

1. Wave 87 panel refresh
   Panels can now poll using manifest-driven refresh intervals.

2. Existing addon trigger surface
   FormicOS already exposes addon triggers through the addon API and
   Queen tool surface.

3. Service colonies are not yet real persistence
   Do not try to turn this into a restart-surviving data plane.

4. Local git base layer
   The repo panel must remain useful without this cache. The cache exists
   for remote provider calls, not basic repo state.

## What To Build

### 1. Add a lightweight TTL cache helper for remote enrichment

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

### 2. Keep invalidation simple

For this wave:

- time-based expiry is enough
- restart clearing cache is acceptable
- no durable persistence required

### 3. Support manual refresh

Provide a helper that invalidates or refreshes the cache through the
existing addon trigger path.

This should allow:

- operator-triggered refresh
- Queen-triggered refresh if needed later

### 4. Make freshness visible to the addon

The cache helper should make it easy for Team B's handler to surface:

- last refresh time
- whether the current payload is cached
- last refresh error

### 5. Stay out of service-colony territory

Do not add:

- background polling loops
- auth refresh
- restart re-registration
- external durable state

## Constraints

- Keep the API small and boring.
- No new general caching subsystem outside the repo-activity addon
  package.
- No overlap edits in Team B's main handler file.

## Validation

- targeted new tests for:
  - cache miss then cache hit
  - TTL expiry causes refresh
  - manual refresh invalidates cached entry
  - cached error / freshness metadata behaves predictably
  - local-only mode does not require the cache

## Overlap Note

- Team B will consume your helper API from the addon handler.
- Coordinate on the helper function names and return shape.
- Do not edit the main repo-activity handler unless the owning team
  explicitly hands it off.
