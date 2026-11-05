import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { importMessage } from './importDecision.ts';
import type { ImportResponse } from './types.ts';

test('permanent deletion removes the recycled-key new-id confirmation path', () => {
  const source = readFileSync(new URL('./importDecision.ts', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /REIMPORT_CONFIRMATION_REQUIRED/);
  assert.doesNotMatch(source, /newDatasetConfirmation/);
  assert.doesNotMatch(source, /回收站/);
});

test('existing and newly imported messages agree with actual response counts', () => {
  const result = (imported: number, existing: number) => ({ datasets: [], all_datasets: [],
    summary: { total: imported + existing, imported, existing } } as ImportResponse);
  const existing = importMessage(result(0, 3));
  assert.equal(existing, '该路径已有数据集。本次选中 3 个（新增 0 / 已有 3）');
  assert.ok(!existing.includes('新建 id'));
  assert.equal(importMessage(result(1, 0)), '本次选中 1 个（新增 1 / 已有 0）');
});
