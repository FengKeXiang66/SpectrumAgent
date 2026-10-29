import assert from 'node:assert/strict';
import test from 'node:test';
import { displayName, mergeRecords, type DatasetRecord } from '../../../src/components/datasets/types.ts';
import { datasetChoices, readableText } from '../../../src/components/assistant/presentation.ts';
import type { ChatEntry } from '../../../src/components/assistant/sse.ts';

test('G3 shared displayName uses the server name and preserves the legacy fallback', () => {
  const record = { id: 'one', dataset: { name: 'source' }, display_name: 'source（反射率）' } as DatasetRecord;
  assert.equal(displayName(record), 'source（反射率）');
  assert.equal(displayName({ ...record, display_name: undefined }), 'source');
  assert.equal(displayName({ ...record, display_name: '' }), '');
});

test('G2 all_datasets refreshes a previously unique name without duplicating records', () => {
  const reflected = { id: 'one', dataset: { name: 'source' }, display_name: 'source' } as DatasetRecord;
  const raw = { ...reflected, id: 'two', display_name: 'source（原始 DN）' };
  const updated = { ...reflected, display_name: 'source（反射率）' };
  const merged = mergeRecords([reflected], [updated, raw]);
  assert.deepEqual(merged.map(displayName), ['source（反射率）', 'source（原始 DN）']);
  assert.equal(merged.length, 2);
});

test('G assistant choices and readable references use exactly the API display name', () => {
  const id = '00000000-0000-0000-0000-000000000012';
  const record = { id, dataset: { name: 'source' }, display_name: 'source（原始 DN）' } as DatasetRecord;
  const entries: ChatEntry[] = [{ event: 'step', data: { tool: 'datasets.list', seq: 1, status: 'ok',
    result_summary: { dataset_12_id: id, dataset_12_name: record.display_name! } } }];
  const choices = datasetChoices(entries, [record]);
  assert.equal(choices[0].label, displayName(record));
  assert.ok(readableText(id, [], [record]).startsWith(displayName(record)));
  const legacy: ChatEntry[] = [{ event: 'step', data: { tool: 'datasets.list', seq: 1, status: 'ok',
    result_summary: { dataset_ids: id } } }];
  assert.equal(datasetChoices(legacy, [record])[0].label, displayName(record));
});
