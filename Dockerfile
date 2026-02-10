FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies (production only)
RUN uv sync --frozen --no-dev

# Copy application code
COPY src/ ./src/

# Default config location (mount your own at runtime)
COPY config.yaml ./
COPY api_keys.yaml.example ./

# Expose default port (override via config.yaml or docker-compose)
EXPOSE 8000

# Run the application
CMD ["uv", "run", "uvicorn", "openai_batch_proxy.main:app", "--host", "0.0.0.0", "--port", "8000"]
