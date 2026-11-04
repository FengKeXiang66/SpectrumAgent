import test from 'node:test';
import assert from 'node:assert/strict';
import { importMessage, newDatasetConfirmation } from './importDecision.ts';
import type { ImportResponse } from './types.ts';

test('only the absent-active recycled-key error promises a new dataset id', () => {
  const copy = newDatasetConfirmation({ error: 'REIMPORT_CONFIRMATION_REQUIRED' });
  assert.ok(copy);
  for (const text of ['新建 id', '从头标注', '30 天', '双份空间']) assert.ok(copy.includes(text));
});

test('active records and concurrent active conflicts never open the fresh-id confirmation', () => {
  for (const response of [{ error: 'REIMPORT_ACTIVE_EXISTS' }, { error: 'IMPORT_CONFLICT' },
    { datasets: [], summary: { total: 1, imported: 0, existing: 1 } }, null, 'REIMPORT_CONFIRMATION_REQUIRED']) {
    assert.equal(newDatasetConfirmation(response), null);
  }
});

test('existing and newly imported messages agree with actual response counts', () => {
  const result = (imported: number, existing: number) => ({ datasets: [], all_datasets: [],
    summary: { total: imported + existing, imported, existing } } as ImportResponse);
  const existing = importMessage(result(0, 3));
  assert.equal(existing, '该路径已有数据集。本次选中 3 个（新增 0 / 已有 3）');
  assert.ok(!existing.includes('新建 id'));
  assert.equal(importMessage(result(1, 0)), '本次选中 1 个（新增 1 / 已有 0）');
});
