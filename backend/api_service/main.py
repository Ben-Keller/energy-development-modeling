from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .integrated import build_integrated_results, validate_integrated_results
from .scenarios import build_scenario_list
from .settings import get_settings
from .jobs import JobManager, JobQueueFullError
from .runner import build_environment_setup_report
from .schemas import (
    JobInfo,
    JobListResponse,
    JobSubmitResponse,
    RunRequest,
)

logger = logging.getLogger(__name__)
RUN_ID_PATTERN = re.compile(r"^[a-f0-9]{8}$")

app = FastAPI(title="EDIM Calliope-Africa API", version="0.1.0")
settings = get_settings()
job_manager = JobManager(settings, use_subprocess=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _discover_frontend_dir() -> Path | None:
    env_dir = (os.getenv("EDIM_FRONTEND_DIR") or "").strip()
    if env_dir:
        path = Path(env_dir).expanduser().resolve()
        if path.exists() and path.is_dir():
            return path

    candidates = [
        Path("/app/frontend"),  # Docker runtime mount
        Path(__file__).resolve().parents[2] / "frontend",  # local repo root
    ]
    for path in candidates:
        if path.exists() and path.is_dir():
            return path
    return None

FRONTEND_DIR = _discover_frontend_dir()
if FRONTEND_DIR is not None:
    app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="ui")
else:
    logger.warning("Frontend directory not found; UI routes disabled.")

def _read_summary_json(path):
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        logger.exception("Failed reading run summary at %s", path)
        raise HTTPException(status_code=500, detail="Could not read run summary.")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in run summary at %s (possibly mid-write)", path)
        raise HTTPException(status_code=503, detail="Run summary is not ready yet. Please retry.")

def _resolve_run_file_path(run_id: str, filename: str):
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id format.")
    candidate = (settings.runs_dir / run_id / filename).resolve()
    runs_root = settings.runs_dir.resolve()
    if runs_root not in candidate.parents:
        raise HTTPException(status_code=400, detail="Invalid run_id path.")
    return candidate

def _require_calliope_model_yaml() -> None:
    model_path = settings.calliope_root / "model.yaml"
    if not model_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Missing Calliope-Africa model.yaml at {model_path}",
        )

@app.get("/", include_in_schema=False)
def root():
    if FRONTEND_DIR is not None:
        return RedirectResponse(url="/ui/", status_code=307)
    return {"ok": True, "message": "UI not available. Set EDIM_FRONTEND_DIR or add ./frontend."}

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/api/scenarios")
def list_scenarios():
    overrides_path = settings.calliope_root / "overrides.yaml"
    metadata_path = settings.config_dir / "scenario_metadata.csv"
    if not overrides_path.exists():
        raise HTTPException(status_code=400, detail=f"Missing Calliope-Africa overrides.yaml at {overrides_path}")
    scenarios = build_scenario_list(overrides_path, metadata_path)
    return {"scenarios": [s.model_dump() for s in scenarios]}


@app.get("/api/environment-setup")
def get_environment_setup(scenario: str = "", run_profile: str = "dev"):
    queue_stats = job_manager.runtime_stats()
    return build_environment_setup_report(
        settings=settings,
        queue_stats=queue_stats,
        scenario=scenario,
        run_profile=run_profile,
    )


@app.get("/api/preflight", include_in_schema=False)
def get_preflight_compat(scenario: str = "", run_profile: str = "dev"):
    return get_environment_setup(scenario=scenario, run_profile=run_profile)


@app.post("/api/jobs", response_model=JobSubmitResponse)
def submit_job(req: RunRequest):
    _require_calliope_model_yaml()
    try:
        job = job_manager.submit(req)
    except JobQueueFullError as e:
        raise HTTPException(status_code=429, detail=str(e))
    return JobSubmitResponse(job=job)


@app.get("/api/jobs", response_model=JobListResponse)
def list_jobs(limit: int = 50):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")
    return JobListResponse(jobs=job_manager.list(limit=limit))


@app.get("/api/jobs/{job_id}", response_model=JobInfo)
def get_job(job_id: str):
    try:
        return job_manager.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found")


@app.post("/api/jobs/{job_id}/cancel", response_model=JobInfo)
def cancel_job(job_id: str):
    try:
        return job_manager.cancel(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found")

@app.get("/api/run/{run_id}/summary")
def get_summary(run_id: str):
    path = _resolve_run_file_path(run_id, "summary.json")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Run summary not found")
    return _read_summary_json(path)


@app.get("/api/run/{run_id}/development")
def get_development_impacts(run_id: str):
    path = _resolve_run_file_path(run_id, "development_impacts.json")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Development impacts not found")
    return _read_summary_json(path)


@app.get("/api/run/{run_id}/integrated")
def get_integrated_results(run_id: str):
    integrated_path = _resolve_run_file_path(run_id, "integrated_results.json")
    if integrated_path.exists():
        integrated = _read_summary_json(integrated_path)
        try:
            return validate_integrated_results(integrated)
        except ValueError:
            logger.exception("Integrated payload validation failed for %s", integrated_path)
            # Fall through to rebuild from summary for resiliency.
    # Backward-compat for historical runs without integrated artifact.
    summary_path = _resolve_run_file_path(run_id, "summary.json")
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="Integrated results not found")
    summary = _read_summary_json(summary_path)
    coupling_manifest = summary.get("coupling_manifest") or {}
    return build_integrated_results(summary, coupling_manifest=coupling_manifest)


@app.get("/api/run/{run_id}/download/exchange/{file_path:path}")
def download_exchange_file(run_id: str, file_path: str):
    normalized = file_path.strip().lstrip("/")
    if not normalized or ".." in normalized:
        raise HTTPException(status_code=400, detail="Invalid exchange path")
    candidate = _resolve_run_file_path(run_id, f"exchange/{normalized}")
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Exchange file not found")
    media_type, _ = mimetypes.guess_type(candidate.name)
    return FileResponse(
        path=str(candidate),
        filename=candidate.name,
        media_type=media_type or "application/octet-stream",
    )

@app.get("/api/run/{run_id}/download/csv")
def download_results_csv(run_id: str):
    path = _resolve_run_file_path(run_id, "results.csv")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Results CSV not found")
    return FileResponse(path=str(path), filename=f"edim_{run_id}_results.csv", media_type="text/csv")


@app.get("/api/run/{run_id}/download/report")
def download_report(run_id: str):
    path = _resolve_run_file_path(run_id, "report.md")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Run report not found")
    return FileResponse(path=str(path), filename=f"edim_{run_id}_report.md", media_type="text/markdown")


@app.get("/api/run/{run_id}/download/exchange_bundle")
def download_exchange_bundle(run_id: str):
    path = _resolve_run_file_path(run_id, "exchange_bundle.zip")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Exchange bundle not found")
    return FileResponse(path=str(path), filename=f"edim_{run_id}_exchange_bundle.zip", media_type="application/zip")
