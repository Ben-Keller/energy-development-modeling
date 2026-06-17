from __future__ import annotations

import csv
import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .scenario_report import load_or_parse_scenario_report


HEURISTIC_METHOD = "mrio_direct_heuristic_v1"
SUBNATIONAL_RE = re.compile(r"^[A-Z]{3}_.+")
COUNTRY_ALIAS = {
    "ZA": "ZAF",
    "BR": "BRA",
    "IN": "IND",
}

AFRICA_MRIO_SCENARIO_LABELS = {
    "S1": {
        "label": "S1 - Full decarbonization",
        "short_label": "Full decarbonization",
        "scenario_type": "full_decarbonization",
        "description": (
            "Africa-wide national placeholder scenario. South Africa uses the ZA-S1 report record; "
            "all other African countries use Rest-of-Africa WF-S1 assumptions until country-specific "
            "expert MRIO scenario records are supplied."
        ),
    },
    "S2": {
        "label": "S2 - National policy target",
        "short_label": "National policy target",
        "scenario_type": "policy_target",
        "description": (
            "Africa-wide national placeholder scenario. South Africa uses the ZA-S2 report record; "
            "all other African countries use Rest-of-Africa WF-S2 assumptions until country-specific "
            "expert MRIO scenario records are supplied."
        ),
    },
}

AFRICAN_COUNTRY_NAMES = {
    "AGO": "Angola",
    "BDI": "Burundi",
    "BEN": "Benin",
    "BFA": "Burkina Faso",
    "BWA": "Botswana",
    "CAF": "Central African Republic",
    "CIV": "Cote d'Ivoire",
    "CMR": "Cameroon",
    "COD": "Democratic Republic of the Congo",
    "COG": "Republic of the Congo",
    "COM": "Comoros",
    "CPV": "Cabo Verde",
    "DJI": "Djibouti",
    "DZA": "Algeria",
    "EGY": "Egypt",
    "ERI": "Eritrea",
    "ETH": "Ethiopia",
    "GAB": "Gabon",
    "GHA": "Ghana",
    "GIN": "Guinea",
    "GMB": "Gambia",
    "GNB": "Guinea-Bissau",
    "GNQ": "Equatorial Guinea",
    "KEN": "Kenya",
    "LBR": "Liberia",
    "LBY": "Libya",
    "LSO": "Lesotho",
    "MAR": "Morocco",
    "MDG": "Madagascar",
    "MLI": "Mali",
    "MOZ": "Mozambique",
    "MRT": "Mauritania",
    "MUS": "Mauritius",
    "MWI": "Malawi",
    "NAM": "Namibia",
    "NER": "Niger",
    "NGA": "Nigeria",
    "RWA": "Rwanda",
    "SDN": "Sudan",
    "SEN": "Senegal",
    "SLE": "Sierra Leone",
    "SOM": "Somalia",
    "SSD": "South Sudan",
    "STP": "Sao Tome and Principe",
    "SWZ": "Eswatini",
    "SYC": "Seychelles",
    "TCD": "Chad",
    "TGO": "Togo",
    "TUN": "Tunisia",
    "TZA": "Tanzania",
    "UGA": "Uganda",
    "ZAF": "South Africa",
    "ZMB": "Zambia",
    "ZWE": "Zimbabwe",
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return [{str(k): str(v) for k, v in row.items()} for row in csv.DictReader(f) if isinstance(row, dict)]


def _write_csv(path: Path, rows: List[Dict[str, Any]], columns: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def _percent_to_float(raw: Any) -> float | None:
    text = str(raw or "").replace("~", "").strip()
    match = re.search(r"[-+]?\d+(?:\.\d+)?\s*%", text)
    if not match:
        return None
    try:
        return float(match.group(0).replace("%", "").strip()) / 100.0
    except ValueError:
        return None


def _target_value_for_year(row: Dict[str, Any], target_year: int) -> str:
    if int(target_year) <= 2030:
        return str(row.get("target_2030", "")).strip()
    return str(row.get("target_2050", "")).strip()


def _load_calliope_locations(calliope_root: Path) -> List[str]:
    out: set[str] = set()
    for path in calliope_root.glob("**/*.yaml"):
        try:
            import yaml

            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        locs = data.get("locations") or {}
        if isinstance(locs, dict):
            for loc in locs.keys():
                key = str(loc).strip()
                if key:
                    out.add(key)
    return sorted(out)


def _african_country_rows(config_dir: Path) -> List[Dict[str, str]]:
    """Return one national row per African country, enriched by model geography mapping where present."""
    rows: Dict[str, Dict[str, str]] = {
        code: {
            "country_code": code,
            "country_name": name,
            "source_mapping_code": "ZA" if code == "ZAF" else "WF",
            "source": "african_country_placeholder_seed",
        }
        for code, name in AFRICAN_COUNTRY_NAMES.items()
    }
    for row in _read_csv_rows(config_dir / "scenario_geography_mapping.csv"):
        mrio_geo = str(row.get("mrio_geography_code", "")).strip()
        country = str(row.get("calliope_country_code", "")).strip().upper()
        if not country:
            continue
        if mrio_geo == "ZA":
            country = "ZAF"
        if mrio_geo not in {"ZA", "WF"}:
            continue
        rows[country] = {
            "country_code": country,
            "country_name": AFRICAN_COUNTRY_NAMES.get(country, country),
            "source_mapping_code": mrio_geo,
            "source": "scenario_geography_mapping.csv",
        }
    return [rows[key] for key in sorted(rows)]


def _annotate_shock_row(row: Dict[str, Any], record: Dict[str, Any], archetype_id: str) -> Dict[str, Any]:
    row["scenario_id"] = str(record.get("scenario_id", ""))
    row["scenario_archetype_id"] = archetype_id
    row["source_report_scenario_id"] = str(record.get("source_report_scenario_id", ""))
    row["placeholder"] = bool(record.get("placeholder", False))
    row["placeholder_method"] = str(record.get("placeholder_method", ""))
    return row


def _scenario_summary_drivers(summary: Dict[str, Any], target_year: int) -> Tuple[float, float]:
    fossil_delta = _safe_float(summary.get("fossil_delta_2030_numeric"), 0.0)
    renewable_share = _safe_float(
        summary.get("renewable_share_2030_numeric") if target_year <= 2030 else summary.get("renewable_share_2050_numeric"),
        0.0,
    )
    return fossil_delta, renewable_share


def _generate_direct_shock_rows_for_scenario_record(
    *,
    record: Dict[str, Any],
    archetype_id: str,
    target_year: int,
    base_amount: float,
) -> Tuple[List[Dict[str, Any]], float]:
    record_summary = record.get("summary") or {}
    record_geography_code = str(record.get("geography_code", "") or "").strip()
    record_geography_name = str((record.get("geography") or {}).get("name", "") or record_summary.get("geography_name", "")).strip()
    shock_categories = record.get("shock_categories") or {}
    az_rows = shock_categories.get("A/Z") or []
    e_rows = shock_categories.get("E") or []
    y_rows = shock_categories.get("Y") or []
    fossil_delta, renewable_share = _scenario_summary_drivers(record_summary, target_year)
    fossil_amount = base_amount * abs(fossil_delta)
    renewable_amount = base_amount * max(renewable_share, 0.0)
    rows: List[Dict[str, Any]] = []

    common_notes = str(record.get("notes", "")).strip()
    if fossil_amount > 0:
        fossil_params = [r for r in az_rows if _sector_for_parameter(r.get("parameter", "")) in {"Coal_supply_chain", "Gas_supply_chain", "Oil_supply_chain"}]
        sectors = [_sector_for_parameter(r.get("parameter", "")) for r in fossil_params] or [
            "Coal_supply_chain",
            "Gas_supply_chain",
            "Oil_supply_chain",
        ]
        per_sector = -fossil_amount / max(len(sectors), 1)
        for sector in sectors:
            rows.append(
                _annotate_shock_row(
                    {
                        "shock_category": "A/Z",
                        "parameter": "fossil structural reduction",
                        "mario_parameter": "A/Z",
                        "mario_region": record_geography_code,
                        "geography": record_geography_name,
                        "mario_sector": sector,
                        "target_year": target_year,
                        "shock_value_musd": per_sector,
                        "method": HEURISTIC_METHOD,
                        "notes": "Signed fossil supply-chain reduction derived from report fossil delta target. " + common_notes,
                    },
                    record,
                    archetype_id,
                )
            )

    if renewable_amount > 0:
        allocation = [
            ("Construction_of_power_assets", 0.50),
            ("Electrical_equipment", 0.35),
            ("Transmission_and_distribution", 0.15),
        ]
        for sector, share in allocation:
            rows.append(
                _annotate_shock_row(
                    {
                        "shock_category": "A/Z",
                        "parameter": "renewable structural reallocation",
                        "mario_parameter": "A/Z",
                        "mario_region": record_geography_code,
                        "geography": record_geography_name,
                        "mario_sector": sector,
                        "target_year": target_year,
                        "shock_value_musd": renewable_amount * share,
                        "method": HEURISTIC_METHOD,
                        "notes": "Renewable/grid supply-chain gain derived from report renewable-share target. " + common_notes,
                    },
                    record,
                    archetype_id,
                )
            )

    for y_row in y_rows:
        pct = _percent_to_float(_target_value_for_year(y_row, target_year))
        if pct is None:
            continue
        amount = base_amount * abs(pct)
        rows.append(
            _annotate_shock_row(
                {
                    "shock_category": "Y",
                    "parameter": y_row.get("parameter", ""),
                    "mario_parameter": "Y",
                    "mario_region": record_geography_code,
                    "geography": record_geography_name,
                    "mario_sector": _sector_for_parameter(y_row.get("parameter", ""), "Construction_of_power_assets"),
                    "target_year": target_year,
                    "shock_value_musd": amount,
                    "method": HEURISTIC_METHOD,
                    "notes": "Final-demand proxy from parsed report percentage target. " + common_notes,
                },
                record,
                archetype_id,
            )
        )

    emissions_proxy = 0.0
    for e_row in e_rows:
        pct = _percent_to_float(_target_value_for_year(e_row, target_year))
        if pct is not None:
            emissions_proxy += -abs(pct)
    return rows, emissions_proxy


def _scenario_for_country_from_report(
    *,
    report: Dict[str, Any],
    scenario_code: str,
    country_code: str,
) -> Dict[str, Any]:
    source_prefix = "ZA" if country_code == "ZAF" else "WF"
    source_id = f"{source_prefix}-{scenario_code}"
    source = copy.deepcopy((report.get("scenarios") or {}).get(source_id) or {})
    if not source:
        raise ValueError(f"Required source report scenario '{source_id}' was not found.")
    label_meta = AFRICA_MRIO_SCENARIO_LABELS.get(scenario_code, {})
    country_name = AFRICAN_COUNTRY_NAMES.get(country_code, country_code)
    source["scenario_id"] = f"{country_code}-{scenario_code}"
    source["scenario_code"] = scenario_code
    source["scenario_archetype_id"] = scenario_code
    source["source_report_scenario_id"] = source_id
    source["geography_code"] = country_code
    source["geography"] = {
        "type": "Country",
        "name": country_name,
        "exiobase_code": country_code,
        "source_code_label": country_code,
    }
    source["label"] = label_meta.get("short_label") or source.get("label", scenario_code)
    source["placeholder"] = country_code != "ZAF"
    source["placeholder_method"] = "" if country_code == "ZAF" else "rest_of_africa_report_assumptions_applied_to_national_placeholder"
    source["placeholder_source_report_scenario_id"] = "" if country_code == "ZAF" else source_id
    source["notes"] = (
        "South Africa uses the dedicated scenario report record."
        if country_code == "ZAF"
        else "Placeholder national MRIO scenario generated from the Rest-of-Africa report scenario record."
    )
    summary = dict(source.get("summary") or {})
    summary["scenario_id"] = source["scenario_id"]
    summary["source_report_scenario_id"] = source_id
    summary["geography_name"] = country_name
    summary["placeholder"] = source["placeholder"]
    source["summary"] = summary
    return source


def build_africa_national_mrio_placeholder_scenarios(config_dir: Path, report: Dict[str, Any]) -> Dict[str, Any]:
    countries = _african_country_rows(config_dir)
    scenarios: Dict[str, Dict[str, Any]] = {}
    for scenario_code in ("S1", "S2"):
        label_meta = AFRICA_MRIO_SCENARIO_LABELS[scenario_code]
        records = [
            _scenario_for_country_from_report(
                report=report,
                scenario_code=scenario_code,
                country_code=row["country_code"],
            )
            for row in countries
        ]
        target_years: set[int] = set()
        for record in records:
            target_years.update(int(y) for y in (record.get("target_years") or []) if str(y).isdigit())
        scenarios[scenario_code] = {
            "scenario_id": scenario_code,
            "scenario_code": scenario_code,
            "scenario_type": label_meta["scenario_type"],
            "label": label_meta["label"],
            "short_label": label_meta["short_label"],
            "description": label_meta["description"],
            "geography_code": "AFRICA_NATIONAL",
            "geography": {
                "type": "Country collection",
                "name": "African countries, national placeholder records",
                "exiobase_code": "AFRICA_NATIONAL",
                "source_code_label": "S1/S2 national expansion",
            },
            "target_years": sorted(target_years or {2030, 2050}),
            "national_scenarios": records,
            "national_record_count": len(records),
            "placeholder_record_count": sum(1 for record in records if record.get("placeholder")),
            "source_report_scenario_ids": sorted({str(record.get("source_report_scenario_id", "")) for record in records}),
            "placeholder_method": (
                "South Africa uses ZA-S1/ZA-S2 records from the report; all other African countries use "
                "WF-S1/WF-S2 Rest-of-Africa assumptions as national placeholders."
            ),
            "provenance": {
                "source_file": report.get("source_file", ""),
                "source_sha256": report.get("source_sha256", ""),
                "generated_from": "Energy Modelling Scenario Report.docx + inputs/scenario_geography_mapping.csv",
            },
        }
    return {
        "schema_version": "africa_national_mrio_placeholder_scenarios_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_report_sha256": report.get("source_sha256", ""),
        "country_count": len(countries),
        "countries": countries,
        "scenarios": scenarios,
    }


def write_africa_national_mrio_placeholder_scenarios(config_dir: Path, report: Dict[str, Any]) -> Dict[str, Any]:
    payload = build_africa_national_mrio_placeholder_scenarios(config_dir, report)
    path = config_dir / "generated" / "africa_national_mrio_placeholder_scenarios.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def _target_profile_for_record(record: Dict[str, Any]) -> Dict[str, Any]:
    summary = record.get("summary") or {}
    return {
        "scenario_id": record.get("scenario_id", ""),
        "source_report_scenario_id": record.get("source_report_scenario_id", ""),
        "geography_code": record.get("geography_code", ""),
        "geography_name": (record.get("geography") or {}).get("name", summary.get("geography_name", "")),
        "placeholder": bool(record.get("placeholder", False)),
        "renewable_share_2030": summary.get("renewable_share_2030", ""),
        "renewable_share_2030_numeric": summary.get("renewable_share_2030_numeric"),
        "renewable_share_2050": summary.get("renewable_share_2050", ""),
        "renewable_share_2050_numeric": summary.get("renewable_share_2050_numeric"),
        "fossil_delta_2030": summary.get("fossil_delta_2030", ""),
        "fossil_delta_2030_numeric": summary.get("fossil_delta_2030_numeric"),
        "net_zero_year": summary.get("net_zero_year", ""),
        "net_zero_year_numeric": summary.get("net_zero_year_numeric"),
    }


def _target_scenario_catalog_entry(row: Dict[str, Any]) -> Dict[str, Any]:
    national_records = list(row.get("national_scenarios") or [])
    zaf_record = next((record for record in national_records if record.get("geography_code") == "ZAF"), None)
    placeholder_record = next((record for record in national_records if record.get("placeholder")), None)
    return {
        "scenario_id": row.get("scenario_id", ""),
        "scenario_code": row.get("scenario_code", ""),
        "scenario_type": row.get("scenario_type", ""),
        "label": row.get("label", ""),
        "short_label": row.get("short_label", ""),
        "description": row.get("description", ""),
        "target_years": [int(y) for y in (row.get("target_years") or []) if str(y).isdigit()],
        "national_record_count": row.get("national_record_count", 0),
        "placeholder_record_count": row.get("placeholder_record_count", 0),
        "source_report_scenario_ids": row.get("source_report_scenario_ids", []),
        "placeholder_method": row.get("placeholder_method", ""),
        "target_profiles": {
            "south_africa": _target_profile_for_record(zaf_record or {}),
            "rest_of_africa_placeholder": _target_profile_for_record(placeholder_record or {}),
        },
    }


def _mrio_shock_mapping_options(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "mapping_id": HEURISTIC_METHOD,
            "label": "A/Z, E, and Y heuristic shock mapping",
            "description": (
                "Translates the selected integrated target pathway into separate MRIO-direct A/Z structural, "
                "E emissions-intensity proxy, and Y final-demand proxy rows. Bridge-derived Calliope values remain "
                "authoritative for overlapping headline totals."
            ),
            "shock_categories": report.get("shock_structure") or [],
            "shock_file_structure": report.get("shock_file_structure") or [],
            "calibration_steps": report.get("calibration_steps") or [],
            "method": HEURISTIC_METHOD,
            "model_quality_ceiling": "analyst_review",
        }
    ]


def build_integrated_scenario_catalog(config_dir: Path, calliope_root: Path, energy_scenarios: List[Dict[str, Any]]) -> Dict[str, Any]:
    report = load_or_parse_scenario_report(config_dir)
    africa_mrio = write_africa_national_mrio_placeholder_scenarios(config_dir, report)
    mapping_rows = _read_csv_rows(config_dir / "scenario_geography_mapping.csv")
    target_years: set[int] = set()
    target_scenarios: List[Dict[str, Any]] = []
    for scenario_id in ("S1", "S2"):
        row = dict((africa_mrio.get("scenarios") or {}).get(scenario_id) or {})
        years = [int(y) for y in (row.get("target_years") or []) if str(y).isdigit()]
        target_years.update(years)
        target_scenarios.append(_target_scenario_catalog_entry(row))

    default_energy = ""
    if energy_scenarios:
        keys = {str(row.get("key", "")) for row in energy_scenarios}
        default_energy = "new_links" if "new_links" in keys else str(energy_scenarios[0].get("key", ""))
    default_target = "S2" if any(row.get("scenario_id") == "S2" for row in target_scenarios) else (target_scenarios[0]["scenario_id"] if target_scenarios else "")
    shock_mappings = _mrio_shock_mapping_options(report)
    return {
        "schema_version": "integrated_scenario_catalog_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "energy_model_engines": [
            {"value": "calliope", "label": "Calliope", "runtime_status": "executable"},
            {"value": "osemosys", "label": "OSeMOSYS", "runtime_status": "adapter_target_pending_runtime"},
        ],
        "energy_scenarios": energy_scenarios,
        # "scenarios" is a backward-compat alias used by the smoke test and legacy clients.
        "scenarios": energy_scenarios,
        "target_scenarios": target_scenarios,
        "mrio_shock_mappings": shock_mappings,
        "target_years": sorted(target_years or {2030, 2050}),
        "geography_alignment_options": mapping_rows,
        "report": {
            "source_file": report.get("source_file", ""),
            "source_sha256": report.get("source_sha256", ""),
            "scenario_count": len(report.get("scenario_ids") or []),
            "africa_national_placeholder_dataset": "inputs/generated/africa_national_mrio_placeholder_scenarios.json",
            "africa_national_country_count": africa_mrio.get("country_count", 0),
        },
        "defaults": {
            "energy_scenario_key": default_energy,
            "energy_model_engine": "calliope",
            "target_scenario_id": default_target,
            "mrio_scenario_id": default_target,
            "mrio_shock_mapping_id": shock_mappings[0]["mapping_id"] if shock_mappings else "",
            "target_year": 2030,
        },
    }


def build_geography_alignment(
    *,
    config_dir: Path,
    calliope_root: Path,
    mrio_scenario: Dict[str, Any],
) -> Dict[str, Any]:
    geography_code = str(mrio_scenario.get("geography_code", "")).strip()
    if geography_code == "AFRICA_NATIONAL":
        national_records = list(mrio_scenario.get("national_scenarios") or [])
        calliope_locations = _load_calliope_locations(calliope_root)
        available = set(calliope_locations)
        selected_locations = sorted(
            {
                str(row.get("calliope_location", "")).strip()
                for row in _read_csv_rows(config_dir / "scenario_geography_mapping.csv")
                if str(row.get("mrio_geography_code", "")).strip() in {"ZA", "WF"}
                and str(row.get("calliope_location", "")).strip() in available
            }
        )
        return {
            "status": "aligned" if selected_locations else "mrio_only",
            "blocking_mismatch": False,
            "mrio_geography_code": geography_code,
            "mrio_geography": mrio_scenario.get("geography", {}),
            "calliope_locations": selected_locations,
            "calliope_location_count": len(selected_locations),
            "alignment_level": "africa_national_placeholder_to_calliope_locations",
            "mapping_rows": [
                {
                    "mrio_geography_code": str(record.get("geography_code", "")),
                    "source_report_scenario_id": str(record.get("source_report_scenario_id", "")),
                    "placeholder": str(bool(record.get("placeholder"))),
                    "alignment_level": "national_placeholder",
                    "notes": str(record.get("notes", "")),
                }
                for record in national_records
            ],
            "national_record_count": len(national_records),
            "placeholder_record_count": sum(1 for record in national_records if record.get("placeholder")),
            "notes": (
                "Africa national MRIO scenario applies report-derived national placeholder records. "
                "South Africa uses dedicated ZA report assumptions; all other African country records use Rest-of-Africa assumptions."
            ),
        }

    mapped_rows = [
        row for row in _read_csv_rows(config_dir / "scenario_geography_mapping.csv")
        if str(row.get("mrio_geography_code", "")).strip() == geography_code
    ]
    calliope_locations = _load_calliope_locations(calliope_root)
    available = set(calliope_locations)
    selected_locations = sorted(
        {
            str(row.get("calliope_location", "")).strip()
            for row in mapped_rows
            if str(row.get("calliope_location", "")).strip() in available
        }
    )
    alias_country = COUNTRY_ALIAS.get(geography_code, geography_code)
    if not selected_locations:
        selected_locations = sorted(
            loc for loc in calliope_locations if loc == alias_country or loc.startswith(f"{alias_country}_")
        )

    mrio_subnational = bool(str(mrio_scenario.get("geography", {}).get("type", "")).lower() == "subnational")
    calliope_subnational = any(SUBNATIONAL_RE.match(loc) for loc in selected_locations)
    blocking_mismatch = bool(mrio_subnational and calliope_subnational and not mapped_rows)
    status = "aligned" if selected_locations else "mrio_only"
    if blocking_mismatch:
        status = "blocking_mismatch"
    return {
        "status": status,
        "blocking_mismatch": blocking_mismatch,
        "mrio_geography_code": geography_code,
        "mrio_geography": mrio_scenario.get("geography", {}),
        "calliope_locations": selected_locations,
        "calliope_location_count": len(selected_locations),
        "alignment_level": ",".join(sorted({str(r.get("alignment_level", "")).strip() for r in mapped_rows if str(r.get("alignment_level", "")).strip()})),
        "mapping_rows": mapped_rows,
        "notes": (
            "No Calliope locations were mapped; MRIO-direct effects remain at the MRIO geography only."
            if not selected_locations
            else "MRIO geography applies to the mapped Calliope national/subnational locations."
        ),
    }


def build_scenario_package(
    *,
    config_dir: Path,
    calliope_root: Path,
    energy_scenario_key: str,
    mrio_scenario_id: str,
    target_year: int,
    run_profile: str,
    levers: Dict[str, Any],
    strict_validation: bool,
    allow_placeholder_data: bool,
    energy_model_engine: str = "calliope",
) -> Dict[str, Any]:
    report = load_or_parse_scenario_report(config_dir)
    scenarios = report.get("scenarios") or {}
    if mrio_scenario_id in AFRICA_MRIO_SCENARIO_LABELS:
        africa_mrio = write_africa_national_mrio_placeholder_scenarios(config_dir, report)
        mrio_scenario = (africa_mrio.get("scenarios") or {}).get(mrio_scenario_id)
        if not mrio_scenario:
            raise ValueError(f"Africa national MRIO scenario '{mrio_scenario_id}' could not be generated.")
    elif mrio_scenario_id not in scenarios:
        raise ValueError(f"MRIO scenario '{mrio_scenario_id}' was not found in the parsed scenario report.")
    else:
        mrio_scenario = scenarios[mrio_scenario_id]
    geography_alignment = build_geography_alignment(
        config_dir=config_dir,
        calliope_root=calliope_root,
        mrio_scenario=mrio_scenario,
    )
    if geography_alignment.get("blocking_mismatch"):
        raise ValueError(
            "Scenario geography alignment failed: MRIO and Calliope both expose incompatible subnational groupings."
        )
    now = datetime.now(timezone.utc).isoformat()
    engine = str(energy_model_engine or "calliope").strip().lower()
    return {
        "schema_version": "integrated_scenario_package_v1",
        "created_at_utc": now,
        "energy_model_engine": engine,
        "energy_scenario_key": energy_scenario_key,
        "mrio_scenario_id": mrio_scenario_id,
        "target_year": int(target_year),
        "run_profile": run_profile,
        "levers": levers,
        "strict_validation": bool(strict_validation),
        "allow_placeholder_data": bool(allow_placeholder_data),
        "energy": {
            "adapter": f"{engine}_v1",
            "model": engine,
            "scenario_key": energy_scenario_key,
            "runtime_status": "executable" if engine == "calliope" else "adapter_target_pending_runtime",
        },
        "target_scenario": {
            "scenario_id": mrio_scenario_id,
            "target_year": int(target_year),
            "scenario": mrio_scenario,
        },
        "mrio_direct": {
            "adapter": HEURISTIC_METHOD,
            "shock_mapping": {
                "mapping_id": HEURISTIC_METHOD,
                "shock_categories": ["A/Z", "E", "Y"],
                "notes": "MRIO-direct shock mapping consumes the selected integrated target scenario but does not define the target scenario itself.",
            },
            "scenario": mrio_scenario,
            "report_source": {
                "source_file": report.get("source_file", ""),
                "source_sha256": report.get("source_sha256", ""),
            },
        },
        "geography_alignment": geography_alignment,
        "provenance": {
            "source": "EDIM integrated scenario setup",
            "report_source_file": report.get("source_file", ""),
            "report_source_sha256": report.get("source_sha256", ""),
        },
    }


def _sector_for_parameter(parameter: str, default: str = "Electricity_and_heat") -> str:
    text = str(parameter or "").lower()
    if "coal" in text:
        return "Coal_supply_chain"
    if "gas" in text:
        return "Gas_supply_chain"
    if "oil" in text or "diesel" in text:
        return "Oil_supply_chain"
    if "solar" in text or "wind" in text or "hydro" in text or "renewable" in text:
        return "Electrical_equipment"
    if "capacity" in text or "investment" in text:
        return "Construction_of_power_assets"
    if "demand" in text or "access" in text:
        return "Electricity_and_heat"
    return default


def build_mrio_direct_inputs(
    *,
    scenario_package: Dict[str, Any],
    bridge_total_shock_musd: float,
    direct_config: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    direct_config = direct_config or {}
    scale = _safe_float(direct_config.get("structural_reallocation_bridge_scale"), 0.25)
    max_ratio = _safe_float(direct_config.get("max_direct_to_bridge_ratio"), 1.0)
    scenario = ((scenario_package.get("mrio_direct") or {}).get("scenario") or {})
    target_year = int(scenario_package.get("target_year") or 2030)
    geography_code = str(scenario.get("geography_code", "") or "").strip()
    base_amount = max(float(bridge_total_shock_musd or 0.0), 0.0) * max(scale, 0.0)
    shock_rows: List[Dict[str, Any]] = []

    scenario_records = list(scenario.get("national_scenarios") or [])
    national_placeholder_dataset = bool(scenario_records)
    if not scenario_records:
        scenario_records = [scenario]
    per_record_base_amount = base_amount / max(len(scenario_records), 1)
    archetype_id = str(scenario.get("scenario_code") or scenario.get("scenario_id") or "")
    emissions_proxy_values: List[float] = []
    for record in scenario_records:
        record_rows, record_emissions_proxy = _generate_direct_shock_rows_for_scenario_record(
            record=record,
            archetype_id=archetype_id,
            target_year=target_year,
            base_amount=per_record_base_amount,
        )
        shock_rows.extend(record_rows)
        emissions_proxy_values.append(record_emissions_proxy)

    total_abs = sum(abs(_safe_float(row.get("shock_value_musd"))) for row in shock_rows)
    cap = max(float(bridge_total_shock_musd or 0.0), 0.0) * max(max_ratio, 0.0)
    capped = False
    if cap > 0 and total_abs > cap:
        factor = cap / total_abs
        for row in shock_rows:
            row["shock_value_musd"] = _safe_float(row.get("shock_value_musd")) * factor
        capped = True

    emissions_proxy = sum(emissions_proxy_values) / max(len(emissions_proxy_values), 1)

    positive = sum(max(_safe_float(row.get("shock_value_musd")), 0.0) for row in shock_rows)
    negative = sum(min(_safe_float(row.get("shock_value_musd")), 0.0) for row in shock_rows)
    return {
        "schema_version": "mrio_direct_inputs_v1",
        "method": HEURISTIC_METHOD,
        "scenario_id": scenario.get("scenario_id", ""),
        "target_year": target_year,
        "geography_code": geography_code,
        "geography": scenario.get("geography", {}),
        "national_record_count": len(scenario_records),
        "placeholder_record_count": int(
            scenario.get("placeholder_record_count") or sum(1 for record in scenario_records if record.get("placeholder"))
        ),
        "bridge_total_reference_musd": float(bridge_total_shock_musd or 0.0),
        "configuration": {
            "structural_reallocation_bridge_scale": scale,
            "max_direct_to_bridge_ratio": max_ratio,
        },
        "shock_rows": shock_rows,
        "totals": {
            "positive_direct_shock_musd": positive,
            "negative_direct_shock_musd": negative,
            "net_direct_shock_musd": positive + negative,
            "emissions_intensity_delta_proxy": emissions_proxy,
        },
        "diagnostics": {
            "heuristic": True,
            "capped_to_bridge_ratio": capped,
            "shock_row_count": len(shock_rows),
            "overlap_policy": "bridge_authoritative_for_headline_totals",
            "national_placeholder_dataset": national_placeholder_dataset,
            "source_report_scenario_ids": scenario.get("source_report_scenario_ids", []),
            "placeholder_method": scenario.get("placeholder_method", ""),
            "per_record_base_amount_musd": per_record_base_amount,
        },
    }


def write_scenario_artifacts(run_dir: Path, scenario_package: Dict[str, Any], mrio_direct_inputs: Dict[str, Any] | None = None) -> Dict[str, str]:
    import json

    scenario_dir = run_dir / "scenario"
    scenario_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "scenario_package.json").write_text(json.dumps(scenario_package, indent=2), encoding="utf-8")
    (scenario_dir / "energy_input_manifest.json").write_text(
        json.dumps(scenario_package.get("energy") or {}, indent=2),
        encoding="utf-8",
    )
    (scenario_dir / "report_scenario_reference.json").write_text(
        json.dumps((scenario_package.get("mrio_direct") or {}).get("scenario") or {}, indent=2),
        encoding="utf-8",
    )
    (scenario_dir / "geography_alignment.json").write_text(
        json.dumps(scenario_package.get("geography_alignment") or {}, indent=2),
        encoding="utf-8",
    )
    artifacts = {
        "scenario_package_json": "scenario_package.json",
        "energy_input_manifest_json": "scenario/energy_input_manifest.json",
        "report_scenario_reference_json": "scenario/report_scenario_reference.json",
        "geography_alignment_json": "scenario/geography_alignment.json",
    }
    if mrio_direct_inputs is not None:
        (scenario_dir / "mrio_direct_inputs.json").write_text(json.dumps(mrio_direct_inputs, indent=2), encoding="utf-8")
        rows = list(mrio_direct_inputs.get("shock_rows") or [])
        _write_csv(
            scenario_dir / "mrio_direct_shocks.csv",
            rows,
            [
                "scenario_id",
                "scenario_archetype_id",
                "source_report_scenario_id",
                "shock_category",
                "parameter",
                "mario_parameter",
                "mario_region",
                "geography",
                "mario_sector",
                "target_year",
                "shock_value_musd",
                "method",
                "placeholder",
                "placeholder_method",
                "notes",
            ],
        )
        artifacts["mrio_direct_inputs_json"] = "scenario/mrio_direct_inputs.json"
        artifacts["mrio_direct_shocks_csv"] = "scenario/mrio_direct_shocks.csv"
    return artifacts
