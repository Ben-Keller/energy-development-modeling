from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[2]
for _candidate in (REPO_ROOT, REPO_ROOT / "backend", REPO_ROOT / "model_runtime"):
    _path = str(_candidate)
    if _path not in sys.path:
        sys.path.insert(0, _path)

from model_runtime.edim_model.core.mario_runtime import (
    load_development_indicator_mapping,
    load_scenario_assumptions,
    mario_inputs_health,
)
from api_service.settings import get_settings


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _geo_placeholder_summary(repo_root: Path) -> Dict[str, Any]:
    path = repo_root / "frontend" / "geo" / "edim_locations_placeholder.geojson"
    payload = _read_json(path)
    features = payload.get("features") if isinstance(payload, dict) else []
    if not isinstance(features, list):
        features = []
    placeholder_count = 0
    for feature in features:
        props = (feature or {}).get("properties") or {}
        if props.get("placeholder_geometry"):
            placeholder_count += 1
    return {
        "path": str(path),
        "exists": path.exists(),
        "placeholder_feature_count": placeholder_count,
        "is_placeholder_collection": bool(payload.get("is_placeholder")) if isinstance(payload, dict) else False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit EDIM data readiness and data-readiness diagnostics.")
    parser.add_argument("--scenario", default="baseline", help="Scenario key used for assumption matching.")
    parser.add_argument("--run-id", default="", help="Optional run_id to inspect coupling diagnostics.")
    args = parser.parse_args()

    settings = get_settings()
    repo_root = Path(__file__).resolve().parents[2]

    mario_health = mario_inputs_health(settings.config_dir)
    assumptions = load_scenario_assumptions(settings.config_dir, scenario_key=str(args.scenario or ""))
    indicators = load_development_indicator_mapping(settings.config_dir)
    geo_summary = _geo_placeholder_summary(repo_root)

    payload: Dict[str, Any] = {
        "scenario": str(args.scenario or ""),
        "mario_inputs": mario_health,
        "scenario_assumptions": {
            "path": assumptions.get("path"),
            "selected_count": assumptions.get("selected_count"),
            "selected_placeholder_row_count": assumptions.get("selected_placeholder_row_count"),
        },
        "development_indicator_mapping": {
            "path": indicators.get("path"),
            "record_count": indicators.get("record_count"),
            "exists": indicators.get("exists"),
        },
        "geo_placeholders": geo_summary,
    }

    run_id = str(args.run_id or "").strip()
    if run_id:
        run_dir = settings.runs_dir / run_id
        coupling_manifest = _read_json(run_dir / "artifacts" / "final" / "coupling_manifest.json") or _read_json(run_dir / "coupling_manifest.json")
        payload["run_artifact_diagnostics"] = {
            "run_id": run_id,
            "coupling_manifest_found": bool(coupling_manifest),
            "placeholder_input_row_count": int(coupling_manifest.get("placeholder_input_row_count", 0) or 0),
            "strict_validation": bool(coupling_manifest.get("strict_validation", False)),
        }

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
