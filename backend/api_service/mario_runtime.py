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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def mario_inputs_health(config_dir: Path) -> Dict[str, Any]:
    mario_dir = config_dir / "mario_inputs"
    out = {
        "mario_dir": str(mario_dir),
        "exists": mario_dir.exists(),
        "missing_required": [],
        "present_required": [],
        "ok": False,
    }
    if not mario_dir.exists():
        out["missing_required"] = list(REQUIRED_MARIO_INPUT_FILES)
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
            "mario_runner_source": "builtin:api_service.mario_runtime.run_mario_io_runtime",
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
            "mario_runner_source": "builtin:api_service.mario_runtime.run_mario_io_runtime",
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
        "mario_runner_source": "builtin:api_service.mario_runtime.run_mario_io_runtime",
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
