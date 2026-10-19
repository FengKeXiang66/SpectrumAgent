import assert from 'node:assert/strict';
import test from 'node:test';
import { mergeRecords, describeError, type DatasetRecord } from './types.ts';

test('retries and existing imports keep exactly one row per persisted ID', () => {
  const record = { id: 'one', dataset: { name: 'a' }, existing: false } as DatasetRecord;
  const updated = { ...record, existing: true };
  assert.deepEqual(mergeRecords([record], [updated, { ...record, id: 'two' }]), [updated, { ...record, id: 'two' }]);
});

test('batch errors retain source path and reason for the user', () => {
  const message = describeError({ detail: '整批未登记', context: { items: [{ path: 'example.hdr', error: 'SIZE_MISMATCH' }] } });
  assert.match(message, /example.hdr/);
  assert.match(message, /SIZE_MISMATCH/);
});
