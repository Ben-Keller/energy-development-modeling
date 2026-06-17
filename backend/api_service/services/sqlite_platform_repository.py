"""SQLite-backed platform metadata repository.

This is the local transactional reference implementation for backend handoff.
It keeps large artifacts on the filesystem through the existing artifact
storage boundary, while storing project/run/report/export metadata in SQLite.
Azure deployments can replace this class with SQL/Cosmos-backed persistence
without changing API routers or model runtime code.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List

from fastapi import HTTPException

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
SQLITE_SCHEMA_VERSION = "edim_platform_sqlite_v1"


def sqlite_platform_path(settings: Settings) -> Path:
    configured = getattr(settings, "platform_sqlite_path", None)
    if configured:
        return Path(configured).expanduser().resolve()
    return (settings.runs_dir.parent / "platform" / "platform.sqlite3").resolve()


class SQLitePlatformRepository:
    """Transactional local repository for platform metadata.

    Records are stored as JSON payloads plus indexed columns. This keeps the
    repository tolerant of evolving API payloads while still providing the
    database semantics needed for cloud migration: transactions, indexed owner
    isolation, restart-safe run history, and a single replaceable persistence
    boundary.
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._db_path = sqlite_platform_path(settings)
        self._lock = threading.RLock()
        self._initialize()

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def db_path(self) -> Path:
        return self._db_path

    def list_projects(self, *, user_id: str) -> List[Dict[str, Any]]:
        rows = self._records("project")
        if not is_admin_user(user_id):
            rows = [row for row in rows if _owner(row) == user_id]
        rows.sort(key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""), reverse=True)
        return rows

    def create_project(self, *, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._transaction() as conn:
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
            self._upsert(conn, "project", project)
            return project

    def get_project(self, *, user_id: str, project_id: str) -> Dict[str, Any]:
        safe_project_id = _project_id_for_user(project_id, user_id) if not is_admin_user(user_id) else normalize_scope_id(project_id, "")
        project = self._record("project", safe_project_id)
        if project and _can_access_owner(user_id, _owner(project)):
            return project
        raise HTTPException(status_code=404, detail="Project not found.")

    def update_project(self, *, user_id: str, project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._transaction() as conn:
            safe_project_id = _project_id_for_user(project_id, user_id) if not is_admin_user(user_id) else normalize_scope_id(project_id, "")
            project = self._record("project", safe_project_id, conn=conn)
            if not project or not _can_access_owner(user_id, _owner(project)):
                raise HTTPException(status_code=404, detail="Project not found.")
            updated = dict(project)
            for key, limit in {"title": 200, "geography": 120, "project_type": 80, "model_architecture_id": 80, "scenario_label": 200, "notes": 2000, "status": 50}.items():
                if key in payload:
                    updated[key] = str(payload.get(key) or "").strip()[:limit]
            updated["updated_at"] = _now()
            updated["last_updated_by_user_id"] = user_id
            self._upsert(conn, "project", updated)
            return updated

    def delete_project(self, *, user_id: str, project_id: str, delete_files: bool = False) -> Dict[str, Any]:
        storage_refs_to_delete: List[Any] = []
        run_ids_to_delete: List[str] = []
        deleted_report_count = 0
        deleted_export_count = 0
        with self._transaction() as conn:
            safe_project_id = _project_id_for_user(project_id, user_id) if not is_admin_user(user_id) else normalize_scope_id(project_id, "")
            project = self._record("project", safe_project_id, conn=conn)
            if not project or not _can_access_owner(user_id, _owner(project)):
                raise HTTPException(status_code=404, detail="Project not found.")
            owner = _owner(project)
            if user_id != owner and not is_admin_user(user_id):
                raise HTTPException(status_code=403, detail="Only the project owner or admin can delete this project.")
            run_rows = [
                row
                for row in self._records("run", conn=conn)
                if row.get("project_id") == safe_project_id and _owner(row) == owner
            ]
            report_rows = [
                row
                for row in self._records("report", conn=conn)
                if row.get("project_id") == safe_project_id and _owner(row) == owner
            ]
            export_rows = [
                row
                for row in self._records("export", conn=conn)
                if row.get("project_id") == safe_project_id and _owner(row) == owner
            ]
            run_ids_to_delete = [str(row.get("run_id") or "") for row in run_rows if row.get("run_id")]
            deleted_report_count = len(report_rows)
            deleted_export_count = len(export_rows)
            for row in report_rows:
                storage_refs_to_delete.extend([row.get("storage_ref"), row.get("source_data_storage_ref")])
            for row in export_rows:
                storage_refs_to_delete.append(row.get("storage_ref"))
            for row in run_rows:
                self._delete(conn, "run", str(row.get("run_id") or ""))
            for row in report_rows:
                self._delete(conn, "report", str(row.get("report_id") or ""))
            for row in export_rows:
                self._delete(conn, "export", str(row.get("export_id") or ""))
            self._delete(conn, "project", safe_project_id)
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
        with self._transaction() as conn:
            project = self._ensure_project(conn, project_id, user_id=user_id)
            now = _now()
            resolved_run_id = normalize_scope_id(run_id, "") if run_id else uuid.uuid4().hex
            existing = self._record("run", resolved_run_id, conn=conn)
            resolved_project_id = str(project.get("project_id") or normalize_scope_id(project_id, "default"))
            project_run_number = _positive_int((existing or {}).get("project_run_number"))
            if project_run_number <= 0:
                project_run_number = self._next_project_run_number(conn, resolved_project_id, exclude_run_id=resolved_run_id)
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
            self._upsert(conn, "run", record)
            return record

    def update_run_record(self, run_id: str, updates: Dict[str, Any], *, user_id: str) -> Dict[str, Any]:
        with self._transaction() as conn:
            safe_run_id = normalize_scope_id(run_id, "")
            record = self._record("run", safe_run_id, conn=conn)
            if not record or not _can_access_owner(user_id, _owner(record)):
                raise HTTPException(status_code=404, detail="Run record not found.")
            updated = {**record, **updates, "last_updated_by_user_id": user_id, "updated_at": _now()}
            self._upsert(conn, "run", updated)
            return updated

    def get_run_record(self, run_id: str, *, user_id: str) -> Dict[str, Any]:
        safe_run_id = normalize_scope_id(run_id, "")
        record = self._record("run", safe_run_id)
        if record and _can_access_owner(user_id, _owner(record)):
            return self._numbered_run_record(record, user_id=user_id)
        raise HTTPException(status_code=404, detail="Run record not found.")

    def get_run_record_by_execution(self, execution_id: str, *, user_id: str) -> Dict[str, Any]:
        safe_execution_id = normalize_scope_id(execution_id, "")
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json
                FROM platform_records
                WHERE kind = 'run' AND execution_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (safe_execution_id,),
            ).fetchone()
        record = _loads(row["payload_json"]) if row else None
        if record and _can_access_owner(user_id, _owner(record)):
            return self._numbered_run_record(_normalize_owner(record), user_id=user_id)
        raise HTTPException(status_code=404, detail="Run execution not found.")

    def _next_project_run_number(self, conn: sqlite3.Connection, project_id: str, *, exclude_run_id: str = "") -> int:
        rows = [
            row
            for row in self._records("run", conn=conn)
            if str(row.get("project_id") or "") == project_id and str(row.get("run_id") or "") != exclude_run_id
        ]
        explicit = [_positive_int(row.get("project_run_number")) for row in rows]
        explicit = [value for value in explicit if value > 0]
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
            records = [row for row in records if _owner(row) == user_id]
        if project_id:
            safe_project_id = _project_id_for_user(project_id, user_id) if not is_admin_user(user_id) else normalize_scope_id(project_id, "default")
            records = [row for row in records if row.get("project_id") == safe_project_id]
        if not include_drafts:
            records = [row for row in records if row.get("status") != "draft"]
        records = _with_project_run_numbers(records)
        records.sort(key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""), reverse=True)
        return records[: max(1, int(limit))]

    def delete_run_record(self, run_id: str, *, user_id: str, delete_files: bool = False) -> Dict[str, Any]:
        with self._transaction() as conn:
            safe_run_id = normalize_scope_id(run_id, "")
            current = self._record("run", safe_run_id, conn=conn)
            if not current or not _can_access_owner(user_id, _owner(current)):
                raise HTTPException(status_code=404, detail="Run record not found.")
            owner = _owner(current)
            self._delete(conn, "run", safe_run_id)
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
                    references.append(
                        {
                            "run_id": str(record.get("run_id") or ""),
                            "project_id": str(record.get("project_id") or ""),
                            "status": status,
                        }
                    )
        return references

    def list_reports(self, *, project_id: str | None, user_id: str) -> List[Dict[str, Any]]:
        rows = self._records("report")
        if not is_admin_user(user_id):
            rows = [row for row in rows if _owner(row) == user_id]
        if project_id:
            safe_project_id = _project_id_for_user(project_id, user_id) if not is_admin_user(user_id) else normalize_scope_id(project_id, "default")
            rows = [row for row in rows if row.get("project_id") == safe_project_id]
        rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
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
        with self._lock:
            project = self.get_project(user_id=user_id, project_id=project_id)
            owner = _owner(project)
            safe_project_id = str(project.get("project_id") or normalize_scope_id(project_id, "default"))
            selected_run_ids = [normalize_scope_id(run_id, "") for run_id in run_ids if normalize_scope_id(run_id, "")]
            selected_run_ids = self._filter_project_run_ids(selected_run_ids, project_id=safe_project_id, owner_user_id=owner, user_id=user_id)
            if not selected_run_ids:
                selected_run_ids = [
                    str(row.get("run_id"))
                    for row in self.list_run_records(project_id=safe_project_id, user_id=user_id, include_drafts=False)
                    if _owner(row) == owner
                ]
            run_records = [self.get_run_record(run_id, user_id=user_id) for run_id in selected_run_ids]
            summaries = {run_id: self._load_run_summary_for_report(run_id) for run_id in selected_run_ids}
            selected_run_set = set(selected_run_ids)
            export_records = [
                row
                for row in self.list_exports(project_id=safe_project_id, user_id=user_id)
                if _owner(row) == owner and (not selected_run_ids or selected_run_set.intersection(row.get("run_ids") or []))
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
            with self._transaction() as conn:
                self._upsert(conn, "report", record)
            return record

    def get_report(self, report_id: str, *, user_id: str) -> Dict[str, Any]:
        safe_report_id = normalize_scope_id(report_id, "")
        record = self._record("report", safe_report_id)
        if record and _can_access_owner(user_id, _owner(record)):
            return record
        raise HTTPException(status_code=404, detail="Report not found.")

    def list_exports(self, *, project_id: str | None, user_id: str) -> List[Dict[str, Any]]:
        rows = self._records("export")
        if not is_admin_user(user_id):
            rows = [row for row in rows if _owner(row) == user_id]
        if project_id:
            safe_project_id = _project_id_for_user(project_id, user_id) if not is_admin_user(user_id) else normalize_scope_id(project_id, "default")
            rows = [row for row in rows if row.get("project_id") == safe_project_id]
        rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
        return rows

    def create_project_export(
        self,
        *,
        project_id: str,
        run_ids: Iterable[str] | None,
        include_reports: bool,
        user_id: str,
    ) -> Dict[str, Any]:
        with self._lock:
            project = self.get_project(user_id=user_id, project_id=project_id)
            owner = _owner(project)
            safe_project_id = str(project.get("project_id") or normalize_scope_id(project_id, "default"))
            selected_run_ids = [normalize_scope_id(run_id, "") for run_id in (run_ids or []) if normalize_scope_id(run_id, "")]
            selected_run_ids = self._filter_project_run_ids(selected_run_ids, project_id=safe_project_id, owner_user_id=owner, user_id=user_id)
            if not selected_run_ids:
                selected_run_ids = [
                    str(row.get("run_id"))
                    for row in self.list_run_records(project_id=safe_project_id, user_id=user_id, include_drafts=False)
                    if _owner(row) == owner
                ]
            run_records = [self.get_run_record(run_id, user_id=user_id) for run_id in selected_run_ids]
            export_id = uuid.uuid4().hex[:12]
            created_at = _now()
            export_artifact = build_project_export_artifact(
                settings=self._settings,
                export_id=export_id,
                project=project,
                run_records=run_records,
                reports=[report for report in self.list_reports(project_id=safe_project_id, user_id=user_id) if _owner(report) == owner],
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
            with self._transaction() as conn:
                self._upsert(conn, "export", record)
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

    def _create_run_record_with_source(
        self,
        *,
        project_id: str,
        request_payload: Dict[str, Any],
        status: str,
        dataset_snapshot: Dict[str, Any],
        user_id: str,
        source_run_id: str,
    ) -> Dict[str, Any]:
        record = self.create_run_record(
            project_id=project_id,
            request_payload=request_payload,
            status=status,
            dataset_snapshot=dataset_snapshot,
            user_id=user_id,
        )
        return self.update_run_record(record["run_id"], {"source_run_id": source_run_id}, user_id=user_id)

    def _filter_project_run_ids(self, run_ids: List[str], *, project_id: str, owner_user_id: str, user_id: str) -> List[str]:
        out: List[str] = []
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

    def _ensure_project(self, conn: sqlite3.Connection, project_id: str = "default", *, user_id: str = LOCAL_USER_ID) -> Dict[str, Any]:
        safe_project_id = _project_id_for_user(project_id, user_id)
        project = self._record("project", safe_project_id, conn=conn)
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
        self._upsert(conn, "project", project)
        return project

    def _initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS platform_records (
                    kind TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    owner_user_id TEXT NOT NULL,
                    project_id TEXT NOT NULL DEFAULT '',
                    execution_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (kind, record_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS platform_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_platform_records_owner_kind ON platform_records(owner_user_id, kind)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_platform_records_project_kind ON platform_records(project_id, kind)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_platform_records_execution ON platform_records(execution_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_platform_records_status_kind ON platform_records(status, kind)")
            conn.execute(
                """
                INSERT INTO platform_metadata(key, value)
                VALUES ('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (SQLITE_SCHEMA_VERSION,),
            )

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _record(self, kind: str, record_id: str, *, conn: sqlite3.Connection | None = None) -> Dict[str, Any] | None:
        safe_id = normalize_scope_id(record_id, "")
        if not safe_id:
            return None
        close = False
        if conn is None:
            conn = self._connect()
            close = True
        try:
            row = conn.execute(
                "SELECT payload_json FROM platform_records WHERE kind = ? AND record_id = ?",
                (kind, safe_id),
            ).fetchone()
        finally:
            if close:
                conn.close()
        if not row:
            return None
        payload = _loads(row["payload_json"])
        return _normalize_owner(payload) if isinstance(payload, dict) else None

    def _records(self, kind: str, *, conn: sqlite3.Connection | None = None) -> List[Dict[str, Any]]:
        close = False
        if conn is None:
            conn = self._connect()
            close = True
        try:
            rows = conn.execute(
                "SELECT payload_json FROM platform_records WHERE kind = ? ORDER BY updated_at DESC",
                (kind,),
            ).fetchall()
        finally:
            if close:
                conn.close()
        out: List[Dict[str, Any]] = []
        for row in rows:
            payload = _loads(row["payload_json"])
            if isinstance(payload, dict):
                out.append(_normalize_owner(payload))
        return out

    def _upsert(self, conn: sqlite3.Connection, kind: str, record: Dict[str, Any]) -> None:
        record_id = _record_id(kind, record)
        if not record_id:
            raise ValueError(f"Cannot persist {kind} record without an id.")
        normalized = _normalize_owner(record)
        payload_json = json.dumps(normalized, indent=None, sort_keys=True)
        conn.execute(
            """
            INSERT INTO platform_records(
                kind,
                record_id,
                owner_user_id,
                project_id,
                execution_id,
                status,
                created_at,
                updated_at,
                payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(kind, record_id) DO UPDATE SET
                owner_user_id = excluded.owner_user_id,
                project_id = excluded.project_id,
                execution_id = excluded.execution_id,
                status = excluded.status,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at,
                payload_json = excluded.payload_json
            """,
            (
                kind,
                record_id,
                _owner(normalized),
                str(normalized.get("project_id") or (record_id if kind == "project" else "")),
                str(normalized.get("execution_id") or ""),
                str(normalized.get("status") or ""),
                str(normalized.get("created_at") or ""),
                str(normalized.get("updated_at") or normalized.get("created_at") or ""),
                payload_json,
            ),
        )

    def _delete(self, conn: sqlite3.Connection, kind: str, record_id: str) -> None:
        conn.execute(
            "DELETE FROM platform_records WHERE kind = ? AND record_id = ?",
            (kind, normalize_scope_id(record_id, "")),
        )

def _record_id(kind: str, record: Dict[str, Any]) -> str:
    key = {
        "project": "project_id",
        "run": "run_id",
        "report": "report_id",
        "export": "export_id",
    }.get(kind, "")
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
        used = {_positive_int(row.get("project_run_number")) for row in rows}
        used.discard(0)
        next_number = 1
        for row in sorted(rows, key=lambda item: (str(item.get("created_at") or ""), str(item.get("run_id") or ""))):
            out = dict(row)
            current = _positive_int(out.get("project_run_number"))
            if current <= 0:
                while next_number in used:
                    next_number += 1
                current = next_number
                used.add(current)
            out["project_run_number"] = current
            numbered_by_id[str(out.get("run_id") or id(row))] = out

    return [numbered_by_id.get(str(row.get("run_id") or id(row)), row) for row in records]


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
