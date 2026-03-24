# Wave 35 Validation Track — Integration Tests + Documentation

## Role

You are the quality gate. You write integration tests that prove the full post-35 system works end-to-end. You also perform the final documentation pass. You run AFTER Teams 1, 2, and 3 have all landed and passed CI.

## Coordination rules

- `CLAUDE.md` defines the evergreen repo rules. This prompt overrides root `AGENTS.md` for this dispatch.
- Read all ADRs (045-046) before writing tests. The invariants and models are your test specifications.
- Read the Wave 35 plan for the 15 smoke test items.
- You may touch any source file to fix validation failures, but document every fix.
- **Wait for all 3 teams to land before starting.** Team 1 = parallel planner + events. Team 2 = self-maintenance + distillation. Team 3 = score rendering + directives + per-workspace weights + mastery restoration.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `tests/integration/test_parallel_planning.py` | CREATE | Multi-colony orchestration integration test |
| `tests/integration/test_self_maintenance.py` | CREATE | Autonomy + dispatch integration test |
| `tests/integration/test_distillation.py` | CREATE | Knowledge distillation pipeline test |
| `tests/integration/test_directives.py` | CREATE | Operator directive injection test |
| `tests/integration/test_mastery_restoration.py` | CREATE | Restoration bonus integration test |
| `tests/integration/test_workspace_weights.py` | CREATE | Per-workspace weight integration test |
| `tests/integration/test_replay_55.py` | CREATE | 55-event replay idempotency test |
| `CLAUDE.md` | MODIFY | Full update for post-35 codebase |
| `AGENTS.md` | MODIFY | Parallel planning, autonomy levels, directives |
| `docs/KNOWLEDGE_LIFECYCLE.md` | MODIFY | Self-maintenance loop, distillation, mastery restoration |
| `docs/OPERATORS_GUIDE.md` | MODIFY | Autonomy configuration, directive usage, weight tuning |

## DO NOT TOUCH (unless fixing a validation failure)

- `surface/queen_runtime.py` — Team 1 owns
- `surface/self_maintenance.py` — Team 2 owns
- `surface/proactive_intelligence.py` — Team 2 owns
- `surface/knowledge_catalog.py` — Team 3 owns
- `engine/runner.py` — Team 3 owns
- `config/caste_recipes.yaml` — Team 1 owns
- `frontend/*` — Teams 1 and 3 own

---

## V1. Integration tests

### Parallel planning test

Queen receives "build a REST API with auth and tests." Generates DelegationPlan with 2 parallel groups:
- Group 1: [research-auth, research-db] — run simultaneously
- Group 2: [implement-api] — depends on Group 1
ParallelPlanCreated event emitted. Both Group 1 colonies start concurrently. Group 2 starts only after Group 1 completes. Queen explains her grouping decision in reasoning field.

### Self-maintenance test

Create workspace with known contradiction (two verified entries with opposite polarity, domain overlap > 0.3). Set autonomy_level to auto_notify with `auto_actions=["contradiction"]`. Run maintenance. Verify:
- Research colony spawns automatically
- MAINTENANCE_COLONY_SPAWNED AG-UI event emitted
- Colony tagged with ["maintenance", "contradiction"]
- After resolution: contradiction insight clears from next briefing

### Distillation test

Create 6 entries with strong co-occurrence (weight > 3.0). Run maintenance to flag distillation_candidates. Set autonomy to allow distillation (`auto_actions=["distillation"]`). Verify:
- Archivist colony spawns
- KnowledgeDistilled event emitted
- Distilled entry has decay_class="stable", elevated alpha (capped at 30)
- Source entries marked with distilled_into
- distillation_candidates list shrinks after distillation

### Operator directive test

Spawn colony. Send CONTEXT_UPDATE directive via chat_colony. Verify:
- ColonyChatMessage event includes directive_type in payload
- Next round's context includes directive with special framing
- Send URGENT CONSTRAINT_ADD → appears before task description
- Normal directive → appears after task, before round history

### Mastery-restoration test

Entry with peak_alpha=25, simulated 180-day stable decay (current_alpha ~13.14). Successful observation:
- Restoration bonus applied (~2.37)
- After 3 successive observations: alpha approaches ~22
- Ephemeral entry at same gap: NO bonus
- Failed observation: NO bonus

### Per-workspace weights test

Set workspace weights: semantic=0.43, thompson=0.25, freshness=0.15, status=0.10, thread=0.07, cooccurrence=0.0 (sum=1.00). Verify:
- Retrieval uses workspace weights, not global defaults
- Invariants 1-4 pass with these weights
- Invariant 5 (co-occurrence boost) does NOT pass (correct — cooccurrence=0.0)
- Weights must sum to 1.0 validation works

### 55-event replay test

Full replay with all 55 event types (53 existing + ParallelPlanCreated + KnowledgeDistilled). Double-apply each new event type → projections identical (idempotency).

---

## V2. 15 smoke test items from Wave 35 plan

Run each item and document pass/fail/fixed:

1. Queen generates DelegationPlan with parallel groups for complex task
2. Two parallel colonies run simultaneously, wall time < 2x single colony
3. Queen references knowledge gaps and score breakdowns in reasoning
4. Full-tier memory_search returns score_breakdown with ranking_explanation
5. Self-maintenance dispatches research colony for contradiction (auto_notify)
6. Distillation spawns archivist colony for dense cluster (auto_notify)
7. Budget cap blocks 3rd maintenance colony when daily budget exhausted
8. CONTEXT_UPDATE directive appears in next round with special framing
9. URGENT CONSTRAINT_ADD appears before task description
10. configure_scoring with semantic=0.43, cooccurrence=0.0 (sum=1.00) → invariant 5 fails (correct)
11. Mastery restoration: peak_alpha=25 + 180-day decay + re-observation → bonus applied
12. Suggest level: briefing shows SuggestedColony, no colonies spawn
13. Replay with 55 events including ParallelPlanCreated and KnowledgeDistilled → identical
14. All documentation accurate for post-35 codebase
15. Full CI passes

---

## V3. Final documentation pass

### CLAUDE.md

- Event union: 55 (ADR-gated). Add ParallelPlanCreated and KnowledgeDistilled.
- Multi-colony orchestration: DelegationPlan, parallel groups, concurrent dispatch
- Self-maintenance: autonomy levels (suggest/auto_notify/autonomous), MaintenanceDispatcher, 3 eligible categories
- Knowledge distillation: cluster synthesis, archivist colonies, elevated confidence, stable decay
- Operator directives: 4 types (context_update, priority_shift, constraint_add, strategy_change), urgent/normal priority
- Per-workspace composite weights: configure_scoring tool, WorkspaceConfigChanged storage
- Mastery-restoration bonus: 20% gap recovery, peak_alpha tracking, stable/permanent only
- Score breakdown rendering: ranking_explanation at standard/full tier
- Key paths: add self_maintenance.py

### KNOWLEDGE_LIFECYCLE.md

- Self-maintenance loop: insight → SuggestedColony → policy check → dispatch → outcome → feedback
- Distillation pipeline: cluster detection → density check → archivist synthesis → KnowledgeDistilled → elevated entry
- Mastery-restoration formula: gap = peak_alpha - current_alpha, bonus = gap * 0.2 when current < peak * 0.5
- Per-workspace weight tuning: configure_scoring tool, impact on invariants

### AGENTS.md

- Queen: parallel planning, DelegationPlan, concurrent spawn
- Operator directives: 4 types, delivery via chat_colony
- configure_scoring tool description
- Maintenance policy tools (set_maintenance_policy, get_maintenance_policy)

### OPERATORS_GUIDE.md

- Autonomy level configuration: what each level does, when to use each
- Maintenance policy: auto_actions, budget limits, concurrent caps
- Directive usage: when to use each type, urgent vs normal
- Weight tuning: how to read score breakdowns, what each weight does, when to adjust
- Distillation: how to enable, what to expect, how to review results

---

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Produce a final summary:
```
Wave 35 Results:
  Smoke tests: X/15 pass
  Integration tests: X pass, Y fail
  Fixed: Z items (list what was fixed)

  Parallel planning: pass/fail
  Self-maintenance: pass/fail (autonomy levels tested)
  Distillation: pass/fail
  Directives: pass/fail
  Mastery restoration: pass/fail
  Per-workspace weights: pass/fail
  55-event replay: pass/fail

Documentation:
  CLAUDE.md: sections updated
  KNOWLEDGE_LIFECYCLE.md: sections added
  AGENTS.md: changes
  OPERATORS_GUIDE.md: sections added

Final CI:
  ruff: pass/fail
  pyright: X errors
  lint_imports: X violations
  pytest: X passed, Y failed
```
