"""Isolated compute worker daemon.

The worker is a pure compute consumer. It has no access to PostgreSQL
and no backend service imports. It communicates with the rest of the
platform exclusively through:

  - Azure Service Bus (execution, cancellation, and completion queues)
  - Azure Blob Storage (input datasets, run artifacts, runtime event logs)

Authentication uses DefaultAzureCredential / System-Assigned Managed
Identity in staging/production; local dev falls back to emulator
connection strings.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("edim-worker")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utcnow_iso() -> str:
    return _utcnow().isoformat()


class WorkerConfig:
    def __init__(self) -> None:
        self.worker_id = os.getenv("EDIM_WORKER_ID", f"edim-worker-{uuid.uuid4().hex[:8]}")

        # Paths
        self.calliope_root = Path(os.getenv("EDIM_CALLIOPE_ROOT", "/app/calliope-africa"))
        self.runs_dir = Path(os.getenv("EDIM_RUNS_DIR", "/app/outputs/runs"))
        self.config_dir = Path(os.getenv("EDIM_CONFIG_DIR", "/app/inputs"))
        self.runtime_config_path = Path(os.getenv("EDIM_RUNTIME_CONFIG", "/app/inputs/runtime_config.json"))

        # Timing / reliability
        self.lock_renewal_seconds = int(os.getenv("EDIM_WORKER_LOCK_RENEWAL_SECONDS", "60"))
        self.polling_interval_seconds = float(os.getenv("EDIM_WORKER_POLL_INTERVAL", "5"))
        self.max_run_seconds = float(os.getenv("EDIM_WORKER_MAX_RUN_SECONDS", "3600"))
        self.cancellation_poll_seconds = float(os.getenv("EDIM_WORKER_CANCELLATION_POLL_SECONDS", "5"))
        self.max_attempts = int(os.getenv("EDIM_WORKER_MAX_ATTEMPTS", "3"))

        # Service Bus
        self.servicebus_connection_string = os.getenv("EDIM_SERVICEBUS_CONNECTION_STRING", "").strip()
        self.servicebus_namespace = os.getenv("EDIM_SERVICEBUS_NAMESPACE", "").strip()
        self.servicebus_use_connection_string = _env_bool(
            "EDIM_SERVICEBUS_USE_CONNECTION_STRING", bool(self.servicebus_connection_string)
        )
        self.execution_queue_name = os.getenv("EDIM_SERVICEBUS_QUEUE_NAME", "execution-queue-local").strip()
        self.cancellation_queue_name = os.getenv(
            "EDIM_SERVICEBUS_CANCELLATION_QUEUE_NAME", "cancellation-queue-local"
        ).strip()
        self.completion_queue_name = os.getenv(
            "EDIM_SERVICEBUS_COMPLETION_QUEUE_NAME", "completion-queue-local"
        ).strip()

        # Blob storage
        self.blob_account_url = os.getenv("EDIM_BLOB_ACCOUNT_URL", "").strip()
        self.blob_connection_string = os.getenv("EDIM_AZURITE_CONNECTION_STRING", "").strip() or os.getenv(
            "EDIM_BLOB_CONNECTION_STRING", ""
        ).strip()
        self.blob_container_prefix = os.getenv("EDIM_BLOB_CONTAINER_PREFIX", "stg-").strip()
        self.blob_use_connection_string = _env_bool("EDIM_BLOB_USE_CONNECTION_STRING", bool(self.blob_connection_string))

        # Artifact retention policy from runtime_config.json
        self.artifact_policy = _load_artifact_policy(self.runtime_config_path)

    def servicebus_client(self):
        from azure.servicebus import ServiceBusClient

        if self.servicebus_use_connection_string and self.servicebus_connection_string:
            return ServiceBusClient.from_connection_string(self.servicebus_connection_string)
        if not self.servicebus_namespace:
            raise RuntimeError(
                "Set EDIM_SERVICEBUS_NAMESPACE (or EDIM_SERVICEBUS_CONNECTION_STRING for emulator)."
            )
        namespace = self.servicebus_namespace.rstrip("/")
        if not namespace.startswith("sb://"):
            namespace = f"sb://{namespace}"
        from azure.identity import DefaultAzureCredential

        return ServiceBusClient(fully_qualified_namespace=namespace, credential=DefaultAzureCredential())

    def blob_service_client(self):
        from azure.storage.blob import BlobServiceClient

        if self.blob_use_connection_string and self.blob_connection_string:
            return BlobServiceClient.from_connection_string(self.blob_connection_string)
        if not self.blob_account_url:
            raise RuntimeError(
                "Set EDIM_BLOB_ACCOUNT_URL (or EDIM_AZURITE_CONNECTION_STRING for emulator)."
            )
        from azure.identity import DefaultAzureCredential

        return BlobServiceClient(account_url=self.blob_account_url, credential=DefaultAzureCredential())


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _load_artifact_policy(runtime_config_path: Path) -> dict:
    if not runtime_config_path.is_file():
        return {}
    try:
        payload = json.loads(runtime_config_path.read_text(encoding="utf-8"))
        return payload.get("artifacts", {}) if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


# ---------------------------------------------------------------------------
# Service Bus helpers
# ---------------------------------------------------------------------------


class _ActiveLease:
    """Wraps a received Service Bus message and a background lease-renewer."""

    def __init__(self, sb_message, receiver) -> None:
        self.sb_message = sb_message
        self.receiver = receiver
        self._stop = threading.Event()
        self._lock_lost = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start_renewer(self, interval_seconds: int) -> None:
        def _loop() -> None:
            while not self._stop.wait(interval_seconds):
                try:
                    self.receiver.renew_message_lock(self.sb_message)
                    logger.debug("Renewed SB lock for %s", self.sb_message.message_id)
                except Exception as _renew_exc:
                    from azure.servicebus.exceptions import ServiceBusError
                    if isinstance(_renew_exc, ServiceBusError):
                        logger.warning(
                            "SB lock renewal failed for %s (%s); lock may expire before job finishes",
                            self.sb_message.message_id, _renew_exc,
                        )
                    else:
                        logger.exception("Failed to renew SB lock for %s", self.sb_message.message_id)
                    self._lock_lost.set()
                    return

        with self._lock:
            if self._thread is None:
                self._thread = threading.Thread(
                    target=_loop, daemon=True, name=f"edim-sb-renewer-{self.sb_message.message_id}"
                )
                self._thread.start()

    def stop_renewer(self) -> None:
        with self._lock:
            if self._thread is not None:
                self._stop.set()
                self._thread.join(timeout=2)
                self._thread = None

    def complete(self) -> None:
        self.stop_renewer()
        try:
            self.receiver.complete_message(self.sb_message)
        except Exception as _complete_exc:
            from azure.servicebus.exceptions import MessageLockLostError
            if isinstance(_complete_exc, MessageLockLostError):
                logger.warning(
                    "Cannot complete message %s: lock was lost; message will be redelivered",
                    self.sb_message.message_id,
                )
            else:
                raise

    def abandon(self) -> None:
        self.stop_renewer()
        self.receiver.abandon_message(self.sb_message)

    def dead_letter(self, reason: str) -> None:
        self.stop_renewer()
        try:
            self.receiver.dead_letter_message(self.sb_message, reason=reason)
        except ValueError:
            # Receiver was already closed (e.g. connection reset during long run).
            # Abandon so the message returns to the queue rather than being lost.
            logger.warning("Receiver shut down before dead-letter; abandoning message instead (reason=%s)", reason)
            try:
                self.receiver.abandon_message(self.sb_message)
            except Exception:
                logger.exception("Failed to abandon message after dead-letter failure")


def _send_json(client, queue_name: str, payload: dict, message_id: Optional[str] = None) -> None:
    from azure.servicebus import ServiceBusMessage

    body = json.dumps(payload).encode("utf-8")
    sb_message = ServiceBusMessage(
        body=body,
        content_type="application/json",
        message_id=message_id,
        correlation_id=payload.get("run_id"),
    )
    # Only close the *sender*, not the entire ServiceBusClient.  Closing the
    # client would burn through the shared instance, causing subsequent calls
    # (e.g. _send_completion after _send_running) to fail silently and leave
    # the Service Bus message un-completed, triggering a redelivery loop.
    with client.get_queue_sender(queue_name=queue_name) as sender:
        sender.send_messages(sb_message)


# ---------------------------------------------------------------------------
# Blob helpers
# ---------------------------------------------------------------------------


def _ensure_container(blob_client, container_name: str) -> None:
    try:
        blob_client.create_container(name=container_name)
    except Exception as exc:
        if "ContainerAlreadyExists" not in str(exc) and "AlreadyExists" not in str(exc):
            logger.warning("Could not create container %s: %s", container_name, exc)


def _blob_name_from_uri(uri: str) -> Optional[str]:
    try:
        from urllib.parse import urlparse

        parts = urlparse(uri)
        path = parts.path.lstrip("/")
        segments = path.split("/", 2)
        if len(segments) >= 3 and segments[0] == "devstoreaccount1":
            return segments[2]
        if len(segments) >= 2:
            return "/".join(segments[1:])
        return None
    except Exception:
        return None


def _download_datasets(
    config: WorkerConfig,
    blob_client,
    dataset_versions: list[dict],
    workspace: Path,
) -> None:
    if not dataset_versions:
        return
    datasets_dir = workspace / "inputs" / "datasets"
    datasets_dir.mkdir(parents=True, exist_ok=True)
    container_name = f"{config.blob_container_prefix}input-datasets"
    _ensure_container(blob_client, container_name)
    container = blob_client.get_container_client(container_name)

    for item in dataset_versions:
        dataset_id = item["dataset_id"]
        version_id = item["version_id"]
        storage_uri = item.get("storage_uri", "")
        blob_name = _blob_name_from_uri(storage_uri)
        if not blob_name:
            raise RuntimeError(f"Cannot parse storage_uri for dataset version {version_id}: {storage_uri}")
        local_path = datasets_dir / f"{dataset_id}_{version_id}"
        logger.info("Downloading dataset %s version %s -> %s", dataset_id, version_id, local_path)
        blob = container.get_blob_client(blob_name)
        with open(local_path, "wb") as fh:
            downloader = blob.download_blob()
            downloader.readinto(fh)


def _upload_artifacts(
    config: WorkerConfig,
    blob_client,
    artifact_root: Path,
    run_id: str,
    artifact_catalog: dict,
) -> list[dict]:
    if artifact_root.joinpath("artifacts").is_dir():
        source_dir = artifact_root / "artifacts"
    else:
        source_dir = artifact_root

    container_name = f"{config.blob_container_prefix}run-artifacts"
    _ensure_container(blob_client, container_name)
    container = blob_client.get_container_client(container_name)

    skip_dirs = {"inputs", "work", "logs"}
    uploaded: list[dict] = []
    for path in source_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(source_dir).as_posix()
        catalog_entry = artifact_catalog.get(rel, {})
        if not catalog_entry.get("retain_on_success", True):
            logger.info("Skipping artifact %s (retain_on_success=false)", rel)
            continue
        if rel.split("/", 1)[0] in skip_dirs:
            continue
        blob_name = f"{run_id}/{rel}"
        logger.info("Uploading artifact %s -> %s/%s", path, container_name, blob_name)
        with open(path, "rb") as fh:
            container.upload_blob(name=blob_name, data=fh, overwrite=True)
        uploaded.append(
            {
                "artifact_id": rel,
                "provider": "azure_blob",
                "container": container_name,
                "object_key": blob_name,
            }
        )
    return uploaded


def _append_event_to_blob(
    config: WorkerConfig,
    blob_client,
    execution_id: str,
    event_line: str,
) -> None:
    """Append a single JSONL event line to an append blob in the logs container."""
    container_name = f"{config.blob_container_prefix}logs"
    _ensure_container(blob_client, container_name)
    blob_name = f"{execution_id}/runtime_events.jsonl"
    blob = blob_client.get_blob_client(container_name, blob_name)
    line = event_line.encode("utf-8") + b"\n"
    try:
        # AppendBlob may not exist yet; create if needed.
        try:
            blob.append_block(line)
        except Exception as exc:
            if "BlobNotFound" in str(exc) or "does not exist" in str(exc):
                blob.create_append_blob()
                blob.append_block(line)
            else:
                raise
    except Exception:
        logger.exception("Failed to append event to blob for %s", execution_id)


# ---------------------------------------------------------------------------
# Run execution
# ---------------------------------------------------------------------------


def _stage_workspace(config: WorkerConfig, execution_id: str, bundle: dict) -> Path:
    workspace = config.runs_dir / execution_id
    inputs_dir = workspace / "inputs"
    artifacts_dir = workspace / "artifacts"
    logs_dir = workspace / "logs"
    work_dir = workspace / "work"
    for d in (inputs_dir, artifacts_dir, logs_dir, work_dir):
        d.mkdir(parents=True, exist_ok=True)

    bundle_path = inputs_dir / "request_bundle.json"
    bundle_path.write_text(
        json.dumps(bundle, indent=2, default=str),
        encoding="utf-8",
    )
    return workspace


def _purge_workspace(workspace: Path) -> None:
    try:
        shutil.rmtree(workspace)
    except FileNotFoundError:
        pass
    except Exception:
        logger.exception("Failed to purge workspace %s", workspace)


class _EventLog:
    """Local JSONL event log that also mirrors to Blob append storage."""

    def __init__(self, config: WorkerConfig, blob_client, execution_id: str, run_id: str, log_path: Path) -> None:
        self._config = config
        self._blob_client = blob_client
        self._execution_id = execution_id
        self._run_id = run_id
        self._log_path = log_path
        self._lock = threading.Lock()

    def append(self, level: str, stage: str, message: str, payload: Optional[dict] = None) -> None:
        event = {
            "timestamp": _utcnow_iso(),
            "execution_id": self._execution_id,
            "run_id": self._run_id,
            "level": level,
            "stage": stage,
            "message": message,
            "payload": payload,
        }
        line = json.dumps(event, default=str)
        with self._lock:
            with open(self._log_path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        _append_event_to_blob(self._config, self._blob_client, self._execution_id, line)


def _run_cli(
    args: list[str],
    cwd: Path,
    env: dict,
    event_log: _EventLog,
    cancel_event: threading.Event,
    max_seconds: float,
) -> tuple[int, Optional[str]]:
    proc = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    last_json_line: Optional[str] = None

    def _stdout_reader() -> None:
        nonlocal last_json_line
        try:
            if proc.stdout is None:
                return
            for line in proc.stdout:
                line = line.rstrip("\n")
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    event_log.append(level="info", stage="worker", message=line, payload={"stream": "stdout"})
                    continue
                if isinstance(payload, dict) and ("stage" in payload or "level" in payload or "message" in payload):
                    event_log.append(
                        level=payload.get("level", "info"),
                        stage=payload.get("stage", ""),
                        message=payload.get("message", ""),
                        payload=payload.get("payload"),
                    )
                last_json_line = line
        except Exception:
            logger.exception("stdout reader failed")

    def _stderr_reader() -> None:
        try:
            if proc.stderr is None:
                return
            for line in proc.stderr:
                line = line.rstrip("\n")
                event_log.append(level="error", stage="worker", message=line, payload={"stream": "stderr"})
                logger.info("subprocess: %s", line)
        except Exception:
            logger.exception("stderr reader failed")

    stdout_thread = threading.Thread(target=_stdout_reader, name=f"stdout-{event_log._execution_id}", daemon=True)
    stderr_thread = threading.Thread(target=_stderr_reader, name=f"stderr-{event_log._execution_id}", daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    start = time.monotonic()
    try:
        while proc.poll() is None:
            if cancel_event.is_set():
                logger.warning("Cancellation requested; terminating subprocess for %s", event_log._execution_id)
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
                return 130, None
            if time.monotonic() - start > max_seconds:
                logger.error("Run exceeded max runtime of %s seconds; terminating.", max_seconds)
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
                return 124, None
            time.sleep(0.5)
    finally:
        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)

    return proc.returncode, last_json_line


def _poll_cancellation_queue(
    config: WorkerConfig,
    cancellation_client,
    execution_id: str,
    cancel_event: threading.Event,
) -> None:
    """Background thread: check the cancellation queue for this execution."""
    while not cancel_event.is_set():
        try:
            # Build a fresh client per iteration — the shared cancellation_client
            # is a ServiceBusClient that gets closed by the `with` context manager.
            fresh_client = config.servicebus_client()
            with fresh_client:
                receiver = fresh_client.get_queue_receiver(queue_name=config.cancellation_queue_name, prefetch=1)
                with receiver:
                    messages = receiver.receive_messages(max_message_count=1, max_wait_time=1)
                    if messages:
                        msg = messages[0]
                        body_parts = msg.body
                        body_bytes = body_parts if isinstance(body_parts, (bytes, bytearray)) else b"".join(body_parts)
                        payload = json.loads(body_bytes.decode("utf-8"))
                        if payload.get("execution_id") == execution_id or payload.get("run_id") == execution_id:
                            cancel_event.set()
                            receiver.complete_message(msg)
                            logger.warning("Cancellation message received for execution_id=%s", execution_id)
                        else:
                            receiver.abandon_message(msg)
        except Exception:
            logger.exception("Cancellation queue poll error")
        time.sleep(config.cancellation_poll_seconds)


# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------


def _execute_payload(
    config: WorkerConfig,
    execution_client,
    completion_client,
    cancellation_client,
    blob_client,
    payload: dict,
) -> None:
    run_id = payload["run_id"]
    execution_id = payload["execution_id"]
    attempt_count = int(payload.get("attempt_count", 1))
    dataset_versions = payload.get("dataset_versions", [])

    # When the API has already constructed a complete model_run_bundle_v1
    # (signalled by the presence of "schema_version"), pass it directly to
    # the black-box CLI without reconstruction.
    if "schema_version" in payload:
        bundle = dict(payload)
    else:
        request_payload = payload.get("request_payload") or {}
        bundle = {
            "execution_id": execution_id,
            "run_id": run_id,
            "project_id": payload.get("project_id"),
            "user_id": payload.get("user_id"),
            "request_payload": request_payload,
            "dataset_versions": dataset_versions,
            "attempt_count": attempt_count,
        }

    # Clean up stale directories from prior attempts (retry safety).
    # The model runtime's _create_run_dir uses mkdir(exist_ok=False).
    for stale in (config.runs_dir / run_id, config.runs_dir / execution_id):
        if stale.exists():
            shutil.rmtree(stale)

    workspace = _stage_workspace(config, execution_id, bundle)

    # Upload the request bundle to blob for traceability (plan 7 / issue 7).
    try:
        _bundle_container = f"{config.blob_container_prefix}execution-bundles"
        _ensure_container(blob_client, _bundle_container)
        blob_client.get_container_client(_bundle_container).upload_blob(
            name=f"{execution_id}/request_bundle.json",
            data=(workspace / "inputs" / "request_bundle.json").read_bytes(),
            overwrite=True,
        )
    except Exception:
        logger.warning("Failed to upload execution bundle for %s; continuing.", execution_id)

    log_path = workspace / "logs" / "runtime_events.jsonl"
    event_log = _EventLog(config, blob_client, execution_id, run_id, log_path)
    event_log.append(
        level="milestone",
        stage="worker_setup",
        message="Worker accepted execution",
        payload={"worker_id": config.worker_id, "attempt_count": attempt_count},
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + ":" + env.get("PYTHONPATH", "")
    env["EDIM_RUNS_DIR"] = str(workspace)

    repo_root = Path(__file__).resolve().parents[1]
    outcome = "failed"
    error: Optional[str] = None
    summary: Optional[dict] = None
    should_retry = False
    started_at = _utcnow_iso()
    cancel_event = threading.Event()

    _send_running(config, completion_client, execution_id, run_id, attempt_count, started_at)

    cancel_thread = threading.Thread(
        target=_poll_cancellation_queue,
        args=(config, cancellation_client, execution_id, cancel_event),
        daemon=True,
        name=f"edim-cancel-poller-{execution_id}",
    )
    cancel_thread.start()

    try:
        _download_datasets(config, blob_client, dataset_versions, workspace)

        event_log.append(level="milestone", stage="preflight", message="Running preflight checks")
        rc, _ = _run_cli(
            [sys.executable, "-m", "edim_model.cli", "preflight", "--bundle", str(workspace / "inputs" / "request_bundle.json")],
            cwd=repo_root,
            env=env,
            event_log=event_log,
            cancel_event=cancel_event,
            max_seconds=300,
        )
        if rc != 0:
            error = f"preflight failed with rc={rc}"
            logger.error("Preflight failed for run %s", run_id)
            _send_completion(config, completion_client, execution_id, run_id, "failed", attempt_count, error, None, [], started_at, blob_client=blob_client)
            return

        event_log.append(level="milestone", stage="model_run", message="Starting model solve")
        rc, last_json_line = _run_cli(
            [sys.executable, "-m", "edim_model.cli", "run", "--bundle", str(workspace / "inputs" / "request_bundle.json")],
            cwd=repo_root,
            env=env,
            event_log=event_log,
            cancel_event=cancel_event,
            max_seconds=config.max_run_seconds,
        )

        if cancel_event.is_set() or rc == 130:
            outcome = "cancelled"
            error = "Cancelled by user."
        elif rc == 0:
            outcome = "succeeded"
            if last_json_line:
                try:
                    summary = json.loads(last_json_line)
                except Exception:
                    summary = None
            artifact_catalog = config.artifact_policy.get("manifest", {})
            try:
                artifact_root = workspace
                if isinstance(summary, dict) and summary.get("run_dir"):
                    candidate = Path(summary["run_dir"])
                    if candidate.is_dir():
                        artifact_root = candidate
                storage_refs = _upload_artifacts(config, blob_client, artifact_root, run_id, artifact_catalog)
                if summary is None:
                    summary = {}
                summary["artifact_catalog"] = storage_refs
            except Exception as exc:
                logger.exception("Artifact upload failed for run %s", run_id)
                outcome = "failed"
                error = f"artifact upload failed: {exc}"
                should_retry = True
        elif rc == 124:
            error = f"run exceeded max runtime of {config.max_run_seconds}s"
            should_retry = True
        else:
            error = f"run failed with rc={rc}"
            should_retry = True

    except Exception as exc:
        logger.exception("Run execution crashed for %s", run_id)
        error = f"execution exception: {exc}"
        should_retry = True
    finally:
        cancel_event.set()
        cancel_thread.join(timeout=2)
        _purge_workspace(workspace)

    finished_at = _utcnow_iso()

    if should_retry and attempt_count < config.max_attempts:
        _requeue_execution(config, execution_client, payload)
        return

    _send_completion(
        config,
        completion_client,
        execution_id,
        run_id,
        outcome,
        attempt_count,
        error,
        summary,
        summary.get("artifact_catalog", []) if isinstance(summary, dict) else [],
        started_at,
        finished_at,
        blob_client=blob_client,
    )


def _send_completion(
    config: WorkerConfig,
    completion_client,
    execution_id: str,
    run_id: str,
    outcome: str,
    attempt_count: int,
    error: Optional[str],
    summary: Optional[dict],
    artifact_storage_refs: list[dict],
    started_at: str,
    finished_at: Optional[str] = None,
    blob_client=None,
) -> None:
    summary_ref: Optional[dict] = None
    if summary is not None and blob_client is not None:
        try:
            container_name = f"{config.blob_container_prefix}run-artifacts"
            _ensure_container(blob_client, container_name)
            blob_name = f"{run_id}/summary.json"
            container = blob_client.get_container_client(container_name)
            container.upload_blob(
                name=blob_name,
                data=json.dumps(summary, default=str).encode("utf-8"),
                overwrite=True,
            )
            summary_ref = {
                "provider": "azure_blob",
                "container": container_name,
                "object_key": blob_name,
            }
            logger.info("Uploaded summary to blob %s/%s", container_name, blob_name)
        except Exception:
            logger.exception("Failed to upload summary to blob for execution_id=%s; inlining instead", execution_id)
            summary_ref = None

    payload = {
        "execution_id": execution_id,
        "run_id": run_id,
        "worker_id": config.worker_id,
        "outcome": outcome,
        "attempt_count": attempt_count,
        "error": error,
        "summary": None if summary_ref else summary,
        "summary_ref": summary_ref,
        "artifact_catalog": artifact_storage_refs,
        "started_at": started_at,
        "finished_at": finished_at or _utcnow_iso(),
    }
    try:
        _send_json(completion_client, config.completion_queue_name, payload, message_id=execution_id)
        logger.info("Sent completion for execution_id=%s outcome=%s", execution_id, outcome)
    except Exception:
        logger.exception("Failed to send completion for execution_id=%s", execution_id)


def _send_running(
    config: "WorkerConfig",
    completion_client,
    execution_id: str,
    run_id: str,
    attempt_count: int,
    started_at: str,
) -> None:
    """Notify the API that the worker has accepted and started this execution."""
    payload = {
        "execution_id": execution_id,
        "run_id": run_id,
        "worker_id": config.worker_id,
        "outcome": "running",
        "attempt_count": attempt_count,
        "started_at": started_at,
    }
    try:
        _send_json(completion_client, config.completion_queue_name, payload, message_id=f"{execution_id}_running")
        logger.info("Sent running notification for execution_id=%s", execution_id)
    except Exception:
        logger.exception("Failed to send running notification for execution_id=%s", execution_id)


def _requeue_execution(config: WorkerConfig, execution_client, payload: dict) -> None:
    payload["attempt_count"] = int(payload.get("attempt_count", 1)) + 1
    try:
        _send_json(execution_client, config.execution_queue_name, payload, message_id=payload.get("execution_id"))
        logger.warning(
            "Re-queued execution_id=%s attempt %s", payload.get("execution_id"), payload["attempt_count"]
        )
    except Exception:
        logger.exception("Failed to re-queue execution_id=%s", payload.get("execution_id"))


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def _process_one(config: WorkerConfig, execution_client, completion_client, cancellation_client, blob_client) -> bool:
    receiver = execution_client.get_queue_receiver(queue_name=config.execution_queue_name, prefetch=1)
    with receiver:
        messages = receiver.receive_messages(
            max_message_count=1,
            max_wait_time=int(config.polling_interval_seconds),
        )
        if not messages:
            return False
        sb_message = messages[0]
        body_parts = sb_message.body
        if isinstance(body_parts, (bytes, bytearray)):
            body_bytes = body_parts
        else:
            body_bytes = b"".join(body_parts)  # handles list, tuple, and generator (azure-servicebus 7.x)
        payload = json.loads(body_bytes.decode("utf-8"))
        execution_id = payload.get("execution_id")
        logger.info("Received SB message execution_id=%s", execution_id)

        # Complete the Service Bus message immediately so the emulator does not
        # redeliver it when lock renewal fails (a known issue with the local
        # Service Bus emulator).  Status is tracked exclusively through the
        # completion queue, so the API knows the run outcome even if the
        # worker crashes after this point.
        try:
            receiver.complete_message(sb_message)
            logger.info("Completed SB message execution_id=%s (immediate settlement)", execution_id)
        except Exception:
            logger.warning("Could not complete SB message for execution_id=%s; continuing anyway", execution_id, exc_info=True)

        try:
            _execute_payload(config, execution_client, completion_client, cancellation_client, blob_client, payload)
        except Exception:
            logger.exception("Run failed for execution_id=%s", execution_id)
    return True


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Allow EDIM_SB_LOG_LEVEL to override Azure Service Bus verbosity.
    # Set to DEBUG in docker-compose / env to see raw AMQP frames and
    # message settlement traces. Defaults to WARNING to keep logs clean.
    _sb_level_name = os.getenv("EDIM_SB_LOG_LEVEL", "WARNING").upper()
    _sb_level = getattr(logging, _sb_level_name, logging.WARNING)
    for _sb_logger in (
        "azure.servicebus",
        "azure.servicebus._pyamqp",
        "azure.core.pipeline.policies.http_logging_policy",
    ):
        logging.getLogger(_sb_logger).setLevel(_sb_level)

    config = WorkerConfig()
    logger.info("Starting EDIM worker: id=%s", config.worker_id)

    def _make_sb_clients():
        return (
            config.servicebus_client(),
            config.servicebus_client(),
            config.servicebus_client(),
        )

    try:
        execution_client, completion_client, cancellation_client = _make_sb_clients()
        logger.info("Service Bus clients ready")
    except Exception as exc:
        logger.error("Failed to create Service Bus client: %s", exc)
        return 1

    try:
        blob_client = config.blob_service_client()
        logger.info("Blob Storage client ready")
    except Exception as exc:
        logger.error("Failed to create Blob Storage client: %s", exc)
        return 1

    while True:
        try:
            processed = _process_one(config, execution_client, completion_client, cancellation_client, blob_client)
        except Exception as exc:
            from azure.servicebus.exceptions import ServiceBusConnectionError, ServiceBusError
            if isinstance(exc, (ServiceBusConnectionError, ServiceBusError)) or "amqp" in str(exc).lower() or "socket" in str(exc).lower():
                logger.warning("Service Bus connection error, recreating clients: %s", exc)
                try:
                    execution_client, completion_client, cancellation_client = _make_sb_clients()
                    logger.info("Service Bus clients recreated")
                except Exception:
                    logger.exception("Failed to recreate Service Bus clients")
            else:
                logger.exception("Worker loop error")
            processed = False
        if not processed:
            time.sleep(config.polling_interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
