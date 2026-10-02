from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from .base import DevelopmentModelModule, EnergyModelModule, ModelModuleError
from .calliope import CalliopeEnergyModule
from .mrio import MrioDevelopmentModule
from .osemosys import OsemosysEnergyModule


_ENERGY_MODULES: Dict[str, EnergyModelModule] = {
    "calliope": CalliopeEnergyModule(),
    "osemosys": OsemosysEnergyModule(),
}

_DEVELOPMENT_MODULES: Dict[str, DevelopmentModelModule] = {
    "mario": MrioDevelopmentModule(),
}


def get_energy_model_module(engine: str) -> EnergyModelModule:
    key = str(engine or "calliope").strip().lower()
    try:
        return _ENERGY_MODULES[key]
    except KeyError as exc:
        raise ModelModuleError(
            f"Unknown energy model engine '{engine}'. Available engines: {sorted(_ENERGY_MODULES)}"
        ) from exc


def get_development_model_module(mode: str) -> DevelopmentModelModule:
    key = str(mode or "mario").strip().lower()
    try:
        return _DEVELOPMENT_MODULES[key]
    except KeyError as exc:
        raise ModelModuleError(
            f"Unknown development model mode '{mode}'. Available modes: {sorted(_DEVELOPMENT_MODULES)}"
        ) from exc


def model_module_catalog() -> List[dict]:
    seen = set()
    rows = []
    for module in [*_ENERGY_MODULES.values(), *_DEVELOPMENT_MODULES.values()]:
        module_id = module.info.module_id
        if module_id in seen:
            continue
        seen.add(module_id)
        rows.append(module.info.to_dict())
    return sorted(rows, key=lambda row: (row.get("kind", ""), row.get("module_id", "")))


def _manifest_modules(manifest: Dict[str, Any] | None) -> List[Dict[str, Any]]:
    if not isinstance(manifest, dict):
        return []
    modules = manifest.get("modules") or []
    return [dict(row) for row in modules if isinstance(row, dict) and row.get("module_id")]


def _configured_module_ids(manifest: Dict[str, Any] | None) -> set[str]:
    return {str(row.get("module_id", "")).strip() for row in _manifest_modules(manifest) if row.get("module_id")}


def _configured_modules(manifest: Dict[str, Any] | None) -> Iterable[Any]:
    """Return registered module instances that are enabled by the runtime manifest."""
    configured_ids = _configured_module_ids(manifest)
    for module in [*_ENERGY_MODULES.values(), *_DEVELOPMENT_MODULES.values()]:
        if configured_ids and module.info.module_id not in configured_ids:
            continue
        yield module


def _normalize_channel(channel: Dict[str, Any], module_config: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(channel)
    row.setdefault("module_id", module_config.get("module_id", ""))
    row.setdefault("module_kind", module_config.get("kind", ""))
    row.setdefault("module_label", module_config.get("label", ""))
    row.setdefault("implementation_status", module_config.get("implementation_status", ""))
    row.setdefault("options", [])
    return row


def _merge_channels(channels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge module contributions that configure the same runtime selector.

    Engine selectors are naturally contributed by multiple energy modules.
    The public catalog should expose one selector per `config_key`, with the
    individual module options preserved in that selector's `options` list.
    """
    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for channel in channels:
        key = str(channel.get("config_key") or channel.get("channel_id") or "").strip()
        if not key:
            key = f"{channel.get('module_id', '')}.{channel.get('channel_id', '')}"
        if key not in merged:
            merged[key] = dict(channel)
            merged[key]["options"] = []
            merged[key]["source_modules"] = []
            order.append(key)
        target = merged[key]
        source_module = str(channel.get("module_id") or "").strip()
        if source_module and source_module not in target["source_modules"]:
            target["source_modules"].append(source_module)
        seen_values = {str(option.get("value")) for option in target.get("options", []) if isinstance(option, dict)}
        for option in channel.get("options") or []:
            if not isinstance(option, dict):
                continue
            value = str(option.get("value") or "")
            if value in seen_values:
                continue
            target["options"].append(dict(option))
            seen_values.add(value)
        if not target.get("default") and channel.get("default"):
            target["default"] = channel.get("default")
    return [merged[key] for key in order]


def module_scenario_catalog(settings: Any, manifest: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Build the scenario catalog from model-owned scenario channels."""
    module_configs: List[Dict[str, Any]] = []
    channels: List[Dict[str, Any]] = []
    defaults: Dict[str, Any] = {}

    for module in _configured_modules(manifest):
        catalog_builder = getattr(module, "scenario_catalog", None)
        if not callable(catalog_builder):
            continue
        module_config = dict(catalog_builder(settings) or {})
        module_config.setdefault("module_id", module.info.module_id)
        module_config.setdefault("kind", module.info.kind)
        module_config.setdefault("label", module.info.label)
        module_config.setdefault("implementation_status", module.info.implementation_status)
        module_channels = [
            _normalize_channel(row, module_config)
            for row in (module_config.get("scenario_channels") or [])
            if isinstance(row, dict)
        ]
        module_config["scenario_channels"] = module_channels
        module_configs.append(module_config)
        channels.extend(module_channels)
        defaults.update(dict(module_config.get("defaults") or {}))

    registered_ids = {str(row.get("module_id", "")) for row in module_configs}
    for row in _manifest_modules(manifest):
        module_id = str(row.get("module_id", ""))
        if module_id in registered_ids:
            continue
        manifest_channels = [
            _normalize_channel(channel, row)
            for channel in (row.get("scenario_channels") or [])
            if isinstance(channel, dict)
        ]
        if manifest_channels:
            module_config = {
                "module_id": module_id,
                "kind": row.get("kind", ""),
                "label": row.get("label", module_id),
                "implementation_status": row.get("implementation_status", "not_registered"),
                "scenario_channels": manifest_channels,
                "defaults": {},
                "source": "runtime_manifest",
            }
            module_configs.append(module_config)
            channels.extend(manifest_channels)

    if "mrio_scenario_id" not in defaults and defaults.get("target_scenario_id"):
        defaults["mrio_scenario_id"] = defaults["target_scenario_id"]

    return {
        "schema_version": "model_scenario_catalog",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_modules": model_module_catalog(),
        "module_configurations": sorted(module_configs, key=lambda row: (str(row.get("kind", "")), str(row.get("module_id", "")))),
        "scenario_channels": sorted(_merge_channels(channels), key=lambda row: (str(row.get("module_kind", "")), str(row.get("config_key", "")), str(row.get("channel_id", "")))),
        "defaults": defaults,
    }
