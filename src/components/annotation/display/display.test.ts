import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { previewRequest } from '../../datasets/api.ts';
import { applyLut, changeLut, DEFAULT_LUT, displayRequest, makeLut, validLut } from './display.ts';

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

test('default LUT is identity for all 256 intensities', () => {
  assert.deepEqual([...makeLut(DEFAULT_LUT)], Array.from({ length: 256 }, (_, i) => i));
});

test('LUT rejects nonfinite/out of range/gap under 16 and preserves last valid parameters', () => {
  const previous = { black: 100, white: 200, gamma: 2 };
  for (const next of [
    { black: -1, white: 255, gamma: 1 }, { black: 129, white: 255, gamma: 1 },
    { black: 0, white: 127, gamma: 1 }, { black: 0, white: 256, gamma: 1 },
    { black: 128, white: 128, gamma: 1 }, { black: 128, white: 143, gamma: 1 },
    { black: 0, white: 255, gamma: .19 }, { black: 0, white: 255, gamma: 5.1 },
    { black: NaN, white: 255, gamma: 1 },
  ]) {
    assert.equal(validLut(next), false);
    assert.equal(changeLut(previous, next), previous);
    assert.throws(() => makeLut(next));
  }
  for (const gamma of [.2, 5]) assert.equal(validLut({ black: 128, white: 144, gamma }), true);
});

test('LUT follows clamp and inverse gamma, one table for RGB, alpha unchanged and input untouched', () => {
  const values = { black: 20, white: 200, gamma: 2 };
  const lut = makeLut(values);
  assert.equal(lut[0], 0); assert.equal(lut[255], 255);
  assert.equal(lut[100], Math.round(((100-20)/(200-20)) ** .5*255));
  const source = new Uint8ClampedArray([100, 100, 100, 128, 20, 20, 20, 255]);
  const before = source.slice(), after = applyLut(source, lut);
  assert.deepEqual([...after], [lut[100], lut[100], lut[100], 128, 0, 0, 0, 255]);
  assert.deepEqual(source, before);
});

test('manual LUT values stay local and are independent of image request keys', () => {
  const source = readFileSync(new URL('../AnnotationWorkbench.tsx', import.meta.url), 'utf8');
  const toolbar = readFileSync(new URL('./DisplayToolbar.tsx', import.meta.url), 'utf8');
  const requestEffect = source.slice(source.indexOf('let selection;'), source.indexOf('const execute ='));
  assert.doesNotMatch(requestEffect, /displayLut/);
  assert.doesNotMatch(toolbar, /\binvoke\s*\(|\bfetch\s*\(|\.preview\s*\(/);
  assert.match(source, /displayStretch === 'manual' \? 'none' : 'auto'/);
});
