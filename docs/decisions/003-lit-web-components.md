# ADR-003: Lit Web Components for Frontend

**Status:** Accepted
**Date:** 2026-03-12

## Context
The frontend needs to render tree navigation, topology graphs, real-time event
streams, and operator controls. React is the default choice but adds a heavy
runtime, complex build tooling, and framework churn risk.

## Decision
Use Lit Web Components. Each component ≤200 lines. Web-native (no virtual DOM,
no framework runtime). Lit's reactive properties map naturally to event-sourced
state updates. TypeScript for type safety. The component registry and infrastructure
target ≤500 lines.

Frontend LOC target: ≤5,000 lines total.

## Consequences
- **Good:** Small bundle, fast rendering, web-native (works in any framework context).
- **Good:** No framework upgrade treadmill. Web Components are a platform standard.
- **Bad:** Smaller ecosystem than React. Fewer pre-built component libraries.
- **Bad:** Some developers are less familiar with Lit.
- **Acceptable:** FormicOS's UI is specialized enough that pre-built React components
  wouldn't save significant time anyway. The topology graph uses a dedicated library
  regardless of framework choice.

## FormicOS Impact
Affects: frontend/ directory entirely.
