## Wave 48 Cloud Audit Prompt

Audit the live repo against the Wave 48 packet before implementation starts.

This is not a brainstorming exercise. It is a repo-truth check for the planned
seams, the caste-grounding decisions, the team split, and the product-identity
guard.

## Core Questions

1. Are the Reviewer and Researcher still under-grounded in the live recipes?
2. Does the repo still need a thread-first timeline rather than another
   workspace-level summary?
3. Is colony-audit Forager attribution still too thin for the intended UI?
4. Does the existing creator Review step still rely on local rough estimates
   instead of backend preview truth?
5. Is running-colony progress still shallow enough that bounded activity polish
   is justified?
6. Is the preferred mediated Researcher -> Forager path realistic in the live
   seams, or does the fallback direct-web path look more practical?

## Read First

1. `docs/waves/wave_48/wave_48_plan.md`
2. `docs/waves/wave_48/acceptance_gates.md`
3. `docs/waves/wave_48/coder_prompt_team_1.md`
4. `docs/waves/wave_48/coder_prompt_team_2.md`
5. `docs/waves/wave_48/coder_prompt_team_3.md`
6. `AGENTS.md`
7. `CLAUDE.md`

Then verify the relevant code seams directly.

## Verify These Specific Claims

### Claim A: Reviewer and Researcher are still under-grounded

Check:

- `config/caste_recipes.yaml`
- `src/formicos/engine/tool_dispatch.py`

Confirm:

- whether Reviewer still lacks direct repo/diff visibility
- whether Researcher still lacks repo-read grounding
- whether either caste already has a fresh-information path we are missing

### Claim B: Thread-first timeline is still missing

Check:

- `frontend/src/components/thread-view.ts`
- `frontend/src/state/store.ts`
- `src/formicos/surface/routes/api.py`
- `src/formicos/surface/projections.py`

Confirm whether there is already a thread-level chronological operator story,
or whether the current surfaces still leave the story fragmented.

### Claim C: Colony audit payload is still too thin for Forager attribution

Check:

- `src/formicos/surface/projections.py`
- `frontend/src/components/colony-audit.ts`

Confirm whether the audit payload currently includes rich Forager provenance
and cycle linkage, or whether Wave 48 still needs backend/read-model shaping.

### Claim D: Review-step preview is still local/rough

Check:

- `frontend/src/components/colony-creator.ts`
- `src/formicos/surface/queen_tools.py`

Confirm:

- whether the backend preview substrate already exists on both spawn paths
- whether the frontend Review step still uses a local estimate instead of that
  substrate

### Claim E: Running-state clarity is still partial

Check:

- `frontend/src/components/colony-detail.ts`
- `frontend/src/components/colony-chat.ts`
- `frontend/src/state/store.ts`
- any current event/projection preview fields relevant to recent activity

Confirm whether a bounded "latest meaningful activity" improvement is still a
real gap.

### Claim F: Preferred Researcher -> Forager mediation is realistic

Check:

- `src/formicos/surface/runtime.py`
- `src/formicos/engine/tool_dispatch.py`
- `src/formicos/engine/runner.py`
- existing Forager service seams and any relevant API/service helpers

Answer explicitly:

- does a bounded `request_forage`-style path look straightforward enough for
  Wave 48?
- if not, is the direct Researcher web fallback the more realistic in-wave
  choice?

## Team-Split Audit

Check whether the proposed ownership is still clean:

- Team 1: backend/read-model + fresh-information path
- Team 2: frontend flow + integration
- Team 3: recipes/docs truth

Call out hidden overlap risk, especially in:

- `src/formicos/engine/tool_dispatch.py`
- `src/formicos/engine/runner.py`
- `src/formicos/surface/queen_tools.py`
- `frontend/src/state/store.ts`
- `config/caste_recipes.yaml`

## Product-Identity Audit

Answer explicitly:

1. Does each Must item clearly help arbitrary operator tasks?
2. Does the packet preserve "specialization without blindness"?
3. Does the packet avoid turning the Forager into a second colony worker model?
4. Is any item starting to drift toward benchmark-only optimization?

## Output Format

Return:

1. Findings first, ordered by severity, with file references
2. Repo-truth confirmation of the main Wave 48 seams
3. Any corrections needed before coder dispatch
4. A benchmark-drift / product-identity check
5. A short verdict: dispatch-ready or not, and why

## Important Guardrails

- Do not evaluate Wave 48 by whether it helps a leaderboard.
- Evaluate it by whether it makes the specialist castes more grounded and the
  operator story more coherent.
- If a planned item is too loose, recommend narrowing it rather than expanding
  scope.
