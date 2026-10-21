import assert from 'node:assert/strict';
import test from 'node:test';
import { preprocessClient, requests } from './api.ts';
import type { PreprocessApi, PreprocessRequest, RecipeBody, RunBody } from './types.ts';

const pipeline = { steps: [{ op: 'snv', version: 1, params: {} }] };
const body = { annotation_version_id: 'annotation', recipe_version_id: 'recipe-version' };
const cases: [string, (api: PreprocessApi) => Promise<unknown>, PreprocessRequest][] = [
  ['list_recipes', api => api.listRecipes(), { op: 'list_recipes' }],
  ['create_recipe', api => api.createRecipe({ code: 'example', name: '示例', description: '描述', note: '备注', pipeline }), { op: 'create_recipe', body: { code: 'example', name: '示例', description: '描述', note: '备注', pipeline } }],
  ['get_recipe', api => api.getRecipe('recipe'), { op: 'get_recipe', id: 'recipe' }],
  ['add_version', api => api.addVersion('recipe', { pipeline, note: 'new' }), { op: 'add_version', id: 'recipe', body: { pipeline, note: 'new' } }],
  ['select_recipe', api => api.selectRecipe('project', 'recipe'), { op: 'select_recipe', project_id: 'project', recipe_id: 'recipe' }],
  ['deselect_recipe', api => api.deselectRecipe('project', 'recipe'), { op: 'deselect_recipe', project_id: 'project', recipe_id: 'recipe' }],
  ['list_project_recipes', api => api.listProjectRecipes('project'), { op: 'list_project_recipes', project_id: 'project' }],
  ['create_run', api => api.createRun('dataset', body), { op: 'create_run', dataset_id: 'dataset', body }],
  ['list_runs', api => api.listRuns('dataset'), { op: 'list_runs', dataset_id: 'dataset' }],
  ['get_run', api => api.getRun('run'), { op: 'get_run', id: 'run' }],
  ['compare', api => api.compare('dataset', { annotation_version_id: 'annotation', recipe_version_ids: ['r1', 'r2'] }), { op: 'compare', dataset_id: 'dataset', body: { annotation_version_id: 'annotation', recipe_version_ids: ['r1', 'r2'] } }],
  ['get_artifact', api => api.getArtifact('run', 'report'), { op: 'get_artifact', run_id: 'run', kind: 'report' }],
];
for (const [op, call, expected] of cases) test(`preprocess IPC ${op}: exact projection and sole command`, async () => {
  const sent: unknown[] = [];
  const api = preprocessClient(async <T>(command: string, args: { request: PreprocessRequest }) => { sent.push({ command, args }); return { marker: true } as T; });
  assert.deepEqual(await call(api), { marker: true });
  assert.deepEqual(sent, [{ command: 'preprocess_forward', args: { request: expected } }]);
});
test('request bodies omit runtime extras, run guard/block_size, and editor state', () => {
  const extra = { ...body, guard: 'keep', block_size: 1, url: 'forbidden', draft: true };
  assert.deepEqual(requests.createRun('dataset', extra as RunBody), { op: 'create_run', dataset_id: 'dataset', body });
  const recipe = { code: 'c', name: 'n', pipeline, preview: true };
  assert.deepEqual(requests.createRecipe(recipe as RecipeBody), { op: 'create_recipe', body: { code: 'c', name: 'n', pipeline } });
  assert.deepEqual(requests.compare('d', { annotation_version_id: 'a', recipe_version_ids: ['r'], ...{ block_size: 1 } }),
    { op: 'compare', dataset_id: 'd', body: { annotation_version_id: 'a', recipe_version_ids: ['r'] } });
});
test('report is parsed JSON; only sample_spectra uses binary wrapper; 204 stays null', async () => {
  const report = { curves: { classes: [] } }, binary = { content_type: 'application/octet-stream', body_base64: 'AA==', filename: 'sample_spectra.npz' };
  const api = preprocessClient(async <T>(_command: string, { request }: { request: PreprocessRequest }) =>
    (request.op === 'get_artifact' ? request.kind === 'report' ? report : binary : null) as T);
  assert.equal(await api.getArtifact('r', 'report'), report);
  assert.equal(await api.getArtifact('r', 'sample_spectra'), binary);
  assert.equal(await api.deselectRecipe('p', 'r'), null);
});
