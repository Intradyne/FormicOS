# Wave 80 Design Note: The Queen Learns to Plan

## Theme

Wave 80 should make the Queen better at decomposition by connecting
existing infrastructure into a small, scored planning brief. The goal is
not another planning subsystem. The goal is to make the Queen consult
the right signals before she decides how to split work.

The key empirical claim from the recent swarm work is still the right
one:

> The ceiling is not the worker model by itself. The ceiling is whether
> the Queen decomposes work into pieces the worker can actually handle.

## Verified Repo Truth

This packet is grounded in the live repo as of 2026-03-30.

- The Queen already retrieves knowledge before the first LLM call.
  `QueenAgent.respond()` resolves toolsets at
  `src/formicos/surface/queen_runtime.py:1185-1188` and then calls
  `runtime.retrieve_relevant_memory(...)` at
  `src/formicos/surface/queen_runtime.py:1200`. The gap is not missing
  retrieval. The gap is that the query is the raw operator message, not
  a decomposition-focused query.
- The knowledge graph is live and graph proximity is already active.
  `knowledge_catalog.search()` computes graph scores at
  `src/formicos/surface/knowledge_catalog.py:331-386`, and
  `graph_proximity` already has weight `0.06` in
  `src/formicos/surface/knowledge_constants.py:33-40`.
- Playbooks exist and are already useful, but they currently encode
  execution workflow, not decomposition structure.
  `load_playbook()` and `load_all_playbooks()` live at
  `src/formicos/engine/playbook_loader.py:31` and `:111`.
- Workflow learning exists, but its stable fingerprint is only
  `(strategy, sorted castes)` at
  `src/formicos/surface/workflow_learning.py:193-199`. It is not yet a
  model-aware decomposition memory.
- Structural file coupling already exists in lightweight form.
  `analyze_workspace()` and `WorkspaceStructure.relevant_context()` live
  at `src/formicos/adapters/code_analysis.py:165` and `:87`.
- `ColonyTask` already carries `depends_on`, `input_from`, and
  `target_files` at `src/formicos/core/types.py:879-896`, but it does
  not carry `expected_outputs`.
- `spawn_parallel` already exposes a DAG-shaped tool schema at
  `src/formicos/surface/queen_tools.py:500-598`, but that schema is
  missing both `target_files` and `expected_outputs` on the task items.
- `ProjectionStore.outcome_stats()` already aggregates prior colony
  results for planning at `src/formicos/surface/projections.py:739-759`.

## Product Stance

Wave 80 should not overcorrect into architectural purity.

- The Queen keeps direct execution tools. This wave does not impose a
  delegator-only runtime charter.
- This wave does not add a new budget slot. The planning brief must fit
  inside the existing `memory_retrieval` budget and only appear on turns
  where the `colony` toolset is active.
- This wave does not retune retrieval weights. `graph_proximity` stays
  at `0.06` until the planning-brief path is measured on its own.
- This wave does not add new event types, new queues, or a new planning
  database.
- This wave does not change colony execution, convergence, or
  stigmergic routing in `runner.py`.

## The Right Wave 80 Shape

The right shape is a thin planning layer made from four existing signal
families plus one handoff fix:

1. Knowledge patterns
   Reuse the existing knowledge catalog, but query it with a
   decomposition-oriented phrase and post-filter the results for pattern-
   like entries.

2. Playbook hints
   Add a decomposition hint path alongside the existing execution
   playbook path. The Queen should see a one-line structural hint, not
   the whole execution card.

3. Capability profiles
   Ship a small static capability-profile file for known worker models
   and load it through a helper. This frontloads Wave 81's model-aware
   planning without pretending the system has already learned these
   values from outcomes.

4. Structural coupling
   Reuse the existing workspace code analysis to produce one optional
   file-coupling hint when the operator message references recognizable
   files or modules.

5. File-mediated handoff
   Align `ColonyTask` and `spawn_parallel` with the already-established
   idea that downstream colonies should consume upstream files, not only
   prose.

## Planning Brief Constraints

The planning brief should be a compact scored block, not another prompt
dump.

- Inject only when `"colony"` is in the resolved toolsets.
- Consume the existing `memory_retrieval` slot, not a new slot.
- Hard cap the planning brief to `min(500, budget.memory_retrieval // 3)`
  tokens. If the slot is small, the brief shrinks first.
- If there is no strong signal for a section, omit that section instead
  of padding it with generic prose.
- Prefer one-line sections with compact evidence markers.

The target shape is:

```text
PLANNING BRIEF
- Patterns: addon-build (q=0.59, score=0.82) | refactor (q=0.72, score=0.76)
- Playbook: code_implementation (conf=1.00) -> 3-5 colonies, grouped files, coder-led
- Worker: qwen3.5-4b (n=24) -> 3-4 files optimal, 1-file -16%, focused can reach 0.738
- Coupling: scanner<->coverage<->quality (conf=0.67, direct deps)
```

The coupling line is optional. If the operator did not reference any
recognizable files or modules, the brief should omit it rather than
invent structure.

## Frontloading Wave 81/82 Groundwork

Wave 80 can safely frontload a few future-wave seams without sprawling:

- A dedicated `planning_brief.py` helper instead of more logic inside
  `queen_runtime.py`.
- A shipped `config/capability_profiles.json` plus an optional runtime
  override path. This lets future waves learn into a stable file
  contract without changing the Queen interface again.
- Optional `decomposition` blocks in curated playbook YAML files. This
  creates a durable structural hint seam without changing colony
  execution behavior.
- `expected_outputs` on `ColonyTask` plus automatic `target_files`
  wiring from upstream tasks. This makes file-mediated colony handoff a
  real contract instead of an operator-only convention.

## Packet Shape

Three implementation tracks are enough.

### Team A: Planning Brief Integration

Owns:

- `src/formicos/surface/planning_brief.py` (new)
- `src/formicos/surface/queen_runtime.py`
- `tests/unit/surface/test_planning_brief.py` (new)

Mission:

- Build the brief
- Keep it small
- Inject it conditionally
- Reuse existing retrieval and structural analysis

### Team B: Planning Signal Providers

Owns:

- `src/formicos/engine/playbook_loader.py`
- `src/formicos/surface/capability_profiles.py` (new)
- `config/capability_profiles.json` (new)
- selected `config/playbooks/*.yaml`
- tests for playbook hints and capability profiles

Mission:

- Make playbooks speak in decomposition terms
- Ship a static model-capability signal
- Keep everything deterministic and cheap

### Team C: File-Mediated Planning Contracts

Owns:

- `src/formicos/core/types.py`
- `src/formicos/surface/queen_tools.py`
- `tests/unit/surface/test_file_handoff.py` (new)

Mission:

- Align the `spawn_parallel` tool schema with `ColonyTask`
- Add `expected_outputs`
- Auto-wire downstream `target_files` from upstream outputs

## Merge Order

1. Team B
2. Team C
3. Team A

Team A integrates signals from Team B and benefits from Team C's more
expressive parallel-plan contract, so it should land last.

## Success Conditions

Wave 80 is successful if:

1. The Queen injects a compact planning brief only on colony-capable
   planning turns.
2. The brief stays within the existing `memory_retrieval` budget and
   does not add a new slot.
3. The brief can be built from existing repo state even when the
   workspace has a sparse knowledge base: playbook hint + capability
   summary still work.
4. `get_decomposition_hints()` returns a short structural hint from the
   curated playbook set.
5. Worker capability summaries come from shipped config, not hardcoded
   prompt prose.
6. `ColonyTask` accepts `expected_outputs`, and `spawn_parallel` can
   express and auto-wire file handoff through `target_files`.
7. Existing tests still pass, and the new tests cover the brief path,
   playbook hint path, and file-handoff path.
