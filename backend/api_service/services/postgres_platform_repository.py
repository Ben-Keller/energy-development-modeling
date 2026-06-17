"""PostgreSQL-backed platform metadata repository.

Direct port of SQLitePlatformRepository to SQLAlchemy + Postgres.
Uses the same platform_records JSON-blob table schema so all business
logic is identical; only the storage layer differs.

Injected into create_app() when EDIM_DATABASE_URL is set.
"""

from __future__ import annotations

import json
import shutil
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Iterator, List, Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..settings import Settings
from .dataset_repository import normalize_scope_id
from .platform_artifacts import (
    build_project_export_artifact,
    build_report_artifacts,
    load_run_summary_for_report,
    platform_storage_ref_path,
)
from .users import DEFAULT_USER_ID, is_admin_user

LOCAL_USER_ID = DEFAULT_USER_ID

_UPSERT_SQL = text("""
    INSERT INTO platform_records(
        kind, record_id, owner_user_id, project_id,
        execution_id, status, created_at, updated_at, payload_json
    )
    VALUES (
        :kind, :record_id, :owner_user_id, :project_id,
        :execution_id, :status, :created_at, :updated_at, :payload_json
    )
    ON CONFLICT(kind, record_id) DO UPDATE SET
        owner_user_id = EXCLUDED.owner_user_id,
        project_id    = EXCLUDED.project_id,
        execution_id  = EXCLUDED.execution_id,
        status        = EXCLUDED.status,
        created_at    = EXCLUDED.created_at,
        updated_at    = EXCLUDED.updated_at,
        payload_json  = EXCLUDED.payload_json
""")

_SELECT_ONE_SQL = text(
    "SELECT payload_json FROM platform_records WHERE kind = :kind AND record_id = :record_id"
)
_SELECT_ALL_SQL = text(
    "SELECT payload_json FROM platform_records WHERE kind = :kind ORDER BY updated_at DESC"
)
_SELECT_BY_EXEC_SQL = text(
    "SELECT payload_json FROM platform_records"
    " WHERE kind = 'run' AND execution_id = :execution_id"
    " ORDER BY updated_at DESC LIMIT 1"
)
_DELETE_SQL = text(
    "DELETE FROM platform_records WHERE kind = :kind AND record_id = :record_id"
)


class PostgresPlatformRepository:
    """SQLAlchemy-backed PlatformRepository using JSON-blob platform_records table."""

    def __init__(self, session_factory, settings: Settings) -> None:
        self._session_factory = session_factory
        self._settings = settings

    @property
    def settings(self) -> Settings:
        return self._settings

    # ------------------------------------------------------------------
    # Session / transaction helpers
    # ------------------------------------------------------------------

    @contextmanager
    def _transaction(self) -> Iterator[Session]:
        with self._session_factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    def _record(self, kind: str, record_id: str, *, session: Optional[Session] = None) -> Dict[str, Any] | None:
        safe_id = normalize_scope_id(record_id, "")
        if not safe_id:
            return None
        if session is not None:
            row = session.execute(_SELECT_ONE_SQL, {"kind": kind, "record_id": safe_id}).fetchone()
        else:
            with self._session_factory() as s:
                row = s.execute(_SELECT_ONE_SQL, {"kind": kind, "record_id": safe_id}).fetchone()
        if not row:
            return None
        payload = _loads(row[0])
        return _normalize_owner(payload) if isinstance(payload, dict) else None

    def _records(self, kind: str, *, session: Optional[Session] = None) -> List[Dict[str, Any]]:
        if session is not None:
            rows = session.execute(_SELECT_ALL_SQL, {"kind": kind}).fetchall()
        else:
            with self._session_factory() as s:
                rows = s.execute(_SELECT_ALL_SQL, {"kind": kind}).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            payload = _loads(row[0])
            if isinstance(payload, dict):
                out.append(_normalize_owner(payload))
        return out

    def _upsert(self, session: Session, kind: str, record: Dict[str, Any]) -> None:
        record_id = _record_id(kind, record)
        if not record_id:
            raise ValueError(f"Cannot persist {kind} record without an id.")
        normalized = _normalize_owner(record)
        session.execute(
            _UPSERT_SQL,
            {
                "kind": kind,
                "record_id": record_id,
                "owner_user_id": _owner(normalized),
                "project_id": str(normalized.get("project_id") or (record_id if kind == "project" else "")),
                "execution_id": str(normalized.get("execution_id") or ""),
                "status": str(normalized.get("status") or ""),
                "created_at": str(normalized.get("created_at") or ""),
                "updated_at": str(normalized.get("updated_at") or normalized.get("created_at") or ""),
                "payload_json": json.dumps(normalized, sort_keys=True),
            },
        )

    def _delete(self, session: Session, kind: str, record_id: str) -> None:
        session.execute(_DELETE_SQL, {"kind": kind, "record_id": normalize_scope_id(record_id, "")})

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def list_projects(self, *, user_id: str) -> List[Dict[str, Any]]:
        rows = self._records("project")
        if not is_admin_user(user_id):
            rows = [row for row in rows if _owner(row) == user_id]
        rows.sort(key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""), reverse=True)
        return rows

    def create_project(self, *, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._transaction() as session:
            now = _now()
            project = {
                "project_id": uuid.uuid4().hex[:12],
                "title": str(payload.get("title") or "Untitled project").strip()[:200] or "Untitled project",
                "geography": str(payload.get("geography") or "").strip()[:120],
                "project_type": str(payload.get("project_type") or payload.get("model_architecture_id") or "energy-development").strip()[:80],
                "model_architecture_id": str(payload.get("model_architecture_id") or "energy-development").strip()[:80],
                "scenario_label": str(payload.get("scenario_label") or "").strip()[:200],
                "notes": str(payload.get("notes") or "").strip()[:2000],
                "status": "active",
                "owner_user_id": user_id,
                "created_by_user_id": user_id,
                "created_at": now,
                "updated_at": now,
            }
            self._upsert(session, "project", project)
            return project

    def get_project(self, *, user_id: str, project_id: str) -> Dict[str, Any]:
        safe_project_id = _project_id_for_user(project_id, user_id) if not is_admin_user(user_id) else normalize_scope_id(project_id, "")
        project = self._record("project", safe_project_id)
        if project and _can_access_owner(user_id, _owner(project)):
            return project
        raise HTTPException(status_code=404, detail="Project not found.")

    def update_project(self, *, user_id: str, project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._transaction() as session:
            safe_project_id = _project_id_for_user(project_id, user_id) if not is_admin_user(user_id) else normalize_scope_id(project_id, "")
            project = self._record("project", safe_project_id, session=session)
            if not project or not _can_access_owner(user_id, _owner(project)):
                raise HTTPException(status_code=404, detail="Project not found.")
            updated = dict(project)
            for key, limit in {"title": 200, "geography": 120, "project_type": 80, "model_architecture_id": 80, "scenario_label": 200, "notes": 2000, "status": 50}.items():
                if key in payload:
                    updated[key] = str(payload.get(key) or "").strip()[:limit]
            updated["updated_at"] = _now()
            updated["last_updated_by_user_id"] = user_id
            self._upsert(session, "project", updated)
            return updated

    def delete_project(self, *, user_id: str, project_id: str, delete_files: bool = False) -> Dict[str, Any]:
        storage_refs_to_delete: List[Any] = []
        run_ids_to_delete: List[str] = []
        deleted_report_count = 0
        deleted_export_count = 0
        with self._transaction() as session:
            safe_project_id = _project_id_for_user(project_id, user_id) if not is_admin_user(user_id) else normalize_scope_id(project_id, "")
            project = self._record("project", safe_project_id, session=session)
            if not project or not _can_access_owner(user_id, _owner(project)):
                raise HTTPException(status_code=404, detail="Project not found.")
            owner = _owner(project)
            if user_id != owner and not is_admin_user(user_id):
                raise HTTPException(status_code=403, detail="Only the project owner or admin can delete this project.")
            run_rows = [r for r in self._records("run", session=session) if r.get("project_id") == safe_project_id and _owner(r) == owner]
            report_rows = [r for r in self._records("report", session=session) if r.get("project_id") == safe_project_id and _owner(r) == owner]
            export_rows = [r for r in self._records("export", session=session) if r.get("project_id") == safe_project_id and _owner(r) == owner]
            run_ids_to_delete = [str(r.get("run_id") or "") for r in run_rows if r.get("run_id")]
            deleted_report_count = len(report_rows)
            deleted_export_count = len(export_rows)
            for r in report_rows:
                storage_refs_to_delete.extend([r.get("storage_ref"), r.get("source_data_storage_ref")])
            for r in export_rows:
                storage_refs_to_delete.append(r.get("storage_ref"))
            for r in run_rows:
                self._delete(session, "run", str(r.get("run_id") or ""))
            for r in report_rows:
                self._delete(session, "report", str(r.get("report_id") or ""))
            for r in export_rows:
                self._delete(session, "export", str(r.get("export_id") or ""))
            self._delete(session, "project", safe_project_id)
        if delete_files:
            for run_id in run_ids_to_delete:
                run_dir = self._settings.runs_dir / run_id
                if run_dir.exists() and run_dir.is_dir():
                    shutil.rmtree(run_dir)
            for storage_ref in storage_refs_to_delete:
                path = platform_storage_ref_path(self._settings, storage_ref)
                if path is not None and path.exists() and path.is_file():
                    path.unlink()
        return {
            "ok": True,
            "project_id": safe_project_id,
            "deleted_runs": len(run_ids_to_delete),
            "deleted_reports": deleted_report_count,
            "deleted_exports": deleted_export_count,
        }

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    def create_run_record(
        self,
        *,
        project_id: str,
        request_payload: Dict[str, Any],
        run_id: str = "",
        execution_id: str = "",
        status: str,
        dataset_snapshot: Dict[str, Any] | None = None,
        user_id: str,
    ) -> Dict[str, Any]:
        with self._transaction() as session:
            project = self._ensure_project(session, project_id, user_id=user_id)
            now = _now()
            resolved_run_id = normalize_scope_id(run_id, "") if run_id else uuid.uuid4().hex
            existing = self._record("run", resolved_run_id, session=session)
            resolved_project_id = str(project.get("project_id") or normalize_scope_id(project_id, "default"))
            project_run_number = _positive_int((existing or {}).get("project_run_number"))
            if project_run_number <= 0:
                project_run_number = self._next_project_run_number(session, resolved_project_id, exclude_run_id=resolved_run_id)
            record = {
                "run_id": resolved_run_id,
                "execution_id": execution_id,
                "project_id": resolved_project_id,
                "project_run_number": project_run_number,
                "run_name": str(request_payload.get("run_name") or "").strip()[:200],
                "status": status,
                "stage": status,
                "progress": 0.0 if status == "draft" else 0.01,
                "message": "Draft saved." if status == "draft" else "Queued",
                "created_at": str((existing or {}).get("created_at") or now),
                "updated_at": now,
                "started_at": None,
                "finished_at": None,
                "owner_user_id": str((existing or {}).get("owner_user_id") or _owner(project)),
                "created_by_user_id": str((existing or {}).get("created_by_user_id") or user_id),
                "last_updated_by_user_id": user_id,
                "request": request_payload,
                "execution_queue_message": {},
                "execution_attempts": [],
                "cancellation_requested": False,
                "worker_id": "",
                "dataset_snapshot": dataset_snapshot or {},
                "artifact_catalog": [],
                "summary_available": False,
                "source_run_id": str((existing or {}).get("source_run_id") or ""),
            }
            self._upsert(session, "run", record)
            return record

    def update_run_record(self, run_id: str, updates: Dict[str, Any], *, user_id: str) -> Dict[str, Any]:
        with self._transaction() as session:
            safe_run_id = normalize_scope_id(run_id, "")
            record = self._record("run", safe_run_id, session=session)
            if not record or not _can_access_owner(user_id, _owner(record)):
                raise HTTPException(status_code=404, detail="Run record not found.")
            updated = {**record, **updates, "last_updated_by_user_id": user_id, "updated_at": _now()}
            self._upsert(session, "run", updated)
            return updated

    def get_run_record(self, run_id: str, *, user_id: str) -> Dict[str, Any]:
        safe_run_id = normalize_scope_id(run_id, "")
        record = self._record("run", safe_run_id)
        if record and _can_access_owner(user_id, _owner(record)):
            return self._numbered_run_record(record, user_id=user_id)
        raise HTTPException(status_code=404, detail="Run record not found.")

    def get_run_record_by_execution(self, execution_id: str, *, user_id: str) -> Dict[str, Any]:
        safe_exec_id = normalize_scope_id(execution_id, "")
        with self._session_factory() as session:
            row = session.execute(_SELECT_BY_EXEC_SQL, {"execution_id": safe_exec_id}).fetchone()
        record = _loads(row[0]) if row else None
        if record and _can_access_owner(user_id, _owner(record)):
            return self._numbered_run_record(_normalize_owner(record), user_id=user_id)
        raise HTTPException(status_code=404, detail="Run execution not found.")

    def list_run_records(
        self,
        *,
        project_id: str | None,
        user_id: str,
        include_drafts: bool = True,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        records = self._records("run")
        if not is_admin_user(user_id):
            records = [r for r in records if _owner(r) == user_id]
        if project_id:
            safe_project_id = _project_id_for_user(project_id, user_id) if not is_admin_user(user_id) else normalize_scope_id(project_id, "default")
            records = [r for r in records if r.get("project_id") == safe_project_id]
        if not include_drafts:
            records = [r for r in records if r.get("status") != "draft"]
        records = _with_project_run_numbers(records)
        records.sort(key=lambda r: str(r.get("updated_at") or r.get("created_at") or ""), reverse=True)
        return records[: max(1, int(limit))]

    def delete_run_record(self, run_id: str, *, user_id: str, delete_files: bool = False) -> Dict[str, Any]:
        with self._transaction() as session:
            safe_run_id = normalize_scope_id(run_id, "")
            current = self._record("run", safe_run_id, session=session)
            if not current or not _can_access_owner(user_id, _owner(current)):
                raise HTTPException(status_code=404, detail="Run record not found.")
            owner = _owner(current)
            self._delete(session, "run", safe_run_id)
        if delete_files and (user_id == owner or is_admin_user(user_id)):
            run_dir = self._settings.runs_dir / safe_run_id
            if run_dir.exists() and run_dir.is_dir():
                shutil.rmtree(run_dir)
        return {"ok": True, "run_id": safe_run_id}

    def duplicate_run_record(self, run_id: str, *, user_id: str) -> Dict[str, Any]:
        source = self.get_run_record(run_id, user_id=user_id)
        request_payload = dict(source.get("request") or {})
        base_name = str(request_payload.get("run_name") or source.get("run_name") or source.get("run_id") or "Run")
        request_payload["run_name"] = f"{base_name} copy"[:200]
        return self._create_run_record_with_source(
            project_id=str(source.get("project_id") or "default"),
            request_payload=request_payload,
            status="draft",
            dataset_snapshot=dict(source.get("dataset_snapshot") or {}),
            user_id=_owner(source) if is_admin_user(user_id) else user_id,
            source_run_id=str(source.get("run_id") or ""),
        )

    def list_dataset_version_references(self, *, dataset_id: str, version_id: str, user_id: str) -> List[Dict[str, Any]]:
        references: List[Dict[str, Any]] = []
        for record in self.list_run_records(project_id=None, user_id=user_id, include_drafts=True, limit=10000):
            status = str(record.get("status") or "draft").strip().lower()
            if status == "draft":
                continue
            snapshot = record.get("dataset_snapshot") if isinstance(record.get("dataset_snapshot"), dict) else {}
            for row in snapshot.get("datasets") or []:
                if not isinstance(row, dict):
                    continue
                if str(row.get("id") or "") == dataset_id and str(row.get("active_version_id") or "") == version_id:
                    references.append({
                        "run_id": str(record.get("run_id") or ""),
                        "project_id": str(record.get("project_id") or ""),
                        "status": status,
                    })
        return references

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------

    def list_reports(self, *, project_id: str | None, user_id: str) -> List[Dict[str, Any]]:
        rows = self._records("report")
        if not is_admin_user(user_id):
            rows = [r for r in rows if _owner(r) == user_id]
        if project_id:
            safe_project_id = _project_id_for_user(project_id, user_id) if not is_admin_user(user_id) else normalize_scope_id(project_id, "default")
            rows = [r for r in rows if r.get("project_id") == safe_project_id]
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return rows

    def create_report(
        self,
        *,
        project_id: str,
        run_ids: Iterable[str],
        report_type: str,
        options: Dict[str, Any],
        user_id: str,
    ) -> Dict[str, Any]:
        project = self.get_project(user_id=user_id, project_id=project_id)
        owner = _owner(project)
        safe_project_id = str(project.get("project_id") or normalize_scope_id(project_id, "default"))
        selected_run_ids = [normalize_scope_id(run_id, "") for run_id in run_ids if normalize_scope_id(run_id, "")]
        selected_run_ids = self._filter_project_run_ids(selected_run_ids, project_id=safe_project_id, owner_user_id=owner, user_id=user_id)
        if not selected_run_ids:
            selected_run_ids = [
                str(r.get("run_id"))
                for r in self.list_run_records(project_id=safe_project_id, user_id=user_id, include_drafts=False)
                if _owner(r) == owner
            ]
        run_records = [self.get_run_record(run_id, user_id=user_id) for run_id in selected_run_ids]
        summaries = {run_id: self._load_run_summary_for_report(run_id) for run_id in selected_run_ids}
        selected_run_set = set(selected_run_ids)
        export_records = [
            r for r in self.list_exports(project_id=safe_project_id, user_id=user_id)
            if _owner(r) == owner and (not selected_run_ids or selected_run_set.intersection(r.get("run_ids") or []))
        ]
        report_id = uuid.uuid4().hex[:12]
        created_at = _now()
        artifacts = build_report_artifacts(
            settings=self._settings,
            report_id=report_id,
            project=project,
            run_records=run_records,
            summaries=summaries,
            exports=export_records,
            report_type=report_type,
            options=options or {},
            generated_by_user_id=user_id,
            generated_at=created_at,
        )
        source_data = artifacts["source_data"]
        record = {
            "report_id": report_id,
            "project_id": safe_project_id,
            "run_ids": selected_run_ids,
            "report_type": str(report_type or "project_summary"),
            "format": "markdown",
            "source_schema_version": source_data.get("schema_version", ""),
            "status": "succeeded",
            "queued_at": created_at,
            "started_at": created_at,
            "finished_at": created_at,
            "status_history": [
                {"status": "queued", "at": created_at},
                {"status": "running", "at": created_at},
                {"status": "succeeded", "at": created_at},
            ],
            "owner_user_id": owner,
            "created_by_user_id": user_id,
            "created_at": created_at,
            "updated_at": created_at,
            "storage_ref": artifacts["storage_ref"],
            "source_data_storage_ref": artifacts["source_data_storage_ref"],
            "download_url": f"/api/projects/{safe_project_id}/reports/{report_id}/download",
            "source_data_url": f"/api/projects/{safe_project_id}/reports/{report_id}/data",
            "options": options or {},
        }
        with self._transaction() as session:
            self._upsert(session, "report", record)
        return record

    def get_report(self, report_id: str, *, user_id: str) -> Dict[str, Any]:
        safe_report_id = normalize_scope_id(report_id, "")
        record = self._record("report", safe_report_id)
        if record and _can_access_owner(user_id, _owner(record)):
            return record
        raise HTTPException(status_code=404, detail="Report not found.")

    # ------------------------------------------------------------------
    # Exports
    # ------------------------------------------------------------------

    def list_exports(self, *, project_id: str | None, user_id: str) -> List[Dict[str, Any]]:
        rows = self._records("export")
        if not is_admin_user(user_id):
            rows = [r for r in rows if _owner(r) == user_id]
        if project_id:
            safe_project_id = _project_id_for_user(project_id, user_id) if not is_admin_user(user_id) else normalize_scope_id(project_id, "default")
            rows = [r for r in rows if r.get("project_id") == safe_project_id]
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return rows

    def create_project_export(
        self,
        *,
        project_id: str,
        run_ids: Iterable[str] | None,
        include_reports: bool,
        user_id: str,
    ) -> Dict[str, Any]:
        project = self.get_project(user_id=user_id, project_id=project_id)
        owner = _owner(project)
        safe_project_id = str(project.get("project_id") or normalize_scope_id(project_id, "default"))
        selected_run_ids = [normalize_scope_id(run_id, "") for run_id in (run_ids or []) if normalize_scope_id(run_id, "")]
        selected_run_ids = self._filter_project_run_ids(selected_run_ids, project_id=safe_project_id, owner_user_id=owner, user_id=user_id)
        if not selected_run_ids:
            selected_run_ids = [
                str(r.get("run_id"))
                for r in self.list_run_records(project_id=safe_project_id, user_id=user_id, include_drafts=False)
                if _owner(r) == owner
            ]
        run_records = [self.get_run_record(run_id, user_id=user_id) for run_id in selected_run_ids]
        export_id = uuid.uuid4().hex[:12]
        created_at = _now()
        export_artifact = build_project_export_artifact(
            settings=self._settings,
            export_id=export_id,
            project=project,
            run_records=run_records,
            reports=[r for r in self.list_reports(project_id=safe_project_id, user_id=user_id) if _owner(r) == owner],
            owner_user_id=owner,
            created_by_user_id=user_id,
            created_at=created_at,
            include_reports=include_reports,
        )
        record = {
            "export_id": export_id,
            "project_id": safe_project_id,
            "run_ids": selected_run_ids,
            "status": "succeeded",
            "queued_at": created_at,
            "started_at": created_at,
            "finished_at": _now(),
            "owner_user_id": owner,
            "created_by_user_id": user_id,
            "created_at": created_at,
            "updated_at": _now(),
            "storage_ref": export_artifact["storage_ref"],
            "size_bytes": export_artifact["size_bytes"],
            "download_url": f"/api/projects/{safe_project_id}/exports/{export_id}/download",
        }
        with self._transaction() as session:
            self._upsert(session, "export", record)
        return record

    def create_run_export(self, *, run_id: str, user_id: str) -> Dict[str, Any]:
        record = self.get_run_record(run_id, user_id=user_id)
        return self.create_project_export(
            project_id=str(record.get("project_id") or "default"),
            run_ids=[run_id],
            include_reports=False,
            user_id=user_id,
        )

    def get_export(self, export_id: str, *, user_id: str) -> Dict[str, Any]:
        safe_export_id = normalize_scope_id(export_id, "")
        record = self._record("export", safe_export_id)
        if record and _can_access_owner(user_id, _owner(record)):
            return record
        raise HTTPException(status_code=404, detail="Export not found.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_run_record_with_source(self, *, project_id, request_payload, status, dataset_snapshot, user_id, source_run_id) -> Dict[str, Any]:
        record = self.create_run_record(
            project_id=project_id,
            request_payload=request_payload,
            status=status,
            dataset_snapshot=dataset_snapshot,
            user_id=user_id,
        )
        return self.update_run_record(record["run_id"], {"source_run_id": source_run_id}, user_id=user_id)

    def _filter_project_run_ids(self, run_ids, *, project_id, owner_user_id, user_id) -> List[str]:
        out = []
        for run_id in run_ids:
            try:
                record = self.get_run_record(run_id, user_id=user_id)
            except HTTPException:
                continue
            if record.get("project_id") == project_id and _owner(record) == owner_user_id:
                out.append(run_id)
        return out

    def _load_run_summary_for_report(self, run_id: str) -> Dict[str, Any]:
        return load_run_summary_for_report(self._settings, run_id)

    def _ensure_project(self, session: Session, project_id: str = "default", *, user_id: str = LOCAL_USER_ID) -> Dict[str, Any]:
        safe_project_id = _project_id_for_user(project_id, user_id)
        project = self._record("project", safe_project_id, session=session)
        if project and _can_access_owner(user_id, _owner(project)):
            return project
        now = _now()
        project = {
            "project_id": safe_project_id,
            "title": "Default project" if normalize_scope_id(project_id, "default") == "default" else safe_project_id,
            "geography": "",
            "project_type": "energy-development",
            "model_architecture_id": "energy-development",
            "scenario_label": "",
            "notes": "",
            "status": "active",
            "owner_user_id": user_id,
            "created_by_user_id": user_id,
            "created_at": now,
            "updated_at": now,
        }
        self._upsert(session, "project", project)
        return project

    def _next_project_run_number(self, session: Session, project_id: str, *, exclude_run_id: str = "") -> int:
        rows = [
            r for r in self._records("run", session=session)
            if str(r.get("project_id") or "") == project_id and str(r.get("run_id") or "") != exclude_run_id
        ]
        explicit = [_positive_int(r.get("project_run_number")) for r in rows]
        explicit = [v for v in explicit if v > 0]
        return max([len(rows), *explicit], default=0) + 1

    def _numbered_run_record(self, record: Dict[str, Any], *, user_id: str) -> Dict[str, Any]:
        if _positive_int(record.get("project_run_number")) > 0:
            return record
        project_id = str(record.get("project_id") or "")
        if not project_id:
            return record
        rows = self.list_run_records(project_id=project_id, user_id=user_id, include_drafts=True, limit=10000)
        for row in rows:
            if row.get("run_id") == record.get("run_id"):
                return row
        return record


# ---------------------------------------------------------------------------
# Module-level helpers (identical to sqlite_platform_repository.py)
# ---------------------------------------------------------------------------

def _record_id(kind: str, record: Dict[str, Any]) -> str:
    key = {"project": "project_id", "run": "run_id", "report": "report_id", "export": "export_id"}.get(kind, "")
    return normalize_scope_id(str(record.get(key) or ""), "")


def _default_project_id(user_id: str) -> str:
    return f"default_{normalize_scope_id(user_id, LOCAL_USER_ID)}"


def _project_id_for_user(project_id: str | None, user_id: str) -> str:
    safe = normalize_scope_id(project_id, "default")
    return _default_project_id(user_id) if safe == "default" else safe


def _normalize_owner(record: Dict[str, Any]) -> Dict[str, Any]:
    owner = normalize_scope_id(str(record.get("owner_user_id") or record.get("created_by_user_id") or LOCAL_USER_ID), LOCAL_USER_ID)
    out = dict(record)
    out["owner_user_id"] = owner
    out["created_by_user_id"] = normalize_scope_id(str(record.get("created_by_user_id") or owner), owner)
    return out


def _positive_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _with_project_run_numbers(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_project: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        by_project.setdefault(str(record.get("project_id") or ""), []).append(record)
    numbered_by_id: Dict[str, Dict[str, Any]] = {}
    for rows in by_project.values():
        used = {_positive_int(r.get("project_run_number")) for r in rows}
        used.discard(0)
        next_number = 1
        for r in sorted(rows, key=lambda item: (str(item.get("created_at") or ""), str(item.get("run_id") or ""))):
            out = dict(r)
            current = _positive_int(out.get("project_run_number"))
            if current <= 0:
                while next_number in used:
                    next_number += 1
                current = next_number
                used.add(current)
            out["project_run_number"] = current
            numbered_by_id[str(out.get("run_id") or id(r))] = out
    return [numbered_by_id.get(str(r.get("run_id") or id(r)), r) for r in records]


def _owner(record: Dict[str, Any]) -> str:
    return normalize_scope_id(str(record.get("owner_user_id") or record.get("created_by_user_id") or LOCAL_USER_ID), LOCAL_USER_ID)


def _can_access_owner(user_id: str, owner_user_id: str) -> bool:
    return user_id == owner_user_id or is_admin_user(user_id)


def _loads(raw: str) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
