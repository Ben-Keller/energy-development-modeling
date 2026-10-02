from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict

from ..schemas import RunRequest
from ..settings import Settings
from .artifacts import load_artifact_manifest
from .contracts import ModelRuntimeManifest

MODEL_RUN_BUNDLE_SCHEMA_VERSION = "model_run_bundle_v1"
ARTIFACT_MANIFEST_SCHEMA_VERSION = "artifact_manifest_v1"
RUNTIME_ARTIFACT_HANDOFF_SCHEMA_VERSION = "runtime_artifact_handoff_v1"


def _path_str(path: Path | None) -> str:
    return str(path.resolve()) if path is not None else ""


def settings_runtime_snapshot(settings: Settings) -> Dict[str, Any]:
    runtime_config = settings.runtime_config or {}
    model_runtime_config = runtime_config.get("model_runtime") if isinstance(runtime_config.get("model_runtime"), dict) else {}
    return {
        "calliope_root": _path_str(settings.calliope_root),
        "runs_dir": _path_str(settings.runs_dir),
        "config_dir": _path_str(settings.config_dir),
        "dev_subset_start": settings.dev_subset_start,
        "dev_subset_end": settings.dev_subset_end,
        "analysis_subset_start": settings.analysis_subset_start,
        "analysis_subset_end": settings.analysis_subset_end,
        "dev_solver_time_limit_seconds": settings.dev_solver_time_limit_seconds,
        "analysis_solver_time_limit_seconds": settings.analysis_solver_time_limit_seconds,
        "allow_full_year": settings.allow_full_year,
        "solver": settings.solver,
        "summary_max_generation_techs": settings.summary_max_generation_techs,
        "summary_max_generation_timesteps": settings.summary_max_generation_timesteps,
        "summary_max_category_rows": settings.summary_max_category_rows,
        "summary_diagnostics_max_rows": settings.summary_diagnostics_max_rows,
        "development_engine": settings.development_engine,
        "mario_db_path": settings.mario_db_path,
        "mario_timeout_seconds": settings.mario_timeout_seconds,
        "mario_fail_on_error": settings.mario_fail_on_error,
        "model_runtime_mode": getattr(settings, "model_runtime_mode", "subprocess"),
        "runtime_artifact_handoff_mode": getattr(settings, "runtime_artifact_handoff_mode", "shared_filesystem"),
        "dataset_staging_mode": getattr(settings, "dataset_staging_mode", "copy_to_run"),
        "model_manifest_path": _path_str(getattr(settings, "model_manifest_path", None)),
        "dataset_manifest_path": _path_str(getattr(settings, "dataset_manifest_path", None)),
        "runtime_config": {
            "artifacts": runtime_config.get("artifacts") if isinstance(runtime_config.get("artifacts"), dict) else {},
            "data_policy": runtime_config.get("data_policy") if isinstance(runtime_config.get("data_policy"), dict) else {},
            "model_runtime": {
                "safe_env": list(model_runtime_config.get("safe_env") or []),
            },
        },
    }


def runtime_artifact_handoff_payload(settings: Settings) -> Dict[str, Any]:
    mode = str(getattr(settings, "runtime_artifact_handoff_mode", "shared_filesystem") or "shared_filesystem").strip().lower()
    return {
        "schema_version": RUNTIME_ARTIFACT_HANDOFF_SCHEMA_VERSION,
        "mode": mode,
        "contract": "artifact_catalog_to_storage_provider_v1",
        "local_default": mode == "shared_filesystem",
        "description": (
            "Runtime artifacts are available in the run directory and registered by artifact id."
            if mode == "shared_filesystem"
            else "Runtime artifacts must be published by the configured artifact storage provider before terminal status."
        ),
    }


def _artifact_policy_payload(settings: Settings) -> Dict[str, Any]:
    return {
        "schema_version": ARTIFACT_MANIFEST_SCHEMA_VERSION,
        "manifest": {
            artifact_id: asdict(entry) if is_dataclass(entry) else dict(entry)
            for artifact_id, entry in load_artifact_manifest(settings.runtime_config).items()
        },
    }


def _json_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path | None) -> str:
    if path is None:
        return ""
    path = path.expanduser()
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_provenance_payload(
    *,
    settings: Settings,
    request_payload: Dict[str, Any],
    manifest: ModelRuntimeManifest,
    dataset_manifest: Dict[str, Any],
    artifact_policy: Dict[str, Any],
) -> Dict[str, Any]:
    model_manifest_path = getattr(settings, "model_manifest_path", None)
    dataset_manifest_path = getattr(settings, "dataset_manifest_path", None)
    runtime_config = settings.runtime_config or {}
    return {
        "schema_version": "edim_run_provenance",
        "model_runtime": {
            "model_id": manifest.model_id,
            "model_version": manifest.model_version,
            "manifest_path": _path_str(model_manifest_path),
            "manifest_sha256": _file_sha256(model_manifest_path),
        },
        "model_architecture_id": str(request_payload.get("model_architecture_id") or ""),
        "energy_model_engine": str(request_payload.get("energy_model_engine") or ""),
        "dataset_manifest": {
            "manifest_path": _path_str(dataset_manifest_path),
            "source_manifest_sha256": _file_sha256(dataset_manifest_path),
            "snapshot_sha256": _json_sha256(dataset_manifest),
            "dataset_count": len(dataset_manifest.get("datasets") or []),
        },
        "artifact_policy": {
            "sha256": _json_sha256(artifact_policy),
            "artifact_count": len((artifact_policy.get("manifest") or {}) if isinstance(artifact_policy, dict) else {}),
        },
        "runtime_config": {
            "sha256": _json_sha256(runtime_config),
        },
        "request": {
            "sha256": _json_sha256(request_payload),
        },
    }


def build_model_run_bundle(
    *,
    settings: Settings,
    request: RunRequest,
    execution_id: str | None = None,
    run_id: str | None = None,
    manifest: ModelRuntimeManifest,
    scenario_package: Dict[str, Any] | None = None,
    dataset_manifest: Dict[str, Any] | None = None,
    queue_message: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    request_payload = request.model_dump(mode="json")
    resolved_execution_id = str(execution_id or "").strip()
    resolved_run_id = str(run_id or resolved_execution_id or "").strip()
    resolved_dataset_manifest = dataset_manifest or {}
    artifact_policy = _artifact_policy_payload(settings)
    return {
        "schema_version": MODEL_RUN_BUNDLE_SCHEMA_VERSION,
        "execution_id": resolved_execution_id,
        "run_id": resolved_run_id,
        "model_runtime": manifest.to_dict(),
        "queue_message": queue_message or {},
        "request": request_payload,
        "scenario_package": scenario_package or {},
        "dataset_manifest": resolved_dataset_manifest,
        "artifact_policy": artifact_policy,
        "artifact_handoff": runtime_artifact_handoff_payload(settings),
        "runtime_settings": settings_runtime_snapshot(settings),
        "provenance": _run_provenance_payload(
            settings=settings,
            request_payload=request_payload,
            manifest=manifest,
            dataset_manifest=resolved_dataset_manifest,
            artifact_policy=artifact_policy,
        ),
        "execution": {
            "execution_id": resolved_execution_id,
            "run_id": resolved_run_id,
            "mode": getattr(settings, "model_runtime_mode", "subprocess"),
            "backend_contract": "black_box_subprocess_v1",
            "artifact_handoff_mode": getattr(settings, "runtime_artifact_handoff_mode", "shared_filesystem"),
            "artifact_handoff_contract": RUNTIME_ARTIFACT_HANDOFF_SCHEMA_VERSION,
        },
    }


def write_model_run_bundle(path: Path, bundle: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8")
    return path
