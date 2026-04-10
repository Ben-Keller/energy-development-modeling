const { useEffect, useMemo, useRef, useState } = React;

const API_BASE = String(window.EDIM_API_BASE || "").trim().replace(/\/+$/, "");
const ACTIVE_STATUSES = new Set(["queued", "running"]);
const TERMINAL_JOB_STATUSES = new Set(["succeeded", "failed", "cancelled"]);

const DEFAULT_LEVERS = {
  demand_multiplier: 1.0,
  renewables_capex_multiplier: 1.0,
  fossil_fuel_price_multiplier: 1.0,
  carbon_price_usd_per_tco2: 0.0,
};

const ENERGY_MODEL_OPTIONS = [
  { value: "calliope", label: "Calliope", runtimeStatus: "Executable now" },
  { value: "osemosys", label: "OSeMOSYS", runtimeStatus: "Adapter target, runtime pending" },
];

const POLICY_LEVER_TOOLTIPS = {
  renewables_capex_multiplier:
    "Scales renewable generation capital costs before the energy solve. Values below 1.0 represent policies that reduce delivered renewable CAPEX, such as concessional finance, tax credits, local supply-chain improvements, or procurement reform. Values above 1.0 test higher financing, equipment, or delivery costs.",
  fossil_fuel_price_multiplier:
    "Scales fossil fuel variable costs. Values above 1.0 represent higher fuel prices, reduced subsidies, supply risk premiums, or fuel-tax exposure. Values below 1.0 represent lower fuel costs or continued subsidies. Interpret this as an operating-cost policy and market-risk lever.",
  carbon_price_usd_per_tco2:
    "Adds a carbon cost per tonne of CO2 to emitting generation. Higher values represent carbon pricing, emissions standards converted to an implicit price, or climate-risk cost internalization. Use it to test how strongly emissions are penalized in dispatch and investment decisions.",
  demand_multiplier:
    "Scales electricity demand. Values above 1.0 represent faster electrification, access expansion, industrial growth, or higher demand forecasts. Values below 1.0 represent efficiency, demand response, slower growth, or conservation. Interpret it as a demand-side policy and planning-sensitivity lever.",
};

const DEVELOPMENT_METRIC_LABELS = {
  gva_total_musd: "Gross value added (MUSD)",
  jobs_total: "Jobs",
  household_income_proxy_musd: "Household income proxy (MUSD)",
};

const LOCATION_MAP_METRICS = [
  { key: "total_shock_musd", label: "Total shock (CAPEX + OPEX) (MUSD)", scope: "location" },
  { key: "capex_shock_musd", label: "CAPEX shock (MUSD)", scope: "location" },
  { key: "opex_shock_musd", label: "OPEX/fuel shock (MUSD)", scope: "location" },
  { key: "jobs_total", label: "Jobs (regional)", scope: "region" },
  { key: "gva_total_musd", label: "GVA (MUSD, regional)", scope: "region" },
  {
    key: "household_income_proxy_musd",
    label: "Household income proxy (MUSD, regional)",
    scope: "region",
  },
];

const LOCATION_MAP_GEOJSON_PATH =
  String(window.EDIM_GEOJSON_PATH || "").trim() || "./geo/world_fit.geojson";

const LOCATION_MAP_COUNTRIES_MANIFEST_PATH =
  String(window.EDIM_COUNTRIES_MANIFEST_PATH || "").trim() || "./geo/countries_manifest.json";

const LOCATION_MAP_TOPO_DIR =
  String(window.EDIM_COUNTRIES_TOPO_DIR || "").trim() || "./geo/countries_topojson";

const RUN_STAGE_ORDER = [
  "queued",
  "scenario_prepare",
  "energy_input_prepare",
  "build_model",
  "solve_energy",
  "write_artifacts",
  "build_summary",
  "bridge_prepare",
  "mrio_direct_prepare",
  "development",
  "build_integrated",
  "complete",
];

const ARCHITECTURE_BOXES = [
  {
    id: "scenario",
    type: "input",
    title: "Integrated scenario definition",
    subtitle: "User parameters + scenario datasets",
    stages: ["scenario_prepare"],
  },
  {
    id: "operations",
    type: "model",
    title: "Environment setup",
    subtitle: "Validation diagnostics, queue state, run controls, and selected job context",
    stages: ["queued", "scenario_prepare", "complete"],
  },
  {
    id: "calliope_data",
    type: "input",
    title: "Energy model input data",
    subtitle: "Static model files, scenario definitions, levers, and model metadata",
    datasetLayers: ["calliope", "scenario"],
    stages: ["energy_input_prepare", "build_model"],
  },
  {
    id: "mrio_data",
    type: "input",
    title: "MRIO input data",
    subtitle: "Intensity, sector split, indicator, geography, and report-derived target datasets",
    datasetLayers: ["mrio", "bridge"],
    stages: ["mrio_direct_prepare", "development"],
  },
  {
    id: "adapter",
    type: "model",
    title: "Unified scenario adapter",
    subtitle: "Routes one scenario package into the selected energy model, bridge, and MRIO inputs",
    stages: ["scenario_prepare", "energy_input_prepare", "mrio_direct_prepare"],
  },
  {
    id: "calliope",
    type: "model",
    title: "Energy model",
    subtitle: "Selected engine solves generation, capacity, costs, reliability, emissions, and spatial energy outputs",
    stages: ["build_model", "solve_energy", "write_artifacts", "build_summary"],
  },
  {
    id: "bridge",
    type: "model",
    title: "Energy-to-MRIO bridge",
    subtitle: "Translates solved energy outputs into investment, operating, fuel, and price/tax shocks",
    stages: ["bridge_prepare"],
  },
  {
    id: "mrio",
    type: "model",
    title: "MRIO development runtime",
    subtitle: "Combines bridge channel, direct MRIO assumptions, and general MRIO input datasets",
    stages: ["development"],
  },
  {
    id: "outputs",
    type: "output",
    title: "Integrated outputs",
    subtitle: "Downloadable run artifacts, diagnostics, and dashboard-ready results",
    stages: ["build_integrated", "complete"],
  },
];

const DEFAULT_OUTPUT_ARTIFACTS = [
  { key: "results_csv", label: "Integrated results CSV", url: "csv" },
  { key: "report_markdown", label: "Run report Markdown", url: "report" },
  { key: "exchange_bundle_zip", label: "Exchange bundle ZIP", url: "exchange_bundle" },
  { key: "scenario_package_json", label: "Unified scenario package JSON" },
  { key: "energy_input_manifest_json", label: "Energy input manifest JSON" },
  { key: "report_scenario_reference_json", label: "Report scenario reference JSON" },
  { key: "geography_alignment_json", label: "Geography alignment diagnostics JSON" },
  { key: "mrio_direct_inputs_json", label: "MRIO-direct inputs JSON" },
  { key: "mrio_direct_shocks_csv", label: "MRIO-direct shocks CSV" },
  { key: "energy_service_balance_csv", label: "Energy service balance CSV" },
  { key: "calliope_component_activity_csv", label: "Calliope component activity CSV" },
  { key: "investment_shocks_csv", label: "Investment shocks CSV" },
  { key: "operating_shocks_csv", label: "Operating shocks CSV" },
  { key: "prices_and_taxes_csv", label: "Prices and taxes CSV" },
  { key: "coupling_manifest_json", label: "Coupling manifest JSON" },
];

const ARCHITECTURE_NODE_BOX_MAP = {
  userParams: "scenario",
  scenarioData: "scenario",
  calliopeStaticData: "calliope_data",
  adapter: "adapter",
  energyModel: "calliope",
  bridge: "bridge",
  mrioInputs: "mrio_data",
  mario: "mrio",
  outputs: "outputs",
};

const DEFAULT_FLOW_NODE_LAYOUT = {
  scenario: { x: 40, y: 30, w: 900, h: 650 },
  operations: { x: 990, y: 30, w: 450, h: 650 },
  calliope_data: { x: 40, y: 820, w: 360, h: 170 },
  adapter: { x: 505, y: 820, w: 470, h: 150 },
  mrio_data: { x: 1040, y: 820, w: 390, h: 170 },
  calliope: { x: 72, y: 1100, w: 380, h: 150 },
  bridge: { x: 515, y: 1240, w: 390, h: 140 },
  mrio: { x: 1015, y: 1265, w: 410, h: 155 },
  outputs: { x: 520, y: 1560, w: 430, h: 155 },
};

const DEFAULT_FLOW_EDGES = [
  { from: "scenario", to: "adapter", label: "scenario settings" },
  { from: "calliope_data", to: "calliope", label: "static energy inputs" },
  { from: "adapter", to: "calliope", label: "engine patch" },
  { from: "adapter", to: "mrio", label: "MRIO shocks" },
  { from: "calliope", to: "bridge", label: "solved outputs" },
  { from: "calliope", to: "outputs", label: "energy results" },
  { from: "bridge", to: "mrio", label: "bridge channel" },
  { from: "mrio_data", to: "mrio", label: "MRIO datasets" },
  { from: "mrio", to: "outputs", label: "development results" },
];

const DEFAULT_FLOW_CANVAS_SIZE = { width: 1480, height: 1740 };
const DEFAULT_FLOW_NODE_ORDER = ["scenario", "operations", "calliope_data", "adapter", "mrio_data", "calliope", "bridge", "mrio", "outputs"];
const DEFAULT_FIXED_FLOW_NODES = ["scenario", "operations"];

function defaultFlowDefinition() {
  return {
    canvas: { ...DEFAULT_FLOW_CANVAS_SIZE },
    nodes: Object.fromEntries(Object.entries(DEFAULT_FLOW_NODE_LAYOUT).map(([id, rect]) => [id, { ...rect }])),
    edges: DEFAULT_FLOW_EDGES.map((edge) => ({ ...edge })),
    order: [...DEFAULT_FLOW_NODE_ORDER],
    fixedNodes: [...DEFAULT_FIXED_FLOW_NODES],
  };
}

function normalizeMainUiFlow(flow) {
  if (!flow || !Array.isArray(flow.nodes) || !flow.nodes.length) return defaultFlowDefinition();
  const nodes = {};
  const order = [];
  flow.nodes.forEach((node) => {
    const id = String(node && node.id ? node.id : "").trim();
    if (!id) return;
    const rect = {
      x: Number(node.x),
      y: Number(node.y),
      w: Number(node.w || node.width),
      h: Number(node.h || node.height),
    };
    if (!Number.isFinite(rect.x) || !Number.isFinite(rect.y) || !Number.isFinite(rect.w) || !Number.isFinite(rect.h)) return;
    nodes[id] = rect;
    order.push(id);
  });
  if (!order.length) return defaultFlowDefinition();
  const canvas = flow.canvas || {};
  return {
    canvas: {
      width: Number(canvas.width) || DEFAULT_FLOW_CANVAS_SIZE.width,
      height: Number(canvas.height) || DEFAULT_FLOW_CANVAS_SIZE.height,
    },
    nodes,
    edges: Array.isArray(flow.edges)
      ? flow.edges
          .map((edge) => ({
            from: String(edge && edge.from ? edge.from : "").trim(),
            to: String(edge && edge.to ? edge.to : "").trim(),
            label: String(edge && edge.label ? edge.label : "").trim(),
          }))
          .filter((edge) => edge.from && edge.to)
      : DEFAULT_FLOW_EDGES.map((edge) => ({ ...edge })),
    order,
    fixedNodes: Array.isArray(flow.fixedNodes) ? flow.fixedNodes.map((id) => String(id)) : [...DEFAULT_FIXED_FLOW_NODES],
  };
}

const LOCATION_MAP_ID_KEYS = [
  "location_id",
  "location",
  "calliope_location",
  "iso3",
  "ISO_A3",
  "id",
];

const LOCATION_MAP_REGION_KEYS = ["mario_region", "region", "subregion", "name"];

const SUBREGION_CENTROIDS = {
  KEN_NBOR: { country: "KEN", lat: -1.2833, lon: 36.8172, label: "Kenya Nairobi Region" },
  KEN_CSTR: { country: "KEN", lat: -1.910164, lon: 40.588417, label: "Kenya Coast Region" },
  KEN_WSTR: { country: "KEN", lat: 1.91667, lon: 35.3333, label: "Kenya Western Region" },
  KEN_MTKR: { country: "KEN", lat: 0.071, lon: 37.69, label: "Kenya Mount Kenya Region" },
  NGA_CNW: { country: "NGA", lat: 10.80866, lon: 7.404304, label: "Center and North-West Nigeria" },
  NGA_E: { country: "NGA", lat: 10.157032, lon: 11.276511, label: "East Nigeria" },
  NGA_S: { country: "NGA", lat: 5.573991, lon: 6.605761, label: "South Nigeria" },
  NGA_W: { country: "NGA", lat: 7.708529, lon: 3.999334, label: "West Nigeria" },
  MOZ_NC: { country: "MOZ", lat: -15.0, lon: 33.0, label: "Mozambique North-Center" },
  MOZ_S: { country: "MOZ", lat: -26.0, lon: 32.0, label: "Mozambique South" },
};

const REGION_TO_POOL_HINTS = {
  north_africa: "NAPP",
  central_africa: "CAPP",
  east_africa: "EAPP",
  southern_africa: "SAPP",
  west_africa: "WAPP",
};

const AI_REGION_ALIASES = [
  { aliases: ["west africa", "western africa", "wapp"], region: "west_africa", label: "West Africa", pool: "WAPP" },
  { aliases: ["east africa", "eastern africa", "eapp"], region: "east_africa", label: "East Africa", pool: "EAPP" },
  { aliases: ["southern africa", "south africa region", "sapp"], region: "southern_africa", label: "Southern Africa", pool: "SAPP" },
  { aliases: ["central africa", "middle africa", "capp"], region: "central_africa", label: "Central Africa", pool: "CAPP" },
  { aliases: ["north africa", "northern africa", "napp"], region: "north_africa", label: "North Africa", pool: "NAPP" },
];

const AI_COUNTRY_ALIASES = [
  { iso3: "DZA", label: "Algeria", aliases: ["algeria", "dza"] },
  { iso3: "AGO", label: "Angola", aliases: ["angola", "ago"] },
  { iso3: "BEN", label: "Benin", aliases: ["benin"] },
  { iso3: "BWA", label: "Botswana", aliases: ["botswana", "bwa"] },
  { iso3: "BFA", label: "Burkina Faso", aliases: ["burkina faso", "burkina", "bfa"] },
  { iso3: "BDI", label: "Burundi", aliases: ["burundi", "bdi"] },
  { iso3: "CMR", label: "Cameroon", aliases: ["cameroon", "cmr"] },
  { iso3: "CPV", label: "Cape Verde", aliases: ["cape verde", "cabo verde", "cpv"] },
  { iso3: "CAF", label: "Central African Republic", aliases: ["central african republic", "car", "caf"] },
  { iso3: "TCD", label: "Chad", aliases: ["chad", "tcd"] },
  { iso3: "COM", label: "Comoros", aliases: ["comoros", "com"] },
  { iso3: "COG", label: "Republic of the Congo", aliases: ["republic of the congo", "congo brazzaville", "cog"] },
  { iso3: "COD", label: "Democratic Republic of the Congo", aliases: ["democratic republic of the congo", "dr congo", "drc", "cod"] },
  { iso3: "CIV", label: "Cote d'Ivoire", aliases: ["cote d ivoire", "ivory coast", "civ"] },
  { iso3: "DJI", label: "Djibouti", aliases: ["djibouti", "dji"] },
  { iso3: "EGY", label: "Egypt", aliases: ["egypt", "egy"] },
  { iso3: "GNQ", label: "Equatorial Guinea", aliases: ["equatorial guinea", "gnq"] },
  { iso3: "ERI", label: "Eritrea", aliases: ["eritrea", "eri"] },
  { iso3: "SWZ", label: "Eswatini", aliases: ["eswatini", "swaziland", "swz"] },
  { iso3: "ETH", label: "Ethiopia", aliases: ["ethiopia", "eth"] },
  { iso3: "GAB", label: "Gabon", aliases: ["gabon", "gab"] },
  { iso3: "GMB", label: "Gambia", aliases: ["gambia", "the gambia", "gmb"] },
  { iso3: "GHA", label: "Ghana", aliases: ["ghana", "gha"] },
  { iso3: "GIN", label: "Guinea", aliases: ["guinea", "gin"] },
  { iso3: "GNB", label: "Guinea-Bissau", aliases: ["guinea bissau", "guinea-bissau", "gnb"] },
  { iso3: "KEN", label: "Kenya", aliases: ["kenya", "ken"] },
  { iso3: "LSO", label: "Lesotho", aliases: ["lesotho", "lso"] },
  { iso3: "LBR", label: "Liberia", aliases: ["liberia", "lbr"] },
  { iso3: "LBY", label: "Libya", aliases: ["libya", "lby"] },
  { iso3: "MDG", label: "Madagascar", aliases: ["madagascar", "mdg"] },
  { iso3: "MWI", label: "Malawi", aliases: ["malawi", "mwi"] },
  { iso3: "MLI", label: "Mali", aliases: ["mali", "mli"] },
  { iso3: "MRT", label: "Mauritania", aliases: ["mauritania", "mrt"] },
  { iso3: "MUS", label: "Mauritius", aliases: ["mauritius", "mus"] },
  { iso3: "MAR", label: "Morocco", aliases: ["morocco", "mar"] },
  { iso3: "MOZ", label: "Mozambique", aliases: ["mozambique", "moz"] },
  { iso3: "NAM", label: "Namibia", aliases: ["namibia", "nam"] },
  { iso3: "NER", label: "Niger", aliases: ["niger", "ner"] },
  { iso3: "NGA", label: "Nigeria", aliases: ["nigeria", "nga"] },
  { iso3: "RWA", label: "Rwanda", aliases: ["rwanda", "rwa"] },
  { iso3: "STP", label: "Sao Tome and Principe", aliases: ["sao tome and principe", "sao tome", "stp"] },
  { iso3: "SEN", label: "Senegal", aliases: ["senegal", "sen"] },
  { iso3: "SYC", label: "Seychelles", aliases: ["seychelles", "syc"] },
  { iso3: "SLE", label: "Sierra Leone", aliases: ["sierra leone", "sle"] },
  { iso3: "SOM", label: "Somalia", aliases: ["somalia", "som"] },
  { iso3: "ZAF", label: "South Africa", aliases: ["south africa", "zaf", "za"] },
  { iso3: "SSD", label: "South Sudan", aliases: ["south sudan", "ssd"] },
  { iso3: "SDN", label: "Sudan", aliases: ["sudan", "sdn"] },
  { iso3: "TZA", label: "Tanzania", aliases: ["tanzania", "united republic of tanzania", "tza"] },
  { iso3: "TGO", label: "Togo", aliases: ["togo", "tgo"] },
  { iso3: "TUN", label: "Tunisia", aliases: ["tunisia", "tun"] },
  { iso3: "UGA", label: "Uganda", aliases: ["uganda", "uga"] },
  { iso3: "ZMB", label: "Zambia", aliases: ["zambia", "zmb"] },
  { iso3: "ZWE", label: "Zimbabwe", aliases: ["zimbabwe", "zwe"] },
];

const MAP_COLOR_SCALE_STOPS = [
  { at: 0.0, color: "#132b43" },
  { at: 0.25, color: "#1b5b7a" },
  { at: 0.5, color: "#2f8ca3" },
  { at: 0.75, color: "#6abf69" },
  { at: 1.0, color: "#f3c24d" },
];

const STATUS_THEME = {
  queued: { label: "Queued", className: "badge badge-queued" },
  running: { label: "Running", className: "badge badge-running" },
  succeeded: { label: "Succeeded", className: "badge badge-succeeded" },
  failed: { label: "Failed", className: "badge badge-failed" },
  cancelled: { label: "Cancelled", className: "badge badge-cancelled" },
  ok: { label: "OK", className: "badge badge-succeeded" },
  warn: { label: "Warn", className: "badge badge-warning" },
  error: { label: "Error", className: "badge badge-failed" },
  production_ready: { label: "Production ready", className: "badge badge-succeeded" },
  analyst_review: { label: "Analyst review", className: "badge badge-warning" },
  exploratory_only: { label: "Exploratory only", className: "badge badge-failed" },
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

function formatSharePercent(value, digits = 1) {
  const n = toNumber(value, NaN);
  if (!Number.isFinite(n)) return "-";
  return `${(n * 100).toFixed(digits)}%`;
}

function humanizeResolution(value) {
  const key = String(value || "").trim().toLowerCase();
  if (!key) return "-";
  if (key === "location") return "Country/subcountry";
  if (key === "region") return "Region";
  if (key === "pool") return "Power pool";
  if (key === "global") return "Global";
  if (key === "location_or_pool") return "Country/subcountry or pool";
  if (key === "region_supplier") return "Region-supplier";
  return key.replace(/_/g, " ");
}

function normalizeLocationId(value) {
  return String(value || "").trim().toUpperCase();
}

function normalizeRegionKey(value) {
  return String(value || "").trim().toLowerCase();
}

function locationToParentCountry(location) {
  const token = normalizeLocationId(location);
  if (!token) return "";
  const idx = token.indexOf("_");
  return idx >= 0 ? token.slice(0, idx) : token;
}

function isSubregionLocation(location) {
  const token = normalizeLocationId(location);
  return token.includes("_");
}

function firstNonEmpty(obj, keys) {
  if (!obj || typeof obj !== "object") return "";
  for (const key of keys || []) {
    const value = obj[key];
    if (value != null && String(value).trim()) return String(value).trim();
  }
  return "";
}

function splitCsvLine(line) {
  const cells = [];
  let current = "";
  let inQuotes = false;
  for (let idx = 0; idx < line.length; idx += 1) {
    const ch = line[idx];
    if (inQuotes) {
      if (ch === "\"") {
        const next = line[idx + 1];
        if (next === "\"") {
          current += "\"";
          idx += 1;
        } else {
          inQuotes = false;
        }
      } else {
        current += ch;
      }
      continue;
    }
    if (ch === "\"") {
      inQuotes = true;
      continue;
    }
    if (ch === ",") {
      cells.push(current);
      current = "";
      continue;
    }
    current += ch;
  }
  cells.push(current);
  return cells;
}

function parseCsvRows(csvText) {
  const src = String(csvText || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  if (!src.trim()) return [];
  const lines = src.split("\n").filter((line) => line.trim());
  if (!lines.length) return [];
  const headers = splitCsvLine(lines[0]).map((col) => String(col || "").trim());
  if (!headers.length) return [];
  return lines
    .slice(1)
    .map((line) => splitCsvLine(line))
    .map((cells) => {
      const row = {};
      headers.forEach((key, idx) => {
        row[key] = String(cells[idx] != null ? cells[idx] : "").trim();
      });
      return row;
    })
    .filter((row) => Object.values(row).some((value) => String(value || "").trim()));
}

function parseLocTechCarrierToken(token) {
  const src = String(token || "").trim();
  if (!src) return null;
  const parts = src.split("::");
  if (parts.length < 2) return null;
  const location = cleanLocationToken(parts[0]);
  const tech = String(parts[1] || "").trim();
  if (!location || !tech) return null;
  return { location, tech };
}

function parseLocTechToken(token) {
  const src = String(token || "").trim();
  if (!src) return null;
  const parts = src.split("::");
  if (parts.length < 2) return null;
  const location = cleanLocationToken(parts[0]);
  const tech = String(parts[1] || "").trim();
  if (!location || !tech) return null;
  return { location, tech };
}

function addTechValueByLocation(target, location, tech, value) {
  if (!target || !location || !tech || !Number.isFinite(value)) return;
  if (!target.has(location)) target.set(location, new Map());
  const techMap = target.get(location);
  techMap.set(tech, toNumber(techMap.get(tech)) + value);
}

function addValueByLocation(target, location, value) {
  if (!target || !location || !Number.isFinite(value)) return;
  target.set(location, toNumber(target.get(location)) + value);
}

function buildRunSpatialTechData(resultsCsvText) {
  const src = String(resultsCsvText || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  if (!src.trim()) {
    return {
      generationByLocationTech: new Map(),
      capacityByLocationTech: new Map(),
      monetaryCostByLocation: new Map(),
      emissionsByLocation: new Map(),
      demandByLocation: new Map(),
      unservedByLocation: new Map(),
    };
  }
  const lines = src.split("\n").filter((line) => line.trim());
  if (lines.length < 2) {
    return {
      generationByLocationTech: new Map(),
      capacityByLocationTech: new Map(),
      monetaryCostByLocation: new Map(),
      emissionsByLocation: new Map(),
      demandByLocation: new Map(),
      unservedByLocation: new Map(),
    };
  }

  const headers = splitCsvLine(lines[0]).map((col) => String(col || "").trim());
  const idx = new Map(headers.map((col, i) => [col, i]));
  const variableIdx = idx.get("variable");
  const valueIdx = idx.get("value");
  if (variableIdx == null || valueIdx == null) {
    return {
      generationByLocationTech: new Map(),
      capacityByLocationTech: new Map(),
      monetaryCostByLocation: new Map(),
      emissionsByLocation: new Map(),
      demandByLocation: new Map(),
      unservedByLocation: new Map(),
    };
  }

  const locTechCarrierIdx = idx.get("loc_tech_carriers_prod");
  const locTechsIdx = idx.get("loc_techs");
  const locTechsCostIdx = idx.get("loc_techs_cost");
  const locTechsDemandIdx = idx.get("loc_techs_balance_demand_constraint");
  const locCarriersIdx = idx.get("loc_carriers");
  const costsIdx = idx.get("costs");
  const locsIdx = idx.get("locs");
  const techsIdx = idx.get("techs");

  const generationByLocationTech = new Map();
  const capacityByLocationTech = new Map();
  const monetaryCostByLocation = new Map();
  const emissionsByLocation = new Map();
  const demandByLocation = new Map();
  const unservedByLocation = new Map();

  for (let i = 1; i < lines.length; i += 1) {
    const cells = splitCsvLine(lines[i]);
    const variable = String(cells[variableIdx] || "").trim();
    if (
      variable !== "carrier_prod" &&
      variable !== "energy_cap" &&
      variable !== "cost" &&
      variable !== "required_resource" &&
      variable !== "unmet_demand"
    ) {
      continue;
    }
    const value = toNumber(cells[valueIdx], NaN);
    if (!Number.isFinite(value)) continue;

    let parsed = null;
    if (variable === "cost") {
      const costClass = String((costsIdx != null && cells[costsIdx]) || "").trim().toLowerCase();
      if (costClass !== "monetary" && costClass !== "co2") continue;
      if (locTechsCostIdx != null) {
        parsed = parseLocTechToken(cells[locTechsCostIdx]);
      }
      if (!parsed && locsIdx != null) {
        const location = cleanLocationToken(cells[locsIdx]);
        parsed = location ? { location, tech: "" } : null;
      }
      if (parsed && parsed.location) {
        if (costClass === "monetary") addValueByLocation(monetaryCostByLocation, parsed.location, value);
        else addValueByLocation(emissionsByLocation, parsed.location, value);
      }
      continue;
    } else if (variable === "required_resource") {
      if (locTechsDemandIdx != null) {
        parsed = parseLocTechToken(cells[locTechsDemandIdx]);
      }
      if (!parsed && locsIdx != null) {
        const location = cleanLocationToken(cells[locsIdx]);
        parsed = location ? { location, tech: "" } : null;
      }
      if (parsed && parsed.location) {
        addValueByLocation(demandByLocation, parsed.location, Math.abs(value));
      }
      continue;
    } else if (variable === "unmet_demand") {
      if (locCarriersIdx != null) {
        const location = cleanLocationToken(cells[locCarriersIdx]);
        parsed = location ? { location, tech: "" } : null;
      }
      if (!parsed && locsIdx != null) {
        const location = cleanLocationToken(cells[locsIdx]);
        parsed = location ? { location, tech: "" } : null;
      }
      if (parsed && parsed.location) {
        addValueByLocation(unservedByLocation, parsed.location, Math.max(0, value));
      }
      continue;
    } else if (variable === "carrier_prod" && locTechCarrierIdx != null) {
      parsed = parseLocTechCarrierToken(cells[locTechCarrierIdx]);
    } else if (variable === "energy_cap" && locTechsIdx != null) {
      parsed = parseLocTechToken(cells[locTechsIdx]);
    }
    if (!parsed && locsIdx != null && techsIdx != null) {
      const location = cleanLocationToken(cells[locsIdx]);
      const tech = String(cells[techsIdx] || "").trim();
      parsed = location && tech ? { location, tech } : null;
    }
    if (!parsed) continue;

    if (variable === "carrier_prod") {
      addTechValueByLocation(generationByLocationTech, parsed.location, parsed.tech, value);
    } else if (variable === "energy_cap") {
      addTechValueByLocation(capacityByLocationTech, parsed.location, parsed.tech, value);
    }
  }

  return {
    generationByLocationTech,
    capacityByLocationTech,
    monetaryCostByLocation,
    emissionsByLocation,
    demandByLocation,
    unservedByLocation,
  };
}

function aggregateLocationShockRows(capexRows, opexRows) {
  const byLocation = new Map();
  const ingest = (rows, channelKey) => {
    (rows || []).forEach((row) => {
      const location = normalizeLocationId(firstNonEmpty(row, ["location", "calliope_location"]));
      if (!location) return;
      const value = toNumber(
        row && row.shock_value_musd != null && String(row.shock_value_musd).trim()
          ? row.shock_value_musd
          : row && row.shock_value,
        0
      );
      const region = firstNonEmpty(row, ["region", "mario_region"]);
      let rec = byLocation.get(location);
      if (!rec) {
        rec = {
          location,
          region,
          total_shock_musd: 0,
          capex_shock_musd: 0,
          opex_shock_musd: 0,
          row_count: 0,
        };
        byLocation.set(location, rec);
      }
      if (!rec.region && region) rec.region = region;
      rec[channelKey] = toNumber(rec[channelKey]) + value;
      rec.total_shock_musd = toNumber(rec.total_shock_musd) + value;
      rec.row_count += 1;
    });
  };

  ingest(capexRows, "capex_shock_musd");
  ingest(opexRows, "opex_shock_musd");

  return Array.from(byLocation.values()).sort(
    (a, b) => Math.abs(toNumber(b.total_shock_musd)) - Math.abs(toNumber(a.total_shock_musd))
  );
}

function aggregateLocationRowsByRegion(locationRows) {
  const byRegion = new Map();
  (locationRows || []).forEach((row) => {
    const regionKey = normalizeRegionKey(row && row.region);
    if (!regionKey) return;
    let rec = byRegion.get(regionKey);
    if (!rec) {
      rec = {
        region: String(row.region || ""),
        total_shock_musd: 0,
        capex_shock_musd: 0,
        opex_shock_musd: 0,
        location_count: 0,
      };
      byRegion.set(regionKey, rec);
    }
    rec.total_shock_musd = toNumber(rec.total_shock_musd) + toNumber(row.total_shock_musd);
    rec.capex_shock_musd = toNumber(rec.capex_shock_musd) + toNumber(row.capex_shock_musd);
    rec.opex_shock_musd = toNumber(rec.opex_shock_musd) + toNumber(row.opex_shock_musd);
    rec.location_count += 1;
  });
  return byRegion;
}

function cleanLocationToken(raw) {
  const token = normalizeLocationId(raw);
  if (!token) return "";
  const main = token.split("::")[0];
  return normalizeLocationId(main);
}

function rowLocationValue(row) {
  if (!row || typeof row !== "object") return "";
  return firstNonEmpty(row, [
    "location",
    "location_id",
    "calliope_location",
    "iso3",
    "ISO_A3",
    "loc",
    "locs",
  ]);
}

function rowRegionValue(row) {
  if (!row || typeof row !== "object") return "";
  return firstNonEmpty(row, ["region", "mario_region"]);
}

function rowPoolValue(row) {
  if (!row || typeof row !== "object") return "";
  return firstNonEmpty(row, ["pool", "src_pool", "dst_pool"]);
}

function normalizePoolKey(value) {
  return String(value || "").trim().toUpperCase();
}

function inferPoolFromRegion(region) {
  const key = normalizeRegionKey(region);
  if (!key) return "";
  return normalizePoolKey(REGION_TO_POOL_HINTS[key] || "");
}

function buildRegionLookup(records) {
  const map = new Map();
  (records || []).forEach((row) => {
    const region = rowRegionValue(row);
    const key = normalizeRegionKey(region);
    if (!key || map.has(key)) return;
    map.set(key, row);
  });
  return map;
}

function metricValueForFeature(resolved, metricKey, regionLookup) {
  if (!resolved) return NaN;
  const row = resolved.record;
  if (row && row[metricKey] != null && String(row[metricKey]).trim() !== "") {
    const value = toNumber(row[metricKey], NaN);
    if (Number.isFinite(value)) return value;
  }
  const regionKey = normalizeRegionKey(
    (row && row.region) || resolved.regionKey || resolved.region || ""
  );
  if (!regionKey || !(regionLookup instanceof Map) || !regionLookup.has(regionKey)) return NaN;
  const regionRow = regionLookup.get(regionKey);
  return toNumber(regionRow && regionRow[metricKey], NaN);
}

function spatialFilterGranularity(spatialFilter) {
  if (!spatialFilter) return "global";
  const selectedLocation = normalizeLocationId(spatialFilter.locationId);
  if (selectedLocation) return isSubregionLocation(selectedLocation) ? "subregion" : "country";
  const selectedCountry = normalizeLocationId(spatialFilter.countryIso3);
  if (selectedCountry) return "country";
  const selectedRegion = normalizeRegionKey(spatialFilter.region);
  if (selectedRegion) return "region";
  const selectedPool = normalizePoolKey(spatialFilter.pool || inferPoolFromRegion(spatialFilter.region));
  if (selectedPool) return "pool";
  return "global";
}

function rowMatchesSpatialFilter(row, spatialFilter) {
  if (!spatialFilter) return true;
  const selectionGranularity = spatialFilterGranularity(spatialFilter);
  const selectedLocation = normalizeLocationId(spatialFilter.locationId);
  const selectedCountry = normalizeLocationId(spatialFilter.countryIso3 || locationToParentCountry(selectedLocation));
  const selectedRegion = normalizeRegionKey(spatialFilter.region);
  const selectedPool = normalizePoolKey(spatialFilter.pool || inferPoolFromRegion(spatialFilter.region));

  const locationRaw = rowLocationValue(row);
  const regionRaw = rowRegionValue(row);
  const poolRaw = rowPoolValue(row);
  const rowLocation = cleanLocationToken(locationRaw);
  const rowRegion = normalizeRegionKey(regionRaw);
  const rowPool = normalizePoolKey(poolRaw);

  if (rowLocation) {
    if (selectedLocation && !isSubregionLocation(selectedLocation)) {
      return locationToParentCountry(rowLocation) === selectedLocation;
    }
    if (selectedLocation) {
      return rowLocation === selectedLocation;
    }
    if (selectedCountry) {
      return locationToParentCountry(rowLocation) === selectedCountry;
    }
    if (selectedRegion && rowRegion) {
      return rowRegion === selectedRegion;
    }
    return true;
  }
  if (rowRegion) {
    if (selectionGranularity === "region") return rowRegion === selectedRegion;
    return false;
  }
  if (rowPool) {
    if (selectionGranularity === "pool") return rowPool === selectedPool;
    if (selectionGranularity === "region" && selectedPool) return rowPool === selectedPool;
    return false;
  }
  return false;
}

function applySpatialFilterRecords(records, spatialFilter) {
  if (!spatialFilter) return records || [];
  return (records || []).filter((row) => rowMatchesSpatialFilter(row, spatialFilter));
}

function buildLocationRegionLookup(locationMapData) {
  const out = new Map();
  const byLocation = locationMapData && locationMapData.byLocation;
  if (byLocation instanceof Map) {
    byLocation.forEach((row, locationId) => {
      const id = normalizeLocationId(locationId);
      if (!id) return;
      out.set(id, normalizeRegionKey(row && row.region));
    });
  } else {
    const rows = Array.isArray(locationMapData && locationMapData.locationRows)
      ? locationMapData.locationRows
      : [];
    rows.forEach((row) => {
      const id = normalizeLocationId(row && row.location);
      if (!id) return;
      out.set(id, normalizeRegionKey(row && row.region));
    });
  }
  return out;
}

function locationMatchesSpatialFilter(locationId, spatialFilter, locationRegionLookup) {
  if (!spatialFilter) return true;
  const selectedLocation = normalizeLocationId(spatialFilter.locationId);
  const selectedCountry = normalizeLocationId(spatialFilter.countryIso3 || locationToParentCountry(selectedLocation));
  const selectedRegion = normalizeRegionKey(spatialFilter.region);
  const rowLocation = normalizeLocationId(locationId);
  if (!rowLocation) return false;

  if (selectedLocation) {
    if (isSubregionLocation(selectedLocation)) return rowLocation === selectedLocation;
    return locationToParentCountry(rowLocation) === selectedLocation;
  }
  if (selectedCountry) {
    return locationToParentCountry(rowLocation) === selectedCountry;
  }
  if (selectedRegion && locationRegionLookup instanceof Map) {
    return normalizeRegionKey(locationRegionLookup.get(rowLocation)) === selectedRegion;
  }
  return true;
}

function aggregateSpatialTechByLocation(locationTechMap, spatialFilter, locationRegionLookup) {
  if (!(locationTechMap instanceof Map) || !locationTechMap.size) return [];
  const byTech = new Map();
  locationTechMap.forEach((techMap, locationId) => {
    if (!locationMatchesSpatialFilter(locationId, spatialFilter, locationRegionLookup)) return;
    if (!(techMap instanceof Map)) return;
    techMap.forEach((value, tech) => {
      byTech.set(tech, toNumber(byTech.get(tech)) + toNumber(value));
    });
  });
  return Array.from(byTech.entries())
    .map(([techs, value]) => ({ techs, value }))
    .sort((a, b) => Math.abs(toNumber(b && b.value)) - Math.abs(toNumber(a && a.value)));
}

function sumLocationValueMapForFilter(valuesByLocation, spatialFilter, locationRegionLookup) {
  if (!(valuesByLocation instanceof Map) || !valuesByLocation.size) {
    return { total: NaN, hasAny: false };
  }
  if (!spatialFilter) {
    let total = 0;
    valuesByLocation.forEach((value) => {
      total += toNumber(value, 0);
    });
    return { total, hasAny: true };
  }
  let total = 0;
  let hasAny = false;
  valuesByLocation.forEach((value, locationId) => {
    if (!locationMatchesSpatialFilter(locationId, spatialFilter, locationRegionLookup)) return;
    total += toNumber(value, 0);
    hasAny = true;
  });
  return hasAny ? { total, hasAny: true } : { total: NaN, hasAny: false };
}

function sumRowsNumeric(records, key) {
  return (records || []).reduce((sum, row) => sum + toNumber(row && row[key], 0), 0);
}

function isImportLeakageSectorName(name) {
  const supplier = String(name || "").trim().toLowerCase();
  if (!supplier) return false;
  return ["import", "foreign", "rest_of_world", "row"].some((token) => supplier.includes(token));
}

function pointInRing(point, ring) {
  const x = toNumber(point && point[0], NaN);
  const y = toNumber(point && point[1], NaN);
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Array.isArray(ring) || ring.length < 3) return false;
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
    const xi = toNumber(ring[i] && ring[i][0], NaN);
    const yi = toNumber(ring[i] && ring[i][1], NaN);
    const xj = toNumber(ring[j] && ring[j][0], NaN);
    const yj = toNumber(ring[j] && ring[j][1], NaN);
    if (!Number.isFinite(xi) || !Number.isFinite(yi) || !Number.isFinite(xj) || !Number.isFinite(yj)) continue;
    const intersects = (yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / ((yj - yi) || 1e-12) + xi;
    if (intersects) inside = !inside;
  }
  return inside;
}

function pointInPolygonCoords(point, polygonCoords) {
  if (!Array.isArray(polygonCoords) || !polygonCoords.length) return false;
  if (!pointInRing(point, polygonCoords[0])) return false;
  for (let idx = 1; idx < polygonCoords.length; idx += 1) {
    if (pointInRing(point, polygonCoords[idx])) return false;
  }
  return true;
}

function pointInGeometry(point, geometry) {
  if (!geometry || typeof geometry !== "object") return false;
  if (geometry.type === "Polygon") {
    return pointInPolygonCoords(point, geometry.coordinates || []);
  }
  if (geometry.type === "MultiPolygon") {
    const polygons = geometry.coordinates || [];
    return polygons.some((coords) => pointInPolygonCoords(point, coords));
  }
  return false;
}

function geometryBbox(geometry) {
  let minLon = Infinity;
  let minLat = Infinity;
  let maxLon = -Infinity;
  let maxLat = -Infinity;

  const walk = (coords) => {
    if (!Array.isArray(coords) || !coords.length) return;
    if (typeof coords[0] === "number" && typeof coords[1] === "number") {
      const lon = toNumber(coords[0], NaN);
      const lat = toNumber(coords[1], NaN);
      if (Number.isFinite(lon) && Number.isFinite(lat)) {
        minLon = Math.min(minLon, lon);
        minLat = Math.min(minLat, lat);
        maxLon = Math.max(maxLon, lon);
        maxLat = Math.max(maxLat, lat);
      }
      return;
    }
    coords.forEach((item) => walk(item));
  };
  walk(geometry && geometry.coordinates);

  if (!Number.isFinite(minLon) || !Number.isFinite(minLat) || !Number.isFinite(maxLon) || !Number.isFinite(maxLat)) {
    return null;
  }
  return [minLon, minLat, maxLon, maxLat];
}

function ensurePointInsideGeometry(point, geometry) {
  if (pointInGeometry(point, geometry)) return point;
  const bbox = geometryBbox(geometry);
  if (!bbox) return null;
  const [minLon, minLat, maxLon, maxLat] = bbox;
  const center = [(minLon + maxLon) / 2, (minLat + maxLat) / 2];
  if (pointInGeometry(center, geometry)) return center;

  const cols = 12;
  const rows = 12;
  for (let r = 0; r <= rows; r += 1) {
    const lat = minLat + ((maxLat - minLat) * r) / rows;
    for (let c = 0; c <= cols; c += 1) {
      const lon = minLon + ((maxLon - minLon) * c) / cols;
      const candidate = [lon, lat];
      if (pointInGeometry(candidate, geometry)) return candidate;
    }
  }
  return null;
}

function clampPointToGeometry(sourcePoint, targetPoint, geometry) {
  if (!sourcePoint || !targetPoint) return targetPoint;
  if (pointInGeometry(targetPoint, geometry)) return targetPoint;
  if (!pointInGeometry(sourcePoint, geometry)) return sourcePoint;

  let low = 0.0;
  let high = 1.0;
  for (let i = 0; i < 30; i += 1) {
    const mid = (low + high) / 2;
    const probe = [
      sourcePoint[0] + (targetPoint[0] - sourcePoint[0]) * mid,
      sourcePoint[1] + (targetPoint[1] - sourcePoint[1]) * mid,
    ];
    if (pointInGeometry(probe, geometry)) low = mid;
    else high = mid;
  }
  return [
    sourcePoint[0] + (targetPoint[0] - sourcePoint[0]) * low,
    sourcePoint[1] + (targetPoint[1] - sourcePoint[1]) * low,
  ];
}

function distanceDeg(a, b) {
  const dx = toNumber((a && a[0]) - (b && b[0]), 0);
  const dy = toNumber((a && a[1]) - (b && b[1]), 0);
  return Math.sqrt(dx * dx + dy * dy);
}

function createSubregionCircleFeature(countryFeature, subregionCode, subregionPoints, index) {
  const geometry = countryFeature && countryFeature.geometry;
  if (!geometry) return null;
  const centroidMeta = SUBREGION_CENTROIDS[subregionCode];
  if (!centroidMeta) return null;

  const requestedCenter = [toNumber(centroidMeta.lon, NaN), toNumber(centroidMeta.lat, NaN)];
  const center = ensurePointInsideGeometry(requestedCenter, geometry);
  if (!center) return null;

  const bbox = geometryBbox(geometry);
  if (!bbox) return null;
  const [minLon, minLat, maxLon, maxLat] = bbox;
  const width = Math.max(0.1, maxLon - minLon);
  const height = Math.max(0.1, maxLat - minLat);
  const count = Math.max(1, subregionPoints.length);

  const nearestOther = subregionPoints
    .filter((row) => row.code !== subregionCode)
    .map((row) => distanceDeg(center, row.center))
    .filter((v) => Number.isFinite(v) && v > 0)
    .sort((a, b) => a - b)[0];

  const baseRadiusLon = width / (3.2 * (Math.sqrt(count) + 1.5));
  const baseRadiusLat = height / (3.2 * (Math.sqrt(count) + 1.5));
  const nearestCap = Number.isFinite(nearestOther) ? Math.max(0.12, nearestOther * 0.42) : Infinity;
  const radiusLon = Math.max(0.1, Math.min(baseRadiusLon, nearestCap));
  const radiusLat = Math.max(0.1, Math.min(baseRadiusLat, nearestCap));

  const steps = 28;
  const ring = [];
  for (let i = 0; i < steps; i += 1) {
    const angle = (2 * Math.PI * i) / steps + (index * Math.PI) / steps;
    const target = [center[0] + Math.cos(angle) * radiusLon, center[1] + Math.sin(angle) * radiusLat];
    ring.push(clampPointToGeometry(center, target, geometry));
  }
  if (!ring.length) return null;
  ring.push(ring[0]);

  return {
    type: "Feature",
    properties: {
      location_id: subregionCode,
      display_name: centroidMeta.label || subregionCode,
      country_iso3: centroidMeta.country,
      synthetic_subregion_area: true,
      synthetic_method: "circle_fallback",
    },
    geometry: {
      type: "Polygon",
      coordinates: [ring],
    },
  };
}

function ensureClosedRing(ring) {
  if (!Array.isArray(ring) || !ring.length) return [];
  const out = ring.map((xy) => [toNumber(xy && xy[0], 0), toNumber(xy && xy[1], 0)]);
  const first = out[0];
  const last = out[out.length - 1];
  if (first[0] !== last[0] || first[1] !== last[1]) out.push([first[0], first[1]]);
  return out;
}

function createVoronoiSubregionFeatures(countryFeature, subregionPoints) {
  if (
    !window.d3 ||
    !window.d3.Delaunay ||
    !window.turf ||
    typeof window.turf.intersect !== "function"
  ) {
    return [];
  }
  const geometry = countryFeature && countryFeature.geometry;
  if (!geometry) return [];
  const bbox = geometryBbox(geometry);
  if (!bbox || subregionPoints.length < 2) return [];

  const [minLon, minLat, maxLon, maxLat] = bbox;
  const delaunay = window.d3.Delaunay.from(
    subregionPoints.map((row) => row.center),
    (p) => p[0],
    (p) => p[1]
  );
  const voronoi = delaunay.voronoi([minLon, minLat, maxLon, maxLat]);
  const countryShape = {
    type: "Feature",
    properties: {},
    geometry: JSON.parse(JSON.stringify(geometry)),
  };

  const features = [];
  subregionPoints.forEach((row, idx) => {
    const centroidMeta = SUBREGION_CENTROIDS[row.code] || {};
    const cell = voronoi.cellPolygon(idx);
    if (!cell || cell.length < 3) return;
    const cellRing = ensureClosedRing(cell);
    if (cellRing.length < 4) return;
    const cellFeature = {
      type: "Feature",
      properties: {},
      geometry: {
        type: "Polygon",
        coordinates: [cellRing],
      },
    };
    let clipped = null;
    try {
      clipped = window.turf.intersect(countryShape, cellFeature);
    } catch (_) {
      clipped = null;
    }
    const clippedGeometry = clipped && clipped.geometry ? clipped.geometry : null;
    if (!clippedGeometry) return;
    if (!pointInGeometry(row.center, clippedGeometry)) return;
    features.push({
      type: "Feature",
      properties: {
        location_id: row.code,
        display_name: centroidMeta.label || row.code,
        country_iso3: centroidMeta.country || locationToParentCountry(row.code),
        synthetic_subregion_area: true,
        synthetic_method: "voronoi",
      },
      geometry: clippedGeometry,
    });
  });
  return features;
}

function extractGeoFeatureLocationId(feature) {
  const props = (feature && feature.properties) || {};
  const fromProps = firstNonEmpty(props, LOCATION_MAP_ID_KEYS);
  if (fromProps) return normalizeLocationId(fromProps);
  const fromFeature = feature && feature.id != null ? String(feature.id).trim() : "";
  return normalizeLocationId(fromFeature);
}

function extractGeoFeatureRegionKey(feature) {
  const props = (feature && feature.properties) || {};
  const raw = firstNonEmpty(props, LOCATION_MAP_REGION_KEYS);
  return normalizeRegionKey(raw);
}

function getGeoFeatureLabel(feature) {
  const props = (feature && feature.properties) || {};
  const label = firstNonEmpty(props, [
    "display_name",
    "name",
    "admin",
    "location_id",
    "location",
    "calliope_location",
    "iso3",
    "ISO_A3",
    "region",
    "mario_region",
  ]);
  if (label) return label;
  return extractGeoFeatureLocationId(feature) || "Unnamed area";
}

function resolvedGeoUrl(basePath, relativePath) {
  const candidate = String(relativePath || "").trim();
  if (!candidate) return "";
  if (/^https?:\/\//i.test(candidate)) return candidate;
  try {
    return new URL(candidate, new URL(basePath, window.location.href)).toString();
  } catch (_) {
    return candidate;
  }
}

function buildLocationRowsFromCsvTexts(capexCsvText, opexCsvText) {
  const capexRows = parseCsvRows(capexCsvText);
  const opexRows = parseCsvRows(opexCsvText);
  return aggregateLocationShockRows(capexRows, opexRows);
}

function normalizeCountryFeatureFeature(countryIso3, feature) {
  if (!feature || feature.type !== "Feature" || !feature.geometry) return null;
  const props = { ...((feature && feature.properties) || {}) };
  if (!props.location_id) props.location_id = countryIso3;
  if (!props.country_iso3) props.country_iso3 = countryIso3;
  if (!props.display_name) props.display_name = String(props.nam_en || props.name || countryIso3);
  return {
    type: "Feature",
    properties: props,
    geometry: JSON.parse(JSON.stringify(feature.geometry)),
  };
}

async function loadCountryFeatureFromTopo(countryIso3, manifest) {
  if (!manifest || typeof manifest !== "object") return null;
  const countries = manifest.countries || {};
  const countryMeta = countries[countryIso3];
  if (!countryMeta || countryMeta.has_file === false) return null;
  const explicitTopoPath = String(countryMeta.file || "").trim();
  const inferredPath = `${LOCATION_MAP_TOPO_DIR.replace(/\/+$/, "")}/${countryIso3}.topo.json`;
  const topoUrl = explicitTopoPath
    ? resolvedGeoUrl(LOCATION_MAP_COUNTRIES_MANIFEST_PATH, explicitTopoPath)
    : resolvedGeoUrl(window.location.href, inferredPath);
  const resp = await fetch(topoUrl);
  if (!resp.ok) throw new Error(`Failed to load country topology for ${countryIso3}`);
  const topo = await resp.json();
  const objects = topo && topo.objects ? topo.objects : {};
  const objectName =
    String(countryMeta.object || manifest.topo_object_default || Object.keys(objects)[0] || "").trim() || "data";
  const object = objects[objectName];
  if (!object) return null;
  if (!window.topojson || typeof window.topojson.feature !== "function") {
    throw new Error("topojson-client library is not loaded.");
  }
  const converted = window.topojson.feature(topo, object);
  if (!converted) return null;
  if (converted.type === "FeatureCollection") {
    const first = Array.isArray(converted.features) ? converted.features[0] : null;
    return normalizeCountryFeatureFeature(countryIso3, first);
  }
  return normalizeCountryFeatureFeature(countryIso3, converted);
}

function sourceFeaturesByLocationId(sourceGeojson) {
  const map = new Map();
  const features = Array.isArray(sourceGeojson && sourceGeojson.features) ? sourceGeojson.features : [];
  features.forEach((feature) => {
    const id = extractGeoFeatureLocationId(feature);
    if (!id) return;
    if (!map.has(id)) map.set(id, feature);
  });
  return map;
}

async function buildLocationGeojsonFromCountryAssets(locationRows, sourceGeojson) {
  const requiredLocations = Array.from(
    new Set((locationRows || []).map((row) => normalizeLocationId(row && row.location)).filter(Boolean))
  );
  if (!requiredLocations.length) {
    return sourceGeojson && sourceGeojson.type === "FeatureCollection"
      ? sourceGeojson
      : { type: "FeatureCollection", features: [] };
  }

  const sourceById = sourceFeaturesByLocationId(sourceGeojson);
  const missing = requiredLocations.filter((location) => !sourceById.has(location));
  if (!missing.length) {
    return sourceGeojson && sourceGeojson.type === "FeatureCollection"
      ? sourceGeojson
      : { type: "FeatureCollection", features: [] };
  }

  const manifestResp = await fetch(LOCATION_MAP_COUNTRIES_MANIFEST_PATH);
  if (!manifestResp.ok) {
    throw new Error(`Failed to load countries manifest: ${LOCATION_MAP_COUNTRIES_MANIFEST_PATH}`);
  }
  const manifest = await manifestResp.json();

  const neededCountries = Array.from(new Set(missing.map((location) => locationToParentCountry(location)).filter(Boolean)));
  const countryFeaturePairs = await Promise.all(
    neededCountries.map(async (iso3) => {
      try {
        const feature = await loadCountryFeatureFromTopo(iso3, manifest);
        return [iso3, feature];
      } catch (_) {
        return [iso3, null];
      }
    })
  );
  const countryFeatures = new Map(countryFeaturePairs);

  const features = [];
  const seenLocations = new Set();

  requiredLocations.forEach((location) => {
    if (sourceById.has(location)) {
      const sourceFeature = sourceById.get(location);
      const props = { ...((sourceFeature && sourceFeature.properties) || {}) };
      props.location_id = location;
      if (!props.country_iso3) props.country_iso3 = locationToParentCountry(location);
      if (!props.display_name) props.display_name = getGeoFeatureLabel(sourceFeature);
      features.push({
        type: "Feature",
        properties: props,
        geometry: JSON.parse(JSON.stringify(sourceFeature.geometry)),
      });
      seenLocations.add(location);
    }
  });

  missing.forEach((location) => {
    if (seenLocations.has(location)) return;
    if (isSubregionLocation(location)) return;
    const countryIso3 = locationToParentCountry(location);
    const countryFeature = countryFeatures.get(countryIso3);
    if (!countryFeature || !countryFeature.geometry) return;
    const props = { ...(countryFeature.properties || {}) };
    props.location_id = location;
    props.country_iso3 = countryIso3;
    if (!props.display_name) props.display_name = String(props.nam_en || props.name || countryIso3);
    features.push({
      type: "Feature",
      properties: props,
      geometry: JSON.parse(JSON.stringify(countryFeature.geometry)),
    });
    seenLocations.add(location);
  });

  const subregionGroups = new Map();
  missing.forEach((location) => {
    if (!isSubregionLocation(location)) return;
    if (seenLocations.has(location)) return;
    const meta = SUBREGION_CENTROIDS[location];
    if (!meta) return;
    const countryIso3 = locationToParentCountry(location);
    if (!subregionGroups.has(countryIso3)) subregionGroups.set(countryIso3, []);
    subregionGroups.get(countryIso3).push(location);
  });

  Array.from(subregionGroups.entries()).forEach(([countryIso3, locations]) => {
    const countryFeature = countryFeatures.get(countryIso3);
    if (!countryFeature || !countryFeature.geometry) return;

    const subregionPoints = locations
      .map((location) => {
        const meta = SUBREGION_CENTROIDS[location];
        if (!meta) return null;
        const center = ensurePointInsideGeometry([meta.lon, meta.lat], countryFeature.geometry);
        if (!center) return null;
        return { code: location, center };
      })
      .filter(Boolean);

    const voronoiFeatures = createVoronoiSubregionFeatures(countryFeature, subregionPoints);
    const voronoiByCode = new Map(
      (voronoiFeatures || [])
        .map((feature) => {
          const id = normalizeLocationId(feature && feature.properties && feature.properties.location_id);
          return [id, feature];
        })
        .filter((pair) => pair[0])
    );

    subregionPoints.forEach((row, idx) => {
      const code = normalizeLocationId(row.code);
      const feature =
        voronoiByCode.get(code) ||
        createSubregionCircleFeature(countryFeature, row.code, subregionPoints, idx);
      if (!feature) return;
      features.push(feature);
      seenLocations.add(row.code);
    });
  });

  if (!features.length) {
    return sourceGeojson && sourceGeojson.type === "FeatureCollection"
      ? sourceGeojson
      : { type: "FeatureCollection", features: [] };
  }

  return {
    type: "FeatureCollection",
    features,
  };
}

function buildLocationMapData(runId, geojson, capexCsvText, opexCsvText, precomputedLocationRows = null) {
  const locationRows =
    Array.isArray(precomputedLocationRows) && precomputedLocationRows.length
      ? precomputedLocationRows
      : buildLocationRowsFromCsvTexts(capexCsvText, opexCsvText);
  const byLocation = new Map();
  locationRows.forEach((row) => {
    byLocation.set(normalizeLocationId(row.location), row);
  });
  const byRegion = aggregateLocationRowsByRegion(locationRows);

  const geoFeatures = Array.isArray(geojson && geojson.features) ? geojson.features : [];
  const featureLocationIds = new Set();
  const syntheticSubregionLocationIds = [];
  const placeholderGeometryLocationIds = [];
  geoFeatures.forEach((feature) => {
    const id = extractGeoFeatureLocationId(feature);
    if (id) featureLocationIds.add(id);
    const props = (feature && feature.properties) || {};
    if (props.synthetic_subregion_area && id) syntheticSubregionLocationIds.push(id);
    if ((props.placeholder_geometry || (geojson && geojson.is_placeholder)) && id) {
      placeholderGeometryLocationIds.push(id);
    }
  });
  const modelLocationIds = new Set(locationRows.map((row) => normalizeLocationId(row.location)));
  const unmatchedModelLocationIds = Array.from(modelLocationIds)
    .filter((id) => !featureLocationIds.has(id))
    .sort((a, b) => a.localeCompare(b));
  const unmatchedGeoLocationIds = Array.from(featureLocationIds)
    .filter((id) => !modelLocationIds.has(id))
    .sort((a, b) => a.localeCompare(b));

  return {
    runId,
    geojson,
    locationRows,
    byLocation,
    byRegion,
    coverage: {
      modelLocationCount: modelLocationIds.size,
      geoFeatureLocationCount: featureLocationIds.size,
      unmatchedModelLocationIds,
      unmatchedGeoLocationIds,
      syntheticSubregionLocationIds: syntheticSubregionLocationIds.sort((a, b) => a.localeCompare(b)),
      syntheticSubregionCount: syntheticSubregionLocationIds.length,
      placeholderGeometryLocationIds: placeholderGeometryLocationIds.sort((a, b) => a.localeCompare(b)),
      placeholderGeometryCount: placeholderGeometryLocationIds.length,
      placeholderGeojson: Boolean(geojson && geojson.is_placeholder),
    },
  };
}

function resolveFeatureRecord(feature, mapData) {
  if (!feature || !mapData) return { source: "none", record: null, locationId: "", regionKey: "" };
  const locationId = extractGeoFeatureLocationId(feature);
  if (locationId && mapData.byLocation && mapData.byLocation.has(locationId)) {
    return {
      source: "location",
      record: mapData.byLocation.get(locationId),
      locationId,
      regionKey: normalizeRegionKey(mapData.byLocation.get(locationId).region),
    };
  }
  const regionKey = extractGeoFeatureRegionKey(feature);
  if (regionKey && mapData.byRegion && mapData.byRegion.has(regionKey)) {
    return {
      source: "region",
      record: mapData.byRegion.get(regionKey),
      locationId,
      regionKey,
    };
  }
  return { source: "none", record: null, locationId, regionKey };
}

function clamp01(value) {
  return Math.max(0, Math.min(1, toNumber(value)));
}

function lerp(a, b, t) {
  return a + (b - a) * clamp01(t);
}

function hexToRgb(hex) {
  const clean = String(hex || "").replace("#", "").trim();
  if (!/^[0-9a-f]{6}$/i.test(clean)) return { r: 0, g: 0, b: 0 };
  return {
    r: Number.parseInt(clean.slice(0, 2), 16),
    g: Number.parseInt(clean.slice(2, 4), 16),
    b: Number.parseInt(clean.slice(4, 6), 16),
  };
}

function rgbToHex(r, g, b) {
  const asHex = (n) => {
    const v = Math.max(0, Math.min(255, Math.round(n)));
    return v.toString(16).padStart(2, "0");
  };
  return `#${asHex(r)}${asHex(g)}${asHex(b)}`;
}

function interpolateHexColor(startHex, endHex, t) {
  const start = hexToRgb(startHex);
  const end = hexToRgb(endHex);
  return rgbToHex(lerp(start.r, end.r, t), lerp(start.g, end.g, t), lerp(start.b, end.b, t));
}

function mapLegendGradient() {
  return `linear-gradient(90deg, ${MAP_COLOR_SCALE_STOPS
    .map((stop) => `${stop.color} ${(toNumber(stop.at) * 100).toFixed(1)}%`)
    .join(", ")})`;
}

function colorForMapValue(value, minValue, maxValue) {
  if (!Number.isFinite(value)) return "#1a2334";
  if (!Number.isFinite(minValue) || !Number.isFinite(maxValue) || maxValue <= minValue) {
    return MAP_COLOR_SCALE_STOPS[Math.floor(MAP_COLOR_SCALE_STOPS.length / 2)].color;
  }
  const t = (value - minValue) / (maxValue - minValue);
  const clamped = clamp01(t);
  for (let i = 1; i < MAP_COLOR_SCALE_STOPS.length; i += 1) {
    const prev = MAP_COLOR_SCALE_STOPS[i - 1];
    const next = MAP_COLOR_SCALE_STOPS[i];
    if (clamped <= next.at) {
      const local = (clamped - prev.at) / Math.max(1e-9, next.at - prev.at);
      return interpolateHexColor(prev.color, next.color, local);
    }
  }
  return MAP_COLOR_SCALE_STOPS[MAP_COLOR_SCALE_STOPS.length - 1].color;
}

function buildMapHistogramBins(values, minValue, maxValue, binCount = 16) {
  const cleanValues = (values || []).filter((value) => Number.isFinite(value));
  if (!cleanValues.length || !Number.isFinite(minValue) || !Number.isFinite(maxValue)) return [];
  if (maxValue <= minValue) {
    return [
      {
        min: minValue,
        max: maxValue,
        midpoint: minValue,
        count: cleanValues.length,
        share: 1,
      },
    ];
  }
  const bins = Array.from({ length: Math.max(2, binCount) }, (_, idx) => {
    const min = minValue + ((maxValue - minValue) * idx) / Math.max(1, binCount);
    const max = minValue + ((maxValue - minValue) * (idx + 1)) / Math.max(1, binCount);
    return {
      min,
      max,
      midpoint: (min + max) / 2,
      count: 0,
      share: 0,
    };
  });
  cleanValues.forEach((value) => {
    const t = (value - minValue) / (maxValue - minValue);
    const idx = Math.min(bins.length - 1, Math.max(0, Math.floor(t * bins.length)));
    bins[idx].count += 1;
  });
  const maxCount = Math.max(...bins.map((bin) => bin.count), 1);
  return bins.map((bin) => ({
    ...bin,
    share: bin.count / maxCount,
  }));
}

function escapeHtml(raw) {
  return String(raw || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
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

async function apiGetText(path, fallback) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(await parseApiError(res, fallback));
  return res.text();
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
  fetchScenarioCatalog: async () => apiGet("/api/scenarios", "Failed to load scenarios"),
  fetchInputDatasets: async () =>
    (await apiGet("/api/input-datasets", "Failed to load input datasets")).datasets || [],
  inputDatasetDownloadUrl: (datasetId) =>
    `${API_BASE}/api/input-datasets/${encodeURIComponent(datasetId)}/download`,
  uploadInputDataset: async (datasetId, file) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_BASE}/api/input-datasets/${encodeURIComponent(datasetId)}/upload`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw new Error(await parseApiError(res, "Failed to upload input dataset"));
    return res.json();
  },
  planScenarioQuery: async (payload) =>
    apiPost("/api/ai/scenario-query", payload, "Failed to run AI scenario query"),
  fetchEnvironmentSetup: async (energyScenarioKey, mrioScenarioId, targetYear, runProfile, strictValidation, allowPlaceholderData) => {
    const qs = new URLSearchParams();
    if (energyScenarioKey) qs.set("energy_scenario_key", energyScenarioKey);
    if (mrioScenarioId) qs.set("mrio_scenario_id", mrioScenarioId);
    if (targetYear) qs.set("target_year", String(targetYear));
    if (runProfile) qs.set("run_profile", runProfile);
    if (typeof strictValidation === "boolean") {
      qs.set("strict_validation", strictValidation ? "true" : "false");
    }
    if (typeof allowPlaceholderData === "boolean") {
      qs.set("allow_placeholder_data", allowPlaceholderData ? "true" : "false");
    }
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return apiGet(`/api/environment-setup${suffix}`, "Failed to run environment setup checks");
  },
  fetchJobs: async (limit) => (await apiGet(`/api/jobs?limit=${limit || 30}`, "Failed to load jobs")).jobs || [],
  fetchJob: async (jobId) => apiGet(`/api/jobs/${encodeURIComponent(jobId)}`, "Failed to load job"),
  submitJob: async (req) => (await apiPost("/api/jobs", req, "Failed to submit job")).job,
  cancelJob: async (jobId) => apiPost(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, null, "Failed to cancel job"),
  fetchIntegrated: async (runId) =>
    apiGet(`/api/run/${encodeURIComponent(runId)}/integrated`, "Failed to load integrated results"),
  fetchRunCsv: async (runId) =>
    apiGetText(`/api/run/${encodeURIComponent(runId)}/download/csv`, "Failed to load run results CSV"),
  fetchExchangeCsv: async (runId, filename) =>
    apiGetText(
      `/api/run/${encodeURIComponent(runId)}/download/exchange/${encodeURIComponent(filename)}`,
      `Failed to load ${filename}`
    ),
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

function Modal({ title, subtitle = "", onClose, children, wide = false }) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <div
        className={`modal-card${wide ? " wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", color: "#8ea4c5" }}>
              {subtitle || "Details"}
            </div>
            <h2 style={{ margin: "5px 0 0", fontSize: 20 }}>{title}</h2>
          </div>
          <button type="button" className="icon-button" aria-label={`Close ${title}`} onClick={onClose}>
            x
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

function environmentSetupSummary(environmentSetup) {
  const checks = Array.isArray(environmentSetup && environmentSetup.checks) ? environmentSetup.checks : [];
  const statusCounts = {};
  checks.forEach((row) => {
    const status = String((row && row.status) || "unknown").trim().toLowerCase() || "unknown";
    statusCounts[status] = (statusCounts[status] || 0) + 1;
  });
  const ok = statusCounts.ok || 0;
  const warn = statusCounts.warn || 0;
  const error = statusCounts.error || 0;
  return {
    checks,
    ok,
    warn,
    error,
    statusCounts,
    total: checks.length,
    errors: Array.isArray(environmentSetup && environmentSetup.errors) ? environmentSetup.errors : [],
    warnings: Array.isArray(environmentSetup && environmentSetup.warnings) ? environmentSetup.warnings : [],
  };
}

function checkStatusCountItems(setupSummary) {
  const counts = (setupSummary && setupSummary.statusCounts) || {};
  const preferred = ["ok", "warn", "error"];
  const items = preferred.map((status) => ({
    status,
    label: status === "ok" ? "OK" : status === "warn" ? "Warnings" : "Errors",
    count: toNumber(counts[status], 0),
  }));
  Object.keys(counts)
    .filter((status) => !preferred.includes(status))
    .sort((a, b) => a.localeCompare(b))
    .forEach((status) => {
      items.push({
        status,
        label: status.replace(/_/g, " "),
        count: toNumber(counts[status], 0),
      });
    });
  return items;
}

function environmentPlaceholderDiagnostics(environmentSetup) {
  const marioInputs = (environmentSetup && environmentSetup.mario_inputs) || {};
  const details = Array.isArray(marioInputs.placeholder_details) ? marioInputs.placeholder_details : [];
  const files = details
    .map((row) => String((row && row.file_name) || "").trim())
    .filter(Boolean)
    .sort((a, b) => a.localeCompare(b));
  const rowCount = details.reduce(
    (sum, row) => sum + toNumber(row && row.placeholder_row_count, 0),
    0
  );
  const checks = Array.isArray(environmentSetup && environmentSetup.checks) ? environmentSetup.checks : [];
  const scenarioPlaceholderCheck =
    checks.find((row) => String(row && row.name).toLowerCase() === "scenario_assumptions") ||
    null;
  const scenarioPlaceholderActive = Boolean(
    scenarioPlaceholderCheck &&
      /placeholder/i.test(String(scenarioPlaceholderCheck.message || ""))
  );
  return {
    details,
    files,
    rowCount,
    scenarioPlaceholderCheck,
    scenarioPlaceholderActive,
  };
}

function ValidationDiagnosticsSummary({ environmentSetup, loading = false, compactMode = false }) {
  const setupSummary = environmentSetupSummary(environmentSetup);
  const placeholders = environmentPlaceholderDiagnostics(environmentSetup);
  const attentionChecks = setupSummary.checks.filter((row) => String(row && row.status).toLowerCase() !== "ok");
  const status = loading
    ? "Checking..."
    : environmentSetup
      ? environmentSetup.ok
        ? "Passed"
        : "Needs attention"
      : "Awaiting checks";
  const statusColor = loading
    ? "#bfd4f5"
    : environmentSetup
      ? environmentSetup.ok
        ? "#bdf3d9"
        : "#ffd7b0"
      : "#a9bad0";

  return (
    <div
      style={{
        marginTop: compactMode ? 12 : 0,
        border: "1px solid #28405f",
        borderRadius: 10,
        padding: "10px 10px 12px",
        background: "#0b1424",
      }}
    >
      <div className="row" style={{ justifyContent: "space-between", gap: 8 }}>
        <div style={{ fontSize: 13, fontWeight: 700 }}>Validation diagnostics</div>
        <span style={{ color: statusColor, fontSize: 12, fontWeight: 700 }}>{status}</span>
      </div>
      <div className="row muted" style={{ marginTop: 8, fontSize: 12, gap: 10 }}>
        {checkStatusCountItems(setupSummary).map((item) => (
          <span key={`validation-count-${item.status}`}>
            {item.label}: <code>{loading ? "..." : item.count}</code>
          </span>
        ))}
      </div>
      {attentionChecks.length ? (
        <div style={{ marginTop: 8, display: "grid", gap: 6 }}>
          {attentionChecks.slice(0, 4).map((row, idx) => (
            <div key={`${row.name || "validation"}-${idx}`} className="muted" style={{ fontSize: 11 }}>
              <StatusBadge status={row.status || "warn"} /> {row.label || row.name || "Validation check"}:{" "}
              {row.message || "-"}
            </div>
          ))}
          {attentionChecks.length > 4 ? (
            <div className="muted" style={{ fontSize: 11 }}>
              {attentionChecks.length - 4} more validation diagnostics are available in Run readiness details.
            </div>
          ) : null}
        </div>
      ) : environmentSetup ? (
        <div className="muted" style={{ marginTop: 8, fontSize: 11 }}>
          No validation warnings or errors are reported for the current setup.
        </div>
      ) : (
        <div className="muted" style={{ marginTop: 8, fontSize: 11 }}>
          Validation results will appear after the readiness check completes.
        </div>
      )}
      <div className={placeholders.files.length || placeholders.rowCount > 0 || placeholders.scenarioPlaceholderActive ? "warn" : "ok"} style={{ marginTop: 8, marginBottom: 0, fontSize: 11 }}>
        {placeholders.files.length ? (
          <>
            Placeholder expert datasets: <code>{placeholders.files.join(", ")}</code>{" "}
            ({placeholders.rowCount} rows).
          </>
        ) : placeholders.rowCount > 0 ? (
          <>
            Placeholder expert dataset rows reported: <code>{placeholders.rowCount}</code>.
          </>
        ) : !environmentSetup ? (
          <>Placeholder diagnostics will appear after the readiness check completes.</>
        ) : (
          <>No placeholder expert datasets were reported.</>
        )}
        {placeholders.scenarioPlaceholderActive ? (
          <div style={{ marginTop: 4 }}>
            Scenario assumptions: {placeholders.scenarioPlaceholderCheck.message || "placeholder rows reported"}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function LeverControl({ label, value, min, max, step, onChange, tooltip = "" }) {
  const clamp = (v) => Math.min(max, Math.max(min, v));
  const apply = (raw) => {
    const parsed = Number.parseFloat(raw);
    if (!Number.isFinite(parsed)) return;
    onChange(clamp(parsed));
  };
  return (
    <div style={{ marginBottom: 10 }}>
      <label className="lever-label" title={tooltip || undefined}>
        <span>{label}</span>
        {tooltip ? (
          <span
            className="info-tooltip"
            tabIndex="0"
            role="note"
            title={tooltip}
            aria-label={`${label}: ${tooltip}`}
          >
            <span className="info-tooltip-icon">?</span>
            <span className="info-tooltip-panel">{tooltip}</span>
          </span>
        ) : null}
      </label>
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

function ModelStructurePanel({ style = null, columns = "1fr 1fr 1fr" }) {
  return (
    <div className="card" style={style || undefined}>
      <h3 style={{ marginTop: 0, fontSize: 16 }}>Model structure and data flow</h3>
      <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
        Current runtime architecture: user-defined run parameters and scenario source data are separate input
        streams into one unified adapter layer. The adapter outputs directly to the selected Energy Model and to the MRIO runtime,
        while the Energy Model also feeds integrated results directly for energy-side metrics. Calliope is executable now; OSeMOSYS is represented as the next adapter target.
      </div>
      <div className="grid" style={{ gridTemplateColumns: columns }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 13 }}>1) Separate input streams to the adapter</div>
          <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            The architecture separates what the user chooses from the source data that defines available scenarios.
            Both streams enter the unified adapter layer rather than flowing through a visible scenario-package box.
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            <code>scenario_package.json</code> still exists as a persisted run artifact for audit and rerun
            traceability, but it is not the conceptual routing node in the diagram.
          </div>
          <div style={{ overflowX: "auto", marginTop: 8 }}>
            <table className="panel-table">
              <thead>
                <tr>
                  <th>Input stream</th>
                  <th>Contents</th>
                  <th>Used by</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>User selections</td>
                  <td>Energy pathway, MRIO report scenario, target year, profile, policy levers</td>
                  <td>Unified adapter layer and run artifact provenance</td>
                </tr>
                <tr>
                  <td>Scenario data</td>
                  <td>Energy metadata, engine scenario key, parsed report assumptions</td>
                  <td>Unified adapter layer and scenario catalog</td>
                </tr>
                <tr>
                  <td>Energy model static data</td>
                  <td>Technology files, topology, demand/resource time series</td>
                  <td>Selected Energy Model directly</td>
                </tr>
                <tr>
                  <td>MRIO input datasets</td>
                  <td>Employment, GVA, development, uncertainty, supplier-sector coefficients</td>
                  <td>MRIO runtime directly</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div style={{ fontWeight: 700, fontSize: 13 }}>2) Unified adapter to model runtimes</div>
          <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            The separate energy and MRIO-direct adapter boxes are now represented as one adapter layer. That layer
            resolves user parameters against scenario source data, then outputs model-specific inputs directly to
            the selected Energy Model and the MRIO runtime.
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            It still writes <code>scenario/energy_input_manifest.json</code>,{" "}
            <code>scenario/mrio_direct_inputs.json</code>, <code>scenario/mrio_direct_shocks.csv</code>, and
            <code>scenario_package.json</code> as inspectable artifacts.
          </div>
          <div style={{ overflowX: "auto", marginTop: 8 }}>
            <table className="panel-table">
              <thead>
                <tr>
                  <th>Adapter output</th>
                  <th>Target model</th>
                  <th>Meaning</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Energy runtime patch</td>
                  <td>Energy Model</td>
                  <td>Selects override, profile, solver/time subset, and lever mappings</td>
                </tr>
                <tr>
                  <td>Energy input manifest</td>
                  <td>Energy model artifacts</td>
                  <td>Documents the resolved energy scenario inputs used for the run</td>
                </tr>
                <tr>
                  <td>MRIO shock payload</td>
                  <td>MRIO runtime</td>
                  <td>Report-derived A/Z, E, and Y heuristic shock rows and provenance</td>
                </tr>
                <tr>
                  <td>Scenario package artifact</td>
                  <td>Audit/debugging</td>
                  <td>Records both user parameters and source scenario references without acting as the visible routing box</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div style={{ fontWeight: 700, fontSize: 13 }}>3) Energy Model, bridge, MRIO, and integrated results</div>
          <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            The Energy Model has two visible output paths: one to the bridge layer for MRIO exchange artifacts, and one
            directly to integrated results for energy-side metrics, charts, and spatial diagnostics.
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            The MRIO runtime has three input streams: bridge artifacts from the Energy Model, the adapter-derived MRIO
            scenario payload, and general MRIO input datasets. <code>selected_totals</code> still default to the
            bridge channel on overlaps.
          </div>
          <div style={{ overflowX: "auto", marginTop: 8 }}>
            <table className="panel-table">
              <thead>
                <tr>
                  <th>Runtime stream</th>
                  <th>Artifacts / source</th>
                  <th>Meaning</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Energy Model to bridge</td>
                  <td><code>exchange/investment_shocks.csv</code>, <code>operating_shocks.csv</code></td>
                  <td>CAPEX and OPEX/fuel shocks mapped from energy-model technologies to MRIO sectors</td>
                </tr>
                <tr>
                  <td>Adapter to MRIO</td>
                  <td><code>scenario/mrio_direct_inputs.json</code>, <code>mrio_direct_shocks.csv</code></td>
                  <td>Report-derived A/Z, E, and Y scenario payload outside the energy-model boundary</td>
                </tr>
                <tr>
                  <td>MRIO datasets</td>
                  <td><code>inputs/mario_inputs/*.csv</code> and development coefficients</td>
                  <td>Employment, GVA, supplier-sector, uncertainty, and development-model coefficients</td>
                </tr>
                <tr>
                  <td>MRIO to results</td>
                  <td><code>development_impacts.json</code>, <code>coupling_manifest.json</code></td>
                  <td>Bridge, MRIO-direct, selected totals, combined diagnostics, and overlap warnings</td>
                </tr>
                <tr>
                  <td>Energy Model to results</td>
                  <td><code>integrated_results.json</code>, <code>exchange_bundle.zip</code></td>
                  <td>Direct energy-side final metrics plus dashboard contract, source channels, and provenance</td>
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
  targetScenarios,
  mrioShockMappings,
  mrioScenarioId,
  targetYears,
  targetYear,
  energyModelEngine,
  selectorModel,
  scenarioSelections,
  selectedScenario,
  levers,
  runProfile,
  environmentSetup,
  environmentSetupLoading,
  running,
  queueSubmitting,
  aiPrompt,
  setAiPrompt,
  onApplyAiPrompt,
  aiQueryResult,
  onScenarioChange,
  onMrioScenarioChange,
  onTargetYearChange,
  onEnergyModelEngineChange,
  onScenarioSelectionChange,
  onSetLevers,
  onSetRunProfile,
  onApplyTemplateLevers,
  onRun,
  onResetLevers,
  dashboardMode = false,
  style = null,
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
  const selectedTargetScenario = (targetScenarios || []).find((s) => s.scenario_id === mrioScenarioId) || null;
  const targetProfiles = (selectedTargetScenario && selectedTargetScenario.target_profiles) || {};
  const southAfricaTarget = targetProfiles.south_africa || {};
  const restOfAfricaTarget = targetProfiles.rest_of_africa_placeholder || {};
  const shockMapping = (mrioShockMappings || [])[0] || {};
  const shockCategories = Array.isArray(shockMapping.shock_categories) ? shockMapping.shock_categories : [];
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
    <div
      className="grid"
      style={{
        gridTemplateColumns: dashboardMode ? "1fr" : "1.2fr 0.8fr",
        marginTop: dashboardMode ? 0 : 14,
        ...(style || {}),
      }}
    >
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

                {showStructuredSelector ? (
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
                      These settings define the integrated target pathway used by the energy model and MRIO-direct
                      shock adapter. The MRIO section below only explains how those targets become A/Z, E, and Y shocks.
                    </div>
                    <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", marginTop: 8 }}>
                      <div>
                        <label>Target pathway</label>
                        <select
                          value={mrioScenarioId || ""}
                          onChange={(e) => onMrioScenarioChange && onMrioScenarioChange(e.target.value)}
                          style={{ width: "100%" }}
                        >
                          {(targetScenarios || []).map((s) => (
                            <option key={s.scenario_id} value={s.scenario_id}>
                              {s.scenario_id} - {s.short_label || s.label || s.scenario_type || "Target pathway"}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label>Target year</label>
                        <select
                          value={Number(targetYear || 2030)}
                          onChange={(e) => onTargetYearChange && onTargetYearChange(Number(e.target.value))}
                          style={{ width: "100%" }}
                        >
                          {(targetYears || [2030, 2050]).map((year) => (
                            <option key={year} value={Number(year)}>
                              {year}
                            </option>
                          ))}
                        </select>
                      </div>
                      {scenarioSelections.family === "pathway_2040" ? (
                        <>
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
                        </>
                      ) : null}
                    </div>
                    {selectedTargetScenario ? (
                      <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
                        Target data: South Africa uses <code>{southAfricaTarget.source_report_scenario_id || "-"}</code>{" "}
                        ({southAfricaTarget.renewable_share_2030 || "-"} RE by 2030; fossil delta{" "}
                        {southAfricaTarget.fossil_delta_2030 || "-"}). Other African countries use{" "}
                        <code>{restOfAfricaTarget.source_report_scenario_id || "-"}</code> placeholders (
                        {restOfAfricaTarget.renewable_share_2030 || "-"} RE by 2030; fossil delta{" "}
                        {restOfAfricaTarget.fossil_delta_2030 || "-"}).
                      </div>
                    ) : null}
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
                Pathway sets demand trajectory; build package sets generation/transmission expansion; target pathway
                sets country-level renewable/fossil policy targets; policy adds optional constraints when available.
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
            <div
              style={{
                marginTop: 12,
                border: "1px solid #28405f",
                borderRadius: 10,
                padding: "10px 10px 12px",
                background: "#0b1424",
              }}
            >
              <div style={{ fontWeight: 700, fontSize: 13 }}>MRIO shock mapping</div>
              <div className="muted" style={{ marginTop: 4, fontSize: 12 }}>
                The selected target pathway is mapped into MRIO-direct shocks here. This section does not set country
                targets; it documents the shock adapter used to translate targets into MRIO A/Z, E, and Y rows.
              </div>
              <div className="dashboard-note" style={{ marginTop: 8 }}>
                <div style={{ fontWeight: 700 }}>{shockMapping.label || "A/Z, E, and Y heuristic shock mapping"}</div>
                <div className="muted" style={{ marginTop: 4, fontSize: 12 }}>
                  Method: <code>{shockMapping.mapping_id || "mrio_direct_heuristic_v1"}</code>. Quality ceiling:{" "}
                  <code>{shockMapping.model_quality_ceiling || "analyst_review"}</code>.
                </div>
              </div>
              {shockCategories.length ? (
                <div style={{ display: "grid", gap: 6, marginTop: 8 }}>
                  {shockCategories.map((row, idx) => (
                    <div key={`${row.shock_type || row.mario_parameter || idx}`} className="muted" style={{ fontSize: 12 }}>
                      <b>{row.shock_type || "Shock"}</b>: <code>{row.mario_parameter || "-"}</code> -{" "}
                      {row.description || "Report-derived shock category."}
                    </div>
                  ))}
                </div>
              ) : null}
              {mrioScenarioId ? (
                <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
                  Resolved integrated package: <code>{scenarioKey || "-"}</code> + target{" "}
                  <code>{mrioScenarioId}</code> @ <code>{Number(targetYear || 2030)}</code>. National placeholder
                  expansion and shock rows are recorded in run diagnostics.
                </div>
              ) : null}
            </div>
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
          tooltip={POLICY_LEVER_TOOLTIPS.renewables_capex_multiplier}
          value={levers.renewables_capex_multiplier}
          min={0.7}
          max={1.5}
          step={0.05}
          onChange={(v) => onSetLevers({ ...levers, renewables_capex_multiplier: v })}
        />
        <LeverControl
          label="Fossil variable cost multiplier"
          tooltip={POLICY_LEVER_TOOLTIPS.fossil_fuel_price_multiplier}
          value={levers.fossil_fuel_price_multiplier}
          min={0.7}
          max={1.8}
          step={0.05}
          onChange={(v) => onSetLevers({ ...levers, fossil_fuel_price_multiplier: v })}
        />
        <LeverControl
          label="Carbon price (USD/tCO2)"
          tooltip={POLICY_LEVER_TOOLTIPS.carbon_price_usd_per_tco2}
          value={levers.carbon_price_usd_per_tco2}
          min={0}
          max={300}
          step={10}
          onChange={(v) => onSetLevers({ ...levers, carbon_price_usd_per_tco2: v })}
        />
        <LeverControl
          label="Demand multiplier"
          tooltip={POLICY_LEVER_TOOLTIPS.demand_multiplier}
          value={levers.demand_multiplier}
          min={0.8}
          max={1.4}
          step={0.05}
          onChange={(v) => onSetLevers({ ...levers, demand_multiplier: v })}
        />
      </div>
    </div>
  );
}

function ActiveJobPanel({ activeJob, onCancel, style = null }) {
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
    <div className="card" style={{ marginTop: 14, ...(style || {}) }}>
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

function SelectedJobDetailsPanel({ job, style = null }) {
  if (!job) return null;
  const isActive = isActiveStatus(job.status);
  const summary = job.summary || null;
  const exchangeArtifacts = (summary && summary.exchange_artifacts) || {};
  const hasOutputs = Boolean(job.artifacts && (job.artifacts.csv_url || job.artifacts.summary_url));

  return (
    <div className="card" style={{ marginTop: 14, ...(style || {}) }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <b>Selected job:</b> <code>{job.job_id}</code> <StatusBadge status={job.status} />
        </div>
        <div className="muted" style={{ fontSize: 12 }}>
          {job.created_at ? new Date(job.created_at).toLocaleString() : "-"}
        </div>
      </div>

      <div className="row muted" style={{ marginTop: 8, fontSize: 12 }}>
        <span>Energy: <code>{(job.request && job.request.energy_scenario_key) || "-"}</code></span>
        <span>Target: <code>{(job.request && job.request.mrio_scenario_id) || "-"}</code></span>
        <span>Year: <code>{(job.request && job.request.target_year) || "-"}</code></span>
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

function EnvironmentSetupPanel({
  environmentSetup,
  loading,
  onRefresh,
  onRun = null,
  runDisabled = false,
  queueSubmitting = false,
  running = false,
  style = null,
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [validationOpen, setValidationOpen] = useState(false);

  const setupSummary = environmentSetupSummary(environmentSetup);
  const checks = setupSummary.checks;
  const placeholders = environmentPlaceholderDiagnostics(environmentSetup);
  const statusCountItems = checkStatusCountItems(setupSummary);
  const cleanCheckLine = loading
    ? "Checking validation status..."
    : `${setupSummary.ok}/${setupSummary.total || 0} checks passed cleanly`;
  const statusLabel = loading
    ? "Checking..."
    : environmentSetup
      ? environmentSetup.ok
        ? "Ready to queue"
        : "Action needed"
      : "Not checked";
  const statusStyle = loading
    ? { border: "1px solid #33466a", background: "#0d1a30", color: "#bfd4f5" }
    : environmentSetup && environmentSetup.ok
      ? { border: "1px solid #2f5d49", background: "#10251d", color: "#bdf3d9" }
      : environmentSetup
        ? { border: "1px solid #6f4d2c", background: "#2b2015", color: "#ffd7b0" }
        : { border: "1px solid #33466a", background: "#101827", color: "#bfd4f5" };

  return (
    <div className="card" style={{ marginTop: 14, ...(style || {}) }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3 style={{ marginTop: 0, marginBottom: 0, fontSize: 16 }}>Environment setup</h3>
        <div className="row" style={{ gap: 8 }}>
          {onRun ? (
            <button type="button" className="run-play-button" onClick={onRun} disabled={runDisabled}>
              <span aria-hidden="true">▶</span>
              {queueSubmitting ? "Queuing..." : running ? "Queue another run" : "Run integrated model"}
            </button>
          ) : null}
          <button type="button" onClick={() => setDetailsOpen(true)} style={{ background: "#22304c", fontSize: 12, padding: "6px 10px" }}>
            Open details
          </button>
          <button type="button" onClick={onRefresh} style={{ background: "#22304c", fontSize: 12, padding: "6px 10px" }}>
            Refresh
          </button>
        </div>
      </div>
      <div style={{ ...statusStyle, borderRadius: 10, padding: "8px 10px", marginTop: 8, fontSize: 13 }}>
        {statusLabel}
      </div>
      <div className="muted environment-inline-summary">
        <span>{cleanCheckLine}</span>
        {environmentSetup && environmentSetup.queue ? (
          <>
            <span>Queue usage: {toNumber(environmentSetup.queue.active_jobs)} / {toNumber(environmentSetup.queue.capacity)}</span>
            <span>Solver: <code>{environmentSetup.solver_resolved || environmentSetup.solver_requested || "-"}</code></span>
            <span>Placeholder rows: <code>{placeholders.rowCount}</code></span>
          </>
        ) : null}
      </div>
      {setupSummary.errors.length ? (
        <div className="warn" style={{ marginTop: 10, marginBottom: 0 }}>
          {setupSummary.errors[0]}
        </div>
      ) : null}
      <div className="validation-expander">
        <button type="button" className="validation-toggle" onClick={() => setValidationOpen((prev) => !prev)}>
          {validationOpen ? "Hide validation diagnostics" : "Show validation diagnostics"}
        </button>
        {validationOpen ? (
          <ValidationDiagnosticsSummary
            environmentSetup={environmentSetup}
            loading={loading}
            compactMode={true}
          />
        ) : null}
      </div>
      {detailsOpen ? (
        <Modal title="Environment setup details" subtitle="Readiness checks" wide={true} onClose={() => setDetailsOpen(false)}>
          <div className="row" style={{ gap: 10, marginBottom: 12 }}>
            {statusCountItems.map((item) => (
              <MetricCard
                key={`environment-detail-count-${item.status}`}
                label={`${item.label} checks`}
                value={String(item.count)}
              />
            ))}
          </div>
          {environmentSetup && environmentSetup.queue ? (
            <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
              Queue usage: {toNumber(environmentSetup.queue.active_jobs)} / {toNumber(environmentSetup.queue.capacity)}
              {" · "}
              Solver: <code>{environmentSetup.solver_resolved || environmentSetup.solver_requested || "-"}</code>
              {" · "}
              Placeholder rows: <code>{placeholders.rowCount}</code>
            </div>
          ) : null}
          <ValidationDiagnosticsSummary environmentSetup={environmentSetup} loading={loading} />
          {checks.length ? (
            <div style={{ overflowX: "auto", marginTop: 12 }}>
              <table className="panel-table">
                <thead>
                  <tr>
                    <th>Check</th>
                    <th>Category</th>
                    <th>Status</th>
                    <th>Message</th>
                  </tr>
                </thead>
                <tbody>
                  {checks.map((row, idx) => (
                    <tr key={`${row.name || "check"}-${idx}`}>
                      <td>{row.label || row.name || "-"}</td>
                      <td>{row.category || "-"}</td>
                      <td><StatusBadge status={row.status || "-"} /></td>
                      <td>{row.message || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="muted">No readiness check details are available yet.</div>
          )}
        </Modal>
      ) : null}
    </div>
  );
}

function RunDiagnosticsCard({ confidence }) {
  const placeholderInputFiles = Array.isArray(confidence && confidence.placeholder_input_files)
    ? confidence.placeholder_input_files
    : [];
  const fallbackExchangeUsed = Boolean(confidence && confidence.fallback_exchange_used);
  const surrogateFallbackUsed = Boolean(confidence && confidence.surrogate_fallback_used);
  return (
    <div className="card">
      <h3 style={{ marginTop: 0, fontSize: 15 }}>Run-level diagnostics</h3>
      <div className="muted" style={{ fontSize: 12 }}>
        Scenario-wide diagnostics that do not change with map filtering.
      </div>
      <div className="row muted" style={{ marginTop: 8, fontSize: 12 }}>
        <span>Coupling mode: <code>{String((confidence && confidence.coupling_mode) || "unknown")}</code></span>
        <span>Mapping coverage: {formatSharePercent(toNumber(confidence && confidence.mapping_coverage_share), 1)}</span>
        <span>Fallback mapping: {formatSharePercent(toNumber(confidence && confidence.fallback_mapping_share), 1)}</span>
        <span>Fallback exchange: <code>{fallbackExchangeUsed ? "yes" : "no"}</code></span>
        <span>Surrogate fallback: <code>{surrogateFallbackUsed ? "yes" : "no"}</code></span>
        <span>Placeholder rows: <code>{toNumber(confidence && confidence.placeholder_input_row_count, 0)}</code></span>
        <span>Reliability penalty method: <code>{String((confidence && confidence.reliability_penalty_method) || "-")}</code></span>
        <span>VOLL: <code>{compact(confidence && confidence.value_of_lost_load_usd_per_mwh)}</code></span>
        <span>Import leakage method: <code>{String((confidence && confidence.import_leakage_method) || "-")}</code></span>
      </div>
      {placeholderInputFiles.length ? (
        <div className="warn" style={{ marginTop: 8, marginBottom: 0, fontSize: 12 }}>
          Placeholder expert datasets detected: <code>{placeholderInputFiles.join(", ")}</code>
        </div>
      ) : (
        <div className="ok" style={{ marginTop: 8, marginBottom: 0, fontSize: 12 }}>
          No placeholder expert input files are listed in this run diagnostic payload.
        </div>
      )}
      {fallbackExchangeUsed && confidence && confidence.fallback_exchange_source ? (
        <div className="warn" style={{ marginTop: 8, marginBottom: 0, fontSize: 12 }}>
          Exchange shocks used fallback allocation from <code>{String(confidence.fallback_exchange_source)}</code>.
        </div>
      ) : null}
      {surrogateFallbackUsed && confidence && confidence.surrogate_fallback_reason ? (
        <div className="warn" style={{ marginTop: 8, marginBottom: 0, fontSize: 12 }}>
          Development outputs fell back to surrogate mode: {String(confidence.surrogate_fallback_reason)}
        </div>
      ) : null}
    </div>
  );
}

function ModelQualityCard({ modelQuality, confidence }) {
  const qualityStatus = String((modelQuality && modelQuality.status) || "").trim().toLowerCase();
  const qualityScore = toNumber(modelQuality && modelQuality.score, 0);
  const qualityIssues = Array.isArray(modelQuality && modelQuality.issues) ? modelQuality.issues : [];
  const qualityDiagnostics = (modelQuality && modelQuality.diagnostics) || {};
  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ marginTop: 0, fontSize: 15, marginBottom: 0 }}>Model quality</h3>
        {qualityStatus ? <span className={displayStatus(qualityStatus).className}>{displayStatus(qualityStatus).label}</span> : null}
      </div>
      <div className="row" style={{ gap: 10, marginTop: 8 }}>
        <MetricCard label="Quality score" value={String(Math.round(qualityScore))} />
        <MetricCard
          label="Mapping coverage"
          value={formatSharePercent(toNumber(confidence && confidence.mapping_coverage_share), 1)}
        />
        <MetricCard
          label="Energy balance gap"
          value={formatSharePercent(toNumber(qualityDiagnostics.energy_balance_gap_share), 2)}
        />
        <MetricCard
          label="CO2 method gap"
          value={formatSharePercent(toNumber(qualityDiagnostics.emissions_method_gap_share), 2)}
        />
      </div>
      {modelQuality && modelQuality.summary ? (
        <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          {String(modelQuality.summary)}
        </div>
      ) : null}
      {qualityIssues.length ? (
        <div style={{ display: "grid", gap: 6, marginTop: 8 }}>
          {qualityIssues.map((row, idx) => {
            const sev = normalizeStatus(row && row.severity);
            return (
              <div
                key={`quality-issue-${idx}`}
                style={{
                  border: "1px solid #233754",
                  borderRadius: 8,
                  padding: "8px 10px",
                  background: sev === "error" ? "#261318" : "#0b1323",
                }}
              >
                <div className="row" style={{ justifyContent: "space-between", gap: 8 }}>
                  <div style={{ fontWeight: 700, fontSize: 12 }}>{String((row && row.code) || "issue")}</div>
                  <span className={displayStatus(sev).className}>{displayStatus(sev).label}</span>
                </div>
                <div className="muted" style={{ fontSize: 11, marginTop: 3 }}>{String((row && row.message) || "")}</div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          No quality issues were synthesized for this run.
        </div>
      )}
    </div>
  );
}

function MetricResolutionCard({ metricResolution }) {
  const resolutionRows = Array.isArray(metricResolution && metricResolution.records)
    ? metricResolution.records
    : [];
  return (
    <div className="card">
      <h3 style={{ marginTop: 0, fontSize: 15 }}>Metric resolution</h3>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        This shows the model-native unit for each major metric and what the filtered UI can safely show.
      </div>
      {resolutionRows.length ? (
        <div style={{ display: "grid", gap: 6 }}>
          {resolutionRows.map((row) => (
            <div
              key={`resolution-${String(row.metric_key || row.label)}`}
              style={{ border: "1px solid #233754", borderRadius: 8, padding: "8px 10px", background: "#0b1323" }}
            >
              <div style={{ fontWeight: 700, fontSize: 12 }}>{String(row.label || row.metric_key || "-")}</div>
              <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
                Native: <code>{humanizeResolution(row.native_resolution)}</code> | Filtered UI: <code>{humanizeResolution(row.filtered_resolution)}</code>
              </div>
              {row.notes ? (
                <div className="muted" style={{ fontSize: 11, marginTop: 3 }}>{String(row.notes)}</div>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <div className="muted">Metric resolution metadata was not recorded for this run.</div>
      )}
    </div>
  );
}

function DevelopmentUncertaintyCard({ developmentUncertainty }) {
  const uncertaintyBounds =
    developmentUncertainty &&
    developmentUncertainty.totals_bounds &&
    typeof developmentUncertainty.totals_bounds === "object"
      ? developmentUncertainty.totals_bounds
      : null;
  return (
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
  );
}

function ScenarioAssumptionsCard({ scenarioAssumptions, confidence }) {
  const assumptionsCount = toNumber(confidence && confidence.scenario_assumptions_applied_count, 0);
  const rows = Array.isArray(scenarioAssumptions && scenarioAssumptions.records)
    ? scenarioAssumptions.records
    : [];
  return (
    <div className="card">
      <h3 style={{ marginTop: 0, fontSize: 15 }}>Scenario assumptions</h3>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        Matched rows applied to integrated indicators: <code>{assumptionsCount}</code>
      </div>
      {rows.length ? (
        <div style={{ display: "grid", gap: 6 }}>
          {rows.map((row) => (
            <div
              key={`assumption-${String(row.assumption_key)}`}
              style={{ border: "1px solid #233754", borderRadius: 8, padding: "8px 10px", background: "#0b1323" }}
            >
              <div style={{ fontWeight: 700, fontSize: 12 }}>{String(row.assumption_key || "-")}</div>
              <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
                {String(row.value || row.value_numeric || "-")} {String(row.unit || "")} · scenario <code>{String(row.scenario_key || "-")}</code> · source <code>{String(row.source || "-")}</code>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="muted">No matched scenario assumptions were recorded for this run.</div>
      )}
    </div>
  );
}

function ScenarioProvenanceCard({ scenarioPackage, confidence }) {
  const energy = (scenarioPackage && scenarioPackage.energy) || {};
  const mrio = (scenarioPackage && scenarioPackage.mrio_direct) || {};
  const alignment = (scenarioPackage && scenarioPackage.geography_alignment) || {};
  const report = (mrio && mrio.report_source) || {};
  return (
    <div className="card">
      <h3 style={{ marginTop: 0, fontSize: 15 }}>Integrated scenario provenance</h3>
      <div className="row" style={{ gap: 10 }}>
        <MetricCard label="Energy scenario" value={String((scenarioPackage && scenarioPackage.energy_scenario_key) || energy.scenario_key || "-")} />
        <MetricCard label="Target scenario" value={String((scenarioPackage && scenarioPackage.mrio_scenario_id) || "-")} />
        <MetricCard label="Target year" value={String((scenarioPackage && scenarioPackage.target_year) || "-")} />
        <MetricCard label="Alignment" value={String(alignment.status || "-")} />
      </div>
      <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
        Report source: <code>{String(report.source_file || "-")}</code>
      </div>
      {alignment.notes ? (
        <div className={String(alignment.status || "") === "mrio_only" ? "warn" : "ok"} style={{ marginTop: 8 }}>
          {String(alignment.notes)}
        </div>
      ) : null}
      <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
        Selected totals source: <code>{String(confidence && confidence.selected_totals_source || "-")}</code>
      </div>
    </div>
  );
}

function SourceChannelsCard({ sourceChannels }) {
  const bridge = (sourceChannels && sourceChannels.bridge) || {};
  const direct = (sourceChannels && sourceChannels.mrio_direct) || {};
  const selected = (sourceChannels && sourceChannels.selected_totals) || {};
  const combined = (sourceChannels && sourceChannels.combined_totals) || {};
  const overlap = (sourceChannels && sourceChannels.overlap_diagnostics) || {};
  const directInputs = (direct && direct.inputs) || {};
  const bridgeInputs = (bridge && bridge.inputs) || {};
  const bridgeShockTotal = toNumber(
    bridgeInputs.total_shock_musd,
    toNumber(bridgeInputs.investment_shock_total_musd) + toNumber(bridgeInputs.operating_shock_total_musd)
  );
  const directShockCount = toNumber(
    overlap.mrio_direct_rows,
    toNumber(directInputs && directInputs.diagnostics && directInputs.diagnostics.shock_row_count, 0)
  );
  const directNetShock = toNumber(directInputs && directInputs.totals && directInputs.totals.net_direct_shock_musd, 0);
  return (
    <div className="card">
      <h3 style={{ marginTop: 0, fontSize: 15 }}>Bridge vs MRIO-direct channels</h3>
      {overlap.message ? <div className="warn" style={{ marginTop: 0 }}>{String(overlap.message)}</div> : null}
      <div className="row" style={{ gap: 10, marginTop: 10 }}>
        <MetricCard label="Bridge shock (MUSD)" value={compact(bridgeShockTotal)} />
        <MetricCard label="MRIO direct rows" value={String(directShockCount)} />
        <MetricCard label="MRIO direct net shock" value={compact(directNetShock)} />
        <MetricCard label="Selected jobs" value={compact(toNumber(selected.jobs_total, 0))} />
        <MetricCard label="Combined jobs diagnostic" value={compact(toNumber(combined.jobs_total, 0))} />
      </div>
      <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
        MRIO-direct method: <code>{String(direct.method || "-")}</code>. Headline metrics currently default to bridge-derived Calliope values on overlap.
      </div>
    </div>
  );
}

function DevelopmentIndicatorsCard({ developmentIndicators, confidence }) {
  const indicatorAvailableCount = toNumber(confidence && confidence.development_indicators_available_count, 0);
  const indicatorUnavailableCount = toNumber(confidence && confidence.development_indicators_unavailable_count, 0);
  const rows = Array.isArray(developmentIndicators && developmentIndicators.records)
    ? developmentIndicators.records
    : [];
  return (
    <div className="card">
      <h3 style={{ marginTop: 0, fontSize: 15 }}>Development indicators</h3>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        Available: <code>{indicatorAvailableCount}</code> · Unavailable: <code>{indicatorUnavailableCount}</code>
      </div>
      {rows.length ? (
        <div style={{ display: "grid", gap: 6 }}>
          {rows.map((row) => {
            const available = String(row.status || "").toLowerCase() === "available";
            return (
              <div
                key={`indicator-${String(row.indicator_id)}`}
                style={{ border: "1px solid #233754", borderRadius: 8, padding: "8px 10px", background: "#0b1323" }}
              >
                <div className="row" style={{ justifyContent: "space-between", gap: 8 }}>
                  <div style={{ fontWeight: 700, fontSize: 12 }}>{String(row.indicator_name || row.indicator_id || "-")}</div>
                  <div className="muted" style={{ fontSize: 11 }}>
                    {available ? compact(toNumber(row.value, 0)) : "Unavailable"}
                    {row.unit ? ` ${String(row.unit)}` : ""}
                  </div>
                </div>
                {!available && row.reason ? (
                  <div className="muted" style={{ fontSize: 11, marginTop: 3 }}>{String(row.reason)}</div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="muted">No development indicators were recorded for this run.</div>
      )}
    </div>
  );
}

function SpatialResultsMapPanel({
  mapData,
  mapMetric,
  setMapMetric,
  loading,
  loadError,
  developmentByRegionRecords,
  spatialFilter,
  setSpatialFilter,
}) {
  const mapHostRef = useRef(null);
  const mapRef = useRef(null);
  const layerRef = useRef(null);
  const fittedRunRef = useRef("");

  const metricMeta = LOCATION_MAP_METRICS.find((item) => item.key === mapMetric) || LOCATION_MAP_METRICS[0];
  const regionLookup = useMemo(
    () => buildRegionLookup(developmentByRegionRecords),
    [developmentByRegionRecords]
  );

  function getFeatureInfo(feature) {
    const resolved = resolveFeatureRecord(feature, mapData);
    const locationId = extractGeoFeatureLocationId(feature);
    const props = (feature && feature.properties) || {};
    const regionFromRecord = resolved && resolved.record ? String(resolved.record.region || "").trim() : "";
    const regionFallback = firstNonEmpty(props, ["mario_region", "region"]);
    const region = regionFromRecord || regionFallback;
    const regionKey = normalizeRegionKey(region);
    const regionRow = regionKey && regionLookup.has(regionKey) ? regionLookup.get(regionKey) : null;
    const countryIso3 =
      normalizeLocationId(firstNonEmpty(props, ["country_iso3", "iso3", "ISO_A3"])) ||
      locationToParentCountry(locationId);
    return {
      resolved,
      locationId,
      region,
      regionKey,
      regionRow,
      countryIso3,
      label: getGeoFeatureLabel(feature),
      metricValue: metricValueForFeature(resolved, metricMeta.key, regionLookup),
      totalShock: toNumber(resolved && resolved.record && resolved.record.total_shock_musd, NaN),
      capexShock: toNumber(resolved && resolved.record && resolved.record.capex_shock_musd, NaN),
      opexShock: toNumber(resolved && resolved.record && resolved.record.opex_shock_musd, NaN),
      syntheticSubregionArea: Boolean(props.synthetic_subregion_area),
      placeholderGeometry: Boolean(props.placeholder_geometry || (mapData && mapData.coverage && mapData.coverage.placeholderGeojson)),
      syntheticMethod: String(props.synthetic_method || "").trim(),
    };
  }

  function selectionMatchStrength(info) {
    if (!spatialFilter) return "none";
    const selectedLocation = normalizeLocationId(spatialFilter.locationId);
    const selectedCountry = normalizeLocationId(
      spatialFilter.countryIso3 || locationToParentCountry(selectedLocation)
    );
    const selectedRegion = normalizeRegionKey(spatialFilter.region);

    const featureLocation = normalizeLocationId(info && info.locationId);
    const featureCountry = normalizeLocationId(
      (info && info.countryIso3) || locationToParentCountry(featureLocation)
    );
    const featureRegion = normalizeRegionKey(info && info.region);

    if (selectedLocation) {
      if (isSubregionLocation(selectedLocation)) {
        if (featureLocation === selectedLocation) return "strong";
      } else if (
        featureLocation === selectedLocation ||
        locationToParentCountry(featureLocation) === selectedLocation ||
        featureCountry === selectedLocation
      ) {
        return "strong";
      }
    } else if (
      selectedCountry &&
      (featureCountry === selectedCountry || locationToParentCountry(featureLocation) === selectedCountry)
    ) {
      return "strong";
    }

    if (selectedRegion && featureRegion && selectedRegion === featureRegion) return "weak";
    return "none";
  }

  const mapSummary = useMemo(() => {
    const features = Array.isArray(mapData && mapData.geojson && mapData.geojson.features)
      ? mapData.geojson.features
      : [];
    let matchedByLocation = 0;
    let matchedByRegion = 0;
    let unmatched = 0;
    const metricValues = [];

    features.forEach((feature) => {
      const info = getFeatureInfo(feature);
      if (info.resolved.source === "location") matchedByLocation += 1;
      else if (info.resolved.source === "region") matchedByRegion += 1;
      else unmatched += 1;
      const value = info.metricValue;
      if (Number.isFinite(value)) metricValues.push(value);
    });

    const minValue = metricValues.length ? Math.min(...metricValues) : NaN;
    const maxValue = metricValues.length ? Math.max(...metricValues) : NaN;
    const histogramBins = buildMapHistogramBins(metricValues, minValue, maxValue, 18);

    return {
      featureCount: features.length,
      matchedByLocation,
      matchedByRegion,
      unmatched,
      minValue,
      maxValue,
      metricValueCount: metricValues.length,
      histogramBins,
    };
  }, [mapData, metricMeta.key, regionLookup]);

  const selectedFeatureInfo = useMemo(() => {
    if (!spatialFilter || !mapData || !mapData.geojson || !Array.isArray(mapData.geojson.features)) return null;
    const selectedLocation = normalizeLocationId(spatialFilter.locationId);
    const selectedCountry = normalizeLocationId(
      spatialFilter.countryIso3 || locationToParentCountry(selectedLocation)
    );
    const selectedRegion = normalizeRegionKey(spatialFilter.region);
    let feature =
      mapData.geojson.features.find((row) => extractGeoFeatureLocationId(row) === selectedLocation) || null;
    if (!feature && selectedLocation && !isSubregionLocation(selectedLocation)) {
      feature =
        mapData.geojson.features.find((row) => {
          const featureLocation = extractGeoFeatureLocationId(row);
          if (!featureLocation) return false;
          return (
            featureLocation === selectedLocation ||
            locationToParentCountry(featureLocation) === selectedLocation
          );
        }) || null;
    }
    if (!feature && selectedCountry) {
      feature =
        mapData.geojson.features.find((row) => {
          const props = (row && row.properties) || {};
          const featureCountry = normalizeLocationId(
            firstNonEmpty(props, ["country_iso3", "iso3", "ISO_A3"]) ||
              locationToParentCountry(extractGeoFeatureLocationId(row))
          );
          return featureCountry && featureCountry === selectedCountry;
        }) || null;
    }
    if (!feature && selectedRegion) {
      feature =
        mapData.geojson.features.find((row) => {
          const info = getFeatureInfo(row);
          return info.regionKey && info.regionKey === selectedRegion;
        }) || null;
    }
    if (!feature) return null;
    return getFeatureInfo(feature);
  }, [spatialFilter, mapData, mapMetric, regionLookup]);

  function layerBoundsForAvailableData(layer) {
    if (!layer || !window.L) return null;
    const dataBounds = window.L.latLngBounds([]);
    layer.eachLayer((shapeLayer) => {
      const feature = shapeLayer.feature;
      const info = getFeatureInfo(feature);
      if (!Number.isFinite(info.metricValue)) return;
      const bounds = shapeLayer.getBounds ? shapeLayer.getBounds() : null;
      if (bounds && bounds.isValid()) {
        dataBounds.extend(bounds);
      } else if (shapeLayer.getLatLng) {
        dataBounds.extend(shapeLayer.getLatLng());
      }
    });
    if (dataBounds.isValid()) return dataBounds;
    const layerBounds = layer.getBounds ? layer.getBounds() : null;
    return layerBounds && layerBounds.isValid() ? layerBounds : null;
  }

  function fitMapToAvailableData(layer, signature, force = false) {
    const map = mapRef.current;
    if (!map || !layer) return;
    const bounds = layerBoundsForAvailableData(layer);
    if (!bounds || !bounds.isValid()) return;
    map.invalidateSize();
    if (force || fittedRunRef.current !== signature) {
      map.fitBounds(bounds.pad(0.06), { animate: false, maxZoom: 7 });
      fittedRunRef.current = signature;
    }
  }

  useEffect(() => {
    if (!mapHostRef.current || !window.L || mapRef.current) return;
    const map = window.L.map(mapHostRef.current, {
      zoomControl: true,
      attributionControl: false,
    });
    map.setView([4, 20], 3);
    mapRef.current = map;

    return () => {
      if (layerRef.current) {
        layerRef.current.remove();
        layerRef.current = null;
      }
      map.remove();
      mapRef.current = null;
      fittedRunRef.current = "";
    };
  }, []);

  useEffect(() => {
    if (!mapHostRef.current || !mapRef.current || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      const map = mapRef.current;
      if (!map) return;
      window.setTimeout(() => {
        map.invalidateSize();
        if (layerRef.current) fitMapToAvailableData(layerRef.current, fittedRunRef.current || "resize", true);
      }, 0);
    });
    observer.observe(mapHostRef.current);
    return () => observer.disconnect();
  }, [mapData, metricMeta.key, regionLookup]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !window.L) return;
    if (layerRef.current) {
      layerRef.current.remove();
      layerRef.current = null;
    }

    const features = Array.isArray(mapData && mapData.geojson && mapData.geojson.features)
      ? mapData.geojson.features
      : [];
    if (!features.length) return;

    const minValue = mapSummary.minValue;
    const maxValue = mapSummary.maxValue;

    const layer = window.L.geoJSON(mapData.geojson, {
      style: (feature) => {
        const info = getFeatureInfo(feature);
        const value = info.metricValue;
        const hasValue = Number.isFinite(value);
        const matchStrength = selectionMatchStrength(info);
        const isStrongSelection = matchStrength === "strong";
        const isWeakSelection = matchStrength === "weak";
        return {
          color: isStrongSelection ? "#f4e7b6" : isWeakSelection ? "#6f89aa" : "#233754",
          weight: isStrongSelection ? 2.7 : isWeakSelection ? 1.2 : 0.9,
          fillColor: hasValue ? colorForMapValue(value, minValue, maxValue) : "#1a2334",
          fillOpacity: hasValue
            ? isStrongSelection
              ? 0.97
              : isWeakSelection
                ? 0.6
                : 0.86
            : isStrongSelection
              ? 0.36
              : isWeakSelection
                ? 0.24
                : 0.22,
        };
      },
      onEachFeature: (feature, shapeLayer) => {
        const info = getFeatureInfo(feature);
        const sourceLabel = info.resolved.source === "location"
          ? "Matched by location ID"
          : info.resolved.source === "region"
            ? "Matched by region fallback"
            : "No matched model value";
        const jobs = toNumber(info.regionRow && info.regionRow.jobs_total, NaN);
        const gva = toNumber(info.regionRow && info.regionRow.gva_total_musd, NaN);
        const income = toNumber(info.regionRow && info.regionRow.household_income_proxy_musd, NaN);
        const geometryNote = info.placeholderGeometry
          ? "Placeholder geometry"
          : info.syntheticSubregionArea
            ? `Synthetic ${info.syntheticMethod || "subregion"} geometry`
            : "";

        shapeLayer.bindTooltip(
          `<div style="font-size:12px;line-height:1.4;">
             <div style="font-weight:700;margin-bottom:4px;">${escapeHtml(info.label)}</div>
             ${info.locationId ? `<div>Location ID: <code>${escapeHtml(info.locationId)}</code></div>` : ""}
             ${info.region ? `<div>Region: <code>${escapeHtml(info.region)}</code></div>` : ""}
             <div style="margin-top:4px;">${escapeHtml(metricMeta.label)}: <b>${Number.isFinite(info.metricValue) ? escapeHtml(compact(info.metricValue)) : "-"}</b></div>
             <div>Total shock: ${Number.isFinite(info.totalShock) ? escapeHtml(compact(info.totalShock)) : "-"}</div>
             <div>CAPEX: ${Number.isFinite(info.capexShock) ? escapeHtml(compact(info.capexShock)) : "-"}</div>
             <div>OPEX: ${Number.isFinite(info.opexShock) ? escapeHtml(compact(info.opexShock)) : "-"}</div>
             <div>Jobs (region-level): ${Number.isFinite(jobs) ? escapeHtml(compact(jobs)) : "-"}</div>
             <div>GVA (region-level): ${Number.isFinite(gva) ? escapeHtml(compact(gva)) : "-"}</div>
             <div>Income (region-level): ${Number.isFinite(income) ? escapeHtml(compact(income)) : "-"}</div>
             ${geometryNote ? `<div style="margin-top:4px;color:#ffd4a3;">${escapeHtml(geometryNote)}</div>` : ""}
             <div style="margin-top:4px;color:#9bb3d6;">${escapeHtml(sourceLabel)}</div>
           </div>`,
          { sticky: true, direction: "auto", opacity: 0.96 }
        );

        shapeLayer.on({
          click: () => {
            if (!setSpatialFilter) return;
            const currentLocation = normalizeLocationId(spatialFilter && spatialFilter.locationId);
            const nextLocation = normalizeLocationId(info.locationId);
            const currentRegion = normalizeRegionKey(spatialFilter && spatialFilter.region);
            const nextRegion = normalizeRegionKey(info.region);
            if (currentLocation === nextLocation && currentRegion === nextRegion) {
              setSpatialFilter(null);
              return;
            }
            setSpatialFilter({
              locationId: info.locationId || "",
              countryIso3: info.countryIso3 || locationToParentCountry(info.locationId),
              region: info.region || "",
              label: info.label || info.locationId || info.region || "Selection",
            });
          },
          mouseover: (evt) => {
            evt.target.setStyle({ weight: 1.8, color: "#cfe2ff" });
            if (!window.L.Browser.ie && !window.L.Browser.opera && !window.L.Browser.edge) {
              evt.target.bringToFront();
            }
          },
          mouseout: (evt) => {
            if (layerRef.current) layerRef.current.resetStyle(evt.target);
          },
        });
      },
    }).addTo(map);

    layerRef.current = layer;
    const fitSignature = [
      mapData && mapData.runId ? mapData.runId : "no-run",
      metricMeta.key,
      String(mapSummary.featureCount),
      String(mapSummary.matchedByLocation),
      String(mapSummary.matchedByRegion),
    ].join("|");
    window.setTimeout(() => fitMapToAvailableData(layer, fitSignature), 0);
    window.setTimeout(() => fitMapToAvailableData(layer, fitSignature), 160);
  }, [
    mapData,
    mapSummary.featureCount,
    mapSummary.matchedByLocation,
    mapSummary.matchedByRegion,
    mapSummary.minValue,
    mapSummary.maxValue,
    metricMeta,
    regionLookup,
    spatialFilter,
  ]);

  const unmatchedModelLocationIds =
    (mapData && mapData.coverage && mapData.coverage.unmatchedModelLocationIds) || [];
  const unmatchedGeoLocationIds =
    (mapData && mapData.coverage && mapData.coverage.unmatchedGeoLocationIds) || [];
  const syntheticSubregionLocationIds =
    (mapData && mapData.coverage && mapData.coverage.syntheticSubregionLocationIds) || [];
  const placeholderGeometryLocationIds =
    (mapData && mapData.coverage && mapData.coverage.placeholderGeometryLocationIds) || [];

  const locationCount = mapData && mapData.coverage ? toNumber(mapData.coverage.modelLocationCount) : 0;
  const geoFeatureLocationCount = mapData && mapData.coverage ? toNumber(mapData.coverage.geoFeatureLocationCount) : 0;

  return (
    <div className="card" style={{ minWidth: 0 }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-end" }}>
        <div>
          <h3 style={{ marginTop: 0, marginBottom: 2, fontSize: 15 }}>Spatial results map</h3>
          <div className="muted" style={{ fontSize: 12 }}>
            Location metrics are built from <code>investment_shocks.csv</code> and <code>operating_shocks.csv</code>.
            Regional development metrics are joined by region.
          </div>
        </div>
        <div>
          <label>Map metric</label>
          <select value={mapMetric} onChange={(e) => setMapMetric(e.target.value)} style={{ maxWidth: "100%" }}>
            {LOCATION_MAP_METRICS.map((option) => (
              <option key={option.key} value={option.key}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading ? <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>Loading spatial map inputs...</div> : null}
      {loadError ? (
        <div className="warn" style={{ marginTop: 8, marginBottom: 0 }}>
          {loadError}
        </div>
      ) : null}
      {!window.L ? (
        <div className="warn" style={{ marginTop: 8, marginBottom: 0 }}>
          Leaflet did not load, so the map cannot render.
        </div>
      ) : null}

      <div
        ref={mapHostRef}
        style={{
          marginTop: 10,
          width: "100%",
          maxWidth: "100%",
          minHeight: 320,
          height: "min(52vh, 560px)",
          borderRadius: 12,
          border: "1px solid #273a5c",
          overflow: "hidden",
          background: "#0a1220",
        }}
      />

      <div className="row muted" style={{ marginTop: 8, fontSize: 12, gap: 14 }}>
        <span>Model locations: <code>{locationCount}</code></span>
        <span>GeoJSON location IDs: <code>{geoFeatureLocationCount}</code></span>
        <span>Matched by location: <code>{mapSummary.matchedByLocation}</code></span>
        <span>Matched by region fallback: <code>{mapSummary.matchedByRegion}</code></span>
        <span>Unmatched features: <code>{mapSummary.unmatched}</code></span>
        <span>Synthetic subregions: <code>{syntheticSubregionLocationIds.length}</code></span>
        <span>Placeholder geometries: <code>{placeholderGeometryLocationIds.length}</code></span>
      </div>
      {Number.isFinite(mapSummary.minValue) && Number.isFinite(mapSummary.maxValue) ? (
        <div style={{ marginTop: 8 }}>
          <div
            style={{
              height: 10,
              borderRadius: 999,
              border: "1px solid #2d4268",
              background: mapLegendGradient(),
            }}
          />
          <div className="row muted" style={{ marginTop: 4, fontSize: 11, justifyContent: "space-between" }}>
            <span>{compact(mapSummary.minValue)}</span>
            <span>{compact(mapSummary.maxValue)}</span>
          </div>
          {mapSummary.histogramBins.length ? (
            <div style={{ marginTop: 8 }}>
              <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>
                Distribution across mapped features: <code>{mapSummary.metricValueCount}</code>
              </div>
              <div
                aria-label={`Histogram distribution for ${metricMeta.label}`}
                style={{
                  height: 48,
                  display: "grid",
                  gridTemplateColumns: `repeat(${mapSummary.histogramBins.length}, minmax(3px, 1fr))`,
                  gap: 3,
                  alignItems: "end",
                  padding: "5px 6px",
                  border: "1px solid #223657",
                  borderRadius: 10,
                  background: "#081324",
                }}
              >
                {mapSummary.histogramBins.map((bin, idx) => (
                  <div
                    key={`map-histogram-${idx}`}
                    title={`${compact(bin.min)} to ${compact(bin.max)}: ${bin.count} feature${bin.count === 1 ? "" : "s"}`}
                    style={{
                      height: `${Math.max(2, Math.round(bin.share * 38))}px`,
                      borderRadius: "5px 5px 2px 2px",
                      background: colorForMapValue(bin.midpoint, mapSummary.minValue, mapSummary.maxValue),
                      opacity: bin.count > 0 ? 0.95 : 0.22,
                    }}
                  />
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
          No mapped values were found for the selected metric.
        </div>
      )}
      {selectedFeatureInfo ? (
        <div
          style={{
            marginTop: 10,
            border: "1px solid #2a3f62",
            background: "#0d172a",
            borderRadius: 10,
            padding: "10px 12px",
          }}
        >
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div style={{ fontWeight: 700, fontSize: 13 }}>
              Selection: {selectedFeatureInfo.label}
            </div>
            <button
              type="button"
              style={{ background: "#22304c", fontSize: 12, padding: "5px 9px" }}
              onClick={() => setSpatialFilter && setSpatialFilter(null)}
            >
              Clear filter
            </button>
          </div>
          <div className="row muted" style={{ marginTop: 6, fontSize: 12, gap: 14 }}>
            {selectedFeatureInfo.locationId ? (
              <span>Location: <code>{selectedFeatureInfo.locationId}</code></span>
            ) : null}
            {selectedFeatureInfo.countryIso3 ? (
              <span>Country: <code>{selectedFeatureInfo.countryIso3}</code></span>
            ) : null}
            {selectedFeatureInfo.region ? (
              <span>Region: <code>{selectedFeatureInfo.region}</code></span>
            ) : null}
            <span>{metricMeta.label}: <code>{Number.isFinite(selectedFeatureInfo.metricValue) ? compact(selectedFeatureInfo.metricValue) : "-"}</code></span>
            {selectedFeatureInfo.syntheticSubregionArea ? (
              <span>Synthetic geometry: <code>{selectedFeatureInfo.syntheticMethod || "yes"}</code></span>
            ) : null}
            {selectedFeatureInfo.placeholderGeometry ? (
              <span>Placeholder geometry: <code>yes</code></span>
            ) : null}
          </div>
          <div className="row muted" style={{ marginTop: 6, fontSize: 12, gap: 14 }}>
            <span>Total shock: <code>{Number.isFinite(selectedFeatureInfo.totalShock) ? compact(selectedFeatureInfo.totalShock) : "-"}</code></span>
            <span>CAPEX: <code>{Number.isFinite(selectedFeatureInfo.capexShock) ? compact(selectedFeatureInfo.capexShock) : "-"}</code></span>
            <span>OPEX: <code>{Number.isFinite(selectedFeatureInfo.opexShock) ? compact(selectedFeatureInfo.opexShock) : "-"}</code></span>
            <span>Jobs (region-level): <code>{Number.isFinite(toNumber(selectedFeatureInfo.regionRow && selectedFeatureInfo.regionRow.jobs_total, NaN)) ? compact(selectedFeatureInfo.regionRow && selectedFeatureInfo.regionRow.jobs_total) : "-"}</code></span>
            <span>GVA (region-level): <code>{Number.isFinite(toNumber(selectedFeatureInfo.regionRow && selectedFeatureInfo.regionRow.gva_total_musd, NaN)) ? compact(selectedFeatureInfo.regionRow && selectedFeatureInfo.regionRow.gva_total_musd) : "-"}</code></span>
            <span>Income (region-level): <code>{Number.isFinite(toNumber(selectedFeatureInfo.regionRow && selectedFeatureInfo.regionRow.household_income_proxy_musd, NaN)) ? compact(selectedFeatureInfo.regionRow && selectedFeatureInfo.regionRow.household_income_proxy_musd) : "-"}</code></span>
          </div>
          <details style={{ marginTop: 6 }}>
            <summary className="muted" style={{ cursor: "pointer", fontSize: 12 }}>
              Raw selection payload
            </summary>
            <pre
              style={{
                marginTop: 6,
                maxHeight: 180,
                overflow: "auto",
                background: "#0a1220",
                border: "1px solid #243551",
                borderRadius: 8,
                padding: 8,
                fontSize: 11,
              }}
            >
              {JSON.stringify(
                {
                  location: selectedFeatureInfo.locationId,
                  country_iso3: selectedFeatureInfo.countryIso3,
                  region: selectedFeatureInfo.region,
                  map_match_source: selectedFeatureInfo.resolved.source,
                  synthetic_subregion_area: selectedFeatureInfo.syntheticSubregionArea,
                  placeholder_geometry: selectedFeatureInfo.placeholderGeometry,
                  map_row: selectedFeatureInfo.resolved.record || null,
                  regional_development_row: selectedFeatureInfo.regionRow || null,
                },
                null,
                2
              )}
            </pre>
          </details>
        </div>
      ) : null}

      {unmatchedModelLocationIds.length ? (
        <details style={{ marginTop: 8 }}>
          <summary className="muted" style={{ cursor: "pointer", fontSize: 12 }}>
            Missing in GeoJSON: {unmatchedModelLocationIds.length} model locations
          </summary>
          <div style={{ marginTop: 6, fontSize: 12 }}>
            <code>{unmatchedModelLocationIds.join(", ")}</code>
          </div>
        </details>
      ) : null}
      {unmatchedGeoLocationIds.length ? (
        <details style={{ marginTop: 8 }}>
          <summary className="muted" style={{ cursor: "pointer", fontSize: 12 }}>
            GeoJSON IDs without model data in this run: {unmatchedGeoLocationIds.length}
          </summary>
          <div style={{ marginTop: 6, fontSize: 12 }}>
            <code>{unmatchedGeoLocationIds.join(", ")}</code>
          </div>
        </details>
      ) : null}
      {syntheticSubregionLocationIds.length ? (
        <details style={{ marginTop: 8 }}>
          <summary className="muted" style={{ cursor: "pointer", fontSize: 12 }}>
            Synthetic subregion geometries: {syntheticSubregionLocationIds.length}
          </summary>
          <div style={{ marginTop: 6, fontSize: 12 }}>
            <code>{syntheticSubregionLocationIds.join(", ")}</code>
          </div>
        </details>
      ) : null}
      {placeholderGeometryLocationIds.length ? (
        <details style={{ marginTop: 8 }}>
          <summary className="muted" style={{ cursor: "pointer", fontSize: 12 }}>
            Placeholder geometries: {placeholderGeometryLocationIds.length}
          </summary>
          <div style={{ marginTop: 6, fontSize: 12 }}>
            <code>{placeholderGeometryLocationIds.join(", ")}</code>
          </div>
        </details>
      ) : null}
      <div className="muted" style={{ marginTop: 8, fontSize: 11 }}>
        GeoJSON source: <code>{LOCATION_MAP_GEOJSON_PATH}</code>. Override with{" "}
        <code>window.EDIM_GEOJSON_PATH</code> before loading the app.
      </div>
      <div className="muted" style={{ marginTop: 4, fontSize: 11 }}>
        Country topology manifest: <code>{LOCATION_MAP_COUNTRIES_MANIFEST_PATH}</code>. Subregions are synthesized from
        model centroid points inside parent-country boundaries.
      </div>
      <div className="muted" style={{ marginTop: 4, fontSize: 11 }}>
        Click any country/subregion to filter other charts where spatial fields are available.
      </div>
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
  modelQuality,
  metricResolution,
  scenarioPackage,
  sourceChannels,
  scenarioAssumptions,
  developmentIndicators,
  developmentUncertainty,
  reliability,
  physicalEmissions,
  systemStructure,
  energyBalance,
  tradeNetRecords,
  emissionsByPool,
  costByComponent,
  developmentByRegion,
  developmentByRegionSupplier,
  developmentBySector,
  developmentMetric,
  setDevelopmentMetric,
  developmentMetricLabel,
  locationMapData,
  locationMapMetric,
  setLocationMapMetric,
  locationMapLoading,
  locationMapError,
  runSpatialTechData,
  runSpatialTechLoading,
  runSpatialTechError,
  spatialFilter,
  setSpatialFilter,
}) {
  const [activeSection, setActiveSection] = useState("overview");
  const [barFilter, setBarFilter] = useState("");
  const [barLimit, setBarLimit] = useState("20");

  const uncertaintyBounds =
    developmentUncertainty &&
    developmentUncertainty.totals_bounds &&
    typeof developmentUncertainty.totals_bounds === "object"
      ? developmentUncertainty.totals_bounds
      : null;
  const rankedLimit = Math.max(5, Math.round(toNumber(barLimit, 20)));
  const baseGenerationByTechRanked = aggregateByLabel(
    ((((result && result.summary) || {}).generation_by_tech || {}).records || []),
    "techs",
    "value"
  );
  const baseCapacityByTechRecords = (((result && result.summary) || {}).capacity_by_tech || {}).records || [];
  const baseLocationRows = Array.isArray(locationMapData && locationMapData.locationRows)
    ? locationMapData.locationRows
    : [];
  const selectionGranularity = useMemo(() => spatialFilterGranularity(spatialFilter), [spatialFilter]);
  const isCountryLikeSelection = selectionGranularity === "country" || selectionGranularity === "subregion";
  const countryLevelSelectionActive = Boolean(spatialFilter) && isCountryLikeSelection;
  const canFilterRegionRows = Boolean(spatialFilter) && !isCountryLikeSelection;
  const canFilterPoolRows = Boolean(spatialFilter) && !isCountryLikeSelection;
  const selectedResultsTitle = useMemo(() => {
    if (!spatialFilter) return "Regional / country / subcountry results";
    if (selectionGranularity === "subregion") return "Selected subcountry results";
    if (selectionGranularity === "country") return "Selected country results";
    if (selectionGranularity === "region") return "Selected regional results";
    if (selectionGranularity === "pool") return "Selected pool results";
    return "Selected area results";
  }, [spatialFilter, selectionGranularity]);
  const selectedDriversTitle = useMemo(() => {
    if (!spatialFilter) return "Regional / country / subcountry drivers";
    if (selectionGranularity === "subregion") return "Selected subcountry drivers";
    if (selectionGranularity === "country") return "Selected country drivers";
    if (selectionGranularity === "region") return "Selected regional drivers";
    if (selectionGranularity === "pool") return "Selected pool drivers";
    return "Selected area drivers";
  }, [spatialFilter, selectionGranularity]);
  const selectedResultsScopeNote = useMemo(() => {
    if (!spatialFilter) return "Choose a country, subcountry, or region on the map to populate this box.";
    const label = spatialFilter.label || spatialFilter.locationId || spatialFilter.region || "selection";
    if (countryLevelSelectionActive) {
      return `Scope: ${label}. Metrics here use the finest compatible resolution; region-only series stay regional.`;
    }
    return `Scope: ${label}. Metrics here are filtered to the selected area.`;
  }, [spatialFilter, countryLevelSelectionActive]);
  const locationRegionLookup = useMemo(() => buildLocationRegionLookup(locationMapData), [locationMapData]);
  const filteredGenerationByTech = useMemo(() => {
    if (!spatialFilter) return baseGenerationByTechRanked;
    const byLocation = runSpatialTechData && runSpatialTechData.generationByLocationTech;
    const rows = aggregateSpatialTechByLocation(byLocation, spatialFilter, locationRegionLookup);
    return rows.length ? rows : baseGenerationByTechRanked;
  }, [spatialFilter, runSpatialTechData, locationRegionLookup, baseGenerationByTechRanked]);
  const filteredCapacityByTech = useMemo(() => {
    if (!spatialFilter) return baseCapacityByTechRecords;
    const byLocation = runSpatialTechData && runSpatialTechData.capacityByLocationTech;
    const rows = aggregateSpatialTechByLocation(byLocation, spatialFilter, locationRegionLookup);
    return rows.length ? rows : baseCapacityByTechRecords;
  }, [spatialFilter, runSpatialTechData, locationRegionLookup, baseCapacityByTechRecords]);
  const filteredLocationShockRows = useMemo(
    () => applySpatialFilterRecords(baseLocationRows, spatialFilter),
    [baseLocationRows, spatialFilter]
  );
  const filteredLocationShockTotals = useMemo(
    () => ({
      totalShockMusd: sumRowsNumeric(filteredLocationShockRows, "total_shock_musd"),
      capexShockMusd: sumRowsNumeric(filteredLocationShockRows, "capex_shock_musd"),
      opexShockMusd: sumRowsNumeric(filteredLocationShockRows, "opex_shock_musd"),
    }),
    [filteredLocationShockRows]
  );
  const filteredMonetaryCost = useMemo(
    () =>
      sumLocationValueMapForFilter(
        runSpatialTechData && runSpatialTechData.monetaryCostByLocation,
        spatialFilter,
        locationRegionLookup
      ),
    [spatialFilter, runSpatialTechData, locationRegionLookup]
  );
  const filteredEmissionsFromLocation = useMemo(
    () =>
      sumLocationValueMapForFilter(
        runSpatialTechData && runSpatialTechData.emissionsByLocation,
        spatialFilter,
        locationRegionLookup
      ),
    [spatialFilter, runSpatialTechData, locationRegionLookup]
  );
  const filteredReliabilityFromLocation = useMemo(() => {
    const demand = sumLocationValueMapForFilter(
      runSpatialTechData && runSpatialTechData.demandByLocation,
      spatialFilter,
      locationRegionLookup
    );
    const unserved = sumLocationValueMapForFilter(
      runSpatialTechData && runSpatialTechData.unservedByLocation,
      spatialFilter,
      locationRegionLookup
    );
    const demandTotal = demand.hasAny ? demand.total : 0;
    const unservedTotal = unserved.hasAny ? unserved.total : 0;
    return {
      demandTotal,
      unservedTotal,
      unservedEnergyShare: demandTotal > 0 ? unservedTotal / demandTotal : 0,
      hasAny: demand.hasAny || unserved.hasAny,
    };
  }, [spatialFilter, runSpatialTechData, locationRegionLookup]);
  const filteredReliabilityDemandRows = useMemo(
    () =>
      canFilterPoolRows
        ? applySpatialFilterRecords(
            (reliability && reliability.demand_by_pool && reliability.demand_by_pool.records) || [],
            spatialFilter
          )
        : (reliability && reliability.demand_by_pool && reliability.demand_by_pool.records) || [],
    [reliability, spatialFilter, canFilterPoolRows]
  );
  const filteredReliabilityUnservedRows = useMemo(
    () =>
      canFilterPoolRows
        ? applySpatialFilterRecords(
            (reliability && reliability.unserved_by_pool && reliability.unserved_by_pool.records) || [],
            spatialFilter
          )
        : (reliability && reliability.unserved_by_pool && reliability.unserved_by_pool.records) || [],
    [reliability, spatialFilter, canFilterPoolRows]
  );
  const filteredReliabilitySummary = useMemo(() => {
    if (spatialFilter && filteredReliabilityFromLocation.hasAny) return filteredReliabilityFromLocation;
    const demandTotal = sumRowsNumeric(filteredReliabilityDemandRows, "value");
    const unservedTotal = sumRowsNumeric(filteredReliabilityUnservedRows, "value");
    return {
      demandTotal,
      unservedTotal,
      unservedEnergyShare: demandTotal > 0 ? unservedTotal / demandTotal : 0,
      hasAny: filteredReliabilityDemandRows.length > 0 || filteredReliabilityUnservedRows.length > 0,
    };
  }, [spatialFilter, filteredReliabilityFromLocation, filteredReliabilityDemandRows, filteredReliabilityUnservedRows]);
  const filteredDevelopmentByRegion = useMemo(
    () => (canFilterRegionRows ? applySpatialFilterRecords(developmentByRegion, spatialFilter) : developmentByRegion),
    [developmentByRegion, spatialFilter, canFilterRegionRows]
  );
  const filteredDevelopmentByRegionSupplierRows = useMemo(() => {
    const regionSupplierRows = Array.isArray(developmentByRegionSupplier)
      ? developmentByRegionSupplier
      : [];
    if (!regionSupplierRows.length) return [];
    return canFilterRegionRows ? applySpatialFilterRecords(regionSupplierRows, spatialFilter) : regionSupplierRows;
  }, [developmentByRegionSupplier, spatialFilter, canFilterRegionRows]);
  const filteredDevelopmentBySector = useMemo(() => {
    if (canFilterRegionRows && filteredDevelopmentByRegionSupplierRows.length) {
      return aggregateByLabel(filteredDevelopmentByRegionSupplierRows, "supplier_sector", developmentMetric);
    }
    return developmentBySector;
  }, [filteredDevelopmentByRegionSupplierRows, developmentBySector, developmentMetric, canFilterRegionRows]);
  const filteredTradeNetRecords = useMemo(
    () => (canFilterPoolRows ? applySpatialFilterRecords(tradeNetRecords, spatialFilter) : tradeNetRecords),
    [tradeNetRecords, spatialFilter, canFilterPoolRows]
  );
  const filteredEmissionsByPoolSummary = useMemo(
    () => (canFilterPoolRows ? applySpatialFilterRecords(emissionsByPool, spatialFilter) : emissionsByPool),
    [emissionsByPool, spatialFilter, canFilterPoolRows]
  );
  const filteredEmissionsByPoolFromLocation = useMemo(() => {
    const byLocation = runSpatialTechData && runSpatialTechData.emissionsByLocation;
    if (!(byLocation instanceof Map) || !byLocation.size) return [];
    const byPool = new Map();
    byLocation.forEach((value, locationId) => {
      if (spatialFilter && !locationMatchesSpatialFilter(locationId, spatialFilter, locationRegionLookup)) return;
      const region = normalizeRegionKey(locationRegionLookup.get(normalizeLocationId(locationId)));
      const inferredPool = inferPoolFromRegion(region) || "UNKNOWN";
      byPool.set(inferredPool, toNumber(byPool.get(inferredPool), 0) + toNumber(value, 0));
    });
    return Array.from(byPool.entries())
      .map(([pool, value]) => ({ pool, value }))
      .sort((a, b) => Math.abs(toNumber(b && b.value)) - Math.abs(toNumber(a && a.value)));
  }, [runSpatialTechData, spatialFilter, locationRegionLookup]);
  const resolvedEmissionsByPool = useMemo(
    () => (filteredEmissionsByPoolFromLocation.length ? filteredEmissionsByPoolFromLocation : filteredEmissionsByPoolSummary),
    [filteredEmissionsByPoolFromLocation, filteredEmissionsByPoolSummary]
  );
  const filteredEmissionsTotal = useMemo(() => {
    if (spatialFilter && filteredEmissionsFromLocation.hasAny) {
      return { total: filteredEmissionsFromLocation.total, hasAny: true };
    }
    const total = sumRowsNumeric(resolvedEmissionsByPool, "value");
    const hasAny = Array.isArray(resolvedEmissionsByPool) && resolvedEmissionsByPool.length > 0;
    return hasAny ? { total, hasAny: true } : { total: NaN, hasAny: false };
  }, [spatialFilter, filteredEmissionsFromLocation, resolvedEmissionsByPool]);
  const filteredDevelopmentJobsTotal = useMemo(
    () => sumRowsNumeric(filteredDevelopmentByRegion, "jobs_total"),
    [filteredDevelopmentByRegion]
  );
  const filteredDevelopmentGvaTotal = useMemo(
    () => sumRowsNumeric(filteredDevelopmentByRegion, "gva_total_musd"),
    [filteredDevelopmentByRegion]
  );
  const filteredImportLeakageMusd = useMemo(() => {
    const sourceRows = filteredDevelopmentByRegionSupplierRows.length
      ? filteredDevelopmentByRegionSupplierRows
      : developmentBySector;
    return (sourceRows || []).reduce((sum, row) => {
      if (!isImportLeakageSectorName(row && row.supplier_sector)) return sum;
      return sum + toNumber(row && row.shock_value_musd, 0);
    }, 0);
  }, [filteredDevelopmentByRegionSupplierRows, developmentBySector]);
  const canApplyDevelopmentTotals = Boolean(spatialFilter) && canFilterRegionRows && filteredDevelopmentByRegion.length > 0;
  const canApplyImportLeakage =
    Boolean(spatialFilter) && canFilterRegionRows && filteredDevelopmentByRegionSupplierRows.length > 0;
  const resolvedIntegratedMetrics = useMemo(() => {
    const rows = Array.isArray(integratedMetrics) ? integratedMetrics : [];
    return rows.map((metric) => {
      const key = String((metric && metric.key) || "");
      let value = toNumber(metric && metric.value, 0);
      if (spatialFilter) {
        if (key === "monetary_cost" && filteredMonetaryCost.hasAny) {
          value = filteredMonetaryCost.total;
        } else if (key === "physical_emissions" && filteredEmissionsTotal.hasAny) {
          value = filteredEmissionsTotal.total;
        } else if (key === "unserved_energy_share" && filteredReliabilitySummary.hasAny) {
          value = filteredReliabilitySummary.unservedEnergyShare;
        } else if (key === "jobs_total" && canApplyDevelopmentTotals) {
          value = filteredDevelopmentJobsTotal;
        } else if (key === "gva_total_musd" && canApplyDevelopmentTotals) {
          value = filteredDevelopmentGvaTotal;
        } else if (key === "import_leakage_musd" && canApplyImportLeakage) {
          value = filteredImportLeakageMusd;
        }
      }
      return { ...(metric || {}), value };
    });
  }, [
    integratedMetrics,
    spatialFilter,
    filteredMonetaryCost,
    filteredEmissionsTotal,
    filteredReliabilitySummary,
    canApplyDevelopmentTotals,
    filteredDevelopmentJobsTotal,
    filteredDevelopmentGvaTotal,
    canApplyImportLeakage,
    filteredImportLeakageMusd,
  ]);
  const displayedDevelopmentDrivers = useMemo(() => {
    if (!spatialFilter) {
      return {
        capex_effect_musd: toNumber(developmentDrivers && developmentDrivers.capex_effect_musd, 0),
        opex_effect_musd: toNumber(developmentDrivers && developmentDrivers.opex_effect_musd, 0),
        reliability_penalty_proxy: toNumber(developmentDrivers && developmentDrivers.reliability_penalty_proxy, 0),
        import_leakage_musd: toNumber(developmentDrivers && developmentDrivers.import_leakage_musd, 0),
      };
    }
    return {
      capex_effect_musd: filteredLocationShockTotals.capexShockMusd,
      opex_effect_musd: filteredLocationShockTotals.opexShockMusd,
      reliability_penalty_proxy: filteredReliabilitySummary.hasAny
        ? filteredReliabilitySummary.unservedTotal
        : toNumber(developmentDrivers && developmentDrivers.reliability_penalty_proxy, 0),
      import_leakage_musd: canApplyImportLeakage
        ? filteredImportLeakageMusd
        : toNumber(developmentDrivers && developmentDrivers.import_leakage_musd, 0),
    };
  }, [
    spatialFilter,
    developmentDrivers,
    filteredLocationShockTotals,
    filteredReliabilitySummary,
    canApplyImportLeakage,
    filteredImportLeakageMusd,
  ]);
  const displayedReliability = useMemo(() => {
    if (!spatialFilter) {
      return {
        demandTotal: toNumber(reliability && reliability.demand_total, 0),
        unservedTotal: toNumber(reliability && reliability.unserved_total, 0),
        unservedEnergyShare: toNumber(reliability && reliability.unserved_energy_share, 0),
      };
    }
    if (!filteredReliabilitySummary.hasAny) {
      return {
        demandTotal: toNumber(reliability && reliability.demand_total, 0),
        unservedTotal: toNumber(reliability && reliability.unserved_total, 0),
        unservedEnergyShare: toNumber(reliability && reliability.unserved_energy_share, 0),
      };
    }
    return filteredReliabilitySummary;
  }, [spatialFilter, reliability, filteredReliabilitySummary]);
  const globalDevelopmentDrivers = useMemo(
    () => ({
      capex_effect_musd: toNumber(developmentDrivers && developmentDrivers.capex_effect_musd, 0),
      opex_effect_musd: toNumber(developmentDrivers && developmentDrivers.opex_effect_musd, 0),
      reliability_penalty_proxy: toNumber(developmentDrivers && developmentDrivers.reliability_penalty_proxy, 0),
      import_leakage_musd: toNumber(developmentDrivers && developmentDrivers.import_leakage_musd, 0),
    }),
    [developmentDrivers]
  );
  const placeholderInputFiles = Array.isArray(confidence && confidence.placeholder_input_files)
    ? confidence.placeholder_input_files
    : [];
  const qualityStatus = String((modelQuality && modelQuality.status) || "").trim().toLowerCase();
  const qualityScore = toNumber(modelQuality && modelQuality.score, 0);
  const qualityIssues = Array.isArray(modelQuality && modelQuality.issues) ? modelQuality.issues : [];
  const qualityDiagnostics = (modelQuality && modelQuality.diagnostics) || {};
  const resolutionRows = Array.isArray(metricResolution && metricResolution.records)
    ? metricResolution.records
    : [];
  const fallbackExchangeUsed = Boolean(confidence && confidence.fallback_exchange_used);
  const surrogateFallbackUsed = Boolean(confidence && confidence.surrogate_fallback_used);
  const assumptionsCount = toNumber(confidence && confidence.scenario_assumptions_applied_count, 0);
  const indicatorAvailableCount = toNumber(confidence && confidence.development_indicators_available_count, 0);
  const indicatorUnavailableCount = toNumber(confidence && confidence.development_indicators_unavailable_count, 0);
  const scenarioAssumptionRows = Array.isArray(scenarioAssumptions && scenarioAssumptions.records)
    ? scenarioAssumptions.records
    : [];
  const developmentIndicatorRows = Array.isArray(developmentIndicators && developmentIndicators.records)
    ? developmentIndicators.records
    : [];
  const sectionTabs = [
    { key: "overview", label: "Overview" },
    { key: "system", label: "Energy system" },
    { key: "development", label: "Development" },
    { key: "method", label: "Method" },
  ];

  if (!result) return null;

  return (
    <div className="analysis-shell">
      <div className="card analysis-header-card">
        <div className="row" style={{ justifyContent: "space-between", gap: 12 }}>
          <div>
            <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", color: "#8ea4c5" }}>
              Run results workspace
            </div>
            <div style={{ marginTop: 4, fontWeight: 700, fontSize: 18 }}>
              {selectedRunLabel || "Selected run"} <code>{result.artifacts.run_id}</code>
            </div>
          </div>
          <div className="row">
            <a href={toApiUrl(result.artifacts.csv_url)} target="_blank" rel="noreferrer">Results CSV</a>
            {exchangeArtifacts.report_markdown ? (
              <a href={toApiUrl(exchangeArtifacts.report_markdown)} target="_blank" rel="noreferrer">Run report</a>
            ) : null}
            {exchangeArtifacts.exchange_bundle_zip ? (
              <a href={toApiUrl(exchangeArtifacts.exchange_bundle_zip)} target="_blank" rel="noreferrer">Exchange bundle ZIP</a>
            ) : null}
          </div>
        </div>
        <div className="row muted" style={{ fontSize: 12 }}>
          <span>Solver: {runMetadata.solver || "-"}</span>
          <span>Termination: {runMetadata.termination_condition || "-"}</span>
          <span>Solve time: {runMetadata.solution_time_seconds != null ? `${toNumber(runMetadata.solution_time_seconds).toFixed(2)} s` : "-"}</span>
          <span>Objective: {runMetadata.objective_function_value != null ? compact(runMetadata.objective_function_value) : "-"}</span>
          <span>Spatial filter: <code>{spatialFilter ? spatialFilter.label || spatialFilter.locationId || spatialFilter.region || "-" : "none"}</code></span>
        </div>
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
        {result.summary && result.summary.warnings && result.summary.warnings.length ? (
          <details style={{ marginTop: 4 }}>
            <summary style={{ cursor: "pointer", fontWeight: 700 }}>Run warnings ({result.summary.warnings.length})</summary>
            <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
              {result.summary.warnings.map((w, i) => (
                <li key={i} style={{ marginBottom: 4 }}>{w}</li>
              ))}
            </ul>
          </details>
        ) : null}
      </div>

      <div className="analysis-section-body">
        {activeSection === "overview" ? (
          <div className="dashboard-stack">
            <div className="workspace-map-grid">
              <div className="dashboard-stack">
                <SpatialResultsMapPanel
                  mapData={locationMapData}
                  mapMetric={locationMapMetric}
                  setMapMetric={setLocationMapMetric}
                  loading={locationMapLoading}
                  loadError={locationMapError}
                  developmentByRegionRecords={developmentByRegion}
                  spatialFilter={spatialFilter}
                  setSpatialFilter={setSpatialFilter}
                />
                {spatialFilter ? (
                  <div className="card" style={{ marginTop: 0 }}>
                    <div className="row" style={{ justifyContent: "space-between" }}>
                      <div className="muted" style={{ fontSize: 12 }}>
                        Spatial filter is active for mappable datasets: <code>{spatialFilter.label || spatialFilter.locationId || spatialFilter.region || "-"}</code>
                      </div>
                      <button
                        type="button"
                        style={{ background: "#22304c", fontSize: 12, padding: "6px 10px" }}
                        onClick={() => setSpatialFilter && setSpatialFilter(null)}
                      >
                        Clear spatial filter
                      </button>
                    </div>
                    {countryLevelSelectionActive ? (
                      <div className="muted" style={{ marginTop: 8, fontSize: 11 }}>
                        Country/subregion selection applies strict unit alignment. Region/pool-only series stay at their native resolution.
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>

              <div className="workspace-side-stack">
                <div className="card">
                  <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                    <h3 style={{ marginTop: 0, fontSize: 15, marginBottom: 0 }}>Global final results</h3>
                    <span className="muted" style={{ fontSize: 11 }}>Run-wide</span>
                  </div>
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
                  <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                    These values are global outputs for the full model run and do not change with map selection.
                  </div>
                </div>

                <div
                  className="card"
                  style={{
                    border: "1px solid #38527e",
                    background: "linear-gradient(180deg, rgba(19,33,54,0.96) 0%, rgba(11,22,37,0.96) 100%)",
                  }}
                >
                  <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                    <h3 style={{ marginTop: 0, fontSize: 15, marginBottom: 0 }}>{selectedResultsTitle}</h3>
                    <span className="muted" style={{ fontSize: 11 }}>
                      {spatialFilter ? "Map-filtered" : "Awaiting selection"}
                    </span>
                  </div>
                  {spatialFilter && resolvedIntegratedMetrics.length ? (
                    <div className="row" style={{ gap: 12 }}>
                      {resolvedIntegratedMetrics.map((m) => (
                        <MetricCard
                          key={`selected-${String(m.key)}`}
                          label={`${String(m.label)} (${String(m.unit)})`}
                          value={compact(toNumber(m.value))}
                        />
                      ))}
                    </div>
                  ) : (
                    <div className="muted">Select a country, subcountry, or region on the map to view scoped final results.</div>
                  )}
                  <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                    {selectedResultsScopeNote}
                  </div>
                  {spatialFilter && runSpatialTechLoading ? (
                    <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                      Loading location-level cost details from <code>results.csv</code>...
                    </div>
                  ) : null}
                  {spatialFilter && runSpatialTechError ? (
                    <div className="warn" style={{ marginTop: 8, marginBottom: 0 }}>
                      {runSpatialTechError}
                    </div>
                  ) : null}
                </div>

	                <div className="card">
	                  <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
	                    <h3 style={{ marginTop: 0, fontSize: 15, marginBottom: 0 }}>Global development drivers</h3>
	                    <span className="muted" style={{ fontSize: 11 }}>Run-wide</span>
	                  </div>
	                  <div className="row" style={{ gap: 10 }}>
	                    <MetricCard label="CAPEX effect (MUSD)" value={compact(globalDevelopmentDrivers.capex_effect_musd)} />
	                    <MetricCard label="OPEX effect (MUSD)" value={compact(globalDevelopmentDrivers.opex_effect_musd)} />
	                    <MetricCard label="Reliability penalty (MUSD)" value={compact(globalDevelopmentDrivers.reliability_penalty_proxy)} />
	                  </div>
	                  <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
	                    Global development drivers are derived from the full run summary. Import leakage is reported with final results.
	                  </div>
	                </div>

                <div
                  className="card"
                  style={{
                    border: "1px solid #38527e",
                    background: "linear-gradient(180deg, rgba(19,33,54,0.96) 0%, rgba(11,22,37,0.96) 100%)",
                  }}
                >
                  <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                    <h3 style={{ marginTop: 0, fontSize: 15, marginBottom: 0 }}>{selectedDriversTitle}</h3>
                    <span className="muted" style={{ fontSize: 11 }}>
                      {spatialFilter ? "Map-filtered" : "Awaiting selection"}
                    </span>
                  </div>
	                  {spatialFilter ? (
	                    <>
	                      <div className="row" style={{ gap: 10 }}>
	                        <MetricCard label="CAPEX effect (MUSD)" value={compact(displayedDevelopmentDrivers.capex_effect_musd)} />
	                        <MetricCard label="OPEX effect (MUSD)" value={compact(displayedDevelopmentDrivers.opex_effect_musd)} />
	                        <MetricCard label="Reliability penalty (MUSD)" value={compact(displayedDevelopmentDrivers.reliability_penalty_proxy)} />
	                        <MetricCard label="Total shock (MUSD)" value={compact(filteredLocationShockTotals.totalShockMusd)} />
	                      </div>
                      <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                        Spatial filter is active; values use the finest compatible resolution available for each metric.
                      </div>
                    </>
                  ) : (
                    <div className="muted">Select a country, subcountry, or region on the map to compare scoped drivers against the global run.</div>
                  )}
                </div>
              </div>
            </div>

            <div className="workspace-grid-2">
              <RunDiagnosticsCard confidence={confidence} />
              <ModelQualityCard modelQuality={modelQuality} confidence={confidence} />
            </div>

            <DevelopmentUncertaintyCard developmentUncertainty={developmentUncertainty} />
          </div>
        ) : null}

        {activeSection === "system" ? (
          <div className="dashboard-stack">
            <div className="workspace-grid-2">
              <div className="card">
                <h3 style={{ marginTop: 0, fontSize: 15 }}>Generation by technology</h3>
                <RankedBars
                  records={filteredGenerationByTech}
                  labelKey="techs"
                  valueKey="value"
                  emptyMessage="No generation records for this run."
                  limit={rankedLimit}
                  filterText={barFilter}
                />
                {spatialFilter && runSpatialTechLoading ? (
                  <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                    Preparing location-filtered generation from <code>results.csv</code>...
                  </div>
                ) : null}
                {spatialFilter && runSpatialTechError ? (
                  <div className="warn" style={{ marginTop: 8, marginBottom: 0 }}>
                    {runSpatialTechError}
                  </div>
                ) : null}
                <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                  Values are aggregated across all model timesteps.
                </div>
              </div>

              <div className="card">
                <h3 style={{ marginTop: 0, fontSize: 15 }}>Capacity (energy_cap)</h3>
                <RankedBars
                  records={filteredCapacityByTech}
                  labelKey="techs"
                  valueKey="value"
                  emptyMessage="No capacity records for this run."
                  limit={rankedLimit}
                  filterText={barFilter}
                />
                {spatialFilter && runSpatialTechLoading ? (
                  <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                    Preparing location-filtered capacity from <code>results.csv</code>...
                  </div>
                ) : null}
              </div>
            </div>

            <div className="workspace-grid-2">
              <div className="card">
                <h3 style={{ marginTop: 0, fontSize: 15 }}>Reliability snapshot</h3>
                <div className="row" style={{ gap: 18 }}>
                  <MetricCard label="Demand total" value={compact(displayedReliability.demandTotal)} />
                  <MetricCard label="Unserved total" value={compact(displayedReliability.unservedTotal)} />
                  <MetricCard label="Unserved share" value={`${(toNumber(displayedReliability.unservedEnergyShare) * 100).toFixed(3)}%`} />
                </div>
                {spatialFilter ? (
                  <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                    Reliability uses location-level demand/unserved from <code>results.csv</code> when available, otherwise pool diagnostics.
                  </div>
                ) : null}
              </div>

              <div className="card">
                <h3 style={{ marginTop: 0, fontSize: 15 }}>Inter-pool trade balance</h3>
                <RankedBars
                  records={filteredTradeNetRecords}
                  labelKey="pool"
                  valueKey="value"
                  emptyMessage="No inter-pool transmission balance data."
                  limit={rankedLimit}
                  filterText={barFilter}
                />
                {countryLevelSelectionActive ? (
                  <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                    This is net pool trade balance (exports minus imports). It stays pool-level and does not downscale to individual countries.
                  </div>
                ) : null}
              </div>
            </div>

            <div className="workspace-grid-2">
              <div className="card">
                <h3 style={{ marginTop: 0, fontSize: 15 }}>Physical emissions by pool</h3>
                <RankedBars
                  records={resolvedEmissionsByPool}
                  labelKey="pool"
                  valueKey="value"
                  emptyMessage="No physical emissions records for this run."
                  limit={rankedLimit}
                  filterText={barFilter}
                />
                {countryLevelSelectionActive ? (
                  <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                    Pool bars are rebuilt from direct location-level CO2 totals where available; otherwise they remain on the native pool diagnostic.
                  </div>
                ) : null}
              </div>

              <div className="dashboard-stack">
                <div className="card">
                  <h3 style={{ marginTop: 0, fontSize: 15 }}>System structure</h3>
                  <div className="row" style={{ gap: 10 }}>
                    <MetricCard label="Renewable generation share" value={formatSharePercent(systemStructure && systemStructure.renewable_generation_share, 1)} />
                    <MetricCard label="Zero-carbon generation share" value={formatSharePercent(systemStructure && systemStructure.zero_carbon_generation_share, 1)} />
                    <MetricCard label="Fossil generation share" value={formatSharePercent(systemStructure && systemStructure.fossil_generation_share, 1)} />
                    <MetricCard label="Generation total" value={compact(systemStructure && systemStructure.generation_total)} />
                    <MetricCard label="Capacity total" value={compact(systemStructure && systemStructure.capacity_total)} />
                  </div>
                  <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
                    Technology groups are heuristic reporting buckets derived from Calliope technology names.
                  </div>
                </div>

                <div className="card">
                  <h3 style={{ marginTop: 0, fontSize: 15 }}>Emissions and energy balance</h3>
                  <div className="row" style={{ gap: 10 }}>
                    <MetricCard label="Physical emissions" value={compact(physicalEmissions && physicalEmissions.total_emissions)} />
                    <MetricCard label="CO2 method" value={String((physicalEmissions && physicalEmissions.method) || "-")} />
                    <MetricCard label="CO2 factor coverage" value={formatSharePercent(physicalEmissions && physicalEmissions.factor_coverage_share, 1)} />
                    <MetricCard label="Max pool balance gap" value={formatSharePercent(energyBalance && energyBalance.max_abs_balance_gap_share, 2)} />
                  </div>
                  <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
                    Emissions prefer direct <code>cost[costs=co2]</code> accounting when the run exposes it. Pool balance checks whether generation, trade, demand, and unserved energy reconcile cleanly.
                  </div>
                  {Array.isArray(energyBalance && energyBalance.records) && energyBalance.records.length ? (
                    <div style={{ marginTop: 10, overflowX: "auto" }}>
                      <table className="panel-table">
                        <thead>
                          <tr>
                            <th>Pool</th>
                            <th>Generation</th>
                            <th>Demand</th>
                            <th>Net imports</th>
                            <th>Balance gap</th>
                          </tr>
                        </thead>
                        <tbody>
                          {energyBalance.records.slice(0, 8).map((row) => (
                            <tr key={`balance-${String(row.pool)}`}>
                              <td>{String(row.pool || "-")}</td>
                              <td>{compact(row.generation)}</td>
                              <td>{compact(row.demand)}</td>
                              <td>{compact(row.net_imports)}</td>
                              <td>{compact(row.balance_gap)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : null}
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
            </div>
          </div>
        ) : null}

        {activeSection === "development" ? (
          <div className="dashboard-stack">
            <div className="workspace-grid-2">
              <div className="card">
                <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                  <h3 style={{ marginTop: 0, fontSize: 15, marginBottom: 0 }}>Development drivers</h3>
                  <span className="muted" style={{ fontSize: 11 }}>
                    {spatialFilter ? "Map-filtered when possible" : "Run-wide"}
                  </span>
	                </div>
	                <div className="row" style={{ gap: 10 }}>
	                  <MetricCard label="CAPEX effect (MUSD)" value={compact(displayedDevelopmentDrivers.capex_effect_musd)} />
	                  <MetricCard label="OPEX effect (MUSD)" value={compact(displayedDevelopmentDrivers.opex_effect_musd)} />
	                  <MetricCard label="Reliability penalty (MUSD)" value={compact(displayedDevelopmentDrivers.reliability_penalty_proxy)} />
	                  {spatialFilter ? <MetricCard label="Total shock (MUSD)" value={compact(filteredLocationShockTotals.totalShockMusd)} /> : null}
	                </div>
	                <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
	                  Development remains region-coupled unless explicit country/subregional coefficients are provided. Import leakage is reported with final results.
	                </div>
              </div>

              <DevelopmentUncertaintyCard developmentUncertainty={developmentUncertainty} />
            </div>

            <div className="workspace-grid-2">
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
                  records={filteredDevelopmentByRegion}
                  labelKey="region"
                  valueKey={developmentMetric}
                  limit={rankedLimit}
                  filterText={barFilter}
                  emptyMessage="No development-by-region records for this run."
                />
                <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                  Value shown: {developmentMetricLabel}
                </div>
                {countryLevelSelectionActive ? (
                  <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                    Development impacts are modeled at region level and are not split to country/subregion without explicit subregional coefficients.
                  </div>
                ) : null}
              </div>

              <div className="card">
                <h3 style={{ marginTop: 0, fontSize: 15 }}>Development impacts by supplier sector</h3>
                <RankedBars
                  records={filteredDevelopmentBySector}
                  labelKey="supplier_sector"
                  valueKey={developmentMetric}
                  limit={rankedLimit}
                  filterText={barFilter}
                  emptyMessage="No development-by-sector records for this run."
                />
                <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                  Value shown: {developmentMetricLabel}
                </div>
                {countryLevelSelectionActive ? (
                  <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                    Supplier-sector impacts are region-coupled in current outputs.
                  </div>
                ) : null}
              </div>
            </div>

            <div className="workspace-grid-2">
              <ScenarioAssumptionsCard scenarioAssumptions={scenarioAssumptions} confidence={confidence} />
              <DevelopmentIndicatorsCard developmentIndicators={developmentIndicators} confidence={confidence} />
            </div>
          </div>
        ) : null}

        {activeSection === "method" ? (
          <div className="dashboard-stack">
            <div className="workspace-grid-2">
              <ScenarioProvenanceCard scenarioPackage={scenarioPackage} confidence={confidence} />
              <SourceChannelsCard sourceChannels={sourceChannels} />
            </div>
            <div className="workspace-grid-2">
              <MetricResolutionCard metricResolution={metricResolution} />
              <RunDiagnosticsCard confidence={confidence} />
            </div>
            <div className="workspace-grid-2">
              <ModelQualityCard modelQuality={modelQuality} confidence={confidence} />
              <div className="card">
                <h3 style={{ marginTop: 0, fontSize: 15 }}>System structure and emissions method</h3>
                <div className="row" style={{ gap: 10 }}>
                  <MetricCard label="Renewable generation share" value={formatSharePercent(systemStructure && systemStructure.renewable_generation_share, 1)} />
                  <MetricCard label="CO2 method" value={String((physicalEmissions && physicalEmissions.method) || "-")} />
                  <MetricCard label="CO2 source" value={String((physicalEmissions && physicalEmissions.source_variable) || "-")} />
                  <MetricCard label="Max pool balance gap" value={formatSharePercent(energyBalance && energyBalance.max_abs_balance_gap_share, 2)} />
                </div>
                <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
                  Use this tab to understand which outputs are direct model values and which are derived or region-coupled.
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function RecentJobsPanel({ jobs, selectedJobId, onSelectJob, style = null, limit = 12 }) {
  return (
    <div className="card" style={{ marginTop: 14, ...(style || {}) }}>
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
                <th>Energy scenario</th>
                <th>Run ID</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {jobs.slice(0, limit).map((j) => {
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
                  <td>{(j.request && j.request.energy_scenario_key) || "-"}</td>
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

function AnalysisCanvasInfoModal({ onClose }) {
  return (
    <Modal title="Analysis canvas" subtitle="Mission control guide" onClose={onClose} wide={true}>
      <div className="dashboard-stack">
        <div className="muted" style={{ fontSize: 13 }}>
          The analysis canvas is the center results workspace. It stays separate from the command rail and operations
          rail so users can configure, run, monitor, and interpret without scrolling through a single long page.
        </div>
        <div className="workspace-grid-3">
          <div className="dashboard-note">
            <div style={{ fontWeight: 700, fontSize: 13 }}>1. Configure</div>
            <div className="muted" style={{ marginTop: 4, fontSize: 12 }}>
              Use the scenario definition rail to select the energy pathway, MRIO report scenario, target year, and
              levers, then review readiness diagnostics and placeholder inventory.
            </div>
          </div>
          <div className="dashboard-note">
            <div style={{ fontWeight: 700, fontSize: 13 }}>2. Queue and monitor</div>
            <div className="muted" style={{ marginTop: 4, fontSize: 12 }}>
              Environment setup stays collapsed by default. Open details only when you need to diagnose readiness,
              queue, solver, mapping, placeholder, or data issues.
            </div>
          </div>
          <div className="dashboard-note">
            <div style={{ fontWeight: 700, fontSize: 13 }}>3. Interrogate outputs</div>
            <div className="muted" style={{ marginTop: 4, fontSize: 12 }}>
              After a run completes, the center workspace exposes overview, energy system, development, and method
              tabs with map-based filtering where metric resolution allows it.
            </div>
          </div>
        </div>
        <div className="card" style={{ marginTop: 0 }}>
          <h3 style={{ marginTop: 0, fontSize: 15 }}>What appears in the center workspace</h3>
          <div style={{ display: "grid", gap: 6 }}>
            <div className="dashboard-note">Overview: map-first results, global vs selected metrics, uncertainty, and model quality.</div>
            <div className="dashboard-note">Energy system: generation, capacity, reliability, trade balance, emissions, and system structure.</div>
            <div className="dashboard-note">Development: region/sector impacts, uncertainty, scenario assumptions, and indicator outputs.</div>
            <div className="dashboard-note">Method: metric resolution, coupling diagnostics, source-channel comparison, and quality context.</div>
          </div>
        </div>
      </div>
    </Modal>
  );
}

function DashboardHeader({
  runViewMode,
  onRunViewModeChange,
  hasResult,
}) {
  return (
    <div className="app-header">
      <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.09em", color: "#8ea4c5" }}>
        Modeling Dashboard
      </div>
      <h1 className="header-title">Integrated energy-development dashboard</h1>
      <div className="muted" style={{ marginTop: 6, fontSize: 13, maxWidth: 760 }}>
        United Nations Development Programme
      </div>
      <div className="app-nav-row">
        <div className="app-nav segmented-control">
          <button
            type="button"
            className={runViewMode === "setup" ? "seg-button active" : "seg-button"}
            onClick={() => onRunViewModeChange("setup")}
          >
            Diagram setup
          </button>
          <button
            type="button"
            className={runViewMode === "results" ? "seg-button active" : "seg-button"}
            onClick={() => onRunViewModeChange("results")}
            disabled={!hasResult}
          >
            Results mode
          </button>
        </div>
      </div>
    </div>
  );
}

function EmptyAnalysisWorkspace({
  selectedScenario,
  scenarioKey,
  environmentSetup,
  activeJob,
  hasResult,
}) {
  return (
    <div className="dashboard-empty">
      <div className="dashboard-empty-hero">
        <div className="card">
          <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", color: "#8ea4c5" }}>
            Run results workspace
          </div>
          <h2 style={{ marginTop: 8, marginBottom: 8, fontSize: 22 }}>
            {hasResult ? "Select a run to inspect results." : "Run a scenario to populate the dashboard."}
          </h2>
          <div className="muted" style={{ fontSize: 13, maxWidth: 720 }}>
            This workspace is designed around one loop: choose a scenario, validate readiness, queue a run, then inspect
            global and spatial outputs in the center canvas while keeping operations visible.
          </div>
          <div className="workspace-grid-3" style={{ marginTop: 12 }}>
            <div className="dashboard-note">
              <div style={{ fontWeight: 700, fontSize: 13 }}>1. Configure</div>
              <div className="muted" style={{ marginTop: 4, fontSize: 12 }}>
                Use the command rail to select the scenario family, tune the levers, and choose the run profile.
              </div>
            </div>
            <div className="dashboard-note">
              <div style={{ fontWeight: 700, fontSize: 13 }}>2. Validate and run</div>
              <div className="muted" style={{ marginTop: 4, fontSize: 12 }}>
                Environment checks tell you whether the data and coupling path are clean enough for the requested run.
              </div>
            </div>
            <div className="dashboard-note">
              <div style={{ fontWeight: 700, fontSize: 13 }}>3. Interrogate outputs</div>
              <div className="muted" style={{ marginTop: 4, fontSize: 12 }}>
                Once a run completes, the canvas switches to a tabbed dashboard for overview, system, development, and method analysis.
              </div>
            </div>
          </div>
        </div>

        <div className="dashboard-stack">
          <div className="card">
            <h3 style={{ marginTop: 0, fontSize: 15 }}>Current session</h3>
            <div className="row" style={{ gap: 10 }}>
              <MetricCard
                label="Scenario"
                value={selectedScenario && selectedScenario.title ? selectedScenario.title : scenarioKey || "None"}
              />
              <MetricCard
                label="Environment"
                value={environmentSetup ? (environmentSetup.ok ? "Ready" : "Needs action") : "Checking"}
              />
              <MetricCard
                label="Active job"
                value={activeJob ? displayStatus(activeJob.status).label : "Idle"}
              />
            </div>
            <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
              The app stays in a dashboard shell even before the first run, so you can assess readiness without scrolling through setup and results panels.
            </div>
          </div>
          <div className="card">
            <h3 style={{ marginTop: 0, fontSize: 15 }}>What will appear here</h3>
            <div className="muted" style={{ fontSize: 12 }}>
              After a successful run, this center panel becomes a fixed analysis workspace with:
            </div>
            <div style={{ display: "grid", gap: 6, marginTop: 10 }}>
              <div className="dashboard-note">Overview: map-first results, global vs selected metrics, uncertainty, and model quality.</div>
              <div className="dashboard-note">Energy system: generation, capacity, reliability, trade balance, emissions, and system structure.</div>
              <div className="dashboard-note">Development: region/sector impacts, uncertainty, scenario assumptions, and indicator outputs.</div>
              <div className="dashboard-note">Method: metric resolution, coupling diagnostics, source channels, and quality context.</div>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0, fontSize: 15 }}>Architecture and model flow</h3>
	        <div className="muted" style={{ fontSize: 12 }}>
	          The model structure and data-flow reference now lives in the Architecture tab with the interactive system
	          diagram, including separate user/scenario input streams, the unified adapter layer, Energy Model static inputs,
	          MRIO input datasets, and direct Energy-Model-to-results flow.
	        </div>
      </div>
    </div>
  );
}

function runStageIndex(stage) {
  const idx = RUN_STAGE_ORDER.indexOf(normalizeStatus(stage));
  return idx >= 0 ? idx : 0;
}

function architectureBoxStatus(box, activeJob, result) {
  if (result && !activeJob) {
    return {
      state: box.type === "input" ? "loaded" : "completed",
      label: box.type === "input" ? "Loaded" : "Completed",
      icon: "✓",
    };
  }
  if (!activeJob) {
    return { state: "ready", label: "Ready", icon: "✓" };
  }
  const status = normalizeStatus(activeJob.status);
  if (status === "queued") return { state: "pending", label: "Pending", icon: "…" };
  if (status === "failed") return { state: "failed", label: "Failed", icon: "!" };
  if (status === "cancelled") return { state: "failed", label: "Cancelled", icon: "!" };

  const currentIdx = runStageIndex(activeJob.stage || "scenario_prepare");
  const stageIndexes = (box.stages || []).map(runStageIndex).filter((idx) => idx >= 0);
  const minIdx = Math.min(...stageIndexes);
  const maxIdx = Math.max(...stageIndexes);
  if (currentIdx > maxIdx) {
    return {
      state: box.type === "input" ? "loaded" : "completed",
      label: box.type === "input" ? "Loaded" : "Completed",
      icon: "✓",
    };
  }
  if (currentIdx >= minIdx && currentIdx <= maxIdx) {
    return {
      state: "running",
      label: box.type === "input" ? "Loading" : "Running",
      icon: "●",
    };
  }
  return { state: "pending", label: "Pending", icon: "…" };
}

function ArchitectureStatusPill({ status }) {
  return (
    <span className={`arch-status-pill ${status.state}`}>
      <span aria-hidden="true">{status.icon}</span>
      {status.label}
    </span>
  );
}

function ArchitectureBox({ box, activeJob, result, children, featured = false }) {
  const status = architectureBoxStatus(box, activeJob, result);
  return (
    <section className={`arch-live-box ${box.type} ${status.state}${featured ? " featured" : ""}`}>
      <div className="arch-live-box-glow" aria-hidden="true" />
      <div className="arch-live-box-header">
        <div>
          <div className="arch-live-type">{box.type}</div>
          <h3>{box.title}</h3>
          <p>{box.subtitle}</p>
        </div>
        <ArchitectureStatusPill status={status} />
      </div>
      <div className="arch-live-box-body">{children}</div>
      {status.state === "pending" ? <div className="arch-live-overlay">Pending</div> : null}
    </section>
  );
}

function buildArchitectureNodeStatuses(activeJob, result) {
  const boxById = new Map(ARCHITECTURE_BOXES.map((box) => [box.id, box]));
  const nodeStatuses = {};
  Object.entries(ARCHITECTURE_NODE_BOX_MAP).forEach(([nodeId, boxId]) => {
    const box = boxById.get(boxId);
    if (!box) return;
    const status = architectureBoxStatus(box, activeJob, result);
    nodeStatuses[nodeId] = status;
  });
  return {
    overallStatus: activeJob ? "Run in progress" : result ? "Final results ready" : "Ready to run",
    nodeStatuses,
  };
}

function D3ArchitectureCore({ activeJob, result, children }) {
  const iframeRef = useRef(null);
  const architectureState = useMemo(
    () => buildArchitectureNodeStatuses(activeJob, result),
    [activeJob && activeJob.status, activeJob && activeJob.stage, result && result.artifacts && result.artifacts.run_id]
  );

  function postState() {
    const frame = iframeRef.current;
    if (!frame || !frame.contentWindow) return;
    frame.contentWindow.postMessage({ type: "EDIM_ARCHITECTURE_STATE", state: architectureState }, "*");
  }

  useEffect(() => {
    postState();
    const timer = window.setTimeout(postState, 160);
    return () => window.clearTimeout(timer);
  }, [architectureState]);

  return (
    <div className="d3-architecture-core">
      <iframe
        ref={iframeRef}
        className="d3-architecture-frame"
        title="EDIM D3 system architecture diagram"
        src="./architecture.html"
        onLoad={postState}
      />
      <div className="d3-architecture-control-layer">{children}</div>
    </div>
  );
}

function D3OverlayPanel({ area, title, children }) {
  return (
    <section className={`d3-overlay-panel ${area}`}>
      {title ? <div className="d3-overlay-title">{title}</div> : null}
      {children}
    </section>
  );
}

function flowSlotOffset(index, total, spacing = 28) {
  if (!Number.isFinite(index) || !Number.isFinite(total) || total <= 1) return 0;
  return (index - (total - 1) / 2) * spacing;
}

function flowSideFor(source, target) {
  const sx = source.x + source.w / 2;
  const sy = source.y + source.h / 2;
  const tx = target.x + target.w / 2;
  const ty = target.y + target.h / 2;
  const dx = tx - sx;
  const dy = ty - sy;
  const xRatio = Math.abs(dx) / Math.max(1, source.w / 2);
  const yRatio = Math.abs(dy) / Math.max(1, source.h / 2);
  if (xRatio > yRatio) return dx >= 0 ? "right" : "left";
  return dy >= 0 ? "bottom" : "top";
}

function flowAnchor(node, side, offset = 0) {
  if (side === "bottom") return { x: node.x + node.w / 2 + offset, y: node.y + node.h };
  if (side === "top") return { x: node.x + node.w / 2 + offset, y: node.y };
  if (side === "left") return { x: node.x, y: node.y + node.h / 2 + offset };
  return { x: node.x + node.w, y: node.y + node.h / 2 + offset };
}

function flowNormal(side) {
  if (side === "bottom") return { x: 0, y: 1 };
  if (side === "top") return { x: 0, y: -1 };
  if (side === "left") return { x: -1, y: 0 };
  return { x: 1, y: 0 };
}

function flowEdgePath(from, to, sourceSide, targetSide, sourceOffset = 0, targetOffset = 0) {
  const start = flowAnchor(from, sourceSide, sourceOffset);
  const end = flowAnchor(to, targetSide, targetOffset);
  const sourceNormal = flowNormal(sourceSide);
  const targetNormal = flowNormal(targetSide);
  const distance = Math.max(70, Math.min(180, Math.hypot(end.x - start.x, end.y - start.y) * 0.32));
  const c1 = { x: start.x + sourceNormal.x * distance, y: start.y + sourceNormal.y * distance };
  const c2 = { x: end.x + targetNormal.x * distance, y: end.y + targetNormal.y * distance };
  return `M ${start.x} ${start.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${end.x} ${end.y}`;
}

function FlowEdgeLayer({ positions, edges, canvas }) {
  const canvasSize = canvas || DEFAULT_FLOW_CANVAS_SIZE;
  return (
    <svg
      className="flow-edge-layer"
      width={canvasSize.width}
      height={canvasSize.height}
      viewBox={`0 0 ${canvasSize.width} ${canvasSize.height}`}
      aria-hidden="true"
    >
      <defs>
        <marker id="flow-arrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="strokeWidth">
          <path d="M 0 0 L 12 6 L 0 12 z" fill="#67e8f9" opacity="0.82" />
        </marker>
      </defs>
      {(edges || DEFAULT_FLOW_EDGES).map((edge) => {
        const edgeRows = edges || DEFAULT_FLOW_EDGES;
        const from = positions[edge.from];
        const to = positions[edge.to];
        if (!from || !to) return null;
        const sourceSide = flowSideFor(from, to);
        const targetSide = flowSideFor(to, from);
        const outgoing = edgeRows.filter((row) => {
          const rowFrom = positions[row.from];
          const rowTo = positions[row.to];
          return row.from === edge.from && rowFrom && rowTo && flowSideFor(rowFrom, rowTo) === sourceSide;
        });
        const incoming = edgeRows.filter((row) => {
          const rowFrom = positions[row.from];
          const rowTo = positions[row.to];
          return row.to === edge.to && rowFrom && rowTo && flowSideFor(rowTo, rowFrom) === targetSide;
        });
        const sourceOffset = flowSlotOffset(outgoing.indexOf(edge), outgoing.length);
        const targetOffset = flowSlotOffset(incoming.indexOf(edge), incoming.length);
        const start = flowAnchor(from, sourceSide, sourceOffset);
        const end = flowAnchor(to, targetSide, targetOffset);
        const labelX = (start.x + end.x) / 2;
        const labelY = (start.y + end.y) / 2 - 8;
        return (
          <g key={`${edge.from}-${edge.to}`}>
            <path className="flow-edge" d={flowEdgePath(from, to, sourceSide, targetSide, sourceOffset, targetOffset)} markerEnd="url(#flow-arrow)" />
            <text className="flow-edge-label" x={labelX} y={labelY}>{edge.label}</text>
          </g>
        );
      })}
    </svg>
  );
}

function FlowNode({
  box,
  rect,
  status,
  expanded,
  dragging,
  fixed,
  onToggle,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  onMeasure,
  children,
}) {
  const nodeRef = useRef(null);
  const nodeStyle = { left: rect.x, top: rect.y, width: rect.w };
  if (!fixed) nodeStyle.minHeight = expanded ? rect.h : 0;

  useEffect(() => {
    const element = nodeRef.current;
    if (!element || typeof onMeasure !== "function") return undefined;

    function publishSize() {
      onMeasure({
        w: Math.round(element.offsetWidth || rect.w),
        h: Math.round(element.offsetHeight || rect.h),
      });
    }

    publishSize();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(() => publishSize());
    observer.observe(element);
    return () => observer.disconnect();
  }, [expanded, rect.h, rect.w, onMeasure]);

  const collapsedSummary = (
    <div className="flow-node-summary">
      <div>{box.subtitle}</div>
      <div className="flow-node-hint">{fixed ? "Fixed run-definition band." : "Expand for controls and data."}</div>
    </div>
  );
  return (
    <section
      ref={nodeRef}
      className={`flow-node node-${box.id} ${box.type} ${status.state} ${expanded ? "expanded" : "collapsed"} ${dragging ? "dragging" : ""} ${fixed ? "fixed" : ""}`}
      style={nodeStyle}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <div className="flow-node-glimmer" aria-hidden="true" />
      <div className="flow-node-header" onPointerDown={onPointerDown}>
        <div>
          <div className="flow-node-type">{box.type}</div>
          <h3>{box.title}</h3>
          {!expanded ? <p>{box.subtitle}</p> : null}
        </div>
        <div className="flow-node-actions">
          <ArchitectureStatusPill status={status} />
          <button type="button" className="flow-node-toggle" onClick={onToggle}>
            {expanded ? "Collapse" : "Expand"}
          </button>
        </div>
      </div>
      <div className="flow-node-body">{expanded ? children : collapsedSummary}</div>
      {status.state === "pending" ? <div className="flow-node-overlay">Pending</div> : null}
    </section>
  );
}

function FlowModelCanvas({
  activeJob,
  result,
  scenarioControls,
  operationsPanel,
  calliopeDatasets,
  mrioDatasets,
  selectedRunId,
  exchangeArtifacts,
  onUploadDataset,
  statusMessage,
}) {
  const [flowDefinition, setFlowDefinition] = useState(() => defaultFlowDefinition());
  const [positions, setPositions] = useState(() => defaultFlowDefinition().nodes);
  const [measuredNodes, setMeasuredNodes] = useState({});
  const [expandedNodes, setExpandedNodes] = useState({ scenario: true, operations: true });
  const [draggingId, setDraggingId] = useState("");
  const dragRef = useRef(null);
  const fixedNodeSet = useMemo(() => new Set(flowDefinition.fixedNodes || []), [flowDefinition.fixedNodes]);
  const boxById = useMemo(() => {
    const rows = ARCHITECTURE_BOXES.map((box) => [box.id, box]);
    return new Map(rows);
  }, []);

  const orderedNodeIds = flowDefinition.order || DEFAULT_FLOW_NODE_ORDER;
  const edgePositions = useMemo(() => {
    const rows = {};
    orderedNodeIds.forEach((id) => {
      if (!positions[id]) return;
      rows[id] = { ...positions[id], ...(measuredNodes[id] || {}) };
    });
    return rows;
  }, [orderedNodeIds, positions, measuredNodes]);

  useEffect(() => {
    let cancelled = false;
    async function loadFlowDefinition() {
      try {
        const response = await fetch("./architecture.spec.json", { cache: "no-store" });
        if (!response.ok) return;
        const spec = await response.json();
        const nextDefinition = normalizeMainUiFlow(spec && spec.mainUiFlow);
        if (cancelled) return;
        setFlowDefinition(nextDefinition);
        setPositions(nextDefinition.nodes);
      } catch (_) {
        // The default definition keeps the UI usable if the spec file cannot be fetched.
      }
    }
    loadFlowDefinition();
    return () => {
      cancelled = true;
    };
  }, []);

  function toggleNode(id) {
    setExpandedNodes((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  function handleNodeMeasure(id, size) {
    if (!size || !Number.isFinite(size.w) || !Number.isFinite(size.h)) return;
    setMeasuredNodes((prev) => {
      const current = prev[id];
      if (current && current.w === size.w && current.h === size.h) return prev;
      return { ...prev, [id]: size };
    });
  }

  function startDrag(event, id) {
    if (fixedNodeSet.has(id)) return;
    if (event.button !== 0) return;
    if (event.target && event.target.closest && event.target.closest("button, input, select, textarea, a, label")) return;
    const rect = positions[id];
    if (!rect) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      id,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: rect.x,
      originY: rect.y,
    };
    setDraggingId(id);
  }

  function moveDrag(event) {
    const drag = dragRef.current;
    if (!drag) return;
    const canvas = flowDefinition.canvas || DEFAULT_FLOW_CANVAS_SIZE;
    const nextX = Math.max(12, Math.min(canvas.width - 280, drag.originX + event.clientX - drag.startX));
    const nextY = Math.max(12, Math.min(canvas.height - 110, drag.originY + event.clientY - drag.startY));
    setPositions((prev) => ({
      ...prev,
      [drag.id]: { ...prev[drag.id], x: nextX, y: nextY },
    }));
  }

  function endDrag(event) {
    const drag = dragRef.current;
    if (drag && event.currentTarget && event.currentTarget.hasPointerCapture && event.currentTarget.hasPointerCapture(drag.pointerId)) {
      event.currentTarget.releasePointerCapture(drag.pointerId);
    }
    dragRef.current = null;
    setDraggingId("");
  }

  function renderNodeBody(id) {
    if (id === "scenario") return scenarioControls;
    if (id === "operations") return operationsPanel;
    if (id === "calliope_data") {
      return (
        <>
          <div className="diagram-note" style={{ marginBottom: 10 }}>
            Static energy-model data includes technology definitions, network/topology files, demand and resource time
            series, and model metadata. These datasets go directly into the Energy Model rather than through the adapter.
          </div>
          <DatasetRows datasets={calliopeDatasets} onUpload={onUploadDataset} />
        </>
      );
    }
    if (id === "mrio_data") {
      return (
        <>
          <div className="diagram-note" style={{ marginBottom: 10 }}>
            Core MRIO inputs include employment, GVA, supplier-sector coefficients, uncertainty parameters, geography
            mappings, and other development-accounting datasets used directly by the MRIO runtime.
          </div>
          <DatasetRows datasets={mrioDatasets} onUpload={onUploadDataset} />
        </>
      );
    }
    if (id === "outputs") {
      return (
        <>
          <div className="diagram-note" style={{ marginBottom: 10 }}>
            <div><b>Downloadables:</b> integrated results, scenario package, manifests, shock files, bridge artifacts, and diagnostics.</div>
            <div style={{ marginTop: 6 }}><b>Displayed results:</b> the results workspace separates global outputs from spatially filterable outputs and keeps source-channel provenance visible.</div>
          </div>
          <OutputRows runId={selectedRunId} exchangeArtifacts={exchangeArtifacts} />
        </>
      );
    }
    if (id === "adapter") {
      return (
        <div className="diagram-note">
          <div><b>Role:</b> Resolves user selections against scenario source data, then writes model-specific run inputs.</div>
          <div style={{ marginTop: 6 }}><b>Energy outputs:</b> runtime patch, resolved scenario key, lever mappings, and <code>scenario/energy_input_manifest.json</code>.</div>
          <div style={{ marginTop: 6 }}><b>MRIO outputs:</b> direct shock payloads plus <code>scenario/mrio_direct_inputs.json</code> and <code>scenario/mrio_direct_shocks.csv</code>.</div>
          <div style={{ marginTop: 6 }}><b>Audit artifact:</b> <code>scenario_package.json</code> persists both user-defined parameters and source scenario references.</div>
        </div>
      );
    }
    if (id === "calliope") {
      return (
        <div className="diagram-note">
          <div><b>Inputs:</b> static technology/topology/time-series data plus the adapter-resolved runtime patch.</div>
          <div style={{ marginTop: 6 }}><b>Outputs:</b> capacity, generation, cost, reliability, emissions, trade, and spatial energy balances.</div>
          <div style={{ marginTop: 6 }}><b>Routing:</b> solved outputs feed both the bridge and integrated results directly for energy-side headline metrics.</div>
          <div style={{ marginTop: 6 }}><b>Engine status:</b> Calliope is executable now; OSeMOSYS remains selectable but not runnable yet.</div>
        </div>
      );
    }
    if (id === "bridge") {
      return (
        <div className="diagram-note">
          <div><b>Purpose:</b> Translate solved energy-model outputs into MRIO-ready exchange artifacts.</div>
          <div style={{ marginTop: 6 }}><b>Channels written:</b> investment, operating, fuel, emissions, and price/tax shocks.</div>
          <div style={{ marginTop: 6 }}><b>Current policy:</b> bridge-derived values remain the default headline source when they overlap with MRIO-direct effects.</div>
        </div>
      );
    }
    if (id === "mrio") {
      return (
        <div className="diagram-note">
          <div><b>Inputs:</b> bridge artifacts, adapter-derived MRIO shocks, and the core MRIO coefficient/input datasets.</div>
          <div style={{ marginTop: 6 }}><b>Outputs:</b> jobs, GVA, household income proxy, supplier-sector impacts, uncertainty, and source-channel diagnostics.</div>
          <div style={{ marginTop: 6 }}><b>Interpretation:</b> where explicit country/subregional coefficients are absent, impacts remain region-coupled.</div>
        </div>
      );
    }
    return null;
  }

  return (
    <div className="flow-model-shell">
      <div className="flow-model-toolbar">
        <div>
          <div className="flow-model-eyebrow">Draggable model graph</div>
          <div className="flow-model-title">Configure the run inside the data-flow diagram</div>
        </div>
        <div className="row flow-model-controls">
          {statusMessage ? <div className="flow-inline-status ok">{statusMessage}</div> : null}
          <button type="button" onClick={() => setPositions(flowDefinition.nodes)}>Reset layout</button>
          <button
            type="button"
            onClick={() => setExpandedNodes((prev) => {
              const allExpanded = orderedNodeIds.every((id) => prev[id]);
              return Object.fromEntries(orderedNodeIds.map((id) => [id, !allExpanded]));
            })}
          >
            {orderedNodeIds.every((id) => expandedNodes[id]) ? "Collapse all" : "Expand all"}
          </button>
        </div>
      </div>
      <div className="flow-model-viewport">
        <div className="flow-model-canvas" style={{ width: flowDefinition.canvas.width, height: flowDefinition.canvas.height }}>
          <FlowEdgeLayer positions={edgePositions} edges={flowDefinition.edges} canvas={flowDefinition.canvas} />
          {orderedNodeIds.map((id) => {
            const box = boxById.get(id);
            const rect = positions[id];
            if (!box || !rect) return null;
            const status = architectureBoxStatus(box, activeJob, result);
            return (
              <FlowNode
                key={id}
                box={box}
                rect={rect}
                status={status}
                expanded={Boolean(expandedNodes[id])}
                dragging={draggingId === id}
                fixed={fixedNodeSet.has(id)}
                onToggle={() => toggleNode(id)}
                onPointerDown={(event) => startDrag(event, id)}
                onPointerMove={moveDrag}
                onPointerUp={endDrag}
                onMeasure={(size) => handleNodeMeasure(id, size)}
              >
                {renderNodeBody(id)}
              </FlowNode>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function DiagramScenarioControls({
  scenarios,
  scenarioKey,
  targetScenarios,
  mrioShockMappings,
  mrioScenarioId,
  targetYears,
  targetYear,
  energyModelEngine,
  selectorModel,
  scenarioSelections,
  selectedScenario,
  levers,
  runProfile,
  environmentSetup,
  environmentSetupLoading,
  running,
  queueSubmitting,
  aiPrompt,
  setAiPrompt,
  onApplyAiPrompt,
  aiQueryResult,
  onScenarioChange,
  onMrioScenarioChange,
  onTargetYearChange,
  onEnergyModelEngineChange,
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
  const selectedTargetScenario = (targetScenarios || []).find((s) => s.scenario_id === mrioScenarioId) || null;
  const shockMapping = (mrioShockMappings || [])[0] || {};
  const selectedEnergyModel = ENERGY_MODEL_OPTIONS.find((option) => option.value === energyModelEngine) || ENERGY_MODEL_OPTIONS[0];
  const energyModelExecutable = selectedEnergyModel.value === "calliope";
  const [aiCommandOpen, setAiCommandOpen] = useState(false);

  return (
    <div className="diagram-scenario-controls">
      <div className={`ai-command scenario-ai-command ${aiCommandOpen ? "open" : "collapsed"}`}>
        <div className="ai-command-header">
          <div>
            <label>AI scenario command</label>
          </div>
          <button type="button" className="ai-command-toggle" onClick={() => setAiCommandOpen((prev) => !prev)}>
            {aiCommandOpen ? "Hide details" : "Expand"}
          </button>
        </div>
        <div className="ai-command-row">
          <input
            value={aiPrompt}
            onChange={(e) => setAiPrompt(e.target.value)}
            placeholder="Example: 2050 full decarbonization with high demand and a strong carbon price"
          />
          <button type="button" onClick={onApplyAiPrompt}>Configure</button>
        </div>
        {aiCommandOpen ? (
          <>
            <div className="muted" style={{ marginTop: 6, fontSize: 12 }}>
              The planner infers scenario controls, policy levers, and geography focus from the query, then reports what changed and why.
            </div>
            <AiQueryResultPanel result={aiQueryResult} />
          </>
        ) : null}
      </div>
      <div className="diagram-scenario-layout">
        <div className="diagram-selector-stack">
          <div className="diagram-section-label">Scenario selectors</div>
          <div className="diagram-control-grid">
            <div>
              <label>Energy model engine</label>
              <select value={selectedEnergyModel.value} onChange={(e) => onEnergyModelEngineChange(e.target.value)}>
                {ENERGY_MODEL_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label} - {option.runtimeStatus}
                  </option>
                ))}
              </select>
            </div>
            {showStructuredSelector ? (
              <>
                <div>
                  <label>Main scenario type</label>
                  <select
                    value={scenarioSelections.family}
                    onChange={(e) => onScenarioSelectionChange({ family: e.target.value })}
                  >
                    {selectorModel.hasPathway2040 ? (
                      <option value="pathway_2040">2040 pathway scenarios</option>
                    ) : null}
                    {selectorModel.hasTransmissionOnly ? (
                      <option value="transmission_only">Transmission-only scenario</option>
                    ) : null}
                  </select>
                </div>
                <div>
                  <label>Target pathway</label>
                  <select value={mrioScenarioId || ""} onChange={(e) => onMrioScenarioChange(e.target.value)}>
                    {(targetScenarios || []).map((s) => (
                      <option key={s.scenario_id} value={s.scenario_id}>
                        {s.scenario_id} - {s.short_label || s.label || s.scenario_type || "Target pathway"}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label>Target year</label>
                  <select value={Number(targetYear || 2030)} onChange={(e) => onTargetYearChange(Number(e.target.value))}>
                    {(targetYears || [2030, 2050]).map((year) => (
                      <option key={year} value={Number(year)}>{year}</option>
                    ))}
                  </select>
                </div>
                {scenarioSelections.family === "pathway_2040" ? (
                  <>
                    <div>
                      <label>Demand pathway</label>
                      <select value={scenarioSelections.pathway} onChange={(e) => onScenarioSelectionChange({ pathway: e.target.value })}>
                        {selectorModel.pathways.map((path) => (
                          <option key={path} value={path}>{pathwayLabel(path)}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label>Energy build package</label>
                      <select
                        value={activePackage}
                        onChange={(e) => {
                          const parts = String(e.target.value || "").split("_");
                          onScenarioSelectionChange({ generation: parts[0] || "legacy", transmission: parts[1] || "legacy" });
                        }}
                      >
                        {packageOptions.map((code) => (
                          <option key={code} value={code}>{SCENARIO_PACKAGE_LABELS[code] || code}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label>Policy package</label>
                      <select
                        value={scenarioSelections.policy ? "on" : "off"}
                        onChange={(e) => onScenarioSelectionChange({ policy: e.target.value === "on" })}
                        disabled={!policyAvailable}
                      >
                        <option value="off">Standard</option>
                        {policyAvailable ? <option value="on">Policy push</option> : null}
                      </select>
                    </div>
                  </>
                ) : null}
              </>
            ) : (
              <div>
                <label>Energy scenario</label>
                <select value={scenarioKey} onChange={(e) => onScenarioChange(e.target.value)}>
                  {(scenarios || []).map((s) => (
                    <option key={s.key} value={s.key}>{s.title}</option>
                  ))}
                </select>
              </div>
            )}
            <div>
              <label>Run profile</label>
              <select value={runProfile} onChange={(e) => onSetRunProfile(e.target.value)}>
                <option value="dev">Dev profile</option>
                <option value="analysis">Analysis profile</option>
                <option value="full">Full profile</option>
              </select>
            </div>
          </div>

          <div className="diagram-note">
            <div><b>Resolved package:</b> <code>{selectedEnergyModel.label}</code> / <code>{scenarioKey || "-"}</code> + target <code>{mrioScenarioId || "-"}</code> @ <code>{Number(targetYear || 2030)}</code></div>
            <div className="muted" style={{ marginTop: 4 }}>
              MRIO shock mapping: <code>{shockMapping.mapping_id || "mrio_direct_heuristic_v1"}</code>.{" "}
              {selectedTargetScenario ? selectedTargetScenario.label || selectedTargetScenario.short_label || "" : ""}
            </div>
            {!energyModelExecutable ? (
              <div className="warn" style={{ marginTop: 8 }}>
                OSeMOSYS is selectable for scenario design/provenance, but the executable runtime adapter is not implemented yet. Select Calliope to run the model now.
              </div>
            ) : null}
          </div>
        </div>

        <div className="diagram-slider-stack">
          <div className="diagram-section-label">Policy levers</div>
          <div className="diagram-lever-grid">
            <LeverControl
              label="Renewables CAPEX multiplier"
              tooltip={POLICY_LEVER_TOOLTIPS.renewables_capex_multiplier}
              value={levers.renewables_capex_multiplier}
              min={0.7}
              max={1.5}
              step={0.05}
              onChange={(v) => onSetLevers({ ...levers, renewables_capex_multiplier: v })}
            />
            <LeverControl
              label="Fossil variable cost multiplier"
              tooltip={POLICY_LEVER_TOOLTIPS.fossil_fuel_price_multiplier}
              value={levers.fossil_fuel_price_multiplier}
              min={0.7}
              max={1.8}
              step={0.05}
              onChange={(v) => onSetLevers({ ...levers, fossil_fuel_price_multiplier: v })}
            />
            <LeverControl
              label="Carbon price (USD/tCO2)"
              tooltip={POLICY_LEVER_TOOLTIPS.carbon_price_usd_per_tco2}
              value={levers.carbon_price_usd_per_tco2}
              min={0}
              max={300}
              step={10}
              onChange={(v) => onSetLevers({ ...levers, carbon_price_usd_per_tco2: v })}
            />
            <LeverControl
              label="Demand multiplier"
              tooltip={POLICY_LEVER_TOOLTIPS.demand_multiplier}
              value={levers.demand_multiplier}
              min={0.8}
              max={1.4}
              step={0.05}
              onChange={(v) => onSetLevers({ ...levers, demand_multiplier: v })}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function DatasetRows({ datasets, onUpload }) {
  if (!datasets || !datasets.length) {
    return <div className="muted" style={{ fontSize: 12 }}>No datasets are registered for this layer.</div>;
  }
  return (
    <div className="diagram-dataset-list">
      {datasets.map((dataset) => (
        <div key={dataset.id} className="diagram-dataset-row">
          <div>
            <div style={{ fontWeight: 700 }}>{dataset.label}</div>
            <div className="muted" style={{ fontSize: 11 }}>
              {dataset.filename} · {dataset.exists ? "available" : "missing"}
            </div>
            <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>{dataset.role}</div>
          </div>
          <div className="diagram-dataset-actions">
            <a href={api.inputDatasetDownloadUrl(dataset.id)} download>Download</a>
            <label className="dataset-upload-button">
              Upload
              <input
                type="file"
                onChange={(event) => {
                  const file = event.target.files && event.target.files[0];
                  if (file) onUpload(dataset.id, file);
                  event.target.value = "";
                }}
              />
            </label>
          </div>
        </div>
      ))}
    </div>
  );
}

function OutputRows({ runId, exchangeArtifacts }) {
  const artifacts = DEFAULT_OUTPUT_ARTIFACTS.map((row) => {
    if (exchangeArtifacts && exchangeArtifacts[row.key]) {
      const artifactPath = String(exchangeArtifacts[row.key] || "");
      const href = artifactPath.startsWith("/api/")
        ? `${API_BASE}${artifactPath}`
        : runId
          ? `${API_BASE}/api/run/${encodeURIComponent(runId)}/download/artifact/${encodeURIComponent(artifactPath).replace(/%2F/g, "/")}`
          : "";
      return { ...row, href };
    }
    if (!runId || !row.url) return { ...row, href: "" };
    return { ...row, href: `${API_BASE}/api/run/${encodeURIComponent(runId)}/download/${row.url}` };
  });
  return (
    <div className="diagram-dataset-list">
      {artifacts.map((artifact) => (
        <div key={artifact.key} className="diagram-output-row">
          <div>
            <div style={{ fontWeight: 700 }}>{artifact.label}</div>
            <div className="muted" style={{ fontSize: 11 }}>{artifact.key}</div>
          </div>
          {artifact.href ? (
            <a href={artifact.href} download>Download</a>
          ) : (
            <span className="muted" style={{ fontSize: 12 }}>Available after run</span>
          )}
        </div>
      ))}
    </div>
  );
}

function RunTabs({ jobs, selectedJobId, activeJob, onSelectJob }) {
  const rows = (jobs || []).slice(0, 8);
  return (
    <div className="run-tab-strip" aria-label="Model run tabs">
      {rows.length ? rows.map((job) => {
        const effective = activeJob && activeJob.job_id === job.job_id ? activeJob : job;
        const status = displayStatus(effective.status);
        const selected = selectedJobId === job.job_id;
        return (
          <button
            key={job.job_id}
            type="button"
            className={`run-tab ${selected ? "active" : ""}`}
            onClick={() => onSelectJob(effective)}
          >
            <span>{effective.artifacts && effective.artifacts.run_id ? effective.artifacts.run_id : effective.job_id}</span>
            <span className={status.className}>{status.label}</span>
          </button>
        );
      }) : <div className="muted" style={{ fontSize: 12 }}>No model runs yet.</div>}
    </div>
  );
}

function normalizeAiQueryText(raw) {
  return String(raw || "")
    .toLowerCase()
    .replace(/[^a-z0-9.%/+-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function aiTextHas(text, phrase) {
  const normalizedPhrase = normalizeAiQueryText(phrase);
  if (!normalizedPhrase) return false;
  return (` ${text} `).includes(` ${normalizedPhrase} `);
}

function clampAiValue(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function aiAddUpdate(result, parameter, value, reason) {
  result.updates.push({ parameter, value, reason });
}

function aiPercentValue(text, subjectPattern, directionPattern) {
  const a = new RegExp(`${directionPattern}\\s+(?:the\\s+)?${subjectPattern}[^0-9]{0,36}([0-9]+(?:\\.[0-9]+)?)\\s*%`, "i");
  const b = new RegExp(`${subjectPattern}[^0-9]{0,36}${directionPattern}[^0-9]{0,36}([0-9]+(?:\\.[0-9]+)?)\\s*%`, "i");
  const match = text.match(a) || text.match(b);
  return match ? toNumber(match[1], NaN) : NaN;
}

function aiMultiplierValue(text, subjectPattern) {
  const match =
    text.match(new RegExp(`${subjectPattern}[^0-9]{0,36}(?:multiplier|to|at|=)\\s*([0-9]+(?:\\.[0-9]+)?)\\s*(?:x)?`, "i")) ||
    text.match(new RegExp(`(?:multiplier|set)\\s+${subjectPattern}[^0-9]{0,36}([0-9]+(?:\\.[0-9]+)?)\\s*(?:x)?`, "i"));
  return match ? toNumber(match[1], NaN) : NaN;
}

function aiCarbonPriceValue(text) {
  const match =
    text.match(/(?:carbon price|carbon tax|co2 price|co2 cost)[^0-9]{0,36}([0-9]+(?:\.[0-9]+)?)/i) ||
    text.match(/([0-9]+(?:\.[0-9]+)?)\s*(?:usd\/tco2|usd per tco2|dollars per tonne|dollars per ton)/i);
  return match ? toNumber(match[1], NaN) : NaN;
}

function aiLocationCandidates(locationMapData) {
  const candidates = [];
  Object.entries(SUBREGION_CENTROIDS).forEach(([code, row]) => {
    candidates.push({
      type: "subregion",
      aliases: [code.toLowerCase(), normalizeAiQueryText(row.label)],
      locationId: code,
      countryIso3: row.country,
      label: row.label || code,
    });
  });
  if (locationMapData && locationMapData.byLocation instanceof Map) {
    locationMapData.byLocation.forEach((row, locationId) => {
      const id = normalizeLocationId(locationId);
      const label = firstNonEmpty(row, ["display_name", "name", "label", "location", "location_id"]) || id;
      candidates.push({
        type: isSubregionLocation(id) ? "subregion" : "country",
        aliases: [id.toLowerCase(), normalizeAiQueryText(label)],
        locationId: id,
        countryIso3: normalizeLocationId(row && row.country_iso3) || locationToParentCountry(id),
        region: row && row.region ? String(row.region) : "",
        label,
      });
    });
  }
  AI_COUNTRY_ALIASES.forEach((row) => {
    candidates.push({
      type: "country",
      aliases: row.aliases,
      locationId: row.iso3,
      countryIso3: row.iso3,
      label: row.label,
    });
  });
  AI_REGION_ALIASES.forEach((row) => {
    candidates.push({
      type: "region",
      aliases: row.aliases,
      region: row.region,
      pool: row.pool,
      label: row.label,
    });
  });
  return candidates
    .map((row) => ({
      ...row,
      aliases: (row.aliases || []).map(normalizeAiQueryText).filter(Boolean),
    }))
    .sort((a, b) => {
      const aLen = Math.max(...a.aliases.map((alias) => alias.length), 0);
      const bLen = Math.max(...b.aliases.map((alias) => alias.length), 0);
      return bLen - aLen;
    });
}

function inferAiFocus(text, locationMapData) {
  for (const candidate of aiLocationCandidates(locationMapData)) {
    if ((candidate.aliases || []).some((alias) => aiTextHas(text, alias))) return candidate;
  }
  return null;
}

function applyPromptConfiguration(prompt, options) {
  const text = normalizeAiQueryText(prompt);
  const result = { ok: false, message: "", updates: [], warnings: [], focus: null };
  if (!text) {
    result.message = "No query was provided. Enter a new query with scenario, year, lever, or geography intent.";
    return result;
  }

  const selectorModel = options.selectorModel || {};
  const scenarioPatch = {};
  const nextLevers = { ...(options.currentLevers || DEFAULT_LEVERS) };
  const targetYears = (options.targetYears || []).map((year) => Number(year)).filter((year) => Number.isFinite(year));

  if (aiTextHas(text, "osemosys")) {
    options.onEnergyModelEngineChange("osemosys");
    aiAddUpdate(result, "Energy model engine", "OSeMOSYS", "The query explicitly mentioned OSeMOSYS.");
  } else if (aiTextHas(text, "calliope")) {
    options.onEnergyModelEngineChange("calliope");
    aiAddUpdate(result, "Energy model engine", "Calliope", "The query explicitly mentioned Calliope.");
  }

  if (aiTextHas(text, "full")) {
    options.onSetRunProfile("full");
    aiAddUpdate(result, "Run profile", "full", "The query asked for a full run.");
  } else if (aiTextHas(text, "analysis") || aiTextHas(text, "review")) {
    options.onSetRunProfile("analysis");
    aiAddUpdate(result, "Run profile", "analysis", "The query asked for analysis/review mode.");
  } else if (aiTextHas(text, "fast") || aiTextHas(text, "dev") || aiTextHas(text, "quick")) {
    options.onSetRunProfile("dev");
    aiAddUpdate(result, "Run profile", "dev", "The query asked for a fast or development run.");
  }

  const yearMatch = text.match(/\b(2030|2040|2050)\b/);
  if (yearMatch) {
    const year = Number(yearMatch[1]);
    if (!targetYears.length || targetYears.includes(year)) {
      options.onTargetYearChange(year);
      aiAddUpdate(result, "Target year", String(year), `The query explicitly mentioned ${year}.`);
    } else {
      result.warnings.push(`Target year ${year} is not available in the current catalog; available years are ${targetYears.join(", ")}.`);
    }
  }

  if (aiTextHas(text, "s1") || aiTextHas(text, "decarbonization") || aiTextHas(text, "decarbonisation") || aiTextHas(text, "net zero") || aiTextHas(text, "renewable push")) {
    const target = (options.targetScenarios || []).find((s) => String(s.scenario_id || "").toLowerCase() === "s1");
    if (target) {
      options.onMrioScenarioChange(target.scenario_id);
      aiAddUpdate(result, "Target pathway", target.scenario_id, "The query points to S1/decarbonization-style targets.");
    }
  } else if (aiTextHas(text, "s2") || aiTextHas(text, "national policy") || aiTextHas(text, "ndc") || aiTextHas(text, "policy target")) {
    const target = (options.targetScenarios || []).find((s) => String(s.scenario_id || "").toLowerCase() === "s2");
    if (target) {
      options.onMrioScenarioChange(target.scenario_id);
      aiAddUpdate(result, "Target pathway", target.scenario_id, "The query points to S2/national-policy-target assumptions.");
    }
  }

  if (selectorModel.hasTransmissionOnly && (aiTextHas(text, "transmission only") || aiTextHas(text, "new links only"))) {
    scenarioPatch.family = "transmission_only";
    aiAddUpdate(result, "Main scenario type", "Transmission-only", "The query asked for a transmission-only/new-links scenario.");
  }

  if (selectorModel.hasPathway2040) {
    if (aiTextHas(text, "announced commitments") || aiTextHas(text, "ac pathway") || aiTextHas(text, "ac scenario")) {
      scenarioPatch.pathway = "AC";
      aiAddUpdate(result, "Demand pathway", "Announced Commitments (AC)", "The query referenced the AC/Announced Commitments pathway.");
    } else if (aiTextHas(text, "steps") || aiTextHas(text, "stated policies")) {
      scenarioPatch.pathway = "STEPS";
      aiAddUpdate(result, "Demand pathway", "STEPS", "The query referenced the STEPS/Stated Policies pathway.");
    } else if (aiTextHas(text, "high demand")) {
      scenarioPatch.pathway = selectorModel.pathways && selectorModel.pathways.includes("AC") ? "AC" : scenarioPatch.pathway;
      aiAddUpdate(result, "Demand pathway", scenarioPatch.pathway || "higher demand pathway", "The query asked for high demand; AC is used when present.");
    } else if (aiTextHas(text, "low demand")) {
      scenarioPatch.pathway = selectorModel.pathways && selectorModel.pathways.includes("STEPS") ? "STEPS" : scenarioPatch.pathway;
      aiAddUpdate(result, "Demand pathway", scenarioPatch.pathway || "lower demand pathway", "The query asked for low demand; STEPS is used when present.");
    }

    if (aiTextHas(text, "new generation") || aiTextHas(text, "new gen") || aiTextHas(text, "generation expansion")) {
      scenarioPatch.generation = "new";
      aiAddUpdate(result, "Energy build package", "new generation", "The query asked for new generation buildout.");
    } else if (aiTextHas(text, "legacy generation") || aiTextHas(text, "old generation") || aiTextHas(text, "old gen")) {
      scenarioPatch.generation = "legacy";
      aiAddUpdate(result, "Energy build package", "legacy generation", "The query asked to keep legacy generation assumptions.");
    }

    if (aiTextHas(text, "no new links") || aiTextHas(text, "legacy links") || aiTextHas(text, "old links") || aiTextHas(text, "legacy transmission")) {
      scenarioPatch.transmission = "legacy";
      aiAddUpdate(result, "Energy build package", "legacy links", "The query asked to avoid new transmission links.");
    } else if (aiTextHas(text, "new links") || aiTextHas(text, "new transmission") || aiTextHas(text, "transmission expansion")) {
      scenarioPatch.transmission = "new";
      aiAddUpdate(result, "Energy build package", "new links", "The query asked for transmission expansion/new links.");
    }

    if (aiTextHas(text, "standard policy") || aiTextHas(text, "no policy push")) {
      scenarioPatch.policy = false;
      aiAddUpdate(result, "Policy package", "standard", "The query asked for standard/no policy push.");
    } else if (aiTextHas(text, "policy push") || aiTextHas(text, "policy package") || aiTextHas(text, "strong policy")) {
      scenarioPatch.policy = true;
      aiAddUpdate(result, "Policy package", "on if available", "The query asked for stronger policy support.");
    }
  }

  if (Object.keys(scenarioPatch).length) {
    if (selectorModel.hasPathway2040 && !scenarioPatch.family) scenarioPatch.family = "pathway_2040";
    options.onScenarioSelectionChange(scenarioPatch);
  }

  const demandMultiplier = aiMultiplierValue(text, "(?:demand|load)");
  const demandUp = aiPercentValue(text, "(?:demand|load)", "(?:increase|raise|grow|higher)");
  const demandDown = aiPercentValue(text, "(?:demand|load)", "(?:decrease|reduce|lower|cut)");
  if (Number.isFinite(demandMultiplier)) {
    nextLevers.demand_multiplier = clampAiValue(demandMultiplier, 0.8, 1.4);
    aiAddUpdate(result, "Demand multiplier", nextLevers.demand_multiplier.toFixed(2), "The query specified a demand/load multiplier.");
  } else if (Number.isFinite(demandUp)) {
    nextLevers.demand_multiplier = clampAiValue(1 + demandUp / 100, 0.8, 1.4);
    aiAddUpdate(result, "Demand multiplier", nextLevers.demand_multiplier.toFixed(2), `The query asked to increase demand by ${demandUp}%.`);
  } else if (Number.isFinite(demandDown)) {
    nextLevers.demand_multiplier = clampAiValue(1 - demandDown / 100, 0.8, 1.4);
    aiAddUpdate(result, "Demand multiplier", nextLevers.demand_multiplier.toFixed(2), `The query asked to reduce demand by ${demandDown}%.`);
  }

  const renewablePattern = "(?:renewable|renewables|solar|wind|renewable capex|renewables capex)(?:\\s+(?:capex|cost|costs|price|prices))?";
  const renewableMultiplier = aiMultiplierValue(text, renewablePattern);
  const renewableDown = aiPercentValue(text, renewablePattern, "(?:decrease|reduce|lower|cut|cheaper)");
  const renewableUp = aiPercentValue(text, renewablePattern, "(?:increase|raise|higher|more expensive)");
  if (Number.isFinite(renewableMultiplier)) {
    nextLevers.renewables_capex_multiplier = clampAiValue(renewableMultiplier, 0.7, 1.5);
    aiAddUpdate(result, "Renewables CAPEX multiplier", nextLevers.renewables_capex_multiplier.toFixed(2), "The query specified a renewables cost/CAPEX multiplier.");
  } else if (Number.isFinite(renewableDown)) {
    nextLevers.renewables_capex_multiplier = clampAiValue(1 - renewableDown / 100, 0.7, 1.5);
    aiAddUpdate(result, "Renewables CAPEX multiplier", nextLevers.renewables_capex_multiplier.toFixed(2), `The query asked to reduce renewable costs by ${renewableDown}%.`);
  } else if (Number.isFinite(renewableUp)) {
    nextLevers.renewables_capex_multiplier = clampAiValue(1 + renewableUp / 100, 0.7, 1.5);
    aiAddUpdate(result, "Renewables CAPEX multiplier", nextLevers.renewables_capex_multiplier.toFixed(2), `The query asked to increase renewable costs by ${renewableUp}%.`);
  } else if (aiTextHas(text, "cheap renewables") || aiTextHas(text, "low cost renewables")) {
    nextLevers.renewables_capex_multiplier = 0.85;
    aiAddUpdate(result, "Renewables CAPEX multiplier", "0.85", "The query implied cheaper renewables without a numeric value, so a moderate placeholder reduction was applied.");
  }

  const fossilPattern = "(?:fossil|gas|coal|oil|fuel)(?:\\s+(?:cost|costs|price|prices|variable cost))?";
  const fossilMultiplier = aiMultiplierValue(text, fossilPattern);
  const fossilUp = aiPercentValue(text, fossilPattern, "(?:increase|raise|higher|more expensive)");
  const fossilDown = aiPercentValue(text, fossilPattern, "(?:decrease|reduce|lower|cut|cheaper)");
  if (Number.isFinite(fossilMultiplier)) {
    nextLevers.fossil_fuel_price_multiplier = clampAiValue(fossilMultiplier, 0.7, 1.8);
    aiAddUpdate(result, "Fossil variable cost multiplier", nextLevers.fossil_fuel_price_multiplier.toFixed(2), "The query specified a fossil/fuel cost multiplier.");
  } else if (Number.isFinite(fossilUp)) {
    nextLevers.fossil_fuel_price_multiplier = clampAiValue(1 + fossilUp / 100, 0.7, 1.8);
    aiAddUpdate(result, "Fossil variable cost multiplier", nextLevers.fossil_fuel_price_multiplier.toFixed(2), `The query asked to increase fossil/fuel costs by ${fossilUp}%.`);
  } else if (Number.isFinite(fossilDown)) {
    nextLevers.fossil_fuel_price_multiplier = clampAiValue(1 - fossilDown / 100, 0.7, 1.8);
    aiAddUpdate(result, "Fossil variable cost multiplier", nextLevers.fossil_fuel_price_multiplier.toFixed(2), `The query asked to reduce fossil/fuel costs by ${fossilDown}%.`);
  } else if (aiTextHas(text, "high fossil prices") || aiTextHas(text, "expensive fossil") || aiTextHas(text, "fuel price shock")) {
    nextLevers.fossil_fuel_price_multiplier = 1.25;
    aiAddUpdate(result, "Fossil variable cost multiplier", "1.25", "The query implied higher fossil/fuel prices without a numeric value, so a moderate placeholder increase was applied.");
  }

  const carbonPrice = aiCarbonPriceValue(text);
  if (Number.isFinite(carbonPrice)) {
    nextLevers.carbon_price_usd_per_tco2 = clampAiValue(carbonPrice, 0, 300);
    aiAddUpdate(result, "Carbon price", `${nextLevers.carbon_price_usd_per_tco2.toFixed(0)} USD/tCO2`, "The query specified a carbon price or CO2 price.");
  }

  if (JSON.stringify(nextLevers) !== JSON.stringify(options.currentLevers || DEFAULT_LEVERS)) {
    options.onSetLevers(nextLevers);
  }

  const focus = inferAiFocus(text, options.locationMapData);
  if (focus) {
    result.focus = focus;
    if (focus.type === "region") {
      options.onSetSpatialFilter({ region: focus.region, pool: focus.pool || inferPoolFromRegion(focus.region), label: focus.label, source: "ai_query" });
      aiAddUpdate(result, "Geography focus", focus.label, "The query mentioned a model region/power pool.");
    } else {
      options.onSetSpatialFilter({
        locationId: focus.locationId || focus.countryIso3 || "",
        countryIso3: focus.countryIso3 || locationToParentCountry(focus.locationId),
        region: focus.region || "",
        label: focus.label || focus.locationId || focus.countryIso3,
        source: "ai_query",
      });
      aiAddUpdate(result, "Geography focus", focus.label || focus.locationId || focus.countryIso3, "The query mentioned a country or subcountry model location.");
    }
  } else if (
    aiTextHas(text, "global") ||
    aiTextHas(text, "all countries") ||
    aiTextHas(text, "no country filter") ||
    aiTextHas(text, "africa") ||
    aiTextHas(text, "africa wide")
  ) {
    options.onSetSpatialFilter(null);
    aiAddUpdate(result, "Geography focus", "global / Africa-wide", "The query asked for the full model geography rather than a specific country or region.");
  }

  result.ok = result.updates.length > 0;
  result.message = result.ok
    ? `Applied ${result.updates.length} inferred setting${result.updates.length === 1 ? "" : "s"}.`
    : "I could not infer any scenario controls, levers, or geography from that query. Enter a new query with explicit scenario, year, lever, or country/region terms.";
  return result;
}

function applyRemoteAiPlan(remoteResult, options) {
  const plan = (remoteResult && remoteResult.plan) || {};
  const result = {
    ok: Boolean(remoteResult && remoteResult.ok),
    source: (remoteResult && remoteResult.source) || "azure_openai",
    message: (remoteResult && remoteResult.message) || "AI planner returned a scenario configuration.",
    updates: Array.isArray(remoteResult && remoteResult.updates) ? remoteResult.updates : [],
    warnings: Array.isArray(remoteResult && remoteResult.warnings) ? remoteResult.warnings : [],
    focus: null,
  };

  if (!result.ok) return result;

  const applied = [];
  const addApplied = (parameter, value, reason) => {
    applied.push({ parameter, value, reason });
  };

  const runProfile = String(plan.run_profile || "").trim().toLowerCase();
  if (["dev", "analysis", "full"].includes(runProfile)) {
    options.onSetRunProfile(runProfile);
    addApplied("Run profile", runProfile, "Set by Azure OpenAI query plan.");
  }

  const energyModelEngine = String(plan.energy_model_engine || "").trim().toLowerCase();
  if (["calliope", "osemosys"].includes(energyModelEngine)) {
    options.onEnergyModelEngineChange(energyModelEngine);
    addApplied("Energy model engine", energyModelEngine === "osemosys" ? "OSeMOSYS" : "Calliope", "Set by Azure OpenAI query plan.");
  }

  const targetYear = Number(plan.target_year);
  const targetYears = (options.targetYears || []).map((year) => Number(year)).filter((year) => Number.isFinite(year));
  if (Number.isFinite(targetYear)) {
    if (!targetYears.length || targetYears.includes(targetYear)) {
      options.onTargetYearChange(targetYear);
      addApplied("Target year", String(targetYear), "Set by Azure OpenAI query plan.");
    } else {
      result.warnings.push(`AI selected unavailable target year ${targetYear}; available years are ${targetYears.join(", ")}.`);
    }
  }

  const targetScenarioId = String(plan.target_scenario_id || "").trim().toUpperCase();
  if (targetScenarioId) {
    const target = (options.targetScenarios || []).find((s) => String(s.scenario_id || "").toUpperCase() === targetScenarioId);
    if (target) {
      options.onMrioScenarioChange(target.scenario_id);
      addApplied("Target pathway", target.scenario_id, "Set by Azure OpenAI query plan.");
    } else {
      result.warnings.push(`AI selected unavailable target pathway ${targetScenarioId}.`);
    }
  }

  const scenarioPatch = plan.scenario_patch && typeof plan.scenario_patch === "object" ? plan.scenario_patch : {};
  const cleanScenarioPatch = {};
  if (["pathway_2040", "transmission_only"].includes(String(scenarioPatch.family || ""))) {
    cleanScenarioPatch.family = scenarioPatch.family;
  }
  if (["STEPS", "AC"].includes(String(scenarioPatch.pathway || "").toUpperCase())) {
    cleanScenarioPatch.pathway = String(scenarioPatch.pathway).toUpperCase();
  }
  if (["legacy", "new"].includes(String(scenarioPatch.generation || ""))) {
    cleanScenarioPatch.generation = scenarioPatch.generation;
  }
  if (["legacy", "new"].includes(String(scenarioPatch.transmission || ""))) {
    cleanScenarioPatch.transmission = scenarioPatch.transmission;
  }
  if (typeof scenarioPatch.policy === "boolean") {
    cleanScenarioPatch.policy = scenarioPatch.policy;
  }
  if (Object.keys(cleanScenarioPatch).length) {
    options.onScenarioSelectionChange(cleanScenarioPatch);
    addApplied("Energy scenario controls", JSON.stringify(cleanScenarioPatch), "Set by Azure OpenAI query plan.");
  }

  const levers = plan.levers && typeof plan.levers === "object" ? plan.levers : {};
  const nextLevers = { ...(options.currentLevers || DEFAULT_LEVERS) };
  const leverRanges = {
    demand_multiplier: [0.8, 1.4],
    renewables_capex_multiplier: [0.7, 1.5],
    fossil_fuel_price_multiplier: [0.7, 1.8],
    carbon_price_usd_per_tco2: [0, 300],
  };
  Object.entries(leverRanges).forEach(([key, range]) => {
    const value = Number(levers[key]);
    if (!Number.isFinite(value)) return;
    nextLevers[key] = clampAiValue(value, range[0], range[1]);
    addApplied(key, String(nextLevers[key]), "Set by Azure OpenAI query plan.");
  });
  if (JSON.stringify(nextLevers) !== JSON.stringify(options.currentLevers || DEFAULT_LEVERS)) {
    options.onSetLevers(nextLevers);
  }

  const focus = plan.geography_focus && typeof plan.geography_focus === "object" ? plan.geography_focus : {};
  const focusType = String(focus.type || "").toLowerCase();
  if (focusType === "global") {
    options.onSetSpatialFilter(null);
    addApplied("Geography focus", "global / Africa-wide", "Set by Azure OpenAI query plan.");
  } else if (focusType === "region") {
    const region = normalizeRegionKey(focus.region || focus.label);
    const pool = normalizePoolKey(focus.pool) || inferPoolFromRegion(region);
    options.onSetSpatialFilter({
      region,
      pool,
      label: focus.label || region || pool || "Region focus",
      source: "ai_query",
    });
    result.focus = focus;
    addApplied("Geography focus", focus.label || region || pool, "Set by Azure OpenAI query plan.");
  } else if (focusType === "country" || focusType === "subregion") {
    const locationId = normalizeLocationId(focus.location_id || focus.country_iso3);
    const countryIso3 = normalizeLocationId(focus.country_iso3) || locationToParentCountry(locationId);
    if (locationId || countryIso3) {
      options.onSetSpatialFilter({
        locationId: locationId || countryIso3,
        countryIso3,
        region: focus.region || "",
        label: focus.label || locationId || countryIso3,
        source: "ai_query",
      });
      result.focus = focus;
      addApplied("Geography focus", focus.label || locationId || countryIso3, "Set by Azure OpenAI query plan.");
    }
  }

  if (!result.updates.length) result.updates = applied;
  result.ok = applied.length > 0;
  if (!result.ok) {
    result.message = "The AI planner returned a response, but no valid UI setting could be applied. Enter a new query.";
  }
  return result;
}

function AiQueryResultPanel({ result }) {
  if (!result) return null;
  return (
    <div className={`ai-query-result ${result.ok ? "ok" : "failed"}`}>
      <div style={{ fontWeight: 800 }}>
        {result.ok ? result.message : `${result.message} New query needed.`}
      </div>
      {result.source ? (
        <div className="muted" style={{ marginTop: 4, fontSize: 11 }}>
          Planner source: <code>{result.source}</code>
        </div>
      ) : null}
      <details open={!result.ok}>
        <summary>{result.ok ? "View query explanation" : "View parser details"}</summary>
        {result.updates && result.updates.length ? (
          <div className="ai-query-update-list">
            {result.updates.map((row, idx) => (
              <div key={`${row.parameter}-${idx}`} className="ai-query-update-row">
                <div>
                  <b>{row.parameter}</b>: <code>{row.value}</code>
                </div>
                <div className="muted" style={{ fontSize: 12 }}>{row.reason}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
            No settings were changed. Try mentioning a target like <code>S1</code>, a year like <code>2050</code>,
            a lever like <code>carbon price 50</code>, or a focus such as <code>Kenya</code> or <code>West Africa</code>.
          </div>
        )}
        {result.warnings && result.warnings.length ? (
          <div className="ai-query-warnings">
            {result.warnings.map((warning, idx) => (
              <div key={`warning-${idx}`}>{warning}</div>
            ))}
          </div>
        ) : null}
      </details>
    </div>
  );
}

function ArchitectureRunWorkspace({
  runViewMode,
  jobs,
  selectedJobId,
  activeJob,
  onSelectJob,
  selectedRunId,
  result,
  exchangeArtifacts,
  inputDatasets,
  onUploadDataset,
  errorMessage,
  statusMessage,
  scenarioControls,
  operationsPanel,
  resultsPanel,
}) {
  const workspaceState = activeJob ? "running" : result ? "complete" : "ready";
  const datasetGroups = useMemo(() => {
    const byLayer = new Map();
    (inputDatasets || []).forEach((dataset) => {
      const layer = dataset.layer || "other";
      if (!byLayer.has(layer)) byLayer.set(layer, []);
      byLayer.get(layer).push(dataset);
    });
    return byLayer;
  }, [inputDatasets]);
  const calliopeDatasets = [
    ...(datasetGroups.get("calliope") || []),
    ...(datasetGroups.get("scenario") || []),
  ];
  const mrioDatasets = [
    ...(datasetGroups.get("mrio") || []),
    ...(datasetGroups.get("bridge") || []),
  ];

  return (
    <div className={`architecture-run-workspace ${workspaceState}`}>
      <RunTabs jobs={jobs} selectedJobId={selectedJobId} activeJob={activeJob} onSelectJob={onSelectJob} />

      {errorMessage ? <div className="warn" style={{ marginTop: 0 }}>{errorMessage}</div> : null}
      {statusMessage && runViewMode === "results" ? <div className="ok" style={{ marginTop: 0 }}>{statusMessage}</div> : null}

      {runViewMode === "results" && result ? (
        <div className="results-mode-grid">
          <aside className="results-settings-panel">
            <ArchitectureBox box={ARCHITECTURE_BOXES[0]} activeJob={activeJob} result={result}>
              {scenarioControls}
            </ArchitectureBox>
          </aside>
          <main className="results-mode-main">{resultsPanel}</main>
        </div>
      ) : (
        <FlowModelCanvas
          activeJob={activeJob}
          result={result}
          scenarioControls={scenarioControls}
          operationsPanel={operationsPanel}
          calliopeDatasets={calliopeDatasets}
          mrioDatasets={mrioDatasets}
          selectedRunId={selectedRunId}
          exchangeArtifacts={exchangeArtifacts}
          onUploadDataset={onUploadDataset}
          statusMessage={statusMessage}
        />
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
  const [scenarioCatalog, setScenarioCatalog] = useState(null);
  const [scenarios, setScenarios] = useState([]);
  const [inputDatasets, setInputDatasets] = useState([]);
  const [scenarioKey, setScenarioKey] = useState("");
  const [targetScenarios, setTargetScenarios] = useState([]);
  const [mrioShockMappings, setMrioShockMappings] = useState([]);
  const [mrioScenarioId, setMrioScenarioId] = useState("");
  const [targetYears, setTargetYears] = useState([2030, 2050]);
  const [targetYear, setTargetYear] = useState(2030);
  const [energyModelEngine, setEnergyModelEngine] = useState("calliope");
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
  const [locationMapData, setLocationMapData] = useState(null);
  const [locationMapLoading, setLocationMapLoading] = useState(false);
  const [locationMapError, setLocationMapError] = useState("");
  const [locationMapMetric, setLocationMapMetric] = useState("total_shock_musd");
  const [runSpatialTechData, setRunSpatialTechData] = useState(null);
  const [runSpatialTechLoading, setRunSpatialTechLoading] = useState(false);
  const [runSpatialTechError, setRunSpatialTechError] = useState("");
  const [spatialFilter, setSpatialFilter] = useState(null);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiQueryResult, setAiQueryResult] = useState(null);
  const [runViewMode, setRunViewMode] = useState("setup");
  const locationMapCacheRef = useRef(new Map());
  const runSpatialTechCacheRef = useRef(new Map());

  const selectedScenario = useMemo(
    () => (scenarios || []).find((s) => s.key === scenarioKey),
    [scenarios, scenarioKey]
  );
  const scenarioSelectorModel = useMemo(
    () => buildScenarioSelectorModel(scenarios),
    [scenarios]
  );
  const effectiveStrictValidation = runProfile === "analysis" || runProfile === "full";
  const allowPlaceholderData = true;
  const scenarioSelections = useMemo(
    () => deriveScenarioSelections(scenarioKey, scenarioSelectorModel),
    [scenarioKey, scenarioSelectorModel]
  );

  async function refreshScenarios() {
    try {
      const catalog = await api.fetchScenarioCatalog();
      const rows = catalog.energy_scenarios || [];
      const targetRows = catalog.target_scenarios || [];
      const shockRows = catalog.mrio_shock_mappings || [];
      const years = (catalog.target_years || [2030, 2050]).map((y) => Number(y)).filter((y) => Number.isFinite(y));
      setScenarioCatalog(catalog);
      setScenarios(rows);
      setTargetScenarios(targetRows);
      setMrioShockMappings(shockRows);
      setTargetYears(years.length ? years : [2030, 2050]);
      setEnergyModelEngine((prev) => {
        const available = new Set((catalog.energy_model_engines || ENERGY_MODEL_OPTIONS).map((row) => String(row.value || "").toLowerCase()));
        if (prev && available.has(String(prev).toLowerCase())) return prev;
        return String((catalog.defaults && catalog.defaults.energy_model_engine) || "calliope");
      });
      setScenarioKey((prev) => {
        if (prev && rows.some((s) => s.key === prev)) return prev;
        return (catalog.defaults && catalog.defaults.energy_scenario_key) || (rows[0] && rows[0].key) || "";
      });
      setMrioScenarioId((prev) => {
        if (prev && targetRows.some((s) => s.scenario_id === prev)) return prev;
        return (
          (catalog.defaults && catalog.defaults.target_scenario_id) ||
          (targetRows[0] && targetRows[0].scenario_id) ||
          ""
        );
      });
      setTargetYear((prev) => {
        if (years.includes(Number(prev))) return Number(prev);
        return Number((catalog.defaults && catalog.defaults.target_year) || years[0] || 2030);
      });
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to load scenarios"));
    }
  }

  async function refreshInputDatasets() {
    try {
      const rows = await api.fetchInputDatasets();
      setInputDatasets(rows);
      return rows;
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to load input dataset catalog"));
      return [];
    }
  }

  async function refreshEnvironmentSetup(nextScenario, nextMrioScenarioId, nextTargetYear, nextRunProfile, nextStrictValidation, nextAllowPlaceholderData) {
    const scenario = nextScenario || scenarioKey;
    const mrioScenario = nextMrioScenarioId || mrioScenarioId;
    const year = nextTargetYear || targetYear;
    const profile = nextRunProfile || runProfile;
    const strict = typeof nextStrictValidation === "boolean" ? nextStrictValidation : effectiveStrictValidation;
    const allowPlaceholders =
      typeof nextAllowPlaceholderData === "boolean" ? nextAllowPlaceholderData : allowPlaceholderData;
    setEnvironmentSetupLoading(true);
    try {
      const payload = await api.fetchEnvironmentSetup(scenario, mrioScenario, year, profile, strict, allowPlaceholders);
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
      setRunViewMode("results");
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
      await Promise.all([refreshScenarios(), refreshJobs(), refreshInputDatasets()]);
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
        const payload = await api.fetchEnvironmentSetup(
          scenarioKey,
          mrioScenarioId,
          targetYear,
          runProfile,
          effectiveStrictValidation,
          allowPlaceholderData
        );
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
  }, [scenarioKey, mrioScenarioId, targetYear, runProfile, effectiveStrictValidation]);

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
    setSpatialFilter(null);
  }, [result && result.artifacts && result.artifacts.run_id]);

  useEffect(() => {
    const runId = result && result.artifacts && result.artifacts.run_id;
    if (!runId) {
      setLocationMapData(null);
      setLocationMapLoading(false);
      setLocationMapError("");
      return;
    }

    const cached = locationMapCacheRef.current.get(runId);
    if (cached) {
      setLocationMapData(cached);
      setLocationMapLoading(false);
      setLocationMapError("");
      return;
    }

    let cancelled = false;
    async function loadLocationMapData() {
      setLocationMapLoading(true);
      setLocationMapError("");
      try {
        const [geojsonResult, capexCsvText, opexCsvText] = await Promise.all([
          fetch(LOCATION_MAP_GEOJSON_PATH),
          api.fetchExchangeCsv(runId, "investment_shocks.csv"),
          api.fetchExchangeCsv(runId, "operating_shocks.csv"),
        ]);
        let sourceGeojson = { type: "FeatureCollection", features: [] };
        if (geojsonResult.ok) {
          sourceGeojson = await geojsonResult.json();
        }

        const locationRows = buildLocationRowsFromCsvTexts(capexCsvText, opexCsvText);
        const effectiveGeojson = await buildLocationGeojsonFromCountryAssets(locationRows, sourceGeojson);
        if (cancelled) return;
        const payload = buildLocationMapData(
          runId,
          effectiveGeojson,
          capexCsvText,
          opexCsvText,
          locationRows
        );
        locationMapCacheRef.current.set(runId, payload);
        setLocationMapData(payload);
      } catch (err) {
        if (!cancelled) {
          setLocationMapData(null);
          setLocationMapError(toErrorMessage(err, "Failed to build spatial map dataset"));
        }
      } finally {
        if (!cancelled) setLocationMapLoading(false);
      }
    }
    loadLocationMapData();
    return () => {
      cancelled = true;
    };
  }, [result && result.artifacts && result.artifacts.run_id]);

  useEffect(() => {
    const runId = result && result.artifacts && result.artifacts.run_id;
    if (!runId) {
      setRunSpatialTechData(null);
      setRunSpatialTechLoading(false);
      setRunSpatialTechError("");
      return;
    }

    const cached = runSpatialTechCacheRef.current.get(runId);
    if (cached) {
      setRunSpatialTechData(cached);
      setRunSpatialTechLoading(false);
      setRunSpatialTechError("");
      return;
    }

    let cancelled = false;
    async function loadRunSpatialTechData() {
      setRunSpatialTechLoading(true);
      setRunSpatialTechError("");
      try {
        const resultsCsvText = await api.fetchRunCsv(runId);
        if (cancelled) return;
        const payload = buildRunSpatialTechData(resultsCsvText);
        runSpatialTechCacheRef.current.set(runId, payload);
        setRunSpatialTechData(payload);
      } catch (err) {
        if (!cancelled) {
          setRunSpatialTechData(null);
          setRunSpatialTechError(toErrorMessage(err, "Failed to prepare spatially filterable tech outputs"));
        }
      } finally {
        if (!cancelled) setRunSpatialTechLoading(false);
      }
    }
    loadRunSpatialTechData();
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
    if (!scenarioKey || !mrioScenarioId || queueSubmitting) return;

    setErrorMessage("");
    setStatusMessage("");
    setQueueSubmitting(true);

    try {
      const currentEnvironmentSetup = await refreshEnvironmentSetup(
        scenarioKey,
        mrioScenarioId,
        targetYear,
        runProfile,
        effectiveStrictValidation,
        allowPlaceholderData
      );
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
        energy_model_engine: energyModelEngine,
        energy_scenario_key: scenarioKey,
        mrio_scenario_id: mrioScenarioId,
        target_year: Number(targetYear),
        run_profile: runProfile,
        strict_validation: effectiveStrictValidation,
        allow_placeholder_data: allowPlaceholderData,
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

  async function onUploadDataset(datasetId, file) {
    if (!datasetId || !file) return;
    setErrorMessage("");
    setStatusMessage(`Uploading ${file.name}...`);
    try {
      await api.uploadInputDataset(datasetId, file);
      await refreshInputDatasets();
      setStatusMessage(`Updated input dataset ${datasetId}. Re-run validation before queuing a model run.`);
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to upload input dataset"));
      setStatusMessage("");
    }
  }

  function aiPlannerOptions() {
    return {
      targetScenarios,
      targetYears,
      selectorModel: scenarioSelectorModel,
      currentLevers: levers,
      onSetRunProfile: setRunProfile,
      onMrioScenarioChange: setMrioScenarioId,
      onTargetYearChange: setTargetYear,
      onScenarioSelectionChange,
      onSetLevers: setLevers,
      onEnergyModelEngineChange: setEnergyModelEngine,
      locationMapData,
      onSetSpatialFilter: setSpatialFilter,
    };
  }

  function aiPlannerPayload() {
    return {
      query: aiPrompt,
      current: {
        energy_scenario_key: scenarioKey,
        energy_model_engine: energyModelEngine,
        mrio_scenario_id: mrioScenarioId,
        target_year: Number(targetYear),
        run_profile: runProfile,
        levers,
        spatial_filter: spatialFilter,
      },
      available: {
        target_years: targetYears,
        target_scenarios: (targetScenarios || []).map((row) => ({
          scenario_id: row.scenario_id,
          label: row.short_label || row.label || row.scenario_type || "",
        })),
        energy_controls: {
          families: [
            scenarioSelectorModel.hasPathway2040 ? "pathway_2040" : "",
            scenarioSelectorModel.hasTransmissionOnly ? "transmission_only" : "",
          ].filter(Boolean),
          pathways: scenarioSelectorModel.pathways || [],
          generation_options: scenarioSelectorModel.generationOptions || [],
          transmission_options: scenarioSelectorModel.transmissionOptions || [],
          packages: SCENARIO_PACKAGE_ORDER,
          energy_model_engines: ENERGY_MODEL_OPTIONS.map((option) => option.value),
        },
      },
    };
  }

  async function onApplyAiPrompt() {
    const options = aiPlannerOptions();
    let queryResult = null;
    try {
      const remote = await api.planScenarioQuery(aiPlannerPayload());
      if (remote && remote.ok) {
        queryResult = applyRemoteAiPlan(remote, options);
      } else {
        const fallback = applyPromptConfiguration(aiPrompt, options);
        queryResult = {
          ...fallback,
          source: "local_fallback",
          warnings: [
            ...((remote && remote.warnings) || []),
            remote && remote.message ? `Azure planner unavailable: ${remote.message}` : "Azure planner returned no applicable settings.",
            ...(fallback.warnings || []),
          ],
        };
      }
    } catch (err) {
      const fallback = applyPromptConfiguration(aiPrompt, options);
      queryResult = {
        ...fallback,
        source: "local_fallback",
        warnings: [
          `Azure planner request failed: ${toErrorMessage(err, "AI planner request failed")}`,
          ...(fallback.warnings || []),
        ],
      };
    }

    setAiQueryResult(queryResult);
    if (queryResult.ok) {
      setStatusMessage(queryResult.message);
      setErrorMessage("");
    } else {
      setStatusMessage("");
      setErrorMessage(`${queryResult.message} New query needed.`);
    }
  }

  function onSelectJob(job) {
    if (!job) return;
    setSelectedJobId(job.job_id);
    if (normalizeStatus(job.status) === "succeeded" && job.artifacts && job.summary) {
      setResult({ artifacts: job.artifacts, summary: job.summary });
      setSelectedRunId(job.artifacts.run_id);
      setStatusMessage(`Inspecting run ${job.artifacts.run_id}.`);
      setRunViewMode("results");
    } else {
      setSelectedRunId("");
      setResult(null);
      setRunViewMode("setup");
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
  const modelQuality = (integratedView && integratedView.model_quality) || {};
  const metricResolution = (integratedView && integratedView.metric_resolution) || {};
  const scenarioPackageView = (integratedView && integratedView.scenario_package) || ((result && result.summary && result.summary.scenario_package) || {});
  const sourceChannels = (integratedView && integratedView.source_channels) || {};
  const scenarioAssumptions = (integratedView && integratedView.scenario_assumptions) || ((result && result.summary && result.summary.scenario_assumptions) || {});
  const developmentIndicators = (integratedView && integratedView.development_indicators) || ((result && result.summary && result.summary.development_indicators) || {});
  const developmentUncertainty = (integratedView && integratedView.development_uncertainty) || {};

  const reliability = summaryDiagnostics.reliability || {};
  const physicalEmissions = summaryDiagnostics.physical_emissions || {};
  const systemStructure = summaryDiagnostics.system_structure || {};
  const energyBalance = summaryDiagnostics.energy_balance || {};
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

  const developmentByRegionSupplier = Array.isArray(
    result &&
      result.summary &&
      result.summary.development_impacts &&
      result.summary.development_impacts.by_region_supplier &&
      result.summary.development_impacts.by_region_supplier.records
  )
    ? result.summary.development_impacts.by_region_supplier.records
    : [];

  const developmentBySector = Array.isArray(result && result.summary && result.summary.development_impacts && result.summary.development_impacts.by_supplier_sector && result.summary.development_impacts.by_supplier_sector.records)
    ? result.summary.development_impacts.by_supplier_sector.records
    : [];
  const selectedJob = useMemo(() => {
    if (activeJob && selectedJobId && activeJob.job_id === selectedJobId) return activeJob;
    return (jobs || []).find((j) => j.job_id === selectedJobId) || null;
  }, [jobs, activeJob, selectedJobId]);
  const energyModelExecutable = energyModelEngine === "calliope";
  const runDisabled = !scenarioKey || !mrioScenarioId || queueSubmitting || !energyModelExecutable;

  const selectedRunLabel = selectedRunId ? "Selected run" : "Latest run";
  const scenarioControls = (
    <DiagramScenarioControls
      scenarios={scenarios}
      scenarioKey={scenarioKey}
      targetScenarios={targetScenarios}
      mrioShockMappings={mrioShockMappings}
      mrioScenarioId={mrioScenarioId}
      targetYears={targetYears}
      targetYear={targetYear}
      energyModelEngine={energyModelEngine}
      selectorModel={scenarioSelectorModel}
      scenarioSelections={scenarioSelections}
      selectedScenario={selectedScenario}
      levers={levers}
      runProfile={runProfile}
      environmentSetup={environmentSetup}
      environmentSetupLoading={environmentSetupLoading}
      running={running}
      queueSubmitting={queueSubmitting}
      aiPrompt={aiPrompt}
      setAiPrompt={setAiPrompt}
      onApplyAiPrompt={onApplyAiPrompt}
      aiQueryResult={aiQueryResult}
      onScenarioChange={setScenarioKey}
      onMrioScenarioChange={setMrioScenarioId}
      onTargetYearChange={setTargetYear}
      onEnergyModelEngineChange={setEnergyModelEngine}
      onScenarioSelectionChange={onScenarioSelectionChange}
      onSetLevers={setLevers}
      onSetRunProfile={setRunProfile}
      onApplyTemplateLevers={onApplyTemplateLevers}
      onRun={onRun}
      onResetLevers={onResetLevers}
    />
  );
  const operationsPanel = (
    <div className="diagram-ops-stack">
      <EnvironmentSetupPanel
        environmentSetup={environmentSetup}
        loading={environmentSetupLoading}
        onRun={onRun}
        runDisabled={runDisabled}
        queueSubmitting={queueSubmitting}
        running={running}
        onRefresh={() =>
          refreshEnvironmentSetup(scenarioKey, mrioScenarioId, targetYear, runProfile, effectiveStrictValidation, allowPlaceholderData)
        }
        style={{ marginTop: 0 }}
      />
      <ActiveJobPanel activeJob={activeJob} onCancel={onCancelActiveJob} style={{ marginTop: 0 }} />
      <SelectedJobDetailsPanel job={selectedJob} style={{ marginTop: 0 }} />
    </div>
  );
  const resultsPanel = result ? (
    <RunResultsPanel
      result={result}
      selectedRunLabel={selectedRunLabel}
      runMetadata={runMetadata}
      exchangeArtifacts={exchangeArtifacts}
      integratedMetrics={integratedMetrics}
      developmentDrivers={developmentDrivers}
      confidence={confidence}
      modelQuality={modelQuality}
      metricResolution={metricResolution}
      scenarioPackage={scenarioPackageView}
      sourceChannels={sourceChannels}
      scenarioAssumptions={scenarioAssumptions}
      developmentIndicators={developmentIndicators}
      developmentUncertainty={developmentUncertainty}
      reliability={reliability}
      physicalEmissions={physicalEmissions}
      systemStructure={systemStructure}
      energyBalance={energyBalance}
      tradeNetRecords={tradeNetRecords}
      emissionsByPool={emissionsByPool}
      costByComponent={costByComponent}
      developmentByRegion={developmentByRegion}
      developmentByRegionSupplier={developmentByRegionSupplier}
      developmentBySector={developmentBySector}
      developmentMetric={developmentMetric}
      setDevelopmentMetric={setDevelopmentMetric}
      developmentMetricLabel={DEVELOPMENT_METRIC_LABELS[developmentMetric]}
      locationMapData={locationMapData}
      locationMapMetric={locationMapMetric}
      setLocationMapMetric={setLocationMapMetric}
      locationMapLoading={locationMapLoading}
      locationMapError={locationMapError}
      runSpatialTechData={runSpatialTechData}
      runSpatialTechLoading={runSpatialTechLoading}
      runSpatialTechError={runSpatialTechError}
      spatialFilter={spatialFilter}
      setSpatialFilter={setSpatialFilter}
    />
  ) : null;

  return (
    <div className="app-shell">
      <DashboardHeader
        runViewMode={runViewMode}
        onRunViewModeChange={setRunViewMode}
        hasResult={Boolean(result)}
      />

      <div className="app-body app-body-single">
        <ArchitectureRunWorkspace
          runViewMode={runViewMode}
          jobs={jobs}
          selectedJobId={selectedJobId}
          activeJob={activeJob}
          onSelectJob={onSelectJob}
          selectedRunId={selectedRunId}
          result={result}
          exchangeArtifacts={exchangeArtifacts}
          inputDatasets={inputDatasets}
          onUploadDataset={onUploadDataset}
          errorMessage={errorMessage}
          statusMessage={statusMessage}
          scenarioControls={scenarioControls}
          operationsPanel={operationsPanel}
          resultsPanel={resultsPanel}
        />
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
