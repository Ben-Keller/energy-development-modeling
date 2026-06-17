from __future__ import annotations

import shutil
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from ..dependencies import get_artifact_storage_service, get_current_user_context, get_event_store, get_job_manager, get_platform_repository, get_settings
from ...jobs import JobManager, JobQueueFullError
from ...runtime import EventStore
from ...schemas import (
    RunArtifacts,
    PublicRunCreateRequest,
    PublicRunConfiguration,
    PublicProjectRunResponse,
    PublicRunPatchRequest,
    PublicRunScenarioSelection,
    ProjectRunListResponse,
    ProjectRunResponse,
    RunArtifactListResponse,
    RunEventsResponse,
    RunExecutionInfo,
    RunListResponse,
    RunRequest,
    RunStatusView,
    RUN_STATUSES,
    RunSummary,
    RunSubmitResponse,
)
from ...services.artifact_storage import ArtifactStorageService
from ...services.platform_repository import PlatformRepository
from ...services.users import UserContext
from ...settings import Settings

router = APIRouter()


def _server_placeholder_policy(settings: Settings | None) -> bool:
    if settings is None:
        return True
    runtime_config = getattr(settings, "runtime_config", {}) or {}
    data_policy = runtime_config.get("data_policy") if isinstance(runtime_config, dict) else {}
    if isinstance(data_policy, dict) and "allow_placeholder_data" in data_policy:
        return bool(data_policy.get("allow_placeholder_data"))
    return True


def _strict_validation_for_profile(profile: str) -> bool:
    return str(profile or "").strip().lower() in {"analysis", "full"}


def _normalize_request_for_project(req: RunRequest | PublicRunCreateRequest | Dict[str, Any], project_id: str, *, settings: Settings | None = None) -> RunRequest:
    payload = req.model_dump(mode="json") if hasattr(req, "model_dump") else dict(req)
    scenario = payload.get("scenario")
    if isinstance(scenario, dict):
        payload["energy_scenario_key"] = scenario.get("energy_scenario_key") or payload.get("energy_scenario_key")
        payload["mrio_scenario_id"] = scenario.get("target_scenario_id") or scenario.get("mrio_scenario_id") or payload.get("mrio_scenario_id")
        payload["target_year"] = scenario.get("target_year") or payload.get("target_year")
        payload.pop("scenario", None)
    profile = str(payload.get("run_profile") or "dev").strip().lower() or "dev"
    payload["run_profile"] = profile
    payload.setdefault("model_architecture_id", "energy-development")
    payload.setdefault("energy_model_engine", "calliope")
    payload.setdefault("levers", {})
    payload.setdefault("run_name", "")
    strict_validation = payload.get("strict_validation")
    placeholder_policy = payload.get("allow_placeholder_data")
    payload["strict_validation"] = _strict_validation_for_profile(profile) if strict_validation is None else bool(strict_validation)
    payload["allow_placeholder_data"] = _server_placeholder_policy(settings) if placeholder_policy is None else bool(placeholder_policy)
    payload["project_id"] = project_id
    return RunRequest(**payload)


def _public_configuration_from_request(request_payload: Dict[str, Any], *, run_name: str = "") -> PublicRunConfiguration:
    return PublicRunConfiguration(
        run_name=str(run_name or request_payload.get("run_name") or ""),
        model_architecture_id=str(request_payload.get("model_architecture_id") or "energy-development"),
        energy_model_engine=str(request_payload.get("energy_model_engine") or "calliope"),
        scenario=PublicRunScenarioSelection(
            energy_scenario_key=str(request_payload.get("energy_scenario_key") or ""),
            target_scenario_id=str(request_payload.get("mrio_scenario_id") or ""),
            target_year=request_payload.get("target_year"),
        ),
        run_profile=str(request_payload.get("run_profile") or "dev"),
        levers=dict(request_payload.get("levers") or {}),
    )


def _public_run_configuration(record: Dict[str, Any]) -> PublicRunConfiguration:
    request_payload = record.get("request") if isinstance(record.get("request"), dict) else {}
    return _public_configuration_from_request(request_payload, run_name=str(record.get("run_name") or ""))


def _public_project_run_list_item(record: Dict[str, Any]) -> Dict[str, Any]:
    status = _normalized_status(record)
    run_id = str(record.get("run_id") or "")
    return {
        "run_id": run_id,
        "execution_id": str(record.get("execution_id") or ""),
        "project_id": str(record.get("project_id") or ""),
        "project_run_number": int(record.get("project_run_number") or 0),
        "run_name": str(record.get("run_name") or ""),
        "status": status,
        "stage": str(record.get("stage") or status),
        "progress": float(record.get("progress") or 0.0),
        "message": str(record.get("message") or ""),
        "created_at": str(record.get("created_at") or ""),
        "updated_at": str(record.get("updated_at") or ""),
        "started_at": record.get("started_at"),
        "finished_at": record.get("finished_at"),
        "queue_position": record.get("queue_position"),
        "cancellation_requested": bool(record.get("cancellation_requested")),
        "error": record.get("error"),
        "artifacts": (
            RunArtifacts(
                run_id=run_id,
                summary_url=f"/api/runs/{run_id}/summary",
                csv_url=f"/api/runs/{run_id}/artifacts/results_csv",
            ).model_dump(mode="json")
            if run_id and status == "succeeded"
            else None
        ),
        "summary_available": bool(record.get("summary_available")),
        "source_run_id": str(record.get("source_run_id") or ""),
        "configuration": _public_run_configuration(record).model_dump(mode="json"),
    }


def _status_view_from_execution_info(info: RunExecutionInfo) -> RunStatusView:
    request_payload = info.request.model_dump(mode="json") if isinstance(info.request, RunRequest) else {}
    return RunStatusView(
        run_id=info.run_id or "",
        execution_id=info.execution_id,
        project_id=str(request_payload.get("project_id") or ""),
        project_run_number=int(info.project_run_number or 0),
        run_name=str(request_payload.get("run_name") or ""),
        status=info.status,
        stage=info.stage or str(info.status),
        progress=float(info.progress or 0.0),
        message=info.message or "",
        created_at=info.created_at,
        updated_at=info.updated_at,
        started_at=info.started_at,
        finished_at=info.finished_at,
        queue_position=info.queue_position,
        cancellation_requested=bool(info.cancellation_requested),
        error=info.error,
        artifacts=info.artifacts,
        summary_available=bool(info.summary),
        configuration=_public_configuration_from_request(request_payload),
    )


def _normalized_status(record: Dict[str, Any]) -> str:
    status = str(record.get("status") or "draft").strip().lower()
    return status if status in RUN_STATUSES else "failed"


def _require_draft_run(record: Dict[str, Any], *, action: str) -> None:
    status = _normalized_status(record)
    if status != "draft":
        raise HTTPException(status_code=409, detail=f"Cannot {action} a run with status '{status}'. Duplicate it to create a new draft.")


@router.get("/api/runs", response_model=RunListResponse)
def list_runs(limit: int = 50, job_manager: JobManager = Depends(get_job_manager), user: UserContext = Depends(get_current_user_context)):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")
    runs = job_manager.list(limit=limit, user_id=user.user_id)
    return RunListResponse(runs=[_status_view_from_execution_info(run) for run in runs])


@router.get("/api/executions/{execution_id}/status", response_model=RunStatusView)
def get_run_status(
    execution_id: str,
    job_manager: JobManager = Depends(get_job_manager),
    repository: PlatformRepository = Depends(get_platform_repository),
    storage: ArtifactStorageService = Depends(get_artifact_storage_service),
    user: UserContext = Depends(get_current_user_context),
):
    try:
        return _status_view_from_execution_info(job_manager.get(execution_id, user_id=user.user_id))
    except KeyError as exc:
        try:
            record = repository.get_run_record_by_execution(execution_id, user_id=user.user_id)
        except Exception:
            raise HTTPException(status_code=404, detail="Run not found") from exc
        return _status_view_from_execution_info(_execution_info_from_record(record, storage=storage))


@router.post("/api/executions/{execution_id}/cancel", response_model=RunStatusView)
def cancel_run(
    execution_id: str,
    settings: Settings = Depends(get_settings),
    job_manager: JobManager = Depends(get_job_manager),
    repository: PlatformRepository = Depends(get_platform_repository),
    storage: ArtifactStorageService = Depends(get_artifact_storage_service),
    user: UserContext = Depends(get_current_user_context),
):
    try:
        return _status_view_from_execution_info(job_manager.cancel(execution_id, user_id=user.user_id))
    except KeyError as exc:
        try:
            record = repository.get_run_record_by_execution(execution_id, user_id=user.user_id)
        except Exception:
            raise HTTPException(status_code=404, detail="Run not found") from exc
        if str(record.get("status") or "").strip().lower() in {"queued", "running"}:
            _clear_cancelled_run_files(settings, run_id=str(record.get("run_id") or ""), execution_id=execution_id)
            record = repository.update_run_record(
                str(record.get("run_id") or ""),
                {
                    "execution_id": "",
                    "status": "draft",
                    "stage": "draft",
                    "progress": 0.0,
                    "message": "Run cancelled; draft restored.",
                    "error": None,
                    "started_at": None,
                    "finished_at": None,
                    "execution_queue_message": {},
                    "execution_attempts": [],
                    "cancellation_requested": False,
                    "worker_id": "",
                    "dataset_snapshot": {},
                    "artifact_catalog": [],
                    "summary_available": False,
                },
                user_id=user.user_id,
            )
        return _status_view_from_execution_info(_execution_info_from_record(record, storage=storage))


@router.get("/api/executions/{execution_id}/events", response_model=RunEventsResponse)
def get_run_events(
    execution_id: str,
    job_manager: JobManager = Depends(get_job_manager),
    repository: PlatformRepository = Depends(get_platform_repository),
    event_store: EventStore = Depends(get_event_store),
    user: UserContext = Depends(get_current_user_context),
):
    try:
        job_manager.get(execution_id, user_id=user.user_id)
    except KeyError as exc:
        try:
            repository.get_run_record_by_execution(execution_id, user_id=user.user_id)
        except Exception:
            raise HTTPException(status_code=404, detail="Run not found") from exc
    return {"execution_id": execution_id, "events": event_store.read_events(execution_id)}


def _summary_payload(run_id: str, storage: ArtifactStorageService) -> dict:
    return storage.read_json_artifact(run_id, "summary_json")


def _development_payload(run_id: str, storage: ArtifactStorageService) -> dict:
    return storage.read_json_artifact(run_id, "development_impacts_json")


def _integrated_payload(run_id: str, storage: ArtifactStorageService) -> dict:
    return storage.read_json_artifact(run_id, "integrated_results_json")


def _authorize_run_access(run_id: str, repository: PlatformRepository, user_id: str) -> None:
    repository.get_run_record(run_id, user_id=user_id)


def _resolved_project_id(repository: PlatformRepository, user_id: str, project_id: str) -> str:
    return str(repository.get_project(user_id=user_id, project_id=project_id).get("project_id") or project_id)


def _clear_cancelled_run_files(settings: Settings, *, run_id: str, execution_id: str) -> None:
    roots = {
        settings.runs_dir.resolve(),
        (settings.runs_dir / "_queued").resolve(),
    }
    for path in (
        settings.runs_dir / str(run_id or ""),
        settings.runs_dir / "_queued" / str(execution_id or ""),
    ):
        if not path.exists() or not path.is_dir():
            continue
        try:
            if path.parent.resolve() in roots:
                shutil.rmtree(path)
        except Exception:
            pass


def _execution_info_from_record(record: Dict[str, Any], *, storage: ArtifactStorageService | None = None) -> RunExecutionInfo:
    """Rehydrate public execution status from persisted project-run metadata.

    The local queue keeps active state in memory, but project run records are
    the durable source for history, compare, reports, and restart recovery.
    Cloud deployments should make this path the primary status source.
    """
    request_payload = record.get("request") if isinstance(record.get("request"), dict) else {}
    req = _normalize_request_for_project(request_payload, str(record.get("project_id") or "default"))
    run_id = str(record.get("run_id") or "")
    execution_id = str(record.get("execution_id") or run_id)
    status = str(record.get("status") or "draft").strip().lower()
    if status not in RUN_STATUSES:
        status = "failed"
    summary_model = None
    if storage is not None and run_id and bool(record.get("summary_available")):
        try:
            summary_model = RunSummary(**storage.read_json_artifact(run_id, "summary_json"))
        except Exception:
            summary_model = None
    artifacts = (
        RunArtifacts(
            run_id=run_id,
            summary_url=f"/api/runs/{run_id}/summary",
            csv_url=f"/api/runs/{run_id}/artifacts/results_csv",
        )
        if run_id and status == "succeeded"
        else None
    )
    return RunExecutionInfo(
        execution_id=execution_id,
        run_id=run_id or None,
        project_run_number=int(record.get("project_run_number") or 0),
        status=status,  # type: ignore[arg-type]
        progress=max(0.0, min(1.0, float(record.get("progress") or 0.0))),
        stage=str(record.get("stage") or status),
        message=str(record.get("message") or ""),
        queue_position=None,
        created_at=str(record.get("created_at") or ""),
        started_at=record.get("started_at"),
        finished_at=record.get("finished_at"),
        updated_at=record.get("updated_at"),
        worker_pid=None,
        worker_id=str(record.get("worker_id") or ""),
        cancellation_requested=bool(record.get("cancellation_requested")),
        execution_queue_message=dict(record.get("execution_queue_message") or {}),
        execution_attempts=list(record.get("execution_attempts") or []),
        error=record.get("error"),
        request=req,
        artifacts=artifacts,
        summary=summary_model,
        run_artifacts=list(record.get("artifact_catalog") or []),
    )


@router.get("/api/runs/{run_id}/summary")
def get_run_summary(run_id: str, storage: ArtifactStorageService = Depends(get_artifact_storage_service), repository: PlatformRepository = Depends(get_platform_repository), user: UserContext = Depends(get_current_user_context)):
    _authorize_run_access(run_id, repository, user.user_id)
    return _summary_payload(run_id, storage)


@router.get("/api/runs/{run_id}/development")
def get_run_development(run_id: str, storage: ArtifactStorageService = Depends(get_artifact_storage_service), repository: PlatformRepository = Depends(get_platform_repository), user: UserContext = Depends(get_current_user_context)):
    _authorize_run_access(run_id, repository, user.user_id)
    return _development_payload(run_id, storage)


@router.get("/api/runs/{run_id}/integrated")
def get_run_integrated(run_id: str, storage: ArtifactStorageService = Depends(get_artifact_storage_service), repository: PlatformRepository = Depends(get_platform_repository), user: UserContext = Depends(get_current_user_context)):
    _authorize_run_access(run_id, repository, user.user_id)
    return _integrated_payload(run_id, storage)


@router.get("/api/runs/{run_id}/artifacts", response_model=RunArtifactListResponse)
def list_run_artifacts(run_id: str, storage: ArtifactStorageService = Depends(get_artifact_storage_service), repository: PlatformRepository = Depends(get_platform_repository), user: UserContext = Depends(get_current_user_context)):
    _authorize_run_access(run_id, repository, user.user_id)
    summary = _summary_payload(run_id, storage)
    return {"run_id": run_id, "artifacts": summary.get("artifact_catalog") or []}


@router.get("/api/runs/{run_id}/artifacts/{artifact_id}")
def download_run_artifact_by_id(run_id: str, artifact_id: str, storage: ArtifactStorageService = Depends(get_artifact_storage_service), repository: PlatformRepository = Depends(get_platform_repository), user: UserContext = Depends(get_current_user_context)):
    _authorize_run_access(run_id, repository, user.user_id)
    return storage.download_response_for_artifact(run_id, artifact_id)


@router.get("/api/projects/{project_id}/runs", response_model=ProjectRunListResponse)
def list_project_runs(
    project_id: str,
    include_drafts: bool = True,
    limit: int = 200,
    repository: PlatformRepository = Depends(get_platform_repository),
    user: UserContext = Depends(get_current_user_context),
):
    actual_project_id = _resolved_project_id(repository, user.user_id, project_id)
    rows = repository.list_run_records(project_id=actual_project_id, user_id=user.user_id, include_drafts=include_drafts, limit=limit)
    rows = [row for row in rows if str(row.get("status") or "").strip().lower() != "cancelled"]
    return {
        "project_id": actual_project_id,
        "runs": [_public_project_run_list_item(row) for row in rows],
    }


@router.post("/api/projects/{project_id}/runs", response_model=PublicProjectRunResponse)
def create_project_run_draft(
    project_id: str,
    req: PublicRunCreateRequest,
    settings: Settings = Depends(get_settings),
    repository: PlatformRepository = Depends(get_platform_repository),
    user: UserContext = Depends(get_current_user_context),
):
    actual_project_id = _resolved_project_id(repository, user.user_id, project_id)
    normalized = _normalize_request_for_project(req, actual_project_id, settings=settings)
    record = repository.create_run_record(
        project_id=actual_project_id,
        request_payload=normalized.model_dump(mode="json"),
        status="draft",
        user_id=user.user_id,
    )
    return {"run": _public_project_run_list_item(record)}


@router.get("/api/projects/{project_id}/runs/{run_id}", response_model=PublicProjectRunResponse)
def get_project_run(
    project_id: str,
    run_id: str,
    repository: PlatformRepository = Depends(get_platform_repository),
    user: UserContext = Depends(get_current_user_context),
):
    actual_project_id = _resolved_project_id(repository, user.user_id, project_id)
    record = repository.get_run_record(run_id, user_id=user.user_id)
    if record.get("project_id") != actual_project_id:
        raise HTTPException(status_code=404, detail="Run record not found in project.")
    return {"run": _public_project_run_list_item(record)}


@router.get("/api/projects/{project_id}/runs/{run_id}/diagnostics", response_model=ProjectRunResponse)
def get_project_run_diagnostics(
    project_id: str,
    run_id: str,
    repository: PlatformRepository = Depends(get_platform_repository),
    user: UserContext = Depends(get_current_user_context),
):
    actual_project_id = _resolved_project_id(repository, user.user_id, project_id)
    record = repository.get_run_record(run_id, user_id=user.user_id)
    if record.get("project_id") != actual_project_id:
        raise HTTPException(status_code=404, detail="Run record not found in project.")
    return {"run": record}


@router.patch("/api/projects/{project_id}/runs/{run_id}", response_model=PublicProjectRunResponse)
def patch_project_run(
    project_id: str,
    run_id: str,
    payload: PublicRunPatchRequest,
    settings: Settings = Depends(get_settings),
    repository: PlatformRepository = Depends(get_platform_repository),
    user: UserContext = Depends(get_current_user_context),
):
    actual_project_id = _resolved_project_id(repository, user.user_id, project_id)
    current = repository.get_run_record(run_id, user_id=user.user_id)
    if current.get("project_id") != actual_project_id:
        raise HTTPException(status_code=404, detail="Run record not found in project.")
    updates: Dict[str, Any] = {}
    if payload.request is not None or payload.run_name is not None:
        _require_draft_run(current, action="edit")
    if payload.request is not None:
        normalized = _normalize_request_for_project(payload.request, actual_project_id, settings=settings)
        updates["request"] = normalized.model_dump(mode="json")
        updates["run_name"] = normalized.run_name
    if payload.run_name is not None:
        updates["run_name"] = payload.run_name
        request_payload = dict(updates.get("request") or current.get("request") or {})
        request_payload["run_name"] = payload.run_name
        updates["request"] = _normalize_request_for_project(request_payload, actual_project_id, settings=settings).model_dump(mode="json")
    if not updates:
        return {"run": _public_project_run_list_item(current)}
    return {"run": _public_project_run_list_item(repository.update_run_record(run_id, updates, user_id=user.user_id))}


@router.post("/api/projects/{project_id}/runs/{run_id}/submit", response_model=RunSubmitResponse)
def submit_project_run(
    project_id: str,
    run_id: str,
    repository: PlatformRepository = Depends(get_platform_repository),
    job_manager: JobManager = Depends(get_job_manager),
    user: UserContext = Depends(get_current_user_context),
):
    actual_project_id = _resolved_project_id(repository, user.user_id, project_id)
    record = repository.get_run_record(run_id, user_id=user.user_id)
    if record.get("project_id") != actual_project_id:
        raise HTTPException(status_code=404, detail="Run record not found in project.")
    _require_draft_run(record, action="submit")
    req = _normalize_request_for_project(record.get("request") or {}, actual_project_id)
    try:
        job = job_manager.submit(req, run_id=run_id, user_id=user.user_id)
    except JobQueueFullError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RunSubmitResponse(run=_status_view_from_execution_info(job))


@router.post("/api/projects/{project_id}/runs/{run_id}/duplicate", response_model=PublicProjectRunResponse)
def duplicate_project_run(
    project_id: str,
    run_id: str,
    repository: PlatformRepository = Depends(get_platform_repository),
    user: UserContext = Depends(get_current_user_context),
):
    actual_project_id = _resolved_project_id(repository, user.user_id, project_id)
    source = repository.get_run_record(run_id, user_id=user.user_id)
    if source.get("project_id") != actual_project_id:
        raise HTTPException(status_code=404, detail="Run record not found in project.")
    return {"run": _public_project_run_list_item(repository.duplicate_run_record(run_id, user_id=user.user_id))}


@router.delete("/api/projects/{project_id}/runs/{run_id}")
def delete_project_run(
    project_id: str,
    run_id: str,
    delete_files: bool = False,
    repository: PlatformRepository = Depends(get_platform_repository),
    user: UserContext = Depends(get_current_user_context),
):
    actual_project_id = _resolved_project_id(repository, user.user_id, project_id)
    source = repository.get_run_record(run_id, user_id=user.user_id)
    if source.get("project_id") != actual_project_id:
        raise HTTPException(status_code=404, detail="Run record not found in project.")
    if _normalized_status(source) in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="Cancel the active execution before deleting this run.")
    return repository.delete_run_record(run_id, user_id=user.user_id, delete_files=delete_files)


@router.get("/api/runs/{run_id}/logs")
def get_run_logs(
    run_id: str,
    repository: PlatformRepository = Depends(get_platform_repository),
    event_store: EventStore = Depends(get_event_store),
    user: UserContext = Depends(get_current_user_context),
):
    record = repository.get_run_record(run_id, user_id=user.user_id)
    execution_id = str(record.get("execution_id") or "")
    events = event_store.read_events(execution_id) if execution_id else []
    status = _normalized_status(record)
    return {
        "run_id": run_id,
        "execution_id": execution_id,
        "status": status,
        "stage": str(record.get("stage") or status),
        "progress": max(0.0, min(1.0, float(record.get("progress") or 0.0))),
        "message": str(record.get("message") or ""),
        "events": events,
    }


@router.post("/api/runs/{run_id}/export")
def export_single_run(run_id: str, repository: PlatformRepository = Depends(get_platform_repository), user: UserContext = Depends(get_current_user_context)):
    return {"export": repository.create_run_export(run_id=run_id, user_id=user.user_id)}
