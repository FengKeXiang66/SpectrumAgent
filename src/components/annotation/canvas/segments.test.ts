import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { blockAction, blockBadge, decodeSegments, hitTest, isBlockClick } from './segments.ts';
import type { Label } from '../types.ts';

test('RGB id decoding retains ids above 255 and verifies every block count', () => {
  const rgba = new Uint8ClampedArray(800 * 4);
  for (let id = 0; id < 800; id++) { rgba[4 * id] = id & 255; rgba[4 * id + 1] = id >> 8; rgba[4 * id + 3] = 255; }
  const map = { png: '', shape: [20, 40] as [number, number], counts: Array(800).fill(1) };
  const decoded = decodeSegments(rgba, map);
  assert.deepEqual([...decoded.ids], Array.from({ length: 800 }, (_, i) => i));
  assert.throws(() => decodeSegments(rgba, { ...map, counts: Array(800).fill(2) }), /计数不一致/);
  assert.throws(() => decodeSegments(rgba.slice(4), map), /尺寸不一致/);
  assert.throws(() => decodeSegments(rgba, { ...map, counts: [1] }), /超出块范围/);
});

test('hitTest is local and rejects out-of-image and fractional coordinates', () => {
  const map = { ids: new Uint16Array([0, 255, 256, 65535]), shape: [2, 2] as [number, number] };
  assert.equal(hitTest(map, 0, 1), 255);
  assert.equal(hitTest(map, 1, 0), 256);
  assert.equal(hitTest(map, 1, 1), 65535);
  for (const [r, c] of [[-1, 0], [2, 0], [0, 2], [0, .5], [NaN, 0]]) assert.equal(hitTest(map, r, c), null);
});

test('3px Euclidean boundary is inclusive; drags produce no block action', () => {
  assert.ok(isBlockClick(10, 10, 13, 10));
  assert.ok(isBlockClick(0, 0, 1.8, 2.4));
  assert.ok(!isBlockClick(10, 10, 13.01, 10));
  assert.ok(!isBlockClick(10, 10, 13, 13));
  assert.deepEqual([blockAction(0, false), blockAction(0, true), blockAction(2, true), blockAction(1, false)],
    ['confirm', 'uncertain', 'erase', null]);
});

test('badges distinguish blank, uncertain, two and three kinds of marking', () => {
  const labels = [{ name: 'PET' }] as Label[];
  const blocks = { label: [-1, -2, 0, 0], purity: [100, 40, 60, 60], label_count: [0, 1, 2, 3] };
  assert.equal(blockBadge(0, [10, 10, 10, 10], blocks, labels), '块 0 · 10 px · 未标注');
  assert.match(blockBadge(1, [10, 10, 10, 10], blocks, labels), /不确定 40%/);
  assert.match(blockBadge(2, [10, 10, 10, 10], blocks, labels), /PET 60% · 含 2 种标记/);
  assert.match(blockBadge(3, [10, 10, 10, 10], blocks, labels), /PET 60% · 含 3 种标记/);
});

test('canvas uses unscaled id loading, the existing contextmenu guard and down-time modifiers', () => {
  const source = readFileSync(new URL('./AnnotationCanvas.tsx', import.meta.url), 'utf8');
  assert.match(source, /context\.imageSmoothingEnabled = false/);
  assert.match(source, /context\.drawImage\(image, 0, 0\)/);
  assert.equal((source.match(/onContextMenu=/g) ?? []).length, 1);
  assert.match(source, /onContextMenu=\{event => event\.preventDefault\(\)\}/);
  assert.match(source, /click && event\.button === 2/);
  assert.match(source, /shiftKey: event\.shiftKey/);
  const up = source.slice(source.indexOf('onPointerUp='), source.indexOf('onPointerCancel='));
  assert.doesNotMatch(up, /event\.(shiftKey|button)/);
  assert.ok(up.indexOf('if (current.click)') < up.indexOf('props.onSeed('));
});
