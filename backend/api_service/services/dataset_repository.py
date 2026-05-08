from __future__ import annotations

import csv
import hashlib
import io
import json
import mimetypes
import re
import shutil
import time
import uuid
from pathlib import Path
from zipfile import BadZipFile, ZipFile
from typing import Any, Dict, List, Protocol

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response

from ..settings import Settings

DATASET_STAGING_SCHEMA_VERSION = "dataset_staging_v1"
DATASET_STORAGE_REF_SCHEMA_VERSION = "dataset_storage_ref_v1"
LOCAL_DATASET_STORAGE_PROVIDER = "local_filesystem"


class DatasetRepository(Protocol):
    """Route-facing boundary for input dataset metadata, versions, and files."""

    def list_input_datasets(
        self,
        *,
        user_id: str,
        layer: str = "",
        input_property: str = "",
        role: str = "",
    ) -> List[Dict[str, Any]]: ...

    def download_response_for_dataset(self, dataset_id: str, *, user_id: str) -> Response: ...
    def download_response_for_version(self, dataset_id: str, version_id: str, *, user_id: str) -> Response: ...
    def register_upload(self, dataset_id: str, filename: str, content: bytes, *, user_id: str) -> Dict[str, Any]: ...
    def list_versions(self, dataset_id: str, *, user_id: str) -> List[Dict[str, Any]]: ...
    def activate_version(self, dataset_id: str, version_id: str, *, user_id: str) -> Dict[str, Any]: ...
    def delete_version(self, dataset_id: str, version_id: str, *, user_id: str) -> Dict[str, Any]: ...
    def runtime_dataset_manifest(self, *, user_id: str) -> Dict[str, Any]: ...
    def stage_runtime_datasets(self, *, user_id: str, run_dir: Path, staging_mode: str) -> Dict[str, Any]: ...


class LocalDatasetRepository(DatasetRepository):
    """Filesystem-backed dataset repository used by local development.

    Cloud deployments should replace this with a database/object-storage
    implementation while preserving method semantics.
    """

    def __init__(self, settings: Settings):
        self._settings = settings

    @property
    def settings(self) -> Settings:
        return self._settings

    def list_input_datasets(
        self,
        *,
        user_id: str,
        layer: str = "",
        input_property: str = "",
        role: str = "",
    ) -> List[Dict[str, Any]]:
        rows = []
        for row in build_input_dataset_catalog(self._settings, user_id=user_id):
            search_text = " ".join(
                str(row.get(key, ""))
                for key in ("id", "label", "layer", "role", "scope", "upload_policy")
            ).lower()
            if layer and str(row.get("layer", "")).lower() != layer.lower():
                continue
            if role and role.lower() not in str(row.get("role", "")).lower():
                continue
            if input_property and input_property.lower() not in search_text:
                continue
            path = Path(row["path"])
            stat = path.stat() if path.exists() else None
            rows.append(
                {
                    "id": row["id"],
                    "label": row["label"],
                    "layer": row["layer"],
                    "role": row["role"],
                    "required": bool(row.get("required", False)),
                    "scope": row.get("scope", "system"),
                    "upload_policy": row.get("upload_policy", "project_override"),
                    "user_upload_listable": bool(row.get("user_upload_listable", True)),
                    "filename": path.name,
                    "source_filename": Path(row.get("source_path", path)).name,
                    "exists": path.exists(),
                    "size_bytes": stat.st_size if stat else None,
                    "active_version_id": row.get("active_version_id", ""),
                    "versioned_override": bool(row.get("versioned_override", False)),
                    "download_url": f"/api/input-datasets/{row['id']}/download",
                }
            )
        return rows

    def download_response_for_dataset(self, dataset_id: str, *, user_id: str) -> Response:
        dataset = resolve_input_dataset(self._settings, dataset_id, user_id=user_id)
        path = Path(dataset["path"])
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Input dataset file not found.")
        media_type, _ = mimetypes.guess_type(path.name)
        return FileResponse(path=str(path), filename=path.name, media_type=media_type or "application/octet-stream")

    def download_response_for_version(self, dataset_id: str, version_id: str, *, user_id: str) -> Response:
        metadata = resolve_dataset_version(self._settings, dataset_id, version_id, user_id=user_id)
        path = Path(str(metadata.get("path", ""))).expanduser()
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Dataset version file not found.")
        filename = str(metadata.get("filename") or path.name)
        media_type, _ = mimetypes.guess_type(filename)
        return FileResponse(path=str(path), filename=filename, media_type=media_type or "application/octet-stream")

    def register_upload(self, dataset_id: str, filename: str, content: bytes, *, user_id: str) -> Dict[str, Any]:
        return register_dataset_upload(self._settings, dataset_id, filename, content, user_id=user_id)

    def list_versions(self, dataset_id: str, *, user_id: str) -> List[Dict[str, Any]]:
        resolve_input_dataset(self._settings, dataset_id, user_id=user_id)
        return list_dataset_versions(self._settings, dataset_id, user_id=user_id)

    def activate_version(self, dataset_id: str, version_id: str, *, user_id: str) -> Dict[str, Any]:
        return activate_dataset_version(self._settings, dataset_id, version_id, user_id=user_id)

    def delete_version(self, dataset_id: str, version_id: str, *, user_id: str) -> Dict[str, Any]:
        return delete_dataset_version(self._settings, dataset_id, version_id, user_id=user_id)

    def runtime_dataset_manifest(self, *, user_id: str) -> Dict[str, Any]:
        mode = _normalize_dataset_staging_mode(getattr(self._settings, "dataset_staging_mode", "copy_to_run"))
        rows = []
        for row in build_input_dataset_catalog(self._settings, user_id=user_id):
            path = Path(row.get("path", "")).expanduser()
            source_path = Path(row.get("source_path", row.get("path", ""))).expanduser()
            exists = path.exists() and path.is_file()
            status = "missing"
            if exists:
                if mode == "copy_to_run":
                    status = "pending_copy"
                elif mode == "object_reference":
                    status = "object_reference"
                else:
                    status = "referenced"
            manifest_row = self._manifest_row(row, path=path, source_path=source_path)
            manifest_row.update(_dataset_file_metadata(path, include_hash=False))
            manifest_row.update(
                {
                    "staging_mode": mode,
                    "staging_status": status,
                    "staged_relative_path": "",
                    "storage_ref": _local_dataset_storage_ref(self._settings, path),
                    "source_storage_ref": _local_dataset_storage_ref(self._settings, source_path),
                }
            )
            rows.append(manifest_row)
        return _add_dataset_staging_summary(
            {"schema_version": "model_dataset_manifest_v1", "datasets": rows},
            staging_mode=mode,
        )

    def stage_runtime_datasets(self, *, user_id: str, run_dir: Path, staging_mode: str) -> Dict[str, Any]:
        mode = _normalize_dataset_staging_mode(staging_mode)
        run_dir = run_dir.expanduser().resolve()
        rows = []
        for row in build_input_dataset_catalog(self._settings, user_id=user_id):
            dataset_id = str(row.get("id", "")).strip()
            source_path = Path(row.get("path", "")).expanduser()
            path = source_path
            status = "referenced"
            relative_path = ""
            storage_ref = _local_dataset_storage_ref(self._settings, path)
            source_storage_ref = storage_ref

            if mode == "copy_to_run":
                if source_path.exists() and source_path.is_file():
                    target = run_dir / "inputs" / "datasets" / dataset_id / source_path.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_path, target)
                    path = target.resolve()
                    status = "copied"
                    relative_path = target.relative_to(run_dir).as_posix()
                    storage_ref = _local_dataset_storage_ref(self._settings, path, run_dir=run_dir)
                    source_storage_ref = _local_dataset_storage_ref(self._settings, source_path)
                else:
                    status = "missing"
            elif mode == "object_reference":
                status = "object_reference"

            manifest_row = self._manifest_row(row, path=path, source_path=source_path)
            manifest_row.update(_dataset_file_metadata(path, include_hash=True))
            manifest_row.update(
                {
                    "staging_mode": mode,
                    "staging_status": status,
                    "staged_relative_path": relative_path,
                    "storage_ref": storage_ref,
                    "source_storage_ref": source_storage_ref,
                }
            )
            rows.append(manifest_row)
        return _add_dataset_staging_summary(
            {"schema_version": "model_dataset_manifest_v1", "datasets": rows},
            staging_mode=mode,
        )

    def _manifest_row(self, row: Dict[str, Any], *, path: Path, source_path: Path) -> Dict[str, Any]:
        return {
            "id": row.get("id", ""),
            "label": row.get("label", ""),
            "layer": row.get("layer", ""),
            "role": row.get("role", ""),
            "path": str(path),
            "required": bool(row.get("required", False)),
            "scope": row.get("scope", "system"),
            "upload_policy": row.get("upload_policy", "project_override"),
            "user_upload_listable": bool(row.get("user_upload_listable", True)),
            "active_version_id": row.get("active_version_id", ""),
            "active_version_created_at": row.get("active_version_created_at", ""),
            "versioned_override": bool(row.get("versioned_override", False)),
            "source_path": str(source_path),
        }


def stage_runtime_dataset_manifest(
    repository: DatasetRepository,
    *,
    user_id: str,
    run_dir: Path,
    staging_mode: str,
) -> Dict[str, Any]:
    """Resolve the exact dataset snapshot handed to the model runtime."""
    stage_fn = getattr(repository, "stage_runtime_datasets", None)
    if callable(stage_fn):
        return stage_fn(user_id=user_id, run_dir=run_dir, staging_mode=staging_mode)

    mode = _normalize_dataset_staging_mode(staging_mode)
    manifest = repository.runtime_dataset_manifest(user_id=user_id)
    rows = []
    for raw in manifest.get("datasets") or []:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        path = Path(str(row.get("path", ""))).expanduser()
        row.update(_dataset_file_metadata(path, include_hash=True))
        row.setdefault("staging_mode", mode)
        row.setdefault("staging_status", "object_reference" if mode == "object_reference" else ("referenced" if path.exists() and path.is_file() else "missing"))
        row.setdefault("staged_relative_path", "")
        rows.append(row)
    return _add_dataset_staging_summary(
        {"schema_version": str(manifest.get("schema_version") or "model_dataset_manifest_v1"), "datasets": rows},
        staging_mode=mode,
    )


def _normalize_dataset_staging_mode(value: str | None) -> str:
    mode = (value or "copy_to_run").strip().lower().replace("-", "_")
    aliases = {
        "copy": "copy_to_run",
        "object": "object_reference",
        "referenced": "reference",
        "in_place": "reference",
    }
    mode = aliases.get(mode, mode)
    if mode not in {"reference", "copy_to_run", "object_reference"}:
        raise ValueError(f"Unsupported dataset staging mode: {value!r}")
    return mode


def _add_dataset_staging_summary(manifest: Dict[str, Any], *, staging_mode: str) -> Dict[str, Any]:
    rows = [row for row in manifest.get("datasets") or [] if isinstance(row, dict)]
    manifest["dataset_staging"] = {
        "schema_version": DATASET_STAGING_SCHEMA_VERSION,
        "mode": _normalize_dataset_staging_mode(staging_mode),
        "dataset_count": len(rows),
        "pending_copy_dataset_count": sum(1 for row in rows if row.get("staging_status") == "pending_copy"),
        "copied_dataset_count": sum(1 for row in rows if row.get("staging_status") == "copied"),
        "referenced_dataset_count": sum(1 for row in rows if row.get("staging_status") == "referenced"),
        "object_reference_dataset_count": sum(1 for row in rows if row.get("staging_status") == "object_reference"),
        "missing_required_dataset_ids": [
            str(row.get("id") or "")
            for row in rows
            if bool(row.get("required")) and row.get("staging_status") == "missing"
        ],
    }
    return manifest


def _dataset_file_metadata(path: Path, *, include_hash: bool) -> Dict[str, Any]:
    exists = path.exists() and path.is_file()
    return {
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else None,
        "content_sha256": _sha256_file(path) if exists and include_hash else "",
        "media_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _local_dataset_storage_ref(settings: Settings, path: Path, *, run_dir: Path | None = None) -> Dict[str, Any]:
    resolved = path.expanduser().resolve()
    if run_dir is not None:
        try:
            return {
                "schema_version": DATASET_STORAGE_REF_SCHEMA_VERSION,
                "storage_provider": LOCAL_DATASET_STORAGE_PROVIDER,
                "storage_scope": "run_input",
                "object_key": resolved.relative_to(run_dir.expanduser().resolve()).as_posix(),
                "filename": resolved.name,
            }
        except ValueError:
            pass
    for scope, root in (
        ("repo", settings.config_dir.resolve().parent),
        ("dataset_upload", (settings.runs_dir.parent / "dataset_uploads").resolve()),
        ("run", settings.runs_dir.resolve()),
    ):
        try:
            return {
                "schema_version": DATASET_STORAGE_REF_SCHEMA_VERSION,
                "storage_provider": LOCAL_DATASET_STORAGE_PROVIDER,
                "storage_scope": scope,
                "object_key": resolved.relative_to(root).as_posix(),
                "filename": resolved.name,
            }
        except ValueError:
            continue
    return {
        "schema_version": DATASET_STORAGE_REF_SCHEMA_VERSION,
        "storage_provider": LOCAL_DATASET_STORAGE_PROVIDER,
        "storage_scope": "external_local",
        "object_key": resolved.name,
        "filename": resolved.name,
    }


# Local filesystem dataset helpers. Kept in this module so dataset catalog,
# upload/versioning, and runtime staging share one backend boundary.
from fastapi import HTTPException

from ..settings import Settings

INPUT_DATASET_ID_PATTERN = r"^[a-z0-9_]+$"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
ALLOWED_UPLOAD_SUFFIXES = {".csv", ".json", ".geojson", ".xlsx", ".xls"}


def normalize_scope_id(value: str | None, default: str) -> str:
    text = str(value or default).strip()
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)[:120]
    return normalized or default


def _dataset_uploads_dir(settings: Settings, user_id: str = "local_user") -> Path:
    safe_user = normalize_scope_id(user_id, "local_user")
    path = settings.runs_dir.parent / "dataset_uploads" / "users" / safe_user
    path.mkdir(parents=True, exist_ok=True)
    return path


def _active_versions_path(settings: Settings, user_id: str = "local_user") -> Path:
    return _dataset_uploads_dir(settings, user_id=user_id) / "active_versions.json"


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _valid_dataset_id(dataset_id: str) -> bool:
    return bool(dataset_id) and all(ch.islower() or ch.isdigit() or ch == "_" for ch in dataset_id)


def _load_active_versions(settings: Settings, user_id: str = "local_user") -> Dict[str, Dict[str, Any]]:
    raw = _load_json(_active_versions_path(settings, user_id=user_id), {})
    return raw if isinstance(raw, dict) else {}


def _write_active_versions(settings: Settings, active: Dict[str, Dict[str, Any]], user_id: str = "local_user") -> None:
    _write_json(_active_versions_path(settings, user_id=user_id), active)


def _repo_root(settings: Settings) -> Path:
    return settings.config_dir.resolve().parent


def _resolve_manifest_datasets(settings: Settings) -> List[Dict[str, Any]]:
    manifest_path = getattr(settings, "dataset_manifest_path", None)
    if not manifest_path or not Path(manifest_path).exists():
        raise FileNotFoundError("Dataset manifest is required and was not found.")
    raw = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    datasets = raw.get("datasets") if isinstance(raw, dict) else None
    if not isinstance(datasets, list):
        raise ValueError("Dataset manifest must contain a datasets list.")
    format_values = {
        "repo_root": str(_repo_root(settings)),
        "config_dir": str(settings.config_dir),
        "calliope_root": str(settings.calliope_root),
        "runs_dir": str(settings.runs_dir),
    }
    out: List[Dict[str, Any]] = []
    for row in datasets:
        if not isinstance(row, dict):
            continue
        path_template = str(row.get("path_template", row.get("path", ""))).strip()
        try:
            resolved = path_template.format(**format_values)
        except Exception:
            resolved = path_template
        out.append(
            {
                "id": str(row.get("id", "")).strip(),
                "label": str(row.get("label", row.get("id", ""))).strip(),
                "layer": str(row.get("layer", "model")).strip(),
                "role": str(row.get("role", "")).strip(),
                "path": Path(resolved).expanduser(),
                "required": bool(row.get("required", False)),
                "scope": str(row.get("scope", "system")).strip(),
                "upload_policy": str(row.get("upload_policy", "project_override")).strip(),
                "user_upload_listable": bool(row.get("user_upload_listable", True)),
            }
        )
    return [row for row in out if _valid_dataset_id(str(row.get("id", "")))]


def build_input_dataset_catalog(settings: Settings, user_id: str = "local_user") -> List[Dict[str, Any]]:
    base_rows = _resolve_manifest_datasets(settings)
    active = _load_active_versions(settings, user_id=user_id)
    out: List[Dict[str, Any]] = []
    for row in base_rows:
        dataset_id = str(row.get("id", ""))
        base_path = Path(row["path"])
        active_row = active.get(dataset_id) if isinstance(active.get(dataset_id), dict) else None
        if active_row and active_row.get("path"):
            active_path = Path(str(active_row["path"])).expanduser()
            out.append(
                {
                    **row,
                    "path": active_path,
                    "source_path": base_path,
                    "active_version_id": str(active_row.get("version_id", "")),
                    "active_version_created_at": str(active_row.get("created_at", "")),
                    "versioned_override": True,
                }
            )
        else:
            out.append({**row, "source_path": base_path, "active_version_id": "", "versioned_override": False})
    return out


def resolve_input_dataset(settings: Settings, dataset_id: str, user_id: str = "local_user") -> Dict[str, Any]:
    dataset_id = dataset_id.strip()
    if not _valid_dataset_id(dataset_id):
        raise HTTPException(status_code=400, detail="Invalid dataset id.")
    datasets = {row["id"]: row for row in build_input_dataset_catalog(settings, user_id=user_id)}
    dataset = datasets.get(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Input dataset not found.")
    return dataset


def list_dataset_versions(settings: Settings, dataset_id: str, user_id: str = "local_user") -> List[Dict[str, Any]]:
    dataset_id = dataset_id.strip()
    if not _valid_dataset_id(dataset_id):
        raise HTTPException(status_code=400, detail="Invalid dataset id.")
    versions_dir = _dataset_uploads_dir(settings, user_id=user_id) / dataset_id
    if not versions_dir.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for metadata_path in sorted(versions_dir.glob("*.json"), reverse=True):
        raw = _load_json(metadata_path, {})
        if isinstance(raw, dict) and raw.get("version_id"):
            rows.append(raw)
    return rows


def resolve_dataset_version(settings: Settings, dataset_id: str, version_id: str, user_id: str = "local_user") -> Dict[str, Any]:
    dataset_id = dataset_id.strip()
    version_id = version_id.strip()
    if not _valid_dataset_id(dataset_id):
        raise HTTPException(status_code=400, detail="Invalid dataset id.")
    versions = {str(row.get("version_id", "")): row for row in list_dataset_versions(settings, dataset_id, user_id=user_id)}
    metadata = versions.get(version_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="Dataset version not found.")
    return metadata


def activate_dataset_version(settings: Settings, dataset_id: str, version_id: str, user_id: str = "local_user") -> Dict[str, Any]:
    dataset_id = dataset_id.strip()
    version_id = version_id.strip()
    if not _valid_dataset_id(dataset_id):
        raise HTTPException(status_code=400, detail="Invalid dataset id.")
    metadata = resolve_dataset_version(settings, dataset_id, version_id, user_id=user_id)
    path = Path(str(metadata.get("path", ""))).expanduser()
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Dataset version file not found.")
    active = _load_active_versions(settings, user_id=user_id)
    active[dataset_id] = metadata
    _write_active_versions(settings, active, user_id=user_id)
    return metadata


def delete_dataset_version(settings: Settings, dataset_id: str, version_id: str, user_id: str = "local_user") -> Dict[str, Any]:
    dataset_id = dataset_id.strip()
    version_id = version_id.strip()
    if not _valid_dataset_id(dataset_id):
        raise HTTPException(status_code=400, detail="Invalid dataset id.")
    versions_dir = _dataset_uploads_dir(settings, user_id=user_id) / dataset_id
    metadata_path = versions_dir / f"{version_id}.json"
    metadata = _load_json(metadata_path, {})
    if not metadata_path.exists() or not isinstance(metadata, dict):
        raise HTTPException(status_code=404, detail="Dataset version not found.")
    active = _load_active_versions(settings, user_id=user_id)
    if (active.get(dataset_id) or {}).get("version_id") == version_id:
        active.pop(dataset_id, None)
        _write_active_versions(settings, active, user_id=user_id)
    file_path = Path(str(metadata.get("path", ""))).expanduser()
    if file_path.exists() and file_path.is_file():
        file_path.unlink()
    metadata_path.unlink()
    return {"ok": True, "dataset_id": dataset_id, "version_id": version_id}


def register_dataset_upload(settings: Settings, dataset_id: str, filename: str, content: bytes, *, user_id: str = "local_user") -> Dict[str, Any]:
    dataset = resolve_input_dataset(settings, dataset_id, user_id=user_id)
    validation = validate_dataset_upload(dataset=dataset, filename=filename, content=content)
    suffix = Path(filename or "dataset.bin").suffix
    version_id = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}_{dataset_id}"
    versions_dir = _dataset_uploads_dir(settings, user_id=user_id) / dataset_id
    versions_dir.mkdir(parents=True, exist_ok=True)
    target = versions_dir / f"{version_id}{suffix}"
    target.write_bytes(content)
    metadata = {
        "version_id": version_id,
        "dataset_id": dataset_id,
        "filename": filename or target.name,
        "path": str(target.resolve()),
        "size_bytes": target.stat().st_size,
        "created_at": datetime_utc_now(),
        "scope": "user_override",
        "user_id": normalize_scope_id(user_id, "local_user"),
        "validation": validation,
    }
    _write_json(versions_dir / f"{version_id}.json", metadata)
    active = _load_active_versions(settings, user_id=user_id)
    active[dataset_id] = metadata
    _write_active_versions(settings, active, user_id=user_id)
    return metadata


def validate_dataset_upload(*, dataset: Dict[str, Any], filename: str, content: bytes) -> Dict[str, Any]:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{suffix or 'none'}'. Allowed types: CSV, JSON, GeoJSON, XLSX, XLS.")
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded dataset is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Uploaded dataset exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.")

    validation: Dict[str, Any] = {"ok": True, "file_type": suffix.lstrip("."), "warnings": [], "checks": []}
    if suffix == ".csv":
        upload_headers = _csv_headers(content, filename)
        validation["headers"] = upload_headers
        validation["checks"].append({"id": "csv_parseable", "status": "ok", "message": f"Detected {len(upload_headers)} columns."})
        expected_path = Path(dataset.get("source_path") or dataset.get("path") or "")
        if expected_path.suffix.lower() == ".csv" and expected_path.exists():
            expected_headers = _csv_headers(expected_path.read_bytes(), expected_path.name)
            missing = [header for header in expected_headers if header not in upload_headers]
            if missing:
                raise HTTPException(status_code=400, detail=f"Uploaded CSV is missing required columns for {dataset.get('id')}: {', '.join(missing[:12])}")
            validation["checks"].append({"id": "required_headers", "status": "ok", "message": "Uploaded CSV includes all required source headers."})
    elif suffix in {".json", ".geojson"}:
        try:
            payload = json.loads(content.decode("utf-8-sig"))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Uploaded {suffix} is not valid JSON.") from exc
        if suffix == ".geojson":
            if not isinstance(payload, dict) or payload.get("type") not in {"FeatureCollection", "Feature", "Polygon", "MultiPolygon", "Point", "MultiPoint", "LineString", "MultiLineString", "GeometryCollection"}:
                raise HTTPException(status_code=400, detail="Uploaded GeoJSON must be a valid GeoJSON object with a recognized type.")
        validation["checks"].append({"id": "json_parseable", "status": "ok", "message": "JSON parsed successfully."})
    elif suffix == ".xlsx":
        try:
            with ZipFile(io.BytesIO(content)) as zf:
                names = set(zf.namelist())
        except BadZipFile as exc:
            raise HTTPException(status_code=400, detail="Uploaded XLSX is not a valid workbook archive.") from exc
        if "[Content_Types].xml" not in names:
            raise HTTPException(status_code=400, detail="Uploaded XLSX is missing workbook content types.")
        validation["checks"].append({"id": "xlsx_container", "status": "ok", "message": "Workbook archive structure is valid."})
    elif suffix == ".xls":
        if not content.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
            raise HTTPException(status_code=400, detail="Uploaded XLS is not a valid legacy Excel file.")
        validation["warnings"].append("Legacy .xls structure was checked by file signature only; convert to .xlsx for stronger validation.")
    return validation


def _csv_headers(content: bytes, filename: str) -> List[str]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"{filename or 'CSV'} must be UTF-8 encoded.") from exc
    reader = csv.reader(io.StringIO(text))
    try:
        headers = next(reader)
    except StopIteration as exc:
        raise HTTPException(status_code=400, detail=f"{filename or 'CSV'} has no header row.") from exc
    cleaned = [str(header).strip() for header in headers if str(header).strip()]
    if not cleaned:
        raise HTTPException(status_code=400, detail=f"{filename or 'CSV'} has no usable column headers.")
    return cleaned


def datetime_utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
