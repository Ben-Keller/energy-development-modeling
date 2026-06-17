# Backend Tools

Utility scripts for backend smoke tests, handoff checks, and post-run analysis/visuals.

- `backend_handoff_smoke.py`: deployment-oriented HTTP smoke test for the user/project/run/artifact/export contract against an already-running backend.
- `smoke_check.py`: local smoke helper that starts a temporary backend process and can optionally run a model.
- `model_readiness_audit.py`: model/data readiness checks for a scenario or completed run.
- `generate_refinement_visuals.py`: builds SVG figures from the latest run in `outputs/runs/`.

## Handoff Usage

Backend/cloud teams should run `backend_handoff_smoke.py` against the same
subprocess runtime contract used in local development.

```bash
python3 scripts/run_local.py --port 8000
python backend/tools/backend_handoff_smoke.py --base-url http://127.0.0.1:8000 --user-id undp_analyst --timeout-seconds 900
```

Passing this script means the hosted backend can resolve users, create projects,
verify `/api/system/manifest`, submit project-owned runs, observe execution
events, verify the configured runtime artifact handoff and dataset staging modes, verify the
`execution_queue_message` payload embedded in the run bundle, verify
`execution_retry_policy` and `execution_attempt` worker lifecycle
metadata, download artifacts, generate Markdown reports plus report source-data
JSON, and build export bundles through the public API contract.
By default the script uses the lightweight `energy-only` architecture with the
transmission-only `new_links` scenario and `dev` time slice. Add
`--model-architecture-id energy-development` when the full bridge/MRIO path
needs to be smoke tested. The script executes the real packaged model, so local
Calliope solves should use a multi-minute timeout.
