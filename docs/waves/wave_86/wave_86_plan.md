# Wave 86 Plan: Learn From Validated Success

## Status

Dispatch-ready. Grounded in source truth as of 2026-04-01.

## Summary

Wave 84 stabilized runtime execution.

Wave 85 made planning policy the live Queen routing authority and
improved planning-signal quality.

Wave 86 should not add more planning scaffolding. The next distinctive
step is to make the system improve from trustworthy outcomes and to make
code structure traversable in retrieval.

Two active tracks:

- Track A: outcome learning from validated success, folded together with
  verification refinement
- Track B: graph bridge phase 1, so code structure can participate in
  graph traversal and retrieval scoring

Deferred:

- playbook-quality ranking until playbook provenance is persisted on
  outcomes
- any new verifier colony or UI surface

## Verified Repo Truth

### 1. There is no repo `memory.md` authority to rely on here

This packet is grounded in current source seams plus
`docs/waves/PROGRESS.md`, not a canonical `memory.md` file.

### 2. Planning policy and live eval are already live

Wave 86 should not spend time redoing Wave 85.

- `planning_policy.py` is already wired into the live Queen respond path
  in `queen_runtime.py`
- `queen_planning_eval.py` already has a real guarded `live_eval` smoke
  and the pytest marker is registered

### 3. Plan patterns still only enter the system through explicit saves

`plan_patterns.py` is a YAML-backed store with:

- `list_patterns()`
- `get_pattern()`
- `save_pattern()`

It has no autonomous learning path yet. Patterns are still saved only
through operator/workbench or explicit API use.

### 4. There is already a nearby learning family

The codebase already learns from good outcomes in adjacent ways:

- auto-template creation in `colony_manager.py`
- trajectory extraction in `colony_manager.py`
- playbook proposal in `colony_manager.py`

So auto-learning plan patterns is not a new architectural direction. It
is a missing member of an existing family.

### 5. The durable seam for plan learning is persisted plan + outcome state

Do not build plan learning on the transient `_pending_parallel` map
alone.

The durable sources already exist:

- `thread.active_plan` and `thread.parallel_groups` in projections
- `ParallelPlanCreated.plan` and `planning_signals`
- replay-derived `ColonyOutcome`
- colony projections with validator/productivity truth

That is the elegant seam for learning from completed plans.

### 6. Verification signals already exist

There is already meaningful completion truth in the current system:

- validator state from `RoundCompleted` to projection
- `contractSatisfied` in Queen result metadata
- `productive_calls` / `observation_calls` on colony projections
- quality score on colony outcomes

Wave 86 should extend these seams, not invent a second verification
system next to them.

### 7. `expected_outputs` are not always file paths

Many `expected_outputs` come from `task_classifier.py` defaults like:

- `code`
- `test`
- `report`
- `document`

So a naive "does the expected output file exist?" gate would be wrong.

### 8. The graph bridge is still partially unwired

Three key facts are simultaneously true:

- `reflect_structure_to_graph()` already exists in
  `structural_planner.py`
- it is still unwired
- the runtime KG bridge only maps memory entries to SKILL/CONCEPT nodes
  through `entry_kg_nodes`

That means the graph has memory-entry lineage, but code-structure
MODULE nodes are still not part of the retrieval loop.

### 9. The codebase-index reindex seam is the natural graph hook

The addon reindex path already has the right context:

- workspace root
- runtime
- projections
- vector port

The elegant hook is the shared reindex completion seam, not a generic
app-startup side effect and not a manual-trigger-only special case.

### 10. Playbook-quality tracking is not ready yet

Current outcomes do not persist enough provenance to say "this outcome
came from playbook X" in a trustworthy way.

So "rank playbooks by historical quality" is not a Wave 86 item. First
persist provenance, then score it.

## Track A: Learn From Validated Success

Goal:

Teach the system to accumulate decomposition patterns automatically, but
only from outcomes that are strong enough to trust.

This track also tightens operator truth by using the same validation
logic to decide whether a completion is learnable and whether it should
be presented as validated vs needs review.

### Scope

1. Extend the plan-pattern store with additive trust fields

Keep backward compatibility for existing operator-saved patterns.

Additive fields may include:

- `status`: `approved` | `candidate`
- `learning_source`: `operator` | `auto`
- `evidence`: compact counters / summary

Important:

- existing manually saved patterns should continue to behave as approved
- this wave should not require a migration

2. Add a single validation/eligibility helper

Build one helper that answers:

- is this outcome learnable?
- should this result be surfaced as validated vs needs review?
- why?

It should consume existing truth only:

- quality
- validator verdict
- contract satisfaction
- productive vs total calls
- failure count for parallel plans

Do not introduce a second ad hoc verification model.

3. Auto-save candidate patterns from validated outcomes

Parallel plans:

- use the persisted plan structure and colony outcomes
- do not depend solely on `_pending_parallel`
- save a candidate only when the completed plan passes conservative gates

Single-colony / fast_path:

- only learn from clearly strong validated successes
- this is for cases like standout one-colony refactors, not every ordinary
  completion

4. Deduplicate by deterministic bundle

Do not spray near-duplicate candidates into the store.

Use a deterministic bundle derived from persisted data, such as:

- task class
- route kind (`parallel_dag`, `single_colony`, `fast_path`)
- normalized target-file set
- group count / colony count

5. Promote cautiously

Do not let first-sighting auto-learned patterns immediately behave like
operator-approved truth.

Recommended safety model:

- first validated success -> `candidate`
- repeated validated success for same bundle can promote to
  `approved` / learned

Retrieval in planning signals should continue to prefer approved
patterns. Candidate patterns may be surfaced separately or ignored by
default, but they should not silently outrank approved/operator patterns.

6. Surface verification state in completion truth

Use the same helper to improve result truth:

- validated
- needs review
- failed delivery / low-confidence completion

This should build on existing validator/contract/productivity seams.
Do not add a new event type.

### Good Gates

The exact thresholds can be tuned in implementation, but the direction
should be conservative:

- no colony failures for a learnable parallel plan
- no validator fail
- no contract gap when a contract exists
- non-trivial productive work
- quality materially above the current mediocre floor

### Owned Files

- `src/formicos/surface/plan_patterns.py`
- `src/formicos/surface/planning_signals.py`
- `src/formicos/surface/planning_brief.py`
- `src/formicos/surface/queen_runtime.py`
- `src/formicos/surface/colony_manager.py`
- `tests/unit/surface/test_plan_patterns.py`
- `tests/unit/surface/test_planning_signals.py`
- `tests/unit/surface/test_planning_brief.py`
- `tests/unit/surface/test_queen_runtime.py`
- `tests/unit/surface/test_colony_manager.py`

## Track B: Graph Bridge Phase 1

Goal:

Make code structure traversable so retrieval can move between:

- operator file/module references
- MODULE nodes
- DEPENDS_ON edges
- memory entries linked to those modules

### Scope

1. Wire structural reflection into the shared reindex seam

After a successful codebase reindex, call `reflect_structure_to_graph()`
using the existing addon runtime context.

Prefer a shared helper in the addon reindex path so both:

- manual/triggered reindex
- scheduled reindex

use the same reflection seam.

2. Add conservative entry-to-module edges

Do not mine arbitrary raw text.

Bridge memory entries to modules only from structured or low-risk refs,
for example:

- `source_colony_id` to colony projection target files
- artifact filenames / paths
- exact file-path refs in titles or summaries

Prefer the smallest truthful edge shape. Reuse existing predicate
semantics if they are sufficient; only add a new bridge predicate if the
extra distinction clearly pays for itself.

3. Seed graph scoring from module refs

When the operator query mentions files/modules, use the corresponding
MODULE nodes as graph seeds in addition to existing entry-based seeds.

This is the step that lets graph proximity reflect code structure rather
than only entry lineage.

4. Keep it additive and best-effort

- no new event types
- no new frontend surface
- no semantic indexing rewrite
- no speculative raw-content entity mining
- reflection/bridge failures must not fail the reindex itself

### Owned Files

- `src/formicos/adapters/knowledge_graph.py` only if a new bridge
  predicate is clearly justified
- `src/formicos/addons/codebase_index/indexer.py`
- `src/formicos/addons/codebase_index/search.py` if needed for trigger-path
  context plumbing
- `src/formicos/surface/structural_planner.py`
- `src/formicos/surface/runtime.py`
- `src/formicos/surface/knowledge_catalog.py`
- tests for codebase-index / structural planner / KG bridge / graph
  proximity

## Merge Order

Both tracks can start in parallel.

Recommended order:

1. Track A first if there is any ambiguity about new plan-pattern fields,
   because Track A defines learning trust semantics.
2. Track B can land independently once its tests are green.

## What Wave 86 Does Not Do

- no playbook-quality ranking yet
- no new verifier colony
- no model swap
- no new UI surface
- no new event types
- no rework of the live Queen routing policy

## Success Criteria

Wave 86 is successful if:

1. The system can auto-save at least one candidate plan pattern from a
   validated successful run without operator action.
2. Auto-learned patterns are clearly distinguished from approved/operator
   patterns.
3. Learning eligibility uses existing validator/contract/productivity
   truth instead of a second verification system.
4. Manual and scheduled reindex both create MODULE nodes and DEPENDS_ON
   edges in the KG.
5. Memory entries can connect to MODULE nodes via conservative structured
   refs.
6. A file/module-oriented query can produce non-zero graph-proximity
   influence for structurally related memory entries.

## Post-Wave Decision Gate

After Wave 86:

- If candidate plan patterns accumulate with strong repeated evidence,
  decide whether auto-promotion should become more aggressive.
- If graph-seeded retrieval clearly improves planning/retrieval,
  continue to graph bridge phase 2.
- Only after playbook provenance is persisted on outcomes should
  playbook-quality ranking become an active wave.
