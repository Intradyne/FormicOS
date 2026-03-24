# Wave 23 Dispatch Prompts

Three parallel coder prompts for the final Wave 23 plan.

If `AGENTS.md` still lags behind the wave, treat the Wave 23 plan and these prompts as the authority for this dispatch.

---

## Team 1 - Track A: Operator Experience Polish

```text
You are Coder 1 for Wave 23. Your track is "Operator Experience Polish."

Read first, in order:
1. C:\Users\User\FormicOSa\CLAUDE.md
2. C:\Users\User\FormicOSa\AGENTS.md
3. C:\Users\User\FormicOSa\docs\waves\wave_23\plan.md
4. C:\Users\User\FormicOSa\docs\waves\wave_23\algorithms.md

Deliver exactly these tickets:

A1. Deliberate empty states
- queen-chat.ts: add a clear empty state when there are no messages
- knowledge-view.ts: add empty states for Skills and Library
- thread-view.ts: add empty state when a thread has no colonies
- round-history.ts: add empty state when no rounds exist
- colony-detail.ts: when a colony is running but has no completed rounds yet, show progress instead of emptiness

A2. First-run welcome refinement
- update the first-run Queen welcome text in src/formicos/surface/app.py
- suggest concrete tasks
- mention Knowledge -> Library
- keep it short

A3. Colony detail should lead with outcome
- completed colonies: add a prominent Final Output section using the latest entries from c.rounds
- running colonies: show Round N / M plus a thin progress bar using c.round and c.maxRounds

A4. Browser smoke runner story
- add a smoke script in frontend/package.json
- because the test file is at repo-root tests/browser/smoke.spec.ts, the script path from frontend must use ../tests/browser/smoke.spec.ts
- document the run flow in CONTRIBUTING.md
- do not add a bash-only script

Key constraints:
- Reuse existing empty-state and surface styles where possible
- No backend changes other than the first-run welcome text in app.py
- Do not redesign components
- c.rounds, c.round, and c.maxRounds already exist in the frontend snapshot shape

Files you own:
- frontend/src/components/queen-chat.ts
- frontend/src/components/knowledge-view.ts
- frontend/src/components/thread-view.ts
- frontend/src/components/round-history.ts
- frontend/src/components/colony-detail.ts
- src/formicos/surface/app.py (welcome text only)
- frontend/package.json
- CONTRIBUTING.md

Do not touch:
- Python backend files outside app.py
- config/*
- routes/*
- docker-compose.yml
- Dockerfile

Validation:
- cd frontend && npm run build
```

---

## Team 2 - Track B: Queen Composition + Behavior Guardrails

```text
You are Coder 2 for Wave 23. Your track is "Queen Composition + Behavior Guardrails."

Read first, in order:
1. C:\Users\User\FormicOSa\CLAUDE.md
2. C:\Users\User\FormicOSa\AGENTS.md
3. C:\Users\User\FormicOSa\docs\waves\wave_23\plan.md
4. C:\Users\User\FormicOSa\docs\waves\wave_23\algorithms.md

Important overlap rule:
- Coder 1 touches frontend/src/components/queen-chat.ts first for empty states
- reread queen-chat.ts before editing it

Deliverables:

B1. Prior work surfacing on spawn
- in queen_runtime.py, after a colony is spawned, query workspace memory plus skill bank for top related hits
- append those hits to the spawn confirmation message
- this is post-decision surfacing only
- do not hardcode a numeric relevance threshold
- include provenance where available
- spawn must still work normally if search returns nothing or errors

B2. Quality-aware follow-up text
- branch follow_up_colony() on quality band
- high quality: positive summary
- medium quality: completed, may benefit from review
- low quality: suggest retry or a different approach
- keep the existing recency/thread checks intact

B3. Save-as-preference path
- in queen-chat.ts, add a small save/pin affordance for Queen messages
- dispatch a save-queen-note event
- in formicos-app.ts, translate that event into a WS command
- in commands.py, add the command handler
- route through the Queen's existing note-save logic
- if needed, extract a tiny shared helper in QueenAgent so the WS command path and queen_note tool path reuse the same save implementation
- do not create a second persistence path

B4. Prompt refinement
- extend the Queen prompt in config/caste_recipes.yaml with multi-step workflow guidance
- add post-completion suggestions
- keep this additive, not a rewrite

Key constraints:
- no new Queen tools
- no autonomous multi-colony execution
- post-spawn prior work surfacing must be described honestly as post-decision
- save-preference should be operator-visible and deterministic

Files you own:
- src/formicos/surface/queen_runtime.py
- src/formicos/surface/commands.py
- frontend/src/components/queen-chat.ts
- frontend/src/components/formicos-app.ts
- config/caste_recipes.yaml

Do not touch:
- src/formicos/core/*
- src/formicos/engine/*
- src/formicos/surface/routes/*
- src/formicos/surface/transcript.py
- src/formicos/surface/agui_endpoint.py
- docker-compose.yml
- Dockerfile

Validation:
- python scripts/lint_imports.py
- python -m pytest -q
- cd frontend && npm run build
```

---

## Team 3 - Track C: Inbound A2A Task Lifecycle

```text
You are Coder 3 for Wave 23. Your track is "Inbound A2A Task Lifecycle."

Read first, in order:
1. C:\Users\User\FormicOSa\CLAUDE.md
2. C:\Users\User\FormicOSa\AGENTS.md
3. C:\Users\User\FormicOSa\docs\waves\wave_23\plan.md
4. C:\Users\User\FormicOSa\docs\waves\wave_23\algorithms.md
5. C:\Users\User\FormicOSa\docs\decisions\038-a2a-task-lifecycle.md

Deliverables:

C1. New route module
- create src/formicos/surface/routes/a2a.py
- add:
  - POST /a2a/tasks
  - GET /a2a/tasks
  - GET /a2a/tasks/{task_id}
  - GET /a2a/tasks/{task_id}/result
  - DELETE /a2a/tasks/{task_id}

C2. Deterministic team selection
- load templates asynchronously with await load_templates()
- use deterministic template match first
- use simple keyword heuristics second
- safe fallback last
- do not call the Queen LLM internally

C3. Transcript-backed results
- GET /a2a/tasks/{task_id}/result must call build_transcript()
- do not recreate transcript shaping

C4. Agent Card and registry
- advertise A2A in routes/protocols.py
- wire the new route module through routes/__init__.py and app.py
- add A2A protocol entry to the capability registry construction path

C5. A2A docs
- create docs/A2A-TASKS.md
- include request/response shapes
- include deterministic team-selection rules
- explicitly state that A2A is poll/result only in Wave 23

Key constraints:
- tasks are colonies
- task_id = colony_id
- normal workspace by default
- use dedicated A2A-style thread names, not a separate workspace
- do not advertise streaming
- do not add stream_url
- do not touch AG-UI

Files you own:
- src/formicos/surface/routes/a2a.py
- src/formicos/surface/routes/__init__.py
- src/formicos/surface/routes/protocols.py
- src/formicos/surface/app.py
- docs/A2A-TASKS.md

Do not touch:
- src/formicos/core/*
- src/formicos/engine/*
- src/formicos/surface/queen_runtime.py
- src/formicos/surface/agui_endpoint.py
- src/formicos/surface/transcript.py
- frontend/*
- docker-compose.yml
- Dockerfile

Validation:
- python scripts/lint_imports.py
- python -m pytest -q
```
