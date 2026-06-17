from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from ..dependencies import get_artifact_storage_service, get_current_user_context, get_platform_repository
from ...schemas import (
    ExportListResponse,
    ExportResponse,
    ProjectListResponse,
    ProjectResponse,
    ReportListResponse,
    ReportResponse,
    SessionResponse,
)
from ...services.artifact_storage import ArtifactStorageService
from ...services.platform_repository import PlatformRepository
from ...services.users import UserContext, list_test_users

router = APIRouter()


class ProjectPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="Untitled project", max_length=200)
    geography: str = Field(default="", max_length=120)
    project_type: str = Field(default="energy-development", max_length=80)
    model_architecture_id: str = Field(default="energy-development", max_length=80)
    scenario_label: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=2000)


class ProjectPatchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    geography: str | None = Field(default=None, max_length=120)
    project_type: str | None = Field(default=None, max_length=80)
    model_architecture_id: str | None = Field(default=None, max_length=80)
    scenario_label: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    status: str | None = Field(default=None, max_length=50)


class ReportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_ids: list[str] = Field(default_factory=list)
    report_type: str = Field(default="project_summary", max_length=80)
    options: Dict[str, Any] = Field(default_factory=dict)


class ExportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_ids: list[str] = Field(default_factory=list)
    include_reports: bool = True


@router.get("/api/session", response_model=SessionResponse)
def get_session(user: UserContext = Depends(get_current_user_context)):
    return {
        "authenticated": True,
        "auth_mode": user.auth_mode,
        "user": user.to_dict(),
        "available_users": list_test_users(),
    }


@router.get("/api/projects", response_model=ProjectListResponse)
def get_projects(repository: PlatformRepository = Depends(get_platform_repository), user: UserContext = Depends(get_current_user_context)):
    return {"user_id": user.user_id, "projects": repository.list_projects(user_id=user.user_id)}


def _resolved_project_id(repository: PlatformRepository, user_id: str, project_id: str) -> str:
    return str(repository.get_project(user_id=user_id, project_id=project_id).get("project_id") or project_id)


@router.post("/api/projects", response_model=ProjectResponse)
def post_project(payload: ProjectPayload, repository: PlatformRepository = Depends(get_platform_repository), user: UserContext = Depends(get_current_user_context)):
    return {"project": repository.create_project(user_id=user.user_id, payload=payload.model_dump())}


@router.get("/api/projects/{project_id}", response_model=ProjectResponse)
def get_project_by_id(project_id: str, repository: PlatformRepository = Depends(get_platform_repository), user: UserContext = Depends(get_current_user_context)):
    return {"project": repository.get_project(user_id=user.user_id, project_id=project_id)}


@router.patch("/api/projects/{project_id}", response_model=ProjectResponse)
def patch_project(project_id: str, payload: ProjectPatchPayload, repository: PlatformRepository = Depends(get_platform_repository), user: UserContext = Depends(get_current_user_context)):
    clean_payload: Dict[str, Any] = {key: value for key, value in payload.model_dump().items() if value is not None}
    return {"project": repository.update_project(user_id=user.user_id, project_id=project_id, payload=clean_payload)}


@router.delete("/api/projects/{project_id}")
def remove_project(
    project_id: str,
    delete_files: bool = Query(default=False),
    repository: PlatformRepository = Depends(get_platform_repository),
    user: UserContext = Depends(get_current_user_context),
):
    return repository.delete_project(user_id=user.user_id, project_id=project_id, delete_files=delete_files)


@router.get("/api/projects/{project_id}/reports", response_model=ReportListResponse)
def get_project_reports(project_id: str, repository: PlatformRepository = Depends(get_platform_repository), user: UserContext = Depends(get_current_user_context)):
    actual_project_id = _resolved_project_id(repository, user.user_id, project_id)
    return {"project_id": actual_project_id, "reports": repository.list_reports(project_id=actual_project_id, user_id=user.user_id)}


@router.post("/api/projects/{project_id}/reports", response_model=ReportResponse)
def post_project_report(project_id: str, payload: ReportPayload, repository: PlatformRepository = Depends(get_platform_repository), user: UserContext = Depends(get_current_user_context)):
    return {"report": repository.create_report(project_id=project_id, run_ids=payload.run_ids, report_type=payload.report_type, options=payload.options, user_id=user.user_id)}


@router.get("/api/projects/{project_id}/reports/{report_id}", response_model=ReportResponse)
def get_project_report(project_id: str, report_id: str, repository: PlatformRepository = Depends(get_platform_repository), user: UserContext = Depends(get_current_user_context)):
    actual_project_id = _resolved_project_id(repository, user.user_id, project_id)
    report = repository.get_report(report_id, user_id=user.user_id)
    if report.get("project_id") != actual_project_id:
        raise HTTPException(status_code=404, detail="Report not found in project.")
    return {"report": report}


@router.get("/api/projects/{project_id}/reports/{report_id}/download")
def download_project_report(project_id: str, report_id: str, repository: PlatformRepository = Depends(get_platform_repository), storage: ArtifactStorageService = Depends(get_artifact_storage_service), user: UserContext = Depends(get_current_user_context)):
    actual_project_id = _resolved_project_id(repository, user.user_id, project_id)
    report = repository.get_report(report_id, user_id=user.user_id)
    if report.get("project_id") != actual_project_id:
        raise HTTPException(status_code=404, detail="Report not found in project.")
    return storage.download_response_for_ref(
        report.get("storage_ref"),
        filename=f"{report_id}.md",
        default_media_type="text/markdown",
    )


@router.get("/api/projects/{project_id}/reports/{report_id}/data")
def download_project_report_source_data(project_id: str, report_id: str, repository: PlatformRepository = Depends(get_platform_repository), storage: ArtifactStorageService = Depends(get_artifact_storage_service), user: UserContext = Depends(get_current_user_context)):
    actual_project_id = _resolved_project_id(repository, user.user_id, project_id)
    report = repository.get_report(report_id, user_id=user.user_id)
    if report.get("project_id") != actual_project_id:
        raise HTTPException(status_code=404, detail="Report not found in project.")
    return storage.download_response_for_ref(
        report.get("source_data_storage_ref"),
        filename=f"{report_id}.source.json",
        default_media_type="application/json",
    )


@router.get("/api/projects/{project_id}/exports", response_model=ExportListResponse)
def get_project_exports(project_id: str, repository: PlatformRepository = Depends(get_platform_repository), user: UserContext = Depends(get_current_user_context)):
    actual_project_id = _resolved_project_id(repository, user.user_id, project_id)
    return {"project_id": actual_project_id, "exports": repository.list_exports(project_id=actual_project_id, user_id=user.user_id)}


@router.post("/api/projects/{project_id}/exports", response_model=ExportResponse)
def post_project_export(project_id: str, payload: ExportPayload, repository: PlatformRepository = Depends(get_platform_repository), user: UserContext = Depends(get_current_user_context)):
    return {"export": repository.create_project_export(project_id=project_id, run_ids=payload.run_ids, include_reports=payload.include_reports, user_id=user.user_id)}


@router.get("/api/projects/{project_id}/exports/{export_id}", response_model=ExportResponse)
def get_project_export(project_id: str, export_id: str, repository: PlatformRepository = Depends(get_platform_repository), user: UserContext = Depends(get_current_user_context)):
    actual_project_id = _resolved_project_id(repository, user.user_id, project_id)
    export = repository.get_export(export_id, user_id=user.user_id)
    if export.get("project_id") != actual_project_id:
        raise HTTPException(status_code=404, detail="Export not found in project.")
    return {"export": export}


@router.get("/api/projects/{project_id}/exports/{export_id}/download")
def download_project_export(project_id: str, export_id: str, repository: PlatformRepository = Depends(get_platform_repository), storage: ArtifactStorageService = Depends(get_artifact_storage_service), user: UserContext = Depends(get_current_user_context)):
    actual_project_id = _resolved_project_id(repository, user.user_id, project_id)
    export = repository.get_export(export_id, user_id=user.user_id)
    if export.get("project_id") != actual_project_id:
        raise HTTPException(status_code=404, detail="Export not found in project.")
    return storage.download_response_for_ref(
        export.get("storage_ref"),
        filename=f"{export_id}.zip",
        default_media_type="application/zip",
    )
