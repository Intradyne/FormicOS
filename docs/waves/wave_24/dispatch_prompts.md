# Wave 24 Dispatch Prompts

Three parallel coder teams. Each prompt is copy/paste ready.

---

## Team 1 - Track A: Operator Truth

```text
You are Coder 1 for Wave 24. Your track is "Operator Truth."

Working directory:
C:\Users\User\FormicOSa

Read first, in order:
1. C:\Users\User\FormicOSa\CLAUDE.md
2. C:\Users\User\FormicOSa\AGENTS.md
3. C:\Users\User\FormicOSa\docs\waves\wave_24\plan.md
4. C:\Users\User\FormicOSa\docs\waves\wave_24\algorithms.md

Mission:
Fix the operator-facing surfaces that currently undermine trust: model naming, tree collapse, context explanation, VRAM units, aggregate budget wording, and colony display names.

Deliverables:

A1. Canonical model identity
- Keep the backend snapshot shape stable.
- In the model registry and overview surfaces, show the human-readable local model name prominently.
- Show the routing address as secondary information.
- Verify the existing backend probe path is already sending a usable human-readable name before changing anything.

A2. Tree collapse fix
- Reproduce the reported collapse bug live.
- Fix the actual interaction problem in tree-nav.ts.
- Remove any temporary debug logging before finishing.
- This ticket is not done until collapse is verified in the browser.

A3. Effective-vs-configured context explanation
- When effective context is lower than configured context, explain why in plain language.
- Replace cryptic fit-only wording with a short operator-facing explanation.

A4. VRAM normalization and display
- Normalize VRAM units in the backend probe path to MiB.
- Keep JSON field names stable (`usedMb`, `totalMb`).
- Render human-readable units in the frontend, using GiB where appropriate.
- Update all operator-visible VRAM surfaces, not just one.

A5. Aggregate budget truth
- Remove the misleading aggregate cost/budget denominator from summary surfaces.
- Show session cost only in top-level overview surfaces.
- Keep colony-level budget visible in colony detail; do not remove that.

A6. Colony display names
- Send colony display names through the tree snapshot.
- Prefer named colonies over raw ids in tree-derived views.

A7. Small trust cleanup
- Fix the stale context-size comment in config/formicos.yaml if it still contradicts the live 80k-era setup.

Owned files:
- src/formicos/surface/view_state.py
- src/formicos/surface/ws_handler.py (VRAM normalization only)
- frontend/src/components/model-registry.ts
- frontend/src/components/queen-overview.ts
- frontend/src/components/formicos-app.ts
- frontend/src/components/tree-nav.ts
- config/formicos.yaml

Do not touch:
- src/formicos/core/*
- src/formicos/engine/*
- src/formicos/surface/projections.py
- src/formicos/surface/agui_endpoint.py
- src/formicos/surface/routes/*
- src/formicos/surface/transcript.py
- frontend/src/components/colony-detail.ts
- docs/A2A-TASKS.md

Key constraints:
- This is a truth pass, not a redesign.
- Tree collapse must be live-verified, not assumed from code reading.
- VRAM JSON field names stay stable.
- Aggregate budget truth changes only top-level surfaces; per-colony budget remains.

Validation:
- python scripts/lint_imports.py
- python -m pytest -q
- cd frontend && npm run build
```

---

## Team 2 - Track B: A2A Attach + Shared Event Translation

```text
You are Coder 2 for Wave 24. Your track is "A2A Attach + Shared Event Translation."

Working directory:
C:\Users\User\FormicOSa

Read first, in order:
1. C:\Users\User\FormicOSa\CLAUDE.md
2. C:\Users\User\FormicOSa\AGENTS.md
3. C:\Users\User\FormicOSa\docs\waves\wave_24\plan.md
4. C:\Users\User\FormicOSa\docs\waves\wave_24\algorithms.md

Mission:
Complete the missing "submit then attach" story for external clients without changing the existing protocol model.

Deliverables:

B1. Multi-subscriber colony fan-out
- Generalize colony subscriptions in ws_handler.py so more than one consumer can listen to the same colony.
- subscribe_colony() should return a queue for that subscriber.
- unsubscribe_colony() should remove a specific queue, not clear the whole colony entry.
- Update the existing AG-UI caller to use the new unsubscribe signature.

B2. Shared event translator
- Extract the AG-UI-shaped event translation logic from agui_endpoint.py into a shared helper module.
- Keep AG-UI behavior equivalent after extraction.
- The new A2A attach endpoint must reuse the same translation logic, not duplicate it.

B3. A2A attach endpoint
- Add GET /a2a/tasks/{task_id}/events
- Semantics must be snapshot-then-live-tail.
- Terminal tasks should return final snapshot plus terminal event, then close.
- Running tasks should return current snapshot, then live translated events.

B4. Protocol truth updates
- Update Agent Card to advertise A2A streaming only after attach exists.
- Update the capability registry wiring so A2A semantics reflect submit/poll/attach/result.
- Update docs/A2A-TASKS.md to match the live endpoint set.

Owned files:
- src/formicos/surface/ws_handler.py
- src/formicos/surface/event_translator.py
- src/formicos/surface/agui_endpoint.py
- src/formicos/surface/routes/a2a.py
- src/formicos/surface/routes/protocols.py
- src/formicos/surface/app.py
- docs/A2A-TASKS.md

Do not touch:
- src/formicos/core/*
- src/formicos/engine/*
- src/formicos/surface/projections.py
- src/formicos/surface/transcript.py
- src/formicos/surface/view_state.py
- frontend/*
- config/*

Key constraints:
- AG-UI remains spawn-and-stream only.
- Attach lives under A2A, not AG-UI.
- Do not invent a second task entity.
- Do not duplicate event translation logic.
- Do not advertise streaming before attach is real.

Validation:
- python scripts/lint_imports.py
- python -m pytest -q
```

---

## Team 3 - Track C: Failure Clarity + Smoke Coverage

```text
You are Coder 3 for Wave 24. Your track is "Failure Clarity + Smoke Coverage."

Working directory:
C:\Users\User\FormicOSa

Read first, in order:
1. C:\Users\User\FormicOSa\CLAUDE.md
2. C:\Users\User\FormicOSa\AGENTS.md
3. C:\Users\User\FormicOSa\docs\waves\wave_24\plan.md
4. C:\Users\User\FormicOSa\docs\waves\wave_24\algorithms.md

Important overlap rule:
- Coder 2 owns routes/a2a.py first for the attach endpoint.
- Reread routes/a2a.py after Coder 2 lands before adding failure enrichment there.

Mission:
Make failed and killed tasks more understandable without inventing richer semantics than the repo actually stores, and extend smoke coverage for the new truth surfaces.

Deliverables:

C1. Projection failure metadata
- Preserve existing failure metadata already present on events.
- Add conservative projection fields for failed and killed colonies.
- Populate them in the existing event handlers.

C2. Transcript failure_context
- Add an optional failure_context block to build_transcript().
- Keep the shape conservative:
  - failure_reason
  - failed_at_round
  - killed_by
  - killed_at_round
- Include it only when the data exists.

C3. A2A status failure enrichment
- Add the same conservative failure_context to the A2A status response.
- Make this match the transcript story closely.

C4. Browser smoke expansion
- Add a few assertions that cover the truth surfaces from this wave:
  - tree collapse actually changes visibility
  - model naming looks human-readable
  - named colonies appear by display name when available
  - aggregate cost display no longer reads like cost/budget

Owned files:
- src/formicos/surface/projections.py
- src/formicos/surface/transcript.py
- src/formicos/surface/routes/a2a.py (after reread)
- tests/browser/smoke.spec.ts

Do not touch:
- src/formicos/core/events.py
- src/formicos/engine/*
- src/formicos/surface/ws_handler.py
- src/formicos/surface/agui_endpoint.py
- src/formicos/surface/event_translator.py
- src/formicos/surface/view_state.py
- frontend/*
- config/*

Key constraints:
- Only use failure data the repo actually stores or can store from existing events.
- Do not invent governance metadata that is not persisted.
- Keep the browser smoke path small and focused on operator-visible truths.

Validation:
- python scripts/lint_imports.py
- python -m pytest -q
- cd frontend && npm run build
```
