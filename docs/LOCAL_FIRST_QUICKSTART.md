# Local-First Quick Start

Run FormicOS entirely on your machine with no API keys and no cloud dependencies.

## Prerequisites

- **Docker** with BuildKit (Docker Desktop or WSL2 integration)
- **NVIDIA GPU** with CUDA support (RTX 5090 recommended, 32 GB VRAM)
- **~10 GB disk space** for model weights + Docker images
- **nvidia-container-toolkit** installed

No Python, Node.js, or other local toolchain required -- everything runs in containers.

## 1. Clone and Download Models

```bash
git clone https://github.com/Intradyne/FormicOS.git
cd FormicOS
mkdir -p .models && cd .models

# LLM — Qwen3-30B-A3B (MoE, 3.3B active params, excellent tool calling)
huggingface-cli download Qwen/Qwen3-30B-A3B-Instruct-2507-GGUF \
  Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf --local-dir .

# Embedding — Qwen3-Embedding-0.6B (decoder-only, last-token pooling)
huggingface-cli download Qwen/Qwen3-Embedding-0.6B-GGUF \
  Qwen3-Embedding-0.6B-Q8_0.gguf --local-dir .

cd ..
```

## 2. Build the Blackwell-Native LLM Image

The default Docker image uses Blackwell-native CUDA kernels (sm_120) for full
performance on RTX 5090. Without this, llama.cpp falls back to PTX JIT
compilation, resulting in ~10x slower inference and ~16k effective context
instead of the default 80k target.

```bash
bash scripts/build_llm_image.sh
```

This takes 10-20 minutes on first build. It produces `local/llama.cpp:server-cuda-blackwell`.

**Fallback (non-Blackwell GPUs):** If you can't build the image or have an
older GPU, set in `.env`:
```
LLM_IMAGE=ghcr.io/ggml-org/llama.cpp:server-cuda
```
The stack will still work but with reduced context and throughput.

## 3. Build the Sandbox Image (Optional)

The sandbox image enables isolated code execution inside colonies. Without it,
`code_execute` falls back to a restricted subprocess.

```bash
docker build -f docker/sandbox.Dockerfile -t formicos-sandbox:latest .
```

To **disable** Docker-based sandboxing entirely (e.g. when you don't want to
mount the Docker socket), add to `.env`:
```
SANDBOX_ENABLED=false
```

> **Security note:** The default `docker-compose.yml` mounts the Docker socket
> (`/var/run/docker.sock`) into the FormicOS container so it can spawn sandbox
> sibling containers. This gives the container Docker daemon access. For a
> single-operator local-first deployment this is standard practice. Set
> `SANDBOX_ENABLED=false` to disable Docker sandboxing, and remove the socket
> mount as well if you want to opt out of daemon access entirely.

## 4. Start FormicOS

```bash
docker compose up -d
```

First boot takes a minute or two:
- Builds the FormicOS application image (frontend + Python backend)
- Starts Qdrant (vector store), embedding sidecar, LLM server, and FormicOS
- Creates a default workspace and "main" thread

Watch for healthy containers:
```bash
docker compose ps
```

All four services (`formicos-colony`, `formicos-llm`, `formicos-embed`, `formicos-qdrant`) should show `healthy`.

You can also confirm the app has replayed and bootstrapped:
```bash
curl http://localhost:8080/health
```

Expected shape:
```json
{
  "status": "ok",
  "last_seq": 0,
  "bootstrapped": true,
  "workspaces": 1,
  "threads": 1
}
```

## 5. Open the UI

Navigate to **http://localhost:8080**.

You'll see:
- **Startup panel** while the backend connects and loads the first workspace
- **Tree navigator** (left sidebar) with "default" workspace and "main" thread
- **Queen tab** with the welcome message and first-run guidance
- **Knowledge** tab for unified skills, experiences, and the graph
- **Models** and **Settings** tabs for runtime inspection

## 6. First Interaction

1. Wait for the startup panel to clear
2. Click on the "main" thread in the Queen view
3. Type a message like: "Write a Python function that checks if a number is prime"
4. The Queen responds with a plan and can spawn a colony of agents
5. Watch the colony execute rounds in the tree navigator

## 7. Explore the UI

- **Queen tab** -- chat with the Queen, see active colonies, approve/deny requests
- **Knowledge tab** -- inspect unified knowledge entries, score explanations, proactive briefing context, and the graph
- **Playbook tab** -- browse built-in templates before you spawn
- **Tree navigator** -- click workspaces, threads, and colonies to drill down
- **Models tab** -- see registered models (local + cloud), context windows, slot utilization
- **Settings tab** -- view event store status, coordination strategy, and protocol connections

## VRAM Budget

At 80k context on RTX 5090 (32 GB):

| Component | VRAM |
|-----------|------|
| Model weights (Q4_K_M) | ~17.3 GB |
| KV cache (80k ctx x 2 slots x q8_0) | ~5.2 GB |
| Compute buffers | ~2.4 GB |
| Embedding sidecar (Q8_0) | ~0.7 GB |
| **Total** | **~25.6 GB** |
| Headroom | ~6.4 GB |

If VRAM is tight, set `EMBED_GPU_LAYERS=0` in `.env` to move embedding to CPU,
freeing ~700 MB.

## Multi-GPU Setup

If your machine has multiple GPUs (e.g., RTX 5090 for inference + RTX 3080 for
display), pin the LLM and embedding containers to the inference GPU by setting
`CUDA_DEVICE` in `.env`:

```bash
# .env
CUDA_DEVICE=0   # GPU index for inference (default: 0)
```

**Docker Desktop / WSL2 note:** The `device_ids` field in the compose `deploy`
block is ignored on Docker Desktop with WSL2 — all GPUs are passed through
regardless. `CUDA_VISIBLE_DEVICES` (set automatically from `CUDA_DEVICE`) is
the effective control. Without pinning, llama.cpp may split the model across
GPUs, causing segfaults or severe performance degradation.

Run `nvidia-smi -L` to list GPUs and their indices.

## Troubleshooting

### "Connection refused" on http://localhost:8080
The server is still starting. The LLM server can take up to 2 minutes to load
the model. Check `docker compose logs formicos-llm` for progress.

### Context shows less than 80k in the UI
`--fit on` auto-sizes the KV cache to available VRAM. If the effective context
is significantly lower than 80k, you may be using the generic CUDA image
(PTX JIT). Build the Blackwell image with `bash scripts/build_llm_image.sh`.

### Port 8080 already in use
Another service is using port 8080. Either stop it, or change the port mapping
in `docker-compose.yml`:
```yaml
ports:
  - "9090:8080"  # access at http://localhost:9090
```

### Container keeps restarting
Check logs: `docker compose logs formicos-colony`. Common causes:
- Missing model files in `.models/`
- Invalid YAML syntax in config files
- Disk full

### Reset all state
To start fresh (deletes all events and model data):
```bash
docker compose down -v
docker compose up -d
```
