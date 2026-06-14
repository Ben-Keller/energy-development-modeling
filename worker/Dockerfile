# Dockerfile for edim-worker (isolated compute daemon).
# Build context is the repo root so both backend/ and model_runtime/ are available.

FROM python:3.11-slim

WORKDIR /app

# System dependencies required by netCDF4 / Calliope build chain.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libhdf5-dev \
    libnetcdf-dev \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install backend dependencies.
COPY backend/requirements.txt /tmp/backend-requirements.txt
RUN pip install -U pip && pip install -r /tmp/backend-requirements.txt

# Install worker-specific dependencies.
COPY worker/requirements.txt /tmp/worker-requirements.txt
RUN pip install -r /tmp/worker-requirements.txt

# Ensure repo-root packages are importable.
ENV PYTHONPATH=/app

# Default command is overridden by docker-compose-dev.yml.
CMD ["python", "-m", "worker.daemon"]
