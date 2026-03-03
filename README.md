# Formic-OS

A local-first colony operating system that coordinates multiple LLM agents into self-organizing swarms using stigmergic coordination, dynamic topology routing, and shared environmental state.

**Version**: 0.9.0

## Architecture

Formic-OS applies biological colony intelligence to multi-agent AI. Instead of explicit message-passing between agents, agents read shared state, perform work, and write results back. Other agents observe the changes in the next round. A dynamic topology (DyTopo) -- computed from semantic similarity of agent intent descriptors -- determines execution order each round.

### The 5-Phase DyTopo Loop

Every colony run executes rounds of the following phases:

1. **Goal** -- The manager agent decomposes the task into round objectives.
2. **Intent** -- Each agent declares a short key/query descriptor of its planned work.
3. **Routing** -- Intent embeddings are compared by cosine similarity to build a DAG. Agents with related intents are linked. Topological sort determines execution order.
4. **Execution** -- Agents run in parallel by topological level. Agents at the same DAG depth execute concurrently via `asyncio.gather()`. Each receives upstream outputs plus shared context. Agents can call tools (file I/O, code execution, MCP tools).
5. **Compression** -- Round outputs are summarized. TKG facts extracted. Governance checks run (convergence, stall detection, path diversity). Skills distilled on colony completion.

### Key Concepts

- **Colony**: A group of agents working on a single task. Each colony has an isolated context tree, workspace directory, and Qdrant namespace. Colonies can be paused, resumed, and destroyed independently.
- **Castes & YAML Recipes**: Agent roles (Manager, Architect, Coder, Reviewer, Researcher, DyTopo). The `config/caste_recipes.yaml` strictly decouples the LLM model, temperature, escalation rules, and tools from the Python codebase.
- **Subcastes**: Model tier abstraction (heavy/balanced/light) that maps to concrete model assignments.
- **Teams**: Agent groupings within a colony, each with independent DyTopo routing.
- **Skill Bank**: Cross-colony skill library. Skills distilled from completed colonies transfer to future runs.
- **Supercolony**: The layer managing multiple concurrent colonies.
- **Durable Execution**: If the system crashes, FormicOS reads from `.formicos/sessions/state.json` to resume exact execution without data loss.

### System Layers

```
Web Dashboard         SPA: colony control, topology graph (with round history),
                      per-colony streaming, team builder, HITL approval,
                      workspace browser, Objects inspector
API Gateway           REST + WebSocket (colony-scoped), request validation
Colony Manager        Lifecycle: create / start / pause / resume / destroy
Colony                Orchestrator (5-phase loop, parallel DAG execution),
                      Agents, Router, Governance
Shared Services       Context Tree, Skill Bank, Archivist, RAG Engine,
                      Session Manager, Audit Log
External I/O          Model Registry, MCP Gateway, Workspace (per-colony)
Infrastructure        llama.cpp, Qdrant, Docker, GPU
```

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Runtime | Python 3.12 | Core application |
| API | FastAPI + Uvicorn | REST + WebSocket server |
| LLM Client | AsyncOpenAI (openai SDK) | Streaming inference |
| LLM Inference | llama.cpp (CUDA) | Local GPU inference, OpenAI-compatible API |
| LLM Model | Qwen3-30B-A3B-Instruct Q4_K_M | Primary reasoning model |
| Embeddings | BGE-M3 via llama.cpp | 1024-dim dense vectors for RAG |
| Routing Embeddings | all-MiniLM-L6-v2 (sentence-transformers) | 384-dim CPU embeddings for DyTopo |
| Vector DB | Qdrant | Semantic search, per-colony namespaces |
| Tool Integration | MCP (Model Context Protocol) | External tool servers |
| Frontend | Vanilla JS + Cytoscape.js | SPA dashboard, topology graph |
| Containers | Docker Compose | Multi-service orchestration |
| Resilience | tenacity, json-repair | Retry logic, malformed JSON recovery |

**No LangChain** -- this is an intentional architectural constraint. Every dependency must earn its place.

## Project Structure

```
Formic-OS/
  src/                    # Application source code
    __main__.py           #   Entry point
    server.py             #   FastAPI app factory, lifespan, legacy routes
    models.py             #   Pydantic models (config, API schemas — leaf dependency)
    api/                  #   Extracted V1 route modules (v0.7.9)
      ws.py               #     ConnectionManager + ConnectionManagerV1
      helpers.py          #     V1 helper functions
      callbacks.py        #     WebSocket callback factories
      routes/             #     V1 endpoint modules
        system.py         #       /system, /health, /metrics, /models, /tools
        auth.py           #       /auth/keys CRUD
        colonies.py       #       Colony CRUD, lifecycle, results
        workspace.py      #       Workspace file operations
        admin.py          #       /admin/rebuild, diagnostics, queue
        sessions.py       #       /sessions, /approvals
        castes.py         #       /castes, /skills CRUD
    orchestrator.py       #   5-phase DyTopo loop
    agents.py             #   LLM agent execution (streaming, tool calling)
    router.py             #   NumPy-based DAG from intent embeddings
    context.py            #   AsyncContextTree (scoped state store)
    colony_manager.py     #   Colony lifecycle management
    model_registry.py     #   Multi-backend model dispatch
    auth.py               #   API Key authentication (ClientAPIKey, APIKeyStore)
    webhook.py            #   Outbound webhook dispatcher with backoff
    worker.py             #   VRAM-aware auto-scaling worker pool
    skill_bank.py         #   Cross-colony skill library
    archivist.py          #   Summarization, TKG extraction, skill distillation
    governance.py         #   Convergence, stall, path diversity checks
    rag.py                #   Qdrant-backed vector search + Semantic Slicing
    mcp_client.py         #   MCP Gateway client (stdio + SSE fallback)
    session.py            #   Session persistence (save/load/autosave)
    approval.py           #   HITL approval gate
    audit.py              #   Append-only JSONL audit log
    stigmergy.py          #   Stigmergy knowledge graph
    web/                  #   Frontend SPA
      index.html          #     Dashboard HTML
      app.js              #     Application logic
      style.css           #     Styles
  tests/                  # Test suite (pytest + pytest-asyncio)
  config/                 # Runtime configuration
    formicos.yaml         #   Main configuration file
    caste_recipes.yaml    #   Agent model/tool/escalation definitions
    prompts/              #   Caste system prompts (manager.md, coder.md, etc.)
  scripts/                # Utility scripts
    mcp_gateway.py        #   MCP gateway aggregation (sidecar mode)
    compile_context.py    #   V0.8.0 Cloud Model Handover script
  docs/                   # Design documents and specifications
    v0.8.0/               #   v0.8.0 Master Spec & AI Handover Protocols
  workspace/              # Colony workspace (agent file artifacts)
  Dockerfile              # FormicOS container image
  Dockerfile.mcp-gateway  # MCP gateway sidecar image
  docker-compose.yml      # Full stack: formicos + llm + embedding + qdrant + mcp-gateway
  pyproject.toml          # Package metadata and build config
  requirements.txt        # Python dependencies
```

## Quick Start

### Prerequisites

- Docker Desktop 4.48+ with GPU support enabled
- NVIDIA GPU with 24 GB+ VRAM (32 GB recommended for full context)
- GGUF model files in `./.models/` (or set `LLM_MODEL_DIR`):
  - `Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf` (LLM, ~18 GB)
  - `bge-m3-q8_0.gguf` (embeddings, ~635 MB)

### 1. Download Models

```bash
mkdir -p .models && cd .models
# LLM (Qwen3-30B-A3B, Q4_K_M quantization)
huggingface-cli download Qwen/Qwen3-30B-A3B-Instruct-2507-GGUF \
  Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf --local-dir .
# Embeddings (BGE-M3, Q8_0 quantization)
huggingface-cli download second-state/BGE-M3-GGUF \
  bge-m3-q8_0.gguf --local-dir .
```

### 2. Start the Stack

```bash
docker compose up -d
```

This starts five services:

| Service | Port | Description |
|---------|------|-------------|
| formicos | 8080 | Web dashboard and API |
| llm | 8008 | llama.cpp LLM inference (GPU, 8K context) |
| embedding | 8009 | llama.cpp BGE-M3 embeddings (CPU) |
| qdrant | 6333 | Vector database |
| mcp-gateway | -- | MCP tool gateway (internal) |

Wait for all services to become healthy:

```bash
docker compose ps   # all should show "healthy" or "running"
```

The LLM server takes 1-2 minutes to load the model. You can monitor progress:

```bash
docker logs -f formicos-llm
```

### 3. Open the Dashboard

Navigate to **http://localhost:8080** in your browser.

### 4. Create Your First Colony

1. Click **+ New Colony** in the Supercolony tab
2. Enter a task description (e.g., "Build a snake game in Python")
3. Choose a team preset (**Full-Stack** recommended) or configure agents manually
4. Set max rounds (3-5 for simple tasks, 8-10 for complex ones)
5. Click **Create** then **Start**

The **Stream** panel shows real-time agent output. The **Topology** panel shows the routing DAG (use `<` / `>` to browse round history). Files created by agents appear in the **Workspace** tab.

### Run Without Docker (Development)

```bash
pip install -r requirements.txt
export FORMICOS_CONFIG=config/formicos.yaml
uvicorn src.server:app_factory --host 0.0.0.0 --port 8000 --factory
```

When running locally, update `config/formicos.yaml` to point inference and embedding endpoints to your local llama.cpp instances (default: `http://localhost:8008/v1` and `http://localhost:8009/v1`).

## Configuration Reference

All configuration lives in `config/formicos.yaml`. Every section maps to a field in the `FormicOSConfig` Pydantic model.

### Key Sections

**identity** -- Project name and version displayed in the dashboard.

**hardware** -- GPU type, VRAM capacity, alert threshold. Triggers dashboard warnings when VRAM usage nears the limit.

**inference** -- Primary LLM backend. `endpoint` points to the llama.cpp server. `model_alias` maps to the OpenAI-compatible API. `max_tokens_per_agent` caps per-agent output.

**embedding** -- Embedding backend for RAG. `routing_model` specifies the lightweight sentence-transformer used for DyTopo routing (loaded in-process on CPU).

**routing** -- DyTopo parameters. `tau` is the cosine-similarity threshold for edge creation. `k_in` caps incoming edges per agent. `broadcast_fallback` sends to all agents when no edge exceeds tau.

**convergence** -- Colony termination. `similarity_threshold` detects when outputs stop changing. `path_diversity_warning_after` triggers tunnel vision alerts.

**caste_recipes** -- Handled by `config/caste_recipes.yaml`. Decouples agent tools, models, escalation rules, and safety bounds (Durable execution overrides).

**model_registry** -- Maps logical model IDs to backend connections (llama_cpp, openai_compatible, ollama, anthropic_api). Used by subcaste resolution.

**subcaste_map** -- Maps tiers (heavy/balanced/light) to model registry entries. Supports optional `refine_with` for draft-refine two-stage inference.

**mcp_gateway** -- MCP tool integration. Transport strategy: stdio first (Docker MCP Toolkit), SSE fallback (sidecar container). Server management via Docker Desktop MCP Toolkit.

**qdrant** -- Vector database connection. Collections are auto-created. Per-colony namespaces use `colony_{id}_docs`.

**skill_bank** -- Persistent skill library. `dedup_threshold` prevents near-duplicates. `prune_zero_hit_after` removes unused skills.

**persistence** -- Session autosave configuration. Sessions stored as JSON.

**approval_required** -- Actions requiring HITL approval (main branch merge, cloud escalation, file deletion outside workspace).

## API Endpoints

The API server runs on port 8000 inside the container (mapped to 8080 on host by default).

### System

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/system` | System status (GPU, VRAM, model info) |
| GET | `/api/models` | Model registry listing |
| GET | `/api/prompts` | List available caste prompts |
| GET | `/api/prompt/{caste}` | Read a caste prompt |
| PUT | `/api/prompt/{caste}` | Update a caste prompt |

### Colony Lifecycle

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/colony` | Current colony state |
| POST | `/api/run` | Start a new colony run (task, agents, max_rounds) |
| POST | `/api/resume` | Resume a saved session |
| POST | `/api/colony/extend` | Add rounds to a running colony |
| GET | `/api/supercolony` | All managed colonies overview |
| POST | `/api/colony/{id}/create` | Create a new colony |
| POST | `/api/colony/{id}/start` | Start a created colony |
| POST | `/api/colony/{id}/pause` | Pause a running colony |
| POST | `/api/colony/{id}/resume` | Resume a paused colony |
| DELETE | `/api/colony/{id}/destroy` | Destroy a colony |

### Colony Data

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/topology` | Current DyTopo graph |
| GET | `/api/topology/history` | Topology snapshots from all rounds |
| GET | `/api/decisions` | Decision log |
| GET | `/api/episodes` | Episodic memory |
| GET | `/api/tkg` | Temporal knowledge graph |
| GET | `/api/epochs` | Epoch summaries |
| POST | `/api/suggest-team` | AI-generated team recommendation for a task |
| GET | `/api/castes` | Available agent castes |

### Workspace

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/workspace/{colony_id}/files` | List files in a colony's workspace |
| GET | `/api/workspace/{colony_id}/file?path=...` | Read a single file |
| POST | `/api/workspace/{colony_id}/upload` | Upload a file to workspace |

### Sessions

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/sessions` | List saved sessions |
| DELETE | `/api/sessions/{id}` | Delete a session |

### Skill Bank

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/skill-bank` | List all skills |
| GET | `/api/skill-bank/skill/{id}` | Get a specific skill |
| POST | `/api/skill-bank/skill` | Create a skill |
| PUT | `/api/skill-bank/skill/{id}` | Update a skill |
| DELETE | `/api/skill-bank/skill/{id}` | Delete a skill |

### Tools and Intervention

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/mcp/reconnect` | Reconnect MCP gateway |
| POST | `/api/v1/approvals/override` | Approve/deny a pending action (Headless Override) |
| POST | `/api/v1/colonies/{id}/intervene` | Inject operator guidance into a running colony |

### Webhooks

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/webhooks/logs` | View outbound webhook delivery logs |

### WebSocket

| Path | Description |
|------|-------------|
| `/ws/stream` | Real-time streaming (agent tokens, round updates, colony events) |

### V1 API (prefix: /api/v1)

Structured contract-based API with `ApiErrorV1` error envelopes, `EventEnvelopeV1` WS events, and `ColonyStateV1`/`ColonyResultV1` response models. See [docs/0.7.2/api-reference.md](docs/0.7.2/api-reference.md) for the full V1 endpoint listing.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/system` | System status with schema_version |
| GET | `/api/v1/system/health` | Health checks (llm, mcp, embedding) |
| GET | `/api/v1/system/metrics` | SLO percentiles (p50, p95, p99) |
| GET | `/api/v1/colonies` | List all colonies |
| POST | `/api/v1/colonies` | Create colony (auto-generates ID) |
| GET | `/api/v1/colonies/{id}` | Colony state (ColonyStateV1) |
| POST | `/api/v1/colonies/{id}/start` | Start colony |
| POST | `/api/v1/colonies/{id}/pause` | Pause colony |
| POST | `/api/v1/colonies/{id}/resume` | Resume colony |
| POST | `/api/v1/colonies/{id}/extend` | Add rounds |
| POST | `/api/v1/colonies/{id}/reuse` | Re-run with new task |
| GET | `/api/v1/colonies/{id}/results` | Colony results (ColonyResultV1) |
| GET | `/api/v1/colonies/{id}/workspace/archive` | Download workspace ZIP |

## v0.8.0 Cloud Handover Architecture

FormicOS has reached its architectural apex. The v0.8.0 release incorporates:
- **Durable Execution**: Auto-resume colonies from `.json` checkpoints on Docker crashes.
- **Voting Parallelism**: Mitigate LLM hallucinations by spawning 3 parallel `Coder` replicas that dynamically vote via a `Reviewer` node.
- **YAML Engine**: `caste_recipes.yaml` abstracts models, logic, bounds, and escalation fallbacks natively.
- **Headless Telemetry**: Centralized `/api/v1/admin/diagnostics` for extracting logic diffs and Stack Traces.

See `docs/v0.8.0/` for the complete Agentic Codebase Master Spec.

## Development

### Running Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

Tests use pytest-asyncio with `asyncio_mode = "auto"`. No running services required -- tests mock external dependencies.

### Local Development Without Docker

1. Start llama.cpp for LLM inference:
   ```bash
   llama-server --model Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf \
     --alias gpt-4 --ctx-size 8192 --n-gpu-layers 99 \
     --flash-attn on --jinja --port 8008
   ```

2. Start llama.cpp for embeddings:
   ```bash
   llama-server --model bge-m3-q8_0.gguf \
     --embeddings --ctx-size 8192 --n-gpu-layers 99 --port 8009
   ```

3. Start Qdrant:
   ```bash
   docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant:latest
   ```

4. Update `config/formicos.yaml` endpoints to `http://localhost:8008/v1` and `http://localhost:8009/v1`, and Qdrant host to `localhost`.

5. Start FormicOS:
   ```bash
   uvicorn src.server:app_factory --host 0.0.0.0 --port 8000 --factory --reload
   ```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FORMICOS_CONFIG` | `config/formicos.yaml` | Path to configuration file |
| `LLM_IMAGE` | `ghcr.io/ggml-org/llama.cpp:server-cuda` | llama.cpp Docker image |
| `LLM_MODEL_DIR` | `./models` | Host path to GGUF model files |
| `LLM_PORT` | `8008` | Host port for LLM server |
| `LLM_CONTEXT_SIZE` | `8192` | LLM context window size |
| `EMBEDDING_PORT` | `8009` | Host port for embedding server |
| `QDRANT_PORT` | `6333` | Host port for Qdrant REST |
| `QDRANT_GRPC_PORT` | `6334` | Host port for Qdrant gRPC |

## License

FORMICOS LICENSE AGREEMENT
==========================

This software is licensed under the GNU Affero General Public License version 3 (AGPLv3), with the following Additional Permissions granted under Section 7 of the AGPLv3.

SPECIAL EXCEPTION FOR SMALL BUSINESSES AND EDUCATIONAL INSTITUTIONS:
As a special exception to the AGPLv3, the copyright holders of FormicOS grant you permission to modify the software and interact with it remotely through a computer network (e.g., as a SaaS) WITHOUT the obligation to distribute the corresponding source code under Section 13, PROVIDED THAT you meet at least one of the following criteria:

1. Educational / Non-Profit: You are using the software exclusively for academic research, teaching at a recognized educational institution, or operating as a registered non-profit organization (e.g., 501(c)(3)).
2. Small Business Commercial Use: Your organization (including any corporate affiliates) has a Gross Annual Revenue of less than $1,000,000 USD (or local equivalent) in the trailing 12 months.

If your organization exceeds the $1,000,000 USD revenue threshold, this exception automatically terminates. At that point, you must either fully comply with the source-sharing requirements of Section 13 of the AGPLv3, or obtain a separate Commercial License from the copyright holder.

COMMERCIAL LICENSING:
If you do not meet the criteria for the exception above and wish to use FormicOS in a closed-source commercial environment without complying with the AGPLv3 network source-sharing requirements, please contact the repository owner for a Commercial License.

