from __future__ import annotations

"""
Summary payload builders for the EDIM MVP backend.

This module intentionally keeps summary logic deterministic and data-first:
- `build_summary_core(...)` extracts compact chart-ready aggregates from model outputs.
- `build_summary_diagnostics(...)` computes reliability/trade/emissions/cost diagnostics.

Key modeling assumptions to keep explicit for maintainers:
1. Pool mapping comes from Calliope location constraint YAML files.
2. Physical emissions are derived as generation * technology CO2 factor when available.
3. Technology grouping is heuristic string-based classification for visualization only.
4. Missing model variables do not hard-fail a run; warnings are emitted in summary payloads.
"""

import math
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import yaml


def _to_dataframe(da) -> pd.DataFrame:
    try:
        return da.to_dataframe(name="value").reset_index()
    except Exception:
        return pd.DataFrame(columns=["value"])


def _clean_values(df: pd.DataFrame) -> pd.DataFrame:
    if "value" not in df.columns:
        return pd.DataFrame(columns=["value"])
    out = df.copy()
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.replace([np.inf, -np.inf], np.nan).dropna(subset=["value"])
    return out


def _expand_composite_indices(df: pd.DataFrame) -> pd.DataFrame:
    """
    Expand common Calliope composite indices (loc::tech::carrier) into chart-friendly columns.
    """
    if df.empty:
        return df
    out = df.copy()
    for col in list(out.columns):
        if col.startswith("loc_tech_carriers"):
            split = out[col].astype(str).str.split("::", n=2, expand=True)
            if split.shape[1] >= 1 and "locs" not in out.columns:
                out["locs"] = split[0]
            if split.shape[1] >= 2 and "techs" not in out.columns:
                out["techs"] = split[1]
            if split.shape[1] >= 3 and "carriers" not in out.columns:
                out["carriers"] = split[2]
        elif col.startswith("loc_techs"):
            split = out[col].astype(str).str.split("::", n=1, expand=True)
            if split.shape[1] >= 1 and "locs" not in out.columns:
                out["locs"] = split[0]
            if split.shape[1] >= 2 and "techs" not in out.columns:
                out["techs"] = split[1]
        elif col == "loc_carriers":
            split = out[col].astype(str).str.split("::", n=1, expand=True)
            if split.shape[1] >= 1 and "locs" not in out.columns:
                out["locs"] = split[0]
            if split.shape[1] >= 2 and "carriers" not in out.columns:
                out["carriers"] = split[1]
    return out


def _to_records(df: pd.DataFrame, dims: List[str], max_rows: int | None = None) -> List[Dict[str, Any]]:
    if df.empty or "value" not in df.columns:
        return []
    keep = [c for c in dims if c in df.columns]
    out = df[keep + ["value"]].copy()
    if max_rows is not None and len(out) > max_rows:
        out = out.head(max_rows)
    out["value"] = out["value"].astype(float).round(6)
    for c in keep:
        out[c] = out[c].astype(str)
    return out.to_dict(orient="records")


def _maybe_get(model, varname: str):
    try:
        return model.results[varname]
    except Exception:
        return None


def _maybe_get_input(model, varname: str):
    try:
        return model.inputs[varname]
    except Exception:
        pass
    try:
        return model._model_data[varname]
    except Exception:
        return None


def _summarize_generation(
    da,
    max_generation_techs: int,
    max_generation_timesteps: int,
    warnings: List[str],
) -> List[Dict[str, Any]]:
    df = _expand_composite_indices(_clean_values(_to_dataframe(da)))
    if not {"timesteps", "techs"}.issubset(df.columns):
        warnings.append("Result variable 'carrier_prod' is missing required dimensions (timesteps, techs).")
        return []

    df = df.groupby(["timesteps", "techs"], as_index=False)["value"].sum()

    tech_totals = (
        df.groupby(["techs"], as_index=False)["value"].sum().sort_values("value", ascending=False, key=lambda s: s.abs())
    )
    if len(tech_totals) > max_generation_techs:
        keep_techs = set(tech_totals.head(max_generation_techs)["techs"].tolist())
        df = df[df["techs"].isin(keep_techs)]

    unique_timesteps = sorted(df["timesteps"].dropna().astype(str).unique().tolist())
    if len(unique_timesteps) > max_generation_timesteps:
        step = max(1, math.ceil(len(unique_timesteps) / max_generation_timesteps))
        bucket_map = {t: idx // step for idx, t in enumerate(unique_timesteps)}
        bucket_label = {}
        for timestep, bucket in bucket_map.items():
            if bucket not in bucket_label:
                bucket_label[bucket] = timestep
        df = df.assign(_time_key=df["timesteps"].astype(str))
        df = df.assign(_bucket=df["_time_key"].map(bucket_map))
        df = df.groupby(["_bucket", "techs"], as_index=False)["value"].sum()
        df["timesteps"] = df["_bucket"].map(bucket_label)
        df = df.drop(columns=["_bucket", "_time_key"], errors="ignore")

    df = df.assign(_time_sort=df["timesteps"].astype(str)).sort_values(["_time_sort", "techs"])
    df = df.drop(columns=["_time_sort"])
    return _to_records(df, ["timesteps", "techs"])


def _summarize_category(
    da,
    dims: List[str],
    max_rows: int,
    warnings: List[str],
    label: str,
) -> List[Dict[str, Any]]:
    df = _expand_composite_indices(_clean_values(_to_dataframe(da)))
    group_dims = [d for d in dims if d in df.columns]
    if not group_dims:
        warnings.append(f"Result variable '{label}' is missing expected dimensions {dims}.")
        return []
    df = df.groupby(group_dims, as_index=False)["value"].sum()
    df = df.sort_values("value", ascending=False, key=lambda s: s.abs())
    if len(df) > max_rows:
        df = df.head(max_rows)
    return _to_records(df, group_dims)


def build_summary_core(
    model,
    run_id: str,
    scenario: str,
    fast_dev_mode: bool,
    warnings: List[str],
    max_generation_techs: int,
    max_generation_timesteps: int,
    max_category_rows: int,
    run_profile: str = "dev",
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "run_id": run_id,
        "scenario": scenario,
        "fast_dev_mode": fast_dev_mode,
        "run_profile": str(run_profile),
        "warnings": list(warnings),
        "generation_by_tech": {},
        "capacity_by_tech": {},
        "new_capacity_by_tech": {},
        "system_cost": {},
        "emissions": {},
    }

    carrier_prod = _maybe_get(model, "carrier_prod")
    if carrier_prod is not None:
        out["generation_by_tech"]["records"] = _summarize_generation(
            carrier_prod,
            max_generation_techs=max_generation_techs,
            max_generation_timesteps=max_generation_timesteps,
            warnings=out["warnings"],
        )
    else:
        out["warnings"].append("Result variable 'carrier_prod' not found; generation chart will be empty.")

    energy_cap = _maybe_get(model, "energy_cap")
    if energy_cap is not None:
        out["capacity_by_tech"]["records"] = _summarize_category(
            energy_cap,
            dims=["techs"],
            max_rows=max_category_rows,
            warnings=out["warnings"],
            label="energy_cap",
        )
    else:
        out["warnings"].append("Result variable 'energy_cap' not found; capacity chart will be empty.")

    energy_cap_new = _maybe_get(model, "energy_cap_new")
    energy_cap_new_missing = energy_cap_new is None
    if energy_cap_new is not None:
        out["new_capacity_by_tech"]["records"] = _summarize_category(
            energy_cap_new,
            dims=["techs"],
            max_rows=max_category_rows,
            warnings=out["warnings"],
            label="energy_cap_new",
        )

    cost = _maybe_get(model, "cost")
    if cost is not None:
        out["system_cost"]["records"] = _summarize_category(
            cost,
            dims=["costs"],
            max_rows=max_category_rows,
            warnings=out["warnings"],
            label="cost",
        )
    else:
        out["warnings"].append("Result variable 'cost' not found; cost chart will be empty.")

    emissions = _maybe_get(model, "emissions")
    if emissions is not None:
        out["emissions"]["records"] = _summarize_category(
            emissions,
            dims=["emissions", "techs"],
            max_rows=max_category_rows,
            warnings=out["warnings"],
            label="emissions",
        )
    else:
        co2_cost = None
        if cost is not None:
            try:
                if "costs" in cost.coords:
                    labels = [str(v) for v in cost["costs"].values.tolist()]
                    target = next((v for v in labels if v.strip().lower() == "co2"), None)
                    if target is not None:
                        co2_cost = cost.sel(costs=target)
            except Exception:
                co2_cost = None

        if co2_cost is not None:
            out["emissions"]["records"] = _summarize_category(
                co2_cost,
                dims=["emissions", "techs"],
                max_rows=max_category_rows,
                warnings=out["warnings"],
                label="emissions",
            )
        else:
            out["warnings"].append(
                "Result variable 'emissions' not found; emissions chart will be empty unless the model defines it."
            )

    if "records" not in out["new_capacity_by_tech"] or not out["new_capacity_by_tech"]["records"]:
        energy_cap_equals = _maybe_get(model, "energy_cap_equals")
        if energy_cap_equals is None:
            energy_cap_equals = _maybe_get_input(model, "energy_cap_equals")
        if energy_cap is not None and energy_cap_equals is not None:
            try:
                inferred_new_cap = (energy_cap - energy_cap_equals).clip(min=0)
                out["new_capacity_by_tech"]["records"] = _summarize_category(
                    inferred_new_cap,
                    dims=["techs"],
                    max_rows=max_category_rows,
                    warnings=out["warnings"],
                    label="energy_cap_new",
                )
            except Exception:
                pass
    if energy_cap_new_missing and (
        "records" not in out["new_capacity_by_tech"] or not out["new_capacity_by_tech"]["records"]
    ):
        out["warnings"].append("Result variable 'energy_cap_new' not found; new capacity chart will be empty.")

    return out


# Backward-compatible alias for older imports.
def summarize_model_results(*args, **kwargs):
    return build_summary_core(*args, **kwargs)


POOL_LOCATION_FILES = {
    "CAPP": "CAPP/Location_Constraints_CAPP.yaml",
    "EAPP": "EAPP/Location_Constraints_EAPP.yaml",
    "NAPP": "NAPP/Location_Constraints_NAPP.yaml",
    "SAPP": "SAPP/Location_Constraints_SAPP.yaml",
    "WAPP": "WAPP/Location_Constraints_WAPP.yaml",
}


def _classify_tech_group(tech: str) -> str:
    """Map detailed technology names to stable reporting groups."""
    t = str(tech)
    if "Transmission" in t or "_kV" in t:
        return "Transmission"
    if "Demand" in t:
        return "Demand"
    if t.startswith("Hydro"):
        return "Hydro"
    if t.startswith(("PV", "CSP", "Wind")):
        return "VRE"
    if t.startswith("Nuclear"):
        return "Nuclear"
    if t.startswith("Bioenergy"):
        return "Bioenergy"
    if t.startswith("Geothermal"):
        return "Geothermal"
    if any(k in t for k in ("Coal", "HFO", "Steam", "OCGT", "CCGT", "Diesel", "Gas_Engine", "ISCC")):
        return "Fossil"
    if "Battery" in t or "Storage" in t:
        return "Storage"
    return "Other"


def _load_pool_mapping(calliope_root: Path | None) -> Dict[str, str]:
    """Build loc -> pool lookup from Calliope-Africa location constraint YAMLs."""
    if calliope_root is None:
        return {}
    out: Dict[str, str] = {}
    for pool, rel_path in POOL_LOCATION_FILES.items():
        path = calliope_root / rel_path
        if not path.exists():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        for loc in (data.get("locations") or {}).keys():
            out[str(loc)] = pool
    return out


def _extract_run_metadata(model, run_id: str, scenario: str) -> Dict[str, Any]:
    """Extract lightweight solve metadata from Calliope/xarray attrs."""
    attrs = getattr(model.results, "attrs", {}) or {}
    run_config = attrs.get("run_config")
    solver = None
    if isinstance(run_config, str):
        try:
            parsed = yaml.safe_load(run_config) or {}
            solver = parsed.get("solver")
        except Exception:
            solver = None

    return {
        "run_id": run_id,
        "scenario": scenario,
        "termination_condition": str(attrs.get("termination_condition", "")),
        "objective_function_value": float(attrs.get("objective_function_value", 0.0))
        if attrs.get("objective_function_value") is not None
        else None,
        "solution_time_seconds": float(attrs.get("solution_time", 0.0))
        if attrs.get("solution_time") is not None
        else None,
        "time_finished": str(attrs.get("time_finished", "")),
        "calliope_version": str(attrs.get("calliope_version", "")),
        "solver": solver,
    }


def _summarize_reliability(model, pool_map: Dict[str, str], max_rows: int, warnings: List[str]) -> Dict[str, Any]:
    """Summarize demand/unserved metrics globally and by pool."""
    out: Dict[str, Any] = {
        "demand_total": 0.0,
        "unserved_total": 0.0,
        "unserved_energy_share": 0.0,
        "hours_with_unserved": 0,
        "max_unserved_hour": 0.0,
        "demand_by_pool": {"records": []},
        "unserved_by_pool": {"records": []},
    }

    demand_total = 0.0
    demand_pool_df = pd.DataFrame(columns=["pool", "value"])
    carrier_con = model.results["carrier_con"] if "carrier_con" in model.results else None
    if carrier_con is None:
        warnings.append("Summary diagnostics reliability: 'carrier_con' not found.")
    else:
        con_df = _expand_composite_indices(_clean_values(_to_dataframe(carrier_con)))
        if {"locs", "techs"}.issubset(con_df.columns):
            demand_df = con_df[con_df["techs"] == "Demand_power"].copy()
            if not demand_df.empty:
                demand_df["pool"] = demand_df["locs"].map(pool_map).fillna("UNKNOWN")
                demand_pool_df = (
                    demand_df.groupby("pool", as_index=False)["value"]
                    .sum()
                    .assign(value=lambda d: -d["value"])
                    .sort_values("value", ascending=False)
                )
                demand_total = float(-demand_df["value"].sum())
            else:
                warnings.append("Summary diagnostics reliability: no Demand_power rows found in carrier_con.")
        else:
            warnings.append("Summary diagnostics reliability: carrier_con missing loc/tech dimensions.")

    unmet_total = 0.0
    hours_with_unserved = 0
    max_unserved_hour = 0.0
    unmet_pool_df = pd.DataFrame(columns=["pool", "value"])
    unmet = model.results["unmet_demand"] if "unmet_demand" in model.results else None
    if unmet is None:
        warnings.append("Summary diagnostics reliability: 'unmet_demand' not found.")
    else:
        unmet_df = _expand_composite_indices(_clean_values(_to_dataframe(unmet)))
        if {"locs", "timesteps"}.issubset(unmet_df.columns):
            unmet_df["pool"] = unmet_df["locs"].map(pool_map).fillna("UNKNOWN")
            unmet_df["value"] = unmet_df["value"].clip(lower=0)
            unmet_total = float(unmet_df["value"].sum())
            unmet_pool_df = unmet_df.groupby("pool", as_index=False)["value"].sum().sort_values("value", ascending=False)
            hourly = unmet_df.groupby("timesteps", as_index=False)["value"].sum()
            hourly = hourly[hourly["value"] > 0]
            hours_with_unserved = int(len(hourly))
            max_unserved_hour = float(hourly["value"].max()) if not hourly.empty else 0.0
        else:
            warnings.append("Summary diagnostics reliability: unmet_demand missing loc/timestep dimensions.")

    out["demand_total"] = demand_total
    out["unserved_total"] = unmet_total
    out["unserved_energy_share"] = (unmet_total / demand_total) if demand_total > 0 else 0.0
    out["hours_with_unserved"] = hours_with_unserved
    out["max_unserved_hour"] = max_unserved_hour
    out["demand_by_pool"]["records"] = _to_records(demand_pool_df, ["pool"], max_rows=max_rows)
    out["unserved_by_pool"]["records"] = _to_records(unmet_pool_df, ["pool"], max_rows=max_rows)
    return out


def _is_transmission_tech(tech: str) -> bool:
    t = str(tech)
    return ("Transmission" in t) or ("_kV" in t)


def _summarize_trade_matrix(model, pool_map: Dict[str, str], max_rows: int, warnings: List[str]) -> Dict[str, Any]:
    """Build inter-pool transmission matrix and net import/export table."""
    out: Dict[str, Any] = {"records": [], "net_by_pool": {"records": []}, "total_interpool_flow": 0.0}
    carrier_prod = model.results["carrier_prod"] if "carrier_prod" in model.results else None
    if carrier_prod is None:
        warnings.append("Summary diagnostics trade_matrix: 'carrier_prod' not found.")
        return out

    df = _expand_composite_indices(_clean_values(_to_dataframe(carrier_prod)))
    if not {"locs", "techs"}.issubset(df.columns):
        warnings.append("Summary diagnostics trade_matrix: carrier_prod missing loc/tech dimensions.")
        return out

    trans = df[df["techs"].map(_is_transmission_tech)].copy()
    if trans.empty:
        return out
    trans["dst_loc"] = trans["techs"].astype(str).str.rsplit(":", n=1).str[-1]
    trans["src_pool"] = trans["locs"].map(pool_map).fillna("UNKNOWN")
    trans["dst_pool"] = trans["dst_loc"].map(pool_map).fillna("UNKNOWN")
    inter = trans[trans["src_pool"] != trans["dst_pool"]].copy()
    if inter.empty:
        return out

    trade = inter.groupby(["src_pool", "dst_pool"], as_index=False)["value"].sum()
    trade = trade.sort_values("value", ascending=False, key=lambda s: s.abs())
    if len(trade) > max_rows:
        warnings.append(f"Summary diagnostics trade_matrix truncated to {max_rows} rows.")
    out["records"] = _to_records(trade, ["src_pool", "dst_pool"], max_rows=max_rows)
    out["total_interpool_flow"] = float(trade["value"].sum())

    exports = inter.groupby("src_pool", as_index=False)["value"].sum().rename(columns={"src_pool": "pool", "value": "exports"})
    imports = inter.groupby("dst_pool", as_index=False)["value"].sum().rename(columns={"dst_pool": "pool", "value": "imports"})
    net = exports.merge(imports, on="pool", how="outer").fillna(0.0)
    net["value"] = net["exports"] - net["imports"]
    net = net.sort_values("value", ascending=False, key=lambda s: s.abs())
    out["net_by_pool"]["records"] = _to_records(net, ["pool"], max_rows=max_rows)
    return out


def _extract_emission_factors(tech_library: dict | None) -> Dict[str, float]:
    """Load om_prod CO2 factors from merged technology library."""
    out: Dict[str, float] = {}
    if not tech_library:
        return out
    for tech, body in (tech_library.get("techs") or {}).items():
        try:
            raw = body["costs"]["co2"]["om_prod"]
        except Exception:
            continue
        if isinstance(raw, (int, float)):
            out[str(tech)] = float(raw)
    return out


def _summarize_physical_emissions(
    model,
    tech_library: dict | None,
    pool_map: Dict[str, str],
    max_rows: int,
    warnings: List[str],
) -> Dict[str, Any]:
    """Compute physical emissions from generation and mapped technology factors."""
    out: Dict[str, Any] = {
        "method": "",
        "factor_coverage_share": 0.0,
        "total_emissions": 0.0,
        "by_tech": {"records": []},
        "by_pool": {"records": []},
    }
    carrier_prod = model.results["carrier_prod"] if "carrier_prod" in model.results else None
    if carrier_prod is None:
        warnings.append("Summary diagnostics physical_emissions: 'carrier_prod' not found.")
        return out

    gen = _expand_composite_indices(_clean_values(_to_dataframe(carrier_prod)))
    if not {"techs", "locs"}.issubset(gen.columns):
        warnings.append("Summary diagnostics physical_emissions: carrier_prod missing tech/loc dimensions.")
        return out

    factors = _extract_emission_factors(tech_library)
    if not factors:
        warnings.append("Summary diagnostics physical_emissions: no technology emission factors found in tech library.")
        return out

    gen["factor"] = gen["techs"].map(factors).fillna(0.0)
    gen["emissions"] = gen["value"] * gen["factor"]
    covered_generation = float(gen.loc[gen["factor"] > 0, "value"].sum())
    total_generation = float(gen["value"].sum())
    out["factor_coverage_share"] = (covered_generation / total_generation) if total_generation > 0 else 0.0

    by_tech = gen.groupby("techs", as_index=False)["emissions"].sum().rename(columns={"emissions": "value"})
    by_pool = (
        gen.assign(pool=gen["locs"].map(pool_map).fillna("UNKNOWN"))
        .groupby("pool", as_index=False)["emissions"]
        .sum()
        .rename(columns={"emissions": "value"})
    )
    by_tech = by_tech.sort_values("value", ascending=False, key=lambda s: s.abs())
    by_pool = by_pool.sort_values("value", ascending=False, key=lambda s: s.abs())
    out["method"] = "generation_x_tech_co2_factor"
    out["total_emissions"] = float(by_tech["value"].sum()) if not by_tech.empty else 0.0
    out["by_tech"]["records"] = _to_records(by_tech, ["techs"], max_rows=max_rows)
    out["by_pool"]["records"] = _to_records(by_pool, ["pool"], max_rows=max_rows)
    return out


def _component_var_defs() -> Dict[str, List[str]]:
    return {
        "investment": ["cost_investment"],
        "fixed_om": ["cost_om_annual"],
        "variable_prod": ["cost_om_prod", "cost_var"],
        "variable_con": ["cost_om_con"],
    }


def _summarize_cost_decomposition(model, max_rows: int, warnings: List[str]) -> Dict[str, Any]:
    """Aggregate component costs to chart-ready records."""
    out: Dict[str, Any] = {"component_records": [], "class_totals": {"records": []}}
    parts: List[pd.DataFrame] = []
    for component, candidates in _component_var_defs().items():
        chosen_var = ""
        for var in candidates:
            if var in model.results:
                chosen_var = var
                break
        if not chosen_var:
            continue
        df = _expand_composite_indices(_clean_values(_to_dataframe(model.results[chosen_var])))
        if "costs" not in df.columns:
            continue
        if "timesteps" in df.columns:
            group_cols = [c for c in ("costs", "techs", "timesteps") if c in df.columns]
            if "timesteps" in group_cols:
                group_cols.remove("timesteps")
            df = df.groupby(group_cols, as_index=False)["value"].sum()
        elif "techs" in df.columns:
            df = df.groupby(["costs", "techs"], as_index=False)["value"].sum()
        else:
            df = df.groupby(["costs"], as_index=False)["value"].sum()

        if "techs" in df.columns:
            df["tech_group"] = df["techs"].map(_classify_tech_group)
            df = df.groupby(["costs", "tech_group"], as_index=False)["value"].sum()
        else:
            df["tech_group"] = "ALL"
        df["component"] = component
        parts.append(df[["costs", "component", "tech_group", "value"]])

    if not parts:
        warnings.append("Summary diagnostics cost_decomposition: no component cost variables found.")
    else:
        merged = pd.concat(parts, axis=0, ignore_index=True)
        merged = merged.sort_values("value", ascending=False, key=lambda s: s.abs())
        if len(merged) > max_rows:
            warnings.append(f"Summary diagnostics cost_decomposition component records truncated to {max_rows}.")
        out["component_records"] = _to_records(merged, ["costs", "component", "tech_group"], max_rows=max_rows)

    if "cost" in model.results:
        total = _clean_values(_to_dataframe(model.results["cost"]))
        if "costs" in total.columns:
            class_totals = total.groupby("costs", as_index=False)["value"].sum()
            class_totals = class_totals.sort_values("value", ascending=False, key=lambda s: s.abs())
            out["class_totals"]["records"] = _to_records(class_totals, ["costs"], max_rows=max_rows)
    return out


def build_summary_diagnostics(
    model,
    run_id: str,
    scenario: str,
    calliope_root: Path | None,
    tech_library: dict | None,
    max_rows: int,
    warnings: List[str],
) -> Dict[str, Any]:
    """Build diagnostics payload used by API + UI detailed panels."""
    pool_map = _load_pool_mapping(calliope_root)
    return {
        "version": "1.0",
        "run_metadata": _extract_run_metadata(model, run_id=run_id, scenario=scenario),
        "reliability": _summarize_reliability(model, pool_map=pool_map, max_rows=max_rows, warnings=warnings),
        "trade_matrix": _summarize_trade_matrix(model, pool_map=pool_map, max_rows=max_rows, warnings=warnings),
        "physical_emissions": _summarize_physical_emissions(
            model,
            tech_library=tech_library,
            pool_map=pool_map,
            max_rows=max_rows,
            warnings=warnings,
        ),
        "cost_decomposition": _summarize_cost_decomposition(model, max_rows=max_rows, warnings=warnings),
    }
