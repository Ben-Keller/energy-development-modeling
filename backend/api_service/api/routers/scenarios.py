from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import get_job_manager, get_model_catalog_provider, get_settings
from ...jobs import JobManager
from ...services.model_catalog import ModelCatalogProvider
from ...settings import Settings

router = APIRouter()


@router.get("/api/scenarios")
def list_scenarios(
    settings: Settings = Depends(get_settings),
    job_manager: JobManager = Depends(get_job_manager),
    catalog_provider: ModelCatalogProvider = Depends(get_model_catalog_provider),
):
    return catalog_provider.scenario_catalog(settings=settings, manifest=job_manager.runtime_manifest())
