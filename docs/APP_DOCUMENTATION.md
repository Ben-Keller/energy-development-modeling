# EDIM Platform Documentation

Document status: platform reference  
Last verified against the repository: 2026-07-27

This is the read-first guide to the Energy-Development Integrated Modeling (EDIM) platform. It covers the product surface, system architecture, ownership boundaries, local operation, APIs, data management, run lifecycle, artifacts, validation, and deployment handoff. The scientific methods, assumptions, datasets, model equations, and research gaps are documented separately in the [Modeling methodology](model/MODELING_METHODOLOGY.md).

## 1. What This App Is

EDIM is a project-based modeling workspace for exploring how energy transition pathways can affect development outcomes. It combines:

- a frontend dashboard for projects, model configuration, result exploration, comparison, reports, and dataset management;
- a FastAPI backend that owns users, projects, runs, datasets, artifacts, reports, exports, queue state, and runtime status;
- a black-box model runtime package that executes energy-only or energy-development model architectures.

The intended product pattern is:

```text
User -> Project -> Model run configuration -> Validated run -> Model execution -> Results -> Compare/report/export
```

The intended backend integration pattern is:

```text
Frontend DTOs -> Backend orchestration -> Run bundle -> Black-box model runtime -> Declared artifacts -> Backend descriptors -> Frontend views/downloads
```

### Current deployment status

The repository is a local, test-user platform and a hosting handoff reference. Its principal production replacement points are explicit:

- test-user headers must be replaced by managed authentication and authorization;
- the local SQLite platform repository must be replaced or operated as a managed durable store;
- the in-process queue and subprocess worker must be replaced by durable queue/worker infrastructure for hosted scale;
- shared-filesystem artifact and dataset handoff must be replaced by an approved object-storage pattern when workers are not co-located;
- placeholder modeling datasets must be replaced before development results are used for policy decisions.

These substitutions are platform concerns. The model runtime remains isolated behind the run-bundle, event, manifest, and artifact contracts described below.

## 2. Documentation Map

Use this file as the entry point, then jump to the deeper references as needed.

- [Root README](../README.md): local setup, placeholder data status, quickstart, and artifact locations.
- [System documentation](system/SYSTEM_DOCUMENTATION.md): detailed system architecture and runtime behavior.
- [Backend handoff](handoff/BACKEND_HANDOFF.md): backend/provider replacement contract for Azure or another hosted platform.
- [Technical architecture handoff](handoff/EDIM_Technical_Architecture_and_Requirements_Handoff.md): short navigation document for backend, frontend, and design teams.
- [Model runtime README](../model_runtime/README.md): black-box model package contract, runtime CLI, manifests, and module boundary.
- [Modeling methodology](model/MODELING_METHODOLOGY.md): implemented methods, datasets, assumptions, interpretation limits, and scientific gap register.
- [Frontend README](../frontend/README.md): frontend file organization, build, runtime switching, and handoff notes.
- [Model I/O catalog CSV](model/EDIM_model_io_catalog.csv): detailed input/output inventory.
- [Model I/O catalog XLSX](model/EDIM_model_io_catalog.xlsx): spreadsheet version of the input/output inventory.
- [MARIO inputs README](../inputs/mario_inputs/README.md): MRIO/development input data notes.
- [Geo README](../frontend/geo/README.md): bundled geospatial assets and placeholder geometry notes.

## 3. Main Product Surfaces

### Landing Page

Purpose:

- introduce EDIM as an energy-development decision-support platform;
- provide entry points to projects and methodology;
- show the production hero visualization and platform framing.

Key files:

- `frontend/app.jsx`
- `frontend/hero-visual.jsx`
- `frontend/hero-defaults.json`
- `frontend/assets/`

### Projects Overview

Purpose:

- select, create, rename, archive, or delete projects;
- switch test users;
- manage datasets separately from projects;
- expose project cards and project-level actions without model-run clutter.

Current user model:

- test users are available in the UI;
- normal users see their own projects and datasets;
- the seeded admin user can see projects across accounts;
- this is structured to be replaced by real auth later without changing the model runtime contract.

### Project Workspace

Purpose:

- act as the homepage for a selected project;
- show compact project statistics;
- separate model selection from model comparison;
- keep project-level reports and exports accessible.

Core tabs:

- `Model Selection`: create/open model runs and select eligible completed runs.
- `Model Comparison`: compare completed model runs and generate comparison/report outputs.

### Model Workspace

Purpose:

- configure one model run;
- show the model architecture as the primary UI structure;
- let users inspect inputs, model stages, data links, validation diagnostics, and run readiness.

Model workspace behavior:

- draft runs are editable;
- queued/running/succeeded runs are locked;
- running and succeeded runs can be duplicated into a new draft;
- succeeded runs show results and make scenario details secondary.

The graph-centered UI is driven by the model architecture catalog, not hard-coded frontend stage assumptions.

### Results Workspace

Purpose:

- display spatial, energy-system, development, and method/provenance outputs;
- keep scenario/run details available without taking over the results view;
- provide run management through a modal rather than a permanent side panel.

Main result tabs:

- `Overview`: spatial map and headline outputs.
- `Energy system`: generation, capacity, system cost, energy-side outputs.
- `Development`: jobs, GVA, import leakage, emissions/development metrics where available.
- `Method`: scenario definition, provenance, diagnostics, model chain, and assumptions.

### Methodology Page

Purpose:

- explain EDIM from a policy/programme user perspective;
- describe why energy-only analysis is not enough for development decisions;
- show how architecture modes, scenario channels, datasets, and interpretation principles work.

Key files:

- `frontend/methodology/methodology.js`
- `frontend/methodology/methodology.css`

## 4. Runtime Architecture

The app is intentionally split into three layers.

### Frontend Layer

Location:

- `frontend/`

Responsibilities:

- render the landing page, projects, workspace, graph UI, result views, methodology page, reports, exports, and dataset controls;
- call backend APIs through `frontend/api-client.js`;
- switch between local backend and hosted backend using runtime configuration;
- consume model architecture catalogs and artifact descriptors;
- avoid direct filesystem assumptions.

Important files:

- `frontend/index.html`: static shell and script load order.
- `frontend/api-client.js`: backend URL selection, test-user headers, transport helpers, downloads, runtime target switching.
- `frontend/app.jsx`: React app, project/run UI, graph workspace, results, high-level API wrapper.
- `frontend/scripts/build-static.js`: static bundle build/check script.
- `frontend/runtime-config.js`: public runtime config for backend target switching.
- `frontend/runtime-config.local.js`: local override config.
- `frontend/geo/`: bundled map assets.

Build command:

```bash
cd frontend
npm run build
cd ..
```

### Backend Layer

Location:

- `backend/api_service/`

Responsibilities:

- create and serve the FastAPI app;
- expose user/session/project/dataset/run/report/export APIs;
- stage run bundles;
- own queue/execution state;
- read runtime events;
- publish artifact descriptors;
- serve frontend static files under `/ui`;
- provide the stable system manifest for hosted backend compatibility checks.

Important files:

- `backend/api_service/main.py`: composition root and provider injection point.
- `backend/api_service/api/routers/`: route modules.
- `backend/api_service/services/`: project/user/dataset/artifact/report/catalog services.
- `backend/api_service/runtime/`: runtime contracts, bundles, events, artifact manifest handling.
- `backend/api_service/adapters/subprocess_runtime.py`: local subprocess runtime adapter.
- `backend/api_service/jobs.py`: local queue/job manager.
- `backend/api_service/settings.py`: local settings and path configuration.

Cloud replacement points:

- user/auth provider;
- platform/project repository;
- dataset repository;
- artifact storage;
- event store;
- queue/worker manager;
- subprocess/container runtime adapter.

### Model Runtime Layer

Location:

- `model_runtime/`

Responsibilities:

- accept one staged `model_run_bundle_v1`;
- run preflight checks;
- execute model stages;
- emit `runtime_event_v1` JSONL progress events;
- write declared artifacts;
- return final result event;
- keep model internals behind the runtime CLI boundary.

Important files:

- `model_runtime/edim_model/model_manifest.json`: black-box runtime contract.
- `model_runtime/edim_model/dataset_manifest.json`: dataset contract.
- `model_runtime/edim_model/architecture_catalog.json`: graph/result-surface catalog.
- `model_runtime/edim_model/cli.py`: runtime command entrypoint.
- `model_runtime/edim_model/local_runtime.py`: bundle executor.
- `model_runtime/edim_model/modules/`: model module implementations.
- `model_runtime/model_modules/calliope/Calliope-Africa-main/`: bundled Calliope model source.

Runtime commands:

```bash
python -m edim_model.cli catalog --config-dir inputs --manifest model_runtime/edim_model/model_manifest.json
python -m edim_model.cli preflight --bundle /path/to/request_bundle.json
python -m edim_model.cli run --bundle /path/to/request_bundle.json
```

## 5. Model Architectures

The frontend and backend use the same model-owned architecture catalog:

```text
model_runtime/edim_model/architecture_catalog.json
```

Current architecture modes:

- `energy-only`: runs the energy-side architecture and hides MRIO/development result surfaces.
- `energy-development`: runs the full integrated energy -> bridge -> MRIO/development workflow.

Current model modules:

- `calliope`: ready energy system model module.
- `mrio`: ready development/MRIO module.
- `osemosys`: planned energy model boundary; not executable until a real implementation and dependencies are supplied.

Architecture catalog responsibilities:

- graph boxes;
- graph links;
- model-stage labels;
- visible dataset layers;
- selectable result tabs;
- output artifacts;
- I/O wire modes used by the model graph.

When adding new model modules, update the model runtime manifest and architecture catalog first, then expose the new capability through the backend catalog. Do not hard-code new modules into frontend components.

## 6. Data and Inputs

Top-level input configuration:

- `inputs/runtime_config.json`: runtime controls and artifact policy.
- `inputs/scenario_metadata.csv`: energy pathway labels and defaults.
- `inputs/lever_mappings.csv`: lever-to-model mapping controls.
- `inputs/scenario_geography_mapping.csv`: model geography alignment.
- `inputs/generated/scenario_report_scenarios.json`: structured scenario target data.
- `inputs/generated/africa_national_mrio_placeholder_scenarios.json`: current national MRIO placeholder target data.

MRIO/development inputs:

- `inputs/mario_inputs/calliope_tech_to_mario_sector.csv`
- `inputs/mario_inputs/calliope_cost_to_mario_account.csv`
- `inputs/mario_inputs/capex_sector_split.csv`
- `inputs/mario_inputs/opex_sector_split.csv`
- `inputs/mario_inputs/country_to_pool.csv`
- `inputs/mario_inputs/development_indicator_mapping.csv`
- `inputs/mario_inputs/employment_intensity.csv`
- `inputs/mario_inputs/value_added_intensity.csv`
- `inputs/mario_inputs/scenario_assumptions.csv`
- `inputs/mario_inputs/scenario_report_scenarios.csv`

Frontend geospatial inputs:

- `frontend/geo/countries.geojson`
- `frontend/geo/world_fit.geojson`
- `frontend/geo/edim_locations_placeholder.geojson`

Important placeholder policy:

- The repository includes coherent seeded placeholder datasets for local end-to-end testing.
- Placeholder data are not final analytical evidence.
- The UI exposes validation and placeholder diagnostics.
- See the root [README](../README.md) and [model I/O catalog](model/EDIM_model_io_catalog.csv) for the exact replacement instructions.

## 7. User, Project, Dataset, and Run Model

### Users

Current local implementation:

- uses seeded test users;
- supports an admin-style user that can view all projects;
- keeps data scoped by user id;
- is designed to be replaced by hosted auth without changing the model runtime.

Backend integration rule:

- replace the current user context provider, but preserve the backend-facing user context shape.

### Projects

A project is the main organizational unit. It groups:

- model runs;
- dataset versions;
- project reports;
- export bundles;
- comparison selections.

Project actions:

- create project;
- edit project name;
- open workspace;
- archive;
- delete;
- generate/download project-level report or export.

### Datasets

Dataset management is user/project aware. Current behavior:

- upload dataset versions;
- list available datasets;
- download uploaded datasets;
- activate/delete versions where supported;
- snapshot active dataset references at run submission.

Important rule:

- execution should use the submitted dataset snapshot, not whatever dataset version is active later.

### Runs

Run statuses:

- `draft`: editable configuration.
- `queued`: submitted and awaiting execution.
- `running`: executing and locked.
- `succeeded`: completed and immutable.
- `failed`: terminal error state.
- `cancelled`: cancelled execution state; UI should return to an editable draft path where applicable.

Run actions:

- create draft;
- edit draft;
- submit/queue run;
- monitor progress/events;
- duplicate configuration;
- delete run;
- inspect artifacts;
- compare completed runs.

## 8. Run Lifecycle

The canonical flow is:

```text
Create project
Create draft run
Configure scenario + levers + architecture + datasets
Validate environment setup
Submit draft run
Backend snapshots datasets and stages run bundle
Queue executes model runtime
Runtime emits events and artifacts
Backend records terminal status
Frontend displays results and downloads
```

Runtime stages commonly include:

- `environment_setup`
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

## 9. API Surface Overview

The full route contract is documented in [Backend handoff](handoff/BACKEND_HANDOFF.md). The frontend primarily uses these groups:

System:

- `GET /api/system/manifest`
- `GET /api/model-runtimes`
- `GET /api/scenarios`
- `GET /api/environment-setup`

Session/projects:

- `GET /api/session`
- `GET /api/projects`
- `POST /api/projects`
- `GET /api/projects/{project_id}`
- `PATCH /api/projects/{project_id}`
- `DELETE /api/projects/{project_id}`

Runs:

- `GET /api/projects/{project_id}/runs`
- `POST /api/projects/{project_id}/runs`
- `PATCH /api/projects/{project_id}/runs/{run_id}`
- `POST /api/projects/{project_id}/runs/{run_id}/submit`
- `POST /api/projects/{project_id}/runs/{run_id}/duplicate`
- `DELETE /api/projects/{project_id}/runs/{run_id}`
- `GET /api/executions/{execution_id}/status`
- `GET /api/executions/{execution_id}/events`
- `POST /api/executions/{execution_id}/cancel`

Datasets:

- `GET /api/input-datasets`
- `GET /api/input-datasets/{dataset_id}/download`
- `POST /api/input-datasets/{dataset_id}/upload`
- `GET /api/input-datasets/{dataset_id}/versions`
- version download, activation, and deletion routes under the same dataset path.

Artifacts/reports/exports:

- run artifact descriptor routes;
- artifact download routes;
- project report routes;
- project export bundle routes.

Frontend rule:

- download from backend-provided descriptors and artifact ids;
- do not infer raw filesystem paths in UI code.

## 10. Artifacts, Reports, and Exports

Run package layout:

```text
outputs/runs/<run_id>/
  inputs/
  artifacts/
    intermediate/
    final/
  logs/
  exports/
```

Common artifacts:

- `inputs/request_bundle.json`
- `inputs/scenario_package.json`
- `inputs/model_manifest.json`
- `inputs/dataset_manifest.json`
- `inputs/artifact_policy.json`
- `artifacts/final/results.csv`
- `artifacts/final/summary.json`
- `artifacts/final/development_impacts.json`
- `artifacts/final/integrated_results.json`
- `exports/report.md`
- `exports/exchange_bundle.zip`

Project reports and exports:

```text
outputs/platform/reports/
outputs/platform/exports/
```

The backend should expose artifacts through descriptors with stable ids and storage references. Cloud storage can replace local filesystem paths without changing frontend download behavior.

## 11. Local Setup

Use Python `3.11`. The packaged Calliope runtime pins dependencies that are not compatible with newer Python/Numpy combinations.

Install backend and runtime:

```bash
cd /Users/ben/Documents/UNDP/SEH/energy-development-modeling
python3.11 -m venv backend/.venv
source backend/.venv/bin/activate
pip3 install -U pip
pip3 install -r backend/requirements.txt
pip3 install -r backend/requirements-dev.txt
pip3 install --no-build-isolation -e ./model_runtime
```

Install/build frontend:

```bash
cd /Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend
npm install
npm run build
cd ..
```

Run local app directly:

```bash
cd /Users/ben/Documents/UNDP/SEH/energy-development-modeling
backend/.venv/bin/python scripts/run_local.py --no-open
```

The runner:

- requires Python 3.11 for the backend/model runtime environment;
- serves the frontend under `/ui/`;
- starts FastAPI;
- tries the requested port first;
- automatically attempts later ports if the requested port is busy;
- opens the browser unless `--no-open` is used.

## 12. Local/Hosted Backend Switch

The frontend can call:

- `Local`: same origin as the UI;
- `Backend`: the hosted backend configured through `EDIM_BACKEND_API_BASE`.

The hosted backend must:

- serve the same API route contract;
- allow the frontend origin through CORS;
- expose `GET /api/system/manifest`;
- pass frontend compatibility diagnostics;
- support the same descriptor-based artifact/report/export downloads.

`EDIM_BACKEND_API_BASE` is public browser config. It must not include secrets, API keys, or signed URLs.

## 13. Testing and Validation

Recommended checks before handoff or commit:

```bash
cd /Users/ben/Documents/UNDP/SEH/energy-development-modeling
git diff --check
python3 -m py_compile scripts/run_local.py
cd frontend
npm run build
cd ..
```

Backend tests, after the Python 3.11 environment is installed:

```bash
cd /Users/ben/Documents/UNDP/SEH/energy-development-modeling
PYTHONPATH=backend:model_runtime backend/.venv/bin/python -m pytest backend/tests -q
```

Backend handoff smoke test, against a running backend:

```bash
cd /Users/ben/Documents/UNDP/SEH/energy-development-modeling
backend/.venv/bin/python scripts/run_local.py --port 8000
backend/.venv/bin/python backend/tools/backend_handoff_smoke.py --base-url http://127.0.0.1:8000 --user-id undp_analyst --timeout-seconds 900
```

Use `--model-architecture-id energy-development` when you need the full bridge/MRIO path. The default smoke mode is intentionally lighter.

## 14. Deployment and Backend Handoff Principles

For cloud/backend teams:

- keep the frontend API contract stable;
- keep model execution behind the runtime manifest and run bundle;
- replace local providers at `create_app(...)` injection points;
- do not make frontend components aware of Blob paths, run directories, or model internals;
- keep artifact downloads descriptor-based;
- keep dataset snapshots immutable at submission;
- expose system manifest diagnostics for CI and frontend compatibility checks;
- run the backend handoff smoke test after each infrastructure substitution.

The black-box model package can continue evolving if it preserves:

- CLI entrypoint shape;
- `model_run_bundle_v1` input;
- `runtime_event_v1` output events;
- declared artifact ids;
- final result event.

## 15. Troubleshooting

### `backend/.venv/bin/python: No module named pytest`

Install dev requirements:

```bash
source backend/.venv/bin/activate
pip3 install -r backend/requirements-dev.txt
```

### `ERROR: Cannot install calliope==0.6.10 ... numpy`

Use Python 3.11 and install the runtime exactly as documented:

```bash
python3.11 -m venv backend/.venv
source backend/.venv/bin/activate
pip3 install -r backend/requirements.txt
pip3 install --no-build-isolation -e ./model_runtime
```

### Port already in use

The local runner automatically tries later ports. Or specify a starting port:

```bash
backend/.venv/bin/python scripts/run_local.py --port 8010
```

### Hosted backend switch is disabled

Set the public frontend runtime config for `EDIM_BACKEND_API_BASE` and ensure the hosted backend serves `GET /api/system/manifest`.

## 16. Maintenance Rules

Keep these boundaries intact:

- frontend renders from DTOs and descriptors;
- backend owns projects, users, datasets, runs, artifacts, reports, exports, and queue status;
- model runtime owns only model execution;
- data inputs live under `inputs/`, `frontend/geo/`, or model module asset folders;
- large raw photos/videos stay gitignored;
- generated runtime outputs stay under `outputs/`;
- new model modules are registered in model manifests/catalogs before being exposed in UI;
- new downloads are exposed through artifact/report/export descriptors, not raw paths.

Before handoff, make sure newly added files are staged deliberately and belong to the EDIM platform, model runtime, inputs, tests, or documentation.
