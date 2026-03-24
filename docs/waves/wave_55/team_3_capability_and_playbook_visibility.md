# Team 3: Capability + Playbook Visibility

You own the low-churn capability upgrades and the read-only playbook visibility surface.

Two lanes:
- capability
- playbook visibility

They should stay bounded and reversible.

## Mission

Deliver the cheapest real capability expansion and make operational playbooks visible in the UI without turning them into a new live editing surface.

## Read first

1. `config/formicos.yaml`
2. `src/formicos/adapters/llm_openai_compatible.py`
3. `.env.example`
4. `docker-compose.yml` only if local-model evaluation needs it
5. `frontend/src/components/playbook-view.ts`
6. `src/formicos/engine/playbook_loader.py`
7. `src/formicos/surface/routes/api.py`

## Sub-change A: Add MiniMax + DeepSeek providers

Add OpenAI-compatible registry entries in `formicos.yaml` for:
- MiniMax M2.7
- DeepSeek V3.2 / DeepSeek chat model as chosen in current config naming conventions

These should be real, usable registry entries, not placeholders.

Also update `.env.example` with the required API keys.

### MiniMax adapter nuance

If MiniMax needs `reasoning_split` to keep thinking output separate from tool-call content, add the smallest possible adapter tweak in `llm_openai_compatible.py`.

Keep it provider-specific and tiny.

## Sub-change B: Evaluate Qwen3-Coder locally

Check whether the required GGUF is already present locally.

If present:
- register it cleanly
- smoke it on moderate tasks
- compare parse reliability and quality against the current baseline

If not present:
- report `Blocked: model not downloaded`
- include the exact filename needed

This is an evaluation, not a commitment.
Do not widen into a model-migration project.

## Sub-change C: Playbook viewer (read-only)

Add a playbook-listing endpoint and a read-only playbook tab.

The operator should be able to see:
- task class
- targeted castes
- workflow
- steps
- productive tools
- observation tools
- example

This is **viewer before editor**.
Do not add playbook editing.

### Backend

Add a helper in `playbook_loader.py` to load all playbooks from disk for display.

Add:
- `GET /api/v1/playbooks`

to return the playbook list.

### Frontend

Add a `Playbooks` sub-tab in `playbook-view.ts`.

Render the playbooks as readable cards.
Do not make them interactive beyond viewing.

## Owned files

- `config/formicos.yaml`
- `src/formicos/adapters/llm_openai_compatible.py`
- `.env.example`
- `docker-compose.yml` only if needed for local-model evaluation
- `frontend/src/components/playbook-view.ts`
- `src/formicos/engine/playbook_loader.py`
- `src/formicos/surface/routes/api.py` for:
  - `GET /api/v1/playbooks`

## Do not touch

- `queen-overview.ts`
- `knowledge-browser.ts`
- `frontend/src/types.ts`
- `projections.py`
- `view_state.py`
- convergence/governance logic
- quality formula
- playbook YAML content
- event type definitions

## Acceptance bar

1. MiniMax and DeepSeek appear as real provider entries.
2. Any MiniMax-specific adapter tweak is minimal and isolated.
3. Qwen3-Coder is either evaluated or cleanly reported blocked by missing model file.
4. The Playbooks tab shows all operational playbooks read-only.
5. The playbook display is complete enough for an operator to understand what is guiding agents.
6. Frontend build passes.

## Summary must include

- which providers were added
- whether MiniMax needed adapter handling
- Qwen3-Coder availability and smoke outcome
- how playbooks are loaded and returned by the API
- confirmation that the playbook UI is read-only
