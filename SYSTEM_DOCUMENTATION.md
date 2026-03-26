# EDIM System Documentation

This document is the full technical reference for the EDIM MVP in this repository.

- Repository root: `/Users/ben/Downloads/edim-calliope-africa`
- Purpose: run integrated energy-development scenarios using Calliope-Africa + MARIO-style economic propagation.
- Primary runtime: FastAPI backend + no-build React frontend.

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
- Frontend UI: `frontend/`
- Runtime input controls: `inputs/`
- Run artifacts: `outputs/`
- Energy model source: `Calliope-Africa-main/`

## 2) Repository Structure

```text
edim-calliope-africa/
  backend/
    api_service/
      main.py
      jobs.py
      runner.py
      summarize.py
      integrated.py
      mario_runtime.py
      levers.py
      scenarios.py
      schemas.py
      settings.py
    tests/
      test_mvp.py
    tools/
      smoke_check.py
      generate_refinement_visuals.py
  frontend/
    index.html
    app.jsx
  inputs/
    lever_mappings.csv
    scenario_metadata.csv
    development_model.csv
    mario_inputs/
      *.csv
  outputs/
    runs/
    figures/
  Calliope-Africa-main/
    model.yaml
    overrides.yaml
    *.yaml
```

## 3) End-to-End Runtime Flow

1. UI requests `/api/environment-setup` and `/api/scenarios`.
2. UI submits `POST /api/jobs`.
3. `JobManager` enqueues a run and executes it in a subprocess worker.
4. `runner.run_calliope_synchronously` runs staged execution:
   - `environment_setup`
   - `cleanup`
   - `prepare_inputs`
   - `build_model`
   - `solve_energy`
   - `write_artifacts`
   - `build_summary`
   - `development`
   - `build_integrated`
   - `complete`
5. Artifacts are written to `outputs/runs/<run_id>/`.
6. UI polls `/api/jobs/{job_id}` and loads run outputs.

## 4) Backend Components

### `main.py`

- FastAPI app wiring.
- CORS setup.
- Frontend static mount at `/ui`.
- API route definitions for scenarios, environment setup, jobs, and run artifacts.

### `jobs.py`

- In-memory queue + worker thread.
- Subprocess run execution for robust cancellation.
- Job deduplication by request fingerprint.
- Queue capacity enforcement.
- Progress/stage heartbeat and status transitions.

### `runner.py`

Core orchestrator:

- Input/retention setup and run directory creation.
- Calliope model assembly and runtime override patching.
- Solver compatibility patches for HiGHS/appsi.
- Solve execution and result-health checks.
- Results CSV export (`results.csv`).
- Summary + diagnostics build.
- Development outputs via MARIO or surrogate.
- Integrated payload construction and baseline comparison.
- Artifact writing (`summary.json`, report, exchange bundle zip, etc.).

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
- Uses exact → region mean → global mean intensity fallback hierarchy.
- Returns totals and disaggregations with uncertainty bounds.

### `integrated.py`

- Validates integrated payload schema.
- Builds integrated metrics and confidence metadata.
- Builds baseline comparison deltas vs latest baseline scenario run.
- Generates report markdown and exchange bundle zip.

### `levers.py`

- Loads lever mappings from CSV.
- Resolves tech wildcard mappings.
- Applies CAPEX/fuel/carbon lever patch generation.

### `scenarios.py`

- Reads Calliope scenario keys from `overrides.yaml`.
- Merges optional metadata from `scenario_metadata.csv`.

### `settings.py`

Environment-driven settings:

- Paths, solver, run profile windows, time limits.
- Summary row caps.
- Queue/history/retention controls.
- Development engine mode and MARIO runtime options.

### `schemas.py`

Pydantic models for request/response contracts:

- `RunRequest`, `LeverValues`, `JobInfo`, `RunSummary`, etc.

## 5) API Reference

### Health/UI

- `GET /health`
- `GET /` (redirects to `/ui/` when frontend exists)
- `GET /ui/` (static frontend)

### Scenario and Environment

- `GET /api/scenarios`
- `GET /api/environment-setup?scenario=<key>&run_profile=<dev|analysis|full>`
- `GET /api/preflight` (compat alias to environment setup)

### Jobs

- `POST /api/jobs`
- `GET /api/jobs?limit=<n>`
- `GET /api/jobs/{job_id}`
- `POST /api/jobs/{job_id}/cancel`

### Run Outputs

- `GET /api/run/{run_id}/summary`
- `GET /api/run/{run_id}/development`
- `GET /api/run/{run_id}/integrated`
- `GET /api/run/{run_id}/download/csv`
- `GET /api/run/{run_id}/download/report`
- `GET /api/run/{run_id}/download/exchange_bundle`
- `GET /api/run/{run_id}/download/exchange/{file_path}`

## 6) Scenario and Model Layering

### Base Calliope model

File: `Calliope-Africa-main/model.yaml`

- Imports technology, location constraints, and transmission link files.
- Defines base temporal subset and run settings.

### Scenario catalog

File: `Calliope-Africa-main/overrides.yaml`

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

- Timeseries in `Calliope-Africa-main/Timeseries`.
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
- `policy_question`, `baseline_scenario`, `expected_tradeoff`, `user_label`
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

Dotted parameter paths for surrogate and MARIO uncertainty config, e.g.:

- `surrogate.totals.jobs_total_multiplier`
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

The bridge writes exchange artifacts in `outputs/runs/<run_id>/exchange/`.

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

- If no tech-level component rows, build summary-based fallback shocks using cost totals and regional weights.
- If still empty, runtime returns zero development impacts with explicit diagnostics.

## 13) MARIO Runtime Outputs

`development_impacts.json` structure:

- `method`: currently `mario_io_runtime_v1` when MARIO path runs
- `inputs`: investment/operating/total shocks
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
  - intensity match fallback counts
  - year
  - optional surrogate benchmark deltas

## 14) Development Engine Modes

Configured via `EDIM_DEVELOPMENT_ENGINE`:

- `mario`: use MARIO runtime; fail if MARIO path errors.
- `auto`: attempt MARIO then fallback to surrogate (unless fail-on-error is enabled).
- `surrogate`: skip MARIO and compute development proxies from configurable coefficients.

Surrogate equations and uncertainties are controlled through `inputs/development_model.csv`.

## 15) Integrated Results Payload

`integrated_results.json` includes:

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
  - mapping coverage/fallback
  - warning count
  - MARIO runtime diagnostics
- `development_uncertainty`
- `baseline_comparison`

Baseline comparison source:

- Baseline scenario key from `scenario_metadata.csv` (`baseline_scenario` column).
- Uses latest historical run for that baseline scenario when available.

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

Core UX flow:

1. Scenario setup and lever tuning.
2. Environment setup checks.
3. Queue run.
4. Monitor active job with stage/progress/heartbeat.
5. Inspect selected job outputs.
6. Review integrated charts and diagnostics.

Notable UI behaviors:

- Jobs table rows are clickable to inspect a specific job/run.
- Active job panel shows elapsed runtime and "last backend checkpoint" age.
- Environment panel exposes backend checks by category.

## 18) Artifact Layout and Contracts

Per-run directory:

- `outputs/runs/<run_id>/`

Core files:

- `results.csv`
- `summary.json`
- `development_impacts.json`
- `integrated_results.json`
- `coupling_manifest.json`
- `report.md`
- `exchange_bundle.zip`
- `ui_override_patch.yaml`

Exchange subdirectory:

- `exchange/calliope_component_activity.csv`
- `exchange/investment_shocks.csv`
- `exchange/operating_shocks.csv`
- `exchange/energy_service_balance.csv`
- `exchange/prices_and_taxes.csv`
- `exchange/metadata.json`
- `exchange/mario_runner.log`
- mirrored integrated/development/coupling JSON files

## 19) Environment Setup Checks Semantics

`/api/environment-setup` returns:

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
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
uvicorn api_service.main:app --reload --port 8000
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
```

### Optional figure generation

```bash
python backend/tools/generate_refinement_visuals.py \
  --runs-dir outputs/runs \
  --calliope-root Calliope-Africa-main \
  --output-dir outputs/figures
```

## 23) Operational Caveats

1. Placeholder or sparse intensity tables will strongly affect development realism.
2. `calliope_cost_to_mario_account.csv` is currently validated but lightly used in runtime logic.
3. `development_indicator_mapping.csv` and `scenario_assumptions.csv` are not yet deeply wired into runtime calculations.
4. Large cases can remain solver-bound for long periods; monitor stage and heartbeat timestamps.
5. Job queue state is in-memory; restarting backend clears in-memory job history but keeps run artifacts.
6. Legacy run folders may contain older `results.nc` artifacts from prior versions.

## 24) Current Example Run Snapshot

A recent successful dev run (`run_id=239bbd4e`) shows:

- `scenario`: `new_links`
- `run_profile`: `dev`
- `warnings`: `0`
- coupling mode: `mario`
- mapping coverage: `1.0`
- fallback mapping share: `0.0`
- shock rows used: `1144`
- MARIO runtime seconds: ~`3.43`

This confirms end-to-end Calliope -> exchange -> MARIO -> integrated payload flow is operational in the current workspace state.
