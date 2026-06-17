from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .base import CancelCallback, EnergyModelModule, ModelModuleError, ModelModuleInfo, ProgressCallback


class OsemosysEnergyModule(EnergyModelModule):
    info = ModelModuleInfo(
        module_id="osemosys",
        kind="energy",
        label="OSeMOSYS energy system model",
        implementation_status="planned",
        description="Placeholder module boundary for a future OSeMOSYS energy-model implementation.",
        asset_root="model_runtime/model_modules/osemosys",
        supported_engines=[],
        stages=["energy_input_prepare", "build_model", "solve_energy", "write_artifacts", "build_summary"],
    )

    def scenario_catalog(self, settings: Any) -> Dict[str, Any]:
        return {
            "module_id": self.info.module_id,
            "kind": self.info.kind,
            "label": self.info.label,
            "implementation_status": self.info.implementation_status,
            "scenario_channels": [
                {
                    "channel_id": "energy_model_engine",
                    "label": "Energy model engine",
                    "config_key": "energy_model_engine",
                    "value_field": "energy_model_engine",
                    "required": True,
                    "options": [
                        {
                            "value": "osemosys",
                            "label": "OSeMOSYS",
                            "runtime_status": self.info.implementation_status,
                            "disabled": True,
                            "description": "Registered for architecture planning; executable runtime is not packaged yet.",
                        }
                    ],
                    "default": "",
                }
            ],
            "defaults": {},
        }

    def _not_available(self) -> None:
        raise ModelModuleError(
            "OSeMOSYS is registered as a planned energy module, but no executable OSeMOSYS runtime is packaged yet."
        )

    def resolve_model_definition(self, settings: Any) -> Path:
        self._not_available()

    def load_technology_library(self, settings: Any) -> Dict[str, Any]:
        self._not_available()

    def build_runtime_override(
        self,
        *,
        settings: Any,
        req: Any,
        lever_patch: Dict[str, Any],
        solver_name: str,
    ) -> Dict[str, Any]:
        self._not_available()

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
        self._not_available()
