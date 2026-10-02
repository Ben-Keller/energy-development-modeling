const { expect } = require("@playwright/test");

const PROJECT = {
  project_id: "project_alpha",
  title: "National transition planning",
  geography: "South Africa",
  project_type: "energy-development",
  model_architecture_id: "energy-development",
  scenario_label: "Integrated pathways",
  notes: "",
  status: "active",
  owner_user_id: "undp_analyst",
  created_at: "2026-06-10T09:00:00Z",
  updated_at: "2026-06-16T13:30:00Z",
  visual_summary: {
    model_count: 3,
    completed_count: 1,
    active_count: 1,
    failed_count: 0,
    architecture_count: 1,
    scenario_count: 3,
    kpi_scope_count: 13,
    variation_score: 1,
    models: [{
      run_id: "run_draft_01",
      project_run_number: 1,
      status: "draft",
      architecture_id: "energy-development",
      scenario_key: "baseline",
      target_scenario_id: "",
      target_year: 2030,
      run_profile: "dev",
      lever_count: 0,
      artifact_count: 0,
      kpi_scope_count: 0,
      summary_available: false,
    }, {
      run_id: "run_complete_02",
      project_run_number: 2,
      status: "succeeded",
      architecture_id: "energy-development",
      scenario_key: "high-renewables",
      target_scenario_id: "green-transition",
      target_year: 2040,
      run_profile: "full",
      lever_count: 4,
      artifact_count: 6,
      kpi_scope_count: 8,
      summary_available: true,
    }, {
      run_id: "run_active_03",
      project_run_number: 3,
      status: "running",
      architecture_id: "energy-development",
      scenario_key: "access-acceleration",
      target_scenario_id: "inclusive-growth",
      target_year: 2035,
      run_profile: "full",
      lever_count: 2,
      artifact_count: 1,
      kpi_scope_count: 5,
      summary_available: true,
    }],
  },
};

const DRAFT_RUN = {
  run_id: "run_draft_01",
  execution_id: "",
  project_id: PROJECT.project_id,
  project_run_number: 1,
  run_name: "Baseline planning case",
  status: "draft",
  stage: "draft",
  progress: 0,
  message: "",
  created_at: "2026-06-16T13:35:00Z",
  updated_at: "2026-06-16T13:35:00Z",
  request: {
    project_id: PROJECT.project_id,
    model_architecture_id: "energy-development",
    energy_scenario_key: "baseline",
    target_year: 2030,
    run_profile: "dev",
    levers: {},
  },
};

function completedComparisonRun(runId, runNumber, runName, scenarioKey, targetYear) {
  return {
    ...DRAFT_RUN,
    run_id: runId,
    execution_id: `execution_${runId}`,
    project_run_number: runNumber,
    run_name: runName,
    status: "succeeded",
    stage: "succeeded",
    progress: 1,
    message: "Complete",
    finished_at: "2026-06-16T15:00:00Z",
    summary_available: true,
    request: {
      ...DRAFT_RUN.request,
      energy_scenario_key: scenarioKey,
      target_year: targetYear,
      run_profile: "full",
      levers: {
        renewable_capex_reduction: runNumber * 0.1,
        demand_growth_multiplier: 1 + runNumber * 0.02,
      },
    },
  };
}

function comparisonSummary(run, multiplier) {
  const artifact = (artifactId, label, mediaType) => ({
    artifact_id: artifactId,
    label,
    kind: "final",
    producer_stage: "build_summary",
    path: `artifacts/final/${artifactId}`,
    download_url: `/api/runs/${run.run_id}/artifacts/${artifactId}`,
    include_in_project_bundle: true,
    expose_download: true,
    embed_in_summary: false,
    embed_in_final_results: false,
    required_for_report: true,
    size_bytes: Math.round(2048 * multiplier),
    media_type: mediaType,
  });
  return {
    run_id: run.run_id,
    model_architecture_id: "energy-development",
    energy_scenario_key: run.request.energy_scenario_key,
    mrio_scenario_id: "green-transition",
    target_year: run.request.target_year,
    run_profile: "full",
    generation_by_tech: {
      records: [
        { timesteps: "2030-01-01", techs: "Solar PV", value: 60 * multiplier },
        { timesteps: "2030-01-02", techs: "Solar PV", value: 40 * multiplier },
        { timesteps: "2030-01-01", techs: "Wind", value: 55 * multiplier },
      ],
    },
    capacity_by_tech: {
      records: [
        { techs: "Solar PV", value: 25 * multiplier },
        { techs: "Wind", value: 18 * multiplier },
      ],
    },
    new_capacity_by_tech: {
      records: [{ techs: "Solar PV", value: 8 * multiplier }],
    },
    system_cost: {
      records: [{ costs: "monetary", value: 1_000_000 * multiplier }],
    },
    summary_diagnostics: {
      run_metadata: {
        solver: "highs",
        termination_condition: "optimal",
        solution_time_seconds: 12 * multiplier,
        objective_function_value: 1000 * multiplier,
        calliope_version: "0.6.10",
      },
      reliability: {
        demand_total: 500 * multiplier,
        unserved_total: 2 / multiplier,
        unserved_energy_share: 0.004 / multiplier,
        hours_with_unserved: Math.round(3 / multiplier),
        max_unserved_hour: 1.2 / multiplier,
      },
      physical_emissions: {
        total_emissions: 90 / multiplier,
        factor_coverage_share: 0.95,
        factor_method_gap_share: 0.02,
        by_tech: { records: [{ techs: "Gas", value: 90 / multiplier }] },
        by_pool: { records: [{ pool: "SAPP", value: 90 / multiplier }] },
      },
      system_structure: {
        renewable_generation_share: 0.42 * multiplier,
        zero_carbon_generation_share: 0.48 * multiplier,
        fossil_generation_share: 0.52 / multiplier,
        renewable_capacity_share: 0.5 * multiplier,
        zero_carbon_capacity_share: 0.56 * multiplier,
        fossil_capacity_share: 0.44 / multiplier,
        generation_by_group: { records: [{ tech_group: "VRE", value: 155 * multiplier }] },
        capacity_by_group: { records: [{ tech_group: "VRE", value: 43 * multiplier }] },
      },
      cost_decomposition: {
        component_records: [
          { costs: "monetary", component: "investment", tech_group: "VRE", value: 600_000 * multiplier },
          { costs: "monetary", component: "variable_prod", tech_group: "Fossil", value: 400_000 / multiplier },
        ],
      },
      energy_balance: {
        records: [{
          pool: "SAPP",
          generation: 500 * multiplier,
          demand: 480 * multiplier,
          unserved: 2 / multiplier,
          imports: 10,
          exports: 30 * multiplier,
          balance_gap_share: 0.002,
        }],
      },
      trade_matrix: {
        net_by_pool: { records: [{ pool: "SAPP", imports: 10, exports: 30 * multiplier, value: 20 * multiplier }] },
      },
    },
    development_impacts: {
      selected_totals: {
        jobs_total: 1200 * multiplier,
        gva_total_musd: 45 * multiplier,
        household_income_proxy_musd: 12 * multiplier,
      },
      combined_totals: {
        jobs_total: 1350 * multiplier,
        gva_total_musd: 50 * multiplier,
      },
      by_region: {
        records: [{
          region: "Southern Africa",
          jobs_total: 1200 * multiplier,
          gva_total_musd: 45 * multiplier,
          household_income_proxy_musd: 12 * multiplier,
        }],
      },
      by_supplier_sector: {
        records: [{
          supplier_sector: "Electrical equipment",
          jobs_total: 420 * multiplier,
          gva_total_musd: 14 * multiplier,
          shock_value_musd: 20 * multiplier,
        }],
      },
    },
    integrated_results: {
      integrated_overview: {
        metrics: [
          { key: "monetary_cost", label: "System cost", unit: "USD", value: 1_000_000 * multiplier },
          { key: "physical_emissions", label: "Physical emissions", unit: "tCO2", value: 90 / multiplier },
          { key: "jobs_total", label: "Jobs", unit: "jobs", value: 1200 * multiplier },
        ],
      },
      development_drivers: {
        capex_effect_musd: 20 * multiplier,
        opex_effect_musd: 8 * multiplier,
        reliability_penalty_proxy: 1.5 / multiplier,
        import_leakage_musd: 4 / multiplier,
      },
      regional_development: {
        records: [{
          region: "Southern Africa",
          jobs_total: 1200 * multiplier,
          gva_total_musd: 45 * multiplier,
        }],
      },
      development_indicators: {
        records: [
          { indicator_id: "jobs_total", indicator_name: "Total employment impact", unit: "jobs", status: "available", value: 1200 * multiplier },
          { indicator_id: "poverty_effect", indicator_name: "Poverty effect", unit: "share", status: "unavailable", value: null },
        ],
      },
      development_confidence: {
        mapping_coverage_share: 0.92,
        unmapped_mapping_share: 0.08,
        warnings_count: 1,
        mario_runtime_seconds: 4 * multiplier,
        placeholder_input_row_count: 0,
        development_indicators_available_count: 1,
        development_indicators_unavailable_count: 1,
      },
      model_quality: {
        status: "analyst_review",
        issues: [{ code: "mapping_review", severity: "warning" }],
      },
      scenario_assumptions: {
        selected_values: {
          carbon_price: { label: "Carbon price", value_numeric: 35 * multiplier, unit: "USD/tCO2" },
        },
      },
      metric_resolution: {
        records: [{
          metric_key: "generation_by_technology",
          label: "Generation by technology",
          native_resolution: "global",
          filtered_resolution: "location",
          notes: "Location-level values are available in results.csv.",
        }],
      },
      source_channels: {
        selected_totals: {
          jobs_total: 1200 * multiplier,
          gva_total_musd: 45 * multiplier,
        },
        combined_totals: {
          jobs_total: 1350 * multiplier,
          gva_total_musd: 50 * multiplier,
        },
      },
    },
    artifact_catalog: [
      artifact("results_csv", "Integrated results CSV", "text/csv"),
      artifact("integrated_results_json", "Integrated results JSON", "application/json"),
      artifact("report_markdown", "Model report", "text/markdown"),
    ],
    warnings: ["Comparison fixture warning"],
  };
}

const DATASET = {
  id: "national_demand",
  label: "National demand outlook",
  layer: "demand",
  role: "Scenario demand projection",
  required: false,
  scope: "user",
  upload_policy: "project_override",
  user_upload_listable: true,
  filename: "demand.csv",
  source_filename: "demand.csv",
  exists: true,
  size_bytes: 128,
  active_version_id: "version_01",
  versioned_override: true,
  project_ids: [PROJECT.project_id],
  download_url: "/api/input-datasets/national_demand/download",
};

const SYSTEM_DATASET = {
  id: "reference_emissions_factors",
  label: "Reference emissions factors",
  layer: "energy",
  role: "Platform emissions coefficients",
  required: true,
  scope: "system",
  upload_policy: "system_managed",
  user_upload_listable: false,
  filename: "emissions_factors.csv",
  exists: true,
  active_version_id: "2026.1",
};

function sessionPayload() {
  const user = {
    user_id: "undp_analyst",
    display_name: "UNDP Analyst",
    email: "analyst@example.org",
    organization: "UNDP",
    roles: ["analyst"],
    is_admin: false,
    auth_mode: "test_user_header",
  };
  return {
    authenticated: true,
    auth_mode: "test_user_header",
    user,
    available_users: [user],
  };
}

function publicRun(run) {
  const request = run.request || {};
  return {...run, request:undefined, configuration:run.configuration || {
    run_name:run.run_name, model_architecture_id:request.model_architecture_id || "energy-development",
    energy_model_engine:request.energy_model_engine || "calliope", run_profile:request.run_profile || "dev",
    scenario:{energy_scenario_key:request.energy_scenario_key || "baseline", target_scenario_id:request.mrio_scenario_id || "", target_year:request.target_year || 2030}, levers:request.levers || {}
  }};
}

async function mockPlatformApi(page, options = {}) {
  let projectRuns = Array.isArray(options.projectRuns) ? options.projectRuns : [DRAFT_RUN];
  const comparisonSummaries = options.summaries && typeof options.summaries === "object" ? options.summaries : {};
  const artifactTexts = options.artifactTexts && typeof options.artifactTexts === "object"
    ? options.artifactTexts
    : {};
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    let payload = {};
    const artifactTextMatch = path.match(/^\/api\/runs\/([^/]+)\/artifacts\/([^/]+)$/);
    if (
      artifactTextMatch &&
      Object.prototype.hasOwnProperty.call(artifactTexts, artifactTextMatch[2])
    ) {
      await route.fulfill({
        status: 200,
        contentType: "text/csv",
        body: String(artifactTexts[artifactTextMatch[2]] || ""),
      });
      return;
    }

    if (path === "/api/system/manifest") {
      payload = {
        ok: true,
        schema_version: "edim_system_manifest",
        public_endpoints: {},
        diagnostics: [],
      };
    } else if (path === "/api/session") {
      payload = sessionPayload();
    } else if (path === "/api/projects" && method === "GET") {
      payload = { user_id: "undp_analyst", projects: [PROJECT] };
    } else if (path === `/api/projects/${PROJECT.project_id}/runs`) {
      payload = { project_id: PROJECT.project_id, runs: projectRuns.map(publicRun) };
    } else if (path === `/api/projects/${PROJECT.project_id}/runs/validate` && method === "POST") {
      payload = {
        ok: true,
        checks: [
          {
            name: "scenario_inputs",
            label: "Scenario inputs",
            category: "inputs",
            status: "ok",
            message: "Required scenario inputs are available.",
          },
          {
            name: "solver",
            label: "Solver",
            category: "execution",
            status: "ok",
            message: "The configured solver is available.",
          },
        ],
        errors: [],
        warnings: [],
        queue: { active_jobs: 0, capacity: 2 },
        solver_resolved: "highs",
        mario_inputs: { placeholder_details: [] },
      };
    } else if (path.startsWith(`/api/projects/${PROJECT.project_id}/runs/`) && method === "PATCH") {
      const body = request.postDataJSON();
      const runId = decodeURIComponent(path.split("/").pop());
      const current = projectRuns.find((run) => run.run_id === runId) || DRAFT_RUN;
      const updated = {
        ...current,
        run_name: body.run_name || current.run_name,
        request: body.request || current.request,
        configuration: body.request || publicRun(current).configuration,
        updated_at: "2026-06-16T14:05:00Z",
      };
      projectRuns = projectRuns.map((run) => run.run_id === updated.run_id ? updated : run);
      payload = { run: publicRun(updated) };
    } else if (path === `/api/projects/${PROJECT.project_id}/reports`) {
      payload = { project_id: PROJECT.project_id, reports: options.reports || [] };
    } else if (path === `/api/projects/${PROJECT.project_id}/exports`) {
      payload = { project_id: PROJECT.project_id, exports: options.exports || [] };
    } else if (path === "/api/input-datasets") {
      payload = { datasets: [DATASET, SYSTEM_DATASET] };
    } else if (path === `/api/input-datasets/${DATASET.id}/versions`) {
      payload = {
        dataset_id: DATASET.id,
        user_id: "undp_analyst",
        scope: "user",
        versions: [{
          version_id: "version_01",
          dataset_id: DATASET.id,
          filename: "demand.csv",
          path: "/mock/demand.csv",
          size_bytes: 128,
          created_at: "2026-06-16T13:25:00Z",
          scope: "user_override",
          user_id: "undp_analyst",
          project_ids: [PROJECT.project_id],
          validation: { ok: true },
        }],
      };
    } else if (path === "/api/model-runtimes") {
      payload = {};
    } else if (path === "/api/runs") {
      payload = { jobs: [] };
    } else {
      const summaryMatch = path.match(/^\/api\/runs\/([^/]+)\/summary$/);
      const artifactsMatch = path.match(/^\/api\/runs\/([^/]+)\/artifacts$/);
      if (summaryMatch && comparisonSummaries[summaryMatch[1]]) {
        payload = comparisonSummaries[summaryMatch[1]];
      } else if (artifactsMatch && comparisonSummaries[artifactsMatch[1]]) {
        payload = {
          run_id: artifactsMatch[1],
          artifacts: comparisonSummaries[artifactsMatch[1]].artifact_catalog || [],
        };
      }
    }
    if (path === "/api/scenarios") {
      payload = {
        schema_version: "model_scenario_catalog",
        defaults: {},
        module_configurations: [],
        scenario_channels: [],
      };
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(payload),
    });
  });
}

async function openProjects(page) {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Open projects" }).click();
  await expect(page.getByRole("heading", { name: "Your Projects", exact: true })).toBeVisible();
}

async function expectWorkspaceReturnAnchor(page, button) {
  const anchor = await button.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    const header = (document.querySelector(".workspace-navigation") || document.querySelector(".edim-topbar")).getBoundingClientRect();
    return {
      left: rect.left,
      offsetFromHeader: rect.top - header.bottom,
    };
  });
  expect(Math.abs(anchor.left - 18), JSON.stringify(anchor)).toBeLessThanOrEqual(2);
  expect(Math.abs(anchor.offsetFromHeader - 12), JSON.stringify(anchor)).toBeLessThanOrEqual(2);
}


module.exports = { publicRun, PROJECT, DRAFT_RUN, completedComparisonRun, comparisonSummary, DATASET, SYSTEM_DATASET, sessionPayload, mockPlatformApi, openProjects, expectWorkspaceReturnAnchor };
