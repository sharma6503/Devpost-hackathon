# ── Stage 1: builder ──────────────────────────────────────────────────────────
# Installs all build-time tooling (Node installer scripts, uv, ast-grep binary
# extraction) and pre-bakes MCP servers. None of the build tooling survives into
# the final image; only compiled binaries, installed packages, and app source are
# copied forward.
FROM python:3.13-slim-bookworm AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    UV_COMPILE_BYTECODE=1 \
    PATH="/root/.local/bin/:$PATH" \
    NPM_CONFIG_CACHE=/tmp/.npm \
    UV_CACHE_DIR=/tmp/.uv_cache

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg unzip wget \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Pre-install MCP servers
RUN uv tool install mcp-atlassian && \
    npm install -g @modelcontextprotocol/server-github

# Install ast-grep (sg) binary
RUN mkdir -p /tmp/ast-grep && \
    curl -LsSf https://github.com/ast-grep/ast-grep/releases/latest/download/app-x86_64-unknown-linux-gnu.zip -o /tmp/ast-grep.zip && \
    unzip /tmp/ast-grep.zip -d /tmp/ast-grep && \
    mv /tmp/ast-grep/sg /usr/local/bin/sg && \
    chmod +x /usr/local/bin/sg && \
    rm -rf /tmp/ast-grep /tmp/ast-grep.zip

WORKDIR /app
COPY pyproject.toml ./
RUN uv sync --no-dev
COPY . .

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
# Slim final image — only Node.js runtime (needed for MCP server process),
# compiled binaries, and the app itself. All build-time installer artifacts
# (~200 MB) stay in the builder layer.
FROM python:3.13-slim-bookworm AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    GOOGLE_CLOUD_LOCATION=global \
    PATH="/app/.venv/bin:/root/.local/bin:$PATH" \
    NPM_CONFIG_CACHE=/tmp/.npm

# Node.js runtime is required at container start (MCP server process).
# We install it here directly (no installer script needed — just the package).
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g @modelcontextprotocol/server-github \
    && rm -rf /var/lib/apt/lists/*

# Copy only the artifacts we need from the builder stage.
COPY --from=builder /usr/local/bin/sg /usr/local/bin/sg
COPY --from=builder /root/.local /root/.local
COPY --from=builder /app /app

WORKDIR /app

EXPOSE 8080

# Launches the API server on the assigned Cloud Run port directly via virtualenv uvicorn.
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
