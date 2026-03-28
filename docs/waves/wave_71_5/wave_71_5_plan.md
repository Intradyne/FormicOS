# Wave 71.5: Mission Control Surface

**Status:** Dispatch-ready packet
**Predecessor:** Wave 71.0
**Theme:** Turn the operational loop into a dedicated operator surface instead
of scattering it across Settings, Overview, and chat.

## Packet Authority

Use these docs:

- `docs/waves/wave_71_0/design_note.md` — invariants that apply to both halves
- `docs/waves/wave_71_5/team_a_prompt.md`
- `docs/waves/wave_71_5/team_b_prompt.md`
- `docs/waves/wave_71_5/team_c_prompt.md`

## Locked Boundaries

- One new top-level surface: `Operations`.
- One owner for `operations-view.ts`: Team A.
- Use `71.0` endpoints and files; do not re-derive backend state in the browser.
- Keep existing Queen overview and Settings concise; the new operational loop
  should live primarily in the Operations tab.

## Scope

| Track | Outcome | Team |
|------|---------|------|
| 1 | Operations tab shell + nav integration | A |
| 2 | Action inbox/history + continuation review | B |
| 3 | Journal panel + procedures editor + ops summary card | C |

## Team Missions

### Team A - Operations Shell

Own the new tab and layout. Mount Team B and Team C leaf components. Do not
rebuild their internals.

### Team B - Action Review

Own the operator inbox:

- pending actions
- recent automatic actions
- continuation proposals
- future action kinds without an inbox redesign
- approve/reject workflow with reasons

### Team C - Operational Memory Surfaces

Own the human-readable operational surfaces:

- journal panel
- procedures editor
- compact operational summary card

## Merge Order

Recommended merge order:

1. Team B
2. Team C
3. Team A

Why:

- Team B and Team C create the leaf components.
- Team A integrates them in one Operations surface and nav path.

## Known Housekeeping

- `formicos-app.ts` line 62: `grid-template-columns: repeat(7, ...)` — must
  become `repeat(8, ...)` for the new Operations tab.
- `formicos-app.ts` line 239: responsive breakpoint `repeat(5, ...)` — verify
  8 tabs still fit or adjust breakpoint.
- `ViewId` type union (line 27) needs `'operations'` added.
- `NAV` array (lines 29–37) needs the Operations entry.

## Acceptance Focus

- one clear home for the operational loop
- pending actions are reviewable without scanning chat
- inbox semantics come from action `kind` and `status`, not legacy approval
  labels
- rejection reasons are captured in the UI
- operator can inspect/edit procedures directly
- operator can see what happened while away via journal + summary
- browser does not parse markdown plans or runtime internals directly

## Validation

```bash
npm run build
npm run lint  # if lint config exists
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

## Success Condition

Wave 71.5 succeeds if the operator can open one tab and immediately answer:

- what is waiting on me
- what happened while I was away
- what the Queen plans to continue next
- what standing procedures are currently governing autonomous behavior
