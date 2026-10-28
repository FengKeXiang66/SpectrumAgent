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
