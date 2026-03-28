# Wave 70: Superseded By Split Packet

**Status:** Superseded for dispatch

The original single-wave Wave 70 packet is no longer the authority.
It has been split into two sequential packets:

- `docs/waves/wave_70_0/wave_70_0_plan.md`
- `docs/waves/wave_70_5/wave_70_5_plan.md`

## Why It Was Split

The original packet mixed two different jobs:

- backend/control-plane flexibility
- operator-visible product surface wiring

After Wave 69, shipping major new capabilities with no operator-facing
surface would have felt like a product regression. The split keeps the
backend work sharp and generic in `70.0`, then finishes the trust/visibility
surface in `70.5`.

## Authority

Use these docs for dispatch:

- `docs/waves/wave_70_0/team_a_prompt.md`
- `docs/waves/wave_70_0/team_b_prompt.md`
- `docs/waves/wave_70_0/team_c_prompt.md`
- `docs/waves/wave_70_5/team_a_prompt.md`
- `docs/waves/wave_70_5/team_b_prompt.md`
- `docs/waves/wave_70_5/team_c_prompt.md`

The original prompts in `docs/waves/wave_70/` are retained only as an
archival first draft.
