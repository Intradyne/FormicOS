# Deployment Guide

How to deploy FormicOS from clone to running stack.

---

## Quick Start (Cloud — recommended)

No GPU required. Three containers: FormicOS + Qdrant + Docker proxy.

```bash
git clone https://github.com/Intradyne/FormicOS.git
cd FormicOS
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY=sk-ant-...
docker compose build && docker compose up -d
```

Verify:
```bash
docker compose ps          # 3 containers should show "healthy"
curl http://localhost:8080/health
```

Navigate to **http://localhost:8080**. Wait for the startup panel to clear
and the Queen welcome message to appear.

### Prerequisites (cloud path)

| Requirement | Minimum |
|-------------|---------|
| **Docker** | Docker Engine 24+ with Compose V2, or Docker Desktop 4.30+ |
| **API key** | At least one of: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` |

Embeddings use sentence-transformers MiniLM (~80 MB auto-download, 384-dim).
No GPU needed.

---

## Advanced: Local GPU Inference

Five containers: adds llama.cpp LLM + Qwen3-Embedding sidecar (GPU).

**Production local model:** Qwen3.5-35B-A3B (MoE, 3.5B active params/token).
Benchmarked at 0.503 average quality across 5/5 real-repo tasks with zero
hangs. This is the default and recommended local profile.

### Prerequisites (local GPU)

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| **GPU** | 24 GB VRAM (RTX 3090 / 4090 / A5000) | 32 GB VRAM (RTX 5090) |
| **CPU** | 4 cores | 8+ cores |
| **RAM** | 32 GB | 64 GB |
| **Disk** | ~20 GB (models + Docker images) | 40 GB+ |
| **NVIDIA** | NVIDIA Container Toolkit installed | Driver 555+ for Blackwell GPUs |

### One-command setup

```bash
bash scripts/setup-local-gpu.sh
docker compose up -d
```

This downloads models, builds the Blackwell llama.cpp image, and enables the
`local-gpu` Docker Compose profile in your `.env`.

### Manual setup

```bash
cp .env.example .env
```

Uncomment the "Local GPU override" block in `.env`, then:

```bash
# Download models
mkdir -p .models && cd .models
huggingface-cli download Qwen/Qwen3.5-35B-A3B-GGUF \
  Qwen3.5-35B-A3B-Q4_K_M.gguf --local-dir .
huggingface-cli download Qwen/Qwen3-Embedding-0.6B-GGUF \
  Qwen3-Embedding-0.6B-Q8_0.gguf --local-dir .
cd ..

# Build Blackwell-native llama.cpp image
bash scripts/build_llm_image.sh

# Start (5 containers)
docker compose up -d
```

For non-Blackwell GPUs, set `LLM_IMAGE=ghcr.io/ggml-org/llama.cpp:server-cuda`
in `.env`. The generic image uses PTX JIT and falls back to ~16k effective
context.

### Embedding dimension lock-in

Cloud-first uses 384-dim MiniLM embeddings. Local GPU uses 1024-dim Qwen3
via the sidecar. **You cannot switch between cloud and local embedding on
an existing Qdrant collection without re-indexing.** Choose once at setup
time. To re-index: stop FormicOS, delete the `qdrant-data` volume, restart.

---

## Services

| Container | Port | Purpose | Profile |
|-----------|------|---------|---------|
| `formicos-colony` | 8080 | FormicOS application (backend + frontend) | *(always)* |
| `formicos-qdrant` | 6333, 6334 | Qdrant vector store | *(always)* |
| `formicos-docker-proxy` | -- (internal 2375) | Docker socket proxy for sandbox spawning | *(always)* |
| `formicos-llm` | 8008 → 8080 | llama.cpp LLM inference (GPU) | `local-gpu` |
| `formicos-embed` | 8200 | Qwen3-Embedding sidecar (GPU) | `local-gpu` |

Profile-gated services only start when `COMPOSE_PROFILES=local-gpu` is set
in `.env`. Adapters handle missing endpoints gracefully at first LLM call.

---

## Configuration

### Environment variables (.env)

Copy `.env.example` to `.env`. See `.env.example` for the full list with
inline documentation. Key variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | *(none)* | Anthropic API key for cloud models (Claude) |
| `COMPOSE_PROFILES` | *(none)* | Set to `local-gpu` to enable LLM + embedding containers |
| `QUEEN_MODEL` | `anthropic/claude-sonnet-4-6` | Queen model (env var overrides formicos.yaml) |
| `CODER_MODEL` | `anthropic/claude-sonnet-4-6` | Coder model |
| `REVIEWER_MODEL` | `anthropic/claude-haiku-4-5` | Reviewer model |
| `EMBED_MODEL` | `all-MiniLM-L6-v2` | Embedding model (sentence-transformers or sidecar) |
| `EMBED_URL` | *(empty)* | Embedding sidecar URL (set for local GPU) |
| `EMBED_DIMENSIONS` | `384` | Embedding vector dimensions (384 for MiniLM, 1024 for Qwen3) |
| `LLM_HOST` | *(empty)* | Local LLM endpoint (set for local GPU) |
| `FORMICOS_DATA_DIR` | `./data` (dev) / `/data` (Docker) | Persistent data directory |
| `SANDBOX_ENABLED` | `true` | Enable/disable Docker sandbox for code execution |

### Application config

| File | Purpose |
|------|---------|
| `config/formicos.yaml` | Model routing, tier definitions, context windows |
| `config/caste_recipes.yaml` | Caste prompts, tool lists, model assignments |
| `config/templates/` | Colony templates (7 built-in) |

### Multi-GPU pinning (local GPU only)

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

## HTTPS (Production / Exposed Deployments)

For local development, HTTPS is not needed. Claude Desktop and Claude Code
both connect over HTTP via localhost (Claude Desktop uses `mcp-remote` to
bridge stdio to HTTP -- see `docs/DEVELOPER_BRIDGE.md`).

HTTPS is only needed when exposing FormicOS to external clients over the
network. The repo includes an optional Caddy reverse proxy sidecar that
terminates TLS on port 8443 using locally-trusted certificates generated
by [mkcert](https://github.com/FiloSottile/mkcert).

### Setup

```bash
# Install mkcert
# Windows: winget install FiloSottile.mkcert
# macOS:   brew install mkcert
# Linux:   see https://github.com/FiloSottile/mkcert#installation

# Install the local CA into system trust stores (one-time)
mkcert -install

# Generate certs for localhost
mkdir -p certs
mkcert -cert-file certs/localhost.pem -key-file certs/localhost-key.pem \
  localhost 127.0.0.1 ::1
```

The `certs/` directory is gitignored -- certificates are generated per-machine.

### Enable HTTPS

The caddy service is commented out in `docker-compose.yml` by default.
Uncomment it, or use the override file:

```bash
docker compose -f docker-compose.yml -f docker-compose.https.yml up -d
```

Caddy listens on `:8443` and reverse-proxies all traffic to `formicos:8080`.
The `Caddyfile` at the repo root configures TLS:

```
:8443 {
    tls /certs/localhost.pem /certs/localhost-key.pem
    reverse_proxy formicos:8080
}
```

### Verify

```bash
curl https://localhost:8443/health
```

If this fails with a certificate error, run `mkcert -install` to add the
local CA to your system trust store.

---

## VRAM Budget

### RTX 5090 (32 GB) — recommended local stack

| Component | VRAM | Notes |
|-----------|------|-------|
| Qwen3.5-35B-A3B Q4_K_M weights | ~19.5 GB | MoE, 3.5B active params/token |
| KV cache (65k ctx × 5 slots) | ~5.5 GB | `--fit on` auto-sizes to available VRAM |
| Compute buffers | ~2.4 GB | |
| Qwen3-Embedding-0.6B Q8_0 | ~0.7 GB | Set `EMBED_GPU_LAYERS=0` for CPU fallback |
| **Total GPU** | **~28.1 GB** | ~3.9 GB headroom |

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

## Experimental: Devstral Local Profile

Devstral Small 2 can be used as an alternative local model. It has strong
instruction following but is significantly slower than Qwen3.5 MoE on
consumer hardware due to its dense architecture.

**Status:** Experiment/reference profile. Not recommended as the default
production path on current consumer GPUs.

To use Devstral:

1. Copy `.env.devstral` to `.env` (or merge its model settings)
2. Download the Devstral GGUF into `.models/`
3. Set `LLM_FLASH_ATTN=off`, `LLM_CACHE_TYPE_K=f16`, `LLM_CACHE_TYPE_V=f16`
4. Use conservative slot/context settings (see `.env.devstral`)

Devstral is useful for testing instruction-following quality or as a
comparison baseline. For iterative colony work, Qwen3.5-35B remains
materially faster and is the recommended production profile.

---

## Runtime Diagnostics (Wave 84)

### Event-loop slow-callback detection

Set `FORMICOS_ASYNCIO_DEBUG=1` in `.env` to enable asyncio slow-callback
warnings. This logs any callback that blocks the event loop for >100ms,
with enough context to identify the blocking function.

Use this when diagnosing app health-check failures or WebSocket stream
deaths during sustained colony work. Disable in normal operation.

### Idle-gated extraction

Colony completion hooks (memory extraction, transcript harvest) now drain
through a deferred idle queue instead of competing immediately with live
colony work. This prevents LLM capacity starvation during bursty
multi-colony completions. No configuration needed — always active.

### Connection pool limits

The local OpenAI-compatible adapter uses explicit `httpx` connection-pool
limits (`max_connections=10`, `max_keepalive_connections=5`) on top of
earlier transport hardening (`Connection: close`, transport reset/retry).

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
