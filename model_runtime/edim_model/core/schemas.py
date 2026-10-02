from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RunProfile = Literal["dev", "analysis", "full"]
EnergyModelEngine = Literal["calliope"]


class ScenarioInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    title: str
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    policy_question: str = ""
    expected_tradeoff: str = ""
    user_label: str = ""
    preset_levers: Dict[str, float] = Field(default_factory=dict)


class LeverValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    demand_multiplier: float = Field(default=1.0, ge=0.0, le=5.0, allow_inf_nan=False)
    renewables_capex_multiplier: float = Field(default=1.0, ge=0.0, le=5.0, allow_inf_nan=False)
    fossil_fuel_price_multiplier: float = Field(default=1.0, ge=0.0, le=10.0, allow_inf_nan=False)
    carbon_price_usd_per_tco2: float = Field(default=0.0, ge=0.0, le=1000.0, allow_inf_nan=False)


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    project_id: str = Field(default="default", min_length=1, max_length=120, description="Project/workspace identifier that owns this run in the platform layer")
    run_name: str = Field(default="", max_length=200, description="Optional user-facing run label")
    model_architecture_id: str = Field(default="energy-development", min_length=1, max_length=80, description="Selectable model architecture controlling graph, result surface, and visible artifact families")
    energy_model_engine: EnergyModelEngine = Field(default="calliope", description="Energy-model runtime engine. Calliope is the active executable runtime.")
    energy_scenario_key: str = Field(..., min_length=1, max_length=200, description="Energy scenario key from the energy model catalog")
    mrio_scenario_id: str = Field(..., min_length=1, max_length=50, description="Integrated target scenario id, currently S1 for full decarbonization or S2 for national policy target; MRIO shock mapping is fixed to the report A/Z/E/Y adapter for now")
    target_year: int = Field(..., ge=1900, le=2200, description="Scenario target year used by the integrated package")
    levers: LeverValues = Field(default_factory=LeverValues)
    run_profile: RunProfile
    strict_validation: bool
    allow_placeholder_data: bool

    @model_validator(mode="after")
    def _normalize_profile(self) -> "RunRequest":
        if self.run_profile in {"analysis", "full"}:
            self.strict_validation = True
        return self


class RunArtifacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    summary_url: str
    csv_url: str


class ArtifactDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    label: str
    kind: str
    producer_stage: str
    path: str
    download_url: str
    include_in_project_bundle: bool
    expose_download: bool
    embed_in_summary: bool
    embed_in_final_results: bool
    required_for_report: bool
    size_bytes: int | None = None
    media_type: str = "application/octet-stream"


class RunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    run_id: str
    model_architecture_id: str = "energy-development"
    energy_scenario_key: str
    mrio_scenario_id: str
    target_year: int
    run_profile: RunProfile
    warnings: List[str] = Field(default_factory=list)

    scenario_package: Dict[str, Any] = Field(default_factory=dict)
    generation_by_tech: Dict[str, Any] = Field(default_factory=dict)
    capacity_by_tech: Dict[str, Any] = Field(default_factory=dict)
    new_capacity_by_tech: Dict[str, Any] = Field(default_factory=dict)
    system_cost: Dict[str, Any] = Field(default_factory=dict)
    emissions: Dict[str, Any] = Field(default_factory=dict)
    summary_diagnostics: Dict[str, Any] = Field(default_factory=dict)
    development_impacts: Dict[str, Any] = Field(default_factory=dict)
    integrated_results: Dict[str, Any] = Field(default_factory=dict)
    coupling_manifest: Dict[str, Any] = Field(default_factory=dict)
    scenario_assumptions: Dict[str, Any] = Field(default_factory=dict)
    development_indicators: Dict[str, Any] = Field(default_factory=dict)
    run_package: Dict[str, Any] = Field(default_factory=dict)
    artifact_catalog: List[ArtifactDescriptor] = Field(default_factory=list)


class RunExecutionInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_id: str
    run_id: str | None = None
    status: str
    progress: float = 0.0
    stage: str = ""
    message: str = ""
    queue_position: int | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str | None = None
    worker_pid: int | None = None
    error: str | None = None
    request: RunRequest
    artifacts: RunArtifacts | None = None
    summary: RunSummary | None = None
    run_artifacts: List[ArtifactDescriptor] = Field(default_factory=list)


class RunSubmitResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: RunExecutionInfo


class RunListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runs: List[RunExecutionInfo] = Field(default_factory=list)
