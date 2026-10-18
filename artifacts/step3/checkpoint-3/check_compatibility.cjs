// Uses the already installed npm's semver module. No package installation.
const fs = require('node:fs');
const path = require('node:path');
const semver = require('D:/Install/nvm/nodejs/node_modules/npm/node_modules/semver');
const metadata = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const selected = Object.fromEntries(metadata.results.filter(x => x.ecosystem === 'npm').map(x => [x.name, x.version]));
const rows = [];
for (const item of metadata.results.filter(x => x.ecosystem === 'npm')) {
  const range = item.engines?.node;
  if (range) {
    rows.push({ package: item.name, kind: 'node-engine', required: range, actual: process.versions.node, passed: semver.satisfies(process.versions.node, range) });
  }
  for (const [peer, required] of Object.entries(item.peerDependencies || {})) {
    const actual = selected[peer];
    const optional = item.peerDependenciesMeta?.[peer]?.optional === true;
    rows.push({ package: item.name, kind: 'peer', peer, required, actual: actual || null, optional,
      passed: actual ? semver.satisfies(actual, required) : optional });
  }
  if (item.raw.typeScriptVersion) {
    rows.push({ package: item.name, kind: 'minimum-typescript', required: item.raw.typeScriptVersion,
      actual: selected.typescript, passed: semver.gte(selected.typescript, semver.coerce(item.raw.typeScriptVersion)) });
  }
}
const npm = JSON.parse(fs.readFileSync('D:/Install/nvm/nodejs/node_modules/npm/package.json', 'utf8'));
rows.push({ package: 'npm', kind: 'node-engine', version: npm.version, required: npm.engines.node,
  actual: process.versions.node, passed: semver.satisfies(process.versions.node, npm.engines.node) });
const result = { node: process.version, platform: process.platform, arch: process.arch,
  PATH_Node_20_18_0_satisfies_vite: semver.satisfies('20.18.0', metadata.results.find(x => x.name === 'vite').engines.node), rows };
fs.writeFileSync(path.join(__dirname, 'compatibility-matrix.json'), JSON.stringify(result, null, 2) + '\n');
process.stdout.write(JSON.stringify(result, null, 2) + '\n');
if (rows.some(row => !row.passed)) process.exitCode = 1;
