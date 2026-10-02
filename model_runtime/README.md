# EDIM Model Runtime

This folder is the black-box model package handed to backend/cloud teams.

Use Python 3.11 for this package. The current executable Calliope module pins
`calliope==0.6.10` and `numpy==1.23.5`, so Python 3.12+ is intentionally not
declared as supported.

## Commands

```bash
python -m edim_model.cli run --bundle /path/to/request_bundle.json
python -m edim_model.cli preflight --bundle /path/to/request_bundle.json
python -m edim_model.cli catalog --config-dir /path/to/inputs --manifest /path/to/model_manifest.json
```

The runtime reads only the `model_run_bundle_v1` bundle, emits `runtime_event_v1` JSONL to stdout, writes declared artifacts under the configured run package, and finishes with a `result` event containing `run_id` and `payload.summary`.

The backend allocates `run_id` before execution starts. The runtime should preserve that id exactly and write artifacts under the run package specified by `runtime_settings.runs_dir` and `run_id`.

## Runtime Responsibilities

The runtime owns model execution only:

- Validate model-specific input readiness in `preflight`.
- Read scenario, dataset, runtime, and artifact policy data from the bundle.
- Run the model.
- Emit progress as `runtime_event_v1` JSONL.
- Write only declared artifacts or runtime-private work files.
- Emit one final `result` event containing the final summary payload.

The runtime must not own platform concerns:

- user authorization
- project membership
- report/export APIs
- frontend URLs
- durable queue semantics
- direct Blob/database access unless the selected cloud handoff mode explicitly assigns upload responsibility to the runtime

This separation is what lets backend teams host updated model versions without changing route or frontend code.

Cloud deployments must choose one artifact handoff mode explicitly:

- shared mounted storage at `runtime_settings.runs_dir`;
- runtime-side upload to object storage with artifact object keys emitted in the final result event;
- worker-side upload from ephemeral runtime storage before marking the run terminal.

The API layer should continue to expose artifact ids rather than raw runtime paths.

## Event Contract

Each line written to stdout should be a JSON object with:

- `schema_version`: `runtime_event_v1`
- `type`: `stage_started`, `progress`, `warning`, `error`, `stage_completed`, or `result`
- `stage`: current stage key when applicable
- `progress`: numeric share between `0` and `1` when applicable
- `message`: user-facing status text
- `run_id`: stable run namespace
- `payload`: event-specific metadata

The final event must be:

```json
{
  "schema_version": "runtime_event_v1",
  "type": "result",
  "run_id": "<stable run id>",
  "payload": {
    "summary": {
      "run_id": "<stable run id>",
      "artifact_catalog": []
    }
  }
}
```

The backend uses this event as the completion handshake.

## Files

- `edim_model/model_manifest.json`: executable contract.
- `edim_model/dataset_manifest.json`: input dataset contract.
- `edim_model/architecture_catalog.json`: model-owned graph/result-surface catalog served by `/api/model-runtimes`.
- `edim_model/cli.py`: process entrypoint.
- `edim_model/core/orchestration.py`: model-agnostic ordered stage runner with progress/cancellation semantics.
- `edim_model/core/edim_pipeline.py`: EDIM-specific stage sequence that wires scenario preparation, selected model
  modules, summaries, development outputs, and final artifacts.
- `edim_model/local_runtime.py`: black-box bundle executor used by the CLI. Its primary entrypoint is `execute_bundle`.
- `edim_model/core/runner.py`: shared model-core helpers and the model-neutral `run_model_synchronously` entrypoint.
  Keep new architecture orchestration in pipeline modules rather than adding another inline runner.
- `edim_model/modules/`: model module registry and per-module implementation boundaries.
  - `calliope.py`: executable Calliope energy module.
  - `mrio.py`: executable MARIO development-impact module.
- `model_modules/`: bundled model assets organized by engine. The current Calliope source lives at
  `model_modules/calliope/Calliope-Africa-main/`; future model engines should add sibling directories under
  `model_modules/<engine>/` rather than adding large model source folders at the repository root.
- `edim_model/contracts.py`: shared artifact registry, run package layout, artifact retention policy loader, and runtime
  event helpers. Keep this file backend-neutral; it is the only shared contract module used across API and runtime code.
- `Dockerfile`: container packaging reference.

Run bundles include `queue_message.schema_version = execution_queue_message`, `queue_message.retry_policy.schema_version = execution_retry_policy`, and `dataset_manifest.dataset_staging.schema_version = dataset_staging_v1`. Runtimes should read the per-dataset `path` field for local `reference` and `copy_to_run` modes, and should use `storage_ref` for cloud `object_reference` mode once a storage-backed worker implementation is available. Worker lifecycle is not owned by the model package; the backend worker records it as `execution_attempt` while invoking this runtime.

`preflight` is self-contained inside this package. The `run` command uses `edim_model/local_runtime.py::execute_bundle` as a runtime bridge over the packaged model core in `edim_model/core`; backend/API code is not imported by the runtime package. This keeps the hosting boundary stable while the model internals continue to evolve.

## Model Modules

The runtime is organized around a module registry in `edim_model/modules/registry.py`.

- Energy modules are selected by `request.energy_model_engine`.
- Development modules are selected by `runtime_settings.development_engine`.
- `model_manifest.json` exposes the same module catalog to the backend through its `modules` field.
- `catalog` exposes module-owned scenario channels and architecture metadata to `/api/scenarios` and `/api/model-runtimes`.
- `preflight` checks the selected module status before a run starts.

Current modules:

- `calliope`: ready, executable energy optimization module.
- `osemosys`: planned energy optimization boundary; selectable only after an executable package is supplied.
- `mrio`: ready, development layer consuming bridge-derived and MRIO-direct inputs.

## Adding A New Model Runtime

To add another model without changing backend APIs:

1. Add a model package with the same CLI shape.
2. Add a `model_manifest.json` with a new `model_id`, `model_version`, supported engines, entrypoints, and declared outputs.
3. Ensure the package consumes `model_run_bundle_v1`.
4. Ensure the package emits `runtime_event_v1`.
5. Keep model-specific validation inside `preflight`.
6. Add required input datasets to a dataset manifest.
7. Update the runtime catalog/default selection only after `preflight` and the backend handoff smoke test pass.
