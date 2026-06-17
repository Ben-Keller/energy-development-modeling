from __future__ import annotations

"""Platform report/export file assembly helpers.

Repositories persist metadata. This module owns the local filesystem reference
implementation for generated report/export files so cloud deployments can move
the same behavior behind object storage without putting ZIP/report assembly
inside persistence classes.
"""

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import HTTPException

from ..settings import Settings
from .artifact_storage import (
    local_platform_storage_ref,
    resolve_artifact_download,
    resolve_local_platform_storage_ref,
)
from .dataset_repository import normalize_scope_id
from .reporting import build_project_report_markdown, build_project_report_source_data
from .users import DEFAULT_USER_ID


def platform_root(settings: Settings) -> Path:
    path = settings.runs_dir.parent / "platform"
    path.mkdir(parents=True, exist_ok=True)
    return path


def generated_reports_dir(settings: Settings) -> Path:
    path = platform_root(settings) / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def generated_exports_dir(settings: Settings) -> Path:
    path = platform_root(settings) / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def platform_storage_ref_path(settings: Settings, storage_ref: Any) -> Path | None:
    if isinstance(storage_ref, dict) and storage_ref.get("object_key"):
        try:
            return resolve_local_platform_storage_ref(settings, storage_ref)
        except HTTPException:
            return None
    return None


def load_run_summary_for_report(settings: Settings, run_id: str) -> Dict[str, Any]:
    try:
        return _load_json(resolve_artifact_download(settings, run_id, "summary_json"), {})
    except Exception:
        return {}


def build_report_artifacts(
    *,
    settings: Settings,
    report_id: str,
    project: Dict[str, Any],
    run_records: List[Dict[str, Any]],
    summaries: Dict[str, Dict[str, Any]],
    exports: List[Dict[str, Any]],
    report_type: str,
    options: Dict[str, Any],
    generated_by_user_id: str,
    generated_at: str,
) -> Dict[str, Any]:
    report_dir = generated_reports_dir(settings)
    markdown_path = report_dir / f"{report_id}.md"
    source_data_path = report_dir / f"{report_id}.source.json"
    source_data = build_project_report_source_data(
        project=project,
        run_records=run_records,
        summaries=summaries,
        exports=exports,
        report_type=report_type,
        options=options or {},
        generated_by_user_id=generated_by_user_id,
        generated_at=generated_at,
    )
    source_data_path.write_text(json.dumps(source_data, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(build_project_report_markdown(source_data), encoding="utf-8")
    return {
        "source_data": source_data,
        "markdown_path": markdown_path,
        "source_data_path": source_data_path,
        "storage_ref": local_platform_storage_ref(
            settings,
            markdown_path,
            filename=f"{report_id}.md",
            media_type="text/markdown",
        ),
        "source_data_storage_ref": local_platform_storage_ref(
            settings,
            source_data_path,
            filename=f"{report_id}.source.json",
            media_type="application/json",
        ),
    }


def build_project_export_artifact(
    *,
    settings: Settings,
    export_id: str,
    project: Dict[str, Any],
    run_records: List[Dict[str, Any]],
    reports: Iterable[Dict[str, Any]],
    owner_user_id: str,
    created_by_user_id: str,
    created_at: str,
    include_reports: bool,
) -> Dict[str, Any]:
    path = generated_exports_dir(settings) / f"{export_id}.zip"
    selected_run_ids = [str(row.get("run_id") or "") for row in run_records if row.get("run_id")]
    with ZipFile(path, "w", ZIP_DEFLATED) as zf:
        uploaded_dataset_files = zip_uploaded_dataset_snapshots(run_records, zf)
        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "schema_version": "edim_project_export_v1",
                    "project_id": str(project.get("project_id") or ""),
                    "owner_user_id": owner_user_id,
                    "run_ids": selected_run_ids,
                    "created_by_user_id": created_by_user_id,
                    "created_at": created_at,
                    "uploaded_dataset_files": uploaded_dataset_files,
                },
                indent=2,
                sort_keys=True,
            ),
        )
        zf.writestr("project.json", json.dumps(project, indent=2, sort_keys=True))
        zf.writestr("runs.json", json.dumps(run_records, indent=2, sort_keys=True))
        zf.writestr(
            "datasets/uploaded_dataset_manifest.json",
            json.dumps(uploaded_dataset_files, indent=2, sort_keys=True),
        )
        for record in run_records:
            zip_run_bundle_artifacts(settings, record, zf, prefix=f"runs/{record.get('run_id', '')}")
        if include_reports:
            for report in reports:
                report_path = platform_storage_ref_path(settings, report.get("storage_ref"))
                if report_path is not None and report_path.exists() and report_path.is_file():
                    zf.write(report_path, f"reports/{report_path.name}")
                source_data_path = platform_storage_ref_path(settings, report.get("source_data_storage_ref"))
                if source_data_path is not None and source_data_path.exists() and source_data_path.is_file():
                    zf.write(source_data_path, f"reports/{source_data_path.name}")
    return {
        "path": path,
        "storage_ref": local_platform_storage_ref(
            settings,
            path,
            filename=f"{export_id}.zip",
            media_type="application/zip",
        ),
        "size_bytes": path.stat().st_size if path.exists() else 0,
    }


def zip_uploaded_dataset_snapshots(run_records: List[Dict[str, Any]], zf: ZipFile) -> List[Dict[str, Any]]:
    manifest: List[Dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for record in run_records:
        owner = _owner(record)
        snapshot = record.get("dataset_snapshot") if isinstance(record.get("dataset_snapshot"), dict) else {}
        datasets = snapshot.get("datasets") if isinstance(snapshot.get("datasets"), list) else []
        for dataset in datasets:
            if not isinstance(dataset, dict):
                continue
            version_id = str(dataset.get("active_version_id") or "").strip()
            if not version_id and not bool(dataset.get("versioned_override", False)):
                continue
            source_path = Path(str(dataset.get("path") or "")).expanduser()
            if dataset.get("staging_status") == "copied" and dataset.get("source_path"):
                source_path = Path(str(dataset.get("source_path") or "")).expanduser()
            if not source_path.exists() or not source_path.is_file():
                continue
            dataset_id = normalize_scope_id(str(dataset.get("id") or "dataset"), "dataset")
            key = (owner, dataset_id, version_id or source_path.stem, str(source_path.resolve()))
            if key in seen:
                continue
            seen.add(key)
            archive_path = f"datasets/users/{owner}/{dataset_id}/{source_path.name}"
            zf.write(source_path, archive_path)
            metadata_path = source_path.with_suffix(".json")
            metadata_archive_path = ""
            if metadata_path.exists() and metadata_path.is_file():
                metadata_archive_path = f"datasets/users/{owner}/{dataset_id}/{metadata_path.name}"
                zf.write(metadata_path, metadata_archive_path)
            manifest.append(
                {
                    "owner_user_id": owner,
                    "run_id": record.get("run_id", ""),
                    "dataset_id": dataset_id,
                    "version_id": version_id,
                    "filename": source_path.name,
                    "archive_path": archive_path,
                    "metadata_archive_path": metadata_archive_path,
                    "size_bytes": source_path.stat().st_size,
                }
            )
    return manifest


def zip_run_bundle_artifacts(settings: Settings, record: Dict[str, Any], zf: ZipFile, prefix: str) -> None:
    run_id = normalize_scope_id(str(record.get("run_id") or ""), "")
    if not run_id:
        return
    run_dir = (settings.runs_dir / run_id).resolve()
    if not run_dir.exists() or not run_dir.is_dir():
        return
    artifact_catalog = record.get("artifact_catalog") if isinstance(record.get("artifact_catalog"), list) else []
    for artifact in artifact_catalog:
        if not isinstance(artifact, dict) or not bool(artifact.get("include_in_project_bundle", False)):
            continue
        relative = str(artifact.get("path") or "").strip().lstrip("/")
        if not relative:
            continue
        path = (run_dir / relative).resolve()
        if run_dir not in path.parents or not path.exists() or not path.is_file():
            continue
        zf.write(path, f"{prefix}/{path.relative_to(run_dir)}")


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _owner(record: Dict[str, Any]) -> str:
    return normalize_scope_id(
        str(record.get("owner_user_id") or record.get("created_by_user_id") or DEFAULT_USER_ID),
        DEFAULT_USER_ID,
    )
