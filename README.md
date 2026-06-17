# EDIM MVP

Minimal test-user workbench for integrated energy-development scenario runs.

Full technical documentation is in:

- [System documentation](docs/system/SYSTEM_DOCUMENTATION.md)
- [Backend handoff](docs/handoff/BACKEND_HANDOFF.md)
- [Model I/O catalog](docs/model/EDIM_model_io_catalog.xlsx)

## Data status

The repository now ships with seeded placeholder expert datasets so the full workflow can run end-to-end without empty
tables. These seeded values are internally coherent and materially better than the original 4-row samples, but they are
still placeholders. They should not be treated as project-calibrated evidence.

The local UI prints validation and placeholder diagnostics in the Environment setup panel. `analysis` and `full`
profiles use strict validation automatically; the local reference implementation allows seeded placeholder data so the
full workflow can still be tested end-to-end.

### Placeholder datasets that must be replaced by domain experts

1. `inputs/mario_inputs/employment_intensity.csv`
   - Purpose: direct and total jobs intensities used by the MARIO development runtime.
   - Current status: now populated with seeded placeholder rows covering 5 MARIO regions and 10 energy-relevant sectors.
   - Required action: replace every placeholder row with calibrated `jobs_per_musd_direct` and `jobs_per_musd_total`
     values for each `(mario_region, mario_sector)` combination that can appear in exchange shocks.
   - Completion rule: no placeholder rows remain; `source` cites the real study/database; `reference_year` matches the
     monetary basis of the MARIO table.

2. `inputs/mario_inputs/value_added_intensity.csv`
   - Purpose: GVA and household-income multipliers used by the MARIO development runtime.
   - Current status: now populated with seeded placeholder rows covering 5 MARIO regions and 10 energy-relevant sectors.
   - Required action: replace every placeholder row with calibrated `gva_per_musd_output` and
     `household_income_per_musd_output` values for each `(mario_region, mario_sector)` used by the model.
   - Completion rule: no placeholder rows remain; `source` cites the real evidence base; units are consistent with the
     MARIO monetary year.

3. `inputs/mario_inputs/scenario_assumptions.csv`
   - Purpose: exogenous scenario assumptions used by integrated indicator reporting.
   - Current status: now populated with seeded placeholder rows for the active EDIM scenario keys plus `baseline`.
   - Required action: replace placeholder rows with scenario-specific or `baseline` assumptions. The runtime currently
     consumes matched assumptions for indicator reporting, especially `carbon_price`; unmatched rows are preserved as
     metadata.
   - Completion rule: no placeholder rows remain in the matched scenario/baseline rows; `scenario_key` values are real
     scenario identifiers or `baseline`; units are explicit.

4. `inputs/generated/africa_national_mrio_placeholder_scenarios.json`
   - Purpose: national target-pathway records used when the integrated scenario setup chooses `S1` or `S2`; the MRIO
     shock-mapping selector only controls how those targets become A/Z, E, and Y shock rows.
   - Current status: generated from structured inputs in `inputs/generated/scenario_report_scenarios.json`,
     `inputs/mario_inputs/scenario_report_scenarios.csv`, and the African country seed list. South Africa uses the
     dedicated `ZA-S1`/`ZA-S2` records; every other African country uses `WF-S1`/`WF-S2` Rest-of-Africa assumptions as a
     national placeholder.
   - Required action: replace placeholder country records with expert national MRIO scenario assumptions when available,
     preserving the `S1` full-decarbonization and `S2` national-policy-target archetype structure.
   - Completion rule: each national record has country-specific provenance, no non-South-Africa record depends on
     `WF-S1`/`WF-S2`, and generated diagnostics report zero placeholder national MRIO records.

### Expert-curated dataset that is seeded and usable, but still needs ownership

5. `inputs/mario_inputs/development_indicator_mapping.csv`
   - Purpose: maps modeled metrics to reported development indicators.
   - Current status: seeded with supported driver mappings and fully usable for placeholder runs.
   - The runtime currently computes all seeded rows directly from existing model outputs.

### Geospatial placeholder note

- `frontend/geo/edim_locations_placeholder.geojson` is still a placeholder model-location geometry asset.
- `frontend/geo/countries.geojson` is the consolidated country-boundary file used for country/subregion rendering.
- When explicit subregion polygons are missing, the frontend synthesizes country subregions from centroid points and
  Voronoi partitioning inside parent-country boundaries from `countries.geojson`.
- This is acceptable for exploration, not for final cartography. Replacing these shapes is a GIS task, not an energy
  calibration task.

## How experts should populate the placeholder datasets

1. Start from the active tech-sector mapping.
   - Review `inputs/mario_inputs/calliope_tech_to_mario_sector.csv`,
     `inputs/mario_inputs/capex_sector_split.csv`, and `inputs/mario_inputs/opex_sector_split.csv`.
   - Enumerate the `(mario_region, mario_sector)` pairs that can actually appear in the exchange shocks.

2. Fill intensity tables at that exact resolution.
   - `employment_intensity.csv`: one row per `(mario_region, mario_sector)`.
   - `value_added_intensity.csv`: one row per `(mario_region, mario_sector)`.
   - Avoid region averages unless no sector-specific evidence exists; if averaging is unavoidable, document it in
     `notes`.

3. Use consistent monetary conventions.
   - Intensities are interpreted per `1 MUSD` of modeled output/shock.
   - `reference_year` should match the IO table year or the deflated target year used to build the table.
   - If source data are in local currency, convert them before entry and document the FX/deflator basis in `notes`.

4. Replace placeholder provenance with real provenance.
   - Do not leave `source=placeholder`.
   - Put the actual data source or study name in `source`.
   - Use `notes` for caveats, imputation rules, and any sector aggregation.

5. Populate scenario assumptions against real scenario keys.
   - Use `scenario_key=baseline` for shared defaults.
   - Use an exact EDIM scenario key when an assumption is scenario-specific.
   - Keep `unit` explicit, for example `usd_per_tco2`, `multiplier`, `index`.

6. Validate before treating results as final.
   - In the UI, select `analysis` or `full` profile to run strict validation automatically.
   - The run should pass environment setup without placeholder expert datasets, incomplete MARIO mappings, or invalid
     CAPEX/OPEX share groups.
   - The resulting run-level diagnostics should show `Placeholder rows: 0`.

## Quickstart

### 1) Python version

Use Python `3.11`.

### 2) Install local dependencies

```bash
python3.11 -m venv backend/.venv
source backend/.venv/bin/activate
pip3 install -U pip
pip3 install -r backend/requirements.txt
pip3 install -r backend/requirements-dev.txt
pip3 install --no-build-isolation -e ./model_runtime
```

### 3) Optional frontend bundle check

```bash
cd frontend
npm install
npm run build
cd ..
```

### 4) Run the local app

```bash
source backend/.venv/bin/activate
python3 scripts/run_local.py
```

The runner starts FastAPI with the same project-owned, black-box model handoff path used for backend deployment. It
tries the requested port first (`8000` by default), then automatically picks the next available port if that port is
already in use.

### 5) Open the app

- `http://127.0.0.1:8000/ui/`

If the runner selected another port, use the URL printed in the terminal.

### 6) Queue a run

1. Select or create a project from the dashboard header.
2. Select scenario, target pathway, target year, run profile, and levers.
3. Confirm **Environment setup** is ready.
4. Click **Queue run**.
5. Monitor status in the project run tabs and the environment/operations panel.

The canonical UI flow is project-owned: the frontend creates a draft run under
`/api/projects/{project_id}/runs`, submits that draft, then polls the resulting
`execution_id`.

### 7) Work with project results

After a run succeeds, the same dashboard supports:

- Results mode for the selected run.
- Compare mode across completed runs in the active project.
- Project report generation, including Markdown and structured source-data JSON.
- Single-run and project export bundle downloads.
- Input dataset upload/download plus version activation/deletion.

Project records, runs, reports, exports, and dataset overrides are linked to
the active user. The seeded `admin` test user can see all user-owned projects;
normal test users see only their own records.

### 8) Outputs

Run artifacts are written to:

- `outputs/runs/<run_id>/`

Project reports and export bundles are written to:

- `outputs/platform/reports/`
- `outputs/platform/exports/`

Each generated report has:

- `<report_id>.md`
- `<report_id>.source.json`

The source JSON uses schema `edim_project_report_source_v1` and is built from
project metadata, selected project runs, run summary artifacts, and export
records. It is deliberately basic for now so future report renderers can consume
the same backend source-data contract.

Dataset uploads are written as user-owned immutable versions under:

- `outputs/dataset_uploads/users/<user_id>/<dataset_id>/`

Main run outputs include:

- `inputs/request_bundle.json`
- `inputs/scenario_package.json`
- `artifacts/final/results.csv`
- `artifacts/final/summary.json`
- `artifacts/final/development_impacts.json`
- `artifacts/final/integrated_results.json`
- `exports/report.md`
- `exports/exchange_bundle.zip`

All UI downloads should go through artifact ids or project/report/export
descriptors returned by the API. Do not build new frontend code that infers
filesystem paths.

Project report and export records expose `storage_ref` objects with
provider/object-key metadata. Local development resolves those references to
`outputs/platform/...`; cloud storage should replace them with Blob/container
keys without changing frontend download URLs.

## Handoff Architecture Summary

The handoff structure is intentionally simple. Run `cd frontend && npm run build` to validate and create the compact static bundle in `frontend/dist/` for deployment:

1. **Frontend shell**: renders the basic landing page, projects, the graph-centered
   model workspace, run controls, result panels, compare mode, reports, exports,
   and dataset versions.
2. **Backend API/orchestration**: owns auth context, project/run/report/export
   records, dataset metadata, artifact access, run queueing, and progress/status.
3. **Black-box model runtime**: consumes one run bundle, emits progress events,
   writes declared artifacts, and returns a final summary.

Backend/cloud developers should replace infrastructure providers, not model or
route logic:

- Auth provider: replace `get_current_user_context`.
- Platform repository: replace `PlatformRepository` (the local reference implementation is SQLite-backed).
- Dataset repository: replace `DatasetRepository`.
- Artifact storage: replace `ArtifactStorageService`.
- Runtime event store: replace `EventStore`.
- Queue/worker: replace local `JobManager`/`LocalExecutionQueue` with a durable
  queue and worker using `execution_queue_message`.

Local development now enqueues the same `execution_queue_message` payload that
cloud workers should consume. The payload is persisted in the project run record
as `execution_queue_message` and embedded in each run bundle as `queue_message`.
Each run record also stores `execution_attempts` using `execution_attempt`,
including worker id, heartbeat, cancellation, and terminal attempt status.

Frontend/platform developers should keep using the API client boundary in
`frontend/app.jsx` rather than hard-coding URLs inside components.

The dashboard header includes a runtime target switch for backend testing:

- `Local`: calls the same origin that served the app, normally `http://127.0.0.1:8000`.
- `Backend`: calls the hosted backend URL configured by the frontend runtime environment.

Set the backend target with `EDIM_BACKEND_API_BASE` before starting or building
the frontend. The local runner and frontend build script also read this key from
repo-root `.env` if it is not exported in the shell:

```bash
EDIM_BACKEND_API_BASE=https://your-hosted-backend.example.org python3 scripts/run_local.py --port 8000

cd frontend
EDIM_BACKEND_API_BASE=https://your-hosted-backend.example.org npm run build
```

Switching runtime targets clears the loaded workspace state and reloads session,
projects, datasets, runtime catalogs, and scenario catalogs from the selected API.
If `EDIM_BACKEND_API_BASE` is not set, the Backend side of the switch is disabled.
This variable is a public API URL only; never put secrets in frontend runtime config.
On switch, the frontend first probes `GET /api/system/manifest` and displays
`Contract ok`, `Contract warning`, or `Contract error` in the header. Backend
mode is not used if the manifest is unreachable, has the wrong schema, or reports
failed diagnostics.

## Backend Handoff Smoke Test

Run the handoff smoke test against the same subprocess runtime contract used in deployment:

```bash
source backend/.venv/bin/activate
python3 scripts/run_local.py --port 8000
python backend/tools/backend_handoff_smoke.py --base-url http://127.0.0.1:8000 --timeout-seconds 900
```

The smoke test validates session/user context, the machine-readable system
manifest, project creation, dataset catalog, runtime catalog, environment setup,
draft run creation, run submission, status polling, runtime events, artifact
downloads, report generation, run export, and project export.
By default it uses the lightweight `energy-only` architecture with the
transmission-only `new_links` scenario and `dev` time slice. To run the full
bridge/MRIO integration smoke, add `--model-architecture-id energy-development`.
It still runs the real packaged model, so the timeout needs to allow several
minutes for local Calliope solves.

### 7) Legacy Output Reference

The local run package remains:

- `outputs/runs/<run_id>/`

Primary declared artifacts remain:

- `summary_json`
- `integrated_results_json`
- `development_impacts_json`
- `results_csv`
- `report_markdown`
- `exchange_bundle_zip`

These are resolved through:

- `GET /api/runs/{run_id}/artifacts/{artifact_id}`

Do not depend on physical file paths from frontend or cloud code.

## Refactored runtime boundary

The codebase is now split so TVA can treat the model runtime as a black box more easily:

- `backend/api_service/main.py`
  - Thin FastAPI composition root and route surface.
- `backend/api_service/services/`
  - Backend-facing application services for dataset catalogs and run artifact resolution.
- `backend/api_service/runtime/`
  - Backend execution contracts, queues, event parsing, and run stores.
- `model_runtime/edim_model/contracts.py`
  - Shared artifact registry, run package layout, retention policy loader, and runtime event helpers used by both the
    backend adapter and the executable model package. This keeps artifact behavior in one place without coupling the
    model runtime back to the FastAPI service.
- `backend/api_service/adapters/`
  - Execution adapters. `SubprocessModelRuntime` is the black-box hosting path.
- `model_runtime/edim_model/`
  - Executable model package. It exposes `run` and `preflight` commands through
    `python -m edim_model.cli`.
  - The current real runtime imports packaged model core from `model_runtime/edim_model/core`, not backend API modules.
  - `architecture_catalog.json` is the model-owned architecture graph/result surface catalog served through
    `GET /api/model-runtimes`.
  - Model-specific layers are registered under `model_runtime/edim_model/modules/`: `calliope` owns the executable
    energy layer, `osemosys` declares the planned but disabled OSeMOSYS boundary, and `mrio` owns the
    development-impact layer.
  - Scenario selectors are module-owned. Each model module contributes `scenario_channels` such as
    `scenario.energy_scenario_key`, `scenario.target_scenario_id`, or `scenario.mrio_shock_mapping_id`; `/api/scenarios`
    aggregates those channels for the frontend. Future modules should add their own channels instead of extending a
    global "energy scenario versus MRIO scenario" switch.
- `model_runtime/model_modules/`
  - Bundled model source/data assets by engine. The current Calliope-Africa model is under
    `model_runtime/model_modules/calliope/Calliope-Africa-main/`; future large model assets should be added as sibling
    engine folders instead of repository-root folders.
- `frontend/dist/`
  - Generated static frontend deployment bundle.
- `model_runtime/edim_model/architecture_catalog.json`
  - Canonical model-owned architecture catalog used by both `GET /api/model-runtimes` and the frontend static build.
- `frontend/app.jsx`
  - Single-file dashboard shell containing the UI, API client, workspace artifact helpers, dataset controls, and result
    artifact components. The app intentionally stays consolidated for handoff simplicity while keeping backend
    calls behind the in-file API client boundary.

The platform API is project-owned and run-centric. The frontend should create
drafts through `POST /api/projects/{project_id}/runs`, submit with
`POST /api/projects/{project_id}/runs/{run_id}/submit`, poll
the compact `GET /api/executions/{execution_id}/status`, and download declared outputs through
`GET /api/runs/{run_id}/artifacts/{artifact_id}`. The public run-output contract is
`artifact_catalog`; the backend no longer infers model output paths. Run
outputs and artifact downloads are authorized through the run record owner/admin
policy before files are resolved. The local platform API now uses a replaceable
test-user context, links projects/datasets/runs/reports/exports to an owning
user, rejects unknown test-user headers, and includes an admin test account that
can see all user-owned projects.

### Black-box model hosting contract

The backend now prepares a manifest-driven run bundle and launches the selected model runtime through an executable
adapter.

- Execution identity:
  - `execution_id` identifies the queue/worker attempt.
  - `run_id` is a 32-character hex id allocated at submission and is the stable artifact namespace for results, comparison, exports, and reports.
- Model manifest: `model_runtime/edim_model/model_manifest.json`
  - Declares model id/version, entrypoint, supported schemas, required inputs, declared outputs, stages, and resource
    expectations.
- Dataset manifest: `model_runtime/edim_model/dataset_manifest.json`
  - Declares model-owned input datasets, paths, required status, scope, and upload policy.
- Run bundle: `outputs/runs/<run_id>/inputs/request_bundle.json`
  - Immutable model request containing the backend-normalized user configuration, model manifest snapshot, dataset
    manifest snapshot, artifact policy, runtime settings, and scenario package content where available.
- Runtime events: `outputs/runs/<run_id>/logs/runtime_events.jsonl`
  - JSONL event stream with `runtime_event_v1` objects for progress, warnings, errors, and final result emission.
Default runtime mode is configured in `inputs/runtime_config.json` under:

```json
{
  "model_runtime": {
    "mode": "subprocess",
    "artifact_handoff_mode": "shared_filesystem",
    "dataset_staging_mode": "copy_to_run",
    "manifest_path": "./model_runtime/edim_model/model_manifest.json",
    "dataset_manifest_path": "./model_runtime/edim_model/dataset_manifest.json"
  }
}
```

`artifact_handoff_mode` is part of the backend system manifest:

- `shared_filesystem`: local default, where runtime artifacts stay under `outputs/runs/<run_id>`.
- `worker_staged_upload`: recommended Azure target, where the worker uploads declared artifacts through the injected artifact storage provider before terminal status.
- `runtime_direct_upload`: reserved for future runtimes that publish directly to object storage.

Completed runs include `artifact_publication` diagnostics in `summary.json` so deployment teams can confirm how artifacts were handed from the model runtime to the API/download layer.

`dataset_staging_mode` controls how input datasets are handed to the runtime:

- `copy_to_run`: local default, where inputs are copied into `inputs/datasets/<dataset_id>/` in the run package before execution.
- `reference`: development-only mode where the run bundle references resolved active input paths.
- `object_reference`: cloud-provider mode for durable object-storage references.

Every run bundle includes `dataset_manifest.dataset_staging.schema_version = dataset_staging_v1` plus per-dataset staging status, storage references, file hashes, and sizes where available.

For cloud deployment, the backend should keep the same interface and replace only the adapter implementation:

- Local development: `SubprocessModelRuntime`
- Container worker: future `ContainerModelRuntime`
- Azure Batch / Kubernetes / queue worker: future `RemoteJobModelRuntime`

The configured local platform store is SQLite (`storage.platform_store_backend = sqlite` in `inputs/runtime_config.json`). It stores project/run/report/export metadata transactionally under `outputs/platform/platform.sqlite3`, keeps large artifacts on disk, and imports existing JSON indexes when the SQLite database is first created. There is no active JSON repository path; hosted deployments should replace `PlatformRepository` with a managed database implementation rather than adding another local persistence mode.

Backend provider injection is explicit through `create_app(settings=..., platform_repository=..., artifact_storage=..., dataset_repository=..., event_store=..., job_manager=...)`. The local defaults are filesystem plus SQLite metadata; hosted deployments should inject cloud database, Blob/object-storage, runtime event, and durable queue providers at that composition root.


### Versioned input dataset overrides

Input dataset uploads are stored as user-owned versioned overrides instead of overwriting repository files. Uploads are written under `outputs/dataset_uploads/users/<user_id>/<dataset_id>/`, with active versions recorded in that user folder. Dataset APIs are intentionally user-scoped, not project-scoped. The run bundle receives a staged snapshot of the selected user’s active datasets through `dataset_manifest`, so one user’s uploaded inputs do not silently affect another user’s run. Project exports include uploaded dataset files referenced by exported run snapshots under `datasets/users/<user_id>/...`, making exported workspaces reproducible even when user overrides are outside the run directory. The upload API validates file type, size, parseability, and CSV headers before activating a version. Versions can be listed, reactivated, filtered in the dataset catalog, and deleted through the API.

The route layer uses `DatasetRepository` for catalog, upload, version, active-pointer, download, and runtime dataset staging behavior. Azure can replace this provider without changing the model runtime contract.

### Local platform APIs for handoff

The local reference implementation exposes platform endpoints for TVA/backend integration:

- `GET /api/session`
- `GET /api/system/manifest`
- `GET /api/projects`
- `POST /api/projects`
- `GET /api/projects/{project_id}`
- `PATCH /api/projects/{project_id}`
- `DELETE /api/projects/{project_id}`
- `GET /api/projects/{project_id}/runs`
- `POST /api/projects/{project_id}/runs`
- `GET /api/projects/{project_id}/runs/{run_id}`
- `GET /api/projects/{project_id}/runs/{run_id}/diagnostics`
- `PATCH /api/projects/{project_id}/runs/{run_id}`
- `POST /api/projects/{project_id}/runs/{run_id}/submit`
- `POST /api/projects/{project_id}/runs/{run_id}/duplicate`
- `DELETE /api/projects/{project_id}/runs/{run_id}`
- `GET /api/runs/{run_id}/logs`
- `POST /api/runs/{run_id}/export`
- `GET /api/projects/{project_id}/reports`
- `POST /api/projects/{project_id}/reports`
- `GET /api/projects/{project_id}/exports`
- `POST /api/projects/{project_id}/exports`
- `GET /api/scenarios`
- `GET /api/input-datasets?layer=<layer>&input_property=<text>&role=<text>`
- `GET /api/model-runtimes`
- `POST /api/projects/{project_id}/runs/validate`
- `GET /api/input-datasets/{dataset_id}/versions`
- `POST /api/input-datasets/{dataset_id}/versions/{version_id}/activate`
- `DELETE /api/input-datasets/{dataset_id}/versions/{version_id}`

The frontend uses the project-owned run flow: create/find a project, create a draft run under that project, submit that
run, and poll by `execution_id`.

Authentication is still a local test shim, not production auth. The frontend sends `X-EDIM-User-Id` for one of the seeded test users from `GET /api/session`; unknown test-user IDs are rejected rather than mapped to an account. Production should replace only this session/dependency layer with authenticated user context while preserving the same owner-user fields, run-artifact authorization, and admin visibility behavior.

The frontend API client exposes a small auth-provider seam through `window.EDIM_API_CLIENT.setAuthProvider(...)`. The default provider writes the local test-user header, but a hosted shell can replace it with a provider that returns bearer-token or managed-session headers without changing dashboard components.

### Run package layout

Each run now uses a stable package layout under `outputs/runs/<run_id>/`:

- `inputs/`
  - Request bundle, model manifest snapshot, dataset manifest snapshot, artifact policy, scenario package, and staged
    scenario-side manifests.
- `work/`
  - Temporary runtime-only files that do not need to be exposed.
- `artifacts/`
  - Declared intermediate and final artifacts.
- `logs/`
  - Runtime JSONL events and model logs such as MARIO execution logging.
- `exports/`
  - Durable export bundles and generated reports.

### Artifact retention policy

- `inputs/runtime_config.json`
  - The `artifacts.manifest` section is now the control surface for retention and exposure policy.
- Each artifact declares:
  - `path`
  - `producer_stage`
  - `kind`
  - `retain_on_success`
  - `retain_on_failure`
  - `embed_in_summary`
  - `embed_in_final_results`
  - `include_in_project_bundle`
  - `expose_download`
  - `required_for_report`
  - optional `drop_after_consumed_by`

The runtime registry uses that manifest to decide where files are written and which artifacts are exposed back through
the run API.

## Recommended workflow for final runs

1. Run `dev` with strict validation on to catch configuration/data issues cheaply.
2. Once strict `dev` passes, run `analysis` or `full`.
3. Review the run-level diagnostics in the UI before using the outputs externally.

## New model quality diagnostics

The workbench now exposes a synthesized model-quality layer so users do not have to infer trustworthiness from raw
warnings alone.

- `Model quality`
  - Combines placeholder usage, mapping coverage, warning count, CO2 method consistency, and
    pool energy-balance residuals into a score and status.
  - Status values:
    - `production_ready`
    - `analyst_review`
    - `exploratory_only`

- `Metric resolution`
  - Shows the model-native resolution of each major output and what the filtered UI can safely display.
  - This is the main guardrail against country-level interpretation of region-only development outputs.

- `System structure`
  - Reports renewable / zero-carbon / fossil generation shares and generation by reporting group.

- `Emissions and energy balance`
  - Physical emissions now prefer direct `cost[costs=co2]` accounting when available.
  - The backend also computes pool-level balance residuals so generation, trade, demand, and unmet demand can be
    checked for consistency.

When reviewing a run, treat the following as blocking for decision-grade use:

1. `Model quality = exploratory_only`
2. `Placeholder rows > 0`
3. Large pool balance residuals or CO2 method gaps

## Dashboard UI structure

The frontend is now organized as an architecture-driven dashboard rather than a long scrolling report:

1. Model architecture catalog: `GET /api/model-runtimes -> architecture_catalog` defines selectable architecture graphs.
2. Setup canvas: the selected architecture supplies the visible boxes, arrows, dataset inputs, result tabs, and output artifacts.
3. Results canvas: `energy-development` shows `Overview`, `Energy system`, `Development`, and `Method`; `energy-only` hides MRIO/development tabs and artifacts.

The design intent is to make the model architecture itself the primary UI. Adding a future architecture should mostly
mean adding a new runtime-owned catalog entry plus backend/runtime support for the same `model_architecture_id`.

## Unified Scenario Architecture

EDIM now uses one integrated scenario package per run. Users configure:

- `model_architecture_id`: the selected model graph/result surface, currently `energy-development` or `energy-only`.
- `scenario.energy_scenario_key`: the Calliope energy pathway.
- `scenario.target_scenario_id`: the integrated target pathway id, currently `S1` for full decarbonization or `S2` for national policy target.
- `scenario.target_year`: the year used for structured MRIO assumptions.
- `run_profile` and levers.

The frontend sends only the compact run configuration. The backend derives `project_id`, strict-validation behavior,
placeholder-data policy, dataset snapshots, runtime settings, model manifests, artifact policy, queue metadata, and
execution attempts.

The backend routes that package through architecture-specific channels:

- Energy channel: `IntegratedScenarioPackage -> Calliope adapter -> Calliope solve -> bridge exchange CSVs`.
- MRIO-direct channel: `IntegratedScenarioPackage target pathway -> MRIO shock mapping adapter -> heuristic A/Z, E, Y inputs`.
- Energy-only architecture: energy solve and integrated results assembly run; bridge, MRIO-direct, and development
  runtime stages are skipped and no MRIO/development artifacts are exposed.

Each submitted run bundle and final integrated results payload includes `run_provenance`, with hashes for the normalized
request, runtime manifest, runtime config, dataset snapshot, and artifact policy. This is the audit handle backend teams
should preserve when moving execution to queue workers or containers.

For now, the system keeps bridge-derived and MRIO-direct outputs side by side. If both channels overlap, headline
development totals default to the Calliope bridge-derived values. The structured MRIO-direct effects are retained as
diagnostic/secondary outputs under the MRIO-direct heuristic method.

Run artifacts include:

- `scenario_package.json`
- `scenario/energy_input_manifest.json`
- `scenario/report_scenario_reference.json`
- `scenario/geography_alignment.json`
- `scenario/mrio_direct_inputs.json`
- `scenario/mrio_direct_shocks.csv`

Structured MRIO scenario targets live in `inputs/generated/scenario_report_scenarios.json`, with the analyst-readable
CSV extraction at `inputs/mario_inputs/scenario_report_scenarios.csv`. The backend also generates
`inputs/generated/africa_national_mrio_placeholder_scenarios.json`, which expands the UI-level `S1`/`S2` selection to
one national MRIO record per African country. South Africa uses the dedicated structured `ZA` records; other African
countries use Rest-of-Africa assumptions until expert national records are supplied. Caches are keyed by structured input
SHA/provenance and are rebuilt automatically when those structured inputs change.

Geography alignment is controlled by `inputs/scenario_geography_mapping.csv`. National target scenarios fan out to mapped
Calliope subnational locations for the same parent country. Regional MRIO scenarios fan out to mapped country/location
rows. Mismatches only block when both sides expose incompatible subnational groupings.

## Useful commands

### Unit tests

```bash
PYTHONPATH=backend:model_runtime backend/.venv/bin/python -m pytest backend/tests/test_mvp.py -q
```

### Smoke checks

```bash
source backend/.venv/bin/activate
python3 backend/tools/smoke_check.py
python3 backend/tools/smoke_check.py --run-model
python3 backend/tools/model_readiness_audit.py --scenario new_links
python3 backend/tools/model_readiness_audit.py --scenario new_links --run-id <run_id>
```

Backend handoff smoke test against an already-running backend:

```bash
source backend/.venv/bin/activate
python3 scripts/run_local.py --port 8000
python backend/tools/backend_handoff_smoke.py --base-url http://127.0.0.1:8000 --timeout-seconds 900
```

This validates user/session context, `/api/system/manifest`, project-owned run
submission, runtime events, artifact-id downloads, report generation, and export
bundle downloads.

### Docker

```bash
docker compose up --build
```
