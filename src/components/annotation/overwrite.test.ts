import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { overwriteSummary } from './overwrite.ts';
import type { Statistics } from './types.ts';

const current: Statistics = { n_pixels: 148352, labeled_pixels: 2607, blank_pixels: 145233, uncertain_pixels: 512,
  labeled_percent: 0, blank_percent: 0, uncertain_percent: 0, label_counts: { '0': 0, '1': 2607 },
  pending_pixels: 0, dominant_label_id: null };
const previous = { version_no: 1, created_at: '2026-11-01 17:30', labeled_pixels: 2607 };

test('C4: previous version total and current label-index counts render as separate summaries', () => {
  assert.deepEqual(overwriteSummary(previous, current, [{ name: 'PE' }, { name: 'PP' }]), [
    '将覆写 v1（2026-11-01 17:30 创建，2,607 px 已标注）',
    '本次保存将写入：PP 2,607 px · 留白 145,233 px · 不确定 512 px',
  ]);
});
test('C4: zero classes and uncertainty are omitted while zero blank pixels remain visible', () => {
  assert.equal(overwriteSummary(previous, { ...current, label_counts: { '0': 0 }, blank_pixels: 0, uncertain_pixels: 0 },
    [{ name: 'PE' }])[1], '本次保存将写入：留白 0 px');
});
const source = readFileSync(new URL('./AnnotationWorkbench.tsx', import.meta.url), 'utf8');
test('C4: missing overwrite summary cannot suppress the confirmation dialog', () => {
  assert.doesNotMatch(source, /confirmOverwrite\s*&&\s*overwriteText/);
});
test('C1/C2/C3/C7: auto-default uses a touched ref, resets per dataset, and follows the version count', () => {
  assert.match(source, /overwriteTouched = useRef\(false\)/);
  assert.match(source, /overwriteTouched\.current = false;[\s\S]*?setVersions\(\[\]\);[\s\S]*?\}, \[id\]\)/);
  assert.match(source, /if \(!overwriteTouched\.current && versions\.length\) setOverwrite\(true\);\s*\}, \[versions\.length\]\)/);
  assert.match(source, /onChange=\{event => \{ overwriteTouched\.current = true; setOverwrite\(event\.target\.checked\); \}\}/);
});
test('C1/C3/C6: overwrite retains the confirmation gate and cancelling only dismisses the dialog', () => {
  assert.match(source, /if \(overwrite && !confirmed\) \{ setConfirmOverwrite\(true\); return; \}/);
  assert.match(source, /overwrite: true, confirm: true/);
  assert.match(source, /onClick=\{\(\) => setConfirmOverwrite\(false\)\}>取消/);
  assert.match(source, /取消勾选可另存新版本/);
});
