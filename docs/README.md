# FormicOS Documentation

## For Users

- [Quick Start](LOCAL_FIRST_QUICKSTART.md) — local-first setup, first colony in minutes
- [Operator's Guide](OPERATORS_GUIDE.md) — day-to-day operation, knowledge management
- [Deployment](DEPLOYMENT.md) — Docker Compose production deployment
- [Runbook](RUNBOOK.md) — operational procedures and troubleshooting

## Architecture

- [Architecture Overview](ARCHITECTURE.md) — four-layer architecture, event sourcing
- [Knowledge Pipeline](KNOWLEDGE_PIPELINE_REFERENCE.md) — extraction, scoring, retrieval
- [Knowledge Lifecycle](KNOWLEDGE_LIFECYCLE.md) — entry lifecycle, operator controls
- [Replay Safety](REPLAY_SAFETY.md) — event replay guarantees
- [API Surface Integration](API_SURFACE_INTEGRATION_REFERENCE.md) — MCP, HTTP, WebSocket, A2A, AG-UI

## Findings

- [Key Findings](../FINDINGS.md) -- measurement results and discoveries

## Specifications (current state)

- [Knowledge System](specs/knowledge_system.md)
- [Colony Execution](specs/colony_execution.md)
- [Extraction Pipeline](specs/extraction_pipeline.md)
- [Context Assembly](specs/context_assembly.md)
- [Cost Tracking](specs/cost_tracking.md)
- [Proactive Intelligence](specs/proactive_intelligence.md)

## Development

- [Contributing](../CONTRIBUTING.md)
- [Development Workflow](DEVELOPMENT_WORKFLOW.md) -- wave cadence, delivery loop
- [ADRs](decisions/) -- 49 architectural decision records
- [GitHub Admin](GITHUB_ADMIN_SETUP.md) -- repo settings, branch protection

## Reference

- [Architecture Map](reference/architecture_map.md) — code-anchored architecture reference
- [Knowledge Dynamics Audit](reference/knowledge_dynamics_audit.md)
- [Knowledge Curation Audit](reference/knowledge_curation_audit.md)
- [Knowledge Flow Audit](reference/knowledge_flow_audit.md)
- [Tool Dispatch Reference](reference/tool_dispatch_and_agent_loop.md)

## Research

- [Stigmergy Knowledge Substrate](research/stigmergy_knowledge_substrate_research.md) — knowledge-as-pheromone thesis
- [OpenClaw Research Briefing](research/openclaw_research_briefing_for_orchestrator.md)
- [Coordination Math Map](research/coordination_context_knowledge_math_map.md)

## Wave History

The [waves/](waves/) directory contains 60 wave planning documents, dispatch
prompts, and decision logs. Each wave directory is self-contained project history.
See [waves/PROGRESS.md](waves/PROGRESS.md) for the progress tracker.

## Archived

- [archive/](archive/) — stale documents preserved for history (handoffs, unimplemented integrations)
- [internal/](internal/) — development-only artifacts (session logs, research prompts)
