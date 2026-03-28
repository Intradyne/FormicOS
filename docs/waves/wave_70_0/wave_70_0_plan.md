# Wave 70.0: Operational Flexibility

**Status:** Dispatch-ready packet
**Predecessor:** Wave 69
**Theme:** Land the backend/control-plane substrate for MCP access,
project-level intelligence, and earned autonomy without forcing half-finished
UI into the same merge window.

## Packet Authority

This file is the dispatch overview. The prompts are the authority for
implementation detail:

- `docs/waves/wave_70_0/team_a_prompt.md`
- `docs/waves/wave_70_0/team_b_prompt.md`
- `docs/waves/wave_70_0/team_c_prompt.md`

## Locked Boundaries

- No new event types. No changes to the closed event union.
- No new projection fields.
- No retrieval/scoring math changes except the Queen context budget carve-out
  needed for project-plan injection.
- No operator-surface buildout in this packet beyond additive REST/status/meta
  contracts that `70.5` will consume.
- Every new capability must land with a stable machine-readable seam:
  endpoint, metadata payload, or addon summary field. `70.5` should not need
  to parse backend internals.

## Scope

| Track | Outcome | Team |
|------|---------|------|
| 1 | MCP bridge addon core + remote tool calls | A |
| 2 | Dynamic MCP tool discovery + `discover_mcp_tools` | A |
| 3 | Generic bridge health exposure for Queen/addon summaries | A |
| 4 | Project plan parser/helper + milestone tools | B |
| 5 | `GET /api/v1/project-plan` + dedicated `project_plan` budget slot | B |
| 6 | Project-plan injection for new conversations | B |
| 7 | Daily autonomy budget visibility + `check_autonomy_budget` | C |
| 8 | Blast radius estimator + proposal metadata | C |
| 9 | Autonomy scoring + `GET /api/v1/workspaces/{id}/autonomy-status` | C |

## Team Missions

### Team A - MCP Bridge Substrate

Own the external-tool seam:

- bridge remote MCP servers into the addon system
- expose discovered tools to the Queen cleanly
- report bridge health generically, without hardcoded addon-name checks
- make bridge status visible through machine-readable backend seams that
  `70.5` can consume

### Team B - Project Intelligence Substrate

Own the project-wide planning seam:

- store and update one project plan per data root
- parse it from a single shared helper, not ad hoc regexes everywhere
- give the Queen a dedicated project-plan context budget
- expose a read endpoint that `70.5` can render directly

### Team C - Autonomy Trust Substrate

Own the autonomy/trust seam:

- daily budget truth
- blast radius estimation
- graduated autonomy scoring
- stable proposal/status metadata and one read endpoint for `70.5`

## Merge Order

All three teams can develop in parallel. Recommended merge order:

1. Team B
2. Team C
3. Team A

Why:

- Team B changes the Queen context budget contract and project-plan endpoint.
- Team C adds the autonomy-status contract and proposal metadata.
- Team A is backend-heavy but mostly orthogonal, and its addon-summary/health
  shaping can merge last once the core runtime contracts are stable.

## Shared Seams

- `src/formicos/surface/queen_tools.py` is shared by all three teams:
  additive tool handlers only. Each team adds handlers to `_handlers` dict
  (near line 198) and tool specs before `*self._addon_tool_specs` (line 1411).
  All additions are self-contained — no team modifies another team's handlers.
- `src/formicos/surface/routes/api.py` is shared by all three teams:
  additive route sections only. Team A expands the existing `/api/v1/addons`
  handler. Teams B and C add new endpoints to the route table (lines 1600–1720).
- `src/formicos/surface/queen_runtime.py` is shared by Teams A and B only:
  Team A owns the deliberation frame addon coverage section (lines 1456–1495),
  Team B owns the project-plan injection block (insert between lines 953–955).
  Team C does not touch this file.
- `config/caste_recipes.yaml` is shared by all three teams:
  tool list only. Append new tool names to the Queen tools array (line 207).
  No system-prompt rewrite in this packet. Merge order matters — last team
  to merge should verify all tools are present and the count is correct.

## Acceptance Focus

- no hardcoded `if addon_name == "mcp-bridge"` routing
- bridge health exposed through reusable backend seams
- project plan has a dedicated Queen context budget, not shared with
  `project_context.md`
- `GET /api/v1/project-plan` returns structured data from a shared parser
- `GET /api/v1/workspaces/{id}/autonomy-status` returns structured trust data
- proposal metadata carries blast-radius/autonomy truth for `70.5`
- no operator-surface work required to validate the backend packet

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

## Success Condition

Wave 70.0 succeeds if `70.5` can be mostly frontend work:

- no UI needs to parse markdown files directly
- no UI needs to inspect runtime internals directly
- no UI needs hardcoded addon-name heuristics for MCP health
- all three new capabilities are exposed through stable contracts
