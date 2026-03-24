# Wave 55: Truth-First UX -- Dispatch Pack

This folder contains the dispatch-ready prompts for Wave 55.

Wave 55 goal:
- make progress detection truthful
- make existing intelligence visible to the operator
- raise capability with low-churn provider/model improvements
- do all of that without a new self-experimentation engine

Guiding constraint:
**show signals the system already computes or can derive from existing events; do not invent new subsystems.**

## Parallel Start Notes

All three teams can start immediately.

### Team 1 owns: Progress Truth
- `src/formicos/engine/runner.py`
- `src/formicos/engine/runner_types.py`
- `src/formicos/surface/colony_manager.py` only if stall tracking must be adjusted
- targeted backend tests

### Team 2 owns: Operator Visibility
- `frontend/src/components/queen-overview.ts`
- `frontend/src/components/knowledge-browser.ts`
- `frontend/src/components/learning-card.ts` if created
- `frontend/src/types.ts`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/view_state.py`
- `src/formicos/surface/routes/api.py` for knowledge-usage and learning-summary endpoints

### Team 3 owns: Capability + Playbook Visibility
- `config/formicos.yaml`
- `src/formicos/adapters/llm_openai_compatible.py`
- `.env.example`
- `docker-compose.yml` only if local-model evaluation needs it
- `frontend/src/components/playbook-view.ts`
- `src/formicos/engine/playbook_loader.py`
- `src/formicos/surface/routes/api.py` for playbook-listing endpoint only

## Controlled overlap

Team 2 and Team 3 both touch `src/formicos/surface/routes/api.py`.

Safe split:
- Team 2 owns:
  - knowledge usage response enrichment
  - `GET /api/v1/workspaces/{workspace_id}/learning-summary`
- Team 3 owns:
  - `GET /api/v1/playbooks`

Append new route helpers cleanly and do not rewrite existing route groups.

## Explicit non-goals

Do not reopen:
- playbook YAML content
- quality formula v2
- eval harness
- knowledge catalog scoring/retrieval
- event type additions

Additive event fields are also discouraged here unless a team can show that replay-safe derivation from existing events is impossible.

## Success condition for the wave

After Wave 55, the operator should be able to:
- trust that productive planning/coding rounds are not mislabeled as stalls
- see whether a colony was productive or spinning
- see whether knowledge actually helped
- see the operational playbooks guiding agents
- see real provider/model options in the system

## Prompt files

- [Team 1 Prompt](c:/Users/User/FormicOSa/docs/waves/wave_55/team_1_progress_truth.md)
- [Team 2 Prompt](c:/Users/User/FormicOSa/docs/waves/wave_55/team_2_operator_visibility.md)
- [Team 3 Prompt](c:/Users/User/FormicOSa/docs/waves/wave_55/team_3_capability_and_playbook_visibility.md)
