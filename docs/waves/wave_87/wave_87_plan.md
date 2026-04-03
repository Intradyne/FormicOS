# Wave 87 Plan: Panel Zero

## Status

Dispatch-ready. Grounded in source truth as of 2026-04-01.

## Summary

Wave 86 closed the learning loop and made structural retrieval more
useful.

Wave 87 should not widen into a generic hosting platform yet. It should
prove one concrete thing:

**Can FormicOS host a living capability that the operator actually opens
every day?**

This wave makes FormicOS its own first customer by shipping a real
system-health addon mounted inside the existing host surface.

Three active tracks:

- Track A: system-health addon plus addon-route/backend plumbing
- Track B: declarative panel-surface expansion in the frontend
- Track C: runtime hardening plus capability-selection policy, so the
  Queen chooses the right instrument before reaching for colonies or
  addons

Deferred:

- service-colony backing for panel zero
- arbitrary generated component hosting
- playbook-provenance persistence and ranking
- full workstream / lifecycle architecture

## One Falsifiable Goal

After this wave ships, the operator should be able to open the workspace
browser and see a live "System Health" addon that answers, at a glance:

- how many colonies ran recently
- average quality over recent outcomes
- whether any plan patterns were auto-learned
- whether the codebase index is healthy
- how many memory entries exist

If the operator starts checking this panel instead of curling internal
routes and grepping logs, the hosted-capability thesis has passed its
first real product test.

## Verified Repo Truth

### 1. Addon routes are mounted, but request context is not passed through

`app.py` mounts a catch-all addon route at:

- `GET /addons/{addon_name}/{path}`

The matched handler is currently called as:

- `handler_fn({}, "", "", runtime_context=ctx)` or
- `handler_fn({}, "", "")`

So addon route handlers do **not** receive query params, headers,
`workspace_id`, or `thread_id` today. They do receive `runtime_context`.

### 2. `runtime_context` is already rich enough for panel zero

Addon handlers already receive runtime context with:

- `runtime`
- `projections`
- `settings`
- `data_dir`
- `mcp_bridge`
- bridge health helper

That means panel zero does not need new backend APIs just to read
FormicOS state. It can read projections directly.

### 3. Addon panel registration is currently thin

`addon_loader.py` only preserves these panel fields:

- `target`
- `display_type`
- `path`
- `addon_name`

Anything else in `panels:` is dropped today, including any potential
refresh policy.

### 4. Panel placement is real, but only as UI routing metadata

`target` is not a free-form hint. The frontend uses it to decide where a
panel mounts:

- workspace browser renders `target == "workspace"`
- knowledge browser renders `target == "knowledge"`

But this is placement metadata, not a security boundary.

### 5. The panel renderer is intentionally small right now

`addon-panel.ts` currently supports only:

- `status_card`
- `table`
- `log`

It also hardcodes a 60-second polling interval with no manifest
override.

### 6. The WebSocket snapshot is global and effectively unbounded

`view_state.py` currently includes:

- all workspaces
- all threads
- all colonies in each thread
- full colony chat messages
- full round records
- full Queen thread message history

There is no pagination or snapshot filtering today.

### 7. A quick snapshot cap is possible, but it is not the full lifecycle fix

`ThreadProjection.status` already supports `active | completed | archived`,
so archived threads can be skipped cheaply.

Colony projections already expose enough recency fields to build a
bounded recent-first slice.

That makes a practical cap possible in `view_state.py`, but it does not
replace the deeper workstream/lifecycle project.

### 8. Cold-start delegation is failing before the narrowing strategy can fully help

The current fresh-thread colony path still has two real holes:

- `_is_colony_turn` is suppressed by any `?` in the operator message
- the Queen path narrows tools, but does not yet require tool use on the
  first narrowed turn

The adapter/runtime seam already supports `tool_choice`. The missing
piece is Queen-side wiring.

### 9. The Queen has many instruments, but no explicit durability doctrine yet

`planning_policy.py` currently decides only between:

- `fast_path`
- `single_colony`
- `parallel_dag`

That is a colony-routing policy, not a full capability-selection policy.

Meanwhile `queen_tools.py` already exposes multiple different
instruments:

- inspection tools
- direct workspace mutation tools
- colony execution tools
- addon operations
- service queries

Without a doctrine, the system risks shifting from "too eager to spawn
colonies" to "too eager to build hosted things."

### 10. Panel zero can be built mostly from existing data surfaces

Existing routes already expose most of the needed data:

- `/health`
- `/api/v1/workspaces/{workspace_id}/outcomes`
- `/api/v1/workspaces/{workspace_id}/learning-summary`
- `/api/v1/workspaces/{workspace_id}/plan-patterns`
- `/api/v1/workspaces/{workspace_id}/project-binding`
- `/api/v1/addons`
- `/api/v1/system/providers`
- `/api/v1/queen-budget`
- `/api/v1/workspaces/{workspace_id}/autonomy-status`

But panel zero should prefer same-process projection reads via
`runtime_context` rather than making self-HTTP calls from the addon.

### 11. The learning-loop wiring fixes are already in source

The following are already present and should not be re-scoped as fresh
feature work:

- `tasks` / `task_previews` normalization in `plan_patterns.py`
- `parallel_groups` / `groups` fallback in `plan_patterns.py`
- relaxed `spawn_source` gate in `colony_manager.py`
- `verify_outcome` gate logging

Wave 87 should treat these as deploy-truth / smoke verification, not as
new implementation scope.

## Track A: System-Health Addon And Addon Plumbing

## Goal

Ship a real addon under the existing addon system that renders FormicOS
health and learning state inside the workspace browser.

This is the first hosted capability proof.

## Scope

### 1. Create a new addon package

Add a new addon, for example:

- `addons/system-health/addon.yaml`
- `src/formicos/addons/system_health/...`

The addon should mount into the workspace browser, not the knowledge
tab.

### 2. Keep panel zero self-contained

Panel zero should **not** depend on a service colony.

Its route handler should read from `runtime_context` directly and reshape
existing state into declarative panel JSON.

Do not implement same-process self-HTTP from the addon back into
FormicOS routes.

### 3. Provide at least two useful panel surfaces

Recommended split:

- an overview/status panel with high-frequency refresh
- a trends/details panel with slower refresh

Good data to include:

- recent colony count
- succeeded / failed counts
- average quality
- recent quality sparkline
- memory entry count
- plan-pattern counts, split by `candidate` / `approved`
- codebase-index health from project binding / sidecar truth
- addon health summary

### 4. Add query-param passthrough to addon routes

`app.py` should pass `request.query_params` through as the addon
handler's `inputs` dict.

This is required so panels can scope themselves to the active workspace
without inventing a second request path.

### 5. Add manifest-driven refresh metadata to panel registration

Add a new additive panel field:

- `refresh_interval_s`

This should be preserved in addon registration so it can reach the
frontend through the existing snapshot path.

### 6. Keep the addon payload declarative

The addon should return data shapes for the frontend renderer, not
arbitrary executable UI code.

## Owned Files

- `addons/system-health/addon.yaml`
- `src/formicos/addons/system_health/__init__.py`
- `src/formicos/addons/system_health/status.py` or equivalent handler module
- `src/formicos/surface/app.py`
- `src/formicos/surface/addon_loader.py`
- relevant addon/app tests

## Track B: Declarative Panel Surface Expansion

## Goal

Make the existing addon host surface expressive enough for a daily-use
dashboard without introducing dynamic component execution.

## Scope

### 1. Expand the declarative vocabulary in `addon-panel.ts`

Add support for a small set of richer display shapes, such as:

- `kpi_card`
- `sparkline` or inline trend strip
- grouped or status-aware tables

The implementation should stay lightweight:

- inline SVG for simple trend rendering
- no charting library
- no iframe/runtime component execution

### 2. Consume manifest-driven refresh intervals

Panels should honor `refresh_interval_s` when present instead of always
polling every 60 seconds.

The self-health addon should be able to declare different refresh
intervals for different panels.

### 3. Add workspace-scoped fetch URLs

The frontend currently fetches addon panels from a static addon path.

It should append the active workspace context, at minimum:

- `?workspace_id=<active workspace>`

for mounted workspace panels.

### 4. Preserve the current host model

Do not turn this wave into arbitrary component hosting.

The renderer still owns layout and paint. Addons return declarative data.

## Owned Files

- `frontend/src/components/addon-panel.ts`
- `frontend/src/components/workspace-browser.ts`
- `frontend/src/components/knowledge-browser.ts`
- `frontend/src/components/formicos-app.ts`
- `frontend/src/types.ts`
- `docs/contracts/types.ts`
- frontend build validation

## Track C: Runtime Hardening And Capability Selection

## Goal

Remove the two most immediate blockers to daily use:

- unbounded operator snapshots
- unreliable fresh-thread delegation

And add the missing policy doctrine so the Queen can choose among reply,
inspect, edit, execute, host, and operate instead of only choosing a
colony topology.

This track also re-verifies the already-landed learning-loop fixes.

## Scope

### 1. Extend planning policy from colony routing to capability selection

Add a higher-level capability mode to `PlanningDecision`, based on the
durability ladder:

- `reply`
- `inspect`
- `edit`
- `execute`
- `host`
- `operate`

Recommended meaning for this wave:

- `reply`: answer directly, no tool pressure
- `inspect`: prefer status/search/inspection tools
- `edit`: prefer direct workspace mutation tools
- `execute`: colony work (`fast_path`, `single_colony`, `parallel_dag`)
- `host`: durable operator-facing capability work such as dashboards or
  addon-packaged outputs
- `operate`: hosted capability + persistent/service/integration work

Important:

- this extends the existing planning-policy seam; it is not a new
  subsystem
- `route` remains the execution-mode choice inside `execute`
- `host` and `operate` are policy outputs first; they should narrow
  tools and tests now, not force a full colony-generated addon runtime in
  this wave

### 2. Add golden tests for the capability ladder

Add or extend deterministic policy tests so prompts land on the correct
instrument class, for example:

- `what's the status of the workspace?` -> `inspect`
- `fix this failing test in checkpoint.py` -> `edit` or `execute`
  depending on final thresholds, but consistently
- `audit this repo for SSRF` -> `execute`
- `build me a dashboard I'll use daily` -> `host`
- `monitor GitHub and keep the dashboard updated` -> `operate`

The point is not perfect semantic classification. The point is to encode
the doctrine before Wave 88 adds more durable primitives.

### 3. Use capability mode to scope Queen behavior in `_respond_inner()`

The Queen should not only know colony route. It should know which class
of instrument to reach for.

Use the capability mode to narrow the Queen's available tool surface
appropriately:

- `reply` -> no artificial tool pressure
- `inspect` -> status/search/inspection-biased surface
- `edit` -> workspace-biased surface
- `execute` -> colony/planning path
- `host` -> durable-capability planning path
- `operate` -> addon/service/integration-biased path

For this wave, keep this practical:

- do not invent new Queen tools just to satisfy the ladder
- use the ladder to avoid overusing the strongest available primitive

### 4. Ship the quick bounded-snapshot cap

In `view_state.py`:

- skip archived threads by default
- cap colonies per thread to a recent slice

Recommended cap for this wave:

- most recent 20 colonies per thread

Use existing projection recency fields. Do not invent the full
workstream model here.

Important:

- this is explicitly a partial operational fix
- document it as such

### 5. Fix the question-mark colony gate

Replace the current raw `?` suppression with a more truthful helper that
distinguishes:

- genuine informational questions
- polite implementation requests like "can you fix..." or
  "could you audit..."

The colony path should not depend on punctuation.

### 6. Require tool use on the first narrowed fresh-thread turn

When the Queen is on a true fresh-thread, first-turn narrowed colony path,
wire `tool_choice="required"` through the LLM call.

This should use the already-existing runtime/adapter seam.

Do not broaden this into a generic tool-choice redesign. This is a
targeted cold-start enforcement fix.

### 7. Re-verify learning-loop wiring fixes

Do not reopen already-landed learning changes unless the repo truth has
drifted.

This track should verify:

- plan-pattern field normalization still exists
- relaxed single-colony auto-learn gate still exists
- gate logging is still present

Treat these as smoke/acceptance truth, not fresh feature scope.

## Owned Files

- `src/formicos/surface/view_state.py`
- `src/formicos/surface/planning_policy.py`
- `src/formicos/surface/queen_runtime.py`
- `tests/unit/surface/test_planning_policy.py`
- `tests/unit/surface/test_routing_agreement.py`
- `tests/unit/surface/test_snapshot_fields.py`
- `tests/unit/surface/test_snapshot_routing.py`
- `tests/unit/surface/test_queen_runtime.py`
- `tests/unit/surface/test_toolset_classifier.py`
- `tests/eval/queen_planning_eval.py` if the golden prompt surface needs
  to reflect capability mode
- any small targeted tests needed for the cold-start path

## Merge Order

Recommended order:

1. Track B first or in lockstep with Track A so the new declarative panel
   shapes exist before the addon depends on them.
2. Track A next to land the actual system-health addon and the route /
   refresh plumbing.
3. Track C can land independently.

Single-owner seams:

- `queen_runtime.py`: Team C only
- `planning_policy.py`: Team C only
- `view_state.py`: Team C only
- `addon_loader.py` and addon package files: Team A only
- `addon-panel.ts`: Team B only

## What Wave 87 Does Not Do

- no service-colony backing for panel zero
- no arbitrary generated React/component execution
- no full workstream or lifecycle refactor
- no playbook-provenance persistence
- no external-data dashboard yet
- no MCP gateway redesign

## Success Criteria

Wave 87 is successful if:

1. A new workspace-mounted "System Health" addon is visible in the
   workspace browser.
2. The addon can render richer declarative shapes than
   `status_card/table/log`.
3. Addon panels can declare and honor per-panel refresh intervals.
4. Addon route handlers receive query-param inputs and can scope to the
   active workspace.
5. The default snapshot path skips archived threads and caps per-thread
   colony detail.
6. Planning policy can classify prompts across the durability ladder
   instead of only returning colony execution modes.
7. A fresh-thread polite implementation request can still enter the
   colony/tool path without being blocked by a literal `?`.
8. The Queen can require tool use on the first narrowed cold-start turn.
9. The already-landed learning-loop wiring fixes are still present and
   covered by tests or smoke verification.

## Clean-Room Acceptance

After merge, run a clean-state smoke that proves three things:

1. Panel zero mounts and refreshes.
2. The snapshot no longer balloons immediately under historical colony
   load.
3. A fresh-thread implementation request delegates even when phrased
   politely.
4. A small capability-policy golden set produces stable mode choices
   across `reply -> inspect -> edit -> execute -> host -> operate`.

The learning loop should be re-smoked on warm state, but a stochastic
`>0.7` run is evidence, not a hard acceptance gate.

## Post-Wave Decision Gate

After Wave 87:

- If the operator uses panel zero daily, proceed to panel one:
  an external-data, service-backed hosted capability.
- If panel zero does not become part of daily behavior, stop and inspect
  before investing in broader hosting/runtime work.
