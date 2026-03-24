FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl \
    && rm -rf /var/lib/apt/lists/*

# Core Python deps (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Heavy ML deps (separate layer — failure-tolerant)
COPY requirements-ml.txt .
RUN pip install --no-cache-dir -r requirements-ml.txt \
    || echo "WARNING: ML deps failed — server will start without routing embedder"

# App code
COPY . .

# Entrypoint — cleans stale WAL files from bind-mounted state
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Set PYTHONPATH so src/ imports resolve
ENV PYTHONPATH=/app

# Serve web dashboard via uvicorn
EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "src.server:app_factory", \
     "--host", "0.0.0.0", "--port", "8000", "--factory"]
