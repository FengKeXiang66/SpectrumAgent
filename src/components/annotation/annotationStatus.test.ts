import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { annotationBadge } from './annotationStatus.ts';
import type { JsonProjectionStatus } from './types.ts';

const status = (value: Partial<JsonProjectionStatus> = {}): JsonProjectionStatus => ({
  exists: true, path: 'C:/data/exports/cube/sample.json', filename: 'sample.json',
  generated_at: '2026-11-05 10:00:00', version_no: 1, reason: null, ...value,
});

test('unread and missing contracts are never guessed as 未标注', () => {
  assert.equal(annotationBadge(undefined, 0).label, '读取标注状态…');
  assert.equal(annotationBadge(undefined, 0).tone, 'pending');
  assert.equal(annotationBadge(null, 3).label, '标注状态未知');
  assert.equal(annotationBadge(null, 3).tone, 'unknown');
});

test('absent file shows 未标注 and explains existing versions when present', () => {
  const fresh = annotationBadge(status({ exists: false, path: null, filename: null,
    generated_at: null, version_no: null, reason: 'no_manifest' }), 0);
  assert.equal(fresh.label, '未标注');
  assert.equal(fresh.tone, 'absent');
  assert.match(fresh.detail, /尚未生成该图的 JSON 标注文件/);
  const failedExport = annotationBadge(status({ exists: false, reason: 'missing_json' }), 2);
  assert.match(failedExport.detail, /已有 2 个标注版本/);
  assert.match(failedExport.detail, /JSON 标注文件缺失/);
});

test('present file shows 已有 JSON 标注文件 with manifest provenance', () => {
  const badge = annotationBadge(status(), 1);
  assert.equal(badge.label, '已有 JSON 标注文件');
  assert.equal(badge.tone, 'present');
  assert.match(badge.detail, /文件名 sample\.json/);
  assert.match(badge.detail, /对应 v1/);
  assert.match(badge.detail, /生成于 2026-11-05 10:00:00/);
});

test('sparse manifest metadata falls back instead of rendering undefined', () => {
  const badge = annotationBadge(status({ filename: null, generated_at: null, version_no: null }), 0);
  assert.equal(badge.label, '已有 JSON 标注文件');
  assert.equal(badge.detail, '该图已生成 JSON 标注文件。');
});

const workbench = readFileSync(new URL('./AnnotationWorkbench.tsx', import.meta.url), 'utf8');
const css = readFileSync(new URL('./annotation.css', import.meta.url), 'utf8');
test('workbench renders a full-width badge from the versions listing, not from save state', () => {
  assert.match(workbench, /annotationBadge\(projectionStatus, versions\.length\)/);
  assert.match(workbench, /annotation-json-status-/);
  assert.match(workbench, /\{badge\.label\}/);
  assert.match(workbench, /\{badge\.detail\}/);
  assert.match(workbench, /aria-label="本图标注状态"/);
  assert.match(workbench, /listing\.json_projection \?\? null/);
  assert.match(workbench, /setProjectionStatus\(undefined\)/);
  assert.match(workbench, /<\/header>\s*<div className=\{`annotation-json-status/);
  assert.doesNotMatch(workbench, /setProjectionStatus\(\{ exists: versions\.length/);
  for (const tone of ['present', 'absent', 'pending', 'unknown']) {
    assert.ok(css.includes(`.annotation-json-status-${tone}`), tone);
  }
});
