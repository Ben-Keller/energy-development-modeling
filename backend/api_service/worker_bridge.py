"""Bridge between the isolated compute worker and the API database layer.

The worker never writes to Postgres. Instead it sends completion
messages on a Service Bus completion queue and polls a cancellation
queue. This module owns:

  - Sending cancellation requests to the worker.
  - Consuming completion messages and updating project_runs /
    execution_attempts in Postgres.

The completion consumer runs in a background thread started from the
FastAPI lifespan (composition.py).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from .db_models import ExecutionAttemptRecord, ExecutionEventRecord, ProjectRunRecord
from .services.service_bus_queue import ServiceBusQueueClient

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


class WorkerBridge:
    """Manages cancellation/completion queues for worker isolation."""

    def __init__(
        self,
        session_factory,
        cancellation_queue: ServiceBusQueueClient,
        completion_queue: ServiceBusQueueClient,
        blob_client=None,
        blob_container_prefix: str = "stg-",
        poll_interval_seconds: float = 5.0,
    ) -> None:
        self._session_factory = session_factory
        self._cancellation_queue = cancellation_queue
        self._completion_queue = completion_queue
        self._blob_client = blob_client
        self._blob_container_prefix = blob_container_prefix
        self._poll_interval_seconds = poll_interval_seconds
        self._consumer_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start_completion_consumer(self) -> None:
        if self._consumer_thread is not None:
            return
        self._consumer_thread = threading.Thread(
            target=self._completion_loop,
            daemon=True,
            name="edim-completion-consumer",
        )
        self._consumer_thread.start()
        logger.info("Completion queue consumer started")

    def stop_completion_consumer(self) -> None:
        self._stop_event.set()
        if self._consumer_thread is not None:
            self._consumer_thread.join(timeout=5)
            self._consumer_thread = None

    def request_cancellation(self, run_id: str, execution_id: str, cancelled_by: Optional[str] = None) -> None:
        """Send a cancellation request to the worker."""
        payload = {
            "execution_id": execution_id,
            "run_id": run_id,
            "cancelled_by": cancelled_by,
            "requested_at": _utcnow().isoformat(),
        }
        try:
            self._cancellation_queue.send_json(
                payload,
                message_id=execution_id,
                correlation_id=run_id,
            )
            logger.info("Sent cancellation message for execution_id=%s", execution_id)
        except Exception:
            logger.exception("Failed to send cancellation message for %s", execution_id)

    def _completion_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                payload = self._completion_queue.receive_one(
                    max_wait_seconds=int(self._poll_interval_seconds),
                    on_message=self._handle_completion,
                )
                if payload is None:
                    continue
            except Exception:
                logger.exception("Completion consumer error")
                time.sleep(self._poll_interval_seconds)

    def _handle_completion(self, payload: dict) -> bool:
        """Persist a completion message to Postgres. Returns True on success."""
        execution_id = payload.get("execution_id")
        run_id = payload.get("run_id")
        outcome = payload.get("outcome")
        error = payload.get("error")
        summary = payload.get("summary")
        summary_ref = payload.get("summary_ref")
        if summary is None and summary_ref and self._blob_client is not None:
            try:
                container = self._blob_client.get_container_client(summary_ref["container"])
                summary = json.loads(container.download_blob(summary_ref["object_key"]).readall())
                logger.info("Fetched summary from blob %s/%s", summary_ref["container"], summary_ref["object_key"])
            except Exception:
                logger.exception("Failed to fetch summary from blob for execution_id=%s", execution_id)
        artifact_storage_refs = payload.get("artifact_storage_refs", [])
        attempt_count = int(payload.get("attempt_count", 1))
        worker_id = payload.get("worker_id", "unknown")
        started_at = _parse_iso(payload.get("started_at"))
        finished_at = _parse_iso(payload.get("finished_at")) or _utcnow()

        logger.info("Processing completion for execution_id=%s outcome=%s", execution_id, outcome)

        # "running" is a status-only notification — create attempt row on pickup.
        if outcome == "running":
            try:
                with self._session_factory() as session:
                    run = session.get(ProjectRunRecord, run_id)
                    if run is not None and run.status == "queued":
                        run.status = "running"
                        if started_at is not None:
                            run.started_at = started_at
                    # Create attempt record on worker pickup (plan 6.5.1). Skip if
                    # already present (e.g. duplicate delivery).
                    existing = session.execute(
                        select(ExecutionAttemptRecord).where(
                            ExecutionAttemptRecord.execution_id == execution_id,
                            ExecutionAttemptRecord.attempt_count == attempt_count,
                        )
                    ).scalar_one_or_none()
                    if existing is None:
                        session.add(
                            ExecutionAttemptRecord(
                                run_id=run_id,
                                execution_id=execution_id,
                                worker_id=worker_id,
                                attempt_count=attempt_count,
                                started_at=started_at or _utcnow(),
                                outcome="running",
                            )
                        )
                    session.commit()
                    logger.info("Run %s transitioned to running (attempt %s)", run_id, attempt_count)
            except Exception:
                logger.exception("Failed to set running status for %s", run_id)
            return True

        try:
            with self._session_factory() as session:
                run = session.get(ProjectRunRecord, run_id)
                if run is not None:
                    run.status = outcome
                    run.finished_at = finished_at
                    run.active_execution_id = None
                    if run.started_at is None and started_at is not None:
                        run.started_at = started_at
                    if summary is not None:
                        run.request_payload = {**(run.request_payload or {}), "summary": summary}
                    if artifact_storage_refs:
                        run.request_payload = {**(run.request_payload or {}), "artifact_storage_refs": artifact_storage_refs}
                # Upsert attempt record — may already exist from the "running"
                # notification sent on worker pickup.
                existing_attempt = session.execute(
                    select(ExecutionAttemptRecord).where(
                        ExecutionAttemptRecord.execution_id == execution_id,
                        ExecutionAttemptRecord.attempt_count == attempt_count,
                    )
                ).scalar_one_or_none()
                if existing_attempt is not None:
                    existing_attempt.finished_at = finished_at
                    existing_attempt.outcome = outcome
                    if error:
                        existing_attempt.error = error
                else:
                    session.add(
                        ExecutionAttemptRecord(
                            run_id=run_id,
                            execution_id=execution_id,
                            worker_id=worker_id,
                            attempt_count=attempt_count,
                            started_at=started_at or finished_at,
                            finished_at=finished_at,
                            outcome=outcome,
                            error=error,
                        )
                    )
                session.commit()
                self._import_event_log_from_blob(session, execution_id, run_id)
            return True
        except Exception:
            logger.exception("Failed to persist completion for %s", execution_id)
            return False

    def _import_event_log_from_blob(self, session, execution_id: str, run_id: str) -> None:
        """Import runtime events written by the worker to Blob append storage."""
        if self._blob_client is None:
            return
        container_name = f"{self._blob_container_prefix}logs"
        blob_name = f"{execution_id}/runtime_events.jsonl"
        try:
            blob = self._blob_client.get_blob_client(container_name, blob_name)
            if not blob.exists():
                return
            data = blob.download_blob().readall().decode("utf-8", errors="replace")
        except Exception:
            logger.exception("Failed to read event log blob %s/%s", container_name, blob_name)
            return

        events: list[ExecutionEventRecord] = []
        for line in data.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            ts = _parse_iso(payload.get("timestamp"))
            events.append(
                ExecutionEventRecord(
                    execution_id=execution_id,
                    run_id=run_id,
                    level=payload.get("level", "info"),
                    stage=payload.get("stage", ""),
                    message=payload.get("message", ""),
                    payload=payload.get("payload"),
                    timestamp=ts or _utcnow(),
                )
            )
        if events:
            try:
                session.add_all(events)
                session.commit()
                logger.info("Imported %d events for execution_id=%s", len(events), execution_id)
            except Exception:
                logger.exception("Failed to import events for %s", execution_id)
                session.rollback()
