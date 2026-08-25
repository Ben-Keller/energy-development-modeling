from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from ..dependencies import get_current_user_context, get_dataset_repository, get_job_manager, get_model_catalog_provider, get_settings
from ...jobs import JobManager
from ...runtime import (
    ARTIFACT_MANIFEST_SCHEMA_VERSION,
    EXECUTION_ATTEMPT_SCHEMA_VERSION,
    EXECUTION_QUEUE_MESSAGE_SCHEMA_VERSION,
    EXECUTION_RETRY_POLICY_SCHEMA_VERSION,
    MODEL_RUN_BUNDLE_SCHEMA_VERSION,
    RUNTIME_ARTIFACT_HANDOFF_SCHEMA_VERSION,
    RUNTIME_EVENT_SCHEMA_VERSION,
    SYSTEM_MANIFEST_SCHEMA_VERSION,
    load_artifact_manifest,
)
from ...services.artifact_storage import RUNTIME_ARTIFACT_PUBLICATION_SCHEMA_VERSION, STORAGE_REF_SCHEMA_VERSION
from ...services.dataset_repository import DATASET_STAGING_SCHEMA_VERSION, DATASET_STORAGE_REF_SCHEMA_VERSION
from ...services.dataset_repository import DatasetRepository
from ...services.model_catalog import ModelCatalogProvider
from ...services.users import UserContext
from ...schemas import EnvironmentSetupResponse, LeverValues, ModelRuntimeCatalogResponse, RunRequest, SystemManifestResponse
from ...settings import Settings

router = APIRouter()


@router.get("/", include_in_schema=False)
def root(request: Request):
    frontend_dir = getattr(request.app.state, "frontend_dir", None)
    if frontend_dir is not None:
        return RedirectResponse(url="/ui/", status_code=307)
    return {"ok": True, "message": "UI not available. Set EDIM_FRONTEND_DIR or add ./frontend."}


@router.get("/health")
def health():
    return {"ok": True}


def _provider_descriptor(provider: Any, *, boundary: str, local_default: str, cloud_target: str, notes: str = "") -> Dict[str, Any]:
    provider_name = provider.__class__.__name__ if provider is not None else local_default
    provider_module = provider.__class__.__module__ if provider is not None else ""
    return {
        "boundary": boundary,
        "current_provider": provider_name,
        "current_provider_module": provider_module,
        "local_default": local_default,
        "cloud_target": cloud_target,
        "replace_at": "create_app(...) provider injection",
        "notes": notes,
    }


def _strict_validation_for_profile(profile: str) -> bool:
    return str(profile or "").strip().lower() in {"analysis", "full"}


def _server_placeholder_policy(settings: Settings) -> bool:
    runtime_config = getattr(settings, "runtime_config", {}) or {}
    data_policy = runtime_config.get("data_policy") if isinstance(runtime_config, dict) else {}
    if isinstance(data_policy, dict) and "allow_placeholder_data" in data_policy:
        return bool(data_policy.get("allow_placeholder_data"))
    return True


def _public_validation_params(payload: Dict[str, Any], *, project_id: str) -> Dict[str, Any]:
    config = payload.get("configuration") if isinstance(payload.get("configuration"), dict) else payload
    scenario = config.get("scenario") if isinstance(config.get("scenario"), dict) else {}
    return {
        "project_id": project_id,
        "energy_scenario_key": str(scenario.get("energy_scenario_key") or config.get("energy_scenario_key") or "new_links"),
        "mrio_scenario_id": str(scenario.get("target_scenario_id") or scenario.get("mrio_scenario_id") or config.get("mrio_scenario_id") or "S2"),
        "target_year": int(scenario.get("target_year") or config.get("target_year") or 2030),
        "run_profile": str(config.get("run_profile") or "dev"),
    }


def _configuration_schema_from_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    engines = [str(value) for value in (manifest.get("supported_energy_model_engines") or [])]
    architectures = [str(value) for value in (manifest.get("supported_model_architectures") or [])]
    return {
        "schema_version": "public_run_configuration_schema",
        "required": ["model_architecture_id", "energy_model_engine", "scenario", "run_profile", "levers"],
        "fields": {
            "model_architecture_id": {"type": "enum", "options": architectures},
            "energy_model_engine": {"type": "enum", "options": engines},
            "scenario.energy_scenario_key": {"type": "string"},
            "scenario.target_scenario_id": {"type": "string"},
            "scenario.target_year": {"type": "integer"},
            "run_profile": {"type": "enum", "options": ["dev", "analysis", "full"]},
            "levers": {"type": "object"},
        },
        "backend_derived": [
            "project_id",
            "strict_validation",
            "allow_placeholder_data",
            "dataset_snapshot",
            "model_manifest",
            "artifact_policy",
            "queue_metadata",
        ],
    }


def _system_manifest_payload(
    request: Request,
    *,
    settings: Settings,
    job_manager: JobManager,
    dataset_repository: DatasetRepository,
    user: UserContext,
) -> dict[str, Any]:
    """Build the stable deployment manifest used by CI and platform checks."""
    manifest = job_manager.runtime_manifest()
    artifact_manifest = load_artifact_manifest(settings.runtime_config)
    dataset_manifest = dataset_repository.runtime_dataset_manifest(user_id=user.user_id)
    required_artifacts = {
        "request_bundle_json",
        "dataset_manifest_json",
        "model_manifest_json",
        "artifact_policy_json",
        "runtime_events_jsonl",
        "summary_json",
        "integrated_results_json",
        "results_csv",
    }
    artifact_ids = set(artifact_manifest.keys())
    diagnostics = [
        {
            "id": "model_manifest",
            "status": "ok" if manifest.get("model_id") else "error",
            "message": f"Model runtime manifest: {manifest.get('model_id', 'missing')} {manifest.get('model_version', '')}".strip(),
        },
        {
            "id": "dataset_manifest",
            "status": "ok" if dataset_manifest.get("schema_version") else "error",
            "message": f"Dataset manifest rows: {len(dataset_manifest.get('datasets') or [])}",
        },
        {
            "id": "artifact_manifest",
            "status": "ok" if required_artifacts.issubset(artifact_ids) else "error",
            "message": f"Artifact manifest entries: {len(artifact_ids)}",
            "missing_required": sorted(required_artifacts - artifact_ids),
        },
        {
            "id": "runtime_mode",
            "status": "ok",
            "message": f"Runtime mode: {settings.model_runtime_mode}",
        },
        {
            "id": "artifact_handoff_mode",
            "status": "ok",
            "message": f"Artifact handoff mode: {settings.runtime_artifact_handoff_mode}",
        },
        {
            "id": "dataset_staging_mode",
            "status": "ok",
            "message": f"Dataset staging mode: {settings.dataset_staging_mode}",
        },
    ]
    ok = all(str(row.get("status") or "") != "error" for row in diagnostics)
    return {
        "schema_version": SYSTEM_MANIFEST_SCHEMA_VERSION,
        "ok": ok,
        "app": {
            "name": "EDIM backend",
            "api_version": "0.1.0",
            "contract": "project_run_black_box_model_runtime",
        },
        "user_context": {
            "active_user_id": user.user_id,
            "auth_mode": user.auth_mode,
            "is_admin": user.is_admin,
            "production_replacement": "Replace get_current_user_context with Azure/session auth while preserving UserContext fields.",
        },
        "contracts": {
            "system_manifest": SYSTEM_MANIFEST_SCHEMA_VERSION,
            "model_run_bundle": MODEL_RUN_BUNDLE_SCHEMA_VERSION,
            "artifact_manifest": ARTIFACT_MANIFEST_SCHEMA_VERSION,
            "runtime_artifact_handoff": RUNTIME_ARTIFACT_HANDOFF_SCHEMA_VERSION,
            "runtime_artifact_publication": RUNTIME_ARTIFACT_PUBLICATION_SCHEMA_VERSION,
            "runtime_event": RUNTIME_EVENT_SCHEMA_VERSION,
            "execution_queue_message": EXECUTION_QUEUE_MESSAGE_SCHEMA_VERSION,
            "execution_retry_policy": EXECUTION_RETRY_POLICY_SCHEMA_VERSION,
            "execution_attempt": EXECUTION_ATTEMPT_SCHEMA_VERSION,
            "run_provenance": "edim_run_provenance",
            "dataset_staging": DATASET_STAGING_SCHEMA_VERSION,
            "dataset_storage_ref": DATASET_STORAGE_REF_SCHEMA_VERSION,
            "platform_storage_ref": STORAGE_REF_SCHEMA_VERSION,
        },
        "public_endpoints": {
            "session_and_projects": [
                "GET /api/session",
                "GET /api/projects",
                "POST /api/projects",
                "GET /api/projects/{project_id}",
                "PATCH /api/projects/{project_id}",
                "DELETE /api/projects/{project_id}",
            ],
            "runs": [
                "GET /api/projects/{project_id}/runs",
                "POST /api/projects/{project_id}/runs",
                "GET /api/projects/{project_id}/runs/{run_id}",
                "PATCH /api/projects/{project_id}/runs/{run_id}",
                "POST /api/projects/{project_id}/runs/{run_id}/submit",
                "POST /api/projects/{project_id}/runs/{run_id}/duplicate",
                "DELETE /api/projects/{project_id}/runs/{run_id}",
                "GET /api/runs",
                "GET /api/executions/{execution_id}/status",
                "POST /api/executions/{execution_id}/cancel",
                "GET /api/executions/{execution_id}/events",
            ],
            "artifacts_reports_exports": [
                "GET /api/runs/{run_id}/summary",
                "GET /api/runs/{run_id}/development",
                "GET /api/runs/{run_id}/integrated",
                "GET /api/runs/{run_id}/artifacts",
                "GET /api/runs/{run_id}/artifacts/{artifact_id}",
                "GET /api/runs/{run_id}/logs",
                "POST /api/runs/{run_id}/export",
                "GET /api/projects/{project_id}/reports",
                "POST /api/projects/{project_id}/reports",
                "GET /api/projects/{project_id}/reports/{report_id}",
                "GET /api/projects/{project_id}/reports/{report_id}/download",
                "GET /api/projects/{project_id}/reports/{report_id}/data",
                "GET /api/projects/{project_id}/exports",
                "POST /api/projects/{project_id}/exports",
                "GET /api/projects/{project_id}/exports/{export_id}",
                "GET /api/projects/{project_id}/exports/{export_id}/download",
            ],
            "datasets_and_runtime": [
                "GET /api/input-datasets",
                "POST /api/input-datasets",
                "PATCH /api/input-datasets/{dataset_id}",
                "POST /api/projects/{project_id}/datasets",
                "GET /api/input-datasets/{dataset_id}/download",
                "POST /api/input-datasets/{dataset_id}/upload",
                "GET /api/input-datasets/{dataset_id}/versions",
                "GET /api/input-datasets/{dataset_id}/versions/{version_id}/download",
                "POST /api/input-datasets/{dataset_id}/versions/{version_id}/activate",
                "DELETE /api/input-datasets/{dataset_id}/versions/{version_id}",
                "GET /api/scenarios",
                "GET /api/model-runtimes",
                "POST /api/projects/{project_id}/runs/validate",
                "GET /api/system/manifest",
            ],
            "operations_diagnostics": [
                "GET /api/projects/{project_id}/runs/{run_id}/diagnostics",
                "GET /api/environment-setup",
            ],
        },
        "provider_boundaries": {
            "auth": {
                "boundary": "get_current_user_context",
                "current_provider": "test_header",
                "local_default": "X-EDIM-User-Id local test users",
                "cloud_target": "Azure/session-backed auth provider returning UserContext",
                "replace_at": "backend/api_service/api/dependencies.py",
            },
            "platform_repository": _provider_descriptor(
                getattr(request.app.state, "platform_repository", None),
                boundary="PlatformRepository",
                local_default="SQLitePlatformRepository",
                cloud_target="Azure SQL/Cosmos-backed project/run/report/export repository",
            ),
            "dataset_repository": _provider_descriptor(
                getattr(request.app.state, "dataset_repository", None),
                boundary="DatasetRepository",
                local_default="LocalDatasetRepository",
                cloud_target="Database plus Blob/object-storage-backed dataset catalog and version repository",
            ),
            "artifact_storage": _provider_descriptor(
                getattr(request.app.state, "artifact_storage", None),
                boundary="ArtifactStorageService",
                local_default="LocalArtifactStorageService",
                cloud_target="Blob/object-storage-backed artifact, report, and export service",
            ),
            "event_store": _provider_descriptor(
                getattr(request.app.state, "event_store", None),
                boundary="EventStore",
                local_default="LocalEventStore",
                cloud_target="DB/blob/event-stream-backed runtime event store",
            ),
            "queue_worker": _provider_descriptor(
                getattr(request.app.state, "job_manager", None),
                boundary="JobManager / ExecutionQueue",
                local_default="JobManager + LocalExecutionQueue + SubprocessModelRuntime",
                cloud_target="Durable queue plus worker service using execution_queue_message and execution_attempt",
            ),
            "model_catalog": _provider_descriptor(
                getattr(request.app.state, "model_catalog_provider", None),
                boundary="ModelCatalogProvider",
                local_default="RuntimeCliModelCatalogProvider",
                cloud_target="Cached model-catalog provider backed by packaged runtime catalog outputs",
                notes="Owns scenario channels and architecture graph metadata served through /api/scenarios and /api/model-runtimes.",
            ),
        },
        "runtime": {
            "mode": settings.model_runtime_mode,
            "artifact_handoff_mode": settings.runtime_artifact_handoff_mode,
            "dataset_staging_mode": settings.dataset_staging_mode,
            "execution_retry_policy": job_manager.execution_retry_policy(),
            "model_manifest": manifest,
            "dataset_count": len(dataset_manifest.get("datasets") or []),
            "artifact_manifest_count": len(artifact_manifest),
            "required_artifacts": sorted(required_artifacts),
        },
        "storage": {
            "platform_store_backend": settings.platform_store_backend,
            "runtime_artifact_handoff_mode": settings.runtime_artifact_handoff_mode,
            "dataset_staging_mode": settings.dataset_staging_mode,
            "cloud_replacement_expected": settings.runtime_artifact_handoff_mode != "shared_filesystem"
            or settings.dataset_staging_mode == "object_reference"
            or settings.platform_store_backend not in {"sqlite", "sqlite3"},
        },
        "diagnostics": diagnostics,
        "operational_notes": [
            "Keep frontend downloads descriptor-based; do not infer filesystem paths.",
            "Treat model runtime as a black box consuming model_run_bundle_v1.",
            "Persist project run records before enqueueing execution_queue_message.",
            "Record execution_attempt whenever a worker accepts, heartbeats, cancels, or finishes an attempt.",
            "Run backend/tools/backend_handoff_smoke.py and compare this manifest in deployment CI.",
        ],
    }


@router.get("/api/system/manifest", response_model=SystemManifestResponse)
def get_system_manifest(
    request: Request,
    settings: Settings = Depends(get_settings),
    job_manager: JobManager = Depends(get_job_manager),
    dataset_repository: DatasetRepository = Depends(get_dataset_repository),
    user: UserContext = Depends(get_current_user_context),
):
    """Return the stable system manifest used by CI and platform deployment checks."""
    return _system_manifest_payload(
        request,
        settings=settings,
        job_manager=job_manager,
        dataset_repository=dataset_repository,
        user=user,
    )


@router.get("/api/model-runtimes", response_model=ModelRuntimeCatalogResponse)
def list_model_runtimes(
    settings: Settings = Depends(get_settings),
    job_manager: JobManager = Depends(get_job_manager),
    dataset_repository: DatasetRepository = Depends(get_dataset_repository),
    catalog_provider: ModelCatalogProvider = Depends(get_model_catalog_provider),
    user: UserContext = Depends(get_current_user_context),
):
    manifest = job_manager.runtime_manifest()
    dataset_manifest = dataset_repository.runtime_dataset_manifest(user_id=user.user_id)
    architecture_catalog = catalog_provider.architecture_catalog(settings=settings, manifest=manifest)
    try:
        scenario_catalog = catalog_provider.scenario_catalog(settings=settings, manifest=manifest)
    except Exception as exc:
        scenario_catalog = {
            "schema_version": "model_scenario_catalog",
            "generated_at_utc": "",
            "model_modules": manifest.get("modules") or [],
            "module_configurations": [],
            "scenario_channels": [],
            "defaults": {},
            "metadata": {
                "catalog_status": "unavailable",
                "error": str(exc),
            },
        }
    supported_architectures = [str(value) for value in (manifest.get("supported_model_architectures") or [])]
    declared_outputs = [{"artifact_id": str(value), "label": str(value).replace("_", " ").title()} for value in (manifest.get("declared_outputs") or [])]
    return {
        "default_model_id": manifest.get("model_id", ""),
        "runtime_mode": settings.model_runtime_mode,
        "artifact_handoff_mode": getattr(settings, "runtime_artifact_handoff_mode", "shared_filesystem"),
        "dataset_staging_mode": getattr(settings, "dataset_staging_mode", "copy_to_run"),
        "execution_retry_policy": job_manager.execution_retry_policy(),
        "runtimes": [manifest],
        "configuration_schema": _configuration_schema_from_manifest(manifest),
        "architecture_catalog": architecture_catalog,
        "scenario_catalog": scenario_catalog,
        "model_architectures": architecture_catalog.get("architectures")
        if isinstance(architecture_catalog.get("architectures"), list)
        else [{"id": value, "label": value.replace("-", " ").title()} for value in supported_architectures],
        "declared_outputs": declared_outputs,
        "dataset_manifest_path": str(settings.dataset_manifest_path or ""),
        "datasets": dataset_manifest.get("datasets") or [],
    }


@router.get("/api/environment-setup", response_model=EnvironmentSetupResponse)
def get_environment_setup(
    energy_scenario_key: str = "",
    mrio_scenario_id: str = "",
    target_year: int = 2030,
    run_profile: str = "dev",
    project_id: str = "default",
    strict_validation: bool | None = None,
    allow_placeholder_data: bool | None = None,
    settings: Settings = Depends(get_settings),
    job_manager: JobManager = Depends(get_job_manager),
    dataset_repository: DatasetRepository = Depends(get_dataset_repository),
    user: UserContext = Depends(get_current_user_context),
):
    effective_strict_validation = bool(strict_validation) if strict_validation is not None else _strict_validation_for_profile(run_profile)
    effective_allow_placeholder_data = _server_placeholder_policy(settings) if allow_placeholder_data is None else bool(allow_placeholder_data)
    queue_stats = job_manager.runtime_stats()
    manifest = job_manager.runtime_manifest()
    dataset_rows = list((dataset_repository.runtime_dataset_manifest(user_id=user.user_id).get("datasets") or []))
    checks = [
        {
            "id": "model_runtime_manifest",
            "type": "runtime",
            "status": "ok" if manifest.get("model_id") else "error",
            "message": f"Runtime manifest loaded: {manifest.get('model_id', 'unknown')} {manifest.get('model_version', '')}".strip(),
        },
        {
            "id": "queue_capacity",
            "type": "runtime",
            "status": "ok" if queue_stats.get("active_jobs", 0) < queue_stats.get("capacity", 1) else "error",
            "message": f"{queue_stats.get('active_jobs', 0)}/{queue_stats.get('capacity', 1)} active execution slots used.",
        },
        {
            "id": "dataset_staging_mode",
            "type": "storage",
            "status": "ok",
            "message": f"Dataset staging mode: {getattr(settings, 'dataset_staging_mode', 'copy_to_run')}",
        },
    ]
    platform_backend = str(getattr(settings, "platform_store_backend", "sqlite") or "sqlite").strip().lower()
    import os as _os
    database_url = _os.getenv("EDIM_DATABASE_URL", "").strip()
    if database_url:
        platform_backend = "postgresql"
    platform_path = getattr(settings, "platform_sqlite_path", None)
    sqlite_path = Path(str(platform_path or settings.runs_dir.parent / "platform" / "platform.sqlite3"))
    if database_url:
        storage_ok = True
        store_label = "PostgreSQL"
        store_path = database_url.split("@")[-1] if "@" in database_url else database_url
    else:
        storage_ok = platform_backend in {"sqlite", "sqlite3"} and (sqlite_path.exists() or sqlite_path.parent.exists())
        store_label = "SQLite"
        store_path = str(sqlite_path)
    checks.append(
        {
            "id": "platform_metadata_store",
            "type": "storage",
            "status": "ok" if storage_ok else "error",
            "message": f"Platform metadata store: {store_label} at {store_path}",
            "path": str(sqlite_path) if not database_url else store_path,
        }
    )
    placeholder_datasets = []
    for row in dataset_rows:
        path = Path(str(row.get("path", ""))).expanduser()
        exists = bool(row.get("path") and path.exists())
        dataset_id = str(row.get("id", ""))
        is_placeholder = "placeholder" in dataset_id or "placeholder" in str(row.get("label", "")).lower()
        if is_placeholder:
            placeholder_datasets.append(dataset_id)
        status = "ok" if exists else ("error" if row.get("required") else "warning")
        checks.append(
            {
                "id": dataset_id,
                "type": "dataset",
                "status": status,
                "message": f"{row.get('label', dataset_id)} {'found' if exists else 'missing'}",
                "path": str(row.get("path", "")),
                "required": bool(row.get("required", False)),
                "placeholder": is_placeholder,
                "active_version_id": row.get("active_version_id", ""),
            }
        )
    try:
        runtime_preflight = job_manager.preflight(
            RunRequest(
                project_id=project_id,
                energy_scenario_key=energy_scenario_key or "new_links",
                mrio_scenario_id=mrio_scenario_id or "S2",
                target_year=target_year,
                run_profile=run_profile,  # type: ignore[arg-type]
                strict_validation=effective_strict_validation,
                allow_placeholder_data=effective_allow_placeholder_data,
                levers=LeverValues(),
            ),
            user_id=user.user_id,
        )
    except Exception as exc:
        runtime_preflight = {"ok": False, "message": str(exc), "payload": {}}
    if not bool(runtime_preflight.get("ok", False)):
        checks.append({"id": "runtime_preflight", "type": "runtime", "status": "error", "message": str(runtime_preflight.get("message", "Runtime preflight failed."))})
    else:
        checks.append({"id": "runtime_preflight", "type": "runtime", "status": "ok", "message": str(runtime_preflight.get("message", "Runtime preflight passed."))})
    counts: dict[str, int] = {}
    for check in checks:
        key = str(check.get("status", "other"))
        counts[key] = counts.get(key, 0) + 1
    return {
        "schema_version": "environment_setup_v2",
        "ok": counts.get("error", 0) == 0,
        "user_id": user.user_id,
        "queue": queue_stats,
        "model_runtime": manifest,
        "runtime_preflight": runtime_preflight,
        "checks": checks,
        "counts": counts,
        "validation": {
            "strict_validation": effective_strict_validation,
            "allow_placeholder_data": effective_allow_placeholder_data,
            "placeholder_datasets": placeholder_datasets,
            "message": f"{counts.get('ok', 0)}/{len(checks)} checks passed cleanly",
        },
    }


@router.post("/api/projects/{project_id}/runs/validate", response_model=EnvironmentSetupResponse)
def validate_project_run_configuration(
    project_id: str,
    payload: Dict[str, Any],
    settings: Settings = Depends(get_settings),
    job_manager: JobManager = Depends(get_job_manager),
    dataset_repository: DatasetRepository = Depends(get_dataset_repository),
    user: UserContext = Depends(get_current_user_context),
):
    params = _public_validation_params(payload or {}, project_id=project_id)
    return get_environment_setup(
        energy_scenario_key=params["energy_scenario_key"],
        mrio_scenario_id=params["mrio_scenario_id"],
        target_year=params["target_year"],
        run_profile=params["run_profile"],
        project_id=params["project_id"],
        strict_validation=None,
        allow_placeholder_data=None,
        settings=settings,
        job_manager=job_manager,
        dataset_repository=dataset_repository,
        user=user,
    )

__all__ = ["router"]
