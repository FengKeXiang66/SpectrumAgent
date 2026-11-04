import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const GUARDS = [
  { file: '../components/annotation/annotation-skin.css', media: ['@media (max-width: 720px)'] },
  { file: '../components/preprocess/preprocess-skin.css', media: [] },
  { file: '../components/modeling/modeling-skin.css', media: [], bareModelPanel: true },
];

for (const { file, media, bareModelPanel } of GUARDS) {
  test(`skin guards: ${file.split('/').at(-1)}`, () => {
    const source = readFileSync(new URL(file, import.meta.url), 'utf8');
    assert.doesNotMatch(source, /position:\s*fixed|100vh|z-index/);
    assert.doesNotMatch(source, /!important/);
    assert.deepEqual((source.match(/@media\s*[^{]*/g) ?? []).map(s => s.trim()), media);
    if (bareModelPanel) assert.doesNotMatch(source, /^\s*\.model-panel[^[]/m);
  });
}
