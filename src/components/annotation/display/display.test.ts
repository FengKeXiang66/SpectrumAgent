import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { previewRequest } from '../../datasets/api.ts';

test('old numeric preview call keeps the exact single-band request', () => {
  assert.deepEqual(previewRequest('cube', 0), { op: 'preview', id: 'cube', band: 0 });
});

test('extended preview request projects only allowed keys and explicit full resolution', () => {
  assert.deepEqual(previewRequest('cube', { band: 7, size: 'full', arbitrary: 'ignored' } as never),
    { op: 'preview', id: 'cube', band: 7, size: 'full' });
});

test('S05 band changes use display state, full resolution, and retain PNG onload hotfix', () => {
  const workbench = readFileSync(new URL('../AnnotationWorkbench.tsx', import.meta.url), 'utf8');
  const canvas = readFileSync(new URL('../canvas/AnnotationCanvas.tsx', import.meta.url), 'utf8');
  assert.match(workbench, /size: 'full'/);
  assert.match(workbench, /onBand=\{setDisplayBand\}/);
  assert.match(canvas, /image.onload/);
  assert.doesNotMatch(canvas, /await\s+image\.decode\(/);
});
