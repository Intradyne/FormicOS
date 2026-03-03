# Formic-OS Quick Start Guide

Get a multi-agent colony running in five steps.

## Prerequisites

- **Docker Desktop 4.48+** with GPU support enabled (Settings > Resources > GPU)
- **NVIDIA GPU** with 32 GB+ VRAM (RTX 4090, RTX 5090, or similar). 16 GB will work with smaller models and reduced context sizes.
- **16 GB+ system RAM** (32 GB recommended)
- **GGUF model files** downloaded to a local directory:
  - `Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf` -- primary LLM (~18 GB)
  - `bge-m3-q8_0.gguf` -- embedding model (~635 MB)

## Step 1: Clone and Configure

Clone the repository:

```bash
git clone <repository-url> Formic-OS
cd Formic-OS
```

Place your GGUF model files in the `./models/` directory:

```bash
mkdir -p models
# Copy or symlink your model files here:
#   models/Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf
#   models/bge-m3-q8_0.gguf
```

Review `config/formicos.yaml`. The defaults work out of the box for an RTX 5090 with 32 GB VRAM. If your hardware differs, adjust these settings:

```yaml
hardware:
  gpu: rtx4090          # Your GPU model (informational)
  vram_gb: 24           # Your total VRAM
  vram_alert_threshold_gb: 20

inference:
  context_size: 8192   # Matches the updated 8K KV Cache profile
```

If you reduce the context size, also update the LLM_CONTEXT_SIZE environment variable:

```bash
export LLM_CONTEXT_SIZE=8192
```

## Step 2: Start the Stack

```bash
docker compose up -d
```

This launches five services:

| Service | Container | Port | Startup Time |
|---------|-----------|------|-------------|
| FormicOS | formicos-colony | 8080 | ~15 seconds |
| LLM (llama.cpp) | formicos-llm | 8008 | 1-3 minutes (model loading) |
| Embeddings (llama.cpp) | formicos-embedding | 8009 | ~30 seconds |
| Qdrant | formicos-qdrant | 6333 | ~5 seconds |
| MCP Gateway | formicos-mcp-gateway | -- | ~10 seconds |

Monitor startup progress:

```bash
docker compose logs -f
```

Wait until the LLM service reports it is ready. The llama.cpp server will log a message like `main: server is listening on 0.0.0.0:8080` when model loading completes.

Check that all services are healthy:

```bash
docker compose ps
```

All services should show `Up` or `Up (healthy)`.

## Step 3: Open the Dashboard

Navigate to **http://localhost:8080** in your browser.

The dashboard shows:
- **System panel** (top) -- GPU usage, model info, connection status
- **Colony control** -- Task input, agent configuration, run controls
- **Topology graph** -- Live DyTopo visualization (Cytoscape.js)
- **Decision log** -- Real-time colony decisions and agent outputs
- **Objects tab** -- Colony structure, teams, castes, skills, MCP tools

Verify the system panel shows your GPU and model information. If it shows "Unknown", the LLM server may still be loading.

## Step 4: Create Your First Colony

In the dashboard:

1. Enter a task in the task input field. Start with something concrete:
   ```
   Write a Python script that reads a CSV file and generates a summary report with statistics for each numeric column.
   ```

2. Configure agents. A good starting configuration:
   - **Agents**: 3 (manager is always included automatically)
   - **Max rounds**: 5
   - **Castes**: Architect, Coder, Reviewer

3. Click **Run**.

The orchestrator begins the 5-phase DyTopo loop. You will see:
- The manager decomposing the task in Phase 1
- Agent intent declarations in Phase 2
- The topology graph updating in Phase 3
- Streaming agent outputs in Phase 4 (with potential Voting Parallelism replicas)
- Compression summaries in Phase 5

Each round takes 30 seconds to several minutes depending on context size and GPU speed.

## Step 5: View Results

When the colony completes (by convergence or max rounds), a completion modal appears showing:
- Colony summary
- Files created in the workspace
- A "View Results" button

Agent artifacts are written to the `./workspace/` directory on your host machine (mounted into the container). You can also browse results via the Objects tab.

To run another task, enter a new task and click Run. Previous sessions are saved automatically and can be loaded from the Sessions panel.

## Troubleshooting

### GPU Not Detected

**Symptom**: System panel shows "No GPU" or VRAM displays 0.

**Fixes**:
- Verify Docker Desktop GPU support is enabled: Settings > Resources > GPU
- Check NVIDIA Container Toolkit is installed: `nvidia-smi` should work inside Docker
- Restart Docker Desktop after enabling GPU support
- On Windows, ensure WSL2 backend is active (not Hyper-V)

```bash
# Verify GPU is visible to Docker
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

### LLM Server Fails to Start

**Symptom**: `formicos-llm` container exits or restarts repeatedly.

**Fixes**:
- Check logs: `docker compose logs llm`
- Verify the model file exists and the path is correct in `docker-compose.yml`
- Reduce `LLM_CONTEXT_SIZE` if you get CUDA out-of-memory errors:
  ```bash
  LLM_CONTEXT_SIZE=32768 docker compose up -d llm
  ```
- Ensure the GGUF file is not corrupted (re-download if needed)

### Qdrant Connection Refused

**Symptom**: Dashboard shows "Qdrant unavailable" or RAG features fail.

**Fixes**:
- Check Qdrant is running: `docker compose ps qdrant`
- Check logs: `docker compose logs qdrant`
- Verify port 6333 is not in use by another process: `netstat -an | grep 6333`
- The Qdrant container health check uses TCP only (`</dev/tcp/localhost/6333`). If it shows unhealthy, the service itself has a problem.

### MCP Gateway Not Connecting

**Symptom**: Objects tab shows MCP error or no tools available.

**Fixes**:
- The MCP gateway requires Docker Desktop 4.48+ with MCP Toolkit enabled
- Enable MCP servers via Docker Desktop: Settings > MCP Toolkit
- Or via CLI:
  ```bash
  docker mcp server enable filesystem fetch memory sequentialthinking
  docker mcp server ls
  ```
- Check gateway logs: `docker compose logs mcp-gateway`
- Try reconnecting via the dashboard (MCP section > Reconnect button)
- If running outside Docker, the gateway falls back to SSE on `http://localhost:8811`

### WebSocket Disconnects

**Symptom**: Dashboard shows "Disconnected" or streaming stops mid-round.

**Fixes**:
- The dashboard implements exponential backoff reconnection automatically. Wait a few seconds.
- Check that the FormicOS container is healthy: `docker compose ps formicos`
- If behind a reverse proxy, ensure WebSocket upgrade headers are forwarded
- Check browser console for connection errors

### Colony Appears Stuck

**Symptom**: No progress for several minutes, round counter not advancing.

**Fixes**:
- The LLM may be processing a large context. Check GPU utilization: `nvidia-smi`
- If HITL approval is pending, check the dashboard for an approval modal
- Use the Intervene button to inject guidance into the colony
- Extend rounds with the Extend button if the colony hit `max_rounds`
- Check orchestrator logs: `docker compose logs formicos`

### Resetting Everything

To start completely fresh:

```bash
docker compose down -v          # Stop all services, remove volumes
rm -rf workspace/*              # Clear workspace artifacts
rm -rf sessions/*               # Clear saved sessions
docker compose up -d            # Restart
```

The `-v` flag removes the Qdrant data volume. Omit it if you want to keep your vector data.
