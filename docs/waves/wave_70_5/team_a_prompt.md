# Wave 70.5 - Team A: MCP Settings UX

**Theme:** Turn the 70.0 MCP bridge contract into a usable operator surface.

## Context

Read `docs/waves/wave_70_5/wave_70_5_plan.md` first. Assume `70.0` landed:

- `/api/v1/addons` can expose bridge health additively
- addon config routes exist
- MCP bridge stores server config through the addon config path

You are building the leaf UI component only. Team C owns `settings-view.ts`.

### Key seams to read before coding

- `settings-view.ts` — card sections use `.settings-card` class
  (`background: var(--v-surface)`, `border: 1px solid var(--v-border)`,
  `border-radius: 10px`, `padding: 16px 20px`). Each section is a private
  `_render*Card()` method mounted in `render()`. Team C will mount your
  card; you just export a self-contained `<fc-mcp-servers-card>`.
- `addons-view.ts` — read-only addon status/trigger view (lines 1–221).
  Not the right place for MCP config. Your card goes in settings.
- `routes/api.py` — addon config: `GET /api/v1/addons/mcp-bridge/config?workspace_id=...`
  and `PUT /api/v1/addons/{addon_name}/config` (line 1664). Addon summary:
  `GET /api/v1/addons` (line 1295).
- `styles/shared.ts` — Void Protocol tokens: `--v-surface`, `--v-border`,
  `--v-fg`, `--v-fg-muted`, `--v-accent`, `--v-success`, `--v-danger`,
  `--f-mono`. Glass card: `.glass` class (line 82).

## Your Files (exclusive ownership)

- `frontend/src/components/mcp-servers-card.ts` — **new**
- `frontend/src/styles/shared.ts` or atoms only if a tiny additive style atom is needed
- `frontend/src/components/addons-view.ts` only if a small deep-link/help affordance is needed

## Do Not Touch

- `frontend/src/components/settings-view.ts` - Team C owns
- `frontend/src/components/queen-overview.ts` - Team B owns
- `frontend/src/components/proposal-card.ts` - Team C owns
- backend files unless a tiny addon-summary payload expansion is truly required

## Overlap Coordination

- Team C will mount `<fc-mcp-servers-card>` inside settings.
- Keep the component self-contained: let it fetch its own data rather than
  requiring shared store changes.

---

## Goal

Build a real MCP server management card so the operator never has to type raw
JSON to configure bridge servers.

## Requirements

### Data sources

Use existing `70.0` contracts:

- `GET /api/v1/addons`
- `GET /api/v1/addons/mcp-bridge/config?workspace_id=...`
- `PUT /api/v1/addons/mcp-bridge/config`

If bridge health is present in addon summaries, render it. If not, fall back
to config-only presentation without inventing runtime inspection in the browser.

### UI

Create `fc-mcp-servers-card` as a glass-card section that renders:

- connected servers list
- server name
- URL
- health dot/status
- discovered tool count if available
- last connected / last error if available
- Add Server inline form
- Disconnect / Remove actions

### Write behavior

The UI may still persist the server list through the addon config route, but it
must present it as structured fields:

- `name`
- `url`
- optional transport/options if supported

No raw JSON textarea.

### Empty states

- no bridge installed
- bridge installed but no servers configured
- server configured but unhealthy

## Acceptance Gates

- [ ] `fc-mcp-servers-card` exists as a self-contained component
- [ ] no raw JSON entry in the operator UI
- [ ] reads from existing addon/bridge contracts
- [ ] writes through existing addon config route
- [ ] health is shown honestly when available
- [ ] component is ready for Team C to mount without store work

## Validation

```bash
npm run build
npm run lint  # if lint config exists
```
