from __future__ import annotations

"""Structured MRIO scenario target input loader.

The original narrative scenario report is not a runtime dependency. Scenario
content used by the model is stored as structured repo inputs:

- inputs/generated/scenario_report_scenarios.json: machine-readable scenario payload
- inputs/mario_inputs/scenario_report_scenarios.csv: analyst-readable extracted table
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict


SCENARIO_REPORT_SCHEMA_VERSION = "scenario_report_v1"
STRUCTURED_REPORT_JSON = Path("generated") / "scenario_report_scenarios.json"
STRUCTURED_REPORT_CSV = Path("mario_inputs") / "scenario_report_scenarios.csv"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_or_parse_scenario_report(config_dir: Path, report_path: Path | None = None) -> Dict[str, Any]:
    """Load structured scenario target data.

    The function name is retained for internal caller stability, but it no
    loads only structured scenario targets. Passing a non-JSON path is rejected so the
    model cannot silently reintroduce narrative documents as runtime inputs.
    """
    config_dir = config_dir.resolve()
    source_path = (report_path or (config_dir / STRUCTURED_REPORT_JSON)).resolve()
    if source_path.suffix.lower() != ".json":
        raise ValueError("Scenario target data must be supplied as structured JSON.")
    if not source_path.exists():
        raise FileNotFoundError(f"Structured scenario report input not found: {source_path}")

    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != SCENARIO_REPORT_SCHEMA_VERSION:
        raise ValueError(f"Structured scenario report input is malformed: {source_path}")
    if not isinstance(payload.get("scenarios"), dict) or not payload.get("scenario_ids"):
        raise ValueError(f"Structured scenario report input has no scenarios: {source_path}")

    csv_path = config_dir / STRUCTURED_REPORT_CSV
    payload = dict(payload)
    payload["source_file"] = str(csv_path.relative_to(config_dir.parent) if csv_path.exists() else source_path.relative_to(config_dir.parent))
    payload["source_sha256"] = _sha256(csv_path if csv_path.exists() else source_path)
    return payload
