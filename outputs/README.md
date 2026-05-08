# Outputs

Generated local artifacts are written here. Runtime output data is intentionally
ignored by git; this folder keeps only the structure and operational notes.

- `runs/<run_id>/`: structured model run package.
  - `inputs/`: immutable request bundle and staged dataset references/copies.
  - `work/`: temporary runtime workspace and droppable intermediates.
  - `artifacts/`: durable declared model artifacts governed by `inputs/runtime_config.json`.
  - `logs/`: user-facing and technical runtime logs.
  - `exports/`: run-level export bundles and generated reports.
- `platform/`: local SQLite metadata, project reports, and project export files.
- `dataset_uploads/`: user-owned uploaded dataset versions used by local runs.
- `figures/`: optional generated SVG charts from backend utility scripts.

Before a formal demo or handoff smoke test, clear ignored runtime state if you
need a clean project/run list. Do not commit generated files from this directory.
