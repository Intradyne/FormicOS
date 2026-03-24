# FormicOS v2 Frontend Prototype Brief

**Wave 12 deliverable.** This brief provides everything a UI designer needs to build a complete, interactive React prototype for FormicOS v2, reflecting the full backend capability after Waves 8-11.

## Files

- `ui-spec-proto.jsx` — Phase 1 prototype (7 views, original design system, pre-Wave 8 data shapes)
- `frontend-prototype-brief.md` — **Wave 12 brief.** Complete data surface reference, view specifications, interaction patterns, and mock data guidance for the new full frontend prototype.
- `ui-v2-proto.jsx` — *(to be created)* Full interactive prototype with all 16 views.

## How the brief works

The brief covers structure, data, views, and interactions. The operator provides visual style constraints separately. The designer builds a single-file React JSX prototype using the brief as the specification.

## What changed since Phase 1

| Wave | New backend capability | Frontend impact |
|------|----------------------|----------------|
| 8 | Quality scoring, skill crystallization, cost tracking | Quality dots, skills badge, real cost numbers |
| 9 | Compute routing, skill confidence, skill bank stats | Per-agent model column with provider colors, routing badges |
| 10 | Qdrant, Gemini provider, skill browser, defensive parsing | 3-provider visualization, browsable skill bank |
| 11 | Beta confidence, LLM dedup, colony templates, Queen naming, suggest-team | Multi-step colony creation, template browser, uncertainty bars, merge badges, display names |

## Views (16 total, up from 7)

1. Queen Overview (fleet dashboard)
2. Colony Detail (monitoring + round history + topology)
3. Colony Creator (multi-step: describe → configure → launch)
4. Thread View (colonies + merge edges)
5. Skill Browser (confidence bars + uncertainty + merge badges)
6. Template Browser (saved configs + use counts)
7. Model Registry (3 providers + routing table)
8. Workspace Config (overrides + governance)
9. Queen Chat (persistent panel, always accessible)
10. Approval Queue (pending operator decisions)
11. Settings (system config + protocol status)
12. Round Timeline (expandable per-round agent output)
13. Topology Graph (pheromone node-link diagram)
14. Tree Navigation (sidebar workspace → thread → colony)
15. Colony Card (compact card used in fleet + thread views)
16. App Shell (layout with sidebar, top bar, chat panel)
