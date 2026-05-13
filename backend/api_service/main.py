from __future__ import annotations

import logging
import os
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

    This is the composition root for handoff. Azure/cloud code should inject
    auth-aware repositories, Blob-backed artifact/dataset services, and a
    durable queue-backed job manager here rather than modifying router logic.
    """
    settings = settings or get_settings()
    if job_manager is not None:
        platform_repository = platform_repository or getattr(job_manager, "_run_repository", None)
        artifact_storage = artifact_storage or getattr(job_manager, "_artifact_storage", None)
        dataset_repository = dataset_repository or getattr(job_manager, "_dataset_repository", None)
        event_store = event_store or getattr(job_manager, "_event_store", None)
    platform_repository = platform_repository or create_platform_repository(settings)
    artifact_storage = artifact_storage or LocalArtifactStorageService(settings)
    dataset_repository = dataset_repository or LocalDatasetRepository(settings)
    event_store = event_store or LocalEventStore(settings.runs_dir)
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
