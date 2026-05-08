from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

import yaml

from .schemas import ScenarioInfo
from .scenario_package import build_integrated_scenario_catalog


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    out: List[Dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if isinstance(row, dict):
                out.append({str(k): str(v) for k, v in row.items()})
    return out


def _parse_tags(raw: str) -> List[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    # Accept "|" (preferred) and "," separators for convenience.
    if "|" in text:
        parts = [piece.strip() for piece in text.split("|")]
    else:
        parts = [piece.strip() for piece in text.split(",")]
    return [tag for tag in parts if tag]


def load_scenarios_from_overrides(overrides_path: Path) -> List[str]:
    """Return sorted scenario keys from Calliope overrides.yaml."""
    data = _load_yaml(overrides_path)
    scenarios = data.get("scenarios", {})
    if not isinstance(scenarios, dict):
        return []
    return sorted(list(scenarios.keys()))


def load_scenario_metadata(metadata_path: Path) -> Dict[str, ScenarioInfo]:
    """Load UI metadata from inputs/scenario_metadata.csv."""
    if not metadata_path.exists():
        return {}
    out: Dict[str, ScenarioInfo] = {}
    for row in _read_csv_rows(metadata_path):
        key = str(row.get("key", "")).strip()
        if not key:
            continue
        preset_levers: Dict[str, float] = {}
        for lever_key in (
            "demand_multiplier",
            "renewables_capex_multiplier",
            "fossil_fuel_price_multiplier",
            "carbon_price_usd_per_tco2",
        ):
            raw_value = str(row.get(lever_key, "")).strip()
            if not raw_value:
                continue
            try:
                preset_levers[lever_key] = float(raw_value)
            except (TypeError, ValueError):
                continue
        out[key] = ScenarioInfo(
            key=key,
            title=str(row.get("title", key)).strip() or key,
            description=str(row.get("description", "")).strip(),
            tags=_parse_tags(row.get("tags", "")),
            policy_question=str(row.get("policy_question", "")).strip(),
            expected_tradeoff=str(row.get("expected_tradeoff", "")).strip(),
            user_label=str(row.get("user_label", "")).strip(),
            preset_levers=preset_levers,
        )
    return out


def build_scenario_list(overrides_path: Path, metadata_path: Path) -> List[ScenarioInfo]:
    """Merge scenario keys from overrides.yaml with optional UI metadata."""
    keys = load_scenarios_from_overrides(overrides_path)
    metadata = load_scenario_metadata(metadata_path)
    out: List[ScenarioInfo] = []
    for key in keys:
        if key in metadata:
            out.append(metadata[key])
        else:
            out.append(ScenarioInfo(key=key, title=key, description="", tags=[]))
    return out


def build_integrated_catalog(overrides_path: Path, metadata_path: Path, config_dir: Path, calliope_root: Path) -> Dict[str, object]:
    """Build the unified energy + MRIO scenario catalog for the UI/API."""
    energy_scenarios = [s.model_dump() for s in build_scenario_list(overrides_path, metadata_path)]
    return build_integrated_scenario_catalog(
        config_dir=config_dir,
        calliope_root=calliope_root,
        energy_scenarios=energy_scenarios,
    )
