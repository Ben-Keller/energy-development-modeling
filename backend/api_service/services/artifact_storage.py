from __future__ import annotations

import json
import mimetypes
import re
from pathlib import Path
from typing import Any, Dict, Protocol

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response

from ..runtime import ArtifactRegistry
from ..settings import Settings

STORAGE_REF_SCHEMA_VERSION = "edim_storage_ref_v1"
LOCAL_PLATFORM_STORAGE_PROVIDER = "local_platform_filesystem"
RUNTIME_ARTIFACT_PUBLICATION_SCHEMA_VERSION = "runtime_artifact_publication_v1"
RUN_ID_PATTERN = re.compile(r"^[a-f0-9]{8,32}$")


def resolve_run_dir(settings: Settings, run_id: str) -> Path:
    if not RUN_ID_PATTERN.fullmatch(str(run_id or "").lower()):
        raise HTTPException(status_code=400, detail="Invalid run_id format.")
    path = (settings.runs_dir / run_id).resolve()
    if settings.runs_dir.resolve() not in path.parents:
        raise HTTPException(status_code=400, detail="Invalid run_id path.")
    return path


def resolve_run_artifact_registry(settings: Settings, run_id: str) -> ArtifactRegistry:
    run_dir = resolve_run_dir(settings, run_id)
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    artifact_policy_path = run_dir / "inputs" / "artifact_policy.json"
    artifact_policy = _load_json_file(artifact_policy_path)
    return ArtifactRegistry(run_id=run_id, run_dir=run_dir, runtime_config=artifact_policy or settings.runtime_config)


def _load_json_file(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def read_summary_json(path: Path):
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        raise HTTPException(status_code=500, detail="Could not read run summary.")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=503, detail="Run summary is not ready yet. Please retry.")


def resolve_artifact_download(settings: Settings, run_id: str, artifact_id: str) -> Path:
    registry = resolve_run_artifact_registry(settings, run_id)
    try:
        path = registry.path_for(artifact_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Artifact not found") from exc
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return path


def local_platform_storage_ref(settings: Settings, path: Path, *, filename: str = "", media_type: str = "application/octet-stream") -> Dict[str, Any]:
    """Build a portable storage reference for a local platform artifact.

    The reference deliberately exposes an object key relative to the platform
    storage root, not an absolute local filesystem path. Cloud providers should
    keep the same semantic shape while using Blob/container object keys.
    """
    root = (settings.runs_dir.parent / "platform").resolve()
    resolved = path.expanduser().resolve()
    try:
        object_key = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"Platform storage object must be under {root}: {resolved}") from exc
    size_bytes = resolved.stat().st_size if resolved.exists() and resolved.is_file() else 0
    media_type = media_type or mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
    return {
        "schema_version": STORAGE_REF_SCHEMA_VERSION,
        "storage_provider": LOCAL_PLATFORM_STORAGE_PROVIDER,
        "storage_scope": "platform",
        "object_key": object_key,
        "filename": filename or resolved.name,
        "media_type": media_type,
        "size_bytes": size_bytes,
    }


def resolve_local_platform_storage_ref(settings: Settings, storage_ref: Dict[str, Any]) -> Path:
    provider = str(storage_ref.get("storage_provider") or "")
    if provider and provider != LOCAL_PLATFORM_STORAGE_PROVIDER:
        raise HTTPException(status_code=501, detail=f"Unsupported local storage provider: {provider}")
    object_key = str(storage_ref.get("object_key") or "").strip().lstrip("/")
    if not object_key:
        raise HTTPException(status_code=404, detail="Storage reference is missing object_key.")
    root = (settings.runs_dir.parent / "platform").resolve()
    path = (root / object_key).resolve()
    if root not in path.parents and path != root:
        raise HTTPException(status_code=400, detail="Storage reference escapes platform storage root.")
    return path


class ArtifactStorageService(Protocol):
    """Download/read boundary for durable run and platform files."""

    def publish_run_artifacts(self, *, run_id: str, run_dir: Path, artifact_catalog: list[Dict[str, Any]], handoff_mode: str) -> Dict[str, Any]: ...
    def read_json_artifact(self, run_id: str, artifact_id: str) -> dict: ...
    def download_response_for_artifact(self, run_id: str, artifact_id: str) -> Response: ...
    def download_response_for_ref(self, storage_ref: Dict[str, Any] | None, *, filename: str, default_media_type: str) -> Response: ...


class LocalArtifactStorageService(ArtifactStorageService):
    """Filesystem-backed artifact storage used by local development."""

    def __init__(self, settings: Settings):
        self._settings = settings

    @property
    def settings(self) -> Settings:
        return self._settings

    def publish_run_artifacts(self, *, run_id: str, run_dir: Path, artifact_catalog: list[Dict[str, Any]], handoff_mode: str) -> Dict[str, Any]:
        """Finalize runtime artifacts through the configured storage boundary.

        Local development uses shared filesystem handoff, so publication is a
        no-op after the runtime writes declared artifacts. Azure should replace
        this service with an implementation that uploads the cataloged files to
        Blob Storage and returns provider-specific object references here.
        """
        mode = (handoff_mode or "shared_filesystem").strip().lower()
        artifacts = [dict(row) for row in artifact_catalog if isinstance(row, dict)]
        downloadable = [row for row in artifacts if row.get("expose_download")]
        status = "available_in_place" if mode == "shared_filesystem" else "provider_not_configured"
        message = (
            "Shared filesystem handoff: declared artifacts remain available in the local run directory."
            if mode == "shared_filesystem"
            else f"Local artifact storage cannot publish {mode} artifacts; inject a cloud ArtifactStorageService for deployment."
        )
        return {
            "schema_version": RUNTIME_ARTIFACT_PUBLICATION_SCHEMA_VERSION,
            "run_id": run_id,
            "handoff_mode": mode,
            "storage_provider": "local_filesystem",
            "storage_scope": "run",
            "object_prefix": run_id,
            "status": status,
            "published": mode == "shared_filesystem",
            "artifact_count": len(artifacts),
            "downloadable_artifact_count": len(downloadable),
            "message": message,
        }

    def read_json_artifact(self, run_id: str, artifact_id: str) -> dict:
        path = resolve_artifact_download(self._settings, run_id, artifact_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=503, detail="Run artifact is not valid JSON yet. Please retry.") from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Could not read run artifact.") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=503, detail="Run artifact JSON must be an object.")
        return payload

    def download_response_for_artifact(self, run_id: str, artifact_id: str) -> Response:
        path = resolve_artifact_download(self._settings, run_id, artifact_id)
        return self._file_response(path, filename=path.name, default_media_type="application/octet-stream")

    def download_response_for_ref(self, storage_ref: Dict[str, Any] | None, *, filename: str, default_media_type: str) -> Response:
        if isinstance(storage_ref, dict) and storage_ref.get("object_key"):
            path = resolve_local_platform_storage_ref(self._settings, storage_ref)
            response_filename = filename or str(storage_ref.get("filename") or path.name)
            response_media_type = str(storage_ref.get("media_type") or default_media_type or "application/octet-stream")
            return self._file_response(path, filename=response_filename, default_media_type=response_media_type)
        raise HTTPException(status_code=404, detail="Storage reference not found.")

    def _file_response(self, path: Path, *, filename: str, default_media_type: str) -> FileResponse:
        media_type, _ = mimetypes.guess_type(path.name)
        return FileResponse(path=str(path), filename=filename or path.name, media_type=media_type or default_media_type)
