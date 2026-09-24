"""Completion Bridge — API-side Service Bus listener.

Listens on the Azure Service Bus *completion queue* for worker status
notifications and updates the corresponding ``project_runs`` rows in
PostgreSQL via ``PlatformRepository``.

Architecture (plan 6.2):
  - Worker daemon (isolated container, no Postgres access) runs the model,
    uploads artifacts directly to Blob Storage, and posts status updates
    (``outcome`` = ``"running"`` / ``"succeeded"`` / ``"failed"`` /
    ``"cancelled"``) to the Service Bus completion queue.
  - The API hosts this bridge as a background thread.  It consumes the
    completion queue and is the **only** component that writes terminal
    run state to PostgreSQL.

The bridge is optional — when Service Bus is not configured the API
falls back to in-process execution via ``JobManager._worker_loop``, which
writes state directly.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Mapping from worker outcome to project_runs status.
_OUTCOME_STATUS: dict[str, str] = {
    "running": "running",
    # Progress messages keep the run active but carry a granular stage so the
    # frontend can advance its stage tracker instead of showing "running".
    "progress": "running",
    "succeeded": "succeeded",
    "failed": "failed",
    "cancelled": "cancelled",
}

_TERMINAL_OUTCOMES = {"succeeded", "failed", "cancelled"}


class CompletionBridge:
    """Background thread that bridges worker completion messages → Postgres.

    Instantiate, call ``start()``, and keep a reference so the thread
    isn't garbage-collected.  Call ``stop()`` during graceful shutdown.
    """

    def __init__(
        self,
        platform_repository,  # PlatformRepository
        queue_name: str,
        connection_string: str | None = None,
        namespace: str | None = None,
        poll_interval: float = 5.0,
        job_manager=None,
    ) -> None:
        self._repo = platform_repository
        self._queue_name = queue_name
        self._connection_string = connection_string
        self._namespace = namespace
        self._poll_interval = poll_interval
        # Optional PostgresJobManager. The bridge writes the platform JSON
        # record; the job manager owns the project_runs row that backs
        # /api/executions/{id}/status. Without it that row would never leave
        # "running" for isolated-worker runs.
        self._job_manager = job_manager
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._listen,
            daemon=True,
            name="edim-completion-bridge",
        )
        self._thread.start()
        logger.info(
            "CompletionBridge started on queue '%s' (poll %.1fs).",
            self._queue_name,
            self._poll_interval,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None
        logger.info("CompletionBridge stopped.")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _listen(self) -> None:
        from .service_bus_queue import ServiceBusQueueClient

        while not self._stop_event.is_set():
            try:
                # Create a fresh client each iteration so stale connections
                # from emulator restarts don't block message receipt.
                client = ServiceBusQueueClient(
                    queue_name=self._queue_name,
                    connection_string=self._connection_string,
                    namespace=self._namespace,
                )
                while not self._stop_event.is_set():
                    handled = self._process_one(client)
                    if not handled:
                        break  # outer loop will recreate client
            except Exception:
                logger.exception("CompletionBridge processing error; will retry.")
            self._stop_event.wait(self._poll_interval)

    def _process_one(self, client) -> bool:
        """Receive and handle one completion message.

        Uses the ``on_message`` callback so the Service Bus receiver and
        client stay alive for the entire message settlement lifecycle.
        """
        result: list[bool] = []

        def _handle(payload: dict) -> bool:
            execution_id = str(payload.get("execution_id") or "")
            run_id = str(payload.get("run_id") or "")
            outcome = str(payload.get("outcome") or "").strip().lower()

            logger.info(
                "CompletionBridge received outcome=%s for execution=%s run=%s",
                outcome,
                execution_id,
                run_id,
            )

            if not run_id or outcome not in _OUTCOME_STATUS:
                logger.warning(
                    "Unknown completion payload (run_id=%s outcome=%s); abandoning.",
                    run_id,
                    outcome,
                )
                result.append(False)
                return False  # abandon

            status = _OUTCOME_STATUS[outcome]
            updates = _build_status_update(payload, status)

            try:
                self._repo.update_run_record(
                    run_id, updates, user_id="system"
                )
                logger.info("Updated run %s to status=%s via completion bridge.", run_id, status)
                result.append(True)
                return True  # complete
            except Exception:
                logger.warning(
                    "Completion bridge could not update run %s (may be stale); completing message.",
                    run_id, exc_info=True,
                )
                result.append(True)
                return True  # complete — don't retry
            finally:
                # The job manager owns the live job record that backs
                # /api/runs and the run list; keep it in step with the platform
                # JSON record so an isolated-worker run reaches a terminal
                # state and reports the worker's granular stage.
                _apply_job_manager_update(self._job_manager, run_id, execution_id, updates)

        client.receive_one(
            max_wait_seconds=int(self._poll_interval),
            on_message=_handle,
        )
        return any(result)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_status_update(payload: Dict[str, Any], status: str) -> Dict[str, Any]:
    """Build the field dict for ``PlatformRepository.update_run_record``.

    Mirrors the shape written by ``JobManager._worker_loop`` so the
    frontend status view renders identically whether the run was processed
    in-process or by the isolated worker.
    """
    # The worker reports a granular stage (for example "solve_energy").
    # Fall back to the coarse status when it is absent so older payloads and
    # terminal outcomes still produce a renderable stage.
    stage = str(payload.get("stage") or "").strip() or status
    message = str(payload.get("message") or "").strip() or _status_message(status, payload)

    updates: Dict[str, Any] = {
        "status": status,
        "stage": stage,
        "message": message,
    }

    if status == "running":
        started_at = str(payload.get("started_at") or "")
        if started_at:
            updates["started_at"] = started_at
        reported = payload.get("progress")
        try:
            progress = float(reported)
        except (TypeError, ValueError):
            progress = 0.05
        updates["progress"] = max(0.0, min(1.0, progress))
        updates["worker_id"] = str(payload.get("worker_id") or "")
        updates["execution_attempts"] = [
            {
                "execution_id": payload.get("execution_id"),
                "run_id": payload.get("run_id"),
                "attempt": int(payload.get("attempt_count", 1)),
                "worker_id": payload.get("worker_id"),
                "status": "running",
                "started_at": payload.get("started_at"),
            }
        ]
    elif status in _TERMINAL_OUTCOMES:
        updates["finished_at"] = str(payload.get("finished_at") or "")
        updates["progress"] = 1.0 if status == "succeeded" else 0.0
        updates["error"] = str(payload.get("error") or "") if status != "succeeded" else None
        if status == "succeeded":
            updates["summary_available"] = True
        if payload.get("artifact_catalog"):
            updates["artifact_catalog"] = list(payload["artifact_catalog"])

    return updates


def _apply_job_manager_update(
    job_manager,
    run_id: str,
    execution_id: str,
    updates: Dict[str, Any],
) -> None:
    """Mirror a completion update onto the live job record.

    Best-effort: a failure here must not stop message settlement, because the
    platform JSON record has already been updated and the message would
    otherwise be retried forever.
    """
    if job_manager is None:
        return
    apply_update = getattr(job_manager, "apply_worker_update", None)
    if apply_update is None:
        return
    try:
        apply_update(
            run_id,
            execution_id=execution_id or None,
            status=str(updates.get("status") or "") or None,
            stage=str(updates.get("stage") or "") or None,
            progress=updates.get("progress"),
            message=str(updates.get("message") or "") or None,
            error=updates.get("error"),
            started_at=str(updates.get("started_at") or "") or None,
            finished_at=str(updates.get("finished_at") or "") or None,
        )
    except Exception:
        logger.warning(
            "Completion bridge could not update job state for run %s.",
            run_id,
            exc_info=True,
        )


def _status_message(status: str, payload: Dict[str, Any]) -> str:
    if status == "running":
        return f"Worker {payload.get('worker_id', '?')} started."
    if status == "succeeded":
        return "Run completed successfully."
    if status == "failed":
        return str(payload.get("error") or "Run failed.")[:500]
    if status == "cancelled":
        return "Run cancelled."
    return status