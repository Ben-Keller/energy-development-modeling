from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd


REQUIRED_MARIO_INPUT_FILES = [
    "calliope_tech_to_mario_sector.csv",
    "capex_sector_split.csv",
    "opex_sector_split.csv",
    "calliope_cost_to_mario_account.csv",
    "country_to_pool.csv",
    "employment_intensity.csv",
    "value_added_intensity.csv",
]

OPTIONAL_MARIO_INPUT_FILES = [
    "development_indicator_mapping.csv",
    "scenario_assumptions.csv",
]

EXPERT_OWNED_DATASETS: Dict[str, Dict[str, Any]] = {
    "employment_intensity.csv": {
        "label": "Employment intensity table",
        "strict_blocking": True,
        "description": "Direct and total jobs factors by MARIO region and sector.",
    },
    "value_added_intensity.csv": {
        "label": "Value-added intensity table",
        "strict_blocking": True,
        "description": "GVA and household-income multipliers by MARIO region and sector.",
    },
    "scenario_assumptions.csv": {
        "label": "Scenario assumptions table",
        "strict_blocking": True,
        "description": "Exogenous macro and policy assumptions used by integrated indicators.",
    },
    "development_indicator_mapping.csv": {
        "label": "Development indicator mapping",
        "strict_blocking": False,
        "description": "Maps modeled metrics into reported development indicators.",
    },
}

PLACEHOLDER_SOURCE_VALUES = {"placeholder", "todo", "tbd", "sample", "example"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            out: List[Dict[str, str]] = []
            for row in reader:
                if not isinstance(row, dict):
                    continue
                out.append({str(k): "" if v is None else str(v).strip() for k, v in row.items()})
            return out
    except Exception:
        return []


def _placeholder_examples_for_rows(rows: List[Dict[str, str]], max_examples: int = 5) -> Tuple[int, List[Dict[str, Any]]]:
    count = 0
    examples: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows, start=2):
        source = str(row.get("source", "")).strip().lower()
        notes = str(row.get("notes", "")).strip().lower()
        is_placeholder = source in PLACEHOLDER_SOURCE_VALUES or ("placeholder" in source)
        if not is_placeholder and notes:
            is_placeholder = ("placeholder" in notes) or ("replace with" in notes)
        if not is_placeholder:
            continue
        count += 1
        if len(examples) >= max_examples:
            continue
        label_parts = [
            str(row.get("assumption_key", "")).strip(),
            str(row.get("indicator_id", "")).strip(),
            str(row.get("mario_region", "")).strip(),
            str(row.get("mario_sector", "")).strip(),
        ]
        label = " / ".join([part for part in label_parts if part][:3])
        examples.append(
            {
                "line": idx,
                "label": label,
                "source": str(row.get("source", "")).strip(),
                "notes": str(row.get("notes", "")).strip(),
            }
        )
    return count, examples


def _normalize_year(value: Any) -> int | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        year = int(float(raw))
    except Exception:
        return None
    return year if year > 0 else None


def _assumption_scope_rank(row_scenario: str, target_scenario: str) -> int:
    normalized = str(row_scenario or "").strip().lower()
    target = str(target_scenario or "").strip().lower()
    if target and normalized == target:
        return 3
    if normalized == "baseline":
        return 2
    if not normalized:
        return 1
    return 0


def load_scenario_assumptions(
    config_dir: Path,
    scenario_key: str = "",
    run_year: int | None = None,
) -> Dict[str, Any]:
    path = config_dir / "mario_inputs" / "scenario_assumptions.csv"
    rows = _read_csv_rows(path)
    placeholder_row_count, placeholder_examples = _placeholder_examples_for_rows(rows)
    selected_candidates: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        assumption_key = str(row.get("assumption_key", "")).strip()
        scenario_name = str(row.get("scenario_key", "")).strip()
        if not assumption_key:
            continue
        scope_rank = _assumption_scope_rank(scenario_name, scenario_key)
        if scope_rank <= 0:
            continue
        effective_year = _normalize_year(row.get("effective_year"))
        candidate = {
            **row,
            "effective_year": effective_year,
            "scope_rank": scope_rank,
        }
        selected_candidates.setdefault(assumption_key, []).append(candidate)

    selected_records: List[Dict[str, Any]] = []
    selected_values: Dict[str, Dict[str, Any]] = {}
    selected_placeholder_row_count = 0
    for assumption_key, candidates in selected_candidates.items():
        candidates.sort(
            key=lambda row: (
                int(row.get("scope_rank") or 0),
                int(row.get("effective_year") or -1),
            ),
            reverse=True,
        )
        chosen = candidates[0]
        selected_records.append(
            {
                "assumption_key": assumption_key,
                "scenario_key": str(chosen.get("scenario_key", "")).strip(),
                "value": str(chosen.get("value", "")).strip(),
                "value_numeric": _safe_float(chosen.get("value"), float("nan")),
                "unit": str(chosen.get("unit", "")).strip(),
                "effective_year": chosen.get("effective_year"),
                "source": str(chosen.get("source", "")).strip(),
                "notes": str(chosen.get("notes", "")).strip(),
                "match_scope": (
                    "scenario"
                    if _assumption_scope_rank(chosen.get("scenario_key", ""), scenario_key) >= 3
                    else "baseline"
                    if str(chosen.get("scenario_key", "")).strip().lower() == "baseline"
                    else "default"
                ),
            }
        )
        selected_values[assumption_key] = selected_records[-1]
        source = str(chosen.get("source", "")).strip().lower()
        notes = str(chosen.get("notes", "")).strip().lower()
        if source in PLACEHOLDER_SOURCE_VALUES or "placeholder" in source or "placeholder" in notes or "replace with" in notes:
            selected_placeholder_row_count += 1

    selected_records.sort(key=lambda row: str(row.get("assumption_key", "")))
    return {
        "path": str(path),
        "exists": path.exists(),
        "requested_scenario": str(scenario_key or ""),
        "run_year": int(run_year) if run_year else None,
        "records": selected_records,
        "selected_values": selected_values,
        "selected_count": len(selected_records),
        "selected_placeholder_row_count": int(selected_placeholder_row_count),
        "file_placeholder_row_count": int(placeholder_row_count),
        "file_placeholder_examples": placeholder_examples,
    }


def load_development_indicator_mapping(config_dir: Path) -> Dict[str, Any]:
    path = config_dir / "mario_inputs" / "development_indicator_mapping.csv"
    rows = _read_csv_rows(path)
    normalized_rows = []
    for row in rows:
        indicator_id = str(row.get("indicator_id", "")).strip()
        if not indicator_id:
            continue
        normalized_rows.append(
            {
                "indicator_id": indicator_id,
                "indicator_name": str(row.get("indicator_name", "")).strip() or indicator_id,
                "driver_metric": str(row.get("driver_metric", "")).strip(),
                "aggregation_rule": str(row.get("aggregation_rule", "")).strip(),
                "unit": str(row.get("unit", "")).strip(),
                "lag_years": _normalize_year(row.get("lag_years")) or 0,
                "notes": str(row.get("notes", "")).strip(),
            }
        )
    return {
        "path": str(path),
        "exists": path.exists(),
        "records": normalized_rows,
        "record_count": len(normalized_rows),
    }


def mario_inputs_health(config_dir: Path) -> Dict[str, Any]:
    mario_dir = config_dir / "mario_inputs"
    out = {
        "mario_dir": str(mario_dir),
        "exists": mario_dir.exists(),
        "missing_required": [],
        "present_required": [],
        "missing_optional": [],
        "present_optional": [],
        "expert_owned_files": sorted(EXPERT_OWNED_DATASETS.keys()),
        "placeholder_files": [],
        "placeholder_row_counts": {},
        "placeholder_details": [],
        "blocking_placeholder_files": [],
        "expert_inputs_ready": False,
        "ok": False,
    }
    if not mario_dir.exists():
        out["missing_required"] = list(REQUIRED_MARIO_INPUT_FILES)
        out["missing_optional"] = list(OPTIONAL_MARIO_INPUT_FILES)
        return out

    missing: List[str] = []
    present: List[str] = []
    for name in REQUIRED_MARIO_INPUT_FILES:
        candidate = mario_dir / name
        if candidate.exists() and candidate.is_file():
            present.append(name)
        else:
            missing.append(name)

    out["missing_required"] = missing
    out["present_required"] = present
    missing_optional: List[str] = []
    present_optional: List[str] = []
    for name in OPTIONAL_MARIO_INPUT_FILES:
        candidate = mario_dir / name
        if candidate.exists() and candidate.is_file():
            present_optional.append(name)
        else:
            missing_optional.append(name)
    out["missing_optional"] = missing_optional
    out["present_optional"] = present_optional

    placeholder_details: List[Dict[str, Any]] = []
    placeholder_row_counts: Dict[str, int] = {}
    blocking_placeholder_files: List[str] = []
    for file_name, meta in EXPERT_OWNED_DATASETS.items():
        candidate = mario_dir / file_name
        rows = _read_csv_rows(candidate)
        placeholder_count, examples = _placeholder_examples_for_rows(rows)
        if placeholder_count <= 0:
            continue
        placeholder_row_counts[file_name] = int(placeholder_count)
        placeholder_details.append(
            {
                "file_name": file_name,
                "label": str(meta.get("label", file_name)),
                "strict_blocking": bool(meta.get("strict_blocking", False)),
                "placeholder_row_count": int(placeholder_count),
                "examples": examples,
            }
        )
        if bool(meta.get("strict_blocking", False)):
            blocking_placeholder_files.append(file_name)

    out["placeholder_row_counts"] = placeholder_row_counts
    out["placeholder_details"] = placeholder_details
    out["placeholder_files"] = sorted(placeholder_row_counts.keys())
    out["blocking_placeholder_files"] = sorted(blocking_placeholder_files)
    out["expert_inputs_ready"] = len(blocking_placeholder_files) == 0
    out["ok"] = len(missing) == 0
    return out


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _normalize_str_columns(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    out = df.copy()
    for col in cols:
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].fillna("").astype(str).str.strip()
    return out


def _resolve_intensity_row(
    intensity_df: pd.DataFrame,
    region: str,
    sector: str,
    region_col: str,
    sector_col: str,
) -> Tuple[pd.Series, str]:
    exact = intensity_df[
        (intensity_df[region_col] == str(region)) & (intensity_df[sector_col] == str(sector))
    ]
    if not exact.empty:
        return exact.iloc[0], "exact"

    region_rows = intensity_df[intensity_df[region_col] == str(region)]
    if not region_rows.empty:
        numeric = region_rows.select_dtypes(include=["number"]).mean(numeric_only=True)
        merged = pd.Series({**region_rows.iloc[0].to_dict(), **numeric.to_dict()})
        return merged, "region_mean"

    if not intensity_df.empty:
        numeric = intensity_df.select_dtypes(include=["number"]).mean(numeric_only=True)
        merged = pd.Series({**intensity_df.iloc[0].to_dict(), **numeric.to_dict()})
        return merged, "global_mean"

    return pd.Series(dtype=float), "default"


def _sum_col(df: pd.DataFrame, col: str) -> float:
    if col not in df.columns or df.empty:
        return 0.0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0.0).sum())


def _relative_bounds(value: float, rel: float) -> Tuple[float, float]:
    bounded = max(0.0, float(rel))
    return max(value * (1.0 - bounded), 0.0), max(value * (1.0 + bounded), 0.0)


def _to_records(df: pd.DataFrame, cols: List[str], value_cols: List[str], max_rows: int = 200) -> List[Dict[str, Any]]:
    if df.empty:
        return []
    out = df.copy()
    for col in cols:
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].astype(str)
    for col in value_cols:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0).astype(float)
    out = out.sort_values(value_cols[0], ascending=False, key=lambda s: s.abs())
    if len(out) > max_rows:
        out = out.head(max_rows)
    return out[cols + value_cols].to_dict(orient="records")


def _empty_mario_development_payload(
    *,
    run_id: str,
    scenario: str,
    year: int,
    inv_df: pd.DataFrame,
    op_df: pd.DataFrame,
    reason: str,
) -> Dict[str, Any]:
    total_shock = _sum_col(inv_df, "shock_value_musd") + _sum_col(op_df, "shock_value_musd")
    return {
        "run_id": run_id,
        "scenario": scenario,
        "method": "mario_io_runtime_v1",
        "inputs": {
            "investment_shock_total_musd": _sum_col(inv_df, "shock_value_musd"),
            "operating_shock_total_musd": _sum_col(op_df, "shock_value_musd"),
            "total_shock_musd": total_shock,
        },
        "totals": {
            "jobs_direct": 0.0,
            "jobs_total": 0.0,
            "gva_total_musd": 0.0,
            "household_income_proxy_musd": 0.0,
        },
        "uncertainty": {
            "method": "relative_bounds_v1",
            "totals_bounds": {
                "jobs_direct_low": 0.0,
                "jobs_direct_high": 0.0,
                "jobs_total_low": 0.0,
                "jobs_total_high": 0.0,
                "gva_total_musd_low": 0.0,
                "gva_total_musd_high": 0.0,
                "household_income_proxy_musd_low": 0.0,
                "household_income_proxy_musd_high": 0.0,
            },
        },
        "by_region": {"records": []},
        "by_supplier_sector": {"records": []},
        "by_region_supplier": {"records": []},
        "diagnostics": {
            "shock_rows_used": 0,
            "intensity_match_counts": {"exact": 0, "region_mean": 0, "global_mean": 0, "default": 0},
            "year": int(year),
            "empty_reason": reason,
        },
        "metadata": {"engine": "mario", "source_tables_dir": "", "result_mode": "zero_output"},
    }


def run_mario_io_runtime(
    exchange_dir: Path,
    config_dir: Path,
    run_id: str,
    scenario: str,
    year: int,
    uncertainty_relative: Dict[str, float] | None = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    warnings: List[str] = []
    mario_dir = config_dir / "mario_inputs"
    health = mario_inputs_health(config_dir)
    if not health["ok"]:
        missing = ", ".join(health.get("missing_required", []))
        raise RuntimeError(f"MARIO runtime missing required inputs: {missing}")

    inv_df = _normalize_str_columns(_read_csv(exchange_dir / "investment_shocks.csv"), ["region", "mario_sector", "technology"])
    op_df = _normalize_str_columns(_read_csv(exchange_dir / "operating_shocks.csv"), ["region", "mario_sector", "technology"])
    shock_parts = [df for df in (inv_df, op_df) if not df.empty]
    shocks = pd.concat(shock_parts, axis=0, ignore_index=True) if shock_parts else pd.DataFrame()
    if shocks.empty:
        warnings.append("MARIO runtime received no exchange shock rows; returning zero development impacts.")
        development = _empty_mario_development_payload(
            run_id=run_id,
            scenario=scenario,
            year=year,
            inv_df=inv_df,
            op_df=op_df,
            reason="no_exchange_shock_rows",
        )
        development["metadata"]["source_tables_dir"] = str(mario_dir)
        runtime_meta = {
            "mario_runtime_executed": True,
            "mario_runtime_error": "",
            "mario_runner_source": "builtin:model_runtime.edim_model.core.mario_runtime.run_mario_io_runtime",
            "bridge_method": "calliope_to_mario_exchange_with_io_runtime",
            "shock_record_count": 0,
        }
        return development, runtime_meta, warnings

    if "shock_value_musd" not in shocks.columns:
        if "shock_value" in shocks.columns:
            shocks["shock_value_musd"] = pd.to_numeric(shocks["shock_value"], errors="coerce").fillna(0.0)
        else:
            shocks["shock_value_musd"] = 0.0
    shocks["shock_value_musd"] = pd.to_numeric(shocks["shock_value_musd"], errors="coerce").fillna(0.0)

    emp = _normalize_str_columns(
        _read_csv(mario_dir / "employment_intensity.csv"),
        ["mario_region", "mario_sector"],
    )
    va = _normalize_str_columns(
        _read_csv(mario_dir / "value_added_intensity.csv"),
        ["mario_region", "mario_sector"],
    )
    for col in ("jobs_per_musd_direct", "jobs_per_musd_total"):
        if col not in emp.columns:
            emp[col] = 0.0
        emp[col] = pd.to_numeric(emp[col], errors="coerce").fillna(0.0)
    for col in ("gva_per_musd_output", "household_income_per_musd_output"):
        if col not in va.columns:
            va[col] = 0.0
        va[col] = pd.to_numeric(va[col], errors="coerce").fillna(0.0)

    detail_rows: List[Dict[str, Any]] = []
    intensity_match_counts = {"exact": 0, "region_mean": 0, "global_mean": 0, "default": 0}

    for row in shocks.to_dict(orient="records"):
        region = str(row.get("region", "")).strip() or "UNKNOWN"
        sector = str(row.get("mario_sector", "")).strip() or "UNKNOWN"
        shock = max(_safe_float(row.get("shock_value_musd"), 0.0), 0.0)
        if shock <= 0:
            continue

        emp_row, emp_mode = _resolve_intensity_row(
            emp, region=region, sector=sector, region_col="mario_region", sector_col="mario_sector"
        )
        va_row, va_mode = _resolve_intensity_row(
            va, region=region, sector=sector, region_col="mario_region", sector_col="mario_sector"
        )
        intensity_match_counts[emp_mode] = intensity_match_counts.get(emp_mode, 0) + 1
        intensity_match_counts[va_mode] = intensity_match_counts.get(va_mode, 0) + 1

        jobs_direct = shock * _safe_float(emp_row.get("jobs_per_musd_direct"), 0.0)
        jobs_total = shock * _safe_float(emp_row.get("jobs_per_musd_total"), 0.0)
        gva_total = shock * _safe_float(va_row.get("gva_per_musd_output"), 0.0)
        hh_income = shock * _safe_float(va_row.get("household_income_per_musd_output"), 0.0)

        if jobs_total < jobs_direct:
            jobs_total = jobs_direct

        detail_rows.append(
            {
                "region": region,
                "supplier_sector": sector,
                "technology": str(row.get("technology", "")),
                "shock_value_musd": shock,
                "jobs_direct": jobs_direct,
                "jobs_total": jobs_total,
                "gva_total_musd": gva_total,
                "household_income_proxy_musd": hh_income,
            }
        )

    if not detail_rows:
        warnings.append("MARIO runtime received only non-positive shock values; returning zero development impacts.")
        development = _empty_mario_development_payload(
            run_id=run_id,
            scenario=scenario,
            year=year,
            inv_df=inv_df,
            op_df=op_df,
            reason="non_positive_exchange_shocks",
        )
        development["metadata"]["source_tables_dir"] = str(mario_dir)
        runtime_meta = {
            "mario_runtime_executed": True,
            "mario_runtime_error": "",
            "mario_runner_source": "builtin:model_runtime.edim_model.core.mario_runtime.run_mario_io_runtime",
            "bridge_method": "calliope_to_mario_exchange_with_io_runtime",
            "shock_record_count": 0,
        }
        return development, runtime_meta, warnings

    detail = pd.DataFrame(detail_rows)
    totals = {
        "jobs_direct": _sum_col(detail, "jobs_direct"),
        "jobs_total": _sum_col(detail, "jobs_total"),
        "gva_total_musd": _sum_col(detail, "gva_total_musd"),
        "household_income_proxy_musd": _sum_col(detail, "household_income_proxy_musd"),
    }

    by_region = (
        detail.groupby("region", as_index=False)[
            ["shock_value_musd", "jobs_direct", "jobs_total", "gva_total_musd", "household_income_proxy_musd"]
        ]
        .sum()
        .rename(columns={"region": "region"})
    )
    by_sector = (
        detail.groupby("supplier_sector", as_index=False)[
            ["shock_value_musd", "jobs_direct", "jobs_total", "gva_total_musd", "household_income_proxy_musd"]
        ]
        .sum()
        .rename(columns={"supplier_sector": "supplier_sector"})
    )
    by_region_sector = detail.groupby(["region", "supplier_sector"], as_index=False)[
        ["shock_value_musd", "jobs_direct", "jobs_total", "gva_total_musd", "household_income_proxy_musd"]
    ].sum()

    uncertainty_cfg = uncertainty_relative or {}
    jd_low, jd_high = _relative_bounds(totals["jobs_direct"], _safe_float(uncertainty_cfg.get("jobs_direct"), 0.12))
    jt_low, jt_high = _relative_bounds(totals["jobs_total"], _safe_float(uncertainty_cfg.get("jobs_total"), 0.12))
    gva_low, gva_high = _relative_bounds(
        totals["gva_total_musd"], _safe_float(uncertainty_cfg.get("gva_total_musd"), 0.12)
    )
    inc_low, inc_high = _relative_bounds(
        totals["household_income_proxy_musd"],
        _safe_float(uncertainty_cfg.get("household_income_proxy_musd"), 0.12),
    )

    development = {
        "run_id": run_id,
        "scenario": scenario,
        "method": "mario_io_runtime_v1",
        "inputs": {
            "investment_shock_total_musd": _sum_col(inv_df, "shock_value_musd"),
            "operating_shock_total_musd": _sum_col(op_df, "shock_value_musd"),
            "total_shock_musd": _sum_col(shocks, "shock_value_musd"),
        },
        "totals": totals,
        "uncertainty": {
            "method": "relative_bounds_v1",
            "totals_bounds": {
                "jobs_direct_low": jd_low,
                "jobs_direct_high": jd_high,
                "jobs_total_low": jt_low,
                "jobs_total_high": jt_high,
                "gva_total_musd_low": gva_low,
                "gva_total_musd_high": gva_high,
                "household_income_proxy_musd_low": inc_low,
                "household_income_proxy_musd_high": inc_high,
            },
        },
        "by_region": {
            "records": _to_records(
                by_region,
                cols=["region"],
                value_cols=["shock_value_musd", "jobs_direct", "jobs_total", "gva_total_musd", "household_income_proxy_musd"],
                max_rows=200,
            )
        },
        "by_supplier_sector": {
            "records": _to_records(
                by_sector,
                cols=["supplier_sector"],
                value_cols=["shock_value_musd", "jobs_direct", "jobs_total", "gva_total_musd", "household_income_proxy_musd"],
                max_rows=200,
            )
        },
        "by_region_supplier": {
            "records": _to_records(
                by_region_sector,
                cols=["region", "supplier_sector"],
                value_cols=["shock_value_musd", "jobs_direct", "jobs_total", "gva_total_musd", "household_income_proxy_musd"],
                max_rows=300,
            )
        },
        "diagnostics": {
            "shock_rows_used": int(len(detail)),
            "intensity_match_counts": intensity_match_counts,
            "year": int(year),
        },
        "metadata": {"engine": "mario", "source_tables_dir": str(mario_dir)},
    }

    runtime_meta = {
        "mario_runtime_executed": True,
        "mario_runtime_error": "",
        "mario_runner_source": "builtin:model_runtime.edim_model.core.mario_runtime.run_mario_io_runtime",
        "bridge_method": "calliope_to_mario_exchange_with_io_runtime",
        "shock_record_count": int(len(detail)),
    }
    return development, runtime_meta, warnings


def write_exchange_schema_validation(
    schema_path: Path,
    exchange_dir: Path,
) -> Dict[str, Any]:
    rows: List[Dict[str, str]] = []
    if schema_path.exists():
        with schema_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if isinstance(row, dict):
                    rows.append({str(k): str(v) for k, v in row.items()})

    issues: List[str] = []
    checked_files: set[str] = set()
    for row in rows:
        file_name = str(row.get("file_name", "")).strip()
        col = str(row.get("column_name", "")).strip()
        required = str(row.get("required", "")).strip().lower() == "yes"
        if not file_name or not col:
            continue
        checked_files.add(file_name)
        path = exchange_dir / file_name
        if not path.exists():
            if required:
                issues.append(f"Missing required exchange file: {file_name}")
            continue
        try:
            df = pd.read_csv(path, nrows=1)
        except Exception:
            issues.append(f"Could not parse exchange file: {file_name}")
            continue
        if required and col not in df.columns:
            issues.append(f"Missing required column {file_name}.{col}")

    return {
        "schema_path": str(schema_path),
        "checked_files": sorted(checked_files),
        "issues": issues,
        "ok": len(issues) == 0,
    }


def write_runtime_log(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
