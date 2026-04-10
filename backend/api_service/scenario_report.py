from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from zipfile import ZipFile


DOCX_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
SCENARIO_ID_RE = re.compile(r"\b([A-Z]{2}-S[12])\b")
PERCENT_RE = re.compile(r"[-+]?\d+(?:\.\d+)?\s*%")
YEAR_RE = re.compile(r"\b(20\d{2}|19\d{2})\b")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _cell_text(cell: ET.Element) -> str:
    paragraphs: List[str] = []
    for para in cell.findall("./w:p", DOCX_NS):
        text = "".join(t.text or "" for t in para.findall(".//w:t", DOCX_NS)).strip()
        if text:
            paragraphs.append(text)
    return " ".join(paragraphs).strip()


def _read_docx_tables(path: Path) -> List[List[List[str]]]:
    with ZipFile(path) as z:
        document_xml = z.read("word/document.xml")
    root = ET.fromstring(document_xml)
    tables: List[List[List[str]]] = []
    for table in root.findall(".//w:tbl", DOCX_NS):
        rows: List[List[str]] = []
        for tr in table.findall("./w:tr", DOCX_NS):
            cells = [_cell_text(tc) for tc in tr.findall("./w:tc", DOCX_NS)]
            if any(cells):
                rows.append(cells)
        if rows:
            tables.append(rows)
    return tables


def _read_docx_paragraphs(path: Path) -> List[str]:
    with ZipFile(path) as z:
        document_xml = z.read("word/document.xml")
    root = ET.fromstring(document_xml)
    paragraphs: List[str] = []
    for para in root.findall(".//w:p", DOCX_NS):
        text = "".join(t.text or "" for t in para.findall(".//w:t", DOCX_NS)).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def _parse_percent(raw: str) -> float | None:
    text = str(raw or "").replace("~", "")
    match = PERCENT_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group(0).replace("%", "").strip()) / 100.0
    except ValueError:
        return None


def _parse_signed_percent(raw: str) -> float | None:
    text = str(raw or "").replace("~", "")
    match = PERCENT_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group(0).replace("%", "").strip()) / 100.0
    except ValueError:
        return None


def _parse_years(*values: str) -> List[int]:
    years: set[int] = set()
    for value in values:
        for match in YEAR_RE.finditer(str(value or "")):
            try:
                years.add(int(match.group(1)))
            except ValueError:
                continue
    return sorted(years)


def _normalize_geo_code(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    return text.split()[0].strip()


def _scenario_type_from_id(scenario_id: str) -> str:
    return "full_decarbonization" if str(scenario_id).endswith("-S1") else "policy_target"


def _collect_paragraph_window(paragraphs: List[str], scenario_id: str) -> Dict[str, str]:
    start = -1
    for idx, para in enumerate(paragraphs):
        if scenario_id in para:
            start = idx
            break
    if start < 0:
        return {"description": "", "implementation_notes": "", "policy_sources": ""}
    end = len(paragraphs)
    for idx in range(start + 1, len(paragraphs)):
        if SCENARIO_ID_RE.search(paragraphs[idx]) and scenario_id not in paragraphs[idx]:
            end = idx
            break
    window = paragraphs[start:end]
    implementation = ""
    sources = ""
    for para in window:
        if para.lower().startswith("mario implementation notes:"):
            implementation = para.split(":", 1)[1].strip()
        elif para.lower().startswith("policy sources:"):
            sources = para.split(":", 1)[1].strip()
    description = " ".join(p for p in window[:3] if scenario_id not in p)[:1000]
    return {
        "description": description,
        "implementation_notes": implementation,
        "policy_sources": sources,
    }


def parse_scenario_report(report_path: Path) -> Dict[str, Any]:
    report_path = report_path.resolve()
    if not report_path.exists():
        raise FileNotFoundError(f"Scenario report not found: {report_path}")

    tables = _read_docx_tables(report_path)
    paragraphs = _read_docx_paragraphs(report_path)
    source_hash = _sha256(report_path)

    geographies: Dict[str, Dict[str, str]] = {}
    scenario_labels: Dict[str, Dict[str, str]] = {}
    shock_structure: List[Dict[str, str]] = []
    shock_file_structure: List[Dict[str, str]] = []
    calibration_steps: List[Dict[str, str]] = []
    summary_by_id: Dict[str, Dict[str, Any]] = {}
    detail_by_id: Dict[str, List[Dict[str, str]]] = {}

    for rows in tables:
        header = [str(x).strip() for x in rows[0]]
        header_key = "|".join(h.lower() for h in header)
        if header[:3] == ["Type", "Geography", "Exiobase Code"]:
            for row in rows[1:]:
                if len(row) < 3:
                    continue
                code = _normalize_geo_code(row[2])
                geographies[code] = {
                    "type": row[0],
                    "name": row[1],
                    "exiobase_code": code,
                    "source_code_label": row[2],
                }
        elif header[:3] == ["#", "Scenario", "Description"]:
            for row in rows[1:]:
                if len(row) < 3:
                    continue
                scenario_labels[row[0]] = {"label": row[1], "description": row[2]}
        elif header[:3] == ["Shock Type", "MARIO Parameter", "Description"]:
            for row in rows[1:]:
                if len(row) >= 3:
                    shock_structure.append(
                        {"shock_type": row[0], "mario_parameter": row[1], "description": row[2]}
                    )
        elif header[:3] == ["Sheet Name", "MARIO Parameter", "Content Description"]:
            for row in rows[1:]:
                if len(row) >= 3:
                    shock_file_structure.append(
                        {"sheet_name": row[0], "mario_parameter": row[1], "description": row[2]}
                    )
        elif header[:3] == ["Step", "Action", "Notes"]:
            for row in rows[1:]:
                if len(row) >= 3:
                    calibration_steps.append({"step": row[0], "action": row[1], "notes": row[2]})
        elif header[:7] == [
            "ID",
            "Geography",
            "RE Share 2030",
            "RE Share 2050",
            "Fossil Δ 2030",
            "Net-Zero Year",
            "Shock Type",
        ]:
            for row in rows[1:]:
                if len(row) < 7:
                    continue
                scenario_id = str(row[0]).strip()
                summary_by_id[scenario_id] = {
                    "scenario_id": scenario_id,
                    "geography_name": row[1],
                    "renewable_share_2030": row[2],
                    "renewable_share_2030_numeric": _parse_percent(row[2]),
                    "renewable_share_2050": row[3],
                    "renewable_share_2050_numeric": _parse_percent(row[3]),
                    "fossil_delta_2030": row[4],
                    "fossil_delta_2030_numeric": _parse_signed_percent(row[4]),
                    "net_zero_year": row[5],
                    "net_zero_year_numeric": (_parse_years(row[5]) or [None])[0],
                    "shock_type": row[6],
                }
        else:
            title = str(rows[0][0]).strip() if rows and rows[0] else ""
            match = SCENARIO_ID_RE.search(title)
            if match and len(rows) >= 3:
                scenario_id = match.group(1)
                records: List[Dict[str, str]] = []
                for row in rows[2:]:
                    if len(row) >= 3:
                        records.append(
                            {
                                "parameter": row[0],
                                "target_2030": row[1],
                                "target_2050": row[2],
                            }
                        )
                detail_by_id[scenario_id] = records

    scenarios: Dict[str, Any] = {}
    for scenario_id, summary in sorted(summary_by_id.items()):
        geo_code = scenario_id.split("-", 1)[0]
        scenario_code = scenario_id.split("-", 1)[1]
        para_meta = _collect_paragraph_window(paragraphs, scenario_id)
        target_years = {2030, 2050}
        if summary.get("net_zero_year_numeric"):
            target_years.add(int(summary["net_zero_year_numeric"]))
        label = scenario_labels.get(scenario_code, {}).get("label") or summary.get("shock_type") or scenario_code
        scenarios[scenario_id] = {
            "scenario_id": scenario_id,
            "geography_code": geo_code,
            "geography": geographies.get(geo_code, {"name": summary.get("geography_name", ""), "type": ""}),
            "scenario_code": scenario_code,
            "scenario_type": _scenario_type_from_id(scenario_id),
            "label": label,
            "description": para_meta["description"] or scenario_labels.get(scenario_code, {}).get("description", ""),
            "summary": summary,
            "targets": detail_by_id.get(scenario_id, []),
            "target_years": sorted(target_years),
            "shock_categories": {
                "A/Z": [row for row in detail_by_id.get(scenario_id, []) if "coefficient" in row.get("parameter", "").lower() or "share" in row.get("parameter", "").lower()],
                "E": [row for row in detail_by_id.get(scenario_id, []) if "co2" in row.get("parameter", "").lower() or "emission" in row.get("parameter", "").lower()],
                "Y": [row for row in detail_by_id.get(scenario_id, []) if any(k in row.get("parameter", "").lower() for k in ("capacity", "demand", "access", "investment"))],
            },
            "implementation_notes": para_meta["implementation_notes"],
            "policy_sources": para_meta["policy_sources"],
            "provenance": {
                "source_file": str(report_path),
                "source_sha256": source_hash,
            },
        }

    return {
        "schema_version": "scenario_report_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_file": str(report_path),
        "source_sha256": source_hash,
        "geographies": geographies,
        "scenario_labels": scenario_labels,
        "shock_structure": shock_structure,
        "shock_file_structure": shock_file_structure,
        "calibration_steps": calibration_steps,
        "scenarios": scenarios,
        "scenario_ids": sorted(scenarios.keys()),
    }


def load_or_parse_scenario_report(config_dir: Path, report_path: Path | None = None) -> Dict[str, Any]:
    config_dir = config_dir.resolve()
    repo_root = config_dir.parent
    source_path = (report_path or (repo_root / "Energy Modelling Scenario Report.docx")).resolve()
    cache_dir = config_dir / "generated"
    cache_path = cache_dir / "scenario_report_scenarios.json"

    if source_path.exists() and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("source_sha256") == _sha256(source_path):
                return cached
        except Exception:
            pass

    parsed = parse_scenario_report(source_path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(parsed, indent=2, sort_keys=True), encoding="utf-8")
    return parsed
