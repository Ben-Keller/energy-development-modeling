from __future__ import annotations

from typing import Any, Dict, Iterable, List, Protocol

from ..runtime import RunRepository
from ..settings import Settings


class PlatformRepository(RunRepository, Protocol):
    """Persistence boundary for platform metadata.

    Cloud deployments should replace this interface with a transactional
    database-backed implementation while preserving method semantics.
    """

    def list_projects(self, *, user_id: str) -> List[Dict[str, Any]]: ...
    def create_project(self, *, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]: ...
    def get_project(self, *, user_id: str, project_id: str) -> Dict[str, Any]: ...
    def update_project(self, *, user_id: str, project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]: ...
    def delete_project(self, *, user_id: str, project_id: str, delete_files: bool = False) -> Dict[str, Any]: ...

    def get_run_record(self, run_id: str, *, user_id: str) -> Dict[str, Any]: ...
    def get_run_record_by_execution(self, execution_id: str, *, user_id: str) -> Dict[str, Any]: ...
    def list_run_records(self, *, project_id: str | None, user_id: str, include_drafts: bool = True, limit: int = 200) -> List[Dict[str, Any]]: ...
    def delete_run_record(self, run_id: str, *, user_id: str, delete_files: bool = False) -> Dict[str, Any]: ...
    def duplicate_run_record(self, run_id: str, *, user_id: str) -> Dict[str, Any]: ...
    def list_dataset_version_references(self, *, dataset_id: str, version_id: str, user_id: str) -> List[Dict[str, Any]]: ...

    def list_reports(self, *, project_id: str | None, user_id: str) -> List[Dict[str, Any]]: ...
    def create_report(self, *, project_id: str, run_ids: Iterable[str], report_type: str, options: Dict[str, Any], user_id: str) -> Dict[str, Any]: ...
    def get_report(self, report_id: str, *, user_id: str) -> Dict[str, Any]: ...

    def list_exports(self, *, project_id: str | None, user_id: str) -> List[Dict[str, Any]]: ...
    def create_project_export(self, *, project_id: str, run_ids: Iterable[str] | None, include_reports: bool, user_id: str) -> Dict[str, Any]: ...
    def create_run_export(self, *, run_id: str, user_id: str) -> Dict[str, Any]: ...
    def get_export(self, export_id: str, *, user_id: str) -> Dict[str, Any]: ...


def create_platform_repository(settings: Settings) -> PlatformRepository:
    """Create the platform metadata repository.

    Uses PostgresPlatformRepository when EDIM_DATABASE_URL is set (docker-compose-dev
    and cloud deployments). Falls back to SQLitePlatformRepository for bare-metal dev.
    """
    import os

    database_url = os.getenv("EDIM_DATABASE_URL", "").strip()
    if database_url:
        from ..db import build_engine, build_session_factory
        from .postgres_platform_repository import PostgresPlatformRepository

        engine = build_engine()
        session_factory = build_session_factory(engine)
        return PostgresPlatformRepository(session_factory, settings)  # type: ignore[return-value]

    backend = str(getattr(settings, "platform_store_backend", "sqlite") or "sqlite").strip().lower()
    if backend not in {"sqlite", "sqlite3"}:
        raise ValueError("platform_store_backend must be 'sqlite'.")
    from .sqlite_platform_repository import SQLitePlatformRepository

    return SQLitePlatformRepository(settings)  # type: ignore[return-value]
