from __future__ import annotations

import tempfile
import time
import unittest
import multiprocessing as mp
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import pandas as pd
from fastapi import HTTPException

from api_service.integrated import (
    build_integrated_results,
    build_run_report_markdown,
    create_exchange_bundle_zip,
    validate_integrated_results,
)
from api_service.jobs import JobManager, JobQueueFullError
from api_service.levers import load_lever_mappings
from api_service.main import _read_summary_json
from api_service.mario_runtime import mario_inputs_health, run_mario_io_runtime
from api_service.scenario_package import (
    build_integrated_scenario_catalog,
    build_geography_alignment,
    build_mrio_direct_inputs,
    build_scenario_package,
    write_scenario_artifacts,
)
from api_service.scenario_report import load_or_parse_scenario_report
from api_service.runner import (
    RunCancelledError,
    _build_development_outputs,
    _results_health,
    _write_exchange_files_for_mario,
    _load_development_model_config,
    build_environment_setup_report,
)
from api_service.scenarios import load_scenario_metadata
from api_service.schemas import LeverValues, RunRequest
from api_service.settings import Settings
from api_service.summarize import build_summary_diagnostics


def _build_settings(base: Path, *, dedupe_enabled: bool = True, queue_capacity: int = 200) -> Settings:
    calliope_root = base / "Calliope-Africa-main"
    calliope_root.mkdir(parents=True, exist_ok=True)
    (calliope_root / "model.yaml").write_text("model: {}", encoding="utf-8")
    (calliope_root / "overrides.yaml").write_text("{}", encoding="utf-8")

    runs_dir = base / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    config_dir = base / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "lever_mappings.csv").write_text(
        "\n".join(
            [
                "key,value",
                "renewables_tech,PV*",
                "fossil_tech,CCGT*",
                "capex_key_path,costs.monetary.energy_cap",
                "fuel_cost_key_path,costs.monetary.om_con",
                "carbon_price_path,run.objective_options.cost_class.co2",
            ]
        ),
        encoding="utf-8",
    )

    return Settings(
        calliope_root=calliope_root,
        runs_dir=runs_dir,
        config_dir=config_dir,
        dev_subset_start="2019-01-01",
        dev_subset_end="2019-01-02",
        analysis_subset_start="2019-01-01",
        analysis_subset_end="2019-03-31",
        dev_solver_time_limit_seconds=180.0,
        analysis_solver_time_limit_seconds=900.0,
        allow_full_year=True,
        solver="highs",
        cors_allow_origins=["http://localhost:8000"],
        summary_max_generation_techs=10,
        summary_max_generation_timesteps=240,
        summary_max_category_rows=25,
        summary_diagnostics_max_rows=100,
        run_retention_days=30,
        run_max_dirs=200,
        job_history_limit=200,
        job_dedupe_enabled=dedupe_enabled,
        job_queue_capacity=queue_capacity,
        development_engine="auto",
        mario_db_path="",
        mario_timeout_seconds=120.0,
        mario_fail_on_error=False,
    )


def _wait_terminal(manager: JobManager, job_id: str, timeout_seconds: float = 8.0):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        info = manager.get(job_id)
        if str(info.status).lower() in {"succeeded", "failed", "cancelled"}:
            return info
        time.sleep(0.02)
    raise AssertionError(f"Job did not reach terminal status: {job_id}")


def _summary_template(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "energy_scenario_key": "new_links",
        "mrio_scenario_id": "S2",
        "target_year": 2030,
        "run_profile": "dev",
        "system_cost": {"records": [{"costs": "monetary", "value": 100.0}]},
        "summary_diagnostics": {
            "physical_emissions": {"total_emissions": 50.0},
            "reliability": {"unserved_energy_share": 0.01, "unserved_total": 5.0},
        },
        "development_impacts": {
            "totals": {"jobs_total": 120.0, "gva_total_musd": 20.0},
            "inputs": {"investment_shock_total_musd": 10.0, "operating_shock_total_musd": 3.0},
            "by_region": {"records": [{"region": "A", "jobs_total": 120.0, "gva_total_musd": 20.0}]},
            "by_supplier_sector": {"records": [{"supplier_sector": "Import_goods", "shock_value_musd": 2.5}]},
        },
        "warnings": [],
    }


def _run_request() -> RunRequest:
    return RunRequest(
        energy_scenario_key="new_links",
        mrio_scenario_id="S2",
        target_year=2030,
        run_profile="dev",
        strict_validation=False,
        allow_placeholder_data=True,
        levers=LeverValues(),
    )


def _scenario_package() -> dict:
    return {
        "schema_version": "integrated_scenario_package_v1",
        "energy_scenario_key": "new_links",
        "mrio_scenario_id": "S2",
        "target_year": 2030,
        "run_profile": "dev",
        "levers": {},
        "energy": {"adapter": "calliope_v1", "model": "calliope", "scenario_key": "new_links"},
        "mrio_direct": {
            "adapter": "mrio_direct_heuristic_v1",
            "scenario": {
                "scenario_id": "ZA-S2",
                "geography_code": "ZA",
                "geography": {"name": "South Africa", "type": "Country"},
                "summary": {
                    "fossil_delta_2030_numeric": -0.15,
                    "renewable_share_2030_numeric": 0.22,
                },
                "shock_categories": {
                    "A/Z": [
                        {"parameter": "Coal A-matrix coefficient", "target_2030": "Reduce by ~15% by 2030", "target_2050": "Reduce to 0 by 2050"},
                        {"parameter": "Renewable electricity share", "target_2030": "22% by 2030", "target_2050": "100% by 2050"},
                    ],
                    "E": [{"parameter": "CO2 emission intensity", "target_2030": "Reduce by ~15%", "target_2050": "0"}],
                    "Y": [{"parameter": "Solar/Wind addition", "target_2030": "+10%", "target_2050": "+full capacity"}],
                },
            },
            "report_source": {"source_file": "test.docx", "source_sha256": "test"},
        },
        "geography_alignment": {"status": "aligned", "calliope_locations": ["ZAF"]},
        "provenance": {"source": "test"},
    }


def _seed_mario_inputs(config_dir: Path) -> Path:
    mario_dir = config_dir / "mario_inputs"
    mario_dir.mkdir(parents=True, exist_ok=True)
    (mario_dir / "calliope_tech_to_mario_sector.csv").write_text(
        "calliope_tech,mario_sector,shock_channel\nCCGT_pp,Gas_supply_chain,opex\nPV_New,Electrical_equipment,capex\n",
        encoding="utf-8",
    )
    (mario_dir / "capex_sector_split.csv").write_text(
        "calliope_tech,mario_region,mario_sector,share\nPV_New,East_Africa,Electrical_equipment,1.0\n",
        encoding="utf-8",
    )
    (mario_dir / "opex_sector_split.csv").write_text(
        "calliope_tech,mario_region,mario_sector,opex_type,share\nCCGT_pp,East_Africa,Gas_supply_chain,fuel,1.0\nCCGT_pp,East_Africa,Maintenance_services,om,1.0\n",
        encoding="utf-8",
    )
    (mario_dir / "calliope_cost_to_mario_account.csv").write_text(
        "calliope_cost_class,calliope_component,mario_account,mario_flow_type\nmonetary,energy_cap,Intermediate_demand,investment\n",
        encoding="utf-8",
    )
    (mario_dir / "country_to_pool.csv").write_text(
        "calliope_location,power_pool,mario_region\nEGY,EAPP,East_Africa\n",
        encoding="utf-8",
    )
    (mario_dir / "employment_intensity.csv").write_text(
        "mario_region,mario_sector,jobs_per_musd_direct,jobs_per_musd_total\nEast_Africa,Gas_supply_chain,4.0,7.0\nEast_Africa,Maintenance_services,6.0,11.0\nEast_Africa,Electrical_equipment,5.0,9.0\n",
        encoding="utf-8",
    )
    (mario_dir / "value_added_intensity.csv").write_text(
        "mario_region,mario_sector,gva_per_musd_output,household_income_per_musd_output\nEast_Africa,Gas_supply_chain,0.35,0.15\nEast_Africa,Maintenance_services,0.4,0.22\nEast_Africa,Electrical_equipment,0.3,0.12\n",
        encoding="utf-8",
    )
    (mario_dir / "scenario_assumptions.csv").write_text(
        "assumption_key,scenario_key,value,unit,effective_year,source,notes\ncarbon_price,baseline,25,usd_per_tco2,2019,expert,calibrated baseline carbon proxy\n",
        encoding="utf-8",
    )
    (mario_dir / "development_indicator_mapping.csv").write_text(
        "indicator_id,indicator_name,driver_metric,aggregation_rule,unit,lag_years,notes\njobs_total,Total employment impact,jobs_per_musd_total,sum,jobs,0,from MARIO + intensity tables\ngva_total,Gross value added impact,gva_per_musd_output,sum,musd_2019,0,from MARIO output\nco2_cost_burden,Carbon cost burden,co2_cost_proxy,sum,musd_2019,0,proxy based on physical emissions and carbon price\n",
        encoding="utf-8",
    )
    (mario_dir / "exchange_output_schema.csv").write_text(
        "file_name,column_name,required,dtype,description\nenergy_service_balance.csv,run_id,yes,string,x\n",
        encoding="utf-8",
    )
    return mario_dir


class SchemaTests(unittest.TestCase):
    def test_run_request_profile_normalization(self):
        req = RunRequest(
            energy_scenario_key="new_links",
            mrio_scenario_id="S2",
            target_year=2030,
            run_profile="analysis",
            strict_validation=False,
            allow_placeholder_data=True,
        )
        self.assertEqual(req.run_profile, "analysis")
        self.assertEqual(req.energy_scenario_key, "new_links")
        self.assertEqual(req.mrio_scenario_id, "S2")
        self.assertTrue(req.strict_validation)

    def test_run_request_rejects_legacy_scenario_shape(self):
        with self.assertRaises(Exception):
            RunRequest(
                scenario="new_links",
                fast_dev_mode=True,
                energy_scenario_key="new_links",
                mrio_scenario_id="S2",
                target_year=2030,
                run_profile="dev",
                strict_validation=False,
                allow_placeholder_data=True,
            )


class ScenarioReportTests(unittest.TestCase):
    def test_root_report_parser_recovers_expected_scenarios(self):
        repo_root = Path(__file__).resolve().parents[2]
        report = load_or_parse_scenario_report(repo_root / "inputs")
        expected = {"ZA-S1", "ZA-S2", "IN-S1", "IN-S2", "BR-S1", "BR-S2", "WF-S1", "WF-S2", "WM-S1", "WM-S2"}
        self.assertEqual(set(report["scenario_ids"]), expected)
        za = report["scenarios"]["ZA-S2"]
        self.assertEqual(za["geography_code"], "ZA")
        self.assertTrue(za["shock_categories"]["A/Z"])
        self.assertIn(2030, za["target_years"])

    def test_scenario_package_and_direct_inputs_are_complete(self):
        repo_root = Path(__file__).resolve().parents[2]
        package = build_scenario_package(
            config_dir=repo_root / "inputs",
            calliope_root=repo_root / "Calliope-Africa-main",
            energy_scenario_key="new_links",
            mrio_scenario_id="S2",
            target_year=2030,
            run_profile="dev",
            levers={},
            strict_validation=False,
            allow_placeholder_data=True,
        )
        self.assertEqual(package["mrio_scenario_id"], "S2")
        self.assertEqual(package["target_scenario"]["scenario_id"], "S2")
        self.assertEqual(package["mrio_direct"]["shock_mapping"]["mapping_id"], "mrio_direct_heuristic_v1")
        self.assertEqual(package["mrio_direct"]["scenario"]["scenario_id"], "S2")
        self.assertGreater(package["mrio_direct"]["scenario"]["national_record_count"], 1)
        self.assertEqual(package["geography_alignment"]["alignment_level"], "africa_national_placeholder_to_calliope_locations")
        self.assertEqual(package["geography_alignment"]["status"], "aligned")
        direct = build_mrio_direct_inputs(
            scenario_package=package,
            bridge_total_shock_musd=100.0,
            direct_config={"structural_reallocation_bridge_scale": 0.25, "max_direct_to_bridge_ratio": 1.0},
        )
        self.assertEqual(direct["method"], "mrio_direct_heuristic_v1")
        self.assertEqual(direct["scenario_id"], "S2")
        self.assertTrue(direct["diagnostics"]["national_placeholder_dataset"])
        self.assertGreater(len(direct["shock_rows"]), 0)
        direct_regions = {str(row.get("mario_region", "")) for row in direct["shock_rows"]}
        source_ids = {str(row.get("source_report_scenario_id", "")) for row in direct["shock_rows"]}
        self.assertIn("ZAF", direct_regions)
        self.assertTrue(any(region and region != "ZAF" for region in direct_regions))
        self.assertIn("ZA-S2", source_ids)
        self.assertIn("WF-S2", source_ids)
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = write_scenario_artifacts(Path(tmp), package, direct)
            self.assertIn("scenario_package_json", artifacts)
            self.assertTrue((Path(tmp) / "scenario_package.json").exists())
            self.assertTrue((Path(tmp) / "scenario" / "mrio_direct_inputs.json").exists())
            self.assertTrue((Path(tmp) / "scenario" / "mrio_direct_shocks.csv").exists())

    def test_integrated_catalog_splits_targets_from_mrio_shock_mapping(self):
        repo_root = Path(__file__).resolve().parents[2]
        catalog = build_integrated_scenario_catalog(
            repo_root / "inputs",
            repo_root / "Calliope-Africa-main",
            energy_scenarios=[{"key": "new_links", "title": "New links"}],
        )
        self.assertEqual([row["scenario_id"] for row in catalog["target_scenarios"]], ["S1", "S2"])
        self.assertEqual(catalog["defaults"]["mrio_scenario_id"], "S2")
        self.assertEqual(catalog["defaults"]["target_scenario_id"], "S2")
        self.assertEqual(catalog["defaults"]["mrio_shock_mapping_id"], "mrio_direct_heuristic_v1")
        self.assertEqual(catalog["mrio_shock_mappings"][0]["mapping_id"], "mrio_direct_heuristic_v1")
        self.assertIn("target_profiles", catalog["target_scenarios"][1])
        self.assertGreater(catalog["report"]["africa_national_country_count"], 50)
        self.assertTrue((repo_root / "inputs" / "generated" / "africa_national_mrio_placeholder_scenarios.json").exists())

    def test_geography_alignment_fans_out_national_and_regional_scenarios(self):
        repo_root = Path(__file__).resolve().parents[2]
        report = load_or_parse_scenario_report(repo_root / "inputs")
        za_alignment = build_geography_alignment(
            config_dir=repo_root / "inputs",
            calliope_root=repo_root / "Calliope-Africa-main",
            mrio_scenario=report["scenarios"]["ZA-S2"],
        )
        wf_alignment = build_geography_alignment(
            config_dir=repo_root / "inputs",
            calliope_root=repo_root / "Calliope-Africa-main",
            mrio_scenario=report["scenarios"]["WF-S2"],
        )
        br_alignment = build_geography_alignment(
            config_dir=repo_root / "inputs",
            calliope_root=repo_root / "Calliope-Africa-main",
            mrio_scenario=report["scenarios"]["BR-S2"],
        )
        self.assertIn("ZAF", za_alignment["calliope_locations"])
        self.assertGreater(wf_alignment["calliope_location_count"], 1)
        self.assertFalse(wf_alignment["blocking_mismatch"])
        self.assertEqual(br_alignment["status"], "mrio_only")

    def test_lever_mappings_csv_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            (config_dir / "lever_mappings.csv").write_text(
                "\n".join(
                    [
                        "key,value",
                        "renewables_tech,PV*",
                        "renewables_tech,Wind*",
                        "fossil_tech,CCGT*",
                        "capex_key_path,costs.monetary.energy_cap",
                        "fuel_cost_key_path,costs.monetary.om_con",
                        "carbon_price_path,run.objective_options.cost_class.co2",
                    ]
                ),
                encoding="utf-8",
            )
            mappings = load_lever_mappings(config_dir)
            self.assertIn("PV*", mappings.renewables_techs)
            self.assertIn("CCGT*", mappings.fossil_techs)
            self.assertEqual(mappings.capex_key_path, ["costs", "monetary", "energy_cap"])
            self.assertEqual(mappings.fuel_cost_key_path, ["costs", "monetary", "om_con"])
            self.assertEqual(
                mappings.carbon_price_path,
                ["run", "objective_options", "cost_class", "co2"],
            )

    def test_development_model_csv_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            (config_dir / "development_model.csv").write_text(
                "\n".join(
                    [
                        "parameter,value",
                        "surrogate.totals.jobs_total_multiplier,2.2",
                        "mario.uncertainty_relative_bounds.jobs_total,0.18",
                    ]
                ),
                encoding="utf-8",
            )
            cfg = _load_development_model_config(config_dir)
            self.assertAlmostEqual(cfg["surrogate"]["totals"]["jobs_total_multiplier"], 2.2)
            self.assertAlmostEqual(cfg["mario"]["uncertainty_relative_bounds"]["jobs_total"], 0.18)

    def test_results_health_handles_missing_results(self):
        class _NoResults:
            results = None

        health = _results_health(_NoResults())
        self.assertEqual(health["var_count"], 0)
        self.assertEqual(health["termination_condition"], "")

    def test_results_health_reads_attrs_and_data_vars(self):
        class _Results:
            attrs = {"termination_condition": "optimal", "solution_time": 12.5}
            data_vars = {"carrier_prod": object(), "cost": object()}

        class _Model:
            results = _Results()

        health = _results_health(_Model())
        self.assertEqual(health["var_count"], 2)
        self.assertEqual(health["termination_condition"], "optimal")


class IntegratedResultsTests(unittest.TestCase):
    def test_build_integrated_results_contains_expected_fields(self):
        payload = build_integrated_results(_summary_template("run1"))
        self.assertEqual(payload["run_id"], "run1")
        self.assertTrue(payload["integrated_overview"]["metrics"])
        self.assertIn("development_drivers", payload)
        self.assertIn("development_uncertainty", payload)
        self.assertIn("scenario_provenance", payload)
        self.assertIn("source_channels", payload)

    def test_build_integrated_results_uses_selected_totals_and_exposes_channels(self):
        summary = _summary_template("run1")
        summary["development_impacts"]["bridge"] = {"totals": {"jobs_total": 120.0, "gva_total_musd": 20.0}}
        summary["development_impacts"]["mrio_direct"] = {
            "method": "mrio_direct_heuristic_v1",
            "totals": {"jobs_total": 30.0, "gva_total_musd": 5.0},
        }
        summary["development_impacts"]["selected_totals"] = {"jobs_total": 120.0, "gva_total_musd": 20.0}
        summary["development_impacts"]["combined_totals"] = {"jobs_total": 150.0, "gva_total_musd": 25.0}
        summary["development_impacts"]["overlap_diagnostics"] = {
            "overlap_exists": True,
            "selected_totals_source": "bridge",
            "temporary_merge_logic": True,
        }
        payload = build_integrated_results(
            summary,
            coupling_manifest={
                "mrio_direct_heuristic": True,
                "selected_totals_source": "bridge",
                "temporary_overlap_policy": "bridge_authoritative_for_headline_totals",
            },
        )
        self.assertEqual(payload["source_channels"]["selected_totals"]["jobs_total"], 120.0)
        self.assertEqual(payload["source_channels"]["combined_totals"]["jobs_total"], 150.0)
        self.assertEqual(payload["development_confidence"]["selected_totals_source"], "bridge")
        self.assertIn(payload["model_quality"]["status"], {"analyst_review", "exploratory_only"})

    def test_validate_integrated_results_rejects_missing_metric(self):
        payload = build_integrated_results(_summary_template("run1"))
        payload["integrated_overview"]["metrics"] = [
            row for row in payload["integrated_overview"]["metrics"] if row.get("key") != "jobs_total"
        ]
        with self.assertRaises(ValueError):
            validate_integrated_results(payload)

    def test_build_integrated_results_loads_assumptions_and_indicators(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            _seed_mario_inputs(config_dir)
            payload = build_integrated_results(
                _summary_template("run1"),
                config_dir=config_dir,
                lever_values={"carbon_price_usd_per_tco2": 10.0},
            )
            self.assertTrue(payload["scenario_assumptions"]["records"])
            self.assertGreaterEqual(payload["development_indicators"]["available_count"], 1)

    def test_build_integrated_results_exposes_model_quality_and_resolution(self):
        summary = _summary_template("run1")
        summary["summary_diagnostics"]["physical_emissions"] = {
            "method": "cost_class_co2_direct",
            "factor_coverage_share": 0.25,
            "factor_method_gap_share": 0.0,
            "total_emissions": 50.0,
        }
        summary["summary_diagnostics"]["energy_balance"] = {
            "max_abs_balance_gap_share": 0.0,
        }
        payload = build_integrated_results(
            summary,
            coupling_manifest={
                "development_engine_mode": "mario",
                "mapping_coverage_share": 1.0,
                "fallback_mapping_share": 0.0,
                "placeholder_input_row_count": 0,
                "allow_placeholder_data": False,
            },
        )
        self.assertEqual(payload["model_quality"]["status"], "production_ready")
        self.assertTrue(payload["metric_resolution"]["records"])


class SummaryDiagnosticsTests(unittest.TestCase):
    class _FakeDA:
        def __init__(self, rows):
            self._rows = rows

        def to_dataframe(self, name="value"):
            return pd.DataFrame(self._rows)

    class _FakeResults(dict):
        def __init__(self, *args, **kwargs):
            attrs = kwargs.pop("attrs", None) or {}
            super().__init__(*args, **kwargs)
            self.attrs = attrs
            self.data_vars = self

    class _FakeModel:
        def __init__(self, results):
            self.results = results

    def test_build_summary_diagnostics_prefers_direct_co2_and_builds_balance(self):
        results = self._FakeResults(
            {
                "carrier_prod": self._FakeDA(
                    [
                        {"locs": "EGY", "techs": "CCGT_pp", "value": 100.0},
                        {"locs": "EGY", "techs": "PV1", "value": 50.0},
                    ]
                ),
                "carrier_con": self._FakeDA(
                    [
                        {"locs": "EGY", "techs": "Demand_power", "value": -150.0},
                    ]
                ),
                "unmet_demand": self._FakeDA(
                    [
                        {"locs": "EGY", "timesteps": "2019-01-01 00:00:00", "value": 0.0},
                    ]
                ),
                "cost": self._FakeDA(
                    [
                        {"locs": "EGY", "techs": "CCGT_pp", "costs": "co2", "value": 90.0},
                        {"locs": "EGY", "techs": "CCGT_pp", "costs": "monetary", "value": 10.0},
                    ]
                ),
                "energy_cap": self._FakeDA(
                    [
                        {"techs": "CCGT_pp", "value": 20.0},
                        {"techs": "PV1", "value": 30.0},
                    ]
                ),
            },
            attrs={
                "termination_condition": "optimal",
                "solution_time": 1.0,
                "objective_function_value": 2.0,
            },
        )
        model = self._FakeModel(results)
        diagnostics = build_summary_diagnostics(
            model=model,
            run_id="run1",
            scenario="new_links",
            calliope_root=None,
            tech_library={
                "techs": {
                    "CCGT_pp": {"costs": {"co2": {"om_prod": 0.9}}},
                    "PV1": {"costs": {"co2": {"om_prod": 0.0}}},
                }
            },
            max_rows=20,
            warnings=[],
        )
        self.assertEqual(diagnostics["physical_emissions"]["method"], "cost_class_co2_direct")
        self.assertAlmostEqual(diagnostics["physical_emissions"]["total_emissions"], 90.0)
        self.assertAlmostEqual(diagnostics["energy_balance"]["max_abs_balance_gap_share"], 0.0)
        self.assertGreater(diagnostics["system_structure"]["renewable_generation_share"], 0.0)


class MainAndArtifactTests(unittest.TestCase):
    def test_read_summary_json_invalid_payload_returns_503(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.json"
            path.write_text("{invalid-json}", encoding="utf-8")
            with self.assertRaises(HTTPException) as ctx:
                _read_summary_json(path)
            self.assertEqual(ctx.exception.status_code, 503)

    def test_create_exchange_bundle_contains_core_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            exchange_dir = run_dir / "exchange"
            exchange_dir.mkdir(parents=True, exist_ok=True)
            (exchange_dir / "energy_service_balance.csv").write_text("a,b\n1,2\n", encoding="utf-8")
            (run_dir / "results.csv").write_text("variable,value\ncost,1\n", encoding="utf-8")
            (run_dir / "development_impacts.json").write_text("{}", encoding="utf-8")
            (run_dir / "coupling_manifest.json").write_text("{}", encoding="utf-8")
            (run_dir / "integrated_results.json").write_text("{}", encoding="utf-8")

            zip_path = create_exchange_bundle_zip(run_dir)
            self.assertTrue(zip_path and zip_path.exists())
            with ZipFile(zip_path, "r") as zf:
                names = set(zf.namelist())
            self.assertIn("exchange/energy_service_balance.csv", names)
            self.assertIn("results.csv", names)
            self.assertIn("development_impacts.json", names)
            self.assertIn("coupling_manifest.json", names)
            self.assertIn("integrated_results.json", names)

    def test_report_markdown_contains_key_sections(self):
        summary = {
            "run_id": "abc12345",
            "energy_scenario_key": "new_links",
            "mrio_scenario_id": "ZA-S2",
            "target_year": 2030,
            "run_profile": "dev",
            "warnings": ["example warning"],
            "summary_diagnostics": {
                "run_metadata": {
                    "solver": "highs",
                    "termination_condition": "optimal",
                    "solution_time_seconds": 12.3,
                    "objective_function_value": 45.6,
                },
                "reliability": {
                    "demand_total": 100.0,
                    "unserved_total": 0.5,
                    "unserved_energy_share": 0.005,
                    "hours_with_unserved": 2,
                },
            },
        }
        integrated = {
            "integrated_overview": {
                "metrics": [{"key": "jobs_total", "label": "Jobs", "unit": "jobs", "value": 10.0}]
            },
            "development_drivers": {
                "capex_effect_musd": 1.0,
                "opex_effect_musd": 2.0,
                "reliability_penalty_proxy": 3.0,
                "import_leakage_musd": 4.0,
            },
            "development_confidence": {
                "coupling_mode": "surrogate",
                "mapping_coverage_share": 0.9,
                "fallback_mapping_share": 0.1,
                "mario_runtime_executed": False,
                "mario_runtime_seconds": 0.0,
                "mario_runner_source": "",
            },
        }
        report = build_run_report_markdown(summary=summary, integrated=integrated)
        self.assertIn("# EDIM Run Report", report)
        self.assertIn("energy_scenario_key", report)
        self.assertIn("mrio_scenario_id", report)
        self.assertIn("## Integrated Metrics", report)
        self.assertIn("example warning", report)


class JobManagerTests(unittest.TestCase):
    def test_dedupes_identical_inflight_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = _build_settings(Path(tmp), dedupe_enabled=True)
            calls = {"count": 0}

            def _fake_run(settings, req, progress_callback=None, cancel_requested=None):
                calls["count"] += 1
                time.sleep(0.2)
                run_id = f"run-{calls['count']:02d}"
                (settings.runs_dir / run_id).mkdir(parents=True, exist_ok=True)
                summary = {
                    "run_id": run_id,
                    "energy_scenario_key": req.energy_scenario_key,
                    "mrio_scenario_id": req.mrio_scenario_id,
                    "target_year": req.target_year,
                    "run_profile": req.run_profile,
                    "warnings": [],
                }
                return run_id, summary, [], settings.runs_dir

            req = RunRequest(energy_scenario_key="new_links", mrio_scenario_id="ZA-S2", target_year=2030, run_profile="dev", strict_validation=False, allow_placeholder_data=True, levers=LeverValues())
            with patch("api_service.jobs.run_calliope_synchronously", side_effect=_fake_run):
                manager = JobManager(settings)
                first = manager.submit(req)
                time.sleep(0.03)
                second = manager.submit(req)
                self.assertEqual(first.job_id, second.job_id)
                final = _wait_terminal(manager, first.job_id)
                self.assertEqual(final.status, "succeeded")
                self.assertEqual(calls["count"], 1)

    def test_cancel_running_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = _build_settings(Path(tmp), dedupe_enabled=False)

            def _fake_run(settings, req, progress_callback=None, cancel_requested=None):
                if progress_callback:
                    progress_callback("solve_energy", 0.5, "Solving")
                for _ in range(120):
                    if cancel_requested and cancel_requested():
                        raise RunCancelledError("Run cancelled by user request.")
                    time.sleep(0.01)
                run_id = "run-long"
                (settings.runs_dir / run_id).mkdir(parents=True, exist_ok=True)
                summary = {
                    "run_id": run_id,
                    "energy_scenario_key": req.energy_scenario_key,
                    "mrio_scenario_id": req.mrio_scenario_id,
                    "target_year": req.target_year,
                    "run_profile": req.run_profile,
                    "warnings": [],
                }
                return run_id, summary, [], settings.runs_dir

            req = RunRequest(energy_scenario_key="new_links", mrio_scenario_id="ZA-S2", target_year=2030, run_profile="dev", strict_validation=False, allow_placeholder_data=True, levers=LeverValues())
            with patch("api_service.jobs.run_calliope_synchronously", side_effect=_fake_run):
                manager = JobManager(settings)
                job = manager.submit(req)
                deadline = time.time() + 2.0
                while time.time() < deadline:
                    if manager.get(job.job_id).status == "running":
                        break
                    time.sleep(0.02)
                manager.cancel(job.job_id)
                final = _wait_terminal(manager, job.job_id)
                self.assertEqual(final.status, "cancelled")

    def test_queue_capacity_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = _build_settings(Path(tmp), dedupe_enabled=False, queue_capacity=1)

            def _fake_run(settings, req, progress_callback=None, cancel_requested=None):
                time.sleep(0.25)
                run_id = "run-one"
                (settings.runs_dir / run_id).mkdir(parents=True, exist_ok=True)
                summary = {
                    "run_id": run_id,
                    "energy_scenario_key": req.energy_scenario_key,
                    "mrio_scenario_id": req.mrio_scenario_id,
                    "target_year": req.target_year,
                    "run_profile": req.run_profile,
                    "warnings": [],
                }
                return run_id, summary, [], settings.runs_dir

            req = RunRequest(energy_scenario_key="new_links", mrio_scenario_id="ZA-S2", target_year=2030, run_profile="dev", strict_validation=False, allow_placeholder_data=True, levers=LeverValues())
            with patch("api_service.jobs.run_calliope_synchronously", side_effect=_fake_run):
                manager = JobManager(settings)
                first = manager.submit(req)
                with self.assertRaises(JobQueueFullError):
                    manager.submit(req)
                _wait_terminal(manager, first.job_id)

    def test_cancel_running_job_subprocess_mode(self):
        if "fork" not in mp.get_all_start_methods():
            self.skipTest("Subprocess cancellation test requires fork start method.")

        with tempfile.TemporaryDirectory() as tmp:
            settings = _build_settings(Path(tmp), dedupe_enabled=False)

            def _fake_run(settings, req, progress_callback=None, cancel_requested=None):
                if progress_callback:
                    progress_callback("solve_energy", 0.55, "Solving")
                for _ in range(300):
                    time.sleep(0.01)
                run_id = "run-subprocess"
                (settings.runs_dir / run_id).mkdir(parents=True, exist_ok=True)
                summary = {
                    "run_id": run_id,
                    "energy_scenario_key": req.energy_scenario_key,
                    "mrio_scenario_id": req.mrio_scenario_id,
                    "target_year": req.target_year,
                    "run_profile": req.run_profile,
                    "warnings": [],
                }
                return run_id, summary, [], settings.runs_dir

            req = RunRequest(energy_scenario_key="new_links", mrio_scenario_id="ZA-S2", target_year=2030, run_profile="dev", strict_validation=False, allow_placeholder_data=True, levers=LeverValues())
            with patch("api_service.jobs.run_calliope_synchronously", side_effect=_fake_run):
                manager = JobManager(settings, use_subprocess=True)
                job = manager.submit(req)
                deadline = time.time() + 2.0
                while time.time() < deadline:
                    if manager.get(job.job_id).status == "running":
                        break
                    time.sleep(0.02)
                manager.cancel(job.job_id)
                final = _wait_terminal(manager, job.job_id)
                self.assertEqual(final.status, "cancelled")


class MetadataTests(unittest.TestCase):
    def test_scenario_metadata_parses_tags_and_templates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scenario_metadata.csv"
            path.write_text(
                "\n".join(
                    [
                        "key,title,description,tags,policy_question,expected_tradeoff,user_label,demand_multiplier,renewables_capex_multiplier,fossil_fuel_price_multiplier,carbon_price_usd_per_tco2",
                        "s1,Scenario 1,,policy,,,,1.0,1.0,1.0,40",
                        "s2,Scenario 2,,ndc|2040,,,,1.0,1.0,1.0,",
                    ]
                ),
                encoding="utf-8",
            )
            data = load_scenario_metadata(path)
            self.assertEqual(data["s1"].tags, ["policy"])
            self.assertEqual(data["s2"].tags, ["ndc", "2040"])
            self.assertEqual(data["s1"].preset_levers["carbon_price_usd_per_tco2"], 40.0)


class EnvironmentSetupTests(unittest.TestCase):
    def test_environment_setup_reports_ready_when_required_inputs_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = _build_settings(Path(tmp))
            report = build_environment_setup_report(
                settings=settings,
                queue_stats={"capacity": 3, "active_jobs": 1},
                energy_scenario_key="",
                run_profile="dev",
            )
            self.assertTrue(report["ok"])
            self.assertIn(report["solver_resolved"], {"highs", "appsi_highs"})

    def test_environment_setup_reports_not_ready_on_missing_model_and_full_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = _build_settings(Path(tmp))
            (settings.calliope_root / "model.yaml").unlink()
            report = build_environment_setup_report(
                settings=settings,
                queue_stats={"capacity": 1, "active_jobs": 1},
                energy_scenario_key="",
                run_profile="dev",
            )
            self.assertFalse(report["ok"])
            statuses = {(row["name"], row["status"]) for row in report.get("checks", [])}
            self.assertIn(("calliope_model", "error"), statuses)
            self.assertIn(("queue_capacity", "warn"), statuses)

    def test_environment_setup_mario_mode_requires_mario_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_settings = _build_settings(Path(tmp))
            settings = replace(base_settings, development_engine="mario")
            report = build_environment_setup_report(
                settings=settings,
                queue_stats={"capacity": 2, "active_jobs": 0},
                energy_scenario_key="",
                run_profile="dev",
            )
            self.assertFalse(report["ok"])
            statuses = {(row["name"], row["status"]) for row in report.get("checks", [])}
            self.assertIn(("mario_inputs", "error"), statuses)

    def test_environment_setup_strict_mode_rejects_placeholder_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            settings = replace(_build_settings(base), development_engine="mario")
            _seed_mario_inputs(settings.config_dir)
            (settings.config_dir / "mario_inputs" / "employment_intensity.csv").write_text(
                "mario_region,mario_sector,jobs_per_musd_direct,jobs_per_musd_total,reference_year,source,notes\nEast_Africa,Gas_supply_chain,4.0,7.0,2019,placeholder,replace with calibrated estimate\n",
                encoding="utf-8",
            )
            report = build_environment_setup_report(
                settings=settings,
                queue_stats={"capacity": 2, "active_jobs": 0},
                energy_scenario_key="new_links",
                run_profile="dev",
                strict_validation=True,
            )
            self.assertFalse(report["ok"])
            statuses = {(row["name"], row["status"]) for row in report.get("checks", [])}
            self.assertIn(("mario_placeholder_inputs", "error"), statuses)

    def test_environment_setup_can_allow_placeholder_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            settings = replace(_build_settings(base), development_engine="mario")
            _seed_mario_inputs(settings.config_dir)
            (settings.config_dir / "mario_inputs" / "employment_intensity.csv").write_text(
                "mario_region,mario_sector,jobs_per_musd_direct,jobs_per_musd_total,reference_year,source,notes\nEast_Africa,Gas_supply_chain,4.0,7.0,2019,seeded_placeholder_v1,seeded placeholder estimate\n",
                encoding="utf-8",
            )
            report = build_environment_setup_report(
                settings=settings,
                queue_stats={"capacity": 2, "active_jobs": 0},
                energy_scenario_key="new_links",
                run_profile="dev",
                strict_validation=True,
                allow_placeholder_data=True,
            )
            self.assertTrue(report["ok"])
            statuses = {(row["name"], row["status"]) for row in report.get("checks", [])}
            self.assertIn(("mario_placeholder_inputs", "warn"), statuses)


class MarioRuntimeTests(unittest.TestCase):
    def test_mario_inputs_health_detects_missing_and_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            health_missing = mario_inputs_health(config_dir)
            self.assertFalse(health_missing["ok"])
            _seed_mario_inputs(config_dir)
            health_present = mario_inputs_health(config_dir)
            self.assertTrue(health_present["ok"])
            self.assertTrue(health_present["expert_inputs_ready"])

    def test_mario_inputs_health_detects_seeded_placeholder_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            _seed_mario_inputs(config_dir)
            (config_dir / "mario_inputs" / "scenario_assumptions.csv").write_text(
                "assumption_key,scenario_key,value,unit,effective_year,source,notes\ncarbon_price,new_links,10,usd_per_tco2,2019,seeded_placeholder_v1,seeded placeholder carbon path\n",
                encoding="utf-8",
            )
            health = mario_inputs_health(config_dir)
            self.assertIn("scenario_assumptions.csv", health["placeholder_files"])

    def test_run_mario_io_runtime_produces_development_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            config_dir = base / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            _seed_mario_inputs(config_dir)

            exchange_dir = base / "exchange"
            exchange_dir.mkdir(parents=True, exist_ok=True)
            (exchange_dir / "investment_shocks.csv").write_text(
                "\n".join(
                    [
                        "run_id,scenario,year,region,location,technology,mario_sector,shock_channel,tech_group,shock_value_musd",
                        "run1,new_links,2019,East_Africa,EGY,PV_New,Electrical_equipment,capex,VRE,10.0",
                    ]
                ),
                encoding="utf-8",
            )
            (exchange_dir / "operating_shocks.csv").write_text(
                "\n".join(
                    [
                        "run_id,scenario,year,region,location,technology,mario_sector,shock_channel,tech_group,shock_value_musd",
                        "run1,new_links,2019,East_Africa,EGY,CCGT_pp,Gas_supply_chain,opex,Fossil,5.0",
                        "run1,new_links,2019,East_Africa,EGY,CCGT_pp,Maintenance_services,opex,Fossil,2.0",
                    ]
                ),
                encoding="utf-8",
            )

            development, runtime_meta, warnings = run_mario_io_runtime(
                exchange_dir=exchange_dir,
                config_dir=config_dir,
                run_id="run1",
                scenario="new_links",
                year=2019,
            )
            self.assertEqual(development["method"], "mario_io_runtime_v1")
            self.assertGreater(development["totals"]["jobs_total"], 0.0)
            self.assertTrue(development["by_region"]["records"])
            self.assertTrue(runtime_meta["mario_runtime_executed"])
            self.assertEqual(warnings, [])

    def test_run_mario_io_runtime_returns_zero_payload_when_shocks_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            config_dir = base / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            _seed_mario_inputs(config_dir)

            exchange_dir = base / "exchange"
            exchange_dir.mkdir(parents=True, exist_ok=True)
            header = "run_id,scenario,year,region,location,technology,mario_sector,shock_channel,tech_group,shock_value_musd\n"
            (exchange_dir / "investment_shocks.csv").write_text(header, encoding="utf-8")
            (exchange_dir / "operating_shocks.csv").write_text(header, encoding="utf-8")

            development, runtime_meta, warnings = run_mario_io_runtime(
                exchange_dir=exchange_dir,
                config_dir=config_dir,
                run_id="run-empty",
                scenario="new_links",
                year=2019,
            )
            self.assertEqual(development["totals"]["jobs_total"], 0.0)
            self.assertEqual(runtime_meta["shock_record_count"], 0)
            self.assertTrue(runtime_meta["mario_runtime_executed"])
            self.assertTrue(any("no exchange shock rows" in w.lower() for w in warnings))

    def test_exchange_builder_falls_back_to_summary_monetary_totals(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            settings = _build_settings(base)
            _seed_mario_inputs(settings.config_dir)
            run_dir = settings.runs_dir / "abcd1234"
            run_dir.mkdir(parents=True, exist_ok=True)
            req = RunRequest(energy_scenario_key="new_links", mrio_scenario_id="ZA-S2", target_year=2030, run_profile="dev", strict_validation=False, allow_placeholder_data=True, levers=LeverValues())

            class _NoCostModel:
                results = {}

            summary = {
                "system_cost": {"records": [{"costs": "monetary", "value": 2_500_000.0}]},
                "summary_diagnostics": {
                    "reliability": {"demand_total": 1000.0, "unserved_total": 0.0},
                    "trade_matrix": {},
                    "cost_decomposition": {"component_records": [], "class_totals": {"records": []}},
                },
            }

            _, shock_meta, _, warnings = _write_exchange_files_for_mario(
                model=_NoCostModel(),
                settings=settings,
                req=req,
                run_id="abcd1234",
                run_dir=run_dir,
                summary_diagnostics=summary["summary_diagnostics"],
                summary=summary,
            )
            self.assertGreater(shock_meta["total_rows"], 0)
            self.assertTrue(shock_meta["fallback_exchange_used"])
            self.assertTrue(any("fell back to summary-based allocation" in w for w in warnings))

    def test_exchange_builder_uses_cost_var_for_operating_shocks_when_om_components_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            settings = _build_settings(base)
            _seed_mario_inputs(settings.config_dir)
            run_dir = settings.runs_dir / "efgh5678"
            run_dir.mkdir(parents=True, exist_ok=True)
            req = RunRequest(energy_scenario_key="new_links", mrio_scenario_id="ZA-S2", target_year=2030, run_profile="dev", strict_validation=False, allow_placeholder_data=True, levers=LeverValues())

            import pandas as pd

            class _FakeDA:
                def __init__(self, rows):
                    self._rows = rows

                def to_dataframe(self, name="value"):
                    return pd.DataFrame(self._rows)

            class _FakeModel:
                def __init__(self):
                    self.results = {
                        "cost_investment": _FakeDA(
                            [
                                {
                                    "costs": "monetary",
                                    "loc_techs_investment_cost": "EGY::PV_New",
                                    "value": 2_000_000.0,
                                }
                            ]
                        ),
                        "cost_var": _FakeDA(
                            [
                                {
                                    "timesteps": "2019-01-01 00:00:00",
                                    "costs": "monetary",
                                    "loc_techs_om_cost": "EGY::CCGT_pp",
                                    "value": 7_000_000.0,
                                },
                                {
                                    "timesteps": "2019-01-01 00:00:00",
                                    "costs": "monetary",
                                    "loc_techs_om_cost": "EGY::PV_New",
                                    "value": 3_000_000.0,
                                },
                            ]
                        ),
                    }

            summary = {
                "system_cost": {"records": [{"costs": "monetary", "value": 12_000_000.0}]},
                "summary_diagnostics": {
                    "reliability": {"demand_total": 1000.0, "unserved_total": 0.0},
                    "trade_matrix": {},
                    "cost_decomposition": {"component_records": [], "class_totals": {"records": []}},
                },
            }

            _, shock_meta, _, warnings = _write_exchange_files_for_mario(
                model=_FakeModel(),
                settings=settings,
                req=req,
                run_id="efgh5678",
                run_dir=run_dir,
                summary_diagnostics=summary["summary_diagnostics"],
                summary=summary,
            )
            self.assertGreater(shock_meta["operating_rows"], 0)
            self.assertFalse(shock_meta["fallback_exchange_used"])
            source_map = shock_meta.get("source_variable_by_component") or {}
            self.assertEqual(source_map.get("variable_con"), "cost_var")
            self.assertEqual(source_map.get("variable_prod"), "cost_var")
            self.assertFalse(any("cost_var" in w for w in warnings))

    def test_auto_engine_falls_back_to_surrogate_on_mario_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = _build_settings(Path(tmp))
            settings = replace(settings, development_engine="auto", mario_fail_on_error=False)
            req = RunRequest(energy_scenario_key="new_links", mrio_scenario_id="ZA-S2", target_year=2030, run_profile="dev", strict_validation=False, allow_placeholder_data=True, levers=LeverValues())
            summary = {"summary_diagnostics": {}, "warnings": []}
            expected = (
                {"method": "surrogate_test"},
                {"development_impacts_json": "/api/run/x/development"},
                {"development_engine_mode": "surrogate"},
                ["fallback warning"],
            )
            with patch("api_service.runner._build_mario_development_outputs", side_effect=RuntimeError("boom")):
                with patch("api_service.runner._build_surrogate_development_outputs", return_value=expected) as patched:
                    out = _build_development_outputs(
                        settings=settings,
                        model=object(),
                        summary=summary,
                        req=req,
                        run_id="x",
                        run_dir=Path(tmp),
                        development_model_config={},
                        mapping_quality={},
                        scenario_package=_scenario_package(),
                    )
                    self.assertEqual(out[0]["method"], "surrogate_test")
                    self.assertTrue(patched.called)


if __name__ == "__main__":
    unittest.main()
