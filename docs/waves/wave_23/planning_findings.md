# Wave 23 Planning Findings

**Wave:** 23 - "Operator Smoothness + External Handshake"  
**Purpose:** Repo-accurate findings that shaped the final Wave 23 plan.

---

## Finding 1: AG-UI is spawn-and-stream only

`POST /ag-ui/runs` in `agui_endpoint.py` spawns a new colony and streams that run.

It does not:
- attach to an existing colony
- accept a colony id for subscription
- serve as a general event stream for work spawned elsewhere

**Implication:** Wave 23 A2A must stay poll/result only unless it explicitly adds a separate attach/events endpoint.

---

## Finding 2: The route split already happened

The surface route split from Wave 21 is already live:
- `routes/api.py`
- `routes/colony_io.py`
- `routes/protocols.py`
- `routes/health.py`

**Implication:** Wave 23 docs should not talk about `app.py` as if the old extraction work is still pending.

---

## Finding 3: Colony detail already has the data needed for progress and outcome-first UI

The snapshot already exposes:
- `round`
- `maxRounds`
- `rounds`

No backend change is needed to:
- show `Round N / M`
- render a thin progress bar
- lead with the latest round output

**Implication:** Track A can stay mostly frontend-only.

---

## Finding 4: The existing empty-state pattern is reusable

The frontend already uses `.empty-hint` in a few places.

**Implication:** Track A should reuse that pattern for consistency rather than invent a new empty-state component.

---

## Finding 5: The first-run welcome still lives in app lifespan/bootstrap

The first-run welcome Queen message is already emitted from the app bootstrap path in `app.py`.

**Implication:** The first-run improvement is a text change, not a structural feature.

---

## Finding 6: Queen follow-up is still flat

`follow_up_colony()` in `queen_runtime.py` currently reports a summary, but the language does not meaningfully change by quality band.

**Implication:** Quality-aware follow-up is a good deterministic win for Track B.

---

## Finding 7: Queen notes already inject into future interactions

`_build_messages()` in `queen_runtime.py` already loads and injects thread-scoped Queen notes.

**Implication:** A save-preference interaction only needs a reliable save path. No extra context plumbing is required.

---

## Finding 8: commands.py is the right WS command surface

The repo already has `src/formicos/surface/commands.py` as the WebSocket command dispatch layer.

**Implication:** A `save_queen_note` command belongs there. The implementation should reuse the Queen's existing note-save logic rather than create a second persistence path.

---

## Finding 9: The browser smoke exists, but the runner story is still manual

The Playwright spec lives at:
- `tests/browser/smoke.spec.ts`

The Playwright package lives under:
- `frontend/package.json`

**Implication:** If the smoke runner is exposed through `frontend/package.json`, the path should be `../tests/browser/smoke.spec.ts`. A script pointing at `tests/browser/smoke.spec.ts` from the frontend directory is wrong.

---

## Finding 10: A2A should use async template loading

`load_templates()` is asynchronous.

**Implication:** The A2A submit handler should `await load_templates()` first, then pass the loaded templates into a deterministic team-selection helper. Do not use `run_until_complete` inside the route logic.

---

## Finding 11: A dedicated A2A workspace is the wrong default

Scoped memory and workspace library are workspace-local. Putting A2A work in a separate workspace would isolate those tasks from operator context by default.

**Implication:** The safer Wave 23 default is:
- normal workspace
- dedicated A2A-style thread naming

---

## Finding 12: The current validated baseline is 1321 passing tests

The most recent local validation baseline is:
- `python -m pytest -q` -> `1321 passed`

**Implication:** The docs should still say "full pytest suite green" rather than hard-code the count as an acceptance gate, because that number will drift.
