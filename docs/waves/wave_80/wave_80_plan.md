# Wave 80 Plan: The Queen Learns to Plan

## Summary

Wave 80 should make the Queen better at decomposition by adding a
conditional planning brief and by tightening the file-mediated handoff
contract for parallel plans.

This wave explicitly frontloads a few Wave 81/82 seams:

- shipped capability profiles
- playbook-level decomposition hints
- structural coupling hints from existing code analysis
- explicit file outputs on `ColonyTask`

It does not add a new planner, a new event type, or a new execution
engine.

## Knowledge Grounding Stance

Wave 80 does not create a separate seed-data track.

- The intended live path is to reuse the existing experiment and
  architecture entries already present in the knowledge base.
- The implementation must still work in a sparse or clean-room dev
  environment. If those entries are absent, the planning brief should
  degrade cleanly to playbook hints, capability profiles, and any
  structural coupling signal it can prove.
- That means the brief builder should prefer real retrieved patterns but
  never require them.

## What We Are Building

### Track A: Planning Brief Integration

Goal:

When the Queen is on a decomposition turn, inject a tiny scored planning
brief before the first LLM call.

Implementation shape:

- Add `src/formicos/surface/planning_brief.py`
- Call it from `QueenAgent._respond_inner()` (line 1121, called by
  `respond()` at line 1108) after toolsets are resolved at `:1185-1188`
- Inject the brief before or alongside the existing memory block loaded
  through `runtime.retrieve_relevant_memory(...)` at `:1200`

Signal sources:

- Existing knowledge catalog search
- Existing `ProjectionStore.outcome_stats(...)`
- `get_decomposition_hints()` from Track B
- capability summary from Track B
- existing workspace code analysis

Important constraints:

- Only build the brief when `"colony"` is in the resolved toolsets
- Do not add a new Queen budget slot
- Cap the brief to `min(500, budget.memory_retrieval // 3)` tokens
- Keep the formatted brief under about 2000 characters
- Omit weak sections instead of filling space with generic text

Recommended output shape:

```text
PLANNING BRIEF
- Patterns: addon-build (q=0.59, score=0.82) | refactor (q=0.72, score=0.76)
- Playbook: code_implementation (conf=1.00) -> 3-5 colonies, grouped files, coder-led
- Worker: qwen3.5-4b (n=24) -> 3-4 files optimal, 1-file -16%, focused can reach 0.738
- Coupling: scanner<->coverage<->quality (conf=0.67, direct deps)
```

Notes:

- The patterns line should prefer real knowledge entries already present
  in the knowledge base. Do not create a separate seed-data track in this
  wave.
- If the workspace knowledge base is sparse, fall back to a short
  empirical line from `outcome_stats(...)`.
- The coupling line is conditional. Only include it when the operator
  message references files or modules that can be matched to the
  workspace structure with confidence.

Owned files:

- `src/formicos/surface/planning_brief.py` (new)
- `src/formicos/surface/queen_runtime.py`
- `tests/unit/surface/test_planning_brief.py` (new)

Validation:

- `python -m pytest tests/unit/surface/test_planning_brief.py -q`
- `python -m pytest tests/unit/surface/test_queen_runtime.py -q`
- `python -m pytest tests/unit/adapters/test_code_analysis.py -q`

### Track B: Planning Signal Providers

Goal:

Make playbooks and capability profiles usable as decomposition-time
signals instead of execution-only context.

Implementation shape:

1. Add `get_decomposition_hints(task_description: str) -> str | None` to
   `src/formicos/engine/playbook_loader.py`
2. Add optional `decomposition` blocks to the highest-value curated
   playbooks
3. Add `src/formicos/surface/capability_profiles.py`
4. Add `config/capability_profiles.json`

Playbook hint rules:

- Use `classify_task()` from `src/formicos/surface/task_classifier.py:72`
  as the first discriminator
- Prefer an explicit playbook `decomposition` block when present
- Fall back to deterministic task-class defaults when no decomposition
  block exists
- Return a one-line structural hint with a confidence label
- Do not inject the execution playbook body into the Queen planning brief

Recommended `decomposition` block shape in YAML:

```yaml
decomposition:
  confidence: 1.0
  colony_range: "3-5"
  grouping: "group semantically related files; avoid 1-file splits"
  recommended_caste: "coder"
  recommended_strategy: "stigmergic"
```

Capability profile rules:

- Ship defaults in `config/capability_profiles.json`
- Support an optional runtime override file at:
  `<data_dir>/.formicos/runtime/capability_profiles.json`
- Resolve profiles against the actual worker model, not only
  `settings.models.defaults.coder`
- Use `runtime.resolve_model("coder", workspace_id)` as the first lookup
  path, then normalize by short alias or suffix if needed
- Keep v1 static and deterministic; do not auto-update profiles from
  outcomes in this wave

Recommended initial profiles:

- `qwen3.5-4b`
- the local 35B Queen model only if it is also used as a worker
- `gpt-4.1-mini` if it is still a realistic worker option in this repo

Owned files:

- `src/formicos/engine/playbook_loader.py`
- `src/formicos/surface/capability_profiles.py` (new)
- `config/capability_profiles.json` (new)
- `config/playbooks/code_implementation.yaml`
- `config/playbooks/design.yaml`
- `config/playbooks/research.yaml`
- `config/playbooks/code_review.yaml`
- `config/playbooks/generic.yaml`
- `tests/unit/engine/test_playbook_hints.py` (new)
- `tests/unit/surface/test_capability_profiles.py` (new)

Validation:

- `python -m pytest tests/unit/engine/test_playbook_hints.py -q`
- `python -m pytest tests/unit/surface/test_capability_profiles.py -q`
- `python -m pytest tests/unit/surface/test_queen_tools.py -q`

### Track C: File-Mediated Planning Contracts

Goal:

Make file handoff a first-class part of `spawn_parallel` planning.

Implementation shape:

1. Add `expected_outputs: list[str]` to `ColonyTask` in
   `src/formicos/core/types.py:879-896`
2. Add `expected_outputs` and `target_files` to the per-task schema in
   `spawn_parallel` at `src/formicos/surface/queen_tools.py:500-598`
3. In `_spawn_parallel()` at
   `src/formicos/surface/queen_tools.py:2192-2355`, auto-wire
   downstream `target_files` from upstream `expected_outputs` whenever:
   - the task has `depends_on`
   - explicit `target_files` are empty
   - the upstream task declared outputs

Wiring rules:

- Preserve explicit `target_files`
- Preserve `depends_on` order when collecting upstream outputs
- Deduplicate the final `target_files` list
- Perform auto-wiring before preview-mode formatting so preview output
  reflects the actual resolved handoff plan
- Do not auto-fill `input_from`; that remains an explicit colony-context
  chain, separate from file handoff

Recommended preview enhancement:

- When preview mode is used, include each task's resolved
  `expected_outputs` and `target_files` in the preview text or preview
  metadata so the operator can audit the file plan before dispatch

Owned files:

- `src/formicos/core/types.py`
- `src/formicos/surface/queen_tools.py`
- `tests/unit/surface/test_file_handoff.py` (new)

Validation:

- `python -m pytest tests/unit/surface/test_file_handoff.py -q`
- `python -m pytest tests/unit/surface/test_queen_tools.py -q`
- `python -m pytest tests/integration/test_wave41_multifile_coordination.py -q`

## Merge Order

Recommended order:

1. Track B
2. Track C
3. Track A

Parallel start:

- Track B and Track C can start immediately
- Track A should wait for Track B helper names to freeze
- Track A should reread `ColonyTask` after Track C lands so the planning
  brief examples do not drift from the new handoff contract

## What This Wave Explicitly Does Not Do

- No new budget slot
- No graph-weight retuning
- No new knowledge type or Qdrant collection
- No runner or colony execution changes
- No convergence or stigmergy changes
- No delegator-only runtime charter
- No stage-gated NLAH execution engine
- No host project mount
- No frontend changes
- No new event types

## Post-Wave Validation

After Wave 80 lands, rerun the swarm experiment on the current local
stack with:

- the planning brief enabled
- shipped capability profiles
- playbook decomposition hints
- file handoff via `expected_outputs` -> `target_files`

Success target:

- mean quality materially above the current local Queen + 4B worker
  baseline
- the Queen's first meaningful planning action is decomposition, not
  exploratory flailing
- downstream colonies show resolved `target_files` derived from upstream
  outputs in the spawned plan
