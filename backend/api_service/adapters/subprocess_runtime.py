from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

from ..runtime import (
    ArtifactRegistry,
    ModelExecutionContext,
    ModelExecutionRequest,
    ModelExecutionResult,
    ModelRuntimeManifest,
    RUNTIME_EVENT_SCHEMA_VERSION,
    RuntimeEventLog,
    parse_runtime_event_lines,
)
from ..settings import Settings


class SubprocessModelRuntime:
    """Manifest-driven adapter for executable model packages.

    The API layer should not import Calliope/MRIO code directly. It writes a
    `model_run_bundle_v1`, launches the runtime command from the manifest, and
    consumes `runtime_event_v1` JSONL from stdout.
    """

    def __init__(self, settings: Settings, manifest: ModelRuntimeManifest):
        self._settings = settings
        self._manifest = manifest

    def _command(self, execution_context: ModelExecutionContext) -> List[str]:
        base = list(self._manifest.entrypoint)
        return [*self._normalize_python_command(base), "--bundle", str(execution_context.request_bundle_path)]

    def _preflight_command(self, execution_context: ModelExecutionContext) -> List[str]:
        base = list(self._manifest.preflight_entrypoint or self._manifest.entrypoint)
        if base and base[-1] == "run":
            base[-1] = "preflight"
        return [*self._normalize_python_command(base), "--bundle", str(execution_context.request_bundle_path)]

    def _normalize_python_command(self, base: List[str]) -> List[str]:
        if base and base[0] in {"python", "python3"}:
            base[0] = sys.executable
        return base

    def _cwd(self) -> Path:
        manifest_path = self._manifest.manifest_path
        if manifest_path is not None:
            # model_runtime/edim_model/model_manifest.json -> repo root
            try:
                return manifest_path.resolve().parents[2]
            except IndexError:
                pass
        return Path(__file__).resolve().parents[3]

    def _env(self) -> Dict[str, str]:
        cwd = self._cwd()
        safe_names = {
            "HOME",
            "LANG",
            "LC_ALL",
            "PATH",
            "PYTHONIOENCODING",
            "SSL_CERT_FILE",
            "REQUESTS_CA_BUNDLE",
            "TMPDIR",
            "TEMP",
            "TMP",
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
        }
        runtime_cfg = self._settings.runtime_config if isinstance(self._settings.runtime_config, dict) else {}
        extra_names = ((runtime_cfg.get("model_runtime") or {}).get("safe_env") or []) if isinstance(runtime_cfg.get("model_runtime"), dict) else []
        for name in extra_names:
            text = str(name or "").strip()
            if text and not self._looks_like_secret_env_name(text):
                safe_names.add(text)
        env = {name: os.environ[name] for name in sorted(safe_names) if name in os.environ}
        python_paths = [str(cwd)]
        packaged_runtime_path = cwd / "model_runtime"
        if packaged_runtime_path.exists():
            python_paths.append(str(packaged_runtime_path))
        existing = env.get("PYTHONPATH", "")
        if existing:
            python_paths.append(existing)
        env["PYTHONPATH"] = os.pathsep.join(python_paths)
        env["PYTHONUNBUFFERED"] = "1"
        return env

    @staticmethod
    def _looks_like_secret_env_name(name: str) -> bool:
        upper = str(name or "").upper()
        secret_markers = (
            "API_KEY",
            "APIKEY",
            "ACCESS_KEY",
            "PRIVATE_KEY",
            "CONNECTION_STRING",
            "CREDENTIAL",
            "PASSWORD",
            "SECRET",
            "TOKEN",
        )
        return any(marker in upper for marker in secret_markers)

    def _timeout_seconds(self) -> float:
        try:
            return max(0.0, float((self._manifest.resource_requirements or {}).get("timeout_seconds") or 0.0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _terminate_process(proc: subprocess.Popen, *, kill_after_seconds: float = 5.0) -> None:
        if proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=kill_after_seconds)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=kill_after_seconds)
            except subprocess.TimeoutExpired:
                # The caller will raise the timeout/cancel error; avoid masking
                # that contract with a cleanup failure from a stuck child.
                pass

    def execute(
        self,
        execution_request: ModelExecutionRequest,
        execution_context: ModelExecutionContext,
        *,
        progress_callback: Callable[[str, float, str], None] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> ModelExecutionResult:
        """Execute a black-box runtime and translate stdout events to API state."""
        event_log_path = execution_context.event_log_path or (execution_context.run_dir / "logs" / "runtime_events.jsonl")
        event_log = RuntimeEventLog(event_log_path)
        command = self._command(execution_context)
        start = time.time()
        proc = subprocess.Popen(
            command,
            cwd=str(self._cwd()),
            env=self._env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        run_id = ""
        summary: dict | None = None
        warnings: list[str] = []
        stderr_lines: list[str] = []
        timeout_seconds = self._timeout_seconds()

        line_queue: queue.Queue[tuple[str, str]] = queue.Queue()

        def _read_stream(stream_name: str, stream) -> None:
            if stream is None:
                return
            for stream_line in stream:
                line_queue.put((stream_name, stream_line))

        def _handle_stdout_line(line: str) -> None:
            nonlocal run_id, summary
            for event in parse_runtime_event_lines([line]):
                event_log.append(event)
                event_type = str(event.get("type", ""))
                stage = str(event.get("stage", ""))
                message = str(event.get("message", ""))
                progress = event.get("progress")
                if event_type in {"progress", "stage_started", "stage_completed"} and progress is not None:
                    if progress_callback:
                        progress_callback(stage or event_type, float(progress), message or stage or event_type)
                elif event_type == "result":
                    run_id = str(event.get("run_id", "") or "")
                    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                    summary_payload = payload.get("summary") if isinstance(payload, dict) else None
                    if isinstance(summary_payload, dict):
                        summary = summary_payload
                elif event_type == "warning":
                    if message:
                        warnings.append(message)
                elif event_type == "error":
                    if message:
                        warnings.append(message)

        def _handle_stderr_line(line: str) -> None:
            text = line.rstrip("\n")
            if not text:
                return
            stderr_lines.append(text)
            event_log.append(
                {
                    "schema_version": RUNTIME_EVENT_SCHEMA_VERSION,
                    "type": "stderr",
                    "level": "error",
                    "message": text,
                }
            )

        stdout_reader = threading.Thread(target=_read_stream, args=("stdout", proc.stdout), name="edim-model-runtime-stdout", daemon=True)
        stderr_reader = threading.Thread(target=_read_stream, args=("stderr", proc.stderr), name="edim-model-runtime-stderr", daemon=True)
        stdout_reader.start()
        stderr_reader.start()
        while True:
            if cancel_requested and cancel_requested():
                self._terminate_process(proc)
                raise RuntimeError("Model runtime subprocess cancelled by backend request.")
            if timeout_seconds and (time.time() - start) > timeout_seconds:
                self._terminate_process(proc)
                stderr_text = "\n".join(line for line in stderr_lines if line).strip()
                detail = f"Model runtime subprocess exceeded timeout of {timeout_seconds:.0f}s."
                if stderr_text:
                    detail = f"{detail}\n{stderr_text}"
                raise RuntimeError(detail)

            try:
                stream_name, line = line_queue.get(timeout=0.1)
            except queue.Empty:
                if proc.poll() is not None:
                    stdout_reader.join(timeout=1)
                    stderr_reader.join(timeout=1)
                    while True:
                        try:
                            stream_name, line = line_queue.get_nowait()
                        except queue.Empty:
                            break
                        if stream_name == "stderr":
                            _handle_stderr_line(line)
                        else:
                            _handle_stdout_line(line)
                    break
                continue
            if line:
                if stream_name == "stderr":
                    _handle_stderr_line(line)
                else:
                    _handle_stdout_line(line)
                continue

        return_code = proc.wait()
        if return_code != 0:
            stderr_text = "\n".join(line for line in stderr_lines if line).strip()
            detail = stderr_text or f"Model runtime subprocess exited with code {return_code}."
            raise RuntimeError(detail)

        if summary is None or not run_id:
            raise RuntimeError("Model runtime completed without emitting a result event containing run_id and summary.")

        self._publish_event_log(run_id, event_log_path, summary)

        elapsed = time.time() - start
        if progress_callback:
            progress_callback("complete", 1.0, f"Model runtime completed in {elapsed:.1f}s")
        return ModelExecutionResult(run_id=run_id, summary=summary, warnings=warnings, declared_artifacts=[])

    def _publish_event_log(self, run_id: str, source_path: Path, summary: dict) -> None:
        # Runtime events are both progress logs and a declared downloadable
        # artifact. Register them after completion so artifact catalogs remain
        # complete even when the runtime itself did not know about API storage.
        run_dir = self._settings.runs_dir / run_id
        if not source_path.exists() or not run_dir.exists():
            return
        registry = ArtifactRegistry(run_id, run_dir, self._settings.runtime_config)
        target = registry.path_for("runtime_events_jsonl")
        if source_path.resolve() != target.resolve():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target)
        record = registry.register_existing("runtime_events_jsonl", path=target).to_dict()
        catalog = list(summary.get("artifact_catalog") or [])
        catalog = [row for row in catalog if row.get("artifact_id") != "runtime_events_jsonl"]
        catalog.append(record)
        catalog.sort(key=lambda row: str(row.get("artifact_id", "")))
        summary["artifact_catalog"] = catalog
        summary_path = registry.path_for("summary_json")
        if summary_path.exists():
            try:
                current = json.loads(summary_path.read_text(encoding="utf-8"))
                if isinstance(current, dict):
                    current["artifact_catalog"] = catalog
                    summary_path.write_text(json.dumps(current, indent=2, sort_keys=True), encoding="utf-8")
            except Exception:
                pass

    def preflight(self, execution_context: ModelExecutionContext) -> Dict[str, Any]:
        command = self._preflight_command(execution_context)
        proc = subprocess.run(
            command,
            cwd=str(self._cwd()),
            env=self._env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
            check=False,
        )
        events = list(parse_runtime_event_lines(proc.stdout.splitlines()))
        result_event = next((event for event in reversed(events) if event.get("type") == "result"), {})
        payload = result_event.get("payload") if isinstance(result_event.get("payload"), dict) else {}
        return {
            "ok": proc.returncode == 0,
            "return_code": proc.returncode,
            "message": result_event.get("message", "") or (proc.stderr.strip() if proc.returncode else "Preflight completed"),
            "events": events,
            "payload": payload,
        }
