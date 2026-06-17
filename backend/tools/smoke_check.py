from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class HttpResult:
    status: int
    body: str
    json_payload: Any | None


def _http_json(method: str, url: str, payload: dict | None = None, timeout: float = 20.0) -> HttpResult:
    data: bytes | None = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url=url, method=method.upper(), data=data, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = None
            return HttpResult(status=int(resp.status), body=raw, json_payload=parsed)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} -> HTTP {exc.code}: {raw}") from exc
    except URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc}") from exc


def _http_text(method: str, url: str, timeout: float = 20.0) -> HttpResult:
    req = Request(url=url, method=method.upper())
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return HttpResult(status=int(resp.status), body=raw, json_payload=None)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} -> HTTP {exc.code}: {raw}") from exc
    except URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc}") from exc


def _project_owned_submit(base_url: str, request_payload: dict[str, Any]) -> dict[str, Any]:
    project = _http_json(
        "POST",
        f"{base_url}/api/projects",
        payload={
            "title": "Local smoke project",
            "geography": "Africa",
            "scenario_label": "Local smoke",
            "notes": "Created by backend/tools/smoke_check.py.",
        },
    )
    if not isinstance(project.json_payload, dict) or not isinstance(project.json_payload.get("project"), dict):
        raise RuntimeError("Project create response was not a JSON object.")
    project_id = str(project.json_payload["project"].get("project_id") or "").strip()
    if not project_id:
        raise RuntimeError("Project create response did not include project_id.")
    payload = dict(request_payload)
    payload["project_id"] = project_id
    draft = _http_json("POST", f"{base_url}/api/projects/{project_id}/runs", payload=payload, timeout=30.0)
    if not isinstance(draft.json_payload, dict) or not isinstance(draft.json_payload.get("run"), dict):
        raise RuntimeError("Run draft response was not a JSON object.")
    run_id = str(draft.json_payload["run"].get("run_id") or "").strip()
    if not run_id:
        raise RuntimeError("Run draft response missing run_id.")
    submitted = _http_json("POST", f"{base_url}/api/projects/{project_id}/runs/{run_id}/submit", timeout=30.0)
    if not isinstance(submitted.json_payload, dict) or not isinstance(submitted.json_payload.get("run"), dict):
        raise RuntimeError("Run submit response was not a JSON object.")
    return submitted.json_payload["run"]


def _wait_for_health(base_url: str, timeout_seconds: float) -> None:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            res = _http_json("GET", f"{base_url}/health", timeout=3.0)
            if res.status == 200 and isinstance(res.json_payload, dict) and bool(res.json_payload.get("ok")):
                return
        except Exception as exc:  # pragma: no cover - best effort polling diagnostics
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"Backend did not become healthy in {timeout_seconds:.0f}s. Last error: {last_error}")


def _poll_run_terminal(base_url: str, execution_id: str, timeout_seconds: float) -> dict:
    deadline = time.time() + timeout_seconds
    last_payload: dict = {}
    last_error = ""
    while time.time() < deadline:
        try:
            res = _http_json("GET", f"{base_url}/api/executions/{execution_id}/status", timeout=60.0)
            if not isinstance(res.json_payload, dict):
                raise RuntimeError("Job status payload was not a JSON object.")
            last_payload = res.json_payload
            status = str(last_payload.get("status", "")).strip().lower()
            if status in {"succeeded", "failed", "cancelled"}:
                return last_payload
        except Exception as exc:
            # Solves can briefly block responses; keep polling within global timeout.
            last_error = str(exc)
        time.sleep(2.0)
    raise RuntimeError(
        f"Run execution {execution_id} did not reach terminal state in {timeout_seconds:.0f}s. "
        f"Last payload: {json.dumps(last_payload)}"
        + (f" Last poll error: {last_error}" if last_error else "")
    )


def run_smoke(base_url: str, run_model: bool, run_timeout: float, scenario_override: str) -> None:
    health = _http_json("GET", f"{base_url}/health")
    if health.status != 200:
        raise RuntimeError(f"/health expected 200, got {health.status}")

    ui = _http_text("GET", f"{base_url}/ui/")
    if ui.status != 200:
        raise RuntimeError(f"/ui/ expected 200, got {ui.status}")
    if "<div id=\"root\"></div>" not in ui.body:
        raise RuntimeError("Frontend root container not found in /ui/ response.")

    scenarios_res = _http_json("GET", f"{base_url}/api/scenarios")
    payload = scenarios_res.json_payload
    if not isinstance(payload, dict):
        raise RuntimeError("/api/scenarios returned unexpected payload.")
    scenarios = payload.get("energy_scenarios") or payload.get("scenarios") or []
    if not isinstance(scenarios, list):
        raise RuntimeError("/api/scenarios returned unexpected scenario catalog.")
    if not scenarios:
        raise RuntimeError("No scenarios returned by /api/scenarios.")
    scenario_key = scenario_override or str((scenarios[0] or {}).get("key", "")).strip()
    if not scenario_key:
        raise RuntimeError("Could not determine a scenario key for smoke run.")

    env_res = _http_json(
        "GET",
        f"{base_url}/api/environment-setup?energy_scenario_key={scenario_key}&mrio_scenario_id=S2&target_year=2030&run_profile=dev&allow_placeholder_data=true",
    )
    if not isinstance(env_res.json_payload, dict):
        raise RuntimeError("/api/environment-setup returned unexpected payload.")

    print(f"[ok] health, ui, scenarios, environment-setup for scenario={scenario_key}")

    if not run_model:
        print("[ok] skipped model execution (--run-model not set)")
        return

    run = _project_owned_submit(
        base_url,
        {
            "run_name": "Smoke run",
            "energy_model_engine": "calliope",
            "energy_scenario_key": scenario_key,
            "mrio_scenario_id": "S2",
            "target_year": 2030,
            "run_profile": "dev",
            "strict_validation": False,
            "allow_placeholder_data": True,
            "levers": {
                "demand_multiplier": 1.0,
                "renewables_capex_multiplier": 1.0,
                "fossil_fuel_price_multiplier": 1.0,
                "carbon_price_usd_per_tco2": 10.0,
            },
        },
    )
    execution_id = str(run.get("execution_id") or "").strip()
    if not execution_id:
        raise RuntimeError("Run submit response missing execution_id.")
    print(f"[ok] submitted execution_id={execution_id}")

    final_run = _poll_run_terminal(base_url=base_url, execution_id=execution_id, timeout_seconds=run_timeout)
    status = str(final_run.get("status", "")).strip().lower()
    if status != "succeeded":
        raise RuntimeError(f"Smoke model run ended with status={status}. Payload: {json.dumps(final_run)}")
    run_id = str(final_run.get("run_id") or ((final_run.get("artifacts") or {}).get("run_id", ""))).strip()
    if not run_id:
        raise RuntimeError(f"Succeeded run execution {execution_id} did not include run_id.")
    print(f"[ok] model run succeeded run_id={run_id}")

    summary = _http_json("GET", f"{base_url}/api/runs/{run_id}/summary")
    integrated = _http_json("GET", f"{base_url}/api/runs/{run_id}/integrated")
    if not isinstance(summary.json_payload, dict):
        raise RuntimeError("Run summary payload is invalid.")
    if not isinstance(integrated.json_payload, dict):
        raise RuntimeError("Integrated payload is invalid.")
    metrics = ((integrated.json_payload.get("integrated_overview") or {}).get("metrics") or [])
    if not isinstance(metrics, list) or not metrics:
        raise RuntimeError("Integrated payload metrics are missing.")
    _ = _http_text("GET", f"{base_url}/api/runs/{run_id}/artifacts/results_csv")
    print("[ok] summary, integrated, and csv download endpoints validated")


def main() -> int:
    parser = argparse.ArgumentParser(description="EDIM backend/frontend/model smoke checks.")
    parser.add_argument("--port", type=int, default=8010, help="Local port for temporary uvicorn server.")
    parser.add_argument("--base-url", type=str, default="", help="Target an already-running server (e.g. http://localhost:8000) instead of spawning a local uvicorn process.")
    parser.add_argument("--run-model", action="store_true", help="Execute one real dev-profile model run.")
    parser.add_argument("--run-timeout-seconds", type=float, default=900.0, help="Timeout for model run completion.")
    parser.add_argument("--startup-timeout-seconds", type=float, default=90.0, help="Timeout waiting for backend health.")
    parser.add_argument("--scenario", type=str, default="", help="Scenario key override for model run.")
    args = parser.parse_args()

    # When --base-url is provided, target the running server directly without
    # spawning a local uvicorn subprocess.
    external_base_url = str(args.base_url or "").strip().rstrip("/")
    if external_base_url:
        try:
            _wait_for_health(external_base_url, timeout_seconds=float(args.startup_timeout_seconds))
            run_smoke(
                base_url=external_base_url,
                run_model=bool(args.run_model),
                run_timeout=float(args.run_timeout_seconds),
                scenario_override=str(args.scenario or "").strip(),
            )
            print("[ok] smoke check completed")
            return 0
        except Exception as exc:
            print(f"[error] {exc}")
            return 1

    backend_dir = Path(__file__).resolve().parents[1]
    repo_root = backend_dir.parent
    python_bin = Path(sys.executable)
    base_url = f"http://127.0.0.1:{int(args.port)}"

    cmd = [
        str(python_bin),
        "-m",
        "uvicorn",
        "api_service.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(int(args.port)),
    ]
    env = os.environ.copy()
    python_path_parts = [str(repo_root), str(repo_root / "model_runtime")]
    if env.get("PYTHONPATH"):
        python_path_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(python_path_parts)

    proc = subprocess.Popen(
        cmd,
        cwd=str(backend_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_for_health(base_url, timeout_seconds=float(args.startup_timeout_seconds))
        run_smoke(
            base_url=base_url,
            run_model=bool(args.run_model),
            run_timeout=float(args.run_timeout_seconds),
            scenario_override=str(args.scenario or "").strip(),
        )
        print("[ok] smoke check completed")
        return 0
    except Exception as exc:
        print(f"[error] {exc}")
        return 1
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        if proc.stdout is not None:
            try:
                log_tail = proc.stdout.read()[-4000:]
            except Exception:
                log_tail = ""
            if log_tail.strip():
                print("--- uvicorn log tail ---")
                print(log_tail.strip())


if __name__ == "__main__":
    raise SystemExit(main())
