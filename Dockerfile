# =============================================================================
# Stage 1: Builder — install heavy deps (Whisper, ffmpeg) once
# =============================================================================
FROM python:3.11-slim AS builder

# System dependencies (ffmpeg for audio processing, build tools for Whisper)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt

# =============================================================================
# Stage 2: Runtime — lean final image
# =============================================================================
FROM python:3.11-slim AS runtime

# Copy ffmpeg binary from builder
COPY --from=builder /usr/bin/ffmpeg /usr/bin/ffmpeg
COPY --from=builder /usr/lib/x86_64-linux-gnu/libav* /usr/lib/x86_64-linux-gnu/

# Copy installed Python packages
COPY --from=builder /install /usr/local

# Create non-root user for security
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Copy application code
COPY --chown=appuser:appuser . .

# Create data directories with proper permissions
RUN mkdir -p /app/data/sqlite /app/data/audio_cache \
    && chown -R appuser:appuser /app/data

USER appuser

# Health-check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--loop", "asyncio"]
