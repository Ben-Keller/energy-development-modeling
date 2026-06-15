"""System manifest endpoint (plan 10.3, 3.4).

Reports:
  - ok: True if all migration + diagnostics pass
  - schema_version: the migration head (alembic_version table)
  - public_endpoints: list of routes the frontend should probe
  - diagnostics: per-check status (DB reachable, required tables exist, etc.)
  - runtime: environment marker, auth mode, queue provider, storage provider

The contract is part of the platform/frontend handshake (plan 10.3.1).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Request
from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])


REQUIRED_TABLES = {
    "users",
    "projects",
    "project_runs",
    "execution_attempts",
    "dataset_version_metadata",
    "dataset_version_pointers",
    "project_runs_dataset_versions",
    "reports",
    "exports",
    "execution_events",
}


def _alembic_config() -> Config:
    from pathlib import Path

    # File: backend/api_service/routes/manifest.py
    # parents[0] = routes/, parents[1] = api_service/, parents[2] = backend/
    backend_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "migrations"))
    cfg.set_main_option("sqlalchemy.url", os.getenv("EDIM_DATABASE_URL", ""))
    return cfg


def _migration_diagnostics(engine) -> dict:
    try:
        script = ScriptDirectory.from_config(_alembic_config())
        head = script.get_heads()[0] if script.get_heads() else None
    except Exception as exc:
        return {"error": f"alembic script load failed: {exc}", "head": None, "current": None, "ok": False}

    current: str | None = None
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            current = ctx.get_current_revision()
    except Exception as exc:
        return {
            "head": head,
            "current": None,
            "ok": False,
            "error": f"alembic_version table missing or unreadable: {exc}",
        }

    return {
        "head": head,
        "current": current,
        "ok": bool(current) and (current == head),
        "pending": [] if (not current or current == head) else [head],
    }


def _table_diagnostics(engine) -> dict:
    try:
        inspector = inspect(engine)
        present = set(inspector.get_table_names())
    except Exception as exc:
        return {"ok": False, "error": f"inspect failed: {exc}", "missing": list(REQUIRED_TABLES)}
    missing = REQUIRED_TABLES - present
    return {
        "ok": not missing,
        "present": sorted(present & REQUIRED_TABLES),
        "missing": sorted(missing),
    }


def _build_endpoints() -> list[dict]:
    """List of public endpoints the frontend expects (plan 10.4)."""
    return [
        {"method": "GET",  "path": "/api/system/manifest"},
        # session
        {"method": "GET",  "path": "/api/session"},
        # scenarios + preflight
        {"method": "GET",  "path": "/api/scenarios"},
        {"method": "GET",  "path": "/api/environment-setup"},
        {"method": "GET",  "path": "/api/model-runtimes"},
        # input datasets
        {"method": "GET",  "path": "/api/input-datasets"},
        {"method": "GET",  "path": "/api/input-datasets/{dataset_id}/download"},
        {"method": "POST", "path": "/api/input-datasets/{dataset_id}/upload"},
        # projects
        {"method": "POST", "path": "/api/projects"},
        {"method": "GET",  "path": "/api/projects"},
        {"method": "GET",  "path": "/api/projects/{project_id}"},
        # project runs
        {"method": "POST", "path": "/api/projects/{project_id}/runs"},
        {"method": "GET",  "path": "/api/projects/{project_id}/runs"},
        {"method": "POST", "path": "/api/projects/{project_id}/runs/validate"},
        {"method": "POST", "path": "/api/projects/{project_id}/runs/{run_id}/submit"},
        # legacy job endpoints
        {"method": "GET",  "path": "/api/jobs"},
        {"method": "POST", "path": "/api/jobs"},
        {"method": "GET",  "path": "/api/jobs/{job_id}"},
        {"method": "POST", "path": "/api/jobs/{job_id}/cancel"},
        {"method": "POST", "path": "/api/jobs/cancel-all"},
        # execution status + events
        {"method": "GET",  "path": "/api/executions/{execution_id}/status"},
        {"method": "GET",  "path": "/api/executions/{execution_id}/events"},
        # run results + artifacts
        {"method": "GET",  "path": "/api/runs/{run_id}/artifacts"},
        {"method": "GET",  "path": "/api/run/{run_id}/summary"},
        {"method": "GET",  "path": "/api/run/{run_id}/integrated"},
        {"method": "GET",  "path": "/api/run/{run_id}/development"},
        {"method": "GET",  "path": "/api/run/{run_id}/download/csv"},
        {"method": "GET",  "path": "/api/run/{run_id}/download/artifact/{path}"},
        {"method": "GET",  "path": "/api/run/{run_id}/download/exchange/{path}"},
        {"method": "GET",  "path": "/api/run/{run_id}/download/report"},
        {"method": "GET",  "path": "/api/run/{run_id}/download/exchange_bundle"},
        # AI
        {"method": "POST", "path": "/api/ai/scenario-query"},
    ]


@router.get("/api/system/manifest")
def get_system_manifest(request: Request) -> dict[str, Any]:
    engine = getattr(request.app.state, "db_engine", None)
    diagnostics: dict[str, Any] = {"checks": []}
    overall_ok = True

    if engine is None:
        diagnostics["checks"].append({
            "name": "database_engine",
            "status": "fail",
            "message": "db_engine is not configured on app.state",
        })
        overall_ok = False
    else:
        # DB reachability check.
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            diagnostics["checks"].append({
                "name": "database_reachable",
                "status": "ok",
                "message": "PostgreSQL connection successful.",
            })
        except Exception as exc:
            diagnostics["checks"].append({
                "name": "database_reachable",
                "status": "fail",
                "message": str(exc),
            })
            overall_ok = False

        if overall_ok:
            mig = _migration_diagnostics(engine)
            tbl = _table_diagnostics(engine)
            diagnostics["migration"] = mig
            diagnostics["tables"] = tbl
            diagnostics["checks"].append({
                "name": "alembic_migration",
                "status": "ok" if mig.get("ok") else "fail",
                "message": f"head={mig.get('head')} current={mig.get('current')}",
            })
            diagnostics["checks"].append({
                "name": "required_tables",
                "status": "ok" if tbl.get("ok") else "fail",
                "message": f"present={len(tbl.get('present', []))}/{len(REQUIRED_TABLES)}",
            })
            overall_ok = overall_ok and mig.get("ok", False) and tbl.get("ok", False)

    auth_mode = os.getenv("EDIM_AUTH_MODE", "test_header")
    queue_mode = os.getenv("EDIM_QUEUE_MODE", "postgres")
    storage_mode = os.getenv("EDIM_STORAGE_MODE", "local")

    return {
        "schema_version": "edim_system_manifest_v1",
        "ok": overall_ok,
        "runtime": {
            "auth_mode": auth_mode,
            "queue_mode": queue_mode,
            "storage_mode": storage_mode,
            "deploy_target": os.getenv("EDIM_DEPLOY_TARGET", "local"),
            "artifact_handoff_mode": storage_mode,
            "dataset_staging_mode": "reference",
        },
        "endpoints": _build_endpoints(),
        "diagnostics": diagnostics,
    }
