from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from zipfile import ZIP_DEFLATED, ZipFile

from .mario_runtime import load_development_indicator_mapping, load_scenario_assumptions

IMPORT_LEAKAGE_HEURISTIC_SHARES = (
    ("import", 1.0),
    ("imported", 1.0),
    ("foreign", 1.0),
    ("rest_of_world", 1.0),
    ("row", 1.0),
    ("oil", 0.65),
    ("diesel", 0.65),
    ("hfo", 0.65),
    ("gas", 0.45),
    ("coal", 0.25),
    ("fuel", 0.35),
    ("bioenergy", 0.10),
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _sum_cost_class(summary: Dict[str, Any], cost_class: str) -> float:
    records = ((summary.get("system_cost") or {}).get("records") or [])
    total = 0.0
    target = cost_class.strip().lower()
    for rec in records:
        label = str((rec or {}).get("costs", "")).strip().lower()
        if label == target:
            total += _safe_float((rec or {}).get("value"), 0.0)
    return total


def _development_bridge_channel(development: Dict[str, Any]) -> Dict[str, Any]:
    bridge = development.get("bridge")
    if isinstance(bridge, dict) and bridge:
        return bridge
    return development


def _supplier_shock_value_musd(rec: Dict[str, Any]) -> float:
    for key in ("shock_value_musd", "total_shock_musd", "value_musd", "value", "shock_value"):
        if key in rec:
            return _safe_float(rec.get(key), 0.0)
    return 0.0


def _import_leakage_share_for_supplier(supplier: str) -> float:
    normalized = supplier.strip().lower()
    for token, share in IMPORT_LEAKAGE_HEURISTIC_SHARES:
        if token in normalized:
            return share
    return 0.0


def _estimate_import_leakage_details(development: Dict[str, Any]) -> Dict[str, Any]:
    channel = _development_bridge_channel(development)
    sector_records = ((channel.get("by_supplier_sector") or {}).get("records") or [])
    leakage = 0.0
    contributing: List[Dict[str, Any]] = []
    for rec in sector_records:
        supplier = str((rec or {}).get("supplier_sector", "")).strip().lower()
        shock = max(_supplier_shock_value_musd(rec or {}), 0.0)
        share = _import_leakage_share_for_supplier(supplier)
        if shock <= 0 or share <= 0:
            continue
        value = shock * share
        leakage += value
        contributing.append(
            {
                "supplier_sector": supplier,
                "shock_value_musd": shock,
                "import_leakage_share": share,
                "import_leakage_musd": value,
            }
        )
    return {
        "value_musd": leakage,
        "method": "supplier_sector_import_leakage_heuristic_v1" if contributing else "no_import_or_fuel_supplier_sector",
        "records": contributing,
    }


def _estimate_import_leakage(development: Dict[str, Any]) -> float:
    return _safe_float(_estimate_import_leakage_details(development).get("value_musd"), 0.0)


def _scenario_assumption_value(scenario_assumptions: Dict[str, Any], key: str) -> float:
    selected = scenario_assumptions.get("selected_values") or {}
    entry = selected.get(key) or {}
    return _safe_float(entry.get("value_numeric"), 0.0)


def _estimate_reliability_penalty_musd(
    reliability: Dict[str, Any],
    scenario_assumptions: Dict[str, Any],
) -> float:
    unserved_total = max(_safe_float(reliability.get("unserved_total"), 0.0), 0.0)
    value_of_lost_load = max(_scenario_assumption_value(scenario_assumptions, "value_of_lost_load"), 0.0)
    if unserved_total <= 0 or value_of_lost_load <= 0:
        return 0.0
    # Calliope-Africa energy quantities are in kWh-scale model units; VOLL is stored as USD/MWh.
    return (unserved_total * value_of_lost_load) / 1_000_000_000.0


def _extract_metric_values(summary: Dict[str, Any]) -> Dict[str, float]:
    summary_diagnostics = summary.get("summary_diagnostics") or {}
    reliability = summary_diagnostics.get("reliability") or {}
    physical_emissions = summary_diagnostics.get("physical_emissions") or {}
    development = summary.get("development_impacts") or {}
    dev_totals = development.get("selected_totals") or development.get("totals") or {}

    import_leakage = _estimate_import_leakage(development)

    return {
        "monetary_cost": _sum_cost_class(summary, "monetary"),
        "physical_emissions": _safe_float(physical_emissions.get("total_emissions"), 0.0),
        "unserved_energy_share": _safe_float(reliability.get("unserved_energy_share"), 0.0),
        "jobs_total": _safe_float(dev_totals.get("jobs_total"), 0.0),
        "gva_total_musd": _safe_float(dev_totals.get("gva_total_musd"), 0.0),
        "import_leakage_musd": import_leakage,
    }


def _metric_spec() -> List[Tuple[str, str, str, str]]:
    # key, label, unit, better_direction
    return [
        ("monetary_cost", "System cost", "USD", "down"),
        ("physical_emissions", "Physical emissions", "tCO2", "down"),
        ("unserved_energy_share", "Unserved energy share", "share", "down"),
        ("jobs_total", "Jobs", "jobs", "up"),
        ("gva_total_musd", "GVA", "MUSD", "up"),
        ("import_leakage_musd", "Import leakage", "MUSD", "down"),
    ]


def _validate_numeric(value: Any, field: str) -> float:
    try:
        return float(value)
    except Exception as exc:
        raise ValueError(f"Field '{field}' must be numeric.") from exc


def _build_default_indicator_payload(status: str, message: str) -> Dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "records": [],
        "available_count": 0,
        "unavailable_count": 0,
    }


def _build_development_indicator_payload(
    summary: Dict[str, Any],
    scenario_assumptions: Dict[str, Any],
    indicator_mapping: Dict[str, Any],
    fallback_carbon_price: float,
) -> Dict[str, Any]:
    mapping_rows = indicator_mapping.get("records") or []
    if not mapping_rows:
        return _build_default_indicator_payload(
            "missing_mapping",
            "No development indicator mapping rows were available.",
        )

    values = _extract_metric_values(summary)
    development = summary.get("development_impacts") or {}
    dev_totals = development.get("selected_totals") or development.get("totals") or {}
    physical_emissions = _safe_float(
        ((summary.get("summary_diagnostics") or {}).get("physical_emissions") or {}).get("total_emissions"),
        0.0,
    )
    selected_assumptions = scenario_assumptions.get("selected_values") or {}
    carbon_price_entry = selected_assumptions.get("carbon_price") or {}
    carbon_price = _safe_float(carbon_price_entry.get("value_numeric"), fallback_carbon_price)
    driver_metric_values: Dict[str, float] = {
        "jobs_total": _safe_float(dev_totals.get("jobs_total"), 0.0),
        "gva_total": _safe_float(dev_totals.get("gva_total_musd"), 0.0),
        "gva_total_musd": _safe_float(dev_totals.get("gva_total_musd"), 0.0),
        "household_income_proxy_musd": _safe_float(dev_totals.get("household_income_proxy_musd"), 0.0),
        "import_leakage": _safe_float(values.get("import_leakage_musd"), 0.0),
        "import_leakage_musd": _safe_float(values.get("import_leakage_musd"), 0.0),
        "unserved_energy_share": _safe_float(values.get("unserved_energy_share"), 0.0),
        "monetary_cost": _safe_float(values.get("monetary_cost"), 0.0),
        "co2_cost_proxy": physical_emissions * max(carbon_price, 0.0) / 1_000_000.0,
    }
    driver_metric_sources: Dict[str, List[str]] = {
        "jobs_total": ["development_impacts.selected_totals.jobs_total"],
        "gva_total": ["development_impacts.selected_totals.gva_total_musd"],
        "gva_total_musd": ["development_impacts.selected_totals.gva_total_musd"],
        "household_income_proxy_musd": ["development_impacts.selected_totals.household_income_proxy_musd"],
        "import_leakage": ["development_drivers.import_leakage_musd"],
        "import_leakage_musd": ["development_drivers.import_leakage_musd"],
        "unserved_energy_share": ["summary_diagnostics.reliability.unserved_energy_share"],
        "monetary_cost": ["summary.system_cost"],
        "co2_cost_proxy": [
            "summary_diagnostics.physical_emissions.total_emissions",
            "scenario_assumptions.carbon_price_or_request_lever",
        ],
    }

    records: List[Dict[str, Any]] = []
    available_count = 0
    unavailable_count = 0

    for row in mapping_rows:
        indicator_id = str((row or {}).get("indicator_id", "")).strip()
        indicator_name = str((row or {}).get("indicator_name", "")).strip() or indicator_id
        driver_metric = str((row or {}).get("driver_metric", "")).strip()
        unit = str((row or {}).get("unit", "")).strip()
        aggregation_rule = str((row or {}).get("aggregation_rule", "")).strip()
        lag_years = int(_safe_float((row or {}).get("lag_years"), 0.0))
        notes = str((row or {}).get("notes", "")).strip()
        status = "available"
        reason = ""
        source_metrics: List[str] = []
        value: float | None = None

        if driver_metric in driver_metric_values:
            value = _safe_float(driver_metric_values.get(driver_metric), 0.0)
            source_metrics = driver_metric_sources.get(driver_metric, [])
        else:
            status = "unavailable"
            reason = "The current model output set does not provide a defensible direct formula for this indicator."

        if status == "available":
            available_count += 1
        else:
            unavailable_count += 1

        records.append(
            {
                "indicator_id": indicator_id,
                "indicator_name": indicator_name,
                "unit": unit,
                "aggregation_rule": aggregation_rule,
                "lag_years": lag_years,
                "status": status,
                "value": value,
                "reason": reason,
                "driver_metric": driver_metric,
                "source_metrics": source_metrics,
                "notes": notes,
            }
        )

    return {
        "status": "configured",
        "message": "Development indicators were evaluated from the configured mapping rows.",
        "records": records,
        "available_count": available_count,
        "unavailable_count": unavailable_count,
    }


def _build_metric_resolution_payload() -> Dict[str, Any]:
    return {
        "records": [
            {
                "metric_key": "monetary_cost",
                "label": "System cost",
                "native_resolution": "global",
                "filtered_resolution": "location",
                "notes": "Global in integrated outputs; filtered UI uses location-level monetary cost from results.csv when available.",
            },
            {
                "metric_key": "physical_emissions",
                "label": "Physical emissions",
                "native_resolution": "global",
                "filtered_resolution": "location",
                "notes": "Filtered UI uses location-level CO2 cost totals when available; otherwise pool-level diagnostics remain native.",
            },
            {
                "metric_key": "unserved_energy_share",
                "label": "Unserved energy share",
                "native_resolution": "global",
                "filtered_resolution": "location_or_pool",
                "notes": "Filtered UI uses location-level demand and unmet_demand from results.csv, with pool fallback when loc rows are unavailable.",
            },
            {
                "metric_key": "jobs_total",
                "label": "Jobs",
                "native_resolution": "region",
                "filtered_resolution": "region",
                "notes": "Development jobs remain region-level unless explicit subregional coefficients are provided.",
            },
            {
                "metric_key": "gva_total_musd",
                "label": "GVA",
                "native_resolution": "region",
                "filtered_resolution": "region",
                "notes": "Value added is modeled through region-coupled IO tables.",
            },
            {
                "metric_key": "import_leakage_musd",
                "label": "Import leakage",
                "native_resolution": "region_supplier",
                "filtered_resolution": "region_supplier",
                "notes": "Import leakage is inferred from region-supplier sector rows, not country rows.",
            },
            {
                "metric_key": "generation_by_technology",
                "label": "Generation by technology",
                "native_resolution": "global",
                "filtered_resolution": "location",
                "notes": "Spatial filtering uses location-level generation from results.csv when available.",
            },
            {
                "metric_key": "capacity_by_technology",
                "label": "Capacity by technology",
                "native_resolution": "global",
                "filtered_resolution": "location",
                "notes": "Spatial filtering uses location-level capacity from results.csv when available.",
            },
            {
                "metric_key": "interpool_trade",
                "label": "Inter-pool trade",
                "native_resolution": "pool",
                "filtered_resolution": "pool",
                "notes": "Trade balance is a pool-level diagnostic and should not be interpreted as country-level flow.",
            },
        ]
    }


def _max_abs_surrogate_delta_pct(summary: Dict[str, Any]) -> float:
    diagnostics = ((summary.get("development_impacts") or {}).get("diagnostics") or {})
    benchmark = (diagnostics.get("surrogate_benchmark") or {}).get("metrics") or {}
    best = 0.0
    if isinstance(benchmark, dict):
        for row in benchmark.values():
            if not isinstance(row, dict):
                continue
            pct = row.get("delta_pct")
            if pct is None:
                continue
            best = max(best, abs(_safe_float(pct, 0.0)))
    return float(best)


def _quality_issue(code: str, severity: str, message: str) -> Dict[str, Any]:
    return {"code": str(code), "severity": str(severity), "message": str(message)}


def _build_model_quality(
    summary: Dict[str, Any],
    coupling_manifest: Dict[str, Any] | None,
    scenario_assumptions: Dict[str, Any],
    development_indicators: Dict[str, Any],
) -> Dict[str, Any]:
    coupling_manifest = coupling_manifest or {}
    summary_diagnostics = summary.get("summary_diagnostics") or {}
    physical_emissions = summary_diagnostics.get("physical_emissions") or {}
    energy_balance = summary_diagnostics.get("energy_balance") or {}

    placeholder_rows = int(_safe_float(coupling_manifest.get("placeholder_input_row_count"), 0.0))
    allow_placeholder_data = bool(coupling_manifest.get("allow_placeholder_data", False))
    mapping_coverage = _safe_float(coupling_manifest.get("mapping_coverage_share"), 0.0)
    warnings_count = int(len(summary.get("warnings") or []))
    fallback_exchange_used = bool(coupling_manifest.get("fallback_exchange_used", False))
    surrogate_fallback_used = bool(coupling_manifest.get("surrogate_fallback_used", False))
    mrio_direct_heuristic = bool(coupling_manifest.get("mrio_direct_heuristic", False))
    assumption_placeholder_count = int(scenario_assumptions.get("selected_placeholder_row_count") or 0)
    indicator_unavailable_count = int(development_indicators.get("unavailable_count") or 0)
    emissions_method = str(physical_emissions.get("method", "")).strip()
    emissions_gap_share = _safe_float(physical_emissions.get("factor_method_gap_share"), 0.0)
    balance_gap_share = _safe_float(energy_balance.get("max_abs_balance_gap_share"), 0.0)
    surrogate_delta_pct = _max_abs_surrogate_delta_pct(summary)

    issues: List[Dict[str, Any]] = []
    score = 100.0

    if placeholder_rows > 0:
        issues.append(
            _quality_issue(
                "placeholder_inputs",
                "error",
                f"Placeholder expert datasets remain active ({placeholder_rows} rows).",
            )
        )
        score -= 28.0

    if assumption_placeholder_count > 0:
        issues.append(
            _quality_issue(
                "placeholder_assumptions",
                "warn",
                f"Selected scenario assumptions still include {assumption_placeholder_count} placeholder rows.",
            )
        )
        score -= 6.0

    if mapping_coverage < 0.999:
        missing_share = max(0.0, 1.0 - mapping_coverage)
        severity = "error" if mapping_coverage < 0.9 else "warn"
        issues.append(
            _quality_issue(
                "mapping_coverage",
                severity,
                f"MARIO mapping coverage is {(mapping_coverage * 100.0):.1f}% for required technologies.",
            )
        )
        score -= min(22.0, missing_share * 30.0)

    if fallback_exchange_used:
        issues.append(
            _quality_issue(
                "fallback_exchange",
                "error",
                "Exchange shocks used summary-based fallback allocation instead of tech-level monetary rows.",
            )
        )
        score -= 25.0

    if surrogate_fallback_used:
        issues.append(
            _quality_issue(
                "surrogate_fallback",
                "error",
                "Development outputs fell back to surrogate mode instead of using the MARIO runtime.",
            )
        )
        score -= 25.0

    if mrio_direct_heuristic:
        issues.append(
            _quality_issue(
                "mrio_direct_heuristic",
                "warn",
                "MRIO-direct report assumptions use heuristic v1 effects; bridge-derived values remain authoritative for headline totals.",
            )
        )
        score -= 10.0

    if warnings_count > 0:
        issues.append(
            _quality_issue(
                "warnings_present",
                "warn",
                f"The run emitted {warnings_count} backend warning(s).",
            )
        )
        score -= min(10.0, float(warnings_count))

    if emissions_method != "cost_class_co2_direct":
        issues.append(
            _quality_issue(
                "emissions_fallback_method",
                "warn",
                "Physical emissions are not coming from direct cost[costs=co2] accounting.",
            )
        )
        score -= 8.0

    if emissions_gap_share > 0.05:
        issues.append(
            _quality_issue(
                "emissions_method_gap",
                "warn",
                f"Direct CO2 accounting and factor-rebuilt CO2 differ by {(emissions_gap_share * 100.0):.1f}%.",
            )
        )
        score -= min(10.0, emissions_gap_share * 20.0)

    if balance_gap_share > 0.02:
        severity = "error" if balance_gap_share > 0.05 else "warn"
        issues.append(
            _quality_issue(
                "energy_balance_gap",
                severity,
                f"Pool energy balance residual reaches {(balance_gap_share * 100.0):.2f}% in at least one pool.",
            )
        )
        score -= min(15.0, balance_gap_share * 100.0)

    if surrogate_delta_pct > 0.5:
        issues.append(
            _quality_issue(
                "surrogate_benchmark_gap",
                "warn",
                f"MARIO and surrogate development totals diverge by up to {(surrogate_delta_pct * 100.0):.1f}%.",
            )
        )
        score -= min(8.0, surrogate_delta_pct * 8.0)

    if indicator_unavailable_count > 0:
        issues.append(
            _quality_issue(
                "indicator_coverage",
                "warn",
                f"{indicator_unavailable_count} configured development indicator(s) are still unavailable from current outputs.",
            )
        )
        score -= min(5.0, float(indicator_unavailable_count))

    score = max(0.0, min(100.0, score))
    has_error = any(str((row or {}).get("severity", "")).lower() == "error" for row in issues)
    status = "production_ready"
    if placeholder_rows > 0:
        status = "exploratory_only"
    elif has_error or score < 70.0:
        status = "exploratory_only"
    elif issues or score < 85.0:
        status = "analyst_review"
    if mrio_direct_heuristic and status == "production_ready":
        status = "analyst_review"

    if status == "production_ready":
        summary_text = "Production-ready diagnostics: no fallback coupling path or major consistency issue was detected."
    elif status == "analyst_review":
        summary_text = "Usable for analysis, but review diagnostics before treating outputs as decision-grade."
    else:
        summary_text = "Exploratory only: fallback paths, placeholders, or consistency gaps materially limit confidence."

    return {
        "score": int(round(score)),
        "status": status,
        "summary": summary_text,
        "issues": issues,
        "diagnostics": {
            "emissions_method": emissions_method,
            "emissions_factor_coverage_share": _safe_float(physical_emissions.get("factor_coverage_share"), 0.0),
            "emissions_method_gap_share": emissions_gap_share,
            "energy_balance_gap_share": balance_gap_share,
            "warnings_count": warnings_count,
            "mapping_coverage_share": mapping_coverage,
            "placeholder_input_row_count": placeholder_rows,
            "surrogate_benchmark_max_abs_delta_pct": surrogate_delta_pct,
            "mrio_direct_heuristic": mrio_direct_heuristic,
        },
    }


def validate_integrated_results(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Integrated payload must be a JSON object.")

    required_top = {
        "run_id",
        "energy_scenario_key",
        "mrio_scenario_id",
        "target_year",
        "integrated_overview",
        "development_drivers",
        "regional_development",
        "development_confidence",
    }
    missing_top = [key for key in required_top if key not in payload]
    if missing_top:
        raise ValueError("Integrated payload missing required fields: " + ", ".join(sorted(missing_top)))

    overview = payload.get("integrated_overview")
    if not isinstance(overview, dict):
        raise ValueError("Integrated payload field 'integrated_overview' must be an object.")
    metrics = overview.get("metrics")
    if not isinstance(metrics, list):
        raise ValueError("Integrated payload field 'integrated_overview.metrics' must be a list.")

    required_metric_keys = {key for key, _, _, _ in _metric_spec()}
    seen_keys: set[str] = set()
    for idx, row in enumerate(metrics):
        if not isinstance(row, dict):
            raise ValueError(f"Metric row at index {idx} must be an object.")
        key = str(row.get("key", "")).strip()
        if not key:
            raise ValueError(f"Metric row at index {idx} is missing 'key'.")
        _validate_numeric(row.get("value"), f"integrated_overview.metrics[{idx}].value")
        direction = str(row.get("better_direction", "")).strip().lower()
        if direction not in {"up", "down"}:
            raise ValueError(
                f"Metric row '{key}' has invalid better_direction '{row.get('better_direction')}'."
            )
        seen_keys.add(key)

    missing_metrics = sorted(required_metric_keys - seen_keys)
    if missing_metrics:
        raise ValueError("Integrated payload metrics missing required keys: " + ", ".join(missing_metrics))

    drivers = payload.get("development_drivers")
    if not isinstance(drivers, dict):
        raise ValueError("Integrated payload field 'development_drivers' must be an object.")
    for key in (
        "capex_effect_musd",
        "opex_effect_musd",
        "reliability_penalty_proxy",
        "import_leakage_musd",
    ):
        _validate_numeric(drivers.get(key), f"development_drivers.{key}")

    regional = payload.get("regional_development")
    if not isinstance(regional, dict):
        raise ValueError("Integrated payload field 'regional_development' must be an object.")
    if not isinstance(regional.get("records"), list):
        raise ValueError("Integrated payload field 'regional_development.records' must be a list.")

    confidence = payload.get("development_confidence")
    if not isinstance(confidence, dict):
        raise ValueError("Integrated payload field 'development_confidence' must be an object.")

    required_confidence = {
        "coupling_mode",
        "mapping_coverage_share",
        "fallback_mapping_share",
        "warnings_count",
        "mario_runtime_executed",
        "mario_runtime_error",
        "mario_runtime_seconds",
        "mario_runner_source",
    }
    missing_conf = [key for key in required_confidence if key not in confidence]
    if missing_conf:
        raise ValueError(
            "Integrated payload development_confidence missing required keys: "
            + ", ".join(sorted(missing_conf))
        )

    _validate_numeric(confidence.get("mapping_coverage_share"), "development_confidence.mapping_coverage_share")
    _validate_numeric(confidence.get("fallback_mapping_share"), "development_confidence.fallback_mapping_share")
    _validate_numeric(confidence.get("warnings_count"), "development_confidence.warnings_count")
    _validate_numeric(confidence.get("mario_runtime_seconds"), "development_confidence.mario_runtime_seconds")
    if not isinstance(confidence.get("mario_runtime_executed"), bool):
        raise ValueError("Field 'development_confidence.mario_runtime_executed' must be boolean.")

    scenario_assumptions = payload.get("scenario_assumptions")
    if scenario_assumptions is not None and not isinstance(scenario_assumptions, dict):
        raise ValueError("Integrated payload field 'scenario_assumptions' must be an object when present.")

    development_indicators = payload.get("development_indicators")
    if development_indicators is not None:
        if not isinstance(development_indicators, dict):
            raise ValueError("Integrated payload field 'development_indicators' must be an object when present.")
        if not isinstance(development_indicators.get("records", []), list):
            raise ValueError("Integrated payload field 'development_indicators.records' must be a list.")

    model_quality = payload.get("model_quality")
    if model_quality is not None:
        if not isinstance(model_quality, dict):
            raise ValueError("Integrated payload field 'model_quality' must be an object when present.")
        if not isinstance(model_quality.get("issues", []), list):
            raise ValueError("Integrated payload field 'model_quality.issues' must be a list.")

    metric_resolution = payload.get("metric_resolution")
    if metric_resolution is not None:
        if not isinstance(metric_resolution, dict):
            raise ValueError("Integrated payload field 'metric_resolution' must be an object when present.")
        if not isinstance(metric_resolution.get("records", []), list):
            raise ValueError("Integrated payload field 'metric_resolution.records' must be a list.")

    return payload


def build_integrated_results(
    summary: Dict[str, Any],
    coupling_manifest: Dict[str, Any] | None = None,
    config_dir: Path | None = None,
    lever_values: Dict[str, Any] | None = None,
    run_year: int | None = None,
) -> Dict[str, Any]:
    values = _extract_metric_values(summary)
    development = summary.get("development_impacts") or {}
    dev_inputs = development.get("inputs") or {}
    reliability = ((summary.get("summary_diagnostics") or {}).get("reliability") or {})

    metrics = []
    for key, label, unit, better_direction in _metric_spec():
        metrics.append(
            {
                "key": key,
                "label": label,
                "unit": unit,
                "value": _safe_float(values.get(key), 0.0),
                "better_direction": better_direction,
            }
        )

    import_leakage_details = _estimate_import_leakage_details(development)
    confidence = {
        "coupling_mode": str((coupling_manifest or {}).get("development_engine_mode", "surrogate")),
        "mapping_coverage_share": _safe_float((coupling_manifest or {}).get("mapping_coverage_share"), 0.0),
        "fallback_mapping_share": _safe_float((coupling_manifest or {}).get("fallback_mapping_share"), 0.0),
        "warnings_count": int(len(summary.get("warnings") or [])),
        "mario_runtime_executed": bool((coupling_manifest or {}).get("mario_runtime_executed", False)),
        "mario_runtime_error": str((coupling_manifest or {}).get("mario_runtime_error", "")),
        "mario_runtime_seconds": _safe_float((coupling_manifest or {}).get("mario_runtime_seconds"), 0.0),
        "mario_runner_source": str((coupling_manifest or {}).get("mario_runner_source", "")),
        "fallback_exchange_used": bool((coupling_manifest or {}).get("fallback_exchange_used", False)),
        "fallback_exchange_source": str((coupling_manifest or {}).get("fallback_exchange_source", "")),
        "surrogate_fallback_used": bool((coupling_manifest or {}).get("surrogate_fallback_used", False)),
        "surrogate_fallback_reason": str((coupling_manifest or {}).get("surrogate_fallback_reason", "")),
        "strict_validation": bool((coupling_manifest or {}).get("strict_validation", False)),
        "allow_placeholder_data": bool((coupling_manifest or {}).get("allow_placeholder_data", False)),
        "placeholder_input_files": list((coupling_manifest or {}).get("placeholder_input_files") or []),
        "placeholder_input_row_count": int(_safe_float((coupling_manifest or {}).get("placeholder_input_row_count"), 0.0)),
        "integration_architecture": str((coupling_manifest or {}).get("integration_architecture", "")),
        "mrio_direct_method": str((coupling_manifest or {}).get("mrio_direct_method", "")),
        "mrio_direct_heuristic": bool((coupling_manifest or {}).get("mrio_direct_heuristic", False)),
        "selected_totals_source": str((coupling_manifest or {}).get("selected_totals_source", "")),
        "temporary_overlap_policy": str((coupling_manifest or {}).get("temporary_overlap_policy", "")),
        "import_leakage_method": str(import_leakage_details.get("method", "")),
        "import_leakage_records": list(import_leakage_details.get("records") or []),
    }

    if isinstance(summary.get("scenario_assumptions"), dict) and summary.get("scenario_assumptions"):
        scenario_assumptions = summary.get("scenario_assumptions") or {}
    elif config_dir is not None:
        scenario_assumptions = load_scenario_assumptions(
            config_dir,
            scenario_key=str(summary.get("energy_scenario_key") or summary.get("scenario") or ""),
            run_year=run_year,
        )
    else:
        scenario_assumptions = {
            "status": "not_loaded",
            "message": "Scenario assumptions were not loaded for this payload.",
            "records": [],
            "selected_values": {},
            "selected_count": 0,
            "selected_placeholder_row_count": 0,
        }

    if isinstance(summary.get("development_indicators"), dict) and summary.get("development_indicators"):
        development_indicators = summary.get("development_indicators") or {}
    elif config_dir is not None:
        indicator_mapping = load_development_indicator_mapping(config_dir)
        development_indicators = _build_development_indicator_payload(
            summary=summary,
            scenario_assumptions=scenario_assumptions,
            indicator_mapping=indicator_mapping,
            fallback_carbon_price=_safe_float(
                ((lever_values or {}).get("carbon_price_usd_per_tco2")),
                0.0,
            ),
        )
    else:
        development_indicators = _build_default_indicator_payload(
            "not_loaded",
            "Development indicators were not loaded for this payload.",
        )

    confidence["scenario_assumptions_applied_count"] = int(scenario_assumptions.get("selected_count") or 0)
    confidence["scenario_assumptions_placeholder_count"] = int(
        scenario_assumptions.get("selected_placeholder_row_count") or 0
    )
    confidence["development_indicators_available_count"] = int(
        development_indicators.get("available_count") or 0
    )
    confidence["development_indicators_unavailable_count"] = int(
        development_indicators.get("unavailable_count") or 0
    )
    reliability_penalty_proxy = _estimate_reliability_penalty_musd(
        reliability=reliability,
        scenario_assumptions=scenario_assumptions,
    )
    confidence["value_of_lost_load_usd_per_mwh"] = _scenario_assumption_value(
        scenario_assumptions,
        "value_of_lost_load",
    )
    confidence["reliability_penalty_method"] = "unserved_kwh_times_value_of_lost_load_usd_per_mwh"
    model_quality = _build_model_quality(
        summary=summary,
        coupling_manifest=coupling_manifest,
        scenario_assumptions=scenario_assumptions,
        development_indicators=development_indicators,
    )
    metric_resolution = _build_metric_resolution_payload()

    payload = {
        "run_id": str(summary.get("run_id", "")),
        "energy_scenario_key": str(summary.get("energy_scenario_key", "")),
        "mrio_scenario_id": str(summary.get("mrio_scenario_id", "")),
        "target_year": int(_safe_float(summary.get("target_year"), 0.0)),
        "scenario_package": summary.get("scenario_package") or {},
        "integrated_overview": {"metrics": metrics},
        "development_drivers": {
            "capex_effect_musd": _safe_float(dev_inputs.get("investment_shock_total_musd"), 0.0),
            "opex_effect_musd": _safe_float(dev_inputs.get("operating_shock_total_musd"), 0.0),
            "reliability_penalty_proxy": reliability_penalty_proxy,
            "import_leakage_musd": _safe_float(values.get("import_leakage_musd"), 0.0),
        },
        "regional_development": {"records": ((development.get("bridge") or development).get("by_region") or {}).get("records") or []},
        "development_confidence": confidence,
        "development_uncertainty": development.get("uncertainty") or {},
        "scenario_assumptions": scenario_assumptions,
        "development_indicators": development_indicators,
        "model_quality": model_quality,
        "metric_resolution": metric_resolution,
        "source_channels": {
            "bridge": development.get("bridge") or {},
            "mrio_direct": development.get("mrio_direct") or {},
            "selected_totals": development.get("selected_totals") or {},
            "combined_totals": development.get("combined_totals") or {},
            "overlap_diagnostics": development.get("overlap_diagnostics") or {},
        },
        "scenario_provenance": {
            "package": summary.get("scenario_package") or {},
            "coupling_manifest": {
                "report_scenario_provenance": (coupling_manifest or {}).get("report_scenario_provenance") or {},
                "geography_alignment": (coupling_manifest or {}).get("geography_alignment") or {},
            },
        },
    }
    return validate_integrated_results(payload)


def create_exchange_bundle_zip(run_dir: Path) -> Path | None:
    exchange_dir = run_dir / "exchange"
    zip_path = run_dir / "exchange_bundle.zip"
    with ZipFile(zip_path, mode="w", compression=ZIP_DEFLATED) as zf:
        if exchange_dir.exists() and exchange_dir.is_dir():
            for path in sorted(exchange_dir.rglob("*")):
                if path.is_file():
                    zf.write(path, arcname=str(path.relative_to(run_dir)))
        scenario_dir = run_dir / "scenario"
        if scenario_dir.exists() and scenario_dir.is_dir():
            for path in sorted(scenario_dir.rglob("*")):
                if path.is_file():
                    zf.write(path, arcname=str(path.relative_to(run_dir)))
        for name in ("results.csv", "development_impacts.json", "coupling_manifest.json", "integrated_results.json", "scenario_package.json"):
            candidate = run_dir / name
            if candidate.exists() and candidate.is_file():
                zf.write(candidate, arcname=name)
    return zip_path


def build_run_report_markdown(summary: Dict[str, Any], integrated: Dict[str, Any]) -> str:
    now = datetime.now(timezone.utc).isoformat()
    run_id = str(summary.get("run_id", ""))
    energy_scenario = str(summary.get("energy_scenario_key", ""))
    mrio_scenario = str(summary.get("mrio_scenario_id", ""))
    target_year = int(_safe_float(summary.get("target_year"), 0.0))
    warnings = summary.get("warnings") or []

    run_meta = ((summary.get("summary_diagnostics") or {}).get("run_metadata") or {})
    confidence = (integrated.get("development_confidence") or {})
    metrics = ((integrated.get("integrated_overview") or {}).get("metrics") or [])
    drivers = (integrated.get("development_drivers") or {})
    reliability = ((summary.get("summary_diagnostics") or {}).get("reliability") or {})
    physical_emissions = ((summary.get("summary_diagnostics") or {}).get("physical_emissions") or {})
    system_structure = ((summary.get("summary_diagnostics") or {}).get("system_structure") or {})
    energy_balance = ((summary.get("summary_diagnostics") or {}).get("energy_balance") or {})
    scenario_assumptions = (integrated.get("scenario_assumptions") or {})
    development_indicators = (integrated.get("development_indicators") or {})
    model_quality = (integrated.get("model_quality") or {})
    metric_resolution = (integrated.get("metric_resolution") or {})

    lines = [
        "# EDIM Run Report",
        "",
        f"- generated_at_utc: `{now}`",
        f"- run_id: `{run_id}`",
        f"- energy_scenario_key: `{energy_scenario}`",
        f"- mrio_scenario_id: `{mrio_scenario}`",
        f"- target_year: `{target_year}`",
        f"- run_profile: `{summary.get('run_profile')}`",
        "",
        "## Execution",
        "",
        f"- solver: `{run_meta.get('solver', '')}`",
        f"- termination_condition: `{run_meta.get('termination_condition', '')}`",
        f"- solution_time_seconds: `{_safe_float(run_meta.get('solution_time_seconds'), 0.0):.6f}`",
        f"- objective_function_value: `{_safe_float(run_meta.get('objective_function_value'), 0.0):.6f}`",
        "",
        "## Integrated Metrics",
        "",
    ]

    if metrics:
        for row in metrics:
            if isinstance(row, dict):
                label = str(row.get("label", row.get("key", "")))
                unit = str(row.get("unit", ""))
                value = _safe_float(row.get("value"), 0.0)
                lines.append(f"- {label} ({unit}): `{value:.6f}`")
    else:
        lines.append("- (none)")

    lines.extend(
        [
            "",
            "## Model Quality",
            "",
            f"- status: `{model_quality.get('status', '')}`",
            f"- score: `{int(_safe_float(model_quality.get('score'), 0.0))}`",
            f"- summary: {model_quality.get('summary', '')}",
            "",
            "## Coupling Diagnostics",
            "",
            f"- coupling_mode: `{confidence.get('coupling_mode', '')}`",
            f"- mapping_coverage_share: `{_safe_float(confidence.get('mapping_coverage_share'), 0.0):.6f}`",
            f"- fallback_mapping_share: `{_safe_float(confidence.get('fallback_mapping_share'), 0.0):.6f}`",
            f"- mario_runtime_executed: `{bool(confidence.get('mario_runtime_executed', False))}`",
            f"- mario_runtime_seconds: `{_safe_float(confidence.get('mario_runtime_seconds'), 0.0):.6f}`",
            f"- mario_runner_source: `{confidence.get('mario_runner_source', '')}`",
            f"- fallback_exchange_used: `{bool(confidence.get('fallback_exchange_used', False))}`",
            f"- fallback_exchange_source: `{confidence.get('fallback_exchange_source', '')}`",
            f"- surrogate_fallback_used: `{bool(confidence.get('surrogate_fallback_used', False))}`",
            f"- strict_validation: `{bool(confidence.get('strict_validation', False))}`",
            f"- allow_placeholder_data: `{bool(confidence.get('allow_placeholder_data', False))}`",
            f"- placeholder_input_row_count: `{int(_safe_float(confidence.get('placeholder_input_row_count'), 0.0))}`",
            f"- integration_architecture: `{confidence.get('integration_architecture', '')}`",
            f"- mrio_direct_method: `{confidence.get('mrio_direct_method', '')}`",
            f"- selected_totals_source: `{confidence.get('selected_totals_source', '')}`",
            f"- temporary_overlap_policy: `{confidence.get('temporary_overlap_policy', '')}`",
            "",
            "## Development Drivers",
            "",
            f"- capex_effect_musd: `{_safe_float(drivers.get('capex_effect_musd'), 0.0):.6f}`",
            f"- opex_effect_musd: `{_safe_float(drivers.get('opex_effect_musd'), 0.0):.6f}`",
            f"- reliability_penalty_proxy: `{_safe_float(drivers.get('reliability_penalty_proxy'), 0.0):.6f}`",
            f"- import_leakage_musd: `{_safe_float(drivers.get('import_leakage_musd'), 0.0):.6f}`",
            "",
            "## Resolution",
            "",
        ]
    )

    resolution_rows = metric_resolution.get("records") or []
    if resolution_rows:
        for row in resolution_rows:
            lines.append(
                "- "
                f"{row.get('label', row.get('metric_key', ''))}: "
                f"native=`{row.get('native_resolution', '')}`, "
                f"filtered_ui=`{row.get('filtered_resolution', '')}`"
            )
    else:
        lines.append("- No metric resolution rows were recorded.")

    lines.extend(
        [
            "",
            "## Scenario Assumptions",
            "",
        ]
    )

    assumption_rows = scenario_assumptions.get("records") or []
    if assumption_rows:
        for row in assumption_rows:
            lines.append(
                "- "
                f"{row.get('assumption_key', '')}: "
                f"`{row.get('value', row.get('value_numeric', ''))}` {row.get('unit', '')} "
                f"(scenario_key=`{row.get('scenario_key', '')}`, source=`{row.get('source', '')}`)"
            )
    else:
        lines.append("- No matched scenario assumptions were recorded.")

    lines.extend(
        [
            "",
            "## Development Indicators",
            "",
        ]
    )

    indicator_rows = development_indicators.get("records") or []
    if indicator_rows:
        for row in indicator_rows:
            if str(row.get("status", "")).strip().lower() == "available":
                lines.append(
                    f"- {row.get('indicator_name', row.get('indicator_id', ''))}: "
                    f"`{_safe_float(row.get('value'), 0.0):.6f}` {row.get('unit', '')}"
                )
            else:
                reason = str(row.get("reason", "")).strip()
                lines.append(
                    f"- {row.get('indicator_name', row.get('indicator_id', ''))}: unavailable"
                    + (f" ({reason})" if reason else "")
                )
    else:
        lines.append("- No development indicators were recorded.")

    lines.extend(
        [
            "",
            "## Reliability",
            "",
            f"- demand_total: `{_safe_float(reliability.get('demand_total'), 0.0):.6f}`",
            f"- unserved_total: `{_safe_float(reliability.get('unserved_total'), 0.0):.6f}`",
            f"- unserved_energy_share: `{_safe_float(reliability.get('unserved_energy_share'), 0.0):.6f}`",
            f"- hours_with_unserved: `{int(_safe_float(reliability.get('hours_with_unserved'), 0.0))}`",
            "",
            "## System Structure",
            "",
            f"- generation_total: `{_safe_float(system_structure.get('generation_total'), 0.0):.6f}`",
            f"- capacity_total: `{_safe_float(system_structure.get('capacity_total'), 0.0):.6f}`",
            f"- renewable_generation_share: `{_safe_float(system_structure.get('renewable_generation_share'), 0.0):.6f}`",
            f"- zero_carbon_generation_share: `{_safe_float(system_structure.get('zero_carbon_generation_share'), 0.0):.6f}`",
            f"- fossil_generation_share: `{_safe_float(system_structure.get('fossil_generation_share'), 0.0):.6f}`",
            "",
            "## Emissions",
            "",
            f"- method: `{physical_emissions.get('method', '')}`",
            f"- source_variable: `{physical_emissions.get('source_variable', '')}`",
            f"- total_emissions: `{_safe_float(physical_emissions.get('total_emissions'), 0.0):.6f}`",
            f"- factor_coverage_share: `{_safe_float(physical_emissions.get('factor_coverage_share'), 0.0):.6f}`",
            f"- factor_method_gap_share: `{_safe_float(physical_emissions.get('factor_method_gap_share'), 0.0):.6f}`",
            "",
            "## Energy Balance",
            "",
            f"- max_abs_balance_gap: `{_safe_float(energy_balance.get('max_abs_balance_gap'), 0.0):.6f}`",
            f"- max_abs_balance_gap_share: `{_safe_float(energy_balance.get('max_abs_balance_gap_share'), 0.0):.6f}`",
            "",
            "## Caveats",
            "",
        ]
    )

    quality_issues = model_quality.get("issues") or []
    if quality_issues:
        lines.append("- model_quality_issues:")
        for row in quality_issues:
            lines.append(
                "  - "
                f"[{row.get('severity', '')}] {row.get('code', '')}: {row.get('message', '')}"
            )

    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- No warnings recorded.")

    return "\n".join(lines) + "\n"
