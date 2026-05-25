# ============================================================================
# Crypto Agent Platform — Production Dockerfile
# Multi-stage build for minimal final image size
# ============================================================================

# --- Stage 1: Builder ---
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ src/

# Install Python dependencies into a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# --- Stage 2: Runtime ---
FROM python:3.11-slim AS runtime

LABEL maintainer="crypto-agent-platform"
LABEL description="Multi-agent AI platform for crypto research"

# Create non-root user
RUN groupadd --gid 1000 agent && \
    useradd --uid 1000 --gid agent --create-home agent

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy application source
COPY --from=builder /build/src ./src

# Copy configs
COPY configs/ configs/

# Set ownership
RUN chown -R agent:agent /app

USER agent

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import src; print('ok')" || exit 1

ENTRYPOINT ["python", "-m", "src.main"]
CMD ["--task", "Analyze current market conditions", "--verbose"]
