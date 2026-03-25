# Implementation Specifications — Index

Current-state implementation references for FormicOS subsystems. Each spec is
code-anchored to Wave 60.5 and verified against the live codebase. These are the
canonical source of truth for how the system works today.

For architectural *decisions* (why, not what), see `docs/decisions/`.
For code-anchored file/event inventories, see `docs/reference/architecture_map.md`.

---

| Spec | Subsystem | Key Topics |
|------|-----------|------------|
| [knowledge_system.md](knowledge_system.md) | Knowledge metabolism | Beta confidence, Thompson Sampling, 7-signal composite scoring, decay classes, retrieval tiers, operator overlays |
| [colony_execution.md](colony_execution.md) | Colony runtime | 5-phase round pipeline, tool dispatch, governance cascade, adaptive evaporation, quality scoring, strategies |
| [context_assembly.md](context_assembly.md) | Agent context | Position numbering, tier budgets, playbook injection, progressive disclosure, domain filter, specificity gate |
| [extraction_pipeline.md](extraction_pipeline.md) | Knowledge extraction | Post-colony extraction, transcript harvest, security scanning, admission scoring, Wave 59 curation |
| [queen_orchestration.md](queen_orchestration.md) | Queen agent | Tool dispatch, colony spawning, parallel DAG execution, workflow steps, thread management |
| [proactive_intelligence.md](proactive_intelligence.md) | Proactive intelligence | 17 deterministic rules, MaintenanceDispatcher, distillation, earned autonomy, forage signals |
| [federation.md](federation.md) | Federation | CRDT primitives, push/pull replication, Bayesian peer trust, conflict resolution, vector clocks |
| [web_foraging.md](web_foraging.md) | Web foraging | Egress gateway, fetch pipeline, content quality, search adapters, domain strategy |
| [cost_tracking.md](cost_tracking.md) | Cost tracking | Token counting, reasoning/cache token accounting, cost_fn, budget enforcement, cost display, local-vs-cloud gap analysis |
