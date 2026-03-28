# Deployment Guide

How to deploy FormicOS from clone to running stack. This guide covers the
supported local-first Docker Compose path.

---

## Prerequisites

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| **GPU** | 24 GB VRAM (RTX 3090 / 4090 / A5000) | 32 GB VRAM (RTX 5090) |
| **CPU** | 4 cores | 8+ cores |
| **RAM** | 32 GB | 64 GB |
| **Disk** | ~20 GB (models + Docker images) | 40 GB+ |
| **Docker** | Docker Engine 24+ with Compose V2 | Docker Desktop 4.30+ or native Linux Docker |
| **NVIDIA** | NVIDIA Container Toolkit installed | Driver 555+ for Blackwell GPUs |

**Cloud-only (no GPU):** Set `ANTHROPIC_API_KEY` and/or `GEMINI_API_KEY` in
`.env`. All inference routes to cloud providers. No local GPU needed.

---

## Quick Start

```bash
git clone https://github.com/Intradyne/FormicOS.git
cd FormicOS
cp .env.example .env
```

### 1. Download models (local inference)

```bash
mkdir -p .models && cd .models

# LLM — Qwen3-30B-A3B (MoE, 3.3B active params/token)
huggingface-cli download Qwen/Qwen3-30B-A3B-Instruct-2507-GGUF \
  Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf --local-dir .

# Embedding — Qwen3-Embedding-0.6B
huggingface-cli download Qwen/Qwen3-Embedding-0.6B-GGUF \
  Qwen3-Embedding-0.6B-Q8_0.gguf --local-dir .

cd ..
```

Install `huggingface-cli` if needed: `pip install huggingface_hub[cli]`

### 2. Build the local llama.cpp image (Blackwell GPUs)

```bash
bash scripts/build_llm_image.sh
```

This builds a Blackwell-native image (`sm_120`, CUDA 12.8) for full 80k
context on RTX 5090. For non-Blackwell GPUs, set in `.env`:

```bash
LLM_IMAGE=ghcr.io/ggml-org/llama.cpp:server-cuda
```

The generic image uses PTX JIT compilation and falls back to ~16k effective
context.

### 3. Start the stack

```bash
docker compose up -d
```

### 4. Verify health

```bash
docker compose ps          # All 5 containers should show "healthy"
curl http://localhost:8080/health
curl http://localhost:8008/health
curl http://localhost:8200/health
curl http://localhost:6333/collections
```

### 5. Open the UI

Navigate to **http://localhost:8080**. Wait for the startup panel to clear
and the Queen welcome message to appear.

---

## Services

| Container | Port | Purpose |
|-----------|------|---------|
| `formicos-colony` | 8080 | FormicOS application (backend + frontend) |
| `formicos-llm` | 8008 → 8080 | llama.cpp LLM inference (GPU) |
| `formicos-embed` | 8200 | Qwen3-Embedding sidecar (GPU) |
| `formicos-qdrant` | 6333, 6334 | Qdrant vector store |
| `formicos-docker-proxy` | -- (internal 2375) | Docker socket proxy for sandbox spawning |

All services have health checks. FormicOS waits for the LLM, embedding
sidecar, and Qdrant to be healthy before starting.

---

## Configuration

### Environment variables (.env)

Copy `.env.example` to `.env`. All variables are optional — defaults work
for the standard RTX 5090 local stack.

| Variable | Default | Purpose |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | *(none)* | Anthropic API key for cloud models (Claude) |
| `GEMINI_API_KEY` | *(none)* | Google Gemini API key for cloud models |
| `LLM_IMAGE` | `local/llama.cpp:server-cuda-blackwell` | Docker image for LLM inference |
| `LLM_MODEL_FILE` | `Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf` | GGUF model filename |
| `LLM_CONTEXT_SIZE` | `80000` | Context window size for local LLM |
| `LLM_SLOTS` | `2` | Concurrent inference slots |
| `LLM_SLOT_PROMPT_SIMILARITY` | `0.5` | Prompt prefix reuse aggressiveness (0.0-1.0) |
| `LLM_CACHE_RAM` | `1024` | Prompt cache in system RAM (MB) |
| `LLM_PORT` | `8008` | Host-side port for LLM container |
| `LLM_MODEL_DIR` | `./.models` | Shared model directory (LLM + embedding) |
| `EMBED_GPU_LAYERS` | `99` | GPU layers for embedding model (0 = CPU-only) |
| `CUDA_DEVICE` | `0` | GPU index for LLM + embedding containers |
| `FORMICOS_DATA_DIR` | `./data` (dev) / `/data` (Docker) | Persistent data directory |
| `SANDBOX_ENABLED` | `true` | Enable/disable Docker sandbox for code execution |

### Application config

| File | Purpose |
|------|---------|
| `config/formicos.yaml` | Model routing, tier definitions, context windows |
| `config/caste_recipes.yaml` | Caste prompts, tool lists, model assignments |
| `config/templates/` | Colony templates (7 built-in) |

### Multi-GPU pinning

On multi-GPU systems, set `CUDA_DEVICE` in `.env`:

```bash
CUDA_DEVICE=0
```

This sets `CUDA_VISIBLE_DEVICES` inside the LLM and embedding containers.
**Docker Desktop on WSL2 ignores `device_ids`** in the deploy block and
passes through all GPUs. `CUDA_VISIBLE_DEVICES` is the effective control.

Without pinning, llama.cpp may split model layers across GPUs, causing
segfaults or severe throughput degradation.

---

## Persistence

### SQLite (event store)

FormicOS is event-sourced. A single SQLite file is the source of truth.
On startup, events replay into in-memory projections.

**Rules:**

- **Use named Docker volumes** (the default). The `formicos-data` volume
  in `docker-compose.yml` is a named volume.
- **Never bind-mount the SQLite database on macOS or Windows Docker Desktop.**
  Docker Desktop uses a Linux VM with filesystem translation (gRPC-FUSE or
  VirtioFS). SQLite WAL mode requires POSIX shared-memory semantics
  (`mmap` on `.db-shm`) that do not translate correctly through this layer.
  Bind-mounting will cause silent corruption or locking failures under load.
- **Keep `.db`, `.db-wal`, and `.db-shm` on the same filesystem.** WAL mode
  requires all three files to be co-located. Moving or copying just the
  `.db` file without its WAL companions will lose uncommitted data.
- **FormicOS is a single-writer system.** Do not run multiple FormicOS
  instances against the same SQLite file.

The SQLite adapter currently enables WAL journaling (`PRAGMA journal_mode=WAL`).

### Qdrant (vector store)

Qdrant stores knowledge embeddings for vector search. Data persists in the
`qdrant-data` named volume.

- Qdrant v1.16.2 is required for server-side BM25 hybrid search support.
- Back up by snapshotting the `qdrant-data` volume (see Backup below).
- Qdrant data is reconstructable from the event store — if you lose the
  Qdrant volume, restart FormicOS and embeddings will be re-indexed from
  events on replay.

### Backup

The event store is the primary backup target. Back up the `formicos-data`
volume:

```bash
docker run --rm -v formicos-data:/data -v $(pwd):/backup \
  alpine tar czf /backup/formicos-backup-$(date +%Y%m%d).tar.gz /data
```

To restore:

```bash
docker compose down
docker volume rm formicosa_formicos-data
docker volume create formicosa_formicos-data
docker run --rm -v formicosa_formicos-data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/formicos-backup-YYYYMMDD.tar.gz -C /
docker compose up -d
```

### Reset (destroy all data)

```bash
docker compose down -v
docker compose up -d
```

---

## Security Posture

### Sandboxed code execution

The `code_execute` agent tool runs code inside disposable Docker containers
with:

- `--network=none` — no network access
- `--memory=256m` — memory limit
- `--read-only` — read-only root filesystem
- `--tmpfs /tmp:size=10m` — small writable temp space

These provide basic isolation for code execution tasks.

### Docker socket access

**The FormicOS container routes Docker API calls through a socket proxy**
(`tecnativa/docker-socket-proxy`) configured in `docker-compose.yml`.
The proxy restricts API access to container operations only (CONTAINERS=1,
POST=1; images, networks, volumes, and all other operations are blocked).

The raw Docker socket is mounted read-only into the proxy container, not
into FormicOS itself. This limits the blast radius of a compromise —
FormicOS can create/start/stop containers but cannot pull images, create
networks, or access other Docker API endpoints.

Mitigations:

- Set `SANDBOX_ENABLED=false` to disable sandbox spawning entirely.
- The socket proxy is the default path — no raw socket mount is needed.
- Set `DOCKER_HOST=tcp://docker-proxy:2375` (already configured in
  `docker-compose.yml`).

For stronger isolation, consider running FormicOS inside a Sysbox or
gVisor-based runtime where nested containers do not require host socket
access. This is not yet a shipped configuration.

### Workspace execution

The workspace executor (for repo-backed commands like `git`, test runners,
and build tools) runs commands inside disposable Docker containers when
`WORKSPACE_ISOLATION=true` (the default). The workspace directory is
bind-mounted into the container, and commands run with `--cap-drop=ALL`,
`--security-opt=no-new-privileges`, `--pids-limit`, and a custom seccomp
profile.

Phase-aware networking: dependency-install commands (`pip install`,
`npm install`, etc.) get network access; test and build commands run with
`--network=none`.

When Docker is unavailable, the executor falls back to host-shell
`asyncio.create_subprocess_shell`. Set `WORKSPACE_ISOLATION=false` to
force this fallback. The host-shell path does not have container
isolation.

### What is enforced vs. what is planned

| Control | Status |
|---------|--------|
| Sandbox containers with `--network=none`, `--memory`, `--read-only` | **Enforced** |
| Sandbox `--cap-drop=ALL`, `--no-new-privileges`, `--pids-limit=256` | **Enforced** |
| Custom seccomp profile for sandbox (`config/seccomp-sandbox.json`) | **Enforced** |
| Knowledge security scanning (5-axis) | **Enforced** |
| Event-sourced audit trail | **Enforced** |
| Layer isolation (CI-enforced import rules) | **Enforced** |
| Bayesian federation trust scoring | **Enforced** |
| Docker socket proxy (container-ops only) | **Enforced** |
| Containerized workspace executor (`WORKSPACE_ISOLATION=true`) | **Enforced** (fallback to host-shell when Docker unavailable) |
| Git clone security defaults (hooks disabled, no submodules, symlinks off) | **Enforced** via `safe_git_clone()` |

---

## VRAM Budget

### RTX 5090 (32 GB) — recommended local stack

| Component | VRAM | Notes |
|-----------|------|-------|
| Qwen3-30B-A3B Q4_K_M weights | ~17.3 GB | MoE, 3.3B active params/token |
| KV cache (80k ctx × 2 slots × q8_0) | ~5.2 GB | `--fit on` auto-sizes to available VRAM |
| Compute buffers | ~2.4 GB | |
| Qwen3-Embedding-0.6B Q8_0 | ~0.7 GB | Set `EMBED_GPU_LAYERS=0` for CPU fallback |
| Prompt cache | ~1 GB | In system RAM, not VRAM |
| **Total GPU** | **~25.6 GB** | ~6.4 GB headroom |

### RTX 4090/3090 (24 GB)

The same stack fits with reduced context. Set `LLM_CONTEXT_SIZE=32000` in
`.env`. With `--fit on`, llama.cpp auto-sizes the KV cache to available VRAM.

To free ~700 MB VRAM, move embedding to CPU:

```bash
EMBED_GPU_LAYERS=0
```

### Cloud-only (no GPU)

Add API keys to `.env` and skip model downloads and image builds:

```bash
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AI...
```

The tier system routes all castes to cloud providers. Comment out the `llm`
and `formicos-embed` services in `docker-compose.yml` if desired (FormicOS
will still need Qdrant for vector search, or will fall back to the
sentence-transformers embedding path).

---

## Updating

```bash
git pull
docker compose build formicos
docker compose up -d
```

**Important:** After modifying frontend source or pulling updates, you must
rebuild the Docker image. The frontend is built inside the Docker multi-stage
build — a local `npm run build` does not update the served bundle inside the
container.

---

## Monitoring

### Logs

```bash
docker logs formicos-colony          # Application (structlog JSON)
docker logs formicos-llm             # LLM inference
docker logs formicos-embed           # Embedding sidecar
docker logs formicos-qdrant          # Vector store
```

### Health endpoints

| Endpoint | What it checks |
|----------|---------------|
| `GET /health` (port 8080) | FormicOS app, replay status, workspace/thread/colony counts |
| `GET /health` (port 8008) | llama.cpp LLM readiness |
| `GET /health` (port 8200) | Embedding sidecar readiness |
| `GET /healthz` (port 6333) | Qdrant readiness |

### Observability

FormicOS ships two telemetry adapters:

- **JSONL sink** (`adapters/telemetry_jsonl.py`) — lightweight, always
  available. Events appended to a JSONL file in the data directory.
- **OpenTelemetry adapter** (`adapters/telemetry_otel.py`) — activates
  when `opentelemetry-api` is importable. Instruments LLM calls, colony
  lifecycle, and round execution with spans and metrics. Configure via
  standard OTel environment variables (`OTEL_EXPORTER_OTLP_ENDPOINT`,
  etc.).

The OTel adapter is additive — the JSONL sink remains usable as a
debug-level fallback even when OTel is configured. Live integration
into the runtime call sites is available but not yet wired into all
execution paths.

---

## Troubleshooting

See [RUNBOOK.md](RUNBOOK.md) for detailed troubleshooting guidance covering:

- LLM container startup failures
- Embedding sidecar crashes and multi-GPU issues
- Qdrant connection problems
- Colony execution issues
- Provider fallback behavior
- Frontend bundle staleness after rebuilds

---

## Alternative: Ollama

An Ollama variant is documented (commented out) in `docker-compose.yml`.
To use Ollama instead of llama.cpp:

1. Uncomment the `ollama` service block in `docker-compose.yml`
2. Comment out the `llm` service
3. Set `LLM_HOST=http://ollama:11434` in the FormicOS environment
4. Update model defaults in `config/formicos.yaml` to use `ollama/*` prefixes
5. Pull the model: `docker exec formicos-ollama ollama pull qwen3:30b-a3b`

Ollama is simpler to set up but has higher VRAM overhead and less control
over inference parameters.

---

## Development (without Docker)

For development without Docker:

```bash
# Backend
uv sync --dev
python -m formicos                    # Starts on :8080

# Frontend (separate terminal, for HMR)
cd frontend && npm ci && npm run dev

# Full CI
uv run ruff check src/ && uv run pyright src/ && python scripts/lint_imports.py && python -m pytest -q
```

You need either a running local LLM (llama.cpp, Ollama) or cloud API keys
in `.env`. Qdrant must be running for vector search (`docker compose up qdrant`).
