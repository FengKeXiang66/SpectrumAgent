import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const app = source('../App.tsx');
const datasets = source('../components/datasets/DatasetPanel.tsx');
const model = source('../components/modeling/ModelPanel.tsx');
const viewer = source('./S04.tsx');
const results = source('./S08.tsx');

test('P2 navigation preserves App runId until the results back-to-list action', () => {
  assert.match(app, /\[runId, setRunId\] = useState<string \| null>\(null\)/);
  assert.match(app, /openScreen = \(next: Screen, record\?: DatasetRecord, run\?: string\)/);
  assert.match(app, /if \(run !== undefined\) setRunId\(run\)/);
  assert.match(app, /onNavigate=\{next => openScreen\(next\)\}/);
  assert.equal((app.match(/setRunId\(null\)/g) ?? []).length, 1);
  assert.match(app, /onBackToList=\{\(\) => setRunId\(null\)\}/);
  assert.match(results, /<button onClick=\{onBackToList\}>返回列表<\/button>/);
});

test('P2 S04 and S03 thumbnails share BandCanvas and viewing updates workspace', () => {
  assert.match(datasets, /import BandCanvas from '\.\/BandCanvas'/);
  assert.match(viewer, /import BandCanvas from '\.\.\/components\/datasets\/BandCanvas'/);
  assert.match(datasets, /<BandCanvas preview=\{preview\} thumbnail \/>/);
  assert.match(datasets, /onOpen\('s04', record\); onWorkspaceChange\?\.\(\{ cube_id: record.id \}\); \}\}>查看/);
  assert.doesNotMatch(datasets, /selectedRecord|loadPreview|单波段预览/);
  assert.match(viewer, /api.preview\(record.id, index\)/);
  assert.match(viewer, /request === sequence.current/);
  assert.match(app, /case 's04':[\s\S]*?<S04[\s\S]*?onClose=\{\(\) => setScreen\('s03'\)\}/);
});

test('P2 S08 loads real regression runs and refetches run plus sweep on mount', () => {
  assert.match(results, /modeling.runs\(\)/);
  assert.match(results, /rows.filter\(row => row.task === 'regression'\)/);
  assert.match(results, /onOpen\(row.id\)/);
  assert.match(results, /if \(runId !== null\) void load\(runId\)/);
  assert.match(results, /await modeling.run\(id\)/);
  assert.match(results, /await modeling.sweep\(row.run_id\)/);
  assert.match(results, /aria-label="回归结果"/);
  assert.match(results, /<RegressionCharts/);
  assert.match(results, /!listLoading && !listError/);
  assert.match(results, /暂无回归运行记录。请先在建模屏完成训练。/);
  assert.match(app, /onOpen=\{id => openScreen\('s08', undefined, id\)\}/);
});

test('P2 S07 keeps training and internal views while results and source anchors stay intact', () => {
  assert.match(model, /modeling.train\(/);
  assert.match(model, /onOpenResults\(row.run_id\)/);
  assert.match(model, /<RegistryPanel/);
  assert.match(model, /<InferencePanel/);
  assert.doesNotMatch(model, /回归记录|aria-label="回归结果"|RegressionCharts|beginCharts|acceptResult/);
  assert.match(app, /<PreprocessPanel/);
  assert.match(datasets, /onOpen\('s06', record\)/);
  assert.match(app, /<Composer/);
  assert.ok(app.includes("import SettingsPanel from './components/settings/SettingsPanel'"));
  assert.ok(app.includes('onClick={() => setSettingsOpen(true)}>设置</button>'));
  assert.ok(app.includes("settingsOpen && status.phase === 'Ready' && <SettingsPanel"));
  assert.doesNotMatch(viewer + results, /var\(--brand/);
});
