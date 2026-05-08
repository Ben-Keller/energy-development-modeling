# EDIM System Documentation

This document is the full technical reference for the EDIM MVP in this repository.

- Repository root: this repository checkout.
- Purpose: run integrated energy-development scenarios using Calliope-Africa + MARIO-style economic propagation.
- Primary runtime: FastAPI backend + packaged static React frontend + black-box model runtime.

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Repository Structure](#2-repository-structure)
3. [End-to-End Runtime Flow](#3-end-to-end-runtime-flow)
4. [Backend Components](#4-backend-components)
5. [API Reference](#5-api-reference)
6. [Scenario and Model Layering](#6-scenario-and-model-layering)
7. [Temporal Resolution and Run Profiles](#7-temporal-resolution-and-run-profiles)
8. [Input Controls](#8-input-controls)
9. [Top-level controls (`inputs/`)](#top-level-controls-inputs)
10. [MARIO controls (`inputs/mario_inputs/`)](#mario-controls-inputsmario_inputs)
11. [Lever Application and Override Patching](#9-lever-application-and-override-patching)
12. [Solver Handling and HiGHS Transition](#10-solver-handling-and-highs-transition)
13. [Summary and Diagnostics Outputs](#11-summary-and-diagnostics-outputs)
14. [Calliope -> MARIO Bridge Design](#12-calliope---mario-bridge-design)
15. [MARIO Runtime Outputs](#13-mario-runtime-outputs)
16. [Development Engine Modes](#14-development-engine-modes)
17. [Integrated Results Payload](#15-integrated-results-payload)
18. [Job System Details](#16-job-system-details)
19. [Frontend Behavior and UX](#17-frontend-behavior-and-ux)
20. [Artifact Layout and Contracts](#18-artifact-layout-and-contracts)
21. [Environment Setup Checks Semantics](#19-environment-setup-checks-semantics)
22. [Configuration Reference](#20-configuration-reference)
23. [Running the System](#21-running-the-system)
24. [Validation and Testing](#22-validation-and-testing)
25. [Operational Caveats](#23-operational-caveats)
26. [Current Example Run Snapshot](#24-current-example-run-snapshot)

## 1) System Overview

EDIM executes a coupled pipeline:

1. Build and solve a Calliope-Africa energy optimization scenario.
2. Summarize energy outputs and diagnostics.
3. Convert Calliope outputs into MARIO exchange shock tables.
4. Run built-in MARIO IO runtime to estimate development effects (jobs, GVA, income proxy).
5. Build integrated indicators and export artifacts for UI and downloads.

### Main Modules

- Backend API and orchestration: `backend/api_service/`
- Frontend UI/source and static bundle: `frontend/` (`npm run build` writes `frontend/dist/`)
- Runtime input controls: `inputs/`
- Run artifacts: `outputs/`
- Packaged model runtime: `model_runtime/edim_model/`
- Shared runtime contracts: `model_runtime/edim_model/contracts.py`
- Energy model source: `model_runtime/model_modules/calliope/Calliope-Africa-main/`

## 2) Repository Structure

```text
edim-calliope-africa/
  backend/
    api_service/
      main.py
      jobs.py
      schemas.py
      settings.py
    tests/
      test_mvp.py
    tools/
      smoke_check.py
      generate_refinement_visuals.py
  model_runtime/
    edim_model/
      contracts.py
      cli.py
      model_manifest.json
      dataset_manifest.json
      architecture_catalog.json
      core/
    model_modules/
      calliope/
        Calliope-Africa-main/
          model.yaml
          overrides.yaml
          *.yaml
  frontend/
    index.html
    app.jsx
    geo/countries.geojson
  inputs/
    lever_mappings.csv
    scenario_metadata.csv
    development_model.csv
    mario_inputs/
      *.csv
  outputs/
    runs/
    figures/
```

## 3) End-to-End Runtime Flow

1. UI requests `/api/model-runtimes` for architecture, scenario channels, datasets, and declared outputs, then validates
   the current configuration with `POST /api/projects/{project_id}/runs/validate`. `/api/scenarios` remains available as
   the scenario-catalog-only endpoint for integrations that do not need the full runtime catalog.
2. UI creates a draft run with `POST /api/projects/{project_id}/runs`.
3. UI submits the draft with `POST /api/projects/{project_id}/runs/{run_id}/submit`.
4. `JobManager` creates the execution record, enqueues the run, and launches the configured runtime adapter.
5. `model_runtime.edim_model.local_runtime.execute_bundle` converts the run bundle into runtime settings/request objects
   and calls `model_runtime.edim_model.core.runner.run_model_synchronously`.
6. The generic stage runner in `model_runtime.edim_model.core.orchestration` executes the EDIM pipeline stages:
   - `environment_setup`
   - `cleanup`
   - `scenario_prepare`
   - `energy_input_prepare`
   - `build_model`
   - `solve_energy`
   - `write_artifacts`
   - `build_summary`
   - `bridge_prepare`
   - `mrio_direct_prepare`
   - `development`
   - `build_integrated`
   - `complete`
7. Artifacts are written to `outputs/runs/<run_id>/`.
8. UI polls `/api/executions/{execution_id}/status` and loads run outputs through artifact ids.

The runner delegates model-specific execution through `model_runtime/edim_model/modules/`:

- `calliope.py`: executable energy model module selected by `energy_model_engine=calliope`.
- `osemosys.py`: planned energy module boundary. It is visible as a disabled catalog option but is not listed as a
  supported executable engine until an OSeMOSYS package is added.
- `mrio.py`: executable development module selected by `development_engine=mario` and responsible for bridge-derived
  plus MRIO-direct development outputs.
- Each module also declares its scenario channels. `/api/scenarios` aggregates module-owned channels into one catalog,
  so future model modules can add selectors without turning the API into a list of hard-coded EDIM fields.

## 4) Backend Components

### `main.py`

- FastAPI app wiring.
- CORS setup.
- Frontend static mount at `/ui`.
- API route definitions for session/projects, scenarios, environment setup, datasets, run execution, and run artifacts.

### `jobs.py`

- In-memory queue + worker thread.
- Subprocess run execution for robust cancellation.
- Job deduplication by request fingerprint.
- Queue capacity enforcement.
- Progress/stage heartbeat and status transitions.

### Backend and model boundary

Backend API code no longer exposes model-core compatibility shims. Model-specific implementation lives under
`model_runtime/edim_model/core`; backend tests/tools import that package directly when they need model-level behavior.
The backend orchestration layer should continue to invoke the model through the runtime adapter/CLI boundary for hosted
execution.

### Model runtime orchestration

Generic orchestration and EDIM-specific model stages are deliberately separated:

- `model_runtime/edim_model/core/orchestration.py`: model-agnostic stage primitives. It only knows how to execute ordered
  stages with progress and cancellation checks.
- `model_runtime/edim_model/core/edim_pipeline.py`: EDIM-specific stage sequence. It prepares scenarios, calls selected
  energy/development modules, builds summaries, and writes declared artifacts.
- `model_runtime/edim_model/local_runtime.py`: black-box bundle executor used by the CLI. Its primary entrypoint is
  `execute_bundle`.
- `model_runtime/edim_model/core/runner.py`: shared model-core helpers plus the model-neutral
  `run_model_synchronously` entrypoint. New model architectures should not add another large inline runner here; they
  should add a pipeline module and reuse the generic orchestrator.
- `model_runtime/edim_model/modules/`: model-stage implementations selected by module registry.

### `summarize.py`

Builds summary and diagnostics payloads:

- Generation, capacity, new capacity, cost, emissions summaries.
- Reliability diagnostics (`carrier_con`, `unmet_demand`).
- Inter-pool trade diagnostics.
- Physical emissions via generation × CO2 factor.
- Cost decomposition by component/class.

### `mario_runtime.py`

Built-in MARIO-style runtime:

- Validates required `inputs/mario_inputs` files.
- Loads investment/operating shocks.
- Applies employment and value-added intensities by region/sector.
- Uses exact, region mean, and global mean intensity matching tiers.
- Returns totals and disaggregations with uncertainty bounds.

### `integrated.py`

- Validates integrated payload schema.
- Builds integrated metrics and confidence metadata.
- Generates report markdown and exchange bundle zip.

### `levers.py`

- Loads lever mappings from CSV.
- Resolves tech wildcard mappings.
- Applies CAPEX/fuel/carbon lever patch generation.

### Runtime scenario catalog

- The packaged runtime exposes the module-driven scenario catalog through
  `model_manifest.json -> catalog_entrypoint`; the backend calls this as a
  black-box catalog command through `ModelCatalogProvider`.
- Scenario selectors are exposed only through generic `scenario_channels[]`.
  The frontend derives current EDIM selectors from each channel's `config_key`,
  options, and defaults instead of using model-specific top-level arrays.
- The Calliope module reads `overrides.yaml` plus `scenario_metadata.csv`; the MRIO module reads structured scenario-target
  pathways and shock mapping assumptions.

### `settings.py`

Environment-driven settings:

- Paths, solver, run profile windows, time limits.
- Summary row caps.
- Queue/history/retention controls.
- Development engine mode and MARIO runtime options.

### `schemas.py`

Pydantic models for request/response contracts:

- `PublicRunConfiguration`, `RunRequest`, `LeverValues`, `RunExecutionInfo`, `RunSummary`, etc.
- `PublicRunConfiguration` is the compact frontend contract.
- `RunRequest` is the backend-normalized internal execution contract used after route-boundary mapping.

## 5) API Reference

The main backend handoff endpoints now expose explicit OpenAPI response schemas for dataset catalogs, environment setup,
the machine-readable system manifest, model runtime catalog, run event streams, and run artifact listings. The schema references are tested in
`backend/tests/test_mvp.py` so backend/frontend contract drift is visible.

### Health/UI

- `GET /health`
- `GET /` (redirects to `/ui/` when frontend exists)
- `GET /ui/` (static frontend)

### Scenario and Environment

- `GET /api/scenarios`
- `GET /api/system/manifest`
- `GET /api/model-runtimes`
- `POST /api/projects/{project_id}/runs/validate`

### Runs

- `GET /api/runs?limit=<n>`
- `GET /api/executions/{execution_id}/status`
- `GET /api/executions/{execution_id}/events`
- `POST /api/executions/{execution_id}/cancel`
- `GET /api/projects/{project_id}/runs`
- `POST /api/projects/{project_id}/runs`
- `GET /api/projects/{project_id}/runs/{run_id}`
- `GET /api/projects/{project_id}/runs/{run_id}/diagnostics`
- `PATCH /api/projects/{project_id}/runs/{run_id}`
- `POST /api/projects/{project_id}/runs/{run_id}/submit`

Frontend run creation and draft updates use this compact payload:

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
  "levers": {}
}
```

The backend derives project ownership, strict validation, placeholder-data policy, dataset snapshots, runtime settings,
model manifests, artifact policy, queue metadata, and execution attempts. Frontend-facing run endpoints return compact
rows with `configuration`; detailed internals remain behind `/diagnostics`, logs, and artifact endpoints.
- `POST /api/projects/{project_id}/runs`
- `GET /api/projects/{project_id}/runs/{run_id}`
- `PATCH /api/projects/{project_id}/runs/{run_id}`
- `POST /api/projects/{project_id}/runs/{run_id}/submit`
- `POST /api/projects/{project_id}/runs/{run_id}/duplicate`
- `DELETE /api/projects/{project_id}/runs/{run_id}`
- `GET /api/runs/{run_id}/logs`
- `POST /api/runs/{run_id}/export`

### Run Outputs

- `GET /api/runs/{run_id}/summary`
- `GET /api/runs/{run_id}/development`
- `GET /api/runs/{run_id}/integrated`
- `GET /api/runs/{run_id}/artifacts`
- `GET /api/runs/{run_id}/artifacts/{artifact_id}`

All run-output routes are resolved through the run record first. A user can read a run summary, result payload, artifact catalog, or artifact file only when they own the run or have the admin role.

### Local Platform Artifacts

- `GET /api/projects/{project_id}/reports`
- `POST /api/projects/{project_id}/reports`
- `GET /api/projects/{project_id}/reports/{report_id}/download`
- `GET /api/projects/{project_id}/exports`
- `POST /api/projects/{project_id}/exports`
- `GET /api/projects/{project_id}/exports/{export_id}/download`

## 6) Scenario and Model Layering

### Base Calliope model

File: `model_runtime/model_modules/calliope/Calliope-Africa-main/model.yaml`

- Imports technology, location constraints, and transmission link files.
- Defines base temporal subset and run settings.

### Scenario catalog

File: `model_runtime/model_modules/calliope/Calliope-Africa-main/overrides.yaml`

Current scenario keys:

- `new_links`
- `2040_STEPS_old_gen_old_links`
- `2040_AC_old_gen_old_links`
- `2040_STEPS_old_links`
- `2040_AC_old_links`
- `2040_STEPS_old_gen`
- `2040_AC_old_gen`
- `2040_STEPS`
- `2040_AC`
- `2040_STEPS_policy`
- `2040_AC_policy`

Scenario building blocks:

- `new_demand_STEPS.yaml`
- `new_demand_AC.yaml`
- `new_generation.yaml`
- `new_gen_loc.yaml`
- `new_transmission_links.yaml`
- `policy.yaml`

### Selector logic in UI

The frontend presents a hierarchical selector:

1. Main scenario family:
   - `2040 pathway scenarios`
   - `Transmission-only scenario`
2. Demand pathway (`STEPS` or `AC`) for 2040 family.
3. Energy build package (generation/transmission legacy/new combinations).
4. Policy package (`Standard` / `Policy push` when available).

This resolves to one concrete scenario key in `overrides.yaml`.

## 7) Temporal Resolution and Run Profiles

### Base model timeline

- Timeseries in `model_runtime/model_modules/calliope/Calliope-Africa-main/Timeseries`.
- Backend currently infers runtime year from profile subset start (default year 2019).

### Runtime profiles

- `dev`
  - subset: `EDIM_DEV_SUBSET_START` to `EDIM_DEV_SUBSET_END`
  - default solver time limit: `EDIM_DEV_SOLVER_TIME_LIMIT_SECONDS=3600`
- `analysis`
  - subset: `EDIM_ANALYSIS_SUBSET_START` to `EDIM_ANALYSIS_SUBSET_END`
  - default solver time limit: `EDIM_ANALYSIS_SOLVER_TIME_LIMIT_SECONDS=14400`
- `full`
  - no subset patch from runtime profile
  - allowed only if `EDIM_ALLOW_FULL_YEAR=true`

## 8) Input Controls

## Top-level controls (`inputs/`)

### `scenario_metadata.csv`

Columns include:

- `key`, `title`, `description`, `tags`
- `policy_question`, `expected_tradeoff`, `user_label`
- optional preset levers:
  - `demand_multiplier`
  - `renewables_capex_multiplier`
  - `fossil_fuel_price_multiplier`
  - `carbon_price_usd_per_tco2`

### `lever_mappings.csv`

Defines:

- renewable and fossil tech pattern groups
- mapping paths for CAPEX/fuel/carbon lever patching

### `development_model.csv`

Dotted parameter paths for MARIO uncertainty config, e.g.:

- `mario.uncertainty_relative_bounds.jobs_total`

## MARIO controls (`inputs/mario_inputs/`)

Required by runtime health:

- `calliope_tech_to_mario_sector.csv`
- `capex_sector_split.csv`
- `opex_sector_split.csv`
- `calliope_cost_to_mario_account.csv`
- `country_to_pool.csv`
- `employment_intensity.csv`
- `value_added_intensity.csv`

Also present:

- `exchange_output_schema.csv`
- `development_indicator_mapping.csv`
- `scenario_assumptions.csv`

## 9) Lever Application and Override Patching

At run start, backend constructs an override patch that merges:

1. Solver/run profile settings.
2. Runtime subset-time window for `dev` and `analysis`.
3. Lever-based CAPEX/fuel/carbon path updates.

Additionally, `demand_multiplier` is applied directly to `Demand_power` resource profiles.

Patch is written to:

- `outputs/runs/<run_id>/ui_override_patch.yaml`

## 10) Solver Handling and HiGHS Transition

Runtime solver selection (`EDIM_SOLVER=highs` default):

1. Prefer Pyomo `appsi_highs` if available.
2. Otherwise use CLI `highs` if found.
3. Emit warning if no usable HiGHS backend is available.

Compatibility hardening includes patching around Calliope 0.6 + Pyomo HiGHS option handling to avoid known incompatible kwargs.

## 11) Summary and Diagnostics Outputs

`summary.json` includes:

- `generation_by_tech`
- `capacity_by_tech`
- `new_capacity_by_tech`
- `system_cost`
- `emissions`
- `summary_diagnostics`
- `development_impacts`
- `integrated_results`
- `coupling_manifest`
- `warnings`

Diagnostics in `summary_diagnostics` include:

- `run_metadata`
- `reliability`
- `trade_matrix`
- `physical_emissions`
- `cost_decomposition`

## 12) Calliope -> MARIO Bridge Design

EDIM now prepares one integrated scenario package before model execution:

`IntegratedScenarioPackage -> energy adapter -> Calliope -> bridge exchange CSVs`

and in parallel:

`IntegratedScenarioPackage -> MRIO-direct adapter -> structured A/Z, E, and Y scenario-target inputs`

The two channels are intentionally kept separate in v1. Bridge-derived Calliope results remain authoritative for
headline development totals when bridge and MRIO-direct effects overlap. MRIO-direct effects are emitted as
MRIO-direct heuristic diagnostics until exact MARIO matrix shock execution replaces the heuristic layer.

The bridge writes exchange artifacts under `outputs/runs/<run_id>/artifacts/intermediate/exchange/` and exposes them only through artifact descriptors.

Primary extraction order:

- Investment: `cost_investment`
- OPEX/fuel: `cost_om_annual`, `cost_om_prod`, `cost_om_con`
- Fallback OPEX path: `cost_var` split by tech class into fuel vs non-fuel

Mapping and splitting:

- Tech mapping: `calliope_tech_to_mario_sector.csv`
- CAPEX split: `capex_sector_split.csv`
- OPEX split: `opex_sector_split.csv`
- Geo mapping: `country_to_pool.csv`

Generated exchange CSVs:

- `calliope_component_activity.csv`
- `investment_shocks.csv`
- `operating_shocks.csv`
- `energy_service_balance.csv`
- `prices_and_taxes.csv`

Schema check:

- validated against `exchange_output_schema.csv`

Fallback bridge behavior:

- If no tech-level component rows are available, fail the bridge preparation stage with a data-readiness error.
- If still empty, runtime returns zero development impacts with explicit diagnostics.

## 13) MARIO Runtime Outputs

`development_impacts.json` structure:

- `method`: currently `mario_io_runtime_v1` when MARIO path runs
- `inputs`: investment/operating/total shocks
- `bridge`: bridge-derived Calliope-to-MARIO development payload
- `mrio_direct`: structured MRIO-direct heuristic payload
- `selected_totals`: headline totals, currently defaulting to bridge-derived values on overlap
- `combined_totals`: diagnostic bridge + MRIO-direct sum, not the default headline value
- `overlap_diagnostics`: source-precedence and overlap notes
- `totals`:
  - `jobs_direct`
  - `jobs_total`
  - `gva_total_musd`
  - `household_income_proxy_musd`
- `uncertainty.totals_bounds`
- `by_region.records`
- `by_supplier_sector.records`
- `by_region_supplier.records`
- `diagnostics`:
  - shock rows used
  - intensity match tier counts
  - year

## 14) Development Engine Mode

Configured via `EDIM_DEVELOPMENT_ENGINE`:

- `mario`: use MARIO runtime; fail if MARIO path errors.

MARIO uncertainty bounds are controlled through `inputs/development_model.csv`.

## 15) Integrated Results Payload

`integrated_results.json` includes:

- `model_architecture_id` in the request/scenario provenance, currently `energy-development` or `energy-only`
- `scenario.energy_scenario_key`
- `scenario.target_scenario_id` (backend-normalized to `mrio_scenario_id` inside the model request bundle)
- `scenario.target_year`
- `scenario_package`
- `run_provenance`
  - normalized public request hash
  - runtime manifest hash
  - runtime config hash
  - dataset snapshot hash
  - artifact policy hash
- `integrated_overview.metrics`
  - system cost
  - physical emissions
  - unserved energy share
  - jobs
  - GVA
  - import leakage
- `development_drivers`
- `regional_development`
- `development_confidence`
  - coupling mode
  - mapping coverage/unmapped technologies
  - warning count
  - MARIO runtime diagnostics
- `development_uncertainty`
- `source_channels`
  - `bridge`
  - `mrio_direct`
  - `selected_totals`
  - `combined_totals`
  - `overlap_diagnostics`
- `scenario_provenance`

Structured MRIO scenario targets are stored at `inputs/generated/scenario_report_scenarios.json`, with an
analyst-readable CSV extraction at `inputs/mario_inputs/scenario_report_scenarios.csv`. Geography fan-out is controlled
by `inputs/scenario_geography_mapping.csv`.

## 16) Job System Details

- Queue and history are in-memory.
- Subprocess workers provide strong cancel semantics.
- Active statuses: `queued`, `running`.
- Terminal statuses: `succeeded`, `failed`, `cancelled`.
- Deduplication can reuse active or successful prior jobs with identical fingerprints.

Capacity and dedupe controls:

- `EDIM_JOB_QUEUE_CAPACITY`
- `EDIM_JOB_DEDUPE_ENABLED`
- `EDIM_JOB_HISTORY_LIMIT`

## 17) Frontend Behavior and UX

UI file set:

- `frontend/index.html`
- `frontend/app.jsx`
- `frontend/dist/` generated by `npm run build`
- `model_runtime/edim_model/architecture_catalog.json`
- `frontend/geo/countries.geojson`

Core UX flow:

1. Select or create a project.
2. Select a model architecture, then configure scenario setup and lever tuning.
3. Review environment setup checks.
4. Queue a project-owned run.
5. Monitor active execution with stage/progress/heartbeat.
6. Inspect selected run outputs.
7. Compare completed project runs.
8. Generate reports and export bundles.

Notable UI behaviors:

- `GET /api/model-runtimes -> architecture_catalog` is the frontend source of truth for selectable model architectures. The backend serves model-owned metadata declared by `model_runtime/edim_model/model_manifest.json`; `npm run build` also packages `model_runtime/edim_model/architecture_catalog.json` into the static bundle for hosted deployments.
- Each architecture controls graph boxes/edges, fixed nodes, enabled result tabs, and the output artifact list shown in the diagram.
- Energy-only mode hides MRIO/development boxes, the development results tab, region-level development map metrics, and MRIO output artifacts while still persisting `model_architecture_id` in the run request. The runtime also skips bridge, MRIO-direct, and development stages for energy-only runs.
- Project run tabs are clickable to inspect a specific run.
- Active execution panel shows elapsed runtime and "last backend checkpoint" age.
- Environment panel exposes backend checks by category.
- Dataset boxes expose upload/download plus user-scoped version activation/deletion.

## 18) Artifact Layout and Contracts

Per-run directory:

- `outputs/runs/<run_id>/`

Core artifact files:

- `artifacts/final/results.csv`
- `artifacts/final/summary.json`
- `artifacts/final/development_impacts.json`
- `artifacts/final/integrated_results.json`
- `artifacts/final/coupling_manifest.json`
- `exports/report.md`
- `exports/exchange_bundle.zip`
- `inputs/runtime/ui_override_patch.yaml`

Exchange artifact subdirectory:

- `artifacts/intermediate/exchange/calliope_component_activity.csv`
- `artifacts/intermediate/exchange/investment_shocks.csv`
- `artifacts/intermediate/exchange/operating_shocks.csv`
- `artifacts/intermediate/exchange/energy_service_balance.csv`
- `artifacts/intermediate/exchange/prices_and_taxes.csv`
- `artifacts/intermediate/exchange/metadata.json`
- `logs/mario_runner.log`

## 19) Environment Setup Checks Semantics

`POST /api/projects/{project_id}/runs/validate` returns:

- `ok`: queue-ready gate
- `checks[]`: detailed status rows
- `warnings[]` and `errors[]`
- solver and engine resolution metadata
- queue capacity stats
- MARIO input health object

`ok` is true only when:

1. No blocking errors are present.
2. Queue has remaining capacity.

## 20) Configuration Reference

Main env vars (see `.env.example`):

- Pathing:
  - `EDIM_CALLIOPE_ROOT`
  - `EDIM_RUNS_DIR`
  - `EDIM_CONFIG_DIR`
  - `EDIM_FRONTEND_DIR`
- Runtime:
  - `EDIM_SOLVER`
  - `EDIM_ALLOW_FULL_YEAR`
  - `EDIM_DEV_SUBSET_START`
  - `EDIM_DEV_SUBSET_END`
  - `EDIM_ANALYSIS_SUBSET_START`
  - `EDIM_ANALYSIS_SUBSET_END`
  - `EDIM_DEV_SOLVER_TIME_LIMIT_SECONDS`
  - `EDIM_ANALYSIS_SOLVER_TIME_LIMIT_SECONDS`
- Summary caps:
  - `EDIM_SUMMARY_MAX_GENERATION_TECHS`
  - `EDIM_SUMMARY_MAX_GENERATION_TIMESTEPS`
  - `EDIM_SUMMARY_MAX_CATEGORY_ROWS`
  - `EDIM_SUMMARY_DIAGNOSTICS_MAX_ROWS`
- Queue/history/retention:
  - `EDIM_JOB_HISTORY_LIMIT`
  - `EDIM_JOB_DEDUPE_ENABLED`
  - `EDIM_JOB_QUEUE_CAPACITY`
  - `EDIM_RUN_RETENTION_DAYS`
  - `EDIM_RUN_MAX_DIRS`
- Development engine:
  - `EDIM_DEVELOPMENT_ENGINE`
  - `EDIM_MARIO_DB_PATH`
  - `EDIM_MARIO_TIMEOUT_SECONDS`
  - `EDIM_MARIO_FAIL_ON_ERROR`
- CORS:
  - `EDIM_CORS_ALLOW_ORIGINS`

## 21) Running the System

### Local backend

```bash
python3.11 -m venv backend/.venv
source backend/.venv/bin/activate
pip3 install -U pip
pip3 install -r backend/requirements.txt
pip3 install --no-build-isolation -e ./model_runtime
python3 scripts/run_local.py --port 8000
```

Open UI:

- `http://127.0.0.1:8000/ui/`

### Docker

```bash
docker compose up --build
```

## 22) Validation and Testing

### Unit tests

```bash
cd backend
python -m unittest discover -s tests -p "test_*.py"
```

### Smoke checks

```bash
cd backend
source .venv/bin/activate
python tools/smoke_check.py
python tools/smoke_check.py --run-model
python tools/backend_handoff_smoke.py --base-url http://127.0.0.1:8000 --timeout-seconds 900
```

`backend_handoff_smoke.py` is the cloud-handoff acceptance smoke test. It expects the backend to be running with the manifest-defined subprocess runtime and validates the user, `/api/system/manifest`, project, run, event, artifact, report, and export contracts.
Its default execution path uses the `energy-only` architecture, the
transmission-only `new_links` energy scenario, and the `dev` time slice. Add
`--model-architecture-id energy-development` to test the full bridge/MRIO path.

### Optional figure generation

```bash
python backend/tools/generate_refinement_visuals.py \
  --runs-dir outputs/runs \
  --calliope-root model_runtime/model_modules/calliope/Calliope-Africa-main \
  --output-dir outputs/figures
```

## 23) Operational Caveats

1. Placeholder or sparse intensity tables will strongly affect development realism.
2. `calliope_cost_to_mario_account.csv` is currently validated but lightly used in runtime logic.
3. `development_indicator_mapping.csv` and `scenario_assumptions.csv` are now consumed by integrated indicators and
   scenario diagnostics, but their calibration should still be reviewed by development and energy-sector experts.
4. Large cases can remain solver-bound for long periods; monitor stage and heartbeat timestamps.
5. Live queue execution state is in-memory in the local reference implementation; persisted project run records and run artifacts remain available after restart.
6. `GET /api/executions/{execution_id}/status` falls back to persisted run records when live queue state is unavailable.
7. Local demo environments should clear ignored `outputs/runs/` and `outputs/platform/` state before formal handoff demos.

The default local platform store uses SQLite for owner-tagged project/run/report/export metadata. It is configured through `storage.platform_store_backend = sqlite` in `inputs/runtime_config.json` or `EDIM_PLATFORM_STORE_BACKEND=sqlite`, writes to `outputs/platform/platform.sqlite3`, and keeps large run/report/export artifacts in the existing artifact folders. The older JSON indexes are import-only migration sources; there is no active JSON repository mode. Azure deployment should replace the platform repository with a managed transactional database and replace `JobManager` with Azure Service Bus or an equivalent durable queue plus persisted progress events.

## 24) Current Example Run Snapshot

A recent successful dev run (`run_id=239bbd4e`) shows:

- `scenario`: `new_links`
- `run_profile`: `dev`
- `warnings`: `0`
- coupling mode: `mario`
- mapping coverage: `1.0`
- unmapped mapping share: `0.0`
- shock rows used: `1144`
- MARIO runtime seconds: ~`3.43`

This confirms end-to-end Calliope -> exchange -> MARIO -> integrated payload flow is operational in the current workspace state.

## Black-Box Model Runtime Contract

The backend is now structured so model execution can be hosted as a black box. The API layer prepares a run bundle, launches a model runtime adapter, consumes structured progress events, and resolves declared artifacts. The backend should not need to understand Calliope, MRIO, bridge internals, or future model internals once a model exposes the same contract.

### Runtime package

The executable EDIM runtime lives in `model_runtime/edim_model/`.

- `model_manifest.json`: versioned model contract with entrypoints, supported schemas, required inputs, declared outputs, stage names, and resource expectations.
- `dataset_manifest.json`: model-owned input dataset contract used by the backend dataset catalog and upload/download UI.
- `cli.py`: executable entrypoint with two commands:
  - `run`: executes the real EDIM Calliope/MRIO runtime.
  - `preflight`: validates staged bundle/dataset availability.
- `core/`: packaged EDIM model implementation used by the real runtime. The runtime package does not import backend API modules.

### Backend execution boundary

The primary backend boundary is in `backend/api_service/runtime/` and `backend/api_service/adapters/`.

- `ModelExecutionRequest`: backend-facing execution request and immutable run-bundle snapshot.
- `ModelExecutionContext`: paths for the queued run bundle, event log, model manifest, and dataset manifest.
- `SubprocessModelRuntime`: manifest-driven adapter that launches the model as a subprocess and parses JSONL events.
- `RunRepository`, `ExecutionQueue`, `RunStore`, `ArtifactStore`, and `EventStore`: provider interfaces that let Azure replace local database/file/event/queue implementations without changing route or model-runtime code.
- `PlatformRepository`: route-facing project/run/report/export metadata interface. The default local implementation is SQLite-backed. Cloud deployment should inject a managed database-backed implementation through `app.state.platform_repository`.
- `ArtifactStorageService`: route-facing artifact JSON/read/download interface. The local implementation uses the filesystem; cloud deployment should inject a Blob-backed implementation through `app.state.artifact_storage`.
- `ArtifactStorageService.publish_run_artifacts(...)`: runtime artifact handoff hook. Local mode uses `shared_filesystem`; Azure should use `worker_staged_upload` so worker-produced declared artifacts are uploaded before a run is marked terminal.
- `DatasetRepository`: route-facing input dataset catalog/version/upload/download/staging interface. The local implementation uses repository files plus user upload folders; cloud deployment should inject a database/object-storage implementation through `app.state.dataset_repository`.
- `EventStore`: route-facing and worker-facing runtime event persistence interface. The local implementation uses JSONL files; cloud deployment should inject database, Blob, or event-stream backed event persistence through `app.state.event_store`.
- `RuntimeEventLog`: JSONL event persistence and replay helper.
- `ArtifactRegistry`: artifact retention, descriptor, and download policy manager.

### Run bundle schema

Every model execution receives a `model_run_bundle_v1` JSON document. The bundle contains:

- `execution_id` (32-character hex queue/worker attempt id in the local implementation)
- `run_id` (32-character hex stable result namespace in the local implementation)
- `model_runtime`
- `queue_message`
- `request`
- `scenario_package`
- `dataset_manifest`
- `artifact_policy`
- `artifact_handoff`
- `runtime_settings`
- `execution`

This is the only input a black-box runtime should require. Future model packages should preserve this bundle shape and add model-specific fields under namespaced keys rather than changing backend API contracts.

`artifact_handoff` uses `runtime_artifact_handoff_v1`. Supported modes are `shared_filesystem`, `worker_staged_upload`, and `runtime_direct_upload`. The configured local default is `shared_filesystem`; the recommended cloud deployment mode is `worker_staged_upload`.

`dataset_manifest` includes `dataset_staging_v1` metadata. Supported dataset staging modes are `reference`, `copy_to_run`, and `object_reference`. The local default is `copy_to_run`, which creates self-contained local/container run packages; `object_reference` is the cloud-provider mode for Blob/object-storage backed workers.

### Runtime event schema

Runtimes emit newline-delimited JSON with `schema_version = runtime_event_v1`.

Supported event types include:

- `stage_started`
- `progress`
- `warning`
- `error`
- `stage_completed`
- `result`

The `result` event must include `run_id` and `payload.summary`. The backend treats this as the completion handshake.

### Artifact policy

The artifact policy is controlled by `inputs/runtime_config.json` under `artifacts.manifest`. New black-box contract artifacts include:

- `model_manifest_json`
- `dataset_manifest_json`
- `artifact_policy_json`
- `runtime_events_jsonl`
- `artifact_index_json`

The backend exposes downloadable files only through artifact descriptors. UI and project-export code should not infer paths.

### Cloud handoff implications

To host models in the cloud without changing the backend API:

1. Package each model as a container or executable runtime with a manifest.
2. Ensure the runtime accepts `--bundle <path-or-uri>`.
3. Emit `runtime_event_v1` JSONL progress events.
4. Write declared artifacts under the requested run package layout.
5. Emit a final `result` event containing `run_id` and summary metadata.
6. Keep all model-specific validation inside the runtime `preflight` command.
7. Keep project/user/storage concerns outside the model package.

The handoff smoke test should be run against the manifest-defined subprocess runtime so CI exercises the same contract used in deployment.

## Final Handoff Refactor Notes

The public backend surface is project-owned and run-centric. The frontend
canonical submission flow is:

1. `GET /api/session`
2. `GET /api/projects`
3. `POST /api/projects` if a project needs to be created
4. `POST /api/projects/{project_id}/runs`
5. `POST /api/projects/{project_id}/runs/{run_id}/submit`
6. `GET /api/executions/{execution_id}/status`
7. `GET /api/projects/{project_id}/runs`
8. `GET /api/runs/{run_id}/summary`
9. `GET /api/runs/{run_id}/development`
10. `GET /api/runs/{run_id}/integrated`
11. `GET /api/runs/{run_id}/artifacts`
12. `GET /api/runs/{run_id}/artifacts/{artifact_id}`

Run submission is project-owned through draft and submit endpoints. Legacy
`/api/jobs`, `/api/run/...`, and direct quick-run submission routes are not part
of the mounted application surface. Downloads should always go through artifact
ids, report ids, or export ids.

The complete local user flow now includes project selection/creation, project
run history, durable status from persisted run records, result viewing,
completed-run comparison, project reports, run/project exports, and dataset
version activation/deletion.

### Basic report generation

`POST /api/projects/{project_id}/reports` now produces a backend-owned report
artifact pair:

- Markdown report: `<report_id>.md`
- Structured source data: `<report_id>.source.json`

The source data schema is `edim_project_report_source_v1`. It contains project
metadata, selected run records, available run `summary_json` content reduced to
report-ready metrics/artifacts/warnings, and existing project export metadata.
This is intentionally a basic export-data-backed report system. It establishes
the backend linkage for future document/HTML report rendering without tying the
frontend to model internals or raw filesystem paths.

Report and export records use `storage_ref` objects as their primary storage
contract. Local development resolves those references to
`outputs/platform/reports/...` and `outputs/platform/exports/...`; Azure storage
providers should keep the same object-key semantics while pointing to Blob or
equivalent object storage.

The dashboard header includes a Local/Backend runtime target switch for backend
testing. The Backend side is enabled only when `EDIM_BACKEND_API_BASE` is set
before running `python3 scripts/run_local.py` or before `cd frontend && npm run
build`. The variable is a public browser-visible API base URL, not a secret. On
switch, the frontend clears loaded workspace state and reloads session, project,
dataset, runtime, and scenario catalogs from the selected API.

The local reference implementation also exposes platform endpoints that define the user/project boundary for cloud replacement:

- `GET /api/session`
- `GET /api/projects`
- `POST /api/projects`
- `GET /api/projects/{project_id}`
- `PATCH /api/projects/{project_id}`
- `DELETE /api/projects/{project_id}`
- `GET /api/projects/{project_id}/runs`
- `POST /api/projects/{project_id}/runs`
- `GET /api/projects/{project_id}/runs/{run_id}`
- `PATCH /api/projects/{project_id}/runs/{run_id}`
- `POST /api/projects/{project_id}/runs/{run_id}/submit`
- `POST /api/projects/{project_id}/runs/{run_id}/duplicate`
- `DELETE /api/projects/{project_id}/runs/{run_id}`
- `GET /api/runs/{run_id}/logs`
- `POST /api/runs/{run_id}/export`
- `GET /api/projects/{project_id}/reports`
- `POST /api/projects/{project_id}/reports`
- `GET /api/projects/{project_id}/reports/{report_id}/download`
- `GET /api/projects/{project_id}/exports`
- `POST /api/projects/{project_id}/exports`
- `GET /api/projects/{project_id}/exports/{export_id}/download`

This build uses a local test-user auth shim. `GET /api/session` returns the active user plus available test users, and the frontend sends `X-EDIM-User-Id` on API calls. Unknown test-user IDs are rejected. Projects are not shared across users; each project, run, report, export, and dataset override has an owner user. The `admin` test account can list and access all user-owned projects for oversight. Production should replace only this session/dependency layer with authenticated user context and server-side authorization checks while keeping the owner-user object contracts stable.

The frontend keeps this replaceable through `window.EDIM_API_CLIENT.setAuthProvider(...)`. The default provider sends the local test-user header, but an Azure-hosted shell can inject a provider that returns bearer-token or managed-session headers without changing workspace, run, or result components.

Each submitted run now has:

- `execution_id`: queue/worker attempt id.
- `run_id`: stable result namespace allocated before execution starts.

### Dataset versioning

Input dataset uploads no longer overwrite repository source files. User-owned uploaded files are stored under:

`outputs/dataset_uploads/users/<user_id>/<dataset_id>/<version_id>.<ext>`

The user active override index is:

`outputs/dataset_uploads/users/<user_id>/active_versions.json`

The dataset catalog reports whether a dataset is using a versioned override with:

- `active_version_id`
- `versioned_override`

Dataset APIs are user-scoped rather than project-scoped. Project exports include uploaded dataset files referenced by exported run snapshots under `datasets/users/<user_id>/<dataset_id>/`, plus `datasets/uploaded_dataset_manifest.json`, so backend handoff bundles can be reconstructed without relying on mutable local upload folders.

The dataset catalog includes:

- `source_filename`
- `active_version_id`
- `versioned_override`

The model run bundle receives a staged snapshot of the selected user's active datasets through `dataset_manifest`. Each row includes `staging_mode`, `staging_status`, `storage_ref`, `source_storage_ref`, optional `staged_relative_path`, `content_sha256`, and `size_bytes` where locally readable. Backend/cloud storage can later swap the local filesystem implementation for object storage without changing the model runtime contract. Uploads are validated for allowed file type, size, basic parseability, and required CSV headers before they become active.

Dataset lifecycle endpoints:

- `GET /api/input-datasets?layer=<layer>&input_property=<text>&role=<text>`
- `GET /api/input-datasets/{dataset_id}/versions`
- `POST /api/input-datasets/{dataset_id}/versions/{version_id}/activate`
- `DELETE /api/input-datasets/{dataset_id}/versions/{version_id}`

### Runtime preflight

`POST /api/projects/{project_id}/runs/validate` includes `runtime_preflight`, which is produced by the selected model runtime's `preflight` command. Backend-side checks remain for UI diagnostics, but the executable runtime owns final model package readiness. `GET /api/environment-setup` remains available as a compatibility/debug route.

### Backend system manifest

`GET /api/system/manifest` returns `edim_system_manifest`, a compact machine-readable system manifest for hosted deployments. It lists the stable contract identifiers, public endpoint groups, provider boundaries, runtime modes, artifact/data staging settings, and diagnostics that deployment CI can compare before running the full smoke test. This keeps deployment checks out of frontend code and avoids relying on prose documentation for compatibility.

### Runtime adapter simplification

The local queue now has one execution path:

`PublicRunConfiguration -> RunRequest -> model_run_bundle_v1 -> SubprocessModelRuntime -> runtime_event_v1 JSONL -> artifact_catalog`

The older in-process Python runtime and multiprocessing compatibility route were removed from the active backend path. Unit tests use injected fake runtimes where needed; production uses the manifest-defined subprocess runtime.

Cloud queue workers should use `execution_queue_message`, represented by `ExecutionQueueMessage` in `backend/api_service/runtime/contracts.py`, as the durable queue payload. The message carries `execution_id`, `run_id`, `project_id`, `user_id`, `attempt`, `created_at`, `execution_retry_policy`, and the backend-normalized `RunRequest` JSON. The local queue now uses the same payload shape; it is persisted in the project run record and embedded in `model_run_bundle_v1.queue_message` so worker provenance is inspectable from `request_bundle_json`.

Worker lifecycle is separately recorded with `execution_attempt`, represented by `ExecutionAttemptRecord`. Project run diagnostics expose `execution_attempts`, `worker_id`, and `cancellation_requested`; hosted workers should map those fields to their queue lease, worker identity, heartbeat, cancellation, and terminal attempt state. Frontend status polling stays compact and does not receive queue messages, attempts, model bundles, or dataset snapshots.
