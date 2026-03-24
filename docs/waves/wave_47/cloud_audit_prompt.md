## Wave 47 Cloud Audit Prompt

Audit the live repo against the Wave 47 packet before implementation starts.

This audit is not a brainstorming exercise. It is a repo-truth check for the
planned seams, team split, and product-identity guard.

## Core Questions

1. Is the current codebase still missing a true surgical edit tool?
2. Does `fast_path` still need replay-safe spawn/event/projection truth?
3. Is structural context still effectively compute-once rather than
   round-refreshed?
4. Are git tasks still primarily generic shell execution rather than
   first-class tools?
5. Are preview/progress surfaces still partial enough that Wave 47's bounded
   frontloading is justified?

## Read First

1. `docs/waves/wave_47/wave_47_plan.md`
2. `docs/waves/wave_47/acceptance_gates.md`
3. `docs/waves/wave_47/coder_prompt_team_1.md`
4. `docs/waves/wave_47/coder_prompt_team_2.md`
5. `docs/waves/wave_47/coder_prompt_team_3.md`
6. `AGENTS.md`
7. `CLAUDE.md`

Then verify the relevant code seams directly.

## Verify These Specific Claims

### Claim A: `patch_file` does not already exist

Check:

- `src/formicos/engine/tool_dispatch.py`
- `src/formicos/engine/runner.py`
- `config/caste_recipes.yaml`

Confirm whether coding agents still rely on full-file replacement and generic
execution rather than a search/replace patch primitive.

### Claim B: `fast_path` is not yet replay truth

Check:

- `src/formicos/core/events.py`
- `docs/contracts/events.py`
- `docs/contracts/types.ts`
- `src/formicos/surface/runtime.py`
- `src/formicos/surface/projections.py`

Confirm whether spawn/replay state currently carries any execution-mode flag
like `fast_path`.

### Claim C: structural context is not yet refreshed per round

Check:

- `src/formicos/surface/colony_manager.py`
- `src/formicos/engine/runner.py`
- `src/formicos/engine/context.py`
- `src/formicos/adapters/code_analysis.py`

Confirm whether structural context is still built once at colony start and
whether it is actually visible in agent round context.

### Claim D: git workflow still lacks first-class tools

Check:

- `src/formicos/engine/tool_dispatch.py`
- `src/formicos/engine/runner.py`
- `config/caste_recipes.yaml`

Confirm whether git operations are still done primarily through shell commands
or generic workspace execution.

### Claim E: preview/progress are still thin

Check:

- `src/formicos/surface/queen_tools.py`
- relevant frontend/store files for colony detail and spawn UX
- any existing stream/event translation for round status

Confirm:

- whether preview exists on neither, one, or both spawn paths
- whether fast-path estimates already exist
- whether any progress summary is already shipped and, if so, where it is
  derived from

## Team-Split Audit

Check whether the proposed ownership is still clean:

- Team 1: tool surface
- Team 2: replay/runtime/context/preview
- Team 3: recipes/docs truth

Call out any hidden overlap risk, especially in:

- `src/formicos/engine/runner.py`
- frontend store/detail files
- `config/caste_recipes.yaml`

## Product-Identity Audit

Answer explicitly:

1. Does each Must item clearly help arbitrary operator coding tasks?
2. Is any proposed item starting to drift toward benchmark-only optimization?
3. Does the packet still read like "better hands, not more brains"?

## Output Format

Return:

1. Findings first, ordered by severity, with file references
2. Repo-truth confirmation of the main Wave 47 seams
3. Any corrections needed before coder dispatch
4. A benchmark-drift check
5. A short verdict: dispatch-ready or not, and why

## Important Guardrails

- Do not evaluate Wave 47 based on whether it beats Aider.
- Evaluate it based on whether it improves real coding fluency in the product.
- If a planned item seems too loose, recommend narrowing it rather than
  expanding scope.
