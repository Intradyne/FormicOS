# Wave 89 Team B Prompt

## Mission

Turn the Wave 87 `host` doctrine into a real generation path.

This track is the bridge from:

- `capability_mode == "host"`

to:

- a colony that writes a constrained addon package
- and finishes by using `deploy_addon`

## Owned Files

- `src/formicos/surface/queen_runtime.py`
- `src/formicos/surface/planning_policy.py` only if host-mode
  calibration or tests need adjustment
- targeted tests under `tests/unit/surface/`

## Do Not Touch

- deployment infrastructure files owned by Team A
- `src/formicos/surface/addon_loader.py`
- frontend files
- service-colony persistence
- generated MCP-backed addon scope
- existing-addon reload / replace behavior

## Repo Truth To Read First

1. `src/formicos/surface/planning_policy.py`
   `host` already exists as a capability-mode output.

2. `src/formicos/surface/queen_runtime.py`
   The Queen currently logs `capability_mode`, but host-mode does not
   yet have a special colony prompt / execution path.

3. Project-bound workspace writes
   Colonies can already write into the live repo when the workspace is
   project-bound. That is what makes generated addon files deployable in
   this wave.

4. Wave 89 scope
   The first proof is internal-data only. Do not make the first
   generated addon depend on MCP or remote providers.

## What To Build

### 1. Add a host-specific colony context path

When the planning decision classifies a request as `host`, inject
additional colony context such as:

- addon template skeleton
- handler boilerplate expectations
- declarative panel vocabulary
- safe runtime_context fields
- output paths for addon files in the bound repo
- explicit instruction to finish by calling `deploy_addon`

### 2. Keep the first generated proof narrow and internal

The first generated dashboard should use internal FormicOS data only,
for example:

- colony outcomes
- quality trends
- auto-learned pattern counts
- pattern library state

Do not widen into remote provider integration here.

### 3. Bias toward the smallest viable colony

The first host path should prefer a single coder colony unless the task
clearly needs decomposition.

Do not widen into multi-agent addon factories or lifecycle loops.

### 4. Keep existing-addon modification explicitly non-gating

If you touch modification follow-up behavior at all, keep it clearly
restart-required and out of the acceptance path.

Wave 89 succeeds when a **new** addon can be generated and mounted
without restart.

## Constraints

- Do not invent a second deployment path.
- Do not bypass `deploy_addon`.
- No promise of existing-addon live replacement.
- No generated MCP-backed addon proof in this track.

## Validation

- targeted tests for:
  - host-like prompt selects or preserves `capability_mode == "host"`
  - host-mode prompt/context includes the addon template truth
  - host-mode path expects `deploy_addon` instead of raw file delivery
  - non-host requests do not accidentally inherit the addon-generation
    prompt

## Overlap Note

- Team A owns the deployment tool and strict loader.
- You own the Queen-side behavior that decides when and how to use it.
- Do not duplicate addon packaging logic inside `queen_runtime.py`.
