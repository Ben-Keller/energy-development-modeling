const fs = require('fs');
const path = require('path');
const babel = require('@babel/standalone');

const root = path.resolve(__dirname, '..');
const repoRoot = path.resolve(root, '..');
const dist = path.join(root, 'dist');
const runtimeArchitectureCatalog = path.join(repoRoot, 'model_runtime', 'edim_model', 'architecture_catalog.json');
const architectureCatalogPath = runtimeArchitectureCatalog;
const vendorFiles = [
  ['node_modules/react/umd/react.production.min.js', 'vendor/react/react.production.min.js'],
  ['node_modules/react-dom/umd/react-dom.production.min.js', 'vendor/react/react-dom.production.min.js'],
  ['node_modules/leaflet/dist/leaflet.js', 'vendor/leaflet/leaflet.js'],
  ['node_modules/leaflet/dist/leaflet.css', 'vendor/leaflet/leaflet.css'],
  ['node_modules/leaflet/dist/images/layers.png', 'vendor/leaflet/images/layers.png'],
  ['node_modules/leaflet/dist/images/layers-2x.png', 'vendor/leaflet/images/layers-2x.png'],
  ['node_modules/leaflet/dist/images/marker-icon.png', 'vendor/leaflet/images/marker-icon.png'],
  ['node_modules/leaflet/dist/images/marker-icon-2x.png', 'vendor/leaflet/images/marker-icon-2x.png'],
  ['node_modules/leaflet/dist/images/marker-shadow.png', 'vendor/leaflet/images/marker-shadow.png'],
  ['node_modules/d3-delaunay/dist/d3-delaunay.min.js', 'vendor/d3/d3-delaunay.min.js'],
  ['node_modules/@turf/turf/turf.min.js', 'vendor/turf/turf.min.js'],
];

const knownIoTypes = new Set([
  'aggregate',
  'scenario',
  'catalog',
  'control',
  'manifest',
  'energy-config',
  'energy-scenario',
  'energy-network',
  'technology',
  'time-series',
  'geospatial',
  'mrio-scenario',
  'mrio-shock',
  'mapping',
  'calibration',
  'validation',
  'energy-output',
  'bridge-shock',
  'development-output',
  'diagnostic',
  'report',
  'package',
]);

const groupedIoTypes = new Set([
  'aggregate',
  'scenario',
  'catalog',
  'control',
  'manifest',
  'energy-config',
  'energy-scenario',
  'energy-network',
  'technology',
  'time-series',
  'geospatial',
  'mrio-scenario',
  'mrio-shock',
  'mapping',
  'calibration',
  'validation',
  'energy-output',
  'bridge-shock',
  'development-output',
  'diagnostic',
  'report',
  'package',
]);

const knownInformationLayers = new Set([
  'scenario-definition',
  'energy-input-package',
  'energy-runtime',
  'energy-results',
  'bridge-exchange',
  'mrio-input-package',
  'mrio-direct-assumptions',
  'geography-mapping',
  'development-results',
  'diagnostics-artifacts',
]);

const dataIoTypes = new Set([
  'scenario',
  'control',
  'energy-config',
  'energy-scenario',
  'energy-network',
  'technology',
  'time-series',
  'geospatial',
  'mrio-scenario',
  'mrio-shock',
  'mapping',
  'calibration',
  'energy-output',
  'bridge-shock',
  'development-output',
]);

function validateIoType(type, context) {
  const normalized = String(type || '').trim().toLowerCase();
  if (!normalized) throw new Error(`${context} is missing an I/O type.`);
  if (!knownIoTypes.has(normalized)) throw new Error(`${context} uses unknown I/O type '${type}'.`);
  if (!groupedIoTypes.has(normalized)) throw new Error(`${context} has no frontend wire group for I/O type '${type}'.`);
}

function validateInformationLayer(value, context) {
  const normalized = String(value || '').trim();
  if (!normalized) throw new Error(`${context} is missing informationLayer for Layers mode.`);
  if (!knownInformationLayers.has(normalized)) throw new Error(`${context} uses unknown informationLayer '${value}'.`);
}

function validateDataGroup(value, context) {
  const normalized = String(value || '').trim();
  if (!normalized) throw new Error(`${context} is missing dataGroup for Data mode.`);
}

function validateArchitectureCatalog() {
  if (!fs.existsSync(architectureCatalogPath)) {
    throw new Error('Missing model-owned architecture catalog at model_runtime/edim_model/architecture_catalog.json.');
  }
  const catalog = JSON.parse(fs.readFileSync(architectureCatalogPath, 'utf8'));
  const architectures = Array.isArray(catalog.architectures) ? catalog.architectures : [];
  if (!architectures.length) {
    throw new Error(`${path.relative(repoRoot, architectureCatalogPath)} must define at least one architecture.`);
  }
  const architectureIds = new Set(architectures.map((architecture) => architecture.id).filter(Boolean));
  if (!architectureIds.has(catalog.defaultArchitectureId)) {
    throw new Error(`defaultArchitectureId '${catalog.defaultArchitectureId}' does not match an architecture id.`);
  }
  for (const architecture of architectures) {
    const graph = architecture.graph || {};
    const graphNodes = Array.isArray(graph.nodes) ? graph.nodes : [];
    const nodeIds = new Set(graphNodes.map((node) => node.id).filter(Boolean));
    const boxIds = new Set((architecture.boxes || []).map((box) => box.id).filter(Boolean));
    for (const nodeId of nodeIds) {
      if (!boxIds.has(nodeId)) throw new Error(`Architecture '${architecture.id}' graph node '${nodeId}' has no matching box.`);
    }
    for (const edge of graph.edges || []) {
      if (!nodeIds.has(edge.from) || !nodeIds.has(edge.to)) {
        throw new Error(`Architecture '${architecture.id}' edge '${edge.from} -> ${edge.to}' references a missing node.`);
      }
      if (!Array.isArray(edge.io) || !edge.io.length) {
        throw new Error(`Architecture '${architecture.id}' edge '${edge.from} -> ${edge.to}' must declare I/O rows so Layers mode covers the information flow.`);
      }
      for (const ioRow of edge.io) {
        const rowContext = `Architecture '${architecture.id}' edge '${edge.from} -> ${edge.to}' I/O '${ioRow && ioRow.id ? ioRow.id : 'unknown'}'`;
        validateIoType(ioRow && ioRow.type, rowContext);
        validateInformationLayer(ioRow && ioRow.informationLayer, rowContext);
        if (dataIoTypes.has(String((ioRow && ioRow.type) || '').trim().toLowerCase()) && !Array.isArray(ioRow.layers)) {
          validateDataGroup(ioRow && ioRow.dataGroup, rowContext);
        }
        if (Array.isArray(ioRow.layers)) {
          for (const layer of ioRow.layers) {
            const layerType = (layer && layer.type) || ioRow.type;
            const layerContext = `${rowContext} layer '${layer && layer.id ? layer.id : 'unknown'}'`;
            validateIoType(layerType, layerContext);
            if (dataIoTypes.has(String(layerType || '').trim().toLowerCase())) {
              validateDataGroup((layer && layer.dataGroup) || (ioRow && ioRow.dataGroup), layerContext);
            }
          }
        }
      }
    }
    if (!Array.isArray(architecture.resultTabs) || !architecture.resultTabs.length) {
      throw new Error(`Architecture '${architecture.id}' must define resultTabs.`);
    }
    if (!Array.isArray(architecture.outputArtifacts) || !architecture.outputArtifacts.length) {
      throw new Error(`Architecture '${architecture.id}' must define outputArtifacts.`);
    }
  }
}

function copyFile(relativePath) {
  const source = path.join(root, relativePath);
  const target = path.join(dist, relativePath);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.copyFileSync(source, target);
}

function compiledScriptContent(relativePath) {
  const source = fs.readFileSync(path.join(root, relativePath), 'utf8');
  const result = babel.transform(source, {
    filename: relativePath,
    presets: ['env', 'react'],
    sourceType: 'script',
    sourceMaps: 'inline',
  });
  return `${result.code}\n`;
}

function writeCompiledScript(relativePath, targetRelativePath) {
  const target = path.join(dist, targetRelativePath);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, compiledScriptContent(relativePath), 'utf8');
}

function validateFrontendScripts() {
  [
    'hero-visual.jsx',
    'methodology/methodology.js',
    'domain/evidence.jsx',
    'app.jsx',
  ].forEach((relativePath) => {
    compiledScriptContent(relativePath);
  });
  vendorFiles.forEach(([sourceRelativePath]) => {
    if (!fs.existsSync(path.join(root, sourceRelativePath))) {
      throw new Error(`Missing bundled frontend runtime dependency: ${sourceRelativePath}. Run npm install.`);
    }
  });
}

function writeHtmlEntrypoint() {
  const source = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  const compiled = source
    .replace(/\n\s*<link rel="stylesheet" href="\.\/(?:design-phases|styles)\/[^"]+" \/>/g, '')
    .replace(
      /(<link rel="stylesheet" href="\.\/methodology\/methodology\.css" \/>)/,
      '$1\n    <link rel="stylesheet" href="./design-system.css?v=platform-reliability-5" />'
    )
    .replace(/\n\s*<script src="https:\/\/unpkg\.com\/@babel\/standalone\/babel\.min\.js"[^>]*><\/script>/, '')
    .replace(
      /\n\s*<script type="text\/babel" data-presets="env,react" src="\.\/hero-visual\.jsx"><\/script>/,
      '\n    <script src="./hero-visual.js"></script>'
    )
    .replace(
      /\n\s*<script type="text\/babel" data-presets="env,react" src="\.\/methodology\/methodology\.js"><\/script>/,
      '\n    <script src="./methodology/methodology.compiled.js"></script>'
    )
    .replace(
      /\n\s*<script type="text\/babel" data-presets="env,react" src="\.\/domain\/evidence\.jsx"><\/script>/,
      '\n    <script src="./domain/evidence.js"></script>'
    )
    .replace(
      /\n\s*<script type="text\/babel" data-presets="env,react" src="\.\/app\.jsx"><\/script>/,
      '\n    <script src="./app.js?v=workspace-user-summary-31"></script>'
    );
  fs.writeFileSync(path.join(dist, 'index.html'), compiled, 'utf8');
}

function writeConsolidatedDesignStyles() {
  const source = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  const paths = Array.from(
    source.matchAll(/<link rel="stylesheet" href="\.\/((?:design-phases|styles)\/[^"?]+)(?:\?[^"]*)?" \/>/g),
    (match) => match[1]
  );
  const content = paths.map((relativePath) => {
    const css = fs.readFileSync(path.join(root, relativePath), 'utf8');
    return `/* ${relativePath} */\n${css.trim()}\n`;
  }).join('\n');
  fs.writeFileSync(path.join(dist, 'design-system.css'), content, 'utf8');
}

function copyAbsoluteFile(sourcePath, targetRelativePath) {
  const target = path.join(dist, targetRelativePath);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.copyFileSync(sourcePath, target);
}

function copyDirectory(relativePath) {
  const source = path.join(root, relativePath);
  const target = path.join(dist, relativePath);
  if (!fs.existsSync(source) || !fs.statSync(source).isDirectory()) {
    throw new Error(`Missing frontend asset directory: ${relativePath}.`);
  }
  fs.cpSync(source, target, { recursive: true });
}

function readDotEnvValue(key) {
  const envPath = path.join(repoRoot, '.env');
  if (!fs.existsSync(envPath)) return '';
  const lines = fs.readFileSync(envPath, 'utf8').split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const idx = trimmed.indexOf('=');
    if (idx <= 0) continue;
    const name = trimmed.slice(0, idx).trim();
    if (name !== key) continue;
    let value = trimmed.slice(idx + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    return value;
  }
  return '';
}

function runtimeConfigContent() {
  const localApiBase = process.env.EDIM_LOCAL_API_BASE || readDotEnvValue('EDIM_LOCAL_API_BASE') || '';
  const backendApiBase = process.env.EDIM_BACKEND_API_BASE || readDotEnvValue('EDIM_BACKEND_API_BASE') || '';
  return [
    '// Generated frontend runtime configuration.',
    `window.EDIM_LOCAL_API_BASE = ${JSON.stringify(localApiBase)};`,
    `window.EDIM_BACKEND_API_BASE = ${JSON.stringify(backendApiBase)};`,
    '',
  ].join('\n');
}

validateArchitectureCatalog();
validateFrontendScripts();
if (process.argv.includes('--check')) {
  console.log('Frontend static assets, browser scripts, and architecture catalog are valid.');
  process.exit(0);
}
fs.rmSync(dist, { recursive: true, force: true });
fs.mkdirSync(dist, { recursive: true });
writeHtmlEntrypoint();
writeConsolidatedDesignStyles();
[
  'api-client.js',
  'geo/README.md',
  'geo/world_fit.geojson',
  'geo/countries.geojson',
  'geo/edim_locations_placeholder.geojson',
  'assets/undp-logo.svg',
  'assets/icons/sliders-horizontal.svg',
  'assets/icons/user-round.svg',
  'assets/icons/calendar.svg',
  'assets/icons/layers.svg',
  'assets/icons/map-pin.svg',
  'assets/icons/target.svg',
  'assets/icons/archive.svg',
  'assets/icons/pencil.svg',
  'assets/icons/chevron-down.svg',
  'hero-defaults.json',
].forEach(copyFile);
copyDirectory('assets/webp');
copyDirectory('methodology');
copyDirectory('vendor/fonts');
vendorFiles.forEach(([sourceRelativePath, targetRelativePath]) => {
  copyAbsoluteFile(path.join(root, sourceRelativePath), targetRelativePath);
});
writeCompiledScript('hero-visual.jsx', 'hero-visual.js');
writeCompiledScript('methodology/methodology.js', 'methodology/methodology.compiled.js');
writeCompiledScript('domain/evidence.jsx', 'domain/evidence.js');
writeCompiledScript('app.jsx', 'app.js');
copyAbsoluteFile(architectureCatalogPath, 'model_architectures.json');
fs.writeFileSync(path.join(dist, 'runtime-config.js'), runtimeConfigContent());
fs.writeFileSync(
  path.join(dist, 'runtime-config.local.js'),
  [
    'window.EDIM_LOCAL_API_BASE = window.EDIM_LOCAL_API_BASE || "";',
    'window.EDIM_BACKEND_API_BASE = window.EDIM_BACKEND_API_BASE || "";',
    '',
  ].join('\n')
);

const manifest = {
  schema_version: 'edim_frontend_static_bundle',
  generated_at: new Date().toISOString(),
  entrypoint: 'index.html',
  included_paths: [
    'index.html',
    'api-client.js',
    'design-system.css',
    'hero-visual.js',
    'domain/evidence.js',
    'app.js',
    'runtime-config.js',
    'runtime-config.local.js',
    'model_architectures.json',
    'geo/world_fit.geojson',
    'geo/countries.geojson',
    'geo/edim_locations_placeholder.geojson',
    'assets/undp-logo.svg',
    'assets/icons/sliders-horizontal.svg',
    'assets/icons/user-round.svg',
    'assets/icons/calendar.svg',
    'assets/icons/layers.svg',
    'assets/icons/map-pin.svg',
    'assets/icons/target.svg',
    'assets/icons/archive.svg',
    'assets/icons/pencil.svg',
    'assets/icons/chevron-down.svg',
    'assets/webp/',
    'vendor/fonts/',
    'hero-defaults.json',
    'methodology/methodology.css',
    'methodology/methodology.compiled.js',
    'vendor/react/',
    'vendor/leaflet/',
    'vendor/d3/',
    'vendor/turf/',
  ],
};
fs.writeFileSync(path.join(dist, 'bundle-manifest.json'), JSON.stringify(manifest, null, 2));
console.log(`Built static frontend bundle at ${dist}`);
