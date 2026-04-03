# Architecture Decision Records — Index

| ADR | Title | Status |

> Note: this index reflects ADR files currently present in the repo. Active
> wave docs may reference upcoming ADR numbers before their files land; treat
> the checked-in ADR set here as the source of truth for what is already
> recorded.

|-----|-------|--------|
| [001](001-event-sourcing.md) | Event Sourcing as Sole Persistence Mechanism | Accepted |
| [002](002-pydantic-only.md) | Pydantic v2 as Sole Serialization Library | Accepted |
| [003](003-lit-web-components.md) | Lit Web Components for Frontend | Accepted |
| [004](004-typing-protocol.md) | typing.Protocol for Port Interfaces | Accepted |
| [005](005-mcp-sole-api.md) | MCP as Sole Programmatic API | Accepted |
| [006](006-trunk-based-development.md) | Trunk-Based Development with Feature Flags | Accepted |
| [007](007-agent-tool-system.md) | Agent Tool System via LLM Tool Specs | Proposed |
| [008](008-context-window-management.md) | Tiered Context Window Management | Proposed |
| [009](009-cost-tracking.md) | Real Cost Tracking from Model Registry | Proposed |
| [010](010-skill-crystallization.md) | Skill Crystallization on Colony Completion | Proposed |
| [011](011-quality-scoring.md) | Colony Quality Scoring from Existing Signals | Proposed |
| [012](012-compute-router.md) | Caste-Phase Compute Router | Proposed |
| [013](013-qdrant-migration.md) | Qdrant Migration — Replace LanceDB with Qdrant behind VectorPort | Accepted |
| [014](014-gemini-provider.md) | Gemini Provider + Defensive Structured Output | Accepted |
| [015](015-event-union-expansion.md) | Event Union Expansion — Wave 11 Contract Opening | Accepted |
| [016](016-colony-templates.md) | Colony Templates — Reusable Colony Configurations | Accepted |
| [017](017-bayesian-confidence-dedup.md) | Bayesian Skill Confidence + LLM-Gated Deduplication | Accepted |
| [018](018-frontend-rewrite.md) | Frontend Rewrite — Luminous Void v2.1 | Accepted |
| [019](019-hybrid-search-adapter-internal.md) | Hybrid Search Stays Adapter-Internal in Wave 13 | Accepted |
| [020](020-casteslot-clean-break.md) | CasteSlot Clean Break | Accepted |
| [021](021-qdrant-upgrade-bm25.md) | Qdrant Image Upgrade for Server-Side BM25 | Accepted |
| [022](022-budget-regime-injection.md) | Budget Regime Injection into Agent Prompts | Accepted |
| [023](023-caste-tool-permissions.md) | Caste-Based Tool Permission Enforcement | Accepted |
| [024](024-provider-cooldown.md) | Provider Cooldown Cache | Accepted |
| [025](025-sync-embedding-resolution.md) | Sync Embedding Resolution for Qwen3 Sidecar | Accepted |
| [026](026-first-run-bootstrap.md) | First-Run Bootstrap Behavior | Accepted |
| [027](027-nav-consolidation-fleet.md) | Nav Consolidation — Fleet Tab | Accepted |
| [028](028-nav-regroup-playbook.md) | Nav Regrouping — Playbook Tab Replaces Fleet | Accepted |
| [029](029-colony-file-io-rest.md) | Colony File I/O as REST + Filesystem | Accepted |
| [030](030-queen-tool-surface.md) | Queen Tool Surface Expansion | Accepted |
| [031](031-blackwell-default.md) | Blackwell Image Default + 131k Context | Accepted |
| [032](032-colony-redirect.md) | Colony Redirect for Mid-Run Goal Steering | Accepted |
| [033](033-colony-chaining.md) | Colony Chaining Through Input Sources | Accepted |
| [034](034-mcp-streamable-http.md) | MCP Streamable HTTP Transport | Accepted |
| [035](035-agui-tier1-bridge.md) | AG-UI Tier 1 Bridge with Honest Summary Semantics | Accepted |
| [036](036-capability-registry.md) | Capability Registry as Single Source of System Truth | Accepted |
| [037](037-scoped-colony-memory.md) | Scoped Colony Scratch Memory | Accepted |
| [038](038-a2a-task-lifecycle.md) | Inbound A2A Task Lifecycle as Colony View | Accepted |
| [039](039-knowledge-metabolism.md) | Knowledge Metabolism — Confidence Evolution, Thompson Sampling, Workflow Steps | Proposed |
| [040](040-wave-31-ship-polish.md) | Wave 31 Ship Polish Decisions | Accepted |
| [041](041-knowledge-tuning.md) | Knowledge Confidence Tuning — Gamma-Decay, Archival Decay, Scoring Normalization | Approved |
| [042](042-event-union-expansion.md) | Event Union Expansion 48 → 53 — CRDT Operations and Merge Audit | Proposed |
| [043](043-cooccurrence-data-model.md) | Co-occurrence Data Model — Collection Infrastructure and Deferred Scoring | Proposed |
| [044](044-cooccurrence-scoring.md) | Composite Scoring with Co-occurrence — Weight Rebalancing | Proposed |
| [045](045-event-union-parallel-distillation.md) | Event Union Expansion 53 → 55 — Parallel Planning and Knowledge Distillation | Proposed |
| [046](046-autonomy-levels.md) | Autonomy Levels for Self-Maintenance Colonies | Proposed |
| [047](047-outcome-metrics-retention.md) | Colony Outcome Metrics Retention and Surfacing | Proposed |
| [048](048-memory-entry-refined.md) | MemoryEntryRefined Event — In-Place Knowledge Curation | Proposed |
| [049](049-knowledge-hierarchy.md) | Knowledge Hierarchy — Materialized Paths on Projections | Proposed |
| [050](050-two-pass-retrieval.md) | Two-Pass Retrieval — Personalized PageRank for Graph Proximity | Proposed |
| [051](051-dynamic-context-caps.md) | Dynamic Queen Context Caps — Proportional Budget Allocation | Proposed |
| [052](052-ai-filesystem.md) | AI Filesystem — State/Artifact Separation + Amnesiac Forking | Proposed |
