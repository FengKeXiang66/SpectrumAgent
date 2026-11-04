import test from 'node:test';
import assert from 'node:assert/strict';
import { datasetClient, type Request } from './api.ts';
import type { DatasetRecord } from './types.ts';

test('chat-selected registered cubes load through the existing fixed get operation', async () => {
  const calls: Request[] = [];
  const record = { id: '00000000-0000-0000-0000-000000000001', dataset: { name: '已登记样本' } } as DatasetRecord;
  const client = datasetClient(async () => null, async <T>(request: Request) => { calls.push(request); return record as T; });
  assert.equal(await client.get(record.id), record);
  assert.deepEqual(calls, [{ op: 'get', id: record.id }]);
});

test('catalog and recycle operations use fixed typed requests with explicit confirmation', async () => {
  const calls: Request[] = [];
  const client = datasetClient(async () => null, async <T>(request: Request) => {
    calls.push(request); return {} as T;
  });
  await client.catalog();
  await client.catalog(20, 40);
  await client.deletePreview('cube-id');
  await client.delete('cube-id', 'preview-token', true);
  await client.recycleList();
  await client.restore('deletion-id', true);
  assert.deepEqual(calls, [
    { op: 'catalog', limit: 100, offset: 0 }, { op: 'catalog', limit: 20, offset: 40 },
    { op: 'delete_preview', id: 'cube-id' },
    { op: 'delete', id: 'cube-id', confirm: true, preview_token: 'preview-token' },
    { op: 'recycle_list' }, { op: 'restore', deletion_id: 'deletion-id', confirm: true },
  ]);
});

test('reimport confirmation is sent only from an explicit caller choice', async () => {
  const calls: Request[] = [];
  const client = datasetClient(async () => null, async <T>(request: Request) => {
    calls.push(request); return {} as T;
  });
  await client.importDirectory('C:/source', true);
  await client.importDirectory('C:/source', true, true);
  assert.deepEqual(calls, [{ op: 'import', path: 'C:/source', raw: true },
    { op: 'import', path: 'C:/source', raw: true, confirm_new: true }]);
});
