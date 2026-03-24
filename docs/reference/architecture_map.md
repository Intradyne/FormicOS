# FormicOS Architecture Map

> Living reference for engineers and AI coder teams.
> Last audited: 2026-03-23 against commit HEAD (updated for Waves 54–59).

---

## Section 1: Layer Inventory

Four backend layers with strict inward dependency (enforced by CI via
`scripts/lint_imports.py`). Plus eval, frontend, and config.

### Layer Summary

| Layer | Directory | Files | LOC | May Import |
|-------|-----------|-------|-----|------------|
| **Core** | `src/formicos/core/` | 7 | 3,237 | Nothing |
| **Engine** | `src/formicos/engine/` | 12 | 5,147 | Core only |
| **Adapters** | `src/formicos/adapters/` | 22 | 6,388 | Core only |
| **Surface** | `src/formicos/surface/` | 41 | 24,862 | Core, Engine, Adapters |
| **Eval** | `src/formicos/eval/` | 6 | 2,069 | — |
| **Frontend** | `frontend/src/` | 40 | 13,509 | — |
| **Config** | `config/` | ~47 | ~1,000+ | — |

### Core (`src/formicos/core/`) — 3,237 lines

Base types, events, ports, protocols. No outbound dependencies.

| File | Lines | Role |
|------|-------|------|
| `events.py` | 1,588 | 65-event discriminated union (closed set). `FormicOSEvent` union type, `EVENT_TYPE_NAMES` manifest |
| `types.py` | 912 | Core domain types: `AgentConfig`, `ColonyContext`, `VectorDocument`, `KnowledgeAccessItem`, `MergeReason`, `RedirectTrigger` |
| `settings.py` | 238 | Pydantic config models: `SystemSettings`, `GovernanceSettings`, `RoutingSettings`, `EmbeddingSettings`, context budgets |
| `ports.py` | 219 | Protocol definitions for LLM, vector store, coordination strategy, logging ports |
| `crdt.py` | 201 | CRDT primitives: G-Counters, LWW Registers, G-Sets, `ObservationCRDT` for federation |
| `vector_clock.py` | 46 | Vector clock for causal ordering |
| `__init__.py` | 33 | Package exports |

### Engine (`src/formicos/engine/`) — 5,147 lines

Pure computation: round execution, tool dispatch, scoring, strategies. Imports Core only.

| File | Lines | Role |
|------|-------|------|
| `runner.py` | 2,817 | 5-phase round loop (goal → intent → route → execute → compress); adaptive evaporation, convergence detection, stall tracking |
| `tool_dispatch.py` | 650 | `TOOL_SPECS` registry, `TOOL_CATEGORY_MAP`, `check_tool_permission()`, `_execute_tool()` dispatch |
| `context.py` | 626 | Context assembly with tier budgets, token estimation, edge truncation, playbook injection at position 2.5, knowledge threshold gate |
| `service_router.py` | 347 | Service lifecycle (startup, event handlers, maintenance dispatch) |
| `strategies/stigmergic.py` | 209 | Pheromone-based routing with DyTopo tau threshold cutoff |
| `telemetry_bus.py` | 175 | Structured logging and telemetry event broadcasting |
| `playbook_loader.py` | 133 | YAML playbook loading with caste-aware resolution order |
| `runner_types.py` | 97 | `RoundRunner` config and tool dispatch signatures |
| `scoring_math.py` | 66 | UCB/Thompson Sampling math for agent routing |
| `strategies/sequential.py` | 25 | Sequential execution strategy stub |

### Adapters (`src/formicos/adapters/`) — 6,388 lines

Tech bindings for LLM, vector, sandbox, security, web. Imports Core only.

| File | Lines | Role |
|------|-------|------|
| `sandbox_manager.py` | 984 | Code execution sandbox: Docker containers with `--network=none`, `--memory=256m`, `--read-only`; gVisor/seccomp profiles |
| `code_analysis.py` | 564 | Code repository analysis for context and pattern extraction |
| `knowledge_graph.py` | 559 | TKG triple storage and entity deduplication (threshold 0.85) |
| `fetch_pipeline.py` | 453 | Graduated fetch + content extraction (Level 1 trafilatura, Level 2 fallback) |
| `vector_qdrant.py` | 437 | Qdrant vector store adapter with semantic search |
| `egress_gateway.py` | 393 | Controlled HTTP egress with rate/domain/size limits for web foraging |
| `queen_intent_parser.py` | 367 | Intent classification and tool-call synthesis from Queen output |
| `llm_gemini.py` | 347 | Google Gemini API adapter |
| `llm_openai_compatible.py` | 327 | OpenAI-compatible API adapter (llama.cpp, Ollama) |
| `web_search.py` | 317 | Pluggable web search adapter (SerpAPI, DuckDuckGo) |
| `content_quality.py` | 261 | Deterministic content-quality scoring (no LLM) for web foraging admission |
| `telemetry_otel.py` | 248 | OpenTelemetry instrumentation |
| `llm_anthropic.py` | 233 | Anthropic Messages API adapter |
| `store_sqlite.py` | 214 | SQLite persistence for events, projections, knowledge, federation peers |
| `parse_defensive.py` | 191 | JSON repair and defensive parsing |
| `nemoclaw_client.py` | 156 | External client adapter |
| `embedding_qwen3.py` | 109 | Qwen3-Embedding sidecar adapter |
| `ast_security.py` | 81 | AST-based security analysis |
| `federation_transport.py` | 84 | Federation transport layer |
| `telemetry_jsonl.py` | 36 | JSONL telemetry sink |
| `output_sanitizer.py` | 26 | Output length capping (10,000 chars) |

### Surface (`src/formicos/surface/`) — 24,862 lines

Wiring, orchestration, HTTP/WS/CLI, lifecycle. Imports Core, Engine, Adapters.

| File | Lines | Role |
|------|-------|------|
| `projections.py` | 2,310 | Event-sourced projections: `ProjectionStore`, `ColonyProjection`, `ColonyOutcome`, `BudgetSnapshot`, 60 event handlers |
| `queen_tools.py` | 2,134 | 21 Queen tools: `spawn_colony`, `spawn_parallel`, `memory_search`, `read_colony_output`, etc. |
| `colony_manager.py` | 1,980 | Colony lifecycle, step continuation, progress tracking, memory extraction, dispatch coordination |
| `proactive_intelligence.py` | 1,923 | 17 deterministic briefing rules (7 knowledge + 4 performance + evaporation + branching + earned autonomy + template health + outcome digest + popular unexamined) |
| `runtime.py` | 1,633 | Runtime bootstrap: adapters, event loop, projection init, `emit_and_broadcast()`, tool factory methods, model resolution |
| `knowledge_catalog.py` | 1,066 | Federated knowledge retrieval, Thompson Sampling, 6-signal composite scoring (ADR-044) |
| `forager.py` | 1,023 | Forager cycle orchestration: reactive/proactive/operator-triggered web acquisition with domain strategy memory |
| `queen_runtime.py` | 995 | Queen LLM loop with tool execution and `follow_up_colony` context |
| `app.py` | 822 | Starlette app setup, event loop, middleware, startup/shutdown, adapter wiring |
| `mcp_server.py` | 745 | FastMCP server with 35+ tools (MCP protocol) |
| `view_state.py` | 655 | `build_snapshot()`: UI state projection from projections → WebSocket payload |
| `maintenance.py` | 586 | Dedup, stale sweep, contradiction detection, confidence reset handlers |
| `structured_error.py` | 511 | `StructuredError` contracts with 35+ error codes and recovery hints |
| `memory_store.py` | 461 | In-memory projection layer for knowledge entries; Qdrant sync |
| `self_maintenance.py` | 460 | `MaintenanceDispatcher`: autonomy policy enforcement, distillation dispatch |
| `conflict_resolution.py` | 456 | Pareto + adaptive threshold conflict resolution for federation |
| `ws_handler.py` | 435 | WebSocket handler: `fan_out_event()`, `send_state()`, workspace subscriptions |
| `event_translator.py` | 325 | Event serialization and format translation |
| `config_validator.py` | 306 | Workspace configuration validation and schema enforcement |
| `memory_extractor.py` | 304 | Knowledge extraction from colony output and transcripts |
| `commands.py` | 301 | CLI command definitions and handlers |
| `admission.py` | 270 | Knowledge entry admission scoring and filtering |
| `template_manager.py` | 227 | Workspace template loading and management |
| `queen_thread.py` | 216 | Workflow thread management with step sequencing |
| `federation.py` | 209 | Federation protocol (push/pull replication) |
| `transcript_view.py` | 195 | Canonical colony transcript schema for A2A/MCP export |
| `agui_endpoint.py` | 194 | AG-UI integration endpoint |
| `trust.py` | 189 | Bayesian peer trust scoring (10th percentile of Beta posterior) |
| `credential_scan.py` | 187 | detect-secrets scanning and credential redaction |
| `memory_scanner.py` | 162 | Memory scanning utilities |
| `transcript.py` | 149 | Colony transcript assembly |
| `view_models.py` | 113 | View model types |
| `config_endpoints.py` | 101 | Configuration REST endpoints |
| `task_classifier.py` | 90 | Task classification for playbook selection |
| `metacognition.py` | 89 | Metacognitive utilities |
| `registry.py` | 83 | Service registry |
| `queen_shared.py` | 75 | Shared Queen utilities |
| `knowledge_constants.py` | 63 | `COMPOSITE_WEIGHTS`, `GAMMA_RATES`, `PRIOR_ALPHA/BETA`, decay constants |
| `model_registry_view.py` | 68 | Model registry view helpers |

**Routes sub-module (`src/formicos/surface/routes/`) — 2,594 lines:**

| File | Lines | Role |
|------|-------|------|
| `api.py` | 927 | REST endpoints: workspaces, colonies, knowledge, outcomes, create-demo, learning-summary |
| `knowledge_api.py` | 440 | Knowledge search, detail, feedback, configuration REST endpoints |
| `colony_io.py` | 430 | Colony input/output and lifecycle REST endpoints |
| `a2a.py` | 409 | Agent-to-agent federation protocol routes |
| `protocols.py` | 174 | WebSocket and SSE protocol handlers |
| `memory_api.py` | 170 | Memory/transcript search REST endpoints |
| `health.py` | 44 | Health check endpoint |

### Eval (`src/formicos/eval/`) — 2,069 lines

| File | Lines | Role |
|------|-------|------|
| `sequential_runner.py` | 713 | Sequential colony execution harness with metrics collection |
| `run.py` | 529 | Task runner with suite/task loading and result persistence |
| `compounding_curve.py` | 468 | Reinforcement curve tracking and convergence detection |
| `compare.py` | 343 | Benchmark result comparison and statistical analysis |

### Frontend (`frontend/src/`) — 13,509 lines

Lit Web Components, TypeScript, state management.

**Key components (>300 lines):**

| File | Lines | Role |
|------|-------|------|
| `components/colony-detail.ts` | 1,068 | Colony status, rounds, tools, transcript display |
| `components/knowledge-browser.ts` | 984 | Searchable knowledge entry browser with confidence tiers, hot/warm/cold badges |
| `state/store.ts` | 709 | Lit-based global state management: `applySnapshot()`, `applyEvent()`, `notify()` |
| `components/formicos-app.ts` | 668 | Root app shell with routing and layout |
| `components/colony-creator.ts` | 654 | Colony creation wizard |
| `components/queen-overview.ts` | 647 | Queen status, thread context, active colonies, learning card |
| `components/thread-view.ts` | 480 | Thread detail, goals, steps, colonies |
| `components/proactive-briefing.ts` | 466 | Proactive intelligence briefing with action buttons |
| `components/workflow-view.ts` | 439 | Workflow definition and monitoring |
| `components/knowledge-view.ts` | 400 | Individual knowledge entry detail view |
| `components/config-memory.ts` | 394 | Memory configuration UI |
| `components/model-registry.ts` | 389 | Available models and cost display |
| `components/template-editor.ts` | 381 | Template creation and editing |
| `components/caste-editor.ts` | 376 | Caste configuration editor |
| `components/queen-chat.ts` | 356 | Queen conversation UI with tool preview |
| `components/thread-timeline.ts` | 344 | Workflow thread progress timeline |
| `components/colony-audit.ts` | 301 | Colony event history audit trail |
| `components/playbook-view.ts` | 294 | Playbook definition display |
| `types.ts` | 866 | TypeScript types mirroring Python contracts |

**Infrastructure:**

| File | Lines | Role |
|------|-------|------|
| `ws/client.ts` | 109 | WebSocket client for live colony event streaming |
| `styles/shared.ts` | 118 | Shared CSS and design tokens |
| `helpers.ts` | 85 | DOM and utility helpers |

### Config (`config/`) — ~47 files

| Directory | Count | Purpose |
|-----------|-------|---------|
| Root YAML | 5 | `formicos.yaml`, `caste_recipes.yaml`, `experimentable_params.yaml`, `sandbox_profiles.yaml`, `seccomp-sandbox.json` |
| `playbooks/` | 12 | Operational guidance per task class × caste |
| `templates/` | 8 | Colony team configurations (code-review, debugging, demo-workspace, etc.) |
| `eval/suites/` | 10 | Task orchestration suites for benchmarking |
| `eval/tasks/` | 13 | Individual task definitions with acceptance criteria |

---

## Section 2: Data Flow Traces

### Flow 1: Task Intake → Colony Completion

Operator submits task via Queen chat → classification → spawn → round loop → completion → quality score → frontend update.

| Step | Function | File:Line |
|------|----------|-----------|
| 1 | `respond(workspace_id, thread_id)` | `surface/queen_runtime.py:483` |
| 2 | `_runtime.retrieve_relevant_memory()` | `surface/queen_runtime.py:509` |
| 3 | `_build_thread_context(thread_id, workspace_id)` | `surface/queen_runtime.py:868` |
| 4 | `generate_briefing(workspace_id, projections)` | `surface/queen_runtime.py:544` |
| 5 | `_handle_queen_tool_call(...)` | `surface/queen_runtime.py:620` |
| 6 | `classify_task(task_text)` | `surface/queen_tools.py:1039` |
| 7 | `_spawn_colony(inputs, workspace_id, thread_id)` | `surface/queen_tools.py:954` |
| 8 | `spawn_colony(workspace_id, thread_id, task, castes, ...)` | `surface/runtime.py:550` |
| 9 | `emit_and_broadcast(ColonySpawned(...))` | `surface/runtime.py:579` |
| 10 | `start_colony(colony_id)` | `surface/colony_manager.py:398` |
| 11 | `_run_colony_inner(colony_id)` | `surface/colony_manager.py:534` |
| 12 | `_make_strategy(colony.strategy)` | `surface/colony_manager.py:1931` |
| 13 | `_runtime.build_agents(colony_id)` | `surface/runtime.py:778` |
| 14 | `fetch_knowledge_for_colony(task, workspace_id, ...)` | `surface/runtime.py:1080` |
| 15 | `runner.run_round(colony_context, agents, strategy, ...)` | `surface/colony_manager.py:731` |
| 16 | Governance check: `result.governance.action == "complete"` | `surface/colony_manager.py:879` |
| 17 | `compute_quality_score(rounds, max_rounds, convergence, ...)` | `surface/colony_manager.py:267` |
| 18 | `emit_and_broadcast(ColonyCompleted(...))` | `surface/colony_manager.py:913` |
| 19 | `_post_colony_hooks(colony_id, colony, quality, ...)` | `surface/colony_manager.py:1025` |
| 20 | `follow_up_colony(colony_id, workspace_id, thread_id, ...)` | `surface/queen_runtime.py:333` |
| 21 | `ws_manager.send_state_to_workspace(workspace_id)` | `surface/colony_manager.py:530` |

### Flow 2: Context Assembly

Colony round start → system prompt → playbook → knowledge injection → routed outputs → skill bank.

| Step | Function | File:Line |
|------|----------|-----------|
| 1 | `assemble_context(agent, colony_context, round_goal, ...)` | `engine/context.py:371` |
| 2 | System prompt injection | `engine/context.py:405` |
| 3 | Round goal formatting | `engine/context.py:408` |
| 4 | Operational playbook injection (position 2.5) | `engine/context.py:412-414` |
| 5 | Structural context injection | `engine/context.py:417-422` |
| 6 | Input sources (chained colonies) | `engine/context.py:425-446` |
| 7 | Knowledge items injection (`[System Knowledge]`) | `engine/context.py:452-494` |
| 8 | **Threshold gate**: `if raw_similarity < _MIN_KNOWLEDGE_SIMILARITY: continue` | `engine/context.py:457-465` |
| 9 | Routed outputs assembly | `engine/context.py:499-508` |
| 10 | Merge summaries | `engine/context.py:512-517` |
| 11 | Previous round summary | `engine/context.py:520-525` |
| 12 | Skill bank retrieval (`RetrievalPipeline`) | `engine/context.py:537-548` |
| 13 | Exploration-confidence scoring | `engine/context.py:572-583` |
| 14 | Composite skill score: `0.50*semantic + 0.25*confidence + 0.20*freshness + 0.05*exploration` | `engine/context.py:578-583` |
| 15 | Top 3 skills selected, injected | `engine/context.py:586-606` |
| 16 | Return `ContextResult(messages, retrieved_skill_ids, knowledge_items_used)` | `engine/context.py:618` |

**Budget-aware assembly** (`engine/context.py:225-256`): `SCOPE_BUDGETS` allocates per-scope token budgets — task_knowledge 35%, observations 20%, structured_facts 15%, round_history 15%, scratch_memory 15%.

### Flow 3: Knowledge Lifecycle

#### Part A: Creation (colony completion → event → storage)

| Step | Function | File:Line |
|------|----------|-----------|
| 1 | `_hook_memory_extraction(colony_id, ws_id, succeeded)` | `surface/colony_manager.py:1048` |
| 2 | `extract_institutional_memory(colony_id, workspace_id, ...)` | `surface/colony_manager.py:1745` |
| 3 | `build_extraction_prompt(task, final_output, artifacts, ...)` | `surface/colony_manager.py:1783` |
| 4 | LLM extraction call (temperature=0.0) | `surface/colony_manager.py:1795` |
| 5 | `parse_extraction_response(response.content)` | `surface/colony_manager.py:1824` |
| 6 | `build_memory_entries(raw, colony_id, workspace_id, ...)` | `surface/colony_manager.py:1825` |
| 7 | Thread scope tagging | `surface/colony_manager.py:1836-1837` |
| 8 | Extraction quality gate: `_check_extraction_quality(entry)` | `surface/colony_manager.py:1842-1849` |
| 9 | Inline dedup check | `surface/colony_manager.py:1852` |
| 10 | Security scanning: `scan_entry(entry)` → 5-axis scan | `surface/colony_manager.py:1866-1867` |
| 11 | Admission policy: `_evaluate(entry, scanner_result)` | `surface/colony_manager.py:1873` |
| 12 | `emit_and_broadcast(MemoryEntryCreated(...))` | `surface/colony_manager.py:1896` |
| 13 | Status → verified (if source colony succeeded) | `surface/colony_manager.py:1904` |
| 14 | `emit_and_broadcast(MemoryExtractionCompleted(...))` | `surface/colony_manager.py:1917` |

#### Part B: Event → Projection → Vector

| Step | Function | File:Line |
|------|----------|-----------|
| 15 | `emit_and_broadcast(event)` — single mutation path | `surface/runtime.py:484` |
| 16 | `event_store.append(event)` → SQLite | `surface/runtime.py:486` |
| 17 | `projections.apply(event_with_seq)` | `surface/runtime.py:488` |
| 18 | `_on_memory_entry_created(store, event)` | `surface/projections.py:1512` |
| 19 | `store.memory_entries[entry_id] = data` | `surface/projections.py:1523` |
| 20 | `memory_store.sync_entry(entry_id, projection_entries)` | `surface/runtime.py:500` |
| 21 | Embedding text assembly | `surface/memory_store.py:59-65` |
| 22 | `VectorDocument(id, content, metadata)` | `surface/memory_store.py:67-87` |
| 23 | `vector.upsert(collection, docs)` → Qdrant | `surface/memory_store.py:88` |

#### Part C: Retrieval & Injection

| Step | Function | File:Line |
|------|----------|-----------|
| 24 | `catalog.search(query, workspace_id, thread_id, top_k)` | `surface/knowledge_catalog.py:318` |
| 25 | Thread-boosted search (if thread_id) | `surface/knowledge_catalog.py:363-372` |
| 26 | Institutional memory search | `surface/knowledge_catalog.py:382-387` |
| 27 | Legacy skill bank search | `surface/knowledge_catalog.py:397-399` |
| 28 | Parallel gather + dedup | `surface/knowledge_catalog.py:403-412` |
| 29 | Operator overlay application (pin/mute) | `surface/knowledge_catalog.py:415` |
| 30 | Workspace weights: `get_workspace_weights(workspace_id, projections)` | `surface/knowledge_catalog.py:420` |
| 31 | Composite scoring: `_composite_key(item, weights)` | `surface/knowledge_catalog.py:258` |
| 32 | Score = `0.38*semantic + 0.25*thompson + 0.15*freshness + 0.10*status + 0.07*thread + 0.05*cooccurrence` | `surface/knowledge_catalog.py:288-295` |
| 33 | Federated penalty: `federated_retrieval_penalty(item)` | `surface/knowledge_catalog.py:287` |
| 34 | Threshold gate in context assembly | `engine/context.py:457-465` |

### Flow 4: Model Routing

Colony spawning → model resolution → adapter selection → LLM call → parse → tool extraction.

| Step | Function | File:Line |
|------|----------|-----------|
| 1 | `_run_colony_inner()` starts colony | `surface/colony_manager.py:534` |
| 2 | `_runtime.build_agents(colony_id)` | `surface/colony_manager.py:540` |
| 3 | `build_agents()` with tier-aware resolution | `surface/runtime.py:778` |
| 4 | Three-tier cascade: explicit → tier_model → `resolve_model()` | `surface/runtime.py:811-814` |
| 5 | `resolve_model(caste, workspace_id)` — workspace config then system defaults | `surface/runtime.py:765` |
| 6 | `_route_fn()` closure calls `llm_router.route()` | `surface/colony_manager.py:566` |
| 7 | `LLMRouter.route()` — budget gate → routing table → adapter check | `surface/runtime.py:218` |
| 8 | `_resolve(model)` — prefix-based adapter selection (split on `/`) | `surface/runtime.py:410` |
| 9 | `llm_port.complete(model, messages, tools, temperature, max_tokens)` | `engine/runner.py:1480` |
| 10 | Response parsing: `response.tool_calls` → `_parse_tool_args()` | `engine/runner.py:1508-1521` |
| 11 | `_execute_tool()` with permission checks | `engine/runner.py:1552` |

### Flow 5: Convergence → Governance → Quality

Round outputs → convergence detection → governance decision → quality score.

| Step | Function | File:Line |
|------|----------|-----------|
| 1 | `run_round()` completes | `engine/runner.py:969` |
| 2 | `_compute_convergence()` | `engine/runner.py:1145` |
| 3 | Async embeddings → sync → heuristic fallback | `engine/runner.py:2271` |
| 4 | `_compute_convergence_from_vecs()` — 3-signal score | `engine/runner.py:2299` |
| 5 | `score = 0.4*goal_alignment + 0.3*stability + 0.3*min(1.0, progress*5.0)` | `engine/runner.py:2299` |
| 6 | `is_stalled = stability > 0.95 and progress < 0.01 and round > 2` | `engine/runner.py:2325` |
| 7 | `is_converged = score > 0.85 and stability > 0.90` | `engine/runner.py:2326` |
| 8 | `_evaluate_governance()` — 5 rules | `engine/runner.py:2397` |
| 9 | Rule 1: stalled + (recent_successful_code_execute OR recent_productive_action) + round ≥ 2 → "complete" (verified_execution_converged) | `engine/runner.py:2397` |
| 10 | Rule 2: stalled + stall_count ≥ 4 → "force_halt" | `engine/runner.py:2397` |
| 11 | Rule 3: stalled + stall_count ≥ 2 → "warn" | `engine/runner.py:2397` |
| 12 | Rule 4: goal_alignment < 0.2 + round > 3 → "warn" | `engine/runner.py:2397` |
| 13 | Rule 5: converged + round ≥ 2 → "complete" | `engine/runner.py:2397` |
| 14 | Stall tracking: `stall_count = prior + 1 if stalled else 0` | `surface/colony_manager.py:1167` |
| 15 | `compute_quality_score()` — 5-signal weighted geometric mean | `surface/colony_manager.py:267` |
| 16 | round_efficiency (w=0.20): `max(1.0 - rounds/max_rounds, 0.20)` | `surface/colony_manager.py:267` |
| 17 | convergence_score (w=0.25): `max(convergence, 0.01)` | `surface/colony_manager.py:267` |
| 18 | governance_score (w=0.20): `max(1.0 - warnings/3.0, 0.01)` | `surface/colony_manager.py:267` |
| 19 | stall_score (w=0.15): `max(1.0 - stalls/rounds, 0.01)` | `surface/colony_manager.py:267` |
| 20 | productive_ratio (w=0.20): `max(productive/total, 0.01)` | `surface/colony_manager.py:267` |

### Flow 6: Frontend Update

Colony event → projection → view_state snapshot → WebSocket → Lit component.

| Step | Function | File:Line |
|------|----------|-----------|
| 1 | `emit_and_broadcast(event)` — single mutation path | `surface/runtime.py:484` |
| 2 | `event_store.append(event)` | `surface/runtime.py:486` |
| 3 | `projections.apply(event_with_seq)` | `surface/runtime.py:488` |
| 4 | `ProjectionStore.apply()` — handler dispatch via `_HANDLERS` | `surface/projections.py:698` |
| 5 | Handler mutates projection state (e.g. `_on_colony_completed`) | `surface/projections.py:1060` |
| 6 | `ws_manager.fan_out_event(event_with_seq)` | `surface/runtime.py:489` |
| 7 | `fan_out_event()` → JSON to all workspace subscribers | `surface/ws_handler.py:219` |
| 8 | Payload: `{"type": "event", "event": model_dump_json()}` | `surface/ws_handler.py:223-226` |
| 9 | `ws.send_text(payload)` | `surface/ws_handler.py:231` |
| 10 | Frontend: `ws.onmessage` parses JSON, calls listeners | `frontend/src/ws/client.ts:54-58` |
| 11 | `store.handleMessage(msg)` routes to `applySnapshot()` or `applyEvent()` | `frontend/src/state/store.ts:118` |
| 12 | `applyEvent(event)` updates state slices | `frontend/src/state/store.ts:145` |
| 13 | `this.notify()` calls all subscribers | `frontend/src/state/store.ts:142` |
| 14 | Components: `store.subscribe(() => this.syncFromStore())` | `frontend/src/components/formicos-app.ts:241` |
| 15 | Lit reactivity: `@state` changes trigger re-render | — |

**Full snapshot path** (on WebSocket connect): `send_state()` → `build_snapshot()` (`surface/view_state.py:21`) → `_build_tree()` (`surface/view_state.py:45-149`) → `applySnapshot()` on frontend.

---

## Section 3: Event Type Catalog

**65 event types** (closed union). Defined in `core/events.py`. Union type `FormicOSEvent`. Handler registry in `projections.py`. Wave 59 added `MemoryEntryRefined`, `LearningLoopTemplateUpdated`, `LearningLoopTemplateCreated`.

### Colony Lifecycle (11 events)

| Event | Handler | Projection Modified |
|-------|---------|-------------------|
| `ColonySpawned` | `_on_colony_spawned` | Creates `ColonyProjection`; updates thread status; infers suggestion follow-through |
| `RoundStarted` | `_on_round_started` | Audit-only (logs round initiation) |
| `PhaseEntered` | `_on_phase_entered` | Audit-only (logs phase transition) |
| `AgentTurnStarted` | `_on_agent_turn_started` | Creates `AgentProjection` |
| `AgentTurnCompleted` | `_on_agent_turn_completed` | Updates `AgentProjection`; records tokens; tracks productive vs observation tool calls |
| `RoundCompleted` | `_on_round_completed` | Updates convergence, cost, validator fields; records budget snapshot |
| `ColonyCompleted` | `_on_colony_completed` | Marks colony "completed"; persists artifacts; records `ColonyOutcome` |
| `ColonyFailed` | `_on_colony_failed` | Marks colony "failed"; records failure reason |
| `ColonyKilled` | `_on_colony_killed` | Marks colony "killed"; records actor; updates operator behavior |
| `ColonyRedirected` | `_on_colony_redirected` | Updates active goal; appends redirect history |
| `ColonyEscalated` | `_on_colony_escalated` | Sets routing_override (replay-safe escalation) |

### Thread & Workspace (4 events)

| Event | Handler | Projection Modified |
|-------|---------|-------------------|
| `WorkspaceCreated` | `_on_workspace_created` | Creates `WorkspaceProjection` with config snapshot |
| `ThreadCreated` | `_on_thread_created` | Creates `ThreadProjection`; stores goal, expected outputs |
| `ThreadRenamed` | `_on_thread_renamed` | Updates thread display name |
| `ThreadGoalSet` | `_on_thread_goal_set` | Updates thread goal and expected_outputs |

### Thread Workflow (3 events)

| Event | Handler | Projection Modified |
|-------|---------|-------------------|
| `ThreadStatusChanged` | `_on_thread_status_changed` | Updates thread status (active/completed/archived) |
| `WorkflowStepDefined` | `_on_workflow_step_defined` | Appends `WorkflowStep` to thread |
| `WorkflowStepCompleted` | `_on_workflow_step_completed` | Marks step complete/failed; increments continuation_depth |

### Knowledge System (13 events)

| Event | Handler | Projection Modified |
|-------|---------|-------------------|
| `MemoryEntryCreated` | `_on_memory_entry_created` | Stores in `memory_entries`; seeds confidence; marks competing_pairs dirty |
| `MemoryEntryStatusChanged` | `_on_memory_entry_status_changed` | Updates entry status and timestamp; marks competing_pairs dirty |
| `MemoryExtractionCompleted` | `_on_memory_extraction_completed` | Adds colony_id to `memory_extractions_completed` set |
| `KnowledgeAccessRecorded` | `_on_knowledge_access_recorded` | Appends accesses to colony; accumulates per-entry usage counts |
| `MemoryEntryScopeChanged` | `_on_memory_entry_scope_changed` | Updates entry scope (thread → global promotion) |
| `MemoryConfidenceUpdated` | `_on_memory_confidence_updated` | Updates Beta(alpha, beta); tracks peak_alpha for mastery restoration |
| `MemoryEntryMerged` | `_on_memory_entry_merged` | Updates target content/domains; marks source as rejected |
| `KnowledgeDistilled` | `_on_knowledge_distilled` | Upgrades to stable decay_class; elevates alpha; marks sources |
| `KnowledgeEntityCreated` | `_on_knowledge_entity_created` | Increments `colony.kg_entity_count` |
| `KnowledgeEdgeCreated` | `_on_knowledge_edge_created` | Increments `colony.kg_edge_count` |
| `KnowledgeEntityMerged` | `_on_knowledge_entity_merged` | Audit-only |
| `KnowledgeEntryOperatorAction` | `_on_knowledge_entry_operator_action` | Modifies operator_overlays: pin/unpin, mute/unmute, invalidate/reinstate |
| `KnowledgeEntryAnnotated` | `_on_knowledge_entry_annotated` | Appends `OperatorAnnotation` to overlays |
| `MemoryEntryRefined` | `_on_memory_entry_refined` | Updates entry content/title in-place; increments refinement_count (Wave 59) |

### Configuration & Approvals (5 events)

| Event | Handler | Projection Modified |
|-------|---------|-------------------|
| `WorkspaceConfigChanged` | `_on_workspace_config_changed` | Updates workspace config snapshot |
| `ApprovalRequested` | `_on_approval_requested` | Creates `ApprovalProjection` |
| `ApprovalGranted` | `_on_approval_granted` | Updates approval status to "granted" |
| `ApprovalDenied` | `_on_approval_denied` | Updates approval status to "denied" |
| `ConfigSuggestionOverridden` | `_on_config_suggestion_overridden` | Records `ConfigOverrideRecord` in operator_overlays |

### Colony Templates & Naming (4 events)

| Event | Handler | Projection Modified |
|-------|---------|-------------------|
| `ColonyTemplateCreated` | `_on_colony_template_created` | Creates `TemplateProjection` |
| `ColonyTemplateUsed` | `_on_colony_template_used` | Increments template use_count |
| `ColonyNamed` | `_on_colony_named` | Updates colony.display_name |
| `SkillConfidenceUpdated` | `_on_skill_confidence_updated` | Audit-only |

### Service & Inter-Colony (5 events)

| Event | Handler | Projection Modified |
|-------|---------|-------------------|
| `ServiceQuerySent` | `_on_service_query_sent` | Appends chat messages to sender and target colonies |
| `ServiceQueryResolved` | `_on_service_query_resolved` | Appends resolution preview to source colony |
| `ColonyServiceActivated` | `_on_colony_service_activated` | Sets colony status="service" |
| `SkillMerged` | `_on_skill_merged` | Audit-only |
| `ColonyChatMessage` | `_on_colony_chat_message` | Appends `ChatMessageProjection`; records operator directive patterns |

### Execution & Artifacts (2 events)

| Event | Handler | Projection Modified |
|-------|---------|-------------------|
| `CodeExecuted` | `_on_code_executed` | Stub handler (sandbox tracking deferred) |
| `ContextUpdated` | ❌ No handler | Not projected; audit/infrastructure only |

### Models & Resources (3 events)

| Event | Handler | Projection Modified |
|-------|---------|-------------------|
| `ModelRegistered` | `_on_model_registered` | Updates workspace.models dict |
| `ModelAssignmentChanged` | `_on_model_assignment_changed` | Updates workspace.model_assignments |
| `TokensConsumed` | `_on_tokens_consumed` | Records token spend in `BudgetSnapshot` (model-level breakdown) |

### Queen & Operator (2 events)

| Event | Handler | Projection Modified |
|-------|---------|-------------------|
| `QueenMessage` | `_on_queen_message` | Appends `ChatMessageProjection` with queen metadata |
| `QueenNoteSaved` | `_on_queen_note_saved` | Records thread-scoped note in `queen_notes` |

### Merge & Strategy (2 events)

| Event | Handler | Projection Modified |
|-------|---------|-------------------|
| `MergeCreated` | `_on_merge_created` | Creates `MergeProjection` |
| `MergePruned` | `_on_merge_pruned` | Removes `MergeProjection` |

### Federation & CRDT (5 events)

| Event | Handler | Projection Modified |
|-------|---------|-------------------|
| `CRDTCounterIncremented` | `_on_crdt_counter_incremented` | Updates entry CRDT counter value |
| `CRDTTimestampUpdated` | `_on_crdt_timestamp_updated` | Updates LWW timestamp register |
| `CRDTSetElementAdded` | `_on_crdt_set_element_added` | Appends element to G-Set |
| `CRDTRegisterAssigned` | `_on_crdt_register_assigned` | Updates LWW Register |
| `DeterministicServiceRegistered` | ❌ No handler | Stub (not projected) |

### Foraging (4 events)

| Event | Handler | Projection Modified |
|-------|---------|-------------------|
| `ForageRequested` | `_on_forage_requested` | Records pending forage request |
| `ForageCycleCompleted` | `_on_forage_cycle_completed` | Creates `ForageCycleSummary`; preserves colony/thread linkage |
| `DomainStrategyUpdated` | `_on_domain_strategy_updated` | Updates `DomainStrategyProjection` with preferred_level, success/failure counts |
| `ForagerDomainOverride` | `_on_forager_domain_override` | Records `DomainOverrideProjection` (trust/distrust/reset) |

### Learning Loop (2 events, Wave 59)

| Event | Handler | Projection Modified |
|-------|---------|-------------------|
| `LearningLoopTemplateCreated` | `_on_learning_loop_template_created` | Creates learned template in projection |
| `LearningLoopTemplateUpdated` | `_on_learning_loop_template_updated` | Updates template success/failure counts |

### Multi-Colony Orchestration (1 event)

| Event | Handler | Projection Modified |
|-------|---------|-------------------|
| `ParallelPlanCreated` | `_on_parallel_plan_created` | Sets thread.active_plan and thread.parallel_groups for DAG delegation |

### Handler Coverage

- **63 events** with projection handlers
- **2 events** without handlers: `ContextUpdated` (audit/infrastructure), `DeterministicServiceRegistered` (stub)

---

## Section 4: Configuration Seams

### Configuration Files

| Config File | Consumer | What It Controls |
|-------------|----------|------------------|
| `config/formicos.yaml` | `core/settings.py` → `load_config()` | Model registry, routing defaults, governance limits, embedding endpoint, vector DB, context budgets, effector limits |
| `config/caste_recipes.yaml` | `core/settings.py` → `load_castes()` | System prompts, tools, temperature, max_tokens, max_iterations, execution time, tool call limits per caste |
| `config/playbooks/*.yaml` | `engine/playbook_loader.py` → `load_playbook()` | Operational guidance per task class × caste. Resolution: `{class}_{caste}` → `{class}` → `generic_{caste}` → `generic` |
| `config/templates/*.yaml` | `surface/template_manager.py` → `load_templates()` | Colony team configurations: castes, strategy, budget, max_rounds |
| `config/eval/suites/*.yaml` | `eval/run.py` | Task orchestration suites for benchmarking |
| `config/eval/tasks/*.yaml` | `eval/run.py` | Individual task definitions with acceptance criteria |
| `config/sandbox_profiles.yaml` | `adapters/sandbox_manager.py` | Execution profiles: memory, cores, network access |
| `config/experimentable_params.yaml` | (reference) | Whitelist of dynamically tunable parameters with bounds |
| `config/seccomp-sandbox.json` | `adapters/sandbox_manager.py` | Seccomp syscall allowlist for sandbox containers |

### Environment Variables

| Variable | Default | Consumer | Purpose |
|----------|---------|----------|---------|
| `FORMICOS_DATA_DIR` | `./data` | `formicos.yaml` interpolation | Workspace data directory |
| `LLM_HOST` | `http://localhost:8008` | `formicos.yaml` model registry | llama.cpp server endpoint |
| `EMBED_URL` | `http://localhost:8200` | `formicos.yaml` embedding | Embedding service endpoint |
| `QDRANT_URL` | `http://localhost:6333` | `formicos.yaml` vector | Vector database endpoint |
| `ANTHROPIC_API_KEY` | (required) | `surface/app.py:269` | Claude API authentication |
| `GEMINI_API_KEY` | (required) | `surface/app.py:275` | Gemini API authentication |
| `DEEPSEEK_API_KEY` | (required) | `formicos.yaml` | DeepSeek API authentication |
| `MINIMAX_API_KEY` | (required) | `formicos.yaml` | MiniMax API authentication |
| `SERPER_API_KEY` | (optional) | `surface/app.py:379` | Web search provider |
| `LLM_SLOTS` | `2` | `adapters/llm_openai_compatible.py` | Concurrent LLM request slots |
| `FORMICOS_KNOWLEDGE_MIN_SIMILARITY` | `0.50` | `engine/context.py:52` | Knowledge injection threshold |
| `FORMICOS_MAINTENANCE_INTERVAL_S` | `86400` | `surface/app.py:684` | Maintenance scheduler interval (seconds) |
| `FORMICOS_OTEL_ENABLED` | disabled | `surface/app.py:727` | OpenTelemetry sink opt-in |
| `WORKSPACE_IMAGE` | `python:3.12-slim` | `adapters/sandbox_manager.py:48` | Workspace executor container image |
| `WORKSPACE_MEMORY_MB` | `512` | `adapters/sandbox_manager.py:59` | Workspace container memory limit |
| `SANDBOX_ENABLED` | `true` | `adapters/sandbox_manager.py:63` | Docker sandbox feature flag |
| `WORKSPACE_ISOLATION` | `true` | `adapters/sandbox_manager.py:66` | Workspace container isolation |
| `GIT_CLONE_DEPTH` | `1` | `adapters/sandbox_manager.py:100` | Shallow clone depth |
| `LLM_MODEL_FILE` | `Qwen3-30B-A3B-...` | `surface/view_state.py:355` | Local model filename |

### Hardcoded Constants

**Knowledge system** (`surface/knowledge_constants.py`):

```
COMPOSITE_WEIGHTS = {semantic: 0.38, thompson: 0.25, freshness: 0.15,
                     status: 0.10, thread: 0.07, cooccurrence: 0.05}
GAMMA_RATES = {ephemeral: 0.98, stable: 0.995, permanent: 1.0}
PRIOR_ALPHA = 5.0, PRIOR_BETA = 5.0
MAX_ELAPSED_DAYS = 180.0
```

**Context assembly** (`engine/context.py`):

```
_MIN_KNOWLEDGE_SIMILARITY = 0.50  (env override: FORMICOS_KNOWLEDGE_MIN_SIMILARITY)
SCOPE_BUDGETS = {task_knowledge: 35%, observations: 20%, structured_facts: 15%,
                 round_history: 15%, scratch_memory: 15%}
```

**Runner** (`engine/runner.py`):

```
_EVAPORATE_MIN = 0.85, _EVAPORATE_MAX = 0.95  (adaptive evaporation bounds)
_STRENGTHEN = 1.15, _WEAKEN = 0.75  (pheromone reinforcement/reduction)
_LOWER = 0.1, _UPPER = 2.0  (pheromone floor/ceiling)
_BRANCHING_STAGNATION_THRESHOLD = 2.0
TOOL_OUTPUT_CAP = 2000 chars
```

**Sandbox** (`adapters/sandbox_manager.py`):

```
SANDBOX_IMAGE = "formicos-sandbox:latest"
DEFAULT_TIMEOUT_S = 10, MAX_TIMEOUT_S = 30
MEMORY_LIMIT_MB = 256, MAX_OUTPUT_BYTES = 50,000
WORKSPACE_PIDS_LIMIT = 512, WORKSPACE_MAX_TIMEOUT_S = 120
```

**Egress** (`adapters/egress_gateway.py`):

```
_DEFAULT_MAX_BYTES = 500,000 (500 KB per fetch)
_DEFAULT_RATE_LIMIT = 2.0 req/s, _DEFAULT_RATE_BURST = 5
```

### Workspace-Level Overrides

Persisted via `WorkspaceConfigChanged` events. Consumed by `knowledge_constants.py` → `get_workspace_weights()`. Falls back to global `COMPOSITE_WEIGHTS`.

### Configuration Loading Sequence

1. **App startup** (`surface/app.py:186-189`): Load `formicos.yaml` via `load_config()`, load `caste_recipes.yaml` via `load_castes()`, interpolate `${VAR:default}` patterns
2. **Settings validation** (`core/settings.py`): Parse into Pydantic v2 models, derive provider from model address
3. **Adapter instantiation** (`surface/app.py:199-398`): SQLite, embedding, Qdrant, LLM adapters (only if API keys present), knowledge catalog, forager
4. **Runtime initialization** (`surface/app.py:327-400`): `LLMRouter` with routing table, cost function from model registry, wire into `Runtime` singleton
5. **Lifespan startup** (`surface/app.py:654-737`): Replay events into projections, rehydrate colony state, start maintenance scheduler, start telemetry bus

---

## Section 5: Cross-Cutting Concerns

### 1. Replay Safety

**Single mutation path**: All state changes flow through `emit_and_broadcast()` (`runtime.py:484`), which atomically: appends to event store → applies to projection → broadcasts to WebSocket → syncs memory store.

**Replay on cold start**:
1. App boots, loads event log from SQLite (single-writer)
2. `ProjectionStore.replay(all_events)` replays in seq order (`projections.py:708-714`)
3. For each event: type name extracted → handler from `_HANDLERS` called → in-memory projection mutated
4. Monotonic seq guard: `if seq > self.last_seq: self.last_seq = seq` (`projections.py:701-702`) — rejects out-of-order
5. Competing pairs marked dirty; rebuilt lazily on first access (`projections.py:712-714`, `781-783`)
6. `MemoryStore` rebuilds Qdrant from projection entries (`memory_store.py:109-125`)

**Idempotency**: Most handlers overwrite (upsert) or append to lists. Seq monotonic check prevents double-processing.

### 2. Budget Enforcement

**Budget truth**: `BudgetSnapshot` dataclass (`projections.py:287-300`) tracks `total_cost`, `total_input_tokens`, `total_output_tokens`, `model_usage` dict.

**Enforcement points**:
- **Per-round**: `budget_remaining = budget_limit - total_colony_cost - cumulative_cost` (`runner.py:1045`)
- **Per-round accumulation**: `agent_costs` list; `cumulative_cost = sum(agent_costs)` (`runner.py:1035-1042`)
- **LLM context injection**: `build_budget_block()` inserts budget info at message position 1 (`runner.py:1445-1458`)
- **Token recording**: `TokensConsumed` event → `_on_tokens_consumed()` handler records spend in colony and workspace budgets (`projections.py:1286-1310`)
- **Context assembly**: Per-scope budgets via `SCOPE_BUDGETS` with early-exit (`context.py:225-256`)
- **Queries**: `workspace_budget()`, `colony_budget()`, `workspace_budget_utilization()` (`projections.py:830-851`)

**When exceeded**: Escalation triggered or round ended. Queen/router decides whether to continue or cap. See ADR-022.

### 3. Tool Permission Model

**Deny-by-default** (ADR-023). Implemented in `engine/tool_dispatch.py:570-650`.

**Caste policies** (`tool_dispatch.py:570-609`):

| Caste | Allowed Categories | Denied Tools | Per-Iteration Cap |
|-------|-------------------|-------------|-------------------|
| Queen | delegate, read_fs, vector_query | code_execute | 10 |
| Coder | exec_code, vector_query, read_fs, write_fs, network_out | — | 15 |
| Reviewer | vector_query, read_fs | code_execute | 8 |
| Researcher | vector_query, search_web, read_fs, network_out | code_execute | 10 |
| Archivist | vector_query, read_fs, write_fs | code_execute | 8 |

**Check chain** (`check_tool_permission()` at `tool_dispatch.py:612-650`):
1. Unknown caste → deny
2. Tool in explicit deny list → deny
3. Tool not in `TOOL_CATEGORY_MAP` → deny (unknown tool)
4. Category not in policy's allowed_categories → deny
5. `iteration_tool_count >= limit` → deny
6. All pass → return None (granted)

### 4. Federation Trust

**Bayesian trust** using 10th percentile of Beta posterior (not mean). Implemented in `surface/trust.py`.

| Function | Location | Purpose |
|----------|----------|---------|
| `PeerTrust` | `trust.py:15-44` | `alpha`, `beta` fields; `score` property = `_beta_ppf_approx(0.10, alpha, beta)` |
| `record_success()` | `trust.py:29-30` | `alpha += 1.0` |
| `record_failure()` | `trust.py:32-38` | `beta += 2.0` (asymmetric — failures count double) |
| `decay()` | `trust.py:40-44` | Exponential decay toward prior Beta(1,1) |
| `trust_discount()` | `trust.py:47-62` | Per-hop decay 0.6–0.85 range; capped at 0.5 |
| `entry_confidence_score()` | `trust.py:65-79` | 10th percentile of entry's Beta(alpha, beta) |
| `federated_retrieval_penalty()` | `trust.py:82-146` | Combines entry posterior (60%) + status floor (40%) + hop discount → multiplier in [0.1, 0.9] |

**Status floors** (`trust.py:121-128`): verified=0.8, active=0.55, candidate=0.35, stale=0.2.

**Key properties**: New peers start at Beta(1,1). Need ~30+ successes to reach 0.8 trust. Federated entries never outweigh local (hop discount cap 0.5). Candidates can't outrank verified entries.

### 5. Proactive Intelligence

**14 deterministic rules** (no LLM). Generated from projection state. Implemented in `surface/proactive_intelligence.py`.

| # | Rule | Category | Lines | Trigger |
|---|------|----------|-------|---------|
| 1 | Confidence decline | confidence | 139–184 | Entry alpha dropped >20% in 7 days |
| 2 | Contradiction | contradiction | 190–270 | 2+ verified entries, high domain overlap, classified as contradiction |
| 3 | Federation trust drop | federation | 276–302 | Peer trust score < 0.5 |
| 4 | Coverage gap | coverage | 308–360 | Domain with ≥3 entries, prediction_error_count ≥ 3 |
| 5 | Stale cluster | staleness | 366–462 | Co-occurrence cluster where ALL entries have error_count > 3 |
| 6 | Merge opportunity | merge | 468–513 | 2+ entries, domain overlap ≥ 50%, title similarity ≥ 50% |
| 7 | Federation inbound | inbound | 519–561 | Foreign entries in domain with zero local coverage |
| 8 | Strategy efficiency | performance | 567–612 | Strategy quality gap > 15% vs best (≥3 samples) |
| 9 | Diminishing rounds | performance | 618–645 | ≥2 colonies ran 10+ rounds, <40% quality |
| 10 | Cost outlier | performance | 651–684 | Colony cost > 2.5x workspace median (≥5 samples) |
| 11 | Knowledge ROI | performance | 690–726 | ≥3 successful colonies, >30% cost with zero entries extracted |
| 12 | Adaptive evaporation | evaporation | 761–882 | Domain-level decay class recommendation based on error/demotion/confidence |
| 13 | Branching stagnation | stagnation | 1076–1154 | ≥2 of 3 branching factors low AND failure rate ≥30% |
| 14 | Earned autonomy | earned_autonomy | 1207–1306 | ≥5 follow-throughs (promote) or ≥3 kills (demote) |

**Entry point**: `generate_briefing(workspace_id, projections)` at line 1813. Returns `ProactiveBriefing` with insights + stats.

**Trigger points**:
- Scheduled: `MaintenanceDispatcher` calls at maintenance cycle (`self_maintenance.py`)
- Queen context: Injected as briefing_section in system message (`queen_runtime.py`)
- REST: `GET /api/v1/briefing/{workspace_id}` (`routes/api.py`)
- MCP: `/briefing/{workspace_id}` resource (`mcp_server.py`)
- Forage: Coverage/confidence/stale rules include `forage_signal` metadata

**Severity**: `action_required` > `attention` > `info`.

---

## Section 6: Test Map

### Overview

| Metric | Count |
|--------|-------|
| Python test files | 231 |
| Test functions | 2,770 |
| Async test functions | 594 |
| Test classes | 635 |

### Tests by Layer

| Directory | Focus | Files | Tests |
|-----------|-------|-------|-------|
| `tests/unit/core/` | Events, types, CRDTs, settings | 12 | 136 |
| `tests/unit/engine/` | Runner, strategies, scoring, evaporation, playbooks | 19 | 329 |
| `tests/unit/adapters/` | LLM, storage, vector, sandbox, security, web foraging | 24 | 396 |
| `tests/unit/surface/` | Colony manager, knowledge, projections, federation, Queen, API, maintenance | 137 | 1,495 |
| `tests/unit/config/` | Caste prompts | 2 | 9 |
| `tests/unit/benchmark/` | Sequential runner, eval harness | 2 | — |
| `tests/unit/` (root) | Layer boundaries, bootstrap, replay | 4 | ~20 |
| `tests/integration/` | Multi-component workflows, end-to-end scenarios | 21 | 246 |
| `tests/contract/` | Event schema, TypeScript parity, contract bootstrap | 4 | 36 |
| `tests/smoke/` | Critical path validation (events, decay, credentials, MCP) | 1 | 34 |
| `tests/features/` | BDD specs (pytest-bdd with Gherkin features from `docs/specs/`) | 2 + 8 steps | ~15 scenarios |

### Key Test Patterns

**Root conftest** (`tests/conftest.py`):
- `MockLLM`: Configurable LLM port with recorded calls
- `MockResponse`: Fields for content, tool_calls, tokens, model, stop_reason
- Auto-loads 7 BDD step modules

**Features conftest** (`tests/features/conftest.py`):
- `event_collector`: `EventCollector` implementing `EventStorePort`
- `proj_env`: Projection environment with store, collector, `FakeRuntime`
- Helper factories: `make_recipe()`, `make_agent()`, `make_colony_context()`, `setup_workspace()`, `setup_thread()`, `setup_colony()`

**Markers**: `@pytest.mark.asyncio` (594 tests), `@pytest.mark.parametrize` (contract tests)

### Surface Test Subcategories

The surface layer has the most tests (1,495) covering:

| Subcategory | Key Files | Focus |
|-------------|-----------|-------|
| Knowledge system | `test_knowledge_catalog.py`, `test_thompson_sampling.py`, `test_bayesian_confidence.py`, `test_tiered_retrieval.py` | Confidence, retrieval, scoring |
| Maintenance | `test_self_maintenance.py`, `test_proactive_intelligence.py`, `test_contradiction_detection.py`, `test_distillation.py` | 14 rules, dedup, decay |
| Federation | `test_federation.py`, `test_trust.py`, `test_conflict_resolution.py` | Bayesian trust, Pareto resolution |
| Forager | `test_wave44_forager.py`, `test_wave44_reactive_trigger.py`, `test_wave46_forager_surface.py` | Web acquisition, domain strategy |
| Colony lifecycle | `test_colony_manager.py`, `test_parallel_planning.py`, `test_step_continuation.py` | Lifecycle, DAG, steps |
| Queen | `test_queen_runtime.py`, `test_directives.py`, `test_operator_overlays.py` | Orchestration, directives |
| API | `test_knowledge_route.py`, `test_mcp_server.py`, `test_a2a_routes.py`, `test_ws_handler.py` | REST, MCP, A2A, WS |
| Errors | `test_structured_error.py`, `test_structured_error_wiring.py` | Error contracts |

### Standalone Test Scripts

| Script | Purpose |
|--------|---------|
| `tests/smoke_test.py` | Standalone smoke (not pytest) |
| `tests/smoke_wave54.py` | Wave 54 smoke test |
| `tests/smoke_wave54_quality.py` | Quality validation smoke |
| `tests/test_contract_parity_v2.py` | Global contract parity (12 tests) |

---

## Projection State Structure

The `ProjectionStore` (`projections.py`) maintains these read models:

| Field | Type | Purpose |
|-------|------|---------|
| `workspaces` | `dict[str, WorkspaceProjection]` | Config, threads, models per workspace |
| `colonies` | `dict[str, ColonyProjection]` | Status, rounds, agents, artifacts, budget, escalation |
| `memory_entries` | `dict[str, dict]` | Knowledge entries: confidence, domains, scope, CRDT state, overlays |
| `templates` | `dict[str, TemplateProjection]` | Template usage counts |
| `merges` | `dict[str, MergeProjection]` | Merge relationships |
| `approvals` | `dict[str, ApprovalProjection]` | Approval workflow state |
| `operator_behavior` | `OperatorBehaviorProjection` | Feedback, kills, directives, suggestion follow-through |
| `operator_overlays` | `OperatorOverlayState` | Pin/mute/invalidate sets, annotations, config overrides |
| `domain_strategies` | `dict[str, DomainStrategyProjection]` | Fetch preferences per workspace/domain |
| `forage_cycles` | `list[ForageCycleSummary]` | Forage audit trail |
| `domain_overrides` | `dict[str, DomainOverrideProjection]` | Operator trust controls |
| `knowledge_entry_usage` | `dict[str, dict]` | Per-entry usage counts from `KnowledgeAccessRecorded` |
| `competing_pairs` | (lazy) | Bidirectional competing hypothesis pairs |
| `colony_outcomes` | `dict[str, ColonyOutcome]` | Performance summaries |
| `queen_notes` | `dict[str, ...]` | Private thread-scoped notes |
