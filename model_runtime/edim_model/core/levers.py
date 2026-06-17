from __future__ import annotations

from dataclasses import dataclass
import csv
import fnmatch
from pathlib import Path
from typing import List, Tuple, Any

from .schemas import LeverValues

DEFAULT_RENEWABLES_TECHS = [
    "PV*",
    "Wind*",
    "CSP*",
    "Hydro_Large*",
    "Hydro_Small*",
    "Geothermal",
    "Nuclear",
]
DEFAULT_FOSSIL_TECHS = [
    "Coal_pp",
    "CCGT*",
    "OCGT*",
    "HFO_pp",
    "Steam_Gas_pp",
    "Diesel_Engine",
    "Gas_Engine",
]
DEFAULT_CAPEX_KEY_PATH = ["costs", "monetary", "energy_cap"]
DEFAULT_FUEL_COST_KEY_PATH = ["costs", "monetary", "om_con"]
DEFAULT_CARBON_PRICE_PATH = ["run", "objective_options", "cost_class", "co2"]

@dataclass
class LeverMappings:
    # Tech groupings and the YAML paths used to apply multipliers.
    renewables_techs: List[str]
    fossil_techs: List[str]
    # Where to apply CAPEX multiplier for a tech (relative key path)
    capex_key_path: List[str]
    # Where to apply fuel cost multiplier (relative key path)
    fuel_cost_key_path: List[str]
    # Optional: path where carbon price should be written (absolute path from override root)
    carbon_price_path: List[str]


def _read_csv_rows(path: Path) -> List[dict]:
    if not path.exists():
        return []
    out: List[dict] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if isinstance(row, dict):
                out.append({str(k): str(v) for k, v in row.items()})
    return out


def _parse_path(value: str, default: List[str]) -> List[str]:
    raw = str(value or "").strip()
    if not raw:
        return list(default)
    parts = [part.strip() for part in raw.split(".") if part.strip()]
    return parts or list(default)


def load_lever_mappings(config_dir: Path) -> LeverMappings:
    path = config_dir / "lever_mappings.csv"
    rows = _read_csv_rows(path)
    renewables_techs = list(DEFAULT_RENEWABLES_TECHS)
    fossil_techs = list(DEFAULT_FOSSIL_TECHS)
    capex_key_path = list(DEFAULT_CAPEX_KEY_PATH)
    fuel_cost_key_path = list(DEFAULT_FUEL_COST_KEY_PATH)
    carbon_price_path = list(DEFAULT_CARBON_PRICE_PATH)

    if rows:
        renewables_techs = []
        fossil_techs = []
        for row in rows:
            key = str(row.get("key", "")).strip().lower()
            value = str(row.get("value", "")).strip()
            if not key or not value:
                continue
            if key == "renewables_tech":
                renewables_techs.append(value)
            elif key == "fossil_tech":
                fossil_techs.append(value)
            elif key == "capex_key_path":
                capex_key_path = _parse_path(value, DEFAULT_CAPEX_KEY_PATH)
            elif key == "fuel_cost_key_path":
                fuel_cost_key_path = _parse_path(value, DEFAULT_FUEL_COST_KEY_PATH)
            elif key == "carbon_price_path":
                carbon_price_path = _parse_path(value, DEFAULT_CARBON_PRICE_PATH)

        if not renewables_techs:
            renewables_techs = list(DEFAULT_RENEWABLES_TECHS)
        if not fossil_techs:
            fossil_techs = list(DEFAULT_FOSSIL_TECHS)

    return LeverMappings(
        renewables_techs=renewables_techs,
        fossil_techs=fossil_techs,
        capex_key_path=capex_key_path,
        fuel_cost_key_path=fuel_cost_key_path,
        carbon_price_path=carbon_price_path,
    )

def _resolve_tech_group(specs: List[str], available_techs: List[str]) -> Tuple[List[str], List[str]]:
    """
    Resolve a list of exact tech names and/or glob patterns against available techs.
    Returns (matches, unresolved_specs).
    """
    matched: set[str] = set()
    unresolved: List[str] = []
    for spec in specs:
        spec = str(spec).strip()
        if not spec:
            continue
        if spec in available_techs:
            matched.add(spec)
            continue
        pattern_matches = [t for t in available_techs if fnmatch.fnmatch(t, spec)]
        if pattern_matches:
            matched.update(pattern_matches)
            continue
        unresolved.append(spec)
    return sorted(matched), unresolved

def _set_nested(d: dict, path: List[str], value: Any) -> None:
    cur = d
    for p in path[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    cur[path[-1]] = value

def _get_nested(d: dict, path: List[str]) -> Tuple[bool, Any]:
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return False, None
        cur = cur[p]
    return True, cur

def build_lever_override_patch(
    levers: LeverValues,
    mappings: LeverMappings,
    base_tech_library: dict,
) -> Tuple[dict, List[str]]:
    """
    Returns (override_dict_patch, warnings).

    We implement levers as a Calliope override patch (nested dict) that can be passed
    as override_dict when building the model.

    IMPORTANT:
    - This relies on tech names matching those in the Calliope-Africa tech library.
    - If keys/techs don't exist, we skip and add a warning.
    """
    warnings: List[str] = []
    patch: dict = {"techs": {}}
    available_techs = sorted((base_tech_library.get("techs") or {}).keys())
    renewables_techs, unresolved_renewables = _resolve_tech_group(mappings.renewables_techs, available_techs)
    fossil_techs, unresolved_fossil = _resolve_tech_group(mappings.fossil_techs, available_techs)

    for spec in unresolved_renewables:
        warnings.append(f"Renewables CAPEX lever: mapping spec '{spec}' matched no techs; skipped.")
    for spec in unresolved_fossil:
        warnings.append(f"Fossil fuel price lever: mapping spec '{spec}' matched no techs; skipped.")

    # Apply renewables CAPEX multiplier
    if levers.renewables_capex_multiplier != 1.0 and renewables_techs:
        for tech in renewables_techs:
            exists, cur_val = _get_nested(base_tech_library["techs"][tech], mappings.capex_key_path)
            if not exists or not isinstance(cur_val, (int, float)):
                warnings.append(f"Renewables CAPEX lever: key path {mappings.capex_key_path} not numeric for tech '{tech}'; skipped.")
                continue
            new_val = float(cur_val) * float(levers.renewables_capex_multiplier)
            patch["techs"].setdefault(tech, {})
            _set_nested(patch["techs"][tech], mappings.capex_key_path, new_val)

    # Apply fossil fuel price multiplier (often om_prod or carrier costs depending on model)
    if levers.fossil_fuel_price_multiplier != 1.0 and fossil_techs:
        for tech in fossil_techs:
            exists, cur_val = _get_nested(base_tech_library["techs"][tech], mappings.fuel_cost_key_path)
            if not exists or not isinstance(cur_val, (int, float)):
                warnings.append(f"Fossil fuel price lever: key path {mappings.fuel_cost_key_path} not numeric for tech '{tech}'; skipped.")
                continue
            new_val = float(cur_val) * float(levers.fossil_fuel_price_multiplier)
            patch["techs"].setdefault(tech, {})
            _set_nested(patch["techs"][tech], mappings.fuel_cost_key_path, new_val)

    # Apply carbon price if mapping exists.
    if levers.carbon_price_usd_per_tco2 and mappings.carbon_price_path:
        _set_nested(patch, mappings.carbon_price_path, float(levers.carbon_price_usd_per_tco2))
    elif levers.carbon_price_usd_per_tco2 and not mappings.carbon_price_path:
        warnings.append("Carbon price lever set, but carbon_price_path is not configured; lever ignored.")

    # Clean empty techs
    if not patch["techs"]:
        patch.pop("techs", None)

    return patch, warnings
