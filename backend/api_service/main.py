from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import shutil
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .ai_query import plan_scenario_query
from .integrated import build_integrated_results, validate_integrated_results
from .scenarios import build_integrated_catalog
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
INPUT_DATASET_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")

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
    if settings.frontend_dir and settings.frontend_dir.exists() and settings.frontend_dir.is_dir():
        return settings.frontend_dir

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


def _input_dataset_catalog():
    repo_root = settings.config_dir.resolve().parent
    rows = [
        {
            "id": "scenario_metadata",
            "label": "Energy scenario metadata",
            "layer": "scenario",
            "role": "Maps Calliope override keys into scenario labels and user-facing descriptions.",
            "path": settings.config_dir / "scenario_metadata.csv",
        },
        {
            "id": "scenario_report",
            "label": "Energy Modelling Scenario Report",
            "layer": "scenario",
            "role": "Source report parsed into integrated target pathways and MRIO-direct assumptions.",
            "path": repo_root / "Energy Modelling Scenario Report.docx",
        },
        {
            "id": "africa_placeholder_scenarios",
            "label": "Africa national placeholder target scenarios",
            "layer": "scenario",
            "role": "National S1/S2 placeholder targets for African countries not explicitly defined in the report.",
            "path": settings.config_dir / "generated" / "africa_national_mrio_placeholder_scenarios.json",
        },
        {
            "id": "scenario_geography_mapping",
            "label": "Scenario geography mapping",
            "layer": "scenario",
            "role": "Maps MRIO geographies to Calliope countries and subnational locations.",
            "path": settings.config_dir / "scenario_geography_mapping.csv",
        },
        {
            "id": "calliope_model",
            "label": "Calliope model definition",
            "layer": "calliope",
            "role": "Primary Calliope-Africa model YAML.",
            "path": settings.calliope_root / "model.yaml",
        },
        {
            "id": "calliope_overrides",
            "label": "Calliope scenario overrides",
            "layer": "calliope",
            "role": "Calliope override definitions used by the energy scenario selector.",
            "path": settings.calliope_root / "overrides.yaml",
        },
        {
            "id": "lever_mappings",
            "label": "Policy lever mappings",
            "layer": "calliope",
            "role": "Maps UI policy levers to model-side parameter adjustments.",
            "path": settings.config_dir / "lever_mappings.csv",
        },
        {
            "id": "development_model",
            "label": "Development model configuration",
            "layer": "mrio",
            "role": "Development/MRIO runtime configuration and model controls.",
            "path": settings.config_dir / "development_model.csv",
        },
        {
            "id": "employment_intensity",
            "label": "Employment intensity",
            "layer": "mrio",
            "role": "Jobs per monetary shock by MRIO region and supplier sector.",
            "path": settings.config_dir / "mario_inputs" / "employment_intensity.csv",
        },
        {
            "id": "value_added_intensity",
            "label": "Value-added intensity",
            "layer": "mrio",
            "role": "Gross value added per monetary shock by MRIO region and supplier sector.",
            "path": settings.config_dir / "mario_inputs" / "value_added_intensity.csv",
        },
        {
            "id": "development_indicator_mapping",
            "label": "Development indicator mapping",
            "layer": "mrio",
            "role": "Maps MRIO impacts into development indicators shown in the dashboard.",
            "path": settings.config_dir / "mario_inputs" / "development_indicator_mapping.csv",
        },
        {
            "id": "scenario_assumptions",
            "label": "MRIO scenario assumptions",
            "layer": "mrio",
            "role": "Assumptions used by direct MRIO shock preparation.",
            "path": settings.config_dir / "mario_inputs" / "scenario_assumptions.csv",
        },
        {
            "id": "country_to_pool",
            "label": "Country to power-pool mapping",
            "layer": "mrio",
            "role": "Country and region mapping used for spatial aggregation and MRIO alignment.",
            "path": settings.config_dir / "mario_inputs" / "country_to_pool.csv",
        },
        {
            "id": "capex_sector_split",
            "label": "CAPEX sector split",
            "layer": "bridge",
            "role": "Splits Calliope capital expenditure shocks into MRIO supplier sectors.",
            "path": settings.config_dir / "mario_inputs" / "capex_sector_split.csv",
        },
        {
            "id": "opex_sector_split",
            "label": "OPEX sector split",
            "layer": "bridge",
            "role": "Splits operating and fuel shocks into MRIO supplier sectors.",
            "path": settings.config_dir / "mario_inputs" / "opex_sector_split.csv",
        },
        {
            "id": "calliope_tech_to_mario_sector",
            "label": "Calliope technology to MRIO sector",
            "layer": "bridge",
            "role": "Maps solved energy technologies to MRIO sector accounts.",
            "path": settings.config_dir / "mario_inputs" / "calliope_tech_to_mario_sector.csv",
        },
    ]
    return rows


def _resolve_input_dataset(dataset_id: str) -> dict:
    dataset_id = dataset_id.strip()
    if not INPUT_DATASET_ID_PATTERN.fullmatch(dataset_id):
        raise HTTPException(status_code=400, detail="Invalid dataset id.")
    datasets = {row["id"]: row for row in _input_dataset_catalog()}
    dataset = datasets.get(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Input dataset not found.")
    return dataset

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
    return build_integrated_catalog(overrides_path, metadata_path, settings.config_dir, settings.calliope_root)


@app.get("/api/environment-setup")
def get_environment_setup(
    energy_scenario_key: str = "",
    mrio_scenario_id: str = "",
    target_year: int = 2030,
    run_profile: str = "dev",
    strict_validation: bool | None = None,
    allow_placeholder_data: bool = False,
):
    queue_stats = job_manager.runtime_stats()
    return build_environment_setup_report(
        settings=settings,
        queue_stats=queue_stats,
        energy_scenario_key=energy_scenario_key,
        mrio_scenario_id=mrio_scenario_id,
        target_year=target_year,
        run_profile=run_profile,
        strict_validation=strict_validation,
        allow_placeholder_data=allow_placeholder_data,
    )


@app.get("/api/input-datasets")
def list_input_datasets():
    datasets = []
    for row in _input_dataset_catalog():
        path = Path(row["path"])
        stat = path.stat() if path.exists() else None
        datasets.append(
            {
                "id": row["id"],
                "label": row["label"],
                "layer": row["layer"],
                "role": row["role"],
                "filename": path.name,
                "exists": path.exists(),
                "size_bytes": stat.st_size if stat else None,
                "download_url": f"/api/input-datasets/{row['id']}/download",
            }
        )
    return {"datasets": datasets}


@app.post("/api/ai/scenario-query")
def plan_ai_scenario_query(payload: dict):
    return plan_scenario_query(payload, settings=settings)


@app.get("/api/input-datasets/{dataset_id}/download")
def download_input_dataset(dataset_id: str):
    dataset = _resolve_input_dataset(dataset_id)
    path = Path(dataset["path"])
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Input dataset file not found.")
    media_type, _ = mimetypes.guess_type(path.name)
    return FileResponse(
        path=str(path),
        filename=path.name,
        media_type=media_type or "application/octet-stream",
    )


@app.post("/api/input-datasets/{dataset_id}/upload")
async def upload_input_dataset(dataset_id: str, file: UploadFile = File(...)):
    dataset = _resolve_input_dataset(dataset_id)
    path = Path(dataset["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(f"{path.name}.bak")
        shutil.copy2(path, backup)
    with path.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    return {
        "ok": True,
        "dataset_id": dataset_id,
        "filename": path.name,
        "size_bytes": path.stat().st_size,
    }


@app.get("/api/preflight", include_in_schema=False)
def get_preflight_compat(
    energy_scenario_key: str = "",
    mrio_scenario_id: str = "",
    target_year: int = 2030,
    run_profile: str = "dev",
    strict_validation: bool | None = None,
    allow_placeholder_data: bool = False,
):
    return get_environment_setup(
        energy_scenario_key=energy_scenario_key,
        mrio_scenario_id=mrio_scenario_id,
        target_year=target_year,
        run_profile=run_profile,
        strict_validation=strict_validation,
        allow_placeholder_data=allow_placeholder_data,
    )


@app.post("/api/jobs", response_model=JobSubmitResponse)
def submit_job(req: RunRequest):
    if req.energy_model_engine != "calliope":
        raise HTTPException(
            status_code=501,
            detail="OSeMOSYS is selectable for scenario design/provenance, but the executable runtime adapter is not implemented yet. Use energy_model_engine='calliope' to run now.",
        )
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
    return build_integrated_results(summary, coupling_manifest=coupling_manifest, config_dir=settings.config_dir)


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


@app.get("/api/run/{run_id}/download/artifact/{file_path:path}")
def download_run_artifact(run_id: str, file_path: str):
    normalized = file_path.strip().lstrip("/")
    if not normalized or ".." in normalized:
        raise HTTPException(status_code=400, detail="Invalid artifact path")
    candidate = _resolve_run_file_path(run_id, normalized)
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Run artifact not found")
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
