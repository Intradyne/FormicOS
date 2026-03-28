# Wave 70.5 - Team C: Trust Integration

**Theme:** Integrate the new trust surfaces into existing product UI with one
owner for settings and one owner for proposal-card truth.

## Context

Read `docs/waves/wave_70_5/wave_70_5_plan.md` first. Assume `70.0` landed:

- `GET /api/v1/workspaces/{id}/autonomy-status`
- proposal metadata can carry blast-radius truth
- Team A provides `<fc-mcp-servers-card>`

You own the integration surfaces:

- `settings-view.ts`
- `proposal-card.ts`

### Key seams to read before coding

- `settings-view.ts` — 6 existing card sections, each a `_render*Card()`
  method mounted at lines 391–408. Mount your new cards after the existing
  ones. Card class: `.settings-card` (lines 30–36). Data fetching in
  `connectedCallback()` (line 218).
- `proposal-card.ts` — `ProposalData` type (types.ts line 236: `summary`,
  `options`, `questions?`, `recommendation?`). Render structure: summary →
  options → questions → recommendation → bottom-actions. Blast-radius
  section goes between recommendation (line 178) and bottom-actions (line
  180). If `action.blast_radius` is absent, render unchanged.
- `types.ts` — extend `ProposalData` or add a sibling `BlastRadiusData`
  interface for the metadata that `70.0` Team C attaches.
- `system-overview.ts` — compact one-line summary (line 59). Queen tool
  count is **hardcoded at 38** (line 34). After 70.0 adds 3+ new tools,
  this needs updating — either hardcode the new count or compute it
  dynamically from the model registry.

## Your Files (exclusive ownership)

- `frontend/src/components/autonomy-card.ts` — **new**
- `frontend/src/components/settings-view.ts`
- `frontend/src/components/proposal-card.ts`
- `frontend/src/components/system-overview.ts` — tool count update
- `frontend/src/types.ts` — additive type additions only

## Do Not Touch

- `frontend/src/components/mcp-servers-card.ts` — Team A owns
- `frontend/src/components/project-plan-card.ts` and `queen-overview.ts` — Team B owns
- backend files unless a tiny presentational payload shim is absolutely required

## Overlap Coordination

- Team A delivers a self-contained MCP card. You mount it; you do not rewrite it.
- Keep settings integration centralized here so `settings-view.ts` has one owner.

---

## Track 3: Autonomy Card + Settings Integration

### Goal

Make autonomy visible and trustworthy from the settings surface.

### Requirements

Create `fc-autonomy-card` that fetches:

```text
GET /api/v1/workspaces/{id}/autonomy-status
```

Render:

- autonomy level
- trust score (0-100) plus grade
- daily budget/spend/remaining
- recent autonomous actions table (last 5)
- blast radius score/recommendation when available in recent actions

Then mount both:

- `<fc-mcp-servers-card>`
- `<fc-autonomy-card>`

inside `settings-view.ts`.

### Settings rules

- do not create a new view
- keep the existing settings layout language from Wave 69
- present autonomy as inspectable truth, not marketing copy

---

## Track 4: Proposal-Card Blast Radius

### Goal

When proposal metadata includes blast-radius/autonomy truth, render it inline
where the operator makes the decision.

### Requirements

Enhance `proposal-card.ts` so that when metadata includes blast-radius fields,
the card shows:

- blast radius score
- level (`low` / `medium` / `high`)
- top factors
- recommendation (`proceed` / `notify` / `escalate`)

This is additive. If the metadata is absent, render the existing card unchanged.

## Acceptance Gates

- [ ] `fc-autonomy-card` exists and is self-contained
- [ ] `settings-view.ts` mounts both the MCP and autonomy cards
- [ ] `proposal-card.ts` renders blast-radius truth when `action.blast_radius` present
- [ ] `proposal-card.ts` renders unchanged when blast-radius absent
- [ ] `system-overview.ts` tool count reflects new 70.0 tools
- [ ] `types.ts` extended with blast-radius type (additive only)
- [ ] no new nav/view sprawl
- [ ] one owner for `settings-view.ts`
- [ ] trust data comes from `70.0` contracts, not browser recomputation

## Validation

```bash
npm run build
npm run lint  # if lint config exists
```
