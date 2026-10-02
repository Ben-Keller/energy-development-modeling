from __future__ import annotations

"""Basic project report generation from backend-owned export records.

This module intentionally stays model-agnostic. It consumes project/run/export
metadata plus already-declared run summary artifacts and produces report-ready
Markdown and a structured JSON source payload. Future rich report renderers can
replace this service without changing platform routes.
"""

import json
from typing import Any, Dict, Iterable, List


REPORT_SOURCE_SCHEMA_VERSION = "edim_project_report_source_v1"
EVIDENCE_STATUS_ORDER = {
    "not_evaluated": 0,
    "production_ready": 1,
    "analyst_review": 2,
    "exploratory_only": 3,
}


def evidence_from_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    integrated = summary.get("integrated_results") if isinstance(summary.get("integrated_results"), dict) else {}
    quality = integrated.get("model_quality") if isinstance(integrated.get("model_quality"), dict) else {}
    status = str(quality.get("status") or "not_evaluated").strip().lower()
    if status not in EVIDENCE_STATUS_ORDER:
        status = "not_evaluated"
    issues = quality.get("issues") if isinstance(quality.get("issues"), list) else []
    try:
        score = int(round(float(quality.get("score") or 0)))
    except (TypeError, ValueError):
        score = 0
    return {
        "status": status,
        "score": max(0, min(100, score)),
        "summary": str(quality.get("summary") or ""),
        "issue_count": len(issues),
        "requires_acknowledgement": status == "exploratory_only",
    }


def aggregate_evidence(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    evidence_rows = [dict(row or {}) for row in rows]
    statuses = [str(row.get("status") or "not_evaluated") for row in evidence_rows]
    overall = max(statuses, key=lambda value: EVIDENCE_STATUS_ORDER.get(value, 0), default="not_evaluated")
    return {
        "status": overall,
        "requires_acknowledgement": "exploratory_only" in statuses,
        "counts": {status: statuses.count(status) for status in EVIDENCE_STATUS_ORDER},
    }


def build_project_report_source_data(
    *,
    project: Dict[str, Any],
    run_records: Iterable[Dict[str, Any]],
    summaries: Dict[str, Dict[str, Any]],
    exports: Iterable[Dict[str, Any]],
    report_type: str,
    options: Dict[str, Any],
    generated_by_user_id: str,
    generated_at: str,
) -> Dict[str, Any]:
    """Build the stable source-data payload used by the basic report renderer."""

    runs = [_run_source_row(row, summaries.get(str(row.get("run_id") or ""), {})) for row in run_records]
    export_rows = [_export_source_row(row) for row in exports]
    evidence_rows = [evidence_from_summary(summaries.get(str(row.get("run_id") or ""), {})) for row in run_records]
    evidence_overview = aggregate_evidence(evidence_rows)
    return {
        "schema_version": REPORT_SOURCE_SCHEMA_VERSION,
        "report_type": str(report_type or "project_summary"),
        "generated_at": generated_at,
        "generated_by_user_id": generated_by_user_id,
        "project": {
            "project_id": str(project.get("project_id") or ""),
            "title": str(project.get("title") or ""),
            "geography": str(project.get("geography") or ""),
            "scenario_label": str(project.get("scenario_label") or ""),
            "owner_user_id": str(project.get("owner_user_id") or project.get("created_by_user_id") or ""),
            "status": str(project.get("status") or ""),
        },
        "run_count": len(runs),
        "completed_run_count": sum(1 for row in runs if row.get("status") == "succeeded"),
        "evidence": evidence_overview,
        "runs": runs,
        "exports": export_rows,
        "options": dict(options or {}),
    }


def build_project_report_markdown(source_data: Dict[str, Any]) -> str:
    """Render a basic Markdown project report from source data."""

    project = source_data.get("project") if isinstance(source_data.get("project"), dict) else {}
    runs = source_data.get("runs") if isinstance(source_data.get("runs"), list) else []
    exports = source_data.get("exports") if isinstance(source_data.get("exports"), list) else []
    options = source_data.get("options") if isinstance(source_data.get("options"), dict) else {}
    report_title = str(source_data.get("report_type") or "project_summary").replace("_", " ").title()

    lines = [
        f"# EDIM {report_title}",
        "",
        f"> Evidence status: **{str((source_data.get('evidence') or {}).get('status') or 'not_evaluated').replace('_', ' ').title()}**",
        (
            "> Exploratory output: this report includes results that require explicit analyst acknowledgement "
            "and must not be treated as policy-grade evidence."
            if bool((source_data.get("evidence") or {}).get("requires_acknowledgement"))
            else "> Review the model-quality and provenance sections before using results in decisions."
        ),
        "",
        "## Report Metadata",
        "",
        f"- Generated at: {source_data.get('generated_at', '-')}",
        f"- Generated by: `{source_data.get('generated_by_user_id', '-')}`",
        f"- Source schema: `{source_data.get('schema_version', REPORT_SOURCE_SCHEMA_VERSION)}`",
        "",
        "## Project",
        "",
        f"- Project: {project.get('title') or project.get('project_id') or '-'}",
        f"- Project ID: `{project.get('project_id', '-')}`",
        f"- Owner: `{project.get('owner_user_id', '-')}`",
        f"- Geography: {project.get('geography') or '-'}",
        f"- Scenario label: {project.get('scenario_label') or '-'}",
        "",
        "## Model Overview",
        "",
        f"- Models included: `{source_data.get('run_count', 0)}`",
        f"- Completed executions: `{source_data.get('completed_run_count', 0)}`",
        "",
    ]

    if runs:
        lines.extend(
            [
                "| Model | Execution status | Energy scenario | MRIO scenario | Target year | Execution profile |",
                "| --- | --- | --- | --- | ---: | --- |",
            ]
        )
        for row in runs:
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{row.get('run_id', '-')}`",
                        str(row.get("status") or "-"),
                        str(row.get("energy_scenario_key") or "-"),
                        str(row.get("mrio_scenario_id") or "-"),
                        str(row.get("target_year") or "-"),
                        str(row.get("run_profile") or "-"),
                    ]
                )
                + " |"
            )
    else:
        lines.append("No models were included in this report.")

    lines.extend(["", "## Integrated Metrics", ""])
    metric_rows = _metric_rows_for_report(runs)
    if metric_rows:
        lines.extend(["| Model | Metric | Value | Unit |", "| --- | --- | ---: | --- |"])
        for row in metric_rows:
            lines.append(
                f"| `{row['run_id']}` | {row['label']} | {_format_value(row['value'])} | {row['unit'] or '-'} |"
            )
    else:
        lines.append("No integrated metrics were available for the selected models.")

    lines.extend(["", "## Export Data", ""])
    if exports:
        lines.extend(["| Export | Models | Size | Status |", "| --- | ---: | ---: | --- |"])
        for row in exports:
            lines.append(
                f"| `{row.get('export_id', '-')}` | {len(row.get('run_ids') or [])} | {_format_value(row.get('size_bytes', 0))} bytes | {row.get('status', '-')} |"
            )
    else:
        lines.append("No project export bundles existed when this report was generated.")

    lines.extend(["", "## Artifact Availability", ""])
    artifact_rows = _artifact_rows_for_report(runs)
    if artifact_rows:
        lines.extend(["| Model | Artifact | Kind | Download |", "| --- | --- | --- | --- |"])
        for row in artifact_rows:
            lines.append(
                f"| `{row.get('run_id', '-')}` | `{row.get('artifact_id', '-')}` | {row.get('kind', '-')} | {row.get('download_url') or '-'} |"
            )
    else:
        lines.append("No artifact catalog rows were available for the selected models.")

    warnings = [warning for run in runs for warning in (run.get("warnings") or []) if warning]
    lines.extend(["", "## Warnings", ""])
    if warnings:
        for warning in warnings[:50]:
            lines.append(f"- {warning}")
    else:
        lines.append("No execution warnings were reported for the selected models.")

    if options:
        lines.extend(["", "## Report Options", "", "```json", json.dumps(options, indent=2, sort_keys=True), "```"])

    return "\n".join(lines) + "\n"


def _run_source_row(record: Dict[str, Any], summary: Dict[str, Any]) -> Dict[str, Any]:
    request = record.get("request") if isinstance(record.get("request"), dict) else {}
    integrated = summary.get("integrated_results") if isinstance(summary.get("integrated_results"), dict) else {}
    overview = integrated.get("integrated_overview") if isinstance(integrated.get("integrated_overview"), dict) else {}
    metrics = overview.get("metrics") if isinstance(overview.get("metrics"), list) else []
    artifacts = summary.get("artifact_catalog") if isinstance(summary.get("artifact_catalog"), list) else record.get("artifact_catalog") or []
    evidence = evidence_from_summary(summary)
    return {
        "run_id": str(record.get("run_id") or ""),
        "execution_id": str(record.get("execution_id") or ""),
        "run_name": str(record.get("run_name") or request.get("run_name") or ""),
        "status": str(record.get("status") or ""),
        "stage": str(record.get("stage") or ""),
        "progress": float(record.get("progress") or 0.0),
        "energy_scenario_key": str(request.get("energy_scenario_key") or summary.get("energy_scenario_key") or ""),
        "mrio_scenario_id": str(request.get("mrio_scenario_id") or summary.get("mrio_scenario_id") or ""),
        "target_year": request.get("target_year") or summary.get("target_year") or "",
        "run_profile": str(request.get("run_profile") or summary.get("run_profile") or ""),
        "created_at": str(record.get("created_at") or ""),
        "finished_at": str(record.get("finished_at") or ""),
        "summary_available": bool(summary),
        "metrics": [_metric_source_row(metric) for metric in metrics if isinstance(metric, dict)],
        "artifact_catalog": [dict(row) for row in artifacts if isinstance(row, dict)],
        "warnings": list(summary.get("warnings") or []),
        "evidence": evidence,
    }


def _metric_source_row(metric: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "key": str(metric.get("key") or ""),
        "label": str(metric.get("label") or metric.get("key") or ""),
        "unit": str(metric.get("unit") or ""),
        "value": metric.get("value"),
    }


def _export_source_row(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "export_id": str(record.get("export_id") or ""),
        "project_id": str(record.get("project_id") or ""),
        "run_ids": list(record.get("run_ids") or []),
        "status": str(record.get("status") or ""),
        "size_bytes": int(record.get("size_bytes") or 0),
        "created_at": str(record.get("created_at") or ""),
        "download_url": str(record.get("download_url") or ""),
    }


def _metric_rows_for_report(runs: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for run in runs:
        run_id = str(run.get("run_id") or "")
        for metric in run.get("metrics") or []:
            if not isinstance(metric, dict):
                continue
            rows.append(
                {
                    "run_id": run_id,
                    "label": metric.get("label") or metric.get("key") or "-",
                    "unit": metric.get("unit") or "",
                    "value": metric.get("value"),
                }
            )
    return rows


def _artifact_rows_for_report(runs: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for run in runs:
        run_id = str(run.get("run_id") or "")
        for artifact in run.get("artifact_catalog") or []:
            if not isinstance(artifact, dict):
                continue
            rows.append(
                {
                    "run_id": run_id,
                    "artifact_id": str(artifact.get("artifact_id") or ""),
                    "kind": str(artifact.get("kind") or ""),
                    "download_url": str(artifact.get("download_url") or ""),
                }
            )
    return rows[:100]


def _format_value(value: Any) -> str:
    try:
        number = float(value)
    except Exception:
        return str(value if value is not None else "-")
    if abs(number) >= 1_000_000:
        return f"{number:,.0f}"
    if abs(number) >= 100:
        return f"{number:,.1f}"
    return f"{number:,.3f}".rstrip("0").rstrip(".")
