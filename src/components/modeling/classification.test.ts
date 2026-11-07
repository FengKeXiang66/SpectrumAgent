// TASK-36: these fail on lost task fields, editable grouping, invented counts or a broken task switch.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { Children, isValidElement, type ReactNode } from 'react';
import ts from 'typescript';
import { renderToStaticMarkup } from 'react-dom/server';
import { modelingClient, type ClassificationBody, type ClassificationResult, type ClassScore, type Request } from './api.ts';

type Element = { type: unknown; props: Record<string, unknown> };
let componentSerial = 0;
function elements(tree: ReactNode): Element[] {
  const result: Element[] = [];
  const visit = (node: ReactNode) => {
    if (!isValidElement<Record<string, unknown>>(node)) return;
    result.push(node); Children.forEach(node.props.children as ReactNode, visit);
  };
  visit(tree); return result;
}
async function component(file: string, dependencies: Record<string, unknown>) {
  let cursor = 0;
  const slots: unknown[] = [], effects = new Map<number, { deps: unknown[]; cleanup?: () => void }>();
  const pending: (() => void)[] = [];
  const scope = globalThis as unknown as Record<string, unknown>;
  const key = '__classification_' + file.replace(/\W/g, '_') + componentSerial++;
  scope[key] = { ...dependencies,
    useState: (initial: unknown) => {
      const index = cursor++;
      if (!(index in slots)) slots[index] = initial;
      return [slots[index], (value: unknown) => { slots[index] = typeof value === 'function' ? value(slots[index]) : value; }];
    },
    useEffect: (effect: () => (() => void) | void, deps: unknown[] = []) => {
      const index = cursor++, previous = effects.get(index);
      if (previous && deps.length === previous.deps.length && deps.every((item, i) => Object.is(item, previous.deps[i]))) return;
      previous?.cleanup?.();
      const entry = { deps, cleanup: undefined as (() => void) | undefined };
      effects.set(index, entry);
      pending.push(() => { if (effects.get(index) === entry) entry.cleanup = effect() || undefined; });
    },
  };
  const source = readFileSync(new URL(file, import.meta.url), 'utf8').replace(/^import[^\n]*;\r?$/gm, '');
  const prefix = 'const {' + Object.keys(scope[key] as object).join(',') + '} = globalThis[' + JSON.stringify(key) + '];\n';
  const output = ts.transpileModule(prefix + source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext } })
    .outputText.replace(/(["'])react\/jsx-runtime\1/g, JSON.stringify(import.meta.resolve('react/jsx-runtime')));
  const { default: Panel } = await import('data:text/javascript;base64,' + Buffer.from(output).toString('base64'));
  return {
    render: (props: object): ReactNode => { cursor = 0; return Panel(props); },
    flush: async () => { pending.splice(0).forEach(effect => effect()); for (let i = 0; i < 4; i++) await new Promise(resolve => setImmediate(resolve)); },
    dispose: () => { effects.forEach(effect => effect.cleanup?.()); delete scope[key]; },
  };
}

test('classification client forwards the explicit discriminated body through the existing native command', async () => {
  const calls: unknown[] = [];
  const client = modelingClient(async <T>(command: string, args: { request: Request }) => { calls.push({ command, args }); return {} as T; });
  const body: ClassificationBody = { task: 'classification', cube_ids: ['c'], annotation_version_ids: ['a'], preprocess_run_ids: ['p'],
    target: 'label', cv_strategy: 'group_kfold', cv_folds: 5, seed: 17, split_strategy: 'none', confidence_threshold: 0 };
  await client.train(body);
  assert.deepEqual(calls, [{ command: 'models_forward', args: { request: { op: 'create_run', body } } }]);
});

test('S07 classification uses bound reports, fixed five-fold CV, default zero threshold and real LV recommendations', async () => {
  const calls: Request[] = [];
  const client = modelingClient(async <T>(_command: string, { request }: { request: Request }) => {
    calls.push(request);
    if (request.op === 'preflight_run') return { status: 'succeeded' } as T;
    if (request.op === 'create_run') return { task: 'classification', status: 'succeeded', run_id: 'trained',
      by_cv_min: 2, by_elbow: 1, selected_lv: 2, confusion: { lv: {} } } as T;
    throw new Error('unexpected operation');
  });
  const records = Array.from({ length: 5 }, (_, i) => ({ id: 'c' + i }));
  const choices = Object.fromEntries(records.map(row => [row.id, [{ id: 'p' + row.id, version: 'a' + row.id }]]));
  const opened: string[] = [];
  const panel = await component('./ClassificationPanel.tsx', { modeling: client, displayName: (row: { id: string }) => row.id,
    failureMessage: String, preprocessing: { getArtifact: async (run: string) => ({ run_id: run, annotation_version_id: 'a' + run.slice(1),
      label_index: { '0': 'background', '1': 'material' }, curves: { classes: [{ label_index: 0, count: 2 }, { label_index: 1, count: 3 }] } }) } });
  let working: Promise<void> = Promise.resolve();
  const props = { records, choices, busy: false, work: (action: () => Promise<void>) => { working = action(); return working; }, onOpenResults: (id: string) => opened.push(id) };
  const render = () => elements(panel.render(props));
  const button = (name: string) => render().find(row => row.type === 'button' && row.props.children === name)!;
  const click = (name: string) => { (button(name).props.onClick as () => void)(); return working; };
  try {
    for (let i = 0; i < 5; i++) {
      const select = render().filter(row => row.type === 'select')[i];
      (select.props.onChange as (event: unknown) => void)({ target: { value: 'pc' + i } });
    }
    render(); await panel.flush();
    const tree = panel.render(props);
    assert.match(JSON.stringify(tree), /确认版已标像素 25 个，类别 2 个/);
    assert.equal(button('训练 PLS-DA').props.disabled, false);
    assert.equal(render().filter(row => row.type === 'select').length, 5, 'no editable CV or group key');
    await click('分类预检');
    await click('训练 PLS-DA');
    const request = calls.find(row => row.op === 'create_run');
    assert.deepEqual(request, { op: 'create_run', body: { task: 'classification', cube_ids: records.map(row => row.id),
      annotation_version_ids: records.map(row => 'a' + row.id), preprocess_run_ids: records.map(row => 'p' + row.id),
      target: 'label', cv_strategy: 'group_kfold', cv_folds: 5, split_strategy: 'none', seed: 17, confidence_threshold: 0 } });
    assert.match(JSON.stringify(panel.render(props)), /CV 最小建议 LV/);
    (button('查看分类结果').props.onClick as () => void)(); assert.deepEqual(opened, ['trained']);
    const threshold = render().filter(row => row.type === 'input')[2];
    (threshold.props.onChange as (event: unknown) => void)({ target: { value: '1' } });
    await assert.rejects(click('训练 PLS-DA'), /置信度阈值须在/);
  } finally { panel.dispose(); }
});

test('S07 task toggle preserves the regression form and makes classification independently reachable', async () => {
  const ClassificationPanel = () => null;
  const panel = await component('./ModelPanel.tsx', { ClassificationPanel, RegistryPanel: () => null, InferencePanel: () => null,
    displayName: String, annotations: { projects: async () => [], labels: async () => [] },
    preprocessing: {}, modeling: { targets: async () => [] } });
  const props = { records: [], onClose() {}, onOpenResults() {} };
  try {
    assert.match(JSON.stringify(panel.render(props)), /样品连续量/);
    const toggle = elements(panel.render(props)).find(row => row.type === 'button' && row.props.children === 'PLS-DA 分类')!;
    (toggle.props.onClick as () => void)();
    assert.ok(elements(panel.render(props)).some(row => row.type === ClassificationPanel));
    const back = elements(panel.render(props)).find(row => row.type === 'button' && row.props.children === 'PLS 回归')!;
    (back.props.onClick as () => void)();
    assert.match(JSON.stringify(panel.render(props)), /样品连续量/);
  } finally { panel.dispose(); }
});

function classificationResult(): ClassificationResult {
  const score: ClassScore = { oa: .75, kappa: .5, aa: .75, macro_f1: .7, labels: [0, 1], confusion: [[2, 0], [1, 1]],
    per_class: [{ label: 0, precision: 2/3, recall: 1, f1: .8 }, { label: 1, precision: null, recall: .5, f1: null }] };
  const statistic = { mean: .4, std: .1 };
  const summary = { oa: statistic, kappa: statistic, aa: statistic, macro_f1: statistic,
    per_class: [{ label: 0, precision: statistic, recall: statistic, f1: statistic },
      { label: 1, precision: { mean: null, std: null }, recall: statistic, f1: { mean: null, std: null } }] };
  return { task: 'classification', run_id: 'classification-run', status: 'succeeded', n_samples: 2, n_pixels_used: 6,
    selected_lv: 2, best_lv: 2, by_cv_min: 2, by_elbow: 1, metrics: { pixel: { oa: .625, kappa: null }, sample: { oa: .5, kappa: 0 } },
    leak_report: { passed: true }, error: null, confusion: { scores: { pixel: score, sample: score },
      folds: [{ fold_index: 0, pixel: score, sample: score }], fold_summary: { pixel: summary, sample: summary },
      threshold: { confidence_threshold: .6, uncertain_pixels: 2, accepted_pixels: 4, total_pixels: 6 },
      lv: { best_lv: 2, elbow_lv: 1, selected_lv: 2, by_cv_min: 2, by_elbow: 1, manual_override: false, definition: 'saved rule', curve: [] },
      manifest: { operator: 'train_plsda', operator_version: 1, code_version: 'revision', seed: 17 } } };
}

test('classification rendering preserves DB metrics, JSON matrix/F1/fold statistics and null disclosure', async () => {
  const panel = await component('./ClassificationResults.tsx', {});
  try {
    const html = renderToStaticMarkup(panel.render({ result: classificationResult() }));
    for (const label of ['像素级分类指标', '样品级分类指标', 'pixel 混淆矩阵', 'sample 混淆矩阵', '每类 F1', '折间均值', '置信度阈值', '不确定像素']) assert.ok(html.includes(label));
    assert.match(html, /<dd>0.625<\/dd>/, 'OA must come from the metric table response');
    assert.match(html, /<dd>不适用<\/dd>/);
    assert.match(html, /<td>0.4<\/td><td>0.1<\/td>/, 'fold statistics must use saved backend values');
    assert.doesNotMatch(html, /94.5%|0.921|782,500|伪彩分类图|ROC|Top 5|NaN|undefined/);
    const preflight = renderToStaticMarkup(panel.render({ result: { task: 'classification', status: 'succeeded' } }));
    assert.match(preflight, /尚无分类训练产物/);
  } finally { panel.dispose(); }
});

test('S08 classification reads only the selected run and never requests regression charts or a separate sweep', async () => {
  const calls: string[] = [], ClassificationResults = () => null, RegressionCharts = () => null;
  const panel = await component('../../screens/S08.tsx', { ClassificationResults, RegressionCharts, metricLabels: {}, failureMessage: String,
    regressionCharts: () => [], modeling: { run: async (id: string) => { calls.push(id); return classificationResult(); },
      sweep: async () => { assert.fail('classification must not fetch a regression sweep'); } } });
  const props = { runId: 'classification-run', onOpen() {}, onBackToList() {}, onClose() {} };
  try {
    panel.render(props); await panel.flush();
    const tree = elements(panel.render(props));
    assert.deepEqual(calls, ['classification-run']);
    assert.ok(tree.some(row => row.type === ClassificationResults));
    assert.ok(!tree.some(row => row.type === RegressionCharts));
  } finally { panel.dispose(); }
});

test('S08 list retains regression runs and also includes classification runs', async () => {
  const panel = await component('../../screens/S08.tsx', { ClassificationResults: () => null, RegressionCharts: () => null, metricLabels: {}, failureMessage: String,
    regressionCharts: () => [], modeling: { runs: async () => [{ id: 'regression-id', task: 'regression', status: 'succeeded' },
      { id: 'classification-id', task: 'classification', status: 'succeeded' }, { id: 'unknown-id', task: 'unknown', status: 'succeeded' }] } });
  const props = { runId: null, onOpen() {}, onBackToList() {}, onClose() {} };
  try {
    panel.render(props); await panel.flush();
    const html = renderToStaticMarkup(panel.render(props));
    assert.ok(html.includes('regression-id') && html.includes('classification-id'));
    assert.ok(!html.includes('unknown-id'));
  } finally { panel.dispose(); }
});

test('S09 classification table follows the unchanged regression table and uses exactly one listing with no detail fan-out', async () => {
  let listings = 0, details = 0;
  const panel = await component('../../screens/S09.tsx', { ClassificationResults: () => null, metricLabels: {}, failureMessage: String,
    displayName: String, preprocessing: { listRuns: async () => { assert.fail('no selected dataset'); } }, modeling: {
      runs: async () => { listings++; return [{ id: 'regression-id', task: 'regression', status: 'succeeded' },
        { id: 'classification-id', task: 'classification', status: 'succeeded', oa: .625, kappa: null, lv: 2 },
        { id: 'preflight-id', task: 'classification', status: 'succeeded' }]; },
      run: async () => { details++; return classificationResult(); } } });
  const props = { records: [] };
  try {
    panel.render(props); await panel.flush();
    const html = renderToStaticMarkup(panel.render(props));
    assert.equal(listings, 1); assert.equal(details, 0);
    assert.ok(html.indexOf('aria-label="回归台账列表"') < html.indexOf('aria-label="分类台账列表"'));
    const table = html.slice(html.indexOf('<table aria-label="回归台账列表">'), html.indexOf('</table>')+8);
    assert.deepEqual([...table.matchAll(/<th>(.*?)<\/th>/g)].map(row => row[1]), ['运行 ID', 'task', 'status']);
    const classification = html.slice(html.indexOf('<table aria-label="分类台账列表">'));
    assert.ok(classification.includes('classification-id') && classification.includes('preflight-id'));
    assert.match(classification, /<td>0.625<\/td><td>不适用<\/td><td>2<\/td>/);
    assert.doesNotMatch(classification, /NaN|undefined|94.5%|0.921/);
  } finally { panel.dispose(); }
});
