from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from ..dependencies import get_current_user_context, get_dataset_repository, get_platform_repository
from ...schemas import (
    DatasetDeleteResponse,
    DatasetUploadResponse,
    DatasetVersionsResponse,
    InputDatasetCreatePayload,
    InputDatasetListResponse,
    InputDatasetPatchPayload,
    InputDatasetResponse,
    ProjectDatasetAssignmentPayload,
    ProjectDatasetAssignmentResponse,
)
from ...services.dataset_repository import DatasetRepository
from ...services.platform_repository import PlatformRepository
from ...services.users import UserContext

router = APIRouter()


@router.get("/api/input-datasets", response_model=InputDatasetListResponse)
def list_input_datasets(
    layer: str = Query(default=""),
    input_property: str = Query(default=""),
    role: str = Query(default=""),
    repository: DatasetRepository = Depends(get_dataset_repository),
    user: UserContext = Depends(get_current_user_context),
):
    return {"datasets": repository.list_input_datasets(user_id=user.user_id, layer=layer, input_property=input_property, role=role)}


@router.post("/api/input-datasets", response_model=InputDatasetResponse)
def create_input_dataset(
    payload: InputDatasetCreatePayload,
    repository: DatasetRepository = Depends(get_dataset_repository),
    user: UserContext = Depends(get_current_user_context),
):
    return {"dataset": repository.create_input_dataset(payload.model_dump(), user_id=user.user_id)}


@router.patch("/api/input-datasets/{dataset_id}", response_model=InputDatasetResponse)
def update_input_dataset(
    dataset_id: str,
    payload: InputDatasetPatchPayload,
    repository: DatasetRepository = Depends(get_dataset_repository),
    user: UserContext = Depends(get_current_user_context),
):
    clean_payload = {key: value for key, value in payload.model_dump().items() if value is not None}
    return {"dataset": repository.update_input_dataset(dataset_id, clean_payload, user_id=user.user_id)}


@router.post("/api/projects/{project_id}/datasets", response_model=ProjectDatasetAssignmentResponse)
def attach_input_dataset_to_project(
    project_id: str,
    payload: ProjectDatasetAssignmentPayload,
    repository: DatasetRepository = Depends(get_dataset_repository),
    platform_repository: PlatformRepository = Depends(get_platform_repository),
    user: UserContext = Depends(get_current_user_context),
):
    project = platform_repository.get_project(user_id=user.user_id, project_id=project_id)
    return repository.attach_dataset_to_project(
        payload.dataset_id,
        payload.version_id,
        str(project.get("project_id") or project_id),
        user_id=user.user_id,
    )


@router.get("/api/input-datasets/{dataset_id}/download")
def download_input_dataset(dataset_id: str, repository: DatasetRepository = Depends(get_dataset_repository), user: UserContext = Depends(get_current_user_context)):
    return repository.download_response_for_dataset(dataset_id, user_id=user.user_id)


@router.post("/api/input-datasets/{dataset_id}/upload", response_model=DatasetUploadResponse)
async def upload_input_dataset(
    dataset_id: str,
    file: UploadFile = File(...),
    repository: DatasetRepository = Depends(get_dataset_repository),
    user: UserContext = Depends(get_current_user_context),
):
    content = await file.read()
    metadata = repository.register_upload(dataset_id, file.filename or "", content, user_id=user.user_id)
    return {"ok": True, **metadata}


@router.get("/api/input-datasets/{dataset_id}/versions", response_model=DatasetVersionsResponse)
def get_input_dataset_versions(dataset_id: str, repository: DatasetRepository = Depends(get_dataset_repository), user: UserContext = Depends(get_current_user_context)):
    return {"dataset_id": dataset_id, "user_id": user.user_id, "scope": "user", "versions": repository.list_versions(dataset_id, user_id=user.user_id)}


@router.get("/api/input-datasets/{dataset_id}/versions/{version_id}/download")
def download_input_dataset_version(dataset_id: str, version_id: str, repository: DatasetRepository = Depends(get_dataset_repository), user: UserContext = Depends(get_current_user_context)):
    return repository.download_response_for_version(dataset_id, version_id, user_id=user.user_id)


@router.post("/api/input-datasets/{dataset_id}/versions/{version_id}/activate", response_model=DatasetUploadResponse)
def activate_input_dataset_version(dataset_id: str, version_id: str, repository: DatasetRepository = Depends(get_dataset_repository), user: UserContext = Depends(get_current_user_context)):
    metadata = repository.activate_version(dataset_id, version_id, user_id=user.user_id)
    return {"ok": True, **metadata}


@router.delete("/api/input-datasets/{dataset_id}/versions/{version_id}", response_model=DatasetDeleteResponse)
def delete_input_dataset_version(
    dataset_id: str,
    version_id: str,
    repository: DatasetRepository = Depends(get_dataset_repository),
    platform_repository: PlatformRepository = Depends(get_platform_repository),
    user: UserContext = Depends(get_current_user_context),
):
    references = platform_repository.list_dataset_version_references(
        dataset_id=dataset_id,
        version_id=version_id,
        user_id=user.user_id,
    )
    if references:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Dataset version is referenced by submitted run snapshots and cannot be deleted.",
                "references": references[:20],
            },
        )
    return repository.delete_version(dataset_id, version_id, user_id=user.user_id)
