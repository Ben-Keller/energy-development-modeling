from __future__ import annotations

import argparse
import json
import sys
import traceback
from types import SimpleNamespace
from pathlib import Path
from typing import Any, Callable, Dict

from .local_runtime import REPO_ROOT, execute_bundle
from .modules import get_energy_model_module, model_module_catalog, module_scenario_catalog
from .modules.base import ModelModuleError
from .contracts import RuntimeEvent, runtime_settings_from_bundle


def _execution_id(bundle: Dict[str, Any]) -> str:
    return str(bundle.get("execution_id") or "")


def _emit(event_type: str, *, stage: str = "", progress: float | None = None, message: str = "", level: str = "info", run_id: str = "", execution_id: str = "", payload: Dict[str, Any] | None = None) -> None:
    print(
        RuntimeEvent(
            type=event_type,
            stage=stage,
            progress=progress,
            message=message,
            level=level,
            run_id=run_id,
            execution_id=execution_id,
            payload=payload or {},
        ).to_json_line(),
        flush=True,
    )


def _load_bundle(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Run bundle not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Run bundle is not valid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Run bundle must be a JSON object.")
    if data.get("schema_version") != "model_run_bundle_v1":
        raise RuntimeError("Unsupported run bundle schema_version; expected model_run_bundle_v1.")
    return data


def _progress_callback(execution_id: str) -> Callable[[str, float, str], None]:
    def _progress(stage: str, progress: float, message: str) -> None:
        _emit("progress", stage=stage, progress=float(progress), message=str(message), execution_id=execution_id)

    return _progress


def run(args: argparse.Namespace) -> int:
    bundle = _load_bundle(Path(args.bundle).expanduser().resolve())
    execution_id = _execution_id(bundle)
    _emit("stage_started", stage="runtime", progress=0.0, message="Model runtime process started", execution_id=execution_id)
    run_id, summary, warnings = execute_bundle(
        bundle,
        progress_callback=_progress_callback(execution_id),
    )
    for warning in warnings:
        _emit("warning", stage="runtime", message=str(warning), level="warning", run_id=run_id, execution_id=execution_id)
    _emit("result", stage="complete", progress=1.0, message="Model runtime completed", run_id=run_id, execution_id=execution_id, payload={"summary": summary})
    return 0


def preflight(args: argparse.Namespace) -> int:
    bundle = _load_bundle(Path(args.bundle).expanduser().resolve())
    settings = runtime_settings_from_bundle(bundle, REPO_ROOT)
    req = bundle.get("request") if isinstance(bundle.get("request"), dict) else {}
    engine = str(req.get("energy_model_engine") or "calliope").strip().lower()
    dataset_manifest = bundle.get("dataset_manifest") if isinstance(bundle.get("dataset_manifest"), dict) else {}
    datasets = dataset_manifest.get("datasets") if isinstance(dataset_manifest.get("datasets"), list) else []
    checks = []
    module_error = ""
    try:
        energy_module = get_energy_model_module(engine)
        checks.append(
            {
                "id": "energy_module",
                "path": energy_module.info.module_id,
                "required": True,
                "exists": energy_module.info.implementation_status == "ready",
                "staging_mode": "module_registry",
                "staging_status": energy_module.info.implementation_status,
                "has_storage_ref": False,
            }
        )
        if energy_module.info.implementation_status != "ready":
            module_error = f"Energy module '{engine}' is {energy_module.info.implementation_status}."
    except ModelModuleError as exc:
        module_error = str(exc)
        checks.append(
            {
                "id": "energy_module",
                "path": engine,
                "required": True,
                "exists": False,
                "staging_mode": "module_registry",
                "staging_status": "missing",
                "has_storage_ref": False,
            }
        )
    for dataset in datasets:
        if not isinstance(dataset, dict):
            continue
        path = Path(str(dataset.get("path", ""))).expanduser()
        required = bool(dataset.get("required", False))
        checks.append(
            {
                "id": dataset.get("id", ""),
                "path": str(path),
                "required": required,
                "exists": path.exists(),
                "staging_mode": dataset.get("staging_mode", ""),
                "staging_status": dataset.get("staging_status", ""),
                "has_storage_ref": isinstance(dataset.get("storage_ref"), dict),
            }
        )
    missing = [row for row in checks if row["required"] and not row["exists"]]
    status = "failed" if missing else "passed"
    message = f"Preflight {status}"
    if module_error:
        message = f"{message}: {module_error}"
    _emit(
        "result",
        stage="preflight",
        progress=1.0,
        message=message,
        execution_id=_execution_id(bundle),
        payload={
            "status": status,
            "checks": checks,
            "settings_config_dir": str(settings.config_dir),
            "model_modules": model_module_catalog(),
        },
    )
    return 2 if missing else 0


def catalog(args: argparse.Namespace) -> int:
    config_dir = Path(args.config_dir).expanduser().resolve() if args.config_dir else REPO_ROOT / "inputs"
    calliope_root = (
        Path(args.calliope_root).expanduser().resolve()
        if args.calliope_root
        else REPO_ROOT / "model_runtime" / "model_modules" / "calliope" / "Calliope-Africa-main"
    )
    manifest_path = Path(args.manifest).expanduser().resolve() if args.manifest else REPO_ROOT / "model_runtime" / "edim_model" / "model_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    settings = SimpleNamespace(config_dir=config_dir, calliope_root=calliope_root)
    architecture_path = Path(args.architecture_catalog).expanduser().resolve() if args.architecture_catalog else REPO_ROOT / "model_runtime" / "edim_model" / "architecture_catalog.json"
    architecture_catalog = json.loads(architecture_path.read_text(encoding="utf-8")) if architecture_path.exists() else {
        "schemaVersion": "edim_model_architecture_catalog",
        "defaultArchitectureId": (manifest.get("supported_model_architectures") or [""])[0],
        "architectures": [
            {"id": value, "label": str(value).replace("-", " ").title()}
            for value in (manifest.get("supported_model_architectures") or [])
        ],
    }
    print(
        json.dumps(
            {
                "schema_version": "edim_model_catalog",
                "scenario_catalog": module_scenario_catalog(settings=settings, manifest=manifest),
                "architecture_catalog": architecture_catalog,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="edim-model-runtime")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "preflight"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--bundle", required=True)
    catalog_cmd = sub.add_parser("catalog")
    catalog_cmd.add_argument("--config-dir", default="")
    catalog_cmd.add_argument("--calliope-root", default="")
    catalog_cmd.add_argument("--manifest", default="")
    catalog_cmd.add_argument("--architecture-catalog", default="")
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            return run(args)
        if args.command == "preflight":
            return preflight(args)
        if args.command == "catalog":
            return catalog(args)
        raise RuntimeError(f"Unknown command: {args.command}")
    except Exception as exc:
        _emit("error", stage="runtime", progress=1.0, message=str(exc), level="error", payload={"traceback": traceback.format_exc()})
        print(traceback.format_exc(), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
