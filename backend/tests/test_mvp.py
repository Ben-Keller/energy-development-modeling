from __future__ import annotations

import tempfile
import time
import unittest
import multiprocessing as mp
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from fastapi import HTTPException

from api_service.integrated import (
    build_baseline_comparison,
    build_integrated_results,
    build_run_report_markdown,
    create_exchange_bundle_zip,
    validate_integrated_results,
)
from api_service.jobs import JobManager, JobQueueFullError
from api_service.levers import load_lever_mappings
from api_service.main import _read_summary_json
from api_service.mario_runtime import mario_inputs_health, run_mario_io_runtime
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
        "scenario": "new_links",
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
        "calliope_tech,mario_region,mario_sector,opex_type,share\nCCGT_pp,East_Africa,Gas_supply_chain,fuel,0.7\nCCGT_pp,East_Africa,Maintenance_services,om,0.3\n",
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
    (mario_dir / "exchange_output_schema.csv").write_text(
        "file_name,column_name,required,dtype,description\nenergy_service_balance.csv,run_id,yes,string,x\n",
        encoding="utf-8",
    )
    return mario_dir


class SchemaTests(unittest.TestCase):
    def test_run_request_profile_normalization(self):
        req = RunRequest(scenario="new_links", run_profile="analysis", fast_dev_mode=False)
        self.assertEqual(req.run_profile, "analysis")
        self.assertTrue(req.fast_dev_mode)

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

    def test_validate_integrated_results_rejects_missing_metric(self):
        payload = build_integrated_results(_summary_template("run1"))
        payload["integrated_overview"]["metrics"] = [
            row for row in payload["integrated_overview"]["metrics"] if row.get("key") != "jobs_total"
        ]
        with self.assertRaises(ValueError):
            validate_integrated_results(payload)

    def test_build_baseline_comparison_returns_deltas(self):
        current = build_integrated_results(_summary_template("run-current"))
        baseline_summary = _summary_template("run-base")
        baseline_summary["system_cost"]["records"][0]["value"] = 120.0
        baseline = build_integrated_results(baseline_summary)

        comparison = build_baseline_comparison(
            current_integrated=current,
            baseline_integrated=baseline,
            baseline_scenario="2040_STEPS",
            baseline_run_id="run-base",
        )
        self.assertEqual(comparison["status"], "found")
        self.assertTrue(comparison["metrics"]["records"])


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
            "scenario": "new_links",
            "fast_dev_mode": True,
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
                    "scenario": req.scenario,
                    "fast_dev_mode": req.fast_dev_mode,
                    "warnings": [],
                }
                return run_id, summary, [], settings.runs_dir

            req = RunRequest(scenario="new_links", fast_dev_mode=True, levers=LeverValues())
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
                    "scenario": req.scenario,
                    "fast_dev_mode": req.fast_dev_mode,
                    "warnings": [],
                }
                return run_id, summary, [], settings.runs_dir

            req = RunRequest(scenario="new_links", fast_dev_mode=True, levers=LeverValues())
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
                    "scenario": req.scenario,
                    "fast_dev_mode": req.fast_dev_mode,
                    "warnings": [],
                }
                return run_id, summary, [], settings.runs_dir

            req = RunRequest(scenario="new_links", fast_dev_mode=True, levers=LeverValues())
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
                    "scenario": req.scenario,
                    "fast_dev_mode": req.fast_dev_mode,
                    "warnings": [],
                }
                return run_id, summary, [], settings.runs_dir

            req = RunRequest(scenario="new_links", fast_dev_mode=True, levers=LeverValues())
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
                        "key,title,description,tags,policy_question,baseline_scenario,expected_tradeoff,user_label,demand_multiplier,renewables_capex_multiplier,fossil_fuel_price_multiplier,carbon_price_usd_per_tco2",
                        "s1,Scenario 1,,policy,,,,,1.0,1.0,1.0,40",
                        "s2,Scenario 2,,ndc|2040,,,,,1.0,1.0,1.0,",
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
                scenario="",
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
                scenario="",
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
                scenario="",
                run_profile="dev",
            )
            self.assertFalse(report["ok"])
            statuses = {(row["name"], row["status"]) for row in report.get("checks", [])}
            self.assertIn(("mario_inputs", "error"), statuses)


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
            req = RunRequest(scenario="new_links", fast_dev_mode=True, levers=LeverValues())

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
            req = RunRequest(scenario="new_links", fast_dev_mode=True, levers=LeverValues())

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
            req = RunRequest(scenario="new_links", fast_dev_mode=True, levers=LeverValues())
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
                    )
                    self.assertEqual(out[0]["method"], "surrogate_test")
                    self.assertTrue(patched.called)


if __name__ == "__main__":
    unittest.main()
