#!/usr/bin/env bash
# setup-local-swarm.sh — Add a parallel colony worker model to the local GPU stack.
# Downloads Qwen3.5-4B GGUF and appends swarm configuration to .env.
#
# Prerequisites: run setup-local-gpu.sh first (main LLM + embedding).
# Platform: Linux / WSL2 / Git Bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

echo "==> Downloading swarm model (Qwen3.5-4B)..."
mkdir -p .models && cd .models
huggingface-cli download Qwen/Qwen3.5-4B-GGUF \
  Qwen3.5-4B-Q4_K_M.gguf --local-dir .
cd "$REPO_DIR"

echo "==> Appending swarm configuration to .env..."
if [ ! -f .env ]; then
  echo "ERROR: .env not found. Run setup-local-gpu.sh first."
  exit 1
fi

# Only append if not already configured
if ! grep -q "LLM_SWARM_HOST" .env 2>/dev/null; then
  cat >> .env <<'EOF'

# --- Local Swarm (parallel colony workers) ---
# Deep Queen profile (RECOMMENDED): Queen gets full 65K context, 4 parallel workers at 32K each.
LLM_SWARM_HOST=http://llm-swarm:8080
LLM_SWARM_SLOTS=4
LLM_SWARM_CTX=128000
CODER_MODEL=llama-cpp-swarm/qwen3.5-4b-swarm
REVIEWER_MODEL=llama-cpp-swarm/qwen3.5-4b-swarm
ARCHIVIST_MODEL=llama-cpp-swarm/qwen3.5-4b-swarm
LLM_SLOTS=1
EOF
  echo "   Swarm config appended to .env"
else
  echo "   Swarm config already present in .env — skipping"
fi

echo "==> Done. Start with:"
echo "   docker compose -f docker-compose.yml -f docker-compose.local-swarm.yml up -d"
echo "   This adds a swarm worker container alongside the existing stack."
