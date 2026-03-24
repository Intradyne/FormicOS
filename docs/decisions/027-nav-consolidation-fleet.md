# ADR-027: Nav Consolidation -- Fleet Tab

**Status:** Accepted
**Date:** 2026-03-14
**Context:** Wave 15. Aligning the live frontend nav with the v3 visual spec.

---

## Decision

Merge the existing Models and Castes tabs into a single "Fleet" tab with internal sub-tabs.

## Context

The v3 prototype specifies 5 navigation tabs: Queen, Knowledge, Templates, Fleet, Settings.

The live frontend (post-Wave 12/14) has 6 tabs: Queen, Knowledge, Templates, Models, Castes, Settings.

Models and Castes are closely related -- both concern the agent compute layer. Separating them adds a tab that doesn't carry its weight for a typical operator workflow. The operator configures models and castes together, not independently.

## Implementation

Create `frontend/src/components/fleet-view.ts` that:
- Contains two internal sub-tabs: "Models" and "Castes"
- Renders the existing `fc-model-registry` and `fc-castes-view` components
- Defaults to "Models" sub-tab

Update `formicos-app.ts`:
- Replace `models` and `castes` ViewId entries with `fleet`
- Update NAV array to 5 entries
- Route `fleet` view to `fc-fleet-view`

## Why not a deeper merge?

The model registry and castes view are functionally distinct components with different data sources and interaction patterns. Merging them into a single component would increase complexity without improving UX. The Fleet tab is a navigation container, not a feature merge.

## Alternatives considered

**Keep 6 tabs:** Works but doesn't match the visual spec, and the extra tab adds noise for operators who rarely change caste configs independently of model assignments.

**Drop Castes entirely:** Too aggressive. Caste configuration is genuinely useful for power users and becomes more important as template customization grows.
