import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';
import { Children, isValidElement, type ReactNode } from 'react';
import { modelingClient, mapSource, paletteGradient, clippingMessage, inferenceWarning, stageLabels,
  type Request, type ConcentrationMap, type InferenceStats } from './api.ts';

test('six new fixed requests preserve exact bodies and strip input extras', async () => {
  const sent: { command: string; request: Request }[] = [];
  const client = modelingClient(async <T>(command: string, { request }: { request: Request }): Promise<T> => {
    sent.push({ command, request }); return {} as T;
  });
  await client.register('run');
  await client.register('run', 'model');
  await client.models();
  await client.stage('model', 'production');
  await client.infer({ model_id: 'model', cube_id: 'cube', preprocess_run_id: 'pre', annotation_version_id: 'ann', url: 'bad' } as never);
  await client.inference('infer');
  await client.inferenceMap('infer');
  assert.ok(sent.every(row => row.command === 'models_forward'));
  assert.deepEqual(sent.map(row => row.request), [
    { op: 'register_model', run_id: 'run' }, { op: 'register_model', run_id: 'run', name: 'model' }, { op: 'list_models' },
    { op: 'set_model_stage', id: 'model', stage: 'production' },
    { op: 'create_inference', model_id: 'model', cube_id: 'cube', preprocess_run_id: 'pre', annotation_version_id: 'ann' },
    { op: 'get_inference', id: 'infer' }, { op: 'get_inference_map', id: 'infer' },
  ]);
});
test('map source permits only PNG base64 and positive integer dimensions', () => {
  const map = { width: 4, height: 65, mime: 'image/png', png_base64: 'iVBORw0KGgoAAA==', applicability_png_base64: 'iVBORw0KGgoBBB==' } as ConcentrationMap;
  assert.equal(mapSource(map), 'data:image/png;base64,iVBORw0KGgoAAA==');
  assert.equal(mapSource(map, true), 'data:image/png;base64,iVBORw0KGgoBBB==');
  for (const patch of [{ mime: 'image/svg+xml' }, { png_base64: '<script>' }, { width: 0 }, { height: 1.2 }]) {
    assert.equal(mapSource({ ...map, ...patch } as ConcentrationMap), '');
  }
});
test('fixed palette rejects invalid RGB and preserves ordered endpoints', () => {
  assert.equal(paletteGradient([[0, 1, 2], [253, 231, 37]]), 'linear-gradient(to right, rgb(0,1,2),rgb(253,231,37))');
  for (const input of [[], [[0, 1, 2]], [[0, 1, NaN], [0, 1, 2]], [[0, 1, 256], [0, 1, 2]]]) assert.equal(paletteGradient(input), '');
});
test('clipping disclosure includes foreground totals and both directions', () => {
  const text = clippingMessage({ out_of_range_count: 7, below_range_count: 2, above_range_count: 5 } as InferenceStats);
  assert.ok(text.includes('共 7 个越界')); assert.ok(text.includes('低于下限 2')); assert.ok(text.includes('高于上限 5'));
});
test('stages and required scientific warning are explicit', () => {
  assert.deepEqual(Object.keys(stageLabels), ['experiment', 'candidate', 'production']);
  assert.equal(inferenceWarning, '模型训练粒度＝样品均值谱；像素级预测为域外外推，仅表示含量空间分布趋势');
});
test('components use the client, disclose calibration, progress and independent map errors', () => {
  const registry = readFileSync(new URL('./RegistryPanel.tsx', import.meta.url), 'utf8');
  const inference = readFileSync(new URL('./InferencePanel.tsx', import.meta.url), 'utf8');
  for (const text of [registry, inference]) {
    assert.doesNotMatch(text, /\b(?:invoke|fetch)\s*\(/);
    assert.match(text, /可审计不可反证/);
  }
  assert.match(registry, /正在计算标定…/);
  assert.match(inference, /统计结果保留/);
  assert.match(inference, /全局训练残差区间/);
  assert.match(inference, /clippingMessage/);
  assert.match(inference, /pixel_mean/); assert.match(inference, /sample_prediction/);
});

test('registered coefficient button is lazy per model and shows pending then success or 404 state', async () => {
  // No DOM/Canvas: execute the actual component's event callbacks with isolated
  // hook state and React element objects, using the existing TypeScript compiler.
  const calls: Request[] = [], states: unknown[] = [], effects: (() => void)[] = [];
  let cursor = 0, mounted = false;
  const pending = new Map<string, { resolve(value: unknown): void; reject(error: unknown): void }>();
  const client = modelingClient(async <T>(_command: string, { request }: { request: Request }): Promise<T> => {
    calls.push(request);
    if (request.op === 'list_runs') return [] as T;
    if (request.op === 'list_models') return ['first', 'second'].map(id => ({
      id, name: id, version: 1, stage: 'experiment', quality_label: '仅可做半定量', metrics: {},
      applicability: { y_min: 0, y_max: 1, n_features: 3 },
    })) as T;
    if (request.op === 'get_coefficients') return new Promise<T>((resolve, reject) => {
      pending.set(request.model_id, { resolve: value => resolve(value as T), reject });
    });
    throw new Error('unexpected request');
  });
  const key = '__coefficient_event_test_135';
  const scope = globalThis as unknown as Record<string, unknown>;
  scope[key] = {
    modeling: client, stageLabels, failureMessage: (error: { detail?: string }) => error.detail ?? String(error),
    useState: (initial: unknown) => {
      const index = cursor++;
      if (!(index in states)) states[index] = initial;
      return [states[index], (next: unknown) => {
        states[index] = typeof next === 'function' ? next(states[index]) : next;
      }];
    },
    useEffect: (effect: () => void) => { if (!mounted) effects.push(effect); },
  };
  try {
    let source = readFileSync(new URL('./RegistryPanel.tsx', import.meta.url), 'utf8');
    source = source.replace(/^import .* from 'react';$/m, 'const {useState,useEffect} = globalThis["' + key + '"];')
      .replace(/^import .* from '.\/api.ts';$/m, 'const {modeling,stageLabels} = globalThis["' + key + '"];')
      .replace(/^import .* from '.\/chart.ts';$/m, 'const {failureMessage} = globalThis["' + key + '"];')
      .replace(/^import CoefficientChart from '.\/CoefficientChart.tsx';$/m, 'const CoefficientChart = () => null;');
    const output = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext } })
      .outputText.replace(/(["'])react\/jsx-runtime\1/g, JSON.stringify(import.meta.resolve('react/jsx-runtime')));
    const { default: Panel } = await import('data:text/javascript;base64,' + Buffer.from(output).toString('base64'));
    const render = (): ReactNode => { cursor = 0; const tree = Panel({ onClose() {} }); mounted = true; return tree; };
    const elements = (tree: ReactNode) => {
      const found: { type: unknown; props: Record<string, unknown> }[] = [];
      const visit = (node: ReactNode) => {
        if (!isValidElement<Record<string, unknown>>(node)) return;
        found.push(node); Children.forEach(node.props.children as ReactNode, visit);
      };
      visit(tree); return found;
    };
    const buttons = () => elements(render()).filter(node => node.type === 'button' && node.props.children === '查看波段系数');
    const charts = () => elements(render()).filter(node => node.props.input !== undefined).map(node => node.props.input as {
      loading?: boolean; result?: { model_id: string }; error?: string;
    });
    render(); effects.forEach(effect => effect());
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(buttons().length, 2);
    assert.deepEqual(calls.map(row => row.op), ['list_runs', 'list_models']);
    assert.equal(charts().length, 0);
    (buttons()[0].props.onClick as () => void)();
    assert.deepEqual(calls.at(-1), { op: 'get_coefficients', model_id: 'first' });
    assert.equal(buttons()[0].props.disabled, true); assert.equal(charts()[0].loading, true);
    pending.get('first')!.resolve({ model_id: 'first', coefficients: [1, -2, 3] });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(charts()[0].result?.model_id, 'first');
    assert.equal(buttons()[0].props.disabled, false);
    (buttons()[1].props.onClick as () => void)();
    pending.get('second')!.reject({ error: 'MODEL_NOT_FOUND', detail: '注册模型不存在' });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(charts()[1].error, '注册模型不存在');
    assert.equal(charts()[0].result?.model_id, 'first');
    assert.deepEqual(calls.map(row => row.op), ['list_runs', 'list_models', 'get_coefficients', 'get_coefficients']);
  } finally { delete scope[key]; }
});
