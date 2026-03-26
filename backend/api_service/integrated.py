from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from zipfile import ZIP_DEFLATED, ZipFile


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


def _estimate_import_leakage(development: Dict[str, Any]) -> float:
    sector_records = ((development.get("by_supplier_sector") or {}).get("records") or [])
    leakage = 0.0
    for rec in sector_records:
        supplier = str((rec or {}).get("supplier_sector", "")).strip().lower()
        if any(token in supplier for token in ("import", "foreign", "rest_of_world", "row")):
            leakage += _safe_float((rec or {}).get("shock_value_musd"), 0.0)
    return leakage


def _extract_metric_values(summary: Dict[str, Any]) -> Dict[str, float]:
    summary_diagnostics = summary.get("summary_diagnostics") or {}
    reliability = summary_diagnostics.get("reliability") or {}
    physical_emissions = summary_diagnostics.get("physical_emissions") or {}
    development = summary.get("development_impacts") or {}
    dev_totals = development.get("totals") or {}

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


def validate_integrated_results(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Integrated payload must be a JSON object.")

    required_top = {
        "run_id",
        "scenario",
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

    return payload


def build_integrated_results(
    summary: Dict[str, Any],
    coupling_manifest: Dict[str, Any] | None = None,
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

    reliability_penalty_proxy = _safe_float(reliability.get("unserved_total"), 0.0)
    confidence = {
        "coupling_mode": str((coupling_manifest or {}).get("development_engine_mode", "surrogate")),
        "mapping_coverage_share": _safe_float((coupling_manifest or {}).get("mapping_coverage_share"), 0.0),
        "fallback_mapping_share": _safe_float((coupling_manifest or {}).get("fallback_mapping_share"), 0.0),
        "warnings_count": int(len(summary.get("warnings") or [])),
        "mario_runtime_executed": bool((coupling_manifest or {}).get("mario_runtime_executed", False)),
        "mario_runtime_error": str((coupling_manifest or {}).get("mario_runtime_error", "")),
        "mario_runtime_seconds": _safe_float((coupling_manifest or {}).get("mario_runtime_seconds"), 0.0),
        "mario_runner_source": str((coupling_manifest or {}).get("mario_runner_source", "")),
    }

    payload = {
        "run_id": str(summary.get("run_id", "")),
        "scenario": str(summary.get("scenario", "")),
        "integrated_overview": {"metrics": metrics},
        "development_drivers": {
            "capex_effect_musd": _safe_float(dev_inputs.get("investment_shock_total_musd"), 0.0),
            "opex_effect_musd": _safe_float(dev_inputs.get("operating_shock_total_musd"), 0.0),
            "reliability_penalty_proxy": reliability_penalty_proxy,
            "import_leakage_musd": _safe_float(values.get("import_leakage_musd"), 0.0),
        },
        "regional_development": {"records": ((development.get("by_region") or {}).get("records") or [])},
        "development_confidence": confidence,
        "development_uncertainty": development.get("uncertainty") or {},
    }
    return validate_integrated_results(payload)


def build_baseline_comparison(
    current_integrated: Dict[str, Any],
    baseline_integrated: Dict[str, Any] | None,
    baseline_scenario: str,
    baseline_run_id: str,
) -> Dict[str, Any]:
    """Build metric deltas between current run and baseline run integrated payloads."""
    scenario_key = str(baseline_scenario or "").strip()
    run_id = str(baseline_run_id or "").strip()
    if not scenario_key:
        return {
            "status": "not_configured",
            "baseline_scenario": "",
            "baseline_run_id": "",
            "message": "No baseline_scenario configured for this scenario.",
            "metrics": {"records": []},
        }

    if not baseline_integrated:
        return {
            "status": "missing",
            "baseline_scenario": scenario_key,
            "baseline_run_id": run_id,
            "message": "No historical baseline run was found.",
            "metrics": {"records": []},
        }

    current_rows = ((current_integrated.get("integrated_overview") or {}).get("metrics") or [])
    baseline_rows = ((baseline_integrated.get("integrated_overview") or {}).get("metrics") or [])

    current_by_key: Dict[str, Dict[str, Any]] = {}
    baseline_by_key: Dict[str, Dict[str, Any]] = {}
    for row in current_rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key", "")).strip()
        if key:
            current_by_key[key] = row
    for row in baseline_rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key", "")).strip()
        if key:
            baseline_by_key[key] = row

    records: List[Dict[str, Any]] = []
    for key, cur in current_by_key.items():
        base = baseline_by_key.get(key)
        if not isinstance(base, dict):
            continue
        cur_value = _safe_float(cur.get("value"), 0.0)
        base_value = _safe_float(base.get("value"), 0.0)
        delta = cur_value - base_value
        denom = abs(base_value)
        delta_pct = (delta / denom) if denom > 1e-12 else None
        better_direction = str(cur.get("better_direction", "")).strip().lower()
        improved: bool | None
        if better_direction == "down":
            improved = delta < 0
        elif better_direction == "up":
            improved = delta > 0
        else:
            improved = None
        records.append(
            {
                "key": key,
                "label": str(cur.get("label", key)),
                "unit": str(cur.get("unit", "")),
                "current_value": cur_value,
                "baseline_value": base_value,
                "delta_value": delta,
                "delta_pct": delta_pct,
                "better_direction": better_direction,
                "improved_vs_baseline": improved,
            }
        )

    records.sort(key=lambda row: abs(_safe_float(row.get("delta_value"), 0.0)), reverse=True)
    return {
        "status": "found",
        "baseline_scenario": scenario_key,
        "baseline_run_id": run_id,
        "message": "Baseline comparison computed from latest historical baseline run.",
        "metrics": {"records": records},
    }


def create_exchange_bundle_zip(run_dir: Path) -> Path | None:
    exchange_dir = run_dir / "exchange"
    zip_path = run_dir / "exchange_bundle.zip"
    with ZipFile(zip_path, mode="w", compression=ZIP_DEFLATED) as zf:
        if exchange_dir.exists() and exchange_dir.is_dir():
            for path in sorted(exchange_dir.rglob("*")):
                if path.is_file():
                    zf.write(path, arcname=str(path.relative_to(run_dir)))
        for name in ("results.csv", "development_impacts.json", "coupling_manifest.json", "integrated_results.json"):
            candidate = run_dir / name
            if candidate.exists() and candidate.is_file():
                zf.write(candidate, arcname=name)
    return zip_path


def build_run_report_markdown(summary: Dict[str, Any], integrated: Dict[str, Any]) -> str:
    now = datetime.now(timezone.utc).isoformat()
    run_id = str(summary.get("run_id", ""))
    scenario = str(summary.get("scenario", ""))
    warnings = summary.get("warnings") or []

    run_meta = ((summary.get("summary_diagnostics") or {}).get("run_metadata") or {})
    confidence = (integrated.get("development_confidence") or {})
    metrics = ((integrated.get("integrated_overview") or {}).get("metrics") or [])
    drivers = (integrated.get("development_drivers") or {})
    reliability = ((summary.get("summary_diagnostics") or {}).get("reliability") or {})
    baseline = (integrated.get("baseline_comparison") or {})

    lines = [
        "# EDIM Run Report",
        "",
        f"- generated_at_utc: `{now}`",
        f"- run_id: `{run_id}`",
        f"- scenario: `{scenario}`",
        f"- fast_dev_mode: `{summary.get('fast_dev_mode')}`",
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

    lines.extend(["", "## Baseline Comparison", ""])
    baseline_status = str(baseline.get("status", "not_configured"))
    lines.append(f"- status: `{baseline_status}`")
    lines.append(f"- baseline_scenario: `{baseline.get('baseline_scenario', '')}`")
    lines.append(f"- baseline_run_id: `{baseline.get('baseline_run_id', '')}`")
    if baseline.get("message"):
        lines.append(f"- message: {baseline.get('message')}")
    baseline_metrics = ((baseline.get("metrics") or {}).get("records") or [])
    if baseline_metrics:
        lines.append("- metric_deltas:")
        for row in baseline_metrics[:6]:
            label = str(row.get("label", row.get("key", "")))
            delta = _safe_float(row.get("delta_value"), 0.0)
            lines.append(f"  - {label}: `{delta:.6f}`")

    lines.extend(
        [
            "",
            "## Coupling Diagnostics",
            "",
            f"- coupling_mode: `{confidence.get('coupling_mode', '')}`",
            f"- mapping_coverage_share: `{_safe_float(confidence.get('mapping_coverage_share'), 0.0):.6f}`",
            f"- fallback_mapping_share: `{_safe_float(confidence.get('fallback_mapping_share'), 0.0):.6f}`",
            f"- mario_runtime_executed: `{bool(confidence.get('mario_runtime_executed', False))}`",
            f"- mario_runtime_seconds: `{_safe_float(confidence.get('mario_runtime_seconds'), 0.0):.6f}`",
            f"- mario_runner_source: `{confidence.get('mario_runner_source', '')}`",
            "",
            "## Development Drivers",
            "",
            f"- capex_effect_musd: `{_safe_float(drivers.get('capex_effect_musd'), 0.0):.6f}`",
            f"- opex_effect_musd: `{_safe_float(drivers.get('opex_effect_musd'), 0.0):.6f}`",
            f"- reliability_penalty_proxy: `{_safe_float(drivers.get('reliability_penalty_proxy'), 0.0):.6f}`",
            f"- import_leakage_musd: `{_safe_float(drivers.get('import_leakage_musd'), 0.0):.6f}`",
            "",
            "## Reliability",
            "",
            f"- demand_total: `{_safe_float(reliability.get('demand_total'), 0.0):.6f}`",
            f"- unserved_total: `{_safe_float(reliability.get('unserved_total'), 0.0):.6f}`",
            f"- unserved_energy_share: `{_safe_float(reliability.get('unserved_energy_share'), 0.0):.6f}`",
            f"- hours_with_unserved: `{int(_safe_float(reliability.get('hours_with_unserved'), 0.0))}`",
            "",
            "## Caveats",
            "",
        ]
    )

    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- No warnings recorded.")

    return "\n".join(lines) + "\n"
