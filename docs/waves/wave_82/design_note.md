# Wave 82 Design Note: Visible Learning Planner

## Theme

Wave 82 should make the planner learn from real outcomes, ground itself
in real file structure, and show the operator why it made a plan before
that plan burns time.

Wave 81 makes workspace truth real.
Wave 82 makes planning truth visible and compounding.

This wave is not a new planner service and not a full Wave 83 workbench.
It is the point where FormicOS stops hiding planning intelligence behind
logs and starts exposing it as an operator-facing control surface.

## Verified Repo Truth

This packet is grounded in the live repo as of 2026-03-31.

- `src/formicos/surface/workflow_learning.py` is still write-side and
  proposal-oriented. It recognizes repeating patterns and writes
  `workflow_template` or `procedure_suggestion` actions, but its stable
  fingerprint is still only `(strategy, sorted castes)`. It does not
  yet serve planning-time decomposition memories.
- `src/formicos/surface/planning_brief.py` already exists and already
  composes a tiny brief from real seams:
  knowledge catalog search, playbook hints, capability summaries, and
  code-analysis coupling hints.
- the Queen's colony-work classifier now accepts ordinary implementation
  verbs such as `add`, `improve`, `strengthen`, `write`, `cover`, and
  `consolidate`, so the real-repo task pack no longer depends on the
  operator rephrasing every task into explicit build language just to
  reach colony dispatch.
- `src/formicos/surface/parallel_plans.py` now exists after Wave 81 and
  already tracks deferred groups, honest aggregation, restart-time
  reconstruction, and per-task/group truth. Wave 82 should reuse that
  execution truth instead of inventing a separate plan-state story.
- `src/formicos/surface/capability_profiles.py` is still a shipped-JSON
  loader with optional runtime override. It is useful as a bootstrap,
  but not yet a replay-derived learning surface.
- `src/formicos/adapters/code_analysis.py` already builds a lightweight
  dependency graph, reverse dependencies, and test companions. That is
  enough to drive planning hints if it is connected to the real project
  root and the knowledge graph.
- Wave 81 project binding and the project-binding/status APIs are now
  real runtime truth, not a plan hypothesis. The current FormicOS
  workspace reports a bound project root and a ready code index with
  populated file/chunk counts, which means Wave 82 can treat indexed
  real-repo truth as an established seam.
- `src/formicos/adapters/knowledge_graph.py` already supports
  `MODULE` entities, `DEPENDS_ON` edges, and `personalized_pagerank(...)`.
  `src/formicos/surface/knowledge_catalog.py` already consumes graph
  proximity in retrieval. Wave 82 should extend that seam, not create a
  second graph system.
- `frontend/src/components/queen-chat.ts` already renders multiple
  structured card types and already shows `consulted_entries` when the
  Queen includes them in message metadata.
- `frontend/src/components/thread-view.ts` and
  `frontend/src/components/workflow-view.ts` already render active
  parallel DAG truth and already expose an `edit-plan` seam. Wave 82
  should extend that surface, not bypass it with a disconnected preview.
- `frontend/src/components/formicos-app.ts` already has the preview
  confirm/open-editor path and already carries draft `target_files`
  state into `frontend/src/components/colony-creator.ts`.
- `frontend/src/types.ts` already has `ParallelResultMeta`,
  `DelegationPlanPreview`, `ThreadPlan`, and the metadata seams needed
  for a more capable planning UI. What is missing is richer plan
  metadata and a better operator correction surface.

## Product Stance

Wave 82 should keep the architecture simple and visible.

- Reuse the Wave 80 planning brief instead of replacing it.
- Reuse the Wave 81 real project root instead of inventing another file
  substrate.
- Reuse the existing knowledge graph instead of building a separate
  "repo map" subsystem.
- Reuse Queen chat preview/result metadata plus the existing
  thread/workflow DAG surfaces instead of inventing a second plan UI
  protocol.
- Keep the Queen powerful. This is not a runtime-charter wave.

The right shape is:

- learned planning signals
- structural planning signals
- replay-derived capability calibration
- visible plan explainability and small pre-dispatch correction

## The Right Wave 82 Shape

Wave 82 should have four tracks.

### A. Learned Planning Signals

Turn planning signals into structured, replay-friendly data rather than
one-off text assembly.

This track should:

- extend workflow learning with a read path for planning-time outcomes
- add a small structured planning-signals helper for the Queen
- persist enough plan provenance for replay and UI comparison
- keep the planning brief tiny while making the underlying signals
  available to the UI

### B. Structural Planner

Turn real project structure into planning-grade signals.

This track should:

- populate the knowledge graph with module dependency data from the
  real project root
- expose suggested file groups and coupling hints
- prefer proved structure over guessed structure
- reduce the Queen's reconnaissance tax by giving her structural facts
  before she reaches for `ls` and `find`

### C. Replay-Derived Capability Calibration

Turn capability profiles from shipped priors into learned overlays.

This track should:

- preserve shipped profiles as bootstrap defaults
- derive live overlays from replayed colony outcomes
- key capability by planner model, worker model, and granularity
- expose confidence and sample size so the operator can see whether a
  summary is established or still warming up

### D. Visible Learning Planner

Make learned and structural planning visible, comparable, and lightly
steerable.

This is where the operator should be able to:

- see why the Queen proposed this plan
- compare it to a prior successful plan
- correct a task description before dispatch
- move a file between colonies before dispatch
- confirm the actual DAG, not just trust that it was fine
- see the same pending/running/blocked/completed group truth in preview,
  active-plan, and result views

This is the minimal steering wheel that should land before the full Wave
83 planning workbench.

## Why UI Is In-Wave

Wave 81 fixes "what actually ran."
Wave 82 must fix "why this plan exists."

If Wave 82 lands only as backend learning, the operator still has a
black box:

- the planning brief may have been right or wrong
- the Queen may have obeyed it or ignored it
- structural hints may have existed or been omitted
- learned patterns may have been sparse or dominant

Without UI, the operator still finds out after the run and still has to
infer the cause from logs.

Wave 82 therefore treats explainability and minimal correction as part
of planning architecture, not polish.

## Shared Evaluation Substrate

Wave 82 should not invent a new benchmark pack.

It should reuse the real-repo task pack defined in:

- `docs/waves/wave_81/real_repo_task_pack.md`

That task pack is now live, not hypothetical: `rtp-01` already proved
end-to-end real-code execution, and `rtp-02` through `rtp-05` are the
active comparison set.

That gives Wave 81 and Wave 82 the same evaluation substrate:

- Wave 81 proves real workspace truth
- Wave 82 proves learned and structural planning on the same tasks

## Success Conditions

Wave 82 is successful if:

1. the planning brief is backed by structured planning signals rather
   than ad hoc line assembly
2. workflow learning can return relevant prior decompositions for
   planning turns
3. real project structure is reflected into the knowledge graph and used
   for coupling and suggested grouping
4. capability summaries are replay-derived overlays on top of shipped
   priors
5. the operator can see "why this plan" before dispatch
6. the operator can make small plan corrections before dispatch without
   waiting for the full Wave 83 workbench
7. preview, active-plan, and result surfaces agree about group truth
8. the same real-repo task pack can show whether Wave 82 improved plan
   quality or just added more hidden machinery
