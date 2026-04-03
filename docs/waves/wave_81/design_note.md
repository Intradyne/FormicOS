# Wave 81 Design Note: Real Workspace Truth

## Theme

Wave 81 should move FormicOS from synthetic workspace truth to real
workspace truth.

That means three things ship together:

1. the runtime works against a real project root
2. the operator can see that truth in the UI
3. runtime bugs stop hiding behind misleading summaries

This wave is not just a mount. It is the point where FormicOS starts
working on real code and showing the operator what is actually
happening.

## Verified Repo Truth

This packet is grounded in the live repo as of 2026-03-30.

- Addons already have a central workspace-root seam.
  `src/formicos/surface/app.py` injects `workspace_root_fn` into addon
  runtime context, but today it always resolves to
  `data/workspaces/{id}/files`.
- The existing workspace library is real and already used by the UI.
  `frontend/src/components/workspace-browser.ts` and
  `src/formicos/surface/routes/colony_io.py` use
  `/api/v1/workspaces/{id}/files` for uploaded/shared files.
  That surface should not be silently repurposed into "the bound host
  project."
- Codebase indexing is already wired to `workspace_root_fn`.
  `src/formicos/addons/codebase_index/search.py`,
  `src/formicos/addons/codebase_index/indexer.py`, and
  `src/formicos/addons/codebase_index/status.py` already expect a root
  function and a vector port. Once the root is truthful, the addon path
  becomes useful immediately.
- The Queen planning brief already reads workspace structure through
  `src/formicos/surface/planning_brief.py`. Today that structure comes
  from the workspace files tree, which is usually colony output or a
  sparse library, not the operator's real project.
- Parallel-plan generation is no longer the main failure.
  Recent runs proved the Queen can generate a correct 5-task, 2-group
  plan. The runtime bug is that `spawn_parallel` in
  `src/formicos/surface/queen_tools.py` dispatches later groups
  immediately, while `Runtime._resolve_input_sources()` in
  `src/formicos/surface/runtime.py` only accepts completed source
  colonies. Group 2 therefore fails before it ever becomes runnable.
- The UI already contains the right surfaces, but not enough truth.
  `workspace-browser.ts`, `settings-view.ts`, `queen-overview.ts`,
  `fc-preview-card.ts`, and `fc-result-card.ts` already exist. The
  operator still had to go to logs because those components do not show
  project binding, blocked groups, or benchmark truth clearly enough.

## Product Stance

Wave 81 should be pragmatic, not overbuilt.

- Use `PROJECT_DIR` as the v1 bootstrap for a real project root.
- Keep the existing workspace library as a separate surface.
- Treat UI as part of the control plane, not as polish.
- Fix runtime truth and UI truth in the same wave.
- Do not jump all the way to the full Wave 83 planning workbench yet.

The resulting model is:

- `Project Root`
  Real code the Queen and colonies act on when bound.
- `Workspace Library`
  Uploaded/shared files already exposed through `/files`.
- `Working Memory`
  AI runtime state.
- `Artifacts`
  Durable colony outputs.

That separation is more truthful than overloading one tree and calling
it everything.

## The Right Wave 81 Shape

Wave 81 should have four tracks.

### A. Project Binding

Introduce one shared workspace-root helper and make the runtime act on a
real bound project root when `PROJECT_DIR` is present.

### B. Operational Truth

Fix the bugs that made recent runs misleading:

- shared-KV budget truth
- provider error visibility
- parallel-group execution semantics
- honest result aggregation and plan completion

### C. Codebase Index + Real-Repo Task Pack

Turn the existing codebase-index addon into a real-project surface and
define the benchmark pack that Wave 81 and Wave 82 will both use.

### D. Operator-Visible Workspace Truth

Show the operator:

- what project is bound
- what is project code vs library vs working memory vs artifacts
- whether a plan group is pending, running, blocked, or done
- how the real-repo benchmark pack is performing

## Why UI Is In-Wave

This session proved the point.

Every serious Queen failure was discovered from logs:

- plan truncation
- reconnaissance exit
- Group 2 never launched

If the operator had seen those states in the UI, the correction could
have happened before spending several minutes of colony runtime.

Wave 81 therefore treats UI as part of the planning and runtime
architecture:

- the workspace surface becomes truthful
- the active-plan surface becomes truthful
- the benchmark surface becomes visible

## Packet Shape

This packet is intentionally split into:

- one design note
- one dispatch plan
- four bounded team prompts
- one real-repo task-pack note

That gives Track C and Track D a common evaluation target instead of
letting benchmarking drift into log-only improvisation.

## Success Conditions

Wave 81 is successful if:

1. FormicOS can bind to a real project root with `PROJECT_DIR`.
2. Colonies, addons, and Queen file-focused logic operate on that bound
   root when present.
3. The workspace library remains intact as a separate upload/shared-file
   surface.
4. Parallel plans no longer silently drop later groups.
5. Group state is visible in the UI as pending/running/blocked/completed
   rather than inferred from incomplete result summaries.
6. Codebase indexing runs against the bound project root and reports
   truthful status.
7. A real-repo task pack exists and can be seen in-product, not just in
   logs.
