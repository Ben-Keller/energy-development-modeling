from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Protocol, Tuple


ProgressCallback = Callable[[str, float, str], None] | None
CancelCallback = Callable[[], bool] | None


class ModelModuleError(RuntimeError):
    """Raised when a registered model module cannot execute a requested mode."""


@dataclass(frozen=True)
class ModelModuleInfo:
    module_id: str
    kind: str
    label: str
    implementation_status: str
    description: str = ""
    asset_root: str = ""
    supported_engines: List[str] = field(default_factory=list)
    supported_modes: List[str] = field(default_factory=list)
    stages: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_id": self.module_id,
            "kind": self.kind,
            "label": self.label,
            "implementation_status": self.implementation_status,
            "description": self.description,
            "asset_root": self.asset_root,
            "supported_engines": list(self.supported_engines),
            "supported_modes": list(self.supported_modes),
            "stages": list(self.stages),
        }


class EnergyModelModule(Protocol):
    info: ModelModuleInfo

    def scenario_catalog(self, settings: Any) -> Dict[str, Any]: ...

    def resolve_model_definition(self, settings: Any) -> Path: ...

    def load_technology_library(self, settings: Any) -> Dict[str, Any]: ...

    def build_runtime_override(
        self,
        *,
        settings: Any,
        req: Any,
        lever_patch: Dict[str, Any],
        solver_name: str,
    ) -> Dict[str, Any]: ...

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
    ) -> Any: ...


class DevelopmentModelModule(Protocol):
    info: ModelModuleInfo

    def scenario_catalog(self, settings: Any) -> Dict[str, Any]: ...

    def run(
        self,
        *,
        settings: Any,
        model: Any,
        summary: Dict[str, Any],
        req: Any,
        run_id: str,
        run_dir: Path,
        development_model_config: Dict[str, Any],
        mapping_quality: Dict[str, Any],
        scenario_package: Dict[str, Any],
        artifact_registry: Any = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]: ...
