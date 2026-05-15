# Use the official uv image — it has Python + uv preinstalled.
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

# Install dependencies first (cached layer — only rebuilds when pyproject changes).
COPY pyproject.toml ./
RUN uv sync --no-dev --frozen --no-install-project 2>/dev/null || uv sync --no-dev --no-install-project

# Copy app code.
COPY app ./app

# Install the project itself.
RUN uv sync --no-dev --no-editable

# Fly.io expects the app to listen on $PORT (default 8080).
ENV PORT=8080
EXPOSE 8080

CMD ["uv", "run", "python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
