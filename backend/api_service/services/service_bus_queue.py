"""Azure Service Bus implementation of the ExecutionQueue protocol.

Implements plan chapter 6 (Durable Messaging & Job State Machine).
Uses Peek-Lock pattern (plan 6.4) with auto-renewal of message locks.
The local development environment uses the Service Bus emulator
(mcr.microsoft.com/azure-messaging/servicebus-emulator) so the same
code path runs in dev, staging, and production.

Authentication:
  - Dev: EDIM_SERVICEBUS_CONNECTION_STRING (emulator).
  - Staging/Production: EDIM_SERVICEBUS_NAMESPACE + App Service
    System-Assigned Managed Identity via DefaultAzureCredential (plan 2.4).
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Optional

try:
    from azure.identity import DefaultAzureCredential
    from azure.servicebus import ServiceBusClient, ServiceBusMessage
    from azure.servicebus.exceptions import OperationTimeoutError
    _SERVICE_BUS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _SERVICE_BUS_AVAILABLE = False

from ..runtime.stores import ExecutionQueue, QueueMessage

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ServiceBusQueueClient:
    """Thin wrapper around one Service Bus queue.

    Supports send/receive and peek-lock completion. Used for the
    execution, cancellation, and completion queues.
    """

    def __init__(
        self,
        queue_name: str,
        connection_string: Optional[str] = None,
        namespace: Optional[str] = None,
        renew_interval_seconds: int = 60,
    ) -> None:
        if not _SERVICE_BUS_AVAILABLE:
            raise RuntimeError(
                "azure-servicebus is not installed. Add it to requirements to use ServiceBusQueueClient."
            )
        self._queue_name = queue_name
        self._renew_interval_seconds = renew_interval_seconds
        # Store credentials so we can create a fresh client per operation.
        # Using `with client:` closes the underlying transport; re-creating
        # avoids stale/broken connections after startup races or emulator
        # restarts (plan 6.7 / local dev reliability).
        self._connection_string = connection_string
        self._namespace = namespace
        self._renewers: dict[str, tuple[threading.Thread, threading.Event]] = {}
        self._renewers_lock = threading.Lock()

    def _new_client(self) -> ServiceBusClient:
        """Create a fresh ServiceBusClient for each operation."""
        return self._build_client(self._connection_string, self._namespace)

    @staticmethod
    def _build_client(connection_string: Optional[str], namespace: Optional[str]) -> ServiceBusClient:
        if connection_string:
            return ServiceBusClient.from_connection_string(connection_string)
        if not namespace:
            raise ValueError("Either connection_string or namespace must be provided.")
        fqdn = namespace.rstrip("/")
        if not fqdn.startswith("sb://"):
            fqdn = f"sb://{fqdn}"
        return ServiceBusClient(fully_qualified_namespace=fqdn, credential=DefaultAzureCredential())

    def send_json(self, payload: dict, message_id: Optional[str] = None, correlation_id: Optional[str] = None) -> None:
        body = json.dumps(payload).encode("utf-8")
        sb_message = ServiceBusMessage(
            body=body,
            content_type="application/json",
            message_id=message_id,
            correlation_id=correlation_id,
        )
        client = self._new_client()
        with client:
            sender = client.get_queue_sender(queue_name=self._queue_name)
            with sender:
                sender.send_messages(sb_message)

    def receive_one(
        self,
        max_wait_seconds: int = 5,
        on_message: Optional[Callable[[dict], None]] = None,
    ) -> Optional[dict]:
        """Receive a single JSON message with Peek-Lock.

        If on_message is provided, the message is passed to the callback
        inside the lock; the callback must return True to complete the
        message or False to abandon it. If on_message is None, the raw
        payload is returned and the caller must call complete/abandon
        via the returned lease object.
        """
        client = self._new_client()
        with client:
            receiver = client.get_queue_receiver(queue_name=self._queue_name, prefetch=1)
            with receiver:
                msgs = receiver.receive_messages(max_message_count=1, max_wait_time=max_wait_seconds)
                if not msgs:
                    return None
                msg = msgs[0]
                body_parts = msg.body
                body_bytes = body_parts if isinstance(body_parts, (bytes, bytearray)) else b"".join(body_parts)
                payload = json.loads(body_bytes.decode("utf-8"))
                if on_message is not None:
                    try:
                        ok = on_message(payload)
                        if ok:
                            receiver.complete_message(msg)
                        else:
                            receiver.abandon_message(msg)
                    except Exception:
                        logger.exception("Message handler failed for queue %s", self._queue_name)
                        receiver.abandon_message(msg)
                    return payload
                self._start_renewer(msg, receiver)
                payload["_sb_receiver"] = receiver
                payload["_sb_message"] = msg
                return payload

    def complete(self, payload: dict) -> None:
        receiver = payload.pop("_sb_receiver", None)
        msg = payload.pop("_sb_message", None)
        if receiver is None or msg is None:
            return
        self._stop_renewer(msg.get("message_id"))
        receiver.complete_message(msg)

    def abandon(self, payload: dict) -> None:
        receiver = payload.pop("_sb_receiver", None)
        msg = payload.pop("_sb_message", None)
        if receiver is None or msg is None:
            return
        self._stop_renewer(msg.get("message_id"))
        receiver.abandon_message(msg)

    def dead_letter(self, payload: dict, reason: str) -> None:
        receiver = payload.pop("_sb_receiver", None)
        msg = payload.pop("_sb_message", None)
        if receiver is None or msg is None:
            return
        self._stop_renewer(msg.get("message_id"))
        receiver.dead_letter_message(msg, reason=reason)

    def _start_renewer(self, sb_message, receiver) -> None:
        stop_event = threading.Event()
        message_id = sb_message.message_id
        thread = threading.Thread(
            target=self._renew_loop,
            args=(sb_message, receiver, stop_event),
            daemon=True,
            name=f"edim-sb-renewer-{message_id}",
        )
        with self._renewers_lock:
            self._renewers[message_id] = (thread, stop_event)
        thread.start()

    def _renew_loop(self, sb_message, receiver, stop_event: threading.Event) -> None:
        while not stop_event.wait(self._renew_interval_seconds):
            try:
                receiver.renew_message_lock(sb_message)
                logger.debug("Renewed Service Bus lock for %s", sb_message.message_id)
            except Exception:
                logger.exception("Failed to renew Service Bus lock for %s", sb_message.message_id)
                return

    def _stop_renewer(self, message_id: str) -> None:
        with self._renewers_lock:
            entry = self._renewers.pop(message_id, None)
        if entry is None:
            return
        thread, stop_event = entry
        stop_event.set()
        thread.join(timeout=2)


class ServiceBusExecutionQueue:
    """Service Bus adapter matching the LocalExecutionQueue interface.

    Exposes ``put / qsize / task_done`` so it can be injected as the
    ``execution_queue`` parameter of the local ``JobManager``.  When this
    adapter is active the ``JobManager`` worker thread is disabled — the
    isolated ``edim-worker`` container consumes the same Service Bus queue
    and runs models externally.

    On ``put()``, the adapter constructs a complete ``model_run_bundle_v1``
    bundle from the incoming message dict and the injected manifest/settings.
    The worker daemon receives this bundle and writes it directly to
    ``request_bundle.json`` — no reconstruction needed.
    """

    def __init__(
        self,
        client: ServiceBusQueueClient,
        settings: "Settings | None" = None,
        manifest: dict | None = None,
        runtime_config: dict | None = None,
    ) -> None:
        self._client = client
        self._settings = settings
        self._manifest = manifest or {}
        self._runtime_config = runtime_config or {}

    def put(self, message: dict) -> None:
        execution_id = str(message.get("execution_id") or "")
        run_id = str(message.get("run_id") or "")

        # Construct a complete model_run_bundle_v1 bundle so the worker
        # daemon can pass it directly to the black-box CLI.
        bundle = self._build_bundle(message)
        self._client.send_json(
            bundle,
            message_id=execution_id,
            correlation_id=run_id,
        )
        logger.info("Dispatched execution %s to Service Bus queue %s", execution_id, self._client._queue_name)

    def _build_bundle(self, message: dict) -> dict:
        """Build a model_run_bundle_v1 from a queue message and injected config."""
        execution_id = str(message.get("execution_id") or "")
        run_id = str(message.get("run_id") or execution_id)
        request_payload = message.get("request_payload") if isinstance(message.get("request_payload"), dict) else {}

        artifact_policy = {}
        if self._runtime_config:
            artifact_policy = self._runtime_config.get("artifacts") if isinstance(self._runtime_config.get("artifacts"), dict) else {}

        runtime_settings: dict = {}
        if self._settings is not None:
            runtime_settings = self._settings_snapshot(self._settings)

        return {
            "schema_version": "model_run_bundle_v1",
            "execution_id": execution_id,
            "run_id": run_id,
            "project_id": message.get("project_id", ""),
            "user_id": message.get("user_id", ""),
            "request": request_payload,
            "dataset_versions": message.get("dataset_versions") or [],
            "attempt_count": int(message.get("attempt_count", message.get("attempt", 1))),
            "model_runtime": self._manifest,
            "artifact_policy": artifact_policy,
            "runtime_settings": runtime_settings,
        }

    @staticmethod
    def _settings_snapshot(settings) -> dict:
        """Minimal runtime_settings snapshot for the model black box."""
        from pathlib import Path

        def _ps(p):
            return str(p.resolve()) if p is not None else ""

        rc = getattr(settings, "runtime_config", {}) or {}
        return {
            "calliope_root": _ps(getattr(settings, "calliope_root", None)),
            "runs_dir": _ps(getattr(settings, "runs_dir", None)),
            "config_dir": _ps(getattr(settings, "config_dir", None)),
            "dev_subset_start": getattr(settings, "dev_subset_start", ""),
            "dev_subset_end": getattr(settings, "dev_subset_end", ""),
            "analysis_subset_start": getattr(settings, "analysis_subset_start", ""),
            "analysis_subset_end": getattr(settings, "analysis_subset_end", ""),
            "dev_solver_time_limit_seconds": getattr(settings, "dev_solver_time_limit_seconds", 0),
            "analysis_solver_time_limit_seconds": getattr(settings, "analysis_solver_time_limit_seconds", 0),
            "allow_full_year": getattr(settings, "allow_full_year", False),
            "solver": getattr(settings, "solver", "highs"),
            "summary_max_generation_techs": getattr(settings, "summary_max_generation_techs", 0),
            "summary_max_generation_timesteps": getattr(settings, "summary_max_generation_timesteps", 0),
            "summary_max_category_rows": getattr(settings, "summary_max_category_rows", 0),
            "summary_diagnostics_max_rows": getattr(settings, "summary_diagnostics_max_rows", 0),
            "development_engine": getattr(settings, "development_engine", "mario"),
            "mario_db_path": getattr(settings, "mario_db_path", ""),
            "mario_timeout_seconds": getattr(settings, "mario_timeout_seconds", 120.0),
            "mario_fail_on_error": getattr(settings, "mario_fail_on_error", False),
            "model_runtime_mode": getattr(settings, "model_runtime_mode", "subprocess"),
            "runtime_artifact_handoff_mode": getattr(settings, "runtime_artifact_handoff_mode", "shared_filesystem"),
            "dataset_staging_mode": getattr(settings, "dataset_staging_mode", "copy_to_run"),
            "model_manifest_path": _ps(getattr(settings, "model_manifest_path", None)),
            "dataset_manifest_path": _ps(getattr(settings, "dataset_manifest_path", None)),
            "runtime_config": rc,
            "job_dedupe_enabled": getattr(settings, "job_dedupe_enabled", True),
            "job_queue_capacity": getattr(settings, "job_queue_capacity", 12),
        }

    def qsize(self) -> int:
        return 0

    def task_done(self) -> None:
        pass

    def get(self):
        raise RuntimeError("ServiceBusExecutionQueue.get() is not used when start_worker=False")


class AzureServiceBusQueue(ExecutionQueue):
    """Azure Service Bus implementation of the ExecutionQueue protocol.

    This adapter exposes the legacy single-queue interface while the
    rest of the system uses ServiceBusQueueClient directly for the
    execution, cancellation, and completion queues.
    """

    def __init__(
        self,
        queue_name: str,
        connection_string: Optional[str] = None,
        namespace: Optional[str] = None,
        lease_seconds: int = 300,
        renew_interval_seconds: int = 60,
    ) -> None:
        self._client = ServiceBusQueueClient(
            queue_name=queue_name,
            connection_string=connection_string,
            namespace=namespace,
            renew_interval_seconds=renew_interval_seconds,
        )
        self._lease_seconds = lease_seconds

    def enqueue(self, message: QueueMessage) -> None:
        body = {
            "execution_id": message.execution_id,
            "run_id": message.run_id,
            "project_id": message.project_id,
            "user_id": message.user_id,
            "request_payload": message.request_payload,
            "dataset_versions": message.dataset_versions,
            "attempt_count": message.attempt_count,
            "enqueued_at": _utcnow_iso(),
        }
        self._client.send_json(
            body,
            message_id=message.execution_id,
            correlation_id=message.run_id,
        )
        logger.info("Enqueued message %s on queue %s", message.execution_id, self._client._queue_name)

    def reserve(self, lease_seconds: int = 300) -> Optional[QueueMessage]:
        payload = self._client.receive_one(max_wait_seconds=lease_seconds)
        if payload is None:
            return None
        return QueueMessage(
            execution_id=payload["execution_id"],
            run_id=payload["run_id"],
            project_id=payload.get("project_id", ""),
            user_id=payload.get("user_id", ""),
            request_payload=payload.get("request_payload", {}),
            dataset_versions=payload.get("dataset_versions", []),
            attempt_count=int(payload.get("attempt_count", 1)),
        )

    def complete(self, message: QueueMessage) -> None:
        # The worker holds the raw payload lease; this adapter method is
        # unused in the new design.
        return None

    def abandon(self, message: QueueMessage, requeue: bool = True) -> None:
        return None

    def dead_letter(self, message: QueueMessage, reason: str) -> None:
        return None

    def renew_lease(self, message: QueueMessage, lease_seconds: int = 60) -> None:
        return None

    def depth(self) -> int:
        return -1
