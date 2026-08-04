from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

from .adapters import SubprocessModelRuntime
from .runtime import (
    ArtifactRegistry,
    EXECUTION_RETRY_POLICY_SCHEMA_VERSION,
    ExecutionAttemptRecord,
    ExecutionQueueMessage,
    LocalEventStore,
    LocalExecutionQueue,
    LocalRunStore,
    ModelExecutionContext,
    ModelExecutionRequest,
    ModelRuntimeManifest,
    RunRepository,
    RuntimeEvent,
    build_model_run_bundle,
    load_model_runtime_manifest,
    validate_request_against_manifest,
    write_model_run_bundle,
    EventStore,
)
from .schemas import TERMINAL_RUN_STATUSES, RunArtifacts, RunExecutionInfo, RunRequest, RunSummary
from .services.artifact_storage import ArtifactStorageService, LocalArtifactStorageService
from .services.dataset_repository import DatasetRepository, LocalDatasetRepository, stage_runtime_dataset_manifest
from .services.platform_repository import create_platform_repository
from .services.users import DEFAULT_USER_ID, is_admin_user
from .settings import Settings

logger = logging.getLogger(__name__)

FINAL_JOB_STATUSES = set(TERMINAL_RUN_STATUSES)
LOCAL_USER_ID = DEFAULT_USER_ID


class JobQueueFullError(RuntimeError):
    pass


def _fmt_ts(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _fmt_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"


@dataclass
class _JobRecord:
    execution_id: str
    request: RunRequest
    run_id: str
    user_id: str = LOCAL_USER_ID
    request_fingerprint: str = ""
    status: str = "queued"
    progress: float = 0.0
    stage: str = "queued"
    message: str = "Queued"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    worker_pid: int | None = None
    error: str | None = None
    summary: dict | None = None
    cancel_requested: bool = False
    queue_message: Dict[str, Any] = field(default_factory=dict)
    execution_attempts: List[Dict[str, Any]] = field(default_factory=list)
    worker_id: str = ""
    dataset_snapshot: Dict[str, Any] = field(default_factory=dict)
    project_run_number: int = 0


class JobManager:
    """Local run queue for the API layer.

    The manager is intentionally model-agnostic: it builds a run bundle, invokes
    a runtime adapter, stores progress, and exposes run/job state. The runtime
    adapter owns all model-specific execution.
    """

    def __init__(
        self,
        settings: Settings,
        runtime: Any | None = None,
        run_repository: RunRepository | None = None,
        execution_queue: Any | None = None,
        event_store: EventStore | None = None,
        dataset_repository: DatasetRepository | None = None,
        artifact_storage: ArtifactStorageService | None = None,
        *,
        start_worker: bool = True,
    ):
        self._settings = settings
        self._runtime_manifest = self._load_runtime_manifest()
        self._runtime = runtime or self._build_runtime()
        self._run_repository = run_repository or create_platform_repository(settings)
        self._dataset_repository = dataset_repository or LocalDatasetRepository(settings)
        self._event_store = event_store or LocalEventStore(settings.runs_dir)
        self._artifact_storage = artifact_storage or LocalArtifactStorageService(settings)
        self._jobs: Dict[str, _JobRecord] = {}
        self._pending: List[str] = []
        self._queue = execution_queue or LocalExecutionQueue()
        self._lock = threading.Lock()
        self._start_worker = start_worker
        if start_worker:
            self._worker = threading.Thread(target=self._worker_loop, daemon=True, name="edim-run-worker")
            self._worker.start()
        else:
            self._worker = None

    def _load_runtime_manifest(self) -> ModelRuntimeManifest:
        path = getattr(self._settings, "model_manifest_path", None)
        if path and path.exists():
            return load_model_runtime_manifest(path)
        raise FileNotFoundError(f"Model runtime manifest not found at {path}")

    def _build_runtime(self) -> SubprocessModelRuntime:
        mode = str(getattr(self._settings, "model_runtime_mode", "subprocess") or "subprocess").strip().lower()
        if mode != "subprocess":
            raise ValueError("EDIM model_runtime.mode must be 'subprocess'.")
        return SubprocessModelRuntime(self._settings, self._runtime_manifest)

    def _dataset_manifest_payload(self, user_id: str = LOCAL_USER_ID) -> Dict[str, Any]:
        return self._dataset_repository.runtime_dataset_manifest(user_id=user_id)

    def _stage_dataset_manifest_payload(self, *, user_id: str, run_dir) -> Dict[str, Any]:
        return stage_runtime_dataset_manifest(
            self._dataset_repository,
            user_id=user_id,
            run_dir=run_dir,
            staging_mode=getattr(self._settings, "dataset_staging_mode", "copy_to_run"),
        )

    def _stage_execution_dataset_snapshot(self, execution_id: str, *, user_id: str) -> Dict[str, Any]:
        queued_dir = LocalRunStore(self._settings.runs_dir).queued_dir(execution_id)
        return self._stage_dataset_manifest_payload(user_id=user_id, run_dir=queued_dir)

    def _build_execution_contract(
        self,
        execution_id: str,
        run_id: str,
        req: RunRequest,
        *,
        user_id: str = LOCAL_USER_ID,
        queue_message: Dict[str, Any] | None = None,
        dataset_manifest: Dict[str, Any] | None = None,
        persist_dataset_snapshot: bool = True,
    ) -> tuple[ModelExecutionRequest, ModelExecutionContext]:
        request_payload = req.model_dump(mode="json")
        issues = validate_request_against_manifest(request_payload, self._runtime_manifest)
        if issues:
            raise ValueError(issues[0])
        run_store = LocalRunStore(self._settings.runs_dir)
        queued_dir = run_store.queued_dir(execution_id)
        dataset_manifest = dataset_manifest or self._stage_dataset_manifest_payload(user_id=user_id, run_dir=queued_dir)
        bundle = build_model_run_bundle(
            settings=self._settings,
            request=req,
            execution_id=execution_id,
            run_id=run_id,
            manifest=self._runtime_manifest,
            dataset_manifest=dataset_manifest,
            queue_message=queue_message or self._queue_message_for_values(
                execution_id=execution_id,
                run_id=run_id,
                project_id=req.project_id or "default",
                user_id=user_id,
                request_payload=request_payload,
                created_at=_fmt_ts(time.time()) or "",
            ).to_dict(),
        )
        bundle_path = write_model_run_bundle(queued_dir / "inputs" / "request_bundle.json", bundle)
        if persist_dataset_snapshot:
            try:
                self._run_repository.update_run_record(run_id, {"dataset_snapshot": dataset_manifest}, user_id=user_id)
            except Exception:
                logger.exception("Failed to persist staged dataset snapshot for run_id=%s", run_id)
        return (
            ModelExecutionRequest(
                run_id=run_id,
                request_payload=request_payload,
                scenario_package={},
                artifact_policy=(bundle.get("artifact_policy") or {}).get("manifest", {}),
                run_profile=req.run_profile,
                request_bundle=bundle,
                model_id=self._runtime_manifest.model_id,
                model_version=self._runtime_manifest.model_version,
            ),
            ModelExecutionContext(
                run_id=run_id,
                run_dir=queued_dir,
                request_bundle_path=bundle_path,
                artifact_policy=(bundle.get("artifact_policy") or {}).get("manifest", {}),
                event_log_path=self._event_store.event_log_path(execution_id),
                model_manifest_path=self._runtime_manifest.manifest_path,
                dataset_manifest_path=getattr(self._settings, "dataset_manifest_path", None),
            ),
        )

    def submit(self, req: RunRequest, *, run_id: str | None = None, user_id: str = LOCAL_USER_ID) -> RunExecutionInfo:
        if run_id:
            return self._submit_one(req, run_id=run_id, user_id=user_id)
        return self.submit_many([req], user_id=user_id)[0]

    def submit_many(self, requests: List[RunRequest], *, user_id: str = LOCAL_USER_ID) -> List[RunExecutionInfo]:
        if not requests:
            return []
        for req in requests:
            issues = validate_request_against_manifest(req.model_dump(mode="json"), self._runtime_manifest)
            if issues:
                raise ValueError(issues[0])

        queued_messages: List[Dict[str, Any]] = []
        out: List[RunExecutionInfo] = []
        with self._lock:
            requests_with_fingerprint: List[tuple[RunRequest, str]] = []
            dedupe_enabled = bool(self._settings.job_dedupe_enabled)
            unique_new_fingerprints: set[str] = set()
            for req in requests:
                request_fingerprint = self._request_fingerprint(req, user_id=user_id)
                requests_with_fingerprint.append((req, request_fingerprint))
                if not dedupe_enabled:
                    unique_new_fingerprints.add(f"{request_fingerprint}:{len(unique_new_fingerprints)}")
                    continue
                if request_fingerprint in unique_new_fingerprints:
                    continue
                if self._find_reusable_job_locked(request_fingerprint) is not None:
                    continue
                unique_new_fingerprints.add(request_fingerprint)

            if not self._can_accept_locked(len(unique_new_fingerprints)):
                raise JobQueueFullError(
                    f"Job queue capacity reached ({self._settings.job_queue_capacity}). "
                    "Wait for running/queued jobs to finish or cancel."
                )

            for req, request_fingerprint in requests_with_fingerprint:
                reusable = self._find_reusable_job_locked(request_fingerprint)
                if reusable is not None:
                    reusable.message = (
                        "Duplicate request deduplicated; reusing active job."
                        if reusable.status in {"queued", "running"}
                        else "Duplicate request matched cached successful run."
                    )
                    reusable.updated_at = time.time()
                    queue_position = self._queue_position_locked(reusable.execution_id) if reusable.status == "queued" else None
                    out.append(self._to_job_info_locked(reusable, queue_position=queue_position))
                    continue

                execution_id = uuid.uuid4().hex
                run_id = uuid.uuid4().hex
                rec = _JobRecord(execution_id=execution_id, run_id=run_id, request=req, user_id=user_id, request_fingerprint=request_fingerprint)
                rec.queue_message = self._queue_message_for_record(rec).to_dict()
                rec.dataset_snapshot = self._stage_execution_dataset_snapshot(execution_id, user_id=user_id)
                self._jobs[execution_id] = rec
                self._pending.append(execution_id)
                self._create_platform_run_record(rec)
                queued_messages.append(rec.queue_message)
                out.append(self._to_job_info_locked(rec, queue_position=len(self._pending)))

            self._trim_history_locked()

        for message in queued_messages:
            self._queue.put(message)
        return out

    def _submit_one(self, req: RunRequest, *, run_id: str, user_id: str = LOCAL_USER_ID) -> RunExecutionInfo:
        issues = validate_request_against_manifest(req.model_dump(mode="json"), self._runtime_manifest)
        if issues:
            raise ValueError(issues[0])
        with self._lock:
            self._ensure_existing_run_is_submittable(run_id, user_id=user_id)
            if not self._can_accept_locked(1):
                raise JobQueueFullError(
                    f"Job queue capacity reached ({self._settings.job_queue_capacity}). "
                    "Wait for running/queued jobs to finish or cancel."
                )
            execution_id = uuid.uuid4().hex
            rec = _JobRecord(
                execution_id=execution_id,
                run_id=run_id,
                request=req,
                user_id=user_id,
                request_fingerprint=self._request_fingerprint(req, user_id=user_id),
            )
            rec.queue_message = self._queue_message_for_record(rec).to_dict()
            rec.dataset_snapshot = self._stage_execution_dataset_snapshot(execution_id, user_id=user_id)
            self._jobs[execution_id] = rec
            self._pending.append(execution_id)
            self._create_platform_run_record(rec)
            info = self._to_job_info_locked(rec, queue_position=len(self._pending))
            self._trim_history_locked()
        self._queue.put(rec.queue_message)
        return info

    def _ensure_existing_run_is_submittable(self, run_id: str, *, user_id: str) -> None:
        get_record = getattr(self._run_repository, "get_run_record", None)
        if not callable(get_record):
            return
        try:
            existing = get_record(run_id, user_id=user_id)
        except Exception:
            return
        status = str(existing.get("status") or "draft").strip().lower()
        if status != "draft":
            raise ValueError(f"Run {run_id} is {status or 'unknown'} and cannot be submitted again.")

    def get(self, execution_id: str, *, user_id: str = LOCAL_USER_ID) -> RunExecutionInfo:
        with self._lock:
            rec = self._jobs.get(execution_id)
            if rec is None:
                raise KeyError(execution_id)
            if rec.user_id != user_id and not is_admin_user(user_id):
                raise KeyError(execution_id)
            queue_position = self._queue_position_locked(execution_id) if rec.status == "queued" else None
            return self._to_job_info_locked(rec, queue_position=queue_position)

    def cancel(self, execution_id: str, *, user_id: str = LOCAL_USER_ID) -> RunExecutionInfo:
        with self._lock:
            rec = self._jobs.get(execution_id)
            if rec is None:
                raise KeyError(execution_id)
            if rec.user_id != user_id and not is_admin_user(user_id):
                raise KeyError(execution_id)
            if rec.status in FINAL_JOB_STATUSES:
                return self._to_job_info_locked(rec, queue_position=None)

            rec.cancel_requested = True
            now = time.time()
            rec.updated_at = now
            if rec.status == "queued":
                if rec.execution_id in self._pending:
                    self._pending.remove(rec.execution_id)
                self._reset_run_to_draft_after_cancel_locked(rec, message="Run cancelled before start; draft restored.")
            else:
                rec.stage = "cancelling"
                rec.message = "Cancellation requested; terminating model runtime at the next adapter checkpoint."
                self._update_current_attempt_locked(
                    rec,
                    status="cancelling",
                    heartbeat_at=_fmt_ts(now) or "",
                    cancellation_requested=True,
                    message=rec.message,
                )
                self._update_platform_run_record(rec)
            queue_position = self._queue_position_locked(rec.execution_id) if rec.status == "queued" else None
            return self._to_job_info_locked(rec, queue_position=queue_position)

    def can_accept(self, count: int = 1) -> bool:
        with self._lock:
            return self._can_accept_locked(count)

    def list(self, limit: int = 50, *, user_id: str = LOCAL_USER_ID) -> List[RunExecutionInfo]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
            if not is_admin_user(user_id):
                jobs = [rec for rec in jobs if rec.user_id == user_id]
            jobs = [rec for rec in jobs if rec.status != "draft"]
            return [
                self._to_job_info_locked(rec, queue_position=self._queue_position_locked(rec.execution_id) if rec.status == "queued" else None)
                for rec in jobs[: max(1, limit)]
            ]

    def runtime_stats(self) -> Dict[str, float | int]:
        with self._lock:
            counts = {"queued": 0, "running": 0, "succeeded": 0, "failed": 0, "cancelled": 0, "other": 0}
            for rec in self._jobs.values():
                status = str(rec.status or "").strip().lower()
                counts[status if status in counts else "other"] += 1
            capacity = max(1, int(self._settings.job_queue_capacity))
            active_jobs = counts["queued"] + counts["running"]
            total_jobs = len(self._jobs)
        try:
            queue_depth = int(self._queue.qsize())
        except Exception:
            queue_depth = counts["queued"]
        return {
            "capacity": capacity,
            "active_jobs": active_jobs,
            "queued_jobs": counts["queued"],
            "running_jobs": counts["running"],
            "succeeded_jobs": counts["succeeded"],
            "failed_jobs": counts["failed"],
            "cancelled_jobs": counts["cancelled"],
            "other_jobs": counts["other"],
            "tracked_jobs": total_jobs,
            "queue_depth": max(0, queue_depth),
            "utilization_share": active_jobs / float(capacity),
        }

    def runtime_manifest(self) -> Dict[str, Any]:
        return self._runtime_manifest.to_dict()

    def execution_retry_policy(self) -> Dict[str, Any]:
        return self._retry_policy_payload()

    def event_log_path(self, execution_id: str):
        return self._event_store.event_log_path(execution_id)

    def read_events(self, execution_id: str) -> list[Dict[str, Any]]:
        return self._event_store.read_events(execution_id)

    def _retry_policy_payload(self) -> Dict[str, Any]:
        return {
            "schema_version": EXECUTION_RETRY_POLICY_SCHEMA_VERSION,
            "max_attempts": max(1, int(getattr(self._settings, "job_execution_max_attempts", 1))),
            "retry_on": ["worker_start_failure", "infrastructure_failure"],
            "model_errors_terminal": True,
            "local_manager_retries": False,
        }

    def _queue_message_for_record(self, rec: _JobRecord) -> ExecutionQueueMessage:
        return self._queue_message_for_values(
            execution_id=rec.execution_id,
            run_id=rec.run_id,
            project_id=rec.request.project_id or "default",
            user_id=rec.user_id,
            request_payload=rec.request.model_dump(mode="json"),
            created_at=_fmt_ts(rec.created_at) or "",
        )

    def _queue_message_for_values(
        self,
        *,
        execution_id: str,
        run_id: str,
        project_id: str,
        user_id: str,
        request_payload: Dict[str, Any],
        created_at: str,
        attempt: int = 1,
    ) -> ExecutionQueueMessage:
        return ExecutionQueueMessage(
            execution_id=execution_id,
            run_id=run_id,
            project_id=project_id,
            user_id=user_id,
            request_payload=request_payload,
            attempt=attempt,
            created_at=created_at,
            retry_policy=self._retry_policy_payload(),
        )

    def _coerce_queue_message(self, raw: Any) -> ExecutionQueueMessage:
        if isinstance(raw, ExecutionQueueMessage):
            return raw
        if isinstance(raw, dict):
            return ExecutionQueueMessage.from_dict(raw)
        execution_id = str(raw or "").strip()
        with self._lock:
            rec = self._jobs.get(execution_id)
            if rec is not None:
                return self._queue_message_for_record(rec)
        return self._queue_message_for_values(
            execution_id=execution_id,
            run_id="",
            project_id="",
            user_id=LOCAL_USER_ID,
            request_payload={},
            created_at="",
        )

    def _worker_identity(self) -> str:
        return f"local-thread:{os.getpid()}:{threading.current_thread().name}"

    def _start_execution_attempt_locked(self, rec: _JobRecord, queue_message: ExecutionQueueMessage) -> None:
        now = _fmt_ts(time.time()) or ""
        attempt = ExecutionAttemptRecord(
            execution_id=rec.execution_id,
            run_id=rec.run_id,
            attempt=int(queue_message.attempt or 1),
            worker_id=self._worker_identity(),
            status="running",
            started_at=now,
            heartbeat_at=now,
            cancellation_requested=bool(rec.cancel_requested),
            message="Worker accepted execution message.",
        ).to_dict()
        rec.execution_attempts = [
            row
            for row in rec.execution_attempts
            if not (
                str(row.get("execution_id") or "") == rec.execution_id
                and int(row.get("attempt") or 1) == int(queue_message.attempt or 1)
            )
        ]
        rec.execution_attempts.append(attempt)
        rec.worker_id = str(attempt.get("worker_id") or "")
        rec.worker_pid = os.getpid()

    def _update_current_attempt_locked(self, rec: _JobRecord, **updates: Any) -> None:
        if not rec.execution_attempts:
            return
        current = dict(rec.execution_attempts[-1])
        current.update({key: value for key, value in updates.items() if value is not None})
        rec.execution_attempts[-1] = current

    def _finish_execution_attempt_locked(self, rec: _JobRecord, *, status: str, error: str | None = None) -> None:
        now = _fmt_ts(time.time()) or ""
        self._update_current_attempt_locked(
            rec,
            status=status,
            run_id=rec.run_id,
            heartbeat_at=now,
            finished_at=now,
            cancellation_requested=bool(rec.cancel_requested),
            retryable=False,
            error=str(error or ""),
            message=rec.message,
        )

    def _publish_runtime_artifacts(self, result) -> Dict[str, Any]:
        summary = dict(result.summary or {})
        artifact_catalog = [dict(row) for row in summary.get("artifact_catalog") or [] if isinstance(row, dict)]
        handoff_mode = str(getattr(self._settings, "runtime_artifact_handoff_mode", "shared_filesystem") or "shared_filesystem")
        publish = getattr(self._artifact_storage, "publish_run_artifacts", None)
        if callable(publish):
            publication = publish(
                run_id=result.run_id,
                run_dir=self._settings.runs_dir / result.run_id,
                artifact_catalog=artifact_catalog,
                handoff_mode=handoff_mode,
            )
        else:
            publication = {
                "schema_version": "runtime_artifact_publication_v1",
                "run_id": result.run_id,
                "handoff_mode": handoff_mode,
                "storage_provider": "unconfigured",
                "status": "skipped",
                "published": False,
                "artifact_count": len(artifact_catalog),
                "message": "Artifact storage provider does not implement publish_run_artifacts.",
            }
        summary["artifact_publication"] = publication
        self._write_summary_publication(result.run_id, summary)
        result.summary = summary
        if handoff_mode != "shared_filesystem" and not bool(publication.get("published")):
            raise RuntimeError(
                "Runtime artifact handoff failed: "
                f"mode={handoff_mode}, provider={publication.get('storage_provider', 'unknown')}, "
                f"status={publication.get('status', 'unknown')}"
            )
        return publication

    def _write_summary_publication(self, run_id: str, summary: Dict[str, Any]) -> None:
        try:
            run_dir = self._settings.runs_dir / run_id
            registry = ArtifactRegistry(run_id, run_dir, self._settings.runtime_config)
            summary_path = registry.path_for("summary_json")
            if not summary_path.exists():
                return
            current = json.loads(summary_path.read_text(encoding="utf-8"))
            if isinstance(current, dict):
                current["artifact_publication"] = summary.get("artifact_publication") or {}
                summary_path.write_text(json.dumps(current, indent=2, sort_keys=True), encoding="utf-8")
        except Exception:
            logger.exception("Failed to update summary artifact publication metadata for run_id=%s", run_id)

    def _create_platform_run_record(self, rec: _JobRecord) -> None:
        try:
            record = self._run_repository.create_run_record(
                project_id=rec.request.project_id or "default",
                run_id=rec.run_id,
                execution_id=rec.execution_id,
                request_payload=rec.request.model_dump(mode="json"),
                status=rec.status,
                dataset_snapshot=rec.dataset_snapshot or self._dataset_manifest_payload(user_id=rec.user_id),
                user_id=rec.user_id,
            )
            rec.project_run_number = int(record.get("project_run_number") or rec.project_run_number or 0)
            if rec.queue_message:
                self._run_repository.update_run_record(
                    rec.run_id,
                    {
                        "execution_queue_message": rec.queue_message,
                        "execution_attempts": list(rec.execution_attempts),
                        "cancellation_requested": bool(rec.cancel_requested),
                        "worker_id": rec.worker_id,
                    },
                    user_id=rec.user_id,
                )
        except Exception:
            logger.exception("Failed to persist platform run record for run_id=%s", rec.run_id)

    def _update_platform_run_record(self, rec: _JobRecord, updates: Dict[str, Any] | None = None) -> None:
        payload = {
            "execution_id": rec.execution_id,
            "status": rec.status,
            "stage": rec.stage,
            "progress": max(0.0, min(1.0, float(rec.progress))),
            "message": rec.message,
            "started_at": _fmt_ts(rec.started_at),
            "finished_at": _fmt_ts(rec.finished_at),
            "error": rec.error,
            "execution_queue_message": rec.queue_message,
            "execution_attempts": list(rec.execution_attempts),
            "cancellation_requested": bool(rec.cancel_requested),
            "worker_id": rec.worker_id,
        }
        if rec.summary is not None:
            payload["summary_available"] = True
            payload["artifact_catalog"] = rec.summary.get("artifact_catalog") or []
        if updates:
            payload.update(updates)
        try:
            self._run_repository.update_run_record(rec.run_id, payload, user_id=rec.user_id)
        except Exception:
            logger.exception("Failed to update platform run record for run_id=%s", rec.run_id)

    def _clear_execution_outputs(self, *, execution_id: str, run_id: str) -> None:
        for path in (
            self._settings.runs_dir / str(run_id or ""),
            self._settings.runs_dir / "_queued" / str(execution_id or ""),
        ):
            try:
                if path.exists() and path.is_dir() and path.parent.resolve() in {
                    self._settings.runs_dir.resolve(),
                    (self._settings.runs_dir / "_queued").resolve(),
                }:
                    shutil.rmtree(path)
            except Exception:
                logger.exception("Failed to clear cancelled run artifacts at %s", path)

    def _reset_run_to_draft_after_cancel_locked(self, rec: _JobRecord, *, message: str) -> None:
        self._clear_execution_outputs(execution_id=rec.execution_id, run_id=rec.run_id)
        rec.status = "draft"
        rec.progress = 0.0
        rec.stage = "draft"
        rec.message = message
        rec.error = None
        rec.started_at = None
        rec.finished_at = None
        rec.worker_pid = None
        rec.worker_id = ""
        rec.summary = None
        rec.cancel_requested = False
        rec.queue_message = {}
        rec.execution_attempts = []
        rec.dataset_snapshot = {}
        rec.updated_at = time.time()
        self._update_platform_run_record(
            rec,
            updates={
                "execution_id": "",
                "started_at": None,
                "finished_at": None,
                "error": None,
                "execution_queue_message": {},
                "execution_attempts": [],
                "cancellation_requested": False,
                "worker_id": "",
                "dataset_snapshot": {},
                "artifact_catalog": [],
                "summary_available": False,
            },
        )

    def preflight(self, req: RunRequest, *, user_id: str = LOCAL_USER_ID) -> Dict[str, Any]:
        execution_id = f"preflight_{uuid.uuid4().hex}"
        _, execution_context = self._build_execution_contract(execution_id, uuid.uuid4().hex, req, user_id=user_id, persist_dataset_snapshot=False)
        preflight_fn = getattr(self._runtime, "preflight", None)
        if not callable(preflight_fn):
            return {"ok": True, "message": "Runtime adapter does not expose preflight.", "payload": {}}
        return preflight_fn(execution_context)

    def _queue_position_locked(self, execution_id: str) -> int | None:
        try:
            return self._pending.index(execution_id) + 1
        except ValueError:
            return None

    def _to_job_info_locked(self, rec: _JobRecord, queue_position: int | None) -> RunExecutionInfo:
        artifacts = None
        summary_model = None
        run_artifacts = []
        if rec.run_id and rec.status == "succeeded":
            artifacts = RunArtifacts(
                run_id=rec.run_id,
                summary_url=f"/api/runs/{rec.run_id}/summary",
                csv_url=f"/api/runs/{rec.run_id}/artifacts/results_csv",
            )
        if rec.summary is not None:
            try:
                summary_model = RunSummary(**rec.summary)
                run_artifacts = list(summary_model.artifact_catalog or [])
            except Exception:
                summary_model = None
        return RunExecutionInfo(
            execution_id=rec.execution_id,
            run_id=rec.run_id,
            project_run_number=int(rec.project_run_number or 0),
            status=rec.status,
            progress=max(0.0, min(1.0, float(rec.progress))),
            stage=rec.stage,
            message=rec.message,
            queue_position=queue_position,
            created_at=_fmt_ts(rec.created_at) or "",
            started_at=_fmt_ts(rec.started_at),
            finished_at=_fmt_ts(rec.finished_at),
            updated_at=_fmt_ts(rec.updated_at),
            worker_pid=rec.worker_pid,
            worker_id=rec.worker_id,
            cancellation_requested=bool(rec.cancel_requested),
            execution_queue_message=rec.queue_message,
            execution_attempts=list(rec.execution_attempts),
            error=rec.error,
            request=rec.request,
            artifacts=artifacts,
            summary=summary_model,
            run_artifacts=run_artifacts,
        )

    def _trim_history_locked(self) -> None:
        limit = max(1, int(self._settings.job_history_limit))
        if len(self._jobs) <= limit:
            return
        finished = [j for j in self._jobs.values() if j.status in FINAL_JOB_STATUSES]
        finished.sort(key=lambda x: x.created_at)
        while len(self._jobs) > limit and finished:
            victim = finished.pop(0)
            self._jobs.pop(victim.execution_id, None)
            if victim.execution_id in self._pending:
                self._pending.remove(victim.execution_id)

    def _can_accept_locked(self, count: int) -> bool:
        capacity = max(1, int(self._settings.job_queue_capacity))
        active = sum(1 for rec in self._jobs.values() if rec.status in {"queued", "running"})
        return (active + max(0, int(count))) <= capacity

    def _request_fingerprint(self, req: RunRequest, *, user_id: str = LOCAL_USER_ID) -> str:
        payload = {
            "request": req.model_dump(mode="json"),
            "solver": self._settings.solver,
            "model_runtime": self._runtime_manifest.to_dict(),
            "dataset_staging_mode": getattr(self._settings, "dataset_staging_mode", "copy_to_run"),
            "user_id": user_id,
            "input_fingerprint": self._input_fingerprint(user_id),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _input_fingerprint(self, user_id: str = LOCAL_USER_ID) -> list[str]:
        out: list[str] = []
        dataset_manifest = self._dataset_repository.runtime_dataset_manifest(user_id=user_id)
        for row in dataset_manifest.get("datasets", []):
            path = self._path_for_fingerprint(row.get("path"))
            try:
                stat = path.stat()
                out.append(f"{row.get('id', path.name)}:{stat.st_mtime_ns}:{stat.st_size}")
            except Exception:
                out.append(f"{row.get('id', 'unknown')}:missing")
        return out

    @staticmethod
    def _path_for_fingerprint(path_value: Any):
        from pathlib import Path

        return Path(str(path_value or "")).expanduser()

    def _find_reusable_job_locked(self, request_fingerprint: str) -> _JobRecord | None:
        if not self._settings.job_dedupe_enabled:
            return None
        records = [rec for rec in self._jobs.values() if rec.request_fingerprint == request_fingerprint]
        if not records:
            return None
        active = [rec for rec in records if rec.status in {"queued", "running"}]
        if active:
            active.sort(key=lambda x: x.created_at, reverse=True)
            return active[0]
        succeeded = [
            rec
            for rec in records
            if rec.status == "succeeded"
            and rec.run_id
            and rec.summary is not None
            and (self._settings.runs_dir / rec.run_id).exists()
        ]
        if succeeded:
            succeeded.sort(key=lambda x: x.created_at, reverse=True)
            return succeeded[0]
        return None

    def _update_progress(self, execution_id: str, stage: str, progress: float, message: str) -> None:
        with self._lock:
            rec = self._jobs.get(execution_id)
            if rec is None:
                return
            if rec.cancel_requested and rec.status == "running":
                rec.stage = "cancelling"
                rec.message = "Cancellation requested; terminating model runtime at the next adapter checkpoint."
                rec.updated_at = time.time()
                self._update_current_attempt_locked(
                    rec,
                    status="cancelling",
                    heartbeat_at=_fmt_ts(rec.updated_at) or "",
                    cancellation_requested=True,
                    message=rec.message,
                )
                self._update_platform_run_record(rec)
                return
            rec.stage = stage
            rec.progress = max(0.0, min(1.0, float(progress)))
            rec.message = message
            rec.updated_at = time.time()
            self._update_current_attempt_locked(
                rec,
                status="running",
                heartbeat_at=_fmt_ts(rec.updated_at) or "",
                cancellation_requested=bool(rec.cancel_requested),
                message=message,
            )
            self._update_platform_run_record(rec)

    def _is_cancel_requested(self, execution_id: str) -> bool:
        with self._lock:
            rec = self._jobs.get(execution_id)
            return bool(rec and rec.cancel_requested)

    def _append_result_event_if_missing(self, execution_id: str, result: Any) -> None:
        try:
            events = self._event_store.read_events(execution_id)
        except Exception:
            events = []
        if any(str(row.get("type") or "") == "result" for row in events if isinstance(row, dict)):
            return
        self._event_store.append_event(
            execution_id,
            RuntimeEvent(
                type="result",
                stage="complete",
                progress=1.0,
                message="Run completed",
                run_id=str(result.run_id),
                payload={"summary": result.summary, "warnings": list(getattr(result, "warnings", []) or [])},
            ),
        )

    def _emit_runtime_heartbeat(self, execution_id: str, *, started_at: float, last_event_at: float) -> None:
        now = time.time()
        with self._lock:
            rec = self._jobs.get(execution_id)
            if rec is None or rec.status != "running":
                return
            elapsed = _fmt_elapsed(now - started_at)
            since_event = _fmt_elapsed(now - last_event_at)
            if str(rec.stage or "").strip().lower() == "solve_energy":
                rec.message = f"Solving energy optimization problem (elapsed {elapsed}, {since_event} since last runtime event)"
            else:
                rec.message = f"{rec.message or 'Running'} (elapsed {elapsed})"
            rec.updated_at = now
            self._update_current_attempt_locked(
                rec,
                status="running",
                heartbeat_at=_fmt_ts(now) or "",
                cancellation_requested=bool(rec.cancel_requested),
                message=rec.message,
            )
            self._update_platform_run_record(rec)

    def _worker_loop(self) -> None:
        while True:
            raw_queue_message = self._queue.get()
            try:
                queue_message = self._coerce_queue_message(raw_queue_message)
            except Exception:
                logger.exception("Invalid execution queue message received")
                self._queue.task_done()
                continue
            execution_id = queue_message.execution_id
            with self._lock:
                rec = self._jobs.get(execution_id)
                if rec is None:
                    self._queue.task_done()
                    continue
                rec.queue_message = rec.queue_message or queue_message.to_dict()
                if rec.status == "draft":
                    self._queue.task_done()
                    continue
                if rec.status == "cancelled" or rec.cancel_requested:
                    if execution_id in self._pending:
                        self._pending.remove(execution_id)
                    self._reset_run_to_draft_after_cancel_locked(rec, message="Run cancelled before start; draft restored.")
                    self._queue.task_done()
                    continue
                rec.status = "running"
                rec.started_at = time.time()
                rec.progress = max(rec.progress, 0.05)
                rec.stage = "starting"
                rec.message = "Starting run"
                rec.updated_at = rec.started_at
                if execution_id in self._pending:
                    self._pending.remove(execution_id)
                self._start_execution_attempt_locked(rec, queue_message)
                self._update_platform_run_record(rec)

            try:
                execution_request, execution_context = self._build_execution_contract(
                    execution_id,
                    rec.run_id,
                    rec.request,
                    user_id=rec.user_id,
                    queue_message=rec.queue_message or queue_message.to_dict(),
                    dataset_manifest=rec.dataset_snapshot,
                )
                result = self._runtime.execute(
                    execution_request,
                    execution_context,
                    progress_callback=lambda stage, progress, message: self._update_progress(execution_id, stage, progress, message),
                    cancel_requested=lambda: self._is_cancel_requested(execution_id),
                )
                if self._is_cancel_requested(execution_id):
                    raise RuntimeError("Run cancelled by user request.")
                self._publish_runtime_artifacts(result)
                self._append_result_event_if_missing(execution_id, result)
                with self._lock:
                    if rec.cancel_requested:
                        rec.status = "cancelled"
                        rec.progress = 1.0
                        rec.stage = "cancelled"
                        rec.message = "Run cancelled."
                        rec.error = "Cancelled by user."
                    else:
                        rec.status = "succeeded"
                        rec.progress = 1.0
                        rec.stage = "complete"
                        rec.message = "Run completed"
                        rec.run_id = result.run_id
                        rec.summary = result.summary
                    rec.finished_at = time.time()
                    rec.updated_at = rec.finished_at
                    self._finish_execution_attempt_locked(rec, status=rec.status, error=rec.error)
                    self._update_platform_run_record(rec)
            except Exception as exc:  # pragma: no cover - guarded by API tests
                if self._is_cancel_requested(execution_id):
                    logger.info("Run cancelled for execution_id=%s", execution_id)
                else:
                    logger.exception("Asynchronous run failed for execution_id=%s", execution_id)
                with self._lock:
                    if rec.cancel_requested:
                        self._reset_run_to_draft_after_cancel_locked(rec, message="Run cancelled; draft restored.")
                    else:
                        rec.status = "failed"
                        rec.error = str(exc)
                        rec.stage = "failed"
                        rec.message = "Run failed"
                        rec.progress = 1.0
                        rec.finished_at = time.time()
                        rec.updated_at = rec.finished_at
                        self._finish_execution_attempt_locked(rec, status=rec.status, error=rec.error)
                        self._update_platform_run_record(rec)
            finally:
                with self._lock:
                    self._trim_history_locked()
                self._queue.task_done()
