"""SQLAlchemy ORM models for the EDIM relational schema.

Implements plan chapter 3.3 (relational data model). All tables include
owner_user_id (plan 2.3.1, 3.5) so the Postgres repositories can apply
mandatory ownership filters at the SQL level. Datasets and runs are
linked through project_runs_dataset_versions (plan 3.3.2 / 5.3 reference
locking): deleting a dataset version that is still referenced by a run
will raise an IntegrityError.

The ORM definitions are the source of truth for table structure. Alembic
migrations are generated from these models (autogenerate) and committed
to the repo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Common metadata for all EDIM ORM models."""

    pass


# ---------------------------------------------------------------------------
# Users (plan 3.3.1)
# ---------------------------------------------------------------------------


class UserRecord(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(512), default="")
    email: Mapped[str] = mapped_column(String(512), default="")
    organization: Mapped[str] = mapped_column(String(512), default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auth_mode: Mapped[str] = mapped_column(String(32), default="test_header", nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<UserRecord user_id={self.user_id!r} is_admin={self.is_admin}>"


# ---------------------------------------------------------------------------
# Projects (plan 3.3.1)
# ---------------------------------------------------------------------------


class ProjectRecord(Base):
    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("users.user_id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    geography_code: Mapped[str] = mapped_column(String(32), default="")
    geography_label: Mapped[str] = mapped_column(String(256), default="")
    use_case_label: Mapped[str] = mapped_column(String(256), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    runs: Mapped[list["ProjectRunRecord"]] = relationship(back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_projects_owner_updated", "owner_user_id", "updated_at"),
    )


# ---------------------------------------------------------------------------
# Project Runs (plan 3.3.1, 3.3.2, 6.3)
# ---------------------------------------------------------------------------

# Allowed statuses from plan 6.3.1.
RUN_STATUSES = ("draft", "queued", "running", "succeeded", "failed", "cancelled")


class ProjectRunRecord(Base):
    __tablename__ = "project_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), index=True, nullable=False
    )
    owner_user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    active_execution_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    execution_queue_message: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    run_profile: Mapped[str] = mapped_column(String(32), default="dev", nullable=False)
    energy_scenario_key: Mapped[str] = mapped_column(String(128), nullable=False)
    mrio_scenario_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_year: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["ProjectRecord"] = relationship(back_populates="runs")
    attempts: Mapped[list["ExecutionAttemptRecord"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    dataset_links: Mapped[list["ProjectRunDatasetVersionRecord"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_project_runs_owner_updated", "owner_user_id", "updated_at"),
        Index("ix_project_runs_status", "status"),
    )


class ExecutionAttemptRecord(Base):
    """Plan 6.5: one row per worker engagement with a queue message."""

    __tablename__ = "execution_attempts"

    attempt_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("project_runs.run_id", ondelete="CASCADE"), index=True, nullable=False
    )
    execution_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    worker_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    run: Mapped["ProjectRunRecord"] = relationship(back_populates="attempts")

    __table_args__ = (
        UniqueConstraint("execution_id", "attempt_count", name="uq_execution_attempt"),
    )


# ---------------------------------------------------------------------------
# Datasets (plan 3.3.1, 5.2, 5.3)
# ---------------------------------------------------------------------------


class DatasetVersionMetadataRecord(Base):
    """Immutable record per file upload (plan 5.2.1)."""

    __tablename__ = "dataset_version_metadata"

    dataset_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    owner_user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    validation_metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("dataset_id", "file_hash", name="uq_dataset_version_hash"),
    )


class DatasetVersionPointerRecord(Base):
    """Active version pointer for a dataset (plan 3.3.1, 5.2.2)."""

    __tablename__ = "dataset_version_pointers"

    dataset_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    active_version_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("dataset_version_metadata.dataset_version_id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Project-Run <-> Dataset-Version reference locking (plan 3.3.2, 5.3)
# ---------------------------------------------------------------------------


class ProjectRunDatasetVersionRecord(Base):
    """Snapshot of dataset version IDs used at run submission.

    The combination of (run_id, dataset_id) is unique, and the FK to
    dataset_version_metadata prevents the referenced version from being
    deleted (reference locking).
    """

    __tablename__ = "project_runs_dataset_versions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("project_runs.run_id", ondelete="CASCADE"), index=True, nullable=False
    )
    dataset_id: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("dataset_version_metadata.dataset_version_id", ondelete="RESTRICT"),
        nullable=False,
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    run: Mapped["ProjectRunRecord"] = relationship(back_populates="dataset_links")

    __table_args__ = (
        UniqueConstraint("run_id", "dataset_id", name="uq_run_dataset"),
    )


# ---------------------------------------------------------------------------
# Reports & Exports (plan 3.3.1, 9.1, 9.2, 9.3)
# ---------------------------------------------------------------------------


REPORT_STATUSES = ("queued", "started", "succeeded", "failed", "cancelled")


class ReportRecord(Base):
    __tablename__ = "reports"

    report_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), index=True, nullable=False
    )
    owner_user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    selected_run_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    storage_ref: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)


class ExportRecord(Base):
    __tablename__ = "exports"

    export_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), index=True, nullable=False
    )
    owner_user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    storage_ref: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Runtime Events (plan chapter 8)
# ---------------------------------------------------------------------------


class ExecutionEventRecord(Base):
    """Persistent event log entries (plan 8.3, 8.5).

    Indexed on (execution_id, timestamp) for ordered polling by the UI.
    """

    __tablename__ = "execution_events"

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    execution_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    run_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    level: Mapped[str] = mapped_column(String(16), default="info", nullable=False)
    stage: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_execution_events_exec_ts", "execution_id", "timestamp"),
    )
