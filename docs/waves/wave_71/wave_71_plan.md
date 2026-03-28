# Wave 71: The Operational Loop

**Status:** Split dispatch packet
**Predecessor:** Wave 70.0 + 70.5

Wave 71 is split into two sequential packets:

- `docs/waves/wave_71_0/wave_71_0_plan.md`
- `docs/waves/wave_71_5/wave_71_5_plan.md`

## Why It Is Split

This wave is really two jobs:

- give the Queen durable, multi-day operational coherence
- make that operational state legible and steerable for the operator

`71.0` lands the backend/control-plane substrate first:

- Queen journal
- operating procedures
- durable action queue
- scheduled operational sweeps
- cross-artifact continuation/sync summary

`71.5` then gives those capabilities a real home in the product surface:

- dedicated Operations tab
- action inbox and review controls
- journal panel
- procedures editor

## Authority

Use these docs for dispatch:

- `docs/waves/wave_71_0/design_note.md`
- `docs/waves/wave_71_0/team_a_prompt.md`
- `docs/waves/wave_71_0/team_b_prompt.md`
- `docs/waves/wave_71_0/team_c_prompt.md`
- `docs/waves/wave_71_5/team_a_prompt.md`
- `docs/waves/wave_71_5/team_b_prompt.md`
- `docs/waves/wave_71_5/team_c_prompt.md`

## Thesis

Wave 71 makes autonomy operational rather than episodic. The Queen should be
able to pick up a project after hours or days away, explain what she has been
doing, show what is waiting on the operator, and follow workspace-specific
operating procedures without smearing operational state into
`memory_entries`.
