# Multi-stage Docker build for video processing platform
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    # FFmpeg for video processing
    ffmpeg \
    # System utilities
    curl \
    wget \
    git \
    # Build dependencies
    build-essential \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN useradd --create-home --shell /bin/bash app

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt pyproject.toml ./

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Development stage
FROM base as development

# Install development dependencies
RUN pip install pytest pytest-asyncio pytest-cov black isort flake8 mypy

# Copy source code
COPY --chown=app:app . .

# Install application in development mode
RUN pip install -e .

# Switch to app user
USER app

# Expose ports
EXPOSE 8000 5555

# Default command for development
CMD ["video-processor", "server", "start", "--host", "0.0.0.0", "--reload"]

# Production stage
FROM base as production

# Copy source code
COPY --chown=app:app src/ ./src/
COPY --chown=app:app pyproject.toml ./

# Install application
RUN pip install .

# Create necessary directories
RUN mkdir -p /app/output /app/temp /app/cache /app/logs && \
    chown -R app:app /app

# Switch to app user
USER app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Default command for production
CMD ["video-processor", "server", "production", "--workers", "4", "--bind", "0.0.0.0:8000"]

# Worker stage
FROM production as worker

# Default command for worker
CMD ["video-processor", "worker", "start", "--concurrency", "4"]

# Beat scheduler stage
FROM production as beat

# Default command for beat scheduler
CMD ["celery", "-A", "src.celery_app.app", "beat", "--loglevel", "info"]