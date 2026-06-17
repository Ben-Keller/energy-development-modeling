from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .base import CancelCallback, EnergyModelModule, ModelModuleInfo, ProgressCallback


class CalliopeEnergyModule(EnergyModelModule):
    info = ModelModuleInfo(
        module_id="calliope",
        kind="energy",
        label="Calliope energy system model",
        implementation_status="ready",
        description="Executable Calliope-Africa energy optimization module.",
        asset_root="model_runtime/model_modules/calliope/Calliope-Africa-main",
        supported_engines=["calliope"],
        stages=["energy_input_prepare", "build_model", "solve_energy", "write_artifacts", "build_summary"],
    )

    def scenario_catalog(self, settings: Any) -> Dict[str, Any]:
        from ..core.scenarios import build_scenario_list

        overrides_path = settings.calliope_root / "overrides.yaml"
        metadata_path = settings.config_dir / "scenario_metadata.csv"
        scenarios = [row.model_dump() for row in build_scenario_list(overrides_path, metadata_path)]
        default_key = ""
        if scenarios:
            keys = {str(row.get("key", "")) for row in scenarios}
            default_key = "new_links" if "new_links" in keys else str(scenarios[0].get("key", ""))
        options = [
            {
                "value": str(row.get("key", "")),
                "label": str(row.get("title") or row.get("key") or ""),
                "description": str(row.get("description") or ""),
                "metadata": row,
            }
            for row in scenarios
        ]
        return {
            "module_id": self.info.module_id,
            "kind": self.info.kind,
            "label": self.info.label,
            "implementation_status": self.info.implementation_status,
            "scenario_channels": [
                {
                    "channel_id": "energy_pathway",
                    "label": "Energy pathway",
                    "config_key": "scenario.energy_scenario_key",
                    "value_field": "energy_scenario_key",
                    "required": True,
                    "options": options,
                    "default": default_key,
                },
                {
                    "channel_id": "energy_model_engine",
                    "label": "Energy model engine",
                    "config_key": "energy_model_engine",
                    "value_field": "energy_model_engine",
                    "required": True,
                    "options": [
                        {
                            "value": engine,
                            "label": engine.title(),
                            "runtime_status": self.info.implementation_status,
                        }
                        for engine in self.info.supported_engines
                    ],
                    "default": self.info.supported_engines[0] if self.info.supported_engines else "",
                },
            ],
            "defaults": {
                "energy_model_engine": self.info.supported_engines[0] if self.info.supported_engines else "",
                "energy_scenario_key": default_key,
            },
        }

    def resolve_model_definition(self, settings: Any) -> Path:
        from ..core import runner as core_runner

        return core_runner._resolve_model_yaml(settings)

    def load_technology_library(self, settings: Any) -> Dict[str, Any]:
        from ..core import runner as core_runner

        return core_runner._resolve_tech_library(settings)

    def build_runtime_override(
        self,
        *,
        settings: Any,
        req: Any,
        lever_patch: Dict[str, Any],
        solver_name: str,
    ) -> Dict[str, Any]:
        from ..core import runner as core_runner

        return core_runner._build_runtime_override_patch(
            settings=settings,
            req=req,
            lever_patch=lever_patch,
            solver_name=solver_name,
        )

    def solve(
        self,
        *,
        settings: Any,
        req: Any,
        model_definition: Path,
        override_patch: Dict[str, Any],
        warnings: List[str],
        progress_callback: ProgressCallback,
        cancel_requested: CancelCallback,
    ) -> Any:
        from ..core import runner as core_runner

        calliope = core_runner._get_calliope_module()
        core_runner._patch_calliope_appsi_solver_factory()
        core_runner._patch_calliope_highs_warmstart()

        with core_runner._pushd(settings.calliope_root):
            model = core_runner._build_model_with_overrides(
                calliope.Model,
                model_definition,
                req.energy_scenario_key,
                override_patch,
            )
            core_runner._apply_demand_multiplier(model, req.levers.demand_multiplier, warnings)
            core_runner._check_cancel(cancel_requested)
            core_runner._emit_progress(
                progress_callback,
                "solve_energy",
                0.55,
                "Solving Calliope energy optimization problem",
            )
            model.run()
        core_runner._check_cancel(cancel_requested)

        health = core_runner._results_health(model)
        if int(health.get("var_count", 0)) <= 0:
            term = str(health.get("termination_condition", "")).strip() or "unknown"
            if term.lower() in {"maxtimelimit", "timelimit", "max_time_limit"}:
                raise RuntimeError(
                    "Calliope returned no result variables because the solve hit a time limit "
                    f"(termination_condition={term}). Increase EDIM_DEV_SOLVER_TIME_LIMIT_SECONDS "
                    "or run a lighter dev scenario."
                )
            raise RuntimeError(
                "Calliope returned no result variables; cannot build summary/development outputs "
                f"(termination_condition={term})."
            )
        return model
