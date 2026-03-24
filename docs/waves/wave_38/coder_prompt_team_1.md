# Wave 38 Team 1 - Ecosystem Protocols + NemoClaw Bridge

## Role

You own the ecosystem boundary track of Wave 38.

Your job is to:

- integrate an external specialist boundary through the existing tool-level seam
- harden A2A protocol truth without pretending the repo starts from zero
- keep the Agent Card, docs, and real routes aligned

This is the "callable from the outside without lying about the shape" track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_38/wave_38_plan.md`
4. `docs/waves/wave_38/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `docs/A2A-TASKS.md`
7. `src/formicos/surface/routes/a2a.py`
8. `src/formicos/surface/routes/protocols.py`
9. `src/formicos/engine/service_router.py`
10. `src/formicos/surface/queen_tools.py`

## Coordination rules

- A2A already exists. Do not rewrite it from scratch.
- Preserve `/a2a/tasks` submit / poll / attach / result semantics unless a new
  compatibility layer is strictly additive.
- NemoClaw integration in Wave 38 is Pattern 1 only: tool-level external
  specialist bridge.
- Do **not** wrap NemoClaw as `LLMPort` in this wave.
- Keep external specialist calls traceable through existing
  `ServiceQuerySent` / `ServiceQueryResolved` paths.
- Keep provider fallback and capability escalation separate. This track does
  not own auto-escalation.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `src/formicos/surface/routes/a2a.py` | OWN | A2A compatibility hardening without replacing the current lifecycle |
| `src/formicos/surface/routes/protocols.py` | OWN | Agent Card protocol truth and discovery updates |
| `src/formicos/surface/structured_error.py` | MODIFY | additive A2A / protocol error consistency only |
| `src/formicos/engine/service_router.py` | MODIFY | only if a small additive seam is needed for external specialist handlers |
| `src/formicos/surface/app.py` | MODIFY | register external specialist handlers / protocol wiring |
| `src/formicos/surface/queen_tools.py` | MODIFY | additive `query_service` ergonomics only if needed |
| `src/formicos/adapters/nemoclaw_client.py` | CREATE | bounded external specialist client |
| `docs/A2A-TASKS.md` | MODIFY | truth-in-advertising and compatibility notes |
| `docs/NEMOCLAW_INTEGRATION.md` | CREATE | operator/deployment guide |
| `tests/unit/surface/test_wave38_a2a_truth.py` | CREATE | route/card/docs alignment tests |
| `tests/integration/test_wave38_nemoclaw_service.py` | CREATE | tool-level specialist bridge coverage |

## DO NOT TOUCH

- `src/formicos/core/*`
- `src/formicos/engine/runner.py`
- `src/formicos/surface/projections.py` - Team 2 owns
- `src/formicos/surface/routes/api.py` - Team 2 owns
- `tests/integration/test_wave37_stigmergic_loop.py` - Team 2 owns
- `src/formicos/surface/admission.py` - Team 3 owns
- `src/formicos/surface/knowledge_catalog.py` - Team 3 owns
- `src/formicos/surface/federation.py` - Team 3 owns
- `src/formicos/surface/trust.py` - Team 3 owns
- `src/formicos/adapters/knowledge_graph.py` - Team 3 owns
- `frontend/src/components/knowledge-browser.ts` - Team 3 owns

## Overlap rules

- `src/formicos/surface/app.py`
  - You own additive protocol / external specialist registration only.
  - Do not widen unrelated startup or maintenance wiring.
- `src/formicos/engine/service_router.py`
  - Touch only if the current deterministic handler seam is insufficient.
  - Prefer using the existing `register_handler()` path as-is.

---

## 1A. NemoClaw tool-level specialist bridge

Build Pattern 1 only.

### Required scope

1. Add a bounded client for an external NemoClaw-like specialist service.
2. Register that specialist through the existing `ServiceRouter` path.
3. Make it callable through `query_service`.
4. Preserve service-query traceability and timeout behavior.

### Hard constraints

- Do **not** make this an `LLMPort` adapter.
- Do **not** hide state transitions inside the external specialist.
- Do **not** bypass `ServiceQuerySent` / `ServiceQueryResolved`.
- Keep the first integration narrow and operator-readable.

### What success looks like

The Queen or a colony can call a named external specialist through
`query_service`, and the call is visible in the normal service trace path.

---

## 1B. A2A compatibility hardening

Treat this as a standards-honesty pass, not a rewrite.

### Required scope

1. Preserve the current colony-backed task lifecycle.
2. Make the Agent Card, docs, and route behavior agree.
3. If you add a compatibility wrapper, keep it additive and map it onto the
   existing lifecycle rather than creating a second store or route truth.
4. Keep attach semantics snapshot-then-live-tail.

### Hard constraints

- Do not claim support the routes do not actually provide.
- Do not create a second task store.
- Do not convert the current lifecycle into a hand-wavy "A2A compatible"
  statement without concrete route truth.

### What success looks like

Another engineer can read the card, the docs, and the route code and arrive at
the same understanding of what FormicOS supports.

---

## 1C. Ecosystem docs

Leave behind docs that an operator can actually use.

Required topics:

- NemoClaw specialist setup
- endpoint / auth assumptions
- local-only vs externally exposed deployment posture
- what Pattern 1 is and what Pattern 2 is not yet

---

## Acceptance targets for Team 1

1. A tool-level external specialist bridge exists and uses the current service
   trace path.
2. `/.well-known/agent.json`, `docs/A2A-TASKS.md`, and the live route behavior
   agree.
3. No second task store or hidden lifecycle was introduced.
4. Wave 38 still does not pretend that model-level external agent wrapping has
   landed.
5. No new event types were added.

## Validation

```bash
python scripts/lint_imports.py
python -m pytest -q
```

If your changes affect docs or protocol examples, read the final docs and
sample payloads carefully. The user will trust those docs more than comments.

## Required report

- exact files changed
- what external specialist path was added
- how the specialist call stays visible in existing service-query traces
- what changed in the Agent Card
- what changed in A2A docs / compatibility behavior
- confirmation that no new event types or second task store were introduced
