from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


SYSTEM_MANIFEST_SCHEMA_VERSION = "edim_system_manifest"
EXECUTION_QUEUE_MESSAGE_SCHEMA_VERSION = "execution_queue_message"
EXECUTION_ATTEMPT_SCHEMA_VERSION = "execution_attempt"
EXECUTION_RETRY_POLICY_SCHEMA_VERSION = "execution_retry_policy"


@dataclass(frozen=True)
class ExecutionQueueMessage:
    """Durable queue payload for cloud/backend workers.

    The local in-memory queue and cloud queues should both carry this complete
    message and persist the corresponding run record before enqueueing.
    """

    execution_id: str
    run_id: str
    project_id: str
    user_id: str
    request_payload: Dict[str, Any]
    schema_version: str = EXECUTION_QUEUE_MESSAGE_SCHEMA_VERSION
    attempt: int = 1
    created_at: str = ""
    retry_policy: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "execution_id": self.execution_id,
            "run_id": self.run_id,
            "project_id": self.project_id,
            "user_id": self.user_id,
            "attempt": int(self.attempt),
            "created_at": self.created_at,
            "request_payload": dict(self.request_payload),
            "retry_policy": dict(self.retry_policy or {}),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ExecutionQueueMessage":
        if payload.get("schema_version") != EXECUTION_QUEUE_MESSAGE_SCHEMA_VERSION:
            raise ValueError(f"Unsupported queue message schema_version: {payload.get('schema_version')!r}")
        return cls(
            execution_id=str(payload.get("execution_id") or ""),
            run_id=str(payload.get("run_id") or ""),
            project_id=str(payload.get("project_id") or ""),
            user_id=str(payload.get("user_id") or ""),
            attempt=int(payload.get("attempt") or 1),
            created_at=str(payload.get("created_at") or ""),
            request_payload=dict(payload.get("request_payload") or {}),
            retry_policy=dict(payload.get("retry_policy") or {}),
        )


@dataclass(frozen=True)
class ExecutionAttemptRecord:
    """Persisted worker lifecycle record for one execution attempt."""

    execution_id: str
    run_id: str
    attempt: int
    worker_id: str
    status: str
    schema_version: str = EXECUTION_ATTEMPT_SCHEMA_VERSION
    started_at: str = ""
    heartbeat_at: str = ""
    finished_at: str | None = None
    cancellation_requested: bool = False
    retryable: bool = False
    error: str = ""
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "execution_id": self.execution_id,
            "run_id": self.run_id,
            "attempt": int(self.attempt),
            "worker_id": self.worker_id,
            "status": self.status,
            "started_at": self.started_at,
            "heartbeat_at": self.heartbeat_at,
            "finished_at": self.finished_at,
            "cancellation_requested": bool(self.cancellation_requested),
            "retryable": bool(self.retryable),
            "error": self.error,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ExecutionAttemptRecord":
        if payload.get("schema_version") != EXECUTION_ATTEMPT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported execution attempt schema_version: {payload.get('schema_version')!r}")
        return cls(
            execution_id=str(payload.get("execution_id") or ""),
            run_id=str(payload.get("run_id") or ""),
            attempt=int(payload.get("attempt") or 1),
            worker_id=str(payload.get("worker_id") or ""),
            status=str(payload.get("status") or ""),
            started_at=str(payload.get("started_at") or ""),
            heartbeat_at=str(payload.get("heartbeat_at") or ""),
            finished_at=payload.get("finished_at"),
            cancellation_requested=bool(payload.get("cancellation_requested")),
            retryable=bool(payload.get("retryable")),
            error=str(payload.get("error") or ""),
            message=str(payload.get("message") or ""),
        )


@dataclass(frozen=True)
class ModelExecutionRequest:
    """Backend-to-runtime request snapshot.

    This object is deliberately model-agnostic. Model-specific details belong in
    `request_bundle` or in the runtime package, not in API routers.
    """

    run_id: str
    request_payload: Dict[str, Any]
    scenario_package: Dict[str, Any]
    artifact_policy: Dict[str, Dict[str, Any]]
    run_profile: str
    request_bundle: Dict[str, Any] = field(default_factory=dict)
    model_id: str = ""
    model_version: str = ""


@dataclass(frozen=True)
class ModelExecutionContext:
    """Filesystem/context handles passed to a runtime adapter.

    A future container/remote adapter can replace these paths with staged
    object-storage locations while preserving the same semantic fields.
    """

    run_id: str
    run_dir: Path
    request_bundle_path: Path
    artifact_policy: Dict[str, Dict[str, Any]]
    event_log_path: Path | None = None
    model_manifest_path: Path | None = None
    dataset_manifest_path: Path | None = None


@dataclass(frozen=True)
class ProgressEvent:
    stage: str
    progress: float
    message: str


@dataclass(frozen=True)
class DeclaredArtifact:
    """Artifact emitted by a runtime and controlled by artifact policy."""

    artifact_id: str
    path: Path
    producer_stage: str
    kind: str
    expose_download: bool = True
    include_in_project_bundle: bool = True
    embed_in_summary: bool = False
    embed_in_final_results: bool = False


@dataclass
class ModelExecutionResult:
    """Terminal runtime result consumed by JobManager and project records."""

    run_id: str
    summary: Dict[str, Any]
    warnings: List[str] = field(default_factory=list)
    declared_artifacts: List[DeclaredArtifact] = field(default_factory=list)


@dataclass(frozen=True)
class ModelRuntimeManifest:
    """Runtime package manifest loaded by the backend before execution."""

    schema_version: str
    model_id: str
    model_version: str
    label: str
    description: str
    entrypoint_type: str
    entrypoint: List[str]
    preflight_entrypoint: List[str] = field(default_factory=list)
    catalog_entrypoint: List[str] = field(default_factory=list)
    supported_schema_versions: Dict[str, Any] = field(default_factory=dict)
    supported_energy_model_engines: List[str] = field(default_factory=list)
    supported_model_architectures: List[str] = field(default_factory=list)
    required_inputs: List[str] = field(default_factory=list)
    declared_outputs: List[str] = field(default_factory=list)
    progress_stages: List[str] = field(default_factory=list)
    modules: List[Dict[str, Any]] = field(default_factory=list)
    architecture_catalog_path: str = ""
    resource_requirements: Dict[str, Any] = field(default_factory=dict)
    capabilities: Dict[str, Any] = field(default_factory=dict)
    manifest_path: Path | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "label": self.label,
            "description": self.description,
            "entrypoint_type": self.entrypoint_type,
            "entrypoint": self.entrypoint,
            "preflight_entrypoint": self.preflight_entrypoint,
            "catalog_entrypoint": self.catalog_entrypoint,
            "supported_schema_versions": self.supported_schema_versions,
            "supported_energy_model_engines": self.supported_energy_model_engines,
            "supported_model_architectures": self.supported_model_architectures,
            "required_inputs": self.required_inputs,
            "declared_outputs": self.declared_outputs,
            "progress_stages": self.progress_stages,
            "modules": self.modules,
            "architecture_catalog_path": self.architecture_catalog_path,
            "resource_requirements": self.resource_requirements,
            "capabilities": self.capabilities,
            "manifest_path": str(self.manifest_path) if self.manifest_path else "",
        }


def default_model_manifest_path(repo_root: Path) -> Path:
    return repo_root / "model_runtime" / "edim_model" / "model_manifest.json"


def load_model_runtime_manifest(path: Path) -> ModelRuntimeManifest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Model runtime manifest not found at {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model runtime manifest is not valid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Model runtime manifest must be a JSON object.")
    required = ["schema_version", "model_id", "model_version", "entrypoint_type", "entrypoint"]
    missing = [key for key in required if not raw.get(key)]
    if missing:
        raise ValueError(f"Model runtime manifest missing required fields: {', '.join(missing)}")
    entrypoint = raw.get("entrypoint")
    if not isinstance(entrypoint, list) or not all(isinstance(item, str) and item for item in entrypoint):
        raise ValueError("Model runtime manifest entrypoint must be a non-empty string list.")
    return ModelRuntimeManifest(
        schema_version=str(raw.get("schema_version", "")),
        model_id=str(raw.get("model_id", "")),
        model_version=str(raw.get("model_version", "")),
        label=str(raw.get("label", raw.get("model_id", ""))),
        description=str(raw.get("description", "")),
        entrypoint_type=str(raw.get("entrypoint_type", "")),
        entrypoint=list(entrypoint),
        preflight_entrypoint=list(raw.get("preflight_entrypoint") or []),
        catalog_entrypoint=list(raw.get("catalog_entrypoint") or []),
        supported_schema_versions=dict(raw.get("supported_schema_versions") or {}),
        supported_energy_model_engines=list(raw.get("supported_energy_model_engines") or []),
        supported_model_architectures=list(raw.get("supported_model_architectures") or []),
        required_inputs=list(raw.get("required_inputs") or []),
        declared_outputs=list(raw.get("declared_outputs") or []),
        progress_stages=list(raw.get("progress_stages") or []),
        modules=list(raw.get("modules") or []),
        architecture_catalog_path=str(raw.get("architecture_catalog_path") or ""),
        resource_requirements=dict(raw.get("resource_requirements") or {}),
        capabilities=dict(raw.get("capabilities") or {}),
        manifest_path=path,
    )


def validate_request_against_manifest(request_payload: Dict[str, Any], manifest: ModelRuntimeManifest) -> list[str]:
    issues: list[str] = []
    supported_engines = {str(item).strip().lower() for item in manifest.supported_energy_model_engines if str(item).strip()}
    engine = str(request_payload.get("energy_model_engine", "")).strip().lower()
    if supported_engines and engine and engine not in supported_engines:
        issues.append(
            f"Selected model runtime '{manifest.model_id}' supports energy_model_engine values "
            f"{sorted(supported_engines)}, but received '{engine}'."
        )
    supported_architectures = {
        str(item).strip().lower().replace("_", "-")
        for item in manifest.supported_model_architectures
        if str(item).strip()
    }
    architecture_id = str(request_payload.get("model_architecture_id", "")).strip().lower().replace("_", "-")
    if supported_architectures and architecture_id and architecture_id not in supported_architectures:
        issues.append(
            f"Selected model runtime '{manifest.model_id}' supports model_architecture_id values "
            f"{sorted(supported_architectures)}, but received '{architecture_id}'."
        )
    return issues
