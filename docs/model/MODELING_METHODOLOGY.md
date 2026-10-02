# EDIM Modeling Methodology

Document status: modeling-team handoff  
Implementation baseline: EDIM runtime `0.1.0`  
Last verified against the repository: 2026-07-19

## 1. Purpose and audience

This document describes the modeling methods currently implemented in the Energy-Development Integrated Modeling (EDIM) platform. It is written for energy-system, input-output, development-economics, data, and validation specialists who need to review, calibrate, or extend the model.

It answers five questions:

1. What does the current runtime calculate?
2. How do scenarios and user controls alter the calculation?
3. Which datasets feed each stage, and how ready are they?
4. Which outputs can be interpreted now, and with what caveats?
5. What must be completed before the results are suitable for policy-grade use?

This document describes the code as implemented. It does not treat interface labels, planned modules, or seeded data as evidence that a method is scientifically complete.

## 2. Current methodological status

EDIM currently supports two executable architectures:

| Architecture | Implemented calculation | Current use |
| --- | --- | --- |
| `energy-only` | Calliope-Africa capacity expansion and dispatch, followed by energy summaries and diagnostics | Energy-system exploration and technical validation |
| `energy-development` | The energy calculation plus an energy-to-development bridge and coefficient-based development impact estimates | Integrated workflow testing and analyst review |

Current module status:

| Module | Runtime status | Scientific status |
| --- | --- | --- |
| Calliope | Executable | Requires a formal source inventory, calibration, benchmark runs, and scenario sign-off |
| Energy-to-MRIO bridge | Executable | Mapping logic is explicit, but monetary units, sector coverage, and treatment of negative shocks require review |
| Development impact estimator | Executable | Uses regional/sector intensity multiplication; it is not yet a full MRIO Leontief calculation |
| MRIO-direct scenario channel | Executable | Explicitly heuristic and retained for comparison, not headline results |
| OSeMOSYS | Planned only | No executable package or validated model is present |

The repository contains seeded placeholder values for employment intensity, value-added intensity, and scenario assumptions. These allow end-to-end execution, but the resulting development impacts are not policy-grade estimates. `analysis` and `full` profiles enforce strict validation and reject these values unless placeholder use is explicitly allowed.

## 3. Method at a glance

```text
Integrated scenario package
  |-- energy pathway and policy levers
  |-- target pathway, year, and geography
  |-- dataset-version snapshot
  v
Calliope-Africa optimization
  |-- generation and capacity
  |-- system cost and emissions
  |-- reliability and power-pool trade
  v
Energy-to-development bridge
  |-- technology/location monetary components
  |-- CAPEX, OPEX, and fuel supplier-sector shocks
  v
Coefficient-based development calculation
  |-- jobs = positive shock x employment intensity
  |-- GVA = positive shock x value-added intensity
  |-- household income proxy = positive shock x income intensity
  v
Integrated results
  |-- bridge-derived headline totals
  |-- heuristic MRIO-direct channel shown separately
  |-- quality, uncertainty, provenance, and resolution metadata
```

The canonical implementation is in:

- `model_runtime/edim_model/core/edim_pipeline.py`
- `model_runtime/edim_model/core/runner.py`
- `model_runtime/edim_model/core/scenario_package.py`
- `model_runtime/edim_model/core/mario_runtime.py`
- `model_runtime/edim_model/core/integrated.py`

The detailed machine-readable input/output inventory is [EDIM_model_io_catalog.csv](EDIM_model_io_catalog.csv).

## 4. Scenario definition

### 4.1 Canonical package

Every run is represented by an `integrated_scenario_package_v1` object. It binds together:

- model architecture;
- energy model engine;
- Calliope energy pathway;
- development target pathway and year;
- optional MRIO shock mapping;
- user policy levers;
- geography alignment;
- structured scenario-source provenance;
- submitted dataset versions.

The package is written into the run directory before execution. It should be treated as the canonical record of what was requested; reports and dashboards should not reconstruct a scenario from labels alone.

### 4.2 Energy pathways

Energy pathways are the scenario keys declared in Calliope's `overrides.yaml`, enriched with labels and preset levers from `inputs/scenario_metadata.csv`. The current catalog contains:

- transmission-only expansion;
- 2040 STEPS and Announced Commitments demand pathways;
- combinations of legacy or expandable generation and transmission;
- policy variants.

The scenario key determines which Calliope override imports are active. It does not by itself define the development target pathway.

### 4.3 Development target pathways

The development channel uses a target scenario id, target year, and optional structured shock-mapping id. Current national African S1/S2 records are generated as placeholders:

- South Africa uses the corresponding South Africa scenario record where available;
- other African countries inherit Rest-of-Africa assumptions until country-specific records are supplied;
- country aliases and model locations are aligned through `scenario_geography_mapping.csv`.

This fallback is a known assumption, not a country forecast.

### 4.4 Policy levers

The UI exposes four numerical levers:

| Lever | Runtime action |
| --- | --- |
| Demand multiplier | Scales the loaded Calliope `resource` values for `Demand_power` technologies after model build |
| Renewable CAPEX multiplier | Scales `costs.monetary.energy_cap` for mapped renewable technologies |
| Fossil fuel price multiplier | Scales `costs.monetary.om_con` for mapped fossil technologies |
| Carbon price | Sets the Calliope CO2 objective cost-class weight and is also available to integrated reporting |

Technology families and target key paths are data-driven through `inputs/lever_mappings.csv`. Wildcards are resolved against the loaded Calliope technology library. The generated patch is saved as `inputs/runtime/ui_override_patch.yaml` in the run package.

Modeling review is still required to confirm that the carbon-price value and Calliope CO2 cost-class units form a dimensionally correct monetary penalty.

### 4.5 Year semantics

The current system carries several year concepts that are not a single dynamic timeline:

- Calliope time-series coordinates use 2019 timestamps;
- STEPS and Announced Commitments pathway labels describe 2040 demand assumptions;
- the development target selector typically refers to 2030 or 2050;
- bridge records are labeled with the selected development target year;
- seeded development coefficients generally use a 2019 reference and monetary basis.

Selecting a development target year does not independently advance or interpolate the Calliope model. It selects the structured development assumptions and labels bridge outputs. Before cross-year claims are made, the modeling team must approve how energy pathway year, weather/profile year, coefficient year, target year, currency basis, and any discounting or deflation relate.

## 5. Energy-system model

### 5.1 Engine and scope

The current executable engine is Calliope `0.6.10`, using the bundled Calliope-Africa model. It represents national and subnational locations grouped into the CAPP, EAPP, NAPP, SAPP, and WAPP power pools, with generation, demand, storage, and transmission technologies defined in YAML and hourly profiles stored in CSV files.

The optimization runs in Calliope planning mode. The base objective minimizes weighted system cost:

```text
minimize sum(monetary cost components x monetary weight)
       + sum(CO2 cost components x CO2 weight)
```

The base model uses a monetary weight of `1` and a CO2 weight of `0`; a run-level carbon-price lever can change the latter. Constraints include technology resource availability, efficiencies, capacity bounds, transmission limits and losses, storage behavior, demand balance, and scenario-specific expansion or policy limits.

`ensure_feasibility` is enabled, so unmet demand can appear through feasibility mechanisms and must be reviewed in reliability diagnostics rather than assuming every solution fully serves demand.

### 5.2 Scenario variants

The primary 2040 families are:

- STEPS demand;
- Announced Commitments demand;
- existing versus expandable generation;
- existing versus expandable transmission;
- optional policy constraints.

The exact imported files for each variant are defined in `model_runtime/model_modules/calliope/Calliope-Africa-main/overrides.yaml`.

### 5.3 Temporal profiles

| Profile | Time window | Solver time limit | Validation behavior | Intended use |
| --- | --- | --- | --- | --- |
| `dev` | 2019-01-01 to 2019-01-02 | 3,600 seconds | Strict only when requested | Software and pipeline checks |
| `analysis` | 2019-01-01 to 2019-03-31 | 14,400 seconds | Strict by default | Intermediate analyst review |
| `full` | Model's full configured year | 14,400-second runtime process limit; no profile-specific solver limit | Strict by default | Full-resolution runs after calibration |

The shortened profiles are temporal samples, not statistically weighted representative periods. Their annual cost, generation, reliability, or development totals must not be compared with full-year outputs as if they had equivalent temporal coverage.

### 5.4 Energy outputs

The summarization layer extracts:

- generation by technology and time;
- installed and new capacity;
- monetary and CO2 cost classes;
- physical emissions derived from production and emission factors;
- demand, served energy, unmet demand, and unserved-energy share;
- transmission and power-pool trade diagnostics;
- component-level monetary activity used by the development bridge.

Native energy results are exported to `results.csv`; dashboard-ready aggregates and diagnostics are stored in `summary.json`.

### 5.5 Energy-model evidence gaps

The Calliope files contain many inline source links, but there is no consolidated data dictionary recording source title, publisher, version, access date, geography, reference year, transformation, license, and reviewer for every parameter and time series. The minimal bundled README also does not document calibration or benchmark performance. These are blocking gaps for a defensible model release.

## 6. Energy-to-development bridge

### 6.1 Purpose

The bridge translates solved energy-model monetary activity into supplier-sector shocks that the development layer can consume. It does not pass generation directly into employment multipliers.

### 6.2 Transformation

For each available technology-location monetary component, the bridge:

1. classifies it as investment, fixed/variable OPEX, or fuel consumption;
2. maps the Calliope location to a power pool and development region;
3. maps the technology/component to a default development supplier sector and shock channel;
4. applies CAPEX or OPEX split shares, normalized to sum to one for the matched group;
5. aggregates records by run, scenario, year, region, location, technology, sector, and channel;
6. writes investment and operating shock tables in million USD units.

Conceptually, for technology-location component `c` and supplier sector `s`:

```text
shock[c,s] = max(component_value[c], 0) x normalized_split_share[c,s]
```

The current implementation clips non-positive component values to zero. It therefore estimates activity supported by positive spending but does not represent contraction, displacement, stranded assets, or avoided fossil-sector activity in the bridge headline channel.

### 6.3 Mapping fallback behavior

Matching follows an explicit hierarchy:

- exact technology and region;
- technology wildcard within a technology group;
- generic/default mapping;
- built-in default sector for the component type.

Missing location mappings produce `UNKNOWN` regions and warnings. Missing or invalid split rows fall back to a single default supplier sector. Mapping coverage and fallback shares are written to diagnostics and affect the model-quality status.

### 6.4 Bridge outputs

The principal exchange artifacts are:

- `calliope_component_activity.csv`;
- `investment_shocks.csv`;
- `operating_shocks.csv`;
- `prices_and_taxes.csv`;
- `energy_service_balance.csv`;
- `metadata.json` and schema-validation diagnostics.

## 7. Development impact calculation

### 7.1 Current engine

The configured engine label is `mario`, but the current built-in calculation does not load a MARIO database or solve a multiregional input-output system. `mario_db_path` is empty in the default runtime configuration.

The implemented method is a coefficient-based impact estimator. For each positive bridge shock in region `r` and supplier sector `s`:

```text
jobs_direct[r,s] = shock_musd[r,s] x jobs_per_musd_direct[r,s]
jobs_total[r,s]  = shock_musd[r,s] x jobs_per_musd_total[r,s]
gva_musd[r,s]    = shock_musd[r,s] x gva_per_musd_output[r,s]
income_musd[r,s] = shock_musd[r,s] x household_income_per_musd_output[r,s]
```

The runtime enforces `jobs_total >= jobs_direct`. It then sums records by region, supplier sector, and region-supplier pair.

This method does not currently calculate `x = (I - A)^-1 y`, interregional trade propagation, endogenous price effects, supply constraints, household feedbacks, fiscal closure, or dynamic adjustment. The term `MRIO` in the UI and code should therefore be read as the intended model family and data interface, not evidence that a full MRIO solve is already active.

### 7.2 Intensity matching

Employment and value-added coefficients are selected using:

1. exact region-sector match;
2. region mean;
3. global mean;
4. zero/default record.

Match counts are reported in run diagnostics. Any use of regional or global means weakens the spatial and sectoral interpretation and should be treated as a calibration warning.

### 7.3 Uncertainty

The current uncertainty treatment applies symmetric relative bounds to aggregated development totals:

```text
lower = max(value x (1 - relative_bound), 0)
upper = max(value x (1 + relative_bound), 0)
```

The default relative bound is 12 percent for jobs, GVA, and household-income metrics. These bounds are configured values, not empirically estimated confidence intervals and not a propagation of input or model uncertainty.

### 7.4 MRIO-direct scenario channel

A second development channel converts structured policy targets into heuristic shocks. It currently:

- derives fossil reductions and renewable gains from percentage targets;
- allocates renewable gains 50 percent to power-asset construction, 35 percent to electrical equipment, and 15 percent to transmission and distribution;
- uses mapped fossil supply-chain sectors for reductions;
- scales development effects using output-intensity ratios inferred from the bridge result.

The method is tagged `mrio_direct_heuristic`. It is useful for tracing scenario assumptions and comparing channels, but it is not selected for headline totals.

### 7.5 Headline selection and overlap

Both bridge and MRIO-direct outputs are retained. To avoid double counting:

- `selected_totals` use bridge-derived values;
- `combined_totals` show an unadjusted diagnostic sum;
- the dashboard exposes both source channels and an overlap warning.

`combined_totals` must not be presented as the authoritative development result until a formal channel reconciliation method is approved.

## 8. Integrated indicators

The integrated layer combines energy and selected development outputs. Current reported indicators include:

| Indicator | Current derivation | Important limitation |
| --- | --- | --- |
| Total jobs | Selected bridge total | Depends on seeded intensities; positive spending only |
| GVA | Selected bridge total | Coefficient estimate, not an endogenous IO response |
| Household income supported | Selected bridge total | Proxy from a value-added share coefficient |
| Import leakage | Supplier-name heuristic and fixed shares | Not calculated from an import matrix |
| Unserved energy share | Calliope reliability diagnostics | Profile-dependent |
| System cost | Sum of Calliope monetary cost records | Unit and annualization review required |
| Carbon cost burden | Physical emissions x selected carbon price | Reporting proxy; not an economy-wide welfare measure |

The reliability penalty proxy multiplies unserved energy by a scenario `value_of_lost_load` assumption. Import leakage uses fixed supplier-name rules. Both should remain labeled as proxies until replaced with reviewed methods.

Metric-resolution metadata states whether each result is global, location, power-pool, region, or supplier-sector level. Frontend filters must honor this metadata; a global result must not be displayed as a country-specific estimate merely because a country is selected.

## 9. Dataset inventory and readiness

The runtime dataset contract is `model_runtime/edim_model/dataset_manifest.json`. The table below summarizes the methodological role and current readiness of each group.

| Dataset or group | Current content | Readiness | Required action |
| --- | --- | --- | --- |
| Calliope model YAML | Technologies, locations, constraints, links, and costs | Executable; partially sourced inline | Build a formal source and transformation register; calibrate and benchmark |
| Calliope time series | Hourly demand, solar, wind, and hydro profiles | Executable | Document source/version and validate country coverage, reference year, missing values, and scaling |
| Energy scenario metadata | 11 scenario records plus labels/preset levers | Executable | Modeling-team sign-off on policy meaning and lever defaults |
| Lever mappings | Renewable/fossil families and Calliope key paths | Executable | Unit tests and expert review of complete technology coverage |
| Structured scenario targets | 71 analyst-readable target rows plus JSON form | Exploratory | Replace inherited regional assumptions with country-owned, cited pathways |
| Africa national S1/S2 scenarios | Generated country records | Placeholder | Replace Rest-of-Africa inheritance and approve geography-specific scenarios |
| Geography mapping | 58 mapping rows | Executable | Resolve all model locations and remove `UNKNOWN` outcomes |
| Technology-to-sector mapping | 9 rows | Seed mapping | Align names and accounts to the selected MRIO database |
| CAPEX split | 5 rows | Seed mapping | Calibrate technology/region supplier shares and document source years |
| OPEX/fuel split | 11 rows | Seed mapping | Calibrate technology/region supplier shares and document source years |
| Country-to-pool mapping | 55 rows | Executable | Verify regional aggregation and MRIO geography concordance |
| Employment intensity | 50 rows: 5 regions x 10 sectors | Seeded placeholder | Replace every placeholder row with calibrated, cited factors |
| Value-added intensity | 50 rows: 5 regions x 10 sectors | Seeded placeholder | Replace every placeholder row with calibrated, cited factors |
| Scenario assumptions | 72 rows | Seeded placeholder | Replace matched assumptions with scenario/year-specific evidence |
| Development indicator mapping | 7 rows | Technically supported | Agree indicator definitions, units, aggregation, and public claims |
| Exchange schema | 14 field rules | Executable | Extend with unit, sign, price basis, and accounting identity checks |
| Geospatial display assets | Country polygons plus placeholder subnational centroids | Mixed | Replace representative Voronoi geometry with authoritative boundaries where needed |

For every policy-grade dataset, the modeling team should record:

- owner and reviewer;
- source title, publisher, link or identifier, and license;
- source version and access date;
- reference year and price/currency basis;
- geographic and sector classification;
- transformation and imputation method;
- uncertainty or quality rating;
- checksum and effective model version.

## 10. Outputs and provenance

Each submitted run snapshots its request, scenario package, dataset manifest, model manifest, and artifact policy. The principal analytical outputs are:

| Artifact | Role |
| --- | --- |
| `results.csv` | Long-form energy-model results |
| `summary.json` | Energy aggregates, diagnostics, scenario package, and artifact catalog |
| `development_impacts.json` | Bridge, MRIO-direct, selected and combined development channels |
| `coupling_manifest.json` | Mapping coverage, methods, overlap policy, and runtime diagnostics |
| `integrated_results.json` | Dashboard/report payload with indicators, quality, resolution, and provenance |
| `report.md` | Human-readable run summary; not a computational data source |
| `exchange_bundle.zip` | Portable package of reviewed inputs and outputs |

Runs should be compared only when their architecture, profile, temporal window, geography, dataset versions, price basis, and scenario definitions are compatible. The run package contains the information needed to make that determination.

## 11. Validation and quality controls

Preflight validation checks:

- selected module and architecture support;
- Calliope model and scenario availability;
- solver readiness;
- required dataset presence and schema;
- technology, geography, and supplier mapping coverage;
- placeholder status in expert-owned datasets;
- queue and runtime settings.

Strict validation is automatically active for `analysis` and `full`. Without `allow_placeholder_data`, it blocks known placeholder employment/value-added tables and matched placeholder scenario assumptions.

Post-run quality metadata checks:

- bridge mapping coverage and fallback share;
- unknown geography and sector mappings;
- intensity match tiers;
- heuristic MRIO-direct use;
- unavailable development indicators;
- reliability and model warnings;
- metric resolution.

A technically successful run is not automatically scientifically valid. `succeeded` means the executable contract completed and artifacts passed structural checks; analytical readiness must be judged from `model_quality`, `coupling_manifest`, provenance, and the calibration record.

## 12. Remaining gaps and acceptance criteria

### Priority 0: blocks policy-grade interpretation

| Gap | Why it matters | Acceptance criterion |
| --- | --- | --- |
| Placeholder development intensities | Jobs and GVA totals currently depend on seeded values | All active region-sector pairs use cited, reviewed coefficients with reference year, unit, and uncertainty metadata; strict preflight passes without placeholder allowance |
| No full MRIO solve | Indirect and trade effects are represented only by supplied total coefficients | Select a licensed MRIO database, implement a reproducible baseline and shock solve, reconcile classifications, and validate results against an independent calculation |
| Country scenario inheritance | Most African national pathways inherit Rest-of-Africa assumptions | Country-specific pathways are approved or a documented regionalization method with uncertainty is accepted |
| Energy data provenance/calibration | Inline links are incomplete as a release record | A versioned source register, data QA report, and benchmark comparison are approved by energy model leads |
| Monetary-unit chain | Energy costs become MUSD shocks without a complete documented conversion chain | Units, currency, price year, annualization, sign convention, and scaling reconcile from Calliope component to exchange table |

### Priority 1: required for robust comparative analysis

| Gap | Why it matters | Acceptance criterion |
| --- | --- | --- |
| Negative and avoided activity | Current bridge clips non-positive shocks | Approved gross/net accounting represents gains, losses, displacement, imports, and stranded activity without double counting |
| Scenario channel overlap | Bridge and MRIO-direct channels can describe the same transition | Formal channel ownership and merge rules replace the diagnostic unadjusted sum |
| Temporal comparability | Dev/analysis profiles are partial-year samples | Full-year runs or validated representative-period weights support annual reporting; UI/report labels state the basis |
| Uncertainty method | Fixed +/-12 percent bounds are not evidence-based | Parameter distributions or scenario ranges are documented and propagated; reported intervals have a defined interpretation |
| Baseline comparison | Development impacts are spending-supported levels, not necessarily net additional effects | A canonical baseline and compatible differencing protocol are implemented and tested |
| Import leakage and reliability proxies | Current formulas use fixed heuristics | Methods are tied to reviewed import data and VOLL evidence, with sensitivity analysis |

### Priority 2: model governance and extension

| Gap | Acceptance criterion |
| --- | --- |
| Validation suite | Golden scenarios, accounting checks, regression tolerances, and expected warning sets run in CI |
| Classification governance | Technology, sector, geography, and indicator concordances have named owners and change review |
| Model versioning | Every result records code version, model/data versions, checksums, solver version, and parameter set |
| Spatial outputs | Authoritative boundaries replace placeholder subnational display geometry where spatial claims are made |
| OSeMOSYS option | Keep disabled until an executable package, manifest, scenario mapping, output adapter, and benchmark suite pass the same contract |

## 13. Recommended modeling-team review sequence

1. Agree the intended decision questions and the meaning of each scenario family.
2. Freeze the units, currency basis, reference years, and gross-versus-net accounting conventions.
3. Audit and calibrate the Calliope model and publish benchmark results.
4. Select the MRIO database and approve sector/geography concordances.
5. Replace employment, value-added, and scenario placeholder tables.
6. Validate the bridge against hand-calculated technology-location examples.
7. Implement and independently reproduce the MRIO solve.
8. Define baseline, overlap, displacement, and import treatment.
9. Propagate uncertainty and run sensitivity tests.
10. Approve public indicators and interpretation language.

## 14. Reproducing and reviewing a run

Use Python 3.11 and the repository environment. Before submitting an analytical run:

```bash
python -m edim_model.cli catalog \
  --config-dir inputs \
  --manifest model_runtime/edim_model/model_manifest.json
```

After the platform stages a bundle:

```bash
python -m edim_model.cli preflight --bundle /path/to/request_bundle.json
python -m edim_model.cli run --bundle /path/to/request_bundle.json
```

For review, retain the entire run package and inspect at minimum:

1. `inputs/request_bundle.json` and `inputs/scenario_package.json`;
2. `inputs/dataset_manifest.json` and dataset-version references;
3. `inputs/runtime/ui_override_patch.yaml`;
4. energy summary and reliability diagnostics;
5. bridge exchange tables and schema validation;
6. development intensity match counts and selected totals source;
7. `coupling_manifest.json` and `integrated_results.json.model_quality`;
8. all warnings and runtime events.

## 15. Change-control rule

Any change to a scenario definition, model equation, source dataset, mapping, unit conversion, fallback, indicator formula, uncertainty assumption, or headline-selection rule is a methodological change. Update this document, the machine-readable manifests, the model I/O catalog, and the relevant tests in the same change.
