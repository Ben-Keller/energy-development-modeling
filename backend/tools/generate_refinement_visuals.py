#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd
import yaml


POOL_LOCATION_FILES = {
    "CAPP": "CAPP/Location_Constraints_CAPP.yaml",
    "EAPP": "EAPP/Location_Constraints_EAPP.yaml",
    "NAPP": "NAPP/Location_Constraints_NAPP.yaml",
    "SAPP": "SAPP/Location_Constraints_SAPP.yaml",
    "WAPP": "WAPP/Location_Constraints_WAPP.yaml",
}


def _find_latest_run_with_results(runs_dir: Path) -> Path:
    csv_candidates = [p for p in runs_dir.glob("*/artifacts/final/results.csv") if p.is_file()]
    if csv_candidates:
        return max(csv_candidates, key=lambda p: p.stat().st_mtime)
    raise FileNotFoundError(f"No declared results_csv artifact found under {runs_dir}")


def _load_pool_mapping(calliope_root: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for pool, rel_path in POOL_LOCATION_FILES.items():
        path = calliope_root / rel_path
        if not path.exists():
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for loc in (data.get("locations") or {}).keys():
            out[str(loc)] = pool
    return out


def _tech_group(tech: str) -> str:
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


def _pretty_number(value: float) -> str:
    v = float(value)
    av = abs(v)
    if av >= 1_000_000_000:
        return f"{v / 1_000_000_000:.2f}B"
    if av >= 1_000_000:
        return f"{v / 1_000_000:.2f}M"
    if av >= 1_000:
        return f"{v / 1_000:.2f}K"
    return f"{v:.2f}"


def _write_hbar_svg(
    path: Path,
    title: str,
    subtitle: str,
    rows: Iterable[Tuple[str, float]],
    color: str = "#3f7df0",
    width: int = 1100,
) -> None:
    rows_list = list(rows)
    if not rows_list:
        rows_list = [("No data", 0.0)]

    left_margin = 300
    right_margin = 160
    top_margin = 100
    row_height = 42
    bar_height = 22
    chart_width = width - left_margin - right_margin
    height = top_margin + len(rows_list) * row_height + 60
    max_value = max(abs(v) for _, v in rows_list) or 1.0

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#0b1220"/>',
        f'<text x="{left_margin}" y="40" fill="#e6edf8" font-size="24" font-family="Arial" font-weight="700">{html.escape(title)}</text>',
        f'<text x="{left_margin}" y="66" fill="#9fb0c9" font-size="14" font-family="Arial">{html.escape(subtitle)}</text>',
    ]

    y = top_margin
    for label, value in rows_list:
        bar_w = (abs(value) / max_value) * chart_width
        lines.append(
            f'<text x="{left_margin - 12}" y="{y + 16}" fill="#d6e0f0" font-size="14" font-family="Arial" text-anchor="end">{html.escape(str(label))}</text>'
        )
        lines.append(
            f'<rect x="{left_margin}" y="{y}" width="{bar_w:.2f}" height="{bar_height}" rx="4" fill="{color}" />'
        )
        lines.append(
            f'<text x="{left_margin + chart_width + 10}" y="{y + 16}" fill="#d6e0f0" font-size="14" font-family="Arial">{html.escape(_pretty_number(value))}</text>'
        )
        y += row_height

    lines.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_diverging_svg(
    path: Path,
    title: str,
    subtitle: str,
    rows: Iterable[Tuple[str, float]],
    width: int = 1200,
) -> None:
    rows_list = list(rows)
    if not rows_list:
        rows_list = [("No data", 0.0)]

    left_margin = 300
    right_margin = 180
    top_margin = 110
    row_height = 42
    bar_height = 20
    chart_width = width - left_margin - right_margin
    half = chart_width / 2
    zero_x = left_margin + half
    max_abs = max(abs(v) for _, v in rows_list) or 1.0
    height = top_margin + len(rows_list) * row_height + 80

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#0b1220"/>',
        f'<text x="{left_margin}" y="40" fill="#e6edf8" font-size="24" font-family="Arial" font-weight="700">{html.escape(title)}</text>',
        f'<text x="{left_margin}" y="68" fill="#9fb0c9" font-size="14" font-family="Arial">{html.escape(subtitle)}</text>',
        f'<line x1="{zero_x}" y1="{top_margin - 20}" x2="{zero_x}" y2="{height - 30}" stroke="#5d6f8a" stroke-width="1.5"/>',
        f'<text x="{zero_x - 8}" y="{top_margin - 30}" fill="#6ed08a" font-size="12" font-family="Arial" text-anchor="end">Net import</text>',
        f'<text x="{zero_x + 8}" y="{top_margin - 30}" fill="#7fb2ff" font-size="12" font-family="Arial">Net export</text>',
    ]

    y = top_margin
    for label, value in rows_list:
        w = (abs(value) / max_abs) * half
        if value >= 0:
            x = zero_x
            fill = "#4f87ff"
        else:
            x = zero_x - w
            fill = "#6ecf8a"
        lines.append(
            f'<text x="{left_margin - 12}" y="{y + 15}" fill="#d6e0f0" font-size="14" font-family="Arial" text-anchor="end">{html.escape(str(label))}</text>'
        )
        lines.append(
            f'<rect x="{x:.2f}" y="{y}" width="{w:.2f}" height="{bar_height}" rx="4" fill="{fill}" />'
        )
        lines.append(
            f'<text x="{left_margin + chart_width + 10}" y="{y + 15}" fill="#d6e0f0" font-size="14" font-family="Arial">{html.escape(_pretty_number(value))}</text>'
        )
        y += row_height

    lines.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _load_run_metadata(run_dir: Path) -> Tuple[str, str, str]:
    summary_path = run_dir / "artifacts" / "final" / "summary.json"
    if not summary_path.exists():
        summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        return "unknown", "unknown", "n/a"
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return "unknown", "unknown", "n/a"

    diagnostics = (payload.get("summary_diagnostics") or {})
    run_meta = diagnostics.get("run_metadata") or {}
    scenario = str(payload.get("scenario") or "unknown")
    solved_at = str(run_meta.get("time_finished") or "unknown")
    solution_time = str(run_meta.get("solution_time_seconds") or "n/a")
    return scenario, solved_at, solution_time


def _series_from_results_frame(results: pd.DataFrame, pool_map: Dict[str, str]):
    frame = results.copy()
    if "variable" not in frame.columns or "value" not in frame.columns:
        raise ValueError("Results frame must include 'variable' and 'value' columns.")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame.dropna(subset=["value"])

    carrier_prod = frame[frame["variable"] == "carrier_prod"].copy()
    if "loc_tech_carriers_prod" in carrier_prod.columns:
        split = carrier_prod["loc_tech_carriers_prod"].astype(str).str.split("::", n=2, expand=True)
        if split.shape[1] >= 2:
            carrier_prod["loc"] = split[0]
            carrier_prod["tech"] = split[1]
    elif "loc_tech_carriers" in carrier_prod.columns:
        split = carrier_prod["loc_tech_carriers"].astype(str).str.split("::", n=2, expand=True)
        if split.shape[1] >= 2:
            carrier_prod["loc"] = split[0]
            carrier_prod["tech"] = split[1]

    generation_by_group = pd.DataFrame(columns=["group", "value"])
    generation_by_pool = pd.DataFrame(columns=["pool", "value"])
    net = pd.DataFrame(columns=["pool", "net_export"])
    if {"loc", "tech"}.issubset(carrier_prod.columns):
        carrier_prod["group"] = carrier_prod["tech"].map(_tech_group)
        carrier_prod["pool"] = carrier_prod["loc"].map(pool_map).fillna("UNKNOWN")
        generation_by_group = (
            carrier_prod.groupby("group", as_index=False)["value"].sum().sort_values("value", ascending=False)
        )
        generation_by_pool = (
            carrier_prod.groupby("pool", as_index=False)["value"].sum().sort_values("value", ascending=False)
        )

        # Inter-pool transmission net: +export (prod side) / -import.
        trans = carrier_prod[carrier_prod["tech"].str.contains("Transmission|_kV:", regex=True, na=False)].copy()
        if not trans.empty:
            trans["dst"] = trans["tech"].str.split(":").str[-1]
            trans["src_pool"] = trans["loc"].map(pool_map).fillna("UNKNOWN")
            trans["dst_pool"] = trans["dst"].map(pool_map).fillna("UNKNOWN")
            inter = trans[trans["src_pool"] != trans["dst_pool"]]
            exports = inter.groupby("src_pool")["value"].sum()
            imports = inter.groupby("dst_pool")["value"].sum()
            pools = sorted(set(exports.index) | set(imports.index))
            net = pd.DataFrame(
                {
                    "pool": pools,
                    "net_export": [
                        float(exports.get(pool, 0.0) - imports.get(pool, 0.0))
                        for pool in pools
                    ],
                }
            ).sort_values("net_export", ascending=False)

    energy_cap = frame[frame["variable"] == "energy_cap"].copy()
    capacity_by_group = pd.DataFrame(columns=["group", "value"])
    if "loc_techs" in energy_cap.columns:
        split = energy_cap["loc_techs"].astype(str).str.split("::", n=1, expand=True)
        if split.shape[1] >= 2:
            energy_cap["tech"] = split[1]
            energy_cap["group"] = energy_cap["tech"].map(_tech_group)
            capacity_by_group = (
                energy_cap.groupby("group", as_index=False)["value"].sum().sort_values("value", ascending=False)
            )

    cost = frame[frame["variable"] == "cost"].copy()
    cost_by_class = pd.DataFrame(columns=["costs", "value"])
    if "costs" in cost.columns:
        cost_by_class = cost.groupby("costs", as_index=False)["value"].sum().sort_values("value", ascending=False)

    return generation_by_group, generation_by_pool, capacity_by_group, cost_by_class, net


def _rows(df: pd.DataFrame, label_col: str, value_col: str, limit: int = 10) -> List[Tuple[str, float]]:
    if label_col not in df.columns or value_col not in df.columns:
        return []
    top = df.head(limit)
    return [(str(r[label_col]), float(r[value_col])) for _, r in top.iterrows()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate EDIM refinement diagnostic SVGs.")
    parser.add_argument("--runs-dir", default="outputs/runs", help="Path to runs directory.")
    parser.add_argument(
        "--calliope-root",
        default="model_runtime/model_modules/calliope/Calliope-Africa-main",
        help="Path to Calliope-Africa root.",
    )
    parser.add_argument(
        "--output-dir", default="outputs/figures", help="Directory where SVG charts will be written."
    )
    parser.add_argument("--run-id", default="", help="Optional run ID to use instead of latest run.")
    args = parser.parse_args()

    runs_dir = Path(args.runs_dir)
    calliope_root = Path(args.calliope_root)
    output_dir = Path(args.output_dir)

    if args.run_id:
        csv_path = runs_dir / args.run_id / "artifacts" / "final" / "results.csv"
        if csv_path.exists():
            results_path = csv_path
        else:
            raise FileNotFoundError(f"No declared results_csv artifact for run_id={args.run_id}")
    else:
        results_path = _find_latest_run_with_results(runs_dir)

    pool_map = _load_pool_mapping(calliope_root)
    results_frame = pd.read_csv(results_path)
    gen_group, gen_pool, cap_group, cost_class, net_pool = _series_from_results_frame(results_frame, pool_map)

    run_dir = results_path.parents[2]
    run_id = run_dir.name
    scenario, solved_at, solution_time = _load_run_metadata(run_dir)
    subtitle = f"run_id={run_id}, scenario={scenario}, solved_at={solved_at}, solution_time={solution_time}s"

    _write_hbar_svg(
        output_dir / "generation_by_group.svg",
        "Generation by Technology Group",
        subtitle,
        _rows(gen_group, "group", "value", limit=12),
        color="#5d95ff",
    )
    _write_hbar_svg(
        output_dir / "generation_by_pool.svg",
        "Generation by Power Pool",
        subtitle,
        _rows(gen_pool, "pool", "value", limit=10),
        color="#41b98b",
    )
    _write_hbar_svg(
        output_dir / "capacity_by_group.svg",
        "Installed Capacity by Technology Group",
        subtitle,
        _rows(cap_group, "group", "value", limit=12),
        color="#cf7dff",
    )
    _write_hbar_svg(
        output_dir / "cost_by_class.svg",
        "System Cost by Cost Class",
        subtitle + " (note: co2 is model cost-class proxy, not physical emissions)",
        _rows(cost_class, "costs", "value", limit=10),
        color="#ff9770",
    )
    _write_diverging_svg(
        output_dir / "net_interpool_transmission.svg",
        "Net Inter-pool Transmission (Prod-side)",
        subtitle,
        _rows(net_pool, "pool", "net_export", limit=10),
    )

    print(f"Wrote charts to {output_dir.resolve()}")
    for p in sorted(output_dir.glob("*.svg")):
        print(p.resolve())


if __name__ == "__main__":
    main()
