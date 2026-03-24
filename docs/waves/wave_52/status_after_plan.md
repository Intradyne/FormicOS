# Wave 52: Status

**Date:** 2026-03-20
**Status:** Complete. All three teams shipped. 3388 tests passing (3
pre-existing prompt line-count failures out of scope).

---

## Final Status

- Team 1: Shipped. Backend coherence + intelligence reach.
- Team 2: Shipped. Frontend protocol truth cleanup.
- Team 3: Shipped. Docs + ADR truth.

---

## Acceptance Gates

### Packet A -- Control-Plane Coherence

| Gate | Result | Notes |
|------|--------|-------|
| A1: Canonical Version Truth | PASS | `formicos.__version__` is the single source; registry and Agent Card read from it |
| A2: Event Count Truth | PASS | All Wave 52-touched docs agree on 64 |
| A3: ADR Truth | PASS | ADR 045/046/047 status updated to Accepted with shipped context |
| A4: Protocol Description Truth | PASS | Frontend: stale "Not implemented" / "planned" / "Agent Card discovery only" replaced with "Inactive" |
| A5: Docs Claim Truth | PASS | A2A docs: learned-template reach, selection metadata, budget/spawn-gate parity documented. AG-UI docs: classifier defaults, budget behavior, idle semantics documented |
| A6: Stream Lifecycle Truth | PASS | A2A/AG-UI no longer emit terminal RUN_FINISHED on inactivity; keepalive + idle_disconnect (non-terminal) |

### Packet B -- Intelligence Reach + Visible Learning

| Gate | Result | Notes |
|------|--------|-------|
| B0: Queen Tool-Result Hygiene | PASS | Untrusted-data wrapping, HTML escaping, per-result truncation, oldest-first compaction |
| B1: Thread-Aware Queen Retrieval | PASS | `respond()` and `memory_search` tool both pass `thread_id` |
| B2: A2A Learned-Template Reach | PASS | `load_all_templates(projection_templates=...)` used; selection metadata in response |
| B3: External Budget Truth | PASS | AG-UI: explicit classifier-derived budget, no silent 5.0. Both paths use BudgetEnforcer spawn gate |
| B4: AG-UI Omitted-Defaults Truth | PASS | `classify_task()` for server-selected defaults; reported honestly |
| B5: Learned Templates Visible | PASS | `_rule_learned_template_health` in proactive intelligence; surfaces in briefing |
| B6: Recent Outcomes Visible | PASS | `_rule_recent_outcome_digest` in proactive intelligence; surfaces in briefing |
| B7: Briefing Selection Includes New Signals | PASS | Dedicated 2-slot `learning_loop` section; not crowded out by existing caps |

### Parallel Safety

| Gate | Result | Notes |
|------|--------|-------|
| P1: Disjoint Ownership | PASS | Team 1: backend; Team 2: frontend; Team 3: docs/ADRs |
| P2: Team 3 Final Truth Refresh | PASS | Docs updated after rereading Team 1 and Team 2 outcomes |

---

## Shipped Scope

### Packet A

- A1: Canonical version unification (`formicos.__version__`)
- A2: Event count corrected to 64 in all touched docs
- A3: ADR 045/046/047 status corrected from Proposed to Accepted
- A4: Frontend stale protocol text replaced with accurate labels
- A5: Stale docs claims corrected (A2A learned-template reach, budget,
  timeout semantics; AG-UI defaults, budget, idle behavior)
- A6/A7: External streams changed from terminal timeout to non-terminal
  idle with keepalive and eventual idle_disconnect

### Packet B

- B0: Queen tool-result prompt-boundary hygiene matching colony runner
- B0.5: Thread-aware Queen auto-retrieval and memory_search tool
- B1/B2: A2A learned-template reach with selection metadata in response
- B2: Spawn-gate parity for both A2A and AG-UI via BudgetEnforcer
- B3: AG-UI explicit classifier-derived budget (no silent 5.0 default)
- B4: AG-UI classifier-informed caste defaults when omitted
- B5: Learned template health briefing rule
- B6: Recent outcome digest briefing rule
- B7: Dedicated 2-slot learning-loop briefing section

---

## Intentionally Out Of Scope

- No new event types
- No AG-UI Tier 2 / bidirectional steering
- No full A2A conformance push
- No token streaming work
- No MCP expansion
- No Queen auto-substituting templates silently
- No auto-tuning config from outcomes
- No new external dependencies
- Transport naming normalization on the backend side (view_state.py
  fallback string) -- frontend displays whatever the backend sends; if
  backend normalizes in a future wave, frontend will follow automatically

---

## Remaining Debt Classification

### Pre-existing (not Wave 52 debt)

- 3 test failures: queen prompt line-count assertions (pre-existing
  before Wave 52)
- 19 pyright errors: all pre-existing, none in Wave 52 code

### Control-plane truth debt

- Transport naming: registry says `"Streamable HTTP"`, view_state
  fallback says `"streamable_http"`. Frontend displays whichever it
  receives. Low severity -- consistent in practice when protocol is
  active.

### Intelligence-reach debt

- None. All planned intelligence-reach items shipped.

### Surface-truth debt

- None from Wave 52 scope.

### Docs debt

- None. All owned docs updated in final truth-refresh pass.

### Advisory/model-dependent

- Queen briefing intelligence is ultimately LLM-dependent: the Queen
  sees the briefing, learned-template matches, and outcome digest, but
  decides autonomously how to use them. The substrate provides signals;
  the Queen interprets.

---

## Validation

| Check | Result |
|-------|--------|
| `ruff check src/` | PASS |
| `pyright src/` | 19 pre-existing errors, none in Wave 52 code |
| `python scripts/lint_imports.py` | PASS (97 files, no violations) |
| `pytest` | 3388 passed, 3 failed (pre-existing) |
| Contract tests | 406 passed |
| Frontend build | Clean |

---

## What Wave 52 Proved

The system now describes itself consistently. External integrators get
the same budget discipline and learned-template intelligence as the
Queen path. The Queen briefing visibly reflects that the system is
learning from work, not just storing evidence silently.

The event union remains at 64. No new subsystems, no new external
dependencies. The wave is additive wiring and truth alignment, not
capability expansion.
