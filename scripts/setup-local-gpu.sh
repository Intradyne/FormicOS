#!/usr/bin/env bash
# setup-local-gpu.sh — Prepare the local GPU stack for FormicOS.
# Downloads models, builds the Blackwell llama.cpp image, and enables
# the local-gpu profile in .env.
#
# Requirements: huggingface-cli, bash, Docker
# Platform: Linux / WSL2 / Git Bash (matches build_llm_image.sh)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

echo "==> Downloading models..."
mkdir -p .models && cd .models
huggingface-cli download Qwen/Qwen3.5-35B-A3B-GGUF \
  Qwen3.5-35B-A3B-Q4_K_M.gguf --local-dir .
huggingface-cli download Qwen/Qwen3-Embedding-0.6B-GGUF \
  Qwen3-Embedding-0.6B-Q8_0.gguf --local-dir .
cd "$REPO_DIR"

echo "==> Building Blackwell llama.cpp image..."
bash scripts/build_llm_image.sh

echo "==> Enabling local-gpu profile in .env..."
if [ ! -f .env ]; then
  cp .env.example .env
  echo "   Created .env from .env.example"
fi

# Uncomment the local GPU block
sed -i 's/^# COMPOSE_PROFILES=local-gpu/COMPOSE_PROFILES=local-gpu/' .env
sed -i 's/^# QUEEN_MODEL=llama-cpp\/qwen3.5-35b/QUEEN_MODEL=llama-cpp\/qwen3.5-35b/' .env
sed -i 's/^# CODER_MODEL=llama-cpp\/qwen3.5-35b/CODER_MODEL=llama-cpp\/qwen3.5-35b/' .env
sed -i 's/^# REVIEWER_MODEL=llama-cpp\/qwen3.5-35b/REVIEWER_MODEL=llama-cpp\/qwen3.5-35b/' .env
sed -i 's/^# RESEARCHER_MODEL=llama-cpp\/qwen3.5-35b/RESEARCHER_MODEL=llama-cpp\/qwen3.5-35b/' .env
sed -i 's/^# ARCHIVIST_MODEL=llama-cpp\/qwen3.5-35b/ARCHIVIST_MODEL=llama-cpp\/qwen3.5-35b/' .env
sed -i 's/^# LLM_HOST=http:\/\/llm:8080/LLM_HOST=http:\/\/llm:8080/' .env
sed -i 's/^# EMBED_URL=http:\/\/formicos-embed:8200/EMBED_URL=http:\/\/formicos-embed:8200/' .env
sed -i 's/^# EMBED_MODEL=nomic-ai\/nomic-embed-text-v1.5/EMBED_MODEL=nomic-ai\/nomic-embed-text-v1.5/' .env
sed -i 's/^# EMBED_DIMENSIONS=768/EMBED_DIMENSIONS=768/' .env

echo "==> Done. Run: docker compose up -d"
echo "   This will start 5 containers (FormicOS + Qdrant + Docker proxy + LLM + Embedding)."
