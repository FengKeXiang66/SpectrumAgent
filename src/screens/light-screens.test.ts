import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const app = read('../App.tsx');
const dashboard = read('./S02.tsx');
const ledger = read('./S09.tsx');
const search = read('./S10.tsx');
const settings = read('./S11.tsx');

test('P5 S02 uses props for four cards, recent regression runs and phase plus generation only', () => {
  for (const label of ['数据集概览', '回归运行概览', '引擎概览', '快捷入口']) assert.ok(dashboard.includes(`aria-label="${label}"`));
  assert.match(dashboard, /records.length/);
  assert.match(dashboard, /runs.length/);
  assert.match(dashboard, /runs.slice\(0, 3\)/);
  assert.match(dashboard, /onOpenRun\(row.id\)/);
  assert.match(dashboard, /PHASE_TITLE\[status.phase\]/);
  assert.match(dashboard, /status.generation_id/);
  assert.doesNotMatch(dashboard, /\bpid\b|\bport\b|useEffect|modeling\.(?:runs|run)\(/);
  assert.match(app, /setDashboardRuns\(rows.filter\(row => row.task === 'regression'\)\)/);
  assert.match(app, /onOpenRun=\{id => openScreen\('s08', undefined, id\)\}/);
  assert.match(app, /onContinueAnnotation=\{\(\) => openScreen\('s05'\)\}/);
});

test('P5 S09 regression table has only id task status and a client task filter without invented timestamps', () => {
  const table = ledger.slice(ledger.indexOf('<table aria-label="回归台账列表">'), ledger.indexOf('</table>') + 8);
  assert.deepEqual([...table.matchAll(/<th>(.*?)<\/th>/g)].map(row => row[1]), ['运行 ID', 'task', 'status']);
  assert.doesNotMatch(table, /created_at|finished_at|时间|未知|Date/);
  assert.match(table, /row.id.slice\(0, 8\)/);
  assert.match(ledger, /useState<'all' \| 'regression'>\('regression'\)/);
  assert.match(ledger, /runs.filter\(row => row.task === 'regression'\)/);
  assert.match(ledger, /task === 'regression' \? regressionRuns : runs/);
  assert.doesNotMatch(ledger, /new Date|Date.now|Kappa/);
});

test('P5 S09 fetches selected run details and retains backend metrics quality and collapsed leak report', () => {
  assert.match(ledger, /modeling.run\(selectedRun\)/);
  assert.match(ledger, /setSelectedRun\(row.id\)/);
  for (const field of ['n_samples', 'n_pixels_used', 'selected_lv', 'best_lv', 'metrics', 'quality_label']) assert.ok(ledger.includes(`result.${field}`));
  assert.match(ledger, /<details><summary>泄漏预检<\/summary><pre>\{JSON.stringify\(result.leak_report/);
  assert.match(ledger, /if \(live\) setResult\(row\)/);
  assert.match(ledger, /setDetailError\(failureMessage\(failure\)\)/);
});

test('P5 S09 preprocess reads only the selected dataset and preserves real time fields and empty states', () => {
  assert.equal((ledger.match(/preprocessing.listRuns\(/g) ?? []).length, 1);
  assert.match(ledger, /if \(!datasetId\) return;[\s\S]*?preprocessing.listRuns\(datasetId\)/);
  assert.match(ledger, /\}, \[datasetId\]\)/);
  assert.match(ledger, /records.map\(record => <option[\s\S]*?displayName\(record\)/);
  assert.match(ledger, /<td>\{row.created_at\}<\/td><td>\{row.finished_at \?\? '尚未结束'\}/);
  assert.match(ledger, /选择一个数据集查看其预处理运行/);
  assert.match(ledger, /暂无已登记数据集。请先在数据屏登记数据。/);
  assert.match(ledger, /暂无回归运行记录。请先在建模屏完成训练。/);
  assert.doesNotMatch(ledger, /Promise.all\(records.map/);
});

test('P5 S10 has a data-screen action and S11 embeds the settings form without fake controls', () => {
  assert.match(search, /<h2>检索<\/h2>/);
  assert.match(search, /检索在阶段二提供。/);
  assert.match(search, /<button onClick=\{onOpenData\}>返回数据屏<\/button>/);
  assert.doesNotMatch(search, /后续批次启用|<input|useEffect|invoke/);
  assert.doesNotMatch(settings, /onOpenSettings|打开设置/);
  assert.match(settings, /出域记录在阶段二提供/);
  assert.equal((settings.match(/<button/g) ?? []).length, 0);
  assert.match(settings, /<SettingsPanel/);
  assert.doesNotMatch(settings, /<table|role="dialog"/);
  assert.match(app, /<S11 onBack=\{/);
  assert.doesNotMatch(app, /onOpenSettings/);
});

test('P5 inserts four screen cases while preserving source anchors S03 debug text and theme boundary', () => {
  for (const screen of ['s02', 's09', 's10', 's11']) {
    const position = app.indexOf(`case '${screen}':`);
    assert.ok(position >= 0 && position < app.indexOf('default:'));
  }
  assert.ok(app.includes('<p>进程 {status.pid} · 端口 {status.port} · 启动代次 {status.generation_id}</p>'));
  assert.ok(app.includes('<PreprocessPanel'));
  assert.ok(read('../components/datasets/DatasetPanel.tsx').includes("onOpen('s06', record)"));
  assert.ok(app.includes('<Composer'));
  for (const anchor of ["onClick={() => openScreen('s11')}>设置</button>", '<S11 onBack={', "case 's11'"]) assert.ok(app.includes(anchor));
  assert.doesNotMatch(dashboard + ledger + search + settings, /var\(--brand/);
});
