# EDIM MVP

Minimal single-user workbench for integrated energy-development scenario runs.

Full technical documentation is in:

- [SYSTEM_DOCUMENTATION.md](SYSTEM_DOCUMENTATION.md)

## Data status

The repository now ships with seeded placeholder expert datasets so the full workflow can run end-to-end without empty
tables. These seeded values are internally coherent and materially better than the original 4-row samples, but they are
still placeholders. They should not be treated as project-calibrated evidence.

If you run with `analysis` or `full` profile, or with `strict validation` enabled in `dev`, the backend will fail early
when placeholder expert data are present unless you explicitly enable `Allow placeholder data` in the frontend.

### Placeholder datasets that must be replaced by domain experts

1. `inputs/mario_inputs/employment_intensity.csv`
   - Purpose: direct and total jobs intensities used by the MARIO development runtime.
   - Current status: now populated with seeded placeholder rows covering 5 MARIO regions and 10 energy-relevant sectors.
   - Required action: replace every placeholder row with calibrated `jobs_per_musd_direct` and `jobs_per_musd_total`
     values for each `(mario_region, mario_sector)` combination that can appear in exchange shocks.
   - Completion rule: no placeholder rows remain; `source` cites the real study/database; `reference_year` matches the
     monetary basis of the MARIO table.

2. `inputs/mario_inputs/value_added_intensity.csv`
   - Purpose: GVA and household-income multipliers used by the MARIO development runtime.
   - Current status: now populated with seeded placeholder rows covering 5 MARIO regions and 10 energy-relevant sectors.
   - Required action: replace every placeholder row with calibrated `gva_per_musd_output` and
     `household_income_per_musd_output` values for each `(mario_region, mario_sector)` used by the model.
   - Completion rule: no placeholder rows remain; `source` cites the real evidence base; units are consistent with the
     MARIO monetary year.

3. `inputs/mario_inputs/scenario_assumptions.csv`
   - Purpose: exogenous scenario assumptions used by integrated indicator reporting.
   - Current status: now populated with seeded placeholder rows for the active EDIM scenario keys plus `baseline`.
   - Required action: replace placeholder rows with scenario-specific or `baseline` assumptions. The runtime currently
     consumes matched assumptions for indicator reporting, especially `carbon_price`; unmatched rows are preserved as
     metadata.
   - Completion rule: no placeholder rows remain in the matched scenario/baseline rows; `scenario_key` values are real
     scenario identifiers or `baseline`; units are explicit.

4. `inputs/generated/africa_national_mrio_placeholder_scenarios.json`
   - Purpose: national target-pathway records used when the integrated scenario setup chooses `S1` or `S2`; the MRIO
     shock-mapping selector only controls how those targets become A/Z, E, and Y shock rows.
   - Current status: generated from `Energy Modelling Scenario Report.docx` plus the African country seed list. South
     Africa uses the dedicated `ZA-S1`/`ZA-S2` report records; every other African country uses `WF-S1`/`WF-S2`
     Rest-of-Africa assumptions as a national placeholder.
   - Required action: replace placeholder country records with expert national MRIO scenario assumptions when available,
     preserving the `S1` full-decarbonization and `S2` national-policy-target archetype structure.
   - Completion rule: each national record has country-specific provenance, no non-South-Africa record depends on
     `WF-S1`/`WF-S2`, and generated diagnostics report zero placeholder national MRIO records.

### Expert-curated dataset that is seeded and usable, but still needs ownership

5. `inputs/mario_inputs/development_indicator_mapping.csv`
   - Purpose: maps modeled metrics to reported development indicators.
   - Current status: seeded with supported driver mappings and fully usable for placeholder runs.
   - The runtime currently computes all seeded rows directly from existing model outputs.

### Geospatial placeholder note

- `frontend/geo/edim_locations_placeholder.geojson` is still a placeholder geometry asset.
- When explicit subregion polygons are missing, the frontend synthesizes country subregions from centroid points and
  Voronoi partitioning inside parent-country boundaries.
- This is acceptable for exploration, not for final cartography. Replacing these shapes is a GIS task, not an energy
  calibration task.

## How experts should populate the placeholder datasets

1. Start from the active tech-sector mapping.
   - Review `inputs/mario_inputs/calliope_tech_to_mario_sector.csv`,
     `inputs/mario_inputs/capex_sector_split.csv`, and `inputs/mario_inputs/opex_sector_split.csv`.
   - Enumerate the `(mario_region, mario_sector)` pairs that can actually appear in the exchange shocks.

2. Fill intensity tables at that exact resolution.
   - `employment_intensity.csv`: one row per `(mario_region, mario_sector)`.
   - `value_added_intensity.csv`: one row per `(mario_region, mario_sector)`.
   - Avoid region averages unless no sector-specific evidence exists; if averaging is unavoidable, document it in
     `notes`.

3. Use consistent monetary conventions.
   - Intensities are interpreted per `1 MUSD` of modeled output/shock.
   - `reference_year` should match the IO table year or the deflated target year used to build the table.
   - If source data are in local currency, convert them before entry and document the FX/deflator basis in `notes`.

4. Replace placeholder provenance with real provenance.
   - Do not leave `source=placeholder`.
   - Put the actual data source or study name in `source`.
   - Use `notes` for caveats, imputation rules, and any sector aggregation.

5. Populate scenario assumptions against real scenario keys.
   - Use `scenario_key=baseline` for shared defaults.
   - Use an exact EDIM scenario key when an assumption is scenario-specific.
   - Keep `unit` explicit, for example `usd_per_tco2`, `multiplier`, `index`.

6. Validate before treating results as final.
   - In the UI, select `analysis` or `full` profile, or enable `Strict validation` in `dev`.
   - If you need to run with the seeded datasets temporarily, enable `Allow placeholder data`.
   - The run should pass environment setup without:
     - placeholder expert datasets
     - incomplete MARIO mappings
     - invalid CAPEX/OPEX share groups
   - The resulting run-level diagnostics should show:
     - `Fallback exchange: no`
     - `Surrogate fallback: no`
     - `Placeholder rows: 0`

## Quickstart

### 1) Python version

Use Python `3.11`.

### 2) Backend setup

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
uvicorn api_service.main:app --reload --port 8000
```

### 3) Open the app

- `http://127.0.0.1:8000/ui/`

### 4) Queue a run

1. Select scenario and run profile.
2. Confirm **Environment setup** is ready.
3. Click **Queue run**.
4. Monitor status in the jobs panel.

### 5) Outputs

Run artifacts are written to:

- `outputs/runs/<run_id>/`

Main outputs include:

- `results.csv`
- `summary.json`
- `development_impacts.json`
- `integrated_results.json`
- `report.md`
- `exchange_bundle.zip`

## Recommended workflow for final runs

1. Run `dev` with strict validation on to catch configuration/data issues cheaply.
2. Once strict `dev` passes, run `analysis` or `full`.
3. Review the run-level diagnostics in the UI before using the outputs externally.

## New model quality diagnostics

The workbench now exposes a synthesized model-quality layer so users do not have to infer trustworthiness from raw
warnings alone.

- `Model quality`
  - Combines placeholder usage, fallback coupling paths, mapping coverage, warning count, CO2 method consistency, and
    pool energy-balance residuals into a score and status.
  - Status values:
    - `production_ready`
    - `analyst_review`
    - `exploratory_only`

- `Metric resolution`
  - Shows the model-native resolution of each major output and what the filtered UI can safely display.
  - This is the main guardrail against country-level interpretation of region-only development outputs.

- `System structure`
  - Reports renewable / zero-carbon / fossil generation shares and generation by reporting group.

- `Emissions and energy balance`
  - Physical emissions now prefer direct `cost[costs=co2]` accounting when available.
  - The backend also computes pool-level balance residuals so generation, trade, demand, and unmet demand can be
    checked for consistency.

When reviewing a run, treat the following as blocking for decision-grade use:

1. `Model quality = exploratory_only`
2. `Fallback exchange = yes`
3. `Surrogate fallback = yes`
4. `Placeholder rows > 0`
5. Large pool balance residuals or CO2 method gaps

## Dashboard UI structure

The frontend is now organized as a fixed dashboard rather than a long scrolling report:

1. Left rail: scenario design, lever controls, validation mode, and environment readiness.
2. Center canvas: tabbed analysis workspace for `Overview`, `Energy system`, `Development`, and `Method`.
3. Right rail: active operations, selected job details, and recent run history.

The design intent is to keep configuration, operations, and analysis visible at the same time so users do not have to
scroll between setup and results to maintain context.

## Unified Scenario Architecture

EDIM now uses one integrated scenario package per run. Users configure:

- `energy_scenario_key`: the Calliope energy pathway.
- `mrio_scenario_id`: the integrated target pathway id, currently `S1` for full decarbonization or `S2` for national policy target. The name is retained in the request payload, but the UI presents it as a target pathway rather than an MRIO shock selector.
- `target_year`: the year used for report-derived MRIO assumptions.
- `run_profile`, validation mode, placeholder-data mode, and levers.

The backend routes that package through two channels:

- Energy channel: `IntegratedScenarioPackage -> Calliope adapter -> Calliope solve -> bridge exchange CSVs`.
- MRIO-direct channel: `IntegratedScenarioPackage target pathway -> MRIO shock mapping adapter -> heuristic A/Z, E, Y inputs`.

For now, the system keeps bridge-derived and MRIO-direct outputs side by side. If both channels overlap, headline
development totals default to the Calliope bridge-derived values. The report-derived MRIO-direct effects are retained as
diagnostic/secondary outputs and explicitly marked `mrio_direct_heuristic_v1`.

Run artifacts include:

- `scenario_package.json`
- `scenario/energy_input_manifest.json`
- `scenario/report_scenario_reference.json`
- `scenario/geography_alignment.json`
- `scenario/mrio_direct_inputs.json`
- `scenario/mrio_direct_shocks.csv`

The scenario report parser reads `Energy Modelling Scenario Report.docx` from the repository root and caches normalized
scenario data in `inputs/generated/scenario_report_scenarios.json`. The backend also generates
`inputs/generated/africa_national_mrio_placeholder_scenarios.json`, which expands the UI-level `S1`/`S2` selection to
one national MRIO record per African country. South Africa uses the dedicated report data; other African countries use
Rest-of-Africa report assumptions until expert national records are supplied. Caches are keyed by source SHA/provenance
and are rebuilt automatically when the report changes.

Geography alignment is controlled by `inputs/scenario_geography_mapping.csv`. National target scenarios fan out to mapped
Calliope subnational locations for the same parent country. Regional MRIO scenarios fan out to mapped country/location
rows. Mismatches only block when both sides expose incompatible subnational groupings.

## Useful commands

### Unit tests

```bash
cd backend
python -m unittest discover -s tests -p "test_*.py"
```

### Smoke checks

```bash
cd backend
source .venv/bin/activate
python tools/smoke_check.py
python tools/smoke_check.py --run-model
python tools/model_readiness_audit.py --scenario new_links
python tools/model_readiness_audit.py --scenario new_links --run-id <run_id>
```

### Docker

```bash
docker compose up --build
```
