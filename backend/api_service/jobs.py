from __future__ import annotations

import hashlib
import json
import logging
import multiprocessing as mp
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

from .runner import RunCancelledError, run_calliope_synchronously
from .schemas import JobInfo, RunArtifacts, RunRequest, RunSummary
from .settings import Settings


logger = logging.getLogger(__name__)


FINAL_JOB_STATUSES = {"succeeded", "failed", "cancelled"}


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


def _subprocess_job_main(settings: Settings, req_payload: Dict[str, Any], event_queue: Any) -> None:
    def _emit(payload: Dict[str, Any]) -> None:
        try:
            event_queue.put(payload)
        except Exception:
            pass

    req = RunRequest(**req_payload)

    def _progress(stage: str, progress: float, message: str) -> None:
        _emit(
            {
                "kind": "progress",
                "stage": str(stage),
                "progress": float(progress),
                "message": str(message),
            }
        )

    try:
        run_id, summary, _, _ = run_calliope_synchronously(
            settings,
            req,
            progress_callback=_progress,
            cancel_requested=None,
        )
        _emit({"kind": "result", "run_id": run_id, "summary": summary})
    except RunCancelledError as exc:
        _emit({"kind": "cancelled", "error": str(exc)})
    except Exception as exc:
        _emit({"kind": "error", "error": str(exc)})


@dataclass
class _JobRecord:
    job_id: str
    request: RunRequest
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
    run_id: str | None = None
    summary: dict | None = None
    cancel_requested: bool = False


class JobManager:
    def __init__(self, settings: Settings, use_subprocess: bool = False):
        self._settings = settings
        self._use_subprocess = bool(use_subprocess)
        self._jobs: Dict[str, _JobRecord] = {}
        self._pending: List[str] = []
        self._queue: queue.Queue[str] = queue.Queue()
        self._active_processes: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True, name="edim-job-worker")
        self._worker.start()

    def submit(self, req: RunRequest) -> JobInfo:
        return self.submit_many([req])[0]

    def submit_many(self, requests: List[RunRequest]) -> List[JobInfo]:
        if not requests:
            return []

        queued_job_ids: List[str] = []
        out: List[JobInfo] = []
        with self._lock:
            requests_with_fingerprint: List[tuple[RunRequest, str]] = []
            dedupe_enabled = bool(self._settings.job_dedupe_enabled)
            new_jobs_needed = 0
            unique_new_fingerprints: set[str] = set()
            for req in requests:
                request_fingerprint = self._request_fingerprint(req)
                requests_with_fingerprint.append((req, request_fingerprint))
                if not dedupe_enabled:
                    new_jobs_needed += 1
                    continue
                if request_fingerprint in unique_new_fingerprints:
                    continue
                if self._find_reusable_job_locked(request_fingerprint) is not None:
                    continue
                unique_new_fingerprints.add(request_fingerprint)

            if dedupe_enabled:
                new_jobs_needed = len(unique_new_fingerprints)

            if not self._can_accept_locked(new_jobs_needed):
                raise JobQueueFullError(
                    f"Job queue capacity reached ({self._settings.job_queue_capacity}). "
                    "Wait for running/queued jobs to finish or cancel."
                )

            for req, request_fingerprint in requests_with_fingerprint:
                reusable = self._find_reusable_job_locked(request_fingerprint)
                if reusable is not None:
                    if reusable.status in {"queued", "running"}:
                        reusable.message = "Duplicate request deduplicated; reusing active job."
                    else:
                        reusable.message = "Duplicate request matched cached successful run."
                    reusable.updated_at = time.time()
                    queue_position = None
                    if reusable.status == "queued":
                        try:
                            queue_position = self._pending.index(reusable.job_id) + 1
                        except ValueError:
                            queue_position = None
                    out.append(self._to_job_info_locked(reusable, queue_position=queue_position))
                    continue

                job_id = uuid.uuid4().hex[:12]
                rec = _JobRecord(job_id=job_id, request=req, request_fingerprint=request_fingerprint)
                self._jobs[job_id] = rec
                self._pending.append(job_id)
                queued_job_ids.append(job_id)
                out.append(
                    self._to_job_info_locked(
                        rec,
                        queue_position=len(self._pending),
                    )
                )

            self._trim_history_locked()

        for job_id in queued_job_ids:
            self._queue.put(job_id)
        return out

    def get(self, job_id: str) -> JobInfo:
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec is None:
                raise KeyError(job_id)
            queue_position = None
            if rec.status == "queued":
                try:
                    queue_position = self._pending.index(job_id) + 1
                except ValueError:
                    queue_position = None
            return self._to_job_info_locked(rec, queue_position=queue_position)

    def cancel(self, job_id: str) -> JobInfo:
        proc_to_terminate = None
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec is None:
                raise KeyError(job_id)

            if rec.status in FINAL_JOB_STATUSES:
                return self._to_job_info_locked(rec, queue_position=None)

            rec.cancel_requested = True
            now = time.time()
            rec.updated_at = now
            queue_position = None

            if rec.status == "queued":
                rec.status = "cancelled"
                rec.progress = 1.0
                rec.stage = "cancelled"
                rec.message = "Run cancelled before start."
                rec.error = "Cancelled by user."
                rec.finished_at = now
                rec.worker_pid = None
                if rec.job_id in self._pending:
                    self._pending.remove(rec.job_id)
            else:
                rec.stage = "cancelling"
                if self._use_subprocess:
                    rec.message = "Cancellation requested; terminating worker process."
                    proc_to_terminate = self._active_processes.get(job_id)
                else:
                    rec.message = "Cancellation requested; waiting for next safe checkpoint."

            if rec.status == "queued":
                try:
                    queue_position = self._pending.index(rec.job_id) + 1
                except ValueError:
                    queue_position = None
            info = self._to_job_info_locked(rec, queue_position=queue_position)

        if proc_to_terminate is not None:
            try:
                if proc_to_terminate.is_alive():
                    proc_to_terminate.terminate()
            except Exception:
                logger.exception("Failed terminating subprocess for cancelled job_id=%s", job_id)
        return info

    def can_accept(self, count: int = 1) -> bool:
        with self._lock:
            return self._can_accept_locked(count)

    def list(self, limit: int = 50) -> List[JobInfo]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
            out = []
            for rec in jobs[: max(1, limit)]:
                queue_position = None
                if rec.status == "queued":
                    try:
                        queue_position = self._pending.index(rec.job_id) + 1
                    except ValueError:
                        queue_position = None
                out.append(self._to_job_info_locked(rec, queue_position=queue_position))
            return out

    def runtime_stats(self) -> Dict[str, float | int]:
        with self._lock:
            counts = {
                "queued": 0,
                "running": 0,
                "succeeded": 0,
                "failed": 0,
                "cancelled": 0,
                "other": 0,
            }
            for rec in self._jobs.values():
                status = str(rec.status or "").strip().lower()
                if status in counts:
                    counts[status] += 1
                else:
                    counts["other"] += 1

            capacity = max(1, int(self._settings.job_queue_capacity))
            active_jobs = counts["queued"] + counts["running"]
            total_jobs = len(self._jobs)

        try:
            queue_depth = int(self._queue.qsize())
        except Exception:
            queue_depth = counts["queued"]

        utilization = active_jobs / float(capacity)
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
            "utilization_share": utilization,
        }

    def _to_job_info_locked(self, rec: _JobRecord, queue_position: int | None) -> JobInfo:
        artifacts = None
        summary_model = None
        if rec.run_id:
            artifacts = RunArtifacts(
                run_id=rec.run_id,
                summary_url=f"/api/run/{rec.run_id}/summary",
                csv_url=f"/api/run/{rec.run_id}/download/csv",
            )
        if rec.summary is not None:
            try:
                summary_model = RunSummary(**rec.summary)
            except Exception:
                # Keep API responsive even if summary payload drifts.
                summary_model = None
        return JobInfo(
            job_id=rec.job_id,
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
            error=rec.error,
            request=rec.request,
            artifacts=artifacts,
            summary=summary_model,
        )

    def _trim_history_locked(self) -> None:
        limit = max(1, int(self._settings.job_history_limit))
        if len(self._jobs) <= limit:
            return
        finished = [j for j in self._jobs.values() if j.status in FINAL_JOB_STATUSES]
        finished.sort(key=lambda x: x.created_at)
        while len(self._jobs) > limit and finished:
            victim = finished.pop(0)
            self._jobs.pop(victim.job_id, None)
            if victim.job_id in self._pending:
                self._pending.remove(victim.job_id)

    def _can_accept_locked(self, count: int) -> bool:
        capacity = max(1, int(self._settings.job_queue_capacity))
        active = sum(1 for rec in self._jobs.values() if rec.status in {"queued", "running"})
        return (active + max(0, int(count))) <= capacity

    def _request_fingerprint(self, req: RunRequest) -> str:
        try:
            req_payload = req.model_dump(mode="json")
        except Exception:
            req_payload = req.model_dump()

        payload = {
            "request": req_payload,
            "solver": self._settings.solver,
            "input_fingerprint": self._input_fingerprint(),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _input_fingerprint(self) -> list[str]:
        paths = [
            self._settings.calliope_root / "model.yaml",
            self._settings.calliope_root / "overrides.yaml",
            self._settings.config_dir / "lever_mappings.csv",
            self._settings.config_dir / "scenario_metadata.csv",
            self._settings.config_dir / "development_model.csv",
        ]
        out: list[str] = []
        for path in paths:
            try:
                stat = path.stat()
                out.append(f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
            except OSError:
                out.append(f"{path.name}:missing")
        return out

    def _find_reusable_job_locked(self, request_fingerprint: str) -> _JobRecord | None:
        if not self._settings.job_dedupe_enabled:
            return None

        records = [
            rec
            for rec in self._jobs.values()
            if rec.request_fingerprint == request_fingerprint
        ]
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

    def _update_progress(self, job_id: str, stage: str, progress: float, message: str) -> None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec is None:
                return
            if rec.cancel_requested and rec.status == "running":
                rec.stage = "cancelling"
                rec.message = (
                    "Cancellation requested; terminating worker process."
                    if self._use_subprocess
                    else "Cancellation requested; waiting for next safe checkpoint."
                )
                rec.updated_at = time.time()
                return
            rec.stage = stage
            rec.progress = max(0.0, min(1.0, float(progress)))
            rec.message = message
            rec.updated_at = time.time()

    def _is_cancel_requested(self, job_id: str) -> bool:
        with self._lock:
            rec = self._jobs.get(job_id)
            return bool(rec and rec.cancel_requested)

    def _emit_runtime_heartbeat(self, job_id: str, *, started_at: float, last_event_at: float) -> None:
        now = time.time()
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec is None or rec.status != "running":
                return
            elapsed = _fmt_elapsed(now - started_at)
            since_event = _fmt_elapsed(now - last_event_at)
            stage = str(rec.stage or "").strip().lower()
            if stage == "solve_energy":
                rec.message = (
                    f"Solving energy optimization problem "
                    f"(elapsed {elapsed}, {since_event} since last solver callback)"
                )
            else:
                rec.message = f"{rec.message or 'Running'} (elapsed {elapsed})"
            rec.updated_at = now

    def _run_job_subprocess(self, job_id: str, rec: _JobRecord) -> tuple[str, str | None, dict | None, str]:
        try:
            ctx = mp.get_context("spawn")
        except ValueError:
            ctx = mp.get_context("fork")
        event_queue: Any = ctx.Queue()
        req_payload = rec.request.model_dump(mode="json")
        worker = ctx.Process(
            target=_subprocess_job_main,
            args=(self._settings, req_payload, event_queue),
            daemon=True,
        )
        worker.start()

        with self._lock:
            current = self._jobs.get(job_id)
            if current is not None:
                current.worker_pid = int(worker.pid or 0) or None
                current.updated_at = time.time()
            self._active_processes[job_id] = worker

        started_at = rec.started_at or time.time()
        last_event_at = time.time()
        last_heartbeat_at = 0.0

        outcome_status = "failed"
        outcome_run_id: str | None = None
        outcome_summary: dict | None = None
        outcome_error = "Run failed"
        finished = False
        finished_at: float | None = None
        received_terminal_event = False

        def _handle_event(event: Dict[str, Any]) -> None:
            nonlocal outcome_status, outcome_run_id, outcome_summary, outcome_error, finished, finished_at, received_terminal_event, last_event_at
            kind = str((event or {}).get("kind", "")).strip().lower()
            last_event_at = time.time()
            if kind == "progress":
                self._update_progress(
                    job_id,
                    str(event.get("stage", "")),
                    float(event.get("progress", 0.0)),
                    str(event.get("message", "")),
                )
                return
            if kind == "result":
                outcome_status = "succeeded"
                outcome_run_id = str(event.get("run_id", "")).strip() or None
                maybe_summary = event.get("summary")
                outcome_summary = maybe_summary if isinstance(maybe_summary, dict) else None
                outcome_error = ""
                finished = True
                finished_at = time.time()
                received_terminal_event = True
                return
            if kind == "cancelled":
                outcome_status = "cancelled"
                outcome_error = str(event.get("error", "Run cancelled."))
                finished = True
                finished_at = time.time()
                received_terminal_event = True
                return
            if kind == "error":
                outcome_status = "failed"
                outcome_error = str(event.get("error", "Run failed."))
                finished = True
                finished_at = time.time()
                received_terminal_event = True
                return

        try:
            while True:
                if self._is_cancel_requested(job_id):
                    outcome_status = "cancelled"
                    outcome_error = "Cancelled by user."
                    if worker.is_alive():
                        worker.terminate()
                    finished = True
                    if finished_at is None:
                        finished_at = time.time()

                try:
                    event = event_queue.get(timeout=0.5)
                    if isinstance(event, dict):
                        _handle_event(event)
                except queue.Empty:
                    pass
                except Exception:
                    logger.exception("Failed reading subprocess event queue for job_id=%s", job_id)

                now = time.time()
                if worker.is_alive() and (now - last_heartbeat_at) >= 10.0:
                    self._emit_runtime_heartbeat(job_id, started_at=started_at, last_event_at=last_event_at)
                    last_heartbeat_at = now

                if finished and worker.is_alive():
                    try:
                        worker.join(timeout=0.5)
                    except Exception:
                        pass
                    now = time.time()
                    if worker.is_alive() and finished_at is not None and (now - finished_at) >= 15.0:
                        try:
                            worker.terminate()
                            worker.join(timeout=2.0)
                            if worker.is_alive():
                                worker.kill()
                        except Exception:
                            pass

                if not worker.is_alive():
                    # Drain any final events emitted before process exit.
                    while True:
                        try:
                            tail_event = event_queue.get_nowait()
                        except queue.Empty:
                            break
                        except Exception:
                            break
                        if isinstance(tail_event, dict):
                            _handle_event(tail_event)
                    if self._is_cancel_requested(job_id) and outcome_status != "succeeded":
                        outcome_status = "cancelled"
                        outcome_error = "Cancelled by user."
                    break

            exit_code = worker.exitcode
            if outcome_status == "succeeded" and outcome_run_id and outcome_summary is not None:
                return outcome_status, outcome_run_id, outcome_summary, ""
            if outcome_status == "cancelled":
                return "cancelled", None, None, outcome_error or "Cancelled by user."

            if not outcome_error:
                outcome_error = f"Worker process exited unexpectedly (exit_code={exit_code})."
            if exit_code not in (0, None) and "exit_code" not in outcome_error and (not received_terminal_event):
                outcome_error = f"{outcome_error} (exit_code={exit_code})"
            return "failed", None, None, outcome_error
        finally:
            with self._lock:
                self._active_processes.pop(job_id, None)
                current = self._jobs.get(job_id)
                if current is not None and current.worker_pid is not None:
                    current.worker_pid = None
                    current.updated_at = time.time()

    def _worker_loop(self) -> None:
        while True:
            job_id = self._queue.get()
            with self._lock:
                rec = self._jobs.get(job_id)
                if rec is None:
                    self._queue.task_done()
                    continue
                if rec.status == "cancelled" or rec.cancel_requested:
                    rec.status = "cancelled"
                    rec.progress = 1.0
                    rec.stage = "cancelled"
                    rec.message = "Run cancelled before start."
                    rec.error = "Cancelled by user."
                    rec.finished_at = time.time()
                    rec.updated_at = rec.finished_at
                    rec.worker_pid = None
                    if job_id in self._pending:
                        self._pending.remove(job_id)
                    self._queue.task_done()
                    continue
                rec.status = "running"
                rec.started_at = time.time()
                rec.progress = max(rec.progress, 0.05)
                rec.stage = "starting"
                rec.message = "Starting run"
                rec.updated_at = rec.started_at
                rec.worker_pid = None
                if job_id in self._pending:
                    self._pending.remove(job_id)

            try:
                if self._use_subprocess:
                    status, run_id, summary, err_text = self._run_job_subprocess(job_id, rec)
                    if status == "succeeded" and run_id and isinstance(summary, dict):
                        with self._lock:
                            rec.status = "succeeded"
                            rec.progress = 1.0
                            rec.stage = "complete"
                            rec.message = "Run completed"
                            rec.run_id = run_id
                            rec.summary = summary
                            rec.finished_at = time.time()
                            rec.updated_at = rec.finished_at
                            rec.worker_pid = None
                    elif status == "cancelled":
                        with self._lock:
                            rec.status = "cancelled"
                            rec.error = err_text or "Cancelled by user."
                            rec.stage = "cancelled"
                            rec.message = "Run cancelled."
                            rec.progress = 1.0
                            rec.finished_at = time.time()
                            rec.updated_at = rec.finished_at
                            rec.worker_pid = None
                    else:
                        with self._lock:
                            rec.status = "failed"
                            rec.error = err_text or "Run failed."
                            rec.stage = "failed"
                            rec.message = "Run failed"
                            rec.finished_at = time.time()
                            rec.updated_at = rec.finished_at
                            rec.worker_pid = None
                else:
                    run_id, summary, _, _ = run_calliope_synchronously(
                        self._settings,
                        rec.request,
                        progress_callback=lambda stage, progress, message: self._update_progress(
                            job_id, stage, progress, message
                        ),
                        cancel_requested=lambda: self._is_cancel_requested(job_id),
                    )
                    with self._lock:
                        if rec.cancel_requested:
                            rec.status = "cancelled"
                            rec.progress = 1.0
                            rec.stage = "cancelled"
                            rec.message = "Run cancelled after completion checkpoint."
                            rec.error = "Cancelled by user."
                            rec.finished_at = time.time()
                            rec.updated_at = rec.finished_at
                            rec.worker_pid = None
                            self._trim_history_locked()
                            continue
                        rec.status = "succeeded"
                        rec.progress = 1.0
                        rec.stage = "complete"
                        rec.message = "Run completed"
                        rec.run_id = run_id
                        rec.summary = summary
                        rec.finished_at = time.time()
                        rec.updated_at = rec.finished_at
                        rec.worker_pid = None
            except RunCancelledError as e:
                with self._lock:
                    rec.status = "cancelled"
                    rec.error = str(e)
                    rec.stage = "cancelled"
                    rec.message = "Run cancelled."
                    rec.progress = 1.0
                    rec.finished_at = time.time()
                    rec.updated_at = rec.finished_at
                    rec.worker_pid = None
            except Exception as e:  # pragma: no cover - guarded by API tests
                logger.exception("Asynchronous run failed for job_id=%s", job_id)
                with self._lock:
                    rec.status = "failed"
                    rec.error = str(e)
                    rec.stage = "failed"
                    rec.message = "Run failed"
                    rec.finished_at = time.time()
                    rec.updated_at = rec.finished_at
                    rec.worker_pid = None
            finally:
                with self._lock:
                    self._active_processes.pop(job_id, None)
                    self._trim_history_locked()
                self._queue.task_done()
