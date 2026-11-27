import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { preprocessingPrompt } from '../src/components/assistant/preprocessing-navigation.ts';
import { validateClassification, formCommand, formInputLabel, recipeMemberStatus } from '../src/components/assistant/preprocessing-form.ts';
import { curveRuns, compilePipeline } from '../src/components/preprocess/pipeline.ts';
import { NAV, SCREEN_TITLE } from '../src/shell/screens.ts';

test('old preprocessing navigation preserves input, targets one sample and has no retired screen', () => {
  assert.equal(NAV.flatMap(group => group.items).some(row => row.screen === 's06'), false);
  assert.equal('s06' in SCREEN_TITLE, false);
  assert.match(preprocessingPrompt('sample-id', ''), /sample-id/);
  assert.match(preprocessingPrompt('sample-id', ''), /分类训练.*回归/);
  assert.equal(preprocessingPrompt('other-sample', '保留原输入'), '保留原输入');
});

test('classification and recipe parameter contracts remain distinct', () => {
  validateClassification([{ op: 'savgol', window: 5, polyorder: 2, derivative: 1, delta_nm: 5 }]);
  validateClassification([{ op: 'snv' }, { op: 'pca', n_components: 2 }]);
  for (const steps of [
    [{ op: 'sg_derivative', order: 1 }],
    [{ op: 'savgol', window: 4, polyorder: 2, derivative: 1, delta_nm: 5 }],
    [{ op: 'savgol', window: 5, polyorder: 2, derivative: 1 }],
    [{ op: 'pca' }], [{ op: 'snv', ddof: 3 }], [{ op: 'l2', epsilon: 0 }],
  ]) assert.throws(() => validateClassification(steps));
  assert.throws(() => compilePipeline([{ op: 'savgol', version: 1, params: {} }], [1, 2, 3], 3));
  assert.deepEqual(curveRuns([1, null, 2, 3, NaN]), [[[0, 1]], [[2, 2], [3, 3]]]);
  const command = formCommand({ kind: 'classification', action: 'update', expected_revision: 3 });
  assert.equal(formInputLabel(command), '分类预处理：提交参数修改');
  assert.equal(formInputLabel('你好'), '你好');
  assert.equal(recipeMemberStatus({ recipe_id: 'new', members: [{ cube_id: 'cube', recipe_id: 'old', status: 'ready' }] }, 'cube'), 'need_preprocess');
  assert.equal(recipeMemberStatus({ recipe_id: 'same', members: [{ cube_id: 'cube', recipe_id: 'same', status: 'ready' }] }, 'cube'), 'ready');
});

test('conversation exposes two form modes and serializes only a fixed read operation', async () => {
  const server = await createServer({ server: { middlewareMode: true, watch: null, hmr: false }, appType: 'custom' });
  try {
    const { default: Fields } = await server.ssrLoadModule('/src/components/assistant/ClassificationPreprocessingFields.tsx');
    const { default: PipelineEditor } = await server.ssrLoadModule('/src/components/preprocess/PipelineEditor.tsx');
    const { agentClient } = await server.ssrLoadModule('/src/components/assistant/api.ts');
    const { default: AssistantBar } = await server.ssrLoadModule('/src/components/assistant/AssistantBar.tsx');
    const { default: useSession } = await server.ssrLoadModule('/src/components/assistant/useSession.ts');
    const calls = [];
    const client = agentClient(async (command, body) => { calls.push([command, body]); return { kind: 'recipe' }; });
    await client.preprocessingEditor('session', 'recipe', 'cube');
    assert.deepEqual(calls, [['agent_forward', { request: { op: 'preprocessing_editor', id: 'session', kind: 'recipe', cube_id: 'cube' } }]]);
    const fields = renderToStaticMarkup(createElement(Fields, { disabled: false, steps: [
      { op: 'savgol', window: 9, polyorder: 3, derivative: 1, delta_nm: 5 }, { op: 'pca', n_components: 2 },
    ], onChange() {} }));
    assert.match(fields, /波长步长 nm/); assert.match(fields, /value="9"/); assert.match(fields, /训练折内拟合/);
    const recipe = renderToStaticMarkup(createElement(PipelineEditor, { steps: [{ op: 'sg_derivative', version: 1,
      params: { window: 5, polyorder: 2, order: 1 } }], initialAxis: [1, 2, 3, 4, 5], bands: 5, onChange() {} }));
    assert.match(recipe, /sg_derivative/); assert.match(recipe, /order/);
    function Probe() {
      const session = useSession({ enabled: true, generation: 1 });
      return createElement(AssistantBar, { session, onHistory() {}, onViewer() {} });
    }
    const html = renderToStaticMarkup(createElement(Probe));
    assert.match(html, /分类预处理参数/); assert.match(html, /回归／高级配方参数/);
  } finally { await server.close(); }
});
