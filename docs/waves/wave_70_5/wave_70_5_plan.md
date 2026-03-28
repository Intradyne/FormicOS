# Wave 70.5: Operator Trust Surface

**Status:** Dispatch-ready packet
**Predecessor:** Wave 70.0
**Theme:** Finish the UI wiring for the 70.0 contracts so MCP access,
project intelligence, and autonomy are visible, editable where appropriate,
and trustworthy to the operator.

## Packet Authority

This file is the dispatch overview. The prompts are the authority for
implementation detail:

- `docs/waves/wave_70_5/team_a_prompt.md`
- `docs/waves/wave_70_5/team_b_prompt.md`
- `docs/waves/wave_70_5/team_c_prompt.md`

## Locked Boundaries

- No new event types.
- No new projection fields.
- No new core autonomy/MCP/project-plan logic in this packet unless a tiny
  payload expansion is absolutely required for rendering.
- No new nav surfaces. Use existing settings, overview, and proposal surfaces.
- One owner for `settings-view.ts`: Team C.

## Scope

| Track | Outcome | Team |
|------|---------|------|
| 1 | MCP Servers card and config UX | A |
| 2 | Project Plan overview card | B |
| 3 | Autonomy card + settings integration | C |
| 4 | Proposal-card blast-radius rendering | C |

## Team Missions

### Team A - MCP Settings UX

Own the MCP server management leaf component. Build a real form-based surface
over the `70.0` bridge/config contracts. Do not own `settings-view.ts`.

### Team B - Project Visibility

Own the workspace-level project-plan card in the Queen overview. Use the
`70.0` endpoint; do not re-implement parsing in the browser.

### Team C - Trust Integration

Own the settings integration and proposal-card truth surface:

- mount Team A's MCP card
- mount the autonomy card
- render blast-radius truth in proposal cards

## Merge Order

Recommended merge order:

1. Team A
2. Team B
3. Team C

Why:

- Team A provides the MCP card that Team C mounts.
- Team B is independent.
- Team C is the integrator for `settings-view.ts` and proposal-card polish.

## Known Housekeeping

- `system-overview.ts` hardcodes the Queen tool count at 38 (line 34).
  Wave 70.0 adds at least 3 new tools. Team C owns this file and must
  update the count (or compute it dynamically).

## Acceptance Focus

- no raw JSON MCP configuration in the operator UI
- no frontend markdown parsing of project plans
- autonomy/trust shown from `70.0` endpoint data, not recomputed in the browser
- `settings-view.ts` has one owner (Team C)
- every `70.0` capability has an operator-visible seam in `70.5`
- `types.ts` additions are additive only (Team C owns blast-radius type)

## Validation

```bash
npm run build
npm run lint  # if lint config exists
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

## Success Condition

Wave 70.5 succeeds if the operator can:

- connect and inspect MCP servers without typing raw JSON
- see the workspace project plan from the overview surface
- inspect autonomy level, trust score, and budget remaining in settings
- understand blast radius directly on proposal cards
