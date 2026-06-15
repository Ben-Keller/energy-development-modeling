"""State manager for execution jobs (plan 6.3, 6.4).

The JobManager is a thin wrapper that:

  1. On submit, upserts the user, creates a project (if needed), creates
     a `project_runs` row with status=queued, and enqueues an
     `ExecutionQueueMessage` to the configured execution queue.
  2. On get/list/cancel, reads and mutates the `project_runs` table.
  3. On runtime_stats, counts runs by status and queries the queue depth.

It does NOT execute model runs. Execution happens in the isolated
worker daemon (`worker/daemon.py`), which has no access to Postgres.
The worker consumes execution messages, runs the model, writes
artifacts/events to Blob Storage, and sends a completion message on
a Service Bus completion queue. The API's `WorkerBridge` consumes
those completion messages and is the only component that writes
terminal state to `project_runs` and `execution_attempts`.

Public API:
  - submit(req, user_id) -> JobInfo
  - submit_many(reqs, user_id) -> list[JobInfo]
  - get(job_id) -> JobInfo
  - cancel(job_id) -> JobInfo
  - list(limit) -> list[JobInfo]
  - runtime_stats() -> dict
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db_models import (
    DatasetVersionMetadataRecord,
    ProjectRecord,
    ProjectRunRecord,
    ProjectRunDatasetVersionRecord,
    UserRecord,
    RUN_STATUSES,
)
from .runtime.stores import QueueMessage
from .schemas import JobInfo, RunArtifacts, RunRequest
from .settings import Settings

logger = logging.getLogger(__name__)


FINAL_JOB_STATUSES = {"succeeded", "failed", "cancelled"}


def _job_id_from_run_id(run_id: str) -> str:
    return run_id.replace("run_", "job_", 1) if run_id.startswith("run_") else run_id


def _run_id_from_job_id(job_id: str) -> str:
    if job_id.startswith("run_"):
        return job_id
    if job_id.startswith("job_"):
        return job_id.replace("job_", "run_", 1)
    return job_id


class PostgresJobManager:
    """Postgres + Service Bus-backed job state manager. Plan 6.3.

    The manager is a state machine for `project_runs`. It does not
    execute runs in-process; the worker daemon consumes from the
    execution queue and writes back the terminal state.
    """

    def __init__(
        self,
        session_factory,
        settings: Settings,
        queue_provider,
        worker_bridge=None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._queue = queue_provider
        self._worker_bridge = worker_bridge

    # ------------------------------------------------------------------
    # submission
    # ------------------------------------------------------------------

    def submit(self, req: RunRequest, user_id: str) -> JobInfo:
        return self.submit_many([req], user_id)[0]

    def submit_many(self, reqs: List[RunRequest], user_id: str) -> List[JobInfo]:
        if not reqs:
            return []
        out: List[JobInfo] = []
        queued: List[Tuple[JobInfo, str, str]] = []  # (info, run_id, execution_id)

        with self._session_factory() as session:
            # Upsert the user first so the FK on projects.owner_user_id
            # resolves. Plan 2.3.1: every project/run is tagged with
            # the validated UserContext.user_id at creation.
            self._ensure_user(session, user_id)

            for req in reqs:
                project = self._ensure_default_project(session, user_id, req)
                run_id = f"run_{uuid.uuid4().hex[:12]}"
                execution_id = f"exec_{uuid.uuid4().hex[:12]}"
                rec = ProjectRunRecord(
                    run_id=run_id,
                    project_id=project.project_id,
                    owner_user_id=user_id,
                    active_execution_id=execution_id,
                    status="queued",
                    run_profile=req.run_profile,
                    energy_scenario_key=req.energy_scenario_key,
                    mrio_scenario_id=req.mrio_scenario_id,
                    target_year=req.target_year,
                    request_payload=req.model_dump(mode="json"),
                    execution_queue_message={
                        "execution_id": execution_id,
                        "run_id": run_id,
                        "project_id": project.project_id,
                        "user_id": user_id,
                        "request_payload": req.model_dump(mode="json"),
                        "attempt_count": 1,
                    },
                )
                session.add(rec)
                session.flush()
                info = self._to_job_info(rec, queue_position=None)
                info.status = "queued"
                info.stage = "queued"
                info.message = "Queued"
                info.queue_position = len(queued) + 1
                out.append(info)
                queued.append((info, run_id, execution_id))
            session.commit()

        # Enqueue messages after the transaction commits. The worker
        # will see them on its next reserve. If enqueue fails, the run
        # is still recorded as `queued` and can be re-enqueued by an
        # operator (or by a background sweeper in a future iteration).
        for info, run_id, execution_id in queued:
            message = QueueMessage(
                execution_id=execution_id,
                run_id=run_id,
                project_id=project.project_id,
                user_id=user_id,
                request_payload=info.request.model_dump(mode="json"),
                dataset_versions=self._dataset_versions_for_run(session, run_id),
                attempt_count=1,
            )
            try:
                self._queue.enqueue(message)
            except Exception:
                logger.exception("Failed to enqueue message for run %s", run_id)

        return out

    def _dataset_versions_for_run(self, session: Session, run_id: str) -> list[dict]:
        stmt = (
            select(ProjectRunDatasetVersionRecord, DatasetVersionMetadataRecord)
            .join(
                DatasetVersionMetadataRecord,
                ProjectRunDatasetVersionRecord.dataset_version_id
                == DatasetVersionMetadataRecord.dataset_version_id,
            )
            .where(ProjectRunDatasetVersionRecord.run_id == run_id)
        )
        out: list[dict] = []
        for link, version in session.execute(stmt):
            out.append(
                {
                    "dataset_id": link.dataset_id,
                    "version_id": version.dataset_version_id,
                    "storage_uri": version.storage_uri,
                    "file_hash": version.file_hash,
                    "mime_type": version.mime_type,
                }
            )
        return out

    def _ensure_user(self, session: Session, user_id: str, display_name: str = "", email: str = "") -> None:
        existing = session.get(UserRecord, user_id)
        now = datetime.now(timezone.utc)
        if existing is None:
            session.add(
                UserRecord(
                    user_id=user_id,
                    display_name=display_name or user_id,
                    email=email or f"{user_id}@dev.local",
                    organization="local-dev",
                    is_admin=False,
                    auth_mode="test_header",
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
            session.flush()
        else:
            existing.last_seen_at = now

    def _ensure_default_project(self, session: Session, user_id: str, req: RunRequest) -> ProjectRecord:
        """Look up or create a project that owns the run.

        For the migration, we use a single per-user project keyed by
        the energy scenario. A future iteration will expose explicit
        project creation in the API.
        """
        stmt = select(ProjectRecord).where(
            ProjectRecord.owner_user_id == user_id,
            ProjectRecord.title == f"Default project ({req.energy_scenario_key})",
        )
        existing = session.execute(stmt).scalar_one_or_none()
        if existing is not None:
            return existing
        project = ProjectRecord(
            project_id=f"proj_{uuid.uuid4().hex[:12]}",
            owner_user_id=user_id,
            title=f"Default project ({req.energy_scenario_key})",
            geography_code="",
            use_case_label="",
        )
        session.add(project)
        session.flush()
        return project

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------

    def get(self, job_id: str, owner_user_id: str | None = None, is_admin: bool = False) -> JobInfo:
        run_id = _run_id_from_job_id(job_id)
        with self._session_factory() as session:
            rec = session.get(ProjectRunRecord, run_id)
            if rec is None:
                raise KeyError(job_id)
            if owner_user_id and not is_admin and rec.owner_user_id != owner_user_id:
                raise KeyError(job_id)  # 404 to avoid ownership info leakage
            return self._to_job_info(rec, queue_position=None)

    def list(self, limit: int = 50, owner_user_id: str | None = None, is_admin: bool = False) -> List[JobInfo]:
        with self._session_factory() as session:
            stmt = (
                select(ProjectRunRecord)
                .order_by(ProjectRunRecord.created_at.desc())
                .limit(max(1, min(limit, 500)))
            )
            if owner_user_id and not is_admin:
                stmt = stmt.where(ProjectRunRecord.owner_user_id == owner_user_id)
            recs = session.execute(stmt).scalars().all()
            return [self._to_job_info(r, queue_position=None) for r in recs]

    def submit_run(self, run_id: str, user_id: str, is_admin: bool = False) -> JobInfo:
        """Transition a draft run to queued and enqueue it (plan 6.3.2).

        Raises KeyError if the run is not found or not owned by the user.
        Raises ValueError if the run is not in draft status.
        """
        with self._session_factory() as session:
            stmt = select(ProjectRunRecord).where(ProjectRunRecord.run_id == run_id)
            if not is_admin:
                stmt = stmt.where(ProjectRunRecord.owner_user_id == user_id)
            rec = session.execute(stmt).scalar_one_or_none()
            if rec is None:
                raise KeyError(run_id)
            if rec.status != "draft":
                raise ValueError(f"Run must be in draft status to submit (current: {rec.status})")
            execution_id = f"exec_{uuid.uuid4().hex[:12]}"
            rec.status = "queued"
            rec.active_execution_id = execution_id
            rec.execution_queue_message = {
                "execution_id": execution_id,
                "run_id": run_id,
                "project_id": rec.project_id,
                "user_id": user_id,
                "request_payload": rec.request_payload,
                "attempt_count": 1,
            }
            project_id = rec.project_id
            session.commit()
            session.refresh(rec)
            info = self._to_job_info(rec, queue_position=None)

        with self._session_factory() as session2:
            dvs = self._dataset_versions_for_run(session2, run_id)

        message = QueueMessage(
            execution_id=execution_id,
            run_id=run_id,
            project_id=project_id,
            user_id=user_id,
            request_payload=info.request.model_dump(mode="json"),
            dataset_versions=dvs,
            attempt_count=1,
        )
        try:
            self._queue.enqueue(message)
        except Exception:
            logger.exception("Failed to enqueue message for run %s; run is queued in DB", run_id)
        return info

    def cancel(self, job_id: str, owner_user_id: str | None = None, is_admin: bool = False) -> JobInfo:
        run_id = _run_id_from_job_id(job_id)
        with self._session_factory() as session:
            rec = session.get(ProjectRunRecord, run_id)
            if rec is None:
                raise KeyError(job_id)
            if owner_user_id and not is_admin and rec.owner_user_id != owner_user_id:
                raise KeyError(job_id)
            if rec.status in FINAL_JOB_STATUSES:
                return self._to_job_info(rec, queue_position=None)
            rec.cancellation_requested = True
            if rec.status == "queued":
                rec.status = "cancelled"
                rec.finished_at = datetime.now(timezone.utc)
            else:
                # Notify the isolated worker via Service Bus.
                if rec.active_execution_id and self._worker_bridge is not None:
                    self._worker_bridge.request_cancellation(
                        run_id=rec.run_id,
                        execution_id=rec.active_execution_id,
                        cancelled_by=None,
                    )
            session.commit()
            session.refresh(rec)
            return self._to_job_info(rec, queue_position=None)

    def cancel_all(self, statuses: List[str] | None = None, user_id: str | None = None) -> List[JobInfo]:
        """Cancel all jobs whose status is in `statuses` (default: queued + running).

        If `user_id` is given, only jobs owned by that user are cancelled.
        """
        target_statuses = set(statuses) if statuses else {"queued", "running"}
        now = datetime.now(timezone.utc)
        with self._session_factory() as session:
            filters = [ProjectRunRecord.status.in_(target_statuses)]
            if user_id is not None:
                filters.append(ProjectRunRecord.owner_user_id == user_id)
            stmt = select(ProjectRunRecord).where(*filters)
            recs = session.execute(stmt).scalars().all()
            for rec in recs:
                rec.cancellation_requested = True
                if rec.status == "queued":
                    rec.status = "cancelled"
                    rec.finished_at = now
                else:
                    if rec.active_execution_id and self._worker_bridge is not None:
                        self._worker_bridge.request_cancellation(
                            run_id=rec.run_id,
                            execution_id=rec.active_execution_id,
                            cancelled_by=None,
                        )
            session.commit()
            for rec in recs:
                session.refresh(rec)
            return [self._to_job_info(r, queue_position=None) for r in recs]

    def runtime_stats(self) -> Dict[str, float | int]:
        with self._session_factory() as session:
            counts = {s: 0 for s in ("queued", "running", "succeeded", "failed", "cancelled", "other")}
            for status in RUN_STATUSES:
                stmt = select(ProjectRunRecord).where(ProjectRunRecord.status == status)
                counts[status] = len(session.execute(stmt).scalars().all())
        capacity = max(1, int(self._settings.job_queue_capacity))
        active = counts["queued"] + counts["running"]
        try:
            depth = int(self._queue.depth())
        except Exception:
            depth = counts["queued"]
        return {
            "capacity": capacity,
            "active_jobs": active,
            "queued_jobs": counts["queued"],
            "running_jobs": counts["running"],
            "succeeded_jobs": counts["succeeded"],
            "failed_jobs": counts["failed"],
            "cancelled_jobs": counts["cancelled"],
            "other_jobs": counts["other"],
            "tracked_jobs": sum(counts.values()),
            "queue_depth": max(0, depth),
            "utilization_share": active / float(capacity),
        }

    # ------------------------------------------------------------------
    # DTO conversion
    # ------------------------------------------------------------------

    def _to_job_info(self, rec: ProjectRunRecord, queue_position: Optional[int]) -> JobInfo:
        try:
            req = RunRequest(**(rec.request_payload or {}))
        except Exception:
            req = RunRequest(
                energy_scenario_key=rec.energy_scenario_key,
                mrio_scenario_id=rec.mrio_scenario_id,
                target_year=rec.target_year,
                run_profile=rec.run_profile,
                strict_validation=False,
                allow_placeholder_data=True,
            )
        artifacts = (
            RunArtifacts(
                run_id=rec.run_id,
                summary_url=f"/api/run/{rec.run_id}/summary",
                csv_url=f"/api/run/{rec.run_id}/download/csv",
            )
            if rec.status == "succeeded"
            else None
        )
        progress = 0.0
        if rec.status == "succeeded":
            progress = 1.0
        elif rec.status == "running":
            progress = 0.5
        return JobInfo(
            job_id=_job_id_from_run_id(rec.run_id),
            status=rec.status,
            progress=progress,
            stage=rec.status,
            message=rec.status.title(),
            queue_position=queue_position,
            created_at=rec.created_at.isoformat() if rec.created_at else "",
            started_at=rec.started_at.isoformat() if rec.started_at else None,
            finished_at=rec.finished_at.isoformat() if rec.finished_at else None,
            updated_at=rec.updated_at.isoformat() if rec.updated_at else None,
            worker_pid=None,
            error=None,
            request=req,
            artifacts=artifacts,
            summary=None,
        )
