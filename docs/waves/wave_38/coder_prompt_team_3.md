# Wave 38 Team 3 - Poisoning Defense + Bi-Temporal Knowledge

## Role

You own the knowledge-hardening track of Wave 38.

Your job is to:

- turn the Wave 37 admission seam into real policy
- harden federation trust against weak foreign dominance
- and surface temporal truth where the repo actually has it

This is the "make the knowledge field safer and more honest about time" track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_38/wave_38_plan.md`
4. `docs/waves/wave_38/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `src/formicos/surface/admission.py`
7. `src/formicos/surface/memory_scanner.py`
8. `src/formicos/surface/knowledge_catalog.py`
9. `src/formicos/surface/federation.py`
10. `src/formicos/surface/trust.py`
11. `src/formicos/adapters/knowledge_graph.py`
12. `src/formicos/core/events.py`
13. `src/formicos/core/types.py`

## Coordination rules

- Keep the core event union closed at 55 unless you hit a real ADR-level
  blocker.
- Build on the existing four-axis scanner and Wave 37 admission seam.
- Do not overclaim a fully temporalized knowledge layer if only part of the
  substrate becomes temporalized.
- Do not casually edit `core/` to add typed temporal fields. If you conclude
  that full typed `MemoryEntry` temporal fields are required, stop and report
  that as an ADR-level blocker instead of quietly widening the core contract.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `src/formicos/surface/admission.py` | OWN | real admission scoring / intake policy |
| `src/formicos/surface/memory_scanner.py` | MODIFY | only if additive scanner-policy integration is required |
| `src/formicos/surface/knowledge_catalog.py` | OWN | poisoning-defense and temporal surfacing |
| `src/formicos/surface/federation.py` | OWN | stronger foreign-entry handling |
| `src/formicos/surface/trust.py` | OWN | trust hardening and asymmetric penalties |
| `src/formicos/adapters/knowledge_graph.py` | OWN | bi-temporal edge surfacing / query support |
| `src/formicos/surface/routes/knowledge_api.py` | MODIFY | additive temporal / trust read surfaces |
| `src/formicos/surface/colony_manager.py` | MODIFY | intake-path admission enforcement only if needed |
| `src/formicos/surface/projections.py` | MODIFY | only if additive temporal metadata must be surfaced in read models |
| `frontend/src/components/knowledge-browser.ts` | MODIFY | temporal / trust display |
| `tests/unit/surface/test_wave38_admission.py` | CREATE | admission policy tests |
| `tests/unit/surface/test_wave38_federation_trust.py` | CREATE | federated trust dominance tests |
| `tests/unit/surface/test_wave38_bitemporal.py` | CREATE | temporal surfacing tests |
| `tests/unit/adapters/test_knowledge_graph.py` | MODIFY | temporal edge coverage |

## DO NOT TOUCH

- `src/formicos/engine/*`
- `src/formicos/surface/routes/a2a.py` - Team 1 owns
- `src/formicos/surface/routes/protocols.py` - Team 1 owns
- `src/formicos/engine/service_router.py` - Team 1 owns
- `src/formicos/surface/queen_tools.py` - Team 1 owns
- `src/formicos/surface/routes/api.py` benchmark / escalation reporting - Team 2 owns
- `tests/integration/test_wave37_stigmergic_loop.py` - Team 2 owns
- `tests/integration/test_wave38_benchmarks.py` - Team 2 owns
- `tests/integration/test_wave38_escalation_matrix.py` - Team 2 owns

## Overlap rules

- `src/formicos/surface/projections.py`
  - Team 2 owns escalation outcome matrix additions.
  - You touch it only for additive temporal read-model support if truly needed.
  - Reread before merge if both land.
- `src/formicos/surface/colony_manager.py`
  - Your scope is admission enforcement in the ingestion path only.
  - Do not widen colony execution or governance behavior.

---

## 3A. Real admission scoring and intake policy

Wave 37 left a pass-through seam. Turn it into a real policy.

### Required scope

Combine:

- scanner findings
- factual confidence
- semantic novelty
- temporal recency
- content-type prior
- future utility prior
- federation origin / peer trust

Use existing status surfaces where possible:

- `candidate`
- `active`
- `verified`
- `rejected`
- `stale`

Implementation note: the Wave 37 admission seam exists as
`evaluate_entry()` in `src/formicos/surface/admission.py`, but it is not yet
wired into the ingestion path. Wiring that policy into the memory extraction /
entry-ingestion flow in `src/formicos/surface/colony_manager.py` is part of
your scope if admission is meant to affect intake rather than only retrieval
annotation.

### Hard constraints

- Keep the policy explainable.
- Prefer conservative gating over destructive deletion.
- Do not bury the decision in one opaque score without rationale.

### What success looks like

Admission scoring is no longer pass-through and suspicious or low-value entries
can be blocked or strongly demoted through existing status mechanisms.

---

## 3B. Federation trust hardening

Weak foreign entries should not easily outrank strong local verified entries.

### Required scope

1. Strengthen trust penalties where appropriate.
2. Review query-time trust discounting and hop behavior.
3. Surface peer origin and trust context more clearly.
4. Prove through tests that ordinary local verified knowledge wins by default
   over weak foreign knowledge.

### Hard constraints

- Keep the trust math inspectable.
- Do not break legitimate high-trust federation.
- Do not turn this into a full Wave 39 or Wave 40 security program.

---

## 3C. Bi-temporal knowledge surfacing

Be honest about where the repo already has temporal truth and extend from there.

### Required scope

1. Treat event / creation time as transaction time.
2. Surface validity windows separately where available.
3. Expose graph-edge validity windows.
4. Add temporal surfacing for institutional memory only where replay-safe truth
   is available without a casual core contract change.

### Hard constraints

- Do not claim "every entry is fully bi-temporal" unless that is actually true.
- If full typed `MemoryEntry` temporal fields become necessary, stop and report
  the ADR-level blocker rather than quietly editing `core/`.
- Label transaction time vs validity time explicitly in the UI / API.

### What success looks like

An operator can tell:

- when the system learned something
- when it was considered true
- when it stopped being considered true

for the temporalized parts of the knowledge surface.

---

## Acceptance targets for Team 3

1. Admission scoring materially affects intake or downstream trust.
2. Weak federated entries no longer dominate strong local verified entries
   under ordinary conditions.
3. Temporal truth is surfaced honestly where the substrate actually supports it.
4. No casual `core/` expansion was introduced.
5. No new event types were added.

## Validation

```bash
python scripts/lint_imports.py
python -m pytest -q
cd frontend && npm run build
```

If the temporal work starts pushing toward a core contract change, stop and
report that clearly instead of "solving" it with a hidden type expansion.

## Required report

- exact files changed
- how admission policy changed from Wave 37
- how federation trust hardening was implemented
- what temporal truth is now surfaced and where
- whether any part of the deeper memory-entry temporal model was deferred
- confirmation that no new event types were added
