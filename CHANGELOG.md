# Changelog

Narrative development history of FormicOS. This is not a commit log — it tells the product story of how FormicOS evolved from a stigmergic coordination experiment into a self-maintaining, knowledge-metabolic multi-agent system.

---

## Wave 36 — Colony Intelligence + Demo Path

The system becomes presentable. Colony outcomes surface as replay-derived metrics — success rates, cost, knowledge extraction, quality scores — without new events. The Queen and proactive intelligence consume these signals to inform planning. A guided demo path lets a new visitor create a pre-seeded workspace, watch the Queen plan in parallel, see colonies execute with live DAG visualization, and observe self-maintenance resolve a knowledge contradiction — all in one session.

**Key additions:**
- Colony outcome metrics surfaced through replay-derived projections (ADR-047)
- Guided demo workspace with 10 seeded knowledge entries and a deliberate contradiction
- Demo annotation bar that advances through real system state changes
- Workflow DAG polish: meaningful phase labels, animated status transitions, cost accumulator, mini-DAG in Active Plans
- "Try the Demo" entry point on the Queen landing page
- README restructured for first-60-seconds readability

## Wave 35.5 — Orchestration Legibility

Made the parallel planning system visible. The DAG visualization component (`fc-workflow-view`) was wired into the thread view with live colony status, cost and knowledge annotations per task node, and a fallback to the legacy step timeline for older threads. Active Plans appeared on the Queen overview with compact summary cards. The frontend store gained event handlers for `ParallelPlanCreated` and workflow events.

## Wave 35 — Parallel Planning + Workflow Threads

The Queen learned to decompose complex tasks into parallel execution plans. `spawn_parallel` creates a `DelegationPlan` DAG validated with Kahn's algorithm (no cycles). Tasks are organized into `parallel_groups` — tasks within a group run concurrently via `asyncio.gather`, groups execute sequentially. Workflow threads gained goals, steps, and continuation depth. `ParallelPlanCreated` became the 55th event.

## Wave 34 — Proactive Intelligence + Self-Maintenance

The system began watching itself. Proactive intelligence surfaces 7 deterministic rules (no LLM calls): confidence decline, contradiction, federation trust drop, coverage gap, stale cluster, merge opportunity, federation inbound. Three rules include `suggested_colony` configurations for auto-dispatch. `MaintenanceDispatcher` connects insights to automatic colony dispatch with three autonomy levels: `suggest`, `auto_notify`, `autonomous`. Policy controls daily budgets and category opt-ins.

## Wave 33 — Knowledge Metabolism + Federation

Knowledge entries gained Bayesian confidence posteriors (`Beta(alpha, beta)`) evolved by Thompson Sampling, replacing the earlier scalar confidence. Decay classes (ephemeral, stable, permanent) with gamma-decay at query time. Retrieval scoring moved to a 6-signal composite: semantic, Thompson, freshness, status, thread bonus, and co-occurrence. Federation arrived via Computational CRDTs — push/pull replication with Bayesian peer trust (10th percentile penalizing uncertainty) and three-phase conflict resolution (Pareto dominance, adaptive threshold, competing hypotheses).

---

For detailed technical decisions, see [docs/decisions/](docs/decisions/).
For wave-by-wave implementation details, see [docs/waves/PROGRESS.md](docs/waves/PROGRESS.md).
