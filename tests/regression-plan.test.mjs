import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { regressionCommand, regressionInputLabel, validateRegression } from '../src/components/assistant/regression-plan-form.ts';

const document = { preprocess_run_ids: ['a', 'b', 'c', 'd'], target_schema_id: 'schema', split_strategy: 'ks',
  test_ratio: 1/3, cv_strategy: 'kfold', cv_folds: 2, seed: 17, n_components: null, max_components: 2 };

test('regression form requires explicit inputs and only serializes a reviewed execution', () => {
  validateRegression(document);
  validateRegression({ ...document, cv_strategy: 'loo', cv_folds: undefined });
  for (const patch of [{ preprocess_run_ids: ['a', 'a', 'b', 'c'] }, { preprocess_run_ids: [] }, { target_schema_id: '' },
    { split_strategy: undefined }, { test_ratio: NaN }, { test_ratio: 1 }, { seed: -1 }, { seed: 2**32 },
    { cv_folds: 1 }, { cv_folds: 257 }, { n_components: undefined }, { n_components: 0 }, { max_components: 0 }])
    assert.throws(() => validateRegression({ ...document, ...patch }));
  const text = regressionCommand({ action: 'execute', expected_revision: 3, review_digest: 'review', form_id: 'form' });
  assert.match(text, /^提交回归训练方案 /);
  assert.equal(regressionInputLabel(text), '回归训练方案：确认方案并训练');
  assert.equal(regressionInputLabel('普通对话'), '普通对话');
});

test('regression review shows actual targets and holdout membership through fixed local metadata API', async () => {
  const server = await createServer({ server: { middlewareMode: true, watch: null, hmr: false }, appType: 'custom' });
  try {
    const { RegressionReview } = await server.ssrLoadModule('/src/components/assistant/RegressionPlanCard.tsx');
    const { agentClient } = await server.ssrLoadModule('/src/components/assistant/api.ts');
    const calls = [];
    const client = agentClient(async (command, body) => { calls.push([command, body]); return {}; });
    await client.regressionPlan('session');
    assert.deepEqual(calls, [['agent_forward', { request: { op: 'regression_plan', id: 'session' } }]]);
    const html = renderToStaticMarkup(createElement(RegressionReview, { data: { revision: 3, document,
      members: [{ cube_id: 'train', name: '训练样品' }, { cube_id: 'test', name: '测试样品' }],
      review: { target_name: '含量', unit: '%', input_stage: '前景均值谱', inner_folds: 2, lv_upper_bound: 2,
        pipeline: { steps: [] }, metrics: ['RMSEP', 'R²P'], training_protocol: 'sample_pls_foldwise_v1',
        train_cube_ids: ['train'], test_cube_ids: ['test'], values: [{ cube_id: 'train', value: 10 }, { cube_id: 'test', value: 20 }], note: '训练折内拟合' },
    } }));
    assert.match(html, /修订 3/); assert.match(html, /前景均值谱/); assert.match(html, /训练折内拟合/);
    assert.match(html, /训练样品<\/td><td>10<\/td><td>训练／内层验证/);
    assert.match(html, /测试样品<\/td><td>20<\/td><td>独立测试/);
    assert.match(html, /原谱，无附加变换/); assert.match(html, /RMSEP、R²P/);
  } finally { await server.close(); }
});
