# Wave 79 / 79.5 Design Note

## Core position

FormicOS should **not** adopt a pure "orchestrator can never act directly"
model right now.

The Queen having direct execution/edit/test tools is a product feature:

- small fixes do not need colony overhead
- operators can stay in one conversational loop
- the system remains useful even when delegation would be mechanically
  correct but ergonomically clumsy

So the right near-term direction is:

- keep direct Queen action available
- reduce irrelevant tool surface with dynamic loading
- make file-backed workflow and colony handoff much more visible

This is a pragmatic architecture, not the paper's purist one.

## Invariants

1. Direct Queen action remains allowed.

Wave 79 does not remove `run_command`, `edit_file`, `run_tests`,
`batch_command`, or `write_workspace_file` from the Queen.

Dynamic toolset loading may omit them when they are irrelevant to the
current turn, but the system does not introduce a hard runtime charter
that forbids direct work.

If FormicOS ever adds a stricter delegator-only mode, it should be an
optional workspace policy, not the default product posture.

2. File-backed coordination is the main upgrade path.

The live repo already has the right substrate:

- `target_files`
- `input_sources`
- working memory under `.formicos/runtime/`
- artifact promotion under `.formicos/artifacts/`
- result artifacts on colony completion

The problem is visibility and workflow ergonomics, not absence of
infrastructure.

3. No stage-engine/NLAH runtime in 79.5.

Stage-gated contracts are a real future direction, but they are more than
UI polish:

- they want runtime stage state
- deterministic gates
- retry/fork semantics at stage boundaries
- new operator-facing contract surfaces

That is too large for a follow-on to Wave 79 and would blur the packet.

4. Use files as the source of truth, not prose summaries, where practical.

When colonies build on prior colony outputs, the preferred pattern is:

- point at actual files via `target_files`
- chain prior colony outputs via `input_sources`
- avoid over-summarizing prior work into task prose

This is the part of the Harness Engineering research that fits FormicOS
cleanly today.

## What 79 does

Wave 79 is about local-model quality and context efficiency:

- dynamic Queen toolset loading
- colony tool pruning
- convergence improvement
- compaction refinements
- Queen path-safe file writing

## What 79.5 does

Wave 79.5 is about file-aware workflow UX:

- selecting target files
- seeing concrete output files
- promoting uploaded documents into searchable knowledge
- making file-mediated colony handoff visible to the operator

## What is intentionally deferred

- hard runtime charter that forbids Queen direct action
- NLAH / stage-gated runtime contracts
- host-project filesystem mounting
- multi-project workspace binding
- new event types just for file workflow polish
