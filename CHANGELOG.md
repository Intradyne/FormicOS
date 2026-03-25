# Changelog

Narrative development history of FormicOS. This is not a commit log — it tells the product story of how FormicOS evolved from a stigmergic coordination experiment into a self-maintaining, knowledge-metabolic multi-agent system.

---

## Wave 65 — The Operational OS

The addon system became real. Every Wave 64 stub turned into working code: codebase index runs real vector search and reindex, git control runs real git commands with two-phase smart commit and branch analysis, proactive intelligence rules are callable through addon handlers with per-workspace rule enable/disable. The Queen gained five autonomous agency tools — `batch_command`, `summarize_thread`, `draft_document`, `list_addons`, `trigger_addon` — bringing the tool count to 36. Cron triggers fire addon handlers on schedule with proper signature detection. MCP chaining guidance in the Queen system prompt positions addons as persistent intelligence alongside external MCP services. Addon developer documentation shipped.

**Key additions:**
- Addon runtime context injection (`vector_port`, `embed_fn`, `workspace_root_fn`, `projections`, `runtime`)
- Real codebase index: semantic search via vector_port, structural chunking, full/incremental reindex with cron
- Real git control: two-phase smart commit, branch divergence analysis, create branch, stash, forbidden ops safety
- Trigger wiring: TriggerDispatcher background loop, cron → handler dispatch, `trigger_addon` Queen tool
- Queen autonomous agency: batch_command, summarize_thread, draft_document, list_addons
- Proactive intelligence addon handlers with per-workspace rule configuration
- Addon development guide (addons/README.md) and TEMPLATE scaffold
- Wave 65.5 polish: porcelain parsing fix, consecutive-arg forbidden ops, cron DOW convention, trigger loop cleanup, parameter schema validation, 36 net new tests

## Wave 64 — Parallel Execution + Addon Infrastructure

The system learned to use multiple LLM providers simultaneously and gained an addon framework. Per-provider adapter factory with endpoint-keyed concurrency, optimistic file locking for concurrent agents, Queen smart fan-out with retry and cloud routing heuristics, and a full addon lifecycle — manifest discovery, handler resolution, component registration, trigger dispatch, and three built-in addons (codebase-index, git-control, proactive-intelligence). Three new events brought the closed union to 69.

**Key additions:**
- Per-provider concurrency with endpoint-keyed adapter factory
- Optimistic file locking with content-hash conflict detection
- Queen retry_colony tool with failure context and model override
- Heuristic cloud routing (complexity, @cloud tag, propose_plan, token budget, parse failure)
- Addon loader: manifest parser, handler resolver, component registration, 3 new events (#67-69)
- Proactive intelligence extraction to addon module (1980 lines)
- TriggerDispatcher with cron parsing and double-fire prevention
- Reasoning and cache token accounting through the full pipeline

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
