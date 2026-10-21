import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { previewRequest } from '../../datasets/api.ts';
import { displayRequest } from './display.ts';

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
  assert.match(readFileSync(new URL('./display.ts', import.meta.url), 'utf8'), /size: 'full'/);
  assert.match(workbench, /onBand=\{setDisplayBand\}/);
  assert.match(canvas, /image.onload/);
  assert.doesNotMatch(canvas, /await\s+image\.decode\(/);
});

test('display modes are exclusive, preserve RGB order and reject duplicates', () => {
  assert.deepEqual(displayRequest('single', 2, [4, 2, 1], 'none', 5), { band: 2, size: 'full', stretch: 'none' });
  assert.deepEqual(displayRequest('rgb', 2, [4, 2, 1], 'auto', 5), { bands: '4,2,1', size: 'full', stretch: 'auto' });
  assert.deepEqual(displayRequest('auto', 2, [4, 2, 1], 'auto', 5), { bands: 'auto', size: 'full', stretch: 'auto' });
  assert.throws(() => displayRequest('rgb', 0, [1, 1, 2], 'auto', 5));
  assert.throws(() => displayRequest('single', 5, [0, 1, 2], 'auto', 5));
});

test('entry defaults to backend automatic selection and displays returned RGB wavelengths', () => {
  const source = readFileSync(new URL('../AnnotationWorkbench.tsx', import.meta.url), 'utf8');
  assert.match(source, /useState<DisplayMode>\('auto'\)/);
  assert.match(source, /base\.wavelengths/);
  assert.match(source, /base\.fallback/);
});
