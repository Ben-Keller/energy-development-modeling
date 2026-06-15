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


def _poll_job_terminal(base_url: str, job_id: str, timeout_seconds: float) -> dict:
    deadline = time.time() + timeout_seconds
    last_payload: dict = {}
    last_error = ""
    while time.time() < deadline:
        try:
            res = _http_json("GET", f"{base_url}/api/jobs/{job_id}", timeout=60.0)
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
        f"Job {job_id} did not reach terminal state in {timeout_seconds:.0f}s. "
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
    if not isinstance(payload, dict) or not isinstance(payload.get("scenarios"), list):
        raise RuntimeError("/api/scenarios returned unexpected payload.")
    scenarios = payload["scenarios"]
    if not scenarios:
        raise RuntimeError("No scenarios returned by /api/scenarios.")
    scenario_key = scenario_override or str((scenarios[0] or {}).get("key", "")).strip()
    if not scenario_key:
        raise RuntimeError("Could not determine a scenario key for smoke run.")

    env_res = _http_json(
        "GET",
        f"{base_url}/api/environment-setup?scenario={scenario_key}&run_profile=dev",
    )
    if not isinstance(env_res.json_payload, dict):
        raise RuntimeError("/api/environment-setup returned unexpected payload.")

    print(f"[ok] health, ui, scenarios, environment-setup for scenario={scenario_key}")

    if not run_model:
        print("[ok] skipped model execution (--run-model not set)")
        return

    submit_res = _http_json(
        "POST",
        f"{base_url}/api/jobs",
        payload={
            "scenario": scenario_key,
            "run_profile": "dev",
            "fast_dev_mode": True,
            "levers": {
                "demand_multiplier": 1.0,
                "renewables_capex_multiplier": 1.0,
                "fossil_fuel_price_multiplier": 1.0,
                "carbon_price_usd_per_tco2": 10.0,
            },
        },
        timeout=30.0,
    )
    if not isinstance(submit_res.json_payload, dict):
        raise RuntimeError("Job submit response was not a JSON object.")
    job = submit_res.json_payload.get("job") or {}
    job_id = str(job.get("job_id", "")).strip()
    if not job_id:
        raise RuntimeError("Job submit response missing job_id.")
    print(f"[ok] submitted job_id={job_id}")

    final_job = _poll_job_terminal(base_url=base_url, job_id=job_id, timeout_seconds=run_timeout)
    status = str(final_job.get("status", "")).strip().lower()
    if status != "succeeded":
        raise RuntimeError(f"Smoke model run ended with status={status}. Payload: {json.dumps(final_job)}")
    run_id = str(((final_job.get("artifacts") or {}).get("run_id", ""))).strip()
    if not run_id:
        raise RuntimeError(f"Succeeded job {job_id} did not include run_id in artifacts.")
    print(f"[ok] model run succeeded run_id={run_id}")

    summary = _http_json("GET", f"{base_url}/api/run/{run_id}/summary")
    integrated = _http_json("GET", f"{base_url}/api/run/{run_id}/integrated")
    if not isinstance(summary.json_payload, dict):
        raise RuntimeError("Run summary payload is invalid.")
    if not isinstance(integrated.json_payload, dict):
        raise RuntimeError("Integrated payload is invalid.")
    metrics = ((integrated.json_payload.get("integrated_overview") or {}).get("metrics") or [])
    if not isinstance(metrics, list) or not metrics:
        raise RuntimeError("Integrated payload metrics are missing.")
    _ = _http_text("GET", f"{base_url}/api/run/{run_id}/download/csv")
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
