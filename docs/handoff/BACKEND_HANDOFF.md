# EDIM Backend Handoff Contract

This file is the backend-team handoff reference for hosting EDIM as a project/workspace platform around a black-box model runtime. It intentionally focuses on backend integration boundaries, not model-science improvements.

## Current State

The local implementation is ready for backend migration work in these areas:

- A thin FastAPI route layer in `backend/api_service/api/routers/`.
- Application services in `backend/api_service/services/`.
- Runtime contracts, event parsing, and artifact policy in `backend/api_service/runtime/`.
- Artifact read/download boundary in `backend/api_service/services/artifact_storage.py`.
- Dataset metadata/upload boundary in `backend/api_service/services/dataset_repository.py`.
- Runtime event persistence boundary through `EventStore` in `backend/api_service/runtime/stores.py`.
- A subprocess model adapter in `backend/api_service/adapters/subprocess_runtime.py`.
- A packaged model runtime in `model_runtime/edim_model/`.

The active local backend is single-instance and filesystem-backed. Cloud deployment should replace persistence, queueing, auth, and storage providers while preserving the public route semantics and model-runtime contract below.

The complete local user flow is now implemented:

1. User lands on the basic UNDP/EDIM entry page.
2. User selects a seeded test account and runtime target.
3. User opens the projects workspace.
4. User selects or creates a project.
5. User configures a model run in the graph-centered model workspace.
6. User validates environment setup.
7. Frontend creates a project run draft.
8. Frontend submits that project run.
9. Backend queues an execution and updates the project run record.
10. Frontend polls by `execution_id`.
11. User views results from persisted run artifacts.
12. User compares completed project runs.
13. User generates project reports and run/project export bundles.
14. User manages input dataset upload versions.

The frontend should be treated as a platform shell around this flow, not as a model-specific caller. Low-level HTTP transport, runtime target selection, test-user headers, upload calls, and browser-safe download URL behavior live in `frontend/api-client.js`. `frontend/app.jsx` builds the higher-level workspace/project/run methods on top of that transport. Frontend components should not infer artifact paths or direct model filenames.

The current frontend is a static React/Babel shell served by FastAPI for handoff simplicity. This is acceptable for backend contract testing. A later frontend repackaging to Vite or another compiled React setup is allowed, but it must preserve:

- `frontend/api-client.js` transport semantics or an equivalent API-client boundary
- `EDIM_LOCAL_API_BASE` / `EDIM_BACKEND_API_BASE` runtime configuration
- `GET /api/system/manifest` compatibility probing before loading hosted backend data
- descriptor-based artifact/report/export downloads
- the current hash-route behavior for the landing, projects/workspace, and methodology surfaces
- no direct model filesystem assumptions in UI components

The frontend currently includes:

- landing page and shared header branding
- project/workspace shell
- graph-centered model-run workspace
- static user-facing methodology page at `#/methodology`
- optimized landing-page visual assets in `frontend/assets/webp/`

Raw source images in `frontend/assets/photos/` are local-only and ignored; they are not part of the deployed frontend payload.

The frontend header now includes a runtime target switch for backend testing.
`Local` calls the same origin serving the UI. `Backend` calls the hosted API
base URL configured from the frontend runtime environment variable
`EDIM_BACKEND_API_BASE`; users do not enter backend URLs in the UI. Switching
targets clears loaded workspace state and reloads session, projects, datasets,
runtime catalogs, and scenario catalogs from the selected API. Hosted backends
used with this switch must allow the UI origin through CORS and must serve the
same route contract described below. If `EDIM_BACKEND_API_BASE` is unset, the
Backend side of the switch is disabled. `EDIM_BACKEND_API_BASE` is a public API
URL only; it must not contain credentials, API keys, signed URLs, or tenant
secrets because it is loaded into the browser runtime.

When the user switches targets, the frontend now probes `GET /api/system/manifest`
before loading project data. The switch displays a compact compatibility state:

- `Contract ok`: the manifest schema is correct, manifest diagnostics are clean, and the endpoints used by the frontend are listed.
- `Contract warning`: the backend is reachable, but one or more frontend-required endpoints are not listed in the manifest.
- `Contract error`: the manifest is unavailable, has the wrong schema, or reports failed diagnostics. Backend mode is not used when this check fails.

For early Azure testing, the hosted backend can use the same local test-user
contract by accepting `X-EDIM-User-Id`. If production auth is introduced before
handoff testing, the frontend API client has a single `window.EDIM_AUTH_PROVIDER`
extension point, but no speculative bearer/cookie auth behavior is hard-coded.
The backend must also allow the frontend origin through CORS and allow the
headers/methods used by the API surface below.

## Identity Contract

The API route layer now depends on `UserContext` from `backend/api_service/services/users.py`.

Stable fields:

- `user_id`
- `display_name`
- `email`
- `organization`
- `roles`
- `is_admin`
- `auth_mode`

Local auth uses `X-EDIM-User-Id` and seeded test users. Production should replace only `get_current_user_context` in `backend/api_service/api/dependencies.py` with real auth middleware/session logic.

Authorization rule:

- Non-admin users can access only records where `owner_user_id == user_id`.
- Admin users can list/access all owner-scoped records.
- Projects are not shared across users in the current contract.

## Run Identity Contract

There are two ids:

- `execution_id`: queue/worker attempt id.
- `run_id`: stable result namespace for artifacts, project records, comparison, reports, and exports.

Local ids are 32-character lowercase hex strings.

## Run State Machine

Run statuses are defined in `backend/api_service/schemas.py`.

Allowed statuses:

- `draft`
- `queued`
- `running`
- `succeeded`
- `failed`
- `cancelled`

Allowed transitions:

- `draft -> queued | cancelled`
- `queued -> running | cancelled | failed`
- `running -> succeeded | failed | cancelled`
- terminal: `succeeded | failed | cancelled`

The local API enforces draft editing, submission, cancellation, resubmission, and active-run deletion against this state machine. Completed or active runs must be duplicated before their configuration can be changed.

Status persistence note:

- The local `JobManager` owns live execution state while a process is running.
- The `PlatformRepository` is updated throughout execution and is the durable local run-history source.
- `GET /api/executions/{execution_id}/status` falls back to persisted project run records when in-memory execution state is unavailable.
- Cloud deployment should make persisted run state the primary source of truth and use queue/worker state only for active execution control.

## Public API Surface

The backend exposes typed OpenAPI response schemas for the main handoff-critical routes. Contract coverage is guarded by `test_openapi_exposes_system_manifest_schemas` in `backend/tests/test_mvp.py`.

`GET /api/system/manifest` is the stable machine-readable system manifest for
deployment compatibility and CI checks. It returns:

- `schema_version = edim_system_manifest`
- all stable payload/contract identifiers used by the backend/platform runtime
- public endpoint groups expected by the frontend/platform shell
- provider boundaries to replace for auth, metadata, datasets, artifacts, events, and queue/workers
- runtime mode, artifact handoff mode, dataset staging mode, and retry policy
- diagnostics that deployment CI can fail on before running the full smoke test

Session:

- `GET /api/session`
- `GET /api/system/manifest`

Projects:

- `GET /api/projects`
- `POST /api/projects`
- `GET /api/projects/{project_id}`
- `PATCH /api/projects/{project_id}`
- `DELETE /api/projects/{project_id}`

Project runs:

- `GET /api/projects/{project_id}/runs`
- `POST /api/projects/{project_id}/runs`
- `GET /api/projects/{project_id}/runs/{run_id}`
- `GET /api/projects/{project_id}/runs/{run_id}/diagnostics`
- `PATCH /api/projects/{project_id}/runs/{run_id}`
- `POST /api/projects/{project_id}/runs/{run_id}/submit`
- `POST /api/projects/{project_id}/runs/{run_id}/duplicate`
- `DELETE /api/projects/{project_id}/runs/{run_id}`

Frontend-facing run configuration is intentionally compact. `POST /api/projects/{project_id}/runs` and the `request`
field in `PATCH /api/projects/{project_id}/runs/{run_id}` should use this public shape:

```json
{
  "run_name": "Policy target case",
  "model_architecture_id": "energy-development",
  "energy_model_engine": "calliope",
  "scenario": {
    "energy_scenario_key": "new_links",
    "target_scenario_id": "S2",
    "target_year": 2030
  },
  "run_profile": "dev",
  "levers": {
    "demand_multiplier": 1.0,
    "renewables_capex_multiplier": 1.0,
    "fossil_fuel_price_multiplier": 1.0,
    "carbon_price_usd_per_tco2": 0.0
  }
}
```

The backend derives and owns these internal execution fields:

- `project_id` from the route and authorization context
- `strict_validation` from `run_profile`
- placeholder-data policy from server/runtime configuration
- selected dataset snapshot at submit time
- model runtime manifest, dataset manifest, artifact policy, and runtime settings
- queue message, execution attempts, worker metadata, and artifact catalog

The frontend-facing run endpoints return compact run items with `configuration`, status/progress, timestamps, ids, and
artifact download handles only. They do not expose model request bundles, dataset snapshots, queue messages, execution
attempts, artifact policy, or artifact catalogs. Those internals remain available through
`GET /api/projects/{project_id}/runs/{run_id}/diagnostics`, logs, and artifact endpoints for backend handoff and
operations.

Execution and status:

- `GET /api/runs`
- `GET /api/executions/{execution_id}/status`
- `POST /api/executions/{execution_id}/cancel`
- `GET /api/executions/{execution_id}/events`

Run outputs:

- `GET /api/runs/{run_id}/summary`
- `GET /api/runs/{run_id}/development`
- `GET /api/runs/{run_id}/integrated`
- `GET /api/runs/{run_id}/artifacts`
- `GET /api/runs/{run_id}/artifacts/{artifact_id}`
- `GET /api/runs/{run_id}/logs`
- `POST /api/runs/{run_id}/export`

Datasets:

- `GET /api/input-datasets`
- `GET /api/input-datasets/{dataset_id}/download`
- `POST /api/input-datasets/{dataset_id}/upload`
- `GET /api/input-datasets/{dataset_id}/versions`
- `GET /api/input-datasets/{dataset_id}/versions/{version_id}/download`
- `POST /api/input-datasets/{dataset_id}/versions/{version_id}/activate`
- `DELETE /api/input-datasets/{dataset_id}/versions/{version_id}`

Reports and exports:

- `GET /api/projects/{project_id}/reports`
- `POST /api/projects/{project_id}/reports`
- `GET /api/projects/{project_id}/reports/{report_id}`
- `GET /api/projects/{project_id}/reports/{report_id}/download`
- `GET /api/projects/{project_id}/reports/{report_id}/data`
- `GET /api/projects/{project_id}/exports`
- `POST /api/projects/{project_id}/exports`
- `GET /api/projects/{project_id}/exports/{export_id}`
- `GET /api/projects/{project_id}/exports/{export_id}/download`

System/catalog:

- `GET /api/scenarios`
- `GET /api/system/manifest`
- `GET /api/model-runtimes`
- `GET /api/environment-setup`
- `POST /api/projects/{project_id}/runs/validate`

`GET /api/scenarios` is module-driven. The stable shape is `module_configurations[]` plus `scenario_channels[]`, where each
channel declares the owning module, `config_key`, allowed options, default, and source/provenance. The frontend derives
energy pathways, target pathways, target years, and shock mappings from these channels instead of receiving EDIM-specific
top-level selector arrays. New model modules should register new channels through
`model_runtime/edim_model/modules/` and `model_runtime/edim_model/model_manifest.json`.

`GET /api/model-runtimes` is the canonical architecture/runtime catalog endpoint. It returns the selected runtime
manifest, configuration schema, declared outputs, dataset contract, runtime mode, artifact handoff mode, dataset staging
mode, execution retry policy, model architecture metadata, `architecture_catalog`, and a convenience
`scenario_catalog` payload for clients that initialize runtime and scenario metadata together.
`GET /api/scenarios` remains the canonical scenario-catalog endpoint; it returns module-owned `scenario_channels` and
`module_configurations`. Hosted backends should preserve both surfaces for frontend compatibility, but should avoid
adding model-specific selector fields outside the module-owned scenario-channel structure.
The frontend should not ship a separate architecture contract. The architecture catalog
is model-owned in `model_runtime/edim_model/architecture_catalog.json` and currently loaded through
`ModelCatalogProvider`, whose local implementation calls the packaged runtime catalog command declared in
`model_manifest.json -> catalog_entrypoint`.

Canonical frontend submission sequence:

1. `GET /api/session`
2. `GET /api/projects`
3. `POST /api/projects` when no suitable project exists
4. `GET /api/scenarios`
5. `GET /api/input-datasets`
6. `POST /api/projects/{project_id}/runs/validate`
7. `POST /api/projects/{project_id}/runs`
8. `POST /api/projects/{project_id}/runs/{run_id}/submit`
9. `GET /api/executions/{execution_id}/status`
10. `GET /api/projects/{project_id}/runs`
11. `GET /api/runs/{run_id}/summary | integrated | artifacts`

Compare/report/export sequence:

1. `GET /api/projects/{project_id}/runs`
2. Select completed run ids client-side.
3. `POST /api/projects/{project_id}/reports`
4. `GET /api/projects/{project_id}/reports/{report_id}/download`
5. `POST /api/runs/{run_id}/export`
6. `POST /api/projects/{project_id}/exports`
7. `GET /api/projects/{project_id}/exports/{export_id}/download`

Reports and exports use `succeeded`, `failed`, or `cancelled` lifecycle status semantics. Locally they are generated
synchronously but still include queued/started/finished metadata so the production backend can move them to background
workers without changing the frontend contract.

## Persistence Replacement Boundary

Local persistence uses one repository interface with a SQLite reference implementation:

- `SQLitePlatformRepository` in `backend/api_service/services/sqlite_platform_repository.py`, selected by `storage.platform_store_backend = sqlite` or `EDIM_PLATFORM_STORE_BACKEND=sqlite`.

The SQLite implementation stores owner-scoped project/run/report/export metadata transactionally in `outputs/platform/platform.sqlite3`, keeps large artifacts in the existing artifact folders, and imports existing JSON indexes into SQLite when the database is first initialized.

Objects that need durable database tables:

- users or external user references
- projects
- runs
- reports
- exports
- dataset version metadata
- active dataset version pointers
- runtime events or event pointers
- artifact descriptors or artifact pointers

The provider seam is now explicit:

- `RunRepository` in `backend/api_service/runtime/stores.py`
- `EventStore` in `backend/api_service/runtime/stores.py`
- `PlatformRepository` in `backend/api_service/services/platform_repository.py`
- `SQLitePlatformRepository` in `backend/api_service/services/sqlite_platform_repository.py`
- `create_platform_repository` in `backend/api_service/services/platform_repository.py`

The platform and run routers depend on `PlatformRepository`. Azure deployment should treat SQLite as the local reference schema and provide a cloud database-backed implementation injected as `app.state.platform_repository`.

The FastAPI composition root accepts provider injection:

`create_app(settings=..., platform_repository=..., artifact_storage=..., dataset_repository=..., event_store=..., job_manager=..., model_catalog_provider=...)`

Azure deployment should use this hook rather than modifying route code.

## Model Catalog Provider Boundary

Model scenarios and UI graph architecture are runtime-owned metadata, not backend hard-codes.

Local implementation:

- `RuntimeCliModelCatalogProvider` in `backend/api_service/services/model_catalog.py`
- Calls `model_manifest.json -> catalog_entrypoint`
- Uses an allowlisted environment for catalog subprocesses
- Requires a model-owned catalog command; the backend does not import model scenario modules directly

Cloud replacement options:

- Cache model catalogs in a database or object store when a model image/package is registered.
- Resolve the active catalog through the same `ModelCatalogProvider` interface.
- Keep `/api/scenarios` and `/api/model-runtimes` response shapes stable while model packages evolve.
- Treat `architecture_catalog` as the source of truth for selectable model architectures, result tabs, graph boxes, graph edges, and user-visible output artifacts.

Required packaged runtime command shape:

```bash
python -m edim_model.cli catalog \
  --config-dir <inputs-dir> \
  --calliope-root <calliope-model-root> \
  --manifest <model_manifest.json> \
  --architecture-catalog <architecture-catalog-json>
```

The command must return a JSON object with `scenario_catalog` and `architecture_catalog`.

## Runtime Event Store Replacement Boundary

Runtime progress/history reads are routed through `EventStore` instead of direct
local file access.

Local implementation:

- `LocalEventStore`
- JSONL-backed under `outputs/runs/_queued/<execution_id>/logs/runtime_events.jsonl`
- used by `JobManager` while the subprocess runtime is active
- used by `/api/executions/{execution_id}/events` and `/api/runs/{run_id}/logs`

Cloud replacement should provide a database, Blob, or event-stream-backed
implementation and inject it as `app.state.event_store`.

Required semantics:

- `event_log_path(execution_id)` returns a local worker path only when the
  selected adapter needs one. Remote/container adapters may ignore this method
  or return a staging path.
- `append_event(execution_id, event)` persists one `runtime_event_v1` object.
- `read_events(execution_id)` returns ordered `runtime_event_v1` event objects.
- `import_event_log(execution_id, source_path)` lets local/container workers
  publish a completed JSONL log into durable event storage.

Cloud implementations should keep event authorization in the route/service layer
and never expose worker-local event paths to the frontend.

## Artifact Storage Replacement Boundary

Run artifact reads and platform report/export downloads are routed through `ArtifactStorageService` in `backend/api_service/services/artifact_storage.py`.

Local implementation:

- `LocalArtifactStorageService`
- filesystem-backed
- uses artifact ids and the persisted run artifact policy to resolve run artifacts
- returns FastAPI `FileResponse` for local files

Cloud replacement should provide a Blob-backed implementation and inject it as `app.state.artifact_storage`.

Report and project-export file assembly is separated from repository persistence in
`backend/api_service/services/platform_artifacts.py`. `SQLitePlatformRepository`
persists metadata and calls that helper only for the local reference
implementation. A hosted backend can keep the same repository contract while
moving report rendering, ZIP assembly, and storage publication into background
workers or object-storage services.

Required semantics:

- `read_json_artifact(run_id, artifact_id)` returns a JSON object for summary/development/integrated endpoints.
- `download_response_for_artifact(run_id, artifact_id)` returns a controlled download response for declared run artifacts.
- `download_response_for_ref(storage_ref, filename, default_media_type)` returns a controlled download response for report/export storage references.

Preferred cloud behavior:

- Store `storage_ref` objects with provider/container/object-key metadata in run/report/export records.
- Resolve artifact ids to Blob objects, not local paths.
- Return a streaming response or short-lived signed URL.
- Keep authorization in route/service logic before calling storage.

Platform report/export records now use storage references as their primary
storage contract:

```json
{
  "schema_version": "edim_storage_ref_v1",
  "storage_provider": "local_platform_filesystem",
  "storage_scope": "platform",
  "object_key": "reports/<report_id>.md",
  "filename": "<report_id>.md",
  "media_type": "text/markdown",
  "size_bytes": 1234
}
```

Cloud providers should keep the semantic fields but use provider-specific
container/object keys instead of local paths.

## Basic Report Generation Contract

The current report system is intentionally basic and backend-owned:

- `POST /api/projects/{project_id}/reports` creates one Markdown report.
- The generator also writes a structured source-data JSON file.
- Report source data uses schema `edim_project_report_source_v1`.
- Source data is built from project metadata, selected project run records, available run `summary_json` artifacts, and existing project export records.
- The frontend downloads reports through `download_url` and source data through `source_data_url`.
- Project export bundles include both `reports/<report_id>.md` and `reports/<report_id>.source.json` when `include_reports=true`.

This is not a final publication renderer. It is the stable backend linkage for future report renderers. A richer renderer can consume the same source-data JSON and replace Markdown output without changing project/run/report APIs.

## Dataset Repository Replacement Boundary

Input dataset catalogs, user-scoped versions, upload activation, and dataset file downloads are routed through `DatasetRepository` in `backend/api_service/services/dataset_repository.py`.

Local implementation:

- `LocalDatasetRepository`
- filesystem-backed upload versions under `outputs/dataset_uploads/users/<user_id>/`
- active-version pointers in per-user `active_versions.json`
- runtime dataset snapshots emitted through `runtime_dataset_manifest(user_id=...)`
- staged runtime snapshots emitted through `stage_runtime_datasets(user_id=..., run_dir=..., staging_mode=...)`

Cloud replacement should provide a database/object-storage implementation and inject it as `app.state.dataset_repository`.

Required semantics:

- `list_input_datasets(...)` returns UI/API descriptors for the active user.
- `runtime_dataset_manifest(user_id=...)` returns the active-user dataset catalog snapshot.
- `stage_runtime_datasets(...)` returns the exact file/object references handed to `model_run_bundle_v1`.
- `register_upload(...)` stores one immutable version, validates it, and makes it active.
- `activate_version(...)` changes only the active pointer, not the underlying uploaded object.
- `download_response_for_dataset(...)` returns a controlled response or signed URL equivalent for the active version/source object.

Dataset staging is explicit in `inputs/runtime_config.json -> model_runtime.dataset_staging_mode` and `GET /api/model-runtimes -> dataset_staging_mode`.

Allowed modes:

- `copy_to_run`: local default. The bundle copies resolved input files into `inputs/datasets/<dataset_id>/` under the queued run package before execution so submitted runs are self-contained.
- `reference`: development-only mode. The bundle references existing resolved local paths and includes `dataset_staging_v1` metadata.
- `object_reference`: provider mode for cloud implementations that hand model workers durable object-storage references instead of local paths.

Every `dataset_manifest` in a run bundle includes:

- `dataset_staging.schema_version = dataset_staging_v1`
- per-dataset `staging_mode`
- per-dataset `staging_status`
- per-dataset `storage_ref`
- per-dataset `source_storage_ref`
- optional `staged_relative_path`
- `content_sha256` and `size_bytes` where the file is locally readable

## Queue Replacement Boundary

Local execution queue:

- `JobManager` in `backend/api_service/jobs.py`
- `LocalExecutionQueue` in `backend/api_service/runtime/stores.py`
- local development now enqueues the same `execution_queue_message` payload that cloud workers should consume

Cloud replacement should provide:

- durable enqueue
- worker lease/visibility timeout
- cancellation propagation
- retry policy from `execution_retry_policy`
- attempt lifecycle records using `execution_attempt`
- progress-event persistence
- terminal status update

Suggested Azure mapping:

- Azure Service Bus or Storage Queue for execution messages.
- Worker service or Batch job for model runtime execution.
- Database row for run status.
- Blob Storage for run package and artifacts.

Required cloud queue behavior:

- Create the run record transactionally before enqueueing.
- Store `execution_id`, `run_id`, `project_id`, `user_id`, request payload, and attempt count in the queue message.
- Persist one `execution_attempt` row/object whenever a worker accepts a message, heartbeat it while running, and finish it with terminal status.
- Update persisted status on every worker state transition.
- Persist or stream `runtime_event_v1` events so `/api/executions/{execution_id}/events` does not depend on a local file.
- Support cancellation by marking persisted state and propagating cancellation to the active worker where possible.
- Never expose raw queue ids, local paths, or worker paths to the frontend.

The queue message is also stored in:

- project run record field `execution_queue_message`
- run bundle field `queue_message`
- downloadable `request_bundle_json` artifact

This makes worker input provenance inspectable without relying on local queue internals.

Queue payload schema:

```json
{
  "schema_version": "execution_queue_message",
  "execution_id": "<queue attempt id>",
  "run_id": "<stable artifact namespace>",
  "project_id": "<owning project id>",
  "user_id": "<owner user id>",
  "attempt": 1,
  "created_at": "<ISO timestamp>",
  "retry_policy": {
    "schema_version": "execution_retry_policy",
    "max_attempts": 1,
    "retry_on": ["worker_start_failure", "infrastructure_failure"],
    "model_errors_terminal": true,
    "local_manager_retries": false
  },
  "request_payload": {
    "...": "backend-normalized internal RunRequest JSON"
  }
}
```

This schema is represented by `ExecutionQueueMessage` in `backend/api_service/runtime/contracts.py`.
`request_payload.model_architecture_id` is part of the durable run contract. The current frontend catalog supports
`energy-development` and `energy-only`; hosted runtimes should validate this against
`model_runtime/edim_model/model_manifest.json -> supported_model_architectures` before execution.
Local retry-policy defaults are configured by
`inputs/runtime_config.json -> jobs.execution_max_attempts` or
`EDIM_JOB_EXECUTION_MAX_ATTEMPTS`. The local worker records the policy but does
not retry model errors; hosted workers can implement retry semantics while
preserving the same payload shape.

Attempt payload schema:

```json
{
  "schema_version": "execution_attempt",
  "execution_id": "<execution id>",
  "run_id": "<run id>",
  "attempt": 1,
  "worker_id": "<worker identity>",
  "status": "running | succeeded | failed | cancelled",
  "started_at": "<ISO timestamp>",
  "heartbeat_at": "<ISO timestamp>",
  "finished_at": "<ISO timestamp or null>",
  "cancellation_requested": false,
  "retryable": false,
  "error": "",
  "message": ""
}
```

Project run diagnostics expose `execution_queue_message`, `execution_attempts`,
`cancellation_requested`, and `worker_id`. Frontend status polling uses the compact
`GET /api/executions/{execution_id}/status` response and does not receive queue messages,
execution attempts, model request bundles, or dataset snapshots.

## Model Runtime Contract

The backend must treat the model as a black box.

Runtime package:

- `model_runtime/edim_model/model_manifest.json`
- `model_runtime/edim_model/dataset_manifest.json`
- `model_runtime/edim_model/cli.py`

Backend sends one `model_run_bundle_v1` JSON bundle. The runtime must:

1. Read the bundle.
2. Emit newline-delimited `runtime_event_v1` events to stdout.
3. Write declared artifacts under the run package layout.
4. Emit a final `result` event with `run_id` and `payload.summary`.

Required commands:

- `python -m edim_model.cli preflight --bundle <bundle>`
- `python -m edim_model.cli run --bundle <bundle>`
- `python -m edim_model.cli catalog ...`

`PYTHONPATH` or the container image must make `model_runtime/` importable before these commands run.

Runtime artifact handoff is now an explicit contract, not an implicit shared-disk assumption.

Configured field:

- `inputs/runtime_config.json -> model_runtime.artifact_handoff_mode`
- Env override: `EDIM_RUNTIME_ARTIFACT_HANDOFF_MODE`
- Run-bundle field: `artifact_handoff.schema_version = runtime_artifact_handoff_v1`
- Runtime catalog field: `GET /api/model-runtimes -> artifact_handoff_mode`

Allowed modes:

- `shared_filesystem`: local default. Runtime writes under `runtime_settings.runs_dir`; API reads declared artifact ids from the same mounted filesystem.
- `worker_staged_upload`: recommended Azure target. Worker/runtime writes to ephemeral or mounted worker disk, then the injected `ArtifactStorageService.publish_run_artifacts(...)` uploads declared artifacts to durable object storage before marking the run terminal.
- `runtime_direct_upload`: future mode for runtimes that upload directly and emit storage references in their final result event.

Current local implementation selects `shared_filesystem` and returns an `artifact_publication` diagnostic in `summary.json`. Azure should implement `ArtifactStorageService.publish_run_artifacts(...)` to upload every declared artifact in `artifact_catalog`, return object-storage references/diagnostics, and keep the public API artifact-id based. Do not expose raw worker filesystem paths to the frontend.

## Artifact Contract

Artifacts are controlled by `inputs/runtime_config.json` under `artifacts.manifest`.

Each artifact has:

- `id`
- `path`
- `producer_stage`
- `kind`
- `retain_on_success`
- `retain_on_failure`
- `embed_in_final_results`
- `embed_in_summary`
- `include_in_project_bundle`
- `expose_download`
- `required_for_report`
- `drop_after_consumed_by`

Public downloads must use artifact ids:

`GET /api/runs/{run_id}/artifacts/{artifact_id}`

The frontend and reports should not infer filesystem paths.

Cloud replacement should map artifact ids to Blob Storage objects and return controlled download responses or signed URLs.

Run bundles and final integrated results include `run_provenance` with stable hashes for the normalized public request,
runtime manifest, runtime config, dataset snapshot, and artifact policy. Backend workers should preserve this object in
logs/results so an executed model can be reproduced from the exact submitted contract.

## Run Package Layout

Every run package has:

- `inputs/`
- `work/`
- `artifacts/`
- `logs/`
- `exports/`

Durable outputs should come from declared artifacts, not ad hoc files.

## Dataset Upload Contract

Dataset uploads are user-scoped.

Local path:

`outputs/dataset_uploads/users/<user_id>/<dataset_id>/`

The model run bundle receives a staged snapshot of the selected user's active datasets in `dataset_manifest`.
The snapshot includes `dataset_staging_v1` metadata so workers know whether inputs were referenced in place,
copied into the run package, or provided as object-storage references.

Cloud replacement should store uploaded files in object storage and persist active-version pointers in a database.
Once a dataset version is referenced by a submitted run snapshot, deletion should be rejected. This protects submitted
run provenance from later active-version changes or user cleanup. Archive/supersede is acceptable; destructive deletion
is not.

## Architecture-Specific Runtime Behavior

Current supported architectures:

- `energy-development`: runs energy solve, bridge preparation, MRIO-direct preparation, development runtime, and integrated results assembly.
- `energy-only`: runs energy solve and integrated results assembly only. Bridge, MRIO-direct, and development stages are intentionally skipped. The final results include an energy-only coupling manifest and no MRIO/development artifacts are exposed.

Hosted workers should validate `request_payload.model_architecture_id` against the runtime manifest before execution and
should not infer development/MRIO behavior from frontend tabs.

## Canonical Frontend Run Flow

The canonical UI/backend flow is project-owned:

1. `GET /api/projects`
2. `POST /api/projects` if the user has no project
3. `POST /api/projects/{project_id}/runs` to create a draft run record
4. `POST /api/projects/{project_id}/runs/{run_id}/submit` to queue execution
5. Poll `GET /api/executions/{execution_id}/status`

Run submission is project-owned only; backend platform integrations should keep
the draft-and-submit flow as the canonical contract.

## Hosted Frontend Compatibility Checklist

A hosted backend used through the frontend `Backend` switch must satisfy this minimum compatibility contract:

- expose the same public route contract as the local backend
- return compatible OpenAPI schemas for the frontend-facing endpoints
- serve `GET /api/session`, `GET /api/system/manifest`, `GET /api/model-runtimes`, `GET /api/scenarios`, project, run, dataset, artifact, report, and export endpoints
- return `schema_version = edim_system_manifest` from `/api/system/manifest`
- return `ok = true` and no `error` diagnostics from `/api/system/manifest`
- list all frontend-used API routes in `manifest.public_endpoints`
- allow the frontend origin through CORS, including required methods, `Content-Type`, and transitional `X-EDIM-User-Id` header if test-user mode is used
- return artifact/report/export download URLs that are valid from the browser
- preserve artifact-id based downloads rather than requiring the frontend to infer storage paths
- preserve user/project/run ownership semantics

Production authenticated downloads should use browser-valid signed URLs or a backend-supported download flow compatible
with the final auth provider. Local/testing downloads can use the current test-user header/query behavior.

## Local Setup and Validation Commands

Local execution requires Python 3.11 because the packaged Calliope runtime depends on `calliope==0.6.10` and
`numpy==1.23.5`.

Initial setup:

```bash
python3.11 -m venv backend/.venv
source backend/.venv/bin/activate
pip3 install -r backend/requirements.txt
pip3 install -r backend/requirements-dev.txt
pip3 install --no-build-isolation -e ./model_runtime
cd frontend && npm install && npm run build
```

Regression checks before handoff or before changing provider seams:

```bash
cd /path/to/energy-development-modeling
source backend/.venv/bin/activate
cd frontend && npm run build
cd ..
PYTHONPATH=backend:model_runtime backend/.venv/bin/python -m pytest backend/tests
```

## Backend Team First Smoke Test

The executable handoff smoke test is:

```bash
cd /path/to/energy-development-modeling
source backend/.venv/bin/activate
python3 scripts/run_local.py --port 8000
```

In a second terminal:

```bash
cd /path/to/energy-development-modeling
source backend/.venv/bin/activate
python backend/tools/backend_handoff_smoke.py \
  --base-url http://127.0.0.1:8000 \
  --user-id undp_analyst \
  --timeout-seconds 900
```

The default smoke execution uses the `energy-only` architecture, the
transmission-only `new_links` energy scenario, and the `dev` time slice. This is
the recommended backend handoff check because it validates user/project/run
ownership, queue submission, model-runtime handoff, events, declared artifacts,
reports, and exports without requiring the MRIO/development layer. Use
`--model-architecture-id energy-development` for a full integration smoke.

The script validates this minimum cloud-handoff sequence:

1. `GET /api/session`
2. `GET /api/system/manifest`, including contract identifiers, provider boundaries, and required endpoints
3. `POST /api/projects`
4. `GET /api/input-datasets`
5. `GET /api/model-runtimes`, including `artifact_handoff_mode`, `dataset_staging_mode`, and `execution_retry_policy`
6. `POST /api/projects/{project_id}/runs/validate`
7. `POST /api/projects/{project_id}/runs`
8. `POST /api/projects/{project_id}/runs/{run_id}/submit`
9. Poll `GET /api/executions/{execution_id}/status`
10. `GET /api/executions/{execution_id}/events`
11. `GET /api/runs/{run_id}/artifacts`
12. Download `summary_json` through `GET /api/runs/{run_id}/artifacts/summary_json` and verify `artifact_publication`
13. Download `integrated_results_json`, `dataset_manifest_json`, `request_bundle_json`, and `results_csv` through artifact ids, verifying queue and retry policy metadata
14. `POST /api/projects/{project_id}/reports` and download the report plus source data
15. `POST /api/runs/{run_id}/export` and download the export bundle
16. `POST /api/projects/{project_id}/exports` and download the project export bundle

If this sequence works in cloud infrastructure, the hosted backend is exercising the same subprocess runtime contract used by local development.

## Current Repository Reference Map

Backend/platform:

- `backend/api_service/main.py`: FastAPI composition root and provider injection point.
- `backend/api_service/api/dependencies.py`: local auth/session dependency replacement point.
- `backend/api_service/api/routers/`: public API route layer.
- `backend/api_service/services/platform_repository.py`: platform metadata repository protocol.
- `backend/api_service/services/sqlite_platform_repository.py`: local SQLite reference implementation.
- `backend/api_service/services/dataset_repository.py`: dataset catalog/upload/version boundary.
- `backend/api_service/services/artifact_storage.py`: artifact/report/export download boundary.
- `backend/api_service/runtime/`: queue, event, artifact, bundle, and runtime contract types.
- `backend/api_service/adapters/subprocess_runtime.py`: local subprocess model-runtime adapter.
- `backend/tools/backend_handoff_smoke.py`: deployment-oriented HTTP acceptance smoke test.

Model runtime:

- `model_runtime/edim_model/model_manifest.json`: black-box runtime manifest.
- `model_runtime/edim_model/architecture_catalog.json`: model-owned UI/runtime architecture catalog.
- `model_runtime/edim_model/dataset_manifest.json`: model-owned dataset contract.
- `model_runtime/edim_model/cli.py`: runtime `preflight`, `catalog`, and `run` command entrypoint.
- `model_runtime/edim_model/core/orchestration.py`: generic stage orchestration.
- `model_runtime/edim_model/core/edim_pipeline.py`: EDIM-specific stage composition.
- `model_runtime/edim_model/modules/`: model-module boundaries for Calliope, MRIO, and planned OSeMOSYS support.
- `model_runtime/model_modules/calliope/`: packaged Calliope-Africa model assets.

Frontend/static shell:

- `frontend/api-client.js`: low-level API target, auth header, upload, and download transport boundary.
- `frontend/app.jsx`: project/workspace UI, high-level API wrapper, manifest compatibility check, and run state handling.
- `frontend/index.html`: static shell, shared styles, script loading, and runtime config loading.
- `frontend/runtime-config.js`: default frontend runtime-config bridge.
- `frontend/runtime-config.local.js`: generated local runtime config; ignored by Git.
- `frontend/scripts/build-static.js`: static bundle validator/builder.
- `frontend/methodology/`: static user-facing methodology page.
- `frontend/hero-visual.jsx` and `frontend/hero-defaults.json`: landing-page visualization.
- `frontend/assets/webp/`: optimized frontend image assets.
- `frontend/assets/photos/`: raw local photo source folder; ignored and not deployed.

Documentation:

- `docs/handoff/BACKEND_HANDOFF.md`: this backend implementation contract.
- `docs/system/SYSTEM_DOCUMENTATION.md`: broader system documentation.
- `docs/model/`: model input/output catalogs.
- `README.md`: local setup and operator entry points.

## Still Local-Only

These are intentionally not production implementations:

- test-header auth
- local SQLite platform metadata store
- local file artifact storage
- in-memory execution queue
- local subprocess runtime adapter

They are replaceable backend seams, not model-science work.

## Azure Migration Checklist

Implement these in order:

1. Replace `get_current_user_context` with Azure/session-backed auth that returns the same `UserContext` shape.
2. Replace the local SQLite reference with an Azure SQL/Cosmos-backed `PlatformRepository`.
3. Implement Blob/object-storage-backed `ArtifactStorageService`.
4. Implement database/object-storage-backed `DatasetRepository`.
5. Implement DB/Blob/event-stream-backed `EventStore`.
6. Replace local `JobManager` queue internals with a durable queue and worker lifecycle.
7. Keep `execution_queue_message`, `execution_retry_policy`, and `execution_attempt` as the queue/worker payload contracts.
8. Expose `/api/system/manifest` unchanged and compare its `contracts` in deployment CI.
9. Run `backend/tools/backend_handoff_smoke.py` in the hosted environment.
10. Keep all frontend downloads descriptor-based: artifact ids, report ids, export ids.
11. Add deployment CI that runs the smoke test and checks OpenAPI schema compatibility.

## Do Not Change During Hosting Migration

- Do not make the backend depend on Calliope or MRIO internals.
- Do not make frontend components infer artifact filenames or filesystem paths.
- Do not split project ownership across multiple users in this version.
- Do not allow uploaded datasets to overwrite repository source files.
- Do not bypass artifact descriptors for downloads.
