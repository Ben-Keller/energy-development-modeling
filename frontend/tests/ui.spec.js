const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;

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
      payload = { project_id: PROJECT.project_id, runs: projectRuns };
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
        updated_at: "2026-06-16T14:05:00Z",
      };
      projectRuns = projectRuns.map((run) => run.run_id === updated.run_id ? updated : run);
      payload = { run: updated };
    } else if (path === `/api/projects/${PROJECT.project_id}/reports`) {
      payload = { project_id: PROJECT.project_id, reports: [] };
    } else if (path === `/api/projects/${PROJECT.project_id}/exports`) {
      payload = { project_id: PROJECT.project_id, exports: [] };
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
    const header = document.querySelector(".edim-topbar").getBoundingClientRect();
    return {
      left: rect.left,
      offsetFromHeader: rect.top - header.bottom,
    };
  });
  expect(Math.abs(anchor.left - 18), JSON.stringify(anchor)).toBeLessThanOrEqual(2);
  expect(Math.abs(anchor.offsetFromHeader - 12), JSON.stringify(anchor)).toBeLessThanOrEqual(2);
}

test.beforeEach(async ({ page }) => {
  await mockPlatformApi(page);
});

test("audience pages do not expose implementation placeholders", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("Integrated modeling workflow")).toBeVisible();
  await expect(page.getByText("EDIM_LANDING_VIDEO_SRC")).toHaveCount(0);

  await page.getByRole("button", { name: "Explore the methodology" }).click();
  await expect(page.getByRole("heading", { name: "Energy decisions rarely stay inside the energy sector" })).toBeVisible();
  await expect(page.getByText(/Placeholder visual/i)).toHaveCount(0);
});

test("Proxima Nova establishes a differentiated hierarchy", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all([
      '300 16px "Proxima Nova"',
      '400 16px "Proxima Nova"',
      'italic 400 16px "Proxima Nova"',
      '600 16px "Proxima Nova"',
      '700 16px "Proxima Nova"',
      '800 16px "Proxima Nova"',
      '900 16px "Proxima Nova"',
    ].map((spec) => document.fonts.load(spec, "Proxima Nova verification")));
  });

  const landingType = await page.evaluate(() => {
    const hero = document.querySelector(".landing-hero-card h1");
    const heroStyle = getComputedStyle(hero);
    const bodyStyle = getComputedStyle(document.body);
    const proximaFaces = [...document.fonts]
      .filter((font) => font.family.replaceAll('"', "") === "Proxima Nova");
    return {
      bodyFamily: bodyStyle.fontFamily,
      bodySize: Number.parseFloat(bodyStyle.fontSize),
      heroFamily: heroStyle.fontFamily,
      heroSize: Number.parseFloat(heroStyle.fontSize),
      proximaAvailable: document.fonts.check('400 16px "Proxima Nova"'),
      registeredFaces: proximaFaces.map((font) => `${font.style}:${font.weight}:${font.status}`),
      fontResources: performance.getEntriesByType("resource")
        .map((entry) => entry.name)
        .filter((name) => name.includes("/proxima-nova/")),
    };
  });

  expect(landingType.bodyFamily).toContain("Proxima Nova");
  expect(landingType.bodyFamily).not.toContain("EDIM Proxima Nova");
  expect(landingType.heroFamily).toContain("Proxima Nova");
  expect(landingType.proximaAvailable).toBe(true);
  expect(landingType.registeredFaces).toEqual(expect.arrayContaining([
    "normal:300:loaded",
    "normal:400:loaded",
    "normal:600:loaded",
    "normal:700:loaded",
    "normal:800:loaded",
    "normal:900:loaded",
    "italic:400:loaded",
  ]));
  expect(landingType.fontResources.some((name) => name.endsWith("proxima-nova-regular.otf"))).toBe(true);
  expect(landingType.fontResources.some((name) => name.endsWith("proxima-nova-bold.otf"))).toBe(true);
  expect(landingType.heroSize).toBeGreaterThanOrEqual(38);
  expect(landingType.heroSize).toBeGreaterThan(landingType.bodySize * 2.5);

  await page.getByRole("button", { name: "Explore the methodology" }).click();
  await expect(page.locator(".methodology-shell")).toBeVisible();
  const methodologyFamilies = await page.locator(".methodology-shell").evaluate((shell) => ({
    shell: getComputedStyle(shell).fontFamily,
    heading: getComputedStyle(shell.querySelector("h1")).fontFamily,
  }));
  expect(methodologyFamilies.shell).toContain("Proxima Nova");
  expect(methodologyFamilies.heading).toContain("Proxima Nova");
  await page.getByRole("button", { name: "Return to landing page" }).click();

  await page.getByRole("button", { name: "Open projects" }).click();
  const workspaceType = await page.evaluate(() => {
    const pageTitle = getComputedStyle(document.querySelector(".projects-overview-header h2"));
    const cardTitle = getComputedStyle(document.querySelector(".project-card-title"));
    const body = getComputedStyle(document.body);
    return {
      bodySize: Number.parseFloat(body.fontSize),
      cardSize: Number.parseFloat(cardTitle.fontSize),
      pageFamily: pageTitle.fontFamily,
      pageSize: Number.parseFloat(pageTitle.fontSize),
    };
  });

  expect(workspaceType.pageFamily).toContain("Proxima Nova");
  expect(workspaceType.pageSize).toBeGreaterThan(workspaceType.cardSize);
  expect(workspaceType.cardSize).toBeGreaterThan(workspaceType.bodySize);
});

test("top-level navigation resets the active scroll container", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("button", { name: "Explore the methodology" })).toBeVisible();
  await page.evaluate(() => {
    window.scrollTo(0, 900);
    const shell = document.querySelector(".landing-shell");
    if (shell) shell.scrollTop = 900;
    const button = [...document.querySelectorAll("button")]
      .find((element) => element.textContent.includes("Explore the methodology"));
    button.click();
  });

  await expect(page.locator(".methodology-shell")).toBeVisible();
  await expect.poll(() => page.evaluate(() => ({
    windowY: window.scrollY,
    shellY: document.querySelector(".methodology-shell")?.scrollTop || 0,
  }))).toEqual({ windowY: 0, shellY: 0 });

  await page.evaluate(() => {
    window.scrollTo(0, 900);
    const shell = document.querySelector(".methodology-shell");
    if (shell) shell.scrollTop = 900;
    document.querySelector('button[aria-label="Return to landing page"]').click();
  });
  await expect(page.locator(".landing-shell")).toBeVisible();
  await expect.poll(() => page.evaluate(() => ({
    windowY: window.scrollY,
    shellY: document.querySelector(".landing-shell")?.scrollTop || 0,
  }))).toEqual({ windowY: 0, shellY: 0 });
});

test("project name entry keeps focus across keystrokes", async ({ page }) => {
  await openProjects(page);
  await page.getByRole("button", { name: "New project" }).click();
  const input = page.getByRole("textbox", { name: "Project name" });
  await input.pressSequentially("South Africa transition study", { delay: 15 });
  await expect(input).toBeFocused();
  await expect(input).toHaveValue("South Africa transition study");
});

test("runtime switch stays visible and user selection opens from the user icon", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".runtime-target-control")).toBeVisible();
  await expect(page.locator(".runtime-target-control").getByText("Local", { exact: true })).toBeVisible();
  await expect(page.locator(".runtime-target-control").getByText("Remote", { exact: true })).toBeVisible();
  await expect(page.locator(".header-user-select")).toBeHidden();
  const userMenu = page.getByRole("button", { name: "User menu for UNDP Analyst" });
  await expect(userMenu.locator("img")).toHaveAttribute("src", "./assets/icons/user-round.svg");
  await userMenu.click();
  await expect(page.locator(".header-user-select")).toBeVisible();
  await expect(page.locator(".header-user-select select")).toHaveValue("undp_analyst");
});

test("project overview keeps workspace context above a focused project collection", async ({ page }) => {
  await openProjects(page);

  await expect(page.locator(".header-project-title")).toHaveCount(0);
  const intro = page.locator(".modeling-workspace-intro");
  await expectWorkspaceReturnAnchor(page, intro.getByRole("button", { name: "Return to home" }));
  await expect(intro.getByRole("heading", { name: "Modeling Workspace" })).toBeVisible();
  await expect(intro.getByText("Active projects", { exact: true })).toBeVisible();
  await expect(intro.getByText("Models", { exact: true })).toBeVisible();
  await expect(intro.getByText("Completed executions", { exact: true })).toBeVisible();
  await expect(intro.getByText("Geographies", { exact: true })).toBeVisible();
  await expect(intro.getByText("Current user", { exact: true })).toBeVisible();
  await expect(intro.getByText("UNDP Analyst", { exact: true })).toBeVisible();
  await expect(intro.getByText("Last active", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your Projects" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Projects" })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Datasets" })).toHaveCount(0);
  await expect(page.locator(".projects-dataset-rail")).toHaveCount(0);
  await expect(page.getByText("Project data overrides", { exact: true })).toHaveCount(0);
  await expect(page.getByText("System inputs", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Add override" })).toHaveCount(0);
  await expect(page.getByText("Not evaluated", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Exploratory only", { exact: true })).toHaveCount(0);

  const placement = await page.evaluate(() => {
    const introBox = document.querySelector(".modeling-workspace-intro").getBoundingClientRect();
    const headingBox = document.querySelector(".projects-overview-header").getBoundingClientRect();
    const gridBox = document.querySelector(".active-project-grid").getBoundingClientRect();
    return {
      introBeforeHeading: introBox.bottom <= headingBox.top,
      headingBeforeGrid: headingBox.bottom <= gridBox.top,
    };
  });
  expect(placement.introBeforeHeading).toBe(true);
  expect(placement.headingBeforeGrid).toBe(true);

  await intro.getByRole("button", { name: "Return to home" }).click();
  await expect(page.getByRole("heading", {
    name: "Model development outcomes from energy transition pathways.",
  })).toBeVisible();
});

test("project and model cards open from their full surface", async ({ page }) => {
  await openProjects(page);

  await page.locator(".project-card").first().click({ position: { x: 120, y: 104 } });
  await expect(page.locator(".project-information-bar")).toBeVisible();

  await page.locator(".project-model-card").first().click({ position: { x: 120, y: 104 } });
  await expect(page.locator(".model-run-management-pane")).toBeVisible();
});

test("archived projects stay collapsed below the active project grid", async ({ page }) => {
  await openProjects(page);
  await expect(page.locator(".archive-toggle-control")).toHaveCount(0);

  const activeGrid = page.locator(".active-project-grid");
  const archiveSection = page.locator(".archived-projects-section");
  await expect(activeGrid.getByText(PROJECT.title, { exact: true })).toBeVisible();
  await expect(archiveSection).toBeVisible();
  await expect(archiveSection.locator(".archived-projects-body")).toBeHidden();
  await expect(archiveSection.locator(".archived-projects-count")).toHaveText("0");

  const verticalOrder = await page.evaluate(() => {
    const active = document.querySelector(".active-project-grid").getBoundingClientRect();
    const archived = document.querySelector(".archived-projects-section").getBoundingClientRect();
    return archived.top >= active.bottom;
  });
  expect(verticalOrder).toBe(true);

  await archiveSection.locator("summary").click();
  await expect(archiveSection.locator(".archived-projects-body")).toBeVisible();
  await expect(archiveSection.getByText("No archived projects.", { exact: true })).toBeVisible();
  await expect(activeGrid.getByText(PROJECT.title, { exact: true })).toBeVisible();
});

test("secondary project artifacts use progressive disclosure", async ({ page }) => {
  await openProjects(page);
  await page.getByRole("button", { name: "Open project", exact: true }).click();

  const reports = page.locator("details.project-secondary-disclosure").filter({ hasText: "Reports" });
  await expect(reports).toBeVisible();
  await expect(reports.locator(".project-secondary-disclosure-body")).toBeHidden();
  await reports.locator("summary").click();
  await expect(reports.locator(".project-secondary-disclosure-body")).toBeVisible();
});

test("model comparison spans full output families and reference deltas", async ({ page }, testInfo) => {
  const runA = completedComparisonRun("run_compare_a", 1, "Current policy", "baseline", 2030);
  const runB = completedComparisonRun("run_compare_b", 2, "Accelerated transition", "high-renewables", 2040);
  const summaryA = comparisonSummary(runA, 1);
  const summaryB = comparisonSummary(runB, 1.25);
  await page.unroute("**/api/**");
  await mockPlatformApi(page, {
    projectRuns: [runA, runB],
    summaries: {
      [runA.run_id]: summaryA,
      [runB.run_id]: summaryB,
    },
  });

  await openProjects(page);
  await page.getByRole("button", { name: "Open project", exact: true }).click();
  await expect(page.getByRole("tab", { name: "Model Selection" })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Model Comparison" })).toHaveCount(0);
  const compareLaunch = page.getByRole("button", { name: /Compare models/ });
  await expect(compareLaunch).toBeDisabled();
  await expect(page.locator(".project-model-card h3").first()).toHaveCSS("color", "rgb(243, 246, 250)");
  await expect(page.locator(".project-selection-workbench")).toHaveScreenshot(
    `model-selection-comparison-entry-${testInfo.project.name}.png`
  );
  const modelSelections = page.locator(".project-model-card .project-compare-toggle input");
  await expect(modelSelections).toHaveCount(2);
  await modelSelections.nth(0).check();
  await modelSelections.nth(1).check();
  await expect(compareLaunch).toBeEnabled();
  await compareLaunch.click();
  const backToModels = page.getByRole("button", { name: "Back to models" });
  await expect(backToModels).toBeVisible();
  await expectWorkspaceReturnAnchor(page, backToModels);
  await expect(page.locator(".project-comparison-workbench")).toHaveScreenshot(
    `model-comparison-page-${testInfo.project.name}.png`
  );
  const runChoices = page.locator(".project-compare-run-pill");
  await expect(runChoices).toHaveCount(2);
  await expect(runChoices.nth(0)).toHaveAttribute("aria-pressed", "true");
  await expect(runChoices.nth(1)).toHaveAttribute("aria-pressed", "true");

  await expect(page.getByRole("heading", { name: "Comparison results" })).toBeVisible();
  await expect(page.locator(".comparison-output-tabs").getByRole("tab")).toHaveCount(7);
  await expect(page.locator(".comparison-results-total b")).not.toHaveText("0");
  await expect(page.locator(".comparison-matrix").getByText("System cost", { exact: true })).toBeVisible();
  await expect(page.locator(".comparison-value-delta").filter({ hasText: "Reference" }).first()).toBeVisible();
  await expect(page.locator(".project-comparison-table-panel")).toHaveScreenshot(
    `rich-comparison-${testInfo.project.name}.png`
  );

  await page.getByRole("tab", { name: /Energy/ }).click();
  await expect(page.getByRole("heading", { name: "Energy system" })).toBeVisible();
  const generationGroup = page.locator("details.comparison-output-group").filter({ hasText: "Generation by technology" });
  await expect(generationGroup.locator("summary")).toBeVisible();
  await generationGroup.locator("summary").click();
  await expect(generationGroup.getByText("Solar PV", { exact: true })).toBeVisible();

  await page.getByRole("tab", { name: /Cost/ }).click();
  await expect(page.getByText("Cost components", { exact: true })).toBeVisible();
  await expect(page.getByText("Reliability", { exact: true })).toBeVisible();

  await page.getByRole("tab", { name: /Development/ }).click();
  const indicatorGroup = page.locator("details.comparison-output-group").filter({ hasText: "Development indicators" });
  await expect(indicatorGroup.locator("summary")).toBeVisible();
  await indicatorGroup.locator("summary").click();
  await expect(indicatorGroup.getByText("Total employment impact", { exact: true })).toBeVisible();

  await page.getByRole("tab", { name: /Regional/ }).click();
  await expect(page.getByText("Development by region", { exact: true })).toBeVisible();
  await expect(page.getByText(/Southern Africa · Jobs/)).toBeVisible();

  await page.getByRole("tab", { name: /Quality/ }).click();
  await expect(page.getByText("Model configuration", { exact: true })).toBeVisible();
  await expect(page.getByText("Data and coupling quality", { exact: true })).toBeVisible();

  await page.getByRole("tab", { name: /Files/ }).click();
  await expect(page.getByText("Integrated results CSV", { exact: true })).toBeVisible();
  await expect(page.locator(".comparison-artifact-matrix a", { hasText: "Download" })).toHaveCount(6);

  await page.getByRole("button", { name: "Change", exact: true }).click();
  await expect(page.getByRole("button", { name: "Change", exact: true })).toHaveAttribute("aria-pressed", "true");
  const overflow = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
  }));
  expect(overflow.documentWidth).toBeLessThanOrEqual(overflow.viewportWidth + 1);

  await page.getByRole("button", { name: "Back to models" }).click();
  await expect(page.getByRole("heading", { name: "Models", exact: true })).toBeVisible();
  await expect(page.locator(".project-model-card")).toHaveCount(2);
});

test("results utilities pair warnings with downloads and keep display controls chart-local", async ({ page }, testInfo) => {
  const completedRun = completedComparisonRun(
    "run_results_controls",
    1,
    "Results controls review",
    "baseline",
    2030
  );
  const summary = comparisonSummary(completedRun, 1);
  summary.warnings = [
    "One scenario input uses a provisional coefficient.",
    "Review regional mapping coverage before publication.",
  ];
  summary.generation_by_tech.records = Array.from({ length: 12 }, (_, index) => ({
    techs: `Technology ${String(index + 1).padStart(2, "0")}`,
    value: 120 - index * 5,
  }));
  const mapLocations = ["ZAF", "KEN", "NGA", "EGY", "MAR", "GHA", "ETH", "TZA", "ZMB", "SEN", "BWA", "NAM"];
  const investmentShocks = [
    "location,region,shock_value_musd",
    ...mapLocations.map((location, index) => `${location},Africa,${(index + 1) * 12}`),
  ].join("\n");
  const operatingShocks = [
    "location,region,shock_value_musd",
    ...mapLocations.map((location, index) => `${location},Africa,${index % 3 === 0 ? -4 : 5}`),
  ].join("\n");

  await page.unroute("**/api/**");
  await mockPlatformApi(page, {
    projectRuns: [completedRun],
    summaries: { [completedRun.run_id]: summary },
    artifactTexts: {
      investment_shocks_csv: investmentShocks,
      operating_shocks_csv: operatingShocks,
    },
  });

  await openProjects(page);
  await page.getByRole("button", { name: "Open project", exact: true }).click();
  await page.getByRole("button", { name: "Open model", exact: true }).click();

  const resultsHeader = page.locator(".analysis-header-card");
  await expect(resultsHeader.getByText("Model results", { exact: true })).toBeVisible();
  await expect(resultsHeader.locator(".evidence-notice")).toHaveCount(0);
  await expect(resultsHeader.locator(".results-context-bar")).toHaveCount(0);
  await expect(resultsHeader.getByRole("heading", { name: "Results controls review", level: 1 })).toBeVisible();
  await expect(resultsHeader.getByText("Model 1: Results controls review", { exact: true })).toHaveCount(0);
  await resultsHeader.getByRole("button", { name: "Edit model name", exact: true }).click();
  const modelNameInput = resultsHeader.getByRole("textbox", { name: "Model name" });
  await expect(modelNameInput).toHaveValue("Results controls review");
  await modelNameInput.fill("Updated results model");
  await resultsHeader.getByRole("button", { name: "Save", exact: true }).click();
  await expect(resultsHeader.getByRole("heading", { name: "Updated results model", level: 1 })).toBeVisible();
  const titleActions = resultsHeader.locator(".analysis-title-actions");
  await expect(titleActions.getByRole("button", { name: "Duplicate model", exact: true })).toBeVisible();
  await expect(titleActions.getByRole("button", { name: "Technical details", exact: true })).toBeVisible();
  await expect(titleActions.getByRole("button", { name: "Execution management", exact: true })).toHaveCount(0);
  await expect(titleActions.getByRole("button", { name: "Technical execution", exact: true })).toHaveCount(0);
  await expect(titleActions.getByRole("button", { name: "Selected model details", exact: true })).toHaveCount(0);
  await expect(resultsHeader.locator(".analysis-model-title-edit-icon")).toHaveCount(1);
  const inlineTechnicalExecution = resultsHeader.locator(".analysis-inline-technical-execution");
  await expect(inlineTechnicalExecution).toBeVisible();
  await expect(inlineTechnicalExecution.getByText("Architecture", { exact: true })).toBeVisible();
  await expect(inlineTechnicalExecution.getByText("Energy model", { exact: true })).toBeVisible();
  await expect(inlineTechnicalExecution.getByText("Target pathway", { exact: true })).toHaveCount(1);
  await expect(resultsHeader.getByText(/MRIO shock mapping:/)).toHaveCount(0);
  await expect(titleActions.locator("details.analysis-warning-menu")).toHaveCount(0);
  const downloadsMenu = titleActions.locator("details.analysis-download-menu");
  await expect(downloadsMenu.locator("summary")).toHaveText("Downloads");
  await expect(downloadsMenu.locator(".analysis-download-chevron")).toHaveCount(1);
  const actionRows = await titleActions.locator(":scope > button, :scope > .analysis-output-action-pair").evaluateAll((items) =>
    items.map((item) => {
      const rect = item.getBoundingClientRect();
      return { top: rect.top, bottom: rect.bottom };
    })
  );
  expect(actionRows).toHaveLength(3);
  expect(actionRows[1].top).toBeGreaterThanOrEqual(actionRows[0].bottom);
  expect(actionRows[2].top).toBeGreaterThanOrEqual(actionRows[1].bottom);
  await expect(resultsHeader.getByText("Chart display", { exact: true })).toHaveCount(0);
  await expect(resultsHeader.getByText("Run technical details", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Fit to data", exact: true })).toHaveCount(0);
  await downloadsMenu.locator("summary").click();
  await expect(downloadsMenu.getByRole("link", { name: "Results CSV" })).toBeVisible();
  await expect(downloadsMenu.getByRole("link", { name: "Summary JSON" })).toBeVisible();
  await downloadsMenu.locator("summary").click();
  const resultTabs = page.locator(".results-section-tab-row");
  await expect(resultTabs).toBeVisible();
  await expect(resultsHeader.locator(".results-section-tabs")).toHaveCount(0);
  expect(await resultTabs.evaluate((tabs) => !tabs.closest(".analysis-header-card"))).toBe(true);
  await expect(resultsHeader).toHaveScreenshot(`results-title-utilities-${testInfo.project.name}.png`);

  await expect(page.locator(".scenario-definition-strip")).toHaveCount(0);
  await titleActions.getByRole("button", { name: "Technical details", exact: true }).click();
  const technicalDetailsDialog = page.getByRole("dialog", { name: "Technical details" });
  await expect(technicalDetailsDialog.locator(".results-technical-summary .results-kpi-group-label")).toHaveText("Execution environment");
  await expect(technicalDetailsDialog.getByText("Solver: highs", { exact: true })).toBeVisible();
  await expect(technicalDetailsDialog.getByText("Termination: optimal", { exact: true })).toBeVisible();
  await expect(technicalDetailsDialog.getByText(/MRIO shock mapping:/)).toBeVisible();
  await expect(technicalDetailsDialog.getByText("mrio_direct_heuristic", { exact: true })).toBeVisible();
  await expect(technicalDetailsDialog.getByText("Selected model record", { exact: true })).toBeVisible();
  await expect(technicalDetailsDialog.getByText("Selected model:", { exact: true })).toBeVisible();
  await expect(technicalDetailsDialog.getByText("Execution warnings", { exact: true })).toBeVisible();
  await expect(technicalDetailsDialog.getByText("One scenario input uses a provisional coefficient.")).toBeVisible();
  await expect(technicalDetailsDialog.getByRole("link", { name: "Results CSV" })).toHaveCount(0);
  await expect(technicalDetailsDialog.getByRole("link", { name: "Summary JSON" })).toHaveCount(0);
  await expect(technicalDetailsDialog.locator(".modal-body")).toHaveScreenshot(`technical-details-area-${testInfo.project.name}.png`);
  await technicalDetailsDialog.getByRole("button", { name: "Close Technical details" }).click();

  const mapStage = page.locator(".spatial-results-map-stage");
  const mapDistribution = mapStage.locator(".map-distribution-overlay");
  const geographicKpis = page.locator(".results-geographic-kpi-strip");
  const runWidePanel = page.locator(".results-run-wide-panel");
  await expect(geographicKpis).toBeVisible();
  await expect(geographicKpis.getByText("Key outcomes", { exact: true })).toBeVisible();
  await expect(resultsHeader.getByText("Geography", { exact: true })).toHaveCount(0);
  await expect(geographicKpis.getByText("System cost (USD)", { exact: true })).toBeVisible();
  await expect(geographicKpis.getByText("Physical emissions (tCO2)", { exact: true })).toBeVisible();
  await expect(geographicKpis.getByText("Jobs (jobs)", { exact: true })).toHaveCount(0);
  await expect(geographicKpis.getByText("CAPEX effect (MUSD)", { exact: true })).toBeVisible();
  await expect(geographicKpis.getByText("OPEX effect (MUSD)", { exact: true })).toBeVisible();
  await expect(geographicKpis.getByText("Reliability penalty (MUSD)", { exact: true })).toBeVisible();
  await expect(runWidePanel).toBeVisible();
  await expect(runWidePanel.getByText("Overall results", { exact: true })).toBeVisible();
  await expect(page.getByText("Geography-responsive results", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Not affected by map selection", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Scenario-wide results", { exact: true })).toHaveCount(0);
  await expect(runWidePanel.getByText("Jobs (jobs)", { exact: true })).toBeVisible();
  await expect(runWidePanel.getByText("System cost (USD)", { exact: true })).toHaveCount(0);
  await expect(runWidePanel.getByText("Physical emissions (tCO2)", { exact: true })).toHaveCount(0);
  await expect(runWidePanel.getByText("Import leakage (MUSD)", { exact: true })).toBeVisible();
  await expect(runWidePanel.getByText("CAPEX effect (MUSD)", { exact: true })).toHaveCount(0);
  await expect(runWidePanel.getByText("OPEX effect (MUSD)", { exact: true })).toHaveCount(0);
  await expect(runWidePanel.getByText("Reliability penalty (MUSD)", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Select an area for local results", { exact: true })).toHaveCount(0);
  const geographicAboveMap = await page.locator(".results-map-widget-column").evaluate((column) => {
    const kpis = column.querySelector(".results-geographic-kpi-strip");
    const map = column.querySelector(".spatial-results-map-card");
    if (!kpis || !map) return false;
    return kpis.getBoundingClientRect().bottom <= map.getBoundingClientRect().top;
  });
  expect(geographicAboveMap).toBe(true);
  const runWideTextBeforeFilter = await runWidePanel.innerText();
  await expect(mapDistribution).toBeVisible();
  await expect(mapDistribution.getByLabel(/Histogram distribution for/)).toBeVisible();
  await expect(page.getByText("Map coverage and distribution", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Geometry and source details", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Model locations:", { exact: false })).toHaveCount(0);
  await expect(page.getByText(/Click any country\/subregion to filter/)).toHaveCount(0);
  await expect(page.getByText(/Spatial filter is active for mappable datasets/)).toHaveCount(0);
  const attachedDistribution = await mapDistribution.evaluate((overlay) => {
    const histogram = overlay.querySelector(".map-distribution-histogram");
    const gradient = overlay.querySelector(".map-distribution-gradient");
    const stage = overlay.closest(".spatial-results-map-stage");
    if (!histogram || !gradient || !stage) return null;
    const histogramRect = histogram.getBoundingClientRect();
    const gradientRect = gradient.getBoundingClientRect();
    const overlayRect = overlay.getBoundingClientRect();
    const stageRect = stage.getBoundingClientRect();
    return {
      histogramGap: gradientRect.top - histogramRect.bottom,
      histogramInset:
        Math.min(histogramRect.left - gradientRect.left, gradientRect.right - histogramRect.right),
      contained:
        overlayRect.left >= stageRect.left &&
        overlayRect.right <= stageRect.right &&
        overlayRect.top >= stageRect.top &&
        overlayRect.bottom <= stageRect.bottom,
    };
  });
  expect(attachedDistribution.histogramGap).toBeGreaterThanOrEqual(4);
  expect(attachedDistribution.histogramGap).toBeLessThanOrEqual(5);
  expect(attachedDistribution.histogramInset).toBeGreaterThanOrEqual(6);
  expect(attachedDistribution.contained).toBe(true);
  await expect(mapStage).toHaveScreenshot(`map-integrated-distribution-${testInfo.project.name}.png`);
  await expect(page.locator(".results-overview-widget-layout")).toHaveScreenshot(
    `results-scope-layout-${testInfo.project.name}.png`
  );

  await page.locator(".spatial-results-map-host .leaflet-overlay-pane path").first().click({ force: true });
  await expect(resultsHeader.locator(".results-context-bar")).toHaveCount(0);
  await expect(geographicKpis.locator(".results-scope-badge")).toHaveCount(0);
  await expect(page.getByText("Raw selection payload", { exact: true })).toHaveCount(0);
  await expect(page.getByText(/Country\/subregion selection applies strict unit alignment/)).toHaveCount(0);
  await expect(geographicKpis).toHaveScreenshot(`filtered-results-box-${testInfo.project.name}.png`);
  expect(await runWidePanel.innerText()).toBe(runWideTextBeforeFilter);

  await resultTabs.getByRole("tab", { name: "Energy system" }).click();
  const systemDiagnostics = page.locator("section.results-section-static").filter({
    hasText: "System diagnostics",
  });
  await expect(systemDiagnostics).toBeVisible();
  await expect(systemDiagnostics.getByRole("heading", { name: "Reliability snapshot" })).toBeVisible();
  await expect(page.locator("details.results-section-disclosure").filter({
    hasText: "System diagnostics",
  })).toHaveCount(0);
  const generationCard = page.locator(".analysis-section-body .card").filter({
    has: page.getByRole("heading", { name: "Generation by technology" }),
  }).first();
  const chartControls = generationCard.getByRole("group", {
    name: "generation by technology display controls",
  });
  await expect(chartControls).toBeVisible();
  await expect(page.getByText("Chart display", { exact: true })).toHaveCount(0);
  await expect(generationCard.locator(".hbar-row")).toHaveCount(10);
  await chartControls.getByRole("combobox", {
    name: "Rows shown for generation by technology",
  }).selectOption("15");
  await expect(generationCard.locator(".hbar-row")).toHaveCount(12);
  await expect(generationCard.getByRole("searchbox")).toHaveCount(0);
  await expect(page.getByPlaceholder("Filter labels")).toHaveCount(0);
  await expect(generationCard).toHaveScreenshot(`chart-local-display-controls-${testInfo.project.name}.png`);

  await resultTabs.getByRole("tab", { name: "Development" }).click();
  const developmentCoverage = page.locator("section.results-section-static").filter({
    hasText: "Assumptions and indicator coverage",
  });
  await expect(developmentCoverage).toBeVisible();
  await expect(developmentCoverage.getByRole("heading", { name: "Scenario assumptions" })).toBeVisible();
  await expect(developmentCoverage.getByRole("heading", { name: "Development indicators" })).toBeVisible();
  await expect(page.locator("details.results-section-disclosure").filter({
    hasText: "Assumptions and indicator coverage",
  })).toHaveCount(0);
});

test("project and model cards render evolving identity visuals", async ({ page }) => {
  await openProjects(page);
  const projectVisual = page.locator(".project-card .project-identity-visual");
  await expect(projectVisual).toBeVisible();
  await expect(projectVisual).toHaveAttribute(
    "aria-label",
    /National transition planning visual: 3 models, 1 complete/
  );
  await expect(projectVisual).toHaveAttribute("data-sector-count", "3");
  const projectRevision = await projectVisual.getAttribute("data-identity-revision");
  const projectMarkup = await projectVisual.evaluate((element) => element.innerHTML);
  await expect(projectVisual.locator(".entity-identity-shape")).toHaveCount(3);
  await expect(projectVisual.locator(".model-identity-circle-field")).toHaveCount(3);
  await expect(projectVisual.locator("[data-model-circle]")).toHaveCount(3);
  await expect(projectVisual.locator("[data-project-sector]")).toHaveCount(3);
  await expect(projectVisual.locator("mask path")).toHaveCount(3);
  const sectorFeather = projectVisual.locator('filter[id^="project-sector-feather-"] feGaussianBlur');
  await expect(sectorFeather).toHaveAttribute("stdDeviation", "0.85");
  await expect(projectVisual.locator(".identity-gradient-layer--project-core")).toHaveCount(0);
  await expect(projectVisual.locator(".project-identity-sector-field[transform]")).toHaveCount(0);
  await expect(projectVisual.locator("clipPath circle")).toHaveAttribute("r", "46");
  await expect(projectVisual.locator("linearGradient")).not.toHaveCount(0);
  await expect(projectVisual.locator("radialGradient")).not.toHaveCount(0);
  await expect(projectVisual.locator("line")).toHaveCount(0);
  await expect(projectVisual.locator("[stroke]")).toHaveCount(0);

  await page.getByRole("button", { name: "Open project", exact: true }).click();
  await expect(page.getByText("Not evaluated", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Exploratory only", { exact: true })).toHaveCount(0);
  const projectInformation = page.locator(".project-information-bar");
  await expect(projectInformation).toBeVisible();
  await expect(page.locator(".header-project-title")).toHaveCount(0);
  const backToProjects = projectInformation.getByRole("button", { name: "Back to projects" });
  await expect(backToProjects).toBeVisible();
  await expectWorkspaceReturnAnchor(page, backToProjects);
  await expect(projectInformation.getByRole("heading", { name: PROJECT.title, level: 1 })).toBeVisible();
  expect(await backToProjects.evaluate((button) => (
    button.compareDocumentPosition(button.parentElement.querySelector("h1")) & Node.DOCUMENT_POSITION_FOLLOWING
  ))).toBeTruthy();
  const projectHeadingAlignment = await projectInformation.evaluate((element) => {
    const back = element.querySelector(".workspace-back-button").getBoundingClientRect();
    const title = element.querySelector("h1").getBoundingClientRect();
    return { backRight: back.right, titleLeft: title.left };
  });
  expect(projectHeadingAlignment.titleLeft).toBeGreaterThan(projectHeadingAlignment.backRight);
  await expect(projectInformation.getByText("South Africa", { exact: true })).toBeVisible();
  await expect(projectInformation.getByText("Energy-Development", { exact: true })).toBeVisible();
  await expect(projectInformation.locator(".project-information-meta-item")).toHaveCount(4);
  await expect(projectInformation.locator(".project-information-icon")).toHaveCount(4);
  await expect(projectInformation.locator(".project-information-stats strong")).toHaveText(["1", "0", "0", "0"]);
  await expect(projectInformation.getByRole("button", { name: "New model" })).toBeVisible();
  await expect(page.locator(".project-selection-toolbar").getByRole("button", { name: "New model" })).toHaveCount(0);
  const informationLayout = await projectInformation.evaluate((element) => {
    const heading = element.querySelector("h1");
    const rect = element.getBoundingClientRect();
    const parentRect = element.parentElement.getBoundingClientRect();
    return {
      headingSize: Number.parseFloat(getComputedStyle(heading).fontSize),
      widthDelta: Math.abs(rect.width - parentRect.width),
    };
  });
  expect(informationLayout.headingSize).toBeGreaterThanOrEqual(30);
  expect(informationLayout.widthDelta).toBeLessThanOrEqual(2);
  const modelVisual = page.locator(".project-model-card .model-identity-visual");
  await expect(modelVisual).toBeVisible();
  await expect(modelVisual).toHaveAttribute(
    "aria-label",
    /Model 1: Baseline planning case visual: draft, energy-development/
  );
  await expect(modelVisual.locator("clipPath circle")).toHaveAttribute("r", "46");
  await expect(modelVisual.locator("path")).not.toHaveCount(0);
  await expect(modelVisual.locator("linearGradient")).not.toHaveCount(0);
  await expect(modelVisual.locator("radialGradient")).not.toHaveCount(0);
  await expect(modelVisual.locator("feGaussianBlur")).toHaveCount(3);
  await expect(modelVisual.locator("line")).toHaveCount(0);
  await expect(modelVisual.locator("[stroke]")).toHaveCount(0);

  await page.getByRole("button", { name: "Back to projects" }).click();
  await expect(projectVisual).toHaveAttribute("data-identity-revision", projectRevision);
  await expect(projectVisual).toHaveJSProperty("innerHTML", projectMarkup);
});

test("model setup prioritizes essential choices", async ({ page }, testInfo) => {
  await openProjects(page);
  await page.getByRole("button", { name: "Open project", exact: true }).click();
  await page.getByRole("button", { name: "Open model", exact: true }).click();

  await expect(page.locator(".flow-model-canvas")).toBeVisible();
  const projectContext = page.locator(".run-project-context");
  await expect(projectContext.getByRole("button", { name: "Return to project" })).toBeVisible();
  await expectWorkspaceReturnAnchor(page, projectContext.getByRole("button", { name: "Return to project" }));
  await expect(projectContext.locator(".run-project-title")).toHaveText(PROJECT.title);
  const modelNavigationAlignment = await projectContext.evaluate((element) => {
    const back = element.querySelector(".workspace-back-button").getBoundingClientRect();
    const title = element.querySelector(".run-project-title").getBoundingClientRect();
    return { backRight: back.right, titleLeft: title.left };
  });
  expect(modelNavigationAlignment.titleLeft).toBeGreaterThan(modelNavigationAlignment.backRight);
  await expect(page.getByRole("tab", { name: PROJECT.title })).toHaveCount(0);
  await expect(page.locator(".model-project-context")).toHaveCount(0);
  await expect(page.locator(".header-project-title")).toHaveCount(0);
  const modelTabHierarchy = await page.getByRole("tab", {
    name: /Model 1: Baseline planning case - draft/,
  }).evaluate((tab) => {
    const title = tab.querySelector(".run-tab-title");
    const subtitle = tab.querySelector(".run-tab-subtitle");
    if (!title || !subtitle) return null;
    const titleStyle = getComputedStyle(title);
    const subtitleStyle = getComputedStyle(subtitle);
    return {
      title: title.textContent.trim(),
      subtitle: subtitle.textContent.trim(),
      titleSize: Number.parseFloat(titleStyle.fontSize),
      subtitleSize: Number.parseFloat(subtitleStyle.fontSize),
      titleTop: title.getBoundingClientRect().top,
      subtitleTop: subtitle.getBoundingClientRect().top,
    };
  });
  expect(modelTabHierarchy).toEqual(expect.objectContaining({
    title: "Baseline planning case",
    subtitle: "Model 1",
  }));
  expect(modelTabHierarchy.titleSize).toBeGreaterThanOrEqual(15);
  expect(modelTabHierarchy.subtitleSize).toBeGreaterThanOrEqual(13);
  expect(modelTabHierarchy.titleTop).toBeLessThan(modelTabHierarchy.subtitleTop);
  const projectTitleSize = await projectContext.locator(".run-project-title").evaluate((title) =>
    Number.parseFloat(getComputedStyle(title).fontSize)
  );
  expect(projectTitleSize).toBeGreaterThanOrEqual(20);
  expect(projectTitleSize).toBeGreaterThan(modelTabHierarchy.titleSize);
  await expect(page.locator(".global-run-tab-bar")).toHaveScreenshot(
    `model-navigation-${testInfo.project.name}.png`
  );
  const editableModelTab = page.getByRole("tab", {
    name: /Model 1: Baseline planning case - draft/,
  });
  await editableModelTab.locator(".run-tab-title").dblclick();
  const renameModelInput = page.getByRole("textbox", { name: "Rename Baseline planning case" });
  await expect(renameModelInput).toBeVisible();
  await expect(renameModelInput).toHaveValue("Baseline planning case");
  await renameModelInput.fill("Grid transition baseline");
  await renameModelInput.press("Enter");
  await expect(page.getByRole("tab", {
    name: /Model 1: Grid transition baseline - draft/,
  })).toBeVisible();
  await expect(page.getByText("Model setup", { exact: true })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Setup" })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Model flow" })).toHaveCount(0);
  const inputModule = page.locator(".input-module-layout");
  await expect(inputModule).toBeVisible();
  const inputNodeBottomSpacing = await page.locator(".flow-node.node-scenario").evaluate((node) => {
    const layout = node.querySelector(".input-module-layout");
    const footer = node.querySelector(".flow-node-drag-footer");
    if (!layout || !footer) return null;
    const nodeRect = node.getBoundingClientRect();
    const layoutRect = layout.getBoundingClientRect();
    const footerStyle = getComputedStyle(footer);
    return {
      gap: nodeRect.bottom - layoutRect.bottom,
      footerPosition: footerStyle.position,
      footerBottom: footerStyle.bottom,
    };
  });
  expect(inputNodeBottomSpacing).toEqual(expect.objectContaining({
    footerPosition: "absolute",
    footerBottom: "0px",
  }));
  expect(inputNodeBottomSpacing.gap).toBeLessThanOrEqual(6);
  await expect(
    inputModule.locator(".diagram-selector-stack .run-setup-group-eyebrow")
  ).toHaveText(["Model", "Scenario", "Execution"]);
  await expect(inputModule.getByText("Energy model engine", { exact: true })).toBeVisible();
  await expect(inputModule.getByText("Execution profile", { exact: true })).toBeVisible();
  await expect(page.getByText("Policy levers", { exact: true })).toBeVisible();
  await expect(page.getByText("Execution settings", { exact: true })).toHaveCount(0);
  await expect(inputModule.getByText("Technical execution", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Selected model details", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Progress:", { exact: false })).toHaveCount(0);
  await expect(page.getByText("Outputs will appear here", { exact: false })).toHaveCount(0);
  const readinessPanel = page.locator(".run-readiness-panel");
  await expect(readinessPanel.getByText("Execution name", { exact: true })).toHaveCount(0);
  await expect(readinessPanel.locator(".run-name-control")).toHaveCount(0);
  await expect(readinessPanel.getByText("Readiness details", { exact: true })).toHaveCount(0);
  await expect(readinessPanel.getByText("Validation checks", { exact: true })).toBeVisible();
  await expect(readinessPanel.getByText("No validation warnings or errors", { exact: false })).toHaveCount(0);
  const diagnosticButton = readinessPanel.getByRole("button", {
    name: "Open full technical readiness diagnostic",
  });
  await expect(diagnosticButton).toBeVisible();
  await expect(readinessPanel.getByText("Passed", { exact: true })).toBeVisible();
  const technicalExecutionButton = readinessPanel.getByRole("button", { name: "Technical execution", exact: true });
  await expect(technicalExecutionButton).toBeVisible();
  await expect(readinessPanel).toHaveScreenshot(`validation-checks-${testInfo.project.name}.png`);
  await technicalExecutionButton.click();
  const technicalExecutionDialog = page.getByRole("dialog", { name: "Technical execution" });
  await expect(technicalExecutionDialog.getByText("Architecture", { exact: true })).toBeVisible();
  await technicalExecutionDialog.getByRole("button", { name: "Close Technical execution" }).click();
  await diagnosticButton.click();
  const diagnosticDialog = page.getByRole("dialog", { name: "Technical readiness diagnostic" });
  await expect(diagnosticDialog).toBeVisible();
  await expect(diagnosticDialog.locator(".modal-body").getByText("Validation checks", { exact: true })).toBeVisible();
  await diagnosticDialog.getByRole("button", { name: "Close Technical readiness diagnostic" }).click();
  await expect(diagnosticDialog).toBeHidden();
  const draftPanel = page.locator(".draft-save-panel");
  await expect(draftPanel.getByText("Last edited", { exact: true })).toBeVisible();
  await expect(draftPanel.getByRole("button", { name: "Save draft" })).toBeVisible();
  await draftPanel.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByText("Draft saved.", { exact: true })).toBeVisible();
  await expect(draftPanel.locator("time")).toHaveAttribute("datetime", "2026-06-16T14:05:00Z");
  await expect(draftPanel).toHaveScreenshot(`draft-save-state-${testInfo.project.name}.png`);
});

test("graph display tools stay visible and mobile canvas remains bounded", async ({ page }, testInfo) => {
  await openProjects(page);
  await page.getByRole("button", { name: "Open project", exact: true }).click();
  await page.getByRole("button", { name: "Open model", exact: true }).click();

  await expect(page.locator(".flow-model-canvas")).toBeVisible();
  const inputNode = page.locator(".flow-node.node-scenario");
  await expect(inputNode).not.toHaveClass(/fixed/);
  const initialGraphAlignment = await page.locator(".flow-model-viewport").evaluate((viewport) => {
    const canvas = viewport.querySelector(".flow-model-canvas");
    const input = viewport.querySelector(".flow-node.node-scenario");
    if (!canvas || !input) return null;
    const canvasBounds = canvas.getBoundingClientRect();
    const inputBounds = input.getBoundingClientRect();
    return {
      scrollLeft: viewport.scrollLeft,
      centeredScrollLeft: Math.max(0, (viewport.scrollWidth - viewport.clientWidth) / 2),
      inputCenterOffset:
        inputBounds.left + inputBounds.width / 2 - (canvasBounds.left + canvasBounds.width / 2),
    };
  });
  expect(initialGraphAlignment).not.toBeNull();
  expect(Math.abs(initialGraphAlignment.scrollLeft - initialGraphAlignment.centeredScrollLeft)).toBeLessThan(3);
  expect(Math.abs(initialGraphAlignment.inputCenterOffset)).toBeLessThan(3);
  await expect(page.locator(".flow-display-menu")).toHaveCount(0);
  const graphDisplay = page.locator(".flow-display-controls-expanded");
  await expect(graphDisplay.getByText("Graph display", { exact: true })).toBeVisible();
  await expect(graphDisplay.getByRole("button", { name: "Single" })).toBeVisible();
  await expect(graphDisplay.getByRole("button", { name: "Data" })).toBeVisible();
  await expect(graphDisplay.getByRole("button", { name: "Layers" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Reset layout" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Expand all|Collapse all/ })).toBeVisible();
  await graphDisplay.getByRole("button", { name: "Data" }).click();
  await expect(graphDisplay.getByRole("button", { name: "Data" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".flow-model-toolbar")).toHaveScreenshot(
    `graph-display-expanded-${testInfo.project.name}.png`
  );

  if (!testInfo.project.name.includes("mobile")) {
    const collapsedNode = page.locator(".flow-node.node-calliope");
    const collapsedWidth = await collapsedNode.evaluate((element) => element.getBoundingClientRect().width);
    await collapsedNode.getByRole("button", { name: "Expand" }).click();
    await page.waitForTimeout(220);
    const expandedWidth = await collapsedNode.evaluate((element) => element.getBoundingClientRect().width);
    expect(expandedWidth).toBeGreaterThan(collapsedWidth + 40);
    await expect(collapsedNode).toHaveScreenshot(
      `flow-node-horizontal-expanded-${testInfo.project.name}.png`
    );

    const viewportElement = page.locator(".flow-model-viewport");
    const panStart = await viewportElement.evaluate((viewport) => {
      const bounds = viewport.getBoundingClientRect();
      for (let y = bounds.bottom - 28; y > bounds.top + 80; y -= 24) {
        for (let x = bounds.right - 28; x > bounds.left + 80; x -= 24) {
          const target = document.elementFromPoint(x, y);
          if (target && !target.closest(".flow-node, button, input, select, textarea, a, label, .flow-edge-hover-target")) {
            return { x, y };
          }
        }
      }
      return null;
    });
    expect(panStart).not.toBeNull();
    await page.mouse.move(panStart.x, panStart.y);
    await page.mouse.down();
    await page.mouse.move(panStart.x - 90, panStart.y - 70, { steps: 5 });
    await page.mouse.up();
    const panned = await viewportElement.evaluate((viewport) => ({
      left: viewport.scrollLeft,
      top: viewport.scrollTop,
    }));
    expect(panned.left).toBeGreaterThan(50);
    expect(panned.top).toBeGreaterThan(30);
    await viewportElement.evaluate((viewport) => viewport.scrollTo(0, 0));

    const header = inputNode.locator(".flow-node-header");
    const before = await inputNode.boundingBox();
    const handle = await header.boundingBox();
    expect(before).not.toBeNull();
    expect(handle).not.toBeNull();
    await page.mouse.move(handle.x + 24, handle.y + 24);
    await page.mouse.down();
    await page.mouse.move(handle.x + 84, handle.y + 64, { steps: 5 });
    await page.mouse.up();
    const after = await inputNode.boundingBox();
    expect(after.x).toBeGreaterThan(before.x + 40);
    expect(after.y).toBeGreaterThan(before.y + 20);
    await page.getByRole("button", { name: "Reset layout" }).click();
    const reset = await inputNode.boundingBox();
    expect(Math.abs(reset.x - before.x)).toBeLessThan(5);
    expect(Math.abs(reset.y - before.y)).toBeLessThan(5);

    await collapsedNode.getByRole("button", { name: "Collapse" }).click();
    const bottomHandle = collapsedNode.locator(".flow-node-drag-footer");
    await expect(bottomHandle).toBeVisible();
    await bottomHandle.scrollIntoViewIfNeeded();
    const bottomBefore = await collapsedNode.evaluate((element) => ({
      left: Number.parseFloat(element.style.left),
      top: Number.parseFloat(element.style.top),
    }));
    const bottomHandleBox = await bottomHandle.boundingBox();
    expect(bottomHandleBox).not.toBeNull();
    await page.mouse.move(
      bottomHandleBox.x + bottomHandleBox.width / 2,
      bottomHandleBox.y + bottomHandleBox.height / 2
    );
    await page.mouse.down();
    await page.mouse.move(
      bottomHandleBox.x + bottomHandleBox.width / 2 + 64,
      bottomHandleBox.y + bottomHandleBox.height / 2 + 42,
      { steps: 5 }
    );
    await page.mouse.up();
    const bottomAfter = await collapsedNode.evaluate((element) => ({
      left: Number.parseFloat(element.style.left),
      top: Number.parseFloat(element.style.top),
    }));
    expect(bottomAfter.left).toBeGreaterThan(bottomBefore.left + 44);
    expect(bottomAfter.top).toBeGreaterThan(bottomBefore.top + 24);
    await page.getByRole("button", { name: "Reset layout" }).click();
  }

  if (testInfo.project.name.includes("mobile")) {
    const viewport = await page.locator(".flow-model-viewport").boundingBox();
    expect(viewport.height).toBeLessThanOrEqual(622);
  }
});

test("run-specific status does not leak into the projects overview", async ({ page }) => {
  await openProjects(page);
  await page.getByRole("button", { name: "Open project", exact: true }).click();
  await page.getByRole("button", { name: "Open model", exact: true }).click();
  await expect(page.locator(".model-run-management-pane").getByRole("heading", { name: "Execution", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Return to project" }).click();
  await expect(page.getByText(/Selected execution/)).toHaveCount(0);
  await expect(page.locator(".project-information-bar")).toBeVisible();
  await expect(page.locator(".project-model-card").first()).toBeVisible();
});

test("core workspace surfaces meet automated accessibility checks", async ({ page }) => {
  await openProjects(page);

  const projectsAudit = await new AxeBuilder({ page })
    .include(".projects-overview-panel")
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(projectsAudit.violations).toEqual([]);

  await page.getByRole("button", { name: "Open project", exact: true }).click();
  await page.getByRole("button", { name: "Open model", exact: true }).click();
  const modelAudit = await new AxeBuilder({ page })
    .include("#model-workspace-primary")
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(modelAudit.violations).toEqual([]);

  const nestedInteractive = await page.evaluate(() => (
    [...document.querySelectorAll('[role="button"]')]
      .filter((element) => element.querySelector("button, a[href], input, select, textarea"))
      .map((element) => element.outerHTML.slice(0, 200))
  ));
  expect(nestedInteractive).toEqual([]);
});

test("network failures are classified with an actionable service message", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.route("**/api/test-unavailable", (route) => route.abort("connectionrefused"));

  const failure = await page.evaluate(async () => {
    try {
      await window.EDIM_HTTP_CLIENT.apiGet("/api/test-unavailable", "Failed to load test data");
      return null;
    } catch (error) {
      return {
        message: error.message,
        kind: error.kind,
        requestId: error.requestId,
      };
    }
  });

  expect(failure).toEqual(expect.objectContaining({
    kind: "unavailable",
  }));
  expect(failure.message).toContain("Cannot reach the modeling service");
  expect(failure.requestId).toMatch(/^edim-|^[0-9a-f-]{36}$/);
});

test("projects overview visual baseline", async ({ page }, testInfo) => {
  await openProjects(page);
  const panel = page.locator(".projects-overview-panel");
  await expect(panel).toBeVisible();
  const projectCardSpacing = await page.locator(".project-card").first().evaluate((card) => {
    const visual = card.querySelector(".project-card-visual-wrap").getBoundingClientRect();
    const open = card.querySelector(".project-open-link").getBoundingClientRect();
    return {
      horizontalGap: visual.left - open.right,
      overlaps: !(
        open.right <= visual.left ||
        open.left >= visual.right ||
        open.bottom <= visual.top ||
        open.top >= visual.bottom
      ),
    };
  });
  expect(projectCardSpacing.overlaps).toBe(false);
  expect(projectCardSpacing.horizontalGap).toBeGreaterThanOrEqual(10);

  const archiveAlignment = await page.locator(".archived-projects-section > summary").evaluate((summary) => {
    const summaryRect = summary.getBoundingClientRect();
    const copyRect = summary.querySelector(".archived-projects-copy").getBoundingClientRect();
    return {
      distanceFromLeft: copyRect.left - summaryRect.left,
      distanceFromRight: summaryRect.right - copyRect.right,
      textAlign: getComputedStyle(summary.querySelector(".archived-projects-copy")).textAlign,
    };
  });
  expect(archiveAlignment.distanceFromRight).toBeLessThan(80);
  expect(archiveAlignment.distanceFromLeft).toBeGreaterThan(archiveAlignment.distanceFromRight);
  expect(archiveAlignment.textAlign).toBe("right");
  await expect(panel).toHaveScreenshot(`projects-overview-${testInfo.project.name}.png`);
});
