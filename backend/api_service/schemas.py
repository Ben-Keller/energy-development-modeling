from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RunProfile = Literal["dev", "analysis", "full"]
EnergyModelEngine = Literal["calliope", "osemosys"]


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
    model_config = ConfigDict(extra="ignore")

    energy_model_engine: EnergyModelEngine = Field(default="calliope", description="Energy-model runtime engine. Calliope is executable now; OSeMOSYS is a selectable adapter target pending runtime implementation.")
    energy_scenario_key: str = Field(default="", min_length=0, max_length=200, description="Energy scenario key from the energy model catalog")
    # Legacy alias accepted from smoke test and older clients. Takes effect only when energy_scenario_key is empty.
    scenario: str = Field(default="", exclude=True, description="Backward-compat alias for energy_scenario_key.")
    mrio_scenario_id: str = Field(default="ZA-S2", min_length=1, max_length=50, description="Integrated target scenario id")
    target_year: int = Field(default=2030, ge=1900, le=2200, description="Scenario target year")
    levers: LeverValues = Field(default_factory=LeverValues)
    run_profile: RunProfile = Field(default="dev")
    strict_validation: bool = Field(default=False)
    allow_placeholder_data: bool = Field(default=True)

    @model_validator(mode="after")
    def _normalize(self) -> "RunRequest":
        # Resolve legacy scenario alias → energy_scenario_key.
        if not self.energy_scenario_key and self.scenario:
            self.energy_scenario_key = self.scenario
        if not self.energy_scenario_key:
            raise ValueError("energy_scenario_key (or scenario) is required.")
        # Analysis/full profiles force strict validation.
        if self.run_profile in {"analysis", "full"}:
            self.strict_validation = True
        return self


class RunArtifacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    summary_url: str
    csv_url: str


class RunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
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
    exchange_artifacts: Dict[str, Any] = Field(default_factory=dict)
    integrated_results: Dict[str, Any] = Field(default_factory=dict)
    coupling_manifest: Dict[str, Any] = Field(default_factory=dict)
    scenario_assumptions: Dict[str, Any] = Field(default_factory=dict)
    development_indicators: Dict[str, Any] = Field(default_factory=dict)


class JobInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
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


class JobSubmitResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job: JobInfo


class JobListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobs: List[JobInfo] = Field(default_factory=list)
