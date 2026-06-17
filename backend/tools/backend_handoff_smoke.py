from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}
DEFAULT_RUN_TIMEOUT_SECONDS = 900.0


@dataclass(frozen=True)
class HttpResult:
    status: int
    body: str
    payload: Any | None


class SmokeFailure(RuntimeError):
    pass


def _headers(user_id: str, json_body: bool = False) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "X-EDIM-User-Id": user_id,
    }
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


def _request_json(method: str, url: str, *, user_id: str, payload: dict[str, Any] | None = None, timeout: float = 30.0) -> HttpResult:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = Request(url=url, method=method.upper(), data=data, headers=_headers(user_id, json_body=payload is not None))
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = None
            return HttpResult(status=int(resp.status), body=body, payload=parsed)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SmokeFailure(f"{method.upper()} {url} returned HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise SmokeFailure(f"{method.upper()} {url} failed: {exc}") from exc


def _request_text(method: str, url: str, *, user_id: str, timeout: float = 30.0) -> HttpResult:
    req = Request(url=url, method=method.upper(), headers=_headers(user_id))
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return HttpResult(status=int(resp.status), body=body, payload=None)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SmokeFailure(f"{method.upper()} {url} returned HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise SmokeFailure(f"{method.upper()} {url} failed: {exc}") from exc


def _request_binary(method: str, url: str, *, user_id: str, timeout: float = 30.0) -> bytes:
    req = Request(url=url, method=method.upper(), headers=_headers(user_id))
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SmokeFailure(f"{method.upper()} {url} returned HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise SmokeFailure(f"{method.upper()} {url} failed: {exc}") from exc


def _object(result: HttpResult, label: str) -> dict[str, Any]:
    if not isinstance(result.payload, dict):
        raise SmokeFailure(f"{label} did not return a JSON object.")
    return result.payload


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise SmokeFailure(f"{label} was not a JSON array.")
    return value


def _base_url(raw: str) -> str:
    cleaned = raw.strip().rstrip("/")
    if not cleaned:
        raise SmokeFailure("Base URL cannot be empty.")
    return cleaned


def _absolute_url(base_url: str, path_or_url: str) -> str:
    value = path_or_url.strip()
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if not value.startswith("/"):
        value = f"/{value}"
    return f"{base_url}{value}"


def _print_step(verbose: bool, message: str) -> None:
    if verbose:
        print(message, flush=True)


def _wait_for_health(base_url: str, *, user_id: str, timeout_seconds: float, verbose: bool) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            health = _object(_request_json("GET", f"{base_url}/health", user_id=user_id, timeout=5.0), "health")
            if health.get("ok") is True:
                return health
            last_error = f"unhealthy payload: {health}"
        except Exception as exc:  # pragma: no cover - diagnostic path for deployed services
            last_error = str(exc)
        _print_step(verbose, f"[wait] backend health not ready: {last_error}")
        time.sleep(0.5)
    raise SmokeFailure(f"Backend did not become healthy within {timeout_seconds:.0f}s. Last error: {last_error}")


def _poll_terminal(base_url: str, execution_id: str, *, user_id: str, timeout_seconds: float, poll_interval_seconds: float, verbose: bool) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_status: dict[str, Any] = {}
    last_error = ""
    while time.time() < deadline:
        try:
            status = _object(
                _request_json("GET", f"{base_url}/api/executions/{execution_id}/status", user_id=user_id, timeout=30.0),
                "run status",
            )
            last_status = status
            state = str(status.get("status") or "").strip().lower()
            _print_step(verbose, f"[poll] execution_id={execution_id} status={state} stage={status.get('stage', '')}")
            if state in TERMINAL_STATUSES:
                return status
        except Exception as exc:  # pragma: no cover - diagnostic path for deployed services
            last_error = str(exc)
        time.sleep(max(0.1, poll_interval_seconds))
    detail = json.dumps(last_status, sort_keys=True) if last_status else "no status payload"
    if last_error:
        detail = f"{detail}; last error: {last_error}"
    raise SmokeFailure(
        f"Run execution {execution_id} did not reach a terminal status within {timeout_seconds:.0f}s: {detail}. "
        f"{_timeout_guidance(last_status)}"
    )


def _timeout_guidance(last_status: dict[str, Any]) -> str:
    state = str(last_status.get("status") or "").strip().lower()
    stage = str(last_status.get("stage") or "").strip().lower()
    if state == "running" and stage == "solve_energy":
        return (
            "The backend reached the real energy solver and was still progressing when the smoke wrapper timed out. "
            "This is usually a smoke-test timeout, not a failed run. Re-run with "
            f"--timeout-seconds {int(DEFAULT_RUN_TIMEOUT_SECONDS)} or higher, or inspect the execution status endpoint."
        )
    if state in {"queued", "running"}:
        return (
            "The run was still active when polling stopped. Increase --timeout-seconds if the backend is healthy "
            "and execution events show continued progress."
        )
    return "Check the backend logs and execution events for the last emitted runtime stage."


def _run_request(project_id: str, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "run_name": str(args.run_name),
        "model_architecture_id": str(args.model_architecture_id),
        "energy_model_engine": str(args.energy_model_engine),
        "scenario": {
            "energy_scenario_key": str(args.energy_scenario_key),
            "target_scenario_id": str(args.mrio_scenario_id),
            "target_year": int(args.target_year),
        },
        "run_profile": str(args.run_profile),
        "levers": {
            "demand_multiplier": float(args.demand_multiplier),
            "renewables_capex_multiplier": float(args.renewables_capex_multiplier),
            "fossil_fuel_price_multiplier": float(args.fossil_fuel_price_multiplier),
            "carbon_price_usd_per_tco2": float(args.carbon_price_usd_per_tco2),
        },
    }


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    base_url = _base_url(args.base_url)
    user_id = str(args.user_id).strip()
    if not user_id:
        raise SmokeFailure("User id cannot be empty.")

    _print_step(args.verbose, f"[check] backend={base_url} user={user_id}")
    _wait_for_health(base_url, user_id=user_id, timeout_seconds=float(args.startup_timeout_seconds), verbose=bool(args.verbose))

    session = _object(_request_json("GET", f"{base_url}/api/session", user_id=user_id), "session")
    session_user = session.get("user") if isinstance(session.get("user"), dict) else {}
    if str(session_user.get("user_id") or "") != user_id:
        raise SmokeFailure(f"/api/session resolved user_id={session_user.get('user_id')!r}, expected {user_id!r}.")
    _print_step(args.verbose, "[ok] session resolved requested user")

    system_manifest = _object(_request_json("GET", f"{base_url}/api/system/manifest", user_id=user_id), "system manifest")
    if system_manifest.get("schema_version") != "edim_system_manifest":
        raise SmokeFailure("/api/system/manifest did not return edim_system_manifest.")
    if not bool(system_manifest.get("ok", False)):
        raise SmokeFailure(f"/api/system/manifest reported not ok: {system_manifest.get('diagnostics')}")
    contracts = system_manifest.get("contracts") if isinstance(system_manifest.get("contracts"), dict) else {}
    for contract_key, expected_version in {
        "model_run_bundle": "model_run_bundle_v1",
        "runtime_event": "runtime_event_v1",
        "execution_queue_message": "execution_queue_message",
        "execution_retry_policy": "execution_retry_policy",
        "execution_attempt": "execution_attempt",
        "dataset_staging": "dataset_staging_v1",
    }.items():
        if contracts.get(contract_key) != expected_version:
            raise SmokeFailure(
                f"/api/system/manifest contracts.{contract_key}={contracts.get(contract_key)!r}; "
                f"expected {expected_version!r}."
            )
    _print_step(args.verbose, "[ok] system manifest endpoint returned expected contract identifiers")

    project_payload = {
        "title": str(args.project_title),
        "geography": str(args.project_geography),
        "project_type": "energy" if str(args.model_architecture_id) == "energy-only" else "energy-development",
        "model_architecture_id": str(args.model_architecture_id),
        "scenario_label": "Backend handoff smoke",
        "notes": "Created by backend_handoff_smoke.py to validate the platform/model runtime boundary.",
    }
    project_response = _object(_request_json("POST", f"{base_url}/api/projects", user_id=user_id, payload=project_payload), "project create")
    project = project_response.get("project") if isinstance(project_response.get("project"), dict) else {}
    project_id = str(project.get("project_id") or "").strip()
    if not project_id:
        raise SmokeFailure("Project create response did not include project.project_id.")
    _print_step(args.verbose, f"[ok] project created project_id={project_id}")

    datasets_response = _object(_request_json("GET", f"{base_url}/api/input-datasets", user_id=user_id), "dataset catalog")
    datasets = _list(datasets_response.get("datasets"), "input dataset catalog")
    if not datasets:
        raise SmokeFailure("/api/input-datasets returned no datasets.")
    missing_required = [
        str(row.get("id") or "")
        for row in datasets
        if isinstance(row, dict) and bool(row.get("required")) and not bool(row.get("exists"))
    ]
    if missing_required:
        raise SmokeFailure(f"Required input datasets are missing: {', '.join(missing_required)}")
    _print_step(args.verbose, f"[ok] dataset catalog returned {len(datasets)} datasets")

    runtimes_response = _object(_request_json("GET", f"{base_url}/api/model-runtimes", user_id=user_id), "model runtime catalog")
    runtime_mode = str(runtimes_response.get("runtime_mode") or "")
    artifact_handoff_mode = str(runtimes_response.get("artifact_handoff_mode") or "")
    dataset_staging_mode = str(runtimes_response.get("dataset_staging_mode") or "")
    execution_retry_policy = runtimes_response.get("execution_retry_policy") if isinstance(runtimes_response.get("execution_retry_policy"), dict) else {}
    runtimes = _list(runtimes_response.get("runtimes"), "model runtime catalog runtimes")
    if not runtimes:
        raise SmokeFailure("/api/model-runtimes returned no runtimes.")
    if artifact_handoff_mode not in {"shared_filesystem", "worker_staged_upload", "runtime_direct_upload"}:
        raise SmokeFailure(f"/api/model-runtimes returned unsupported artifact_handoff_mode={artifact_handoff_mode!r}.")
    if dataset_staging_mode not in {"reference", "copy_to_run", "object_reference"}:
        raise SmokeFailure(f"/api/model-runtimes returned unsupported dataset_staging_mode={dataset_staging_mode!r}.")
    if execution_retry_policy.get("schema_version") != "execution_retry_policy":
        raise SmokeFailure("/api/model-runtimes did not include execution_retry_policy.")
    if runtime_mode != "subprocess":
        raise SmokeFailure(
            f"Backend runtime_mode is {runtime_mode!r}; expected 'subprocess' for the packaged model contract."
        )
    _print_step(args.verbose, f"[ok] runtime catalog mode={runtime_mode} artifact_handoff={artifact_handoff_mode} dataset_staging={dataset_staging_mode}")

    env_query = urlencode(
        {
            "energy_scenario_key": args.energy_scenario_key,
            "mrio_scenario_id": args.mrio_scenario_id,
            "target_year": int(args.target_year),
            "run_profile": args.run_profile,
            "project_id": project_id,
            "strict_validation": "true" if args.strict_validation else "false",
            "allow_placeholder_data": "true" if args.allow_placeholder_data else "false",
        }
    )
    environment = _object(_request_json("GET", f"{base_url}/api/environment-setup?{env_query}", user_id=user_id), "environment setup")
    if not environment.get("ok"):
        raise SmokeFailure(f"/api/environment-setup is not ready: {json.dumps(environment.get('counts', {}), sort_keys=True)}")
    _print_step(args.verbose, f"[ok] environment setup ready counts={environment.get('counts', {})}")

    request_payload = _run_request(project_id, args)
    draft_response = _object(
        _request_json("POST", f"{base_url}/api/projects/{project_id}/runs", user_id=user_id, payload=request_payload, timeout=30.0),
        "run draft create",
    )
    draft = draft_response.get("run") if isinstance(draft_response.get("run"), dict) else {}
    run_id = str(draft.get("run_id") or "").strip()
    if not run_id:
        raise SmokeFailure("Run draft response did not include run.run_id.")
    _print_step(args.verbose, f"[ok] run draft created run_id={run_id}")

    submit_response = _object(
        _request_json("POST", f"{base_url}/api/projects/{project_id}/runs/{run_id}/submit", user_id=user_id, timeout=30.0),
        "run submit",
    )
    run_execution = submit_response.get("run") if isinstance(submit_response.get("run"), dict) else {}
    execution_id = str(run_execution.get("execution_id") or "").strip()
    if not execution_id:
        raise SmokeFailure("Run submit response did not include run.execution_id.")
    _print_step(args.verbose, f"[ok] run submitted execution_id={execution_id}")

    final_status = _poll_terminal(
        base_url,
        execution_id,
        user_id=user_id,
        timeout_seconds=float(args.timeout_seconds),
        poll_interval_seconds=float(args.poll_interval_seconds),
        verbose=bool(args.verbose),
    )
    if str(final_status.get("status") or "").lower() != "succeeded":
        raise SmokeFailure(f"Run did not succeed: {json.dumps(final_status, sort_keys=True)}")
    final_run_id = str(final_status.get("run_id") or run_id).strip()
    if final_run_id != run_id:
        _print_step(args.verbose, f"[note] submitted draft run_id={run_id}; completed run_id={final_run_id}")
        run_id = final_run_id
    _print_step(args.verbose, f"[ok] run succeeded run_id={run_id}")

    project_run_response = _object(
        _request_json("GET", f"{base_url}/api/projects/{project_id}/runs/{run_id}/diagnostics", user_id=user_id),
        "project run diagnostics",
    )
    project_run = project_run_response.get("run") if isinstance(project_run_response.get("run"), dict) else {}
    if str(project_run.get("status") or "").lower() != "succeeded":
        raise SmokeFailure(f"Project run record was not reconciled to succeeded: {project_run}")
    execution_attempts = _list(project_run.get("execution_attempts"), "project run execution attempts")
    if not execution_attempts:
        raise SmokeFailure("Project run record did not include execution attempts.")
    latest_attempt = execution_attempts[-1] if isinstance(execution_attempts[-1], dict) else {}
    if latest_attempt.get("schema_version") != "execution_attempt" or latest_attempt.get("status") != "succeeded":
        raise SmokeFailure(f"Project run latest execution attempt was not succeeded: {latest_attempt}")
    if not str(project_run.get("worker_id") or "").startswith("local-thread:"):
        raise SmokeFailure("Project run record did not include local worker identity.")
    _print_step(args.verbose, "[ok] project run record reconciled to succeeded with execution attempt metadata")

    events_response = _object(_request_json("GET", f"{base_url}/api/executions/{execution_id}/events", user_id=user_id), "run events")
    events = _list(events_response.get("events"), "run events")
    if not events:
        raise SmokeFailure("Run events endpoint returned no events.")
    _print_step(args.verbose, f"[ok] run events returned {len(events)} events")

    artifacts_response = _object(_request_json("GET", f"{base_url}/api/runs/{run_id}/artifacts", user_id=user_id), "run artifact list")
    artifacts = _list(artifacts_response.get("artifacts"), "run artifacts")
    artifact_ids = {str(row.get("artifact_id") or "") for row in artifacts if isinstance(row, dict)}
    required_artifacts = {"summary_json", "integrated_results_json", "results_csv"}
    missing_artifacts = sorted(required_artifacts - artifact_ids)
    if missing_artifacts:
        raise SmokeFailure(f"Run artifact catalog is missing required artifacts: {', '.join(missing_artifacts)}")
    _print_step(args.verbose, f"[ok] artifact catalog returned {len(artifacts)} artifacts")

    integrated = _object(_request_json("GET", f"{base_url}/api/runs/{run_id}/integrated", user_id=user_id), "integrated results")
    if not integrated:
        raise SmokeFailure("Integrated results endpoint returned an empty payload.")
    _print_step(args.verbose, "[ok] integrated results endpoint returned JSON")

    summary_result = _request_json("GET", f"{base_url}/api/runs/{run_id}/artifacts/summary_json", user_id=user_id)
    summary = _object(summary_result, "summary_json artifact")
    if str(summary.get("run_id") or "") != run_id:
        raise SmokeFailure("Downloaded summary_json did not match the completed run_id.")
    publication = summary.get("artifact_publication") if isinstance(summary.get("artifact_publication"), dict) else {}
    if publication.get("schema_version") != "runtime_artifact_publication_v1":
        raise SmokeFailure("summary_json did not include runtime_artifact_publication_v1 diagnostics.")
    if str(publication.get("handoff_mode") or "") != artifact_handoff_mode:
        raise SmokeFailure("summary_json artifact_publication did not match /api/model-runtimes artifact_handoff_mode.")
    _print_step(args.verbose, "[ok] summary_json artifact downloaded by artifact id with publication diagnostics")

    integrated_artifact = _object(
        _request_json("GET", f"{base_url}/api/runs/{run_id}/artifacts/integrated_results_json", user_id=user_id),
        "integrated_results_json artifact",
    )
    if str(integrated_artifact.get("run_id") or "") != run_id:
        raise SmokeFailure("Downloaded integrated_results_json did not match the completed run_id.")
    dataset_manifest_artifact = _object(
        _request_json("GET", f"{base_url}/api/runs/{run_id}/artifacts/dataset_manifest_json", user_id=user_id),
        "dataset_manifest_json artifact",
    )
    dataset_staging = dataset_manifest_artifact.get("dataset_staging") if isinstance(dataset_manifest_artifact.get("dataset_staging"), dict) else {}
    if dataset_staging.get("schema_version") != "dataset_staging_v1":
        raise SmokeFailure("Downloaded dataset_manifest_json did not include dataset_staging_v1 metadata.")
    if str(dataset_staging.get("mode") or "") != dataset_staging_mode:
        raise SmokeFailure("dataset_manifest_json staging mode did not match /api/model-runtimes dataset_staging_mode.")
    request_bundle_artifact = _object(
        _request_json("GET", f"{base_url}/api/runs/{run_id}/artifacts/request_bundle_json", user_id=user_id),
        "request_bundle_json artifact",
    )
    queue_message = request_bundle_artifact.get("queue_message") if isinstance(request_bundle_artifact.get("queue_message"), dict) else {}
    if queue_message.get("schema_version") != "execution_queue_message":
        raise SmokeFailure("request_bundle_json did not include execution_queue_message queue_message.")
    if str(queue_message.get("execution_id") or "") != execution_id or str(queue_message.get("run_id") or "") != run_id:
        raise SmokeFailure("request_bundle_json queue_message did not match submitted execution/run ids.")
    queue_retry_policy = queue_message.get("retry_policy") if isinstance(queue_message.get("retry_policy"), dict) else {}
    if queue_retry_policy.get("schema_version") != "execution_retry_policy":
        raise SmokeFailure("request_bundle_json queue_message did not include execution_retry_policy.")
    csv_result = _request_text("GET", f"{base_url}/api/runs/{run_id}/artifacts/results_csv", user_id=user_id)
    if "variable" not in csv_result.body:
        raise SmokeFailure("Downloaded results_csv did not look like a CSV results artifact.")
    _print_step(args.verbose, "[ok] integrated_results_json, dataset_manifest_json, request_bundle_json, and results_csv artifacts downloaded")

    report_response = _object(
        _request_json(
            "POST",
            f"{base_url}/api/projects/{project_id}/reports",
            user_id=user_id,
            payload={"run_ids": [run_id], "report_type": "backend_handoff_smoke", "options": {"source": "backend_handoff_smoke.py"}},
            timeout=60.0,
        ),
        "project report",
    )
    report = report_response.get("report") if isinstance(report_response.get("report"), dict) else {}
    report_id = str(report.get("report_id") or "").strip()
    report_download_url = str(report.get("download_url") or "").strip()
    if not report_id or not report_download_url:
        raise SmokeFailure("Project report response did not include report_id and download_url.")
    report_download = _request_text("GET", _absolute_url(base_url, report_download_url), user_id=user_id, timeout=60.0)
    if "EDIM" not in report_download.body:
        raise SmokeFailure("Downloaded project report did not contain the expected EDIM report content.")
    report_data_url = str(report.get("source_data_url") or "").strip()
    if not report_data_url:
        raise SmokeFailure("Project report response did not include source_data_url.")
    report_data = _object(
        _request_json("GET", _absolute_url(base_url, report_data_url), user_id=user_id, timeout=60.0),
        "project report source data",
    )
    if report_data.get("schema_version") != "edim_project_report_source_v1":
        raise SmokeFailure("Project report source data did not use the expected schema.")
    _print_step(args.verbose, f"[ok] project report and source data downloaded report_id={report_id}")

    export_response = _object(_request_json("POST", f"{base_url}/api/runs/{run_id}/export", user_id=user_id, timeout=60.0), "single run export")
    export = export_response.get("export") if isinstance(export_response.get("export"), dict) else {}
    export_id = str(export.get("export_id") or "").strip()
    export_download_url = str(export.get("download_url") or "").strip()
    if not export_id or not export_download_url:
        raise SmokeFailure("Run export response did not include export_id and download_url.")
    export_download = _request_binary("GET", _absolute_url(base_url, export_download_url), user_id=user_id, timeout=60.0)
    if not export_download.startswith(b"PK"):
        raise SmokeFailure("Downloaded run export did not look like a ZIP bundle.")
    _print_step(args.verbose, f"[ok] run export created and downloaded export_id={export_id}")

    project_export_response = _object(
        _request_json(
            "POST",
            f"{base_url}/api/projects/{project_id}/exports",
            user_id=user_id,
            payload={"run_ids": [run_id], "include_reports": False},
            timeout=60.0,
        ),
        "project export",
    )
    project_export = project_export_response.get("export") if isinstance(project_export_response.get("export"), dict) else {}
    project_export_id = str(project_export.get("export_id") or "").strip()
    project_export_download_url = str(project_export.get("download_url") or "").strip()
    if not project_export_id or not project_export_download_url:
        raise SmokeFailure("Project export response did not include export_id and download_url.")
    project_export_download = _request_binary("GET", _absolute_url(base_url, project_export_download_url), user_id=user_id, timeout=60.0)
    if not project_export_download.startswith(b"PK"):
        raise SmokeFailure("Downloaded project export did not look like a ZIP bundle.")
    _print_step(args.verbose, f"[ok] project export created and downloaded export_id={project_export_id}")

    cleanup = {"status": "kept", "project_id": project_id}
    if not bool(args.keep_project):
        _request_json("DELETE", f"{base_url}/api/projects/{project_id}/runs/{run_id}", user_id=user_id, timeout=30.0)
        _request_json("DELETE", f"{base_url}/api/projects/{project_id}", user_id=user_id, timeout=30.0)
        cleanup = {"status": "deleted", "project_id": project_id, "run_id": run_id}
        _print_step(args.verbose, f"[ok] temporary smoke project deleted project_id={project_id}")

    return {
        "ok": True,
        "base_url": base_url,
        "user_id": user_id,
        "runtime_mode": runtime_mode,
        "system_manifest": system_manifest.get("schema_version"),
        "artifact_handoff_mode": artifact_handoff_mode,
        "artifact_publication_status": publication.get("status"),
        "dataset_staging_mode": dataset_staging_mode,
        "dataset_count": dataset_staging.get("dataset_count"),
        "queue_message_contract": queue_message.get("schema_version"),
        "execution_retry_policy_contract": execution_retry_policy.get("schema_version"),
        "execution_attempt_count": len(execution_attempts),
        "project_id": project_id,
        "run_id": run_id,
        "execution_id": execution_id,
        "status": final_status.get("status"),
        "event_count": len(events),
        "artifact_count": len(artifacts),
        "artifacts": sorted(artifact_ids),
        "csv_bytes": len(csv_result.body.encode("utf-8")),
        "report_id": report_id,
        "report_download_bytes": len(report_download.body.encode("utf-8")),
        "report_source_schema_version": report_data.get("schema_version"),
        "export_id": export_id,
        "export_download_bytes": len(export_download),
        "project_export_id": project_export_id,
        "project_export_download_bytes": len(project_export_download),
        "cleanup": cleanup,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a deployment-oriented EDIM backend handoff smoke test against an already-running backend. "
            "The backend should use the manifest-defined subprocess model runtime."
        )
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL.")
    parser.add_argument("--user-id", default="undp_analyst", help="Test user id to send through X-EDIM-User-Id.")
    parser.add_argument("--project-title", default="Backend handoff smoke", help="Title for the temporary smoke-test project.")
    parser.add_argument("--project-geography", default="South Africa", help="Geography label for the temporary smoke-test project.")
    parser.add_argument("--run-name", default="Backend handoff smoke run", help="Run name for the temporary smoke-test run.")
    parser.add_argument("--keep-project", action="store_true", help="Keep the temporary smoke project for manual debugging.")
    parser.add_argument(
        "--model-architecture-id",
        default="energy-only",
        choices=("energy-only", "energy-development"),
        help=(
            "Model architecture to execute. The default uses the lightweight energy-only smoke path; "
            "use energy-development for the full bridge/MRIO integration smoke."
        ),
    )
    parser.add_argument("--energy-model-engine", default="calliope", choices=("calliope",))
    parser.add_argument(
        "--energy-scenario-key",
        default="new_links",
        help="Energy scenario key. Default is the transmission-only new_links scenario.",
    )
    parser.add_argument("--mrio-scenario-id", default="S2")
    parser.add_argument("--target-year", type=int, default=2030)
    parser.add_argument("--run-profile", default="dev", choices=("dev", "analysis", "full"))
    parser.add_argument("--strict-validation", action="store_true")
    parser.add_argument("--allow-placeholder-data", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--demand-multiplier", type=float, default=1.0)
    parser.add_argument("--renewables-capex-multiplier", type=float, default=1.0)
    parser.add_argument("--fossil-fuel-price-multiplier", type=float, default=1.0)
    parser.add_argument("--carbon-price-usd-per-tco2", type=float, default=0.0)
    parser.add_argument("--startup-timeout-seconds", type=float, default=30.0, help="Timeout waiting for backend /health.")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_RUN_TIMEOUT_SECONDS,
        help="Run completion timeout. The smoke test runs the real packaged model, so local Calliope solves can take several minutes.",
    )
    parser.add_argument("--poll-interval-seconds", type=float, default=1.0)
    parser.add_argument("--quiet", dest="verbose", action="store_false", help="Only print the final JSON summary or failure.")
    parser.set_defaults(verbose=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = run_smoke(args)
    except SmokeFailure as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        print(json.dumps({"ok": False, "error": f"Unexpected smoke failure: {exc}"}, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
