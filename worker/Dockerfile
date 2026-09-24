# Dockerfile for edim-worker (isolated compute daemon).
# Build context is the repo root so backend/, model_runtime/ and worker/
# are available.
#
# Architecture: the worker daemon (worker/) does not import backend service
# code. It receives messages from Service Bus, calls the edim_model CLI
# (model_runtime/), and the CLI in turn loads the model-logic black box
# from backend/api_service. In staging/production the worker VM image
# contains only worker/ + model_runtime/ + the backend model logic files
# required by the CLI; it has no Postgres access.

FROM python:3.11-slim

WORKDIR /app

# System dependencies required by netCDF4 / Calliope build chain.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libhdf5-dev \
    libnetcdf-dev \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install backend dependencies (needed by the model-logic black box).
COPY backend/requirements.txt /tmp/backend-requirements.txt
RUN pip install -U pip && pip install -r /tmp/backend-requirements.txt

# Install worker-specific Azure SDKs.
COPY worker/requirements.txt /tmp/worker-requirements.txt
RUN pip install -r /tmp/worker-requirements.txt

# Copy sources. backend/ is needed only because the model logic black box
# currently lives there; the worker daemon itself does not import from it.
COPY backend /app/backend
COPY model_runtime /app/model_runtime
COPY worker /app/worker

# Model input datasets. These ARE a runtime dependency: the model runtime reads
# config_dir for scenario_metadata.csv, lever_mappings.csv, mario_inputs/* and
# generated/*. Omitting this made every run fail at model build, and left
# runtime_config.json absent so the artifact policy came back empty.
#
# The narrative "Energy Modelling Scenario Report.docx" is deliberately NOT
# copied: edim_model.core.scenario_report documents that it is not a runtime
# dependency and loads structured JSON (inputs/generated/...) instead.
COPY inputs /app/inputs

# Run workspaces are created under runs_dir at execution time.
RUN mkdir -p /app/outputs/runs

# Ensure repo-root packages are importable.
# /app makes 'worker', 'backend', 'model_runtime' importable.
# /app/model_runtime makes 'edim_model' importable as a top-level package.
#
# edim_model.local_runtime derives REPO_ROOT as parents[2] of the module file,
# which resolves to /app here - matching the paths above.
ENV PYTHONPATH=/app:/app/model_runtime

# Default command is overridden by docker-compose-dev.yml.
CMD ["python", "-m", "worker.daemon"]
