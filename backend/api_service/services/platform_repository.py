"""Postgres-backed implementation of the PlatformRepository protocol.

Implements plan chapter 3.2 with mandatory ownership filtering at the
SQL level (plan 2.3.1, 3.5). Admins see all records; regular users see
only records where owner_user_id matches their UserContext.

This module is the only file in the codebase that should construct
or query the platform tables directly. Routes and services go through
this repository.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db_models import (
    ProjectRecord,
    ProjectRunRecord,
    ReportRecord,
    ExportRecord,
    UserRecord,
    RUN_STATUSES,
    REPORT_STATUSES,
)
from ..runtime.stores import (
    PlatformRepository,
    ProjectSummary,
    RunSummaryRecord,
    ReportSummary,
)
from ..users import UserContext

logger = logging.getLogger(__name__)


def _iso(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_user(session: Session, actor: UserContext) -> None:
    """Upsert the actor into the users table. Plan 2.3.1 / 3.3.1."""
    existing = session.get(UserRecord, actor.user_id)
    now = _utcnow()
    if existing is None:
        session.add(
            UserRecord(
                user_id=actor.user_id,
                display_name=actor.display_name,
                email=actor.email,
                organization=actor.organization,
                is_admin=actor.is_admin,
                auth_mode=actor.auth_mode.value,
                first_seen_at=now,
                last_seen_at=now,
            )
        )
    else:
        existing.last_seen_at = now
        existing.is_admin = existing.is_admin or actor.is_admin
        if actor.display_name:
            existing.display_name = actor.display_name
        if actor.email:
            existing.email = actor.email


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _project_summary(rec: ProjectRecord) -> ProjectSummary:
    return ProjectSummary(
        project_id=rec.project_id,
        owner_user_id=rec.owner_user_id,
        title=rec.title,
        geography_code=rec.geography_code or "",
        use_case_label=rec.use_case_label or "",
        archived=rec.archived,
        created_at=_iso(rec.created_at),
        updated_at=_iso(rec.updated_at),
    )


def _run_summary(rec: ProjectRunRecord) -> RunSummaryRecord:
    return RunSummaryRecord(
        run_id=rec.run_id,
        project_id=rec.project_id,
        owner_user_id=rec.owner_user_id,
        status=rec.status,
        run_profile=rec.run_profile,
        energy_scenario_key=rec.energy_scenario_key,
        mrio_scenario_id=rec.mrio_scenario_id,
        target_year=rec.target_year,
        created_at=_iso(rec.created_at),
        updated_at=_iso(rec.updated_at),
    )


def _report_summary(rec: ReportRecord) -> ReportSummary:
    return ReportSummary(
        report_id=rec.report_id,
        project_id=rec.project_id,
        owner_user_id=rec.owner_user_id,
        title=rec.title,
        status=rec.status,
        storage_ref=rec.storage_ref,
        created_at=_iso(rec.created_at),
        updated_at=_iso(rec.updated_at),
    )


def _export_summary(rec: ExportRecord) -> ReportSummary:
    # Reuse ReportSummary for exports; they have the same shape.
    return ReportSummary(
        report_id=rec.export_id,
        project_id=rec.project_id,
        owner_user_id=rec.owner_user_id,
        title="",
        status=rec.status,
        storage_ref=rec.storage_ref,
        created_at=_iso(rec.created_at),
        updated_at=_iso(rec.updated_at),
    )


class PostgresPlatformRepository(PlatformRepository):
    """SQLAlchemy-backed PlatformRepository. Plan 3.2."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    # -- session context manager helper --
    def _session(self) -> Session:
        return self._session_factory()

    # ------------------------------------------------------------------
    # Ownership predicate helper (plan 2.3.1, 3.5)
    # ------------------------------------------------------------------

    @staticmethod
    def _owner_clause(actor: UserContext, column):
        """Return a SQLAlchemy filter that restricts a query to rows
        the actor is allowed to see. Admins see everything.
        """
        if actor.is_admin:
            return None
        return column == actor.user_id

    # ------------------------------------------------------------------
    # projects
    # ------------------------------------------------------------------

    def create_project(self, actor: UserContext, **fields) -> ProjectSummary:
        with self._session() as session:
            _ensure_user(session, actor)
            project_id = fields.get("project_id") or _new_id("proj")
            rec = ProjectRecord(
                project_id=project_id,
                owner_user_id=actor.user_id,   # plan 2.3.1: immutable ownership tag
                title=fields.get("title", "Untitled project"),
                geography_code=fields.get("geography_code", ""),
                geography_label=fields.get("geography_label", ""),
                use_case_label=fields.get("use_case_label", ""),
                description=fields.get("description", ""),
            )
            session.add(rec)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                # Retry once with a fresh id.
                rec.project_id = _new_id("proj")
                session.add(rec)
                session.commit()
            session.refresh(rec)
            return _project_summary(rec)

    def get_project(self, actor: UserContext, project_id: str) -> Optional[ProjectSummary]:
        with self._session() as session:
            stmt = select(ProjectRecord).where(ProjectRecord.project_id == project_id)
            owner_filter = self._owner_clause(actor, ProjectRecord.owner_user_id)
            if owner_filter is not None:
                stmt = stmt.where(owner_filter)
            rec = session.execute(stmt).scalar_one_or_none()
            return _project_summary(rec) if rec else None

    def list_projects(self, actor: UserContext, limit: int = 100) -> list[ProjectSummary]:
        with self._session() as session:
            stmt = select(ProjectRecord).order_by(ProjectRecord.updated_at.desc()).limit(max(1, min(limit, 500)))
            owner_filter = self._owner_clause(actor, ProjectRecord.owner_user_id)
            if owner_filter is not None:
                stmt = stmt.where(owner_filter)
            recs = session.execute(stmt).scalars().all()
            return [_project_summary(r) for r in recs]

    def update_project(self, actor: UserContext, project_id: str, **fields) -> ProjectSummary:
        with self._session() as session:
            stmt = select(ProjectRecord).where(ProjectRecord.project_id == project_id)
            owner_filter = self._owner_clause(actor, ProjectRecord.owner_user_id)
            if owner_filter is not None:
                stmt = stmt.where(owner_filter)
            rec = session.execute(stmt).scalar_one_or_none()
            if rec is None:
                raise LookupError(f"Project not found: {project_id}")
            for key in ("title", "geography_code", "geography_label", "use_case_label", "description", "archived"):
                if key in fields:
                    setattr(rec, key, fields[key])
            session.commit()
            session.refresh(rec)
            return _project_summary(rec)

    def archive_project(self, actor: UserContext, project_id: str) -> ProjectSummary:
        return self.update_project(actor, project_id, archived=True)

    # ------------------------------------------------------------------
    # runs
    # ------------------------------------------------------------------

    def create_run(self, actor: UserContext, project_id: str, **fields) -> RunSummaryRecord:
        with self._session() as session:
            _ensure_user(session, actor)
            # Validate project ownership before creating a run.
            proj_stmt = select(ProjectRecord).where(ProjectRecord.project_id == project_id)
            owner_filter = self._owner_clause(actor, ProjectRecord.owner_user_id)
            if owner_filter is not None:
                proj_stmt = proj_stmt.where(owner_filter)
            proj = session.execute(proj_stmt).scalar_one_or_none()
            if proj is None:
                raise LookupError(f"Project not found: {project_id}")
            run_id = fields.get("run_id") or _new_id("run")
            rec = ProjectRunRecord(
                run_id=run_id,
                project_id=project_id,
                owner_user_id=actor.user_id,    # plan 2.3.1
                status=fields.get("status", "draft"),
                run_profile=fields.get("run_profile", "dev"),
                energy_scenario_key=fields["energy_scenario_key"],
                mrio_scenario_id=fields["mrio_scenario_id"],
                target_year=int(fields["target_year"]),
                request_payload=fields.get("request_payload", {}),
                execution_queue_message=fields.get("execution_queue_message"),
                active_execution_id=fields.get("active_execution_id"),
            )
            session.add(rec)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                rec.run_id = _new_id("run")
                session.add(rec)
                session.commit()
            session.refresh(rec)
            return _run_summary(rec)

    def get_run(self, actor: UserContext, run_id: str) -> Optional[RunSummaryRecord]:
        with self._session() as session:
            stmt = select(ProjectRunRecord).where(ProjectRunRecord.run_id == run_id)
            owner_filter = self._owner_clause(actor, ProjectRunRecord.owner_user_id)
            if owner_filter is not None:
                stmt = stmt.where(owner_filter)
            rec = session.execute(stmt).scalar_one_or_none()
            return _run_summary(rec) if rec else None

    def list_runs(
        self, actor: UserContext, project_id: Optional[str] = None, limit: int = 100
    ) -> list[RunSummaryRecord]:
        with self._session() as session:
            stmt = select(ProjectRunRecord).order_by(ProjectRunRecord.updated_at.desc()).limit(max(1, min(limit, 500)))
            if project_id is not None:
                stmt = stmt.where(ProjectRunRecord.project_id == project_id)
            owner_filter = self._owner_clause(actor, ProjectRunRecord.owner_user_id)
            if owner_filter is not None:
                stmt = stmt.where(owner_filter)
            recs = session.execute(stmt).scalars().all()
            return [_run_summary(r) for r in recs]

    def update_run_status(self, actor: UserContext, run_id: str, status: str, **fields) -> RunSummaryRecord:
        if status not in RUN_STATUSES:
            raise ValueError(f"Invalid run status: {status}")
        with self._session() as session:
            stmt = select(ProjectRunRecord).where(ProjectRunRecord.run_id == run_id)
            owner_filter = self._owner_clause(actor, ProjectRunRecord.owner_user_id)
            if owner_filter is not None:
                stmt = stmt.where(owner_filter)
            rec = session.execute(stmt).scalar_one_or_none()
            if rec is None:
                raise LookupError(f"Run not found: {run_id}")
            rec.status = status
            if "active_execution_id" in fields:
                rec.active_execution_id = fields["active_execution_id"]
            if "started_at" in fields:
                rec.started_at = fields["started_at"]
            if "finished_at" in fields:
                rec.finished_at = fields["finished_at"]
            if "execution_queue_message" in fields:
                rec.execution_queue_message = fields["execution_queue_message"]
            session.commit()
            session.refresh(rec)
            return _run_summary(rec)

    def set_run_cancellation(self, actor: UserContext, run_id: str, requested: bool) -> None:
        with self._session() as session:
            stmt = select(ProjectRunRecord).where(ProjectRunRecord.run_id == run_id)
            owner_filter = self._owner_clause(actor, ProjectRunRecord.owner_user_id)
            if owner_filter is not None:
                stmt = stmt.where(owner_filter)
            rec = session.execute(stmt).scalar_one_or_none()
            if rec is None:
                raise LookupError(f"Run not found: {run_id}")
            rec.cancellation_requested = bool(requested)
            if requested and rec.status in {"queued", "running"}:
                # Mark as cancelling; the runner will finalize to cancelled.
                if rec.status == "running":
                    rec.status = "running"  # leave status; runner polls the flag
            session.commit()

    # ------------------------------------------------------------------
    # reports & exports (plan chapter 9)
    # ------------------------------------------------------------------

    def create_report(self, actor: UserContext, project_id: str, **fields) -> ReportSummary:
        with self._session() as session:
            _ensure_user(session, actor)
            self._assert_project_owner(session, actor, project_id)
            rec = ReportRecord(
                report_id=fields.get("report_id") or _new_id("rpt"),
                project_id=project_id,
                owner_user_id=actor.user_id,
                title=fields.get("title", ""),
                status=fields.get("status", "queued"),
                selected_run_ids=fields.get("selected_run_ids", []),
            )
            session.add(rec)
            session.commit()
            session.refresh(rec)
            return _report_summary(rec)

    def get_report(self, actor: UserContext, report_id: str) -> Optional[ReportSummary]:
        with self._session() as session:
            stmt = select(ReportRecord).where(ReportRecord.report_id == report_id)
            owner_filter = self._owner_clause(actor, ReportRecord.owner_user_id)
            if owner_filter is not None:
                stmt = stmt.where(owner_filter)
            rec = session.execute(stmt).scalar_one_or_none()
            return _report_summary(rec) if rec else None

    def list_reports(
        self, actor: UserContext, project_id: Optional[str] = None, limit: int = 100
    ) -> list[ReportSummary]:
        with self._session() as session:
            stmt = select(ReportRecord).order_by(ReportRecord.updated_at.desc()).limit(max(1, min(limit, 500)))
            if project_id is not None:
                stmt = stmt.where(ReportRecord.project_id == project_id)
            owner_filter = self._owner_clause(actor, ReportRecord.owner_user_id)
            if owner_filter is not None:
                stmt = stmt.where(owner_filter)
            recs = session.execute(stmt).scalars().all()
            return [_report_summary(r) for r in recs]

    def update_report(self, actor: UserContext, report_id: str, **fields) -> ReportSummary:
        if "status" in fields and fields["status"] not in REPORT_STATUSES:
            raise ValueError(f"Invalid report status: {fields['status']}")
        with self._session() as session:
            stmt = select(ReportRecord).where(ReportRecord.report_id == report_id)
            owner_filter = self._owner_clause(actor, ReportRecord.owner_user_id)
            if owner_filter is not None:
                stmt = stmt.where(owner_filter)
            rec = session.execute(stmt).scalar_one_or_none()
            if rec is None:
                raise LookupError(f"Report not found: {report_id}")
            for key in ("title", "status", "selected_run_ids", "storage_ref", "error"):
                if key in fields:
                    setattr(rec, key, fields[key])
            session.commit()
            session.refresh(rec)
            return _report_summary(rec)

    def create_export(self, actor: UserContext, project_id: str, **fields) -> ReportSummary:
        with self._session() as session:
            _ensure_user(session, actor)
            self._assert_project_owner(session, actor, project_id)
            rec = ExportRecord(
                export_id=fields.get("export_id") or _new_id("exp"),
                project_id=project_id,
                owner_user_id=actor.user_id,
                status=fields.get("status", "queued"),
            )
            session.add(rec)
            session.commit()
            session.refresh(rec)
            return _export_summary(rec)

    def get_export(self, actor: UserContext, export_id: str) -> Optional[ReportSummary]:
        with self._session() as session:
            stmt = select(ExportRecord).where(ExportRecord.export_id == export_id)
            owner_filter = self._owner_clause(actor, ExportRecord.owner_user_id)
            if owner_filter is not None:
                stmt = stmt.where(owner_filter)
            rec = session.execute(stmt).scalar_one_or_none()
            return _export_summary(rec) if rec else None

    def update_export(self, actor: UserContext, export_id: str, **fields) -> ReportSummary:
        if "status" in fields and fields["status"] not in REPORT_STATUSES:
            raise ValueError(f"Invalid export status: {fields['status']}")
        with self._session() as session:
            stmt = select(ExportRecord).where(ExportRecord.export_id == export_id)
            owner_filter = self._owner_clause(actor, ExportRecord.owner_user_id)
            if owner_filter is not None:
                stmt = stmt.where(owner_filter)
            rec = session.execute(stmt).scalar_one_or_none()
            if rec is None:
                raise LookupError(f"Export not found: {export_id}")
            for key in ("status", "storage_ref", "error"):
                if key in fields:
                    setattr(rec, key, fields[key])
            session.commit()
            session.refresh(rec)
            return _export_summary(rec)

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _assert_project_owner(self, session: Session, actor: UserContext, project_id: str) -> None:
        stmt = select(ProjectRecord).where(ProjectRecord.project_id == project_id)
        owner_filter = self._owner_clause(actor, ProjectRecord.owner_user_id)
        if owner_filter is not None:
            stmt = stmt.where(owner_filter)
        if session.execute(stmt).scalar_one_or_none() is None:
            raise LookupError(f"Project not found: {project_id}")
