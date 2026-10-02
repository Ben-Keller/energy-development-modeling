from __future__ import annotations

from fastapi import HTTPException, Request

from ..jobs import JobManager
from ..runtime import EventStore
from ..services.artifact_storage import ArtifactStorageService
from ..services.dataset_repository import DatasetRepository
from ..services.model_catalog import ModelCatalogProvider
from ..services.platform_repository import PlatformRepository
from ..services.users import AUTH_MODE_TEST_HEADER, UserContext, is_known_test_user, resolve_user_context
from ..settings import Settings


def get_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        raise HTTPException(status_code=500, detail="Application settings not initialized")
    return settings


def get_job_manager(request: Request) -> JobManager:
    job_manager = getattr(request.app.state, "job_manager", None)
    if job_manager is None:
        raise HTTPException(status_code=500, detail="Job manager not initialized")
    return job_manager


def get_event_store(request: Request) -> EventStore:
    """Resolve runtime event persistence for execution progress/history.

    Local development stores JSONL files under `outputs/runs/_queued`. Hosted
    deployments should inject a DB/blob/event-stream implementation here so
    `/api/executions/{execution_id}/events` does not depend on local worker files.
    """
    event_store = getattr(request.app.state, "event_store", None)
    if event_store is None:
        raise HTTPException(status_code=500, detail="Event store not initialized")
    return event_store


def get_platform_repository(request: Request) -> PlatformRepository:
    """Resolve project/run/report/export persistence for the current app.

    Hosted deployments should attach a database-backed implementation to
    `app.state.platform_repository`.
    """
    repository = getattr(request.app.state, "platform_repository", None)
    if repository is None:
        raise HTTPException(status_code=500, detail="Platform repository not initialized")
    return repository


def get_artifact_storage_service(request: Request) -> ArtifactStorageService:
    """Resolve artifact storage for run/report/export reads.

    This is the download boundary. Cloud implementations should authorize in
    the route/service layer, then return a streaming response or signed URL from
    this provider rather than exposing raw storage paths.
    """
    storage = getattr(request.app.state, "artifact_storage", None)
    if storage is None:
        raise HTTPException(status_code=500, detail="Artifact storage service not initialized")
    return storage


def get_dataset_repository(request: Request) -> DatasetRepository:
    """Resolve input dataset catalog/version/upload storage.

    Dataset overrides are user-scoped and are snapshotted into each run bundle.
    Production storage should preserve that semantic even if files move from
    the local filesystem to Blob/object storage.
    """
    repository = getattr(request.app.state, "dataset_repository", None)
    if repository is None:
        raise HTTPException(status_code=500, detail="Dataset repository not initialized")
    return repository


def get_model_catalog_provider(request: Request) -> ModelCatalogProvider:
    """Resolve the model-owned catalog provider for scenarios and architectures."""
    provider = getattr(request.app.state, "model_catalog_provider", None)
    if provider is None:
        raise HTTPException(status_code=500, detail="Model catalog provider not initialized")
    return provider


def get_current_user_context(request: Request) -> UserContext:
    # Local handoff auth shim. Production should replace this dependency with
    # Azure/auth middleware while preserving the downstream user-context shape.
    raw_user_id = (
        request.headers.get("x-edim-user-id")
        or request.query_params.get("user_id")
        or request.cookies.get("edim_user_id")
    )
    if raw_user_id and not is_known_test_user(raw_user_id):
        raise HTTPException(status_code=401, detail="Unknown EDIM test user.")
    return resolve_user_context(raw_user_id, auth_mode=AUTH_MODE_TEST_HEADER)


def get_current_user(request: Request) -> dict:
    return get_current_user_context(request).to_dict()


def get_current_user_id(request: Request) -> str:
    return get_current_user_context(request).user_id
