from __future__ import annotations

"""EDIM-specific model stages built on the generic orchestration layer.

The backend calls the model runtime as a black box. Within that black box, this
module owns the EDIM phase sequence and delegates actual model work to module
adapters such as Calliope and MRIO. The generic stage runner is kept in
``orchestration.py`` so future model architectures can reuse the same execution
shell without inheriting EDIM-specific assumptions.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from ..contracts import ArtifactRegistry
from ..modules import get_development_model_module, get_energy_model_module, model_module_catalog
from .integrated import build_integrated_results
from .levers import build_lever_override_patch, load_lever_mappings
from .orchestration import ModelStage, StageOrchestrator
from .scenario_package import build_scenario_package, write_scenario_artifacts
from .schemas import RunRequest
from .settings import Settings
from .summarize import build_summary_core, build_summary_diagnostics


@dataclass
class EdimPipelineContext:
    settings: Settings
    request: RunRequest
    progress_callback: Callable[[str, float, str], None] | None = None
    cancel_requested: Callable[[], bool] | None = None
    request_bundle: Dict[str, Any] | None = None

    run_id: str = ""
    run_dir: Path | None = None
    run_profile: str = ""
    artifact_registry: ArtifactRegistry | None = None
    model_architecture_id: str = "energy-development"

    energy_module: Any = None
    model_yaml: Path | None = None
    tech_library: Dict[str, Any] = field(default_factory=dict)
    development_model_config: Dict[str, Any] = field(default_factory=dict)
    mapping_quality: Dict[str, Any] = field(default_factory=dict)
    scenario_package: Dict[str, Any] = field(default_factory=dict)

    warnings: List[str] = field(default_factory=list)
    lever_patch: Dict[str, Any] = field(default_factory=dict)
    override_patch: Dict[str, Any] = field(default_factory=dict)
    model: Any = None
    summary: Dict[str, Any] = field(default_factory=dict)
    development_impacts: Dict[str, Any] = field(default_factory=dict)
    coupling_manifest: Dict[str, Any] = field(default_factory=dict)
    integrated: Dict[str, Any] = field(default_factory=dict)


def run_edim_pipeline(
    settings: Settings,
    req: RunRequest,
    progress_callback: Callable[[str, float, str], None] | None = None,
    cancel_requested: Callable[[], bool] | None = None,
    request_bundle: Dict[str, Any] | None = None,
) -> Tuple[str, dict, List[str], Path]:
    """Execute one EDIM run through explicit generic/model-specific boundaries."""

    from . import runner as core_runner

    ctx = EdimPipelineContext(
        settings=settings,
        request=req,
        progress_callback=progress_callback,
        cancel_requested=cancel_requested,
        request_bundle=request_bundle,
    )
    orchestrator = StageOrchestrator[EdimPipelineContext](
        emit_progress=lambda stage, progress, message: core_runner._emit_progress(
            progress_callback,
            stage,
            progress,
            message,
        ),
        check_cancel=lambda: core_runner._check_cancel(cancel_requested),
    )

    orchestrator.run(ctx, _common_stages())
    if ctx.model_architecture_id == "energy-only":
        orchestrator.run(ctx, _energy_only_stages())
    else:
        orchestrator.run(ctx, _energy_development_stages())
    return _pipeline_result(ctx)


def _common_stages() -> List[ModelStage[EdimPipelineContext]]:
    return [
        ModelStage(
            stage_id="environment_setup",
            label="Prepare run envelope",
            handler=_prepare_run,
        ),
        ModelStage(
            stage_id="scenario_prepare",
            label="Build integrated scenario package",
            start_progress=0.06,
            start_message="Building integrated scenario package",
            handler=_prepare_scenario,
        ),
        ModelStage(
            stage_id="energy_input_prepare",
            label="Resolve energy inputs",
            start_progress=0.08,
            start_message="Resolving model tech library and lever mappings",
            handler=_prepare_energy_inputs,
        ),
        ModelStage(
            stage_id="build_model",
            label="Build and solve energy model",
            handler=_solve_energy_model,
        ),
        ModelStage(
            stage_id="write_artifacts",
            label="Write energy artifacts",
            start_progress=0.78,
            start_message="Writing CSV artifacts",
            handler=_write_energy_artifacts,
        ),
        ModelStage(
            stage_id="build_summary",
            label="Build energy summary",
            start_progress=0.86,
            start_message="Building summary payload",
            handler=_build_energy_summary,
        ),
    ]


def _energy_only_stages() -> List[ModelStage[EdimPipelineContext]]:
    return [
        ModelStage(
            stage_id="build_integrated",
            label="Assemble energy-only results",
            start_progress=0.96,
            start_message="Assembling energy-only result package",
            handler=_finalize_energy_only,
        ),
        ModelStage(
            stage_id="complete",
            label="Complete run",
            start_progress=1.0,
            start_message="Run completed successfully",
            handler=_noop,
        ),
    ]


def _energy_development_stages() -> List[ModelStage[EdimPipelineContext]]:
    return [
        ModelStage(
            stage_id="bridge_prepare",
            label="Prepare bridge outputs",
            start_progress=0.90,
            start_message="Preparing Calliope-to-MRIO bridge outputs",
            handler=_noop,
        ),
        ModelStage(
            stage_id="mrio_direct_prepare",
            label="Prepare MRIO-direct inputs",
            start_progress=0.92,
            start_message="Preparing structured MRIO-direct inputs",
            handler=_noop,
        ),
        ModelStage(
            stage_id="development",
            label="Run development model",
            start_progress=0.94,
            start_message="Running integrated development layer",
            handler=_run_development_model,
        ),
        ModelStage(
            stage_id="build_integrated",
            label="Assemble integrated results",
            start_progress=0.96,
            start_message="Assembling integrated result package",
            handler=_finalize_energy_development,
        ),
        ModelStage(
            stage_id="complete",
            label="Complete run",
            start_progress=1.0,
            start_message="Run completed successfully",
            handler=_noop,
        ),
    ]


def _prepare_run(ctx: EdimPipelineContext) -> None:
    from . import runner as core_runner

    run_id, run_dir, run_profile, artifact_registry = core_runner._prepare_generic_model_run(
        settings=ctx.settings,
        req=ctx.request,
        request_bundle=ctx.request_bundle,
        progress_callback=ctx.progress_callback,
        cancel_requested=ctx.cancel_requested,
    )
    ctx.run_id = run_id
    ctx.run_dir = run_dir
    ctx.run_profile = run_profile
    ctx.artifact_registry = artifact_registry
    ctx.energy_module = get_energy_model_module(ctx.request.energy_model_engine)
    ctx.model_yaml = ctx.energy_module.resolve_model_definition(ctx.settings)


def _prepare_scenario(ctx: EdimPipelineContext) -> None:
    from . import runner as core_runner

    ctx.scenario_package = build_scenario_package(
        config_dir=ctx.settings.config_dir,
        calliope_root=ctx.settings.calliope_root,
        energy_model_engine=ctx.request.energy_model_engine,
        energy_scenario_key=ctx.request.energy_scenario_key,
        mrio_scenario_id=ctx.request.mrio_scenario_id,
        target_year=ctx.request.target_year,
        run_profile=ctx.run_profile,
        levers=ctx.request.levers.model_dump(),
        strict_validation=bool(ctx.request.strict_validation),
        allow_placeholder_data=bool(ctx.request.allow_placeholder_data),
    )
    ctx.model_architecture_id = str(
        getattr(ctx.request, "model_architecture_id", "energy-development") or "energy-development"
    )
    ctx.scenario_package["model_architecture_id"] = ctx.model_architecture_id
    ctx.scenario_package["model_architecture"] = {
        "architecture_id": ctx.model_architecture_id,
        "frontend_scope": "energy_and_development"
        if ctx.model_architecture_id != "energy-only"
        else "energy_only",
        "note": "Controls graph layout, result tabs, and visible output artifact families in the frontend.",
    }
    ctx.scenario_package["model_modules"] = {
        "selected_energy_module": ctx.energy_module.info.to_dict(),
        "available_modules": model_module_catalog(),
    }
    core_runner._write_generic_model_input_snapshots(
        artifact_registry=ctx.artifact_registry,
        request_bundle=ctx.request_bundle,
        req=ctx.request,
        run_profile=ctx.run_profile,
        model_architecture_id=ctx.model_architecture_id,
    )
    write_scenario_artifacts(
        ctx.run_dir,
        ctx.scenario_package,
        artifact_registry=ctx.artifact_registry,
    )


def _prepare_energy_inputs(ctx: EdimPipelineContext) -> None:
    from . import runner as core_runner

    lever_mappings = load_lever_mappings(ctx.settings.config_dir)
    ctx.tech_library = ctx.energy_module.load_technology_library(ctx.settings)
    ctx.development_model_config = core_runner._load_development_model_config(ctx.settings.config_dir)
    ctx.mapping_quality, mapping_warnings = core_runner._evaluate_mario_mapping_quality(
        ctx.settings.config_dir,
        ctx.tech_library,
    )
    strict_issues = core_runner._strict_validation_issues(
        settings=ctx.settings,
        energy_scenario_key=ctx.request.energy_scenario_key,
        run_profile=ctx.run_profile,
        strict_validation=getattr(ctx.request, "strict_validation", None),
        allow_placeholder_data=bool(getattr(ctx.request, "allow_placeholder_data", False)),
        mapping_quality=ctx.mapping_quality,
    )
    if strict_issues:
        raise ValueError(strict_issues[0])

    ctx.lever_patch, lever_warnings = build_lever_override_patch(
        ctx.request.levers,
        lever_mappings,
        ctx.tech_library,
    )
    solver_name, solver_warnings = core_runner._resolve_solver_for_runtime(ctx.settings.solver)
    ctx.override_patch = ctx.energy_module.build_runtime_override(
        settings=ctx.settings,
        req=ctx.request,
        lever_patch=ctx.lever_patch,
        solver_name=solver_name,
    )
    core_runner._write_yaml(ctx.artifact_registry.path_for("ui_override_patch_yaml"), ctx.override_patch)
    ctx.artifact_registry.register_existing("ui_override_patch_yaml")
    ctx.warnings = list(lever_warnings) + list(solver_warnings) + list(mapping_warnings)


def _solve_energy_model(ctx: EdimPipelineContext) -> None:
    from . import runner as core_runner

    core_runner._emit_progress(
        ctx.progress_callback,
        "build_model",
        0.15,
        f"Building {ctx.energy_module.info.label}",
    )
    ctx.model = ctx.energy_module.solve(
        settings=ctx.settings,
        req=ctx.request,
        model_definition=ctx.model_yaml,
        override_patch=ctx.override_patch,
        warnings=ctx.warnings,
        progress_callback=ctx.progress_callback,
        cancel_requested=ctx.cancel_requested,
    )


def _write_energy_artifacts(ctx: EdimPipelineContext) -> None:
    from . import runner as core_runner

    csv_path = ctx.artifact_registry.path_for("results_csv")
    csv_rows = core_runner._write_results_csv(csv_path, ctx.model)
    if csv_rows <= 0:
        ctx.warnings.append("Results CSV export produced no rows.")
    ctx.artifact_registry.register_existing("results_csv", path=csv_path)


def _build_energy_summary(ctx: EdimPipelineContext) -> None:
    from . import runner as core_runner

    ctx.summary = build_summary_core(
        ctx.model,
        run_id=ctx.run_id,
        scenario=ctx.request.energy_scenario_key,
        fast_dev_mode=ctx.run_profile != "full",
        run_profile=ctx.run_profile,
        warnings=ctx.warnings,
        max_generation_techs=ctx.settings.summary_max_generation_techs,
        max_generation_timesteps=ctx.settings.summary_max_generation_timesteps,
        max_category_rows=ctx.settings.summary_max_category_rows,
    )
    ctx.summary.pop("scenario", None)
    ctx.summary.pop("fast_dev_mode", None)
    ctx.summary["energy_scenario_key"] = ctx.request.energy_scenario_key
    ctx.summary["model_architecture_id"] = ctx.model_architecture_id
    ctx.summary["mrio_scenario_id"] = ctx.request.mrio_scenario_id
    ctx.summary["target_year"] = int(ctx.request.target_year)
    ctx.summary["run_profile"] = ctx.run_profile
    ctx.summary["scenario_package"] = ctx.scenario_package
    ctx.summary["summary_diagnostics"] = build_summary_diagnostics(
        model=ctx.model,
        run_id=ctx.run_id,
        scenario=ctx.request.energy_scenario_key,
        calliope_root=ctx.settings.calliope_root,
        tech_library=ctx.tech_library,
        max_rows=ctx.settings.summary_diagnostics_max_rows,
        warnings=ctx.summary["warnings"],
    )
    if isinstance(ctx.request_bundle, dict) and isinstance(ctx.request_bundle.get("provenance"), dict):
        ctx.summary["run_provenance"] = ctx.request_bundle["provenance"]


def _finalize_energy_only(ctx: EdimPipelineContext) -> None:
    from . import runner as core_runner

    ctx.coupling_manifest = {
        "schema_version": "edim_coupling_manifest",
        "model_architecture_id": ctx.model_architecture_id,
        "development_engine_mode": "skipped_energy_only",
        "integration_architecture": "energy_only",
        "mario_runtime_executed": False,
        "mario_runtime_error": "",
        "mario_runtime_seconds": 0.0,
        "mario_runner_source": "not_applicable",
        "mapping_coverage_share": 1.0,
        "unmapped_mapping_share": 0.0,
        "strict_validation": bool(ctx.request.strict_validation),
        "allow_placeholder_data": bool(ctx.request.allow_placeholder_data),
        "placeholder_input_files": [],
        "placeholder_input_row_count": 0,
        "mrio_direct_method": "",
        "mrio_direct_heuristic": False,
        "selected_totals_source": "not_applicable",
        "overlap_policy": "not_applicable",
        "warnings": [
            "Energy-only architecture selected: bridge, MRIO-direct, and development runtime stages were skipped."
        ],
    }
    ctx.development_impacts = {
        "schema_version": "edim_development_impacts",
        "status": "skipped",
        "reason": "energy_only_architecture",
        "message": "Energy-only architecture selected; development/MRIO outputs were not produced.",
        "inputs": {},
        "bridge": {},
        "mrio_direct": {},
        "selected_totals": {},
        "combined_totals": {},
        "overlap_diagnostics": {"status": "not_applicable"},
        "by_region": {"records": []},
        "by_supplier_sector": {"records": []},
        "uncertainty": {},
    }
    ctx.summary["development_impacts"] = ctx.development_impacts
    ctx.summary["coupling_manifest"] = ctx.coupling_manifest
    ctx.summary.setdefault("warnings", []).extend(ctx.coupling_manifest["warnings"])
    ctx.integrated = build_integrated_results(
        ctx.summary,
        coupling_manifest=ctx.coupling_manifest,
        config_dir=ctx.settings.config_dir,
        lever_values=ctx.request.levers.model_dump(),
        run_year=core_runner._year_from_profile(ctx.settings, ctx.request),
    )
    _attach_integrated_outputs(ctx)
    ctx.artifact_registry.write_json("integrated_results_json", ctx.integrated, dumps=core_runner.json_dumps)
    core_runner._finalize_declared_run_artifacts(
        run_id=ctx.run_id,
        run_dir=ctx.run_dir,
        summary=ctx.summary,
        integrated=ctx.integrated,
        artifact_registry=ctx.artifact_registry,
        include_exchange_bundle=False,
    )


def _run_development_model(ctx: EdimPipelineContext) -> None:
    development_module = get_development_model_module(ctx.settings.development_engine)
    ctx.summary.setdefault("model_modules", {})["development_module"] = development_module.info.to_dict()
    ctx.development_impacts, ctx.coupling_manifest, development_warnings = development_module.run(
        settings=ctx.settings,
        model=ctx.model,
        summary=ctx.summary,
        req=ctx.request,
        run_id=ctx.run_id,
        run_dir=ctx.run_dir,
        development_model_config=ctx.development_model_config,
        mapping_quality=ctx.mapping_quality,
        scenario_package=ctx.scenario_package,
        artifact_registry=ctx.artifact_registry,
    )
    ctx.artifact_registry.prune_consumed_by("development")
    ctx.summary["development_impacts"] = ctx.development_impacts
    ctx.summary["coupling_manifest"] = ctx.coupling_manifest
    if development_warnings:
        ctx.summary["warnings"].extend(development_warnings)


def _finalize_energy_development(ctx: EdimPipelineContext) -> None:
    from . import runner as core_runner

    ctx.integrated = build_integrated_results(
        ctx.summary,
        coupling_manifest=ctx.coupling_manifest,
        config_dir=ctx.settings.config_dir,
        lever_values=ctx.request.levers.model_dump(),
        run_year=core_runner._year_from_profile(ctx.settings, ctx.request),
    )
    _attach_integrated_outputs(ctx)
    ctx.warnings = list(ctx.summary.get("warnings", ctx.warnings))
    ctx.artifact_registry.write_json("development_impacts_json", ctx.development_impacts, dumps=core_runner.json_dumps)
    ctx.artifact_registry.write_json("coupling_manifest_json", ctx.coupling_manifest, dumps=core_runner.json_dumps)
    ctx.artifact_registry.write_json("integrated_results_json", ctx.integrated, dumps=core_runner.json_dumps)
    core_runner._finalize_declared_run_artifacts(
        run_id=ctx.run_id,
        run_dir=ctx.run_dir,
        summary=ctx.summary,
        integrated=ctx.integrated,
        artifact_registry=ctx.artifact_registry,
        include_exchange_bundle=True,
    )


def _attach_integrated_outputs(ctx: EdimPipelineContext) -> None:
    ctx.summary["scenario_assumptions"] = ctx.integrated.get("scenario_assumptions") or {}
    ctx.summary["development_indicators"] = ctx.integrated.get("development_indicators") or {}
    ctx.summary["integrated_results"] = ctx.integrated


def _pipeline_result(ctx: EdimPipelineContext) -> Tuple[str, dict, List[str], Path]:
    warnings = ctx.summary.get("warnings", ctx.warnings) if ctx.summary else ctx.warnings
    return ctx.run_id, ctx.summary, list(warnings), ctx.run_dir


def _noop(ctx: EdimPipelineContext) -> None:
    return None
