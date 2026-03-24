# Team 2: Operator Visibility

You own the surfaces that make FormicOS explain itself to the operator.

Your packet is about visible truth:
- outcome cards should show productivity, not just quality
- the Queen overview should lead with system intelligence
- the Knowledge Browser should show what is actually being used
- the learning loop should be visible without extra navigation

## Mission

Make the operator’s first view answer:
- what happened
- what helped
- what is being learned
- what to do next

Do this using signals that are already present or derivable from existing events.

## Read first

1. `frontend/src/components/queen-overview.ts`
2. `frontend/src/components/knowledge-browser.ts`
3. `frontend/src/types.ts`
4. `src/formicos/surface/projections.py`
5. `src/formicos/surface/view_state.py`
6. `src/formicos/surface/routes/api.py`
7. `src/formicos/core/events.py` for `AgentTurnCompleted`

## Sub-change A: Colony outcome cards with productivity

### Backend

Derive productive and observation counts from existing `AgentTurnCompleted.tool_calls`.

Do **not** add new event fields if derivation is sufficient.

Add replay-derived counts to the colony projection:
- `productive_calls`
- `observation_calls`

Surface them in the view-state snapshot alongside:
- `entriesAccessed`
- existing quality/round/cost fields

### Frontend

Enrich colony cards in `queen-overview.ts` with:
- quality score
- productive / total call ratio
- knowledge-assisted badge when `entriesAccessed > 0`

Color the productivity badge so spinning colonies are visually distinct from productive ones.

## Sub-change B: Briefing-first Queen overview

Make the proactive briefing the hero section of the Queen overview.

It should render before the colony grid and feel like the first thing the operator should act on.

Add action buttons for at least three insight categories.

Examples:
- coverage -> open Queen chat with a research-oriented action
- stagnation -> inspect colony
- outcome_digest -> jump to outcomes/colony area
- learning_loop -> open playbook/template area

Prefer simple navigation/dispatch actions over complex new UI machinery.

## Sub-change C: Knowledge usage indicators

### Backend

Aggregate usage on knowledge entries from existing `KnowledgeAccessRecorded` events.

Expose:
- `usage_count`
- `last_accessed`

through the knowledge API responses already used by the browser.

### Frontend

Show a hot/warm/cold style badge on each knowledge entry:
- hot: heavily used
- warm: used sometimes
- cold: unused

Make zero-use entries visually honest, not silently equivalent to valuable entries.

## Sub-change D: Learning loop card

This team owns the Queen overview, so this team also owns the learning-card integration.

Add a compact learning card to the overview that shows:
- learned template count
- top template if any
- knowledge entry count
- recent quality trend

Use a lightweight visual treatment.
No charting library.
Handle empty state honestly.

Backend endpoint:
- `GET /api/v1/workspaces/{workspace_id}/learning-summary`

Keep the aggregation small and deterministic.

## Owned files

- `frontend/src/components/queen-overview.ts`
- `frontend/src/components/knowledge-browser.ts`
- `frontend/src/components/learning-card.ts` if created
- `frontend/src/types.ts`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/view_state.py`
- `src/formicos/surface/routes/api.py` for:
  - knowledge usage enrichment
  - learning-summary endpoint

## Do not touch

- `runner.py`
- `runner_types.py`
- `colony_manager.py`
- `playbook-view.ts`
- `playbook_loader.py`
- `formicos.yaml`
- adapter/provider logic
- event type definitions

## Acceptance bar

1. Colony cards show productive/total ratio.
2. Colony cards show a knowledge-assisted badge when applicable.
3. The proactive briefing renders first in the Queen overview.
4. At least three insight categories have working actions.
5. Knowledge entries show usage counts with hot/warm/cold styling.
6. The learning card renders with honest empty state.
7. Existing overview/browser behavior is not broken.
8. Frontend build passes.

## Summary must include

- how productive/observation counts are derived
- which projection handler owns the derivation
- which briefing categories got actions
- how knowledge usage is aggregated
- what the learning-summary endpoint returns
- confirmation that no new event fields were required
