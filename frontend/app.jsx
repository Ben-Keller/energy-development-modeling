const { useEffect, useId, useMemo, useRef, useState } = React;

const API_BASE = String(window.EDIM_API_BASE || window.location.origin || "").trim().replace(/\/+$/, "");
const ACTIVE_STATUSES = new Set(["queued", "running"]);
const TERMINAL_JOB_STATUSES = new Set(["succeeded", "failed", "cancelled"]);
const RESET_JOB_STATUSES = new Set(["draft"]);
const RUN_CONFIG_LOCK_STATUSES = new Set(["queued", "running", "succeeded"]);

function handleTablistKeyDown(event, currentIndex, itemCount, onSelect) {
  const keyOffsets = {
    ArrowRight: 1,
    ArrowDown: 1,
    ArrowLeft: -1,
    ArrowUp: -1,
  };
  let nextIndex = null;
  if (Object.prototype.hasOwnProperty.call(keyOffsets, event.key)) {
    nextIndex = (currentIndex + keyOffsets[event.key] + itemCount) % itemCount;
  } else if (event.key === "Home") {
    nextIndex = 0;
  } else if (event.key === "End") {
    nextIndex = itemCount - 1;
  }
  if (nextIndex === null || itemCount < 1) return;

  event.preventDefault();
  const tablist = event.currentTarget.closest('[role="tablist"]');
  onSelect(nextIndex);
  window.requestAnimationFrame(() => {
    const tabs = tablist ? tablist.querySelectorAll('[role="tab"]') : [];
    if (tabs[nextIndex]) tabs[nextIndex].focus();
  });
}

const DEFAULT_LEVERS = {
  demand_multiplier: 1.0,
  renewables_capex_multiplier: 1.0,
  fossil_fuel_price_multiplier: 1.0,
  carbon_price_usd_per_tco2: 0.0,
};

const ENERGY_MODEL_OPTIONS = [
  { value: "calliope", label: "Calliope", runtimeStatus: "Executable now" },
];

const PROJECT_TYPE_OPTIONS = [
  { value: "energy-only", projectType: "energy", label: "Energy" },
  { value: "energy-development", projectType: "energy-development", label: "Energy-Development" },
];

const PROJECT_GEOGRAPHY_OPTIONS = [
  "Africa",
  "North Africa",
  "West Africa",
  "Central Africa",
  "East Africa",
  "Southern Africa",
  "South Africa",
  "India",
  "Brazil",
];

const DEFAULT_MODEL_ARCHITECTURE_ID = "energy-development";

const LANDING_HERO_BASE_TUNING = {
  scale: 1.16,
  curvature: 1,
  drift: 1,
  pulseSpeed: 1,
  interaction: 1,
  lines: 1.58,
  labels: 1,
  titleStrength: 1.35,
  pulses: 1,
  images: 1,
  contrast: 1.52,
  glow: 1.25,
  flashlight: 1.35,
  flashlightSize: 1,
};

const LANDING_HERO_DEFAULTS_PATH =
  String(window.EDIM_HERO_DEFAULTS_PATH || "").trim() || "./hero-defaults.json";

function getFrontendApiBase() {
  const api = window.EDIM_API_CLIENT || {};
  return typeof api.getApiBase === "function" ? api.getApiBase() : window.location.origin;
}

function normalizeLandingHeroTuning(values) {
  const source = values && typeof values === "object" ? values : {};
  return Object.keys(LANDING_HERO_BASE_TUNING).reduce((acc, key) => {
    const fallback = Number(LANDING_HERO_BASE_TUNING[key] || 1);
    const value = Number(source[key]);
    acc[key] = Number.isFinite(value) ? value : fallback;
    return acc;
  }, {});
}

function normalizeLandingHeroDefaults(payload) {
  const source = payload && typeof payload === "object" ? payload : {};
  const tuningSource = source.tuningDefaults && typeof source.tuningDefaults === "object"
    ? source.tuningDefaults
    : source.tuning && typeof source.tuning === "object"
      ? source.tuning
      : source;
  return {
    schema: "edim_hero_background_defaults",
    theme: source.theme || "solar",
    tuningDefaults: normalizeLandingHeroTuning(tuningSource),
  };
}

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

const LOCATION_MAP_COUNTRIES_GEOJSON_PATH =
  String(window.EDIM_COUNTRIES_GEOJSON_PATH || "").trim() || "./geo/countries.geojson";

const MODEL_ARCHITECTURES_PATH =
  String(window.EDIM_MODEL_ARCHITECTURES_PATH || "").trim() || "./model_architectures.json";

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
    subtitle: "Intensity, sector split, indicator, geography, and structured scenario-target datasets",
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
    subtitle: "Downloadable model artifacts, diagnostics, and dashboard-ready results",
    stages: ["build_integrated", "complete"],
  },
];

const DEFAULT_FLOW_NODE_LAYOUT = {
  scenario: { x: 40, y: 30, w: 980, h: 650 },
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

const IO_WIRE_TYPE_STYLES = {
  aggregate: { label: "Aggregate flow", color: "#67e8f9" },
  scenario: { label: "Scenario package", color: "#67e8f9" },
  catalog: { label: "Catalog / metadata", color: "#38bdf8" },
  control: { label: "Controls / levers", color: "#a78bfa" },
  manifest: { label: "Manifest", color: "#818cf8" },
  "energy-config": { label: "Energy config", color: "#60a5fa" },
  "energy-scenario": { label: "Energy scenario", color: "#2563eb" },
  "energy-network": { label: "Network / grid", color: "#14b8a6" },
  technology: { label: "Technology data", color: "#2dd4bf" },
  "time-series": { label: "Time series", color: "#0ea5e9" },
  geospatial: { label: "Geography", color: "#34d399" },
  "mrio-scenario": { label: "MRIO scenario", color: "#f472b6" },
  "mrio-shock": { label: "MRIO-direct shock", color: "#fb7185" },
  mapping: { label: "Mapping", color: "#facc15" },
  calibration: { label: "Calibration", color: "#f59e0b" },
  validation: { label: "Validation", color: "#c084fc" },
  "energy-output": { label: "Energy output", color: "#22c55e" },
  "bridge-shock": { label: "Bridge shock", color: "#f97316" },
  "development-output": { label: "Development output", color: "#84cc16" },
  diagnostic: { label: "Diagnostic", color: "#94a3b8" },
  report: { label: "Report", color: "#e2e8f0" },
  package: { label: "Package / export", color: "#f8fafc" },
};

const IO_WIRE_GROUP_STYLES = {
  aggregate: { label: "Aggregate flow", color: "#67e8f9" },
  "scenario-definition": { label: "Scenario definition", color: "#5eead4" },
  "energy-input-package": { label: "Energy input package", color: "#38bdf8" },
  "energy-runtime": { label: "Energy runtime instructions", color: "#818cf8" },
  "energy-results": { label: "Solved energy outputs", color: "#22c55e" },
  "bridge-exchange": { label: "Bridge exchange package", color: "#fb923c" },
  "mrio-input-package": { label: "MRIO input package", color: "#f472b6" },
  "mrio-direct-assumptions": { label: "MRIO-direct assumptions", color: "#fb7185" },
  "geography-mapping": { label: "Geography / mapping", color: "#34d399" },
  "development-results": { label: "Development outputs", color: "#84cc16" },
  "diagnostics-artifacts": { label: "Diagnostics / artifacts", color: "#94a3b8" },
};

const DATA_WIRE_GROUP_STYLES = {
  "data-scenario": { label: "Scenario data", color: "#22d3ee" },
  "data-energy-config": { label: "Energy config", color: "#60a5fa" },
  "data-energy-scenario": { label: "Energy scenario settings", color: "#2563eb" },
  "data-network-spatial": { label: "Grid / geography", color: "#14b8a6" },
  "data-technology": { label: "Technology assumptions", color: "#2dd4bf" },
  "data-time-series": { label: "Resource / demand series", color: "#0ea5e9" },
  "data-mrio-scenario": { label: "MRIO scenario / shocks", color: "#fb7185" },
  "data-mapping": { label: "Sector/geography mapping", color: "#fde047" },
  "data-calibration": { label: "Economic calibration", color: "#f59e0b" },
  "data-energy-output": { label: "Energy results", color: "#22c55e" },
  "data-bridge-output": { label: "Bridge shocks", color: "#fb923c" },
  "data-development-output": { label: "Development results", color: "#a3e635" },
};

const INFORMATION_LAYER_ORDER = [
  "aggregate",
  "scenario-definition",
  "energy-input-package",
  "energy-runtime",
  "energy-results",
  "bridge-exchange",
  "mrio-input-package",
  "mrio-direct-assumptions",
  "geography-mapping",
  "development-results",
  "diagnostics-artifacts",
];

const DATA_WIRE_GROUP_ORDER = [
  "aggregate",
  "data-scenario",
  "data-energy-config",
  "data-energy-scenario",
  "data-network-spatial",
  "data-technology",
  "data-time-series",
  "data-mrio-scenario",
  "data-mapping",
  "data-calibration",
  "data-energy-output",
  "data-bridge-output",
  "data-development-output",
];

const DATA_IO_WIRE_TYPES = new Set([
  "scenario",
  "control",
  "energy-config",
  "energy-scenario",
  "energy-network",
  "technology",
  "time-series",
  "geospatial",
  "mrio-scenario",
  "mrio-shock",
  "mapping",
  "calibration",
  "energy-output",
  "bridge-shock",
  "development-output",
]);

function normalizeIoWireType(type) {
  const key = String(type || "aggregate").trim().toLowerCase();
  return IO_WIRE_TYPE_STYLES[key] ? key : "aggregate";
}

function ioWireGroup(type) {
  const normalized = normalizeIoWireType(type);
  if (normalized === "aggregate") return "aggregate";
  if (["scenario", "control", "catalog"].includes(normalized)) return "scenario-definition";
  if (["energy-config", "energy-scenario", "energy-network", "technology", "time-series"].includes(normalized)) return "energy-input-package";
  if (["geospatial", "mapping"].includes(normalized)) return "geography-mapping";
  if (["mrio-scenario", "mrio-shock", "calibration"].includes(normalized)) return "mrio-input-package";
  if (normalized === "energy-output") return "energy-results";
  if (normalized === "bridge-shock") return "bridge-exchange";
  if (normalized === "development-output") return "development-results";
  if (["manifest", "validation", "diagnostic", "report", "package"].includes(normalized)) return "diagnostics-artifacts";
  return "aggregate";
}

function ioInformationLayer(type, explicitLayer) {
  const explicit = String(explicitLayer || "").trim();
  if (explicit && IO_WIRE_GROUP_STYLES[explicit]) return explicit;
  return ioWireGroup(type);
}

function ioWireDataGroup(type) {
  const normalized = normalizeIoWireType(type);
  if (["scenario", "control"].includes(normalized)) return "data-scenario";
  if (normalized === "energy-config") return "data-energy-config";
  if (normalized === "energy-scenario") return "data-energy-scenario";
  if (["energy-network", "geospatial"].includes(normalized)) return "data-network-spatial";
  if (normalized === "technology") return "data-technology";
  if (normalized === "time-series") return "data-time-series";
  if (["mrio-scenario", "mrio-shock"].includes(normalized)) return "data-mrio-scenario";
  if (normalized === "mapping") return "data-mapping";
  if (normalized === "calibration") return "data-calibration";
  if (normalized === "energy-output") return "data-energy-output";
  if (normalized === "bridge-shock") return "data-bridge-output";
  if (normalized === "development-output") return "data-development-output";
  return ioWireGroup(normalized);
}

function ioWireStyle(type) {
  return DATA_WIRE_GROUP_STYLES[type] || IO_WIRE_GROUP_STYLES[type] || IO_WIRE_GROUP_STYLES[ioWireGroup(type)] || IO_WIRE_GROUP_STYLES.aggregate;
}

function ioWireSourceStyle(type) {
  return IO_WIRE_TYPE_STYLES[normalizeIoWireType(type)] || IO_WIRE_TYPE_STYLES.aggregate;
}

function buildScenarioWireContext(scenarioKey, scenarioSelections) {
  const parsed = parseScenarioDimensions(scenarioKey) || {};
  const selections = scenarioSelections || {};
  const family = parsed.family || selections.family || "";
  return {
    scenarioKey: String(scenarioKey || ""),
    family,
    scenarioFamily: family,
    pathway: parsed.pathway || selections.pathway || "",
    generation: parsed.generation || selections.generation || "",
    transmission: parsed.transmission || selections.transmission || "",
    policy: typeof parsed.policy === "boolean" ? parsed.policy : Boolean(selections.policy),
  };
}

function activeWhenLabel(activeWhen) {
  if (!activeWhen || typeof activeWhen !== "object") return "";
  if (Array.isArray(activeWhen.anyOf)) {
    return activeWhen.anyOf.map(activeWhenLabel).filter(Boolean).join(" or ");
  }
  if (Array.isArray(activeWhen.allOf)) {
    return activeWhen.allOf.map(activeWhenLabel).filter(Boolean).join(" and ");
  }
  return Object.entries(activeWhen)
    .filter(([key]) => key !== "anyOf" && key !== "allOf")
    .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(" / ") : String(value)}`)
    .join(", ");
}

function conditionValueMatches(actual, expected) {
  if (Array.isArray(expected)) return expected.some((item) => conditionValueMatches(actual, item));
  if (typeof expected === "boolean") return Boolean(actual) === expected;
  return String(actual || "").toLowerCase() === String(expected || "").toLowerCase();
}

function activeWhenMatches(activeWhen, context) {
  if (!activeWhen || typeof activeWhen !== "object") return true;
  if (Array.isArray(activeWhen.anyOf)) {
    return activeWhen.anyOf.some((rule) => activeWhenMatches(rule, context));
  }
  if (Array.isArray(activeWhen.allOf)) {
    return activeWhen.allOf.every((rule) => activeWhenMatches(rule, context));
  }
  const fieldMap = {
    scenarioKey: context.scenarioKey,
    scenario_key: context.scenarioKey,
    family: context.family,
    scenarioFamily: context.scenarioFamily,
    scenario_family: context.scenarioFamily,
    pathway: context.pathway,
    generation: context.generation,
    transmission: context.transmission,
    policy: context.policy,
  };
  return Object.entries(activeWhen).every(([key, expected]) => {
    if (key === "anyOf" || key === "allOf") return true;
    return conditionValueMatches(fieldMap[key], expected);
  });
}

function normalizeIoLayer(layer, parent, index) {
  const layerId = String((layer && (layer.id || layer.key || layer.path)) || `${parent.id}-layer-${index + 1}`).trim();
  const layerLabel = String((layer && (layer.label || layer.name || layer.path)) || layerId).trim();
  return {
    id: layerId,
    label: layerLabel,
    type: normalizeIoWireType((layer && layer.type) || parent.type),
    activeWhen: (layer && (layer.activeWhen || layer.active_when)) || null,
    informationLayer: String((layer && (layer.informationLayer || layer.information_layer)) || "").trim(),
    purpose: String((layer && layer.purpose) || "").trim(),
    granularity: String((layer && layer.granularity) || "").trim(),
    dataGroup: String((layer && (layer.dataGroup || layer.data_group)) || "").trim(),
    dataGroupLabel: String((layer && (layer.dataGroupLabel || layer.data_group_label)) || "").trim(),
    variantLabel: String((layer && (layer.variantLabel || layer.variant_label)) || "").trim(),
    parentId: parent.id,
    parentLabel: parent.label,
  };
}

function normalizeEdgeIo(edge) {
  const rawRows = Array.isArray(edge && edge.io)
    ? edge.io
    : Array.isArray(edge && edge.ios)
      ? edge.ios
      : Array.isArray(edge && edge.wires)
        ? edge.wires
        : [];
  return rawRows
    .map((row, index) => {
      const id = String((row && (row.id || row.io_id || row.key)) || `io-${index + 1}`).trim();
      const label = String((row && (row.label || row.name)) || id).trim();
      return {
        id,
        label,
        type: normalizeIoWireType(row && row.type),
        activeWhen: (row && (row.activeWhen || row.active_when)) || null,
        informationLayer: String((row && (row.informationLayer || row.information_layer)) || "").trim(),
        purpose: String((row && row.purpose) || "").trim(),
        granularity: String((row && row.granularity) || "").trim(),
        dataGroup: String((row && (row.dataGroup || row.data_group)) || "").trim(),
        dataGroupLabel: String((row && (row.dataGroupLabel || row.data_group_label)) || "").trim(),
        variantLabel: String((row && (row.variantLabel || row.variant_label)) || "").trim(),
        layers: Array.isArray(row && (row.layers || row.dataLayers))
          ? (row.layers || row.dataLayers)
              .map((layer, layerIndex) => normalizeIoLayer(layer, { id, label, type: normalizeIoWireType(row && row.type) }, layerIndex))
              .filter((layer) => layer.id && layer.label)
          : [],
      };
    })
    .filter((row) => row.id && row.label);
}

const DEFAULT_FLOW_CANVAS_SIZE = { width: 1480, height: 1740 };
const FLOW_CANVAS_NODE_PADDING = 96;
const DEFAULT_FLOW_NODE_ORDER = ["scenario", "calliope_data", "adapter", "mrio_data", "calliope", "bridge", "mrio", "outputs"];
const DEFAULT_FIXED_FLOW_NODES = [];

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
            io: normalizeEdgeIo(edge),
          }))
          .filter((edge) => edge.from && edge.to)
      : DEFAULT_FLOW_EDGES.map((edge) => ({ ...edge, io: normalizeEdgeIo(edge) })),
    order,
    fixedNodes: Array.isArray(flow.fixedNodes) ? flow.fixedNodes.map((id) => String(id)) : [...DEFAULT_FIXED_FLOW_NODES],
  };
}

function normalizeFlowDefinition(flow) {
  if (flow && Array.isArray(flow.nodes)) return normalizeMainUiFlow(flow);
  if (flow && flow.nodes && typeof flow.nodes === "object") {
    const nodes = {};
    const order = [];
    Object.entries(flow.nodes).forEach(([id, rect]) => {
      if (!rect) return;
      nodes[id] = { ...rect };
      order.push(id);
    });
    return {
      canvas: flow.canvas || { ...DEFAULT_FLOW_CANVAS_SIZE },
      nodes,
      edges: Array.isArray(flow.edges)
        ? flow.edges.map((edge) => ({ ...edge, io: normalizeEdgeIo(edge) }))
        : DEFAULT_FLOW_EDGES.map((edge) => ({ ...edge, io: normalizeEdgeIo(edge) })),
      order: Array.isArray(flow.order) && flow.order.length ? [...flow.order] : order,
      fixedNodes: Array.isArray(flow.fixedNodes) ? flow.fixedNodes.map((id) => String(id)) : [...DEFAULT_FIXED_FLOW_NODES],
    };
  }
  return defaultFlowDefinition();
}

function centerExpandedFlowNode(definition, nodeId) {
  const rect = definition && definition.nodes ? definition.nodes[nodeId] : null;
  const canvas = definition && definition.canvas ? definition.canvas : DEFAULT_FLOW_CANVAS_SIZE;
  if (!rect) return definition;

  const baseWidth = Number(rect.w) || 320;
  const expandedWidth = baseWidth + Math.min(120, Math.max(48, Math.round(baseWidth * 0.16)));
  let canvasWidth = Number(canvas.width) || DEFAULT_FLOW_CANVAS_SIZE.width;
  Object.values(definition.nodes || {}).forEach((nodeRect) => {
    const nodeX = Number(nodeRect && nodeRect.x);
    const nodeWidth = Number(nodeRect && nodeRect.w);
    if (!Number.isFinite(nodeX) || !Number.isFinite(nodeWidth)) return;
    canvasWidth = Math.max(canvasWidth, nodeX + nodeWidth + FLOW_CANVAS_NODE_PADDING);
  });
  const centeredX = Math.max(12, Math.round((canvasWidth - expandedWidth) / 2));

  return {
    ...definition,
    nodes: {
      ...definition.nodes,
      [nodeId]: { ...rect, x: centeredX },
    },
  };
}

function defaultArchitectureCatalog() {
  return {
    schemaVersion: "edim_model_architecture_catalog",
    defaultArchitectureId: DEFAULT_MODEL_ARCHITECTURE_ID,
    architectures: [
      {
        id: DEFAULT_MODEL_ARCHITECTURE_ID,
        label: "Energy-Development",
        shortLabel: "Energy-Development",
        description: "Full EDIM architecture linking the energy model, bridge, and MRIO/development impacts.",
        requiresMrio: true,
        requiresBridge: true,
        resultTabs: ["overview", "system", "development", "method"],
        enabledDatasetLayers: ["calliope", "scenario", "mrio", "bridge"],
        boxes: ARCHITECTURE_BOXES.map((box) => ({ ...box })),
        graph: defaultFlowDefinition(),
        outputArtifacts: [],
      },
    ],
  };
}

function normalizeArchitecture(raw) {
  const baseArchitecture = defaultArchitectureCatalog().architectures[0];
  const id = String((raw && raw.id) || baseArchitecture.id).trim() || baseArchitecture.id;
  const boxes = Array.isArray(raw && raw.boxes) && raw.boxes.length
    ? raw.boxes.map((box) => ({ ...box }))
    : baseArchitecture.boxes.map((box) => ({ ...box }));
  return {
    ...baseArchitecture,
    ...(raw || {}),
    id,
    label: String((raw && raw.label) || baseArchitecture.label),
    shortLabel: String((raw && raw.shortLabel) || (raw && raw.label) || baseArchitecture.shortLabel),
    description: String((raw && raw.description) || baseArchitecture.description),
    requiresMrio: raw && Object.prototype.hasOwnProperty.call(raw, "requiresMrio") ? Boolean(raw.requiresMrio) : true,
    requiresBridge: raw && Object.prototype.hasOwnProperty.call(raw, "requiresBridge") ? Boolean(raw.requiresBridge) : true,
    enabledDatasetLayers: Array.isArray(raw && raw.enabledDatasetLayers)
      ? raw.enabledDatasetLayers.map((layer) => String(layer))
      : ["calliope", "scenario", "mrio", "bridge"],
    resultTabs: Array.isArray(raw && raw.resultTabs) && raw.resultTabs.length
      ? raw.resultTabs.map((tab) => String(tab))
      : ["overview", "system", "development", "method"],
    boxes,
    graph: normalizeFlowDefinition((raw && raw.graph) || (raw && raw.mainUiFlow)),
    outputArtifacts: Array.isArray(raw && raw.outputArtifacts) ? raw.outputArtifacts.map((row) => ({ ...row })) : [],
  };
}

function normalizeArchitectureCatalog(raw) {
  const baseCatalog = defaultArchitectureCatalog();
  const architectures = Array.isArray(raw && raw.architectures)
    ? raw.architectures.map(normalizeArchitecture).filter((row) => row.id)
    : baseCatalog.architectures.map(normalizeArchitecture);
  const rows = architectures.length ? architectures : baseCatalog.architectures.map(normalizeArchitecture);
  const defaultArchitectureId = String((raw && raw.defaultArchitectureId) || baseCatalog.defaultArchitectureId);
  return {
    ...(raw || {}),
    schemaVersion: String((raw && raw.schemaVersion) || baseCatalog.schemaVersion),
    defaultArchitectureId: rows.some((row) => row.id === defaultArchitectureId) ? defaultArchitectureId : rows[0].id,
    architectures: rows,
  };
}

function architectureById(catalog, architectureId) {
  const normalized = catalog && Array.isArray(catalog.architectures) ? catalog : defaultArchitectureCatalog();
  return (
    normalized.architectures.find((row) => row.id === architectureId) ||
    normalized.architectures.find((row) => row.id === normalized.defaultArchitectureId) ||
    normalized.architectures[0] ||
    normalizeArchitecture(null)
  );
}

function architectureIncludesDevelopment(architecture) {
  return Boolean(architecture && architecture.requiresMrio !== false);
}

function architectureOutputArtifacts(architecture) {
  return Array.isArray(architecture && architecture.outputArtifacts) ? architecture.outputArtifacts : [];
}

function architectureResultTabs(architecture) {
  const tabs = Array.isArray(architecture && architecture.resultTabs) ? architecture.resultTabs : [];
  return tabs.length ? tabs : ["overview", "system", "development", "method"];
}

function scenarioCatalogChannel(catalog, configKey) {
  const channels = Array.isArray(catalog && catalog.scenario_channels) ? catalog.scenario_channels : [];
  return channels.find((row) => String(row && row.config_key) === configKey) || null;
}

function scenarioCatalogOptions(catalog, configKey) {
  const channel = scenarioCatalogChannel(catalog, configKey);
  return Array.isArray(channel && channel.options) ? channel.options : [];
}

function optionMetadata(option, keyName) {
  const metadata = option && option.metadata && typeof option.metadata === "object" ? { ...option.metadata } : {};
  const value = option && Object.prototype.hasOwnProperty.call(option, "value") ? option.value : "";
  if (keyName && value !== "") metadata[keyName] = metadata[keyName] || value;
  metadata.label = metadata.label || (option && option.label) || value;
  metadata.description = metadata.description || (option && option.description) || "";
  return metadata;
}

function rowsFromScenarioChannel(catalog, configKey, keyName) {
  return scenarioCatalogOptions(catalog, configKey).map((option) => optionMetadata(option, keyName));
}

function yearsFromScenarioChannel(catalog) {
  return scenarioCatalogOptions(catalog, "scenario.target_year")
    .map((option) => Number(option && Object.prototype.hasOwnProperty.call(option, "value") ? option.value : option))
    .filter((year) => Number.isFinite(year));
}

function energyModelCatalogOptions(catalog) {
  const rows = scenarioCatalogOptions(catalog, "energy_model_engine");
  return rows.length ? rows : ENERGY_MODEL_OPTIONS;
}

function projectTypeForArchitecture(architectureId) {
  const option = PROJECT_TYPE_OPTIONS.find((row) => row.value === architectureId);
  return option ? option.projectType : "energy-development";
}

function projectTypeLabel(project) {
  const architectureId = String((project && project.model_architecture_id) || "").trim();
  const projectType = String((project && project.project_type) || "").trim();
  const option =
    PROJECT_TYPE_OPTIONS.find((row) => row.value === architectureId) ||
    PROJECT_TYPE_OPTIONS.find((row) => row.projectType === projectType);
  return option ? option.label : projectType || architectureId || "Energy-Development";
}

function projectGeographyLabel(value) {
  const label = String(value || "").trim();
  if (!label) return "";
  return label === "Africa-wide" ? "Africa" : label;
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
  completed: { label: "Succeeded", className: "badge badge-succeeded" },
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

function isResetStatus(status) {
  return RESET_JOB_STATUSES.has(normalizeStatus(status));
}

function displayStatus(status) {
  const key = normalizeStatus(status);
  return STATUS_THEME[key] || { label: status || "Unknown", className: "badge badge-neutral" };
}

const evidenceComponents = window.EDIM_EVIDENCE || {};
const EvidenceBadge = evidenceComponents.EvidenceBadge || function EvidenceBadgeFallback({ status }) {
  const normalized = String(status || "not_evaluated").trim().toLowerCase();
  if (normalized === "exploratory_only" || normalized === "not_evaluated") return null;
  return <StatusBadge status={normalized} />;
};
const evidenceFromSummary = evidenceComponents.evidenceFromSummary || (() => ({ status: "not_evaluated", score: 0 }));
const evidenceFromModel = evidenceComponents.evidenceFromModel || ((model) => ({
  status: String((model && model.evidence_status) || "not_evaluated"),
  score: Number(model && model.evidence_score) || 0,
  summary: String((model && model.evidence_summary) || ""),
}));
const ENTITY_VISUAL_STATUS_COLORS = {
  draft: "#91A0B7",
  queued: "#F2C14E",
  running: "#4CB6E8",
  succeeded: "#48C78E",
  failed: "#F06B67",
};

function visualHash(value) {
  const text = String(value || "");
  let hash = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function visualRandom(seed) {
  let state = seed >>> 0;
  return () => {
    state += 0x6D2B79F5;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function visualPolar(radius, angle, center = 50) {
  return {
    x: center + Math.cos(angle) * radius,
    y: center + Math.sin(angle) * radius,
  };
}

function visualSectorPath(startAngle, endAngle, radius = 54) {
  const span = Math.max(0, endAngle - startAngle);
  const start = visualPolar(radius, startAngle);
  const end = visualPolar(radius, endAngle);
  const largeArc = span > Math.PI ? 1 : 0;
  return [
    "M 50 50",
    `L ${start.x.toFixed(2)} ${start.y.toFixed(2)}`,
    `A ${radius} ${radius} 0 ${largeArc} 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)}`,
    "Z",
  ].join(" ");
}

function visualSmoothClosedPath(points) {
  if (!Array.isArray(points) || points.length < 3) return "";
  const size = points.length;
  const commands = [`M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)}`];
  for (let index = 0; index < size; index += 1) {
    const previous = points[(index - 1 + size) % size];
    const current = points[index];
    const next = points[(index + 1) % size];
    const afterNext = points[(index + 2) % size];
    const firstControl = {
      x: current.x + (next.x - previous.x) / 6,
      y: current.y + (next.y - previous.y) / 6,
    };
    const secondControl = {
      x: next.x - (afterNext.x - current.x) / 6,
      y: next.y - (afterNext.y - current.y) / 6,
    };
    commands.push(
      `C ${firstControl.x.toFixed(2)} ${firstControl.y.toFixed(2)} ${secondControl.x.toFixed(2)} ${secondControl.y.toFixed(2)} ${next.x.toFixed(2)} ${next.y.toFixed(2)}`
    );
  }
  return `${commands.join(" ")} Z`;
}

function visualContourPath(seed, {
  center = 50,
  baseRadius = 30,
  variance = 6,
  eccentricity = 2,
  pointCount = 56,
} = {}) {
  const random = visualRandom(seed);
  const knotCount = 9 + Math.floor(random() * 5);
  let radialNoise = Array.from({ length: knotCount }, () => random() * 2 - 1);
  for (let pass = 0; pass < 2; pass += 1) {
    radialNoise = radialNoise.map((value, index) => (
      radialNoise[(index - 1 + knotCount) % knotCount]
      + value * 2
      + radialNoise[(index + 1) % knotCount]
    ) / 4);
  }
  const centerOffsetAngle = random() * Math.PI * 2;
  const offsetX = Math.cos(centerOffsetAngle) * eccentricity;
  const offsetY = Math.sin(centerOffsetAngle) * eccentricity;
  const points = Array.from({ length: pointCount }, (_, index) => {
    const angle = (index / pointCount) * Math.PI * 2;
    const knotPosition = (index / pointCount) * knotCount;
    const knotIndex = Math.floor(knotPosition) % knotCount;
    const nextKnot = (knotIndex + 1) % knotCount;
    const local = knotPosition - Math.floor(knotPosition);
    const eased = local * local * (3 - 2 * local);
    const noise = radialNoise[knotIndex] * (1 - eased) + radialNoise[nextKnot] * eased;
    const radius = Math.max(4, Math.min(42, baseRadius + variance * noise * 1.9));
    const point = visualPolar(radius, angle, center);
    return {
      x: point.x + offsetX,
      y: point.y + offsetY,
    };
  });
  return visualSmoothClosedPath(points);
}

function visualHsl(hue, saturation, lightness) {
  const normalizedHue = ((Number(hue) % 360) + 360) % 360;
  return `hsl(${normalizedHue.toFixed(1)}, ${saturation}%, ${lightness}%)`;
}

function visualColorHarmony(seed, sequence = 0) {
  const random = visualRandom(seed);
  const baseHue = (seed % 360 + sequence * 137.508) % 360;
  const analogousDirection = random() > 0.5 ? 1 : -1;
  const analogousHue = baseHue + analogousDirection * (28 + random() * 24);
  const complementHue = baseHue + 166 + random() * 28;
  return {
    primary: visualHsl(baseHue, 76, 57),
    analogous: visualHsl(analogousHue, 72, 62),
    complement: visualHsl(complementHue, 74, 58),
    highlight: visualHsl(baseHue + analogousDirection * 12, 84, 78),
    shadow: visualHsl(baseHue + 8, 52, 17),
  };
}

function modelVisualDescriptor(row) {
  const source = row && typeof row === "object" ? row : {};
  const configuration = runConfigurationPayload(source);
  const architectureId = String(source.architecture_id || configuration.model_architecture_id || "energy-development");
  const scenarioKey = String(source.scenario_key || configuration.energy_scenario_key || "");
  const targetScenarioId = String(source.target_scenario_id || configuration.mrio_scenario_id || "");
  const targetYear = Number(source.target_year || configuration.target_year) || null;
  const levers = configuration.levers && typeof configuration.levers === "object" ? configuration.levers : {};
  const artifactCount = Number(source.artifact_count)
    || (Array.isArray(source.artifact_catalog) ? source.artifact_catalog.length : 0);
  const summaryAvailable = Boolean(source.summary_available || source.summary);
  const kpiScopeCount = Number(source.kpi_scope_count)
    || (summaryAvailable ? (architectureId === "energy-development" ? 8 : 5) : 0);
  const adjustedLeverCount = Object.entries(levers).filter(([key, value]) => {
    if (!Object.prototype.hasOwnProperty.call(DEFAULT_LEVERS, key)) return true;
    const parsed = Number(value);
    return !Number.isFinite(parsed) || Math.abs(parsed - Number(DEFAULT_LEVERS[key])) > 1e-9;
  }).length;
  return {
    runId: String(source.run_id || ""),
    projectRunNumber: Number(source.project_run_number || source.run_number) || 0,
    status: normalizeStatus(source.status) || "draft",
    architectureId,
    scenarioKey,
    targetScenarioId,
    targetYear,
    runProfile: String(source.run_profile || configuration.run_profile || "dev"),
    leverCount: source.lever_count == null ? adjustedLeverCount : Number(source.lever_count) || 0,
    artifactCount,
    kpiScopeCount,
    summaryAvailable,
    evidenceStatus: String(source.evidence_status || "not_evaluated"),
    evidenceScore: Number(source.evidence_score) || 0,
  };
}

function modelVisualSeed(descriptor) {
  return [
    descriptor.runId,
    descriptor.projectRunNumber,
    descriptor.architectureId,
    descriptor.scenarioKey,
    descriptor.targetScenarioId,
    descriptor.targetYear,
    descriptor.runProfile,
  ].join("|");
}

function ModelIdentityShape({
  descriptor,
  subdued = false,
  blurFilterIds = null,
  idNamespace = "",
}) {
  const seed = visualHash(modelVisualSeed(descriptor));
  const idKey = idNamespace ? `${seed}-${visualHash(idNamespace)}` : String(seed);
  const random = visualRandom(seed);
  const integrated = descriptor.architectureId === "energy-development";
  const semanticPaletteSeed = visualHash([
    descriptor.architectureId,
    descriptor.scenarioKey,
    descriptor.targetScenarioId,
    descriptor.runProfile,
  ].join("|"));
  const harmony = visualColorHarmony(semanticPaletteSeed, Math.max(0, descriptor.projectRunNumber - 1));
  const statusColor = ENTITY_VISUAL_STATUS_COLORS[descriptor.status] || ENTITY_VISUAL_STATUS_COLORS.draft;
  const kpiReach = Math.min(4.5, descriptor.kpiScopeCount * 0.42);
  const leverVariance = Math.min(3.5, descriptor.leverCount * 0.65);
  const outerContour = visualContourPath(seed ^ 0x9E3779B9, {
    baseRadius: 29 + kpiReach,
    variance: 4.6 + leverVariance,
    eccentricity: integrated ? 2.8 : 1.4,
  });
  const innerContour = visualContourPath(seed ^ 0x85EBCA6B, {
    baseRadius: 17 + Math.min(3, descriptor.artifactCount * 0.25),
    variance: 4.2 + (descriptor.projectRunNumber % 3),
    eccentricity: 1.8,
    pointCount: 44,
  });
  const accentContour = visualContourPath(seed ^ 0xC2B2AE35, {
    baseRadius: 10 + Math.min(4, descriptor.leverCount * 0.7),
    variance: 3.2 + Math.min(2.5, descriptor.kpiScopeCount * 0.2),
    eccentricity: 7,
    pointCount: 40,
  });
  const anchorAngle = random() * Math.PI * 2;
  const anchor = visualPolar(12 + random() * 13, anchorAngle);
  const gradientAngle = random() * Math.PI * 2;
  const gradientVector = {
    x1: 50 - Math.cos(gradientAngle) * 48,
    y1: 50 - Math.sin(gradientAngle) * 48,
    x2: 50 + Math.cos(gradientAngle) * 48,
    y2: 50 + Math.sin(gradientAngle) * 48,
  };
  const mainGradientId = `identity-main-${idKey}`;
  const coreGradientId = `identity-core-${idKey}`;
  const accentGradientId = `identity-accent-${idKey}`;
  const statusGradientId = `identity-status-${idKey}`;
  const hazeFilterId = (blurFilterIds && blurFilterIds.haze) || `identity-haze-${idKey}`;
  const softFilterId = (blurFilterIds && blurFilterIds.soft) || `identity-soft-${idKey}`;
  const detailFilterId = (blurFilterIds && blurFilterIds.detail) || `identity-detail-${idKey}`;
  return (
    <g className={`entity-identity-shape entity-identity-shape--${descriptor.status}`}>
      <defs>
        <linearGradient
          id={mainGradientId}
          gradientUnits="userSpaceOnUse"
          x1={gradientVector.x1}
          y1={gradientVector.y1}
          x2={gradientVector.x2}
          y2={gradientVector.y2}
        >
          <stop offset="0%" stopColor={harmony.primary} stopOpacity="0.72" />
          <stop offset="52%" stopColor={harmony.analogous} />
          <stop offset="100%" stopColor={harmony.complement} stopOpacity="0.68" />
        </linearGradient>
        <radialGradient id={coreGradientId} cx="36%" cy="30%" r="74%">
          <stop offset="0%" stopColor={harmony.highlight} />
          <stop offset="42%" stopColor={harmony.primary} stopOpacity="0.92" />
          <stop offset="78%" stopColor={harmony.complement} stopOpacity="0.56" />
          <stop offset="100%" stopColor={harmony.complement} stopOpacity="0" />
        </radialGradient>
        <radialGradient id={accentGradientId} cx="42%" cy="38%" r="68%">
          <stop offset="0%" stopColor={harmony.highlight} stopOpacity="0.9" />
          <stop offset="42%" stopColor={harmony.analogous} stopOpacity="0.7" />
          <stop offset="76%" stopColor={harmony.primary} stopOpacity="0.24" />
          <stop offset="100%" stopColor={harmony.primary} stopOpacity="0" />
        </radialGradient>
        <radialGradient id={statusGradientId} cx="38%" cy="34%" r="68%">
          <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.82" />
          <stop offset="28%" stopColor={statusColor} stopOpacity="0.9" />
          <stop offset="68%" stopColor={statusColor} stopOpacity="0.38" />
          <stop offset="100%" stopColor={harmony.shadow} stopOpacity="0" />
        </radialGradient>
        {blurFilterIds ? null : (
          <>
            <filter id={hazeFilterId} x="-35%" y="-35%" width="170%" height="170%">
              <feGaussianBlur stdDeviation={subdued ? "5.2" : "4.4"} />
            </filter>
            <filter id={softFilterId} x="-25%" y="-25%" width="150%" height="150%">
              <feGaussianBlur stdDeviation={subdued ? "3.1" : "2.35"} />
            </filter>
            <filter id={detailFilterId} x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation={subdued ? "2.4" : "1.65"} />
            </filter>
          </>
        )}
      </defs>
      <path
        d={outerContour}
        fill={`url(#${mainGradientId})`}
        fillOpacity={subdued ? 0.34 : 0.52}
        filter={`url(#${hazeFilterId})`}
        className="identity-gradient-layer identity-gradient-layer--haze"
      />
      <path
        d={outerContour}
        fill={`url(#${mainGradientId})`}
        fillOpacity={subdued ? 0.58 : 0.82}
        filter={`url(#${softFilterId})`}
      />
      <path
        d={innerContour}
        fill={`url(#${coreGradientId})`}
        fillOpacity={subdued ? 0.5 : 0.78}
        filter={`url(#${detailFilterId})`}
        className="identity-gradient-layer identity-gradient-layer--core"
      />
      <path
        d={accentContour}
        fill={`url(#${accentGradientId})`}
        fillOpacity={subdued ? 0.44 : 0.76}
        filter={`url(#${detailFilterId})`}
        className="identity-gradient-layer identity-gradient-layer--accent"
      />
      <ellipse
        cx={anchor.x}
        cy={anchor.y}
        rx={integrated ? "11" : "9"}
        ry={integrated ? "8.6" : "7.2"}
        fill={`url(#${accentGradientId})`}
        fillOpacity={subdued ? 0.4 : 0.66}
        filter={`url(#${detailFilterId})`}
        transform={`rotate(${seed % 180} ${anchor.x.toFixed(2)} ${anchor.y.toFixed(2)})`}
      />
      <circle
        cx={anchor.x}
        cy={anchor.y}
        r={integrated ? "7.2" : "6.2"}
        fill={`url(#${statusGradientId})`}
        fillOpacity={subdued ? 0.58 : 0.84}
        filter={`url(#${detailFilterId})`}
        className="identity-gradient-layer identity-gradient-layer--status"
      />
    </g>
  );
}

function ModelIdentityCircleField({
  descriptor,
  className = "",
  idNamespace = "model",
  subdued = false,
}) {
  const seed = visualHash(modelVisualSeed(descriptor));
  const idKey = `${seed}-${visualHash(idNamespace)}`;
  const harmony = visualColorHarmony(
    visualHash([
      descriptor.architectureId,
      descriptor.scenarioKey,
      descriptor.targetScenarioId,
      descriptor.runProfile,
    ].join("|")),
    Math.max(0, descriptor.projectRunNumber - 1)
  );
  const backdropId = `model-identity-backdrop-${idKey}`;
  return (
    <g
      className={`model-identity-circle-field ${className}`.trim()}
      data-model-circle={descriptor.runId || String(descriptor.projectRunNumber)}
    >
      <defs>
        <radialGradient id={backdropId} cx="34%" cy="28%" r="78%">
          <stop offset="0%" stopColor={harmony.primary} stopOpacity="0.34" />
          <stop offset="48%" stopColor={harmony.shadow} stopOpacity="0.78" />
          <stop offset="100%" stopColor="#060B13" />
        </radialGradient>
      </defs>
      <circle cx="50" cy="50" r="46" fill={`url(#${backdropId})`} />
      <ModelIdentityShape
        descriptor={descriptor}
        subdued={subdued}
        idNamespace={idNamespace}
      />
      <circle cx="50" cy="50" r="45" fill="#FFFFFF" fillOpacity="0.025" />
    </g>
  );
}

function ModelIdentityVisual({ run, className = "" }) {
  const descriptor = modelVisualDescriptor(run);
  const label = `${runLabel(run)} visual: ${displayStatus(descriptor.status).label}, ${descriptor.architectureId}, ${descriptor.kpiScopeCount} result indicators`;
  const seed = visualHash(modelVisualSeed(descriptor));
  const clipId = `model-identity-clip-${seed}`;
  return (
    <svg
      className={`entity-identity-visual model-identity-visual ${className}`.trim()}
      viewBox="0 0 100 100"
      role="img"
      aria-label={label}
      data-identity-revision={String(seed)}
    >
      <title>{label}</title>
      <defs>
        <clipPath id={clipId}>
          <circle cx="50" cy="50" r="46" />
        </clipPath>
      </defs>
      <g clipPath={`url(#${clipId})`}>
        <ModelIdentityCircleField
          descriptor={descriptor}
          idNamespace={`model-${descriptor.runId || descriptor.projectRunNumber}`}
        />
      </g>
    </svg>
  );
}

function projectVisualData(project) {
  const summary = project && project.visual_summary && typeof project.visual_summary === "object"
    ? project.visual_summary
    : {};
  const models = Array.isArray(summary.models) ? summary.models.map(modelVisualDescriptor) : [];
  const modelCount = Number(summary.model_count) || models.length;
  const completedCount = Number(summary.completed_count) || 0;
  const fingerprints = new Set(models.map((model) => [
    model.architectureId,
    model.scenarioKey,
    model.targetScenarioId,
    model.targetYear,
    model.runProfile,
    model.leverCount,
  ].join("|")));
  const variationScore = summary.variation_score == null
    ? (modelCount <= 1 ? 0 : (fingerprints.size - 1) / (modelCount - 1))
    : Number(summary.variation_score) || 0;
  return {
    models,
    modelCount,
    completedCount,
    activeCount: Number(summary.active_count) || 0,
    failedCount: Number(summary.failed_count) || 0,
    kpiScopeCount: Number(summary.kpi_scope_count) || 0,
    variationScore,
    evidenceStatus: String(summary.evidence_status || "not_evaluated"),
    exploratoryModelCount: Number(summary.exploratory_model_count) || 0,
    analystReviewModelCount: Number(summary.analyst_review_model_count) || 0,
  };
}

function ProjectIdentityVisual({ project, className = "" }) {
  const data = projectVisualData(project);
  const projectSeed = [
    project && project.project_id,
    project && project.geography,
    project && project.project_type,
    project && project.model_architecture_id,
  ].join("|");
  const seed = visualHash(projectSeed);
  const sectorModels = data.models;
  const sectorCount = sectorModels.length;
  const sectorSpan = sectorCount ? (Math.PI * 2) / sectorCount : Math.PI * 2;
  const sectorPhase = -Math.PI / 2;
  const sectorOverlap = Math.min(0.018, sectorSpan * 0.025);
  const sectorFeatherFilterId = `project-sector-feather-${seed}`;
  const sectors = sectorModels.map((descriptor, index) => {
    const startAngle = sectorPhase + index * sectorSpan - sectorOverlap;
    const endAngle = sectorPhase + (index + 1) * sectorSpan + sectorOverlap;
    const sectorMaskId = `project-sector-mask-${seed}-${index}`;
    return (
      <g
        key={descriptor.runId || `${descriptor.projectRunNumber}-${index}`}
        className="project-identity-sector"
        mask={`url(#${sectorMaskId})`}
        data-project-sector={String(index + 1)}
        data-project-run={descriptor.runId}
      >
        <defs>
          <mask
            id={sectorMaskId}
            x="0"
            y="0"
            width="100"
            height="100"
            maskUnits="userSpaceOnUse"
          >
            <rect x="0" y="0" width="100" height="100" fill="#000000" />
            {sectorCount === 1 ? (
              <circle
                cx="50"
                cy="50"
                r="52"
                fill="#FFFFFF"
              />
            ) : (
              <path
                d={visualSectorPath(startAngle, endAngle)}
                fill="#FFFFFF"
                filter={`url(#${sectorFeatherFilterId})`}
              />
            )}
          </mask>
        </defs>
        <ModelIdentityCircleField
          descriptor={descriptor}
          className="project-identity-sector-field"
          idNamespace={`project-${seed}-${index}`}
          subdued={sectorCount > 12}
        />
      </g>
    );
  });
  const clipId = `project-identity-clip-${seed}`;
  const emptyFieldId = `project-empty-field-${seed}`;
  const revisionSeed = visualHash([
    data.modelCount,
    data.completedCount,
    data.activeCount,
    data.failedCount,
    data.kpiScopeCount,
    data.variationScore.toFixed(4),
    ...data.models.map((descriptor) => [
      modelVisualSeed(descriptor),
      descriptor.status,
      descriptor.leverCount,
      descriptor.artifactCount,
      descriptor.kpiScopeCount,
    ].join(":")),
  ].join("|"));
  const label = `${(project && project.title) || "Project"} visual: ${data.modelCount} models, ${data.completedCount} complete, ${Math.round(data.variationScore * 100)} percent variation`;
  return (
    <svg
      className={`entity-identity-visual project-identity-visual ${className}`.trim()}
      viewBox="0 0 100 100"
      role="img"
      aria-label={label}
      data-identity-revision={String(revisionSeed)}
      data-sector-count={String(sectorCount)}
    >
      <title>{label}</title>
      <defs>
        <radialGradient id={emptyFieldId} cx="38%" cy="34%" r="70%">
          <stop offset="0%" stopColor="#8492A6" stopOpacity="0.54" />
          <stop offset="52%" stopColor="#263244" stopOpacity="0.46" />
          <stop offset="100%" stopColor="#060B13" stopOpacity="0" />
        </radialGradient>
        <filter
          id={sectorFeatherFilterId}
          x="-20%"
          y="-20%"
          width="140%"
          height="140%"
          colorInterpolationFilters="sRGB"
        >
          <feGaussianBlur stdDeviation={sectorCount > 12 ? "0.62" : "0.85"} />
        </filter>
        <clipPath id={clipId}>
          <circle cx="50" cy="50" r="46" />
        </clipPath>
      </defs>
      <g clipPath={`url(#${clipId})`}>
        <circle cx="50" cy="50" r="46" fill="#060B13" />
        {sectorCount ? sectors : (
          <circle
            cx="50"
            cy="50"
            r="31"
            fill={`url(#${emptyFieldId})`}
            className="identity-gradient-layer identity-gradient-layer--project-empty"
          />
        )}
        <circle cx="50" cy="50" r="45" fill="#FFFFFF" fillOpacity="0.025" />
      </g>
    </svg>
  );
}

function runExecutionId(row) {
  return String((row && (row.execution_id || row.run_id)) || "");
}

function runConfigurationPayload(rowOrPayload) {
  const source = rowOrPayload && typeof rowOrPayload === "object" ? rowOrPayload : {};
  const payload =
    source.configuration && typeof source.configuration === "object"
      ? source.configuration
      : source.request && typeof source.request === "object"
        ? source.request
        : source;
  const scenario = payload.scenario && typeof payload.scenario === "object" ? payload.scenario : {};
  const energyScenarioKey = payload.energy_scenario_key || scenario.energy_scenario_key || "";
  const mrioScenarioId = payload.mrio_scenario_id || scenario.target_scenario_id || scenario.mrio_scenario_id || "";
  const targetYear = payload.target_year || scenario.target_year || "";
  return {
    project_id: payload.project_id || source.project_id || "",
    run_name: payload.run_name || source.run_name || "",
    model_architecture_id: payload.model_architecture_id || "energy-development",
    energy_model_engine: payload.energy_model_engine || "calliope",
    energy_scenario_key: energyScenarioKey,
    mrio_scenario_id: mrioScenarioId,
    target_year: targetYear,
    run_profile: payload.run_profile || "dev",
    levers: payload.levers && typeof payload.levers === "object" ? payload.levers : {},
  };
}

function projectRunToDisplayRun(row) {
  const runId = String((row && row.run_id) || "");
  const executionId = runExecutionId(row);
  const status = normalizeStatus(row && row.status) || "draft";
  const request = runConfigurationPayload(row);
  return {
    request,
    configuration: row && row.configuration ? row.configuration : null,
    execution_id: executionId,
    run_id: runId,
    project_id: String((row && row.project_id) || request.project_id || ""),
    project_run_number: runProjectNumber(row) || 0,
    run_name: String((row && row.run_name) || request.run_name || ""),
    model_id: String((row && row.model_id) || runId),
    model_number: Number((row && row.model_number) || runProjectNumber(row) || 0),
    model_name: String((row && row.model_name) || (row && row.run_name) || request.run_name || ""),
    latest_execution_id: String((row && row.latest_execution_id) || executionId),
    evidence_status: String((row && row.evidence_status) || "not_evaluated"),
    evidence_score: Number((row && row.evidence_score) || 0),
    evidence_summary: String((row && row.evidence_summary) || ""),
    status,
    stage: String((row && row.stage) || status),
    progress: toNumber(row && row.progress),
    message: String((row && row.message) || ""),
    queue_position: row && row.queue_position != null ? row.queue_position : null,
    worker_pid: row && row.worker_pid != null ? row.worker_pid : null,
    worker_id: String((row && row.worker_id) || ""),
    cancellation_requested: Boolean(row && row.cancellation_requested),
    created_at: String((row && row.created_at) || ""),
    updated_at: row && row.updated_at ? row.updated_at : null,
    started_at: row && row.started_at ? row.started_at : null,
    finished_at: row && row.finished_at ? row.finished_at : null,
    summary_available: Boolean(row && row.summary_available),
    source_run_id: String((row && row.source_run_id) || ""),
    error: row && row.error ? String(row.error) : null,
    artifacts:
      runId && status === "succeeded"
        ? {
            run_id: runId,
            summary_url: `/api/runs/${encodeURIComponent(runId)}/summary`,
            csv_url: `/api/runs/${encodeURIComponent(runId)}/artifacts/results_csv`,
          }
        : null,
    summary: row && row.summary ? row.summary : null,
  };
}

function runProjectNumber(row) {
  const value = Number(row && (row.project_run_number || row.run_number));
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : null;
}

function runCustomName(row) {
  return String((row && (row.run_name || (row.request && row.request.run_name))) || "").trim();
}

function runLabel(row) {
  if (!row) return "-";
  const number = runProjectNumber(row);
  const base = number ? `Model ${number}` : "Model";
  const name = runCustomName(row);
  return name ? `${base}: ${name}` : base;
}

function modelDisplayName(row) {
  const name = runCustomName(row);
  if (name) return name;
  const number = runProjectNumber(row);
  return number ? `Model ${number}` : "Untitled model";
}

function modelNumberLabel(row) {
  const number = runProjectNumber(row);
  return number ? `Model ${number}` : "Model";
}

function runMetadataLine(row) {
  if (!row) return "-";
  const parts = [];
  if (row.request && row.request.energy_scenario_key) {
    const scenarioLabel = String(row.request.energy_scenario_key).replace(/_/g, " ").trim();
    parts.push(scenarioLabel ? `${scenarioLabel.charAt(0).toUpperCase()}${scenarioLabel.slice(1)}` : "");
  }
  if (row.request && row.request.target_year) parts.push(String(row.request.target_year));
  if (row.created_at) parts.push(formatTimestamp(row.created_at));
  return parts.length ? parts.join(" · ") : "-";
}

function succeededProjectRuns(rows) {
  return (rows || []).filter((row) => normalizeStatus(row && row.status) === "succeeded" && row.run_id);
}

function extractComparableMetrics(summary) {
  const integrated = (summary && summary.integrated_results) || {};
  const metrics = Array.isArray(integrated && integrated.integrated_overview && integrated.integrated_overview.metrics)
    ? integrated.integrated_overview.metrics
    : [];
  const out = {};
  metrics.forEach((row) => {
    const key = String((row && row.key) || "").trim();
    if (!key) return;
    out[key] = {
      key,
      label: String(row.label || key),
      value: toNumber(row.value, NaN),
      unit: String(row.unit || ""),
    };
  });
  return out;
}

const COMPARISON_OUTPUT_SECTIONS = [
  { key: "overview", label: "Outcomes", shortLabel: "Outcomes" },
  { key: "energy", label: "Energy system", shortLabel: "Energy" },
  { key: "cost_reliability", label: "Cost & reliability", shortLabel: "Cost" },
  { key: "development", label: "Development", shortLabel: "Development" },
  { key: "regional", label: "Regional & spatial", shortLabel: "Regional" },
  { key: "assumptions", label: "Assumptions & quality", shortLabel: "Quality" },
  { key: "outputs", label: "Output files", shortLabel: "Files" },
];

function comparisonHumanize(value) {
  const text = String(value == null ? "" : value).replace(/[_-]+/g, " ").trim();
  return text ? `${text.charAt(0).toUpperCase()}${text.slice(1)}` : "Not specified";
}

function comparisonRecords(payload, ...path) {
  let current = payload;
  for (const key of path) {
    if (!current || typeof current !== "object") return [];
    current = current[key];
  }
  return Array.isArray(current) ? current : [];
}

function comparisonNumeric(value) {
  if (value === "" || value == null || typeof value === "boolean") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function comparisonFormatValue(value, unit = "") {
  if (value == null || value === "") return "-";
  const numeric = comparisonNumeric(value);
  if (numeric == null) return String(value);
  const normalizedUnit = String(unit || "").toLowerCase();
  if (normalizedUnit === "share" || normalizedUnit === "ratio") return `${(numeric * 100).toFixed(1)}%`;
  if (normalizedUnit === "count") return Math.round(numeric).toLocaleString();
  return compact(numeric);
}

function comparisonRowsForSummary(summary, run) {
  const payload = summary && typeof summary === "object" ? summary : {};
  const integrated = payload.integrated_results && typeof payload.integrated_results === "object"
    ? payload.integrated_results
    : {};
  const diagnostics = payload.summary_diagnostics && typeof payload.summary_diagnostics === "object"
    ? payload.summary_diagnostics
    : {};
  const development = payload.development_impacts && typeof payload.development_impacts === "object"
    ? payload.development_impacts
    : {};
  const configuration = runConfigurationPayload(run || {});
  const rows = Object.fromEntries(COMPARISON_OUTPUT_SECTIONS.map((section) => [section.key, []]));

  function add(section, group, key, label, value, unit = "", resolution = "") {
    if (!Object.prototype.hasOwnProperty.call(rows, section) || value == null || value === "") return;
    rows[section].push({
      key: `${group}:${key}`,
      group,
      label,
      value,
      unit,
      resolution,
    });
  }

  function addNumericObject(section, group, object, definitions, resolution = "") {
    const source = object && typeof object === "object" ? object : {};
    definitions.forEach(([key, label, unit = ""]) => {
      const value = comparisonNumeric(source[key]);
      if (value != null) add(section, group, key, label, value, unit, resolution);
    });
  }

  function addAggregatedRecords(section, group, records, dimensions, {
    valueKey = "value",
    labelPrefix = "",
    unit = "",
    resolution = "",
  } = {}) {
    const aggregated = new Map();
    (Array.isArray(records) ? records : []).forEach((record) => {
      if (!record || typeof record !== "object") return;
      const labels = dimensions.map((dimension) => String(record[dimension] || "").trim()).filter(Boolean);
      if (!labels.length) return;
      const value = comparisonNumeric(record[valueKey]);
      if (value == null) return;
      const dimensionKey = labels.join(" / ");
      aggregated.set(dimensionKey, (aggregated.get(dimensionKey) || 0) + value);
    });
    aggregated.forEach((value, dimensionKey) => {
      const label = labelPrefix ? `${labelPrefix}: ${comparisonHumanize(dimensionKey)}` : comparisonHumanize(dimensionKey);
      add(section, group, `${labelPrefix}:${dimensionKey}`, label, value, unit, resolution);
    });
  }

  function addMultiMetricRecords(section, group, records, dimensions, definitions, resolution = "") {
    (Array.isArray(records) ? records : []).forEach((record, index) => {
      if (!record || typeof record !== "object") return;
      const dimensionLabel = dimensions
        .map((dimension) => String(record[dimension] || "").trim())
        .filter(Boolean)
        .join(" / ") || `Row ${index + 1}`;
      definitions.forEach(([key, label, unit = ""]) => {
        const value = comparisonNumeric(record[key]);
        if (value == null) return;
        add(
          section,
          group,
          `${dimensionLabel}:${key}`,
          `${comparisonHumanize(dimensionLabel)} · ${label}`,
          value,
          unit,
          resolution
        );
      });
    });
  }

  Object.values(extractComparableMetrics(payload)).forEach((metric) => {
    add("overview", "Integrated outcomes", metric.key, metric.label, metric.value, metric.unit, "Global or native model resolution");
  });

  const systemStructure = diagnostics.system_structure || {};
  addNumericObject("overview", "System composition", systemStructure, [
    ["renewable_generation_share", "Renewable generation share", "share"],
    ["zero_carbon_generation_share", "Zero-carbon generation share", "share"],
    ["fossil_generation_share", "Fossil generation share", "share"],
    ["renewable_capacity_share", "Renewable capacity share", "share"],
    ["zero_carbon_capacity_share", "Zero-carbon capacity share", "share"],
    ["fossil_capacity_share", "Fossil capacity share", "share"],
  ], "Global");

  addAggregatedRecords(
    "energy",
    "Generation by technology",
    comparisonRecords(payload, "generation_by_tech", "records"),
    ["techs"],
    { unit: "model energy", resolution: "Technology / timestep, aggregated for comparison" }
  );
  addAggregatedRecords(
    "energy",
    "Installed capacity",
    comparisonRecords(payload, "capacity_by_tech", "records"),
    ["techs"],
    { unit: "model capacity", resolution: "Technology" }
  );
  addAggregatedRecords(
    "energy",
    "New capacity",
    comparisonRecords(payload, "new_capacity_by_tech", "records"),
    ["techs"],
    { unit: "model capacity", resolution: "Technology" }
  );
  addAggregatedRecords(
    "energy",
    "Generation groups",
    comparisonRecords(systemStructure, "generation_by_group", "records"),
    ["tech_group"],
    { unit: "model energy", resolution: "Technology group" }
  );
  addAggregatedRecords(
    "energy",
    "Capacity groups",
    comparisonRecords(systemStructure, "capacity_by_group", "records"),
    ["tech_group"],
    { unit: "model capacity", resolution: "Technology group" }
  );

  addAggregatedRecords(
    "cost_reliability",
    "System cost classes",
    comparisonRecords(payload, "system_cost", "records"),
    ["costs"],
    { unit: "model cost", resolution: "Global cost class" }
  );
  addAggregatedRecords(
    "cost_reliability",
    "Cost components",
    comparisonRecords(diagnostics, "cost_decomposition", "component_records"),
    ["costs", "component", "tech_group"],
    { unit: "model cost", resolution: "Cost class / component / technology group" }
  );
  addNumericObject("cost_reliability", "Reliability", diagnostics.reliability, [
    ["demand_total", "Total demand", "model energy"],
    ["unserved_total", "Unserved energy", "model energy"],
    ["unserved_energy_share", "Unserved energy share", "share"],
    ["hours_with_unserved", "Hours with unserved demand", "count"],
    ["max_unserved_hour", "Maximum hourly unserved demand", "model energy"],
  ], "Global");
  addNumericObject("cost_reliability", "Physical emissions", diagnostics.physical_emissions, [
    ["total_emissions", "Total physical emissions", "tCO2"],
    ["factor_coverage_share", "Emission-factor coverage", "share"],
    ["factor_method_gap_share", "Emission-method gap", "share"],
  ], "Global");
  addAggregatedRecords(
    "cost_reliability",
    "Emissions by technology",
    comparisonRecords(diagnostics, "physical_emissions", "by_tech", "records"),
    ["techs"],
    { unit: "tCO2", resolution: "Technology" }
  );

  addNumericObject("development", "Development drivers", integrated.development_drivers, [
    ["capex_effect_musd", "Investment effect", "MUSD"],
    ["opex_effect_musd", "Operating effect", "MUSD"],
    ["reliability_penalty_proxy", "Reliability penalty proxy", "MUSD"],
    ["import_leakage_musd", "Import leakage", "MUSD"],
  ], "Global or region-coupled");
  const developmentIndicators = integrated.development_indicators || payload.development_indicators || {};
  (comparisonRecords(developmentIndicators, "records")).forEach((record) => {
    const indicatorKey = String(record.indicator_id || record.indicator_name || "").trim();
    if (!indicatorKey) return;
    const value = record.status === "unavailable" ? "Unavailable" : record.value;
    add(
      "development",
      "Development indicators",
      indicatorKey,
      String(record.indicator_name || comparisonHumanize(indicatorKey)),
      value,
      String(record.unit || ""),
      "Configured indicator mapping"
    );
  });
  const sourceChannels = integrated.source_channels || {};
  ["selected_totals", "combined_totals"].forEach((channelKey) => {
    const channel = sourceChannels[channelKey] || development[channelKey] || {};
    Object.entries(channel).forEach(([key, value]) => {
      const numeric = comparisonNumeric(value);
      if (numeric == null) return;
      add(
        "development",
        channelKey === "selected_totals" ? "Selected development totals" : "Combined channel totals",
        `${channelKey}:${key}`,
        comparisonHumanize(key),
        numeric,
        key.includes("musd") ? "MUSD" : key.includes("jobs") ? "jobs" : "",
        "Development channel total"
      );
    });
  });

  const regionalDevelopment = comparisonRecords(integrated, "regional_development", "records").length
    ? comparisonRecords(integrated, "regional_development", "records")
    : comparisonRecords(development, "by_region", "records");
  addMultiMetricRecords("regional", "Development by region", regionalDevelopment, ["region", "mario_region"], [
    ["jobs_total", "Jobs", "jobs"],
    ["gva_total_musd", "GVA", "MUSD"],
    ["household_income_proxy_musd", "Household income", "MUSD"],
    ["shock_value_musd", "Shock value", "MUSD"],
  ], "Region");
  addMultiMetricRecords(
    "regional",
    "Development by region and supplier",
    comparisonRecords(development, "by_region_supplier", "records"),
    ["region", "mario_region", "supplier_sector"],
    [
      ["jobs_total", "Jobs", "jobs"],
      ["gva_total_musd", "GVA", "MUSD"],
      ["household_income_proxy_musd", "Household income", "MUSD"],
      ["shock_value_musd", "Shock value", "MUSD"],
    ],
    "Region / supplier sector"
  );
  addMultiMetricRecords(
    "regional",
    "Supplier sectors",
    comparisonRecords(development, "by_supplier_sector", "records"),
    ["supplier_sector", "mario_sector"],
    [
      ["jobs_total", "Jobs", "jobs"],
      ["gva_total_musd", "GVA", "MUSD"],
      ["household_income_proxy_musd", "Household income", "MUSD"],
      ["shock_value_musd", "Shock value", "MUSD"],
      ["total_shock_musd", "Total shock", "MUSD"],
    ],
    "Supplier sector"
  );
  addMultiMetricRecords(
    "regional",
    "Pool energy balance",
    comparisonRecords(diagnostics, "energy_balance", "records"),
    ["pool"],
    [
      ["generation", "Generation", "model energy"],
      ["demand", "Demand", "model energy"],
      ["unserved", "Unserved", "model energy"],
      ["imports", "Imports", "model energy"],
      ["exports", "Exports", "model energy"],
      ["balance_gap_share", "Balance gap", "share"],
    ],
    "Power pool"
  );
  addMultiMetricRecords(
    "regional",
    "Inter-pool trade",
    comparisonRecords(diagnostics, "trade_matrix", "net_by_pool", "records"),
    ["pool"],
    [
      ["imports", "Imports", "model energy"],
      ["exports", "Exports", "model energy"],
      ["value", "Net exports", "model energy"],
    ],
    "Power pool"
  );
  addAggregatedRecords(
    "regional",
    "Emissions by pool",
    comparisonRecords(diagnostics, "physical_emissions", "by_pool", "records"),
    ["pool"],
    { unit: "tCO2", resolution: "Power pool" }
  );

  add("assumptions", "Model configuration", "architecture", "Model architecture", payload.model_architecture_id || configuration.model_architecture_id);
  add("assumptions", "Model configuration", "energy_scenario", "Energy scenario", payload.energy_scenario_key || configuration.energy_scenario_key);
  add("assumptions", "Model configuration", "target_pathway", "Target pathway", payload.mrio_scenario_id || configuration.mrio_scenario_id || "Not applicable");
  add("assumptions", "Model configuration", "target_year", "Target year", payload.target_year || configuration.target_year);
  add("assumptions", "Model configuration", "run_profile", "Execution profile", payload.run_profile || configuration.run_profile);
  Object.entries(configuration.levers || {}).forEach(([key, value]) => {
    const normalized = comparisonNumeric(value);
    add("assumptions", "Model levers", `lever:${key}`, comparisonHumanize(key), normalized == null ? String(value) : normalized);
  });
  const selectedAssumptions = ((integrated.scenario_assumptions || payload.scenario_assumptions || {}).selected_values) || {};
  Object.entries(selectedAssumptions).forEach(([key, record]) => {
    const source = record && typeof record === "object" ? record : { value_numeric: record };
    const value = comparisonNumeric(source.value_numeric);
    add(
      "assumptions",
      "Scenario assumptions",
      `assumption:${key}`,
      String(source.label || comparisonHumanize(key)),
      value == null ? String(source.value || source.value_text || "") : value,
      String(source.unit || ""),
      "Scenario assumption"
    );
  });
  const confidence = integrated.development_confidence || {};
  addNumericObject("assumptions", "Data and coupling quality", confidence, [
    ["mapping_coverage_share", "Mapping coverage", "share"],
    ["unmapped_mapping_share", "Unmapped share", "share"],
    ["warnings_count", "Warnings", "count"],
    ["mario_runtime_seconds", "Development runtime", "seconds"],
    ["placeholder_input_row_count", "Placeholder input rows", "count"],
    ["development_indicators_available_count", "Available development indicators", "count"],
    ["development_indicators_unavailable_count", "Unavailable development indicators", "count"],
  ], "Execution diagnostic");
  const modelQuality = integrated.model_quality || {};
  add("assumptions", "Data and coupling quality", "quality_status", "Model quality status", modelQuality.status || "Not reported");
  add("assumptions", "Data and coupling quality", "quality_issues", "Quality issues", Array.isArray(modelQuality.issues) ? modelQuality.issues.length : 0, "count");
  const runMetadata = diagnostics.run_metadata || {};
  [
    ["solver", "Solver"],
    ["termination_condition", "Termination condition"],
    ["calliope_version", "Calliope version"],
    ["solution_time_seconds", "Energy solve time", "seconds"],
    ["objective_function_value", "Objective value", ""],
  ].forEach(([key, label, unit = ""]) => {
    const value = runMetadata[key];
    if (value != null && value !== "") add("assumptions", "Execution", key, label, value, unit, "Execution");
  });
  comparisonRecords(integrated, "metric_resolution", "records").forEach((record) => {
    const key = String(record.metric_key || record.label || "").trim();
    if (!key) return;
    add(
      "assumptions",
      "Output resolution",
      `resolution:${key}`,
      String(record.label || comparisonHumanize(key)),
      [record.native_resolution, record.filtered_resolution].filter(Boolean).join(" → "),
      "",
      String(record.notes || "")
    );
  });

  return rows;
}

function buildComparisonDatasets(selectedRuns, summaries) {
  const datasets = Object.fromEntries(COMPARISON_OUTPUT_SECTIONS.map((section) => [section.key, []]));
  const indexes = Object.fromEntries(COMPARISON_OUTPUT_SECTIONS.map((section) => [section.key, new Map()]));
  (selectedRuns || []).forEach((run) => {
    const runId = String(run && run.run_id || "");
    if (!runId) return;
    const runRows = comparisonRowsForSummary(summaries[runId], run);
    COMPARISON_OUTPUT_SECTIONS.forEach((section) => {
      (runRows[section.key] || []).forEach((row) => {
        if (!indexes[section.key].has(row.key)) {
          indexes[section.key].set(row.key, {
            key: row.key,
            group: row.group,
            label: row.label,
            unit: row.unit,
            resolution: row.resolution,
            values: {},
          });
        }
        indexes[section.key].get(row.key).values[runId] = row.value;
      });
    });
  });
  COMPARISON_OUTPUT_SECTIONS.forEach((section) => {
    datasets[section.key] = Array.from(indexes[section.key].values()).sort((left, right) => (
      left.group.localeCompare(right.group) || left.label.localeCompare(right.label)
    ));
  });
  return datasets;
}

function toNumber(value, defaultValue = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : defaultValue;
}

function toTimestampMs(value) {
  if (!value) return null;
  const ms = Date.parse(String(value));
  return Number.isFinite(ms) ? ms : null;
}

function formatTimestamp(value) {
  const ms = toTimestampMs(value);
  return ms ? new Date(ms).toLocaleString() : "-";
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

function canonicalCountryIso3(value) {
  const token = normalizeLocationId(value);
  if (!token) return "";
  const dotTrimmed = token.replace(/\.TOPO$/i, "");
  const match = dotTrimmed.match(/[A-Z]{3}/);
  return match ? match[0] : dotTrimmed;
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
      synthetic_method: "circle_synthetic",
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
  const countryIso3 = firstNonEmpty(props, ["iso3cd", "ISO_A3", "adm0_a3"]);
  if (countryIso3) return canonicalCountryIso3(countryIso3);
  const fromProps = firstNonEmpty(props, LOCATION_MAP_ID_KEYS);
  if (fromProps) return /\.TOPO$/i.test(String(fromProps)) ? canonicalCountryIso3(fromProps) : normalizeLocationId(fromProps);
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

function buildLocationRowsFromCsvTexts(capexCsvText, opexCsvText) {
  const capexRows = parseCsvRows(capexCsvText);
  const opexRows = parseCsvRows(opexCsvText);
  return aggregateLocationShockRows(capexRows, opexRows);
}

function normalizeCountryFeatureFeature(countryIso3, feature) {
  if (!feature || feature.type !== "Feature" || !feature.geometry) return null;
  const iso3 = canonicalCountryIso3(countryIso3);
  if (!iso3) return null;
  const props = { ...((feature && feature.properties) || {}) };
  props.source_location_id = props.location_id || props.id || "";
  props.source_country_iso3 = props.country_iso3 || props.iso3 || "";
  props.location_id = iso3;
  props.country_iso3 = iso3;
  props.iso3 = iso3;
  if (!props.display_name || /\.TOPO$/i.test(String(props.display_name))) {
    props.display_name = String(props.nam_en || props.name || iso3);
  }
  return {
    type: "Feature",
    properties: props,
    geometry: JSON.parse(JSON.stringify(feature.geometry)),
  };
}

function countryFeatureIso3(feature) {
  const props = (feature && feature.properties) || {};
  return canonicalCountryIso3(
    firstNonEmpty(props, ["iso3cd", "ISO_A3", "adm0_a3", "country_iso3", "iso3", "location_id", "id"])
  );
}

async function loadCountryFeatureMap() {
  const resp = await fetch(LOCATION_MAP_COUNTRIES_GEOJSON_PATH);
  if (!resp.ok) {
    throw new Error(`Failed to load country boundaries: ${LOCATION_MAP_COUNTRIES_GEOJSON_PATH}`);
  }
  const geojson = await resp.json();
  const features = Array.isArray(geojson && geojson.features) ? geojson.features : [];
  const out = new Map();
  features.forEach((feature) => {
    const iso3 = countryFeatureIso3(feature);
    const normalized = normalizeCountryFeatureFeature(iso3, feature);
    if (iso3 && normalized && !out.has(iso3)) out.set(iso3, normalized);
  });
  return out;
}

async function loadBundledArchitectureCatalog() {
  const resp = await fetch(MODEL_ARCHITECTURES_PATH);
  if (!resp.ok) {
    throw new Error(`Failed to load bundled model architecture catalog: ${MODEL_ARCHITECTURES_PATH}`);
  }
  return resp.json();
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

  const neededCountries = Array.from(new Set(missing.map((location) => locationToParentCountry(location)).filter(Boolean)));
  const allCountryFeatures = await loadCountryFeatureMap();
  const countryFeatures = new Map(neededCountries.map((iso3) => [iso3, allCountryFeatures.get(iso3) || null]));

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

function toErrorMessage(err, defaultMessage) {
  if (err && typeof err.message === "string" && err.message.trim()) {
    const requestSuffix = err.requestId ? ` Request ID: ${err.requestId}.` : "";
    return `${err.message}${requestSuffix}`;
  }
  return defaultMessage;
}

function toApiUrl(pathOrUrl) {
  const activeBase =
    window.EDIM_API_CLIENT && typeof window.EDIM_API_CLIENT.getApiBase === "function"
      ? window.EDIM_API_CLIENT.getApiBase()
      : API_BASE || "";
  if (!pathOrUrl) return activeBase;
  if (/^https?:\/\//i.test(pathOrUrl)) return pathOrUrl;
  if (window.EDIM_API_CLIENT && typeof window.EDIM_API_CLIENT.downloadUrl === "function") {
    return window.EDIM_API_CLIENT.downloadUrl(pathOrUrl);
  }
  return `${activeBase}${pathOrUrl}`;
}

const SYSTEM_MANIFEST_SCHEMA = "edim_system_manifest";
const FRONTEND_REQUIRED_ENDPOINTS = [
  "GET /api/session",
  "GET /api/projects",
  "POST /api/projects",
  "PATCH /api/projects/{project_id}",
  "DELETE /api/projects/{project_id}",
  "GET /api/projects/{project_id}/runs",
  "POST /api/projects/{project_id}/runs",
  "PATCH /api/projects/{project_id}/runs/{run_id}",
  "POST /api/projects/{project_id}/runs/{run_id}/submit",
  "POST /api/projects/{project_id}/runs/{run_id}/duplicate",
  "DELETE /api/projects/{project_id}/runs/{run_id}",
  "GET /api/runs",
  "GET /api/executions/{execution_id}/status",
  "POST /api/executions/{execution_id}/cancel",
  "GET /api/executions/{execution_id}/events",
  "GET /api/runs/{run_id}/summary",
  "GET /api/runs/{run_id}/integrated",
  "GET /api/runs/{run_id}/artifacts",
  "GET /api/runs/{run_id}/artifacts/{artifact_id}",
  "GET /api/runs/{run_id}/logs",
  "POST /api/runs/{run_id}/export",
  "GET /api/input-datasets",
  "POST /api/input-datasets",
  "PATCH /api/input-datasets/{dataset_id}",
  "POST /api/projects/{project_id}/datasets",
  "GET /api/input-datasets/{dataset_id}/download",
  "POST /api/input-datasets/{dataset_id}/upload",
  "GET /api/input-datasets/{dataset_id}/versions",
  "GET /api/input-datasets/{dataset_id}/versions/{version_id}/download",
  "POST /api/input-datasets/{dataset_id}/versions/{version_id}/activate",
  "DELETE /api/input-datasets/{dataset_id}/versions/{version_id}",
  "GET /api/scenarios",
  "GET /api/model-runtimes",
  "POST /api/projects/{project_id}/runs/validate",
  "GET /api/projects/{project_id}/reports",
  "POST /api/projects/{project_id}/reports",
  "GET /api/projects/{project_id}/reports/{report_id}/download",
  "GET /api/projects/{project_id}/reports/{report_id}/data",
  "GET /api/projects/{project_id}/exports",
  "POST /api/projects/{project_id}/exports",
  "GET /api/projects/{project_id}/exports/{export_id}/download",
  "GET /api/system/manifest",
];

function flattenManifestEndpoints(manifest) {
  const endpointGroups = (manifest && manifest.public_endpoints) || {};
  const endpoints = new Set();
  Object.values(endpointGroups).forEach((group) => {
    if (Array.isArray(group)) {
      group.forEach((endpoint) => endpoints.add(String(endpoint || "").trim()));
    }
  });
  return endpoints;
}

function evaluateSystemManifest(manifest, target) {
  const endpointSet = flattenManifestEndpoints(manifest);
  const missingEndpoints = FRONTEND_REQUIRED_ENDPOINTS.filter((endpoint) => !endpointSet.has(endpoint));
  const schemaVersion = String((manifest && manifest.schema_version) || "");
  const schemaOk = schemaVersion === SYSTEM_MANIFEST_SCHEMA;
  const manifestOk = Boolean(manifest && manifest.ok !== false);
  const manifestDiagnostics = Array.isArray(manifest && manifest.diagnostics) ? manifest.diagnostics : [];
  const errorDiagnostics = manifestDiagnostics.filter((row) => String(row && row.status) === "error");
  const status = !schemaOk || !manifestOk || errorDiagnostics.length
    ? "error"
    : missingEndpoints.length
      ? "warning"
      : "ok";
  const apiBase = target && target.apiBase ? target.apiBase : "";
  const mode = target && target.mode ? target.mode : "local";
  const message = status === "ok"
    ? `Contract ok: ${mode} API is compatible.`
    : status === "warning"
      ? `Contract warning: ${missingEndpoints.length} frontend endpoint${missingEndpoints.length === 1 ? "" : "s"} not listed.`
      : !schemaOk
        ? `Contract error: expected ${SYSTEM_MANIFEST_SCHEMA}, received ${schemaVersion || "missing schema"}.`
        : errorDiagnostics.length
          ? `Contract error: ${errorDiagnostics.length} manifest diagnostic${errorDiagnostics.length === 1 ? "" : "s"} failed.`
          : "Contract error: system manifest reports not ready.";
  return {
    status,
    message,
    apiBase,
    mode,
    schemaVersion,
    missingEndpoints,
    diagnostics: manifestDiagnostics,
    checkedAt: new Date().toISOString(),
    manifest,
  };
}

/* Consolidated frontend API and artifact helpers. */

/* API client */
(function () {
  const http = window.EDIM_HTTP_CLIENT;
  if (!http) {
    throw new Error("EDIM_HTTP_CLIENT must be loaded before app.jsx");
  }
  const {
    apiGet,
    apiGetText,
    apiPost,
    apiPatch,
    apiDelete,
    uploadInputDataset,
    downloadUrl,
  } = http;

  window.EDIM_API_CLIENT = {
    API_BASE: http.getApiBase(),
    getApiBase: http.getApiBase,
    getApiTarget: http.getApiTarget,
    setApiTarget: http.setApiTarget,
    parseApiError: http.parseApiError,
    apiGet,
    apiGetText,
    apiPost,
    apiPatch,
    apiDelete,
    downloadUrl,
    getAuthProvider: http.getAuthProvider,
    setAuthProvider: http.setAuthProvider,
    getActiveUserId: http.getActiveUserId,
    setActiveUserId: http.setActiveUserId,
    fetchSystemManifest: async () => apiGet("/api/system/manifest", "Failed to load system manifest"),
    fetchSession: async () => apiGet("/api/session", "Failed to load local session"),
    fetchProjects: async () => (await apiGet("/api/projects", "Failed to load projects")).projects || [],
    createProject: async (payload) => (await apiPost("/api/projects", payload, "Failed to create project")).project,
    updateProject: async (projectId, payload) => (await apiPatch(`/api/projects/${encodeURIComponent(projectId)}`, payload, "Failed to update project")).project,
    deleteProject: async (projectId, options) => {
      const qs = new URLSearchParams();
      if (options && typeof options.deleteFiles === "boolean") qs.set("delete_files", options.deleteFiles ? "true" : "false");
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return apiDelete(`/api/projects/${encodeURIComponent(projectId)}${suffix}`, "Failed to delete project");
    },
    fetchProjectRuns: async (projectId, options) => {
      const qs = new URLSearchParams();
      if (options && typeof options.includeDrafts === "boolean") qs.set("include_drafts", options.includeDrafts ? "true" : "false");
      if (options && options.limit) qs.set("limit", String(options.limit));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return (await apiGet(`/api/projects/${encodeURIComponent(projectId)}/runs${suffix}`, "Failed to load project runs")).runs || [];
    },
    createRunDraft: async (projectId, req) => projectRunToDisplayRun((await apiPost(`/api/projects/${encodeURIComponent(projectId)}/runs`, req, "Failed to save run draft")).run),
    updateRunDraft: async (projectId, runId, payload) => projectRunToDisplayRun((await apiPatch(`/api/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}`, payload, "Failed to update run draft")).run),
    submitProjectRun: async (projectId, runId) => {
      const payload = await apiPost(`/api/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/submit`, null, "Failed to submit project run");
      return projectRunToDisplayRun(payload.run);
    },
    duplicateProjectRun: async (projectId, runId) => projectRunToDisplayRun((await apiPost(`/api/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/duplicate`, null, "Failed to duplicate run")).run),
    deleteProjectRun: async (projectId, runId, options) => {
      const qs = new URLSearchParams();
      if (options && typeof options.deleteFiles === "boolean") qs.set("delete_files", options.deleteFiles ? "true" : "false");
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return apiDelete(`/api/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}${suffix}`, "Failed to delete run");
    },
    fetchRunLogs: async (runId) => apiGet(`/api/runs/${encodeURIComponent(runId)}/logs`, "Failed to load run logs"),
    createProjectReport: async (projectId, payload) => (await apiPost(`/api/projects/${encodeURIComponent(projectId)}/reports`, payload || {}, "Failed to create report")).report,
    fetchProjectReports: async (projectId) => (await apiGet(`/api/projects/${encodeURIComponent(projectId)}/reports`, "Failed to load reports")).reports || [],
    createProjectExport: async (projectId, payload) => (await apiPost(`/api/projects/${encodeURIComponent(projectId)}/exports`, payload || {}, "Failed to create project export")).export,
    fetchProjectExports: async (projectId) => (await apiGet(`/api/projects/${encodeURIComponent(projectId)}/exports`, "Failed to load exports")).exports || [],
    createRunExport: async (runId) => (await apiPost(`/api/runs/${encodeURIComponent(runId)}/export`, null, "Failed to export run")).export,
    fetchScenarioCatalog: async () => apiGet("/api/scenarios", "Failed to load scenarios"),
    fetchModelRuntimes: async () => apiGet("/api/model-runtimes", "Failed to load model runtime catalog"),
    fetchInputDatasets: async (filters) => {
      const qs = new URLSearchParams();
      if (filters && filters.layer) qs.set("layer", filters.layer);
      if (filters && filters.role) qs.set("role", filters.role);
      if (filters && filters.inputProperty) qs.set("input_property", filters.inputProperty);
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return (await apiGet(`/api/input-datasets${suffix}`, "Failed to load input datasets")).datasets || [];
    },
    // Forward-compatible dataset-library contracts. The local backend can add
    // these endpoints without requiring another frontend workflow redesign.
    createInputDataset: async (payload) => {
      const response = await apiPost("/api/input-datasets", payload, "Failed to create input dataset");
      return response.dataset || response;
    },
    updateInputDataset: async (datasetId, payload) => {
      const response = await apiPatch(
        `/api/input-datasets/${encodeURIComponent(datasetId)}`,
        payload,
        "Failed to update input dataset"
      );
      return response.dataset || response;
    },
    attachInputDatasetToProject: async (projectId, payload) => {
      return apiPost(
        `/api/projects/${encodeURIComponent(projectId)}/datasets`,
        payload,
        "Failed to add dataset to project"
      );
    },
    inputDatasetDownloadUrl: (datasetId) => downloadUrl(`/api/input-datasets/${encodeURIComponent(datasetId)}/download`),
    inputDatasetVersionDownloadUrl: (datasetId, versionId) => downloadUrl(`/api/input-datasets/${encodeURIComponent(datasetId)}/versions/${encodeURIComponent(versionId)}/download`),
    fetchInputDatasetVersions: async (datasetId) => {
      return (await apiGet(`/api/input-datasets/${encodeURIComponent(datasetId)}/versions`, "Failed to load dataset versions")).versions || [];
    },
    activateInputDatasetVersion: async (datasetId, versionId) => {
      return apiPost(`/api/input-datasets/${encodeURIComponent(datasetId)}/versions/${encodeURIComponent(versionId)}/activate`, null, "Failed to activate dataset version");
    },
    deleteInputDatasetVersion: async (datasetId, versionId) => {
      return apiDelete(`/api/input-datasets/${encodeURIComponent(datasetId)}/versions/${encodeURIComponent(versionId)}`, "Failed to delete dataset version");
    },
    uploadInputDataset,
    fetchEnvironmentSetup: async (energyScenarioKey, mrioScenarioId, targetYear, runProfile, projectId, configuration) => {
      const id = projectId || "default";
      const config = configuration && typeof configuration === "object" ? configuration : {};
      return apiPost(
        `/api/projects/${encodeURIComponent(id)}/runs/validate`,
        {
          configuration: {
            model_architecture_id: config.model_architecture_id || DEFAULT_MODEL_ARCHITECTURE_ID,
            energy_model_engine: config.energy_model_engine || "calliope",
            scenario: {
              energy_scenario_key: energyScenarioKey || "new_links",
              target_scenario_id: mrioScenarioId || "S2",
              target_year: Number(targetYear || 2030),
            },
            run_profile: runProfile || "dev",
            levers: config.levers || {},
          },
        },
        "Failed to run environment setup checks"
      );
    },
    fetchJobs: async (limit) => {
      const payload = await apiGet(`/api/runs?limit=${limit || 30}`, "Failed to load runs");
      return (payload.runs || []).map(projectRunToDisplayRun);
    },
    fetchJob: async (jobId) => projectRunToDisplayRun(await apiGet(`/api/executions/${encodeURIComponent(jobId)}/status`, "Failed to load run")),
    cancelJob: async (jobId) => projectRunToDisplayRun(await apiPost(`/api/executions/${encodeURIComponent(jobId)}/cancel`, null, "Failed to cancel run")),
    fetchRunEvents: async (jobId) => (await apiGet(`/api/executions/${encodeURIComponent(jobId)}/events`, "Failed to load run events")).events || [],
    fetchSummary: async (runId) => apiGet(`/api/runs/${encodeURIComponent(runId)}/summary`, "Failed to load run summary"),
    fetchIntegrated: async (runId) => apiGet(`/api/runs/${encodeURIComponent(runId)}/integrated`, "Failed to load integrated results"),
    fetchArtifactText: async (runId, artifactId) => apiGetText(`/api/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}`, `Failed to load ${artifactId}`),
    fetchRunCsv: async (runId) => apiGetText(`/api/runs/${encodeURIComponent(runId)}/artifacts/results_csv`, "Failed to load run results CSV"),
    fetchRunArtifacts: async (runId) => (await apiGet(`/api/runs/${encodeURIComponent(runId)}/artifacts`, "Failed to load run artifacts")).artifacts || [],
    projectReportDownloadUrl: (projectId, reportId) => downloadUrl(`/api/projects/${encodeURIComponent(projectId)}/reports/${encodeURIComponent(reportId)}/download`),
    projectReportDataUrl: (projectId, reportId) => downloadUrl(`/api/projects/${encodeURIComponent(projectId)}/reports/${encodeURIComponent(reportId)}/data`),
    projectExportDownloadUrl: (projectId, exportId) => downloadUrl(`/api/projects/${encodeURIComponent(projectId)}/exports/${encodeURIComponent(exportId)}/download`)
  };
})();


/* Workspace artifact contracts */
(function () {
  function artifactHref(runId, artifact) {
    if (!artifact || !runId) return "";
    const api = window.EDIM_API_CLIENT || {};
    if (artifact.download_url) {
      const href = /^https?:\/\//i.test(artifact.download_url) ? artifact.download_url : `${getFrontendApiBase()}${artifact.download_url}`;
      return typeof api.downloadUrl === "function" ? api.downloadUrl(artifact.download_url) : href;
    }
    if (artifact.path) {
      const artifactId = artifact.artifact_id || "";
      if (artifactId) {
        const path = `/api/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}`;
        return typeof api.downloadUrl === "function" ? api.downloadUrl(path) : `${getFrontendApiBase()}${path}`;
      }
    }
    return "";
  }

  function normalizeArtifactCatalog(runId, summary) {
    const catalog = Array.isArray(summary && summary.artifact_catalog) ? summary.artifact_catalog : [];
    return catalog.map((artifact) => ({ ...artifact, href: artifactHref(runId, artifact) }));
  }

  window.EDIM_WORKSPACE_CONTRACTS = {
    artifactHref,
    normalizeArtifactCatalog,
  };
})();


/* Result artifact helpers */
(function () {
  const contracts = window.EDIM_WORKSPACE_CONTRACTS || {};

  function buildArtifactIndex(runId, summary) {
    const catalog = typeof contracts.normalizeArtifactCatalog === "function"
      ? contracts.normalizeArtifactCatalog(runId, summary)
      : [];
    return catalog.reduce((acc, artifact) => {
      acc[artifact.artifact_id] = artifact;
      return acc;
    }, {});
  }

  function getArtifactHref(runId, summary, artifactId) {
    const artifactIndex = buildArtifactIndex(runId, summary);
    return artifactIndex[artifactId] && artifactIndex[artifactId].href ? artifactIndex[artifactId].href : "";
  }

  function getSummaryArtifactHref(runId, summary, artifactId) {
    return getArtifactHref(runId, summary, artifactId);
  }

  window.EDIM_RESULT_ARTIFACTS = {
    buildArtifactIndex,
    getArtifactHref,
    getSummaryArtifactHref,
  };
})();


/* Result artifact catalog */
(function () {
  const resultArtifacts = window.EDIM_RESULT_ARTIFACTS || {};

  const DEFAULT_OUTPUT_ARTIFACTS = [
    { key: "results_csv", label: "Integrated results CSV" },
    { key: "report_markdown", label: "Model report Markdown" },
    { key: "exchange_bundle_zip", label: "Exchange bundle ZIP" },
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
  ];

  function buildOutputArtifactRows(runId, summary, requestedArtifacts) {
    const rows = Array.isArray(requestedArtifacts) && requestedArtifacts.length ? requestedArtifacts : DEFAULT_OUTPUT_ARTIFACTS;
    return rows.map((row) => {
      const href = typeof resultArtifacts.getArtifactHref === "function"
        ? resultArtifacts.getArtifactHref(runId, summary, row.key)
        : "";
      if (href) return { ...row, href };
      if (!runId) return { ...row, href: "" };
      const path = `/api/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(row.key)}`;
      const api = window.EDIM_API_CLIENT || {};
      return { ...row, href: typeof api.downloadUrl === "function" ? api.downloadUrl(path) : `${getFrontendApiBase()}${path}` };
    });
  }

  window.EDIM_RESULT_CATALOG = {
    DEFAULT_OUTPUT_ARTIFACTS,
    buildOutputArtifactRows,
  };
})();


/* Result components */
const ResultsModule = (() => {
  const resultCatalog = window.EDIM_RESULT_CATALOG || {
    buildOutputArtifactRows: () => [],
  };

  function OutputRows({ runId, summary, artifacts }) {
    const requestedArtifacts = artifacts && artifacts.length ? artifacts : null;
    const outputArtifacts = resultCatalog.buildOutputArtifactRows(runId, summary, requestedArtifacts);
    return (
      <div className="diagram-dataset-list">
        {outputArtifacts.map((artifact) => (
          <div key={artifact.key} className="diagram-output-row">
            <div>
              <div style={{ fontWeight: 700 }}>{artifact.label}</div>
              <div className="muted" style={{ fontSize: 11 }}>{artifact.key}</div>
            </div>
            {artifact.href ? (
              <a href={artifact.href} download>Download</a>
            ) : (
              <span className="muted" style={{ fontSize: 12 }}>Available after execution</span>
            )}
          </div>
        ))}
      </div>
    );
  }

  return { OutputRows };
})();

window.EDIM_RESULTS_COMPONENTS = ResultsModule;


/* Workspace data components */
const WorkspaceDataComponents = (() => {
  const api = window.EDIM_API_CLIENT || {
    inputDatasetDownloadUrl: (datasetId) => `/api/input-datasets/${encodeURIComponent(datasetId)}/download`,
  };

  function DatasetRows({ datasets, onUpload, onDatasetVersionChange, disabled = false, disabledMessage = "" }) {
    // Dataset versions are user-scoped backend records. The UI only activates
    // or deletes versions through API descriptors; it never overwrites source
    // input files or assumes where uploaded files are stored.
    const [expandedDatasetId, setExpandedDatasetId] = React.useState("");
    const [versionsByDataset, setVersionsByDataset] = React.useState({});
    const [loadingDatasetId, setLoadingDatasetId] = React.useState("");
    const [datasetMessage, setDatasetMessage] = React.useState("");

    async function toggleVersions(datasetId) {
      const nextId = expandedDatasetId === datasetId ? "" : datasetId;
      setExpandedDatasetId(nextId);
      setDatasetMessage("");
      if (!nextId || versionsByDataset[nextId]) return;
      setLoadingDatasetId(nextId);
      try {
        const rows = typeof api.fetchInputDatasetVersions === "function"
          ? await api.fetchInputDatasetVersions(nextId)
          : [];
        setVersionsByDataset((prev) => ({ ...prev, [nextId]: rows }));
      } catch (err) {
        setDatasetMessage(err && err.message ? err.message : "Failed to load dataset versions.");
      } finally {
        setLoadingDatasetId("");
      }
    }

    async function refreshVersions(datasetId) {
      if (typeof api.fetchInputDatasetVersions !== "function") return;
      const rows = await api.fetchInputDatasetVersions(datasetId);
      setVersionsByDataset((prev) => ({ ...prev, [datasetId]: rows }));
      if (typeof onDatasetVersionChange === "function") onDatasetVersionChange();
    }

    async function activateVersion(datasetId, versionId) {
      setDatasetMessage("");
      setLoadingDatasetId(datasetId);
      try {
        await api.activateInputDatasetVersion(datasetId, versionId);
        await refreshVersions(datasetId);
        setDatasetMessage(`Activated version ${versionId}.`);
      } catch (err) {
        setDatasetMessage(err && err.message ? err.message : "Failed to activate dataset version.");
      } finally {
        setLoadingDatasetId("");
      }
    }

    async function deleteVersion(datasetId, versionId) {
      setDatasetMessage("");
      setLoadingDatasetId(datasetId);
      try {
        await api.deleteInputDatasetVersion(datasetId, versionId);
        await refreshVersions(datasetId);
        setDatasetMessage(`Deleted inactive version ${versionId}.`);
      } catch (err) {
        setDatasetMessage(err && err.message ? err.message : "Failed to delete dataset version.");
      } finally {
        setLoadingDatasetId("");
      }
    }

    if (!datasets || !datasets.length) {
      return <div className="muted" style={{ fontSize: 12 }}>No datasets are registered for this layer.</div>;
    }
    return (
      <div className="diagram-dataset-list">
        {disabled ? (
          <div className="diagram-note" style={{ marginBottom: 8 }}>
            {disabledMessage || "Inputs are locked for this model. Duplicate the model to edit dataset versions."}
          </div>
        ) : null}
        {datasetMessage ? <div className="diagram-note" style={{ marginBottom: 8 }}>{datasetMessage}</div> : null}
        {datasets.map((dataset) => (
          <div key={dataset.id} className="diagram-dataset-row">
            <div>
              <div style={{ fontWeight: 700 }}>{dataset.label}</div>
              <div className="muted" style={{ fontSize: 11 }}>
                {dataset.filename} · {dataset.exists ? "available" : "missing"}
              </div>
              <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
                {dataset.role}
                {dataset.active_version_id ? <> · active version <code>{dataset.active_version_id}</code></> : null}
              </div>
            </div>
            <div className="diagram-dataset-actions">
              <a href={api.inputDatasetDownloadUrl(dataset.id)} download>Download</a>
              <button type="button" onClick={() => toggleVersions(dataset.id)}>
                {expandedDatasetId === dataset.id ? "Hide versions" : "Versions"}
              </button>
              <label className="dataset-upload-button" style={disabled ? { opacity: 0.55, pointerEvents: "none" } : null}>
                Upload
                <input
                  type="file"
                  disabled={disabled}
                  onChange={(event) => {
                    const file = event.target.files && event.target.files[0];
                    if (file && !disabled) onUpload(dataset.id, file);
                    event.target.value = "";
                  }}
                />
              </label>
            </div>
            {expandedDatasetId === dataset.id ? (
              <div className="diagram-dataset-version-list">
                {loadingDatasetId === dataset.id ? (
                  <div className="muted" style={{ fontSize: 12 }}>Loading versions...</div>
                ) : (versionsByDataset[dataset.id] || []).length ? (
                  (versionsByDataset[dataset.id] || []).map((version) => {
                    const active = dataset.active_version_id && dataset.active_version_id === version.version_id;
                    return (
                      <div key={version.version_id} className="diagram-dataset-version-row">
                        <div>
                          <div><b>{version.filename || version.version_id}</b> {active ? <span className="badge badge-succeeded">Active</span> : null}</div>
                          <div className="muted" style={{ fontSize: 11 }}>
                            <code>{version.version_id}</code> · {version.size_bytes || 0} bytes · {version.created_at || "-"}
                          </div>
                        </div>
                        <div className="diagram-dataset-actions">
                          {typeof api.inputDatasetVersionDownloadUrl === "function" ? (
                            <a href={api.inputDatasetVersionDownloadUrl(dataset.id, version.version_id)} download>Download</a>
                          ) : null}
                          {!active ? (
                            <button type="button" onClick={() => activateVersion(dataset.id, version.version_id)} disabled={disabled}>Activate</button>
                          ) : null}
                          {!active ? (
                            <button type="button" onClick={() => deleteVersion(dataset.id, version.version_id)} disabled={disabled}>Delete</button>
                          ) : null}
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div className="muted" style={{ fontSize: 12 }}>No uploaded override versions for this dataset.</div>
                )}
              </div>
            ) : null}
          </div>
        ))}
      </div>
    );
  }

  return { DatasetRows };
})();

window.EDIM_WORKSPACE_DATA_COMPONENTS = WorkspaceDataComponents;

/* End consolidated frontend helpers. */

const api = window.EDIM_API_CLIENT;
if (!api) {
  throw new Error("EDIM_API_CLIENT must be loaded before app.jsx");
}
const resultArtifacts = window.EDIM_RESULT_ARTIFACTS || {
  buildArtifactIndex: () => ({}),
  getArtifactHref: () => "",
  getSummaryArtifactHref: () => "",
};
const resultComponents = window.EDIM_RESULTS_COMPONENTS || {};
const OutputRows = resultComponents.OutputRows || function OutputRowsFallback() { return null; };
const workspaceDataComponents = window.EDIM_WORKSPACE_DATA_COMPONENTS || {};
const DatasetRows = workspaceDataComponents.DatasetRows || function DatasetRowsFallback() { return null; };

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
  const dialogRef = useRef(null);
  const onCloseRef = useRef(onClose);
  const previousActiveRef = useRef(document.activeElement);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);
  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const previousActive = previousActiveRef.current;
    window.setTimeout(() => {
      if (dialogRef.current && !dialogRef.current.contains(document.activeElement)) {
        dialogRef.current.focus();
      }
    }, 0);
    function handleKeyDown(event) {
      if (event.key === "Escape" && typeof onCloseRef.current === "function") onCloseRef.current();
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = Array.from(
        dialogRef.current.querySelectorAll(
          'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )
      ).filter((node) => node.offsetParent !== null);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
      if (previousActive && typeof previousActive.focus === "function") previousActive.focus();
    };
  }, []);
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={() => {
      if (typeof onCloseRef.current === "function") onCloseRef.current();
    }}>
      <div
        ref={dialogRef}
        className={`modal-card${wide ? " wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
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

function DetailDialogButton({
  label,
  title = label,
  subtitle = "Model information",
  children,
  className = "secondary-action-button",
  wide = false,
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className={className} onClick={() => setOpen(true)}>
        {label}
      </button>
      {open ? (
        <Modal title={title} subtitle={subtitle} wide={wide} onClose={() => setOpen(false)}>
          {children}
        </Modal>
      ) : null}
    </>
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

function ValidationDiagnosticsSummary({
  environmentSetup,
  loading = false,
  compactMode = false,
  onOpenDetails = null,
}) {
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
        <div style={{ fontSize: 13, fontWeight: 700 }}>Validation checks</div>
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
              {attentionChecks.length - 4} more validation checks are available in the full technical readiness diagnostic.
            </div>
          ) : null}
        </div>
      ) : !environmentSetup ? (
        <div className="muted" style={{ marginTop: 8, fontSize: 11 }}>
          Validation results will appear after the readiness check completes.
        </div>
      ) : null}
      {placeholders.files.length || placeholders.rowCount > 0 || placeholders.scenarioPlaceholderActive ? (
        <div className="warn" style={{ marginTop: 8, marginBottom: 0, fontSize: 11 }}>
          {placeholders.files.length ? (
            <>
              Placeholder expert datasets: <code>{placeholders.files.join(", ")}</code>{" "}
              ({placeholders.rowCount} rows).
            </>
          ) : placeholders.rowCount > 0 ? (
            <>
              Placeholder expert dataset rows reported: <code>{placeholders.rowCount}</code>.
            </>
          ) : (
            <>Scenario assumption placeholders were reported.</>
          )}
          {placeholders.scenarioPlaceholderActive ? (
            <div style={{ marginTop: 4 }}>
              Scenario assumptions: {placeholders.scenarioPlaceholderCheck.message || "placeholder rows reported"}
            </div>
          ) : null}
        </div>
      ) : null}
      {typeof onOpenDetails === "function" ? (
        <button
          type="button"
          className="technical-readiness-button"
          onClick={onOpenDetails}
        >
          Open full technical readiness diagnostic
        </button>
      ) : null}
    </div>
  );
}

function LeverControl({ label, value, min, max, step, onChange, tooltip = "", disabled = false }) {
  const controlId = useId();
  const rangeId = `${controlId}-range`;
  const valueId = `${controlId}-value`;
  const clamp = (v) => Math.min(max, Math.max(min, v));
  const apply = (raw) => {
    const parsed = Number.parseFloat(raw);
    if (!Number.isFinite(parsed)) return;
    onChange(clamp(parsed));
  };
  return (
    <div style={{ marginBottom: 10 }}>
      <div className="lever-label" title={tooltip || undefined}>
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
      </div>
      <div className="row" style={{ marginTop: 6 }}>
        <label className="sr-only" htmlFor={rangeId}>{label} slider</label>
        <input
          id={rangeId}
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          disabled={disabled}
          onChange={(e) => apply(e.target.value)}
          style={{ flex: 1, minWidth: 220 }}
        />
        <label className="sr-only" htmlFor={valueId}>{label} value</label>
        <input
          id={valueId}
          type="number"
          min={min}
          max={max}
          step={step}
          value={value}
          disabled={disabled}
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

function RankedBars({
  records,
  labelKey,
  valueKey,
  controlsLabel = "chart",
  emptyMessage = "No records for this execution.",
}) {
  const [limit, setLimit] = useState("10");
  const normalizedRows = useMemo(
    () => (records || [])
      .map((r) => ({
        label: String(r && r[labelKey] != null ? r[labelKey] : ""),
        value: toNumber(r && r[valueKey]),
      }))
      .filter((r) => r.label)
      .sort((a, b) => Math.abs(b.value) - Math.abs(a.value)),
    [records, labelKey, valueKey]
  );
  const rankedLimit = Math.max(5, Math.round(toNumber(limit, 10)));
  const rows = normalizedRows.slice(0, rankedLimit);
  const showLimit = normalizedRows.length > 10;
  const maxAbs = Math.max(...rows.map((r) => Math.abs(r.value)), 1);
  const displayLabel = (value) => String(value || "")
    .replace(/_/g, " ")
    .replace(/:/g, " · ")
    .replace(/\bpp\b/gi, "plant")
    .replace(/\s+/g, " ")
    .trim();

  return (
    <div className="ranked-bars">
      {showLimit ? (
        <div className="ranked-bars-display-controls" role="group" aria-label={`${controlsLabel} display controls`}>
          <label>
            <span className="sr-only">Rows shown for {controlsLabel}</span>
            <select
              value={limit}
              onChange={(event) => setLimit(event.target.value)}
              aria-label={`Rows shown for ${controlsLabel}`}
            >
              <option value="10">Top 10</option>
              <option value="15">Top 15</option>
              <option value="20">Top 20</option>
              <option value="30">Top 30</option>
            </select>
          </label>
        </div>
      ) : null}
      {rows.length ? (
        <div className="hbar-wrap">
          {rows.map((row, idx) => {
            const share = Math.max(0.02, Math.abs(row.value) / maxAbs);
            return (
              <div className="hbar-row" key={`${row.label}-${idx}`}>
                <div title={row.label} style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {displayLabel(row.label)}
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
      ) : (
        <div className="muted">{normalizedFilter ? "No matching records." : emptyMessage}</div>
      )}
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
    ? `${runExecutionId(activeJob)}|${activeJob.stage}|${Math.round(toNumber(activeJob.progress) * 1000)}|${activeJob.message}`
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
          <b>Active execution:</b> <code>{runExecutionId(activeJob)}</code> <StatusBadge status={activeJob.status} />
          {activeJob.queue_position ? <span className="muted"> - queue position {activeJob.queue_position}</span> : null}
        </div>
        <div className="row">
          <div className="muted">{activeJob.stage}</div>
          <button
            type="button"
            className="danger-outline-button"
            onClick={onCancel}
            disabled={!canCancel}
          >
            Cancel execution
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

function SelectedJobDetailsPanel({ job, style = null, showOutputLinks = true }) {
  if (!job) return null;
  const isActive = isActiveStatus(job.status);
  const summary = job.summary || null;
  const hasOutputs = Boolean(job.artifacts && (job.artifacts.csv_url || job.artifacts.summary_url));
  const reportHref = summary ? resultArtifacts.getSummaryArtifactHref(job.run_id || (summary && summary.run_id) || "", summary, "report_markdown") : "";
  const exchangeBundleHref = summary ? resultArtifacts.getSummaryArtifactHref(job.run_id || (summary && summary.run_id) || "", summary, "exchange_bundle_zip") : "";

  return (
    <div className="card" style={{ marginTop: 14, ...(style || {}) }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <b>Selected model:</b> {runLabel(job)} <StatusBadge status={job.status} />
        </div>
        <div className="muted" style={{ fontSize: 12 }}>
          {job.created_at ? new Date(job.created_at).toLocaleString() : "-"}
        </div>
      </div>

      <div className="row muted" style={{ marginTop: 8, fontSize: 12 }}>
        <span>Energy: <code>{(job.request && job.request.energy_scenario_key) || "-"}</code></span>
        <span>Target: <code>{(job.request && job.request.mrio_scenario_id) || "-"}</code></span>
        <span>Year: <code>{(job.request && job.request.target_year) || "-"}</code></span>
        <span>Execution profile: <code>{(job.request && job.request.run_profile) || "-"}</code></span>
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

      {showOutputLinks && hasOutputs ? (
        <div className="row" style={{ marginTop: 10 }}>
          {job.artifacts && job.artifacts.csv_url ? (
            <a href={toApiUrl(job.artifacts.csv_url)} target="_blank" rel="noreferrer">Results CSV</a>
          ) : null}
          {job.artifacts && job.artifacts.summary_url ? (
            <a href={toApiUrl(job.artifacts.summary_url)} target="_blank" rel="noreferrer">Summary JSON</a>
          ) : null}
          {reportHref ? (
            <a href={reportHref} target="_blank" rel="noreferrer">Model report</a>
          ) : null}
          {exchangeBundleHref ? (
            <a href={exchangeBundleHref} target="_blank" rel="noreferrer">Exchange bundle ZIP</a>
          ) : null}
        </div>
      ) : showOutputLinks ? (
        <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
          Outputs will appear here when this execution reaches <code>succeeded</code>.
        </div>
      ) : null}
    </div>
  );
}

function TechnicalExecutionPanel({
  selectedArchitecture,
  selectedEnergyModel,
  scenarioKey,
  requiresMrio,
  mrioScenarioId,
  selectedTargetScenario,
  targetYear,
  runProfile,
  shockMapping,
  showShockMapping = true,
}) {
  const runProfileLabels = {
    dev: "Dev profile",
    analysis: "Analysis profile",
    full: "Full profile",
  };
  const architectureLabel = selectedArchitecture
    ? selectedArchitecture.shortLabel || selectedArchitecture.label
    : "-";
  const energyModelLabel = selectedEnergyModel
    ? selectedEnergyModel.label || selectedEnergyModel.value
    : "-";
  const targetLabel = selectedTargetScenario
    ? selectedTargetScenario.label || selectedTargetScenario.short_label || selectedTargetScenario.scenario_id
    : "";
  const mappingId = shockMapping && shockMapping.mapping_id
    ? shockMapping.mapping_id
    : "mrio_direct_heuristic";

  return (
    <div className="technical-execution-panel">
      <div className="technical-execution-grid">
        <div><span>Architecture</span><strong>{architectureLabel}</strong></div>
        <div><span>Energy model</span><strong>{energyModelLabel}</strong></div>
        <div><span>Input package</span><strong>{scenarioKey || "Unresolved"}</strong></div>
        {requiresMrio ? <div><span>Target pathway</span><strong>{mrioScenarioId || "Unresolved"}</strong></div> : null}
        <div><span>Target year</span><strong>{Number(targetYear || 2030)}</strong></div>
        <div><span>Execution profile</span><strong>{runProfileLabels[runProfile] || runProfile || "-"}</strong></div>
      </div>
      {requiresMrio && showShockMapping ? (
        <div className="diagram-note technical-execution-note">
          MRIO shock mapping: <code>{mappingId}</code>
          {targetLabel ? ` · ${targetLabel}` : ""}
        </div>
      ) : !requiresMrio ? (
        <div className="diagram-note technical-execution-note">
          Energy-only mode excludes MRIO inputs, development stages, and MRIO output artifacts.
        </div>
      ) : null}
    </div>
  );
}

function DraftSavePanel({ job, onSave, saving = false }) {
  if (!job || normalizeStatus(job.status) !== "draft") return null;
  const editedAt = job.updated_at || job.created_at;
  return (
    <div className="draft-save-panel">
      <div className="draft-save-meta">
        <span>Last edited</span>
        <time dateTime={editedAt || undefined}>
          {editedAt ? new Date(editedAt).toLocaleString() : "Not saved yet"}
        </time>
      </div>
      <button
        type="button"
        className="secondary-action-button"
        onClick={onSave}
        disabled={saving || typeof onSave !== "function"}
      >
        {saving ? "Saving..." : "Save draft"}
      </button>
    </div>
  );
}

function EnvironmentSetupPanel({
  environmentSetup,
  loading,
  onRun = null,
  runDisabled = false,
  runDisabledReason = "",
  queueSubmitting = false,
  running = false,
  technicalExecution = null,
  style = null,
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);

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
    <div className="card run-readiness-panel" style={{ marginTop: 14, ...(style || {}) }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3 style={{ marginTop: 0, marginBottom: 0, fontSize: 16 }}>Execution readiness</h3>
        <div className="row" style={{ gap: 8 }}>
          {onRun ? (
            <button type="button" className="run-play-button" onClick={onRun} disabled={runDisabled}>
              <span aria-hidden="true">▶</span>
              {queueSubmitting ? "Queuing..." : running ? "Queue another execution" : "Run model"}
            </button>
          ) : null}
        </div>
      </div>
      <div style={{ ...statusStyle, borderRadius: 10, padding: "8px 10px", marginTop: 8, fontSize: 13 }}>
        {statusLabel}
      </div>
      {technicalExecution ? (
        <div className="run-readiness-action-row">
          <DetailDialogButton
            label="Technical execution"
            title="Technical execution"
            subtitle="Resolved model configuration"
          >
            {technicalExecution}
          </DetailDialogButton>
        </div>
      ) : null}
      <div className="muted environment-inline-summary">
        <span>{cleanCheckLine}</span>
      </div>
      {setupSummary.errors.length ? (
        <div className="warn" style={{ marginTop: 10, marginBottom: 0 }}>
          {setupSummary.errors[0]}
        </div>
      ) : null}
      {runDisabled && runDisabledReason ? (
        <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
          {runDisabledReason}
        </div>
      ) : null}
      <ValidationDiagnosticsSummary
        environmentSetup={environmentSetup}
        loading={loading}
        compactMode={true}
        onOpenDetails={() => setDetailsOpen(true)}
      />
      {detailsOpen ? (
        <Modal title="Technical readiness diagnostic" subtitle="Validation checks" wide={true} onClose={() => setDetailsOpen(false)}>
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

function DuplicateConfigurationPanel({
  selectedJob,
  onDuplicateConfiguration,
  onDeleteRun,
  actionLoading = false,
  technicalExecution = null,
  showDuplicate = true,
  style = null,
}) {
  if (!selectedJob) return null;
  const status = normalizeStatus(selectedJob.status);
  const isComplete = status === "succeeded";
  const isActive = status === "queued" || status === "running";
  const canDelete = !isActive && typeof onDeleteRun === "function";
  return (
    <div className="card" style={{ marginTop: 14, ...(style || {}) }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
        <div>
          <h3 style={{ marginTop: 0, marginBottom: 4, fontSize: 16 }}>Configuration locked</h3>
          <div className="muted" style={{ fontSize: 12 }}>
            {isActive
              ? "This model has an active execution using an immutable input snapshot."
              : isComplete
                ? "This completed model is preserved as an immutable result record."
                : "This model record is immutable."}
          </div>
          <div className="muted" style={{ fontSize: 11, marginTop: 5 }}>
            Selected: <code>{runLabel(selectedJob)}</code> <StatusBadge status={selectedJob.status} />
          </div>
        </div>
        <div className="run-record-action-row">
          {showDuplicate ? (
            <button
              type="button"
              className="run-play-button"
              onClick={onDuplicateConfiguration}
              disabled={actionLoading}
            >
              Duplicate model
            </button>
          ) : null}
          <button
            type="button"
            className="danger-outline-button"
            onClick={onDeleteRun}
            disabled={actionLoading || !canDelete}
            title={isActive ? "Cancel the active execution before deleting this model." : "Delete this model and its generated files."}
          >
            Delete model
          </button>
        </div>
      </div>
      <div className="diagram-note" style={{ marginTop: 10 }}>
        {isActive
          ? "Cancel the active execution before deleting this model. Duplicating creates a new editable draft without changing the active execution."
          : showDuplicate
            ? "The duplicate becomes a new model draft while the original model and its artifacts remain unchanged. Delete removes this model record and generated files."
            : "Delete removes this model record and its generated files."}
      </div>
      {technicalExecution ? (
        <div className="run-record-utility-row">
          <DetailDialogButton
            label="Technical execution"
            title="Technical execution"
            subtitle="Resolved model configuration"
          >
            {technicalExecution}
          </DetailDialogButton>
        </div>
      ) : null}
    </div>
  );
}

function RunDiagnosticsCard({ confidence }) {
  const placeholderInputFiles = Array.isArray(confidence && confidence.placeholder_input_files)
    ? confidence.placeholder_input_files
    : [];
  return (
    <div className="card result-widget result-widget-extra-small result-widget-diagnostics">
      <h3 style={{ marginTop: 0, fontSize: 15 }}>Execution diagnostics</h3>
      <div className="row muted" style={{ marginTop: 8, fontSize: 12 }}>
        <span>Coupling mode: <code>{String((confidence && confidence.coupling_mode) || "unknown")}</code></span>
        <span>Mapping coverage: {formatSharePercent(toNumber(confidence && confidence.mapping_coverage_share), 1)}</span>
        <span>Unmapped technologies: {formatSharePercent(toNumber(confidence && confidence.unmapped_mapping_share), 1)}</span>
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
          No placeholder expert input files are listed in this execution diagnostic payload.
        </div>
      )}
    </div>
  );
}

function ModelQualityCard({ modelQuality, confidence }) {
  const qualityStatus = String((modelQuality && modelQuality.status) || "").trim().toLowerCase();
  const qualityScore = toNumber(modelQuality && modelQuality.score, 0);
  const qualityIssues = Array.isArray(modelQuality && modelQuality.issues) ? modelQuality.issues : [];
  const qualityDiagnostics = (modelQuality && modelQuality.diagnostics) || {};
  return (
    <div className="card result-widget result-widget-small result-widget-quality">
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
          No quality issues were synthesized for this model.
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
        <div className="muted">Metric resolution metadata was not recorded for this execution.</div>
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
    <div className="card result-widget result-widget-extra-small result-widget-uncertainty">
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
        <div className="muted">Uncertainty bounds were not produced for this execution.</div>
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
        <div className="muted">No matched scenario assumptions were recorded for this model.</div>
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
        <div className="muted">No development indicators were recorded for this model.</div>
      )}
    </div>
  );
}

function SpatialResultsMapPanel({
  mapData,
  mapMetric,
  setMapMetric,
  includeDevelopment,
  loading,
  loadError,
  developmentByRegionRecords,
  spatialFilter,
  setSpatialFilter,
  mapViewport,
  onMapViewportChange,
}) {
  const mapHostRef = useRef(null);
  const mapRef = useRef(null);
  const layerRef = useRef(null);
  const fittedRunRef = useRef("");
  const mapViewportRef = useRef(mapViewport);
  const onMapViewportChangeRef = useRef(onMapViewportChange);

  const availableMapMetrics = useMemo(
    () => LOCATION_MAP_METRICS.filter((item) => includeDevelopment || item.scope !== "region"),
    [includeDevelopment]
  );
  const metricMeta = availableMapMetrics.find((item) => item.key === mapMetric) || availableMapMetrics[0] || LOCATION_MAP_METRICS[0];
  useEffect(() => {
    if (metricMeta && mapMetric !== metricMeta.key) setMapMetric(metricMeta.key);
  }, [metricMeta && metricMeta.key, mapMetric]);
  const regionLookup = useMemo(
    () => buildRegionLookup(developmentByRegionRecords),
    [developmentByRegionRecords]
  );
  const mapExtentSignature = [
    mapData && mapData.runId ? mapData.runId : "no-run",
    String((mapData && mapData.geojson && mapData.geojson.features && mapData.geojson.features.length) || 0),
    String((mapData && mapData.coverage && mapData.coverage.geoFeatureLocationCount) || 0),
  ].join("|");
  const mapExtentSignatureRef = useRef(mapExtentSignature);

  useEffect(() => {
    mapViewportRef.current = mapViewport;
    onMapViewportChangeRef.current = onMapViewportChange;
    mapExtentSignatureRef.current = mapExtentSignature;
  }, [mapViewport, onMapViewportChange, mapExtentSignature]);

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
    const metricValues = [];

    features.forEach((feature) => {
      const info = getFeatureInfo(feature);
      const value = info.metricValue;
      if (Number.isFinite(value)) metricValues.push(value);
    });

    const minValue = metricValues.length ? Math.min(...metricValues) : NaN;
    const maxValue = metricValues.length ? Math.max(...metricValues) : NaN;
    const histogramBins = buildMapHistogramBins(metricValues, minValue, maxValue, 18);

    return {
      featureCount: features.length,
      minValue,
      maxValue,
      histogramBins,
    };
  }, [mapData, metricMeta.key, regionLookup]);

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
    const savedViewport = mapViewportRef.current;
    const canRestoreViewport =
      savedViewport &&
      savedViewport.extentSignature === mapExtentSignatureRef.current &&
      Number.isFinite(Number(savedViewport.latitude)) &&
      Number.isFinite(Number(savedViewport.longitude)) &&
      Number.isFinite(Number(savedViewport.zoom));
    if (canRestoreViewport) {
      map.setView(
        [Number(savedViewport.latitude), Number(savedViewport.longitude)],
        Number(savedViewport.zoom),
        { animate: false }
      );
      fittedRunRef.current = mapExtentSignatureRef.current;
    } else {
      map.setView([4, 20], 3);
    }
    function persistViewport() {
      const callback = onMapViewportChangeRef.current;
      if (typeof callback !== "function") return;
      const center = map.getCenter();
      callback({
        extentSignature: mapExtentSignatureRef.current,
        latitude: center.lat,
        longitude: center.lng,
        zoom: map.getZoom(),
      });
    }
    map.on("moveend", persistViewport);
    mapRef.current = map;

    return () => {
      if (layerRef.current) {
        layerRef.current.remove();
        layerRef.current = null;
      }
      map.off("moveend", persistViewport);
      map.remove();
      mapRef.current = null;
      fittedRunRef.current = "";
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const savedViewport = mapViewport;
    if (
      !map ||
      fittedRunRef.current === mapExtentSignature ||
      !savedViewport ||
      savedViewport.extentSignature !== mapExtentSignature ||
      !Number.isFinite(Number(savedViewport.latitude)) ||
      !Number.isFinite(Number(savedViewport.longitude)) ||
      !Number.isFinite(Number(savedViewport.zoom))
    ) {
      return;
    }
    map.setView(
      [Number(savedViewport.latitude), Number(savedViewport.longitude)],
      Number(savedViewport.zoom),
      { animate: false }
    );
    fittedRunRef.current = mapExtentSignature;
  }, [mapExtentSignature, mapViewport]);

  useEffect(() => {
    if (!mapHostRef.current || !mapRef.current || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      const map = mapRef.current;
      if (!map) return;
      window.setTimeout(() => {
        map.invalidateSize();
      }, 0);
    });
    observer.observe(mapHostRef.current);
    return () => observer.disconnect();
  }, []);

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
            ? "Matched by region context"
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
    window.setTimeout(() => fitMapToAvailableData(layer, mapExtentSignature), 0);
    window.setTimeout(() => fitMapToAvailableData(layer, mapExtentSignature), 160);
  }, [
    mapData,
    mapSummary.featureCount,
    mapSummary.minValue,
    mapSummary.maxValue,
    metricMeta,
    regionLookup,
    spatialFilter,
    mapExtentSignature,
  ]);

  return (
    <div className="card spatial-results-map-card result-widget result-widget-large" style={{ minWidth: 0 }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-end" }}>
        <h3 style={{ marginTop: 0, marginBottom: 2, fontSize: 15 }}>Results map</h3>
        <div className="map-toolbar-controls">
          <label className="map-metric-control">
            <span>Map metric</span>
            <select value={mapMetric} onChange={(e) => setMapMetric(e.target.value)} style={{ maxWidth: "100%" }}>
              {availableMapMetrics.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
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

      <div className="spatial-results-map-stage">
        <div
          ref={mapHostRef}
          className="spatial-results-map-host"
          style={{
            width: "100%",
            maxWidth: "100%",
            minHeight: 320,
            height: "min(52vh, 560px)",
            background: "#0a1220",
          }}
        />
        {Number.isFinite(mapSummary.minValue) && Number.isFinite(mapSummary.maxValue) ? (
          <div className="map-distribution-overlay">
            {mapSummary.histogramBins.length ? (
              <div
                className="map-distribution-histogram"
                aria-label={`Histogram distribution for ${metricMeta.label}`}
                style={{
                  gridTemplateColumns: `repeat(${mapSummary.histogramBins.length}, minmax(3px, 1fr))`,
                }}
              >
                {mapSummary.histogramBins.map((bin, idx) => (
                  <div
                    key={`map-histogram-${idx}`}
                    title={`${compact(bin.min)} to ${compact(bin.max)}: ${bin.count} feature${bin.count === 1 ? "" : "s"}`}
                    style={{
                      height: `${Math.max(2, Math.round(bin.share * 38))}px`,
                      background: colorForMapValue(bin.midpoint, mapSummary.minValue, mapSummary.maxValue),
                      opacity: bin.count > 0 ? 0.95 : 0.22,
                    }}
                  />
                ))}
              </div>
            ) : null}
            <div
              className="map-distribution-gradient"
              style={{
                background: mapLegendGradient(),
              }}
            />
            <div className="map-distribution-range">
              <span>{compact(mapSummary.minValue)}</span>
              <span>{metricMeta.label}</span>
              <span>{compact(mapSummary.maxValue)}</span>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function RunResultsPanel({
  result,
  architecture,
  selectedRunLabel,
  selectedRunName,
  onRenameModel,
  onDuplicateModel,
  duplicateModelLoading = false,
  technicalExecutionPanel,
  technicalDetailsPanel,
  selectedModelDetailsPanel,
  runMetadata,
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
  const [mapViewportsByRun, setMapViewportsByRun] = useState({});
  const [modelNameEditing, setModelNameEditing] = useState(false);
  const [modelNameDraft, setModelNameDraft] = useState("");
  const [modelNameSaving, setModelNameSaving] = useState(false);
  const includesDevelopment = architectureIncludesDevelopment(architecture);
  const visibleTabKeys = architectureResultTabs(architecture);
  const developmentMetricKeys = new Set([
    "jobs_total",
    "gva_total_musd",
    "household_income_proxy_musd",
    "import_leakage_musd",
  ]);
  const displayIntegratedMetrics = useMemo(
    () =>
      includesDevelopment
        ? (integratedMetrics || [])
        : (integratedMetrics || []).filter((metric) => !developmentMetricKeys.has(String(metric && metric.key))),
    [includesDevelopment, integratedMetrics]
  );
  const mapViewportKey = String(
    (locationMapData && locationMapData.runId) ||
    (runMetadata && (runMetadata.run_id || runMetadata.execution_id)) ||
    selectedRunLabel ||
    "current-run"
  );
  useEffect(() => {
    if (!visibleTabKeys.includes(activeSection)) setActiveSection(visibleTabKeys[0] || "overview");
  }, [activeSection, visibleTabKeys.join("|")]);
  useEffect(() => {
    if (!modelNameEditing) setModelNameDraft(String(selectedRunName || ""));
  }, [selectedRunName, modelNameEditing]);

  async function saveModelName() {
    const nextName = String(modelNameDraft || "").trim();
    if (!nextName || typeof onRenameModel !== "function") return;
    setModelNameSaving(true);
    try {
      await onRenameModel(nextName);
      setModelNameEditing(false);
    } catch (_error) {
      // The workspace-level error surface reports persistence failures.
    } finally {
      setModelNameSaving(false);
    }
  }

  const uncertaintyBounds =
    developmentUncertainty &&
    developmentUncertainty.totals_bounds &&
    typeof developmentUncertainty.totals_bounds === "object"
      ? developmentUncertainty.totals_bounds
      : null;
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
    const rows = Array.isArray(displayIntegratedMetrics) ? displayIntegratedMetrics : [];
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
    displayIntegratedMetrics,
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
  const resultEvidence = evidenceFromSummary((result && result.summary) || {});
  const resolutionRows = Array.isArray(metricResolution && metricResolution.records)
    ? metricResolution.records
    : [];
  const countryResponsiveIntegratedMetricKeys = useMemo(() => {
    const keys = new Set([
      "monetary_cost",
      "physical_emissions",
      "unserved_energy_share",
    ]);
    resolutionRows.forEach((row) => {
      const key = String((row && row.metric_key) || "").trim();
      if (!key) return;
      const filteredResolution = String((row && row.filtered_resolution) || "").toLowerCase();
      if (
        filteredResolution.includes("location") ||
        filteredResolution.includes("country") ||
        filteredResolution.includes("subregion")
      ) {
        keys.add(key);
      } else {
        keys.delete(key);
      }
    });
    return keys;
  }, [metricResolution]);
  const countryResponsiveIntegratedMetrics = useMemo(
    () =>
      resolvedIntegratedMetrics.filter((metric) =>
        countryResponsiveIntegratedMetricKeys.has(String((metric && metric.key) || ""))
      ),
    [resolvedIntegratedMetrics, countryResponsiveIntegratedMetricKeys]
  );
  const fixedIntegratedMetrics = useMemo(
    () =>
      displayIntegratedMetrics.filter(
        (metric) => !countryResponsiveIntegratedMetricKeys.has(String((metric && metric.key) || ""))
      ),
    [displayIntegratedMetrics, countryResponsiveIntegratedMetricKeys]
  );
  const fixedMetricsIncludeImportLeakage = fixedIntegratedMetrics.some(
    (metric) => String((metric && metric.key) || "") === "import_leakage_musd"
  );
  const assumptionsCount = toNumber(confidence && confidence.scenario_assumptions_applied_count, 0);
  const indicatorAvailableCount = toNumber(confidence && confidence.development_indicators_available_count, 0);
  const indicatorUnavailableCount = toNumber(confidence && confidence.development_indicators_unavailable_count, 0);
  const scenarioAssumptionRows = Array.isArray(scenarioAssumptions && scenarioAssumptions.records)
    ? scenarioAssumptions.records
    : [];
  const developmentIndicatorRows = Array.isArray(developmentIndicators && developmentIndicators.records)
    ? developmentIndicators.records
    : [];
  const runWarnings = Array.isArray(result && result.summary && result.summary.warnings)
    ? result.summary.warnings
    : [];
  const reportHref = resultArtifacts.getSummaryArtifactHref(result.artifacts.run_id, result.summary, "report_markdown");
  const exchangeBundleHref = resultArtifacts.getSummaryArtifactHref(result.artifacts.run_id, result.summary, "exchange_bundle_zip");
  const sectionTabs = [
    { key: "overview", label: "Overview" },
    { key: "system", label: "Energy system" },
    { key: "development", label: "Development" },
    { key: "method", label: "Method" },
  ].filter((tab) => visibleTabKeys.includes(tab.key));

  if (!result) return null;

  return (
    <div className="analysis-shell">
      <div className="card analysis-header-card">
        <div className="analysis-title-row">
          <div className="analysis-title-copy">
            <div className="view-eyebrow">Model results</div>
            {modelNameEditing ? (
              <div className="analysis-model-title-editor">
                <input
                  type="text"
                  aria-label="Model name"
                  value={modelNameDraft}
                  maxLength={200}
                  autoFocus
                  onChange={(event) => setModelNameDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") saveModelName();
                    if (event.key === "Escape") setModelNameEditing(false);
                  }}
                />
                <button
                  type="button"
                  className="secondary-action-button"
                  onClick={saveModelName}
                  disabled={modelNameSaving || !String(modelNameDraft || "").trim()}
                >
                  {modelNameSaving ? "Saving..." : "Save"}
                </button>
                <button
                  type="button"
                  className="ghost-utility-button"
                  onClick={() => setModelNameEditing(false)}
                  disabled={modelNameSaving}
                >
                  Cancel
                </button>
              </div>
            ) : (
              <div className="analysis-model-title-row">
                <h1 className="view-title">{selectedRunName || "Untitled model"}</h1>
                {typeof onRenameModel === "function" ? (
                  <button
                    type="button"
                    className="icon-button analysis-model-title-edit"
                    aria-label="Edit model name"
                    title="Edit model name"
                    onClick={() => {
                      setModelNameDraft(String(selectedRunName || ""));
                      setModelNameEditing(true);
                    }}
                  >
                    <img
                      className="analysis-model-title-edit-icon"
                      src="./assets/icons/pencil.svg?v=edit-2"
                      alt=""
                      aria-hidden="true"
                    />
                  </button>
                ) : null}
              </div>
            )}
            <div className="view-subtitle">
              Explore this model's outputs by overview, energy-system, development, and method views.
            </div>
            {technicalExecutionPanel ? (
              <div className="analysis-inline-technical-execution" aria-label="Technical execution">
                {technicalExecutionPanel}
              </div>
            ) : null}
          </div>
          <div className="analysis-title-actions analysis-title-actions-stacked">
            {typeof onDuplicateModel === "function" ? (
              <button
                type="button"
                className="primary-action-button analysis-duplicate-model-button"
                onClick={onDuplicateModel}
                disabled={duplicateModelLoading}
              >
                {duplicateModelLoading ? "Duplicating..." : "Duplicate model"}
              </button>
            ) : null}
            {technicalDetailsPanel ? (
              <DetailDialogButton
                label="Technical details"
                title="Technical details"
                subtitle="Model run metadata"
                className="secondary-action-button analysis-model-tool-button analysis-technical-details-button"
                wide={true}
              >
                <div className="results-technical-details-stack">
                  {technicalDetailsPanel}
                  {selectedModelDetailsPanel ? (
                    <section className="results-technical-detail-section" aria-labelledby="selected-model-record-title">
                      <div className="results-kpi-group-label" id="selected-model-record-title">Selected model record</div>
                      {selectedModelDetailsPanel}
                    </section>
                  ) : null}
                  {runWarnings.length ? (
                    <section className="results-technical-detail-section" aria-labelledby="execution-warning-title">
                      <div className="results-kpi-group-label" id="execution-warning-title">Execution warnings</div>
                      <ul className="results-technical-warning-list">
                        {runWarnings.map((warning, index) => <li key={index}>{warning}</li>)}
                      </ul>
                    </section>
                  ) : null}
                </div>
              </DetailDialogButton>
            ) : null}
            <div className="analysis-output-action-pair">
              <details className="analysis-utility-menu analysis-download-menu">
                <summary>
                  <span>Downloads</span>
                  <img
                    className="analysis-download-chevron"
                    src="./assets/icons/chevron-down.svg?v=stacked-actions-1"
                    alt=""
                    aria-hidden="true"
                  />
                </summary>
                <div className="analysis-export-links" aria-label="Result downloads">
                  <a href={toApiUrl(result.artifacts.csv_url)} target="_blank" rel="noreferrer">Results CSV</a>
                  {result.artifacts.summary_url ? (
                    <a href={toApiUrl(result.artifacts.summary_url)} target="_blank" rel="noreferrer">Summary JSON</a>
                  ) : null}
                  {reportHref ? (
                    <a href={reportHref} target="_blank" rel="noreferrer">Model report</a>
                  ) : null}
                  {exchangeBundleHref ? (
                    <a href={exchangeBundleHref} target="_blank" rel="noreferrer">Exchange bundle ZIP</a>
                  ) : null}
                </div>
              </details>
            </div>
          </div>
        </div>
      </div>

      <nav className="analysis-filter-row results-section-tab-row" aria-label="Model result views">
        <div className="segmented-control results-section-tabs" role="tablist" aria-label="Result sections">
          {sectionTabs.map((tab, index) => (
            <button
              key={tab.key}
              type="button"
              id={`result-tab-${tab.key}`}
              role="tab"
              className={activeSection === tab.key ? "seg-button active" : "seg-button"}
              aria-controls="result-tabpanel"
              aria-selected={activeSection === tab.key}
              tabIndex={activeSection === tab.key ? 0 : -1}
              onClick={() => setActiveSection(tab.key)}
              onKeyDown={(event) => handleTablistKeyDown(
                event,
                index,
                sectionTabs.length,
                (nextIndex) => setActiveSection(sectionTabs[nextIndex].key)
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </nav>

      <div
        className="analysis-section-body"
        id="result-tabpanel"
        role="tabpanel"
        aria-labelledby={`result-tab-${activeSection}`}
        tabIndex={0}
      >
        {activeSection === "overview" ? (
          <div className="dashboard-stack results-overview-widget-layout">
            <div className="workspace-map-grid">
              <div className="dashboard-stack results-map-widget-column">
                <section className="card result-widget results-geographic-kpi-strip" aria-labelledby="geographic-results-title">
                  <div className="results-geographic-kpi-heading">
                    <h3 id="geographic-results-title">Key outcomes</h3>
                  </div>
                  <div className={includesDevelopment ? "results-geographic-kpi-groups" : "results-geographic-kpi-groups is-single"}>
                    <div className="results-geographic-kpi-group">
                      <div className="results-kpi-group-label">Final results</div>
                      {countryResponsiveIntegratedMetrics.length ? (
                        <div className="results-kpi-row">
                          {countryResponsiveIntegratedMetrics.map((metric) => (
                            <MetricCard
                              key={`geographic-${String(metric.key)}`}
                              label={`${String(metric.label)} (${String(metric.unit)})`}
                              value={compact(toNumber(metric.value))}
                            />
                          ))}
                        </div>
                      ) : (
                        <div className="muted">Final results are not available for this model.</div>
                      )}
                    </div>
                    {includesDevelopment ? (
                      <div className="results-geographic-kpi-group">
                        <div className="results-kpi-group-label">Development drivers</div>
                        <div className="results-kpi-row">
                          <MetricCard label="CAPEX effect (MUSD)" value={compact(displayedDevelopmentDrivers.capex_effect_musd)} />
                          <MetricCard label="OPEX effect (MUSD)" value={compact(displayedDevelopmentDrivers.opex_effect_musd)} />
                          <MetricCard label="Reliability penalty (MUSD)" value={compact(displayedDevelopmentDrivers.reliability_penalty_proxy)} />
                          <MetricCard label="Total shock (MUSD)" value={compact(filteredLocationShockTotals.totalShockMusd)} />
                        </div>
                      </div>
                    ) : null}
                  </div>
                  {runSpatialTechLoading ? (
                    <div className="muted results-geographic-kpi-status">
                      Loading result detail...
                    </div>
                  ) : null}
                  {runSpatialTechError ? (
                    <div className="warn results-geographic-kpi-status">
                      {runSpatialTechError}
                    </div>
                  ) : null}
                </section>
                <SpatialResultsMapPanel
                  mapData={locationMapData}
                  mapMetric={locationMapMetric}
                  setMapMetric={setLocationMapMetric}
                  includeDevelopment={includesDevelopment}
                  loading={locationMapLoading}
                  loadError={locationMapError}
                  developmentByRegionRecords={developmentByRegion}
                  spatialFilter={spatialFilter}
                  setSpatialFilter={setSpatialFilter}
                  mapViewport={mapViewportsByRun[mapViewportKey] || null}
                  onMapViewportChange={(viewport) => {
                    setMapViewportsByRun((previous) => {
                      const current = previous[mapViewportKey];
                      if (
                        current &&
                        current.extentSignature === viewport.extentSignature &&
                        current.zoom === viewport.zoom &&
                        Math.abs(current.latitude - viewport.latitude) < 0.000001 &&
                        Math.abs(current.longitude - viewport.longitude) < 0.000001
                      ) {
                        return previous;
                      }
                      return { ...previous, [mapViewportKey]: viewport };
                    });
                  }}
                />
              </div>

              <div className="workspace-side-stack results-overview-side">
                <aside className="card result-widget results-run-wide-panel" aria-labelledby="run-wide-results-title">
                  <div className="results-run-wide-heading">
                    <h3 id="run-wide-results-title">Overall results</h3>
                  </div>
                  <div className="results-run-wide-section">
                    <div className="results-kpi-group-label">Final results</div>
                    {fixedIntegratedMetrics.length ? (
                      <div className="results-kpi-row">
                        {fixedIntegratedMetrics.map((metric) => (
                          <MetricCard
                            key={`run-wide-${String(metric.key)}`}
                            label={`${String(metric.label)} (${String(metric.unit)})`}
                            value={compact(toNumber(metric.value))}
                          />
                        ))}
                      </div>
                    ) : (
                      <div className="muted">No overall integrated metrics were recorded for this model.</div>
                    )}
                  </div>
                  {includesDevelopment && !fixedMetricsIncludeImportLeakage ? (
                    <div className="results-run-wide-section">
                      <div className="results-kpi-group-label">Development drivers</div>
                      <div className="results-kpi-row">
                        <MetricCard label="Import leakage (MUSD)" value={compact(globalDevelopmentDrivers.import_leakage_musd)} />
                      </div>
                    </div>
                  ) : null}
                </aside>
              </div>
            </div>

            <details className="results-section-disclosure results-evidence-disclosure">
              <summary>
                <span>Confidence and diagnostics</span>
                <small>Quality, uncertainty, and execution checks</small>
              </summary>
              <div className="results-support-widget-grid">
                <RunDiagnosticsCard confidence={confidence} />
                <ModelQualityCard modelQuality={modelQuality} confidence={confidence} />
                {includesDevelopment ? <DevelopmentUncertaintyCard developmentUncertainty={developmentUncertainty} /> : null}
              </div>
            </details>
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
                  controlsLabel="generation by technology"
                  emptyMessage="No generation records for this model."
                />
                {spatialFilter && runSpatialTechLoading ? (
                  <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                    Preparing generation data...
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
                <h3 style={{ marginTop: 0, fontSize: 15 }}>Installed capacity</h3>
                <RankedBars
                  records={filteredCapacityByTech}
                  labelKey="techs"
                  valueKey="value"
                  controlsLabel="installed capacity"
                  emptyMessage="No capacity records for this model."
                />
                {spatialFilter && runSpatialTechLoading ? (
                  <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                    Preparing capacity data...
                  </div>
                ) : null}
              </div>
            </div>

            <section className="results-section-disclosure results-section-static">
              <div className="results-section-static-header">
                <span>System diagnostics</span>
                <small>Reliability, trade, emissions, balances, and cost components</small>
              </div>
              <div className="results-disclosure-stack">
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
                  controlsLabel="inter-pool trade balance"
                  emptyMessage="No inter-pool transmission balance data."
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
                  controlsLabel="physical emissions by pool"
                  emptyMessage="No physical emissions records for this model."
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
                    controlsLabel="cost decomposition"
                    emptyMessage="No cost decomposition records for this model."
                  />
                </div>
              </div>
            </div>
              </div>
            </section>
          </div>
        ) : null}

        {includesDevelopment && activeSection === "development" ? (
          <div className="dashboard-stack">
            <div className="workspace-grid-2">
              <div className="card">
                <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                  <h3 style={{ marginTop: 0, fontSize: 15, marginBottom: 0 }}>Development drivers</h3>
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
                  controlsLabel="development impacts by region"
                  emptyMessage="No development-by-region records for this model."
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
                  controlsLabel="development impacts by supplier sector"
                  emptyMessage="No development-by-sector records for this model."
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

            <section className="results-section-disclosure results-section-static">
              <div className="results-section-static-header">
                <span>Assumptions and indicator coverage</span>
                <small>Scenario assumptions and development data availability</small>
              </div>
              <div className="workspace-grid-2">
                <ScenarioAssumptionsCard scenarioAssumptions={scenarioAssumptions} confidence={confidence} />
                <DevelopmentIndicatorsCard developmentIndicators={developmentIndicators} confidence={confidence} />
              </div>
            </section>
          </div>
        ) : null}

        {!includesDevelopment && activeSection === "development" ? (
          <div className="card compact-placeholder-card">
            No detailed development outputs are available for this energy-only run.
          </div>
        ) : null}

        {activeSection === "method" ? (
          <div className="dashboard-stack">
            <div className="workspace-grid-2">
              <ScenarioProvenanceCard scenarioPackage={scenarioPackage} confidence={confidence} />
              {includesDevelopment ? (
                <SourceChannelsCard sourceChannels={sourceChannels} />
              ) : (
                <div className="card">
                  <h3 style={{ marginTop: 0, fontSize: 15 }}>Architecture scope</h3>
                  <div className="muted" style={{ fontSize: 12 }}>
                    This run is displayed with the energy-only architecture. MRIO source-channel comparison,
                    development indicators, and MRIO-direct shock artifacts are intentionally hidden.
                  </div>
                </div>
              )}
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

function BackendTargetSwitch({
  apiTarget,
  compatibility,
  onApiTargetModeChange,
  disabled,
}) {
  const target = apiTarget || {};
  const contract = compatibility || {};
  const backendMode = String(target.mode || "local") === "backend";
  const backendConfigured = Boolean(target.hasBackendApiBase);
  const apiBase = String(target.apiBase || target.localApiBase || "").replace(/^https?:\/\//, "");
  const backendBase = String(target.backendApiBase || "").replace(/^https?:\/\//, "");
  const contractStatus = String(contract.status || "").trim();
  const contractMessage = String(contract.message || "").trim();
  const contractLabel = contractStatus
    ? contractStatus === "checking"
      ? "Checking contract"
      : contractMessage || `Contract ${contractStatus}`
    : "Contract not checked";
  return (
    <div className={`runtime-target-control ${backendMode ? "is-backend" : "is-local"}`}>
      <div className="runtime-target-row">
        <span className="runtime-target-label">Runtime</span>
        <label className="runtime-switch-control">
          <span className={`runtime-switch-label ${!backendMode ? "is-active" : ""}`}>Local</span>
          <span className="runtime-toggle-shell">
            <input
              className="runtime-toggle-input"
              type="checkbox"
              checked={backendMode}
              onChange={(event) => onApiTargetModeChange(event.target.checked ? "backend" : "local")}
              disabled={disabled || (!backendConfigured && !backendMode)}
              aria-label="Switch between local and remote runtime"
            />
            <span className="runtime-toggle-track" aria-hidden="true">
              <span className="runtime-toggle-thumb" />
            </span>
          </span>
          <span className={`runtime-switch-label ${backendMode ? "is-active" : ""}`}>Remote</span>
        </label>
        <span className="runtime-info-slot">
          <button
            type="button"
            className={`runtime-info-button ${contractStatus || (backendConfigured ? "idle" : "warning")}`}
            aria-label="Runtime connection details"
          >
            i
          </button>
          <span className="runtime-info-panel">
            <span><b>Active:</b> {backendMode ? "Remote" : "Local"}</span>
            <span><b>API:</b> {backendMode && backendConfigured ? (backendBase || "configured remote") : (apiBase || "current origin")}</span>
            <span><b>Remote API:</b> {backendConfigured ? "Configured" : "Not configured"}</span>
            <span><b>Contract:</b> {contractLabel}</span>
          </span>
        </span>
      </div>
    </div>
  );
}

function ProductBrand({ onClick = null }) {
  const clickable = typeof onClick === "function";
  const className = `edim-brand${clickable ? " brand-home-button" : ""}`;
  const content = (
    <>
      <img
        className="edim-logo"
        src="./assets/undp-logo.svg?v=edim"
        alt="UNDP"
      />
      <span className="edim-brand-copy">
        <strong>Energy Development Modeling</strong>
        <small>United Nations Development Programme</small>
      </span>
    </>
  );
  if (clickable) {
    return (
      <button type="button" className={className} onClick={onClick} aria-label="Return to landing page">
        {content}
      </button>
    );
  }
  return (
    <div className={className}>
      {content}
    </div>
  );
}

function UnifiedHeader({
  currentUserId,
  availableUsers,
  onUserChange,
  apiTarget,
  systemCompatibility,
  onApiTargetModeChange,
  apiTargetLoading,
  onReturnToLanding,
}) {
  const activeUser = (availableUsers || []).find((user) => user.user_id === currentUserId) || null;
  const activeUserLabel = (activeUser && (activeUser.display_name || activeUser.user_id)) || currentUserId || "User";
  const handleUserSelect = (event) => {
    const userId = event.target.value;
    const menu = event.currentTarget.closest("details");
    if (menu) menu.removeAttribute("open");
    onUserChange(userId);
  };
  return (
    <header className="edim-topbar">
      <ProductBrand onClick={onReturnToLanding} />

      <div className="header-project-area" aria-hidden="true" />

      <div className="header-right-controls">
        <BackendTargetSwitch
          apiTarget={apiTarget}
          compatibility={systemCompatibility}
          onApiTargetModeChange={onApiTargetModeChange}
          disabled={apiTargetLoading}
        />
        <details className="header-user-menu">
          <summary role="button" aria-label={`User menu for ${activeUserLabel}`} title={activeUserLabel}>
            <img src="./assets/icons/user-round.svg" alt="" aria-hidden="true" />
          </summary>
          <div className="header-user-menu-body">
            <div className="header-user-heading">
              <b>{activeUserLabel}</b>
              <span>{(activeUser && (activeUser.organization || activeUser.email)) || "Active user"}</span>
            </div>
            <label className="header-user-select">
              <span>Switch user</span>
              <select value={currentUserId || ""} onChange={handleUserSelect} disabled={apiTargetLoading}>
                {(availableUsers || []).map((user) => (
                  <option key={user.user_id} value={user.user_id}>
                    {user.display_name || user.user_id}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </details>
      </div>
    </header>
  );
}

function LandingHeroVisualSlot({ tuning }) {
  const HeroBackground = window.EDIMHeroBackground && window.EDIMHeroBackground.HeroBackground;
  const resolvedTuning = {
    ...LANDING_HERO_BASE_TUNING,
    ...(tuning || {}),
  };
  return (
    <div className="landing-hero-visual-slot" aria-hidden="true">
      <div id="landing-hero-d3-root" className="landing-hero-d3-root" data-visual-slot="landing-hero-d3">
        {HeroBackground ? (
          <HeroBackground
            theme="solar"
            intensity={1.12}
            seed={31}
            tuning={resolvedTuning}
            style={{ zIndex: 0 }}
          />
        ) : null}
      </div>
    </div>
  );
}

function LandingCardVisual({ type }) {
  const visualClass = `landing-card-visual ${type}`;
  if (type === "country") {
    return (
      <div className={visualClass} aria-hidden="true">
        <svg viewBox="0 0 240 140">
          <path d="M24 98 C48 48, 86 78, 112 38 C148 -8, 192 34, 214 82" />
          <circle cx="66" cy="76" r="14" />
          <circle cx="122" cy="50" r="22" />
          <circle cx="184" cy="72" r="16" />
          <line x1="66" y1="76" x2="122" y2="50" />
          <line x1="122" y1="50" x2="184" y2="72" />
        </svg>
      </div>
    );
  }
  if (type === "evidence") {
    return (
      <div className={visualClass} aria-hidden="true">
        <svg viewBox="0 0 240 140">
          <rect x="28" y="88" width="28" height="24" />
          <rect x="70" y="64" width="28" height="48" />
          <rect x="112" y="42" width="28" height="70" />
          <rect x="154" y="72" width="28" height="40" />
          <path d="M36 48 L86 58 L126 28 L178 48 L210 30" />
          <circle cx="126" cy="28" r="8" />
        </svg>
      </div>
    );
  }
  return (
    <div className={visualClass} aria-hidden="true">
      <svg viewBox="0 0 240 140">
        <polygon points="54,34 90,54 90,96 54,116 18,96 18,54" />
        <polygon points="132,20 178,46 178,98 132,124 86,98 86,46" />
        <polygon points="204,42 232,58 232,90 204,106 176,90 176,58" />
        <line x1="90" y1="76" x2="86" y2="76" />
        <line x1="178" y1="74" x2="176" y2="74" />
      </svg>
    </div>
  );
}

function LandingPage({
  currentUserId,
  availableUsers,
  onUserChange,
  apiTarget,
  systemCompatibility,
  onApiTargetModeChange,
  apiTargetLoading,
  onEnter,
  onOpenMethodology,
  statusMessage,
  errorMessage,
}) {
  const currentUser = (availableUsers || []).find((user) => user.user_id === currentUserId) || null;
  const canEnter = Boolean(currentUserId) && !apiTargetLoading;
  const landingVideoSrc = String(window.EDIM_LANDING_VIDEO_SRC || "").trim();
  const [heroDefaults, setHeroDefaults] = useState(normalizeLandingHeroTuning(LANDING_HERO_BASE_TUNING));
  const heroFlashlightRef = useRef(null);
  useEffect(() => {
    let cancelled = false;
    async function loadHeroDefaults() {
      try {
        const response = await fetch(LANDING_HERO_DEFAULTS_PATH, { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = normalizeLandingHeroDefaults(await response.json());
        if (cancelled) return;
        setHeroDefaults(payload.tuningDefaults);
      } catch (err) {
        // The built-in base tuning remains the fallback if the static config is unavailable.
      }
    }
    loadHeroDefaults();
    return () => {
      cancelled = true;
    };
  }, []);
  useEffect(() => {
    const overlay = heroFlashlightRef.current;
    if (!overlay) return undefined;
    const clearFlashlight = () => {
      overlay.style.setProperty("--landing-hero-flashlight-opacity", "0");
    };
    window.addEventListener("blur", clearFlashlight);
    return () => window.removeEventListener("blur", clearFlashlight);
  }, []);
  function updateHeroFlashlight(event) {
    const overlay = heroFlashlightRef.current;
    if (!overlay) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / Math.max(rect.width, 1)) * 100;
    const y = ((event.clientY - rect.top) / Math.max(rect.height, 1)) * 100;
    overlay.style.setProperty("--landing-hero-flashlight-x", `${Math.max(0, Math.min(100, x)).toFixed(2)}%`);
    overlay.style.setProperty("--landing-hero-flashlight-y", `${Math.max(0, Math.min(100, y)).toFixed(2)}%`);
    const textAreaMultiplier = x < 48 ? 0.18 + (Math.max(0, x) / 48) * 0.38 : 0.62;
    overlay.style.setProperty("--landing-hero-flashlight-opacity", textAreaMultiplier.toFixed(3));
  }
  function clearHeroFlashlight() {
    const overlay = heroFlashlightRef.current;
    if (overlay) overlay.style.setProperty("--landing-hero-flashlight-opacity", "0");
  }
  return (
    <div className="landing-shell">
      <UnifiedHeader
        currentUserId={currentUserId}
        availableUsers={availableUsers}
        onUserChange={onUserChange}
        apiTarget={apiTarget}
        systemCompatibility={systemCompatibility}
        onApiTargetModeChange={onApiTargetModeChange}
        apiTargetLoading={apiTargetLoading}
        onReturnToLanding={null}
      />

      <main className="landing-main">
        <section className="landing-hero-section" onPointerMove={updateHeroFlashlight} onPointerLeave={clearHeroFlashlight}>
          <LandingHeroVisualSlot tuning={heroDefaults} />
          <div className="landing-hero-scrim" aria-hidden="true" />
          <div ref={heroFlashlightRef} className="landing-hero-flashlight" aria-hidden="true" />
          <div className="landing-hero-card">
            <h1>Model development outcomes from energy transition pathways.</h1>
            <p>
              Help countries connect energy-system choices to jobs, growth, emissions, affordability, and service delivery
              so transition planning can support development priorities and investment decisions.
            </p>
            <div className="landing-actions">
              <button type="button" className="landing-primary-action" onClick={onEnter} disabled={!canEnter}>
                Open projects
              </button>
              <button type="button" className="landing-secondary-action" onClick={onOpenMethodology}>
                Explore the methodology
              </button>
            </div>
            {errorMessage ? <div className="warn landing-message">{errorMessage}</div> : null}
            {statusMessage ? <div className="ok landing-message">{statusMessage}</div> : null}
          </div>
        </section>

        <section className="landing-video-section">
          <div className="landing-section-heading">
            <div className="landing-section-kicker">Platform overview</div>
            <h2>From energy pathways to development evidence.</h2>
            <p>
              The workspace is structured around projects, model architectures, scenario packages, model runs, exports,
              and comparison views so country teams can move from question to evidence without losing provenance.
            </p>
          </div>
          <div className="landing-video-frame">
            {landingVideoSrc ? (
              <video controls playsInline preload="metadata" src={landingVideoSrc}>
                Platform overview video.
              </video>
            ) : (
              <div className="landing-video-placeholder">
                <div className="landing-video-play" aria-hidden="true">▶</div>
                <div>
                  <div className="landing-video-title">Integrated modeling workflow</div>
                  <div className="landing-video-copy">Configure scenarios, connect model stages, and turn results into traceable evidence for policy and investment decisions.</div>
                </div>
              </div>
            )}
          </div>
        </section>

        <section className="landing-feature-section">
          <div className="landing-section-heading compact">
            <div className="landing-section-kicker">What the platform supports</div>
            <h2>Clean workflows for country energy-transition decisions.</h2>
          </div>
          <div className="landing-feature-grid">
            <article className="landing-feature-card">
              <LandingCardVisual type="energy" />
              <h3>Energy for development</h3>
              <p>Assess how power-sector pathways shape employment, value creation, emissions, reliability, and access outcomes.</p>
            </article>
            <article className="landing-feature-card">
              <LandingCardVisual type="country" />
              <h3>Country decision support</h3>
              <p>Organize scenarios around national planning questions, compare alternatives, and maintain traceable evidence for partners.</p>
            </article>
            <article className="landing-feature-card">
              <LandingCardVisual type="evidence" />
              <h3>Investment-ready outputs</h3>
              <p>Translate model runs into downloadable artifacts, reports, and comparison views that support prioritization and financing dialogue.</p>
            </article>
          </div>
        </section>
      </main>

      <footer className="landing-footer">
        <div>United Nations Development Programme</div>
        <div>Energy Development Modeling</div>
        <div>Decision support for sustainable energy transitions.</div>
      </footer>
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

function groupDataWireRows(rows) {
  const grouped = new Map();
  (rows || []).forEach((row) => {
    const groupKey = String(row.dataGroup || "").trim() || `single:${row.id}`;
    if (!grouped.has(groupKey)) {
      grouped.set(groupKey, {
        ...row,
        id: groupKey.startsWith("single:") ? row.id : groupKey,
        label: row.dataGroupLabel || row.label,
        variantLabels: [],
        variantIds: [],
      });
    }
    const target = grouped.get(groupKey);
    const variantLabel = row.variantLabel || row.label || row.id;
    if (variantLabel && !target.variantLabels.includes(variantLabel)) target.variantLabels.push(variantLabel);
    if (row.id && !target.variantIds.includes(row.id)) target.variantIds.push(row.id);
  });
  return Array.from(grouped.values()).map((row) => ({
    ...row,
    variantCount: row.variantLabels.length,
    variantSummary: row.variantLabels.join(", "),
  }));
}

function buildVisualWireRows(edges, mode, context = {}) {
  const sourceEdges = Array.isArray(edges) && edges.length ? edges : DEFAULT_FLOW_EDGES;
  const expandRows = (rows, dataOnly) => rows.flatMap((row) => {
    const layers = Array.isArray(row.layers) && row.layers.length
      ? row.layers
      : [{ id: row.id, label: row.label, type: row.type, activeWhen: row.activeWhen, informationLayer: row.informationLayer, purpose: row.purpose, granularity: row.granularity, parentId: row.id, parentLabel: row.label }];
    return layers
      .filter((layer) => {
        const typeMatches = !dataOnly || DATA_IO_WIRE_TYPES.has(normalizeIoWireType(layer.type || row.type));
        const activeMatches = !dataOnly || activeWhenMatches(layer.activeWhen || row.activeWhen, context);
        return typeMatches && activeMatches;
      })
      .map((layer) => ({
        ...layer,
        id: `${row.id}:${layer.id || layer.label}`,
        label: layer.label || row.label,
        type: normalizeIoWireType(layer.type || row.type),
        activeWhen: layer.activeWhen || row.activeWhen,
        informationLayer: layer.informationLayer || row.informationLayer || "",
        purpose: layer.purpose || row.purpose || "",
        granularity: layer.granularity || row.granularity || "",
        dataGroup: layer.dataGroup || row.dataGroup || "",
        dataGroupLabel: layer.dataGroupLabel || row.dataGroupLabel || "",
        variantLabel: layer.variantLabel || row.variantLabel || "",
        parentId: layer.parentId || row.id,
        parentLabel: layer.parentLabel || row.label,
      }));
  });
  return sourceEdges.flatMap((edge, edgeIndex) => {
    const rawIoRows = Array.isArray(edge.io) && edge.io.length ? edge.io : [];
    const dataRows = rawIoRows.filter((row) => DATA_IO_WIRE_TYPES.has(normalizeIoWireType(row && row.type)));
    const ioRows = mode === "layers"
      ? groupDataWireRows(expandRows(dataRows, true))
      : mode === "data" && rawIoRows.length
        ? rawIoRows
        : [{ id: "aggregate", label: edge.label || "aggregate flow", type: "aggregate" }];
    return ioRows.map((wire, wireIndex) => {
      const sourceType = normalizeIoWireType(wire.type);
      const informationLayer = ioInformationLayer(sourceType, wire.informationLayer);
      return {
        from: edge.from,
        to: edge.to,
        edgeLabel: edge.label || "",
        edgeKey: `${edge.from}-${edge.to}-${edgeIndex}`,
        wireKey: `${edge.from}-${edge.to}-${edgeIndex}-${wire.id || wireIndex}`,
        wireLabel: wire.label || wire.id || edge.label || "I/O",
        wireId: wire.id || `io-${wireIndex + 1}`,
        wireType: mode === "layers" ? ioWireDataGroup(sourceType) : mode === "data" ? informationLayer : "aggregate",
        sourceWireType: sourceType,
        informationLayer,
        purpose: wire.purpose || "",
        granularity: wire.granularity || "",
        activeWhenLabel: activeWhenLabel(wire.activeWhen),
        parentId: wire.parentId || "",
        parentLabel: wire.parentLabel || "",
        variantCount: Number(wire.variantCount || 0),
        variantSummary: wire.variantSummary || "",
        wireIndex,
        wireCount: ioRows.length,
      };
    });
  });
}

function IoWireLegend({ edges, mode, context }) {
  const rows = buildVisualWireRows(edges, mode, context);
    const counts = rows.reduce((acc, row) => {
    const type = row.wireType || "aggregate";
    acc[type] = (acc[type] || 0) + 1;
    return acc;
  }, {});
  const types = Object.keys(counts).sort((a, b) => {
    const order = mode === "layers" ? DATA_WIRE_GROUP_ORDER : INFORMATION_LAYER_ORDER;
    const ai = order.indexOf(a);
    const bi = order.indexOf(b);
    if (ai >= 0 && bi >= 0) return ai - bi;
    if (ai >= 0) return -1;
    if (bi >= 0) return 1;
    return ioWireStyle(a).label.localeCompare(ioWireStyle(b).label);
  });
  if (!types.length) return null;
  return (
    <div className="flow-io-legend" aria-label="I/O wire color legend">
      {types.map((type) => {
        const style = ioWireStyle(type);
        return (
          <span key={type} className="flow-io-legend-item">
            <span className="flow-io-legend-swatch" style={{ backgroundColor: style.color }} />
            <span>{style.label}</span>
            {mode !== "single" ? <span className="flow-io-legend-count">{counts[type]}</span> : null}
          </span>
        );
      })}
    </div>
  );
}

function FlowEdgeLayer({ positions, edges, canvas, mode = "single", context, onWireHover, onWireLeave }) {
  const canvasSize = canvas || DEFAULT_FLOW_CANVAS_SIZE;
  const edgeRows = Array.isArray(edges) && edges.length ? edges : DEFAULT_FLOW_EDGES;
  const visualRows = buildVisualWireRows(edgeRows, mode, context).filter((row) => positions[row.from] && positions[row.to]);
  const markerTypes = Array.from(new Set(visualRows.map((row) => row.wireType || "aggregate")));
  const renderedBundleLabels = new Set();
  const detailedMode = mode !== "single";
  const expandedWireMode = mode === "layers";
  const informationMode = mode === "data";
  const wireSpacing = expandedWireMode ? 5 : informationMode ? 10 : 28;
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
        {markerTypes.map((type) => {
          const style = ioWireStyle(type);
          return (
            <marker key={type} id={`flow-arrow-${type}`} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="strokeWidth">
              <path d="M 0 0 L 8 4 L 0 8 z" fill={style.color} opacity={detailedMode ? "0.74" : "0.9"} />
            </marker>
          );
        })}
      </defs>
      {visualRows.map((row) => {
        const from = positions[row.from];
        const to = positions[row.to];
        if (!from || !to) return null;
        const sourceSide = flowSideFor(from, to);
        const targetSide = flowSideFor(to, from);
        const outgoing = visualRows.filter((candidate) => {
          const rowFrom = positions[candidate.from];
          const rowTo = positions[candidate.to];
          return candidate.from === row.from && rowFrom && rowTo && flowSideFor(rowFrom, rowTo) === sourceSide;
        });
        const incoming = visualRows.filter((candidate) => {
          const rowFrom = positions[candidate.from];
          const rowTo = positions[candidate.to];
          return candidate.to === row.to && rowFrom && rowTo && flowSideFor(rowTo, rowFrom) === targetSide;
        });
        const sourceOffset = flowSlotOffset(outgoing.indexOf(row), outgoing.length, wireSpacing);
        const targetOffset = flowSlotOffset(incoming.indexOf(row), incoming.length, wireSpacing);
        const start = flowAnchor(from, sourceSide, sourceOffset);
        const end = flowAnchor(to, targetSide, targetOffset);
        const labelX = (start.x + end.x) / 2;
        const labelY = (start.y + end.y) / 2 - 8;
        const style = ioWireStyle(row.wireType);
        const sourceStyle = ioWireSourceStyle(row.sourceWireType);
        const showSingleLabel = mode === "single";
        const showBundleLabel = mode !== "single" && !renderedBundleLabels.has(row.edgeKey);
        if (showBundleLabel) renderedBundleLabels.add(row.edgeKey);
        const tooltip = {
          id: row.wireId,
          label: row.wireLabel,
          type: row.wireType,
          typeLabel: style.label,
          sourceTypeLabel: sourceStyle.label,
          edgeLabel: row.edgeLabel,
          purpose: row.purpose,
          granularity: row.granularity,
          activeWhenLabel: row.activeWhenLabel,
          parentLabel: row.parentLabel,
          variantCount: row.variantCount,
          variantSummary: row.variantSummary,
          from: row.from,
          to: row.to,
          mode,
        };
        return (
          <g key={row.wireKey} className={`flow-wire flow-wire-${row.wireType}`}>
            <path
              className="flow-edge-hover-target"
              d={flowEdgePath(from, to, sourceSide, targetSide, sourceOffset, targetOffset)}
              style={{ strokeWidth: expandedWireMode ? 4 : 7 }}
              onPointerMove={(event) => {
                if (typeof onWireHover === "function") {
                  onWireHover(tooltip, event);
                }
              }}
              onPointerLeave={() => {
                if (typeof onWireLeave === "function") onWireLeave();
              }}
            />
            <path
              className={`flow-edge ${detailedMode ? "flow-edge-io" : "flow-edge-single"}`}
              d={flowEdgePath(from, to, sourceSide, targetSide, sourceOffset, targetOffset)}
              markerEnd={`url(#flow-arrow-${row.wireType})`}
              style={{
                stroke: style.color,
                strokeWidth: expandedWireMode ? 0.9 : informationMode ? 1.7 : 2.4,
                opacity: expandedWireMode ? 0.64 : informationMode ? 0.76 : 0.78,
                strokeLinecap: "round",
              }}
            />
            {showSingleLabel ? (
              <text className="flow-edge-label" x={labelX} y={labelY}>{row.edgeLabel}</text>
            ) : null}
            {showBundleLabel ? (
              <text className="flow-edge-label flow-edge-bundle-label" x={(from.x + from.w / 2 + to.x + to.w / 2) / 2} y={(from.y + from.h / 2 + to.y + to.h / 2) / 2 - 12}>
                {row.edgeLabel} · {row.wireCount} {mode === "data" ? "info" : mode === "layers" ? "layers" : "I/O"}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}

function MethodologyArchitectureDiagram({
  selectedArchitecture = DEFAULT_MODEL_ARCHITECTURE_ID,
  architectureCatalog,
  activeNodeIds = [],
}) {
  const architecture = architectureById(
    architectureCatalog || normalizeArchitectureCatalog(null),
    selectedArchitecture
  );
  const flowDefinition = normalizeFlowDefinition(architecture && architecture.graph);
  const boxes = ((architecture && architecture.boxes) || ARCHITECTURE_BOXES).map((box) => ({ ...box }));
  const boxById = new Map(boxes.map((box) => [box.id, box]));
  const orderedNodeIds = flowDefinition.order || DEFAULT_FLOW_NODE_ORDER;
  const positions = flowDefinition.nodes || {};
  const canvas = flowDefinition.canvas || DEFAULT_FLOW_CANVAS_SIZE;
  const activeSet = new Set(activeNodeIds || []);
  const developmentMuted = selectedArchitecture === "energy-only" && architectureIncludesDevelopment(architecture);
  const mutedSet = new Set(developmentMuted ? ["bridge", "mrio", "mrio_data"] : []);
  const edges = (flowDefinition.edges || DEFAULT_FLOW_EDGES).filter((edge) => {
    if (!positions[edge.from] || !positions[edge.to]) return false;
    return !mutedSet.has(edge.from) && !mutedSet.has(edge.to);
  });

  return (
    <div className="methodology-architecture-diagram" aria-label={`${architecture.shortLabel || architecture.label} model architecture`}>
      <svg
        viewBox={`0 0 ${canvas.width} ${canvas.height}`}
        preserveAspectRatio="xMidYMid meet"
        aria-hidden="true"
      >
        <defs>
          <marker id="methodology-flow-arrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="strokeWidth">
            <path d="M 0 0 L 12 6 L 0 12 z" fill="#67e8f9" opacity="0.82" />
          </marker>
        </defs>
        {edges.map((edge) => {
          const from = positions[edge.from];
          const to = positions[edge.to];
          const sourceSide = flowSideFor(from, to);
          const targetSide = flowSideFor(to, from);
          const edgeRows = edges;
          const outgoing = edgeRows.filter((row) => row.from === edge.from && flowSideFor(positions[row.from], positions[row.to]) === sourceSide);
          const incoming = edgeRows.filter((row) => row.to === edge.to && flowSideFor(positions[row.to], positions[row.from]) === targetSide);
          const sourceOffset = flowSlotOffset(outgoing.indexOf(edge), outgoing.length, 36);
          const targetOffset = flowSlotOffset(incoming.indexOf(edge), incoming.length, 36);
          const start = flowAnchor(from, sourceSide, sourceOffset);
          const end = flowAnchor(to, targetSide, targetOffset);
          return (
            <g key={`${edge.from}-${edge.to}`}>
              <path d={flowEdgePath(from, to, sourceSide, targetSide, sourceOffset, targetOffset)} markerEnd="url(#methodology-flow-arrow)" />
              <text x={(start.x + end.x) / 2} y={(start.y + end.y) / 2 - 10}>{edge.label}</text>
            </g>
          );
        })}
      </svg>
      {orderedNodeIds.map((id) => {
        const box = boxById.get(id);
        const rect = positions[id];
        if (!box || !rect) return null;
        const isMuted = mutedSet.has(id);
        const isActive = activeSet.has(id) || (!activeSet.size && !isMuted);
        return (
          <article
            key={id}
            className={`methodology-architecture-node ${box.type} ${isMuted ? "muted" : ""} ${isActive ? "active" : ""}`}
            style={{
              left: `${(rect.x / canvas.width) * 100}%`,
              top: `${(rect.y / canvas.height) * 100}%`,
              width: `${(rect.w / canvas.width) * 100}%`,
              minHeight: `${Math.max(82, (rect.h / canvas.height) * 420)}px`,
            }}
          >
            <div className="methodology-architecture-node-type">{box.type}</div>
            <h3>{box.title}</h3>
            <p>{box.subtitle}</p>
          </article>
        );
      })}
    </div>
  );
}

window.EDIMMethodologyArchitectureDiagram = MethodologyArchitectureDiagram;

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
  const baseWidth = Number(rect.w) || 320;
  const expandedWidth = baseWidth + Math.min(120, Math.max(48, Math.round(baseWidth * 0.16)));
  const nodeStyle = { left: rect.x, top: rect.y, width: expanded ? expandedWidth : baseWidth };
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
      <div className="flow-node-hint">{fixed ? "Fixed model-definition band." : "Expand for controls and data."}</div>
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
      {!fixed ? (
        <div
          className="flow-node-drag-footer"
          onPointerDown={onPointerDown}
          title={`Drag to move ${box.title}`}
          aria-hidden="true"
        />
      ) : null}
      {status.state === "pending" ? <div className="flow-node-overlay">Pending</div> : null}
    </section>
  );
}

function FlowModelCanvas({
  activeJob,
  result,
  architecture,
  scenarioControls,
  calliopeDatasets,
  mrioDatasets,
  datasetsByNode,
  selectedRunId,
  inputsLocked = false,
  lockReason = "",
  onUploadDataset,
  onDatasetVersionChange,
  scenarioKey = "",
  scenarioSelections = {},
}) {
  const initialFlow = centerExpandedFlowNode(
    normalizeFlowDefinition(architecture && architecture.graph),
    "scenario"
  );
  const [flowDefinition, setFlowDefinition] = useState(() => initialFlow);
  const [positions, setPositions] = useState(() => initialFlow.nodes);
  const [measuredNodes, setMeasuredNodes] = useState({});
  const [expandedNodes, setExpandedNodes] = useState({ scenario: true });
  const [draggingId, setDraggingId] = useState("");
  const [canvasPanning, setCanvasPanning] = useState(false);
  const [ioWireMode, setIoWireMode] = useState("single");
  const [wireTooltip, setWireTooltip] = useState(null);
  const dragRef = useRef(null);
  const panRef = useRef(null);
  const viewportRef = useRef(null);
  const wireContext = useMemo(
    () => buildScenarioWireContext(scenarioKey, scenarioSelections),
    [scenarioKey, scenarioSelections]
  );
  const includesDevelopment = architectureIncludesDevelopment(architecture);
  const outputArtifacts = architectureOutputArtifacts(architecture);
  const fixedNodeSet = useMemo(() => new Set(flowDefinition.fixedNodes || []), [flowDefinition.fixedNodes]);
  const boxById = useMemo(() => {
    const rows = ((architecture && architecture.boxes) || ARCHITECTURE_BOXES).map((box) => [box.id, box]);
    return new Map(rows);
  }, [architecture]);

  const orderedNodeIds = flowDefinition.order || DEFAULT_FLOW_NODE_ORDER;
  const edgePositions = useMemo(() => {
    const rows = {};
    orderedNodeIds.forEach((id) => {
      if (!positions[id]) return;
      rows[id] = { ...positions[id], ...(measuredNodes[id] || {}) };
    });
    return rows;
  }, [orderedNodeIds, positions, measuredNodes]);
  const dynamicCanvas = useMemo(() => {
    const baseCanvas = flowDefinition.canvas || DEFAULT_FLOW_CANVAS_SIZE;
    let width = Number(baseCanvas.width) || DEFAULT_FLOW_CANVAS_SIZE.width;
    let height = Number(baseCanvas.height) || DEFAULT_FLOW_CANVAS_SIZE.height;
    orderedNodeIds.forEach((id) => {
      const rect = positions[id];
      if (!rect) return;
      const measured = measuredNodes[id] || {};
      const nodeWidth = Number(measured.w || rect.w || 0);
      const nodeHeight = Number(measured.h || rect.h || 0);
      if (Number.isFinite(nodeWidth)) width = Math.max(width, rect.x + nodeWidth + FLOW_CANVAS_NODE_PADDING);
      if (Number.isFinite(nodeHeight)) height = Math.max(height, rect.y + nodeHeight + FLOW_CANVAS_NODE_PADDING);
    });
    return {
      width: Math.ceil(width),
      height: Math.ceil(height),
    };
  }, [flowDefinition.canvas, measuredNodes, orderedNodeIds, positions]);

  useEffect(() => {
    const nextDefinition = centerExpandedFlowNode(
      normalizeFlowDefinition(architecture && architecture.graph),
      "scenario"
    );
    setFlowDefinition(nextDefinition);
    setPositions(nextDefinition.nodes);
    setMeasuredNodes({});
    setExpandedNodes({ scenario: true });
  }, [architecture && architecture.id]);

  useEffect(() => {
    const frameId = window.requestAnimationFrame(() => {
      const viewport = viewportRef.current;
      if (!viewport) return;
      viewport.scrollLeft = Math.max(0, (viewport.scrollWidth - viewport.clientWidth) / 2);
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [architecture && architecture.id]);

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
    const canvas = dynamicCanvas || flowDefinition.canvas || DEFAULT_FLOW_CANVAS_SIZE;
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

  function startCanvasPan(event) {
    if (event.button !== 0) return;
    if (
      event.target &&
      event.target.closest &&
      event.target.closest(".flow-node, button, input, select, textarea, a, label, .flow-edge-hover-target")
    ) {
      return;
    }
    const viewport = viewportRef.current;
    if (!viewport) return;
    viewport.setPointerCapture(event.pointerId);
    panRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      scrollLeft: viewport.scrollLeft,
      scrollTop: viewport.scrollTop,
    };
    setCanvasPanning(true);
    event.preventDefault();
  }

  function moveCanvasPan(event) {
    const pan = panRef.current;
    const viewport = viewportRef.current;
    if (!pan || !viewport || pan.pointerId !== event.pointerId) return;
    viewport.scrollLeft = pan.scrollLeft - (event.clientX - pan.startX);
    viewport.scrollTop = pan.scrollTop - (event.clientY - pan.startY);
  }

  function endCanvasPan(event) {
    const pan = panRef.current;
    const viewport = viewportRef.current;
    if (
      pan &&
      viewport &&
      viewport.hasPointerCapture &&
      viewport.hasPointerCapture(pan.pointerId)
    ) {
      viewport.releasePointerCapture(pan.pointerId);
    }
    panRef.current = null;
    setCanvasPanning(false);
  }

  function handleWireHover(payload, event) {
    if (!payload || !event) return;
    const bounds = event.currentTarget && event.currentTarget.ownerSVGElement
      ? event.currentTarget.ownerSVGElement.getBoundingClientRect()
      : null;
    setWireTooltip({
      ...payload,
      x: bounds ? event.clientX - bounds.left + 14 : 0,
      y: bounds ? event.clientY - bounds.top + 14 : 0,
    });
  }

  function clearWireTooltip() {
    setWireTooltip(null);
  }

  function renderNodeBody(id) {
    const box = boxById.get(id) || {};
    if (id === "scenario") return scenarioControls;
    if (id === "calliope_data") {
      return (
        <>
          <div className="diagram-note" style={{ marginBottom: 10 }}>
            Static energy-model data includes technology definitions, network/topology files, demand and resource time
            series, and model metadata. These datasets go directly into the Energy Model rather than through the adapter.
          </div>
          <DatasetRows
            datasets={(datasetsByNode && datasetsByNode[id]) || calliopeDatasets}
            onUpload={onUploadDataset}
            onDatasetVersionChange={onDatasetVersionChange}
            disabled={inputsLocked}
            disabledMessage={lockReason}
          />
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
          <DatasetRows
            datasets={(datasetsByNode && datasetsByNode[id]) || mrioDatasets}
            onUpload={onUploadDataset}
            onDatasetVersionChange={onDatasetVersionChange}
            disabled={inputsLocked}
            disabledMessage={lockReason}
          />
        </>
      );
    }
    if (id === "outputs") {
      return (
        <>
          <div className="diagram-note" style={{ marginBottom: 10 }}>
            <div><b>Downloadables:</b> artifacts listed here come from the selected architecture definition.</div>
            <div style={{ marginTop: 6 }}>
              <b>Displayed results:</b>{" "}
              {includesDevelopment
                ? "energy outputs, development outputs, source-channel diagnostics, and spatial filters."
                : "energy-system outputs only; MRIO/development artifacts and tabs are hidden."}
            </div>
          </div>
          <OutputRows runId={selectedRunId} summary={result && result.summary} artifacts={outputArtifacts} />
        </>
      );
    }
    if (id === "adapter") {
      return (
        <div className="diagram-note">
          <div><b>Role:</b> Resolves user selections against scenario source data, then writes model-specific run inputs.</div>
          <div style={{ marginTop: 6 }}><b>Energy outputs:</b> runtime patch, resolved scenario key, lever mappings, and <code>scenario/energy_input_manifest.json</code>.</div>
          {includesDevelopment ? (
            <div style={{ marginTop: 6 }}><b>MRIO outputs:</b> direct shock payloads plus <code>scenario/mrio_direct_inputs.json</code> and <code>scenario/mrio_direct_shocks.csv</code>.</div>
          ) : null}
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
          <div style={{ marginTop: 6 }}><b>Engine status:</b> Calliope is the active executable energy model.</div>
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
    if (Array.isArray(box.datasetLayers) && box.datasetLayers.length) {
      return (
        <DatasetRows
          datasets={(datasetsByNode && datasetsByNode[id]) || []}
          onUpload={onUploadDataset}
          onDatasetVersionChange={onDatasetVersionChange}
          disabled={inputsLocked}
          disabledMessage={lockReason}
        />
      );
    }
    return null;
  }

  return (
    <div className="flow-model-shell">
      <div className="flow-model-toolbar">
        <div className="flow-model-heading">
          <div className="flow-model-eyebrow">Model flow</div>
          <div className="flow-model-title">
            Configure the {architecture ? architecture.shortLabel || architecture.label : "selected"} run
          </div>
        </div>
        <div className="row flow-model-controls">
          <div className="flow-display-controls-expanded" aria-label="Graph display">
            <span className="flow-display-controls-label">Graph display</span>
            <div className="flow-display-controls-body">
              <div className="flow-io-mode-switch" role="group" aria-label="I/O wire display mode">
                <button
                  type="button"
                  className={ioWireMode === "single" ? "active" : ""}
                  onClick={() => setIoWireMode("single")}
                  aria-pressed={ioWireMode === "single"}
                >
                  Single
                </button>
                <button
                  type="button"
                  className={ioWireMode === "data" ? "active" : ""}
                  onClick={() => setIoWireMode("data")}
                  aria-pressed={ioWireMode === "data"}
                  title="Show packaged information flows by type"
                >
                  Data
                </button>
                <button
                  type="button"
                  className={ioWireMode === "layers" ? "active" : ""}
                  onClick={() => setIoWireMode("layers")}
                  aria-pressed={ioWireMode === "layers"}
                  title="Show detailed logical data layers passing through the model"
                >
                  Layers
                </button>
              </div>
              <button type="button" className="ghost-utility-button" onClick={() => setPositions(flowDefinition.nodes)}>Reset layout</button>
              <button
                type="button"
                className="ghost-utility-button"
                onClick={() => setExpandedNodes((prev) => {
                  const allExpanded = orderedNodeIds.every((id) => prev[id]);
                  return Object.fromEntries(orderedNodeIds.map((id) => [id, !allExpanded]));
                })}
              >
                {orderedNodeIds.every((id) => expandedNodes[id]) ? "Collapse all" : "Expand all"}
              </button>
            </div>
          </div>
        </div>
      </div>
      <div
        ref={viewportRef}
        className={`flow-model-viewport ${canvasPanning ? "panning" : ""}`}
        onPointerDown={startCanvasPan}
        onPointerMove={moveCanvasPan}
        onPointerUp={endCanvasPan}
        onPointerCancel={endCanvasPan}
      >
        <div className="flow-model-canvas" style={{ width: dynamicCanvas.width, height: dynamicCanvas.height }}>
          <FlowEdgeLayer
            positions={edgePositions}
            edges={flowDefinition.edges}
            canvas={dynamicCanvas}
            mode={ioWireMode}
            context={wireContext}
            onWireHover={handleWireHover}
            onWireLeave={clearWireTooltip}
          />
          {wireTooltip ? (
            <div
              className="flow-wire-tooltip"
              style={{
                left: Math.min(Math.max(12, wireTooltip.x), Math.max(12, dynamicCanvas.width - 280)),
                top: Math.min(Math.max(12, wireTooltip.y), Math.max(12, dynamicCanvas.height - 126)),
              }}
            >
              <div className="flow-wire-tooltip-kicker">{wireTooltip.from}{" -> "}{wireTooltip.to}</div>
              <div className="flow-wire-tooltip-title">{wireTooltip.mode === "single" ? wireTooltip.edgeLabel : wireTooltip.label}</div>
              <div className="flow-wire-tooltip-meta">
                <span>{wireTooltip.mode === "single" ? "aggregate" : wireTooltip.id}</span>
                <span>{wireTooltip.typeLabel}</span>
                {wireTooltip.mode !== "single" && wireTooltip.sourceTypeLabel && wireTooltip.sourceTypeLabel !== wireTooltip.typeLabel ? (
                  <span>{wireTooltip.sourceTypeLabel}</span>
                ) : null}
              </div>
              {wireTooltip.mode !== "single" && wireTooltip.edgeLabel ? (
                <div className="flow-wire-tooltip-flow">{wireTooltip.edgeLabel}</div>
              ) : null}
              {wireTooltip.purpose ? (
                <div className="flow-wire-tooltip-flow">{wireTooltip.purpose}</div>
              ) : null}
              {wireTooltip.granularity ? (
                <div className="flow-wire-tooltip-flow">Granularity: {wireTooltip.granularity}</div>
              ) : null}
              {wireTooltip.mode === "layers" && wireTooltip.activeWhenLabel ? (
                <div className="flow-wire-tooltip-flow">Active when {wireTooltip.activeWhenLabel}</div>
              ) : null}
              {(wireTooltip.mode === "data" || wireTooltip.mode === "layers") && wireTooltip.parentLabel && wireTooltip.parentLabel !== wireTooltip.label ? (
                <div className="flow-wire-tooltip-flow">Layer from: {wireTooltip.parentLabel}</div>
              ) : null}
              {wireTooltip.mode === "layers" && wireTooltip.variantCount > 1 ? (
                <div className="flow-wire-tooltip-flow">Regional variants grouped: {wireTooltip.variantSummary}</div>
              ) : null}
            </div>
          ) : null}
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
      <IoWireLegend edges={flowDefinition.edges} mode={ioWireMode} context={wireContext} />
    </div>
  );
}

function DiagramScenarioControls({
  architectureCatalog,
  selectedArchitectureId,
  selectedArchitecture,
  energyModelOptions = ENERGY_MODEL_OPTIONS,
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
  onArchitectureChange,
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
  inputsLocked = false,
  lockReason = "",
}) {
  const setupControlId = useId();
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
  const normalizedEnergyModelOptions = (Array.isArray(energyModelOptions) && energyModelOptions.length ? energyModelOptions : ENERGY_MODEL_OPTIONS)
    .map((option) => ({
      value: String(option && option.value ? option.value : ""),
      label: String((option && option.label) || (option && option.value) || ""),
      runtimeStatus: String((option && (option.runtimeStatus || option.runtime_status)) || ""),
      disabled: Boolean(option && option.disabled),
    }))
    .filter((option) => option.value);
  const selectedEnergyModel = normalizedEnergyModelOptions.find((option) => option.value === energyModelEngine) || normalizedEnergyModelOptions[0] || ENERGY_MODEL_OPTIONS[0];
  const architectureOptions = Array.isArray(architectureCatalog && architectureCatalog.architectures)
    ? architectureCatalog.architectures
    : defaultArchitectureCatalog().architectures;
  const requiresMrio = architectureIncludesDevelopment(selectedArchitecture);
  const adjustedLeverCount = [
    ["renewables_capex_multiplier", 1],
    ["fossil_fuel_price_multiplier", 1],
    ["carbon_price_usd_per_tco2", 0],
    ["demand_multiplier", 1],
  ].filter(([key, neutral]) => Math.abs(toNumber(levers && levers[key], neutral) - neutral) > 0.000001).length;
  if (inputsLocked) {
    return (
      <LockedScenarioSummary
        lockReason={lockReason}
        selectedArchitecture={selectedArchitecture}
        selectedEnergyModel={selectedEnergyModel}
        selectedScenario={selectedScenario}
        scenarioKey={scenarioKey}
        selectedTargetScenario={selectedTargetScenario}
        mrioScenarioId={mrioScenarioId}
        targetYear={targetYear}
        runProfile={runProfile}
        scenarioSelections={scenarioSelections}
        activePackage={activePackage}
        policyAvailable={policyAvailable}
        requiresMrio={requiresMrio}
        levers={levers}
      />
    );
  }

  return (
    <div className="diagram-scenario-controls">
      <div className="diagram-scenario-layout input-module-layout">
        <section className="diagram-selector-stack input-module-column" aria-labelledby="run-setup-heading">
          <div className="diagram-section-heading">
            <div className="diagram-section-label" id="run-setup-heading">Model setup</div>
            <small>{selectedEnergyModel.label} · {runProfile}</small>
          </div>
          <div className="diagram-control-grid cognitive-essential-grid">
            <div className="run-setup-group-eyebrow">Model</div>
            <div>
              <label htmlFor={`${setupControlId}-architecture`}>Model architecture</label>
              <select id={`${setupControlId}-architecture`} value={selectedArchitectureId || DEFAULT_MODEL_ARCHITECTURE_ID} onChange={(e) => onArchitectureChange(e.target.value)}>
                {architectureOptions.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.shortLabel || option.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor={`${setupControlId}-engine`}>Energy model engine</label>
              <select id={`${setupControlId}-engine`} value={selectedEnergyModel.value} onChange={(e) => onEnergyModelEngineChange(e.target.value)}>
                {normalizedEnergyModelOptions.map((option) => (
                  <option key={option.value} value={option.value} disabled={option.disabled}>
                    {option.label} - {option.runtimeStatus}
                  </option>
                ))}
              </select>
            </div>
            <div className="run-setup-group-eyebrow">Scenario</div>
            {showStructuredSelector ? (
              <div>
                <label htmlFor={`${setupControlId}-scenario-family`}>Main scenario type</label>
                <select
                  id={`${setupControlId}-scenario-family`}
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
            ) : (
              <div>
                <label htmlFor={`${setupControlId}-scenario`}>Energy scenario</label>
                <select id={`${setupControlId}-scenario`} value={scenarioKey} onChange={(e) => onScenarioChange(e.target.value)}>
                  {(scenarios || []).map((s) => (
                    <option key={s.key} value={s.key}>{s.title}</option>
                  ))}
                </select>
              </div>
            )}
            {requiresMrio ? (
              <div>
                <label htmlFor={`${setupControlId}-target-pathway`}>Target pathway</label>
                <select id={`${setupControlId}-target-pathway`} value={mrioScenarioId || ""} onChange={(e) => onMrioScenarioChange(e.target.value)}>
                  {(targetScenarios || []).map((s) => (
                    <option key={s.scenario_id} value={s.scenario_id}>
                      {s.short_label || s.label || s.scenario_id}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}
            <div>
              <label htmlFor={`${setupControlId}-target-year`}>Target year</label>
              <select id={`${setupControlId}-target-year`} value={Number(targetYear || 2030)} onChange={(e) => onTargetYearChange(Number(e.target.value))}>
                {(targetYears || [2030, 2050]).map((year) => (
                  <option key={year} value={Number(year)}>{year}</option>
                ))}
              </select>
            </div>
            <div className="run-setup-group-eyebrow">Execution</div>
            <div>
              <label htmlFor={`${setupControlId}-execution-profile`}>Execution profile</label>
              <select id={`${setupControlId}-execution-profile`} value={runProfile} onChange={(e) => onSetRunProfile(e.target.value)}>
                <option value="dev">Dev profile</option>
                <option value="analysis">Analysis profile</option>
                <option value="full">Full profile</option>
              </select>
            </div>
          </div>

          {showStructuredSelector && scenarioSelections.family === "pathway_2040" ? (
            <div className="input-module-subsection">
              <div className="diagram-section-heading">
                <div className="diagram-section-label">Pathway details</div>
                <small>{pathwayLabel(scenarioSelections.pathway)} · {SCENARIO_PACKAGE_LABELS[activePackage] || activePackage}</small>
              </div>
              <div className="diagram-control-grid">
                <div>
                  <label htmlFor={`${setupControlId}-demand-pathway`}>Demand pathway</label>
                  <select id={`${setupControlId}-demand-pathway`} value={scenarioSelections.pathway} onChange={(e) => onScenarioSelectionChange({ pathway: e.target.value })}>
                    {selectorModel.pathways.map((path) => (
                      <option key={path} value={path}>{pathwayLabel(path)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor={`${setupControlId}-build-package`}>Energy build package</label>
                  <select
                    id={`${setupControlId}-build-package`}
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
                  <label htmlFor={`${setupControlId}-policy-package`}>Policy package</label>
                  <select
                    id={`${setupControlId}-policy-package`}
                    value={scenarioSelections.policy ? "on" : "off"}
                    onChange={(e) => onScenarioSelectionChange({ policy: e.target.value === "on" })}
                    disabled={!policyAvailable}
                  >
                    <option value="off">Standard</option>
                    {policyAvailable ? <option value="on">Policy push</option> : null}
                  </select>
                </div>
              </div>
            </div>
          ) : null}
        </section>

        <section className="diagram-slider-stack input-module-column" aria-labelledby="policy-levers-heading">
          <div className="diagram-section-heading">
            <div className="diagram-section-label" id="policy-levers-heading">Policy levers</div>
            <small>{adjustedLeverCount ? `${adjustedLeverCount} adjusted` : "Neutral defaults"}</small>
          </div>
          <div className="input-module-levers">
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
            <div className="cognitive-inline-actions">
              {selectedScenario && selectedScenario.preset_levers ? (
                <button type="button" className="ghost-utility-button" onClick={onApplyTemplateLevers}>
                  Apply scenario defaults
                </button>
              ) : null}
              <button type="button" className="ghost-utility-button" onClick={onResetLevers}>
                Reset levers
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function RunTabs({
  jobs,
  selectedJobId,
  activeJob,
  mode,
  activeProject,
  onReturnToProject,
  onSelectJob,
  onRenameModel,
}) {
  const [renamingId, setRenamingId] = useState("");
  const [renameDraft, setRenameDraft] = useState("");
  const [renameSaving, setRenameSaving] = useState(false);
  const rows = jobs || [];
  const selectedRow = rows.find((job) => runExecutionId(job) === selectedJobId) || null;
  const visibleRows = rows.slice(0, 4);
  if (selectedRow && !visibleRows.includes(selectedRow)) {
    visibleRows.splice(Math.max(visibleRows.length - 1, 0), 1, selectedRow);
  }
  const visibleIds = new Set(visibleRows.map((job) => runExecutionId(job)));
  const overflowRows = rows.filter((job) => !visibleIds.has(runExecutionId(job)));
  const selectedOverflowId = overflowRows.some((job) => runExecutionId(job) === selectedJobId)
    ? selectedJobId
    : "";

  function startRename(event, job, displayedName) {
    if (typeof onRenameModel !== "function") return;
    event.preventDefault();
    event.stopPropagation();
    setRenamingId(runExecutionId(job));
    setRenameDraft(displayedName);
  }

  async function commitRename(job, previousName) {
    if (renameSaving) return;
    const nextName = String(renameDraft || "").trim();
    if (!nextName || nextName === previousName) {
      setRenamingId("");
      return;
    }
    setRenameSaving(true);
    try {
      await onRenameModel(job, nextName);
      setRenamingId("");
    } catch (_error) {
      // The workspace-level error surface reports persistence failures.
    } finally {
      setRenameSaving(false);
    }
  }

  return (
    <div className="run-tab-strip" aria-label="Project model navigation">
      <div className="run-project-context">
        <button type="button" className="workspace-back-button" onClick={onReturnToProject}>
          <span aria-hidden="true">←</span>
          <span>Return to project</span>
        </button>
        <div className="run-project-title" title={(activeProject && activeProject.title) || "Untitled project"}>
          {(activeProject && activeProject.title) || "Untitled project"}
        </div>
      </div>
      <div className="run-tab-list" role="tablist" aria-label="Models">
      {visibleRows.length ? visibleRows.map((job, index) => {
        const effective = activeJob && runExecutionId(activeJob) === runExecutionId(job)
          ? { ...job, ...activeJob, project_run_number: job.project_run_number || activeJob.project_run_number }
          : job;
        const status = displayStatus(effective.status);
        const statusKey = normalizeStatus(effective.status) || "unknown";
        const modelNumber = runProjectNumber(effective);
        const modelTitle = modelNumber ? `Model ${modelNumber}` : "Model";
        const customName = runCustomName(effective);
        const id = runExecutionId(effective);
        const selected = mode !== "project" && selectedJobId === id;
        const displayedName = customName || modelTitle;
        if (renamingId === id) {
          return (
            <div
              key={id || job.run_id}
              className={`run-tab run-tab-renaming status-${statusKey} ${selected ? "active" : ""}`}
            >
              <span className="run-tab-text">
                <input
                  type="text"
                  className="run-tab-rename-input"
                  aria-label={`Rename ${displayedName}`}
                  value={renameDraft}
                  maxLength={200}
                  autoFocus
                  disabled={renameSaving}
                  onChange={(event) => setRenameDraft(event.target.value)}
                  onBlur={() => commitRename(effective, displayedName)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      event.currentTarget.blur();
                    }
                    if (event.key === "Escape") {
                      event.preventDefault();
                      setRenamingId("");
                    }
                  }}
                />
                {customName ? <span className="run-tab-subtitle">{modelTitle}</span> : null}
              </span>
              <span className="run-tab-status-label">{renameSaving ? "Saving" : status.label}</span>
            </div>
          );
        }
        return (
          <button
            key={id || job.run_id}
            type="button"
            role="tab"
            className={`run-tab status-${statusKey} ${selected ? "active" : ""}`}
            aria-controls="model-workspace-primary"
            aria-selected={selected}
            tabIndex={selected || (mode === "project" && index === 0) ? 0 : -1}
            onClick={() => onSelectJob(effective)}
            onKeyDown={(event) => handleTablistKeyDown(
              event,
              index,
              visibleRows.length,
              (nextIndex) => onSelectJob(visibleRows[nextIndex])
            )}
            title={`${runLabel(effective)} - ${status.label}`}
            aria-label={`${runLabel(effective)} - ${status.label}`}
          >
            <span className="run-tab-text">
              <span
                className="run-tab-title"
                title="Double-click to rename model"
                onDoubleClick={(event) => startRename(event, effective, displayedName)}
              >
                {displayedName}
              </span>
              {customName ? <span className="run-tab-subtitle">{modelTitle}</span> : null}
            </span>
            <span className="run-tab-status-label">{status.label}</span>
          </button>
        );
      }) : null}
      {overflowRows.length ? (
        <label className="run-tab-overflow">
          <span className="sr-only">More models</span>
          <select
            aria-label={`More models (${overflowRows.length})`}
            value={selectedOverflowId}
            onChange={(event) => {
              const selected = overflowRows.find((job) => runExecutionId(job) === event.target.value);
              if (selected) onSelectJob(selected);
            }}
          >
            <option value="">More models ({overflowRows.length})</option>
            {overflowRows.map((job) => (
              <option key={runExecutionId(job) || job.run_id} value={runExecutionId(job)}>
                {runLabel(job)} - {displayStatus(job.status).label}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      </div>
    </div>
  );
}

function ReadOnlyScenarioValue({ label, value, note = "" }) {
  return (
    <div className="scenario-readonly-value">
      <div className="scenario-readonly-label">{label}</div>
      <div className="scenario-readonly-main">{value || "-"}</div>
      {note ? <div className="scenario-readonly-note">{note}</div> : null}
    </div>
  );
}

function LockedScenarioSummary({
  lockReason,
  selectedArchitecture,
  selectedEnergyModel,
  selectedScenario,
  scenarioKey,
  selectedTargetScenario,
  mrioScenarioId,
  targetYear,
  runProfile,
  scenarioSelections,
  activePackage,
  policyAvailable,
  requiresMrio,
  levers,
}) {
  const runProfileLabels = {
    dev: "Dev profile",
    analysis: "Analysis profile",
    full: "Full profile",
  };
  const familyLabel = scenarioSelections && scenarioSelections.family === "pathway_2040"
    ? "2040 pathway scenarios"
    : scenarioSelections && scenarioSelections.family === "transmission_only"
      ? "Transmission-only scenario"
      : scenarioSelections && scenarioSelections.family
        ? scenarioSelections.family
        : "-";
  const policyLabel = scenarioSelections && scenarioSelections.policy
    ? "Policy push"
    : policyAvailable
      ? "Standard"
      : "Standard";
  const leverRows = [
    ["Renewables CAPEX multiplier", levers && levers.renewables_capex_multiplier],
    ["Fossil variable cost multiplier", levers && levers.fossil_fuel_price_multiplier],
    ["Carbon price", levers && levers.carbon_price_usd_per_tco2, "USD/tCO2"],
    ["Demand multiplier", levers && levers.demand_multiplier],
  ];

  return (
    <div className="diagram-scenario-controls scenario-readonly-panel">
      <div className="diagram-note scenario-readonly-lock">
        <div>
          <b>Inputs locked:</b> {lockReason || "This selected run uses an immutable input snapshot."}
        </div>
      </div>

      <div className="diagram-scenario-layout input-module-layout">
        <section className="diagram-selector-stack input-module-column">
          <div className="diagram-section-heading">
            <div className="diagram-section-label">Model setup</div>
            <small>{selectedEnergyModel ? selectedEnergyModel.label : "-"} · {runProfileLabels[runProfile] || runProfile || "-"}</small>
          </div>
          <div className="scenario-readonly-grid">
            <div className="run-setup-group-eyebrow">Model</div>
            <ReadOnlyScenarioValue
              label="Model architecture"
              value={selectedArchitecture ? selectedArchitecture.shortLabel || selectedArchitecture.label : "-"}
            />
            <ReadOnlyScenarioValue
              label="Energy model"
              value={selectedEnergyModel ? selectedEnergyModel.label : "-"}
              note={selectedEnergyModel ? selectedEnergyModel.runtimeStatus : ""}
            />
            <div className="run-setup-group-eyebrow">Scenario</div>
            <ReadOnlyScenarioValue label="Main scenario type" value={familyLabel} />
            <ReadOnlyScenarioValue
              label="Energy scenario"
              value={selectedScenario ? selectedScenario.title : scenarioKey}
            />
            <ReadOnlyScenarioValue
              label="Target year"
              value={String(Number(targetYear || 2030))}
            />
            {requiresMrio ? (
              <ReadOnlyScenarioValue
                label="Target pathway"
                value={selectedTargetScenario ? selectedTargetScenario.short_label || selectedTargetScenario.label || selectedTargetScenario.scenario_id : mrioScenarioId}
              />
            ) : null}
            {scenarioSelections && scenarioSelections.family === "pathway_2040" ? (
              <>
                <ReadOnlyScenarioValue
                  label="Demand pathway"
                  value={pathwayLabel(scenarioSelections.pathway)}
                />
                <ReadOnlyScenarioValue
                  label="Energy build package"
                  value={SCENARIO_PACKAGE_LABELS[activePackage] || activePackage}
                />
                <ReadOnlyScenarioValue
                  label="Policy package"
                  value={policyLabel}
                />
              </>
            ) : null}
            <div className="run-setup-group-eyebrow">Execution</div>
            <ReadOnlyScenarioValue label="Execution profile" value={runProfileLabels[runProfile] || runProfile || "-"} />
          </div>
        </section>

        <section className="diagram-slider-stack input-module-column">
          <div className="diagram-section-heading">
            <div className="diagram-section-label">Policy levers</div>
            <small>{leverRows.length} values</small>
          </div>
          <div className="scenario-readonly-grid lever-grid">
            {leverRows.map(([label, rawValue, unit]) => (
              <ReadOnlyScenarioValue
                key={label}
                label={label}
                value={`${Number.isFinite(Number(rawValue)) ? compact(Number(rawValue)) : "-"}${unit ? ` ${unit}` : ""}`}
              />
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function UploadedDatasetsPanel({
  inputDatasets,
  projects,
  activeProjectId,
  onRefresh,
  actionLoading,
}) {
  const [versionsByDataset, setVersionsByDataset] = useState({});
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [datasetSearch, setDatasetSearch] = useState("");
  const [datasetFormat, setDatasetFormat] = useState("all");
  const [localActionLoading, setLocalActionLoading] = useState(false);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const defaultDatasetDraft = { label: "", role: "User-provided dataset", layer: "user" };
  const [createDraft, setCreateDraft] = useState(defaultDatasetDraft);
  const [createFile, setCreateFile] = useState(null);
  const [attachTarget, setAttachTarget] = useState(null);
  const [attachProjectId, setAttachProjectId] = useState(activeProjectId || "");
  const [renameTarget, setRenameTarget] = useState(null);
  const [renameLabel, setRenameLabel] = useState("");
  const [detailsTarget, setDetailsTarget] = useState(null);

  const allDatasets = Array.isArray(inputDatasets) ? inputDatasets : [];
  const datasets = allDatasets.filter(
    (dataset) => dataset && dataset.user_upload_listable !== false
  );
  const systemDatasets = allDatasets.filter(
    (dataset) => dataset && dataset.user_upload_listable === false
  );
  const activeProjects = (Array.isArray(projects) ? projects : []).filter(
    (project) => project && String(project.status || "active").toLowerCase() !== "archived"
  );
  const availableLayers = Array.from(new Set(
    datasets.map((dataset) => String(dataset.layer || "").trim()).filter(Boolean)
  )).sort();
  const datasetKey = datasets.map((row) => `${row.id}:${row.active_version_id || ""}`).join("|");
  const busy = Boolean(actionLoading || loading || localActionLoading);

  async function refreshVersions() {
    if (!datasets.length || typeof api.fetchInputDatasetVersions !== "function") {
      setVersionsByDataset({});
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      const pairs = await Promise.all(
        datasets.map(async (dataset) => [dataset.id, await api.fetchInputDatasetVersions(dataset.id)])
      );
      setVersionsByDataset(Object.fromEntries(pairs));
    } catch (err) {
      setMessage(toErrorMessage(err, "Failed to load uploaded dataset versions"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refreshVersions();
  }, [datasetKey]);

  const uploadedRows = datasets.flatMap((dataset) => (
    (versionsByDataset[dataset.id] || []).map((version) => ({
      dataset,
      version,
      active: dataset.active_version_id && dataset.active_version_id === version.version_id,
    }))
  ));
  function formatFromFilename(filename) {
    const ext = String(filename || "").split(".").pop();
    return ext && ext !== filename ? ext.toUpperCase() : "-";
  }
  const availableFormats = Array.from(new Set(
    uploadedRows.map(({ version }) => formatFromFilename(version.filename || version.version_id))
  )).sort();
  const normalizedDatasetSearch = datasetSearch.trim().toLowerCase();
  const filteredUploadedRows = uploadedRows.filter(({ dataset, version }) => {
    const filename = version.filename || version.version_id;
    const format = formatFromFilename(filename);
    if (datasetFormat !== "all" && format !== datasetFormat) return false;
    if (!normalizedDatasetSearch) return true;
    return [
      dataset.label,
      dataset.id,
      dataset.role,
      dataset.layer,
      filename,
      version.version_id,
    ].some((value) => String(value || "").toLowerCase().includes(normalizedDatasetSearch));
  });
  const filtersActive = Boolean(normalizedDatasetSearch || datasetFormat !== "all");

  function projectAvailabilityLabel(dataset, version) {
    const projectIds =
      (Array.isArray(version && version.project_ids) && version.project_ids) ||
      (Array.isArray(dataset && dataset.project_ids) && dataset.project_ids) ||
      (Array.isArray(dataset && dataset.attached_project_ids) && dataset.attached_project_ids) ||
      null;
    if (!projectIds) return "Available";
    return `${projectIds.length} project${projectIds.length === 1 ? "" : "s"}`;
  }

  async function refreshDatasetLibrary() {
    if (typeof onRefresh === "function") await onRefresh();
    await refreshVersions();
  }

  async function submitCreateDataset(event) {
    event.preventDefault();
    const label = String(createDraft.label || "").trim();
    const role = String(createDraft.role || "").trim();
    const layer = String(createDraft.layer || "").trim();
    if (!label || !role || !layer || !createFile) {
      setMessage("Dataset name, role, layer, and file are required.");
      return;
    }
    setLocalActionLoading(true);
    setMessage("");
    try {
      const created = await api.createInputDataset({
        label,
        role,
        layer,
        scope: "user",
        upload_policy: "project_override",
      });
      const datasetId = String((created && (created.id || created.dataset_id)) || "").trim();
      if (!datasetId) throw new Error("Dataset creation response did not include an id.");
      await api.uploadInputDataset(datasetId, createFile);
      await refreshDatasetLibrary();
      setCreateModalOpen(false);
      setCreateDraft(defaultDatasetDraft);
      setCreateFile(null);
      setMessage(`Created dataset "${label}" and uploaded ${createFile.name}.`);
    } catch (err) {
      setMessage(toErrorMessage(err, "Failed to create dataset"));
    } finally {
      setLocalActionLoading(false);
    }
  }

  function openAttachModal(dataset, version) {
    setAttachTarget({ dataset, version });
    setAttachProjectId(
      activeProjects.some((project) => project.project_id === activeProjectId)
        ? activeProjectId
        : ((activeProjects[0] && activeProjects[0].project_id) || "")
    );
    setMessage("");
  }

  async function submitAttachDataset(event) {
    event.preventDefault();
    if (!attachTarget || !attachProjectId) return;
    setLocalActionLoading(true);
    setMessage("");
    try {
      await api.attachInputDatasetToProject(attachProjectId, {
        dataset_id: attachTarget.dataset.id,
        version_id: attachTarget.version.version_id,
      });
      const project = activeProjects.find((row) => row.project_id === attachProjectId);
      setAttachTarget(null);
      await refreshDatasetLibrary();
      setMessage(`Added "${attachTarget.dataset.label || attachTarget.dataset.id}" to ${project ? project.title : "the selected project"}.`);
    } catch (err) {
      setMessage(toErrorMessage(err, "Failed to add dataset to project"));
    } finally {
      setLocalActionLoading(false);
    }
  }

  function openRenameModal(dataset) {
    setRenameTarget(dataset);
    setRenameLabel(dataset.label || dataset.id || "");
    setMessage("");
  }

  async function submitRenameDataset(event) {
    event.preventDefault();
    const label = String(renameLabel || "").trim();
    if (!renameTarget || !label) return;
    setLocalActionLoading(true);
    setMessage("");
    try {
      await api.updateInputDataset(renameTarget.id, { label });
      setRenameTarget(null);
      await refreshDatasetLibrary();
      setMessage(`Renamed dataset to "${label}".`);
    } catch (err) {
      setMessage(toErrorMessage(err, "Failed to rename dataset"));
    } finally {
      setLocalActionLoading(false);
    }
  }

  async function activateDatasetVersion(dataset, version) {
    setLocalActionLoading(true);
    setMessage("");
    try {
      await api.activateInputDatasetVersion(dataset.id, version.version_id);
      await refreshDatasetLibrary();
      setMessage(`Activated ${version.filename || version.version_id}.`);
    } catch (err) {
      setMessage(toErrorMessage(err, "Failed to activate dataset version"));
    } finally {
      setLocalActionLoading(false);
    }
  }

  async function deleteDatasetVersion(dataset, version) {
    const filename = version.filename || version.version_id;
    const confirmed = window.confirm(`Delete dataset version "${filename}"? Submitted model runs that reference it will block deletion.`);
    if (!confirmed) return;
    setLocalActionLoading(true);
    setMessage("");
    try {
      await api.deleteInputDatasetVersion(dataset.id, version.version_id);
      await refreshDatasetLibrary();
      setMessage(`Deleted dataset version "${filename}".`);
    } catch (err) {
      setMessage(toErrorMessage(err, "Failed to delete dataset version"));
    } finally {
      setLocalActionLoading(false);
    }
  }

  return (
    <div className="dataset-management-view">
      <div className="dataset-management-header">
        <div>
          <h2 style={{ margin: "0 0 4px" }}>Project data overrides</h2>
          <div className="muted" style={{ fontSize: 13 }}>{uploadedRows.length} uploaded versions</div>
        </div>
        <div className="dataset-management-actions">
          <button
            type="button"
            className="primary-action-button"
            onClick={() => {
              setCreateDraft((prev) => ({
                ...prev,
                layer: prev.layer || "user",
              }));
              setCreateModalOpen(true);
              setMessage("");
            }}
            disabled={busy}
          >
            Add override
          </button>
          <button
            type="button"
            className={`icon-button refresh-icon-button ${loading ? "is-loading" : ""}`}
            onClick={async () => {
              await refreshVersions();
              if (typeof onRefresh === "function") await onRefresh();
            }}
            disabled={busy}
            aria-label={loading ? "Refreshing datasets" : "Refresh datasets"}
            title={loading ? "Refreshing datasets" : "Refresh datasets"}
          >
            <span aria-hidden="true">↻</span>
          </button>
        </div>
      </div>
      {message ? <div className="warn" role="status" aria-live="polite" style={{ marginTop: 10 }}>{message}</div> : null}
      {createModalOpen ? (
        <Modal title="Add dataset" subtitle="Upload a reusable source" onClose={() => setCreateModalOpen(false)}>
          <form className="project-create-form dataset-action-form" onSubmit={submitCreateDataset}>
            <label>
              Dataset name
              <input
                type="text"
                value={createDraft.label}
                maxLength={200}
                placeholder="Example: National technology costs"
                onChange={(event) => setCreateDraft((prev) => ({ ...prev, label: event.target.value }))}
                autoFocus
                required
              />
            </label>
            <label>
              File
              <input
                type="file"
                accept=".csv,.json,.xlsx,.xls,.zip,.geojson,.yaml,.yml"
                onChange={(event) => setCreateFile((event.target.files && event.target.files[0]) || null)}
                required
              />
            </label>
            <details className="dataset-classification-disclosure">
              <summary>Classification</summary>
              <div className="dataset-classification-fields">
                <label>
                  Role
                  <input
                    type="text"
                    value={createDraft.role}
                    maxLength={120}
                    onChange={(event) => setCreateDraft((prev) => ({ ...prev, role: event.target.value }))}
                    required
                  />
                </label>
                <label>
                  Model layer
                  <input
                    type="text"
                    list="dataset-layer-options"
                    value={createDraft.layer}
                    maxLength={120}
                    onChange={(event) => setCreateDraft((prev) => ({ ...prev, layer: event.target.value }))}
                    required
                  />
                  <datalist id="dataset-layer-options">
                    {availableLayers.map((layer) => <option key={layer} value={layer} />)}
                  </datalist>
                </label>
              </div>
            </details>
            {message ? <div className="warn dataset-modal-message" role="alert">{message}</div> : null}
            <div className="modal-action-row">
              <button type="button" onClick={() => setCreateModalOpen(false)} disabled={localActionLoading}>Cancel</button>
              <button type="submit" className="run-play-button" disabled={localActionLoading || !createFile}>
                Create dataset
              </button>
            </div>
          </form>
        </Modal>
      ) : null}
      {attachTarget ? (
        <Modal title="Add to project" subtitle="Dataset assignment" onClose={() => setAttachTarget(null)}>
          <form className="project-create-form dataset-action-form" onSubmit={submitAttachDataset}>
            <div className="dataset-action-summary">
              <b>{attachTarget.dataset.label || attachTarget.dataset.id}</b>
              <span>{attachTarget.version.filename || attachTarget.version.version_id}</span>
            </div>
            <label>
              Project
              <select
                value={attachProjectId}
                onChange={(event) => setAttachProjectId(event.target.value)}
                autoFocus
                required
              >
                {!activeProjects.length ? <option value="">No active projects available</option> : null}
                {activeProjects.map((project) => (
                  <option key={project.project_id} value={project.project_id}>
                    {project.title || project.project_id}
                  </option>
                ))}
              </select>
            </label>
            {message ? <div className="warn dataset-modal-message" role="alert">{message}</div> : null}
            <div className="modal-action-row">
              <button type="button" onClick={() => setAttachTarget(null)} disabled={localActionLoading}>Cancel</button>
              <button type="submit" className="run-play-button" disabled={localActionLoading || !attachProjectId}>
                Add to project
              </button>
            </div>
          </form>
        </Modal>
      ) : null}
      {renameTarget ? (
        <Modal title="Rename dataset" subtitle="Dataset metadata" onClose={() => setRenameTarget(null)}>
          <form className="project-create-form dataset-action-form" onSubmit={submitRenameDataset}>
            <label>
              Dataset name
              <input
                type="text"
                value={renameLabel}
                maxLength={200}
                onChange={(event) => setRenameLabel(event.target.value)}
                autoFocus
                required
              />
            </label>
            {message ? <div className="warn dataset-modal-message" role="alert">{message}</div> : null}
            <div className="modal-action-row">
              <button type="button" onClick={() => setRenameTarget(null)} disabled={localActionLoading}>Cancel</button>
              <button type="submit" className="run-play-button" disabled={localActionLoading || !String(renameLabel || "").trim()}>
                Save name
              </button>
            </div>
          </form>
        </Modal>
      ) : null}
      {detailsTarget ? (
        <Modal title={detailsTarget.dataset.label || detailsTarget.dataset.id} subtitle="Dataset details" onClose={() => setDetailsTarget(null)}>
          <dl className="dataset-details-list">
            <div><dt>Dataset id</dt><dd><code>{detailsTarget.dataset.id}</code></dd></div>
            <div><dt>Version id</dt><dd><code>{detailsTarget.version.version_id}</code></dd></div>
            <div><dt>Role</dt><dd>{detailsTarget.dataset.role || "-"}</dd></div>
            <div><dt>Layer</dt><dd>{detailsTarget.dataset.layer || "-"}</dd></div>
            <div><dt>Source</dt><dd>{detailsTarget.dataset.path || detailsTarget.dataset.filename || "-"}</dd></div>
            <div><dt>File size</dt><dd>{compact(detailsTarget.version.size_bytes || 0)} bytes</dd></div>
            <div><dt>Project access</dt><dd>{projectAvailabilityLabel(detailsTarget.dataset, detailsTarget.version)}</dd></div>
            <div><dt>Updated</dt><dd>{formatTimestamp(detailsTarget.version.created_at)}</dd></div>
          </dl>
          <div className="modal-action-row">
            <button type="button" onClick={() => setDetailsTarget(null)}>Close</button>
          </div>
        </Modal>
      ) : null}
      {uploadedRows.length ? (
        <>
          <details className="dataset-filter-disclosure">
            <summary>
              <span>Filter datasets</span>
              <small>
                {filtersActive
                  ? `${filteredUploadedRows.length} of ${uploadedRows.length} versions`
                  : `${uploadedRows.length} versions`}
              </small>
            </summary>
            <div className="dataset-library-toolbar" role="search" aria-label="Filter dataset library">
              <label className="dataset-search-field">
                <span>Search datasets</span>
                <input
                  type="search"
                  value={datasetSearch}
                  onChange={(event) => setDatasetSearch(event.target.value)}
                  placeholder="Name, file, role, or version"
                />
              </label>
              <label className="dataset-format-field">
                <span>Format</span>
                <select value={datasetFormat} onChange={(event) => setDatasetFormat(event.target.value)}>
                  <option value="all">All formats</option>
                  {availableFormats.map((format) => (
                    <option key={format} value={format}>{format}</option>
                  ))}
                </select>
              </label>
              <div className="dataset-filter-summary" aria-live="polite">
                {filteredUploadedRows.length} of {uploadedRows.length} versions
              </div>
              {filtersActive ? (
                <button
                  type="button"
                  className="ghost-utility-button dataset-clear-filters"
                  onClick={() => {
                    setDatasetSearch("");
                    setDatasetFormat("all");
                  }}
                >
                  Clear filters
                </button>
              ) : null}
            </div>
          </details>
          <div className="dataset-table-wrap">
            <table className="panel-table dataset-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Format</th>
                  <th>Last updated</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredUploadedRows.length ? filteredUploadedRows.map(({ dataset, version, active }) => {
                  const filename = version.filename || version.version_id;
                  return (
                    <tr key={`${dataset.id}-${version.version_id}`}>
                      <td data-label="Dataset">
                        <b>{dataset.label || dataset.id}</b> {active ? <span className="badge badge-succeeded">Active</span> : null}
                        <div className="muted" style={{ fontSize: 11 }}>
                          {filename}
                        </div>
                      </td>
                      <td data-label="Format">{formatFromFilename(filename)}</td>
                      <td data-label="Updated">{formatTimestamp(version.created_at)}</td>
                      <td data-label="Actions">
                        <div className="dataset-table-actions">
                          <button
                            type="button"
                            className="dataset-primary-row-action"
                            onClick={() => openAttachModal(dataset, version)}
                            disabled={busy || !activeProjects.length}
                            title={activeProjects.length ? "Add this dataset version to a project" : "Create an active project first"}
                          >
                            Add to project
                          </button>
                          <details className="dataset-overflow-menu">
                            <summary aria-label={`Actions for ${dataset.label || dataset.id}`} title="More dataset actions">
                              ...
                            </summary>
                            <div className="dataset-overflow-menu-body">
                              <button type="button" onClick={() => setDetailsTarget({ dataset, version })}>View details</button>
                              <button type="button" onClick={() => openRenameModal(dataset)} disabled={busy}>Rename</button>
                              <button
                                type="button"
                                onClick={() => activateDatasetVersion(dataset, version)}
                                disabled={busy || active}
                              >
                                {active ? "Active version" : "Make active"}
                              </button>
                              <a href={api.inputDatasetVersionDownloadUrl(dataset.id, version.version_id)} download>Download</a>
                              <button
                                type="button"
                                className="danger-menu-button"
                                onClick={() => deleteDatasetVersion(dataset, version)}
                                disabled={busy}
                              >
                                Delete version
                              </button>
                            </div>
                          </details>
                        </div>
                      </td>
                    </tr>
                  );
                }) : (
                  <tr>
                    <td colSpan="4" className="dataset-no-results">
                      No dataset versions match the current filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <div className="dataset-empty-state">
          <div style={{ fontWeight: 900 }}>No project overrides.</div>
          <div className="muted" style={{ fontSize: 13, marginTop: 5 }}>
            This project currently uses the platform's system inputs without uploaded replacements.
          </div>
        </div>
      )}
      <section className="dataset-system-inputs" aria-labelledby="system-inputs-title">
        <div className="dataset-management-header">
          <div>
            <h3 id="system-inputs-title">System inputs</h3>
            <div className="muted" style={{ fontSize: 12 }}>
              Read-only reference data used unless a project override is attached.
            </div>
          </div>
          <span className="result-scope-token result-scope-token--scenario_wide">Platform managed</span>
        </div>
        {systemDatasets.length ? (
          <div className="dataset-system-input-list">
            {systemDatasets.map((dataset) => (
              <div className="dataset-system-input" key={dataset.id}>
                <div>
                  <strong>{dataset.label || dataset.id}</strong>
                  <small className="muted">
                    {[dataset.role, dataset.layer].filter(Boolean).join(" · ") || "Reference input"}
                  </small>
                </div>
                <small title={dataset.path || dataset.filename || ""}>
                  {dataset.active_version_id ? `Version ${dataset.active_version_id}` : "Bundled source"}
                </small>
              </div>
            ))}
          </div>
        ) : (
          <div className="muted" style={{ marginTop: 9, fontSize: 12 }}>
            System-input provenance is not available from the current backend.
          </div>
        )}
      </section>
    </div>
  );
}

function ModelRunManagementPane({
  activeJob,
  selectedJob,
  operationsPanel,
  errorMessage,
  statusMessage,
  runViewMode,
}) {
  const statusSource = activeJob || selectedJob;
  const normalizedStatus = normalizeStatus(statusSource && statusSource.status);
  const overallStatusLabel = statusSource
    ? displayStatus(statusSource.status).label
    : runViewMode === "project"
      ? "Project"
      : "Ready";
  return (
    <aside className="model-run-management-pane" aria-label="Model execution management">
      <div className="run-management-header">
        <div>
          <h2>Execution</h2>
        </div>
        <div className={`overall-run-status ${normalizedStatus || ""}`}>
          {overallStatusLabel}
        </div>
      </div>

      {errorMessage ? <div className="warn" style={{ marginTop: 0 }}>{errorMessage}</div> : null}
      {statusMessage ? <div className="ok" style={{ marginTop: errorMessage ? 8 : 0 }}>{statusMessage}</div> : null}

      <section className="run-management-section">
        {operationsPanel}
      </section>
    </aside>
  );
}

function NewModelModal({
  projectRuns,
  defaultName,
  onClose,
  onCreateBase,
  onCreateFromExisting,
  actionLoading = false,
}) {
  const candidates = (projectRuns || []).filter((run) => {
    const status = normalizeStatus(run && run.status);
    return run && run.run_id && status !== "cancelled" && run.request;
  });
  const [mode, setMode] = useState("base");
  const [name, setName] = useState("");
  const [sourceRunId, setSourceRunId] = useState((candidates[0] && candidates[0].run_id) || "");

  async function submit(event) {
    event.preventDefault();
    const cleanName = String(name || "").trim();
    const created = mode === "existing"
      ? await onCreateFromExisting(sourceRunId, cleanName)
      : await onCreateBase(cleanName);
    if (created) onClose();
  }

  return (
    <Modal title="New model" subtitle="Create an editable model draft" onClose={onClose}>
      <form className="project-create-form" onSubmit={submit}>
        <label>
          Model name
          <input
            type="text"
            value={name}
            maxLength={200}
            placeholder={defaultName || "Example: National policy target 2050"}
            onChange={(event) => setName(event.target.value)}
            autoFocus
          />
        </label>

        <fieldset className="new-model-choice-group">
          <legend>Starting point</legend>
          <label className="new-model-choice">
            <input
              type="radio"
              name="new-model-source"
              value="base"
              checked={mode === "base"}
              onChange={() => setMode("base")}
            />
            <span>
              <b>Start from base model</b>
              <small>Use the project architecture, default scenario inputs, default target year, and neutral policy levers.</small>
            </span>
          </label>
          <label className="new-model-choice">
            <input
              type="radio"
              name="new-model-source"
              value="existing"
              checked={mode === "existing"}
              onChange={() => setMode("existing")}
              disabled={!candidates.length}
            />
            <span>
              <b>Customize an existing model input</b>
              <small>Copy the selected model configuration into a new editable draft without changing the original.</small>
            </span>
          </label>
        </fieldset>

        {mode === "existing" ? (
          <label>
            Existing model input
            <select value={sourceRunId} onChange={(event) => setSourceRunId(event.target.value)} disabled={!candidates.length}>
              {candidates.map((run) => (
                <option key={run.run_id} value={run.run_id}>
                  {runLabel(run)} - {displayStatus(run.status).label}
                </option>
              ))}
            </select>
            {!candidates.length ? (
              <div className="muted" style={{ fontSize: 12, marginTop: 5 }}>
                No existing model inputs are available in this project yet.
              </div>
            ) : null}
          </label>
        ) : null}

        <div className="modal-action-row">
          <button type="button" onClick={onClose} disabled={actionLoading}>Cancel</button>
          <button
            type="submit"
            className="run-play-button"
            disabled={actionLoading || (mode === "existing" && !sourceRunId)}
          >
            Create draft
          </button>
        </div>
      </form>
    </Modal>
  );
}

function ProjectsOverviewPanel({
  projects,
  activeProjectId,
  activeProject,
  projectRuns,
  projectReports,
  projectExports,
  onOpenProject,
  onCreateProject,
  onRenameProject,
  onArchiveProject,
  onRestoreProject,
  onDeleteProject,
  onDownloadProjectFiles,
  onReturnHome,
  currentUser,
  actionLoading,
  isAdminView = false,
}) {
  const [editingProjectId, setEditingProjectId] = useState("");
  const [titleDrafts, setTitleDrafts] = useState({});
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [createDraft, setCreateDraft] = useState({
    title: "",
    geography: PROJECT_GEOGRAPHY_OPTIONS[0],
    model_architecture_id: "energy-development",
  });
  const activeProjects = (projects || []).filter((project) => String(project.status || "active").toLowerCase() !== "archived");
  const archivedProjects = (projects || []).filter((project) => String(project.status || "active").toLowerCase() === "archived");
  const activeProjectSummaries = activeProjects.map(projectVisualData);
  const workspaceModelCount = activeProjectSummaries.reduce((total, summary) => total + summary.modelCount, 0);
  const workspaceCompletedCount = activeProjectSummaries.reduce((total, summary) => total + summary.completedCount, 0);
  const workspaceGeographyCount = new Set(
    activeProjects
      .map((project) => projectGeographyLabel(project.geography))
      .filter(Boolean)
  ).size;
  const userDisplayName =
    (currentUser && (currentUser.display_name || currentUser.user_id)) ||
    "Current user";
  const userContext =
    (currentUser && (currentUser.organization || currentUser.email)) ||
    "Platform workspace";
  const lastActivityMs = [
    ...(projects || []),
    ...(projectRuns || []),
    ...(projectReports || []),
    ...(projectExports || []),
  ].reduce((latest, record) => {
    const timestamp = toTimestampMs(
      record && (
        record.updated_at ||
        record.finished_at ||
        record.started_at ||
        record.created_at
      )
    );
    return timestamp && timestamp > latest ? timestamp : latest;
  }, 0);
  const lastActivityLabel = lastActivityMs
    ? formatTimestamp(new Date(lastActivityMs).toISOString())
    : "This session";

  function draftTitle(project) {
    const id = project.project_id;
    return Object.prototype.hasOwnProperty.call(titleDrafts, id)
      ? titleDrafts[id]
      : (project.title || "");
  }

  async function saveTitle(project) {
    const nextTitle = String(draftTitle(project) || "").trim();
    if (!nextTitle || nextTitle === (project.title || "")) {
      setEditingProjectId("");
      return;
    }
    await onRenameProject(project.project_id, nextTitle);
    setEditingProjectId("");
  }

  async function submitCreateProject(event) {
    event.preventDefault();
    const title = String(createDraft.title || "").trim();
    const architectureId = String(createDraft.model_architecture_id || "energy-development");
    const created = await onCreateProject({
      title: title || "Untitled project",
      geography: String(createDraft.geography || "").trim(),
      model_architecture_id: architectureId,
      project_type: projectTypeForArchitecture(architectureId),
      scenario_label: architectureId === "energy-only" ? "Energy model workspace" : "Energy-Development model workspace",
    });
    if (!created) return;
    setCreateModalOpen(false);
    setCreateDraft({
      title: "",
      geography: PROJECT_GEOGRAPHY_OPTIONS[0],
      model_architecture_id: "energy-development",
    });
  }

  function renderProjectCard(project) {
    const selected = project.project_id === activeProjectId;
    const modifiedAt = project.updated_at || project.last_modified_at || project.created_at;
    const editing = editingProjectId === project.project_id;
    const visualData = projectVisualData(project);
    return (
      <div
        key={project.project_id}
        className={`dashboard-note project-card ${selected ? "row-selected" : ""}`}
      >
        <div className="project-card-visual-wrap">
          <ProjectIdentityVisual project={project} />
        </div>
        <button
          type="button"
          className="entity-card-open-target"
          aria-label={`Open project: ${project.title || "Untitled project"}`}
          onClick={() => onOpenProject(project.project_id)}
          disabled={actionLoading}
        />
        <div className="project-card-header">
          <div className="project-card-title-wrap">
            {editing ? (
              <div className="project-title-edit-row">
                <input
                  type="text"
                  value={draftTitle(project)}
                  maxLength={200}
                  onChange={(event) => setTitleDrafts((prev) => ({ ...prev, [project.project_id]: event.target.value }))}
                  style={{ width: "100%", minWidth: 0, fontWeight: 800 }}
                />
                <button type="button" onClick={() => saveTitle(project)} disabled={actionLoading}>Save</button>
                <button type="button" onClick={() => setEditingProjectId("")} disabled={actionLoading}>Cancel</button>
              </div>
            ) : (
              <div className="project-title-row">
                <div className="project-card-title">{project.title || "Untitled project"}</div>
                <button
                  type="button"
                  className="project-edit-icon"
                  aria-label={`Edit project name: ${project.title || "Untitled project"}`}
                  title="Edit project name"
                  onClick={() => {
                    setTitleDrafts((prev) => ({ ...prev, [project.project_id]: project.title || "" }));
                    setEditingProjectId(project.project_id);
                  }}
                  disabled={actionLoading}
                >
                  ✎
                </button>
              </div>
            )}
          </div>
          <details className="project-overflow-menu">
            <summary aria-label={`Project actions for ${project.title || "Untitled project"}`}>...</summary>
            <div className="project-overflow-menu-body">
              <button
                type="button"
                onClick={() => onDownloadProjectFiles(project.project_id)}
                disabled={actionLoading}
              >
                Download files
              </button>
              {String(project.status || "active").toLowerCase() === "archived" ? (
                <button type="button" onClick={() => onRestoreProject(project.project_id)} disabled={actionLoading}>Restore</button>
              ) : (
                <button type="button" onClick={() => onArchiveProject(project.project_id)} disabled={actionLoading}>Archive</button>
              )}
              <button
                type="button"
                onClick={() => onDeleteProject(project.project_id)}
                disabled={actionLoading}
                className="danger-menu-button"
              >
                Delete
              </button>
            </div>
          </details>
        </div>
        <div className="project-card-context">
          <span>{projectGeographyLabel(project.geography) || "No geography"}</span>
          <span>{projectTypeLabel(project)}</span>
        </div>
        {isAdminView ? (
          <div className="muted" style={{ marginTop: 4, fontSize: 12 }}>
            Owner: <code>{project.owner_user_id || "-"}</code>
          </div>
        ) : null}
        <div className="project-card-updated">
          Updated {formatTimestamp(modifiedAt)}
        </div>
        <div className="project-card-evidence">
          <EvidenceBadge status={visualData.evidenceStatus} compact />
        </div>
        <div className="project-card-footer">
          <div>
            <div>
              {visualData.modelCount} {visualData.modelCount === 1 ? "model" : "models"}
              {" · "}
              {visualData.completedCount} complete
            </div>
          </div>
          <button
            type="button"
            className="project-open-link"
            onClick={() => onOpenProject(project.project_id)}
            disabled={actionLoading}
          >
            Open project
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="card projects-overview-panel">
      <section className="modeling-workspace-intro" aria-labelledby="modeling-workspace-title">
        <div className="modeling-workspace-copy">
          <button
            type="button"
            className="workspace-return-home workspace-back-button"
            onClick={onReturnHome}
          >
            <span aria-hidden="true">←</span>
            <span>Return to home</span>
          </button>
          <div className="modeling-workspace-kicker">Analysis portfolio</div>
          <h1 id="modeling-workspace-title">Modeling Workspace</h1>
          <p>
            Organize energy and development analyses, explore alternative pathways,
            and bring model evidence together for planning and policy decisions.
          </p>
        </div>
        <div className="modeling-workspace-summary">
          <section className="modeling-workspace-user" aria-label="Current user">
            <span className="modeling-workspace-user-icon" aria-hidden="true" />
            <div className="modeling-workspace-user-identity">
              <small>Current user</small>
              <strong>{userDisplayName}</strong>
              <span>{userContext}</span>
            </div>
            <div className="modeling-workspace-user-activity">
              <small>Last active</small>
              <strong>{lastActivityLabel}</strong>
            </div>
          </section>
          <ul className="modeling-workspace-metrics" aria-label="Workspace summary">
            <li className="modeling-workspace-metric">
              <span className="modeling-workspace-metric-icon projects" aria-hidden="true" />
              <div>
                <span className="modeling-workspace-metric-label">Active projects</span>
                <strong className="modeling-workspace-metric-value">{activeProjects.length}</strong>
              </div>
            </li>
            <li className="modeling-workspace-metric">
              <span className="modeling-workspace-metric-icon models" aria-hidden="true" />
              <div>
                <span className="modeling-workspace-metric-label">Models</span>
                <strong className="modeling-workspace-metric-value">{workspaceModelCount}</strong>
              </div>
            </li>
            <li className="modeling-workspace-metric">
              <span className="modeling-workspace-metric-icon completed" aria-hidden="true" />
              <div>
                <span className="modeling-workspace-metric-label">Completed executions</span>
                <strong className="modeling-workspace-metric-value">{workspaceCompletedCount}</strong>
              </div>
            </li>
            <li className="modeling-workspace-metric">
              <span className="modeling-workspace-metric-icon geographies" aria-hidden="true" />
              <div>
                <span className="modeling-workspace-metric-label">Geographies</span>
                <strong className="modeling-workspace-metric-value">{workspaceGeographyCount}</strong>
              </div>
            </li>
          </ul>
        </div>
      </section>

      <section className="projects-collection" aria-labelledby="your-projects-title">
          <div className="row projects-overview-header" style={{ justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
            <div>
              <h2 id="your-projects-title" style={{ margin: "0 0 6px" }}>Your Projects</h2>
              <div className="muted" style={{ fontSize: 13 }}>
                {activeProjects.length} active · {archivedProjects.length} archived
              </div>
            </div>
            <div className="project-overview-actions">
              <button type="button" className="primary-action-button" onClick={() => setCreateModalOpen(true)} disabled={actionLoading}>
                New project
              </button>
            </div>
          </div>

          {createModalOpen ? (
            <Modal title="Create project" subtitle="Project setup" onClose={() => setCreateModalOpen(false)}>
              <form className="project-create-form" onSubmit={submitCreateProject}>
                <label>
                  Project name
                  <input
                    type="text"
                    value={createDraft.title}
                    maxLength={200}
                    placeholder="Example: South Africa energy transition"
                    onChange={(event) => setCreateDraft((prev) => ({ ...prev, title: event.target.value }))}
                    autoFocus
                  />
                </label>
                <label>
                  Geography
                  <select
                    value={createDraft.geography}
                    onChange={(event) => setCreateDraft((prev) => ({ ...prev, geography: event.target.value }))}
                  >
                    {PROJECT_GEOGRAPHY_OPTIONS.map((option) => (
                      <option key={option} value={option}>{option}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Type
                  <select
                    value={createDraft.model_architecture_id}
                    onChange={(event) => setCreateDraft((prev) => ({ ...prev, model_architecture_id: event.target.value }))}
                  >
                    {PROJECT_TYPE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </label>
                <div className="modal-action-row">
                  <button type="button" onClick={() => setCreateModalOpen(false)} disabled={actionLoading}>
                    Cancel
                  </button>
                  <button type="submit" className="run-play-button" disabled={actionLoading}>
                    Create project
                  </button>
                </div>
              </form>
            </Modal>
          ) : null}

          <div className="workspace-grid-3 active-project-grid">
            {activeProjects.length ? (
              activeProjects.map(renderProjectCard)
            ) : (
              <div className="dashboard-note" style={{ gridColumn: "1 / -1" }}>
                <div style={{ fontWeight: 800 }}>No active projects for this user yet.</div>
                <div className="muted" style={{ marginTop: 4, fontSize: 12 }}>
                  Create a project to start configuring and running models.
                </div>
              </div>
            )}
          </div>

          <details className="archived-projects-section">
            <summary>
              <span className="archived-projects-icon" aria-hidden="true" />
              <span className="archived-projects-copy">
                <strong>Archived projects</strong>
                <small>Projects retained outside the active workspace</small>
              </span>
              <span className="archived-projects-count">{archivedProjects.length}</span>
            </summary>
            <div className="archived-projects-body">
              {archivedProjects.length ? (
                <div className="workspace-grid-3 archived-project-grid">
                  {archivedProjects.map(renderProjectCard)}
                </div>
              ) : (
                <div className="archived-projects-empty">No archived projects.</div>
              )}
            </div>
          </details>
      </section>
    </div>
  );
}

function ComparisonValueCell({
  row,
  runId,
  baselineRunId,
  displayMode,
}) {
  const value = row.values[runId];
  const numeric = comparisonNumeric(value);
  const baseline = comparisonNumeric(row.values[baselineRunId]);
  const numericValues = Object.values(row.values).map(comparisonNumeric).filter((item) => item != null);
  const maxMagnitude = numericValues.length ? Math.max(...numericValues.map((item) => Math.abs(item)), 0) : 0;
  const magnitude = numeric != null && maxMagnitude > 0 ? Math.min(100, Math.abs(numeric) / maxMagnitude * 100) : 0;
  const delta = numeric != null && baseline != null ? numeric - baseline : null;
  const deltaShare = delta != null && Math.abs(baseline) > 1e-12 ? delta / Math.abs(baseline) : null;
  const isBaseline = runId === baselineRunId;
  const showAbsolute = displayMode !== "change";
  const showDelta = displayMode !== "absolute";

  if (value == null || value === "") return <td className="comparison-value-cell unavailable">Not available</td>;
  if (numeric == null) {
    return (
      <td className={`comparison-value-cell comparison-value-cell--text ${isBaseline ? "baseline" : ""}`}>
        <span>{String(value)}</span>
        {isBaseline ? <small>Reference</small> : null}
      </td>
    );
  }

  return (
    <td className={`comparison-value-cell ${isBaseline ? "baseline" : ""}`}>
      <div className="comparison-value-main">
        {showAbsolute ? <strong>{comparisonFormatValue(numeric, row.unit)}</strong> : null}
        {showDelta ? (
          <span className={`comparison-value-delta ${delta == null || Math.abs(delta) < 1e-12 ? "neutral" : delta > 0 ? "positive" : "negative"}`}>
            {isBaseline
              ? "Reference"
              : deltaShare == null
                ? delta == null ? "No reference" : `${delta > 0 ? "+" : ""}${comparisonFormatValue(delta, row.unit)}`
                : `${deltaShare > 0 ? "+" : ""}${(deltaShare * 100).toFixed(1)}%`}
          </span>
        ) : null}
      </div>
      <span className="comparison-value-track" aria-hidden="true">
        <span style={{ width: `${magnitude}%` }} />
      </span>
    </td>
  );
}

function ComparisonMatrix({
  rows,
  selectedRuns,
  summaries,
  baselineRunId,
  displayMode,
}) {
  const grouped = useMemo(() => {
    const groups = new Map();
    (rows || []).forEach((row) => {
      if (!groups.has(row.group)) groups.set(row.group, []);
      groups.get(row.group).push(row);
    });
    return Array.from(groups.entries());
  }, [rows]);

  if (!rows.length) {
    return <div className="comparison-empty">This output family is not available in the selected model summaries.</div>;
  }

  return (
    <div className="comparison-group-list">
      {grouped.map(([group, groupRows], groupIndex) => (
        <details key={group} className="comparison-output-group" open={groupIndex === 0}>
          <summary>
            <span>{group}</span>
            <small>{groupRows.length} outputs</small>
          </summary>
          <div className="comparison-table-scroll">
            <table className="comparison-matrix">
              <thead>
                <tr>
                  <th>Output</th>
                  {selectedRuns.map((run) => (
                    <th key={run.run_id}>
                      <span>{modelDisplayName(run)}</span>
                      <small>{modelNumberLabel(run)}</small>
                      <EvidenceBadge
                        status={evidenceFromModel(run, summaries && summaries[run.run_id]).status}
                        compact
                      />
                      {run.run_id === baselineRunId ? <small>Reference model</small> : null}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {groupRows.map((row) => (
                  <tr key={row.key}>
                    <th scope="row">
                      <span>{row.label}</span>
                      <small>
                        {[row.unit, row.resolution].filter(Boolean).join(" · ") || "Native model output"}
                      </small>
                    </th>
                    {selectedRuns.map((run) => (
                      <ComparisonValueCell
                        key={`${row.key}-${run.run_id}`}
                        row={row}
                        runId={run.run_id}
                        baselineRunId={baselineRunId}
                        displayMode={displayMode}
                      />
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ))}
    </div>
  );
}

function comparisonArtifactRows(selectedRuns, summaries, artifactCatalogs) {
  const rows = new Map();
  (selectedRuns || []).forEach((run) => {
    const runId = String(run && run.run_id || "");
    if (!runId) return;
    const summaryCatalog = Array.isArray(summaries[runId] && summaries[runId].artifact_catalog)
      ? summaries[runId].artifact_catalog
      : [];
    const fetchedCatalog = Array.isArray(artifactCatalogs[runId]) ? artifactCatalogs[runId] : [];
    const catalog = fetchedCatalog.length ? fetchedCatalog : summaryCatalog;
    catalog.forEach((artifact) => {
      if (!artifact || typeof artifact !== "object") return;
      const artifactId = String(artifact.artifact_id || artifact.key || "").trim();
      if (!artifactId) return;
      if (!rows.has(artifactId)) {
        rows.set(artifactId, {
          key: artifactId,
          label: String(artifact.label || comparisonHumanize(artifactId)),
          kind: String(artifact.kind || ""),
          mediaType: String(artifact.media_type || ""),
          runs: {},
        });
      }
      const href = window.EDIM_WORKSPACE_CONTRACTS && typeof window.EDIM_WORKSPACE_CONTRACTS.artifactHref === "function"
        ? window.EDIM_WORKSPACE_CONTRACTS.artifactHref(runId, artifact)
        : "";
      rows.get(artifactId).runs[runId] = {
        ...artifact,
        href,
      };
    });
  });
  return Array.from(rows.values()).sort((left, right) => left.label.localeCompare(right.label));
}

function ComparisonArtifactMatrix({
  selectedRuns,
  summaries,
  artifactCatalogs,
}) {
  const rows = useMemo(
    () => comparisonArtifactRows(selectedRuns, summaries, artifactCatalogs),
    [selectedRuns, summaries, artifactCatalogs]
  );
  if (!rows.length) {
    return <div className="comparison-empty">No downloadable output catalog is available for the selected models.</div>;
  }
  return (
    <div className="comparison-table-scroll">
      <table className="comparison-matrix comparison-artifact-matrix">
        <thead>
          <tr>
            <th>Output file</th>
            {selectedRuns.map((run) => (
              <th key={run.run_id}>
                <span>{modelDisplayName(run)}</span>
                <small>{modelNumberLabel(run)}</small>
                <EvidenceBadge
                  status={evidenceFromModel(run, summaries && summaries[run.run_id]).status}
                  compact
                />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <th scope="row">
                <span>{row.label}</span>
                <small>{[row.kind, row.mediaType, row.key].filter(Boolean).join(" · ")}</small>
              </th>
              {selectedRuns.map((run) => {
                const artifact = row.runs[run.run_id];
                return (
                  <td key={`${row.key}-${run.run_id}`} className={`comparison-artifact-cell ${artifact ? "" : "unavailable"}`}>
                    {artifact ? (
                      <>
                        {artifact.href ? <a href={artifact.href} download>Download</a> : <strong>Available</strong>}
                        <small>{artifact.size_bytes != null ? `${compact(artifact.size_bytes)} bytes` : "Persisted output"}</small>
                      </>
                    ) : "Not available"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProjectComparePanel({
  activeProject,
  projectRuns,
  projectReports,
  projectExports,
  compareRunIds,
  onToggleCompareRun,
  onCreateReport,
  onCreateRunExport,
  onNewModel,
  onOpenRun,
  onReturnToProjects,
  actionLoading = false,
  isAdminView = false,
}) {
  // Project-level view reads completed run summaries from persisted artifacts.
  // It does not depend on live execution internals and remains a parent page
  // above individual immutable or editable model runs.
  const [workspaceTab, setWorkspaceTab] = useState("selection");
  const runs = projectRuns || [];
  const successfulRuns = succeededProjectRuns(runs);
  const activeRuns = runs.filter((run) => ["queued", "running"].includes(normalizeStatus(run && run.status)));
  const selectedIds = compareRunIds;
  const selectedRuns = successfulRuns.filter((run) => selectedIds.includes(run.run_id));
  const modifiedAt = activeProject && (activeProject.updated_at || activeProject.last_modified_at || activeProject.created_at);
  const projectTitle = (activeProject && activeProject.title) || "Untitled project";
  const projectNotes = String((activeProject && activeProject.notes) || "").trim();
  const meaningfulProjectNotes = projectNotes === "Created from the projects overview." ? "" : projectNotes;
  const projectDescription = String(
    meaningfulProjectNotes ||
    (activeProject && activeProject.scenario_label) ||
    "A shared workspace for configuring, running, and comparing energy-development models."
  ).trim();
  const projectGeography = activeProject && projectGeographyLabel(activeProject.geography);
  const projectFocus = String((activeProject && activeProject.scenario_label) || "").trim();
  const reportLabel = selectedRuns.length > 1 ? "Generate comparison report" : "Generate project report";
  const [summaries, setSummaries] = useState({});
  const [artifactCatalogs, setArtifactCatalogs] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [comparisonSection, setComparisonSection] = useState("overview");
  const [baselineRunId, setBaselineRunId] = useState("");
  const [comparisonDisplayMode, setComparisonDisplayMode] = useState("both");

  useEffect(() => {
    const missing = selectedRuns
      .map((run) => run.run_id)
      .filter((runId) => (
        runId &&
        (
          !summaries[runId] ||
          !Object.prototype.hasOwnProperty.call(artifactCatalogs, runId)
        )
      ));
    if (!missing.length) return;
    let cancelled = false;
    async function loadSummaries() {
      setLoading(true);
      setError("");
      try {
        const rows = await Promise.all(missing.map(async (runId) => {
          const summary = summaries[runId] || await api.fetchSummary(runId);
          const artifacts = Object.prototype.hasOwnProperty.call(artifactCatalogs, runId)
            ? artifactCatalogs[runId]
            : await api.fetchRunArtifacts(runId).catch(() => []);
          return [runId, summary, artifacts];
        }));
        if (cancelled) return;
        setSummaries((prev) => {
          const next = { ...prev };
          rows.forEach(([runId, summary]) => {
            next[runId] = summary;
          });
          return next;
        });
        setArtifactCatalogs((prev) => {
          const next = { ...prev };
          rows.forEach(([runId, , artifacts]) => {
            next[runId] = artifacts;
          });
          return next;
        });
      } catch (err) {
        if (!cancelled) setError(toErrorMessage(err, "Failed to load model outputs for comparison"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadSummaries();
    return () => {
      cancelled = true;
    };
  }, [
    selectedRuns.map((run) => run.run_id).join("|"),
    Object.keys(summaries).sort().join("|"),
    Object.keys(artifactCatalogs).sort().join("|"),
  ]);

  useEffect(() => {
    const selectedRunIds = selectedRuns.map((run) => run.run_id);
    if (!selectedRunIds.includes(baselineRunId)) setBaselineRunId(selectedRunIds[0] || "");
  }, [selectedRuns.map((run) => run.run_id).join("|"), baselineRunId]);

  const comparisonDatasets = useMemo(
    () => buildComparisonDatasets(selectedRuns, summaries),
    [selectedRuns, summaries]
  );
  const artifactComparisonRows = useMemo(
    () => comparisonArtifactRows(selectedRuns, summaries, artifactCatalogs),
    [selectedRuns, summaries, artifactCatalogs]
  );
  const activeComparisonDefinition = COMPARISON_OUTPUT_SECTIONS.find((section) => section.key === comparisonSection)
    || COMPARISON_OUTPUT_SECTIONS[0];
  const activeComparisonRows = comparisonDatasets[activeComparisonDefinition.key] || [];

  function runTimestamp(run) {
    return formatTimestamp(run.updated_at || run.finished_at || run.started_at || run.created_at);
  }

  function openComparison() {
    if (selectedRuns.length < 2) return;
    setWorkspaceTab("comparison");
  }

  return (
    <div className="project-workspace-page card">
      {workspaceTab === "selection" ? (
        <section className="project-information-bar" aria-label={`Project overview: ${projectTitle}`}>
        <div className="project-information-main">
          <div className="project-information-heading-row">
            <button
              type="button"
              className="project-information-back workspace-back-button"
              onClick={onReturnToProjects}
            >
              <span aria-hidden="true">←</span>
              <span>Back to projects</span>
            </button>
            <div className="project-information-heading-copy">
              <div className="project-information-eyebrow">Project workspace</div>
              <h1>{projectTitle}</h1>
            </div>
          </div>
          <p>{projectDescription}</p>
          <div className="project-information-metadata">
            <div className="project-information-meta-item">
              <span className="project-information-icon icon-map-pin" aria-hidden="true" />
              <span>
                <small>Geography</small>
                <b>{projectGeography || "Not specified"}</b>
              </span>
            </div>
            <div className="project-information-meta-item">
              <span className="project-information-icon icon-layers" aria-hidden="true" />
              <span>
                <small>Modeling scope</small>
                <b>{activeProject ? projectTypeLabel(activeProject) : "Energy-Development"}</b>
              </span>
            </div>
            {projectFocus ? (
              <div className="project-information-meta-item">
                <span className="project-information-icon icon-target" aria-hidden="true" />
                <span>
                  <small>Project focus</small>
                  <b>{projectFocus}</b>
                </span>
              </div>
            ) : null}
            <div className="project-information-meta-item">
              <span className="project-information-icon icon-calendar" aria-hidden="true" />
              <span>
                <small>Last updated</small>
                <b>{modifiedAt ? formatTimestamp(modifiedAt) : "Not available"}</b>
              </span>
            </div>
            {isAdminView && activeProject && activeProject.owner_user_id ? (
              <div className="project-information-meta-item">
                <span className="project-information-icon icon-user" aria-hidden="true" />
                <span>
                  <small>Owner</small>
                  <b>{activeProject.owner_user_id}</b>
                </span>
              </div>
            ) : null}
          </div>
        </div>
        <div className="project-information-summary">
          <div className="project-information-visual">
            {activeProject ? <ProjectIdentityVisual project={activeProject} /> : null}
          </div>
          <div className="project-information-stats" aria-label="Project totals">
            <div>
              <strong>{runs.length}</strong>
              <span>Models</span>
            </div>
            <div>
              <strong>{successfulRuns.length}</strong>
              <span>Complete</span>
            </div>
            <div>
              <strong>{activeRuns.length}</strong>
              <span>In progress</span>
            </div>
            <div>
              <strong>{(projectReports || []).length}</strong>
              <span>Reports</span>
            </div>
          </div>
          <button
            type="button"
            className="primary-action-button project-information-new-model"
            onClick={onNewModel}
            disabled={actionLoading || !activeProject}
          >
            <span aria-hidden="true">+</span>
            New model
          </button>
        </div>
        </section>
      ) : null}

      {workspaceTab === "selection" ? (
        <section
          className="project-selection-workbench"
          aria-label="Project models"
        >
          <div className="project-selection-toolbar">
            <div>
              <h2>Models</h2>
              <div className="muted">{runs.length} models · {successfulRuns.length} complete · {selectedRuns.length} selected</div>
            </div>
            <button
              type="button"
              className="secondary-action-button model-comparison-launch"
              disabled={selectedRuns.length < 2}
              onClick={openComparison}
              title={selectedRuns.length < 2 ? "Select at least two completed models" : "Open model comparison"}
            >
              <span>Compare models</span>
              <b aria-label={`${selectedRuns.length} selected`}>{selectedRuns.length}</b>
            </button>
          </div>

          <div className="project-run-card-grid">
            {runs.length ? runs.map((run) => {
              const complete = normalizeStatus(run.status) === "succeeded";
              const checked = compareRunIds.includes(run.run_id);
              return (
                <article
                  key={run.run_id}
                  className={`project-model-card ${checked ? "selected" : ""}`}
                >
                  <button
                    type="button"
                    className="entity-card-open-target"
                    aria-label={`Open model: ${modelDisplayName(run)}`}
                    onClick={() => onOpenRun(run)}
                  />
                  <div className="project-model-card-head">
                    <div>
                      <h3>{modelDisplayName(run)}</h3>
                      <div className="muted">{modelNumberLabel(run)} · {runMetadataLine(run)}</div>
                    </div>
                    <StatusBadge status={run.status} />
                  </div>
                  <div className="project-model-card-visual">
                    <ModelIdentityVisual run={run} />
                  </div>
                  <div className="project-model-card-actions">
                    <div>
                      <EvidenceBadge
                        status={evidenceFromModel(run, summaries[run.run_id]).status}
                        summary={evidenceFromModel(run, summaries[run.run_id]).summary}
                        compact
                      />
                    </div>
                    <div className="project-card-open-actions">
                      {complete ? (
                        <label className="project-compare-toggle">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => onToggleCompareRun(run.run_id)}
                          />
                          Compare
                        </label>
                      ) : null}
                      {complete ? (
                        <button type="button" className="ghost-utility-button" onClick={() => onCreateRunExport(run.run_id)} disabled={actionLoading}>Export</button>
                      ) : null}
                      <button
                        type="button"
                        className="secondary-action-button project-primary-open"
                        onClick={() => onOpenRun(run)}
                      >
                        Open model
                      </button>
                    </div>
                  </div>
                </article>
              );
            }) : (
              <div className="dashboard-note" style={{ gridColumn: "1 / -1" }}>
                <div style={{ fontWeight: 900 }}>No models yet.</div>
                <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>Create a model to start configuring the project scenario.</div>
              </div>
            )}
          </div>

          <div className="project-secondary-panels">
            <details className="project-secondary-panel project-secondary-disclosure">
              <summary>
                <span>Reports</span>
                <small>{(projectReports || []).length}</small>
              </summary>
              <div className="project-secondary-disclosure-body">
                <div className="project-selection-section-header">
                  <div className="muted">Generated from completed model outputs.</div>
                <button type="button" className="secondary-action-button" onClick={onCreateReport} disabled={actionLoading || !successfulRuns.length}>{reportLabel}</button>
                </div>
                {(projectReports || []).length ? (
                  <div className="project-artifact-list">
                    {(projectReports || []).slice(0, 6).map((report) => (
                      <div key={report.report_id} className="diagram-dataset-version-row">
                        <div>
                          <div>
                            <b>{report.report_type || "Project report"}</b>{" "}
                            <StatusBadge status={report.status} />{" "}
                            <EvidenceBadge status={report.evidence_status} compact />
                          </div>
                          <div className="project-artifact-meta" title={`Report id: ${report.report_id || "-"}`}>
                            {(report.run_ids || []).length} models
                            {report.created_at ? ` · ${formatTimestamp(report.created_at)}` : ""}
                          </div>
                        </div>
                        <div className="diagram-dataset-actions">
                          <a href={api.projectReportDownloadUrl(report.project_id, report.report_id)} download>Report</a>
                          {report.source_data_url ? <a href={api.projectReportDataUrl(report.project_id, report.report_id)} download>Data</a> : null}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : <div className="muted">No reports generated yet.</div>}
              </div>
            </details>

            <details className="project-secondary-panel project-secondary-disclosure">
              <summary>
                <span>Exports</span>
                <small>{(projectExports || []).length}</small>
              </summary>
              <div className="project-secondary-disclosure-body">
                {(projectExports || []).length ? (
                  <div className="project-artifact-list">
                    {(projectExports || []).slice(0, 6).map((row) => (
                      <div key={row.export_id} className="diagram-dataset-version-row">
                        <div>
                          <div>
                            <b>{(row.run_ids || []).length === 1 ? "Model export" : "Project files export"}</b>{" "}
                            <StatusBadge status={row.status} />{" "}
                            <EvidenceBadge status={row.evidence_status} compact />
                          </div>
                          <div className="project-artifact-meta" title={`Export id: ${row.export_id || "-"}`}>
                            {compact(row.size_bytes || 0)} bytes
                            {row.created_at ? ` · ${formatTimestamp(row.created_at)}` : ""}
                          </div>
                        </div>
                        <a href={api.projectExportDownloadUrl(row.project_id, row.export_id)} download>Download</a>
                      </div>
                    ))}
                  </div>
                ) : <div className="muted">No export bundles generated yet.</div>}
              </div>
            </details>
          </div>
        </section>
      ) : (
        <section
          className="project-comparison-workbench"
          aria-label="Model comparison"
        >
          <button
            type="button"
            className="project-information-back comparison-back-to-models workspace-back-button"
            onClick={() => setWorkspaceTab("selection")}
          >
            <span aria-hidden="true">←</span>
            <span>Back to models</span>
          </button>
          <div className="project-comparison-header">
            <div>
              <div className="run-management-eyebrow">Comparison workbench</div>
              <h3>Compare completed models</h3>
              <div className="muted">Compare outcomes, energy outputs, costs, reliability, development effects, regional detail, assumptions, quality, and files.</div>
            </div>
            <div className="project-comparison-actions">
              <div className="project-comparison-count"><b>{selectedRuns.length}</b><span>selected</span></div>
            </div>
          </div>

          <div className="project-compare-run-pills" aria-label="Completed models available for comparison">
            {successfulRuns.length ? successfulRuns.map((run) => {
              const selected = selectedIds.includes(run.run_id);
              return (
                <button
                  key={run.run_id}
                  type="button"
                  className={`project-compare-run-pill ${selected ? "selected" : ""}`}
                  onClick={() => onToggleCompareRun(run.run_id)}
                  aria-pressed={selected}
                >
                  <span>{modelDisplayName(run)}</span>
                  <small>{modelNumberLabel(run)} · {runMetadataLine(run)}</small>
                  <EvidenceBadge
                    status={evidenceFromModel(run, summaries[run.run_id]).status}
                    compact
                  />
                </button>
              );
            }) : <div className="muted" style={{ fontSize: 12 }}>No completed runs are available for comparison yet.</div>}
          </div>

          {selectedRuns.length ? <div className="project-selected-compare-note">Selected comparison set: {selectedRuns.map((run) => modelDisplayName(run)).join(", ")}</div> : null}
          {error ? <div className="warn">{error}</div> : null}
          {loading ? <div className="diagram-note">Loading model outputs and file catalogs...</div> : null}

          <div className="project-comparison-table-panel">
            <div className="comparison-results-heading">
              <div>
                <div className="run-management-eyebrow">Model evidence</div>
                <h4>Comparison results</h4>
              </div>
              {selectedRuns.length >= 2 ? (
                <div className="comparison-results-total">
                  <b>{COMPARISON_OUTPUT_SECTIONS.reduce((total, section) => (
                    total + (section.key === "outputs" ? artifactComparisonRows.length : (comparisonDatasets[section.key] || []).length)
                  ), 0)}</b>
                  <span>comparable outputs</span>
                </div>
              ) : null}
            </div>
            {selectedRuns.length < 2 ? (
              <div className="comparison-empty">
                {successfulRuns.length ? "Select at least two completed models to compare their full output sets." : "Execute and complete at least two models to activate comparison."}
              </div>
            ) : (
              <div className="comparison-workbench-body">
                <div className="comparison-control-bar">
                  <label>
                    <span>Reference model</span>
                    <select value={baselineRunId} onChange={(event) => setBaselineRunId(event.target.value)}>
                      {selectedRuns.map((run) => <option key={run.run_id} value={run.run_id}>{modelDisplayName(run)}</option>)}
                    </select>
                  </label>
                  <div className="comparison-display-control" role="group" aria-label="Comparison value display">
                    {[
                      ["absolute", "Values"],
                      ["change", "Change"],
                      ["both", "Both"],
                    ].map(([value, label]) => (
                      <button
                        key={value}
                        type="button"
                        className={comparisonDisplayMode === value ? "active" : ""}
                        aria-pressed={comparisonDisplayMode === value}
                        onClick={() => setComparisonDisplayMode(value)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="comparison-output-tabs" role="tablist" aria-label="Comparison output families">
                  {COMPARISON_OUTPUT_SECTIONS.map((section, index) => {
                    const count = section.key === "outputs"
                      ? artifactComparisonRows.length
                      : (comparisonDatasets[section.key] || []).length;
                    const active = comparisonSection === section.key;
                    return (
                      <button
                        key={section.key}
                        type="button"
                        role="tab"
                        id={`comparison-output-tab-${section.key}`}
                        aria-selected={active}
                        aria-controls="comparison-output-panel"
                        tabIndex={active ? 0 : -1}
                        className={active ? "active" : ""}
                        onClick={() => setComparisonSection(section.key)}
                        onKeyDown={(event) => handleTablistKeyDown(
                          event,
                          index,
                          COMPARISON_OUTPUT_SECTIONS.length,
                          (nextIndex) => setComparisonSection(COMPARISON_OUTPUT_SECTIONS[nextIndex].key)
                        )}
                      >
                        <span>{section.shortLabel}</span>
                        <small>{count}</small>
                      </button>
                    );
                  })}
                </div>

                <section
                  className="comparison-output-panel"
                  id="comparison-output-panel"
                  role="tabpanel"
                  aria-labelledby={`comparison-output-tab-${activeComparisonDefinition.key}`}
                  tabIndex={0}
                >
                  <div className="comparison-output-panel-heading">
                    <div>
                      <h5>{activeComparisonDefinition.label}</h5>
                      <p>
                        {activeComparisonDefinition.key === "outputs"
                          ? `${artifactComparisonRows.length} persisted file types across the selected models.`
                          : `${activeComparisonRows.length} normalized outputs across the selected models. Missing values remain explicit.`}
                      </p>
                    </div>
                  </div>
                  {activeComparisonDefinition.key === "outputs" ? (
                    <ComparisonArtifactMatrix
                      selectedRuns={selectedRuns}
                      summaries={summaries}
                      artifactCatalogs={artifactCatalogs}
                    />
                  ) : (
                    <ComparisonMatrix
                      rows={activeComparisonRows}
                      selectedRuns={selectedRuns}
                      summaries={summaries}
                      baselineRunId={baselineRunId}
                      displayMode={comparisonDisplayMode}
                    />
                  )}
                </section>
              </div>
            )}
          </div>
        </section>
      )}
    </div>
  );
}

function ArchitectureRunWorkspace({
  architecture,
  runViewMode,
  flowActiveJob = null,
  inputsLocked = false,
  lockReason = "",
  selectedRunId,
  result,
  inputDatasets,
  onUploadDataset,
  onDatasetVersionChange,
  errorMessage,
  statusMessage,
  runManagementPanel,
  projectsOverviewPanel,
  comparePanel,
  scenarioControls,
  resultsPanel,
  scenarioKey = "",
  scenarioSelections = {},
}) {
  const workspaceState = flowActiveJob ? "running" : result ? "complete" : "ready";
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
  const datasetsByNode = useMemo(() => {
    const out = {};
    ((architecture && architecture.boxes) || ARCHITECTURE_BOXES).forEach((box) => {
      const layers = Array.isArray(box.datasetLayers) ? box.datasetLayers : [];
      if (!layers.length) return;
      out[box.id] = layers.flatMap((layer) => datasetGroups.get(layer) || []);
    });
    return out;
  }, [architecture, datasetGroups]);

  return (
    <div className={`architecture-run-workspace ${workspaceState}`}>
      {runViewMode === "projects" ? (
        <>
          {projectsOverviewPanel}
          {errorMessage || statusMessage ? (
            <div className="project-overview-message-stack">
              {errorMessage ? <div className="warn" style={{ marginTop: 0 }}>{errorMessage}</div> : null}
              {statusMessage ? <div className="ok" style={{ marginTop: errorMessage ? 8 : 0 }}>{statusMessage}</div> : null}
            </div>
          ) : null}
        </>
      ) : (
        <>
          <div className={`model-workspace-with-management ${runViewMode === "project" || (runViewMode === "results" && result) ? "no-side-panel" : ""}`}>
            <main className="model-workspace-primary" id="model-workspace-primary">
              {runViewMode === "project" ? (
                comparePanel
              ) : runViewMode === "results" && result ? (
                <div className="results-mode-stack">
                  <main className="results-mode-main">{resultsPanel}</main>
                </div>
              ) : (
                <FlowModelCanvas
                  activeJob={flowActiveJob}
                  result={result}
                  architecture={architecture}
                  scenarioControls={scenarioControls}
                  calliopeDatasets={calliopeDatasets}
                  mrioDatasets={mrioDatasets}
                  datasetsByNode={datasetsByNode}
                  selectedRunId={selectedRunId}
                  inputsLocked={inputsLocked}
                  lockReason={lockReason}
                  onUploadDataset={onUploadDataset}
                  onDatasetVersionChange={onDatasetVersionChange}
                  scenarioKey={scenarioKey}
                  scenarioSelections={scenarioSelections}
                />
              )}
            </main>
            {runViewMode === "project" || (runViewMode === "results" && result) ? null : runManagementPanel}
          </div>
        </>
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

function resetTopLevelScroll() {
  window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  document
    .querySelectorAll(".landing-shell, .methodology-shell, .model-workspace-primary, .architecture-flow-panel")
    .forEach((element) => element.scrollTo({ top: 0, left: 0, behavior: "auto" }));
}

function App() {
  const [session, setSession] = useState(null);
  const [currentUserId, setCurrentUserId] = useState(api.getActiveUserId ? api.getActiveUserId() : "undp_analyst");
  const [apiTarget, setApiTarget] = useState(() => (
    api.getApiTarget
      ? api.getApiTarget()
      : { mode: "local", localApiBase: window.location.origin, backendApiBase: "", apiBase: window.location.origin }
  ));
  const [systemCompatibility, setSystemCompatibility] = useState(null);
  const [projects, setProjects] = useState([]);
  const [activeProjectId, setActiveProjectId] = useState("");
  const [projectRuns, setProjectRuns] = useState([]);
  const [projectReports, setProjectReports] = useState([]);
  const [projectExports, setProjectExports] = useState([]);
  const [compareRunIds, setCompareRunIds] = useState([]);
  const [platformActionLoading, setPlatformActionLoading] = useState(false);
  const [draftSaving, setDraftSaving] = useState(false);
  const [scenarioCatalog, setScenarioCatalog] = useState(null);
  const [architectureCatalog, setArchitectureCatalog] = useState(() => normalizeArchitectureCatalog(null));
  const [selectedArchitectureId, setSelectedArchitectureId] = useState(DEFAULT_MODEL_ARCHITECTURE_ID);
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
  const [customRunName, setCustomRunName] = useState("");
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
  const [runViewMode, setRunViewMode] = useState("projects");
  const [methodologyOpen, setMethodologyOpen] = useState(() => window.location.hash === "#/methodology");
  const [landingOpen, setLandingOpen] = useState(() => window.location.hash !== "#/methodology");
  const [newModelModalOpen, setNewModelModalOpen] = useState(false);
  const locationMapCacheRef = useRef(new Map());
  const runSpatialTechCacheRef = useRef(new Map());
  const availableUsers = (session && session.available_users) || [];
  const currentUser = (session && session.user) || {};
  const isAdminView = Boolean(currentUser && currentUser.is_admin);
  const navigationPageKey = methodologyOpen
    ? "methodology"
    : landingOpen
      ? "landing"
      : runViewMode === "projects"
        ? "projects"
        : `${runViewMode}:${activeProjectId}:${selectedJobId}`;

  const selectedScenario = useMemo(
    () => (scenarios || []).find((s) => s.key === scenarioKey),
    [scenarios, scenarioKey]
  );

  useEffect(() => {
    function handleHashChange() {
      const nextMethodologyOpen = window.location.hash === "#/methodology";
      setMethodologyOpen(nextMethodologyOpen);
      if (nextMethodologyOpen) setLandingOpen(false);
    }
    handleHashChange();
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  useEffect(() => {
    const frameId = window.requestAnimationFrame(() => {
      resetTopLevelScroll();
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [navigationPageKey]);

  useEffect(() => {
    if (!statusMessage) return undefined;
    const timer = window.setTimeout(() => setStatusMessage(""), 7000);
    return () => window.clearTimeout(timer);
  }, [statusMessage]);

  const defaultRunName = useMemo(() => {
    const baseName = selectedScenario && selectedScenario.title
      ? selectedScenario.title
      : scenarioKey || "EDIM run";
    return `${baseName} ${targetYear || ""}`.trim();
  }, [selectedScenario, scenarioKey, targetYear]);
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
  const selectedArchitecture = useMemo(
    () => architectureById(architectureCatalog, selectedArchitectureId),
    [architectureCatalog, selectedArchitectureId]
  );
  const selectedArchitectureRequiresMrio = architectureIncludesDevelopment(selectedArchitecture);
  const effectiveMrioScenarioId = selectedArchitectureRequiresMrio ? mrioScenarioId : (mrioScenarioId || "S1");

  function clearBackendBoundState() {
    setProjects([]);
    setActiveProjectId("");
    setProjectRuns([]);
    setProjectReports([]);
    setProjectExports([]);
    setCompareRunIds([]);
    setInputDatasets([]);
    setJobs([]);
    setActiveJob(null);
    setSelectedJobId("");
    setResult(null);
    setSelectedRunId("");
    setIntegratedPayload(null);
    setRunning(false);
    setQueueSubmitting(false);
    setEnvironmentSetup(null);
    setLocationMapData(null);
    setLocationMapError("");
    setRunSpatialTechData(null);
    setRunSpatialTechError("");
    setSpatialFilter(null);
    locationMapCacheRef.current.clear();
    runSpatialTechCacheRef.current.clear();
    setRunViewMode("projects");
  }

  function applyScenarioCatalog(catalog) {
    const rows = rowsFromScenarioChannel(catalog, "scenario.energy_scenario_key", "key");
    const targetRows = rowsFromScenarioChannel(catalog, "scenario.target_scenario_id", "scenario_id");
    const shockRows = rowsFromScenarioChannel(catalog, "scenario.mrio_shock_mapping_id", "mapping_id");
    const years = yearsFromScenarioChannel(catalog);
    setScenarioCatalog(catalog);
    setScenarios(rows);
    setTargetScenarios(targetRows);
    setMrioShockMappings(shockRows);
    setTargetYears(years.length ? years : [2030, 2050]);
    setEnergyModelEngine((prev) => {
      const available = new Set(
        energyModelCatalogOptions(catalog)
          .filter((row) => !row.disabled)
          .map((row) => String(row.value || "").toLowerCase())
      );
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
    return { rows, targetRows, shockRows, years };
  }

  async function refreshModelArchitectures() {
    try {
      const runtimeCatalog = await api.fetchModelRuntimes();
      const catalog = normalizeArchitectureCatalog(
        (runtimeCatalog && runtimeCatalog.architecture_catalog) ||
        {
          schemaVersion: "edim_model_architecture_catalog",
          defaultArchitectureId: DEFAULT_MODEL_ARCHITECTURE_ID,
          architectures: (runtimeCatalog && runtimeCatalog.model_architectures) || [],
        }
      );
      setArchitectureCatalog(catalog);
      setSelectedArchitectureId((prev) => {
        if (prev && catalog.architectures.some((row) => row.id === prev)) return prev;
        return catalog.defaultArchitectureId;
      });
      if (runtimeCatalog && runtimeCatalog.scenario_catalog) {
        applyScenarioCatalog(runtimeCatalog.scenario_catalog);
      }
      return catalog;
    } catch (err) {
      try {
        const bundledCatalog = normalizeArchitectureCatalog(await loadBundledArchitectureCatalog());
        setArchitectureCatalog(bundledCatalog);
        setSelectedArchitectureId((prev) => {
          if (prev && bundledCatalog.architectures.some((row) => row.id === prev)) return prev;
          return bundledCatalog.defaultArchitectureId;
        });
        setErrorMessage("");
        return bundledCatalog;
      } catch (bundleErr) {
        setErrorMessage(
          `${toErrorMessage(err, "Failed to load model architecture catalog from backend runtime catalog")} ` +
          `${toErrorMessage(bundleErr, "Bundled model architecture catalog is also unavailable")}`
        );
      }
      return architectureCatalog;
    }
  }

  async function refreshScenarios() {
    try {
      const catalog = await api.fetchScenarioCatalog();
      applyScenarioCatalog(catalog);
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to load scenarios"));
    }
  }

  async function refreshSession() {
    try {
      const payload = await api.fetchSession();
      setSession(payload);
      if (payload && payload.user && payload.user.user_id) {
        setCurrentUserId(payload.user.user_id);
        if (api.setActiveUserId) api.setActiveUserId(payload.user.user_id);
      }
      return payload;
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to load user session"));
      return null;
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

  async function refreshProjects() {
    try {
      const rows = typeof api.fetchProjects === "function" ? await api.fetchProjects() : [];
      setProjects(rows);
      setActiveProjectId((prev) => {
        if (prev && rows.some((project) => project.project_id === prev)) return prev;
        const activeRows = rows.filter((project) => String(project.status || "active").toLowerCase() !== "archived");
        return ((activeRows[0] || rows[0]) && (activeRows[0] || rows[0]).project_id) || "";
      });
      return rows;
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to load projects"));
      return [];
    }
  }

  async function refreshProjectRuns(projectId) {
    // Project run records are the durable history source. The active execution
    // poller can enrich one row while running, but tabs/compare/reporting should
    // come from this project-owned list rather than ephemeral queue memory.
    const id = projectId || activeProjectId;
    if (!id || typeof api.fetchProjectRuns !== "function") {
      setProjectRuns([]);
      setJobs([]);
      return [];
    }
    try {
      const rows = await api.fetchProjectRuns(id, { includeDrafts: true, limit: 100 });
      const displayRows = rows.map(projectRunToDisplayRun);
      const activeDisplayJob = displayRows.find((j) => isActiveStatus(j.status)) || null;
      setProjectRuns(displayRows);
      setJobs(displayRows);
      setRunning(Boolean(displayRows.find((j) => normalizeStatus(j.status) === "running")));
      setActiveJob((prev) => activeDisplayJob || (prev && isActiveStatus(prev.status) ? prev : null));
      setCompareRunIds((prev) => {
        const valid = new Set(succeededProjectRuns(displayRows).map((run) => run.run_id));
        return prev.filter((runId) => valid.has(runId));
      });
      const selected = selectedJobId ? displayRows.find((run) => runExecutionId(run) === selectedJobId || run.run_id === selectedJobId) : null;
      if (!selected && displayRows[0]) {
        setSelectedJobId(runExecutionId(displayRows[0]));
      }
      return displayRows;
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to load project runs"));
      setProjectRuns([]);
      setJobs([]);
      return [];
    }
  }

  async function refreshProjectOutputs(projectId) {
    const id = projectId || activeProjectId;
    if (!id) {
      setProjectReports([]);
      setProjectExports([]);
      return { reports: [], exports: [] };
    }
    try {
      const [reports, exports] = await Promise.all([
        typeof api.fetchProjectReports === "function" ? api.fetchProjectReports(id) : [],
        typeof api.fetchProjectExports === "function" ? api.fetchProjectExports(id) : [],
      ]);
      setProjectReports(reports);
      setProjectExports(exports);
      return { reports, exports };
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to load project reports/exports"));
      return { reports: [], exports: [] };
    }
  }

  async function refreshProjectWorkspace(projectId) {
    const id = projectId || activeProjectId;
    const [runs] = await Promise.all([
      refreshProjectRuns(id),
      refreshProjectOutputs(id),
      refreshProjects(),
    ]);
    return runs;
  }

  async function ensureActiveProject() {
    const current = activeProjectId && projects.find((project) => project.project_id === activeProjectId);
    if (current) return current;
    const rows = await refreshProjects();
    if (rows[0]) return rows[0];
    const created = await api.createProject({
      title: "Default EDIM project",
      geography: "",
      project_type: "energy-development",
      model_architecture_id: "energy-development",
      scenario_label: "Integrated EDIM runs",
      notes: "Auto-created local project for canonical project-owned run submission.",
    });
    setProjects([created]);
    setActiveProjectId(created.project_id);
    return created;
  }

  async function refreshEnvironmentSetup(nextScenario, nextMrioScenarioId, nextTargetYear, nextRunProfile, nextProjectId) {
    const scenario = nextScenario || scenarioKey;
    const mrioScenario = nextMrioScenarioId || mrioScenarioId;
    const year = nextTargetYear || targetYear;
    const profile = nextRunProfile || runProfile;
    setEnvironmentSetupLoading(true);
    try {
      const payload = await api.fetchEnvironmentSetup(
        scenario,
        mrioScenario,
        year,
        profile,
        nextProjectId || activeProjectId || "default",
        {
          model_architecture_id: selectedArchitecture.id,
          energy_model_engine: energyModelEngine,
          levers,
        }
      );
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
    if (activeProjectId) {
      const displayRows = await refreshProjectRuns(activeProjectId);
      const activeDisplayJob = displayRows.find((j) => isActiveStatus(j.status)) || null;
      const selectedJob =
        (selectedJobId && displayRows.find((j) => runExecutionId(j) === selectedJobId || j.run_id === selectedJobId)) ||
        activeDisplayJob ||
        displayRows[0] ||
        null;
      setRunning(Boolean(displayRows.find((j) => normalizeStatus(j.status) === "running")));
      setActiveJob((prev) => activeDisplayJob || (prev && isActiveStatus(prev.status) ? prev : null));
      if (selectedJob) setSelectedJobId(runExecutionId(selectedJob));
      return displayRows;
    }
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
        (selectedJobId && rows.find((j) => runExecutionId(j) === selectedJobId || j.run_id === selectedJobId)) ||
        runningJob ||
        rows[0] ||
        null;
      if (selectedJob) {
        setSelectedJobId(runExecutionId(selectedJob));
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

  async function reloadPlatformShell(successMessage = "") {
    clearBackendBoundState();
    setErrorMessage("");
    setStatusMessage("");
    await refreshSession();
    const [initialProjects] = await Promise.all([
      refreshProjects(),
      refreshInputDatasets(),
      refreshModelArchitectures(),
    ]);
    const initialProjectId = (initialProjects && initialProjects[0] && initialProjects[0].project_id) || "";
    if (initialProjects && initialProjects[0] && initialProjects[0].model_architecture_id) {
      setSelectedArchitectureId(initialProjects[0].model_architecture_id);
    }
    if (initialProjectId) {
      await refreshProjectWorkspace(initialProjectId);
    } else {
      await refreshJobs();
    }
    setRunViewMode("projects");
    if (successMessage) setStatusMessage(successMessage);
  }

  async function probeSystemCompatibility() {
    const target = api.getApiTarget ? api.getApiTarget() : apiTarget;
    setSystemCompatibility({
      status: "checking",
      mode: target.mode,
      apiBase: target.apiBase,
      message: "Checking API contract...",
    });
    try {
      const manifest = await api.fetchSystemManifest();
      const compatibility = evaluateSystemManifest(manifest, target);
      setSystemCompatibility(compatibility);
      return compatibility;
    } catch (err) {
      const compatibility = {
        status: "error",
        mode: target.mode,
        apiBase: target.apiBase,
        message: toErrorMessage(err, "Contract error: system manifest is unavailable"),
        missingEndpoints: [],
        diagnostics: [],
        checkedAt: new Date().toISOString(),
      };
      setSystemCompatibility(compatibility);
      return compatibility;
    }
  }

  async function applyApiTarget(nextMode) {
    if (!api.setApiTarget) return;
    const mode = String(nextMode || "local") === "backend" ? "backend" : "local";
    const currentTarget = api.getApiTarget ? api.getApiTarget() : apiTarget;
    if (mode === "backend" && !currentTarget.hasBackendApiBase) {
      setApiTarget(currentTarget);
      setErrorMessage("Backend mode is unavailable because EDIM_BACKEND_API_BASE is not configured.");
      return;
    }
    const next = api.setApiTarget({ mode });
    setApiTarget(next);
    clearBackendBoundState();
    setErrorMessage("");
    setStatusMessage("");
    setPlatformActionLoading(true);
    try {
      const compatibility = await probeSystemCompatibility();
      if (mode === "backend" && compatibility.status === "error") {
        const restored = api.setApiTarget({ mode: currentTarget.mode || "local" });
        setApiTarget(restored);
        setErrorMessage(compatibility.message || "Backend API contract check failed.");
        return;
      }
      await reloadPlatformShell(
        mode === "backend"
          ? `Connected to backend API: ${next.apiBase}${compatibility.status === "warning" ? " (contract warning)" : ""}`
          : `Connected to local API: ${next.apiBase}`
      );
    } catch (err) {
      setErrorMessage(toErrorMessage(err, `Failed to connect to ${mode === "backend" ? "backend" : "local"} API`));
    } finally {
      setApiTarget(api.getApiTarget ? api.getApiTarget() : next);
      setPlatformActionLoading(false);
    }
  }

  async function handleApiTargetModeChange(nextMode) {
    await applyApiTarget(nextMode);
  }

  async function hydrateIntegratedForRun(runId, summaryPayload) {
    if (summaryPayload && Object.keys(summaryPayload).length > 0) {
      setIntegratedPayload(summaryPayload);
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
      if (job.request && job.request.model_architecture_id) setSelectedArchitectureId(job.request.model_architecture_id);
      const nextResult = { artifacts: job.artifacts, summary: job.summary };
      setResult(nextResult);
      setSelectedRunId(job.artifacts.run_id);
      setSelectedJobId(runExecutionId(job));
      setStatusMessage(`${runLabel(job)} completed successfully.`);
      setErrorMessage("");
      setRunViewMode("results");
      await hydrateIntegratedForRun(job.artifacts.run_id, job.summary.integrated_results || null);
    } else if (status === "failed") {
      setSelectedJobId(runExecutionId(job));
      setErrorMessage(job.error || job.message || "Execution failed.");
    } else if (status === "cancelled") {
      setSelectedJobId(runExecutionId(job));
      setErrorMessage("Execution was cancelled.");
    } else if (status === "draft") {
      setSelectedJobId(job.run_id || "");
      setSelectedRunId("");
      setResult(null);
      setIntegratedPayload(null);
      setStatusMessage("Execution cancelled; draft restored.");
      setErrorMessage("");
      setRunViewMode("setup");
    }

    setActiveJob(null);
    await refreshProjectWorkspace(activeProjectId || (job.request && job.request.project_id) || "default");
  }

  useEffect(() => {
    let cancelled = false;
    async function boot() {
      const target = api.getApiTarget ? api.getApiTarget() : apiTarget;
      setApiTarget(target);
      if (target.mode === "backend" && !target.backendApiBase) {
        clearBackendBoundState();
        setErrorMessage("Backend mode is unavailable because EDIM_BACKEND_API_BASE is not configured.");
        return;
      }
      await probeSystemCompatibility();
      await reloadPlatformShell("");
      if (cancelled) return;
    }
    boot();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleUserChange(userId) {
    if (api.setActiveUserId) api.setActiveUserId(userId);
    setCurrentUserId(userId);
    setJobs([]);
    setProjects([]);
    setProjectRuns([]);
    setProjectReports([]);
    setProjectExports([]);
    setCompareRunIds([]);
    setActiveProjectId("");
    setActiveJob(null);
    setSelectedJobId("");
    setResult(null);
    setSelectedRunId("");
    setIntegratedPayload(null);
    setStatusMessage("");
    setErrorMessage("");
    setRunViewMode("projects");
    await refreshSession();
    let refreshedProjects = await refreshProjects();
    if (!refreshedProjects.length && typeof api.createProject === "function") {
      const created = await api.createProject({
        title: "Default EDIM project",
        geography: "",
        project_type: "energy-development",
        model_architecture_id: "energy-development",
        scenario_label: "Integrated EDIM runs",
        notes: "Auto-created local project for canonical project-owned run submission.",
      });
      refreshedProjects = [created];
      setProjects(refreshedProjects);
      setActiveProjectId(created.project_id);
    }
    const nextProjectId = (refreshedProjects[0] && refreshedProjects[0].project_id) || "";
    if (refreshedProjects[0] && refreshedProjects[0].model_architecture_id) {
      setSelectedArchitectureId(refreshedProjects[0].model_architecture_id);
    }
    await Promise.all([
      refreshInputDatasets(),
      nextProjectId ? refreshProjectWorkspace(nextProjectId) : refreshJobs(),
      refreshEnvironmentSetup(scenarioKey, effectiveMrioScenarioId, targetYear, runProfile, nextProjectId || "default"),
    ]);
    setRunViewMode("projects");
  }

  async function handleProjectChange(projectId, nextMode = "project") {
    if (!projectId) return;
    const project = (projects || []).find((row) => row.project_id === projectId) || null;
    const architectureId = String((project && project.model_architecture_id) || "").trim();
    if (architectureId) setSelectedArchitectureId(architectureId);
    if (projectId === activeProjectId) {
      if (nextMode === "project") {
        setSelectedJobId("");
        setSelectedRunId("");
        setResult(null);
        setIntegratedPayload(null);
      }
      if (nextMode) setRunViewMode(nextMode);
      return;
    }
    setActiveProjectId(projectId);
    setActiveJob(null);
    setSelectedJobId("");
    setResult(null);
    setSelectedRunId("");
    setIntegratedPayload(null);
    setCompareRunIds([]);
    setStatusMessage(`Selected project ${project && project.title ? project.title : projectId}.`);
    setErrorMessage("");
    await Promise.all([
      refreshProjectWorkspace(projectId),
      refreshEnvironmentSetup(scenarioKey, effectiveMrioScenarioId, targetYear, runProfile, projectId),
    ]);
    if (nextMode === "project") {
      setSelectedJobId("");
      setSelectedRunId("");
      setResult(null);
      setIntegratedPayload(null);
    }
    if (nextMode) setRunViewMode(nextMode);
  }

  async function handleCreateProject(projectPayload = null) {
    setPlatformActionLoading(true);
    setErrorMessage("");
    try {
      const architectureId = String((projectPayload && projectPayload.model_architecture_id) || "energy-development");
      const created = await api.createProject({
        title: `EDIM project ${(projects || []).length + 1}`,
        geography: "Africa",
        project_type: projectTypeForArchitecture(architectureId),
        model_architecture_id: architectureId,
        scenario_label: architectureId === "energy-only" ? "Energy model workspace" : "Energy-Development model workspace",
        notes: "Created from the modeling dashboard.",
        ...(projectPayload || {}),
      });
      setProjects((prev) => [created, ...(prev || [])]);
      if (created.model_architecture_id) setSelectedArchitectureId(created.model_architecture_id);
      await handleProjectChange(created.project_id);
      setStatusMessage(`Created project ${created.title || created.project_id}.`);
      return created;
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to create project"));
      return null;
    } finally {
      setPlatformActionLoading(false);
    }
  }

  async function handleRenameProject(projectId, title) {
    if (!projectId || !title) return;
    setPlatformActionLoading(true);
    setErrorMessage("");
    try {
      const updated = await api.updateProject(projectId, { title });
      setProjects((prev) => (prev || []).map((project) => project.project_id === projectId ? updated : project));
      setStatusMessage(`Renamed project to ${updated.title || projectId}.`);
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to rename project"));
    } finally {
      setPlatformActionLoading(false);
    }
  }

  async function handleArchiveProject(projectId) {
    if (!projectId) return;
    const confirmed = window.confirm("Archive this project? It will move out of the active project list but can be restored from the project archive.");
    if (!confirmed) return;
    setPlatformActionLoading(true);
    setErrorMessage("");
    try {
      const updated = await api.updateProject(projectId, { status: "archived" });
      const nextProjects = (projects || []).map((project) => project.project_id === projectId ? updated : project);
      setProjects(nextProjects);
      if (activeProjectId === projectId) {
        const nextActive = nextProjects.find((row) => String(row.status || "active").toLowerCase() !== "archived");
        setActiveProjectId(nextActive ? nextActive.project_id : "");
        setRunViewMode("projects");
      }
      setStatusMessage(`Archived project ${updated.title || projectId}.`);
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to archive project"));
    } finally {
      setPlatformActionLoading(false);
    }
  }

  async function handleRestoreProject(projectId) {
    if (!projectId) return;
    setPlatformActionLoading(true);
    setErrorMessage("");
    try {
      const updated = await api.updateProject(projectId, { status: "active" });
      setProjects((prev) => (prev || []).map((project) => project.project_id === projectId ? updated : project));
      setStatusMessage(`Restored project ${updated.title || projectId}.`);
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to restore project"));
    } finally {
      setPlatformActionLoading(false);
    }
  }

  async function handleDeleteProject(projectId) {
    if (!projectId) return;
    const project = (projects || []).find((row) => row.project_id === projectId);
    const confirmed = window.confirm(`Delete project "${project && project.title ? project.title : projectId}"? This removes its local runs, reports, exports, and project metadata.`);
    if (!confirmed) return;
    setPlatformActionLoading(true);
    setErrorMessage("");
    try {
      await api.deleteProject(projectId, { deleteFiles: true });
      const rows = await refreshProjects();
      if (activeProjectId === projectId) {
        setActiveProjectId("");
        setProjectRuns([]);
        setProjectReports([]);
        setProjectExports([]);
        setCompareRunIds([]);
        setActiveJob(null);
        setSelectedJobId("");
        setResult(null);
        setSelectedRunId("");
        setIntegratedPayload(null);
        const nextProject = rows.find((row) => String(row.status || "active").toLowerCase() !== "archived") || rows[0] || null;
        if (nextProject) {
          setActiveProjectId(nextProject.project_id);
        }
      }
      setRunViewMode("projects");
      setStatusMessage("Deleted project.");
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to delete project"));
    } finally {
      setPlatformActionLoading(false);
    }
  }

  useEffect(() => {
    if (!scenarioKey) return;
    let cancelled = false;
    async function loadEnvironmentSetup() {
      try {
        const payload = await api.fetchEnvironmentSetup(
          scenarioKey,
          effectiveMrioScenarioId,
          targetYear,
          runProfile,
          activeProjectId || "default",
          {
            model_architecture_id: selectedArchitecture.id,
            energy_model_engine: energyModelEngine,
            levers,
          }
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
  }, [scenarioKey, effectiveMrioScenarioId, targetYear, runProfile, activeProjectId, selectedArchitecture.id, energyModelEngine, levers]);

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
          api.fetchArtifactText(runId, "investment_shocks_csv"),
          api.fetchArtifactText(runId, "operating_shocks_csv"),
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
    const executionId = runExecutionId(activeJob);
    if (!executionId) return;

    let stopped = false;
    const poll = async () => {
      try {
        const latest = await api.fetchJob(executionId);
        if (stopped) return;
        setActiveJob(latest);
        setRunning(isActiveStatus(latest.status));
        if (isTerminalStatus(latest.status) || isResetStatus(latest.status)) await finalizeJob(latest);
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
  }, [activeJob && runExecutionId(activeJob)]);

  async function onRun() {
    if (selectedRunInputsLocked) {
      setErrorMessage("This selected run is locked. Create an editable draft from the locked configuration before running changes.");
      return;
    }
    const editableDraftRunId =
      selectedJob && normalizeStatus(selectedJob.status) === "draft" && selectedJob.run_id
        ? selectedJob.run_id
        : "";
    if (!editableDraftRunId) {
      setErrorMessage("Create a new model draft, or select an existing draft, before running the model.");
      return;
    }
    if (!scenarioKey || (selectedArchitectureRequiresMrio && !mrioScenarioId) || queueSubmitting) return;

    setErrorMessage("");
    setStatusMessage("");
    setQueueSubmitting(true);

    try {
      const project = await ensureActiveProject();
      const projectId = project && project.project_id ? project.project_id : "default";
      const currentEnvironmentSetup = await refreshEnvironmentSetup(
        scenarioKey,
        effectiveMrioScenarioId,
        targetYear,
        runProfile,
        projectId
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
            : "Execution readiness checks need attention. Review the highlighted items and try again.");
        setErrorMessage(message);
        return;
      }

      const resolvedRunName = (customRunName || "").trim() || defaultRunName;
      const requestPayload = currentRunRequestPayload(projectId, resolvedRunName);
      await api.updateRunDraft(projectId, editableDraftRunId, {
        request: requestPayload,
        run_name: resolvedRunName,
      });
      const job = await api.submitProjectRun(projectId, editableDraftRunId);
      setActiveJob(job);
      setSelectedJobId(runExecutionId(job));
      setRunning(true);
      setStatusMessage(`Queued run "${resolvedRunName}".`);
      await refreshProjectWorkspace(projectId);
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to submit run"));
    } finally {
      setQueueSubmitting(false);
    }
  }

  async function onSaveSelectedDraft() {
    if (!selectedEditableDraft || !selectedEditableDraft.run_id) {
      setErrorMessage("Select an editable draft before saving.");
      return;
    }
    const projectId =
      activeProjectId ||
      selectedEditableDraft.project_id ||
      (selectedEditableDraft.request && selectedEditableDraft.request.project_id) ||
      "";
    if (!projectId) {
      setErrorMessage("Select a project before saving this draft.");
      return;
    }

    setDraftSaving(true);
    setErrorMessage("");
    setStatusMessage("");
    try {
      const resolvedRunName = (customRunName || "").trim() || defaultRunName;
      const requestPayload = currentRunRequestPayload(projectId, resolvedRunName);
      const savedDraft = await api.updateRunDraft(projectId, selectedEditableDraft.run_id, {
        request: requestPayload,
        run_name: resolvedRunName,
      });
      await refreshProjectWorkspace(projectId);
      setSelectedJobId(runExecutionId(savedDraft));
      setStatusMessage("Draft saved.");
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to save draft"));
    } finally {
      setDraftSaving(false);
    }
  }

  async function onRenameModel(targetJob, nextName) {
    const cleanName = String(nextName || "").trim();
    if (!cleanName || !targetJob || !targetJob.run_id) return;
    const projectId =
      activeProjectId ||
      targetJob.project_id ||
      (targetJob.request && targetJob.request.project_id) ||
      "";
    if (!projectId) {
      setErrorMessage("Select a project before renaming this model.");
      throw new Error("Project is required to rename a model.");
    }

    setErrorMessage("");
    try {
      const updated = await api.updateRunDraft(projectId, targetJob.run_id, { run_name: cleanName });
      if (runExecutionId(targetJob) === selectedJobId) setCustomRunName(cleanName);
      setProjectRuns((rows) =>
        rows.map((row) => row.run_id === updated.run_id ? { ...row, ...updated } : row)
      );
      setJobs((rows) =>
        rows.map((row) => row.run_id === updated.run_id ? { ...row, ...updated } : row)
      );
      if (activeJob && activeJob.run_id === updated.run_id) {
        setActiveJob((current) => ({ ...(current || {}), ...updated }));
      }
      await refreshProjectWorkspace(projectId);
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to rename model"));
      throw err;
    }
  }

  async function onCancelActiveJob() {
    if (!activeJob) return;
    try {
      const updated = await api.cancelJob(runExecutionId(activeJob));
      if (isResetStatus(updated.status)) {
        setActiveJob(null);
        setRunning(false);
        setSelectedJobId(updated.run_id || "");
        setSelectedRunId("");
        setResult(null);
        setIntegratedPayload(null);
        setStatusMessage(updated.message || "Execution cancelled; draft restored.");
        setErrorMessage("");
      } else {
        setActiveJob(updated);
        setStatusMessage(updated.message || `Cancellation requested for execution ${runExecutionId(updated)}.`);
        if (isTerminalStatus(updated.status)) await finalizeJob(updated);
      }
      await refreshProjectWorkspace(activeProjectId || (updated.request && updated.request.project_id) || "default");
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to cancel run"));
    }
  }

  async function onUploadDataset(datasetId, file) {
    if (!datasetId || !file) return;
    if (selectedRunInputsLocked) {
      setErrorMessage("Inputs are locked for the selected model. Duplicate the model before changing datasets.");
      return;
    }
    setErrorMessage("");
    setStatusMessage(`Uploading ${file.name}...`);
    try {
      await api.uploadInputDataset(datasetId, file);
      await onDatasetVersionChange();
      setStatusMessage(`Updated input dataset ${datasetId}. Re-run validation before starting an execution.`);
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to upload input dataset"));
      setStatusMessage("");
    }
  }

  async function onDatasetVersionChange() {
    await Promise.all([
      refreshInputDatasets(),
      refreshEnvironmentSetup(scenarioKey, effectiveMrioScenarioId, targetYear, runProfile, activeProjectId || "default"),
    ]);
  }

  function onToggleCompareRun(runId) {
    if (!runId) return;
    setCompareRunIds((prev) => {
      if (prev.includes(runId)) return prev.filter((id) => id !== runId);
      return [...prev, runId];
    });
  }

  async function onCreateProjectReport() {
    if (!activeProjectId) return;
    const runIds = compareRunIds.length ? compareRunIds : succeededProjectRuns(projectRuns).map((run) => run.run_id);
    const selectedModels = projectRuns.filter((run) => runIds.includes(run.run_id));
    const containsExploratoryEvidence = selectedModels.some(
      (run) => normalizeEvidenceStatus(run && run.evidence_status) === "exploratory_only"
    );
    if (containsExploratoryEvidence) {
      const acknowledged = window.confirm(
        "One or more selected models are marked Exploratory only. The report will carry this limitation and must not be treated as policy-grade evidence. Generate it anyway?"
      );
      if (!acknowledged) return;
    }
    setPlatformActionLoading(true);
    setErrorMessage("");
    try {
      await api.createProjectReport(activeProjectId, {
        run_ids: runIds,
        report_type: compareRunIds.length > 1 ? "comparison_summary" : "project_summary",
        options: {
          source: "dashboard",
          selected_compare_run_ids: compareRunIds,
          acknowledge_exploratory: containsExploratoryEvidence,
        },
      });
      await refreshProjectOutputs(activeProjectId);
      setStatusMessage("Generated project report.");
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to generate project report"));
    } finally {
      setPlatformActionLoading(false);
    }
  }

  function downloadProjectExport(projectId, exportId) {
    if (!projectId || !exportId) return;
    const anchor = document.createElement("a");
    anchor.href = api.projectExportDownloadUrl(projectId, exportId);
    anchor.download = "";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  }

  async function onDownloadProjectFiles(projectId) {
    const targetProjectId = projectId || activeProjectId;
    if (!targetProjectId) return;
    setPlatformActionLoading(true);
    setErrorMessage("");
    try {
      const bundle = await api.createProjectExport(targetProjectId, {
        run_ids: [],
        include_reports: true,
      });
      if (targetProjectId === activeProjectId) await refreshProjectOutputs(targetProjectId);
      setStatusMessage("Prepared project files export.");
      downloadProjectExport(targetProjectId, bundle.export_id);
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to download project files"));
    } finally {
      setPlatformActionLoading(false);
    }
  }

  async function onCreateRunExport(runId) {
    if (!runId) return;
    setPlatformActionLoading(true);
    setErrorMessage("");
    try {
      const bundle = await api.createRunExport(runId);
      await refreshProjectOutputs(activeProjectId);
      setStatusMessage("Created model export.");
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to create model export"));
    } finally {
      setPlatformActionLoading(false);
    }
  }

  function baseRunRequestPayload(projectId, runName = "") {
    const architectureId = String(
      (activeProject && activeProject.model_architecture_id) ||
        selectedArchitecture.id ||
        DEFAULT_MODEL_ARCHITECTURE_ID
    );
    const defaultScenarioKey =
      (scenarioCatalog && scenarioCatalog.defaults && scenarioCatalog.defaults.energy_scenario_key) ||
      ((scenarios || [])[0] && (scenarios || [])[0].key) ||
      scenarioKey;
    const defaultMrioScenarioId =
      (scenarioCatalog && scenarioCatalog.defaults && scenarioCatalog.defaults.target_scenario_id) ||
      ((targetScenarios || [])[0] && (targetScenarios || [])[0].scenario_id) ||
      effectiveMrioScenarioId;
    const defaultYear = Number(
      (scenarioCatalog && scenarioCatalog.defaults && scenarioCatalog.defaults.target_year) ||
        ((targetYears || [])[0]) ||
        targetYear ||
        2030
    );
    const defaultEngine =
      (scenarioCatalog && scenarioCatalog.defaults && scenarioCatalog.defaults.energy_model_engine) ||
      "calliope";
    const defaultTargetScenarioId = architectureIncludesDevelopment(architectureById(architectureCatalog, architectureId))
      ? defaultMrioScenarioId
      : (defaultMrioScenarioId || "S1");
    return {
      run_name: String(runName || "").trim() || `Base model ${defaultYear}`,
      model_architecture_id: architectureId,
      energy_model_engine: defaultEngine,
      scenario: {
        energy_scenario_key: defaultScenarioKey,
        target_scenario_id: defaultTargetScenarioId,
        target_year: defaultYear,
      },
      run_profile: "dev",
      levers: { ...DEFAULT_LEVERS },
    };
  }

  function currentRunRequestPayload(projectId, runName = "") {
    const resolvedRunName = String(runName || "").trim() || defaultRunName;
    return {
      run_name: resolvedRunName,
      model_architecture_id: selectedArchitecture.id,
      energy_model_engine: energyModelEngine,
      scenario: {
        energy_scenario_key: scenarioKey,
        target_scenario_id: effectiveMrioScenarioId,
        target_year: Number(targetYear),
      },
      run_profile: runProfile,
      levers,
    };
  }

  function applyRunRequestToControls(request) {
    const payload = runConfigurationPayload(request);
    if (payload.model_architecture_id) setSelectedArchitectureId(String(payload.model_architecture_id));
    if (payload.energy_model_engine) setEnergyModelEngine(String(payload.energy_model_engine));
    if (payload.energy_scenario_key) setScenarioKey(String(payload.energy_scenario_key));
    if (payload.mrio_scenario_id) setMrioScenarioId(String(payload.mrio_scenario_id));
    if (payload.target_year) setTargetYear(Number(payload.target_year));
    if (payload.run_profile) setRunProfile(String(payload.run_profile));
    if (payload.levers && typeof payload.levers === "object") {
      setLevers({ ...DEFAULT_LEVERS, ...payload.levers });
    }
    setCustomRunName(String(payload.run_name || ""));
  }

  async function onDuplicateSelectedConfiguration() {
    const source = selectedJob || activeJob;
    const sourceRunId = source && source.run_id;
    const projectId = activeProjectId || (source && source.request && source.request.project_id) || "";
    if (!sourceRunId || !projectId) {
      setErrorMessage("Select a model before duplicating its configuration.");
      return;
    }
    setPlatformActionLoading(true);
    setErrorMessage("");
    try {
      const draft = await api.duplicateProjectRun(projectId, sourceRunId);
      applyRunRequestToControls(draft.request || {});
      setResult(null);
      setSelectedRunId("");
      setIntegratedPayload(null);
      setSelectedJobId(runExecutionId(draft));
      setRunViewMode("setup");
      await refreshProjectWorkspace(projectId);
      setSelectedJobId(runExecutionId(draft));
      setStatusMessage(`Duplicated configuration as draft "${runLabel(draft)}".`);
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to duplicate configuration"));
    } finally {
      setPlatformActionLoading(false);
    }
  }

  async function onDeleteSelectedRun() {
    const source = selectedJob || activeJob;
    const sourceRunId = source && source.run_id;
    const projectId = activeProjectId || (source && source.request && source.request.project_id) || "";
    const status = normalizeStatus(source && source.status);
    if (!sourceRunId || !projectId) {
      setErrorMessage("Select a model before deleting it.");
      return;
    }
    if (status === "queued" || status === "running") {
      setErrorMessage("Cancel the active execution before deleting this model.");
      return;
    }
    const confirmed = window.confirm(`Delete ${runLabel(source)}? This removes the run record and generated run files.`);
    if (!confirmed) return;
    setPlatformActionLoading(true);
    setErrorMessage("");
    try {
      await api.deleteProjectRun(projectId, sourceRunId, { deleteFiles: true });
      setActiveJob((prev) => (prev && runExecutionId(prev) === runExecutionId(source) ? null : prev));
      setRunning(false);
      setSelectedJobId("");
      setSelectedRunId("");
      setResult(null);
      setIntegratedPayload(null);
      setRunViewMode("project");
      await refreshProjectWorkspace(projectId);
      await refreshProjectOutputs(projectId);
      setStatusMessage(`Deleted ${runLabel(source)}.`);
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to delete run"));
    } finally {
      setPlatformActionLoading(false);
    }
  }

  async function onCreateBaseModelDraft(name = "") {
    setPlatformActionLoading(true);
    setErrorMessage("");
    try {
      const project = await ensureActiveProject();
      const projectId = project && project.project_id ? project.project_id : "default";
      const requestPayload = baseRunRequestPayload(projectId, name);
      const draft = await api.createRunDraft(projectId, requestPayload);
      applyRunRequestToControls(draft.request || requestPayload);
      setActiveJob(null);
      setRunning(false);
      setResult(null);
      setSelectedRunId("");
      setIntegratedPayload(null);
      setSelectedJobId(runExecutionId(draft));
      setRunViewMode("setup");
      await refreshProjectWorkspace(projectId);
      setSelectedJobId(runExecutionId(draft));
      setStatusMessage(`Created editable model draft "${runLabel(draft)}".`);
      return draft;
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to create model draft"));
      return null;
    } finally {
      setPlatformActionLoading(false);
    }
  }

  async function onCreateModelDraftFromExisting(sourceRunId, name = "") {
    if (!sourceRunId) {
      setErrorMessage("Select an existing model input to customize.");
      return null;
    }
    const projectId = activeProjectId || "";
    if (!projectId) {
      setErrorMessage("Select a project before creating a model draft.");
      return null;
    }
    setPlatformActionLoading(true);
    setErrorMessage("");
    try {
      const duplicated = await api.duplicateProjectRun(projectId, sourceRunId);
      const cleanName = String(name || "").trim();
      const draft = cleanName
        ? await api.updateRunDraft(projectId, duplicated.run_id, { run_name: cleanName })
        : duplicated;
      applyRunRequestToControls(draft.request || duplicated.request || {});
      setActiveJob(null);
      setRunning(false);
      setResult(null);
      setSelectedRunId("");
      setIntegratedPayload(null);
      setSelectedJobId(runExecutionId(draft));
      setRunViewMode("setup");
      await refreshProjectWorkspace(projectId);
      setSelectedJobId(runExecutionId(draft));
      setStatusMessage(`Created editable model draft "${runLabel(draft)}" from existing inputs.`);
      return draft;
    } catch (err) {
      setErrorMessage(toErrorMessage(err, "Failed to create model draft from existing input"));
      return null;
    } finally {
      setPlatformActionLoading(false);
    }
  }

  async function onSelectJob(job) {
    if (!job) return;
    const id = runExecutionId(job);
    const jobArchitectureId = job.request && job.request.model_architecture_id;
    if (jobArchitectureId) setSelectedArchitectureId(jobArchitectureId);
    if (job.request) applyRunRequestToControls(job.request);
    setSelectedJobId(id);
    setErrorMessage("");
    const runId = job.run_id || (job.artifacts && job.artifacts.run_id);
    if (normalizeStatus(job.status) === "succeeded" && runId) {
      try {
        const summary = job.summary || await api.fetchSummary(runId);
        setResult({
          artifacts: job.artifacts || {
            run_id: runId,
            summary_url: `/api/runs/${encodeURIComponent(runId)}/summary`,
            csv_url: `/api/runs/${encodeURIComponent(runId)}/artifacts/results_csv`,
          },
          summary,
        });
        setSelectedRunId(runId);
        setStatusMessage(`Inspecting ${runLabel(job)}.`);
        setRunViewMode("results");
      } catch (err) {
        setErrorMessage(toErrorMessage(err, "Failed to load selected model results"));
      }
    } else {
      setSelectedRunId("");
      setResult(null);
      setRunViewMode("setup");
      setStatusMessage("");
    }
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

  function onArchitectureChange(architectureId) {
    const next = architectureById(architectureCatalog, architectureId);
    setSelectedArchitectureId(next.id);
    setStatusMessage(`Selected model architecture: ${next.shortLabel || next.label}.`);
  }

  function onResetLevers() {
    setLevers({ ...DEFAULT_LEVERS });
  }

  const summaryDiagnostics = (result && result.summary && result.summary.summary_diagnostics) || {};
  const runMetadata = summaryDiagnostics.run_metadata || {};
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
    if (activeJob && selectedJobId && runExecutionId(activeJob) === selectedJobId) return activeJob;
    return (jobs || []).find((j) => runExecutionId(j) === selectedJobId || j.run_id === selectedJobId) || null;
  }, [jobs, activeJob, selectedJobId]);
  const selectedRunStatus = normalizeStatus(selectedJob && selectedJob.status);
  const selectedRunInputsLocked = Boolean(selectedJob && RUN_CONFIG_LOCK_STATUSES.has(selectedRunStatus));
  const selectedRunLockReason = selectedRunInputsLocked
    ? selectedRunStatus === "succeeded"
      ? "Completed model inputs are locked to preserve result provenance."
      : "Queued and running model inputs are locked because execution uses an immutable input snapshot."
    : "";
  const selectedRunActiveJob = activeJob && selectedJob && runExecutionId(activeJob) === runExecutionId(selectedJob)
    ? activeJob
    : null;
  const selectedEditableDraft = selectedJob && normalizeStatus(selectedJob.status) === "draft" && selectedJob.run_id
    ? selectedJob
    : null;
  const activeProject = useMemo(
    () => (projects || []).find((project) => project.project_id === activeProjectId) || null,
    [projects, activeProjectId]
  );
  const runDisabled = selectedRunInputsLocked || !selectedEditableDraft || !scenarioKey || (selectedArchitectureRequiresMrio && !mrioScenarioId) || queueSubmitting;
  const runDisabledReason = !selectedEditableDraft
    ? "Click New model to create an editable draft, or select an existing draft, before running."
    : selectedRunInputsLocked
      ? selectedRunLockReason
      : !scenarioKey
        ? "Select an energy scenario before running."
        : selectedArchitectureRequiresMrio && !mrioScenarioId
          ? "Select a target pathway before running."
          : "";

  const selectedRunLabel = selectedJob ? runLabel(selectedJob) : selectedRunId ? "Selected model" : "Latest model";
  const selectedRunName = selectedJob ? runCustomName(selectedJob) || "Untitled model" : "Selected model";
  const technicalEnergyModelOptions = energyModelCatalogOptions(scenarioCatalog);
  const technicalEnergyModel = technicalEnergyModelOptions.find(
    (option) => String(option && option.value) === String(energyModelEngine)
  ) || technicalEnergyModelOptions[0] || ENERGY_MODEL_OPTIONS[0];
  const technicalTargetScenario = (targetScenarios || []).find(
    (scenario) => scenario.scenario_id === mrioScenarioId
  ) || null;
  const technicalShockMapping = (mrioShockMappings || [])[0] || {};
  const technicalShockMappingId = technicalShockMapping.mapping_id || "mrio_direct_heuristic";
  const technicalExecution = (
    <TechnicalExecutionPanel
      selectedArchitecture={selectedArchitecture}
      selectedEnergyModel={technicalEnergyModel}
      scenarioKey={scenarioKey}
      requiresMrio={selectedArchitectureRequiresMrio}
      mrioScenarioId={mrioScenarioId}
      selectedTargetScenario={technicalTargetScenario}
      targetYear={targetYear}
      runProfile={runProfile}
      shockMapping={technicalShockMapping}
      showShockMapping={!result}
    />
  );
  const scenarioControls = (
    <DiagramScenarioControls
      architectureCatalog={architectureCatalog}
      selectedArchitectureId={selectedArchitecture.id}
      selectedArchitecture={selectedArchitecture}
      energyModelOptions={energyModelCatalogOptions(scenarioCatalog)}
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
      onArchitectureChange={onArchitectureChange}
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
      inputsLocked={selectedRunInputsLocked}
      lockReason={selectedRunLockReason}
    />
  );
  const operationsPanel = (
    <div className="diagram-ops-stack">
      {selectedRunInputsLocked ? (
        <DuplicateConfigurationPanel
          selectedJob={selectedJob}
          onDuplicateConfiguration={onDuplicateSelectedConfiguration}
          onDeleteRun={onDeleteSelectedRun}
          actionLoading={platformActionLoading}
          technicalExecution={result ? null : technicalExecution}
          showDuplicate={!result}
          style={{ marginTop: 0 }}
        />
      ) : (
        <EnvironmentSetupPanel
          environmentSetup={environmentSetup}
          loading={environmentSetupLoading}
          onRun={onRun}
          runDisabled={runDisabled}
          runDisabledReason={runDisabledReason}
          queueSubmitting={queueSubmitting}
          running={running}
          technicalExecution={technicalExecution}
          style={{ marginTop: 0 }}
        />
      )}
      <ActiveJobPanel activeJob={activeJob} onCancel={onCancelActiveJob} style={{ marginTop: 0 }} />
      {selectedRunStatus === "draft" ? (
        <DraftSavePanel
          job={selectedJob}
          onSave={onSaveSelectedDraft}
          saving={draftSaving}
        />
      ) : null}
      {!result && selectedJob && selectedRunStatus !== "draft" && !(activeJob && runExecutionId(activeJob) === runExecutionId(selectedJob)) ? (
        <div className="selected-run-action-row">
          <DetailDialogButton
            label="Selected model details"
            title="Selected model details"
            subtitle="Model record"
            wide={true}
          >
            <SelectedJobDetailsPanel job={selectedJob} style={{ marginTop: 0 }} />
          </DetailDialogButton>
        </div>
      ) : null}
    </div>
  );
  const resultsTechnicalDetails = result ? (
    <section className="results-technical-summary" aria-labelledby="results-technical-summary-title">
      <div className="results-kpi-group-label" id="results-technical-summary-title">Execution environment</div>
      <div className="analysis-technical-grid">
        <span>Solver: {runMetadata.solver || "-"}</span>
        <span>Termination: {runMetadata.termination_condition || "-"}</span>
        <span>Solve time: {runMetadata.solution_time_seconds != null ? `${toNumber(runMetadata.solution_time_seconds).toFixed(2)} s` : "-"}</span>
        <span>Objective: {runMetadata.objective_function_value != null ? compact(runMetadata.objective_function_value) : "-"}</span>
        <span>Spatial filter: <code>{spatialFilter ? spatialFilter.label || spatialFilter.locationId || spatialFilter.region || "-" : "none"}</code></span>
        {selectedArchitectureRequiresMrio ? (
          <span>MRIO shock mapping: <code>{technicalShockMappingId}</code></span>
        ) : null}
      </div>
    </section>
  ) : null;
  const runManagementPanel = (
    <ModelRunManagementPane
      activeJob={activeJob}
      selectedJob={selectedJob}
      operationsPanel={operationsPanel}
      errorMessage={errorMessage}
      statusMessage={statusMessage}
      runViewMode={runViewMode}
    />
  );
  const resultsPanel = result ? (
    <RunResultsPanel
      result={result}
      architecture={selectedArchitecture}
      selectedRunLabel={selectedRunLabel}
      selectedRunName={selectedRunName}
      onRenameModel={(nextName) => onRenameModel(selectedJob, nextName)}
      onDuplicateModel={selectedRunInputsLocked ? onDuplicateSelectedConfiguration : null}
      duplicateModelLoading={platformActionLoading}
      technicalExecutionPanel={technicalExecution}
      technicalDetailsPanel={resultsTechnicalDetails}
      selectedModelDetailsPanel={selectedJob && selectedRunStatus !== "draft" ? (
        <SelectedJobDetailsPanel job={selectedJob} style={{ marginTop: 0 }} showOutputLinks={false} />
      ) : null}
      runMetadata={runMetadata}
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
  const projectsOverviewPanel = (
    <ProjectsOverviewPanel
      projects={projects}
      activeProjectId={activeProjectId}
      activeProject={activeProject}
      projectRuns={projectRuns}
      projectReports={projectReports}
      projectExports={projectExports}
      onOpenProject={(projectId) => handleProjectChange(projectId, "project")}
      onCreateProject={handleCreateProject}
      onRenameProject={handleRenameProject}
      onArchiveProject={handleArchiveProject}
      onRestoreProject={handleRestoreProject}
      onDeleteProject={handleDeleteProject}
      onDownloadProjectFiles={onDownloadProjectFiles}
      onReturnHome={openLandingPage}
      currentUser={currentUser}
      actionLoading={platformActionLoading}
      isAdminView={isAdminView}
    />
  );
  const comparePanel = (
    <ProjectComparePanel
      activeProject={activeProject}
      projectRuns={projectRuns}
      projectReports={projectReports}
      projectExports={projectExports}
      compareRunIds={compareRunIds}
      onToggleCompareRun={onToggleCompareRun}
      onCreateReport={onCreateProjectReport}
      onCreateRunExport={onCreateRunExport}
      onNewModel={() => setNewModelModalOpen(true)}
      onOpenRun={onSelectJob}
      onReturnToProjects={openProjectsPage}
      actionLoading={platformActionLoading}
      isAdminView={isAdminView}
    />
  );
  const showRunTabs = runViewMode !== "projects" && runViewMode !== "project" && Boolean(activeProject);
  const clearMethodologyRoute = () => {
    if (window.location.hash === "#/methodology" && window.history && window.history.pushState) {
      window.history.pushState("", document.title, window.location.pathname + window.location.search);
    }
  };
  const openMethodologyPage = () => {
    setStatusMessage("");
    setErrorMessage("");
    setMethodologyOpen(true);
    setLandingOpen(false);
    if (window.location.hash !== "#/methodology") window.location.hash = "/methodology";
  };
  function openLandingPage() {
    setStatusMessage("");
    setErrorMessage("");
    clearMethodologyRoute();
    setMethodologyOpen(false);
    setLandingOpen(true);
  }
  function openProjectsPage() {
    setStatusMessage("");
    setErrorMessage("");
    clearMethodologyRoute();
    setMethodologyOpen(false);
    setLandingOpen(false);
    setRunViewMode("projects");
  }

  if (methodologyOpen) {
    const MethodologyPage = window.EDIMMethodology && window.EDIMMethodology.MethodologyPage;
    return MethodologyPage ? (
      <MethodologyPage
        architectureCatalog={architectureCatalog}
        header={(
          <UnifiedHeader
            currentUserId={currentUserId}
            availableUsers={availableUsers}
            onUserChange={handleUserChange}
            apiTarget={apiTarget}
            systemCompatibility={systemCompatibility}
            onApiTargetModeChange={handleApiTargetModeChange}
            apiTargetLoading={platformActionLoading}
            onReturnToLanding={openLandingPage}
          />
        )}
        onOpenProjects={openProjectsPage}
        onStartProject={openProjectsPage}
        onReturnDashboard={openLandingPage}
      />
    ) : (
      <div className="container">
        <div className="card">
          <h2>Explore the methodology</h2>
          <p className="muted">The methodology page script is not loaded.</p>
          <button type="button" onClick={openProjectsPage}>Open projects</button>
        </div>
      </div>
    );
  }

  if (landingOpen) {
    return (
      <LandingPage
        currentUserId={currentUserId}
        availableUsers={availableUsers}
        onUserChange={handleUserChange}
        apiTarget={apiTarget}
        systemCompatibility={systemCompatibility}
        onApiTargetModeChange={handleApiTargetModeChange}
        apiTargetLoading={platformActionLoading}
        onEnter={() => {
          openProjectsPage();
        }}
        onOpenMethodology={openMethodologyPage}
        statusMessage={statusMessage}
        errorMessage={errorMessage}
      />
    );
  }

  return (
    <div className="app-shell">
      <UnifiedHeader
        currentUserId={currentUserId}
        availableUsers={availableUsers}
        onUserChange={handleUserChange}
        apiTarget={apiTarget}
        systemCompatibility={systemCompatibility}
        onApiTargetModeChange={handleApiTargetModeChange}
        apiTargetLoading={platformActionLoading}
        onReturnToLanding={openLandingPage}
      />

      {newModelModalOpen ? (
        <NewModelModal
          projectRuns={projectRuns}
          defaultName={defaultRunName}
          onClose={() => setNewModelModalOpen(false)}
          onCreateBase={onCreateBaseModelDraft}
          onCreateFromExisting={onCreateModelDraftFromExisting}
          actionLoading={platformActionLoading}
        />
      ) : null}

      <div className={`global-run-tab-bar ${showRunTabs ? "" : "empty"}`}>
        {showRunTabs ? (
          <RunTabs
            jobs={jobs}
            selectedJobId={selectedJobId}
            activeJob={activeJob}
            mode={runViewMode}
            activeProject={activeProject}
            onReturnToProject={() => handleProjectChange(activeProjectId, "project")}
            onSelectJob={onSelectJob}
            onRenameModel={onRenameModel}
          />
        ) : null}
      </div>

      <div className={`app-body app-body-single workspace-mode-${runViewMode}`}>
        <ArchitectureRunWorkspace
          architecture={selectedArchitecture}
          runViewMode={runViewMode}
          flowActiveJob={selectedRunActiveJob}
          inputsLocked={selectedRunInputsLocked}
          lockReason={selectedRunLockReason}
          selectedRunId={selectedRunId}
          result={result}
          inputDatasets={inputDatasets}
          onUploadDataset={onUploadDataset}
          onDatasetVersionChange={onDatasetVersionChange}
          errorMessage={errorMessage}
          statusMessage={statusMessage}
          runManagementPanel={runManagementPanel}
          projectsOverviewPanel={projectsOverviewPanel}
          comparePanel={comparePanel}
          scenarioControls={scenarioControls}
          resultsPanel={resultsPanel}
          scenarioKey={scenarioKey}
          scenarioSelections={scenarioSelections}
        />
      </div>
    </div>
  );
}

try {
  ReactDOM.createRoot(document.getElementById("root")).render(<App />);
  window.EDIM_APP_MOUNTED = true;
} catch (error) {
  if (window.EDIM_SHOW_STARTUP_ERROR) {
    window.EDIM_SHOW_STARTUP_ERROR(error);
  }
  throw error;
}
