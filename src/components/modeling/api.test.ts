import assert from 'node:assert/strict';
import test from 'node:test';
import { modelingClient, metricLabels, type Request } from './api.ts';

test('sample value uses fixed native command and preserves annotation response', async () => {
  const calls: unknown[] = [];
  const api = modelingClient(async <T>(command: string, args: { request: Request }) => {
    calls.push({ command, args }); return { value: 1.25, source: 'annotation' } as T;
  });
  assert.equal((await api.put('cube', 'schema', 1.25)).source, 'annotation');
  assert.deepEqual(calls, [{ command: 'models_forward', args: { request: { op: 'put_target', cube_id: 'cube', schema_id: 'schema', value: 1.25 } } }]);
  await assert.rejects(api.put('cube', 'schema', NaN));
  assert.equal(calls.length, 1);
});

test('CSV duplicate confirmation is an explicit second import', async () => {
  const calls: Request[] = [];
  const api = modelingClient(async <T>(_command: string, { request }: { request: Request }) => { calls.push(request); return {} as T; });
  await api.importCSV('project', 'cube_name,schema,value');
  await api.importCSV('project', 'cube_name,schema,value', true);
  assert.deepEqual(calls.map(row => row.op === 'import_targets' && row.overwrite), [false, true]);
});

test('PLS request retains explicit bound runs and only regression CV; seven result labels', async () => {
  const sent: Request[] = [];
  const api = modelingClient(async <T>(_command: string, { request }: { request: Request }) => { sent.push(request); return {} as T; });
  const body = { task: 'regression' as const, preprocess_run_ids: ['bound-run'], target_schema_id: 'schema', split_strategy: 'ks' as const,
    cv_strategy: 'loo' as const, cv_folds: 5, test_ratio: 1 / 3, seed: 17, n_components: 2 };
  await api.train(body); await api.run('run'); await api.sweep('run');
  assert.deepEqual(sent, [{ op: 'create_run', body }, { op: 'get_run', id: 'run' }, { op: 'lv_sweep', id: 'run' }]);
  assert.deepEqual(Object.keys(metricLabels), ['rmse', 'r2', 'rmsep', 'r2p', 'rpd', 'rer', 'bias']);
});

test('coefficients use one fixed read-only native operation and exact model id body', async () => {
  const sent: unknown[] = [];
  const api = modelingClient(async <T>(command: string, args: { request: Request }) => {
    sent.push({ command, args }); return { model_id: 'registered', coefficients: [1, -2] } as T;
  });
  assert.equal(sent.length, 0);
  const row = await api.coefficients('registered');
  assert.deepEqual(row.coefficients, [1, -2]);
  assert.deepEqual(sent, [{ command: 'models_forward', args: { request: { op: 'get_coefficients', model_id: 'registered' } } }]);
});
