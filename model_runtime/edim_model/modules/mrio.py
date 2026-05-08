from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from .base import DevelopmentModelModule, ModelModuleInfo


class MrioDevelopmentModule(DevelopmentModelModule):
    info = ModelModuleInfo(
        module_id="mrio",
        kind="development",
        label="MRIO development model",
        implementation_status="ready",
        description=(
            "Development-impact module using bridge-derived exchange shocks plus "
            "structured MRIO-direct scenario assumptions."
        ),
        supported_modes=["mario"],
        stages=["bridge_prepare", "mrio_direct_prepare", "development"],
    )

    def scenario_catalog(self, settings: Any) -> Dict[str, Any]:
        from ..core.scenario_package import (
            _mrio_shock_mapping_options,
            _read_csv_rows,
            _target_scenario_catalog_entry,
            write_africa_national_mrio_placeholder_scenarios,
        )
        from ..core.scenario_report import load_or_parse_scenario_report

        report = load_or_parse_scenario_report(settings.config_dir)
        africa_mrio = write_africa_national_mrio_placeholder_scenarios(settings.config_dir, report)
        target_years: set[int] = set()
        target_scenarios = []
        for scenario_id in ("S1", "S2"):
            row = dict((africa_mrio.get("scenarios") or {}).get(scenario_id) or {})
            years = [int(y) for y in (row.get("target_years") or []) if str(y).isdigit()]
            target_years.update(years)
            target_scenarios.append(_target_scenario_catalog_entry(row))
        shock_mappings = _mrio_shock_mapping_options(report)
        default_target = (
            "S2"
            if any(row.get("scenario_id") == "S2" for row in target_scenarios)
            else (str(target_scenarios[0].get("scenario_id") or "") if target_scenarios else "")
        )
        return {
            "module_id": self.info.module_id,
            "kind": self.info.kind,
            "label": self.info.label,
            "implementation_status": self.info.implementation_status,
            "scenario_channels": [
                {
                    "channel_id": "target_pathway",
                    "label": "Development target pathway",
                    "config_key": "scenario.target_scenario_id",
                    "value_field": "target_scenario_id",
                    "required": True,
                    "options": [
                        {
                            "value": str(row.get("scenario_id") or ""),
                            "label": str(row.get("short_label") or row.get("label") or row.get("scenario_id") or ""),
                            "description": str(row.get("description") or ""),
                            "metadata": row,
                        }
                        for row in target_scenarios
                    ],
                    "default": default_target,
                },
                {
                    "channel_id": "target_year",
                    "label": "Target year",
                    "config_key": "scenario.target_year",
                    "value_field": "target_year",
                    "required": True,
                    "options": [{"value": year, "label": str(year)} for year in sorted(target_years or {2030, 2050})],
                    "default": 2030,
                },
                {
                    "channel_id": "mrio_shock_mapping",
                    "label": "MRIO shock mapping",
                    "config_key": "scenario.mrio_shock_mapping_id",
                    "value_field": "mrio_shock_mapping_id",
                    "required": False,
                    "options": [
                        {
                            "value": str(row.get("mapping_id") or ""),
                            "label": str(row.get("label") or row.get("mapping_id") or ""),
                            "description": str(row.get("description") or ""),
                            "metadata": row,
                        }
                        for row in shock_mappings
                    ],
                    "default": str(shock_mappings[0].get("mapping_id") or "") if shock_mappings else "",
                },
            ],
            "defaults": {
                "target_scenario_id": default_target,
                "mrio_scenario_id": default_target,
                "mrio_shock_mapping_id": str(shock_mappings[0].get("mapping_id") or "") if shock_mappings else "",
                "target_year": 2030,
            },
            "metadata": {
                "geography_alignment_options": _read_csv_rows(settings.config_dir / "scenario_geography_mapping.csv"),
                "report": {
                    "source_file": report.get("source_file", ""),
                    "source_sha256": report.get("source_sha256", ""),
                    "scenario_count": len(report.get("scenario_ids") or []),
                    "africa_national_placeholder_dataset": "inputs/generated/africa_national_mrio_placeholder_scenarios.json",
                    "africa_national_country_count": africa_mrio.get("country_count", 0),
                },
            },
        }

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
    ) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
        from ..core import runner as core_runner

        core_runner._normalize_development_engine_label(settings.development_engine)
        return core_runner._build_mario_development_outputs(
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
