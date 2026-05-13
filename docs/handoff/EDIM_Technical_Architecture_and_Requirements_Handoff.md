# EDIM Technical Architecture and Backend Handoff

_Current implementation snapshot for backend, frontend, and design teams._

Last refreshed: 2026-05-08.

This Markdown file is a navigation artifact. The canonical implementation contracts live in:

- [BACKEND_HANDOFF.md](BACKEND_HANDOFF.md)
- [SYSTEM_DOCUMENTATION.md](../system/SYSTEM_DOCUMENTATION.md)
- [README.md](../../README.md)
- [model_runtime/README.md](../../model_runtime/README.md)
- [EDIM_model_io_catalog.csv](../model/EDIM_model_io_catalog.csv)

## 1. Current System Shape

The repository is organized around a thin FastAPI backend, a static frontend workspace, and a packaged model runtime. The backend owns projects, users, datasets, runs, artifact descriptors, reports, exports, and local queue orchestration. The model runtime is treated as a black-box package with explicit manifests and a subprocess-ready contract.

The frontend talks to project-owned run APIs and artifact descriptors. It should not infer filesystem paths or model internals. The backend translates UI requests into staged run bundles and passes those bundles to the model runtime.

## 2. Backend Handoff State

FastAPI composition root: `backend/api_service/main.py`. Route modules live under `backend/api_service/api/routers`. Service modules own platform state, datasets, artifact storage, reports, model catalogs, and user context. Runtime contracts live under `backend/api_service/runtime`.

Provider replacement points for cloud deployment are explicit: authentication/user context, platform repository, dataset repository, artifact storage, runtime event store, execution queue, and model subprocess or container runner. The local reference uses SQLite and local filesystem storage only as replaceable implementations.

The canonical public flow is:

`session -> projects -> draft run -> submit run -> execution status/events -> run summary/development/integrated results -> artifact/report/export downloads`

## 3. Model Runtime Boundary

The model package lives under `model_runtime`. Its model manifest, dataset manifest, and architecture catalog define the runtime contract. The backend should load and expose those manifests rather than hard-coding model internals.

The current executable energy engine is Calliope. A future alternative engine module exists as a disabled/planned placeholder and should not be advertised as executable until its runtime implementation and dependencies are complete. MRIO/development logic is packaged as a separate model module within the same model runtime boundary.

Run execution uses staged bundles with `inputs`, `work`, `artifacts`, `logs`, and `exports`. The artifact policy in `inputs/runtime_config.json` controls whether intermediate outputs are retained, embedded in final payloads, included in bundles, or exposed for download.

## 4. Frontend Contract

The frontend workspace is graph-centered but model-architecture driven. It loads the runtime architecture catalog from the backend where possible and falls back to the bundled static model architecture catalog only for offline/local resilience.

The UI should continue to render from backend DTOs: project summaries, run summaries, run status/events, artifact descriptors, dataset catalog entries, model runtime catalog entries, and report/export descriptors. It should not depend on raw run directory layout.

## 5. Required Backend Acceptance Checks

Before handoff, run the static frontend build, backend unit tests, Python compile check, diff whitespace check, and backend handoff smoke test. The smoke test validates the current project-owned run flow, manifest endpoint, event stream, artifacts, reports, and exports.

Recommended local startup: create `backend/.venv` with Python 3.11, install backend requirements, install the model runtime editable package with no build isolation, build frontend assets, then run `scripts/run_local.py` from the activated environment.

## 6. Canonical Files To Read First

- [BACKEND_HANDOFF.md](BACKEND_HANDOFF.md): backend deployment contract and provider replacement map.
- [SYSTEM_DOCUMENTATION.md](../system/SYSTEM_DOCUMENTATION.md): full system architecture, runtime flow, artifact policy, and operational details.
- [README.md](../../README.md): local setup, run commands, frontend/backend overview, and verification commands.
- [model_runtime/README.md](../../model_runtime/README.md): black-box model package contract, manifests, and Python runtime constraints.
- [EDIM_model_io_catalog.csv](../model/EDIM_model_io_catalog.csv) and [EDIM_model_io_catalog.xlsx](../model/EDIM_model_io_catalog.xlsx): input/output catalog for datasets, generated artifacts, API payloads, and model outputs.
