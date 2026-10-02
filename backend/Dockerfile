FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app:/app/model_runtime

# System deps (netcdf)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libhdf5-dev \
    libnetcdf-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/requirements.txt
RUN pip install -U pip setuptools wheel && pip install -r requirements.txt

COPY model_runtime /app/model_runtime
RUN pip install --no-build-isolation /app/model_runtime

COPY backend/api_service /app/api_service
COPY inputs /app/inputs
COPY frontend /app/frontend

EXPOSE 8000
CMD ["uvicorn", "api_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
