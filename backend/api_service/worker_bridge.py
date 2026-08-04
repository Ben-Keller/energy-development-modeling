"""Bridge between the isolated compute worker and the API database layer.

The worker never writes to Postgres. Instead it sends completion
messages on a Service Bus completion queue and polls a cancellation
queue. This module owns:

  - Sending cancellation requests to the worker.
  - Consuming completion messages and updating project_runs /
    execution_attempts via the PlatformRepository.

The completion consumer runs in a background thread started from the
FastAPI lifespan (main.py).  All database writes go through the
PlatformRepository protocol — no typed ORM dependency.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .services.service_bus_queue import ServiceBusQueueClient

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utcnow_iso() -> str:
    return _utcnow().isoformat()


# ---------------------------------------------------------------------------
# WorkerBridge
# ---------------------------------------------------------------------------


class WorkerBridge:
    """Manages cancellation/completion queues for worker isolation.

    All status updates go through the PlatformRepository protocol so
    this bridge works identically against SQLite, PostgreSQL, or a
    cloud database backend.
    """

    def __init__(
        self,
        platform_repository,
        cancellation_queue: ServiceBusQueueClient,
        completion_queue: ServiceBusQueueClient,
        blob_client=None,
        blob_container_prefix: str = "stg-",
        poll_interval_seconds: float = 5.0,
    ) -> None:
        self._platform = platform_repository
        self._cancellation_queue = cancellation_queue
        self._completion_queue = completion_queue
        self._blob_client = blob_client
        self._blob_container_prefix = blob_container_prefix
        self._poll_interval_seconds = poll_interval_seconds
        self._consumer_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Cancellation (API → worker)
    # ------------------------------------------------------------------

    def request_cancellation(
        self, run_id: str, execution_id: str, cancelled_by: Optional[str] = None
    ) -> None:
        """Send a cancellation request to the worker via Service Bus."""
        payload = {
            "execution_id": execution_id,
            "run_id": run_id,
            "cancelled_by": cancelled_by,
            "requested_at": _utcnow_iso(),
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

    # ------------------------------------------------------------------
    # Completion consumer (worker → Service Bus → API → Postgres)
    # ------------------------------------------------------------------

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
        """Persist a completion message to Postgres via PlatformRepository.

        Handles both ``outcome="running"`` (worker-accepted notification)
        and terminal outcomes (``succeeded``, ``failed``, ``cancelled``).
        Returns True on success so the Service Bus client completes the
        message; returns False to abandon it for retry.
        """
        execution_id = str(payload.get("execution_id") or "")
        run_id = str(payload.get("run_id") or "")
        outcome = str(payload.get("outcome") or "")
        worker_id = str(payload.get("worker_id") or "unknown")
        error = payload.get("error")
        attempt_count = int(payload.get("attempt_count", 1))
        started_at = payload.get("started_at") or _utcnow_iso()
        finished_at = payload.get("finished_at") or _utcnow_iso()

        logger.info(
            "Completion: exec=%s run=%s outcome=%s worker=%s",
            execution_id, run_id, outcome, worker_id,
        )

        if not execution_id or not run_id:
            logger.warning("Completion message missing execution_id or run_id; acking.")
            return True

        try:
            record = self._find_run(run_id, execution_id)
            if record is None:
                logger.warning("Run not found run=%s exec=%s; acking stale message.", run_id, execution_id)
                return True

            owner = str(record.get("owner_user_id") or "undp_analyst")

            # ---- worker-accepted notification ----
            if outcome == "running":
                current_status = str(record.get("status") or "").lower()
                if current_status == "queued":
                    self._platform.update_run_record(
                        run_id,
                        {
                            "status": "running",
                            "stage": "running",
                            "message": f"Worker {worker_id} accepted execution (attempt {attempt_count}).",
                            "started_at": started_at,
                            "execution_id": execution_id,
                            "execution_attempts": _upsert_attempt(
                                record, execution_id, worker_id, attempt_count,
                                outcome="running", started_at=started_at,
                            ),
                        },
                        user_id=owner,
                    )
                    logger.info("Run %s → running (attempt %s)", run_id, attempt_count)
                return True

            # ---- terminal outcome ----
            updates: Dict[str, Any] = {
                "status": outcome,
                "stage": outcome,
                "finished_at": finished_at,
                "execution_id": "",
            }
            if error:
                updates["error"] = str(error)
            if outcome == "cancelled":
                updates["message"] = "Cancelled by user request."
            elif outcome == "failed":
                updates["message"] = str(error or "Run failed.")
            else:
                updates["message"] = "Run completed."
                updates["progress"] = 1.0
                updates["summary_available"] = True

            updates["execution_attempts"] = _upsert_attempt(
                record, execution_id, worker_id, attempt_count,
                outcome=outcome, started_at=started_at, finished_at=finished_at,
                error=error,
            )
            self._platform.update_run_record(run_id, updates, user_id=owner)
            logger.info("Run %s → %s (attempt %s)", run_id, outcome, attempt_count)
            return True

        except Exception:
            logger.exception("Failed to persist completion exec=%s", execution_id)
            return False  # abandon → retry

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_run(self, run_id: str, execution_id: str) -> Optional[dict]:
        """Look up a run record, trying common dev user ids."""
        candidates = ("undp_analyst", "local_user", "dev-user-1")
        for uid in candidates:
            try:
                return self._platform.get_run_record(run_id, user_id=uid)
            except Exception:
                pass
        for uid in candidates:
            try:
                return self._platform.get_run_record_by_execution(execution_id, user_id=uid)
            except Exception:
                pass
        return None


def _upsert_attempt(
    record: dict,
    execution_id: str,
    worker_id: str,
    attempt_count: int,
    *,
    outcome: str,
    started_at: str,
    finished_at: Optional[str] = None,
    error: Optional[str] = None,
) -> list:
    """Merge or create an execution_attempt entry."""
    attempts = list(record.get("execution_attempts") or [])
    attempts = [
        a for a in attempts
        if not (
            str(a.get("execution_id") or "") == execution_id
            and int(a.get("attempt") or 0) == attempt_count
        )
    ]
    attempts.append({
        "execution_id": execution_id,
        "run_id": str(record.get("run_id") or ""),
        "attempt": attempt_count,
        "worker_id": worker_id,
        "outcome": outcome,
        "started_at": started_at,
        "heartbeat_at": finished_at or started_at,
        "finished_at": finished_at,
        "error": str(error or ""),
    })
    return attempts
