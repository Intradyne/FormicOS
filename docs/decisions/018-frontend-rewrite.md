# ADR-018: Frontend Rewrite — Luminous Void v2.1

**Status:** Accepted
**Date:** 2026-03-14
**Depends on:** ADR-003 (Lit Web Components), ADR-015 (Event Union Expansion), ADR-016 (Colony Templates), ADR-017 (Bayesian Confidence)

## Context

The current frontend was built incrementally across Waves 3-5 (shell + 7 views) and extended in Waves 8-11 (quality dots, routing badges, skill browser, colony creator, template browser). It works, but it was built before the backend had most of its current capabilities. The result is a developer dashboard — functional, but not something an operator who didn't build the system could use effectively.

Wave 11 completed the backend. The system now has 27 event types, 3 LLM providers, config-driven routing, Bayesian skill confidence, LLM dedup, colony templates, Queen naming, suggest-team, and full REST+WS API coverage. Every data surface the operator needs is available. The frontend doesn't surface most of it.

A v2.1 React prototype (1509 lines, `docs/prototype/formicos-v2.jsx`) was built to spec the full operator experience. It covers 16+ components with rich mock data matching the real backend contracts.

## Decision

### Upgrade the existing Lit frontend to match the v2.1 prototype

This is NOT a framework migration. The frontend stays as Lit Web Components with Vite. The existing infrastructure (`state/store.ts`, `ws/client.ts`, `styles/shared.ts`, `types.ts`) is retained and extended. Each existing component is upgraded in-place; new components are added.

### Three parallel teams, one serial Step 0

**Step 0 (serial, all teams):** Extract shared design primitives into importable files. The prototype defines atoms (`Pill`, `Dot`, `Meter`, `Btn`, `Glass`, `Sparkline`, `DefenseGauge`, `QualityDot`, `PheromoneBar`) and tokens (`V`, `F`, `PROVIDER_COLOR`) that all components import. These must be extracted before teams diverge, or every team will duplicate them.

Current `atoms.ts` already has some primitives. Step 0 extends it with the prototype's full set and ensures `shared.ts` tokens match the Luminous Void palette.

**Phase 1 (3 parallel teams):**
- **Team A** — Core Shell + Real-Time (AppShell, TreeNav, QueenChat, QueenOverview)
- **Team B** — Colony Lifecycle + Topology (ColonyDetail, RoundTimeline, TopologyGraph, ColonyCreator, ThreadView)
- **Team C** — Data Views + Config (SkillBrowser, TemplateBrowser, ModelRegistry, CastesView, WorkspaceConfig, Settings)

### No backend changes

Every endpoint and event type already exists. Wave 12 is frontend-only. The backend is frozen for this wave — no new events, no new REST routes, no new WS commands. If a frontend component discovers a missing backend field, it handles the absence gracefully (nullish coalescing, empty state) rather than requesting a backend change.

### The prototype is the visual spec

The v2.1 prototype replaces written specs for this wave. Each team's components must match the prototype's visual output, data wiring, and interaction patterns. The prototype's mock data shapes match `docs/contracts/types.ts`.

## Consequences

- Frontend components grow from 17 to ~20 files (some components merge, some split)
- Bundle size will increase — target < 60KB gzip (currently ~28KB)
- Every model reference in the UI shows provider-colored dots (green/blue/amber)
- Colony cards everywhere show `displayName` with UUID subtitle
- Skill browser shows ± uncertainty bars with α/β on hover
- Colony detail gets expandable round-by-round history with per-agent output
- Queen chat is always accessible as a collapsible panel
- Colony creation is a 3-step flow with suggest-team and template selection
- No backend changes — this is a frontend-only wave
