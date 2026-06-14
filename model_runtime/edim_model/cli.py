"""CLI entry point for the EDIM model runtime.

Contract (plan 7.2):
  python -m edim_model.cli catalog
  python -m edim_model.cli preflight --bundle <path>
  python -m edim_model.cli run --bundle <path>

The CLI is intentionally thin while the backend orchestration modules are being
refactored into this runtime package. For now it delegates to the existing
backend logic so the local worker can execute real Calliope runs end-to-end.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

# The worker image adds both /app/backend and /app/model_runtime to PYTHONPATH.
from backend.api_service.scenarios import build_integrated_catalog
from backend.api_service.runner import run_calliope_synchronously
from backend.api_service.schemas import RunRequest
from backend.api_service.settings import get_settings

logger = logging.getLogger("edim_model.cli")


def _load_bundle(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Bundle must be a JSON object.")
    return payload


def _bundle_to_run_request(bundle: dict[str, Any]) -> RunRequest:
    request = bundle.get("request_payload") or bundle
    return RunRequest(**request)


def cmd_catalog(args: argparse.Namespace) -> int:
    settings = get_settings()
    overrides_path = settings.calliope_root / "overrides.yaml"
    metadata_path = settings.config_dir / "scenario_metadata.csv"
    catalog = build_integrated_catalog(
        overrides_path=overrides_path,
        metadata_path=metadata_path,
        config_dir=settings.config_dir,
        calliope_root=settings.calliope_root,
    )
    print(json.dumps(catalog, indent=2, default=str))
    return 0


def cmd_preflight(args: argparse.Namespace) -> int:
    bundle_path = Path(args.bundle)
    if not bundle_path.is_file():
        logger.error("Bundle file not found: %s", bundle_path)
        return 1

    try:
        bundle = _load_bundle(bundle_path)
        req = _bundle_to_run_request(bundle)
    except Exception as exc:
        logger.error("Invalid bundle: %s", exc)
        return 1

    result = {
        "valid": True,
        "execution_id": bundle.get("execution_id"),
        "run_id": bundle.get("run_id"),
        "request": req.model_dump(mode="json"),
    }
    print(json.dumps(result, indent=2, default=str))
    return 0


def _progress(stage: str, progress: float, message: str) -> None:
    event = {
        "timestamp": "",
        "level": "milestone" if progress in (0.0, 1.0) else "info",
        "stage": stage,
        "message": message,
        "progress": progress,
    }
    print(json.dumps(event, default=str))
    sys.stdout.flush()


def cmd_run(args: argparse.Namespace) -> int:
    bundle_path = Path(args.bundle)
    if not bundle_path.is_file():
        logger.error("Bundle file not found: %s", bundle_path)
        return 1

    try:
        bundle = _load_bundle(bundle_path)
        req = _bundle_to_run_request(bundle)
    except Exception as exc:
        logger.error("Invalid bundle: %s", exc)
        return 1

    settings = get_settings()
    try:
        run_id, summary, warnings, run_dir = run_calliope_synchronously(
            settings=settings,
            req=req,
            progress_callback=_progress,
            cancel_requested=None,
        )
    except Exception as exc:
        logger.exception("Model run failed.")
        return 1

    result = {
        "ok": True,
        "execution_id": bundle.get("execution_id"),
        "run_id": run_id,
        "run_dir": str(run_dir),
        "warnings": warnings,
        "summary": summary,
    }
    print(json.dumps(result, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(prog="edim_model.cli", description="EDIM model runtime CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    catalog_parser = subparsers.add_parser("catalog", help="Return scenario and architecture catalogs.")
    catalog_parser.set_defaults(func=cmd_catalog)

    preflight_parser = subparsers.add_parser("preflight", help="Validate a run bundle without solving.")
    preflight_parser.add_argument("--bundle", required=True, type=str, help="Path to request_bundle.json")
    preflight_parser.set_defaults(func=cmd_preflight)

    run_parser = subparsers.add_parser("run", help="Execute a full model run from a bundle.")
    run_parser.add_argument("--bundle", required=True, type=str, help="Path to request_bundle.json")
    run_parser.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
