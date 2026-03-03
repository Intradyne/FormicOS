FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Set PYTHONPATH so src/ imports resolve
ENV PYTHONPATH=/app

# Serve web dashboard via uvicorn
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "src.server:app_factory", \
     "--host", "0.0.0.0", "--port", "8000", "--factory"]
