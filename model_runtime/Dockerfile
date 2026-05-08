FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY model_runtime /app/model_runtime
COPY inputs /app/inputs

RUN pip install --no-cache-dir -e /app/model_runtime

ENTRYPOINT ["edim-model-runtime"]
CMD ["--help"]
