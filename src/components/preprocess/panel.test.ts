import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { isTransportError, preprocessClient, recoverRun, submitRun } from './api.ts';
import { classLegend, describePreprocessError, PHASE_TWO, type PreprocessRequest, type RunSummary } from './types.ts';

const summary = (id: string, status = 'succeeded') => ({ id, status } as RunSummary);
test('recovery inspects only new succeeded summaries and matches recipe in details', async () => {
  const calls: PreprocessRequest[] = [];
  const api = preprocessClient(async <T>(_command: string, { request }: { request: PreprocessRequest }) => {
    calls.push(request);
    return (request.op === 'list_runs' ? [summary('old'), summary('pending', 'running'), summary('other'), summary('match')]
      : request.op === 'get_run' ? { id: request.id, recipe_version_id: request.id === 'match' ? 'chosen' : 'other', status: 'succeeded' } : null) as T;
  });
  assert.equal((await recoverRun(api, 'cube', 'chosen', [summary('old')]))?.id, 'match');
  assert.deepEqual(calls, [{ op: 'list_runs', dataset_id: 'cube' }, { op: 'get_run', id: 'other' }, { op: 'get_run', id: 'match' }]);
  assert.equal(await recoverRun(api, 'cube', 'missing', [summary('old')]), null);
});
test('transport and timeout recover, business errors do not; structured details remain visible', () => {
  assert.ok(isTransportError({ error: 'TRANSPORT', detail: 'connection lost' }));
  assert.ok(isTransportError(new Error('request timed out'))); assert.ok(isTransportError(new TypeError('Failed to fetch')));
  assert.equal(isTransportError({ error: 'INVALID_REQUEST', detail: 'bad recipe' }), false);
  assert.equal(isTransportError({ error: 'INVALID_REQUEST', detail: 'unsupported timeout parameter' }), false);
  assert.match(describePreprocessError({ error: 'INVALID_REQUEST', detail: 'duplicate code', context: { fields: ['code'] } }), /INVALID_REQUEST：duplicate code\n.*\n/s);
});
test('submit TRANSPORT automatically restores new matching success; unknown outcome stays pending verification', async () => {
  const calls: string[] = [];
  const body = { annotation_version_id: 'a', recipe_version_id: 'chosen' };
  const api = preprocessClient(async <T>(_command: string, { request }: { request: PreprocessRequest }) => {
    calls.push(request.op);
    if (request.op === 'create_run') throw { error: 'TRANSPORT', detail: 'lost response' };
    return (request.op === 'list_runs' ? [summary('new')] : { id: 'new', recipe_version_id: 'chosen', status: 'succeeded' }) as T;
  });
  const recovered = await submitRun(api, 'cube', body, []);
  assert.equal(recovered.interrupted, true); assert.equal(recovered.run?.id, 'new');
  assert.deepEqual(calls, ['create_run', 'list_runs', 'get_run']);
  const unavailable = preprocessClient(async () => { throw new Error('network unavailable'); });
  assert.deepEqual(await submitRun(unavailable, 'cube', body, []), { run: null, interrupted: true });
  const business = { error: 'OPERATOR_VERSION_STALE', detail: 'gone' };
  const rejected = preprocessClient(async () => { throw business; });
  await assert.rejects(() => submitRun(rejected, 'cube', body, []), error => error === business);
});
test('legend resolves index→id→code with backend colors, missing id prefix, unlabeled title', () => {
  assert.deepEqual(classLegend(2, { '2': 'abcdefgh-1234' }, [{ id: 'abcdefgh-1234', code: 'PET', color_hex: '#123456' }]), { code: 'PET', color: '#123456' });
  assert.equal(classLegend(2, { '2': 'abcdefgh-1234' }, []).code, 'abcdefgh');
  assert.equal(classLegend(-1, {}, []).code, '整体均值');
});
test('S06 component wiring: no transport outside API, no numeric engine / fake preview; global chat unchanged', () => {
  const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
  const panel = read('./PreprocessPanel.tsx'), editor = read('./PipelineEditor.tsx'), chart = read('./CompareChart.tsx');
  for (const source of [panel, editor, chart]) assert.doesNotMatch(source, /\bfetch\s*\(|\binvoke\s*\(|http:\/\//);
  assert.match(panel, /projects\[0\]/); assert.match(panel, /annotations\.versions\(record\.id\)/);
  assert.match(panel, /先在 S05 标注并保存/); assert.match(panel, /disabled=\{!annotationVersion/);
  assert.match(panel, /任务可能已完成/); assert.match(panel, /submitRun\(preprocessing/); assert.match(panel, /refresh最近|刷新最近/);
  assert.match(panel, /preprocessing\.addVersion/); assert.doesNotMatch(panel, /\.updateRecipe|\.deleteRecipe/);
  assert.match(panel, /comparison\.ranking\.map/); assert.doesNotMatch(panel, /ranking\.sort|fisher\s*[:=]\s*\w+\s*\//);
  assert.match(panel, /metrics\.boundaries/); assert.match(panel, /metrics\.limitations/); assert.match(panel, /comparison\.selection/);
  assert.match(panel, /step\.meta\.variance_definition/); assert.match(panel, /分量重构能量占比/);
  assert.match(chart, /未标注：整体均值/); assert.match(chart, /curveRuns\(values\)/); assert.match(chart, /band index/);
  assert.match(editor, /无波长轴，crop\/resample 禁用/); assert.match(editor, /生成目标轴/);
  assert.match(read('../datasets/DatasetPanel.tsx'), /<PreprocessPanel/);
  assert.doesNotMatch(read('./preprocess.css'), /position:\s*fixed|100vh|z-index/);
});
test('unsupported operations are all marked stage two / not applicable without example metrics', () => {
  assert.equal(PHASE_TWO.length, 5);
  for (const text of PHASE_TWO) assert.match(text, /阶段二/);
  assert.ok(PHASE_TWO.some(text => text.includes('坏波段'))); assert.ok(PHASE_TWO.some(text => text.includes('ROI')));
  assert.ok(PHASE_TWO.some(text => text.includes('Kappa'))); assert.ok(PHASE_TWO.some(text => text.includes('单独预览')));
});
