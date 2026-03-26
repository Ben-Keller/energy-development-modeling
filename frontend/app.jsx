const { useEffect, useMemo, useState } = React;

const API_BASE = String(window.EDIM_API_BASE || "").trim().replace(/\/+$/, "");
const ACTIVE_STATUSES = new Set(["queued", "running"]);
const TERMINAL_JOB_STATUSES = new Set(["succeeded", "failed", "cancelled"]);

const DEFAULT_LEVERS = {
  demand_multiplier: 1.0,
  renewables_capex_multiplier: 1.0,
  fossil_fuel_price_multiplier: 1.0,
  carbon_price_usd_per_tco2: 0.0,
};

const DEVELOPMENT_METRIC_LABELS = {
  gva_total_musd: "Gross value added (MUSD)",
  jobs_total: "Jobs",
  household_income_proxy_musd: "Household income proxy (MUSD)",
};

const STATUS_THEME = {
  queued: { label: "Queued", className: "badge badge-queued" },
  running: { label: "Running", className: "badge badge-running" },
  succeeded: { label: "Succeeded", className: "badge badge-succeeded" },
  failed: { label: "Failed", className: "badge badge-failed" },
  cancelled: { label: "Cancelled", className: "badge badge-cancelled" },
  ok: { label: "OK", className: "badge badge-succeeded" },
  warn: { label: "Warn", className: "badge badge-warning" },
  error: { label: "Error", className: "badge badge-failed" },
};

function normalizeStatus(status) {
  return String(status || "").trim().toLowerCase();
}

function isActiveStatus(status) {
  return ACTIVE_STATUSES.has(normalizeStatus(status));
}

function isTerminalStatus(status) {
  return TERMINAL_JOB_STATUSES.has(normalizeStatus(status));
}

function displayStatus(status) {
  const key = normalizeStatus(status);
  return STATUS_THEME[key] || { label: status || "Unknown", className: "badge badge-neutral" };
}

function toNumber(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function toTimestampMs(value) {
  if (!value) return null;
  const ms = Date.parse(String(value));
  return Number.isFinite(ms) ? ms : null;
}

function formatElapsed(totalSeconds) {
  const sec = Math.max(0, Math.floor(toNumber(totalSeconds)));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m ${String(s).padStart(2, "0")}s`;
  return `${m}m ${String(s).padStart(2, "0")}s`;
}

function compact(value) {
  const n = toNumber(value);
  const abs = Math.abs(n);
  if (abs >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(2)}B`;
  if (abs >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `${(n / 1_000).toFixed(2)}K`;
  return n.toFixed(2);
}

const SCENARIO_PATHWAY_ORDER = ["STEPS", "AC"];
const SCENARIO_ASSET_ORDER = ["legacy", "new"];
const SCENARIO_PACKAGE_ORDER = ["legacy_legacy", "new_legacy", "legacy_new", "new_new"];
const SCENARIO_PACKAGE_LABELS = {
  legacy_legacy: "Legacy generation + legacy links",
  new_legacy: "New generation + legacy links",
  legacy_new: "Legacy generation + new links",
  new_new: "New generation + new links",
};

function scenarioTuple(pathway, generation, transmission, policy) {
  return `${String(pathway)}|${String(generation)}|${String(transmission)}|${policy ? "1" : "0"}`;
}

function scenarioPackage(generation, transmission) {
  return `${String(generation)}_${String(transmission)}`;
}

function parseScenarioDimensions(key) {
  const normalized = String(key || "").trim();
  if (!normalized) return null;
  if (normalized === "new_links") {
    return {
      family: "transmission_only",
      pathway: "",
      generation: "",
      transmission: "",
      policy: false,
    };
  }
  const match = normalized.match(/^2040_(STEPS|AC)(.*)$/i);
  if (!match) return null;
  const pathway = String(match[1]).toUpperCase();
  const suffix = String(match[2] || "");
  return {
    family: "pathway_2040",
    pathway,
    generation: /_old_gen/i.test(suffix) ? "legacy" : "new",
    transmission: /_old_links/i.test(suffix) ? "legacy" : "new",
    policy: /_policy$/i.test(suffix),
  };
}

function sortWithOrder(values, order) {
  return Array.from(new Set(values || [])).sort((a, b) => {
    const ai = order.indexOf(a);
    const bi = order.indexOf(b);
    if (ai >= 0 && bi >= 0) return ai - bi;
    if (ai >= 0) return -1;
    if (bi >= 0) return 1;
    return String(a).localeCompare(String(b));
  });
}

function buildScenarioSelectorModel(scenarios) {
  const rows = Array.isArray(scenarios) ? scenarios : [];
  const hasTransmissionOnly = rows.some((s) => String(s && s.key) === "new_links");
  const pathwayRows = [];
  const tupleToScenario = new Map();

  rows.forEach((scenario) => {
    const key = String((scenario && scenario.key) || "").trim();
    const dims = parseScenarioDimensions(key);
    if (!dims || dims.family !== "pathway_2040") return;
    pathwayRows.push({ key, dims });
    tupleToScenario.set(
      scenarioTuple(dims.pathway, dims.generation, dims.transmission, dims.policy),
      key
    );
  });

  const pathways = sortWithOrder(
    pathwayRows.map((row) => row.dims.pathway),
    SCENARIO_PATHWAY_ORDER
  );
  const generationOptions = sortWithOrder(
    pathwayRows.map((row) => row.dims.generation),
    SCENARIO_ASSET_ORDER
  );
  const transmissionOptions = sortWithOrder(
    pathwayRows.map((row) => row.dims.transmission),
    SCENARIO_ASSET_ORDER
  );

  return {
    hasTransmissionOnly,
    hasPathway2040: pathwayRows.length > 0,
    pathways,
    generationOptions,
    transmissionOptions,
    pathwayRows,
    tupleToScenario,
    firstScenarioKey: String((rows[0] && rows[0].key) || ""),
    firstPathwayScenarioKey: String((pathwayRows[0] && pathwayRows[0].key) || ""),
  };
}

function availablePackagesForPathway(selectorModel, pathway) {
  if (!selectorModel) return [];
  const rows = Array.isArray(selectorModel.pathwayRows) ? selectorModel.pathwayRows : [];
  const matches = rows.filter((row) => row && row.dims && row.dims.pathway === pathway);
  const values = matches.map((row) => scenarioPackage(row.dims.generation, row.dims.transmission));
  return sortWithOrder(values, SCENARIO_PACKAGE_ORDER);
}

function deriveScenarioSelections(scenarioKey, selectorModel) {
  const defaults = {
    family: selectorModel.hasPathway2040
      ? "pathway_2040"
      : selectorModel.hasTransmissionOnly
        ? "transmission_only"
        : "direct",
    pathway: selectorModel.pathways[0] || "STEPS",
    generation: selectorModel.generationOptions[0] || "legacy",
    transmission: selectorModel.transmissionOptions[0] || "legacy",
    policy: false,
  };
  const parsed = parseScenarioDimensions(scenarioKey);
  if (!parsed) return defaults;
  if (parsed.family === "transmission_only") {
    return { ...defaults, family: "transmission_only", policy: false };
  }
  return {
    family: "pathway_2040",
    pathway: parsed.pathway || defaults.pathway,
    generation: parsed.generation || defaults.generation,
    transmission: parsed.transmission || defaults.transmission,
    policy: Boolean(parsed.policy),
  };
}

function resolveScenarioKey(selectorModel, selections) {
  if (!selectorModel) return "";
  if (selections.family === "transmission_only" && selectorModel.hasTransmissionOnly) {
    return "new_links";
  }
  if (!selectorModel.hasPathway2040) {
    return selectorModel.hasTransmissionOnly ? "new_links" : selectorModel.firstScenarioKey;
  }
  const pathway = selections.pathway || selectorModel.pathways[0];
  const generation = selections.generation || selectorModel.generationOptions[0];
  const transmission = selections.transmission || selectorModel.transmissionOptions[0];
  const requestedPolicy = Boolean(selections.policy);

  const tryTuples = [
    scenarioTuple(pathway, generation, transmission, requestedPolicy),
    scenarioTuple(pathway, generation, transmission, false),
  ];

  selectorModel.generationOptions.forEach((gen) => {
    selectorModel.transmissionOptions.forEach((trn) => {
      tryTuples.push(scenarioTuple(pathway, gen, trn, false));
      tryTuples.push(scenarioTuple(pathway, gen, trn, true));
    });
  });
  selectorModel.pathways.forEach((path) => {
    selectorModel.generationOptions.forEach((gen) => {
      selectorModel.transmissionOptions.forEach((trn) => {
        tryTuples.push(scenarioTuple(path, gen, trn, false));
        tryTuples.push(scenarioTuple(path, gen, trn, true));
      });
    });
  });

  for (const key of tryTuples) {
    if (selectorModel.tupleToScenario.has(key)) {
      return selectorModel.tupleToScenario.get(key);
    }
  }
  return selectorModel.firstPathwayScenarioKey || selectorModel.firstScenarioKey || "";
}

function toErrorMessage(err, fallback) {
  if (err && typeof err.message === "string" && err.message.trim()) {
    return err.message;
  }
  return fallback;
}

function toApiUrl(pathOrUrl) {
  if (!pathOrUrl) return API_BASE || "";
  if (/^https?:\/\//i.test(pathOrUrl)) return pathOrUrl;
  return `${API_BASE}${pathOrUrl}`;
}

async function parseApiError(res, fallback) {
  const text = await res.text();
  try {
    const parsed = JSON.parse(text);
    if (parsed && typeof parsed.detail === "string" && parsed.detail.trim()) {
      return `${fallback}: ${parsed.detail}`;
    }
  } catch (_) {
    // Non-JSON response.
  }
  if (text.trim()) return `${fallback}: ${text}`;
  return `${fallback}: HTTP ${res.status}`;
}

async function apiGet(path, fallback) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(await parseApiError(res, fallback));
  return res.json();
}

async function apiPost(path, body, fallback) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body == null ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await parseApiError(res, fallback));
  return res.json();
}

const api = {
  fetchScenarios: async () => (await apiGet("/api/scenarios", "Failed to load scenarios")).scenarios || [],
  fetchEnvironmentSetup: async (scenario, runProfile) => {
    const qs = new URLSearchParams();
    if (scenario) qs.set("scenario", scenario);
    if (runProfile) qs.set("run_profile", runProfile);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return apiGet(`/api/environment-setup${suffix}`, "Failed to run environment setup checks");
  },
  fetchJobs: async (limit) => (await apiGet(`/api/jobs?limit=${limit || 30}`, "Failed to load jobs")).jobs || [],
  fetchJob: async (jobId) => apiGet(`/api/jobs/${encodeURIComponent(jobId)}`, "Failed to load job"),
  submitJob: async (req) => (await apiPost("/api/jobs", req, "Failed to submit job")).job,
  cancelJob: async (jobId) => apiPost(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, null, "Failed to cancel job"),
  fetchIntegrated: async (runId) =>
    apiGet(`/api/run/${encodeURIComponent(runId)}/integrated`, "Failed to load integrated results"),
};

function MetricCard({ label, value }) {
  return (
    <div className="metric-card">
      <div className="muted" style={{ fontSize: 11 }}>{label}</div>
      <div style={{ marginTop: 4, fontWeight: 700 }}>{value}</div>
    </div>
  );
}

function StatusBadge({ status }) {
  const meta = displayStatus(status);
  return <span className={meta.className}>{meta.label}</span>;
}

function LeverControl({ label, value, min, max, step, onChange }) {
  const clamp = (v) => Math.min(max, Math.max(min, v));
  const apply = (raw) => {
    const parsed = Number.parseFloat(raw);
    if (!Number.isFinite(parsed)) return;
    onChange(clamp(parsed));
  };
  return (
    <div style={{ marginBottom: 10 }}>
      <label>{label}</label>
      <div className="row" style={{ marginTop: 6 }}>
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => apply(e.target.value)}
          style={{ flex: 1, minWidth: 220 }}
        />
        <input
          type="number"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => apply(e.target.value)}
          style={{ width: 110 }}
        />
      </div>
    </div>
  );
}

function ProgressBar({ progress, height = 8 }) {
  const pct = Math.max(2, Math.round(toNumber(progress) * 100));
  return (
    <div style={{ marginTop: 8, background: "#0f1524", borderRadius: 10, overflow: "hidden" }}>
      <div
        style={{
          width: `${pct}%`,
          height,
          background: "#4f87ff",
          transition: "width 240ms ease",
        }}
      />
    </div>
  );
}

function pathwayLabel(pathway) {
  const normalized = String(pathway || "").toUpperCase();
  if (normalized === "AC") return "Announced Commitments (AC)";
  if (normalized === "STEPS") return "STEPS";
  return normalized || "-";
}

function ModelStructurePanel() {
  return (
    <div className="card" style={{ marginTop: 14 }}>
      <h3 style={{ marginTop: 0, fontSize: 16 }}>Model structure and data flow</h3>
      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 13 }}>1) Scenario to Calliope energy model</div>
          <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            The scenario selector controls model family and assumptions. The backend resolves that into one Calliope
            scenario key from <code>overrides.yaml</code>, then applies runtime solver/time/levers patching.
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            Runtime patch includes solver selection, run profile time subset, and lever mappings from{" "}
            <code>inputs/lever_mappings.csv</code>.
          </div>
          <div style={{ overflowX: "auto", marginTop: 8 }}>
            <table className="panel-table">
              <thead>
                <tr>
                  <th>Selector input type</th>
                  <th>High-level meaning</th>
                  <th>Calliope input effect</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Main scenario type</td>
                  <td>Chooses a model family (2040 pathways vs transmission-only)</td>
                  <td>Selects a scenario namespace in <code>overrides.yaml</code></td>
                </tr>
                <tr>
                  <td>Demand pathway</td>
                  <td>Higher-level demand trajectory assumption (STEPS or AC)</td>
                  <td>Switches demand assumptions embedded in scenario overrides</td>
                </tr>
                <tr>
                  <td>Energy build package</td>
                  <td>Whether generation and transmission expansion options are enabled</td>
                  <td>Switches generation/link build options used in the optimization</td>
                </tr>
                <tr>
                  <td>Policy package</td>
                  <td>Standard vs policy-constrained/policy-push variant</td>
                  <td>Adds/removes policy constraint settings in the selected scenario</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div style={{ fontWeight: 700, fontSize: 13 }}>2) Calliope outputs to MARIO exchange inputs</div>
          <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            Cost variables and reliability diagnostics are converted into exchange CSV files in{" "}
            <code>outputs/runs/&lt;run_id&gt;/exchange</code>.
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            Mapping uses <code>inputs/mario_inputs/calliope_tech_to_mario_sector.csv</code>,{" "}
            <code>capex_sector_split.csv</code>, <code>opex_sector_split.csv</code>, and{" "}
            <code>country_to_pool.csv</code>.
          </div>
          <div style={{ overflowX: "auto", marginTop: 8 }}>
            <table className="panel-table">
              <thead>
                <tr>
                  <th>Calliope source</th>
                  <th>Exchange file</th>
                  <th>MARIO runtime use</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><code>cost_investment</code></td>
                  <td><code>investment_shocks.csv</code></td>
                  <td>CAPEX shock rows by region, technology, and MARIO sector</td>
                </tr>
                <tr>
                  <td><code>cost_om_annual</code>, <code>cost_om_prod</code>, <code>cost_om_con</code></td>
                  <td><code>operating_shocks.csv</code></td>
                  <td>OPEX/fuel shock rows by region, technology, and MARIO sector</td>
                </tr>
                <tr>
                  <td>Pool demand, unserved energy, and net trade diagnostics</td>
                  <td><code>energy_service_balance.csv</code></td>
                  <td>Energy service context and validation trace for coupled outputs</td>
                </tr>
                <tr>
                  <td>Selected lever values</td>
                  <td><code>prices_and_taxes.csv</code></td>
                  <td>Policy/price context for the scenario run metadata</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div style={{ fontWeight: 700, fontSize: 13 }}>3) Final integrated results</div>
          <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            MARIO runtime combines exchange shocks with <code>employment_intensity.csv</code> and{" "}
            <code>value_added_intensity.csv</code> to produce development impacts.
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            The backend then assembles energy + development metrics into one integrated payload with confidence and
            baseline comparison.
          </div>
          <div style={{ overflowX: "auto", marginTop: 8 }}>
            <table className="panel-table">
              <thead>
                <tr>
                  <th>Output artifact</th>
                  <th>What it contains</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><code>results.csv</code></td>
                  <td>Full flattened Calliope results variables and dimensions</td>
                </tr>
                <tr>
                  <td><code>summary.json</code></td>
                  <td>Energy summary, diagnostics, warnings, and artifact links</td>
                </tr>
                <tr>
                  <td><code>development_impacts.json</code></td>
                  <td>Jobs, GVA, household income totals with regional and sector splits</td>
                </tr>
                <tr>
                  <td><code>integrated_results.json</code></td>
                  <td>System cost, emissions, reliability, jobs, GVA, import leakage, confidence, and baseline deltas</td>
                </tr>
                <tr>
                  <td><code>exchange_bundle.zip</code></td>
                  <td>Packaged exchange CSVs + integrated JSONs for downstream review/share</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

function RankedBars({
  records,
  labelKey,
  valueKey,
  limit = 12,
  filterText = "",
  emptyMessage = "No records for this run.",
}) {
  const rows = useMemo(() => {
    const filter = String(filterText || "").trim().toLowerCase();
    return (records || [])
      .map((r) => ({
        label: String(r && r[labelKey] != null ? r[labelKey] : ""),
        value: toNumber(r && r[valueKey]),
      }))
      .filter((r) => r.label)
      .filter((r) => (!filter ? true : r.label.toLowerCase().includes(filter)))
      .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
      .slice(0, limit);
  }, [records, labelKey, valueKey, limit, filterText]);

  if (!rows.length) {
    return <div className="muted">{emptyMessage}</div>;
  }

  const maxAbs = Math.max(...rows.map((r) => Math.abs(r.value)), 1);

  return (
    <div className="hbar-wrap">
      {rows.map((row, idx) => {
        const share = Math.max(0.02, Math.abs(row.value) / maxAbs);
        return (
          <div className="hbar-row" key={`${row.label}-${idx}`}>
            <div title={row.label} style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {row.label}
            </div>
            <div className="hbar-track">
              <div
                className={`hbar-fill ${row.value < 0 ? "negative" : ""}`}
                style={{ width: `${Math.round(share * 100)}%` }}
              />
            </div>
            <div style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{compact(row.value)}</div>
          </div>
        );
      })}
    </div>
  );
}

function ScenarioSetupPanel({
  scenarios,
  scenarioKey,
  selectorModel,
  scenarioSelections,
  selectedScenario,
  levers,
  runProfile,
  running,
  queueSubmitting,
  onScenarioChange,
  onScenarioSelectionChange,
  onSetLevers,
  onSetRunProfile,
  onApplyTemplateLevers,
  onRun,
  onResetLevers,
}) {
  const showStructuredSelector = Boolean(
    selectorModel && (selectorModel.hasTransmissionOnly || selectorModel.hasPathway2040)
  );
  const packageOptions = availablePackagesForPathway(selectorModel, scenarioSelections.pathway);
  const selectedPackage = scenarioPackage(
    scenarioSelections.generation,
    scenarioSelections.transmission
  );
  const activePackage = packageOptions.includes(selectedPackage)
    ? selectedPackage
    : packageOptions[0] || "legacy_legacy";
  const [activeGeneration, activeTransmission] = String(activePackage).split("_");
  const policyAvailable = Boolean(
    showStructuredSelector &&
      scenarioSelections &&
      scenarioSelections.family === "pathway_2040" &&
      selectorModel.tupleToScenario.has(
        scenarioTuple(
          scenarioSelections.pathway,
          activeGeneration,
          activeTransmission,
          true
        )
      )
  );

  return (
    <div className="grid" style={{ gridTemplateColumns: "1.2fr 0.8fr", marginTop: 14 }}>
      <div className="card">
        <div className="row">
          <div style={{ flex: 1, minWidth: 320 }}>
            <label>Scenario setup</label>
            {showStructuredSelector ? (
              <div style={{ marginTop: 8 }}>
                <div
                  style={{
                    border: "1px solid #2a3a58",
                    borderRadius: 10,
                    padding: "10px 10px 12px",
                    background: "#0d182c",
                  }}
                >
                  <div style={{ fontWeight: 700, fontSize: 13 }}>Step 1: Main model selector</div>
                  <div className="muted" style={{ marginTop: 4, fontSize: 12 }}>
                    Choose the model family first, then configure the details below.
                  </div>
                  <div style={{ marginTop: 8 }}>
                    <label>Main scenario type</label>
                    <select
                      value={scenarioSelections.family}
                      onChange={(e) => onScenarioSelectionChange({ family: e.target.value })}
                      style={{ width: "100%" }}
                    >
                      {selectorModel.hasPathway2040 ? (
                        <option value="pathway_2040">2040 pathway scenarios</option>
                      ) : null}
                      {selectorModel.hasTransmissionOnly ? (
                        <option value="transmission_only">Transmission-only scenario</option>
                      ) : null}
                    </select>
                  </div>
                </div>

                {scenarioSelections.family === "pathway_2040" ? (
                  <div
                    style={{
                      marginTop: 10,
                      border: "1px solid #22324f",
                      borderRadius: 10,
                      padding: "10px 10px 12px",
                      background: "#0b1424",
                    }}
                  >
                    <div style={{ fontWeight: 700, fontSize: 13 }}>Step 2: Additional scenario details</div>
                    <div className="muted" style={{ marginTop: 4, fontSize: 12 }}>
                      These settings refine demand, build-out assumptions, and optional policy constraints.
                    </div>
                    <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", marginTop: 8 }}>
                      <div>
                        <label>Demand pathway</label>
                        <select
                          value={scenarioSelections.pathway}
                          onChange={(e) => onScenarioSelectionChange({ pathway: e.target.value })}
                          style={{ width: "100%" }}
                        >
                          {selectorModel.pathways.map((path) => (
                            <option key={path} value={path}>
                              {pathwayLabel(path)}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label>Energy build package</label>
                        <select
                          value={activePackage}
                          onChange={(e) => {
                            const code = String(e.target.value || "");
                            const parts = code.split("_");
                            const generation = parts[0] || "legacy";
                            const transmission = parts[1] || "legacy";
                            onScenarioSelectionChange({ generation, transmission });
                          }}
                          style={{ width: "100%" }}
                        >
                          {packageOptions.map((code) => (
                            <option key={code} value={code}>
                              {SCENARIO_PACKAGE_LABELS[code] || code}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label>Policy package</label>
                        <select
                          value={scenarioSelections.policy ? "on" : "off"}
                          onChange={(e) => onScenarioSelectionChange({ policy: e.target.value === "on" })}
                          style={{ width: "100%" }}
                          disabled={!policyAvailable}
                        >
                          <option value="off">Standard</option>
                          {policyAvailable ? <option value="on">Policy push</option> : null}
                        </select>
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>
            ) : (
              <div style={{ marginTop: 6 }}>
                <select value={scenarioKey} onChange={(e) => onScenarioChange(e.target.value)} style={{ width: "100%" }}>
                  {(scenarios || []).map((s) => (
                    <option key={s.key} value={s.key}>
                      {s.title}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {showStructuredSelector && scenarioSelections.family === "pathway_2040" ? (
              <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
                Pathway sets demand trajectory; build package sets generation/transmission expansion; policy adds
                optional constraints and incentives when available.
              </div>
            ) : null}
            <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
              Resolved scenario key: <code>{scenarioKey || "-"}</code>
            </div>
            {selectedScenario && selectedScenario.description ? (
              <div className="muted" style={{ marginTop: 8, fontSize: 13 }}>
                {selectedScenario.description}
              </div>
            ) : null}
            {selectedScenario && selectedScenario.policy_question ? (
              <div style={{ marginTop: 8, fontSize: 13 }}>
                <b>Policy question:</b> {selectedScenario.policy_question}
              </div>
            ) : null}
            {selectedScenario && selectedScenario.expected_tradeoff ? (
              <div className="muted" style={{ marginTop: 6, fontSize: 12 }}>
                Expected tradeoff: {selectedScenario.expected_tradeoff}
              </div>
            ) : null}
            {selectedScenario && selectedScenario.tags && selectedScenario.tags.length ? (
              <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
                Tags: {selectedScenario.tags.join(", ")}
              </div>
            ) : null}
            {selectedScenario && selectedScenario.preset_levers && Object.keys(selectedScenario.preset_levers).length ? (
              <div className="row" style={{ marginTop: 10 }}>
                <button
                  type="button"
                  style={{ background: "#2b557f", padding: "7px 10px", fontSize: 12 }}
                  onClick={onApplyTemplateLevers}
                >
                  Apply template levers
                </button>
                {selectedScenario.user_label ? (
                  <span className="muted" style={{ fontSize: 12 }}>
                    Template: {selectedScenario.user_label}
                  </span>
                ) : null}
              </div>
            ) : null}
          </div>
          <div style={{ minWidth: 220 }}>
            <label>Run mode</label>
            <div className="row" style={{ marginTop: 6 }}>
              <select value={runProfile} onChange={(e) => onSetRunProfile(e.target.value)}>
                <option value="dev">Dev profile (short subset)</option>
                <option value="analysis">Analysis profile (extended subset)</option>
                <option value="full">Full profile (no subset)</option>
              </select>
            </div>
          </div>
        </div>
      </div>
      <div className="card">
        <h2 style={{ marginTop: 0, fontSize: 16 }}>Policy levers</h2>
        <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
          Start with defaults, then change only what you need.
        </div>
        <LeverControl
          label="Renewables CAPEX multiplier"
          value={levers.renewables_capex_multiplier}
          min={0.7}
          max={1.5}
          step={0.05}
          onChange={(v) => onSetLevers({ ...levers, renewables_capex_multiplier: v })}
        />
        <LeverControl
          label="Fossil variable cost multiplier"
          value={levers.fossil_fuel_price_multiplier}
          min={0.7}
          max={1.8}
          step={0.05}
          onChange={(v) => onSetLevers({ ...levers, fossil_fuel_price_multiplier: v })}
        />
        <LeverControl
          label="Carbon price (USD/tCO2)"
          value={levers.carbon_price_usd_per_tco2}
          min={0}
          max={300}
          step={10}
          onChange={(v) => onSetLevers({ ...levers, carbon_price_usd_per_tco2: v })}
        />
        <LeverControl
          label="Demand multiplier"
          value={levers.demand_multiplier}
          min={0.8}
          max={1.4}
          step={0.05}
          onChange={(v) => onSetLevers({ ...levers, demand_multiplier: v })}
        />
        <div className="row" style={{ marginTop: 12 }}>
          <button onClick={onRun} disabled={!scenarioKey || queueSubmitting}>
            {queueSubmitting ? "Queuing..." : running ? "Queue another run" : "Queue run"}
          </button>
          <button onClick={onResetLevers} disabled={queueSubmitting} style={{ background: "#22304c" }}>
            Reset levers
          </button>
        </div>
      </div>
    </div>
  );
}

function ActiveJobPanel({ activeJob, onCancel }) {
  const [clockMs, setClockMs] = useState(() => Date.now());
  const [checkpointMs, setCheckpointMs] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setClockMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const checkpointSignature = activeJob
    ? `${activeJob.job_id}|${activeJob.stage}|${Math.round(toNumber(activeJob.progress) * 1000)}|${activeJob.message}`
    : "";

  useEffect(() => {
    setCheckpointMs(Date.now());
  }, [checkpointSignature]);

  if (!activeJob) return null;
  const status = normalizeStatus(activeJob.status);
  const canCancel = status === "queued" || status === "running";

  const startedAtMs = toTimestampMs(activeJob.started_at);
  const updatedAtMs = toTimestampMs(activeJob.updated_at);
  const elapsedSeconds = startedAtMs ? Math.max(0, (clockMs - startedAtMs) / 1000) : 0;
  const elapsedLabel = startedAtMs ? formatElapsed(elapsedSeconds) : "-";
  const checkpointBaseMs = updatedAtMs || checkpointMs;
  const checkpointAgeSeconds = Math.max(0, (clockMs - checkpointBaseMs) / 1000);
  const checkpointAgeLabel = formatElapsed(checkpointAgeSeconds);
  const stageKey = String(activeJob.stage || "").trim().toLowerCase();

  const stageHint = (() => {
    if (status !== "running") return "";
    if (stageKey === "solve_energy") {
      if (elapsedSeconds >= 1200) {
        return "Solver is still running. Large cases can take 20+ minutes in dev mode.";
      }
      if (elapsedSeconds >= 600) {
        return "Solver is still running. This stage often takes the longest.";
      }
      return "Solver is optimizing the energy system now.";
    }
    if (stageKey === "build_model") return "Preparing optimization model structures.";
    if (stageKey === "write_artifacts") return "Solve finished; writing CSV artifacts.";
    if (stageKey === "build_summary") return "Compiling summary diagnostics.";
    if (stageKey === "development") return "Converting energy outputs into development effects.";
    if (stageKey === "build_integrated") return "Assembling final integrated results.";
    return "";
  })();

  return (
    <div className="card" style={{ marginTop: 14 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <b>Active job:</b> <code>{activeJob.job_id}</code> <StatusBadge status={activeJob.status} />
          {activeJob.queue_position ? <span className="muted"> - queue position {activeJob.queue_position}</span> : null}
        </div>
        <div className="row">
          <div className="muted">{activeJob.stage}</div>
          <button
            type="button"
            style={{ background: "#6f3d3d", padding: "6px 10px", fontSize: 12 }}
            onClick={onCancel}
            disabled={!canCancel}
          >
            Cancel job
          </button>
        </div>
      </div>
      <ProgressBar progress={activeJob.progress} height={10} />
      <div className="row muted" style={{ marginTop: 8, fontSize: 12 }}>
        <span>Stage: <code>{activeJob.stage || "-"}</code></span>
        <span>Elapsed: <code>{elapsedLabel}</code></span>
        <span>Last backend checkpoint: <code>{checkpointAgeLabel} ago</code></span>
        {activeJob.worker_pid ? <span>Worker PID: <code>{activeJob.worker_pid}</code></span> : null}
      </div>
      {stageHint ? (
        <div className="muted" style={{ marginTop: 6, fontSize: 12 }}>
          {stageHint}
        </div>
      ) : null}
      {status === "running" && checkpointAgeSeconds >= 900 ? (
        <div className="warn" style={{ marginTop: 8, marginBottom: 0, fontSize: 12 }}>
          No backend checkpoint update for 15+ minutes. Solver may still be working, but this can also indicate a
          stalled solve.
        </div>
      ) : null}
      <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
        {activeJob.message || "Running"}
      </div>
    </div>
  );
}

function SelectedJobDetailsPanel({ job }) {
  if (!job) return null;
  const isActive = isActiveStatus(job.status);
  const summary = job.summary || null;
  const exchangeArtifacts = (summary && summary.exchange_artifacts) || {};
  const hasOutputs = Boolean(job.artifacts && (job.artifacts.csv_url || job.artifacts.summary_url));

  return (
    <div className="card" style={{ marginTop: 14 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <b>Selected job:</b> <code>{job.job_id}</code> <StatusBadge status={job.status} />
        </div>
        <div className="muted" style={{ fontSize: 12 }}>
          {job.created_at ? new Date(job.created_at).toLocaleString() : "-"}
        </div>
      </div>

      <div className="row muted" style={{ marginTop: 8, fontSize: 12 }}>
        <span>Scenario: <code>{(job.request && job.request.scenario) || "-"}</code></span>
        <span>Run profile: <code>{(job.request && job.request.run_profile) || "-"}</code></span>
        <span>Progress: <code>{Math.round(toNumber(job.progress) * 100)}%</code></span>
        {job.queue_position != null ? <span>Queue position: <code>{job.queue_position}</code></span> : null}
        {job.worker_pid ? <span>Worker PID: <code>{job.worker_pid}</code></span> : null}
      </div>

      {isActive ? <ProgressBar progress={job.progress} height={8} /> : null}

      <div className="row muted" style={{ marginTop: 8, fontSize: 12 }}>
        <span>Started: <code>{job.started_at ? new Date(job.started_at).toLocaleString() : "-"}</code></span>
        <span>Updated: <code>{job.updated_at ? new Date(job.updated_at).toLocaleString() : "-"}</code></span>
        <span>Finished: <code>{job.finished_at ? new Date(job.finished_at).toLocaleString() : "-"}</code></span>
      </div>

      <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
        Stage: <code>{job.stage || "-"}</code>
      </div>
      <div className="muted" style={{ marginTop: 6, fontSize: 12 }}>
        Message: {job.message || "-"}
      </div>
      {job.error ? (
        <div style={{ marginTop: 8, fontSize: 12, color: "#ffc8c8" }}>
          Error: {job.error}
        </div>
      ) : null}

      {hasOutputs ? (
        <div className="row" style={{ marginTop: 10 }}>
          {job.artifacts && job.artifacts.csv_url ? (
            <a href={toApiUrl(job.artifacts.csv_url)} target="_blank" rel="noreferrer">Results CSV</a>
          ) : null}
          {job.artifacts && job.artifacts.summary_url ? (
            <a href={toApiUrl(job.artifacts.summary_url)} target="_blank" rel="noreferrer">Summary JSON</a>
          ) : null}
          {exchangeArtifacts.report_markdown ? (
            <a href={toApiUrl(exchangeArtifacts.report_markdown)} target="_blank" rel="noreferrer">Run report</a>
          ) : null}
          {exchangeArtifacts.exchange_bundle_zip ? (
            <a href={toApiUrl(exchangeArtifacts.exchange_bundle_zip)} target="_blank" rel="noreferrer">Exchange bundle ZIP</a>
          ) : null}
        </div>
      ) : (
        <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
          Outputs will appear here when this job reaches <code>succeeded</code>.
        </div>
      )}
    </div>
  );
}

function WorkflowStatusPanel({ hasScenario, environmentSetupOk, running, hasResult }) {
  const steps = [
    { key: "setup", label: "1. Setup", done: hasScenario },
    { key: "queue", label: "2. Queue", done: environmentSetupOk || running || hasResult },
    { key: "monitor", label: "3. Monitor", done: hasResult, active: running },
    { key: "review", label: "4. Review", done: hasResult },
  ];
  return (
    <div className="card" style={{ marginTop: 14 }}>
      <h3 style={{ marginTop: 0, fontSize: 16 }}>Workflow</h3>
      <div className="row">
        {steps.map((step) => {
          const bg = step.done ? "#1a3b2e" : step.active ? "#1b2d4a" : "#131b2d";
          const border = step.done ? "#2d6651" : step.active ? "#335b97" : "#293851";
          const color = step.done ? "#bff4dd" : step.active ? "#bcd9ff" : "#a9bad0";
          return (
            <div
              key={step.key}
              style={{
                border: `1px solid ${border}`,
                background: bg,
                color,
                borderRadius: 10,
                padding: "6px 10px",
                fontSize: 12,
                fontWeight: 600,
              }}
            >
              {step.label}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function EnvironmentSetupPanel({ environmentSetup, loading, onRefresh }) {
  if (!environmentSetup && !loading) return null;

  const checks = Array.isArray(environmentSetup && environmentSetup.checks) ? environmentSetup.checks : [];
  const statusLabel = loading ? "Checking..." : environmentSetup && environmentSetup.ok ? "Ready to queue" : "Action needed";
  const statusStyle = loading
    ? { border: "1px solid #33466a", background: "#0d1a30", color: "#bfd4f5" }
    : environmentSetup && environmentSetup.ok
      ? { border: "1px solid #2f5d49", background: "#10251d", color: "#bdf3d9" }
      : { border: "1px solid #6f4d2c", background: "#2b2015", color: "#ffd7b0" };

  return (
    <div className="card" style={{ marginTop: 14 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3 style={{ marginTop: 0, marginBottom: 0, fontSize: 16 }}>Environment setup</h3>
        <button type="button" onClick={onRefresh} style={{ background: "#22304c", fontSize: 12, padding: "6px 10px" }}>
          Refresh checks
        </button>
      </div>
      <div style={{ ...statusStyle, borderRadius: 10, padding: "8px 10px", marginTop: 8, fontSize: 13 }}>
        {statusLabel}
      </div>
      {environmentSetup && environmentSetup.queue ? (
        <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          Queue usage: {toNumber(environmentSetup.queue.active_jobs)} / {toNumber(environmentSetup.queue.capacity)}
        </div>
      ) : null}
      {checks.length ? (
        <div style={{ overflowX: "auto", marginTop: 8 }}>
          <table className="panel-table">
            <thead>
              <tr>
                <th>Check</th>
                <th>Status</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              {checks.map((row, idx) => (
                <tr key={`${row.name || "check"}-${idx}`}>
                  <td>{row.label || row.name || "-"}</td>
                  <td><StatusBadge status={row.status || "-"} /></td>
                  <td>{row.message || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

function RunResultsPanel({
  result,
  selectedRunLabel,
  runMetadata,
  exchangeArtifacts,
  integratedMetrics,
  developmentDrivers,
  confidence,
  baselineComparison,
  developmentUncertainty,
  reliability,
  tradeNetRecords,
  emissionsByPool,
  costByComponent,
  developmentByRegion,
  developmentBySector,
  developmentMetric,
  setDevelopmentMetric,
  developmentMetricLabel,
}) {
  const [activeSection, setActiveSection] = useState("overview");
  const [barFilter, setBarFilter] = useState("");
  const [barLimit, setBarLimit] = useState("20");

  if (!result) return null;

  const baselineStatus = String((baselineComparison && baselineComparison.status) || "").trim().toLowerCase();
  const baselineRows =
    baselineComparison &&
    baselineComparison.metrics &&
    Array.isArray(baselineComparison.metrics.records)
      ? baselineComparison.metrics.records
      : [];

  const improvedCount = baselineRows.filter((r) => r && r.improved_vs_baseline === true).length;
  const worsenedCount = baselineRows.filter((r) => r && r.improved_vs_baseline === false).length;
  const uncertaintyBounds =
    developmentUncertainty &&
    developmentUncertainty.totals_bounds &&
    typeof developmentUncertainty.totals_bounds === "object"
      ? developmentUncertainty.totals_bounds
      : null;
  const rankedLimit = Math.max(5, Math.round(toNumber(barLimit, 20)));
  const generationByTechRanked = aggregateByLabel(
    (((result.summary || {}).generation_by_tech || {}).records || []),
    "techs",
    "value"
  );
  const sectionTabs = [
    { key: "overview", label: "Overview" },
    { key: "system", label: "Energy system" },
    { key: "development", label: "Development" },
  ];

  return (
    <div style={{ marginTop: 14 }} className="grid">
      <div className="ok">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div>
            <b>{selectedRunLabel || "Selected run"}</b> - ID: <code>{result.artifacts.run_id}</code>
          </div>
          <div className="row">
            <a href={toApiUrl(result.artifacts.csv_url)} target="_blank" rel="noreferrer">Download Results CSV</a>
            {exchangeArtifacts.report_markdown ? (
              <a href={toApiUrl(exchangeArtifacts.report_markdown)} target="_blank" rel="noreferrer">Run report</a>
            ) : null}
            {exchangeArtifacts.exchange_bundle_zip ? (
              <a href={toApiUrl(exchangeArtifacts.exchange_bundle_zip)} target="_blank" rel="noreferrer">Exchange bundle ZIP</a>
            ) : null}
          </div>
        </div>
        <div className="row muted" style={{ marginTop: 8, fontSize: 12 }}>
          <span>Solver: {runMetadata.solver || "-"}</span>
          <span>Termination: {runMetadata.termination_condition || "-"}</span>
          <span>Solve time: {runMetadata.solution_time_seconds != null ? `${toNumber(runMetadata.solution_time_seconds).toFixed(2)} s` : "-"}</span>
          <span>Objective: {runMetadata.objective_function_value != null ? compact(runMetadata.objective_function_value) : "-"}</span>
        </div>
        {result.summary && result.summary.warnings && result.summary.warnings.length ? (
          <div style={{ marginTop: 10 }}>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>Warnings</div>
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {result.summary.warnings.map((w, i) => (
                <li key={i} style={{ marginBottom: 4 }}>{w}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>

      <div className="card">
        <div className="row" style={{ justifyContent: "space-between", gap: 12 }}>
          <div className="segmented-control">
            {sectionTabs.map((tab) => (
              <button
                key={tab.key}
                type="button"
                className={activeSection === tab.key ? "seg-button active" : "seg-button"}
                onClick={() => setActiveSection(tab.key)}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className="row" style={{ gap: 8 }}>
            <div>
              <label>Filter bars</label>
              <input
                type="text"
                value={barFilter}
                onChange={(e) => setBarFilter(e.target.value)}
                placeholder="Type to filter labels"
                style={{ width: 190 }}
              />
            </div>
            <div>
              <label>Top rows</label>
              <select value={barLimit} onChange={(e) => setBarLimit(e.target.value)}>
                <option value="10">Top 10</option>
                <option value="15">Top 15</option>
                <option value="20">Top 20</option>
                <option value="30">Top 30</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {activeSection === "overview" ? (
        <>
          <div className="grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <div className="card">
              <h3 style={{ marginTop: 0, fontSize: 15 }}>Integrated overview</h3>
              {integratedMetrics.length ? (
                <div className="row" style={{ gap: 12 }}>
                  {integratedMetrics.map((m) => (
                    <MetricCard
                      key={String(m.key)}
                      label={`${String(m.label)} (${String(m.unit)})`}
                      value={compact(toNumber(m.value))}
                    />
                  ))}
                </div>
              ) : (
                <div className="muted">Integrated metrics not available for this run.</div>
              )}
            </div>

            <div className="card">
              <h3 style={{ marginTop: 0, fontSize: 15 }}>Development drivers</h3>
              <div className="row" style={{ gap: 10 }}>
                <MetricCard label="CAPEX effect (MUSD)" value={compact(developmentDrivers.capex_effect_musd)} />
                <MetricCard label="OPEX effect (MUSD)" value={compact(developmentDrivers.opex_effect_musd)} />
                <MetricCard label="Reliability penalty" value={compact(developmentDrivers.reliability_penalty_proxy)} />
                <MetricCard label="Import leakage (MUSD)" value={compact(developmentDrivers.import_leakage_musd)} />
              </div>
              <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                Mode: <code>{String(confidence.coupling_mode || "unknown")}</code> | Mapping coverage:{" "}
                {(toNumber(confidence.mapping_coverage_share) * 100).toFixed(1)}%
              </div>
            </div>
          </div>

          <div className="grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <div className="card">
              <h3 style={{ marginTop: 0, fontSize: 15 }}>Baseline comparison</h3>
              {baselineStatus === "found" && baselineRows.length ? (
                <>
                  <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
                    Baseline scenario: <code>{baselineComparison.baseline_scenario || "-"}</code> | Baseline run:{" "}
                    <code>{baselineComparison.baseline_run_id || "-"}</code>
                  </div>
                  <div className="row" style={{ gap: 12, marginBottom: 8 }}>
                    <MetricCard label="Improved metrics" value={String(improvedCount)} />
                    <MetricCard label="Worsened metrics" value={String(worsenedCount)} />
                  </div>
                  <RankedBars
                    records={baselineRows}
                    labelKey="label"
                    valueKey="delta_value"
                    limit={rankedLimit}
                    filterText={barFilter}
                    emptyMessage="No baseline deltas were computed."
                  />
                  <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                    Positive/negative bars are deltas from baseline.
                  </div>
                </>
              ) : (
                <div className="muted">
                  {(baselineComparison && baselineComparison.message) || "Baseline comparison not available for this run."}
                </div>
              )}
            </div>

            <div className="card">
              <h3 style={{ marginTop: 0, fontSize: 15 }}>Development uncertainty</h3>
              {uncertaintyBounds ? (
                <div className="row" style={{ gap: 10 }}>
                  <MetricCard
                    label="Jobs total range"
                    value={`${compact(uncertaintyBounds.jobs_total_low)} to ${compact(uncertaintyBounds.jobs_total_high)}`}
                  />
                  <MetricCard
                    label="GVA range (MUSD)"
                    value={`${compact(uncertaintyBounds.gva_total_musd_low)} to ${compact(uncertaintyBounds.gva_total_musd_high)}`}
                  />
                  <MetricCard
                    label="Income range (MUSD)"
                    value={`${compact(uncertaintyBounds.household_income_proxy_musd_low)} to ${compact(uncertaintyBounds.household_income_proxy_musd_high)}`}
                  />
                  <MetricCard
                    label="Direct jobs range"
                    value={`${compact(uncertaintyBounds.jobs_direct_low)} to ${compact(uncertaintyBounds.jobs_direct_high)}`}
                  />
                </div>
              ) : (
                <div className="muted">Uncertainty bounds were not produced for this run.</div>
              )}
              {developmentUncertainty && developmentUncertainty.method ? (
                <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                  Method: <code>{String(developmentUncertainty.method)}</code>
                </div>
              ) : null}
            </div>
          </div>
        </>
      ) : null}

      {activeSection === "system" ? (
        <>
          <div className="grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <div className="card">
              <h3 style={{ marginTop: 0, fontSize: 15 }}>Generation by technology</h3>
              <RankedBars
                records={generationByTechRanked}
                labelKey="techs"
                valueKey="value"
                emptyMessage="No generation records for this run."
                limit={rankedLimit}
                filterText={barFilter}
              />
              <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                Values are aggregated across all model timesteps.
              </div>
            </div>
            <div className="card">
              <h3 style={{ marginTop: 0, fontSize: 15 }}>Capacity (energy_cap)</h3>
              <RankedBars
                records={(((result.summary || {}).capacity_by_tech || {}).records || [])}
                labelKey="techs"
                valueKey="value"
                emptyMessage="No capacity records for this run."
                limit={rankedLimit}
                filterText={barFilter}
              />
            </div>
          </div>

          <div className="grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <div className="card">
              <h3 style={{ marginTop: 0, fontSize: 15 }}>Reliability snapshot</h3>
              <div className="row" style={{ gap: 18 }}>
                <MetricCard label="Demand total" value={compact(reliability.demand_total)} />
                <MetricCard label="Unserved total" value={compact(reliability.unserved_total)} />
                <MetricCard label="Unserved share" value={`${(toNumber(reliability.unserved_energy_share) * 100).toFixed(3)}%`} />
              </div>
            </div>
            <div className="card">
              <h3 style={{ marginTop: 0, fontSize: 15 }}>Inter-pool net transmission</h3>
              <RankedBars
                records={tradeNetRecords}
                labelKey="pool"
                valueKey="value"
                emptyMessage="No inter-pool transmission balance data."
                limit={rankedLimit}
                filterText={barFilter}
              />
            </div>
          </div>

          <div className="grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <div className="card">
              <h3 style={{ marginTop: 0, fontSize: 15 }}>Physical emissions by pool</h3>
              <RankedBars
                records={emissionsByPool}
                labelKey="pool"
                valueKey="value"
                emptyMessage="No physical emissions records for this run."
                limit={rankedLimit}
                filterText={barFilter}
              />
            </div>
            <div className="card">
              <h3 style={{ marginTop: 0, fontSize: 15 }}>Cost decomposition by component</h3>
              <RankedBars
                records={costByComponent}
                labelKey="component"
                valueKey="value"
                emptyMessage="No cost decomposition records for this run."
                limit={rankedLimit}
                filterText={barFilter}
              />
            </div>
          </div>
        </>
      ) : null}

      {activeSection === "development" ? (
        <div className="grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <div className="card">
            <div className="row" style={{ justifyContent: "space-between" }}>
              <h3 style={{ marginTop: 0, fontSize: 15 }}>Development impacts by region</h3>
              <div>
                <label style={{ marginRight: 6 }}>Metric</label>
                <select value={developmentMetric} onChange={(e) => setDevelopmentMetric(e.target.value)}>
                  <option value="gva_total_musd">GVA (MUSD)</option>
                  <option value="jobs_total">Jobs</option>
                  <option value="household_income_proxy_musd">Household income (MUSD)</option>
                </select>
              </div>
            </div>
            <RankedBars
              records={developmentByRegion}
              labelKey="region"
              valueKey={developmentMetric}
              limit={rankedLimit}
              filterText={barFilter}
              emptyMessage="No development-by-region records for this run."
            />
            <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
              Value shown: {developmentMetricLabel}
            </div>
          </div>

          <div className="card">
            <h3 style={{ marginTop: 0, fontSize: 15 }}>Development impacts by supplier sector</h3>
            <RankedBars
              records={developmentBySector}
              labelKey="supplier_sector"
              valueKey={developmentMetric}
              limit={rankedLimit}
              filterText={barFilter}
              emptyMessage="No development-by-sector records for this run."
            />
            <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
              Value shown: {developmentMetricLabel}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function RecentJobsPanel({ jobs, selectedJobId, onSelectJob }) {
  return (
    <div className="card" style={{ marginTop: 14 }}>
      <h3 style={{ marginTop: 0, fontSize: 16 }}>Recent jobs</h3>
      {!jobs.length ? (
        <div className="muted">No jobs yet.</div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table className="panel-table">
            <thead>
              <tr>
                <th>Job</th>
                <th>Status</th>
                <th>Progress</th>
                <th>Scenario</th>
                <th>Run ID</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {jobs.slice(0, 12).map((j) => {
                return (
                <tr
                  key={j.job_id}
                  className={selectedJobId && j.job_id === selectedJobId ? "row-selected" : ""}
                  onClick={() => onSelectJob(j)}
                  style={{ cursor: "pointer" }}
                >
                  <td><code>{j.job_id}</code></td>
                  <td><StatusBadge status={j.status} /></td>
                  <td>{Math.round(toNumber(j.progress) * 100)}%</td>
                  <td>{(j.request && j.request.scenario) || "-"}</td>
                  <td>{(j.artifacts && j.artifacts.run_id) || "-"}</td>
                  <td>{new Date(j.created_at).toLocaleString()}</td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function aggregateCostByComponent(records) {
  const byComponent = new Map();
  (records || []).forEach((row) => {
    const component = String((row && row.component) || "other");
    const value = toNumber(row && row.value);
    byComponent.set(component, toNumber(byComponent.get(component)) + value);
  });
  return Array.from(byComponent.entries())
    .map(([component, value]) => ({ component, value }))
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
}

function aggregateByLabel(records, labelKey, valueKey) {
  const grouped = new Map();
  (records || []).forEach((row) => {
    const label = String(row && row[labelKey] != null ? row[labelKey] : "").trim();
    if (!label) return;
    const value = toNumber(row && row[valueKey]);
    grouped.set(label, toNumber(grouped.get(label)) + value);
  });
  return Array.from(grouped.entries())
    .map(([label, value]) => ({ [labelKey]: label, [valueKey]: value }))
    .sort((a, b) => Math.abs(toNumber(b && b[valueKey])) - Math.abs(toNumber(a && a[valueKey])));
}

function App() {
  const [scenarios, setScenarios] = useState([]);
  const [scenarioKey, setScenarioKey] = useState("");
  const [levers, setLevers] = useState({ ...DEFAULT_LEVERS });
  const [runProfile, setRunProfile] = useState("dev");
  const [environmentSetup, setEnvironmentSetup] = useState(null);
  const [environmentSetupLoading, setEnvironmentSetupLoading] = useState(false);
  const [jobs, setJobs] = useState([]);
  const [activeJob, setActiveJob] = useState(null);
  const [selectedJobId, setSelectedJobId] = useState("");
  const [result, setResult] = useState(null);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [integratedPayload, setIntegratedPayload] = useState(null);
  const [running, setRunning] = useState(false);
  const [queueSubmitting, setQueueSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [developmentMetric, setDevelopmentMetric] = useState("gva_total_musd");

  const selectedScenario = useMemo(
    () => (scenarios || []).find((s) => s.key === scenarioKey),
    [scenarios, scenarioKey]
  );
  const scenarioSelectorModel = useMemo(
    () => buildScenarioSelectorModel(scenarios),
    [scenarios]
  );
  const scenarioSelections = useMemo(
    () => deriveScenarioSelections(scenarioKey, scenarioSelectorModel),
    [scenarioKey, scenarioSelectorModel]
  );

  async function refreshScenarios() {
    try {
      const rows = await api.fetchScenarios();
      setScenarios(rows);
      setScenarioKey((prev) => {
        if (prev && rows.some((s) => s.key === prev)) return prev;
        return (rows[0] && rows[0].key) || "";
      });
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to load scenarios"));
    }
  }

  async function refreshEnvironmentSetup(nextScenario, nextRunProfile) {
    const scenario = nextScenario || scenarioKey;
    const profile = nextRunProfile || runProfile;
    setEnvironmentSetupLoading(true);
    try {
      const payload = await api.fetchEnvironmentSetup(scenario, profile);
      setEnvironmentSetup(payload);
      return payload;
    } catch (err) {
      setEnvironmentSetup(null);
      setErrorMessage(toErrorMessage(err, "Failed to load environment setup checks"));
      return null;
    } finally {
      setEnvironmentSetupLoading(false);
    }
  }

  async function refreshJobs() {
    try {
      const rows = await api.fetchJobs(50);
      setJobs(rows);
      const runningJob = rows.find((j) => normalizeStatus(j.status) === "running") || null;
      const queuedJob = rows.find((j) => normalizeStatus(j.status) === "queued") || null;
      const activeDisplayJob = runningJob || queuedJob;
      setRunning(Boolean(runningJob));
      setActiveJob((prev) => {
        if (activeDisplayJob) return activeDisplayJob;
        if (prev && isActiveStatus(prev.status)) return prev;
        return null;
      });
      const selectedJob =
        (selectedJobId && rows.find((j) => j.job_id === selectedJobId)) ||
        runningJob ||
        rows[0] ||
        null;
      if (selectedJob) {
        setSelectedJobId(selectedJob.job_id);
      }
      if (
        selectedJob &&
        normalizeStatus(selectedJob.status) === "succeeded" &&
        selectedJob.artifacts &&
        selectedJob.summary
      ) {
        setSelectedRunId(selectedJob.artifacts.run_id);
        setResult({ artifacts: selectedJob.artifacts, summary: selectedJob.summary });
      } else {
        setSelectedRunId("");
        setResult(null);
      }
      return rows;
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to load job queue"));
      return [];
    }
  }

  async function hydrateIntegratedForRun(runId, fallbackSummary) {
    if (fallbackSummary && Object.keys(fallbackSummary).length > 0) {
      setIntegratedPayload(fallbackSummary);
      return;
    }
    try {
      const payload = await api.fetchIntegrated(runId);
      setIntegratedPayload(payload);
    } catch (_) {
      setIntegratedPayload(null);
    }
  }

  async function finalizeJob(job) {
    setRunning(false);
    const status = normalizeStatus(job.status);

    if (status === "succeeded" && job.artifacts && job.summary) {
      const nextResult = { artifacts: job.artifacts, summary: job.summary };
      setResult(nextResult);
      setSelectedRunId(job.artifacts.run_id);
      setSelectedJobId(job.job_id);
      setStatusMessage(`Run ${job.artifacts.run_id} completed successfully.`);
      setErrorMessage("");
      await hydrateIntegratedForRun(job.artifacts.run_id, job.summary.integrated_results || null);
    } else if (status === "failed") {
      setSelectedJobId(job.job_id);
      setErrorMessage(job.error || job.message || "Run failed.");
    } else if (status === "cancelled") {
      setSelectedJobId(job.job_id);
      setErrorMessage("Run was cancelled.");
    }

    setActiveJob(null);
    await refreshJobs();
  }

  useEffect(() => {
    let cancelled = false;
    async function boot() {
      setErrorMessage("");
      setStatusMessage("");
      await Promise.all([refreshScenarios(), refreshJobs()]);
      if (cancelled) return;
    }
    boot();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!scenarioKey) return;
    let cancelled = false;
    async function loadEnvironmentSetup() {
      try {
        const payload = await api.fetchEnvironmentSetup(scenarioKey, runProfile);
        if (!cancelled) setEnvironmentSetup(payload);
      } catch (_) {
        if (!cancelled) setEnvironmentSetup(null);
      } finally {
        if (!cancelled) setEnvironmentSetupLoading(false);
      }
    }
    setEnvironmentSetupLoading(true);
    loadEnvironmentSetup();
    return () => {
      cancelled = true;
    };
  }, [scenarioKey, runProfile]);

  useEffect(() => {
    const runId = result && result.artifacts && result.artifacts.run_id;
    if (!runId) {
      setIntegratedPayload(null);
      return;
    }

    let cancelled = false;
    async function load() {
      const fromSummary = result && result.summary && result.summary.integrated_results;
      if (fromSummary && Object.keys(fromSummary).length > 0) {
        setIntegratedPayload(fromSummary);
        return;
      }
      try {
        const payload = await api.fetchIntegrated(runId);
        if (!cancelled) setIntegratedPayload(payload);
      } catch (_) {
        if (!cancelled) setIntegratedPayload(null);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [result && result.artifacts && result.artifacts.run_id]);

  useEffect(() => {
    if (!activeJob || !isActiveStatus(activeJob.status)) return;

    let stopped = false;
    const poll = async () => {
      try {
        const latest = await api.fetchJob(activeJob.job_id);
        if (stopped) return;
        setActiveJob(latest);
        setRunning(isActiveStatus(latest.status));
        if (isTerminalStatus(latest.status)) await finalizeJob(latest);
      } catch (err) {
        if (!stopped) setErrorMessage(toErrorMessage(err, "Failed to poll active job"));
      }
    };

    poll();
    const timer = window.setInterval(() => poll(), 2000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [activeJob && activeJob.job_id]);

  async function onRun() {
    if (!scenarioKey || queueSubmitting) return;

    setErrorMessage("");
    setStatusMessage("");
    setQueueSubmitting(true);

    try {
      const currentEnvironmentSetup = await refreshEnvironmentSetup(scenarioKey, runProfile);
      if (!(currentEnvironmentSetup && currentEnvironmentSetup.ok)) {
        const blockingErrors = Array.isArray(currentEnvironmentSetup && currentEnvironmentSetup.errors)
          ? currentEnvironmentSetup.errors
          : [];
        const queueState = currentEnvironmentSetup && currentEnvironmentSetup.queue;
        const queueBlocked =
          queueState && toNumber(queueState.active_jobs) >= toNumber(queueState.capacity, 1);
        const message =
          blockingErrors[0] ||
          (queueBlocked
            ? "Queue is currently at capacity. Wait for active jobs to finish."
            : "Environment setup checks are not passing. Resolve highlighted issues and retry.");
        setErrorMessage(message);
        return;
      }

      const job = await api.submitJob({
        scenario: scenarioKey,
        fast_dev_mode: runProfile !== "full",
        run_profile: runProfile,
        levers,
      });
      setActiveJob(job);
      setSelectedJobId(job.job_id);
      setRunning(true);
      setStatusMessage(`Queued run ${job.job_id}.`);
      await refreshJobs();
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to submit run"));
    } finally {
      setQueueSubmitting(false);
    }
  }

  async function onCancelActiveJob() {
    if (!activeJob) return;
    try {
      const updated = await api.cancelJob(activeJob.job_id);
      setActiveJob(updated);
      setStatusMessage(updated.message || `Cancellation requested for job ${updated.job_id}.`);
      if (isTerminalStatus(updated.status)) await finalizeJob(updated);
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to cancel job"));
    }
  }

  function onSelectJob(job) {
    if (!job) return;
    setSelectedJobId(job.job_id);
    if (normalizeStatus(job.status) === "succeeded" && job.artifacts && job.summary) {
      setResult({ artifacts: job.artifacts, summary: job.summary });
      setSelectedRunId(job.artifacts.run_id);
      setStatusMessage(`Inspecting run ${job.artifacts.run_id}.`);
    } else {
      setSelectedRunId("");
      setResult(null);
      setStatusMessage(`Selected job ${job.job_id} (${job.status}).`);
    }
    setErrorMessage("");
  }

  function onApplyTemplateLevers() {
    if (!(selectedScenario && selectedScenario.preset_levers)) return;
    setLevers((prev) => ({ ...prev, ...selectedScenario.preset_levers }));
  }

  function onScenarioSelectionChange(patch) {
    const nextSelections = { ...scenarioSelections, ...(patch || {}) };
    const resolvedKey = resolveScenarioKey(scenarioSelectorModel, nextSelections);
    if (resolvedKey && resolvedKey !== scenarioKey) {
      setScenarioKey(resolvedKey);
    }
  }

  function onResetLevers() {
    setLevers({ ...DEFAULT_LEVERS });
  }

  const summaryDiagnostics = (result && result.summary && result.summary.summary_diagnostics) || {};
  const runMetadata = summaryDiagnostics.run_metadata || {};
  const exchangeArtifacts = (result && result.summary && result.summary.exchange_artifacts) || {};

  const integratedView = integratedPayload || ((result && result.summary && result.summary.integrated_results) || {});
  const integratedMetrics = Array.isArray(integratedView && integratedView.integrated_overview && integratedView.integrated_overview.metrics)
    ? integratedView.integrated_overview.metrics
    : [];

  const developmentDrivers = (integratedView && integratedView.development_drivers) || {};
  const confidence = (integratedView && integratedView.development_confidence) || ((result && result.summary && result.summary.coupling_manifest) || {});
  const baselineComparison = (integratedView && integratedView.baseline_comparison) || {};
  const developmentUncertainty = (integratedView && integratedView.development_uncertainty) || {};

  const reliability = summaryDiagnostics.reliability || {};
  const tradeNetRecords = Array.isArray(summaryDiagnostics && summaryDiagnostics.trade_matrix && summaryDiagnostics.trade_matrix.net_by_pool && summaryDiagnostics.trade_matrix.net_by_pool.records)
    ? summaryDiagnostics.trade_matrix.net_by_pool.records
    : [];
  const emissionsByPool = Array.isArray(summaryDiagnostics && summaryDiagnostics.physical_emissions && summaryDiagnostics.physical_emissions.by_pool && summaryDiagnostics.physical_emissions.by_pool.records)
    ? summaryDiagnostics.physical_emissions.by_pool.records
    : [];

  const costByComponent = aggregateCostByComponent(
    Array.isArray(summaryDiagnostics && summaryDiagnostics.cost_decomposition && summaryDiagnostics.cost_decomposition.component_records)
      ? summaryDiagnostics.cost_decomposition.component_records
      : []
  );

  const developmentByRegion = Array.isArray(result && result.summary && result.summary.development_impacts && result.summary.development_impacts.by_region && result.summary.development_impacts.by_region.records)
    ? result.summary.development_impacts.by_region.records
    : Array.isArray(integratedView && integratedView.regional_development && integratedView.regional_development.records)
      ? integratedView.regional_development.records
      : [];

  const developmentBySector = Array.isArray(result && result.summary && result.summary.development_impacts && result.summary.development_impacts.by_supplier_sector && result.summary.development_impacts.by_supplier_sector.records)
    ? result.summary.development_impacts.by_supplier_sector.records
    : [];
  const selectedJob = useMemo(() => {
    if (activeJob && selectedJobId && activeJob.job_id === selectedJobId) return activeJob;
    return (jobs || []).find((j) => j.job_id === selectedJobId) || null;
  }, [jobs, activeJob, selectedJobId]);

  const selectedRunLabel = selectedRunId ? "Selected run" : "Latest run";

  return (
    <div className="container">
      <div className="card" style={{ marginBottom: 14 }}>
        <h1 style={{ margin: 0, fontSize: 22 }}>EDIM MVP Workbench</h1>
        <div className="muted" style={{ fontSize: 13, marginTop: 6 }}>
          Select a scenario, queue one run, and inspect integrated energy-development outputs.
        </div>
      </div>

      {errorMessage ? <div className="warn">{errorMessage}</div> : null}
      {statusMessage ? <div className="ok">{statusMessage}</div> : null}

      <WorkflowStatusPanel
        hasScenario={Boolean(scenarioKey)}
        environmentSetupOk={Boolean(environmentSetup && environmentSetup.ok)}
        running={running}
        hasResult={Boolean(result)}
      />

      <ModelStructurePanel />

      <ScenarioSetupPanel
        scenarios={scenarios}
        scenarioKey={scenarioKey}
        selectorModel={scenarioSelectorModel}
        scenarioSelections={scenarioSelections}
        selectedScenario={selectedScenario}
        levers={levers}
        runProfile={runProfile}
        running={running}
        queueSubmitting={queueSubmitting}
        onScenarioChange={setScenarioKey}
        onScenarioSelectionChange={onScenarioSelectionChange}
        onSetLevers={setLevers}
        onSetRunProfile={setRunProfile}
        onApplyTemplateLevers={onApplyTemplateLevers}
        onRun={onRun}
        onResetLevers={onResetLevers}
      />

      <EnvironmentSetupPanel
        environmentSetup={environmentSetup}
        loading={environmentSetupLoading}
        onRefresh={() => refreshEnvironmentSetup()}
      />

      <ActiveJobPanel activeJob={activeJob} onCancel={onCancelActiveJob} />
      <SelectedJobDetailsPanel job={selectedJob} />

      <RunResultsPanel
        result={result}
        selectedRunLabel={selectedRunLabel}
        runMetadata={runMetadata}
        exchangeArtifacts={exchangeArtifacts}
        integratedMetrics={integratedMetrics}
        developmentDrivers={developmentDrivers}
        confidence={confidence}
        baselineComparison={baselineComparison}
        developmentUncertainty={developmentUncertainty}
        reliability={reliability}
        tradeNetRecords={tradeNetRecords}
        emissionsByPool={emissionsByPool}
        costByComponent={costByComponent}
        developmentByRegion={developmentByRegion}
        developmentBySector={developmentBySector}
        developmentMetric={developmentMetric}
        setDevelopmentMetric={setDevelopmentMetric}
        developmentMetricLabel={DEVELOPMENT_METRIC_LABELS[developmentMetric]}
      />

      <RecentJobsPanel jobs={jobs} selectedJobId={selectedJobId} onSelectJob={onSelectJob} />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
