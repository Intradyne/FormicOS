#!/usr/bin/env bash
# Build a Blackwell-native llama.cpp server image for RTX 5090 / sm_120.
#
# Usage:
#   bash scripts/build_llm_image.sh
#
# Produces:
#   local/llama.cpp:server-cuda-blackwell
#
# Requirements:
#   - Docker with BuildKit (Docker Desktop or WSL2 integration)
#   - ~10-20 minutes on first build, faster on rebuild
#   - ~4 GB disk for the build context + image layers
#
# Why not the official image?
#   ghcr.io/ggml-org/llama.cpp:server-cuda ships CUDA 12.4 which predates
#   Blackwell (sm_120). The RTX 5090 falls back to PTX JIT compilation,
#   resulting in ~10x slower inference and higher VRAM overhead. A native
#   build eliminates PTX JIT and enables full Blackwell kernel performance.
#
# Fallback:
#   If you cannot build locally, set in .env:
#     LLM_IMAGE=ghcr.io/ggml-org/llama.cpp:server-cuda
#   The stack will still work but with reduced context and throughput.

set -euo pipefail

IMAGE_TAG="${1:-local/llama.cpp:server-cuda-blackwell}"
BUILD_DIR="${TMPDIR:-/tmp}/llama-cpp-build"
LLAMA_REPO="https://github.com/ggml-org/llama.cpp.git"

echo "==> Building llama.cpp server with Blackwell (sm_120) CUDA kernels"
echo "    Image tag: ${IMAGE_TAG}"
echo "    Build dir: ${BUILD_DIR}"
echo ""

# Clone or update llama.cpp
if [ -d "${BUILD_DIR}" ]; then
    echo "==> Updating existing llama.cpp clone..."
    cd "${BUILD_DIR}"
    git fetch --depth 1 origin master
    git checkout FETCH_HEAD
else
    echo "==> Cloning llama.cpp..."
    git clone --depth 1 "${LLAMA_REPO}" "${BUILD_DIR}"
    cd "${BUILD_DIR}"
fi

# Build the Docker image with Blackwell-native CUDA kernels.
#
# Compile-time flag:
#   CUDA_DOCKER_ARCH=120       - Native Blackwell kernels (no PTX JIT)
#     Note: CMake adds the sm_ prefix itself, so pass just "120" not "sm_120"
#
# Runtime flags (set in docker-compose.yml environment, not build args):
#   GGML_CUDA_NO_PINNED=1      - Avoids GDDR7 pinned-memory issues on RTX 5090
#   GGML_CUDA_FORCE_CUBLAS=ON  - Fixes prompt processing bug on Blackwell
#   GGML_CUDA_FA_ALL_QUANTS=ON - Enables sub-f16 KV cache with flash attention
#   GGML_CUDA_GRAPHS=ON        - Batches kernel launches for lower overhead
echo ""
echo "==> Building Docker image (this takes 10-20 minutes on first run)..."

docker build \
    -t "${IMAGE_TAG}" \
    --build-arg CUDA_VERSION=12.8.1 \
    --build-arg CUDA_DOCKER_ARCH=120 \
    --build-arg CMAKE_ARGS="-DGGML_CUDA_NO_PINNED=1 -DGGML_CUDA_FORCE_CUBLAS=ON -DGGML_CUDA_FA_ALL_QUANTS=ON -DGGML_CUDA_GRAPHS=ON -DGGML_FLASH_ATTN=ON" \
    --target server \
    -f .devops/cuda.Dockerfile \
    .

echo ""
echo "==> Done! Image built: ${IMAGE_TAG}"
echo ""
echo "    You can now run:  docker compose up -d"
echo "    Or verify with:   docker run --rm ${IMAGE_TAG} --version"
