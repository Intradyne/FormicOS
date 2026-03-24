## Role

You own the testing and integration-hardening track of Wave 40.

Your job is to:

- write the missing cross-feature interaction tests
- audit flaky behavior
- strengthen confidence in the seams created by Waves 37-39

This is the "prove the repo behaves correctly where features meet" track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_40/wave_40_plan.md`
4. `docs/waves/wave_40/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `src/formicos/surface/projections.py`
7. `src/formicos/surface/knowledge_catalog.py`
8. `src/formicos/engine/runner.py`
9. `src/formicos/surface/colony_manager.py`
10. `src/formicos/surface/proactive_intelligence.py`
11. `src/formicos/surface/routes/a2a.py`
12. `tests/integration/`

## Coordination rules

- This is a testing track, not a feature track.
- Prefer behavior-level tests over import-path-coupled tests.
- If Team 1 refactors helpers, reread the final behavior before locking tests.
- If an interaction seam is hard to test through a full integration path,
  use the cleanest lower-level test that still proves the behavior.
- Control randomness where retrieval or Thompson Sampling would otherwise make
  tests unstable.
- Do **not** add new product capabilities to make testing easier.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `tests/integration/test_wave40_interactions.py` | CREATE | primary interaction matrix |
| `tests/integration/test_wave40_overlay_retrieval.py` | CREATE | overlay / retrieval / federation seams |
| `tests/integration/test_wave40_escalation_truth.py` | CREATE | escalation / validator / reporting seams |
| `tests/integration/test_wave40_protocol_truth.py` | CREATE | native task API / wrapper truth if dual API lands |
| `tests/unit/*` | MODIFY | only where focused coverage is cleaner than integration |
| existing test files affected by refactors | MODIFY | keep expectations truthful after Team 1 cleanup |

## DO NOT TOUCH

- backend production files except for tiny testability fixes explicitly needed
- frontend components
- docs
- protocol implementation code except where a microscopic test seam is needed

If a production change feels larger than "tiny testability fix," stop and
report it instead of claiming the testing track.

## Overlap rules

- Team 1 owns backend refactors.
  - Reread the final backend seams before finalizing assertions.
  - Do not lock tests to obsolete helper locations if behavior is unchanged.
- Team 3 owns dual-API implementation and docs truth.
  - If the wrapper or Agent Card changes surface behavior, test the behavior,
    not the exact private helper structure.

---

## 2A. Critical interaction pairs

Write focused tests for the highest-value interaction seams.

Target at least 5-7 of these:

1. operator overlays x retrieval scoring
2. operator overlays x federation truth
3. validators x auto-escalation
4. earned autonomy x config memory evidence
5. bi-temporal edges x graph query filtering
6. admission scoring x federation trust
7. topology bias x muted / invalidated entries
8. auto-escalation x escalation matrix truth
9. co-occurrence x operator invalidation
10. proactive insights x operator annotations

You do not need to force all 10 if the top 5-7 are clearly the riskiest and
well-covered.

### Hard constraints

- Do **not** invent new features to complete a pair.
- If one pair turns out to depend on a genuinely missing production seam,
  report the smallest blocker clearly.

---

## 2B. Flaky test audit

Run the suite multiple times or otherwise stress likely flaky seams.

Priority suspects:

- retrieval-order expectations that do not control randomness
- timing-sensitive async or SSE assertions
- tests that assume incidental projection ordering

### Success looks like

- unstable tests are either fixed or clearly quarantined
- the repo is less likely to go red on timing noise or stochastic ranking

---

## 2C. Coverage gap analysis

Stretch only after the interaction matrix is in place.

If you do this:

- focus on high-traffic surface functions
- prefer precise tests over coverage gaming
- mention which weak seams you strengthened and why

---

## Validation

Run, at minimum:

1. your new interaction tests
2. any directly related existing test modules
3. `python -m pytest -q` if the interaction work touches broad shared seams

Your summary must include:

- which interaction pairs you covered
- any flaky tests found and how they were handled
- any real blocker you discovered in production code
