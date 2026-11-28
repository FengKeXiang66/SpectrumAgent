import assert from 'node:assert/strict';
import test from 'node:test';
import { createServer } from 'vite';

test('new regression inference sends only model and cube; real masks and legacy references remain explicit', async () => {
  const server = await createServer({ server: { middlewareMode: true, watch: null, hmr: false }, appType: 'custom' });
  try {
    const { modelingClient } = await server.ssrLoadModule('/src/components/modeling/api.ts');
    const calls = [];
    const client = modelingClient(async (command, args) => { calls.push([command, args]); return {}; });
    await client.infer({ model_id: 'model', cube_id: 'new-cube' });
    await client.infer({ model_id: 'model', cube_id: 'masked-cube', annotation_version_id: 'mask' });
    await client.infer({ model_id: 'legacy', cube_id: 'old-cube', preprocess_run_id: 'run', annotation_version_id: 'annotation' });
    assert.deepEqual(calls.map(row => row[1].request), [
      { op: 'create_inference', model_id: 'model', cube_id: 'new-cube' },
      { op: 'create_inference', model_id: 'model', cube_id: 'masked-cube', annotation_version_id: 'mask' },
      { op: 'create_inference', model_id: 'legacy', cube_id: 'old-cube', preprocess_run_id: 'run', annotation_version_id: 'annotation' },
    ]);
    assert.ok(calls.every(row => row[0] === 'models_forward'));
  } finally { await server.close(); }
});
