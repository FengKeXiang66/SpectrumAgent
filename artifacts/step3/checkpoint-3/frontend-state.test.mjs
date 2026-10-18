import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from '../../../node_modules/typescript/lib/typescript.js';

const source = await readFile(new URL('../../../src/status.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } });
const { acceptSnapshot } = await import('data:text/javascript;base64,' + Buffer.from(compiled.outputText).toString('base64'));
const state = (generation_id, phase) => ({ generation_id, phase, cleanup_complete: false });

test('late snapshot cannot resurrect Ready after Failed or Stopping', () => {
  for (const phase of ['Failed', 'Stopping']) {
    const current = state(2, phase);
    assert.equal(acceptSnapshot(current, state(2, 'Ready')), current);
    assert.equal(acceptSnapshot(current, state(1, 'Ready')), current);
  }
});
test('same-generation cleanup updates and a new retry generation are accepted', () => {
  const failed = state(2, 'Failed');
  const cleaned = { ...failed, cleanup_complete: true };
  assert.equal(acceptSnapshot(failed, cleaned), cleaned);
  const retry = state(3, 'Starting');
  assert.equal(acceptSnapshot(cleaned, retry), retry);
  const ready = state(3, 'Ready');
  assert.equal(acceptSnapshot(retry, ready), ready);
  assert.equal(acceptSnapshot(ready, cleaned), ready);
});
