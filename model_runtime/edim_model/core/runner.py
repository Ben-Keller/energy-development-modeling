from __future__ import annotations

"""Single-run execution orchestrator for the EDIM MVP backend."""

import csv
import fnmatch
import json
import logging
import os
import re
import shutil
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

import numpy as np
import pandas as pd
import yaml

from .integrated import (
    build_run_report_markdown,
    create_exchange_bundle_zip,
)
from .levers import load_lever_mappings
from .mario_runtime import (
    load_development_indicator_mapping,
    load_scenario_assumptions,
    mario_inputs_health,
    run_mario_io_runtime,
    write_exchange_schema_validation,
    write_runtime_log,
)
from .scenario_package import (
    build_mrio_direct_inputs,
    build_scenario_package,
    write_scenario_artifacts,
)
from ..modules import get_development_model_module
from ..contracts import ArtifactRegistry
from .scenarios import load_scenario_metadata, load_scenarios_from_overrides
from .schemas import RunRequest
from .settings import Settings

logger = logging.getLogger(__name__)
RUN_DIR_PATTERN = re.compile(r"^[a-f0-9]{8,32}$")
DEVELOPMENT_MODEL_DEFAULTS: Dict[str, Any] = {
    "mario": {
        "uncertainty_relative_bounds": {
            "jobs_direct": 0.12,
            "jobs_total": 0.12,
            "gva_total_musd": 0.12,
            "household_income_proxy_musd": 0.12,
        }
    },
    "mario_direct": {
        "structural_reallocation_bridge_scale": 0.25,
        "max_direct_to_bridge_ratio": 1.0,
    },
}


class RunCancelledError(RuntimeError):
    pass


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _write_text_atomic(path: Path, text: str) -> None:
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def _write_yaml(path: Path, data: dict) -> None:
    payload = yaml.safe_dump(data, sort_keys=False)
    _write_text_atomic(path, payload)


def _write_json(path: Path, payload: Any) -> None:
    _write_text_atomic(path, json_dumps(payload))


def _ensure_dirs(*paths: Path) -> None:
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)


def _exchange_dir(run_dir: Path, artifact_registry: ArtifactRegistry | None = None) -> Path:
    if artifact_registry is None:
        path = run_dir / "exchange"
    else:
        path = artifact_registry.path_for("exchange_metadata_json").parent
    _ensure_dirs(path)
    return path


@contextmanager
def _pushd(path: Path):
    prev = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


def _create_run_dir(runs_dir: Path, preferred_run_id: str | None = None) -> Tuple[str, Path]:
    _ensure_dirs(runs_dir)
    preferred = str(preferred_run_id or "").strip().lower()
    if preferred and RUN_DIR_PATTERN.fullmatch(preferred):
        run_dir = runs_dir / preferred
        try:
            run_dir.mkdir(parents=False, exist_ok=False)
            return preferred, run_dir
        except FileExistsError:
            if any(run_dir.iterdir()):
                raise RuntimeError(f"Requested run_id already exists and is not empty: {preferred}")
            return preferred, run_dir
    for _ in range(32):
        run_id = uuid.uuid4().hex
        run_dir = runs_dir / run_id
        try:
            run_dir.mkdir(parents=False, exist_ok=False)
            return run_id, run_dir
        except FileExistsError:
            continue
    raise RuntimeError("Failed to allocate a unique run_id after multiple attempts.")


def _iter_run_dirs(runs_dir: Path) -> List[Path]:
    if not runs_dir.exists():
        return []
    out: List[Path] = []
    for entry in runs_dir.iterdir():
        if entry.is_dir() and RUN_DIR_PATTERN.fullmatch(entry.name):
            out.append(entry)
    out.sort(key=lambda p: p.stat().st_mtime)
    return out


def _cleanup_old_runs(settings: Settings) -> None:
    run_dirs = _iter_run_dirs(settings.runs_dir)
    if not run_dirs:
        return

    now = time.time()
    to_delete: set[Path] = set()

    if settings.run_retention_days > 0:
        cutoff = now - (settings.run_retention_days * 24 * 60 * 60)
        for path in run_dirs:
            if path.stat().st_mtime < cutoff:
                to_delete.add(path)

    if settings.run_max_dirs > 0:
        remaining = [p for p in run_dirs if p not in to_delete]
        if len(remaining) > settings.run_max_dirs:
            overflow = len(remaining) - settings.run_max_dirs
            for path in remaining[:overflow]:
                to_delete.add(path)

    for path in sorted(to_delete):
        try:
            shutil.rmtree(path)
            logger.info("Deleted old run directory: %s", path)
        except Exception:
            logger.exception("Failed deleting old run directory: %s", path)


def _get_calliope_module():
    # Import lazily so the server can start even if Calliope isn't installed yet.
    import calliope  # type: ignore

    return calliope


def _patch_calliope_highs_warmstart() -> None:
    """
    Calliope 0.6.x forwards warmstart to Pyomo solve kwargs.
    Pyomo's HiGHS plugin rejects this kwarg, so remove it for HiGHS solvers.
    """
    try:
        from calliope.backend.pyomo import model as pyomo_model  # type: ignore
    except Exception:
        return

    solve_model = getattr(pyomo_model, "solve_model", None)
    if solve_model is None or getattr(solve_model, "_edim_highs_warmstart_patch", False):
        return

    def _strip_highs_incompatible_options(raw: Any) -> Tuple[Any, List[str]]:
        if not isinstance(raw, dict):
            return raw, []
        out = dict(raw)
        removed: List[str] = []
        disallowed = {
            "numericfocus",
            "method",
            "crossover",
            "barconvtol",
            "barhomogeneous",
            "mipfocus",
            "nodefiledir",
            "nodefilestart",
        }
        for key in list(out.keys()):
            key_norm = str(key).strip().lower()
            if key_norm in disallowed or key_norm.startswith("gurobi_"):
                removed.append(str(key))
                out.pop(key, None)
        return out, removed

    def _wrapped_solve_model(*args, **kwargs):
        solver = kwargs.get("solver")
        if solver is None and len(args) >= 2:
            solver = args[1]
        solver_normalized = solver.strip().lower() if isinstance(solver, str) else ""
        if solver_normalized in {"highs", "appsi_highs"}:
            kwargs.pop("warmstart", None)
            if "solver_options" in kwargs:
                cleaned, removed = _strip_highs_incompatible_options(kwargs.get("solver_options"))
                kwargs["solver_options"] = cleaned
                if removed:
                    logger.info("Dropped %d HiGHS-incompatible solver options: %s", len(removed), ", ".join(sorted(removed)))
            elif len(args) >= 4:
                args_list = list(args)
                cleaned, removed = _strip_highs_incompatible_options(args_list[3])
                args_list[3] = cleaned
                args = tuple(args_list)
                if removed:
                    logger.info("Dropped %d HiGHS-incompatible solver options: %s", len(removed), ", ".join(sorted(removed)))

        result = solve_model(*args, **kwargs)

        # appsi_highs can return an optimizer object without `.name`.
        # Calliope accesses opt.name unconditionally in some code paths.
        if solver_normalized == "appsi_highs":
            try:
                _, opt = result
                if opt is not None and not hasattr(opt, "name"):
                    setattr(opt, "name", "appsi_highs")
            except Exception:
                pass
        return result

    setattr(_wrapped_solve_model, "_edim_highs_warmstart_patch", True)
    pyomo_model.solve_model = _wrapped_solve_model


def _patch_calliope_appsi_solver_factory() -> None:
    """
    Calliope 0.6.x passes solver_io=None into SolverFactory unconditionally.
    appsi_highs rejects solver_io, so drop it for that solver.
    """
    try:
        from calliope.backend.pyomo import model as pyomo_model  # type: ignore
    except Exception:
        return

    solver_factory = getattr(pyomo_model, "SolverFactory", None)
    if solver_factory is None or getattr(solver_factory, "_edim_appsi_patch", False):
        return

    def _wrapped_solver_factory(*args, **kwargs):
        solver_name = args[0] if args else kwargs.get("name")
        if isinstance(solver_name, str) and solver_name.strip().lower() == "appsi_highs":
            kwargs = dict(kwargs)
            kwargs.pop("solver_io", None)
        return solver_factory(*args, **kwargs)

    setattr(_wrapped_solver_factory, "_edim_appsi_patch", True)
    pyomo_model.SolverFactory = _wrapped_solver_factory


def _resolve_model_yaml(settings: Settings) -> Path:
    return settings.calliope_root / "model.yaml"


def _extract_import_entries(data: dict) -> List[str]:
    raw_imports = data.get("import", [])
    if isinstance(raw_imports, str):
        return [raw_imports]
    if isinstance(raw_imports, list):
        return [item for item in raw_imports if isinstance(item, str)]
    return []


def _collect_imported_yaml_files(entry_file: Path, repo_root: Path, visited: set[Path], out: List[Path]) -> None:
    resolved = entry_file.resolve()
    if resolved in visited:
        return
    if not resolved.exists() or not resolved.is_file():
        return
    if resolved.suffix.lower() not in {".yaml", ".yml"}:
        return

    visited.add(resolved)
    out.append(resolved)

    try:
        data = _load_yaml(resolved)
    except Exception:
        logger.exception("Failed to parse YAML while collecting imports: %s", resolved)
        return

    root_resolved = repo_root.resolve()
    for rel in _extract_import_entries(data):
        candidate = (resolved.parent / rel).resolve()
        if candidate != root_resolved and root_resolved not in candidate.parents:
            continue
        _collect_imported_yaml_files(candidate, repo_root, visited, out)


def _resolve_tech_library(settings: Settings) -> dict:
    model_yaml = _resolve_model_yaml(settings)
    files: List[Path] = []
    _collect_imported_yaml_files(model_yaml, settings.calliope_root, set(), files)

    merged: dict = {"techs": {}}
    for fpath in files:
        data = _load_yaml(fpath)
        techs = data.get("techs", {})
        if isinstance(techs, dict) and techs:
            merged["techs"] = deep_merge(merged["techs"], techs)

    return merged


def _emit_progress(
    progress_callback: Callable[[str, float, str], None] | None,
    stage: str,
    progress: float,
    message: str,
) -> None:
    if progress_callback is None:
        return
    try:
        bounded = max(0.0, min(1.0, float(progress)))
        progress_callback(stage, bounded, message)
    except Exception:
        logger.exception("Progress callback failed at stage=%s", stage)


def _check_cancel(cancel_requested: Callable[[], bool] | None) -> None:
    if cancel_requested is None:
        return
    try:
        if cancel_requested():
            raise RunCancelledError("Run cancelled by user request.")
    except RunCancelledError:
        raise
    except Exception:
        logger.exception("Cancellation callback failed unexpectedly")


def _apply_demand_multiplier(model, multiplier: float, warnings: List[str]) -> None:
    if abs(float(multiplier) - 1.0) < 1e-9:
        return

    applied = False
    seen_datasets: set[int] = set()
    datasets = [getattr(model, "inputs", None), getattr(model, "_model_data", None)]
    for ds in datasets:
        if ds is None:
            continue
        ds_id = id(ds)
        if ds_id in seen_datasets:
            continue
        seen_datasets.add(ds_id)

        data_vars = getattr(ds, "data_vars", {})
        if "resource" not in data_vars:
            continue

        resource = ds["resource"]
        demand_dim = None
        demand_labels: List[str] = []
        for dim in resource.dims:
            coord = resource.coords.get(dim)
            if coord is None:
                continue
            labels = [str(v) for v in coord.values.tolist()]
            if any(lbl.endswith("::Demand_power") for lbl in labels):
                demand_dim = dim
                demand_labels = [lbl for lbl in labels if lbl.endswith("::Demand_power")]
                break

        if demand_dim is None or not demand_labels:
            continue

        idx = np.array(demand_labels, dtype=object)
        try:
            before = ds["resource"].loc[{demand_dim: idx}]
            ds["resource"].loc[{demand_dim: idx}] = before * float(multiplier)
            applied = True
        except Exception:
            logger.exception("Failed applying demand multiplier on resource[%s]", demand_dim)

    if applied:
        warnings.append(
            f"Demand multiplier applied to Demand_power resource profiles (x{float(multiplier):.4g})."
        )
    else:
        warnings.append(
            "Demand multiplier was set but no Demand_power resource profile was found; lever ignored."
        )


def _build_model_with_overrides(
    model_factory: Callable[..., Any],
    model_yaml: Path,
    scenario: str,
    override_patch: dict,
):
    if not override_patch:
        return model_factory(str(model_yaml), scenario=scenario)

    build_errors: List[str] = []
    try:
        return model_factory(str(model_yaml), scenario=scenario, override_dict=override_patch)
    except TypeError as e:
        build_errors.append(f"Model(build override_dict) failed: {e}")
        try:
            return model_factory(str(model_yaml), scenario=scenario, overrides=override_patch)
        except TypeError as e2:
            build_errors.append(f"Model(build overrides) failed: {e2}")

    raise RuntimeError(
        "Could not apply required runtime overrides when building Calliope model. "
        + " | ".join(build_errors)
    )


def _is_pyomo_solver_available(name: str) -> bool:
    try:
        from pyomo.environ import SolverFactory

        solver = SolverFactory(name)
        return bool(solver.available(False))
    except Exception:
        return False


def _resolve_solver_for_runtime(requested_solver: str) -> Tuple[str, List[str]]:
    normalized = (requested_solver or "").strip().lower() or "highs"
    if normalized != "highs":
        return normalized, []

    if _is_pyomo_solver_available("appsi_highs"):
        return "appsi_highs", []

    if shutil.which("highs"):
        return "highs", []

    return "highs", [
        "No usable HiGHS backend detected. Install highspy (appsi_highs) or set "
        "EDIM_SOLVER to an available solver."
    ]


def _resolve_run_profile(req: RunRequest) -> str:
    profile = str(getattr(req, "run_profile", "") or "").strip().lower()
    if profile in {"dev", "analysis", "full"}:
        return profile
    return "dev"


def _requested_run_id_from_bundle(request_bundle: Dict[str, Any] | None) -> str:
    if not isinstance(request_bundle, dict):
        return ""
    execution_payload = request_bundle.get("execution") if isinstance(request_bundle.get("execution"), dict) else {}
    return str(request_bundle.get("run_id") or execution_payload.get("run_id") or "").strip()


def _artifact_policy_from_bundle(
    request_bundle: Dict[str, Any] | None,
    settings: Settings,
) -> Dict[str, Any]:
    if isinstance(request_bundle, dict) and isinstance(request_bundle.get("artifact_policy"), dict):
        return request_bundle["artifact_policy"]
    return settings.runtime_config


def _prepare_generic_model_run(
    *,
    settings: Settings,
    req: RunRequest,
    request_bundle: Dict[str, Any] | None,
    progress_callback: Callable[[str, float, str], None] | None,
    cancel_requested: Callable[[], bool] | None,
) -> Tuple[str, Path, str, ArtifactRegistry]:
    """Generic run envelope shared by any packaged model implementation.

    Everything here is model-agnostic: validate the request envelope, apply
    retention, allocate the run directory, and create the artifact registry.
    The Calliope/MRIO-specific implementation begins after this function
    returns.
    """
    _emit_progress(progress_callback, "environment_setup", 0.01, "Validating request")
    _check_cancel(cancel_requested)

    run_profile = _resolve_run_profile(req)
    if run_profile == "full" and (not settings.allow_full_year):
        raise ValueError("Full-year runs are disabled in this environment.")

    _emit_progress(progress_callback, "cleanup", 0.03, "Applying run artifact retention")
    _cleanup_old_runs(settings)
    _check_cancel(cancel_requested)

    run_id, run_dir = _create_run_dir(
        settings.runs_dir,
        preferred_run_id=_requested_run_id_from_bundle(request_bundle),
    )
    artifact_registry = ArtifactRegistry(
        run_id,
        run_dir,
        _artifact_policy_from_bundle(request_bundle, settings),
    )
    return run_id, run_dir, run_profile, artifact_registry


def _write_generic_model_input_snapshots(
    *,
    artifact_registry: ArtifactRegistry,
    request_bundle: Dict[str, Any] | None,
    req: RunRequest,
    run_profile: str,
    model_architecture_id: str,
) -> None:
    """Persist input snapshots before model-specific work mutates state."""
    artifact_registry.write_json(
        "request_bundle_json",
        request_bundle
        or {
            "schema_version": "model_run_bundle_v1",
            "energy_model_engine": req.energy_model_engine,
            "model_architecture_id": model_architecture_id,
            "energy_scenario_key": req.energy_scenario_key,
            "mrio_scenario_id": req.mrio_scenario_id,
            "target_year": req.target_year,
            "run_profile": run_profile,
            "strict_validation": bool(req.strict_validation),
            "allow_placeholder_data": bool(req.allow_placeholder_data),
            "levers": req.levers.model_dump(),
        },
        dumps=json_dumps,
    )
    if not isinstance(request_bundle, dict):
        return
    if isinstance(request_bundle.get("model_runtime"), dict):
        artifact_registry.write_json("model_manifest_json", request_bundle["model_runtime"], dumps=json_dumps)
    if isinstance(request_bundle.get("dataset_manifest"), dict):
        artifact_registry.write_json("dataset_manifest_json", request_bundle["dataset_manifest"], dumps=json_dumps)
    if isinstance(request_bundle.get("artifact_policy"), dict):
        artifact_registry.write_json("artifact_policy_json", request_bundle["artifact_policy"], dumps=json_dumps)


def _run_package_metadata(artifact_registry: ArtifactRegistry, run_dir: Path) -> Dict[str, str]:
    return {
        "inputs_dir": str(artifact_registry.layout.inputs_dir.relative_to(run_dir)),
        "work_dir": str(artifact_registry.layout.work_dir.relative_to(run_dir)),
        "artifacts_dir": str(artifact_registry.layout.artifacts_dir.relative_to(run_dir)),
        "logs_dir": str(artifact_registry.layout.logs_dir.relative_to(run_dir)),
        "exports_dir": str(artifact_registry.layout.exports_dir.relative_to(run_dir)),
    }


def _finalize_declared_run_artifacts(
    *,
    run_id: str,
    run_dir: Path,
    summary: Dict[str, Any],
    integrated: Dict[str, Any],
    artifact_registry: ArtifactRegistry,
    include_exchange_bundle: bool,
) -> None:
    """Generic final artifact/index publication shared by all architectures."""
    report_markdown = build_run_report_markdown(summary=summary, integrated=integrated)
    artifact_registry.write_text("report_markdown", report_markdown)
    if include_exchange_bundle:
        create_exchange_bundle_zip(run_dir, artifact_registry=artifact_registry)

    summary["run_package"] = _run_package_metadata(artifact_registry, run_dir)
    artifact_registry.prune_consumed_by("build_integrated")
    artifact_registry.prune_for_outcome(success=True)
    artifact_registry.write_json("summary_json", summary, dumps=json_dumps)
    summary["artifact_catalog"] = artifact_registry.exposed_descriptors()
    artifact_registry.write_json(
        "artifact_index_json",
        {
            "schema_version": "artifact_index_v1",
            "run_id": run_id,
            "artifacts": summary["artifact_catalog"],
        },
        dumps=json_dumps,
    )
    summary["artifact_catalog"] = artifact_registry.exposed_descriptors()
    artifact_registry.write_json("summary_json", summary, dumps=json_dumps)


def _normalize_profile_label(run_profile: str | None) -> str:
    profile = str(run_profile or "").strip().lower()
    if profile in {"dev", "analysis", "full"}:
        return profile
    return "dev"


def _resolve_strict_validation(
    run_profile: str | None,
    strict_validation: bool | None = None,
) -> bool:
    profile = _normalize_profile_label(run_profile)
    if profile in {"analysis", "full"}:
        return True
    return bool(strict_validation)


def _normalize_development_engine_label(engine: str | None) -> str:
    mode = str(engine or "").strip().lower()
    if mode == "mario":
        return mode
    raise RuntimeError("development_engine must be 'mario'.")


def _strict_validation_issues(
    *,
    settings: Settings,
    energy_scenario_key: str,
    run_profile: str | None,
    strict_validation: bool | None,
    allow_placeholder_data: bool = False,
    mapping_quality: Dict[str, Any] | None = None,
) -> List[str]:
    issues: List[str] = []
    if not _resolve_strict_validation(run_profile, strict_validation):
        return issues

    _normalize_development_engine_label(settings.development_engine)
    mario_health = mario_inputs_health(settings.config_dir)
    blocking_files = mario_health.get("blocking_placeholder_files") or []
    if blocking_files and not allow_placeholder_data:
        issues.append(
            "Strict validation failed: expert-owned MARIO inputs still contain placeholder rows "
            f"({', '.join(sorted(blocking_files))})."
        )

    if mapping_quality:
        unmapped_mapping_count = int(_safe_float(mapping_quality.get("unmapped_mapping_count"), 0.0))
        capex_bad = int(_safe_float(mapping_quality.get("capex_split_bad_groups"), 0.0))
        opex_bad = int(_safe_float(mapping_quality.get("opex_split_bad_groups"), 0.0))
        if unmapped_mapping_count > 0:
            issues.append(
                "Strict validation failed: MARIO tech-sector mapping does not cover all required "
                f"technologies ({unmapped_mapping_count} missing)."
            )
        if capex_bad > 0:
            issues.append(
                "Strict validation failed: CAPEX split table has groups that do not sum to 1 "
                f"({capex_bad} invalid groups)."
            )
        if opex_bad > 0:
            issues.append(
                "Strict validation failed: OPEX split table has groups that do not sum to 1 "
                f"({opex_bad} invalid groups)."
            )

    assumptions = load_scenario_assumptions(settings.config_dir, scenario_key=energy_scenario_key)
    if (not allow_placeholder_data) and int(assumptions.get("selected_placeholder_row_count") or 0) > 0:
        issues.append(
            "Strict validation failed: selected scenario assumptions still use placeholder rows in "
            "scenario_assumptions.csv."
        )
    return issues


def build_environment_setup_report(
    settings: Settings,
    queue_stats: Dict[str, Any] | None = None,
    energy_scenario_key: str = "",
    mrio_scenario_id: str = "",
    target_year: int = 2030,
    run_profile: str | None = None,
    strict_validation: bool | None = None,
    allow_placeholder_data: bool = False,
) -> Dict[str, Any]:
    checks: List[Dict[str, str]] = []
    warnings: List[str] = []
    errors: List[str] = []
    tech_library: Dict[str, Any] = {}

    def _record(status: str, name: str, message: str, label: str = "", category: str = "runtime") -> None:
        checks.append(
            {
                "name": name,
                "label": label or name.replace("_", " ").title(),
                "category": category,
                "status": status,
                "message": message,
            }
        )
        if status == "error":
            errors.append(message)
        elif status == "warn":
            warnings.append(message)

    model_path = settings.calliope_root / "model.yaml"
    if model_path.exists():
        _record("ok", "calliope_model", f"Found model.yaml at {model_path}", label="Calliope Model File", category="calliope")
    else:
        _record(
            "error",
            "calliope_model",
            f"Missing Calliope model file: {model_path}",
            label="Calliope Model File",
            category="calliope",
        )

    overrides_path = settings.calliope_root / "overrides.yaml"
    scenario_options: List[str] = []
    if overrides_path.exists():
        _record(
            "ok",
            "calliope_overrides",
            f"Found overrides.yaml at {overrides_path}",
            label="Calliope Scenario Overrides",
            category="calliope",
        )
        try:
            scenario_options = load_scenarios_from_overrides(overrides_path)
            _record(
                "ok",
                "scenario_catalog",
                f"Loaded {len(scenario_options)} scenarios from overrides.yaml.",
                label="Scenario Catalog Loaded",
                category="calliope",
            )
        except Exception:
            logger.exception("Failed loading scenario list from overrides.yaml during environment setup check")
            _record(
                "warn",
                "scenario_catalog",
                "Could not parse overrides.yaml scenario list.",
                label="Scenario Catalog Loaded",
                category="calliope",
            )
    else:
        _record(
            "error",
            "calliope_overrides",
            f"Missing overrides.yaml file: {overrides_path}",
            label="Calliope Scenario Overrides",
            category="calliope",
        )

    requested_energy_scenario = str(energy_scenario_key or "").strip()
    requested_mrio_scenario = str(mrio_scenario_id or "").strip()
    if requested_energy_scenario:
        if scenario_options:
            if requested_energy_scenario in scenario_options:
                _record(
                    "ok",
                    "energy_scenario_selection",
                    f"Energy scenario '{requested_energy_scenario}' is available.",
                    label="Energy Scenario Valid",
                    category="calliope",
                )
            else:
                _record(
                    "error",
                    "energy_scenario_selection",
                    f"Energy scenario '{requested_energy_scenario}' is not in overrides.yaml.",
                    label="Energy Scenario Valid",
                    category="calliope",
                )
        else:
            _record(
                "warn",
                "energy_scenario_selection",
                "Scenario list unavailable; cannot validate selection.",
                label="Energy Scenario Valid",
                category="calliope",
            )

    if requested_mrio_scenario:
        try:
            scenario_package = build_scenario_package(
                config_dir=settings.config_dir,
                calliope_root=settings.calliope_root,
                energy_scenario_key=requested_energy_scenario,
                mrio_scenario_id=requested_mrio_scenario,
                target_year=int(target_year),
                run_profile=_normalize_profile_label(run_profile),
                levers={},
                strict_validation=bool(strict_validation),
                allow_placeholder_data=bool(allow_placeholder_data),
            )
            alignment = scenario_package.get("geography_alignment") or {}
            level = "warn" if str(alignment.get("status")) == "mrio_only" else "ok"
            _record(
                level,
                "mrio_report_scenario",
                (
                    f"Loaded MRIO-direct scenario '{requested_mrio_scenario}' for target year {int(target_year)}. "
                    f"Geography alignment status: {alignment.get('status', '')}."
                ),
                label="MRIO Report Scenario Valid",
                category="mario",
            )
        except Exception as exc:
            _record(
                "error",
                "mrio_report_scenario",
                str(exc),
                label="MRIO Report Scenario Valid",
                category="mario",
            )

    if model_path.exists():
        try:
            tech_library = _resolve_tech_library(settings)
            tech_count = len((tech_library.get("techs") or {}))
            if tech_count > 0:
                _record(
                    "ok",
                    "calliope_tech_library",
                    f"Parsed Calliope tech library ({tech_count} technologies merged from imports).",
                    label="Calliope Tech Library Loaded",
                    category="calliope",
                )
            else:
                _record(
                    "warn",
                    "calliope_tech_library",
                    "Calliope tech library parsed but no technologies were found.",
                    label="Calliope Tech Library Loaded",
                    category="calliope",
                )
        except Exception:
            logger.exception("Failed parsing Calliope tech library during environment setup check")
            _record(
                "error",
                "calliope_tech_library",
                "Failed to parse imported Calliope YAML tech library.",
                label="Calliope Tech Library Loaded",
                category="calliope",
            )

    lever_map_path = settings.config_dir / "lever_mappings.csv"
    if lever_map_path.exists():
        try:
            mappings = load_lever_mappings(settings.config_dir)
            _record(
                "ok",
                "lever_mappings",
                (
                    "Loaded lever controls "
                    f"(renewables specs={len(mappings.renewables_techs)}, "
                    f"fossil specs={len(mappings.fossil_techs)})."
                ),
                label="Lever Controls Loaded",
                category="controls",
            )
        except Exception:
            logger.exception("Failed loading lever mappings during environment setup check")
            _record(
                "error",
                "lever_mappings",
                f"Lever mappings file exists but could not be parsed: {lever_map_path}",
                label="Lever Controls Loaded",
                category="controls",
            )
    else:
        _record(
            "error",
            "lever_mappings",
            f"Missing required lever mappings file: {lever_map_path}",
            label="Lever Controls Loaded",
            category="controls",
        )

    metadata_path = settings.config_dir / "scenario_metadata.csv"
    if metadata_path.exists():
        try:
            metadata = load_scenario_metadata(metadata_path)
            metadata_count = len(metadata)
            if metadata_count == 0:
                _record(
                    "warn",
                    "scenario_metadata",
                    "Scenario metadata file loaded but has no valid rows.",
                    label="Scenario Metadata Loaded",
                    category="controls",
                )
            else:
                coverage_msg = ""
                if scenario_options:
                    overlap = sum(1 for key in metadata.keys() if key in set(scenario_options))
                    coverage = overlap / max(len(scenario_options), 1)
                    coverage_msg = f" Coverage {overlap}/{len(scenario_options)} scenarios ({coverage:.0%})."
                _record(
                    "ok",
                    "scenario_metadata",
                    f"Loaded scenario metadata for {metadata_count} scenarios.{coverage_msg}",
                    label="Scenario Metadata Loaded",
                    category="controls",
                )
        except Exception:
            logger.exception("Failed loading scenario metadata during environment setup check")
            _record(
                "warn",
                "scenario_metadata",
                f"Scenario metadata file exists but could not be parsed: {metadata_path}",
                label="Scenario Metadata Loaded",
                category="controls",
            )
    else:
        _record(
            "warn",
            "scenario_metadata",
            f"Optional scenario metadata missing: {metadata_path}",
            label="Scenario Metadata Loaded",
            category="controls",
        )

    development_model_path = settings.config_dir / "development_model.csv"
    if development_model_path.exists():
        try:
            cfg_rows = _read_csv_rows(development_model_path)
            cfg = _load_development_model_config(settings.config_dir)
            mario_present = "mario" in cfg
            _record(
                "ok",
                "development_model_config",
                (
                    f"Loaded development model controls ({len(cfg_rows)} parameter rows). "
                    f"Sections: mario={mario_present}."
                ),
                label="Development Model Controls Loaded",
                category="controls",
            )
        except Exception:
            logger.exception("Failed loading development_model.csv during environment setup check")
            _record(
                "warn",
                "development_model_config",
                f"Development model controls file exists but could not be parsed: {development_model_path}",
                label="Development Model Controls Loaded",
                category="controls",
            )
    else:
        _record(
            "error",
            "development_model_config",
            f"Required development model controls file missing: {development_model_path}",
            label="Development Model Controls Loaded",
            category="controls",
        )

    profile = _normalize_profile_label(run_profile)
    strict_effective = _resolve_strict_validation(profile, strict_validation)
    if profile == "full" and (not settings.allow_full_year):
        _record(
            "error",
            "run_profile",
            "Full profile requested but full-year runs are disabled.",
            label="Run Profile Allowed",
            category="runtime",
        )
    else:
        _record("ok", "run_profile", f"Run profile '{profile}' is allowed.", label="Run Profile Allowed", category="runtime")
    _record(
        "ok",
        "strict_validation",
        (
            "Strict validation is enabled."
            if strict_effective
            else "Strict validation is disabled for this development run profile."
        ),
        label="Validation Mode",
        category="runtime",
    )
    _record(
        "ok",
        "placeholder_data_mode",
        (
            "Placeholder expert datasets are allowed for this run."
            if allow_placeholder_data
            else "Placeholder expert datasets are not allowed."
        ),
        label="Placeholder Data Mode",
        category="runtime",
    )

    if profile == "dev":
        _record(
            "ok",
            "runtime_subset_window",
            f"Dev subset window: {settings.dev_subset_start} to {settings.dev_subset_end}",
            label="Run Time Subset Window",
            category="runtime",
        )
        _record(
            "ok",
            "runtime_solver_time_limit",
            f"Dev solver time limit: {settings.dev_solver_time_limit_seconds:.0f} seconds.",
            label="Solver Time Limit",
            category="runtime",
        )
    elif profile == "analysis":
        _record(
            "ok",
            "runtime_subset_window",
            f"Analysis subset window: {settings.analysis_subset_start} to {settings.analysis_subset_end}",
            label="Run Time Subset Window",
            category="runtime",
        )
        _record(
            "ok",
            "runtime_solver_time_limit",
            f"Analysis solver time limit: {settings.analysis_solver_time_limit_seconds:.0f} seconds.",
            label="Solver Time Limit",
            category="runtime",
        )

    resolved_solver, solver_warnings = _resolve_solver_for_runtime(settings.solver)
    if solver_warnings:
        for message in solver_warnings:
            level = "warn"
            if "Using appsi_highs" in message:
                level = "ok"
            _record(level, "solver", message, label="Solver Backend Loaded", category="runtime")
    else:
        _record(
            "ok",
            "solver",
            f"Solver '{resolved_solver}' is available for EDIM_SOLVER={settings.solver}.",
            label="Solver Backend Loaded",
            category="runtime",
        )

    queue = dict(queue_stats or {})
    capacity = max(1, int(_safe_float(queue.get("capacity"), settings.job_queue_capacity)))
    active_jobs = max(0, int(_safe_float(queue.get("active_jobs"), 0)))
    queue["capacity"] = capacity
    queue["active_jobs"] = active_jobs
    queue["has_capacity"] = active_jobs < capacity
    if queue["has_capacity"]:
        _record(
            "ok",
            "queue_capacity",
            f"Queue has capacity ({active_jobs}/{capacity} active jobs).",
            label="Job Queue Capacity",
            category="runtime",
        )
    else:
        _record(
            "warn",
            "queue_capacity",
            f"Queue is full ({active_jobs}/{capacity} active jobs).",
            label="Job Queue Capacity",
            category="runtime",
        )

    development_engine = _normalize_development_engine_label(settings.development_engine)
    _record(
        "ok",
        "development_engine",
        f"Development engine mode: {development_engine}",
        label="Development Engine Mode",
        category="mario",
    )
    _record(
        "ok",
        "mario_timeout",
        f"MARIO timeout set to {settings.mario_timeout_seconds:.1f} seconds.",
        label="MARIO Runtime Timeout",
        category="mario",
    )
    mario_health = mario_inputs_health(settings.config_dir)
    if mario_health.get("ok"):
        _record(
            "ok",
            "mario_inputs",
            "MARIO input mappings and intensities are available.",
            label="MARIO Inputs Loaded",
            category="mario",
        )
    else:
        missing = ", ".join(mario_health.get("missing_required", []))
        _record("error", "mario_inputs", f"MARIO required inputs missing: {missing}", label="MARIO Inputs Loaded", category="mario")

    placeholder_details = mario_health.get("placeholder_details") or []
    if placeholder_details:
        total_placeholder_rows = sum(
            int((row or {}).get("placeholder_row_count") or 0) for row in placeholder_details
        )
        file_names = sorted(
            str((row or {}).get("file_name", "")).strip()
            for row in placeholder_details
            if str((row or {}).get("file_name", "")).strip()
        )
        _record(
            "error"
            if strict_effective and (mario_health.get("blocking_placeholder_files") or []) and not allow_placeholder_data
            else "warn",
            "mario_placeholder_inputs",
            (
                "Expert-owned MARIO datasets still contain placeholder rows "
                f"({total_placeholder_rows} rows across {len(file_names)} files). "
                f"Files: {', '.join(file_names)}"
            ),
            label="Expert Data Calibration",
            category="mario",
        )
    else:
        _record(
            "ok",
            "mario_placeholder_inputs",
            "Expert-owned MARIO datasets do not contain placeholder rows.",
            label="Expert Data Calibration",
            category="mario",
        )

    indicator_mapping = load_development_indicator_mapping(settings.config_dir)
    if indicator_mapping.get("exists"):
        _record(
            "ok",
            "development_indicator_mapping",
            f"Loaded development indicator mapping ({int(indicator_mapping.get('record_count') or 0)} rows).",
            label="Development Indicator Mapping",
            category="mario",
        )
    else:
        _record(
            "warn",
            "development_indicator_mapping",
            "development_indicator_mapping.csv is missing; integrated indicator reporting will be limited.",
            label="Development Indicator Mapping",
            category="mario",
        )

    assumptions = load_scenario_assumptions(settings.config_dir, scenario_key=requested_energy_scenario)
    selected_placeholder_count = int(assumptions.get("selected_placeholder_row_count") or 0)
    selected_count = int(assumptions.get("selected_count") or 0)
    if assumptions.get("exists"):
        if selected_placeholder_count > 0:
            _record(
                "error" if strict_effective and not allow_placeholder_data else "warn",
                "scenario_assumptions",
                f"Selected scenario assumptions still contain placeholder rows ({selected_placeholder_count} matched rows).",
                label="Scenario Assumptions Loaded",
                category="mario",
            )
        elif selected_count > 0:
            _record(
                "ok",
                "scenario_assumptions",
                f"Loaded {selected_count} matched scenario assumptions for integrated indicators.",
                label="Scenario Assumptions Loaded",
                category="mario",
            )
        else:
            _record(
                "warn",
                "scenario_assumptions",
                "scenario_assumptions.csv exists but no rows matched the selected scenario or baseline.",
                label="Scenario Assumptions Loaded",
                category="mario",
            )
    else:
        _record(
            "warn",
            "scenario_assumptions",
            "scenario_assumptions.csv is missing; indicator assumptions will use request levers where possible.",
            label="Scenario Assumptions Loaded",
            category="mario",
        )

    if tech_library:
        mapping_quality, mapping_quality_warnings = _evaluate_mario_mapping_quality(settings.config_dir, tech_library)
        if mapping_quality_warnings:
            _record(
                "error" if strict_effective else "warn",
                "mario_mapping_quality",
                " ".join(mapping_quality_warnings),
                label="MARIO Mapping Quality",
                category="mario",
            )
        else:
            _record(
                "ok",
                "mario_mapping_quality",
                "MARIO mapping coverage and split tables passed validation checks.",
                label="MARIO Mapping Quality",
                category="mario",
            )

    if settings.mario_db_path:
        db_path = Path(settings.mario_db_path).expanduser()
        if db_path.exists():
            _record(
                "ok",
                "mario_db_path",
                f"Configured MARIO DB path exists: {db_path}",
                label="MARIO DB Path",
                category="mario",
            )
        else:
            msg = f"Configured MARIO DB path does not exist: {db_path}"
            _record("error", "mario_db_path", msg, label="MARIO DB Path", category="mario")

    ready = (len(errors) == 0) and bool(queue["has_capacity"])
    return {
        "ok": ready,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "energy_scenario_key": requested_energy_scenario,
        "mrio_scenario_id": requested_mrio_scenario,
        "target_year": int(target_year),
        "run_profile": profile,
        "strict_validation": strict_effective,
        "allow_placeholder_data": bool(allow_placeholder_data),
        "solver_requested": settings.solver,
        "solver_resolved": resolved_solver,
        "development_engine": development_engine,
        "queue": queue,
        "mario_inputs": mario_health,
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
    }


# Backward-compatible alias for older callers still using "preflight" terminology.
def build_preflight_report(
    settings: Settings,
    queue_stats: Dict[str, Any] | None = None,
    energy_scenario_key: str = "",
    mrio_scenario_id: str = "",
    target_year: int = 2030,
    run_profile: str | None = None,
    strict_validation: bool | None = None,
    allow_placeholder_data: bool = False,
) -> Dict[str, Any]:
    return build_environment_setup_report(
        settings=settings,
        queue_stats=queue_stats,
        energy_scenario_key=energy_scenario_key,
        mrio_scenario_id=mrio_scenario_id,
        target_year=target_year,
        run_profile=run_profile,
        strict_validation=strict_validation,
        allow_placeholder_data=allow_placeholder_data,
    )


def _build_runtime_override_patch(
    settings: Settings,
    req: RunRequest,
    lever_patch: dict,
    solver_name: str,
) -> dict:
    run_profile = _resolve_run_profile(req)
    solver_patch = {"run": {"solver": solver_name}}
    if solver_name != "gurobi":
        # Clear inherited Gurobi-specific options (e.g. NumericFocus).
        solver_options: dict = {}
        if run_profile == "dev":
            solver_options["time_limit"] = float(settings.dev_solver_time_limit_seconds)
        elif run_profile == "analysis":
            solver_options["time_limit"] = float(settings.analysis_solver_time_limit_seconds)
        solver_patch["run"]["solver_options"] = solver_options or {"_REPLACE_": None}

    time_patch: dict = {}
    if run_profile == "dev":
        time_patch = {"model": {"subset_time": [settings.dev_subset_start, settings.dev_subset_end]}}
    elif run_profile == "analysis":
        time_patch = {
            "model": {"subset_time": [settings.analysis_subset_start, settings.analysis_subset_end]}
        }

    override_patch: dict = {}
    for patch in (solver_patch, time_patch, lever_patch):
        if patch:
            override_patch = deep_merge(override_patch, patch)
    return override_patch


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _sum_cost_class(summary: Dict[str, Any], cost_class: str) -> float:
    records = ((summary.get("system_cost") or {}).get("records") or [])
    total = 0.0
    target = cost_class.strip().lower()
    for rec in records:
        label = str((rec or {}).get("costs", "")).strip().lower()
        if label == target:
            total += _safe_float((rec or {}).get("value"), 0.0)
    return total


def _sum_component_cost(summary_diagnostics: Dict[str, Any], component: str) -> float:
    records = ((summary_diagnostics.get("cost_decomposition") or {}).get("component_records") or [])
    total = 0.0
    wanted = component.strip().lower()
    for row in records:
        if not isinstance(row, dict):
            continue
        if str(row.get("component", "")).strip().lower() != wanted:
            continue
        if str(row.get("costs", "")).strip().lower() != "monetary":
            continue
        total += _safe_float(row.get("value"), 0.0)
    return max(total, 0.0)


def _normalize_pool_rows(summary_diagnostics: Dict[str, Any]) -> List[Dict[str, float]]:
    reliability = summary_diagnostics.get("reliability") or {}
    trade = summary_diagnostics.get("trade_matrix") or {}

    demand_rows = ((reliability.get("demand_by_pool") or {}).get("records") or [])
    unserved_rows = ((reliability.get("unserved_by_pool") or {}).get("records") or [])
    net_rows = ((trade.get("net_by_pool") or {}).get("records") or [])

    pools: Dict[str, Dict[str, float]] = {}

    def _row(pool: str) -> Dict[str, float]:
        key = str(pool or "UNKNOWN")
        if key not in pools:
            pools[key] = {"pool": key, "demand": 0.0, "unserved": 0.0, "net_imports": 0.0}
        return pools[key]

    for rec in demand_rows:
        if not isinstance(rec, dict):
            continue
        cur = _row(str(rec.get("pool", "UNKNOWN")))
        cur["demand"] += _safe_float(rec.get("value"), 0.0)

    for rec in unserved_rows:
        if not isinstance(rec, dict):
            continue
        cur = _row(str(rec.get("pool", "UNKNOWN")))
        cur["unserved"] += _safe_float(rec.get("value"), 0.0)

    for rec in net_rows:
        if not isinstance(rec, dict):
            continue
        cur = _row(str(rec.get("pool", "UNKNOWN")))
        if ("exports" in rec) or ("imports" in rec):
            cur["net_imports"] += _safe_float(rec.get("imports"), 0.0) - _safe_float(rec.get("exports"), 0.0)
        else:
            # Legacy summaries stored net exports in `value`; convert to net imports.
            cur["net_imports"] -= _safe_float(rec.get("value"), 0.0)

    rows = list(pools.values())
    rows.sort(key=lambda r: abs(r["demand"]), reverse=True)

    if not rows:
        demand_total = _safe_float(reliability.get("demand_total"), 0.0)
        unserved_total = _safe_float(reliability.get("unserved_total"), 0.0)
        if demand_total or unserved_total:
            rows = [
                {
                    "pool": "ALL",
                    "demand": demand_total,
                    "unserved": unserved_total,
                    "net_imports": 0.0,
                }
            ]

    return rows


def _stringify_csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if np.isnan(value) or np.isinf(value):
            return ""
        return f"{value:.10g}"
    return str(value)


def _write_results_csv(path: Path, model: Any) -> int:
    results = getattr(model, "results", None)
    if results is None or not getattr(results, "data_vars", None):
        return 0

    data_vars = sorted(str(name) for name in results.data_vars.keys())
    all_dims: List[str] = []
    for name in data_vars:
        da = results[name]
        for dim in da.dims:
            dim_name = str(dim)
            if dim_name not in all_dims:
                all_dims.append(dim_name)

    path.parent.mkdir(parents=True, exist_ok=True)
    row_count = 0
    with path.open("w", encoding="utf-8", newline="") as f:
        fieldnames = ["variable"] + all_dims + ["value"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for var_name in data_vars:
            da = results[var_name]
            try:
                table = da.to_dataframe(name="value").reset_index()
            except Exception:
                logger.exception("Failed converting result variable '%s' to CSV rows", var_name)
                continue

            if "value" not in table.columns:
                continue

            try:
                table = table[table["value"].notna()]
            except Exception:
                pass

            for record in table.to_dict(orient="records"):
                out: Dict[str, str] = {"variable": var_name, "value": _stringify_csv_value(record.get("value"))}
                for dim in all_dims:
                    out[dim] = _stringify_csv_value(record.get(dim))
                writer.writerow(out)
                row_count += 1

    return row_count


def _results_health(model: Any) -> Dict[str, Any]:
    results = getattr(model, "results", None)
    attrs = getattr(results, "attrs", {}) or {}
    data_vars = getattr(results, "data_vars", None)
    try:
        var_count = int(len(data_vars.keys())) if data_vars is not None else 0
    except Exception:
        var_count = 0
    return {
        "var_count": var_count,
        "termination_condition": str(attrs.get("termination_condition", "")).strip(),
        "solution_time": attrs.get("solution_time"),
        "objective_function_value": attrs.get("objective_function_value"),
    }


def _write_energy_service_balance_csv(
    path: Path,
    run_id: str,
    scenario: str,
    summary_diagnostics: Dict[str, Any],
    year: int,
    pool_to_region: Dict[str, str] | None = None,
) -> None:
    rows = _normalize_pool_rows(summary_diagnostics)
    pool_to_region = pool_to_region or {}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "run_id",
                "scenario",
                "region",
                "power_pool",
                "carrier",
                "generation",
                "demand",
                "unserved",
                "net_imports",
                "year",
            ],
        )
        writer.writeheader()
        for row in rows:
            pool = str(row["pool"])
            net_imports = _safe_float(row["net_imports"], 0.0)
            demand = _safe_float(row["demand"], 0.0)
            unserved = _safe_float(row["unserved"], 0.0)
            generation = max(demand - unserved - net_imports, 0.0)
            writer.writerow(
                {
                    "run_id": run_id,
                    "scenario": scenario,
                    "region": pool_to_region.get(pool, pool),
                    "power_pool": pool,
                    "carrier": "power",
                    "generation": f"{generation:.6f}",
                    "demand": f"{demand:.6f}",
                    "unserved": f"{unserved:.6f}",
                    "net_imports": f"{net_imports:.6f}",
                    "year": int(year),
                }
            )


def _config_float(config: Dict[str, Any], path: List[str], default: float) -> float:
    cur: Any = config
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return float(default)
        cur = cur[key]
    return _safe_float(cur, default)


def _set_nested_by_dotted_key(root: Dict[str, Any], dotted_key: str, value: float) -> None:
    parts = [part.strip() for part in str(dotted_key).split(".") if part.strip()]
    if not parts:
        return
    cur: Dict[str, Any] = root
    for part in parts[:-1]:
        existing = cur.get(part)
        if not isinstance(existing, dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = float(value)


def _load_development_model_config(config_dir: Path) -> Dict[str, Any]:
    config = deep_merge({}, DEVELOPMENT_MODEL_DEFAULTS)
    path = config_dir / "development_model.csv"
    if not path.exists():
        raise FileNotFoundError(f"Required development model config not found: {path}")
    try:
        rows = _read_csv_rows(path)
    except Exception as exc:
        raise RuntimeError(f"Failed loading development model config at {path}: {exc}") from exc
    for row in rows:
        key = str(row.get("parameter", "")).strip() or str(row.get("key", "")).strip()
        raw_value = str(row.get("value", "")).strip()
        if not key or not raw_value:
            continue
        try:
            value = float(raw_value)
        except ValueError:
            continue
        _set_nested_by_dotted_key(config, key, value)
    return config


def _read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    out: List[Dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if isinstance(row, dict):
                out.append({str(k): str(v) for k, v in row.items()})
    return out


def _share_issues(
    rows: List[Dict[str, str]],
    share_key: str,
    group_keys: List[str],
    tolerance: float = 0.01,
) -> int:
    grouped: Dict[Tuple[str, ...], float] = {}
    for row in rows:
        group = tuple(str(row.get(key, "")).strip() for key in group_keys)
        share = _safe_float(row.get(share_key), 0.0)
        grouped[group] = grouped.get(group, 0.0) + share
    issues = 0
    for total in grouped.values():
        if abs(total - 1.0) > tolerance:
            issues += 1
    return issues


def _evaluate_mario_mapping_quality(config_dir: Path, tech_library: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    out: Dict[str, Any] = {
        "mapping_coverage_share": 0.0,
        "unmapped_mapping_share": 1.0,
        "unmapped_mapping_count": 0,
        "mapping_required_tech_count": 0,
        "mapping_mapped_tech_count": 0,
        "capex_split_bad_groups": 0,
        "opex_split_bad_groups": 0,
        "mapping_validation_warning_count": 0,
    }

    mario_dir = config_dir / "mario_inputs"
    if not mario_dir.exists():
        warnings.append("MARIO mapping diagnostics skipped: inputs/mario_inputs directory not found.")
        out["mapping_validation_warning_count"] = len(warnings)
        return out, warnings

    available_techs = sorted((tech_library.get("techs") or {}).keys())
    required_techs = [
        tech
        for tech in available_techs
        if ("Demand" not in tech) and ("Transmission" not in tech) and ("_kV" not in tech)
    ]
    required_set = set(required_techs)
    out["mapping_required_tech_count"] = len(required_set)

    tech_map_rows = _read_csv_rows(mario_dir / "calliope_tech_to_mario_sector.csv")
    if not tech_map_rows:
        warnings.append("MARIO mapping file calliope_tech_to_mario_sector.csv is missing or empty.")
    tech_map_df = pd.DataFrame(tech_map_rows) if tech_map_rows else pd.DataFrame()
    if not tech_map_df.empty:
        for col in tech_map_df.columns:
            tech_map_df[col] = tech_map_df[col].fillna("").astype(str).str.strip()
    mapped_required: set[str] = set()
    for tech in required_set:
        tech_group = _classify_tech_group(tech)
        match = _match_rows_by_tech(tech_map_df, technology=tech, tech_group=tech_group)
        if not match.empty:
            mapped_required.add(tech)

    coverage = (len(mapped_required) / float(len(required_set))) if required_set else 1.0
    missing_techs = sorted(required_set - mapped_required)
    out["mapping_mapped_tech_count"] = len(mapped_required)
    out["mapping_coverage_share"] = coverage
    out["unmapped_mapping_share"] = max(0.0, 1.0 - coverage)
    out["unmapped_mapping_count"] = len(missing_techs)

    if coverage < 0.8:
        preview = ", ".join(missing_techs[:5])
        warnings.append(
            "MARIO mapping coverage is low "
            f"({coverage:.1%}, missing {len(missing_techs)} techs)."
            + (f" Examples: {preview}" if preview else "")
        )

    capex_rows = _read_csv_rows(mario_dir / "capex_sector_split.csv")
    opex_rows = _read_csv_rows(mario_dir / "opex_sector_split.csv")
    if not capex_rows:
        warnings.append("MARIO mapping file capex_sector_split.csv is missing or empty.")
    if not opex_rows:
        warnings.append("MARIO mapping file opex_sector_split.csv is missing or empty.")
    out["capex_split_bad_groups"] = _share_issues(
        rows=capex_rows,
        share_key="share",
        group_keys=["calliope_tech", "mario_region"],
    )
    out["opex_split_bad_groups"] = _share_issues(
        rows=opex_rows,
        share_key="share",
        group_keys=["calliope_tech", "mario_region", "opex_type"],
    )

    if out["capex_split_bad_groups"] > 0:
        warnings.append(
            "CAPEX split table has groups where shares do not sum to 1: "
            f"{out['capex_split_bad_groups']}"
        )
    if out["opex_split_bad_groups"] > 0:
        warnings.append(
            "OPEX split table has groups where shares do not sum to 1: "
            f"{out['opex_split_bad_groups']}"
        )

    out["mapping_validation_warning_count"] = len(warnings)
    return out, warnings


def _default_region_for_pool(pool: str) -> str:
    defaults = {
        "CAPP": "Central_Africa",
        "EAPP": "East_Africa",
        "NAPP": "North_Africa",
        "SAPP": "Southern_Africa",
        "WAPP": "West_Africa",
    }
    return defaults.get(str(pool).strip(), str(pool).strip() or "UNKNOWN")


POOL_LOCATION_FILES = {
    "CAPP": "CAPP/Location_Constraints_CAPP.yaml",
    "EAPP": "EAPP/Location_Constraints_EAPP.yaml",
    "NAPP": "NAPP/Location_Constraints_NAPP.yaml",
    "SAPP": "SAPP/Location_Constraints_SAPP.yaml",
    "WAPP": "WAPP/Location_Constraints_WAPP.yaml",
}


def _year_from_profile(settings: Settings, req: RunRequest) -> int:
    target_year = int(getattr(req, "target_year", 0) or 0)
    if target_year > 1900:
        return target_year
    profile = _resolve_run_profile(req)
    if profile == "analysis":
        source = settings.analysis_subset_start
    elif profile == "full":
        source = settings.dev_subset_start
    else:
        source = settings.dev_subset_start
    year = int(str(source).split("-")[0])
    return year if year > 1900 else 2019


def _load_country_pool_mapping(
    config_dir: Path, calliope_root: Path | None = None
) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    path = config_dir / "mario_inputs" / "country_to_pool.csv"
    loc_to_region: Dict[str, str] = {}
    loc_to_pool: Dict[str, str] = {}
    pool_to_region: Dict[str, str] = {}
    if path.exists():
        for row in _read_csv_rows(path):
            loc = str(row.get("calliope_location", "")).strip()
            pool = str(row.get("power_pool", "")).strip()
            region = str(row.get("mario_region", "")).strip()
            if not loc:
                continue
            if pool:
                loc_to_pool[loc] = pool
            if region:
                loc_to_region[loc] = region
            elif pool:
                loc_to_region[loc] = _default_region_for_pool(pool)
            if pool and region:
                pool_to_region[pool] = region
            elif pool:
                pool_to_region.setdefault(pool, _default_region_for_pool(pool))

    # Fill missing locations from canonical Calliope pool location constraints.
    if calliope_root is not None:
        for pool, rel_path in POOL_LOCATION_FILES.items():
            path = calliope_root / rel_path
            if not path.exists():
                continue
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            for loc in (data.get("locations") or {}).keys():
                key = str(loc).strip()
                if not key:
                    continue
                loc_to_pool.setdefault(key, pool)
                loc_to_region.setdefault(key, _default_region_for_pool(pool))
            pool_to_region.setdefault(pool, _default_region_for_pool(pool))
    return loc_to_region, loc_to_pool, pool_to_region


def _classify_tech_group(tech: str) -> str:
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


def _da_to_dataframe(da: Any) -> pd.DataFrame:
    try:
        return da.to_dataframe(name="value").reset_index()
    except Exception:
        return pd.DataFrame(columns=["value"])


def _clean_df_values(df: pd.DataFrame) -> pd.DataFrame:
    if "value" not in df.columns:
        return pd.DataFrame(columns=["value"])
    out = df.copy()
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.replace([np.inf, -np.inf], np.nan).dropna(subset=["value"])
    return out


def _expand_calliope_indices(df: pd.DataFrame) -> pd.DataFrame:
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
    return out


def _extract_component_base_rows(
    model: Any,
    component: str,
    variable: str,
    opex_type: str,
) -> pd.DataFrame:
    if variable not in model.results:
        return pd.DataFrame(
            columns=[
                "location",
                "technology",
                "component",
                "opex_type",
                "shock_value_musd",
            ]
        )
    raw = _expand_calliope_indices(_clean_df_values(_da_to_dataframe(model.results[variable])))
    if raw.empty:
        return pd.DataFrame(
            columns=[
                "location",
                "technology",
                "component",
                "opex_type",
                "shock_value_musd",
            ]
        )
    if "costs" in raw.columns:
        raw = raw[raw["costs"].astype(str).str.strip().str.lower() == "monetary"]
    if raw.empty:
        return pd.DataFrame(
            columns=[
                "location",
                "technology",
                "component",
                "opex_type",
                "shock_value_musd",
            ]
        )

    if "locs" not in raw.columns:
        raw["locs"] = "ALL"
    if "techs" not in raw.columns:
        raw["techs"] = "ALL"
    grouped = raw.groupby(["locs", "techs"], as_index=False)["value"].sum()
    grouped["value"] = pd.to_numeric(grouped["value"], errors="coerce").fillna(0.0).clip(lower=0.0)
    grouped = grouped[grouped["value"] > 0]
    if grouped.empty:
        return pd.DataFrame(
            columns=[
                "location",
                "technology",
                "component",
                "opex_type",
                "shock_value_musd",
            ]
        )
    grouped["component"] = component
    grouped["opex_type"] = opex_type
    grouped["location"] = grouped["locs"].astype(str)
    grouped["technology"] = grouped["techs"].astype(str)
    grouped["shock_value_musd"] = grouped["value"] / 1_000_000.0
    return grouped[["location", "technology", "component", "opex_type", "shock_value_musd"]]


def _build_component_base_rows(model: Any, warnings: List[str]) -> Tuple[pd.DataFrame, Dict[str, str]]:
    source_by_component: Dict[str, str] = {}
    parts: List[pd.DataFrame] = []

    def _add_rows(component: str, variable: str, opex_type: str) -> pd.DataFrame:
        rows = _extract_component_base_rows(model=model, component=component, variable=variable, opex_type=opex_type)
        if rows.empty:
            return rows
        rows = rows.copy()
        rows["source_variable"] = variable
        source_by_component[component] = variable
        parts.append(rows)
        return rows

    _add_rows("investment", "cost_investment", "capex")
    fixed_rows = _add_rows("fixed_om", "cost_om_annual", "om")
    var_prod_rows = _add_rows("variable_prod", "cost_om_prod", "om")
    var_con_rows = _add_rows("variable_con", "cost_om_con", "fuel")

    # Calliope-Africa commonly publishes variable operating costs as `cost_var`.
    # Use it when explicit om_prod/om_con result arrays are unavailable.
    if var_prod_rows.empty and var_con_rows.empty:
        mixed = _extract_component_base_rows(model=model, component="variable_mixed", variable="cost_var", opex_type="mixed")
        if not mixed.empty:
            mixed = mixed.copy()
            mixed["source_variable"] = "cost_var"
            fossil_mask = mixed["technology"].map(lambda t: _classify_tech_group(t) == "Fossil")
            fuel_rows = mixed[fossil_mask].copy()
            om_rows = mixed[~fossil_mask].copy()
            if not fuel_rows.empty:
                fuel_rows["component"] = "variable_con"
                fuel_rows["opex_type"] = "fuel"
                source_by_component["variable_con"] = "cost_var"
                parts.append(fuel_rows)
            if not om_rows.empty:
                om_rows["component"] = "variable_prod"
                om_rows["opex_type"] = "om"
                source_by_component["variable_prod"] = "cost_var"
                parts.append(om_rows)

    if fixed_rows.empty and "fixed_om" not in source_by_component:
        source_by_component["fixed_om"] = ""
    if "investment" not in source_by_component:
        source_by_component["investment"] = ""
    if "variable_prod" not in source_by_component:
        source_by_component["variable_prod"] = ""
    if "variable_con" not in source_by_component:
        source_by_component["variable_con"] = ""

    base_rows = pd.concat(parts, axis=0, ignore_index=True) if parts else pd.DataFrame()
    if not base_rows.empty:
        group_cols = ["location", "technology", "component", "opex_type", "source_variable"]
        base_rows = (
            base_rows.groupby(group_cols, as_index=False)["shock_value_musd"]
            .sum()
            .sort_values("shock_value_musd", ascending=False)
        )
    return base_rows, source_by_component


def _load_mario_mapping_tables(config_dir: Path) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    mario_dir = config_dir / "mario_inputs"
    tech_map = pd.read_csv(mario_dir / "calliope_tech_to_mario_sector.csv")
    capex_split = pd.read_csv(mario_dir / "capex_sector_split.csv")
    opex_split = pd.read_csv(mario_dir / "opex_sector_split.csv")

    for df in (tech_map, capex_split, opex_split):
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].fillna("").astype(str).str.strip()
    if "share" in capex_split.columns:
        capex_split["share"] = pd.to_numeric(capex_split["share"], errors="coerce").fillna(0.0).clip(lower=0.0)
    if "share" in opex_split.columns:
        opex_split["share"] = pd.to_numeric(opex_split["share"], errors="coerce").fillna(0.0).clip(lower=0.0)
    return tech_map, capex_split, opex_split


def _norm_token(value: Any) -> str:
    return str(value or "").strip()


def _norm_key(value: Any) -> str:
    return _norm_token(value).lower()


def _is_wildcard_pattern(value: str) -> bool:
    return any(ch in value for ch in ("*", "?", "[", "]"))


def _is_generic_token(value: str) -> bool:
    return _norm_key(value) in {"", "all", "any", "*"}


def _match_rows_by_tech(df: pd.DataFrame, technology: str, tech_group: str) -> pd.DataFrame:
    if df.empty:
        return df
    work = df.copy()
    if "calliope_tech" not in work.columns:
        return work

    tech = _norm_token(technology)
    work["calliope_tech"] = work["calliope_tech"].fillna("").astype(str).str.strip()
    exact = work[work["calliope_tech"] == tech]
    if not exact.empty:
        return exact

    candidates = work
    if "tech_group" in work.columns:
        tg = _norm_key(tech_group)
        grouped = work[work["tech_group"].astype(str).str.strip().str.lower() == tg]
        candidates = grouped if not grouped.empty else work.iloc[0:0]
    if candidates.empty:
        return candidates

    wildcard = candidates[
        candidates["calliope_tech"].map(
            lambda p: (not _is_generic_token(str(p))) and _is_wildcard_pattern(str(p)) and fnmatch.fnmatchcase(tech, str(p))
        )
    ]
    if not wildcard.empty:
        return wildcard

    generic = candidates[candidates["calliope_tech"].map(lambda x: _is_generic_token(str(x)))]
    if not generic.empty:
        return generic
    return work.iloc[0:0]


def _match_split_rows(
    split_df: pd.DataFrame,
    technology: str,
    tech_group: str,
    region: str,
    opex_type: str = "",
) -> pd.DataFrame:
    if split_df.empty:
        return split_df
    work = split_df.copy()
    region_key = _norm_token(region)
    if "mario_region" in work.columns:
        work["mario_region"] = work["mario_region"].fillna("").astype(str).str.strip()
        exact_region = work[work["mario_region"] == region_key]
        generic_region = work[work["mario_region"].map(lambda x: _is_generic_token(str(x)))]
        work = exact_region if not exact_region.empty else generic_region
    if work.empty:
        return work

    if opex_type and "opex_type" in work.columns:
        wanted = _norm_key(opex_type)
        work["opex_type"] = work["opex_type"].fillna("").astype(str).str.strip()
        exact_type = work[work["opex_type"].astype(str).str.lower() == wanted]
        if exact_type.empty:
            generic_type = work[work["opex_type"].map(lambda x: _is_generic_token(str(x)) or _norm_key(x) == "mixed")]
            work = generic_type if not generic_type.empty else work
        else:
            work = exact_type
    if work.empty:
        return work

    return _match_rows_by_tech(work, technology=technology, tech_group=tech_group)


def _default_sector_for_component(tech_group: str, component: str) -> str:
    tg = _norm_key(tech_group)
    comp = _norm_key(component)
    if comp == "investment":
        if tg == "transmission":
            return "Transmission_and_distribution"
        return "Construction_of_power_assets"
    if tg == "transmission":
        return "Transmission_and_distribution"
    if tg == "demand":
        return "Electricity_and_heat"
    return "Electricity_and_heat"


def _default_channel_for_component(component: str) -> str:
    comp = _norm_key(component)
    if comp == "investment":
        return "capex"
    if comp == "variable_con":
        return "fuel"
    return "opex"


def _build_split_shocks(
    base_rows: pd.DataFrame,
    tech_map: pd.DataFrame,
    capex_split: pd.DataFrame,
    opex_split: pd.DataFrame,
    default_region_by_pool: Dict[str, str],
    run_id: str,
    scenario: str,
    year: int,
    warnings: List[str],
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    investment_records: List[Dict[str, Any]] = []
    operating_records: List[Dict[str, Any]] = []

    if base_rows.empty:
        return pd.DataFrame(), pd.DataFrame()

    for row in base_rows.to_dict(orient="records"):
        technology = str(row.get("technology", "")).strip()
        location = str(row.get("location", "")).strip()
        region = str(row.get("region", "")).strip() or default_region_by_pool.get(str(row.get("pool", "")).strip(), "UNKNOWN")
        shock_value = max(_safe_float(row.get("shock_value_musd"), 0.0), 0.0)
        if shock_value <= 0:
            continue
        component = str(row.get("component", "")).strip().lower()
        opex_type = str(row.get("opex_type", "")).strip().lower()
        tech_group = _classify_tech_group(technology)

        tech_match = _match_rows_by_tech(tech_map, technology=technology, tech_group=tech_group) if not tech_map.empty else pd.DataFrame()
        default_sector = _default_sector_for_component(tech_group=tech_group, component=component)
        default_channel = _default_channel_for_component(component=component)
        if not tech_match.empty:
            candidate_sector = str(tech_match.iloc[0].get("mario_sector", "")).strip()
            candidate_channel = str(tech_match.iloc[0].get("shock_channel", "")).strip().lower()
            if candidate_sector:
                default_sector = candidate_sector
            if component == "investment" and candidate_channel in {"capex"}:
                default_channel = candidate_channel
            elif component != "investment" and candidate_channel in {"opex", "fuel"}:
                default_channel = candidate_channel
        if component == "variable_con":
            default_channel = "fuel"

        if component == "investment":
            split = _match_split_rows(
                capex_split,
                technology=technology,
                tech_group=tech_group,
                region=region,
            )
            if split.empty:
                split_rows = [{"mario_sector": default_sector, "share": 1.0, "opex_type": ""}]
            else:
                total_share = float(split["share"].sum())
                if total_share <= 0:
                    warnings.append(f"CAPEX split has non-positive shares for {technology}/{region}; using default sector.")
                    split_rows = [{"mario_sector": default_sector, "share": 1.0, "opex_type": ""}]
                else:
                    split_rows = [
                        {
                            "mario_sector": str(r.get("mario_sector", "")),
                            "share": float(r.get("share", 0.0)) / total_share,
                            "opex_type": "",
                        }
                        for _, r in split.iterrows()
                    ]
            for srow in split_rows:
                investment_records.append(
                    {
                        "run_id": run_id,
                        "scenario": scenario,
                        "year": int(year),
                        "region": region,
                        "location": location,
                        "technology": technology,
                        "mario_sector": str(srow["mario_sector"]) or default_sector,
                        "shock_channel": "capex",
                        "tech_group": tech_group,
                        "shock_value_musd": shock_value * _safe_float(srow["share"], 0.0),
                    }
                )
            continue

        split = _match_split_rows(
            opex_split,
            technology=technology,
            tech_group=tech_group,
            region=region,
            opex_type=opex_type,
        )
        if split.empty:
            split_rows = [{"mario_sector": default_sector, "share": 1.0, "opex_type": opex_type}]
        else:
            total_share = float(split["share"].sum())
            if total_share <= 0:
                warnings.append(f"OPEX split has non-positive shares for {technology}/{region}; using default sector.")
                split_rows = [{"mario_sector": default_sector, "share": 1.0, "opex_type": opex_type}]
            else:
                split_rows = [
                    {
                        "mario_sector": str(r.get("mario_sector", "")),
                        "share": float(r.get("share", 0.0)) / total_share,
                        "opex_type": str(r.get("opex_type", "")),
                    }
                    for _, r in split.iterrows()
                ]
        for srow in split_rows:
            row_opex_type = _norm_key(srow.get("opex_type", ""))
            row_channel = default_channel
            if row_opex_type == "fuel":
                row_channel = "fuel"
            elif row_opex_type == "om":
                row_channel = "opex"
            operating_records.append(
                {
                    "run_id": run_id,
                    "scenario": scenario,
                    "year": int(year),
                    "region": region,
                    "location": location,
                    "technology": technology,
                    "mario_sector": str(srow["mario_sector"]) or default_sector,
                    "shock_channel": row_channel,
                    "tech_group": tech_group,
                    "shock_value_musd": shock_value * _safe_float(srow["share"], 0.0),
                }
            )

    inv_df = pd.DataFrame(investment_records)
    op_df = pd.DataFrame(operating_records)
    if not inv_df.empty:
        inv_df = inv_df.groupby(
            [
                "run_id",
                "scenario",
                "year",
                "region",
                "location",
                "technology",
                "mario_sector",
                "shock_channel",
                "tech_group",
            ],
            as_index=False,
        )["shock_value_musd"].sum()
    if not op_df.empty:
        op_df = op_df.groupby(
            [
                "run_id",
                "scenario",
                "year",
                "region",
                "location",
                "technology",
                "mario_sector",
                "shock_channel",
                "tech_group",
            ],
            as_index=False,
        )["shock_value_musd"].sum()
    return inv_df, op_df


def _write_exchange_files_for_mario(
    model: Any,
    settings: Settings,
    req: RunRequest,
    run_id: str,
    run_dir: Path,
    summary_diagnostics: Dict[str, Any],
    summary: Dict[str, Any],
    artifact_registry: ArtifactRegistry | None = None,
) -> Tuple[Path, Dict[str, Any], List[str]]:
    warnings: List[str] = []
    exchange_dir = _exchange_dir(run_dir, artifact_registry)
    year = _year_from_profile(settings, req)

    loc_to_region, loc_to_pool, pool_to_region = _load_country_pool_mapping(
        settings.config_dir, settings.calliope_root
    )
    for pool in {"CAPP", "EAPP", "NAPP", "SAPP", "WAPP"}:
        pool_to_region.setdefault(pool, _default_region_for_pool(pool))

    base_rows, source_by_component = _build_component_base_rows(model=model, warnings=warnings)
    if base_rows.empty:
        raise RuntimeError(
            "MARIO exchange builder found no tech-level monetary component rows. "
            "Calliope outputs must include technology/location monetary component rows for bridge execution."
        )
    else:
        base_rows["location"] = base_rows["location"].astype(str).str.strip()
        base_rows["pool"] = base_rows["location"].map(loc_to_pool).fillna("UNKNOWN")
        base_rows["region"] = base_rows["location"].map(loc_to_region)
        base_rows["region"] = base_rows["region"].fillna(base_rows["pool"].map(pool_to_region)).fillna("UNKNOWN")
        unknown_mask = base_rows["region"].astype(str).str.strip().eq("UNKNOWN")
        if bool(unknown_mask.any()):
            unknown_locs = (
                base_rows.loc[unknown_mask, "location"]
                .astype(str)
                .dropna()
                .unique()
                .tolist()
            )
            preview = ", ".join(sorted(unknown_locs)[:12])
            warnings.append(
                "Location-to-region mapping is incomplete; some exchange rows use UNKNOWN region "
                f"({len(unknown_locs)} locations). Sample: {preview}"
            )

    tech_map, capex_split, opex_split = _load_mario_mapping_tables(settings.config_dir)
    inv_df, op_df = _build_split_shocks(
        base_rows=base_rows,
        tech_map=tech_map,
        capex_split=capex_split,
        opex_split=opex_split,
        default_region_by_pool=pool_to_region,
        run_id=run_id,
        scenario=req.energy_scenario_key,
        year=year,
        warnings=warnings,
    )
    if inv_df.empty and op_df.empty:
        raise RuntimeError(
            "MARIO exchange builder produced no investment or operating shocks. "
            "Check technology-to-sector, CAPEX split, and OPEX split input mappings."
        )

    activity_cols = [
        "run_id",
        "scenario",
        "year",
        "region",
        "location",
        "technology",
        "component",
        "opex_type",
        "source_variable",
        "shock_value_musd",
    ]
    activity_path = (
        artifact_registry.path_for("calliope_component_activity_csv")
        if artifact_registry is not None
        else exchange_dir / "calliope_component_activity.csv"
    )
    if base_rows.empty:
        pd.DataFrame(columns=activity_cols).to_csv(activity_path, index=False)
    else:
        activity_df = base_rows.copy()
        activity_df["run_id"] = run_id
        activity_df["scenario"] = req.energy_scenario_key
        activity_df["year"] = int(year)
        for col in activity_cols:
            if col not in activity_df.columns:
                activity_df[col] = ""
        activity_df = activity_df[activity_cols].sort_values("shock_value_musd", ascending=False)
        activity_df.to_csv(activity_path, index=False)

    inv_path = (
        artifact_registry.path_for("investment_shocks_csv")
        if artifact_registry is not None
        else exchange_dir / "investment_shocks.csv"
    )
    op_path = (
        artifact_registry.path_for("operating_shocks_csv")
        if artifact_registry is not None
        else exchange_dir / "operating_shocks.csv"
    )
    if inv_df.empty:
        pd.DataFrame(
            columns=[
                "run_id",
                "scenario",
                "year",
                "region",
                "location",
                "technology",
                "mario_sector",
                "shock_channel",
                "tech_group",
                "shock_value",
                "shock_value_musd",
            ]
        ).to_csv(inv_path, index=False)
    else:
        inv_df = inv_df.copy()
        inv_df["shock_value"] = inv_df["shock_value_musd"]
        inv_df.to_csv(inv_path, index=False)

    if op_df.empty:
        pd.DataFrame(
            columns=[
                "run_id",
                "scenario",
                "year",
                "region",
                "location",
                "technology",
                "mario_sector",
                "shock_channel",
                "tech_group",
                "shock_value",
                "shock_value_musd",
            ]
        ).to_csv(op_path, index=False)
    else:
        op_df = op_df.copy()
        op_df["shock_value"] = op_df["shock_value_musd"]
        op_df.to_csv(op_path, index=False)

    energy_service_balance_path = (
        artifact_registry.path_for("energy_service_balance_csv")
        if artifact_registry is not None
        else exchange_dir / "energy_service_balance.csv"
    )
    _write_energy_service_balance_csv(
        path=energy_service_balance_path,
        run_id=run_id,
        scenario=req.energy_scenario_key,
        summary_diagnostics=summary_diagnostics,
        year=year,
        pool_to_region=pool_to_region,
    )
    prices_df = pd.DataFrame(
        [
            {
                "run_id": run_id,
                "scenario": req.energy_scenario_key,
                "year": int(year),
                "carbon_price_usd_per_tco2": float(req.levers.carbon_price_usd_per_tco2),
                "demand_multiplier": float(req.levers.demand_multiplier),
                "renewables_capex_multiplier": float(req.levers.renewables_capex_multiplier),
                "fossil_fuel_price_multiplier": float(req.levers.fossil_fuel_price_multiplier),
            }
        ]
    )
    prices_and_taxes_path = (
        artifact_registry.path_for("prices_and_taxes_csv")
        if artifact_registry is not None
        else exchange_dir / "prices_and_taxes.csv"
    )
    prices_df.to_csv(prices_and_taxes_path, index=False)

    schema_validation = write_exchange_schema_validation(
        schema_path=settings.config_dir / "mario_inputs" / "exchange_output_schema.csv",
        exchange_dir=exchange_dir,
    )
    if not schema_validation.get("ok"):
        warnings.extend(schema_validation.get("issues", []))

    metadata = {
        "run_id": run_id,
        "scenario": req.energy_scenario_key,
        "year": int(year),
        "development_engine_mode": "mario",
        "bridge_method": "calliope_to_mario_exchange_with_io_runtime",
        "source_variable_by_component": source_by_component,
        "base_component_rows": int(len(base_rows)),
        "shock_rows": {
            "investment": int(len(inv_df)),
            "operating": int(len(op_df)),
        },
        "schema_validation": schema_validation,
    }
    if artifact_registry is not None:
        artifact_registry.register_existing("calliope_component_activity_csv", path=activity_path)
        artifact_registry.register_existing("investment_shocks_csv", path=inv_path)
        artifact_registry.register_existing("operating_shocks_csv", path=op_path)
        artifact_registry.register_existing("energy_service_balance_csv", path=energy_service_balance_path)
        artifact_registry.register_existing("prices_and_taxes_csv", path=prices_and_taxes_path)
        artifact_registry.write_json("exchange_metadata_json", metadata, dumps=json_dumps)
    else:
        (exchange_dir / "metadata.json").write_text(json_dumps(metadata), encoding="utf-8")
    shock_meta = {
        "investment_rows": int(len(inv_df)),
        "operating_rows": int(len(op_df)),
        "total_rows": int(len(inv_df) + len(op_df)),
        "investment_total_musd": float(inv_df["shock_value_musd"].sum()) if not inv_df.empty else 0.0,
        "operating_total_musd": float(op_df["shock_value_musd"].sum()) if not op_df.empty else 0.0,
        "base_component_rows": int(len(base_rows)),
        "source_variable_by_component": source_by_component,
    }
    return exchange_dir, shock_meta, warnings


def _relative_bounds(value: float, rel: float) -> Tuple[float, float]:
    bounded_rel = max(0.0, rel)
    low = max(value * (1.0 - bounded_rel), 0.0)
    high = max(value * (1.0 + bounded_rel), 0.0)
    return low, high


def _build_sector_rows(
    summary_diagnostics: Dict[str, Any],
    total_shock_musd: float,
    jobs_direct: float,
    jobs_total: float,
    gva_total_musd: float,
    household_income_proxy_musd: float,
) -> List[Dict[str, Any]]:
    component_records = ((summary_diagnostics.get("cost_decomposition") or {}).get("component_records") or [])
    sector_totals: Dict[str, float] = {}

    for rec in component_records:
        if not isinstance(rec, dict):
            continue
        if str(rec.get("costs", "")).strip().lower() != "monetary":
            continue
        sector = str(rec.get("tech_group", "Other") or "Other")
        sector_totals[sector] = sector_totals.get(sector, 0.0) + max(_safe_float(rec.get("value"), 0.0), 0.0)

    if not sector_totals:
        sector_totals = {
            "Power construction": max(total_shock_musd * 0.4, 0.0),
            "Fuel supply": max(total_shock_musd * 0.35, 0.0),
            "Grid services": max(total_shock_musd * 0.25, 0.0),
        }

    # Add an explicit import channel for leakage diagnostics.
    import_share = 0.12
    if "Fuel supply" in sector_totals:
        sector_totals["imported_fuels"] = max(sector_totals["Fuel supply"] * import_share, 0.0)
        sector_totals["Fuel supply"] = max(sector_totals["Fuel supply"] * (1.0 - import_share), 0.0)

    total_weight = sum(max(v, 0.0) for v in sector_totals.values())
    if total_weight <= 0:
        total_weight = 1.0

    rows: List[Dict[str, Any]] = []
    for sector, raw_weight in sorted(sector_totals.items(), key=lambda kv: kv[1], reverse=True):
        weight = max(raw_weight, 0.0)
        share = weight / total_weight
        rows.append(
            {
                "supplier_sector": sector,
                "shock_value_musd": total_shock_musd * share,
                "jobs_direct": jobs_direct * share,
                "jobs_total": jobs_total * share,
                "gva_total_musd": gva_total_musd * share,
                "household_income_proxy_musd": household_income_proxy_musd * share,
            }
        )

    return rows


def _build_region_rows(
    summary_diagnostics: Dict[str, Any],
    total_shock_musd: float,
    jobs_direct: float,
    jobs_total: float,
    gva_total_musd: float,
    household_income_proxy_musd: float,
) -> List[Dict[str, Any]]:
    pool_rows = _normalize_pool_rows(summary_diagnostics)
    if not pool_rows:
        pool_rows = [{"pool": "ALL", "demand": 1.0, "unserved": 0.0, "net_imports": 0.0}]

    total_demand = sum(max(_safe_float(row.get("demand"), 0.0), 0.0) for row in pool_rows)
    denom = total_demand if total_demand > 0 else float(len(pool_rows))

    rows: List[Dict[str, Any]] = []
    for row in pool_rows:
        demand = max(_safe_float(row.get("demand"), 0.0), 0.0)
        share = (demand / denom) if total_demand > 0 else (1.0 / denom)
        pool = str(row.get("pool", "UNKNOWN"))
        rows.append(
            {
                "region": pool,
                "power_pool": pool,
                "shock_value_musd": total_shock_musd * share,
                "jobs_direct": jobs_direct * share,
                "jobs_total": jobs_total * share,
                "gva_total_musd": gva_total_musd * share,
                "household_income_proxy_musd": household_income_proxy_musd * share,
            }
        )

    return rows


def _development_total_shock(development: Dict[str, Any]) -> float:
    inputs = development.get("inputs") or {}
    total = _safe_float(inputs.get("total_shock_musd"), 0.0)
    if total > 0:
        return total
    return max(_safe_float(inputs.get("investment_shock_total_musd"), 0.0), 0.0) + max(
        _safe_float(inputs.get("operating_shock_total_musd"), 0.0), 0.0
    )


def _build_direct_development_payload(
    mrio_direct_inputs: Dict[str, Any],
    bridge_development: Dict[str, Any],
) -> Dict[str, Any]:
    bridge_total_shock = _development_total_shock(bridge_development)
    bridge_totals = bridge_development.get("totals") or {}

    ratios: Dict[str, float] = {}
    for key in ("jobs_direct", "jobs_total", "gva_total_musd", "household_income_proxy_musd"):
        ratios[key] = (_safe_float(bridge_totals.get(key), 0.0) / bridge_total_shock) if bridge_total_shock > 0 else 0.0

    rows: List[Dict[str, Any]] = []
    for row in mrio_direct_inputs.get("shock_rows") or []:
        shock = _safe_float(row.get("shock_value_musd"), 0.0)
        rows.append(
            {
                "region": str(row.get("mario_region", "") or "UNKNOWN"),
                "supplier_sector": str(row.get("mario_sector", "") or "UNKNOWN"),
                "shock_category": str(row.get("shock_category", "")),
                "shock_value_musd": shock,
                "jobs_direct": shock * ratios["jobs_direct"],
                "jobs_total": shock * ratios["jobs_total"],
                "gva_total_musd": shock * ratios["gva_total_musd"],
                "household_income_proxy_musd": shock * ratios["household_income_proxy_musd"],
                "method": str(row.get("method", "")),
                "notes": str(row.get("notes", "")),
            }
        )

    totals = {
        "jobs_direct": sum(_safe_float(row.get("jobs_direct"), 0.0) for row in rows),
        "jobs_total": sum(_safe_float(row.get("jobs_total"), 0.0) for row in rows),
        "gva_total_musd": sum(_safe_float(row.get("gva_total_musd"), 0.0) for row in rows),
        "household_income_proxy_musd": sum(
            _safe_float(row.get("household_income_proxy_musd"), 0.0) for row in rows
        ),
    }
    by_region: Dict[str, Dict[str, Any]] = {}
    by_sector: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        region = str(row.get("region", "UNKNOWN"))
        sector = str(row.get("supplier_sector", "UNKNOWN"))
        by_region.setdefault(region, {"region": region, "shock_value_musd": 0.0, **{k: 0.0 for k in totals}})
        by_sector.setdefault(sector, {"supplier_sector": sector, "shock_value_musd": 0.0, **{k: 0.0 for k in totals}})
        for target in (by_region[region], by_sector[sector]):
            target["shock_value_musd"] += _safe_float(row.get("shock_value_musd"), 0.0)
            for key in totals:
                target[key] += _safe_float(row.get(key), 0.0)

    return {
        "method": str(mrio_direct_inputs.get("method", "mrio_direct_heuristic")),
        "scenario_id": str(mrio_direct_inputs.get("scenario_id", "")),
        "target_year": int(_safe_float(mrio_direct_inputs.get("target_year"), 0.0)),
        "geography_code": str(mrio_direct_inputs.get("geography_code", "")),
        "inputs": mrio_direct_inputs,
        "totals": totals,
        "by_region": {"records": list(by_region.values())},
        "by_supplier_sector": {"records": list(by_sector.values())},
        "detail_records": rows,
        "diagnostics": {
            **(mrio_direct_inputs.get("diagnostics") or {}),
            "effect_estimation": "direct_mrio_effects_scaled_by_bridge_output_intensity_ratios",
            "bridge_total_reference_musd": bridge_total_shock,
        },
    }


def _attach_mrio_direct_layer(
    *,
    development: Dict[str, Any],
    coupling_manifest: Dict[str, Any],
    run_dir: Path,
    scenario_package: Dict[str, Any],
    development_model_config: Dict[str, Any],
    artifact_registry: ArtifactRegistry | None = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    warnings: List[str] = []
    bridge_payload = {
        "method": development.get("method", ""),
        "inputs": development.get("inputs") or {},
        "totals": development.get("totals") or {},
        "uncertainty": development.get("uncertainty") or {},
        "by_region": development.get("by_region") or {"records": []},
        "by_supplier_sector": development.get("by_supplier_sector") or {"records": []},
        "by_region_supplier": development.get("by_region_supplier") or {"records": []},
        "diagnostics": development.get("diagnostics") or {},
        "metadata": development.get("metadata") or {},
    }
    bridge_total = _development_total_shock(development)
    mrio_direct_inputs = build_mrio_direct_inputs(
        scenario_package=scenario_package,
        bridge_total_shock_musd=bridge_total,
        direct_config=(development_model_config.get("mario_direct") or {}),
    )
    mrio_direct = _build_direct_development_payload(mrio_direct_inputs, bridge_payload)
    selected_totals = dict(bridge_payload.get("totals") or {})
    combined_totals = dict(selected_totals)
    for key, value in (mrio_direct.get("totals") or {}).items():
        combined_totals[key] = _safe_float(combined_totals.get(key), 0.0) + _safe_float(value, 0.0)

    overlap_diagnostics = {
        "policy": "bridge_authoritative_for_headline_totals",
        "merge_logic": "bridge_authoritative_overlap_handling",
        "message": (
            "Bridge-derived Calliope outputs and structured MRIO-direct heuristic outputs are both retained. "
            "Headline selected_totals use bridge-derived values when channels overlap; MRIO-direct effects remain "
            "available for source-channel comparison."
        ),
        "bridge_rows": int(coupling_manifest.get("shock_record_count") or 0),
        "mrio_direct_rows": int((mrio_direct_inputs.get("diagnostics") or {}).get("shock_row_count") or 0),
        "overlap_default_source": "bridge",
    }
    development["bridge"] = bridge_payload
    development["mrio_direct"] = mrio_direct
    development["selected_totals"] = selected_totals
    development["combined_totals"] = combined_totals
    development["overlap_diagnostics"] = overlap_diagnostics

    coupling_manifest.update(
        {
            "integration_architecture": "bridge_plus_mrio_direct",
            "energy_scenario_key": scenario_package.get("energy_scenario_key", ""),
            "mrio_scenario_id": scenario_package.get("mrio_scenario_id", ""),
            "target_year": int(_safe_float(scenario_package.get("target_year"), 0.0)),
            "mrio_direct_method": mrio_direct.get("method", ""),
            "mrio_direct_heuristic": True,
            "mrio_direct_rows": int(overlap_diagnostics["mrio_direct_rows"]),
            "mrio_direct_net_shock_musd": _safe_float(
                ((mrio_direct_inputs.get("totals") or {}).get("net_direct_shock_musd")),
                0.0,
            ),
            "selected_totals_source": "bridge",
            "overlap_policy": "bridge_authoritative_for_headline_totals",
            "report_scenario_provenance": (
                (scenario_package.get("mrio_direct") or {}).get("report_source") or {}
            ),
            "geography_alignment": scenario_package.get("geography_alignment") or {},
        }
    )
    write_scenario_artifacts(
        run_dir,
        scenario_package,
        mrio_direct_inputs=mrio_direct_inputs,
    )
    warnings.append(
        "MRIO-direct heuristic outputs are retained separately; bridge-derived values remain authoritative for headline totals."
    )
    return development, coupling_manifest, warnings


def _build_mario_development_outputs(
    settings: Settings,
    model: Any,
    summary: Dict[str, Any],
    req: RunRequest,
    run_id: str,
    run_dir: Path,
    development_model_config: Dict[str, Any],
    mapping_quality: Dict[str, Any],
    scenario_package: Dict[str, Any],
    artifact_registry: ArtifactRegistry | None = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    warnings: List[str] = []
    start = time.time()
    summary_diagnostics = summary.get("summary_diagnostics") or {}

    exchange_dir, shock_meta, exchange_warnings = _write_exchange_files_for_mario(
        model=model,
        settings=settings,
        req=req,
        run_id=run_id,
        run_dir=run_dir,
        summary_diagnostics=summary_diagnostics,
        summary=summary,
        artifact_registry=artifact_registry,
    )
    warnings.extend(exchange_warnings)

    mario_cfg = (development_model_config.get("mario") or {})
    uncertainty_cfg = mario_cfg.get("uncertainty_relative_bounds") or {
        "jobs_direct": 0.12,
        "jobs_total": 0.12,
        "gva_total_musd": 0.12,
        "household_income_proxy_musd": 0.12,
    }
    year = _year_from_profile(settings, req)
    development, runtime_meta, runtime_warnings = run_mario_io_runtime(
        exchange_dir=exchange_dir,
        config_dir=settings.config_dir,
        run_id=run_id,
        scenario=req.energy_scenario_key,
        year=year,
        uncertainty_relative=uncertainty_cfg if isinstance(uncertainty_cfg, dict) else {},
    )
    warnings.extend(runtime_warnings)
    elapsed = max(time.time() - start, 0.0)
    if elapsed > float(settings.mario_timeout_seconds):
        raise TimeoutError(
            f"MARIO runtime exceeded timeout ({elapsed:.2f}s > {settings.mario_timeout_seconds:.2f}s)."
        )
    mario_health = mario_inputs_health(settings.config_dir)
    coupling_manifest = {
        "run_id": run_id,
        "scenario": req.energy_scenario_key,
        "development_engine_mode": "mario",
        "bridge_method": str(runtime_meta.get("bridge_method", "calliope_to_mario_exchange_with_io_runtime")),
        "mapping_coverage_share": _safe_float(mapping_quality.get("mapping_coverage_share"), 0.0),
        "unmapped_mapping_share": _safe_float(mapping_quality.get("unmapped_mapping_share"), 1.0),
        "unmapped_mapping_count": int(_safe_float(mapping_quality.get("unmapped_mapping_count"), 0.0)),
        "shock_record_count": int(_safe_float(runtime_meta.get("shock_record_count"), shock_meta.get("total_rows", 0))),
        "shock_balance_gap_share": 0.0,
        "warnings_count": len(warnings),
        "mapping_required_tech_count": int(_safe_float(mapping_quality.get("mapping_required_tech_count"), 0.0)),
        "mapping_mapped_tech_count": int(_safe_float(mapping_quality.get("mapping_mapped_tech_count"), 0.0)),
        "capex_split_bad_groups": int(_safe_float(mapping_quality.get("capex_split_bad_groups"), 0.0)),
        "opex_split_bad_groups": int(_safe_float(mapping_quality.get("opex_split_bad_groups"), 0.0)),
        "mario_runtime_executed": bool(runtime_meta.get("mario_runtime_executed", True)),
        "mario_runtime_error": str(runtime_meta.get("mario_runtime_error", "")),
        "mario_runtime_seconds": float(elapsed),
        "mario_runner_source": str(runtime_meta.get("mario_runner_source", "")),
        "strict_validation": bool(getattr(req, "strict_validation", False)),
        "allow_placeholder_data": bool(getattr(req, "allow_placeholder_data", False)),
        "placeholder_input_files": mario_health.get("placeholder_files") or [],
        "placeholder_input_row_counts": mario_health.get("placeholder_row_counts") or {},
        "placeholder_input_row_count": int(
            sum(int(v or 0) for v in (mario_health.get("placeholder_row_counts") or {}).values())
        ),
    }

    mario_runner_log_path = (
        artifact_registry.path_for("mario_runner_log")
        if artifact_registry is not None
        else exchange_dir / "mario_runner.log"
    )
    write_runtime_log(
        mario_runner_log_path,
        {
            "run_id": run_id,
            "scenario": req.energy_scenario_key,
            "elapsed_seconds": elapsed,
            "development_engine_mode": "mario",
            "runner_source": coupling_manifest["mario_runner_source"],
            "shock_meta": shock_meta,
            "warnings_count": len(warnings),
        },
    )
    if artifact_registry is not None:
        artifact_registry.register_existing("mario_runner_log", path=mario_runner_log_path)
        _write_json(artifact_registry.layout.work_dir / "development_impacts_mario.json", development)
    else:
        _write_json(exchange_dir / "development_impacts_mario.json", development)

    development, coupling_manifest, direct_warnings = _attach_mrio_direct_layer(
        development=development,
        coupling_manifest=coupling_manifest,
        run_dir=run_dir,
        scenario_package=scenario_package,
        development_model_config=development_model_config,
        artifact_registry=artifact_registry,
    )
    warnings.extend(direct_warnings)
    return development, coupling_manifest, warnings


def _build_development_outputs(
    settings: Settings,
    model: Any,
    summary: Dict[str, Any],
    req: RunRequest,
    run_id: str,
    run_dir: Path,
    development_model_config: Dict[str, Any],
    mapping_quality: Dict[str, Any],
    scenario_package: Dict[str, Any],
    artifact_registry: ArtifactRegistry | None = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    return get_development_model_module(settings.development_engine).run(
        settings=settings,
        model=model,
        summary=summary,
        req=req,
        run_id=run_id,
        run_dir=run_dir,
        development_model_config=development_model_config,
        mapping_quality=mapping_quality,
        scenario_package=scenario_package,
        artifact_registry=artifact_registry,
    )


def run_model_synchronously(
    settings: Settings,
    req: RunRequest,
    progress_callback: Callable[[str, float, str], None] | None = None,
    cancel_requested: Callable[[], bool] | None = None,
    request_bundle: Dict[str, Any] | None = None,
) -> Tuple[str, dict, List[str], Path]:
    """Run one model package synchronously through the selected pipeline.

    The backend/runtime boundary should call this model-neutral entrypoint.
    It delegates to the pipeline selected by this package; the current package
    uses the EDIM pipeline.
    """
    from .edim_pipeline import run_edim_pipeline

    return run_edim_pipeline(
        settings=settings,
        req=req,
        progress_callback=progress_callback,
        cancel_requested=cancel_requested,
        request_bundle=request_bundle,
    )


def json_dumps(obj: Any) -> str:
    import orjson

    return orjson.dumps(obj, option=orjson.OPT_INDENT_2).decode("utf-8")


def deep_merge(a: dict, b: dict) -> dict:
    """
    Recursively merge dict b into dict a (without mutating inputs).
    """
    out = dict(a)
    for k, v in b.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out
