# Frontend Changelog

**Build verified:** 2026-03-12 via `npm run build`
**Bundle:** `dist/assets/index-DHU-n_UD.js` 100.32 kB raw / 25.02 kB gzip
**Total frontend source:** 2,262 LOC across `frontend/src/`
**Total custom elements:** 19 across 14 component files

## Wave 3 - Transport + Core Views

### Delivered files
- `frontend/src/ws/client.ts` (109 LOC) - reconnecting WebSocket client with message and connection-state subscriptions.
- `frontend/src/state/store.ts` (173 LOC) - reactive operator store driven by `state` and `event` WS frames.
- `frontend/src/components/formicos-app.ts` (292 LOC) - application shell, sidebar navigation, top bar, cross-view routing, and protocol status display.
- `frontend/src/components/tree-nav.ts` (63 LOC) - tree navigator for workspaces, threads, and colonies.
- `frontend/src/components/thread-view.ts` (144 LOC) - thread workspace with merge, prune, broadcast, and spawn actions.
- `frontend/src/components/queen-chat.ts` (108 LOC) - multi-thread Queen chat surface and event timeline rendering.

### Notes
- Wave 3 source total: 889 LOC.
- `formicos-app.ts` intentionally exceeded the 200 LOC soft cap because it is the shell that composes every major surface.

## Wave 4 - Operational Views

### Delivered files
- `frontend/src/components/colony-detail.ts` (172 LOC) - colony metrics, topology, agent table, pheromone display, and embedded Queen chat.
- `frontend/src/components/queen-overview.ts` (121 LOC) - supercolony dashboard, approvals, active colonies, and global resource rollups.
- `frontend/src/components/breadcrumb-nav.ts` (29 LOC) - breadcrumb navigation for tree traversal.
- `frontend/src/components/approval-queue.ts` (48 LOC) - HITL approval cards and decision affordances.
- `frontend/src/components/round-history.ts` (56 LOC) - round timeline and execution history view.

### Notes
- Wave 4 source total: 426 LOC.

## Wave 5 - Configuration Views

### Delivered files
- `frontend/src/components/workspace-config.ts` (104 LOC) - workspace overrides, governance display, and per-thread rollups.
- `frontend/src/components/model-registry.ts` (151 LOC) - local/cloud model inventory, status display, and cascade summary.
- `frontend/src/components/castes-view.ts` (94 LOC) - caste recipe browser and capability display.
- `frontend/src/components/settings-view.ts` (76 LOC) - event-store, coordination-strategy, and protocol settings surface.

### Notes
- Wave 5 source total: 425 LOC.

## Shared frontend infrastructure

- `frontend/src/components/atoms.ts` (181 LOC) - shared `fc-dot`, `fc-pill`, `fc-meter`, `fc-btn`, `fc-defense-gauge`, and `fc-pheromone-bar`.
- `frontend/src/styles/shared.ts` (87 LOC) - Void Protocol CSS custom properties and shared glass/utility styles.
- `frontend/src/types.ts` (247 LOC) - frontend-local mirror of the frozen contract shapes.
- `frontend/src/index.ts` (7 LOC) - application entry point.

## Deviations from the original split

- Tokens shipped in `frontend/src/styles/shared.ts` instead of a standalone `frontend/src/tokens.ts`.
- Atom components were consolidated into `frontend/src/components/atoms.ts` instead of a directory of per-atom files.
- The delivered frontend remains contract-compatible and builds clean with those packaging changes.
