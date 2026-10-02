from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RunProfile = Literal["dev", "analysis", "full"]
EnergyModelEngine = Literal["calliope"]
RunStatus = Literal["draft", "queued", "running", "succeeded", "failed", "cancelled"]

RUN_STATUSES: tuple[str, ...] = ("draft", "queued", "running", "succeeded", "failed", "cancelled")
TERMINAL_RUN_STATUSES: tuple[str, ...] = ("succeeded", "failed", "cancelled")
RUN_STATUS_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "draft": ("queued", "cancelled"),
    "queued": ("running", "cancelled", "failed"),
    "running": ("succeeded", "failed", "cancelled"),
    "succeeded": (),
    "failed": (),
    "cancelled": (),
}


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


class PlatformUserRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    user_id: str
    display_name: str = ""
    email: str = ""
    organization: str = ""
    roles: List[str] = Field(default_factory=list)
    is_admin: bool = False
    auth_mode: str = ""


class ProjectVisualModelSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    project_run_number: int = 0
    status: str = "draft"
    architecture_id: str = "energy-development"
    scenario_key: str = ""
    target_scenario_id: str = ""
    target_year: int | None = None
    run_profile: str = "dev"
    lever_count: int = 0
    artifact_count: int = 0
    kpi_scope_count: int = 0
    summary_available: bool = False
    evidence_status: str = "not_evaluated"
    evidence_score: int = 0


class ProjectVisualSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_count: int = 0
    completed_count: int = 0
    active_count: int = 0
    failed_count: int = 0
    architecture_count: int = 0
    scenario_count: int = 0
    kpi_scope_count: int = 0
    variation_score: float = 0.0
    evidence_status: str = "not_evaluated"
    exploratory_model_count: int = 0
    analyst_review_model_count: int = 0
    models: List[ProjectVisualModelSummary] = Field(default_factory=list)


class ProjectRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    project_id: str
    title: str = ""
    geography: str = ""
    project_type: str = "energy-development"
    model_architecture_id: str = "energy-development"
    scenario_label: str = ""
    notes: str = ""
    status: str = "active"
    owner_user_id: str = ""
    created_by_user_id: str = ""
    last_updated_by_user_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    visual_summary: ProjectVisualSummary = Field(default_factory=ProjectVisualSummary)


class ProjectRunRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: str
    execution_id: str = ""
    project_id: str = ""
    project_run_number: int = 0
    run_name: str = ""
    status: RunStatus | str = "draft"
    stage: str = ""
    progress: float = 0.0
    message: str = ""
    owner_user_id: str = ""
    created_by_user_id: str = ""
    last_updated_by_user_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    request: Dict[str, Any] = Field(default_factory=dict)
    execution_queue_message: Dict[str, Any] = Field(default_factory=dict)
    execution_attempts: List[Dict[str, Any]] = Field(default_factory=list)
    cancellation_requested: bool = False
    worker_id: str = ""
    dataset_snapshot: Dict[str, Any] = Field(default_factory=dict)
    artifact_catalog: List[Dict[str, Any]] = Field(default_factory=list)
    summary_available: bool = False
    source_run_id: str = ""
    model_id: str = ""
    model_number: int = 0
    model_name: str = ""
    latest_execution_id: str = ""
    evidence_status: str = "not_evaluated"
    evidence_score: int = 0
    evidence_summary: str = ""


class PublicRunScenarioSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    energy_scenario_key: str = ""
    target_scenario_id: str = ""
    target_year: int | None = None


class PublicRunConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    run_name: str = ""
    model_architecture_id: str = "energy-development"
    energy_model_engine: EnergyModelEngine | str = "calliope"
    scenario: PublicRunScenarioSelection = Field(default_factory=PublicRunScenarioSelection)
    run_profile: RunProfile | str = "dev"
    levers: Dict[str, Any] = Field(default_factory=dict)


class PublicRunCreateRequest(PublicRunConfiguration):
    """Frontend-facing run configuration.

    Server-owned execution details such as project id, validation strictness,
    placeholder policy, dataset snapshot, runtime manifest, queue metadata, and
    artifact policy are deliberately excluded from this DTO.
    """

    model_config = ConfigDict(extra="forbid", protected_namespaces=())


class PublicRunPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_name: str | None = Field(default=None, max_length=200)
    request: PublicRunCreateRequest | None = None


class ProjectRunListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    execution_id: str = ""
    project_id: str = ""
    project_run_number: int = 0
    run_name: str = ""
    model_id: str = ""
    model_number: int = 0
    model_name: str = ""
    latest_execution_id: str = ""
    evidence_status: str = "not_evaluated"
    evidence_score: int = 0
    evidence_summary: str = ""
    status: RunStatus | str = "draft"
    stage: str = ""
    progress: float = 0.0
    message: str = ""
    created_at: str = ""
    updated_at: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    queue_position: int | None = None
    cancellation_requested: bool = False
    error: str | None = None
    artifacts: RunArtifacts | None = None
    summary_available: bool = False
    source_run_id: str = ""
    configuration: PublicRunConfiguration = Field(default_factory=PublicRunConfiguration)


class RunStatusView(ProjectRunListItem):
    model_config = ConfigDict(extra="forbid")


class PublicProjectRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: ProjectRunListItem


class StorageReference(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str = "edim_storage_ref_v1"
    storage_provider: str = ""
    storage_scope: str = ""
    object_key: str = ""
    filename: str = ""
    media_type: str = "application/octet-stream"
    size_bytes: int = 0


class ReportRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    report_id: str
    project_id: str = ""
    run_ids: List[str] = Field(default_factory=list)
    report_type: str = ""
    format: str = "markdown"
    source_schema_version: str = ""
    evidence_status: str = "not_evaluated"
    requires_evidence_acknowledgement: bool = False
    status: str = ""
    owner_user_id: str = ""
    created_by_user_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    storage_ref: StorageReference | None = None
    source_data_storage_ref: StorageReference | None = None
    download_url: str = ""
    source_data_url: str = ""
    options: Dict[str, Any] = Field(default_factory=dict)


class ExportRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    export_id: str
    project_id: str = ""
    run_ids: List[str] = Field(default_factory=list)
    status: str = ""
    owner_user_id: str = ""
    created_by_user_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    storage_ref: StorageReference | None = None
    size_bytes: int = 0
    evidence_status: str = "not_evaluated"
    contains_exploratory_outputs: bool = False
    download_url: str = ""


class SessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authenticated: bool
    auth_mode: str
    user: PlatformUserRecord
    available_users: List[PlatformUserRecord] = Field(default_factory=list)


class ProjectListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    projects: List[ProjectRecord] = Field(default_factory=list)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: ProjectRecord


class ProjectRunListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    runs: List[ProjectRunListItem] = Field(default_factory=list)


class ProjectRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: ProjectRunRecord


class ReportListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    reports: List[ReportRecord] = Field(default_factory=list)


class ReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report: ReportRecord


class ExportListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    exports: List[ExportRecord] = Field(default_factory=list)


class ExportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    export: ExportRecord


class RuntimeEventRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str = ""
    type: str = ""
    stage: str = ""
    progress: float | None = None
    message: str = ""
    level: str = "info"
    run_id: str = ""
    execution_id: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict)


class RunEventsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_id: str
    events: List[RuntimeEventRecord] = Field(default_factory=list)


class RunArtifactListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    artifacts: List[ArtifactDescriptor] = Field(default_factory=list)


class InputDatasetDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    layer: str
    role: str
    required: bool
    scope: str
    upload_policy: str
    user_upload_listable: bool = True
    filename: str
    source_filename: str
    exists: bool
    size_bytes: int | None = None
    active_version_id: str = ""
    versioned_override: bool = False
    project_ids: List[str] = Field(default_factory=list)
    download_url: str


class InputDatasetListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    datasets: List[InputDatasetDescriptor] = Field(default_factory=list)


class InputDatasetCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=200)
    layer: str = Field(min_length=1, max_length=80)
    role: str = Field(min_length=1, max_length=500)
    scope: str = Field(default="user", max_length=50)
    upload_policy: str = Field(default="project_override", max_length=80)


class InputDatasetPatchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=200)
    layer: str | None = Field(default=None, min_length=1, max_length=80)
    role: str | None = Field(default=None, min_length=1, max_length=500)


class InputDatasetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: InputDatasetDescriptor


class ProjectDatasetAssignmentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9_]+$")
    version_id: str = Field(min_length=1, max_length=200)


class ProjectDatasetAssignmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    project_id: str
    dataset_id: str
    version_id: str
    project_ids: List[str] = Field(default_factory=list)


class DatasetVersionMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    version_id: str = ""
    dataset_id: str = ""
    filename: str = ""
    path: str = ""
    size_bytes: int | None = None
    created_at: str = ""
    scope: str = ""
    user_id: str = ""
    project_ids: List[str] = Field(default_factory=list)
    validation: Dict[str, Any] = Field(default_factory=dict)


class DatasetUploadResponse(DatasetVersionMetadata):
    ok: bool = True


class DatasetVersionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    user_id: str
    scope: str
    versions: List[DatasetVersionMetadata] = Field(default_factory=list)


class DatasetDeleteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    dataset_id: str
    version_id: str


class EnvironmentCheck(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    type: str
    status: str
    message: str = ""
    path: str = ""
    required: bool = False
    placeholder: bool = False
    active_version_id: str = ""


class EnvironmentValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strict_validation: bool
    allow_placeholder_data: bool
    placeholder_datasets: List[str] = Field(default_factory=list)
    message: str = ""


class EnvironmentSetupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    schema_version: str
    ok: bool
    user_id: str
    queue: Dict[str, Any] = Field(default_factory=dict)
    model_runtime: Dict[str, Any] = Field(default_factory=dict)
    runtime_preflight: Dict[str, Any] = Field(default_factory=dict)
    checks: List[EnvironmentCheck] = Field(default_factory=list)
    counts: Dict[str, int] = Field(default_factory=dict)
    validation: EnvironmentValidation


class ModelRuntimeCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_model_id: str
    runtime_mode: str
    artifact_handoff_mode: str
    dataset_staging_mode: str
    execution_retry_policy: Dict[str, Any] = Field(default_factory=dict)
    runtimes: List[Dict[str, Any]] = Field(default_factory=list)
    configuration_schema: Dict[str, Any] = Field(default_factory=dict)
    architecture_catalog: Dict[str, Any] = Field(default_factory=dict)
    scenario_catalog: Dict[str, Any] = Field(default_factory=dict)
    model_architectures: List[Dict[str, Any]] = Field(default_factory=list)
    declared_outputs: List[Dict[str, Any]] = Field(default_factory=list)
    dataset_manifest_path: str
    datasets: List[Dict[str, Any]] = Field(default_factory=list)


class SystemManifestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    ok: bool
    app: Dict[str, Any] = Field(default_factory=dict)
    user_context: Dict[str, Any] = Field(default_factory=dict)
    contracts: Dict[str, str] = Field(default_factory=dict)
    public_endpoints: Dict[str, List[str]] = Field(default_factory=dict)
    provider_boundaries: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    runtime: Dict[str, Any] = Field(default_factory=dict)
    storage: Dict[str, Any] = Field(default_factory=dict)
    diagnostics: List[Dict[str, Any]] = Field(default_factory=list)
    operational_notes: List[str] = Field(default_factory=list)


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
    run_provenance: Dict[str, Any] = Field(default_factory=dict)
    run_package: Dict[str, Any] = Field(default_factory=dict)
    artifact_publication: Dict[str, Any] = Field(default_factory=dict)
    artifact_catalog: List[ArtifactDescriptor] = Field(default_factory=list)


class RunExecutionInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_id: str
    run_id: str | None = None
    project_run_number: int = 0
    status: RunStatus
    progress: float = 0.0
    stage: str = ""
    message: str = ""
    queue_position: int | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str | None = None
    worker_pid: int | None = None
    worker_id: str = ""
    cancellation_requested: bool = False
    execution_queue_message: Dict[str, Any] = Field(default_factory=dict)
    execution_attempts: List[Dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    request: RunRequest
    artifacts: RunArtifacts | None = None
    summary: RunSummary | None = None
    run_artifacts: List[ArtifactDescriptor] = Field(default_factory=list)


class RunSubmitResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: RunStatusView


class RunListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runs: List[RunStatusView] = Field(default_factory=list)
