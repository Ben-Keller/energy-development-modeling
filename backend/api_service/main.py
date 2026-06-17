from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.routers import (
    datasets_router,
    platform_router,
    runs_router,
    scenarios_router,
    system_router,
)
from .jobs import JobManager
from .runtime import EventStore, LocalEventStore
from .services.artifact_storage import ArtifactStorageService, LocalArtifactStorageService
from .services.dataset_repository import DatasetRepository, LocalDatasetRepository
from .services.model_catalog import ModelCatalogProvider, RuntimeCliModelCatalogProvider
from .services.platform_repository import PlatformRepository, create_platform_repository
from .settings import Settings, get_settings

logger = logging.getLogger(__name__)


def _run_alembic_migrations(settings: Settings) -> None:
    """Run 'alembic upgrade head' before the app accepts traffic.

    Only executed when EDIM_DATABASE_URL is set and EDIM_RUN_MIGRATIONS is
    truthy (default true in docker-compose-dev.yml).
    """
    run_migrations = os.getenv("EDIM_RUN_MIGRATIONS", "true").strip().lower()
    if run_migrations not in {"1", "true", "yes"}:
        logger.info("Skipping alembic migrations (EDIM_RUN_MIGRATIONS=%s).", run_migrations)
        return
    database_url = os.getenv("EDIM_DATABASE_URL", "").strip()
    if not database_url:
        return
    backend_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["EDIM_ALEMBIC_URL"] = database_url
    cmd = [sys.executable, "-m", "alembic", "-c", str(backend_root / "alembic.ini"), "upgrade", "head"]
    logger.info("Running alembic upgrade head...")
    result = subprocess.run(cmd, cwd=str(backend_root), env=env, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("alembic upgrade failed:\nstdout=%s\nstderr=%s", result.stdout, result.stderr)
        raise RuntimeError(f"alembic upgrade failed: {result.stderr or result.stdout}")
    logger.info("alembic upgrade head completed.")


def _create_event_store(settings: Settings) -> EventStore:
    """Return PostgresEventStore when EDIM_DATABASE_URL is set, else local JSONL."""
    database_url = os.getenv("EDIM_DATABASE_URL", "").strip()
    if database_url:
        try:
            from .db import build_engine, build_session_factory
            from .services.event_store import PostgresEventStore

            engine = build_engine()
            session_factory = build_session_factory(engine)
            return PostgresEventStore(session_factory)  # type: ignore[return-value]
        except Exception as exc:
            logger.warning("PostgresEventStore unavailable (%s); falling back to LocalEventStore.", exc)
    return LocalEventStore(settings.runs_dir)


def _discover_frontend_dir(settings) -> Path | None:
    env_dir = (os.getenv("EDIM_FRONTEND_DIR") or "").strip()
    if env_dir:
        path = Path(env_dir).expanduser().resolve()
        if path.exists() and path.is_dir():
            return path
    if settings.frontend_dir and settings.frontend_dir.exists() and settings.frontend_dir.is_dir():
        return settings.frontend_dir
    return None


def create_app(
    settings: Settings | None = None,
    *,
    platform_repository: PlatformRepository | None = None,
    artifact_storage: ArtifactStorageService | None = None,
    dataset_repository: DatasetRepository | None = None,
    event_store: EventStore | None = None,
    model_catalog_provider: ModelCatalogProvider | None = None,
    job_manager: JobManager | None = None,
) -> FastAPI:
    """Create the FastAPI app with replaceable infrastructure providers.

    When EDIM_DATABASE_URL is set (docker-compose-dev and cloud deployments):
      - Runs Alembic migrations before accepting traffic
      - Uses PostgresPlatformRepository for durable project/run metadata
      - Uses PostgresEventStore for execution event persistence
      - Artifact storage and dataset repository still use local filesystem
        (volume-mounted in docker-compose-dev); Azurite-backed implementations
        are a TODO (injection point is here via artifact_storage= / dataset_repository=).
    """
    settings = settings or get_settings()

    # Run migrations before creating providers so the schema is ready.
    _run_alembic_migrations(settings)

    if job_manager is not None:
        platform_repository = platform_repository or getattr(job_manager, "_run_repository", None)
        artifact_storage = artifact_storage or getattr(job_manager, "_artifact_storage", None)
        dataset_repository = dataset_repository or getattr(job_manager, "_dataset_repository", None)
        event_store = event_store or getattr(job_manager, "_event_store", None)
    platform_repository = platform_repository or create_platform_repository(settings)
    artifact_storage = artifact_storage or LocalArtifactStorageService(settings)
    dataset_repository = dataset_repository or LocalDatasetRepository(settings)
    event_store = event_store or _create_event_store(settings)
    model_catalog_provider = model_catalog_provider or RuntimeCliModelCatalogProvider()
    job_manager = job_manager or JobManager(
        settings,
        run_repository=platform_repository,
        dataset_repository=dataset_repository,
        event_store=event_store,
        artifact_storage=artifact_storage,
    )

    app = FastAPI(title="EDIM Calliope-Africa API", version="0.1.0")
    app.state.settings = settings
    app.state.platform_repository = platform_repository
    app.state.artifact_storage = artifact_storage
    app.state.dataset_repository = dataset_repository
    app.state.event_store = event_store
    app.state.model_catalog_provider = model_catalog_provider
    app.state.job_manager = job_manager
    app.state.frontend_dir = _discover_frontend_dir(settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1):\d+$",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if app.state.frontend_dir is not None:
        app.mount("/ui", StaticFiles(directory=str(app.state.frontend_dir), html=True), name="ui")
    else:
        logger.warning("Frontend directory not found; UI routes disabled.")

    for router in (system_router, platform_router, scenarios_router, datasets_router, runs_router):
        app.include_router(router)
    return app


app = create_app()
