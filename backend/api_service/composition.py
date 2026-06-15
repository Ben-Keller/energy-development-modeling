"""Application composition root.

Builds the database engine, runs Alembic migrations at startup
(plan 3.4: "before the new App Service container is permitted to
accept traffic"), and wires the Postgres-backed providers and the
Azure Service Bus queues into app.state so FastAPI dependencies can
pull them per-request.

Architecture (plan 1.3.1, 6.1, 6.2):
  - PostgreSQL owns durable state (project_runs, execution_attempts,
    dataset_version_metadata, etc.) — written ONLY by the API layer.
    The isolated worker daemon has no database access.
  - Azure Service Bus owns the messaging: execution queue (worker
    consumes), cancellation queue (worker consumes, API produces),
    and completion queue (worker produces, API consumes). Dev uses
    the Service Bus emulator; staging and production use the real
    Service Bus Standard namespace with Managed Identity.
  - Azure Blob Storage owns unstructured data: input datasets,
    run artifacts, and runtime event logs.
  - The API only enqueues execution and cancellation messages. The
    worker daemon (separate container) consumes and runs the model.
    There is no in-process runner.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

from .db import build_engine, build_session_factory
from .services.event_store import PostgresEventStore
from .services.platform_repository import PostgresPlatformRepository
from .services.dataset_repository import PostgresDatasetRepository
from .services.service_bus_queue import AzureServiceBusQueue, ServiceBusQueueClient
from .settings import Settings
from .users import build_auth_provider, resolve_auth_mode
from .worker_bridge import WorkerBridge

try:
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient
    _AZURE_BLOB_AVAILABLE = True
except ImportError:  # pragma: no cover
    _AZURE_BLOB_AVAILABLE = False

logger = logging.getLogger(__name__)


def _alembic_upgrade_head(database_url: str, backend_root: Path) -> None:
    """Run alembic upgrade head transactionally. Plan 3.4."""
    env = os.environ.copy()
    env["EDIM_ALEMBIC_URL"] = database_url
    cmd = [sys.executable, "-m", "alembic", "-c", str(backend_root / "alembic.ini"), "upgrade", "head"]
    logger.info("Running alembic upgrade head...")
    result = subprocess.run(cmd, cwd=str(backend_root), env=env, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("alembic upgrade failed:\nstdout=%s\nstderr=%s", result.stdout, result.stderr)
        raise RuntimeError(f"alembic upgrade failed: {result.stderr or result.stdout}")


def _database_url_for_alembic() -> str:
    """Resolve the database URL for alembic. Honors EDIM_ALEMBIC_URL,
    EDIM_DATABASE_URL, and falls back to EDIM_DB_* discrete vars.
    """
    url = os.getenv("EDIM_ALEMBIC_URL") or os.getenv("EDIM_DATABASE_URL", "").strip()
    if url:
        return url
    user = os.getenv("EDIM_DB_USER", "edim")
    password = os.getenv("EDIM_DB_PASSWORD", "edim")
    host = os.getenv("EDIM_DB_HOST", "edim-db")
    port = os.getenv("EDIM_DB_PORT", "5432")
    name = os.getenv("EDIM_DB_NAME", "edim_db_local")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


def _service_bus_credentials():
    """Return (connection_string, namespace) from environment."""
    connection_string = os.getenv("EDIM_SERVICEBUS_CONNECTION_STRING", "").strip()
    namespace = os.getenv("EDIM_SERVICEBUS_NAMESPACE", "").strip()
    if not connection_string and not namespace:
        raise RuntimeError(
            "Set EDIM_SERVICEBUS_CONNECTION_STRING (dev emulator) or "
            "EDIM_SERVICEBUS_NAMESPACE (staging/production Managed Identity)."
        )
    return connection_string or None, namespace or None


def _build_service_bus_queue():
    """Construct the legacy AzureServiceBusQueue adapter for execution enqueueing."""
    connection_string, namespace = _service_bus_credentials()
    queue_name = os.getenv("EDIM_SERVICEBUS_QUEUE_NAME", "execution-queue-local").strip()
    return AzureServiceBusQueue(
        connection_string=connection_string,
        namespace=namespace,
        queue_name=queue_name,
    )


def _build_service_bus_queue_client(queue_name_env: str, default_name: str) -> ServiceBusQueueClient:
    connection_string, namespace = _service_bus_credentials()
    queue_name = os.getenv(queue_name_env, default_name).strip()
    return ServiceBusQueueClient(
        queue_name=queue_name,
        connection_string=connection_string,
        namespace=namespace,
    )


def _build_blob_service_client():
    """Construct a BlobServiceClient for the API.

    Dev uses EDIM_AZURITE_CONNECTION_STRING; staging/production use
    EDIM_BLOB_ACCOUNT_URL + Managed Identity.
    """
    if not _AZURE_BLOB_AVAILABLE:
        raise RuntimeError("azure-storage-blob is not installed.")
    connection_string = os.getenv("EDIM_AZURITE_CONNECTION_STRING", "").strip() or os.getenv(
        "EDIM_BLOB_CONNECTION_STRING", ""
    ).strip()
    account_url = os.getenv("EDIM_BLOB_ACCOUNT_URL", "").strip()
    if connection_string:
        return BlobServiceClient.from_connection_string(connection_string)
    if account_url:
        return BlobServiceClient(account_url=account_url, credential=DefaultAzureCredential())
    raise RuntimeError(
        "Set EDIM_AZURITE_CONNECTION_STRING (dev emulator) or EDIM_BLOB_ACCOUNT_URL (staging/production)."
    )


def bootstrap_app(app, settings: Settings, run_migrations: bool = True) -> None:
    """Wire Postgres + Service Bus + providers onto a FastAPI app instance.

    Called from main.py at startup. If run_migrations is False, the
    caller is responsible for ensuring migrations have already been
    applied (e.g. from a separate init container).
    """
    engine = build_engine()
    session_factory = build_session_factory(engine)
    app.state.db_engine = engine
    app.state.db_session_factory = session_factory

    if run_migrations:
        backend_root = Path(__file__).resolve().parents[1]
        _alembic_upgrade_head(_database_url_for_alembic(), backend_root)

    platform_repo = PostgresPlatformRepository(session_factory)
    dataset_repo = PostgresDatasetRepository(session_factory)
    event_store = PostgresEventStore(session_factory)
    queue_provider = _build_service_bus_queue()
    cancellation_queue = _build_service_bus_queue_client(
        "EDIM_SERVICEBUS_CANCELLATION_QUEUE_NAME", "cancellation-queue-local"
    )
    completion_queue = _build_service_bus_queue_client(
        "EDIM_SERVICEBUS_COMPLETION_QUEUE_NAME", "completion-queue-local"
    )

    app.state.platform_repository = platform_repo
    app.state.dataset_repository = dataset_repo
    app.state.event_store = event_store
    app.state.queue_provider = queue_provider
    app.state.cancellation_queue = cancellation_queue
    app.state.completion_queue = completion_queue

    blob_client = _build_blob_service_client()
    app.state.blob_client = blob_client

    app.state.worker_bridge = WorkerBridge(
        session_factory=session_factory,
        cancellation_queue=cancellation_queue,
        completion_queue=completion_queue,
        blob_client=blob_client,
        blob_container_prefix=os.getenv("EDIM_BLOB_CONTAINER_PREFIX", "stg-").strip(),
    )
    app.state.worker_bridge.start_completion_consumer()

    app.state.auth_provider = build_auth_provider(resolve_auth_mode())

    from .jobs_pg import PostgresJobManager

    app.state.job_manager = PostgresJobManager(
        session_factory=session_factory,
        settings=settings,
        queue_provider=queue_provider,
        worker_bridge=app.state.worker_bridge,
    )

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection verified.")
    except Exception as exc:
        logger.error("Database connection failed: %s", exc)
        raise
