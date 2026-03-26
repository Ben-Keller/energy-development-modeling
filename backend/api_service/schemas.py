from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RunProfile = Literal["dev", "analysis", "full"]


class ScenarioInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    title: str
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    policy_question: str = ""
    baseline_scenario: str = ""
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
    model_config = ConfigDict(extra="forbid")

    scenario: str = Field(..., min_length=1, max_length=200, description="Scenario key from overrides.yaml")
    levers: LeverValues = Field(default_factory=LeverValues)
    fast_dev_mode: bool = True
    run_profile: RunProfile | None = None

    @model_validator(mode="after")
    def _normalize_profile(self) -> "RunRequest":
        profile = self.run_profile or ("dev" if self.fast_dev_mode else "full")
        self.run_profile = profile
        self.fast_dev_mode = profile != "full"
        return self


class RunArtifacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    summary_url: str
    csv_url: str


class RunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    scenario: str
    fast_dev_mode: bool
    run_profile: RunProfile | None = None
    warnings: List[str] = Field(default_factory=list)

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
