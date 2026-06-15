from __future__ import annotations

import dataclasses
import json
import logging
import mimetypes
import os
import re
import shutil
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .ai_query import plan_scenario_query
from .composition import bootstrap_app
from .integrated import build_integrated_results, validate_integrated_results
from .request_context import reset_current_request, set_current_request
from .routes.manifest import router as manifest_router
from .scenarios import build_integrated_catalog
from .settings import get_settings
from .jobs_pg import PostgresJobManager
from .runner import build_environment_setup_report
from .schemas import (
    JobInfo,
    JobListResponse,
    JobSubmitResponse,
    RunRequest,
)
from .users import UserContext

logger = logging.getLogger(__name__)
RUN_ID_PATTERN = re.compile(r"^run_[a-f0-9]{12}$")
INPUT_DATASET_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")


# ---------------------------------------------------------------------------
# Pydantic request bodies for project-centric routes
# ---------------------------------------------------------------------------

class CreateProjectBody(BaseModel):
    title: str = "Untitled project"
    geography_code: str = ""
    use_case_label: str = ""
    description: str = ""


class CreateRunBody(BaseModel):
    energy_scenario_key: str
    mrio_scenario_id: str
    target_year: int = 2030
    run_profile: str = "dev"
    request_payload: dict = {}


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

async def _get_current_user(request: Request) -> UserContext:
    """Resolve the authenticated UserContext for this request."""
    return await request.app.state.auth_provider(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup hooks (DB connection, alembic migrations, queue
    consumers) before the first request, and clean up on shutdown.
    """
    # Suppress verbose AMQP transport internals — keep before bootstrap so the
    # Service Bus connection setup is already quiet.
    for _noisy in ("azure.servicebus._pyamqp", "azure.core.pipeline.policies.http_logging_policy"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)

    settings = get_settings()
    run_migrations = os.getenv("EDIM_RUN_MIGRATIONS", "true").strip().lower() in ("1", "true", "yes")
    bootstrap_app(app, settings, run_migrations=run_migrations)
    logger.info("Application startup complete (Postgres + Alembic + Service Bus ready).")
    try:
        yield
    finally:
        bridge = getattr(app.state, "worker_bridge", None)
        if bridge is not None:
            bridge.stop_completion_consumer()
        logger.info("Application shutdown complete.")


app = FastAPI(title="EDIM Calliope-Africa API", version="0.2.0", lifespan=lifespan)
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _request_context_middleware(request: Request, call_next):
    """Bind the current request to a contextvar for the duration of
    the handler so repository helpers can resolve the active session
    and UserContext without explicit parameter threading.
    """
    token = set_current_request(request)
    try:
        return await call_next(request)
    finally:
        reset_current_request(token)


app.include_router(manifest_router)

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

def _validate_run_id(run_id: str) -> None:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id format.")


def _blob_container_prefix() -> str:
    return os.getenv("EDIM_BLOB_CONTAINER_PREFIX", "stg-").strip()


def _stream_blob(run_id: str, blob_key: str, filename: str, media_type: str):
    """Return a 307 SAS redirect to a blob in stg-run-artifacts (plan 4.3).

    Falls back to direct streaming when the credential doesn't expose an
    account key (e.g. managed identity in staging/production).
    """
    from fastapi.responses import StreamingResponse
    from azure.storage.blob import generate_blob_sas, BlobSasPermissions

    blob_service = app.state.blob_client
    container_name = f"{_blob_container_prefix()}run-artifacts"
    account_key = getattr(blob_service.credential, "account_key", None)

    if account_key:
        expiry = datetime.now(timezone.utc) + timedelta(minutes=15)
        sas_token = generate_blob_sas(
            account_name=blob_service.account_name,
            container_name=container_name,
            blob_name=blob_key,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry,
            content_disposition=f'attachment; filename="{filename}"',
            content_type=media_type,
        )
        internal_base = blob_service.url.rstrip("/")
        public_base = os.getenv("EDIM_BLOB_PUBLIC_URL", "").strip().rstrip("/")
        if public_base:
            i_parsed = urlparse(internal_base)
            p_parsed = urlparse(public_base)
            base = urlunparse((p_parsed.scheme, p_parsed.netloc, i_parsed.path, "", "", ""))
        else:
            base = internal_base
        return RedirectResponse(
            url=f"{base}/{container_name}/{blob_key}?{sas_token}",
            status_code=307,
        )

    # Streaming fallback (managed identity / no key available).
    try:
        stream = blob_service.get_blob_client(container_name, blob_key).download_blob()
    except Exception as exc:
        if "BlobNotFound" in str(exc) or "404" in str(exc) or "does not exist" in str(exc):
            raise HTTPException(status_code=404, detail=f"{filename} not found for this run.")
        raise HTTPException(status_code=502, detail=f"Blob storage error: {exc}")

    def _iter():
        for chunk in stream.chunks():
            yield chunk

    return StreamingResponse(
        _iter(),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _read_blob_json(run_id: str, blob_key: str) -> dict:
    """Fetch and parse a JSON blob from stg-run-artifacts."""
    blob_client = app.state.blob_client
    container_name = f"{_blob_container_prefix()}run-artifacts"
    try:
        data = blob_client.get_blob_client(container_name, blob_key).download_blob().readall()
        return json.loads(data)
    except Exception as exc:
        if "BlobNotFound" in str(exc) or "404" in str(exc) or "does not exist" in str(exc):
            raise HTTPException(status_code=404, detail="Run artifact not found.")
        raise HTTPException(status_code=502, detail=f"Blob storage error: {exc}")


# kept for non-run filesystem paths (input datasets etc.)
def _resolve_run_file_path(run_id: str, filename: str):
    _validate_run_id(run_id)
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
    job_manager: PostgresJobManager = app.state.job_manager
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
async def submit_job(req: RunRequest, request: Request):
    if req.energy_model_engine != "calliope":
        raise HTTPException(
            status_code=501,
            detail="OSeMOSYS is selectable for scenario design/provenance, but the executable runtime adapter is not implemented yet. Use energy_model_engine='calliope' to run now.",
        )
    _require_calliope_model_yaml()
    user = await _get_current_user(request)
    job_manager: PostgresJobManager = app.state.job_manager
    try:
        job = job_manager.submit(req, user_id=user.user_id)
    except Exception as e:
        logger.exception("Job submission failed")
        raise HTTPException(status_code=500, detail=str(e))
    return JobSubmitResponse(job=job)


@app.get("/api/jobs", response_model=JobListResponse)
async def list_jobs(request: Request, limit: int = 50):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")
    user = await _get_current_user(request)
    job_manager: PostgresJobManager = app.state.job_manager
    return JobListResponse(
        jobs=job_manager.list(
            limit=limit,
            owner_user_id=user.user_id,
            is_admin=user.is_admin,
        )
    )


@app.get("/api/jobs/{job_id}", response_model=JobInfo)
async def get_job(job_id: str, request: Request):
    user = await _get_current_user(request)
    job_manager: PostgresJobManager = app.state.job_manager
    try:
        return job_manager.get(job_id, owner_user_id=user.user_id, is_admin=user.is_admin)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found")


@app.post("/api/jobs/cancel-all", response_model=JobListResponse)
async def cancel_all_jobs(request: Request, owner_user_id: Optional[str] = None):
    user = await _get_current_user(request)
    # Non-admins can only cancel their own jobs.
    target_user = owner_user_id if (user.is_admin and owner_user_id) else user.user_id
    job_manager: PostgresJobManager = app.state.job_manager
    cancelled = job_manager.cancel_all(user_id=target_user)
    return JobListResponse(jobs=cancelled)


@app.post("/api/jobs/{job_id}/cancel", response_model=JobInfo)
async def cancel_job(job_id: str, request: Request):
    user = await _get_current_user(request)
    job_manager: PostgresJobManager = app.state.job_manager
    try:
        return job_manager.cancel(job_id, owner_user_id=user.user_id, is_admin=user.is_admin)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found")

@app.get("/api/run/{run_id}/summary")
def get_summary(run_id: str):
    _validate_run_id(run_id)
    return _read_blob_json(run_id, f"{run_id}/summary.json")


@app.get("/api/run/{run_id}/development")
def get_development_impacts(run_id: str):
    _validate_run_id(run_id)
    return _read_blob_json(run_id, f"{run_id}/development_impacts.json")


@app.get("/api/run/{run_id}/integrated")
def get_integrated_results(run_id: str):
    _validate_run_id(run_id)
    try:
        integrated = _read_blob_json(run_id, f"{run_id}/integrated_results.json")
        try:
            return validate_integrated_results(integrated)
        except ValueError:
            logger.exception("Integrated payload validation failed for %s", run_id)
            # Fall through to rebuild from summary for resiliency.
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
    # Backward-compat: rebuild from summary if integrated artifact missing.
    summary = _read_blob_json(run_id, f"{run_id}/summary.json")
    coupling_manifest = summary.get("coupling_manifest") or {}
    return build_integrated_results(summary, coupling_manifest=coupling_manifest, config_dir=settings.config_dir)


@app.get("/api/run/{run_id}/download/csv")
def download_run_csv(run_id: str):
    _validate_run_id(run_id)
    return _stream_blob(run_id, f"{run_id}/results.csv", f"results_{run_id}.csv", "text/csv")


@app.get("/api/run/{run_id}/download/exchange/{file_path:path}")
def download_exchange_file(run_id: str, file_path: str):
    _validate_run_id(run_id)
    normalized = file_path.strip().lstrip("/")
    if not normalized or ".." in normalized:
        raise HTTPException(status_code=400, detail="Invalid exchange path")
    media_type, _ = mimetypes.guess_type(normalized)
    filename = Path(normalized).name
    return _stream_blob(run_id, f"{run_id}/exchange/{normalized}", filename, media_type or "application/octet-stream")


@app.get("/api/run/{run_id}/download/artifact/{file_path:path}")
def download_run_artifact(run_id: str, file_path: str):
    _validate_run_id(run_id)
    normalized = file_path.strip().lstrip("/")
    if not normalized or ".." in normalized:
        raise HTTPException(status_code=400, detail="Invalid artifact path")
    media_type, _ = mimetypes.guess_type(normalized)
    filename = Path(normalized).name
    return _stream_blob(run_id, f"{run_id}/{normalized}", filename, media_type or "application/octet-stream")


@app.get("/api/run/{run_id}/download/report")
def download_report(run_id: str):
    _validate_run_id(run_id)
    return _stream_blob(run_id, f"{run_id}/report.md", f"edim_{run_id}_report.md", "text/markdown")


@app.get("/api/run/{run_id}/download/exchange_bundle")
def download_exchange_bundle(run_id: str):
    _validate_run_id(run_id)
    return _stream_blob(run_id, f"{run_id}/exchange_bundle.zip", f"edim_{run_id}_exchange_bundle.zip", "application/zip")


# ---------------------------------------------------------------------------
# Session / identity (Issues 1, 2)
# ---------------------------------------------------------------------------

@app.get("/api/session")
async def get_session(request: Request):
    """Return the resolved UserContext for the caller (plan 2.3.1)."""
    user = await _get_current_user(request)
    return {
        "user_id": user.user_id,
        "display_name": user.display_name,
        "email": user.email,
        "organization": user.organization,
        "roles": list(user.roles),
        "is_admin": user.is_admin,
        "auth_mode": user.auth_mode.value,
    }


# ---------------------------------------------------------------------------
# Projects (Issue 1)
# ---------------------------------------------------------------------------

@app.post("/api/projects", status_code=201)
async def create_project(body: CreateProjectBody, request: Request):
    user = await _get_current_user(request)
    repo = request.app.state.platform_repository
    project = repo.create_project(user, **body.model_dump())
    return dataclasses.asdict(project)


@app.get("/api/projects")
async def list_projects(request: Request, limit: int = 100):
    user = await _get_current_user(request)
    repo = request.app.state.platform_repository
    projects = repo.list_projects(user, limit=limit)
    return {"projects": [dataclasses.asdict(p) for p in projects]}


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str, request: Request):
    user = await _get_current_user(request)
    repo = request.app.state.platform_repository
    project = repo.get_project(user, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return dataclasses.asdict(project)


# ---------------------------------------------------------------------------
# Model runtimes (Issue 1)
# ---------------------------------------------------------------------------

@app.get("/api/model-runtimes")
def get_model_runtimes():
    """Return available model engines and artifact/staging config (plan 3.2)."""
    storage_mode = os.getenv("EDIM_STORAGE_MODE", "azure_blob")
    return {
        "energy_engines": [
            {"key": "calliope", "label": "Calliope-Africa", "status": "available"},
            {"key": "osemosys", "label": "OSeMOSYS", "status": "not_implemented"},
        ],
        "development_engine": settings.development_engine,
        "artifact_handoff_mode": storage_mode,
        "dataset_staging_mode": "reference",
        "run_profile_options": ["dev", "analysis"],
    }


# ---------------------------------------------------------------------------
# Project-scoped run lifecycle (Issue 1)
# ---------------------------------------------------------------------------

@app.post("/api/projects/{project_id}/runs/validate")
async def validate_project_run(
    project_id: str,
    request: Request,
    energy_scenario_key: str = "",
    mrio_scenario_id: str = "",
    target_year: int = 2030,
    run_profile: str = "dev",
    strict_validation: bool | None = None,
    allow_placeholder_data: bool = False,
):
    """Validate environment setup for a project run (plan 3.2.3)."""
    user = await _get_current_user(request)
    repo = request.app.state.platform_repository
    project = repo.get_project(user, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    job_manager: PostgresJobManager = app.state.job_manager
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


@app.post("/api/projects/{project_id}/runs", status_code=201)
async def create_project_run(project_id: str, body: CreateRunBody, request: Request):
    """Create a draft run (not yet queued) for a project (plan 6.3.1)."""
    user = await _get_current_user(request)
    repo = request.app.state.platform_repository
    project = repo.get_project(user, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        run = repo.create_run(
            user,
            project_id=project_id,
            status="draft",
            energy_scenario_key=body.energy_scenario_key,
            mrio_scenario_id=body.mrio_scenario_id,
            target_year=body.target_year,
            run_profile=body.run_profile,
            request_payload=body.request_payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return dataclasses.asdict(run)


@app.get("/api/projects/{project_id}/runs")
async def list_project_runs(project_id: str, request: Request, limit: int = 100):
    user = await _get_current_user(request)
    repo = request.app.state.platform_repository
    runs = repo.list_runs(user, project_id=project_id, limit=limit)
    return {"runs": [dataclasses.asdict(r) for r in runs]}


@app.post("/api/projects/{project_id}/runs/{run_id}/submit")
async def submit_project_run(project_id: str, run_id: str, request: Request):
    """Enqueue a draft run (transition draft → queued, plan 6.3.2)."""
    user = await _get_current_user(request)
    _require_calliope_model_yaml()
    job_manager: PostgresJobManager = app.state.job_manager
    try:
        job = job_manager.submit_run(run_id, user_id=user.user_id, is_admin=user.is_admin)
    except KeyError:
        raise HTTPException(status_code=404, detail="Run not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"job": job.model_dump()}


# ---------------------------------------------------------------------------
# Execution status + events (Issues 1, 5)
# ---------------------------------------------------------------------------

@app.get("/api/executions/{execution_id}/status")
async def get_execution_status(execution_id: str, request: Request):
    """Poll run status by execution_id (plan 6.4)."""
    from sqlalchemy import select as _select
    from .db_models import ExecutionAttemptRecord as _EAR, ProjectRunRecord as _PRR

    user = await _get_current_user(request)
    session_factory = request.app.state.db_session_factory

    with session_factory() as session:
        attempt = session.execute(
            _select(_EAR).where(_EAR.execution_id == execution_id).limit(1)
        ).scalar_one_or_none()
        if attempt is None:
            # Fall back to active_execution_id on run (pre-pickup)
            run = session.execute(
                _select(_PRR).where(_PRR.active_execution_id == execution_id).limit(1)
            ).scalar_one_or_none()
        else:
            run = session.get(_PRR, attempt.run_id)

        if run is None:
            raise HTTPException(status_code=404, detail="Execution not found")
        if not user.is_admin and run.owner_user_id != user.user_id:
            raise HTTPException(status_code=404, detail="Execution not found")

        return {
            "execution_id": execution_id,
            "run_id": run.run_id,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        }


@app.get("/api/executions/{execution_id}/events")
async def get_execution_events(execution_id: str, request: Request):
    """Return all runtime events for an execution (plan 8.5)."""
    from sqlalchemy import select as _select
    from .db_models import ExecutionAttemptRecord as _EAR, ProjectRunRecord as _PRR
    import dataclasses as _dc

    user = await _get_current_user(request)
    session_factory = request.app.state.db_session_factory

    # Verify access: find the owning run.
    with session_factory() as session:
        attempt = session.execute(
            _select(_EAR).where(_EAR.execution_id == execution_id).limit(1)
        ).scalar_one_or_none()
        run_id = attempt.run_id if attempt else None
        if run_id:
            run = session.get(_PRR, run_id)
        else:
            run = session.execute(
                _select(_PRR).where(_PRR.active_execution_id == execution_id).limit(1)
            ).scalar_one_or_none()

    if run is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    if not user.is_admin and run.owner_user_id != user.user_id:
        raise HTTPException(status_code=404, detail="Execution not found")

    event_store = request.app.state.event_store
    events = event_store.read_events(execution_id)
    return {"execution_id": execution_id, "events": [_dc.asdict(e) for e in events]}


# ---------------------------------------------------------------------------
# Run artifacts listing (Issue 1)
# ---------------------------------------------------------------------------

@app.get("/api/runs/{run_id}/artifacts")
async def list_run_artifacts(run_id: str, request: Request):
    """List available blob artifacts for a completed run."""
    _validate_run_id(run_id)
    user = await _get_current_user(request)
    session_factory = request.app.state.db_session_factory
    from sqlalchemy import select as _select
    from .db_models import ProjectRunRecord as _PRR

    with session_factory() as session:
        run = session.get(_PRR, run_id)
        if run is None or (not user.is_admin and run.owner_user_id != user.user_id):
            raise HTTPException(status_code=404, detail="Run not found")

    blob_service = request.app.state.blob_client
    container_name = f"{_blob_container_prefix()}run-artifacts"
    prefix = f"{run_id}/"
    artifacts = []
    try:
        container = blob_service.get_container_client(container_name)
        for blob in container.list_blobs(name_starts_with=prefix):
            rel_path = blob.name[len(prefix):]
            artifacts.append({
                "name": rel_path,
                "blob_name": blob.name,
                "size_bytes": blob.size,
                "last_modified": blob.last_modified.isoformat() if blob.last_modified else None,
                "download_url": f"/api/run/{run_id}/download/artifact/{rel_path}",
            })
    except Exception as exc:
        if "ContainerNotFound" in str(exc) or "404" in str(exc):
            pass  # No artifacts yet
        else:
            logger.warning("Error listing artifacts for %s: %s", run_id, exc)

    return {"run_id": run_id, "artifacts": artifacts}
