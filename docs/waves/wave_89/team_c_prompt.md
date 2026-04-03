# Wave 89 Team C Prompt

## Mission

Add the smallest truthful observation seam for hosted capabilities, and
only expand the panel surface if the first generated internal dashboard
is genuinely blocked.

This is not a monitoring platform wave. It is a visibility wave.

## Owned Files

- one new helper module under `src/formicos/surface/` if needed for
  hosted-capability status assembly
- `src/formicos/surface/queen_tools.py` for
  `check_hosted_capabilities`
- `frontend/src/components/addon-panel.ts` only if the first generated
  dashboard is blocked by missing declarative rendering
- targeted tests under `tests/unit/surface/` and frontend-adjacent tests
  if required

## Do Not Touch

- deployment infrastructure owned by Team A
- `src/formicos/surface/addon_loader.py`
- `src/formicos/surface/queen_runtime.py`
- service-colony persistence
- autonomous repair
- existing-addon replace/hot-reload work

## Repo Truth To Read First

1. `src/formicos/surface/view_state.py`
   Addon summaries already surface:
   - manifest identity
   - registered panels
   - refresh intervals
   - trigger metadata
   - registration health / error state

2. `src/formicos/surface/app.py`
   Addon registrations and triggers already exist as live runtime truth.

3. `frontend/src/components/addon-panel.ts`
   The surface already supports:
   - `status_card`
   - `table`
   - `log`
   - `kpi_card`
   - sparkline trends via `trend`

4. Wave 89 scope
   The first generated dashboard is internal and should likely fit the
   existing vocabulary. Expand only if the proof case is actually
   blocked.

## What To Build

### 1. Add `check_hosted_capabilities`

Build a lightweight Queen tool that reports the current hosted
capability set from existing runtime truth such as:

- addon registrations
- addon summary fields
- panel metadata
- registration status / last error
- trigger metadata

This should answer the present snapshot. It should not introduce a
background watcher or probe daemon.

### 2. Make the output useful for operator trust

The result should make it easy to see:

- which hosted panels are mounted
- which addon owns them
- refresh interval
- status / disabled state
- last known error
- trigger / refresh hooks when present

### 3. Expand panel vocabulary only if needed

If the concrete first generated dashboard genuinely needs one additive
shape beyond the current surface, add it carefully.

Do not widen into a general dashboard framework unless the proof is
blocked without it.

## Constraints

- Keep observation lightweight and truthful.
- No proactive repair loop.
- No service-colony data plane work.
- Avoid broad frontend redesign.

## Validation

- targeted tests for:
  - hosted capability listing reflects current addon registrations
  - disabled/error state is surfaced truthfully
  - panel metadata (target/path/refresh interval) is included
  - any additive frontend shape renders deterministically

## Overlap Note

- `queen_tools.py` is the one shared seam with Team A.
- Reread Team A's landed `deploy_addon` changes before finalizing your
  tool wiring.
- Do not reopen deployment validation or loader ownership boundaries.
