**EDIM Technical Architecture and Requirements Handoff**

*Integrated Energy-Development Modeling Dashboard*

Prepared for frontend, backend, design, modeling, and data teams. Last updated: 2026-04-10.

# **1\. Purpose and Audience**

This document is a detailed handoff for teams carrying forward the EDIM project. It explains the current technical architecture, the unified scenario model, the runtime data flow, frontend dashboard behavior, expected API contracts, data ownership requirements, validation rules, known limitations, and the implementation roadmap needed to mature the system from a working integrated prototype into a production-grade energy-development decision-support platform.

* Frontend team: use this to understand state, API contracts, dashboard panels, filtering rules, and result provenance panels.  
* Backend team: use this to understand orchestration stages, package schemas, parser/cache behavior, run artifacts, validation, diagnostics, and extension points.  
* Design team: use this to understand primary workflows, dashboard layout requirements, visual hierarchy, map interactions, and user trust/provenance needs.  
* Energy modeling and MRIO team: use this to understand Calliope integration, bridge-derived outputs, report-derived MRIO-direct assumptions, placeholder data, and where exact MARIO matrix shock execution should replace heuristics.  
* Project/product leads: use this to understand acceptance criteria, risks, team responsibilities, and the forward roadmap.

# **2\. Executive Summary**

EDIM is an integrated energy-development modeling workbench. The backend runs an energy scenario through Calliope, converts solved energy outputs into MRIO exchange inputs, applies an MRIO/development impact layer, and returns integrated results to a dashboard UI. The current architecture has been refactored around one required IntegratedScenarioPackage per run. The user no longer configures separate energy and MRIO scenarios. Instead, each run specifies one integrated scenario definition containing an energy scenario key, an MRIO report scenario id, target year, run profile, strict validation behavior, placeholder-data behavior, and user lever selections.

The architecture intentionally keeps two development input channels side by side for now: bridge-derived outputs from solved Calliope results, and MRIO-direct scenario assumptions parsed from the root scenario report. Headline development totals currently default to the bridge-derived Calliope channel when the two overlap. The MRIO-direct channel is retained as a transparent diagnostic/source channel and is labeled mrio\_direct\_heuristic\_v1 until exact MARIO A/Z/E/Y matrix shock execution is implemented.

# **3\. Repository Map**

| Path | Primary responsibility | Team ownership |
| :---- | :---- | :---- |
| backend/api\_service/ | FastAPI app, run orchestration, jobs, scenario catalog, scenario package, report parser, Calliope to MARIO bridge, MARIO runtime, integrated result builder. | Backend and modeling engineering |
| backend/tests/ | Regression tests for schemas, parser, package generation, run artifacts, runtime outputs, integrated results, and job behavior. | Backend engineering |
| backend/tools/ | Developer tools and readiness/audit helpers. | Backend engineering |
| frontend/app.jsx | No-build React dashboard application, API client, state orchestration, scenario setup, map, charts, method/provenance panels. | Frontend and design engineering |
| frontend/index.html | Static shell, global CSS, React/Leaflet/D3/Turf/Babel browser dependencies. | Frontend engineering |
| frontend/geo/ | Placeholder/current geometry assets and geospatial README. | Frontend, GIS, and data teams |
| inputs/ | Scenario metadata, lever mappings, development model controls, geography mapping, generated report cache. | Modeling/data engineering |
| inputs/mario\_inputs/ | MRIO/development coefficients, sector mappings, country/pool mappings, placeholder expert datasets. | MRIO/data experts |
| Calliope-Africa-main/ | Calliope energy model source, overrides, technologies, locations, timeseries. | Energy modeling team |
| outputs/runs/ | Run output artifacts. Treat as generated runtime state, not source of truth. | Operations/backend |
| README.md | Quick start plus placeholder dataset instructions and high-level architecture notes. | All teams |
| SYSTEM\_DOCUMENTATION.md | System-level documentation and API/runtime description. | All teams |
| Energy Modelling Scenario Report.docx | Source report parsed into MRIO-direct scenario assumptions. | Energy/MRIO modeling experts |

# **4\. Conceptual Architecture**

The system has a single upstream run configuration and three downstream adapters. The package is the source of truth for every run. The energy adapter prepares and solves the energy model. The bridge adapter converts solved energy outputs into MARIO exchange files. The MRIO-direct adapter converts report-derived assumptions into direct MRIO shock proxies. The development runtime then consumes both bridge-derived and MRIO-direct channels and emits integrated results.

IntegratedScenarioPackage  
  \-\> Energy adapter (Calliope v1)  
      \-\> Calliope model solve  
      \-\> results.csv and summary diagnostics  
      \-\> Bridge adapter  
          \-\> exchange/investment\_shocks.csv  
          \-\> exchange/operating\_shocks.csv  
          \-\> exchange/energy\_service\_balance.csv  
  \-\> MRIO-direct adapter (mrio\_direct\_heuristic\_v1)  
      \-\> scenario/mrio\_direct\_inputs.json  
      \-\> scenario/mrio\_direct\_shocks.csv

Bridge outputs \+ MRIO-direct inputs  
  \-\> development runtime (MARIO runtime or surrogate fallback)  
  \-\> development\_impacts.json  
  \-\> coupling\_manifest.json  
  \-\> integrated\_results.json  
  \-\> frontend dashboard

# **5\. Required Run Contract**

The run request is intentionally breaking and does not preserve the legacy energy-only request shape. The backend schema uses extra="forbid", so clients must not send legacy fields such as scenario or fast\_dev\_mode. Frontend and automation clients should construct exactly this integrated request shape.

{  
  "energy\_scenario\_key": "new\_links",  
  "mrio\_scenario\_id": "ZA-S2",  
  "target\_year": 2030,  
  "run\_profile": "dev",  
  "strict\_validation": false,  
  "allow\_placeholder\_data": true,  
  "levers": {  
    "demand\_multiplier": 1.0,  
    "renewables\_capex\_multiplier": 1.0,  
    "fossil\_fuel\_price\_multiplier": 1.0,  
    "carbon\_price\_usd\_per\_tco2": 0.0  
  }  
}

| Field | Type | Requirement | Meaning |
| :---- | :---- | :---- | :---- |
| energy\_scenario\_key | string | Required | Calliope override/scenario key from the integrated catalog. This replaces the legacy top-level scenario field. |
| mrio\_scenario\_id | string | Required | Report-derived MRIO scenario id such as ZA-S1, ZA-S2, IN-S1, IN-S2, BR-S1, BR-S2, WF-S1, WF-S2, WM-S1, or WM-S2. |
| target\_year | integer | Required | Scenario target year for package construction and MRIO-direct assumption selection. Catalog currently exposes 2030, 2050, 2055, 2060, and 2070\. |
| run\_profile | dev | analysis | full | Required | Runtime profile. Analysis and full force strict\_validation true. |
| strict\_validation | boolean | Required | Fail early on degraded model readiness, placeholder expert data when not allowed, or strict-mode coupling problems. |
| allow\_placeholder\_data | boolean | Required | Allows seeded placeholder expert datasets to be used. Does not hide warnings or upgrade model quality. |
| levers | object | Required, may use defaults | User-controlled scenario levers applied to runtime override patch and downstream diagnostics. |

# **6\. Scenario Catalog and Report Parser**

The backend exposes one integrated scenario catalog from /api/scenarios. It combines Calliope override scenarios with MRIO scenarios parsed from the root Energy Modelling Scenario Report.docx. The parser uses standard DOCX ZIP/XML extraction, not an external Office dependency. Parsed output is cached by source SHA256 in inputs/generated/scenario\_report\_scenarios.json and rebuilt when the DOCX changes.

| Source | Current behavior |
| :---- | :---- |
| Calliope overrides | Read from Calliope-Africa-main/overrides.yaml and enriched by inputs/scenario\_metadata.csv. |
| Scenario report | Parsed from Energy Modelling Scenario Report.docx into normalized scenario records. |
| Generated cache | inputs/generated/scenario\_report\_scenarios.json includes source\_sha256, scenario ids, geographies, scenario labels, shock structures, targets, implementation notes, calibration notes, and provenance. |
| Catalog defaults | energy\_scenario\_key defaults to new\_links when present; mrio\_scenario\_id defaults to ZA-S2; target\_year defaults to 2030\. |
| Target years | Catalog currently exposes 2030, 2050, 2055, 2060, and 2070 from parsed target years and net-zero years. |

| Parsed scenario id | Geography code | Scenario class |
| :---- | :---- | :---- |
| ZA-S1 | ZA | Full decarbonization |
| ZA-S2 | ZA | Policy target |
| IN-S1 | IN | Full decarbonization |
| IN-S2 | IN | Policy target |
| BR-S1 | BR | Full decarbonization |
| BR-S2 | BR | Policy target |
| WF-S1 | WF | Full decarbonization |
| WF-S2 | WF | Policy target |
| WM-S1 | WM | Full decarbonization |
| WM-S2 | WM | Policy target |

# **7\. IntegratedScenarioPackage Schema**

The IntegratedScenarioPackage is persisted as scenario\_package.json in every run directory. It is the primary run configuration artifact and must be inspectable enough to reproduce a run. The object contains run-level metadata, energy adapter inputs, MRIO-direct scenario content, geography alignment, levers, validation settings, placeholder-data mode, and provenance.

{  
  "schema\_version": "integrated\_scenario\_package\_v1",  
  "created\_at\_utc": "...",  
  "energy\_scenario\_key": "new\_links",  
  "mrio\_scenario\_id": "ZA-S2",  
  "target\_year": 2030,  
  "run\_profile": "dev",  
  "levers": {...},  
  "strict\_validation": false,  
  "allow\_placeholder\_data": true,  
  "energy": {  
    "adapter": "calliope\_v1",  
    "model": "calliope",  
    "scenario\_key": "new\_links"  
  },  
  "mrio\_direct": {  
    "adapter": "mrio\_direct\_heuristic\_v1",  
    "scenario": {...parsed report scenario...},  
    "report\_source": {  
      "source\_file": ".../Energy Modelling Scenario Report.docx",  
      "source\_sha256": "..."  
    }  
  },  
  "geography\_alignment": {...},  
  "provenance": {...}  
}

| Subobject | Required content | Downstream consumers |
| :---- | :---- | :---- |
| energy | Adapter name, model family, Calliope scenario key. | Calliope model construction and energy input manifest. |
| mrio\_direct | Report scenario record, adapter method, source report file/hash. | MRIO-direct adapter, frontend provenance panels, diagnostics. |
| geography\_alignment | Mapped Calliope locations, MRIO geography, alignment level, blocking flag, notes. | MRIO-direct adapter, environment setup, frontend warning/status UI. |
| provenance | Source file/hash, package creation source, timestamp. | Run report, debugging, reproducibility, audit trail. |

# **8\. Geography Alignment Rules**

Geography alignment is defined in inputs/scenario\_geography\_mapping.csv and validated at package creation time. The current Calliope model is Africa-focused, while the report includes South Africa, India, Brazil, Rest of Africa, and Rest of Middle East. Therefore the mapping must distinguish aligned energy/MRIO geographies from MRIO-only report geographies.

* National MRIO scenarios apply to all Calliope locations with the same parent country when Calliope has subnational groupings.  
* Regional MRIO scenarios apply to all mapped Calliope countries and locations in the MRIO region.  
* MRIO-only geographies are allowed when Calliope has no matching energy model location. They remain valid report-derived MRIO assumptions but cannot be spatially aligned to Calliope locations.  
* A blocking mismatch occurs only when MRIO and Calliope both expose subnational groupings and no one-to-one or many-to-one mapping exists.  
* The alignment artifact is persisted as scenario/geography\_alignment.json for every run.

| Mapping case | Current handling |
| :---- | :---- |
| ZA | Maps to ZAF. If Calliope later adds South Africa subregions, national MRIO should fan out to those subregions unless MRIO also becomes subnational. |
| WF | Rest of Africa fans out to mapped non-ZAF Calliope locations, including current national and subnational location ids. |
| IN and BR | Parsed report scenarios are retained as MRIO-only because Calliope-Africa currently has no matching location. |
| WM | Parsed report scenario is retained as MRIO-only because current Calliope-Africa does not represent this geography. |

# **9\. Backend Runtime Sequence**

The orchestrator emits explicit progress stages. The stage names should remain stable enough for frontend progress display and run debugging. The development stage currently wraps both bridge runtime execution and MRIO-direct attachment because direct inputs are attached alongside development-impact construction.

| Stage | What happens | Primary outputs |
| :---- | :---- | :---- |
| scenario\_prepare | Build IntegratedScenarioPackage from request, parsed report, geography mapping, and levers. | scenario\_package.json, initial scenario/ artifacts. |
| energy\_input\_prepare | Load lever mappings, tech library, development model config, mapping quality, strict-validation checks, solver runtime patch. | ui\_override\_patch.yaml, validation warnings/errors. |
| build\_model | Load Calliope, patch solver integration, instantiate model with selected energy\_scenario\_key and runtime patch. | In-memory Calliope model. |
| solve\_energy | Run Calliope optimization. | In-memory solved model results. |
| write\_artifacts | Write general Calliope results CSV. | results.csv. |
| build\_summary | Build summary payload and diagnostics from solved Calliope results. | summary fields, summary\_diagnostics. |
| bridge\_prepare | Prepare Calliope-to-MRIO bridge exchange outputs. | exchange/\*.csv and bridge diagnostics. |
| mrio\_direct\_prepare | Prepare report-derived MRIO-direct inputs. | scenario/mrio\_direct\_inputs.json, scenario/mrio\_direct\_shocks.csv. |
| development | Run MARIO runtime or surrogate fallback and attach bridge/direct source channels. | development\_impacts.json, coupling\_manifest.json. |
| build\_integrated | Build integrated result payload, baseline comparison, model quality, indicators, and run report. | integrated\_results.json, run\_report.md, summary.json. |

# **10\. Development Output Channel Policy**

The current implementation explicitly keeps bridge-derived and MRIO-direct effects separate. This is deliberate. Some report-derived MRIO assumptions overlap conceptually with Calliope-derived bridge outputs. Until exact MARIO A/Z/E/Y matrix shock execution is implemented and overlap logic is removed, bridge-derived Calliope results are authoritative for headline totals.

development\_impacts \= {  
  "bridge": {...bridge-derived development payload...},  
  "mrio\_direct": {...report-derived heuristic payload...},  
  "selected\_totals": {...bridge totals used for headlines...},  
  "combined\_totals": {...bridge \+ direct diagnostic sum...},  
  "overlap\_diagnostics": {  
    "overlap\_exists": true,  
    "selected\_totals\_source": "bridge",  
    "temporary\_merge\_logic": true,  
    "policy": "bridge\_authoritative\_for\_headline\_totals",  
    "message": "Headline selected\_totals use bridge-derived values when channels overlap..."  
  }  
}

| Field | Purpose | Frontend use |
| :---- | :---- | :---- |
| bridge | The authoritative bridge-derived development payload from solved Calliope outputs and MARIO/surrogate runtime. | Show as the primary source channel. |
| mrio\_direct | Report-derived MRIO-direct heuristic v1 payload. | Show side by side with explicit heuristic and overlap warnings. |
| selected\_totals | Headline development totals, currently bridge-derived. | Use for overview KPI cards, integrated indicators, and quality-scored outputs. |
| combined\_totals | Diagnostic bridge plus direct sum. | Do not present as headline; use as an analyst comparison only. |
| overlap\_diagnostics | Temporary overlap/merge policy record. | Show warning panel and explain that bridge currently wins on overlap. |

# **11\. MRIO-Direct Heuristic v1**

The MRIO-direct adapter converts parsed report content into shock rows aligned with A/Z, E, Y, and metadata categories. This is a pragmatic v1 heuristic and is not a replacement for exact MARIO matrix shock execution. All rows are labeled mrio\_direct\_heuristic\_v1, and model quality cannot exceed analyst\_review while this mode is active. Sparse test fixtures or additional issues may still downgrade the run to exploratory\_only.

| Shock category | Current heuristic behavior | Important caveat |
| :---- | :---- | :---- |
| A/Z | Uses parsed fossil reduction and renewable share targets to create signed direct structural shock rows by MRIO geography and sector. Fossil supply-chain values are negative; renewable/grid/construction allocations are positive. | Does not yet mutate exact A or Z matrices in MARIO. |
| E | Produces an emissions-intensity proxy delta. It does not overwrite solved Calliope physical emissions. | Must remain separate from Calliope emissions until exact E-matrix treatment is implemented. |
| Y | Uses parsed capacity, access, demand, or investment percentages where available to create final-demand proxy rows. | Parsing depends on report table structure and should be reviewed by MRIO experts. |
| Metadata/provenance | Carries scenario id, geography, target year, method, source report hash, capping status, and overlap policy. | Frontends should expose the provenance and not hide the heuristic status. |

| Configuration | Default | Meaning |
| :---- | :---- | :---- |
| mario\_direct.structural\_reallocation\_bridge\_scale | 0.25 | Scales direct heuristic shock amount relative to bridge total shock magnitude. |
| mario\_direct.max\_direct\_to\_bridge\_ratio | 1.0 | Caps absolute direct shock magnitude as a ratio of bridge total shock. |
| selected\_totals\_source | bridge | Bridge-derived channel wins for headline development metrics when overlap exists. |

# **12\. API Reference for Teams**

| Endpoint | Method | Purpose | Important payload details |
| :---- | :---- | :---- | :---- |
| /api/scenarios | GET | Returns one integrated catalog. | Includes energy\_scenarios, mrio\_scenarios, target\_years, geography\_alignment\_options, report metadata, defaults, and a temporary scenarios alias for UI inspection. |
| /api/environment-setup | GET | Runs readiness checks for selected integrated scenario configuration. | Query params: energy\_scenario\_key, mrio\_scenario\_id, target\_year, run\_profile, strict\_validation, allow\_placeholder\_data. |
| /api/preflight | GET | Alias/related readiness flow for run prerequisites. | Use the same integrated query params as environment setup. |
| /api/jobs | POST | Submits a run. | Requires the integrated RunRequest shape. Legacy scenario/fast\_dev\_mode is invalid. |
| /api/jobs | GET | Lists queued/running/completed jobs. | Frontend uses request.energy\_scenario\_key, request.mrio\_scenario\_id, and request.target\_year in tables/status displays. |
| /api/jobs/{job\_id} | GET | Polls a submitted job. | Returns status, progress, stage, artifacts, summary, errors. |
| /api/run/{run\_id}/integrated | GET | Returns integrated\_results.json. | Includes scenario\_provenance and source\_channels. |
| /api/run/{run\_id}/development | GET | Returns development\_impacts.json. | Includes bridge, mrio\_direct, selected\_totals, combined\_totals, and overlap\_diagnostics. |
| /api/run/{run\_id}/download/{path} | GET | Downloads run artifacts. | Used for exchange CSVs, scenario artifacts, reports, and bundles. |

# **13\. Run Artifact Contract**

Every run should leave enough inspectable artifacts to debug exactly how results were constructed. Files below should be considered stable contracts unless a migration plan is documented.

| Artifact | Location | Description |
| :---- | :---- | :---- |
| scenario\_package.json | run root | Primary run configuration artifact. Contains integrated package and provenance. |
| energy\_input\_manifest.json | scenario/ | Energy adapter manifest for the selected Calliope scenario. |
| report\_scenario\_reference.json | scenario/ | Parsed report scenario record used by MRIO-direct adapter. |
| geography\_alignment.json | scenario/ | Geography mapping status, mapped locations, notes, and blocking mismatch flag. |
| mrio\_direct\_inputs.json | scenario/ | Structured MRIO-direct heuristic payload. |
| mrio\_direct\_shocks.csv | scenario/ | Tabular MRIO-direct shock rows for audit/review. |
| results.csv | run root | Calliope result export. |
| summary.json | run root | Top-level backend run summary, including scenario\_package and integrated\_results. |
| development\_impacts.json | run root and exchange/ | Development channel payload with bridge/direct/selected/combined/overlap fields. |
| coupling\_manifest.json | run root and exchange/ | Integration architecture, model quality inputs, selected source policy, placeholder data, mapping quality, runtime status. |
| integrated\_results.json | run root | Frontend-oriented integrated results payload. |
| run\_report.md | run root | Human-readable run report generated from summary/integrated payloads. |
| exchange/\*.csv | exchange/ | Calliope-to-MRIO bridge exchange files and schema validation outputs. |

# **14\. Integrated Results Contract**

Integrated results are built for the dashboard and for downstream review. Headline development metrics must use development\_impacts.selected\_totals, not raw bridge/direct/combined totals. The integrated payload also carries source\_channels and scenario\_provenance so the UI can explain where each result came from.

integrated\_results \= {  
  "run\_id": "...",  
  "energy\_scenario\_key": "new\_links",  
  "mrio\_scenario\_id": "ZA-S2",  
  "target\_year": 2030,  
  "scenario\_package": {...},  
  "integrated\_overview": {...},  
  "development\_drivers": {...selected-totals based...},  
  "regional\_development": {...bridge regional records...},  
  "development\_confidence": {  
    "integration\_architecture": "bridge\_plus\_mrio\_direct\_v1",  
    "mrio\_direct\_method": "mrio\_direct\_heuristic\_v1",  
    "selected\_totals\_source": "bridge",  
    "temporary\_overlap\_policy": "bridge\_authoritative\_for\_headline\_totals"  
  },  
  "source\_channels": {  
    "bridge": {...},  
    "mrio\_direct": {...},  
    "selected\_totals": {...},  
    "combined\_totals": {...},  
    "overlap\_diagnostics": {...}  
  },  
  "scenario\_provenance": {...}  
}

# **15\. Placeholder Data and Expert-Owned Inputs**

The repository includes seeded placeholder expert datasets so the workflow can run end-to-end. These are not project-calibrated evidence. Strict validation blocks placeholder expert data unless allow\_placeholder\_data is true. Even when placeholders are allowed, model quality and frontend warnings must remain explicit.

| Dataset | Owner | What experts must provide |
| :---- | :---- | :---- |
| inputs/mario\_inputs/employment\_intensity.csv | MRIO/economic experts | Calibrated jobs\_per\_musd\_direct and jobs\_per\_musd\_total by MARIO region/sector, with source citations and reference year. Remove placeholder provenance. |
| inputs/mario\_inputs/value\_added\_intensity.csv | MRIO/economic experts | Calibrated gva\_per\_musd\_output and household\_income\_per\_musd\_output by MARIO region/sector. Units must match MARIO monetary convention. |
| inputs/mario\_inputs/scenario\_assumptions.csv | MRIO and scenario experts | Scenario-specific assumptions for energy\_scenario\_key/baseline rows. Replace placeholder sources and notes. |
| inputs/mario\_inputs/development\_indicator\_mapping.csv | Development indicator experts | Supported driver mappings, units, lag assumptions, and aggregation rules for indicators. |
| inputs/mario\_inputs/country\_to\_pool.csv | GIS/modeling experts | Complete Calliope location to power-pool/MRIO-region mapping. Critical for avoiding UNKNOWN region outputs. |
| frontend/geo/edim\_locations\_placeholder.geojson | GIS/data team | Real GeoJSON geometry for country/subcountry regions or approved centroid inputs for Voronoi coverage. Placeholder geometries must be replaced before production claims. |
| inputs/scenario\_geography\_mapping.csv | Energy/MRIO/GIS team | Mapping rows for MRIO geography to Calliope country/location. Must be maintained when Calliope or MRIO region systems change. |

# **16\. Frontend Architecture**

The frontend is currently a no-build React application loaded from frontend/index.html with Babel standalone. This is convenient for rapid iteration but should be revisited for production. The app is structured as a fixed dashboard shell rather than a long scrolling page. It has a left command rail for integrated scenario setup, a central analysis canvas with tabs, and a right rail for jobs/readiness/model-structure panels.

| UI area | Responsibilities | Key implementation notes |
| :---- | :---- | :---- |
| Left command rail | Integrated scenario definition: energy pathway, MRIO report scenario, target year, profile, validation, placeholder toggle, levers, run action. | Reads /api/scenarios defaults; submits integrated RunRequest only. |
| Overview tab | Map-first results, global vs selected metrics, baseline comparison, model quality. | Map selection should filter all filterable charts; non-filterable global metrics should be shown separately. |
| Energy system tab | Generation, capacity, reliability, trade balance, emissions, and system structure. | Country/subregion filtering should apply only where the underlying result has compatible spatial resolution. |
| Development tab | Development impacts by region/sector, uncertainty, scenario assumptions, indicators. | Use selected\_totals for headline metrics and show source-channel comparison where relevant. |
| Method tab | Metric resolution, coupling diagnostics, scenario provenance, bridge/direct source channel panels. | Must explain overlap policy and heuristic MRIO-direct method clearly. |
| Right rail | Recent jobs, environment setup, model structure/readiness. | Use job.request.energy\_scenario\_key, mrio\_scenario\_id, and target\_year. |

# **17\. Design Requirements**

The design goal is a decision-support dashboard, not a generic data dump. Users should always understand: what scenario they are running, whether data are placeholder or reviewed, which metrics are global versus spatially filterable, and whether development effects came from Calliope bridge outputs or report-derived MRIO-direct assumptions.

* Make the integrated scenario definition visibly singular. Do not present energy and MRIO as separate run modes.  
* Separate global/unfilterable outputs from country/subcountry filterable outputs. Avoid implying a global metric has regional precision.  
* For map interactions, highlight the selected country/subregion as the primary highlight. Parent region context may be shown with a lighter highlight.  
* Use a clear legend with matching map colors. A legend color must be identical to the choropleth/polygon/point layer color mapping.  
* When a region/subregion is selected, every compatible chart should respond. Charts that cannot respond due to model granularity should stay in a clearly labeled global or non-spatial area.  
* Show provenance and warnings close to headline outputs, not hidden in a technical footer.  
* Treat placeholder data as a trust-state problem. Use labels and warnings that a policy user can understand: "placeholder expert coefficients active" is clearer than a generic warning.  
* MRIO-direct heuristic outputs must be visually secondary to bridge-selected headline outputs until exact matrix shock execution is implemented.

# **18\. Backend Engineering Requirements**

* Maintain strict schema enforcement on RunRequest. Breaking API changes are acceptable for this phase, but the frontend and docs must stay synchronized.  
* Keep scenario\_package.json as the canonical run configuration artifact and include it in exchange bundles.  
* Keep bridge and MRIO-direct channels separate until the team explicitly removes overlap/merge logic.  
* Do not silently downgrade strict validation. Analysis/full profiles force strict\_validation true.  
* Keep all fallback paths visible in coupling\_manifest and development\_confidence.  
* When adding OSeMOSYS support, add an energy adapter behind the package boundary rather than changing the frontend run contract.  
* When exact MARIO matrix execution is implemented, replace mrio\_direct\_heuristic\_v1 with a new method name and migration note. Do not silently reuse the old method label.  
* Preserve geography alignment diagnostics. They are essential for avoiding misleading regional/subregional interpretation.

# **19\. Testing Requirements**

| Test area | Required coverage |
| :---- | :---- |
| Report parser | Verify all 10 scenario ids are recovered, with geographies, targets, A/Z, E, and Y guidance, source hash, and cache rebuild behavior. |
| Scenario package | Verify integrated request produces package, energy manifest, report scenario reference, geography alignment artifact, MRIO-direct inputs, and shocks CSV. |
| Geography alignment | Verify national-to-subnational fan-out, regional fan-out, MRIO-only allowed cases, and blocking behavior only for incompatible subnational-to-subnational mappings. |
| Run request schema | Verify new request shape is accepted and legacy scenario/fast\_dev\_mode extras are rejected. |
| Development runtime | Verify bridge and MRIO-direct outputs are both produced, selected\_totals defaults to bridge, combined\_totals is diagnostic, and overlap\_diagnostics is emitted. |
| Integrated results | Verify source\_channels, scenario\_provenance, model quality cap, and selected-total indicator paths. |
| Frontend smoke tests | Verify catalog load, MRIO scenario selector, target-year selector, run payload, alignment warning display, source-channel panels, map filtering behavior, and placeholder toggle. |
| Documentation checks | Verify README/SYSTEM\_DOCUMENTATION and this DOCX are updated when API or artifact contracts change. |

# **20\. Operations and Runbook**

* Backend runs through FastAPI/uvicorn. The app serves frontend static assets when the frontend directory is configured or present.  
* If port conflicts occur, use the project startup scripts or Make targets that auto-select alternate frontend/backend ports where available.  
* Job queue state is in memory. Restarting the backend clears in-memory job history but does not remove run artifacts under outputs/runs.  
* Generated report cache lives at inputs/generated/scenario\_report\_scenarios.json and is keyed by the DOCX source hash.  
* Run artifacts under outputs/runs are generated. Keep them for debugging and reproducibility but do not treat them as source configuration.  
* When model inputs are updated, rerun backend tests and inspect environment setup checks before running long analysis/full jobs.  
* For production deployment, replace Babel-standalone frontend loading with a normal build pipeline, pin dependency versions, and add browser-level smoke tests.

# **21\. Known Limitations and Risks**

| Risk/limitation | Impact | Recommended resolution |
| :---- | :---- | :---- |
| MRIO-direct heuristic v1 | Can support transparent scenario exploration but is not exact MARIO matrix shock execution. | Implement exact A/Z/E/Y matrix shock preparation/execution and retire temporary overlap merge logic. |
| Placeholder expert datasets | Headline development impacts may not be evidence-grade. | Replace placeholder coefficients with expert-calibrated datasets and provenance. |
| No-build frontend | Harder to lint, type-check, test, and package reliably. | Move to Vite or equivalent build system with tests and pinned dependencies. |
| MRIO-only report geographies | India, Brazil, and WM scenarios cannot align to Calliope-Africa energy locations today. | Add corresponding energy model geography or use a clearly MRIO-only workflow with separate interpretation. |
| Spatial resolution mismatch | Charts may appear filterable beyond available model granularity if UI is careless. | Keep metric-resolution metadata visible and enforce filtering only where supported. |
| Job queue in memory | Backend restart loses in-memory job status. | Persist job state in a lightweight database if multi-user or production workflows are needed. |
| Report parser depends on DOCX table conventions | Report structure edits can change parsed output unexpectedly. | Add parser fixture tests and require scenario report template/versioning. |

# **22\. Roadmap**

| Priority | Workstream | Concrete next steps |
| :---- | :---- | :---- |
| P0 | Exact MRIO shock execution | Replace heuristic v1 with exact MARIO A/Z/E/Y matrix shock construction, scenario-specific shock files, validation, and provenance. |
| P0 | Expert data replacement | Calibrate and replace placeholder employment, value-added, assumptions, geography, and indicator datasets. |
| P1 | Frontend productionization | Add package.json, Vite build, lint/test tooling, Playwright smoke tests, CI checks, and dependency pinning. |
| P1 | Filtering rigor | Formalize metric spatial resolution metadata and ensure map selection filters only compatible charts. |
| P1 | Geospatial assets | Replace placeholder GeoJSON, validate geometries, and document geometry source/licensing. |
| P2 | OSeMOSYS adapter | Add energy adapter interface implementation behind IntegratedScenarioPackage without changing frontend contract. |
| P2 | Persistent jobs | Add durable job store and retention policy for multi-session run management. |
| P2 | Design system | Extract dashboard components and visual tokens into a reusable design system with accessibility testing. |

# **23\. Acceptance Criteria for the Next Team**

* A user can configure one integrated run from the frontend using energy\_scenario\_key, mrio\_scenario\_id, target\_year, run\_profile, validation mode, placeholder-data mode, and levers.  
* The backend persists scenario\_package.json and scenario/ artifacts for every run.  
* The report parser reliably extracts all 10 report scenarios and rebuilds its cache when the DOCX source hash changes.  
* Development outputs expose bridge, mrio\_direct, selected\_totals, combined\_totals, and overlap\_diagnostics.  
* Headline integrated metrics use selected\_totals and clearly mark bridge as the temporary authoritative source on overlap.  
* Frontend result panels show scenario provenance, bridge inputs, MRIO-direct assumptions, overlap policy, and source-channel comparison.  
* Strict validation and placeholder-data settings are visible and enforced consistently.  
* Tests cover parser, package, geography alignment, runtime channels, integrated results, request schema, and frontend smoke behavior.  
* Documentation stays synchronized with API/artifact contracts.

# **24\. File-Level Implementation Guide**

| File | What future teams should change here |
| :---- | :---- |
| backend/api\_service/scenario\_report.py | Update when the scenario report DOCX template changes or more structured extraction is needed. Add tests before changing parser assumptions. |
| backend/api\_service/scenario\_package.py | Update package schema, geography alignment, MRIO-direct adapter, and scenario artifact writing. This is the main package boundary. |
| backend/api\_service/schemas.py | Update external API request/response contracts. Coordinate every change with frontend and docs. |
| backend/api\_service/scenarios.py | Update integrated catalog shape and default selection rules. |
| backend/api\_service/runner.py | Update orchestration stages, Calliope execution, bridge outputs, development runtime selection, and artifact persistence. |
| backend/api\_service/integrated.py | Update integrated result contract, model quality logic, report generation, source channel exposure, and exchange bundle contents. |
| backend/api\_service/mario\_runtime.py | Update MARIO runtime, placeholder data detection, indicator/assumption loading, and exact matrix execution integration. |
| frontend/app.jsx | Update dashboard state, API client, scenario setup flow, map/chart panels, source-channel panels, and job status UI. |
| frontend/index.html | Update global CSS, external browser dependencies, and dashboard shell styling until a build system is added. |
| inputs/scenario\_geography\_mapping.csv | Maintain MRIO-to-Calliope mapping as geographies evolve. |
| inputs/mario\_inputs/\*.csv | Replace placeholders and maintain expert-owned calibrated development/MRIO datasets. |
| README.md and SYSTEM\_DOCUMENTATION.md | Keep user-facing and system-facing docs synchronized with runtime behavior. |

# **25\. Final Guidance**

The most important engineering principle is to keep the integrated scenario package as the boundary object. Frontend should not know or care whether the energy model is Calliope or OSeMOSYS beyond the catalog labels. Backend should route package contents to adapters and preserve provenance. Design should make data trust, spatial resolution, and source-channel policy obvious to users. Modeling teams should replace placeholder inputs and the MRIO-direct heuristic with exact evidence-backed implementations as the next major fidelity upgrade.

# **26\. Developer Environment and Running the System**

The current repository is optimized for local development and iterative modeling work. The frontend is served as static files by the backend when available. There is no package.json in this checkout, so frontend validation is currently manual/browser-based unless a separate local tool is added. Backend tests are Python unittest-based and should be run before handoff or model-data changes.

| Task | Current command or requirement | Notes |
| :---- | :---- | :---- |
| Install backend dependencies | pip3 install \-r backend/requirements.txt | The user environment uses pip3. Prefer a virtual environment to avoid global package conflicts. |
| Install frontend dependencies | No package.json currently present | The frontend loads React, ReactDOM, Leaflet, D3 Delaunay, Turf, and Babel from CDN in frontend/index.html. |
| Run backend tests | PYTHONPATH=backend python3 \-m unittest discover \-s backend/tests \-p "test\_mvp.py" | This is the current regression test suite used during the unified scenario refactor. |
| Compile backend Python | python3 \-m py\_compile backend/api\_service/\*.py backend/tests/test\_mvp.py | Catches syntax/import issues quickly. |
| Serve backend | uvicorn app.main:app \--app-dir backend \--reload \--reload-dir backend \--host 127.0.0.1 \--port \<port\> | Use an available port. Previous work requested auto-port retry behavior for backend/frontend startup scripts. |
| Open UI | Backend static mount under /ui/ when frontend is available | Exact URL depends on selected backend port. |
| Check scenario catalog | GET /api/scenarios | Should return integrated\_scenario\_catalog\_v1 with energy\_scenarios, mrio\_scenarios, target\_years, geography\_alignment\_options, report, defaults. |
| Submit a run | POST /api/jobs with integrated RunRequest | Do not use legacy scenario or fast\_dev\_mode fields. |

# **27\. Backend Module Responsibilities in Detail**

| Module | Detailed responsibility | Common change triggers |
| :---- | :---- | :---- |
| main.py | FastAPI app initialization, static frontend mount, route declarations, settings access, environment/preflight/scenario/jobs/run-artifact endpoints. | New route, API query change, frontend static behavior, route-level validation. |
| settings.py | Environment-variable configuration, Calliope root discovery, run directory, solver/profile defaults, job queue capacity, MARIO runtime controls. | Deployment configuration, default solver/profile changes, run retention, queue capacity. |
| schemas.py | Pydantic contracts for RunRequest, RunSummary, JobInfo, artifacts, levers, and scenario metadata. | Any frontend/backend contract change. |
| jobs.py | In-memory job manager, deduplication, progress state, cancellation, summary loading and API-safe job serialization. | Persistent job store, multi-user workflows, queue policy changes. |
| scenarios.py | Calliope override scenario list, scenario metadata loading, integrated catalog composition. | New scenario source, changed catalog UI metadata, new default rules. |
| scenario\_report.py | DOCX table and paragraph parsing, report SHA256 cache, normalized scenario report schema. | Report template changes, richer assumption extraction, parser robustness improvements. |
| scenario\_package.py | Integrated package creation, geography alignment, MRIO-direct heuristic inputs, scenario artifact writer. | New energy adapters, exact MRIO-direct adapter, updated mapping rules, new artifact schema. |
| runner.py | End-to-end orchestration, Calliope solve, lever patching, exchange file generation, development runtime dispatch, scenario artifacts, integrated output assembly. | Any runtime stage change, bridge logic, model validation, run artifact lifecycle. |
| mario\_runtime.py | MARIO input health, placeholder detection, scenario assumptions, indicator mapping, IO runtime or surrogate interfaces. | Exact MARIO execution, new intensity datasets, placeholder policy, indicators. |
| integrated.py | Integrated result payload, development quality model, source channel exposure, baseline comparison, run report, exchange bundle creation. | Dashboard contract changes, model quality policy, output schema changes. |
| summarize.py | Calliope result summarization and diagnostics for generation, capacity, emissions, cost, reliability, spatial records. | New energy output metrics, unit fixes, spatial-resolution improvements. |

# **28\. Frontend State and Component Responsibilities**

The frontend app is currently concentrated in frontend/app.jsx. Future teams should consider extracting these concerns into separate modules once a build system exists. Until then, changes should be made carefully because browser Babel transpiles the full file at runtime.

| State or component area | Current purpose | Requirements for future changes |
| :---- | :---- | :---- |
| scenarioCatalog, scenarios, scenarioKey | Integrated catalog and selected energy scenario. | Must load from /api/scenarios and use defaults.energy\_scenario\_key where available. |
| mrioScenarios, mrioScenarioId | Report-derived MRIO scenario list and active selected report scenario. | Must submit mrio\_scenario\_id in every run request and show it in job/result provenance. |
| targetYears, targetYear | Available parsed target years and selected target year. | Must submit target\_year as a number and display in setup, job row, and results. |
| levers | Demand/capex/fuel/carbon levers. | Must remain part of the integrated scenario definition, not a separate mode. |
| runProfile, strictValidation, allowPlaceholderData | Runtime profile and validation/trust controls. | Analysis/full lock strict validation. Placeholder mode must be explicit and visible. |
| environmentSetup | Readiness checks for selected integrated configuration. | Reload when energy scenario, MRIO scenario, target year, profile, strict validation, or placeholder mode changes. |
| jobs, activeJob, result, integratedPayload | Job queue and selected run state. | Use integrated fields from job.request and result.summary. Avoid legacy scenario display. |
| locationMapData, spatialFilter | Map data and selected geography filter. | Apply to all compatible panels and clearly separate global/non-filterable metrics. |
| ScenarioSetupPanel | Left rail scenario definition UI. | Keep energy pathway, MRIO report scenario, target year, profile, validation, placeholder toggle, levers, and run button together. |
| RunResultsPanel | Tabbed dashboard results. | Show scenario provenance and source channels in Method tab. Keep source-channel warnings visible. |
| ScenarioProvenanceCard | Displays package and report provenance. | Must include energy scenario, MRIO scenario, target year, geography alignment, report source, selected totals source. |
| SourceChannelsCard | Displays bridge versus MRIO-direct source-channel diagnostics. | Must clearly state bridge-derived values are currently headline-authoritative on overlap. |

# **29\. Units, Granularity, and Interpretation Rules**

The project mixes energy model outputs, monetary bridge shocks, development impact coefficients, and spatial aggregations. Teams must preserve unit and granularity metadata because misleading regional interpretation is a major risk.

| Metric family | Likely unit/granularity | Interpretation requirement |
| :---- | :---- | :---- |
| Generation by technology | Energy quantity from Calliope result summaries; technology and sometimes location/time resolution. | Filter spatially only when row-level location or region exists. Otherwise show as global. |
| Capacity / energy\_cap | Power capacity from Calliope, by technology/location when available. | Country/subregion filtering can be valid when location is present. |
| System cost | Global model objective or cost records. | Generally global unless the model output provides a supported regional cost decomposition. Put non-filterable values in global box. |
| Physical emissions | tCO2 from diagnostics, technology/location depending on source method. | Do not assume country precision if only regional/global emissions exist. Show method and coverage. |
| Investment/operating shocks | MUSD exchange shock values from Calliope-to-MARIO bridge. | Spatially tied to mapped region/location when bridge rows contain location and mapping is complete. |
| Jobs | Jobs from development intensity factors and shock totals. | Use selected\_totals for headline. Avoid weighted regional estimates unless explicitly documented and backed by source data. |
| GVA and household income proxy | MUSD or MUSD-equivalent from intensity factors. | Keep source-channel and placeholder status visible. |
| MRIO-direct emissions proxy | Dimensionless or proxy delta from E shock heuristic. | Do not overwrite solved Calliope physical emissions. Display as MRIO-direct proxy only. |
| Map values | Chosen frontend metric, often shock or derived impact by geography. | Legend colors must match layer colors; selected geography filters only compatible charts. |

# **30\. Validation and Model Quality Gates**

Validation is not just a backend concern. It is a trust workflow that must surface in the UI and documentation. Strict validation should fail fast; non-strict validation should still report warnings and downgrade quality where appropriate.

| Gate | Backend behavior | Frontend/design behavior |
| :---- | :---- | :---- |
| Required package fields | RunRequest requires integrated fields and forbids legacy extras. | Do not render submit-enabled state unless energy scenario, MRIO scenario, and target year are selected. |
| Strict profile lock | analysis/full force strict\_validation true. | Render strict validation as locked/on for analysis and full. |
| Placeholder inputs | Blocked in strict mode unless allow\_placeholder\_data is true; always counted in diagnostics. | Show placeholder toggle and warnings. Do not imply production readiness with placeholders active. |
| Geography mismatch | Only blocking when both sides expose incompatible subnational systems without mapping. | Show alignment status and clear MRIO-only or mapped-location note. |
| Mapping coverage/fallbacks | Coupling manifest tracks mapping coverage, fallback share, fallback exchange usage, placeholder rows. | Expose model quality/status and method details near result interpretation. |
| MRIO-direct heuristic | Caps quality at analyst\_review or below while active. | Label as heuristic v1 and secondary to selected bridge totals. |
| Runtime errors | Job status becomes failed with error message; artifacts may be incomplete. | Show error message and avoid rendering partial results as successful. |

# **31\. Accessibility, Performance, and Product Requirements**

| Area | Requirement |
| :---- | :---- |
| Accessibility | Use semantic headings, adequate contrast, keyboard-accessible controls, visible focus states, and chart/map alternatives where possible. Do not encode critical trust status only with color. |
| Responsiveness | Dashboard must work on desktop and mobile. Current CSS switches to single-column below 1180px and 980px; test those breakpoints after any layout change. |
| Performance | Avoid blocking the UI with large CSV parsing on every render. Cache run map/tech datasets by run id as the current app does. |
| Map performance | Use simplified/appropriate GeoJSON and avoid redoing Voronoi/Turf work unnecessarily. Precompute where feasible for large geometries. |
| Error states | Every async panel should have loading, empty, and error states. Readiness failures should be actionable. |
| User trust | Display data source, placeholder status, heuristic status, quality status, and selected source channel close to the metrics they affect. |
| Extensibility | Keep scenario setup generic enough for future OSeMOSYS support without adding separate user-facing modes. |

# **32\. Security, Deployment, and Data Governance Notes**

The current system is a local/workbench application. Before deployment to shared users, teams should make explicit decisions about authentication, job isolation, artifact retention, and data governance.

* Add authentication/authorization before exposing run submission or artifact download endpoints beyond trusted local use.  
* Do not allow arbitrary file path access from run download endpoints. Keep path resolution constrained to the configured runs directory.  
* Define run retention and cleanup policy for outputs/runs. Large Calliope runs can accumulate quickly.  
* Persist jobs if users need durable run history across backend restarts.  
* Pin frontend CDN dependencies or move to a bundled build to avoid silent dependency drift.  
* Document source/licensing for any real GeoJSON, MRIO coefficients, employment multipliers, and scenario assumptions.  
* Keep report source SHA256 and generated scenario cache under review when scenario report content changes.

# **33\. Definition of Done for Future Feature Work**

* The feature has a clear source-of-truth schema and artifact contract if it affects model outputs.  
* The feature updates backend tests for parser/package/runtime/integrated behavior as applicable.  
* The frontend shows loading, empty, error, and trust/provenance states for new data.  
* Spatial filtering behavior is explicit: either supported and tested, or clearly marked global/non-filterable.  
* Placeholder or heuristic data are labeled and reflected in model quality.  
* README.md, SYSTEM\_DOCUMENTATION.md, and this DOCX are updated if the API, artifact, or user workflow changes.  
* No legacy request fields are reintroduced unless a deliberate migration plan is documented.  
* Run artifacts are inspectable enough for another engineer/modeler to reproduce or diagnose the result.

# **34\. Suggested Team Split**

| Team | Immediate ownership |
| :---- | :---- |
| Backend platform | Stabilize integrated RunRequest, artifact contracts, job persistence plan, tests, exact MRIO runtime integration surface, deployment configuration. |
| Energy modeling | Validate Calliope scenario metadata, outputs, spatial resolution, emissions/cost attribution, and future OSeMOSYS adapter boundaries. |
| MRIO/development modeling | Replace heuristic MRIO-direct logic with exact A/Z/E/Y matrix shock execution and calibrate development coefficients. |
| Data/GIS | Replace placeholder GeoJSON, maintain geography mapping, validate region/subregion identifiers, document geospatial provenance. |
| Frontend engineering | Productionize build/test pipeline, modularize app.jsx, implement robust source-channel and spatial filtering UX, add smoke tests. |
| Product/design | Refine dashboard workflow, trust/provenance language, map legend/selection behavior, and global versus filtered results hierarchy. |

# **35\. High-Level Migration Path to Production**

| Phase | Outcome | Exit criteria |
| :---- | :---- | :---- |
| Phase 1: Stabilize prototype | Current unified architecture works end-to-end with transparent heuristic/placeholder warnings. | All backend tests pass; integrated catalog/run/artifacts stable; frontend smoke-tested manually. |
| Phase 2: Replace placeholder evidence | Development outputs use expert-calibrated data. | No placeholder rows in required expert datasets; model quality can exceed analyst\_review when other gates pass. |
| Phase 3: Exact MRIO shocks | MRIO-direct channel executes exact A/Z/E/Y matrix shock logic. | mrio\_direct\_heuristic\_v1 retired or kept only as optional debug mode; overlap merge policy simplified. |
| Phase 4: Frontend productionization | Dashboard has build system, tests, and component boundaries. | Vite/build pipeline, lint/test/Playwright checks, pinned dependencies, CI ready. |
| Phase 5: Deployment hardening | Multi-user or shared deployment is safe. | Auth, persistent jobs, artifact retention, monitoring, configuration docs, data governance docs. |

