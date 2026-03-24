You own the Wave 50 cross-workspace knowledge frontend and template UX track.

This is the operator-surface track. You are not inventing new learning
substrate or retrieval logic. Your job is to make the operator see and control
the learning that Team 1 builds: template suggestions in preview cards, global
knowledge indicators, and explicit promotion affordances.

## Mission

Land the frontend-heavy parts of Wave 50:

1. template annotation on preview cards
2. learned vs operator template indicators in config memory
3. global scope indicators in knowledge browser
4. explicit "Promote to Global" affordance
5. auto-promotion candidate flagging (Should)

The core rule still applies:

**If the benchmark disappeared tomorrow, would we still want this change in
FormicOS?**

Yes. Operators want to see why the system is recommending a particular team
shape and control what knowledge crosses project boundaries.

## Read First

1. AGENTS.md
2. CLAUDE.md
3. docs/waves/wave_50/wave_50_plan.md
4. docs/waves/wave_50/acceptance_gates.md
5. frontend/src/components/fc-preview-card.ts
6. frontend/src/components/config-memory.ts
7. frontend/src/components/knowledge-browser.ts
8. frontend/src/state/store.ts
9. frontend/src/types.ts

Before editing, reread Team 1's final additive fields and projection shapes.
The frontend must follow repo truth, not the original wave sketch.
Team 1 is authoritative for shared contract/type shapes, especially
frontend/src/types.ts and backend route payloads. Build against Team 1's
landed shape rather than editing shared contract files in parallel.

## Owned Files

- frontend/src/components/fc-preview-card.ts
- frontend/src/components/config-memory.ts
- frontend/src/components/knowledge-browser.ts
- frontend/src/state/store.ts
- targeted frontend/store tests

## Do Not Touch

- backend Python files
- src/formicos/core/events.py
- src/formicos/surface/projections.py
- frontend/src/types.ts
- config/caste_recipes.yaml
- docs files

Team 1 owns all backend learning and scope plumbing. Team 3 owns docs truth.

## Required Work

### Track A: Template Annotation On Preview Cards

When Team 1's template-aware preview includes template metadata:

- show "Based on previous success: [template name]" on the preview card
- show success/failure rate if available
- make it clear the template is a suggestion, not an override

If template metadata is absent, render the preview card normally.

### Track B: Config Memory Template Surface

config-memory.ts currently shows outcome-derived recommendations. Extend it:

- show learned templates alongside operator templates
- distinguish them visually (badge or label)
- show success_count / failure_count / use_count for learned templates
- show task_category so the operator knows when this template applies

### Track C: Knowledge Browser Global Scope

When Team 1's global scope lands:

- show a scope badge on each knowledge entry: Thread | Workspace | Global
- add a "Promote to Global" button on workspace-scoped entries
- call Team 1's backend promotion route on promotion
- show a confirmation before promoting

Important:

- do not fabricate MemoryEntryScopeChanged directly in the frontend
- reuse the existing knowledge promotion surface extended by Team 1
- if the backend route shape changes slightly, follow Team 1's landed seam
  rather than the original packet wording

### Track D: Auto-Promotion Candidate Indicators (Should)

If Team 1 surfaces promotion candidates:

- show a subtle indicator on qualifying entries
- include a "Promote?" affordance
- keep it non-intrusive

### Track E: Store Integration

Extend store.ts to handle:

- learned template stats from projection updates
- global-scoped memory entries
- promotion request / optimistic-state handling only if Team 1's route
  contract makes that clean

## Hard Constraints

- Do not fabricate template stats or scope indicators
- Do not auto-promote entries from the frontend
- Do not fabricate backend events from the frontend
- Do not rebuild config-memory or knowledge-browser from scratch
- Do not add backend logic

## Validation

Run at minimum:

1. frontend build / type-check path
2. targeted tests for template annotation rendering
3. targeted tests for scope badge and promotion flow

## Summary Must Include

- how template annotation appears on preview cards
- how learned vs operator templates are distinguished
- how global scope is indicated in the knowledge browser
- whether Promote to Global shipped and which backend route it uses
- whether auto-promotion candidate flagging shipped
- what you kept out to stay bounded
