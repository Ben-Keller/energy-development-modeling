const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;
const { PROJECT, DRAFT_RUN, completedComparisonRun, comparisonSummary, DATASET, SYSTEM_DATASET, sessionPayload, mockPlatformApi, openProjects, expectWorkspaceReturnAnchor } = require("./platform-fixtures");

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
  await expect(intro.getByRole("heading", { name: "Your Projects" })).toBeVisible();
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
  await expect(page.getByText("Not evaluated", { exact: true }).first()).toBeVisible();
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

  await page.locator(".project-model-card").first().click({ position: { x: 12, y: 12 } });
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
  await expect(resultsHeader.locator(".evidence-notice")).toBeVisible();
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
  await titleActions.getByRole("button", { name: "Model actions", exact: true }).click();
  await expect(page.getByRole("dialog", {name:"Model actions"}).getByRole("button", {name:"Duplicate model", exact:true})).toBeVisible();
  await page.getByRole("button", {name:"Close Model actions"}).click();
  await expect(titleActions.getByRole("button", { name: "Technical details", exact: true })).toBeVisible();
  await expect(titleActions.getByRole("button", { name: "Execution management", exact: true })).toHaveCount(0);
  await expect(titleActions.getByRole("button", { name: "Technical execution", exact: true })).toHaveCount(0);
  await expect(titleActions.getByRole("button", { name: "Selected model details", exact: true })).toHaveCount(0);
  await expect(resultsHeader.locator(".analysis-model-title-edit-icon")).toHaveCount(1);
  await page.locator(".recorded-inputs > summary").click();
  const inlineTechnicalExecution = page.locator(".recorded-inputs");
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
  for (const row of actionRows) expect(row.bottom).toBeGreaterThan(row.top);
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
  await expect(generationCard.getByRole("searchbox")).toBeVisible();
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

test("project identities persist while model cards prioritize readable metadata", async ({ page }) => {
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
  await expect(page.getByText("Not evaluated", { exact: true }).first()).toBeVisible();
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
    return { backBottom: back.bottom, titleTop: title.top };
  });
  expect(projectHeadingAlignment.titleTop).toBeGreaterThan(projectHeadingAlignment.backBottom);
  await expect(projectInformation.getByText("South Africa", { exact: true })).toBeVisible();
  await expect(projectInformation.getByText("Energy-Development", { exact: true })).toBeVisible();
  await expect(projectInformation.locator(".project-information-meta-item")).toHaveCount(4);
  await expect(projectInformation.locator(".project-information-icon")).toHaveCount(4);
  await expect(projectInformation.locator(".project-information-stats strong")).toHaveText(["1", "0", "0", "0"]);
  const kpis = await projectInformation.locator(".project-information-stats > div").evaluateAll(nodes => nodes.map(node => { const r = node.getBoundingClientRect(); return {top:r.top,right:r.right}; }));
  expect(Math.max(...kpis.map(r=>r.top))-Math.min(...kpis.map(r=>r.top))).toBeLessThanOrEqual(1);
  expect(Math.max(...kpis.map(r=>r.right))).toBeLessThanOrEqual(page.viewportSize().width);

  await expect(projectInformation.getByRole("button", { name: "New model" })).toHaveCount(0);
  await expect(page.locator(".project-selection-toolbar").getByRole("button", { name: "New model" })).toBeVisible();
  const informationLayout = await projectInformation.evaluate((element) => {
    const heading = element.querySelector("h1");
    const rect = element.getBoundingClientRect();
    const parentRect = element.parentElement.getBoundingClientRect();
    return {
      headingSize: Number.parseFloat(getComputedStyle(heading).fontSize),
      widthDelta: Math.abs(rect.width - parentRect.width),
    };
  });
  expect(informationLayout.headingSize).toBeGreaterThanOrEqual(24);
  expect(informationLayout.widthDelta).toBeLessThanOrEqual(2);
  const modelCard = page.locator(".project-model-card");
  await expect(modelCard.getByRole("heading", {name:"Baseline planning case"})).toBeVisible();
  await expect(modelCard.locator(".project-model-card-head")).toContainText("draft");
  await expect(modelCard.getByRole("button", {name:"Open model", exact:true})).toBeVisible();

  await page.getByRole("button", { name: "Back to projects" }).click();
  await expect(projectVisual).toHaveAttribute("data-identity-revision", projectRevision);
  await expect(projectVisual).toHaveJSProperty("innerHTML", projectMarkup);
});

test("model setup prioritizes essential choices", async ({ page }, testInfo) => {
  await openProjects(page);
  await page.getByRole("button", { name: "Open project", exact: true }).click();
  await page.getByRole("button", { name: "Open model", exact: true }).click();

  await page.locator(".model-flow-disclosure > summary").click();
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
  await expect(inputModule.locator("select").first()).toBeVisible();
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

  await page.locator(".model-flow-disclosure > summary").click();
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
