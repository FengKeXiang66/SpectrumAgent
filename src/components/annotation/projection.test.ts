import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const source = readFileSync(new URL('./AnnotationWorkbench.tsx', import.meta.url), 'utf8');
test('projection consumes save response, shows a selectable absolute path and fixed folder command', () => {
  assert.match(source, /setExportResult\(result\.export\)/);
  assert.match(source, /readOnly value=\{exportResult\.path\}/);
  assert.match(source, /event\.currentTarget\.select\(\)/);
  assert.match(source, /invoke\('open_exports_directory', \{ cubeId: id \}\)/);
  assert.doesNotMatch(source, /exports\/(status|regenerate)/);
});
test('projection failures keep save available and explicitly explain overwrite retry', () => {
  assert.match(source, /标注已保存；JSON 投影失败/);
  assert.match(source, /重试须覆写，否则会多出一个版本/);
  assert.match(source, /JSON 投影：/);
  for (const status of ['最新', '失败', '过期']) assert.ok(source.includes(`'${status}'`));
  assert.match(source, /overwrite: true, confirm: true/);
  assert.doesNotMatch(source, /disabled=\{[^}]*exportResult/);
  assert.match(source, /!exportResult\.ok && exportResult\.error && <p role="alert" className="annotation-error"/);
  assert.match(source, /exportResult\?\.ok && exportResult\.warning && <p role="status" className="annotation-warning"/);
  assert.doesNotMatch(source, /exportResult\.ok \? exportResult\.error/);
});
