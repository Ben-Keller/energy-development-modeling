"""Runtime provider protocols (plan chapter 3.2, 5.1, 6.2, 8.1).

These define the contracts that the API, worker, and any future
alternative implementation must satisfy. The Postgres-backed
implementations live in services/. Local dev and staging can substitute
alternate providers without changing the orchestrator code in runner.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Protocol, Sequence


# ---------------------------------------------------------------------------
# PlatformRepository (plan 3.2)
# ---------------------------------------------------------------------------


@dataclass
class ProjectSummary:
    project_id: str
    owner_user_id: str
    title: str
    geography_code: str
    use_case_label: str
    archived: bool
    created_at: str
    updated_at: str


@dataclass
class RunSummaryRecord:
    run_id: str
    project_id: str
    owner_user_id: str
    status: str
    run_profile: str
    energy_scenario_key: str
    mrio_scenario_id: str
    target_year: int
    created_at: str
    updated_at: str


@dataclass
class ReportSummary:
    report_id: str
    project_id: str
    owner_user_id: str
    title: str
    status: str
    storage_ref: Optional[dict]
    created_at: str
    updated_at: str


class PlatformRepository(Protocol):
    """CRUD over projects, runs, reports, exports. Plan 3.2.

    All read methods accept an actor: UserContext and apply mandatory
    ownership filtering (plan 2.3.1, 3.5). Admins see all records.
    """

    # --- projects ---
    def create_project(self, actor, **fields) -> ProjectSummary: ...
    def get_project(self, actor, project_id: str) -> Optional[ProjectSummary]: ...
    def list_projects(self, actor, limit: int = 100) -> list[ProjectSummary]: ...
    def update_project(self, actor, project_id: str, **fields) -> ProjectSummary: ...
    def archive_project(self, actor, project_id: str) -> ProjectSummary: ...

    # --- runs ---
    def create_run(self, actor, project_id: str, **fields) -> RunSummaryRecord: ...
    def get_run(self, actor, run_id: str) -> Optional[RunSummaryRecord]: ...
    def list_runs(self, actor, project_id: Optional[str] = None, limit: int = 100) -> list[RunSummaryRecord]: ...
    def update_run_status(self, actor, run_id: str, status: str, **fields) -> RunSummaryRecord: ...
    def set_run_cancellation(self, actor, run_id: str, requested: bool) -> None: ...

    # --- reports ---
    def create_report(self, actor, project_id: str, **fields) -> ReportSummary: ...
    def get_report(self, actor, report_id: str) -> Optional[ReportSummary]: ...
    def list_reports(self, actor, project_id: Optional[str] = None, limit: int = 100) -> list[ReportSummary]: ...
    def update_report(self, actor, report_id: str, **fields) -> ReportSummary: ...

    # --- exports ---
    def create_export(self, actor, project_id: str, **fields) -> ReportSummary: ...
    def get_export(self, actor, export_id: str) -> Optional[ReportSummary]: ...
    def update_export(self, actor, export_id: str, **fields) -> ReportSummary: ...


# ---------------------------------------------------------------------------
# DatasetRepository (plan 5.1)
# ---------------------------------------------------------------------------


@dataclass
class DatasetVersionRecord:
    dataset_version_id: str
    dataset_id: str
    owner_user_id: str
    storage_uri: str
    file_hash: str
    file_size_bytes: int
    mime_type: str
    validation_metrics: dict
    is_archived: bool
    created_at: str


class DatasetRepository(Protocol):
    """CRUD over dataset versions with reference-locking semantics (plan 5.3)."""

    def register_version(self, actor, **fields) -> DatasetVersionRecord: ...
    def get_version(self, actor, dataset_version_id: str) -> Optional[DatasetVersionRecord]: ...
    def list_versions(self, actor, dataset_id: str) -> list[DatasetVersionRecord]: ...
    def list_all_for_owner(self, actor) -> list[DatasetVersionRecord]: ...
    def activate_version(self, actor, dataset_id: str, dataset_version_id: str) -> None: ...
    def get_active_version(self, actor, dataset_id: str) -> Optional[DatasetVersionRecord]: ...
    def archive_version(self, actor, dataset_version_id: str) -> DatasetVersionRecord: ...
    def hard_delete_version(self, actor, dataset_version_id: str) -> bool: ...


# ---------------------------------------------------------------------------
# ExecutionQueue (plan 6.2)
# ---------------------------------------------------------------------------


@dataclass
class QueueMessage:
    execution_id: str
    run_id: str
    project_id: str
    user_id: str
    request_payload: dict
    dataset_versions: list[dict] = field(default_factory=list)
    attempt_count: int = 1


@dataclass
class CompletionMessage:
    execution_id: str
    run_id: str
    worker_id: str
    outcome: str
    attempt_count: int
    error: Optional[str] = None
    summary: Optional[dict] = None
    artifact_storage_refs: list[dict] = field(default_factory=list)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


@dataclass
class CancellationMessage:
    execution_id: str
    run_id: str
    cancelled_by: Optional[str] = None


class ExecutionQueue(Protocol):
    """Durable queue seam. Postgres implementation in this workstream;
    AzureServiceBusQueue is a follow-up (plan 6.2)."""

    def enqueue(self, message: QueueMessage) -> None: ...
    def reserve(self, lease_seconds: int = 300) -> Optional[QueueMessage]: ...
    def complete(self, message: QueueMessage) -> None: ...
    def abandon(self, message: QueueMessage, requeue: bool = True) -> None: ...
    def dead_letter(self, message: QueueMessage, reason: str) -> None: ...
    def renew_lease(self, message: QueueMessage, lease_seconds: int = 60) -> None: ...
    def depth(self) -> int: ...


# ---------------------------------------------------------------------------
# EventStore (plan 8.1)
# ---------------------------------------------------------------------------


@dataclass
class RuntimeEvent:
    execution_id: str
    run_id: Optional[str]
    level: str
    stage: str
    message: str
    payload: Optional[dict]
    timestamp: str


class EventStore(Protocol):
    """Durable event log for live progress tracking (plan 8.1)."""

    def append_event(self, event: RuntimeEvent) -> None: ...
    def read_events(self, execution_id: str) -> list[RuntimeEvent]: ...
    def import_event_log(self, execution_id: str, source_path: str) -> int: ...
