// TASK-36: these fail on lost task fields, editable grouping, invented counts or a broken task switch.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { Children, isValidElement, type ReactNode } from 'react';
import ts from 'typescript';
import { modelingClient, type ClassificationBody, type Request } from './api.ts';

type Element = { type: unknown; props: Record<string, unknown> };
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
  const key = '__classification_' + file.replace(/\W/g, '_');
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
