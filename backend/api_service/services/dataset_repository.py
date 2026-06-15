"""Postgres-backed implementation of the DatasetRepository protocol.

Implements plan chapter 5 with reference-locking semantics (plan 5.3).
The project_runs_dataset_versions table has a FK ON DELETE RESTRICT
against dataset_version_metadata, so calling hard_delete_version on a
version that is still referenced by any run will raise IntegrityError.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db_models import (
    DatasetVersionMetadataRecord,
    DatasetVersionPointerRecord,
)
from ..runtime.stores import DatasetRepository, DatasetVersionRecord
from ..users import UserContext

logger = logging.getLogger(__name__)


def _iso(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _new_version_id() -> str:
    return f"dsv_{uuid.uuid4().hex[:12]}"


def _to_record(rec: DatasetVersionMetadataRecord) -> DatasetVersionRecord:
    return DatasetVersionRecord(
        dataset_version_id=rec.dataset_version_id,
        dataset_id=rec.dataset_id,
        owner_user_id=rec.owner_user_id,
        storage_uri=rec.storage_uri,
        file_hash=rec.file_hash,
        file_size_bytes=rec.file_size_bytes,
        mime_type=rec.mime_type,
        validation_metrics=rec.validation_metrics or {},
        is_archived=rec.is_archived,
        created_at=_iso(rec.created_at),
    )


class PostgresDatasetRepository(DatasetRepository):
    """SQLAlchemy-backed DatasetRepository. Plan 5.1."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def _session(self) -> Session:
        return self._session_factory()

    @staticmethod
    def _owner_clause(actor: UserContext, column):
        if actor.is_admin:
            return None
        return column == actor.user_id

    def register_version(self, actor: UserContext, **fields) -> DatasetVersionRecord:
        with self._session() as session:
            version_id = fields.get("dataset_version_id") or _new_version_id()
            rec = DatasetVersionMetadataRecord(
                dataset_version_id=version_id,
                dataset_id=fields["dataset_id"],
                owner_user_id=actor.user_id,  # plan 5.2.1
                storage_uri=fields["storage_uri"],
                file_hash=fields["file_hash"],
                file_size_bytes=int(fields.get("file_size_bytes", 0)),
                mime_type=fields.get("mime_type", ""),
                validation_metrics=fields.get("validation_metrics", {}),
            )
            session.add(rec)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                rec.dataset_version_id = _new_version_id()
                session.add(rec)
                session.commit()
            session.refresh(rec)
            return _to_record(rec)

    def get_version(self, actor: UserContext, dataset_version_id: str) -> Optional[DatasetVersionRecord]:
        with self._session() as session:
            stmt = select(DatasetVersionMetadataRecord).where(
                DatasetVersionMetadataRecord.dataset_version_id == dataset_version_id
            )
            owner_filter = self._owner_clause(actor, DatasetVersionMetadataRecord.owner_user_id)
            if owner_filter is not None:
                stmt = stmt.where(owner_filter)
            rec = session.execute(stmt).scalar_one_or_none()
            return _to_record(rec) if rec else None

    def list_versions(self, actor: UserContext, dataset_id: str) -> list[DatasetVersionRecord]:
        with self._session() as session:
            stmt = (
                select(DatasetVersionMetadataRecord)
                .where(DatasetVersionMetadataRecord.dataset_id == dataset_id)
                .order_by(DatasetVersionMetadataRecord.created_at.desc())
            )
            owner_filter = self._owner_clause(actor, DatasetVersionMetadataRecord.owner_user_id)
            if owner_filter is not None:
                stmt = stmt.where(owner_filter)
            recs = session.execute(stmt).scalars().all()
            return [_to_record(r) for r in recs]

    def list_all_for_owner(self, actor: UserContext) -> list[DatasetVersionRecord]:
        with self._session() as session:
            stmt = (
                select(DatasetVersionMetadataRecord)
                .order_by(DatasetVersionMetadataRecord.created_at.desc())
            )
            owner_filter = self._owner_clause(actor, DatasetVersionMetadataRecord.owner_user_id)
            if owner_filter is not None:
                stmt = stmt.where(owner_filter)
            recs = session.execute(stmt).scalars().all()
            return [_to_record(r) for r in recs]

    def activate_version(self, actor: UserContext, dataset_id: str, dataset_version_id: str) -> None:
        with self._session() as session:
            # Verify version ownership.
            vstmt = select(DatasetVersionMetadataRecord).where(
                DatasetVersionMetadataRecord.dataset_version_id == dataset_version_id,
                DatasetVersionMetadataRecord.dataset_id == dataset_id,
            )
            owner_filter = self._owner_clause(actor, DatasetVersionMetadataRecord.owner_user_id)
            if owner_filter is not None:
                vstmt = vstmt.where(owner_filter)
            version = session.execute(vstmt).scalar_one_or_none()
            if version is None:
                raise LookupError(f"Dataset version not found: {dataset_version_id}")
            # Upsert pointer.
            pstmt = select(DatasetVersionPointerRecord).where(
                DatasetVersionPointerRecord.dataset_id == dataset_id
            )
            owner_filter = self._owner_clause(actor, DatasetVersionPointerRecord.owner_user_id)
            if owner_filter is not None:
                pstmt = pstmt.where(owner_filter)
            pointer = session.execute(pstmt).scalar_one_or_none()
            if pointer is None:
                session.add(
                    DatasetVersionPointerRecord(
                        dataset_id=dataset_id,
                        owner_user_id=actor.user_id,
                        active_version_id=dataset_version_id,
                    )
                )
            else:
                pointer.active_version_id = dataset_version_id
            session.commit()

    def get_active_version(self, actor: UserContext, dataset_id: str) -> Optional[DatasetVersionRecord]:
        with self._session() as session:
            pstmt = select(DatasetVersionPointerRecord).where(
                DatasetVersionPointerRecord.dataset_id == dataset_id
            )
            owner_filter = self._owner_clause(actor, DatasetVersionPointerRecord.owner_user_id)
            if owner_filter is not None:
                pstmt = pstmt.where(owner_filter)
            pointer = session.execute(pstmt).scalar_one_or_none()
            if pointer is None or pointer.active_version_id is None:
                return None
            vstmt = select(DatasetVersionMetadataRecord).where(
                DatasetVersionMetadataRecord.dataset_version_id == pointer.active_version_id
            )
            rec = session.execute(vstmt).scalar_one_or_none()
            return _to_record(rec) if rec else None

    def archive_version(self, actor: UserContext, dataset_version_id: str) -> DatasetVersionRecord:
        with self._session() as session:
            stmt = select(DatasetVersionMetadataRecord).where(
                DatasetVersionMetadataRecord.dataset_version_id == dataset_version_id
            )
            owner_filter = self._owner_clause(actor, DatasetVersionMetadataRecord.owner_user_id)
            if owner_filter is not None:
                stmt = stmt.where(owner_filter)
            rec = session.execute(stmt).scalar_one_or_none()
            if rec is None:
                raise LookupError(f"Dataset version not found: {dataset_version_id}")
            rec.is_archived = True
            session.commit()
            session.refresh(rec)
            return _to_record(rec)

    def hard_delete_version(self, actor: UserContext, dataset_version_id: str) -> bool:
        """Attempt a destructive delete. Plan 5.3: blocked by FK if any
        run still references the version (IntegrityError raised by
        project_runs_dataset_versions.dataset_version_id FK ON DELETE
        RESTRICT)."""
        with self._session() as session:
            stmt = select(DatasetVersionMetadataRecord).where(
                DatasetVersionMetadataRecord.dataset_version_id == dataset_version_id
            )
            owner_filter = self._owner_clause(actor, DatasetVersionMetadataRecord.owner_user_id)
            if owner_filter is not None:
                stmt = stmt.where(owner_filter)
            rec = session.execute(stmt).scalar_one_or_none()
            if rec is None:
                return False
            session.delete(rec)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                logger.info("hard_delete_version blocked by reference lock: %s", exc)
                raise
            return True
