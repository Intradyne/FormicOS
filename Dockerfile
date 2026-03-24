# Stage 1: Frontend build
FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.12-slim AS runtime

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Docker CLI for sandbox container spawning (code_execute tool)
COPY --from=docker:27-cli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /app

# Install Python dependencies (cached layer)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --frozen

# Copy source and config
COPY src/ src/
COPY config/ config/

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist/ frontend/dist/

# Create data directory
RUN mkdir -p /data

ENV FORMICOS_DATA_DIR=/data
EXPOSE 8080

# Health check
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

ENTRYPOINT ["uv", "run", "python", "-m", "formicos"]
