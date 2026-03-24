## Role

You own the budget-truth, observability, and deterministic hardening-test
track of Wave 43.

Your job is to:

- build a real budget truth surface
- add bounded enforcement on top of that truth
- improve observability and CI determinism without turning the wave into a
  platform rewrite

This is the "make operations inspectable and enforceable" track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_43/wave_43_plan.md`
4. `docs/waves/wave_43/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `src/formicos/surface/projections.py`
7. `src/formicos/surface/runtime.py`
8. `src/formicos/adapters/telemetry_jsonl.py`
9. `src/formicos/core/events.py`
10. `tests/`

## Coordination rules

- Build budget truth before you build strong enforcement.
- Any circuit breaker or hard stop must be explainable from inspectable truth.
- OpenTelemetry is additive beside JSONL, not a replacement-first rewrite.
- Start the recorded-fixture layer small: Queen planning plus 1-2 high-value
  paths only.
- Do **not** add live LLM dependence to CI.
- Do **not** turn this into a general observability platform buildout.
- Do **not** add event types unless you hit a real blocker and can prove it.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `src/formicos/surface/projections.py` | OWN | workspace/colony budget truth and related projection state |
| `src/formicos/surface/runtime.py` | OWN | bounded budget enforcement and runtime circuit breakers |
| `src/formicos/adapters/telemetry_jsonl.py` | MODIFY | only if needed to coexist cleanly with additive OTel |
| `src/formicos/adapters/telemetry_otel.py` | CREATE | additive observability adapter if shipped |
| `tests/` | CREATE/MODIFY | recorded fixtures, regression tests, replay/property tests |

## DO NOT TOUCH

- Docker and execution-isolation files - Team 1 owns
- deployment/doc files - Team 3 owns
- Wave 41/42 intelligence features unless a bounded test or truth surface
  interaction requires it

---

## Pillar 3: Budget truth, enforcement, and observability

### Required scope

1. Build workspace-level and colony-level budget truth from existing token/cost
   events.
2. Use that truth to add bounded enforcement and circuit breakers.
3. Keep the enforcement behavior operator-legible.
4. Add at least a minimal additive observability path for the most valuable
   runtime seams.

### Hard constraints

- Do **not** pretend agent-level token counters are already sufficient budget
  truth.
- Do **not** add opaque enforcement logic that cannot be explained afterward.
- Do **not** replace JSONL first.
- Do **not** make observability adoption mandatory to run the system locally.

### Guidance

- The current budget substrate is much thinner than the product language may
  suggest. `_on_tokens_consumed` currently only updates `agent.tokens` as a
  single integer. There is no cost-denominated tracking, no colony-level
  running total in projections, and no workspace-level aggregation.
  `budget_remaining` is still computed ephemerally inside the runner loop.
  You are building the first real budget-truth surface, not augmenting a
  mature one.
- Start by making `TokensConsumed` actually useful at workspace and colony
  scope.
- Favor bounded backpressure and circuit-breaker rules over clever policy.
- If you expose metrics, start with the seams most useful to hardening:
  replay, retrieval, LLM duration/tokens, colony timing, execution timing.

---

## Pillar 4: Deterministic hardening tests

### Required scope

1. Add a small recorded-fixture layer for the highest-value LLM paths.
2. Expand regression coverage around Wave 43 hardening behavior.
3. Improve replay/property-based confidence where it materially helps.

### Hard constraints

- Do **not** try to fixture the whole product in one wave.
- Do **not** depend on live LLM calls in CI for the new assurances.
- Do **not** let test infrastructure sprawl outrank the production budget and
  observability work.

---

## Validation

Run, at minimum:

1. `python scripts/lint_imports.py`
2. targeted pytest for budget, telemetry, replay, and recorded-fixture seams
3. full `python -m pytest -q` if your truth/enforcement changes broaden across
   shared runtime surfaces

## Developmental evidence

Your summary must include:

- what budget truth now exists at workspace and colony scope
- what enforcement/circuit-breaker behavior now exists
- what observability was added and what remained intentionally simple
- which recorded fixtures landed
- what you rejected to keep this track bounded
