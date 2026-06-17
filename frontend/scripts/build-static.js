const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const repoRoot = path.resolve(root, '..');
const dist = path.join(root, 'dist');
const runtimeArchitectureCatalog = path.join(repoRoot, 'model_runtime', 'edim_model', 'architecture_catalog.json');
const architectureCatalogPath = runtimeArchitectureCatalog;

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
if (process.argv.includes('--check')) {
  console.log('Frontend static assets and architecture catalog are valid.');
  process.exit(0);
}
fs.rmSync(dist, { recursive: true, force: true });
[
  'index.html',
  'api-client.js',
  'hero-visual.jsx',
  'app.jsx',
  'geo/README.md',
  'geo/world_fit.geojson',
  'geo/countries.geojson',
  'geo/edim_locations_placeholder.geojson',
  'assets/undp-logo.svg',
  'hero-defaults.json',
].forEach(copyFile);
copyDirectory('assets/webp');
copyDirectory('methodology');
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
    'hero-visual.jsx',
    'app.jsx',
    'runtime-config.js',
    'runtime-config.local.js',
    'model_architectures.json',
    'geo/world_fit.geojson',
    'geo/countries.geojson',
    'geo/edim_locations_placeholder.geojson',
    'assets/undp-logo.svg',
    'assets/webp/',
    'hero-defaults.json',
    'methodology/methodology.css',
    'methodology/methodology.js',
  ],
};
fs.writeFileSync(path.join(dist, 'bundle-manifest.json'), JSON.stringify(manifest, null, 2));
console.log(`Built static frontend bundle at ${dist}`);
