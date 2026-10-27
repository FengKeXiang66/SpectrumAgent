import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
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
