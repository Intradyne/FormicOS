# FormicOS Runbook

Operational guide for deploying and running FormicOS.

---

## Hardware Requirements

### GPU (recommended)

| Component | VRAM | Notes |
|-----------|------|-------|
| Qwen3-30B-A3B Q4_K_M (LLM) | ~21.1 GB | MoE, 3.3B active params/token |
| Qwen3-Embedding-0.6B Q8_0 | ~0.7 GB | 1024-dim dense embeddings |
| **Total** | **~21.8 GB** | Fits RTX 3090/4090/5090 with headroom |

- **Minimum GPU:** 24 GB VRAM (RTX 3090, RTX 4090, A5000)
- **Recommended GPU:** 32 GB VRAM (RTX 5090) for comfortable headroom
- **CPU:** 8+ cores recommended (llama.cpp uses `--threads 8 --threads-batch 16`)
- **RAM:** 32 GB minimum, 64 GB recommended
- **Disk:** ~20 GB for model files + Docker images

### Cloud-only (no GPU)

Set `ANTHROPIC_API_KEY` and/or `GEMINI_API_KEY` in `.env`. The tier system routes
all castes to cloud providers. No local GPU needed. Requires internet access.

---

## Model Downloads

Download models before first `docker compose up`:

```bash
mkdir -p .models && cd .models

# LLM (required for local inference)
huggingface-cli download Qwen/Qwen3-30B-A3B-Instruct-2507-GGUF \
  Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf --local-dir .

# Embedding sidecar (required for vector search)
huggingface-cli download Qwen/Qwen3-Embedding-0.6B-GGUF \
  Qwen3-Embedding-0.6B-Q8_0.gguf --local-dir .
```

Install `huggingface-cli` if needed: `pip install huggingface_hub[cli]`

---

## Docker Setup

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env to add API keys (optional) or override defaults
```

### Multi-GPU pinning

On multi-GPU systems, pin inference to a specific GPU by setting `CUDA_DEVICE`
in `.env`:

```bash
CUDA_DEVICE=0   # GPU index for LLM + embedding (default: 0)
```

This sets `CUDA_VISIBLE_DEVICES` inside the `llm` and `formicos-embed`
containers. The compose file also sets `device_ids` in the deploy block, but
**Docker Desktop on WSL2 ignores `device_ids`** and passes through all GPUs.
`CUDA_VISIBLE_DEVICES` is the effective control on WSL2.

Without pinning, llama.cpp may split model layers across GPUs, causing
segfaults on the secondary GPU or severe throughput degradation (e.g., 1 tok/s
instead of 240 tok/s).

### 2. Start all services

```bash
docker compose up -d
```

This starts five containers:

| Container | Port | Purpose |
|-----------|------|---------|
| `formicos-llm` | 8008 (host) → 8080 (container) | llama.cpp LLM inference |
| `formicos-embed` | 8200 | Qwen3-Embedding sidecar |
| `formicos-qdrant` | 6333, 6334 | Qdrant vector store (hybrid search) |
| `formicos-docker-proxy` | — (internal 2375) | Docker socket proxy for sandbox spawning |
| `formicos-colony` | 8080 | FormicOS application |

### 3. Verify health

```bash
docker compose ps          # all containers should show "healthy"
curl http://localhost:8080/health
```

The app health payload now includes replay/bootstrap counts:
```json
{
  "status": "ok",
  "last_seq": 0,
  "bootstrapped": true,
  "workspaces": 1,
  "threads": 1,
  "colonies": 0
}
```

### 4. Open the UI

Navigate to **http://localhost:8080**. On first boot you'll see the Queen tab
after a short startup panel. Once the workspace tree appears, the Queen posts
the welcome message and getting-started instructions.

---

## First Colony Walkthrough

1. Open **http://localhost:8080** and wait for the startup panel to clear
2. Read the welcome message from the Queen
3. Click the **+** button or type a task in the input area
4. Example: *Write a Python function that validates email addresses with tests*
5. The Queen suggests a team composition with castes and tiers
6. Adjust the team if desired, then click **Spawn**
7. Watch the colony run -- chat messages appear for each round
8. Colony completes with a cost summary, artifacts, and knowledge extraction

---

## API Keys

Cloud model keys are optional. Set them in `.env`:

```bash
ANTHROPIC_API_KEY=sk-ant-...    # Enables Anthropic models (Claude)
GEMINI_API_KEY=AI...            # Enables Google Gemini models
```

The tier system (`heavy` / `standard` / `light`) routes castes to appropriate
providers. Cloud keys enable fallback when local inference is slow or unavailable.

---

## Configuration Reference

All settings in `.env` (see `.env.example` for defaults). For a comprehensive
reference, see [DEPLOYMENT.md](DEPLOYMENT.md).

| Variable | Default | Purpose |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | *(none)* | Anthropic API key for cloud models |
| `GEMINI_API_KEY` | *(none)* | Gemini API key for cloud models |
| `LLM_IMAGE` | `local/llama.cpp:server-cuda-blackwell` | Docker image for LLM inference |
| `LLM_MODEL_FILE` | `Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf` | GGUF model filename |
| `LLM_CONTEXT_SIZE` | `80000` | Context window size for local LLM |
| `LLM_SLOTS` | `2` | Concurrent inference slots |
| `LLM_PORT` | `8008` | Host-side port for LLM container |
| `LLM_MODEL_DIR` | `./.models` | Shared model directory (LLM + embedding) |
| `EMBED_GPU_LAYERS` | `99` | GPU layers for embedding (0 = CPU-only) |
| `CUDA_DEVICE` | `0` | GPU index for LLM + embedding |
| `FORMICOS_DATA_DIR` | `./data` (dev) / `/data` (Docker) | Persistent data directory |
| `SANDBOX_ENABLED` | `true` | Enable/disable Docker sandbox |

---

## Colony Templates

FormicOS ships with 7 built-in templates in `config/templates/`:

| Template | Castes | Budget | Rounds | Use case |
|----------|--------|--------|--------|----------|
| `full-stack` | 2x coder, reviewer, archivist | $5 | 12 | General implementation |
| `code-review` | coder, reviewer | $3 | 10 | Code review and fixes |
| `debugging` | coder, reviewer | $4 | 10 | Bug diagnosis and repair |
| `research-heavy` | 2x researcher, archivist | $5 | 15 | Deep research tasks |
| `documentation` | researcher, archivist | $3 | 8 | Documentation generation |
| `rapid-prototype` | 1x coder (heavy tier) | $5 | 8 | Fast prototyping with cloud model |
| `minimal` | 1x coder | $2 | 6 | Quick single-agent tasks |

Templates with an **archivist** caste extract knowledge graph entities.

---

## Troubleshooting

### LLM container won't start

- **Model file missing:** Ensure the GGUF file exists in `.models/` directory
- **VRAM insufficient:** Check `nvidia-smi`. Try a smaller quant (Q3_K_M) or
  reduce `LLM_CONTEXT_SIZE`
- **NVIDIA driver:** Ensure NVIDIA Container Toolkit is installed:
  `nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker`

### Embedding sidecar unhealthy / segfaults

- Check logs: `docker logs formicos-embed`
- Verify model exists: `ls .models/Qwen3-Embedding-0.6B-Q8_0.gguf`
- The sidecar needs ~700 MB VRAM -- check GPU memory pressure
- **Multi-GPU crash:** If the sidecar splits layers across GPUs and segfaults,
  set `CUDA_DEVICE=0` in `.env` to pin it to a single GPU (see
  [Multi-GPU pinning](#multi-gpu-pinning) above)

### Qdrant won't connect

- Check status: `curl http://localhost:6333/healthz`
- Check logs: `docker logs formicos-qdrant`
- Qdrant v1.16.2 is required for server-side BM25 support

### "No embedding function" warnings

- The embedding sidecar must be healthy before FormicOS starts
- Check `docker compose ps` -- `formicos-embed` should show `healthy`
- FormicOS depends on the sidecar via `depends_on` with health condition

### Colony stuck / no progress

- Check LLM health: `curl http://localhost:8008/health`
- Check structured logs: `docker logs formicos-colony | grep error`
- Verify API keys if using cloud models: invalid keys cause silent failures
  (check logs for `fallback_triggered` or `provider_cooldown`)

### First boot shows no welcome message

- The welcome message only appears when `projections.last_seq == 0` (fresh database)
- If you've run before, the database already has events -- delete the volume to reset:
  `docker compose down -v && docker compose up -d`

---

## Persistence Rules

### SQLite (event store)

- **Use named Docker volumes** (the default `formicos-data` volume).
- **Never bind-mount the SQLite database on macOS or Windows Docker Desktop.**
  Docker Desktop's filesystem translation layer does not support the POSIX
  shared-memory semantics that SQLite WAL mode requires. Bind-mounting will
  cause silent corruption or locking failures under load.
- **Keep `.db`, `.db-wal`, and `.db-shm` on the same filesystem.** Moving
  just the `.db` without its WAL companions will lose uncommitted data.
- **FormicOS is a single-writer system.** Do not run multiple instances
  against the same SQLite file.

### Qdrant (vector store)

- Uses named Docker volume `qdrant-data`.
- Qdrant data is reconstructable from the event store — if you lose the
  volume, restart FormicOS and embeddings re-index from events on replay.
- Qdrant v1.16.2 is required for server-side BM25 hybrid search support.

---

## Maintenance

### Backup

The event store is a single SQLite file. Back up the `formicos-data` volume:

```bash
docker run --rm -v formicos-data:/data -v $(pwd):/backup \
  alpine tar czf /backup/formicos-backup-$(date +%Y%m%d).tar.gz /data
```

### Reset

To start fresh (destroys all data):

```bash
docker compose down -v
docker compose up -d
```

### Logs

```bash
docker logs formicos-colony          # Application logs (structlog JSON)
docker logs formicos-llm             # LLM inference logs
docker logs formicos-embed           # Embedding sidecar logs
docker logs formicos-qdrant          # Vector store logs
```

### Updating

```bash
git pull
docker compose build formicos
docker compose up -d
```

---

## Stream C Smoke Findings (2026-03-15)

### Frontend bundle staleness after rebuild

After modifying frontend source and running `cd frontend && npm run build`, the
Docker container still serves the old bundle until you rebuild the Docker image:

```bash
docker compose build formicos
docker compose up -d formicos
```

**Symptom:** The served JS filename (visible in `curl http://localhost:8080/`)
doesn't match the local `frontend/dist/assets/index-*.js` filename.

### Provider fallback chain

When a cloud provider returns 401 (invalid API key), the LLM router:

1. Tries the configured model (e.g., `anthropic/claude-sonnet-4.6`)
2. Falls back to secondary provider (e.g., `gemini/gemini-2.5-flash`)
3. Falls back to local (`llama-cpp/gpt-4`)
4. Activates cooldown (120s) for the failing provider

Check logs: `docker logs formicos-colony | grep fallback`

The colony continues running on fallback models. Quality may vary with local
models (e.g., convergence stalls, repeated outputs).

### CasteSlot event format migration

If upgrading from a pre-Wave 14 event store, the `ColonySpawned` event format
changed from `caste_names: list[str]` to `castes: list[CasteSlot]`. Old events
will fail Pydantic validation on replay. Reset the volume to fix:

```bash
docker compose down
docker volume rm formicosa_formicos-data
docker compose up -d
```

### WebSocket subscription required for event fan-out

The WS client must send a `subscribe` action before receiving events:

```json
{"action": "subscribe", "workspaceId": "default", "payload": {}}
```

Without subscribing, the client receives the initial state snapshot but no
subsequent events. The frontend handles this automatically on connect.

### Knowledge extraction is archivist-shaped

The strongest structured knowledge extraction path uses the archivist model and
archivist-oriented colonies. If your first few colonies do not include strong
archivist participation, the Knowledge view may stay sparse. Use templates like
`full-stack`, `research-heavy`, or `documentation` to exercise the full
knowledge pipeline.

---

## Colony Output Quality — Tuning Debt (Wave 24)

Low-quality colony output under the local stack is **model and sandbox tuning
debt**. It is not evidence that A2A, AG-UI, or any Wave 24 protocol/UX work
has regressed. The protocol surfaces (submit, poll, attach, result, transcript)
are working correctly; what varies is the quality of work the colony produces
given a particular model, task, and sandbox configuration.

### Likely causes

- **Local-model reasoning quality.** Smaller quantized models (Q4_K_M) may
  struggle with complex multi-step tasks, tool-call formatting, or code
  generation that a cloud model handles easily.
- **Sandbox/runtime quirks.** Code execution tasks may hit `__main__`
  packaging assumptions, missing imports in the sandbox, or filesystem
  restrictions that cause agent code to fail silently.
- **Task/model mismatch.** Code-heavy or multi-file tasks assigned to a
  single-agent `minimal` template on a local model will underperform compared
  to a `full-stack` template with cloud-tier models.

### What to try

1. **Inspect the transcript and `failure_context` first.** The transcript
   (`GET /api/v1/colonies/{id}/transcript` or `GET /a2a/tasks/{id}/result`)
   now includes structured `failure_context` for failed and killed colonies.
   Start here before assuming a protocol problem.
2. **Compare local vs cloud model assignment.** Run the same task with a
   cloud model (`rapid-prototype` template or set `ANTHROPIC_API_KEY`) and
   compare output quality. If the cloud run succeeds, the issue is model
   capability, not infrastructure.
3. **Reduce task ambiguity.** Vague descriptions produce vague output. Tighten
   the task description or choose a more specific template.
4. **Validate sandbox assumptions.** Run smaller `code_execute`-style tasks
   to isolate whether the sandbox itself is the bottleneck.
5. **Treat this as tuning/benchmarking debt.** File it as a model-selection
   or template-tuning issue. Do not open architecture or protocol changes
   to address output quality.
